"""Administrator-owned feature availability, independent of expert mode and tenant data."""
import json
import threading

from flask import jsonify, request

# Core ingest, the private programme preview, accounts and existing archives stay available.
CATALOG = (
    ('twitch', 'Plattformen & Chat', 'Twitch', 'Streaming, Kontofreigabe, Kanalverwaltung und Chat.'),
    ('youtube', 'Plattformen & Chat', 'YouTube', 'Streaming, Kontofreigabe, Sendungsauswahl und Chat.'),
    ('custom_outputs', 'Plattformen & Chat', 'Eigene Streaming-Anbieter', 'Der feste eigene Anbieter und zusätzliche eigene Ausgänge.'),
    ('discord', 'Plattformen & Chat', 'Discord-Bot', 'Bot-Einrichtung, Discord-Chat und Discord im Widget.'),
    ('webrtc', 'Medien', 'WebRTC', 'Browser-Kamera und WebRTC-Vorschau. Die HLS-Programmvorschau bleibt verfügbar.'),
    ('recording', 'Medien', 'Neue Aufnahmen', 'Manuelle Programm-/Quellenaufnahme und native MediaMTX-Aufnahme. Vorhandene Dateien bleiben erhalten.'),
    ('ftp', 'Medien', 'FTP-Uploads', 'Persönliche FTPS-Zugänge und automatische Video-Importe. Zugangsdaten und Dateien bleiben bei einer Sperre erhalten.'),
    ('playlists', 'Medien', 'Playlists', 'Video-Playlists, Offline-Fallback und zeitgesteuerte Ausspielung. Gespeicherte Medien und Regeln bleiben erhalten.'),
    ('playback', 'Medien', 'Playback & Clips', 'Zeitversetzte Segmentwiedergabe und Clip-Verwaltung.'),
    ('viewers', 'Medien', 'Öffentliche Zuschauerlinks', 'Öffentliche HLS-Player. Gespeicherte Links bleiben erhalten, sind während der Sperre unbenutzbar.'),
    ('advanced_routing', 'Erweiterungen', 'Zusätzliche Quellen & Routing', 'Weitere Quellen und Konten, Routingänderungen und Szenen. Source 1 und 2 bleiben verfügbar.'),
    ('browser_overlays', 'Erweiterungen', 'Browser-Overlays', 'Browserseiten auf Live-Programmen und Offline-Videos.'),
    ('automation', 'Erweiterungen', 'Automation & Export', 'Hooks, Zeitpläne, WebDAV-Export und automatische Neuverbindungen.'),
    ('notifications', 'Erweiterungen', 'Benachrichtigungen', 'Webhook- und E-Mail-Meldungen.'),
)
KEYS = frozenset(row[0] for row in CATALOG)
LABELS = {row[0]: row[2] for row in CATALOG}
DEFAULT_OUTPUTS = ('twitch', 'youtube', 'custom')


class ServicePolicy:
    def __init__(self, core):
        self.c = core
        self.pending_runtime = False
        self.install_routes()

    def flags(self):
        with self.c.db() as connection:
            row = connection.execute("SELECT value FROM settings WHERE name='service_policy'").fetchone()
        value = self.c.decrypt(row['value']) if row else '{}'
        try:
            saved = json.loads(value)
            if not isinstance(saved, dict): raise ValueError()
            return {key: saved.get(key, True) is True for key in KEYS}
        except (ValueError, TypeError):
            # Corrupt explicit policy must not silently enable restricted services.
            self.c.logging.error('Dienstfreigaben sind ungültig; optionale Dienste bleiben gesperrt.')
            return dict.fromkeys(KEYS, False)

    def enabled(self, key):
        return self.flags()[key]

    def require(self, key):
        if not self.enabled(key):
            raise self.c.Error(LABELS[key] + ' wurde durch die Administration gesperrt.', http_status=403)

    def output_allowed(self, kind):
        flags = self.flags()
        platform = kind.split('-')[0]
        key = {'twitch': 'twitch', 'youtube': 'youtube', 'custom': 'custom_outputs'}.get(platform)
        return bool(key and flags[key] and (kind in DEFAULT_OUTPUTS or flags['advanced_routing']))

    def require_output(self, kind):
        if not self.output_allowed(kind):
            raise self.c.Error('Dieser Streaming-Ausgang wurde durch die Administration gesperrt.', http_status=403)

    def source_allowed(self, source):
        flags = self.flags()
        return bool((source.get('fixed', False) or flags['advanced_routing']) and (source.get('protocol') != 'webrtc' or flags['webrtc']))

    def owned_paths(self, user):
        c = self.c
        return ({user['prefix'] + row['key'] for row in c.MODEL.sources(user, archived=True)}
                | {user['prefix'] + 'replay',user['prefix']+'playlist-source2'}
                | {row[key] for row in c.MODEL.programs(user, archived=True) for key in ('path', 'rtc_path')}
                | {c.output_path(user, kind) for kind in c.output_kinds(user)})

    def catalog(self):
        flags = self.flags()
        return [dict(id=key, group=group, label=label, description=description, enabled=flags[key])
                for key, group, label, description in CATALOG]

    def install_routes(self):
        c = self.c

        @c.app.before_request
        def service_access():
            path = request.path
            # Let the regular authentication middleware handle private anonymous calls.
            if not path.startswith('/watch/') and not c.current():
                return
            requirements = []
            for prefix, key in (('/api/ftp','ftp'),('/api/admin/users/', 'ftp') if request.path.endswith('/ftp') else ('/__no_ftp_route__','ftp'),('/api/planner','automation'),('/api/planner','playlists'),('/api/playlists', 'playlists'), ('/api/playlist-folders', 'playlists'), ('/api/playout', 'playlists'),('/oauth/twitch', 'twitch'), ('/api/twitch/', 'twitch'),
                                ('/oauth/youtube', 'youtube'), ('/api/youtube/', 'youtube'),
                                ('/api/discord', 'discord'), ('/api/routing', 'advanced_routing'),
                                ('/api/custom-outputs', 'advanced_routing'), ('/api/scenes', 'advanced_routing'),
                                ('/api/playback', 'playback'), ('/api/admin/playback', 'playback'),
                                ('/api/clips', 'playback'), ('/media/clip/', 'playback'),
                                ('/api/automation', 'automation'), ('/api/renewal', 'automation'),
                                ('/api/notifications', 'notifications'), ('/api/viewer-link', 'viewers'),
                                ('/watch/', 'viewers'), ('/webrtc/', 'webrtc'), ('/api/admin/webrtc', 'webrtc')):
                if path == prefix or path.startswith(prefix):
                    requirements.append(key)
            if path.startswith('/api/webrtc/') and not (request.method == 'DELETE' and '/session/' in path):
                requirements.append('webrtc')
            if path in ('/api/native-recording', '/api/recordings/start'):
                requirements.append('recording')
            if path.startswith('/api/videos/') and path.endswith('/browser'):
                requirements.append('browser_overlays')
            for key in requirements:
                self.require(key)
            body = request.get_json(silent=True)
            body = body if isinstance(body, dict) else {}
            if path == '/api/output':
                self.require_output(str(body.get('kind', 'twitch')))
            if path == '/api/outputs/select' and isinstance(body.get('kinds'), list):
                for kind in body['kinds']:
                    if isinstance(kind, str): self.require_output(kind)
            parts = path.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api', 'outputs'] and parts[3] != 'stop':
                self.require_output(parts[2])
            if len(parts) >= 4 and parts[:3] == ['api', 'routing', 'outputs']:
                self.require_output(parts[3])
            if len(parts) >= 3 and parts[:2] == ['api', 'custom-outputs']:
                self.require_output(parts[2])
            if path.startswith('/preview/source/') and parts[2] not in ('source1', 'source2'):
                self.require('advanced_routing')
            if path.startswith('/api/ingest/') or path.startswith('/webrtc/source/') or path.startswith('/api/webrtc/source/'):
                key = parts[2] if parts[1] == 'ingest' else parts[3] if parts[0] == 'api' else parts[2]
                if key not in ('source1', 'source2'):
                    self.require('advanced_routing')

        @c.app.get('/api/admin/services')
        @c.login_required
        def services_status(user):
            if not user['admin']:
                raise c.Error('Nur Administratoren dürfen Dienste verwalten.', http_status=403)
            return jsonify(services=self.catalog(), runtime_pending=self.pending_runtime)

        @c.app.post('/api/admin/services')
        @c.login_required
        def services_update(user):
            if not user['admin']:
                raise c.Error('Nur Administratoren dürfen Dienste verwalten.', http_status=403)
            body = c.FEATURES.body()
            key, enabled = body.get('id'), body.get('enabled')
            if not isinstance(key, str) or key not in KEYS or type(enabled) is not bool or set(body) != {'id', 'enabled'}:
                raise c.Error('Bitte einen bekannten Dienst und einen gültigen Schalter angeben.', http_status=400)
            with c.LOCK:
                flags = self.flags()
                if flags[key] != enabled:
                    flags[key] = enabled
                    c.set_setting('service_policy', json.dumps(flags))
                    if key == 'automation' and enabled:
                        c.write("UPDATE scheduled_jobs SET status='error',message='Während der Dienstsperre verpasst; bitte neu planen.' WHERE status='pending' AND run_at<=?", (c.time.time(),))
                    self.enforce_local()
                    if key in ('twitch', 'youtube', 'custom_outputs', 'advanced_routing', 'recording', 'playback', 'automation', 'webrtc'):
                        self.pending_runtime = True
                    self.sync_runtime()
                    c.logging.info('Administrator %s hat Dienst %s %s.', user['id'], key, 'freigegeben' if enabled else 'gesperrt')
            return jsonify(ok=True, services=self.catalog(), runtime_pending=self.pending_runtime,
                           warning='Freigabe gespeichert; MediaMTX-Abgleich wird erneut versucht.' if self.pending_runtime else '')

    def capture_records(self, config):
        """Remember native recording intent before masking effective path settings."""
        saved = json.loads(self.c.setting('service_paused_recordings', '{}') or '{}')
        original = dict(saved)
        for user in self.c.rows('SELECT * FROM users'):
            blocked = self.owned_paths(user) if not self.enabled('recording') else {
                user['prefix'] + row['key'] for row in self.c.MODEL.sources(user, archived=True)
                if not self.source_allowed(row)}
            for name in blocked:
                path = config.get('paths', {}).get(name, {})
                if path.get('record', (config.get('pathDefaults') or {}).get('record', False)):
                    saved[name] = True
        if saved != original:
            self.c.set_setting('service_paused_recordings', json.dumps(saved))

    def mask_config(self, config, managed_auth):
        """Apply effective restrictions only to this installation's owned paths."""
        flags = self.flags()
        remaining = json.loads(self.c.setting('service_paused_recordings', '{}') or '{}')
        all_owned = set()
        for user in self.c.rows('SELECT * FROM users'):
            owned = self.owned_paths(user)
            all_owned.update(owned)
            blocked = {user['prefix'] + row['key'] for row in self.c.MODEL.sources(user, archived=True)
                       if not self.source_allowed(row)}
            for name in owned & config.get('paths', {}).keys():
                path = config['paths'][name]
                if not flags['recording'] or name in blocked:
                    path['record'] = False
                elif name in remaining and user['active'] and user['role'] != 'moderator':
                    path['record'] = bool(remaining.pop(name))
            for auth in managed_auth:
                if auth['user'] == self.c.media_username(user) and not flags['playback']:
                    auth['permissions'] = [row for row in auth['permissions'] if row['action'] != 'playback']
        self.remaining_records = {name:value for name,value in remaining.items() if name in all_owned}

    def reconciled(self):
        saved = json.loads(self.c.setting('service_paused_recordings', '{}') or '{}')
        if saved != self.remaining_records:
            self.c.set_setting('service_paused_recordings', json.dumps(self.remaining_records))

    def enforce_local(self):
        c, flags = self.c, self.flags()
        for platform in ('twitch', 'youtube', 'discord'):
            if not flags[platform]:
                with c.CHAT.lock:
                    users = {uid for uid, service in c.CHAT.workers if service == platform}
                for uid in users:
                    c.CHAT.stop_platform(uid, platform, clear=False)
        if hasattr(c, 'PLAYLISTS'):
            from routing_model import job_key
            for key,job in list(c.PLAYLISTS.jobs.items()):
                if not flags['playlists'] or not flags['automation'] and job.get('scheduled'):
                    c.ENGINE.stop_relay(job_key({'id':key[0]}, key[1]))
        if not flags['recording']:
            for uid in list(c.ENGINE.recorders):
                c.ENGINE.stop_record(uid, 'Aufnahmedienst durch Administration gesperrt.')
        if not flags['webrtc']:
            sessions = list(c.FEATURES.rtc_sessions.values())
            c.FEATURES.rtc_sessions.clear()
            for entry in sessions:
                threading.Thread(target=c.FEATURES.close_rtc, args=(entry[2],), daemon=True).start()
            c.FEATURES.program_preview.close()
        if not flags['automation']:
            c.write('UPDATE users SET renew_next=0,renew_resume=0 WHERE renew_next!=0 OR renew_resume!=0')
        if not flags['advanced_routing']:
            for key in list(c.ENGINE.source_probes):
                if key[1] not in ('source1', 'source2'):
                    c.ENGINE.stop_source_probe(key)

    def sync_runtime(self):
        if self.pending_runtime:
            try:
                self.pending_runtime = self.c.reconcile() is False
            except (OSError, self.c.Error):
                self.c.logging.warning('Dienstsperre gespeichert; MediaMTX-Abgleich steht aus.')
