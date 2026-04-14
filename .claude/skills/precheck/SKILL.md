---
name: precheck
description: PR 作成前の lint + format + test 一括実行。引数で scope (python/rust/cs/go/js/cpp/all) を指定可能。未指定なら git diff から自動判定。
argument-hint: "[python|rust|cs|go|js|cpp|all]"
disable-model-invocation: true
allowed-tools: Bash(uv run *) Bash(cargo *) Bash(dotnet *) Bash(go test *) Bash(go vet *) Bash(node *) Bash(npm *) Bash(cmake *) Bash(ctest *) Bash(git diff *) Bash(git status *)
---

# Pre-commit / Pre-PR チェック

`$ARGUMENTS` で指定されたスコープに対して、CI が実行するチェックと同等の検査をローカルで実行します。

## 変更ファイル

!`git diff --name-only HEAD 2>/dev/null | head -30`

## スコープ判定

引数 `$ARGUMENTS`:
- `python` → src/python/ + src/python_run/ のみ
- `rust` → src/rust/ のみ
- `cs` → src/csharp/ のみ
- `go` → src/go/ のみ
- `js` → src/wasm/openjtalk-web/ のみ
- `cpp` → src/cpp/ のみ
- `all` → 全ランタイム
- (空) → 上記の `git diff` の結果からスコープを推定 (複数該当ならそれら全て)

## 実行ステップ (該当スコープのみ)

### Python

```bash
# Lint
uv run ruff check src/python_run/ src/python/

# Format check
uv run ruff format --check src/python_run/ src/python/

# Unit tests (runtime + g2p)
cd src/python_run && uv run pytest tests/ -o addopts="" --tb=short -q && cd ../..
```

### Rust

```bash
cd src/rust
cargo fmt --all -- --check
cargo clippy --workspace --all-features -- -D warnings
cargo test -p piper-plus --no-fail-fast
cd ../..
```

### C# (.NET)

```bash
dotnet build src/csharp/PiperPlus.sln -c Release --nologo
dotnet format src/csharp/PiperPlus.sln --verify-no-changes --no-restore
dotnet test src/csharp/PiperPlus.sln -c Release --no-build --nologo --verbosity minimal
```

### Go

```bash
cd src/go
go vet ./... ./phonemize/...
go test -race -count=1 ./... ./phonemize/...
cd ../..
```

### JavaScript / WASM

```bash
cd src/wasm/openjtalk-web
npm run test:npm-package:all
cd ../../..
```

### C++

```bash
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

## 報告フォーマット

各ステップ完了後、以下の形式で結果を報告:

```
## Precheck 結果

| ステップ | 結果 | 詳細 |
|---------|------|------|
| Python ruff check | ✅ / ❌ | (失敗時はエラー要約) |
| Python ruff format | ✅ / ❌ | |
| Python pytest | ✅ / ❌ | (passed/failed/skipped カウント) |
| ... | ... | ... |
```

## 失敗時の対応

- **ruff format 失敗** → `uv run ruff format src/python_run/ src/python/` で自動修正
- **ruff check 失敗** → `uv run ruff check --fix src/python_run/ src/python/` で自動修正
- **pytest 失敗** → 失敗テストの最初の 3 件を要約して原因候補を提示
- **dotnet format 失敗** → `dotnet format src/csharp/PiperPlus.sln` で自動修正

## 注意

- pytest.ini に `--cov` が含まれていて pytest-cov が無い環境では `-o addopts=""` で上書きする (CLAUDE.md memory)
- 学習ジョブや巨大ベンチマークは実行しない (unit/integration のみ)
- 1 ステップでも失敗したら以降のステップは実行せず即報告 (`set -e` 相当)
