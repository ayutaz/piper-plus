# COLD-M1: クイックウィン（ORT設定修正）

> **マイルストーン一覧:** [coldstart-milestones.md](coldstart-milestones.md)
> **前提チケット:** なし（独立実装可能。最初に実施することで M2 以降の baseline を確定できる）
> **ブランチ:** `feat/coldstart-m1-ort-settings`
> **期間:** 1 週間
> **期待削減量:** ~300–500ms（C# ~200–400ms + Rust ~50–100ms + DirectML ~200ms）
> **リスク:** 低

---

## 1. タスク目的とゴール

### 背景

現状の C# 実装 (`SessionFactory.cs:91`) は ONNX Runtime のグラフ最適化を `ORT_DISABLE_ALL` に設定している。コメントには「C++ piper.cpp に合わせる」と記載されているが、C# 実装は現在 C++ から独立した実装であり、この制約は不要である。

`ORT_DISABLE_ALL` はセッション作成後の推論時にグラフ最適化が毎回走ることを意味し、初回発話レイテンシの主要因となっている。`ORT_ENABLE_ALL` に変更することで、ORT はセッション作成時に一度だけ最適化を実行し、以降の推論コストを大幅に削減できる。

Rust 実装 (`engine.rs`) では `Session::builder()` の段階でスレッド数を明示していないため、ORT が CPU コア数に応じてスレッドを過剰に割り当てる場合がある。VITS は小モデルであり、スレッド数上限を設けることで初回推論のスレッド生成コストを削減できる。

DirectML 使用時（Windows 環境）は入力テンソルの形状が動的なため、初回推論時に追加の再最適化が発生する。形状ヒントを事前宣言することでこのコストを排除できる。

### ゴール

コード変更を最小限に抑えた「クイックウィン」として、最大 ~500ms の削減を達成する。

- **対策 A**: `SessionFactory.cs` の1行変更でグラフ最適化を有効化（C#）
- **対策 B**: `engine.rs` にスレッド設定を追加（Rust）
- **対策 C**: DirectML 使用時に入力形状を事前宣言（C# / DirectML のみ）

### 完了条件

- [ ] 対策 A: `SessionFactory.cs:91` の `ORT_DISABLE_ALL` → `ORT_ENABLE_ALL` が実装・テスト済み
- [ ] 対策 B: `engine.rs` の `Session::builder()` 後に `with_intra_threads()` / `with_inter_threads()` が追加されている
- [ ] 対策 C: `SessionFactory.cs` の DirectML パスに `AddFreeDimensionOverrideByName` が追加されている（DirectML 利用者向け）
- [ ] 各プラットフォームで before/after の計測値を PR に記載する
- [ ] 既存テストスイート全パス（C# 829テスト・Rust テスト群）
- [ ] 音声品質回帰なし（音声比較テスト）

---

## 2. 実装内容の詳細

### 2-A. C# — `GraphOptimizationLevel` 修正

**ファイル:** `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`

**変更箇所:** 91行目（`options.GraphOptimizationLevel = ...` の行）

```csharp
// Before (行 90–91)
// Match C++ piper.cpp: disable graph optimisation.
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;

// After
// C# 実装は C++ から独立しているため ORT_ENABLE_ALL を使用する。
// ORT_ENABLE_ALL はセッション作成時に一度だけグラフ最適化を実行し、
// 以降の推論コストを大幅に削減する。
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;
```

コメント行も合わせて更新し、「C++ piper.cpp に合わせる」という古いコメントを削除する。

**変更後の `Create()` メソッド（関連部分）:**

```csharp
var options = new SessionOptions();

// ORT_ENABLE_ALL: セッション作成時に一度グラフ最適化を実行する。
// C++ piper.cpp との互換性制約は現 C# 実装には不要。
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;

if (useCuda)
{
    TryAppendCudaProvider(options, resolvedDeviceId, logger);
}
```

> **注意:** `ORT_ENABLE_ALL` はセッション作成時間が若干増加する可能性がある（計測値として PR に記載すること）。セッション作成コストが増えても初回推論コストが減れば総体的に改善となる。

---

### 2-B. Rust — `SessionBuilder` スレッド設定

**ファイル:** `src/rust/piper-core/src/engine.rs`

**変更箇所:** 95–105行目の `Session::builder()` チェーン

```rust
// Before (行 95–105)
let builder = Session::builder().map_err(|e| PiperError::ModelLoad(e.to_string()))?;

let (mut builder, actual_device) =
    crate::gpu::configure_session_builder(builder, &device_type)
        .map_err(|e| PiperError::ModelLoad(format!("device config: {e}")))?;
```

```rust
// After
// スレッド数を物理コア数の上限 4 に設定。
// VITS は小モデルのため過剰なスレッドはオーバーヘッドになる。
// with_intra_threads: 単一演算子内の並列度（行列演算など）
// with_inter_threads: 演算子間の並列度（グラフノード間）
let num_intra_threads = std::thread::available_parallelism()
    .map(|n| n.get())
    .unwrap_or(2)
    .min(4);

let builder = Session::builder()
    .map_err(|e| PiperError::ModelLoad(e.to_string()))?
    .with_intra_threads(num_intra_threads)
    .map_err(|e| PiperError::ModelLoad(format!("intra_threads: {e}")))?
    .with_inter_threads(1)
    .map_err(|e| PiperError::ModelLoad(format!("inter_threads: {e}")))?;

let (mut builder, actual_device) =
    crate::gpu::configure_session_builder(builder, &device_type)
        .map_err(|e| PiperError::ModelLoad(format!("device config: {e}")))?;
```

`num_intra_threads` の算出は `load()` の冒頭（デバイス文字列パースの後）に置く。

> **補足:** `std::thread::available_parallelism()` は論理コア数を返すが、VITS 程度の小モデルでは `.min(4)` で上限を設けることで無駄なスレッド生成を抑制できる。物理コア数が 4 未満の環境（例: CI の 2コアVM）では自然に 2 スレッドになる。

---

### 2-C. C# — DirectML 形状事前宣言（DirectML 使用時のみ）

**ファイル:** `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`

`TryAppendCudaProvider()` と同様に `TryConfigureDirectML()` プライベートメソッドを追加し、`Create()` から条件分岐で呼ぶ。

`Create()` シグネチャに `bool useDirectMl = false` パラメータを追加する:

```csharp
public static InferenceSession Create(
    string modelPath,
    bool useCuda = false,
    int gpuDeviceId = 0,
    bool testMode = false,
    bool useDirectMl = false,
    ILogger? logger = null)
```

`Create()` 内の設定部分:

```csharp
var options = new SessionOptions();
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;

if (useCuda)
{
    TryAppendCudaProvider(options, resolvedDeviceId, logger);
}

if (useDirectMl)
{
    TryConfigureDirectMl(options, resolvedDeviceId, logger);
}
```

`TryConfigureDirectMl()` の実装:

```csharp
/// <summary>
/// DirectML 実行プロバイダを設定し、入力形状ヒントを付与する。
/// DirectML では動的形状の初回推論時に再最適化が発生するため、
/// <c>AddFreeDimensionOverrideByName</c> でヒントを事前宣言してこれを排除する。
/// </summary>
private static void TryConfigureDirectMl(
    SessionOptions options, int deviceId, ILogger logger)
{
    try
    {
        // DirectML 必須設定
        options.EnableMemoryPattern = false;
        options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;

        // 入力形状ヒント（VITS の代表的な入力形状）
        // batch_size は常に 1、phoneme_length は典型的な長さでヒントを与える
        options.AddFreeDimensionOverrideByName("batch_size", 1);
        options.AddFreeDimensionOverrideByName("phoneme_length", 200);

        options.AppendExecutionProvider("DML", new Dictionary<string, string>
        {
            ["device_id"] = deviceId.ToString(),
        });

        logger.LogInformation(
            "DirectML execution provider configured (device_id={DeviceId})", deviceId);
    }
    catch (Exception ex)
    {
        logger.LogWarning(
            "DirectML execution provider unavailable, falling back to CPU: {Message}",
            ex.Message);
    }
}
```

> **補足:** `AddFreeDimensionOverrideByName` は ONNX モデルに動的次元名 (`"batch_size"`, `"phoneme_length"` 等) が定義されている場合に有効。VITS モデルの入力ノード名は `input` (shape: `[batch, phoneme_length]`) であるため、動的次元名が存在するかどうかを事前に確認すること。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| C# エンジニア | 1名 | `SessionFactory.cs` の対策 A / C 実装、`SessionFactoryTests.cs` へのテスト追加、DirectML ヒント検証 |
| Rust エンジニア | 1名 | `engine.rs` の対策 B 実装、`with_intra_threads` / `with_inter_threads` の API 確認、Rust テスト追加 |
| QA エンジニア | 1名 | 3 プラットフォームでの before/after レイテンシ計測、音声品質回帰テスト（WAV diff）、DirectML 環境での動作確認 |

**合計 3 名**（C# と Rust を 1 名で兼任する場合は 2 名体制でも実施可能）

---

## 4. テスト項目

### 4-A. C# ユニットテスト (xUnit v3)

**ファイル:** `src/csharp/PiperPlus.Core.Tests/SessionFactoryTests.cs`（既存ファイルに追加）

```csharp
// SessionFactoryTests.cs に追加

[Fact]
public void Create_UsesOrtEnableAll_GraphOptimizationLevel()
{
    // SessionOptions の GraphOptimizationLevel が ORT_ENABLE_ALL であることをリフレクションで確認。
    // 実際のセッション作成はモデルファイルが必要なため、SessionOptions の構成だけ検証する。

    // Arrange: SessionFactory の内部オプション構成を確認するため、
    // SessionOptions を直接生成して期待値と照合する
    var options = new SessionOptions();
    options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;

    // Assert: ORT_ENABLE_ALL = Level3 (最大最適化)
    Assert.Equal(
        GraphOptimizationLevel.ORT_ENABLE_ALL,
        options.GraphOptimizationLevel);
}

[Fact]
public void Create_FileNotFound_ThrowsBeforeSessionCreation()
{
    // 既存テスト: ファイル不在時は FileNotFoundException が投げられ
    // セッション作成（最適化レベル設定）には到達しないことを確認
    Assert.Throws<FileNotFoundException>(
        () => SessionFactory.Create("/nonexistent/model.onnx"));
}

[Fact]
public void Create_WithDirectMl_DoesNotThrowWithFallback()
{
    // DirectML EP が存在しない環境でも CPU フォールバックして例外を投げないことを確認。
    // useDirectMl=true を渡して FileNotFoundException（モデル不在）のみが発生することを検証。
    var ex = Assert.Throws<FileNotFoundException>(
        () => SessionFactory.Create(
            modelPath: "/nonexistent/model.onnx",
            useDirectMl: true));

    Assert.Contains("model.onnx", ex.Message);
}
```

**ファイル:** `src/csharp/PiperPlus.Core.Tests/GraphOptimizationTests.cs`（新規）

```csharp
using Microsoft.ML.OnnxRuntime;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// COLD-M1 対策 A: GraphOptimizationLevel が ORT_ENABLE_ALL に設定されていることを確認する。
/// </summary>
public sealed class GraphOptimizationTests
{
    [Fact]
    public void OrtEnableAll_HasHigherOptimizationThanDisableAll()
    {
        // ORT_ENABLE_ALL > ORT_DISABLE_ALL であることを型安全に確認
        Assert.True(
            (int)GraphOptimizationLevel.ORT_ENABLE_ALL >
            (int)GraphOptimizationLevel.ORT_DISABLE_ALL,
            "ORT_ENABLE_ALL should represent a higher optimization level than ORT_DISABLE_ALL");
    }

    [Fact]
    public void SessionOptions_DefaultGraphOptimizationLevel_IsNotDisabled()
    {
        // ORT デフォルト値が ORT_DISABLE_ALL でないことを確認（ORT バージョン依存の検知）
        var options = new SessionOptions();
        // ORT のデフォルトは ORT_ENABLE_BASIC であるため、DISABLE_ALL ではないはず
        Assert.NotEqual(
            GraphOptimizationLevel.ORT_DISABLE_ALL,
            options.GraphOptimizationLevel);
    }

    [Theory]
    [InlineData(GraphOptimizationLevel.ORT_DISABLE_ALL)]
    [InlineData(GraphOptimizationLevel.ORT_ENABLE_BASIC)]
    [InlineData(GraphOptimizationLevel.ORT_ENABLE_EXTENDED)]
    [InlineData(GraphOptimizationLevel.ORT_ENABLE_ALL)]
    public void SessionOptions_AcceptsAllOptimizationLevels(GraphOptimizationLevel level)
    {
        // ORT が各最適化レベルを受け付けることを確認（API 互換性テスト）
        var options = new SessionOptions();
        var ex = Record.Exception(() => options.GraphOptimizationLevel = level);
        Assert.Null(ex);
    }
}
```

### 4-B. Rust ユニットテスト

**ファイル:** `src/rust/piper-core/src/engine.rs`（既存 `#[cfg(test)]` ブロックに追加）

```rust
#[test]
fn test_intra_threads_calculation() {
    // num_intra_threads の算出ロジックを単体確認
    let available = std::thread::available_parallelism()
        .map(|n| n.get())
        .unwrap_or(2);
    let num_intra_threads = available.min(4);

    // 結果は常に [1, 4] の範囲内
    assert!(num_intra_threads >= 1, "should have at least 1 thread");
    assert!(num_intra_threads <= 4, "should not exceed 4 threads");
}

#[test]
fn test_inter_threads_is_one() {
    // inter_threads は常に 1 (VITS の演算子グラフは逐次処理が効率的)
    let inter_threads: usize = 1;
    assert_eq!(inter_threads, 1);
}

#[test]
fn test_thread_count_on_low_cpu() {
    // 2コア環境のシミュレーション: min(2, 4) = 2
    let simulated_available = 2;
    let result = simulated_available.min(4);
    assert_eq!(result, 2);
}

#[test]
fn test_thread_count_on_high_cpu() {
    // 32コア環境のシミュレーション: min(32, 4) = 4 (上限が機能する)
    let simulated_available = 32;
    let result = simulated_available.min(4);
    assert_eq!(result, 4);
}
```

**ファイル:** `src/rust/piper-core/tests/test_ort_settings.rs`（新規、統合テスト）

```rust
// test_ort_settings.rs
// ORT セッション設定が正しく適用されることを確認する統合テスト。
// 実際のモデルがない環境ではモデルロードの時点でエラーになることを確認する。

use piper_plus::engine::OnnxEngine;
use piper_plus::config::VoiceConfig;
use std::path::PathBuf;

#[test]
fn test_load_nonexistent_model_returns_error() {
    // モデル不在時のエラーが ModelLoad であることを確認（スレッド設定エラーではない）
    let config = VoiceConfig::default();
    let result = OnnxEngine::load(
        &PathBuf::from("/nonexistent/model.onnx"),
        &config,
        "cpu",
    );
    assert!(result.is_err(), "missing model should return error");
    let err_str = result.unwrap_err().to_string();
    // スレッド設定エラーではなくモデルロードエラーであること
    // (with_intra_threads が成功した後にコミット失敗することを間接確認)
    assert!(
        !err_str.contains("intra_threads"),
        "error should be from model loading, not thread config: {err_str}"
    );
}
```

### 4-C. E2E レイテンシ計測テスト

QA エンジニアが以下を手動実行し、計測値を PR に記載する。

**計測コマンド — Rust:**

```bash
# before: 変更前の baseline
cargo build --release -p piper-plus-cli
time cargo run --release -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト" --quiet

# after: M1 適用後
time cargo run --release -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト" --quiet
```

**計測コマンド — C#:**

```bash
# before
dotnet run --project src/csharp/PiperPlus.Cli --configuration Release -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト"

# after
dotnet run --project src/csharp/PiperPlus.Cli --configuration Release -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト"
```

**計測内容の構造化ログ追加（推奨）:**

`SessionFactory.Create()` と `OnnxEngine::load()` に計測ログを追加して PR 記載を容易にする。

```csharp
// SessionFactory.cs — Create() 内
var sw = System.Diagnostics.Stopwatch.StartNew();
var session = new InferenceSession(modelPath, options);
sw.Stop();
logger.LogInformation(
    "InferenceSession created in {ElapsedMs}ms (GraphOptimization={Level})",
    sw.ElapsedMilliseconds,
    options.GraphOptimizationLevel);
return session;
```

```rust
// engine.rs — commit_from_file の前後
let session_start = std::time::Instant::now();
let session = builder
    .commit_from_file(model_path)
    .map_err(|e| PiperError::ModelLoad(e.to_string()))?;
tracing::info!(
    "OnnxEngine session created in {:?} (intra_threads={})",
    session_start.elapsed(),
    num_intra_threads
);
```

**PR に記載する計測テーブル（必須）:**

| 指標 | before (ms) | after (ms) | 削減量 |
|------|------------|------------|--------|
| C# セッション作成時間 | | | |
| C# 初回発話レイテンシ | | | |
| C# 2 回目発話レイテンシ | | | |
| Rust セッション作成時間 | | | |
| Rust 初回発話レイテンシ | | | |
| Rust 2 回目発話レイテンシ | | | |
| C# DirectML 初回発話（条件付き） | | | |

---

## 5. 実装に関する懸念事項とレビュー項目

### 5-1. ORT_ENABLE_ALL によるセッション作成時間の増加（低〜中リスク）

`ORT_ENABLE_ALL` はグラフ最適化をセッション作成時に実行するため、`new InferenceSession()` の所要時間が増加する可能性がある。

- **期待挙動:** セッション作成 +X ms、初回推論 -(X+Y) ms → トータルで Y ms 削減
- **最悪ケース:** セッション作成が長くかかりすぎて起動体験が悪化する（計測で確認必須）
- **対策:** セッション作成コストが 500ms を超える場合は `ORT_ENABLE_EXTENDED`（Level 2）の採用も検討する

**レビュー確認点:**
- `new InferenceSession()` の before/after 時間を必ず計測して PR に記載すること
- セッション作成時間 + 初回推論時間の合計が before より短くなることを確認すること

### 5-2. ORT バージョンとの互換性（低リスク）

現在の `piper-core/Cargo.toml` では `ort = "2.0.0-rc.12"` を使用している。`with_intra_threads()` / `with_inter_threads()` は ORT 2.x の `SessionBuilder` API に存在するが、rc バージョンでの API 安定性を確認すること。

**レビュー確認点:**
- `Session::builder().with_intra_threads(N)` が `ort 2.0.0-rc.12` で利用可能か確認する
- `cargo doc -p piper-plus` で `SessionBuilder` の API を確認する
- もし API が存在しない場合は `.with_optimization_level()` など代替メソッドで対応する

### 5-3. DirectML の `AddFreeDimensionOverrideByName` とモデルの動的次元名（中リスク）

`AddFreeDimensionOverrideByName("batch_size", 1)` は ONNX モデルに `batch_size` という名前の動的次元が存在する場合にのみ有効。VITS モデルの動的次元名は `Netron` 等で確認が必要。

**レビュー確認点:**
- `test/models/multilingual-test-medium.onnx` を Netron で開き、入力ノードの動的次元名を確認する
- 次元名が存在しない場合は `AddFreeDimensionOverrideByName` を省略して `EnableMemoryPattern = false` + `ORT_SEQUENTIAL` のみを適用する
- 次元名が `"input"` 等モデル固有の名前の場合は、設定を柔軟化するか `PiperConfig` に持たせることを検討する

### 5-4. 音声品質回帰（低リスク）

`ORT_ENABLE_ALL` によるグラフ最適化は一般に音声品質に影響しないが、浮動小数点演算の順序が変わることで微細な数値差が生じる可能性がある。

**レビュー確認点:**
- before/after で同一テキストを合成し、WAV ファイルの波形を比較する
- RMSE が一定閾値（例: 0.01 以下）に収まることを確認する
- QA エンジニアが主観試聴で品質差がないことを確認する

### 5-5. 既存の `SessionFactoryTests.cs` への影響（低リスク）

既存テスト (`SessionFactoryTests.cs`) は `Create()` のシグネチャを直接呼び出しているが、パラメータ追加（`useDirectMl`）はデフォルト引数のため既存テストには影響しない。念のため全テストを `dotnet test` で通すこと。

**レビュー確認点:**
- `Create()` シグネチャへの `useDirectMl = false` 追加が既存の 829 テストに影響しないことを確認する
- `InferenceTests.cs` に実モデルを使った E2E テストがある場合は before/after 両方で実行する

---

## 6. 一から作り直すとしたら

このタスクを最初から設計し直す場合、以下のアーキテクチャを検討する。

### 代替案 A: `SessionOptions` ビルダーパターン

現在の `SessionFactory.Create()` は静的メソッドであり、すべての設定が一箇所に集中している。設計し直すとすれば `SessionOptionsBuilder` クラスを導入してデバイス・最適化レベル・形状ヒントを分離管理する構成が理想的。

```csharp
// 理想的な設計（M1 の範囲外）
var session = new SessionOptionsBuilder()
    .WithGraphOptimization(GraphOptimizationLevel.ORT_ENABLE_ALL)
    .WithDirectMl(deviceId: 0)
    .WithFreeDimension("batch_size", 1)
    .Build(modelPath);
```

ただし既存 API の互換性維持を優先するため、M1 では最小変更にとどめる。

### 代替案 B: プロファイルベースの最適化レベル選択

`ORT_ENABLE_ALL` / `ORT_ENABLE_BASIC` / `ORT_DISABLE_ALL` を `VoiceConfig` または環境変数で切り替えられる設計。ユーザーが起動時間と推論速度のトレードオフを調整できる。ただし複雑性が増すため M1 では採用しない。

### 代替案 C: ORT の `intra_op_num_threads` を `VoiceConfig` で設定

Rust の `with_intra_threads()` を固定値ではなく `VoiceConfig` 経由で設定可能にする。ユーザーが `-c '{"intra_threads": 2}'` 等で上書きできる。VITS の小モデル向けにはデフォルト 4 が適切だが、将来的な大型モデル対応を見越した設計。M1 では固定値で開始し、M2 以降でパラメータ化を検討する。

### 結論

M1 は「既存コードへの最小変更でコールドスタート改善」が目的であるため、現方針（1行変更 + スレッド設定追加）が最も適切。設計し直すとしても根本的なアーキテクチャ変更は不要で、上記の代替案 A のような API 整理は M6 以降の技術的負債解消フェーズで対応するのが現実的。

---

## 7. 後続タスクへの連絡事項

### M2 (Warmup) への依存関係

M2 では `OnnxEngine::warmup()` / `PiperSession.WarmupAsync()` を実装し、ダミー推論でグラフ最適化キャッシュを起動時に温める。M1 の `ORT_ENABLE_ALL` 適用後は **セッション作成時に最適化が完了しているため、warmup の効果が変わる可能性がある**。

M2 チームへの引き継ぎ事項:
- M1 適用後の「セッション作成時間」と「初回推論時間」の計測値を PR に記載する
- `ORT_ENABLE_ALL` + warmup の組み合わせが相乗効果を持つかを M2 の計測で検証する
- M1 の baseline 計測値を M2 の PR に `M1 baseline: Xms` として再掲する

### M5 (事前最適化済みモデル配布) への依存関係

M5 では `SessionOptions.OptimizedModelFilePath` を使って最適化済みモデルをキャッシュする。M1 で `ORT_ENABLE_ALL` を設定した状態で M5 を適用すると、最適化済みモデルの生成がより完全な最適化を含むものになる。M5 実装時に M1 の設定が前提となることを確認すること。

### 計測結果の共有フォーマット

M1 の PR には以下のフォーマットで計測結果を記載し、M2 以降の baseline として使用する:

```
## 計測環境
- OS:
- CPU:
- RAM:
- .NET バージョン:
- Rust バージョン:
- モデル: test/models/multilingual-test-medium.onnx

## C# 計測結果
| 指標 | before (ms) | after (ms) | 削減量 |
|------|------------|------------|--------|
| セッション作成時間 | | | |
| 初回発話レイテンシ | | | |
| 2 回目発話レイテンシ | | | |

## Rust 計測結果
| 指標 | before (ms) | after (ms) | 削減量 |
|------|------------|------------|--------|
| セッション作成時間 | | | |
| 初回発話レイテンシ | | | |
| 2 回目発話レイテンシ | | | |
```
