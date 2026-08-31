---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 1.0
description: Converts a scroll-snap HTML pitch deck (Skill B output) to PowerPoint
  by screenshotting each slide via headless Playwright at 1920x1080 and embedding
  as full-bleed images.
expected_state:
  description: PPTX with one slide per HTML section exists
  verification_tool: none
inputs:
- name: html
  type: string
- name: pptx
  type: string
last_adjusted: '2026-05-11T17:55:41+00:00'
name: roarboot-html-to-pptx
requires_approval: false
successes: 1
---

# roarboot-html-to-pptx

Converts an HTML pitch deck (Skill B output) into a PowerPoint deck where
each slide is a full-bleed screenshot. The HTML stays the source of truth,
PPTX is a derived artifact for tools that need PowerPoint format.

## Pipeline

1. Find newest `VibeMind_Pitch_*.html` in `C:/Users/User/Desktop/HR/`
2. Headless Playwright opens HTML at 1920x1080, disables scroll-snap CSS
3. For each `<section class="slide">`, scroll into view + screenshot
4. python-pptx builds a 16:9 deck with one slide per image

## Last run (2026-05-11)

- Source: VibeMind_Pitch_midnight_20260511_195426.html
- Target: VibeMind_Pitch_midnight_20260511_195426.pptx
- Slides: 14
- Resolution: 1920x1080

## Reproducibility

```
python scripts/demo_html_to_pptx.py
python scripts/demo_html_to_pptx.py --html <path> --pptx <out>
```
