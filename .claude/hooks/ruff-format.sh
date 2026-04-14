#!/usr/bin/env bash
# PostToolUse hook: auto-format Python files after Claude edits them.
#
# Reads the tool input from stdin (JSON via Claude Code hooks contract),
# extracts the edited file path, and runs ruff format + check --fix on it.
#
# Only Python files under recognized piper-plus source directories are
# processed. All errors are silenced because PostToolUse cannot block
# the original tool result anyway, and we don't want the hook itself
# to fail the workflow.

set -uo pipefail

# Read JSON payload from stdin (Claude Code hooks contract)
INPUT=$(cat)

# Extract a JSON field from $INPUT. Prefers jq for speed; falls back to Python
# (which is always available in piper-plus dev environments).
extract_field() {
  local field="$1"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$INPUT" | jq -r ".${field} // empty" 2>/dev/null
  elif command -v python >/dev/null 2>&1; then
    printf '%s' "$INPUT" | python -c '
import json, sys
try:
    d = json.load(sys.stdin)
    for k in sys.argv[1].split("."):
        if not isinstance(d, dict):
            d = None
            break
        d = d.get(k)
    print(d if d is not None else "")
except Exception:
    pass
' "$field" 2>/dev/null
  fi
}

# Extract the edited file path
FILE=$(extract_field "tool_input.file_path")

# Bail out early if no file path or not a Python file
case "$FILE" in
  "") exit 0 ;;
  *.py) ;;
  *) exit 0 ;;
esac

# Only process files inside known piper-plus Python source trees.
# Match both repository-relative paths (e.g. src/python_run/foo.py)
# and absolute or parent-prefixed paths (e.g. /repo/src/python_run/foo.py).
case "$FILE" in
  src/python/*|*/src/python/*|src/python_run/*|*/src/python_run/*|tools/benchmark/*|*/tools/benchmark/*|docker/*|*/docker/*) ;;
  *) exit 0 ;;
esac

# Make sure we run from the project root so uv finds pyproject.toml
cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Run ruff format and ruff check --fix.
# All errors are silenced; we never want the hook to surface noise.
if command -v uv >/dev/null 2>&1; then
  uv run ruff format "$FILE" >/dev/null 2>&1 || true
  uv run ruff check --fix "$FILE" >/dev/null 2>&1 || true
elif command -v ruff >/dev/null 2>&1; then
  ruff format "$FILE" >/dev/null 2>&1 || true
  ruff check --fix "$FILE" >/dev/null 2>&1 || true
fi

exit 0
