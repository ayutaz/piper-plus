#!/usr/bin/env bash
# UserPromptSubmit hook: inject contextual reminders based on keywords.
#
# Detects high-impact keywords in the user prompt (PR creation,
# commits, training, language addition, etc.) and adds small reminders
# from CLAUDE.md to the conversation context. Never blocks.

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

PROMPT=$(extract_field "prompt")

if [ -z "$PROMPT" ]; then
  exit 0
fi

NOTES=""

case "$PROMPT" in
  *"PR作成"*|*"PR を作成"*|*"PRを作成"*|*"プルリク"*|*"pull request"*|*"pull-request"*)
    NOTES+=$'### PR 作成リマインダー\n'
    NOTES+=$'- PR 先は **dev** ブランチ (CLAUDE.md)\n'
    NOTES+=$'- 事前に `/check-pr-ready` skill か手動で次を実行:\n'
    NOTES+=$'  - `uv run ruff check src/python_run/ src/python/`\n'
    NOTES+=$'  - `uv run ruff format --check src/python_run/ src/python/`\n'
    NOTES+=$'  - `uv run pytest src/python_run/tests/ -o addopts=""`\n'
    NOTES+=$'- PR タイトルは 70 文字以内、本文は HEREDOC で渡す\n'
    ;;
esac

case "$PROMPT" in
  *"コミット"*|*"git commit"*|*"commit して"*)
    NOTES+=$'### コミットリマインダー\n'
    NOTES+=$'- `--no-verify` / `--no-gpg-sign` は禁止 (CLAUDE.md)\n'
    NOTES+=$'- `git add -A` / `git add .` は避けて、ファイル指定で `git add <file>`\n'
    NOTES+=$'- `.env` / credentials は誤コミット禁止\n'
    NOTES+=$'- メッセージは 1-2 文、why を強調、HEREDOC 形式\n'
    NOTES+=$'- 既存コミットの `--amend` は明示要求がない限り禁止\n'
    NOTES+=$'- **大規模変更 (>100 行 or 新規 API)** なら `/sync-docs` でドキュメント監査を先に実行\n'
    NOTES+=$'- 推奨フロー: `/sync-docs` → `/commit` → `gh pr create`\n'
    ;;
esac

case "$PROMPT" in
  *"学習開始"*|*"学習を開始"*|*"training"*|*"ファインチューニング"*|*"fine-tune"*|*"finetune"*)
    NOTES+=$'### 学習開始リマインダー\n'
    NOTES+=$'- CLAUDE.md の Template A (事前学習) / Template B (finetune) を参照\n'
    NOTES+=$'- V100 では `--precision 32-true` 必須 (FP16 は致命的に遅い)\n'
    NOTES+=$'- 速度優先なら `--no-wavlm` 推奨\n'
    NOTES+=$'- NCCL: `NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1`\n'
    NOTES+=$'- 学習時間は見送り理由にならない (memory: feedback_training_cost)\n'
    ;;
esac

case "$PROMPT" in
  *"言語追加"*|*"新言語"*|*"add language"*|*"言語を追加"*)
    NOTES+=$'### 新言語追加リマインダー\n'
    NOTES+=$'- `/add-language <lang-code>` skill を使用\n'
    NOTES+=$'- 6 フェーズ: Python G2P → Rust → C++ → C# → JS/WASM → CI+Docs\n'
    NOTES+=$'- 各フェーズ完了ごとにコミット推奨\n'
    NOTES+=$'- 完了後 `/review-language <lang-code>` で 10 エージェント並列レビュー\n'
    ;;
esac

case "$PROMPT" in
  *"テスト追加"*|*"add test"*|*"テストを追加"*)
    NOTES+=$'### テスト追加リマインダー\n'
    NOTES+=$'- パッケージは `uv pip install` ではなく `uv add` (memory: feedback_uv_add)\n'
    NOTES+=$'- テストは `uv run pytest` 経由で実行 (memory: feedback_uv_testing)\n'
    NOTES+=$'- pytest.ini が `--cov` を要求するので `-o addopts=""` で上書き可能\n'
    ;;
esac

case "$PROMPT" in
  *"ドキュメント"*|*"docs "*|*"README"*|*"CLAUDE.md"*|*"CHANGELOG"*)
    NOTES+=$'### ドキュメント更新リマインダー\n'
    NOTES+=$'- `/sync-docs` でエージェントチームによる一括監査・更新が可能\n'
    NOTES+=$'- 監査対象: CLAUDE.md / README / CHANGELOG / docs/features / docstring\n'
    NOTES+=$'- 大規模コード変更後は `/sync-docs` → `/commit` のフローを推奨\n'
    ;;
esac

case "$PROMPT" in
  *"レビュー"*|*"review comment"*|*"レビューコメント"*|*"resolve"*|*"レビューに返信"*|*"PR のコメント"*)
    NOTES+=$'### レビュー対応リマインダー\n'
    NOTES+=$'- `/reply-review <pr-number>` skill で返信 + resolve を自動化できます\n'
    NOTES+=$'- 修正をコミットしてから skill を実行するフロー:\n'
    NOTES+=$'  1. レビュー指摘を修正\n'
    NOTES+=$'  2. `/commit` でコミット (適切な prefix 付き)\n'
    NOTES+=$'  3. `git push` で PR に反映\n'
    NOTES+=$'  4. `/reply-review <pr-number>` で返信 + resolve\n'
    NOTES+=$'- GraphQL API を使うため `gh` CLI が認証済みである必要があります\n'
    ;;
esac

if [ -n "$NOTES" ]; then
  if command -v jq >/dev/null 2>&1; then
    jq -n --arg ctx "$NOTES" '{
      hookSpecificOutput: {
        hookEventName: "UserPromptSubmit",
        additionalContext: $ctx
      }
    }'
  elif command -v python >/dev/null 2>&1; then
    python -c '
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": sys.argv[1]
    }
}))
' "$NOTES"
  fi
fi

exit 0
