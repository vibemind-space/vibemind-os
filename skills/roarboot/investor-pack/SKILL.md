---
agents:
- '*'
app: roarboot
attempts: 1
confidence: 1.0
description: Bundles Grant DOCX + Pitch HTML/PDF/PPTX into one investor-ready ZIP
  with SHA256 manifest and reproducibility instructions.
expected_state:
  description: ZIP file with 4 artifacts + README exists
  verification_tool: none
inputs:
- description: Re-run all upstream skills first
  name: regenerate
  type: boolean
- name: theme
  type: string
last_adjusted: '2026-05-11T17:55:41+00:00'
name: roarboot-investor-pack
requires_approval: false
successes: 1
---

# roarboot-investor-pack

One-shot bundler for the four investor-facing artifacts. Combines:
- Grant DOCX (Skill A)
- Pitch HTML (Skill B)
- Pitch PDF (Skill E1)
- Pitch PPTX (Skill D)

## What's inside

```
VibeMind_Investor_Pack_20260511_195541.zip
├── 1_Grant_Application.docx     (42,933B)
├── 2_Pitch_Deck.html            (23,544B)
├── 3_Pitch_Deck.pdf             (5,175,989B)
├── 4_Pitch_Deck.pptx            (4,901,869B)
└── README.md                    (with SHA256 manifest)
```

## Usage

```
python scripts/demo_investor_pack.py                          # bundle existing artifacts
python scripts/demo_investor_pack.py --regenerate             # regen all 4 first
python scripts/demo_investor_pack.py --regenerate --theme sunset
```

## Last bundle (2026-05-11)

- Theme: midnight
- Total ZIP size: 9.3MB
- Output: `C:\Users\User\Desktop\HR\VibeMind_Investor_Pack_20260511_195541.zip`
