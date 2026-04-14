#!/usr/bin/env bash
# SessionStart hook: inject env vars and project status into the session.
#
# - Appends piper-plus default environment variables to CLAUDE_ENV_FILE
#   when Claude provides one (used during startup/resume).
# - Reports current branch and HEAD commit + key CLAUDE.md rules so Claude
#   has consistent context regardless of when the session begins.

set -uo pipefail

# Set environment variables for the session if Claude provides an env file
if [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -f "${CLAUDE_ENV_FILE}" ]; then
  {
    echo 'export NCCL_DEBUG=WARN'
    echo 'export NCCL_P2P_DISABLE=1'
    echo 'export NCCL_IB_DISABLE=1'
    echo 'export PYTHONDONTWRITEBYTECODE=1'
  } >> "$CLAUDE_ENV_FILE"
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Gather basic git information
BRANCH="(no-git)"
HEAD=""
DIRTY=""
if git rev-parse --git-dir >/dev/null 2>&1; then
  BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
  HEAD=$(git log -1 --oneline 2>/dev/null || echo "")
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    DIRTY="(未コミット変更あり)"
  fi
fi

CONTEXT="### piper-plus セッション開始
- ブランチ: ${BRANCH} ${DIRTY}
- 直近: ${HEAD}

### CLAUDE.md キールール (要約)
- PR 先は **dev** ブランチ
- \`git commit --no-verify\` / \`--no-gpg-sign\` 禁止
- パッケージ追加は \`uv add\` (\`uv pip install\` 禁止)
- テストは \`uv run pytest\` 経由
- 学習: V100 は \`--precision 32-true\` 必須、\`--no-wavlm\` 推奨
- ファイル編集後は ruff format/check が hook で自動実行されます
"

if command -v jq >/dev/null 2>&1; then
  jq -n --arg ctx "$CONTEXT" '{
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: $ctx
    }
  }'
elif command -v python >/dev/null 2>&1; then
  python -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": sys.argv[1]
    }
}))
' "$CONTEXT"
fi

exit 0
