# Discord-Bot mit StreamDesk verbinden

Ab 1.1.5 liegt die Einrichtung unter **Expertenmodus → Discord-Bot**. Dort sind Verbindung und Anleitung zusammen erreichbar. Jeder Benutzer verbindet seinen eigenen Bot und Textkanal. Der bereits eingerichtete Chat bleibt unter **Chat & Widget** auch bei ausgeschaltetem Expertenmodus nutzbar.

## 1. App und Bot erstellen

Öffne das [Discord Developer Portal](https://discord.com/developers/applications), wähle **New Application** und gib der App einen Namen. Auf der Seite **Bot** erzeugst du mit **Reset Token** einen Token. Diesen benötigst du für das StreamDesk-Formular; nach dem Speichern zeigt StreamDesk ihn nicht mehr an.

Aktiviere auf derselben Seite unter **Privileged Gateway Intents** den **Message Content Intent** und speichere. Ohne diese Freigabe kann Discord normale Kanalnachrichten ohne Text liefern, auch bei Abruf über die HTTP-API. Verifizierte Apps benötigen gegebenenfalls eine zusätzliche Freigabe. Siehe [Discord: Message Content Intent](https://docs.discord.com/developers/events/gateway#message-content-intent).

## 2. Bot auf den Server einladen

Aktiviere unter **Installation** den Kontext **Guild Install**. Wähle **Discord Provided Link**, den Scope **bot** und die Berechtigungen **View Channels**, **Read Message History** und **Send Messages**. Öffne den Installationslink und wähle deinen Discord-Server. Dein Discord-Konto benötigt dort die Berechtigung zum Hinzufügen von Apps. Siehe [Discord: App und Installation](https://docs.discord.com/developers/quick-start/getting-started).

Die Bot-Rolle muss diese Rechte auch im gewünschten Textkanal haben, insbesondere bei privaten Kanälen.

## 3. Kanal-ID kopieren

Schalte in Discord unter **Benutzereinstellungen → Erweitert** den **Entwicklermodus** ein. Klicke mit der rechten Maustaste auf den gewünschten Textkanal und wähle **Kanal-ID kopieren**. Benötigt wird die lange Zahl, nicht der Kanalname und nicht die Server-ID. Siehe [Discord: IDs finden](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID).

## 4. In StreamDesk speichern

Aktiviere deinen Expertenmodus und öffne **Discord-Bot**. Trage Kanal-ID und Bot-Token ein und wähle **Discord verbinden**. StreamDesk prüft den Kanalzugriff und speichert den Token mit dem Installationsschlüssel verschlüsselt. Die Statusabfrage gibt ausschließlich deine Kanal-ID, den Kanalnamen und den Verbindungsstatus zurück.

## 5. Chat und Widget verwenden

Öffne **Chat & Widget**, wähle Discord als Chat und bei Bedarf als Sendeziel. Für ein OBS-Widget kannst du dort einen Widget-Link mit Discord als Plattform erzeugen. Zum Trennen oder Austauschen des Bots öffnest du erneut **Expertenmodus → Discord-Bot**.

## Wenn die Verbindung nicht funktioniert

- **Kanal nicht gefunden:** Kanal-ID, Einladung und Kanalrechte prüfen.
- **Nachrichten ohne Text:** Message Content Intent im Developer Portal kontrollieren.
- **Token ungültig:** Unter **Bot → Reset Token** neu erzeugen und in StreamDesk erneut speichern.
- **Bot wird als offline angezeigt:** StreamDesk verwendet die Discord-HTTP-API. Eine grüne Online-Anzeige des Bots ist für diese Verbindung nicht erforderlich.
