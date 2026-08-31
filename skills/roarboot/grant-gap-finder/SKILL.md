---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 0.6
description: Cross-references Investor-Grant Fragenkatalog mit allen 115 Roarboot-Projekten
  und schlaegt fuer jede unvollstaendige Frage Quellen + LLM-Vorschlaege vor.
eval_score: 65
expected_state:
  description: Excel mit 6 Gap-Zeilen + LLM-Suggestions existiert
  verification_tool: excel_verify_file
inputs: []
last_adjusted: '2026-05-08T12:01:25+00:00'
name: roarboot-grant-gap-finder
requires_approval: false
successes: 1
---

# roarboot-grant-gap-finder

Cross-Reference Tool: identifiziert Lücken im Investor-Grant-Antrag und
schlägt Antworten aus dem Projekt-Knowledge vor.

## Pipeline

1. Parse Grant-Fragenkatalog (50 Fragen) — Regex auf strukturierte Q&A-Sections
2. Filtere auf nicht-'beantwortet' → 6 Gaps
3. Für jede Gap: keyword-overlap-Score gegen alle 115 Project _overview.md
4. Für die Top-3 actionable Gaps (Score ≥ 2): LLM-Vorschlag via roarboot_ask
5. Excel-Output mit Sheets 'Gaps' + 'Summary'
6. excel_verify + file_evaluate

## Aktuelle Lage (2026-05-08)

- Gesamt-Fragen: 50
- Beantwortet: 44
- Gaps gesamt: 6
- Gaps mit Projekt-Match: 6
- Gaps mit Score ≥ 2: 0
- LLM-Suggestions generiert: 5

## Reproduzierbarkeit

`python scripts/demo_grant_gap_finder.py` — keine Args, deterministisch
für die Search-Phase, LLM-Aufruf nur für Top-3 actionable.
