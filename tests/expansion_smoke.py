"""Real protected native playback in fMP4 and MPEG-TS; routing is tested separately.
Temporary data, loopback-only MediaMTX. Run with --mediamtx --ffmpeg --ffprobe.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import yaml
from media_smoke import port,until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for binary in ('mediamtx','ffmpeg','ffprobe'):parser.add_argument('--'+binary,required=True,type=Path)
    args=parser.parse_args();processes=[];core=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-playback-') as temporary:
        base=Path(temporary);(base/'bin').mkdir();(base/'native').mkdir()
        for binary in ('ffmpeg','ffprobe'):(base/'bin'/binary).symlink_to(getattr(args,binary).resolve())
        api,rtsp,playback=port(),port(),port();config=base/'media.yml'
        foreign={'user':'outside','pass':'fixture','ips':[],'permissions':[{'action':'read','path':'foreign'}]}
        config.write_text(yaml.safe_dump({'logLevel':'warn','api':True,'apiAddress':f'127.0.0.1:{api}',
            'rtsp':True,'rtspAddress':f'127.0.0.1:{rtsp}','rtspTransports':['tcp'],'rtmp':False,'srt':False,'hls':False,
            'webrtc':False,'moq':False,'playback':False,'playbackAddress':f'127.0.0.1:{playback}',
            'authMethod':'internal','authInternalUsers':[foreign],'paths':{'foreign':{'source':'publisher'}}}))
        clip=base/'fixture.mp4';clip.write_bytes(b'not-used-by-playback')
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_NATIVE_ROOT=str(base/'native'),
            STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',
            MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        try:
            with patch.object(core.threading,'Thread'):
                uid=core.add_user('alice','Playback-Fixture-Password-123',admin=True);other=core.add_user('bobby','Playback-Fixture-Password-456')
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]
            log=(base/'media.log').open('wb');processes.append(subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT))
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            client=core.app.test_client();headers={'X-CSRF-Token':'playback'}
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='playback',expert_mode=True)
            def post(path,body):
                response=client.post(path,json=body,headers=headers);assert response.status_code==200,(path,response.status_code,response.json);return response.json
            key=post('/api/routing/sources',{'label':'Archive camera','protocol':'srt'})['key'];core.sync_media_runtime()
            post('/api/admin/playback',{'enabled':True,'address':f'127.0.0.1:{playback}'})
            for fmt in ('fmp4','mpegts'):
                post('/api/native-recording',{'source':key,'enabled':True,'format':fmt,'segment':'1m','retention':'1d'})
                process=subprocess.Popen([str(args.ffmpeg),'-v','error','-nostdin','-re','-f','lavfi','-i','testsrc=size=640x360:rate=15',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-c:v','libx264','-preset','ultrafast','-tune','zerolatency',
                    '-pix_fmt','yuv420p','-g','15','-threads','1','-c:a','aac','-f','rtsp','-rtsp_transport','tcp',core.RTSP+user['prefix']+key],
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(process)
                until(lambda:core.mtx('paths/get/'+user['prefix']+key).get('online'));time.sleep(5)
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
                post('/api/native-recording',{'source':key,'enabled':False})
                spans=until(lambda:(client.get('/api/playback/'+key+'/spans').json or {}).get('spans'))
                response=client.get(spans[-1]['url']);assert response.status_code==200
                file=base/(fmt+'.mp4');file.write_bytes(response.data);response.close()
                subprocess.run([str(args.ffmpeg),'-v','error','-i',str(file),'-t','1','-f','null','-'],check=True,capture_output=True)
                public=core.app.test_client();assert public.get(spans[-1]['url']).status_code==401
                with public.session_transaction() as session:session.update(uid=other,version=1,csrf='other',expert_mode=True)
                assert public.get(spans[-1]['url']).status_code==404
                print('PASS:',fmt,'owned playback decoded; anonymous and foreign-tenant requests rejected.',flush=True)
            current=yaml.safe_load(config.read_text());assert current['paths']['foreign']=={'source':'publisher'};assert foreign in current['authInternalUsers']
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
            if sys.exc_info()[0]:print((base/'media.log').read_text()[-4000:] if (base/'media.log').exists() else '')


if __name__=='__main__':main()
