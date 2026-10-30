"""Per-user studio preferences and recurring, provider-independent stream plans."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import jsonify, request
from playlist_features import active_schedule, intervals, minute

TABLES=('stream_plans','planner_outputs','twitch_plan_segments')

def migrate(c):
    with c.db() as db:
        columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
        for name,definition in [('expert_preference','INTEGER NOT NULL DEFAULT 0'),('switch_text',"TEXT NOT NULL DEFAULT 'Synchronisation'"),('replay_label',"TEXT NOT NULL DEFAULT 'Wiederholung'"),('replay_corner',"TEXT NOT NULL DEFAULT 'top-left'")]:
            if name not in columns:db.execute('ALTER TABLE users ADD COLUMN '+name+' '+definition)
        db.executescript('''CREATE TABLE IF NOT EXISTS stream_plans(
          id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,title TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
          timezone TEXT NOT NULL,days TEXT NOT NULL,start TEXT NOT NULL,end TEXT NOT NULL,playlist_id INTEGER NOT NULL,
          targets TEXT NOT NULL,sync_twitch INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,sync_message TEXT NOT NULL DEFAULT '');
          CREATE TABLE IF NOT EXISTS planner_outputs(user_id INTEGER NOT NULL,kind TEXT NOT NULL,mode TEXT NOT NULL DEFAULT '',window TEXT NOT NULL DEFAULT '',blocked TEXT NOT NULL DEFAULT '',PRIMARY KEY(user_id,kind));
          CREATE TABLE IF NOT EXISTS twitch_plan_segments(user_id INTEGER NOT NULL,plan_id INTEGER NOT NULL,day INTEGER NOT NULL,segment_id TEXT NOT NULL,revision INTEGER NOT NULL,PRIMARY KEY(user_id,plan_id,day));''')

class StudioFeatures:
    def __init__(self,c):
        self.c=c;self.migrate_common_playlist();self.retry={};self.last_sync=0;self.sync_worker=None;self.install_routes()
    def migrate_common_playlist(self):
        c=self.c
        with c.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS studio_migrations(name TEXT PRIMARY KEY)')
            if db.execute("SELECT 1 FROM studio_migrations WHERE name='common-source2'").fetchone():return
            for user in db.execute('SELECT id FROM users').fetchall():
                profiles=db.execute("SELECT * FROM playlist_profiles WHERE user_id=? ORDER BY CASE scope WHEN 'source:source2' THEN 0 WHEN 'default' THEN 1 ELSE 2 END,scope",(user['id'],)).fetchall()
                chosen=next((p for p in profiles if p['enabled']),None)
                if chosen:
                    db.execute('UPDATE playlist_profiles SET enabled=0 WHERE user_id=?',(user['id'],))
                    db.execute("INSERT INTO playlist_profiles(user_id,scope,enabled,playlist_id,delay_seconds,timezone,schedules,auto_start) VALUES (?,'source:source2',1,?,?,?,?,?) ON CONFLICT(user_id,scope) DO UPDATE SET enabled=1,playlist_id=excluded.playlist_id,delay_seconds=excluded.delay_seconds,timezone=excluded.timezone,schedules=excluded.schedules,auto_start=excluded.auto_start",(user['id'],chosen['playlist_id'],chosen['delay_seconds'],chosen['timezone'],chosen['schedules'],chosen['auto_start']))
            for row in db.execute("SELECT * FROM playlist_positions ORDER BY CASE program WHEN 'main' THEN 0 ELSE 1 END").fetchall():
                db.execute("INSERT OR IGNORE INTO playlist_positions(user_id,program,playlist_id,revision,offset) VALUES (?,'source2-playlist',?,?,?)",(row['user_id'],row['playlist_id'],row['revision'],row['offset']))
            db.execute("INSERT INTO studio_migrations(name) VALUES ('common-source2')")
    def preferences(self,user):
        return {k:user[k] for k in ('switch_text','replay_label','replay_corner')}
    def owned(self,user,ident):return self.c.PLAYLISTS.owned('stream_plans',user,ident)
    def public_plan(self,row):
        return dict(row,days=json.loads(row['days']),targets=json.loads(row['targets']),enabled=bool(row['enabled']),sync_twitch=bool(row['sync_twitch']))
    def install_routes(self):
        c=self.c
        @c.app.get('/api/studio/preferences',endpoint='studio_preferences')
        @c.login_required
        def preferences(user):return jsonify(**self.preferences(user))
        @c.app.post('/api/studio/preferences',endpoint='studio_save_preferences')
        @c.login_required
        def save_preferences(user):
            b=c.FEATURES.body();text=b.get('switch_text');label=b.get('replay_label');corner=b.get('replay_corner')
            if any(not isinstance(s,str) or not 1<=len(s.strip())<=100 or any(not ch.isprintable() for ch in s) for s in (text,label)):
                raise c.Error('Bitte einen sichtbaren Text mit 1–100 Zeichen eingeben.')
            if corner not in ('top-left','top-right','bottom-left','bottom-right'):raise c.Error('Ungültige Overlay-Position.')
            fresh=dict(user,switch_text=text.strip(),replay_label=label.strip(),replay_corner=corner)
            self.switch_file(fresh,create=True)
            with c.LOCK:
                before=self.preferences(user)
                c.write('UPDATE users SET switch_text=?,replay_label=?,replay_corner=? WHERE id=?',(fresh['switch_text'],fresh['replay_label'],corner,user['id']))
                try:c.reconcile()
                except Exception:
                    c.write('UPDATE users SET switch_text=?,replay_label=?,replay_corner=? WHERE id=?',(before['switch_text'],before['replay_label'],before['replay_corner'],user['id']))
                    raise
            return jsonify(ok=True)
        @c.app.get('/api/planner')
        @c.login_required
        def planner(user):
            auth=c.rows('SELECT scopes FROM twitch_auth WHERE user_id=?',(user['id'],))
            return jsonify(plans=[self.public_plan(row) for row in c.rows('SELECT * FROM stream_plans WHERE user_id=? ORDER BY start,id',(user['id'],))],
                           playlists=c.PLAYLISTS.public(user)['playlists'],outputs=[dict(kind=row['kind'],label=row.get('label') or {'twitch':'Twitch','youtube':'YouTube','custom':'Eigener Anbieter'}.get(row['kind'],row['kind']),configured=bool(row['endpoint']),allowed=c.SERVICES.output_allowed(row['kind'])) for row in c.destinations(user)],
                           twitch_schedule_connected=bool(auth and 'channel:manage:schedule' in json.loads(auth[0]['scopes'] or '[]')))
        @c.app.post('/api/planner')
        @c.login_required
        def add_plan(user):return self.save(user,None)
        @c.app.route('/api/planner/<int:ident>',methods=['POST','DELETE'])
        @c.login_required
        def edit_plan(user,ident):
            self.owned(user,ident)
            if request.method=='DELETE':
                with c.LOCK:c.write('DELETE FROM stream_plans WHERE id=? AND user_id=?',(ident,user['id']))
                return jsonify(ok=True)
            return self.save(user,ident)
    def save(self,user,ident):
        c=self.c;b=c.FEATURES.body();title=c.PLAYLISTS.name(b.get('title'));enabled=c.FEATURES.boolean(b,'enabled');sync=c.FEATURES.boolean(b,'sync_twitch')
        zone=b.get('timezone','Europe/Berlin')
        try:
            if not isinstance(zone,str) or len(zone)>80:raise ValueError()
            ZoneInfo(zone)
        except (ValueError,ZoneInfoNotFoundError):raise c.Error('Ungültige Zeitzone.') from None
        rules=c.PLAYLISTS.validate_rules(user,[dict(playlist_id=b.get('playlist_id'),start=b.get('start'),end=b.get('end'),days=b.get('days'))]);rule=rules[0]
        if not c.PLAYLISTS.videos(user,json.loads(c.PLAYLISTS.owned('playlists',user,rule['playlist_id'])['items'])):raise c.Error('Bitte eine Playlist mit Videos wählen.')
        targets=b.get('targets')
        if not isinstance(targets,list) or not targets or any(not isinstance(k,str) or k not in c.output_kinds(user) for k in targets) or len(targets)!=len(set(targets)):raise c.Error('Bitte mindestens einen gültigen Ausgang wählen.')
        for kind in targets:
            c.SERVICES.require_output(kind)
            if not c.MODEL.route(user,kind):raise c.Error('Der Ausgang benötigt zuerst eine Quellenzuordnung.')
            if not any(d['kind']==kind and d['endpoint'] for d in c.destinations(user)):raise c.Error('Bitte den gewählten Anbieter zuerst einrichten.')
        if sync and 'twitch' not in targets:raise c.Error('Für die Twitch-Übertragung bitte den Standard-Twitch-Ausgang wählen.')
        if sync and not 30<=((minute(rule['end'])-minute(rule['start']))%1440 or 1440)<=1380:raise c.Error('Twitch-Sendezeiten benötigen eine Dauer von 30 Minuten bis 23 Stunden. Ohne Twitch-Übertragung sind andere Zeitfenster möglich.')
        with c.LOCK:
            if ident:self.owned(user,ident)
            existing=c.rows('SELECT * FROM stream_plans WHERE user_id=?',(user['id'],))
            if ident is None and len(existing)>=100:raise c.Error('Maximal 100 geplante Streams.')
            if enabled:
                for old in existing:
                    if old['id']==ident or not old['enabled']:continue
                    if zone!=old['timezone']:raise c.Error('Gemeinsame Ausgänge müssen dieselbe Zeitzone verwenden.',http_status=409)
                    prior=dict(start=old['start'],end=old['end'],days=json.loads(old['days']))
                    if any(a<d and b_>c_ for a,b_ in intervals(rule) for c_,d in intervals(prior)) and (set(targets)&set(json.loads(old['targets'])) or old['playlist_id']!=rule['playlist_id']):raise c.Error('Eine gemeinsame Playlist über Source 2: überlappende Pläne benötigen dieselbe Playlist und unterschiedliche Ausgänge.',http_status=409)
            args=(title,int(enabled),zone,json.dumps(rule['days']),rule['start'],rule['end'],rule['playlist_id'],json.dumps(targets),int(sync))
            if ident:c.write("UPDATE stream_plans SET title=?,enabled=?,timezone=?,days=?,start=?,end=?,playlist_id=?,targets=?,sync_twitch=?,revision=revision+1,sync_message='' WHERE id=? AND user_id=?",args+(ident,user['id']))
            else:ident=c.write('INSERT INTO stream_plans(user_id,title,enabled,timezone,days,start,end,playlist_id,targets,sync_twitch) VALUES (?,?,?,?,?,?,?,?,?,?)',(user['id'],)+args)
        return jsonify(ok=True,id=ident)
    def active(self,user,kind,stamp=None):
        if not self.c.SERVICES.enabled('automation') or not self.c.SERVICES.enabled('playlists'):return None
        for row in self.c.rows('SELECT * FROM stream_plans WHERE user_id=? AND enabled=1 ORDER BY id',(user['id'],)):
            if kind not in json.loads(row['targets']):continue
            rule,window=active_schedule([dict(start=row['start'],end=row['end'],days=json.loads(row['days']))],row['timezone'],time.time() if stamp is None else stamp)
            if rule:return dict(row,window='plan:'+str(row['id'])+':'+str(row['revision'])+':'+window)
        return None
    def plan(self,user,program,stamp=None):
        for kind in self.c.output_kinds(user):
            if not self.c.SERVICES.output_allowed(kind):continue
            active=self.active(user,kind,stamp)
            if not active:continue
            rows=self.c.rows('SELECT * FROM playlists WHERE id=? AND user_id=?',(active['playlist_id'],user['id']))
            if not rows:continue
            return dict(profile={'scope':'source:source2'},playlist=rows[0],scheduled=True,window=active['window'],delay=0,auto=False,planner=True)
        return None
    def manual_control(self,user,kind=None):
        for target in [kind] if kind else self.c.output_kinds(user):
            active=self.active(user,target)
            self.c.write("INSERT INTO planner_outputs(user_id,kind,blocked) VALUES (?,?,?) ON CONFLICT(user_id,kind) DO UPDATE SET mode='',window='',blocked=excluded.blocked",(user['id'],target,active['window'] if active else ''))
    def tick_outputs(self,user,program,config,now):
        c=self.c
        for kind in program['targets']:
            active=self.active(user,kind);states=c.rows('SELECT * FROM planner_outputs WHERE user_id=? AND kind=?',(user['id'],kind));state=states[0] if states else dict(mode='',window='',blocked='')
            path=c.output_path(user,kind);running=bool(config['paths'].get(path,{}).get('forward'));wanted=active and c.SERVICES.output_allowed(kind)
            if now<self.retry.get((user['id'],kind),0):continue
            try:
                if wanted and not running and state['blocked']!=active['window']:
                    c.forward(user,True,kind=kind,origin='planner')
                    c.write("INSERT INTO planner_outputs(user_id,kind,mode,window) VALUES (?,?,'schedule',?) ON CONFLICT(user_id,kind) DO UPDATE SET mode='schedule',window=excluded.window",(user['id'],kind,active['window']))
                    config['paths'][path]['forward']=c.configured_forwards(user)[path]
                elif wanted and state['mode'] and state['window']!=active['window']:
                    c.write('UPDATE planner_outputs SET window=? WHERE user_id=? AND kind=?',(active['window'],user['id'],kind))
                elif not wanted and state['mode']:
                    if running:c.forward(user,False,kind=kind,origin='planner');config['paths'][path]['forward']=[]
                    c.write("UPDATE planner_outputs SET mode='',window='' WHERE user_id=? AND kind=?",(user['id'],kind))
            except (c.Error,OSError):
                self.retry[(user['id'],kind)]=now+30
                c.logging.warning('Geplanter Ausgang konnte nicht geschaltet werden (Benutzer %s).',user['id'])
    def can_switch_video(self):
        import os
        return os.getenv('STREAMDESK_MEDIAMTX_MODE')!='remote-api' or os.getenv('STREAMDESK_NATIVE_SHARED')=='1'
    def switch_file(self,user,create=False):
        if not self.can_switch_video():return ''
        c=self.c;folder=c.FEATURES.native_root if user['switch_text']=='Synchronisation' else c.FEATURES.native_root/user['username']
        if folder.is_symlink():raise c.Error('Ungültiger Speicherordner.')
        key=hashlib.sha256(user['switch_text'].encode()).hexdigest()[:20];target=folder/('.switch-'+key+'.mp4')
        if target.is_file():return str(target)
        if not create:return ''
        if not c.FEATURES.native_root.is_dir():raise c.Error('Gemeinsamer Medienspeicher für das Umschaltbild fehlt.')
        folder.mkdir(exist_ok=True,mode=0o2770);text=folder/('.switch-'+secrets.token_hex(8)+'.txt');temp=folder/('.switch-'+secrets.token_hex(8)+'.mp4')
        try:
            text.write_text(user['switch_text']);command=['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=0x111827:s=1920x1080:r=30','-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-t','2','-vf','drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile='+str(text)+':expansion=none:fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2','-c:v','libx264','-profile:v','baseline','-preset','veryfast','-threads','1','-pix_fmt','yuv420p','-g','30','-bf','0','-c:a','aac','-ar','48000','-ac','2','-movflags','+faststart',str(temp)]
            subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60)
            import os
            os.chown(temp,-1,c.FEATURES.native_root.stat().st_gid);temp.chmod(0o640);temp.replace(target)
        except (OSError,subprocess.SubprocessError):raise c.Error('Umschaltbild konnte nicht erzeugt werden.') from None
        finally:text.unlink(missing_ok=True);temp.unlink(missing_ok=True)
        return str(target)
    def overlay(self,user):
        folder=self.c.DATA/'playout'/str(user['id']);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        key=hashlib.sha256(user['replay_label'].encode()).hexdigest()[:20];text=folder/('label-'+key+'.txt')
        if not text.exists():self.c.atomic(text,user['replay_label'])
        x='30' if user['replay_corner'].endswith('left') else 'w-text_w-30';y='30' if user['replay_corner'].startswith('top') else 'h-text_h-30'
        return 'drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:textfile='+str(text)+':expansion=none:fontsize=40:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=12:x='+x+':y='+y
    def twitch_call(self,user,method,body=None,segment=None):
        c=self.c;auth=c.rows('SELECT scopes FROM twitch_auth WHERE user_id=?',(user['id'],))
        if not auth or 'channel:manage:schedule' not in json.loads(auth[0]['scopes'] or '[]'):raise c.Error('Bitte Twitch erneut verbinden, um den Zeitplan freizugeben.')
        token,broadcaster=c.validated_twitch_token(user['id']);path='https://api.twitch.tv/helix/schedule/segment?'+c.urllib.parse.urlencode(dict(broadcaster_id=broadcaster,**({'id':segment} if segment else {})))
        return c.remote(path,json.dumps(body).encode() if body is not None else None,{'Authorization':'Bearer '+token,'Client-Id':c.setting('client_id'),'Content-Type':'application/json'},method)
    def sync_twitch(self):
        c=self.c
        if not c.SERVICES.enabled('automation') or not c.SERVICES.enabled('twitch'):return
        # Only segments created by StreamDesk are ever changed or removed.
        plans={r['id']:r for r in c.rows('SELECT * FROM stream_plans')}
        for segment in c.rows('SELECT * FROM twitch_plan_segments'):
            plan=plans.get(segment['plan_id'])
            if plan and plan['enabled'] and plan['sync_twitch'] and segment['day'] in json.loads(plan['days']):continue
            users=c.rows('SELECT * FROM users WHERE id=? AND active=1',(segment['user_id'],))
            if not users:continue
            try:self.twitch_call(users[0],'DELETE',segment=segment['segment_id']);c.write('DELETE FROM twitch_plan_segments WHERE user_id=? AND plan_id=? AND day=?',(segment['user_id'],segment['plan_id'],segment['day']))
            except c.Error:pass
        for plan in plans.values():
            if not plan['enabled'] or not plan['sync_twitch']:continue
            users=c.rows("SELECT * FROM users WHERE id=? AND active=1 AND role!='moderator'",(plan['user_id'],))
            if not users:continue
            user=users[0]
            try:
                for day in json.loads(plan['days']):
                    old=c.rows('SELECT * FROM twitch_plan_segments WHERE user_id=? AND plan_id=? AND day=?',(user['id'],plan['id'],day))
                    if old and old[0]['revision']==plan['revision']:continue
                    now=datetime.now(ZoneInfo(plan['timezone']));start=now.replace(hour=minute(plan['start'])//60,minute=minute(plan['start'])%60,second=0,microsecond=0)+timedelta(days=(day-now.weekday())%7)
                    if start<=now:start+=timedelta(days=7)
                    if start.astimezone(timezone.utc).astimezone(ZoneInfo(plan['timezone'])).hour!=start.hour:start+=timedelta(days=7)
                    body=dict(start_time=start.astimezone(timezone.utc).isoformat(),timezone=plan['timezone'],duration=str((minute(plan['end'])-minute(plan['start']))%1440 or 1440),title=plan['title'],is_recurring=True)
                    if old:
                        body.pop('is_recurring',None);self.twitch_call(user,'PATCH',body,old[0]['segment_id']);segment=old[0]['segment_id']
                    else:segment=self.twitch_call(user,'POST',body)['data']['segments'][0]['id']
                    c.write('INSERT INTO twitch_plan_segments(user_id,plan_id,day,segment_id,revision) VALUES (?,?,?,?,?) ON CONFLICT(user_id,plan_id,day) DO UPDATE SET segment_id=excluded.segment_id,revision=excluded.revision',(user['id'],plan['id'],day,segment,plan['revision']))
                c.write("UPDATE stream_plans SET sync_message='An Twitch übertragen.' WHERE id=? AND revision=?",(plan['id'],plan['revision']))
            except (c.Error,KeyError,IndexError) as exc:
                message=str(exc) if isinstance(exc,c.Error) else 'Twitch hat keine gültige Zeitplan-Antwort geliefert.'
                c.write('UPDATE stream_plans SET sync_message=? WHERE id=?',(message[:250],plan['id']))
    def background(self):
        c=self.c
        try:
            changed=False
            if c.FEATURES.native_root.is_dir() and self.can_switch_video():
                for user in c.rows("SELECT * FROM users WHERE active=1 AND role!='moderator'"):
                    if not self.switch_file(user):self.switch_file(user,create=True);changed=True
            if changed:
                with c.LOCK:c.reconcile()
            self.sync_twitch()
        except Exception:c.logging.exception('Studio-Hintergrundabgleich wird erneut versucht.')
    def tick(self):
        if time.monotonic()-self.last_sync>=60 and (not self.sync_worker or not self.sync_worker.is_alive()):
            self.last_sync=time.monotonic();self.sync_worker=self.c.threading.Thread(target=self.background,daemon=True);self.sync_worker.start()
