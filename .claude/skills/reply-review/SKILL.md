---
name: reply-review
description: PR レビューコメント (GitHub / Copilot) に対して対応内容を返信し、review thread を resolve します。修正コミット後に呼び出してください。
argument-hint: "<pr-number> [commit-hash]"
disable-model-invocation: true
allowed-tools: Bash(gh api *) Bash(gh pr view *) Bash(gh pr checks *) Bash(git log *) Bash(git show *) Bash(git rev-parse *) Read Grep
---

# PR レビューコメント自動返信 + Resolve

修正コミット後に呼び出して、未解決の review comment に対応内容を返信し、thread を resolve します。

## 引数

- `$1` (必須): PR 番号 (例: `349`)
- `$2` (任意): 返信に記載するコミットハッシュ。省略時は `git rev-parse HEAD` の短縮 hash を使用。

## 実行前の確認

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 最新コミット: !`git log -1 --oneline`
- 引数: $ARGUMENTS

## 手順

### フェーズ 1: Review Thread の取得

GraphQL で **未解決** の review thread を取得:

```bash
gh api graphql -f query='
query($pr: Int!) {
  repository(owner: "ayutaz", name: "piper-plus") {
    pullRequest(number: $pr) {
      reviewThreads(first: 50) {
        nodes {
          id
          isResolved
          comments(first: 1) {
            nodes {
              id
              databaseId
              path
              line
              body
              author { login }
            }
          }
        }
      }
    }
  }
}' -F pr=<PR_NUMBER> --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false) | {thread_id: .id, comment: .comments.nodes[0]}'
```

各 thread について:
- `thread_id`: GraphQL mutation で resolve するための ID
- `comment.databaseId`: REST API で reply するための ID
- `comment.path` + `comment.line`: どのファイルのどの行のコメントか
- `comment.body`: レビュー本文 (対応内容を判定する材料)

### フェーズ 2: 各コメントと修正の対応付け

1. 未解決 thread をリストで表示 (path:line、author、body の要約)
2. ユーザーに確認: 「どのコメントに対して、何をコミットで対応したか」
3. 引数 `$2` のハッシュ、または `git log dev..HEAD` の直近コミットから対応コミットを推定
4. コミットの diff (`git show --stat <hash>`) を確認し、各コメントと修正を紐付け
5. 紐付け結果をユーザーに提示して承認を得る

### フェーズ 3: 返信投稿

各コメントに対して、以下のテンプレートで返信を投稿:

```
対応しました (commit <hash>)。

<修正内容の 1-3 行要約>

<必要なら修正前後のコードスニペット>

<検証結果: テスト PASS カウント等>
```

REST API で返信:

```bash
gh api repos/ayutaz/piper-plus/pulls/<PR>/comments \
  --method POST \
  -F in_reply_to=<comment_database_id> \
  -f body="$REPLY_BODY" \
  --silent
```

**注意**:
- `in_reply_to` は **REST API の comment id (databaseId)** を使う。GraphQL の thread id ではない
- コメント本文に backtick やクォートを含める場合、変数展開に注意 (ヒアドキュメントか `printf '%s' "$BODY"` 経由を推奨)
- 1 件ずつループして投稿し、失敗したら残りを続行するか停止するかユーザーに確認

### フェーズ 4: Review Thread の Resolve

各 thread を GraphQL で resolve:

```bash
gh api graphql -f query='
mutation ResolveThread($id: ID!) {
  resolveReviewThread(input: {threadId: $id}) {
    thread { id isResolved }
  }
}' -f id=<THREAD_ID> --jq '.data.resolveReviewThread.thread | "\(.id): resolved=\(.isResolved)"'
```

全 thread をループで resolve。

### フェーズ 5: 最終レポート

```
## レビュー対応完了

### PR #<N>

| コメント | ファイル | 返信 | Resolve |
|---------|---------|------|---------|
| 1 | src/... | ✅ | ✅ |
| 2 | docs/... | ✅ | ✅ |
| ... | ... | ... | ... |

全 <N> 件 完了。
```

## 注意事項

- **未対応のコメントは resolve しない**。修正コミットが無いコメントは reply のみ (「次のコミットで対応予定」等) または保留
- **リソース ID の取り違えに注意**: GraphQL の `id` (node ID) と REST の `databaseId` を混同しない
- **コメント本文に含まれるコード**: suggestion 形式のコメント (コードブロック付き) はそのまま引用せず、要約で返信
- **dry-run オプション**: `$ARGUMENTS` に `--dry-run` が含まれていたら、投稿・resolve を実行せず計画のみ表示

## 使用例

```
# PR #349 のレビューに返信+resolve (コミットは HEAD)
/reply-review 349

# PR #350 に対して特定コミットで対応
/reply-review 350 a2e57f05

# Dry-run で計画のみ表示
/reply-review 349 --dry-run
```

## 期待効果

- レビュー対応ループ (修正 → push → 手動返信 → 手動 resolve) を 1 コマンドに集約
- 返信漏れ・resolve 漏れを防止
- コミットハッシュの記載を自動化し、後から trace しやすくする
