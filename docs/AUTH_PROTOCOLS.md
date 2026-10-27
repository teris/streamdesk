# Authentifizierung und Spezialprotokolle

Globale Änderungen benötigen ein Administratorkonto und den ausdrücklich aktivierten Expertenmodus.

## MediaMTX-Authentifizierung

Unter **Protokolle & WebRTC** ist derzeit ausschließlich `internal` freigegeben. Die neue HTTP-/JWT-Umschaltung ist in Oberfläche und API gesperrt: StreamDesk stellt bisher persönliche Benutzer-/Passwort-Zugänge und interne Relay-Rechte aus, keine vollständige JWT-/IdP-Anbindung. Ein bloßer globaler Wechsel würde Vorschau, Aufnahme und Konfigurationsabgleich unterbrechen. API, Metrics und pprof werden dafür nicht pauschal von der Authentifizierung ausgenommen. Bestehende externe Auth-Konfigurationen werden beim Attach weiterhin abgelehnt.

Voraussetzungen für eine spätere Freigabe:

1. MediaMTX-Konfiguration und StreamDesk-Daten sichern.
2. IdP/Auth-URL mit einem Testkonto und allen benötigten Aktionen prüfen.
3. Wartungsfenster einplanen. Attach ändert eine bestehende externe Auth-Konfiguration weiterhin nicht automatisch.

## Quellenprotokolle

- RTMP, SRT, WebRTC/WHIP und MoQ verwenden persönliche Publish-Rechte.
- SRT-Verbindungsdaten enthalten zusätzlich eine persönliche Leseadresse für externe Decoder.
- MPEG-TS und RTP sind in MediaMTX statische UDP-Quellen pro Pfad. Ein Wildcard-Listener wird nur mit einer festen öffentlichen `source`-IP akzeptiert; alternativ ist Multicast zulässig. RTP benötigt zusätzlich eine SDP-Beschreibung.
- MoQ ist experimentell und global standardmäßig deaktiviert.

RTMPS/RTSPS-Zertifikate werden über den Installer eingerichtet. Dieser aktiviert zunächst den optionalen Modus, damit die internen RTSP-Programme erhalten bleiben. Die Umschaltung auf ausschließlich RTSPS benötigt einen bereits eingerichteten `rtsps://`-Endpunkt für die interne Verarbeitung; andernfalls lehnt die API den Wechsel ab.
