---
name: watch-pr
description: PR の CI checks を一度ポーリングし、green/red/pending を集計する。`/loop` と組み合わせて 5 分間隔の継続監視に使う (例 `/loop /watch-pr 489`)。red になったら失敗 job のログを fetch し、原因を「format drift / test fail / flake」に分類して修正案を提案する。
argument-hint: "[pr-number]"
disable-model-invocation: true
allowed-tools: Bash(gh pr checks *) Bash(gh pr view *) Bash(gh run view *) Bash(gh api *) Bash(git rev-parse *) Bash(git branch *) Read Grep
---

# PR CI Status Watcher

PR の CI checks を 1 回ポーリングして状態を集計する skill。継続監視は `/loop` と組み合わせる:

```text
/loop /watch-pr 489       # 5 分間隔で polling、red/green/timeout で通知
/watch-pr                 # 引数省略時は現在ブランチに紐づく PR を自動検出
```

## 引数

- `$1` (任意): PR 番号 (例: `489`)。省略時は `gh pr view --json number` で現在ブランチから自動取得

## 実行前の確認

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS

## 手順

### フェーズ 1: PR 番号の確定

引数 `$1` がない場合、現在ブランチに紐づく PR を取得:

```bash
PR_NUM=$(gh pr view --json number --jq '.number' 2>/dev/null)
```

該当 PR がない場合 (= まだ push していない / PR 未作成) は、その旨をユーザーに報告して停止。

### フェーズ 2: CI checks の一括取得

```bash
gh pr checks "$PR_NUM" --json name,state,conclusion,link --jq '.[]'
```

各 check は以下の状態のいずれか:

- **state**: `QUEUED` / `IN_PROGRESS` / `COMPLETED`
- **conclusion** (COMPLETED 時のみ): `SUCCESS` / `FAILURE` / `CANCELLED` / `SKIPPED` / `NEUTRAL` / `TIMED_OUT` / `ACTION_REQUIRED`

### フェーズ 3: 集計とサマリ

以下のテーブルでサマリを表示 (件数は実際の集計値):

```text
## PR #<N> CI Status (<HH:MM:SS>)

| State        | Count |
|--------------|-------|
| ✅ Success   | <n>   |
| ❌ Failure   | <n>   |
| 🔁 Pending   | <n>   |
| ⏭️ Skipped   | <n>   |
| ⚠️ Cancelled | <n>   |

Total: <total> checks
```

判定ルール:

- **All green** (failure=0, pending=0, cancelled=0): 「全 N checks green、merge 可能状態」
- **Red** (failure ≥ 1): フェーズ 4 へ
- **Pending** (queued/in_progress ≥ 1): 「N checks がまだ走行中、再度 polling を推奨」
- **Suspicious skip** (cancelled+skipped が 3 件以上連続): silent skip の可能性を警告 (PR #419 事例)

### フェーズ 4: 失敗 job の分析 (failure ≥ 1 時のみ)

各失敗 job について:

1. job 名と link を表示
2. `gh run view <run-id> --log-failed` で失敗 step のログを fetch (最大 100 行)
3. ログを以下の pattern で分類:
   - **Format drift**: `ruff` `cargo fmt` `gofmt` `dotnet format` `clippy` 系のエラー → ローカル `pre-commit run --all-files` で修復可能
   - **Test fail**: `FAILED` `assert` `panicked` `expected` 系 → どのテストかを抽出
   - **Build error**: `error[E0` `cannot find` `undefined reference` 系 → コンパイルエラー
   - **Flake**: `timeout` `network` `connection reset` `rate limit` 系 → 一過性、retry 推奨
   - **Contract drift**: `MISMATCH` `OUT OF SYNC` `byte-for-byte` 系 → 該当 `check-*` skill を案内
4. 分類別に推奨アクションを提示

### フェーズ 5: 次のアクション提案

| 状態 | 推奨アクション |
|------|-------------|
| All green | `/check-pr-ready` で最終確認、または merge を提案 (`gh pr merge --auto` は memory の禁止に従い使わない) |
| Red (format drift) | `pre-commit run --all-files` をローカル実行、修正後 `/commit` |
| Red (test fail) | 該当テストファイル名を提示、`/run-tests <scope>` で再現 |
| Red (flake) | `gh run rerun <run-id> --failed` を提示 (ユーザー確認後実行) |
| Red (contract drift) | `/check-pua` `/check-loanword` 等の該当 skill を提示 |
| Pending | `/loop /watch-pr <PR>` で継続監視を推奨 |

## 継続監視モード

ユーザーが「green になるまで監視して」と希望する場合:

```text
/loop /watch-pr <PR>
```

`/loop` skill が `/watch-pr <PR>` を再帰的に呼び出す。各 iteration で:

1. 本 skill を 1 回実行
2. all green → ユーザーに完了通知して `/loop` を終了
3. red → 失敗分析を表示して `/loop` を終了 (人間判断が必要)
4. pending → 次の polling 間隔まで sleep (自動 pace は 5 分目安、 cache TTL の都合で `delaySeconds <= 270` 推奨)

## 注意事項

- **無限ループ防止**: 4 時間以上 pending が続くケースは `/loop` を終了して人間に確認を促す
- **rate limit**: GitHub API は 5000 req/hour、ポーリング間隔を 1 分未満にしない
- **silent skip**: cancelled+skipped が連続 3 以上は path filter による意図的 skip かもしれないが、PR #419 事例のように baseline が silent に skip されることがあるので警告
- **失敗ログ取得失敗時**: `gh run view` が 404 を返す場合 (job がまだ完了していない等) はスキップ
- **merge は user-only**: 本 skill から `gh pr merge` を実行することは禁止 (memory `feedback_merge_caution` に従う)

## 使用例

```text
# 現在ブランチの PR を 1 回チェック
/watch-pr

# PR #489 を 1 回チェック
/watch-pr 489

# 5 分間隔で継続監視 (loop skill が pace 決定)
/loop /watch-pr 489

# 固定 5 分間隔
/loop 5m /watch-pr 489
```

## 期待効果

- ユーザーが 7 ランタイム × ~94 jobs の CI を手動で `gh pr checks` ポーリングする手間を削減
- red 時に「どの分類の失敗か」即座に分類することで対応時間を短縮
- silent skip (PR #419 type) の早期検出
