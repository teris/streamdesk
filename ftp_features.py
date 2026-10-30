"""Tenant FTP credentials and post-transfer imports through the regular video pipeline."""
import fcntl
import hashlib
import errno
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from flask import jsonify, request
from upload_features import require_space

TABLES=('ftp_accounts','ftp_imports','ftp_library_views')

def migrate(c):
    with c.db() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS ftp_accounts(user_id INTEGER PRIMARY KEY,username TEXT NOT NULL UNIQUE,password TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS ftp_imports(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'queued',message TEXT NOT NULL DEFAULT '',upload_id TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS ftp_library_views(user_id INTEGER PRIMARY KEY,name TEXT NOT NULL,error TEXT NOT NULL DEFAULT '',entries TEXT NOT NULL DEFAULT '{}',directories TEXT NOT NULL DEFAULT '{}');
          CREATE TABLE IF NOT EXISTS ftp_log_state(id INTEGER PRIMARY KEY CHECK(id=1),inode INTEGER NOT NULL,offset INTEGER NOT NULL);''')

        columns={row['name'] for row in db.execute('PRAGMA table_info(ftp_library_views)')}
        for name in ('entries','directories'):
            if name not in columns:db.execute("ALTER TABLE ftp_library_views ADD COLUMN "+name+" TEXT NOT NULL DEFAULT '{}'")
        columns={row['name'] for row in db.execute('PRAGMA table_info(ftp_imports)')}
        if 'staging' not in columns:db.execute("ALTER TABLE ftp_imports ADD COLUMN staging TEXT NOT NULL DEFAULT ''")
        if 'folder_id' not in columns:db.execute('ALTER TABLE ftp_imports ADD COLUMN folder_id INTEGER')

class FTPFeatures:
    def __init__(self,c):
        self.c=c;self.worker=None;self.last_tick=0;self.library_versions={};self.library_lock=c.threading.RLock();self.root=c.DATA/'ftp';self.install_routes()
    def configured(self):return os.getenv('STREAMDESK_FTP_ENABLED','0')=='1'
    def connection(self,user):
        rows=self.c.rows('SELECT username,enabled FROM ftp_accounts WHERE user_id=?',(user['id'],))
        account=dict(rows[0],enabled=bool(rows[0]['enabled'])) if rows else None
        views=self.c.rows('SELECT name,error FROM ftp_library_views WHERE user_id=?',(user['id'],))
        return dict(library_path='/'+views[0]['name'] if views else '/Bibliothek',library_error=views[0]['error'] if views else '',configured=self.configured(),account=account,host=self.c.HOST.strip('[]'),port=int(os.getenv('STREAMDESK_FTP_PORT','2121')),tls=True,
                    protocol='FTP mit explizitem TLS',passive=True,passive_ports=os.getenv('STREAMDESK_FTP_PASSIVE','30000:30049'),
                    user=dict(id=user['id'],username=user['username'],active=bool(user['active'])))
    def public(self,user):
        imports=[]
        for row in self.c.rows('SELECT * FROM ftp_imports WHERE user_id=? ORDER BY created DESC LIMIT 30',(user['id'],)):
            retryable=False
            if row['state']=='error':
                try:self.source(row);retryable=True
                except (self.c.Error,OSError):pass
            jobs=self.c.rows('SELECT progress,video_id FROM video_uploads WHERE id=? AND user_id=?',(row['upload_id'],user['id'])) if row['upload_id'] else []
            imports.append({**{key:row[key] for key in ('id','state','message','upload_id','created','size','folder_id')},'filename':Path(row['path']).name,'retryable':retryable,'retained':bool(row['staging']),'progress':jobs[0]['progress'] if jobs else None,'video_id':jobs[0]['video_id'] if jobs else None})
        return dict(**self.connection(user),imports=imports)
    def install_routes(self):
        c=self.c
        @c.app.get('/api/ftp')
        @c.login_required
        def ftp(user):return jsonify(**self.public(user))
        @c.app.post('/api/ftp/imports/<ident>/retry')
        @c.login_required
        def retry_import(user,ident):
            c.SERVICES.require('playlists')
            with c.LOCK:
                account=c.rows('SELECT enabled FROM ftp_accounts WHERE user_id=?',(user['id'],))
                if not self.configured() or not account or not account[0]['enabled']:raise c.Error('Der FTP-Zugang ist nicht freigegeben.',http_status=403)
                found=c.rows('SELECT * FROM ftp_imports WHERE id=? AND user_id=?',(ident,user['id']))
                if not found:raise c.Error('FTP-Import nicht gefunden.',http_status=404)
                row=found[0]
                if row['state'] in ('queued','processing'):return jsonify(ok=True)
                if row['state']!='error':raise c.Error('Dieser FTP-Import ist bereits abgeschlossen.',http_status=409)
                self.source(row)
                c.write("UPDATE ftp_imports SET state='queued',message='Import wird erneut versucht.' WHERE id=?",(ident,))
            return jsonify(ok=True)
        @c.app.delete('/api/ftp/imports/<ident>/source')
        @c.login_required
        def discard_import(user,ident):
            with c.LOCK:
                found=c.rows('SELECT * FROM ftp_imports WHERE id=? AND user_id=?',(ident,user['id']))
                if not found:raise c.Error('FTP-Import nicht gefunden.',http_status=404)
                row=found[0]
                if row['state']!='error' or not row['staging']:raise c.Error('Nur zurückbehaltene Quelldateien fehlgeschlagener Importe können hier gelöscht werden.',http_status=409)
                self.source(row).unlink()
                c.write("UPDATE ftp_imports SET staging='',message='Die zurückbehaltene Quelldatei wurde entfernt.' WHERE id=?",(ident,))
            return jsonify(ok=True)
        @c.app.post('/api/ftp/password',endpoint='ftp_password')
        @c.login_required
        def password(user):
            b=c.FEATURES.body();secret=self.password(b.get('password'))
            with c.LOCK:
                if not c.rows('SELECT 1 FROM ftp_accounts WHERE user_id=?',(user['id'],)):raise c.Error('Bitte die Administration um einen FTP-Zugang bitten.',http_status=404)
                c.write('UPDATE ftp_accounts SET password=? WHERE user_id=?',(c.generate_password_hash(secret),user['id']))
            return jsonify(ok=True)
        @c.app.route('/api/admin/users/<int:uid>/ftp',methods=['GET','POST','DELETE'])
        @c.login_required
        def admin_ftp(user,uid):
            if not user['admin']:raise c.Error('Nur Administratoren dürfen FTP-Zugänge verwalten.',http_status=403)
            found=c.rows("SELECT * FROM users WHERE id=? AND role!='moderator'",(uid,))
            if not found:raise c.Error('Benutzer nicht gefunden.',http_status=404)
            if request.method=='GET':return jsonify(**self.connection(found[0]))
            if not self.configured():raise c.Error('FTP muss zuerst mit dem Installer eingerichtet werden. Das Update mit --enable-ftp ausführen.',http_status=409)
            if request.method=='DELETE':
                c.write('UPDATE ftp_accounts SET enabled=0 WHERE user_id=?',(uid,));return jsonify(ok=True)
            b=c.FEATURES.body();enabled=c.FEATURES.boolean(b,'enabled');previous=c.rows('SELECT * FROM ftp_accounts WHERE user_id=?',(uid,))
            secret=b.get('password');hashed=c.generate_password_hash(self.password(secret)) if secret else previous[0]['password'] if previous else None
            if not hashed:raise c.Error('Bitte ein FTP-Passwort festlegen.')
            with c.LOCK:
                self.root.mkdir(mode=0o700,exist_ok=True)
                home=self.root/str(uid)
                if home.is_symlink() or self.root.is_symlink():raise c.Error('Ungültiger FTP-Speicherordner.')
                home.mkdir(mode=0o700,exist_ok=True)
                c.write('INSERT INTO ftp_accounts(user_id,username,password,enabled) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET password=excluded.password,enabled=excluded.enabled',(uid,'sd_'+c.NAMESPACE+'_'+str(uid),hashed,int(enabled)))
            self.sync_library(found[0])
            return jsonify(ok=True,username='sd_'+c.NAMESPACE+'_'+str(uid),**self.connection(found[0]))
    def sync_library(self,user):
        with self.library_lock:self._sync_library(user)
    @staticmethod
    def fingerprint(path):
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode):return None
        return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]
    @staticmethod
    def mapping(value):
        try:result=json.loads(value)
        except (TypeError,ValueError):return {}
        return result if isinstance(result,dict) else {}
    def _sync_library(self,user):
        """Writable folders contain read-only video aliases and completed uploads.

        Only recorded aliases may be removed or replaced. Unknown files, FTP
        temporary files and nonempty incoming folders must survive every sync.
        """
        c=self.c;uid=user['id'];home=self.root/str(uid)
        revision=c.rows('SELECT revision FROM library_revisions WHERE user_id=?',(uid,))
        revision=revision[0]['revision'] if revision else 0
        if not home.is_dir() or any(p.is_symlink() for p in [home,*home.parents]):return
        views=c.rows('SELECT * FROM ftp_library_views WHERE user_id=?',(uid,))
        if views:view=views[0];name=view['name']
        else:
            name='Bibliothek';suffix=1
            while (home/name).exists() or (home/name).is_symlink():
                suffix+=1;name='Bibliothek (StreamDesk '+str(suffix)+')'
            c.write('INSERT INTO ftp_library_views(user_id,name) VALUES (?,?)',(uid,name))
            view=dict(entries='{}',directories='{}')
        root=home/name
        if root.is_symlink():return
        cache=self.library_versions.get(uid)
        if isinstance(cache,dict) and cache['revision']==revision:
            try:
                if all((root/relative).is_dir() and not (root/relative).is_symlink() and (root/relative).stat().st_mtime_ns==stamp for relative,stamp in cache['directories'].items()):return
            except OSError:pass
        previous=self.mapping(view['entries']);old_dirs=self.mapping(view['directories'])
        folders=c.rows('SELECT id,name,parent_id FROM playlist_folders WHERE user_id=? ORDER BY id',(uid,))
        videos=c.rows('SELECT id,name,path,rendered,folder_id FROM videos WHERE user_id=? ORDER BY id',(uid,))
        by_id={row['id']:row for row in folders};paths={None:Path('.')};used={};expected={};files={};seen_dirs=set();sources={};source_marks=set()
        private=c.DATA/'media'/user['username']
        for row in videos:
            source=Path(row['rendered'] or row['path'])
            if not source.is_file() or any(p.is_symlink() for p in [source,*source.parents]) or not source.resolve().is_relative_to(private.resolve()):continue
            try:mark=self.fingerprint(source)
            except OSError:continue
            if mark is not None:sources[row['id']]=source;source_marks.add(tuple(mark))
        try:
            root.mkdir(mode=0o700,exist_ok=True)
            for current,dirs,names in os.walk(root,followlinks=False):
                base=Path(current);base.chmod(0o700);seen_dirs.add(base.relative_to(root))
                # Never follow a client-supplied link, including during cleanup.
                for child in dirs:
                    if (base/child).is_symlink():raise OSError('Symlink in FTP library')
                for filename in names:
                    target=base/filename;files[target.relative_to(root)]=self.fingerprint(target)
            managed={relative for relative,mark in files.items() if mark is not None and (previous.get(relative.as_posix())==mark or tuple(mark) in source_marks)}
            def safe(value):
                value=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',value).strip(' .')[:100]
                return value if value and not value.startswith('.') else 'Ohne Namen'
            def unique(parent,label,ident,directory=False):
                names=used.setdefault(parent,set());candidate=label;index=0
                while True:
                    relative=parent/candidate;target=root/relative
                    blocked=target.is_symlink() or target.exists() and not (target.is_dir() if directory else relative in managed)
                    if candidate.casefold() not in names and not blocked:break
                    index+=1;extension=Path(label).suffix if not directory else '';stem=label[:-len(extension)] if extension else label
                    candidate=stem+' ['+str(ident)+(' '+str(index) if index>1 else '')+']'+extension
                names.add(candidate.casefold());return relative
            def folder(ident,seen=()):
                if ident in paths:return paths[ident]
                row=by_id.get(ident)
                if not row or ident in seen or len(seen)>=8:return Path('.')
                parent=folder(row['parent_id'],(*seen,ident));paths[ident]=unique(parent,safe(row['name']),ident,directory=True)
                return paths[ident]
            for row in folders:folder(row['id'])
            for row in videos:
                if row['id'] not in sources:continue
                label=safe(row['name'])
                if not label.lower().endswith('.mp4'):label+='.mp4'
                expected[unique(folder(row['folder_id']),label,row['id'])]=sources[row['id']]
            directories={relative:ident for ident,relative in paths.items()}
            for relative in managed:
                target=root/relative;source=expected.get(relative)
                # Recheck the inode: a finished atomic upload may have replaced
                # the name since the scan. It is then incoming data, never trash.
                if self.fingerprint(target)!=files[relative]:continue
                if source is None or not os.path.samefile(target,source):target.unlink()
            for relative in sorted(old_dirs,key=lambda value:len(Path(value).parts),reverse=True):
                target=root/relative
                if Path(relative) in directories or not target.is_dir() or target.is_symlink():continue
                try:target.rmdir()
                except OSError as exc:
                    if exc.errno not in (errno.ENOTEMPTY,errno.EEXIST):raise
                    # Preserve the folder ID while an upload is still in an old
                    # folder name after a web rename/move.
                    directories[Path(relative)]=old_dirs[relative]
            for relative in sorted(directories,key=lambda value:len(value.parts)):
                target=root/relative
                if target.is_symlink():raise OSError('Symlink in FTP library')
                target.mkdir(mode=0o700,parents=True,exist_ok=True);target.chmod(0o700)
            for relative,source in expected.items():
                target=root/relative
                if source.stat().st_mode&0o222:source.chmod(0o400)
                if not target.exists() and not target.is_symlink():os.link(source,target)
            entries={relative.as_posix():self.fingerprint(root/relative) for relative,source in expected.items() if (root/relative).is_file() and not (root/relative).is_symlink() and os.path.samefile(root/relative,source)}
            c.write("UPDATE ftp_library_views SET entries=?,directories=?,error='' WHERE user_id=?",(json.dumps(entries),json.dumps({relative.as_posix():ident for relative,ident in directories.items()}),uid))
            candidates=seen_dirs|set(directories)
            self.library_versions[uid]=dict(revision=revision,directories={relative.as_posix():(root/relative).stat().st_mtime_ns for relative in candidates if (root/relative).is_dir() and not (root/relative).is_symlink()})
        except OSError:
            c.logging.exception('FTP-Bibliotheksansicht wird erneut synchronisiert.')
            c.write('UPDATE ftp_library_views SET error=? WHERE user_id=?',('Die Bibliotheksansicht wird erneut abgeglichen. Vorhandene Uploads bleiben erhalten.',uid))
    def library_upload(self,uid,path):
        views=self.c.rows('SELECT name FROM ftp_library_views WHERE user_id=?',(uid,))
        return bool(views and path.parts and path.parts[0]==views[0]['name'])
    def mirror_file(self,uid,path,relative):
        views=self.c.rows('SELECT name,entries FROM ftp_library_views WHERE user_id=?',(uid,))
        if not views or not relative.parts or relative.parts[0]!=views[0]['name']:return False
        mark=self.mapping(views[0]['entries']).get(Path(*relative.parts[1:]).as_posix())
        return mark is not None and self.fingerprint(path)==mark
    def upload_folder(self,user,relative):
        views=self.c.rows('SELECT name,directories FROM ftp_library_views WHERE user_id=?',(user['id'],))
        if not views or not relative.parts or relative.parts[0]!=views[0]['name']:return self.folder(user,relative.parent)
        parent=Path(*relative.parts[1:]).parent;mapping=self.mapping(views[0]['directories']);anchor=parent
        while anchor.as_posix() not in mapping and anchor!=Path('.'):anchor=anchor.parent
        ident=mapping.get(anchor.as_posix())
        if ident is not None and not self.c.rows('SELECT id FROM playlist_folders WHERE id=? AND user_id=?',(ident,user['id'])):raise self.c.Error('Der Zielordner für diesen FTP-Upload wurde gelöscht. Bitte einen vorhandenen Ordner wählen.')
        return self.folder(user,parent.relative_to(anchor),parent=ident)
    def password(self,value):
        if not isinstance(value,str) or not 12<=len(value)<=256 or any(not x.isprintable() for x in value):raise self.c.Error('Das FTP-Passwort benötigt 12–256 sichtbare Zeichen.')
        return value
    def source(self,row):
        c=self.c;home=self.root/str(row['user_id']);original=Path(row['path'])
        if '..' in original.parts or not original.is_relative_to(home) or not self.video_name(original):raise c.Error('Ungültige FTP-Datei.')
        path=Path(row['staging'] or row['path'])
        if row['staging'] and (path.parent!=c.DATA/'uploads' or not re.fullmatch(r'ftp-[0-9a-f]{32}\.mp4',path.name)):raise c.Error('Ungültige FTP-Zwischendatei.')
        if any(p.is_symlink() for p in [path,*path.parents]):raise c.Error('Ungültige FTP-Datei.')
        try:details=path.stat()
        except FileNotFoundError:raise c.Error('Die Quelldatei ist nicht mehr vorhanden. Bitte erneut per FTP hochladen.') from None
        if not stat.S_ISREG(details.st_mode) or details.st_nlink!=1:raise c.Error('Die Datei ist keine neue FTP-Videodatei.')
        if details.st_size<=0:raise c.Error('Die FTP-Datei ist leer oder wurde unvollständig übertragen.')
        return path
    def recover_old_size_errors(self):
        c=self.c
        for row in c.rows("SELECT i.* FROM ftp_imports i JOIN users u ON u.id=i.user_id JOIN ftp_accounts f ON f.user_id=u.id WHERE i.state='error' AND i.message='Nur MP4-Dateien bis 500 MB können importiert werden.' AND u.active=1 AND f.enabled=1"):
            try:path=self.source(row)
            except (c.Error,OSError):continue
            details=path.stat()
            # A later upload under the same name needs its own completion
            # receipt; an old rejection must not consume an active transfer.
            if details.st_size>500*1024*1024 and details.st_mtime<=row['created']:
                c.write("UPDATE ftp_imports SET state='queued',message='Die frühere Größenbegrenzung ist aufgehoben. Import wird erneut versucht.' WHERE id=?",(row['id'],))
    @staticmethod
    def video_name(path):
        # Pure-FTPd's AutoRename preserves an existing file and appends .1, .2,
        # etc. Keep those uploads importable and give them a normal MP4 name.
        match=re.fullmatch(r'(.+\.mp4)(?:\.(\d+))?',path.name,re.I)
        if not match:return None
        return match[1] if not match[2] else Path(match[1]).stem+' ('+match[2]+')'+Path(match[1]).suffix
    def ingest_log(self):
        """Pure-FTPd emits transfer events after closing a transfer, never by file age."""
        c=self.c;log=Path(os.getenv('STREAMDESK_FTP_LOG',str(c.DATA/'ftp-transfers.log')))
        if not log.is_file() or log.is_symlink():return
        metadata=log.stat();saved=c.rows('SELECT * FROM ftp_log_state WHERE id=1');offset=saved[0]['offset'] if saved and saved[0]['inode']==metadata.st_ino and saved[0]['offset']<=metadata.st_size else 0
        with log.open('rb') as stream:
            stream.seek(offset)
            for _ in range(100):
                start=stream.tell();line=stream.readline(8193)
                if not line:break
                if not line.endswith(b'\n'):
                    if len(line)>8192:offset=stream.tell();continue
                    break
                offset=stream.tell();parts=line.decode('utf8','replace').rstrip('\n').split(' ',7)
                if len(parts)!=8 or parts[4]!='U':continue
                found=c.rows('SELECT * FROM ftp_accounts WHERE username=? AND enabled=1',(parts[2],))
                if not found:continue
                try:size=int(parts[5]);path=Path(parts[7]);uid=found[0]['user_id'];home=self.root/str(uid)
                except (ValueError,TypeError):continue
                if not path.is_absolute() or not path.is_relative_to(home) or any(p.is_symlink() for p in [path,*path.parents]) or not self.video_name(path):continue
                relative=path.relative_to(home)
                try:
                    if path.stat().st_nlink!=1 or self.mirror_file(uid,path,relative):continue
                except OSError:continue
                checked=Path(*relative.parts[1:]) if self.library_upload(uid,relative) else relative
                if len(checked.parts)>9 or any(part.startswith('.') or len(part)>120 or any(not ch.isprintable() for ch in part) for part in checked.parts):continue
                ident=hashlib.sha256((str(metadata.st_ino)+':'+str(start)+':'+line.decode('utf8','replace')).encode()).hexdigest()
                c.write('INSERT OR IGNORE INTO ftp_imports(id,user_id,path,size,created) VALUES (?,?,?,?,?)',(ident,uid,str(path),size,time.time()))
        c.write('INSERT INTO ftp_log_state(id,inode,offset) VALUES (1,?,?) ON CONFLICT(id) DO UPDATE SET inode=excluded.inode,offset=excluded.offset',(metadata.st_ino,offset))
    def folder(self,user,path,parent=None):
        for part in path.parts:
            name=self.c.PLAYLISTS.name(part);rows=[row for row in self.c.rows('SELECT id,name FROM playlist_folders WHERE user_id=? AND parent_id IS ?',(user['id'],parent)) if row['name'].casefold()==name.casefold()]
            if rows:parent=rows[0]['id']
            else:
                if len(self.c.rows('SELECT id FROM playlist_folders WHERE user_id=?',(user['id'],)))>=100:raise self.c.Error('Maximale Ordneranzahl erreicht.')
                parent=self.c.write('INSERT INTO playlist_folders(user_id,name,parent_id) VALUES (?,?,?)',(user['id'],name,parent))
        return parent
    def import_one(self,row):
        c=self.c;path=self.source(row);home=self.root/str(row['user_id']);target=None
        with c.LOCK:
            found=c.rows("SELECT u.* FROM users u JOIN ftp_accounts f ON u.id=f.user_id WHERE u.id=? AND u.active=1 AND f.enabled=1",(row['user_id'],))
            if not found:return
            user=found[0]
            if user['upload_state'] in ('queued','processing') or len(c.rows("SELECT id FROM users WHERE upload_state IN ('queued','processing')"))>=2:return
            if not row['staging'] and self.mirror_file(row['user_id'],path,path.relative_to(home)):raise c.Error('Ungültige FTP-Datei.')
            try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            except FileNotFoundError:raise c.Error('FTP-Datei wurde verschoben oder entfernt.') from None
            with os.fdopen(fd,'rb') as stream:
                details=os.fstat(stream.fileno())
                if not stat.S_ISREG(details.st_mode) or details.st_nlink!=1 or details.st_size<=0:raise c.Error('Die FTP-Datei ist leer oder keine reguläre neue Videodatei.')
                try:fcntl.lockf(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
                except BlockingIOError:return
                try:require_space(c)
                except c.Error:
                    c.write("UPDATE ftp_imports SET message='Zu wenig freier Speicher. Der Import wartet auf freien Platz.' WHERE id=?",(row['id'],));return
                folder=row['folder_id'] if row['staging'] else self.upload_folder(user,path.relative_to(home));ident=secrets.token_urlsafe(24);name=self.video_name(Path(row['path']))
                if not name:raise c.Error('Nur MP4-Dateien können importiert werden.')
                name=name[:120]
                c.UPLOADS.register(user,ident,name,details.st_size,'ftp',folder)
                target=path if row['staging'] else c.DATA/'uploads'/('ftp-'+secrets.token_hex(16)+'.mp4');target.parent.mkdir(exist_ok=True)
                # Detach the inode from the FTP jail before processing it. An encoder
                # never follows a path that the FTP client can replace later.
                if path!=target:path.rename(target)
                c.write("UPDATE users SET upload_state='queued',upload_id=?,upload_message='FTP-Video wartet auf Umwandlung.' WHERE id=?",(ident,user['id']))
                c.UPLOAD_RESERVATIONS[user['id']]=0
                c.write("UPDATE ftp_imports SET state='processing',upload_id=?,message='Video wird umgewandelt.',staging=?,folder_id=? WHERE id=?",(ident,str(target),folder,row['id']))
                try:c.JOBS.submit(c.convert,user['id'],target,name,folder,upload_id=ident)
                except Exception:
                    c.UPLOAD_RESERVATIONS.pop(user['id'],None);c.write("UPDATE users SET upload_state='error' WHERE id=?",(user['id'],));c.UPLOADS.update(ident,user['id'],'error',message='FTP-Import konnte nicht gestartet werden.')
                    raise c.Error('FTP-Import konnte nicht gestartet werden. Die Quelldatei bleibt für einen neuen Versuch erhalten.') from None
    def run(self):
        c=self.c
        try:
            if not self.configured() or not c.SERVICES.enabled('ftp') or not c.SERVICES.enabled('playlists'):return
            for user in c.rows('SELECT u.* FROM users u JOIN ftp_accounts f ON u.id=f.user_id WHERE u.active=1'):
                self.sync_library(user)
            with c.LOCK:self.ingest_log()
            with c.LOCK:self.recover_old_size_errors()
            for row in c.rows("SELECT * FROM ftp_imports WHERE state='processing'"):
                jobs=c.rows('SELECT state,message FROM video_uploads WHERE id=?',(row['upload_id'],))
                if jobs and jobs[0]['state'] in ('ready','error'):c.write('UPDATE ftp_imports SET state=?,message=? WHERE id=?',(jobs[0]['state'],jobs[0]['message'],row['id']))
            for row in c.rows("SELECT * FROM ftp_imports WHERE state='queued' ORDER BY created LIMIT 30"):
                try:self.import_one(row)
                except (c.Error,OSError) as exc:c.write("UPDATE ftp_imports SET state='error',message=? WHERE id=?",(str(exc) if isinstance(exc,c.Error) else 'FTP-Datei konnte nicht importiert werden.',row['id']))
        except Exception:c.logging.exception('FTP-Import wird erneut versucht.')
    def tick(self):
        if self.configured() and time.monotonic()-self.last_tick>=3 and (not self.worker or not self.worker.is_alive()):
            self.last_tick=time.monotonic();self.worker=self.c.threading.Thread(target=self.run,daemon=True);self.worker.start()
