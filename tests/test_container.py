import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('container_bootstrap',Path(__file__).resolve().parents[1]/'scripts/container_bootstrap.py')
bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)


class ContainerBootstrapTests(unittest.TestCase):
    def test_partial_database_can_retry_first_account_without_overwriting_existing_users(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            self.assertFalse(bootstrap.existing_users(root))
            self.assertFalse((root/'app.db').exists())
            with sqlite3.connect(root/'app.db') as connection:
                connection.execute('CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT)')
            self.assertFalse(bootstrap.existing_users(root))
            with sqlite3.connect(root/'app.db') as connection:
                connection.execute("INSERT INTO users VALUES (1,'existing-admin')")
            self.assertTrue(bootstrap.existing_users(root))
            with sqlite3.connect(root/'app.db') as connection:
                self.assertEqual(connection.execute('SELECT username FROM users').fetchone()[0],'existing-admin')

    def test_quoted_password_is_serialized_exactly_and_weak_settings_rejected(self):
        password='Fixture-"quoted"-\\-Password-123'
        value=bootstrap.credentials({'STREAMDESK_ADMIN_USER':'Admin','STREAMDESK_ADMIN_PASSWORD':password})
        self.assertEqual(json.loads(json.dumps(value))['password'],password)
        for user,secret in (('bad name','Long-Fixture-Password-123'),('admin','short')):
            with self.assertRaises(ValueError):bootstrap.credentials({'STREAMDESK_ADMIN_USER':user,'STREAMDESK_ADMIN_PASSWORD':secret})

    def test_corrupt_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'app.db';path.write_bytes(b'corrupt fixture')
            with self.assertRaises(sqlite3.DatabaseError):bootstrap.existing_users(Path(temporary))
            self.assertEqual(path.read_bytes(),b'corrupt fixture')
