---
agents:
- '*'
app: rowboat
attempts: 1
confidence: 0.6
description: Exportiert Notizen einer Rowboat-Bubble nach Excel
expected_state:
  description: Excel-Datei mit Rowboat-Daten existiert
  verification_tool: excel_verify_file
inputs: []
last_adjusted: '2026-05-08T09:48:00+02:00'
name: rowboat-export-bubble-notes
requires_approval: true
secrets: []
successes: 1
trigger: Rowboat Brain Capability Router Notizen nach Excel exportieren
---

# Skill: rowboat-export-bubble-notes

Exportiert echte Daten aus dem Rowboat-Knowledge-Backend für die Bubble `Brain Capability Router` in eine Excel-Datei.

## Zweck

- Rowboat-Knowledge direkt per `rowboat_search` abfragen.
- Bis zu 10 Treffer als Excel-Zeilen schreiben.
- Datei unter der HR-Konvention speichern: `C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx`.
- Datei per `excel_verify_file` validieren.
- Datei mit `file_evaluate` semantisch prüfen.
- Optional in Rowboat Knowledge hochladen.

## Schritte

1. **Approval einholen**
   - Tool: `handoff_approval_request`
   - Parameter:
     - `action='Lernlauf rowboat-export-bubble-notes: Rowboat-Daten lesen und Excel-Datei unter C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx erzeugen'`
     - `reason='Ich werde eine HR-Excel-Datei schreiben und den Skill persistent speichern; bei Timeout gilt approved.'`
     - `timeout_seconds=90`
     - `default_on_timeout='approved'`
   - Bei `decision != approved`: abbrechen.

2. **Rowboat-Daten holen**
   - Tool: `rowboat_search`
   - Parameter:
     - `query='Brain'`
     - `folder='Brain Capability Router'`
     - `limit=15`
   - Erwartete Struktur:
     - `results[]` mit `{name, source_name, content_excerpt, content_full_length, created_at, _id}`.
   - Rowboat Search dedupliziert automatisch nach `(sourceId, name)` und liefert die neuesten Versionen.

3. **Excel-Zeilen formatieren**
   - Ziel-Datei: `C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx`
   - Sheet: `BrainRouter`
   - Header:
     ```json
     ["Quelle", "Titel", "Inhalt-Auszug", "Laenge", "Erstellt"]
     ```
   - Für die ersten ca. 10 Treffer jeweils:
     - `Quelle = source_name`
     - `Titel = name`
     - `Inhalt-Auszug = content_excerpt[:300]`
     - `Laenge = str(content_full_length)`
     - `Erstellt = created_at[:19]`
   - Alle Zellwerte als Strings normalisieren.

4. **Excel erstellen**
   - Tool: `xlsx_create_from_data`
   - Parameter:
     - `file_path='C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx'`
     - `sheet_name='BrainRouter'`
     - `rows=<header + data_rows>`
     - `bold_rows=[1]`
     - `freeze_pane='A2'`
     - `cell_styles=[{range:'A1:E1', fill_color:'305496', font_color:'FFFFFF', bold:true}]`
     - `overwrite=true`

5. **Excel verifizieren**
   - Tool: `excel_verify_file`
   - Parameter:
     - `file_path='C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx'`
     - `must_contain_text=['Brain']`
     - `min_rows=2`
   - Erfolg nur wenn die Datei existiert, valide ist und mindestens Header + eine Datenzeile enthält.

6. **Auto-Evaluierung**
   - Tool: `file_evaluate`
   - Expected Intent:
     - Excel mit allen tatsächlich von `rowboat_search` zurückgegebenen deduplizierten Treffern aus `Brain Capability Router`; Spalten `Quelle`, `Titel`, `Inhalt-Auszug`, `Laenge`, `Erstellt`.
   - Confidence-Mapping:
     - Score ≥ 90 ⇒ `confidence=1.0`
     - 70-89 ⇒ `confidence=0.8`
     - 50-69 ⇒ `confidence=0.6`
     - <50 ⇒ `confidence=0.3` und `# QUALITY_ISSUES` ergänzen.

7. **HR-Upload in Rowboat**
   - Nach erfolgreichem Save + Verify:
     - `rowboat_upload(file_path=<file>, title='Rowboat BrainRouter Notes Export 2026', tags=['hr','rowboat-export','2026'])`
   - Upload-Fehler sind non-fatal, solange `xlsx_create_from_data` und `excel_verify_file` erfolgreich waren.

## Testlauf 2026-05-08

- Existing-Check: Skill-Search/Qdrant nicht erreichbar, neuer Lernlauf gestartet.
- Approval: approved via timeout default.
- Rowboat Query: `query='Brain'`, `folder='Brain Capability Router'`, `limit=15`.
- Rowboat Treffer: `2` deduplizierte Treffer.
- Datei geschrieben: `C:/Users/User/Desktop/HR/Rowboat_BrainRouter_Notes_2026.xlsx`.
- Excel Verify: erfolgreich (`3` Zeilen, `5` Spalten, Text `Brain` vorhanden).
- Auto-Eval: Score `50`, Confidence `0.6`.
- Rowboat Upload: HTTP 500, non-fatal.

## Beispiel-Daten aus dem Testlauf

| Quelle | Titel | Laenge | Erstellt |
|---|---|---:|---|
| VibeMind - Projekt:Brain Capability Router | [Projekt] Brain Capability Router | 192 | 2026-05-04T06:55:13 |
| VibeMind - Brain Capability Router | Brain Capability Router - Overview | 3169 | 2026-05-06T11:31:47 |
