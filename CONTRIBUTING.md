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

Für einen zusätzlichen lokalen Medientest stehen `tests/media_smoke.py` und Playwright/Chromium zur Verfügung:

```bash
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/media_smoke.py --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg
```

Dieser Test erzeugt temporäre Konten und Testmedien, verwendet ausschließlich automatisch gewählte Loopback-Ports und entfernt seine Prozesse/Daten anschließend. Er verändert keine vorhandenen Dienste. Geprüft werden echte Weiterleitungen, Quellensteuerung, Expertenprüfung, Theme/Mobilansicht, WHIP, WHEP, öffentlicher HLS-Player und native Segmente. Das Testskript schaltet die sonst gesperrten lokalen Ausgangsadressen nur innerhalb des Tests ausdrücklich frei. Öffentliches Streaming ist kein Bestandteil dieses Tests.

Der Wiederaufsetzungsweg lässt sich ohne systemd mit temporären Daten gegen ein echtes lokales MediaMTX prüfen:

```bash
.venv/bin/python tests/recovery_smoke.py --mediamtx /pfad/zu/mediamtx
```

Dieser Test prüft neue Administrator-Anmeldung und Schlüssel, den Erhalt verwaister Dateien/fremder Pfade und die auf eigene alte Pfade begrenzte Laufzeitbereinigung. Die Unit-Tests simulieren zusätzlich den Installer einschließlich erfolgreichem Ablauf und Rücknahme eines fehlgeschlagenen Wiederaufsetzens.

Für authentifiziertes SRT-Publish, Quellenumschaltung und HLS-Vorschau gibt es einen eigenen lokalen Test:

```bash
.venv/bin/python tests/srt_smoke.py --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg
```

Dabei wird 25 Sekunden ausschließlich auf Loopback gesendet. Die lokale Dienstberechtigung darf diesen SRT-Eingang im Test nicht anonym beschreiben; die von StreamDesk ausgegebenen Medienzugangsdaten müssen greifen.

Vor einem Release den Installer mit einer neuen Instanz und dem Attach-Modus prüfen. Kontofreigaben an echte Plattformen erfordern Testkonten; öffentliches Senden ist kein automatischer Bestandteil der Tests.

## Welle-0-Medientest ab rc.4

```bash
.venv/bin/python tests/expansion_smoke.py \
  --mediamtx /pfad/zu/mediamtx \
  --ffmpeg /pfad/zu/ffmpeg \
  --ffprobe /pfad/zu/ffprobe
```

Der Test prüft Source 3 und Pull mit echter Engine, Auto/manuelle Wahl, drei Custom-Ziele neben den festen Plattform-Slots, beide Aufnahmeformate mit dekodierter Playback-Antwort, Benutzergrenzen auch direkt an MediaMTX sowie Desktop/Mobilansichten. Er nutzt temporäre Daten und ausschließlich Loopback-Ziele. Lokale Pull-/Forward-Adressen werden nur innerhalb dieses Tests freigegeben.

## Programm-Regression ab rc.5

```bash
.venv/bin/python tests/program_smoke.py \
  --mediamtx /pfad/zu/mediamtx \
  --ffmpeg /pfad/zu/ffmpeg \
  --ffprobe /pfad/zu/ffprobe
```

Zwei Quellen mit B-Frames und unterschiedlichen Auflösungen werden parallel gestartet. Der Test prüft die Dashboard- und WebRTC-Programmvorschau ohne Streamingziel, tatsächliche Bildfarben, Audio-Track, dieselbe laufende Aufnahme über Quellenverlust/Wechsel und Offline-Fallback sowie Weiterleitungs-Start/Stopp. Abschließend werden Laufzeit, Audio und Dekodierung der fertigen Aufnahme geprüft.

## Routing- und Kontotest ab rc.6

```bash
.venv/bin/python tests/routing_smoke.py \
  --mediamtx /pfad/zu/mediamtx \
  --ffmpeg /pfad/zu/ffmpeg \
  --ffprobe /pfad/zu/ffprobe
```

Prüft die Routingmatrix mit fünf Quellen, sechs lokalen Senken und echter Bildprüfung, Programmaufnahme, getrennten Zugangsdatenkarten, Programmauswahl/-link, Passwortwechsel beider Rollen, Löschung eines deaktivierten Benutzers sowie Mobilansichten. `expansion_smoke.py` konzentriert sich ab rc.6 auf privates Playback; `program_smoke.py` prüft Aufnahme- und Vorschaukontinuität, `media_smoke.py` die bisherigen Protokoll-/UI-Funktionen.
