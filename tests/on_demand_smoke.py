"""Real on-demand RTSP pull activation and idle shutdown, on temporary loopback ports."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch
import yaml
from media_smoke import port, until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx',required=True,type=Path);parser.add_argument('--ffmpeg',required=True,type=Path)
    args=parser.parse_args();processes=[];core=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-demand-') as temporary:
        base=Path(temporary);(base/'bin').mkdir();(base/'bin'/'ffmpeg').symlink_to(args.ffmpeg.resolve())
        api,rtsp=port(),port();config=base/'media.yml'
        config.write_text(yaml.safe_dump({'logLevel':'warn','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,
            'hls':False,'webrtc':False,'moq':False,'authMethod':'internal','paths':{'camera-feed':{'source':'publisher'}}}))
        clip=base/'offline.mp4'
        subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=green:s=640x360:r=15',
            '-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2','-c:v','libx264','-preset','ultrafast','-g','15',
            '-pix_fmt','yuv420p','-c:a','aac','-threads','1',str(clip)],check=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),
            MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',
            PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        try:
            with patch.object(core.threading,'Thread'):uid=core.add_user('alice','Demand-Fixture-Password-123')
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            client=core.app.test_client()
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='demand',expert_mode=True)
            headers={'X-CSRF-Token':'demand'}
            with (base/'media.log').open('wb') as log:
                processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('info'));core.sync_media_runtime()
            with patch.object(core,'validate_output',side_effect=lambda value:value):
                response=client.post('/api/routing/sources',headers=headers,json={'label':'Demand camera','protocol':'rtsp',
                    'url':core.RTSP+'camera-feed','source_on_demand':True})
            assert response.status_code==200,response.json
            source=response.json['key'];core.MODEL.save_route(user,'custom',[source]);core.reconcile();core.sync_media_runtime()
            process=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i','color=c=blue:s=640x360:r=15',
                '-c:v','libx264','-preset','ultrafast','-g','15',
                '-threads','1','-f','rtsp','-rtsp_transport','tcp',core.RTSP+'camera-feed'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            processes.append(process);until(lambda:core.mtx('paths/get/camera-feed').get('online'))
            assert not core.mtx('paths/get/'+user['prefix']+source).get('available')
            core.ENGINE.thread=threading.Thread(target=core.ENGINE.run,daemon=True);core.ENGINE.thread.start()
            program=core.MODEL.output_program(user,'custom')
            consumer=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-rtsp_transport','tcp','-i',core.RTSP+program['path'],
                '-c','copy','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(consumer)
            def selected():
                return next((row.get('selected_source') for row in core.ENGINE.snapshot.get(uid,{}).get('programs',[]) if row['id']==program['id']),None)
            until(lambda:selected()==source,timeout=30)
            def blue():
                image=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','5000000','-i',core.RTSP+program['path'],
                    '-frames:v','1','-vf','scale=1:1,format=rgb24','-an','-f','rawvideo','pipe:1'],capture_output=True,check=True,timeout=10).stdout
                return len(image)>=3 and image[2]>180 and image[0]<60 and image[1]<60
            until(blue,timeout=30)
            subprocess.run([str(args.ffmpeg),'-v','error','-nostdin','-rtsp_transport','tcp','-timeout','5000000',
                '-i',core.RTSP+program['path'],'-t','1','-map','0:a:0','-f','null','-'],check=True,capture_output=True,timeout=15)
            consumer.terminate()
            try:consumer.wait(timeout=2)
            except subprocess.TimeoutExpired:consumer.kill();consumer.wait()
            until(lambda:not core.ENGINE.source_probes,timeout=20)
            until(lambda:not core.mtx('paths/get/'+user['prefix']+source).get('available'),timeout=20)
            print('PASS: a program consumer activates a video-only on-demand pull, receives decoded video and continuous audio; idle programs release the probe and upstream source.')
        finally:
            if core:
                core.ENGINE.running=False
                if core.ENGINE.thread:core.ENGINE.thread.join(timeout=6)
                for key in list(core.ENGINE.source_probes):core.ENGINE.stop_source_probe(key)
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
            if sys.exc_info()[0] and (base/'media.log').exists():print((base/'media.log').read_text()[-3000:])


if __name__=='__main__':main()
