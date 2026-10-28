"""Tenant-owned media folders, resumable looping playlists and local-time playout rules."""
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import jsonify, request

TABLES = ('playlist_folders', 'playlists', 'playlist_profiles', 'playlist_positions', 'playlist_output_state')


def migrate(c):
    with c.db() as db:
        db.executescript('''
          CREATE TABLE IF NOT EXISTS playlist_folders(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,parent_id INTEGER);
          CREATE TABLE IF NOT EXISTS playlists(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,name TEXT NOT NULL,folder_id INTEGER,items TEXT NOT NULL DEFAULT '[]',revision INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS playlist_profiles(user_id INTEGER NOT NULL,scope TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,playlist_id INTEGER,delay_seconds INTEGER NOT NULL DEFAULT 600,timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',schedules TEXT NOT NULL DEFAULT '[]',auto_start INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(user_id,scope));
          CREATE TABLE IF NOT EXISTS playlist_positions(user_id INTEGER NOT NULL,program TEXT NOT NULL,playlist_id INTEGER NOT NULL,revision INTEGER NOT NULL,offset REAL NOT NULL DEFAULT 0,PRIMARY KEY(user_id,program,playlist_id));
          CREATE TABLE IF NOT EXISTS playlist_output_state(user_id INTEGER NOT NULL,kind TEXT NOT NULL,mode TEXT NOT NULL DEFAULT '',window TEXT NOT NULL DEFAULT '',blocked TEXT NOT NULL DEFAULT '',PRIMARY KEY(user_id,kind));
        ''')
        if 'folder_id' not in {row['name'] for row in db.execute('PRAGMA table_info(videos)')}:
            db.execute('ALTER TABLE videos ADD COLUMN folder_id INTEGER')
        if 'playlist_scope' not in {row['name'] for row in db.execute('PRAGMA table_info(routing_programs)')}:
            db.execute("ALTER TABLE routing_programs ADD COLUMN playlist_scope TEXT NOT NULL DEFAULT ''")


def minute(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
        raise ValueError('Zeit als HH:MM angeben (00:00 bis 23:59).')
    hour, mins = map(int, value.split(':'))
    return hour * 60 + mins


def intervals(rule):
    start, end = minute(rule['start']), minute(rule['end'])
    length = (end - start) % 1440 or 1440
    result = []
    for day in rule['days']:
        begin = day * 1440 + start
        finish = begin + length
        result.append((begin, min(finish, 10080)))
        if finish > 10080:
            result.append((0, finish - 10080))
    return result


def active_schedule(rules, timezone, stamp):
    local = datetime.fromtimestamp(stamp, ZoneInfo(timezone))
    value = local.weekday() * 1440 + local.hour * 60 + local.minute
    for rule in rules:
        if any(start <= value < end for start, end in intervals(rule)):
            day = local.date()
            if minute(rule['end']) <= minute(rule['start']) and local.hour * 60 + local.minute < minute(rule['start']):
                day -= timedelta(days=1)
            signature = hashlib.sha256(json.dumps(rule, sort_keys=True).encode()).hexdigest()[:12]
            return rule, signature + ':' + day.isoformat()
    return None, ''


class PlaylistFeatures:
    def __init__(self, c):
        self.c = c
        self.jobs = {}
        self.offline_since = {}
        self.last_checkpoint = {}
        self.retry = {}
        self.install_routes()

    def owned(self, table, user, ident):
        if type(ident) is not int:
            raise self.c.Error('Ungültige Kennung.', http_status=400)
        rows = self.c.rows('SELECT * FROM ' + table + ' WHERE id=? AND user_id=?', (ident, user['id']))
        if not rows:
            raise self.c.Error('Eintrag nicht gefunden.', http_status=404)
        return rows[0]

    def name(self, value):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 80 or any(ord(char) < 32 for char in value):
            raise self.c.Error('Bitte einen Namen mit 1–80 Zeichen eingeben.')
        return value.strip()

    def folder(self, user, value):
        if value is not None:
            self.owned('playlist_folders', user, value)
        return value

    def folder_tree(self, user, ident, parent):
        tree = {row['id']: row['parent_id'] for row in self.c.rows('SELECT * FROM playlist_folders WHERE user_id=?', (user['id'],))}
        tree[ident] = parent
        for node in tree:
            seen = set()
            while node is not None:
                if node in seen or len(seen) >= 8:
                    raise self.c.Error('Ordner dürfen keine Kreise bilden und höchstens acht Ebenen haben.')
                seen.add(node);node = tree.get(node)

    def unique(self, table, user, name, parent, ident=None):
        column = 'parent_id' if table == 'playlist_folders' else 'folder_id'
        for row in self.c.rows('SELECT * FROM ' + table + ' WHERE user_id=?', (user['id'],)):
            if row['id'] != ident and row[column] == parent and row['name'].casefold() == name.casefold():
                raise self.c.Error('Dieser Name ist in diesem Ordner bereits vergeben.', http_status=409)

    def videos(self, user, items):
        if not isinstance(items, list) or len(items) > 200 or any(type(vid) is not int for vid in items):
            raise self.c.Error('Eine Playlist darf höchstens 200 Videoeinträge enthalten.')
        result = []
        for vid in items:
            row = self.owned('videos', user, vid)
            path = Path(row['rendered'] or row['path'])
            root = self.c.DATA / 'media' / user['username']
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise self.c.Error('Ein Video ist nicht mehr verfügbar.', http_status=409)
            if not math.isfinite(row['duration']) or row['duration'] <= 0:
                raise self.c.Error('Die Videolänge wird noch ermittelt. Bitte danach erneut speichern.', http_status=409)
            result.append(dict(row, file=str(path.resolve())))
        return result

    def video_referenced(self, user, vid, active_only=False):
        if any(job['user_id'] == user['id'] and vid in job['items'] for job in self.jobs.values()):
            return True
        return not active_only and any(vid in json.loads(row['items']) for row in self.c.rows('SELECT items FROM playlists WHERE user_id=?', (user['id'],)))

    def assigned_ids(self,user):
        result=set()
        for row in self.c.rows('SELECT playlist_id,schedules FROM playlist_profiles WHERE user_id=?',(user['id'],)):
            if row['playlist_id'] is not None:result.add(row['playlist_id'])
            result.update(rule['playlist_id'] for rule in json.loads(row['schedules']))
        return result

    def media_details(self,user,videos):
        playlists=self.c.rows('SELECT id,name,items FROM playlists WHERE user_id=?',(user['id'],))
        assigned=self.assigned_ids(user)
        active={ident for job in list(self.jobs.values()) if job['user_id']==user['id'] for ident in job['items']}
        for video in videos:
            uses=[row for row in playlists if video['id'] in json.loads(row['items'])]
            reason=''
            if video['id']==user['selected_video_id']:reason='Aktuelles Offline-Video: zuerst ein anderes Video auswählen.'
            elif video['id'] in active:reason='In einer laufenden Playlist: Wiedergabe zuerst pausieren.'
            elif any(row['id'] in assigned and not any(ident!=video['id'] for ident in json.loads(row['items'])) for row in uses):reason='Letztes Video einer zugeordneten Playlist: zuerst die Ausspielregel anpassen.'
            elif user['upload_state'] in ('queued','processing') and not user.get('upload_id'):reason='Videoverarbeitung läuft: bitte deren Abschluss abwarten.'
            video.update(in_playlists=[row['name'] for row in uses],can_delete=not bool(reason),delete_reason=reason)
        return videos

    def public(self, user):
        videos=self.c.rows('SELECT id,name,duration,size,folder_id FROM videos WHERE user_id=? ORDER BY name,id',(user['id'],))
        return dict(folders=self.c.rows('SELECT * FROM playlist_folders WHERE user_id=? ORDER BY name,id', (user['id'],)),
                    playlists=[dict(row, items=json.loads(row['items'])) for row in self.c.rows('SELECT * FROM playlists WHERE user_id=? ORDER BY name,id', (user['id'],))],
                    videos=self.media_details(user,videos))

    def scope(self, user, value):
        if value == 'default':return value
        if not isinstance(value, str):raise self.c.Error('Ungültiger Geltungsbereich.')
        if value.startswith('source:'):
            source = self.c.MODEL.source(user, value[7:])
            if source['key'] == 'source1':raise self.c.Error('Source 1 bleibt ausschließlich der feste Live-Eingang.')
            if not source['fixed']:self.c.SERVICES.require('advanced_routing')
            return value
        if value.startswith('output:') and value[7:] in self.c.output_kinds(user):
            self.c.SERVICES.require_output(value[7:])
            return value
        raise self.c.Error('Quelle oder Ausgang nicht gefunden.', http_status=404)

    def validate_rules(self, user, rules):
        if not isinstance(rules, list) or len(rules) > 50:raise self.c.Error('Maximal 50 Zeitfenster pro Regelbereich.')
        occupied, result = [], []
        for rule in rules:
            if not isinstance(rule, dict):raise self.c.Error('Ungültiges Zeitfenster.')
            self.owned('playlists', user, rule.get('playlist_id'))
            self.videos(user, json.loads(self.owned('playlists', user, rule['playlist_id'])['items']))
            days = rule.get('days', list(range(7)))
            if not isinstance(days, list) or not days or any(type(day) is not int or day not in range(7) for day in days) or len(days) != len(set(days)):
                raise self.c.Error('Bitte gültige Wochentage auswählen.')
            item = dict(playlist_id=rule['playlist_id'], start=rule.get('start'), end=rule.get('end'), days=sorted(days))
            try:segments = intervals(item)
            except (ValueError, TypeError):raise self.c.Error('Zeit als HH:MM angeben (00:00 bis 23:59).') from None
            for start, end in segments:
                if any(start < right and end > left for left, right in occupied):
                    raise self.c.Error('Zeitfenster dürfen sich im selben Regelbereich nicht überschneiden.', http_status=409)
            occupied.extend(segments);result.append(item)
        return result

    def install_routes(self):
        c = self.c
        @c.app.get('/api/playlists', endpoint='playlist_library')
        @c.login_required
        def library(user):return jsonify(**self.public(user))

        @c.app.post('/api/playlist-folders')
        @c.login_required
        def create_folder(user):
            body = c.FEATURES.body()
            with c.LOCK:
                if len(c.rows('SELECT id FROM playlist_folders WHERE user_id=?', (user['id'],))) >= 100:raise c.Error('Maximal 100 Ordner pro Benutzer.')
                name, parent = self.name(body.get('name')), self.folder(user, body.get('parent_id'))
                self.folder_tree(user, -1, parent);self.unique('playlist_folders', user, name, parent)
                ident = c.write('INSERT INTO playlist_folders(user_id,name,parent_id) VALUES (?,?,?)', (user['id'], name, parent))
            return jsonify(ok=True, id=ident)

        @c.app.route('/api/playlist-folders/<int:ident>', methods=['POST', 'DELETE'])
        @c.login_required
        def update_folder(user, ident):
            with c.LOCK:
                self.owned('playlist_folders', user, ident)
                if request.method == 'DELETE':
                    occupied = any(c.rows('SELECT id FROM '+table+' WHERE user_id=? AND '+column+'=?', (user['id'], ident)) for table, column in (('playlist_folders', 'parent_id'), ('playlists', 'folder_id'), ('videos', 'folder_id')))
                    if occupied:raise c.Error('Bitte den Ordner zuerst leeren.', http_status=409)
                    c.write('DELETE FROM playlist_folders WHERE id=? AND user_id=?', (ident, user['id']))
                else:
                    body = c.FEATURES.body();name, parent = self.name(body.get('name')), self.folder(user, body.get('parent_id'))
                    self.folder_tree(user, ident, parent);self.unique('playlist_folders', user, name, parent, ident)
                    c.write('UPDATE playlist_folders SET name=?,parent_id=? WHERE id=? AND user_id=?', (name, parent, ident, user['id']))
            return jsonify(ok=True)

        @c.app.post('/api/playlists')
        @c.login_required
        def create_playlist(user):
            body = c.FEATURES.body()
            with c.LOCK:
                if len(c.rows('SELECT id FROM playlists WHERE user_id=?', (user['id'],))) >= 100:raise c.Error('Maximal 100 Playlists pro Benutzer.')
                name, folder = self.name(body.get('name')), self.folder(user, body.get('folder_id'))
                items = body.get('items', []);self.videos(user, items);self.unique('playlists', user, name, folder)
                ident = c.write('INSERT INTO playlists(user_id,name,folder_id,items) VALUES (?,?,?,?)', (user['id'], name, folder, json.dumps(items)))
            return jsonify(ok=True, id=ident)

        @c.app.route('/api/playlists/<int:ident>', methods=['POST', 'DELETE'])
        @c.login_required
        def update_playlist(user, ident):
            with c.LOCK:
                row = self.owned('playlists', user, ident)
                if request.method == 'DELETE':
                    if any(job['playlist_id'] == ident and job['user_id'] == user['id'] for job in self.jobs.values()):raise c.Error('Diese Playlist wird gerade gesendet.', http_status=409)
                    for profile in c.rows('SELECT * FROM playlist_profiles WHERE user_id=?', (user['id'],)):
                        if profile['playlist_id'] == ident or any(rule['playlist_id'] == ident for rule in json.loads(profile['schedules'])):
                            raise c.Error('Bitte die Playlist zuerst aus Ausspielregeln und Zeitplänen entfernen.', http_status=409)
                    c.write('DELETE FROM playlists WHERE id=? AND user_id=?', (ident, user['id']))
                    c.write('DELETE FROM playlist_positions WHERE user_id=? AND playlist_id=?', (user['id'], ident))
                else:
                    body = c.FEATURES.body();name, folder = self.name(body.get('name')), self.folder(user, body.get('folder_id'))
                    items = body.get('items', []);self.videos(user, items);self.unique('playlists', user, name, folder, ident)
                    if not items and any(profile['playlist_id'] == ident or any(rule['playlist_id'] == ident for rule in json.loads(profile['schedules'])) for profile in c.rows('SELECT * FROM playlist_profiles WHERE user_id=?',(user['id'],))):
                        raise c.Error('Eine zugeordnete Playlist darf nicht leer gespeichert werden.', http_status=409)
                    c.write('UPDATE playlists SET name=?,folder_id=?,items=?,revision=revision+? WHERE id=? AND user_id=?',
                            (name, folder, json.dumps(items), int(items != json.loads(row['items'])), ident, user['id']))
            return jsonify(ok=True)

        @c.app.post('/api/playlists/videos/<int:ident>/folder')
        @c.login_required
        def move_video(user, ident):
            with c.LOCK:
                self.owned('videos', user, ident);parent = self.folder(user, c.FEATURES.body().get('folder_id'))
                c.write('UPDATE videos SET folder_id=? WHERE id=? AND user_id=?', (parent, ident, user['id']))
            return jsonify(ok=True)

        @c.app.post('/api/playlists/upload', endpoint='playlist_upload')
        @c.login_required
        def upload(user):
            raw = request.form.get('folder_id', '')
            try:folder = int(raw) if raw else None
            except ValueError:raise c.Error('Ungültiger Ordner.') from None
            self.folder(user, folder)
            return c.accept_upload(user, max_duration=7200, folder_id=folder)

        @c.app.get('/api/playout')
        @c.login_required
        @c.expert_required
        def profiles(user):
            return jsonify(profiles=[dict(row, schedules=json.loads(row['schedules']), enabled=bool(row['enabled']), auto_start=bool(row['auto_start'])) for row in c.rows('SELECT * FROM playlist_profiles WHERE user_id=?', (user['id'],))],
                           sources=c.MODEL.public_sources(user), outputs=[{'kind':kind, 'label':next((row.get('label') or {'twitch':'Twitch','youtube':'YouTube','custom':'Eigener Anbieter'}.get(kind,kind) for row in c.destinations(user) if row['kind']==kind), {'twitch':'Twitch','youtube':'YouTube','custom':'Eigener Anbieter'}.get(kind,kind))} for kind in c.output_kinds(user)], timezones=['Europe/Berlin', 'UTC'])

        @c.app.post('/api/playout')
        @c.login_required
        @c.expert_required
        def save_profile(user):
            body = c.FEATURES.body()
            with c.LOCK:
                scope = self.scope(user, body.get('scope'))
                enabled, auto = c.FEATURES.boolean(body, 'enabled'), c.FEATURES.boolean(body, 'auto_start')
                delay = body.get('delay_seconds', 600)
                if type(delay) is not int or not 0 <= delay <= 86400:raise c.Error('Verzögerung zwischen 0 und 1440 Minuten wählen.')
                zone = body.get('timezone', 'Europe/Berlin')
                try:
                    if not isinstance(zone, str) or len(zone) > 80:raise ValueError()
                    ZoneInfo(zone)
                except (ZoneInfoNotFoundError, ValueError):raise c.Error('Ungültige Zeitzone.') from None
                rules = self.validate_rules(user, body.get('schedules', []))
                if rules or auto:c.SERVICES.require('automation')
                ident = body.get('playlist_id')
                if ident is not None:
                    row = self.owned('playlists', user, ident)
                    if not self.videos(user, json.loads(row['items'])):raise c.Error('Eine leere Playlist kann nicht ausgespielt werden.')
                for rule in rules:
                    if not json.loads(self.owned('playlists', user, rule['playlist_id'])['items']):raise c.Error('Eine leere Playlist kann nicht eingeplant werden.')
                previous = c.rows('SELECT * FROM playlist_profiles WHERE user_id=? AND scope=?', (user['id'], scope))
                if scope.startswith('output:') and not previous:c.FEATURES.routing.stopped(user, scope[7:])
                with c.FEATURES.routing.change(user):
                    c.write('''INSERT INTO playlist_profiles(user_id,scope,enabled,playlist_id,delay_seconds,timezone,schedules,auto_start)
                            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,scope) DO UPDATE SET enabled=excluded.enabled,playlist_id=excluded.playlist_id,
                            delay_seconds=excluded.delay_seconds,timezone=excluded.timezone,schedules=excluded.schedules,auto_start=excluded.auto_start,revision=playlist_profiles.revision+1''',
                            (user['id'], scope, int(enabled), ident, delay, zone, json.dumps(rules), int(auto)))
                    if scope.startswith('output:'):c.MODEL.save_route(user, scope[7:], c.MODEL.route(user, scope[7:]))
            return jsonify(ok=True)

    def plan(self, user, program, stamp=None):
        if not self.c.SERVICES.enabled('playlists'):return None
        scopes = [program.get('playlist_scope')] + ['source:'+key for key in program['sources'] if key != 'source1'] + ['default']
        for scope in filter(None, scopes):
            rows = self.c.rows('SELECT * FROM playlist_profiles WHERE user_id=? AND scope=? AND enabled=1', (user['id'], scope))
            if not rows:continue
            row = rows[0];rule, window = (None, '')
            if self.c.SERVICES.enabled('automation'):
                rule, window = active_schedule(json.loads(row['schedules']), row['timezone'], stamp if stamp is not None else time.time())
            ident = rule['playlist_id'] if rule else row['playlist_id']
            if ident is None:return None
            found = self.c.rows('SELECT * FROM playlists WHERE user_id=? AND id=?', (user['id'], ident))
            if not found:return None
            playlist = found[0]
            return dict(profile=row, playlist=playlist, scheduled=bool(rule), window=('s:'+scope+':'+window) if rule else 'f:'+scope+':'+str(row['revision']),
                        delay=0 if rule else row['delay_seconds'], auto=bool(row['auto_start']) and self.c.SERVICES.enabled('automation'))
        return None

    def decision(self, user, program, live, demand, now):
        key = (user['id'], program['id']);plan = self.plan(user, program)
        if live or not demand and not (plan and plan['auto']):self.offline_since.pop(key, None)
        else:self.offline_since.setdefault(key, now)
        age = now - self.offline_since.get(key, now)
        eligible = plan and not live and (plan['scheduled'] or age >= plan['delay'])
        return plan, bool(eligible)

    def automatic(self, user, program, plan, eligible, config, now, live=False):
        with self.c.LOCK:
            fresh = self.plan(user, program)
            if (fresh or {}).get('window') != (plan or {}).get('window'):
                return
            return self._automatic(user, program, plan, eligible, config, now, live)

    def _automatic(self, user, program, plan, eligible, config, now, live=False):
        c = self.c
        for kind in program['targets']:
            rows = c.rows('SELECT * FROM playlist_output_state WHERE user_id=? AND kind=?', (user['id'], kind))
            state = rows[0] if rows else dict(mode='', window='', blocked='')
            configured = next((row for row in c.destinations(user) if row['kind'] == kind), None)
            selected = configured and configured['endpoint'] and (configured['selected'] or plan and plan['profile']['scope'].startswith('output:'))
            desired = plan and plan['auto'] and selected and c.SERVICES.output_allowed(kind)
            window = plan['window'] if plan else ''
            running = bool(config['paths'].get(c.output_path(user, kind), {}).get('forward'))
            if running and state['mode'] and live and c.SERVICES.enabled('playlists') and c.SERVICES.enabled('automation') and c.SERVICES.output_allowed(kind):
                continue  # A returning live streamer keeps the output even beyond the playlist window.
            keep_fallback_live = desired and state['mode'] == 'fallback' and state['window'] == window
            wanted = desired and (plan['scheduled'] or eligible or keep_fallback_live)
            try:
                if state['mode'] and not wanted:
                    if running:c.forward(user, False, kind=kind, origin='playlist')
                    c.write("UPDATE playlist_output_state SET mode='',blocked=?,window='' WHERE user_id=? AND kind=?", (state['window'], user['id'], kind))
                    config['paths'][c.output_path(user, kind)]['forward'] = []
                elif wanted and not running and state['blocked'] != window and now >= self.retry.get((user['id'], kind), 0):
                    c.forward(user, True, kind=kind, origin='playlist')
                    c.write('''INSERT INTO playlist_output_state(user_id,kind,mode,window) VALUES (?,?,?,?) ON CONFLICT(user_id,kind) DO UPDATE SET mode=excluded.mode,window=excluded.window''',
                            (user['id'], kind, 'schedule' if plan['scheduled'] else 'fallback', window))
                    config['paths'][c.output_path(user, kind)]['forward'] = c.configured_forwards(user)[c.output_path(user, kind)]
                elif wanted and state['mode']:
                    c.write('UPDATE playlist_output_state SET window=? WHERE user_id=? AND kind=?', (window, user['id'], kind))
            except (c.Error, OSError):
                self.retry[(user['id'], kind)] = now + 30
                c.logging.warning('Automatischer Playlist-Ausgang %s konnte nicht geändert werden (Benutzer %s).', kind, user['id'])

    def manual_control(self, user, kind=None):
        for target in [kind] if kind else self.c.output_kinds(user):
            plan = self.plan(user, self.c.MODEL.output_program(user, target))
            self.c.write('''INSERT INTO playlist_output_state(user_id,kind,blocked) VALUES (?,?,?) ON CONFLICT(user_id,kind) DO UPDATE SET mode='',window='',blocked=excluded.blocked''',
                         (user['id'], target, plan['window'] if plan else ''))

    def start(self, user, program, plan):
        c = self.c;playlist = plan['playlist'];key = (user['id'], program['id'])
        videos = self.videos(user, json.loads(playlist['items']))
        if not videos:raise c.Error('Die Playlist enthält keine verfügbaren Videos.')
        total = sum(row['duration'] for row in videos)
        saved = c.rows('SELECT * FROM playlist_positions WHERE user_id=? AND program=? AND playlist_id=?', (user['id'], program['id'], playlist['id']))
        offset = saved[0]['offset'] % total if saved and saved[0]['revision'] == playlist['revision'] else 0
        folder = c.DATA / 'playout' / str(user['id']);folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest = folder / (program['id']+'.ffconcat');progress = folder / (program['id']+'.progress')
        def quote(value):return value.replace("'", "'\\''")
        c.atomic(manifest, 'ffconcat version 1.0\n'+''.join("file '"+quote(row['file'])+"'\nduration "+format(row['duration'], '.6f')+'\n' for row in videos))
        progress.unlink(missing_ok=True)
        self.jobs[key] = dict(user_id=user['id'], program=program['id'], playlist_id=playlist['id'], revision=playlist['revision'],
                              offset=offset, total=total, scheduled=plan['scheduled'], progress=progress, manifest=manifest, items=[row['id'] for row in videos], videos=videos, name=playlist['name'])
        return ['-re', '-stream_loop', '-1', '-f', 'concat', '-safe', '0', '-protocol_whitelist', 'file,pipe', '-ss', format(offset, '.6f'), '-i', str(manifest)], ['-progress', str(progress), '-stats_period', '0.25']

    def position(self, job):
        elapsed = 0
        try:
            with job['progress'].open('rb') as stream:
                stream.seek(max(0, stream.seek(0, 2)-8192));data = stream.read().decode('utf-8', 'replace')
            values = re.findall(r'^out_time_us=(\d+)$', data, re.M)
            if values:elapsed = int(values[-1]) / 1_000_000
        except OSError:pass
        return (job['offset'] + elapsed) % job['total']

    def checkpoint(self, key, pause=False):
        key = (key, 'main') if isinstance(key, int) else key
        job = self.jobs.get(key)
        if not job:return
        now = time.monotonic()
        if pause or now - self.last_checkpoint.get(key, -10) >= 2:
            self.c.write('''INSERT INTO playlist_positions(user_id,program,playlist_id,revision,offset) VALUES (?,?,?,?,?) ON CONFLICT(user_id,program,playlist_id) DO UPDATE SET revision=excluded.revision,offset=excluded.offset''',
                         (job['user_id'], job['program'], job['playlist_id'], job['revision'], self.position(job)))
            self.last_checkpoint[key] = now
        if pause:
            self.jobs.pop(key, None);job['progress'].unlink(missing_ok=True);job['manifest'].unlink(missing_ok=True)

    def describe(self, key, plan, live):
        key = (key, 'main') if isinstance(key, int) else key
        job = self.jobs.get(key)
        if not job:
            return dict(active=False, paused=bool(live and plan), name=plan['playlist']['name'] if plan else '', video='', offset=0)
        offset = self.position(job);remaining = offset
        video = job['videos'][-1]
        for row in job['videos']:
            video = row
            if remaining < row['duration']:break
            remaining -= row['duration']
        return dict(active=True, paused=False, name=job['name'], video=video['name'], offset=round(offset, 2), total=round(job['total'], 2), item_offset=round(remaining, 2))
