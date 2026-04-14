# `.claude/` — Claude Code Automation for piper-plus

このディレクトリには、piper-plus プロジェクトで Claude Code を使う際の自動化設定 (hooks + skills) が含まれています。

## ファイル一覧

```
.claude/
├── README.md                       # このファイル
├── settings.json                   # プロジェクト共有 hooks 定義 (git 管理)
├── settings.local.json             # 個人設定 (gitignore 済み、permissions 等)
├── hooks/                          # シェルスクリプト hooks (LF 改行)
│   ├── ruff-format.sh              # PostToolUse: Python ファイル自動 format
│   ├── guard-bash.sh               # PreToolUse: 危険コマンドブロック
│   ├── prompt-guard.sh             # UserPromptSubmit: キーワード検出 → リマインダー
│   ├── stop-warn-uncommitted.sh    # Stop: 未コミット変更を警告
│   └── session-env.sh              # SessionStart: env 変数 + ブランチ情報注入
├── skills/                         # ユーザー起動 skills (`/<name>` で実行)
│   ├── precheck/SKILL.md           # /precheck — lint + format + test 一括
│   ├── check-pr-ready/SKILL.md     # /check-pr-ready — PR 作成前の最終チェック
│   ├── commit/SKILL.md             # /commit — CLAUDE.md 準拠コミット
│   ├── run-tests/SKILL.md          # /run-tests — 各言語ランタイムテスト
│   ├── sync-docs/SKILL.md          # /sync-docs — エージェントチームによる全ドキュメント監査・更新
│   └── reply-review/SKILL.md       # /reply-review — レビューコメントに返信 + thread resolve
└── commands/                       # 既存の slash commands (skills と併存可)
    ├── add-language.md             # 新言語追加ガイド
    └── review-language.md          # 10 エージェント並列レビュー
```

## Hooks (自動実行)

`settings.json` で定義された 5 つの hook が以下のタイミングで自動実行されます:

| Hook | タイミング | 動作 |
|------|----------|------|
| **PostToolUse** (Edit/Write/MultiEdit) | ファイル編集後 | Python ファイルに `ruff format` + `ruff check --fix` を自動適用 |
| **PreToolUse** (Bash) | bash コマンド実行前 | force push、`--no-verify`、`/data/piper/` 削除等の危険コマンドをブロック |
| **UserPromptSubmit** | ユーザー入力時 | 「PR 作成」「コミット」「学習開始」等のキーワードを検出して CLAUDE.md ルールをリマインド |
| **Stop** | セッション終了時 | 未コミット変更があれば 1 回だけ警告 |
| **SessionStart** | セッション開始/再開時 | NCCL 環境変数 + 現在のブランチ情報を注入 |

### 主な保護対象 (guard-bash.sh)

- `git push --force` to main/master
- `git commit --no-verify` (CLAUDE.md 禁止)
- `git commit --no-gpg-sign` (CLAUDE.md 禁止)
- `git reset --hard origin/main|master`
- `rm -rf /data/piper/output-*` / `rm -rf /data/piper/dataset-*` (学習データ保護)
- `epoch=*.ckpt` / `checkpoints/` の削除 (チェックポイント保護)
- `npm publish` (リリースワークフロー経由を強制)

`echo`/`printf`/`cat`/`tee` で始まるコマンドは false-positive 防止のためチェックをスキップします (例: `echo 'git push --force main'` のようなデモ・テスト)。

## Skills (手動起動)

### `/precheck [scope]`
lint + format + test を一括実行。引数で対象を絞れます (`python`/`rust`/`cs`/`go`/`js`/`cpp`/`all`)。未指定時は `git diff` から自動判定。

### `/check-pr-ready [skip-tests]`
PR 作成前の最終チェック (lint/test/docs/CHANGELOG/未コミット確認)。`/precheck` の上位版で、ドキュメント整合性も検証します。

### `/commit [optional message]`
CLAUDE.md のコミットルール (`--no-verify` 禁止、HEREDOC、適切な prefix) を強制した安全なコミット。

### `/run-tests [scope]`
各言語ランタイムのテストを CI と同条件でローカル実行。

### `/sync-docs [commit-range]`
**エージェントチームで全ドキュメントを監査・更新**。コード変更に対して CLAUDE.md / README / CHANGELOG / docs/features / docstring の整合性を 6 エージェント並列で監査し、必要な更新を提案・適用します。

**推奨フロー**:
1. 実装・テスト追加
2. `/sync-docs` でドキュメント監査 → 承認後に自動更新
3. `/commit` でコミット
4. `/check-pr-ready` → PR 作成

**監査エージェント**:
- Agent 1: CLAUDE.md (実装済み機能・ファイルパス・API 表)
- Agent 2: ルート README (Features / Feature Support Matrix)
- Agent 3: ランタイム別 README (python_run, openjtalk-web, etc.)
- Agent 4: CHANGELOG (Unreleased セクション)
- Agent 5: docs/features / docs/spec
- Agent 6: docstring / JSDoc 整合性

PR #349 で発生した「ドキュメント更新を一括で後付けする」パターンをコミット単位で防止します。

### `/reply-review <pr-number> [commit-hash]`
**レビューコメントへの返信 + thread resolve を自動化**。修正コミット後に呼び出すと、未解決の review thread を取得し、各コメントに対応内容 (コミットハッシュ付き) を返信して thread を resolve します。

**推奨フロー**:
1. レビュー指摘を修正
2. `/commit` でコミット
3. `git push` で PR に反映
4. `/reply-review <pr-number>` で返信 + resolve

**内部で使う API**:
- GraphQL `resolveReviewThread` mutation (thread resolve)
- REST API `POST /repos/{owner}/{repo}/pulls/{pr}/comments` with `in_reply_to` (返信投稿)

GitHub CLI (`gh`) の認証が必要です。`$1` を省略した場合は引数不足エラー、`$2` を省略した場合は `git rev-parse HEAD` の短縮ハッシュを使用します。

PR #349 / #350 のレビュー対応で手動実行していたワークフローを skill 化したものです。

## 依存

### 必須
- **Python 3** (どのフックでも fallback として使用)
- **Git Bash** (Windows) または bash (Unix)

### オプション (高速化)
- **jq** — インストールされていれば自動的に使用 (`jq` 不在時は Python フォールバック)

Windows での jq インストール (任意):
```sh
# Scoop
scoop install jq

# Chocolatey
choco install jq

# winget
winget install jqlang.jq
```

## 改行種について

`.claude/hooks/*.sh` は **LF (Unix)** 改行で保存される必要があります。これは `.gitattributes` の `*.sh text eol=lf` ルールで自動的に保証されます。

CRLF で保存されると Git Bash で以下のエラーが出ます:
```
bash: $'\r': command not found
```

## デバッグ

### 個別フックのテスト

```bash
# guard-bash: 危険コマンドが正しくブロックされるか
echo '{"tool_input":{"command":"git push --force main"}}' | bash .claude/hooks/guard-bash.sh

# prompt-guard: キーワードがリマインダーを生成するか
echo '{"prompt":"PR を作成してください"}' | bash .claude/hooks/prompt-guard.sh

# session-env: env 変数とブランチ情報の出力
bash .claude/hooks/session-env.sh < /dev/null
```

### フックを一時無効化

`.claude/settings.json` の該当 hook をコメントアウト、または `.claude/settings.local.json` に空配列で上書き:

```json
{
  "hooks": {
    "PreToolUse": []
  }
}
```

## 設計思想

このディレクトリの自動化は、**phoneme timing PR (#349) で発生した以下の問題** を再発防止するために導入されました:

1. **CI で ruff lint/format が失敗** → ローカル実行を忘れていた
2. **ドキュメント更新漏れ** → 大きな機能追加時にリマインダーがなかった
3. **危険コマンド** → human review 前にうっかり実行するリスク
4. **未コミット変更の放置** → セッション終了時に気付かない

Hooks は **自動実行で予防**、Skills は **明示的に呼び出して使う一括ツール** という棲み分けです。
**問題 2** (ドキュメント更新漏れ) は `/sync-docs` skill でエージェントチームによる並列監査として解決しています。コミット前に呼び出すことで、PR #349 のような「後付けの一括ドキュメント更新」を避けられます。

## 既存 commands との関係

`.claude/commands/` にある `add-language.md` / `review-language.md` は **slash commands** として引き続き動作します。これらは `/add-language <lang>` / `/review-language <lang>` で起動できます。

新規追加した skills (`/precheck`, `/check-pr-ready`, `/commit`, `/run-tests`) は **frontmatter 付き** で同じく slash command として動作します。

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — プロジェクト全体のルール
- [Claude Code hooks 公式ドキュメント](https://code.claude.com/docs/en/hooks)
- [Claude Code skills 公式ドキュメント](https://code.claude.com/docs/en/skills)
