"""YouTube OAuth and per-user, on-demand Twitch / YouTube chat."""
import collections
import datetime
import hashlib
import hmac
import json
import secrets
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from flask import request, session, jsonify, redirect, render_template

YOUTUBE_SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'


def install_integrations(core):
    app, login = core.app, core.login_required
    hub = ChatHub(core)

    @app.post('/api/admin/google')
    @login
    def configure_google(user):
        if not user['admin']:
            return jsonify(error='Keine Berechtigung.'), 403
        body = request.get_json() or {}
        client = str(body.get('client_id', '')).strip()
        if not client.endswith('.apps.googleusercontent.com') or len(client) > 250:
            raise core.Error('Bitte die Client-ID der Google-Webanwendung eintragen.')
        core.set_setting('google_client_id', client)
        if body.get('client_secret'):
            core.set_setting('google_client_secret', str(body['client_secret']).strip())
        return jsonify(ok=True)

    @app.get('/oauth/youtube')
    @login
    def youtube_oauth(user):
        if not core.setting('google_client_id') or not core.setting('google_client_secret'):
            return redirect('/?notice=youtube_setup#settings')
        if not request.is_secure or request.host.split(':')[0] != urllib.parse.urlsplit(core.PUBLIC).hostname:
            return redirect('/?notice=use_domain')
        state = secrets.token_urlsafe(32)
        session['google_oauth'] = {'state': state, 'time': time.time(), 'uid': user['id']}
        return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urllib.parse.urlencode({
            'client_id': core.setting('google_client_id'), 'redirect_uri': core.PUBLIC + '/oauth/youtube/callback',
            'response_type': 'code', 'scope': YOUTUBE_SCOPE, 'access_type': 'offline', 'prompt': 'consent', 'state': state}))

    @app.get('/oauth/youtube/callback')
    @login
    def youtube_callback(user):
        state = session.pop('google_oauth', {})
        if (state.get('uid') != user['id'] or time.time() - state.get('time', 0) > 600
                or not state.get('state') or not hmac.compare_digest(state['state'], request.args.get('state', ''))):
            return redirect('/?notice=youtube_failed#settings')
        if request.args.get('error') or not request.args.get('code'):
            return redirect('/?notice=youtube_cancelled#settings')
        token, stored = '', False
        try:
            grant = core.remote('https://oauth2.googleapis.com/token', urllib.parse.urlencode({
                'code': request.args['code'], 'client_id': core.setting('google_client_id'),
                'client_secret': core.setting('google_client_secret'), 'redirect_uri': core.PUBLIC + '/oauth/youtube/callback',
                'grant_type': 'authorization_code'}).encode())
            token = grant['access_token']
            if YOUTUBE_SCOPE not in grant.get('scope', '').split() or not grant.get('refresh_token'):
                raise core.Error('YouTube-Berechtigung fehlt.')
            account = core.remote('https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true',
                                  headers={'Authorization': 'Bearer ' + token})['items'][0]
            with core.OAUTH_LOCK:
                core.write('INSERT OR REPLACE INTO youtube_auth(user_id,channel_id,name,access,refresh,expires,client_id) VALUES (?,?,?,?,?,?,?)',
                           (user['id'], account['id'], account['snippet']['title'], core.encrypt(token), core.encrypt(grant['refresh_token']),
                            time.time() + grant.get('expires_in', 3600), core.setting('google_client_id')))
            hub.stop_platform(user['id'], 'youtube', clear=True)
            stored = True
            return redirect('/?notice=youtube_ok#settings')
        except Exception:
            return redirect('/?notice=youtube_failed#settings')
        finally:
            if token and not stored:
                try:
                    core.remote('https://oauth2.googleapis.com/revoke', urllib.parse.urlencode({'token': token}).encode())
                except core.Error:
                    pass

    @app.get('/api/youtube/broadcasts')
    @login
    def youtube_broadcasts(user):
        result = hub.youtube_api(user['id'], 'liveBroadcasts?part=snippet,contentDetails,status&mine=true&broadcastType=all&maxResults=50')
        return jsonify(broadcasts=[{'id': x['id'], 'title': x['snippet']['title'], 'status': x['status']['lifeCycleStatus'],
                                    'chat': bool(x['snippet'].get('liveChatId'))} for x in result.get('items', [])
                                   if x['status']['lifeCycleStatus'] != 'complete'])

    @app.post('/api/youtube/broadcast')
    @login
    def youtube_broadcast(user):
        body = request.get_json() or {}
        ident = str(body.get('id', ''))
        if not core.re.fullmatch(r'[A-Za-z0-9_-]{6,100}', ident):
            raise core.Error('Bitte eine eigene YouTube-Sendung auswählen.')
        auth = core.rows('SELECT * FROM youtube_auth WHERE user_id=?', (user['id'],))
        if not auth:
            raise core.Error('Bitte YouTube verbinden.')
        result = hub.youtube_api(user['id'], 'liveBroadcasts?' + urllib.parse.urlencode({'part': 'snippet,contentDetails,status', 'id': ident}))
        if not result.get('items') or result['items'][0]['snippet']['channelId'] != auth[0]['channel_id']:
            raise core.Error('Diese Sendung gehört nicht zu deinem verbundenen Kanal.')
        broadcast = result['items'][0]
        if body.get('output'):
            core.require_stopped(user)
            stream_id = broadcast['contentDetails'].get('boundStreamId')
            if not stream_id:
                raise core.Error('Dieser Sendung ist noch kein YouTube-Stream zugewiesen. Bitte im YouTube Studio einrichten.')
            streams = hub.youtube_api(user['id'], 'liveStreams?' + urllib.parse.urlencode({'part': 'cdn', 'id': stream_id}))
            info = streams['items'][0]['cdn']['ingestionInfo']
            address = info.get('rtmpsIngestionAddress') or info['ingestionAddress']
            endpoint = core.validate_output(address.rstrip('/') + '#' + info['streamName'])
            core.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,0) ON CONFLICT(user_id,kind) DO UPDATE SET endpoint=excluded.endpoint', (user['id'], 'youtube', core.encrypt(endpoint)))
        core.write('UPDATE youtube_auth SET broadcast_id=?,chat_id=? WHERE user_id=?',
                   (ident, broadcast['snippet'].get('liveChatId', ''), user['id']))
        hub.stop_platform(user['id'], 'youtube', clear=True)
        return jsonify(ok=True, title=broadcast['snippet']['title'])

    @app.post('/api/youtube/disconnect')
    @login
    def youtube_disconnect(user):
        found = core.rows('SELECT * FROM youtube_auth WHERE user_id=?', (user['id'],))
        core.write('DELETE FROM youtube_auth WHERE user_id=?', (user['id'],))
        hub.stop_platform(user['id'], 'youtube', clear=True)
        if found:
            try:
                core.remote('https://oauth2.googleapis.com/revoke', urllib.parse.urlencode({'token': core.decrypt(found[0]['refresh'])}).encode())
            except core.Error:
                pass
        return jsonify(ok=True)

    @app.post('/api/twitch/disconnect')
    @login
    def twitch_disconnect(user):
        core.remove_twitch_auth(user['id'])
        core.write("UPDATE users SET twitch_name='' WHERE id=?", (user['id'],))
        hub.stop_platform(user['id'], 'twitch', clear=True)
        return jsonify(ok=True)

    @app.get('/api/chat')
    @login
    def chat_read(user):
        return jsonify(hub.read(user))

    @app.post('/api/chat/send')
    @login
    def chat_send(user):
        return jsonify(hub.send(user, request.get_json() or {}))

    @app.route('/api/chat/widget', methods=['GET', 'POST'])
    @login
    def chat_widget(user):
        result = core.rows('SELECT * FROM widget_tokens WHERE user_id=?', (user['id'],))
        if request.method == 'POST' or not result:
            token = secrets.token_urlsafe(36)
            core.write('INSERT OR REPLACE INTO widget_tokens(user_id,token_hash,token) VALUES (?,?,?)',
                       (user['id'], hashlib.sha256(token.encode()).hexdigest(), core.encrypt(token)))
        else:
            token = core.decrypt(result[0]['token'])
        return jsonify(url=core.PUBLIC + '/chat/widget/' + token)

    def widget_user(token):
        if len(token) > 100:
            from werkzeug.exceptions import NotFound
            raise NotFound()
        found = core.rows('SELECT users.* FROM widget_tokens JOIN users ON users.id=widget_tokens.user_id WHERE token_hash=? AND users.active=1',
                          (hashlib.sha256(token.encode()).hexdigest(),))
        if not found:
            from werkzeug.exceptions import NotFound
            raise NotFound()
        return found[0]

    @app.get('/chat/widget/<token>')
    def widget(token):
        widget_user(token)
        return render_template('chat-widget.html')

    @app.get('/api/chat/widget-data/<token>')
    def widget_data(token):
        user = widget_user(token)
        return jsonify(hub.read(user))

    return hub


class ChatHub:
    def __init__(self, core):
        self.c = core
        self.lock = threading.RLock()
        self.messages = {}
        self.seen = {}
        self.used = {}
        self.workers = {}
        self.status = {}
        self.nonces = collections.OrderedDict()
        self.sent_at = {}
        self.send_locks = {}
        self.youtube_pages = {}

    def info(self, user):
        auth = self.c.rows('SELECT scopes FROM twitch_auth WHERE user_id=?', (user['id'],))
        twitch = bool(auth and self.c.CHAT_SCOPES.issubset(set(json.loads(auth[0]['scopes'] or '[]'))))
        youtube = self.c.rows('SELECT name,broadcast_id,chat_id FROM youtube_auth WHERE user_id=?', (user['id'],))
        return {'twitch_ready': twitch, 'youtube_connected': bool(youtube), 'youtube_name': youtube[0]['name'] if youtube else '',
                'youtube_chat_ready': bool(youtube and youtube[0]['chat_id']), 'broadcast_id': youtube[0]['broadcast_id'] if youtube else '',
                'google_ready': bool(self.c.setting('google_client_id') and self.c.setting('google_client_secret'))}

    def interested(self, uid, stop):
        return not stop.is_set() and time.monotonic() - self.used.get(uid, 0) < 75

    def prune(self, active):
        with self.lock:
            for uid in list(self.messages):
                if uid not in active:
                    self.messages.pop(uid, None)
                    self.seen.pop(uid, None)
                    self.used.pop(uid, None)
                    self.sent_at.pop(uid, None)
                    self.send_locks.pop(uid, None)
            for key in list(self.status):
                if key[0] not in active:
                    self.status.pop(key, None)
            for key in list(self.youtube_pages):
                if key[0] not in active:
                    self.youtube_pages.pop(key, None)
            for key in list(self.workers):
                if key[0] not in active:
                    stop = self.workers.pop(key, None)
                    if stop:
                        stop.set()

    def stop_platform(self, uid, platform, clear=False):
        with self.lock:
            job = self.workers.pop((uid, platform), None)
            if job:
                job.set()
            self.status.pop((uid, platform), None)
            if clear:
                self.messages[uid] = collections.deque((m for m in self.messages.get(uid, []) if m['platform'] != platform), maxlen=200)
                self.seen[uid] = collections.OrderedDict((k, v) for k, v in self.seen.get(uid, {}).items() if not k.startswith(platform + ':'))

    def set_status(self, uid, platform, text, stop):
        with self.lock:
            if not stop.is_set():
                self.status[(uid, platform)] = text

    def read(self, user):
        uid = user['id']
        info = self.info(user)
        with self.lock:
            self.used[uid] = time.monotonic()
            for platform, ready in [('twitch', info['twitch_ready']), ('youtube', info['youtube_chat_ready'])]:
                key = (uid, platform)
                if ready and key not in self.workers:
                    stop = threading.Event()
                    self.workers[key] = stop
                    threading.Thread(target=self.run, args=(uid, platform, stop), daemon=True).start()
                elif not ready and key in self.workers:
                    self.stop_platform(uid, platform, clear=True)
            return {'messages': list(self.messages.get(uid, [])), 'connections': {
                'twitch': self.status.get((uid, 'twitch'), 'Verbinden …' if info['twitch_ready'] else 'Twitch für Chat erneut verbinden'),
                'youtube': self.status.get((uid, 'youtube'), 'Verbinden …' if info['youtube_chat_ready'] else 'YouTube-Sendung für Chat auswählen' if info['youtube_connected'] else 'YouTube-Konto verbinden')}, **info}

    def add(self, uid, platform, ident, author, text, author_id='', published=''):
        if not ident or not text:
            return
        key = platform + ':' + ident
        with self.lock:
            seen = self.seen.setdefault(uid, collections.OrderedDict())
            if key in seen:
                return
            seen[key] = True
            while len(seen) > 1000:
                seen.popitem(last=False)
            self.messages.setdefault(uid, collections.deque(maxlen=200)).append({
                'id': key, 'platform': platform, 'author': str(author)[:100], 'author_id': author_id,
                'text': str(text)[:2000], 'time': published or datetime.datetime.now(datetime.timezone.utc).isoformat()})

    def remove(self, uid, platform, ident=None, author=None):
        with self.lock:
            self.messages[uid] = collections.deque((m for m in self.messages.get(uid, [])
                if not (m['platform'] == platform and (ident is None and author is None or ident and m['id'] == platform + ':' + ident or author and m['author_id'] == author))), maxlen=200)

    def run(self, uid, platform, stop):
        delay = 5
        try:
            while self.interested(uid, stop):
                active = self.c.rows('SELECT active FROM users WHERE id=?', (uid,))
                if not active or not active[0]['active']:
                    self.remove(uid, platform)
                    break
                try:
                    if platform == 'twitch':
                        self.twitch_stream(uid, stop)
                    else:
                        self.youtube_stream(uid, stop)
                    delay = 5
                except self.c.Error as exc:
                    self.set_status(uid, platform, str(exc), stop)
                except Exception:
                    self.set_status(uid, platform, 'Verbindung unterbrochen · erneuter Versuch folgt', stop)
                if stop.wait(delay):
                    break
                delay = min(120, delay * 2)
        finally:
            with self.lock:
                if self.workers.get((uid, platform)) is stop:
                    self.workers.pop((uid, platform), None)
                    self.status.pop((uid, platform), None)

    def twitch_stream(self, uid, stop):
        import websocket
        token, broadcaster = self.c.validated_twitch_token(uid)
        found = self.c.rows('SELECT scopes FROM twitch_auth WHERE user_id=?', (uid,))
        if not found or not self.c.CHAT_SCOPES.issubset(set(json.loads(found[0]['scopes']))):
            raise self.c.Error('Twitch für Chat erneut verbinden')
        address, reconnect = 'wss://eventsub.wss.twitch.tv/ws?keepalive_timeout_seconds=30', False
        pending_socket, pending_welcome = None, None
        while self.interested(uid, stop):
            ws = pending_socket or websocket.create_connection(address, timeout=10, enable_multithread=True)
            pending_socket = None
            try:
                welcome = pending_welcome or json.loads(ws.recv())
                pending_welcome = None
                if welcome['metadata']['message_type'] != 'session_welcome':
                    raise self.c.Error('Twitch-Chat konnte nicht gestartet werden.')
                session_id = welcome['payload']['session']['id']
                if not reconnect:
                    for event in ('channel.chat.message', 'channel.chat.message_delete', 'channel.chat.clear', 'channel.chat.clear_user_messages'):
                        self.c.remote('https://api.twitch.tv/helix/eventsub/subscriptions', json.dumps({
                            'type': event, 'version': '1', 'condition': {'broadcaster_user_id': broadcaster, 'user_id': broadcaster},
                            'transport': {'method': 'websocket', 'session_id': session_id}}).encode(),
                            {'Authorization': 'Bearer ' + token, 'Client-Id': self.c.setting('client_id'), 'Content-Type': 'application/json'}, 'POST')
                self.set_status(uid, 'twitch', 'Verbunden', stop)
                last_frame = time.monotonic()
                reconnect = False
                while self.interested(uid, stop):
                    try:
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        if time.monotonic() - last_frame > 40:
                            raise self.c.Error('Twitch-Chat antwortet nicht · erneuter Versuch folgt')
                        continue
                    if not raw:
                        break
                    last_frame = time.monotonic()
                    frame = json.loads(raw)
                    kind, payload = frame['metadata']['message_type'], frame['payload']
                    if kind == 'session_reconnect':
                        proposed = payload['session']['reconnect_url']
                        parsed = urllib.parse.urlsplit(proposed)
                        if parsed.scheme != 'wss' or parsed.hostname != 'eventsub.wss.twitch.tv':
                            raise self.c.Error('Ungültige Twitch-Neuverbindung.')
                        # Receive the new welcome before closing the old socket,
                        # so Twitch transfers subscriptions without a read gap.
                        pending_socket = websocket.create_connection(proposed, timeout=10, enable_multithread=True)
                        pending_welcome = json.loads(pending_socket.recv())
                        address, reconnect = proposed, True
                        break
                    if kind == 'revocation':
                        raise self.c.Error('Twitch-Chatberechtigung widerrufen · bitte erneut verbinden')
                    if kind != 'notification':
                        continue
                    event = payload['event']
                    event_type = payload['subscription']['type']
                    if event_type == 'channel.chat.message':
                        self.add(uid, 'twitch', event['message_id'], event['chatter_user_name'], event['message']['text'], event['chatter_user_id'], frame['metadata'].get('message_timestamp', ''))
                    elif event_type == 'channel.chat.message_delete':
                        self.remove(uid, 'twitch', ident=event['message_id'])
                    elif event_type == 'channel.chat.clear_user_messages':
                        self.remove(uid, 'twitch', author=event['target_user_id'])
                    elif event_type == 'channel.chat.clear':
                        self.remove(uid, 'twitch')
            finally:
                ws.close()
            if not reconnect:
                break
        if pending_socket:
            pending_socket.close()

    def youtube_token(self, uid, force=False):
        with self.c.OAUTH_LOCK:
            found = self.c.rows('SELECT * FROM youtube_auth WHERE user_id=?', (uid,))
            if not found:
                raise self.c.Error('Bitte YouTube verbinden.')
            auth = found[0]
            if auth['client_id'] != self.c.setting('google_client_id'):
                raise self.c.Error('Google-App geändert · YouTube bitte erneut verbinden.')
            if force or auth['expires'] < time.time() + 60:
                try:
                    grant = self.c.remote('https://oauth2.googleapis.com/token', urllib.parse.urlencode({
                        'grant_type': 'refresh_token', 'client_id': auth['client_id'], 'client_secret': self.c.setting('google_client_secret'),
                        'refresh_token': self.c.decrypt(auth['refresh'])}).encode())
                except self.c.Error as exc:
                    if exc.status in (400, 401, 403):
                        raise self.c.Error('YouTube-Berechtigung abgelaufen · bitte erneut verbinden.') from None
                    raise
                auth['access'], auth['expires'] = self.c.encrypt(grant['access_token']), time.time() + grant.get('expires_in', 3600)
                self.c.write('UPDATE youtube_auth SET access=?,expires=? WHERE user_id=?', (auth['access'], auth['expires'], uid))
            return self.c.decrypt(auth['access']), auth

    def youtube_api(self, uid, path, body=None):
        for attempt in range(2):
            token, auth = self.youtube_token(uid, force=bool(attempt))
            req = urllib.request.Request('https://www.googleapis.com/youtube/v3/' + path,
                data=json.dumps(body).encode() if body is not None else None,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}, method='POST' if body is not None else 'GET')
            try:
                with urllib.request.urlopen(req, timeout=12) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code == 401 and attempt == 0:
                    continue
                try:
                    reasons = [x.get('reason') for x in json.load(exc).get('error', {}).get('errors', [])]
                except (ValueError, AttributeError):
                    reasons = []
                if 'quotaExceeded' in reasons or 'dailyLimitExceeded' in reasons:
                    raise self.c.Error('YouTube-API-Tageskontingent erreicht.') from None
                if 'liveStreamingNotEnabled' in reasons:
                    raise self.c.Error('Bitte Livestreaming im YouTube Studio zuerst aktivieren.') from None
                if any(x in reasons for x in ('liveChatEnded', 'liveChatDisabled', 'liveChatNotFound')):
                    raise self.c.Error('Der YouTube-Chat ist beendet, deaktiviert oder noch nicht verfügbar.') from None
                raise self.c.Error('YouTube-Anfrage abgewiesen. Konto, Berechtigung und Sendung prüfen.') from None
            except (OSError, ValueError):
                raise self.c.Error('YouTube ist gerade nicht erreichbar.') from None

    def youtube_stream(self, uid, stop):
        import grpc
        import stream_list_pb2 as proto
        import stream_list_pb2_grpc as service
        token, auth = self.youtube_token(uid)
        if not auth['chat_id'] or not auth['broadcast_id']:
            raise self.c.Error('YouTube-Sendung für Chat auswählen')
        broadcast = self.youtube_api(uid, 'liveBroadcasts?' + urllib.parse.urlencode({'part': 'status', 'id': auth['broadcast_id']}))
        if not broadcast.get('items') or broadcast['items'][0]['status']['lifeCycleStatus'] not in ('live', 'testing'):
            self.set_status(uid, 'youtube', 'Warte auf Live-Sendung · erneute Prüfung in 2 Minuten', stop)
            stop.wait(120)
            return
        with grpc.secure_channel('youtube.googleapis.com:443', grpc.ssl_channel_credentials()) as channel:
            request = proto.LiveChatMessageListRequest(live_chat_id=auth['chat_id'], part=['id', 'snippet', 'authorDetails'], page_token=self.youtube_pages.get((uid, auth['chat_id']), ''))
            call = service.V3DataLiveChatMessageServiceStub(channel).StreamList(request,
                metadata=(('authorization', 'Bearer ' + token),), timeout=max(30, min(3000, auth['expires'] - time.time() - 60)))
            self.set_status(uid, 'youtube', 'Verbunden', stop)
            # Cancel even a quiet stream when no dashboard or widget is watching.
            def cancel_idle():
                while self.interested(uid, stop) and call.is_active():
                    stop.wait(5)
                call.cancel()
            threading.Thread(target=cancel_idle, daemon=True).start()
            try:
                for response in call:
                    if not self.interested(uid, stop):
                        break
                    if response.next_page_token:
                        self.youtube_pages[(uid, auth['chat_id'])] = response.next_page_token
                    for item in response.items:
                        if item.snippet.type == 2:
                            self.remove(uid, 'youtube', ident=item.id)
                        else:
                            self.add(uid, 'youtube', item.id, item.author_details.display_name, item.snippet.display_message,
                                     item.author_details.channel_id, item.snippet.published_at)
                    if response.offline_at:
                        self.set_status(uid, 'youtube', 'Live-Sendung beendet', stop)
                        stop.wait(120)
                        break
            except grpc.RpcError as exc:
                if stop.is_set() or not self.interested(uid, stop):
                    return
                if exc.code() == grpc.StatusCode.UNAUTHENTICATED:
                    self.c.write('UPDATE youtube_auth SET expires=0 WHERE user_id=?', (uid,))
                if exc.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
                    self.set_status(uid, 'youtube', 'YouTube-Kontingent erreicht · erneuter Versuch später', stop)
                    stop.wait(300)
                    return
                raise self.c.Error('YouTube-Chat unterbrochen · erneuter Versuch folgt') from None
            finally:
                call.cancel()

    def send(self, user, body):
        uid = user['id']
        text = str(body.get('message', '')).strip()
        targets = body.get('targets', [])
        nonce = str(body.get('nonce', ''))
        if not isinstance(targets, list) or not targets or any(t not in ('twitch', 'youtube') for t in targets):
            raise self.c.Error('Bitte Twitch, YouTube oder beide Chats wählen.')
        targets = sorted(set(targets))
        if not text or len(text) > (200 if 'youtube' in targets else 500) or any(ord(x) < 32 and x not in '\t' for x in text):
            raise self.c.Error('Bitte eine Nachricht mit maximal 200 Zeichen für YouTube bzw. 500 Zeichen für Twitch eingeben.')
        if not self.c.re.fullmatch(r'[A-Za-z0-9_-]{12,100}', nonce):
            raise self.c.Error('Ungültige Nachrichtenkennung. Bitte erneut versuchen.')
        digest = hashlib.sha256(json.dumps([text, targets]).encode()).hexdigest()
        with self.send_locks.setdefault(uid, threading.Lock()):
            old = self.nonces.get((uid, nonce))
            if old:
                if old[0] != digest:
                    raise self.c.Error('Diese Nachrichtenkennung wurde bereits verwendet.')
                return old[1]
            if time.monotonic() - self.sent_at.get(uid, 0) < 2:
                raise self.c.Error('Bitte zwei Sekunden zwischen Nachrichten warten.')
            info = self.info(user)
            if 'twitch' in targets and not info['twitch_ready']:
                raise self.c.Error('Bitte Twitch zuerst für Chat erneut verbinden.')
            if 'youtube' in targets and not info['youtube_chat_ready']:
                raise self.c.Error('Bitte zuerst deinen YouTube-Chat auswählen.')
            self.sent_at[uid] = time.monotonic()
            results = {}
            for target in targets:
                try:
                    if target == 'twitch':
                        token, broadcaster = self.c.validated_twitch_token(uid)
                        response = self.c.remote('https://api.twitch.tv/helix/chat/messages', json.dumps({
                            'broadcaster_id': broadcaster, 'sender_id': broadcaster, 'message': text}).encode(),
                            {'Authorization': 'Bearer ' + token, 'Client-Id': self.c.setting('client_id'), 'Content-Type': 'application/json'}, 'POST')['data'][0]
                        if not response.get('is_sent'):
                            raise self.c.Error('Twitch hat die Nachricht nicht angenommen.')
                        self.add(uid, 'twitch', response['message_id'], user['twitch_name'] or user['username'], text, broadcaster)
                    else:
                        auth = self.c.rows('SELECT chat_id,name,channel_id FROM youtube_auth WHERE user_id=?', (uid,))[0]
                        response = self.youtube_api(uid, 'liveChat/messages?part=snippet', {'snippet': {'liveChatId': auth['chat_id'],
                            'type': 'textMessageEvent', 'textMessageDetails': {'messageText': text}}})
                        self.add(uid, 'youtube', response['id'], auth['name'], text, auth['channel_id'])
                    results[target] = {'ok': True}
                except self.c.Error as exc:
                    results[target] = {'ok': False, 'error': str(exc)}
                except (KeyError, TypeError, IndexError):
                    results[target] = {'ok': False, 'error': 'Unerwartete Plattformantwort. Die Zustellung ist nicht bestätigt.'}
            result = {'ok': all(x['ok'] for x in results.values()), 'results': results}
            self.nonces[(uid, nonce)] = (digest, result)
            while len(self.nonces) > 500:
                self.nonces.popitem(last=False)
            return result
