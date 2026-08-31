---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 0.6
description: Excel-Portfolio-Dashboard aller Roarboot-Projekte (regex-parsed _overview.md,
  kein LLM noetig fuer Daten)
eval_score: 65
expected_state:
  description: Excel mit 115 Projekten existiert
  verification_tool: excel_verify_file
inputs: []
last_adjusted: '2026-05-08T11:58:46+00:00'
name: roarboot-project-portfolio
requires_approval: false
successes: 1
---

# roarboot-project-portfolio

Liest alle `_overview.md`-Dateien unter `~/.rowboat/knowledge/Projects/` und erzeugt
ein Excel-Portfolio-Dashboard. Direkter Python-Pfad — der Coordinator-LLM-Loop
hängt bei 115+ Files (zu viele tokens), deshalb regex-parsing + openpyxl direkt.

## Schritte

1. Glob `~/.rowboat/knowledge/Projects/*/_overview.md` -> 115 Files
2. Pro File regex-parse: `Type`, `Status`, `Started`, `Summary`, Ideen-Count, Open-Items-Count
3. Sub-Pages-Count = Anzahl `.md` im Folder ausser `_overview.md`
4. Build Excel: Sheet 'Projekte' (eine Zeile pro Projekt) + 'Status-Summary' (Aggregate)
5. excel_verify_file + file_evaluate
6. SKILL.md persistieren

## Aktuelle Datenlage (2026-05-08)

- Gesamt: **115** Projekte
- Active: **115**
- Mit Ideen (>0): 38
- Mit Open-Items (>0): 0
- Mit Sub-Pages (>0): 38
- Total Ideen: 323
- Avg Ideen pro Projekt: 2.8

## Reproduzierbarkeit

`python scripts/demo_project_portfolio.py` — keine Args nötig, kein LLM-Roundtrip,
deterministisch. Tool-Calls intern: `_xlsx_create_from_data`, `_excel_verify_file`,
`_file_evaluate`.
