# Feature-Übersicht – MediaMTX - StreamDesk

Stand: Version 1.1.0 · Bezug: MediaMTX **v1.21.3**
Dies ist ein Community-UI um MediaMTX, kein offizieller Bestandteil von MediaMTX.

---

## Bereits implementiert

### Oberfläche und Mehrbenutzer

| Feature | Beschreibung |
| --- | --- |
| Dashboard | Empfangs-/Sendedatenrate, Programmstatus, Speicherbelegung, Session- und Gesamtsendezeit |
| Persönliche Konten | Getrennte Eingänge, Videos, Aufnahmen, Ausgänge und Chat-Widgets pro Benutzer |
| Administration | Benutzer anlegen/aktivieren, Twitch- und Google-App-Credentials |
| Anmeldung | Session, CSRF, Rate-Limits (IP + Benutzername), optional Proxy-Trust |
| Installer | `attach` (bestehendes MediaMTX), `standalone` (MediaMTX mitliefern), `update`; `--recover` für Neuanfang bei fehlender Datenbank |
| Expertenmodus | Eigener Menüpunkt und Untermenüs; pro Anmeldung standardmäßig aus, serverseitige Prüfung technischer Endpunkte, globale Einstellungen zusätzlich nur für Administratoren |
| Theme und Mobilgeräte | Helles/dunkles/System-Theme pro Benutzer und Touch-Bedienelemente, unabhängig vom Expertenmodus |

### Erweiterungen in 1.1.0

Die folgenden **Einstellungen und technischen Aktionen benötigen den Expertenmodus**. Bereits gespeicherte Einstellungen bleiben beim Ausschalten wirksam. Normale Bedienung, Chat, Medienbibliotheken und Design bleiben verfügbar. Details: [Expertenmodus](docs/EXPERT_MODE.md).

| Feature | Umfang |
| --- | --- |
| Routing je Ausgang | Source 1 / Source 2 sowie ausdrücklich angelegte Zusatzquellen; Priorität und Zuordnung gelten je Ausgang |
| Per-Ziel Start/Stopp | Einzelne konfigurierte Ziele steuern, andere Ziele und nächste Startauswahl erhalten |
| WebRTC Publish/Play | Browser-Kamera über WHIP, Vorschau über WHEP, tenantbezogener Signalisierungsproxy |
| WebRTC-Servereinstellung | Aktivierung und zusätzliche erreichbare Hosts, zusätzlich Administratorrechte erforderlich |
| Native Path-Aufnahme | fMP4/MPEG-TS auf Source 1, Source 2 oder Programm; Segmentdauer und Aufbewahrung; separater privater Speicher |
| Native Segmentbibliothek | Download und fMP4-Vorschau auch ohne Expertenmodus; kein MediaMTX-Playback-Server |
| Öffentliche HLS-Seite | Persönlicher erneuerbarer/widerrufbarer Zuschauer-Link, ausschließlich Programm und lesender Zugriff |
| Twitch-Neuverbindung | Bestehende Intervallsteuerung und manuelle Neuverbindung jetzt nur im Expertenmodus |

### MediaMTX – genutzt

| Feature | Nutzung in StreamDesk |
| --- | --- |
| Control API (`/v3/`) | Pfade anlegen/patchen, Status, Forward-Ziele, Verfügbarkeit |
| Interne Authentifizierung | Pro Benutzer Publish/Read auf den eigenen Namensbereich |
| Privater Präfix | `streamdesk/<benutzer>/…` (oder anderer `--namespace`) |
| RTMP-Publish | Source 1 (OBS), geschützt mit Benutzer/Passwort |
| SRT-Publish | Source 2 (Handy), Stream-ID mit Zugangsdaten |
| RTSP intern | Relay, Aufnahme, Wiederholung und Weiterleitung im Backend |
| HLS | Interne Vorschau (Dashboard/Quellen), lokal gebunden |
| Path-Forward | Multistream an Twitch, YouTube und/oder Custom-RTMP(S)/SRT/RTSP |
| Always-available | Live-Pfad bleibt bei verbundenem Ausgang „bereit“ (Standby-Tracks) |
| Hot-Reload | YAML-Schreiben + API-Patch; MediaMTX lädt Konfiguration nach |
| Fremde Pfade | Attach-Modus lässt fremde Streams und Konten unberührt |

### Quellen und Programm

| Feature | Beschreibung |
| --- | --- |
| Zwei feste Live-Quellen | Source 1 (OBS, Vorrang) und Source 2 (Handy, Fallback), unveränderlich |
| Zusätzliche Quellen | Bis zu zehn Quellen insgesamt; zusätzliche Publish- oder öffentliche RTSP-/RTSPS-Pull-Quellen nur im Expertenmodus |
| Automatische Umschaltung | Engine wählt je Programm die erste stabile zugeordnete Quelle; bei Ausfall folgt die nächste Priorität bzw. Offline |
| Offline-Videobibliothek | MP4-Upload (max. 500 MiB / 5 Min.), Auswahl, Löschen, Vorschau |
| Standby bei Bedarf | Offline-Schleife läuft für Vorschau, Aufnahme oder aktiven Forward |
| Text-Overlay | Bis zu drei Zeilen, Position/Stil, einmalig eingerechnet |
| Browser-Overlay | Live-Chromium-Overlay (z. B. StreamElements), Demo-Seite eingebaut |
| Manuelle Aufnahme | Live / Source 1 / Source 2 → MP4, Download |
| Wiederholung | Einmaliges Abspielen einer Aufnahme als Source 1 mit Kennzeichnung |

### Streaming und Plattformen

| Feature | Beschreibung |
| --- | --- |
| Multistream | Twitch + YouTube + eigener Anbieter; bis zu zehn getrennte Ausgänge einschließlich zusätzlicher Konten im Expertenmodus |
| Zielauswahl speichern | Gilt beim nächsten Start; Konten bleiben verbunden |
| Streamschlüssel / OAuth | Twitch-Schlüssel oder OAuth; YouTube-Schlüssel oder Sendungsauswahl |
| Twitch-Metadaten | Titel und Kategorie setzen |
| Twitch-Neuverbindung | Optionales Intervall inkl. manueller „Jetzt neu verbinden“ |
| Eigene Ausgänge | Mehrere benannte öffentliche RTMP/RTMPS/SRT/RTSP-Ziele, getrennt start- und stoppbar |

### Chat

| Feature | Beschreibung |
| --- | --- |
| Gemeinsamer Live-Chat | Twitch, YouTube und Discord in einer Ansicht |
| Gezieltes Senden | An einen oder mehrere verbundene Chats |
| Chat-Widget | Nur-lesen-Link für OBS-Dock/Browserquelle, rotierbar |

### BUILD D

| Feature | Beschreibung |
| --- | --- |
| Szenen | Gespeicherte Quellenprogramme, Overlay-Video und Ziele; Anwendung nur bei gestopptem Ausgang |
| Live-Browser-Compositor | Browser-Overlay auf Offline-Video oder gewählter Live-Quelle |
| Rollen | Benutzer, einem Chat-Konto zugewiesene Nur-Chat-Moderatoren und Administratoren |
| Passkeys | WebAuthn-Anmeldung mit ES256/RS256 und zehn rotierbaren Einmal-Recovery-Codes |
| Discord-Chat | Verschlüsselt gespeicherter Bot-Adapter für Lesen und Senden in einem Textkanal |
| Mehrsprachigkeit | Zentrale EN/DE-Stringschicht und persönliche Sprachpräferenz; ältere Detailtexte werden schrittweise markiert |
| Twitch-Zeitplan | Automationsauftrag für Titel, optionale Kategorie und anschließenden Twitch-Start |

---

## Noch nicht umgesetzt (Ideen aus MediaMTX und UI)

Priorität ist eine grobe Einordnung für die Roadmap, keine Zusage.

### MediaMTX-Protokolle und Wiedergabe

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **RTMPS-/RTSPS-Ingest** | `rtmpEncryption` / `rtspEncryption` | Verschlüsselter Encoder-Eingang | mittel |
| **Media-over-QUIC (MoQ)** | `moq` | Moderne Transportoption | niedrig |
| **MPEG-TS / RTP Publish** | native Listener | Spezial-Encoder, Broadcast-Hardware | niedrig |
| **SRT auch als Lesen/Ausspielen** | SRT read | Externe Player/Decoder am Server | niedrig |
| **Protokollwahl pro Quelle im UI** | Path-Config | User wählt RTMP/SRT/WebRTC selbst | mittel |

### Aufnahme und Archiv (nativ MediaMTX)

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Persistente Clips aus Live-HLS/Aufnahme** | Playback-Server / `playback` | Gespeicherte kurze Ausschnitte; Segment-Ausschnitte und Download sind bereits vorhanden | mittel |
| **Aufnahmeplan / Zeitsteuerung** | Hooks + Scheduler im UI | Geplante Sessions, Nachtschichten | mittel |
| **Cloud-Export** | nach Record-Hook | S3/WebDAV nach Segmentende | niedrig |

### Quellen und Routing

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Source-on-demand** | `sourceOnDemand` | Ressourcen sparen, wenn niemand liest | niedrig |
| **Fallback-Kette konfigurierbar** | Path + Engine | Reihenfolge und Timeouts im UI | mittel |
| **runOnPublish / runOnReady Hooks** | `runOnPublish`, `runOnReady`, … | Discord-Webhook, eigene Skripte | mittel |
| **Always-available mit Datei** | `alwaysAvailableFile` | Echtes Standby-MP4 direkt in MediaMTX | mittel |

### Weiterleitung und Multistream

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Kick, Facebook, Trovo-Vorlagen** | Forward-URLs | Vorgefertigte Ingest-Profile | niedrig |
| **Bandbreiten-/Bitrate-Hinweis** | Metrics + UI | Warnung bei zu vielen Zielen | niedrig |
| **Proxy-Pfad zu anderem Server** | Path-Proxy | Kaskade / Edge-Server | niedrig |

### Sicherheit und Betrieb

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **JWT-/HTTP-Auth für MediaMTX** | `authMethod: jwt` / `http` | Anbindung an IdP; aktuell nur `internal` | mittel |
| **Prometheus-Metrics im UI** | `metrics: true` | Leser, Bitrate, Fehler pro Path | mittel |
| **Verschlüsselte Control API** | `apiEncryption` | API nur per HTTPS | mittel |
| **Dienst ohne root** | systemd + Capabilities | Härtere Isolation der UI | hoch |
| **Remote-MediaMTX** | API + getrennte Config | UI und Medienserver auf getrennten Hosts | mittel |
| **Docker-/Compose-Packaging** | – | Einfachere Labor-/Cloud-Setups | mittel |

---

## Abgrenzung: Was MediaMTX kann, StreamDesk bewusst nicht übernimmt

- **Anonyme globale Control API** – wird beim Attach abgelehnt.
- **HTTP/JWT-Auth umbauen** – Installer stellt nicht automatisch um; nur interne Auth wird unterstützt.
- **Fremde Paths löschen oder überschreiben** – Attach respektiert bestehende Medien.
- **YouTube-Sendungen erstellen/beenden** – nur Auswahl und Streamschlüssel, keine Studio-Automation.
- **Automatischer Neustart manueller MP4-Aufnahmen** – diese bleiben manuell und enden bei Quellabbruch. Explizit aktivierte native Path-Aufnahmen laufen bei erneut verfügbarer Quelle weiter.
- **WebRTC / MoQ in Standalone-Defaults** – zunächst aus (`webrtc: false`, `moq: false`); WebRTC lässt sich anschließend als Administrator im Expertenmodus aktivieren.

---

## Vorschlag nächste Schritte

1. Die Erweiterungen 1.1.0-rc.1 auf dem eigenen Testserver mit realem Encoder, HTTPS und WebRTC-Netzwerk prüfen.
2. Anschließend nach Bedarf MediaMTX-Playback-Server, weitere Quellen und zusätzliche Custom-Ziele ausbauen.

Feedback und Priorisierung: Issues oder Beiträge gemäß [CONTRIBUTING.md](CONTRIBUTING.md).
