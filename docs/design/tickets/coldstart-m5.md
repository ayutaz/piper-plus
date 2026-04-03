# COLD-M5: 事前最適化済みモデル配布

> **マイルストーン一覧:** [coldstart-milestones.md](./coldstart-milestones.md)
> **ブランチ:** `feat/coldstart-m5-preopt-model`
> **前提:** M1–M4 完了推奨（特に M1: ORT最適化レベル修正）
> **期間:** 2週間
> **担当:** Rust エンジニア 1名 + C# エンジニア 1名 + MLOps 担当 1名 + QA エンジニア 1名

---

## 目的とゴール

### 背景

ORT (ONNX Runtime) はセッション作成時にグラフ最適化を実行する。このフェーズはモデルサイズや最適化レベルに応じて **~300–500ms** を消費する。毎回起動するたびに同じ最適化を繰り返すのは無駄であり、結果をファイルにキャッシュすることで2回目以降の起動コストをゼロにできる。

ORT には `optimized_model_filepath` オプションが存在し、最適化済みグラフを `.onnx` ファイルとして保存できる。さらに `.ort` 形式（ORT 独自バイナリ）はロード自体も高速で、将来的な配布形式の候補となる。

### ゴール

| 指標 | 現状 | 目標 |
|------|------|------|
| 2回目以降の起動時グラフ最適化コスト | ~300–500ms | **0ms** |
| 最適化済みモデルの音声品質 | — | 元モデルと同等（回帰なし） |
| 最適化済みモデルの自動生成 | なし | 初回起動時に透過的に自動生成 |

---

## 実装する内容の詳細

### 1. Rust — `OnnxEngine::load()` に最適化キャッシュ追加

**ファイル:** `src/rust/piper-core/src/engine.rs:88–106`

現状の `OnnxEngine::load()` は毎回同じ最適化処理を実行している。デバイス種別ごとに最適化済みモデルのパスを決定し、存在すれば直接ロード、なければ最適化実行後に保存する。

```rust
// src/rust/piper-core/src/engine.rs
pub fn load(model_path: &Path, config: &VoiceConfig, device: &str) -> Result<Self, PiperError> {
    let device_type = crate::gpu::parse_device_string(device)
        .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;

    // デバイスラベルを付けた最適化済みモデルパスを生成
    // 例: model.onnx -> model.opt.cpu.onnx / model.opt.cuda.onnx
    let device_label = device_type_label(&device_type); // "cpu", "cuda", "dml", "coreml"
    let opt_stem = format!(
        "{}.opt.{}.onnx",
        model_path.file_stem().unwrap_or_default().to_string_lossy(),
        device_label
    );
    let optimized_path = model_path.with_file_name(opt_stem);

    let builder = Session::builder()
        .map_err(|e| PiperError::ModelLoad(e.to_string()))?
        .with_optimization_level(ort::GraphOptimizationLevel::Level3)
        .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

    let (mut builder, actual_device) =
        crate::gpu::configure_session_builder(builder, &device_type)
            .map_err(|e| PiperError::ModelLoad(format!("device config: {e}")))?;

    // 最適化済みモデルが存在する場合はそこからロード（最適化スキップ）
    // 存在しない場合は通常ロード + 最適化結果を保存
    let session = if optimized_path.exists() {
        tracing::info!("Loading pre-optimized model from {:?}", optimized_path);
        builder
            .commit_from_file(&optimized_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
    } else {
        tracing::info!("Optimizing model and saving to {:?}", optimized_path);
        builder
            .with_optimized_model_filepath(&optimized_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
            .commit_from_file(model_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
    };

    // ... 以下は既存コードのまま
}
```

`device_type_label()` ヘルパーを `engine.rs` または `gpu.rs` に追加:

```rust
fn device_type_label(device_type: &GpuDevice) -> &'static str {
    match device_type {
        GpuDevice::Cpu => "cpu",
        GpuDevice::Cuda(_) => "cuda",
        GpuDevice::DirectMl(_) => "dml",
        GpuDevice::CoreMl => "coreml",
        GpuDevice::TensorRt(_) => "tensorrt",
    }
}
```

**キャッシュ無効化オプション:** `OnnxEngine::load()` に `use_opt_cache: bool` 引数を追加するか、環境変数 `PIPER_DISABLE_OPT_CACHE=1` でバイパス可能にする。テスト環境では後者が便利。

---

### 2. C# — `SessionFactory.Create()` に最適化キャッシュ追加

**ファイル:** `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs:67–103`

現状の `Create()` は `GraphOptimizationLevel.ORT_DISABLE_ALL`（M1 で修正予定）のため最適化キャッシュと組み合わせて実装する。

```csharp
// src/csharp/PiperPlus.Core/Inference/SessionFactory.cs
public static InferenceSession Create(
    string modelPath,
    bool useCuda = false,
    int gpuDeviceId = 0,
    bool testMode = false,
    bool useOptCache = true,   // 新規追加
    ILogger? logger = null)
{
    // ... 既存のバリデーションコード ...

    var options = new SessionOptions();
    options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL; // M1 対応済み

    // デバイスラベルを決定
    string deviceLabel = useCuda ? "cuda" : "cpu";
    string optimizedPath = Path.ChangeExtension(
        modelPath,
        $".opt.{deviceLabel}.onnx");

    // 最適化キャッシュの設定
    if (useOptCache && !File.Exists(optimizedPath))
    {
        // 初回: 最適化実行 + キャッシュ保存
        options.OptimizedModelFilePath = optimizedPath;
        logger?.LogInformation("Optimizing model, saving to {OptimizedPath}", optimizedPath);
    }
    else if (useOptCache && File.Exists(optimizedPath))
    {
        // 2回目以降: 最適化済みモデルをロード
        logger?.LogInformation("Loading pre-optimized model from {OptimizedPath}", optimizedPath);
        modelPath = optimizedPath;
        // 最適化済みモデルのため最適化レベルを下げてロードコストを削減
        options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;
    }

    if (useCuda)
    {
        TryAppendCudaProvider(options, resolvedDeviceId, logger);
    }

    return new InferenceSession(modelPath, options);
}
```

**環境変数バイパス:** `PIPER_DISABLE_OPT_CACHE=1` で `useOptCache = false` にフォールバックする処理を追加。CI テスト環境では必須。

---

### 3. 最適化スクリプト / CLI コマンド提供

**ファイル:** `scripts/optimize_model.py` および `src/rust/piper-cli/src/main.rs`（新規 subcommand）

HuggingFace 配布モデルに事前最適化済みモデルを添付するためのスクリプトを提供する。

#### Python スクリプト

```python
# scripts/optimize_model.py
"""
使用例:
  python scripts/optimize_model.py model.onnx --device cpu
  python scripts/optimize_model.py model.onnx --device cuda
  # → model.opt.cpu.onnx, model.opt.cuda.onnx を生成
"""
import argparse
import onnxruntime as ort

def optimize(model_path: str, device: str, output_path: str | None = None):
    if output_path is None:
        stem = model_path.removesuffix(".onnx")
        output_path = f"{stem}.opt.{device}.onnx"

    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    opts.optimized_model_filepath = output_path

    providers = ["CPUExecutionProvider"]
    if device == "cuda":
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    ort.InferenceSession(model_path, opts, providers=providers)
    print(f"Optimized model saved to: {output_path}")
```

#### Rust CLI subcommand（オプション）

```rust
// src/rust/piper-cli/src/main.rs
// サブコマンド: piper-plus optimize <model.onnx> [--device cpu|cuda|dml]
// → 同ディレクトリに model.opt.<device>.onnx を生成
```

---

### 4. ORT バージョン管理戦略

最適化済みモデルは ORT バージョンに依存するため、バージョンが変わると再生成が必要になる。以下の管理戦略を実装する。

**バージョンスタンプファイル:** 最適化済みモデルと同じディレクトリに `{model}.opt.{device}.version` ファイルを生成し、ORT バージョン文字列を記録する。ロード時にバージョンが一致しない場合は再最適化する。

```rust
// Rust での実装例
fn check_opt_cache_valid(optimized_path: &Path, ort_version: &str) -> bool {
    let version_path = optimized_path.with_extension("version");
    fs::read_to_string(version_path)
        .map(|v| v.trim() == ort_version)
        .unwrap_or(false)
}
```

```csharp
// C# での実装例
private static bool IsOptCacheValid(string optimizedPath)
{
    var versionPath = Path.ChangeExtension(optimizedPath, ".version");
    if (!File.Exists(versionPath)) return false;
    var cachedVersion = File.ReadAllText(versionPath).Trim();
    return cachedVersion == OrtEnv.Instance().GetVersionString();
}
```

---

### 5. HuggingFace モデル配布フロー変更

**対象リポジトリ:** `ayousanz/piper-plus-tsukuyomi-chan`, `ayousanz/piper-plus-base`

新しい配布物レイアウト:

```
model.onnx              # 元モデル（必須）
model.opt.cpu.onnx      # CPU 最適化済み（推奨添付）
model.opt.cuda.onnx     # CUDA 最適化済み（GPU 環境向け）
model.config.json       # 設定ファイル（変更なし）
```

`scripts/optimize_model.py` を GitHub Actions のリリースワークフローに組み込む。

---

## エージェントチームの役割と人数

| 役割 | 人数 | 担当範囲 |
|------|------|---------|
| Rust エンジニア | 1名 | `engine.rs` の最適化キャッシュ実装、`device_type_label()` ヘルパー、バージョンスタンプ管理、Rust テスト |
| C# エンジニア | 1名 | `SessionFactory.cs` の最適化キャッシュ実装、バージョンスタンプ管理、C# テスト |
| MLOps 担当 | 1名 | `scripts/optimize_model.py` 作成、HuggingFace 配布フロー更新、GitHub Actions リリースワークフロー修正 |
| QA エンジニア | 1名 | 音声品質回帰テスト設計・実行、クロスプラットフォーム動作確認、パフォーマンス計測 |

---

## 提供範囲・テスト項目

### Unit テスト

#### Rust (`src/rust/piper-core/tests/`)

新規ファイル: `test_opt_cache.rs`

```rust
// 1. 最適化済みモデルが存在しない場合に自動生成されることを確認
#[test]
fn test_opt_cache_auto_generate() {
    // モデルロード後に .opt.cpu.onnx が生成されていることを確認
}

// 2. 最適化済みモデルが存在する場合にそこからロードされることを確認
#[test]
fn test_opt_cache_load_existing() {
    // 2回目のロードが1回目より速いことを確認
}

// 3. ORT バージョンが変わった場合に再生成されることを確認
#[test]
fn test_opt_cache_version_invalidation() {
    // バージョンスタンプが変わった場合に再最適化が走ることを確認
}

// 4. PIPER_DISABLE_OPT_CACHE=1 でキャッシュがスキップされることを確認
#[test]
fn test_opt_cache_env_bypass() {}

// 5. デバイス別ファイル名のラベルが正しいことを確認
#[test]
fn test_device_type_label() {
    assert_eq!(device_type_label(&GpuDevice::Cpu), "cpu");
    assert_eq!(device_type_label(&GpuDevice::Cuda(0)), "cuda");
    // ...
}
```

#### C# (`src/csharp/PiperPlus.Core.Tests/SessionFactoryTests.cs`)

既存ファイルに追加:

```csharp
// 1. 最適化済みモデルが存在しない場合に OptimizedModelFilePath が設定されることを確認
[Fact]
public void Create_GeneratesOptCachePath_WhenCacheMissing() { }

// 2. 最適化済みモデルが存在する場合にそのパスでロードされることを確認
[Fact]
public void Create_LoadsOptCache_WhenCacheExists() { }

// 3. PIPER_DISABLE_OPT_CACHE=1 でキャッシュが無効化されることを確認
[Fact]
public void Create_SkipsOptCache_WhenEnvVarSet() { }

// 4. バージョン不一致時に再最適化が実行されることを確認
[Fact]
public void Create_RegeneratesOptCache_WhenVersionMismatch() { }
```

### E2E テスト

| テスト | 内容 | 合否基準 |
|--------|------|---------|
| 初回ロード → `.opt.cpu.onnx` 生成確認 | `model.onnx` ロード後にキャッシュファイルが存在すること | ファイル生成を確認 |
| 2回目ロード時間計測 | 1回目と2回目のロード時間を比較 | 2回目が ~300ms 以上短縮 |
| 最適化前後の音声品質比較 | 同一テキスト・パラメータで音声を生成し波形を比較 | RMS 誤差が 1% 未満 |
| CUDA/CPU クロス動作防止確認 | CPU 最適化済みモデルを CUDA セッションでロードしないことを確認 | デバイスラベルが一致しないと別ファイルを使用 |
| `PIPER_DISABLE_OPT_CACHE=1` バイパス | 環境変数設定時にキャッシュを生成・参照しないこと | `.opt.*.onnx` が生成されない |
| ORT バージョン変更後の再生成 | バージョンスタンプを改ざんしてロードし、再最適化が走ることを確認 | 新しいキャッシュファイルが生成される |

### 音声品質回帰テスト

既存の `src/csharp/PiperPlus.Core.Tests/InferenceTests.cs` および `src/rust/piper-core/tests/test_voice_api.rs` に対して、最適化済みモデル使用時の出力が元モデルと同一（またはビット一致）であることを確認するテストケースを追加する。

---

## 実装に関する懸念事項とレビュー項目

### ORT バージョン依存性（リスク: 高）

最適化済みモデルは ORT のメジャー/マイナーバージョンに依存する。バージョンアップ時に古いキャッシュをロードすると、サイレントに誤動作する可能性がある。

**レビュー項目:**
- バージョンスタンプの比較粒度（メジャー.マイナーのみか、パッチバージョンも含むか）を決定する
- ORT バージョン文字列を取得する API が Rust (`ort` crate) / C# (`OrtEnv`) の両方で利用可能か確認する
- バージョン不一致時に古いキャッシュを削除するか、そのまま残すかを決定する（削除推奨）

### デバイス別モデル管理（リスク: 中）

CPU/CUDA/DirectML/CoreML/TensorRT それぞれで最適化済みモデルが異なり、デバイスをまたいでロードすると動作しない（最悪クラッシュ）。

**レビュー項目:**
- ファイル名規則 `model.opt.{device}.onnx` を正式仕様として文書化する
- デバイス情報をファイルヘッダやメタデータとして埋め込む方法（ORT API で可能か）を調査する
- DirectML は `dml` ラベルとするか、デバイス番号も含めるか（例: `dml0`）を決定する

### ディスク容量（リスク: 低〜中）

最適化済みモデルは元モデルの 1–1.5x サイズになる可能性がある。つくよみちゃんモデル (~37MB FP16) であれば ~55MB。デバイス 3種類分で計 ~165MB 追加消費となる。

**レビュー項目:**
- キャッシュの保存先をモデルと同じディレクトリに固定するか、`~/.piper/cache/` などに分離するか検討する（書き込み権限の問題が生じる場合は後者）
- モデルと同じディレクトリが読み取り専用の場合のフォールバック先を定義する（例: `$XDG_CACHE_HOME/piper/`）

### `.ort` 形式（リスク: 高）

`.ort` 形式は ORT の Experimental API であり、API が変更される可能性がある。現時点では `.opt.onnx` に留め、`.ort` 形式は将来のフェーズに先送りすることを推奨する。

**レビュー項目:**
- ORT 1.x での `.ort` 形式の安定性を確認し、安定版になり次第 M6 以降で対応する

### HuggingFace 配布フロー変更（リスク: 中）

リリース時に複数デバイス向けの最適化済みモデルを生成するため、GitHub Actions の実行時間とリソース使用量が増加する。

**レビュー項目:**
- CPU 最適化のみを必須とし、CUDA/DirectML はオプション扱いにする（CI コスト削減）
- HuggingFace への自動プッシュ権限が GitHub Actions に付与されているか確認する

---

## 一から作り直すとしたら

M5 の本質は「グラフ最適化結果の再利用」であり、現在の設計は ORT の既存機能 (`optimized_model_filepath`) に乗っかる形のため根本的には正しい。しかしゼロから設計するとすれば以下のアーキテクチャを選択する。

### モデルキャッシュマネージャとして分離する

現状の設計では `OnnxEngine::load()` と `SessionFactory.Create()` にキャッシュロジックが直接埋め込まれる。これを `ModelCacheManager` / `OptimizedModelCache` として独立したコンポーネントに分離する。

```
ModelCacheManager
  ├── cache_key(model_path, device, ort_version) → hash
  ├── cache_dir() → XDG_CACHE_HOME/piper/ or ~/.piper/cache/
  ├── lookup(key) → Option<PathBuf>
  └── store(key, optimized_path)
```

この設計にすれば:
- キャッシュ保存先がモデルディレクトリの書き込み権限に依存しない
- バージョン管理が hash ベースになりシンプル
- 複数モデルのキャッシュを一元管理できる
- テスト時の差し替えが容易

### `.ort` 形式をデフォルトにする

`optimized_model_filepath` で `.onnx` を生成するのは中間段階で、最終的には `.ort` 形式 (ORT の Flatbuffers ネイティブ形式) にすることでロード時間自体も短縮できる。ORT が `.ort` を安定 API として提供するまで待つよりも、Experimental API として使いながら回帰テストで安全性を担保する選択もある。

### 事前最適化を配布時の責務にする

ランタイムでの「初回最適化 + 保存」より、HuggingFace リポジトリに最適化済みモデルを事前配置する方が UX として優れている。ランタイムキャッシュはインターネット非接続環境やカスタムモデル向けのフォールバックと位置付ける。

---

## 後続タスクへの連絡事項

### M6 への依存関係

M6 の GPU 検出キャッシュ (`gpu.rs:auto_detect_device()`) と M5 のデバイスラベル決定ロジックは密接に関連する。M5 完了後に M6 を実装する際、`device_type_label()` の命名規則を共有する。

### HuggingFace 配布変更の周知

M5 実装後、以下の変更をリリースノートおよびリポジトリ README に記載する:

- `model.opt.cpu.onnx` を手動で削除した場合の再生成手順
- `PIPER_DISABLE_OPT_CACHE=1` の用途（CI 環境、デバッグ）
- デバイス別モデルの命名規則

### C#/Rust の統一

`SessionFactory.Create()` と `OnnxEngine::load()` のキャッシュ動作を統一し、同じ環境変数 (`PIPER_DISABLE_OPT_CACHE`) でバイパスできるようにする。仕様差異はゼロにすること。

### 計測結果の記録

PR に以下の計測結果を記載すること:

```
環境: Windows 11 / Intel Core i7-12700K / 32GB RAM
モデル: tsukuyomi-6lang-v2-fixed.onnx (37MB FP16)

1回目ロード時間 (最適化 + 保存):
  Rust:  XXXms
  C#:    XXXms

2回目ロード時間 (キャッシュ使用):
  Rust:  XXXms (→ -XXXms, -XX%)
  C#:    XXXms (→ -XXXms, -XX%)

最適化済みモデルサイズ: XXXmB (元モデル比 X.Xx)
```
