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


def service_acl(namespace, local_ips=('127.0.0.1', '::1'), owned_paths=()):
    return {'user': 'any', 'pass': '', 'ips': list(local_ips), 'permissions': [
        {'action': 'api', 'path': ''},
        {'action': 'metrics', 'path': ''},
        {'action': 'publish', 'path': '~^' + re.escape(namespace) + '/'},
        {'action': 'read', 'path': '~^' + re.escape(namespace) + '/'},
    ] + [{'action':action,'path':path} for path in sorted(set(owned_paths)) for action in ('publish','read') if path]}


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
    extra=actual-(expected | {('metrics','')})
    return expected<=actual and all(action in ('publish','read') and path and not path.startswith('~') for action,path in extra)


def merge_auth(config, namespace, managed_users, local_ips=('127.0.0.1', '::1'), owned_paths=()):
    if config.get('authMethod', 'internal') != 'internal':
        raise ValueError('Diese Version benötigt interne MediaMTX-Authentifizierung. HTTP/JWT wird nicht automatisch ersetzt.')
    outside = outside_namespace(namespace)
    own_prefix = 'streamdesk_' + namespace + '_'
    service = service_acl(namespace, local_ips, owned_paths)
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


def list_items(call, endpoint):
    items, page = [], 0
    while True:
        result = call(endpoint+'?itemsPerPage=1000'+('&page='+str(page) if page else ''))
        items.extend(result.get('items', []))
        page += 1
        if page >= result.get('pageCount', 1):
            return items
        if page > 10000:
            raise ValueError('Ungültige Seitenzahl der MediaMTX-API.')


def synchronize_runtime(call, config, namespace, obsolete_paths=(), owned_paths=()):
    """Apply only managed changes; fast consecutive atomic file writes can coalesce."""
    from urllib.parse import quote
    explicit=set(owned_paths)
    current = call('config/global/get')
    users = config.get('authInternalUsers', [])
    if not contains_settings(current.get('authInternalUsers'), users):
        call('config/global/patch', {'authInternalUsers': users}, method='PATCH')
    existing = {item['name']: item for item in list_items(call,'config/paths/list')}
    for name in obsolete_paths:
        if not (name.startswith(namespace + '/') or name in explicit) or name in config.get('paths', {}) or name not in existing:
            continue
        try:
            call('config/paths/delete/' + quote(name, safe='/'), method='DELETE')
        except Exception as error:
            if getattr(error, 'status', None) != 404:
                raise
    for name, settings in config.get('paths', {}).items():
        if not (name.startswith(namespace + '/') or name in explicit):
            continue
        path = quote(name, safe='/')
        if name not in existing:
            try:
                call('config/paths/add/' + path, settings, method='POST')
            except Exception as error:
                if getattr(error, 'status', None) != 400:
                    raise
                # The file watcher can add the path between our list and POST.
                refreshed = {item['name']: item for item in list_items(call,'config/paths/list')}
                if name not in refreshed:
                    raise
                if not contains_settings(refreshed[name], settings):
                    call('config/paths/patch/' + path, settings, method='PATCH')
        elif not contains_settings(existing[name], settings):
            call('config/paths/patch/' + path, settings, method='PATCH')
