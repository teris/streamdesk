"""Read-only account detection and JSON credentials for container first setup."""
import json
import os
from pathlib import Path
import re
import sqlite3
import sys


def existing_users(directory):
    database=Path(directory)/'app.db'
    if not database.exists():return False
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
            return False
        return connection.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None


def credentials(environment):
    username=environment.get('STREAMDESK_ADMIN_USER','').lower().strip()
    password=environment.get('STREAMDESK_ADMIN_PASSWORD','')
    if not re.fullmatch(r'[a-z][a-z0-9_-]{2,29}',username) or len(password)<12:
        raise ValueError('Ersteinrichtung benötigt einen gültigen Administratornamen und mindestens zwölf Passwortzeichen.')
    return {'username':username,'password':password}


if __name__=='__main__':
    try:
        if sys.argv[1:] == ['state']:
            print('ready' if existing_users(os.environ['STREAMDESK_DATA']) else 'empty')
        elif sys.argv[1:] == ['credentials']:
            print(json.dumps(credentials(os.environ)))
        else:
            raise ValueError('Erwartet state oder credentials.')
    except (OSError,sqlite3.Error,ValueError,KeyError):
        raise SystemExit('Container-Ersteinrichtung konnte nicht geprüft werden. Datenbank und Administrator-Einstellungen prüfen; vorhandene Daten werden nicht zurückgesetzt.') from None
