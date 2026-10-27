# BUILD D: Plattform und Oberfläche

## Sprache

Angemeldete Benutzer wählen unter Einstellungen Deutsch oder Englisch. Die zentrale Browser-Schicht `static/i18n.js` übersetzt markierte Oberflächentexte über stabile Schlüssel. Nicht markierte ältere Detailtexte bleiben vorerst deutsch; API-Fehler sind weiterhin deutsch, damit bestehende Clients und Tests kompatibel bleiben.

## Szenen und Browser-Compositor

Unter **Expertenmodus → Quellen & Routing** speichert eine Szene eine eindeutige Quellenliste, ein optionales eigenes Offline-/Overlay-Video und eine Liste vorhandener Ausgänge. Speichern und Anwenden benötigen auch serverseitig den Expertenmodus. Anwenden ist nur bei gestoppten Ausgängen möglich; eine Aufnahme darf dadurch ihre Programmzuordnung nicht verlieren. Entfernte Quellen, Ziele oder Mediendateien führen zu einem Konflikt statt zu einer teilweise angewendeten Szene.

Der Browser-Compositor kann nun nicht nur das Offline-Video, sondern auch das aktuell gewählte Live-Programm als Eingang verwenden. URL-Prüfung, DNS-Pinning, privater Renderer-Benutzer und Kapazitätsgrenze bleiben aktiv.

## Rollen

Es gibt `user`, `moderator` und `admin`. Ein Moderator wird in der Administration einem anderen aktiven normalen oder administrativen Konto zugewiesen. Seine Sitzung darf serverseitig die Chat-Seite, Chat-Lesen/-Senden, den eigenen Passwortwechsel und Abmelden verwenden. Ein versteckter UI-Link erweitert diese Policy nicht. Eigene Medienzugänge werden beim Wechsel zur Moderation deaktiviert, Weiterleitungen und Aufnahmen gestoppt und offene eigene Automationen abgeschaltet.

Rollenänderungen erhöhen die Sitzungs-Version und melden das geänderte Konto aus. Das eigene Administratorkonto kann nicht herabgestuft werden.

## Passkeys und Recovery-Codes

Passkeys werden mit `py_webauthn` anhand des vollständigen Attestation-Objekts bzw. der signierten Anmeldeantwort geprüft. Origin, RP-ID, Challenge, lokale Benutzerbestätigung und Signaturzähler werden validiert. Neue Geräte benötigen Benutzerverifikation, etwa PIN oder Biometrie. Herausforderungen liegen fünf Minuten in SQLite und werden vor der Prüfung atomar verbraucht; das Wiederverwenden eines alten Sitzungscookies ermöglicht keine erneute Anmeldung mit derselben Antwort. Registrierung und Anmeldung benötigen HTTPS; `localhost` ist für lokale Browsertests zulässig. Alte gespeicherte ES256-/RS256-Schlüssel bleiben verwendbar, wenn sie Benutzerverifikation liefern.

Beim Registrieren werden zehn neue Einmal-Recovery-Codes angezeigt. Sie ersetzen vorherige Codes, liegen nur als an die Installation gebundene SHA-256-Werte in der Datenbank und werden atomar als benutzt markiert.
Passkey-Anfragen und Recovery-Anmeldungen teilen sich ein Limit von zehn Versuchen je IP und Benutzer innerhalb von fünf Minuten. Passkeys sind eine alternative Anmeldung und kein zusätzlicher zweiter Faktor zur Passwortanmeldung.

## Discord

Pro Benutzer kann unter **Expertenmodus → Discord-Bot** ein Discord-Bot mit Textkanal-ID verbunden werden. Dort steht die Einrichtung Schritt für Schritt; eine Kopie liegt unter [Discord-Einrichtung](DISCORD.md). Einrichten, Verbindungsstatus und Trennen benötigen auch serverseitig den Expertenmodus. Bereits verbundener Chat bleibt nach Ausschalten des Modus verfügbar.

Der Token wird mit dem Installationsschlüssel verschlüsselt und nie an den Browser zurückgegeben. Der Adapter liest im Bedarfsfall alle drei Sekunden neue Nachrichten und kann Nachrichten idempotent mit Discord-Nonce senden. Der Bot benötigt im gewählten Kanal Lesen, Nachrichtenverlauf und Schreiben sowie den aktivierten Message Content Intent im Developer Portal.
Die Kennung für Discord wird tenantbezogen auf 24 Zeichen abgeleitet, um dessen [Nachrichten-API-Grenze](https://docs.discord.com/developers/resources/message#create-message) einzuhalten. Der Lesecursor schreitet auch bei Bot-/Systemnachrichten fort.

## Twitch-Zeitplan

Der Automations-Endpunkt akzeptiert zusätzlich `twitch_start`. Der Payload benötigt `title` und kann `game_id` enthalten. Zum Ausführungszeitpunkt wird zuerst die Twitch-Kanalinformation gesetzt und anschließend ausschließlich der Twitch-Ausgang gestartet. Fehlgeschlagene API-Aufrufe markieren den Auftrag als Fehler.
