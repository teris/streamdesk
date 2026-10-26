# MediaMTX - StreamDesk

Eine selbst gehostete Mehrbenutzer-Oberfläche für OBS-/Handy-Streams, manuelle Aufnahmen, Offline-Videos, Multistreaming und gemeinsamen Twitch-/YouTube-Chat.

**MediaMTX - StreamDesk benötigt [MediaMTX](https://github.com/bluenviron/mediamtx).** MediaMTX übernimmt den eigentlichen Medienverkehr. StreamDesk steuert persönliche Eingänge, automatische Quellenwahl und Ausgänge über dessen Control API. Dies ist ein eigenständiges Community-Projekt und kein offizieller Bestandteil von MediaMTX, Twitch oder YouTube.

```text
OBS (Source 1) ───┐                       ┌─ Twitch
Handy (Source 2) ─┼─ MediaMTX / StreamDesk ─┼─ YouTube
Offline-Video ────┘                       └─ eigener Anbieter
```

## Funktionen

- Kompaktes Dashboard mit Empfangs-/Sendedatenrate, aktuellem Programm, eigener Medienbelegung sowie aktueller und gesamter erfasster Sendezeit.
- Persönliche Konten mit zwei geschützten Eingängen: OBS über RTMP, Handy beispielsweise über SRT. Source 1 hat Vorrang vor Source 2.
- Persönliche Offline-Videobibliothek: MP4 bis 500 MiB und fünf Minuten, Auswahl, Vorschau und Löschen. Die Offline-Schleife beginnt erst bei verbundenem Ausgang.
- Positionierbare Textbeschriftung und live gerenderte Browser-Overlays, etwa von StreamElements. Der Overlay-Browser liefert Bild und Animationen; dessen Audio wird nicht übernommen.
- Ausschließlich manuell gestartete Aufnahmen, MP4-Download und einmalige Wiedergabe als Source 1 mit sichtbarem Hinweis „Wiederholung“.
- Gleichzeitig Twitch, YouTube und/oder ein eigener Streaminganbieter. Die gespeicherte Zielauswahl gilt beim nächsten Start; Konten bleiben beim Abwählen verbunden.
- Optionale Erneuerung der Twitch-Verbindung, während andere Streamingziele verbunden bleiben.
- Twitch-Titel und Kategorie bearbeiten; YouTube-Konto und eigene Sendung auswählen.
- Gemeinsamer Chat mit gezieltem Senden an Twitch, YouTube oder beide; persönliches, erneuerbares Widget für Browser-Docks und Browserquellen.

## Installation

Unterstützt werden **Debian 12/13 mit systemd und Python ab 3.11**, auf amd64 und arm64. Empfohlen wird ein eigener Debian-Server bzw. Proxmox-LXC. Der Installer benötigt root und Internetzugang.

Das ZIP entpacken, in den entpackten Ordner wechseln und den passenden Modus wählen. Es müssen keine vorhandenen StreamDesk-Dateien, Videos oder Schlüssel kopiert werden.

### Vorhandenes MediaMTX einbinden

```bash
sudo bash install.sh --mode attach \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com \
  --mediamtx-config /opt/mediamtx/mediamtx.yml \
  --mediamtx-binary /opt/mediamtx/mediamtx
```

Der Installer ersetzt weder das vorhandene MediaMTX-Programm noch dessen Dienst. Fremde Pfade bleiben bestehen. Es wird ein eigener reservierter Namensbereich `streamdesk/<benutzer>/` angelegt. Vorhandene globale Medienberechtigungen werden so eingegrenzt, dass sie diesen privaten Namensbereich nicht öffnen; ihre Wirkung auf die bisherigen Pfade bleibt erhalten. Details und Einschränkungen stehen in [INSTALL.md](INSTALL.md).

### StreamDesk und MediaMTX gemeinsam neu installieren

```bash
sudo bash install.sh --mode standalone \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com
```

Dabei lädt der Installer das offizielle MediaMTX **v1.21.3** für die erkannte Architektur herunter und prüft dessen fest hinterlegte SHA-256-Prüfsumme. Es werden getrennte systemd-Dienste, ein virtuelles Python-Environment und ein eigenes stummes Standby-Video erstellt. Vorhandene MediaMTX-Dateien oder StreamDesk-Daten werden im Neuinstallationsmodus nicht überschrieben.

Erste Zugangsdaten nach erfolgreicher Installation:

```bash
sudo cat /var/lib/streamdesk/initial-login.txt
```

Es gibt kein öffentliches Standardpasswort. Das Administratorkonto wird mit einem zufälligen Passwort angelegt. Danach das Passwort in der Oberfläche ändern und die Datei mit dem initialen Passwort entfernen.

**Ausführliche Schritte: [INSTALL.md](INSTALL.md).** Weitere Dokumentation:

- [Feature-Übersicht und Roadmap](FEATURE.md)
- [Reverse Proxy und NPMplus](docs/PROXY.md)
- [Twitch- und Google-/YouTube-Kontofreigabe](docs/OAUTH.md)
- [Konfigurationsvariablen](docs/CONFIGURATION.md)
- [Betrieb, Updates, Sicherung und Wiederherstellung](docs/OPERATIONS.md)
- [Mitwirken und Tests](CONTRIBUTING.md)
- [Prüfbericht zu diesem Release](TESTING.md)
- [Sicherheit](SECURITY.md)
- [Änderungen](CHANGELOG.md)

## Erste Verwendung

1. Oberfläche über die konfigurierte öffentliche Adresse öffnen und anmelden.
2. In „Quellen“ die persönlichen OBS-/SRT-Verbindungsdaten anzeigen und im Encoder eintragen.
3. Unter „Einstellungen“ die gewünschten Konten oder Streamschlüssel hinterlegen. Für YouTube einen Livestream im YouTube Studio vorbereiten.
4. „Beim nächsten Stream senden an“ wählen und **Streaming-Auswahl speichern**. Neue Verbindungen aktivieren kein Streamingziel automatisch.
5. Im Dashboard **Stream starten**. **Stream stoppen** beendet die Weiterleitungen, ohne Kontofreigaben oder Schlüssel zu löschen.
6. Aufnahmen und Wiederholungen separat und ausschließlich manuell starten.

Jeder Benutzer besitzt eigene Eingänge, Videos, Aufnahmen, Verbindungen und Chat-Widget-Links. Die Administratorverwaltung legt weitere Benutzer an.

## Grenzen

- Eine neue Twitch-Sitzung ist nicht garantiert unterbrechungsfrei. Eine kurze Neuverbindung setzt die Twitch-Grenze von 48 Stunden nicht zuverlässig zurück. Disconnect-Schutz und eine neue Sendung sind unterschiedliche Dinge.
- API-Kontofreigaben bei Twitch/Google sind für Chat erforderlich. YouTube-Streaming per Schlüssel benötigt keine Google-App. Eine YouTube-Sendung mit deaktiviertem oder beendetem Chat liefert keinen aktiven Chat.
- Die Anwendung erstellt, veröffentlicht oder beendet keine YouTube-Sendung automatisch über die API. Die Autostart-Einstellungen im YouTube Studio gelten weiterhin.
- Aufnahmen werden bei Quellabbruch abgeschlossen und nicht automatisch neu gestartet. Bei weniger als 350 MiB freiem Speicher werden sie beendet; zum Start müssen mindestens 500 MiB frei sein.
- Browser-Overlays benötigen während ihrer Nutzung Chromium und zusätzliche CPU/RAM. Eine gemeinsame Videoausgabe wird auf die Ziele verteilt; die Upload-Bandbreite steigt mit deren Anzahl.
- Der Installer bindet eine **lokale native MediaMTX-Instanz** ein. Eine entfernte Instanz ohne Zugriff auf deren Konfiguration, Docker-exklusive Installationen sowie HTTP-/JWT-Authentifizierung werden in dieser Version nicht automatisch umgebaut.

## Lizenz und Abhängigkeiten

StreamDesk wird unter der [MIT-Lizenz](LICENSE) bereitgestellt. MediaMTX bleibt ein separates Projekt mit eigener MIT-Lizenz. Die YouTube-gRPC-Protokolldefinition und generierter Code beruhen auf Googles Apache-2.0-Beispiel; siehe [NOTICE](NOTICE) und [Lizenztext](LICENSE.youtube-sample.txt). Weitere Laufzeit-Abhängigkeiten stehen in `requirements.txt` und [THIRD_PARTY.md](THIRD_PARTY.md).

Im Release-ZIP sind ausschließlich Quellcode und Dokumentation enthalten: keine Serverdatenbank, Konten, Kennwörter, Streamschlüssel, OAuth-Secrets, privaten Widget-Links oder hochgeladenen Videos.
