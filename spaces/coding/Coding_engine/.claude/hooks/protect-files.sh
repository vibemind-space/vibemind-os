#!/bin/bash
# Hook: PreToolUse (Edit|Write)
# Purpose: Block edits to sensitive files (.env, credentials, keys)
# Exit 0 = allow, Exit 2 = deny
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path','') or d.get('tool_input',{}).get('filePath',''))" 2>/dev/null)
if [ -z "$FILE_PATH" ]; then
  exit 0
fi
BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
  .env|.env.*|.env.local|.env.production|.env.staging)
    echo "BLOCKED: Cannot edit environment file '$BASENAME'. Edit .env.example instead." >&2
    exit 2
    ;;
  credentials.json|.credentials.json|service-account.json)
    echo "BLOCKED: Cannot edit credentials file '$BASENAME'." >&2
    exit 2
    ;;
  *.pem|*.key|*.p12|*.pfx|*.jks)
    echo "BLOCKED: Cannot edit certificate/key file '$BASENAME'." >&2
    exit 2
    ;;
  id_rsa|id_ed25519|id_ecdsa)
    echo "BLOCKED: Cannot edit SSH key '$BASENAME'." >&2
    exit 2
    ;;
esac
case "$FILE_PATH" in
  */.ssh/*)
    echo "BLOCKED: Cannot edit files in .ssh directory." >&2
    exit 2
    ;;
  */.aws/*)
    echo "BLOCKED: Cannot edit AWS credentials." >&2
    exit 2
    ;;
esac
exit 0
