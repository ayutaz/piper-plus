# Piper Plus C# CLI 実装計画

Issue #245 対応。`docs/csharp-cli-implementation-guide.md` に基づく段階的実装計画。

---

## フェーズ概要

| フェーズ | 目標 | 依存 | 成果物 | 状態 |
|---------|------|------|--------|------|
| **1: スケルトン + ONNX推論** | JSONL入力 → WAV出力の最小実装 | なし | ONNX推論 + WAV書き出し | **完了** |
| **2: 日本語音素化** | `--text "日本語"` → WAV | Phase 1 + DotNetG2P | 日本語パイプライン完成 | **完了** |
| **3: CLI完全化** | C++版と同等の全CLIオプション | Phase 1 | フル機能CLI | 未着手 |
| **4: モデル管理** | `--list-models` / `--download-model` | Phase 1 | カタログ + ダウンロード | 未着手 |
| **5: 英語音素化** | `--language en` 対応 | Phase 2 | 英語G2Pパイプライン | 未着手 |
| **6: CI/CD + 配布** | 6 RIDビルド + テスト + リリース | Phase 3 | GitHub Actions + NuGet | 未着手 |

**クリティカルパス（最短で --text → WAV）:** Phase 1 → Phase 2 **完了**

### 依存関係図

```
Phase 1 (スケルトン + ONNX推論) ............. [DONE]
  |
  +---> Phase 2 (日本語音素化) .............. [DONE]
  |       |
  |       +---> Phase 5 (英語音素化)
  |
  +---> Phase 3 (CLI完全化)    ---> Phase 6 (CI/CD)
  |
  +---> Phase 4 (モデル管理)
```

Phase 3, 4, 5 は並行着手可能。

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
| `src/csharp/PiperPlus.Core.Tests/PiperConfigTests.cs` | config.jsonパーステスト (16テスト) | 完了 |
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
- [x] PiperConfig: PUA文字キーの正常デシリアライズ + FindConfigPath (16テスト)
- [x] float32→int16: ゼロ配列、正規化済み配列、クリッピング配列、対称性 (10テスト)

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

## Phase 3: CLI完全化

**目標:** C++版と同等の全CLIオプションが動作する。

**依存:** Phase 1 完了（Phase 2と並行可能）

**状態:** 未着手

### 実装タスク

- [ ] 全30 CLIオプション実装（実装ガイド Section 2.1）
  - 既に16オプションが Phase 1/2 で実装済み
- [ ] 環境変数4種対応
  - `PIPER_DEFAULT_MODEL` と `PIPER_DEFAULT_CONFIG` は Phase 1 で実装済み
- [ ] 出力モード4種: FILE / DIRECTORY / STDOUT / RAW
  - 全4モードが Phase 1 で実装済み
- [ ] `--json-input`: text, speaker_id, speaker, output_file, prosody_features
  - 基本実装は Phase 1 で完了
- [ ] `--use-cuda` / `--gpu-device-id`: CUDA EP条件付きロード
- [ ] `--sentence_silence`: 文末ゼロサンプル挿入（デフォルト0.2秒）
  - Phase 1 で PiperSession.SentenceSilenceSeconds として実装済み
- [ ] `--phoneme_silence`: 音素別無音挿入
- [ ] `--streaming`: チャンク単位raw PCM stdout出力
- [ ] `--output-timing` / `--timing-format`: JSON/TSV音素タイミング
- [ ] `--custom-dict`: カスタム辞書読み込み
- [ ] `--test-mode`, `--debug`, `--quiet`, `--version`
  - `--debug`, `--quiet`, `--version` は Phase 1 で実装済み

### 完了条件

C++ CLIのヘルプ出力と同等のオプション一覧が表示され、各オプションが動作する。

---

## Phase 4: モデル管理

**目標:** `--list-models` / `--download-model` でモデルカタログ管理。

**依存:** Phase 1 完了

**状態:** 未着手

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

**状態:** 未着手

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

### 備考

Program.cs には既に `--language en` のルーティングが実装済み（EnglishPhonemizer をリフレクション解決）。EnglishPhonemizer クラスを作成すれば即座に動作する。

### リスク

| リスク | 対策 |
|--------|------|
| DotNetG2P.English vs g2p-en のOOV差異 | 主要テストケースでPython出力と差分計測 |

---

## Phase 6: CI/CD + 配布

**目標:** 6 RIDビルド・テスト・リリースの自動化。

**依存:** Phase 3 完了

**状態:** 未着手

### 作成ファイル

| ファイル | 説明 |
|---------|------|
| `.github/workflows/csharp-ci.yml` | ビルド+テスト (3 OS) |
| `.github/workflows/csharp-build-all-platforms.yml` | 6 RIDビルド |

### 実装タスク

- [ ] CI: ubuntu/windows/macOS の3 OSマトリクス、`dotnet test` 実行
- [ ] ビルド: 6 RID × Self-Contained。クロスコンパイル時は `PublishReadyToRun=false`
- [ ] アセット: `piper-plus-cli-{rid}.{zip|tar.gz}`
- [ ] NuGet: `<PackAsTool>true</PackAsTool>` 設定（Cli.csprojに設定済み）
- [ ] 既存 `dev-create-release.yml` にC# CLIジョブを統合

### 完了条件

PRトリガーで自動テスト通過、リリース時に6 RIDバイナリ生成。

---

## テストサマリー

| フェーズ | テストファイル | テスト数 | 状態 |
|---------|--------------|---------|------|
| Phase 1 | WavWriterTests.cs | 8 | 完了 |
| Phase 1 | PiperConfigTests.cs | 16 | 完了 |
| Phase 1 | InferenceTests.cs | 10 | 完了 |
| Phase 2 | PhonemeConverterTests.cs | 21 | 完了 |
| Phase 2 | PhonemeEncoderTests.cs | 9 | 完了 |
| Phase 2 | JapanesePhonemizerTests.cs | 8 | 完了 |
| **合計** | | **72** | |

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
