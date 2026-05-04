# T-10: 全体回帰テスト（全5ランタイムの統合テスト）

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01〜T-09 全て
**後続タスク:** なし（このタスクが最終）

---

## 1. タスク目的とゴール

T-01（コントラクト追記）から T-09（ドキュメント更新）までの全実装が完了した後、5つのネイティブランタイム（Python/Rust/Go/C#/C++）にわたって以下を保証するのがこのタスクの目的である。

1. **新規 EP テストが全て PASS**: `PIPER_EXECUTION_PROVIDER` 環境変数の読み取り・auto-detect ロジック・device_label 生成など、各ランタイムで追加したユニットテストが合格する。
2. **既存テストに回帰がない**: Hardware EP 対応の追加によって、以前から存在する warmup・キャッシュ・音声合成・G2P・SSML 等のテストが壊れていないことを確認する。
3. **CPU EP での E2E 合成が完了する**: `PIPER_EXECUTION_PROVIDER=cpu` を指定して CI 環境（GPU なし）でも各ランタイムが `test/models/multilingual-test-medium.onnx` を使った合成を完了できることを確認する。
4. **PR マージ可能な品質を担保**: 全ランタイムのテストが 0 失敗であることを確認した上で、`feat/hardware-ep` ブランチを `dev` にマージする準備を整える。

**完了の定義（Done 基準）:**
- Python/Rust/Go/C# の 4 ランタイムで `PIPER_EXECUTION_PROVIDER=cpu` 指定時のユニットテストが全て PASS
- Rust/Go/C# の各ランタイムで新規追加の env var テストが PASS
- C++ がビルドエラーなし、smoke test (`--provider auto`) が正常終了
- `git log --oneline feat/hardware-ep ^dev` で T-01〜T-09 の全コミットが一覧される
- CI の全ジョブ（ubuntu-24.04 CPU ランナー相当）がグリーン

---

## 2. 実装する内容の詳細

このタスクはコードの新規追加を行わない。T-01〜T-09 の成果物（変更済みファイル群）に対してテストを実行し、その結果を検証・記録・修正するフェーズである。

### 実施する作業

1. **Python 全テスト実行**: `src/python/tests/` と `src/python_run/tests/` の全テストスイートを実行し、T-02/T-03 で追加した `TestGetProviders` / `TestGetDeviceLabel` クラスを含めて全件 PASS を確認する。
2. **Rust 全テスト実行**: `src/rust/` ワークスペース全体の `cargo test` を実行し、T-04 で追加した `test_resolve_device_string_*` テスト群を含めて全件 PASS を確認する。
3. **Go 全テスト実行**: `src/go/` の `go test ./...` を実行し、T-05 で追加した `TestSelectDeviceWithEnv` / `TestConfigureSessionOptionsEnvVar` を含めて全件 PASS を確認する。
4. **C# 全テスト実行**: `src/csharp/` の `dotnet test` を実行し、T-06 で追加した `ResolveDevice_*` / `GetDeviceLabel_*` テスト群を含めて全件 PASS を確認する。
5. **C++ ビルドと smoke test**: `src/cpp/` の cmake ビルドが通ること、および `--provider auto` で `test/models/multilingual-test-medium.onnx` を合成できることを確認する。
6. **コミットログ確認**: `git log --oneline feat/hardware-ep ^dev` で全タスクのコミット（T-01〜T-09）が揃っていることを確認する。
7. **失敗テストへの対応**: テストが失敗した場合は根本原因を特定し、該当タスク（T-01〜T-09）の担当エージェントに修正を依頼するか、このタスク内で最小限の修正（シグネチャミス・import 漏れなど）を行う。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Test Orchestration Agent | 1 | 全ランタイムのテスト実行・結果集約・最終コミットログ確認・PR 作成準備 |
| Python QA Agent | 1 | Python (学習側・ランタイム側) の pytest 実行、失敗時の原因調査と最小修正 |
| Rust/Go QA Agent | 1 | Rust の cargo test・Go の go test 実行、失敗時の原因調査と最小修正 |
| C#/C++ QA Agent | 1 | C# の dotnet test・C++ の cmake ビルドと smoke test、失敗時の原因調査と最小修正 |

**合計 4 名。**Test Orchestration Agent は他 3 名の結果をまとめ、全ランタイムで 0 失敗であることを確認してから最終 PR チェックリストを完成させる。各 QA Agent は独立して並列実行できる。

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

- 全 5 ランタイム（Python/Rust/Go/C#/C++）のテスト実行と結果検証
- 失敗テストが存在する場合の最小修正（T-01〜T-09 の実装バグ修正のみ、新機能追加は行わない）
- C++ の cmake ビルドと `--provider auto` smoke test
- PR マージ前の最終チェックリスト完成

スコープ外: GPU/CoreML/DirectML/OpenVINO EP を使った実機テスト（CI の GPU ランナーは PR CI ではオプション。Release CI で実施）。

### Unit テスト（各ランタイム）

#### Python（pytest）

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
PIPER_EXECUTION_PROVIDER=cpu uv run pytest src/python/tests/ src/python_run/tests/ -v --tb=short
```

確認すべき新規テストクラス:
- `src/python/tests/test_ort_utils.py::TestGetProviders` — 13 テスト（auto 優先度・env var オーバーライド・TensorRT 除外・unknown EP フォールバック等）
- `src/python/tests/test_ort_utils.py::TestGetDeviceLabel` — 11 テスト（各 EP のラベル生成・env var オーバーライド等）

既存テストクラス（回帰確認）:
- `TestCreateSessionOptions`, `TestCreateSessionOptionsParams`, `TestPiperIntraThreadsEnv`, `TestGetLogicalCoreCount`
- `TestWarmup`, `TestModelCacheHelpers`, `TestModelCache`, `TestVoiceCacheParity`
- `src/python_run/tests/` 以下の短テキスト・SSML・タイミング等の全テスト

#### Rust（cargo test）

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/rust
PIPER_EXECUTION_PROVIDER=cpu cargo test --workspace 2>&1 | tail -20
```

確認すべき新規テスト（`piper-core`）:
- `gpu::tests::test_resolve_device_string_env_var_cpu`
- `gpu::tests::test_resolve_device_string_env_var_cuda`
- `gpu::tests::test_resolve_device_string_env_var_coreml`
- `gpu::tests::test_resolve_device_string_no_env_var_uses_param`
- `gpu::tests::test_resolve_device_string_empty_env_var_uses_param`
- `gpu::tests::test_resolve_device_string_auto_without_env`

既存テスト（回帰確認）:
- `gpu::tests::test_parse_*`（cpu/cuda/coreml/directml/tensorrt/auto/invalid）
- `gpu::tests::test_list_devices_*`
- `gpu::tests::test_configure_cpu_returns_cpu`
- `gpu::tests::test_*_fallback_without_feature`（CUDA/CoreML/DirectML/TensorRT feature 未有効時）

注意: Rust テストは環境変数を `std::env::set_var` で書き換えるため、`--test-threads=1` で直列実行することを推奨する。並列実行時に env var が競合するリスクがある。

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/rust
cargo test -p piper-core -- --test-threads=1 2>&1 | tail -30
```

#### Go（go test）

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/go
PIPER_EXECUTION_PROVIDER=cpu go test ./... -v 2>&1 | tail -20
```

確認すべき新規テスト（`piperplus` パッケージ）:
- `TestSelectDeviceWithEnv`（env var なし・cpu・cuda・coreml の各ケース）
- `TestConfigureSessionOptionsEnvVar`（`PIPER_EXECUTION_PROVIDER=cpu` でセッション構成が cpu になること）

既存テスト（回帰確認）:
- `TestParseDevice`（cpu/cuda/coreml/directml/tensorrt/auto/invalid/empty 等 16 ケース）
- `TestDeviceType_String`（各 DeviceType の String() 出力）

Go テストは `t.Setenv` を使用しているため並列実行（`go test -parallel`）でも env var 競合は発生しない。

#### C#（dotnet test）

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus/src/csharp
PIPER_EXECUTION_PROVIDER=cpu dotnet test --logger "console;verbosity=normal" 2>&1 | tail -20
```

確認すべき新規テスト（`PiperPlus.Core.Tests`）:
- `ResolveDevice_EnvVarCpu_ReturnsCpu`
- `ResolveDevice_EnvVarCoreML_ReturnsCoreML`
- `ResolveDevice_NoEnvVar_ReturnsParam`
- `GetDeviceLabel_CoreML_ReturnsCoreML`
- `GetDeviceLabel_DirectML_ReturnsDirectML0`
- `GetDeviceLabel_Cpu_ReturnsCpu`

既存テスト（回帰確認）:
- `PiperPlus.Core.Tests` 以下の全テスト（約 1,000 件）。`dotnet test --filter "FullyQualifiedName!~ResolveDevice&FullyQualifiedName!~GetDeviceLabel"` で既存テストのみを先に回すことも可能。

#### C++（cmake ビルド + smoke test）

```bash
cd /Users/inamotoyuuta/Desktop/piper-plus
cmake -B build/cpp -S src/cpp -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
cmake --build build/cpp --parallel 4 2>&1 | tail -10

# smoke test: CPU フォールバック確認
PIPER_EXECUTION_PROVIDER=cpu \
  build/cpp/piper \
  --model test/models/multilingual-test-medium.onnx \
  --provider auto \
  --output-raw - <<< "テスト" > /dev/null && echo "PASS"
```

C++ には xUnit 等のテストフレームワークによる自動テストが少ないため、ビルドエラーなし + smoke test PASS を成功基準とする。`src/cpp/tests/` に `test_c_api*.cpp` が存在する場合は合わせて実行する。

```bash
# C API テストが存在する場合
cmake -B build/cpp-test -S src/cpp -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON 2>&1 | tail -5
cmake --build build/cpp-test --parallel 4 && ctest --test-dir build/cpp-test --output-on-failure
```

### 統合テスト（E2E）

全ランタイムで共通の E2E 検証を行う。CI 環境（GPU なし）を想定し、`PIPER_EXECUTION_PROVIDER=cpu` を指定する。

**対象モデル:** `test/models/multilingual-test-medium.onnx`

| ランタイム | E2E コマンド例 | 確認内容 |
|---|---|---|
| Python | `PIPER_EXECUTION_PROVIDER=cpu uv run python -m piper_train.infer_onnx --model test/models/multilingual-test-medium.onnx --config test/models/multilingual-test-medium.onnx.json --output-dir /tmp/test-out --text "hello" --language ja-en --speaker-id 0` | 出力 WAV ファイルが生成されること |
| Rust CLI | `PIPER_EXECUTION_PROVIDER=cpu build/rust/piper-plus-cli --model test/models/multilingual-test-medium.onnx --output-raw - <<< "hello" > /dev/null` | 終了コード 0 |
| Go CLI | `PIPER_EXECUTION_PROVIDER=cpu go run src/go/cmd/piper-plus/main.go --model test/models/multilingual-test-medium.onnx --output-raw - <<< "hello" > /dev/null` | 終了コード 0 |
| C# CLI | `PIPER_EXECUTION_PROVIDER=cpu dotnet run --project src/csharp/PiperPlus.Cli -- --model test/models/multilingual-test-medium.onnx --output-raw -` | 終了コード 0 |
| C++ CLI | `PIPER_EXECUTION_PROVIDER=cpu build/cpp/piper --model test/models/multilingual-test-medium.onnx --provider auto --output-raw - <<< "hello" > /dev/null` | 終了コード 0 |

**出力品質の最低保証（Python のみ、他ランタイムは終了コードのみ確認）:**
- 出力 WAV に NaN が含まれないこと
- 出力の RMS > 0 であること（無音でないこと）
- CPU EP と数値比較は行わない（EP 間で FP 演算順序が異なるため許容誤差が大きい）

### 回帰テスト

既存テストが壊れていないことを確認するための実行手順:

```bash
# Python: 既存テストのみ（新規クラスを除外）
uv run pytest src/python/tests/ src/python_run/tests/ -v --tb=short \
  --ignore=src/python/tests/test_ort_utils.py -q
# さらに test_ort_utils.py の既存クラスのみ実行
uv run pytest src/python/tests/test_ort_utils.py \
  -k "TestCreateSessionOptions or TestWarmup or TestModelCache or TestVoiceCacheParity" -v

# Rust: 新規テストを除いた既存テスト
cd src/rust
cargo test -p piper-core -- --skip resolve_device_string --test-threads=1 2>&1 | tail -10

# Go: 新規テストを除いた既存テスト
cd src/go
go test ./piperplus/ -run "TestParseDevice|TestDeviceType_String" -v

# C#: 既存テストのみ
cd src/csharp
dotnet test --filter "FullyQualifiedName!~ResolveDevice&&FullyQualifiedName!~GetDeviceLabel" 2>&1 | tail -10
```

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **Rust env var テストの並列実行問題**: `std::env::set_var` はグローバル状態を変更するため、`cargo test` のデフォルト並列実行では `test_resolve_device_string_env_var_*` テストが互いに干渉するリスクがある。`--test-threads=1` で直列実行するか、テスト内の env var 操作に `serial_test` クレートを使う対策が必要。T-04 の実装時に `serial_test` の採用を検討したか確認する。

2. **Rust の `OnceLock` キャッシュと env var テストの干渉**: `gpu.rs` の `AUTO_DEVICE_CACHE` は `OnceLock` でプロセス内で一度だけ初期化される。`test_auto_detect_device_is_deterministic` や `test_resolve_device_string_auto_without_env` の実行順序によって `OnceLock` が事前に初期化され、env var を書き換えても `auto_detect_device()` の結果が変わらないケースがある。`resolve_device_string("auto")` が `OnceLock` キャッシュを参照する場合、env var による再検出が期待通りに動作しない可能性がある。T-04 の実装がこの問題を回避しているかを確認する。

3. **C# の環境変数分離**: `Environment.SetEnvironmentVariable` はプロセス全体に影響するため、`xUnit` の並列テスト実行との相性が悪い。T-06 で追加したテストがプロセスレベルの `Environment.SetEnvironmentVariable` を直接使用している場合は `[Collection("NonParallel")]` アトリビュートが必要になる。

4. **C++ の cmake ビルド環境**: `src/cpp/` は開発マシン（macOS/Linux）によってビルド結果が異なる。CI runner が `ubuntu-24.04` である場合、macOS ローカルでビルドが通っても CI でコンパイルエラーが発生するケースがある。特に CoreML EP 用の `#ifdef __APPLE__` ブロックと DirectML EP 用の `#if __has_include(<dml_provider_factory.h>)` ブロックが CI runner 上で正しく条件分岐されるかを確認する。

5. **テストモデルの存在確認**: E2E テストで使用する `test/models/multilingual-test-medium.onnx` が全 CI runner で利用可能であることを前提としている。CI の設定（`release.yml` / `test.yml`）でこのファイルが Git LFS または別途ダウンロードされているかを確認する。

6. **`PIPER_EXECUTION_PROVIDER=cpu` の伝播**: `uv run`、`cargo test`、`go test` はそれぞれサブプロセスを起動するため、`PIPER_EXECUTION_PROVIDER` が正しく継承されるかを事前に確認する。CI YML で `env:` ブロックを使って明示的に設定することを推奨する。

### レビューチェックリスト

- [ ] Python: `TestGetProviders::test_tensorrt_excluded_from_auto` が PASS しているか（TensorRT が auto-detect に含まれないことの確認）
- [ ] Python: `TestGetProviders::test_env_var_overrides_device_param` が PASS しているか（env var が device パラメータより優先されること）
- [ ] Rust: `test_resolve_device_string_env_var_*` テストが直列実行（`--test-threads=1`）で全件 PASS しているか
- [ ] Rust: `OnceLock` の `AUTO_DEVICE_CACHE` と `resolve_device_string()` の env var 読み取りが干渉していないか
- [ ] Go: `TestSelectDeviceWithEnv` が `t.Setenv` を使って env var を安全に設定・クリアしているか
- [ ] C#: `ResolveDevice_*` テストが `[Collection("NonParallel")]` またはこれに相当する方法で直列実行されているか
- [ ] C++: `cmake -DCMAKE_BUILD_TYPE=Release` でビルドエラーがないか（macOS と Linux 両方で確認）
- [ ] C++: `--provider auto` に対応する分岐が `piper.cpp` に存在し、`PIPER_EXECUTION_PROVIDER` env var が `main.cpp` で読まれているか
- [ ] 全ランタイム: `PIPER_EXECUTION_PROVIDER=cpu` 指定時に CPU EP が使われていることをログ（INFO レベル）で確認できるか
- [ ] コントラクト準拠: 各ランタイムの auto-detect 優先順位が `ort-session-contract.toml` の `auto_priority = ["CUDA", "CoreML", "DirectML", "OpenVINO", "CPU"]` に準拠しているか
- [ ] キャッシュラベル: 各ランタイムで `coreml` → `"coreml"`、`directml` → `"directml0"`、`tensorrt` → `"tensorrt0"` のラベルが生成されるか（コントラクトの `cache.extra_device_labels` との整合性）
- [ ] `git log --oneline feat/hardware-ep ^dev` で T-01〜T-09 の全コミットが一覧されるか（漏れがないか）
- [ ] `docs/spec/ort-versions.md` に EP 対応状況マトリクスが追記されているか（T-09 の成果物確認）

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

現行の T-10 は「実装が完了してからテストを実行する」という後付けの統合テストフェーズである。Green Field では、**コントラクトドリブンテスト（Contract-Driven Testing）**を中心に据え、仕様書（`ort-session-contract.toml`）が唯一の真実（Single Source of Truth）となる設計にする。全ランタイムのテストが仕様書の値を直接参照することで、実装のズレを PR マージ前に自動検出できる。

### アーキテクチャ

```
ort-session-contract.toml
     │
     ├── contract_test.py      (Python)  — tomllib でコントラクト読み込み → 実装値と比較
     ├── contract_test.rs      (Rust)    — toml crate で読み込み → 定数・関数の返り値と比較
     ├── ContractTest.cs       (C#)      — Tomlyn で読み込み → SessionFactory の返り値と比較
     ├── contract_test.go      (Go)      — toml ライブラリで読み込み → device.go の返り値と比較
     └── contract_test.cpp     (C++)     — header-only TOML パーサーで読み込み → piper.cpp の動作と比較
```

各言語のコントラクトテストは以下を自動検証する:
- `auto_priority` の順序が実装の EP_AUTO_PRIORITY 定数と一致すること
- `cache.extra_device_labels` の各値が `_get_device_label()` 等の返り値と一致すること
- `execution_provider.env.override_var` の値が各実装で参照する env var 名と一致すること

### CI/CD パイプライン設計

```yaml
# .github/workflows/hardware-ep.yml（理想形）
jobs:
  contract-check:
    # ort-session-contract.toml の構文検証 + 全ランタイムのコントラクトテスト
    # 全ランタイムのビルドより先に実行し、仕様不整合を早期検出
    runs-on: ubuntu-24.04
    steps:
      - name: Python contract test
        run: PIPER_EXECUTION_PROVIDER=cpu uv run pytest tests/contract/ -v
      - name: Rust contract test
        run: cargo test -p piper-core contract -- --test-threads=1
      - name: Go contract test
        run: PIPER_EXECUTION_PROVIDER=cpu go test ./piperplus/ -run Contract -v
      - name: C# contract test
        run: dotnet test --filter "Category=Contract"

  unit-test:
    needs: contract-check
    strategy:
      matrix:
        runtime: [python, rust, go, csharp]
    # ... 各ランタイムのユニットテスト

  smoke-test-cpu:
    needs: unit-test
    runs-on: ubuntu-24.04
    # PIPER_EXECUTION_PROVIDER=cpu での全ランタイム E2E テスト

  smoke-test-gpu:
    needs: unit-test
    runs-on: [self-hosted, gpu]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    # NVIDIA GPU での CUDA EP smoke test（release CI のみ）

  smoke-test-coreml:
    needs: unit-test
    runs-on: macos-14
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    # Apple Silicon での CoreML EP smoke test（release CI のみ）
```

### クロスランタイムテストの実装アプローチ

1. **コントラクトファイル読み込みユーティリティ**: 各言語で `ort-session-contract.toml` を読み込む薄いラッパーを用意し、テストコードから直接参照できるようにする。`docs/spec/ort-session-contract.toml` のパスを環境変数 `ORT_CONTRACT_PATH` で指定可能にする。

2. **パラメータ化テスト**: 各 EP（cpu/cuda/coreml/directml/openvino/tensorrt）に対するテストケースをパラメータとして定義し、コントラクトファイルから自動生成する。EP が追加された場合にテストも自動追加される。

3. **env var テストの安全な直列化**: Rust では `serial_test` クレート、C# では `ICollectionFixture` パターン、Go では `TestMain` での直列化を標準パターンとして全チームに共有する。

4. **smoke test の品質基準の定量化**: 現行は「RMS > 0 かつ NaN なし」だが、Green Field では PESQ/STOI スコアの下限値（CPU EP のスコアを基準として ±10% 以内）をコントラクトファイルに定義し、`tools/benchmark/` の MOS ベンチマークツールと統合する。

### 現行実装との主な差異

| 観点 | 現行 T-10 | Green Field |
|---|---|---|
| テスト起点 | 実装完了後に手動実行 | PR オープン時に自動実行 |
| 仕様との整合性確認 | レビューチェックリストで手動確認 | コントラクトテストで自動検証 |
| env var テストの安全性 | Rust で並列実行問題リスクあり | `serial_test` クレート等で標準化 |
| GPU EP のテスト | release CI でオプション | self-hosted ランナーで自動化 |
| smoke test の品質基準 | RMS > 0 + NaN なし | PESQ/STOI 下限値をコントラクトで定義 |
| C++ のテスト | cmake smoke test のみ | コントラクトテスト + C API テスト統合 |
| 障害の発見タイミング | マージ前の最終段階 | T-01〜T-09 の各 PR 時点 |

---

## 7. 後続タスクへの引き継ぎ事項

T-10 はこの Issue (#382) の最終タスクであり、PR マージ前の最終チェックリストを兼ねている。

### PR マージ前の最終チェックリスト

**コード変更の完全性**
- [ ] `docs/spec/ort-session-contract.toml` に `[execution_provider]` / `[execution_provider.env]` / `[cache.extra_device_labels]` が追記されている（T-01）
- [ ] `src/python/piper_train/ort_utils.py` の `get_providers()` と `_get_device_label()` が全 EP に対応している（T-02）
- [ ] `src/python_run/piper/voice.py` に `device: str = "auto"` パラメータが追加され、`use_cuda: bool` との後方互換が維持されている（T-03）
- [ ] `src/rust/piper-core/src/gpu.rs` に `resolve_device_string()` が追加され、`src/rust/piper-core/src/engine.rs` で使用されている（T-04）
- [ ] `src/go/piperplus/device.go` に `selectDeviceWithEnv()` が追加され、`configureSessionOptions()` の先頭で呼ばれている（T-05）
- [ ] `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` に `ResolveDevice()` / `GetDeviceLabel()` / `TryAppendCoreML()` / `AutoDetectAndConfigureEP()` が追加されている（T-06）
- [ ] `src/cpp/piper.cpp` に `provider == "auto"` の分岐、`src/cpp/main.cpp` に `PIPER_EXECUTION_PROVIDER` の読み取りが追加されている（T-07）
- [ ] `src/python_run/setup.py` の `extras_require` に `"directml"` と `"openvino"` グループが追加されている（T-08）
- [ ] `docs/spec/ort-versions.md` に EP 対応状況マトリクスが追記されている（T-09）

**テスト結果**
- [ ] Python: `uv run pytest src/python/tests/ src/python_run/tests/ -v --tb=short` — 0 failed
- [ ] Rust: `cargo test --workspace -- --test-threads=1` — `test result: ok. X passed; 0 failed`
- [ ] Go: `go test ./...` — `ok github.com/ayutaz/piper-plus/...`
- [ ] C#: `dotnet test` — 全 Passed
- [ ] C++: cmake ビルドエラーなし、`--provider auto` smoke test PASS

**コントラクト準拠**
- [ ] 全ランタイムの auto-detect 優先順位が `CUDA → CoreML → DirectML → (OpenVINO) → CPU` であること
- [ ] TensorRT が auto-detect に含まれないこと（明示指定のみ）
- [ ] OpenVINO が Python 以外でフォールバックすること

**ブランチ状態**
- [ ] `git log --oneline feat/hardware-ep ^dev` で T-01〜T-09 の全コミット（9 件以上）が一覧されること
- [ ] コンフリクトなし（`git diff dev...feat/hardware-ep --stat` で差分が想定範囲内であること）
- [ ] CI の全必須ジョブがグリーン

**この T-10 チェックリストが全て満たされた時点で、`feat/hardware-ep` → `dev` への PR をマージできる。**
