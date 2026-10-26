import concurrent.futures
import functools
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import pwd
import sys
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from cryptography.fernet import Fernet
from flask import Flask, request, session, jsonify, render_template, redirect, Response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask.sessions import SecureCookieSessionInterface
import yaml
from media_config import list_items

DATA = Path(os.getenv('STREAMDESK_DATA', '/var/lib/streamdesk'))
CONFIG = Path(os.getenv('MEDIAMTX_CONFIG', '/opt/mediamtx/mediamtx.yml'))
API = os.getenv('MEDIAMTX_API', 'http://127.0.0.1:9997/v3/')
HLS = os.getenv('MEDIAMTX_HLS', 'http://127.0.0.1:8888/')
PUBLIC = os.getenv('STREAMDESK_PUBLIC', 'http://localhost:8080').rstrip('/')
HOST = os.getenv('STREAMDESK_INGEST', '127.0.0.1')
DEFAULT_CLIP = Path(os.getenv('STREAMDESK_DEFAULT_CLIP', str(DATA / 'standby.mp4')))
RTSP = os.getenv('MEDIAMTX_RTSP', 'rtsp://127.0.0.1:8554/').rstrip('/') + '/'
RTMP_PORT = int(os.getenv('MEDIAMTX_RTMP_PORT', '1935'))
SRT_PORT = int(os.getenv('MEDIAMTX_SRT_PORT', '8890'))
NAMESPACE = os.getenv('STREAMDESK_NAMESPACE', 'streamdesk')
if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', NAMESPACE):
    raise RuntimeError('Ungültiger StreamDesk-Namensbereich')
LOCAL_IPS = [p.strip() for p in os.getenv('STREAMDESK_LOCAL_IPS', '127.0.0.1,::1').split(',') if p.strip()]
BROWSER_ROOT = Path(os.getenv('STREAMDESK_BROWSER_ROOT', '/var/lib/streamdesk-browser'))
BROWSER_USER = os.getenv('STREAMDESK_BROWSER_USER', 'streamdesk-browser')
TRUST_PROXY = os.getenv('STREAMDESK_TRUST_PROXY', '0') == '1'
TWITCH = 'rtmps://ingest.global-contribute.live-video.net/app'
STANDBY_TRACKS = [{'codec': 'H264'}, {'codec': 'MPEG4Audio', 'sampleRate': 48000, 'channelCount': 2}]
UPLOAD_LIMIT = 500 * 1024 * 1024
UPLOAD_RESERVATIONS = {}
TEXT_DEFAULTS = {'x': 50, 'y': 93, 'size': 42, 'color': '#ffffff', 'background': '#000000', 'opacity': 65, 'bold': False, 'box': True}
RENEW_INTERVALS = {0, 300, 600, 1800, 43200, 86400, 129600, 172800}
LOCK = threading.RLock()
JOBS = concurrent.futures.ThreadPoolExecutor(max_workers=1)
READY = threading.Event()
OAUTH_LOCK = threading.RLock()
APP_TOKEN = {}
CHAT_SCOPES = {'user:read:chat', 'user:write:chat'}
TWITCH_SCOPES = {'channel:read:stream_key', 'channel:manage:broadcast'}
_DUMMY_PASSWORD_HASH = generate_password_hash('streamdesk-timing-dummy')
app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=501 * 1024 * 1024, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1')
if TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)


class CookiePolicy(SecureCookieSessionInterface):
    def get_cookie_secure(self, application):
        return request.is_secure or application.config['SESSION_COOKIE_SECURE']


app.session_interface = CookiePolicy()


class Error(Exception):
    def __init__(self, message, status=None, *, http_status=400):
        super().__init__(message)
        self.status = status
        self.http_status = http_status


def browser_capacity():
    configured = os.getenv('STREAMDESK_BROWSER_LIMIT', 'auto')
    if configured != 'auto':
        try:
            return max(1, min(16, int(configured)))
        except ValueError:
            return 1
    try:
        memory_kib = int(next(line for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemTotal:')).split()[1])
        cores_per_browser = max(2, (browser_fps() + 4) // 5)
        return max(1, min(16, (os.cpu_count() or 1) // cores_per_browser, memory_kib // (2 * 1024 * 1024)))
    except (OSError, ValueError, StopIteration):
        return 1


def browser_fps():
    try:
        return max(1, min(30, int(os.getenv('STREAMDESK_BROWSER_FPS', '10'))))
    except ValueError:
        return 10


def db():
    connection = sqlite3.connect(DATA / 'app.db', timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def rows(sql, args=()):
    with db() as connection:
        return [dict(row) for row in connection.execute(sql, args)]


def write(sql, args=()):
    with db() as connection:
        cursor = connection.execute(sql, args)
        return cursor.lastrowid


def atomic(path, content):
    path = Path(path)
    previous = path.stat() if path.exists() else None
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.streamdesk-')
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp, previous.st_mode & 0o777 if previous else 0o600)
        if previous and os.geteuid() == 0:
            os.chown(temp, previous.st_uid, previous.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def encrypt(value):
    return cipher.encrypt(value.encode()).decode() if value else ''


def decrypt(value):
    return cipher.decrypt(value.encode()).decode() if value else ''


def setting(name, default=''):
    result = rows('SELECT value FROM settings WHERE name=?', (name,))
    return decrypt(result[0]['value']) if result else default


def set_setting(name, value):
    write('INSERT OR REPLACE INTO settings(name,value) VALUES (?,?)', (name, encrypt(value)))


def remote(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        raise Error(f'Der Dienst meldet HTTP {exc.code}. Bitte Einstellungen prüfen.', status=exc.code) from None
    except (OSError, ValueError):
        raise Error('Verbindung zum Dienst fehlgeschlagen. Bitte später erneut versuchen.') from None


def mtx(path, value=None, method=None):
    return remote(API + path, json.dumps(value).encode() if value is not None else None,
                  {'Content-Type': 'application/json'}, method or ('PATCH' if value is not None else 'GET'))


def media_username(user):
    return 'streamdesk_' + NAMESPACE + '_' + user['username']


def paths(user):
    prefix = user['prefix']
    return [prefix + name for name in ('source1', 'source2', 'live')]


INPUT_NAMES = ('source1', 'source2')
RECORD_SOURCES = (*INPUT_NAMES, 'live')
MAX_CUSTOM_OUTPUTS = 8


def input_paths(user):
    return [user['prefix'] + row['key'] for row in MODEL.sources(user)]


def preview_path(user, slot):
    source = {1: 'source1', 2: 'source2', 3: 'live', 4: 'source3', 5: 'pull'}.get(slot)
    if source is None or source != 'live' and source not in {row['key'] for row in MODEL.sources(user)}:
        raise Error('Ungültige Quelle.', http_status=404)
    if slot == 1 and user['replay_recording_id']:
        source = 'replay'
    return user['prefix'] + source


OUTPUT_KINDS = ('twitch', 'youtube', 'custom')


def valid_output_kind(kind):
    return isinstance(kind, str) and (kind in OUTPUT_KINDS or re.fullmatch(r'(?:twitch|youtube|custom)-[a-f0-9]{12}', kind) is not None)


def output_kinds(user):
    return (*OUTPUT_KINDS, *(d['kind'] for d in destinations(user) if d['kind'] not in OUTPUT_KINDS))


def output_path(user, kind='twitch'):
    return user['prefix'] + ('output' if kind == 'twitch' else 'output-' + kind)


def destinations(user, selected=False):
    found = rows('SELECT * FROM outputs WHERE user_id=? ORDER BY kind', (user['id'],))
    if not found and user['output']:
        found = [{'kind': user['output_kind'], 'endpoint': user['output'], 'selected': 1}]
    return [d for d in found if not selected or d['selected'] and d['endpoint']]


def configured_forwards(user, config=None):
    config = config or yaml.safe_load(CONFIG.read_text())
    return {output_path(user, kind): config['paths'].get(output_path(user, kind), {}).get('forward', []) for kind in output_kinds(user)}


def renewal_forwards(user, config=None):
    active = {p: targets for p, targets in configured_forwards(user, config).items() if targets}
    twitch = output_path(user, 'twitch')
    return {twitch: active[twitch]} if twitch in active else active


def reconcile():
    """Persist only owned paths, ACLs and program groups; keep foreign state intact."""
    with LOCK:
        config = yaml.safe_load(CONFIG.read_text())
        from media_config import merge_auth
        managed_auth, obsolete = [], []
        all_paths = config.setdefault('paths', {})
        for user in rows('SELECT * FROM users'):
            catalog = MODEL.sources(user, archived=True)
            current = {row['key']:row for row in catalog if not row.get('deleted')}
            programs = MODEL.programs(user, archived=True)
            if user['active']:
                managed_auth.append({
                    'user':media_username(user),'pass':decrypt(user['media_secret']),'ips':[],
                    'permissions':[{'action':'publish','path':user['prefix']+row['key']} for row in current.values()
                                   if row['enabled'] and row['protocol'] in ('rtmp','srt')]
                        + [{'action':'read','path':name} for name in
                           [*(user['prefix']+row['key'] for row in catalog),user['prefix']+'replay',
                            *(row['path'] for row in programs),*(row['rtc_path'] for row in programs if row['active'])]]
                        + [{'action':'playback','path':user['prefix']+name} for name in MODEL.record_sources(user)]})
            for row in catalog:
                name = user['prefix']+row['key']
                settings = all_paths.setdefault(name, {})
                enabled = bool(user['active']) and row['enabled'] and not row.get('deleted')
                settings.update(source=decrypt(row['endpoint']) if enabled and row['protocol'] in ('rtsp','rtsps') else 'publisher',
                                sourceOnDemand=False,rtspTransport='tcp',overridePublisher=False,alwaysAvailable=False)
                settings.setdefault('record',False)
                if not enabled:
                    settings['record'] = False
            for legacy in ('source3','pull'):
                name = user['prefix']+legacy
                if legacy not in {row['key'] for row in catalog} and name in all_paths:
                    del all_paths[name];obsolete.append(name)
            all_paths[user['prefix']+'replay'] = {'source':'publisher','overridePublisher':False,'alwaysAvailable':False,'record':False}
            # Each membership set has a stable program path. Identical routes share one encoder.
            for program in programs:
                enabled = bool(user['active']) and program['active']
                settings = all_paths.setdefault(program['path'], {})
                settings.update(source='publisher',overridePublisher=False,alwaysAvailable=enabled,
                                alwaysAvailableFile='',alwaysAvailableTracks=STANDBY_TRACKS,
                                alwaysAvailableRecorded=True,forward=[])
                settings.setdefault('record',False)
                if not enabled:
                    settings['record'] = False
                all_paths[program['rtc_path']] = {'source':'publisher','overridePublisher':False,'record':False,
                    'alwaysAvailable':enabled,'alwaysAvailableFile':'','alwaysAvailableTracks':[{'codec':'H264'},{'codec':'Opus'}]}
            # Retired output paths were created by this integration and are already stopped.
            expected = {output_path(user,kind) for kind in output_kinds(user)}
            for name in list(all_paths):
                if name.startswith(user['prefix']+'output-') and name not in expected:
                    kind = name[len(user['prefix']+'output-'):]
                    if valid_output_kind(kind):
                        del all_paths[name];obsolete.append(name)
            live = paths(user)[2]
            old = all_paths.get(output_path(user)) or {}
            legacy = old.get('forward', [])
            legacy_dest = legacy[0].get('dest') if legacy else None
            for kind in output_kinds(user):
                name = output_path(user,kind)
                outgoing = all_paths.get(name) or {}
                targets = outgoing.get('forward', [])
                if kind == 'custom' and legacy_dest and user['output_kind']=='custom' and decrypt(user['output'])==legacy_dest:
                    targets = legacy
                if kind == 'twitch' and legacy_dest and user['output_kind']=='custom' and decrypt(user['output'])==legacy_dest:
                    targets = []
                if not user['active']:
                    targets = []
                program = MODEL.output_program(user,kind)
                outgoing.update(source=RTSP+program['path'] if targets else 'publisher',sourceOnDemand=False,
                                rtspTransport='tcp',alwaysAvailable=False,record=False,forward=targets)
                all_paths[name] = outgoing
        merge_auth(config,NAMESPACE,managed_auth,LOCAL_IPS)
        atomic(CONFIG,yaml.safe_dump(config,sort_keys=False,allow_unicode=True))
        if os.getenv('STREAMDESK_ENGINE','1')=='1':
            try:
                sync_media_runtime(obsolete)
            except Error:
                logging.warning('MediaMTX ist für den sofortigen Abgleich noch nicht erreichbar; Konfiguration wurde gespeichert.')


def sync_media_runtime(obsolete_paths=()):
    from media_config import synchronize_runtime
    synchronize_runtime(mtx,yaml.safe_load(CONFIG.read_text()),NAMESPACE,obsolete_paths=obsolete_paths)


def initialize():
    global cipher
    DATA.mkdir(parents=True, exist_ok=True)
    os.chmod(DATA, 0o700)
    spool = DATA / 'tmp'
    spool.mkdir(mode=0o700, exist_ok=True)
    tempfile.tempdir = str(spool)
    for name, generator in [('fernet.key', Fernet.generate_key), ('session.key', lambda: secrets.token_hex(32).encode())]:
        path = DATA / name
        if not path.exists():
            atomic(path, generator().decode())
    cipher = Fernet((DATA / 'fernet.key').read_bytes())
    app.secret_key = (DATA / 'session.key').read_text()
    with db() as connection:
        connection.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, admin INTEGER DEFAULT 0,
          active INTEGER DEFAULT 1, version INTEGER DEFAULT 1, prefix TEXT UNIQUE,
          media_secret TEXT, offline TEXT, output TEXT DEFAULT '', output_kind TEXT DEFAULT 'twitch',
          twitch_name TEXT DEFAULT '', upload_state TEXT DEFAULT '', upload_message TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS user_id_sequence(id INTEGER PRIMARY KEY AUTOINCREMENT);
        INSERT OR IGNORE INTO user_id_sequence(id) SELECT id FROM users;
        CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS videos(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
          rendered TEXT DEFAULT '', overlay_text TEXT DEFAULT '', duration REAL DEFAULT 0,
          size INTEGER DEFAULT 0, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS twitch_auth(
          user_id INTEGER PRIMARY KEY, broadcaster_id TEXT NOT NULL, access TEXT NOT NULL,
          refresh TEXT NOT NULL, client_id TEXT NOT NULL, expires REAL NOT NULL,
          validated REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS outputs(user_id INTEGER NOT NULL,kind TEXT NOT NULL,endpoint TEXT NOT NULL,selected INTEGER DEFAULT 1,PRIMARY KEY(user_id,kind));
        CREATE TABLE IF NOT EXISTS youtube_auth(user_id INTEGER PRIMARY KEY,channel_id TEXT NOT NULL,name TEXT NOT NULL,access TEXT NOT NULL,refresh TEXT NOT NULL,expires REAL NOT NULL,client_id TEXT NOT NULL,broadcast_id TEXT DEFAULT '',chat_id TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS widget_tokens(user_id INTEGER PRIMARY KEY,token_hash TEXT NOT NULL UNIQUE,token TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recordings(
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL,
          source TEXT NOT NULL, status TEXT NOT NULL, started REAL NOT NULL, ended REAL,
          duration REAL DEFAULT 0, size INTEGER DEFAULT 0, audio INTEGER DEFAULT 1, message TEXT DEFAULT '');
        ''')
        auth_columns = {r['name'] for r in connection.execute('PRAGMA table_info(twitch_auth)')}
        if 'scopes' not in auth_columns:
            connection.execute("ALTER TABLE twitch_auth ADD COLUMN scopes TEXT DEFAULT '[]'")
        connection.execute("INSERT OR IGNORE INTO outputs(user_id,kind,endpoint,selected) SELECT id,output_kind,output,1 FROM users WHERE output!=''")
        output_columns = {r['name'] for r in connection.execute('PRAGMA table_info(outputs)')}
        if 'label' not in output_columns:
            connection.execute("ALTER TABLE outputs ADD COLUMN label TEXT NOT NULL DEFAULT ''")
        columns = {r['name'] for r in connection.execute('PRAGMA table_info(users)')}
        if 'selected_video_id' not in columns:
            connection.execute('ALTER TABLE users ADD COLUMN selected_video_id INTEGER')
        for name, declaration in [('replay_recording_id', 'INTEGER'), ('renew_interval', 'INTEGER DEFAULT 0'),
                                  ('renew_gap', 'INTEGER DEFAULT 2'), ('renew_next', 'REAL DEFAULT 0'),
                                  ('renew_resume', 'REAL DEFAULT 0'), ('renew_last', 'REAL DEFAULT 0'),
                                  ('stream_total', 'REAL DEFAULT 0'), ('stream_session', 'REAL DEFAULT 0'),
                                  ('stream_started', 'REAL DEFAULT 0'), ('stream_seen', 'REAL DEFAULT 0'),
                                  ('stream_connected', 'INTEGER DEFAULT 0'), ('stats_since', 'REAL DEFAULT 0'),
                                  ('source_mode', "TEXT NOT NULL DEFAULT 'auto'"),
                                  ('source3_protocol', "TEXT NOT NULL DEFAULT 'srt'"),
                                  ('pull_url', "TEXT NOT NULL DEFAULT ''"), ('pull_enabled', 'INTEGER NOT NULL DEFAULT 0'),
                                  ('theme', "TEXT NOT NULL DEFAULT 'system'")]:
            if name not in columns:
                connection.execute(f'ALTER TABLE users ADD COLUMN {name} {declaration}')
        video_columns = {r['name'] for r in connection.execute('PRAGMA table_info(videos)')}
        for column, default in [('overlay_style', "'{}'"), ('browser_url', "''")]:
            if column not in video_columns:
                connection.execute(f'ALTER TABLE videos ADD COLUMN {column} TEXT DEFAULT {default}')
        # Keep every existing user's currently selected clip during migration.
        for user in connection.execute('SELECT id,offline,selected_video_id FROM users').fetchall():
            if user['selected_video_id'] is None and Path(user['offline']).is_file():
                cursor = connection.execute('INSERT OR IGNORE INTO videos(user_id,name,path,size,created) VALUES (?,?,?,?,?)',
                                            (user['id'], 'Bisheriges Offline-Video', user['offline'], Path(user['offline']).stat().st_size, int(time.time())))
                video_id = connection.execute('SELECT id FROM videos WHERE path=?', (user['offline'],)).fetchone()[0]
                connection.execute('UPDATE users SET selected_video_id=? WHERE id=?', (video_id, user['id']))

    MODEL.migrate()


def add_user(username, password, admin=False, legacy=False):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,29}', username):
        raise Error('Benutzername: 3–30 Kleinbuchstaben, Ziffern, _ oder -, mit Buchstabe beginnen.')
    if len(password) < 12:
        raise Error('Bitte mindestens 12 Zeichen als Passwort verwenden.')
    with LOCK:
        if rows('SELECT id FROM users WHERE username=?', (username,)):
            raise Error('Dieser Benutzername ist bereits vergeben.')
        prefix = '' if legacy else NAMESPACE + '/' + username + '/'
        folder = DATA / 'media' / username
        folder.mkdir(parents=True, exist_ok=True)
        offline = folder / 'offline-default.mp4'
        shutil.copyfile(DEFAULT_CLIP, offline)
        try:
            reserved = write('INSERT INTO user_id_sequence DEFAULT VALUES', ())
            uid = write('INSERT INTO users(id,username,password,admin,prefix,media_secret,offline) VALUES (?,?,?,?,?,?,?)',
                        (reserved, username, generate_password_hash(password), int(admin), prefix,
                         encrypt(secrets.token_urlsafe(24)), str(offline)))
            video_id = write('INSERT INTO videos(user_id,name,path,size,created) VALUES (?,?,?,?,?)',
                             (uid, 'Standard-Offline-Video', str(offline), offline.stat().st_size, int(time.time())))
            write('UPDATE users SET selected_video_id=? WHERE id=?', (video_id, uid))
            reconcile()
        except Exception:
            write('DELETE FROM videos WHERE user_id IN (SELECT id FROM users WHERE username=?)', (username,))
            write('DELETE FROM users WHERE username=?', (username,))
            raise
        threading.Thread(target=probe_video_durations, daemon=True).start()
        return uid


def current():
    result = rows('SELECT * FROM users WHERE id=? AND active=1', (session.get('uid', 0),))
    if not result or result[0]['version'] != session.get('version'):
        return None
    return result[0]


def login_required(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        user = current()
        if not user:
            return (jsonify(error='Bitte erneut anmelden.'), 401) if request.path.startswith('/api/') else redirect('/login')
        return function(user, *args, **kwargs)
    return wrapped


def expert_required(function):
    @functools.wraps(function)
    def wrapped(user, *args, **kwargs):
        if session.get('expert_mode') is not True:
            raise Error('Bitte zuerst unter „Expertenmodus“ den Modus aktivieren.', http_status=403)
        return function(user, *args, **kwargs)
    return wrapped


@app.before_request
def csrf():
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        expected = session.get('csrf', '')
        actual = request.headers.get('X-CSRF-Token', '')
        if request.path == '/login':
            actual = request.form.get('csrf', '')
        try:
            valid = bool(expected) and bool(actual) and hmac.compare_digest(expected, actual)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            return jsonify(error='Sitzung abgelaufen. Bitte Seite neu laden.'), 403


@app.after_request
def headers(response):
    response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'SAMEORIGIN',
                             'Referrer-Policy': 'no-referrer',
                             'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; worker-src 'self' blob:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; base-uri 'none'; form-action 'self'"})
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
    else:
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.errorhandler(Error)
def handle_error(error):
    return jsonify(error=str(error)), error.http_status


@app.errorhandler(413)
def too_large(_):
    return jsonify(error='Die Datei ist zu groß. Maximal 500 MB.'), 413


ATTEMPTS = {}


def prune_attempts(now):
    cutoff = now - 300
    for key in list(ATTEMPTS):
        recent = [stamp for stamp in ATTEMPTS[key] if stamp >= cutoff]
        if recent:
            ATTEMPTS[key] = recent
        else:
            ATTEMPTS.pop(key, None)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    session.setdefault('csrf', secrets.token_urlsafe(32))
    if request.method == 'POST':
        ip = request.remote_addr or 'unknown'
        username = request.form.get('username', '').lower().strip()
        password = request.form.get('password', '')
        now = time.time()
        keys = ['ip:' + ip]
        if username:
            keys.append('user:' + username)
        with LOCK:
            prune_attempts(now)
            buckets = []
            for key in keys:
                recent = [stamp for stamp in ATTEMPTS.get(key, []) if now - stamp < 300]
                ATTEMPTS[key] = recent
                buckets.append(recent)
        if any(len(bucket) >= 10 for bucket in buckets):
            error = 'Zu viele Versuche. Bitte in fünf Minuten erneut versuchen.'
        else:
            found = rows('SELECT * FROM users WHERE username=? AND active=1', (username,))
            hashed = found[0]['password'] if found else _DUMMY_PASSWORD_HASH
            if found and check_password_hash(hashed, password):
                session.clear()
                session.update(uid=found[0]['id'], version=found[0]['version'], csrf=secrets.token_urlsafe(32))
                return redirect('/')
            with LOCK:
                for key in keys:
                    ATTEMPTS.setdefault(key, []).append(now)
                if len(ATTEMPTS) > 2000:
                    prune_attempts(now)
            error = 'Benutzername oder Passwort stimmt nicht.'
    return render_template('login.html', csrf=session['csrf'], error=error)


@app.post('/api/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get('/')
@login_required
def index(user):
    return render_template('index.html', user=user, csrf=session['csrf'], public=PUBLIC,
                           expert=session.get('expert_mode') is True)


def update_stream_time(user, state, enabled, stamp=None):
    """Persist actual connected time; destination renewals keep the logical session."""
    stamp = time.time() if stamp is None else stamp
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        connected = state == 'forwarding'
        elapsed = stamp - user['stream_seen']
        delta = elapsed if user['stream_connected'] and 0 <= elapsed <= 5 else 0
        started = user['stream_started']
        if connected and not started:
            started = stamp
        if not enabled:
            started = 0
        if enabled or user['stream_connected'] or user['stream_started']:
            write('UPDATE users SET stream_total=stream_total+?,stream_session=stream_session+?,stream_started=?,stream_seen=?,stream_connected=?,stats_since=CASE WHEN stats_since=0 THEN ? ELSE stats_since END WHERE id=?',
                  (delta, delta, started, stamp, int(connected), stamp, user['id']))


MEDIA_STATS_CACHE = {}


def dashboard_stats(user):
    uid, now = user['id'], time.monotonic()
    cached = MEDIA_STATS_CACHE.get(uid)
    if not cached or now - cached[0] >= 5:
        videos = rows('SELECT id,duration FROM videos WHERE user_id=?', (uid,))
        recordings = rows("SELECT duration FROM recordings WHERE user_id=? AND status='ready'", (uid,))
        used = 0
        for category in ('media', 'recordings'):
            directory = DATA / category / user['username']
            if directory.is_dir():
                for path in directory.iterdir():
                    try:
                        if path.is_file() and path.suffix != '.log':
                            used += path.stat().st_size
                    except OSError:
                        pass
        media = {'used_bytes': used, 'video_count': len(videos), 'video_seconds': sum(v['duration'] or 0 for v in videos),
                 'recording_count': len(recordings), 'recording_seconds': sum(r['duration'] or 0 for r in recordings)}
        MEDIA_STATS_CACHE[uid] = (now, media)
    else:
        media = cached[1]
    disk = shutil.disk_usage(DATA)
    selected = rows('SELECT duration FROM videos WHERE id=? AND user_id=?', (user['selected_video_id'], uid))
    return {**media, 'free_bytes': disk.free, 'total_bytes': disk.total, 'server_used_bytes': disk.used,
            'selected_video_seconds': selected[0]['duration'] if selected else 0,
            'stream_seconds': user['stream_session'], 'total_stream_seconds': user['stream_total'],
            'stream_started': user['stream_started'], 'stats_since': user['stats_since']}


def probe_video_durations():
    for video in rows('SELECT id,path FROM videos WHERE duration<=0'):
        try:
            probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', video['path']], capture_output=True, text=True, timeout=15)
            duration = float(json.loads(probe.stdout)['format']['duration'])
            if duration > 0:
                write('UPDATE videos SET duration=? WHERE id=? AND path=? AND duration<=0', (duration, video['id'], video['path']))
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            pass


@app.get('/api/status')
@login_required
def status(user):
    with LOCK:
        snapshot = dict(ENGINE.snapshot.get(user['id'],{'ok':False,'error':'Verbindung wird aufgebaut …'}))
        source_status = {row['key']:row for row in snapshot.get('sources',[]) if 'key' in row}
        snapshot['sources'] = [dict(row,**{key:source_status.get(row['key'],{}).get(key,value) for key,value in
                                           (('state','offline'),('mbps',0),('tracks',[]))}) for row in MODEL.public_sources(user)]
        program_status = {row['id']:row for row in snapshot.get('programs',[])}
        snapshot['programs'] = [dict(row,**{key:program_status.get(row['id'],{}).get(key,value) for key,value in
            (('available',False),('selected_source',None),('offline_playing',False),('browser_status','off'))},
            preview_url=PUBLIC+'/program/'+row['id']+'/',webrtc_url=PUBLIC+'/webrtc/3/play/?program='+row['id'])
            for row in MODEL.programs(user)]
        selected = rows('SELECT id,name,LENGTH(browser_url)>0 AS browser_enabled FROM videos WHERE id=? AND user_id=?',(user['selected_video_id'],user['id']))
        by_kind={row['kind']:row for row in destinations(user)}
        outputs = [{'kind':row['kind'],'platform':row['kind'].split('-')[0],'configured':bool(row['endpoint']),
                    'label':row.get('label') or {'twitch':'Twitch','youtube':'YouTube','custom':'Eigener Anbieter'}.get(row['kind'],'Weiterer Ausgang'),
                    'selected':bool(row['selected']),'sources':MODEL.route(user,row['kind']),
                    'program':MODEL.output_program(user,row['kind'])['id']} for row in [by_kind[kind] for kind in output_kinds(user) if kind in by_kind]]
        return jsonify(**snapshot,user={'username':user['username'],'admin':bool(user['admin'])},
            expert_mode=session.get('expert_mode') is True,source_mode='auto',theme=user['theme'],
            offline_video=selected[0] if selected else None,recording=recording_status(user),replay_id=user['replay_recording_id'],stats=dashboard_stats(user),
            renewal={'interval':user['renew_interval'],'gap':user['renew_gap'],'next':user['renew_next'],'resume':user['renew_resume'],'last':user['renew_last']},
            output={'configured':bool(destinations(user,True)),'kind':'multi' if len(destinations(user,True))>1 else next((row['kind'] for row in destinations(user,True)),user['output_kind']),'account':user['twitch_name']},
            outputs=outputs,chat=CHAT.info(user),record_sources=MODEL.record_sources(user),
            oauth_ready=bool(setting('client_id') and setting('client_secret')),
            twitch_edit_ready=bool(rows('SELECT user_id FROM twitch_auth WHERE user_id=?',(user['id'],))),
            upload={'state':user['upload_state'],'message':user['upload_message']},
            limits={'browser_limit':browser_capacity(),'browser_fps':browser_fps(),'upload_mb':500},public_url=PUBLIC)


def source_ingest(user, key):
    source = MODEL.source(user,key)
    if source['protocol'] not in ('rtmp','srt'):
        return {'key':key,'label':source['label'],'protocol':source['protocol']}
    path = user['prefix']+key
    name, secret = media_username(user),decrypt(user['media_secret'])
    query = urllib.parse.urlencode({'user':name,'pass':secret})
    stream_id = f'publish:{path}:{name}:{secret}'
    srt_query = urllib.parse.urlencode({'streamid':stream_id,'mode':'caller','latency':1000000,'pkt_size':1316},safe=':/')
    return {'key':key,'label':source['label'],'protocol':source['protocol'],
            'rtmp':f'rtmp://{HOST}:{RTMP_PORT}/{path}?{query}',
            'srt':f'srt://{HOST}:{SRT_PORT}?{srt_query}','srt_server':f'srt://{HOST}:{SRT_PORT}',
            'stream_id':stream_id,'username':name,'password':secret,'srt_mode':'caller','srt_latency_ms':1000}


@app.get('/api/ingest')
@login_required
def ingest(user):
    first, second = source_ingest(user,'source1'),source_ingest(user,'source2')
    return jsonify(**{key:second[key] for key in ('srt','srt_server','stream_id','srt_mode','srt_latency_ms','username','password')},
                   rtmp=first['rtmp'],sources=[source_ingest(user,row['key']) for row in MODEL.sources(user)])


@app.get('/api/ingest/<key>')
@login_required
def ingest_source(user,key):
    return jsonify(source_ingest(user,key))


def resolve_host_ips(hostname, port=443):
    host = (hostname or '').strip('[]')
    if not host:
        return set()
    try:
        return {str(ipaddress.ip_address(host))}
    except ValueError:
        return {entry[4][0] for entry in socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)}


def ingest_ips():
    try:
        return resolve_host_ips(HOST)
    except OSError:
        return set()


def blocked_target_ip(addr, blocked=None):
    ip = ipaddress.ip_address(addr)
    return (not ip.is_global) or addr in (blocked if blocked is not None else ingest_ips())


def validate_output(value):
    if len(value) > 2048 or any(c.isspace() for c in value):
        raise Error('Ungültige Ausgangsadresse.')
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ('rtmp', 'rtmps', 'srt', 'rtsp', 'rtsps') or not parsed.hostname:
            raise ValueError()
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError()
        blocked = ingest_ips()
        addresses = resolve_host_ips(parsed.hostname, parsed.port or 443)
        if not addresses or any(blocked_target_ip(addr, blocked) for addr in addresses):
            raise ValueError()
    except (ValueError, OSError):
        raise Error('Bitte eine öffentliche RTMP-, RTMPS-, SRT- oder RTSP-Zieladresse verwenden.') from None
    return value


def forward(user, enable, kind=None):
    with LOCK:
        config = yaml.safe_load(CONFIG.read_text())
        live = paths(user)[2]
        before = configured_forwards(user, config)
        chosen = [d for d in destinations(user, selected=kind is None) if kind is None or d['kind'] == kind] if enable else []
        if enable and (not chosen or any(not row['endpoint'] for row in chosen)):
            raise Error('Bitte mindestens einen eingerichteten Ausgang auswählen.')
        if any(not MODEL.route(user,row['kind']) for row in chosen):
            raise Error('Bitte diesem Ausgang zuerst im Expertenmodus Quellen zuordnen.')
        endpoints = {d['kind']: validate_output(decrypt(d['endpoint'])) for d in chosen}
        if kind is not None:
            endpoints = {**{k: before[output_path(user, k)][0]['dest'] for k in output_kinds(user)
                            if k != kind and before[output_path(user, k)]}, **endpoints}
        if len(endpoints) != len(set(endpoints.values())):
            raise Error('Dasselbe Streamingziel ist mehrfach ausgewählt.')
        changes = {live: {'forward': [], 'alwaysAvailable': bool(user['active']), 'alwaysAvailableFile': '', 'alwaysAvailableTracks': STANDBY_TRACKS}}
        for output_kind in output_kinds(user) if kind is None else (kind,):
            changes[output_path(user, output_kind)] = {'forward': [{'dest': endpoints[output_kind]}] if output_kind in endpoints else [],
                                                     'source': RTSP + MODEL.output_program(user,output_kind)['path'] if output_kind in endpoints else 'publisher'}
        for name in changes:
            config['paths'].setdefault(name, {'source':'publisher','forward':[],'alwaysAvailable':False,'record':False})
        previous = {name: {key: config['paths'][name].get(key) for key in change} for name, change in changes.items()}
        applied = []
        try:
            for name, change in changes.items():
                mtx('config/paths/patch/' + name, change)
                applied.append(name)
                config['paths'][name].update(change)
            atomic(CONFIG, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
        except (OSError, Error):
            for name in reversed(applied):
                mtx('config/paths/patch/' + name, previous[name])
            raise Error('Ausgänge konnten nicht geändert werden; vorheriger Zustand wiederhergestellt.') from None
        if enable and not any(before.values()):
            write('UPDATE users SET stream_session=0,stream_started=0,stream_seen=0,stream_connected=0 WHERE id=?', (user['id'],))
        if not endpoints:
            update_stream_time(user, 'stopped', False)
        write('UPDATE users SET renew_next=0,renew_resume=0 WHERE id=?', (user['id'],))


@app.post('/api/start')
@login_required
def start(user):
    if not READY.is_set():
        raise Error('MediaMTX wird noch verbunden.')
    if user['upload_state'] in ('queued', 'processing'):
        raise Error('Bitte warten, bis die Videoverarbeitung fertig ist.')
    if not Path(user['offline']).is_file():
        raise Error('Bitte ein verfügbares Offline-Video auswählen.')
    forward(user, True)
    return jsonify(ok=True)


@app.post('/api/stop')
@login_required
def stop(user):
    forward(user, False)
    return jsonify(ok=True)


def require_stopped(user):
    if any(configured_forwards(user).values()):
        raise Error('Bitte die Ausgänge zuerst stoppen.')


@app.post('/api/outputs/select')
@login_required
def select_outputs(user):
    kinds = (request.get_json() or {}).get('kinds')
    if not isinstance(kinds, list) or any(not valid_output_kind(k) for k in kinds):
        raise Error('Ungültige Ausgangsauswahl.')
    with LOCK, db() as connection:
        configured = {d['kind'] for d in destinations(user) if d['endpoint']}
        if any(kind not in configured for kind in kinds):
            raise Error('Bitte zuerst den Streamschlüssel für die gewünschte Plattform hinterlegen.')
        connection.execute('UPDATE outputs SET selected=0 WHERE user_id=?', (user['id'],))
        for kind in kinds:
            connection.execute('UPDATE outputs SET selected=1 WHERE user_id=? AND kind=?', (user['id'], kind))
    return jsonify(ok=True)


@app.post('/api/outputs/<kind>/delete')
@login_required
def delete_output(user, kind):
    if kind not in OUTPUT_KINDS:
        raise Error('Ungültiger Ausgang.')
    if configured_forwards(user).get(output_path(user,kind)):
        raise Error('Bitte diesen Ausgang zuerst stoppen.')
    write('DELETE FROM outputs WHERE user_id=? AND kind=?', (user['id'], kind))
    if user['output_kind'] == kind:
        write("UPDATE users SET output='' WHERE id=?", (user['id'],))
    return jsonify(ok=True)


@app.post('/api/output')
@login_required
def output(user):
    with LOCK:
        return save_output(user)


def save_output(user):
    require_stopped(user)
    body = request.get_json() or {}
    kind = body.get('kind', 'twitch')
    if kind == 'twitch':
        key = str(body.get('key', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{15,256}', key):
            raise Error('Bitte einen gültigen Twitch-Streamschlüssel eingeben.')
        value = TWITCH + '#' + key
    elif kind == 'youtube':
        key = str(body.get('key', '')).strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{10,256}', key):
            raise Error('Bitte einen gültigen YouTube-Streamschlüssel eingeben.')
        value = 'rtmps://a.rtmps.youtube.com:443/live2#' + key
    elif kind == 'custom':
        current = [row for row in destinations(user) if row['kind'].startswith('custom')]
        if not any(row['kind'] == 'custom' for row in current) and len(current) >= MAX_CUSTOM_OUTPUTS:
            raise Error(f'Maximal {MAX_CUSTOM_OUTPUTS} Custom-Ziele pro Benutzer.')
        value = validate_output(str(body.get('url', '')).strip())
    else:
        raise Error('Unbekannter Ausgang.')
    write('UPDATE users SET output=?,output_kind=? WHERE id=?', (encrypt(value), kind, user['id']))
    write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,0) ON CONFLICT(user_id,kind) DO UPDATE SET endpoint=excluded.endpoint', (user['id'], kind, encrypt(value)))
    return jsonify(ok=True)


@app.post('/api/disconnect')
@login_required
def disconnect(user):
    forward(user, False)
    write("UPDATE users SET output='' WHERE id=?", (user['id'],))
    write("UPDATE outputs SET endpoint='',selected=0 WHERE user_id=?", (user['id'],))
    return jsonify(ok=True)


def remove_twitch_auth(uid, revoke=True):
    with OAUTH_LOCK:
        found = rows('SELECT * FROM twitch_auth WHERE user_id=?', (uid,))
        write('DELETE FROM twitch_auth WHERE user_id=?', (uid,))
        if found and revoke:
            try:
                remote('https://id.twitch.tv/oauth2/revoke', urllib.parse.urlencode({
                    'client_id': found[0]['client_id'], 'token': decrypt(found[0]['access'])}).encode())
            except Error:
                pass


def validated_twitch_token(uid, force=False):
    with OAUTH_LOCK:
        found = rows('SELECT * FROM twitch_auth WHERE user_id=?', (uid,))
        if not found:
            raise Error('Bitte Twitch erneut verbinden und die Berechtigung zum Bearbeiten der Kanalinformationen bestätigen.')
        auth = found[0]
        if auth['client_id'] != setting('client_id'):
            remove_twitch_auth(uid, revoke=False)
            raise Error('Die Twitch-App wurde geändert. Bitte dein Konto erneut verbinden.')
        token = decrypt(auth['access'])
        now = time.time()
        if force or now - auth['validated'] >= 3500 or auth['expires'] <= now:
            try:
                checked = remote('https://id.twitch.tv/oauth2/validate', headers={'Authorization': 'OAuth ' + token})
            except Error as exc:
                if exc.status != 401:
                    raise
                try:
                    refreshed = remote('https://id.twitch.tv/oauth2/token', urllib.parse.urlencode({
                        'grant_type': 'refresh_token', 'refresh_token': decrypt(auth['refresh']),
                        'client_id': auth['client_id'], 'client_secret': setting('client_secret')}).encode())
                    token = refreshed['access_token']
                    checked = remote('https://id.twitch.tv/oauth2/validate', headers={'Authorization': 'OAuth ' + token})
                    write('UPDATE twitch_auth SET access=?,refresh=?,expires=? WHERE user_id=?',
                          (encrypt(token), encrypt(refreshed.get('refresh_token') or decrypt(auth['refresh'])),
                           now + refreshed.get('expires_in', 0), uid))
                except Error as refresh_error:
                    if refresh_error.status not in (400, 401, 403):
                        raise
                    remove_twitch_auth(uid, revoke=False)
                    raise Error('Die Twitch-Berechtigung ist abgelaufen. Bitte dein Konto erneut verbinden.') from None
                except KeyError:
                    remove_twitch_auth(uid, revoke=False)
                    raise Error('Die Twitch-Berechtigung ist abgelaufen. Bitte dein Konto erneut verbinden.') from None
            if (checked.get('client_id') != auth['client_id'] or checked.get('user_id') != auth['broadcaster_id']
                    or not TWITCH_SCOPES.issubset(set(checked.get('scopes', [])))):
                remove_twitch_auth(uid, revoke=False)
                raise Error('Die Twitch-Berechtigung reicht nicht aus. Bitte dein Konto erneut verbinden.')
            write('UPDATE twitch_auth SET validated=?,expires=?,scopes=? WHERE user_id=?',
                  (now, now + checked.get('expires_in', 0), json.dumps(checked.get('scopes', [])), uid))
        return token, auth['broadcaster_id']


def twitch_user_api(user, path, body=None):
    for attempt in range(2):
        token, broadcaster = validated_twitch_token(user['id'], force=bool(attempt))
        target = 'https://api.twitch.tv/helix/' + path.replace('{broadcaster}', broadcaster)
        try:
            return remote(target, json.dumps(body).encode() if body is not None else None,
                          {'Authorization': 'Bearer ' + token, 'Client-Id': setting('client_id'), 'Content-Type': 'application/json'},
                          'PATCH' if body is not None else 'GET')
        except Error as exc:
            if exc.status == 401 and attempt == 0:
                write('UPDATE twitch_auth SET validated=0 WHERE user_id=?', (user['id'],))
                continue
            if exc.status == 401:
                remove_twitch_auth(user['id'], revoke=False)
                raise Error('Bitte Twitch erneut verbinden.') from None
            if exc.status == 403:
                raise Error('Twitch erlaubt diese Änderung nicht. Konto und Berechtigungen prüfen.') from None
            raise


def twitch_app_api(path):
    with OAUTH_LOCK:
        client = setting('client_id')
        if not client or not setting('client_secret'):
            raise Error('Die Twitch-App muss zuerst in der Administration eingerichtet werden.')
        for attempt in range(2):
            if APP_TOKEN.get('client') != client or APP_TOKEN.get('expires', 0) <= time.time():
                value = remote('https://id.twitch.tv/oauth2/token', urllib.parse.urlencode({
                    'client_id': client, 'client_secret': setting('client_secret'), 'grant_type': 'client_credentials'}).encode())
                APP_TOKEN.update(client=client, token=value['access_token'], expires=time.time() + max(10, value.get('expires_in', 3600) - 60))
            try:
                return remote('https://api.twitch.tv/helix/' + path,
                              headers={'Authorization': 'Bearer ' + APP_TOKEN['token'], 'Client-Id': client})
            except Error as exc:
                if exc.status == 401 and attempt == 0:
                    APP_TOKEN.clear()
                    continue
                raise


@app.get('/api/twitch/categories')
@login_required
def twitch_categories(user):
    query = request.args.get('q', '').strip()
    if not 2 <= len(query) <= 100:
        raise Error('Bitte zwei bis 100 Zeichen für die Suche eingeben.')
    result = twitch_app_api('search/categories?' + urllib.parse.urlencode({'query': query, 'first': 20}))
    return jsonify(categories=[{'id': item['id'], 'name': item['name']} for item in result.get('data', [])])


@app.get('/api/twitch/channel')
@login_required
def twitch_channel(user):
    result = twitch_user_api(user, 'channels?broadcaster_id={broadcaster}').get('data', [])
    if not result:
        raise Error('Dein Twitch-Kanal wurde nicht gefunden.')
    value = result[0]
    return jsonify(title=value['title'], game_id=value['game_id'], game_name=value['game_name'], name=value['broadcaster_name'])


@app.post('/api/twitch/channel')
@login_required
def twitch_channel_update(user):
    supplied = request.get_json() or {}
    change = {}
    if 'title' in supplied:
        title = str(supplied['title']).strip()
        if not title or len(title) > 140:
            raise Error('Der Streamtitel benötigt 1 bis 140 Zeichen.')
        change['title'] = title
    if 'game_id' in supplied:
        game = str(supplied['game_id'])
        if not re.fullmatch(r'[0-9]{1,20}', game):
            raise Error('Bitte eine Kategorie aus den Suchergebnissen auswählen.')
        if game != '0':
            if not twitch_app_api('games?id=' + game).get('data'):
                raise Error('Diese Twitch-Kategorie wurde nicht gefunden.')
        change['game_id'] = game
    if not change:
        raise Error('Bitte einen Titel oder eine Kategorie angeben.')
    twitch_user_api(user, 'channels?broadcaster_id={broadcaster}', change)
    return jsonify(ok=True)


def validate_twitch_sessions():
    while True:
        try:
            due = rows('SELECT t.user_id FROM twitch_auth t JOIN users u ON u.id=t.user_id WHERE u.active=1 AND t.validated<?', (time.time() - 3500,))
            for item in due:
                try:
                    validated_twitch_token(item['user_id'], force=True)
                except Error:
                    pass
        except Exception:
            logging.warning('Twitch-Berechtigungen konnten vorübergehend nicht geprüft werden.')
        time.sleep(60)


@app.post('/api/password')
@login_required
def password(user):
    body = request.get_json(silent=True)
    if not isinstance(body,dict) or not isinstance(body.get('current'),str) or not isinstance(body.get('password'),str):
        raise Error('Bitte das bisherige und das neue Passwort eingeben.')
    if len(body['password']) < 12:
        raise Error('Das neue Passwort benötigt mindestens 12 Zeichen.')
    with LOCK:
        fresh = rows('SELECT * FROM users WHERE id=?',(user['id'],))[0]
        if not check_password_hash(fresh['password'],body['current']):
            raise Error('Das bisherige Passwort stimmt nicht.')
        version = fresh['version']+1
        write('UPDATE users SET password=?,version=? WHERE id=?',(generate_password_hash(body['password']),version,user['id']))
        session['version'] = version
    return jsonify(ok=True)


def convert(uid, upload, display_name):
    user = rows('SELECT * FROM users WHERE id=?', (uid,))[0]
    destination = Path(user['offline']).parent / ('offline-' + secrets.token_hex(8) + '.mp4')
    try:
        write("UPDATE users SET upload_state='processing',upload_message='Video wird in 1080p30 / H.264 / AAC umgewandelt …' WHERE id=?", (uid,))
        probe = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_format', '-show_streams', '-of', 'json', str(upload)],
                               capture_output=True, timeout=20, text=True)
        meta = json.loads(probe.stdout)
        if not any(x.get('codec_type') == 'video' for x in meta['streams']) or not 0 < float(meta['format']['duration']) <= 300:
            raise Error('Das Video muss eine Videospur enthalten und höchstens fünf Minuten lang sein.')
        audio = '0:a:0' if any(x.get('codec_type') == 'audio' for x in meta['streams']) else '1:a:0'
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-i', str(upload),
                   '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-map', '0:v:0', '-map', audio,
                   '-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                   '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-threads', '1', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
                   '-b:v', '4500k', '-maxrate', '4500k', '-bufsize', '9000k', '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
                   '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-shortest', '-movflags', '+faststart', str(destination)]
        result = subprocess.run(command, capture_output=True, timeout=600)
        if result.returncode:
            raise Error('Das Video konnte nicht umgewandelt werden. Bitte eine normale MP4-Datei verwenden.')
        with LOCK:
            write('INSERT INTO videos(user_id,name,path,duration,size,created) VALUES (?,?,?,?,?,?)',
                  (uid, display_name, str(destination), float(meta['format']['duration']), destination.stat().st_size, int(time.time())))
            write("UPDATE users SET upload_state='ready',upload_message='Video ist in deiner Bibliothek. Zum Senden auswählen.' WHERE id=?", (uid,))
    except Exception as exc:
        destination.unlink(missing_ok=True)
        write("UPDATE users SET upload_state='error',upload_message=? WHERE id=?", (str(exc) if isinstance(exc, Error) else 'Video konnte nicht verarbeitet werden.', uid))
    finally:
        upload.unlink(missing_ok=True)
        with LOCK:
            UPLOAD_RESERVATIONS.pop(uid, None)


@app.post('/api/upload')
@login_required
def upload(user):
    file = request.files.get('video')
    if not file or not file.filename.lower().endswith('.mp4'):
        raise Error('Bitte eine MP4-Datei auswählen.')
    file.stream.seek(0, 2)
    incoming_size = file.stream.tell()
    file.stream.seek(0)
    if incoming_size > UPLOAD_LIMIT:
        raise Error('Maximal 500 MB pro Datei.')
    with LOCK:
        fresh = rows('SELECT upload_state FROM users WHERE id=?', (user['id'],))[0]
        if fresh['upload_state'] in ('queued', 'processing'):
            raise Error('Dein vorheriges Video wird noch verarbeitet.')
        if len(rows("SELECT id FROM users WHERE upload_state IN ('queued','processing')")) >= 2:
            raise Error('Der Server verarbeitet bereits zwei Videos. Bitte später erneut versuchen.')
        if shutil.disk_usage(DATA).free - sum(UPLOAD_RESERVATIONS.values()) < incoming_size + 350 * 1024 * 1024:
            raise Error('Auf dem Server ist zu wenig freier Speicher.')
        UPLOAD_RESERVATIONS[user['id']] = incoming_size
        write("UPDATE users SET upload_state='queued',upload_message='Upload wird empfangen …' WHERE id=?", (user['id'],))
    directory = DATA / 'uploads'
    directory.mkdir(exist_ok=True)
    target = directory / (secrets.token_hex(16) + '.mp4')
    submitted = False
    try:
        file.save(target)
        if target.stat().st_size > UPLOAD_LIMIT:
            raise Error('Maximal 500 MB pro Datei.')
        write("UPDATE users SET upload_state='queued',upload_message='Video wartet auf Verarbeitung …' WHERE id=?", (user['id'],))
        JOBS.submit(convert, user['id'], target, Path(file.filename).name[:120])
        submitted = True
    except Exception:
        target.unlink(missing_ok=True)
        write("UPDATE users SET upload_state='error',upload_message='Upload fehlgeschlagen.' WHERE id=?", (user['id'],))
        raise
    finally:
        if not submitted:
            with LOCK:
                UPLOAD_RESERVATIONS.pop(user['id'], None)
    return jsonify(ok=True)


@app.get('/api/admin')
@login_required
def admin_status(user):
    if not user['admin']:
        return jsonify(error='Keine Berechtigung.'), 403
    return jsonify(current_user_id=user['id'],users=rows('SELECT id,username,admin,active FROM users ORDER BY id'),
                   client_id=setting('client_id'), secret_set=bool(setting('client_secret')),
                   callback=PUBLIC + '/oauth/twitch/callback', public_url=PUBLIC, google_client_id=setting('google_client_id'), google_secret_set=bool(setting('google_client_secret')), google_callback=PUBLIC + '/oauth/youtube/callback')


def owned_video(user, vid):
    result = rows('SELECT * FROM videos WHERE id=? AND user_id=?', (vid, user['id']))
    if not result:
        from werkzeug.exceptions import NotFound
        raise NotFound()
    return result[0]


@app.get('/api/videos')
@login_required
def library(user):
    videos = rows('SELECT id,name,duration,size,created,overlay_text,overlay_style,browser_url FROM videos WHERE user_id=? ORDER BY created DESC,id DESC', (user['id'],))
    for video in videos:
        video['overlay_style'] = {**TEXT_DEFAULTS, **json.loads(video['overlay_style'] or '{}')}
        url = decrypt(video.pop('browser_url'))
        video['browser_enabled'] = bool(url)
        video['browser_host'] = urllib.parse.urlsplit(url).hostname if url else ''
    return jsonify(videos=videos, selected=user['selected_video_id'])


def recording_status(user):
    active = rows("SELECT id,source,status,started FROM recordings WHERE user_id=? AND status IN ('recording','finishing') ORDER BY id DESC LIMIT 1", (user['id'],))
    return {'active': active[0] if active else None, 'free_mb': shutil.disk_usage(DATA).free // 1048576}


def owned_recording(user, rid):
    result = rows('SELECT * FROM recordings WHERE id=? AND user_id=?', (rid, user['id']))
    if not result:
        from werkzeug.exceptions import NotFound
        raise NotFound()
    return result[0]


def finish_recording(rid, reason):
    result = rows('SELECT * FROM recordings WHERE id=?', (rid,))
    if not result:
        return
    recording = result[0]
    path = Path(recording['path'])
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-read_intervals', '%+20', '-count_packets', '-of', 'json', str(path)],
                               capture_output=True, text=True, timeout=20)
        info = json.loads(probe.stdout)
        duration = float(info['format'].get('duration', 0))
        if probe.returncode or duration <= 0 or not any(x.get('codec_type') == 'video' for x in info['streams']):
            raise ValueError()
        audio = int(any(x.get('codec_type') == 'audio' and int(x.get('nb_read_packets', '0') or 0) > 0 for x in info['streams']))
        write("UPDATE recordings SET status='ready',ended=?,duration=?,size=?,audio=?,message=? WHERE id=?",
              (time.time(), duration, path.stat().st_size, audio, reason, rid))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        write("UPDATE recordings SET status='error',ended=?,size=?,message=? WHERE id=?",
              (time.time(), path.stat().st_size if path.exists() else 0, 'Keine abspielbare Aufnahme entstanden. ' + reason, rid))


@app.get('/api/recordings')
@login_required
def recordings(user):
    entries=rows('SELECT id,name,source,status,started,ended,duration,size,message FROM recordings WHERE user_id=? ORDER BY id DESC',(user['id'],))
    return jsonify(recordings=[dict(row,source_label=MODEL.source_label(user,row['source'])) for row in entries],replay_id=user['replay_recording_id'])


@app.post('/api/recordings/start')
@login_required
def record_start(user):
    with LOCK:
        if recording_status(user)['active']:
            raise Error('Es läuft bereits eine Aufnahme oder deren Abschluss.')
        if shutil.disk_usage(DATA).free < 500 * 1048576:
            raise Error('Zu wenig Speicher. Für den Start müssen mindestens 500 MB frei sein.')
        source = str((request.get_json() or {}).get('source', 'live'))
        actual = MODEL.record_path(user,source)
        if source == 'source1' and user['replay_recording_id']:
            actual = user['prefix'] + 'replay'
        info = mtx('paths/get/' + actual)
        if not info.get('available'):
            raise Error('Die gewählte Quelle liefert gerade kein Signal.')
        directory = DATA / 'recordings' / user['username']
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (secrets.token_hex(16) + '.mp4')
        name = time.strftime('Aufnahme %Y-%m-%d %H:%M:%S')
        rid = write("INSERT INTO recordings(user_id,name,path,source,status,started) VALUES (?,?,?,?,?,?)",
                    (user['id'], name, str(path), source, 'recording', time.time()))
        command = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-rtsp_transport', 'tcp', '-timeout', '15000000',
                   '-analyzeduration', '1000000', '-probesize', '1000000',
                   *(['-use_wallclock_as_timestamps', '1'] if MODEL.is_program(source) else []),
                   '-i', RTSP + actual, '-map', '0:v:0', '-map', '0:a:0?', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-af', 'aresample=async=1:first_pts=0',
                   '-max_interleave_delta','1000000','-flush_packets','1','-frag_duration','1000000',
                   '-movflags', '+frag_keyframe+empty_moov+default_base_moof', '-f', 'mp4', str(path)]
        try:
            with path.with_suffix('.log').open('wb') as error_log:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=error_log)
            ENGINE.recorders[user['id']] = (rid, process)
        except OSError:
            write("UPDATE recordings SET status='error',message='Aufnahmedienst konnte nicht starten.' WHERE id=?", (rid,))
            raise Error('Aufnahme konnte nicht gestartet werden.') from None
    return jsonify(ok=True, id=rid)


@app.post('/api/recordings/stop')
@login_required
def record_stop(user):
    ENGINE.stop_record(user['id'], 'Manuell beendet.')
    return jsonify(ok=True)


@app.get('/media/recording/<int:rid>')
@login_required
def recording_file(user, rid):
    recording = owned_recording(user, rid)
    if recording['status'] != 'ready':
        raise Error('Diese Aufnahme ist noch nicht bereit.')
    return send_file(recording['path'], mimetype='video/mp4', conditional=True,
                     as_attachment=request.args.get('download') == '1', download_name=f"Aufnahme-{rid}.mp4")


@app.post('/api/recordings/<int:rid>/delete')
@login_required
def recording_delete(user, rid):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        recording = owned_recording(user, rid)
        if recording['status'] in ('recording', 'finishing') or user['replay_recording_id'] == rid:
            raise Error('Bitte Aufnahme und Wiederholung zuerst beenden.')
        path = Path(recording['path'])
        if path.parent != DATA / 'recordings' / user['username']:
            raise Error('Ungültiger Speicherort.')
        path.unlink(missing_ok=True)
        path.with_suffix('.log').unlink(missing_ok=True)
        write('DELETE FROM recordings WHERE id=? AND user_id=?', (rid, user['id']))
    return jsonify(ok=True)


@app.post('/api/recordings/<int:rid>/replay')
@login_required
def replay_start(user, rid):
    with LOCK:
        recording = owned_recording(user, rid)
        if recording['status'] != 'ready' or not Path(recording['path']).is_file():
            raise Error('Diese Aufnahme ist noch nicht abspielbereit.')
        write('UPDATE users SET replay_recording_id=? WHERE id=?', (rid, user['id']))
    return jsonify(ok=True)


@app.post('/api/replay/stop')
@login_required
def replay_stop(user):
    write('UPDATE users SET replay_recording_id=NULL WHERE id=?', (user['id'],))
    return jsonify(ok=True)


def renewal_period(user):
    value = user['renew_interval']
    active = configured_forwards(user)
    twitch = bool(active.get(output_path(user))) if any(active.values()) else any(d['kind'] == 'twitch' for d in destinations(user, True))
    return min(value, 172680) if value and twitch else value


def begin_renewal(user):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        config = yaml.safe_load(CONFIG.read_text())
        requested = renewal_forwards(user, config)
        if not requested:
            raise Error('Die Ausgänge sind gestoppt.')
        if user['renew_resume']:
            return
        for name in requested:
            mtx('config/paths/patch/' + name, {'forward': []})
        write('UPDATE users SET renew_resume=?,renew_next=0 WHERE id=?', (time.time() + user['renew_gap'], user['id']))


@app.post('/api/renewal')
@login_required
@expert_required
def renewal_settings(user):
    body = request.get_json() or {}
    try:
        interval, gap = int(body.get('interval', 0)), int(body.get('gap', 2))
    except (ValueError, TypeError):
        raise Error('Ungültiges Intervall.') from None
    if interval not in RENEW_INTERVALS or gap not in (2, 5, 10, 30, 95, 120):
        raise Error('Bitte ein angebotenes Intervall und eine angebotene Trennpause wählen.')
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        if user['renew_resume']:
            for name, targets in renewal_forwards(user).items():
                mtx('config/paths/patch/' + name, {'forward': targets})
        write('UPDATE users SET renew_interval=?,renew_gap=?,renew_next=0,renew_resume=0 WHERE id=?', (interval, gap, user['id']))
    return jsonify(ok=True)


@app.post('/api/renewal/now')
@login_required
@expert_required
def renewal_now(user):
    begin_renewal(user)
    return jsonify(ok=True)


@app.get('/media/video/<int:vid>')
@login_required
def video_file(user, vid):
    video = owned_video(user, vid)
    path = video['path'] if request.args.get('original') == '1' else video['rendered'] or video['path']
    return send_file(path, mimetype='video/mp4', conditional=True)


@app.post('/api/videos/<int:vid>/select')
@login_required
def select_video(user, vid):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        video = owned_video(user, vid)
        require_stopped(user)
        if user['upload_state'] in ('queued', 'processing'):
            raise Error('Bitte die laufende Videoverarbeitung abwarten.')
        path = video['rendered'] or video['path']
        if not Path(path).is_file():
            raise Error('Diese Videodatei ist nicht mehr vorhanden.')
        write('UPDATE users SET selected_video_id=?,offline=? WHERE id=?', (vid, path, user['id']))
    return jsonify(ok=True)


@app.post('/api/videos/<int:vid>/delete')
@login_required
def delete_video(user, vid):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        video = owned_video(user, vid)
        if user['selected_video_id'] == vid:
            raise Error('Bitte zuerst ein anderes Offline-Video auswählen. Das ausgewählte Video kann nicht gelöscht werden.')
        if user['upload_state'] in ('queued', 'processing'):
            raise Error('Bitte die laufende Videoverarbeitung abwarten.')
        # Only files inside the authenticated user's media directory can be removed.
        for filename in (video['path'], video['rendered']):
            if filename:
                path = Path(filename)
                if path.parent == DATA / 'media' / user['username']:
                    path.unlink(missing_ok=True)
        write('DELETE FROM videos WHERE id=? AND user_id=?', (vid, user['id']))
    return jsonify(ok=True)


def render_overlay(uid, vid, text, style):
    destination = None
    textfile = None
    try:
        user = rows('SELECT * FROM users WHERE id=?', (uid,))[0]
        video = owned_video(user, vid)
        if text:
            destination = Path(video['path']).with_name('overlay-' + secrets.token_hex(8) + '.mp4')
            textfile = destination.with_suffix('.txt')
            textfile.write_text(text)
            font = '/usr/share/fonts/truetype/dejavu/DejaVuSans' + ('-Bold' if style['bold'] else '') + '.ttf'
            draw = (f"drawtext=fontfile={font}:textfile={textfile}:expansion=none:fontcolor={style['color']}:fontsize={style['size']}:line_spacing=10:"
                    f"box={int(style['box'])}:boxcolor={style['background']}@{style['opacity']/100}:boxborderw=18:"
                    f"x=(w-text_w)*{style['x']/100}:y=(h-text_h)*{style['y']/100}")
            result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-i', video['path'],
                                     '-vf', draw, '-c:v', 'libx264', '-preset', 'veryfast', '-threads', '1',
                                     '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-b:v', '4500k', '-maxrate', '4500k',
                                     '-bufsize', '9000k', '-g', '60', '-sc_threshold', '0', '-c:a', 'copy', '-movflags', '+faststart', str(destination)],
                                    capture_output=True, timeout=600)
            if result.returncode:
                raise Error('Text konnte nicht eingerechnet werden. Video und Schriftinstallation prüfen.')
        with LOCK:
            fresh = rows('SELECT * FROM users WHERE id=?', (uid,))[0]
            if fresh['selected_video_id'] == vid:
                require_stopped(fresh)
            write('UPDATE videos SET overlay_text=?,overlay_style=?,rendered=? WHERE id=? AND user_id=?', (text, json.dumps(style), str(destination) if destination else '', vid, uid))
            if fresh['selected_video_id'] == vid:
                write('UPDATE users SET offline=? WHERE id=?', (str(destination) if destination else video['path'], uid))
            if video['rendered']:
                Path(video['rendered']).unlink(missing_ok=True)
            write("UPDATE users SET upload_state='ready',upload_message='Text-Overlay ist bereit.' WHERE id=?", (uid,))
    except Exception as exc:
        if destination:
            destination.unlink(missing_ok=True)
        write("UPDATE users SET upload_state='error',upload_message=? WHERE id=?", (str(exc) if isinstance(exc, Error) else 'Text konnte nicht verarbeitet werden.', uid))
    finally:
        if textfile:
            textfile.unlink(missing_ok=True)


@app.post('/api/videos/<int:vid>/overlay')
@login_required
def overlay(user, vid):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        owned_video(user, vid)
        if user['selected_video_id'] == vid:
            require_stopped(user)
        if user['upload_state'] in ('queued', 'processing'):
            raise Error('Bitte die laufende Videoverarbeitung abwarten.')
        body = request.get_json() or {}
        text = str(body.get('text', '')).strip()
        style = dict(TEXT_DEFAULTS)
        supplied = body.get('style', {})
        if not isinstance(supplied, dict):
            raise Error('Ungültige Texteinstellungen.')
        for key, lower, upper in [('x', 0, 100), ('y', 0, 100), ('size', 16, 120), ('opacity', 0, 100)]:
            try:
                style[key] = int(supplied.get(key, style[key]))
            except (TypeError, ValueError):
                raise Error('Ungültige Textposition oder Schriftgröße.') from None
            if not lower <= style[key] <= upper:
                raise Error('Textposition, Größe oder Transparenz liegt außerhalb des erlaubten Bereichs.')
        for key in ('color', 'background'):
            style[key] = str(supplied.get(key, style[key]))
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', style[key]):
                raise Error('Ungültige Farbe.')
        for key in ('bold', 'box'):
            style[key] = bool(supplied.get(key, style[key]))
        if len(text) > 200 or len(text.splitlines()) > 3 or any(len(line) > 65 for line in text.splitlines()):
            raise Error('Maximal 200 Zeichen, drei Zeilen und 65 Zeichen pro Zeile.')
        if shutil.disk_usage(DATA).free < 600 * 1024 * 1024:
            raise Error('Zu wenig Speicher für die Text-Version.')
        write("UPDATE users SET upload_state='processing',upload_message='Text wird einmalig ins Video eingerechnet …' WHERE id=?", (user['id'],))
        JOBS.submit(render_overlay, user['id'], vid, text, style)
    return jsonify(ok=True)


@app.post('/api/videos/<int:vid>/browser')
@login_required
def browser_settings(user, vid):
    with LOCK:
        user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
        video = owned_video(user, vid)
        if user['selected_video_id'] == vid:
            require_stopped(user)
        body = request.get_json() or {}
        url = ''
        if body.get('enabled'):
            url = str(body.get('url', '')).strip() or decrypt(video['browser_url'])
            validate_browser_url(url)
        write('UPDATE videos SET browser_url=? WHERE id=? AND user_id=?', (encrypt(url), vid, user['id']))
    return jsonify(ok=True)


def is_overlay_demo(url):
    try:
        parsed = urllib.parse.urlsplit(url)
        public = urllib.parse.urlsplit(PUBLIC)
        return (parsed.scheme in ('http', 'https') and parsed.hostname == public.hostname
                and (parsed.port or {'http': 80, 'https': 443}[parsed.scheme]) == (public.port or {'http': 80, 'https': 443}[public.scheme])
                and parsed.path.rstrip('/') == '/overlay-demo' and not parsed.query and not parsed.fragment
                and not parsed.username and not parsed.password)
    except (ValueError, KeyError):
        return False


def validate_browser_url(url):
    # The built-in demo is rendered from trusted local assets, never fetched.
    if is_overlay_demo(url):
        return PUBLIC + '/overlay-demo'
    try:
        parsed = urllib.parse.urlsplit(url)
        if len(url) > 4096 or any(c.isspace() for c in url) or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError()
        blocked = ingest_ips()
        addresses = resolve_host_ips(parsed.hostname, parsed.port or 443)
        if not addresses or any(blocked_target_ip(addr, blocked) for addr in addresses):
            raise ValueError()
    except (ValueError, OSError):
        raise Error('Bitte eine öffentliche HTTPS-Overlay-Adresse verwenden. Lokale und private Ziele sind gesperrt.') from None
    return url


@app.get('/overlay-demo')
def overlay_demo():
    return render_template('overlay-demo.html')


@app.post('/api/admin/users')
@login_required
def create_user(user):
    if not user['admin']:
        return jsonify(error='Keine Berechtigung.'), 403
    body = request.get_json() or {}
    uid = add_user(str(body.get('username', '')), str(body.get('password', '')))
    return jsonify(ok=True, id=uid)


@app.post('/api/admin/users/<int:uid>/toggle')
@login_required
def toggle_user(user, uid):
    if not user['admin'] or uid == user['id']:
        return jsonify(error='Diese Änderung ist nicht erlaubt.'), 403
    with LOCK:
        target = rows('SELECT * FROM users WHERE id=?', (uid,))
        if not target:
            raise Error('Benutzer nicht gefunden.')
        if target[0]['active']:
            forward(target[0], False)
        write('UPDATE users SET active=1-active,version=version+1 WHERE id=?', (uid,))
        reconcile()
    return jsonify(ok=True)


@app.post('/api/admin/oauth')
@login_required
def configure_oauth(user):
    if not user['admin']:
        return jsonify(error='Keine Berechtigung.'), 403
    body = request.get_json() or {}
    client = str(body.get('client_id', '')).strip()
    if not re.fullmatch(r'[A-Za-z0-9]{10,100}', client):
        raise Error('Bitte die Client-ID deiner Twitch-App eintragen.')
    set_setting('client_id', client)
    if body.get('client_secret'):
        set_setting('client_secret', str(body['client_secret']).strip())
    return jsonify(ok=True)


@app.get('/oauth/twitch')
@login_required
def oauth_start(user):
    require_stopped(user)
    client = setting('client_id')
    if not client or not setting('client_secret'):
        return redirect('/?notice=oauth_setup')
    if request.host.split(':')[0] != urllib.parse.urlsplit(PUBLIC).hostname or not request.is_secure:
        return redirect('/?notice=use_domain')
    state = secrets.token_urlsafe(32)
    session['oauth'] = {'state': state, 'time': time.time(), 'uid': user['id']}
    return redirect('https://id.twitch.tv/oauth2/authorize?' + urllib.parse.urlencode({
        'client_id': client, 'redirect_uri': PUBLIC + '/oauth/twitch/callback', 'response_type': 'code',
        'scope': ' '.join(sorted(TWITCH_SCOPES | CHAT_SCOPES)), 'state': state, 'force_verify': 'true'}))


@app.get('/oauth/twitch/callback')
@login_required
def oauth_callback(user):
    state = session.pop('oauth', {})
    if (state.get('uid') != user['id'] or time.time() - state.get('time', 0) > 600
            or not hmac.compare_digest(str(state.get('state', '')), request.args.get('state', ''))):
        return redirect('/?notice=oauth_failed')
    if request.args.get('error') or not request.args.get('code'):
        return redirect('/?notice=oauth_cancelled')
    token = ''
    stored = False
    try:
        require_stopped(user)
        client = setting('client_id')
        result = remote('https://id.twitch.tv/oauth2/token', urllib.parse.urlencode({
            'client_id': client, 'client_secret': setting('client_secret'), 'code': request.args['code'],
            'grant_type': 'authorization_code', 'redirect_uri': PUBLIC + '/oauth/twitch/callback'}).encode())
        token = result['access_token']
        headers = {'Authorization': 'Bearer ' + token, 'Client-Id': client}
        validate = remote('https://id.twitch.tv/oauth2/validate', headers={'Authorization': 'OAuth ' + token})
        if validate.get('client_id') != client or not TWITCH_SCOPES.issubset(set(validate.get('scopes', []))):
            raise Error('Twitch-Berechtigung fehlt.')
        account = remote('https://api.twitch.tv/helix/users', headers=headers)['data'][0]
        if account['id'] != validate.get('user_id') or not result.get('refresh_token'):
            raise Error('Twitch-Konto konnte nicht bestätigt werden.')
        key = remote('https://api.twitch.tv/helix/streams/key?broadcaster_id=' + account['id'], headers=headers)['data'][0]['stream_key']
        with LOCK, OAUTH_LOCK:
            require_stopped(user)
            previous = rows('SELECT * FROM twitch_auth WHERE user_id=?', (user['id'],))
            with db() as connection:
                connection.execute("UPDATE users SET output=?,output_kind='twitch',twitch_name=? WHERE id=?", (encrypt(TWITCH + '#' + key), account['display_name'], user['id']))
                connection.execute('INSERT OR REPLACE INTO twitch_auth(user_id,broadcaster_id,access,refresh,client_id,expires,validated,scopes) VALUES (?,?,?,?,?,?,?,?)',
                                   (user['id'], account['id'], encrypt(token), encrypt(result['refresh_token']), client,
                                    time.time() + validate.get('expires_in', result.get('expires_in', 3600)), time.time(), json.dumps(validate.get('scopes', []))))
                connection.execute('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,0) ON CONFLICT(user_id,kind) DO UPDATE SET endpoint=excluded.endpoint', (user['id'], 'twitch', encrypt(TWITCH + '#' + key)))
            stored = True
        if previous and decrypt(previous[0]['access']) != token:
            try:
                remote('https://id.twitch.tv/oauth2/revoke', urllib.parse.urlencode({
                    'client_id': previous[0]['client_id'], 'token': decrypt(previous[0]['access'])}).encode())
            except Error:
                pass
        return redirect('/?notice=oauth_ok')
    except Exception:
        return redirect('/?notice=oauth_failed')
    finally:
        # Successful grants are encrypted for title/category changes; failed ones are revoked.
        if token and not stored:
            try:
                remote('https://id.twitch.tv/oauth2/revoke', urllib.parse.urlencode({'client_id': setting('client_id'), 'token': token}).encode())
            except Error:
                pass


def hls_asset(user,path,asset):
    if '..' in asset or not re.fullmatch(r'[A-Za-z0-9_.-]+',asset) or not (asset.endswith(('.m3u8','.mp4','.ts')) or asset=='hls.min.js'):
        return '',404
    query = '?'+request.query_string.decode('ascii',errors='ignore') if request.query_string else ''
    try:
        req = urllib.request.Request(HLS+path+'/'+asset+query,headers=FEATURES.media_headers(user))
        with urllib.request.urlopen(req,timeout=12) as response:
            return Response(response.read(16*1024*1024),content_type=response.headers.get('Content-Type','application/octet-stream'))
    except OSError:
        return '',404


@app.get('/preview/<int:slot>/')
@login_required
def player(user,slot):
    preview_path(user,slot)
    return render_template('player.html',slot=slot)


@app.get('/preview/<int:slot>/<asset>')
@login_required
def preview(user,slot,asset):
    return hls_asset(user,preview_path(user,slot),asset)


@app.get('/preview/source/<key>/')
@login_required
def source_player(user,key):
    MODEL.source(user,key)
    return render_template('player.html')


@app.get('/preview/source/<key>/<asset>')
@login_required
def source_preview(user,key,asset):
    MODEL.source(user,key)
    actual='replay' if key=='source1' and user['replay_recording_id'] else key
    return hls_asset(user,user['prefix']+actual,asset)


@app.get('/program/<pid>/')
@login_required
def program_player(user,pid):
    MODEL.program(user,pid)
    return render_template('player.html')


@app.get('/program/<pid>/<asset>')
@login_required
def program_asset(user,pid,asset):
    return hls_asset(user,MODEL.program(user,pid)['path'],asset)


class Engine:
    def __init__(self):
        self.snapshot = {}
        self.relays = {}
        self.health = {}
        self.retry = {}
        self.browser_jobs = {}
        self.output_samples = {}
        self.ingest_samples = {}
        self.recorders = {}
        self.replays = {}
        self.running = True
        self.thread = None

    def prune_caches(self, active):
        for uid in list(self.snapshot):
            if uid not in active:
                self.snapshot.pop(uid, None)
        for store in (self.output_samples, MEDIA_STATS_CACHE):
            for uid in list(store):
                if uid not in active:
                    store.pop(uid, None)
        for key in list(self.retry):
            if relay_owner(key[0]) not in active:
                self.retry.pop(key, None)
        for store in (self.health, self.ingest_samples):
            for key in list(store):
                if key[0] not in active:
                    store.pop(key, None)
        if 'CHAT' in globals() and CHAT is not None:
            CHAT.prune(active)

    def stop_record(self, uid, reason):
        with LOCK:
            running = self.recorders.pop(uid, None)
            if not running:
                return
            rid, process = running
            write("UPDATE recordings SET status='finishing',message=? WHERE id=?", (reason, rid))
            if process.poll() is None:
                try:
                    process.stdin.write(b'q\n')
                    process.stdin.flush()
                except (OSError, AttributeError):
                    process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            if process.stdin:
                process.stdin.close()
            threading.Thread(target=finish_recording, args=(rid, reason), daemon=True).start()

    def stop_replay(self, uid):
        previous = self.replays.pop(uid, None)
        if previous and previous[1].poll() is None:
            previous[1].terminate()
            try:
                previous[1].wait(timeout=3)
            except subprocess.TimeoutExpired:
                previous[1].kill()
                previous[1].wait()

    def manage_replay(self, user):
        uid = user['id']
        previous = self.replays.get(uid)
        if previous and previous[1].poll() is not None:
            self.replays.pop(uid)
            if user['replay_recording_id'] == previous[0]:
                write('UPDATE users SET replay_recording_id=NULL WHERE id=? AND replay_recording_id=?', (uid, previous[0]))
                user['replay_recording_id'] = None
            previous = None
        rid = user['replay_recording_id']
        if previous and previous[0] != rid:
            self.stop_replay(uid)
            previous = None
        if rid and not previous:
            found = rows("SELECT * FROM recordings WHERE id=? AND user_id=? AND status='ready'", (rid, uid))
            if not found or not Path(found[0]['path']).is_file():
                write('UPDATE users SET replay_recording_id=NULL WHERE id=?', (uid,))
                user['replay_recording_id'] = None
                return 'error'
            recording = found[0]
            video_filter = ('scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,'
                            'drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text=Wiederholung:'
                            'fontsize=48:fontcolor=white:box=1:boxcolor=black@0.65:boxborderw=12:x=30:y=30')
            command = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error', '-re', '-analyzeduration', '1000000', '-probesize', '32768', '-i', recording['path'],
                       '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-map', '0:v:0', '-map', '0:a:0' if recording['audio'] else '1:a:0',
                       '-vf', video_filter, '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-threads', '1', '-profile:v', 'high',
                       '-pix_fmt', 'yuv420p', '-b:v', '4500k', '-maxrate', '4500k', '-bufsize', '9000k', '-g', '60',
                       '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '160k', '-shortest', '-max_interleave_delta', '1000000', '-flush_packets', '1', '-f', 'rtsp', '-rtsp_transport', 'tcp',
                       RTSP + user['prefix'] + 'replay']
            with (DATA / f'replay-{uid}.log').open('wb') as error_log:
                self.replays[uid] = (rid, subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=error_log))
        return 'running' if user['replay_recording_id'] else 'off'

    def manage_renewal(self, user, state):
        with LOCK:
            user = rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
            requested = renewal_forwards(user)
            if not requested:
                if user['renew_next'] or user['renew_resume']:
                    write('UPDATE users SET renew_next=0,renew_resume=0 WHERE id=?', (user['id'],))
                return False
            if user['renew_resume']:
                if time.time() >= user['renew_resume']:
                    for name, targets in requested.items():
                        mtx('config/paths/patch/' + name, {'forward': targets})
                    write('UPDATE users SET renew_resume=0,renew_last=?,renew_next=? WHERE id=?',
                          (time.time(), time.time() + renewal_period(user) if user['renew_interval'] else 0, user['id']))
                return True
            if user['renew_interval'] and state == 'forwarding':
                if not user['renew_next']:
                    write('UPDATE users SET renew_next=? WHERE id=?', (time.time() + renewal_period(user), user['id']))
                elif time.time() >= user['renew_next']:
                    begin_renewal(user)
                    return True
            return False

    def stop_relay(self, uid):
        previous = self.relays.pop(uid, None)
        if previous and previous[1].poll() is None:
            previous[1].terminate()
            try:
                previous[1].wait(timeout=2)
            except subprocess.TimeoutExpired:
                previous[1].kill()
                previous[1].wait()
        job = self.browser_jobs.pop(uid, None)
        if job:
            # Each job has a private HOME. Stopping one renderer must not kill
            # another user's browser after the configured capacity is increased.
            expected_home = ('HOME=' + str(job['directory'])).encode()
            for entry in Path('/proc').glob('[0-9]*/environ'):
                try:
                    if entry.stat().st_uid == job['uid'] and expected_home in entry.read_bytes().split(b'\0'):
                        os.kill(int(entry.parent.name), signal.SIGTERM)
                except (OSError, ValueError):
                    pass
            shutil.rmtree(job['directory'], ignore_errors=True)

    def start_browser(self, user, url, destination, key=None):
        key = user['id'] if key is None else key
        identity = pwd.getpwnam(BROWSER_USER)
        root = BROWSER_ROOT
        directory = root / secrets.token_hex(12)
        directory.mkdir(mode=0o700)
        os.chown(directory, identity.pw_uid, identity.pw_gid)
        source = Path(user['offline'])
        stat = source.stat()
        if shutil.disk_usage(root).free < stat.st_size + 128 * 1024 * 1024:
            shutil.rmtree(directory, ignore_errors=True)
            raise Error('Zu wenig Speicher für die Browserquelle.')
        link = directory / 'clip.mp4'
        job = {'directory': directory, 'source': source, 'uid': identity.pw_uid}
        self.browser_jobs[key] = job
        try:
            shutil.copyfile(source, link)
            os.chown(link, identity.pw_uid, identity.pw_gid)
            os.chmod(link, 0o600)
            environment = {**os.environ, 'HOME': str(directory), 'XDG_CACHE_HOME': str(directory / 'cache')}
            blocked = sorted(ingest_ips())
            pin_rules = []
            demo = is_overlay_demo(url)
            if not demo:
                parsed = urllib.parse.urlsplit(url)
                try:
                    pinned = sorted(resolve_host_ips(parsed.hostname, parsed.port or 443))
                except OSError:
                    pinned = []
                if not pinned or any(blocked_target_ip(addr, set(blocked)) for addr in pinned):
                    raise Error('Bitte eine öffentliche HTTPS-Overlay-Adresse verwenden. Lokale und private Ziele sind gesperrt.')
                pin_rules = ['MAP ' + parsed.hostname + ' ' + pinned[0]]
                if parsed.hostname.startswith('www.'):
                    pin_rules.append('MAP ' + parsed.hostname[4:] + ' ' + pinned[0])
            process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('browser_overlay.py'))],
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       user=identity.pw_uid, group=identity.pw_gid, extra_groups=[], env=environment)
            data = {'clip': str(link), 'url': url, 'destination': destination,
                    'ingest_ips': blocked, 'fps': browser_fps(), 'host_resolver_rules': ', '.join(pin_rules)}
            if demo:
                base = Path(__file__).parent
                html = (base / 'templates/overlay-demo.html').read_text()
                html = html.replace('<link rel="stylesheet" href="/static/overlay-demo.css">', '<style>' + (base / 'static/overlay-demo.css').read_text() + '</style>')
                html = html.replace('<script src="/static/overlay-demo.js" defer></script>', '<script>window.addEventListener("DOMContentLoaded",function(){' + (base / 'static/overlay-demo.js').read_text() + '});</script>')
                data['demo_html'] = html
            process.stdin.write((json.dumps(data) + '\n').encode())
            process.stdin.close()
            return process
        except Exception:
            self.stop_relay(key)
            raise

    def program_tick(self,user,program,healthy,all_paths,config,enabled,now,browser_url):
        key = relay_key(user,program['id'])
        healthy = [name for name in healthy if now >= self.retry.get((key,name),0)]
        offline_key = ('@browser:' if browser_url else '@offline:')+user['offline']
        browser_status = 'off'
        other_browser = bool(browser_url) and key not in self.browser_jobs and len(self.browser_jobs)>=browser_capacity()
        if browser_url:
            browser_status = 'waiting' if other_browser else 'ready'
        live = all_paths.get(program['path'],{})
        local_demand = bool(live.get('readers')) or bool(config['paths'].get(program['path'],{}).get('record'))
        active_record = rows("SELECT source FROM recordings WHERE user_id=? AND status='recording'",(user['id'],))
        local_demand = local_demand or any(row['source']==('live' if program['id']=='main' else program['id']) for row in active_record)
        if program['id']!='main' and not (enabled or local_demand):
            healthy = []
        offline_allowed = bool(program['sources']) and (enabled or local_demand)
        if user['replay_recording_id'] and 'source1' in program['sources']:
            offline_allowed = False
        desired = healthy[0] if healthy else offline_key if offline_allowed and not other_browser and now>=self.retry.get((key,offline_key),0) else None
        previous = self.relays.get(key)
        if previous and previous[1].poll() is not None:
            self.retry[(key,previous[0])] = now+10
            self.stop_relay(key);previous=None
            desired = next((name for name in healthy if now>=self.retry.get((key,name),0)),None)
        if (previous[0] if previous else None)!=desired:
            self.stop_relay(key)
            if desired:
                if desired.startswith('@browser:'):
                    try:
                        self.relays[key] = (desired,self.start_browser(user,browser_url,RTSP+program['path'],key=key))
                    except Exception:
                        self.retry[(key,desired)] = now+30;browser_status='error'
                else:
                    input_args = ['-re','-stream_loop','-1','-i',user['offline']] if desired.startswith('@offline:') else [
                        '-rtsp_transport','tcp','-timeout','15000000','-analyzeduration','1000000','-probesize','1000000','-i',RTSP+desired]
                    command = ['ffmpeg','-hide_banner','-nostdin','-loglevel','error']+input_args+[
                        '-map','0:v:0','-map','0:a:0?',
                        '-vf','scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30',
                        '-c:v','libx264','-preset','veryfast','-tune','zerolatency','-profile:v','baseline',
                        '-pix_fmt','yuv420p','-bf','0','-g','30','-threads','2','-b:v','4500k','-maxrate','4500k','-bufsize','9000k',
                        '-c:a','aac','-b:a','160k','-ar','48000','-ac','2','-af','aresample=async=1:first_pts=0',
                        '-max_interleave_delta','1000000','-flush_packets','1','-f','rtsp','-rtsp_transport','tcp',RTSP+program['path']]
                    suffix = '' if program['id']=='main' else '-'+program['id']
                    with (DATA/f"relay-{user['id']}{suffix}.log").open('wb') as log:
                        self.relays[key] = (desired,subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log))
        current = self.relays.get(key)
        actual = current[0] if current and live.get('online') else None
        selected_source = next((source for source in program['sources'] if actual == user['prefix']+('replay' if source=='source1' and user['replay_recording_id'] else source)),None)
        offline_playing = bool(actual and actual.startswith(('@offline:','@browser:')))
        if browser_url and not healthy:
            if actual and actual.startswith('@browser:'):
                browser_status = 'live'
            elif now<self.retry.get((key,offline_key),0):
                browser_status = 'error'
        return {'id':program['id'],'selected_source':selected_source,'offline_playing':offline_playing,
                'available':bool(live.get('available')),'browser_status':browser_status}

    def tick(self):
        now = time.monotonic()
        all_paths = {p['name']: p for p in list_items(mtx,'paths/list')}
        users = rows('SELECT * FROM users WHERE active=1')
        config = yaml.safe_load(CONFIG.read_text())
        active_ids = {u['id'] for u in users}
        self.prune_caches(active_ids)
        FEATURES.program_preview.monitor(users, all_paths)
        for uid, (rid, process) in list(self.recorders.items()):
            if uid not in active_ids:
                self.stop_record(uid, 'Benutzer deaktiviert.')
            elif process.poll() is not None:
                self.stop_record(uid, 'Quelle beendet oder unterbrochen.')
            elif shutil.disk_usage(DATA).free < 350 * 1048576:
                self.stop_record(uid, 'Automatisch beendet: weniger als 350 MB freier Speicher.')
        for uid in list(self.replays):
            if uid not in active_ids:
                self.stop_replay(uid)
        for key in list(self.relays):
            if relay_owner(key) not in active_ids:
                self.stop_relay(key)
        for user in users:
            uid = user['id']
            names = paths(user)
            replay_state = self.manage_replay(user)
            catalog = MODEL.sources(user)
            inputs = input_paths(user)
            if user['replay_recording_id']:
                inputs[0] = user['prefix'] + 'replay'
            source_info, healthy_by_source = [], {}
            for index, name in enumerate(inputs):
                path = all_paths.get(name, {})
                count = path.get('inboundBytes', 0)
                ident = (path.get('onlineTime'), (path.get('source') or {}).get('id'))
                key = (uid, name)
                old = self.health.get(key)
                if not old or old['identity'] != ident or count < old['count']:
                    old = {'identity': ident, 'count': count, 'change': now, 'since': None, 'sample': now}
                elapsed = max(.1, now - old['sample'])
                bitrate = max(0, count - old['count']) * 8 / elapsed / 1_000_000
                if count > old['count']:
                    old['change'] = now
                    if old['since'] is None:
                        old['since'] = now
                online = bool(path.get('online'))
                stalled = now - old['change'] >= 5
                if not online or stalled:
                    old['since'] = None
                manual_replay = bool(index == 0 and user['replay_recording_id'])
                if catalog[index]['enabled'] and online and old['since'] is not None and (manual_replay or now - old['since'] >= 3):
                    healthy_by_source[catalog[index]['key']] = name
                old.update(count=count, sample=now)
                self.health[key] = old
                source_info.append({**{key:catalog[index][key] for key in ('key','label','protocol','priority','fixed','enabled')},'state': 'offline' if not online else 'stalled' if stalled else 'online',
                                    'mbps': round(bitrate, 2), 'tracks': path.get('tracks', [])})
            FEATURES.monitor_recordings(user)
            desired_forwards = configured_forwards(user, config)
            enabled = any(desired_forwards.values())
            state, forwarders, output_states = 'stopped', [], {}
            for kind in output_kinds(user):
                name = output_path(user, kind)
                target_state = 'stopped'
                if desired_forwards[name]:
                    try:
                        items = mtx('paths/forward-dests/list?path=' + urllib.parse.quote(name, safe='') + '&itemsPerPage=10')['items']
                        target_state = 'forwarding' if any(x['state'] == 'forwarding' for x in items) else 'error' if any(x['state'] == 'error' for x in items) else 'connecting'
                        forwarders.extend(items)
                    except Error:
                        target_state = 'connecting'
                output_states[kind] = target_state
            any_forwarding = any(x == 'forwarding' for x in output_states.values())
            if enabled:
                state = 'forwarding' if any_forwarding else 'error' if any(x == 'error' for x in output_states.values()) else 'connecting'
            renewing = self.manage_renewal(user, state)
            if renewing:
                enabled = True
                state = 'renewing'
                for name in renewal_forwards(user):
                    for kind in output_kinds(user):
                        if output_path(user, kind) == name:
                            output_states[kind] = 'renewing'
            selected_video = rows('SELECT browser_url FROM videos WHERE id=? AND user_id=?',(user['selected_video_id'],uid))
            browser_url = decrypt(selected_video[0]['browser_url']) if selected_video else ''
            program_states = []
            programs = MODEL.programs(user)
            active_keys = {relay_key(user,program['id']) for program in programs}
            for key in list(self.relays):
                if relay_owner(key)==uid and key not in active_keys:
                    self.stop_relay(key)
            for program in programs:
                eligible = [healthy_by_source[source] for source in program['sources'] if source in healthy_by_source]
                active_output = any(desired_forwards.get(output_path(user,kind)) for kind in program['targets'])
                program_states.append(self.program_tick(user,program,eligible,all_paths,config,active_output,now,browser_url))
            main = next(program for program in program_states if program['id']=='main')
            selected = next((i+1 for i,row in enumerate(catalog) if row['key']==main['selected_source']),0)
            offline_playing,browser_status = main['offline_playing'],main['browser_status']
            live = all_paths.get(names[2],{})
            # Count only external inputs and the actual destination, never preview readers.
            incoming = 0
            for input_name in input_paths(user):
                path = all_paths.get(input_name, {})
                identity = (path.get('onlineTime'), (path.get('source') or {}).get('id'))
                counter = path.get('inboundBytes', 0)
                prior = self.ingest_samples.get((uid, input_name))
                if prior and prior[0] == identity and counter >= prior[1] and now > prior[2]:
                    incoming += (counter - prior[1]) * 8 / (now - prior[2]) / 1_000_000
                self.ingest_samples[(uid, input_name)] = (identity, counter, now)
            identity = tuple(sorted(str(f['id']) for f in forwarders))
            sent = sum(f.get('outboundBytes', 0) for f in forwarders)
            previous_output = self.output_samples.get(uid)
            outgoing = 0
            if any_forwarding and previous_output and previous_output[0] == identity and sent >= previous_output[1] and now > previous_output[2]:
                outgoing = (sent - previous_output[1]) * 8 / (now - previous_output[2]) / 1_000_000
            self.output_samples[uid] = (identity, sent, now)
            update_stream_time(user, 'forwarding' if any_forwarding else state, enabled)
            with LOCK:
                self.snapshot[uid] = {'ok': True, 'receive_mbps': round(incoming, 3), 'send_mbps': round(outgoing, 3), 'output_states': output_states, 'sources': source_info, 'selected': selected,
                                      'available': bool(live.get('available')), 'enabled': enabled, 'state': state, 'offline_playing': offline_playing,
                                      'browser_status': browser_status, 'replay_state': replay_state,'programs':program_states}
        READY.set()

    def run(self):
        while self.running:
            try:
                self.tick()
            except Exception as exc:
                logging.warning('MediaMTX-Abgleich fehlgeschlagen (%s).', type(exc).__name__)
                for uid, relay in list(self.relays.items()):
                    if relay[0].startswith(('@offline:', '@browser:')):
                        self.stop_relay(uid)
                READY.clear()
                with LOCK:
                    for user in rows('SELECT id FROM users'):
                        self.snapshot[user['id']] = {'ok': False, 'error': 'MediaMTX ist gerade nicht erreichbar. Status wird erneut geprüft.'}
            time.sleep(1)
        for uid in list(self.relays):
            self.stop_relay(uid)
        for uid in list(self.recorders):
            self.stop_record(uid, 'Aufnahmedienst beendet.')
        for uid in list(self.replays):
            self.stop_replay(uid)
        FEATURES.program_preview.close()


ENGINE = Engine()
from routing_model import RoutingModel, job_key as relay_key, owner as relay_owner
MODEL = RoutingModel(sys.modules[__name__])
initialize()
from integrations import install_integrations
CHAT = install_integrations(sys.modules[__name__])
from media_features import MediaFeatures
FEATURES = MediaFeatures(sys.modules[__name__])
from account_features import install_account_routes
install_account_routes(sys.modules[__name__])
if os.getenv('STREAMDESK_ENGINE', '1') == '1':
    reconcile()
    runtime = BROWSER_ROOT
    if runtime.is_dir():
        for directory in runtime.iterdir():
            if directory.is_dir() and re.fullmatch(r'[a-f0-9]{24}', directory.name):
                shutil.rmtree(directory, ignore_errors=True)
    write("UPDATE users SET upload_state='error',upload_message='Verarbeitung wurde durch einen Neustart unterbrochen.' WHERE upload_state IN ('queued','processing')")
    write('UPDATE twitch_auth SET validated=0')
    write('UPDATE users SET replay_recording_id=NULL')
    for recording in rows("SELECT id FROM recordings WHERE status IN ('recording','finishing')"):
        write("UPDATE recordings SET status='finishing' WHERE id=?", (recording['id'],))
        threading.Thread(target=finish_recording, args=(recording['id'], 'Nach Serverneustart wiederhergestellt; keine automatische Fortsetzung.'), daemon=True).start()
    threading.Thread(target=probe_video_durations, daemon=True).start()
    threading.Thread(target=validate_twitch_sessions, daemon=True).start()
    ENGINE.thread = threading.Thread(target=ENGINE.run, daemon=True)
    ENGINE.thread.start()
