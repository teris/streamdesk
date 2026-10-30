# Konfiguration

Die aktive Datei ist standardmäßig `/etc/streamdesk.env`; bei einem eigenen Dienstnamen `/etc/<dienstname>.env`. Der Installer erzeugt sie mit root-exklusiven Leserechten. Nach manuellen Änderungen den UI-Dienst neu starten.

| Variable | Zweck |
| --- | --- |
| `STREAMDESK_PUBLIC` | Öffentliche UI-Adresse ohne Unterpfad; OAuth-Rückruf und Widget-Links werden daraus gebildet. |
| `STREAMDESK_INGEST` | Vom Encoder erreichbarer Hostname bzw. IP. |
| `STREAMDESK_BIND` | Gunicorn-Listener, Standard `0.0.0.0:8080`. |
| `STREAMDESK_DATA` | Datenbank, Schlüssel, Benutzer-Medien, Aufnahmen und Upload-Zwischenspeicher. |
| `STREAMDESK_APP_DIR` | Vom Installer ab 1.1.0-rc.2 gespeicherter Programmordner für spätere Updates und Wiederaufsetzen. |
| `STREAMDESK_NATIVE_ROOT` | Separates Verzeichnis für native MediaMTX-Segmente, Standard als Nachbar von `STREAMDESK_DATA`: `/var/lib/streamdesk-native`. Installer gibt ausschließlich diesen Bereich dem MediaMTX-Dienstbenutzer. |
| `STREAMDESK_DEFAULT_CLIP` | Persönliche Standby-Vorlage, vom Installer selbst erzeugt. |
| `STREAMDESK_NAMESPACE` | Reservierter MediaMTX-Präfix, Standard `streamdesk`. Nach Einrichtung nicht ohne Datenmigration ändern. |
| `MEDIAMTX_CONFIG` | Lokal schreibbare MediaMTX-Konfiguration. |
| `MEDIAMTX_API` | Lokaler API-Endpunkt inklusive `/v3/`. |
| `MEDIAMTX_API_CA` | Optionale lokale CA-Datei zur Zertifikatsprüfung einer verschlüsselten Control API. |
| `MEDIAMTX_METRICS` | Lokaler Prometheus-Endpunkt; Werte werden vor Ausgabe auf den angemeldeten Tenant-Präfix begrenzt. |
| `MEDIAMTX_RTSP` | Lokaler RTSP-Endpunkt inklusive abschließendem `/`. |
| `MEDIAMTX_HLS` | Lokaler HLS-Endpunkt inklusive abschließendem `/`. |
| `MEDIAMTX_WEBRTC` | Optionaler lokaler WHIP-/WHEP-Endpunkt inklusive abschließendem `/`. Ohne Angabe aus `webrtcAddress` und `webrtcEncryption` der lokalen Konfiguration abgeleitet. |
| `MEDIAMTX_PLAYBACK` | Optionaler interner Playback-Endpunkt. Sonst aus `playbackAddress` und `playbackEncryption` abgeleitet; gültige TLS-Zertifikate erforderlich. |
| `MEDIAMTX_RTMP_PORT` | Port, der in den OBS-Adressen angezeigt wird. |
| `MEDIAMTX_SRT_PORT` | Port, der in den Handy-Adressen angezeigt wird. |
| `STREAMDESK_LOCAL_IPS` | Eigene lokale Quelladressen für die Medien-/API-Dienstberechtigung. Keine fremden Client-IP-Adressen eintragen. |
| `STREAMDESK_BROWSER_ROOT` | Separater temporärer Bereich für unprivilegierte Browser-Renderer. |
| `STREAMDESK_BROWSER_USER` | Systemkonto für Renderer, Standard `streamdesk-browser`. |
| `STREAMDESK_BROWSER_LIMIT` | `auto` oder maximale Anzahl paralleler Browser-Overlays. |
| `STREAMDESK_BROWSER_FPS` | Browserbildrate von 1 bis 30; Standard 10. |
| `COOKIE_SECURE` | Bei öffentlichem HTTPS `1`. |
| `STREAMDESK_TRUST_PROXY` | `1`, wenn ein Reverse Proxy `X-Forwarded-For` / `X-Forwarded-Proto` setzt. Ohne Proxy auf `0` lassen, sonst sind Client-IPs spoofbar. |
| `STREAMDESK_MEDIAMTX_SERVICE` | MediaMTX-Dienstname für weitere Installations-/Update-Aufrufe. |
| `STREAMDESK_MEDIAMTX_BINARY` | Bestehendes MediaMTX-Programm für Update-Prüfungen. |

Der Installer leitet lokale Endpunkte aus der vorhandenen MediaMTX-Konfiguration ab. Nach manueller Änderung eines Medienports auch die betreffenden Env-Werte anpassen. API-/HLS-TLS-Zertifikate werden regulär geprüft.

Der UI-Dienst arbeitet als festes Systemkonto `streamdesk`. Ein vom Installer bereitgestelltes MediaMTX verwendet `streamdesk-media`; bei Attach wird dessen vorhandene feste Identität übernommen. Ein dediziertes Konfigurationsverzeichnis erhält eine ACL für atomare UI-Schreibvorgänge. Für native Aufnahmen werden Setgid-Verzeichnisse und vererbte Benutzer-ACLs eingerichtet; dadurch bleiben Aufnahmen auch bei `UMask=0077` lesbar. Der private Datenordner bleibt davon getrennt. Browser-Overlays laufen bei nativer Installation unter `streamdesk-browser`; die UI besitzt nur `CAP_SETUID`/`CAP_SETGID` zum Starten und Beenden dieser Renderer unter deren Identität. Im Docker-Paket laufen UI und Renderer im selben Containerkonto.

Neue Betriebseinstellungen: `MEDIAMTX_API_CA` enthält eine optionale CA-Datei für die Control API; `MEDIAMTX_METRICS` die interne Metrics-URL; `STREAMDESK_HOOK_ALLOWLIST` ein JSON-Objekt erlaubter Befehle. `STREAMDESK_MEDIAMTX_MODE=remote-api` kennzeichnet entfernte Instanzen. Native Dateifunktionen dort benötigen identisch eingebundenen Speicher und die ausdrückliche Freigabe `STREAMDESK_NATIVE_SHARED=1`. Konfiguration siehe [Installation](../INSTALL.md).

Die Control API kann beim Installieren oder Update ausdrücklich mit `--enable-api-tls --api-cert … --api-key …` verschlüsselt werden. Für eine private CA wird zusätzlich `--api-ca …` angegeben. StreamDesk prüft das Serverzertifikat bei Healthchecks und allen späteren API-Aufrufen; eine Deaktivierung der Prüfung ist nicht vorgesehen.

RTMPS und RTSPS werden mit `--enable-ingest-tls --ingest-cert … --ingest-key …` eingerichtet. Danach kann ein Administrator unter **Expertenmodus → Protokolle & WebRTC** zwischen unverschlüsselt, optional und erforderlich wählen. Der dortige Upload-Grenzwert steuert die Warnung ab 85 Prozent gemessener Ausgangsbandbreite; `0` deaktiviert sie.

## Erweiterungen ab 1.1.0-rc.4

Playback ist bei Neuinstallationen aus. Ein Administrator aktiviert es unter **Expertenmodus → Playback**, mit einem Loopback-Listener wie `127.0.0.1:9996`. Alternativ beim Installieren/Update ausdrücklich `--enable-playback --playback-port 9996` angeben. Ohne diesen Schalter bleiben bestehende Playback-Listener, Aktivierung und TLS-Einstellungen erhalten. Der Port muss vom UI-Prozess erreichbar sein; eine öffentliche Portfreigabe ist für StreamDesk nicht nötig. Vorhandene externe Playback-Listener in Attach-Installationen werden nur durch eine ausdrückliche Änderung umkonfiguriert.

Ab rc.6 sind nur Source 1 und Source 2 standardmäßig vorhanden. Weitere Quellen erhalten erst beim ausdrücklichen Anlegen einen eigenen Tenant-Pfad, z. B. `<namespace>/<benutzer>/source3`. Die alten Vorschauen `/preview/1/`, `/preview/2/`, `/preview/3/` bleiben für Source 1, Source 2 und Standardprogramm gültig. Neue source-spezifische Links verwenden `/preview/source/<quellen-id>/`, Programme `/program/<programm-id>/`. Alle sind durch die angemeldete Eigentümersitzung geschützt.

Die Tabellen `routing_sources`, `output_routing` und `routing_programs` speichern zusätzliche Quellen, Ausgangszuordnungen und die Historie stabiler Programme. Die Quellenmenge bestimmt die Programmkennung; die Priorität wird unabhängig davon gespeichert. Gleiche Mengen teilen sich eine Pipeline, unterschiedliche Mengen können unabhängig senden. In `outputs` bleiben die festen Kennungen `twitch`, `youtube`, `custom` erhalten; zusätzliche Ausgänge heißen `twitch-<id>`, `youtube-<id>` bzw. `custom-<id>`. Zugangsdaten werden verschlüsselt in der Datenbank und nur soweit für MediaMTX erforderlich in der privaten YAML gespeichert.

RTSP-/RTSPS-Pull-Quellen sind optional und benötigen öffentliche Ziele. Lokale/private/link-local und eigene Ingest-Adressen werden wie bei Forwards abgelehnt. DNS wird beim Speichern einer Adresse und beim erneuten Aktivieren geprüft; Deaktivieren benötigt keine erneute DNS-Auflösung. Diese Prüfung ersetzt keine ausgehende Netzwerk-Firewall.

Die Migration übernimmt nachweislich genutzte frühere Source-3-/Pull-Konfigurationen, Aufnahmen und bestehende Ausgänge. Eine unbenutzte, zuvor automatisch erzeugte Source 3 entfällt. Ist die MediaMTX-API während der Migration nicht erreichbar, bleibt ein vorhandener Source-3-Pfad vorsichtshalber als zusätzliche Quelle erhalten. Bestehende Ausgabezuordnungen bleiben erhalten; für neue Benutzer gelten ausschließlich Source 1/2. Eine native Aufnahme eines bisherigen erweiterten Programms wird dessen fortgeführter Programmgruppe zugeordnet. Historische Dateien bleiben erreichbar. Die alte globale manuelle Quellenwahl wird durch die je Ausgang festen Prioritäten ersetzt.

## Programmpfad ab 1.1.0-rc.5

`<präfix>/live` bleibt für aktive Benutzer mit `alwaysAvailable: true` verfügbar. Die Einstellung hängt nicht mehr von der Forward-Liste ab; Ziel-Start/Stopp setzt sie nicht zurück. `alwaysAvailableRecorded: true` hält ausdrücklich aktivierte native Programmaufnahmen während Quellenlücken am Standby-Signal. Es werden keine Aufnahmen automatisch aktiviert. Deaktivierte Benutzer erhalten keinen verfügbaren Programmpfad.

Das Programm verwendet H.264 Baseline, 1080p30 ohne B-Frames, ungefähr 4,5 Mbit/s Video und AAC/48 kHz/Stereo. Für die zusätzliche Videoaufbereitung CPU einplanen. Nur die WebRTC-Programmvorschau liest den separaten persönlichen Pfad `webrtc-program` mit H.264/Opus. Seine Videodaten werden aus dem normalisierten Programm kopiert; dafür ist kein zweiter Videoencoder erforderlich. `libopus` ist Bestandteil des durch den Installer installierten Debian-FFmpeg-Pakets.

Vorschau, manuelle Programmaufnahme, aktivierte native Programmaufnahme und Streamingziele zählen als Verbraucher. Ohne Live-Quelle und ohne Verbraucher wird kein Offline-/Browser-Renderer gestartet. Die MediaMTX-Standby-Verfügbarkeit selbst legt keine zusätzliche Datei an. Direkte Eingangs-/Programmdateirechte und fremde Attach-Pfade bleiben unverändert.

## Konten ab rc.6

Die Tabelle `user_id_sequence` reserviert Benutzer-IDs dauerhaft; nach einer Kontolöschung wird keine alte ID für ein neues Konto wiederverwendet. Dies schützt alte Sitzungscookies vor Zuordnung zu einem neuen Benutzer. Ein Passwortwechsel erhöht weiterhin die Sitzungsversion und aktualisiert nur die aktuelle Anmeldung.


### Vorschauton und Playlist-Audio ab 2.0.0-rc3

Unter der Dashboard-Programmvorschau stehen **Ton einschalten / ausschalten** und **Lautstärke** direkt zur Verfügung. Diese persönliche Wiedergabesteuerung benötigt keinen Expertenmodus und verändert den Ton der Streaming-Ausgänge nicht. Neue Vorschauen beginnen stumm, damit Browser sie automatisch starten können. Nach einer vom Browser blockierten Tonwiedergabe kann der Benutzer ihn erneut per Klick freigeben. Separat geöffnete HLS- und WebRTC-Player bieten dieselben Tonfunktionen.

Die gemeinsame Source-2-Playlist verwendet den privaten RTSP-Hilfspfad `playlist-source2`. Beim Weiterreichen an ein Programm bleibt H.264 unverändert; dessen Audiospur wird als AAC/48 kHz/Stereo mit zur Videospur passender Zeitbasis ausgegeben. Die WebRTC-Brücke wandelt sie entsprechend nach Opus. Die Vorbereitung benötigt beide veröffentlichten Spuren und setzt fehlgeschlagene Prozesse zurück. Eine maximal 45 Sekunden gültige Startfrist verhindert, dass die normale Leerlaufbereinigung den Prozess während der Verbindungsvorbereitung beendet; anschließend gilt wieder die normale Leerlauflogik. Quellenprioritäten, öffentliche Listener und Zugangsdaten werden durch diese Korrektur nicht verändert.

Ab rc4 startet auch der gemeinsame Playlist-Encoder ohne blockierendes Warten. Solange er vorbereitet wird, bleibt derselbe Prozess bestehen; nach spätestens 45 Sekunden ohne erstes Signal wird er aufgeräumt. Eine zurückkehrende Live-Quelle hat weiterhin Vorrang. Interne RTSP-Publisher verwenden 1200 Byte Paketgröße, damit MediaMTX die Pakete nicht nachträglich verkleinern muss.

Ab rc5 verlangt die Startprüfung mehrere Videoframes und eine positive Ausgabezeit. Eine Pfadanmeldung oder ein einzelner Frame ohne Ausgabezeit reicht nicht. Fortsetzpositionen in den letzten 250 Millisekunden der gemeinsamen Schleife beginnen beim nächsten Durchlauf, damit Container-/Audio-Rundung keinen Einstieg hinter dem letzten abspielbaren Frame verursacht. Ein manuelles Zurücksetzen der Datenbank ist dafür nicht erforderlich.

## Speicher für Videoimporte ab 2.0.0-rc6

MP4-Dateien für Playlists und Offline-Videos haben über Web und FTPS keine feste Größen- oder Laufzeitgrenze. Upload und Umwandlung haben kein festes Gesamtzeitlimit. Web-Uploads liegen während des Empfangs direkt unter `STREAMDESK_DATA/uploads` und werden ohne zweite vollständige Dateikopie übernommen. Vor dem Empfang wird die angekündigte Datenmenge, während des Empfangs der tatsächlich noch freie Platz geprüft. Bei nicht ausreichendem Speicher antwortet die Weboberfläche mit einer Speichermeldung (HTTP 507). Unfertige Web-Zwischendateien werden bei Anfrageende beziehungsweise beim Serverneustart entfernt.

Vor der Umwandlung wird zusätzlicher Ausgabespeicher mit ungefähr 650.000 Byte pro Videosekunde reserviert, zuzüglich **350 MiB Betriebsreserve**. Das Original belegt währenddessen ebenfalls Platz. Ein zweistündiges Video benötigt so ungefähr 4,7 GB zusätzlichen freien Platz neben seiner bereits gespeicherten Originaldatei. Reservierungen anderer laufender Umwandlungen werden berücksichtigt; höchstens zwei Benutzer können gleichzeitig verarbeiten. Während FFmpeg läuft, wird freier Platz überwacht; bei Unterschreiten der Reserve wird die Verarbeitung abgebrochen und die Teilausgabe entfernt. Das sind Speicherprüfungen, keine Obergrenzen je Video.

Fehlgeschlagene FTP-Originale bleiben für einen erneuten Import erhalten und können unter **Medien → FTP-Importe** ausdrücklich gelöscht werden. Fertige Bibliotheksdateien werden im FTP-Bereich über Hardlinks angezeigt und belegen dadurch keinen zweiten vollständigen Dateispeicher. Für große HTTP-Uploads gelten zusätzlich die Einstellungen des eigenen [Reverse Proxys](PROXY.md). Die MP4-/Videoprüfung und getrennte Benutzerrechte bleiben erforderlich.
