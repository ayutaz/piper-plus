# C# — ZH-EN Loanword 実装

> Index: [`README.md`](README.md)

## 1. 実装ファイル

| 用途 | パス |
|------|------|
| Phonemizer (Core 薄ラッパ) | `src/csharp/PiperPlus.Core/ChinesePhonemizer.cs` (113 行) |
| Engine interface | `IChineseG2PEngine` |
| Engine 実装 (Cli 側) | `DotNetChineseG2PEngine` (NuGet `DotNetG2P.Chinese 1.8.0` をラップ) |
| Multilingual | `src/csharp/PiperPlus.Core/MultilingualPhonemizer.cs` (`UnicodeLanguageDetector.SegmentText()` あり) |
| 辞書データ | `src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json` |
| テスト | `ChinesePhonemizerTests.cs` (401 行、StubEngine 利用) + `ChinesePhonemizerPuaTests.cs` |

## 2. 現状調査

| 項目 | 状態 |
|------|------|
| pinyin → IPA | NuGet 内部、`ToPuaPhonemes()` / `ToIpaWithProsody()` |
| データロード | csproj に `<EmbeddedResource>` 設定なし (新規追加が必要) |
| ZH-EN dispatch | **❌ 未実装** (line 220 付近に追加余地あり) |
| Engine 拡張 | **NuGet 改修不可なので Core/Cli 側で独立実装が必要** |

**追加 LOC 見込み**: ~400 行 (Engine 経由でなく独立した embedded English 経路を Core 側に実装)

**特殊な制約**: `DotNetG2P.Chinese` (NuGet) は外部ライブラリでビルド不可。**ZH-EN 用の pinyin → IPA を C# 側に独立実装する必要あり** (一部のロジックは Python から移植)。

## 3. 独立実装方針

**問題**: `DotNetG2P.Chinese 1.8.0` (NuGet) は外部ライブラリで改修不可。Python 側の `_pinyin_to_ipa()` 相当を C# 側に独立実装する必要がある。

**Python 移植量見積**:

| Python 関数/データ | LOC | C# 移植要否 |
|------------------|-----|------------|
| `_pinyin_to_ipa()` | ~40 | ◯ 必須 |
| `_split_pinyin()` | ~20 | ◯ 必須 |
| `_normalize_pinyin()` | ~20 | ◯ 必須 |
| `_INITIAL_TO_IPA` (dict) | ~25 | ◯ 必須 (静的辞書として) |
| `_FINAL_TO_IPA` (dict) | ~55 | ◯ 必須 (静的辞書として) |
| `_apply_tone_sandhi()` | ~75 | ✗ **不要** (loanword は単独 syllable で sandhi 不要) |
| `phonemize_embedded_english()` | ~60 | ◯ 必須 |
| **合計** | **~295 行** | **~120 行** (sandhi 除外) |

**3 案比較**:

| 案 | 実装場所 | メリット | デメリット |
|---|---------|--------|-----------|
| **A** | `IChineseG2PEngine` 拡張 + `DotNetChineseG2PEngine` で実装 | Engine 一貫性 | NuGet 経由しない経路を Engine 内に持つ違和感 |
| **B** | `Core/Phonemize/ChineseEmbeddedEnglishConverter` 独立 class | シンプル、Engine 不要 | Engine 経路と独立しすぎる |
| **C** | `MultilingualPhonemizer` 内に直接実装 | 局所的 | 汎用性低、テスト困難 |

**推奨**: **案 A (`IChineseG2PEngine` 拡張)** — Engine interface に `ConvertEmbeddedEnglish(text, loanwordData)` を追加、`DotNetChineseG2PEngine` 内に Python 移植版実装。ロジックは NuGet 経由しないが、interface としては統一。

**csproj 設定 (EmbeddedResource)**:

```xml
<!-- PiperPlus.Core.csproj -->
<ItemGroup>
  <EmbeddedResource Include="Phonemize/Data/zh_en_loanword.json" />
</ItemGroup>
```

```csharp
// PiperPlus.Core/Phonemize/Data/LoanwordDataLoader.cs
internal static class LoanwordDataLoader {
    public static LoanwordData LoadDefault() {
        var asm = typeof(LoanwordDataLoader).Assembly;
        using var stream = asm.GetManifestResourceStream(
            "PiperPlus.Core.Phonemize.Data.zh_en_loanword.json");
        // schema validation 込みでパース
        return ParseAndValidate(stream);
    }
}
```

**実装規模**: 合計 **~340 LOC** (実装 ~140 + テスト ~200)、想定 1.5 週間。

## 4. メモリ管理

`static Lazy<LoanwordData>` で thread-safe 自動共有、IDisposable 不要 (managed dict のみ)。

```csharp
// C#: 推奨パターン
public class ChinesePhonemizer {
    private static readonly Lazy<LoanwordData> s_default =
        new(() => LoanwordDataLoader.LoadDefault(), LazyThreadSafetyMode.ExecutionAndPublication);

    public ChinesePhonemizer(string? customPath = null) {
        _data = customPath == null ? s_default.Value : LoadAndMerge(customPath);
    }
}
// → IDisposable 不要 (LoanwordData は managed のみ、GC で解放)
```

## 5. エラーハンドリング

`FormatException` 例外:

```csharp
throw new FormatException(
    $"zh-en loanword: '{section}.{key}' must be list[str], got {valueType}");
```

メッセージテンプレート (全ランタイム共通):

```text
{path}: '{section}.{key}' must be list[str], got {actual_type}
```

## 6. JSON parser 安全性

C# `System.Text.Json` のデフォルト nest 制限は 64。`JsonSerializerOptions.MaxDepth` を明示設定して安全性向上。

## 7. ベンチマーク

| フレーム | ファイル |
|--------|--------|
| `BenchmarkDotNet` | `src/csharp/PiperPlus.Benchmarks/ChineseEmbeddedEnglishBench.cs` |

## 8. カバレッジ

`coverlet` (`XPlat Code Coverage`) で計測、既存 CI 統合済 (cobertura.xml artifact)。
