"""Explicit MediaMTX authentication strategy changes with reversible settings."""
import copy
import urllib.parse


AUTH_KEYS = (
    'authMethod', 'authInternalUsers', 'authHTTPAddress', 'authHTTPExclude',
    'authJWTJWKS', 'authJWTClaimKey', 'authJWTExclude')
SERVICE_EXCLUDES = []


def snapshot(config):
    return {key: copy.deepcopy(config[key]) for key in AUTH_KEYS if key in config}


def restore(config, previous):
    for key in AUTH_KEYS:
        config.pop(key, None)
    config.update(copy.deepcopy(previous))
    return config


def configure(config, method, *, address='', claim_key='mediamtx_permissions'):
    if method not in ('internal', 'http', 'jwt'):
        raise ValueError('Unbekannte Authentifizierungsstrategie.')
    previous = snapshot(config)
    for key in ('authHTTPAddress', 'authHTTPExclude', 'authJWTJWKS', 'authJWTClaimKey', 'authJWTExclude'):
        config.pop(key, None)
    config['authMethod'] = method
    if method == 'http':
        parsed = urllib.parse.urlsplit(address)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('HTTP-Authentifizierung benötigt eine HTTPS-URL ohne Zugangsdaten.')
        config['authHTTPAddress'] = address
        config['authHTTPExclude'] = copy.deepcopy(SERVICE_EXCLUDES)
    elif method == 'jwt':
        parsed = urllib.parse.urlsplit(address)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('JWT-Authentifizierung benötigt eine HTTPS-JWKS-URL.')
        if not claim_key or len(claim_key) > 128:
            raise ValueError('Ungültiger JWT-Claim-Schlüssel.')
        config['authJWTJWKS'] = address
        config['authJWTClaimKey'] = claim_key
        config['authJWTExclude'] = copy.deepcopy(SERVICE_EXCLUDES)
    return previous
