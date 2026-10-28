# Expertenmodus und Medienerweiterungen · 1.1.8

Den eigenen Menüpunkt **Expertenmodus** öffnen, den Modus aktivieren und **Modus übernehmen** wählen. Die Untermenüs „Protokolle & WebRTC“, „Quellen & Routing“, „Ausgänge & Konten“, „Native Aufnahme“, „Playback“, „Zuschauerfreigabe“, „Neuverbindung“, „Automation & Export“ und „Discord-Bot“ bündeln die technischen Einstellungen. Die normalen Ansichten behalten ihre grundlegenden Funktionen. Er gilt für die aktuelle Anmeldung. Eine weitere Anmeldung startet mit ausgeschaltetem Expertenmodus, auch beim selben Benutzer. Das Backend prüft technische Anfragen zusätzlich zur Sichtbarkeit in der Oberfläche. Ein Administratorkonto umgeht diese Prüfung nicht.

| Immer verfügbar | Nur im Expertenmodus |
| --- | --- |
| Dashboard, bisheriger Gesamtstart/-stopp, Plattformkonten und Streamschlüssel | Zusätzliche Quellen, Zielzuordnungen und Prioritäten verwalten |
| OBS-/SRT-Verbindungsdaten und HLS-Vorschau | Einzelne Weiterleitungen sofort starten/stoppen |
| Videos, Text-/Browser-Overlays, Chat und Widget | Verbindungsintervalle und manuelle Ziel-Neuverbindung |
| Manuelle MP4-Aufnahmen, Downloads und Wiederholungen | Native MediaMTX-Daueraufnahme konfigurieren |
| Vorhandene native Segmente herunterladen / fMP4 ansehen | Öffentliche Zuschauerfreigabe erstellen, erneuern oder widerrufen |
| Theme und mobile Bedienung | WebRTC-Kamera/-Vorschau, Playback eigener Segmente |
| Gespeicherte Streamingziele für den Gesamtstart auswählen | Weitere Twitch-/YouTube-Konten, eigene Anbieter und Pull-Adressen konfigurieren |
| Eingerichteten Discord-Chat lesen und verwenden | Discord-Bot verbinden und trennen; Anleitung siehe [Discord](DISCORD.md) |

Die normalen **Einstellungen** haben eigene Unterseiten für **Streaming-Auswahl**, **Twitch**, **YouTube**, **Eigener Anbieter** und **Darstellung & Sprache**. Twitch-/YouTube-Kontofreigaben, ihre Streamschlüssel und der feste eigene Anbieter bleiben ohne Expertenmodus verwaltbar.

Globale WebRTC- und Playback-Einstellungen benötigen **Administratorrechte und aktivierten Expertenmodus**. Benutzer können nur ihre eigenen Quellen, Ziele, Aufnahmen und Zuschauerfreigaben verwalten.

Das Ausschalten blendet technische Bedienelemente aus und sperrt weitere Änderungen. Es beendet keine laufenden Weiterleitungen oder nativen Aufnahmen und setzt gespeicherte Quellenwahl, Freigaben oder Zeitintervalle nicht zurück. Der Quellenbereich zeigt den wirksamen Modus auch ohne Expertenmodus an. WebRTC-Fenster beenden ihre Verbindung beim nächsten Moduscheck, spätestens nach ungefähr zehn Sekunden.

## Quellen und Routing ab rc.6

Standard sind **Source 1** (RTMP, Priorität 1) und **Source 2** (SRT, Priorität 2). Name, bevorzugtes Protokoll, Identität und Priorität dieser Eingänge sind fest. Es gibt keine automatisch angelegte Source 3 mehr. Die Standardausgänge sind Twitch, YouTube und ein eigener Anbieter, zunächst mit Source 1 → Source 2.

Unter **Expertenmodus → Quellen & Routing** weitere Quellen anlegen, anschließend die gewünschte Quelle im eigenen Auswahlbereich öffnen. Dort bei zusätzlichen Quellen Name, Verbindung und Ebene einstellen sowie die zugehörigen Ausgänge auswählen. Source 1/2 haben ausschließlich die Zielzuordnung, keine veränderbaren Quelleneinstellungen. Jede Quelle erscheint unter **Quellen** in einer eigenen Karte mit separater Vorschau und eigenen, auf Wunsch eingeblendeten Verbindungsdaten. Die vollständige SRT-Adresse gehört in OBS ins Serverfeld; Streamschlüssel leer lassen. Getrennte Felder für andere Apps sind pro Quelle zusätzlich aufklappbar.

**Die Priorität gilt je Ausgang und nur für dessen zugeordnete Quellen.** Source 1 gewinnt immer, wenn sie zugeordnet und verfügbar ist; danach Source 2. Zusätzliche Quellen folgen ab Ebene 3. Kleinere Zahlen haben Vorrang; bei gleicher Ebene entscheidet die Anlegereihenfolge. Andere Ausgänge senden gleichzeitig ihr eigenes Programm. Eine nicht zugeordnete Source 1 übernimmt keinen fremden Ausgang.

| Ausgang | Zugeordnete Quellen in Priorität |
| --- | --- |
| Twitch Standard, YouTube Standard | Source 1 → Source 2 |
| Eigener Anbieter A | Source 1 → Source 2 → Source 5 |
| Twitch Zweitkonto | Source 3 |
| Eigener Anbieter B | Source 3 → Source 4 |
| YouTube Zweitkonto | Source 5 |

Sind Source 1/2 offline, übernimmt Source 5 bei Anbieter A. Anbieter B bleibt unabhängig bei Source 3 bzw. Source 4. Fallen alle einem Ausgang zugeordneten Quellen aus, wird dort das gemeinsame ausgewählte Offline-Video verwendet; Vorschau und Programmaufnahme zählen ebenfalls als Verbraucher. Eine Quelle muss für einige Sekunden stabil liefern, bevor sie übernimmt.

Prioritäten zusätzlicher Quellen können während des Betriebs geändert werden; das Programm und dessen Aufnahme bleiben am selben Pfad. Für eine Änderung der Zielzuordnung oder Zieladresse den betroffenen Ausgang zunächst stoppen. Andere Ausgänge bleiben verbunden. Eine allein referenzierte Programmzuordnung mit laufender Aufnahme lässt sich erst nach Aufnahmeende entfernen. Quellen vor dem Entfernen aus ihren Zuordnungen lösen; vorhandene Aufnahmen bleiben erhalten.

## Ausgänge und weitere Konten

Unter **Expertenmodus → Ausgänge & Konten** weitere Twitch-/YouTube-Ausgänge mit dem Streamschlüssel des jeweiligen Kontos oder eigene Anbieter mit URL und Namen anlegen. Neue Ausgänge starten nicht automatisch und haben zunächst keine zugeordneten Quellen. Erst die Zuordnung unter „Quellen & Routing“ festlegen. Bis zu zehn Quellen und zehn Ausgänge sind möglich; gleiche Quellenmengen teilen sich einen Programmpfad. Unterschiedliche Programme benötigen zusätzliche Encoderleistung, jedes Streamingziel zusätzliche Upload-Bandbreite.

Start/Stopp wirkt sofort auf das jeweilige Ziel. Die Auswahl unter den normalen Einstellungen gilt beim nächsten Gesamtstart. Die bisherigen OAuth-/Chat-Verbindungen gehören weiterhin zu den Standardkonten; zusätzliche Konten sind zusätzliche Streamingziele. „Alle Streamschlüssel entfernen“ stoppt die Ausgänge und leert Zugangsdaten, erhält aber zusätzliche Ausgangsdefinitionen und ihre Zuordnungen. Zusätzliche Ausgänge lassen sich nur im Expertenmodus entfernen.

## Dashboard und Programmaufnahme

Im Dashboard unter **Programmvorschau** zwischen Standardprogramm und den angelegten Ausgängen umschalten. Quellenkette und tatsächliche aktuelle Quelle werden angezeigt. Der private HLS-Vorschau-Link ist immer sichtbar und kopierbar; eine Anmeldung ist erforderlich. Im Expertenmodus erscheint zusätzlich der passende WebRTC-Link mit Ton. Der vorhandene öffentliche Zuschauer-Link bleibt eine ausdrückliche Freigabe für das Standardprogramm.

Die Vorschauauswahl ändert weder Routing noch laufende Aufnahmen. Die gewünschte Aufnahmequelle separat unter „Aufnahmen“ wählen: Standardprogramm, ein zusätzliches Programm oder ein direkter Eingang. Programmaufnahmen laufen bei Quellenwechseln weiter. Bei Änderung einer Quellenmenge wird der Vorschau-Link im Dashboard aktualisiert; Prioritätsänderungen innerhalb derselben Menge behalten den Link.

## WebRTC einrichten

1. StreamDesk über HTTPS bereitstellen. Browser erlauben Kamera-/Mikrofonzugriff auf entfernte Webseiten nur über eine sichere Verbindung.
2. Als Administrator den Expertenmodus aktivieren. Unter **Expertenmodus → Protokolle & WebRTC → MediaMTX · WebRTC-Server** WebRTC einschalten und die vom Client erreichbaren DNS-Namen/IPs eintragen. Dies wirkt auf die gesamte MediaMTX-Instanz.
3. „WebRTC-Server aktivieren“ auswählen, bei Bedarf den vorgeschlagenen Ingest-Host übernehmen und ausdrücklich speichern. Der Status darüber zeigt Aktivierung und laufenden Server.
4. Den vorhandenen MediaMTX-WebRTC-Medienport erreichbar machen. Standardmäßig ist dies UDP 8189. Bei NAT muss der Port zur Instanz weitergeleitet werden. Signalisierung erfolgt über StreamDesk; der HTTP-Listener 8889 muss dafür nicht öffentlich geöffnet werden.
5. Unter **Expertenmodus → Protokolle & WebRTC** die Browser-Kamera auf Source 1/2 starten oder eine Vorschau öffnen. Kamera und Mikrofon werden erst nach Klick und Browserfreigabe verwendet. Ein bereits belegter Eingang wird nicht überschrieben.

Vorhandene Listener-, ICE-, STUN- und TURN-Einstellungen bleiben erhalten. Die Anwendung übernimmt die vom MediaMTX-OPTIONS-Endpunkt ausgegebenen ICE-Server für den Browser. Bei abweichendem lokalem Signalisierungsendpunkt kann `MEDIAMTX_WEBRTC` gesetzt werden; sonst wird er aus der YAML-Konfiguration abgeleitet. Zertifikate werden regulär geprüft.

Kamera-Publish verlangt H.264-Unterstützung im Browser, damit die bestehende RTMP-/Programm-Pipeline weiterarbeiten kann. Die Anwendung wählt H.264 für den Video-Sender und wandelt das Audio im Relay nach AAC, 48 kHz und Stereo. Die WHEP-Vorschau hängt von den Quellcodecs ab; H.264 mit B-Frames und AAC-Audio sind nicht allgemein WebRTC-kompatibel. HLS bleibt als Vorschau verfügbar. Beim Schließen oder Stoppen werden Peer-Verbindung, lokale Kamera/Mikrofon-Tracks und die MediaMTX-Sitzung beendet.

Die Signalisierung authentifiziert sich serverseitig mit dem persönlichen Medienkonto. Die Browserseite erhält keine Medienpasswörter und kann keine fremden Pfade auswählen. Sitzungen sind an Benutzer und Anmeldung gebunden. Bereinigung per DELETE bleibt nach Ausschalten des Expertenmodus möglich.

Referenz: [MediaMTX WebRTC und Netzwerkkonfiguration](https://mediamtx.org/docs/features/webrtc-specific-features), [MediaMTX v1.21.3-Konfiguration](https://github.com/bluenviron/mediamtx/blob/v1.21.3/mediamtx.yml).

## Native Aufnahmen

Unter **Expertenmodus → Native Aufnahme** für eine vorhandene Quelle oder ein eigenes Programm getrennt aktivieren. Formate: fMP4 oder MPEG-TS. Segmentdauer: 1/5/15 Minuten oder 1 Stunde. Automatische Aufbewahrung: 1/7/30 Tage. Die tatsächliche Segmentgrenze hängt auch von den Keyframes der Quelle ab.

Dies ist eine ausdrücklich aktivierte Daueraufnahme: Bei erneut verfügbarer Quelle und nach Serverneustart zeichnet MediaMTX weiter auf. Manuelle MP4-Aufnahmen bleiben davon unabhängig und werden weiterhin nicht automatisch neu gestartet. Für eine Wiederholung wird der separate Replay-Pfad benutzt; die native Einstellung „Source 1“ bezeichnet den tatsächlichen Encodereingang.

Der Installer erzeugt `STREAMDESK_NATIVE_ROOT`, standardmäßig `/var/lib/streamdesk-native`, mit dem Besitzer des MediaMTX-Dienstes und Modus 0750. Darunter liegen getrennte Benutzer-/Quellverzeichnisse. **Bei bestehender Installation zuerst den Installer mit `--mode update` ausführen.** Die private StreamDesk-Datenablage behält Modus 0700. Ein bestehender MediaMTX-systemd-Dienst mit eingeschränkten Schreibpfaden benötigt zusätzlich Schreibzugriff auf dieses Aufnahmeverzeichnis; der Installer ändert fremde Unit-Dateien nicht.

Zum Aktivieren müssen mindestens 500 MiB frei sein. Bei weniger als 350 MiB deaktiviert die laufende StreamDesk-Engine native Aufnahmen innerhalb ihres Prüfintervalls von zehn Sekunden; erneutes Aktivieren erfolgt manuell. Die Aufbewahrungsfrist löscht MediaMTX selbst. Bei gestoppter StreamDesk-Engine gibt es keine zusätzliche Speicherüberwachung durch die UI.

Die Segmentbibliothek zeigt die neuesten 200 Dateien, lädt fMP4 auf Wunsch direkt und bietet Downloads beider Formate. Das jüngste Segment kann noch geschrieben werden. Es gibt keinen öffentlichen Archivzugriff. Die zeitbasierte Wiedergabe ergänzt diese Bibliothek im eigenen Playback-Untermenü.

## Öffentliche Zuschauerfreigabe

Unter **Expertenmodus → Zuschauerfreigabe** ausdrücklich einen Link erstellen. Der Link ist ein persönliches, zufälliges Zugriffstoken: Jeder mit dem vollständigen Link kann das aktuelle Programm ansehen. Es werden ausschließlich HLS-Dateien des eigenen Live-Pfades vermittelt; Eingänge, Archiv und APIs bleiben privat. Es entstehen keine anonymen globalen MediaMTX-Berechtigungen.

„Link erstellen / erneuern“ macht den vorherigen Link ungültig. „Freigabe widerrufen“ sperrt Seite, Playlist und weitere Segmentabrufe; bereits im Browser gepufferte Videosekunden lassen sich nicht zurückholen. Deaktivierte Benutzer besitzen keine gültige Zuschauerfreigabe. Ein aktiver Zuschauerabruf zählt als Programmleser. Fehlen Live-Quellen, kann dadurch auch ohne externes Streamingziel das ausgewählte Offline-Video laufen.

Sicherung und Deinstallation: Den separaten nativen Aufnahmebereich zusätzlich zu `STREAMDESK_DATA` sichern. Eine Deinstallation bewahrt native Segmente; sie liegen außerhalb der bisherigen Datenablage.

## Geschütztes Playback

Ein Administrator aktiviert den globalen Server unter **Expertenmodus → Playback**. Danach können angemeldete Benutzer im Expertenmodus ausschließlich ihre eigenen Aufnahmesegmente nach Quelle und optionalem Startzeitpunkt laden. Einen Eintrag wählen oder den Start und die Dauer des Ausschnitts angeben. Video und Download verwenden denselben geschützten StreamDesk-Proxy; persönliche MediaMTX-Zugangsdaten verlassen den Server dabei nicht. Öffentliche Zuschauer-Links berechtigen ausschließlich zum Live-HLS-Programm.

MediaMTX v1.21.3 unterstützt Playback direkt für fMP4. MPEG-TS wird durch StreamDesk aus eigenen nativen Dateien mit FFprobe untersucht und mit FFmpeg in fragmentiertes MP4 umgepackt, ohne Neucodierung. Das setzt browserfähige Codecs voraus, üblicherweise H.264/AAC. Der MPEG-TS-Abruf endet an Aufnahmelücken; Startpunkte hängen von Keyframes ab. Maximal zwei gleichzeitige MPEG-TS-Konvertierungen und eine Stunde pro Abruf begrenzen die Verarbeitung. Die Liste zeigt höchstens die neuesten 200 Zeitbereiche; bei MPEG-TS die neuesten 200 Dateien je Quelle. Dateidownloads der Segmentbibliothek bleiben unabhängig verfügbar.

Das aktuell am Pfad konfigurierte Aufnahmeformat bestimmt den Playback-Zugriff. Nach einem Wechsel fMP4 ↔ MPEG-TS bleiben ältere Dateien über die Segmentbibliothek verfügbar. Laufende, noch nicht abgeschlossene Segmente können unvollständig sein. Beim Verlassen des Playback-Untermenüs oder Ausschalten des Expertenmodus beendet die Oberfläche die Wiedergabe; bereits heruntergeladene bzw. gepufferte Daten bleiben vorhanden.

Referenzen: [MediaMTX Playback](https://mediamtx.org/docs/features/playback), [Formatgrenze in v1.21.3](https://github.com/bluenviron/mediamtx/blob/v1.21.3/internal/playback/on_get.go#L100).

## Programmaufnahme und Vorschau ab rc.5

Das Programm ist unabhängig von Twitch/YouTube/Custom-Zielen verfügbar. Die Dashboard-Vorschau und **Protokolle & WebRTC → Programm ansehen** benötigen kein gestartetes Streamingziel. Beim Verlust einer Quelle übernimmt die nächste zulässige Quelle bzw. das Offline-Video; für die Umschaltzeit bleibt ein Standby-Signal verfügbar.

Eine manuell gestartete Aufnahme mit Quelle **Programm** bleibt dabei derselbe Aufnahmeprozess und dieselbe MP4-Datei. Ihre Zeitstempel folgen der lokalen Aufnahmezeit, damit wechselnde Publisher-Zeitbasen keine Laufzeitabschnitte verschlucken. Sie endet durch manuellen Stopp, zu wenig Speicher, Deaktivierung des Benutzers oder einen tatsächlichen Fehler des Aufnahme-/Mediendiensts. Direkte Aufnahmen eines einzelnen Eingangs dürfen beim Ende genau dieses Eingangs weiterhin abschließen. Ein Server-/Dienstneustart setzt eine manuelle Aufnahme weiterhin nicht automatisch fort.

Zur Stabilisierung des Programms werden Video auf H.264 Baseline ohne B-Frames, 1920×1080/30 fps und Audio auf AAC, 48 kHz, Stereo normalisiert. Dafür läuft ein Videoencoder pro aktivem Programm und es wird zusätzliche CPU benötigt. Native Aufnahmen der einzelnen Eingänge behalten ihr Quellenformat; native Programmaufnahmen folgen dem normalisierten Programm einschließlich Standby. Dies verhindert Unterbrechungen durch unterschiedliche Auflösungen, B-Frames und Audioformate der Quellen.

Nur für die WebRTC-Programmvorschau wird das AAC-Audio zusätzlich nach Opus gewandelt; das H.264-Bild wird kopiert. Der private Pfad `<präfix>/webrtc-program` enthält keine Aufnahme und keine Weiterleitung. Der Prozess wird beim Öffnen der Experten-Programmvorschau gestartet, zwischen mehreren Fenstern desselben Benutzers geteilt und nach 20 Sekunden ohne Leser beendet. Er wird bei Benutzerdeaktivierung bzw. beim Beenden der Engine aufgeräumt. Direkte WebRTC-Vorschauen von Source 1/2 bleiben vom Quellcodec abhängig.

## Eigenes Konto und Benutzer löschen

**Mein Konto** ist für jeden angemeldeten Benutzer direkt im Menü erreichbar, unabhängig vom Expertenmodus und der Administratorrolle. Das bisherige Passwort und ein neues Passwort mit mindestens zwölf Zeichen eingeben. Die aktuelle Sitzung bleibt angemeldet; andere bestehende Anmeldungen werden ungültig.

Administratoren können unter **Administration** einen anderen Benutzer zunächst deaktivieren und anschließend **Benutzer löschen** wählen. Zum Bestätigen den Benutzernamen eingeben. Aktive Konten und das eigene Administratorkonto sind geschützt. Laufende Uploads/Verarbeitung bzw. Aufnahmeabschlüsse müssen beendet sein. Kontodaten und persönliche MediaMTX-Pfade/Zugänge werden entfernt; Mediendateien werden separat archiviert und nicht endgültig vernichtet. Archivdetails stehen in der Betriebsanleitung.

## Playlists ab 1.1.7

Die normale Ansicht **Playlists** verwaltet Medien, Ordner und Reihenfolge. **Expertenmodus → Playlist-Ausspielung** ergänzt Regeln je Quelle/Ausgang, Fallback-Verzögerung, Wochentage und Zeitzonen. Echte Live-Quellen haben Vorrang; unterbrochene Playlists behalten ihre Position. Details und Beispiele: [Playlists](PLAYLISTS.md).
