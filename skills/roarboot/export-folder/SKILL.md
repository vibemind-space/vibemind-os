---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 1
description: Exportiert eine Roarboot-Knowledge-Folder nach Excel, fragt den User
  interaktiv welchen Folder
expected_state:
  description: Excel mit Folder-Inhalt existiert
  verification_tool: excel_verify_file
inputs:
- description: Folder-Name (vom User via Telegram-Clarify)
  name: folder
  type: string
last_adjusted: '2026-05-07T12:59:00+02:00'
name: roarboot-export-folder
requires_approval: true
secrets: []
successes: 1
trigger: Roarboot Knowledge Folder interaktiv nach Excel exportieren
---

# roarboot-export-folder

Interaktiver Skill: fragt den User via Telegram/Clarify, welcher Roarboot-Knowledge-Folder exportiert werden soll, liest echte Markdown-Wissensdaten aus `~/.rowboat/knowledge` und erzeugt eine Excel-Datei unter `C:/Users/User/Desktop/HR/`.

## Schritte

1. Approval einholen:
   - `handoff_approval_request(action='Skill roarboot-export-folder: User via Telegram nach Folder fragen, Excel mit echten Daten erstellen', timeout_seconds=90, default_on_timeout='approved')`
2. Verfügbare Roarboot-Folder lesen:
   - `roarboot_list_folders()`
   - Nur Folder mit `file_count > 0` als auswählbar anbieten.
3. User interaktiv fragen:
   - Frage: `Welchen Roarboot-Folder willst du nach Excel exportieren?`
   - Optionen/Enum aus den Folder-Namen mit echten Dateien, z. B. `Bewerbung`, `Investor Programs`, `People`, `Projects`, `Topics`, `Videos`, `vibemind-discourse`.
   - Falls keine Antwort innerhalb des Timeouts kommt, Default `Bewerbung` verwenden.
4. Inhalt lesen:
   - `roarboot_read_knowledge(folder=<gewaehlter_folder>, limit=20)`
5. Excel-Zeilen erstellen:
   - Header: `['Pfad', 'Name', 'Inhalt-Auszug', 'Laenge', 'Geaendert']`
   - Datenzeile je Treffer: `[path, name, content_excerpt[:300], str(content_full_length), modified_at[:19]]`
6. Excel-Datei erzeugen:
   - `file_path = 'C:/Users/User/Desktop/HR/Roarboot_<FolderSlug>_2026.xlsx'`
   - Folder-Slug: Leerzeichen durch `_` ersetzen; nicht-alphanumerische Zeichen entschärfen.
   - `sheet_name = <Folder>` gekürzt auf max. 31 Zeichen.
   - `bold_rows=[1]`
   - `freeze_pane='A2'`
   - `cell_styles=[{'range':'A1:E1','fill_color':'305496','font_color':'FFFFFF','bold':true}]`
7. Datei verifizieren:
   - `excel_verify_file(file_path, must_contain_text=[<Folder>], min_rows=2)`
8. Optional gemäß HR-Konvention hochladen:
   - `rowboat_upload(file_path=file_path, title='Roarboot <Folder> Knowledge Export 2026', tags=['hr','roarboot','2026'])`
   - Wenn Rowboat nicht konfiguriert ist (`skipped: true`), bleibt der Skill erfolgreich, solange Excel-Erstellung und Verifikation OK sind.

## Ergebnis des Lernlaufs

- Gewählter Folder: `Bewerbung` (Default, da keine Telegram-Antwort innerhalb Wartezeit)
- Verfügbare Folder mit Daten: `Bewerbung`, `Investor Programs`, `People`, `Projects`, `Topics`, `Videos`, `vibemind-discourse`
- Gelesene Treffer: 1
- Datei: `C:/Users/User/Desktop/HR/Roarboot_Bewerbung_2026.xlsx`
- Excel-Verifikation: OK, 2 Zeilen inkl. Header, 5 Spalten
- Confidence: 1.0
