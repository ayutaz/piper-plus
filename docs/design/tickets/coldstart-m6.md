# COLD-M6: .NET ReadyToRun + GPU 検出キャッシュ

> **マイルストーン一覧:** [coldstart-milestones.md](./coldstart-milestones.md)
> **ブランチ:** `feat/coldstart-m6-readytorun-gpu-cache`
> **前提:** M1–M5 完了推奨（特に M5: デバイスラベル命名規則を共有する）
> **期間:** 1週間
> **期待削減量:** ~100–200ms
> **対象:** C# / Rust（GPU 検出）
> **リスク:** 低
> **チケット番号:** `COLD-M6`

---

## 1. タスク目的とゴール

### 背景

M1–M5 によって ORT グラフ最適化・Warmup・並列初期化・辞書バイナリ化・最適化済みモデルキャッシュの各改善が完了している。M6 はコールドスタート最適化プロジェクトの**最終マイルストーン**であり、残余の起動コストをさらに削減する。

削減対象は2つある。

**1. .NET JIT コンパイルコスト（C# のみ）**

`dotnet publish` でビルドした C# CLI は、起動時に .NET JIT がアセンブリを逐次コンパイルする。ReadyToRun (R2R) 形式で発行するとビルド時にプラットフォーム固有の機械語を事前生成できるため、起動初期の JIT コストを削減できる。R2R はフォールバック JIT が残るため Native AOT とは異なるが、`DotNetG2P.MeCab` のような native DLL に依存する構成でも安全に適用できる。

**2. GPU プロバイダ検出コスト（Rust のみ）**

`gpu.rs:122–149` の `auto_detect_device()` は `--device auto` が指定された際に毎回 CUDA / CoreML / DirectML の利用可能性を確認する。各プロバイダのロードには ~100ms 程度のコストが発生するが、物理的なドライバ構成が変化しない限り同じ結果を返し続ける。結果をファイルキャッシュすることでほぼゼロコストにできる。

### ゴール

| 指標 | 現状 | 目標 |
|------|------|------|
| C# CLI 起動〜first inference ready | baseline | ~100ms 短縮 |
| `auto_detect_device()` 所要時間（キャッシュヒット時） | ~100ms | ≤ 5ms |
| `dotnet publish` 出力バイナリサイズ | baseline | ≤ 50MB 維持 |

### 完了条件

- [ ] 対策 A: `PiperPlus.Cli.csproj` に `<PublishReadyToRun>true</PublishReadyToRun>` が追加されている
- [ ] 対策 A: `csharp-ci.yml` の `dotnet publish` ステップが追加・動作している（linux-x64 / win-x64 / osx-arm64）
- [ ] 対策 B: `gpu.rs` に `read_device_cache()` / `write_device_cache()` が実装されている
- [ ] 対策 B: ドライバ更新（GPU ドライババージョン変更）時にキャッシュが無効化される
- [ ] `PIPER_DISABLE_GPU_CACHE=1` でキャッシュをバイパスできる
- [ ] 既存テストスイート全パス（C# 829テスト・Rust テスト群）
- [ ] 各プラットフォームで before/after の計測値を PR に記載する

---

## 2. 実装内容の詳細

### 2-A. C# — .NET ReadyToRun 発行

#### 2-A-1. `.csproj` への設定追加

**ファイル:** `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj`

`<PropertyGroup>` に `<PublishReadyToRun>` を追加する。`<SuppressTrimAnalysisWarnings>` はすでに設定済みであり、R2R との組み合わせで問題はない。

```xml
<!-- src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj -->
<PropertyGroup>
  <OutputType>Exe</OutputType>
  <TargetFramework>net9.0</TargetFramework>
  <RootNamespace>PiperPlus.Cli</RootNamespace>
  <PackAsTool>true</PackAsTool>
  <ToolCommandName>piper-plus</ToolCommandName>

  <!-- ReadyToRun: ビルド時にプラットフォーム固有の機械語を事前生成し、
       起動時の JIT コストを削減する。Native AOT とは異なりフォールバック JIT が残るため
       DotNetG2P.MeCab のような native DLL 依存構成でも安全に使用できる。 -->
  <PublishReadyToRun>true</PublishReadyToRun>

  <!-- 既存設定は変更しない -->
  <SuppressTrimAnalysisWarnings>true</SuppressTrimAnalysisWarnings>
  <!-- ... -->
</PropertyGroup>
```

> **注意:** `<PublishReadyToRun>` はビルド時に有効化されるのではなく、**`dotnet publish` 時にのみ有効**である。`dotnet build` や `dotnet run` では効果がないため、CI の `publish` ステップで適用される。

#### 2-A-2. CI への `dotnet publish` ステップ追加

**ファイル:** `.github/workflows/csharp-ci.yml`

現在の CI は `dotnet build` + `dotnet test` のみであり `dotnet publish` ステップがない。ReadyToRun はプラットフォーム固有のバイナリを生成するため、CI マトリクス（`ubuntu-22.04` / `windows-latest` / `macos-14`）それぞれで `publish` を実行する。

```yaml
# .github/workflows/csharp-ci.yml
# 既存の Test ステップの後に追加

      - name: Publish (ReadyToRun)
        shell: bash
        run: |
          # マトリクスの os に対応する RID を決定する
          case "${{ matrix.os }}" in
            ubuntu-22.04)  RID="linux-x64"  ;;
            windows-latest) RID="win-x64"   ;;
            macos-14)       RID="osx-arm64" ;;
          esac

          dotnet publish src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj \
            -c Release \
            -r "$RID" \
            --self-contained false \
            -p:PublishReadyToRun=true \
            -o "publish/$RID"

      - name: Check binary size
        shell: bash
        run: |
          case "${{ matrix.os }}" in
            ubuntu-22.04)  RID="linux-x64"  ; BIN="piper-plus"       ;;
            windows-latest) RID="win-x64"   ; BIN="piper-plus.exe"   ;;
            macos-14)       RID="osx-arm64" ; BIN="piper-plus"       ;;
          esac

          SIZE_BYTES=$(stat -c%s "publish/$RID/$BIN" 2>/dev/null \
                    || stat -f%z "publish/$RID/$BIN")
          SIZE_MB=$(echo "scale=1; $SIZE_BYTES / 1048576" | bc)
          echo "Binary size: ${SIZE_MB} MB"

          # 50 MB 上限チェック（ReadyToRun による肥大化の検知）
          if (( SIZE_BYTES > 52428800 )); then
            echo "ERROR: binary exceeds 50 MB limit (${SIZE_MB} MB)"
            exit 1
          fi
```

> **補足:** `--self-contained false` は .NET ランタイムを同梱しないフレームワーク依存発行。ランタイム同梱が必要な場合は `--self-contained true` に変更するが、バイナリサイズが大幅に増加する（~100MB）。現状の CI 方針に合わせてフレームワーク依存を維持する。

---

### 2-B. Rust — GPU 検出結果のキャッシュ

#### 2-B-1. キャッシュの設計方針

**ファイル:** `src/rust/piper-core/src/gpu.rs`（変更箇所: 118–149行目周辺）

キャッシュファイルは `~/.piper/device_cache.json` に保存する。JSON 形式とし、以下のフィールドを持つ。

```json
{
  "device": "cpu",
  "driver_version": "555.42.06",
  "ort_version": "2.0.0-rc.12",
  "created_at": "2026-04-02T10:00:00Z"
}
```

**無効化条件:**
- `driver_version` が変化した（GPU ドライバ更新）
- `ort_version` が変化した（ORT アップデート）
- `PIPER_DISABLE_GPU_CACHE=1` 環境変数が設定されている

#### 2-B-2. `auto_detect_device()` の変更

```rust
// src/rust/piper-core/src/gpu.rs

use std::path::PathBuf;

/// キャッシュファイルのパスを返す。
/// ~/.piper/device_cache.json
fn device_cache_path() -> Option<PathBuf> {
    dirs::home_dir().map(|h| h.join(".piper").join("device_cache.json"))
}

/// キャッシュが現在の環境で有効かどうかを検証する。
/// driver_version と ort_version が一致している場合のみ有効とする。
fn is_cache_valid(cache: &DeviceCache) -> bool {
    // ORT バージョンの一致を確認
    let current_ort = ort::version();
    if cache.ort_version != current_ort {
        tracing::debug!(
            "GPU cache invalid: ORT version changed ({} -> {})",
            cache.ort_version, current_ort
        );
        return false;
    }

    // GPU ドライババージョンの確認（CUDA 環境のみ）
    #[cfg(feature = "cuda")]
    if let Some(ref cached_driver) = cache.driver_version {
        if let Some(current_driver) = get_cuda_driver_version() {
            if *cached_driver != current_driver {
                tracing::debug!(
                    "GPU cache invalid: CUDA driver changed ({} -> {})",
                    cached_driver, current_driver
                );
                return false;
            }
        }
    }

    true
}

/// キャッシュから DeviceType を読み込む。
/// キャッシュが存在しない・無効・読み込み失敗の場合は None を返す。
fn read_device_cache() -> Option<DeviceType> {
    if std::env::var("PIPER_DISABLE_GPU_CACHE").is_ok() {
        tracing::debug!("GPU cache disabled via PIPER_DISABLE_GPU_CACHE");
        return None;
    }

    let path = device_cache_path()?;
    if !path.exists() {
        return None;
    }

    let json = std::fs::read_to_string(&path).ok()?;
    let cache: DeviceCache = serde_json::from_str(&json).ok()?;

    if !is_cache_valid(&cache) {
        // 古いキャッシュは削除して再検出を促す
        let _ = std::fs::remove_file(&path);
        return None;
    }

    tracing::info!("GPU cache hit: using cached device '{}'", cache.device);
    parse_device_string(&cache.device).ok()
}

/// 検出結果をキャッシュファイルに保存する。
/// 書き込み失敗は警告にとどめ、致命的エラーにしない。
fn write_device_cache(device: &DeviceType) {
    if std::env::var("PIPER_DISABLE_GPU_CACHE").is_ok() {
        return;
    }

    let Some(path) = device_cache_path() else { return };

    // ディレクトリがなければ作成
    if let Some(parent) = path.parent() {
        if let Err(e) = std::fs::create_dir_all(parent) {
            tracing::warn!("Failed to create GPU cache directory: {e}");
            return;
        }
    }

    let cache = DeviceCache {
        device: device.to_string(),
        driver_version: {
            #[cfg(feature = "cuda")]
            { get_cuda_driver_version() }
            #[cfg(not(feature = "cuda"))]
            { None }
        },
        ort_version: ort::version().to_string(),
        created_at: chrono::Utc::now().to_rfc3339(),
    };

    match serde_json::to_string_pretty(&cache) {
        Ok(json) => {
            if let Err(e) = std::fs::write(&path, json) {
                tracing::warn!("Failed to write GPU cache: {e}");
            } else {
                tracing::info!("GPU cache written to {:?}", path);
            }
        }
        Err(e) => tracing::warn!("Failed to serialize GPU cache: {e}"),
    }
}

/// Auto-detect the best available device.
///
/// Priority: CUDA -> CoreML -> DirectML -> CPU.
/// Only checks providers whose corresponding feature is enabled.
/// Result is cached in ~/.piper/device_cache.json to avoid repeated detection.
fn auto_detect_device() -> DeviceType {
    // キャッシュヒット: 検出をスキップ
    if let Some(cached) = read_device_cache() {
        return cached;
    }

    // キャッシュミス: 実際の検出を行う
    let device = detect_device_internal();
    write_device_cache(&device);
    device
}

/// 実際の GPU プロバイダ検出処理（既存の auto_detect_device の内容をそのまま移動）
fn detect_device_internal() -> DeviceType {
    #[cfg(feature = "cuda")]
    {
        if is_cuda_available() {
            tracing::info!("Auto-detected CUDA device");
            return DeviceType::Cuda { device_id: 0 };
        }
    }

    #[cfg(feature = "coreml")]
    {
        if is_coreml_available() {
            tracing::info!("Auto-detected CoreML device");
            return DeviceType::CoreML;
        }
    }

    #[cfg(feature = "directml")]
    {
        if is_directml_available() {
            tracing::info!("Auto-detected DirectML device");
            return DeviceType::DirectML { device_id: 0 };
        }
    }

    tracing::info!("No GPU providers available, using CPU");
    DeviceType::Cpu
}
```

#### 2-B-3. `DeviceCache` 構造体の追加

```rust
// src/rust/piper-core/src/gpu.rs （ファイル先頭付近に追加）

use serde::{Deserialize, Serialize};

/// GPU 検出結果のキャッシュ構造体。
/// ~/.piper/device_cache.json に保存される。
#[derive(Debug, Serialize, Deserialize)]
struct DeviceCache {
    /// 検出されたデバイス文字列（例: "cpu", "cuda:0", "directml:0"）
    device: String,
    /// CUDA ドライババージョン（CUDA 環境のみ、それ以外は None）
    driver_version: Option<String>,
    /// キャッシュ生成時の ORT バージョン
    ort_version: String,
    /// キャッシュ生成日時（RFC 3339 形式）
    created_at: String,
}
```

#### 2-B-4. `Cargo.toml` への依存追加

**ファイル:** `src/rust/piper-core/Cargo.toml`

```toml
[dependencies]
# 既存依存は変更しない

# GPU キャッシュ: JSON シリアライズ（既存の serde_json で対応可能な場合は不要）
serde = { version = "1", features = ["derive"] }  # 既存であれば変更不要

# ホームディレクトリ取得
dirs = "5"

# キャッシュ生成日時（created_at フィールド用、省略可能）
chrono = { version = "0.4", features = ["serde"], optional = true }
```

> **補足:** `chrono` は `created_at` フィールドのためだけに使用する。不要であれば `created_at` を `u64` の Unix タイムスタンプ（`std::time::SystemTime` で取得）に置き換えて `chrono` への依存を排除できる。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当範囲 |
|------|------|---------|
| C# エンジニア | 1名 | `PiperPlus.Cli.csproj` への `PublishReadyToRun` 追加、ReadyToRun 発行時の動作確認、バイナリサイズ計測、`GraphOptimizationTests.cs` への R2R 対応確認テスト追加 |
| Rust エンジニア | 1名 | `gpu.rs` の `DeviceCache` 構造体・`read_device_cache()` / `write_device_cache()` / `detect_device_internal()` 実装、`dirs` / `serde` / `chrono` 依存追加、Rust テスト追加 |
| CI 担当 | 1名 | `csharp-ci.yml` への `dotnet publish` ステップ・バイナリサイズチェック追加、3プラットフォームでのビルド動作確認 |

**合計 3 名**

---

## 4. 提供範囲・テスト項目

### 4-A. C# ユニットテスト (xUnit v3)

**ファイル:** `src/csharp/PiperPlus.Core.Tests/PublishConfigTests.cs`（新規）

```csharp
using System.Reflection;

namespace PiperPlus.Core.Tests;

/// <summary>
/// COLD-M6 対策 A: ReadyToRun 発行の設定が正しく機能することを確認する。
/// ReadyToRun はビルド時の設定であり、ユニットテストからは直接検証できないため、
/// アセンブリのランタイム特性を間接的に確認する。
/// </summary>
public sealed class PublishConfigTests
{
    [Fact]
    public void PiperPlusCli_Assembly_CanBeLoaded()
    {
        // PiperPlus.Cli アセンブリがロード可能であることを確認（R2R 破損の検知）
        var assembly = Assembly.LoadFrom("PiperPlus.Cli.dll");
        Assert.NotNull(assembly);
    }

    [Fact]
    public void CoreAssembly_DoesNotThrowOnLoad()
    {
        // PiperPlus.Core がロード時に例外を投げないことを確認
        var ex = Record.Exception(() =>
            Assembly.GetAssembly(typeof(PiperPlus.Core.Inference.SessionFactory)));
        Assert.Null(ex);
    }
}
```

**ファイル:** `src/csharp/PiperPlus.Core.Tests/StartupLatencyTests.cs`（新規）

```csharp
using System.Diagnostics;
using PiperPlus.Core.Inference;

namespace PiperPlus.Core.Tests;

/// <summary>
/// COLD-M6: 起動レイテンシの回帰を検知するためのスモークテスト。
/// 実際の計測は QA エンジニアが実施するが、SessionFactory 初期化の上限時間を設ける。
/// </summary>
public sealed class StartupLatencyTests
{
    [Fact]
    public void SessionFactory_Initialize_CompletesWithinTimeLimit()
    {
        // SessionFactory.Create() はモデルがないと FileNotFoundException になる。
        // ここでは SessionOptions の構築だけを計測し、R2R 適用前後での基本レイテンシを確認する。
        var sw = Stopwatch.StartNew();

        // SessionOptions の生成だけを計測（モデルロードは含まない）
        var _ = Record.Exception(() => SessionFactory.Create("/nonexistent/model.onnx"));

        sw.Stop();

        // セッションオプション構築（例外含む前処理）は 500ms 以内であること
        Assert.True(sw.ElapsedMilliseconds < 500,
            $"SessionFactory initialization took {sw.ElapsedMilliseconds}ms, expected < 500ms");
    }
}
```

### 4-B. Rust ユニットテスト

**ファイル:** `src/rust/piper-core/src/gpu.rs`（既存 `#[cfg(test)]` ブロックに追加）

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use std::env;
    use tempfile::TempDir;

    // 1. PIPER_DISABLE_GPU_CACHE=1 でキャッシュ読み書きがスキップされる
    #[test]
    fn test_gpu_cache_disabled_by_env() {
        env::set_var("PIPER_DISABLE_GPU_CACHE", "1");
        let result = read_device_cache();
        assert!(result.is_none(), "cache should be skipped when env var is set");
        env::remove_var("PIPER_DISABLE_GPU_CACHE");
    }

    // 2. キャッシュファイルが存在しない場合は None を返す
    #[test]
    fn test_read_device_cache_missing_file() {
        // PIPER_DISABLE_GPU_CACHE が設定されていない状態でファイルが存在しない場合
        // （テスト環境では ~/.piper/device_cache.json が存在しないことを前提）
        env::remove_var("PIPER_DISABLE_GPU_CACHE");
        // ここでは device_cache_path() が一時ディレクトリを返す形にするか、
        // または None が返ることだけ確認する（CI環境ではキャッシュなし）
        // 実装上: ファイルが存在しなければ None を返すのが正常動作
    }

    // 3. ORT バージョンが変わったキャッシュは無効と判定される
    #[test]
    fn test_cache_invalid_on_ort_version_mismatch() {
        let cache = DeviceCache {
            device: "cpu".to_string(),
            driver_version: None,
            ort_version: "0.0.0-old".to_string(),  // 現在の ORT バージョンと異なる値
            created_at: "2020-01-01T00:00:00Z".to_string(),
        };
        assert!(!is_cache_valid(&cache),
            "cache with mismatched ORT version should be invalid");
    }

    // 4. ORT バージョンが一致するキャッシュは有効と判定される
    #[test]
    fn test_cache_valid_on_ort_version_match() {
        let current_ort = ort::version().to_string();
        let cache = DeviceCache {
            device: "cpu".to_string(),
            driver_version: None,
            ort_version: current_ort,
            created_at: chrono::Utc::now().to_rfc3339(),
        };
        assert!(is_cache_valid(&cache),
            "cache with matching ORT version should be valid");
    }

    // 5. DeviceCache の JSON シリアライズ・デシリアライズが正常に機能する
    #[test]
    fn test_device_cache_serde_roundtrip() {
        let original = DeviceCache {
            device: "cuda:0".to_string(),
            driver_version: Some("555.42.06".to_string()),
            ort_version: "2.0.0-rc.12".to_string(),
            created_at: "2026-04-02T10:00:00Z".to_string(),
        };

        let json = serde_json::to_string(&original).expect("serialization should succeed");
        let deserialized: DeviceCache =
            serde_json::from_str(&json).expect("deserialization should succeed");

        assert_eq!(original.device, deserialized.device);
        assert_eq!(original.driver_version, deserialized.driver_version);
        assert_eq!(original.ort_version, deserialized.ort_version);
    }

    // 6. write_device_cache + read_device_cache のラウンドトリップ（一時ディレクトリ使用）
    #[test]
    fn test_cache_write_read_roundtrip() {
        // 実装上は device_cache_path() をテスト用に差し替える仕組みが必要。
        // 環境変数 PIPER_DEVICE_CACHE_PATH でオーバーライドできる設計にすると
        // このテストが書きやすくなる。
        let tmp = TempDir::new().unwrap();
        let cache_path = tmp.path().join("device_cache.json");

        env::set_var("PIPER_DEVICE_CACHE_PATH", cache_path.to_str().unwrap());
        env::remove_var("PIPER_DISABLE_GPU_CACHE");

        write_device_cache(&DeviceType::Cpu);
        let result = read_device_cache();

        assert!(result.is_some(), "should read back the written cache");
        assert_eq!(result.unwrap(), DeviceType::Cpu);

        env::remove_var("PIPER_DEVICE_CACHE_PATH");
    }
}
```

**ファイル:** `src/rust/piper-core/tests/test_gpu_cache.rs`（新規、統合テスト）

```rust
// test_gpu_cache.rs
// GPU キャッシュの統合テスト。
// PIPER_DISABLE_GPU_CACHE=1 でキャッシュ無効化が機能することを確認する。

use std::env;

#[test]
fn test_auto_detect_device_with_cache_disabled() {
    // PIPER_DISABLE_GPU_CACHE=1 の場合、auto_detect_device() が毎回実行されることを確認。
    // （CI 環境では GPU がないため CPU が返ることも確認できる）
    env::set_var("PIPER_DISABLE_GPU_CACHE", "1");

    // 2回呼んでも両方同じ結果を返すこと（キャッシュなしで再実行される）
    let device1 = piper_plus::gpu::auto_detect_device_public();
    let device2 = piper_plus::gpu::auto_detect_device_public();
    assert_eq!(format!("{device1}"), format!("{device2}"),
        "auto_detect_device should return consistent results");

    env::remove_var("PIPER_DISABLE_GPU_CACHE");
}
```

### 4-C. E2E テスト

| テスト | 内容 | 合否基準 |
|--------|------|---------|
| R2R ビルド成功確認 | `dotnet publish -r linux-x64 -p:PublishReadyToRun=true` が成功する | exit code 0 |
| R2R バイナリサイズ確認 | publish 後のバイナリが 50MB 以下 | ファイルサイズ ≤ 52,428,800 bytes |
| R2R 発行バイナリの動作確認 | publish した `piper-plus` バイナリが `--help` を正常表示できる | exit code 0、出力が空でない |
| GPU キャッシュ生成確認 | `--device auto` で初回実行後に `~/.piper/device_cache.json` が生成される | ファイルの存在確認 |
| GPU キャッシュヒット時間確認 | 2回目の `--device auto` 実行が1回目より ~100ms 短縮される | 計測値を PR に記載 |
| `PIPER_DISABLE_GPU_CACHE=1` バイパス確認 | 環境変数設定時にキャッシュファイルが生成・参照されない | `.json` が生成されない |
| キャッシュ無効化確認 | `device_cache.json` の `ort_version` を書き換え後に再実行するとキャッシュが再生成される | 新しい `ort_version` のキャッシュが生成される |

### 4-D. パフォーマンス計測（PR 記載必須）

```csharp
// C# 計測: dotnet publish した実行ファイルで計測する（dotnet run ではない）
var sw = Stopwatch.StartNew();
// dotnet publish バイナリを直接実行して起動〜first inference のウォールクロック時間を計測
```

```bash
# Rust 計測: GPU キャッシュのヒット率と所要時間
PIPER_DISABLE_GPU_CACHE=1 time piper-plus --device auto --text "テスト" --quiet
# vs
time piper-plus --device auto --text "テスト" --quiet  # キャッシュヒット
```

**PR に記載する計測テーブル（必須）:**

| 指標 | before (ms) | after (ms) | 削減量 |
|------|------------|------------|--------|
| C# CLI 起動〜first inference (publish バイナリ) | | | |
| C# CLI 起動〜first inference (dotnet run) | | | |
| Rust `auto_detect_device()` 初回（キャッシュなし） | | | |
| Rust `auto_detect_device()` 2回目（キャッシュヒット） | | | |
| `dotnet publish` バイナリサイズ (linux-x64) | | | |
| `dotnet publish` バイナリサイズ (win-x64) | | | |
| `dotnet publish` バイナリサイズ (osx-arm64) | | | |

---

## 5. 実装に関する懸念事項とレビュー項目

### 5-1. ReadyToRun の効果範囲（低リスク）

ReadyToRun はフォールバック JIT が残るため完全な AOT ではない。初回起動の JIT コストを**削減**するが**ゼロにはしない**。特に `DotNetG2P` 系の G2P 処理（リフレクションベースのメソッド解決）は JIT でコンパイルされる部分が残る可能性がある。

**レビュー確認点:**
- `dotnet publish` バイナリと `dotnet run` バイナリで起動時間を比較し、実際に短縮が起きているか計測すること
- 効果が 50ms 未満であった場合は本番環境での優先度を下げる判断を行う
- `<PublishReadyToRunComposite>true</PublishReadyToRunComposite>` の追加検討（複数アセンブリをまとめて R2R 化し効果を高める）

### 5-2. Native AOT が現時点で困難な理由（参考情報）

`DotNetG2P.MeCab` が native DLL (`libmecab.so` / `mecab.dll`) をバンドルしており、P/Invoke ベースの呼び出しを使用している。Native AOT は P/Invoke の動的解決に制限があり、リフレクションや動的型解決（`ResolveTextModePhonemizer`）が存在する `PiperPlus.Core` は現状 AOT 非対応である。将来的に G2P を Rust へ完全移植した場合は AOT を再検討できる。

**レビュー確認点:**
- `<PublishAot>` を試験的に設定し、発生するトリム警告・AOT 警告をリストアップして将来の AOT 移行コストを見積もること（本 PR での AOT 有効化は不要）

### 5-3. GPU キャッシュのキャッシュパス権限（低〜中リスク）

`~/.piper/` ディレクトリの作成には書き込み権限が必要。コンテナ / サーバー環境では `HOME` が `/root` になるケースや、ホームディレクトリが存在しないケースがある。

**レビュー確認点:**
- `dirs::home_dir()` が `None` を返した場合のフォールバックを定義する（例: `$XDG_CACHE_HOME/piper/` または `/tmp/piper/`）
- キャッシュディレクトリ作成失敗は `warn!` レベルにとどめ、致命的エラーにしない（既存コードでも同様の設計）
- `PIPER_DEVICE_CACHE_PATH` 環境変数でキャッシュパスをオーバーライドできる設計にするとテストが容易になる

### 5-4. GPU キャッシュとドライバ更新の無効化タイミング（中リスク）

`driver_version` の取得方法はプラットフォームごとに異なる。CUDA ドライババージョンは `nvml` クレートまたは `nvidia-smi` の出力から取得できるが、`nvml` は追加依存となる。DirectML / CoreML のドライババージョン取得は標準的な API が存在しない。

**レビュー確認点:**
- CUDA 環境のみ `driver_version` を取得し、DirectML / CoreML 環境では `None` として保存する方針が現実的。ORT バージョン変更のみを無効化条件とする簡略化も許容できる
- `nvml` crate を追加するか、`nvidia-smi` コマンド実行で代替するかを決定する（`feature = "cuda"` がある場合のみ適用）
- ドライバ更新後に古いキャッシュが残った場合の症状（CPU で動作するが CUDA が使えるのに使わない）を明記し、`--clear-gpu-cache` CLI オプションまたは `PIPER_DISABLE_GPU_CACHE=1` での手動無効化手順をドキュメントに記載する

### 5-5. M5 の `device_type_label()` との命名統一（低リスク）

M5 で実装された `device_type_label()` は `"cpu"`, `"cuda"`, `"dml"`, `"coreml"`, `"tensorrt"` を返す。M6 の `DeviceCache.device` フィールドには `DeviceType::to_string()` の出力（`"cpu"`, `"cuda:0"`, `"directml:0"` 等）を使用する。フォーマットが M5 のラベルと異なる可能性があるため確認が必要。

**レビュー確認点:**
- `DeviceCache.device` には `parse_device_string()` で再パースできる文字列（`DeviceType::to_string()` の出力）を使用すること
- M5 の `device_type_label()` との命名差異を文書化する

---

## 6. 一から作り直すとしたら

### ReadyToRun について

ReadyToRun は .NET の段階的な最適化手段であり、現状の設計は正しい。ゼロから設計するとすれば以下の方針を選択する。

**Native AOT への段階的移行**

`DotNetG2P.MeCab` の依存が AOT の障壁になっているため、日本語 G2P を Rust（`jpreprocess`）に統一した上で C# から Rust 実装を P/Invoke または FFI 経由で呼び出す形に変更する。これにより C# 側の依存が軽量化され Native AOT が現実的になる。ただしこれは C# CLI の大規模リアーキテクチャであり M6 の範囲を大きく超える。

**プラットフォーム別最適化ビルドの整備**

現在の CI は `dotnet build` + `dotnet test` のみで `dotnet publish` がない。リリース成果物を CI で生成・検証するパイプラインを整備し、`ReadyToRun` / `ReadyToRunComposite` / 将来の AOT をビルドプロファイルで切り替えられる構成にする。

### GPU キャッシュについて

現在の設計（ホームディレクトリの JSON ファイル）は実用的だが、よりロバストな設計は以下の通り。

**システムレベルキャッシュへの移行**

OS のネイティブキャッシュ機構（Linux: `$XDG_CACHE_HOME`, macOS: `~/Library/Caches`, Windows: `%LOCALAPPDATA%`）を `dirs` クレートの `dirs::cache_dir()` で取得し、`~/.piper/` に固定しない設計にする。これによりマルチユーザー環境やコンテナ環境でも適切なキャッシュパスが選択される。

**キャッシュキーの hash ベース管理**

`ort_version + driver_version` の文字列比較ではなく、環境情報を SHA256 でハッシュ化したキャッシュキーで管理する。M5 の `ModelCacheManager` と同じ方式にすることで、将来的にキャッシュを一元管理できる。

```rust
// 理想的な設計（M6 の範囲外）
fn cache_key() -> String {
    use sha2::{Digest, Sha256};
    let mut hasher = Sha256::new();
    hasher.update(ort::version().as_bytes());
    if let Some(driver) = get_cuda_driver_version() {
        hasher.update(driver.as_bytes());
    }
    format!("{:x}", hasher.finalize())[..16].to_string()
}
```

---

## 7. 後続タスクへの連絡事項

### M6 はコールドスタート最適化プロジェクトの最終マイルストーン

M6 完了後、M1–M6 全体の振り返りを実施すること。振り返りでは以下を確認する。

1. **目標達成の確認:** プロジェクト目標「初回発話 ~2,000ms → ~300ms」が達成されているかを M1 baseline から M6 完了後の実測値で検証する
2. **未達成項目の棚卸し:** 各マイルストーンで「検討事項・将来対応」として先送りにした項目をリスト化し、次の技術的負債解消フェーズのバックログに追加する
3. **計測値の記録:** M1–M6 の各 PR に記載された計測値を `docs/design/coldstart-results.md` に集約する

### 振り返り時に確認する技術的負債

| 項目 | 発生マイルストーン | 対応フェーズ |
|------|-----------------|-------------|
| Native AOT 移行の可能性調査 | M6 | 次フェーズ |
| GPU キャッシュの `dirs::cache_dir()` ベース移行 | M6 | 次フェーズ |
| M5 の `.ort` 形式 (Experimental API) の安定版対応 | M5 | ORT 安定化後 |
| M4 の WASM bincode サイズトレードオフ再評価 | M4 | WASM 配布最適化時 |
| M1 の `SessionOptionsBuilder` パターンへのリファクタリング | M1 | API 整理フェーズ |

### M5 への依存関係の確認

M6 の `DeviceCache.device` フィールドのフォーマットは M5 の `device_type_label()` 命名規則と整合させること。M5 の実装担当に `device_type_label()` の戻り値仕様を確認した上で M6 を実装すること。

### 計測結果の集約

M6 PR のマージ後、コールドスタート最適化プロジェクト全体の計測結果を以下の形式で `docs/design/coldstart-results.md` に記録する。

```
## コールドスタート最適化 計測結果サマリ

| マイルストーン | 施策 | 削減量 (実測) |
|--------------|------|--------------|
| M1 | ORT_ENABLE_ALL + スレッド設定 | Xms |
| M2 | Warmup ダミー推論 | Xms |
| M3 | 非同期並列初期化 | Xms |
| M4 | 辞書バイナリ形式化 | Xms |
| M5 | 事前最適化済みモデルキャッシュ | Xms |
| M6 | ReadyToRun + GPU 検出キャッシュ | Xms |
| **合計** | | **Xms** |

目標: 2,000ms → 300ms (削減量: 1,700ms)
実測: Xms → Xms (削減量: Xms)
```
