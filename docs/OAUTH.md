# Twitch und YouTube

Streamschlüssel und Kontofreigaben sind getrennte Dinge. Streaming per Schlüssel funktioniert ohne OAuth-App. Für Chat, Twitch-Kanalinformationen und YouTube-Sendungsauswahl werden die nachfolgenden Kontofreigaben benötigt. Verbinden bzw. erneutes Verbinden aktiviert keinen bisher abgewählten Streamingausgang.

## Twitch

1. In der [Twitch Developer Console](https://dev.twitch.tv/console/apps) eine **Confidential**-App registrieren.
2. Als Rückrufadresse `https://DEINE-DOMAIN/oauth/twitch/callback` eintragen.
3. Client-ID und Client-Secret unter Administration hinterlegen.
4. Jeder Benutzer verbindet unter Einstellungen sein eigenes Konto.

Angeforderte Berechtigungen: `channel:read:stream_key`, `channel:manage:broadcast`, `user:read:chat`, `user:write:chat`. Bei einer älteren Kontofreigabe ohne Chat-Rechte muss erneut verbunden werden. Vor einer neuen Twitch-Kontofreigabe die Streamingausgänge stoppen; Konten bleiben bei einem normalen Stream-Stopp verbunden.

Der Chat verwendet [EventSub und Twitch API](https://dev.twitch.tv/docs/chat/authenticating/). Nachrichten werden als das verbundene Konto gesendet. Plattformseitige Chatregeln gelten weiter.

## Google / YouTube

1. In [Google Cloud](https://console.cloud.google.com/) ein Projekt anlegen und **YouTube Data API v3** aktivieren.
2. Unter Google Auth Platform den Zustimmungsbildschirm und die Zielgruppe einrichten. Für einen externen Testbetrieb die Google-Konten unter **Zielgruppe / Audience → Testnutzer** hinzufügen.
3. Eine OAuth-Client-ID vom Typ **Webanwendung** erstellen.
4. Exakt `https://DEINE-DOMAIN/oauth/youtube/callback` als autorisierte Weiterleitungsadresse setzen.
5. Den Scope `https://www.googleapis.com/auth/youtube.force-ssl` für die benötigten YouTube-Funktionen vorsehen.
6. Client-ID und Client-Secret unter **Administration → Google-App für YouTube** hinterlegen.
7. Jeder Benutzer verbindet in Einstellungen den gewünschten Kanal. Livestreaming muss für diesen Kanal im YouTube Studio aktiviert sein.
8. Eine eigene Sendung im YouTube Studio vorbereiten. In StreamDesk **YouTube-Sendungen laden**, die Sendung wählen und **Für Chat auswählen** verwenden. **Streamschlüssel übernehmen** übernimmt zusätzlich den zugehörigen Streamschlüssel; hierfür die Ausgänge zuerst stoppen.

Eine YouTube-Kontofreigabe alleine erstellt keinen Streamingausgang. Alternativ jederzeit einen eigenen YouTube-Streamschlüssel über den Ausgangseditor speichern und die Plattform anschließend in der Streaming-Auswahl aktivieren.

### Fehler 403: access_denied

Bei einer App im Testmodus muss die tatsächlich zur Anmeldung verwendete Google-E-Mail-Adresse als Testnutzer eingetragen sein. Ein YouTube-Kanalname ist keine Testnutzer-Adresse. Anschließend den Verbindungsprozess von StreamDesk aus neu beginnen. Auch Organisationsrichtlinien können den Zugriff verhindern. [Google-Fehlerhilfe](https://support.google.com/accounts/answer/16668185)

### Testmodus und dauerhafter Betrieb

Im externen Google-Testmodus laufen die Refresh-Tokens für diese Berechtigung nach sieben Tagen ab. Für dauerhaften Betrieb und weitere Nutzer außerhalb des Testmodus können Veröffentlichung und Google-App-Prüfung erforderlich sein. Google verwaltet API-Kontingente pro Cloud-Projekt.

YouTube-Nachrichten werden über die [offizielle Streaming-Live-Chat-Schnittstelle](https://developers.google.com/youtube/data/live/streaming-live-chat) empfangen. OAuth-Ablauf und Token-Erneuerung entsprechen dem [Web-Server-Verfahren](https://developers.google.com/identity/protocols/oauth2/web-server). Zugriffs- und Refresh-Tokens werden verschlüsselt gespeichert und nicht an Widget-Browser weitergegeben.
