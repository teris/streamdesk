"""Opt-in local media/browser smoke test. No external outputs or production data.

Run separately: python tests/media_smoke.py --mediamtx /path/to/mediamtx --ffmpeg /path/to/ffmpeg
Requires Playwright with Chromium. Uses temporary data and loopback listeners only.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def port(udp=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def until(callback, timeout=20):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = callback()
            if result:
                return result
        except Exception as error:
            last_error = error
        time.sleep(.25)
    raise AssertionError('Timed out waiting for local media state') from last_error



def audio_level(video):
    """Measure decoded browser audio without playing the test tone to speakers."""
    return video.evaluate("""async video => {
        if(!video.__meter){
            const stream=video.captureStream();
            if(!stream.getAudioTracks().length)throw new Error('No decoded audio track in preview');
            const context=new AudioContext(),source=context.createMediaStreamSource(stream),analyser=context.createAnalyser(),silent=context.createGain();
            silent.gain.value=0;source.connect(analyser);analyser.connect(silent);silent.connect(context.destination);
            video.__meter={context,analyser};
        }
        const {context,analyser}=video.__meter;await context.resume();
        await new Promise(resolve=>setTimeout(resolve,150));
        const samples=new Float32Array(analyser.fftSize);analyser.getFloatTimeDomainData(samples);
        return Math.sqrt(samples.reduce((sum,value)=>sum+value*value,0)/samples.length);
    }""")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx', required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--screenshots-dir',type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    media_bin, ffmpeg = Path(args.mediamtx).resolve(), Path(args.ffmpeg).resolve()
    processes = []
    with tempfile.TemporaryDirectory(prefix='streamdesk-smoke-') as temporary:
        base = Path(temporary)
        (base / 'bin').mkdir()
        (base / 'bin' / 'ffmpeg').symlink_to(ffmpeg)
        (base / 'native').mkdir()
        api, rtsp, hls, rtc, ice = port(), port(), port(), port(), port(True)
        config = base / 'mediamtx.yml'
        config.write_text(yaml.safe_dump({'logLevel':'warn','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,
            'hls':True,'hlsAddress':f'127.0.0.1:{hls}','hlsVariant':'mpegts','hlsSegmentDuration':'1s',
            'webrtc':False,'webrtcAddress':f'127.0.0.1:{rtc}','webrtcLocalUDPAddress':f'127.0.0.1:{ice}',
            'webrtcIPsFromInterfaces':False,'webrtcAdditionalHosts':['127.0.0.1'],'moq':False,
            'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':{'source':'publisher'}}}))
        clip = base / 'standby.mp4'
        subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','color=c=black:s=640x360:r=15',
            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','1','-c:v','libx264','-preset','ultrafast',
            '-pix_fmt','yuv420p','-c:a','aac','-threads','1',str(clip)],check=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(base/'native'),
            STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',
            MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/',
            COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(root))
        import app as core
        core.app.config['TESTING'] = True
        server = None
        try:
            with patch.object(core.threading,'Thread'):
                uid = core.add_user('alice','Smoke-Fixture-Password-12345',admin=True)
                core.add_user('bobby','Smoke-Fixture-Password-98765')
            media_log = (base/'media.log').open('wb')
            processes.append(subprocess.Popen([str(media_bin),str(config)],stdout=media_log,stderr=subprocess.STDOUT))
            until(lambda: core.mtx('config/global/get'))
            core.sync_media_runtime()
            user = core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            client = core.app.test_client()
            with client.session_transaction() as session:
                session.update(uid=uid,version=1,csrf='smoke-csrf')
            headers = {'X-CSRF-Token':'smoke-csrf'}
            assert client.post('/api/expert-mode',json={'enabled':True},headers=headers).status_code == 200
            assert client.post('/api/native-recording',json={'source':'source2','enabled':True,'segment':'1m','retention':'1d'},headers=headers).status_code == 200
            publish_log = (base/'publish.log').open('wb')
            processes.append(subprocess.Popen([str(ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i','testsrc=size=640x360:rate=15',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-c:v','libx264','-preset','ultrafast','-tune','zerolatency',
                '-pix_fmt','yuv420p','-g','15','-c:a','aac','-threads','1','-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+'source1'],
                stdout=subprocess.DEVNULL,stderr=publish_log))
            core.ENGINE.thread = threading.Thread(target=core.ENGINE.run,daemon=True)
            core.ENGINE.thread.start()
            # Exercise the production reconciliation path after starting the explicit test engine.
            os.environ['STREAMDESK_ENGINE']='1'
            until(lambda: core.ENGINE.snapshot.get(uid,{}).get('selected') == 1)
            # Deliberately local destinations are allowed only inside this test context.
            with core.LOCK:
                cfg = yaml.safe_load(config.read_text())
                for name in ('sink-a','sink-b'):
                    cfg['paths'][user['prefix']+name]={'source':'publisher'}
                core.atomic(config,yaml.safe_dump(cfg))
                core.sync_media_runtime()
            for kind,sink in [('twitch','sink-a'),('youtube','sink-b')]:
                core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(uid,kind,core.encrypt(core.RTSP+user['prefix']+sink)))
            with patch.object(core,'validate_output',side_effect=lambda value:value):
                assert client.post('/api/outputs/twitch/start',json={},headers=headers).status_code==200
                assert client.post('/api/outputs/youtube/start',json={},headers=headers).status_code==200
            until(lambda: all(core.ENGINE.snapshot[uid]['output_states'].get(kind)=='forwarding' for kind in ('twitch','youtube')))
            saved_outputs=core.rows('SELECT * FROM outputs WHERE user_id=? ORDER BY kind',(uid,))
            assert client.post('/api/admin/services',json={'id':'twitch','enabled':False},headers=headers).status_code==200
            until(lambda: core.ENGINE.snapshot[uid]['output_states'].get('twitch')=='stopped')
            assert core.ENGINE.snapshot[uid]['output_states']['youtube']=='forwarding'
            assert client.post('/api/outputs/twitch/start',json={},headers=headers).status_code==403
            assert core.rows('SELECT * FROM outputs WHERE user_id=? ORDER BY kind',(uid,))==saved_outputs
            assert client.post('/api/admin/services',json={'id':'twitch','enabled':True},headers=headers).status_code==200
            assert not core.configured_forwards(user)[core.output_path(user,'twitch')]
            with patch.object(core,'validate_output',side_effect=lambda value:value):
                assert client.post('/api/outputs/twitch/start',json={},headers=headers).status_code==200
            until(lambda: core.ENGINE.snapshot[uid]['output_states'].get('twitch')=='forwarding')
            assert client.post('/api/admin/services',json={'id':'recording','enabled':False},headers=headers).status_code==200
            until(lambda: core.mtx('config/paths/get/'+user['prefix']+'source2')['record'] is False)
            assert client.post('/api/admin/services',json={'id':'recording','enabled':True},headers=headers).status_code==200
            until(lambda: core.mtx('config/paths/get/'+user['prefix']+'source2')['record'] is True)
            assert client.post('/api/outputs/youtube/stop',json={},headers=headers).status_code==200
            until(lambda: core.ENGINE.snapshot[uid]['output_states'].get('youtube')=='stopped')
            assert core.ENGINE.snapshot[uid]['output_states']['twitch']=='forwarding'
            server = make_server('127.0.0.1',0,core.app,threaded=True)
            address = 'http://127.0.0.1:'+str(server.server_port)
            core.PUBLIC=address
            threading.Thread(target=server.serve_forever,daemon=True).start()
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--autoplay-policy=no-user-gesture-required'])
                context=browser.new_context(permissions=['camera','microphone'])
                context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':address}])
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(address+'/#expert');page.wait_for_selector('#expert-form')
                page.uncheck('#expert-mode');page.click('#expert-form button')
                page.wait_for_function('() => !busy')
                page.goto(address+'/#expert-protocols')
                page.wait_for_function("() => location.hash === '#expert'")
                assert not page.locator('#webrtc-server-form').is_visible()
                assert page.request.post(address+'/api/sources/mode',headers={'X-CSRF-Token':'smoke-csrf'},data={'mode':'source2'}).status==403
                page.goto(address+'/#settings-appearance');page.wait_for_selector('#theme-form')
                assert not page.locator('#source-mode-form').is_visible()
                assert not page.locator('#native-form').is_visible()
                if args.screenshots_dir:
                    args.screenshots_dir.mkdir(parents=True,exist_ok=True)
                    page.screenshot(path=str(args.screenshots_dir/'desktop-dark.png'))
                page.select_option('#theme','light');page.click('#theme-form button')
                page.wait_for_function('() => !busy')
                page.wait_for_function("() => document.documentElement.dataset.resolvedTheme === 'light'")
                assert page.locator('body').evaluate("el => getComputedStyle(el).getPropertyValue('--panel').trim()")=='#fff'
                if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'desktop-light.png'))
                page.goto(address+'/#expert');page.check('#expert-mode');page.click('#expert-form button')
                page.wait_for_function('() => !busy')
                page.goto(address+'/#expert-protocols');page.wait_for_selector('#webrtc-fields:not([disabled])')
                page.wait_for_function("() => document.querySelector('#webrtc-availability').textContent.includes('nach der WebRTC-Aktivierung')")
                assert page.locator('[data-webrtc-link]').first.get_attribute('aria-disabled')=='true'
                page.check('#webrtc-enabled');page.fill('#webrtc-hosts','127.0.0.1')
                page.click('#webrtc-server-form button[type=submit]');page.wait_for_function('() => !busy')
                page.wait_for_function("() => document.querySelector('#webrtc-availability').textContent.includes('freigeschaltet')")
                assert page.locator('[data-webrtc-link]').first.get_attribute('aria-disabled')=='false'
                if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'expert-protocols.png'))
                page.goto(address+'/#expert-routing');page.wait_for_selector('#routing-source-nav button')
                assert page.locator('#routing-source-nav button').count()==2
                assert page.request.post(address+'/api/routing/sources/source1',headers={'X-CSRF-Token':'smoke-csrf'},data={'priority':5}).status==403
                assert core.rows('SELECT source_mode FROM users WHERE id=?',(uid,))[0]['source_mode']=='auto'
                until(lambda: core.ENGINE.snapshot[uid].get('selected')==1)
                page.goto(address+'/#settings-appearance');page.wait_for_selector('#theme-form')
                assert not page.locator('#expert-subnav').is_visible()
                assert not page.locator('#expert-form').is_visible()
                page.set_viewport_size({'width':390,'height':844})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
                if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'mobile-light.png'))
                page.goto(address+'/#expert-protocols');page.wait_for_selector('#expert-subnav:visible')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile submenu horizontal overflow'
                if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'mobile-expert.png'))
                publisher=context.new_page();publisher.goto(address+'/webrtc/2/publish/');publisher.click('#rtc-start')
                publisher.wait_for_function("() => document.querySelector('#rtc-status').textContent === 'Kamera wird gesendet.'",timeout=30000)
                reader=context.new_page();reader.goto(address+'/webrtc/1/play/');reader.click('#rtc-start')
                reader.wait_for_function("() => document.querySelector('#rtc-video').readyState >= 2",timeout=30000)
                public_url=client.post('/api/viewer-link',json={'enabled':True},headers=headers).json['url']
                public=browser.new_context();viewer=public.new_page();viewer.goto(public_url)
                viewer.wait_for_function("() => document.querySelector('video').readyState >= 2",timeout=30000)
                assert client.post('/api/viewer-link',json={'enabled':False},headers=headers).status_code==200
                assert public.request.get(public_url+'index.m3u8').status==404
                publisher.click('#rtc-stop')
                until(lambda: client.get('/api/native-recordings').json['segments'])
                segments=client.get('/api/native-recordings').json['segments']
                assert segments[0]['size']>0
                response=client.get(segments[0]['url']);assert response.status_code==200;response.close()
                segment_path=core.FEATURES.recording_directory(user,segments[0]['source'])/segments[0]['name']
                subprocess.run([str(ffmpeg),'-v','error','-i',str(segment_path),'-t','1','-f','null','-'],check=True,capture_output=True)
                assert client.post('/api/admin/services',json={'id':'webrtc','enabled':False},headers=headers).status_code==200
                until(lambda: not core.FEATURES.program_preview.jobs)
                assert client.get('/api/webrtc/ice').status_code==403
                assert client.get('/program/main/index.m3u8').status_code==200
                assert not errors,errors
                browser.close()
            assert yaml.safe_load(config.read_text())['paths']['foreign']=={'source':'publisher'}
            print('PASS: real MediaMTX forwarding, global provider suspension with retained keys, native recording pause/resume, WebRTC suspension with continuing HLS preview, isolated target stop, themes/mobile/expert gating, WHIP/WHEP, viewer revocation and native segments.')
        finally:
            if sys.exc_info()[0]:
                print('Engine snapshots:',core.ENGINE.snapshot,flush=True)
                print('Source modes:',core.rows('SELECT username,source_mode FROM users'),flush=True)
                try:
                    print('Media paths:',[{key:item.get(key) for key in ('name','online','available','inboundBytes','tracks')} for item in core.mtx('paths/list?itemsPerPage=1000').get('items',[])],flush=True)
                except Exception:
                    pass
            core.ENGINE.running=False
            if core.ENGINE.thread:core.ENGINE.thread.join(timeout=10)
            if server:server.shutdown()
            for process in reversed(processes):
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            for log in ('media.log','publish.log'):
                path=base/log
                if path.exists() and path.stat().st_size:print(log+':\n'+path.read_text()[-3500:])


if __name__=='__main__':
    main()
