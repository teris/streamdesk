"""Version-aware MediaMTX HTTP client shared by local and remote deployments."""
import json
import re
import ssl
import urllib.error
import urllib.request


class MediaMTXClientError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


SUPPORTED_MEDIA_VERSIONS = {(1, 21)}


def parse_media_version(value):
    """Return a strict semantic MediaMTX version tuple from CLI/API output."""
    match = re.search(r'(?:\bv)?(\d+)\.(\d+)\.(\d+)(?:\b|[-+])', str(value))
    if not match:
        raise MediaMTXClientError('MediaMTX-Version konnte nicht erkannt werden')
    return tuple(map(int, match.groups()))


def compatibility(version):
    """Describe a tested API/YAML contract. Unknown majors fail closed."""
    try:
        version = parse_media_version(version) if isinstance(version, str) else tuple(version)
        if len(version) != 3 or any(type(part) is not int or part < 0 for part in version):
            raise ValueError()
    except (TypeError,ValueError):
        raise MediaMTXClientError('MediaMTX-Version konnte nicht erkannt werden') from None
    if version[:2] not in SUPPORTED_MEDIA_VERSIONS or version < (1, 21, 3):
        raise MediaMTXClientError(
            f'MediaMTX {version[0]}.{version[1]}.{version[2]} besitzt kein freigegebenes StreamDesk-Kompatibilitätsprofil')
    return {
        'major': version[0], 'api': 'v3', 'config_schema': '1.21',
        'auth': ('internal',), 'recording': True,
        'playback': True, 'forwarding': True,
    }


class MediaMTXClient:
    def __init__(self, base_url, cafile=None, timeout=8, version=None):
        self.base_url = base_url.rstrip('/') + '/'
        self.timeout = timeout
        self.capabilities = compatibility(version) if version is not None else None
        self.context = ssl.create_default_context(cafile=cafile or None) if self.base_url.startswith('https://') else None

    def inspect(self):
        """Probe the instance and bind this client to a tested contract."""
        info = self.call('info')
        if not isinstance(info, dict):
            raise MediaMTXClientError('Ungültige MediaMTX-Versionsantwort')
        value = info.get('version') or info.get('Version')
        self.capabilities = compatibility(value)
        return dict(self.capabilities, version='.'.join(map(str, parse_media_version(value))))

    def call(self, path, value=None, method=None):
        operation = method or ('PATCH' if value is not None else 'GET')
        if operation.upper() not in ('GET', 'HEAD') and self.capabilities is None:
            self.inspect()
        data = json.dumps(value).encode() if value is not None else None
        request = urllib.request.Request(
            self.base_url + path.lstrip('/'), data=data,
            headers={'Content-Type': 'application/json'},
            method=operation)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
                content = response.read()
                return json.loads(content) if content else {}
        except urllib.error.HTTPError as error:
            raise MediaMTXClientError('MediaMTX meldet HTTP ' + str(error.code), error.code) from None
        except (OSError, ValueError) as error:
            raise MediaMTXClientError('MediaMTX ist nicht erreichbar') from error
