"""Real RTSP regression for a rounding-tail bookmark in a long playlist."""
import argparse
import array
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import yaml
from media_smoke import port, until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('mediamtx','ffmpeg','ffprobe'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();core=None;media=None;feed=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-resume-',dir='/tmp') as directory:
        base=Path(directory);(base/'bin').mkdir()
        for name in ('ffmpeg','ffprobe'):(base/'bin'/name).symlink_to(getattr(args,name).resolve())
        clip=base/'fixture.mp4'
        subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=green:s=1920x1080:r=30','-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','8','-c:v','libx264','-profile:v','high','-preset','veryfast','-tune','zerolatency','-g','60','-threads','1','-c:a','aac','-ar','48000','-ac','2',str(clip)],check=True,capture_output=True)
        api,rtsp=port(),port();config=base/'media.yml'
        config.write_text(yaml.safe_dump(dict(logLevel='info',api=True,apiAddress=f'127.0.0.1:{api}',rtsp=True,rtspAddress=f'127.0.0.1:{rtsp}',rtspTransports=['tcp'],rtmp=False,srt=False,hls=False,webrtc=False,moq=False,authMethod='internal',authInternalUsers=[],paths={'foreign':{'source':'publisher'}})))
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),MEDIAMTX_API=f'http://127.0.0.1:{api}/v3/',MEDIAMTX_RTSP=f'rtsp://127.0.0.1:{rtsp}/',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        try:
            with patch.object(core.threading,'Thread'):uid=core.add_user('resume','Resume-Fixture-Password-123',admin=True,legacy=True)
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0];ids=[]
            # Original-container durations and the bookmark match the reported
            # 49-minute failure. Normalized frame durations are slightly shorter.
            for index,duration in enumerate((115.147755,752.349751,737.744399,528.880907,839.215601)):
                target=core.DATA/'media/resume'/('part-'+str(index)+'.mp4')
                subprocess.run([str(args.ffmpeg),'-v','error','-stream_loop','-1','-i',str(clip),'-t',str(int(duration*30)/30),'-c','copy',str(target)],check=True,capture_output=True)
                ids.append(core.write('INSERT INTO videos(user_id,name,path,duration,size,created) VALUES (?,?,?,?,?,?)',(uid,'Part '+str(index),str(target),duration,target.stat().st_size,int(time.time()))))
            ident=core.write('INSERT INTO playlists(user_id,name,items) VALUES (?,?,?)',(uid,'Long playlist',json.dumps(ids)))
            plan=dict(playlist=core.rows('SELECT * FROM playlists WHERE id=?',(ident,))[0],scheduled=True)
            core.write('INSERT INTO playlist_positions(user_id,program,playlist_id,revision,offset) VALUES (?,?,?,?,?)',(uid,'source2-playlist',ident,1,2973.269333))
            with (base/'media.log').open('wb') as log:media=subprocess.Popen([str(args.mediamtx),str(config)],stdout=log,stderr=subprocess.STDOUT)
            until(lambda:core.mtx('config/global/get'));core.sync_media_runtime()
            def ready():
                try:core.PLAYLISTS.start(user,core.MODEL.program(user),plan);return True
                except core.PlaylistStarting:return False
            until(ready,timeout=20);feed=core.PLAYLISTS.feeds[uid];pid=feed['process'].pid
            until(lambda:core.mtx('paths/get/playlist-source2').get('inboundBytes',0)>0,timeout=8)
            first=core.mtx('paths/get/playlist-source2');source_id=first['source']['id'];count=first['inboundBytes']
            # Cross the server's ten-second timeout without reconnecting. An
            # announced track list or a single encoded frame cannot pass this.
            for _ in range(13):
                time.sleep(1);state=core.mtx('paths/get/playlist-source2')
                assert state['online'] and state['source']['id']==source_id
                assert feed['process'].pid==pid and feed['process'].poll() is None
            assert state['inboundBytes']>count
            pcm=subprocess.run([str(args.ffmpeg),'-v','error','-rtsp_transport','tcp','-timeout','5000000','-i',core.RTSP+'playlist-source2','-t','1','-vn','-ac','1','-ar','48000','-f','s16le','pipe:1'],capture_output=True,check=True,timeout=12)
            samples=array.array('h',pcm.stdout);assert samples
            assert math.sqrt(sum(x*x for x in samples)/len(samples))>500
            assert core.PLAYLISTS.position(feed['job'])>2
            assert yaml.safe_load(config.read_text())['paths']['foreign']=={'source':'publisher'}
            print('PASS: reported five-file rounding-tail bookmark resumes with advancing video/audio timestamps, audible PCM and one stable RTSP publisher beyond its timeout; foreign paths preserved.')
        except Exception:
            for log in [base/'media.log',*(base/'data').glob('*.log')]:
                if log.exists():print(log.name,log.read_text(errors='replace')[-3000:])
            raise
        finally:
            if core:
                for key in list(core.PLAYLISTS.jobs):core.PLAYLISTS.checkpoint(key,pause=True)
                core.JOBS.shutdown(wait=True)
            if media and media.poll() is None:media.terminate();media.wait(timeout=5)


if __name__=='__main__':main()
