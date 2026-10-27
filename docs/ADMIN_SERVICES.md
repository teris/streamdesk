# Zentrale Dienstfreigaben

Ab **1.1.6** verwalten Administratoren unter **Administration → Dienste & Freigaben** die für StreamDesk erlaubten Dienste. Die drei aufklappbaren Gruppen zeigen Freigaben und Sperren an. Nur Administratoren dürfen diese Einstellung lesen und ändern; die Verwaltungsseite benötigt keinen Expertenmodus.

Eine Sperre gilt für alle Benutzer einschließlich Administratoren. Auch ein aktivierter Expertenmodus und direkte API-Anfragen erlauben keine Nutzung eines gesperrten Dienstes. Ein Administrator kann die Freigabe wieder aktivieren. Bei bestehenden Installationen sind zunächst alle Dienste freigegeben.

| Gruppe | Freigabe | Wirkung einer Sperre |
| --- | --- | --- |
| Plattformen & Chat | Twitch | Twitch-Ausgänge stoppen; Kontofreigabe, Kanalverwaltung und Chat gesperrt. |
| Plattformen & Chat | YouTube | YouTube-Ausgänge stoppen; Kontofreigabe, Sendungsauswahl und Chat gesperrt. |
| Plattformen & Chat | Eigene Streaming-Anbieter | Fester eigener Anbieter und zusätzliche Custom-Ausgänge stoppen. |
| Plattformen & Chat | Discord-Bot | Einrichtung und Discord-Chat einschließlich Widget gesperrt. |
| Medien | WebRTC | Browser-Kamera und WebRTC-Vorschau gesperrt; bestehende StreamDesk-Sitzungen schließen. |
| Medien | Neue Aufnahmen | Manuelle Aufnahmen abschließen, native Aufnahmen pausieren; neue Aufnahmen gesperrt. |
| Medien | Playback & Clips | Segmentwiedergabe, Clip-Erzeugung und Clip-Verwaltung gesperrt. |
| Medien | Öffentliche Zuschauerlinks | Gespeicherte öffentliche HLS-Links liefern während der Sperre keinen Player und keine Segmente. |
| Erweiterungen | Zusätzliche Quellen & Routing | Zusätzliche Quellen und Ausgänge stilllegen; Routingänderungen und Szenen gesperrt. |
| Erweiterungen | Browser-Overlays | Programme verwenden ihre Quelle ohne das gespeicherte Browser-Overlay. |
| Erweiterungen | Automation & Export | Keine neuen Hooks, Zeitplan-Ausführungen, Exporte oder automatischen Neuverbindungen. |
| Erweiterungen | Benachrichtigungen | Keine neuen Webhook- oder E-Mail-Meldungen. |

## Einstellungen behalten und wiederverwenden

Sperren entfernt keine Benutzerkonten, Streamschlüssel, OAuth-Freigaben, Bot-Tokens, Routingdefinitionen, Zuschauerlinks oder Mediendateien. Die Benutzeroberfläche blendet zugehörige Optionen aus; bereits geöffnete gesperrte Bereiche zeigen einen Hinweis. Andere angemeldete Sitzungen übernehmen Änderungen bei ihrer nächsten Statusabfrage.

Nach Freigabe werden gespeicherte Einstellungen wieder nutzbar. Streaming-Ausgänge und manuelle Aufnahmen werden erneut vom Benutzer gestartet. Native Aufnahmen nehmen ihre zuvor gespeicherte Einstellung wieder an, sobald alle dafür notwendigen Dienste freigegeben sind. Bestehende öffentliche Links sind nach ihrer Freigabe wieder gültig.

Zeitplan-Aufträge bleiben während einer Sperre liegen. Verpasste Termine werden beim Freigeben als Fehler mit dem Hinweis zur erneuten Planung markiert. Zukünftige Termine bleiben eingeplant. Bereits begonnene externe Anfragen können noch zu Ende laufen; neue werden durch die Freigabeprüfung verhindert.

Die private HLS-Programmvorschau, die festen Source 1/2, Benutzerkonten, Passwortwechsel, Darstellung und vorhandene manuelle Aufnahme-Downloads bleiben verfügbar. Dienstsperren ändern ausschließlich StreamDesk-Freigaben und eigene MediaMTX-Pfade/Berechtigungen; fremde Attach-Pfade bleiben erhalten.

## Speicherung und Betriebsstörungen

Die globale Freigabe liegt verschlüsselt in der StreamDesk-Datenbank und übersteht Neustarts und Updates. Das Backup von Datenbank und Installationsschlüssel enthält auch die Freigaben. Fehlende Einträge übernehmen die bisherige Freigabe; ungültige gespeicherte Richtlinien sperren optionale Dienste bis zur Korrektur durch einen Administrator.

Ist MediaMTX beim Ändern einer Freigabe nicht erreichbar, gilt die StreamDesk-Zugriffssperre sofort. Die Administration zeigt den noch ausstehenden Medienserver-Abgleich an; die Engine versucht ihn erneut. Das Beenden von Medienverbindungen benötigt eine erreichbare MediaMTX-Control-API.
