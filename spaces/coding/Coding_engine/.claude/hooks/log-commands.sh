#!/bin/bash
# Hook: PostToolUse (Bash)
# Purpose: Log all executed Bash commands with timestamp
# Non-blocking — always exits 0
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
LOG_DIR="$(dirname "$0")"
LOG_FILE="$LOG_DIR/command-log.txt"
if [ -n "$COMMAND" ]; then
  echo "[$TIMESTAMP] $COMMAND" >> "$LOG_FILE"
fi
exit 0
