# Scripts

## GitHub Authentication

### Setup

1. Copy `.env.example` to `.env`
2. Add your GitHub PAT from <https://github.com/settings/tokens>
3. Required scopes: `repo`, `read:org`, `workflow`
4. Run the setup script:

```powershell
cd scripts
.\gh_auth_setup.ps1
```

### .env Format

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_DEFAULT_PRIVATE=true
```

**IMPORTANT:** The `.env` file should NEVER be committed!
