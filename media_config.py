"""Merge the StreamDesk namespace without replacing foreign paths or users."""
import re

MEDIA_ACTIONS = {'publish', 'read', 'playback'}


def default_internal_users():
    # MediaMTX v1.x defaults when authInternalUsers is absent from a minimal YAML.
    return [
        {'user': 'any', 'pass': '', 'ips': [], 'permissions': [{'action': a, 'path': ''} for a in ('publish', 'read', 'playback')]},
        {'user': 'any', 'pass': '', 'ips': ['127.0.0.1', '::1'], 'permissions': [{'action': a, 'path': ''} for a in ('api', 'metrics', 'pprof')]},
    ]


def outside_namespace(namespace):
    """RE2-compatible complement of '<namespace>/' (Go RE2 has no lookahead)."""
    prefix = namespace + '/'
    alternatives = [re.escape(prefix[:i]) + '[^' + re.escape(char) + '].*' for i, char in enumerate(prefix)]
    alternatives += [re.escape(prefix[:i]) for i in range(len(prefix))]
    return '~^(?:' + '|'.join(alternatives) + ')$'


def service_acl(namespace, local_ips=('127.0.0.1', '::1')):
    return {'user': 'any', 'pass': '', 'ips': list(local_ips), 'permissions': [
        {'action': 'api', 'path': ''},
        {'action': 'publish', 'path': '~^' + re.escape(namespace) + '/'},
        {'action': 'read', 'path': '~^' + re.escape(namespace) + '/'},
    ]}


def is_service_acl(entry, namespace):
    """Recognize our local service ACL even after STREAMDESK_LOCAL_IPS changes."""
    if entry.get('user') != 'any' or (entry.get('pass') or ''):
        return False
    expected = {
        ('api', ''),
        ('publish', '~^' + re.escape(namespace) + '/'),
        ('read', '~^' + re.escape(namespace) + '/'),
    }
    actual = {(p.get('action'), p.get('path') or '') for p in entry.get('permissions') or []}
    return actual == expected


def merge_auth(config, namespace, managed_users, local_ips=('127.0.0.1', '::1')):
    if config.get('authMethod', 'internal') != 'internal':
        raise ValueError('Diese Version benötigt interne MediaMTX-Authentifizierung. HTTP/JWT wird nicht automatisch ersetzt.')
    outside = outside_namespace(namespace)
    own_prefix = 'streamdesk_' + namespace + '_'
    service = service_acl(namespace, local_ips)
    inherited = []
    existing = (config.get('authInternalUsers') or []) if 'authInternalUsers' in config else default_internal_users()
    for original in existing:
        if original.get('user', '').startswith(own_prefix) or is_service_acl(original, namespace):
            continue
        if original.get('user') == 'any' and not original.get('ips') and any(p.get('action') == 'api' for p in original.get('permissions', [])):
            raise ValueError('Anonymer globaler Control-API-Zugriff muss vor dem Einbinden auf lokale Adressen beschränkt werden.')
        user = dict(original)
        user['pass'] = user.get('pass') or ''
        user['ips'] = user.get('ips') or []
        permissions = []
        for original_permission in original.get('permissions', []):
            permission = dict(original_permission)
            path = permission.get('path') or ''
            permission['path'] = path
            if permission.get('action') in MEDIA_ACTIONS:
                if not path:
                    permission['path'] = outside
                elif path.startswith('~') and path != outside:
                    raise ValueError('Bestehende Regex-Medienberechtigungen müssen vor dem Einbinden auf konkrete Pfade beschränkt werden: ' + str(original.get('user', '')))
                elif path.startswith(namespace + '/'):
                    raise ValueError('Der gewählte Namensbereich wird bereits von bestehenden Medienberechtigungen verwendet.')
            permissions.append(permission)
        user['permissions'] = permissions
        inherited.append(user)
    config['authMethod'] = 'internal'
    config['authInternalUsers'] = inherited + [service] + list(managed_users)
    return config


def contains_settings(actual, expected):
    """Compare explicit YAML fields with the API's expanded default values."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(contains_settings(actual.get(key), value) for key, value in expected.items())
    if isinstance(expected, list):
        if actual is None and not expected:
            return True
        return isinstance(actual, list) and len(actual) == len(expected) and all(contains_settings(a, b) for a, b in zip(actual, expected))
    return actual == expected


def synchronize_runtime(call, config, namespace):
    """Apply only managed changes; fast consecutive atomic file writes can coalesce."""
    from urllib.parse import quote
    current = call('config/global/get')
    users = config.get('authInternalUsers', [])
    if not contains_settings(current.get('authInternalUsers'), users):
        call('config/global/patch', {'authInternalUsers': users}, method='PATCH')
    existing = {item['name']: item for item in call('config/paths/list?itemsPerPage=1000').get('items', [])}
    for name, settings in config.get('paths', {}).items():
        if not name.startswith(namespace + '/'):
            continue
        path = quote(name, safe='/')
        if name not in existing:
            call('config/paths/add/' + path, settings, method='POST')
        elif not contains_settings(existing[name], settings):
            call('config/paths/patch/' + path, settings, method='PATCH')
