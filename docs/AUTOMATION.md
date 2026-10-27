# Automation, Zeitplan und Export

## Sichere Hooks

Der Administrator stellt ausführbare Aktionen ausschließlich über `STREAMDESK_HOOK_ALLOWLIST` als JSON-Objekt bereit, zum Beispiel:

```text
{"discord-notify":["/usr/local/bin/streamdesk-notify","--channel","operations"]}
```

Benutzer wählen nur den Namen einer freigegebenen Aktion. Es gibt keine Shell-Auswertung. Prozesse erhalten eine minimale Umgebung ohne Zugangsdaten, laufen höchstens 15 Sekunden und reagieren auf „Quelle veröffentlicht“ oder „Programm bereit“.

## Zeitplan

Aufnahme- und Ausgangsaktionen werden in SQLite gespeichert, nach einem Neustart weiterverarbeitet und genau einem Benutzer zugeordnet. Zeitpunkte werden intern als UTC-Epoch gespeichert; die Oberfläche verwendet die lokale Browserzeit. Ein eigener Hintergrundarbeiter führt die Aufträge aus. Die Übernahme eines offenen Auftrags erfolgt atomar. Wurde ein bereits laufender Auftrag durch einen Neustart unterbrochen, wird er als Fehler markiert und muss vor erneuter Ausführung geprüft werden; externe Startaktionen werden dadurch nicht unbemerkt doppelt ausgelöst.

## Export

Fertige manuelle MP4-Aufnahmen können per HTTPS-PUT an eine WebDAV-/Upload-Zielbasis übertragen werden. Das Ziel muss HTTPS ohne Queryparameter verwenden und mit `/` enden. Beliebige vorsignierte S3-URLs werden nicht unterstützt, da ihre Signatur normalerweise an einen konkreten Objektnamen gebunden ist. Private, lokale und eigene Ingest-Ziele sind gesperrt. Die TCP-Verbindung verwendet eine geprüfte DNS-Adresse, TLS validiert weiterhin den ursprünglichen Hostnamen; HTTP-Weiterleitungen werden abgelehnt.

Exporte laufen separat von Quellensteuerung und Zeitplan. Dateien werden vom Dateideskriptor übertragen und nicht vollständig in den Arbeitsspeicher geladen. Ein Suchlauf erfolgt frühestens alle zehn Sekunden; fehlgeschlagene Dateien erhalten fünf Minuten Wartezeit. Zugangsdaten liegen verschlüsselt in SQLite; erfolgreiche Datei-/Zeitstempel-Kombinationen werden nicht erneut übertragen. Während eines Exports oder einer Clip-Erstellung wird die Kontolöschung zurückgestellt.

## Routing

Stabilitäts-, Stillstands- und Retry-Zeitwerte sind pro Benutzer konfigurierbar. Externe Quellen können `sourceOnDemand` verwenden: Sobald ein zugeordnetes Programm Zuschauer, eine Aufnahme oder einen aktiven Ausgang hat, hält ein leichter RTSP-Leser die Quelle aktiv. Ohne Verbraucher endet dieser Leser wieder. Optional kopiert StreamDesk das gewählte Offline-Video in den gemeinsamen nativen Speicher und verwendet diesen lesbaren Pfad für `alwaysAvailableFile`; der private Datenordner wird nicht geöffnet. Pfad-Proxys akzeptieren ausschließlich öffentliche, SSRF-geprüfte Medienadressen.
