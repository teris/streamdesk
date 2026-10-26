# OBS und SRT-Verbindungsprobleme

Unter **Quellen → Verbindungsdaten für OBS und Handy** die aktuellen Daten anzeigen. Nach einem Wiederaufsetzen ändern sich die Medienzugangsdaten; gespeicherte Encoder-Adressen entsprechend ersetzen.

## OBS als SRT-Sender

1. In OBS **Einstellungen → Stream → Dienst: Benutzerdefiniert** wählen.
2. Die **vollständige SRT-Adresse** aus StreamDesk als Serveradresse übernehmen.
3. Das Feld **Streamschlüssel leer lassen**. Die Publish-Berechtigung steht bereits in der Stream-ID innerhalb der Adresse.
4. Für die bestehende Programm-Pipeline H.264 und AAC verwenden. Die neue Vorlage setzt ausdrücklich `mode=caller`, `latency=1000000` (eine Sekunde) und `pkt_size=1316`.

Apps mit getrennten Feldern erhalten stattdessen die SRT-Serveradresse ohne Query und die separat angezeigte Stream-ID. Dabei Caller-Modus und 1000 ms Latenz einstellen. Eine SRT-Verschlüsselungs-Passphrase ist eine zusätzliche, davon unabhängige Einstellung; nur verwenden, wenn sie auf dem Server tatsächlich konfiguriert ist.

Referenzen: [OBS-SRT-Anleitung](https://obsproject.com/kb/srt-protocol-streaming-guide), [MediaMTX-SRT](https://mediamtx.org/docs/publish/srt).

## Verbindung steht kurz und endet wieder

Im Serverprotokoll bedeutet „is publishing to path“ mit H.264/AAC, dass Verbindung, Authentifizierung und Track-Erkennung zunächst funktioniert haben. Ein späteres `EOF` benennt allein noch nicht den Auslöser. Die anschließende Meldung der Vorschau, dass kein Stream verfügbar ist, kann eine Folge des bereits beendeten Eingangs sein.

Bei OBS zusätzlich das aktuelle Protokoll unter `%APPDATA%\obs-studio\logs` prüfen. Die Meldung `All sockets removed from epoll, waiting would deadlock` kommt aus der lokalen SRT-Verarbeitung des Encoders. Falls gleichzeitig eine SRT-Medienquelle wiederholt erfolglos verbindet, diese Eingangsquelle prüfen. In deren Eigenschaften **Datei schließen, wenn inaktiv** aktivieren, sofern sie unbenutzt nicht weiter verbinden soll. Eine inaktive oder nicht sichtbare Quelle kann sonst weiter Verbindungsversuche unternehmen. Der [OBS-Quellcode](https://github.com/obsproject/obs-studio/blob/33.0.0/plugins/obs-ffmpeg/obs-ffmpeg-source.c) zeigt diese Abhängigkeit der Wiederverbindung von der Inaktivitätsoption.

In einem praktisch geprüften OBS-33-Fall liefen SRT-Ausgang und Empfang am Server nach dieser Einstellung stabil weiter. Die Option ist eine Maßnahme bei diesem konkreten Fehlerbild; sie ersetzt keine Diagnose anderer Codec-, Netzwerk- oder Encoderfehler. Quellen, die auch bei Nichtbenutzung empfangen sollen, entsprechend getrennt betreiben.

Unter **Expertenmodus → Protokolle & WebRTC** zeigt StreamDesk zusätzlich den SRT-Listener und die eigene Publish-Berechtigung. Passwörter werden über die Control API ausgeblendet; die Konsistenzprüfung der Zugangsdaten verwendet deshalb die lokale gespeicherte Konfiguration. Der Status ist kein externer UDP-Erreichbarkeitstest.
