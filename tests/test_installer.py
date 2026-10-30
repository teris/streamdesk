import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def test_major_target_is_explicit_and_unknown_profile_fails_closed(self):
        self.assertEqual(installer.parse([]).mediamtx_major, 1)
        args = installer.parse(['--mediamtx-major', '2'])
        with self.assertRaisesRegex(ValueError, 'kein prüfbares'):
            installer.validate(args)

    def test_runtime_version_probe_fails_closed(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"version":"v1.21.3"}'
        with patch('urllib.request.urlopen', return_value=response):
            self.assertEqual(installer.verify_media_profile('http://127.0.0.1:9997'), '1.21.3')
        response.__enter__.return_value.read.return_value = b'{"version":"v2.0.0"}'
        with patch('urllib.request.urlopen', return_value=response), self.assertRaisesRegex(RuntimeError, 'kein freigegebenes'):
            installer.verify_media_profile('http://127.0.0.1:9997')

    def test_listener_conversion(self):
        self.assertEqual(installer.endpoint(':9997', 9997, 'http'), 'http://127.0.0.1:9997/')
        self.assertEqual(installer.endpoint('0.0.0.0:18554', 8554, 'rtsp'), 'rtsp://127.0.0.1:18554/')
        self.assertEqual(installer.endpoint('[::]:8554', 8554, 'rtsp'), 'rtsp://127.0.0.1:8554/')
        self.assertEqual(installer.port_from(':19935', 1935), 19935)

    def test_fresh_config_uses_own_ports_and_local_control(self):
        args = installer.parse(['--mode', 'standalone', '--api-port', '19997', '--rtsp-port', '18554'])
        config = installer.fresh_config(args)
        self.assertEqual(config['apiAddress'], '127.0.0.1:19997')
        self.assertEqual(config['rtspAddress'], '0.0.0.0:18554')
        self.assertEqual(config['paths'], {})
        self.assertFalse(config['webrtc'])

    def test_attach_preserves_active_ports_and_foreign_paths(self):
        args = installer.parse(['--mode', 'attach'])
        config = {'authMethod': 'internal', 'api': True, 'apiAddress': '127.0.0.1:19997', 'rtsp': True, 'rtspAddress': ':18554',
                  'hls': True, 'hlsAddress': ':18888', 'hlsVariant': 'fmp4', 'rtmp': True, 'srt': True,
                  'paths': {'camera': {'source': 'publisher'}}, 'authInternalUsers': []}
        installer.prepare_config(args, config)
        self.assertEqual(config['apiAddress'], '127.0.0.1:19997')
        self.assertEqual(config['hlsVariant'], 'fmp4')
        self.assertEqual(config['paths'], {'camera': {'source': 'publisher'}})

    def test_reserved_namespace_collision_rejected(self):
        args = installer.parse(['--mode', 'attach'])
        with self.assertRaises(ValueError):
            installer.prepare_config(args, {'paths': {'streamdesk/existing': {}}, 'authInternalUsers': []})

    def test_shell_wrappers_are_valid(self):
        for script in ('install.sh', 'uninstall.sh'):
            subprocess.run(['bash', '-n', str(ROOT / script)], check=True)

    def test_native_storage_is_separate_and_installer_includes_extension(self):
        args = installer.parse(['--mode','standalone'])
        with tempfile.TemporaryDirectory() as temporary:
            args.data_dir=Path(temporary)/'private-data'
            args.data_dir.mkdir(mode=0o700)
            with patch.object(installer,'media_service_identity',return_value=(123,456)), patch.object(installer.os,'chown') as chown:
                directory=installer.native_storage(args,{})
                self.assertEqual(directory,Path(temporary)/'private-data-native')
                self.assertEqual(directory.stat().st_mode & 0o2777,0o2770)
                chown.assert_called_once_with(directory,123,456)
                self.assertEqual(args.data_dir.stat().st_mode & 0o777,0o700)
                with self.assertRaises(ValueError):
                    installer.native_storage(args,{'STREAMDESK_NATIVE_ROOT':str(args.data_dir/'unsafe')})
                with self.assertRaises(ValueError):
                    installer.native_storage(args,{'STREAMDESK_NATIVE_ROOT':'/'})
        self.assertIn('media_features.py',installer.FILES)

    def test_services_run_with_fixed_unprivileged_accounts(self):
        args = SimpleNamespace(
            mediamtx_binary=Path('/opt/mediamtx/mediamtx'), mediamtx_config=Path('/opt/mediamtx/mediamtx.yml'),
            mediamtx_service='mediamtx', app_dir=Path('/opt/streamdesk'), env_file=Path('/etc/streamdesk.env'),
            data_dir=Path('/var/lib/streamdesk'), browser_root=Path('/var/lib/streamdesk-browser'),
            native_root=Path('/var/lib/streamdesk-native'), media_user='streamdesk-media',
            media_group='streamdesk-media', ui_user='streamdesk', ui_group='streamdesk',
            shared_group='streamdesk-media')
        media = installer.service_text(args, media=True)
        ui = installer.service_text(args)
        self.assertIn('User=streamdesk-media', media)
        self.assertIn('ProtectSystem=strict', media)
        self.assertIn('User=streamdesk', ui)
        self.assertIn('SupplementaryGroups=streamdesk-media', ui)
        self.assertNotIn('User=root', media + ui)

    def test_storage_permissions_are_limited_to_config_and_native_roots(self):
        args=SimpleNamespace(ui_user='streamdesk',media_user='streamdesk-media',
                             mediamtx_config=Path('/opt/mediamtx/mediamtx.yml'),native_root=Path('/var/lib/streamdesk-native'))
        with patch.object(installer,'run') as run:
            installer.storage_permissions(args)
        commands=[call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][-1],Path('/opt/mediamtx'))
        self.assertIn('u:streamdesk:rwx',commands[0][2])
        self.assertTrue(all(command[-1] in (Path('/opt/mediamtx'),args.native_root) for command in commands))
        self.assertIn('d:u:streamdesk:rwx',commands[1][2])

    def test_root_mediamtx_config_uses_ui_shared_group_instead_of_root_group(self):
        args=SimpleNamespace(ui_user='streamdesk',shared_group='streamdesk')
        with patch.object(installer,'media_service_identity',return_value=(0,0)),patch.object(installer.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=123,pw_gid=456)),patch.object(installer.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=456)):
            self.assertEqual(installer.media_config_permissions(args),(0o660,(123,456)))

    def test_api_tls_is_explicit_and_preserves_foreign_paths(self):
        args = installer.parse(['--mode', 'attach', '--enable-api-tls', '--api-cert', '/tmp/api.crt', '--api-key', '/tmp/api.key'])
        args.mediamtx_config = Path('/etc/mediamtx/mediamtx.yml')
        config = {'authMethod': 'internal', 'authInternalUsers': [], 'paths': {'foreign': {'source': 'publisher'}}}
        installer.prepare_config(args, config)
        self.assertTrue(config['apiEncryption'])
        self.assertEqual(config['apiServerCert'], '/etc/mediamtx/.streamdesk-api.crt')
        self.assertEqual(config['paths'], {'foreign': {'source': 'publisher'}})

    def test_remote_unit_has_no_local_mediamtx_dependency(self):
        args = SimpleNamespace(
            mediamtx_binary=Path('/usr/bin/false'), mediamtx_config=Path('/var/lib/streamdesk/remote.yml'),
            mediamtx_service='mediamtx', app_dir=Path('/opt/streamdesk'), env_file=Path('/etc/streamdesk.env'),
            data_dir=Path('/var/lib/streamdesk'), browser_root=Path('/var/lib/streamdesk-browser'),
            native_root=Path('/var/lib/streamdesk-native'), ui_user='streamdesk', ui_group='streamdesk',
            shared_group='streamdesk', remote_mediamtx=True)
        unit = installer.service_text(args)
        self.assertIn('After=network-online.target\n', unit)
        self.assertNotIn('mediamtx.service', unit)


if __name__ == '__main__':
    unittest.main()


class PlaybackInstallerTests(unittest.TestCase):
    def test_attach_playback_changes_only_when_explicitly_requested(self):
        import copy
        config={'authMethod':'internal','authInternalUsers':[], 'api':True,'hls':True,'rtsp':True,'rtmp':True,'srt':True,
                'playback':True,'playbackAddress':'127.0.0.1:19996','paths':{'foreign':{'source':'publisher'}}}
        original=copy.deepcopy(config)
        installer.prepare_config(installer.parse(['--mode','attach']),config)
        self.assertEqual(config['playbackAddress'],original['playbackAddress'])
        self.assertEqual(config['paths'],original['paths'])
        args=installer.parse(['--mode','attach','--enable-playback','--playback-port','29996'])
        installer.prepare_config(args,config)
        self.assertTrue(config['playback'])
        self.assertEqual(config['playbackAddress'],'127.0.0.1:29996')
        self.assertFalse(installer.fresh_config(installer.parse(['--mode','standalone']))['playback'])

class FTPInstallerTests(unittest.TestCase):
    def test_ftp_units_use_private_auth_tls_and_separate_listener(self):
        a=installer.parse([]);a.app_dir=Path('/opt/streamdesk');a.data_dir=Path('/var/lib/streamdesk')
        identity=SimpleNamespace(pw_name='streamdesk',pw_uid=123,pw_gid=456)
        units=installer.ftp_units(a,identity)
        self.assertIn('-Y 3',units['streamdesk-ftp']);self.assertIn('-S 0.0.0.0,2121',units['streamdesk-ftp'])
        self.assertIn('extauth:/run/streamdesk-ftp/auth.sock',units['streamdesk-ftp'])
        self.assertIn('pure-authd -u 123 -g 456',units['streamdesk-ftp-auth']);self.assertNotIn('pure-pw',str(units))
        self.assertIn('stats:/var/log/streamdesk-ftp/transfers.log',units['streamdesk-ftp'])
    def test_ftp_program_modules_ship_in_installer(self):
        for name in ('ftp_auth.py','ftp_features.py','studio_features.py'):self.assertIn(name,installer.FILES)
        self.assertTrue(installer.parse(['--enable-ftp']).enable_ftp)
    def test_ftp_install_generates_only_owned_units_and_private_certificate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);a=installer.parse([]);a.app_dir=root/'app';a.data_dir=root/'data';a.data_dir.mkdir();(a.app_dir/'scripts').mkdir(parents=True);a.ingest_host='ftp.example.test'
            etc=root/'etc';units=root/'units';etc.mkdir();units.mkdir();identity=SimpleNamespace(pw_name='streamdesk',pw_uid=123,pw_gid=456)
            (etc/'streamdesk-ftp.pem').write_text('fixture-existing-certificate')
            with patch.object(installer,'ENV_DIR',etc),patch.object(installer,'SYSTEMD_UNIT_DIR',units),patch.object(installer.os,'chown'),patch.object(installer,'run') as run,patch.object(installer,'FTP_LOG_ROOT',root/'logs'),patch.object(installer,'wait_ftp'):
                installer.configure_ftp(a,identity)
            self.assertEqual({p.name for p in units.iterdir()},{'streamdesk-ftp.service','streamdesk-ftp-auth.service'})
            self.assertEqual((etc/'streamdesk-ftp.pem').read_text(),'fixture-existing-certificate')
            self.assertEqual((etc/'streamdesk-ftp.pem').stat().st_mode&0o777,0o600)
            commands=[call.args[0] for call in run.call_args_list]
            self.assertFalse(any('pure-ftpd.service' in str(command) for command in commands))
            self.assertEqual((etc/'streamdesk-ftp.env').stat().st_mode&0o777,0o600)

    def test_ftp_readiness_requires_a_greeting_and_healthy_owned_services(self):
        args=installer.parse([]);connection=MagicMock();connection.__enter__.return_value=connection
        with patch.object(installer.socket,'create_connection',return_value=connection),patch.object(installer,'run') as run,patch.object(installer.time,'sleep'):
            connection.recv.return_value=b'220 Ready\r\n';installer.wait_ftp(args)
            run.assert_called_once_with(['systemctl','is-active','--quiet','streamdesk-ftp-auth','streamdesk-ftp'])
            connection.recv.return_value=b'Not an FTP greeting'
            with self.assertRaisesRegex(RuntimeError,'antwortet nicht'):installer.wait_ftp(args)

    def test_dependency_install_never_removes_an_existing_ftp_server(self):
        args=installer.parse([])
        with patch.object(installer.shutil,'which',return_value='/fixture/program'),patch.object(installer.Path,'is_file',return_value=True),patch.object(installer,'run') as run:
            installer.dependencies(args)
            command=run.call_args_list[1].args[0];self.assertIn('--no-remove',command);self.assertIn('pure-ftpd',command)
            run.reset_mock();args.disable_ftp=True;installer.dependencies(args)
            command=run.call_args_list[1].args[0];self.assertIn('--no-remove',command);self.assertNotIn('pure-ftpd',command)

    def test_ftp_notice_describes_package_install_and_ingest_before_update(self):
        args=installer.parse(['--mode','update','--ingest-host','135.125.128.226'])
        notice=installer.ftp_install_notice(args)
        self.assertIn('VOR DEM UPDATE',notice);self.assertIn('Pure-FTPd (FTP-Server)',notice);self.assertIn('installiert',notice)
        self.assertIn('135.125.128.226',notice);self.assertIn('2121',notice);self.assertIn('30000:30049',notice)
        self.assertIn('--disable-ftp',notice)
        args.disable_ftp=True;self.assertIn('nicht neu installiert',installer.ftp_install_notice(args))
        args.disable_ftp=False;args.skip_system_packages=True;self.assertIn('ausdrücklich übersprungen',installer.ftp_install_notice(args))
    def test_ftp_notice_precedes_any_installer_mutation_in_main(self):
        args=installer.parse(['--mode','update','--ingest-host','ingest.example.test']);args.public_url='https://panel.example.test';args.mediamtx_config=Path('/opt/mediamtx/mediamtx.yml')
        import contextlib,io
        output=io.StringIO()
        def stop_before_changes(*_):
            self.assertIn('Pure-FTPd (FTP-Server)',output.getvalue());raise RuntimeError('stop before mutations')
        with patch.object(installer,'parse',return_value=args),patch.object(installer,'validate',return_value={}),patch.object(installer.os,'geteuid',return_value=0),patch.object(installer.Path,'exists',return_value=True),patch.object(installer.Path,'read_text',return_value='ID=debian\nVERSION_ID=13\n'),patch.object(installer.sys.stdin,'isatty',return_value=False),patch.object(installer,'install',side_effect=stop_before_changes),contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'stop before mutations'):installer.main([])
