# Piper Plus C# CLI 実装計画

Issue #245 対応。`docs/csharp-cli-implementation-guide.md` に基づく段階的実装計画。

---

## フェーズ概要

| フェーズ | 目標 | 依存 | 成果物 |
|---------|------|------|--------|
| **1: スケルトン + ONNX推論** | JSONL入力 → WAV出力の最小実装 | なし | ONNX推論 + WAV書き出し |
| **2: 日本語音素化** | `--text "日本語"` → WAV | Phase 1 + DotNetG2P | 日本語パイプライン完成 |
| **3: CLI完全化** | C++版と同等の全CLIオプション | Phase 1 | フル機能CLI |
| **4: モデル管理** | `--list-models` / `--download-model` | Phase 1 | カタログ + ダウンロード |
| **5: 英語音素化** | `--language en` 対応 | Phase 2 | 英語G2Pパイプライン |
| **6: CI/CD + 配布** | 6 RIDビルド + テスト + リリース | Phase 3 | GitHub Actions + NuGet |

**クリティカルパス（最短で --text → WAV）:** Phase 1 → Phase 2

### 依存関係図

```
Phase 1 (スケルトン + ONNX推論)
  |
  +---> Phase 2 (日本語音素化) ---> Phase 5 (英語音素化)
  |
  +---> Phase 3 (CLI完全化)    ---> Phase 6 (CI/CD)
  |
  +---> Phase 4 (モデル管理)
```

Phase 2, 3, 4 は Phase 1 完了後に並行着手可能。

---

## Phase 1: スケルトン + ONNX推論

**目標:** phoneme_idsを含むJSONLをstdinから読み込み、ONNX推論を実行し、WAVファイルを出力する。

### 作成ファイル

| ファイル | 説明 |
|---------|------|
| `src/csharp/PiperPlus.sln` | ソリューション |
| `src/csharp/Directory.Build.props` | 共通設定 |
| `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj` | net8.0, OnnxRuntime.Managed |
| `src/csharp/PiperPlus.Core/Inference/PiperSession.cs` | ONNX推論ラッパー |
| `src/csharp/PiperPlus.Core/Inference/PiperModel.cs` | モデル能力検出 (has_sid, has_prosody) |
| `src/csharp/PiperPlus.Core/Inference/WavWriter.cs` | 44バイトヘッダー + PCM int16 |
| `src/csharp/PiperPlus.Core/Config/PiperConfig.cs` | config.json デシリアライズ |
| `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj` | net10.0, System.CommandLine |
| `src/csharp/PiperPlus.Cli/Program.cs` | 最小CLI (--model, --config, --json-input) |
| `src/csharp/PiperPlus.Core.Tests/PiperPlus.Core.Tests.csproj` | xunit.v3 テスト |
| `src/csharp/PiperPlus.Core.Tests/WavWriterTests.cs` | WAVヘッダーテスト |
| `src/csharp/PiperPlus.Core.Tests/PiperConfigTests.cs` | config.jsonパーステスト |

### 実装タスク

- [ ] `dotnet new sln` + 3プロジェクト作成
- [ ] `Directory.Build.props` 作成（TFMは各csprojで個別指定）
- [ ] `PiperConfig.cs`: System.Text.Json source generatorでトリム安全にデシリアライズ
  - 必須: `phoneme_id_map`, `audio.sample_rate`, `inference.*`, `num_speakers`
  - config.json検索順序: --config → env → model_path+.json → model_dir/config.json
- [ ] `PiperModel.cs`: InputMetadataから `sid`, `prosody_features` 検出
- [ ] `PiperSession.cs`: `OrtValue.CreateTensorValueFromMemory` でテンソル構築 → `session.Run()`
  - float32→int16変換: ピーク正規化 (max/32767) + clamp
- [ ] `WavWriter.cs`: BinaryWriterで44バイトPCM WAVヘッダー書き出し
- [ ] `Program.cs`: System.CommandLineで最小オプション定義、JSONL stdin読み込み

### テスト項目

- [ ] WavWriter: ヘッダーバイト列の全フィールド検証
- [ ] PiperConfig: PUA文字キーの正常デシリアライズ
- [ ] float32→int16: ゼロ配列、正規化済み配列、クリッピング配列

### 完了条件

```bash
echo '{"phoneme_ids":[1,10,0,5,...], "speaker_id":0}' | \
  dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model test.onnx --output_dir ./out
# → WAVファイルが生成される
```

### リスク

| リスク | 対策 |
|--------|------|
| net10.0 SDKが環境にない | Cliを一時的にnet9.0で開始、後で切り替え |
| ONNX Runtime トリム警告 | `TrimmerRootAssembly` で除外指定 |

---

## Phase 2: 日本語音素化パイプライン

**目標:** `--text "こんにちは"` で日本語テキストから直接WAV生成。

**依存:** Phase 1 完了

### 作成ファイル

| ファイル | 説明 |
|---------|------|
| `src/csharp/PiperPlus.Core/Phonemize/IPhonemizer.cs` | 音素化インターフェース |
| `src/csharp/PiperPlus.Core/Phonemize/JapanesePhonemizer.cs` | DotNetG2P統合 |
| `src/csharp/PiperPlus.Core/Phonemize/PiperPhonemeConverter.cs` | PUA変換 + N変異 + 疑問詞 |
| `src/csharp/PiperPlus.Core/Phonemize/PhonemeEncoder.cs` | phoneme_id変換 (uPiper移植) |
| `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` | PUAテーブル (uPiper移植) |
| `src/csharp/PiperPlus.Core.Tests/JapanesePhonemizerTests.cs` | 日本語音素化テスト |
| `src/csharp/PiperPlus.Core.Tests/PhonemeConverterTests.cs` | PUA・N変異テスト |

### 実装タスク

- [ ] `IPhonemizer.cs`: `Phonemize()`, `PhonemizeWithProsody()`, `GetPhonemeIdMap()`, `PostProcessIds()` — Python `base.py` と1:1対応
- [ ] `OpenJTalkToPiperMapping.cs`: uPiperからコピー（29エントリ、U+E000–U+E01C）
- [ ] `PiperPhonemeConverter.cs`:
  - `GetQuestionType(text)`: Python `_get_question_type` 移植（5種）
  - `ApplyNPhonemeRules(tokens)`: Python `_apply_n_phoneme_rules` 移植（4変異）
  - `MapSequence(tokens)`: 多文字→PUA変換
- [ ] `JapanesePhonemizer.cs`: DotNetG2P → sil/pau変換 → 韻律マーク → 疑問詞 → N変異 → PUA → phoneme_ids
- [ ] `PhonemeEncoder.cs`: uPiperから移植（PiperLogger→ILogger置換）
- [ ] `Program.cs` に `--text`, `--speaker`, `--language` 追加

### テスト項目

- [ ] PUAマッピング29エントリがPython `FIXED_PUA_MAPPING` と完全一致
- [ ] 疑問詞判定: `"本当?!"` → `?!`, `"そうなの?."` → `?.`, `"行くよね?~"` → `?~`
- [ ] N変異: `さんぽ` → N_m, `あんない` → N_n, `ぎんこう` → N_ng, `ほん` → N_uvular
- [ ] E2E: `"こんにちは"` のphoneme_idsがPython実装と一致

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model ja_model.onnx --text "こんにちは、今日は良い天気ですね。" \
  --speaker 0 --output_dir ./out
# → WAVファイルが生成される
```

### リスク

| リスク | 深刻度 | 対策 |
|--------|--------|------|
| **DotNetG2PがNuGet未公開** | 高 | A: GitSubmoduleで取り込み / B: NuGet公開リクエスト / C: JSONL入力のみで先行 |
| MeCab辞書パス | 中 | 環境変数 `DOTNETG2P_NAIST_JDIC_PATH` をドキュメント案内 |

---

## Phase 3: CLI完全化

**目標:** C++版と同等の全CLIオプションが動作する。

**依存:** Phase 1 完了（Phase 2と並行可能）

### 実装タスク

- [ ] 全30 CLIオプション実装（実装ガイド Section 2.1）
- [ ] 環境変数4種対応
- [ ] 出力モード4種: FILE / DIRECTORY / STDOUT / RAW
- [ ] `--json-input`: text, speaker_id, speaker, output_file, prosody_features
- [ ] `--use-cuda` / `--gpu-device-id`: CUDA EP条件付きロード
- [ ] `--sentence_silence`: 文末ゼロサンプル挿入（デフォルト0.2秒）
- [ ] `--phoneme_silence`: 音素別無音挿入
- [ ] `--streaming`: チャンク単位raw PCM stdout出力
- [ ] `--output-timing` / `--timing-format`: JSON/TSV音素タイミング
- [ ] `--custom-dict`: カスタム辞書読み込み
- [ ] `--test-mode`, `--debug`, `--quiet`, `--version`

### 完了条件

C++ CLIのヘルプ出力と同等のオプション一覧が表示され、各オプションが動作する。

---

## Phase 4: モデル管理

**目標:** `--list-models` / `--download-model` でモデルカタログ管理。

**依存:** Phase 1 完了

### 実装タスク

- [ ] `VoiceCatalog.cs`: 埋め込みカタログJSON（tsukuyomi-chan, moe-speech-20speakers）
- [ ] `ModelManager.cs`:
  - OS別デフォルトモデルディレクトリ
  - `FindVoice(nameOrAlias)`: キー→エイリアス順検索
  - `ListModels(langFilter)`: stderr出力、C++版フォーマット一致
  - `DownloadModel()`: HttpClient + HTTPS強制 + サイズ検証
- [ ] セキュリティ検証: パストラバーサル禁止、repoId形式チェック

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- --list-models ja
dotnet run --project src/csharp/PiperPlus.Cli -- --download-model tsukuyomi
```

---

## Phase 5: 英語音素化

**目標:** `--language en --text "Hello world"` で英語WAV生成。

**依存:** Phase 2 完了（IPhonemizerインターフェース）

### 実装タスク

- [ ] `ArpabetToIPAConverter.cs`: uPiperから100%移植
- [ ] `EnglishPhonemizer.cs`:
  - DotNetG2P.English → ARPAbetトークン
  - 機能語判定（~110語リスト）→ ストレス除去
  - ARPAbet→IPA変換（文脈依存: AA+R→ɑːɹ, ER1→ɜː）
  - ストレスマーカー（ˈ/ˌ）挿入
  - `PostProcessIds()`: BOS + PAD + 音素 + PAD + ... + EOS（英語のみinter-phoneme PAD）

### 完了条件

```bash
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model en_model.onnx --text "Hello, how are you today?" \
  --language en --output_dir ./out
```

### リスク

| リスク | 対策 |
|--------|------|
| DotNetG2P.English vs g2p-en のOOV差異 | 主要テストケースでPython出力と差分計測 |

---

## Phase 6: CI/CD + 配布

**目標:** 6 RIDビルド・テスト・リリースの自動化。

**依存:** Phase 3 完了

### 作成ファイル

| ファイル | 説明 |
|---------|------|
| `.github/workflows/csharp-ci.yml` | ビルド+テスト (3 OS) |
| `.github/workflows/csharp-build-all-platforms.yml` | 6 RIDビルド |

### 実装タスク

- [ ] CI: ubuntu/windows/macOS の3 OSマトリクス、`dotnet test` 実行
- [ ] ビルド: 6 RID × Self-Contained。クロスコンパイル時は `PublishReadyToRun=false`
- [ ] アセット: `piper-plus-cli-{rid}.{zip|tar.gz}`
- [ ] NuGet: `<PackAsTool>true</PackAsTool>` 設定
- [ ] 既存 `dev-create-release.yml` にC# CLIジョブを統合

### 完了条件

PRトリガーで自動テスト通過、リリース時に6 RIDバイナリ生成。
