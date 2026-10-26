# Mitwirken

Python 3.11 oder neuer verwenden. Für lokale Prüfungen ein virtuelles Environment außerhalb der eigentlichen Laufzeitdaten anlegen:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
bash -n install.sh uninstall.sh
.venv/bin/python -m compileall -q app.py integrations.py media_config.py scripts
```

Die Unit-Tests verwenden temporäre Dateien und veröffentlichen weder Streams noch Chatnachrichten. Native MediaMTX-Integrationstests benötigen gesonderte Testports und dürfen keine vorhandene produktive Konfiguration übernehmen.

Neue Funktionen müssen Benutzergrenzen beachten. API-Anfragen müssen auf den angemeldeten Benutzer begrenzt bleiben; Widgets dürfen keine Schreibrechte erlangen. Geheimnisse werden ausschließlich verschlüsselt gespeichert und gehören nicht in Logs oder Beispieldaten.

Vor einem Release den Installer mit einer neuen Instanz und dem Attach-Modus prüfen. Kontofreigaben an echte Plattformen erfordern Testkonten; öffentliches Senden ist kein automatischer Bestandteil der Tests.
