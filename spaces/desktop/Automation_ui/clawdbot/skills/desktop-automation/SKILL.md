---
name: desktop-automation
description: Control desktop automation via the Automation_ui backend
user-invocable: true
homepage: http://localhost:8007
---

# Desktop Automation Skill

Du kannst den Desktop des Benutzers fernsteuern. Nutze das `desktop_automation` Tool für alle Automatisierungsaufgaben.

## Verfügbare Aktionen

### Apps & URLs öffnen
- `desktop_automation({ command: "öffne chrome" })` - Browser öffnen
- `desktop_automation({ command: "öffne google.com" })` - Website öffnen
- `desktop_automation({ command: "öffne notepad" })` - App öffnen

### Maus & Klicks
- `desktop_automation({ command: "klick auf Anmelden" })` - Auf Element klicken
- `desktop_automation({ command: "scrolle nach unten" })` - Scrollen

### Tastatur & Eingabe
- `desktop_automation({ command: "tippe Hallo Welt" })` - Text eingeben
- `desktop_automation({ command: "drücke strg+c" })` - Tastenkombination
- `desktop_automation({ command: "drücke enter" })` - Einzelne Taste

### Screenshot & OCR
- `desktop_automation({ command: "screenshot" })` - Screenshot aufnehmen
- `desktop_automation({ command: "lesen" })` - Bildschirmtext per OCR lesen

## Schnellbefehle

Der Benutzer kann auch direkt Befehle schreiben:
- `/screenshot` - Screenshot senden
- `/ocr` oder `/lesen` - Bildschirmtext lesen
- `/automation-status` - Status prüfen

## Beispiel-Workflows

### Website besuchen und suchen
```
1. öffne chrome
2. warte kurz
3. tippe anthropic.com
4. drücke enter
5. warte kurz
6. screenshot
```

### Dokument speichern
```
1. drücke strg+s
```

### Fenster wechseln
```
1. drücke alt+tab
```

## Hinweise

- Befehle funktionieren auf Deutsch und Englisch
- Bei komplexen Aufgaben: schrittweise vorgehen
- Nach URL-Öffnung kurz warten (Seitenladung)
- Screenshot zur Bestätigung senden
