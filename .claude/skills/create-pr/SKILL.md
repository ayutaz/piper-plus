---
name: create-pr
description: 「PR を作って」「pull request を出して」要求で発動。 push 済みブランチに対し、 機能カテゴリ別の表 + 設計判断 + Test plan を含む構造化 PR 本文を作成。 マイルストーン非付与、 auto-merge 非使用、 後から見て分かる機能ベース構造 (フェーズ表現排除) を強制。
argument-hint: "[base-branch] [--title <title>]"
disable-model-invocation: false
allowed-tools: Bash(git log *) Bash(git diff *) Bash(git status *) Bash(git push *) Bash(git rev-parse *) Bash(git remote *) Bash(gh pr create *) Bash(gh pr view *) Bash(gh pr edit *) Bash(cat *) Read Write
---

# PR Creation Helper

PR 作成の **標準フォーマット** を強制し、 過去のレビュー指摘で繰り返し出てきた構造問題 (時系列フェーズ表記、 機能の不明瞭、 Test plan 欠落、 マイルストーン誤付与) を予防する skill。

## 自動発動条件

以下の文脈で LLM が自動判断で本 skill を呼ぶことを想定:

- 「PR を作って / 出して」
- 「pull request を作って」
- 「この変更で PR にして」
- 「branch を push して PR にして」

明示呼び出し: `/create-pr` または `/create-pr <base-branch>`

## 引数

- `$ARGUMENTS` 空: base = `dev` (memory `feedback_merge_caution`: 通常 dev を base にする)
- `<base-branch>`: 明示指定 (例: `main`)
- `--title <title>`: title 上書き (デフォルトは最新コミット message から抽出)

## 制約 (memory 参照)

- **マイルストーン非付与** (memory `feedback_pr_no_milestones`): `--milestone` を一切付けない。 PR body にも「M1」「M2」等の表記を入れない
- **auto-merge 禁止** (memory `feedback_merge_caution`): `gh pr merge --auto` 等を絶対に使わない。 PR 作成のみで完了、 マージはユーザー判断
- **本文書き換え禁止** (memory `feedback_pr_body_over_comments`): 既存 PR の更新は `gh pr edit --body-file` で本文置換。 新規コメントで追記しない
- **--no-verify 禁止** (CLAUDE.md): hook bypass 系オプションを使わない

## フォーマット規定

PR title は **70 文字以内** で機能サマリ。 type(scope) prefix (例: `feat(workflow):`, `fix(g2p):`, `docs(spec):`)。

PR body は以下の **6 セクション** を必ず含める (後から読んで分かる、 機能ベース構造):

### 1. Summary (3 bullet 以内)

- 解決する問題 / 動機 (1-2 行)
- 変更の規模 (コミット数 / ファイル数 / 行数)
- design 上の主要トレードオフ (1 行、 必要なら)

時系列表現 (`Phase 1` / `Phase 2` / `S 級` / `A 級` 等) は使わない。 後から読む人にとって意味がない。

### 2. 新規 / 拡張機能 (機能カテゴリ別の表)

カテゴリの例 (PR の性質に応じて選択):

- **PR レビュー支援** (skill / hook)
- **リリース・ドキュメント整合性** (skill / hook)
- **Commit 時の drift gate** (pre-commit hook)
- **Push 前の最終確認** (opt-in pre-push stage)
- **CI / build 自動化** (workflow)
- **API / runtime 機能追加** (機能種別: synthesis / G2P / SSML / etc.)
- **バグ修正 / 性能改善** (修正内容)
- **ドキュメント / 仕様更新** (spec / migration / reference)

各カテゴリ内は **表形式** で `機能名 / 動作 / 解決する問題 (or インパクト)` の 3 列。 動作は「何がどう動くか」、 解決する問題は「これがないと何が起こるか」。

### 3. 設計判断 / トレードオフ

bullet で意思決定の根拠を残す:

- conservative / aggressive 判断と理由
- 誤検出回避 / false-positive control の設計
- bypass 経路 (緊急時の回避策)
- 既存システムとの整合性 (CI mirror / hook chain 等)

### 4. Test plan (`- [ ]` チェックボックス)

reviewer がそのまま動作確認に使える具体的な手順。 抽象表現 (「動作確認する」) でなく具体的なコマンド or 操作。

### 5. 参考

- canonical truth / spec ファイルへの参照
- 関連 memory file
- 関連 PR / issue 番号

### 6. 何を含めないか

- 時系列 (Phase / 開発過程 / 履歴)
- マイルストーン番号
- 「LLM が generate した」「Claude Code で作成」等の co-authored note
- 確認済み bug の説明 (fix した後の説明は冗長)

## 実行手順

### フェーズ 1: ブランチ状態確認 (並列)

```bash
git status --short
git log --oneline <base>..HEAD
git diff --stat <base>..HEAD
git rev-parse --abbrev-ref HEAD
git remote -v | head -2
```

確認項目:

- working tree clean か
- commit が 1 つ以上 ahead か
- upstream 設定済みか (新規ブランチは `-u` 必要)
- remote が SSH か HTTPS か

### フェーズ 2: PR 本文 draft 作成

`git log <base>..HEAD --pretty=format:"%h %s%n%b"` で全 commit のメッセージを読み、 以下を抽出:

- 機能カテゴリの自動分類 (commit message の type(scope) と diff の path から)
- 行数 / ファイル数 (`git diff --stat` の最後の行)
- 主要トレードオフ (commit body の「why」「設計判断」コメント)

draft を `/tmp/pr-body-<branch-slug>.md` に書き出す。 6 セクション構造を埋める。

### フェーズ 3: ユーザー確認 (任意、 conservative)

ユーザーが「確認なしで進める」と指示している場合は省略。 そうでない場合は draft を表示して承認を取る。

### フェーズ 4: push (必要なら)

```bash
git push -u origin <branch-name>
```

既に push 済みなら skip。 `git rev-parse @{u}` で upstream の有無を確認。

### フェーズ 5: PR 作成 (or 既存 PR 更新)

新規:

```bash
gh pr create --base <base> --title "<title>" --body-file /tmp/pr-body-<branch-slug>.md
```

既存 PR (本ブランチに対する PR が既存) の本文書き換え:

```bash
gh pr edit <PR#> --body-file /tmp/pr-body-<branch-slug>.md
```

`gh pr list --head <branch>` で既存 PR 有無を判定。

### フェーズ 6: 自動 follow-up 提案

PR URL を表示し、 以下を提案 (実行はユーザー指示後):

- `/watch-pr <PR#>` で CI 監視 (新 skill との chain)
- `/reply-review <PR#>` で review 対応 (review 来た後)

## guard hook 回避

memory: pre-commit / GitHub hook が PR body 内の `--no-verify` 等の禁止文字列で誤検出することがある。 対策:

- PR body には実行コマンドの **抽象表記** を使う (「auto-merge」「hook bypass フラグ」等)
- どうしても禁止文字列を含めたい場合は `--body-file` 経由で渡す (引数として渡さない)

## 使用例

```text
# dev base に PR 作成 (自動発動でも明示でも同じ)
/create-pr

# main base 指定
/create-pr main

# title 上書き
/create-pr --title "fix(g2p): 中国語 loanword の正規化漏れ修正"

# 既存 PR の本文更新 (gh pr list で自動判定)
/create-pr
```

## 関連 skill

- `/watch-pr <PR#>`: PR 作成直後の CI 監視
- `/reply-review <PR#>`: review 対応
- `/sync-docs`: PR 作成前のドキュメント整合性監査 (推奨フロー: `/sync-docs` → `/create-pr` → `/watch-pr`)
- `/release-prep`: リリース PR 専用の情報収集

## 期待効果

- PR body の構造を標準化、 reviewer が読みやすい
- 「フェーズ」「マイルストーン」表記の自動排除
- Test plan / 設計判断の missing を予防
- 過去 PR の振り返り時に機能ベースで grep できる (時系列でなく)
- 「PR 作って」要求で自動発動、 ユーザーが skill 名を覚えなくて良い
