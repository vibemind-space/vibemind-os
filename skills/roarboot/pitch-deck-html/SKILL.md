---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 1.0
description: Generates a self-contained HTML pitch deck from real Roarboot Project
  + Grant data. 6 slides with theme, scroll-snap, no JS dependencies.
expected_state:
  description: HTML pitch deck exists
  verification_tool: none
inputs:
- name: theme
  type: string
- name: sections
  type: string
last_adjusted: '2026-05-11T17:54:26+00:00'
name: roarboot-pitch-deck-html
requires_approval: false
successes: 1
---

# roarboot-pitch-deck-html

Self-contained HTML pitch deck. Reads real data from:
- 115 Roarboot Project _overview.md
- AI Nation Grant Fragenkatalog status

## Slides (14)

- cover
- problem
- market
- why_now
- traction
- partners
- metrics
- top_projects
- competition
- gtm
- team
- funding
- ask
- contact

## Themes

midnight, emerald, crimson, arctic, obsidian, sunset

## Reproducibility

```
python scripts/demo_pitch_html.py                    # default midnight
python scripts/demo_pitch_html.py --theme emerald
python scripts/demo_pitch_html.py --interactive       # ask user via Telegram
```

## Latest run (2026-05-11)

- Theme: midnight
- Projects: 116
- Grant progress: 47/53 (89%)
- Output: C:\Users\User\Desktop\HR\VibeMind_Pitch_midnight_20260511_195426.html
