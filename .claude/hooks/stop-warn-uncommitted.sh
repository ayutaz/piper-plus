#!/usr/bin/env bash
# Stop hook: warn Claude once if there are uncommitted changes.
#
# Returns decision=block with a reminder so Claude can decide whether to
# commit, stash, or proceed. The stop_hook_active check prevents infinite
# loops if Claude continues into a second turn.

set -uo pipefail

INPUT=$(cat)

# Extract a JSON field from $INPUT. Prefers jq for speed; falls back to Python.
extract_field() {
  local field="$1"
  local default="$2"
  local result=""
  if command -v jq >/dev/null 2>&1; then
    result=$(printf '%s' "$INPUT" | jq -r ".${field} // empty" 2>/dev/null)
  elif command -v python >/dev/null 2>&1; then
    result=$(printf '%s' "$INPUT" | python -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for k in sys.argv[1].split("."):
        if not isinstance(d, dict):
            d = None
            break
        d = d.get(k)
    if d is None:
        print("")
    elif isinstance(d, bool):
        print("true" if d else "false")
    else:
        print(d)
except Exception:
    pass
' "$field" 2>/dev/null)
  fi
  if [ -z "$result" ]; then
    printf '%s' "$default"
  else
    printf '%s' "$result"
  fi
}

# Avoid infinite loop: if this hook already fired in the current stop
# sequence, do nothing on the second pass.
STOP_ACTIVE=$(extract_field "stop_hook_active" "false")
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Only run inside a git repository
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

# Get a short list of modified/added/deleted files
CHANGED=$(git status --porcelain 2>/dev/null | head -5 || true)
TOTAL=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ' || echo "0")

if [ -z "$CHANGED" ]; then
  exit 0
fi

# Build a friendly multi-line message
MSG="未コミット変更が ${TOTAL} 件あります:"$'\n'"${CHANGED}"
if [ "$TOTAL" -gt 5 ]; then
  MSG="${MSG}"$'\n'"... (合計 ${TOTAL} 件、最初の 5 件のみ表示)"
fi
MSG="${MSG}"$'\n\n'"必要なら /commit skill でコミット、または \`git stash\` で退避してください。"

if command -v jq >/dev/null 2>&1; then
  jq -n --arg reason "$MSG" '{ decision: "block", reason: $reason }'
elif command -v python >/dev/null 2>&1; then
  python -c '
import json, sys
print(json.dumps({"decision": "block", "reason": sys.argv[1]}))
' "$MSG"
fi
exit 0
