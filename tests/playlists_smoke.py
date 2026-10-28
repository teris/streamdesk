"""Real looping, independent output playlists, live preemption/resume and browser management.
Uses temporary MediaMTX/FFmpeg/FFprobe, two local sinks, and a controllable schedule clock.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from media_smoke import port, until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for binary in ('mediamtx','ffmpeg','ffprobe'):parser.add_argument('--'+binary,required=True,type=Path)
    parser.add_argument('--screenshots-dir',type=Path)
    args=parser.parse_args();processes=[];core=None;server=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-playlists-') as temporary:
        base=Path(temporary);(base/'bin').mkdir()
        for binary in ('ffmpeg','ffprobe'):(base/'bin'/binary).symlink_to(getattr(args,binary).resolve())
        api,rtsp,hls=port(),port(),port()
        foreign={'source':'publisher'};config=base/'media.yml'
        config.write_text(yaml.safe_dump({'logLevel':'warn','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,'webrtc':False,'moq':False,
            'hls':True,'hlsAddress':f'127.0.0.1:{hls}','hlsVariant':'mpegts','hlsSegmentDuration':'1s',
            'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':foreign}}))
        def clip(path,color,length=3):
            subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i',f'color=c={color}:s=640x360:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                '-t',str(length),'-c:v','libx264','-preset','ultrafast','-g','30','-pix_fmt','yuv420p','-c:a','aac','-threads','1',str(path)],check=True,capture_output=True)
        standby=base/'offline.mp4';clip(standby,'gray',2)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(standby),
            MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',
            MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/',COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        core.app.config['TESTING']=True
        try:
            with patch.object(core.threading,'Thread'):
                uid=core.add_user('alice','Playlist-Smoke-Password-123',admin=True)
                other=core.add_user('bobby','Playlist-Smoke-Password-456')
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            client=core.app.test_client()
            clock_patch=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));clock_patch.start()
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='playlists',expert_mode=True)
            headers={'X-CSRF-Token':'playlists'}
            def post(path,body):
                result=client.post(path,json=body,headers=headers);assert result.status_code==200,(path,result.status_code,result.json);return result.json
            videos=[]
            for color in ('green','yellow','magenta'):
                path=core.DATA/'media'/'alice'/(color+'.mp4');clip(path,color)
                videos.append(core.write('INSERT INTO videos(user_id,name,path,duration,size,created) VALUES (?,?,?,?,?,?)',(uid,color,str(path),3,path.stat().st_size,time.time())))
            a=post('/api/playlists',{'name':'Playlist A','items':videos[:2]})['id']
            b=post('/api/playlists',{'name':'Playlist B','items':[videos[2]]})['id']
            def profile(scope,ident=None,rules=None,auto=False,delay=0):
                return post('/api/playout',dict(scope=scope,enabled=True,playlist_id=ident,delay_seconds=delay,timezone='UTC',schedules=rules or [],auto_start=auto))
            profile('output:twitch',a,delay=1)
            profile('output:youtube',rules=[dict(playlist_id=b,start='12:00',end='13:00',days=list(range(7)))],auto=True)
            media_log=(base/'media.log').open('wb');processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=media_log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            cfg=yaml.safe_load(config.read_text())
            for kind in ('twitch','youtube'):
                cfg['paths'][user['prefix']+'sink-'+kind]={'source':'publisher'}
                core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(uid,kind,core.encrypt(core.RTSP+user['prefix']+'sink-'+kind)))
            core.atomic(config,yaml.safe_dump(cfg));core.sync_media_runtime()
            clock=[datetime(2026,10,28,12,30,tzinfo=timezone.utc).timestamp()];original_plan=core.PLAYLISTS.plan
            with patch.object(core.PLAYLISTS,'plan',side_effect=lambda user,program,stamp=None:original_plan(user,program,clock[0] if stamp is None else stamp)),patch.object(core,'validate_output',side_effect=lambda value:value):
                core.ENGINE.thread=threading.Thread(target=core.ENGINE.run,daemon=True);core.ENGINE.thread.start();os.environ['STREAMDESK_ENGINE']='1'
                until(lambda:core.READY.is_set() and core.ENGINE.snapshot.get(uid,{}).get('ok'))
                post('/api/start',{})
                programs={kind:core.MODEL.output_program(user,kind)['id'] for kind in ('twitch','youtube')}
                def state(kind):return next(row for row in core.ENGINE.snapshot[uid]['programs'] if row['id']==programs[kind])
                until(lambda:all(state(kind).get('playlist',{}).get('active') for kind in programs),timeout=30)
                def pixel(kind):
                    result=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','6000000','-i',core.RTSP+user['prefix']+'sink-'+kind,'-frames:v','1','-vf','scale=1:1,format=rgb24','-an','-f','rawvideo','pipe:1'],capture_output=True,timeout=12,check=True)
                    return list(result.stdout[:3])
                value=pixel('twitch');assert value[1]>75 and value[2]<60,value
                value=pixel('youtube');assert value[0]>180 and value[2]>180 and value[1]<60,value
                key=(uid,programs['twitch']);pid=core.ENGINE.relays[key][1].pid;time.sleep(7)
                assert core.ENGINE.relays[key][1].pid==pid and core.ENGINE.relays[key][1].poll() is None,'Playlist loop restarted its publisher'
                rid=post('/api/recordings/start',{'source':programs['twitch']})['id'];recorder=core.ENGINE.recorders[uid][1]
                def publish(source,color):
                    log=(base/(source+'.log')).open('wb')
                    process=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i',f'color=c={color}:s=640x360:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-g','30','-pix_fmt','yuv420p','-c:a','aac','-threads','1','-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+source],stdout=subprocess.DEVNULL,stderr=log)
                    processes.append(process);return process
                first=publish('source1','red');second=publish('source2','blue')
                until(lambda:all(state(kind)['selected_source']=='source1' for kind in programs),timeout=30)
                saved=core.rows('SELECT offset FROM playlist_positions WHERE user_id=? AND program=? AND playlist_id=?',(uid,programs['twitch'],a))[0]['offset']
                assert key not in core.PLAYLISTS.jobs
                until(lambda:(lambda value:value[0]>180 and value[1]<60 and value[2]<60)(pixel('twitch')),timeout=30)
                first.terminate()
                try:first.wait(timeout=3)
                except subprocess.TimeoutExpired:first.kill();first.wait()
                until(lambda:all(state(kind)['selected_source']=='source2' for kind in programs))
                second.terminate()
                try:second.wait(timeout=3)
                except subprocess.TimeoutExpired:second.kill();second.wait()
                until(lambda:key in core.PLAYLISTS.jobs,timeout=30)
                assert abs(core.PLAYLISTS.jobs[key]['offset']-saved)<.05,(saved,core.PLAYLISTS.jobs[key]['offset'])
                assert core.ENGINE.recorders[uid]==(rid,recorder) and recorder.poll() is None
                post('/api/recordings/stop',{})
                until(lambda:core.rows('SELECT status FROM recordings WHERE id=?',(rid,))[0]['status']=='ready',timeout=30)
                recording=core.rows('SELECT path FROM recordings WHERE id=?',(rid,))[0]['path']
                subprocess.run([str(args.ffmpeg),'-v','error','-i',recording,'-f','null','-'],capture_output=True,check=True,timeout=30)
                post('/api/outputs/youtube/stop',{});time.sleep(2)
                assert not core.configured_forwards(user)[core.output_path(user,'youtube')]
                clock[0]+=86400
                until(lambda:core.ENGINE.snapshot[uid]['output_states'].get('youtube')=='forwarding',timeout=30)
                clock[0]+=3600
                until(lambda:core.ENGINE.snapshot[uid]['output_states'].get('youtube')=='stopped',timeout=30)
                assert core.ENGINE.snapshot[uid]['output_states']['twitch']=='forwarding'
                server=make_server('127.0.0.1',0,core.app,threaded=True);address='http://localhost:'+str(server.server_port);core.PUBLIC=address
                threading.Thread(target=server.serve_forever,daemon=True).start()
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1440,'height':1000},locale='de-DE',timezone_id='Europe/Berlin')
                    context.add_cookies([{'name':'session','value':client.get_cookie('session').value,'url':address}]);page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(address+'/#playlists');page.wait_for_selector('#playlist-create')
                    page.fill('#playlist-folder-form [name=name]','Sendearchiv');page.click('#playlist-folder-form button');page.wait_for_function('() => !busy')
                    page.fill('#playlist-create [name=name]','Playlist C');page.click('#playlist-create button');page.wait_for_function('() => !busy')
                    page.select_option('#playlist-add-video',str(videos[0]));page.click('#playlist-add-item');page.click('#playlist-edit button[type=submit], #playlist-edit button.primary');page.wait_for_function('() => !busy')
                    page.fill('#playlist-edit [name=name]','Noch nicht gespeichert');page.wait_for_timeout(2500);assert page.input_value('#playlist-edit [name=name]')=='Noch nicht gespeichert'
                    page.fill('#playlist-edit [name=name]','Playlist C')
                    page.set_input_files('#playlist-upload input[type=file]',str(standby));page.click('#playlist-upload button');page.wait_for_function('() => !busy')
                    until(lambda:core.rows('SELECT upload_state FROM users WHERE id=?',(uid,))[0]['upload_state']=='ready',timeout=30)
                    page.wait_for_selector('#playlist-videos .playlist-media-row')
                    uploaded=core.rows("SELECT folder_id,duration FROM videos WHERE user_id=? AND name='offline.mp4'",(uid,))[0]
                    assert uploaded['folder_id'] is not None and uploaded['duration']>1
                    if args.screenshots_dir:
                        args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.evaluate('document.activeElement.blur();window.scrollTo(0,0)');page.screenshot(path=str(args.screenshots_dir/'playlists.png'),full_page=True,style='#toast{visibility:hidden!important}')
                    page.goto(address+'/#expert-playlists');page.wait_for_selector('#playlist-profile-form');page.select_option('#playlist-scope','output:youtube');assert page.locator('.playlist-rule').count()==1
                    page.click('#playlist-profile-form button.primary');page.wait_for_function('() => !busy')
                    assert core.rows('SELECT timezone FROM playlist_profiles WHERE user_id=? AND scope=?',(uid,'output:youtube'))[0]['timezone']=='UTC'
                    if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/'playlist-schedules.png'),full_page=True,style='#toast{visibility:hidden!important}')
                    page.set_viewport_size({'width':390,'height':844})
                    for view in ('playlists','expert-playlists'):
                        page.goto(address+'/#'+view);page.wait_for_selector('[data-view="'+view+'"]:visible');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),view
                    assert not errors,errors;browser.close()
                assert yaml.safe_load(config.read_text())['paths']['foreign']==foreign
                print('PASS: continuous real playlist loops, distinct Twitch/YouTube pixels, Source 1/2 priority, persistent resume, uninterrupted recording, scheduled auto-start/stop and manual-stop precedence, folder/playlist browser UI and mobile layout.')
        finally:
            if sys.exc_info()[0] and core:
                print('Snapshots:',core.ENGINE.snapshot,flush=True)
            if core:
                core.ENGINE.running=False
                if core.ENGINE.thread:core.ENGINE.thread.join(timeout=8)
                # Engine.run owns recorder/relay shutdown.
                pass
            if server:server.shutdown()
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
            if sys.exc_info()[0]:
                for path in base.rglob('*.log'):
                    if path.stat().st_size:print(path.name+':\n'+path.read_text(errors='replace')[-4500:])
            if 'clock_patch' in locals():clock_patch.stop()


if __name__=='__main__':main()
