# Prüfbericht: StreamDesk 1.0.0

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
