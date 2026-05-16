---
name: watch-ci-patterns
description: CI workflow の最近 run を集計し、 failure を「flake / drift / env / test bug」に自動分類する skill。 既存 `/watch-pr <PR>` の workflow-level 拡張。 引数なしで全 workflow の health check、 `--workflow <name>` で個別 workflow の最近失敗パターンを抽出。 docker-build 45% / go-ci 14% / csharp-ci 13% のような chronic flake を可視化する。
argument-hint: "[--workflow <name>] [--limit 30] [--since 7d]"
disable-model-invocation: false
allowed-tools: Bash(gh run list *) Bash(gh run view *) Bash(gh workflow list *) Bash(ls .github/workflows/*) Bash(rg *) Bash(grep *) Bash(awk *) Bash(sort *) Bash(uniq *) Read Grep
---

# CI Failure Pattern Watcher

15 エージェント workflow 監査の調査結果に基づく skill。 主要 failing workflow:

| Workflow | Failure rate | 主要 failure 種別 |
|----------|-------------|-----------------|
| docker-build.yml | 45% | flake (arm64 QEMU / disk space / network) |
| docker-test.yml | 16% | feature-branch test env (disk / arm64) |
| go-ci.yml | 14% | dep drift (go.mod resolver) |
| csharp-ci.yml | 13% | feature-branch issue-426 (docker mount) |
| multi-runtime-rtf.yml | 5% | timing variance / RTF baseline |

## 分類カテゴリ

1. **flake**: 同じ branch の同じ commit で連続失敗 → 再 run で pass。 timing / network 由来。
2. **drift**: lockfile / version pin / contract 不整合。 pre-commit で先回り可能。
3. **env**: runner OS specific / QEMU emulation / disk space / Docker daemon。
4. **test bug**: 同じ branch で再 run しても再現。 実装変更を要する。

## 引数

- `--workflow <name>`: 個別 workflow に絞る (省略時は全 workflow)
- `--limit N`: 取得する run 数 (default 30)
- `--since DUR`: 期間絞り込み (`7d` / `24h`)
- `--branch <name>`: 特定 branch に絞る (default 全 branch)

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS

## フェーズ 1: workflow 一覧取得

```bash
gh workflow list --limit 50 --json name,state,id | jq -r '.[] | select(.state == "active") | .name'
```

`--workflow` 指定時はその 1 つだけ、 省略時は全 active workflow を順次処理。

## フェーズ 2: 各 workflow の最近 run 集計

```bash
gh run list --workflow="$WORKFLOW" --limit "$LIMIT" \
    --json conclusion,name,headBranch,createdAt,displayTitle,databaseId,event
```

集計:

- 全 run 数
- conclusion 別 (success / failure / cancelled / skipped)
- failure rate (failure / (success + failure))

## フェーズ 3: failure run の commit / branch クラスタリング

同じ commit SHA / branch で複数 run があれば flake 疑い。 異なる branch で同じ workflow が同じ step で fail なら drift 疑い:

```bash
gh run list --workflow="$WORKFLOW" --status=failure --limit 50 \
    --json headSha,headBranch,databaseId,createdAt | \
    jq -r 'group_by(.headSha) | map({sha: .[0].headSha, count: length, branches: [.[].headBranch] | unique}) | .[]'
```

`count >= 2 && branches.length == 1` = flake or test bug。 `count == 1 && branches.length > 1` = drift。

## フェーズ 4: 失敗ログのパターン抽出

failure run の上位 3 件を `gh run view --log-failed` でログ取得、 既知 pattern と grep:

```bash
gh run view "$RUN_ID" --log-failed 2>&1 | tail -200 > /tmp/run_$RUN_ID.log

# Pattern matching
grep -E "(disk full|no space left)" /tmp/run_$RUN_ID.log && echo "ENV: disk"
grep -E "(connection refused|timeout|TLS)" /tmp/run_$RUN_ID.log && echo "ENV: network"
grep -E "(go.mod|inconsistent vendoring|missing go.sum)" /tmp/run_$RUN_ID.log && echo "DRIFT: go.mod"
grep -E "(ruff|format.*drift|cargo fmt)" /tmp/run_$RUN_ID.log && echo "DRIFT: format"
grep -E "(qemu|exec format error|illegal instruction)" /tmp/run_$RUN_ID.log && echo "ENV: arm64-emulation"
grep -E "FAILED.*test_" /tmp/run_$RUN_ID.log | head -5  # 実 test failure 名
```

抽出した signature を分類カテゴリに mapping。

## フェーズ 5: report 生成

```markdown
## CI Pattern Report — $(date +%Y-%m-%d)

### Summary
- workflows scanned: $N
- total runs (last $LIMIT): $TOTAL
- failure rate (overall): $RATE%

### Top failing workflows
| Workflow | Failure% | Primary category |
|----------|---------|------------------|
| docker-build | 45% | env (arm64 QEMU) |
| go-ci | 14% | drift (go.mod) |
| ... | ... | ... |

### Action items
- [ ] go-ci drift: `go mod tidy` を pre-push に追加検討
- [ ] docker-build flake: arm64 build を concurrency 制限
- [ ] csharp-ci issue-426: 個別 fix (test bug)
```

## フェーズ 6: 既存 skill との連携

flake / env と判定したら何もしない (再 run 任せ)。 drift と判定したら以下を提案:

- ruff drift → `/bump-deps ruff --target <ver>` 推奨
- ORT drift → `/bump-deps ort --target <ver>` 推奨
- format drift → `pre-commit run --all-files`
- contract drift → 該当 contract gate を pre-commit + CI で再走

test bug は個別 fix なので skill では着手しない、 issue 番号で記録。

## 注意

- **memory feedback_ci_cancelled_baseline**: cancelled / skipped は failure ではない、 baseline 検証が silently skip されることがあるので注意。
- **memory feedback_ci_matrix_no_reduction**: matrix の OS × version 削減は提案しない (網羅性優先)。
- **memory feedback_merge_caution**: 自動で `gh workflow run` 再実行はしない、 user 確認後のみ。
- **rate limit**: gh CLI は GH API の 5000/h を共有。 大量 workflow ある repo では `--limit` を保守的に。

## 使用例

```text
# 全 workflow の health check
/watch-ci-patterns

# docker-build に絞って深堀り
/watch-ci-patterns --workflow docker-build.yml --limit 50

# 最近 24h の failure のみ
/watch-ci-patterns --since 24h

# loop で 30 分ごと監視
/loop 30m /watch-ci-patterns --since 24h
```

## 期待効果

- chronic flake (docker-build 45%) と **本物の drift / test bug を分離**
- failure log の **手作業 `gh run view` 巡回を skill 化**
- drift と判定したら **既存 `/bump-deps` / `/precheck` skill** にバトンを渡す
- `/loop` と組み合わせて **継続的 CI health monitor**
