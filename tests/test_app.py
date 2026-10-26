import os
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


if __name__ == '__main__':
    unittest.main()
