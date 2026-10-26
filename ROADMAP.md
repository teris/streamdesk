---
overview: Verbindliche eigenständige Roadmap für MediaMTX- und Produktwellen ab 1.1.0; unabhängig von FEATURE.md.
todos:
  - id: playback
    content: MediaMTX Playback-Server und geschützte Segment-Wiedergabe
    status: completed
  - id: sources
    content: Source 3 und optionale öffentliche RTSP-Pull-Quelle mit Engine und UI
    status: completed
  - id: customs
    content: Mehrere benannte Custom-Forward-Ziele mit getrenntem Start/Stopp
    status: completed
  - id: docs-tests
    content: Version, Changelog, Dokumentation und Tests für 1.1.0-rc.4
    status: completed
isProject: false
---

# Verbindliche Roadmap: MediaMTX-Erweiterungen

Dieser vom Benutzer vorgegebene Plan ist die Roadmap. Er ist unabhängig von `FEATURE.md`; Abweichungen in der Feature-Liste ändern die Planung nicht. Der frühere Text bezog sich teils auf rc.2/rc.3. Da rc.3 inzwischen das eigene Experten-Untermenü und die SRT-/WebRTC-Korrekturen enthält, wird Welle 0 wie in ihrer Lieferüberschrift als **1.1.0-rc.4** umgesetzt. Danach folgt die Stabilisierung zu **1.1.0**. MediaMTX bleibt bei **v1.21.x**, aktuell v1.21.3.

## Verbindliche Präzisierung: 1.1.0-rc.6

Die später vom Benutzer bestätigte Vorgabe hat bei Abweichungen Vorrang vor der ursprünglichen Welle 0:

- Standard ausschließlich Source 1 und Source 2; diese Eingänge und Prioritäten sind unveränderlich. Standardausgänge Twitch, YouTube und ein eigener Anbieter.
- Zusätzliche Quellen und Ausgänge einschließlich weiterer Twitch-/YouTube-Konten nur ausdrücklich im Expertenmodus anlegen.
- Quellen und Verbindungsdaten sauber pro Quelle trennen; eigene Bereiche „Quellen & Routing“ und „Ausgänge & Konten“.
- Priorität je Ausgang ausschließlich zwischen seinen zugeordneten verfügbaren Quellen. Source 1 immer zuerst, Source 2 danach, zusätzliche Quellen ab Ebene 3. Unabhängige Programme je Quellenmenge; gemeinsame Mengen teilen sich eine Pipeline.
- Dashboard mit Programmwahl je Ausgang, Status und dauerhaft sichtbarem privaten Vorschau-Link.
- Sichtbarer eigener Passwortwechsel unter „Mein Konto“ für beide Kontotypen; Löschung deaktivierter Benutzer in der Administration mit separatem Medienarchiv.

Diese Präzisierung ist in rc.6 umgesetzt. Beispiele und Betriebsgrenzen stehen in `docs/EXPERT_MODE.md`. Die Wellen A–E bleiben Planung.

## Ursprüngliche Welle 0: 1.1.0-rc.4

1. **Playback:** Optionaler MediaMTX-Playback-Server; Aktivierung und globale Listener nur mit Expertenmodus plus Administratorrechten. Proxy mit angemeldeter Eigentümersitzung, keine öffentliche anonyme Archivfreigabe. Vorhandene Vorschau/Downloads bleiben erhalten. fMP4 wird nativ unterstützt; für MPEG-TS ist die Grenze der gepinnten MediaMTX-Version zu berücksichtigen.
2. **Quellen:** Source 3 im Tenant-Präfix mit RTMP-/SRT-Ingest-Hilfen. Optionale RTSP-Pull-Quelle mit Prüfung öffentlicher Ziele wie bei bestehenden Forwards. Auto-Priorität Source 1 → Source 2 → Source 3 → Pull → Offline sowie manuelle Auswahl im Expertenmodus.
3. **Custom-Ziele:** Mehrere benannte URLs, einzeln start-/stoppbar. Obergrenze fünf Custom-Ziele pro Benutzer, Bandbreitenhinweis im UI; Twitch und YouTube bleiben feste Plattform-Slots. Bestehende Custom-Ziele und Schlüssel werden migriert und erhalten.
4. **Release:** DB-Migration, idempotenter Pfadabgleich, Version/Changelog, Betriebs-/Konfigurationsdoku, Unit- und gezielte lokale Medientests. Ein Abgleich mit `FEATURE.md` ist optional.

Akzeptanz:

- Playback nur innerhalb der angemeldeten Eigentümersitzung; fremde Tenants sind gesperrt.
- Source 3 und Pull funktionieren in Auto- und manueller Wahl mit definiertem Offline-Fallback.
- Mindestens drei Custom-Ziele lassen sich speichern und getrennt steuern, ohne Twitch/YouTube zu verlieren.
- Attach erhält fremde MediaMTX-Pfade und vorhandene fremde Auth-Einträge/Berechtigungen; technische Aktionen bleiben im Expertenmodus.
- Kein ungefragter GitHub-Push. Commits nur bei Beauftragung, ohne Cursor-Co-Author.

Die nachfolgende **1.1.0-rc.5** stabilisiert Programmaufnahme und Vorschau: dauerhafter Programmpfad, Quellenwechsel ohne Aufnahmestopp und Programm-HLS/WebRTC auch ohne Streamingziel. Dies ändert die nachfolgenden Wellen nicht.

## Welle A: Betrieb und Sicherheit nach 1.1.0

| Thema | Basis | Priorität |
| --- | --- | --- |
| Dienst ohne root | systemd, Capabilities, getrennte Benutzer | hoch |
| Prometheus-Metrics im UI | Metrics-API: Leser, Bitrate, Fehler pro Pfad | mittel |
| Verschlüsselte Control API | apiEncryption und Zertifikate | mittel |
| RTMPS-/RTSPS-Ingest | rtmpEncryption / rtspEncryption | mittel |
| Remote-MediaMTX | API und Konfigurationszugriff auf getrennten Hosts | mittel |
| Docker-/Compose-Packaging | Labor-/Cloud-Setup | mittel |
| Bandbreitenhinweis bei vielen Forwards | Metrics + UI; über den Hinweis aus Welle 0 hinaus | niedrig |

## Welle B: Auth und Protokolle nach 1.1.0

| Thema | Basis | Priorität |
| --- | --- | --- |
| JWT-Authentifizierung | JWKS / IdP | mittel |
| HTTP-Authentifizierung | Externe Auth-URL pro Aktion | mittel |
| Allgemeine Protokollwahl pro Quelle | RTMP/SRT/WebRTC und Listener-Konfiguration | mittel |
| Media-over-QUIC | MoQ | niedrig |
| MPEG-TS / RTP Publish | Native Listener für Spezial-Encoder | niedrig |
| SRT lesen/ausspielen | Externe Player und Decoder | niedrig |

Auth-Wechsel nur über einen expliziten Installer-/Administratorweg mit Rollback-Hinweis. Attach repariert fremde Auth nicht automatisch.

## Welle C: Automation, Archiv und Routing nach 1.1.0

Voraussetzung: stabile native Aufnahme und Playback aus Welle 0.

| Thema | Basis | Priorität |
| --- | --- | --- |
| runOnPublish / runOnReady | Webhooks und Skripte | mittel |
| Aufnahmeplan / Zeitsteuerung | UI-Scheduler und ggf. Hooks | mittel |
| Cloud-Export | S3/WebDAV nach Segmentende | niedrig |
| Always-available mit Datei | alwaysAvailableFile | mittel |
| Source-on-demand | Ressourcen sparen ohne Leser | niedrig |
| Konfigurierbare Fallback-Kette | Reihenfolge und Timeouts | mittel |
| Path-Proxy zu anderem Server | Kaskade / Edge | niedrig |
| Kick-/Facebook-/Trovo-Vorlagen | Forward-Presets | niedrig |

Hooks nur mit Allowlist, Timeout und ohne Secrets in Env-Dumps.

## Welle D: Plattform und Oberfläche

| Thema | Priorität |
| --- | --- |
| Benachrichtigungen bei Offline, Speicher- und Forward-Fehlern | mittel |
| Szenen / Layouts: Quelle, Overlay und Ziele | mittel |
| Clip-Erzeugung aus Aufnahme/HLS | mittel |
| Rollen, etwa Moderator nur Chat | niedrig |
| Stream-Zeitplan für Titel/Start | niedrig |
| Discord-Chat | niedrig |
| 2FA / Passkeys | niedrig |
| Mehrsprachigkeit EN/DE | niedrig |

## Welle E: MediaMTX-Major

Nach stabilem 1.1.0 zuerst eine Kompatibilitätsmatrix für MediaMTX ≥ 2.x einschließlich API, YAML und Auth erstellen. Danach gezielte Migration oder Dual-Support ohne Datenverlust. **Kein stiller Major-Sprung in Patch-RCs.**

## Architektur und Abgrenzung

Encoder und Pull-Quelle speisen private MediaMTX-Pfade. Die Engine wählt das Programm; dieses geht an Twitch, YouTube und Custom-Ziele sowie an die optionale HLS-Zuschauerfreigabe. Native Segmente werden über den geschützten Playback-Proxy gelesen. StreamDesk steuert über die Control API.

Keine anonyme globale Control API, kein stiller JWT-/HTTP-Umbau, keine Löschung fremder Attach-Pfade, keine YouTube-Studio-Automation. Manuelle FFmpeg-MP4-Aufnahmen bleiben manuell; natives Recording folgt dem MediaMTX-Verhalten. MoQ bleibt standardmäßig aus, bis Welle B es ausdrücklich aktiviert.
