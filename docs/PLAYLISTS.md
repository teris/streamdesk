# Playlists und zeitgesteuerte Ausspielung · 2.0.0-rc6

## Medien getrennt verwalten

Unter **Medien** kannst du benannte Ordner und Unterordner anlegen, MP4-Videos hochladen, umbenennen, verschieben, ansehen und löschen. Unter **Playlists** stehen die Liste und der Editor deiner Playlists. **Videos hinzufügen** bietet eine getrennte Mehrfachauswahl mit Ordnerfilter und Suche. Ordner sind eine Struktur der Medienbibliothek; beim Verschieben bleiben Videodateien und bestehende Verweise erhalten. Playlists dürfen Videos aus verschiedenen Ordnern enthalten, auch mehrfach. Die Pfeile im Editor ändern die Reihenfolge. **Playlist speichern** übernimmt die Änderungen. Ungespeicherte Entwürfe bleiben beim Wechsel zwischen Medien und Playlists erhalten.

Die Playlist-Verwaltung ist ohne Expertenmodus verfügbar. Pro Benutzer sind 100 Ordner, acht Ordnerebenen, 100 Playlists und 200 Videoeinträge je Playlist möglich. MP4-Importe über Web und FTPS haben keine feste Größen- oder Laufzeitgrenze. Das gilt auch für die einfache Offline-Videobibliothek. Die Hintergrundumwandlung erzeugt H.264/AAC mit 1080p30; Videos ohne Ton bekommen eine stille Audiospur. Maßgeblich ist der freie Speicher für Original und umgewandelte Datei einschließlich einer Betriebsreserve. Upload und Umwandlung haben keine feste Gesamtdauer. Für große Web-Uploads muss auch der [Reverse Proxy](PROXY.md) entsprechend eingerichtet sein.

Videos können umbenannt werden, ohne ihre IDs, Zuordnungen oder Wiedergabepositionen zu ändern. Beim Löschen werden aktuelle Playlist-Verweise erneut abgefragt. Nach ausdrücklicher Bestätigung wird das Video auch aus inaktiven Playlists entfernt. Dateien laufender Playlists und letzte Videos zugeordneter Playlists bleiben geschützt; der jeweilige Grund steht in der Oberfläche. Playlists mit Ausspielregeln oder Zeitplänen müssen zuerst dort entfernt werden. Ordner müssen vor dem Löschen leer sein. Das Löschen einer Playlist entfernt keine Videodateien.

## Ausspielung im Expertenmodus

Unter **Expertenmodus → Playlist-Ausspielung** wird die gemeinsame **Source-2-Regel** eingerichtet. Alle laufenden Ausgänge verwenden dieselbe Playlist. Ein einzelner Playlist-Encoder pro Benutzer erzeugt das gekennzeichnete H.264/AAC-Signal; Programme mit verschiedenen Live-Routings übernehmen es ohne erneute Video-Umwandlung.

**Source 1 und Source 2 bleiben feste Live-Eingänge.** Die virtuelle Playlist überschreibt keinen verbundenen Encoder. Gesunde Source-1-/Source-2-Signale pausieren die gemeinsame Playlist. Die normale Quellengesundheitsprüfung gilt weiter.

Die grafische Übersicht zeigt Zeitfenster als anklickbare Balken. Zwischen Woche und einzelnen Tagen wechseln, einen Balken zum Bearbeiten wählen und anschließend die Ausspielregel speichern. Für automatische Sendezeiten und gewählte Anbieter gibt es zusätzlich den normalen **Planer**. Migration aus früheren Ausgangsregeln und Bedienung: [Studio 2.0](STUDIO_2.md).

## Beispiel: erst Offline-Video, nach zehn Minuten Playlist A

1. Playlist A mit Videos anlegen.
2. Die Source-2-Regel öffnen und **Regel aktivieren** wählen.
3. Unter **Playlist nach einem Live-Ausfall** Playlist A auswählen.
4. Die Verzögerung auf **10 Minuten** setzen und speichern.

Nach dem Ausfall aller zugeordneten Live-Quellen läuft zunächst das bisher ausgewählte Offline-Video. Nach zehn Minuten startet Playlist A in Dauerschleife. Kommt eine Live-Quelle zurück, wird die Playlist pausiert. Beim nächsten längeren Ausfall läuft sie an ihrer gespeicherten Position weiter; die Verzögerung beginnt erneut. Bei einer Verzögerung von 0 startet die Playlist unmittelbar nach der Ausfallerkennung.

Die Position wird für das gemeinsame Source-2-Playlist-Programm gespeichert und regelmäßig sowie beim Unterbrechen gesichert. Bei einem unerwarteten Serverausfall kann die letzte kurze Strecke seit der Sicherung erneut abgespielt werden. Änderungen der Videoreihenfolge beginnen eine neue Playlist-Fassung bei Position 0. Namen und Ordner ändern die Wiedergabeposition nicht.

Ab rc5 wird ein Fortsetzpunkt in den letzten 250 Millisekunden einer Schleife auf den Anfang des nächsten Durchlaufs gelegt. Damit führen kleine Rundungsunterschiede zwischen gespeicherten Längen und tatsächlichen Video-/Audioframes nicht zu einem Einstieg hinter dem letzten abspielbaren Frame. Normale Fortsetzpositionen bleiben erhalten. „Playlist wird vorbereitet“ endet erst nach mehreren erzeugten Frames und einer positiven Ausgabezeit.

## Zeitfenster und Zeitzone

Ein Zeitfenster enthält eine Playlist, Von/Bis-Zeit und Wochentage. Standard ist **Europe/Berlin**, alternativ sind gültige IANA-Zeitzonen wie **UTC** möglich. Sommer-/Winterzeit richtet sich nach dieser Zone. Das Ende eines Fensters gehört zum folgenden Fenster; überlappende Fenster im selben Bereich werden abgelehnt.

| Zeitfenster | Playlist |
| --- | --- |
| 12:00–00:00 | B |
| 00:00–06:00 | A |
| 06:00–12:00 | C |

Ein Fenster kann über Mitternacht laufen. Die Wochentage beziehen sich auf den Beginn des Fensters. Gleiche Start-/Endzeiten bedeuten 24 Stunden. Bei der wiederholten Stunde der Zeitumstellung bleibt dieselbe Fensterkennung aktiv.

Ein aktives Zeitfenster startet seine Playlist ohne Fallback-Verzögerung. Live-Quellen haben auch während eines Zeitfensters Vorrang. Außerhalb des Fensters gilt die Fallback-Playlist der gewählten Regel mit ihrer Verzögerung; ist keine hinterlegt, bleibt das normale Offline-Video.

Alle Ausgänge verwenden ab 2.0 dieselbe Playlist über Source 2. Im **Planer** werden die Anbieter gewählt, die zu einem geplanten Stream automatisch verbinden sollen. Zusätzliche Live-Quellen und Konten werden weiterhin im Expertenmodus verwaltet.

## Streaming automatisch starten und stoppen

Ohne **Betroffene Streaming-Ausgänge automatisch starten** werden nur bereits laufende Ausgänge mit der gewählten Playlist versorgt. Mit dieser Option kann ein Zeitfenster seinen Ausgang automatisch starten. Die gemeinsame Ausspielregel berücksichtigt für Streaming ausgewählte Ziele. Der separate Planer besitzt seine eigene ausdrückliche Anbieterauswahl. Streamschlüssel und Quellenzuordnung müssen vorhanden sein.

Automatisch gestartete Ausgänge werden nach dem letzten Zeitfenster beendet, wenn kein anschließender Fallback und kein Live-Streamer übernimmt. Eine zurückgekehrte Live-Quelle hält den Ausgang während ihrer Sendung offen. Manuell gestartete Ausgänge werden durch das Ende eines Playlist-Fensters nicht beendet.

**Ein manueller Stopp hat Vorrang:** Im aktuellen Zeitfenster erfolgt kein automatischer Neustart. Ein späteres neues Fenster darf wieder automatisch starten. Ein manuell gestoppter verzögerter Fallback ohne Zeitfenster bleibt für diese Regel-Fassung gesperrt, bis die Regel bewusst geändert wird. Ein manueller Start übernimmt den Ausgang in die normale Benutzersteuerung.

Zeitpläne und automatischer Ausgangsstart benötigen zusätzlich die globale Freigabe **Automation & Export**. Die normale verzögerte Fallback-Playlist funktioniert unabhängig von dieser Automationsfreigabe.

## Dienstfreigaben, Vorschau und Aufnahmen

Administratoren können **Playlists** zentral sperren. Ordner, Medien, Regeln und Positionen bleiben erhalten. Laufende Playlist-Encoder werden beendet; manuell laufende Ausgänge behalten ihren normalen Offline-Fallback. Automatisch durch Playlists verwaltete Ausgänge werden beendet. Eine Sperre der Automation pausiert zeitgesteuerte Ausspielung und automatische Ausgangsstarts. Expertenmodus und direkte API-Aufrufe umgehen diese Sperren nicht.

Das Dashboard zeigt die aktuelle Playlist, das Video und die Position für das ausgewählte Programm. Die HLS-/WebRTC-Programmvorschau verwendet denselben Programmpfad wie der zugehörige Ausgang. Eine laufende Programmaufnahme behält ihren Prozess über Playlist-Schleifen und Live-Wechsel. Browser-Overlays des normalen Offline-/Live-Programms bleiben dort nutzbar; die Playlist-Ausspielung ergänzt die kontoweite Wiederholungskennzeichnung an der gewählten Bildecke.

Manuelle Browser-Overlays und die Änderung der Reihenfolge während einer Playlist können Programmwechsel auslösen; deshalb werden Videodateien mit aktiver Playlist-Nutzung beim Neuberechnen von Text-Overlays geschützt. Bei einer nicht verfügbaren Playlist greift nach dem fehlgeschlagenen Start der normale Offline-Fallback. Fremde MediaMTX-Pfade und fremde Auth-Einträge bleiben erhalten.

## Mehrfachupload und Fortschritt ab 1.1.8

Im Dateidialog können mehrere MP4-Dateien ausgewählt werden. Bis zu 50 Dateien werden in eine gemeinsame Browser-Warteschlange aufgenommen und nacheinander hochgeladen und umgewandelt. Weitere Dateien können ergänzt werden. Der Zielordner wird beim Hinzufügen zur Warteschlange für jede Datei festgehalten. Beide Bibliotheken zeigen dieselbe Warteschlange; ein Menüwechsel unterbricht sie nicht.

Jede Datei hat zwei Anzeigen: **Upload** mit übertragenen Bytes und Prozent sowie **Umwandlung** anhand der von FFmpeg verarbeiteten Medienzeit. Während der Dateiprüfung bleibt der Umwandlungsbalken unbestimmt. 100 Prozent Umwandlung erscheinen erst nach erfolgreichem Abschluss und Datenbankspeicherung. Fehler werden pro Datei angezeigt; danach wird die nächste Datei verarbeitet. Fehlgeschlagene Dateien können erneut versucht und noch wartende Dateien entfernt werden.

Noch nicht übertragene Dateien liegen im Browser. Für diese Dateien muss die Seite geöffnet bleiben. Eine bereits auf dem Server laufende Umwandlung wird nach einem Seitenneuladen wieder mit ihrem Status angezeigt. Bei einem Serverneustart erhalten unterbrochene Umwandlungen einen Fehlerstatus und müssen erneut hochgeladen werden.

**Umbenennen** bearbeitet den sichtbaren Namen und den Downloadnamen; gespeicherte Dateipfade bleiben stabil. **Löschen** zeigt vorhandene Playlist-Verwendungen an und verlangt eine Bestätigung. Die Oberfläche erklärt, warum ein Video aktuell nicht löschbar ist. Uploads anderer Dateien blockieren das Löschen unbenutzter Videos nicht.

FTPS-Upload, Massen-Auswahl, persönliche Texte und Twitch-Zeitplanübertragung: [Studio 2.0](STUDIO_2.md).
