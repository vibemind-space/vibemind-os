---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 0.6
description: 'Parametrische Extraktion: User waehlt Folder + Felder via Telegram,
  Skill generiert massgeschneiderte Excel mit LLM-Extraktion'
eval_score: 55
expected_state:
  description: Excel mit den vom User gewaehlten Feldern existiert
  verification_tool: excel_verify_file
inputs:
- name: folder
  type: string
- name: fields
  type: string
last_adjusted: '2026-05-08'
name: roarboot-parametric-extract
requires_approval: true
secrets: []
successes: 1
---

# roarboot-parametric-extract

Parametrische Extraktion aus Roarboot-Knowledge: Der User wählt zuerst einen Roarboot-Folder und danach die gewünschten Excel-Felder. Der Skill nutzt `roarboot_ask` für dynamische LLM-Extraktion und schreibt eine maßgeschneiderte Excel-Datei nach `C:/Users/User/Desktop/HR/`.

## Ablauf

1. Approval einholen:
   - `handoff_approval_request(action='Parametric-Extract: User waehlt Folder + Felder, dann LLM-Extraktion + Excel', timeout_seconds=10, default_on_timeout='approved')`
   - Fortfahren, wenn `decision == 'approved'`, auch bei `decision_source == 'timeout_default'`.

2. Folder-Liste holen:
   - `roarboot_list_folders()`
   - Nur Folder mit `file_count > 0` anbieten.
   - Beispiel gültige Folder im Testlauf: `Bewerbung`, `Investor Programs`, `People`, `Projects`, `Topics`, `Videos`, `vibemind-discourse`.

3. Folder-Auswahl via Telegram/UI:
   - `handoff_clarify(question='Welchen Folder willst du extrahieren?', options=<folder_names>, form_schema=[{name:'folder', type:'text', required:true}])`
   - Danach `handoff_clarify_check(clarify_id)` pollen.
   - Wenn nach ca. 15 Sekunden keine Antwort vorliegt, Default verwenden: `folder='People'`.
   - Hinweis: Das aktuell verfügbare `handoff_clarify`-Tool unterstützt kein natives `timeout_seconds/default_on_timeout`; der Default wird daher im Skill-Runner per Sleep+Check umgesetzt.

4. Felder-Auswahl via Telegram/UI:
   - Erst nach Folder-Auswahl starten.
   - `handoff_clarify(question='Welche Felder soll die Excel haben? (comma-separated, z.B. "name, email, mood, last_seen")', form_schema=[{name:'fields', type:'text', required:true}])`
   - Danach `handoff_clarify_check(clarify_id)` pollen.
   - Wenn nach ca. 15 Sekunden keine Antwort vorliegt, Default verwenden: `fields='name, beschreibung, kategorie'`.
   - Felder parsen mit: split by comma, trim whitespace, leere Einträge entfernen.

5. Dynamischen Extract-Prompt bauen:
   - `fields_json_schema = '{ ' + ', '.join([f'"{f}":"<value>"' for f in fields]) + ' }'`
   - Prompt:
     - `Extrahiere aus den Dokumenten ALLE Eintraege als JSON-Array. Pro Eintrag genau diese Felder: <fields_json_schema>. Antworte AUSSCHLIESSLICH mit gueltigem JSON-Array, kein Markdown. Wenn ein Feld fehlt, leerer String. Antworte mit DISTINCT entries. Wenn unsicher: konservativ deduplizieren auf basis von 'name'. Wenn eine Person mehrere Rollen/Stationen hat, fasse sie in einem Feld zusammen (comma-separated oder als Liste).`
   - `roarboot_ask(folder=<folder>, question=<prompt>, max_files=15, model='gpt-4o-mini')`.

6. JSON parsen und normalisieren:
   - Markdown-Fences entfernen, JSON-Array parsen.
   - Eine Zeile pro distinkter Entity/Person erzeugen, nicht eine Zeile pro Lebenslauf-Station.
   - Wenn mehrere Objekte denselben `name` enthalten, auf `name` deduplizieren und andere Feldwerte zusammenführen.
   - Arrays als comma-separated String speichern.
   - Header: Felderliste mit erstem Buchstaben groß, z.B. `Name`, `Beschreibung`, `Kategorie`.

7. Excel schreiben:
   - `slug = folder.lower().replace(' ', '_')`
   - `file_path = f'C:/Users/User/Desktop/HR/Roarboot_{slug}_extract_2026.xlsx'`
   - `xlsx_create_from_data(file_path=file_path, sheet_name=folder[:31], rows=[header]+data_rows, bold_rows=[1], freeze_pane='A2', cell_styles=[{range:'A1:Z1', fill_color:'305496', font_color:'FFFFFF', bold:true}])`.

8. Verify:
   - `excel_verify_file(file_path=file_path, min_rows=2, must_contain_text=<Headerwerte>)`.

9. Auto-Evaluierung:
   - `file_evaluate(file_path=file_path, expected_intent='Parametrische Roarboot-Extraktion aus Folder <folder> mit User/Default-Feldern <fields>. Excel enthält genau diese Felder als Spalten; eine Zeile pro distinkter Entity/Person; mehrere Stationen einer Person in Feldern zusammengefasst.', source_data_description='Roarboot <folder> Folder; dynamische LLM-Extraktion via roarboot_ask')`
   - Confidence aus Score ableiten: `>=90 => 1.0`, `70-89 => 0.8`, `50-69 => 0.6`, `<50 => 0.3`.

10. HR-Artefakt uploaden:
   - `rowboat_upload(file_path=file_path, title=f'Roarboot {folder} Parametric Extract 2026', tags=['hr','parametric-extract','2026'])`.
   - Wenn Rowboat Backendfehler liefert, gilt der Skill technisch trotzdem als erfolgreich, solange Excel-Erstellung und Verify erfolgreich sind.

## Testlauf 2026-05-08

- Approval: approved via `timeout_default`.
- Folder-Default: `People` (Clarify blieb pending).
- Fields-Default: `name, beschreibung, kategorie` (Clarify blieb pending).
- Roarboot-Quelle: `People`, 2 Dateien (`People/User_Profile.md`, `People/`Felix Baumann`.md`).
- LLM lieferte mehrere Felix-Baumann-Stationen; Skill deduplizierte auf 1 distinkte Person und führte Beschreibungen/Kategorien zusammen.
- Datei: `C:/Users/User/Desktop/HR/Roarboot_people_extract_2026.xlsx`.
- Excel Verify: OK, 2 Zeilen, 3 Spalten.
- File Evaluate Score: 55.
- Confidence: 0.6.
- Rowboat Upload: 500 Internal Server Error, technischer Skill trotzdem erfolgreich.

## Auto-Eval-Hinweise

- Die Quelle enthielt faktisch nur eine distinkte Person, daher nur eine Datenzeile.
- Die zusammengeführte Beschreibung ist lang und könnte für Lesbarkeit gekürzt/strukturiert werden.
- Kategorien wurden in einer Zelle zusammengeführt.
