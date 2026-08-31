---
agents:
- '*'
app: git
attempts: 0
confidence: 1.0
description: Erstellt ein neues GitHub-Repository für ein bestehendes Coding-Projekt
  und pusht den lokalen main-Branch hoch. Liest den code_path aus dem Projekt-Manifest
  (.rowboat/knowledge/Coding-Projects/<slug>.md) und aktualisiert das Manifest mit
  der neuen Remote-URL.
inputs:
- name: slug
  type: string
  required: true
- name: visibility
  type: string
  default: private
- name: description
  type: string
  required: false
expected_state:
  description: GitHub-Repo existiert unter dem Account des authentifizierten gh-Users,
    enthält den initial commit, und das Manifest .rowboat/knowledge/Coding-Projects/<slug>.md
    hat den git.remote-Eintrag mit der neuen URL.
  verification_tool: shell_exec
name: github-create-repo
requires_approval: false
successes: 0
last_adjusted: null
---

## Wann diesen Skill nutzen

Wenn der User sagt:
- "push <projekt> auf github"
- "erstell ein github repo für <projekt>"
- "github create <projekt>"
- "veröffentliche <projekt> auf github"

## Voraussetzungen

- `gh` CLI ist installiert und authentifiziert. Check vorab: `gh auth status`
- Das Projekt wurde mit `/project-bootstrap` angelegt (Manifest existiert, lokaler git-Repo vorhanden)

## Schritte

1. **Slug ermitteln**: aus dem User-Prompt extrahieren (z.B. "github create test-bootstrap" → slug=`test-bootstrap`). Wenn unklar, ruf `python scripts/project_resolver.py --list` auf und zeig dem User die Optionen.

2. **Visibility klären**: Default ist `private`. Wenn der User "öffentlich" oder "public" sagt, dann `--visibility public`.

3. **Beschreibung extrahieren** (optional): wenn der User eine Repo-Description gegeben hat (z.B. "...mit beschreibung 'foo'"), nimm sie. Sonst leer lassen.

4. **Owner ermitteln** (VibeMind-Account vs persönlich):
   - **Default für VibeMind-Coding-Projekte**: `--owner vibemind-os` (sofern der Account eingerichtet ist)
   - Persönliche Projekte: `--owner` weglassen (nutzt aktiven gh-User)
   - Wenn User explizit eine Org/Account nennt ("unter foo"): `--owner foo`
   - Das Skript handhabt `gh auth switch` automatisch zwischen Accounts

5. **Skript aufrufen**:
   ```bash
   python scripts/github_create_repo.py --slug <slug> --visibility <private|public> [--owner <user-or-org>] [--description "..."]
   ```

5. **Output verifizieren**: das Skript gibt JSON zurück mit `repo_url`. Wenn `manifest_updated: true`, ist alles ok. Sag dem User die neue Repo-URL.

## Fehlerbehandlung

- `manifest not found`: der Slug existiert nicht. Liste die bekannten Projekte mit `python scripts/project_resolver.py --list`.
- `gh repo create failed`: meistens Auth-Problem oder Repo existiert schon unter dem Namen. Zeig dem User den stderr und schlag `--repo-name <anderer-name>` vor.
- `'<slug>' already has a remote`: das Projekt ist schon auf GitHub. Frag den User ob er die URL haben will oder mit `--force` überschreiben.

## Verifikation

Nach erfolgreichem Lauf, der User kann checken:
```bash
gh repo view <slug>           # zeigt die GitHub-Seite
cat C:/Users/User/.rowboat/knowledge/Coding-Projects/<slug>.md | head -20   # zeigt das aktualisierte Manifest
```
