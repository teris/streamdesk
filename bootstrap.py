"""Installer-only first administrator creation. Password arrives over stdin."""
import json
import sys
import app

if app.rows('SELECT id FROM users'):
    raise SystemExit('Benutzer existieren bereits. Keine Ersteinrichtung durchgeführt.')
settings = json.loads(sys.stdin.readline())
app.add_user(settings['username'], settings['password'], admin=True)
print('Administrator wurde eingerichtet. Es wurde kein Streamingziel gestartet.')
