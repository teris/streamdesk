"""Private upload jobs and measured FFmpeg conversion progress."""
import math
import errno
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import threading
import time
from flask import jsonify, Request


ACTIVE = ('queued', 'checking', 'processing')
DISK_HEADROOM = 350 * 1024 * 1024


def require_space(c, amount=0, excluding=None):
    reserved=sum(value for key,value in c.UPLOAD_RESERVATIONS.items() if key!=excluding)
    if c.shutil.disk_usage(c.DATA).free-reserved < amount+DISK_HEADROOM:
        raise c.Error('Auf dem Server ist zu wenig freier Speicher für Upload oder Umwandlung.',http_status=507)


class StagedVideoUpload:
    """Stream to the media filesystem and promote by rename, without a second copy."""
    def __init__(self,c):
        self.c=c;folder=c.DATA/'uploads';folder.mkdir(mode=0o700,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.web-stage-',dir=folder)
        self.path=Path(name);self.stream=os.fdopen(fd,'w+b')
    def __getattr__(self,name):return getattr(self.stream,name)
    def write(self,data):
        with self.c.LOCK:
            require_space(self.c,len(data))
            try:return self.stream.write(data)
            except OSError as exc:
                if exc.errno==errno.ENOSPC:raise self.c.Error('Der Datenträger ist voll. Der Upload wurde beendet.',http_status=507) from None
                raise
    def promote(self,target):
        try:self.stream.flush()
        except OSError as exc:
            if exc.errno==errno.ENOSPC:raise self.c.Error('Der Datenträger ist voll. Der Upload wurde beendet.',http_status=507) from None
            raise
        self.path.rename(target);self.path=None
    def close(self):
        try:
            try:self.stream.close()
            except OSError as exc:
                if exc.errno!=errno.ENOSPC:raise
        finally:
            if self.path:self.path.unlink(missing_ok=True)


def install_upload_request(c):
    class VideoRequest(Request):
        @property
        def is_video_upload(self):return self.method=='POST' and self.path in ('/api/upload','/api/playlists/upload')
        @Request.max_content_length.getter
        def max_content_length(self):return None if self.is_video_upload else super().max_content_length
        def _get_file_stream(self,total_content_length,content_type,filename=None,content_length=None):
            if not self.is_video_upload:return super()._get_file_stream(total_content_length,content_type,filename,content_length)
            streams=self.__dict__.setdefault('_video_streams',[])
            if not streams:
                with c.LOCK:require_space(c,total_content_length or 0)
            stream=StagedVideoUpload(c);streams.append(stream);return stream
        def close(self):
            try:super().close()
            finally:
                for stream in self.__dict__.get('_video_streams',[]):stream.close()
    c.app.request_class=VideoRequest


def migrate(c):
    with c.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS video_uploads(
            id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,filename TEXT NOT NULL,size INTEGER NOT NULL,
            kind TEXT NOT NULL,folder_id INTEGER,state TEXT NOT NULL DEFAULT 'queued',progress REAL NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',video_id INTEGER,created REAL NOT NULL,updated REAL NOT NULL)''')
        if 'upload_id' not in {row['name'] for row in db.execute('PRAGMA table_info(users)')}:
            db.execute("ALTER TABLE users ADD COLUMN upload_id TEXT NOT NULL DEFAULT ''")


class UploadFeatures:
    def __init__(self, c):
        self.c = c
        self.install_routes()

    def public(self, row):
        return {key:row[key] for key in ('id','filename','size','kind','folder_id','state','progress','message','video_id','created','updated')}

    def get(self, user, ident):
        found = self.c.rows('SELECT * FROM video_uploads WHERE id=? AND user_id=?', (ident,user['id']))
        if not found:raise self.c.Error('Upload nicht gefunden.',http_status=404)
        return self.public(found[0])

    def install_routes(self):
        c = self.c
        @c.app.get('/api/uploads')
        @c.login_required
        def upload_jobs(user):
            rows = c.rows('SELECT * FROM video_uploads WHERE user_id=? ORDER BY created DESC LIMIT 50',(user['id'],))
            return jsonify(jobs=[self.public(row) for row in rows],busy=user['upload_state'] in ('queued','processing'))

        @c.app.get('/api/uploads/<ident>')
        @c.login_required
        def upload_job(user,ident):return jsonify(**self.get(user,ident))

    def register(self,user,ident,name,size,kind,folder):
        stamp=time.time()
        self.c.write('''INSERT INTO video_uploads(id,user_id,filename,size,kind,folder_id,created,updated)
                        VALUES (?,?,?,?,?,?,?,?)''',(ident,user['id'],name,size,kind,folder,stamp,stamp))
        # Keep bounded history, including unfinished jobs regardless of their age.
        self.c.write("DELETE FROM video_uploads WHERE user_id=? AND state IN ('ready','error') AND id NOT IN (SELECT id FROM video_uploads WHERE user_id=? ORDER BY created DESC LIMIT 100)",(user['id'],user['id']))

    def update(self,ident,uid,state,progress=0,message='',video_id=None,connection=None):
        if not ident:return
        progress = float(progress)
        if not math.isfinite(progress):progress=0
        progress=max(0,min(100 if state=='ready' else 99,progress))
        sql='''UPDATE video_uploads SET state=?,progress=MAX(progress,?),message=?,video_id=COALESCE(?,video_id),updated=? WHERE id=? AND user_id=?'''
        args=(state,progress,str(message)[:500],video_id,time.time(),ident,uid)
        if connection is not None:connection.execute(sql,args)
        else:self.c.write(sql,args)

    def summary(self,user):
        found=self.c.rows('SELECT * FROM video_uploads WHERE id=? AND user_id=?',(user.get('upload_id',''),user['id']))
        result={'state':user['upload_state'],'message':user['upload_message'],'progress':None,'job_id':user.get('upload_id','')}
        if found:
            job=self.public(found[0]);result.update(progress=job['progress'],filename=job['filename'],stage=job['state'],video_id=job['video_id'])
        return result

    def recover(self):
        with self.c.db() as connection:
            for row in connection.execute("SELECT id,user_id,kind FROM video_uploads WHERE state IN ('queued','checking','processing')").fetchall():
                message='Umwandlung durch Serverneustart unterbrochen. '+('Unter Medien → FTP-Importe erneut versuchen.' if row['kind']=='ftp' else 'Bitte erneut hochladen.')
                connection.execute("UPDATE users SET upload_state='error',upload_message=? WHERE id=? AND upload_id=?",(message,row['user_id'],row['id']))
                connection.execute("UPDATE video_uploads SET state='error',message=?,updated=? WHERE id=?",(message,time.time(),row['id']))
        # A stopped HTTP upload has no job yet. Remove only our own temporary
        # spool files on startup; retained FTP originals remain available.
        for path in (self.c.DATA/'uploads').glob('.web-stage-*'):
            if path.is_file() and not path.is_symlink():path.unlink(missing_ok=True)

    def encode(self, command, uid, ident, duration, timeout=None):
        """Drain FFmpeg's progress pipe continuously; stderr cannot block the encoder."""
        timed_out=threading.Event()
        disk_full=threading.Event();finished=threading.Event()
        with tempfile.TemporaryFile(mode='w+b',dir=str(self.c.DATA/'tmp')) as errors:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,text=True)
            def expire():
                timed_out.set()
                try:process.kill()
                except ProcessLookupError:pass
            timer=threading.Timer(timeout,expire) if timeout is not None else None
            if timer:timer.daemon=True;timer.start()
            def monitor_disk():
                while not finished.wait(1):
                    if self.c.shutil.disk_usage(self.c.DATA).free<DISK_HEADROOM:
                        disk_full.set()
                        try:process.kill()
                        except ProcessLookupError:pass
                        return
            monitor=threading.Thread(target=monitor_disk,daemon=True);monitor.start()
            last=-1
            try:
                for line in process.stdout:
                    if not line.startswith('out_time_us='):continue
                    try:elapsed=max(0,int(line.split('=',1)[1].strip()))/1_000_000
                    except ValueError:continue
                    progress=min(99,int(elapsed/max(duration,.001)*100))
                    if progress>last:
                        self.update(ident,uid,'processing',progress,'Video wird umgewandelt.')
                        last=progress
                result=process.wait()
            finally:
                finished.set();monitor.join(timeout=2)
                if timer:timer.cancel()
                if process.poll() is None:
                    process.kill();process.wait()
                if process.stdout:process.stdout.close()
            if timed_out.is_set():raise self.c.Error('Die Video-Umwandlung hat das Zeitlimit überschritten.')
            if disk_full.is_set():raise self.c.Error('Zu wenig freier Speicher. Die Umwandlung wurde angehalten.')
            if result:raise self.c.Error('Das Video konnte nicht umgewandelt werden. Bitte eine normale MP4-Datei verwenden.')
