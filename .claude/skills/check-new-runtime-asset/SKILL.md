---
name: check-new-runtime-asset
description: 新規データアセット (JSON/TOML) を追加した PR で「7 箇所の package metadata 更新が全て揃っているか」を 1 コマンドで確認。MANIFEST.in / pyproject package-data / Cargo features / npm files / C# Content / Android assets / SPM resources の更新漏れを fail-fast。PR #397 (loanword wheel 漏れ) / PR #400 / PR #438 で繰り返された配布物欠落事故への対策。
disable-model-invocation: true
allowed-tools: Bash(git diff *) Bash(git status *) Bash(grep *) Bash(python *) Bash(uv run *)
---

<!-- editorconfig-checker-disable-file -->

# 新規ランタイムアセット配布チェック

新規 JSON/TOML データファイルを 1 つでも追加した PR で、各ランタイムの配布物
metadata に同期して載っているかを **PR 提出前に** 確認する。レビュアーが
毎回同じ指摘を出していた配布物欠落 (PR #397 で `zh_en_loanword.json` が
wheel 漏れ、PR #400 で Android assets DSL コメント、PR #438 で setup.py /
pyproject 分離) を local で潰すための skill。

## 何をチェックするか

1. `git diff --name-only origin/dev...HEAD` から **新規追加されたデータ
   ファイル** を検出する (`data/dictionaries/`、`src/python*/g2p/data/`、
   `tests/fixtures/`、`Sources/.../Resources/`、`android/.../assets/` 等)
2. 検出された各ファイルについて、以下 7 箇所の更新有無を grep で確認:
   - `MANIFEST.in` または `pyproject.toml [tool.setuptools.package-data]`
   - `src/python/g2p/MANIFEST.in` (G2P 独立 wheel)
   - `Cargo.toml` の `include` または `features.bundled-dicts`
   - npm `package.json` の `files`
   - C# `.csproj` の `<Content>` / `<EmbeddedResource>`
   - Android `build.gradle.kts` の `assets.srcDirs` (asset auto-bundle なら自動)
   - SPM `Package.swift` の `.process("Resources/...")`
3. 更新漏れがあれば file path と 修正例を提示

## 実行手順

### 1. 新規追加されたデータファイルを列挙

```bash
git diff --name-only --diff-filter=A origin/dev...HEAD | \
  grep -E '\.(json|toml|tsv|txt)$' | \
  grep -E '(data/|fixtures/|Resources/|assets/)' || \
  echo "新規データファイルなし — このチェックは skip 可"
```

### 2. 検出されたファイルごとに 7 箇所の grep を回す

```bash
# 例: src/python/g2p/piper_plus_g2p/data/new_dict.json を追加した場合
BASENAME=$(basename src/python/g2p/piper_plus_g2p/data/new_dict.json)

echo "=== MANIFEST.in / pyproject ==="
grep -rn "$BASENAME" MANIFEST.in src/python/g2p/MANIFEST.in src/python_run/MANIFEST.in 2>/dev/null
grep -rn "$BASENAME" pyproject.toml src/python_run/pyproject.toml src/python/g2p/pyproject.toml 2>/dev/null

echo "=== Cargo.toml ==="
grep -rn "$BASENAME" src/rust/*/Cargo.toml src/rust/*/src/*.rs 2>/dev/null

echo "=== npm files ==="
grep -rn "$BASENAME" src/wasm/*/package.json 2>/dev/null

echo "=== C# csproj ==="
grep -rn "$BASENAME" src/csharp/**/*.csproj 2>/dev/null

echo "=== Android assets ==="
grep -rn "$BASENAME" android/**/build.gradle.kts android/**/src/main/assets/ 2>/dev/null

echo "=== SPM Package.swift ==="
grep -rn "$BASENAME" Package.swift Sources/**/Resources/ 2>/dev/null
```

### 3. 既存 sync gate との連携

新規ファイルが「他ランタイムに mirror される」ものなら、対応する sync gate
(`scripts/check_loanword_consistency.py`、`scripts/check_pua_consistency.py`、
`scripts/check_dictionary_consistency.py` 等) に **canonical path と mirror
path を追加** する。新規 sync gate が必要なら `check_dictionary_consistency.py`
をテンプレートにコピーする。

```bash
# テンプレートをコピーして新規 sync gate を作る場合
cp scripts/check_dictionary_consistency.py scripts/check_<topic>_consistency.py
# PAIRS リストを編集 → CI workflow を追加 → .pre-commit-config.yaml に登録
```

## 確認すべき事項

- [ ] 新規追加データファイルが Python wheel/sdist の同梱対象 (MANIFEST.in or package-data)
- [ ] G2P 独立 wheel (`src/python/g2p/`) を使う場合は **G2P 側の MANIFEST.in** も更新
- [ ] Rust feature `bundled-dicts` を使う場合は `include_str!` のパスが正しい
- [ ] npm `files` フィールド (or デフォルト include されているか) を確認
- [ ] C# `<Content Include="..."><CopyToOutputDirectory>` または `<EmbeddedResource>` が必要
- [ ] Android なら `src/main/assets/` 配下にコピーされること
- [ ] SPM なら `Package.swift` の resources 宣言があること
- [ ] 該当する sync gate (`scripts/check_*_consistency.py`) に登録済み

## 関連ドキュメント

- [feedback_data_asset_distribution.md] (memory)
- [loanword sync](.claude/skills/check-loanword/SKILL.md)
- [dictionary sync](scripts/check_dictionary_consistency.py)
- [PUA sync](.claude/skills/check-pua/SKILL.md)
