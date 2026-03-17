# Piper Plus C# CLI 実装ガイド

Issue #245 対応のための技術調査結果と実装仕様をまとめたドキュメント。

---

## 1. プロジェクト構成 ✅

```
src/csharp/
├── PiperPlus.sln
├── Directory.Build.props
├── PiperPlus.Core/
│   ├── PiperPlus.Core.csproj
│   ├── Inference/
│   │   ├── PiperSession.cs          # ✅ ONNX Runtime 推論ラッパー
│   │   ├── PiperModel.cs            # ✅ モデル能力検出 (sid, prosody等)
│   │   └── WavWriter.cs             # ✅ WAV書き出し (44バイトヘッダー + PCM)
│   ├── Phonemize/
│   │   ├── IPhonemizer.cs           # ✅ 音素化インターフェース + ProsodyInfo + IJapaneseG2PEngine
│   │   ├── JapanesePhonemizer.cs    # ✅ IJapaneseG2PEngine 経由の日本語音素化
│   │   ├── EnglishPhonemizer.cs     # 未実装 (Phase 3)
│   │   ├── PiperPhonemeConverter.cs  # ✅ PUA変換 + N変異 + 疑問詞判定
│   │   └── PhonemeEncoder.cs        # ✅ phoneme_id変換 + PostProcessIds呼び出し
│   ├── Config/
│   │   ├── PiperConfig.cs           # ✅ config.json デシリアライズ (source-gen)
│   │   └── ModelManager.cs          # 未実装 (Phase 3: --list-models / --download-model)
│   └── Mapping/
│       └── OpenJTalkToPiperMapping.cs  # ✅ PUAマッピングテーブル (uPiperから移植)
├── PiperPlus.Cli/
│   ├── PiperPlus.Cli.csproj
│   └── Program.cs                   # ✅ System.CommandLine エントリーポイント
└── PiperPlus.Core.Tests/
    ├── PiperPlus.Core.Tests.csproj
    ├── PiperConfigTests.cs           # ✅
    ├── InferenceTests.cs             # ✅
    ├── WavWriterTests.cs             # ✅
    ├── PhonemeConverterTests.cs      # ✅
    ├── PhonemeEncoderTests.cs        # ✅
    └── JapanesePhonemizerTests.cs    # ✅
```

### NuGet依存関係

**PiperPlus.Core:**
| パッケージ | バージョン | 用途 |
|-----------|----------|------|
| `Microsoft.ML.OnnxRuntime.Managed` | 1.24.3 | ONNX推論 (マネージドAPIのみ) |
| `Microsoft.Extensions.Logging.Abstractions` | 8.0.3 | PhonemeEncoder のロギング抽象化 |

> **注意 (Phase 3):** DotNetG2Pパッケージ (`DotNetG2P`, `DotNetG2P.MeCab`, `DotNetG2P.English`) は [ayutaz/dot-net-g2p](https://github.com/ayutaz/dot-net-g2p) で開発中。NuGet公開後に Core の依存に追加予定。現在 `JapanesePhonemizer` は `IJapaneseG2PEngine` 抽象インターフェース経由で G2P エンジンを受け取るため、DotNetG2P への直接依存はない。CLI (`Program.cs`) ではリフレクションで解決を試みる。

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

---

## 2. CLI インターフェース仕様 ✅ (一部未実装)

C++版 (`src/cpp/main.cpp`) と同等のCLIを提供する。

### 2.1 コマンドラインオプション

#### 実装済み ✅

| オプション | 短形式 | 型 | デフォルト | 説明 |
|-----------|--------|-----|---------|------|
| `--model` | `-m` | FileInfo | 必須 | .onnxモデルファイル |
| `--config` | `-c` | FileInfo | 自動検出 | config.jsonパス |
| `--text` | `-t` | string | - | テキスト直接入力 (JSONL不要) |
| `--language` | - | string | `ja` | `--text` モード用言語: `ja` / `en` |
| `--output_file` | `-f` | string | - | 出力WAVパス (`-`=stdout) |
| `--output_dir` | `-d` | DirectoryInfo | `.` | 出力ディレクトリ |
| `--output_raw` | - | flag | - | Raw PCM (int16) をstdoutに出力 |
| `--speaker` | `-s` | int | 0 | 話者ID |
| `--noise_scale` | - | float | 0.667 | ノイズスケール |
| `--length_scale` | - | float | 1.0 | 長さスケール |
| `--noise_w` | - | float | 0.8 | Duration Predictorノイズ |
| `--sentence_silence` | - | float | 0.2 | 文末無音(秒) |
| `--json-input` | - | flag | - | stdin をJSONLとして解釈 |
| `--version` | - | flag | - | バージョン表示 |
| `--debug` | - | flag | - | DEBUGログ (stderr) |
| `--quiet` | `-q` | flag | - | ログ無効 |

> **注意:** `--text` と `--json-input` は排他。両方指定するとエラーになる。

#### 未実装 (Phase 3以降)

| オプション | 短形式 | 型 | デフォルト | 説明 |
|-----------|--------|-----|---------|------|
| `--list-models` | - | string? | - | モデル一覧表示 |
| `--download-model` | - | string | - | モデルダウンロード |
| `--model-dir` | - | DirectoryInfo | OS依存 | モデル保存先 |
| `--use-cuda` | - | flag | - | CUDA実行プロバイダー使用 |
| `--gpu-device-id` | - | int | 0 | CUDA GPUデバイスID |
| `--phoneme_silence` | - | string | - | 音素別無音設定 (`<phoneme> <seconds>`) |
| `--raw-phonemes` | - | flag | - | 入力を音素として解釈 |
| `--streaming` | - | flag | - | ストリーミングモード |
| `--output-timing` | - | FileInfo | - | 音素タイミング出力パス |
| `--timing-format` | - | string | `json` | タイミング形式 (json/tsv) |
| `--custom-dict` | - | string | - | カスタム辞書ファイル (カンマ区切り) |
| `--espeak_data` | - | DirectoryInfo | 自動検出 | espeak-ngデータパス |
| `--tashkeel_model` | - | FileInfo | - | libtashkeel ORTモデル (アラビア語) |
| `--test-mode` | - | flag | - | ONNX実行スキップ (CI用) |

### 2.2 環境変数

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
| JSONL stdin | `--json-input` または stdin パイプ | 1行1発話。pre-encoded phoneme_ids を含む JSON。 |

**JSONL フォーマット:**
```json
{"phoneme_ids":[1,8,5,39], "speaker_id":0, "output_file":"out.wav", "prosody_features":[[a1,a2,a3],...]}
```

> **注意:** JSONL の `prosody_features` はネストした配列形式 `[[a1,a2,a3],...]`。Python 版の dict 形式 `[{"a1":1,"a2":2,"a3":3},...]` とは異なる。

**出力モード:**

| モード | 条件 | 説明 |
|--------|------|------|
| ディレクトリ | デフォルト | `{output_dir}/{index}.wav` |
| 単一ファイル | `--output_file path` | 指定パスに WAV 出力 |
| WAV stdout | `--output_file -` | WAV バイナリを stdout に出力 |
| Raw PCM stdout | `--output_raw` | ヘッダーなし int16 PCM を stdout に出力 |

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

**scales配列:** `[noise_scale, length_scale, noise_scale_w]` — デフォルト値: `[0.667, 1.0, 0.8]`

### 3.2 出力テンソル ✅

| テンソル名 | 型 | Shape |
|-----------|------|--------|
| `output` | float32 | `[1, 1, audio_samples]` |

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

`PiperModel` コンストラクタで `InferenceSession.InputMetadata` のキーを検査して能力を判定する。

```csharp
// PiperModel コンストラクタ内:
HasSpeakerId = _session.InputMetadata.ContainsKey("sid");
HasProsody   = _session.InputMetadata.ContainsKey("prosody_features");
```

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

- **必ず1文字 (1 codepoint)** — 多文字音素はPUA (U+E000–U+E01C) に変換済み
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

## 6. 英語音素化パイプライン (未実装 — Phase 3)

### 処理フロー

```
テキスト
  → [1] DotNetG2P.English.EnglishG2PEngine.ToPhonemeList(text)
    → ARPAbet トークン列
  → [2] 機能語判定 (~110語リスト) → ストレス除去
  → [3] ARPAbet → IPA 変換 (文脈依存: AA+R→ɑːɹ, ER1→ɜː)
  → [4] ストレスマーカー挿入 (ˈ/ˌ)
  → [5] 単語間スペース挿入 (句読点は前単語に付着)
  → [6] phoneme_id_map ルックアップ
  → [7] post_process_ids: BOS(^) + PAD(_) + 音素 + PAD(_) + ... + EOS($)
```

### BOS/EOS/PAD挿入 (英語のみ)

```
元:     [10, 59, 24, 120, 27, 100]
PAD挿入: [10, 0, 59, 0, 24, 0, 120, 0, 27, 0, 100, 0]
BOS/EOS: [1, 0, 10, 0, 59, 0, 24, 0, 120, 0, 27, 0, 100, 0, 2]
```

**注意:** 日本語モデルではinter-phoneme PADは挿入しない。英語(eSpeak)モデルのみ。

---

## 7. G2P 抽象レイヤーと DotNetG2P 統合

### 7.1 IJapaneseG2PEngine 抽象インターフェース ✅

`JapanesePhonemizer` は G2P エンジンへの直接依存を持たず、`IJapaneseG2PEngine` インターフェースを通じてエンジンを注入する。これにより DotNetG2P 未公開時もテスト可能。

```csharp
// IPhonemizer.cs 内で定義:
public record G2PResult(string[] Phonemes, int[] A1, int[] A2, int[] A3);

public interface IJapaneseG2PEngine
{
    G2PResult Convert(string text);
}
```

**テストでのモック使用例:**
```csharp
// テストで IJapaneseG2PEngine をモック実装して JapanesePhonemizer を検証可能
var mockEngine = new MockG2PEngine(/* 固定値を返す */);
var phonemizer = new JapanesePhonemizer(mockEngine);
var tokens = phonemizer.Phonemize("こんにちは");
```

**CLI での解決 (`Program.cs`):** DotNetG2P がインストールされている場合、リフレクションで `DotNetG2PEngine` を検出して `IJapaneseG2PEngine` として注入する。未インストール時は `NotSupportedException` をスローし、JSONL stdin モードの使用を案内する。

### 7.2 DotNetG2P API (Phase 3 — NuGet公開待ち)

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
| `EncodeDirect(phonemizer, text, phonemeIdMap)` | `(long[], long?)` | ONNX テンソル用 long 配列 (prosody は flat `[a1,a2,a3,...]`) |
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

## 8. uPiper 再利用コード

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

## 9. モデル管理 (未実装 — Phase 3)

### カタログソース

1. **組み込みpiper-plusカタログ** (C#コード内にJSON定義)
2. **上流piper voices.json** (オプション、ファイルから読み込み)

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
- Repo ID: `owner/repo` 形式のみ許可
- URL: HTTPS + HuggingFaceドメインのみ

---

## 10. WAV書き出し ✅

44バイト PCM WAVヘッダー + int16サンプルデータ。NAudio不要。

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

## 11. CI/CD

### ワークフロー構成

| ファイル | 用途 | トリガー |
|---------|------|---------|
| `csharp-ci.yml` | ビルド+テスト (3 OS) | PR/push to dev |
| `csharp-build-all-platforms.yml` | 6 RIDビルド (再利用可能) | workflow_call |

### ビルドマトリクス

| RID | ランナー | 優先度 |
|-----|---------|-------|
| `win-x64` | windows-2022 | 必須 |
| `win-arm64` | windows-2022 (クロス) | 推奨 |
| `linux-x64` | ubuntu-22.04 | 必須 |
| `linux-arm64` | ubuntu-22.04 (クロス) | 必須 |
| `osx-x64` | macos-14 (クロス) | 推奨 |
| `osx-arm64` | macos-14 | 必須 |

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

## 12. 既知の注意点

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
