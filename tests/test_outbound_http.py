import io
import unittest
from unittest.mock import MagicMock, patch

from outbound_http import connect_tls, open_public_https, public_addresses, PublicSMTP


class OutboundHTTPTests(unittest.TestCase):
    def test_private_and_mixed_dns_answers_are_rejected_before_connect(self):
        for addresses in ({'127.0.0.1'}, {'1.1.1.1','10.0.0.1'}, {'::1'}, set()):
            with self.subTest(addresses=addresses), self.assertRaises(ValueError):
                public_addresses('example.com',443,lambda *_:addresses)
        with self.assertRaises(ValueError):
            public_addresses('example.com',443,lambda *_:{'1.1.1.1'},{'1.1.1.1'})

    def test_tls_uses_checked_address_with_original_hostname(self):
        raw=MagicMock();context=MagicMock()
        with patch('outbound_http.socket.create_connection',return_value=raw) as connect:
            result=connect_tls('export.example',443,5,context,lambda *_:{'1.1.1.1'},set())
        connect.assert_called_once_with(('1.1.1.1',443),timeout=5)
        context.wrap_socket.assert_called_once_with(raw,server_hostname='export.example')
        self.assertIs(result,context.wrap_socket.return_value)

    def test_http_redirect_never_forwards_body_or_credentials(self):
        connection=MagicMock();connection.getresponse.return_value.status=307
        with patch('outbound_http.PublicHTTPSConnection',return_value=connection),self.assertRaises(OSError):
            with open_public_https('https://public.example/upload',resolver=lambda *_:{'1.1.1.1'},
                                   data=io.BytesIO(b'private'),headers={'Authorization':'Basic fixture'},method='PUT'):
                self.fail('A redirect must not be returned as success')
        self.assertEqual(connection.request.call_count,1)
        connection.close.assert_called_once()

    def test_streaming_request_retains_body_object(self):
        connection=MagicMock();connection.getresponse.return_value.status=201
        content=io.BytesIO(b'video')
        with patch('outbound_http.PublicHTTPSConnection',return_value=connection):
            with open_public_https('https://public.example/file.mp4',resolver=lambda *_:{'1.1.1.1'},
                                   data=content,method='PUT',headers={'Content-Length':'5'}) as response:
                self.assertEqual(response.status,201)
        self.assertIs(connection.request.call_args.kwargs['body'],content)

    def test_smtp_uses_the_verified_ssl_context_and_pinned_connector(self):
        import ssl
        context=ssl.create_default_context()
        resolver=lambda *_:{'1.1.1.1'}
        smtp=PublicSMTP(context=context,resolver=resolver,local_hostname='unit.local')
        with patch('outbound_http.connect_tls',return_value='fixture-socket') as connect:
            self.assertEqual(smtp._get_socket('smtp.example',465,3),'fixture-socket')
        connect.assert_called_once_with('smtp.example',465,3,context,resolver,())
