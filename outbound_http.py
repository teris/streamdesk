"""Direct public TLS connections with DNS pinning and no HTTP redirects."""
from contextlib import contextmanager
import http.client
import ipaddress
import smtplib
import socket
import ssl
import urllib.parse


def public_addresses(host, port, resolver, blocked=()):
    addresses = sorted(resolver(host, port))
    if not addresses or any(not ipaddress.ip_address(address).is_global or address in blocked for address in addresses):
        raise ValueError('Nur öffentliche Zieladressen sind zulässig.')
    return addresses


def connect_tls(host, port, timeout, context, resolver, blocked):
    # Resolve once; the actual TCP socket uses this checked IP, TLS still verifies
    # the original hostname and sends its SNI. Environment proxies are not used.
    addresses = public_addresses(host, port, resolver, blocked)
    last_error = None
    for address in addresses:
        raw = None
        try:
            raw = socket.create_connection((address, port), timeout=timeout)
            return context.wrap_socket(raw, server_hostname=host)
        except OSError as error:
            if raw is not None:
                raw.close()
            last_error = error
    raise last_error or OSError('Ziel nicht erreichbar.')


class PublicHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, port, *, resolver, blocked, timeout):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self.resolver, self.blocked = resolver, blocked

    def connect(self):
        self.sock = connect_tls(self.host, self.port, self.timeout, self._context, self.resolver, self.blocked)


@contextmanager
def open_public_https(url, *, resolver, blocked=(), data=None, headers=None, method='POST', timeout=10):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Ungültige HTTPS-Adresse.')
    connection = PublicHTTPSConnection(parsed.hostname, parsed.port or 443,
                                       resolver=resolver, blocked=blocked, timeout=timeout)
    response = None
    try:
        path = urllib.parse.urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
        connection.request(method, path, body=data, headers=headers or {})
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise OSError('Das Ziel hat die Anfrage abgelehnt.')
        yield response
    finally:
        if response is not None:
            response.close()
        connection.close()


class PublicSMTP(smtplib.SMTP_SSL):
    def __init__(self, *args, resolver, blocked=(), **kwargs):
        self.resolver, self.blocked = resolver, blocked
        super().__init__(*args, **kwargs)

    def _get_socket(self, host, port, timeout):
        return connect_tls(host, port, timeout, self.context, self.resolver, self.blocked)
