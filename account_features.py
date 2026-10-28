"""Admin removal of inactive accounts with isolated, recoverable media archives."""
import json
import secrets
import time
import yaml
from flask import jsonify, request
from routing_model import owner


def install_account_routes(c):
    @c.app.post('/api/admin/users/<int:uid>/delete')
    @c.login_required
    def delete_user(user,uid):
        if not user['admin'] or uid==user['id']:
            raise c.Error('Dieses Konto darf nicht gelöscht werden.',http_status=403)
        with c.LOCK:
            found = c.rows('SELECT * FROM users WHERE id=?',(uid,))
            if not found:
                raise c.Error('Benutzer nicht gefunden.',http_status=404)
            target = found[0]
            if target['active']:
                raise c.Error('Bitte den Benutzer vor dem Löschen deaktivieren.',http_status=409)
            body = request.get_json(silent=True)
            if not isinstance(body,dict) or body.get('confirm')!=target['username']:
                raise c.Error('Zum Löschen bitte den Benutzernamen bestätigen.')
            if target['upload_state'] in ('queued','processing') or uid in c.UPLOAD_RESERVATIONS:
                raise c.Error('Für diesen Benutzer läuft noch eine Medienverarbeitung. Bitte deren Abschluss abwarten.',http_status=409)
            if c.rows("SELECT id FROM users WHERE role='moderator' AND chat_owner_id=? AND active=1",(uid,)):
                raise c.Error('Diesem Konto sind aktive Moderatoren zugewiesen. Bitte deren Rolle oder Chat-Zuordnung zuerst ändern.',http_status=409)
            if c.rows("SELECT id FROM recordings WHERE user_id=? AND status IN ('recording','finishing')",(uid,)):
                raise c.Error('Die Aufnahme dieses Benutzers wird noch beendet. Bitte kurz warten.',http_status=409)
            automation = c.FEATURES.automation
            if uid in automation.busy_users:
                raise c.Error('Für diesen Benutzer läuft noch ein Auftrag oder Export. Bitte dessen Abschluss abwarten.', http_status=409)
            if c.FEATURES.playback.active_clips.get(uid):
                raise c.Error('Für diesen Benutzer wird noch ein Clip erstellt. Bitte dessen Abschluss abwarten.', http_status=409)
            for key in list(c.PLAYLISTS.jobs):
                if key[0] == uid:c.PLAYLISTS.checkpoint(key, pause=True)
            prefix = target['prefix']
            if prefix!=c.NAMESPACE+'/'+target['username']+'/':
                raise c.Error('Dieses ältere Pfadschema benötigt zuerst eine Migration.')
            for key in list(c.ENGINE.relays):
                if owner(key)==uid:
                    c.ENGINE.stop_relay(key)
            c.ENGINE.stop_record(uid,'Benutzer gelöscht.')
            c.ENGINE.stop_replay(uid)
            for key in list(c.FEATURES.program_preview.jobs):
                if owner(key)==uid:
                    c.FEATURES.program_preview.stop(key)
            before = c.CONFIG.read_text()
            config = yaml.safe_load(before)
            owned = {name:value for name,value in config.get('paths',{}).items() if name.startswith(prefix)}
            config['paths'] = {name:value for name,value in config.get('paths',{}).items() if name not in owned}
            config['authInternalUsers'] = [entry for entry in config.get('authInternalUsers',[]) if entry.get('user')!=c.media_username(target)]
            tables = ('videos','recordings','outputs','twitch_auth','youtube_auth','widget_tokens','viewer_links',
                      'routing_sources','output_routing','routing_programs','scenes','webauthn_credentials',
                      'recovery_codes','discord_auth','routing_policy','clips','automation_hooks','scheduled_jobs',
                      'export_targets','exported_media','notification_settings','webauthn_challenges',
                      'playlist_folders','playlists','playlist_profiles','playlist_positions','playlist_output_state','video_uploads')
            snapshot = {table:c.rows('SELECT * FROM '+table+' WHERE user_id=?',(uid,)) for table in tables}
            archive = c.DATA/'deleted-users'/(str(uid)+'-'+str(int(time.time()))+'-'+secrets.token_hex(4))
            archive.mkdir(parents=True,mode=0o700)
            moved = []
            try:
                for folder in (c.DATA/'media'/target['username'],c.DATA/'recordings'/target['username'],c.DATA/'clips'/target['username'],c.DATA/'playout'/str(uid),
                               c.FEATURES.native_root/target['username']):
                    if folder.is_symlink():
                        raise c.Error('Ein Benutzerverzeichnis ist ein symbolischer Link; Löschung abgebrochen.')
                    if folder.exists():
                        destination = folder.with_name('.deleted-'+folder.name+'-'+str(uid)+'-'+secrets.token_hex(4))
                        folder.rename(destination)
                        moved.append((folder,destination))
                c.atomic(archive/'manifest.json',json.dumps({'user':target,'tables':snapshot,'paths':owned,
                         'media':[{'original':str(a),'archive':str(b)} for a,b in moved]},ensure_ascii=False))
                with c.db() as connection:
                    for table in tables:
                        connection.execute('DELETE FROM '+table+' WHERE user_id=?',(uid,))
                    connection.execute('DELETE FROM users WHERE id=?',(uid,))
                    c.atomic(c.CONFIG,yaml.safe_dump(config,sort_keys=False,allow_unicode=True))
            except Exception:
                c.atomic(c.CONFIG,before)
                for original,renamed in reversed(moved):
                    renamed.rename(original)
                raise
            c.CHAT.prune({row['id'] for row in c.rows('SELECT id FROM users WHERE active=1')})
            c.ENGINE.snapshot.pop(uid,None)
            try:
                c.sync_media_runtime(owned)
            except c.Error:
                c.logging.warning('Laufzeitbereinigung des gelöschten Benutzers wartet auf MediaMTX.')
            return jsonify(ok=True,archived=True)
