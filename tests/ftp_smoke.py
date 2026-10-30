"""Isolated real Pure-FTPd FTPS transfer, chroot, credential rotation and conversion.
Run as root in a disposable local test environment; no system services are installed.
"""
import argparse
import ftplib
import io
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch
import yaml
from media_smoke import port, until


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('pure-ftpd','pure-authd','ffmpeg','ffprobe'):parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--uid',type=int,default=1000);parser.add_argument('--gid',type=int,default=1000)
    args=parser.parse_args();processes=[];core=None
    if os.geteuid()!=0:raise RuntimeError('This isolated FTP daemon test requires root for chroot and UID changes.')
    with tempfile.TemporaryDirectory(prefix='streamdesk-ftps-test-',dir='/tmp') as directory:
        base=Path(directory);base.chmod(0o755);(base/'bin').mkdir()
        for name in ('ffmpeg','ffprobe'):(base/'bin'/name).symlink_to(getattr(args,name).resolve())
        config=base/'media.yml';config.write_text(yaml.safe_dump({'authMethod':'internal','authInternalUsers':[],'paths':{'foreign':{'source':'publisher'}}}))
        clip=base/'fixture.mp4';subprocess.run([str(args.ffmpeg),'-v','error','-f','lavfi','-i','color=c=green:s=320x180:r=30','-t','2','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(clip)],check=True,capture_output=True)
        os.environ.update(STREAMDESK_ENGINE='0',STREAMDESK_DATA=str(base/'data'),STREAMDESK_DEFAULT_CLIP=str(clip),STREAMDESK_FTP_ENABLED='1',STREAMDESK_FTP_UID=str(args.uid),STREAMDESK_FTP_GID=str(args.gid),MEDIAMTX_CONFIG=str(config),PATH=str(base/'bin')+os.pathsep+os.environ['PATH'])
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import app as core
        with patch.object(core.threading,'Thread'):uid=core.add_user('ftpstudio','FTPS-App-Fixture-Password-123',admin=True)
        client=core.app.test_client();headers={'X-CSRF-Token':'ftp'}
        signer=patch('itsdangerous.TimestampSigner.get_timestamp',return_value=int(time.time()));signer.start()
        with client.session_transaction() as session:session.update(uid=uid,version=1,csrf='ftp')
        folder=client.post('/api/playlist-folders',json={'name':'Web Uploads','parent_id':None},headers=headers).json['id']
        nested=client.post('/api/playlist-folders',json={'name':'Unterordner','parent_id':folder},headers=headers).json['id']
        response=client.post('/api/playlists/upload',data={'video':(io.BytesIO(clip.read_bytes()),'Web Video.mp4'),'folder_id':str(nested)},headers=headers)
        assert response.status_code==200,response.json
        until(lambda:core.rows("SELECT * FROM videos WHERE user_id=? AND name='Web Video.mp4'",(uid,)),timeout=35)
        response=client.post('/api/admin/users/'+str(uid)+'/ftp',json={'enabled':True,'password':'FTPS-Fixture-Password-123'},headers=headers);assert response.status_code==200,response.json
        account=response.json['username'];home=core.DATA/'ftp'/str(uid)
        for root,dirs,files in os.walk(core.DATA):
            os.chown(root,args.uid,args.gid)
            for name in files:os.chown(Path(root)/name,args.uid,args.gid)
        wrapper=base/'authenticate';wrapper.write_text('#!/bin/sh\nexec '+sys.executable+' '+str(Path(core.__file__).with_name('ftp_auth.py'))+'\n');wrapper.chmod(0o755)
        key=base/'key.pem';certificate=base/'cert.pem';pem=base/'tls.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=localhost','-keyout',str(key),'-out',str(certificate)],check=True,capture_output=True);pem.write_text(certificate.read_text()+key.read_text());pem.chmod(0o600)
        auth_socket=base/'auth.sock';transferlog=base/'transfers.log';transferlog.touch(mode=0o640);os.chown(transferlog,0,args.gid);os.environ['STREAMDESK_FTP_LOG']=str(transferlog)
        listener=port();context=ssl._create_unverified_context()
        try:
            authlog=(base/'auth.log').open('wb');processes.append(subprocess.Popen([str(args.pure_authd),'-u',str(args.uid),'-g',str(args.gid),'-p',str(base/'auth.pid'),'-s',str(auth_socket),'-r',str(wrapper)],stdout=authlog,stderr=subprocess.STDOUT))
            until(auth_socket.exists,timeout=10)
            serverlog=(base/'ftp.log').open('wb');processes.append(subprocess.Popen([str(args.pure_ftpd),'-A','-E','-H','-R','-r','-0','-Y','3','-U','077:077','-c','10','-u','1','-S','127.0.0.1,'+str(listener),'-l','extauth:'+str(auth_socket),'-2',str(pem),'-O','stats:'+str(transferlog)],stdout=serverlog,stderr=subprocess.STDOUT))
            def connected():
                try:
                    with socket.create_connection(('127.0.0.1',listener),timeout=1):return True
                except OSError:return False
            until(connected,timeout=10)
            plain=ftplib.FTP();plain.connect('127.0.0.1',listener,timeout=10)
            try:
                try:plain.login(account,'FTPS-Fixture-Password-123');raise AssertionError('Plaintext login unexpectedly accepted')
                except (ftplib.error_perm,ftplib.error_temp):pass
            finally:plain.close()
            def login(password):
                ftp=ftplib.FTP_TLS(context=context);ftp.connect('127.0.0.1',listener,timeout=12);ftp.login(account,password);ftp.prot_p();return ftp
            ftp=login('FTPS-Fixture-Password-123');assert ftp.pwd()=='/'
            try:ftp.cwd('/etc');raise AssertionError('FTP escaped its tenant root')
            except (ftplib.error_perm,ftplib.error_temp):pass
            info=client.get('/api/ftp').json;library=info['library_path']
            assert library.lstrip('/') in ftp.nlst()
            ftp.cwd(library+'/Web Uploads/Unterordner');assert 'Web Video.mp4' in ftp.nlst()
            received=io.BytesIO();ftp.retrbinary('RETR Web Video.mp4',received.write)
            web=core.rows("SELECT * FROM videos WHERE user_id=? AND name='Web Video.mp4'",(uid,))[0]
            assert received.getvalue()==Path(web['path']).read_bytes()
            before=set(ftp.nlst());ftp.storbinary('STOR Web Video.mp4',io.BytesIO(clip.read_bytes()))
            renamed=set(ftp.nlst())-before;assert len(renamed)==1,renamed
            duplicate_name=next(iter(renamed));assert core.FTP.video_name(Path(duplicate_name)),duplicate_name
            assert received.getvalue()==Path(web['path']).read_bytes()
            try:ftp.sendcmd('SITE CHMOD 777 Web Video.mp4');raise AssertionError('SITE CHMOD unexpectedly accepted')
            except (ftplib.error_perm,ftplib.error_temp):pass
            ftp.storbinary('STOR Im Unterordner.mp4',io.BytesIO(clip.read_bytes()))
            ftp.mkd('FTP Folgen');ftp.cwd('FTP Folgen');ftp.storbinary('STOR Folge 1.mp4',io.BytesIO(clip.read_bytes()))
            ftp.cwd(library);ftp.storbinary('STOR Direkt in Bibliothek.mp4',io.BytesIO(clip.read_bytes()))
            # Sync must not consume or remove payloads before transfer receipts.
            payload=home/library.lstrip('/')/'Noch im Upload.mp4';payload.write_bytes(b'incomplete-transfer')
            core.write('UPDATE playlist_folders SET name=? WHERE id=?',('Web Archiv',folder));core.FTP.sync_library(core.rows('SELECT * FROM users WHERE id=?',(uid,))[0]);assert payload.read_bytes()==b'incomplete-transfer'
            ftp.cwd('/')
            ftp.mkd('Nachtprogramm');ftp.cwd('Nachtprogramm');ftp.storbinary('STOR Aufnahme.mp4',io.BytesIO(clip.read_bytes()));ftp.quit()
            assert (home/'Nachtprogramm'/'Aufnahme.mp4').is_file()
            until(lambda:transferlog.stat().st_size>0,timeout=8)
            def imported():
                core.FTP.run()
                return len(core.rows("SELECT * FROM videos WHERE user_id=? AND name IN ('Aufnahme.mp4','Direkt in Bibliothek.mp4','Im Unterordner.mp4','Folge 1.mp4')",(uid,)))==4
            until(imported,timeout=80)
            video=core.rows("SELECT * FROM videos WHERE user_id=? AND name='Aufnahme.mp4'",(uid,))[0];assert video['folder_id'];assert not (home/'Nachtprogramm'/'Aufnahme.mp4').exists()
            core.FTP.run()
            assert (home/library.lstrip('/')/'Nachtprogramm'/'Aufnahme.mp4').is_file()
            imported_nested=core.rows("SELECT folder_id FROM videos WHERE user_id=? AND name='Im Unterordner.mp4'",(uid,))[0];assert imported_nested['folder_id']==nested
            parent_id=core.rows("SELECT parent_id FROM playlist_folders WHERE user_id=? AND name='FTP Folgen'",(uid,))[0]['parent_id'];assert parent_id==nested
            assert core.rows("SELECT folder_id FROM videos WHERE user_id=? AND name='Direkt in Bibliothek.mp4'",(uid,))[0]['folder_id'] is None
            assert not core.rows("SELECT id FROM playlist_folders WHERE user_id=? AND name=?",(uid,library.lstrip('/')))
            assert payload.read_bytes()==b'incomplete-transfer'
            assert received.getvalue()==Path(web['path']).read_bytes()
            response=client.post('/api/ftp/password',json={'password':'FTPS-Changed-Fixture-123'},headers=headers);assert response.status_code==200
            for root,dirs,files in os.walk(core.DATA):
                os.chown(root,args.uid,args.gid)
                for name in files:os.chown(Path(root)/name,args.uid,args.gid)
            try:login('FTPS-Fixture-Password-123');raise AssertionError('Old FTP password still accepted')
            except (ftplib.error_perm,ftplib.error_temp):pass
            ftp=login('FTPS-Changed-Fixture-123');ftp.quit()
            response=client.post('/api/admin/users/'+str(uid)+'/ftp',json={'enabled':False},headers=headers);assert response.status_code==200
            try:login('FTPS-Changed-Fixture-123');raise AssertionError('Disabled FTP account still accepted')
            except (ftplib.error_perm,ftplib.error_temp):pass
            print('PASS: real Pure-FTPd FTPS-only login, tenant chroot, web-upload video and nested folders visible/downloadable, library/root/nested/new-folder uploads, non-destructive automatic collision renaming, CHMOD rejected, incomplete upload preserved during web-folder rename, automatic H264/AAC conversion, private password rotation and disabled-account rejection.')
        except Exception:
            print('Transfer log size',transferlog.stat().st_size,'Home files',[str(p.relative_to(home)) for p in home.rglob('*')])
            for name in ('auth.log','ftp.log'):
                path=base/name
                if path.exists():print(name,path.read_text(errors='replace')[-3500:])
            raise
        finally:
            signer.stop()
            if core:core.JOBS.shutdown(wait=True)
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
