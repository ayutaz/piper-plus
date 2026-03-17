# Piper Plus C# CLI 実装ガイド

Issue #245 対応のための技術調査結果と実装仕様をまとめたドキュメント。

**最終更新日:** 2026-03-17

---

## 1. プロジェクト構成 ✅

```
src/csharp/
├── PiperPlus.sln
├── Directory.Build.props
├── global.json                         # .NET SDK 9.0.100 (rollForward: latestFeature)
├── .editorconfig                       # コーディング規約 (file_scoped namespace, indent等)
├── PiperPlus.Core/
│   ├── PiperPlus.Core.csproj
│   ├── Inference/
│   │   ├── PiperSession.cs              # ✅ ONNX Runtime 推論ラッパー (Synthesize / SynthesizeWithDurations)
│   │   ├── PiperModel.cs                # ✅ モデル能力検出 (sid, prosody, durations)
│   │   ├── WavWriter.cs                 # ✅ WAV書き出し (44バイトヘッダー + PCM)
│   │   ├── SessionFactory.cs            # ✅ ONNX セッション生成 (CUDA EP フォールバック)
│   │   ├── TimingWriter.cs              # ✅ 音素タイミング出力 (JSON/TSV)
│   │   ├── StreamingWriter.cs           # ✅ Raw PCM チャンクストリーミング
│   │   └── PhonemeSilenceProcessor.cs   # ✅ 音素別無音分割
│   ├── Phonemize/
│   │   ├── IPhonemizer.cs               # ✅ 音素化インターフェース (IPhonemizer + ProsodyInfo)
│   │   ├── JapanesePhonemizer.cs        # ✅ IJapaneseG2PEngine + G2PResult + 日本語音素化
│   │   ├── EnglishPhonemizer.cs         # ✅ IEnglishG2PEngine + EnglishG2PContext + 英語音素化
│   │   ├── ArpabetToIPAConverter.cs     # ✅ ARPAbet→IPA 変換 + 機能語判定
│   │   ├── PiperPhonemeConverter.cs     # ✅ PUA変換 + N変異 + 疑問詞判定
│   │   ├── PhonemeEncoder.cs            # ✅ phoneme_id変換 + PostProcessIds呼び出し
│   │   ├── CustomDictionary.cs          # ✅ カスタム辞書 (tab区切り、最長一致)
│   │   └── RawPhonemeParser.cs          # ✅ 生音素文字列→phoneme ID変換
│   ├── Config/
│   │   ├── PiperConfig.cs               # ✅ config.json デシリアライズ (source-gen)
│   │   ├── ModelManager.cs              # ✅ モデル一覧・ダウンロード管理
│   │   ├── VoiceCatalog.cs              # ✅ 組み込み＋上流カタログ統合
│   │   ├── VoiceInfo.cs                 # ✅ ボイス情報レコード (VoiceInfo + VoiceFileInfo)
│   │   └── VoiceJsonModels.cs           # ✅ 上流 voices.json デシリアライズ
│   └── Mapping/
│       └── OpenJTalkToPiperMapping.cs   # ✅ PUAマッピングテーブル (uPiperから移植)
├── PiperPlus.Cli/
│   ├── PiperPlus.Cli.csproj
│   └── Program.cs                       # ✅ System.CommandLine エントリーポイント (全30オプション)
└── PiperPlus.Core.Tests/
    ├── PiperPlus.Core.Tests.csproj
    ├── PiperConfigTests.cs              # ✅
    ├── InferenceTests.cs                # ✅
    ├── WavWriterTests.cs                # ✅
    ├── PhonemeConverterTests.cs         # ✅
    ├── PhonemeEncoderTests.cs           # ✅
    ├── JapanesePhonemizerTests.cs       # ✅
    ├── ArpabetToIPAConverterTests.cs    # ✅
    ├── EnglishPhonemizerTests.cs        # ✅
    ├── EnglishPostProcessIdsTests.cs    # ✅
    ├── ModelManagerTests.cs             # ✅
    ├── VoiceCatalogTests.cs             # ✅
    ├── Phase3Tests.cs                   # ✅
    └── Phase4IntegrationTests.cs        # ✅
```

### NuGet依存関係

**PiperPlus.Core:**
| パッケージ | バージョン | 用途 |
|-----------|----------|------|
| `Microsoft.ML.OnnxRuntime.Managed` | 1.24.3 | ONNX推論 (マネージドAPIのみ) |
| `Microsoft.Extensions.Logging.Abstractions` | 8.0.3 | PhonemeEncoder / RawPhonemeParser のロギング抽象化 |

> **DotNetG2P 統合:** `JapanesePhonemizer` は `IJapaneseG2PEngine`、`EnglishPhonemizer` は `IEnglishG2PEngine` 抽象インターフェース経由で G2P エンジンを受け取る。DotNetG2P への直接依存はない。CLI (`Program.cs`) ではリフレクションで解決を試みる。

**PiperPlus.Cli:**
| パッケージ | バージョン | 用途 |
|-----------|----------|------|
| `System.CommandLine` | 2.0.5 | CLI引数パース |
| `Microsoft.ML.OnnxRuntime` | 1.24.3 | ネイティブONNXランタイム |

**PiperPlus.Core.Tests:**
| パッケージ | バージョン |
|-----------|----------|
| `xunit.v3` | 3.2.2 |
| `xunit.runner.visualstudio` | 3.1.5 |
| `Microsoft.NET.Test.Sdk` | 17.13.0 |
| `Microsoft.ML.OnnxRuntime` | 1.24.3 |

### ターゲットフレームワーク

| プロジェクト | TFM | 理由 |
|---|---|---|
| PiperPlus.Core | `net8.0` | uPiper (.NET Standard 2.1 / Unity) との互換性確保 |
| PiperPlus.Cli | `net9.0` | 現行STS、Self-Contained配布に最適 |
| PiperPlus.Core.Tests | `net9.0` | テストは最新で実行 |

### Directory.Build.props
```xml
<Project>
  <PropertyGroup>
    <!-- TFM は各 csproj で個別指定 -->
    <LangVersion>latest</LangVersion>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
    <EnableTrimAnalyzer>true</EnableTrimAnalyzer>
    <IsTrimmable>true</IsTrimmable>
    <JsonSerializerIsReflectionEnabledByDefault>false</JsonSerializerIsReflectionEnabledByDefault>
  </PropertyGroup>
</Project>
```

> **注意:** `TargetFramework` は Directory.Build.props ではなく各 `.csproj` で指定する。
> Core は `<TargetFramework>net8.0</TargetFramework>`、Cli/Tests は `<TargetFramework>net9.0</TargetFramework>`。
> Tests プロジェクトは `<IsTrimmable>false</IsTrimmable>` でトリム分析を無効化。

### Cli csproj NuGet Tool 設定

```xml
<PackAsTool>true</PackAsTool>
<ToolCommandName>piper-plus</ToolCommandName>
```

---

## 2. CLI インターフェース仕様 ✅

C++版 (`src/cpp/main.cpp`) と同等のCLIを提供する。全30オプション実装済み。

### 2.1 コマンドラインオプション

| オプション | 短形式 | 型 | デフォルト | 説明 |
|-----------|--------|-----|---------|------|
| `--model` | `-m` | FileInfo? | 必須 | .onnxモデルファイル |
| `--config` | `-c` | FileInfo? | 自動検出 | config.jsonパス |
| `--text` | `-t` | string? | - | テキスト直接入力 (JSONL不要) |
| `--language` | - | string | `ja` | `--text` モード用言語: `ja` / `en` |
| `--output_file` | `-f` | string? | - | 出力WAVパス (`-`=stdout) |
| `--output_dir` | `-d` | DirectoryInfo | `.` | 出力ディレクトリ |
| `--output_raw` | - | bool | false | Raw PCM (int16) をstdoutに出力 |
| `--speaker` | `-s` | int | 0 | 話者ID |
| `--noise_scale` | - | float | 0.667 | ノイズスケール |
| `--length_scale` | - | float | 1.0 | 長さスケール |
| `--noise_w` | - | float | 0.8 | Duration Predictorノイズ |
| `--sentence_silence` | - | float | 0.2 | 文末無音(秒) |
| `--json-input` | - | bool | false | stdin をJSONLとして解釈 |
| `--version` | - | bool | false | バージョン表示 |
| `--debug` | - | bool | false | DEBUGログ (stderr) |
| `--quiet` | `-q` | bool | false | ログ無効 |
| `--list-models` | - | string? | - | モデル一覧表示 (言語フィルタ可、`Arity=ZeroOrOne`) |
| `--download-model` | - | string? | - | モデルダウンロード |
| `--model-dir` | - | DirectoryInfo? | OS依存 | モデル保存先 |
| `--use-cuda` | - | bool | false | CUDA実行プロバイダー使用 |
| `--gpu-device-id` | - | int | 0 | CUDA GPUデバイスID |
| `--phoneme_silence` | - | string? | - | 音素別無音設定 (`<phoneme> <seconds>`) |
| `--raw-phonemes` | - | bool | false | 入力を音素として解釈 |
| `--streaming` | - | bool | false | ストリーミングモード |
| `--output-timing` | - | string? | - | 音素タイミング出力パス |
| `--timing-format` | - | string | `json` | タイミング形式 (json/tsv) |
| `--custom-dict` | - | string? | - | カスタム辞書ファイル (カンマ区切り) |
| `--espeak_data` | - | string? | - | espeak-ngデータパス (C++ CLI互換、no-op) |
| `--tashkeel_model` | - | string? | - | libtashkeel ORTモデル (C++ CLI互換、no-op) |
| `--test-mode` | - | bool | false | ONNX実行スキップ (CI用) |

> **注意:** `--text` と `--json-input` は排他。両方指定するとエラーになる。

### 2.2 環境変数 ✅

| 変数 | 説明 |
|------|------|
| `PIPER_DEFAULT_MODEL` | デフォルトモデルパス |
| `PIPER_DEFAULT_CONFIG` | デフォルト設定パス |
| `PIPER_MODEL_DIR` | モデル保存先ディレクトリ |
| `PIPER_GPU_DEVICE_ID` | CUDA GPUデバイスID |

### 2.3 入出力モード ✅

**入力モード (排他):**

| モード | 条件 | 説明 |
|--------|------|------|
| テキスト直接入力 | `--text` 指定 | `--language` で言語指定 (デフォルト `ja`)。PhonemeEncoder で自動音素化。 |
| 生音素入力 | `--raw-phonemes` 指定 | stdin からスペース区切り音素を読む。phoneme_id_map でID変換。 |
| JSONL stdin | `--json-input` または stdin パイプ | 1行1発話。pre-encoded phoneme_ids または text フィールドを含む JSON。 |

**JSONL フォーマット:**
```json
{"phoneme_ids":[1,8,5,39], "speaker_id":0, "output_file":"out.wav", "prosody_features":[[a1,a2,a3],...]}
```

JSONL は `text` フィールドにも対応。`text` が指定されると phoneme_ids の代わりにテキストが音素化される。
`speaker` フィールド (文字列) で `speaker_id_map` から話者IDを解決可能。

> **注意:** JSONL の `prosody_features` はネストした配列形式 `[[a1,a2,a3],...]`。Python 版の dict 形式 `[{"a1":1,"a2":2,"a3":3},...]` とは異なる。

**出力モード:**

| モード | 条件 | 説明 |
|--------|------|------|
| ディレクトリ | デフォルト | `{output_dir}/{index}.wav` |
| 単一ファイル | `--output_file path` | 指定パスに WAV 出力 |
| WAV stdout | `--output_file -` | WAV バイナリを stdout に出力 |
| Raw PCM stdout | `--output_raw` または `--streaming` | ヘッダーなし int16 PCM を stdout に出力 |

---

## 3. ONNX モデル テンソル仕様 ✅

### 3.1 入力テンソル ✅

| テンソル名 | 型 | Shape | 必須 |
|-----------|------|--------|------|
| `input` | int64 | `[1, phoneme_length]` | 必須 |
| `input_lengths` | int64 | `[1]` | 必須 |
| `scales` | float32 | `[3]` | 必須 |
| `sid` | int64 | `[1]` | マルチスピーカーのみ |
| `prosody_features` | int64 | `[1, phoneme_length, 3]` | prosodyモデルのみ |

**scales配列:** `[noise_scale, length_scale, noise_scale_w]` -- デフォルト値: `[0.667, 1.0, 0.8]`

### 3.2 出力テンソル ✅

| テンソル名 | 型 | Shape | 必須 |
|-----------|------|--------|------|
| `output` | float32 | `[1, 1, audio_samples]` | 必須 |
| `durations` | float32 | `[1, phoneme_length]` | オプション |

### 3.3 float32→int16変換 ✅

ピークノーマライズ後、**対称クリッピング `[-32767, 32767]`** でint16に変換する。
`short.MinValue` (-32768) ではなく `-32767` を使用し、正負対称を保つ。

```csharp
// PiperSession.ConvertToInt16() の実装:
float maxVal = 0f;
for (int i = 0; i < audio.Length; i++)
{
    float abs = Math.Abs(audio[i]);
    if (abs > maxVal) maxVal = abs;
}
float scale = 32767.0f / Math.Max(0.01f, maxVal);
result[i] = (short)Math.Clamp(audio[i] * scale, -32767f, 32767f);
```

### 3.4 モデル能力検出 ✅

`PiperModel` コンストラクタで `InferenceSession` のメタデータを検査して能力を判定する。

```csharp
// PiperModel コンストラクタ内:
HasSpeakerId     = _session.InputMetadata.ContainsKey("sid");
HasProsody       = _session.InputMetadata.ContainsKey("prosody_features");
HasDurationOutput = _session.OutputMetadata.ContainsKey("durations");
```

**PiperModel 公開プロパティ:**

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `HasSpeakerId` | bool | `sid` 入力テンソルの有無 (マルチスピーカーモデル) |
| `HasProsody` | bool | `prosody_features` 入力テンソルの有無 |
| `HasDurationOutput` | bool | `durations` 出力テンソルの有無 |
| `SampleRate` | int | config.json から取得したサンプルレート (Hz) |
| `InputNames` | IReadOnlyList<string> | ONNX モデルの入力テンソル名一覧 |

### 3.5 推論 API ✅

**SynthesisInput レコード:**
```csharp
public record SynthesisInput(
    long[] PhonemeIds,
    int SpeakerId = 0,
    long[]? ProsodyFeatures = null,     // flat: [a1_0, a2_0, a3_0, a1_1, ...]
    float NoiseScale = 0.667f,
    float LengthScale = 1.0f,
    float NoiseW = 0.8f);
```

**SynthesisResult レコード:**
```csharp
public record SynthesisResult(short[] Audio, float[]? Durations);
```

**PiperSession メソッド:**

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `Synthesize(input)` | `short[]` | int16 PCM 音声 (sentence silence 付き) |
| `SynthesizeToFloat(input)` | `float[]` | 生 float32 音声 (ノーマライズ前) |
| `SynthesizeWithDurations(input)` | `SynthesisResult` | int16 PCM + per-phoneme duration |
| `ConvertToInt16(audio)` | `short[]` | static: float32 → int16 変換 |

**PiperSession プロパティ:**

| プロパティ | 型 | デフォルト | 説明 |
|-----------|-----|---------|------|
| `SentenceSilenceSeconds` | float | 0.2 | 文末無音 (秒) |

---

## 4. config.json スキーマ ✅

### 必須フィールド

```json
{
  "num_speakers": 20,
  "phoneme_id_map": { "_": [0], "^": [1], "$": [2], "a": [10], "\ue000": [17] },
  "audio": { "sample_rate": 22050 },
  "inference": { "noise_scale": 0.667, "length_scale": 1.0, "noise_w": 0.8 }
}
```

### オプションフィールド

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `phoneme_type` | string | `"openjtalk"` / `"text"` (省略時はespeakがデフォルト) |
| `espeak.voice` | string | 言語コード (`"ja"`, `"en-us"`) |
| `speaker_id_map` | object | `{"speaker_1": 0, ...}` |
| `phoneme_map` | object | 音素→音素マッピング (使用頻度低) |
| `audio.hop_size` | int | フレームシフト (音素タイミング用) |
| `prosody_num_symbols` | int | prosodyモデルのみ |
| `prosody_id_map` | object | `{"0": [0], "1": [1], ...}` |

### phoneme_id_map のキー規約

- **必ず1文字 (1 codepoint)** -- 多文字音素はPUA (U+E000-U+E01C) に変換済み
- `_`=PAD, `^`=BOS, `$`=EOS

### config.json 検索順序 ✅

`PiperConfig.FindConfigPath()` で実装済み:

1. `--config` 明示指定
2. `PIPER_DEFAULT_CONFIG` 環境変数
3. `{model_path}.json`
4. `{model_dir}/config.json`

### デシリアライズ ✅

`PiperConfig.LoadFromFile()` は `System.Text.Json` source generator (`PiperConfigJsonContext`) を使用。
トリム安全・AOT安全。`phoneme_id_map`、`audio`、`inference` の必須フィールドバリデーション付き。

---

## 5. 日本語音素化パイプライン ✅

### 処理フロー

```
テキスト
  → [1] IJapaneseG2PEngine.Convert(text)
    → G2PResult { Phonemes[], A1[], A2[], A3[] }
  → [2] sil/pau → 韻律トークン変換 (^, $, ?, _)            [JapanesePhonemizer]
  → [3] 韻律マーカー挿入 (], #, [) — A1/A2/A3基づく         [JapanesePhonemizer]
  → [4] 疑問詞マーカー判定 (GetQuestionType)                [PiperPhonemeConverter]
  → [5] N変異適用 (N → N_m / N_n / N_ng / N_uvular)        [PiperPhonemeConverter]
  → [6] PUA変換 (多文字音素 → 単一コードポイント)            [PiperPhonemeConverter → OpenJTalkToPiperMapping]
  → [7] phoneme_id_map ルックアップ → phoneme_ids           [PhonemeEncoder]
  → [8] prosody_features 対応付け                           [PhonemeEncoder]
```

### 疑問詞マーカー

| 条件 | 戻り値 | PUA |
|------|--------|-----|
| `?!` / `！？` / `？！` で終わる | `?!` | U+E016 |
| `?.` / `。？` / `？。` で終わる | `?.` | U+E017 |
| `?~` / `～？` / `？～` で終わる | `?~` | U+E018 |
| `?` / `？` で終わる | `?` | - |
| その他 | `$` | - |

### N変異ルール

| 変異 | PUA | 後続音素条件 |
|------|-----|-------------|
| `N_m` | U+E019 | m, my, b, by, p, py |
| `N_n` | U+E01A | n, ny, t, ty, d, dy, ts, ch |
| `N_ng` | U+E01B | k, ky, kw, g, gy, gw |
| `N_uvular` | U+E01C | 語末 / 母音 / その他 |

### 固定PUAマッピング (FIXED_PUA_MAPPING)

| PUA | トークン | PUA | トークン |
|-----|---------|-----|---------|
| U+E000 | a: | U+E00E | ch |
| U+E001 | i: | U+E00F | ts |
| U+E002 | u: | U+E010 | sh |
| U+E003 | e: | U+E011 | zy |
| U+E004 | o: | U+E012 | hy |
| U+E005 | cl | U+E013 | ny |
| U+E006 | ky | U+E014 | my |
| U+E007 | kw | U+E015 | ry |
| U+E008 | gy | U+E016 | ?! |
| U+E009 | gw | U+E017 | ?. |
| U+E00A | ty | U+E018 | ?~ |
| U+E00B | dy | U+E019 | N_m |
| U+E00C | py | U+E01A | N_n |
| U+E00D | by | U+E01B | N_ng |
|  |  | U+E01C | N_uvular |

---

## 6. 英語音素化パイプライン ✅

### 処理フロー

```
テキスト
  → [1] IEnglishG2PEngine.ConvertToArpabet(text)
    → per-word ARPAbet トークン列
  → [2] ソースワード抽出 (正規表現 [a-zA-Z']+)
  → [3] 機能語判定 (~110語リスト) → ストレス除去           [ArpabetToIPAConverter]
  → [4] ARPAbet → IPA 変換 (文脈依存: AA+R→ɑːɹ, ER1→ɜː) [ArpabetToIPAConverter.ConvertWord]
  → [5] ストレスマーカー挿入 (ˈ/ˌ)
  → [6] 単語間スペース挿入 (句読点は前単語に付着)
  → [7] phoneme_id_map ルックアップ                        [PhonemeEncoder]
  → [8] PostProcessIds: BOS(^) + PAD(_) + 音素 + PAD(_) + ... + EOS($)
```

### BOS/EOS/PAD挿入 (英語のみ)

```
元:     [10, 59, 24, 120, 27, 100]
PAD挿入: [10, 0, 59, 0, 24, 0, 120, 0, 27, 0, 100, 0]
BOS/EOS: [1, 0, 10, 0, 59, 0, 24, 0, 120, 0, 27, 0, 100, 0, 2]
```

**注意:** 日本語モデルではinter-phoneme PADは挿入しない。英語(eSpeak)モデルのみ。

### 実装クラス

| クラス | ファイル | 役割 |
|--------|---------|------|
| `EnglishPhonemizer` | `EnglishPhonemizer.cs` | `IPhonemizer` 実装、英語音素化メイン処理 |
| `IEnglishG2PEngine` | `EnglishPhonemizer.cs` | G2P エンジン抽象インターフェース |
| `EnglishG2PContext` | `EnglishPhonemizer.cs` | G2P 結果 + ソースワードを保持するレコード |
| `ArpabetToIPAConverter` | `ArpabetToIPAConverter.cs` | ARPAbet→IPA変換、機能語判定、句読点判定 |

---

## 7. G2P 抽象レイヤーと DotNetG2P 統合 ✅

### 7.1 IJapaneseG2PEngine 抽象インターフェース ✅

`JapanesePhonemizer` は G2P エンジンへの直接依存を持たず、`IJapaneseG2PEngine` インターフェースを通じてエンジンを注入する。これにより DotNetG2P 未公開時もテスト可能。

```csharp
// JapanesePhonemizer.cs 内で定義:
public record G2PResult(string[] Phonemes, int[] A1, int[] A2, int[] A3);

public interface IJapaneseG2PEngine
{
    G2PResult Convert(string text);
}
```

### 7.2 IEnglishG2PEngine 抽象インターフェース ✅

`EnglishPhonemizer` は `IEnglishG2PEngine` を通じて G2P エンジンを注入する。

```csharp
// EnglishPhonemizer.cs 内で定義:
public interface IEnglishG2PEngine
{
    List<List<string>> ConvertToArpabet(string text);
}
```

**テストでのモック使用例:**
```csharp
// テストで IJapaneseG2PEngine / IEnglishG2PEngine をモック実装して検証可能
var mockEngine = new MockG2PEngine(/* 固定値を返す */);
var phonemizer = new JapanesePhonemizer(mockEngine);
var tokens = phonemizer.Phonemize("こんにちは");
```

**CLI での解決 (`Program.cs`):** DotNetG2P がインストールされている場合、リフレクションで `DotNetG2PEngine` (日本語) / `DotNetEnglishG2PEngine` (英語) を検出して `IJapaneseG2PEngine` / `IEnglishG2PEngine` として注入する。未インストール時は `NotSupportedException` をスローし、JSONL stdin モードの使用を案内する。

### 7.3 DotNetG2P API

DotNetG2P パッケージは [ayutaz/dot-net-g2p](https://github.com/ayutaz/dot-net-g2p) で開発中。

#### 日本語

```csharp
using var engine = new G2PEngine(new MeCabTokenizer());
ProsodyFeatures features = engine.ToProsodyFeatures("こんにちは");
// features.Phonemes: ["sil","k","o","N","n","i","ch","i","w","a","sil"]
// features.A1: [0, -4, -4, -3, -3, -2, -2, -1, 0, 0, 0]
// features.A2: [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 0]
// features.A3: [0, 5, 5, 4, 4, 3, 3, 2, 1, 1, 0]
```

#### 英語

```csharp
using var engine = new EnglishG2PEngine();
string phonemes = engine.ToPhonemes("hello world");
// "HH AH0 L OW1 W ER1 L D"
```

#### スレッドセーフティ

| クラス | スレッドセーフ |
|---|---|
| `G2PEngine` | 非安全 (スレッドごとにインスタンス作成) |
| `MeCabTokenizer` | 非安全 |
| `EnglishG2PEngine` | 安全 |

#### MeCab辞書パス (検索順)

1. 環境変数 `DOTNETG2P_NAIST_JDIC_PATH`
2. 環境変数 `NAIST_JDIC_PATH`
3. `~/naist-jdic`
4. `./naist-jdic`
5. `./open_jtalk_dic_utf_8-1.11`

---

## 7a. PhonemeEncoder ✅

テキストから ONNX 推論用の phoneme ID 配列 + prosody 配列を生成する静的クラス。
Python `infer_onnx.py` の `text_to_phoneme_ids_and_prosody()` に相当する。

### 処理フロー

```
text → IPhonemizer.PhonemizeWithProsody()
  → tokens + prosody
  → phoneme_id_map ルックアップ (1トークン → 複数ID展開)
  → IPhonemizer.PostProcessIds() (言語固有の BOS/EOS/PAD 挿入)
  → (List<int> PhonemeIds, List<ProsodyInfo?> ProsodyFeatures)
```

### API

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `Encode(phonemizer, text, phonemeIdMap)` | `(List<int>, List<ProsodyInfo?>)` | phoneme ID + prosody リスト |
| `EncodeDirect(phonemizer, text, phonemeIdMap)` | `(long[], long[]?)` | ONNX テンソル用 long 配列 (prosody は flat `[a1,a2,a3,...]`) |
| `SetLogger(ILogger)` | void | 未知音素の警告用ロガー設定 |

**`EncodeDirect` の prosody 配列レイアウト:**
- `[a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...]` (長さ = phonemeIds.Length * 3)
- 全エントリが null の場合は `null` を返す (prosody なしモデル用)
- null エントリは `[0, 0, 0]` で埋められる

---

## 7b. PiperPhonemeConverter ✅

日本語音素パイプラインの3つの静的ヘルパーメソッドを提供する。
Python `japanese.py` の `_get_question_type`、`_apply_n_phoneme_rules` と `token_mapper.py` の `map_sequence` に相当する。

### API

| メソッド | 説明 |
|---------|------|
| `GetQuestionType(text)` | テキスト末尾の句読点から疑問詞マーカーを判定 → `"?!"` / `"?."` / `"?~"` / `"?"` / `"$"` |
| `ApplyNPhonemeRules(tokens)` | `"N"` トークンを後続音素に基づき `N_m` / `N_n` / `N_ng` / `N_uvular` に置換 |
| `MapSequence(tokens)` | 多文字トークンを PUA 単一コードポイントに変換 (`OpenJTalkToPiperMapping` 経由) |

### スキップトークン (N 変異のルックアヘッドで無視)

`_`, `#`, `[`, `]`, `^`, `$`, `?`, `?!`, `?.`, `?~`

---

## 7c. SessionFactory ✅

ONNX Runtime `InferenceSession` のファクトリ。C++ `piper.cpp:loadModel` に対応する。

### 機能

| 機能 | 説明 |
|------|------|
| CUDA EP フォールバック | `--use-cuda` 指定時に CUDA EP を追加。`Microsoft.ML.OnnxRuntime.Gpu` 未インストール時は警告を出して CPU にフォールバック |
| GPU デバイスID解決 | CLI `--gpu-device-id` > 環境変数 `PIPER_GPU_DEVICE_ID` の優先順で解決 |
| グラフ最適化無効 | C++ piper.cpp に合わせ `ORT_DISABLE_ALL` を設定 |
| テストモード | `testMode` パラメータはセッション生成に影響なし (CLI 層で推論スキップを制御) |

### API

```csharp
public static InferenceSession Create(
    string modelPath,
    bool useCuda = false,
    int gpuDeviceId = 0,
    bool testMode = false,
    ILogger? logger = null);
```

---

## 7d. CustomDictionary ✅

テキスト前処理用のカスタム辞書。Python `custom_dict.py` / C++ `custom_dictionary.cpp` に対応する。

### 機能

| 機能 | 説明 |
|------|------|
| 辞書ファイル読み込み | UTF-8、タブ区切り (`original\treplacement`)。`#` コメント行対応 |
| 複数辞書一括読み込み | `LoadDictionaries(paths)` でエラーを stderr に出力しつつ継続 |
| 最長一致置換 | `ApplyToText(text)` でキーの長い順に適用 |
| CLI連携 | `--custom-dict file1.tsv,file2.tsv` でカンマ区切り指定 |

### API

```csharp
public sealed class CustomDictionary
{
    public int Count { get; }
    public void LoadDictionary(string filePath);
    public void LoadDictionaries(IEnumerable<string> filePaths);
    public string ApplyToText(string text);
}
```

---

## 7e. TimingWriter ✅

ONNX `durations` 出力テンソルから音素タイミングを計算し、JSON/TSV で出力する。C++ `piper.cpp:extractTimingsFromDurations` / `outputTimingsAsJSON` / `outputTimingsAsTSV` に対応する。

### 機能

| 機能 | 説明 |
|------|------|
| タイミング計算 | `durations[i]` (フレーム数) を `hopSize / sampleRate` で秒に変換 |
| 特殊トークンスキップ | PAD(0), BOS(1), EOS(2) はクロック進行のみ、出力エントリなし |
| PUA逆引き | `OpenJTalkToPiperMapping.CharToToken` で人間可読名に変換 |
| JSON出力 | source-gen (`TimingJsonContext`) によるトリム安全なシリアライズ |
| TSV出力 | `start\tend\tduration\tphoneme` ヘッダー付きタブ区切り |

### API

```csharp
public static class TimingWriter
{
    public record PhonemeTimingEntry(
        string Phoneme, float StartSeconds, float EndSeconds, float DurationSeconds);

    public static List<PhonemeTimingEntry> CalculateTiming(
        long[] phonemeIds, float[] durations,
        Dictionary<string, int[]> phonemeIdMap,
        int sampleRate, int hopSize = 256);

    // ファイルパス出力
    public static void WriteJson(string filePath, List<PhonemeTimingEntry> entries);
    public static void WriteTsv(string filePath, List<PhonemeTimingEntry> entries);

    // ストリーム出力
    public static void WriteJson(Stream stream, List<PhonemeTimingEntry> entries);
    public static void WriteTsv(Stream stream, List<PhonemeTimingEntry> entries);
}
```

---

## 7f. StreamingWriter ✅

Raw PCM int16 データをストリームにチャンク出力する。C++ `main.cpp:rawOutputProc` に対応する。

### 機能

| 機能 | 説明 |
|------|------|
| チャンク出力 | `WriteChunked()` で 1024 サンプル (2048 バイト) ごとに flush |
| 即時出力 | `WriteImmediate()` で全サンプルを一度に書き出して flush |
| 低レイテンシ | 毎回 `Flush()` を呼び、下流プロセスへ即座に配信 |

### API

```csharp
public static class StreamingWriter
{
    public static void WriteChunked(
        Stream output, ReadOnlySpan<short> samples,
        int chunkSamples = 1024);
    public static void WriteImmediate(
        Stream output, ReadOnlySpan<short> samples);
}
```

---

## 7g. RawPhonemeParser ✅

`--raw-phonemes` モード用のパーサー。スペース区切りの音素文字列を phoneme ID 配列に変換する。C++ `phoneme_parser.cpp:parsePhonemeString` + `phoneme_ids.cpp:phonemes_to_ids` に対応する。

### API

```csharp
public static class RawPhonemeParser
{
    public static long[] Parse(string phonemeString, Dictionary<string, int[]> phonemeIdMap);
    public static void SetLogger(ILogger logger);
}
```

### 解決順序

1. `phoneme_id_map` から直接ルックアップ (単一文字トークン)
2. `OpenJTalkToPiperMapping.TokenToChar` で PUA 変換後にルックアップ (多文字トークン)
3. 未知トークンは警告ログ出力してスキップ

---

## 7h. PhonemeSilenceProcessor ✅

`--phoneme_silence` オプション用のプロセッサ。phoneme ID 列を指定音素で分割し、フレーズ間に無音サンプルを挿入する。C++ `piper.cpp` の `phonemeSilenceSeconds` 処理に対応する。

### API

```csharp
public static class PhonemeSilenceProcessor
{
    public readonly record struct Phrase(
        List<long> PhonemeIds,
        List<long>? ProsodyFlat,
        int SilenceSamples);

    public static Dictionary<string, float> Parse(string specification);
    public static List<Phrase> SplitAtPhonemeSilence(
        long[] phonemeIds, long[]? prosodyFlat,
        Dictionary<string, float> phonemeSilence,
        Dictionary<string, int[]> phonemeIdMap,
        int sampleRate);
}
```

---

## 8. uPiper 再利用コード ✅

| ファイル | Unity非依存率 | 移植方法 |
|---------|-------------|---------|
| `OpenJTalkToPiperMapping.cs` | **100%** | そのままコピー |
| `PhonemeEncoder.cs` | **95%** | `PiperLogger` → `ILogger` に置換 |
| `PiperVoiceConfig.cs` | **80%** | Unity属性を除去、JSON属性追加 |
| `DotNetG2PPhonemizer.cs` | **60%** | Unity条件分岐を除去、パス設定を引数化 |
| `InferenceAudioGenerator.cs` | **30%** | Unity.InferenceEngine → OnnxRuntime 全面書き換え |
| `ArpabetToIPAConverter.cs` | **100%** | そのままコピー |

### 推論エンジン置換対応表

| Unity.InferenceEngine | Microsoft.ML.OnnxRuntime |
|---|---|
| `ModelLoader.Load(asset)` | `new InferenceSession(path)` |
| `new Tensor<int>(shape, data)` | `OrtValue.CreateTensorValueFromMemory(data, shape)` |
| `worker.Schedule()` | `session.Run(inputs)` |
| `worker.PeekOutput()` | `results[0].GetTensorDataAsSpan<float>()` |

---

## 9. モデル管理 ✅

### 実装クラス

| クラス | ファイル | 役割 |
|--------|---------|------|
| `ModelManager` | `Config/ModelManager.cs` | `--list-models` / `--download-model` のメインロジック |
| `VoiceCatalog` | `Config/VoiceCatalog.cs` | 組み込みカタログ + 上流 voices.json の統合読み込み |
| `VoiceInfo` | `Config/VoiceInfo.cs` | ボイス情報レコード (key, language, quality, files等) |
| `VoiceFileInfo` | `Config/VoiceInfo.cs` | ダウンロード対象ファイルレコード (path, size, md5) |
| `VoiceJsonModels` | `Config/VoiceJsonModels.cs` | 上流 voices.json デシリアライズモデル |

### VoiceInfo レコード

```csharp
public record VoiceFileInfo(string RelativePath, long SizeBytes, string Md5Digest);

public record VoiceInfo(
    string Key, string Name,
    string LanguageCode, string LanguageFamily,
    string LanguageNameNative, string LanguageNameEnglish,
    string Quality, int NumSpeakers,
    string Source, string RepoId,
    IReadOnlyList<VoiceFileInfo> Files,
    IReadOnlyList<string> Aliases,
    string Description = "");
```

### ModelManager API

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `GetDefaultModelDir()` | `string` | OS依存のデフォルトモデルディレクトリ |
| `FindVoice(nameOrAlias)` | `VoiceInfo?` | カタログからキーまたはエイリアスで検索 |
| `ListModels(languageFilter?)` | `void` | 利用可能モデル一覧を stderr に出力 |
| `DownloadModelAsync(modelName, modelDir, ct)` | `Task<bool>` | モデルの全ファイルをダウンロード |

### カタログソース

1. **組み込みpiper-plusカタログ** (C#コード内にオブジェクト初期化子で定義、JSON解析不要)
2. **上流piper voices.json** (オプション、ファイルから読み込み)

### VoiceCatalog API

| メソッド | 戻り値 | 説明 |
|---------|--------|------|
| `LoadBuiltInCatalog()` | `IReadOnlyList<VoiceInfo>` | 組み込みカタログを返す |
| `LoadFromFile(path)` | `IReadOnlyList<VoiceInfo>` | 外部 voices.json を読み込み |
| `LoadMergedCatalog(externalPath?)` | `IReadOnlyList<VoiceInfo>` | 組み込み + 外部を統合 (組み込み優先) |

### ダウンロードURL

| モデルソース | URLパターン |
|---|---|
| piper-plus | `https://huggingface.co/{repoId}/resolve/main/{filename}` |
| 上流piper | `https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/{file_path}` |

### デフォルトモデルディレクトリ

| OS | パス |
|---|---|
| Windows | `%APPDATA%\piper\models` |
| macOS | `~/Library/Application Support/piper/models` |
| Linux | `$XDG_DATA_HOME/piper/models` or `~/.local/share/piper/models` |

### セキュリティ検証

- Voice Key: `..`, `/`, `\` を禁止
- Repo ID: `owner/repo` 形式のみ許可 (英数字、ハイフン、アンダースコア、ドット)
- URL: HTTPS + HuggingFaceドメインのみ
- ダウンロード済みファイルはサイズ照合でスキップ

---

## 10. WAV書き出し ✅

44バイト PCM WAVヘッダー + int16サンプルデータ。NAudio不要。

### API

```csharp
public static class WavWriter
{
    public static void Write(Stream stream, ReadOnlySpan<short> samples, int sampleRate);
    public static void Write(string filePath, ReadOnlySpan<short> samples, int sampleRate);
}
```

### WAV ヘッダー構造

```
オフセット  サイズ  フィールド
0          4      "RIFF"
4          4      36 + データバイト数
8          4      "WAVE"
12         4      "fmt "
16         4      16
20         2      1 (PCM)
22         2      1 (モノラル)
24         4      22050 (サンプルレート)
28         4      44100 (バイトレート)
32         2      2 (ブロックアライン)
34         2      16 (ビット深度)
36         4      "data"
40         4      NumSamples * 2
44+        -      int16 PCMデータ
```

---

## 11. CI/CD ✅

### ワークフロー構成

| ファイル | 用途 | トリガー |
|---------|------|---------|
| `csharp-ci.yml` | 3 OS ビルド+テスト (ubuntu-22.04, windows-latest, macos-14) | PR/push to dev |
| `csharp-build-all-platforms.yml` | 6 RID ビルド (再利用可能ワークフロー) | workflow_call / workflow_dispatch |
| `dev-create-release.yml` | リリース作成 (C# CLI ジョブ統合済み) | タグプッシュ |

### ビルドマトリクス

| RID | ランナー | クロスコンパイル |
|-----|---------|----------------|
| `win-x64` | windows-2022 | No |
| `win-arm64` | windows-2022 | Yes |
| `linux-x64` | ubuntu-22.04 | No |
| `linux-arm64` | ubuntu-22.04 | Yes |
| `osx-x64` | macos-14 | Yes |
| `osx-arm64` | macos-14 | No |

### publish設定

```bash
# ネイティブビルド (同一アーキテクチャ)
dotnet publish -c Release -r {RID} \
  --self-contained true \
  -p:PublishSingleFile=true \
  -p:PublishTrimmed=true \
  -p:PublishReadyToRun=true

# クロスコンパイル (win-arm64, linux-arm64, osx-x64)
# PublishReadyToRun はクロスアーキテクチャで非対応のため無効化
dotnet publish -c Release -r {RID} \
  --self-contained true \
  -p:PublishSingleFile=true \
  -p:PublishTrimmed=true \
  -p:PublishReadyToRun=false
```

### 配布方式

1. **GitHub Releases:** Self-Contained バイナリ (全ユーザー向け)
2. **NuGet dotnet tool:** `dotnet tool install -g PiperPlus.Cli` (.NETユーザー向け)

### アセット命名規則

```
piper-plus-cli-win-x64.zip
piper-plus-cli-linux-x64.tar.gz
piper-plus-cli-osx-arm64.tar.gz
```

---

## 12. 既知の注意点 ✅

### パフォーマンス
- ONNX推論はC++と同一ネイティブカーネル使用。P/Invokeオーバーヘッドは < 1%
- 起動時間: Self-Contained JIT 150-500ms / Native AOT 10-50ms
- ONNX Runtime C# APIで初回ロードが遅い場合がある (セッションオプション要チューニング)

### トリミング互換性
- `System.Text.Json` source generator使用推奨 (トリム安全)
- ONNX Runtimeのリフレクション部分でトリム警告が出る可能性あり

### ライセンス
- 全依存パッケージがMIT or Apache-2.0 (GPLフリー)
- C++版のespeak-ng (GPL v3) 依存から解放

### 英語G2P互換性
- DotNetG2P.EnglishはCMU辞書+Flite LTS、Piper Plusのenglish.pyはg2p-en
- OOV処理の差異あり。学習済みモデルとの互換性検証が必要
