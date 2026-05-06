# TICKET-03: C# ZH-EN Code-Switching 実装

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-03 |
| **マイルストーン** | Phase 3 (Day 6-8) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §2.3 / §4.1 C1-C4 / §8.2 (独立実装方針) |
| **ステータス** | 📝 Draft |
| **依存元** | なし (TICKET-01/02 と並列可) |
| **依存先** | TICKET-06 (CI Sync), TICKET-07 (Docs) |
| **追加 LOC** | ~460 (実装 ~260 + テスト ~200) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: `PiperPlus.Core` に ZH-EN code-switching を実装。`DotNetG2P.Chinese 1.8.0` (NuGet 外部依存、改修不可) を経由せず、C# 側で **Python `_pinyin_to_ipa` 相当を独立実装**する。Python 出力と byte-for-byte 一致させる。

**ゴール**:
- `IChineseG2PEngine.ConvertEmbeddedEnglish(text, loanwordData)` が動作する。
- `MultilingualPhonemizer` が `[zh, en, *]` パターンを自動 dispatch する。
- `zh_en_loanword.json` を `<EmbeddedResource>` で同梱 (`Assembly.GetManifestResourceStream` 経由でロード)。
- Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件が Python と同一の IPA 列。
- `PiperPlus.Core.Tests` (xUnit v3) で追加 ~30 テスト全件 PASS。
- 既存 ~1,000 テストにリグレッションなし。
- `dotnet build` の追加時間 **<2 秒**、bin サイズ増 **<50KB**。

---

## 2. 実装する内容の詳細

設計書 §8.2 で確定済みの **案 A (Engine 拡張 + Core 独立実装)** を採用。

### C1. `Core/Phonemize/ChineseEmbeddedEnglish.cs` 新規

**3 サブモジュール**:

```
src/csharp/PiperPlus.Core/Phonemize/
├── Data/
│   ├── zh_en_loanword.json          (EmbeddedResource)
│   ├── LoanwordData.cs               (record)
│   └── LoanwordDataLoader.cs         (Assembly resource → struct + validate)
├── ChineseEmbeddedEnglish.cs         (主実装)
└── PinyinToIpa.cs                    (Python 移植: ~120 LOC)
```

**実装スケッチ**:

```csharp
namespace PiperPlus.Core.Phonemize;

public sealed record LoanwordData(
    int Version,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Acronyms,
    IReadOnlyDictionary<string, IReadOnlyList<string>> Loanwords,
    IReadOnlyDictionary<string, IReadOnlyList<string>> LetterFallback);

public static class LoanwordDataLoader
{
    private static readonly Lazy<LoanwordData> _default = new(LoadDefaultInternal);
    public static LoanwordData Default => _default.Value;

    public static LoanwordData LoadFromPath(string path) { /* ... */ }
    private static LoanwordData LoadDefaultInternal()
    {
        var asm = typeof(LoanwordDataLoader).Assembly;
        using var stream = asm.GetManifestResourceStream(
            "PiperPlus.Core.Phonemize.Data.zh_en_loanword.json")
            ?? throw new InvalidOperationException("zh_en_loanword.json not embedded");
        return ParseAndValidate(stream, "<embedded>");
    }
    // schema validation: list[str] でない field を検出 → ValidationException
}
```

### C2. `Core/Resources/zh_en_loanword.json` を `<EmbeddedResource>` 同梱

`PiperPlus.Core.csproj` に追加:

```xml
<ItemGroup>
  <EmbeddedResource Include="Phonemize/Data/zh_en_loanword.json"
                    LogicalName="PiperPlus.Core.Phonemize.Data.zh_en_loanword.json" />
</ItemGroup>
```

JSON は Python source からコピー、CI で byte 一致を確認 (TICKET-06)。

### C3. `MultilingualPhonemizer.cs` の dispatch 拡張

`IChineseG2PEngine` に `ConvertEmbeddedEnglish` メソッド追加。**現行 signature は `ChineseG2PResult Convert(string text)`** (prosody A1/A2/A3 を含む) なので、新メソッドも同型を返して `PhonemizeWithProsody` 経路と互換に:

```csharp
public interface IChineseG2PEngine
{
    ChineseG2PResult Convert(string text);  // 既存
    ChineseG2PResult ConvertEmbeddedEnglish(string text, LoanwordData data);  // 新規。embedded EN 部分は prosody 0 fill
}
```

`ChineseG2PResult` の `Tokens` に IPA 列、`A1/A2/A3` には embedded EN 部分は **すべて 0** を fill (Python 側と整合、設計書 §8.5)。

`DotNetChineseG2PEngine` 側で実装 (NuGet 経由しない、`PinyinToIpa` 移植版を呼ぶ):

```csharp
public IReadOnlyList<string> ConvertEmbeddedEnglish(string text, LoanwordData data)
{
    var result = new List<string>();
    foreach (var raw in TokenizeEnglishWords(text))
    {
        var stripped = StripTrailingPunctuation(raw);
        if (Lookup(stripped, data) is { } syllables)
        {
            foreach (var syl in syllables)
            {
                var split = PinyinToIpa.SplitPinyin(syl);
                var ipa = PinyinToIpa.Convert(split);
                result.AddRange(ipa);
            }
        }
    }
    return result;
}
```

`MultilingualPhonemizer.Phonemize` 内 dispatch:

```csharp
for (int i = 0; i < segments.Count; i++)
{
    var seg = segments[i];
    if (seg.Lang == "en" && hasZh)
    {
        var prevIsZh = i > 0 && segments[i - 1].Lang == "zh";
        var nextIsZh = i + 1 < segments.Count && segments[i + 1].Lang == "zh";
        if (prevIsZh || nextIsZh)
        {
            var tokens = _zhEngine.ConvertEmbeddedEnglish(seg.Text, _loanwordData);
            result.AddRange(tokens);
            continue;
        }
    }
    result.AddRange(_enEngine.Convert(seg.Text));
}
```

### C4. テスト追加 (xUnit v3)

ファイル分割:

```
src/csharp/PiperPlus.Core.Tests/Phonemize/
├── ChineseEmbeddedEnglishTests.cs        (新規 ~120 LOC)
├── PinyinToIpaTests.cs                    (新規 ~50 LOC、Python fixture と比較)
├── LoanwordDataLoaderTests.cs             (新規 ~30 LOC)
└── MultilingualDispatchTests.cs           (既存 + 拡張 ~30 LOC)
```

#### Unit テスト (xUnit `[Fact]` / `[Theory]`)

| テスト | 内容 |
|------|------|
| `EmbeddedEnglish_Acronym_GPS` | `GPS` → tone marker 含む |
| `EmbeddedEnglish_Loanword_Python_CaseSensitive` | `Python` ≠ `PYTHON` |
| `EmbeddedEnglish_ChatGPT_FiveSyllables` | 5 syllable |
| `EmbeddedEnglish_LetterFallback_ZZ` | `letter_fallback['Z']` × 2 |
| `EmbeddedEnglish_Empty_ReturnsEmpty` | `""` → `[]` |
| `LookupPriority_LoanwordBeatsAcronym_WithOverride` | override で順序確認 |
| `LookupPriority_AcronymBeatsFallback_WithOverride` | 同上 |
| `Punctuation_TrailingComma_Equivalent` | `GPS,` `GPS.` `GPS` 等価 |
| `MultiSegment_TwoEmbeddedEn` | `ChatGPT 和 Python` |
| `Digits_Z2Z9_EqualsZZ` | digit drop |
| `AcronymWithDigits_MP3_DirectHit` | `MP3` 直接 |
| `Loader_DefaultEmbedded_Loads` | `LoanwordData.Default` 非 null |
| `Loader_OnceOnly_SameInstance` | `Lazy<T>` で同一 instance |
| `Loader_InvalidSchema_ThrowsValidationException` | bad schema |
| `Loader_FromPath_FileNotFound_ThrowsFileNotFound` | 欠損 path |
| `MultilingualDispatch_ZhEnZh_Pattern` | `请打开 GPS 系统` |
| `MultilingualDispatch_ZhEn_Pattern_IssueExample` | `请打开 GPS` |
| `MultilingualDispatch_EnZh_Pattern` | `Hello 世界` |
| `MultilingualDispatch_PureZh_NoChange` | regression |
| `MultilingualDispatch_PureEn_UsesEnglishEngine` | regression |
| `IssueExample_PleaseOpenGps` | Issue 例 1 |
| `IssueExample_IUsePython` | Issue 例 2 |
| `IssueExample_LetMeUseChatGpt` | Issue 例 3 |
| `EmbeddedJson_BytesMatchPythonSource` | SHA256 一致 |
| `PinyinToIpa_Initial_BBeats_p` | Python `_INITIAL_TO_IPA['b']` と一致 |
| `PinyinToIpa_Final_AngBeatsAng` | Python `_FINAL_TO_IPA['ang']` と一致 |
| `PinyinToIpa_FullSyllable_Python_pai4` | full syllable round-trip |

合計 **27 テスト**。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | 全体統括、TICKET-01/02 との設計整合 |
| **C# Dev #1** | 1 | C1 (`ChineseEmbeddedEnglish.cs`, `LoanwordDataLoader.cs`)、C2 (csproj 設定)、`PinyinToIpa.cs` 移植 |
| **C# Dev #2** | 1 | C3 (`IChineseG2PEngine` 拡張、`DotNetChineseG2PEngine` 実装、`MultilingualPhonemizer` dispatch) |
| **QA / Test** | 1 | C4 テスト 27 件、Python fixture 比較、`dotnet test` CI 確認 |

**並列化**: C1 と C3 は API 境界が決まれば並列可。C# Dev #1 が `IChineseG2PEngine` 拡張を先に PR、Dev #2 が呼び出し側を実装。

**コミット推奨**:
- `feat(csharp): C1+C2 LoanwordData + EmbeddedResource`
- `feat(csharp): C3 IChineseG2PEngine 拡張と dispatch`
- `feat(csharp): PinyinToIpa 移植 (Python の _pinyin_to_ipa 相当)`
- `test(csharp): C4 ZH-EN テスト追加`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- `PiperPlus.Core` 公開 API:
  - `LoanwordData` (record)
  - `LoanwordDataLoader.Default` / `LoadFromPath(string)`
  - `IChineseG2PEngine.ConvertEmbeddedEnglish(string, LoanwordData)`
- `PiperPlus.Core.Phonemize.PinyinToIpa` (internal、Python 移植)
- `MultilingualPhonemizer` の dispatch 拡張
- `<EmbeddedResource>` 同梱の JSON

### Out of scope

- `DotNetG2P.Chinese` NuGet の改修 (不可、外部)
- `PiperPlus.Cli` の引数追加 (TICKET-07)
- NuGet パッケージ release (TICKET-07)

### テスト項目

xUnit v3 で 27 テスト。Python fixture (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) を `[Theory]` の `MemberData` で読み込み、parameterized で全網羅。

---

## 5. Unit テスト

セクション 2 C4 の表 27 件。`[Theory]` を活用:

```csharp
public static IEnumerable<object[]> MatrixCases()
{
    var json = File.ReadAllText("Phonemize/TestData/zh_en_loanword_matrix.json");
    var matrix = JsonSerializer.Deserialize<TestMatrix>(json);
    foreach (var c in matrix.Cases) yield return new object[] { c.Input, c.Expected };
}

[Theory]
[MemberData(nameof(MatrixCases))]
public void EmbeddedEnglish_FromMatrix(string input, string[] expected)
{
    var actual = _engine.ConvertEmbeddedEnglish(input, LoanwordData.Default);
    Assert.Equal(expected, actual);
}
```

`PinyinToIpaTests` は **Python fixture (`pinyin_to_ipa_table.json`)** を読み込み、initial/final ごとに Python 出力との一致を assert。

---

## 6. E2E テスト

`PiperPlus.Cli` で Issue [#384](https://github.com/ayutaz/piper-plus/issues/384) 例 3 件を音素 dump し、Python と byte 一致確認。

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx \
  --text "请打开 GPS" \
  --language zh-en \
  --output-phonemes phonemes_csharp.json

diff phonemes_python.json phonemes_csharp.json  # 期待: 差分ゼロ
```

---

## 7. 実装に関する懸念事項

### 懸念 1: `DotNetG2P.Chinese` NuGet の独立実装責務分離 (§8.2 X7)
- **影響**: NuGet 経由とそうでない経路が混在。Engine interface を経由する形で隠蔽するが、内部実装で挙動が分岐するため **テストで両方をカバー必要**。
- **緩和**: `DotNetChineseG2PEngine.Convert` (純中国語) と `ConvertEmbeddedEnglish` で内部メソッドを完全分離。後者は `PinyinToIpa` のみ依存し NuGet を呼ばない。
- **責任**: C# Dev #2。

### 懸念 2: PUA codepoint の整合 (`pua-contract.toml`)
- **影響**: tone marker 0xE046-0xE04A を `PinyinToIpa.Convert` の出力に含める必要。間違えると既存学習済みモデルとずれる。
- **緩和**: `PinyinToIpa.cs` の `_TONE_MARKERS` 定数を `pua-contract.toml` から **手動コピー + コメントで参照**。
- **責任**: C# Dev #1。

### 懸念 3: Lazy<T> 初期化の thread safety
- **影響**: `Lazy<LoanwordData>` のデフォルトモードは `LazyThreadSafetyMode.ExecutionAndPublication` で安全だが、明示的に指定しないと将来変更で破壊される可能性。
- **緩和**: `new Lazy<LoanwordData>(LoadDefaultInternal, LazyThreadSafetyMode.ExecutionAndPublication)` を明示。
- **責任**: C# Dev #1。

### 懸念 4: `EmbeddedResource` の LogicalName
- **影響**: `LogicalName` を指定しないと `PiperPlus.Core.Phonemize.Data.zh_en_loanword.json` ではなく `Phonemize.Data.zh_en_loanword.json` などになり `GetManifestResourceStream` で取得失敗。
- **緩和**: csproj で `LogicalName` を明示、テスト `Loader_DefaultEmbedded_Loads` で取得確認。
- **責任**: C# Dev #1。

### 懸念 5: net10.0 LTS への対応
- **影響**: C# 12+ の機能 (collection expressions, primary constructor) を使う場合、`<LangVersion>` 設定が必要。
- **緩和**: `record` (C# 9+) と `IReadOnlyList<T>` だけで実装、新機能は使わない。
- **責任**: C# Dev #1。

### 懸念 6: `PinyinToIpa` の Python 移植精度
- **影響**: Python の `_INITIAL_TO_IPA` / `_FINAL_TO_IPA` 静的辞書を C# に移植する際、文字列リテラル中の Unicode escape を間違えると IPA が乱れる。
- **緩和**: 移植時に **Python から C# 用の dict literal を自動生成するスクリプト**を作る (`tools/gen_pinyin_to_ipa_csharp.py`)。生成物のみコミット、手書きしない。
- **責任**: C# Dev #1。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] `LoanwordData` が record (immutable)、`IReadOnlyDictionary` を field に持つ
- [ ] `Lazy<T>` が `ExecutionAndPublication` モード明示
- [ ] `EmbeddedResource` の `LogicalName` が `PiperPlus.Core.Phonemize.Data.zh_en_loanword.json` になっている
- [ ] `IChineseG2PEngine.ConvertEmbeddedEnglish` のシグネチャが固定
- [ ] dispatch 条件 `[zh,en,*]` / `[en,zh]` / `[zh,en,zh]` が Python と一致
- [ ] tokenize 時 trailing punctuation を strip (`Trim()` ではなく明示的に `[,.!?]` のみ除去)
- [ ] digits を `letter_fallback` で drop (`char.IsDigit`)
- [ ] PUA mapping (0xE020-0xE04A) と整合 (`PinyinToIpa.cs` のコメントで `pua-contract.toml` 参照)
- [ ] `dotnet test --collect:"XPlat Code Coverage"` でカバレッジ ≥90%
- [ ] `dotnet format` 警告ゼロ
- [ ] `dotnet build /p:TreatWarningsAsErrors=true` 警告ゼロ
- [ ] xUnit `[Theory]` で fixture 駆動

### ドキュメントレビュー

- [ ] `src/csharp/README.md` (もしくは `PiperPlus.Core/README.md`) に ZH-EN 例
- [ ] `PiperPlus.Core` の `<PackageReleaseNotes>` (csproj) に ZH-EN 一行
- [ ] `///` XML doc comment を公開 API 全てに付与

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 (major NuGet bump、`PiperPlus.Core 1.0.0`) を対象。本 PR は §8.11 通り `PiperPlus.Core 0.4.0`。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **PUA 出力 byte 一致** | 既存学習済みモデル PUA 0xE020-0xE04A を絶対変えない。 |
| 2 | **Default-on, opt-out 可** | `MultilingualPhonemizerOptions { ZhEnDispatch = true }` で制御。 |
| 3 | **Graceful failure** | default 欠損 → exception (assembly resource は build 時保証)、override 欠損 → `FileNotFoundException`。 |
| 4 | **Single source of truth** | Python JSON が canonical、C# は consumer。 |
| 5 | **NuGet 外部依存に依存しない経路** | `DotNetG2P.Chinese` を経由しない代替経路を Core に常備。9.6a で離脱ロードマップを管理。 |
| 6 | **`init`-only property + reference equality** | `LoanwordData` は `sealed class` + `required init` で immutable。`record` は `IReadOnlyDictionary` の equality 計算が高コストで意味をなさないため不採用。 |
| 7 | **`TheoryData<>` + `ClassData` 駆動テスト** | xUnit v3 の typed `TheoryData` と `ClassData` で fixture を全網羅、Python と byte 比較。 |
| 8 | **C# 慣習を守る** | Go の `embed.FS` や Rust の `phf` を直輸入しない。`<EmbeddedResource>` + `Assembly.GetManifestResourceNames()` glob 検索が C# 標準。 |
| 9 | **AOT-ready from day 1** | `<IsAotCompatible>true</IsAotCompatible>` を csproj に必須化、`JsonSerializerContext` source generator で reflection-free 化。 |
| 10 | **DI を尊重するが強制しない** | `ILogger` (non-generic) を constructor optional、default は `NullLogger.Instance`。 |

### 9.1 データ層

**判断**: AOT publish ユーザー (Unity / iOS / NativeAOT) が既に存在するため、**0.4.0 (本 PR) で `JsonSerializerContext` source generator を導入**。reflection 経由は v1.0.0 では完全廃止。

```csharp
// 内部 DTO (source-gen 対象)
internal sealed class LoanwordDataDto
{
    public int Version { get; set; }
    public Dictionary<string, List<string>> Acronyms { get; set; } = new();
    public Dictionary<string, List<string>> Loanwords { get; set; } = new();
    public Dictionary<string, List<string>> LetterFallback { get; set; } = new();
}

[JsonSerializable(typeof(LoanwordDataDto))]
internal partial class LoanwordJsonContext : JsonSerializerContext { }

// 公開 LoanwordData は DTO から AsReadOnly() で wrap
public sealed class LoanwordData
{
    public required int Version { get; init; }
    public required IReadOnlyDictionary<string, IReadOnlyList<string>> Acronyms { get; init; }
    public required IReadOnlyDictionary<string, IReadOnlyList<string>> Loanwords { get; init; }
    public required IReadOnlyDictionary<string, IReadOnlyList<string>> LetterFallback { get; init; }
}
```

csproj に必須:
```xml
<IsAotCompatible>true</IsAotCompatible>
<EnableTrimAnalyzer>true</EnableTrimAnalyzer>
```

**`<EmbeddedResource>` の堅牢化**: `LogicalName` ハードコードはやめ、glob + `GetManifestResourceNames` 検索:

```xml
<EmbeddedResource Include="Phonemize/Data/*.json" />
<!-- LogicalName は書かない (default の RootNamespace.Phonemize.Data.{name} 命名規則) -->
```

```csharp
private static Stream GetEmbeddedResource(Assembly asm, string fileName)
{
    var name = asm.GetManifestResourceNames()
        .SingleOrDefault(n => n.EndsWith("." + fileName, StringComparison.Ordinal))
        ?? throw new InvalidOperationException(
            $"Embedded resource not found: {fileName}. " +
            $"Available: {string.Join(", ", asm.GetManifestResourceNames())}");
    return asm.GetManifestResourceStream(name)!;
}
```

これで Phase 2 で `ja_en_loanword.json` を追加しても csproj 変更不要。

**初期化方式の比較** (Default 経路のみ):

| 手段 | 採用 | 理由 |
|------|-----|------|
| `static readonly Lazy<LoanwordData>` (本 PR) | ✓ | thread-safe (`ExecutionAndPublication` 明示)、eager すぎず、default は build 時保証で永続失敗 OK |
| `static` constructor | ✗ | `TypeInitializationException` で利用者の例外ハンドリングが煩雑 |
| `[ModuleInitializer]` | ✗ | assembly load 時に走り resource を握りっぱなし、library として GC 不利 |

**重要**: `LoadFromPath(path)` は **`Lazy<T>` を経由しない直接 parse**。同じ load 関数を共有しない。インスタンス化を将来導入する場合は `Lazy<LoanwordData>` を field として持つこと (path ごとに分離)。

### 9.2 API 層

```csharp
// builder pattern + opt-out
var phonemizer = new MultilingualPhonemizerBuilder()
    .WithZhEnDispatch(enabled: true)
    .WithLoanwordData(LoanwordSource.Default)
    // or .WithLoanwordData(LoanwordSource.FromFile("custom.json"))
    .Build();

// LoanwordSource は discriminated union 風 (sealed class hierarchy)
public abstract record LoanwordSource
{
    public sealed record Default : LoanwordSource;
    public sealed record FromFile(string Path) : LoanwordSource;
    public sealed record FromStream(Stream Stream) : LoanwordSource;
}
```

- error: `LoanwordValidationException(string Path, string Section, string Key, string Expected)`、`Message` は Python と一致 (`{Path}: '{Section}.{Key}' must be list[str]`)。
- 現行 `LoanwordDataLoader.Default` は **互換 alias** として残す。

### 9.3 Dispatcher

**Day 1 (本 PR)**: `prevIsZh / nextIsZh` 直書き。

**v1.0.0**: pattern table を `static readonly CodeSwitchPattern[] _patterns = [...]` で declarative 化、JA-EN 拡張を 1 行追加で対応可能に。

### 9.4 Assembly 構成

```
src/csharp/
├── PiperPlus.Core/                       (本体)
│   ├── Phonemize/
│   │   ├── ChineseEmbeddedEnglish.cs
│   │   ├── PinyinToIpa.cs
│   │   └── Data/
│   │       ├── zh_en_loanword.json       (EmbeddedResource)
│   │       ├── LoanwordData.cs
│   │       └── LoanwordDataLoader.cs
│   └── PiperPlus.Core.csproj
├── PiperPlus.Core.Tests/                 (xUnit v3)
└── PiperPlus.Cli/                        (CLI、本 PR では変更なし)
```

**Sub-assembly 化はしない**: C# は同一 namespace 内で十分。ZH-EN 機能のみで `PiperPlus.Core.Phonemize.ZhEn` を切るのは過剰。

### 9.5 Failure mode

| ケース | 動作 | エラー型 |
|-------|------|---------|
| EmbeddedResource 欠損 (build 時) | **build 失敗** (`<EmbeddedResource>` ファイル参照エラー) | — |
| `LoanwordDataLoader.Default` でリソース取得失敗 | `InvalidOperationException` | — |
| `LoadFromPath(path)` で file 欠損 | `FileNotFoundException` | — |
| schema 違反 | `LoanwordValidationException` | Python と同文言 |
| JSON parse error | `JsonException` (System.Text.Json) | inner |
| `ZhEnDispatch=false` | Engine 非経由、loanword は touch しない | — |

### 9.6 i18n 拡張パス

| Phase | 内容 | 必要な変更 |
|-------|------|-----------|
| Phase 1 (本 PR) | ZH-EN | `Data/zh_en_loanword.json` 1 個 |
| Phase 2 | JA-EN / KO-EN | `Data/{ja_en, ko_en}_loanword.json` 追加 + pattern table 拡張 |
| Phase 3 | 任意ペア | `LoanwordRegistry.Register(src, tgt, data)` |

### 9.6a NuGet (`DotNetG2P.Chinese`) 離脱ロードマップ

ZH-EN だけでなく純中国語経路の C# 独立化も計画:

| Phase | 範囲 | 移植量 | リリース |
|-------|------|------|---------|
| **0.4.0** (本 PR) | ZH-EN code-switching のみ | `_pinyin_to_ipa` ~120 LOC | minor bump |
| **0.5.0** | 純中国語 G2P を C# 独立実装 (jieba 代替 + tone sandhi 移植) | +500 LOC, +jieba 辞書 ~3MB | minor bump |
| **1.0.0** | `DotNetG2P.Chinese` 依存削除、NuGet stand-alone | — | **major bump** |

**判断ポイント**: Phase 1 (本 PR) で `PinyinToIpa.cs` を移植してしまえば、Phase 2 の単独実装の **基盤は既に整う**。本 PR では `PinyinToIpa` を `internal sealed` に留めるが、Phase 2 で `public` 化を検討。0.5.0 計画は別 INDEX で管理。

### 9.7 テスト戦略

- **xUnit v3 `TheoryData<>` (typed)** で fixture 駆動。`MemberData` よりも parameter mismatch を compile time で検出可能、`object[]` の serialize リスク回避。
- 大規模 fixture (>100 ケース) は **`ClassData`** + コンストラクタ load + cache。test discovery 時の毎回 file I/O を回避。
- **`AssemblyFixture`** (xUnit v3 新機能) で `LoanwordData.Default` を 1 度だけ load し全 test class で共有。
- **Cross-runtime fixture** (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) を CI sync で `src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/` にコピー (TICKET-06)。
- `Verify.Xunit` (snapshot test) で IPA 列を golden 化、Python 出力と一致確認。
- `dotnet test --collect:"XPlat Code Coverage"` で coverage ≥90%。

```csharp
public class LoanwordMatrixData : TheoryData<string, string[]>
{
    public LoanwordMatrixData() {
        var matrix = JsonSerializer.Deserialize(
            File.ReadAllText("Phonemize/TestData/zh_en_loanword_matrix.json"),
            TestMatrixContext.Default.TestMatrix);
        foreach (var c in matrix!.Cases) Add(c.Input, c.Expected);
    }
}

[Theory, ClassData(typeof(LoanwordMatrixData))]
public void EmbeddedEnglish_FromMatrix(string input, string[] expected) { ... }
```

### 9.8 Observability

**設計原則**: DI は尊重するが強制しない。`PiperPlus.Core` 利用者が DI コンテナを使っていなくても動作する。

```csharp
public sealed class ChineseEmbeddedEnglishConverter
{
    private readonly ILogger _logger;

    public ChineseEmbeddedEnglishConverter(ILoggerFactory? loggerFactory = null)
        : this(loggerFactory?.CreateLogger<ChineseEmbeddedEnglishConverter>()
               ?? NullLogger<ChineseEmbeddedEnglishConverter>.Instance) { }

    public ChineseEmbeddedEnglishConverter(ILogger logger)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }
}
```

- **default は `NullLogger.Instance`** (= no-op)。zero-cost、AOT 対応。
- **`ILogger<T>` ではなく `ILogger`** を field に: generic logger は category 文字列固定で柔軟性低い。
- **構造化ログ**: `[LoggerMessage]` source generator (`Microsoft.Extensions.Logging.Abstractions 8+`) で AOT 互換のログメソッドを生成。文字列 interpolation は AOT 警告。

```csharp
internal static partial class LoanwordLog
{
    [LoggerMessage(EventId = 1001, Level = LogLevel.Debug,
                   Message = "loanword hit: token={Token} syllables={Syllables}")]
    public static partial void LoanwordHit(this ILogger logger, string token, string syllables);

    [LoggerMessage(EventId = 1002, Level = LogLevel.Debug,
                   Message = "acronym hit: token={Token} uppercase={Uppercase}")]
    public static partial void AcronymHit(this ILogger logger, string token, string uppercase);

    [LoggerMessage(EventId = 1003, Level = LogLevel.Debug,
                   Message = "fallback hit: token={Token} char={Char}")]
    public static partial void FallbackHit(this ILogger logger, string token, char @char);
}
```

`PIPER_DEBUG_ZH_EN=1` env var の扱い: env var 直接読みは library として副作用が大きいため避け、**`ILoggingBuilder` extension method** `AddPiperZhEnDebug(this ILoggingBuilder)` を提供 (利用者側で明示的に呼ぶ)。

---

## 10. 後続タスクへの連絡内容

### TICKET-06 (CI Sync) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JSON 配置パス** | `src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json` |
| **比較対象** | Python source と byte 一致 |
| **Validation 確認** | CI で `dotnet test --filter Loader_DefaultEmbedded_Loads` |
| **追加 CI step** | `dotnet build /p:TreatWarningsAsErrors=true` で警告検出 |

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **README** | `src/csharp/README.md` または `PiperPlus.Core/README.md` に ZH-EN 例 |
| **CHANGELOG** | `[Unreleased]` に "Added: ZH-EN code-switching" |
| **NuGet release notes** | `<PackageReleaseNotes>` (csproj) で 1 行 |
| **API doc** | `///` XML doc comment 必須、`docfx` で公開 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §2.3 / §4.1 C1-C4 / §8.2 から派生) |
