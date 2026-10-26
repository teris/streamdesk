import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
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
                self.assertEqual(directory.stat().st_mode & 0o777,0o750)
                chown.assert_called_once_with(directory,123,456)
                self.assertEqual(args.data_dir.stat().st_mode & 0o777,0o700)
                with self.assertRaises(ValueError):
                    installer.native_storage(args,{'STREAMDESK_NATIVE_ROOT':str(args.data_dir/'unsafe')})
                with self.assertRaises(ValueError):
                    installer.native_storage(args,{'STREAMDESK_NATIVE_ROOT':'/'})
        self.assertIn('media_features.py',installer.FILES)


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
