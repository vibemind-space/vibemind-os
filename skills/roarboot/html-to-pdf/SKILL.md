---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 1.0
description: Renders an HTML pitch deck as a landscape A4 PDF via Playwright print-to-pdf,
  one page per slide.
expected_state:
  description: PDF with one page per HTML slide exists
  verification_tool: none
inputs:
- name: html
  type: string
- name: pdf
  type: string
last_adjusted: '2026-05-11T17:55:32+00:00'
name: roarboot-html-to-pdf
requires_approval: false
successes: 1
---

# roarboot-html-to-pdf

Renders the same HTML deck as a PDF for archival/email/print. Uses
Playwright's native print-to-pdf with custom @page CSS so each `.slide`
becomes exactly one landscape page.

## Pipeline

1. Find newest `VibeMind_Pitch_*.html` in HR/
2. Inject print CSS: `@page` 297mm x 167mm landscape, `.slide` -> page-break-after
3. Playwright `page.pdf()` -> PDF

## Last run (2026-05-11)

- Source: VibeMind_Pitch_midnight_20260511_195426.html
- Target: VibeMind_Pitch_midnight_20260511_195426.pdf
- Size: 5175989B

## Usage

```
python scripts/demo_html_to_pdf.py
python scripts/demo_html_to_pdf.py --html <path> --pdf <out>
```
