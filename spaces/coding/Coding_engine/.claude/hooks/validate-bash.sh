#!/bin/bash
# Hook: PreToolUse (Bash)
# Purpose: Block dangerous shell commands
# Exit 0 = allow, Exit 2 = deny
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
if [ -z "$COMMAND" ]; then
  exit 0
fi
# Block force push
if echo "$COMMAND" | grep -qiE "git\s+push\s+.*--force|git\s+push\s+-f\b"; then
  echo "BLOCKED: Force push is dangerous. Use 'git push --force-with-lease' or ask explicitly." >&2
  exit 2
fi
# Block hard reset
if echo "$COMMAND" | grep -qiE "git\s+reset\s+--hard"; then
  echo "BLOCKED: git reset --hard destroys uncommitted work. Confirm with user first." >&2
  exit 2
fi
# Block recursive delete of root or home
if echo "$COMMAND" | grep -qiE "rm\s+-rf\s+/\s|rm\s+-rf\s+~|rmdir\s+/s\s+/q\s+[A-Z]:\\\\$"; then
  echo "BLOCKED: Recursive delete of root/home directory." >&2
  exit 2
fi
# Block DROP TABLE / DROP DATABASE
if echo "$COMMAND" | grep -qiE "DROP\s+(TABLE|DATABASE|SCHEMA)\s"; then
  echo "BLOCKED: SQL DROP operations require explicit user confirmation." >&2
  exit 2
fi
# Block credential exposure
if echo "$COMMAND" | grep -qiE "cat\s+.*\.env\b|type\s+.*\.env\b|echo\s+.*\\\$(API_KEY|SECRET|TOKEN|PASSWORD)"; then
  echo "BLOCKED: Potential credential exposure in command." >&2
  exit 2
fi
exit 0
