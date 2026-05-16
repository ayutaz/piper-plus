#!/usr/bin/env bash
# PreToolUse(Bash) hook: block dangerous commands before execution.
#
# Reads the tool input from stdin and inspects the bash command.
# If the command matches a dangerous pattern, emits a JSON deny
# decision so Claude Code refuses to run it and surfaces the reason.
#
# Patterns are derived from CLAUDE.md rules and piper-plus operational
# safety policy.

set -uo pipefail

INPUT=$(cat)

# Extract a JSON field from $INPUT. Prefers jq for speed; falls back to Python.
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

CMD=$(extract_field "tool_input.command")

if [ -z "$CMD" ]; then
  exit 0
fi

deny() {
  local reason="$1"
  if command -v jq >/dev/null 2>&1; then
    jq -n --arg reason "$reason" '{
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "deny",
        permissionDecisionReason: $reason
      }
    }'
  elif command -v python >/dev/null 2>&1; then
    python -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": sys.argv[1]
    }
}))
' "$reason"
  fi
  exit 0
}

# --- Skip pattern checks for echo/printf/cat-style commands ---------------
# These commands just print text and don't execute the dangerous patterns.
# Without this, developers cannot demonstrate or test the dangerous strings
# (e.g., `echo 'git push --force main'` would be blocked).
case "$CMD" in
  echo\ *|"echo"|printf\ *|"printf"|cat\ *|"cat"|tee\ *|"tee")
    exit 0 ;;
esac

# --- Training data / model protection -------------------------------------
case "$CMD" in
  *"rm -rf /data/piper/output-"*|*"rm -rf /data/piper/dataset-"*)
    deny "本番の学習出力/データセットを削除しようとしています。誤操作防止のため、手動で実行してください。" ;;
  *"rm "*"epoch="*".ckpt"*|*"rm -rf "*"checkpoints/"*)
    deny "チェックポイントファイル/ディレクトリの削除はユーザー確認が必要です。" ;;
esac

# --- Git safety -----------------------------------------------------------
case "$CMD" in
  *"git push"*"--force"*"main"*|*"git push"*"--force"*"master"*)
    deny "main/master への force push は禁止されています。" ;;
  *"git push"*"-f "*"main"*|*"git push"*"-f "*"master"*)
    deny "main/master への force push は禁止されています。" ;;
  *"git push"*"--force-with-lease"*"main"*|*"git push"*"--force-with-lease"*"master"*)
    deny "main/master への force-with-lease push もブロックします。手動で実行してください。" ;;
  *"git reset --hard origin/"*"main"*|*"git reset --hard origin/"*"master"*)
    deny "main/master からの hard reset はユーザー承認が必要です。" ;;
  *"git commit"*"--no-verify"*)
    deny "git commit --no-verify は CLAUDE.md のルールで禁止されています。pre-commit hook の失敗は原因を修正してください。" ;;
  *"git push"*"--no-verify"*)
    deny "git push --no-verify は禁止されています。" ;;
  *"git commit"*"--no-gpg-sign"*)
    deny "--no-gpg-sign は禁止されています (CLAUDE.md)。" ;;
esac

# --- npm publish (should go through release workflow) ---------------------
case "$CMD" in
  "npm publish"*|*" npm publish"*)
    deny "npm publish は手動で行わず、release ワークフロー経由で実行してください。" ;;
esac

# --- PR 作成は /create-pr skill 経由を強制 -------------------------------
# `gh pr create` を直接実行すると /create-pr skill のフェーズ 6.2 で発動する
# `/watch-pr` auto-chain が走らず、 CI 監視が起動しない (PR #498 で発覚)。
# memory: feedback_pr_create_skill_only.md
# command 先頭 / `&& ` / `; ` 直後の場合のみ block (commit message 等の
# 引用内文字列は誤発動を避けるため除外)。
case "$CMD" in
  "gh pr create"|"gh pr create "*|*"&& gh pr create"*|*"; gh pr create"*|*"&&gh pr create"*|*";gh pr create"*)
    deny "gh pr create の直接実行は禁止です。/create-pr skill を使うと watch-pr の auto-chain が発動し、 PR 構造化本文 + CI 監視が一括で起動します。" ;;
esac

exit 0
