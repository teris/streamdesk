# Playlists und zeitgesteuerte Ausspielung · 1.1.8

## Medien getrennt verwalten

Unter **Playlists** kannst du benannte Ordner und Unterordner anlegen, MP4-Videos hochladen und eigene Playlists zusammenstellen. Ordner sind eine Struktur der Medienbibliothek; beim Verschieben bleiben Videodateien und bestehende Verweise erhalten. Playlists dürfen Videos aus verschiedenen Ordnern enthalten, auch mehrfach. Die Pfeile im Editor ändern die Reihenfolge. **Playlist speichern** übernimmt die Änderungen.

Die Playlist-Verwaltung ist ohne Expertenmodus verfügbar. Pro Benutzer sind 100 Ordner, acht Ordnerebenen, 100 Playlists und 200 Videoeinträge je Playlist möglich. Playlist-Uploads erlauben 500 MB und 120 Minuten je MP4-Datei. Die Hintergrundumwandlung erzeugt H.264/AAC mit 1080p30; Videos ohne Ton bekommen eine stille Audiospur. Für die größere umgewandelte Datei muss genügend Speicher frei sein. Die bisherige einfache Offline-Video-Auswahl behält ihr Fünf-Minuten-Limit.

Videos können umbenannt werden, ohne ihre IDs, Zuordnungen oder Wiedergabepositionen zu ändern. Beim Löschen werden aktuelle Playlist-Verweise erneut abgefragt. Nach ausdrücklicher Bestätigung wird das Video auch aus inaktiven Playlists entfernt. Dateien laufender Playlists und letzte Videos zugeordneter Playlists bleiben geschützt; der jeweilige Grund steht in der Oberfläche. Playlists mit Ausspielregeln oder Zeitplänen müssen zuerst dort entfernt werden. Ordner müssen vor dem Löschen leer sein. Das Löschen einer Playlist entfernt keine Videodateien.

## Ausspielung im Expertenmodus

Unter **Expertenmodus → Playlist-Ausspielung** wird eine Regel für einen Bereich eingerichtet:

- **Allgemein:** Fallback für Programme ohne speziellere Regel.
- **Hinter Source 2 oder einer zusätzlichen Quelle:** gilt für Programme, denen dieser Eingang zugeordnet ist.
- **Ausgang:** eigene Regel für Twitch, YouTube oder einen weiteren eingerichteten Ausgang. So können zwei Ausgänge gleichzeitig verschiedene Playlists senden.

Eine aktive Ausgangsregel hat Vorrang vor Quellenregeln; Quellenregeln folgen der bestehenden Quellenpriorität. Danach gilt die allgemeine Regel. Eine aktive Regel ohne passende Zeitfenster und ohne Fallback-Playlist verwendet das normale Offline-Video. Eine deaktivierte Regel lässt die übergeordnete Regel wieder zu.

**Source 1 und Source 2 bleiben feste Live-Eingänge.** Die Playlist wird als virtuelle Ausspielung hinter den echten Eingängen verarbeitet. Es wird kein Encoder auf dem Source-2-Pfad ersetzt. Alle verfügbaren, diesem Programm zugeordneten Live-Quellen haben Vorrang vor einer Playlist. Die bestehende Prüfung auf Quellengesundheit gilt weiter; eine unterbrochene oder nicht mehr sendende Verbindung muss zunächst als ausgefallen erkannt werden.

Beim erstmaligen Anlegen einer eigenen Ausgangsregel muss dieser Ausgang gestoppt sein, weil er eine eigene Programmidentität bekommt. Anschließende Regel- und Zeitplanänderungen behalten diese Identität. Die umschaltbare Dashboard-Vorschau und ihr privater Link zeigen auch diese Programme.

## Beispiel: erst Offline-Video, nach zehn Minuten Playlist A

1. Playlist A mit Videos anlegen.
2. Den gewünschten Bereich öffnen und **Regel aktivieren** wählen.
3. Unter **Playlist nach einem Live-Ausfall** Playlist A auswählen.
4. Die Verzögerung auf **10 Minuten** setzen und speichern.

Nach dem Ausfall aller zugeordneten Live-Quellen läuft zunächst das bisher ausgewählte Offline-Video. Nach zehn Minuten startet Playlist A in Dauerschleife. Kommt eine Live-Quelle zurück, wird die Playlist pausiert. Beim nächsten längeren Ausfall läuft sie an ihrer gespeicherten Position weiter; die Verzögerung beginnt erneut. Bei einer Verzögerung von 0 startet die Playlist unmittelbar nach der Ausfallerkennung.

Die Position wird pro Programm gespeichert und regelmäßig sowie beim Unterbrechen gesichert. Bei einem unerwarteten Serverausfall kann die letzte kurze Strecke seit der Sicherung erneut abgespielt werden. Änderungen der Videoreihenfolge beginnen eine neue Playlist-Fassung bei Position 0. Namen und Ordner ändern die Wiedergabeposition nicht.

## Zeitfenster und Zeitzone

Ein Zeitfenster enthält eine Playlist, Von/Bis-Zeit und Wochentage. Standard ist **Europe/Berlin**, alternativ sind gültige IANA-Zeitzonen wie **UTC** möglich. Sommer-/Winterzeit richtet sich nach dieser Zone. Das Ende eines Fensters gehört zum folgenden Fenster; überlappende Fenster im selben Bereich werden abgelehnt.

| Zeitfenster | Playlist |
| --- | --- |
| 12:00–00:00 | B |
| 00:00–06:00 | A |
| 06:00–12:00 | C |

Ein Fenster kann über Mitternacht laufen. Die Wochentage beziehen sich auf den Beginn des Fensters. Gleiche Start-/Endzeiten bedeuten 24 Stunden. Bei der wiederholten Stunde der Zeitumstellung bleibt dieselbe Fensterkennung aktiv.

Ein aktives Zeitfenster startet seine Playlist ohne Fallback-Verzögerung. Live-Quellen haben auch während eines Zeitfensters Vorrang. Außerhalb des Fensters gilt die Fallback-Playlist der gewählten Regel mit ihrer Verzögerung; ist keine hinterlegt, bleibt das normale Offline-Video.

Für **Twitch: Playlist A von 13–16 Uhr** und **YouTube: Playlist B von 13–16 Uhr** werden zwei Ausgangsregeln mit denselben Zeiten und unterschiedlichen Playlists angelegt. Zusätzliche Quellen und Ausgänge werden wie bisher zuerst im Expertenmodus angelegt und zugeordnet.

## Streaming automatisch starten und stoppen

Ohne **Betroffene Streaming-Ausgänge automatisch starten** werden nur bereits laufende Ausgänge mit der gewählten Playlist versorgt. Mit dieser Option kann ein Zeitfenster seinen Ausgang automatisch starten. Allgemeine und Quellenregeln berücksichtigen dabei nur für Streaming ausgewählte Ziele; eine Ausgangsregel ausschließlich ihren eigenen Ausgang. Streamschlüssel und Quellenzuordnung müssen vorhanden sein.

Automatisch gestartete Ausgänge werden nach dem letzten Zeitfenster beendet, wenn kein anschließender Fallback und kein Live-Streamer übernimmt. Eine zurückgekehrte Live-Quelle hält den Ausgang während ihrer Sendung offen. Manuell gestartete Ausgänge werden durch das Ende eines Playlist-Fensters nicht beendet.

**Ein manueller Stopp hat Vorrang:** Im aktuellen Zeitfenster erfolgt kein automatischer Neustart. Ein späteres neues Fenster darf wieder automatisch starten. Ein manuell gestoppter verzögerter Fallback ohne Zeitfenster bleibt für diese Regel-Fassung gesperrt, bis die Regel bewusst geändert wird. Ein manueller Start übernimmt den Ausgang in die normale Benutzersteuerung.

Zeitpläne und automatischer Ausgangsstart benötigen zusätzlich die globale Freigabe **Automation & Export**. Die normale verzögerte Fallback-Playlist funktioniert unabhängig von dieser Automationsfreigabe.

## Dienstfreigaben, Vorschau und Aufnahmen

Administratoren können **Playlists** zentral sperren. Ordner, Medien, Regeln und Positionen bleiben erhalten. Laufende Playlist-Encoder werden beendet; manuell laufende Ausgänge behalten ihren normalen Offline-Fallback. Automatisch durch Playlists verwaltete Ausgänge werden beendet. Eine Sperre der Automation pausiert zeitgesteuerte Ausspielung und automatische Ausgangsstarts. Expertenmodus und direkte API-Aufrufe umgehen diese Sperren nicht.

Das Dashboard zeigt die aktuelle Playlist, das Video und die Position für das ausgewählte Programm. Die HLS-/WebRTC-Programmvorschau verwendet denselben Programmpfad wie der zugehörige Ausgang. Eine laufende Programmaufnahme behält ihren Prozess über Playlist-Schleifen und Live-Wechsel. Browser-Overlays des normalen Offline-/Live-Programms bleiben dort nutzbar; die Playlist-Ausspielung verwendet die in den Videos bereits enthaltenen Bilder bzw. Text-Overlays.

Manuelle Browser-Overlays und die Änderung der Reihenfolge während einer Playlist können Programmwechsel auslösen; deshalb werden Videodateien mit aktiver Playlist-Nutzung beim Neuberechnen von Text-Overlays geschützt. Bei einer nicht verfügbaren Playlist greift nach dem fehlgeschlagenen Start der normale Offline-Fallback. Fremde MediaMTX-Pfade und fremde Auth-Einträge bleiben erhalten.

## Mehrfachupload und Fortschritt ab 1.1.8

Im Dateidialog können mehrere MP4-Dateien ausgewählt werden. Bis zu 50 Dateien werden in eine gemeinsame Browser-Warteschlange aufgenommen und nacheinander hochgeladen und umgewandelt. Weitere Dateien können ergänzt werden. Der Zielordner wird beim Hinzufügen zur Warteschlange für jede Datei festgehalten. Beide Bibliotheken zeigen dieselbe Warteschlange; ein Menüwechsel unterbricht sie nicht.

Jede Datei hat zwei Anzeigen: **Upload** mit übertragenen Bytes und Prozent sowie **Umwandlung** anhand der von FFmpeg verarbeiteten Medienzeit. Während der Dateiprüfung bleibt der Umwandlungsbalken unbestimmt. 100 Prozent Umwandlung erscheinen erst nach erfolgreichem Abschluss und Datenbankspeicherung. Fehler werden pro Datei angezeigt; danach wird die nächste Datei verarbeitet. Fehlgeschlagene Dateien können erneut versucht und noch wartende Dateien entfernt werden.

Noch nicht übertragene Dateien liegen im Browser. Für diese Dateien muss die Seite geöffnet bleiben. Eine bereits auf dem Server laufende Umwandlung wird nach einem Seitenneuladen wieder mit ihrem Status angezeigt. Bei einem Serverneustart erhalten unterbrochene Umwandlungen einen Fehlerstatus und müssen erneut hochgeladen werden.

**Umbenennen** bearbeitet den sichtbaren Namen und den Downloadnamen; gespeicherte Dateipfade bleiben stabil. **Löschen** zeigt vorhandene Playlist-Verwendungen an und verlangt eine Bestätigung. Die Oberfläche erklärt, warum ein Video aktuell nicht löschbar ist. Uploads anderer Dateien blockieren das Löschen unbenutzter Videos nicht.
