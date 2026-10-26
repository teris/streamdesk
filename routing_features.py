"""Expert-only source/output management and per-output routing."""
from contextlib import contextmanager
import json
import re
import secrets
import urllib.parse
from flask import jsonify
from routing_model import MAX_SOURCES, MAX_OUTPUTS, program_id


class RoutingFeatures:
    def __init__(self, core, media):
        self.c, self.media = core, media
        self.install_routes()

    @contextmanager
    def change(self, user):
        c = self.c
        with c.LOCK:
            tables = ('routing_sources','output_routing','routing_programs','outputs')
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

    def record_guard(self, user, kind, sources):
        c = self.c
        if not isinstance(sources,list) or any(not isinstance(key,str) for key in sources):
            raise c.Error('Ungültige Quellenzuordnung.')
        old = c.MODEL.output_program(user,kind)
        if program_id(sources)==old['id'] or old['id']=='main' or len(old['targets'])>1:
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
            return jsonify(sources=c.MODEL.public_sources(user),outputs=outputs,
                           limits={'sources':MAX_SOURCES,'outputs':MAX_OUTPUTS})

        @c.app.post('/api/routing/sources')
        @expert
        def create_source(user):
            body = media.body()
            label = self.label(body.get('label',''))
            protocol = body.get('protocol','srt')
            if protocol not in ('rtmp','srt','rtsp','rtsps'):
                raise c.Error('Bitte RTMP, SRT oder RTSP-Pull wählen.')
            endpoint = ''
            if protocol in ('rtsp','rtsps'):
                value = body.get('url','')
                if not isinstance(value,str):
                    raise c.Error('Ungültige Pull-Adresse.')
                endpoint,protocol = self.safe_pull(value.strip())
            with self.change(user):
                catalog = c.MODEL.sources(user)
                if len(catalog)>=MAX_SOURCES:
                    raise c.Error(f'Maximal {MAX_SOURCES} Quellen pro Benutzer.')
                all_sources = c.MODEL.sources(user,True)
                ordinal = max([2]+[row.get('ordinal',2) for row in all_sources])+1
                key = 'source'+str(ordinal)
                priority = min(999,max(row['priority'] for row in catalog)+1)
                c.write('INSERT INTO routing_sources(user_id,key,ordinal,label,protocol,endpoint,priority) VALUES (?,?,?,?,?,?,?)',
                        (user['id'],key,ordinal,label,protocol,c.encrypt(endpoint),priority))
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
            protocol = body.get('protocol',source['protocol'])
            if protocol not in ('rtmp','srt','rtsp','rtsps'):
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
            else:
                endpoint = ''
            with self.change(user):
                c.write('UPDATE routing_sources SET label=?,protocol=?,endpoint=?,priority=?,enabled=? WHERE user_id=? AND key=?',
                        (label,protocol,c.encrypt(endpoint),priority,int(enabled),user['id'],key))
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
                        self.stopped(user,kind);self.record_guard(user,kind,after)
                        changes.append((kind,after))
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
            if platform not in c.OUTPUT_KINDS:
                raise c.Error('Bitte Twitch, YouTube oder einen eigenen Anbieter wählen.')
            label = self.label(body.get('label',''))
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
