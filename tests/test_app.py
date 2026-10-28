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
COOKIE_CLOCK = patch('itsdangerous.TimestampSigner.get_timestamp', return_value=int(app.time.time()))
# Session assertions must not depend on wall-clock corrections on the test host.
COOKIE_CLOCK.start()
app.app.config['TESTING'] = True
with patch.object(app.threading, 'Thread'):
    UID = app.add_user('alice', 'Fixture-Only-Password-12345')
    OTHER = app.add_user('bobby', 'Fixture-Only-Password-98765')


def tearDownModule():
    COOKIE_CLOCK.stop()
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
        for form, view in {'theme-form':'settings-appearance','expert-form':'expert','source-create':'expert-routing',
                           'targets-form':'settings','twitch-output-form':'settings-twitch','youtube-output-form':'settings-youtube',
                           'output-form':'settings-custom','discord-form':'expert-discord',
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

    def test_protocol_encryption_bandwidth_and_tenant_metrics(self):
        self.enable()
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        self.addCleanup(app.write,'UPDATE users SET admin=0 WHERE id=?',(UID,))
        config=yaml.safe_load(app.CONFIG.read_text())
        config.update(rtmpServerCert='/tmp/cert',rtmpServerKey='/tmp/key',rtspServerCert='/tmp/cert',rtspServerKey='/tmp/key')
        app.CONFIG.write_text(yaml.safe_dump(config))
        with patch.object(app,'mtx'):
            response=self.client.post('/api/admin/protocol-encryption',json={'rtmp':'optional','rtsp':'optional'},headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(self.client.post('/api/admin/protocol-encryption',json={'rtmp':'optional','rtsp':'strict'},headers=self.headers).status_code,409)
        response=self.client.post('/api/admin/bandwidth',json={'limit_mbps':12.5},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(float(app.setting('bandwidth_limit_mbps')),12.5)

        class Metrics:
            def __enter__(self): return self
            def __exit__(self,*_): pass
            def read(self,_): return (b'paths_readers{name="unittest/alice/live"} 3\n'
                                      b'paths_readers{name="unittest/bobby/live"} 99\n'
                                      b'paths_errors_total{name="unittest/alice/live"} 2\n')
        app.PROMETHEUS_CACHE.clear()
        with patch('app.urllib.request.urlopen',return_value=Metrics()):
            values=app.prometheus_metrics(self.user)
        self.assertEqual(values,{'readers':3,'errors':2,'available':True})

    def test_external_auth_strategy_is_admin_only_and_rolls_back(self):
        self.enable()
        self.assertEqual(self.client.post('/api/admin/auth-strategy',json={'method':'http','address':'https://id.example/auth'},headers=self.headers).status_code,403)
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        self.addCleanup(app.write,'UPDATE users SET admin=0 WHERE id=?',(UID,))
        before = app.CONFIG.read_text()
        with patch.object(app,'mtx',return_value={}) as change:
            response=self.client.post('/api/admin/auth-strategy',json={'method':'jwt','address':'https://id.example/jwks','claim_key':'permissions'},headers=self.headers)
        self.assertEqual(response.status_code,409)
        change.assert_not_called()
        self.assertEqual(app.CONFIG.read_text(),before)
        with patch.object(app,'mtx',side_effect=[{},app.Error('fixture'),{}]):
            response=self.client.post('/api/admin/auth-strategy',json={'method':'internal'},headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertEqual(yaml.safe_load(app.CONFIG.read_text())['authMethod'],'internal')

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
        self.routing_tables={table:app.rows('SELECT * FROM '+table+' WHERE user_id=?',(UID,)) for table in ('routing_sources','output_routing','routing_programs','routing_policy')}
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

    def test_webrtc_mpegts_and_rtp_sources_are_scoped_and_validated(self):
        with patch.object(app,'reconcile'):
            webrtc=self.post('/api/routing/sources',{'label':'Browser','protocol':'webrtc'})
            self.assertEqual(webrtc.status_code,200)
            bad=self.post('/api/routing/sources',{'label':'Unsicher','protocol':'mpegts','url':'udp+mpegts://0.0.0.0:12000'})
            self.assertEqual(bad.status_code,400)
            mpegts=self.post('/api/routing/sources',{'label':'Transport','protocol':'mpegts','url':'udp+mpegts://0.0.0.0:12000?source=93.184.216.34'})
            self.assertEqual(mpegts.status_code,200,mpegts.json)
            rtp=self.post('/api/routing/sources',{'label':'RTP','protocol':'rtp','url':'udp+rtp://239.1.2.3:12002',
                'sdp':'v=0\no=- 1 1 IN IP4 239.1.2.3\ns=RTP\nt=0 0\nm=video 12002 RTP/AVP 96\na=rtpmap:96 H264/90000\n'})
            self.assertEqual(rtp.status_code,200,rtp.json)
        details=self.client.get('/api/ingest/'+mpegts.json['key']).json
        self.assertEqual(details['mpegts'],'udp://127.0.0.1:12000')

    def test_routing_policy_source_on_demand_and_native_standby(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        native_root=Path(temporary.name)
        environment=patch.dict(os.environ,{'STREAMDESK_NATIVE_ROOT':str(native_root)})
        environment.start();self.addCleanup(environment.stop)
        with patch.object(app,'reconcile'):
            response=self.post('/api/routing/policy',{'healthy_seconds':1.5,'stall_seconds':8,'retry_seconds':12,'native_standby':True})
        self.assertEqual(response.status_code,200,response.json)
        policy=app.MODEL.policy(self.user)
        self.assertEqual((policy['healthy_seconds'],policy['stall_seconds'],policy['retry_seconds'],policy['native_standby']),(1.5,8,12,1))
        with patch.object(app,'validate_output',return_value='rtsp://camera.example/live'),patch.object(app,'reconcile'):
            source=self.post('/api/routing/sources',{'label':'Bedarfskamera','protocol':'proxy','url':'rtsp://camera.example/live','source_on_demand':True})
        self.assertEqual(source.status_code,200,source.json)
        app.reconcile()
        config=yaml.safe_load(app.CONFIG.read_text())
        self.assertTrue(config['paths'][self.user['prefix']+source.json['key']]['sourceOnDemand'])
        standby=Path(config['paths'][self.user['prefix']+'live']['alwaysAvailableFile'])
        self.assertTrue(standby.is_relative_to(native_root))
        self.assertEqual(standby.read_bytes(),Path(self.user['offline']).read_bytes())

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
            response=self.post('/api/admin/playback',{'enabled':True,'address':address})
            self.assertEqual(response.status_code,400,response.json)
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
            response = self.post('/api/password',{'current':'wrong','password':changed})
            self.assertEqual(response.status_code,400,response.json)
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


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.client=app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID,version=1,csrf='automation',expert_mode=True)
        self.headers={'X-CSRF-Token':'automation'}
        self.feature=app.FEATURES.automation
        for table in ('automation_hooks','scheduled_jobs','export_targets','exported_media'):
            app.write('DELETE FROM '+table+' WHERE user_id=?',(UID,))

    def post(self,path,body):
        return self.client.post(path,json=body,headers=self.headers)

    def test_allowlisted_hook_has_minimal_environment_and_scheduler_survives_polling(self):
        self.feature.commands={'notify':['/usr/bin/true']}
        self.assertEqual(self.post('/api/automation/hooks',{'event':'publish','action_name':'missing'}).status_code,400)
        self.assertEqual(self.post('/api/automation/hooks',{'event':'publish','action_name':'notify'}).status_code,200)
        user=app.rows('SELECT * FROM users WHERE id=?',(UID,))[0]
        with patch('automation_features.subprocess.run') as run:
            self.feature.run_hook(user,'publish','notify')
        environment=run.call_args.kwargs['env']
        self.assertEqual(set(environment),{'PATH','STREAMDESK_EVENT','STREAMDESK_USER_ID','STREAMDESK_USERNAME'})
        job=self.post('/api/automation/jobs',{'kind':'record_stop','payload':{},'run_at':app.time.time()}).json['id']
        self.feature.last_tick=0
        with patch.object(app.ENGINE,'stop_record') as stop:
            self.feature.run_scheduled()
        stop.assert_called_once_with(UID,'Zeitplan beendet.')
        self.assertEqual(app.rows('SELECT status FROM scheduled_jobs WHERE id=?',(job,))[0]['status'],'done')

    def test_export_configuration_rejects_private_targets_and_keeps_password(self):
        with patch.object(app,'validate_public_http',side_effect=app.Error('blocked')):
            self.assertEqual(self.post('/api/automation/export',{'enabled':True,'url':'https://127.0.0.1/','username':'a','password':'b'}).status_code,400)
        with patch.object(app,'validate_public_http',return_value='https://export.example/'):
            self.assertEqual(self.post('/api/automation/export',{'enabled':True,'url':'https://export.example/','username':'alice','password':'secret'}).status_code,200)
            self.assertEqual(self.post('/api/automation/export',{'enabled':True,'url':'https://export.example/','username':'alice','password':''}).status_code,200)
        row=app.rows('SELECT * FROM export_targets WHERE user_id=?',(UID,))[0]
        self.assertEqual(app.decrypt(row['password']),'secret')


class BuildDTests(unittest.TestCase):
    def setUp(self):
        self.client=app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID,version=app.rows('SELECT version FROM users WHERE id=?',(UID,))[0]['version'],
                           csrf='build-d',expert_mode=True)
        self.headers={'X-CSRF-Token':'build-d'}
        self.user=app.rows('SELECT * FROM users WHERE id=?',(UID,))[0]
        self.outputs=app.rows('SELECT * FROM outputs WHERE user_id=?',(UID,))
        self.routes=app.rows('SELECT * FROM output_routing WHERE user_id=?',(UID,))
        self.addCleanup(self.restore)
        for table in ('scenes','webauthn_credentials','recovery_codes','discord_auth'):
            app.write('DELETE FROM '+table+' WHERE user_id=?',(UID,))
        app.write("UPDATE users SET role='user',admin=0,chat_owner_id=NULL,language='de' WHERE id=?",(UID,))

    def restore(self):
        app.write('UPDATE users SET role=?,admin=?,chat_owner_id=?,language=?,version=? WHERE id=?',
                  tuple(self.user[key] for key in ('role','admin','chat_owner_id','language','version'))+(UID,))
        app.write('DELETE FROM outputs WHERE user_id=?',(UID,))
        for row in self.outputs:
            app.write('INSERT INTO outputs(user_id,kind,endpoint,selected,label) VALUES (?,?,?,?,?)',
                      tuple(row[key] for key in ('user_id','kind','endpoint','selected','label')))
        app.write('DELETE FROM output_routing WHERE user_id=?',(UID,))
        for row in self.routes:
            app.write('INSERT INTO output_routing(user_id,kind,sources) VALUES (?,?,?)',
                      (row['user_id'],row['kind'],row['sources']))

    def post(self,path,body):
        return self.client.post(path,json=body,headers=self.headers)

    def test_language_and_scene_are_tenant_scoped_and_apply_only_stopped(self):
        self.assertEqual(self.post('/api/preferences',{'language':'en'}).status_code,200)
        self.assertEqual(app.rows('SELECT language FROM users WHERE id=?',(UID,))[0]['language'],'en')
        app.write('INSERT OR REPLACE INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,0)',
                  (UID,'twitch',app.encrypt('rtmps://example.invalid/live')))
        response=self.post('/api/scenes',{'name':'Live','sources':['source1'],'video_id':None,'targets':['twitch']})
        self.assertEqual(response.status_code,200,response.json)
        ident=response.json['id']
        with patch.object(app,'configured_forwards',return_value={'fixture':['active']}):
            self.assertEqual(self.post('/api/scenes/'+str(ident)+'/apply',{}).status_code,400)
        with patch.object(app,'configured_forwards',return_value={}),patch.object(app,'reconcile'):
            self.assertEqual(self.post('/api/scenes/'+str(ident)+'/apply',{}).status_code,200)
        self.assertEqual(app.MODEL.route(app.rows('SELECT * FROM users WHERE id=?',(UID,))[0],'twitch'),['source1'])

    def test_moderator_can_only_use_assigned_chat(self):
        app.write("UPDATE users SET role='moderator',chat_owner_id=?,version=version+1 WHERE id=?",(OTHER,UID))
        version=app.rows('SELECT version FROM users WHERE id=?',(UID,))[0]['version']
        with self.client.session_transaction() as session:
            session.update(uid=UID,version=version,csrf='build-d')
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertIn('Moderation',self.client.get('/').get_data(as_text=True))
        self.assertEqual(self.client.get('/api/status').status_code,403)
        with patch.object(app.CHAT,'read',return_value={'messages':[]}) as read:
            self.assertEqual(self.client.get('/api/chat').status_code,200)
            self.assertEqual(read.call_args.args[0]['id'],OTHER)

    def test_recovery_code_is_single_use(self):
        feature=app.FEATURES.build_d
        code='ABCDEF1234'
        app.write('INSERT INTO recovery_codes(user_id,code_hash) VALUES (?,?)',(UID,feature.recovery_hash(UID,code)))
        client=app.app.test_client()
        client.get('/login')
        with client.session_transaction() as session:token=session['csrf']
        headers={'X-CSRF-Token':token}
        self.assertEqual(client.post('/api/recovery/login',json={'username':'alice','code':code},headers=headers).status_code,200)
        client.get('/login')
        with client.session_transaction() as session:token=session['csrf']
        self.assertEqual(client.post('/api/recovery/login',json={'username':'alice','code':code},
                                     headers={'X-CSRF-Token':token}).status_code,401)

    def test_discord_credentials_are_encrypted(self):
        with patch.object(app.CHAT,'discord_api',return_value={'id':'123456789012345678','type':0,'name':'Studio'}):
            response=self.post('/api/discord',{'channel_id':'123456789012345678','bot_token':'x'*40})
        self.assertEqual(response.status_code,200,response.json)
        row=app.rows('SELECT * FROM discord_auth WHERE user_id=?',(UID,))[0]
        self.assertNotEqual(row['bot_token'],'x'*40)
        self.assertEqual(app.decrypt(row['bot_token']),'x'*40)


class ReviewTests(unittest.TestCase):
    """Regressions found while reviewing the post-rc.6 additions."""
    def setUp(self):
        import sqlite3
        self.backup = sqlite3.connect(':memory:')
        with app.db() as connection:
            connection.backup(self.backup)
        config = app.CONFIG.read_text()
        attempts = dict(app.ATTEMPTS)
        self.addCleanup(self.restore, config, attempts)
        app.ATTEMPTS.clear()
        app.write("UPDATE users SET role='user',admin=0,chat_owner_id=NULL WHERE id=?", (UID,))
        app.write('DELETE FROM routing_policy WHERE user_id=?', (UID,))
        self.user = app.rows('SELECT * FROM users WHERE id=?', (UID,))[0]
        self.client = app.app.test_client()
        with self.client.session_transaction() as session:
            session.update(uid=UID,version=self.user['version'],csrf='review',expert_mode=True)
        self.headers = {'X-CSRF-Token':'review'}

    def restore(self, config, attempts):
        with app.db() as connection:
            self.backup.backup(connection)
        self.backup.close()
        app.CONFIG.write_text(config)
        app.ATTEMPTS.clear();app.ATTEMPTS.update(attempts)

    def post(self, path, body):
        return self.client.post(path, json=body, headers=self.headers)

    def test_scenes_cannot_bypass_expert_mode_or_recording_guard(self):
        response = self.post('/api/scenes', {'name':'Review','sources':['source1'],'targets':['twitch']})
        self.assertEqual(response.status_code,200,response.json)
        ident=response.json['id']
        with self.client.session_transaction() as session:session['expert_mode']=False
        self.assertEqual(self.post('/api/scenes',{'name':'Other','sources':['source1'],'targets':[]}).status_code,403)
        self.assertEqual(self.post('/api/scenes/'+str(ident)+'/apply',{}).status_code,403)
        with self.client.session_transaction() as session:session['expert_mode']=True
        before=app.MODEL.route(self.user,'twitch')
        with patch.object(app,'configured_forwards',return_value={}),patch.object(app.FEATURES.routing,'record_guard',side_effect=app.Error('Recording',http_status=409)):
            self.assertEqual(self.post('/api/scenes/'+str(ident)+'/apply',{}).status_code,409)
        self.assertEqual(app.MODEL.route(self.user,'twitch'),before)

    def test_malformed_scene_arrays_are_validation_errors(self):
        for sources,targets in (([{}],[]),(['source1'],[{}])):
            self.assertEqual(self.post('/api/scenes',{'name':'Bad','sources':sources,'targets':targets}).status_code,400)

    def passkey_registration(self, verified=True):
        import base64
        import cbor2
        import hashlib
        import json
        from cryptography.hazmat.primitives.asymmetric import ec
        encode=lambda data:base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        options=self.post('/api/passkeys/register/options',{}).json
        key=ec.generate_private_key(ec.SECP256R1());public=key.public_key().public_numbers()
        ident=b'review-credential-0123456789'
        cose={1:2,3:-7,-1:1,-2:public.x.to_bytes(32,'big'),-3:public.y.to_bytes(32,'big')}
        flags=0x45 if verified else 0x41
        auth=hashlib.sha256(b'stream.example.com').digest()+bytes([flags])+b'\0'*4+b'\0'*16+len(ident).to_bytes(2,'big')+ident+cbor2.dumps(cose)
        body={'credential_id':encode(ident),'client_data':encode(json.dumps({'type':'webauthn.create','challenge':options['challenge'],'origin':app.PUBLIC}).encode()),
              'attestation_object':encode(cbor2.dumps({'fmt':'none','attStmt':{},'authData':auth})),'label':'Review device'}
        return key,ident,body

    def test_passkey_registration_and_login_are_verified_and_single_use(self):
        import base64
        import hashlib
        import json
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        encode=lambda data:base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        key,ident,body=self.passkey_registration()
        response=self.post('/api/passkeys/register',body)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(len(response.json['recovery_codes']),10)
        options=self.post('/api/passkeys/login/options',{'username':'alice'}).json
        cookie=self.client.get_cookie('session').value
        client_data=json.dumps({'type':'webauthn.get','challenge':options['challenge'],'origin':app.PUBLIC}).encode()
        auth=hashlib.sha256(b'stream.example.com').digest()+b'\x05'+b'\0'*4
        signature=key.sign(auth+hashlib.sha256(client_data).digest(),ec.ECDSA(hashes.SHA256()))
        assertion={'credential_id':encode(ident),'client_data':encode(client_data),'authenticator_data':encode(auth),'signature':encode(signature)}
        response=self.post('/api/passkeys/login',assertion)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.client.get('/api/status').status_code,200)
        self.client.set_cookie('session',cookie)
        self.assertEqual(self.post('/api/passkeys/login',assertion).status_code,400)

    def test_passkey_requires_verification_and_rejects_forged_registration(self):
        _,_,body=self.passkey_registration(verified=False)
        self.assertEqual(self.post('/api/passkeys/register',body).status_code,400)
        self.post('/api/passkeys/register/options',{})
        self.assertEqual(self.post('/api/passkeys/register',{'algorithm':'invalid','credential_id':'!!!!','public_key':'!!!!'}).status_code,400)

    def test_passkey_and_recovery_login_share_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.post('/api/recovery/login',{'username':'alice','code':'INVALID'}).status_code,401)
        self.assertEqual(self.post('/api/recovery/login',{'username':'alice','code':'INVALID'}).status_code,429)
        self.assertEqual(self.post('/api/passkeys/login/options',{'username':'alice'}).status_code,429)

    def test_background_export_cannot_hold_up_engine_tick(self):
        import threading
        import time
        feature=app.FEATURES.automation
        entered,release=threading.Event(),threading.Event()
        def slow():
            entered.set();release.wait(5)
        try:
            with patch.object(feature,'export_ready',side_effect=slow),patch.object(feature,'run_scheduled'):
                feature.last_tick=0;feature.last_export=0
                started=time.monotonic();feature.tick()
                self.assertLess(time.monotonic()-started,.5)
                self.assertTrue(entered.wait(2))
                feature.last_tick=0;feature.tick()
                self.assertEqual(len(feature.workers),2)
        finally:
            release.set()
            for worker in feature.workers.values():worker.join(3)
            feature.workers.clear()

    def test_export_streams_files_and_backs_off_on_failure(self):
        from contextlib import contextmanager
        feature=app.FEATURES.automation
        path=app.DATA/'review-export.mp4';path.write_bytes(b'fixture'*1000);self.addCleanup(path.unlink,missing_ok=True)
        app.write("INSERT INTO recordings(user_id,name,path,source,status,started) VALUES (?,?,?,'live','ready',0)",(UID,'Review',str(path)))
        app.write('INSERT OR REPLACE INTO export_targets(user_id,url,username,password,enabled) VALUES (?,?,?,?,1)',(UID,app.encrypt('https://export.example/'),app.encrypt('u'),app.encrypt('p')))
        received=[]
        @contextmanager
        def upload(url,**kwargs):
            self.assertTrue(hasattr(kwargs['data'],'read'))
            received.append(kwargs['data'].read())
            raise OSError('offline')
            yield
        with patch.object(app,'validate_public_http'),patch.object(app,'public_https',side_effect=upload):
            feature.export_ready();feature.export_ready()
        self.assertEqual(received,[b'fixture'*1000])
        row=app.rows('SELECT status,retry_at FROM exported_media WHERE user_id=? AND path=?',(UID,str(path)))[0]
        self.assertEqual(row['status'],'error');self.assertGreater(row['retry_at'],app.time.time())
        self.assertNotIn(UID,feature.busy_users)

    def test_invalid_json_and_smtp_targets_fail_without_network(self):
        for path in ('/api/automation/jobs','/api/automation/hooks','/api/notifications'):
            self.assertEqual(self.post(path,[]).status_code,400)
        base={'enabled':True,'email':'a@example.com','smtp_host':'127.0.0.1','smtp_port':465}
        with patch.object(app,'resolve_host_ips',return_value={'127.0.0.1'}):
            self.assertEqual(self.post('/api/notifications',base).status_code,400)
        self.assertEqual(self.post('/api/notifications',dict(base,smtp_port=70000)).status_code,400)
        self.assertEqual(self.post('/api/notifications',dict(base,email='a@example.com\r\nBcc: b@example.com')).status_code,400)

    def test_on_demand_pull_is_started_for_program_consumer_and_stopped_afterwards(self):
        from unittest.mock import MagicMock
        with patch.object(app,'validate_output',return_value='rtsp://camera.example/live'):
            created=self.post('/api/routing/sources',{'label':'On demand','protocol':'rtsp','url':'rtsp://camera.example/live','source_on_demand':True})
        self.assertEqual(created.status_code,200,created.json)
        key=created.json['key'];app.MODEL.save_route(self.user,'twitch',[key])
        app.reconcile();config=yaml.safe_load(app.CONFIG.read_text());program=app.MODEL.output_program(self.user,'twitch')
        engine=app.Engine();process=MagicMock();process.poll.return_value=None
        with patch.object(app.subprocess,'Popen',return_value=process) as launch:
            engine.demand_sources(self.user,app.MODEL.sources(self.user),{program['path']:{'readers':[{'id':'fixture'}]}},config,100)
            self.assertEqual(launch.call_count,1)
            engine.demand_sources(self.user,app.MODEL.sources(self.user),{},config,101)
            process.terminate.assert_called_once()
            self.assertFalse(engine.source_probes)

    def test_live_browser_overlay_is_not_reported_as_offline_and_failure_falls_back(self):
        from unittest.mock import MagicMock
        engine=app.Engine();program=app.MODEL.program(self.user,'main');process=MagicMock();process.poll.return_value=None
        config=yaml.safe_load(app.CONFIG.read_text());path=self.user['prefix']+'source1'
        all_paths={program['path']:{'online':True,'available':True,'readers':[{}]}}
        with patch.object(engine,'start_browser',return_value=process):
            state=engine.program_tick(self.user,program,[path],all_paths,config,False,100,'https://overlay.example/',app.MODEL.policy(self.user))
        self.assertEqual(state['selected_source'],'source1');self.assertFalse(state['offline_playing'])
        process.poll.return_value=1
        fallback=MagicMock();fallback.poll.return_value=None
        with patch.object(app.subprocess,'Popen',return_value=fallback):
            state=engine.program_tick(self.user,program,[path],all_paths,config,False,101,'https://overlay.example/',app.MODEL.policy(self.user))
        self.assertEqual(engine.relays[UID][0],path)

    def test_proxy_protocol_change_never_reuses_unvalidated_previous_endpoint(self):
        created=self.post('/api/routing/sources',{'label':'Camera','protocol':'srt'})
        self.assertEqual(created.status_code,200)
        with patch.object(app,'validate_output',side_effect=app.Error('Address required')) as check:
            response=self.post('/api/routing/sources/'+created.json['key'],{'protocol':'proxy'})
        self.assertEqual(response.status_code,400);check.assert_called_once_with('')

    def test_admin_deletion_removes_all_new_tenant_data_and_archives_clips(self):
        with patch.object(app.threading,'Thread'):
            uid=app.add_user('reviewdelete','Review-Deletion-Password-123')
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        app.write('UPDATE users SET active=0 WHERE id=?',(uid,))
        folder=app.DATA/'clips'/'reviewdelete';folder.mkdir(parents=True)
        path=folder/'clip.mp4';path.write_bytes(b'private-clip')
        app.write("INSERT INTO clips(user_id,name,path,source,start,duration,size,created) VALUES (?,?,?,'live','2026-01-01T00:00:00Z',1,12,0)",(uid,'Review',str(path)))
        app.write("INSERT INTO scheduled_jobs(user_id,kind,payload,run_at) VALUES (?,'output_start','{}',0)",(uid,))
        app.write("INSERT INTO notification_settings(user_id,webhook) VALUES (?,?)",(uid,app.encrypt('https://example.com/hook')))
        app.write('INSERT INTO routing_policy(user_id) VALUES (?)',(uid,))
        with patch.object(app,'mtx',return_value={}):
            response=self.post('/api/admin/users/'+str(uid)+'/delete',{'confirm':'reviewdelete'})
        self.assertEqual(response.status_code,200,response.json)
        for table in ('clips','scheduled_jobs','notification_settings','routing_policy'):
            self.assertFalse(app.rows('SELECT * FROM '+table+' WHERE user_id=?',(uid,)))
        self.assertFalse(folder.exists())
        self.assertTrue(list((app.DATA/'clips').glob('.deleted-reviewdelete-*')))

    def test_youtube_stream_consumes_grpc_messages_after_discord_extension(self):
        import grpc
        import stream_list_pb2 as proto
        import stream_list_pb2_grpc as service
        import threading
        from unittest.mock import MagicMock
        response=proto.LiveChatMessageListResponse(next_page_token='next-fixture')
        item=response.items.add();item.id='message-1';item.snippet.display_message='Fixture message'
        item.author_details.display_name='Fixture author';item.author_details.channel_id='fixture-channel'
        call=MagicMock();call.__iter__.return_value=iter([response])
        stub=MagicMock();stub.StreamList.return_value=call
        with patch.object(app.CHAT,'youtube_token',return_value=('fixture',{'chat_id':'fixture-chat','broadcast_id':'fixture','expires':app.time.time()+3600})), \
             patch.object(app.CHAT,'youtube_api',return_value={'items':[{'status':{'lifeCycleStatus':'live'}}]}), \
             patch.object(grpc,'secure_channel'),patch.object(service,'V3DataLiveChatMessageServiceStub',return_value=stub), \
             patch.object(app.CHAT,'interested',return_value=True),patch.object(app.CHAT,'add') as add,patch('integrations.threading.Thread'):
            app.CHAT.youtube_stream(UID,threading.Event())
        add.assert_called_once()
        self.assertEqual(add.call_args.args[1:5],('youtube','message-1','Fixture author','Fixture message'))
        self.assertEqual(app.CHAT.youtube_pages[(UID,'fixture-chat')],'next-fixture')
        call.cancel.assert_called_once()

    def test_discord_cursor_advances_past_bot_messages(self):
        from unittest.mock import MagicMock
        app.write('INSERT OR REPLACE INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                  (UID,'123456789012345678','Fixture',app.encrypt('fixture-bot-token')))
        stop=MagicMock();stop.wait.return_value=False
        pages=[[{'id':'123456789012345679','type':0,'author':{'bot':True}}],
               [{'id':'123456789012345680','type':0,'author':{'username':'Human'},'content':'Hello'}]]
        with patch.object(app.CHAT,'interested',side_effect=[True,True,False]),patch.object(app.CHAT,'discord_api',side_effect=pages) as fetch,patch.object(app.CHAT,'add') as add:
            app.CHAT.discord_stream(UID,stop)
        self.assertIn('after=123456789012345679',fetch.call_args_list[1].args[1])
        add.assert_called_once()

    def test_native_standby_copy_is_shared_without_exposing_private_data_root(self):
        with tempfile.TemporaryDirectory(dir=BASE) as temporary,patch.dict(os.environ,{'STREAMDESK_NATIVE_ROOT':temporary}):
            path=Path(app.native_standby_file(self.user))
            self.assertEqual(path.read_bytes(),Path(self.user['offline']).read_bytes())
            self.assertEqual(path.stat().st_mode & 0o777,0o640)
            self.assertFalse(path.is_relative_to(app.DATA))

    def test_batch_routing_cannot_orphan_a_recorded_program(self):
        for kind in ('twitch','youtube'):
            app.MODEL.save_route(self.user,kind,['source1'])
        program=app.MODEL.output_program(self.user,'twitch')
        app.write("INSERT INTO recordings(user_id,name,path,source,status,started) VALUES (?,?,?,?,'recording',0)",
                  (UID,'Guard','/fixture/unused.mp4',program['id']))
        with self.assertRaises(app.Error):
            app.FEATURES.routing.record_guard(self.user,'twitch',['source2'],{'twitch':['source2'],'youtube':['source2']})
        app.FEATURES.routing.record_guard(self.user,'twitch',['source2'])

    def test_udp_protocol_change_requires_matching_url_and_ports_are_exclusive(self):
        created=self.post('/api/routing/sources',{'label':'UDP one','protocol':'mpegts','url':'udp+mpegts://0.0.0.0:12098?source=1.1.1.1'})
        self.assertEqual(created.status_code,200,created.json)
        duplicate=self.post('/api/routing/sources',{'label':'UDP two','protocol':'mpegts','url':'udp+mpegts://0.0.0.0:12098?source=1.0.0.1'})
        self.assertEqual(duplicate.status_code,409)
        key=created.json['key']
        self.assertEqual(self.post('/api/routing/sources/'+key,{'protocol':'rtp'}).status_code,400)
        self.assertEqual(app.MODEL.source(self.user,key)['protocol'],'mpegts')

    def test_remote_native_features_require_shared_storage(self):
        with patch.dict(os.environ,{'STREAMDESK_MEDIAMTX_MODE':'remote-api','STREAMDESK_NATIVE_SHARED':'0'}):
            response=self.post('/api/native-recording',{'source':'source1','enabled':True})
            self.assertEqual(response.status_code,409,response.json)
            response=self.post('/api/routing/policy',{'healthy_seconds':3,'stall_seconds':5,'retry_seconds':10,'native_standby':True})
            self.assertEqual(response.status_code,409,response.json)

    def test_clip_conversion_capacity_is_bounded(self):
        slots=app.FEATURES.playback.remux_slots
        self.assertTrue(slots.acquire(blocking=False));self.assertTrue(slots.acquire(blocking=False))
        try:
            result=self.post('/api/clips',{'source':'source1','start':'2026-10-27T12:00:00Z','duration':1,'name':'Bounded'})
            self.assertEqual(result.status_code,429,result.json)
            self.assertFalse(app.FEATURES.playback.active_clips)
        finally:
            slots.release();slots.release()

    def test_moderator_role_cannot_own_itself_and_retains_own_password_change(self):
        app.write('UPDATE users SET admin=1 WHERE id=?',(UID,))
        result=self.post('/api/admin/users/'+str(OTHER)+'/role',{'role':'moderator','chat_owner_id':OTHER})
        self.assertEqual(result.status_code,409,result.json)
        with patch.object(app,'mtx',return_value={}):
            result=self.post('/api/admin/users/'+str(OTHER)+'/role',{'role':'moderator','chat_owner_id':UID})
        self.assertEqual(result.status_code,200,result.json)
        user=app.rows('SELECT * FROM users WHERE id=?',(OTHER,))[0]
        config=yaml.safe_load(app.CONFIG.read_text())
        self.assertFalse(any(row['user']==app.media_username(user) for row in config['authInternalUsers']))
        app.write('UPDATE users SET password=? WHERE id=?',(app.generate_password_hash('Moderator-Fixture-Password-123'),OTHER))
        client=app.app.test_client()
        with client.session_transaction() as session:session.update(uid=OTHER,version=user['version'],csrf='moderator')
        result=client.post('/api/password',json={'current':'Moderator-Fixture-Password-123','password':'New-Moderator-Password-456'},headers={'X-CSRF-Token':'moderator'})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(client.get('/api/status').status_code,403)

    def test_idle_static_source_is_not_displayed_as_receiving_media(self):
        with patch.object(app,'validate_output',return_value='rtsp://camera.example/live'):
            created=self.post('/api/routing/sources',{'label':'Idle camera','protocol':'rtsp','url':'rtsp://camera.example/live','source_on_demand':True})
        key=created.json['key']
        engine=app.Engine()
        path={'name':self.user['prefix']+key,'online':True,'available':False,'inboundBytes':0,'tracks':[]}
        with patch.object(app,'mtx',return_value={'items':[path]}),patch.object(app.FEATURES.automation,'tick'),patch.object(app.FEATURES.notifications,'observe'):
            engine.tick()
        source=next(row for row in engine.snapshot[UID]['sources'] if row['key']==key)
        self.assertEqual(source['state'],'offline')

    def test_readiness_requires_a_connected_live_engine(self):
        from unittest.mock import MagicMock
        thread=MagicMock()
        with patch.object(app.ENGINE,'thread',thread),patch.object(app.READY,'is_set',return_value=True):
            thread.is_alive.return_value=False
            self.assertEqual(self.client.get('/healthz').status_code,503)
            thread.is_alive.return_value=True
            self.assertEqual(self.client.get('/healthz').status_code,200)

    def test_strict_rtmp_returns_the_actual_encrypted_listener(self):
        config=yaml.safe_load(app.CONFIG.read_text());config.update(rtmpEncryption='strict',rtmpsAddress=':11936')
        app.CONFIG.write_text(yaml.safe_dump(config))
        data=self.client.get('/api/ingest/source1').json
        self.assertTrue(data['rtmp'].startswith('rtmps://127.0.0.1:11936/'))

    def test_discord_nonce_fits_provider_limit_and_retries_are_idempotent(self):
        old_nonces=dict(app.CHAT.nonces);old_sent=dict(app.CHAT.sent_at)
        def restore():
            app.CHAT.nonces.clear();app.CHAT.nonces.update(old_nonces)
            app.CHAT.sent_at.clear();app.CHAT.sent_at.update(old_sent)
        self.addCleanup(restore)
        app.CHAT.sent_at[UID]=0
        app.write('INSERT OR REPLACE INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                  (UID,'123456789012345678','Fixture',app.encrypt('fixture-token')))
        body={'message':'Fixture message','targets':['discord'],'nonce':'review_message_0123456789abcdef0123456789abcdef'}
        with patch.object(app.CHAT,'info',return_value={'discord_ready':True}),patch.object(app.CHAT,'discord_api',return_value={'id':'1234','author':{'username':'Fixture'}}) as send,patch.object(app.CHAT,'add'):
            first=app.CHAT.send(self.user,body)
            self.assertEqual(app.CHAT.send(self.user,body),first)
        self.assertEqual(send.call_count,1)
        self.assertLessEqual(len(send.call_args.args[2]['nonce']),25)

    def test_discord_setup_requires_expert_but_existing_chat_remains_available(self):
        with self.client.session_transaction() as session:session['expert_mode']=False
        for operation,path in (('get','/api/discord'),('post','/api/discord'),('post','/api/discord/disconnect')):
            response=getattr(self.client,operation)(path,**({'json':{},'headers':self.headers} if operation=='post' else {}))
            self.assertEqual(response.status_code,403)
        with patch.object(app.CHAT,'read',return_value={'messages':[]}):
            self.assertEqual(self.client.get('/api/chat').status_code,200)
        with self.client.session_transaction() as session:session['expert_mode']=True
        self.assertEqual(self.client.get('/api/discord').status_code,200)
        self.assertEqual(self.client.post('/api/discord',json={}).status_code,403)

    def test_discord_setup_status_is_private_and_never_returns_bot_token(self):
        app.write('INSERT OR REPLACE INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                  (UID,'123456789012345678','Own studio',app.encrypt('private-review-token')))
        app.write('INSERT OR REPLACE INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                  (OTHER,'987654321098765432','Other studio',app.encrypt('foreign-review-token')))
        data=self.client.get('/api/discord')
        self.assertEqual(data.json,{'connected':True,'channel_id':'123456789012345678','channel_name':'Own studio'})
        self.assertNotIn('token',data.get_data(as_text=True))
        self.assertNotIn('Other studio',data.get_data(as_text=True))

    def test_release_version_is_shared_by_api_ui_and_static_assets(self):
        expected=(ROOT/'VERSION').read_text().strip()
        self.assertEqual(app.APP_VERSION,expected)
        self.assertEqual(self.client.get('/api/status').json['app_version'],expected)
        html=self.client.get('/').get_data(as_text=True)
        self.assertIn('v'+expected,html)
        self.assertIn('/static/discord.js?v='+expected,html)


class ServicePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(app.threading, 'Thread'):
            cls.admin_id = app.add_user('services_admin', 'Services-Fixture-Password-123', admin=True)
            cls.user_id = app.add_user('services_user', 'Services-Fixture-Password-456')

    def setUp(self):
        import json
        self.json = json
        self.config = app.CONFIG.read_text()
        self.saved = app.rows("SELECT * FROM settings WHERE name IN ('service_policy','service_paused_recordings')")
        self.pending = app.SERVICES.pending_runtime
        app.write("DELETE FROM settings WHERE name IN ('service_policy','service_paused_recordings')")
        self.admin = app.app.test_client()
        self.client = app.app.test_client()
        for client, uid in ((self.admin,self.admin_id),(self.client,self.user_id)):
            with client.session_transaction() as session:
                session.update(uid=uid,version=1,csrf='services',expert_mode=True)
        self.headers = {'X-CSRF-Token':'services'}
        self.user = app.rows('SELECT * FROM users WHERE id=?',(self.user_id,))[0]
        app.reconcile()

    def tearDown(self):
        app.CONFIG.write_text(self.config)
        app.write("DELETE FROM settings WHERE name IN ('service_policy','service_paused_recordings')")
        for row in self.saved:
            app.write('INSERT INTO settings(name,value) VALUES (?,?)',(row['name'],row['value']))
        for table in ('outputs','discord_auth','scheduled_jobs','viewer_links'):
            app.write('DELETE FROM '+table+' WHERE user_id IN (?,?)',(self.admin_id,self.user_id))
        app.write("UPDATE users SET output='',output_kind='twitch' WHERE id IN (?,?)",(self.admin_id,self.user_id))
        app.SERVICES.pending_runtime = self.pending
        app.CHAT.prune(set())

    def toggle(self, key, enabled):
        response = self.admin.post('/api/admin/services',json={'id':key,'enabled':enabled},headers=self.headers)
        self.assertEqual(response.status_code,200,response.get_data(as_text=True))
        return response.json

    def test_only_admin_can_change_global_services_without_expert_mode(self):
        self.assertEqual(self.client.get('/api/admin/services').status_code,403)
        self.assertEqual(self.client.post('/api/admin/services',json={'id':'discord','enabled':False},headers=self.headers).status_code,403)
        self.assertEqual(self.admin.post('/api/admin/services',json={'id':'discord','enabled':False}).status_code,403)
        with self.admin.session_transaction() as session:session['expert_mode']=False
        self.toggle('discord',False)
        self.assertFalse(self.client.get('/api/status').json['services']['discord'])
        self.assertIn('admin-service-list',self.admin.get('/').get_data(as_text=True))
        self.assertNotIn('admin-service-list',self.client.get('/').get_data(as_text=True))
        self.assertNotIn('bot_token',self.admin.get('/api/admin/services').get_data(as_text=True))

    def test_defaults_persistence_and_invalid_changes(self):
        self.assertTrue(all(app.SERVICES.flags().values()))
        for body in ({'id':'unknown','enabled':False},{'id':'discord','enabled':'false'},
                     {'id':'discord','enabled':0},{'id':'discord','enabled':False,'user_id':self.user_id}):
            self.assertEqual(self.admin.post('/api/admin/services',json=body,headers=self.headers).status_code,400)
        self.toggle('discord',False)
        from service_policy import ServicePolicy
        restarted = object.__new__(ServicePolicy);restarted.c=app
        self.assertFalse(restarted.enabled('discord'))
        self.assertTrue(restarted.enabled('twitch'))
        self.toggle('discord',True)
        self.assertTrue(restarted.enabled('discord'))

    def test_discord_restriction_keeps_encrypted_credentials_and_chat_history(self):
        token=app.encrypt('Fixture-Discord-Token-123456789012345')
        app.write('INSERT INTO discord_auth(user_id,channel_id,channel_name,bot_token) VALUES (?,?,?,?)',
                  (self.user_id,'123456789012345678','Fixture',token))
        app.CHAT.add(self.user_id,'discord','fixture','Bot','Existing message')
        self.toggle('discord',False)
        for client in (self.admin,self.client):
            self.assertEqual(client.get('/api/discord').status_code,403)
            self.assertEqual(client.post('/api/discord/disconnect',json={},headers=self.headers).status_code,403)
        with patch.object(app.threading,'Thread'),patch.object(app.CHAT,'discord_api') as remote:
            chat=self.client.get('/api/chat').json
            self.assertFalse(chat['discord_ready'])
            self.assertFalse(chat['messages'])
            self.assertEqual(self.client.post('/api/chat/send',json={'targets':['discord'],'message':'test','nonce':'fixture-nonce-1234'},headers=self.headers).status_code,403)
            remote.assert_not_called()
            self.toggle('discord',True)
            self.assertTrue(self.client.get('/api/chat').json['discord_ready'])
        self.assertEqual(app.rows('SELECT bot_token FROM discord_auth WHERE user_id=?',(self.user_id,))[0]['bot_token'],token)
        self.assertEqual(len(app.CHAT.messages[self.user_id]),1)

    def test_provider_suspension_keeps_keys_selection_and_other_outputs(self):
        for kind in ('twitch','youtube'):
            app.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',
                      (self.user_id,kind,app.encrypt('rtmps://fixture.invalid/'+kind+'#Fixture-Key-123')))
        original=app.rows('SELECT * FROM outputs WHERE user_id=?',(self.user_id,))
        self.toggle('twitch',False)
        with patch.object(app,'validate_output',side_effect=lambda value:value),patch.object(app,'mtx'):
            with self.assertRaises(app.Error):app.forward(self.user,True,kind='twitch')
            app.forward(self.user,True)
        config=app.yaml.safe_load(app.CONFIG.read_text())
        self.assertFalse(config['paths'][app.output_path(self.user,'twitch')]['forward'])
        self.assertTrue(config['paths'][app.output_path(self.user,'youtube')]['forward'])
        self.assertEqual(app.rows('SELECT * FROM outputs WHERE user_id=?',(self.user_id,)),original)
        self.assertEqual(self.client.post('/api/output',json={'kind':'twitch','key':'fixture-stream-key-1234'},headers=self.headers).status_code,403)
        self.assertEqual(self.client.post('/api/outputs/select',json={'kinds':['youtube']},headers=self.headers).status_code,200)
        self.assertTrue(app.rows("SELECT selected FROM outputs WHERE user_id=? AND kind='twitch'",(self.user_id,))[0]['selected'])
        self.toggle('twitch',True)
        self.assertFalse(app.yaml.safe_load(app.CONFIG.read_text())['paths'][app.output_path(self.user,'twitch')]['forward'])

    def test_recording_pause_retains_native_settings_and_foreign_paths(self):
        config=app.yaml.safe_load(app.CONFIG.read_text())
        name=self.user['prefix']+'source1'
        config['paths'][name].update(record=True,recordFormat='mpegts',recordSegmentDuration='1m',recordDeleteAfter='3d')
        config['paths']['foreign']={'source':'publisher','record':True,'recordFormat':'fmp4'}
        app.CONFIG.write_text(app.yaml.safe_dump(config))
        with patch.dict(app.ENGINE.recorders,{self.user_id:(123,object())}),patch.object(app.ENGINE,'stop_record') as stop:
            self.toggle('recording',False)
            stop.assert_called_once_with(self.user_id,'Aufnahmedienst durch Administration gesperrt.')
        paused=app.yaml.safe_load(app.CONFIG.read_text())
        self.assertFalse(paused['paths'][name]['record'])
        self.assertEqual(paused['paths'][name]['recordFormat'],'mpegts')
        self.assertEqual(paused['paths']['foreign'],config['paths']['foreign'])
        self.assertEqual(self.client.post('/api/recordings/start',json={'source':'live'},headers=self.headers).status_code,403)
        self.toggle('recording',True)
        resumed=app.yaml.safe_load(app.CONFIG.read_text())
        self.assertTrue(resumed['paths'][name]['record'])
        self.assertEqual(resumed['paths'][name]['recordDeleteAfter'],'3d')
        self.assertEqual(resumed['paths']['foreign'],config['paths']['foreign'])

    def test_paused_automation_does_not_consume_jobs_or_send_notifications(self):
        overdue=app.write('INSERT INTO scheduled_jobs(user_id,kind,payload,run_at) VALUES (?,?,?,?)',
                          (self.user_id,'record_start','{"source":"live"}',app.time.time()-10))
        future=app.write('INSERT INTO scheduled_jobs(user_id,kind,payload,run_at) VALUES (?,?,?,?)',
                         (self.user_id,'record_start','{"source":"live"}',app.time.time()+3600))
        self.toggle('automation',False);self.toggle('notifications',False)
        with patch.object(app,'start_recording') as record,patch.object(app.FEATURES.automation,'run_hook') as hook,patch.object(app.FEATURES.notifications,'public') as notify:
            app.FEATURES.automation.run_scheduled();app.FEATURES.automation.export_ready()
            app.FEATURES.automation.observe(self.user,[{'state':'online'}],[{'available':True}])
            app.FEATURES.notifications.deliver(self.user,'offline')
            record.assert_not_called();hook.assert_not_called();notify.assert_not_called()
        self.assertEqual(app.rows('SELECT status FROM scheduled_jobs WHERE id=?',(overdue,))[0]['status'],'pending')
        self.toggle('automation',True)
        self.assertEqual(app.rows('SELECT status FROM scheduled_jobs WHERE id=?',(overdue,))[0]['status'],'error')
        self.assertEqual(app.rows('SELECT status FROM scheduled_jobs WHERE id=?',(future,))[0]['status'],'pending')

    def test_runtime_failure_keeps_policy_closed_and_retries(self):
        with patch.object(app,'reconcile',side_effect=app.Error('Fixture unavailable')):
            response=self.toggle('twitch',False)
        self.assertTrue(response['runtime_pending'])
        self.assertFalse(app.SERVICES.enabled('twitch'))
        self.assertEqual(self.client.get('/oauth/twitch').status_code,403)
        with patch.object(app,'reconcile',return_value=True):app.SERVICES.sync_runtime()
        self.assertFalse(app.SERVICES.pending_runtime)

    def test_existing_public_viewer_token_is_suspended_then_reusable(self):
        result=self.client.post('/api/viewer-link',json={'enabled':True},headers=self.headers)
        self.assertEqual(result.status_code,200)
        path=urllib.parse.urlsplit(result.json['url']).path
        stored=app.rows('SELECT * FROM viewer_links WHERE user_id=?',(self.user_id,))
        self.toggle('viewers',False)
        self.assertEqual(app.app.test_client().get(path).status_code,403)
        self.assertEqual(app.rows('SELECT * FROM viewer_links WHERE user_id=?',(self.user_id,)),stored)
        self.toggle('viewers',True)
        self.assertEqual(app.app.test_client().get(path).status_code,200)

    def test_all_optional_service_routes_are_blocked_even_for_experts(self):
        cases={'webrtc':('/api/webrtc/ice','/webrtc/3/play/'),
               'playback':('/api/playback/status','/api/clips'),
               'advanced_routing':('/api/routing','/api/scenes'),
               'automation':('/api/automation',),'notifications':('/api/notifications',),
               'youtube':('/api/youtube/broadcasts','/oauth/youtube')}
        for key,paths in cases.items():
            self.toggle(key,False)
            for path in paths:self.assertEqual(self.client.get(path).status_code,403,(key,path))
        self.assertEqual(self.client.get('/api/ingest').status_code,200)
        self.assertEqual(self.client.get('/program/main/').status_code,200)

    def test_webrtc_suspension_closes_sessions_and_program_workers(self):
        sessions=app.FEATURES.rtc_sessions
        previous=dict(sessions);sessions['fixture']=(self.user_id,'csrf','http://localhost/fixture',app.time.monotonic())
        try:
            with patch.object(app.threading,'Thread') as worker,patch.object(app.FEATURES.program_preview,'close') as close:
                self.toggle('webrtc',False)
                self.assertFalse(sessions)
                self.assertTrue(worker.called)
                close.assert_called_once()
            with patch.object(app.FEATURES.program_preview,'start') as start:
                app.FEATURES.program_preview.monitor([self.user],{self.user['prefix']+'webrtc-program':{'readers':[{'id':'fixture'}]}})
                start.assert_not_called()
        finally:sessions.update(previous)

    def test_nested_recording_and_routing_pauses_restore_only_after_both_are_enabled(self):
        result=self.client.post('/api/routing/sources',json={'label':'Fixture camera','protocol':'rtmp'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        key=result.json['key'];name=self.user['prefix']+key
        config=app.yaml.safe_load(app.CONFIG.read_text());config['paths'][name]['record']=True
        app.CONFIG.write_text(app.yaml.safe_dump(config))
        try:
            self.toggle('advanced_routing',False)
            self.assertEqual(self.client.get('/api/ingest/'+key).status_code,403)
            self.assertEqual([row['key'] for row in self.client.get('/api/ingest').json['sources']],['source1','source2'])
            self.assertFalse(app.yaml.safe_load(app.CONFIG.read_text())['paths'][name]['record'])
            self.toggle('recording',False)
            self.toggle('advanced_routing',True)
            self.assertFalse(app.yaml.safe_load(app.CONFIG.read_text())['paths'][name]['record'])
            self.toggle('recording',True)
            self.assertTrue(app.yaml.safe_load(app.CONFIG.read_text())['paths'][name]['record'])
            self.assertEqual(self.client.get('/api/ingest/'+key).status_code,200)
        finally:app.write('DELETE FROM routing_sources WHERE user_id=? AND key=?',(self.user_id,key))

    def test_legacy_empty_prefix_does_not_mask_foreign_recordings(self):
        app.write("UPDATE users SET prefix='' WHERE id=?",(self.user_id,))
        try:
            config=app.yaml.safe_load(app.CONFIG.read_text())
            config['paths']['foreign']={'source':'publisher','record':True}
            app.CONFIG.write_text(app.yaml.safe_dump(config))
            self.toggle('recording',False)
            self.assertTrue(app.yaml.safe_load(app.CONFIG.read_text())['paths']['foreign']['record'])
            self.assertNotIn('foreign',self.json.loads(app.setting('service_paused_recordings','{}')))
        finally:app.write('UPDATE users SET prefix=? WHERE id=?',(self.user['prefix'],self.user_id))

    def test_corrupt_policy_fails_closed_but_admin_can_recover(self):
        app.set_setting('service_policy','not-valid-json')
        self.assertFalse(any(app.SERVICES.flags().values()))
        self.assertEqual(self.client.get('/api/discord').status_code,403)
        self.assertEqual(self.admin.get('/api/admin/services').status_code,200)
        self.toggle('discord',True)
        self.assertTrue(app.SERVICES.enabled('discord'))
        self.assertFalse(app.SERVICES.enabled('youtube'))


class PlaylistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(app.threading,'Thread'):
            cls.uid=app.add_user('playlist_user','Playlist-Fixture-Password-123')
            cls.other=app.add_user('playlist_other','Playlist-Fixture-Password-456')
        app.write('UPDATE videos SET duration=3 WHERE user_id IN (?,?)',(cls.uid,cls.other))

    def setUp(self):
        import json
        self.json=json;self.config=app.CONFIG.read_text()
        self.flags=app.rows("SELECT * FROM settings WHERE name='service_policy'")
        app.write("DELETE FROM settings WHERE name='service_policy'")
        self.user=app.rows('SELECT * FROM users WHERE id=?',(self.uid,))[0]
        self.video=app.rows('SELECT id FROM videos WHERE user_id=?',(self.uid,))[0]['id']
        self.foreign_video=app.rows('SELECT id FROM videos WHERE user_id=?',(self.other,))[0]['id']
        self.client=app.app.test_client();self.headers={'X-CSRF-Token':'playlist-test'}
        with self.client.session_transaction() as session:session.update(uid=self.uid,version=1,csrf='playlist-test',expert_mode=True)

    def tearDown(self):
        for key in list(app.PLAYLISTS.jobs):
            if key[0]==self.uid:app.PLAYLISTS.checkpoint(key,pause=True)
        for table in ('playlist_folders','playlists','playlist_profiles','playlist_positions','playlist_output_state','routing_programs','outputs','output_routing','routing_sources'):
            app.write('DELETE FROM '+table+' WHERE user_id=?',(self.uid,))
        app.write('UPDATE videos SET folder_id=NULL WHERE user_id=?',(self.uid,))
        app.write("UPDATE users SET output='',output_kind='twitch' WHERE id=?",(self.uid,))
        app.CONFIG.write_text(self.config);app.write("DELETE FROM settings WHERE name='service_policy'")
        for row in self.flags:app.write('INSERT INTO settings(name,value) VALUES (?,?)',(row['name'],row['value']))
        app.PLAYLISTS.offline_since={key:value for key,value in app.PLAYLISTS.offline_since.items() if key[0]!=self.uid}

    def post(self,path,body,status=200):
        result=self.client.post(path,json=body,headers=self.headers)
        self.assertEqual(result.status_code,status,result.get_data(as_text=True));return result.json

    def playlist(self,name='Playlist A',items=None):
        return self.post('/api/playlists',{'name':name,'items':items if items is not None else [self.video]})['id']

    def profile(self,**values):
        body=dict(scope='default',enabled=True,auto_start=False,playlist_id=None,delay_seconds=600,timezone='Europe/Berlin',schedules=[])
        body.update(values);return body

    def test_library_is_normal_but_playout_requires_expert_and_csrf(self):
        with self.client.session_transaction() as session:session['expert_mode']=False
        self.playlist()
        self.assertEqual(self.client.get('/api/playlists').status_code,200)
        self.post('/api/playout',self.profile(),403)
        self.assertEqual(self.client.post('/api/playlists',json={'name':'No CSRF'}).status_code,403)

    def test_foreign_media_folders_and_playlists_are_not_usable(self):
        other=app.write('INSERT INTO playlist_folders(user_id,name) VALUES (?,?)',(self.other,'Private'))
        self.post('/api/playlists',{'name':'Foreign media','items':[self.foreign_video]},404)
        self.post('/api/playlists',{'name':'Foreign folder','folder_id':other},404)
        result=self.client.delete('/api/playlist-folders/'+str(other),headers=self.headers)
        self.assertEqual(result.status_code,404)
        self.post('/api/playlists/videos/'+str(self.foreign_video)+'/folder',{'folder_id':None},404)

    def test_folder_cycle_nonempty_delete_and_names(self):
        first=self.post('/api/playlist-folders',{'name':'Archiv'})['id']
        second=self.post('/api/playlist-folders',{'name':'Nacht','parent_id':first})['id']
        self.post('/api/playlist-folders/'+str(first),{'name':'Archiv','parent_id':second},400)
        self.assertEqual(self.client.delete('/api/playlist-folders/'+str(first),headers=self.headers).status_code,409)
        self.post('/api/playlist-folders',{'name':'archiv'},409)
        ident=self.post('/api/playlists',{'name':'Nachtprogramm','folder_id':second,'items':[self.video]})['id']
        self.assertEqual(self.client.delete('/api/playlist-folders/'+str(second),headers=self.headers).status_code,409)
        self.post('/api/playlists/'+str(ident),{'name':'Nachtprogramm','folder_id':first,'items':[self.video]})
        self.assertEqual(self.client.delete('/api/playlist-folders/'+str(second),headers=self.headers).status_code,200)

    def test_playlist_order_duplicates_and_revision(self):
        ident=self.playlist(items=[self.video,self.video])
        self.post('/api/playlists/'+str(ident),{'name':'Renamed','items':[self.video,self.video]})
        row=app.rows('SELECT * FROM playlists WHERE id=?',(ident,))[0]
        self.assertEqual(row['revision'],1);self.assertEqual(self.json.loads(row['items']),[self.video,self.video])
        self.post('/api/playlists/'+str(ident),{'name':'Renamed','items':[self.video]})
        self.assertEqual(app.rows('SELECT revision FROM playlists WHERE id=?',(ident,))[0]['revision'],2)

    def test_live_preempts_and_resets_outage_delay(self):
        ident=self.playlist();self.post('/api/playout',self.profile(playlist_id=ident))
        program=app.MODEL.program(self.user)
        _,eligible=app.PLAYLISTS.decision(self.user,program,False,True,1000);self.assertFalse(eligible)
        _,eligible=app.PLAYLISTS.decision(self.user,program,False,True,1599);self.assertFalse(eligible)
        _,eligible=app.PLAYLISTS.decision(self.user,program,False,True,1600);self.assertTrue(eligible)
        _,eligible=app.PLAYLISTS.decision(self.user,program,True,True,1601);self.assertFalse(eligible)
        _,eligible=app.PLAYLISTS.decision(self.user,program,False,True,1602);self.assertFalse(eligible)

    def test_own_output_rules_split_shared_program_and_keep_identity_on_edit(self):
        a=self.playlist();b=self.playlist('Playlist B')
        before=app.MODEL.output_program(self.user,'twitch')['id'];self.assertEqual(before,'main')
        self.post('/api/playout',self.profile(scope='output:twitch',playlist_id=a))
        self.post('/api/playout',self.profile(scope='output:youtube',playlist_id=b))
        twitch=app.MODEL.output_program(self.user,'twitch');youtube=app.MODEL.output_program(self.user,'youtube')
        self.assertNotEqual(twitch['id'],youtube['id']);self.assertNotEqual(twitch['id'],'main')
        self.assertEqual(app.PLAYLISTS.plan(self.user,twitch)['playlist']['id'],a)
        self.assertEqual(app.PLAYLISTS.plan(self.user,youtube)['playlist']['id'],b)
        self.post('/api/playout',self.profile(scope='output:twitch',playlist_id=b,delay_seconds=0))
        self.assertEqual(app.MODEL.output_program(self.user,'twitch')['id'],twitch['id'])

    def test_source2_and_extra_source_profiles_keep_fixed_sources(self):
        ident=self.playlist();self.post('/api/playout',self.profile(scope='source:source1',playlist_id=ident),400)
        self.post('/api/playout',self.profile(scope='source:source2',playlist_id=ident))
        source=self.post('/api/routing/sources',{'label':'Camera 3','protocol':'rtmp'})['key']
        self.post('/api/playout',self.profile(scope='source:'+source,playlist_id=ident))
        self.assertEqual([row['key'] for row in app.MODEL.sources(self.user)[:2]],['source1','source2'])
        self.assertEqual(app.PLAYLISTS.plan(self.user,app.MODEL.program(self.user))['profile']['scope'],'source:source2')

    def test_daily_schedule_midnight_and_daylight_saving(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from playlist_features import active_schedule
        rules=[dict(playlist_id=1,start='12:00',end='00:00',days=list(range(7))),dict(playlist_id=2,start='00:00',end='06:00',days=list(range(7))),dict(playlist_id=3,start='06:00',end='12:00',days=list(range(7)))]
        for hour,wanted in ((12,1),(23,1),(0,2),(5,2),(6,3),(11,3)):
            stamp=datetime(2026,10,28,hour,0,tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
            self.assertEqual(active_schedule(rules,'Europe/Berlin',stamp)[0]['playlist_id'],wanted)
        sunday=[dict(playlist_id=1,start='02:00',end='03:00',days=[6])]
        windows=[active_schedule(sunday,'Europe/Berlin',datetime(2026,10,25,2,30,fold=fold,tzinfo=ZoneInfo('Europe/Berlin')).timestamp())[1] for fold in (0,1)]
        self.assertEqual(windows[0],windows[1])

    def test_overlapping_week_boundary_and_invalid_rules_rejected(self):
        ident=self.playlist()
        rules=[dict(playlist_id=ident,start='23:00',end='01:00',days=[6]),dict(playlist_id=ident,start='00:30',end='02:00',days=[0])]
        self.post('/api/playout',self.profile(schedules=rules),409)
        for days in ([True],[{}],[],[7]):
            self.post('/api/playout',self.profile(schedules=[dict(playlist_id=ident,start='00:00',end='06:00',days=days)]),400)
        self.post('/api/playout',self.profile(timezone='bad/timezone'),400)

    def test_zero_delay_schedule_and_output_override(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        ident=self.playlist();self.post('/api/playout',self.profile(playlist_id=ident))
        self.post('/api/playout',self.profile(scope='output:twitch',schedules=[dict(playlist_id=ident,start='00:00',end='00:00',days=list(range(7)))],delay_seconds=600))
        plan,eligible=app.PLAYLISTS.decision(self.user,app.MODEL.output_program(self.user,'twitch'),False,True,500)
        self.assertTrue(eligible);self.assertTrue(plan['scheduled'])

    def test_video_and_assigned_playlist_deletion_are_protected(self):
        ident=self.playlist()
        self.post('/api/videos/'+str(self.video)+'/delete',{},409)
        self.post('/api/playout',self.profile(playlist_id=ident))
        self.assertEqual(self.client.delete('/api/playlists/'+str(ident),headers=self.headers).status_code,409)
        self.post('/api/playout',self.profile())
        self.assertEqual(self.client.delete('/api/playlists/'+str(ident),headers=self.headers).status_code,200)
        self.assertTrue(Path(app.owned_video(self.user,self.video)['path']).is_file())

    def test_progress_position_survives_live_pause_and_restart(self):
        ident=self.playlist(items=[self.video,self.video]);self.post('/api/playout',self.profile(playlist_id=ident,delay_seconds=0))
        program=app.MODEL.program(self.user);plan=app.PLAYLISTS.plan(self.user,program)
        args,_=app.PLAYLISTS.start(self.user,program,plan)
        key=(self.uid,'main');job=app.PLAYLISTS.jobs[key];job['progress'].write_text('out_time_us=4200000\n')
        app.PLAYLISTS.checkpoint(self.uid,pause=True)
        self.assertAlmostEqual(app.rows('SELECT offset FROM playlist_positions WHERE user_id=?',(self.uid,))[0]['offset'],4.2)
        app.PLAYLISTS.start(self.user,program,plan)
        self.assertAlmostEqual(app.PLAYLISTS.jobs[key]['offset'],4.2)
        self.assertIn('-stream_loop',args)
        app.PLAYLISTS.checkpoint(key,pause=True)
        self.post('/api/playlists/'+str(ident),{'name':'Updated','items':[self.video]})
        plan=app.PLAYLISTS.plan(self.user,program);app.PLAYLISTS.start(self.user,program,plan)
        self.assertEqual(app.PLAYLISTS.jobs[key]['offset'],0)

    def test_service_switch_and_automation_pause_preserve_library(self):
        ident=self.playlist();self.post('/api/playout',self.profile(playlist_id=ident,schedules=[dict(playlist_id=ident,start='00:00',end='00:00',days=list(range(7)))]))
        flags=app.SERVICES.flags();flags['automation']=False;app.set_setting('service_policy',self.json.dumps(flags))
        plan=app.PLAYLISTS.plan(self.user,app.MODEL.program(self.user));self.assertFalse(plan['scheduled'])
        flags['playlists']=False;app.set_setting('service_policy',self.json.dumps(flags))
        self.assertEqual(self.client.get('/api/playlists').status_code,403)
        self.assertIsNone(app.PLAYLISTS.plan(self.user,app.MODEL.program(self.user)))
        self.assertTrue(app.rows('SELECT id FROM playlists WHERE id=?',(ident,)))

    def test_automatic_start_respects_manual_stop_and_leaves_manual_output_running(self):
        ident=self.playlist();self.post('/api/playout',self.profile(scope='output:twitch',playlist_id=ident,delay_seconds=0,auto_start=True))
        app.write('INSERT INTO outputs(user_id,kind,endpoint,selected) VALUES (?,?,?,1)',(self.uid,'twitch',app.encrypt('rtmps://fixture.invalid/live#key')))
        program=app.MODEL.output_program(self.user,'twitch');plan=app.PLAYLISTS.plan(self.user,program)
        app.PLAYLISTS.manual_control(self.user,'twitch')
        config=app.yaml.safe_load(app.CONFIG.read_text());config['paths'][app.output_path(self.user,'twitch')]['forward']=[]
        with patch.object(app,'forward') as forward:
            app.PLAYLISTS.automatic(self.user,program,plan,True,config,2000)
            forward.assert_not_called()
        config['paths'][app.output_path(self.user,'twitch')]['forward']=[{'dest':'rtmps://fixture.invalid/live#key'}]
        with patch.object(app,'forward') as forward:
            app.PLAYLISTS.automatic(self.user,program,None,False,config,2001)
            forward.assert_not_called()

    def test_upload_uses_playlist_duration_limit_and_owned_folder(self):
        folder=self.post('/api/playlist-folders',{'name':'Uploads'})['id']
        with patch.object(app.JOBS,'submit') as submit:
            response=self.client.post('/api/playlists/upload',data={'folder_id':str(folder),'video':(io.BytesIO(b'fixture'),'clip.mp4')},headers=self.headers)
            self.assertEqual(response.status_code,200,response.json)
            self.assertEqual(submit.call_args.args[-2:],(7200,folder))
            Path(submit.call_args.args[2]).unlink(missing_ok=True)
        app.UPLOAD_RESERVATIONS.pop(self.uid,None)
        app.write("UPDATE users SET upload_state='ready',upload_message='' WHERE id=?",(self.uid,))

    def test_assigned_playlist_cannot_be_saved_empty(self):
        ident=self.playlist();self.post('/api/playout',self.profile(playlist_id=ident))
        self.post('/api/playlists/'+str(ident),{'name':'Empty','items':[]},409)
        self.assertEqual(self.json.loads(app.rows('SELECT items FROM playlists WHERE id=?',(ident,))[0]['items']),[self.video])

    def test_global_playlist_disable_stops_encoder_and_saves_position(self):
        ident=self.playlist();self.post('/api/playout',self.profile(playlist_id=ident,delay_seconds=0))
        program=app.MODEL.program(self.user);plan=app.PLAYLISTS.plan(self.user,program)
        app.PLAYLISTS.start(self.user,program,plan)
        app.PLAYLISTS.jobs[(self.uid,'main')]['progress'].write_text('out_time_us=1500000\n')
        flags=app.SERVICES.flags();flags['playlists']=False;app.set_setting('service_policy',self.json.dumps(flags))
        app.SERVICES.enforce_local()
        self.assertNotIn((self.uid,'main'),app.PLAYLISTS.jobs)
        self.assertAlmostEqual(app.rows('SELECT offset FROM playlist_positions WHERE user_id=?',(self.uid,))[0]['offset'],1.5)


class UploadManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.object(app.threading,'Thread'):
            cls.uid=app.add_user('upload_user','Uploads-Fixture-Password-123')
            cls.other=app.add_user('upload_other','Uploads-Fixture-Password-456')
        app.write('UPDATE videos SET duration=3 WHERE user_id IN (?,?)',(cls.uid,cls.other))

    def setUp(self):
        self.client=app.app.test_client();self.headers={'X-CSRF-Token':'uploads'}
        with self.client.session_transaction() as session:session.update(uid=self.uid,version=1,csrf='uploads',expert_mode=True)
        self.user=app.rows('SELECT * FROM users WHERE id=?',(self.uid,))[0]
        self.config=app.CONFIG.read_text()
        self.path=app.DATA/'media'/'upload_user'/'fixture-extra.mp4';self.path.write_bytes(b'fixture-file')
        self.vid=app.write('INSERT INTO videos(user_id,name,path,duration,size,created) VALUES (?,?,?,?,?,?)',(self.uid,'Original.mp4',str(self.path),3,12,app.time.time()))
        app.write("UPDATE users SET upload_state='ready',upload_id='' WHERE id=?",(self.uid,))

    def tearDown(self):
        for key in list(app.PLAYLISTS.jobs):
            if key[0]==self.uid:app.PLAYLISTS.jobs.pop(key,None)
        for table in ('video_uploads','playlists','playlist_profiles','playlist_positions','playlist_output_state','routing_programs'):
            app.write('DELETE FROM '+table+' WHERE user_id=?',(self.uid,))
        for row in app.rows('SELECT id,path,rendered FROM videos WHERE user_id=? AND id!=?',(self.uid,self.user['selected_video_id'])):
            for key in ('path','rendered'):
                if row[key]:Path(row[key]).unlink(missing_ok=True)
            app.write('DELETE FROM videos WHERE id=?',(row['id'],))
        app.write("UPDATE users SET upload_state='ready',upload_id='' WHERE id=?",(self.uid,))
        app.UPLOAD_RESERVATIONS.pop(self.uid,None);app.CONFIG.write_text(self.config)

    def job(self,ident='fixture-upload-1234567890'):
        app.UPLOADS.register(self.user,ident,'Original.mp4',12,'playlist',None)
        app.write("UPDATE users SET upload_id=?,upload_state='processing' WHERE id=?",(ident,self.uid))
        return ident

    def test_progress_is_private_and_available_without_expert(self):
        ident=self.job();app.UPLOADS.update(ident,self.uid,'processing',42,'Umwandlung läuft.')
        with self.client.session_transaction() as session:session['expert_mode']=False
        response=self.client.get('/api/uploads/'+ident)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['progress'],42)
        self.assertNotIn('user_id',response.json);self.assertNotIn('path',response.json)
        other=app.app.test_client()
        with other.session_transaction() as session:session.update(uid=self.other,version=1,csrf='other')
        self.assertEqual(other.get('/api/uploads/'+ident).status_code,404)
        self.assertFalse(other.get('/api/uploads').json['jobs'])
        self.assertEqual(self.client.get('/api/status').json['upload']['progress'],42)

    def test_duplicate_upload_request_does_not_schedule_conversion_twice(self):
        ident='repeat-upload-1234567890'
        def send(name='Original.mp4',body=b'fixture'):
            return self.client.post('/api/playlists/upload',data={'upload_id':ident,'video':(io.BytesIO(body),name)},headers=self.headers)
        with patch.object(app.JOBS,'submit') as submit:
            first=send();self.assertEqual(first.status_code,200,first.json)
            second=send();self.assertEqual(second.status_code,200,second.json)
            self.assertEqual(first.json['upload_id'],second.json['upload_id']);self.assertEqual(submit.call_count,1)
            Path(submit.call_args.args[2]).unlink(missing_ok=True)
        self.assertEqual(send('Different.mp4').status_code,409)
        self.assertEqual(len(app.rows('SELECT id FROM video_uploads WHERE user_id=?',(self.uid,))),1)

    def test_rename_keeps_file_playlist_and_position(self):
        import json
        ident=app.write('INSERT INTO playlists(user_id,name,items) VALUES (?,?,?)',(self.uid,'Test playlist',json.dumps([self.vid])))
        app.write('INSERT INTO playlist_positions(user_id,program,playlist_id,revision,offset) VALUES (?,?,?,?,?)',(self.uid,'main',ident,1,1.2))
        app.PLAYLISTS.jobs[(self.uid,'main')]={'user_id':self.uid,'items':[self.vid],'videos':[{'id':self.vid,'name':'Original.mp4'}]}
        response=self.client.post('/api/videos/'+str(self.vid)+'/rename',json={'name':'Neuer Name.mp4'},headers=self.headers)
        self.assertEqual(response.status_code,200,response.json)
        row=app.owned_video(self.user,self.vid);self.assertEqual(row['name'],'Neuer Name.mp4');self.assertEqual(row['path'],str(self.path));self.assertTrue(self.path.exists())
        media=self.client.get('/media/video/'+str(self.vid));self.assertIn('Neuer Name.mp4',media.headers.get('Content-Disposition',''));media.close()
        self.assertEqual(app.rows('SELECT revision,items FROM playlists WHERE id=?',(ident,))[0],{'revision':1,'items':json.dumps([self.vid])})
        self.assertEqual(app.rows('SELECT offset FROM playlist_positions WHERE user_id=?',(self.uid,))[0]['offset'],1.2)
        self.assertEqual(app.PLAYLISTS.jobs[(self.uid,'main')]['videos'][0]['name'],'Neuer Name.mp4')

    def test_rename_rejects_foreign_invalid_names_and_missing_csrf(self):
        foreign=app.rows('SELECT id FROM videos WHERE user_id=?',(self.other,))[0]['id']
        self.assertEqual(self.client.post('/api/videos/'+str(foreign)+'/rename',json={'name':'No'},headers=self.headers).status_code,404)
        for name in ('','a'*121,'bad\nname',None):
            self.assertEqual(self.client.post('/api/videos/'+str(self.vid)+'/rename',json={'name':name},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/api/videos/'+str(self.vid)+'/rename',json={'name':'No'}).status_code,403)

    def test_deletion_removes_confirmed_playlist_references(self):
        import json
        ident=app.write('INSERT INTO playlists(user_id,name,items) VALUES (?,?,?)',(self.uid,'Test playlist',json.dumps([self.vid,self.user['selected_video_id'],self.vid])))
        data=self.client.get('/api/playlists').json
        video=next(row for row in data['videos'] if row['id']==self.vid)
        self.assertTrue(video['can_delete']);self.assertEqual(video['in_playlists'],['Test playlist'])
        path='/api/videos/'+str(self.vid)+'/delete'
        self.assertEqual(self.client.post(path,json={},headers=self.headers).status_code,409)
        self.assertEqual(self.client.post(path,json={'remove_from_playlists':True},headers=self.headers).status_code,200)
        self.assertFalse(self.path.exists())
        self.assertEqual(json.loads(app.rows('SELECT items FROM playlists WHERE id=?',(ident,))[0]['items']),[self.user['selected_video_id']])
        self.assertEqual(app.rows('SELECT revision FROM playlists WHERE id=?',(ident,))[0]['revision'],2)

    def test_active_and_last_assigned_videos_are_protected(self):
        import json
        ident=app.write('INSERT INTO playlists(user_id,name,items) VALUES (?,?,?)',(self.uid,'Assigned',json.dumps([self.vid])))
        app.write('INSERT INTO playlist_profiles(user_id,scope,playlist_id) VALUES (?,?,?)',(self.uid,'default',ident))
        result=self.client.post('/api/videos/'+str(self.vid)+'/delete',json={'remove_from_playlists':True},headers=self.headers)
        self.assertEqual(result.status_code,409);self.assertTrue(self.path.exists())
        details=next(row for row in self.client.get('/api/playlists').json['videos'] if row['id']==self.vid)
        self.assertFalse(details['can_delete']);self.assertIn('Letztes Video',details['delete_reason'])
        app.PLAYLISTS.jobs[(self.uid,'main')]={'user_id':self.uid,'items':[self.vid],'videos':[]}
        self.assertEqual(self.client.post('/api/videos/'+str(self.vid)+'/delete',json={'remove_from_playlists':True},headers=self.headers).status_code,409)

    def test_upload_does_not_block_deleting_unrelated_idle_media(self):
        self.job()
        self.assertEqual(self.client.post('/api/videos/'+str(self.vid)+'/delete',json={},headers=self.headers).status_code,200)
        self.assertFalse(self.path.exists())

    def test_encoder_reports_measured_progress_and_caps_completion(self):
        ident=self.job()
        code="print('out_time_us=2500000');print('out_time_us=11000000')"
        app.UPLOADS.encode([sys.executable,'-c',code],self.uid,ident,10,5)
        job=app.UPLOADS.get(self.user,ident)
        self.assertEqual(job['state'],'processing');self.assertEqual(job['progress'],99)
        self.assertIsNone(job['video_id'])
        app.UPLOADS.update(ident,self.uid,'ready',100,'Fertig',self.vid)
        self.assertEqual(app.UPLOADS.get(self.user,ident)['progress'],100)

    def test_encoder_timeout_is_enforced(self):
        ident=self.job();started=app.time.monotonic()
        with self.assertRaises(app.Error):app.UPLOADS.encode([sys.executable,'-c','import time;time.sleep(5)'],self.uid,ident,5,.1)
        self.assertLess(app.time.monotonic()-started,2)

    def test_interrupted_jobs_are_recoverable_with_error_status(self):
        ident=self.job();app.UPLOADS.update(ident,self.uid,'processing',55,'Running')
        app.UPLOADS.recover();job=app.UPLOADS.get(self.user,ident)
        self.assertEqual(job['state'],'error');self.assertEqual(job['progress'],55)
        self.assertIn('Serverneustart',job['message'])

    def test_video_metadata_endpoint_is_private_and_has_no_storage_paths(self):
        response=self.client.get('/api/videos/'+str(self.vid))
        self.assertEqual(response.status_code,200);self.assertTrue(response.json['can_delete'])
        self.assertNotIn('path',response.json);self.assertNotIn('user_id',response.json)
        foreign=app.rows('SELECT id FROM videos WHERE user_id=?',(self.other,))[0]['id']
        self.assertEqual(self.client.get('/api/videos/'+str(foreign)).status_code,404)
