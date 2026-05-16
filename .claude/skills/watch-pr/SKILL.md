---
name: watch-pr
description: PR push 直後 / PR 作成後の auto chain (`/create-pr` のフェーズ 6.2 から発動) / CI 監視 / レビュー対応 / merge 前確認 の文脈で発動。`gh pr checks` を一度 polling し green / red / pending を集計、 red なら失敗 job のログを fetch して「format drift / test fail / build error / flake / contract drift」に分類。 同時に unresolved review thread (人間 / Copilot) も集計し、 stale check 付きで提示。 `/loop /watch-pr <PR>` で継続監視に使える。
argument-hint: "[pr-number]"
disable-model-invocation: false
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

### フェーズ 5: Unresolved review thread の集計

CI status とは独立で、 review コメント / Copilot 指摘が未解決のまま残っていないか
を毎回チェック。 `/check-review-backlog --pr <PR>` 相当の GraphQL を呼ぶ:

```bash
gh api graphql -f query='
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 50) {
        nodes {
          isResolved
          isOutdated
          comments(first: 1) {
            nodes {
              author { login }
              path
              body
              createdAt
            }
          }
        }
      }
    }
  }
}' -F owner=ayutaz -F name=piper-plus -F number="$PR_NUM" --jq \
'.data.repository.pullRequest.reviewThreads.nodes
 | map(select(.isResolved == false))
 | length, map(select(.isResolved == false))[]'
```

集計:

- **Unresolved 0 件**: review 障害なし、 next phase へ
- **Unresolved ≥ 1 件**:
  - reviewer 別 (human / Copilot bot) に分類
  - **stale check**: 該当 file がそのコメント以降に修正済みか (memory `feedback_copilot_stale_review`)
  - 提案テーブル形式で表示:

    ```text
    ## Unresolved Review Threads (#<PR>)

    | # | Reviewer | Path | Stale? | 提案 |
    |---|----------|------|--------|------|
    | 1 | Copilot  | src/foo.py:42 | ✓ stale (b7e71c8 以降に更新済) | dismiss / reply |
    | 2 | yousan   | src/bar.rs:88 | new | 修正 → `/reply-review <PR>` |
    ```

### フェーズ 6: 次のアクション提案

| 状態 | 推奨アクション |
|------|-------------|
| All green + Unresolved 0 | `/check-pr-ready` で最終確認、 user 確認後に merge (`gh pr merge --auto` 禁止) |
| All green + Unresolved ≥ 1 | review 対応必要。 修正コミット後 `/reply-review <PR>` を提案 |
| Red (format drift) | `pre-commit run --all-files` をローカル実行、修正後 `/commit` |
| Red (test fail) | 該当テストファイル名を提示、`/run-tests <scope>` で再現 |
| Red (build error) | エラーログを示してユーザーに方針確認 |
| Red (flake) | `gh run rerun <run-id> --failed` を提示 (ユーザー確認後実行) |
| Red (contract drift) | `/check-pua` `/check-loanword` 等の該当 skill を提示 |
| Pending | `/loop /watch-pr <PR>` で継続監視を推奨 |

## 継続監視モード

ユーザーが「green になるまで監視して」と希望する場合:

```text
/loop /watch-pr <PR>
```

`/loop` skill が `/watch-pr <PR>` を再帰的に呼び出す。 各 iteration で本 skill が
CI + review thread を両方確認。 終了条件:

| iteration の結果 | アクション |
|------------------|-----------|
| All green + Unresolved 0 | ユーザーに完了通知して `/loop` を終了 |
| All green + Unresolved ≥ 1 | review backlog を表示、 `/reply-review <PR>` を提案して `/loop` を終了 (人間判断必須) |
| Red (本物) | 失敗分析を表示して `/loop` を終了 (人間判断が必要) |
| Red (flake のみ) | `gh run rerun --failed` を提案 (確認後実行)、 ループは継続 |
| Pending | 次の polling 間隔まで sleep (自動 pace は CI 状況で 4-20 分、 cache TTL の都合で IN_PROGRESS 多い時は `delaySeconds=270`、 落ち着いた状態なら `1200`+) |

review thread 自動 reply は行わない (memory `feedback_merge_caution` / `feedback_pr_body_over_comments` 遵守)。 reply 自動化が必要な場合はユーザーが明示的に `/reply-review <PR>` を起動。

## 注意事項

- **無限ループ防止**: 4 時間以上 pending が続くケースは `/loop` を終了して人間に確認を促す
- **rate limit**: GitHub API は 5000 req/hour、 ポーリング間隔を 1 分未満にしない
- **silent skip**: cancelled+skipped が連続 3 以上は path filter による意図的 skip かもしれないが、 PR #419 事例のように baseline が silent に skip されることがあるので警告
- **失敗ログ取得失敗時**: `gh run view` が 404 を返す場合 (job がまだ完了していない等) はスキップ
- **merge は user-only**: 本 skill から `gh pr merge` を実行することは禁止 (memory `feedback_merge_caution` に従う)
- **review reply は提案のみ**: フェーズ 5 で集計するが、 自動 reply / resolve は行わない。 `/reply-review <PR>` をユーザーが明示起動する形でのみ実行 (memory `feedback_pr_body_over_comments` 遵守、 各 thread に reviewer 意図を読み解いた返信本文が必要)
- **Copilot stale 検出**: review コメント以降に同 file が更新済なら `stale` フラグ付き提示 (memory `feedback_copilot_stale_review`)。 stale な Copilot 指摘は dismiss / 簡潔な「修正済」 reply が候補

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
