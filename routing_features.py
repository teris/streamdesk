"""Expert-only source/output management and per-output routing."""
from contextlib import contextmanager
import json
import ipaddress
import os
import re
import secrets
import urllib.parse
from flask import jsonify
from routing_model import MAX_SOURCES, MAX_OUTPUTS, program_id

PLATFORM_PRESETS = {
    'kick':'rtmps://fa723fc1b171.global-contribute.live-video.net/app',
    'facebook':'rtmps://live-api-s.facebook.com:443/rtmp',
    'trovo':'rtmp://livepush.trovo.live/live',
}

class RoutingFeatures:
    def __init__(self, core, media):
        self.c, self.media = core, media
        self.install_routes()

    @contextmanager
    def change(self, user):
        c = self.c
        with c.LOCK:
            tables = ('routing_sources','output_routing','routing_programs','outputs','routing_policy','playlist_profiles')
            previous = {table:c.rows('SELECT * FROM '+table+' WHERE user_id=?',(user['id'],)) for table in tables}
            try:
                yield
                c.reconcile()
            except Exception:
                with c.db() as connection:
                    for table, rows in previous.items():
                        connection.execute('DELETE FROM '+table+' WHERE user_id=?',(user['id'],))
                        for row in rows:
                            columns = list(row)
                            connection.execute('INSERT INTO '+table+'('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(row.values()))
                raise

    def label(self, value):
        if not isinstance(value,str) or not 1 <= len(value.strip()) <= 60 or any(ord(char)<32 for char in value):
            raise self.c.Error('Bitte einen Namen mit 1–60 Zeichen angeben.')
        return value.strip()

    def owned_output(self, user, kind):
        found = self.c.rows('SELECT * FROM outputs WHERE user_id=? AND kind=?',(user['id'],kind))
        if not found:
            raise self.c.Error('Ausgang nicht gefunden.',http_status=404)
        return found[0]

    def stopped(self, user, kind):
        if kind not in self.c.output_kinds(user):
            raise self.c.Error('Ausgang nicht gefunden.',http_status=404)
        if self.c.configured_forwards(user).get(self.c.output_path(user,kind)):
            raise self.c.Error('Bitte diesen Ausgang vor einer Zuordnungs- oder Adressänderung stoppen.',http_status=409)

    def safe_pull(self, value):
        try:
            parsed = urllib.parse.urlsplit(value)
            if parsed.scheme not in ('rtsp','rtsps') or parsed.fragment:
                raise ValueError()
        except ValueError:
            raise self.c.Error('Bitte eine öffentliche RTSP-/RTSPS-Adresse verwenden.') from None
        return self.c.validate_output(value),parsed.scheme

    def static_udp_source(self, protocol, body, previous=''):
        value = body.get('url', '')
        if not isinstance(value, str):
            raise self.c.Error('Ungültige UDP-Quelladresse.')
        previous_settings = json.loads(previous) if previous else {}
        if not value.strip() and previous_settings:
            value = previous_settings.get('url', '')
        try:
            parsed = urllib.parse.urlsplit(value.strip())
            expected = 'udp+mpegts' if protocol == 'mpegts' else 'udp+rtp'
            if parsed.scheme != expected or parsed.hostname is None or parsed.port is None or parsed.username or parsed.password or parsed.fragment:
                raise ValueError()
            host = ipaddress.ip_address(parsed.hostname)
            query = urllib.parse.parse_qs(parsed.query, strict_parsing=bool(parsed.query))
            if set(query) - {'source','interface'}:
                raise ValueError()
            if host.is_unspecified:
                allowed = query.get('source', [])
                if len(allowed) != 1 or not ipaddress.ip_address(allowed[0]).is_global:
                    raise ValueError()
            elif not host.is_multicast:
                raise ValueError()
            if not 1024 <= parsed.port <= 65535:
                raise ValueError()
        except (ValueError, OSError):
            raise self.c.Error('UDP-Ingest benötigt udp+mpegts:// bzw. udp+rtp:// mit Multicast oder 0.0.0.0 und öffentlicher source-IP.') from None
        settings = {'url':value.strip()}
        if protocol == 'rtp':
            sdp = body.get('sdp') or previous_settings.get('sdp', '')
            if not isinstance(sdp, str) or not 20 <= len(sdp) <= 8192 or not sdp.startswith('v=0') or '\nm=' not in sdp:
                raise self.c.Error('RTP benötigt eine gültige SDP-Beschreibung (20–8192 Zeichen).')
            settings['sdp'] = sdp
        return json.dumps(settings, separators=(',', ':'))

    def check_udp_listener(self, user, key, endpoint):
        parsed = urllib.parse.urlsplit(json.loads(endpoint)['url'])
        config = self.media.config()
        for name, settings in config.get('paths', {}).items():
            if name == user['prefix'] + key:
                continue
            address = str(settings.get('source', ''))
            if not address.startswith(('udp+mpegts://','udp+rtp://')):
                continue
            other = urllib.parse.urlsplit(address)
            if other.port == parsed.port and (other.hostname == parsed.hostname or other.hostname in ('0.0.0.0','::') or parsed.hostname in ('0.0.0.0','::')):
                raise self.c.Error('Diese UDP-Adresse ist bereits belegt. Bitte einen anderen Port wählen.',http_status=409)
        for enabled, address, default in (('srt','srtAddress',8890),('webrtc','webrtcLocalUDPAddress',8189),('moq','moqHTTP3Address',8892),('moq','moqQUICAddress',8893)):
            value = config.get(address, ':'+str(default))
            if config.get(enabled, enabled!='moq') and value and urllib.parse.urlsplit('udp://'+str(value)).port == parsed.port:
                raise self.c.Error('Dieser UDP-Port wird bereits von einem Medienprotokoll verwendet.',http_status=409)

    def endpoint(self, platform, body, previous=''):
        c = self.c
        if platform == 'custom':
            value = body.get('url','')
            if not isinstance(value,str):
                raise c.Error('Ungültige Zieladresse.')
            return c.validate_output(value.strip()) if value.strip() else previous
        value = body.get('key','')
        if not isinstance(value,str):
            raise c.Error('Ungültiger Streamschlüssel.')
        value = value.strip()
        if not value:
            return previous
        minimum = 15 if platform=='twitch' else 10
        if not re.fullmatch(r'[A-Za-z0-9_-]{'+str(minimum)+r',256}',value):
            raise c.Error('Bitte einen gültigen '+('Twitch' if platform=='twitch' else 'YouTube')+'-Streamschlüssel angeben.')
        return (c.TWITCH if platform=='twitch' else 'rtmps://a.rtmps.youtube.com:443/live2')+'#'+value

    def record_guard(self, user, kind, sources, changes=None):
        c = self.c
        if not isinstance(sources,list) or any(not isinstance(key,str) for key in sources):
            raise c.Error('Ungültige Quellenzuordnung.')
        old = c.MODEL.output_program(user,kind)
        changes = changes or {kind:sources}
        if program_id(sources)==old['id'] or old['id']=='main' or any(program_id(changes.get(target,old['sources']))==old['id'] for target in old['targets']):
            return
        if c.rows("SELECT id FROM recordings WHERE user_id=? AND source=? AND status IN ('recording','finishing')",(user['id'],old['id'])) or self.media.config()['paths'].get(old['path'],{}).get('record'):
            raise c.Error('Für das bisherige Programm läuft eine Aufnahme. Bitte diese vor dem Entfernen der Zuordnung beenden.',http_status=409)

    def install_routes(self):
        c, media = self.c, self.media
        expert = lambda function:c.login_required(c.expert_required(function))

        @c.app.get('/api/routing')
        @expert
        def routing_status(user):
            configured = {row['kind']:row for row in c.destinations(user)}
            outputs = []
            for kind in c.output_kinds(user):
                row = configured.get(kind,{})
                outputs.append({'kind':kind,'platform':kind.split('-')[0],
                    'label':row.get('label') or {'twitch':'Twitch','youtube':'YouTube','custom':'Eigener Anbieter'}.get(kind,'Weiterer Ausgang'),
                    'fixed':kind in c.OUTPUT_KINDS,'configured':bool(row.get('endpoint')),'selected':bool(row.get('selected')),
                    'sources':c.MODEL.route(user,kind),'program':c.MODEL.output_program(user,kind)['id']})
            return jsonify(sources=c.MODEL.public_sources(user),outputs=outputs,policy=c.MODEL.policy(user),
                           limits={'sources':MAX_SOURCES,'outputs':MAX_OUTPUTS})

        @c.app.post('/api/routing/sources')
        @expert
        def create_source(user):
            body = media.body()
            label = self.label(body.get('label',''))
            protocol = body.get('protocol','srt')
            if protocol not in ('rtmp','srt','webrtc','mpegts','rtp','moq','rtsp','rtsps','proxy'):
                raise c.Error('Bitte ein aktiviertes Publish-Protokoll oder RTSP-Pull wählen.')
            endpoint = ''
            on_demand = body.get('source_on_demand', False)
            if type(on_demand) is not bool:
                raise c.Error('Ungültige Source-on-demand-Einstellung.')
            if protocol in ('rtsp','rtsps'):
                value = body.get('url','')
                if not isinstance(value,str):
                    raise c.Error('Ungültige Pull-Adresse.')
                endpoint,protocol = self.safe_pull(value.strip())
            elif protocol in ('mpegts','rtp'):
                endpoint = self.static_udp_source(protocol, body)
            elif protocol == 'proxy':
                value = body.get('url','')
                endpoint = c.validate_output(value.strip()) if isinstance(value,str) else ''
                if not endpoint:
                    raise c.Error('Bitte eine öffentliche Proxy-Adresse angeben.')
            with self.change(user):
                catalog = c.MODEL.sources(user)
                if len(catalog)>=MAX_SOURCES:
                    raise c.Error(f'Maximal {MAX_SOURCES} Quellen pro Benutzer.')
                all_sources = c.MODEL.sources(user,True)
                ordinal = max([2]+[row.get('ordinal',2) for row in all_sources])+1
                key = 'source'+str(ordinal)
                if protocol in ('mpegts','rtp'):
                    self.check_udp_listener(user,key,endpoint)
                priority = min(999,max(row['priority'] for row in catalog)+1)
                c.write('INSERT INTO routing_sources(user_id,key,ordinal,label,protocol,endpoint,priority,source_on_demand) VALUES (?,?,?,?,?,?,?,?)',
                        (user['id'],key,ordinal,label,protocol,c.encrypt(endpoint),priority,int(on_demand)))
            return jsonify(ok=True,key=key)

        @c.app.post('/api/routing/sources/<key>')
        @expert
        def update_source(user,key):
            source = c.MODEL.source(user,key)
            if source['fixed']:
                raise c.Error('Source 1 und Source 2 sind fest und können nicht verändert werden.',http_status=403)
            body = media.body()
            label = self.label(body.get('label',source['label']))
            priority = body.get('priority',source['priority'])
            if type(priority) is not int or not 3<=priority<=999:
                raise c.Error('Zusätzliche Quellen benötigen eine Priorität von 3 bis 999. Source 1 und 2 bleiben davor.')
            enabled = body.get('enabled',source['enabled'])
            if type(enabled) is not bool:
                raise c.Error('Ungültiger Quellenschalter.')
            on_demand = body.get('source_on_demand', bool(source.get('source_on_demand')))
            if type(on_demand) is not bool:
                raise c.Error('Ungültige Source-on-demand-Einstellung.')
            protocol = body.get('protocol',source['protocol'])
            if protocol not in ('rtmp','srt','webrtc','mpegts','rtp','moq','rtsp','rtsps','proxy'):
                raise c.Error('Ungültiges Quellenprotokoll.')
            endpoint = c.decrypt(source['endpoint'])
            if protocol in ('rtsp','rtsps'):
                value = body.get('url','')
                if not isinstance(value,str):
                    raise c.Error('Ungültige Pull-Adresse.')
                if value.strip() or source['protocol'] not in ('rtsp','rtsps') or enabled and not source['enabled']:
                    endpoint,protocol = self.safe_pull(value.strip() or endpoint)
                else:
                    protocol = source['protocol']
            elif protocol == 'proxy':
                value = body.get('url','')
                if not isinstance(value, str):
                    raise c.Error('Ungültige Proxy-Adresse.')
                if value.strip() or protocol != source['protocol'] or enabled and not source['enabled']:
                    endpoint = c.validate_output(value.strip() or endpoint)
            else:
                endpoint = self.static_udp_source(protocol, body, endpoint) if protocol in ('mpegts','rtp') else ''
            with self.change(user):
                if enabled and protocol in ('mpegts','rtp'):
                    self.check_udp_listener(user,key,endpoint)
                c.write('UPDATE routing_sources SET label=?,protocol=?,endpoint=?,priority=?,enabled=?,source_on_demand=? WHERE user_id=? AND key=?',
                        (label,protocol,c.encrypt(endpoint),priority,int(enabled),int(on_demand),user['id'],key))
            return jsonify(ok=True)

        @c.app.post('/api/routing/policy')
        @expert
        def routing_policy(user):
            body = media.body()
            try:
                healthy, stall, retry = (float(body.get(name)) for name in ('healthy_seconds','stall_seconds','retry_seconds'))
            except (TypeError, ValueError):
                raise c.Error('Ungültige Routing-Zeitwerte.') from None
            native_standby = body.get('native_standby', False)
            if native_standby and os.getenv('STREAMDESK_MEDIAMTX_MODE')=='remote-api' and os.getenv('STREAMDESK_NATIVE_SHARED')!='1':
                raise c.Error('Die native Offline-Datei benötigt einen gemeinsam eingebundenen Speicher auf UI- und Medienserver.',http_status=409)
            if not .5 <= healthy <= 30 or not 2 <= stall <= 120 or not 1 <= retry <= 300 or type(native_standby) is not bool:
                raise c.Error('Routing-Zeitwerte liegen außerhalb der erlaubten Grenzen.')
            with self.change(user):
                c.MODEL.save_policy(user, healthy, stall, retry, native_standby)
            return jsonify(ok=True)

        @c.app.post('/api/routing/sources/<key>/delete')
        @expert
        def remove_source(user,key):
            source = c.MODEL.source(user,key)
            if source['fixed']:
                raise c.Error('Standardquellen können nicht gelöscht werden.',http_status=403)
            with self.change(user):
                if any(key in c.MODEL.route(user,kind) for kind in c.output_kinds(user)):
                    raise c.Error('Bitte die Quelle zuerst aus ihren Ausgangszuordnungen entfernen.',http_status=409)
                if c.rows("SELECT id FROM recordings WHERE user_id=? AND source=? AND status IN ('recording','finishing')",(user['id'],key)) or media.config()['paths'].get(user['prefix']+key,{}).get('record'):
                    raise c.Error('Bitte die laufende Aufnahme dieser Quelle zuerst beenden.',http_status=409)
                c.write('UPDATE routing_sources SET deleted=1,enabled=0 WHERE user_id=? AND key=?',(user['id'],key))
            return jsonify(ok=True)

        @c.app.post('/api/routing/sources/<key>/targets')
        @expert
        def source_targets(user,key):
            c.MODEL.source(user,key)
            targets = media.body().get('targets')
            allowed = set(c.output_kinds(user))
            if not isinstance(targets,list) or any(not isinstance(kind,str) or kind not in allowed for kind in targets) or len(targets)!=len(set(targets)):
                raise c.Error('Ungültige oder fremde Ausgangszuordnung.',http_status=404)
            with self.change(user):
                changes = []
                for kind in allowed:
                    before = c.MODEL.route(user,kind)
                    after = [source for source in before if source!=key]+([key] if kind in targets else [])
                    if set(before)!=set(after):
                        self.stopped(user,kind)
                        changes.append((kind,after))
                replacements=dict(changes)
                for kind,after in changes:
                    self.record_guard(user,kind,after,replacements)
                for kind,after in changes:
                    c.MODEL.save_route(user,kind,after)
            return jsonify(ok=True)

        @c.app.post('/api/routing/outputs/<kind>/sources')
        @expert
        def output_sources(user,kind):
            with self.change(user):
                self.stopped(user,kind)
                sources = media.body().get('sources')
                if not isinstance(sources,list):
                    raise c.Error('Ungültige Quellenzuordnung.')
                self.record_guard(user,kind,sources)
                c.MODEL.save_route(user,kind,sources)
            return jsonify(ok=True)

        def create_output(user,body,platform=None):
            platform = platform or body.get('platform')
            c.SERVICES.require_output('custom' if platform in PLATFORM_PRESETS else str(platform))
            preset = platform if platform in PLATFORM_PRESETS else None
            if platform not in c.OUTPUT_KINDS and not preset:
                raise c.Error('Bitte eine unterstützte Plattform oder einen eigenen Anbieter wählen.')
            label = self.label(body.get('label',''))
            if preset:
                key = body.get('key','')
                if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{10,256}',key.strip()):
                    raise c.Error('Bitte einen gültigen Streamschlüssel angeben.')
                endpoint = PLATFORM_PRESETS[preset]+'#'+key.strip()
                platform = 'custom'
            else:
                endpoint = self.endpoint(platform,body)
            if not endpoint:
                raise c.Error('Bitte Zugangsdaten für den Ausgang eingeben.')
            with self.change(user):
                if len(c.output_kinds(user))>=MAX_OUTPUTS:
                    raise c.Error(f'Maximal {MAX_OUTPUTS} Ausgänge pro Benutzer.')
                if any(c.decrypt(row['endpoint'])==endpoint for row in c.destinations(user)):
                    raise c.Error('Diese Zieladresse ist bereits eingerichtet.')
                kind = platform+'-'+secrets.token_hex(6)
                c.write('INSERT INTO outputs(user_id,kind,endpoint,selected,label) VALUES (?,?,?,0,?)',
                        (user['id'],kind,c.encrypt(endpoint),label))
                c.MODEL.save_route(user,kind,[])
            return jsonify(ok=True,kind=kind)

        @c.app.post('/api/routing/outputs')
        @expert
        def add_output(user):
            return create_output(user,media.body())

        @c.app.post('/api/custom-outputs')
        @expert
        def legacy_add_output(user):
            return create_output(user,media.body(),'custom')

        @c.app.post('/api/routing/outputs/<kind>')
        @c.app.post('/api/custom-outputs/<kind>')
        @expert
        def update_output(user,kind):
            body = media.body()
            with self.change(user):
                old = self.owned_output(user,kind)
                label = self.label(body.get('label',old['label'] or 'Eigener Anbieter'))
                endpoint = self.endpoint(kind.split('-')[0],body,c.decrypt(old['endpoint']))
                if endpoint != c.decrypt(old['endpoint']):
                    self.stopped(user,kind)
                    if any(row['kind']!=kind and c.decrypt(row['endpoint'])==endpoint for row in c.destinations(user)):
                        raise c.Error('Diese Zieladresse ist bereits eingerichtet.')
                c.write('UPDATE outputs SET label=?,endpoint=? WHERE user_id=? AND kind=?',
                        (label,c.encrypt(endpoint),user['id'],kind))
            return jsonify(ok=True)

        @c.app.post('/api/routing/outputs/<kind>/delete')
        @c.app.post('/api/custom-outputs/<kind>/delete')
        @expert
        def remove_output(user,kind):
            if kind in c.OUTPUT_KINDS:
                raise c.Error('Standardausgänge bleiben erhalten. Ihre Zugangsdaten lassen sich in den Einstellungen entfernen.',http_status=403)
            with self.change(user):
                self.owned_output(user,kind);self.stopped(user,kind);self.record_guard(user,kind,[])
                c.write('DELETE FROM outputs WHERE user_id=? AND kind=?',(user['id'],kind))
                c.write('DELETE FROM output_routing WHERE user_id=? AND kind=?',(user['id'],kind))
            return jsonify(ok=True)
