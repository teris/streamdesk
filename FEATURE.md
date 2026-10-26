# Feature-Übersicht – MediaMTX - StreamDesk

Stand: Version 1.0.0 · Bezug: MediaMTX **v1.21.x**  
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
| Installer | `attach` (bestehendes MediaMTX), `standalone` (MediaMTX mitliefern), `update` |

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
| Zwei Live-Quellen | OBS (Vorrang) und Handy (Fallback) |
| Automatische Umschaltung | Engine wählt stabile Quelle; bei Ausfall Fallback bzw. Offline |
| Offline-Videobibliothek | MP4-Upload (max. 500 MiB / 5 Min.), Auswahl, Löschen, Vorschau |
| Standby erst mit Ausgang | Offline-Schleife startet erst bei aktivem Forward |
| Text-Overlay | Bis zu drei Zeilen, Position/Stil, einmalig eingerechnet |
| Browser-Overlay | Live-Chromium-Overlay (z. B. StreamElements), Demo-Seite eingebaut |
| Manuelle Aufnahme | Live / Source 1 / Source 2 → MP4, Download |
| Wiederholung | Einmaliges Abspielen einer Aufnahme als Source 1 mit Kennzeichnung |

### Streaming und Plattformen

| Feature | Beschreibung |
| --- | --- |
| Multistream | Twitch + YouTube + Custom gleichzeitig möglich |
| Zielauswahl speichern | Gilt beim nächsten Start; Konten bleiben verbunden |
| Streamschlüssel / OAuth | Twitch-Schlüssel oder OAuth; YouTube-Schlüssel oder Sendungsauswahl |
| Twitch-Metadaten | Titel und Kategorie setzen |
| Twitch-Neuverbindung | Optionales Intervall inkl. manueller „Jetzt neu verbinden“ |
| Custom-Ausgang | Beliebige öffentliche RTMP/RTMPS/SRT/RTSP-Adresse |

### Chat

| Feature | Beschreibung |
| --- | --- |
| Gemeinsamer Live-Chat | Twitch und YouTube in einer Ansicht |
| Gezieltes Senden | Nur Twitch, nur YouTube oder beide |
| Chat-Widget | Nur-lesen-Link für OBS-Dock/Browserquelle, rotierbar |

---

## Noch nicht umgesetzt (Ideen aus MediaMTX und UI)

Priorität ist eine grobe Einordnung für die Roadmap, keine Zusage.

### MediaMTX-Protokolle und Wiedergabe

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **WebRTC Publish/Play** | `webrtc: true`, WHEP/WHIP | Browser-Kamera/Handy ohne OBS; niedrige Latenz-Vorschau | hoch |
| **Öffentliche HLS-/Player-Seite** | HLS + Playback-Rechte | Zuschauer-Link ohne Twitch/YouTube | hoch |
| **RTMPS-/RTSPS-Ingest** | `rtmpEncryption` / `rtspEncryption` | Verschlüsselter Encoder-Eingang | mittel |
| **Media-over-QUIC (MoQ)** | `moq` | Moderne Transportoption | niedrig |
| **MPEG-TS / RTP Publish** | native Listener | Spezial-Encoder, Broadcast-Hardware | niedrig |
| **SRT auch als Lesen/Ausspielen** | SRT read | Externe Player/Decoder am Server | niedrig |
| **Protokollwahl pro Quelle im UI** | Path-Config | User wählt RTMP/SRT/WebRTC selbst | mittel |

### Aufnahme und Archiv (nativ MediaMTX)

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Path-Recording (fMP4/MPEG-TS)** | `record`, `recordPath`, Segmentierung | Daueraufnahme ohne ffmpeg-Relay-Aufnahme | hoch |
| **Playback aufgezeichneter Segmente** | Playback-Server / `playback` | Zeitversetzte Wiedergabe, Clips aus Segmenten | mittel |
| **Aufnahmeplan / Zeitsteuerung** | Hooks + Scheduler im UI | Geplante Sessions, Nachtschichten | mittel |
| **Cloud-Export** | nach Record-Hook | S3/WebDAV nach Segmentende | niedrig |

### Quellen und Routing

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Mehr als zwei Live-Quellen** | weitere Paths | Kamera 3, Discord-Capture, … | mittel |
| **Manuelle Quellenwahl** | Engine statt Auto | Regisseur wählt fest Source 1/2/Offline | hoch |
| **Externe Pull-Quellen** | `source: rtsp://…` / `rpiCamera` | IP-Kameras, Raspberry Pi Cam | mittel |
| **Source-on-demand** | `sourceOnDemand` | Ressourcen sparen, wenn niemand liest | niedrig |
| **Fallback-Kette konfigurierbar** | Path + Engine | Reihenfolge und Timeouts im UI | mittel |
| **runOnPublish / runOnReady Hooks** | `runOnPublish`, `runOnReady`, … | Discord-Webhook, eigene Skripte | mittel |
| **Always-available mit Datei** | `alwaysAvailableFile` | Echtes Standby-MP4 direkt in MediaMTX | mittel |

### Weiterleitung und Multistream

| Idee | MediaMTX-Basis | Nutzen | Priorität |
| --- | --- | --- | --- |
| **Unbegrenzt viele Custom-Ziele** | mehrere `forward`-Einträge | Mehr als Twitch/YouTube/ein Custom | mittel |
| **Kick, Facebook, Trovo-Vorlagen** | Forward-URLs | Vorgefertigte Ingest-Profile | niedrig |
| **Per-Ziel Start/Stopp** | Path-Patches | Nur YouTube stoppen, Twitch läuft weiter | hoch |
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

### UI und Plattform-Erweiterungen

| Idee | Beschreibung | Priorität |
| --- | --- | --- |
| **Szenen / Layouts** | Gespeicherte Kombinationen Quelle + Overlay + Ziele | mittel |
| **Stream-Zeitplan** | Start/Stopp und Twitch-Titel nach Uhrzeit | niedrig |
| **Benachrichtigungen** | Webhook/E-Mail bei Offline, Speicher voll, Forward-Fehler | mittel |
| **2FA / Passkeys** | Zusätzlicher Login-Schutz | niedrig |
| **Rollen** | Moderator nur Chat, kein Stream-Start | niedrig |
| **Clip-Erzeugung** | Kurzer Ausschnitt aus laufender Aufnahme/HLS | mittel |
| **Mehrsprachigkeit** | EN/DE umschaltbar | niedrig |
| **Dark/Light Theme** | Darstellungswahl | niedrig |
| **Mobile-optimierte Regie** | Touch-UI für Start/Stopp und Quellen | mittel |
| **Discord-Chat** | Weitere Chat-Quelle neben Twitch/YouTube | niedrig |

---

## Abgrenzung: Was MediaMTX kann, StreamDesk bewusst nicht übernimmt

- **Anonyme globale Control API** – wird beim Attach abgelehnt.
- **HTTP/JWT-Auth umbauen** – Installer stellt nicht automatisch um; nur interne Auth wird unterstützt.
- **Fremde Paths löschen oder überschreiben** – Attach respektiert bestehende Medien.
- **YouTube-Sendungen erstellen/beenden** – nur Auswahl und Streamschlüssel, keine Studio-Automation.
- **Automatischer Aufnahme-Neustart** – Aufnahmen sind manuell und enden bei Quellabbruch.
- **WebRTC / MoQ** – in Standalone-Defaults bewusst aus (`webrtc: false`, `moq: false`).

---

## Vorschlag nächste Schritte

1. **Manuelle Quellenwahl** und **per-Ziel Start/Stopp** – großer Regie-Nutzen ohne neue MediaMTX-Version.  
2. **WebRTC-Vorschau oder WHIP-Publish** – nutzt vorhandenes MediaMTX-Feature, senkt Einstiegshürde.  
3. **Natives Path-Recording** – weniger ffmpeg-Last, Segmente und Playback aus MediaMTX.  
4. **Öffentliche Zuschauer-HLS-Seite** – optionaler Direct-to-Fan-Kanal neben Twitch/YouTube.

Feedback und Priorisierung: Issues oder Beiträge gemäß [CONTRIBUTING.md](CONTRIBUTING.md).
