# Änderungen

## 1.1.0-rc.6

- Standard wieder exakt Source 1 und Source 2 sowie Twitch, YouTube und ein eigener Anbieter. Source 1/2 lassen sich weder umbenennen, umkonfigurieren, löschen noch unter die Prioritäten zusätzlicher Quellen verschieben.
- Zusätzliche Quellen und Ausgänge nur nach ausdrücklichem Anlegen im Expertenmodus. Je Benutzer bis zu zehn Quellen und zehn Ausgänge, darunter weitere Twitch-/YouTube-Konten mit eigenen Streamschlüsseln und benannte eigene Anbieter.
- Zuordnung pro Quelle und Ausgang: Nur zugeordnete verfügbare Quellen konkurrieren. Source 1 hat Priorität 1, Source 2 Priorität 2, zusätzliche Quellen ab Ebene 3. Verschiedene Ausgänge können gleichzeitig unterschiedliche Programme senden; gleiche Quellenmengen teilen sich einen Encoder.
- Eigene Expertenbereiche „Quellen & Routing“ und „Ausgänge & Konten“. Quellen einzeln auswählen und bearbeiten. Die normale Quellenansicht zeigt je Quelle eine eigene Vorschau und aufklappbare Verbindungsdaten statt einer gemeinsamen Zugangsdatenliste.
- Dashboard mit umschaltbarer Vorschau je Ausgang, tatsächlicher Programmquelle, Prioritätskette und ständig sichtbarem privaten Vorschau-Link; WebRTC-Link im Expertenmodus. Programmaufnahmen können auch gezielt ein zusätzliches Programm erfassen.
- Neuer, für Benutzer und Administratoren sichtbarer Menüpunkt „Mein Konto“ mit eigenem Passwortwechsel. Andere Anmeldungen werden danach ungültig; die aktuelle Sitzung bleibt erhalten.
- Deaktivierte Benutzer können nach Namensbestätigung gelöscht werden. Eigene Pfade/Zugänge und Kontodaten werden entfernt, Mediendateien privat archiviert. Aktive Konten, das eigene Administratorkonto sowie laufende Verarbeitung/Abschlüsse sind geschützt. Benutzer-IDs werden nach Löschen nicht wiederverwendet.
- Aufnahmeabschluss über FFmpeg-Steuerkanal und kurze Fragment-/Interleave-Intervalle statt vorzeitigem erzwungenem Prozessende; verhindert verlorene Schlusssekunden beim manuellen Stopp.
- Wiederholbare Migration erhält tatsächlich genutzte zusätzliche Quellen, vorhandene Schlüssel, Auswahl, Routing und Archive. Eine unbenutzte automatisch erzeugte Source 3 entfällt. Alte globale manuelle Quellenwahl wird durch Prioritäten je Ausgang ersetzt; Quellenwechsel innerhalb eines Programms bleiben aufnahmestabil.

## 1.1.0-rc.5

- Programmpfad bleibt unabhängig von Streamingzielen verfügbar. Quellenwechsel und Start/Stopp von Weiterleitungen schließen Programmleser und die manuelle Programmaufnahme nicht mehr. Lokale Aufnahmezeitstempel erhalten die vollständige Laufzeit trotz wechselnder Publisher-Zeitbasen. Aktivierte native Programmaufnahmen erfassen auch den Standby-Zeitraum zwischen Quellen.
- Dashboard lädt die Programmvorschau nach anfänglichem Verbindungsaufbau, nach Schließen/Öffnen und nach einem Ansichtswechsel wieder korrekt statt auf `about:blank` zu bleiben. HLS-Abrufe verwenden die persönlichen Medienrechte.
- Programmvideo wird einheitlich als H.264 ohne B-Frames mit 1080p30 und AAC/48 kHz/Stereo aufbereitet. Dies verhindert ungültige Zeitstempel und Codecwechsel bei unterschiedlichen Quellenprofilen; der zusätzliche Videoencoder benötigt CPU. Direkte native Eingangsaufnahmen behalten ihr Quellenformat.
- WebRTC-Programmvorschau verwendet einen privaten, nur bei Bedarf gestarteten H.264-/Opus-Pfad, damit auch Programm-Audio im Browser ankommt. Mehrere Zuschauer desselben Benutzers teilen sich den Prozess; nach 20 Sekunden ohne Leser wird er beendet.
- Offline-Video bzw. Browser-Overlay läuft bei Vorschau, Programmaufnahme, aktivierter nativer Programmaufnahme oder Streamingziel; laufende Live-Quellen behalten die eingestellte Priorität. Ohne Verbraucher und ohne aktive Live-Quelle bleibt die Offline-Datei pausiert.
- Neuer echter Regressionstest mit zwei parallelen Quellen, B-Frames und unterschiedlichen Auflösungen: eine Aufnahme, HLS-/WebRTC-Programm ohne Streamingziel, Quellenverlust, Offline-Fallback sowie Start/Stopp eines Ausgangs.

## 1.1.0-rc.4

- Verbindliche eigenständige Planung in `ROADMAP.md`; spätere Wellen bleiben getrennt von dieser Umsetzung.
- Eigenes Playback-Untermenü mit Segmentauswahl, Startzeit/Dauer, Video und Download. MediaMTX-Playback wird nur ausdrücklich durch Administratoren im Expertenmodus aktiviert; neue Listener liegen auf Loopback. Persönliche Playback-Berechtigungen und der Sitzungsproxy begrenzen den Zugriff auf eigene Quellen.
- Native fMP4-Wiedergabe über MediaMTX; MPEG-TS wird wegen der Grenze in v1.21.3 über FFprobe/FFmpeg in fragmentiertes MP4 umgepackt. Höchstens eine Stunde pro Abruf und zwei gleichzeitige MPEG-TS-Konvertierungen.
- Source 3 mit RTMP-/SRT-Verbindungsdaten und optionaler öffentlicher RTSP-/RTSPS-Pull-Quelle. Auto-Priorität Source 1 → Source 2 → Source 3 → Pull → Offline; alle Eingänge auch manuell wählbar und aufnehmbar. Alte Vorschau- und Ingest-Adressen bleiben gültig.
- Programm-Audio wird auf AAC, 48 kHz und Stereo vereinheitlicht; Mono-Quellen können dadurch zuverlässig mit dem MediaMTX-Standby-Signal wechseln.
- Bis zu fünf benannte Custom-Ziele neben den festen Twitch-/YouTube-Slots. Jedes Ziel separat starten/stoppen, umbenennen und nach Stopp ändern/löschen; zusätzliche Upload-Bandbreite wird im UI erläutert. Bestehende Custom-Schlüssel und Auswahldaten bleiben bei der Migration erhalten.
- Installer liefert neue Module und Roadmap aus, erhält vorhandene Playback-Einstellungen und unterstützt die ausdrückliche Aktivierung mit `--enable-playback --playback-port 9996`.

## 1.1.0-rc.3

- Eigener Menüpunkt „Expertenmodus“ mit Untermenüs für Protokolle/WebRTC, Quellen/Ziele, native Aufnahme, Zuschauerfreigabe und Neuverbindung. Normale Einstellungen, Quellen und Aufnahmen enthalten keine technischen Konfigurationsformulare mehr.
- WebRTC mit sichtbarem Konfigurations-/Laufzeitstatus, geführter Aktivierung und vorgeschlagenem Ingest-Host. Bei deaktiviertem Server führt die Kameraseite zur Einrichtung; Server-Aktivierung bleibt eine bewusste Administratoraktion im Expertenmodus.
- SRT-Verbindungsdaten mit explizitem Caller-Modus, einer Sekunde Latenzpuffer und getrennten Server-/Stream-ID-Feldern samt OBS-Hinweisen.
- Protokollstatus zeigt SRT-Listener, eigene Publish-Berechtigung und Konsistenz der gespeicherten Zugangsdaten, ohne Passwörter auszugeben. Die Passwort-Ausblendung der MediaMTX-Control-API wird berücksichtigt.
- Zusätzlicher echter SRT-Medientest und Anleitung für OBS-Verbindungsabbrüche durch parallel fehlschlagende SRT-Eingangsquellen.

## 1.1.0-rc.2

- Wiederaufsetzen nach Datenverlust über `--mode attach --recover` oder `--mode update --recover`: neue Datenbank und Administrator, ohne eine vorhandene Datenbank zu überschreiben.
- Verbliebene Daten einschließlich Schlüssel, Medien und SQLite-Journaldateien bleiben in einem separaten Ordner erhalten; bei einem Fehler werden sie zurückgeschoben.
- Verwaiste eigene MediaMTX-Pfade und Konten werden nach Sicherung ersetzt. Fremde Pfade, Konten, MediaMTX-Binary und dessen Unit bleiben erhalten. Laufzeitbereinigung ist auf nachgewiesene eigene alte Pfade begrenzt.
- Installationsreste ohne Datenbank führen zu einer passenden Wiederherstellungsmeldung statt zur widersprüchlichen Empfehlung eines normalen Updates.
- Updates übernehmen den gespeicherten Datenordner und bei neuen Installationen den Programmordner; bei fehlenden Schlüsseln wird statt der Erzeugung unpassender Ersatzschlüssel abgebrochen.
- UI-Dienst vor dem Konfigurations-/Datenbankbackup stoppen; bei fehlgeschlagener Sicherung den vorher laufenden Dienst wieder starten.

## 1.1.0-rc.1

- Expertenmodus pro Anmeldung, standardmäßig aus; technische Endpunkte prüfen ihn auch serverseitig. Globale WebRTC-Einstellungen benötigen zusätzlich Administratorrechte.
- Manuelle Quellenwahl mit definiertem Offline-Fallback und Start/Stopp einzelner Streamingziele ohne Änderung der anderen Ausgänge.
- Quellenerkennung korrigiert: Die Stabilitätshistorie aktiver Eingänge bleibt zwischen Engine-Durchläufen erhalten.
- WebRTC-Vorschau über WHEP und Browser-Kamera über WHIP mit authentifiziertem Signalisierungsproxy und Sitzungsbereinigung.
- Native MediaMTX-Aufnahme in fMP4/MPEG-TS, Segmentdauer und Aufbewahrung, privater Download und fMP4-Vorschau; separater Speicherbereich und Abschaltung bei wenig Speicher.
- Widerrufbare persönliche Zuschauer-Links für das Live-Programm über HLS, ohne öffentliche MediaMTX-Pfadberechtigung.
- Persönliches helles/dunkles/System-Theme und größere mobile Bedienelemente unabhängig vom Expertenmodus.
- Installer nimmt das neue Modul und den getrennten Aufnahmebereich mit; bestehende Pfad-Aufnahmeeinstellungen bleiben beim Abgleich erhalten.

## 1.0.0

- Erster allgemein konfigurierbarer Quellcode-Release.
- Installer für lokale vorhandene MediaMTX-Instanzen und gemeinsame Neuinstallation.
- Eigener privater Medien-Namensbereich mit Erhalt fremder Streams und Zugänge.
- Mehrbenutzer-Dashboard, Quellenwahl, Offline-Bibliothek, Text-/Browser-Overlays.
- Manuelle Aufnahmen, Downloads und gekennzeichnete Wiederholungen.
- Multistreaming, unabhängige Twitch-Neuverbindung, Twitch-/YouTube-Chat und Widgets.
- Gespeicherte Auswahl für den nächsten Stream ohne Trennung der Kontofreigaben.
- Generische Dokumentation, Konfigurationsbeispiel, Lizenzhinweise und Prüfungen.
