# Installation

## Voraussetzungen

- Debian 12 oder 13 mit laufendem systemd, Python mindestens 3.11, root-Zugang und Internet.
- amd64 oder arm64 für die gemeinsame Neuinstallation. Bereits installierte MediaMTX-Binaries anderer Architekturen können im Attach-Modus verwendet werden.
- MediaMTX **>= 1.21.3 und < 2.0**. Für eine vorhandene ältere Version ist zuerst ein MediaMTX-Update nötig; der Attach-Installer aktualisiert fremde Binaries nicht.
- Eine öffentliche HTTPS-Adresse und Reverse Proxy für Twitch-/YouTube-OAuth. Für einen lokalen Funktionstest ist HTTP möglich; Kontofreigaben erfordern die konfigurierte HTTPS-Adresse.
- Platz für Videos und Aufnahmen. Bei 6 Mbit/s entstehen ungefähr 2,7 GB pro Aufnahmestunde. Zwei CPU-Kerne und 2 GiB RAM sind ein Ausgangspunkt für einen kleinen Testbetrieb; gleichzeitig verwendete Browser-Overlays brauchen zusätzliche Reserven.

Der Installer installiert Python-venv, FFmpeg, DejaVu-Schriften, Chromium und Python-Abhängigkeiten. Python-Pakete liegen ausschließlich im eigenen virtuellen Environment.

## 1. Paket bereitstellen

ZIP auf den Linux-Server übertragen und dort entpacken:

```bash
apt-get update
apt-get install -y unzip python3
unzip streamdesk-1.1.0-rc.6.zip
cd streamdesk-1.1.0-rc.6
bash install.sh --help
```

Domain und Ingest-Host in den folgenden Befehlen ersetzen. Der Ingest-Host ist der vom Encoder erreichbare Servername bzw. die IP, ohne `rtmp://`, `https://` oder Port.

## 2a. Vorhandenes MediaMTX

Beispiel für eine native Installation über das Proxmox-Community-Script:

```bash
sudo bash install.sh --mode attach \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com \
  --mediamtx-config /opt/mediamtx/mediamtx.yml \
  --mediamtx-binary /opt/mediamtx/mediamtx \
  --mediamtx-service mediamtx \
  --dry-run
```

Danach denselben Befehl ohne `--dry-run` ausführen. Bei einem anderen Installationspfad die tatsächlichen Pfade und den Dienstnamen einsetzen.

### Was wird übernommen oder geändert?

- Bestehendes MediaMTX-Programm und dessen systemd-Unit bleiben erhalten.
- Vorhandene fremde Medienpfade und deren Einstellungen bleiben bestehen.
- StreamDesk reserviert `streamdesk/` als privaten Präfix. Bei einer Kollision kann beispielsweise `--namespace studio` gewählt werden.
- Interne Authentifizierung ist erforderlich. Eine vorhandene HTTP-/JWT-Konfiguration wird mit einer Fehlermeldung abgelehnt und nicht ersetzt.
- Globale `publish`-/`read`-/`playback`-Berechtigungen werden mit einem RE2-kompatiblen Ausdruck auf alles **außerhalb** des UI-Namensbereichs begrenzt. Benannte bestehende Konten und eingeschränkte globale API-Berechtigungen bleiben erhalten. Eine anonym und ohne IP-Beschränkung erreichbare Control API wird aus Sicherheitsgründen abgelehnt.
- Vorhandene frei formulierte Regex-Medienberechtigungen werden abgelehnt, wenn sie nicht bereits von dieser StreamDesk-Installation stammen. Sie müssen vorab auf konkrete Medienpfade beschränkt werden. Der Installer macht solche Berechtigungen nicht unbemerkt weiter oder entfernt sie.
- Die lokale Control API sowie HLS und benötigte Medienprotokolle werden aktiviert, falls sie deaktiviert sind. Vorhandene aktivierte Ports und die vorhandene HLS-Variante bleiben erhalten. MediaMTX kann diese Konfigurationsänderungen neu laden; ein Wartungsfenster ist sinnvoll.
- Eine lokale Dienstberechtigung erlaubt StreamDesk den API-Zugriff und den Medienzugriff auf seinen eigenen Präfix. Die Control API sollte für externe Geräte nicht öffentlich zugänglich sein.

Die YAML-Datei wird neu geschrieben; Kommentare und Formatierung bleiben in der privaten Originalsicherung erhalten. Ein vorhandener MediaMTX-Dienst mit festem Benutzer und fester Gruppe wird unterstützt. Bei `DynamicUser=yes` ist zunächst eine feste Dienstgruppe manuell einzurichten.

Der Attach-Modus ist für eine lokale native Instanz auf demselben Linux-System vorgesehen. Bei Docker, externen Authentifizierungsdiensten oder räumlich getrennten Instanzen bitte die Architektur zunächst manuell anpassen; der Installer meldet inkompatible Konfigurationen.

## 2b. Neue Installation inklusive MediaMTX

Auf einem frischen Debian-Container:

```bash
sudo bash install.sh --mode standalone \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com
```

Der MediaMTX-Download kommt ausschließlich von den offiziellen [GitHub-Releases](https://github.com/bluenviron/mediamtx/releases/tag/v1.21.3). Version und SHA-256 sind im Installer festgelegt. Ein vorhandenes Programm, eine vorhandene Konfiguration oder eine belegte Dienst-Unit wird nicht durch diesen Modus ersetzt.

Für die nicht interaktive Installation `--yes` ergänzen. `--public-url` und `--ingest-host` müssen dann angegeben sein.

## 3. Erster Login

```bash
sudo cat /var/lib/streamdesk/initial-login.txt
systemctl status streamdesk mediamtx
```

Die Datei ist nur für root lesbar. Mit diesen Daten an der öffentlichen UI-Adresse anmelden und unter Einstellungen das Passwort ändern. Danach die Datei entfernen:

```bash
sudo rm /var/lib/streamdesk/initial-login.txt
```

Optional kann das initiale Passwort in einer eigenen Datei bereitgestellt werden:

```bash
sudo chmod 600 /root/streamdesk-admin-password.txt
sudo bash install.sh --mode standalone \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com \
  --admin-user admin \
  --admin-password-file /root/streamdesk-admin-password.txt
```

Kein Kennwort als Befehlszeilenargument oder in eine öffentliche ZIP-Datei schreiben.

## 4. Reverse Proxy und Encoder

Standard-UI-Ziel ist `http://SERVER-IP:8080`. Für NPMplus siehe [docs/PROXY.md](docs/PROXY.md). Die Control API und HLS bleiben standardmäßig auf Loopback.

Übliche Ingest-Ports: TCP 1935 für RTMP und UDP 8890 für SRT. TCP 8554 dient der internen RTSP-Verarbeitung; nur extern öffnen, falls externe RTSP-Clients benötigt werden. Die Encoder verwenden **die persönlichen Adressen aus der Oberfläche**, einschließlich Benutzerzugang und Namensbereich.

Konten und App-Schlüssel werden nach der Installation in der Administration eingerichtet. Es werden keine Zugangsdaten des früheren Testservers mitgeliefert. Details: [docs/OAUTH.md](docs/OAUTH.md).

## Optional: geschütztes Playback

Ab rc.4 unter **Expertenmodus → Playback** als Administrator aktivieren. Der neue Listener muss auf Loopback liegen; Standard `127.0.0.1:9996`. Optional beim Installieren oder Update `--enable-playback --playback-port 9996` ergänzen. Ohne diesen Schalter werden bestehende Playback-Einstellungen im Attach-/Update-Modus beibehalten. Persönliche Playback-Rechte werden beim Anwendungsabgleich ergänzt; anonyme Archivberechtigungen für den StreamDesk-Namensbereich werden nicht angelegt.

## 5. Update

Neues Release separat entpacken und darin ausführen:

```bash
sudo bash install.sh --mode update
```

Bei abweichendem Dienstnamen `--service-name` angeben. Der Datenordner wird aus der vorhandenen Env-Datei übernommen. Ab 1.1.0-rc.2 wird auch der Programmordner gespeichert; bei älteren Installationen mit eigenem Programmordner diesen weiter ausdrücklich angeben. Beispiel:

```bash
sudo bash install.sh --mode update \
  --service-name studio-ui \
  --app-dir /opt/studio-ui \
  --data-dir /var/lib/studio-ui
```

Öffentliche Adresse und Endpunkte werden aus `/etc/<dienstname>.env` übernommen. Benutzer, Medien, Schlüssel und Auswahl bleiben erhalten. Der UI-Dienst wird während des Updates neu gestartet; laufende Streams und Aufnahmen können dadurch unterbrochen werden. Im geplanten Wartungsfenster aktualisieren.

Der Update-Modus gilt für Installationen aus diesem Release-Installer. Eine frühere individuelle Entwicklungsversion mit unbenannten Root-Pfaden oder ohne Installationsdatei sollte gesichert und manuell migriert bzw. frisch installiert werden.

### Datenbank gelöscht: neue Instanz an bestehendem MediaMTX

Wenn `attach` eine bestehende Installation meldet und `update` keine Datenbank findet, sind typischerweise Env-Datei, Unit oder MediaMTX-Einträge übrig geblieben. Ein normales Update kann die gelöschten Konten nicht wiederherstellen. Für den bisherigen Zustand müssen `app.db`, `fernet.key` und `session.key` aus einer zusammengehörigen Sicherung zurückgespielt werden.

Für einen ausdrücklich gewünschten **Neuanfang mit neuer Datenbank und neuen Zugangsdaten** das neue Paket entpacken und darin ausführen:

```bash
sudo bash install.sh --mode attach --recover \
  --public-url https://stream.example.com \
  --ingest-host ingest.example.com \
  --mediamtx-config /opt/mediamtx/mediamtx.yml \
  --mediamtx-binary /opt/mediamtx/mediamtx \
  --mediamtx-service mediamtx
```

`--dry-run` kann zum Prüfen ergänzt werden; dabei werden keine Dateien, Dienste oder Pakete geändert. `--mode update --recover` verwendet denselben Wiederaufsetzungsweg. `--recover` ist ausschließlich bei fehlender Datenbank möglich, nicht mit `standalone`.

Dabei geschieht Folgendes:

1. Vorhandene Env-Werte und derselbe MediaMTX-Namensbereich werden übernommen. Abweichende Daten- oder MediaMTX-Konfigurationspfade werden abgelehnt, damit nicht versehentlich die falsche Instanz zurückgesetzt wird.
2. Der UI-Dienst wird gestoppt; Konfiguration, Anwendung, Unit und vorhandene Schlüssel werden privat unter `/var/backups/streamdesk/` gesichert.
3. Ein verbliebener Datenordner wird neben den bisherigen Pfad verschoben, beispielsweise nach `/var/lib/streamdesk-before-recovery-<zeitpunkt>-<kennung>`. Auch Medien, Schlüssel und SQLite-Journaldateien bleiben dort erhalten. Die Sicherung enthält eine `recovery.json` mit diesem Pfad. Große Dateien werden dafür nicht kopiert.
4. Nachweisbar eigene verwaiste MediaMTX-Pfade und Konten werden entfernt und ein neuer StreamDesk-Administrator eingerichtet. Ohne passende Env-Datei müssen bestehende Pfade über ihre reservierten StreamDesk-Medienkonten zuordenbar sein; ein unbekannter belegter Namensbereich wird weiterhin abgelehnt.
5. Neue Zugangsdaten werden ausschließlich in `/var/lib/streamdesk/initial-login.txt` abgelegt. MediaMTX-Binary, bestehende MediaMTX-Unit und fremde Streams/Konten werden nicht ersetzt. Der separate native Aufnahmebereich bleibt erhalten.

Bei einem Installationsfehler werden vorherige Konfiguration und Datenreste wiederhergestellt. Ein späterer erneuter Aufruf mit vorhandener neuer Datenbank ist ein normales `--mode update`; `--recover` überschreibt diese Datenbank nicht.

Nach erfolgreicher Neuinstallation:

```bash
sudo cat /var/lib/streamdesk/initial-login.txt
```

Plattformkonten, Streamschlüssel und Benutzer müssen neu eingerichtet werden. Dateien aus dem archivierten Datenordner werden nicht automatisch einer neuen Datenbank zugeordnet; benötigte Videos lassen sich erneut hochladen. Alte Schlüssel nicht in die neue Instanz kopieren.

## Erweiterte Parameter

`bash install.sh --help` listet alle Optionen. Mit `--app-dir`, `--data-dir`, `--browser-root`, `--service-name`, `--mediamtx-dir`, `--mediamtx-service` und `--namespace` lassen sich getrennte Instanzen betreiben. Ein UI-Namensbereich wird von genau einer StreamDesk-Installation verwaltet.

`--bind 127.0.0.1:8080` beschränkt das UI auf einen lokalen Proxy; der Standard `0.0.0.0:8080` erlaubt auch einen Proxy auf einem anderen Host. Ports für eine neue MediaMTX-Instanz: `--rtsp-port`, `--rtmp-port`, `--srt-port`, `--api-port`, `--hls-port`. Bei Attach bleiben bereits aktivierte Listener erhalten.

`--api-url` und `--hls-url` können vorhandene HTTPS-Endpunkte mit einem gültigen, systemweit vertrauten Zertifikat benennen. Es gibt keinen Schalter zum Abschalten der Zertifikatsprüfung.

`--skip-system-packages` ist für vorbereitete Test-/Deployment-Systeme vorgesehen. FFmpeg, ffprobe, Chromium und die übrigen Systemabhängigkeiten müssen dann bereits installiert sein. Der Installer prüft sie und installiert weiterhin die Python-Abhängigkeiten.

## Fehler und Wiederherstellung

Vor Änderungen entstehen private Sicherungen unter `/var/backups/streamdesk/`. Gesichert werden Konfiguration, App-Quellcode, Env-Datei sowie bei Updates die Datenbank und Verschlüsselungsschlüssel; große Mediendateien werden nicht kopiert. Bei einem Installationsfehler wird der vorherige Konfigurations-/Anwendungsstand wiederhergestellt. Die Sicherung bleibt zur Kontrolle erhalten. Systempakete und das Python-Environment werden dabei nicht automatisch zurückgesetzt; Hinweise dazu stehen im Betriebsleitfaden.

Logs und Wiederherstellungsschritte stehen in [docs/OPERATIONS.md](docs/OPERATIONS.md). Ein erneuter Neuinstallationsaufruf überschreibt keine vorhandene Datenbank.

## Umstieg auf rc.6

Das normale `--mode update` erhält Benutzer, Schlüssel, Medien und tatsächlich konfigurierte zusätzliche Quellen/Ausgänge. Die Datenbank wird beim Start wiederholbar um Routingtabellen und die dauerhafte Benutzer-ID-Vergabe ergänzt. Es gibt danach für neue Benutzer nur zwei feste Standardquellen; zusätzliche Quellen und Konten werden im Expertenmodus angelegt. Die alte globale Quellenfixierung wird durch Prioritäten je Ausgang ersetzt. Nach dem Update unter „Quellen & Routing“ die übernommenen Zuordnungen prüfen.
