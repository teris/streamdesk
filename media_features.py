"""Opt-in MediaMTX controls, scoped to the authenticated StreamDesk tenant."""
import base64
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Response, jsonify, render_template, request, send_file, session
import yaml


class MediaFeatures:
    def __init__(self, core):
        self.c = core
        self.native_root = Path(os.getenv('STREAMDESK_NATIVE_ROOT', str(core.DATA.parent / (core.DATA.name + '-native'))))
        self.rtc_sessions = {}
        self.last_disk_check = {}
        from program_preview import ProgramPreview
        self.program_preview = ProgramPreview(core)
        with core.db() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS viewer_links(
                user_id INTEGER PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, token TEXT NOT NULL)''')
        self.install_routes()
        from routing_features import RoutingFeatures
        from playback_features import PlaybackFeatures
        self.routing = RoutingFeatures(core, self)
        self.playback = PlaybackFeatures(core, self)

    def body(self):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise self.c.Error('Bitte ein JSON-Objekt senden.', http_status=400)
        return body

    def boolean(self, body, name):
        value = body.get(name)
        if type(value) is not bool:
            raise self.c.Error('Ungültiger Schalter: ' + name, http_status=400)
        return value

    def config(self):
        return yaml.safe_load(self.c.CONFIG.read_text())

    def apply_paths(self, changes):
        """Keep file and runtime consistent, including failures while persisting."""
        c = self.c
        with c.LOCK:
            config = self.config()
            defaults = {'record': False, 'recordFormat': 'fmp4', 'recordPath': './recordings/%path/%Y-%m-%d_%H-%M-%S-%f_%z',
                        'recordSegmentDuration': '1h', 'recordDeleteAfter': '1d'}
            defaults.update(config.get('pathDefaults') or {})
            previous = {name: {key: config['paths'][name].get(key, defaults.get(key))
                               for key in change} for name, change in changes.items()}
            applied = []
            try:
                for name, change in changes.items():
                    c.mtx('config/paths/patch/' + name, change)
                    applied.append(name)
                    config['paths'][name].update(change)
                c.atomic(c.CONFIG, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
            except (OSError, c.Error):
                for name in reversed(applied):
                    try:
                        c.mtx('config/paths/patch/' + name, previous[name])
                    except c.Error:
                        c.logging.error('MediaMTX-Rücknahme fehlgeschlagen; Abgleich mit gespeicherter Konfiguration erforderlich.')
                raise c.Error('MediaMTX-Änderung fehlgeschlagen. Die gespeicherte Konfiguration bleibt erhalten.') from None

    def apply_global(self, change, defaults):
        c = self.c
        with c.LOCK:
            config = self.config()
            previous = {key:config.get(key, defaults[key]) for key in change}
            c.mtx('config/global/patch', change)
            config.update(change)
            try:
                c.atomic(c.CONFIG, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
            except OSError:
                c.mtx('config/global/patch', previous)
                raise c.Error('MediaMTX-Konfiguration konnte nicht gespeichert werden.') from None

    def recording_directory(self, user, source, create=False):
        directory = self.native_root / user['username'] / user['prefix'] / source
        if not directory.resolve().is_relative_to((self.native_root / user['username']).resolve()):
            raise self.c.Error('Ungültiger Aufnahmepfad.', http_status=400)
        folder = self.native_root
        for part in directory.relative_to(self.native_root).parts:
            folder = folder / part
            if folder.is_symlink():
                raise self.c.Error('Aufnahmeverzeichnis nicht verfügbar.', http_status=404)
        if create:
            if not self.native_root.is_dir():
                raise self.c.Error('Das Verzeichnis für native Aufnahmen fehlt. Bitte den Installer im Update-Modus ausführen.')
            owner = self.native_root.stat()
            folder = self.native_root
            for part in directory.relative_to(self.native_root).parts:
                folder = folder / part
                folder.mkdir(mode=0o750, exist_ok=True)
                if os.geteuid() == 0:
                    os.chown(folder, owner.st_uid, owner.st_gid)
        if not directory.resolve().is_relative_to(self.native_root.resolve()):
            raise self.c.Error('Ungültiger Aufnahmepfad.', http_status=400)
        return directory

    def monitor_recordings(self, user):
        now = time.monotonic()
        if now - self.last_disk_check.get(user['id'], -60) < 10:
            return
        self.last_disk_check[user['id']] = now
        if self.native_root.is_dir() and shutil.disk_usage(self.native_root).free < 350 * 1048576:
            with self.c.LOCK:
                config = self.config()
                changes = {user['prefix'] + source: {'record': False} for source in self.c.MODEL.record_sources(user)
                           if config['paths'].get(user['prefix'] + source, {}).get('record')}
                if changes:
                    self.apply_paths(changes)
                    self.c.logging.warning('Native Aufnahmen wegen geringem freien Speicher gestoppt (Benutzer-ID %s).', user['id'])

    def rtc_base(self):
        config = self.config()
        if not config.get('webrtc', True):
            raise self.c.Error('WebRTC ist deaktiviert. Ein Administrator kann es unter Expertenmodus → Protokolle & WebRTC aktivieren.')
        override = os.getenv('MEDIAMTX_WEBRTC')
        if override:
            return override.rstrip('/') + '/'
        address = urllib.parse.urlsplit('tcp://' + str(config.get('webrtcAddress', ':8889')))
        host = address.hostname or '127.0.0.1'
        if host in ('0.0.0.0', '::'):
            host = '127.0.0.1'
        host = '[' + host + ']' if ':' in host else host
        return ('https' if config.get('webrtcEncryption') else 'http') + '://' + host + ':' + str(address.port or 8889) + '/'

    def media_headers(self, user):
        credentials = self.c.media_username(user) + ':' + self.c.decrypt(user['media_secret'])
        return {'Authorization': 'Basic ' + base64.b64encode(credentials.encode()).decode()}

    def viewer(self, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,64}', token):
            raise self.c.Error('Dieser Zuschauer-Link ist nicht verfügbar.', http_status=404)
        found = self.c.rows('''SELECT users.* FROM viewer_links JOIN users ON users.id=viewer_links.user_id
            WHERE viewer_links.token_hash=? AND users.active=1''', (hashlib.sha256(token.encode()).hexdigest(),))
        if not found:
            raise self.c.Error('Dieser Zuschauer-Link ist nicht verfügbar.', http_status=404)
        return found[0]

    def install_routes(self):
        c, app = self.c, self.c.app
        login = c.login_required
        expert = lambda fn: login(c.expert_required(fn))

        @app.post('/api/expert-mode')
        @login
        def expert_mode(user):
            enabled = self.boolean(self.body(), 'enabled')
            session['expert_mode'] = enabled
            return jsonify(ok=True, expert_mode=enabled)

        @app.get('/api/expert-mode')
        @login
        def expert_mode_status(user):
            return jsonify(expert_mode=session.get('expert_mode') is True)

        @app.post('/api/preferences')
        @login
        def preferences(user):
            theme = self.body().get('theme')
            if theme not in ('system', 'dark', 'light'):
                raise c.Error('Ungültiges Theme.', http_status=400)
            c.write('UPDATE users SET theme=? WHERE id=?', (theme, user['id']))
            return jsonify(ok=True, theme=theme)

        @app.post('/api/sources/mode')
        @expert
        def source_mode(user):
            mode = self.body().get('mode')
            if mode != 'auto':
                raise c.Error('Die Quellenwahl folgt jetzt der festen Priorität je Ausgang. Zuordnungen unter Quellen & Routing bearbeiten.',http_status=400)
            with c.LOCK:
                c.write('UPDATE users SET source_mode=? WHERE id=?', (mode, user['id']))
                if mode not in ('auto', 'source1'):
                    c.write('UPDATE users SET replay_recording_id=NULL WHERE id=?', (user['id'],))
            return jsonify(ok=True)

        @app.post('/api/outputs/<kind>/<operation>')
        @expert
        def output_control(user, kind, operation):
            if not c.valid_output_kind(kind) or kind not in c.output_kinds(user) or operation not in ('start', 'stop'):
                raise c.Error('Unbekanntes Streamingziel oder unbekannte Aktion.', http_status=404)
            with c.LOCK:
                fresh = c.rows('SELECT * FROM users WHERE id=?', (user['id'],))[0]
                if fresh['renew_resume']:
                    raise c.Error('Bitte die laufende Neuverbindung abwarten oder alle Ausgänge stoppen.')
                if operation == 'start':
                    if not c.READY.is_set():
                        raise c.Error('MediaMTX wird noch verbunden.')
                    if fresh['upload_state'] in ('queued', 'processing') or not Path(fresh['offline']).is_file():
                        raise c.Error('Bitte ein verfügbares Offline-Video auswählen und die Verarbeitung abwarten.')
                c.forward(fresh, operation == 'start', kind=kind)
            return jsonify(ok=True)

        @app.get('/api/expert')
        @expert
        def expert_status(user):
            config = self.config()
            runtime = None
            if c.READY.is_set():
                try:
                    runtime = c.mtx('config/global/get')
                except c.Error:
                    pass
            actual = runtime if isinstance(runtime, dict) else config
            own_auth = next((entry for entry in actual.get('authInternalUsers', []) if entry.get('user') == c.media_username(user)), {})
            credential = own_auth.get('pass')
            if credential == '<redacted>':
                # The Control API intentionally hides passwords; compare our saved credential.
                saved_auth = next((entry for entry in config.get('authInternalUsers', []) if entry.get('user') == c.media_username(user)), {})
                credential = saved_auth.get('pass')
            auth_ready = credential == c.decrypt(user['media_secret']) and any(
                permission.get('action') == 'publish' and permission.get('path') == c.paths(user)[1]
                for permission in own_auth.get('permissions', []))
            native = []
            for source in c.MODEL.active_record_sources(user):
                path = user['prefix'] + source
                settings = config['paths'].get(path, {})
                native.append({'source':source,'label':c.MODEL.source_label(user,source), 'enabled': bool(settings.get('record', False)),
                               'format': settings.get('recordFormat', 'fmp4'),
                               'segment': settings.get('recordSegmentDuration', '1h'),
                               'retention': settings.get('recordDeleteAfter', '1d')})
            links = c.rows('SELECT token FROM viewer_links WHERE user_id=?', (user['id'],))
            return jsonify(native=native, viewer_url=c.PUBLIC + '/watch/' + c.decrypt(links[0]['token']) + '/' if links else '',
                           webrtc=bool(config.get('webrtc', True)),
                           webrtc_runtime=bool(runtime.get('webrtc', True)) if isinstance(runtime, dict) else None,
                           webrtc_hosts=config.get('webrtcAdditionalHosts') or [],
                           webrtc_ice_address=actual.get('webrtcLocalUDPAddress', ':8189'),
                           webrtc_suggested_host=c.HOST.strip('[]'),
                           srt={'enabled': bool(actual.get('srt', True)), 'address': actual.get('srtAddress', ':8890'),
                                'auth_ready': bool(auth_ready), 'runtime_checked': isinstance(runtime, dict),
                                'publish_passphrase_required': bool(config['paths'].get(c.paths(user)[1], {}).get(
                                    'srtPublishPassphrase', (config.get('pathDefaults') or {}).get('srtPublishPassphrase', '')))},
                           native_storage_ready=self.native_root.is_dir(),
                           native_free_mb=shutil.disk_usage(self.native_root).free // 1048576 if self.native_root.is_dir() else None)

        @app.post('/api/native-recording')
        @expert
        def native_recording(user):
            body = self.body()
            source, enabled = body.get('source'), self.boolean(body, 'enabled')
            if source not in c.MODEL.record_sources(user):
                raise c.Error('Ungültige Aufnahmequelle.', http_status=400)
            if enabled and source not in c.MODEL.active_record_sources(user):
                raise c.Error('Eine archivierte Quelle kann nicht erneut aktiviert werden.',http_status=400)
            change = {'record': enabled}
            if enabled:
                fmt, segment, retention = body.get('format', 'fmp4'), body.get('segment', '15m'), body.get('retention', '7d')
                if fmt not in ('fmp4', 'mpegts') or segment not in ('1m', '5m', '15m', '1h') or retention not in ('1d', '7d', '30d'):
                    raise c.Error('Ungültiges Aufnahmeformat, Segment- oder Aufbewahrungsintervall.', http_status=400)
                directory = self.recording_directory(user, source, create=True)
                if shutil.disk_usage(directory).free < 500 * 1048576:
                    raise c.Error('Für native Aufnahmen müssen mindestens 500 MB frei sein.')
                change.update(recordPath=str(self.native_root / user['username'] / '%path' / '%Y-%m-%d_%H-%M-%S-%f_%z'), recordFormat=fmt,
                              recordSegmentDuration=segment, recordDeleteAfter=retention)
            self.apply_paths({user['prefix'] + source: change})
            return jsonify(ok=True)

        @app.get('/api/native-recordings')
        @login
        def native_recordings(user):
            segments = []
            for source in c.MODEL.record_sources(user):
                folder = self.recording_directory(user, source)
                files = sorted((p for p in folder.glob('*') if p.suffix in ('.mp4', '.ts') and not p.is_symlink()), reverse=True)
                for path in files[:200]:
                    try:
                        stat = path.stat()
                        segments.append({'source':source,'label':c.MODEL.source_label(user,source), 'name': path.name, 'size': stat.st_size, 'modified': stat.st_mtime,
                                         'url': '/media/native/' + source + '/' + urllib.parse.quote(path.name)})
                    except FileNotFoundError:
                        pass
            return jsonify(segments=sorted(segments, key=lambda p: p['modified'], reverse=True)[:200])

        @app.get('/media/native/<source>/<name>')
        @login
        def native_file(user, source, name):
            if source not in c.MODEL.record_sources(user) or not re.fullmatch(r'[A-Za-z0-9_+.-]+\.(mp4|ts)', name):
                raise c.Error('Aufnahme nicht gefunden.', http_status=404)
            path = self.recording_directory(user, source) / name
            if path.is_symlink() or not path.is_file():
                raise c.Error('Aufnahme nicht gefunden.', http_status=404)
            return send_file(path, as_attachment=True, download_name=name)

        @app.post('/api/viewer-link')
        @expert
        def viewer_link(user):
            enabled = self.boolean(self.body(), 'enabled')
            with c.LOCK:
                if enabled:
                    token = secrets.token_urlsafe(32)
                    c.write('INSERT OR REPLACE INTO viewer_links(user_id,token_hash,token) VALUES (?,?,?)',
                            (user['id'], hashlib.sha256(token.encode()).hexdigest(), c.encrypt(token)))
                    return jsonify(ok=True, url=c.PUBLIC + '/watch/' + token + '/')
                c.write('DELETE FROM viewer_links WHERE user_id=?', (user['id'],))
            return jsonify(ok=True, url='')

        @app.get('/watch/<token>/')
        def watch(token):
            user = self.viewer(token)
            return render_template('player.html', viewer=user['username'])

        @app.get('/watch/<token>/<asset>')
        def viewer_asset(token, asset):
            user = self.viewer(token)
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', asset) or '..' in asset or not (asset.endswith(('.m3u8', '.mp4', '.ts')) or asset == 'hls.min.js'):
                raise c.Error('Nicht gefunden.', http_status=404)
            query = '?' + request.query_string.decode('ascii', errors='ignore') if request.query_string else ''
            req = urllib.request.Request(c.HLS + c.paths(user)[2] + '/' + asset + query, headers=self.media_headers(user))
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    return Response(response.read(16 * 1024 * 1024), content_type=response.headers.get('Content-Type', 'application/octet-stream'))
            except OSError:
                return '', 404

        @app.post('/api/admin/webrtc')
        @expert
        def configure_webrtc(user):
            if not user['admin']:
                raise c.Error('Nur Administratoren können globale MediaMTX-Einstellungen ändern.', http_status=403)
            body = self.body()
            enabled = self.boolean(body, 'enabled')
            hosts = body.get('hosts', [])
            if not isinstance(hosts, list) or len(hosts) > 16 or any(not isinstance(h, str) or not re.fullmatch(r'[A-Za-z0-9.:_-]{1,253}', h) for h in hosts):
                raise c.Error('Bitte gültige Hostnamen oder IP-Adressen angeben.', http_status=400)
            with c.LOCK:
                config = self.config()
                # Listener addresses and existing ICE/TURN settings stay under server administration.
                change = {'webrtc': enabled, 'webrtcAdditionalHosts': hosts}
                previous = {key: config.get(key, True if key == 'webrtc' else []) for key in change}
                c.mtx('config/global/patch', change)
                config.update(change)
                try:
                    c.atomic(c.CONFIG, yaml.safe_dump(config, sort_keys=False, allow_unicode=True))
                except OSError:
                    c.mtx('config/global/patch', previous)
                    raise c.Error('WebRTC-Konfiguration konnte nicht gespeichert werden.') from None
            return jsonify(ok=True)

        @app.get('/webrtc/<int:slot>/<mode>/')
        @expert
        def rtc_page(user, slot, mode):
            if slot not in (1, 2, 3) or mode not in ('publish', 'play') or mode == 'publish' and slot == 3:
                raise c.Error('Ungültige WebRTC-Quelle.', http_status=404)
            enabled = bool(self.config().get('webrtc', True))
            if enabled:
                self.rtc_base()
            program = request.args.get('program','main')
            if slot==3:
                c.MODEL.program(user,program)
            return render_template('webrtc.html',slot=slot,mode=mode,program=program,csrf=session['csrf'],enabled=enabled,admin=bool(user['admin']))

        @app.post('/api/webrtc/<int:slot>/<mode>')
        @expert
        def rtc_offer(user, slot, mode):
            if slot not in (1, 2, 3) or mode not in ('publish', 'play') or mode == 'publish' and slot == 3:
                raise c.Error('Ungültige WebRTC-Quelle.', http_status=404)
            if request.mimetype != 'application/sdp' or request.content_length is None or not 1 <= request.content_length <= 65536:
                raise c.Error('Ungültiges SDP-Angebot.', http_status=400)
            base = self.rtc_base()
            path = c.paths(user)[slot - 1]
            if slot == 3:
                path = self.program_preview.ensure(user,request.args.get('program','main'))
            if slot == 1 and user['replay_recording_id']:
                if mode == 'publish':
                    raise c.Error('Bitte zuerst die Wiederholung beenden.')
                path = user['prefix'] + 'replay'
            url = base + path + ('/whip' if mode == 'publish' else '/whep')
            headers = {**self.media_headers(user), 'Content-Type': 'application/sdp'}
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=request.get_data(), headers=headers, method='POST'), timeout=15) as upstream:
                    answer = upstream.read(65536)
                    location = urllib.parse.urljoin(url, upstream.headers.get('Location', ''))
                    if not location.startswith(url + '/') or not re.fullmatch(r'[a-fA-F0-9-]{36}', location[len(url) + 1:]):
                        raise c.Error('MediaMTX lieferte keine gültige WebRTC-Sitzung.')
                ident = secrets.token_urlsafe(24)
                with c.LOCK:
                    self.rtc_sessions = {key: value for key, value in self.rtc_sessions.items() if time.monotonic() - value[3] < 86400}
                    if sum(value[0] == user['id'] for value in self.rtc_sessions.values()) >= 12:
                        self.close_rtc(location)
                        raise c.Error('Bitte zuerst andere WebRTC-Fenster schließen.')
                    self.rtc_sessions[ident] = (user['id'], session['csrf'], location, time.monotonic())
                return Response(answer, status=201, content_type='application/sdp', headers={'Location': '/api/webrtc/session/' + ident})
            except OSError:
                raise c.Error('WebRTC-Verbindung fehlgeschlagen. Quelle, Codecs und MediaMTX-Konfiguration prüfen.') from None

        @app.get('/api/webrtc/ice')
        @expert
        def rtc_ice(user):
            url = self.rtc_base() + c.paths(user)[0] + '/whep'
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method='OPTIONS', headers=self.media_headers(user)), timeout=8) as response:
                    links = ','.join(response.headers.get_all('Link') or [])
                servers = []
                for match in re.finditer(r'<([^>]+)>((?:;\s*[\w-]+="[^"]*")*)', links):
                    params = dict(re.findall(r'([\w-]+)="([^"]*)"', match[2]))
                    if params.get('rel') == 'ice-server':
                        servers.append({'urls': match[1], **({'username': params['username'], 'credential': params.get('credential', '')} if 'username' in params else {})})
                return jsonify(iceServers=servers)
            except OSError:
                raise c.Error('WebRTC-Server ist nicht erreichbar.') from None

        @app.delete('/api/webrtc/session/<ident>')
        @login
        def rtc_delete(user, ident):
            # Cleanup remains possible after switching expert mode off.
            with c.LOCK:
                entry = self.rtc_sessions.get(ident)
                if not entry or entry[:2] != (user['id'], session['csrf']):
                    raise c.Error('WebRTC-Sitzung nicht gefunden.', http_status=404)
                self.close_rtc(entry[2])
                self.rtc_sessions.pop(ident, None)
            return '', 204

    def close_rtc(self, location):
        try:
            with urllib.request.urlopen(urllib.request.Request(location, method='DELETE'), timeout=5):
                pass
        except OSError:
            pass
