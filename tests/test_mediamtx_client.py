import json
import unittest
from unittest.mock import patch

from mediamtx_client import MediaMTXClient, MediaMTXClientError, compatibility, parse_media_version


class Response:
    def __init__(self, body=b'{}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def read(self):
        return self.body


class MediaMTXClientTests(unittest.TestCase):
    def test_version_contract_accepts_only_certified_profile(self):
        self.assertEqual(parse_media_version('MediaMTX v1.21.3'), (1, 21, 3))
        self.assertEqual(compatibility('v1.21.9')['api'], 'v3')
        for value in ('v1.20.9', 'v1.22.0', 'v2.0.0'):
            with self.subTest(value=value), self.assertRaises(MediaMTXClientError):
                compatibility(value)

    def test_inspects_info_before_binding_capabilities(self):
        client = MediaMTXClient('http://127.0.0.1:9997/v3/')
        with patch('mediamtx_client.urllib.request.urlopen',
                   return_value=Response(b'{"version":"v1.21.3"}')):
            self.assertEqual(client.inspect()['config_schema'], '1.21')

    def test_builds_versioned_request_without_losing_patch_body(self):
        client = MediaMTXClient('https://media.example/v3/', timeout=3, version='1.21.3')
        with patch('mediamtx_client.urllib.request.urlopen', return_value=Response(b'{"ok":true}')) as send:
            self.assertEqual(client.call('/config/global/patch', {'metrics': True}), {'ok': True})
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, 'https://media.example/v3/config/global/patch')
        self.assertEqual(request.method, 'PATCH')
        self.assertEqual(json.loads(request.data), {'metrics': True})
        self.assertEqual(send.call_args.kwargs['timeout'], 3)

    def test_connection_errors_are_normalized(self):
        client = MediaMTXClient('http://127.0.0.1:9997/v3/')
        with patch('mediamtx_client.urllib.request.urlopen', side_effect=OSError('fixture')):
            with self.assertRaises(MediaMTXClientError):
                client.call('config/global/get')

    def test_unknown_version_prevents_any_write(self):
        client=MediaMTXClient('http://127.0.0.1:9997/v3/')
        with patch('mediamtx_client.urllib.request.urlopen',return_value=Response(b'{"version":"v2.0.0"}')) as send:
            with self.assertRaises(MediaMTXClientError):
                client.call('config/global/patch',{'webrtc':True})
        self.assertEqual(send.call_count,1)
        self.assertEqual(send.call_args.args[0].method,'GET')

    def test_missing_or_invalid_version_is_normalized(self):
        for value in (None,(),(1,21),('1',21,3),True):
            with self.subTest(value=value),self.assertRaises(MediaMTXClientError):
                compatibility(value)
