---
name: sync-docs
description: コミット前にエージェントチームで全ドキュメント (CLAUDE.md / README / CHANGELOG / docs/) を監査し、コード変更に応じて自動更新します。大規模変更時の documentation drift を予防。
argument-hint: "[commit-range]"
disable-model-invocation: true
allowed-tools: Agent Bash(git diff *) Bash(git log *) Bash(git status *) Read Glob Grep Edit Write
---

# ドキュメント同期 (エージェントチーム並列監査)

コード変更に対して **CLAUDE.md / README / CHANGELOG / docs/features / docstring** を一括で監査し、更新が必要な箇所を検出して自動適用します。

## 前提

このスキルは **コミット前** に使うことを想定しています。コミット済みの変更と未ステージ変更の両方を対象にします。

## 入力

- `$ARGUMENTS` が空: `dev..HEAD` (現在のブランチの全変更) + 未コミット変更
- `$ARGUMENTS` = `staged`: ステージ済み変更のみ (`git diff --cached`)
- `$ARGUMENTS` = `HEAD~3..HEAD`: 特定のコミット範囲
- `$ARGUMENTS` = ファイルパス: そのファイルの変更のみ

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- dev との差分ファイル数: !`git diff --name-only dev..HEAD 2>/dev/null | wc -l | tr -d ' '`
- 未コミット変更: !`git status --short 2>/dev/null | wc -l | tr -d ' '`

## フェーズ 1: 変更サマリ収集

1. `git diff --name-only` で変更ファイルをカテゴリ分類:
   - **実装** (`src/python_run/piper/*.py`, `src/python/g2p/**`, `src/rust/piper-core/**`, `src/cpp/*.cpp`, `src/csharp/**`, `src/go/**`, `src/wasm/openjtalk-web/src/*.js`)
   - **テスト** (`*/tests/**`, `*/test/**`)
   - **ビルド** (`*.toml`, `*.json`, `CMakeLists.txt`, `*.yml`)
   - **ドキュメント** (`*.md`, `docs/**`)

2. 各カテゴリのファイル数と代表ファイルを記録

## フェーズ 2: 並列ドキュメント監査 (エージェントチーム)

以下の 6 エージェントを **1 メッセージで並列起動** します:

### Agent 1: CLAUDE.md 監査
**subagent_type**: `Explore`
**task**: CLAUDE.md の「実装済み機能」「重要なファイルパス」「OpenAI 互換 API」セクションを確認し、実装変更に対する追加・修正が必要か判定。新規モジュール/クラス/HTTP エンドポイント/テストファイルが未記載なら、具体的な diff を提案。

### Agent 2: ルート README 監査
**subagent_type**: `Explore`
**task**: `README.md`, `README_EN.md`, `README.*.md` (他言語) の Features / Interfaces / Feature Support Matrix を確認。新機能が各ランタイムで利用可能になった場合、対応 runtime 行を更新。

### Agent 3: ランタイム別 README 監査
**subagent_type**: `Explore`
**task**: `src/python_run/README.md`, `src/python_run/README_http.md`, `src/wasm/openjtalk-web/README.md`, `src/wasm/openjtalk-web/README.npm.md`, `src/rust/piper-cli/README.md`, `src/go/README.md` を確認。API 例・CLI フラグ・HTTP エンドポイントが最新か判定。

### Agent 4: CHANGELOG 監査
**subagent_type**: `Explore`
**task**: `CHANGELOG.md` と `src/wasm/openjtalk-web/CHANGELOG.md` の `[Unreleased]` セクションが、コード変更 (新機能/バグ修正/破壊的変更) を反映しているか確認。未反映なら具体的な markdown を提案。

### Agent 5: docs/features・docs/spec 監査
**subagent_type**: `Explore`
**task**: `docs/features/*.md` と `docs/spec/*.toml` / `*.md` を確認。新機能の専用ドキュメントが必要か、既存の仕様ファイル (ort-session-contract.toml, short-text-contract.toml, phoneme-timing-contract.toml など) の更新が必要か判定。

### Agent 6: docstring / JSDoc 整合性監査
**subagent_type**: `Explore`
**task**: 変更された公開 API (関数・クラス・メソッド) に docstring / JSDoc / TypeScript 型定義があるか確認。新規 public API に docstring がない、または既存の docstring が実装と齟齬している箇所を検出。

各エージェントには以下を渡します:
- 変更ファイル一覧 (フェーズ 1 の出力)
- 対象ディレクトリ
- 「読み取りのみ、変更提案は markdown diff 形式で報告」という指示

## フェーズ 3: 更新提案の統合

6 エージェントの結果を収集し、以下の形式で **統合レポート** を作成:

```
## ドキュメント監査結果

### 🔴 更新必須 (機能との不整合)
| ファイル | 問題 | 提案 |
|---------|------|------|
| CLAUDE.md | 新機能 X が未記載 | 「## 実装済み機能」に新セクション追加 |
| ... | ... | ... |

### 🟠 更新推奨 (品質向上)
| ファイル | 問題 | 提案 |
|---------|------|------|
| README.md | Feature matrix 未更新 | ... |

### 🟢 更新不要
(問題なしのファイル一覧)
```

## フェーズ 4: ユーザー確認 → 自動適用

1. 統合レポートをユーザーに提示
2. ユーザーの承認を得る (「適用してください」等)
3. 承認後、各エージェントが提案した変更を Edit tool で適用
4. 変更後、`git diff` で最終確認

## フェーズ 5: コミット準備

適用が完了したら、以下を表示:
- 更新されたファイルのリスト
- `/commit` skill を呼び出してコミットするよう促す
- または、ドキュメント更新を別コミットに分ける提案

## 注意事項

- **ユーザーの承認なしに勝手に適用しない** (フェーズ 3 → 4 の間で確認を取る)
- **既存の正しい記述を破壊しない** (削除・書き換えは最小限)
- **監査のみ要求された場合** (例: `/sync-docs --audit-only`) は フェーズ 4 をスキップ
- 大規模変更 (>500 行) では特に CLAUDE.md / CHANGELOG の更新を重点確認
- 新規 test ファイルが追加された場合、CLAUDE.md の「テスト」項目に件数を追記することを検討

## 実行例

```
/sync-docs
→ フェーズ 1-3 を実行し、監査レポートを提示
→ ユーザー承認後、フェーズ 4-5 を実行

/sync-docs staged
→ ステージ済み変更のみを監査

/sync-docs HEAD~3..HEAD
→ 直近 3 コミットを監査
```

## 期待効果

PR #349 で発生した「ドキュメント更新を一括で後付けする」パターンを、**コミット単位で小さく防止** します。エージェントチームを並列で動かすことで、6 観点の監査を短時間で完了できます。
