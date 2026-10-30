"""2.0 studio: real shared playlist, planned output, live preemption, FTP import and browser UI."""
import argparse
from datetime import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo
import yaml
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server
from media_smoke import port, until, audio_level


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('mediamtx','ffmpeg','ffprobe'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--screenshots-dir',type=Path)
    parser.add_argument('--legacy',action='store_true')
    parser.add_argument('--complex',action='store_true')
    parser.add_argument('--startup-delay',type=float,default=0)
    args=parser.parse_args();processes=[];server=None;core=None;clock_patch=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));clock_patch.start()
    with tempfile.TemporaryDirectory(prefix='streamdesk-studio-v2-',dir='/tmp') as directory:
        base=Path(directory);(base/'bin').mkdir();native=base/'native';native.mkdir(mode=0o2770)
        for name in ('ffmpeg','ffprobe'):
            if name=='ffmpeg' and args.startup_delay:
                wrapper=base/'bin'/'ffmpeg';wrapper.write_text('#!'+sys.executable+'\nimport os,sys,time\nif any("source2-playlist.progress" in value for value in sys.argv):time.sleep('+repr(args.startup_delay)+')\nos.execv('+repr(str(args.ffmpeg.resolve()))+',['+repr(str(args.ffmpeg.resolve()))+',*sys.argv[1:]])\n');wrapper.chmod(0o755)
            else:(base/'bin'/name).symlink_to(getattr(args,name).resolve())
        api,rtsp,hls,rtc,ice,rtmp=port(),port(),port(),port(),port(True),port();config=base/'media.yml'
        config.write_text(yaml.safe_dump(dict(logLevel='warn',api=True,apiAddress=f'127.0.0.1:{api}',rtsp=True,rtspAddress=f'127.0.0.1:{rtsp}',rtspTransports=['tcp'],rtmp=True,rtmpAddress=f'127.0.0.1:{rtmp}',srt=False,webrtc=True,webrtcAddress=f'127.0.0.1:{rtc}',webrtcLocalUDPAddress=f'127.0.0.1:{ice}',webrtcIPsFromInterfaces=False,webrtcAdditionalHosts=['127.0.0.1'],moq=False,hls=True,hlsAddress=f'127.0.0.1:{hls}',hlsVariant='mpegts',hlsSegmentDuration='1s',authMethod='internal',authInternalUsers=[],paths={'foreign':{'source':'publisher'}})))
        def clip(path,color,length=8):
            subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c='+color+':s=640x360:r=30'+(',noise=alls=25:allf=t' if args.complex and length>=8 else ''),'-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t',str(length),'-c:v','libx264','-profile:v','baseline','-preset','ultrafast','-g','30','-pix_fmt','yuv420p','-c:a','aac','-threads','1',str(path)],check=True,capture_output=True)
        standby=base/'offline.mp4';clip(standby,'gray',2)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(native),STREAMDESK_DEFAULT_CLIP=str(standby),STREAMDESK_FTP_ENABLED='1',STREAMDESK_FTP_HOST='ftp.example.test',STREAMDESK_PUBLIC='http://localhost:8080',MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',MEDIAMTX_HLS=f'http://127.0.0.1:{hls}/',COOKIE_SECURE='0',STREAMDESK_TRUST_PROXY='0',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        try:
            with patch.object(core.threading,'Thread'):
                uid=core.add_user('studio','Studio-Smoke-Fixture-Password-123',admin=True,legacy=args.legacy)
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0];client=core.app.test_client();headers={'X-CSRF-Token':'studio'}
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='studio',expert_mode=True)
            def post(path,body):
                response=client.post(path,json=body,headers=headers);assert response.status_code==200,(path,response.status_code,response.json);return response.json
            videos=[]
            for color in ('green','yellow','magenta'):
                path=core.DATA/'media'/'studio'/(color+'.mp4');clip(path,color)
                core.convert(uid,path,color)
                videos.append(core.rows('SELECT id FROM videos WHERE user_id=? AND name=?',(uid,color))[0]['id'])
            a=post('/api/playlists',{'name':'Gemeinsame Wiederholung','items':videos[:2]})['id']
            post('/api/playout',dict(scope='source:source2',enabled=True,playlist_id=a,delay_seconds=600,timezone='Europe/Berlin',schedules=[dict(playlist_id=a,start='13:00',end='16:00',days=[0,2])],auto_start=False))
            # Both programmes can share one playlist encoder, even with distinct live routing.
            source=post('/api/routing/sources',{'label':'Extra live','protocol':'rtmp'})['key']
            post('/api/routing/routes',{'kind':'youtube','sources':['source1','source2',source]}) if False else None
            core.MODEL.save_route(user,'youtube',['source1','source2',source]);core.STUDIO.switch_file(user,create=True);core.reconcile()
            log=(base/'media.log').open('wb');processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            cfg=yaml.safe_load(config.read_text())
            for kind in ('twitch','youtube'):
                cfg['paths'][user['prefix']+'sink-'+kind]={'source':'publisher'}
                core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(uid,kind,core.encrypt(f'rtmp://127.0.0.1:{rtmp}/'+user['prefix']+'sink-'+kind)))
            if args.legacy:
                cfg['authInternalUsers'].append({'user':'any','pass':'','ips':['127.0.0.1','::1'],'permissions':[{'action':action,'path':'sink-'+kind} for kind in ('twitch','youtube') for action in ('publish','read')]})
            core.atomic(config,yaml.safe_dump(cfg));core.sync_media_runtime()
            post('/api/planner',dict(title='Mo & Mi: Stream oder Wiederholung',enabled=True,timezone='Europe/Berlin',days=[0,2],start='10:00',end='13:00',playlist_id=a,targets=['twitch','youtube'],sync_twitch=False))
            clock=[datetime(2026,11,2,10,30,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()];original_active=core.STUDIO.active
            with patch.object(core.STUDIO,'active',side_effect=lambda user,kind,stamp=None:original_active(user,kind,clock[0] if stamp is None else stamp)),patch.object(core,'validate_output',side_effect=lambda x:x):
                core.ENGINE.thread=threading.Thread(target=core.ENGINE.run,daemon=True);core.ENGINE.thread.start()
                until(lambda:core.READY.is_set() and core.PLAYLISTS.feeds.get(uid),timeout=40)
                warm_pid=core.PLAYLISTS.feeds[uid]['process'].pid
                if args.startup_delay>5:
                    time.sleep(5.5);assert core.PLAYLISTS.feeds[uid]['process'].pid==warm_pid
                    assert core.PLAYLISTS.feeds[uid]['process'].poll() is None
                    assert any(row.get('playlist',{}).get('preparing') for row in core.ENGINE.snapshot[uid]['programs'])
                    print('PASS: slow playlist encoder survives the former five-second limit while the controller stays responsive.',flush=True)
                ids={kind:core.MODEL.output_program(user,kind)['id'] for kind in ('twitch','youtube')}
                def state(kind):return next(row for row in core.ENGINE.snapshot[uid]['programs'] if row['id']==ids[kind])
                until(lambda:all(state(kind).get('playlist',{}).get('active') and state(kind)['offline_playing'] for kind in ids),timeout=35)
                assert core.PLAYLISTS.feeds[uid]['process'].pid==warm_pid
                assert len(core.PLAYLISTS.feeds)==1 and len(core.PLAYLISTS.feeds[uid]['clients'])>=2
                def frame(kind,filter=None):
                    # Sample a chroma-aligned YUV420 area before converting
                    # the color check to RGB.
                    result=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','6000000','-i',core.RTSP+user['prefix']+'sink-'+kind,'-frames:v','1','-vf',filter or 'scale=2:2,format=rgb24','-an','-f','rawvideo','pipe:1'],capture_output=True,timeout=12,check=True)
                    return result.stdout if filter is not None else result.stdout[:3]
                def audible(path):
                    import array, math
                    result=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','6000000','-i',core.RTSP+path,'-t','1','-vn','-ac','1','-ar','48000','-f','s16le','pipe:1'],capture_output=True,timeout=15,check=True)
                    samples=array.array('h',result.stdout)
                    rms=math.sqrt(sum(value*value for value in samples)/max(1,len(samples)))
                    assert rms>500,(path,rms,len(samples))
                def is_red(kind):
                    pixel=frame(kind);return len(pixel)==3 and pixel[0]>180 and pixel[1]<90 and pixel[2]<90
                def is_blue(kind):
                    pixel=frame(kind);return len(pixel)==3 and pixel[2]>160 and pixel[0]<100
                def label_visible():
                    image=frame('twitch','crop=500:100:0:0,format=rgb24')
                    return sum(1 for i in range(0,len(image),3) if min(image[i:i+3])>180)>100
                until(label_visible,timeout=30)
                for kind in ids:audible(user['prefix']+'sink-'+kind)
                connections={kind:core.mtx('paths/get/'+user['prefix']+'sink-'+kind)['source']['id'] for kind in ids}
                first_feed=core.PLAYLISTS.feeds[uid]['process'].pid;time.sleep(2);assert core.PLAYLISTS.feeds[uid]['process'].pid==first_feed
                recording=post('/api/recordings/start',{'source':'live'});record=core.rows("SELECT * FROM recordings WHERE user_id=? AND status='recording'",(uid,))[0];record_pid=core.ENGINE.recorders[uid][1].pid
                def source_process(name,color):
                    proc=subprocess.Popen([str(args.ffmpeg),'-v','error','-re','-f','lavfi','-i','color=c='+color+':s=640x360:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-c:v','libx264','-preset','ultrafast','-tune','zerolatency','-pix_fmt','yuv420p','-g','30','-threads','1','-c:a','aac','-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(proc);return proc
                source2=source_process('source2','blue');source1=source_process('source1','red')
                until(lambda:all(state(k)['selected_source']=='source1' for k in ids),timeout=35)
                until(lambda:all(is_red(kind) for kind in ids),timeout=20);assert uid not in core.PLAYLISTS.feeds
                saved=core.rows("SELECT offset FROM playlist_positions WHERE user_id=? AND program='source2-playlist'",(uid,))[0]['offset'];assert saved>0
                source1.terminate();source1.wait(timeout=6)
                until(lambda:all(state(k)['selected_source']=='source2' for k in ids),timeout=30);until(lambda:all(is_blue(kind) for kind in ids),timeout=20)
                source2.terminate();source2.wait(timeout=6)
                until(lambda:core.PLAYLISTS.feeds.get(uid) and all(state(k).get('playlist',{}).get('active') for k in ids),timeout=35)
                # Controller state can precede the new RTSP reader's first frame;
                # measure the resumed playlist, rather than the previous live silence.
                until(label_visible,timeout=30)
                for kind in ids:audible(user['prefix']+'sink-'+kind)
                assert all(core.mtx('paths/get/'+user['prefix']+'sink-'+kind)['source']['id']==connections[kind] for kind in ids),'RTMP connection restarted during live/playlist switching'
                assert abs(core.PLAYLISTS.feeds[uid]['job']['offset']-saved)<1
                assert core.ENGINE.recorders[uid][1].pid==record_pid
                post('/api/recordings/stop',{});until(lambda:core.rows('SELECT status FROM recordings WHERE id=?',(record['id'],))[0]['status']=='ready',timeout=30)
                finished=core.rows('SELECT * FROM recordings WHERE id=?',(record['id'],))[0]
                subprocess.run([str(args.ffmpeg),'-v','error','-i',finished['path'],'-f','null','-'],check=True,capture_output=True,timeout=30)
                clock[0]=datetime(2026,11,2,13,30,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
                until(lambda:not any(core.configured_forwards(user).values()),timeout=15)
                # FTP transfer event feeds a real conversion and preserves subfolders.
                account=post('/api/admin/users/'+str(uid)+'/ftp',{'enabled':True,'password':'FTP-Smoke-Fixture-Password-123'})['username']
                home=core.DATA/'ftp'/str(uid);(home/'FTP-Ordner').mkdir();source=home/'FTP-Ordner'/'FTP-Film.mp4';clip(source,'cyan',2)
                (core.DATA/'ftp-transfers.log').write_text(f'{int(time.time())} smoke {account} 127.0.0.1 U {source.stat().st_size} 1 {source}\n')
                core.FTP.run();until(lambda:core.rows("SELECT id FROM videos WHERE user_id=? AND name='FTP-Film.mp4'",(uid,)),timeout=35)
                imported=core.rows("SELECT * FROM videos WHERE user_id=? AND name='FTP-Film.mp4'",(uid,))[0];assert imported['folder_id'];assert not source.exists()
                server=make_server('127.0.0.1',port(),core.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start();address='http://127.0.0.1:'+str(server.server_port)
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(headless=True,args=['--no-sandbox','--mute-audio']);context=browser.new_context(viewport={'width':1440,'height':1100});context.add_init_script("window.__peers=[];const Original=window.RTCPeerConnection;window.RTCPeerConnection=class extends Original {constructor(...args){super(...args);window.__peers.push(this);}};");page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda dialog:dialog.accept())
                    page.goto(address+'/login');page.locator('[name=username]').fill('studio');page.locator('[name=password]').fill('Studio-Smoke-Fixture-Password-123');page.locator('button[type=submit]').click();page.wait_for_url(address+'/')
                    page.evaluate("async()=>{const csrf=document.querySelector('meta[name=csrf-token]').content;await fetch('/api/expert-mode',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({enabled:true})});}")
                    clock[0]=datetime(2026,11,2,10,30,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
                    until(lambda:core.PLAYLISTS.feeds.get(uid),timeout=25)
                    page.wait_for_function("() => !document.querySelector('#program-audio-toggle').disabled")
                    page.locator('#program-audio-toggle').click();preview=page.frame_locator('#source3 iframe').locator('video')
                    until(lambda:preview.evaluate('video=>!video.muted&&video.volume>0'))
                    until(lambda:audio_level(preview)>.005,timeout=25)
                    print('PASS: playlist audio is decoded and enabled from the dashboard button.',flush=True)
                    rtc_page=page.context.new_page();rtc_page.goto(address+'/webrtc/3/play/');rtc_page.click('#rtc-start')
                    rtc_page.wait_for_function("() => document.querySelector('#rtc-video').readyState >= 2 && document.querySelector('#rtc-video').currentTime > .2",timeout=30000)
                    rtc_page.wait_for_function("() => document.querySelector('#rtc-video').srcObject.getAudioTracks().length === 1",timeout=10000)
                    rtc_page.wait_for_function("async () => {for(const peer of window.__peers){for(const row of (await peer.getStats()).values()){if(row.type==='inbound-rtp'&&row.kind==='audio'&&row.totalAudioEnergy>.001)return true;}}return false;}",timeout=15000)
                    rtc_page.locator('#rtc-audio-toggle').click();assert rtc_page.locator('#rtc-video').evaluate('video=>!video.muted&&video.volume>0')
                    rtc_page.locator('#rtc-audio-toggle').click();assert rtc_page.locator('#rtc-video').evaluate('video=>video.muted')
                    if args.screenshots_dir:
                        args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.bring_to_front();page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(args.screenshots_dir/('dashboard-ton-'+core.APP_VERSION+'.png')),full_page=True)
                    # WebRTC may first decode the valid switching image while
                    # the shared encoder warms up. Require the actual playlist
                    # picture to arrive, rather than sampling that first frame.
                    rtc_page.wait_for_function("() => {const video=document.querySelector('#rtc-video');const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const c=canvas.getContext('2d');c.drawImage(video,0,0,1,1);const p=c.getImageData(0,0,1,1).data;return p[1]>80&&p[1]>p[2]+50&&p[2]<100;}",timeout=25000)
                    rtc_page.close()
                    core.mtx('config/global/patch',{'webrtcAdditionalHosts':['203.0.113.1']})
                    failed=page.context.new_page();failed.goto(address+'/webrtc/3/play/');failed.click('#rtc-start')
                    failed.wait_for_function("() => document.querySelector('#rtc-status').textContent.includes('Medienverbindung ist nicht erreichbar') || document.querySelector('#rtc-status').textContent.includes('Keine Medienverbindung zum Server')",timeout=25000)
                    assert not failed.locator('#rtc-start').is_disabled();failed.close();core.mtx('config/global/patch',{'webrtcAdditionalHosts':['127.0.0.1']})
                    clock[0]=datetime(2026,11,2,13,30,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
                    print('PASS: uploaded/converted playlist has audible audio at both outputs and decoded H264/Opus audio in browser WebRTC.',flush=True)
                    page.goto(address+'/#playlists');page.locator('#playlist-create [name=name]').fill('Massen-Auswahl');page.locator('#playlist-create button').click();page.wait_for_selector('#playlist-editor:not([hidden])');until(lambda:page.locator('#playlist-bulk-target option').count()>1)
                    page.goto(address+'/#media');page.locator('.media-playlist-transfer summary').click()
                    for ident in videos:page.locator('[data-playlist-video="'+str(ident)+'"]').check()
                    page.locator('#playlist-bulk-add').click();assert page.locator('#playlist-items li').count()==3
                    page.locator('#playlist-edit [name=name]').fill('Umbenannte Auswahl');page.locator('#playlist-edit button.primary').click();until(lambda:core.rows("SELECT id FROM playlists WHERE name='Umbenannte Auswahl'"))
                    if args.screenshots_dir:page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(args.screenshots_dir/('playlists-'+core.APP_VERSION+'.png')),full_page=True)
                    page.wait_for_function('() => !busy');page.locator('#playlist-delete').click();until(lambda:not core.rows("SELECT id FROM playlists WHERE name='Umbenannte Auswahl'"))
                    page.goto(address+'/#planner');page.wait_for_selector('#planner-timeline .timeline-bar');assert page.locator('#planner-form [name=playlist_id] option').count()>=2;assert page.locator('#planner-form [name=target]').count()>=2;assert page.locator('#planner-list .planner-card').count()==1
                    page.locator('#planner-list button.secondary').click();assert page.locator('#planner-form [name=title]').input_value()=='Mo & Mi: Stream oder Wiederholung'
                    if args.screenshots_dir:args.screenshots_dir.mkdir(parents=True,exist_ok=True);page.screenshot(path=str(args.screenshots_dir/('planer-'+core.APP_VERSION+'.png')),full_page=True)
                    page.goto(address+'/#settings-appearance');page.locator('#studio-preferences-form [name=switch_text]').fill('Switching im Studio');page.locator('#studio-preferences-form [name=replay_label]').fill('Wiederholung aus dem Archiv');page.locator('#studio-preferences-form [name=replay_corner]').select_option('bottom-right');page.wait_for_function('() => !busy');page.locator('#studio-preferences-form button').click();until(lambda:core.rows('SELECT switch_text FROM users WHERE id=?',(uid,))[0]['switch_text']=='Switching im Studio',timeout=30)
                    page.goto(address+'/#expert');page.locator('#expert-toggle').check() if page.locator('#expert-toggle').count() else None
                    # Restore expert preference through the same CSRF-protected route, then
                    # prove that normal logout/login brings it back.
                    page.evaluate("async()=>{const csrf=document.querySelector('meta[name=csrf-token]').content;await fetch('/api/expert-mode',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({enabled:true})});}")
                    page.wait_for_function('() => !busy');page.locator('#logout').click();page.wait_for_url(address+'/login');page.locator('[name=username]').fill('studio');page.locator('[name=password]').fill('Studio-Smoke-Fixture-Password-123');page.locator('button[type=submit]').click();page.wait_for_url(address+'/');assert page.locator('html').get_attribute('data-expert')=='true'
                    page.goto(address+'/#expert-playlists');page.wait_for_selector('#playlist-timeline .timeline-bar');page.locator('#playlist-timeline .timeline-toolbar').get_by_text('Mo',exact=True).click();assert page.locator('#playlist-timeline .timeline-bar').first.bounding_box()['width']>50
                    if args.screenshots_dir:page.screenshot(path=str(args.screenshots_dir/('playlist-scheduler-'+core.APP_VERSION+'.png')),full_page=True)
                    for name in ('planner','media','playlists','settings-appearance','administration','expert-playlists'):
                        page.set_viewport_size({'width':390,'height':844});page.goto(address+'/#'+name);page.wait_for_timeout(350);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),name
                    assert not errors,errors;browser.close()
                assert yaml.safe_load(config.read_text())['paths']['foreign']=={'source':'publisher'}
                print('PASS: one shared Source-2 playlist encoder, real replay overlay, planned output start without login/live input, Source 1/2 takeover, resume, continuous decodable recording, schedule end, actual FTP-file conversion, bulk selection, planner/scheduler browser UI, persistent expert preference and mobile layout.')
        except Exception:
            media_log=base/'media.log'
            if media_log.exists():print(media_log.read_text(errors='replace')[-4500:])
            for log in (base/'data').glob('*.log'):print(log.name,log.read_text(errors='replace')[-2500:])
            raise
        finally:
            clock_patch.stop()
            if server:server.shutdown()
            if core:
                for directory,dirs,files in os.walk(core.DATA/'ftp'):
                    Path(directory).chmod(0o700)
                core.ENGINE.running=False
                if core.ENGINE.thread:core.ENGINE.thread.join(timeout=20)
                core.JOBS.shutdown(wait=True)
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
