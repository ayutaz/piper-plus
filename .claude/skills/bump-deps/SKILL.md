---
name: bump-deps
description: ORT / openjtalk / ruff のような cross-runtime に canonical sync が必要な依存関係を 1 コマンドで bump する read-mostly skill。 既存の `check_ort_versions.py` / `check_openjtalk_version_sync.py` / `check_ruff_version_sync.py` が drift 検出後に「どこを何バージョンに上げる」を提示する逆方向 helper。
argument-hint: "<ort|openjtalk|ruff|all> --target <version> [--apply]"
disable-model-invocation: true
allowed-tools: Bash(uv run *) Bash(grep *) Bash(rg *) Bash(curl -s *) Bash(jq *) Bash(awk *) Bash(git diff *) Bash(git status *) Read Edit Grep
---

# Cross-Runtime Dependency Bump Skill

ORT / openjtalk / ruff のような「複数ファイル散在 / canonical source あり」 系の依存関係を、 canonical を更新したら mirror 箇所も同時に提案する skill。

既存の sync gate (`check_*_sync.py`) は drift を検出するだけ、 本 skill は drift を **解消する diff** を提示する。

memory `feedback_conservative_changes.md` に従い、 デフォルト dry-run、 markdown diff の提示のみ。 `--apply` で Edit を実行。

## 対象依存

| 名前 | Canonical | Mirror 数 | 既存 gate |
|------|-----------|---------|----------|
| ONNX Runtime | `cmake/OnnxRuntime.cmake` (ONNXRUNTIME_VERSION) | 6+ ファイル | check_ort_versions.py / check_ort_version_drift.py |
| openjtalk | `cmake/ExternalDeps.cmake` (URL 内の version) | 3+ ファイル | check_openjtalk_version_sync.py |
| ruff | `pyproject.toml` (dev group の最初の出現) | 6 箇所 | check_ruff_version_sync.py |
| (将来) | `cmake/...` (新 dep) | TBD | (新 gate) |

## 引数

- `$1` (必須): `ort` / `openjtalk` / `ruff` / `all`
- `--target X.Y.Z` (必須): 新 version
- `--apply`: dry-run の確認後 Edit を実行 (default は dry-run)

## 現在の状態

- ブランチ: !`git rev-parse --abbrev-ref HEAD`
- 引数: $ARGUMENTS

## フェーズ 1: 現状 + drift 確認

```bash
uv run python scripts/check_ort_versions.py --verbose 2>&1 | head -30
uv run python scripts/check_openjtalk_version_sync.py --verbose 2>&1 | head -20
uv run python scripts/check_ruff_version_sync.py 2>&1 | head -20
```

drift があれば「先に解消」を提案、 なければ「新 target への bump 案」を作る。

## フェーズ 2: ORT bump 案 (`ort` の場合)

```bash
# 6 ファイルの diff を生成
TARGET="$2"  # 例 1.18.0

# 1. cmake/OnnxRuntime.cmake
rg "set\(ONNXRUNTIME_VERSION" cmake/OnnxRuntime.cmake

# 2. .github/workflows/{ort-version-sync,release-shared-lib,android-build,release-kotlin-g2p,kotlin-g2p-ci,build-piper,_build-test-cpp}.yml
rg "ONNXRUNTIME_VERSION:" .github/workflows/ -l

# 3. docker/cpp-dev/Dockerfile
rg "ONNXRUNTIME_VERSION" docker/cpp-dev/Dockerfile

# 4. src/python/pyproject.toml + src/python_run/requirements*.txt
rg "onnxruntime[<>=~]" src/python/ src/python_run/

# 5. src/csharp/*.csproj
rg "Microsoft.ML.OnnxRuntime" src/csharp/

# 6. src/go/go.mod
rg "github.com/yalue/onnxruntime_go" src/go/go.mod

# 7. src/wasm/openjtalk-web/package.json
rg "onnxruntime-web" src/wasm/openjtalk-web/
```

各 hit の前後を markdown diff 形式で出力:

```diff
- set(ONNXRUNTIME_VERSION 1.17.1)
+ set(ONNXRUNTIME_VERSION 1.18.0)
```

## フェーズ 3: openjtalk bump 案 (`openjtalk` の場合)

`cmake/ExternalDeps.cmake` の URL pattern (例えば `pyopenjtalk-plus/archive/v0.4.1.post7.tar.gz`) と、 `src/python/pyproject.toml` / `requirements.txt` / `src/python/g2p/pyproject.toml` の `pyopenjtalk-plus==0.4.1.post7` を同期。

## フェーズ 4: ruff bump 案 (`ruff` の場合)

6 箇所同時更新:

1. `.pre-commit-config.yaml` `rev: v<VER>`
2. `.github/workflows/python-lint.yml` `pip install ruff==<VER>`
3. `.github/workflows/ci.yml` `uv pip install ... ruff==<VER>`
4. `pyproject.toml` 3 dependency group の `"ruff==<VER>"`

## フェーズ 5: 再検証

`--apply` で Edit を実行した後、 同じ check_*_sync.py を再走させて drift 0 を確認:

```bash
uv run python scripts/check_ort_versions.py
uv run python scripts/check_openjtalk_version_sync.py
uv run python scripts/check_ruff_version_sync.py
```

## フェーズ 6: 追加検証 (ORT の場合)

ORT bump は ABI 変更があり得るため、 以下の dependent check も走らせる:

```bash
# Python load test
uv run python -c "import onnxruntime; print(onnxruntime.__version__)"

# Rust load test
(cd src/rust && cargo check -p piper-core)

# 各 runtime CI workflow が pass しているか
gh run list --workflow=ci.yml --limit 5
```

## 注意

- **memory feedback_conservative_changes**: ORT は ABI 互換が崩れやすいため、 patch bump (`0.0.X`) のみ default、 minor / major bump は明示 `--target` 指定必須。
- **memory feedback_pin_actions_sha**: actions の SHA pin に類する操作はこの skill では行わない (`/check-action-pins` 別 skill)。
- **memory feedback_merge_caution**: `--apply` で Edit を実行する時はファイル単位で confirm。

## 使用例

```text
# ORT を 1.18.0 に bump (dry-run)
/bump-deps ort --target 1.18.0

# ruff を 0.16.0 に bump して即適用
/bump-deps ruff --target 0.16.0 --apply

# openjtalk patch bump
/bump-deps openjtalk --target 0.4.1.post8
```

## 期待効果

- ORT / openjtalk / ruff の **bump 漏れ** を check_*_sync.py に頼らず能動的に防ぐ
- canonical source → mirror への **手作業 grep + Edit を 1 skill 化**
- Dependabot uv-workspace PR (pyproject.toml だけ bump) のような **partial bump** に対する後追い fix
- ABI 互換確認の **post-bump dependent check**
