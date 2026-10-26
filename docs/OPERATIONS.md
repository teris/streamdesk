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
- `/etc/streamdesk.env`.
- Die im Env eingetragene MediaMTX-Konfiguration.
- Die beiden systemd-Units und die verwendete Anwendungsversion.

Für eine konsistente Komplettsicherung zuerst Streaming und Aufnahmen regulär stoppen, dann den UI-Dienst stoppen und die Daten kopieren. Für eine reine laufende Datenbanksicherung SQLite-Backup statt bloßem Kopieren der geöffneten DB-Datei verwenden.

Der Installer legt unter `/var/backups/streamdesk/` private Sicherungen an. Diese enthalten bei Updates die SQLite-Datenbank, Schlüssel, Konfiguration und Programmdateien. **Medien und Aufnahmen werden aus Platzgründen nicht kopiert** und bleiben im Datenordner liegen. Vor dem Löschen eines Containers eine vollständige Sicherung außerhalb dieses Containers erstellen, falls dessen Inhalte noch benötigt werden.

Ohne `fernet.key` lassen sich verschlüsselte Konten und Streamschlüssel nicht wiederherstellen. Geheimnisse, Backups und Mediendateien gehören nicht in ein öffentliches GitHub-Repository.

## Wiederherstellen

1. UI-Dienst stoppen.
2. Zusammengehörige Datenbank und Schlüssel aus derselben Sicherung zurückspielen; Medien im selben Datenordner wiederherstellen.
3. Passende Env- und MediaMTX-Konfiguration wiederherstellen. Bei bestehenden fremden Streams vorher spätere Konfigurationsänderungen vergleichen.
4. Die passende Programmversion bereitstellen, dann MediaMTX und den UI-Dienst starten.
5. Benutzerlogin, persönliche Quellen und gespeicherte Ziele prüfen, erst danach einen öffentlichen Stream starten.

Bei einem fehlgeschlagenen Update führt der Installer einen automatischen Rollback für Quellcode, DB und Konfiguration aus. Die private Sicherung bleibt erhalten. Systempakete und das virtuelle Python-Environment gehören nicht zum automatischen Rollback. Vor einem Update wird dessen Paketstand als `requirements-before.txt` gesichert. Falls Abhängigkeiten zurückgesetzt werden müssen, bei gestopptem Dienst das passende Environment mit dieser Datei neu aufbauen und anschließend die Anwendung prüfen. Vor einem großen Versionswechsel zusätzlich eine eigene vollständige Datensicherung anlegen.

## Speicher und Aufnahmen

Eine Aufnahme startet ausschließlich manuell. Unter 350 MiB freiem Platz wird sie beendet; zum Start müssen mindestens 500 MiB frei sein. Nach einem Quellabbruch oder Neustart wird eine unterbrochene Datei soweit möglich zum Download bereitgestellt, jedoch keine Aufnahme automatisch neu begonnen.

Browser-Renderer laufen nur, wenn der zugehörige Offline-Modus mit verbundenem Ausgang aktiv ist. Nach Stopp oder Rückkehr einer Live-Quelle werden sie beendet. Chatverbindungen werden nach etwa 75 Sekunden ohne Dashboard-/Widget-Abruf geschlossen.

## Twitch-Sitzungen

Testintervalle: 5, 10 und 30 Minuten. Weitere Intervalle: 12, 24, 36 und 48 Stunden. Bei aktivem Twitch-Ausgang erfolgt die 48-Stunden-Auswahl zwei Minuten vorher. Die Trennpause ist einstellbar. YouTube-/Custom-Ausgänge bleiben bei einer Twitch-Erneuerung verbunden.

Eine kurze Neuverbindung setzt das Twitch-Sendelimit nicht garantiert zurück. Eine längere Trennung kann eine neue Sendung bewirken und ist für Zuschauer nicht unterbrechungsfrei. [Twitch Disconnect Protection](https://help.twitch.tv/s/article/Disconnect-Protection?language=en_US)

## Deinstallation

```bash
sudo bash uninstall.sh --service-name streamdesk
```

Dabei wird der UI-Dienst gestoppt/deaktiviert und sein reservierter Namensbereich aus der MediaMTX-Konfiguration entfernt. Die zuvor eingegrenzten globalen Medienberechtigungen werden wiederhergestellt. Benutzerdateien, Schlüssel, Datenbank, Backups und MediaMTX selbst bleiben erhalten. Erst nach Prüfung und einer externen Sicherung können die verbleibenden Dateien bei Bedarf manuell gelöscht werden.
