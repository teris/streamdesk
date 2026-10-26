"""Opt-in recovery smoke test against a real local MediaMTX, without systemd.

python tests/recovery_smoke.py --mediamtx /path/to/mediamtx
Uses temporary files and loopback listeners; never connects to public outputs.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_config import service_acl, synchronize_runtime


def free_port(udp=False):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM if udp else socket.SOCK_STREAM) as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mediamtx', required=True, type=Path)
    options = parser.parse_args()
    spec = importlib.util.spec_from_file_location('recovery_installer', ROOT / 'scripts/install.py')
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    with tempfile.TemporaryDirectory(prefix='streamdesk-recovery-smoke-') as temporary:
        base = Path(temporary)
        args = installer.parse(['--mode', 'attach', '--recover', '--media-bind', '127.0.0.1'])
        args.data_dir = base / 'data'
        args.recovery_has_owner = True
        for protocol in ('rtsp', 'rtmp', 'api', 'hls'):
            setattr(args, protocol + '_port', free_port())
        args.srt_port = free_port(udp=True)
        config = installer.fresh_config(args)
        config['authInternalUsers'] = [service_acl(args.namespace),
            {'user': 'streamdesk_streamdesk_alice', 'pass': 'fixture-old-media-secret', 'ips': [],
             'permissions': [{'action': 'publish', 'path': 'streamdesk/alice/source1'}]}]
        config['paths'] = {'camera': {'source': 'publisher'}, 'streamdesk/alice/source1': {'source': 'publisher'},
                           'streamdesk/alice/output': {'source': 'publisher', 'forward': []}}
        path = base / 'mediamtx.yml'
        path.write_text(yaml.safe_dump(config))
        args.data_dir.mkdir()
        (args.data_dir / 'fernet.key').write_bytes(b'fixture-orphaned-key')
        (args.data_dir / 'orphan.mp4').write_bytes(b'fixture-orphaned-media')
        backup = base / 'backup'
        backup.mkdir()
        api_url = f'http://127.0.0.1:{args.api_port}/v3/'

        def api(route, value=None, method=None):
            req = urllib.request.Request(api_url + route, data=json.dumps(value).encode() if value is not None else None,
                                         headers={'Content-Type': 'application/json'}, method=method)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = response.read()
                return json.loads(data) if data else {}

        with (base / 'media.log').open('wb') as log:
            media = subprocess.Popen([str(options.mediamtx.resolve()), str(path)], stdout=log, stderr=subprocess.STDOUT)
            try:
                for _ in range(50):
                    try:
                        api('config/global/get')
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    raise RuntimeError('Local MediaMTX did not start')
                updated = copy.deepcopy(config)
                installer.prepare_config(args, updated)
                previous = installer.quarantine_recovery_data(args, backup)
                installer.write_private(path, yaml.safe_dump(updated))
                clip = base / 'standby.mp4'
                clip.write_bytes(b'fixture-bootstrap-only-clip')
                environment = {**os.environ, 'STREAMDESK_ENGINE': '0', 'STREAMDESK_DATA': str(args.data_dir),
                    'STREAMDESK_DEFAULT_CLIP': str(clip), 'MEDIAMTX_CONFIG': str(path), 'MEDIAMTX_API': api_url,
                    'STREAMDESK_NAMESPACE': args.namespace, 'COOKIE_SECURE': '0', 'STREAMDESK_TRUST_PROXY': '0'}
                password = 'Recovery-Smoke-Fixture-Password-12345'
                subprocess.run([sys.executable, str(ROOT / 'bootstrap.py')], cwd=ROOT, env=environment,
                               input=json.dumps({'username': 'admin', 'password': password}) + '\n', text=True, check=True)
                current = yaml.safe_load(path.read_text())
                # Simulate stale runtime entries when the file watcher has already reloaded.
                time.sleep(.5)
                for name in args.recovery_paths:
                    api('config/paths/add/' + name, {'source': 'publisher'}, method='POST')
                synchronize_runtime(api, current, args.namespace, obsolete_paths=args.recovery_paths)
                names = {item['name'] for item in api('config/paths/list?itemsPerPage=1000')['items']}
                assert 'camera' in names
                assert 'streamdesk/admin/source1' in names
                assert not names.intersection(args.recovery_paths)
                assert current['paths']['camera'] == config['paths']['camera']
                assert not any(entry['user'] == 'streamdesk_streamdesk_alice' for entry in current['authInternalUsers'])
                assert (previous / 'fernet.key').read_bytes() == b'fixture-orphaned-key'
                assert (previous / 'orphan.mp4').read_bytes() == b'fixture-orphaned-media'
                assert (args.data_dir / 'fernet.key').read_bytes() != b'fixture-orphaned-key'
                subprocess.run([sys.executable, '-c',
                    "import app,json,sys; settings=json.load(sys.stdin); client=app.app.test_client(); "
                    "client.get('/login'); "
                    "token=app.app.session_interface.get_signing_serializer(app.app).loads(client.get_cookie('session').value)['csrf']; "
                    "assert client.post('/login',data={'csrf':token,'username':'admin','password':settings['password']}).status_code==302; "
                    "assert [u['username'] for u in app.rows('SELECT username FROM users')]==['admin']"],
                    cwd=ROOT, env=environment, input=json.dumps({'password': password}), text=True, check=True)
                print('PASS: recovery creates a fresh administrator and encryption keys, preserves orphaned files and foreign paths, and removes only obsolete StreamDesk runtime paths.')
            finally:
                media.terminate()
                try:
                    media.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    media.kill()
                    media.wait()


if __name__ == '__main__':
    main()
