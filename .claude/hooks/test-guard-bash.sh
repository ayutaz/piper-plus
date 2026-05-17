#!/usr/bin/env bash
# guard-bash.sh の動作テスト。 hook を変更したらこの script を走らせる:
#   bash .claude/hooks/test-guard-bash.sh
#
# Skill 内 / Skill 外で gh pr create の挙動が変わるため、 transcript_path に
# attributionSkill / Skill tool record を含む mock JSONL を作って入力する。

set -u

HOOK=".claude/hooks/guard-bash.sh"
MOCK_TX=$(mktemp -t guard-bash-test-XXXXXX.jsonl)
FAIL=0

cleanup() { rm -f "$MOCK_TX"; }
trap cleanup EXIT

run() {
  local label="$1" tx_content="$2" hook_input="$3" want_exit="$4" want_output_grep="$5"
  printf '%s\n' "$tx_content" > "$MOCK_TX"
  local out
  out=$(printf '%s' "$hook_input" | bash "$HOOK")
  local got=$?
  local ok=1
  if [ "$got" != "$want_exit" ]; then
    ok=0
  fi
  if [ -n "$want_output_grep" ]; then
    if ! printf '%s' "$out" | grep -q "$want_output_grep"; then
      ok=0
    fi
  fi
  if [ "$ok" = 1 ]; then
    printf '  PASS  %s\n' "$label"
  else
    printf '  FAIL  %s (exit=%s want=%s out=%s)\n' "$label" "$got" "$want_exit" "$out"
    FAIL=$((FAIL+1))
  fi
}

input_for() {
  printf '{"transcript_path":"%s","tool_input":{"command":"%s"}}' "$MOCK_TX" "$1"
}

input_no_tx() {
  printf '{"tool_input":{"command":"%s"}}' "$1"
}

echo "== gh pr create skill-aware guard =="
run "skill 内 (slash command marker)" \
  'random<command-name>/create-pr</command-name>more' \
  "$(input_for 'gh pr create --base dev')" \
  0 ""

run "skill 内 (Skill tool record)" \
  '{"name":"Skill","input":{"skill":"create-pr","args":""}}' \
  "$(input_for 'gh pr create --base dev')" \
  0 ""

run "別 skill が最新 (拒否)" \
  '<command-name>/create-pr</command-name>{"name":"Skill","input":{"skill":"watch-pr"}}' \
  "$(input_for 'gh pr create --base dev')" \
  0 "permissionDecision.*deny"

run "bash command 内の <command-name> リテラルは無視 (拒否)" \
  'echo "<command-name>/create-pr"' \
  "$(input_for 'gh pr create --base dev')" \
  0 "permissionDecision.*deny"

run "transcript なし (拒否)" \
  '' \
  "$(input_no_tx 'gh pr create --base dev')" \
  0 "permissionDecision.*deny"

run "marker 後に tool_result のみ (許可)" \
  $'<command-name>/create-pr</command-name>\n{"type":"user","content":[{"tool_use_id":"toolu_01","type":"tool_result"}]}' \
  "$(input_for 'gh pr create --base dev')" \
  0 ""

run "marker 後に user new prompt (拒否、 historical match 防止)" \
  $'<command-name>/create-pr</command-name>\n{"type":"user","content":"new question after skill done"}' \
  "$(input_for 'gh pr create --base dev')" \
  0 "permissionDecision.*deny"

run "marker 後に tool_result + user prompt 両方 (拒否)" \
  $'<command-name>/create-pr</command-name>\n{"type":"user","content":[{"tool_use_id":"toolu_01","type":"tool_result"}]}\n{"type":"user","content":"another task"}' \
  "$(input_for 'gh pr create --base dev')" \
  0 "permissionDecision.*deny"

echo ""
echo "== 既存挙動の維持 =="
run "echo bypass" \
  '' \
  "$(input_no_tx 'echo gh pr create')" \
  0 ""

run "git push --force main (拒否維持)" \
  '' \
  "$(input_no_tx 'git push --force origin main')" \
  0 "force push"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "all green"
  exit 0
else
  echo "$FAIL test(s) failed"
  exit 1
fi
