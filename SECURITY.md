# Sicherheit

Geheimnisse, Datenbanken, private Widget-Links und vollständige Konfigurationsdateien nicht in öffentliche Issues oder Pull Requests einfügen. Fehlerberichte müssen Streamschlüssel, OAuth-Zugriffs-/Refresh-Tokens, Client-Secrets und Benutzerpasswörter entfernen.

Bitte eine mögliche Schwachstelle über die privaten Meldewege des jeweiligen Repository-Betreibers melden. Dieses Quellcodepaket hinterlegt absichtlich keine persönliche Kontaktadresse. Wer das Repository veröffentlicht, sollte einen erreichbaren privaten Kontakt oder GitHub Private Vulnerability Reporting einrichten.

Betriebsvoraussetzungen: HTTPS am Reverse Proxy, nicht öffentlich erreichbare Control API, interne MediaMTX-Authentifizierung und ein einzelner StreamDesk-Verwalter für den reservierten Namensbereich. Der UI-Dienst besitzt Schreibzugriff auf Konfiguration und Medien; seine Administration ist entsprechend privilegiert. Browser-Renderer verwenden ein eigenes Systemkonto.

Widget-Links sind geheime Leseberechtigungen. Jeder Besitzer eines Links kann den zugehörigen Chat lesen; ein erneuerter Link macht den alten ungültig. Widgets erhalten keine Plattformtokens und können keine Chatnachrichten senden.
