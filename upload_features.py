"""Private upload jobs and measured FFmpeg conversion progress."""
import math
import secrets
import subprocess
import tempfile
import threading
import time
from flask import jsonify


ACTIVE = ('queued', 'checking', 'processing')


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
            connection.execute("UPDATE users SET upload_state='error',upload_message='Umwandlung durch Serverneustart unterbrochen. Bitte erneut hochladen.' WHERE upload_id IN (SELECT id FROM video_uploads WHERE state IN ('queued','checking','processing'))")
            connection.execute("UPDATE video_uploads SET state='error',message='Umwandlung durch Serverneustart unterbrochen. Bitte erneut hochladen.',updated=? WHERE state IN ('queued','checking','processing')",(time.time(),))

    def encode(self, command, uid, ident, duration, timeout):
        """Drain FFmpeg's progress pipe continuously; stderr cannot block the encoder."""
        timed_out=threading.Event()
        with tempfile.TemporaryFile(mode='w+b',dir=str(self.c.DATA/'tmp')) as errors:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=errors,text=True)
            def expire():
                timed_out.set()
                try:process.kill()
                except ProcessLookupError:pass
            timer=threading.Timer(timeout,expire);timer.daemon=True;timer.start()
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
                timer.cancel()
                if process.poll() is None:
                    process.kill();process.wait()
                if process.stdout:process.stdout.close()
            if timed_out.is_set():raise self.c.Error('Die Video-Umwandlung hat das Zeitlimit überschritten.')
            if result:raise self.c.Error('Das Video konnte nicht umgewandelt werden. Bitte eine normale MP4-Datei verwenden.')
