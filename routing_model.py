"""Owned sources, per-output eligibility and stable shared program identities."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import yaml
from media_config import list_items


DEFAULT_SOURCES = (
    {'key':'source1', 'label':'Source 1 · OBS', 'protocol':'rtmp', 'priority':1, 'fixed':True, 'enabled':True},
    {'key':'source2', 'label':'Source 2 · Handy', 'protocol':'srt', 'priority':2, 'fixed':True, 'enabled':True},
)
DEFAULT_KEYS = ['source1', 'source2']
MAX_SOURCES = 10
MAX_OUTPUTS = 10


def owner(key):
    return key[0] if isinstance(key, tuple) else key


def job_key(user, program):
    return user['id'] if program == 'main' else (user['id'], program)


def program_id(sources, playlist_scope=""):
    members = sorted(set(sources))
    if members == DEFAULT_KEYS and not playlist_scope:
        return 'main'
    value = [members, playlist_scope] if playlist_scope else members
    return 'route-' + hashlib.sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()[:12]


class RoutingModel:
    def __init__(self, core):
        self.c = core

    def migrate(self):
        c = self.c
        with c.db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS routing_sources(
                  user_id INTEGER NOT NULL, key TEXT NOT NULL, ordinal INTEGER NOT NULL,
                  label TEXT NOT NULL, protocol TEXT NOT NULL, endpoint TEXT NOT NULL DEFAULT '',
                  priority INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, deleted INTEGER NOT NULL DEFAULT 0,
                  source_on_demand INTEGER NOT NULL DEFAULT 0,
                  PRIMARY KEY(user_id,key), UNIQUE(user_id,ordinal));
                CREATE TABLE IF NOT EXISTS output_routing(
                  user_id INTEGER NOT NULL, kind TEXT NOT NULL, sources TEXT NOT NULL,
                  PRIMARY KEY(user_id,kind));
                CREATE TABLE IF NOT EXISTS routing_programs(
                  user_id INTEGER NOT NULL, id TEXT NOT NULL, sources TEXT NOT NULL,
                  PRIMARY KEY(user_id,id));
                CREATE TABLE IF NOT EXISTS routing_policy(
                  user_id INTEGER PRIMARY KEY, healthy_seconds REAL NOT NULL DEFAULT 3,
                  stall_seconds REAL NOT NULL DEFAULT 5, retry_seconds REAL NOT NULL DEFAULT 10,
                  native_standby INTEGER NOT NULL DEFAULT 0);
            ''')
            source_columns = {row['name'] for row in connection.execute('PRAGMA table_info(routing_sources)')}
            if 'source_on_demand' not in source_columns:
                connection.execute('ALTER TABLE routing_sources ADD COLUMN source_on_demand INTEGER NOT NULL DEFAULT 0')
            if connection.execute("SELECT value FROM settings WHERE name='routing_model_v1'").fetchone():
                return
        config = yaml.safe_load(c.CONFIG.read_text()) or {}
        online = set()
        online_known = os.getenv('STREAMDESK_ENGINE','1')!='1'
        if os.getenv('STREAMDESK_ENGINE', '1') == '1':
            for attempt in range(3):
                try:
                    online = {row['name'] for row in list_items(c.mtx,'paths/list') if row.get('online')}
                    online_known = True
                    break
                except c.Error:
                    if attempt<2:
                        time.sleep(.2)
        native = Path(os.getenv('STREAMDESK_NATIVE_ROOT', str(c.DATA.parent / (c.DATA.name+'-native'))))
        config_changed = False
        with c.db() as connection:
            for user in connection.execute('SELECT * FROM users').fetchall():
                keys = list(DEFAULT_KEYS)
                path = user['prefix']+'source3'
                folder = native / user['username'] / path
                recorded = connection.execute("SELECT 1 FROM recordings WHERE user_id=? AND source='source3' LIMIT 1", (user['id'],)).fetchone()
                keep = (path in online or not online_known and path in config.get('paths',{})
                        or user['source_mode']=='source3' or user['source3_protocol']!='srt' or recorded
                        or config.get('paths', {}).get(path, {}).get('record')
                        or folder.is_dir() and any(folder.glob('*')))
                if keep:
                    connection.execute('INSERT OR IGNORE INTO routing_sources(user_id,key,ordinal,label,protocol,priority) VALUES (?,?,?,?,?,3)',
                                       (user['id'],'source3',3,'Source 3',user['source3_protocol']))
                    keys.append('source3')
                if user['pull_url']:
                    ordinal = len(keys)+1
                    connection.execute('INSERT OR IGNORE INTO routing_sources(user_id,key,ordinal,label,protocol,endpoint,priority,enabled) VALUES (?,?,?,?,?,?,?,?)',
                                       (user['id'],'pull',ordinal,'RTSP-Pull','rtsp',user['pull_url'],ordinal,user['pull_enabled']))
                    keys.append('pull')
                # Preserve actual configured rc.4/rc.5 routing; unused implicit Source 3 disappears.
                for kind in c.output_kinds(user):
                    connection.execute('INSERT OR IGNORE INTO output_routing(user_id,kind,sources) VALUES (?,?,?)',
                                       (user['id'],kind,json.dumps(keys)))
                pid = program_id(keys)
                if pid != 'main':
                    connection.execute('INSERT OR IGNORE INTO routing_programs(user_id,id,sources) VALUES (?,?,?)',
                                       (user['id'],pid,json.dumps(keys)))
                    previous_program = config.get('paths',{}).get(user['prefix']+'live',{})
                    if previous_program.get('record'):
                        config['paths'][user['prefix']+pid] = dict(previous_program)
                        previous_program['record'] = False
                        config_changed = True
                connection.execute("UPDATE users SET source_mode='auto' WHERE id=?", (user['id'],))
            if config_changed:
                c.atomic(c.CONFIG,yaml.safe_dump(config,sort_keys=False,allow_unicode=True))
            connection.execute("INSERT INTO settings(name,value) VALUES ('routing_model_v1','1')")

    def sources(self, user, archived=False):
        extra = self.c.rows('SELECT * FROM routing_sources WHERE user_id=?'+('' if archived else ' AND deleted=0'), (user['id'],))
        result = [dict(row, source_on_demand=False) for row in DEFAULT_SOURCES]
        result += [dict(row, fixed=False, enabled=bool(row['enabled']) and not row['deleted']) for row in extra]
        return sorted(result, key=lambda row:(row['priority'], row.get('ordinal', row['priority'])))

    def source(self, user, key, archived=False):
        result = next((row for row in self.sources(user, archived) if row['key']==key), None)
        if result is None:
            raise self.c.Error('Quelle nicht gefunden.', http_status=404)
        return result

    def public_sources(self, user):
        return [{key:row[key] for key in ('key','label','protocol','priority','fixed','enabled','source_on_demand')} for row in self.sources(user)]

    def policy(self, user):
        rows = self.c.rows('SELECT * FROM routing_policy WHERE user_id=?', (user['id'],))
        return rows[0] if rows else {'user_id':user['id'], 'healthy_seconds':3, 'stall_seconds':5,
                                     'retry_seconds':10, 'native_standby':0}

    def save_policy(self, user, healthy, stall, retry, native_standby):
        self.c.write('''INSERT INTO routing_policy(user_id,healthy_seconds,stall_seconds,retry_seconds,native_standby)
                        VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                        healthy_seconds=excluded.healthy_seconds,stall_seconds=excluded.stall_seconds,
                        retry_seconds=excluded.retry_seconds,native_standby=excluded.native_standby''',
                     (user['id'],healthy,stall,retry,int(native_standby)))

    def route(self, user, kind):
        result = self.c.rows('SELECT sources FROM output_routing WHERE user_id=? AND kind=?', (user['id'],kind))
        return json.loads(result[0]['sources']) if result else list(DEFAULT_KEYS) if kind in self.c.OUTPUT_KINDS else []

    def save_route(self, user, kind, sources):
        c = self.c
        if kind not in c.output_kinds(user):
            raise c.Error('Ausgang nicht gefunden.', http_status=404)
        if not isinstance(sources, list) or any(not isinstance(key,str) for key in sources) or len(sources)!=len(set(sources)):
            raise c.Error('Ungültige Quellenzuordnung.')
        allowed = {row['key'] for row in self.sources(user)}
        if any(key not in allowed for key in sources):
            raise c.Error('Die Zuordnung enthält eine fremde oder gelöschte Quelle.', http_status=404)
        canonical = sorted(sources)
        scope = self.playlist_scope(user, kind)
        pid = program_id(canonical, scope)
        with c.db() as connection:
            connection.execute('INSERT INTO output_routing(user_id,kind,sources) VALUES (?,?,?) ON CONFLICT(user_id,kind) DO UPDATE SET sources=excluded.sources',
                               (user['id'],kind,json.dumps(canonical)))
            if pid != 'main':
                connection.execute('INSERT OR IGNORE INTO routing_programs(user_id,id,sources,playlist_scope) VALUES (?,?,?,?)',
                                   (user['id'],pid,json.dumps(canonical),scope))
        return pid

    def playlist_scope(self, user, kind):
        return 'output:'+kind if self.c.rows('SELECT 1 FROM playlist_profiles WHERE user_id=? AND scope=?',(user['id'],'output:'+kind)) else ''

    def programs(self, user, archived=False):
        definitions = {'main':list(DEFAULT_KEYS)}
        scopes = {'main':''}
        for row in self.c.rows('SELECT id,sources,playlist_scope FROM routing_programs WHERE user_id=?', (user['id'],)):
            definitions[row['id']] = json.loads(row['sources'])
            scopes[row['id']] = row['playlist_scope']
        targets = {}
        for kind in self.c.output_kinds(user):
            sources = self.route(user, kind)
            scope = self.playlist_scope(user, kind)
            pid = program_id(sources, scope)
            scopes[pid] = scope
            # New, not-yet-assigned outputs share a silent empty program until configured.
            definitions[pid] = sources
            targets.setdefault(pid, []).append(kind)
        catalog = self.sources(user, archived)
        result = []
        for pid, members in definitions.items():
            active = pid == 'main' or pid in targets
            if not archived and not active:
                continue
            result.append({'id':pid,'playlist_scope':scopes.get(pid,''),'sources':[row['key'] for row in catalog if row['key'] in members],
                           'path':user['prefix']+('live' if pid=='main' else pid),
                           'rtc_path':user['prefix']+('webrtc-program' if pid=='main' else 'webrtc-'+pid),
                           'targets':targets.get(pid, []),'active':active})
        return result

    def program(self, user, pid='main', archived=False):
        result = next((row for row in self.programs(user, archived) if row['id']==pid), None)
        if result is None:
            raise self.c.Error('Programm nicht gefunden.', http_status=404)
        return result

    def output_program(self, user, kind):
        return self.program(user, program_id(self.route(user,kind), self.playlist_scope(user,kind)))

    def active_record_sources(self,user):
        return [row['key'] for row in self.sources(user)]+['live']+[row['id'] for row in self.programs(user) if row['id']!='main']

    def record_sources(self, user):
        return [row['key'] for row in self.sources(user, True)] + ['live'] + [row['id'] for row in self.programs(user, True) if row['id']!='main']

    def source_label(self,user,key):
        if key=='live':
            return 'Standardprogramm'
        catalog = {row['key']:row['label'] for row in self.sources(user,True)}
        if key in catalog:
            return catalog[key]
        program = next((row for row in self.programs(user,True) if row['id']==key),None)
        if not program:
            return key
        if not program['sources']:
            return 'Programm · noch ohne Quelle'
        outputs = {row['kind']:row.get('label') or row['kind'] for row in self.c.destinations(user)}
        labels = [outputs[kind] for kind in program['targets'] if kind in outputs]
        return 'Programm · '+(' + '.join(labels) if labels else ' → '.join(catalog.get(source,source) for source in program['sources']))

    def record_path(self, user, source):
        if source not in self.record_sources(user):
            raise self.c.Error('Aufnahmequelle nicht gefunden.', http_status=404)
        return user['prefix']+source

    def is_program(self, source):
        return source=='live' or bool(re.fullmatch(r'route-[a-f0-9]{12}', source))
