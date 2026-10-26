# Drittanbieter

StreamDesk lädt bzw. verwendet diese separaten Komponenten:

| Komponente | Verwendung | Projekt/Lizenz |
| --- | --- | --- |
| MediaMTX | Medienserver, Protokolle, Weiterleitungen und HLS einschließlich des gelieferten HLS-Players | [Projekt](https://github.com/bluenviron/mediamtx), MIT |
| FFmpeg | Normalisierung, Aufnahmen und Overlays | [Projekt](https://ffmpeg.org/), Lizenz abhängig von der Debian-Buildkonfiguration; nicht im ZIP enthalten |
| Chromium / Playwright | Live-Browser-Overlays | Separat installiert; Chromium-Drittanbieterlizenzen und Playwright Apache-2.0 |
| Flask, Werkzeug, Gunicorn | Webanwendung und Webserver | Ihre jeweiligen BSD-/MIT-Lizenzen |
| cryptography | Verschlüsselung gespeicherter Geheimnisse | Apache-2.0 / BSD |
| PyYAML | MediaMTX-Konfiguration | MIT |
| websocket-client | Twitch-WebSocket-Client | Apache-2.0 |
| grpcio / protobuf | YouTube-Live-Chat-Streaming | Apache-2.0 / BSD |
| DejaVu fonts | Videobeschriftung | DejaVu-/Bitstream-Vera-Lizenzen des Debian-Pakets |

Python-Laufzeitabhängigkeiten stehen in `requirements.txt`. Die YouTube-Protokolldatei ist unter `NOTICE` und `LICENSE.youtube-sample.txt` erfasst. Die MediaMTX-Binaries sowie Debian-Systempakete werden nicht in diesem Quellcode-ZIP weiterverteilt. Sie behalten ihre eigenen Lizenztexte.
