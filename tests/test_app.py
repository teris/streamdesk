import os
import io
from html.parser import HTMLParser
from email.message import Message
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import yaml

ROOT = Path(__file__).resolve().parents[1]
old_temp = tempfile.tempdir
TEMP = tempfile.TemporaryDirectory(prefix='streamdesk-unit-')
BASE = Path(TEMP.name)
(BASE / 'media.yml').write_text(yaml.safe_dump({'authMethod': 'internal', 'authInternalUsers': [], 'paths': {'foreign': {'source': 'publisher'}}}))
(BASE / 'fixture.mp4').write_bytes(b'not-a-real-movie-test-fixture')
os.environ.update(STREAMDESK_ENGINE='0', STREAMDESK_DATA=str(BASE / 'data'), MEDIAMTX_CONFIG=str(BASE / 'media.yml'),
                  STREAMDESK_DEFAULT_CLIP=str(BASE / 'fixture.mp4'), STREAMDESK_NAMESPACE='unittest',
                  STREAMDESK_PUBLIC='https://stream.example.com', MEDIAMTX_RTMP_PORT='11935', MEDIAMTX_SRT_PORT='18890')
sys.path.insert(0, str(ROOT))
import app
app.app.config['TESTING'] = True
with patch.object(app.threading, 'Thread'):
    UID = app.add_user('alice', 'Fixture-Only-Password-12345')
    OTHER = app.add_user('bobby', 'Fixture-Only-Password-98765')


def tearDownModule():
    tempfile.tempdir = old_temp
    TEMP.cleanup()


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID, version=1, csrf='fixture-csrf')
        self.headers = {'X-CSRF-Token': 'fixture-csrf'}

    def test_ingest_host_ports_and_namespace(self):
        data = self.client.get('/api/ingest').json
        self.assertIn(':11935/unittest/alice/source1?', data['rtmp'])
        self.assertIn(':18890?', data['srt'])
        self.assertEqual(data['username'], 'streamdesk_unittest_alice')

    def test_srt_url_has_explicit_obs_options_and_separate_stream_id(self):
        data = self.client.get('/api/ingest').json
        parsed = urllib.parse.urlsplit(data['srt'])
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(query['streamid'], [data['stream_id']])
        self.assertEqual(query['mode'], ['caller'])
        self.assertEqual(query['latency'], ['1000000'])
        self.assertEqual(query['pkt_size'], ['1316'])
        self.assertEqual(data['srt_server'], 'srt://127.0.0.1:18890')
        self.assertEqual(data['stream_id'].split(':')[2:], [data['username'], data['password']])

    def test_builtin_overlay_is_local_but_arbitrary_private_urls_are_blocked(self):
        self.assertEqual(app.validate_browser_url(app.PUBLIC + '/overlay-demo'), app.PUBLIC + '/overlay-demo')
        self.assertEqual(app.validate_browser_url('https://stream.example.com/overlay-demo'), app.PUBLIC + '/overlay-demo')
        for address in ('http://127.0.0.1/admin', 'https://127.0.0.1/private', 'javascript:alert(1)', 'http://127.0.0.1:8080/overlay-demo'):
            with self.assertRaises(app.Error):
                app.validate_browser_url(address)

    def test_csrf_rejects_non_ascii_header_without_500(self):
        response = self.client.post('/api/logout', headers={'X-CSRF-Token': 'füßchen'})
        self.assertEqual(response.status_code, 403)

    def test_other_users_media_is_private(self):
        ident = app.rows('SELECT id FROM videos WHERE user_id=?', (OTHER,))[0]['id']
        self.assertEqual(self.client.get('/media/video/' + str(ident)).status_code, 404)
        self.assertEqual(self.client.post('/api/videos/' + str(ident) + '/delete', json={}, headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get('/api/admin').status_code, 403)

    def test_selection_does_not_disconnect_accounts_or_drop_keys(self):
        for kind in ('twitch', 'youtube'):
            response = self.client.post('/api/output', json={'kind': kind, 'key': 'fixture-stream-key-123456'}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
        self.assertFalse(any(x['selected'] for x in app.rows('SELECT selected FROM outputs WHERE user_id=?', (UID,))))
        for kinds in (['twitch'], ['youtube'], ['twitch', 'youtube'], []):
            response = self.client.post('/api/outputs/select', json={'kinds': kinds}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(app.rows('SELECT * FROM outputs WHERE user_id=?', (UID,))), 2)
            self.assertEqual({r['kind'] for r in app.rows('SELECT kind FROM outputs WHERE user_id=? AND selected=1', (UID,))}, set(kinds))

    def test_read_only_widget_rotation_and_csrf(self):
        url = self.client.get('/api/chat/widget').json['url']
        token = urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]
        public = app.app.test_client()
        self.assertEqual(public.get('/api/chat/widget-data/' + token).status_code, 200)
        self.assertIn(public.post('/api/chat/send', json={}).status_code, (401, 403))
        self.assertEqual(self.client.post('/api/chat/widget', json={}).status_code, 403)
        self.client.post('/api/chat/widget', json={}, headers=self.headers)
        self.assertEqual(public.get('/api/chat/widget-data/' + token).status_code, 404)


class MediaFeatureTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID, version=1, csrf='feature-csrf')
        self.headers = {'X-CSRF-Token': 'feature-csrf'}
        self.config = app.CONFIG.read_text()
        self.addCleanup(app.CONFIG.write_text, self.config)
        app.write("UPDATE users SET source_mode='auto',theme='system',renew_resume=0,renew_interval=0 WHERE id=?", (UID,))
        app.write('DELETE FROM viewer_links WHERE user_id=?', (UID,))
        self.user = app.rows('SELECT * FROM users WHERE id=?', (UID,))[0]

    def enable(self):
        response = self.client.post('/api/expert-mode', json={'enabled': True}, headers=self.headers)
        self.assertEqual(response.status_code, 200)

    def test_expert_mode_blocks_direct_requests_including_admin(self):
        for path, body in [('/api/sources/mode', {'mode':'source2'}), ('/api/native-recording', {'source':'live','enabled':True}),
                           ('/api/viewer-link', {'enabled':True}), ('/api/admin/webrtc', {'enabled':True}),
                           ('/api/outputs/twitch/start', {}), ('/api/outputs/twitch/stop', {}),
                           ('/api/renewal', {}), ('/api/renewal/now', {})]:
            with self.subTest(path=path), patch.object(app, 'mtx') as mtx:
                response = self.client.post(path, json=body, headers=self.headers)
                self.assertEqual(response.status_code, 403)
                mtx.assert_not_called()
        self.assertEqual(self.client.get('/api/expert').status_code, 403)
        self.assertEqual(self.client.get('/webrtc/2/publish/').status_code, 403)
        self.assertEqual(self.client.get('/api/webrtc/ice').status_code, 403)
        self.assertEqual(self.client.post('/api/webrtc/2/publish', data='v=0', headers={**self.headers,'Content-Type':'application/sdp'}).status_code, 403)

    def test_engine_keeps_health_history_for_active_sources(self):
        engine=app.Engine()
        own=(UID,self.user['prefix']+'source1')
        stale=(99999,'fixture/stale')
        engine.health={own:{'since':123},stale:{'since':124}}
        engine.ingest_samples={own:('fixture',1,2),stale:('fixture',1,2)}
        engine.prune_caches({UID})
        self.assertEqual(engine.health,{own:{'since':123}})
        self.assertEqual(engine.ingest_samples,{own:('fixture',1,2)})

    def test_mode_requires_csrf_boolean_and_explicit_session_opt_in(self):
        self.assertEqual(self.client.post('/api/expert-mode', json={'enabled':True}).status_code, 403)
        for body in ({'enabled':'false'}, {'enabled':1}, [], None):
            self.assertEqual(self.client.post('/api/expert-mode', json=body, headers=self.headers).status_code, 400)
        self.enable()
        other_session = app.app.test_client()
        with other_session.session_transaction() as session:
            session.update(uid=UID,version=1,csrf='second')
        self.assertFalse(other_session.get('/api/expert-mode').json['expert_mode'])
        self.client.post('/api/logout', headers=self.headers)
        self.client.get('/login')
        with self.client.session_transaction() as session:
            token = session['csrf']
        response = self.client.post('/login', data={'csrf':token,'username':'alice','password':'Fixture-Only-Password-12345'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.client.get('/api/expert-mode').json['expert_mode'])

    def test_theme_and_media_library_work_without_expert_mode(self):
        response = self.client.post('/api/preferences', json={'theme':'light'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/status').json['theme'], 'light')
        self.assertEqual(self.client.get('/api/native-recordings').status_code, 200)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertEqual(self.client.post('/api/preferences',json={'theme':'invalid'},headers=self.headers).status_code, 400)

    def test_technical_forms_are_in_expert_submenus_and_theme_stays_in_settings(self):
        class Views(HTMLParser):
            def __init__(self):
                super().__init__(); self.view = None; self.stack = []; self.forms = {}
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'section':
                    self.stack.append(self.view)
                    self.view = attrs.get('data-view', self.view)
                if tag == 'form' and 'id' in attrs:
                    self.forms[attrs['id']] = self.view
            def handle_endtag(self, tag):
                if tag == 'section' and self.stack:
                    self.view = self.stack.pop()
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        self.addCleanup(app.write,'UPDATE users SET admin=0 WHERE id=?',(UID,))
        page = Views();page.feed(self.client.get('/').get_data(as_text=True))
        for form, view in {'theme-form':'settings','expert-form':'expert','source-create':'expert-routing',
                           'native-form':'expert-recording','webrtc-server-form':'expert-protocols',
                           'renewal-form':'expert-renewal'}.items():
            self.assertEqual(page.forms[form], view, form)

    def test_disabled_webrtc_has_setup_page_without_enabling_server(self):
        self.enable()
        config = yaml.safe_load(app.CONFIG.read_text());config['webrtc'] = False
        app.CONFIG.write_text(yaml.safe_dump(config))
        with patch.object(app, 'mtx') as mtx:
            response = self.client.get('/webrtc/2/publish/')
            mtx.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Zur WebRTC-Einrichtung', response.get_data(as_text=True))
        self.assertIn('data-enabled="false"', response.get_data(as_text=True))
        self.assertFalse(yaml.safe_load(app.CONFIG.read_text())['webrtc'])

    def test_protocol_diagnostics_confirm_permissions_without_exposing_secrets(self):
        self.enable()
        runtime = {'webrtc':False,'srt':True,'srtAddress':':18890','authInternalUsers':[
            {'user':app.media_username(self.user),'pass':'<redacted>',
             'permissions':[{'action':'publish','path':self.user['prefix']+'source2'}]}]}
        with patch.object(app.READY,'is_set',return_value=True),patch.object(app,'mtx',return_value=runtime):
            response = self.client.get('/api/expert')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['srt']['auth_ready'])
        self.assertTrue(response.json['srt']['runtime_checked'])
        self.assertFalse(response.json['webrtc_runtime'])
        self.assertNotIn(app.decrypt(self.user['media_secret']),response.get_data(as_text=True))

    def test_source_selection_is_tenant_scoped_and_survives_disabling_mode(self):
        self.enable()
        other_mode=app.rows('SELECT source_mode FROM users WHERE id=?',(OTHER,))[0]['source_mode']
        self.assertEqual(self.client.post('/api/sources/mode',json={'mode':'source2','user_id':OTHER},headers=self.headers).status_code,400)
        self.client.post('/api/expert-mode',json={'enabled':False},headers=self.headers)
        self.assertEqual(self.client.get('/api/status').json['source_mode'],'auto')
        self.assertEqual(app.rows('SELECT source_mode FROM users WHERE id=?',(OTHER,))[0]['source_mode'],other_mode)

    def test_per_target_stop_and_start_preserve_other_forwards_and_selection(self):
        self.enable()
        for kind in ('twitch','youtube'):
            app.write('INSERT OR REPLACE INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',
                      (UID,kind,app.encrypt('rtmps://fixture.example/' + kind)))
        with patch.object(app,'mtx'), patch.object(app,'validate_output',side_effect=lambda value:value):
            app.READY.set()
            try:
                self.assertEqual(self.client.post('/api/outputs/twitch/start',json={},headers=self.headers).status_code,200)
                twitch = app.configured_forwards(self.user)[app.output_path(self.user,'twitch')]
                self.assertEqual(self.client.post('/api/outputs/youtube/start',json={},headers=self.headers).status_code,200)
                self.assertEqual(app.configured_forwards(self.user)[app.output_path(self.user,'twitch')],twitch)
                self.assertEqual(self.client.post('/api/outputs/youtube/stop',json={},headers=self.headers).status_code,200)
                self.assertEqual(app.configured_forwards(self.user)[app.output_path(self.user,'twitch')],twitch)
                self.assertTrue(all(d['selected'] for d in app.destinations(self.user) if d['kind'] in ('twitch','youtube')))
                self.assertTrue(yaml.safe_load(app.CONFIG.read_text())['paths'][app.paths(self.user)[2]]['alwaysAvailable'])
            finally:
                app.READY.clear()

    def test_failed_native_config_save_restores_runtime_and_file(self):
        before = app.CONFIG.read_text()
        path = app.paths(self.user)[0]
        with patch.object(app,'mtx') as mtx, patch.object(app,'atomic',side_effect=OSError('fixture')):
            with self.assertRaises(app.Error):
                app.FEATURES.apply_paths({path:{'record':True,'recordFormat':'mpegts'}})
        self.assertEqual(app.CONFIG.read_text(),before)
        self.assertEqual(mtx.call_args_list[-1].args[1],{'record':False,'recordFormat':'fmp4'})

    def test_native_low_space_monitor_stops_only_the_affected_users_recordings(self):
        config=yaml.safe_load(self.config)
        own=self.user['prefix']+'source1'
        other=app.rows('SELECT prefix FROM users WHERE id=?',(OTHER,))[0]['prefix']+'source1'
        config['paths'][own]['record']=True
        config['paths'][other]['record']=True
        app.CONFIG.write_text(yaml.safe_dump(config))
        app.FEATURES.last_disk_check.pop(UID,None)
        with patch.object(app.FEATURES,'native_root',BASE), patch('media_features.shutil.disk_usage',return_value=SimpleNamespace(free=100*1048576)), patch.object(app.FEATURES,'apply_paths') as apply:
            app.FEATURES.monitor_recordings(self.user)
            apply.assert_called_once_with({own:{'record':False}})

    def test_native_settings_survive_reconcile_and_cannot_write_arbitrary_paths(self):
        self.enable()
        root = BASE / 'native-fixtures'
        root.mkdir(exist_ok=True)
        with patch.object(app.FEATURES,'native_root',root), patch.object(app,'mtx'):
            body = {'source':'source2','enabled':True,'format':'fmp4','segment':'1m','retention':'1d','recordPath':'/etc/invalid'}
            self.assertEqual(self.client.post('/api/native-recording',json=body,headers=self.headers).status_code,200)
            app.reconcile()
            config = yaml.safe_load(app.CONFIG.read_text())
            own = config['paths'][self.user['prefix']+'source2']
            self.assertTrue(own['record'])
            self.assertTrue(own['recordPath'].startswith(str(root / 'alice' / '%path')))
            self.assertEqual(config['paths']['foreign'],yaml.safe_load(self.config)['paths']['foreign'])
            body['source']='../bobby/live'
            self.assertEqual(self.client.post('/api/native-recording',json=body,headers=self.headers).status_code,400)

    def test_native_downloads_do_not_cross_users_or_follow_symlinks(self):
        root = BASE / 'native-downloads'
        own = root / 'alice' / self.user['prefix'] / 'source1';own.mkdir(parents=True,exist_ok=True)
        other_user = app.rows('SELECT * FROM users WHERE id=?',(OTHER,))[0]
        other = root / 'bobby' / other_user['prefix'] / 'source1';other.mkdir(parents=True,exist_ok=True)
        (own/'own.mp4').write_bytes(b'own')
        (other/'foreign.mp4').write_bytes(b'foreign')
        link=own/'link.mp4'
        if not link.exists():link.symlink_to(other/'foreign.mp4')
        with patch.object(app.FEATURES,'native_root',root):
            response=self.client.get('/media/native/source1/own.mp4');self.assertEqual(response.data,b'own');response.close()
            self.assertEqual(self.client.get('/media/native/source1/foreign.mp4').status_code,404)
            self.assertEqual(self.client.get('/media/native/source1/link.mp4').status_code,404)
            self.assertEqual(len(self.client.get('/api/native-recordings').json['segments']),1)

    def test_viewer_rotation_revocation_and_read_only_access(self):
        self.enable()
        public = app.app.test_client()
        url=self.client.post('/api/viewer-link',json={'enabled':True},headers=self.headers).json['url']
        route=urllib.parse.urlsplit(url).path
        self.assertEqual(public.get(route).status_code,200)
        self.assertIn(public.post(route,json={}).status_code,(403,405))
        replacement=self.client.post('/api/viewer-link',json={'enabled':True},headers=self.headers).json['url']
        self.assertEqual(public.get(route).status_code,404)
        route=urllib.parse.urlsplit(replacement).path
        self.assertEqual(public.get(route).status_code,200)
        self.client.post('/api/viewer-link',json={'enabled':False},headers=self.headers)
        self.assertEqual(public.get(route+'index.m3u8').status_code,404)
        self.assertEqual(public.get(route).status_code,404)

    def test_global_webrtc_configuration_requires_admin_and_expert(self):
        self.enable()
        self.assertEqual(self.client.post('/api/admin/webrtc',json={'enabled':True},headers=self.headers).status_code,403)
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        self.addCleanup(app.write,'UPDATE users SET admin=0 WHERE id=?',(UID,))
        with patch.object(app,'mtx') as mtx:
            self.assertEqual(self.client.post('/api/admin/webrtc',json={'enabled':True,'hosts':['ingest.example.com']},headers=self.headers).status_code,200)
            self.assertEqual(mtx.call_args.args[1],{'webrtc':True,'webrtcAdditionalHosts':['ingest.example.com']})
            self.assertEqual(self.client.post('/api/admin/webrtc',json={'enabled':True,'hosts':['https://invalid/path']},headers=self.headers).status_code,400)

    def test_webrtc_session_cleanup_is_bound_to_owner_and_survives_mode_off(self):
        self.enable()
        upstream=io.BytesIO(b'v=0\r\n')
        upstream.headers=Message()
        upstream.headers['Location']='/'+self.user['prefix']+'source2/whip/12345678-1234-1234-1234-123456789abc'
        with patch.object(app.FEATURES,'rtc_base',return_value='http://127.0.0.1:8889/'), patch('media_features.urllib.request.urlopen',return_value=upstream) as fetch:
            response=self.client.post('/api/webrtc/2/publish',data='v=0\r\n',headers={**self.headers,'Content-Type':'application/sdp'})
        self.assertEqual(response.status_code,201)
        self.assertIn('Basic ',fetch.call_args.args[0].get_header('Authorization'))
        self.assertNotIn(app.decrypt(self.user['media_secret']),response.get_data(as_text=True))
        location=response.headers['Location']
        other=app.app.test_client()
        with other.session_transaction() as session:session.update(uid=OTHER,version=1,csrf='other')
        self.assertEqual(other.delete(location,headers={'X-CSRF-Token':'other'}).status_code,404)
        self.client.post('/api/expert-mode',json={'enabled':False},headers=self.headers)
        with patch.object(app.FEATURES,'close_rtc') as close:
            self.assertEqual(self.client.delete(location,headers=self.headers).status_code,204)
            close.assert_called_once()
        self.assertEqual(self.client.delete(location,headers=self.headers).status_code,404)


if __name__ == '__main__':
    unittest.main()


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID, version=1, csrf='expansion', expert_mode=True)
        self.headers = {'X-CSRF-Token':'expansion'}
        self.user = app.rows('SELECT * FROM users WHERE id=?',(UID,))[0]
        self.config = app.CONFIG.read_text()
        self.outputs = app.rows('SELECT * FROM outputs WHERE user_id=?',(UID,))
        self.routing_tables={table:app.rows('SELECT * FROM '+table+' WHERE user_id=?',(UID,)) for table in ('routing_sources','output_routing','routing_programs')}
        for table in self.routing_tables:app.write('DELETE FROM '+table+' WHERE user_id=?',(UID,))
        self.addCleanup(self.restore)
        app.write('DELETE FROM outputs WHERE user_id=?',(UID,))
        app.write("UPDATE users SET admin=0,pull_url='',pull_enabled=0,source_mode='auto',renew_resume=0 WHERE id=?",(UID,))

    def restore(self):
        with app.db() as connection:
            for table,rows in self.routing_tables.items():
                connection.execute('DELETE FROM '+table+' WHERE user_id=?',(UID,))
                for row in rows:connection.execute('INSERT INTO '+table+'('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',tuple(row.values()))
        app.CONFIG.write_text(self.config)
        app.write('DELETE FROM outputs WHERE user_id=?',(UID,))
        for row in self.outputs:
            app.write('INSERT INTO outputs(user_id,kind,endpoint,selected,label) VALUES (?,?,?,?,?)',
                      tuple(row[k] for k in ('user_id','kind','endpoint','selected','label')))
        app.write('UPDATE users SET admin=?,pull_url=?,pull_enabled=?,source_mode=?,renew_resume=?,source3_protocol=? WHERE id=?',
                  tuple(self.user[k] for k in ('admin','pull_url','pull_enabled','source_mode','renew_resume','source3_protocol'))+(UID,))

    def post(self,path,body):
        return self.client.post(path,json=body,headers=self.headers)

    def custom(self,label='Studio'):
        with patch.object(app,'validate_output',side_effect=lambda value:value):
            response=self.post('/api/custom-outputs',{'label':label,'url':'rtsp://public.example/'+label})
        self.assertEqual(response.status_code,200,response.json)
        kind=response.json['kind']
        app.MODEL.save_route(self.user,kind,['source1','source2'])
        app.reconcile()
        return kind

    def source(self,protocol='srt',url='',label='Camera'):
        response=self.post('/api/routing/sources',{'label':label,'protocol':protocol,'url':url})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['key']

    def test_all_new_controls_require_expert_and_csrf(self):
        with self.client.session_transaction() as session:
            session['expert_mode']=False
        for path,body in [('/api/routing/sources',{'label':'Camera','protocol':'srt'}),('/api/routing/outputs',{'platform':'twitch','label':'Twin','key':'fixture-key-123456'}),
                          ('/api/custom-outputs',{'label':'Studio','url':'rtsp://example.org/live'}),
                          ('/api/admin/playback',{'enabled':True})]:
            self.assertEqual(self.post(path,body).status_code,403)
        for path in ('/api/routing','/api/playback/status','/api/playback/live/spans',
                     '/api/playback/live/media?start=2026-01-01T00:00:00Z&duration=5'):
            self.assertEqual(self.client.get(path).status_code,403)
        with self.client.session_transaction() as session:
            session['expert_mode']=True
        self.assertEqual(self.client.post('/api/routing/sources',json={'label':'Camera','protocol':'srt'}).status_code,403)

    def test_public_pull_validation_and_encrypted_storage(self):
        for url in ('rtsp://127.0.0.1/live','rtsp://10.1.2.3/live','rtsp://169.254.169.254/latest','http://example.org/live','rtsp://[broken','rtsp://example.org/x#fragment'):
            response=self.post('/api/routing/sources',{'label':'Camera','protocol':'rtsp','url':url})
            self.assertEqual(response.status_code,400,url)
        url='rtsps://camera:fixture-password@camera.example/live?token=fixture-token'
        with patch.object(app,'resolve_host_ips',return_value={'8.8.8.8'}),patch.object(app,'ingest_ips',return_value={'127.0.0.1'}):
            key=self.source('rtsp',url)
        row=app.rows('SELECT * FROM routing_sources WHERE user_id=? AND key=?',(UID,key))[0]
        self.assertNotIn('fixture-password',row['endpoint']);self.assertEqual(app.decrypt(row['endpoint']),url)
        self.assertEqual(yaml.safe_load(app.CONFIG.read_text())['paths'][self.user['prefix']+key]['source'],url)
        display=self.client.get('/api/routing').get_data(as_text=True)
        self.assertNotIn('fixture-password',display);self.assertNotIn('fixture-token',display)
        # Disabling an already configured pull should not need DNS/network access again.
        with patch.object(app,'validate_output',side_effect=lambda value:value):
            self.assertEqual(self.post('/api/routing/sources/'+key,{'enabled':False}).status_code,200)
        self.assertFalse(app.MODEL.source(self.user,key)['enabled'])

    def test_source3_ingest_and_preview_compatibility(self):
        self.assertEqual([row['key'] for row in app.MODEL.sources(self.user)],['source1','source2'])
        self.assertEqual(self.client.get('/preview/4/').status_code,404)
        key=self.source('rtmp')
        self.assertEqual(key,'source3')
        data=self.client.get('/api/ingest/'+key).json
        self.assertEqual(data['protocol'],'rtmp');self.assertIn(self.user['prefix']+key,data['rtmp'])
        self.assertIn(self.user['prefix']+key,data['stream_id'])
        self.assertEqual(app.preview_path(self.user,3),self.user['prefix']+'live')
        self.assertEqual(app.preview_path(self.user,4),self.user['prefix']+key)
        self.assertEqual(self.client.get('/preview/source/'+key+'/').status_code,200)
        self.assertEqual(self.post('/api/sources/mode',{'mode':'source3'}).status_code,400)

    def test_reconcile_preserves_foreign_paths_auth_and_native_settings(self):
        self.source()
        config=yaml.safe_load(app.CONFIG.read_text())
        foreign={'user':'foreign-camera','pass':'fixture','ips':[],'permissions':[{'action':'publish','path':'external-camera'}]}
        config['authInternalUsers'].append(foreign)
        config['paths'][self.user['prefix']+'source3']={'record':True,'recordFormat':'mpegts'}
        app.CONFIG.write_text(yaml.safe_dump(config))
        app.reconcile();first=app.CONFIG.read_text();app.reconcile()
        self.assertEqual(app.CONFIG.read_text(),first)
        current=yaml.safe_load(first)
        self.assertEqual(current['paths']['foreign'],config['paths']['foreign'])
        self.assertIn(foreign,current['authInternalUsers'])
        self.assertTrue(current['paths'][self.user['prefix']+'source3']['record'])
        auth=next(row for row in current['authInternalUsers'] if row['user']==app.media_username(self.user))
        self.assertIn({'action':'playback','path':self.user['prefix']+'source3'},auth['permissions'])
        self.assertNotIn({'action':'publish','path':self.user['prefix']+'pull'},auth['permissions'])
        self.assertFalse(any(p.get('path','').startswith('unittest/bobby/') for p in auth['permissions']))

    def test_three_customs_start_stop_without_affecting_fixed_slots(self):
        for kind in ('twitch','youtube'):
            app.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',
                      (UID,kind,app.encrypt('rtsp://public.example/'+kind)))
        kinds=[self.custom(label) for label in ('Studio','Backup','Archive')]
        app.reconcile()
        with patch.object(app,'mtx'),patch.object(app,'validate_output',side_effect=lambda value:value):
            user=app.rows('SELECT * FROM users WHERE id=?',(UID,))[0]
            app.forward(user,True)
            for kind in kinds:
                app.forward(user,True,kind=kind)
            before=app.configured_forwards(user)
            app.forward(user,False,kind=kinds[1])
            after=app.configured_forwards(user)
        for kind in ('twitch','youtube',kinds[0],kinds[2]):
            self.assertEqual(after[app.output_path(user,kind)],before[app.output_path(user,kind)])
            self.assertTrue(after[app.output_path(user,kind)])
        self.assertEqual(after[app.output_path(user,kinds[1])],[])
        self.assertEqual({r['kind'] for r in app.destinations(user) if r['selected']},{'twitch','youtube'})
        with patch.object(app,'validate_output',side_effect=lambda value:value):
            self.assertEqual(self.post('/api/custom-outputs/'+kinds[0],{'label':'Changed','url':'rtsp://public.example/new'}).status_code,409)
        self.assertEqual(self.post('/api/custom-outputs/'+kinds[0]+'/delete',{}).status_code,409)
        with patch.object(app,'mtx'):
            self.assertEqual(self.post('/api/custom-outputs/'+kinds[1]+'/delete',{}).status_code,200)
        self.assertNotIn(app.output_path(user,kinds[1]),yaml.safe_load(app.CONFIG.read_text())['paths'])

    def test_custom_limit_duplicates_and_tenant_ownership(self):
        for i in range(7):
            kind=self.custom('Studio'+str(i))
        with patch.object(app,'validate_output',side_effect=lambda value:value):
            self.assertEqual(self.post('/api/custom-outputs',{'label':'Sixth','url':'rtsp://public.example/six'}).status_code,400)
            self.assertEqual(self.post('/api/output',{'kind':'custom','url':'rtsp://public.example/legacy'}).status_code,200)
        with self.client.session_transaction() as session:
            session['uid']=OTHER
        self.assertEqual(self.post('/api/custom-outputs/'+kind,{'label':'Foreign'}).status_code,404)
        self.assertEqual(self.post('/api/custom-outputs/'+kind+'/delete',{}).status_code,404)
        self.assertEqual(self.post('/api/outputs/'+kind+'/stop',{}).status_code,404)

    def test_legacy_database_migration_preserves_secrets_selection_and_labels(self):
        endpoint=app.encrypt('rtsp://public.example/old')
        app.write('INSERT INTO outputs(user_id,kind,endpoint,selected,label) VALUES (?,?,?,1,?)',(UID,'custom',endpoint,'Archive'))
        app.initialize();app.initialize()
        row=app.rows('SELECT * FROM outputs WHERE user_id=? AND kind=?',(UID,'custom'))[0]
        self.assertEqual((row['endpoint'],row['selected'],row['label']),(endpoint,1,'Archive'))
        # Exercise the actual pre-label schema, then the repeatable migration.
        with app.db() as connection:
            connection.execute('ALTER TABLE outputs DROP COLUMN label')
        app.initialize()
        row=app.rows('SELECT * FROM outputs WHERE user_id=? AND kind=?',(UID,'custom'))[0]
        self.assertEqual((row['endpoint'],row['selected'],row['label']),(endpoint,1,''))

    def test_playback_admin_listener_and_rollback(self):
        self.assertEqual(self.post('/api/admin/playback',{'enabled':True}).status_code,403)
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        for address in (':9996','0.0.0.0:9996','remote.example:9996','http://127.0.0.1:9996','127.0.0.1:0','127.0.0.1:9996/path'):
            self.assertEqual(self.post('/api/admin/playback',{'enabled':True,'address':address}).status_code,400)
        with patch.object(app,'mtx') as mtx:
            self.assertEqual(self.post('/api/admin/playback',{'enabled':True,'address':'127.0.0.1:19996'}).status_code,200)
            mtx.assert_called_once_with('config/global/patch',{'playback':True,'playbackAddress':'127.0.0.1:19996'})
        before=app.CONFIG.read_text()
        with patch.object(app,'mtx') as mtx,patch.object(app,'atomic',side_effect=OSError('fixture')):
            self.assertEqual(self.post('/api/admin/playback',{'enabled':False}).status_code,400)
            self.assertEqual(mtx.call_args.args[1],{'playback':True})
        self.assertEqual(app.CONFIG.read_text(),before)

    def test_playback_proxy_uses_own_path_credentials_and_sanitizes_urls(self):
        self.source()
        config=yaml.safe_load(app.CONFIG.read_text());config['playback']=True;app.CONFIG.write_text(yaml.safe_dump(config))
        body=b'[{"start":"2026-10-26T09:00:00Z","duration":30,"url":"http://private.invalid/get?secret=bad"}]'
        class Upstream(io.BytesIO):
            headers=Message()
        with patch('playback_features.urllib.request.urlopen',return_value=Upstream(body)) as upstream:
            response=self.client.get('/api/playback/source3/spans?path=unittest/bobby/live')
            self.assertEqual(response.status_code,200,response.json)
            req=upstream.call_args.args[0]
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)['path'],[self.user['prefix']+'source3'])
            self.assertEqual(req.get_header('Authorization'),app.FEATURES.media_headers(self.user)['Authorization'])
            self.assertNotIn('private.invalid',response.get_data(as_text=True))
            url=response.json['spans'][0]['url']
        with patch('playback_features.urllib.request.urlopen',return_value=Upstream(b'fixture-media')):
            response=self.client.get(url)
            self.assertEqual(response.data,b'fixture-media')
            self.assertEqual(response.headers['Accept-Ranges'],'none')
        for source in ('../bobby/live','bobby','source99'):
            self.assertEqual(self.client.get('/api/playback/'+source+'/spans').status_code,404)
        public=app.app.test_client()
        self.assertEqual(public.get(url).status_code,401)
        for duration in ('nan','inf','-1','3601','oops'):
            self.assertEqual(self.client.get('/api/playback/live/media?start=2026-10-26T09:00:00Z&duration='+duration).status_code,400)
        self.assertEqual(self.client.get('/api/playback/live/media?start=2026-10-26&duration=1').status_code,400)

    def test_mpegts_fallback_only_scans_owned_regular_files(self):
        root=BASE/'expansion-native';root.mkdir(exist_ok=True)
        with patch.object(app.FEATURES,'native_root',root):
            folder=app.FEATURES.recording_directory(self.user,'live',create=True)
            good=folder/'2026-10-26_09-00-00-000000_+0000.ts';good.write_bytes(b'fixture')
            symlink=folder/'2026-10-26_09-01-00-000000_+0000.ts';symlink.symlink_to(good)
            with patch.object(app.FEATURES.playback,'duration',return_value=10):
                found=app.FEATURES.playback.ts_segments(self.user,'live')
            self.assertEqual([row[2] for row in found],[good])
            symlink.unlink();good.unlink()

    def test_program_stays_available_across_forwarding_and_reconcile(self):
        app.reconcile()
        live=self.user['prefix']+'live'
        config=yaml.safe_load(app.CONFIG.read_text())
        self.assertTrue(config['paths'][live]['alwaysAvailable'])
        self.assertTrue(config['paths'][live]['alwaysAvailableRecorded'])
        config['paths'][live]['record']=True
        app.CONFIG.write_text(yaml.safe_dump(config))
        with patch.object(app,'mtx'):
            app.forward(self.user,False)
        app.reconcile()
        settings=yaml.safe_load(app.CONFIG.read_text())['paths'][live]
        self.assertTrue(settings['alwaysAvailable'])
        self.assertTrue(settings['record'])
        self.assertTrue(settings['alwaysAvailableRecorded'])
        self.addCleanup(app.write,'UPDATE users SET active=? WHERE id=?',(self.user['active'],UID))
        app.write('UPDATE users SET active=0 WHERE id=?',(UID,));app.reconcile()
        config=yaml.safe_load(app.CONFIG.read_text())
        self.assertFalse(config['paths'][live]['alwaysAvailable'])
        self.assertFalse(config['paths'][self.user['prefix']+'webrtc-program']['alwaysAvailable'])

    def test_program_hls_proxy_uses_personal_credentials(self):
        class Upstream(io.BytesIO):
            headers=Message()
        with patch('app.urllib.request.urlopen',return_value=Upstream(b'#EXTM3U\n')) as upstream:
            response=self.client.get('/preview/3/index.m3u8?session=fixture')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data,b'#EXTM3U\n')
            req=upstream.call_args.args[0]
            self.assertEqual(req.full_url,app.HLS+self.user['prefix']+'live/index.m3u8?session=fixture')
            self.assertEqual(req.get_header('Authorization'),app.FEATURES.media_headers(self.user)['Authorization'])

    def test_program_webrtc_bridge_is_reused_and_idle_cleanup_is_tenant_scoped(self):
        from unittest.mock import Mock
        from program_preview import ProgramPreview
        manager=ProgramPreview(app)
        first,second=Mock(),Mock()
        first.poll.return_value=second.poll.return_value=None
        other=app.rows('SELECT * FROM users WHERE id=?',(OTHER,))[0]
        with patch('program_preview.subprocess.Popen',side_effect=[first,second]) as spawn:
            job=manager.start(self.user)
            self.assertIs(manager.start(self.user),job)
            self.assertEqual(spawn.call_count,1)
            manager.start(other)
            job['used']=app.time.monotonic()-21
            manager.monitor([self.user,other],{manager.path(other):{'readers':[{'type':'webRTCSession'}]}})
            self.assertNotIn(UID,manager.jobs)
            self.assertIn(OTHER,manager.jobs)
            first.terminate.assert_called_once()
            second.terminate.assert_not_called()
            manager.close()
            second.terminate.assert_called_once()

    def test_program_webrtc_offer_uses_only_owned_browser_compatible_path(self):
        config=yaml.safe_load(app.CONFIG.read_text());config['webrtc']=True;app.CONFIG.write_text(yaml.safe_dump(config))
        path=self.user['prefix']+'webrtc-program'
        class Upstream(io.BytesIO):
            headers=Message()
        upstream=Upstream(b'v=0\r\n')
        upstream.headers['Location']='/'+path+'/whep/12345678-1234-1234-1234-123456789abc'
        with patch.object(app.FEATURES.program_preview,'ensure',return_value=path) as ensure,patch('media_features.urllib.request.urlopen',return_value=upstream) as urlopen:
            response=self.client.post('/api/webrtc/3/play',data='v=0\r\n',headers={**self.headers,'Content-Type':'application/sdp'})
            self.assertEqual(response.status_code,201,response.json)
            self.assertEqual(ensure.call_args.args[0]['id'],UID)
            self.assertIn('/'+path+'/whep',urlopen.call_args.args[0].full_url)
        with self.client.session_transaction() as session:
            session['expert_mode']=False
        with patch.object(app.FEATURES.program_preview,'ensure') as ensure:
            self.assertEqual(self.client.post('/api/webrtc/3/play',data='v=0',headers={**self.headers,'Content-Type':'application/sdp'}).status_code,403)
            ensure.assert_not_called()

    def test_fixed_defaults_and_expert_creation_and_priority_guards(self):
        self.assertEqual([row['key'] for row in self.client.get('/api/status').json['sources']],['source1','source2'])
        self.assertEqual(app.output_kinds(self.user),('twitch','youtube','custom'))
        for key in ('source1','source2'):
            self.assertEqual(self.post('/api/routing/sources/'+key,{'label':'Changed','priority':5}).status_code,403)
            self.assertEqual(self.post('/api/routing/sources/'+key+'/delete',{}).status_code,403)
        source=self.source()
        self.assertEqual(self.post('/api/routing/sources/'+source,{'priority':1}).status_code,400)
        self.assertEqual(self.post('/api/routing/sources/'+source,{'priority':3}).status_code,200)
        with self.client.session_transaction() as session:session['expert_mode']=False
        for path,body in [('/api/routing/sources',{'label':'More','protocol':'srt'}),('/api/routing/outputs',{'platform':'twitch','label':'More','key':'fixture-key-123456'}),('/api/routing/sources/source1/targets',{'targets':[]})]:
            self.assertEqual(self.post(path,body).status_code,403)

    def test_per_output_routing_and_multiple_platform_accounts(self):
        from unittest.mock import Mock
        keys=[self.source(label='Camera'+str(i)) for i in (3,4,5)]
        for kind in ('twitch','youtube','custom'):
            app.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(UID,kind,app.encrypt('rtsp://public.example/'+kind)))
        extra={}
        for platform,label in [('twitch','TwitchTwo'),('youtube','YouTubeTwo'),('custom','ProviderB')]:
            body={'platform':platform,'label':label,'key':'fixture-key-'+label,'url':'rtsp://public.example/'+label}
            with patch.object(app,'validate_output',side_effect=lambda value:value):response=self.post('/api/routing/outputs',body)
            self.assertEqual(response.status_code,200,response.json);extra[platform]=response.json['kind']
        routes={'twitch':['source1','source2'],'youtube':['source1','source2'],'custom':['source1','source2',keys[2]],extra['twitch']:[keys[0]],extra['custom']:keys[:2],extra['youtube']:[keys[2]]}
        for kind,sources in routes.items():self.assertEqual(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':sources}).status_code,200)
        for kind,sources in routes.items():self.assertEqual(app.MODEL.output_program(self.user,kind)['sources'],sources)
        self.assertEqual(app.MODEL.output_program(self.user,'twitch')['id'],'main')
        config=yaml.safe_load(app.CONFIG.read_text());programs=app.MODEL.programs(self.user)
        self.addCleanup(app.READY.clear)
        engine=app.Engine();counter=[0];offline=set()
        def runtime(path,value=None,method=None):
            if path.startswith('paths/list'):
                items=[{'name':self.user['prefix']+source,'online':source not in offline,'onlineTime':'fixture','source':{'id':source},'inboundBytes':counter[0],'tracks':['H264','MPEG4Audio']} for source in ['source1','source2',*keys]]
                items += [{'name':group['path'],'available':True,'online':True,'readers':[{'type':'hlsMuxer'}]} for group in programs]
                return {'items':items}
            return {}
        def step(now):
            counter[0]+=1000
            with patch.object(app,'mtx',side_effect=runtime),patch.object(app.time,'monotonic',return_value=now),patch('app.subprocess.Popen') as spawn:
                spawn.return_value.poll.return_value=None;engine.tick()
        def selected(kind):
            pid=app.MODEL.output_program(self.user,kind)['id'];return next(row['selected_source'] for row in engine.snapshot[UID]['programs'] if row['id']==pid)
        step(100);step(104);step(108)
        self.assertEqual(selected('custom'),'source1');self.assertEqual(selected(extra['custom']),keys[0]);self.assertEqual(selected(extra['twitch']),keys[0]);self.assertEqual(selected(extra['youtube']),keys[2])
        offline.update(['source1','source2']);step(112)
        self.assertEqual(selected('custom'),keys[2]);self.assertEqual(selected(extra['custom']),keys[0])
        self.assertEqual(self.post('/api/routing/sources/'+keys[0],{'priority':9}).status_code,200)
        step(116)
        self.assertEqual(selected(extra['custom']),keys[1]);self.assertEqual(selected(extra['twitch']),keys[0])
        self.assertEqual(app.MODEL.output_program(self.user,extra['custom'])['id'],next(row['id'] for row in programs if row['sources']==keys[:2]))
        with patch.object(app,'mtx'):
            for key in list(engine.relays):engine.stop_relay(key)
        data=self.client.get('/api/status').json
        self.assertNotIn('fixture-key-',str(data))

    def test_source_target_isolation_and_no_unassigned_start(self):
        source=self.source()
        kind=self.custom()
        self.assertEqual(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':[source]}).status_code,200)
        pid=app.MODEL.output_program(self.user,kind)['id']
        for sources in ([{}],['source1','source1'],['foreign']):
            self.assertIn(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':sources}).status_code,(400,404))
        self.assertEqual(self.post('/api/routing/sources/'+source+'/delete',{}).status_code,409)
        self.assertEqual(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':[]}).status_code,200)
        with patch.object(app,'mtx'),patch.object(app,'validate_output',side_effect=lambda value:value),patch.object(app.READY,'is_set',return_value=True):
            self.assertEqual(self.post('/api/outputs/'+kind+'/start',{}).status_code,400)
        self.assertEqual(self.post('/api/routing/sources/'+source+'/delete',{}).status_code,200)
        self.assertEqual(self.client.get('/api/ingest/'+source).status_code,404)
        replacement=self.source();self.assertNotEqual(source,replacement)
        with self.client.session_transaction() as session:session['uid']=OTHER
        self.assertEqual(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':['source1']}).status_code,404)
        self.assertEqual(self.client.get('/program/'+pid+'/').status_code,404)

    def test_legacy_explicit_sources_and_routes_are_migrated_once(self):
        app.write("UPDATE users SET pull_url=?,pull_enabled=1,source_mode='source3' WHERE id=?",(app.encrypt('rtsp://camera.example/live'),UID))
        config=yaml.safe_load(app.CONFIG.read_text());config['paths'][self.user['prefix']+'source3']={'source':'publisher','record':True}
        config['paths'][self.user['prefix']+'live']['record']=True
        app.CONFIG.write_text(yaml.safe_dump(config));app.write("DELETE FROM settings WHERE name='routing_model_v1'")
        app.initialize();app.initialize()
        self.assertEqual([row['key'] for row in app.MODEL.sources(self.user)],['source1','source2','source3','pull'])
        self.assertEqual(app.MODEL.route(self.user,'twitch'),['source1','source2','source3','pull'])
        self.assertEqual(app.decrypt(app.MODEL.source(self.user,'pull')['endpoint']),'rtsp://camera.example/live')
        migrated=yaml.safe_load(app.CONFIG.read_text());program=app.MODEL.output_program(self.user,'twitch')
        self.assertTrue(migrated['paths'][program['path']]['record'])
        self.assertFalse(migrated['paths'][self.user['prefix']+'live']['record'])

    def test_own_password_change_for_normal_user_and_admin_keeps_current_session(self):
        self.addCleanup(app.write,'UPDATE users SET password=?,version=? WHERE id=?',(self.user['password'],self.user['version'],UID))
        for admin in (0,1):
            current='Known-Fixture-Password-123';changed='Changed-Fixture-Password-456'
            app.write('UPDATE users SET admin=?,password=?,version=1 WHERE id=?',(admin,app.generate_password_hash(current),UID))
            with self.client.session_transaction() as session:session['version']=1
            other=app.app.test_client()
            with other.session_transaction() as session:session.update(uid=UID,version=1,csrf='other')
            self.assertEqual(self.post('/api/password',{'current':'wrong','password':changed}).status_code,400)
            self.assertEqual(self.post('/api/password',{'current':current,'password':changed}).status_code,200)
            self.assertEqual(self.client.get('/api/status').status_code,200)
            self.assertEqual(other.get('/api/status').status_code,401)
            self.assertTrue(app.check_password_hash(app.rows('SELECT password FROM users WHERE id=?',(UID,))[0]['password'],changed))
            html=self.client.get('/').get_data(as_text=True)
            self.assertIn('href="#account"',html);self.assertIn('data-view="account"',html)

    def test_admin_delete_requires_inactive_confirmation_and_never_reuses_id(self):
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        with patch.object(app.threading,'Thread'):target=app.add_user('retireduser','Retired-Fixture-Password-123')
        try:
            self.assertEqual(self.post('/api/admin/users/'+str(UID)+'/delete',{'confirm':'alice'}).status_code,403)
            self.assertEqual(self.post('/api/admin/users/'+str(target)+'/delete',{'confirm':'retireduser'}).status_code,409)
            with patch.object(app,'mtx'):self.assertEqual(self.post('/api/admin/users/'+str(target)+'/toggle',{}).status_code,200)
            self.assertEqual(self.post('/api/admin/users/'+str(target)+'/delete',{'confirm':'wrong'}).status_code,400)
            app.write("UPDATE users SET upload_state='processing' WHERE id=?",(target,))
            self.assertEqual(self.post('/api/admin/users/'+str(target)+'/delete',{'confirm':'retireduser'}).status_code,409)
            app.write("UPDATE users SET upload_state='' WHERE id=?",(target,))
            with patch.object(app,'mtx',return_value={}):
                response=self.post('/api/admin/users/'+str(target)+'/delete',{'confirm':'retireduser'})
            self.assertEqual(response.status_code,200,response.json)
            self.assertFalse(app.rows('SELECT * FROM users WHERE id=?',(target,)))
            self.assertFalse(any(name.startswith('unittest/retireduser/') for name in yaml.safe_load(app.CONFIG.read_text())['paths']))
            self.assertTrue(list((app.DATA/'deleted-users').glob(str(target)+'-*/manifest.json')))
            with patch.object(app.threading,'Thread'):replacement=app.add_user('retireduser','New-Fixture-Password-456')
            self.assertGreater(replacement,target)
        finally:
            remaining=app.rows("SELECT id FROM users WHERE username='retireduser'")
            for row in remaining:
                for table in ('videos','recordings','outputs','routing_sources','output_routing','routing_programs'):
                    app.write('DELETE FROM '+table+' WHERE user_id=?',(row['id'],))
                app.write('DELETE FROM users WHERE id=?',(row['id'],))

    def test_clearing_credentials_preserves_expert_output_definitions_and_routes(self):
        source=self.source();kind=self.custom()
        self.assertEqual(self.post('/api/routing/outputs/'+kind+'/sources',{'sources':[source]}).status_code,200)
        with self.client.session_transaction() as session:session['expert_mode']=False
        with patch.object(app,'mtx'):
            self.assertEqual(self.post('/api/disconnect',{}).status_code,200)
        self.assertIn(kind,app.output_kinds(self.user))
        self.assertEqual(app.MODEL.route(self.user,kind),[source])
        self.assertFalse(app.destinations(self.user,True))
        self.assertEqual(self.post('/api/outputs/'+kind+'/delete',{}).status_code,400)
        with self.client.session_transaction() as session:session['expert_mode']=True
        with patch.object(app,'validate_output',side_effect=lambda value:value):
            self.assertEqual(self.post('/api/routing/outputs/'+kind,{'label':'Restored','url':'rtsp://public.example/restored'}).status_code,200)
        self.assertEqual(app.MODEL.route(self.user,kind),[source])

    def test_migration_does_not_drop_legacy_source_during_media_api_outage(self):
        config=yaml.safe_load(app.CONFIG.read_text());config['paths'][self.user['prefix']+'source3']={'source':'publisher','record':False}
        app.CONFIG.write_text(yaml.safe_dump(config));app.write("DELETE FROM settings WHERE name='routing_model_v1'")
        with patch.dict(os.environ,{'STREAMDESK_ENGINE':'1'}),patch.object(app,'mtx',side_effect=app.Error('temporarily offline')):
            app.initialize()
        self.assertIn('source3',[row['key'] for row in app.MODEL.sources(self.user)])
