import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
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


if __name__ == '__main__':
    unittest.main()
