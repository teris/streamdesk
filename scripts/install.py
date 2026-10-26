#!/usr/bin/env python3
"""Native Debian installer. Never deletes application data or foreign media paths."""
import argparse
import datetime
import getpass
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import grp
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

SOURCE = Path(__file__).resolve().parents[1]
VERSION = '1.0.0'
MEDIA_VERSION = '1.21.3'
MEDIA_DIGESTS = {
    'amd64': '0a2ea7eba96023631efa1bea7804823a9145b043b6646a8a05798d4ac24ed635',
    'arm64': '27f038237cb5f77a724f6afc58eca2798f2bc4edf9989895631a80eeb41a4fe2',
}
FILES = ['app.py', 'integrations.py', 'media_config.py', 'browser_overlay.py', 'bootstrap.py',
         'gunicorn.conf.py', 'requirements.txt', 'stream_list.proto', 'stream_list_pb2.py',
         'stream_list_pb2_grpc.py', 'README.md', 'INSTALL.md', 'LICENSE', 'NOTICE', 'LICENSE.youtube-sample.txt', 'VERSION', 'install.sh', 'uninstall.sh', '.env.example', 'CHANGELOG.md', 'FEATURE.md', 'THIRD_PARTY.md', 'SECURITY.md', 'CONTRIBUTING.md', 'TESTING.md']


def run(command, **kwargs):
    return subprocess.run([str(x) for x in command], check=True, **kwargs)


def load_env(path):
    values = {}
    if Path(path).is_file():
        for line in Path(path).read_text().splitlines():
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            values[key] = json.loads(value) if value.startswith('"') else value
    return values


def write_private(path, value, mode=0o600, owner=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.streamdesk-')
    try:
        with os.fdopen(fd, 'w') as file:
            file.write(value)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(name, mode)
        if owner is not None:
            os.chown(name, *owner)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def safe_directory(value):
    path = Path(value)
    if not path.is_absolute() or not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(path)) or '..' in path.parts or len(path.parts) < 3:
        raise ValueError('Bitte einen absoluten Unterordner ohne Leerzeichen verwenden: ' + str(value))
    resolved = path.resolve()
    if str(resolved) in ('/etc','/usr','/var','/var/lib','/opt','/home','/root','/tmp','/var/tmp','/usr/local') or len(resolved.parts)<3:
        raise ValueError('Ein eigener Unterordner wird benötigt: ' + str(value))
    return resolved


def endpoint(address, default_port, scheme):
    value = str(address or ':' + str(default_port))
    parsed = urllib.parse.urlsplit(scheme + '://' + value)
    host = parsed.hostname or '127.0.0.1'
    if host in ('0.0.0.0', '::'):
        host = '127.0.0.1'
    host = '[' + host + ']' if ':' in host else host
    return scheme + '://' + host + ':' + str(parsed.port or default_port) + '/'


def port_from(address, fallback):
    return urllib.parse.urlsplit('tcp://' + str(address or ':' + str(fallback))).port or fallback


def parse(argv=None):
    p = argparse.ArgumentParser(description='StreamDesk für eine neue oder vorhandene MediaMTX-Instanz installieren.')
    p.add_argument('--mode', choices=('standalone', 'attach', 'update'), default='attach')
    p.add_argument('--public-url', help='Öffentliche UI-Adresse, z.B. https://stream.example.com')
    p.add_argument('--ingest-host', help='IP oder DNS-Name für OBS und Handy, ohne Protokoll')
    p.add_argument('--app-dir', default='/opt/streamdesk')
    p.add_argument('--data-dir', default='/var/lib/streamdesk')
    p.add_argument('--service-name', default='streamdesk')
    p.add_argument('--bind', default=None, help='Gunicorn-Listener, Standard 0.0.0.0:8080')
    p.add_argument('--namespace', default='streamdesk')
    p.add_argument('--browser-root', default='/var/lib/streamdesk-browser')
    p.add_argument('--mediamtx-dir', default='/opt/mediamtx')
    p.add_argument('--mediamtx-config')
    p.add_argument('--mediamtx-binary')
    p.add_argument('--mediamtx-service', default='mediamtx')
    p.add_argument('--api-url', help='Optionaler Control-API-Endpunkt mit gültigem TLS-Zertifikat')
    p.add_argument('--hls-url')
    p.add_argument('--media-bind', default='0.0.0.0')
    for name, port in [('rtsp', 8554), ('rtmp', 1935), ('srt', 8890), ('api', 9997), ('hls', 8888)]:
        p.add_argument('--' + name + '-port', type=int, default=port, help='Port bei einer Neuinstallation bzw. einem neu aktivierten Listener')
    p.add_argument('--admin-user', default='admin')
    p.add_argument('--admin-password-file', help='Root-private Datei mit dem initialen Passwort; sonst zufällig erzeugt')
    p.add_argument('--backup-dir', default='/var/backups/streamdesk')
    p.add_argument('--skip-system-packages', action='store_true', help='Nur wenn Debian-Systemabhängigkeiten bereits vorhanden sind')
    p.add_argument('--yes', action='store_true', help='Nicht interaktiv; öffentliche Adresse und Ingest-Host müssen angegeben sein')
    p.add_argument('--dry-run', action='store_true', help='Plan und Konfigurationsprüfung ohne Änderungen')
    return p.parse_args(argv)


def validate(a):
    if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', a.namespace):
        raise ValueError('Ungültiger Namensbereich.')
    for name in (a.service_name, a.mediamtx_service):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,59}', name):
            raise ValueError('Ungültiger Dienstname.')
    if a.service_name == a.mediamtx_service:
        raise ValueError('UI und MediaMTX benötigen unterschiedliche Dienstnamen.')
    for name in ('app_dir', 'data_dir', 'browser_root', 'mediamtx_dir', 'backup_dir'):
        setattr(a, name, safe_directory(getattr(a, name)))
    if a.data_dir == a.app_dir or a.data_dir == a.mediamtx_dir:
        raise ValueError('Anwendungsdaten benötigen einen eigenen Ordner.')
    a.env_file = Path('/etc/' + a.service_name + '.env')
    old = load_env(a.env_file) if a.mode == 'update' else {}
    if old:
        if Path(old.get('STREAMDESK_DATA', str(a.data_dir))) != a.data_dir:
            raise ValueError('Beim Update dieselben --data-dir und --app-dir wie bei der Ersteinrichtung verwenden.')
        a.public_url = a.public_url or old.get('STREAMDESK_PUBLIC')
        a.ingest_host = a.ingest_host or old.get('STREAMDESK_INGEST')
        a.bind = a.bind or old.get('STREAMDESK_BIND')
        a.namespace = old.get('STREAMDESK_NAMESPACE', a.namespace)
        a.browser_root = Path(old.get('STREAMDESK_BROWSER_ROOT', str(a.browser_root)))
        a.mediamtx_config = a.mediamtx_config or old.get('MEDIAMTX_CONFIG')
        a.mediamtx_service = old.get('STREAMDESK_MEDIAMTX_SERVICE', a.mediamtx_service)
        a.mediamtx_binary = a.mediamtx_binary or old.get('STREAMDESK_MEDIAMTX_BINARY')
        a.api_url = a.api_url or old.get('MEDIAMTX_API', '').removesuffix('v3/') or None
        a.hls_url = a.hls_url or old.get('MEDIAMTX_HLS')
    if not a.public_url and not a.yes and sys.stdin.isatty():
        a.public_url = input('Öffentliche UI-Adresse (https://stream.example.com): ').strip()
    if not a.ingest_host and not a.yes and sys.stdin.isatty():
        a.ingest_host = input('IP oder DNS-Name für OBS und Handy: ').strip()
    if not a.public_url or not a.ingest_host:
        raise ValueError('--public-url und --ingest-host werden benötigt.')
    a.bind = a.bind or '0.0.0.0:8080'
    parsed = urllib.parse.urlsplit(a.public_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('--public-url muss eine HTTP(S)-Adresse ohne Unterpfad oder Zugangsdaten sein.')
    a.public_url = a.public_url.rstrip('/')
    host = a.ingest_host.strip('[]')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', host) or host.startswith('.'):
            raise ValueError('--ingest-host muss ein Hostname oder eine IP sein.')
    a.ingest_host = '[' + host + ']' if ':' in host else host
    for value in [a.rtsp_port, a.rtmp_port, a.srt_port, a.api_port, a.hls_port, port_from(a.bind, 8080)]:
        if not 1 <= value <= 65535:
            raise ValueError('Ungültiger Port.')
    if a.mode == 'standalone':
        a.mediamtx_config = Path(a.mediamtx_config or a.mediamtx_dir / 'mediamtx.yml').resolve()
        a.mediamtx_binary = Path(a.mediamtx_binary or a.mediamtx_dir / 'mediamtx').resolve()
        if a.mediamtx_config.exists() or a.mediamtx_binary.exists():
            raise ValueError('MediaMTX existiert bereits. --mode attach verwenden; es wird nichts überschrieben.')
        if len(set([a.rtsp_port, a.rtmp_port, a.api_port, a.hls_port, port_from(a.bind, 8080)])) != 5:
            raise ValueError('TCP-Ports müssen unterschiedlich sein.')
    else:
        candidates = [Path(a.mediamtx_config)] if a.mediamtx_config else [a.mediamtx_dir / 'mediamtx.yml', Path('/etc/mediamtx/mediamtx.yml'), Path('/etc/mediamtx.yml')]
        found = next((p for p in candidates if p.is_file()), None)
        if not found:
            raise ValueError('MediaMTX-Konfiguration fehlt. --mediamtx-config angeben oder --mode standalone verwenden.')
        a.mediamtx_config = found.resolve()
        binary = a.mediamtx_binary or shutil.which('mediamtx') or str(a.mediamtx_config.parent / 'mediamtx')
        a.mediamtx_binary = Path(binary).resolve()
        if not a.mediamtx_binary.is_file():
            raise ValueError('--mediamtx-binary mit dem vorhandenen MediaMTX-Programm angeben.')
        output = subprocess.check_output([str(a.mediamtx_binary), '--version'], text=True).strip()
        match = re.search(r'(\d+)\.(\d+)\.(\d+)', output)
        if not match or not (1, 21, 3) <= tuple(map(int, match.groups())) < (2, 0, 0):
            raise ValueError('Benötigt MediaMTX >= 1.21.3 und < 2; erkannt: ' + output)
    for configured_file in (a.mediamtx_config, a.mediamtx_binary):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', str(configured_file)):
            raise ValueError('Dateipfade benötigen einfache absolute Namen ohne Leerzeichen: ' + str(configured_file))
    _ = parsed.port
    if a.mode != 'update' and a.data_dir.exists() and any(a.data_dir.iterdir()):
        raise ValueError('Der Datenordner ist nicht leer. Einen neuen Ordner oder --mode update verwenden.')
    if a.mode == 'standalone' and any(Path(base, a.mediamtx_service + '.service').exists() for base in ('/etc/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system')):
        raise ValueError('Der MediaMTX-Dienst existiert bereits. --mode attach oder einen anderen Dienstnamen verwenden.')
    if a.mode != 'update' and any(Path(base, a.service_name + '.service').exists() for base in ('/etc/systemd/system', '/usr/lib/systemd/system', '/lib/systemd/system')):
        raise ValueError('Der UI-Dienstname ist bereits belegt. --mode update oder einen anderen Dienstnamen verwenden.')
    if a.mode != 'update' and ((a.data_dir / 'app.db').exists() or a.env_file.exists()):
        raise ValueError('StreamDesk existiert bereits. --mode update verwenden.')
    if a.mode == 'update' and not (a.data_dir / 'app.db').is_file():
        raise ValueError('Keine StreamDesk-Datenbank für ein Update gefunden.')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,29}', a.admin_user):
        raise ValueError('Ungültiger Administratorname.')
    if a.admin_password_file:
        password_file = Path(a.admin_password_file)
        if not password_file.is_file():
            raise ValueError('Die Passwortdatei wurde nicht gefunden: ' + str(password_file))
        if password_file.stat().st_mode & 0o077:
            raise ValueError('Die Passwortdatei darf nur root lesen (chmod 600).')
        if len(password_file.read_text().strip()) < 12:
            raise ValueError('Das Administratorpasswort benötigt mindestens 12 Zeichen.')
    return old


def fresh_config(a):
    bind = '[' + a.media_bind.strip('[]') + ']' if ':' in a.media_bind else a.media_bind
    return {'logLevel': 'info', 'api': True, 'apiAddress': '127.0.0.1:' + str(a.api_port),
            'rtsp': True, 'rtspAddress': bind + ':' + str(a.rtsp_port), 'rtspTransports': ['tcp'],
            'rtmp': True, 'rtmpAddress': bind + ':' + str(a.rtmp_port), 'srt': True, 'srtAddress': bind + ':' + str(a.srt_port),
            'hls': True, 'hlsAddress': '127.0.0.1:' + str(a.hls_port), 'hlsVariant': 'mpegts',
            'webrtc': False, 'moq': False, 'authMethod': 'internal', 'authInternalUsers': [], 'paths': {}}


def prepare_config(a, config):
    from media_config import merge_auth
    config['paths'] = config.get('paths') or {}
    if a.mode != 'update' and any(str(name).startswith(a.namespace + '/') for name in config.get('paths', {})):
        raise ValueError('Der Namensbereich ist bereits belegt. Einen anderen --namespace wählen.')
    if a.mode != 'update' and any(str(u.get('user', '')).startswith('streamdesk_' + a.namespace + '_') for u in config.get('authInternalUsers', [])):
        raise ValueError('Der reservierte Präfix für StreamDesk-Medienkonten ist bereits belegt. Einen anderen --namespace wählen.')
    local_ips = ['127.0.0.1', '::1']
    for protocol, port in [('api', a.api_port), ('hls', a.hls_port), ('rtsp', a.rtsp_port), ('rtmp', a.rtmp_port), ('srt', a.srt_port)]:
        if not config.get(protocol, protocol not in ('api',)):
            config[protocol] = True
            config[protocol + 'Address'] = ('127.0.0.1' if protocol in ('api', 'hls', 'rtsp') else a.media_bind) + ':' + str(port)
            if protocol == 'hls':
                config['hlsVariant'] = 'mpegts'
        address = config.get(protocol + 'Address', ':' + str(port))
        hostname = urllib.parse.urlsplit('tcp://' + str(address)).hostname
        if hostname and hostname not in ('0.0.0.0', '::', '127.0.0.1', '::1'):
            # These are configured local listener addresses, not untrusted client IPs.
            local_ips.extend(x[4][0] for x in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM))
    local_ips = sorted(set(local_ips), key=lambda p: (p != '127.0.0.1', p))
    # Keep managed accounts on update; the running application refreshes them next.
    own_prefix = 'streamdesk_' + a.namespace + '_'
    managed = [u for u in config.get('authInternalUsers', []) if str(u.get('user', '')).startswith(own_prefix)] if a.mode == 'update' else []
    merge_auth(config, a.namespace, managed, local_ips)
    return local_ips


def media_config_permissions(a):
    if a.mode == 'standalone':
        return 0o600, (0, 0)
    service_user = subprocess.check_output(['systemctl', 'show', a.mediamtx_service, '--property=User', '--value'], text=True).strip() or 'root'
    dynamic = subprocess.check_output(['systemctl', 'show', a.mediamtx_service, '--property=DynamicUser', '--value'], text=True).strip()
    if dynamic == 'yes':
        raise ValueError('DynamicUser-Dienste benötigen eine manuell eingerichtete persistente Konfigurationsgruppe.')
    user = pwd.getpwuid(int(service_user)) if service_user.isdigit() else pwd.getpwnam(service_user)
    service_group = subprocess.check_output(['systemctl', 'show', a.mediamtx_service, '--property=Group', '--value'], text=True).strip()
    group_id = (int(service_group) if service_group.isdigit() else grp.getgrnam(service_group).gr_gid) if service_group else user.pw_gid
    return (0o600, (0, 0)) if user.pw_uid == 0 else (0o640, (0, group_id))


def download_media(a):
    architecture = {'x86_64': 'amd64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if not architecture:
        raise ValueError('Automatischer MediaMTX-Download unterstützt amd64 und arm64. Sonst MediaMTX selbst installieren und attach nutzen.')
    name = 'mediamtx_v' + MEDIA_VERSION + '_linux_' + architecture + '.tar.gz'
    url = 'https://github.com/bluenviron/mediamtx/releases/download/v' + MEDIA_VERSION + '/' + name
    with tempfile.TemporaryDirectory(prefix='streamdesk-download-') as temporary:
        archive = Path(temporary) / name
        urllib.request.urlretrieve(url, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != MEDIA_DIGESTS[architecture]:
            raise RuntimeError('MediaMTX-Prüfsumme stimmt nicht. Installation abgebrochen.')
        with tarfile.open(archive, 'r:gz') as bundle:
            member = bundle.getmember('mediamtx')
            if not member.isfile():
                raise RuntimeError('Unerwarteter MediaMTX-Archivinhalt.')
            a.mediamtx_binary.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(member) as source, a.mediamtx_binary.open('wb') as target:
                shutil.copyfileobj(source, target)
            a.mediamtx_binary.chmod(0o755)
    return architecture


def backup(a):
    folder = a.backup_dir / (a.service_name + '-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    folder.mkdir(parents=True, mode=0o700)
    folder.chmod(0o700)
    if a.mediamtx_config.is_file():
        shutil.copy2(a.mediamtx_config, folder / 'mediamtx.yml')
        meta = a.mediamtx_config.stat()
        write_private(folder / 'file-metadata.json', json.dumps({'config_uid': meta.st_uid, 'config_gid': meta.st_gid, 'config_mode': meta.st_mode & 0o777}))
    if a.env_file.is_file():
        shutil.copy2(a.env_file, folder / 'streamdesk.env')
    if (a.data_dir / 'app.db').is_file():
        original = sqlite3.connect(a.data_dir / 'app.db')
        target = sqlite3.connect(folder / 'app.db')
        original.backup(target)
        target.close()
        original.close()
        for name in ('fernet.key', 'session.key'):
            shutil.copy2(a.data_dir / name, folder / name)
    if (a.app_dir / 'venv/bin/pip').is_file():
        frozen = subprocess.check_output([str(a.app_dir / 'venv/bin/pip'), 'freeze'], text=True, stderr=subprocess.PIPE)
        write_private(folder / 'requirements-before.txt', frozen)
    if a.app_dir.exists():
        shutil.copytree(a.app_dir, folder / 'application', ignore=shutil.ignore_patterns('venv', '__pycache__', '.git', 'browsers'))
    for name in (a.service_name, a.mediamtx_service):
        unit = Path('/etc/systemd/system/' + name + '.service')
        if unit.is_file():
            shutil.copy2(unit, folder / (name + '.service'))
    return folder


def dependencies(a):
    if not a.skip_system_packages:
        run(['apt-get', 'update'])
        run(['apt-get', 'install', '-y', '--no-install-recommends', 'python3-venv', 'python3-pip', 'python3-yaml', 'ffmpeg', 'fonts-dejavu-core', 'chromium', 'procps', 'ca-certificates'])
    for command in ('ffmpeg', 'ffprobe', 'systemctl', 'useradd'):
        if not shutil.which(command):
            raise RuntimeError('Fehlende Systemabhängigkeit: ' + command)
    if not Path('/usr/bin/chromium').is_file():
        raise RuntimeError('Chromium fehlt unter /usr/bin/chromium.')


def service_text(a, media=False):
    if media:
        return f'''[Unit]
Description=MediaMTX media server (installed by StreamDesk)
After=network-online.target
Wants=network-online.target
[Service]
ExecStart={a.mediamtx_binary} {a.mediamtx_config}
Restart=on-failure
RestartSec=3
User=root
UMask=0077
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
'''
    return f'''[Unit]
Description=StreamDesk UI and source manager
After=network-online.target {a.mediamtx_service}.service
Wants=network-online.target {a.mediamtx_service}.service
[Service]
WorkingDirectory={a.app_dir}
EnvironmentFile={a.env_file}
ExecStart={a.app_dir}/venv/bin/gunicorn --config {a.app_dir}/gunicorn.conf.py app:app
Restart=always
RestartSec=3
KillMode=control-group
TimeoutStopSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths={a.data_dir} {a.mediamtx_config.parent} {a.browser_root}
[Install]
WantedBy=multi-user.target
'''


def wait_url(url, seconds=30):
    for _ in range(seconds * 2):
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError('Dienst antwortet nicht: ' + url)


def install(a, old):
    global yaml
    before_active = subprocess.run(['systemctl', 'is-active', '--quiet', a.service_name], check=False).returncode == 0
    folder = backup(a)
    print('Sicherung (ohne Medienkopien): ' + str(folder), flush=True)
    media_was_active = subprocess.run(['systemctl', 'is-active', '--quiet', a.mediamtx_service], check=False).returncode == 0
    config_changed = False
    ui_touched = False
    data_existed = a.data_dir.exists()
    media_created = False
    try:
        dependencies(a)
        import yaml
        config = fresh_config(a) if a.mode == 'standalone' else yaml.safe_load(a.mediamtx_config.read_text())
        local_ips = prepare_config(a, config)
        config_mode, config_owner = media_config_permissions(a)
        ui_touched = True
        if before_active:
            run(['systemctl', 'stop', a.service_name])
        # Only our own source is copied. No server database or credentials are part of a release.
        a.app_dir.mkdir(parents=True, exist_ok=True)
        a.app_dir.chmod(0o755)
        os.chown(a.app_dir, 0, 0)
        for name in ('static','templates','scripts','docs'):
            if (a.app_dir/name).is_symlink():
                raise ValueError('Symlinks in Programmverzeichnissen werden nicht überschrieben: ' + name)
        for name in FILES:
            source = SOURCE / name
            if source.resolve() != (a.app_dir / name).resolve():
                shutil.copy2(source, a.app_dir / name)
            os.chown(a.app_dir / name, 0, 0)
            (a.app_dir / name).chmod(0o755 if name.endswith('.sh') else 0o644)
        for name in ('templates', 'static', 'scripts', 'docs'):
            if (SOURCE / name).resolve() != (a.app_dir / name).resolve():
                shutil.copytree(SOURCE / name, a.app_dir / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('static','templates','scripts','docs'):
            for child in [a.app_dir/name, *(a.app_dir/name).rglob('*')]:
                if child.is_symlink():
                    raise ValueError('Symlink in Programmdateien: ' + str(child))
                os.chown(child, 0, 0)
                child.chmod(0o755 if child.is_dir() else 0o644)
        if not (a.app_dir / 'venv/bin/python').exists():
            run([sys.executable, '-m', 'venv', a.app_dir / 'venv'])
        run([a.app_dir / 'venv/bin/pip', 'install', '-r', a.app_dir / 'requirements.txt'])
        a.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        a.data_dir.chmod(0o700)
        if subprocess.run(['id', 'streamdesk-browser'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            run(['useradd', '--system', '--no-create-home', '--shell', '/usr/sbin/nologin', 'streamdesk-browser'])
        a.browser_root.mkdir(parents=True, exist_ok=True)
        a.browser_root.chmod(0o711)
        clip = a.data_dir / 'standby.mp4'
        if not clip.exists():
            run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=0x111827:s=1920x1080:r=30',
                 '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-t', '10', '-vf',
                 "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:text=Standby:fontsize=42:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
                 '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-threads', '1', '-g', '60', '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', clip])
            clip.chmod(0o600)
        api = a.api_url or endpoint(config.get('apiAddress'), a.api_port, 'https' if config.get('apiEncryption') else 'http')
        hls = a.hls_url or endpoint(config.get('hlsAddress'), a.hls_port, 'https' if config.get('hlsEncryption') else 'http')
        rtsp = endpoint(config.get('rtspAddress'), a.rtsp_port, 'rtsp')
        values = dict(old)
        values.update(STREAMDESK_PUBLIC=a.public_url, STREAMDESK_INGEST=a.ingest_host, STREAMDESK_DATA=str(a.data_dir),
                      STREAMDESK_DEFAULT_CLIP=str(clip), STREAMDESK_NAMESPACE=a.namespace, STREAMDESK_BIND=a.bind,
                      STREAMDESK_BROWSER_ROOT=str(a.browser_root), STREAMDESK_BROWSER_USER='streamdesk-browser',
                      STREAMDESK_LOCAL_IPS=','.join(local_ips), STREAMDESK_MEDIAMTX_SERVICE=a.mediamtx_service,
                      STREAMDESK_MEDIAMTX_BINARY=str(a.mediamtx_binary), MEDIAMTX_CONFIG=str(a.mediamtx_config),
                      MEDIAMTX_API=api.rstrip('/') + '/v3/', MEDIAMTX_HLS=hls.rstrip('/') + '/', MEDIAMTX_RTSP=rtsp,
                      MEDIAMTX_RTMP_PORT=str(port_from(config.get('rtmpAddress'), a.rtmp_port)),
                      MEDIAMTX_SRT_PORT=str(port_from(config.get('srtAddress'), a.srt_port)),
                      COOKIE_SECURE='1' if a.public_url.startswith('https:') else '0',
                      STREAMDESK_TRUST_PROXY='1' if a.public_url.startswith('https:') else '0')
        if a.mode == 'standalone':
            download_media(a)
            media_created = True
            write_private('/etc/systemd/system/' + a.mediamtx_service + '.service', service_text(a, media=True), 0o644)
        write_private(a.env_file, ''.join(key + '=' + json.dumps(str(value)) + '\n' for key, value in sorted(values.items())))
        write_private(a.mediamtx_config, yaml.safe_dump(config, sort_keys=False, allow_unicode=True), config_mode, config_owner)
        config_changed = True
        password = ''
        environment = {**os.environ, **values, 'STREAMDESK_ENGINE': '0'}
        if a.mode != 'update':
            password = Path(a.admin_password_file).read_text().strip() if a.admin_password_file else secrets.token_urlsafe(24)
            run([a.app_dir / 'venv/bin/python', a.app_dir / 'bootstrap.py'], cwd=a.app_dir, env=environment,
                input=json.dumps({'username': a.admin_user, 'password': password}) + '\n', text=True)
        write_private('/etc/systemd/system/' + a.service_name + '.service', service_text(a), 0o644)
        run(['systemctl', 'daemon-reload'])
        if a.mode == 'standalone':
            run(['systemctl', 'enable', '--now', a.mediamtx_service])
        elif not media_was_active:
            run(['systemctl', 'start', a.mediamtx_service])
        wait_url(api.rstrip('/') + '/v3/config/global/get')
        run([a.app_dir / 'venv/bin/python', '-c', 'import app; app.sync_media_runtime()'], cwd=a.app_dir, env=environment)
        with sqlite3.connect(a.data_dir / 'app.db') as database:
            owner = database.execute('SELECT prefix FROM users ORDER BY id LIMIT 1').fetchone()
        if not owner:
            raise RuntimeError('Die Datenbank enthält keinen eingerichteten Benutzer.')
        wait_url(api.rstrip('/') + '/v3/config/paths/get/' + urllib.parse.quote(owner[0] + 'source1', safe='/'))
        run(['systemctl', 'enable', '--now', a.service_name])
        bind_url = endpoint(a.bind, 8080, 'http')
        wait_url(bind_url + 'login')
        marker = {'version': VERSION, 'mode': a.mode, 'namespace': a.namespace, 'backup': str(folder), 'media_config': str(a.mediamtx_config)}
        write_private(a.data_dir / 'installation.json', json.dumps(marker, indent=2) + '\n')
        if password:
            write_private(a.data_dir / 'initial-login.txt', 'Benutzername: ' + a.admin_user + '\nPasswort: ' + password + '\n')
        print('\nStreamDesk ' + VERSION + ' ist installiert. UI: ' + a.public_url)
        if password:
            print('Erste Zugangsdaten nur lokal für root: ' + str(a.data_dir / 'initial-login.txt'))
        print('MediaMTX: ' + str(a.mediamtx_config) + ' · Namensbereich: ' + a.namespace + '/')
        print('Es wurde kein Twitch-/YouTube-Stream gestartet.')
    except Exception:
        print('Installation fehlgeschlagen. Vorhandene Konfiguration wird wiederhergestellt.', file=sys.stderr)
        if ui_touched:
            subprocess.run(['systemctl', 'stop', a.service_name], check=False)
        if config_changed and (folder / 'mediamtx.yml').exists():
            shutil.copy2(folder / 'mediamtx.yml', a.mediamtx_config)
            meta = json.loads((folder / 'file-metadata.json').read_text())
            os.chown(a.mediamtx_config, meta['config_uid'], meta['config_gid'])
            os.chmod(a.mediamtx_config, meta['config_mode'])
        if (folder / 'streamdesk.env').exists():
            shutil.copy2(folder / 'streamdesk.env', a.env_file)
        if (folder / 'application').exists():
            shutil.copytree(folder / 'application', a.app_dir, dirs_exist_ok=True)
        if (folder / 'app.db').exists():
            restored = sqlite3.connect(a.data_dir / 'app.db')
            saved = sqlite3.connect(folder / 'app.db')
            saved.backup(restored)
            saved.close()
            restored.close()
        for service in (a.service_name, a.mediamtx_service):
            saved_unit = folder / (service + '.service')
            target_unit = Path('/etc/systemd/system/' + service + '.service')
            if saved_unit.exists():
                shutil.copy2(saved_unit, target_unit)
            elif service == a.service_name and not before_active or service == a.mediamtx_service and media_created:
                subprocess.run(['systemctl', 'disable', '--now', service], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                target_unit.unlink(missing_ok=True)
        if a.mode != 'update' and ui_touched:
            if not (folder / 'streamdesk.env').exists():
                a.env_file.unlink(missing_ok=True)
            # validate() required a completely empty/new data directory.
            if a.data_dir.exists():
                shutil.rmtree(a.data_dir)
                if data_existed:
                    a.data_dir.mkdir(mode=0o700)
        if media_created:
            a.mediamtx_binary.unlink(missing_ok=True)
            a.mediamtx_config.unlink(missing_ok=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=False)
        if before_active and ui_touched:
            subprocess.run(['systemctl', 'start', a.service_name], check=False)
        print('Sicherung: ' + str(folder) + '. Neue Teildateien werden nicht automatisch gelöscht.', file=sys.stderr)
        raise


def main(argv=None):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11 oder neuer wird benötigt.')
    a = parse(argv)
    old = validate(a)
    print('Modus: ' + a.mode + '\nUI: ' + a.public_url + '\nMediaMTX: ' + str(a.mediamtx_config) + '\nPrivater Medien-Namensbereich: ' + a.namespace + '/')
    if a.dry_run:
        if a.mode != 'standalone':
            import yaml
            config = yaml.safe_load(a.mediamtx_config.read_text())
            prepare_config(a, config)
            print('Konfiguration kompatibel; fremde Pfade bleiben erhalten. Globale Medienberechtigungen werden auf Pfade außerhalb des UI-Namensbereichs beschränkt.')
        print('Dry run: keine Dateien, Dienste oder Pakete verändert.')
        return
    if os.geteuid() != 0:
        raise RuntimeError('Bitte mit sudo oder als root ausführen.')
    if not Path('/run/systemd/system').exists():
        raise RuntimeError('Eine native Linux-Installation mit systemd wird benötigt.')
    os_release = dict(line.strip().split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if os_release.get('ID', '').strip('"') != 'debian' or os_release.get('VERSION_ID', '').strip('"').split('.')[0] not in ('12', '13'):
        raise RuntimeError('Dieser Installer unterstützt Debian 12 und 13. Andere Systeme benötigen eine manuelle Installation.')
    if not a.yes and sys.stdin.isatty():
        if input('Konfiguration sichern und Installation ausführen? [ja/NEIN] ').strip().lower() != 'ja':
            print('Abgebrochen.')
            return
    install(a, old)


if __name__ == '__main__':
    sys.path.insert(0, str(SOURCE))
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('FEHLER: ' + str(exc), file=sys.stderr)
        sys.exit(1)
