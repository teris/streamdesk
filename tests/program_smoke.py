"""Regression for continuous program recording and HLS/WebRTC preview without outputs.
Uses real MediaMTX, FFmpeg/FFprobe and Chromium on temporary loopback listeners.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import yaml
from media_smoke import port, until
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for binary in ('mediamtx','ffmpeg','ffprobe'):
        parser.add_argument('--'+binary,required=True,type=Path)
    args=parser.parse_args()
    processes=[];core=None;server=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-program-') as temporary:
        base=Path(temporary);(base/'bin').mkdir()
        for binary in ('ffmpeg','ffprobe'):
            (base/'bin'/binary).symlink_to(getattr(args,binary).resolve())
        api,rtsp,hls,rtc,ice=port(),port(),port(),port(),port(True)
        config=base/'media.yml'
        config.write_text(yaml.safe_dump({'logLevel':'info','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,
            'hls':True,'hlsAddress':f'127.0.0.1:{hls}','hlsVariant':'mpegts','hlsSegmentDuration':'1s',
            'webrtc':True,'webrtcAddress':f'127.0.0.1:{rtc}','webrtcLocalUDPAddress':f'127.0.0.1:{ice}',
            'webrtcIPsFromInterfaces':False,'webrtcAdditionalHosts':['127.0.0.1'],'moq':False,
            'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':{'source':'publisher'}}}))
        clip=base/'offline.mp4'
        subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=green:s=640x360:r=30',
            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2','-c:v','libx264','-preset','ultrafast',
            '-pix_fmt','yuv420p','-g','30','-c:a','aac','-threads','1',str(clip)],check=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(base/'native'),
            STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',
            MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/',
            COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import app as core
        core.app.config['TESTING']=True
        try:
            with patch.object(core.threading,'Thread'):
                uid=core.add_user('alice','Program-Fixture-Password-12345',admin=True)
            log=(base/'media.log').open('wb')
            processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            client=core.app.test_client()
            with client.session_transaction() as session:
                session.update(uid=uid,version=1,csrf='program',expert_mode=True)
            headers={'X-CSRF-Token':'program'}
            def post(path,body):
                response=client.post(path,json=body,headers=headers)
                assert response.status_code==200,(path,response.status_code,response.json)
                return response.json
            def publish(source,color,size,rate):
                log=(base/(source+'.log')).open('wb')
                # Different resolutions and B-frames reproduce common OBS profiles.
                process=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i',f'color=c={color}:s={size}:r={rate}',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-c:v','libx264','-preset','veryfast','-profile:v','high',
                    '-pix_fmt','yuv420p','-bf','2','-g',str(rate),'-c:a','aac','-ac','2','-threads','1',
                    '-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+source],stdout=subprocess.DEVNULL,stderr=log)
                processes.append(process)
                until(lambda:core.mtx('paths/get/'+user['prefix']+source).get('online'))
                return process
            def stop(process):
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            first=publish('source1','red','1280x720',30)
            second=publish('source2','blue','640x360',15)
            core.ENGINE.thread=threading.Thread(target=core.ENGINE.run,daemon=True);core.ENGINE.thread.start()
            until(lambda:core.ENGINE.snapshot.get(uid,{}).get('selected')==1)
            assert not core.ENGINE.snapshot[uid]['enabled']
            rid=post('/api/recordings/start',{'source':'live'})['id']
            recorder=core.ENGINE.recorders[uid][1];started=time.monotonic()
            def recording_alive():
                assert core.ENGINE.recorders[uid]==(rid,recorder)
                assert recorder.poll() is None
                row=core.rows('SELECT status FROM recordings WHERE id=?',(rid,))[0]
                assert row['status']=='recording',row
            server=make_server('127.0.0.1',0,core.app,threaded=True)
            address='http://127.0.0.1:'+str(server.server_port);core.PUBLIC=address
            threading.Thread(target=server.serve_forever,daemon=True).start()
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
                context=browser.new_context()
                context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':address}])
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                # Navigate away and back: this used to leave the iframe on about:blank.
                page.goto(address+'/#settings');page.wait_for_selector('#theme-form')
                page.click('a.menu-link[href="#dashboard"]')
                page.wait_for_function("() => document.querySelector('#source3 iframe').getAttribute('src') === '/program/main/'")
                frame=page.frame_locator('#source3 iframe')
                frame.locator('video').wait_for()
                def wait_color(video, channel):
                    def matches():
                        pixel=video.evaluate('''video => {
                            if (video.readyState < 2) return [0,0,0];
                            const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
                            const context=canvas.getContext('2d');context.drawImage(video,0,0,1,1);
                            return [...context.getImageData(0,0,1,1).data].slice(0,3);
                        }''')
                        return pixel[channel] > max(pixel[(channel+1)%3],pixel[(channel+2)%3])*1.5+40
                    until(matches,timeout=30)

                until(lambda:frame.locator('video').evaluate('video => video.readyState >= 2 && video.currentTime > .2'),timeout=30)
                rtc_page=context.new_page();rtc_page.on('pageerror',lambda error:errors.append(str(error)))
                rtc_page.goto(address+'/webrtc/3/play/');rtc_page.click('#rtc-start')
                rtc_page.wait_for_function("() => document.querySelector('#rtc-video').readyState >= 2 && document.querySelector('#rtc-video').currentTime > .2",timeout=30000)
                rtc_page.wait_for_function("() => document.querySelector('#rtc-video').srcObject.getAudioTracks().length === 1",timeout=10000)
                wait_color(frame.locator('video'),0)
                wait_color(rtc_page.locator('#rtc-video'),0)
                print('PASS: dashboard HLS and program WebRTC video/audio work without any output, including B-frames.',flush=True)
                recording_alive();time.sleep(2)
                # Losing the unselected source must leave the recording alone.
                stop(second);time.sleep(2);recording_alive()
                second=publish('source2','blue','640x360',15)
                until(lambda:core.ENGINE.snapshot[uid]['sources'][1]['state']=='online')
                time.sleep(4)
                stop(first)
                until(lambda:core.ENGINE.snapshot[uid].get('selected')==2)
                recording_alive();time.sleep(3)
                wait_color(frame.locator('video'),2)
                wait_color(rtc_page.locator('#rtc-video'),2)
                # Starting and stopping external forwarding must never recreate the program.
                with core.LOCK:
                    cfg=yaml.safe_load(config.read_text());cfg['paths'][user['prefix']+'sink']={'source':'publisher'}
                    core.atomic(config,yaml.safe_dump(cfg));core.sync_media_runtime()
                core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(uid,'custom',core.encrypt(core.RTSP+user['prefix']+'sink')))
                with patch.object(core,'validate_output',side_effect=lambda value:value):
                    post('/api/start',{})
                until(lambda:core.ENGINE.snapshot[uid].get('state')=='forwarding')
                post('/api/stop',{});recording_alive()
                stop(second)
                until(lambda:core.ENGINE.snapshot[uid].get('offline_playing'))
                recording_alive();time.sleep(4)
                wait_color(frame.locator('video'),1)
                wait_color(rtc_page.locator('#rtc-video'),1)
                for video in (frame.locator('video'),rtc_page.locator('#rtc-video')):
                    before=video.evaluate('video => video.currentTime')
                    until(lambda:video.evaluate('video => video.currentTime')>before+1,timeout=20)
                recording_alive();recorded_for=time.monotonic()-started
                post('/api/recordings/stop',{})
                until(lambda:core.rows('SELECT status FROM recordings WHERE id=?',(rid,))[0]['status']=='ready')
                recording=core.rows('SELECT * FROM recordings WHERE id=?',(rid,))[0]
                print('Recording timing:',recorded_for,recording['duration'],'process exit:',recorder.returncode,flush=True)
                assert recording['duration']>=recorded_for-5,(recording['duration'],recorded_for)
                assert recording['audio']==1
                assert recorder.returncode in (0,255),recorder.returncode
                subprocess.run([str(args.ffmpeg),'-v','error','-i',recording['path'],'-f','null','-'],check=True,capture_output=True)
                assert not errors,errors
                browser.close()
            print('PASS: one continuous program recording survives unselected source loss, Source 1 → Source 2 (resolution change) → offline, and forwarding start/stop; both previews keep advancing.',flush=True)
        finally:
            if sys.exc_info()[0] and core:
                import shutil
                for movie in (base/'data'/'recordings').rglob('*.mp4'):
                    shutil.copyfile(movie,'/tmp/streamdesk-program-failed.mp4')
                print('Snapshots:',core.ENGINE.snapshot,flush=True)
                for path in [*base.glob('*.log'),*(base/'data').glob('*.log'),*(base/'data'/'recordings').rglob('*.log')]:
                    print(path.name+':\n'+path.read_text()[-6000:],flush=True)
            if core:
                core.ENGINE.running=False
                if core.ENGINE.thread:core.ENGINE.thread.join(timeout=12)
            if server:server.shutdown()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':
    main()
