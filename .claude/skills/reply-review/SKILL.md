---
name: reply-review
description: PR レビューコメントへの対応 / review thread の resolve / Copilot や human reviewer のコメントに返信 する文脈で発動。修正コミット後に呼ぶと、各 unresolved thread に対して返信本文を生成し thread を resolve する。`--stale-check` で「コメント以降に該当ファイルが更新済」を自動 flag、`--skip-copilot-style` で Copilot 定型ノイズ regex 除外、`--dry-run` で計画のみ表示。
argument-hint: "<pr-number> [commit-hash] [--stale-check] [--skip-copilot-style] [--dry-run]"
disable-model-invocation: false
allowed-tools: Bash(gh api *) Bash(gh pr view *) Bash(gh pr checks *) Bash(git log *) Bash(git show *) Bash(git rev-parse *) Bash(git diff *) Read Grep
---

# PR レビューコメント自動返信 + Resolve

修正コミット後に呼び出して、未解決の review comment に対応内容を返信し、thread を resolve します。

## 引数

- `$1` (必須): PR 番号 (例: `349`)
- `$2` (任意): 返信に記載するコミットハッシュ。省略時は `git rev-parse HEAD` の短縮 hash を使用。
- `--stale-check` (任意): 各コメントの `originalCommit.oid` と HEAD を比較し、該当ファイルが以降に更新済の場合 stale flag を立てる (フェーズ 1.5 で表示)
- `--skip-copilot-style` (任意): Copilot の定型ノイズコメント (style/lint 系の "Consider using" "Consider renaming" 等) を一覧から除外 (フェーズ 1.7 で適用)
- `--dry-run` (任意): 投稿・resolve を実行せず計画のみ表示

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
              originalCommit { oid }
              commit { oid }
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
- `comment.originalCommit.oid`: コメントが付けられた commit SHA (stale check に使用)
- `comment.commit.oid`: コメントが現在指している commit SHA (rebase 後の最新位置)

### フェーズ 1.5: Stale Check (オプション、`--stale-check` 指定時のみ)

`$ARGUMENTS` に `--stale-check` が含まれる場合、各コメントについて該当ファイルがコメント作成以降に更新済かを判定する。

各コメントごとに以下を実行:

```bash
git log --oneline <originalCommit.oid>..HEAD -- <comment.path> 2>/dev/null
```

- **出力が空**: コメント作成以降にそのファイルへの変更なし → 「未対応」または「対応漏れ」の可能性
- **出力に commit がある**: 該当ファイルがその後 N コミットで更新されている → **stale 候補** (既に修正済の可能性)

stale 候補のテーブルを表示:

```text
## Stale Check 結果

| # | path:line | author | original_commit | since | 推定 |
|---|-----------|--------|-----------------|-------|------|
| 1 | src/foo.py:42 | Copilot | a7f8abb | 3 commits | 🔶 stale (既に修正済の可能性) |
| 2 | docs/bar.md:10 | reviewer | b2c3d4e | 0 commits | ⏳ 未対応 |
```

stale 候補について、ユーザーに以下を確認:

- **A**: そのまま「修正済 (commit `<new>`)」と返信して resolve
- **B**: 内容を再確認してから個別に判定
- **C**: スキップ (フェーズ 3 以降に進まない)

> **注意**: stale 判定は heuristic。ファイルが更新されていても該当箇所が修正されているとは限らない (例: 別関数の追加)。最終判断はユーザーに委ねる。CLAUDE.md memory `feedback_copilot_stale_review` で Copilot の古いコメント参照癖が記録されており、本 check はこれを補助する目的。

### フェーズ 1.7: Copilot Style ノイズ除外 (オプション、`--skip-copilot-style` 指定時のみ)

`$ARGUMENTS` に `--skip-copilot-style` が含まれる場合、Copilot レビュアー (`author.login` が `copilot-pull-request-reviewer` または末尾が `[bot]`) の定型ノイズコメントを一覧から除外する。

判定 regex (大文字小文字無視、コメント body に対して match):

```python
COPILOT_STYLE_NOISE_PATTERNS = [
    r"^Consider (using|renaming|adding|extracting|simplifying)\b",
    r"^Consider whether\b",
    r"\bstyle:\s*prefer\b",
    r"\bsecurity warning\b",
    r"\bMight be worth\b",
    r"^Suggestion: ",
    r"^This (variable|function|class) could be\b",
    r"\b(nit|nit:)\s",
    r"^Optional:",
]
```

除外条件: 上記 pattern のいずれかに match **かつ** author が Copilot bot。

除外したコメントは別表で表示し、ユーザに「個別に確認 / そのまま skip」を選ばせる:

```text
## Copilot Style Noise (除外候補)

| # | path:line | body (先頭 60 文字) | matched pattern |
|---|-----------|-------------------|-----------------|
| 1 | src/foo.py:42 | Consider renaming this variable to ... | ^Consider (renaming) |
| 2 | docs/bar.md:10 | Optional: you could also ...           | ^Optional:        |

これらを除外しますか? (y/N/individual)
- y: 全てスキップ (フェーズ 2 以降の対象から除外)
- N: 通常通り対応
- individual: 1 件ずつ判定
```

> **注意**: 過去 PR (#489, #493) で観測された Copilot コメントの 40-50% がこの pattern に該当 (調査エージェント報告)。誤検出を避けるため、author が Copilot bot **でない** 場合は除外しない (人間レビュアーが意図的に "Consider..." と書いた可能性を尊重)。

### フェーズ 2: 各コメントと修正の対応付け

1. 未解決 thread をリストで表示 (path:line、author、body の要約)
2. ユーザーに確認: 「どのコメントに対して、何をコミットで対応したか」
3. 引数 `$2` のハッシュ、または `git log dev..HEAD` の直近コミットから対応コミットを推定
4. コミットの diff (`git show --stat <hash>`) を確認し、各コメントと修正を紐付け
5. 紐付け結果をユーザーに提示して承認を得る

### フェーズ 3: 返信投稿

各コメントに対して、以下のテンプレートで返信を投稿:

```text
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

```text
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

```text
# PR #349 のレビューに返信+resolve (コミットは HEAD)
/reply-review 349

# PR #350 に対して特定コミットで対応
/reply-review 350 a2e57f05

# Dry-run で計画のみ表示
/reply-review 349 --dry-run

# Stale check 付き: コメント以降のファイル変更を解析して既修正候補を flag
/reply-review 349 --stale-check

# Stale check + dry-run の組み合わせ (検出のみ、投稿しない)
/reply-review 349 --stale-check --dry-run

# Copilot 定型ノイズを除外して対応対象を絞る
/reply-review 349 --skip-copilot-style

# 全フィルタを有効化 (stale 検出 + Copilot ノイズ除外 + dry-run)
/reply-review 349 --stale-check --skip-copilot-style --dry-run
```

## 期待効果

- レビュー対応ループ (修正 → push → 手動返信 → 手動 resolve) を 1 コマンドに集約
- 返信漏れ・resolve 漏れを防止
- コミットハッシュの記載を自動化し、後から trace しやすくする
- `--stale-check` により Copilot の stale review (古い commit を参照したコメント、CLAUDE.md memory `feedback_copilot_stale_review` 記録) を事前検出し、二重対応を防止
- `--skip-copilot-style` により Copilot の定型ノイズコメント (40-50% を占める style/lint 系の "Consider using" 等) を除外し、対応サイクル時間を短縮
