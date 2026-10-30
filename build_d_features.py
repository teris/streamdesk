"""BUILD D: scenes, roles, language preferences and passwordless login."""
import base64
import hashlib
import json
import secrets
import time
import urllib.parse
from webauthn import verify_registration_response, verify_authentication_response

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from flask import jsonify, request, session


def _b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def _decode(value):
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError('Ungültige Base64-Daten.')
    return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)


class BuildDFeatures:
    """Tenant-scoped BUILD D persistence and HTTP API."""
    ROLES = {'user', 'moderator', 'admin'}

    def __init__(self, core):
        self.c = core
        with core.db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS scenes(
                  id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,name TEXT NOT NULL,
                  sources TEXT NOT NULL,video_id INTEGER,targets TEXT NOT NULL,
                  created REAL NOT NULL,UNIQUE(user_id,name));
                CREATE TABLE IF NOT EXISTS webauthn_credentials(
                  id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,credential_id TEXT NOT NULL UNIQUE,
                  public_key BLOB NOT NULL,algorithm INTEGER NOT NULL,sign_count INTEGER NOT NULL DEFAULT 0,
                  label TEXT NOT NULL,created REAL NOT NULL,last_used REAL);
                CREATE TABLE IF NOT EXISTS recovery_codes(
                  user_id INTEGER NOT NULL,code_hash TEXT NOT NULL,used REAL,
                  PRIMARY KEY(user_id,code_hash));
                CREATE TABLE IF NOT EXISTS webauthn_challenges(
                  token TEXT PRIMARY KEY,user_id INTEGER NOT NULL,purpose TEXT NOT NULL,
                  challenge TEXT NOT NULL,created REAL NOT NULL);
            ''')
            columns = {row['name'] for row in connection.execute('PRAGMA table_info(webauthn_credentials)')}
            if 'key_format' not in columns:
                connection.execute("ALTER TABLE webauthn_credentials ADD COLUMN key_format TEXT NOT NULL DEFAULT 'spki'")
        self.install_routes()

    def body(self):
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise self.c.Error('Bitte ein JSON-Objekt senden.')
        return body

    def challenge(self, purpose, uid=0):
        value, token = _b64(secrets.token_bytes(32)), secrets.token_urlsafe(32)
        with self.c.db() as connection:
            connection.execute('DELETE FROM webauthn_challenges WHERE created<?', (time.time()-300,))
            connection.execute('DELETE FROM webauthn_challenges WHERE token=?', (session.get('webauthn_'+purpose, ''),))
            connection.execute('INSERT INTO webauthn_challenges(token,user_id,purpose,challenge,created) VALUES (?,?,?,?,?)',
                               (token, uid, purpose, value, time.time()))
        session['webauthn_' + purpose] = token
        return value

    def consume_challenge(self, purpose):
        token = session.pop('webauthn_' + purpose, '')
        if not isinstance(token, str):
            raise self.c.Error('Die Passkey-Anfrage ist abgelaufen.')
        with self.c.db() as connection:
            pending = connection.execute('DELETE FROM webauthn_challenges WHERE token=? AND purpose=? AND created>=? RETURNING *',
                                         (token, purpose, time.time()-300)).fetchone()
        if pending is None:
            raise self.c.Error('Die Passkey-Anfrage ist abgelaufen oder wurde bereits verwendet.')
        return dict(pending)

    def origin(self):
        parsed = urllib.parse.urlsplit(self.c.PUBLIC)
        return f'{parsed.scheme}://{parsed.netloc}', parsed.hostname

    def verify_client(self, encoded, purpose):
        pending = self.consume_challenge(purpose)
        try:
            data = json.loads(_decode(encoded))
        except (ValueError, TypeError, json.JSONDecodeError):
            raise self.c.Error('Ungültige Passkey-Antwort.') from None
        origin, _ = self.origin()
        expected_type = 'webauthn.create' if purpose == 'register' else 'webauthn.get'
        if not isinstance(data, dict) or data.get('type') != expected_type or data.get('origin') != origin or data.get('crossOrigin') is True:
            raise self.c.Error('Passkey-Ursprung oder Vorgang ist ungültig.')
        try:
            challenge = _decode(data.get('challenge', ''))
            expected = _decode(pending['challenge'])
        except (ValueError, TypeError):
            raise self.c.Error('Ungültige Passkey-Challenge.') from None
        if not secrets.compare_digest(challenge, expected):
            raise self.c.Error('Passkey-Challenge stimmt nicht überein.')
        return pending, hashlib.sha256(_decode(encoded)).digest()

    def verify_authenticator(self, encoded, *, require_attested=False):
        try:
            value = _decode(encoded)
            _, rp_id = self.origin()
            if len(value) < 37 or not secrets.compare_digest(value[:32], hashlib.sha256(rp_id.encode()).digest()):
                raise ValueError()
            flags = value[32]
            if flags & 0x05 != 0x05:
                raise ValueError()
            if require_attested and not flags & 0x40:
                raise ValueError()
            return value, int.from_bytes(value[33:37], 'big')
        except (ValueError, TypeError):
            raise self.c.Error('Authenticator-Daten sind ungültig.') from None

    def install_routes(self):
        c = self.c

        @c.app.get('/api/i18n')
        @c.login_required
        def i18n(user):
            return jsonify(language=user['language'], supported=['de', 'en'])

        @c.app.get('/api/scenes')
        @c.login_required
        def scenes(user):
            result = c.rows('SELECT id,name,sources,video_id,targets,created FROM scenes WHERE user_id=? ORDER BY name', (user['id'],))
            return jsonify(scenes=[dict(row, sources=json.loads(row['sources']), targets=json.loads(row['targets'])) for row in result])

        @c.app.post('/api/scenes')
        @c.login_required
        @c.expert_required
        def save_scene(user):
            body = self.body()
            name = str(body.get('name', '')).strip()
            sources, targets = body.get('sources'), body.get('targets')
            video_id = body.get('video_id')
            if not name or len(name) > 80:
                raise c.Error('Der Szenenname benötigt 1 bis 80 Zeichen.')
            if not isinstance(sources, list) or not sources or any(not isinstance(value, str) for value in sources) or len(sources) != len(set(sources)):
                raise c.Error('Bitte mindestens eine eindeutige Quelle wählen.')
            available = {row['key'] for row in c.MODEL.sources(user)}
            if any(source not in available for source in sources):
                raise c.Error('Die Szene enthält eine unbekannte Quelle.', http_status=404)
            if not isinstance(targets, list) or any(not isinstance(value, str) for value in targets) or len(targets) != len(set(targets)):
                raise c.Error('Ungültige Zielauswahl.')
            output_kinds = set(c.output_kinds(user))
            if any(target not in output_kinds for target in targets):
                raise c.Error('Die Szene enthält ein unbekanntes Ziel.', http_status=404)
            if video_id is not None:
                try:
                    video_id = int(video_id)
                except (TypeError, ValueError):
                    raise c.Error('Ungültiges Overlay-Video.') from None
                c.owned_video(user, video_id)
            c.write('''INSERT INTO scenes(user_id,name,sources,video_id,targets,created) VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id,name) DO UPDATE SET sources=excluded.sources,video_id=excluded.video_id,
                targets=excluded.targets,created=excluded.created''',
                (user['id'], name, json.dumps(sources), video_id, json.dumps(targets), time.time()))
            ident = c.rows('SELECT id FROM scenes WHERE user_id=? AND name=?', (user['id'], name))[0]['id']
            return jsonify(ok=True, id=ident)

        @c.app.delete('/api/scenes/<int:ident>')
        @c.login_required
        def delete_scene(user, ident):
            c.write('DELETE FROM scenes WHERE id=? AND user_id=?', (ident, user['id']))
            return '', 204

        @c.app.post('/api/scenes/<int:ident>/apply')
        @c.login_required
        @c.expert_required
        def apply_scene(user, ident):
            with c.LOCK:
                return self.apply_scene(user, ident)

        @c.app.post('/api/admin/users/<int:uid>/role')
        @c.login_required
        def set_role(user, uid):
            with c.LOCK:
                return self.set_role(user, uid)

        self.install_passkey_routes()

    def apply_scene(self, user, ident):
        c = self.c
        found = c.rows('SELECT * FROM scenes WHERE id=? AND user_id=?', (ident, user['id']))
        if not found:
            raise c.Error('Szene nicht gefunden.', http_status=404)
        c.require_stopped(user)
        scene = found[0]
        sources, targets = json.loads(scene['sources']), json.loads(scene['targets'])
        available = {row['key'] for row in c.MODEL.sources(user)}
        outputs = set(c.output_kinds(user))
        if any(value not in available for value in sources) or any(value not in outputs for value in targets):
            raise c.Error('Die Szene verweist auf entfernte Quellen oder Ziele.', http_status=409)
        video = None
        if scene['video_id'] is not None:
            video = c.owned_video(user, scene['video_id'])
            path = video['rendered'] or video['path']
            if not c.Path(path).is_file():
                raise c.Error('Das Overlay-Video der Szene fehlt.', http_status=409)
        previous_outputs = {row['kind']: row['selected'] for row in c.rows(
            'SELECT kind,selected FROM outputs WHERE user_id=?', (user['id'],))}
        previous_routes = {kind: c.MODEL.route(user, kind) for kind in outputs}
        previous_video = (user['selected_video_id'], user['offline'])
        previous_programs = c.rows('SELECT * FROM routing_programs WHERE user_id=?', (user['id'],))
        try:
            for kind in targets:
                self.c.FEATURES.routing.record_guard(user, kind, sources, {target:sources for target in targets})
            for kind in outputs:
                c.write('UPDATE outputs SET selected=? WHERE user_id=? AND kind=?',
                        (int(kind in targets), user['id'], kind))
            for kind in targets:
                c.MODEL.save_route(user, kind, sources)
            if video:
                c.write('UPDATE users SET selected_video_id=?,offline=? WHERE id=?',
                        (video['id'], video['rendered'] or video['path'], user['id']))
            c.reconcile()
        except Exception:
            for kind, selected in previous_outputs.items():
                c.write('UPDATE outputs SET selected=? WHERE user_id=? AND kind=?',
                        (selected, user['id'], kind))
            with c.db() as connection:
                connection.execute('DELETE FROM output_routing WHERE user_id=?', (user['id'],))
                connection.executemany('INSERT INTO output_routing(user_id,kind,sources) VALUES (?,?,?)',
                                       [(user['id'],kind,json.dumps(old_sources)) for kind,old_sources in previous_routes.items()])
                connection.execute('DELETE FROM routing_programs WHERE user_id=?', (user['id'],))
                connection.executemany('INSERT INTO routing_programs(user_id,id,sources) VALUES (?,?,?)',
                                       [(row['user_id'],row['id'],row['sources']) for row in previous_programs])
            c.write('UPDATE users SET selected_video_id=?,offline=? WHERE id=?',
                    (*previous_video, user['id']))
            try:
                c.reconcile()
            except Exception:
                c.logging.exception('Szenen-Rollback konnte MediaMTX nicht sofort abgleichen.')
            raise
        return jsonify(ok=True)

    def set_role(self, user, uid):
        c = self.c
        if not user['admin'] or uid == user['id']:
            raise c.Error('Diese Rollenänderung ist nicht erlaubt.', http_status=403)
        body = self.body()
        role = body.get('role')
        owner_id = body.get('chat_owner_id')
        if role not in self.ROLES:
            raise c.Error('Unbekannte Rolle.')
        if role == 'admin':
            owner_id = None
        elif role == 'moderator':
            try:
                owner_id = int(owner_id)
            except (TypeError, ValueError):
                raise c.Error('Moderator benötigt ein Chat-Konto.') from None
            if not c.rows("SELECT id FROM users WHERE id=? AND active=1 AND role!='moderator'", (owner_id,)):
                raise c.Error('Chat-Konto nicht gefunden.')
        else:
            owner_id = None
        if not c.rows('SELECT id FROM users WHERE id=?', (uid,)):
            raise c.Error('Benutzer nicht gefunden.', http_status=404)
        if role == 'moderator' and (owner_id == uid or c.rows("SELECT id FROM users WHERE role='moderator' AND chat_owner_id=? AND active=1", (uid,))):
            raise c.Error('Ein Chat-Konto mit zugewiesenen Moderatoren kann nicht selbst Moderator werden.', http_status=409)
        if role == 'moderator':
            c.forward(c.rows('SELECT * FROM users WHERE id=?', (uid,))[0], False)
            c.ENGINE.stop_record(uid, 'Konto wurde zur Chat-Moderation geändert.')
            c.ENGINE.stop_replay(uid)
            for table in ('scheduled_jobs',):
                c.write("UPDATE "+table+" SET status='cancelled' WHERE user_id=? AND status='pending'", (uid,))
            c.write('UPDATE automation_hooks SET enabled=0 WHERE user_id=?', (uid,))
            c.write('UPDATE export_targets SET enabled=0 WHERE user_id=?', (uid,))
        c.write('UPDATE users SET role=?,admin=?,chat_owner_id=?,version=version+1 WHERE id=?',
                (role, int(role == 'admin'), owner_id, uid))
        c.reconcile()
        return jsonify(ok=True)

    def install_passkey_routes(self):
        c = self.c
        @c.app.post('/api/passkeys/register/options')
        @c.login_required
        def registration_options(user):
            _, rp_id = self.origin()
            excluded = [row['credential_id'] for row in c.rows('SELECT credential_id FROM webauthn_credentials WHERE user_id=?', (user['id'],))]
            return jsonify(challenge=self.challenge('register', user['id']), rp_id=rp_id, user_id=_b64(str(user['id']).encode()),
                           username=user['username'], exclude=excluded)

        @c.app.post('/api/passkeys/register')
        @c.login_required
        def register_passkey(user):
            body = self.body()
            pending = self.consume_challenge('register')
            if pending['user_id'] != user['id']:
                raise c.Error('Passkey-Anfrage gehört zu einem anderen Konto.')
            try:
                origin, rp_id = self.origin()
                ident = body.get('credential_id', '')
                result = verify_registration_response(
                    credential={'id':ident, 'rawId':ident, 'type':'public-key', 'response':{
                        'clientDataJSON':body.get('client_data', ''), 'attestationObject':body.get('attestation_object', '')}},
                    expected_challenge=_decode(pending['challenge']), expected_rp_id=rp_id,
                    expected_origin=origin, require_user_verification=True)
            except Exception:
                raise c.Error('Passkey-Registrierung konnte nicht sicher bestätigt werden.') from None
            label = str(body.get('label', 'Passkey')).strip()[:80] or 'Passkey'
            codes = [secrets.token_hex(5).upper() for _ in range(10)]
            with c.LOCK, c.db() as connection:
                if connection.execute('SELECT 1 FROM webauthn_credentials WHERE credential_id=?', (_b64(result.credential_id),)).fetchone():
                    raise c.Error('Dieser Passkey ist bereits registriert.', http_status=409)
                connection.execute('INSERT INTO webauthn_credentials(user_id,credential_id,public_key,algorithm,sign_count,label,created,key_format) VALUES (?,?,?,?,?,?,?,?)',
                                   (user['id'], _b64(result.credential_id), result.credential_public_key, 0, result.sign_count, label, time.time(), 'cose'))
                connection.execute('DELETE FROM recovery_codes WHERE user_id=?', (user['id'],))
                connection.executemany('INSERT INTO recovery_codes(user_id,code_hash) VALUES (?,?)',
                    [(user['id'], self.recovery_hash(user['id'], code)) for code in codes])
            return jsonify(ok=True, recovery_codes=codes)

        @c.app.get('/api/passkeys')
        @c.login_required
        def passkeys(user):
            return jsonify(credentials=c.rows('SELECT id,label,created,last_used FROM webauthn_credentials WHERE user_id=? ORDER BY id', (user['id'],)))

        @c.app.delete('/api/passkeys/<int:ident>')
        @c.login_required
        def delete_passkey(user, ident):
            c.write('DELETE FROM webauthn_credentials WHERE id=? AND user_id=?', (ident, user['id']))
            return '', 204

        @c.app.post('/api/passkeys/login/options')
        def login_options():
            body = self.body()
            username = str(body.get('username', '')).lower().strip()
            found = c.rows('SELECT id FROM users WHERE username=? AND active=1', (username,))
            credentials = c.rows('SELECT credential_id FROM webauthn_credentials WHERE user_id=?', (found[0]['id'],)) if found else []
            if c.login_limited(username):
                raise c.Error('Zu viele Anmeldeversuche. Bitte in fünf Minuten erneut versuchen.', http_status=429)
            uid = found[0]['id'] if found else 0
            _, rp_id = self.origin()
            c.login_failure(username)
            return jsonify(challenge=self.challenge('login', uid), rp_id=rp_id,
                           allow=[row['credential_id'] for row in credentials])

        @c.app.post('/api/passkeys/login')
        def passkey_login():
            body = self.body()
            pending, client_hash = self.verify_client(str(body.get('client_data', '')), 'login')
            found = c.rows('''SELECT w.*,u.active,u.version,u.expert_preference FROM webauthn_credentials w
                              JOIN users u ON u.id=w.user_id WHERE w.credential_id=?''',
                           (str(body.get('credential_id', '')),))
            if not found or found[0]['user_id'] != pending.get('user_id') or not found[0]['active']:
                raise c.Error('Passkey-Anmeldung fehlgeschlagen.', http_status=401)
            credential = found[0]
            try:
                if credential['key_format'] == 'cose':
                    origin, rp_id = self.origin()
                    ident = credential['credential_id']
                    verified = verify_authentication_response(
                        credential={'id':ident, 'rawId':ident, 'type':'public-key', 'response':{
                            'clientDataJSON':body['client_data'], 'authenticatorData':body['authenticator_data'], 'signature':body['signature']}},
                        expected_challenge=_decode(pending['challenge']), expected_rp_id=rp_id,
                        expected_origin=origin, credential_public_key=credential['public_key'],
                        credential_current_sign_count=credential['sign_count'], require_user_verification=True)
                    counter = verified.new_sign_count
                else:
                    auth_data, counter = self.verify_authenticator(str(body.get('authenticator_data', '')))
                    key = serialization.load_der_public_key(credential['public_key'])
                    signature = _decode(str(body.get('signature', '')))
                    signed = auth_data + client_hash
                    if credential['algorithm'] == -7:
                        key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
                    else:
                        key.verify(signature, signed, padding.PKCS1v15(), hashes.SHA256())
            except Exception:
                raise c.Error('Passkey-Anmeldung fehlgeschlagen.', http_status=401) from None
            if credential['sign_count'] and counter and counter <= credential['sign_count']:
                raise c.Error('Der Passkey-Zähler ist ungültig; ein geklonter Authenticator ist möglich.', http_status=401)
            with c.db() as connection:
                cursor = connection.execute('UPDATE webauthn_credentials SET sign_count=?,last_used=? WHERE id=? AND sign_count=?',
                                            (max(counter, credential['sign_count']), time.time(), credential['id'], credential['sign_count']))
                if cursor.rowcount != 1:
                    raise c.Error('Die Passkey-Anfrage wurde bereits verwendet.', http_status=401)
            session.clear()
            session.update(uid=credential['user_id'], version=credential['version'], csrf=secrets.token_urlsafe(32),expert_mode=bool(credential['expert_preference']))
            return jsonify(ok=True)

        @c.app.post('/api/recovery/login')
        def recovery_login():
            body = self.body()
            username = str(body.get('username', '')).lower().strip()
            code = str(body.get('code', '')).upper().strip()
            if c.login_limited(username):
                raise c.Error('Zu viele Anmeldeversuche. Bitte in fünf Minuten erneut versuchen.', http_status=429)
            c.login_failure(username)
            found = c.rows('SELECT id,version,expert_preference FROM users WHERE username=? AND active=1', (username,))
            if not found:
                raise c.Error('Recovery-Code ungültig.', http_status=401)
            digest = self.recovery_hash(found[0]['id'], code)
            with c.db() as connection:
                cursor = connection.execute('UPDATE recovery_codes SET used=? WHERE user_id=? AND code_hash=? AND used IS NULL',
                                            (time.time(), found[0]['id'], digest))
                used = cursor.rowcount == 1
            if not used:
                raise c.Error('Recovery-Code ungültig oder bereits verwendet.', http_status=401)
            session.clear()
            session.update(uid=found[0]['id'], version=found[0]['version'], csrf=secrets.token_urlsafe(32),expert_mode=bool(found[0]['expert_preference']))
            return jsonify(ok=True)

    def recovery_hash(self, uid, code):
        return hashlib.sha256((str(uid) + ':' + code + ':' + self.c.app.secret_key).encode()).hexdigest()
