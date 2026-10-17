# `.claude/` — Claude Code Automation for piper-plus

このディレクトリには、piper-plus プロジェクトで Claude Code を使う際の自動化設定 (hooks + skills) が含まれています。

## ファイル一覧

```text
.claude/
├── README.md                       # このファイル
├── settings.json                   # プロジェクト共有 hooks 定義 (git 管理)
├── settings.local.json             # 個人設定 (gitignore 済み、permissions 等)
├── hooks/                          # シェルスクリプト hooks (LF 改行)
│   ├── ruff-format.sh              # PostToolUse: Python ファイル自動 format
│   ├── guard-bash.sh               # PreToolUse: 危険コマンドブロック
│   ├── prompt-guard.sh             # UserPromptSubmit: キーワード検出 → リマインダー
│   ├── stop-warn-uncommitted.sh    # Stop: 未コミット変更を警告
│   ├── session-env.sh              # SessionStart: env 変数 + ブランチ情報注入
│   └── test-guard-bash.sh          # guard-bash.sh の振る舞いテスト (pre-commit gate `guard-bash-behaviour` から実行)
├── skills/                         # ユーザー起動 skills (`/<name>` で実行)
│   ├── precheck/SKILL.md           # /precheck — lint + format + test 一括
│   ├── check-pr-ready/SKILL.md     # /check-pr-ready — PR 作成前の最終チェック
│   ├── commit/SKILL.md             # /commit — CLAUDE.md 準拠コミット
│   ├── create-pr/SKILL.md          # /create-pr — push → 構造化 PR 本文 → CI 監視 → review 返信 (gh pr create 直接実行は guard-bash が block)
│   ├── watch-pr/SKILL.md           # /watch-pr — PR push 後の CI 監視 auto chain
│   ├── check-review-backlog/SKILL.md # /check-review-backlog — open PR の未解決 review 集計
│   ├── run-tests/SKILL.md          # /run-tests — 各言語ランタイムテスト
│   ├── sync-docs/SKILL.md          # /sync-docs — エージェントチームによる全ドキュメント監査・更新
│   ├── create-pr/SKILL.md          # /create-pr — push → 構造化 PR 本文 → CI 監視 → review 対応 (一括)
│   ├── watch-pr/SKILL.md           # /watch-pr — 既存 PR の CI 集計 + 失敗分類 (create-pr フェーズ 5 の standalone 版)
│   ├── reply-review/SKILL.md       # /reply-review — レビューコメントに返信 + thread resolve
│   ├── check-review-backlog/SKILL.md # /check-review-backlog — open PR の未解決 review thread 集計 (read-only)
│   ├── release-prep/SKILL.md       # /release-prep — リリース前 version 状況確認 (read-mostly)
│   ├── prepare-release/SKILL.md    # /prepare-release — 9 manifest bump 案 + Swift checksum + tag 順序
│   ├── publish-model/SKILL.md      # /publish-model — 学習 ckpt → export + sanity + bench + HF upload
│   ├── eval-zs/SKILL.md            # /eval-zs — zero-shot SECS 評価の標準手順 (cross-utt + dual-encoder + Goodhart 検知)
│   ├── remote-train-ops/SKILL.md   # /remote-train-ops — リモート GPU instance の学習運用 (事故クラス 8 種の再発防止)
│   ├── check-preprocess-env/SKILL.md # /check-preprocess-env — 学習前処理環境の事前検証
│   ├── bump-deps/SKILL.md          # /bump-deps — ORT/openjtalk/ruff の canonical sync 更新
│   ├── watch-ci-patterns/SKILL.md  # /watch-ci-patterns — CI failure を flake/drift/env/test bug 分類
│   ├── check-loanword/SKILL.md     # /check-loanword — ZH-EN loanword mirror 同期検査
│   ├── check-pua/SKILL.md          # /check-pua — PUA テーブル / fixture / config 整合性検査
│   ├── check-runtime-parity/SKILL.md # /check-runtime-parity — 推論パス変更時の全ランタイム追従検査
│   ├── check-cross-runtime/SKILL.md  # /check-cross-runtime — Python canonical 変更の他ランタイム波及検査
│   ├── check-new-runtime-asset/SKILL.md # /check-new-runtime-asset — 新データアセットの package metadata 検査
│   └── skill-health/SKILL.md       # /skill-health — skill / hook の health check (meta)
└── commands/                       # 既存の slash commands (skills と併存可)
    ├── add-language.md             # 新言語追加ガイド
    └── review-language.md          # 10 エージェント並列レビュー
```

> 設計の全体像は repo root の [CLAUDE.md](../CLAUDE.md) `Automation` セクションを参照。 同セクションは本 README から逆方向リンクされている。

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

- `git push --force` / `--force-with-lease` to main/master
- `git push --no-verify` / `git commit --no-verify` (CLAUDE.md 禁止)
- `git commit --no-gpg-sign` (CLAUDE.md 禁止)
- `git reset --hard origin/main|master`
- `rm -rf /data/piper/output-*` / `rm -rf /data/piper/dataset-*` (学習データ保護)
- `epoch=*.ckpt` / `checkpoints/` の削除 (チェックポイント保護)
- `npm publish` (リリースワークフロー経由を強制)
- `git push` の hook bypass フラグ / main・master への `--force-with-lease` push
- `gh pr create` の直接実行 (`/create-pr` skill 内からの実行のみ許可)
- `eval_zs_secs` の `--encoder2` なし実行 (単一 encoder では Goodhart を検知
  できない — 2026-08 の same-utt 0.775 誤報 / Arm B 偽改善事故の再発防止。
  pytest / `--help` / `pre-commit run` / `ruff` / `git add` / `git diff` は
  対象外。手順: `/eval-zs` skill、契約:
  `docs/spec/zs-eval-contract.md`、pre-commit 側は `zs-prevention-gate` が
  防止テスト群の削除・改名を検出)

`echo`/`printf`/`cat`/`tee` で始まるコマンドは false-positive 防止のためチェックをスキップします (例: `echo 'git push --force main'` のようなデモ・テスト)。

## Pre-commit / pre-push gates

canonical 定義は [.pre-commit-config.yaml](../.pre-commit-config.yaml) (約 100 hook エントリ /
16 repo ブロック、うち 10 hook は `stages: [pre-push]`)。導入は clone 後 1 回:

```bash
pre-commit install                          # commit 時 gate
pre-commit install --hook-type pre-push     # push 時 gate (opt-in、推奨)
```

構成の内訳: cross-language formatter (ruff / gofmt / rustfmt / dotnet format /
clang-format / prettier)、contract gate 群 (`scripts/check_*.py`、PUA / loanword /
Swedish LID / phoneme-set / CHANGELOG / ORT バージョン等の同期検査)、および
zero-shot 学習事故由来の再発防止 gate。後者の主なもの:

| gate | trigger | 何を防ぐか |
|------|---------|-----------|
| `guard-bash-behaviour` | `.claude/hooks/(guard\|test-guard)-bash.sh` | guard-bash 判定ロジックの回帰 (`test-guard-bash.sh` を実行。shellcheck では検出不能な振る舞いを pin) |
| `test-threshold-relaxation` | テストの数値閾値の緩和 diff | 根拠 (`# threshold-relaxed: <根拠>`) なしの受け入れ基準緩和 (PQMF -90dB→5dB goalpost moving の再発防止) |
| `zs-prevention-gate` | 評価ガード面 + guard-bash.sh | zero-shot 防止テスト群・評価ガードの削除・改名 |
| `zs-metric-isolation-gate` | 学習コード / メトリクスモジュール | 学習コードからの評価メトリクス import (メトリクスの loss 流用は恒久禁止) |
| `export-path-unification` | `export_onnx.py` | main() への infer 経路手書き複製の再導入 (v11 の ONNX 話者条件断線事故の再発防止、`build_infer_forward` 一本化を強制) |

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

**エージェントチームで全ドキュメントを監査・更新**。コード変更に対して CLAUDE.md / README / CHANGELOG / docs/features / docstring / version drift の整合性を 7 エージェント並列で監査し、必要な更新を提案・適用します。

**推奨フロー**:

1. 実装・テスト追加
2. `/sync-docs` でドキュメント監査 → 承認後に自動更新
3. `/commit` でコミット
4. `/check-pr-ready` → `/create-pr` で PR 作成

**監査エージェント**:

- Agent 1: CLAUDE.md (実装済み機能・ファイルパス・API 表)
- Agent 2: ルート README (Features / Feature Support Matrix)
- Agent 3: ランタイム別 README (python_run, openjtalk-web, etc.)
- Agent 4: CHANGELOG (Unreleased セクション)
- Agent 5: docs/features / docs/spec
- Agent 6: docstring / JSDoc 整合性
- Agent 7: version drift (`docs/spec/release-versions.toml` canonical)

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

### `/create-pr [base-branch] [--title <title>] [--no-watch]`

push → `.github/pull_request_template.md` 準拠の PR 本文で PR 作成 → CI 監視ループ → review thread 返信 + resolve までを 1 skill の inline フェーズで行います (他 skill を chain しない)。 PR 本文は `pr-metadata.yml` の `pr-body-validate` step (Test Plan / Risk Level / Affected Components / Type) を通る形で生成します。 `gh pr create` の直接実行は guard hook が block するため、 PR 作成は本 skill 経由です。

### `/watch-pr [pr-number]` / `/check-review-backlog [--pr <N>]`

既存 PR の CI checks (`gh pr checks --json name,state,bucket,...`) と未解決 review thread を 1 回集計する standalone skill。 継続監視は `/loop /watch-pr <PR>`。 `/check-review-backlog` は全 open PR の未解決 thread を日数で絞って表示します (read-only)。

### その他の skill

| skill | 用途 |
|-------|------|
| `/release-prep` / `/prepare-release` | リリース前の version 確認 (read-mostly) と bump 適用案 + publish 順序ガイド |
| `/publish-model` | 学習 ckpt → ONNX export + sanity + RTF bench + HF upload |
| `/bump-deps` | ORT / openjtalk / ruff の canonical → mirror 同期 bump 案 |
| `/watch-ci-patterns` | workflow 単位の最近 run を集計し failure を flake / drift / env / test bug に分類 |
| `/check-loanword` / `/check-pua` / `/check-runtime-parity` / `/check-cross-runtime` / `/check-new-runtime-asset` | cross-runtime 同期検査 |
| `/skill-health` | skill / hook 自身の health check (frontmatter / script 参照 / trigger 衝突 / hook の shebang) |

## Pre-commit / pre-push gates

git hook 側の gate は `.pre-commit-config.yaml` に集約されています (hook 数は 119、 2026-10-26 時点)。 Claude Code の hooks (上記) とは別の仕組みで、 Claude を使わない commit / push にも効きます。

| 段階 | 有効化 | 主な内容 |
|------|--------|---------|
| commit 時 (default stage) | `pre-commit install` | ruff check + format、 PUA / loanword 等の contract gate (対象ファイル変更時のみ)、 `action-pin-gate`、 `test-threshold-relaxation`、 ruff version sync など |
| push 時 (`stages: [pre-push]`) | `pre-commit install --hook-type pre-push` (opt-in) | `pre-push-contract-gates` (loanword / PUA / language parity / CHANGELOG unreleased の 4 script を full-repo で実行)、 mypy-g2p、 cargo-clippy、 dotnet-format、 golangci-lint、 markdownlint-cli2、 codespell、 gitleaks、 hadolint、 editorconfig-checker |

個々の hook の trigger 条件 (`files:` / `stages:`) は `.pre-commit-config.yaml` の各 entry が正です。 CI 側では `.github/workflows/pre-commit.yml` が commit 段と pre-push 段 (`--hook-stage pre-push`) の hook を PR で実行し、 `lint-gates.yml` が contract gate 等を別 step で実行します。

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

```text
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

`.claude/skills/` の全 23 skill は **frontmatter 付き** で同じく slash command として動作します。

## 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — プロジェクト全体のルール
- [Claude Code hooks 公式ドキュメント](https://code.claude.com/docs/en/hooks)
- [Claude Code skills 公式ドキュメント](https://code.claude.com/docs/en/skills)
