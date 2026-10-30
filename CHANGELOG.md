# Änderungen

## 2.0.0-rc6

- Feste Größen- und Laufzeitgrenzen für MP4-Importe entfernt: Web und FTPS erlauben Videos unabhängig von Dateigröße und Länge, auch in der einfachen Offline-Videobibliothek. Die bisherigen 500 MB, 120 Minuten beziehungsweise fünf Minuten gelten nicht mehr. Upload und eigentliche Umwandlung besitzen kein festes Gesamtzeitlimit.
- Freier Datenträgerspeicher bestimmt den Import: Web-Uploads werden direkt im Datenverzeichnis zwischengespeichert und ohne zweite vollständige Dateikopie übernommen. Empfangene Daten, geschätzter Ausgabespeicher, andere Umwandlungen und 350 MiB Betriebsreserve werden berücksichtigt; laufende Umwandlungen überwachen freien Platz und entfernen bei Abbruch ihre Teilausgabe. Unfertige Web-Zwischendateien werden bei Anfrageende oder nach Serverneustart bereinigt.
- Noch vorhandene abgeschlossene FTP-Dateien, die an der früheren 500-MB-Grenze scheiterten, werden bei aktivem Zugang nach dem Update automatisch erneut eingereiht. Fehlgeschlagene neue FTP-Umwandlungen behalten das Original privat für einen erneuten Versuch; nach Erfolg wird es entfernt. Gespeicherter Zielordner und Benutzerzuordnung bleiben erhalten. Kontolöschung archiviert auch zurückbehaltene FTP-Originale.
- „Medien → FTP-Importe“ ergänzt Status, Dateigröße in GB, gemessenen Umwandlungsfortschritt, Vorschau fertiger Dateien, „Erneut importieren“ und bestätigtes Löschen einer zurückbehaltenen Quelldatei. Derselbe Status bleibt unter „Mein Konto“ verfügbar; Zugänge und interne Dateipfade bleiben geschützt.
- VERSION, Installer-Hinweis, README-Screenshots und Betriebsdokumentation auf rc6 aktualisiert. Reverse-Proxy-Beispiel hebt die bisherige HTTP-Dateigrenze mit `client_max_body_size 0` auf; vorhandene externe Proxy-Hosts müssen manuell angepasst werden.
- Prüfstand: 236 Unit-Tests bestanden. Zwei sparse MP4-Dateien mit jeweils 6 GiB wurden über FTP-Wiederholung beziehungsweise Web-Zwischenspeicher mit echtem FFmpeg 7.1.5 verarbeitet und als dekodierbare H.264-/AAC-Videos einer Playlist zugeordnet. Echte FTPS-, Mehrfachupload-, Desktop-/Mobil- und Studio-Prüfungen einschließlich geplanter lokaler RTMP-Ausgänge, Ton, Quellenwechsel, Fortsetzung, Aufnahme und WebRTC bestanden. Die 6-GiB-Prüfung testet große Dateigrößen mit kurzen gültigen Medieninhalten, keine vollständige 6-GiB-Netzwerkübertragung oder zweistündige Echtzeitwiedergabe.

## 2.0.0-rc5

- Wiederholten Wechsel zwischen Playlist und Standby an einem gespeicherten Schleifenende behoben. Der gemeldete Einstieg lag nur 69 Millisekunden vor dem rechnerischen Ende; die tatsächlichen umgewandelten Videos endeten durch Container-/AAC-Rundung etwas früher. FFmpeg konnte bei diesem Einstieg bei einem Frame ohne Mediendaten hängen bleiben, worauf MediaMTX die Verbindung nach zehn Sekunden schloss. Fortsetzpunkte innerhalb der letzten 250 Millisekunden beginnen jetzt den nächsten Playlist-Durchlauf. Andere Positionen werden unverändert fortgesetzt; vorhandene Videos, Playlists und Zeitpläne bleiben erhalten.
- Die Startprüfung verlangt mehrere Videoframes und eine positive Ausgabezeit. Ein einzelner vorbereiteter Frame mit `out_time=N/A` gilt nicht mehr als laufende Playlist.
- Gezielten echten Regressionstest mit fünf Dateien, den gemeldeten Videolängen und derselben Fortsetzposition ergänzt. Er prüft hörbaren Ton, steigende Datenzähler und eine unveränderte RTSP-Verbindung über die serverseitige Zeitüberschreitung hinaus. Unit-Tests sichern den Endbereich sowie normale Fortsetzpunkte ab.
- Prüfstand: 227 Unit-Tests; gezielter Fortsetztest und vollständiger Studio-Test mit FFmpeg 6.1.1 sowie 7.1.5 und MediaMTX 1.21.3 bestanden. Beide lokalen RTMP-Verbindungen, Aufnahme, Dashboard-Ton und WebRTC bleiben bei den Quellenwechseln erhalten. Version und Dokumentation auf rc5 aktualisiert; die Bestätigung auf dem Benutzer-Server nach Installation steht aus.

## 2.0.0-rc4

- Wiederholte Playlist-Abbrüche im Planer behoben: Der gemeinsame Encoder wird bei einem langsameren Start nicht mehr nach fünf Sekunden beendet. Seine Vorbereitung läuft ohne blockierendes Warten weiter und bleibt über Controller-Durchläufe erhalten. Erst nach 45 Sekunden ohne erstes Signal wird aufgeräumt und mit Wiederholungsabstand neu versucht. Zurückkehrende Live-Quellen können die Vorbereitung unterbrechen; deaktivierte Benutzer und entfernte Programme hinterlassen keinen Startprozess.
- Dashboard zeigt „Playlist wird vorbereitet“ während des Starts. Programme und geplante Ausgänge nutzen währenddessen das bestehende Umschaltbild. Interne RTSP-Ausgaben verwenden 1200 Byte Paketgröße. AAC-/Opus-Umwandlung beim Kopieren des Programmbilds erhält die gemeinsame Zeitbasis beider Spuren.
- FTP-Uploads direkt in „Bibliothek“, bestehende Medien-Unterordner und neue Unterordner ermöglicht. Fertige Videos bleiben gegen Überschreiben geschützt; Pure-FTPd vergibt bei gleichnamigen Uploads einen neuen Namen. Der Abgleich erkennt seine eigenen Ansichtsdateien, erhält unbekannte und unvollständige Uploads und ordnet Uploads auch nach einem Web-Ordnerwechsel dem bisherigen Medienordner zu. Keine zusätzliche Kopie fertiger Videos und kein erneuter Import der Ansichtsdateien.
- Medien- und Playlist-Verwaltung in eigene Menüpunkte getrennt. „Medien“ enthält Ordner, Uploads und Dateiverwaltung; „Playlists“ enthält die Playlist-Liste und den Editor mit Name, Ordner, Reihenfolge und Löschfunktion. Eine aufklappbare Videoauswahl mit Suche, Ordnerfilter und Kontrollkästchen ergänzt den Editor. Entwürfe bleiben beim Ansichtswechsel erhalten; die Massen-Auswahl umfasst alle Videos des aktuellen Medienordners.
- Unit-, echte FTPS-, Medien- und Browsertests um langsame Encoderstarts, erhaltene Uploads, Ordnerzuordnung und getrennte Verwaltungsansichten erweitert. VERSION, Betriebsdokumentation und README mit aktuellen Screenshots auf rc4 aktualisiert. Eine Bestätigung auf dem Benutzer-Server nach dem Update steht aus.

## 2.0.0-rc3

- Deutlich beschriftete Schaltfläche „Ton einschalten / ausschalten“, Lautstärkeregler und Tonstatus direkt unter der Dashboard-Programmvorschau ergänzt. Normale Benutzer können den Ton ohne Expertenmodus bedienen; Browser-Stummschaltung und Regler bleiben synchron. Auch einzeln geöffnete HLS- und WebRTC-Player besitzen eine sichtbare Tonsteuerung.
- Nach einem HLS-Neustart wird eine vom Browser verweigerte automatische Tonwiedergabe aufgefangen: Das Bild startet stumm weiter, der Ton lässt sich erneut per Klick freigeben.
- Playlist-Übernahme ins Programm verarbeitet die Audiospur mit frischen Zeitstempeln als AAC/48 kHz/Stereo. Das gemeinsam erzeugte H.264-Bild wird weiterhin kopiert; es entsteht kein weiterer Videoencoder pro Ausgang. Der interne Transport bleibt RTSP, echte SRT-/RTMP-Live-Eingänge bleiben unverändert.
- WebRTC-Audiobrücke normalisiert den Audiostart vor der Opus-Kodierung und verwendet ein größeres Analysefenster. Die Vorbereitung bestätigt erst ein tatsächlich veröffentlichtes H.264-/Opus-Signal. Unvollständige beziehungsweise fehlgeschlagene Starts räumen ihren Prozess auf, damit der nächste Versuch frisch beginnt.
- Während der WebRTC-Vorbereitung schützt eine begrenzte Startfrist den Prozess vor der bisherigen automatischen Leerlaufbereinigung. Langsamere Playlist-/Verbindungsstarts werden dadurch nicht bereits nach 20 Sekunden ohne verbundenen Leser beendet.
- Tests um Tonbedienung, echten dekodierten Dashboard-Ton, anspruchsvollere Playlist-Bilder und alte Pfade ohne Präfix erweitert. Der Startschutz und die Bereinigung unvollständiger Signale sind durch Unit-Tests abgesichert. Version und Dokumentation auf rc3 aktualisiert; die Bestätigung auf dem Benutzer-Server steht aus.

## 2.0.0-rc2

- FTP-Verwaltung in ein eigenes Administrations-Untermenü verschoben. Erfolgreiches Speichern beendet die Anzeige „Wird gespeichert …“ und zeigt eine dauerhafte Bestätigung.
- Verbindungsdaten des ausgewählten Benutzers sind vor und nach dem Speichern sichtbar: Ingest-Domain/IP, Port, Protokoll, passiver Modus und FTP-Benutzername mit Kopierfunktionen. Vorhandene Zugänge laden ihren Freigabestatus; Passwortwechsel und Sperren erhalten die bestehenden Daten.
- Die FTP-Serveradresse wird ausschließlich aus STREAMDESK_INGEST übernommen. Eine alte abweichende STREAMDESK_FTP_HOST-Einstellung wird ignoriert und vom Installer entfernt.
- Persönlichen FTP-Zugang samt Passwortverwaltung und Verbindungsanleitung nach „Mein Konto“ verschoben.
- Web-Uploads und bestehende Unterordner werden im persönlichen FTP-Ordner „Bibliothek“ zum Lesen und Herunterladen angezeigt, ohne eine zweite Videokopie anzulegen. Umbenennen, Verschieben und Löschen über die Webverwaltung werden automatisch abgeglichen; neue FTP-Uploads bleiben separat möglich. Schreibschutz und Ausschluss aus dem Import verhindern beschädigte oder doppelt importierte Bibliotheksdateien.
- Alle vorhandenen Playlists sind unabhängig vom geöffneten Videoordner erreichbar und bearbeitbar/löschbar. Ungespeicherte Playlist-Entwürfe bleiben beim Ordnerwechsel erhalten.
- Bibliotheksabfragen mit einmaliger Auswertung der Playlist-Verweise und passenden Datenbankindizes beschleunigt. Ordnernavigation verwendet bereits geladene Daten; Videolisten zeigen höchstens 50 Einträge je Seite und unveränderte Hintergrundabfragen bauen die Oberfläche nicht neu auf.
- Direkter MediaMTX-Laufzeitabgleich und lokale Dienstberechtigungen berücksichtigen nun auch ausdrücklich aus der Datenbank zugeordnete ältere Pfade ohne den aktuellen Namensbereich, etwa „live“ und „playlist-source2“. Ein leerer Präfix wird dabei niemals als Freigabe für fremde Pfade verwendet; der Installer nutzt denselben Abgleich.
- WebRTC zeigt einzelne Verbindungsphasen und konkrete Hinweise bei unerreichbarem Medienport oder fehlenden Videodaten; erfolglose Verbindungen werden nach begrenzter Wartezeit aufgeräumt.
- Medienprüfung auf hörbaren Testton erweitert: Upload/Umwandlung, Playlist-Fortsetzung, zwei lokale RTMP-Ausgänge und tatsächlich dekodiertes WebRTC-Audio. Ein absichtlich unerreichbarer WebRTC-Host prüft die Fehleranzeige. Zusätzlicher Integrationslauf mit älteren Konten ohne Pfadpräfix bestanden. Die Bestätigung nach dem Update des Benutzer-Servers steht aus.
- Prüfstand: 218 bestandene Unit-Tests, echte FTPS-Prüfung, Browserprüfung der Kontoverwaltung sowie große Bibliothek und echte Medienprüfung. README-Screenshots und Betriebsdokumentation aktualisiert.
- Der Installer informiert vor Bestätigung und Änderungen ausdrücklich über Installation/Aktualisierung von Pure-FTPd und OpenSSL, zusätzliche FTPS-Dienste, Ingest-Adresse und benötigte Ports. Auch nicht interaktive Updates und reine Prüfungen zeigen den Hinweis; deaktivierte FTP-Einrichtung und übersprungene Paketinstallation werden berücksichtigt.

## 2.0.0-rc1

- Persönliche FTP-Zugänge durch Administratoren anlegen, freigeben und sperren; Benutzer verwalten ihr eigenes getrenntes FTP-Passwort. Pure-FTPd mit verpflichtendem explizitem TLS, abgeschlossenen Benutzerordnern und automatischer Video-Umwandlung einschließlich Unterordnern im nativen Installer ergänzt.
- Mehrere Videos anhaken, ordnerübergreifende Auswahl sammeln und gemeinsam zu einer Playlist hinzufügen. Bearbeiten, Umbenennen, Reihenfolge, Entfernen und bestätigtes Löschen von Playlists deutlicher zugänglich gemacht; verwendete Playlists bleiben geschützt.
- Gemeinsame Playlist über Source 2 für alle Ausgänge statt unterschiedlicher Playlists je Anbieter. Ein geteilter Playlist-Encoder erzeugt das Videosignal; andere Programme übernehmen es ohne erneute Video-Umwandlung. Live auf Source 1/2 pausiert die Playlist, danach wird die gespeicherte Position fortgesetzt. Feste Live-Eingänge und bestehende Programmkennungen bleiben erhalten.
- Grafischer Playlist-Scheduler mit Wochen-/Tagesansicht und anklickbaren Zeitfenstern. Frühere Bereichsregeln werden beim Update in eine gemeinsame Source-2-Regel überführt; andere alte Regeln bleiben deaktiviert gespeichert.
- Neuer persönlicher „Planer“ mit wiederkehrenden Streamzeiten, Ersatz-Playlist und ausdrücklicher Anbieterauswahl. Automatischer Start ohne Anmeldung oder Live-Signal, saubere Übernahme durch Live und Ende automatisch gestarteter Ausgänge am Zeitfensterende. Manuelle Starts und Stopps haben Vorrang.
- Optionale Übertragung wiederkehrender Sendezeiten an Twitch mit zusätzlicher Zeitplan-Berechtigung. Nur von StreamDesk angelegte Twitch-Segmente werden verwaltet; bestehende Stream-/Chat-Berechtigungen bleiben gültig.
- Persönlicher Umschalttext, standardmäßig „Synchronisation“, als Videobild und Vorschau-Verbindungstext. Kontoweite Playlist-Kennzeichnung, standardmäßig „Wiederholung“, mit vier wählbaren Bildecken direkt im gesendeten Video.
- Expertenmodus wird pro Benutzer gespeichert und nach Passwort-, Passkey- sowie Recovery-Anmeldung wiederhergestellt. FTP, Planer und Playlists berücksichtigen die zentralen Dienstfreigaben.
- VERSION, README, Installer, Screenshots und Betriebsdokumentation für 2.0.0-rc1 aktualisiert. 207 Unit-Tests sowie echte FTPS-, Medien- und Browserprüfungen bestanden. MediaMTX bleibt auf dem geprüften 1.21.x-Profil.

## 1.1.8

- Mehrere MP4-Dateien gleichzeitig in Offline- und Playlist-Bibliothek auswählen; gemeinsame Warteschlange verarbeitet die Dateien nacheinander und bleibt beim Menüwechsel erhalten. Fehlerhafte Videos verhindern die folgenden Uploads nicht.
- Pro Datei getrennte Fortschrittsanzeigen für Upload mit übertragener Datenmenge sowie tatsächliche FFmpeg-Umwandlung. Abschluss erst nach erfolgreichem Speichern; private Upload-Aufträge, Wiederaufnahme der Statusanzeige nach Seitenneuladen und Schutz vor doppelter Verarbeitung bei wiederholter Anfrage.
- Videos in beiden Bibliotheken umbenennen; Dateizugänge, IDs, Playlist-Verweise und Wiedergabepositionen bleiben erhalten. Der sichtbare Name wird auch für Dateidownloads verwendet.
- Löschbarkeit und konkrete Nutzungsgründe sichtbar. Löschen fragt aktuelle Verweise erneut ab und kann nach Bestätigung Referenzen aus inaktiven Playlists entfernen. Aktuelle Offline-Videos, laufende Playlist-Dateien und letzte Videos zugeordneter Playlists bleiben geschützt.
- Umwandlungs-Zeitlimit, Fortschritts-/Fehlerstatus und Speicherreservierungen für aufeinanderfolgende Dateien abgesichert. Neue Dokumentation und Version 1.1.8.

## 1.1.7

- Separate Playlist-Verwaltung mit benannten Ordnern/Unterordnern, Video-Uploads bis 500 MB/120 Minuten, Reihenfolge, mehrfachen Videoeinträgen und Dauerschleifen. Die vorhandene Offline-Video-Auswahl bleibt erhalten.
- Expertenbereich für verzögerten Playlist-Fallback, Regeln hinter Source 2/weiteren Eingängen und unabhängige Playlists je Ausgang. Echte zugeordnete Live-Quellen behalten Vorrang; Playlists werden beim nächsten Einsatz an ihrer gespeicherten Position fortgesetzt.
- Wochenzeitpläne mit IANA-Zeitzonen, Mitternachtsfenstern, Überschneidungsprüfung und Sommer-/Winterzeit. Optionaler automatischer Ausgangsstart mit eigenem Ende; manueller Stopp hat Vorrang und manuell gestartete Ausgänge bleiben unabhängig.
- Eigene stabile Programmidentitäten für Ausgangsregeln, Playlist-Status im Dashboard und geschützter Programmvorschau. Programmaufnahmen bleiben bei Playlist-/Live-Wechseln erhalten.
- Globale Dienstfreigabe „Playlists“ mit serverseitiger Sperre; Automation-Freigabe für Zeitpläne. Mandantengrenzen, Schutz referenzierter Videos/Playlists, persistente Positionen und Archivierung bei Kontolöschung ergänzt.
- VERSION, README, Installation und Betriebsdokumentation auf 1.1.7 aktualisiert.

## 1.1.6

- Administration mit gruppierten Dienstfreigaben für alle Benutzer: Plattformen, Discord, WebRTC, neue Aufnahmen, Playback, Zuschauerlinks, zusätzliche Quellen/Routing, Browser-Overlays, Automation und Benachrichtigungen. Nur Administratoren ändern die Freigaben; Expertenmodus und direkte API-Aufrufe umgehen keine Sperren. Konfigurationen und Archive bleiben erhalten.
- Aktive betroffene Ausgänge/WebRTC-Verbindungen werden beendet, manuelle Aufnahmen sauber abgeschlossen und native Aufnahmeabsichten über verschachtelte Dienstsperren erhalten. Hintergrundaufträge pausieren; während der Sperre verpasste Starts müssen neu geplant werden. Fremde MediaMTX-Pfade bleiben unverändert.
- Inhaltsfingerabdruck für statische Dateien ergänzt; Änderungen erhalten auch innerhalb eines Entwicklungsstands frische Browser-Cache-Adressen.

## 1.1.5

- Einstellungen in eigene Untermenüs für Streaming-Auswahl, Twitch, YouTube, eigenen Anbieter und Darstellung/Sprache getrennt. Pro Plattform bleiben Kontofreigabe und Streamschlüssel zusammen; Schlüssel werden im jeweiligen Bereich verwaltet.
- Eigener Expertenbereich „Discord-Bot“ mit Anleitung für App, Token, Message Content Intent, Servereinladung und Kanal-ID. Einrichtung und Trennung sind auch serverseitig an den Expertenmodus gebunden; vorhandene Chats bleiben normal nutzbar.
- Version in Oberfläche und Status-API sichtbar. Statische Dateien übernehmen ihre Cache-Version aus VERSION.


### Prüfung und Korrekturen

- Quellensteuerung von zeitaufwendigen Zeitplan-/Exportarbeiten getrennt; atomare Auftragsübernahme, gestreamte Dateiübertragung und Wartezeiten nach Exportfehlern.
- Szenen im Expertenbereich mit serverseitiger Sperre und Aufnahme-Schutz auch bei gleichzeitigem Umrouten mehrerer Ziele. Automation-Untermenü erreichbar; ungespeicherte Formulare bleiben beim Polling erhalten.
- Vollständige Passkey-Prüfung mit `py_webauthn`, verifizierten Benutzern, serverseitigen Einmal-Challenges und Anmeldelimit für Passkeys/Recovery. Konto- und Clip-Löschung behandeln neue Daten vollständig; erfolgreiche HTTP-204-Antworten werden in der Oberfläche korrekt erkannt.
- YouTube-gRPC-Nachrichtenverarbeitung nach Discord-Erweiterung wiederhergestellt; Discord-Cursor berücksichtigt auch übersprungene Bot-Nachrichten.
- Feste Dienstkonten erhalten begrenzte Konfigurations-/Aufnahme-ACLs; Gruppenrechte bleiben bei atomaren Schreibvorgängen erhalten. Browser-Renderer werden ohne root oder zusätzliche Kill-/Dateirechte gesteuert; Live-Overlays behalten Format und Quellenstatus.
- On-demand-Pull für Programmverbraucher aktiviert und im Leerlauf beendet. Inaktive statische Quellen werden als offline erkannt. Standby-Dateien liegen im gemeinsamen nativen Speicher; UDP-Portkonflikte und unvollständige Protokollwechsel werden abgefangen.
- Remote-Updates behalten Betriebsart und Endpunkte. Native Dateifunktionen benötigen dort explizit gemeinsamen Speicher. Container-Bootstrap erzeugt gültiges JSON auch für Sonderzeichen, private Daten bleiben außerhalb des Build-Kontexts; Readiness prüft den Quellenmanager.
- Unvollständiger HTTP-/JWT-Wechsel gesperrt. Striktes RTSPS ohne vorbereiteten internen TLS-Endpunkt wird abgewiesen; RTMPS-Verbindungsdaten verwenden den tatsächlichen Listener. Webhook-/Export-/SMTP-Verbindungen prüfen und binden öffentliche Zieladressen und folgen keinen HTTP-Weiterleitungen.

### Weitere Änderungen seit rc.6

- MediaMTX-Kompatibilitätsprofil, Versionsprobe und explizite Installer-Ziel-Major-Auswahl verhindern unbekannte Major-/Schema-Wechsel; die 2.x-Freigabe benötigt ein geprüftes StreamDesk-Profil.
- Persistente, eigentümergeschützte Clips sowie deduplizierte Webhook-/E-Mail-Benachrichtigungen für Offline-, Forward- und Speicherereignisse.
- BUILD D ergänzt gespeicherte Szenen aus Quellenprogramm, Overlay-Video und Zielen sowie Browser-Overlays auf Live-Programmen.
- Rollen und serverseitige Policies unterstützen einem Chat-Konto zugewiesene Moderatoren; Administratoren verwalten Rollen.
- WebAuthn-Passkeys mit Einmal-Recovery-Codes, verschlüsselter Discord-Chat-Adapter, EN/DE-Benutzerpräferenz und geplanter Twitch-Titel/Start.
- Installer richtet StreamDesk und das mitgelieferte MediaMTX mit festen unprivilegierten Systemkonten, gemeinsamen Minimalrechten und gehärteten systemd-Units ein.
- Die Control API kann ausdrücklich mit Zertifikat, Schlüssel und optionaler eigener CA auf HTTPS umgestellt werden; Zertifikatsfehler brechen Installation oder Update mit Rollback ab.
- Optionale RTMPS-/RTSPS-Listener mit verwaltetem Zertifikat, tenantisolierte Prometheus-Leser-/Fehlerwerte und eine konfigurierbare Warnung bei 85 Prozent der verfügbaren Upload-Bandbreite.
- Gemeinsamer MediaMTX-Client für lokale und entfernte Control APIs, expliziter Remote-Modus ohne entfernte Dateioperationen sowie Docker-/Compose-Paketierung mit persistenten Volumes und Healthchecks.
- Interne Authentifizierung mit Vorbereitung einer späteren externen Strategie; HTTP-/JWT-Wechsel bleiben bis zur vollständigen Anbindung gesperrt. Quellenwahl für WebRTC, MoQ, abgesichertes UDP-MPEG-TS/RTP und SRT-Leseadressen.
- Konfigurierbare Fallback-/Retry-Zeiten, Source-on-demand, `alwaysAvailableFile`, öffentliche Pfad-Proxys und Kick-/Facebook-/Trovo-Ausgangsvorlagen.
- Persistente Aufnahme-/Ausgangszeitpläne, strikt allowlist-basierte Publish-/Ready-Hooks und idempotenter HTTPS-PUT-Export für WebDAV-/Upload-Zielbasen. Beliebige vorsignierte S3-URLs sind nicht unterstützt.

## 1.1.0

- Stabiler Stand der in 1.1.0-rc.1 bis 1.1.0-rc.6 gelieferten Medien-, Routing-, Playback-, Konto- und Wiederherstellungsfunktionen.
- Die dokumentierte rc.6-Routingmatrix, privaten Vorschau- und Playback-Grenzen sowie Attach-/Recovery-Schutzregeln wurden als Release-Basis übernommen.
- Feature-, Installations- und Testdokumentation auf den stabilen 1.1.0-Stand synchronisiert.

## 1.1.0-rc.6

- Standard wieder exakt Source 1 und Source 2 sowie Twitch, YouTube und ein eigener Anbieter. Source 1/2 lassen sich weder umbenennen, umkonfigurieren, löschen noch unter die Prioritäten zusätzlicher Quellen verschieben.
- Zusätzliche Quellen und Ausgänge nur nach ausdrücklichem Anlegen im Expertenmodus. Je Benutzer bis zu zehn Quellen und zehn Ausgänge, darunter weitere Twitch-/YouTube-Konten mit eigenen Streamschlüsseln und benannte eigene Anbieter.
- Zuordnung pro Quelle und Ausgang: Nur zugeordnete verfügbare Quellen konkurrieren. Source 1 hat Priorität 1, Source 2 Priorität 2, zusätzliche Quellen ab Ebene 3. Verschiedene Ausgänge können gleichzeitig unterschiedliche Programme senden; gleiche Quellenmengen teilen sich einen Encoder.
- Eigene Expertenbereiche „Quellen & Routing“ und „Ausgänge & Konten“. Quellen einzeln auswählen und bearbeiten. Die normale Quellenansicht zeigt je Quelle eine eigene Vorschau und aufklappbare Verbindungsdaten statt einer gemeinsamen Zugangsdatenliste.
- Dashboard mit umschaltbarer Vorschau je Ausgang, tatsächlicher Programmquelle, Prioritätskette und ständig sichtbarem privaten Vorschau-Link; WebRTC-Link im Expertenmodus. Programmaufnahmen können auch gezielt ein zusätzliches Programm erfassen.
- Neuer, für Benutzer und Administratoren sichtbarer Menüpunkt „Mein Konto“ mit eigenem Passwortwechsel. Andere Anmeldungen werden danach ungültig; die aktuelle Sitzung bleibt erhalten.
- Deaktivierte Benutzer können nach Namensbestätigung gelöscht werden. Eigene Pfade/Zugänge und Kontodaten werden entfernt, Mediendateien privat archiviert. Aktive Konten, das eigene Administratorkonto sowie laufende Verarbeitung/Abschlüsse sind geschützt. Benutzer-IDs werden nach Löschen nicht wiederverwendet.
- Aufnahmeabschluss über FFmpeg-Steuerkanal und kurze Fragment-/Interleave-Intervalle statt vorzeitigem erzwungenem Prozessende; verhindert verlorene Schlusssekunden beim manuellen Stopp.
- Wiederholbare Migration erhält tatsächlich genutzte zusätzliche Quellen, vorhandene Schlüssel, Auswahl, Routing und Archive. Eine unbenutzte automatisch erzeugte Source 3 entfällt. Alte globale manuelle Quellenwahl wird durch Prioritäten je Ausgang ersetzt; Quellenwechsel innerhalb eines Programms bleiben aufnahmestabil.

## 1.1.0-rc.5

- Programmpfad bleibt unabhängig von Streamingzielen verfügbar. Quellenwechsel und Start/Stopp von Weiterleitungen schließen Programmleser und die manuelle Programmaufnahme nicht mehr. Lokale Aufnahmezeitstempel erhalten die vollständige Laufzeit trotz wechselnder Publisher-Zeitbasen. Aktivierte native Programmaufnahmen erfassen auch den Standby-Zeitraum zwischen Quellen.
- Dashboard lädt die Programmvorschau nach anfänglichem Verbindungsaufbau, nach Schließen/Öffnen und nach einem Ansichtswechsel wieder korrekt statt auf `about:blank` zu bleiben. HLS-Abrufe verwenden die persönlichen Medienrechte.
- Programmvideo wird einheitlich als H.264 ohne B-Frames mit 1080p30 und AAC/48 kHz/Stereo aufbereitet. Dies verhindert ungültige Zeitstempel und Codecwechsel bei unterschiedlichen Quellenprofilen; der zusätzliche Videoencoder benötigt CPU. Direkte native Eingangsaufnahmen behalten ihr Quellenformat.
- WebRTC-Programmvorschau verwendet einen privaten, nur bei Bedarf gestarteten H.264-/Opus-Pfad, damit auch Programm-Audio im Browser ankommt. Mehrere Zuschauer desselben Benutzers teilen sich den Prozess; nach 20 Sekunden ohne Leser wird er beendet.
- Offline-Video bzw. Browser-Overlay läuft bei Vorschau, Programmaufnahme, aktivierter nativer Programmaufnahme oder Streamingziel; laufende Live-Quellen behalten die eingestellte Priorität. Ohne Verbraucher und ohne aktive Live-Quelle bleibt die Offline-Datei pausiert.
- Neuer echter Regressionstest mit zwei parallelen Quellen, B-Frames und unterschiedlichen Auflösungen: eine Aufnahme, HLS-/WebRTC-Programm ohne Streamingziel, Quellenverlust, Offline-Fallback sowie Start/Stopp eines Ausgangs.

## 1.1.0-rc.4

- Verbindliche eigenständige Planung in `ROADMAP.md`; spätere Wellen bleiben getrennt von dieser Umsetzung.
- Eigenes Playback-Untermenü mit Segmentauswahl, Startzeit/Dauer, Video und Download. MediaMTX-Playback wird nur ausdrücklich durch Administratoren im Expertenmodus aktiviert; neue Listener liegen auf Loopback. Persönliche Playback-Berechtigungen und der Sitzungsproxy begrenzen den Zugriff auf eigene Quellen.
- Native fMP4-Wiedergabe über MediaMTX; MPEG-TS wird wegen der Grenze in v1.21.3 über FFprobe/FFmpeg in fragmentiertes MP4 umgepackt. Höchstens eine Stunde pro Abruf und zwei gleichzeitige MPEG-TS-Konvertierungen.
- Source 3 mit RTMP-/SRT-Verbindungsdaten und optionaler öffentlicher RTSP-/RTSPS-Pull-Quelle. Auto-Priorität Source 1 → Source 2 → Source 3 → Pull → Offline; alle Eingänge auch manuell wählbar und aufnehmbar. Alte Vorschau- und Ingest-Adressen bleiben gültig.
- Programm-Audio wird auf AAC, 48 kHz und Stereo vereinheitlicht; Mono-Quellen können dadurch zuverlässig mit dem MediaMTX-Standby-Signal wechseln.
- Bis zu fünf benannte Custom-Ziele neben den festen Twitch-/YouTube-Slots. Jedes Ziel separat starten/stoppen, umbenennen und nach Stopp ändern/löschen; zusätzliche Upload-Bandbreite wird im UI erläutert. Bestehende Custom-Schlüssel und Auswahldaten bleiben bei der Migration erhalten.
- Installer liefert neue Module und Roadmap aus, erhält vorhandene Playback-Einstellungen und unterstützt die ausdrückliche Aktivierung mit `--enable-playback --playback-port 9996`.

## 1.1.0-rc.3

- Eigener Menüpunkt „Expertenmodus“ mit Untermenüs für Protokolle/WebRTC, Quellen/Ziele, native Aufnahme, Zuschauerfreigabe und Neuverbindung. Normale Einstellungen, Quellen und Aufnahmen enthalten keine technischen Konfigurationsformulare mehr.
- WebRTC mit sichtbarem Konfigurations-/Laufzeitstatus, geführter Aktivierung und vorgeschlagenem Ingest-Host. Bei deaktiviertem Server führt die Kameraseite zur Einrichtung; Server-Aktivierung bleibt eine bewusste Administratoraktion im Expertenmodus.
- SRT-Verbindungsdaten mit explizitem Caller-Modus, einer Sekunde Latenzpuffer und getrennten Server-/Stream-ID-Feldern samt OBS-Hinweisen.
- Protokollstatus zeigt SRT-Listener, eigene Publish-Berechtigung und Konsistenz der gespeicherten Zugangsdaten, ohne Passwörter auszugeben. Die Passwort-Ausblendung der MediaMTX-Control-API wird berücksichtigt.
- Zusätzlicher echter SRT-Medientest und Anleitung für OBS-Verbindungsabbrüche durch parallel fehlschlagende SRT-Eingangsquellen.

## 1.1.0-rc.2

- Wiederaufsetzen nach Datenverlust über `--mode attach --recover` oder `--mode update --recover`: neue Datenbank und Administrator, ohne eine vorhandene Datenbank zu überschreiben.
- Verbliebene Daten einschließlich Schlüssel, Medien und SQLite-Journaldateien bleiben in einem separaten Ordner erhalten; bei einem Fehler werden sie zurückgeschoben.
- Verwaiste eigene MediaMTX-Pfade und Konten werden nach Sicherung ersetzt. Fremde Pfade, Konten, MediaMTX-Binary und dessen Unit bleiben erhalten. Laufzeitbereinigung ist auf nachgewiesene eigene alte Pfade begrenzt.
- Installationsreste ohne Datenbank führen zu einer passenden Wiederherstellungsmeldung statt zur widersprüchlichen Empfehlung eines normalen Updates.
- Updates übernehmen den gespeicherten Datenordner und bei neuen Installationen den Programmordner; bei fehlenden Schlüsseln wird statt der Erzeugung unpassender Ersatzschlüssel abgebrochen.
- UI-Dienst vor dem Konfigurations-/Datenbankbackup stoppen; bei fehlgeschlagener Sicherung den vorher laufenden Dienst wieder starten.

## 1.1.0-rc.1

- Expertenmodus pro Anmeldung, standardmäßig aus; technische Endpunkte prüfen ihn auch serverseitig. Globale WebRTC-Einstellungen benötigen zusätzlich Administratorrechte.
- Manuelle Quellenwahl mit definiertem Offline-Fallback und Start/Stopp einzelner Streamingziele ohne Änderung der anderen Ausgänge.
- Quellenerkennung korrigiert: Die Stabilitätshistorie aktiver Eingänge bleibt zwischen Engine-Durchläufen erhalten.
- WebRTC-Vorschau über WHEP und Browser-Kamera über WHIP mit authentifiziertem Signalisierungsproxy und Sitzungsbereinigung.
- Native MediaMTX-Aufnahme in fMP4/MPEG-TS, Segmentdauer und Aufbewahrung, privater Download und fMP4-Vorschau; separater Speicherbereich und Abschaltung bei wenig Speicher.
- Widerrufbare persönliche Zuschauer-Links für das Live-Programm über HLS, ohne öffentliche MediaMTX-Pfadberechtigung.
- Persönliches helles/dunkles/System-Theme und größere mobile Bedienelemente unabhängig vom Expertenmodus.
- Installer nimmt das neue Modul und den getrennten Aufnahmebereich mit; bestehende Pfad-Aufnahmeeinstellungen bleiben beim Abgleich erhalten.

## 1.0.0

- Erster allgemein konfigurierbarer Quellcode-Release.
- Installer für lokale vorhandene MediaMTX-Instanzen und gemeinsame Neuinstallation.
- Eigener privater Medien-Namensbereich mit Erhalt fremder Streams und Zugänge.
- Mehrbenutzer-Dashboard, Quellenwahl, Offline-Bibliothek, Text-/Browser-Overlays.
- Manuelle Aufnahmen, Downloads und gekennzeichnete Wiederholungen.
- Multistreaming, unabhängige Twitch-Neuverbindung, Twitch-/YouTube-Chat und Widgets.
- Gespeicherte Auswahl für den nächsten Stream ohne Trennung der Kontofreigaben.
- Generische Dokumentation, Konfigurationsbeispiel, Lizenzhinweise und Prüfungen.
