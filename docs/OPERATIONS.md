# Betrieb, Sicherung und Wiederherstellung

## Dienste und Logs

```bash
systemctl status streamdesk mediamtx
journalctl -u streamdesk -n 100 --no-pager
journalctl -u mediamtx -n 100 --no-pager
```

Bei eigenen Dienstnamen die Befehle entsprechend ändern. Die Medien-Automatik läuft in genau einem Gunicorn-Worker. Mehrere Web-Worker würden konkurrierende Encoder- und Chat-Verbindungen erzeugen.

## Daten und Backups

Zusammen sichern:

- `/var/lib/streamdesk/` einschließlich `app.db`, `fernet.key`, `session.key`, Medien und Aufnahmen.
- `STREAMDESK_NATIVE_ROOT`, standardmäßig `/var/lib/streamdesk-native/`, für native MediaMTX-Segmente einschließlich Besitzer und Rechten.
- `/etc/streamdesk.env`.
- Die im Env eingetragene MediaMTX-Konfiguration.
- Die beiden systemd-Units und die verwendete Anwendungsversion.

Für eine konsistente Komplettsicherung zuerst Streaming und Aufnahmen regulär stoppen, dann den UI-Dienst stoppen und die Daten kopieren. Für eine reine laufende Datenbanksicherung SQLite-Backup statt bloßem Kopieren der geöffneten DB-Datei verwenden.

Der Installer legt unter `/var/backups/streamdesk/` private Sicherungen an. Diese enthalten bei Updates die SQLite-Datenbank, Schlüssel, Konfiguration und Programmdateien. **Medien und Aufnahmen werden aus Platzgründen nicht kopiert** und bleiben im Datenordner liegen. Vor dem Löschen eines Containers eine vollständige Sicherung außerhalb dieses Containers erstellen, falls dessen Inhalte noch benötigt werden.

Ohne `fernet.key` lassen sich verschlüsselte Konten und Streamschlüssel nicht wiederherstellen. Geheimnisse, Backups und Mediendateien gehören nicht in ein öffentliches GitHub-Repository.

## Wiederherstellen

Fehlt die Datenbank, entscheiden zwischen einer Wiederherstellung aus einer vollständigen Sicherung und einem Neuanfang: `--mode attach --recover` legt eine neue Instanz mit neuen Zugangsdaten an und bewahrt vorhandene Reste auf. Es rekonstruiert keine gelöschten Konten. Der genaue Ablauf steht unter [Datenbank gelöscht](../INSTALL.md#datenbank-gelöscht-neue-instanz-an-bestehendem-mediamtx).

1. UI-Dienst stoppen.
2. Zusammengehörige Datenbank und Schlüssel aus derselben Sicherung zurückspielen; Medien im selben Datenordner wiederherstellen.
3. Passende Env- und MediaMTX-Konfiguration wiederherstellen. Bei bestehenden fremden Streams vorher spätere Konfigurationsänderungen vergleichen.
4. Die passende Programmversion bereitstellen, dann MediaMTX und den UI-Dienst starten.
5. Benutzerlogin, persönliche Quellen und gespeicherte Ziele prüfen, erst danach einen öffentlichen Stream starten.

Bei einem fehlgeschlagenen Update führt der Installer einen automatischen Rollback für Quellcode, DB und Konfiguration aus. Die private Sicherung bleibt erhalten. Systempakete und das virtuelle Python-Environment gehören nicht zum automatischen Rollback. Vor einem Update wird dessen Paketstand als `requirements-before.txt` gesichert. Falls Abhängigkeiten zurückgesetzt werden müssen, bei gestopptem Dienst das passende Environment mit dieser Datei neu aufbauen und anschließend die Anwendung prüfen. Vor einem großen Versionswechsel zusätzlich eine eigene vollständige Datensicherung anlegen.

Für Updates wird der UI-Dienst vor dem Backup gestoppt. Ist die Datenbank vorhanden, fehlen aber `fernet.key` oder `session.key`, bricht der Installer ab: Passende Schlüssel müssen aus derselben Sicherung wiederhergestellt werden. Eine neue Verschlüsselung kann bestehende gespeicherte Geheimnisse nicht entschlüsseln.

## Speicher und Aufnahmen

Eine manuelle MP4-Aufnahme startet ausschließlich manuell. Unter 350 MiB freiem Platz wird sie beendet; zum Start müssen mindestens 500 MiB frei sein. Nach einem Quellabbruch oder Neustart wird eine unterbrochene Datei soweit möglich zum Download bereitgestellt, jedoch keine manuelle Aufnahme automatisch neu begonnen.

Native Path-Aufnahmen werden gesondert im Expertenmodus aktiviert und laufen bei erneut verfügbarer Quelle weiter. Segmentdauer, Aufbewahrung, separater Speicher und Speicherüberwachung sind unter [Expertenmodus](EXPERT_MODE.md) beschrieben. Für eine vollständige Sicherung native Aufnahmen ebenfalls ausdrücklich deaktivieren und offene Segmente abschließen lassen.

Browser-Renderer laufen nur, wenn der zugehörige Offline-Modus mit verbundenem Ausgang aktiv ist. Nach Stopp oder Rückkehr einer Live-Quelle werden sie beendet. Chatverbindungen werden nach etwa 75 Sekunden ohne Dashboard-/Widget-Abruf geschlossen.

## Twitch-Sitzungen

Testintervalle: 5, 10 und 30 Minuten. Weitere Intervalle: 12, 24, 36 und 48 Stunden. Bei aktivem Twitch-Ausgang erfolgt die 48-Stunden-Auswahl zwei Minuten vorher. Die Trennpause ist einstellbar. YouTube-/Custom-Ausgänge bleiben bei einer Twitch-Erneuerung verbunden.

Das Ändern der Intervalle und manuelles Auslösen einer Neuverbindung benötigen ab 1.1.0-rc.1 den Expertenmodus. Bereits aktivierte Intervalle bleiben beim Ausschalten des Modus wirksam.

Eine kurze Neuverbindung setzt das Twitch-Sendelimit nicht garantiert zurück. Eine längere Trennung kann eine neue Sendung bewirken und ist für Zuschauer nicht unterbrechungsfrei. [Twitch Disconnect Protection](https://help.twitch.tv/s/article/Disconnect-Protection?language=en_US)

## Deinstallation

```bash
sudo bash uninstall.sh --service-name streamdesk
```

Dabei wird der UI-Dienst gestoppt/deaktiviert und sein reservierter Namensbereich aus der MediaMTX-Konfiguration entfernt. Die zuvor eingegrenzten globalen Medienberechtigungen werden wiederhergestellt. Benutzerdateien, Schlüssel, Datenbank, Backups und MediaMTX selbst bleiben erhalten. Erst nach Prüfung und einer externen Sicherung können die verbleibenden Dateien bei Bedarf manuell gelöscht werden.

## Playback, weitere Quellen und Custom-Ziele

Nach einem rc.4-Update bleiben bestehende Plattformschlüssel und Zielauswahlen erhalten; die Migration ergänzt Labels und Quellenoptionen automatisch. MediaMTX bleibt bei v1.21.3; Attach aktualisiert dessen Binary nicht. Die eigenständige Roadmap steht in [ROADMAP.md](../ROADMAP.md).

Playback verwendet einen internen Listener, per Standard `127.0.0.1:9996`. Native fMP4-Daten werden über MediaMTX gestreamt. Für MPEG-TS müssen `ffprobe` und `ffmpeg` im PATH des UI-Diensts liegen; beide gehören zum durch den Installer installierten FFmpeg-Paket. Bei fehlendem FFprobe können MPEG-TS-Zeitbereiche nicht ermittelt werden. Je UI-Prozess laufen höchstens zwei MPEG-TS-Konvertierungen. Temporäre Concat-Manifeste liegen im privaten Daten-Zwischenspeicher und werden nach dem Abruf entfernt. Die Segmente selbst werden nicht umgeschrieben.

Bei ausbleibendem Pull-Signal URL und Erreichbarkeit im MediaMTX-Journal prüfen; geheime URLs vor dem Teilen von Logs schwärzen. Die Quelle verbindet sich dauerhaft, auch wenn gerade eine höher priorisierte Quelle sendet. Der Pull-Schalter beendet sie. Benutzerdeaktivierung beendet alle eigenen Weiterleitungen, deaktiviert eigene native Aufnahmen und setzt den Pull auf Publisher ohne persönliche Publish-Berechtigung zurück.

Viele gleichzeitige Forwards vervielfachen den Upload-Bedarf. Ein Ziel kann im Expertenmodus gestoppt werden, ohne andere Ziele zu unterbrechen. Eine Änderung der Auswahl unter den normalen Einstellungen gilt weiterhin erst beim nächsten Gesamtstart.

## Programmvorschau und laufende Aufnahme

Ab rc.5 bleibt eine Programmaufnahme beim Quellenwechsel aktiv. Den Gesamtstopp für Streamingziele und den Aufnahme-Stopp getrennt bedienen: Ein gestopptes Ziel beendet weder die Aufnahme noch die Vorschau. Ohne Eingänge zeigt das Programm bei Verbrauchern das ausgewählte Offline-Video; kurze Übergänge werden mit Standby überbrückt.

Für das normalisierte Programm wird zusätzlich Video codiert. CPU-Auslastung mit mehreren gleichzeitig aktiven Benutzern prüfen. Die Experten-WebRTC-Programmvorschau wandelt nur Audio nach Opus und teilt ihren Prozess je Benutzer. Diagnose: `relay-<benutzer-id>.log` und `program-preview-<benutzer-id>.log` im privaten Datenordner. Wird der Medienserver selbst neu gestartet oder fällt der Aufnahmedienst tatsächlich aus, endet eine manuelle Aufnahme weiterhin; dies ist vom regulären Quellenwechsel zu unterscheiden.

## Routing und Accountverwaltung ab rc.6

Nur Source 1/2 sind Standard. Zusätzliche Quellen und Konten sowie die Zuordnung pro Ausgang werden im Expertenmodus angelegt. Gleiche Quellenmengen teilen sich eine Pipeline, unterschiedliche Programme benötigen jeweils Encoderleistung. Bei vielen parallelen Programmen CPU und ausgehende Bandbreite prüfen. Ein manuelles Programmaufnahmeende sendet FFmpeg einen regulären Abschlussbefehl; kurze Fragmente begrenzen zusätzlich ungefluschte Schlussdaten.

Unter „Mein Konto“ kann jeder Benutzer sein eigenes Passwort ändern. Unter „Administration“ kann ein Administrator andere deaktivierte Benutzer löschen; aktive Konten, das eigene Administratorkonto und laufende Verarbeitung/Abschlüsse sind geschützt.

Bei Kontolöschung werden Datenbankeinträge, eigene MediaMTX-Pfade und Berechtigungen entfernt. Medien- und Aufnahmeordner werden im selben Dateisystem in `.deleted-<name>-<id>-…` umbenannt, auch im nativen Aufnahmebereich. Ein privates Manifest unter `STREAMDESK_DATA/deleted-users/<id>-…/manifest.json` enthält Zuordnung und Metadaten. Die Archive sind nicht über die Anwendung abrufbar und zählen weiterhin zum belegten Speicher. Sie benötigen die ursprünglichen Schlüssel für verschlüsselte Daten. Es erfolgt keine endgültige Löschung der Mediendateien. Benutzer-IDs und zusätzliche Quellenkennungen werden nicht wiederverwendet.
