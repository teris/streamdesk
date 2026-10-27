"""Persistent scheduler, allowlisted hooks and idempotent HTTPS exports."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

from flask import jsonify, request


class AutomationFeatures:
    EVENTS = {'publish', 'ready'}
    JOBS = {'record_start', 'record_stop', 'output_start', 'output_stop', 'twitch_start'}

    def __init__(self, core):
        self.c = core
        self.last_tick = 0
        self.last_export = 0
        self.busy_users = set()
        self.workers = {}
        self.worker_lock = threading.Lock()
        self.states = {}
        try:
            configured = json.loads(os.getenv('STREAMDESK_HOOK_ALLOWLIST', '{}'))
        except json.JSONDecodeError:
            configured = {}
        if not isinstance(configured, dict):
            configured = {}
        self.commands = {name:value for name,value in configured.items()
                         if re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name)
                         and isinstance(value,list) and value and len(value)<=16
                         and all(isinstance(part,str) and 0<len(part)<=512 for part in value)}
        with core.db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS automation_hooks(
                  id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,event TEXT NOT NULL,
                  action_name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS scheduled_jobs(
                  id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,
                  run_at REAL NOT NULL,status TEXT NOT NULL DEFAULT 'pending',message TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS export_targets(
                  user_id INTEGER PRIMARY KEY,url TEXT NOT NULL,username TEXT NOT NULL DEFAULT '',
                  password TEXT NOT NULL DEFAULT '',enabled INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS exported_media(
                  user_id INTEGER NOT NULL,path TEXT NOT NULL,mtime REAL NOT NULL,status TEXT NOT NULL,
                  message TEXT NOT NULL DEFAULT '',PRIMARY KEY(user_id,path,mtime));
            ''')
            columns = {row['name'] for row in connection.execute('PRAGMA table_info(exported_media)')}
            for name, default in (('attempts', 'INTEGER NOT NULL DEFAULT 0'), ('retry_at', 'REAL NOT NULL DEFAULT 0')):
                if name not in columns:
                    connection.execute('ALTER TABLE exported_media ADD COLUMN ' + name + ' ' + default)
            connection.execute("UPDATE scheduled_jobs SET status='error',message='Ausführung durch Neustart unterbrochen; vor erneutem Start prüfen.' WHERE status='running'")
            connection.execute("UPDATE exported_media SET status='error',retry_at=0 WHERE status='running'")
        self.install_routes()

    def install_routes(self):
        c = self.c
        expert = lambda function:c.login_required(c.expert_required(function))

        @c.app.get('/api/automation')
        @expert
        def automation_status(user):
            return jsonify(
                hooks=c.rows('SELECT id,event,action_name,enabled FROM automation_hooks WHERE user_id=? ORDER BY id',(user['id'],)),
                jobs=c.rows('SELECT id,kind,payload,run_at,status,message FROM scheduled_jobs WHERE user_id=? ORDER BY run_at DESC LIMIT 100',(user['id'],)),
                export=self.public_export(user), available_hooks=sorted(self.commands))

        @c.app.post('/api/automation/hooks')
        @expert
        def automation_save_hook(user):
            body = self.c.FEATURES.body()
            event, action = body.get('event'), body.get('action_name')
            if event not in self.EVENTS or action not in self.commands:
                raise c.Error('Hook-Ereignis oder Allowlist-Aktion ist ungültig.')
            c.write('INSERT INTO automation_hooks(user_id,event,action_name,enabled) VALUES (?,?,?,1)',
                    (user['id'],event,action))
            return jsonify(ok=True)

        @c.app.delete('/api/automation/hooks/<int:ident>')
        @expert
        def automation_delete_hook(user, ident):
            c.write('DELETE FROM automation_hooks WHERE id=? AND user_id=?',(ident,user['id']))
            return '',204

        @c.app.post('/api/automation/jobs')
        @expert
        def automation_schedule(user):
            body = self.c.FEATURES.body()
            kind, payload = body.get('kind'), body.get('payload') or {}
            try:
                run_at = float(body.get('run_at'))
            except (TypeError,ValueError):
                raise c.Error('Ungültiger Ausführungszeitpunkt.') from None
            if kind not in self.JOBS or not isinstance(payload,dict) or not time.time()-60 <= run_at <= time.time()+366*86400:
                raise c.Error('Ungültiger geplanter Auftrag.')
            if kind == 'record_start':
                c.MODEL.record_path(user,str(payload.get('source','live')))
            if kind.startswith('output_') and payload.get('kind') not in c.output_kinds(user):
                raise c.Error('Ausgang nicht gefunden.',http_status=404)
            if kind == 'twitch_start':
                title = str(payload.get('title', '')).strip()
                game = str(payload.get('game_id', '')).strip()
                if not title or len(title) > 140 or game and not re.fullmatch(r'[0-9]{1,20}', game):
                    raise c.Error('Twitch-Zeitplan benötigt einen gültigen Titel und optional eine Kategorie-ID.')
                if 'twitch' not in c.output_kinds(user):
                    raise c.Error('Twitch-Ausgang nicht gefunden.',http_status=404)
            ident=c.write('INSERT INTO scheduled_jobs(user_id,kind,payload,run_at) VALUES (?,?,?,?)',
                          (user['id'],kind,json.dumps(payload,separators=(',',':')),run_at))
            return jsonify(ok=True,id=ident)

        @c.app.delete('/api/automation/jobs/<int:ident>')
        @expert
        def automation_cancel(user, ident):
            c.write("UPDATE scheduled_jobs SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'",(ident,user['id']))
            return '',204

        @c.app.post('/api/automation/export')
        @expert
        def automation_export(user):
            body = self.c.FEATURES.body()
            enabled = body.get('enabled')
            if type(enabled) is not bool:
                raise c.Error('Ungültiger Exportschalter.')
            url = str(body.get('url','')).strip()
            if enabled:
                self.c.validate_public_http(url)
                if not url.endswith('/') or urllib.parse.urlsplit(url).query:
                    raise c.Error('Die WebDAV-/Upload-Adresse muss mit / enden.')
            username = str(body.get('username',''))[:256]
            password = str(body.get('password',''))
            previous = c.rows('SELECT * FROM export_targets WHERE user_id=?',(user['id'],))
            encrypted_password = c.encrypt(password) if password else previous[0]['password'] if previous else ''
            c.write('''INSERT INTO export_targets(user_id,url,username,password,enabled) VALUES (?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET url=excluded.url,username=excluded.username,
                       password=excluded.password,enabled=excluded.enabled''',
                    (user['id'],c.encrypt(url),c.encrypt(username),encrypted_password,int(enabled)))
            return jsonify(ok=True)

    def public_export(self,user):
        found=self.c.rows('SELECT url,username,enabled FROM export_targets WHERE user_id=?',(user['id'],))
        if not found:return {'enabled':False,'url':'','username':''}
        return {'enabled':bool(found[0]['enabled']),'url':self.c.decrypt(found[0]['url']),
                'username':self.c.decrypt(found[0]['username'])}

    def observe(self,user,sources,programs):
        if not self.c.SERVICES.enabled('automation'):return
        current={'publish':any(row.get('state')=='online' for row in sources),
                 'ready':any(row.get('available') for row in programs)}
        before=self.states.get(user['id'],{})
        self.states[user['id']]=current
        for event,value in current.items():
            if value and not before.get(event):
                for hook in self.c.rows('SELECT action_name FROM automation_hooks WHERE user_id=? AND event=? AND enabled=1',
                                        (user['id'],event)):
                    threading.Thread(target=self.run_hook,args=(user,event,hook['action_name']),daemon=True).start()

    def run_hook(self,user,event,name):
        if not self.c.SERVICES.enabled('automation'):return
        command=self.commands.get(name)
        if not command:return
        environment={'PATH':'/usr/local/bin:/usr/bin:/bin','STREAMDESK_EVENT':event,
                     'STREAMDESK_USER_ID':str(user['id']),'STREAMDESK_USERNAME':user['username']}
        try:
            subprocess.run(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=15,check=False)
        except (OSError,subprocess.TimeoutExpired):
            self.c.logging.warning('Allowlist-Hook %s fehlgeschlagen (Benutzer-ID %s).',name,user['id'])

    def tick(self):
        if not self.c.SERVICES.enabled('automation'):return
        now=time.time()
        if now-self.last_tick<1:return
        self.last_tick=now
        with self.worker_lock:
            for name, target in (('schedule', self.run_scheduled), ('exports', self.export_ready)):
                if name == 'exports' and now-self.last_export < 10:
                    continue
                worker = self.workers.get(name)
                if worker is None or not worker.is_alive():
                    if name == 'exports':self.last_export=now
                    worker = threading.Thread(target=self.run_worker, args=(target,), daemon=True)
                    self.workers[name] = worker
                    worker.start()

    def run_worker(self, target):
        try:
            target()
        except Exception:
            self.c.logging.exception('Hintergrundauftrag fehlgeschlagen; Quellensteuerung bleibt aktiv.')

    def run_scheduled(self):
        if not self.c.SERVICES.enabled('automation'):return
        now = time.time()
        for job in self.c.rows("SELECT * FROM scheduled_jobs WHERE status='pending' AND run_at<=? ORDER BY run_at LIMIT 20",(now,)):
            with self.c.LOCK, self.c.db() as connection:
                if not self.c.SERVICES.enabled('automation'):return
                if job['user_id'] in self.busy_users:
                    continue
                cursor = connection.execute("UPDATE scheduled_jobs SET status='running' WHERE id=? AND status='pending'",(job['id'],))
                if cursor.rowcount != 1:
                    continue
                self.busy_users.add(job['user_id'])
            try:
                user=self.c.rows("SELECT * FROM users WHERE id=? AND active=1 AND role!='moderator'",(job['user_id'],))[0]
                payload=json.loads(job['payload'])
                if job['kind']=='record_start':self.c.start_recording(user,str(payload.get('source','live')))
                elif job['kind']=='record_stop':self.c.ENGINE.stop_record(user['id'],'Zeitplan beendet.')
                elif job['kind']=='output_start':self.c.forward(user,True,kind=payload['kind'])
                elif job['kind']=='output_stop':self.c.forward(user,False,kind=payload['kind'])
                elif job['kind']=='twitch_start':
                    change={'title':str(payload['title']).strip()}
                    if payload.get('game_id'):change['game_id']=str(payload['game_id'])
                    self.c.twitch_user_api(user,'channels?broadcaster_id={broadcaster}',change)
                    self.c.forward(user,True,kind='twitch')
                self.c.write("UPDATE scheduled_jobs SET status='done' WHERE id=?",(job['id'],))
            except Exception as error:
                self.c.write("UPDATE scheduled_jobs SET status='error',message=? WHERE id=?",
                             (type(error).__name__,job['id']))
            finally:
                with self.c.LOCK:
                    self.busy_users.discard(job['user_id'])

    def export_ready(self):
        if not self.c.SERVICES.enabled('automation'):return
        for target in self.c.rows('SELECT * FROM export_targets WHERE enabled=1'):
            if not self.c.SERVICES.enabled('automation'):return
            user=self.c.rows("SELECT * FROM users WHERE id=? AND active=1 AND role!='moderator'",(target['user_id'],))
            if not user:continue
            for recording in self.c.rows("SELECT path FROM recordings WHERE user_id=? AND status='ready' ORDER BY id",(target['user_id'],)):
                if not self.c.SERVICES.enabled('automation'):return
                path=Path(recording['path'])
                if not path.is_file() or path.is_symlink():continue
                stamp=path.stat().st_mtime
                with self.c.LOCK:
                    if target['user_id'] in self.busy_users:
                        continue
                    if not self.c.rows('SELECT id FROM users WHERE id=? AND active=1', (target['user_id'],)):
                        break
                    if self.c.rows("SELECT 1 FROM exported_media WHERE user_id=? AND path=? AND mtime=? AND (status='done' OR retry_at>?)",
                                   (target['user_id'],str(path),stamp,time.time())):continue
                    self.c.write("INSERT INTO exported_media(user_id,path,mtime,status) VALUES (?,?,?,'running') ON CONFLICT(user_id,path,mtime) DO UPDATE SET status='running'",
                                 (target['user_id'],str(path),stamp))
                    self.busy_users.add(target['user_id'])
                try:
                    base=self.c.decrypt(target['url'])
                    self.c.validate_public_http(base)
                    headers={'Content-Type':'video/mp4'}
                    username=self.c.decrypt(target['username'])
                    if username:
                        token=base64.b64encode((username+':'+self.c.decrypt(target['password'])).encode()).decode()
                        headers['Authorization']='Basic '+token
                    headers['Content-Length'] = str(path.stat().st_size)
                    import hashlib
                    headers['Idempotency-Key'] = hashlib.sha256((str(target['user_id'])+':'+str(path)+':'+str(stamp)).encode()).hexdigest()
                    with path.open('rb') as content:
                        with self.c.public_https(urllib.parse.urljoin(base,urllib.parse.quote(path.name)),
                                                 data=content,headers=headers,method='PUT',timeout=15) as response:
                            if not 200 <= response.status < 300:raise OSError()
                    self.c.write("UPDATE exported_media SET status='done',message='' WHERE user_id=? AND path=? AND mtime=?",
                                 (target['user_id'],str(path),stamp))
                except (OSError,ValueError,self.c.Error):
                    self.c.write("UPDATE exported_media SET status='error',message='Upload fehlgeschlagen',attempts=attempts+1,retry_at=? WHERE user_id=? AND path=? AND mtime=?",
                                 (time.time()+300,target['user_id'],str(path),stamp))
                finally:
                    with self.c.LOCK:
                        self.busy_users.discard(target['user_id'])
