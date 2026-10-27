# MediaMTX-Kompatibilität

Stand: 27. Oktober 2026

StreamDesk wählt die MediaMTX-Major-Version beim Installieren explizit mit
`--mediamtx-major`. Unbekannte Profile werden abgewiesen, bevor Dateien oder
Dienste verändert werden.

| Bereich | MediaMTX 1.21.3–1.21.x | MediaMTX 2.x |
|---|---|---|
| Status | unterstützt und getestet | nicht freigegeben |
| Control API | `/v3`, Global- und Path-Endpunkte | kein veröffentlichter Vertrag |
| YAML | Schema 1.21 | kein veröffentlichtes Schema |
| Auth | internal; HTTP/JWT bis zur vollständigen Anbindung gesperrt | kein StreamDesk-Profil |
| Forwarding | native Forward-Ziele | nicht verifizierbar |
| Playback/Recording | v1.21-Vertrag | nicht verifizierbar |
| Listener | RTSP(S), RTMP(S), SRT, WebRTC, MoQ | nicht verifizierbar |

Für MediaMTX 2.x enthält StreamDesk noch kein geprüftes API-/YAML-Profil.
Der Installer lehnt `--mediamtx-major 2` deshalb vor Änderungen ab.
Die hier ausgeführten Medientests verwenden konkret 1.21.3; weitere
1.21-Patches werden vom Profil akzeptiert, wurden dabei nicht einzeln getestet.

## Migrationsablauf

1. `--dry-run --mediamtx-major <Ziel>` prüft Zielprofil, lokale YAML und
   Namensraum, ohne Änderungen vorzunehmen.
2. Eine reale Aktualisierung erstellt zuerst die vorhandene
   Konfigurations-, Anwendungs- und Datenbanksicherung.
3. MediaMTX-Konfiguration und Laufzeit werden validiert; danach folgen
   Control-API-, eigener Pfad- und UI-Healthcheck.
4. Jeder Fehler stellt Konfiguration, Anwendung, Datenbank und Units wieder
   her.

Ein 2.x-Profil darf erst ergänzt werden, wenn eine konkrete stabile Version
vorliegt. Dann werden echte API-/YAML-Fixtures, Auth-, Forwarding-, Playback-,
Recording- und Listener-Smokes erforderlich. Erst nach deren Erfolg wird der
Fail-closed-Guard aufgehoben.
