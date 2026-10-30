# Reverse Proxy / NPMplus

Im Proxy-Host die öffentliche Domain auf `http://SERVER-IP:8080` leiten, ein TLS-Zertifikat wählen und HTTPS erzwingen. `STREAMDESK_PUBLIC` muss genau diese öffentliche Adresse ohne Unterpfad enthalten.

Wenn NPMplus auf einem anderen Host bzw. Container läuft, muss der UI-Listener von dort erreichbar sein (Standard `0.0.0.0:8080`). Für einen Proxy auf demselben Host kann `--bind 127.0.0.1:8080` verwendet werden.

Advanced-Konfiguration für NPMplus:

```nginx
client_max_body_size 0;
proxy_request_buffering off;
proxy_buffering off;
proxy_read_timeout 600s;
proxy_send_timeout 600s;
```

`client_max_body_size 0` hebt die feste Dateigrößenbegrenzung des Proxys auf. Bereits vorhandene Proxy-Hosts müssen entsprechend aktualisiert werden; der StreamDesk-Installer verändert externe Proxy-Einstellungen nicht. Auch vorgeschaltete Dienste dürfen große Uploads nicht begrenzen. Die Zeitwerte betreffen ausbleibende Übertragung, nicht die Gesamtdauer eines laufenden Uploads. Die Umwandlung läuft nach der Uploadantwort im Hintergrund. FTPS überträgt direkt zum Ingest-Host und benötigt diese HTTP-Einstellung nicht.

Diese Direktiven in den bestehenden Proxy-Host eintragen, keinen zusätzlichen `location /`-Block anlegen. `Host`, `X-Forwarded-For` und `X-Forwarded-Proto` müssen korrekt weitergegeben werden. Bei HTTPS setzt der Installer `STREAMDESK_TRUST_PROXY=1`, damit Login-Rate-Limits und Cookies die Proxy-Header nutzen. Ohne echten Proxy diesen Wert auf `0` lassen. API, Vorschau und HTML nicht cachen. Der UI-Port sollte im normalen Betrieb nur vom Proxy erreichbar sein.

Der Browser benötigt keine eingehende WebSocket-Weiterleitung: Der Server baut die Twitch-WebSocket- und YouTube-gRPC-Verbindungen ausgehend auf; Dashboard und Widgets fragen ihre Daten über HTTP ab. Die Vorschau nutzt den lokalen HLS-Proxy im UI.

OBS und Handy senden direkt an die Ingest-Ports von MediaMTX. Ein gewöhnlicher HTTP-Proxy-Host ersetzt weder TCP-RTMP noch UDP-SRT.
