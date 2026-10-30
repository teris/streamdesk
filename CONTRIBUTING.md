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

Die getrennten Plattform-Einstellungen und die Discord-Einrichtung lassen sich ohne MediaMTX und ohne externes Discord-Konto im Browser prüfen:

```bash
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/settings_smoke.py
.venv/bin/python tests/services_smoke.py
```

Optional schreibt `--screenshots-dir /pfad/zum/vorschauordner` Ansichten mit ausschließlich lokalen Testdaten.

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

## Zusätzliche Regressionen vom 27. Oktober 2026

```bash
.venv/bin/python tests/account_smoke.py
.venv/bin/python tests/permissions_smoke.py
.venv/bin/python tests/on_demand_smoke.py --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg
```

Der Kontotest nutzt Chromium mit virtuellem WebAuthn-Authenticator auf `localhost`: Registrierung, Anmeldung, Löschung, Szenenspeicherung und Erhalt ungespeicherter Automationsformulare. Der Berechtigungstest benötigt `setfacl`/`getfacl` aus dem Paket `acl` und prüft temporäre Verzeichnisse ohne root oder Systemkontenänderungen. Der Bedarfsquellentest prüft tatsächliches Videobild, Aktivierung durch einen Programmleser und anschließende Freigabe der Pull-Verbindung. Der Playback-Test prüft zusätzlich persistente Clips beider Segmentformate, Eigentümergrenzen und Löschen. Diese Tests senden keine externen Nachrichten oder öffentlichen Streams.

## Versionsnummern und Lieferpakete

Jedes neue ausgelieferte Updatepaket erhält eine höhere Versionsnummer. Ein bereits geliefertes Paket wird nicht mit geänderten Funktionen unter derselben Versionsnummer ersetzt. Vor dem Packen VERSION erhöhen, neue Änderungen in einem eigenen CHANGELOG-Abschnitt erfassen und README sowie Installationsbeispiele angleichen. Anwendung und Installer lesen ihre Versionsnummer aus VERSION; Browsertests verwenden dieselbe Quelle.

## Studio-/Playlist-Integrationstest ab 2.0.0-rc1

```bash
.venv/bin/python tests/studio_smoke.py \
  --mediamtx /pfad/zu/mediamtx \
  --ffmpeg /pfad/zu/ffmpeg \
  --ffprobe /pfad/zu/ffprobe
```

Prüft einen gemeinsamen Source-2-Playlist-Encoder für zwei verschieden geroutete lokale Ausgänge, die tatsächlich eingeblendete Wiederholungskennzeichnung, geplanten Ausgangsstart ohne Anmeldung/Live-Eingang, Source-1/2-Vorrang, gespeichertes Fortsetzen und eine durchgehende dekodierbare Aufnahme. Zusätzlich: Zeitfensterende, echte FTP-Dateiumwandlung, Massen-Auswahl, Playlist-Bearbeitung/-Löschung, sofort nutzbarer Planer, grafische Wochen-/Tagesansicht, dauerhafte Expertenwahl und Mobilansichten. FFmpeg benötigt libx264, AAC und drawtext mit DejaVu-Schriften. `playlists_smoke.py` bleibt ein kompatibler Aufruf für diesen aktuellen Test. Alle Streamingziele sind temporäre Loopback-Senken.

## Upload- und Medienverwaltung ab 1.1.8

```bash
.venv/bin/python tests/uploads_smoke.py --ffmpeg /pfad/zu/ffmpeg --ffprobe /pfad/zu/ffprobe
```

Der Chromium-Test drosselt die lokale Upload-Verbindung und prüft Mehrfachauswahl, Upload-/Encoderfortschritt, Menüwechsel während der Warteschlange, Weiterverarbeitung nach fehlerhaftem Video, Umbenennen in beiden Bibliotheken, bestätigtes Entfernen von Playlist-Verweisen, geschützte Dateien und Mobilansichten. Es werden ausschließlich lokale Testdateien verwendet.


## Isolierter echter FTPS-Test

```bash
sudo .venv/bin/python tests/ftp_smoke.py \
  --pure-ftpd /pfad/zu/pure-ftpd --pure-authd /pfad/zu/pure-authd \
  --ffmpeg /pfad/zu/ffmpeg --ffprobe /pfad/zu/ffprobe \
  --uid 1000 --gid 1000
```

Nur in einer lokalen Testumgebung ausführen; UID/GID müssen ein vorhandenes unprivilegiertes Testkonto bezeichnen. Der Test startet eigene Pure-FTPd-Prozesse auf einem freien Loopback-Port und verwendet temporäre Konten/Dateien. Er prüft FTPS-Pflicht, Chroot, Upload in Unterordner, automatische Umwandlung, Passwortwechsel und gesperrte Zugänge. Es werden keine systemd-Dienste installiert oder öffentliche Konten verwendet. Root ist ausschließlich für Chroot und den Identitätswechsel dieser Testprozesse nötig.


## Bibliothek und FTP-Oberfläche ab rc2

```bash
.venv/bin/python tests/library_ui_smoke.py
.venv/bin/python tests/ftp_ui_smoke.py
.venv/bin/python tests/studio_smoke.py --legacy --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg --ffprobe /pfad/zu/ffprobe
```

Der Bibliothekstest prüft getrennte Medien-/Playlist-Ansichten, gefilterte Video-Mehrfachauswahl, vorhandene verschachtelte Playlists, erhaltene Entwürfe, Seitenaufteilung und 100 Ordner mit mehr als 600 Videos. Der FTP-Oberflächentest prüft tatsächliches Speichern, Ingest-Verbindungsdaten, bestehende Freigaben und die persönliche Passwortverwaltung unter „Mein Konto“. `--screenshots-dir /zielordner` speichert Vorschauen. Der Studio-Test verwendet hörbaren Testton, zwei lokale RTMP-Senken und tatsächlich dekodiertes Browser-WebRTC-Audio; `--legacy` prüft zusätzlich das alte Pfadschema ohne Benutzerpräfix. Die FTPS-Prüfung umfasst sichtbare Web-Uploads, Uploads direkt in die Bibliotheksordner, erhaltene unvollständige Uploads, automatische Umbenennung bei Dateikollisionen und geschützte fertige Videodateien.


Für den anspruchsvolleren Playlist-/Vorschautest zusätzlich `--complex` verwenden. Die lokale Prüfung verwendet bewegte Rauschbilder, echten dekodierten Testton und die sichtbaren Tonregler. Ohne eine pauschale Autoplay-Freigabe wird der Ton per Benutzerklick aktiviert. Die Audio-Messung liest einen aufgenommenen Browser-Medienstrom, ohne den normalen Wiedergabeweg umzuleiten. `program_smoke.py` prüft die Tonbedienung auch bei deaktiviertem Expertenmodus und neue Videoframes nach Quellenwechseln.

`--startup-delay 8` verzögert im Studio-Test ausschließlich den gemeinsamen Playlist-Encoder. Der Test bestätigt, dass derselbe Prozess die frühere Fünf-Sekunden-Grenze überlebt, der Controller weiterhin reagiert und anschließend Bild/Ton an beiden Senken ankommen. Die RTMP-Verbindungen müssen bei Live-Übernahme und Playlist-Fortsetzung erhalten bleiben.

`tests/playlist_resume_smoke.py --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg --ffprobe /pfad/zu/ffprobe` prüft den in rc5 behobenen Einstieg am Ende einer etwa 49 Minuten langen Playlist. Fünf lokale Dateien und der konkrete Fortsetzpunkt bilden den Fehler nach. Der Test erwartet tatsächlich steigende RTSP-Datenzähler, hörbaren PCM-Ton und denselben Publisher über mehr als zehn Sekunden; eine bloße Pfadanmeldung oder ein einzelner Frame genügt nicht. Diesen Test insbesondere mit FFmpeg 7.1.x ausführen.
