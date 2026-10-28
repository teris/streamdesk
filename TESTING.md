# Prüfbericht: StreamDesk 1.1.8

Die Unit-Tests sind für Linux ausgelegt; insbesondere verwenden Anwendung und Installer das POSIX-Modul `pwd`. Reine Windows-Python-Läufe sind daher kein unterstützter Testpfad.

Die Unit-Tests und die reinen Einstellungs-/Dienst-Browsertests fixieren ausschließlich die Signierzeit ihrer Testsitzungen, damit rückwärts korrigierte Uhren auf dem Testhost keine zufälligen Abmeldungen auslösen. Die Sitzungsprüfung der Anwendung bleibt unverändert.

## Mehrfachuploads und Medienverwaltung in 1.1.8

180 Unit-Tests bestehen. Die elf zusätzlichen Fälle prüfen private Upload-Aufträge, wiederholbare Upload-Anfragen ohne doppelte Umwandlung, tatsächliche Encoder-Fortschritte, Zeitlimits und Wiederanlauf nach Serverneustart. Umbenennen erhält Dateien, Playlist-Verweise und Wiedergabepositionen. Fremdzugriffe und Anfragen ohne CSRF werden abgelehnt. Löschen prüft aktuelle Verwendungen, bestätigt das Entfernen aus inaktiven Playlists und schützt laufende sowie letzte Videos zugeordneter Playlists. Unbenutzte Videos können auch während eines anderen Uploads gelöscht werden.

`tests/uploads_smoke.py` wurde mit FFmpeg/FFprobe 7.0.2 und Chromium 156 ausgeführt. Ein normaler Benutzer wählt drei Dateien gemeinsam aus. Bei gedrosselter lokaler Verbindung sind Zwischenstände des Uploads sichtbar; die echte Umwandlung liefert eigene Prozentwerte. Die Warteschlange läuft beim Menüwechsel weiter. Eine defekte Datei wird gemeldet, danach wird die nächste Datei verarbeitet. Fertige Videos haben H.264/AAC einschließlich stiller Audiospur bei fehlendem Ton. Beide Bibliotheken erlauben Umbenennen, bestätigtes Löschen entfernt Playlist-Verweise und die Datei, geschützte Videos zeigen den Grund. Die Mobilansichten bestehen bei 390 Pixeln ohne Seitenüberlauf oder JavaScript-Fehler.

Die echten Playlist-/Programmtests und der Einstellungs-Browsertest bestehen erneut. Durchgehende Aufnahmen, Quellenpriorität, getrennte Ausgänge und Fortsetzen nach einer Live-Unterbrechung bleiben erhalten. Der zusätzliche README-Screenshot zeigt die tatsächlich laufende Umwandlung aus dem Upload-Test.

## Playlists und Zeitpläne in 1.1.7

169 Unit-Tests bestehen. Die 17 zusätzlichen Fälle prüfen normale Medienverwaltung gegenüber Experten-Ausspielung, CSRF und Mandantengrenzen, Ordnerzyklen/Namenskollisionen, Reihenfolge und Revisionen, zehnminütige Ausfallverzögerung, Live-Vorrang, getrennte stabile Ausgangsprogramme, zusätzliche Quellen, Mitternachts-/Wochenwechsel, die wiederholte Stunde der Zeitumstellung, Überschneidungen, Löschschutz, persistente Positionen, manuelle Stopps, Dienstsperren und den erweiterten Uploadpfad.

`tests/playlists_smoke.py` wurde mit MediaMTX 1.21.3, FFmpeg/FFprobe 7.0.2 und Chromium 156 ausgeführt. Zwei echte lokale Ausgänge liefern unterschiedliche Playlist-Bilder; wiederholte Schleifen behalten denselben Publisher. Source 1 übernimmt vor Source 2, danach setzen die Playlists an der gespeicherten Position fort. Eine durchgehende Programmaufnahme bleibt derselbe Prozess und lässt sich anschließend dekodieren. Geprüft werden außerdem automatischer Start in einem neuen Zeitfenster, Ende des automatisch gestarteten Ausgangs, manueller Stopp ohne sofortigen Neustart sowie unveränderte fremde Pfade.

Der Browser prüft Ordner-/Playlist-Erstellung, Reihenfolge speichern, Erhalt ungespeicherter Eingaben, einen echten MP4-Upload mit Hintergrundumwandlung in den gewählten Ordner, Zeitplanformular und Mobilansichten mit 390 Pixeln. Alle Medien und Streamingziele sind temporäre lokale Testdaten; öffentliche Twitch-/YouTube-Konten werden nicht angesprochen. Die neuen README-Screenshots stammen aus diesem Test.

## Zentrale Dienstfreigaben in 1.1.6

152 Unit-Tests bestehen. 13 zusätzliche Unit-Tests gegenüber 1.1.5 prüfen Administratorrechte ohne Expertenmodus, CSRF, strikte Eingaben, Persistenz, gesperrte APIs, erhaltene Zugangsdaten und Auswahl, unberührte fremde MediaMTX-Pfade auch beim Legacy-Präfix, verschachtelte native Aufnahme-/Routingpausen, angehaltene Hintergrundaufträge, wiederverwendbare Zuschauerlinks und erneuten Abgleich nach einem MediaMTX-Ausfall. Eine WebRTC-Sperre darf die Programm-Engine nicht durch verbliebene Vorschau-Leser unterbrechen.

`tests/services_smoke.py` verwendet zwei getrennte Chromium-Sitzungen für Administrator und normalen Benutzer. Geprüft werden globales Sperren und Freigeben ohne Neuanmeldung, ausblendbare Dienstgruppen, gesperrte Direktaufrufe, unveränderte Zugangsdaten, unabhängige Automation-/Benachrichtigungsfreigaben und mobile Ansichten. Die Discord-Antworten sind lokale Testdaten.

Der erweiterte echte MediaMTX-Test prüft zusätzlich den Stopp nur des gesperrten Plattformausgangs bei weiterlaufendem anderem Ausgang, erhaltene Streamschlüssel, ausdrücklichen Neustart nach Freigabe, native Aufnahmepause mit Wiederaufnahme sowie die weiterlaufende HLS-Programmvorschau bei gesperrtem WebRTC.

## Einstellungen und Discord in 1.1.5

Zum Stand 1.1.5 bestanden 139 Unit-Tests. Geprüft werden die getrennten Einstellungen für Streaming-Auswahl, Twitch, YouTube, eigenen Anbieter und Darstellung, die serverseitige Expertensperre für Discord-Einrichtung einschließlich CSRF und Mandantengrenzen sowie die gemeinsame Versionsquelle für API, Oberfläche und Browser-Cache.

`tests/settings_smoke.py` prüft im echten Chromium das unabhängige Speichern und Entfernen der drei Standardziele, Auswahl für den nächsten Stream, getrennte Untermenüs, den fünfstufigen Discord-Leitfaden, ungültige Kanal-IDs, das Leeren des Tokens nach dem Speichern und die weiterhin verfügbare Chatnutzung bei ausgeschaltetem Expertenmodus. Alle neuen Seiten werden bei 390 Pixeln in hellem und dunklem Theme auf Seitenüberlauf geprüft. Discord-Antworten sind lokale Testdaten; es wird kein externer Bot verbunden.

Die bisherigen Medien- und Konto-Browsertests prüfen weiterhin die Programm-/WebRTC-Vorschau, Zielsteuerung, Aufnahme, Themes sowie Passkeys, Szenen und den Erhalt ungespeicherter Formulare. Die nachfolgenden Abschnitte dokumentieren die technische Grundlage und frühere Versionen.

## Prüfung des erweiterten Arbeitsstands am 27. Oktober 2026

136 Unit-Tests bestehen. Zusätzlich wurden Programm-/Routing-/Protokoll-Smokes, fMP4-/MPEG-TS-Playback einschließlich persistenter Clips, SRT, ein echter Bedarfs-Pull, lokale Aufnahme-ACLs sowie Browser-Passkeys/Szenen/Formularerhalt geprüft. Neue Prüfskripte: `account_smoke.py`, `permissions_smoke.py`, `on_demand_smoke.py`. Details, konkrete Versionen und Einschränkungen stehen im [Reviewbericht](docs/REVIEW_2026-10-27.md).

Die folgenden Abschnitte dokumentieren die frühere rc.6-/1.1.0-Basis. Die dort genannte Zahl von 80 Unit-Tests ist historisch; der aktuelle Arbeitsstand enthält zusätzlich die inzwischen ergänzten Funktionen und Regressionen.

## Feste Standards, Routing je Ausgang und Kontooberfläche

80 Unit-Tests bestehen. Neue Prüfungen decken feste Standardquellen, Expertensperren, zusätzliche Konten, die vollständige vom Benutzer bestätigte Routingmatrix, Priorität 1/2 vor Zusatzquellen, Rangänderung ohne neue Programmidentität, Mandantengrenzen, unzugeordnete Ausgänge, nicht wiederverwendete Quellenkennungen, sichere Migration auch bei kurzzeitig fehlender MediaMTX-API, wiederholbare Übernahme tatsächlich genutzter Legacy-Quellen und nativer Programmaufnahme sowie Passwortwechsel beider Kontotypen ab. Kontolöschung benötigt deaktivierten Benutzer und korrekte Namensbestätigung, schützt aktive/eigene Konten und laufende Verarbeitung, erhält Medienarchive und vergibt alte Benutzer-IDs nicht neu. Entfernte Streamschlüssel behalten zusätzliche Ausgangsdefinitionen und Zuordnungen. Ein Paginationstest schützt den Pfadabgleich bei großen Programmhistorien.

`tests/routing_smoke.py` wurde mit MediaMTX 1.21.3, FFmpeg 7.0.2, FFprobe 6.1 und Chromium 156 lokal ausgeführt:

- Fünf unterschiedlich gefärbte echte Testquellen und sechs voneinander getrennte lokale Ausgänge. Twitch/YouTube Standard teilen Source 1/2, Anbieter A nutzt 1/2/5, Twitch Zweitkonto Source 3, Anbieter B Source 3/4, YouTube Zweitkonto Source 5.
- Tatsächliche Bilder an den RTSP-Senken werden dekodiert: getrennte Programme, Prioritätsänderung von 3 auf 4 bei B sowie Fallback von Source 1/2 auf 5 bei A. Andere Zielprogramme bleiben unabhängig. Eine laufende Programmaufnahme bleibt derselbe Prozess.
- Echte Browseroberfläche mit fünf getrennten Quellenkarten, ausschließlich pro Quelle eingeblendeten Verbindungsdaten, Quellen-Auswahlbereich, Dashboard-Programmwechsel und korrektem sichtbarem Link.
- Eigener Passwortwechsel eines normalen Benutzers und eines Administrators über „Mein Konto“; aktuelle Sitzung bleibt gültig, ältere Sitzung erhält HTTP 401.
- Administration deaktiviert einen Benutzer und löscht ihn nach Namensbestätigung. Mobilansichten von Dashboard, Quellen, Routing, Ausgängen und Konto haben bei 390 Pixeln keinen horizontalen Seitenüberlauf.
- Keine JavaScript-Laufzeitfehler in den geprüften Ansichten; fremder MediaMTX-Pfad bleibt erhalten.

`program_smoke.py` bestätigt weiterhin eine einzige durchgehende Programmaufnahme über Quellenwechsel mit unterschiedlichen Auflösungen/B-Frames, Offline-Fallback und Ausgangsstart/-stopp. Der Abschluss erfolgt regulär mit FFmpeg-Exit 0; kurze Fragmente und reguläres Beenden erhalten die Schlussdaten. HLS-/WebRTC-Vorschau zeigt die tatsächlichen wechselnden Bilder und Audio ohne Streamingziel.

`media_smoke.py` besteht mit Expertenmodus, Theme/Mobilansicht, festen Standardquellen, WHIP, WHEP, HLS-Freigabe/Widerruf und nativen Segmenten. `expansion_smoke.py` prüft nun gezielt geschütztes fMP4-/MPEG-TS-Playback nach ausdrücklichem Anlegen einer zusätzlichen Quelle; anonyme und fremde Zugriffe werden abgelehnt. `srt_smoke.py` bestätigt 25 Sekunden SRT-Publish und HLS.

Alle Testziele sind temporäre Loopback-Senken. Die zusätzlichen Konten werden mit getrennten Streamschlüsseln über die echte API angelegt; ausschließlich im Test werden deren Ziele vor Start auf lokale Senken umgebogen. Öffentliche Twitch-/YouTube-Konten oder der Benutzer-Server wurden nicht angesprochen. Ausführung siehe `CONTRIBUTING.md`.

## Vorheriger Prüfbericht: StreamDesk 1.1.0-rc.5

## Durchgehende Programmaufnahme und unabhängige Vorschau

71 Unit-Tests bestehen. Die vier neuen Fälle prüfen den dauerhaften Programmpfad über Ziel-Stopp und Konfigurationsabgleich einschließlich nativer Programmaufnahme/Benutzerdeaktivierung, persönliche Authentifizierung im HLS-Proxy, Wiederverwendung und getrennte Bereinigung der WebRTC-Programmprozesse sowie den eigenen WebRTC-Programmpfad mit serverseitiger Expertensperre.

`tests/program_smoke.py` wurde mit echtem MediaMTX 1.21.3, FFmpeg 7.0.2, FFprobe 6.1 und Chromium 156 erfolgreich ausgeführt. Source 1 (rot, 1280×720/30 fps) und Source 2 (blau, 640×360/15 fps) senden parallel, beide mit H.264-B-Frames. Das Offline-Video ist grün. Geprüft werden:

- HLS-Programmvorschau im echten Dashboard nach Navigation aus den Einstellungen; sie lädt nach `about:blank` korrekt neu und liefert Videobilder ohne eingerichtetes Streamingziel.
- WebRTC-Programm mit dekodiertem Videobild und Audio-Track ohne Streamingziel; im Browser werden für beide Vorschauwege die tatsächlichen Farben Rot → Blau → Grün geprüft.
- Verlust der gerade ungenutzten Source 2, deren erneuter Start, Verlust der ausgewählten Source 1 und anschließender Verlust aller Eingänge: Die manuelle Programmaufnahme behält jeweils dieselbe ID, denselben Prozess und Status `recording`.
- Ein lokaler Forward wird mitten in der Aufnahme gestartet und gestoppt. Aufnahme und beide Vorschauwege laufen weiter. Es werden keine öffentlichen Plattformen verwendet.
- Manueller Aufnahmestopp erzeugt eine fertige MP4 mit Audio und einer Dauer, die die gesamte Aufnahmezeit einschließlich der Quellenwechsel abdeckt. Die komplette Datei wird mit FFmpeg dekodiert.

Die Programmaufnahme nutzt lokale Zeitstempel, um Sprünge der Publisher-Zeitbasis beim Wechsel aufzufangen. Die neue Normalisierung auf H.264 Baseline/1080p30 ohne B-Frames verhindert zuvor beobachtete HLS-DTS-Fehler. Dafür benötigt das Programm einen Videoencoder; die WebRTC-Ableitung kopiert dieses Video und wandelt nur Audio nach Opus.

`expansion_smoke.py` besteht erneut mit Source 3/Pull, fünf parallelen lokalen Ausgängen, geschütztem Playback beider Formate, Benutzergrenzen und Mobilansichten. `media_smoke.py` besteht mit den bisherigen Experten-/Theme-/WHIP-/WHEP-/HLS-/Aufnahmetests. `srt_smoke.py` bestätigt erneut 25 Sekunden SRT-Publish einschließlich HLS-Vorschau. Tests verwenden temporäre Daten und Loopback-Ports; auf dem Benutzer-Server wurde nichts verändert.

Ausführung: [CONTRIBUTING.md](CONTRIBUTING.md). Verhalten und CPU-Bedarf: [Expertenmodus](docs/EXPERT_MODE.md#programmaufnahme-und-vorschau-ab-rc5).

## Vorheriger Prüfbericht: StreamDesk 1.1.0-rc.4

## Welle 0: Playback, weitere Quellen und benannte Customs

67 Unit-Tests bestehen. Neu geprüft werden serverseitige Expertensperren einschließlich Administratoren, CSRF, Loopback-Listener und Rollback, Playback mit persönlichen statt globalen Zugangsdaten, Ablehnung fremder Quellen, ungültige Zeitbereiche, verschlüsselte Pull-URLs ohne Rückgabe von Geheimnissen, SSRF-Sperren, wiederholbare Datenbankmigration mit Erhalt alter Custom-Schlüssel/Flags, fünf Custom-Slots und unabhängiger Stopp zwischen drei Customs und den beiden festen Plattform-Slots. Der Pfadabgleich bleibt idempotent und erhält fremde Pfade/Auth sowie bestehende native Aufnahmeeinstellungen.

`tests/expansion_smoke.py` wurde mit echtem MediaMTX 1.21.3, FFmpeg 7.0.2, FFprobe 6.1 und Chromium 156 lokal ausgeführt:

- Source 3 und RTSP-Pull sind in der laufenden Engine manuell wählbar; Auto bevorzugt Source 1 und fällt auf Source 3, danach auf eine eigenständig sendende Pull-Quelle sowie bei fehlenden Eingängen auf das Offline-Video zurück.
- Drei benannte Custom-Ausgänge und die festen Twitch-/YouTube-Slots senden parallel an getrennte lokale RTSP-Senken. Beim Stopp eines Customs bleiben die vier übrigen Ausgänge verbunden.
- Eigene fMP4- und MPEG-TS-Segmente werden aufgezeichnet, über den angemeldeten Playback-Endpunkt geladen und mit FFmpeg dekodiert. Der MPEG-TS-Ersatzweg berücksichtigt AAC-ADTS beim Umpacken nach MP4.
- Fremde Konten werden sowohl vom StreamDesk-Proxy als auch direkt vom Playback-Server abgelehnt. Anonymer Proxy-Abruf erhält HTTP 401.
- Die neuen Quellen-/Ziel- und Playback-Ansichten funktionieren im Browser ohne JavaScript-Fehler; Wiedergabe erreicht einen dekodierten Videoframe. Mobilansichten mit 390 Pixeln Breite zeigen keinen horizontalen Seitenüberlauf.
- Fremde MediaMTX-Pfade und fremde Auth-Einträge bleiben erhalten.

Der bisherige `media_smoke.py` besteht nach der Audio-Anpassung erneut: unabhängige Ausgänge, Expertenmodus, Theme/Mobilansicht, manueller Fallback, WHIP-Kamera, WHEP-Vorschau, HLS-Freigabe/Widerruf und native Aufnahmesegmente. `srt_smoke.py` bestätigt erneut 25 Sekunden SRT-Publish mit erzeugter URL, Source-2-Auswahl und HLS-Vorschau. Python-/JavaScript-Syntax, Shell-Wrapper und Whitespace-Prüfung bestehen.

Alle neuen Integrationstests verwenden temporäre Daten und Loopback-Ziele. Die lokale Zielprüfung wird ausschließlich im Test für diese Ziele freigegeben. Öffentliche Streamingplattformen, echte Kameras, OAuth-Konten, NAT/HTTPS und eine systemd-Installation auf dem Benutzer-Server wurden für rc.4 nicht ausgeführt. Die erzeugten Screenshots dienen der lokalen UI-Prüfung; sie gehören nicht zum Serverpaket.

Ausführung: [CONTRIBUTING.md](CONTRIBUTING.md). Bedienung und Grenzen: [Expertenmodus](docs/EXPERT_MODE.md). Verbindliche spätere Wellen: [ROADMAP.md](ROADMAP.md).

## Vorheriger Prüfbericht: StreamDesk 1.1.0-rc.3

## Experten-Untermenüs, WebRTC und SRT

56 Unit-Tests bestehen. Neu geprüft werden die Trennung der technischen Formulare in eigene Experten-Untermenüs, die weiterhin frei verfügbare Theme-Einstellung, eine verständliche Einrichtungsseite bei deaktiviertem WebRTC, Protokollstatus ohne Ausgabe von Geheimnissen einschließlich `<redacted>`-Passwörtern der Control API und die vollständigen SRT-Verbindungsparameter.

Der echte lokale Medien-/Browsertest wurde mit zunächst deaktiviertem WebRTC wiederholt: Die Aktivierung über **Expertenmodus → Protokolle & WebRTC** startet den Server; Kamera-Publish und Vorschau funktionieren anschließend. Technische Unterseiten sind bei ausgeschaltetem Modus nicht erreichbar, normale Einstellungen bleiben getrennt. Desktop und Mobilansicht wurden mit dem neuen Untermenü geprüft. Auch Quellenwahl, unabhängige Ausgänge, HLS-Zuschauer und native Segmente bestehen weiter.

`tests/srt_smoke.py` prüft zusätzlich einen echten authentifizierten SRT-Publisher mit H.264/AAC gegen MediaMTX 1.21.3: 25 Sekunden durchgängiges Senden, Auswahl als Source 2 und anschließende HLS-Vorschau. Anonymer Loopback-Publish auf den SRT-Eingang wird im Test ausgeschlossen, damit die Zugangsdaten tatsächlich verwendet werden müssen. Ein realer OBS-Verbindungsabbruch wurde anhand der Client-/Serverprotokolle auf gleichzeitig fehlschlagende SRT-Eingangsversuche eingegrenzt; nach Aktivieren von „Datei schließen, wenn inaktiv“ für die betreffende OBS-Quelle bestätigte der Benutzer stabilen Betrieb. Die Einstellung in OBS wurde separat vorgenommen und gehört nicht zum Serverinstaller.

```bash
.venv/bin/python tests/srt_smoke.py --mediamtx /pfad/zu/mediamtx --ffmpeg /pfad/zu/ffmpeg
```

## Vorherige Installerkorrektur: 1.1.0-rc.2

## Wiederaufsetzen und Update-Erkennung

52 Unit-Tests einschließlich 18 neuer Wiederherstellungs-/Laufzeitfälle bestehen. Die neuen Fälle prüfen die widersprüchlichen Attach-/Update-Fehler bei fehlender Datenbank, Schutz einer vorhandenen Datenbank, gespeicherte eigene Ordner, fehlende Schlüssel, falsche Zielpfade, Zuordnung des alten Namensbereichs, reine Prüfung per `--dry-run`, Erhalt von Medien/Schlüsseln/Journaldateien, Bootstrap auch bei `update --recover`, ausschließlich eigene Laufzeitlöschungen sowie Rücknahme nach einem späten fehlgeschlagenen Healthcheck. Schlägt schon die Sicherung fehl, wird die zuvor laufende UI wieder gestartet. Ein Sicherungsordner innerhalb des zu archivierenden Datenordners wird vor Änderungen abgelehnt.

Zusätzlich wurde `tests/recovery_smoke.py` mit echtem MediaMTX 1.21.3 ausgeführt: neue Datenbank, neuer Administrator mit erfolgreicher Anmeldung, neue Verschlüsselungsschlüssel, erhaltene verwaiste Dateien und fremde Pfade sowie Entfernung alter eigener Laufzeitpfade. Der Test verwendet temporäre Daten und Loopback-Ports; das vollständige Installationsverfahren wird für die automatisierten Ablauf-/Rollbacktests mit simuliertem systemd geprüft. Auf dem Benutzer-Server wurde nichts ausgeführt.

```bash
.venv/bin/python tests/recovery_smoke.py --mediamtx /pfad/zu/mediamtx
```

## Vorherige Medienerweiterung: 1.1.0-rc.1

## Automatische Prüfungen der Erweiterung

34 Unit-Tests prüfen die bisherigen Benutzer-/Mediengrenzen und zusätzlich Expertenmodus, direkte gesperrte API-Anfragen, CSRF, getrennte Anmeldungen, Theme ohne Expertenmodus, Quellenwahl, unabhängige Ausgänge, Aufnahme-Konfigurationsrollback, Erhalt nativer Aufnahmeeinstellungen, private Segmentdownloads, niedrigen Speicher, Zuschauer-Link-Rotation/Widerruf, Administratorrechte und WebRTC-Sitzungsbereinigung. Zwei Regressionen prüfen den Erhalt der Quellengesundheit zwischen Engine-Durchläufen und einen konkurrierenden Pfadabgleich durch den MediaMTX-Dateiwächter.

Python- und JavaScript-Syntax, Shell-Wrapper und `git diff --check` wurden geprüft. Ausführung der Unit-Tests und des lokalen Medientests: [CONTRIBUTING.md](CONTRIBUTING.md).

## Lokaler Medien- und Browsertest

`tests/media_smoke.py` wurde mit einer echten, per SHA-256 geprüften MediaMTX-1.21.3-Binärdatei, FFmpeg 7.0.2 und Chromium 156 in einer lokalen Linux-Testumgebung ausgeführt. Er verwendet temporäre Daten, zwei Benutzer und ausschließlich Loopback-Ports/-Ziele.

Erfolgreich geprüft:

- RTSP-Testquelle → laufende StreamDesk-Engine → zwei lokale Weiterleitungsziele; Stopp eines Ziels bei weiter verbundenem zweitem Ziel.
- Fest gewählte fehlende Quelle → Offline-Video; Rückkehr zu Auto → Live-Quelle.
- Expertenmodus ein/aus über die echte Oberfläche und HTTP 403 bei direktem technischem API-Aufruf ohne aktivierten Modus.
- Helles Theme unabhängig vom Expertenmodus und Mobilansicht mit 390 Pixeln Breite ohne horizontalen Seitenüberlauf.
- Browser-Kamera mit Testgerät über WHIP → MediaMTX und Browser-Vorschau über WHEP mit tatsächlichem Video.
- Öffentlicher HLS-Player ohne Anmeldung mit tatsächlichem Video; weiterer Playlistabruf nach Widerruf abgelehnt.
- Native Source-2-Aufnahme der WebRTC-Kamera, Segmentdownload und Dekodieren der erzeugten Datei mit FFmpeg.
- Fremder MediaMTX-Pfad bleibt erhalten; keine JavaScript-Laufzeitfehler in der geprüften Hauptoberfläche.

Der lokale Test ersetzt keine Prüfung von DNS, HTTPS, Reverse Proxy, NAT/Firewall oder TURN auf dem eigenen Testserver. Die systemd-Neuinstallation, ein Update einer realen 1.0.0-Installation und die Schreibrechte eines eingeschränkten fremden MediaMTX-Dienstes wurden für diesen Release Candidate noch nicht praktisch auf Debian geprüft. Öffentliche Plattformausgänge und echte OAuth-Konten wurden nicht verwendet.

## Nächste Prüfung auf dem Testserver

1. Separaten Debian-Testserver mit Standalone-Installation oder eigener Attach-Instanz einrichten; bei bestehender 1.0.0-Installation den Update-Modus verwenden.
2. Normaler Benutzer ohne Expertenmodus: Dashboard, Gesamtstart/-stopp, Chat, Videos, manuelle Aufnahmen und Theme prüfen.
3. Expertenmodus aktivieren: Quellensteuerung, einzelne Ausgänge, native Aufnahmen und Zuschauerfreigabe prüfen. Nach neuer Anmeldung muss der Modus wieder aus sein.
4. Als Administrator WebRTC aktivieren, erreichbare Hosts und Medienport prüfen, mit Kamera und realen OBS-/Handy-Quellen testen.
5. Zuschauer-Link erneuern und widerrufen, Benutzergrenzen sowie Aufnahmeverzeichnis/-rechte einschließlich systemd-Einschränkungen prüfen.

Einrichtung: [Expertenmodus](docs/EXPERT_MODE.md).

---

# Historischer Prüfbericht: StreamDesk 1.0.0

## Automatische Prüfungen

17 automatisierte Tests prüfen persönliche Medienrechte, gespeicherte Streamingziele, Chat-Widget-Zugriff und Rotation, CSRF-Schutz, lokale Demo-Overlays, Konfigurationsübernahme, Namensbereichskollisionen, Berechtigungen und den auf eigene Pfade begrenzten API-Abgleich. Python-Dateien und Shell-Wrapper wurden auf Syntax geprüft.

Die Tests verwenden temporäre Daten und starten keine öffentlichen Streams. Ausführung siehe [CONTRIBUTING.md](CONTRIBUTING.md).

## Praktische Installationsprüfungen

Auf Debian 13 / amd64 mit systemd wurden getrennte Testdienste und eigene Ports verwendet. Die vorhandene produktive Installation wurde dabei nicht ersetzt.

Erfolgreich geprüft:

- Neue Anwendung mit frischer Datenbank, neuem Python-Environment und frisch heruntergeladenem, per SHA-256 geprüftem MediaMTX.
- Erster Login, eigener Benutzer, persönliche Quellen und gespeicherte Zielauswahl.
- Standby-Video, manuelle Aufnahme, Download und einmalige Wiederholung über ausschließlich lokale Testausgänge.
- Live-Browser-Overlay auf dem tatsächlich erzeugten Programm; Beenden des Renderers nach Streaming-Stopp.
- Update unter Erhalt von Benutzern, Schlüsseln, Aufnahmen und Einstellungen.
- Absichtlich fehlgeschlagenes Update mit Wiederherstellung von Anwendung, Datenbank und Konfiguration.
- Einbindung in bestehendes MediaMTX mit Dienstbenutzer ohne root-Rechte: vorhandener Kamera-Stream blieb verbunden, bestehende Zugänge blieben gültig und UI-Pfade waren gegen fremden Zugriff geschützt. Programm und Dienstdefinition des vorhandenen MediaMTX blieben erhalten.
- Deinstallation der UI unter Erhalt von MediaMTX und persönlichen Daten.

## Grenzen der Prüfung

Die Installation wurde auf einem vorbereiteten Debian-System mit bereits vorhandenen Systemabhängigkeiten getestet; dafür wurde `--skip-system-packages` verwendet. Ein vollständig leerer Proxmox-Container einschließlich Paketinstallation wurde nicht durchgetestet. Debian 12 und arm64 wurden nicht praktisch geprüft.

Es wurden keine öffentlichen Twitch-/YouTube-Streams gestartet und keine Chatnachrichten versendet. Neue OAuth-Apps, DNS, Reverse Proxy, Plattformberechtigungen und reale Encoderverbindungen sind nach der eigenen Installation zu konfigurieren und zu prüfen. Der Browser-Test verwendet das enthaltene Demo-Overlay; die Verfügbarkeit eines externen Overlayanbieters kann das Paket nicht garantieren.
