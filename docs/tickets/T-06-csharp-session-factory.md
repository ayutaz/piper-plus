# T-06: C# SessionFactory に CoreML + auto-detect + PIPER_EXECUTION_PROVIDER 追加

**Milestone:** feat: Hardware EP 自動選択 (#382) — Milestone #16
**依存タスク:** T-01（ort-session-contract.toml EP 仕様追記）
**後続タスク:** T-10（全体回帰テスト）

---

## 1. タスク目的とゴール

### 目的

`src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` に以下の機能を追加し、C# ランタイムを他の 4 ランタイム（Python / Rust / Go / C++）と同水準の EP 対応に引き上げる。

1. **CoreML EP サポート** — macOS ビルドで Apple Neural Engine を活用する（3〜10x 高速化期待）
2. **auto-detect ロジック** — `OrtEnv.Instance.GetAvailableProviders()` で利用可能な EP を列挙し、CUDA → CoreML → DirectML → CPU の優先度で自動選択する
3. **`PIPER_EXECUTION_PROVIDER` 環境変数対応** — 明示的な EP 指定を `PIPER_GPU_DEVICE_ID` より優先して受け付ける

### Done 基準

- `ResolveDevice(string)` と `GetDeviceLabel(string)` の public static メソッドが追加されている
- `PIPER_EXECUTION_PROVIDER` 環境変数が `useCuda` パラメータより優先される
- CoreML EP が macOS ビルドで動作する（`TryAppendCoreML` メソッド追加）
- auto-detect が CUDA → CoreML → DirectML の優先度で動作する
- OpenVINO は実装しない（NuGet パッケージが存在しないためスコープ外）
- `dotnet test PiperPlus.Core.Tests/` が全件 PASSED

---

## 2. 実装する内容の詳細

### 2.1 変更対象ファイル

- **主要変更:** `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`
- **テスト追加:** `src/csharp/PiperPlus.Core.Tests/SessionFactoryTests.cs`（既存ファイルに追記または新規作成）

### 2.2 現状の SessionFactory.cs の構造

現在（415行目付近）の実装：

```csharp
// 既存: CUDA のみサポート
private static void TryAppendCudaProvider(SessionOptions options, int deviceId, ILogger logger)
{
    try
    {
        options.AppendExecutionProvider_CUDA(deviceId);
        logger.LogInformation("CUDA execution provider enabled (device_id={DeviceId})", deviceId);
    }
    catch (Exception ex)
    {
        logger.LogWarning("CUDA execution provider unavailable, falling back to CPU: {Message}", ex.Message);
    }
}
```

`Create()` 内の deviceLabel 計算（122行目）：

```csharp
var deviceLabel = useCuda ? $"cuda{resolvedDeviceId}" : "cpu";
```

### 2.3 追加するメソッド

#### `ResolveDevice(string device = "auto")`

環境変数 `PIPER_EXECUTION_PROVIDER` を読み取り、未設定時は `device` パラメータを返す。

```csharp
/// <summary>
/// Resolves the effective device string, applying PIPER_EXECUTION_PROVIDER env var.
/// PIPER_EXECUTION_PROVIDER env var takes precedence over the device parameter.
/// </summary>
public static string ResolveDevice(string device = "auto")
{
    var ep = Environment.GetEnvironmentVariable("PIPER_EXECUTION_PROVIDER");
    if (!string.IsNullOrWhiteSpace(ep))
        return ep.Trim().ToLowerInvariant();
    return device.ToLowerInvariant();
}
```

#### `GetDeviceLabel(string device)`

キャッシュファイル名に使用するデバイスラベルを返す（`ort-session-contract.toml` のキャッシュ命名規則に従う）。

```csharp
/// <summary>
/// Returns the cache file device label for the given device string.
/// Examples: "cuda:1" → "cuda1", "coreml" → "coreml", "directml" → "directml0"
/// </summary>
public static string GetDeviceLabel(string device)
{
    var resolved = ResolveDevice(device);
    if (resolved is "cpu" or "")
        return "cpu";

    var parts = resolved.Split(':', 2);
    var key = parts[0];
    var id = parts.Length > 1 && int.TryParse(parts[1], out var n) ? n : 0;

    return key switch
    {
        "cuda"      => $"cuda{id}",
        "coreml"    => "coreml",
        "directml"  => $"directml{id}",
        "openvino"  => "openvino",
        "tensorrt"  => $"tensorrt{id}",
        _           => "cpu",
    };
}
```

#### `TryAppendCoreML(SessionOptions, ILogger)`

CoreML EP の追加を試みる。macOS 版 `Microsoft.ML.OnnxRuntime` に CoreML が含まれており、Windows/Linux では失敗する。

```csharp
private static void TryAppendCoreML(SessionOptions options, ILogger logger)
{
    try
    {
        // CoreML EP は macOS/iOS で自動有効。uint flags: 0 = default
        options.AppendExecutionProviderCoreML(0);
        logger.LogInformation("CoreML execution provider enabled");
    }
    catch (Exception ex)
    {
        logger.LogWarning(
            "CoreML execution provider unavailable, falling back to CPU: {Message}",
            ex.Message);
    }
}
```

#### `AutoDetectAndConfigureEP(SessionOptions, ILogger)`

`OrtEnv.Instance.GetAvailableProviders()` で EP を列挙し、優先度順に試みる。

```csharp
private static string AutoDetectAndConfigureEP(SessionOptions options, ILogger logger)
{
    var available = OrtEnv.Instance.GetAvailableProviders();

    if (Array.IndexOf(available, "CUDAExecutionProvider") >= 0)
    {
        TryAppendCudaProvider(options, 0, logger);
        return "cuda0";
    }
    if (Array.IndexOf(available, "CoreMLExecutionProvider") >= 0)
    {
        TryAppendCoreML(options, logger);
        return "coreml";
    }
    if (Array.IndexOf(available, "DmlExecutionProvider") >= 0)
    {
        TryAppendDirectMLProvider(options, 0, logger);
        return "directml0";
    }
    logger.LogInformation("No hardware EP available, using CPU");
    return "cpu";
}
```

### 2.4 `Create()` メソッドの変更

既存の `Create()` メソッド内の deviceLabel 計算を `GetDeviceLabel()` + `ResolveDevice()` に置き換える。

**変更前（122行目付近）:**

```csharp
var deviceLabel = useCuda ? $"cuda{resolvedDeviceId}" : "cpu";
```

**変更後:**

```csharp
// backward compat: useCuda=true → "cuda:<deviceId>"
var deviceStr = useCuda ? $"cuda:{resolvedDeviceId}" : "cpu";
var resolved = ResolveDevice(deviceStr);
var deviceLabel = GetDeviceLabel(resolved);
```

EP 設定ブロック（114〜117行目付近）を拡張：

```csharp
if (useCuda)
{
    TryAppendCudaProvider(options, resolvedDeviceId, logger);
}
```

↓ 変更後：

```csharp
var resolved = ResolveDevice(useCuda ? $"cuda:{resolvedDeviceId}" : "cpu");

switch (resolved)
{
    case "auto":
        deviceLabel = AutoDetectAndConfigureEP(options, logger);
        break;
    case var s when s.StartsWith("cuda"):
    {
        var parts = s.Split(':', 2);
        var devId = parts.Length > 1 && int.TryParse(parts[1], out var n) ? n : resolvedDeviceId;
        TryAppendCudaProvider(options, devId, logger);
        deviceLabel = $"cuda{devId}";
        break;
    }
    case "coreml":
        TryAppendCoreML(options, logger);
        deviceLabel = "coreml";
        break;
    case var s when s.StartsWith("directml"):
    {
        var parts = s.Split(':', 2);
        var devId = parts.Length > 1 && int.TryParse(parts[1], out var n) ? n : 0;
        TryAppendDirectMLProvider(options, devId, logger);
        deviceLabel = $"directml{devId}";
        break;
    }
    // "cpu" または不明な値はそのまま CPU フォールバック
    default:
        deviceLabel = "cpu";
        break;
}
```

### 2.5 `PIPER_GPU_DEVICE_ID` との相互作用

設計仕様（Section 2.3）に従い、以下の優先度で解決する：

1. `PIPER_EXECUTION_PROVIDER=cuda:1` → device 1 の CUDA EP（`PIPER_GPU_DEVICE_ID` より優先）
2. `PIPER_EXECUTION_PROVIDER=cuda` かつ `PIPER_GPU_DEVICE_ID=1` → device 1 の CUDA EP（互換性維持）
3. `PIPER_EXECUTION_PROVIDER` 未設定 かつ `useCuda=true` → `PIPER_GPU_DEVICE_ID` または 0

既存の `ResolveGpuDeviceId()` は後方互換のため削除しない。`PIPER_EXECUTION_PROVIDER` に `:N` が含まれる場合はそちらを優先する実装とする。

### 2.6 追加するテスト

```csharp
[Fact]
public void ResolveDevice_EnvVarCpu_ReturnsCpu()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", "cpu");
    try
    {
        var result = SessionFactory.ResolveDevice("auto");
        Assert.Equal("cpu", result);
    }
    finally
    {
        Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    }
}

[Fact]
public void ResolveDevice_EnvVarCoreML_ReturnsCoreML()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", "coreml");
    try
    {
        var result = SessionFactory.ResolveDevice("auto");
        Assert.Equal("coreml", result);
    }
    finally
    {
        Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    }
}

[Fact]
public void ResolveDevice_NoEnvVar_ReturnsParam()
{
    Environment.SetEnvironmentVariable("PIPER_EXECUTION_PROVIDER", null);
    var result = SessionFactory.ResolveDevice("cpu");
    Assert.Equal("cpu", result);
}

[Fact]
public void GetDeviceLabel_CoreML_ReturnsCoreML()
{
    var label = SessionFactory.GetDeviceLabel("coreml");
    Assert.Equal("coreml", label);
}

[Fact]
public void GetDeviceLabel_DirectML_ReturnsDirectML0()
{
    var label = SessionFactory.GetDeviceLabel("directml");
    Assert.Equal("directml0", label);
}

[Fact]
public void GetDeviceLabel_Cuda1_ReturnsCuda1()
{
    var label = SessionFactory.GetDeviceLabel("cuda:1");
    Assert.Equal("cuda1", label);
}

[Fact]
public void GetDeviceLabel_Cpu_ReturnsCpu()
{
    var label = SessionFactory.GetDeviceLabel("cpu");
    Assert.Equal("cpu", label);
}
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|---|---|---|
| Implementation Agent | 1 | SessionFactory.cs への ResolveDevice / GetDeviceLabel / TryAppendCoreML / AutoDetectAndConfigureEP 追加、Create() ロジック更新 |
| Test Agent | 1 | SessionFactoryTests.cs へのテストケース追加、dotnet test 実行・確認 |
| Review Agent | 1 | 後方互換性（useCuda フラグ）、PIPER_GPU_DEVICE_ID との相互作用、CoreML の例外ハンドリング、コードスタイル確認 |

---

## 4. 提供範囲とテスト項目

### 提供範囲（スコープ）

| ファイル | 変更内容 |
|---|---|
| `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` | `ResolveDevice()`、`GetDeviceLabel()`、`TryAppendCoreML()`、`AutoDetectAndConfigureEP()`、`TryAppendDirectMLProvider()` の追加。`Create()` ロジック更新 |
| `src/csharp/PiperPlus.Core.Tests/SessionFactoryTests.cs` | ResolveDevice / GetDeviceLabel の単体テスト追加 |

**スコープ外:**
- OpenVINO EP（NuGet パッケージ非存在のため）
- TensorRT EP（auto-detect 対象外。明示指定は将来対応）
- CLI レイヤーへの `--provider` フラグ追加（別タスク）

### Unit テスト

| テスト | 検証内容 |
|---|---|
| `ResolveDevice_EnvVarCpu_ReturnsCpu` | PIPER_EXECUTION_PROVIDER=cpu → "cpu" |
| `ResolveDevice_EnvVarCoreML_ReturnsCoreML` | PIPER_EXECUTION_PROVIDER=coreml → "coreml" |
| `ResolveDevice_NoEnvVar_ReturnsParam` | env var 未設定 → 引数値をそのまま返す |
| `GetDeviceLabel_CoreML_ReturnsCoreML` | "coreml" → "coreml" |
| `GetDeviceLabel_DirectML_ReturnsDirectML0` | "directml" → "directml0" |
| `GetDeviceLabel_Cuda1_ReturnsCuda1` | "cuda:1" → "cuda1" |
| `GetDeviceLabel_Cpu_ReturnsCpu` | "cpu" → "cpu" |
| 既存テスト: `ConfigureSessionOptions_*` | 変更なし・全件 PASS |
| 既存テスト: `TryAppendCudaProvider_*` | 変更なし・全件 PASS |

### E2E テスト

- `PIPER_EXECUTION_PROVIDER=cpu` 設定下で `test/models/multilingual-test-medium.onnx` の合成が完了すること
- 出力音声に NaN が含まれないこと（macOS CI: CoreML EP で実行）
- CPU EP 時の既存テスト結果が変わらないこと（回帰）

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項

1. **`AppendExecutionProviderCoreML()` のシグネチャ:** `Microsoft.ML.OnnxRuntime` の C# API にこのメソッドが存在するか、または `OrtApis.AppendExecutionProvider_CoreML(options.Handle, 0)` のような低レベル API が必要か。バージョンに依存するため、実装前にインストール済みパッケージのバージョンを確認すること。
2. **`OrtEnv.Instance.GetAvailableProviders()` の可用性:** `Microsoft.ML.OnnxRuntime` のバージョンに依存する。古いバージョンでは `OrtEnv` クラスが存在しない可能性がある。`ort-versions.md` の記載バージョン（1.17.0 相当）を確認すること。
3. **`TryAppendDirectMLProvider` の有無:** 既存コードに DirectML のメソッドが未実装の場合、`TryAppendCudaProvider` と同パターンで `TryAppendDirectMLProvider` を追加する必要がある。
4. **`PIPER_GPU_DEVICE_ID` との競合:** `PIPER_EXECUTION_PROVIDER=cuda:1` かつ `PIPER_GPU_DEVICE_ID=2` が同時に設定された場合、`PIPER_EXECUTION_PROVIDER` 側のデバイス番号を優先する。実装で確認すること。
5. **macOS CI 環境:** CoreML EP のテストは macOS 環境（Apple Silicon）で実行する必要がある。GitHub Actions の `macos-14` ランナーが必要。

### レビューチェックリスト

- [ ] `ResolveDevice()` が環境変数を大文字小文字無関係に処理しているか（`ToLowerInvariant()` の適用）
- [ ] `GetDeviceLabel()` が `ort-session-contract.toml` のキャッシュ命名規則と一致しているか（`cuda0`, `coreml`, `directml0`）
- [ ] `useCuda=true` の既存呼び出しが `Create()` 変更後も同一動作を維持しているか（後方互換）
- [ ] `PIPER_GPU_DEVICE_ID` が `PIPER_EXECUTION_PROVIDER` 未設定時のみ有効になっているか
- [ ] `TryAppendCoreML()` が非 macOS 環境で例外をキャッチして警告ログを出しているか
- [ ] `AutoDetectAndConfigureEP()` で TensorRT が auto-detect に含まれていないか
- [ ] コードが `dotnet format` スタイルガイドに準拠しているか
- [ ] `OrtEnv.Instance.GetAvailableProviders()` の例外ハンドリングが適切か

---

## 6. 一から作り直すとしたら（Green Field Design）

### 設計思想

C# の強みである型安全性と switch expression を最大活用し、EP 選択ロジックを `enum ExecutionProvider` + `record DeviceConfig(ExecutionProvider Provider, int DeviceId)` として表現する。文字列パースを一カ所（`DeviceConfig.Parse(string)`）に集約し、テスタビリティを高める。

### アーキテクチャ

```csharp
// 理想形: EP を型として表現
public enum ExecutionProvider { Auto, Cpu, Cuda, CoreML, DirectML, TensorRT }

public record DeviceConfig(ExecutionProvider Provider, int DeviceId = 0)
{
    // "cuda:1" → DeviceConfig(Cuda, 1)
    public static DeviceConfig Parse(string value) { ... }

    // 環境変数優先（解決順: PIPER_EXECUTION_PROVIDER > requested > PIPER_GPU_DEVICE_ID）
    // PIPER_EXECUTION_PROVIDER が設定されていれば最優先。
    // 未設定かつ requested が "auto" のとき、PIPER_GPU_DEVICE_ID が設定されていれば
    // 後方互換として "cuda:<id>" に変換する（useCuda=true 相当）。
    public static DeviceConfig Resolve(string requested)
    {
        var ep = Environment.GetEnvironmentVariable("PIPER_EXECUTION_PROVIDER");
        if (!string.IsNullOrWhiteSpace(ep))
            return Parse(ep);

        // 後方互換: PIPER_GPU_DEVICE_ID が設定されていれば "auto" を "cuda:<id>" に読み替え
        var gpuId = Environment.GetEnvironmentVariable("PIPER_GPU_DEVICE_ID");
        if (!string.IsNullOrWhiteSpace(gpuId)
            && int.TryParse(gpuId, out var deviceId)
            && requested == "auto")
            return new DeviceConfig(ExecutionProvider.Cuda, deviceId);

        return Parse(requested);
    }

    public string CacheLabel => Provider switch
    {
        ExecutionProvider.Cuda    => $"cuda{DeviceId}",
        ExecutionProvider.CoreML  => "coreml",
        ExecutionProvider.DirectML => $"directml{DeviceId}",
        _                         => "cpu",
    };
}
```

`SessionFactory` は `DeviceConfig` を受け取り、`SessionOptions` の構成だけに集中する単純な factory に変える。

### 実装アプローチ

- 文字列ベースの EP 名を enum で表現することで `switch` 網羅性チェックをコンパイラが保証
- `IExecutionProviderAppender` インタフェースで各 EP のセットアップを DI 可能にし、テストで差し替え可能にする
- `OrtEnv.Instance.GetAvailableProviders()` を薄い `IProviderDetector` インタフェースで包み、ユニットテストでモック可能にする

### 現行実装との主な差異

| 観点 | 現行実装 | 理想形 |
|---|---|---|
| EP 表現 | 文字列 `"auto"`, `"cuda"` | `enum ExecutionProvider` |
| 型安全性 | なし（typo でサイレント CPU フォールバック） | コンパイル時検証 |
| テスタビリティ | ORT への直接依存 | `IProviderDetector` で DI 可能 |
| 拡張性 | switch に case 追加 | enum 追加 + case 追加（コンパイラが漏れを警告） |
| 技術的負債 | `useCuda: bool` が文字列 EP と並存 | `DeviceConfig` に統合、`useCuda` を廃止 |

---

## 7. 後続タスクへの引き継ぎ事項

後続タスク（T-10: 全体回帰テスト）の担当者へ：

1. **追加されたメソッド:** `SessionFactory.ResolveDevice(string)` と `SessionFactory.GetDeviceLabel(string)` が public static として公開される。他のランタイムのキャッシュラベル仕様と一致していること。
2. **後方互換:** `Create(modelPath, useCuda: true)` の呼び出しは引き続き動作する。`useCuda=true` は内部で `"cuda:{resolvedDeviceId}"` に変換され、`PIPER_EXECUTION_PROVIDER` が未設定の場合に限り有効になる。
3. **CoreML のキャッシュ注意点:** CoreML EP 使用時は ORT グラフ最適化キャッシュ（`.coreml.opt.onnx`）が通常通り生成されるが、CoreML の ANE コンパイルは ORT セッション初期化時に内部で行われるため、初回セッション作成が数秒かかる場合がある（設計仕様 Section 3 参照）。
4. **DirectML メソッド名:** 実装中に `TryAppendDirectMLProvider` の有無を確認し、既存コードにない場合は新規追加する。後続タスク担当者はその有無を前提に依存するコードを書かないこと。
5. **テスト環境:** CoreML の E2E テストは macOS CI (`macos-14`) でのみ実行可能。手元の macOS 以外の環境では CoreML テストがスキップまたは警告になる設計であること。
