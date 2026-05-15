---
name: check-review-backlog
description: 全 open PR の未解決 review thread (isResolved=false) を gh api graphql で集計し、7 日以上未対応のものを backlog として表示する read-only skill。`/loop /check-review-backlog` で週次監視に利用可能。
argument-hint: "[--days N] [--author <login>]"
disable-model-invocation: true
allowed-tools: Bash(gh api *) Bash(gh pr list *) Bash(date *) Read Grep
---

# Unresolved Review Backlog Monitor

全 open PR を走査して、未解決 (`isResolved=false`) の review thread のうち N 日以上経過しているものを backlog として集計する。レビュー対応漏れの早期警告が目的。

## 引数

- `--days N` (任意): 経過日数の閾値 (デフォルト: 7 日)
- `--author <login>` (任意): 特定 reviewer (例: `copilot-pull-request-reviewer`) のコメントに絞る

## 実行前の確認

- 現在時刻 (UTC): !`date -u +"%Y-%m-%dT%H:%M:%SZ"`
- 引数: $ARGUMENTS

## 手順

### フェーズ 1: Open PR 一覧取得

```bash
gh pr list --state open --json number,title,createdAt,updatedAt --limit 50
```

各 open PR について、フェーズ 2 を実行する。

### フェーズ 2: 未解決 thread の集計

各 PR について、GraphQL で未解決 review thread + 最初のコメントを取得:

```bash
gh api graphql -f query='
query($pr: Int!) {
  repository(owner: "ayutaz", name: "piper-plus") {
    pullRequest(number: $pr) {
      title
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              databaseId
              path
              line
              body
              createdAt
              author { login }
              url
            }
          }
        }
      }
    }
  }
}' -F pr=<PR_NUMBER> --jq '.data.repository.pullRequest | {
  title,
  unresolved: [.reviewThreads.nodes[] | select(.isResolved == false) | .comments.nodes[0]]
}'
```

### フェーズ 3: 経過日数フィルタリング

各 thread の `createdAt` (ISO8601) と現在時刻を比較し、`days_old >= --days` のものを抽出:

```python
# 概念 pseudocode (実際は bash + jq + date で実装)
from datetime import datetime, timezone
now = datetime.now(timezone.utc)
threshold_days = int(args.days or 7)
for thread in unresolved_threads:
    created = datetime.fromisoformat(thread["createdAt"].replace("Z", "+00:00"))
    days_old = (now - created).days
    if days_old >= threshold_days:
        backlog.append({**thread, "days_old": days_old})
```

`--author` 指定時は `comment.author.login == args.author` で更に絞る。

### フェーズ 4: 集計レポート

backlog を以下の形式で表示 (経過日数の降順):

```text
## Review Backlog (>= <N> days unresolved)

| PR | Title | Reviewer | path:line | Days | URL |
|----|-------|----------|-----------|------|-----|
| #489 | feat: ... | Copilot | src/foo.py:42 | 21 | https://github.com/.../discussion_r... |
| #501 | fix: ...  | human   | docs/bar.md:10 | 9  | https://github.com/.../discussion_r... |
| ... | ...     | ...     | ...           | ... | ...                                  |

Total: <N> threads across <M> PRs

### 統計
- Copilot bot: <n> threads (<x%>)
- Human reviewers: <n> threads (<x%>)
- 最古: PR #<N>, <days> 日経過
```

backlog が空の場合: `OK: 全 open PR で <N> 日以上未対応の review thread はありません。`

### フェーズ 5: 推奨アクション

| 状況 | 推奨 |
|------|------|
| backlog ≥ 5 件 | 該当 PR の owner に `/reply-review <PR>` 実行を促す。Copilot ノイズが多ければ `--skip-copilot-style` 併用 |
| 30 日以上の thread あり | 該当 PR の状態を確認 (draft / stale / abandoned)。close / resolve 判断を促す |
| Copilot bot 比率 ≥ 60% | `/reply-review <PR> --skip-copilot-style` を案内 |
| 単一 PR で 10+ unresolved | その PR の review 状況が悪化中。優先対応 |

## 継続監視モード

```text
/loop /check-review-backlog          # 自動 pace (週次目安)
/loop 24h /check-review-backlog      # 24 時間ごと
/loop /check-review-backlog --days 3  # 3 日閾値で監視
```

## 使用例

```text
# 7 日以上未対応の thread を一覧 (デフォルト)
/check-review-backlog

# 3 日以上に閾値を厳しく
/check-review-backlog --days 3

# Copilot コメントのみ
/check-review-backlog --author copilot-pull-request-reviewer

# 週次監視
/loop /check-review-backlog
```

## 注意事項

- **read-only**: 本 skill は POST/mutation を一切行わない。集計と表示のみ
- **rate limit**: 50 open PR × GraphQL query で ~50 req、GitHub API 制限 (5000/h) 内
- **タイムゾーン**: `createdAt` は UTC。日数計算は UTC 基準
- **fork PR**: 外部 contributor の fork PR も含む
- **draft PR**: 集計対象 (draft でも review コメントが付くため)
- 集計結果は scrollable な table で、ユーザが目視で優先度判定する想定

## 期待効果

- レビュー対応漏れの可視化 (memory `feedback_copilot_stale_review` の延長線上)
- `/reply-review` 実行のトリガとして利用 (どの PR を優先対応すべきか判断材料)
- 長期 unresolved の発見 → PR の active/abandoned 判定を促進
