# Studio-Update 2.0.0-rc6

## Eine gemeinsame Playlist über Source 2

Ab 2.0 werden Playlists je Benutzer gemeinsam ausgespielt. **Source 1 und Source 2 bleiben unveränderte Live-Eingänge.** Die virtuelle Playlist übernimmt als Ersatz hinter Source 2; sie veröffentlicht nicht auf dem Pfad eines verbundenen Encoders. Ein eigener privater Hilfspfad versorgt die Programme mit einem einzigen H.264/AAC-Encoder. Programme mit unterschiedlichen Live-Routings übernehmen dieses fertig aufbereitete Signal ohne erneute Video-Umwandlung.

Eine gesunde Live-Quelle auf Source 1 oder Source 2 pausiert die gemeinsame Playlist. Die gespeicherte Position wird beim nächsten Einsatz fortgesetzt. Ein geplanter Stream benötigt keine Anmeldung im Browser. Die Programmvorschau und laufende Programmaufnahmen verwenden weiter ihre bestehenden Programmpfade.

Frühere unterschiedliche Playlists je Ausgang sind damit abgelöst. Beim Update wird eine gemeinsame Regel übernommen: zuerst eine bereits aktive Source-2-Regel, sonst eine aktive allgemeine Regel, sonst die erste aktive frühere Bereichsregel. Andere frühere Bereichsregeln bleiben deaktiviert in der Datenbank. Bestehende Programmkennungen und Dateien bleiben erhalten. Das automatische Installer-Backup enthält den vollständigen vorherigen Stand. Die Wiedergabeposition wird nach Möglichkeit aus dem Hauptprogramm übernommen.

## Medien und Playlists getrennt verwalten

Unter **Medien** Ordner verwalten, Videos hochladen, umbenennen, verschieben, ansehen oder löschen. Einzelne Videos anhaken oder alle Videos des aktuellen Ordners wählen. Die Auswahl bleibt beim Ordnerwechsel erhalten. Die aufklappbare Playlist-Übergabe öffnet die gewählte Ziel-Playlist zur weiteren Bearbeitung.

Unter **Playlists** werden ausschließlich Playlists angelegt und bearbeitet. Links steht die Liste, rechts der gewählte Editor mit Name, Ordner und Reihenfolge. **Videos hinzufügen** öffnet eine eigene Auswahl mit Ordnerfilter, Suche und Kontrollkästchen. Mehrere Videos wählen, hinzufügen und anschließend **Playlist speichern** anklicken. Eine Playlist enthält höchstens 200 Videoeinträge; doppelte Einträge sind weiterhin möglich.

Die Liste **Deine Playlists** zeigt alle eigenen Playlists samt Ordnerpfad, unabhängig vom geöffneten Videoordner. **Bearbeiten: …** öffnet die gewählte Playlist. Ein Ordnerwechsel behält einen ungespeicherten Playlist-Entwurf. Große Videoordner werden mit 50 Einträgen je Seite angezeigt; die Massen-Auswahl gilt weiterhin für den ganzen aktuellen Ordner. Name, Ordner und Reihenfolge sind bearbeitbar; einzelne Einträge können entfernt werden. **Playlist löschen** benötigt eine Bestätigung und entfernt keine Videodateien. Laufende oder im Planer beziehungsweise einer Ausspielregel verwendete Playlists sind geschützt. Zuerst die entsprechende Zuordnung entfernen.

## Playlist-Scheduler

**Expertenmodus → Playlist-Ausspielung** enthält die gemeinsame Source-2-Regel, die Verzögerung nach einem Live-Ausfall und wiederkehrende Zeitfenster. Die grafische Übersicht zeigt Playlists als Zeilen und Zeitfenster als Balken. **Woche** und die einzelnen Wochentage wechseln die Ansicht. Ein Balken öffnet das zugehörige Zeitfenster zur Bearbeitung. Die Änderungen werden mit **Ausspielregel speichern** übernommen.

Zeitfenster desselben Regelbereichs dürfen sich nicht überschneiden. Zeitzone, Wochenwechsel und Sommer-/Winterzeit werden berücksichtigt. Gleiche Start- und Endzeit bedeutet einen ganzen Tag; ein kleinerer Endwert reicht in den Folgetag. Die Standardzone ist Europe/Berlin.

## Stream-Planer

Der eigene Menüpunkt **Planer** ist für normale Benutzer verfügbar. Ein Eintrag enthält Titel, Wochentage, Beginn/Ende, Zeitzone, gemeinsame Ersatz-Playlist und die eingerichteten Streaming-Anbieter. Aktivierte Pläne starten die gewählten Anbieter automatisch, auch ohne Live-Eingang oder Browser-Anmeldung.

Beispiel: **Mo und Mi 10:00–13:00**, Twitch und YouTube, Playlist „Wiederholung“. Am Montag ohne Live-Eingang läuft die Playlist. Am Mittwoch beginnt ebenfalls die Playlist; startet Source 1 um 10:30, wird das Live-Signal übernommen. Nach einem erneuten Ausfall wird die Playlist fortgesetzt. Um 13:00 enden die durch diesen Plan automatisch gestarteten Ausgänge.

Manuell gestartete Ausgänge bleiben unabhängig. Ein manueller Stopp verhindert den automatischen Neustart im aktuellen Zeitfenster. Ein späteres neues Zeitfenster darf wieder starten. Überlappende Pläne für verschiedene Anbieter müssen dieselbe Playlist verwenden; ein Ausgang darf keine überlappenden Pläne haben. Gemeinsame Zeitpläne verwenden dieselbe Zeitzone. Die Administration muss **Playlists**, **Automation & Export** und den gewählten Anbieter freigeben.

Ein gerade aktiver Stream-Plan hat für die gemeinsame Playlist Vorrang vor den normalen Playlist-Fallback-/Zeitfensterregeln. Alle laufenden Ausgänge verwenden dieselbe Playlist.

### Übergabe an Twitch

**Sendezeiten auch an meinen Twitch-Kanal übertragen** legt pro gewähltem Wochentag eine wiederkehrende Twitch-Sendezeit an. Dafür Twitch unter **Einstellungen → Twitch** erneut verbinden: benötigt wird zusätzlich `channel:manage:schedule`. Bereits vorhandene Stream-/Chat-Berechtigungen werden beim Update nicht entzogen.

Twitch erlaubt für diese Sendezeiten eine Dauer von 30 Minuten bis 23 Stunden; andere lokale Zeitfenster bleiben ohne Twitch-Übertragung möglich. Der Hintergrundabgleich läuft ungefähr minütlich. Nur von StreamDesk angelegte Zeitplansegmente werden verändert oder entfernt. Externe Twitch-Termine bleiben erhalten. Fehler oder fehlende Berechtigungen erscheinen beim Plan; die lokale Ausspielung läuft unabhängig weiter. Referenz: [Twitch – Scheduling Broadcasts](https://dev.twitch.tv/docs/api/schedule/).

## Persönliche Umschalt- und Wiederholungstexte

Unter **Einstellungen → Darstellung & Sprache → Umschaltbild & Playlist-Kennzeichnung**:

- **Text beim Quellenwechsel:** standardmäßig „Synchronisation“. Wird im Umschaltvideo und beim Neuverbinden der privaten Vorschau verwendet.
- **Text auf Playlist-Videos:** standardmäßig „Wiederholung“, gilt für alle Playlists des Benutzers.
- **Position:** links oben, rechts oben, links unten oder rechts unten.

Der Text wird direkt in das Playlist-Videosignal eingeblendet und ist deshalb auch bei Twitch, YouTube und anderen Anbietern sichtbar. Eine Änderung kann den Playlist-Encoder kurz neu starten; die Programmaufnahme behält ihren Prozess. Ein ausdrücklich aktiviertes natives Standby-Video behält als Medienserver-Ersatzbild Vorrang. Ein echter Ausfall von MediaMTX oder des Netzwerks lässt sich durch ein Umschaltbild nicht überbrücken. Eine Remote-Installation benötigt für das Umschaltvideo den bereits vorgesehenen gemeinsamen nativen Medienspeicher.

Die Wahl des Expertenmodus wird pro Benutzer gespeichert und bei Passwort-, Passkey- und Recovery-Anmeldungen wiederhergestellt. Ausschalten speichert ebenfalls den ausgeschalteten Zustand. Bestehende andere Sitzungen behalten ihre bisherige Freigabe.

## Persönliche FTP-Zugänge

Der native Debian-Installer kündigt die Paketinstallation und FTP-Einrichtung vor der Bestätigung an. Auch mit `--yes` und bei `--dry-run` wird der Hinweis ausgegeben. Er installiert Pure-FTPd und richtet einen eigenen **expliziten FTPS-Dienst auf Port 2121** ein. Vorhandene FTP-Dienste und deren Benutzer bleiben unverändert. Verlangt der Paketmanager die Entfernung eines anderen FTP-Servers, bricht die Installation ab; bei einem solchen Paketkonflikt kann `--disable-ftp` die StreamDesk-Aktualisierung ohne den neuen FTP-Dienst durchführen. Die Authentifizierung läuft über Pure-FTPds [externes Authentifizierungsmodul](https://download.pureftpd.org/pub/pure-ftpd/doc/README.Authentication-Modules); Passwörter werden ausschließlich als Passwort-Hashes gespeichert. Die Webanwendung benötigt keine root-Rechte und führt keine beliebigen Verwaltungsbefehle aus.

1. **Administration → FTP-Zugänge je Benutzer:** Benutzer wählen, separates FTP-Passwort festlegen, Zugang freigeben.
2. **Mein Konto → Dein FTP-Zugang:** Benutzer sieht die Ingest-Domain/IP, Port, Protokoll, passiven Modus und seinen FTP-Benutzernamen. Die kopierbaren Daten und die Verbindungsanleitung bleiben sichtbar. Dort kann er sein eigenes FTP-Passwort ändern.
3. Im FTP-Client **FTP mit explizitem TLS**, den angezeigten Port und die persönlichen Daten verwenden. Bei einem automatisch erzeugten selbstsignierten Zertifikat dessen Fingerabdruck prüfen und dem Zertifikat bewusst vertrauen; ein eigenes gültiges Zertifikat kann der Installer übernehmen.
4. MP4-Dateien in **Bibliothek**, einen vorhandenen Unterordner oder den persönlichen FTP-Hauptordner laden. Neue Unterordner werden in der Medienbibliothek angelegt. Nach Transferende werden die Dateien in die private Umwandlung übernommen. Der Ordner **Bibliothek** zeigt alle fertigen eigenen Videos, einschließlich Web-Uploads und bestehender Unterordner, ohne eine zweite Videokopie anzulegen. Uploads innerhalb dieser Ansicht landen im zugehörigen Medienordner.
5. Unter **Medien → FTP-Importe** stehen Dateigröße, Status, gemessener Umwandlungsfortschritt und Fehlermeldung. Dieselbe Liste ist unter „Mein Konto“ erreichbar. Ab rc6 gibt es keine feste Dateigrößen- oder Laufzeitgrenze, auch für Web-Uploads und Offline-Videos. Original und Umwandlung müssen auf den Datenträger passen. Erst nach erfolgreicher Verarbeitung ist das Video für Playlists verfügbar.

Jeder Zugang ist auf seinen eigenen Ordner beschränkt; er bietet keine Shell-Anmeldung. Bei deaktiviertem StreamDesk-Konto oder gesperrtem FTP-Zugang sind neue Anmeldungen gesperrt. Eine globale Dienstsperre pausiert außerdem neue Importe, behält jedoch Dateien, Zugangsdaten und Konfigurationen. Bereits offene FTP-Verbindungen können noch Daten übertragen; diese werden während der Sperre nicht verarbeitet.

Installer-Optionen:

```bash
sudo bash install.sh --mode update \
  --ftp-port 2121 \
  --ftp-passive-range 30000:30049
```

Port 2121/TCP und 30000–30049/TCP müssen direkt zum Server erreichbar sein; ein HTTP-Reverse-Proxy übernimmt FTP nicht. Bei NAT kann `--ftp-public-ip` die feste öffentliche IPv4-Adresse setzen. `--ftp-certificate /pfad/ftps.pem` übernimmt eine PEM-Datei mit Zertifikat und privatem Schlüssel. Ohne Zertifikat wird eines erzeugt; `--disable-ftp` lässt den eigenen Dienst deaktiviert, `--enable-ftp` aktiviert ihn bei einem späteren Installer-Aufruf wieder. Der Container installiert keinen nativen FTP-Dienst; dort ist FTPS separat bereitzustellen.

Die getrennten Dienste heißen standardmäßig `streamdesk-ftp` und `streamdesk-ftp-auth`. Das Transferprotokoll liegt unter `/var/log/streamdesk-ftp/transfers.log`, Eingangsdateien liegen privat unter dem StreamDesk-Datenordner. Nur abschließende Transferereignisse werden eingelesen; ein noch laufender Upload wird nicht anhand seines Alters importiert. Unterbrochene oder ungültige Transfers durchlaufen ebenfalls die Medienprüfung und können einen Fehler erhalten. Pure-FTPd verweigert neue Uploads bei fast vollem Datenträger.


## FTP-Korrekturen ab rc2

**Administration → FTP-Zugänge** zeigt den bestehenden Zugang des ausgewählten Benutzers einschließlich Freigabestatus und vollständiger Verbindungsdaten. Bei einem neuen Zugang ist ein Passwort erforderlich; beim Bearbeiten kann das Passwortfeld leer bleiben. Nach dem Speichern erscheint eine Bestätigung. Das FTP-Passwort wird nicht im Klartext zurückgegeben.

Die Serveradresse ist immer die konfigurierte **Ingest-Domain oder Ingest-IP** aus `STREAMDESK_INGEST` beziehungsweise `--ingest-host`. Sie kann sich von der Domain der Weboberfläche unterscheiden. Eine alte `STREAMDESK_FTP_HOST`-Angabe wird nicht verwendet.


Die FTP-Bibliotheksansicht wird beim Einrichten des Zugangs und nach Änderungen automatisch abgeglichen. Bei laufender Anwendung geschieht dies ungefähr alle drei Sekunden. Nach größeren Änderungen die Dateiliste im FTP-Client aktualisieren. Leere Web-Unterordner sind ebenfalls sichtbar. Sonderzeichen, die FTP-Programme nicht verlässlich als Dateinamen behandeln, werden in dieser Ansicht ersetzt; bei gleichen Dateinamen hilft eine zusätzliche Kennung. Umbenennen, Verschieben und Löschen der verwalteten Videos erfolgen unter **Medien**. Ab rc4 sind Bibliotheksordner für neue Uploads beschreibbar; fertige Videodateien bleiben gegen direktes Überschreiben geschützt. Der verwaltete Pure-FTPd benennt gleichnamige Uploads automatisch um. `SITE CHMOD` bleibt abgeschaltet. Das Entfernen einer FTP-Ansichtsdatei löscht nicht das Original; der nächste Abgleich stellt die Ansicht wieder her. Neue und unvollständige Uploads bleiben beim Abgleich erhalten. Bereits vorhandene gleichnamige Eingangsordner bleiben erhalten; der tatsächlich gewählte Bibliothekspfad steht in den Verbindungsdaten. Eigene Ansichtsdateien werden nicht erneut importiert. Ein Installer-Update übernimmt die neuen Pure-FTPd-Optionen.

## Langsamer Playlist-Start ab rc4

Die Vorbereitung des gemeinsamen Encoders läuft im Hintergrund. Das Dashboard zeigt **Playlist wird vorbereitet**, bis FFmpeg das erste Signal erzeugt. Der frühere feste Abbruch nach fünf Sekunden entfällt; ein fehlender Start wird nach 45 Sekunden aufgeräumt und mit dem normalen Wiederholungsabstand erneut versucht. Live-Quellen können die Vorbereitung jederzeit unterbrechen. Ausgänge und Programmleser behalten währenddessen das Umschaltbild. Internes RTSP begrenzt die Paketgröße auf 1200 Byte.

### Wenn WebRTC nach dem Start abbricht

Die Signalisierung über die Webadresse und die direkte Medienverbindung sind getrennte Schritte. Unter **Expertenmodus → Protokolle & WebRTC** als Administrator **Ingest-Host übernehmen** und anschließend **WebRTC-Konfiguration speichern** verwenden, wenn die öffentliche Adresse noch fehlt. Der konfigurierte UDP-Medienport (standardmäßig 8189) muss erreichbar sein; bei NAT ist die passende Weiterleitung erforderlich. Bestehende Listener und TURN-Einstellungen werden durch dieses Update nicht automatisch umgebaut. Die Vorschau zeigt jetzt die jeweilige Verbindungsphase und unterscheidet einen nicht erreichbaren Medienweg von einer bestehenden Verbindung ohne Videodaten. Ton lässt sich im Player einschalten.

## Große Videoimporte ab rc6

Web-Uploads werden direkt unter `STREAMDESK_DATA/uploads` zwischengespeichert und per Umbenennen an die Verarbeitung übergeben; dafür wird keine zweite vollständige Uploadkopie angelegt. Die Übertragung und die eigentliche Umwandlung haben kein festes Gesamtzeitlimit. Vor der Umwandlung wird ihr Speicherbedarf aus der Videolänge geschätzt; währenddessen wird freier Speicher überwacht. Die genaue Speicherprüfung ist in der [Konfiguration](CONFIGURATION.md#speicher-für-videoimporte-ab-200-rc6) beschrieben. Ein 6-GB-Video von etwa zwei Stunden ist damit grundsätzlich möglich, sofern ausreichend Speicher vorhanden ist.

Bereits mit „Nur MP4-Dateien bis 500 MB können importiert werden.“ abgewiesene FTP-Dateien werden nach dem Update erneut eingereiht, wenn die ursprüngliche abgeschlossene Datei noch vorhanden und der Zugang aktiv ist. Ein weiterer Upload ist dafür nicht nötig. Neuere Dateien unter demselben Namen benötigen ihr eigenes abgeschlossenes Transferereignis.

Nach einer fehlgeschlagenen FTP-Umwandlung bleibt das Original privat für **Erneut importieren** erhalten. Nach erfolgreicher Umwandlung wird es entfernt und die fertige Datei in „Bibliothek“ eingeblendet. **Quelldatei löschen** gibt nach einem fehlgeschlagenen Import den belegten Speicher frei; ein weiterer Versuch erfordert dann einen neuen Upload. Ein Serverneustart markiert unterbrochene Umwandlungen als Fehler; erhaltene FTP-Originale können erneut versucht werden. Durch frühere Versionen bereits gelöschte Quelldateien lassen sich nicht wiederherstellen.
