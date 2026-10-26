"""Installer recovery tests with private temporary paths and simulated systemd."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml
from media_config import service_acl

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('recovery_installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='streamdesk-recovery-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.etc = self.root / 'etc'
        self.units = self.root / 'units'
        self.etc.mkdir()
        self.units.mkdir()
        self.data = self.root / 'data'
        self.app_dir = self.root / 'application'
        self.media = self.root / 'media.yml'
        self.binary = self.root / 'mediamtx'
        self.binary.write_bytes(b'fixture-existing-media-binary')
        self.config = {'authMethod': 'internal', 'api': True, 'apiAddress': '127.0.0.1:19997',
            'rtsp': True, 'hls': True, 'rtmp': True, 'srt': True,
            'paths': {'camera': {'source': 'rtsp://fixture.example/camera', 'record': True},
                      'streamdesk/alice/source1': {'source': 'publisher'},
                      'streamdesk/alice/output': {'source': 'publisher', 'forward': [{'dest': 'rtmp://fixture.example/app#old-fixture-key'}]}},
            'authInternalUsers': [service_acl('streamdesk'),
                {'user': 'camera-reader', 'pass': 'fixture-only-password', 'ips': [],
                 'permissions': [{'action': 'read', 'path': 'camera'}]},
                {'user': 'streamdesk_streamdesk_alice', 'pass': 'fixture-only-old-secret', 'ips': [],
                 'permissions': [{'action': 'publish', 'path': 'streamdesk/alice/source1'}]}]}
        self.media.write_text(yaml.safe_dump(self.config))
        self.old = {'STREAMDESK_PUBLIC': 'https://fixture.example', 'STREAMDESK_INGEST': 'fixture.example',
                    'STREAMDESK_DATA': str(self.data), 'STREAMDESK_APP_DIR': str(self.app_dir),
                    'STREAMDESK_NAMESPACE': 'streamdesk', 'MEDIAMTX_CONFIG': str(self.media),
                    'STREAMDESK_MEDIAMTX_BINARY': str(self.binary), 'STREAMDESK_MEDIAMTX_SERVICE': 'mediamtx'}
        self.env = self.etc / 'streamdesk.env'
        self.env.write_text(''.join(key + '=' + json.dumps(value) + '\n' for key, value in self.old.items()))
        for target, value in [('ENV_DIR', self.etc), ('SYSTEMD_UNIT_DIR', self.units)]:
            patched = patch.object(installer, target, value)
            patched.start()
            self.addCleanup(patched.stop)
        patched = patch.object(installer, 'service_unit_exists', return_value=True)
        patched.start()
        self.addCleanup(patched.stop)
        patched = patch.object(installer.subprocess, 'check_output', return_value='v1.21.3')
        patched.start()
        self.addCleanup(patched.stop)

    def args(self, mode='attach', recover=True, data=True):
        values = ['--mode', mode, '--public-url', 'https://fixture.example', '--ingest-host', 'fixture.example',
                  '--app-dir', str(self.app_dir), '--browser-root', str(self.root / 'browser'),
                  '--backup-dir', str(self.root / 'backups'), '--mediamtx-config', str(self.media),
                  '--mediamtx-binary', str(self.binary), '--yes']
        if recover:
            values.append('--recover')
        if data:
            values += ['--data-dir', str(self.data)]
        return installer.parse(values)

    def test_partial_attach_and_update_point_to_recovery(self):
        for mode in ('attach', 'update'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, '--recover'):
                installer.validate(self.args(mode, recover=False))

    def test_recovery_never_overwrites_a_present_database(self):
        self.data.mkdir()
        database = self.data / 'app.db'
        database.write_bytes(b'fixture-preserve-this-database')
        for mode in ('attach', 'update'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'überschreibt sie nicht'):
                installer.validate(self.args(mode))
        self.assertEqual(database.read_bytes(), b'fixture-preserve-this-database')

    def test_recovery_uses_saved_data_directory_before_checking_database(self):
        self.data.mkdir()
        (self.data / 'app.db').write_bytes(b'fixture-intact-at-custom-path')
        with self.assertRaisesRegex(ValueError, 'überschreibt sie nicht'):
            installer.validate(self.args(data=False))

    def test_update_inherits_custom_paths_and_rejects_missing_keys(self):
        self.data.mkdir()
        (self.data / 'app.db').write_bytes(b'fixture-existing-database')
        with self.assertRaisesRegex(ValueError, 'Schlüssel fehlen'):
            installer.validate(self.args('update', recover=False, data=False))
        for name in ('fernet.key', 'session.key'):
            (self.data / name).write_bytes(b'fixture-key')
        args = self.args('update', recover=False, data=False)
        args.app_dir = '/opt/streamdesk'
        args.explicit_options.discard('--app-dir')
        installer.validate(args)
        self.assertEqual(args.data_dir, self.data)
        self.assertEqual(args.app_dir, self.app_dir)
        self.assertFalse(args.recover)

    def test_recovery_rejects_different_data_and_media_paths(self):
        args = self.args()
        args.data_dir = str(self.root / 'wrong-data')
        with self.assertRaisesRegex(ValueError, 'data-dir weicht'):
            installer.validate(args)
        other_media = self.root / 'different.yml'
        other_media.write_text(self.media.read_text())
        args = self.args()
        args.mediamtx_config = str(other_media)
        with self.assertRaisesRegex(ValueError, 'dieselbe MediaMTX-Konfiguration'):
            installer.validate(args)

    def test_recovery_requires_existing_media_mode(self):
        with self.assertRaisesRegex(ValueError, 'mode attach'):
            installer.validate(self.args('standalone'))

    def test_recovery_rejects_backup_inside_archived_data(self):
        args = self.args()
        args.backup_dir = str(self.data / 'backups')
        with self.assertRaisesRegex(ValueError, 'Sicherungsordner muss außerhalb'):
            installer.validate(args)
        self.assertFalse(self.data.exists())

    def test_recovery_replaces_only_owned_paths_and_accounts(self):
        args = self.args()
        installer.validate(args)
        config = copy.deepcopy(self.config)
        installer.prepare_config(args, config)
        self.assertEqual(config['paths'], {'camera': self.config['paths']['camera']})
        self.assertEqual(set(args.recovery_paths), {'streamdesk/alice/source1', 'streamdesk/alice/output'})
        self.assertIn(self.config['authInternalUsers'][1], config['authInternalUsers'])
        self.assertNotIn(self.config['authInternalUsers'][2], config['authInternalUsers'])
        self.assertEqual(self.media.read_text(), yaml.safe_dump(self.config))

    def test_recovery_without_env_requires_owned_accounts_for_existing_paths(self):
        self.env.unlink()
        args = self.args()
        installer.validate(args)
        config = copy.deepcopy(self.config)
        installer.prepare_config(args, config)
        config = copy.deepcopy(self.config)
        config['paths']['streamdesk/unknown/live'] = {'source': 'publisher'}
        with self.assertRaisesRegex(ValueError, 'nicht eindeutig'):
            installer.prepare_config(args, config)

    def test_orphaned_media_keys_and_wal_are_preserved_and_restored(self):
        self.data.mkdir()
        for name in ('fernet.key', 'session.key', 'app.db-wal', 'old-video.mp4'):
            (self.data / name).write_bytes(('fixture-' + name).encode())
        args = self.args()
        installer.validate(args)
        folder = self.root / 'backup'
        folder.mkdir()
        with contextlib.redirect_stdout(io.StringIO()):
            previous = installer.quarantine_recovery_data(args, folder)
        self.assertFalse(self.data.exists())
        self.assertTrue((previous / 'old-video.mp4').is_file())
        self.assertEqual(json.loads((folder / 'recovery.json').read_text())['previous_data_dir'], str(previous))
        self.data.mkdir()
        (self.data / 'app.db').write_bytes(b'fixture-new-partial-db')
        installer.restore_recovery_data(args, previous)
        self.assertFalse((self.data / 'app.db').exists())
        self.assertEqual((self.data / 'app.db-wal').read_bytes(), b'fixture-app.db-wal')
        self.assertEqual((self.data / 'fernet.key').read_bytes(), b'fixture-fernet.key')

    def test_database_appearing_after_validation_aborts_without_moving_data(self):
        args = self.args()
        installer.validate(args)
        self.data.mkdir()
        (self.data / 'app.db').write_bytes(b'fixture-created-concurrently')
        folder = self.root / 'backup'
        folder.mkdir()
        with self.assertRaisesRegex(ValueError, 'Inzwischen'):
            installer.quarantine_recovery_data(args, folder)
        self.assertEqual((self.data / 'app.db').read_bytes(), b'fixture-created-concurrently')
        self.assertFalse((folder / 'recovery.json').exists())

    def test_recovery_dry_run_does_not_change_files_or_services(self):
        command = ['--mode', 'attach', '--recover', '--dry-run', '--data-dir', str(self.data),
                   '--app-dir', str(self.app_dir), '--mediamtx-config', str(self.media), '--mediamtx-binary', str(self.binary)]
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        with patch.object(installer.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()) as output:
            installer.main(command)
        run.assert_not_called()
        self.assertIn('Dry run', output.getvalue())
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_backup_failure_restarts_ui_before_any_installation_changes(self):
        args = self.args()
        old = installer.validate(args)
        with patch.object(installer.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, \
             patch.object(installer, 'backup', side_effect=OSError('fixture-backup-failure')), \
             patch.object(installer, 'dependencies') as dependencies:
            with self.assertRaisesRegex(OSError, 'fixture-backup-failure'):
                installer.install(args, old)
        dependencies.assert_not_called()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[-2:], [['systemctl', 'stop', 'streamdesk'], ['systemctl', 'start', 'streamdesk']])
        self.assertFalse(self.data.exists())

    def workflow(self, mode, fail=False):
        self.data.mkdir()
        (self.data / 'orphan.mp4').write_bytes(b'fixture-existing-video')
        (self.data / 'fernet.key').write_bytes(b'fixture-existing-key')
        self.app_dir.mkdir()
        (self.app_dir / 'app.py').write_text('fixture-old-application')
        (self.app_dir / 'venv/bin').mkdir(parents=True)
        for name in ('python', 'pip'):
            (self.app_dir / 'venv/bin' / name).write_text('fixture-runtime')
        for name in ('streamdesk', 'mediamtx'):
            (self.units / (name + '.service')).write_text('fixture-old-' + name + '-unit')
        args = self.args(mode)
        old = installer.validate(args)
        original_env = self.env.read_bytes()
        original_config = self.media.read_bytes()
        calls = []

        def fake_run(command, **kwargs):
            command = [str(value) for value in command]
            calls.append((command, kwargs))
            if command[0] == 'ffmpeg':
                Path(command[-1]).write_bytes(b'fixture-new-standby')
            if len(command) > 1 and command[1].endswith('bootstrap.py'):
                self.assertTrue(args.recover)
                with sqlite3.connect(self.data / 'app.db') as connection:
                    connection.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,prefix TEXT)')
                    connection.execute("INSERT INTO users(prefix) VALUES ('streamdesk/admin/')")
                for name in ('fernet.key', 'session.key'):
                    (self.data / name).write_bytes(b'fixture-new-key')
            return subprocess.CompletedProcess(command, 0)

        def wait(url):
            if fail and url.endswith('/login'):
                raise RuntimeError('fixture-failed-health-check')

        with patch.object(installer, 'dependencies'), patch.object(installer, 'media_service_identity', return_value=(0, 0)), \
             patch.object(installer.os, 'chown'), patch.object(installer.subprocess, 'run', side_effect=fake_run), \
             patch.object(installer, 'wait_url', side_effect=wait), contextlib.redirect_stdout(io.StringIO()), \
             contextlib.redirect_stderr(io.StringIO()):
            if fail:
                with self.assertRaisesRegex(RuntimeError, 'fixture-failed-health-check'):
                    installer.install(args, old)
            else:
                installer.install(args, old)
        backup = next((self.root / 'backups').iterdir())
        self.assertEqual((backup / 'fernet.key').read_bytes(), b'fixture-existing-key')
        self.assertEqual(self.binary.read_bytes(), b'fixture-existing-media-binary')
        self.assertEqual((self.units / 'mediamtx.service').read_text(), 'fixture-old-mediamtx-unit')
        self.assertFalse(any(command[:2] == ['systemctl', 'stop'] and command[-1] == 'mediamtx' for command, _ in calls))
        sync = [kwargs for command, kwargs in calls if '-c' in command and 'synchronize_runtime' in command[-1]]
        self.assertEqual(set(json.loads(sync[0]['input'])), {'streamdesk/alice/source1', 'streamdesk/alice/output'})
        if fail:
            self.assertEqual(self.media.read_bytes(), original_config)
            self.assertEqual(self.env.read_bytes(), original_env)
            self.assertEqual((self.data / 'orphan.mp4').read_bytes(), b'fixture-existing-video')
            self.assertEqual((self.data / 'fernet.key').read_bytes(), b'fixture-existing-key')
            self.assertFalse((self.data / 'app.db').exists())
            self.assertEqual((self.app_dir / 'app.py').read_text(), 'fixture-old-application')
        else:
            self.assertTrue((self.data / 'app.db').is_file())
            self.assertTrue((self.data / 'initial-login.txt').is_file())
            self.assertEqual((self.data / 'initial-login.txt').stat().st_mode & 0o777, 0o600)
            previous = next(self.root.glob('data-before-recovery-*'))
            self.assertEqual((previous / 'orphan.mp4').read_bytes(), b'fixture-existing-video')
            self.assertEqual(yaml.safe_load(self.media.read_text())['paths'], {'camera': self.config['paths']['camera']})
            self.assertTrue(json.loads((self.data / 'installation.json').read_text())['recovered'])

    def test_attach_recovery_creates_new_login_and_keeps_existing_media_service(self):
        self.workflow('attach')

    def test_update_recovery_also_runs_first_admin_bootstrap(self):
        self.workflow('update')

    def test_failed_recovery_restores_original_files_and_orphaned_data(self):
        self.workflow('attach', fail=True)


if __name__ == '__main__':
    unittest.main()
