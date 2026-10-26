#!/usr/bin/env python3
"""Remove only the UI integration. Keep data, source and MediaMTX itself."""
import argparse
import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install import load_env, write_private
from media_config import is_service_acl, outside_namespace


def main():
    parser = argparse.ArgumentParser(description='StreamDesk-Integration entfernen; Daten und MediaMTX bleiben erhalten.')
    parser.add_argument('--service-name', default='streamdesk')
    parser.add_argument('--backup-dir', default='/var/backups/streamdesk')
    parser.add_argument('--yes', action='store_true')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise ValueError('Bitte als root ausführen.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}', args.service_name):
        raise ValueError('Ungültiger Dienstname.')
    backup_root = Path(args.backup_dir)
    if not backup_root.is_absolute() or '..' in backup_root.parts:
        raise ValueError('--backup-dir muss ein absoluter Pfad ohne .. sein.')
    env_file = Path('/etc/' + args.service_name + '.env')
    env = load_env(env_file)
    if not env or not env.get('STREAMDESK_NAMESPACE'):
        raise ValueError('Keine passende Installation gefunden.')
    import yaml
    config_file = Path(env['MEDIAMTX_CONFIG'])
    namespace = env['STREAMDESK_NAMESPACE']
    if not args.yes and input('UI-Dienst stoppen und seine Medienpfade entfernen? [ja/NEIN] ').strip().lower() != 'ja':
        return
    backup = backup_root / (args.service_name + '-uninstall-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, mode=0o700, exist_ok=False)
    shutil.copy2(config_file, backup / 'mediamtx.yml')
    shutil.copy2(env_file, backup / 'streamdesk.env')
    subprocess.run(['systemctl', 'disable', '--now', args.service_name], check=True)
    config = yaml.safe_load(config_file.read_text())
    prefix = namespace + '/'
    config['paths'] = {name: value for name, value in config.get('paths', {}).items() if not str(name).startswith(prefix)}
    users = []
    for original in config.get('authInternalUsers', []):
        if str(original.get('user', '')).startswith('streamdesk_' + namespace + '_') or is_service_acl(original, namespace):
            continue
        user = dict(original)
        user['permissions'] = [dict(p, path='') if p.get('path') == outside_namespace(namespace) else p for p in user.get('permissions', [])]
        users.append(user)
    config['authInternalUsers'] = users
    metadata = config_file.stat()
    write_private(config_file, yaml.safe_dump(config, sort_keys=False, allow_unicode=True), metadata.st_mode & 0o777, (metadata.st_uid, metadata.st_gid))
    Path('/etc/systemd/system/' + args.service_name + '.service').unlink(missing_ok=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    print('UI-Integration entfernt. Daten und Schlüssel bleiben unter ' + env['STREAMDESK_DATA'])
    if env.get('STREAMDESK_NATIVE_ROOT'):
        print('Native Aufnahmesegmente bleiben unter ' + env['STREAMDESK_NATIVE_ROOT'])
    print('MediaMTX, Quellcode und Sicherungen bleiben erhalten. Sicherung: ' + str(backup))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FEHLER: ' + str(exc), file=sys.stderr)
        sys.exit(1)
