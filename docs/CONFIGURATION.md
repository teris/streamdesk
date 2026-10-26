# Konfiguration

Die aktive Datei ist standardmäßig `/etc/streamdesk.env`; bei einem eigenen Dienstnamen `/etc/<dienstname>.env`. Der Installer erzeugt sie mit root-exklusiven Leserechten. Nach manuellen Änderungen den UI-Dienst neu starten.

| Variable | Zweck |
| --- | --- |
| `STREAMDESK_PUBLIC` | Öffentliche UI-Adresse ohne Unterpfad; OAuth-Rückruf und Widget-Links werden daraus gebildet. |
| `STREAMDESK_INGEST` | Vom Encoder erreichbarer Hostname bzw. IP. |
| `STREAMDESK_BIND` | Gunicorn-Listener, Standard `0.0.0.0:8080`. |
| `STREAMDESK_DATA` | Datenbank, Schlüssel, Benutzer-Medien, Aufnahmen und Upload-Zwischenspeicher. |
| `STREAMDESK_DEFAULT_CLIP` | Persönliche Standby-Vorlage, vom Installer selbst erzeugt. |
| `STREAMDESK_NAMESPACE` | Reservierter MediaMTX-Präfix, Standard `streamdesk`. Nach Einrichtung nicht ohne Datenmigration ändern. |
| `MEDIAMTX_CONFIG` | Lokal schreibbare MediaMTX-Konfiguration. |
| `MEDIAMTX_API` | Lokaler API-Endpunkt inklusive `/v3/`. |
| `MEDIAMTX_RTSP` | Lokaler RTSP-Endpunkt inklusive abschließendem `/`. |
| `MEDIAMTX_HLS` | Lokaler HLS-Endpunkt inklusive abschließendem `/`. |
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

Der UI-Dienst arbeitet derzeit als root, weil er lokale Medienpfade, Benutzerdateien und die MediaMTX-Konfiguration verwaltet. Browser-Overlays laufen unter einem separaten Systemkonto mit temporärem Arbeitsverzeichnis. Die systemd-Unit begrenzt schreibbare Bereiche. Eine Trennung der gesamten Verwaltungsanwendung auf einen weniger privilegierten Dienstbenutzer ist ein möglicher zukünftiger Ausbau.
