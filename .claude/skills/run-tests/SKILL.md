---
name: run-tests
description: piper-plus の各言語ランタイムのテストを実行します。引数 python/rust/cs/go/js/cpp/all で対象を選択。未指定なら git diff から自動判定。
argument-hint: "[python|rust|cs|go|js|cpp|all]"
disable-model-invocation: true
allowed-tools: Bash(uv run *) Bash(cargo test *) Bash(dotnet test *) Bash(go test *) Bash(go vet *) Bash(node --test *) Bash(npm *) Bash(cmake *) Bash(ctest *) Bash(git diff *)
---

# piper-plus テスト実行

各言語ランタイムのテストを CI と同じ条件でローカル実行します。

## 変更ファイル

!`git diff --name-only HEAD 2>/dev/null | head -20`

## ターゲット選択

`$ARGUMENTS`:
- `python` → Python 全体
- `rust` → Rust workspace
- `cs` → .NET solution
- `go` → Go module
- `js` → JS/WASM (npm-package)
- `cpp` → C++ (cmake build + ctest)
- `all` → 上記すべて (順次、失敗しても次に進む)
- (空) → `git diff HEAD` の結果から判定 (複数該当ならそれら全部)

## 各ターゲットの実行コマンド

### Python

```bash
cd src/python_run
uv run pytest tests/ -o addopts="" -v --tb=short
cd ../..

# G2P 単体テスト (もし対象なら)
cd src/python/g2p
uv run pytest -o addopts="" -v --tb=short
cd ../../..
```

**注意:**
- pytest.ini の `--cov` を `-o addopts=""` で上書き (pytest-cov が無い環境向け)
- 学習・ベンチマーク系テストは除外 (`-m "unit and not training and not benchmark"` も可)

### Rust

```bash
cd src/rust
cargo test -p piper-plus --no-fail-fast
cargo test -p piper-plus --features naist-jdic --no-fail-fast
cd ../..
```

### C# (.NET)

```bash
dotnet test src/csharp/PiperPlus.sln -c Release --nologo --verbosity minimal
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
# Build がまだなら先にビルド
if [ ! -f build/CMakeCache.txt ]; then
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTS=ON
fi
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

## 結果報告

各ターゲット完了後、以下の形式で報告:

```
## テスト実行結果

| ランタイム | Pass | Fail | Skip | 時間 |
|----------|------|------|------|------|
| Python (pytest) | 212 | 0 | 20 | 22s |
| Rust (cargo test) | 145 | 0 | 0 | 1m |
| ... | ... | ... | ... | ... |

### 失敗詳細
(失敗があった場合のみ、最初の 3 件まで)

- `test_xxx` (ファイル:行): エラー要約
```

## 失敗時のヒント

- **Python ImportError** → `uv sync` で依存をインストール
- **Rust feature not found** → `cargo build` で先にビルドを通す
- **C# build failed** → `dotnet restore src/csharp/PiperPlus.sln` を実行
- **WASM ImportError** → `cd src/wasm/openjtalk-web && npm install`
- **C++ ctest failed** → `cmake --build build --verbose` でビルドエラーを再確認

## 注意

- 失敗しても他のターゲットを続行する (`all` 時)
- 単一ターゲット時は失敗即停止
- 環境依存テスト (espeak-ng 等) はスキップされる場合あり
