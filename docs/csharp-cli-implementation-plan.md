# Piper Plus C# CLI 実装計画

Issue #245 対応。`docs/csharp-cli-implementation-guide.md` に基づく段階的実装計画。

---

## フェーズ概要

| フェーズ | 目標 | 依存 | 成果物 | 状態 |
|---------|------|------|--------|------|
| **1: スケルトン + ONNX推論** | JSONL入力 → WAV出力の最小実装 | なし | ONNX推論 + WAV書き出し | **完了** |
| **2: 日本語音素化** | `--text "日本語"` → WAV | Phase 1 + DotNetG2P | 日本語パイプライン完成 | **完了** |
| **3: CLI完全化** | C++版と同等の全CLIオプション | Phase 1 | フル機能CLI | **完了** |
| **4: モデル管理** | `--list-models` / `--download-model` | Phase 1 | カタログ + ダウンロード | **完了** |
| **5: 英語音素化** | `--language en` 対応 | Phase 2 | 英語G2Pパイプライン | **完了** |
| **6: CI/CD + 配布** | 6 RIDビルド + テスト + リリース | Phase 3 | GitHub Actions + NuGet | **完了** |
| **7: 6言語マルチリンガル対応** | C# CLIで6言語推論サポート | Phase 5 | 6言語Phonemizer + lidテンソル | **未着手** |

**クリティカルパス（最短で --text → WAV）:** Phase 1 → Phase 2 **完了**

### 依存関係図

```
Phase 1 (スケルトン + ONNX推論) ............. [DONE]
  |
  +---> Phase 2 (日本語音素化) .............. [DONE]
  |       |
  |       +---> Phase 5 (英語音素化) .......... [DONE]
  |               |
  |               +---> Phase 7 (6言語マルチリンガル) .. [TODO]
  |
  +---> Phase 3 (CLI完全化) ................. [DONE] ---> Phase 6 (CI/CD) .. [DONE]
  |
  +---> Phase 4 (モデル管理) ................ [DONE]
```

Phase 3, 4, 5 は並行着手可能。Phase 7 は Phase 5 完了後に着手。

---

## Phase 1: スケルトン + ONNX推論 --- 完了

**目標:** phoneme_idsを含むJSONLをstdinから読み込み、ONNX推論を実行し、WAVファイルを出力する。

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.sln` | ソリューション | 完了 |
| `src/csharp/Directory.Build.props` | 共通設定 (LangVersion, Nullable, TrimAnalyzer等) | 完了 |
| `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj` | net8.0, OnnxRuntime.Managed 1.24.3 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/PiperSession.cs` | ONNX推論ラッパー + float32→int16変換 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/PiperModel.cs` | InputMetadata からsid/prosody_features検出 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/WavWriter.cs` | 44バイトヘッダー + MemoryMarshal.AsBytes バルク書き出し | 完了 |
| `src/csharp/PiperPlus.Core/Config/PiperConfig.cs` | System.Text.Json SG でトリム安全デシリアライズ | 完了 |
| `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj` | net9.0, System.CommandLine 2.0.5 | 完了 |
| `src/csharp/PiperPlus.Cli/Program.cs` | CLI (16オプション: --model, --config, --text, --language 等) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/PiperPlus.Core.Tests.csproj` | net9.0, xunit.v3 | 完了 |
| `src/csharp/PiperPlus.Core.Tests/WavWriterTests.cs` | WAVヘッダーテスト (8テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/PiperConfigTests.cs` | config.jsonパーステスト (17テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/InferenceTests.cs` | ConvertToInt16 + SynthesisInput テスト (10テスト) | 完了 |

### 実装タスク

- [x] `dotnet new sln` + 3プロジェクト作成
- [x] `Directory.Build.props` 作成（TFMは各csprojで個別指定）
- [x] `PiperConfig.cs`: System.Text.Json source generatorでトリム安全にデシリアライズ
  - 必須: `phoneme_id_map`, `audio.sample_rate`, `inference.*`, `num_speakers`
  - config.json検索順序: --config → env(`PIPER_DEFAULT_CONFIG`) → model_path+.json → model_dir/config.json
- [x] `PiperModel.cs`: InputMetadataから `sid`, `prosody_features` 検出
- [x] `PiperSession.cs`: `OrtValue.CreateTensorValueFromMemory` でテンソル構築 → `session.Run()`
  - float32→int16変換: ピーク正規化 (max/32767) + 対称クリッピング [-32767, 32767]
- [x] `WavWriter.cs`: BinaryWriter + `MemoryMarshal.AsBytes` で44バイトPCM WAVヘッダー + バルク書き出し
- [x] `Program.cs`: System.CommandLineで16オプション定義、JSONL stdin読み込み + --text モード

### テスト項目

- [x] WavWriter: ヘッダーバイト列の全フィールド検証 (8テスト)
- [x] PiperConfig: PUA文字キーの正常デシリアライズ + FindConfigPath (17テスト)
- [x] Inference: ゼロ配列、正規化済み配列、クリッピング配列、対称性、SynthesisInput (10テスト)

### 完了条件

```bash
echo '{"phoneme_ids":[1,10,0,5,...], "speaker_id":0}' | \
  dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model test.onnx --output_dir ./out
# → WAVファイルが生成される
```

**達成済み。** JSONL stdin入力とWAV出力が動作する。

### リスク（対応結果）

| リスク | 対策 | 結果 |
|--------|------|------|
| net10.0 SDKが環境にない | Cliを一時的にnet9.0で開始、後で切り替え | **net9.0に変更して解決** (C1: TFM net10.0 → net9.0) |
| ONNX Runtime トリム警告 | `TrimmerRootAssembly` で除外指定 | Directory.Build.propsでEnableTrimAnalyzer有効化済み |
| リソースリーク | RunOptions/SessionOptions を適切にDispose | **修正済み** (H3/H5: using宣言追加) |
| クリッピング非対称 | 対称化: [-32767, 32767] | **修正済み** (H1: Math.Clamp(-32767f, 32767f)) |

---

## Phase 2: 日本語音素化パイプライン --- 完了

**目標:** `--text "こんにちは"` で日本語テキストから直接WAV生成。

**依存:** Phase 1 完了

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Phonemize/IPhonemizer.cs` | ProsodyInfo record + IPhonemizer interface (PostProcessIds デフォルトno-op) | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/JapanesePhonemizer.cs` | IJapaneseG2PEngine抽象化 + PhonemizeCore (Python 1:1対応) | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/PiperPhonemeConverter.cs` | GetQuestionType + ApplyNPhonemeRules + MapSequence | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/PhonemeEncoder.cs` | Encode + EncodeDirect (ONNX tensor形式変換) | 完了 |
| `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` | PUA固定マッピング29エントリ (U+E000-U+E01C) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/JapanesePhonemizerTests.cs` | 日本語音素化テスト (8テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/PhonemeConverterTests.cs` | PUA・N変異テスト (21テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/PhonemeEncoderTests.cs` | エンコーダーテスト (9テスト) | 完了 |

### 実装タスク

- [x] `IPhonemizer.cs`: `Phonemize()`, `PhonemizeWithProsody()`, `GetPhonemeIdMap()`, `PostProcessIds()` -- Python `base.py` と1:1対応
- [x] `OpenJTalkToPiperMapping.cs`: 29エントリPUAマッピング（U+E000-U+E01C）、TokenToChar / CharToToken 双方向 + MapToken / MapSequence
- [x] `PiperPhonemeConverter.cs`:
  - `GetQuestionType(text)`: Python `_get_question_type` 移植（5種: $, ?, ?!, ?., ?~）、全角対応
  - `ApplyNPhonemeRules(tokens)`: Python `_apply_n_phoneme_rules` 移植（4変異: N_m, N_n, N_ng, N_uvular）
  - `MapSequence(tokens)`: OpenJTalkToPiperMapping経由の多文字→PUA変換
- [x] `JapanesePhonemizer.cs`: IJapaneseG2PEngine → sil/pau変換 → 韻律マーク (], #, [) → N変異 → PUA → phoneme_ids
  - DotNetG2Pへの直接依存を`IJapaneseG2PEngine`インターフェースで抽象化
- [x] `PhonemeEncoder.cs`: Encode (token→ID + prosody伝搬) + EncodeDirect (long[] + flat prosody変換)
- [x] `Program.cs` に `--text`, `--speaker`, `--language` 追加
  - JapanesePhonemizer は直接参照（H4: リフレクション削減）
  - DotNetG2PEngine はNuGet未公開のためリフレクション解決を維持

### テスト項目

- [x] PUAマッピング29エントリがPython `FIXED_PUA_MAPPING` と完全一致 (1テスト)
- [x] 疑問詞判定: `"本当?!"` → `?!`, `"そうなの?."` → `?.`, `"行くよね?~"` → `?~` + 全角対応 (10テスト)
- [x] N変異: さんぽ→N_m, あんない→N_n, ぎんこう→N_ng, ほん→N_uvular + スキップ・複数N (8テスト)
- [x] PhonemeEncoder: トークン→ID変換、prosody伝搬、未知トークン、multi-IDトークン、PostProcessIds呼び出し (9テスト)
- [x] JapanesePhonemizer E2E: スタブG2Pを使用した統合テスト (8テスト)

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model ja_model.onnx --text "こんにちは、今日は良い天気ですね。" \
  --speaker 0 --output_dir ./out
# → WAVファイルが生成される（DotNetG2P が利用可能な場合）
```

**達成済み。** 音素化パイプラインの全コンポーネントが実装・テスト済み。DotNetG2PがNuGet公開された時点で即座にE2E動作する。

### リスク（対応結果）

| リスク | 深刻度 | 対策 | 結果 |
|--------|--------|------|------|
| **DotNetG2PがNuGet未公開** | 高 | A: GitSubmoduleで取り込み / B: NuGet公開リクエスト / C: JSONL入力のみで先行 | **IJapaneseG2PEngine インターフェースで抽象化して解決。** DotNetG2PEngineはリフレクションで遅延解決。NuGet未公開でもJSONL入力モードは動作、テストはスタブG2Pで全て通過。 |
| MeCab辞書パス | 中 | 環境変数 `DOTNETG2P_NAIST_JDIC_PATH` をドキュメント案内 | 実装済み。DotNetG2P利用時の要件としてドキュメント案内予定。 |
| リフレクション使用 | 低 | JapanesePhonemizer は直接参照に変更 | **修正済み** (H4)。DotNetG2PEngine のみリフレクション維持（NuGet依存回避のため意図的）。 |

---

## Phase 3: CLI完全化 --- 完了

**目標:** C++版と同等の全CLIオプションが動作する。

**依存:** Phase 1 完了（Phase 2と並行可能）

**状態:** ✅ 完了

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs` | CUDA EP条件付きセッション生成 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/StreamingWriter.cs` | チャンク単位raw PCM stdout出力 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/PhonemeSilenceProcessor.cs` | 音素別無音挿入 | 完了 |
| `src/csharp/PiperPlus.Core/Inference/TimingWriter.cs` | JSON/TSV音素タイミング出力 | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/CustomDictionary.cs` | カスタム辞書読み込み | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/RawPhonemeParser.cs` | 生音素文字列パーサー | 完了 |
| `src/csharp/PiperPlus.Core.Tests/Phase3Tests.cs` | Phase 3 テスト (37テスト) | 完了 |

### 実装タスク

- [x] 全30 CLIオプション実装（実装ガイド Section 2.1）
  - Phase 1/2 で実装済み: `--model`, `--config`, `--text`, `--language`, `--speaker`, `--output_file`, `--output_dir`, `--output-raw`, `--json-input`, `--noise-scale`, `--length-scale`, `--noise-w`, `--sentence_silence`, `--debug`, `--quiet`, `--version`
  - Phase 3 で新規追加: `--use-cuda`, `--gpu-device-id`, `--phoneme_silence`, `--streaming`, `--output-timing`, `--timing-format`, `--custom-dict`, `--test-mode`
- [x] 環境変数4種対応
  - `PIPER_DEFAULT_MODEL` と `PIPER_DEFAULT_CONFIG` は Phase 1 で実装済み
  - `PIPER_MODEL_DIR` と `PIPER_DEFAULT_DATA_DIR` は Phase 3 で追加
- [x] 出力モード4種: FILE / DIRECTORY / STDOUT / RAW
  - 全4モードが Phase 1 で実装済み
- [x] `--json-input`: text, speaker_id, speaker, output_file, prosody_features
  - 基本実装は Phase 1 で完了
- [x] `--use-cuda` / `--gpu-device-id`: CUDA EP条件付きロード
- [x] `--sentence_silence`: 文末ゼロサンプル挿入（デフォルト0.2秒）
  - Phase 1 で PiperSession.SentenceSilenceSeconds として実装済み
- [x] `--phoneme_silence`: 音素別無音挿入
- [x] `--streaming`: チャンク単位raw PCM stdout出力
- [x] `--output-timing` / `--timing-format`: JSON/TSV音素タイミング
- [x] `--custom-dict`: カスタム辞書読み込み
- [x] `--test-mode`, `--debug`, `--quiet`, `--version`
  - `--debug`, `--quiet`, `--version` は Phase 1 で実装済み

### 完了条件

C++ CLIのヘルプ出力と同等のオプション一覧が表示され、各オプションが動作する。

**達成済み。** C++版と同等の全CLIオプションが実装・動作する。

---

## Phase 4: モデル管理 --- 完了

**目標:** `--list-models` / `--download-model` でモデルカタログ管理。

**依存:** Phase 1 完了

**状態:** ✅ 完了

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Config/VoiceInfo.cs` | レコード定義 | 完了 |
| `src/csharp/PiperPlus.Core/Config/VoiceCatalog.cs` | 埋め込みカタログ + 外部カタログ統合 | 完了 |
| `src/csharp/PiperPlus.Core/Config/VoiceJsonModels.cs` | JSON デシリアライズモデル | 完了 |
| `src/csharp/PiperPlus.Core/Config/ModelManager.cs` | find/list/download + セキュリティ検証 | 完了 |
| `src/csharp/PiperPlus.Core.Tests/VoiceCatalogTests.cs` | カタログテスト (11テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/ModelManagerTests.cs` | モデル管理テスト (13テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/Phase4IntegrationTests.cs` | Phase 4 統合テスト (12テスト) | 完了 |

### 実装タスク

- [x] `VoiceInfo.cs`: ボイス情報レコード定義
- [x] `VoiceCatalog.cs`: 埋め込みカタログJSON（tsukuyomi-chan, moe-speech-20speakers）+ 外部カタログ統合
- [x] `VoiceJsonModels.cs`: JSON デシリアライズモデル
- [x] `ModelManager.cs`:
  - OS別デフォルトモデルディレクトリ
  - `FindVoice(nameOrAlias)`: キー→エイリアス順検索
  - `ListModels(langFilter)`: stderr出力、C++版フォーマット一致
  - `DownloadModel()`: HttpClient + HTTPS強制 + サイズ検証
- [x] セキュリティ検証: パストラバーサル禁止、repoId形式チェック

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- --list-models ja
dotnet run --project src/csharp/PiperPlus.Cli -- --download-model tsukuyomi
```

**達成済み。** モデルカタログの一覧表示・ダウンロードが動作する。

---

## Phase 5: 英語音素化 --- 完了

**目標:** `--language en --text "Hello world"` で英語WAV生成。

**依存:** Phase 2 完了（IPhonemizerインターフェース）

**状態:** ✅ 完了

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Phonemize/ArpabetToIPAConverter.cs` | ARPABET→IPA変換 + 機能語リスト + 文脈依存ルール | 完了 |
| `src/csharp/PiperPlus.Core/Phonemize/EnglishPhonemizer.cs` | IEnglishG2PEngine + EnglishPhonemizer + PostProcessIds | 完了 |
| `src/csharp/PiperPlus.Core.Tests/ArpabetToIPAConverterTests.cs` | ARPABET→IPA変換テスト (19テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/EnglishPhonemizerTests.cs` | 英語音素化テスト (17テスト) | 完了 |
| `src/csharp/PiperPlus.Core.Tests/EnglishPostProcessIdsTests.cs` | BOS/EOS/PADテスト (15テスト) | 完了 |

### 実装タスク

- [x] `ArpabetToIPAConverter.cs`: ARPABET→IPA変換 + 機能語リスト (~110語) + 文脈依存ルール (AA+R→ɑːɹ, ER0→ɚ, ER1→ɜː)
- [x] `EnglishPhonemizer.cs`:
  - IEnglishG2PEngine インターフェースで G2P エンジンを抽象化
  - DotNetG2P.English → ARPAbetトークン
  - 機能語判定 → ストレス除去
  - ARPAbet→IPA変換（文脈依存）
  - ストレスマーカー（ˈ/ˌ）挿入
  - `PostProcessIds()`: BOS + PAD + 音素 + PAD + ... + EOS（英語のみinter-phoneme PAD）

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model en_model.onnx --text "Hello, how are you today?" \
  --language en --output_dir ./out
```

**達成済み。** 英語音素化パイプラインの全コンポーネントが実装・テスト済み。

### 備考

Program.cs には既に `--language en` のルーティングが実装済み（EnglishPhonemizer をリフレクション解決）。EnglishPhonemizer クラスを作成すれば即座に動作する。

### リスク（対応結果）

| リスク | 対策 | 結果 |
|--------|------|------|
| DotNetG2P.English vs g2p-en のOOV差異 | 主要テストケースでPython出力と差分計測 | テストで検証済み |
| DotNetG2P.English への直接依存 | インターフェース抽象化 | **IEnglishG2PEngine インターフェースで抽象化して解決。** 日本語と同様のパターンでG2Pエンジンを差し替え可能。 |

---

## Phase 6: CI/CD + 配布 --- 完了

**目標:** 6 RIDビルド・テスト・リリースの自動化。

**依存:** Phase 3 完了

**状態:** ✅ 完了

### 作成ファイル

| ファイル | 説明 | 状態 |
|---------|------|------|
| `.github/workflows/csharp-ci.yml` | 3 OS ビルド+テスト | 完了 |
| `.github/workflows/csharp-build-all-platforms.yml` | 6 RID ビルド | 完了 |
| `dev-create-release.yml` に C# CLI ジョブ統合 | リリースワークフロー統合 | 完了 |
| `src/csharp/.editorconfig` | コードスタイル | 完了 |
| `src/csharp/global.json` | SDK バージョン固定 | 完了 |
| `src/csharp/.gitignore` | ビルド出力除外 | 完了 |
| NuGet パッケージメタデータ (csproj 更新) | パッケージ情報 | 完了 |

### 実装タスク

- [x] CI: ubuntu/windows/macOS の3 OSマトリクス、`dotnet test` 実行
- [x] ビルド: 6 RID × Self-Contained。クロスコンパイル時は `PublishReadyToRun=false`
- [x] アセット: `piper-plus-cli-{rid}.{zip|tar.gz}`
- [x] NuGet: `<PackAsTool>true</PackAsTool>` 設定（Cli.csprojに設定済み）
- [x] 既存 `dev-create-release.yml` にC# CLIジョブを統合

### 完了条件

PRトリガーで自動テスト通過、リリース時に6 RIDバイナリ生成。

**達成済み。** 3 OS CI + 6 RID ビルド + リリースワークフロー統合が動作する。

---

## Phase 7: 6言語マルチリンガル対応 --- 未着手

**目標:** C# CLIで6言語マルチリンガルモデル（multilingual-test-medium.onnx）の推論を完全サポート。

**依存:** Phase 5 完了（IPhonemizerインターフェース + 英語音素化）

**状態:** 未着手

**背景:** devブランチにPR #218（C++ multilingual G2P）とPR #251（WebUI/HF/GitHub Pages 6言語対応）がマージされ、Python/C++は6言語（ja/en/zh/es/fr/pt）に対応済み。C# CLIは現在 ja/en のみ対応で、マルチリンガルモデル（multilingual-test-medium.onnx）を正常に推論できない。

### 作成・修正ファイル

#### Phase 7a: ONNX推論の多言語対応（最優先）

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Config/PiperConfig.cs` | `NumLanguages`, `LanguageIdMap` プロパティ追加 | 未着手 |
| `src/csharp/PiperPlus.Core/Inference/PiperModel.cs` | `HasLanguageId` プロパティ追加 | 未着手 |
| `src/csharp/PiperPlus.Core/Inference/PiperSession.cs` | `SynthesisInput` に `LanguageId` 追加、`lid` テンソル構築 | 未着手 |
| `src/csharp/PiperPlus.Cli/Program.cs` | JSONL に `language_id`/`language` フィールド対応、`--language` の6言語拡張 | 未着手 |

#### Phase 7b: ラテン系言語Phonemizer（依存なし、規則ベース）

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Phonemize/SpanishPhonemizer.cs` | スペイン語音素化（~900行、Python `spanish.py` から移植） | 未着手 |
| `src/csharp/PiperPlus.Core/Phonemize/FrenchPhonemizer.cs` | フランス語音素化（~850行、Python `french.py` から移植） | 未着手 |
| `src/csharp/PiperPlus.Core/Phonemize/PortuguesePhonemizer.cs` | ポルトガル語音素化（~750行、Python `portuguese.py` から移植） | 未着手 |

#### Phase 7c: CJK言語Phonemizer

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Phonemize/ChinesePhonemizer.cs` | 中国語音素化（~650行、規則ベース or pypinyin） | 未着手 |
| `src/csharp/PiperPlus.Core/Phonemize/KoreanPhonemizer.cs` | 韓国語音素化（~400行、ハングル分解規則ベース） | 未着手 |

#### Phase 7d: マルチリンガル統合

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` | UnicodeLanguageDetector + 言語別委譲（~400行） | 未着手 |
| `src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` | Unicode範囲ベース言語自動検出（~200行） | 未着手 |

#### Phase 7e: テスト

| ファイル | 説明 | 状態 |
|---------|------|------|
| `src/csharp/PiperPlus.Core.Tests/SpanishPhonemizerTests.cs` | スペイン語音素化テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/FrenchPhonemizerTests.cs` | フランス語音素化テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/PortuguesePhonemizerTests.cs` | ポルトガル語音素化テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/ChinesePhonemizerTests.cs` | 中国語音素化テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/KoreanPhonemizerTests.cs` | 韓国語音素化テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/MultilingualPhonemizerTests.cs` | マルチリンガル統合テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/LanguageIdTests.cs` | lid テンソル送信テスト | 未着手 |
| `src/csharp/PiperPlus.Core.Tests/MultilingualInferenceTests.cs` | 6言語E2E推論テスト | 未着手 |

### 実装タスク

- [ ] PiperConfig に NumLanguages / LanguageIdMap 追加
- [ ] PiperModel に HasLanguageId 検出追加
- [ ] PiperSession に lid テンソル構築追加
- [ ] SynthesisInput に LanguageId フィールド追加
- [ ] Program.cs の --language を6言語対応に拡張
- [ ] JSONL に language_id / language フィールド対応
- [ ] SpanishPhonemizer 実装（規則ベース）
- [ ] FrenchPhonemizer 実装（規則ベース）
- [ ] PortuguesePhonemizer 実装（規則ベース）
- [ ] ChinesePhonemizer 実装（規則ベース）
- [ ] KoreanPhonemizer 実装（規則ベース）
- [ ] MultilingualPhonemizer + UnicodeLanguageDetector 実装
- [ ] 全テスト実装・PASS

### 完了条件

```bash
# 6言語それぞれの推論
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "こんにちは" \
  --language ja --output_dir ./out

dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "Hello, how are you?" \
  --language en --output_dir ./out

dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "你好，今天天气很好。" \
  --language zh --output_dir ./out

dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "Hola, como estas?" \
  --language es --output_dir ./out

dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "Bonjour, comment allez-vous?" \
  --language fr --output_dir ./out

dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model multilingual-test-medium.onnx --text "Ola, como voce esta?" \
  --language pt --output_dir ./out
```

- multilingual-test-medium.onnx で全6言語の推論が成功
- `--language ja/en/zh/es/fr/pt` が全て動作
- JSONL で `language_id` / `language` フィールドが機能
- `lid` テンソルがONNX推論に正しく送信される
- 全テストPASS

### リスク

| リスク | 対策 |
|--------|------|
| 中国語の多音字消義精度 | 規則ベースで95-97%精度。Common 3500字テーブルで対応 |
| 韓国語の音韻規則精度 | ハングル分解は完全実装、複雑な規則は段階的追加 |
| ラテン系言語の移植量 | Python版が規則ベースで依存なし。直接移植で対応 |

### 推定規模

- 新規C#コード: ~5,000-6,000行
- テストコード: ~2,000-3,000行
- 外部依存追加: なし（全て規則ベース実装）

---

## テストサマリー

| フェーズ | テストファイル | テスト数 | 状態 |
|---------|--------------|---------|------|
| Phase 1 | WavWriterTests.cs | 8 | 完了 |
| Phase 1 | PiperConfigTests.cs | 17 | 完了 |
| Phase 1 | InferenceTests.cs | 10 | 完了 |
| Phase 2 | PhonemeConverterTests.cs | 21 | 完了 |
| Phase 2 | PhonemeEncoderTests.cs | 9 | 完了 |
| Phase 2 | JapanesePhonemizerTests.cs | 8 | 完了 |
| Phase 3 | Phase3Tests.cs | 37 | 完了 |
| Phase 4 | VoiceCatalogTests.cs | 11 | 完了 |
| Phase 4 | ModelManagerTests.cs | 13 | 完了 |
| Phase 4 | Phase4IntegrationTests.cs | 12 | 完了 |
| Phase 5 | ArpabetToIPAConverterTests.cs | 19 | 完了 |
| Phase 5 | EnglishPhonemizerTests.cs | 17 | 完了 |
| Phase 5 | EnglishPostProcessIdsTests.cs | 15 | 完了 |
| Phase 7 | SpanishPhonemizerTests.cs | - | 未着手 |
| Phase 7 | FrenchPhonemizerTests.cs | - | 未着手 |
| Phase 7 | PortuguesePhonemizerTests.cs | - | 未着手 |
| Phase 7 | ChinesePhonemizerTests.cs | - | 未着手 |
| Phase 7 | KoreanPhonemizerTests.cs | - | 未着手 |
| Phase 7 | MultilingualPhonemizerTests.cs | - | 未着手 |
| Phase 7 | LanguageIdTests.cs | - | 未着手 |
| Phase 7 | MultilingualInferenceTests.cs | - | 未着手 |
| **合計 (Phase 1-6)** | | **197** | |

---

## レビュー修正履歴

Phase 1/2 完了後のレビューで以下を修正済み:

| ID | 種別 | 内容 | 対象Phase |
|----|------|------|-----------|
| C1 | Critical | TFM net10.0 → net9.0 (Cli, Tests) | Phase 1 |
| H1 | High | クリッピング対称化 [-32767, 32767] (PiperSession.ConvertToInt16) | Phase 1 |
| H3 | High | RunOptions リソースリーク修正 (using宣言追加) | Phase 1 |
| H4 | High | リフレクション削減 — JapanesePhonemizer直接参照 | Phase 2 |
| H5 | High | SessionOptions リソースリーク修正 (using宣言追加) | Phase 1 |
| M2-M8 | Medium | ドキュメント、警告メッセージ、WavWriter MemoryMarshal.AsBytes パフォーマンス等 | Phase 1/2 |

---

## 全フェーズ完了サマリ

| フェーズ | 状態 | コミット |
|---------|------|--------|
| Phase 1: スケルトン + ONNX推論 | ✅ 完了 | 455fa83 |
| Phase 2: 日本語音素化 | ✅ 完了 | 42a72cc |
| レビュー修正 | ✅ 完了 | eb31ba9 |
| ドキュメント更新 | ✅ 完了 | 5b2faf5 |
| Phase 3: CLI完全化 | ✅ 完了 | 46002bd |
| Phase 4: モデル管理 | ✅ 完了 | 601a21f |
| Phase 5: 英語音素化 | ✅ 完了 | 66626f4 |
| Phase 6: CI/CD + 配布 | ✅ 完了 | a6c3062 |
| Phase 7: 6言語マルチリンガル対応 | 未着手 | - |

**総テスト数 (Phase 1-6):** 197 (13ファイル)
**総実装ファイル数 (Phase 1-6):** 35 (.cs) + 2 (workflows) + 3 (設定ファイル)
