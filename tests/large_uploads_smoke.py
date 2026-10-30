"""Real conversion of sparse 6-GiB MP4 inputs through FTP recovery and web staging.
The payload is a valid short MP4 plus a sparse ISO-BMFF free box; this exercises
64-bit file sizes and real FFmpeg without transferring six GiB over a network.
"""
import argparse
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import yaml
from werkzeug.datastructures import FileStorage,MultiDict
from media_smoke import until


def payload(stream,clip):
    total=6*1024**3;stream.write(clip.read_bytes())
    padding=total-stream.tell();stream.write(struct.pack('>I4sQ',1,b'free',padding));stream.truncate(total);stream.flush()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('ffmpeg','ffprobe'):parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args();core=None
    with tempfile.TemporaryDirectory(prefix='streamdesk-large-import-',dir='/tmp') as directory:
        base=Path(directory);(base/'bin').mkdir()
        for name in ('ffmpeg','ffprobe'):(base/'bin'/name).symlink_to(getattr(args,name).resolve())
        clip=base/'fixture.mp4'
        subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=blue:s=640x360:r=30','-f','lavfi','-i','sine=frequency=880:sample_rate=48000','-t','2','-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip)],capture_output=True,check=True)
        config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{}}))
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),MEDIAMTX_CONFIG=str(config),STREAMDESK_FTP_ENABLED='1',PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):uid=core.add_user('largeimports','Large-Import-Fixture-123',admin=True)
        signer=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));signer.start()
        try:
            user=core.rows('SELECT * FROM users WHERE id=?',(uid,))[0];client=core.app.test_client();headers={'X-CSRF-Token':'large'}
            with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='large')
            folder=client.post('/api/playlist-folders',json={'name':'Große Videos','parent_id':None},headers=headers).json['id']
            account=client.post('/api/admin/users/'+str(uid)+'/ftp',json={'enabled':True,'password':'FTP-Large-Fixture-123'},headers=headers)
            assert account.status_code==200,account.json
            home=core.FTP.root/str(uid);library=home/account.json['library_path'].lstrip('/');source=library/'Große Videos'/'FTP 6 GiB.mp4'
            with source.open('wb') as stream:payload(stream,clip)
            assert source.stat().st_size==6*1024**3 and source.stat().st_blocks*512<1024**2
            ident='legacy-six-gib'
            core.write("INSERT INTO ftp_imports(id,user_id,path,size,state,message,created) VALUES (?,?,?,?,'error',?,?)",(ident,uid,str(source),source.stat().st_size,'Nur MP4-Dateien bis 500 MB können importiert werden.',time.time()))
            def ftp_ready():
                core.FTP.run();return core.rows('SELECT state FROM ftp_imports WHERE id=?',(ident,))[0]['state']=='ready'
            until(ftp_ready,timeout=45)
            first=core.rows("SELECT * FROM videos WHERE user_id=? AND name='FTP 6 GiB.mp4'",(uid,))[0]
            assert first['folder_id']==folder
            assert source.samefile(Path(first['path'])) and source.stat().st_size<1024**2
            assert core.rows('SELECT size FROM video_uploads WHERE user_id=? ORDER BY created DESC LIMIT 1',(uid,))[0]['size']==6*1024**3
            stage=core.StagedVideoUpload(core);payload(stage,clip);inode=os.fstat(stage.fileno()).st_ino
            promoted=[];original_promote=stage.promote
            def promote(target):original_promote(target);promoted.append(target.stat().st_ino)
            with core.app.test_request_context('/api/playlists/upload',method='POST'):
                core.request.__dict__['files']=MultiDict({'video':FileStorage(stream=stage,filename='Web 6 GiB.mp4')})
                core.request.__dict__['form']=MultiDict({'upload_id':'large-web-fixture-123456789'})
                with patch.object(FileStorage,'save',side_effect=AssertionError('Unnecessary full-file copy')),patch.object(stage,'promote',side_effect=promote):
                    response=core.accept_upload(user,folder_id=folder,kind='playlist')
                assert response.json['ok']
                assert promoted==[inode]
            stage.close()
            until(lambda:core.rows("SELECT * FROM videos WHERE user_id=? AND name='Web 6 GiB.mp4'",(uid,)),timeout=45)
            second=core.rows("SELECT * FROM videos WHERE user_id=? AND name='Web 6 GiB.mp4'",(uid,))[0];assert second['folder_id']==folder
            for video in (first,second):
                subprocess.run([str(args.ffmpeg),'-v','error','-i',video['path'],'-f','null','-'],capture_output=True,check=True,timeout=15)
            playlist=client.post('/api/playlists',json={'name':'Große Dateien','items':[first['id'],second['id']]},headers=headers)
            assert playlist.status_code==200,playlist.json
            assert len(json.loads(core.rows('SELECT items FROM playlists WHERE id=?',(playlist.json['id'],))[0]['items']))==2
            assert not list((core.DATA/'uploads').glob('*.mp4'))
            print('PASS: sparse 6-GiB MP4 inputs accepted, old FTP size error recovered without re-upload, web staging promoted without a copy, both converted by real FFmpeg to decodable H264/AAC in their owned folder and usable in a playlist.')
        finally:
            signer.stop()
            if core:
                core.JOBS.shutdown(wait=True)
                for directory,dirs,files in os.walk(core.DATA/'ftp'):Path(directory).chmod(0o700)


if __name__=='__main__':main()
