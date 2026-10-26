"""Real per-output routing, fixed defaults, separate source cards and account administration.
Temporary loopback-only MediaMTX/FFmpeg and Chromium; no public platform connection.
"""
import argparse
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
    for binary in ('mediamtx','ffmpeg','ffprobe'):parser.add_argument('--'+binary,required=True,type=Path)
    parser.add_argument('--screenshots-dir',type=Path)
    args=parser.parse_args();processes=[];core=None;server=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-routing-') as temporary:
        base=Path(temporary);(base/'bin').mkdir();(base/'native').mkdir()
        for binary in ('ffmpeg','ffprobe'):(base/'bin'/binary).symlink_to(getattr(args,binary).resolve())
        api,rtsp,hls,rtc,ice=port(),port(),port(),port(),port(True)
        config=base/'media.yml';foreign={'source':'publisher'}
        config.write_text(yaml.safe_dump({'logLevel':'warn','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,
            'hls':True,'hlsAddress':f'127.0.0.1:{hls}','hlsVariant':'mpegts','hlsSegmentDuration':'1s',
            'webrtc':True,'webrtcAddress':f'127.0.0.1:{rtc}','webrtcLocalUDPAddress':f'127.0.0.1:{ice}',
            'webrtcIPsFromInterfaces':False,'webrtcAdditionalHosts':['127.0.0.1'],'moq':False,
            'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':foreign}}))
        clip=base/'offline.mp4';subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=gray:s=640x360:r=30',
            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2','-c:v','libx264','-preset','ultrafast','-g','30','-threads','1','-c:a','aac',str(clip)],check=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(base/'native'),
            STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',
            MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/',COOKIE_SECURE='0',
            STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        core.app.config['TESTING']=True
        try:
            password='Routing-Fixture-Password-123'
            with patch.object(core.threading,'Thread'):
                uid=core.add_user('alice',password,admin=True);other=core.add_user('bobby',password)
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            log=(base/'media.log').open('wb');processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            client=core.app.test_client()
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='routing',expert_mode=True)
            headers={'X-CSRF-Token':'routing'}
            def post(path,body):
                response=client.post(path,json=body,headers=headers);assert response.status_code==200,(path,response.status_code,response.json);return response.json
            assert [row['key'] for row in client.get('/api/status').json['sources']]==['source1','source2']
            keys=[]
            for i in (3,4,5):keys.append(post('/api/routing/sources',{'label':'Camera '+str(i),'protocol':'srt'})['key'])
            assert keys==['source3','source4','source5']
            for kind in ('twitch','youtube','custom'):
                core.write('INSERT INTO outputs(user_id,kind,endpoint,selected,label) VALUES (?,?,?,1,?)',(uid,kind,core.encrypt(core.RTSP+user['prefix']+'sink-'+kind),{'custom':'Provider A','twitch':'Twitch','youtube':'YouTube'}[kind]))
            extra={}
            for platform,label in [('twitch','Twitch account 2'),('youtube','YouTube account 2'),('custom','Provider B')]:
                with patch.object(core,'validate_output',side_effect=lambda value:value):
                    result=post('/api/routing/outputs',{'platform':platform,'label':label,'key':'fixture-key-123456-'+platform,'url':core.RTSP+user['prefix']+'placeholder'})
                extra[platform]=result['kind']
            all_kinds=['twitch','youtube','custom',*extra.values()]
            # Account-specific stream keys are created through the real API. Only the test
            # fixture replaces their endpoints with isolated local sinks before any start.
            with core.LOCK:
                cfg=yaml.safe_load(config.read_text())
                for kind in all_kinds:
                    cfg['paths'][user['prefix']+'sink-'+kind]={'source':'publisher'}
                    core.write('UPDATE outputs SET endpoint=? WHERE user_id=? AND kind=?',(core.encrypt(core.RTSP+user['prefix']+'sink-'+kind),uid,kind))
                core.atomic(config,yaml.safe_dump(cfg));core.sync_media_runtime()
            routes={'twitch':['source1','source2'],'youtube':['source1','source2'],'custom':['source1','source2','source5'],extra['twitch']:['source3'],extra['custom']:['source3','source4'],extra['youtube']:['source5']}
            for kind,sources in routes.items():post('/api/routing/outputs/'+kind+'/sources',{'sources':sources})
            core.sync_media_runtime()
            def publish(key,color):
                log=(base/(key+'.log')).open('wb');process=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i',f'color=c={color}:s=640x360:r=15',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-g','15','-c:a','aac','-ac','2','-threads','1',
                    '-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+key],stdout=subprocess.DEVNULL,stderr=log)
                processes.append(process);until(lambda:core.mtx('paths/get/'+user['prefix']+key).get('online'));return process
            producers={key:publish(key,color) for key,color in [('source1','red'),('source2','green'),('source3','blue'),('source4','yellow'),('source5','magenta')]}
            def stop(process):
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            core.ENGINE.thread=threading.Thread(target=core.ENGINE.run,daemon=True);core.ENGINE.thread.start()
            until(lambda:core.ENGINE.snapshot.get(uid,{}).get('selected')==1)
            post('/api/outputs/select',{'kinds':all_kinds})
            with patch.object(core,'validate_output',side_effect=lambda value:value):post('/api/start',{})
            until(lambda:all(core.ENGINE.snapshot[uid]['output_states'].get(kind)=='forwarding' for kind in all_kinds),timeout=30)
            def selected(kind):
                pid=core.MODEL.output_program(user,kind)['id'];return next(row['selected_source'] for row in core.ENGINE.snapshot[uid]['programs'] if row['id']==pid)
            until(lambda:selected('custom')=='source1' and selected(extra['custom'])=='source3' and selected(extra['twitch'])=='source3' and selected(extra['youtube'])=='source5')
            assert len(core.ENGINE.relays)==5,'Identical source assignments should share their program encoder'
            def pixel(kind):
                result=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','5000000','-i',core.RTSP+user['prefix']+'sink-'+kind,
                    '-frames:v','1','-vf','scale=1:1,format=rgb24','-an','-f','rawvideo','pipe:1'],capture_output=True,timeout=12,check=True)
                return list(result.stdout[:3])
            for kind,channel in [('custom',0),(extra['twitch'],2),(extra['custom'],2)]:
                value=pixel(kind);assert value[channel]>max(value[(channel+1)%3],value[(channel+2)%3])+80,(kind,value)
            value=pixel(extra['youtube']);assert value[0]>180 and value[2]>180 and value[1]<60,value
            pid_a=core.MODEL.output_program(user,'custom')['id'];rid=post('/api/recordings/start',{'source':pid_a})['id'];recorder=core.ENGINE.recorders[uid][1]
            post('/api/routing/sources/source3',{'priority':9})
            until(lambda:selected(extra['custom'])=='source4' and selected(extra['twitch'])=='source3')
            until(lambda:(lambda value:value[0]>180 and value[1]>180 and value[2]<60)(pixel(extra['custom'])),timeout=30)
            stop(producers['source1']);stop(producers['source2'])
            until(lambda:selected('custom')=='source5')
            assert core.ENGINE.recorders[uid]==(rid,recorder) and recorder.poll() is None
            value=pixel('custom');assert value[0]>180 and value[2]>180 and value[1]<60,value
            assert selected(extra['twitch'])=='source3' and selected(extra['custom'])=='source4'
            print('PASS: six local outputs carry independently selected real signals; Source 1/2 fallback to Source 5 for provider A; provider B follows its own priorities; one program recording stays active.',flush=True)
            server=make_server('127.0.0.1',0,core.app,threaded=True);address='http://127.0.0.1:'+str(server.server_port);core.PUBLIC=address
            threading.Thread(target=server.serve_forever,daemon=True).start()
            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=['--autoplay-policy=no-user-gesture-required'])
                context=browser.new_context();context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':address}])
                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(address+'/#sources');page.wait_for_selector('#source-cards .source')
                assert page.locator('#source-cards .source').count()==5
                page.locator('#source1 .source-credentials summary').click();page.wait_for_selector('#source1 .credential-fields code')
                assert page.locator('#source2 .credential-fields code').count()==0
                page.locator('#source1 .source-credentials summary').first.click()
                if args.screenshots_dir:
                    args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(args.screenshots_dir/'rc6-sources.png'),full_page=True)
                page.goto(address+'/#expert-routing');page.wait_for_selector('#routing-source-nav button')
                assert page.locator('#routing-source-nav button').count()==5
                if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'rc6-routing.png'),full_page=True)
                page.goto(address+'/#dashboard');page.wait_for_selector('#program-select')
                page.select_option('#program-select',extra['youtube'])
                page.wait_for_function("() => document.querySelector('#program-link').value.includes('/program/route-')")
                expected=core.MODEL.output_program(user,extra['youtube'])['id']
                assert page.locator('#program-link').input_value().endswith('/program/'+expected+'/')
                assert page.locator('#destination').inner_text()=='YouTube account 2'
                until(lambda:page.frame_locator('#source3 iframe').locator('video').evaluate('video => video.readyState>=2 && video.currentTime>.2'),timeout=30)
                if args.screenshots_dir:
                    args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(args.screenshots_dir/'rc6-dashboard.png'),full_page=True)
                # Ordinary users and admins both have a visible account menu and can change passwords.
                for ident,name in ((other,'bobby'),(uid,'alice')):
                    account=browser.new_context();signed=core.app.test_client()
                    with signed.session_transaction() as session:session.update(uid=ident,version=1,csrf='account')
                    oldcookie=signed.get_cookie('session').value
                    account.add_cookies([{'name':'session','value':oldcookie,'url':address}]);tab=account.new_page();tab.on('pageerror',lambda error:errors.append(str(error)))
                    tab.goto(address+'/#account');tab.wait_for_selector('#password-form:visible')
                    tab.fill('#password-form [name=current]',password);tab.fill('#password-form [name=password]','Changed-Routing-Password-456');tab.click('#password-form button')
                    tab.wait_for_function("() => document.querySelector('#password-form .form-feedback')?.textContent.includes('geändert')")
                    assert tab.request.get(address+'/api/status').status==200
                    stale=core.app.test_client();stale.set_cookie('session',oldcookie);assert stale.get('/api/status').status_code==401
                    tab.close();account.close()
                # Admin account's current cookie has changed; re-authenticate test UI through the real login.
                admin=browser.new_context();adminpage=admin.new_page();adminpage.goto(address+'/login')
                adminpage.fill('[name=username]','alice');adminpage.fill('[name=password]','Changed-Routing-Password-456');adminpage.click('button[type=submit]')
                adminpage.wait_for_function("() => location.pathname === '/'");adminpage.goto(address+'/#administration');adminpage.wait_for_selector('#user-list .user-row')
                bobby=adminpage.locator('#user-list .user-row').filter(has_text='bobby')
                bobby.get_by_role('button',name='Deaktivieren',exact=True).click();bobby.get_by_role('button',name='Benutzer löschen',exact=True).wait_for()
                bobby.get_by_role('button',name='Benutzer löschen',exact=True).click();bobby.locator('input').fill('bobby');bobby.get_by_role('button',name='Konto löschen',exact=True).click()
                until(lambda:not core.rows('SELECT id FROM users WHERE id=?',(other,)))
                for view in ('dashboard','sources','expert-routing','expert-outputs','settings','account'):
                    adminpage.set_viewport_size({'width':390,'height':844});adminpage.goto(address+'/#'+view);adminpage.wait_for_timeout(300)
                    assert adminpage.evaluate('document.documentElement.scrollWidth<=innerWidth'),view+' horizontal overflow'
                assert not errors,errors
                browser.close()
            # The live program recorder still survives priority changes and independent routing.
            core.ENGINE.stop_record(uid,'Test manually stopped.')
            until(lambda:core.rows('SELECT status FROM recordings WHERE id=?',(rid,))[0]['status']=='ready')
            assert yaml.safe_load(config.read_text())['paths']['foreign']==foreign
            print('PASS: source-specific credential cards, output program selection/link, own-password change for user/admin, inactive-user deletion, mobile layout and tenant isolation.',flush=True)
        finally:
            if sys.exc_info()[0] and core:
                print('Snapshots:',core.ENGINE.snapshot,flush=True)
                for path in [*base.glob('*.log'),*(base/'data').glob('relay-*.log')]:print(path.name+':\n'+path.read_text()[-2000:],flush=True)
            if core:
                core.ENGINE.running=False
                if core.ENGINE.thread:core.ENGINE.thread.join(timeout=12)
            if server:server.shutdown()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':main()
