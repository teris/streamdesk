import copy
import re
import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from media_config import merge_auth, outside_namespace, service_acl, synchronize_runtime


class MediaConfigTests(unittest.TestCase):
    def base(self):
        return {'authMethod': 'internal', 'paths': {'camera': {'source': 'publisher', 'record': False}, 'all_others': {}},
                'authInternalUsers': [{'user': 'any', 'pass': '', 'ips': [], 'permissions': [{'action': 'publish', 'path': ''}, {'action': 'read', 'path': ''}]},
                                      {'user': 'camera-reader', 'pass': 'test-only-fixture', 'ips': [], 'permissions': [{'action': 'read', 'path': 'camera'}]}]}

    def test_complement_matches_every_non_namespace_prefix(self):
        for namespace in ('streamdesk', 'sd-test', 'x', 'studio_2'):
            expression = re.compile(outside_namespace(namespace)[1:])
            for path in ('camera', 'camera/sub', namespace, '', 'other/' + namespace, 'a/' + namespace + '/admin', namespace + 'other/path'):
                self.assertIsNotNone(expression.fullmatch(path), path)
            for path in (namespace + '/', namespace + '/admin/source1', namespace + '/test/live'):
                self.assertIsNone(expression.fullmatch(path), path)

    def test_preserves_foreign_paths_and_named_accounts(self):
        config = self.base()
        before = copy.deepcopy(config)
        merge_auth(config, 'streamdesk', [])
        self.assertEqual(config['paths'], before['paths'])
        self.assertEqual(config['authInternalUsers'][1], before['authInternalUsers'][1])
        self.assertEqual(config['authInternalUsers'][0]['permissions'][0]['path'], outside_namespace('streamdesk'))

    def test_minimal_config_keeps_media_server_default_access_outside_namespace(self):
        config = {'paths': {'camera': {'source': 'publisher'}}}
        merge_auth(config, 'streamdesk', [])
        inherited = config['authInternalUsers'][0]
        self.assertEqual(inherited['user'], 'any')
        self.assertEqual(inherited['permissions'][0]['path'], outside_namespace('streamdesk'))
        self.assertTrue(any(p['action'] == 'api' for p in config['authInternalUsers'][1]['permissions']))

    def test_idempotent_and_managed_users_are_replaced(self):
        config = self.base()
        managed = {'user': 'streamdesk_streamdesk_admin', 'pass': 'fixture-only', 'ips': [], 'permissions': [{'action': 'publish', 'path': 'streamdesk/admin/source1'}]}
        merge_auth(config, 'streamdesk', [managed])
        once = copy.deepcopy(config)
        merge_auth(config, 'streamdesk', [managed])
        self.assertEqual(config, once)
        merge_auth(config, 'streamdesk', [])
        self.assertFalse(any(u['user'] == managed['user'] for u in config['authInternalUsers']))
        self.assertEqual(sum(u == service_acl('streamdesk') for u in config['authInternalUsers']), 1)

    def test_runtime_sync_only_adds_managed_paths_and_preserves_active_foreign_paths(self):
        calls = []
        config = {'authInternalUsers': [], 'paths': {'camera': {'source': 'publisher'}, 'streamdesk/admin/source1': {'source': 'publisher'}}}
        def api(path, value=None, method=None):
            calls.append((path, value, method))
            if path == 'config/global/get':
                return {'authInternalUsers': []}
            if path.startswith('config/paths/list'):
                return {'items': [{'name': 'camera', 'source': 'publisher'}]}
            return {}
        synchronize_runtime(api, config, 'streamdesk')
        mutations = [c for c in calls if c[1] is not None]
        self.assertEqual([c[0] for c in mutations], ['config/paths/add/streamdesk/admin/source1'])

    def test_rejects_anonymous_public_control_api(self):
        config = self.base()
        config['authInternalUsers'][0]['permissions'].append({'action':'api','path':''})
        with self.assertRaises(ValueError):
            merge_auth(config, 'streamdesk', [])

    def test_rejects_external_auth_and_unbounded_custom_regex(self):
        config = self.base()
        config['authMethod'] = 'jwt'
        with self.assertRaises(ValueError):
            merge_auth(config, 'streamdesk', [])
        config = self.base()
        config['authInternalUsers'][0]['permissions'][0]['path'] = '~.*'
        with self.assertRaises(ValueError):
            merge_auth(config, 'streamdesk', [])

    def test_service_acl_survives_local_ip_changes(self):
        config = self.base()
        merge_auth(config, 'streamdesk', [], local_ips=('127.0.0.1', '::1'))
        merge_auth(config, 'streamdesk', [], local_ips=('127.0.0.1', '::1', '10.0.0.5'))
        expected = service_acl('streamdesk', ('127.0.0.1', '::1', '10.0.0.5'))
        matches = [u for u in config['authInternalUsers'] if u == expected]
        self.assertEqual(len(matches), 1)
        stale = service_acl('streamdesk', ('127.0.0.1', '::1'))
        self.assertFalse(any(u == stale for u in config['authInternalUsers']))


if __name__ == '__main__':
    unittest.main()
