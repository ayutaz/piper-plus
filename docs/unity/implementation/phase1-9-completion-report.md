# Phase 1.9 Unity.InferenceEngine統合 - 完了報告

完了日: 2025年1月19日

## 概要

Phase 1.9では、Unity.InferenceEngine（Unity 6の新しいAI推論パッケージ、旧Unity.Sentis）を使用してONNXモデルの推論機能を実装しました。これにより、Piperの音声合成モデルをUnity内で直接実行し、日本語テキストから音声を生成することが可能になりました。

## 実装内容

### 1. InferenceAudioGenerator実装

**ファイル**: `Assets/uPiper/Runtime/Core/AudioGeneration/InferenceAudioGenerator.cs`

Unity.InferenceEngineのWorker APIを使用したONNX推論の実装：

```csharp
// Piperモデルは3つの入力を必要とする
var inputTensor = new Tensor<int>(new TensorShape(1, phonemeIds.Length), phonemeIds);
var inputLengthsTensor = new Tensor<int>(new TensorShape(1), new[] { phonemeIds.Length });
var scalesTensor = new Tensor<float>(new TensorShape(3), new[] { noiseScale, lengthScale, noiseW });

// CPUバックエンドを使用（GPUはMetalエラーのため）
_worker = new Worker(_model, BackendType.CPU);
```

主な機能：
- ModelAssetの読み込みとWorkerの初期化
- 3つの必須入力テンソルの準備
- 推論実行とReadbackAndClone()による結果取得
- スレッドセーフな実装

### 2. PhonemeEncoder実装

**ファイル**: `Assets/uPiper/Runtime/Core/AudioGeneration/PhonemeEncoder.cs`

音素からモデル入力IDへの変換：

```csharp
// 多文字音素のPUAマッピング
private static readonly Dictionary<string, string> multiCharPhonemeMap = new Dictionary<string, string>
{
    ["ch"] = "\ue00e",  // "ち"の音
    ["ts"] = "\ue00f",  // "つ"の音
    ["sh"] = "\ue010",  // "し"の音
    // ... 他の多文字音素
};
```

特徴：
- PUA（Private Use Area）文字への自動マッピング
- Piperモデルとの完全互換性
- BOS/EOSトークンの適切な処理

### 3. デモシーン実装

**ファイル**: `Assets/uPiper/Runtime/Demo/InferenceEngineDemo.cs`

実動作するデモの実装：

```csharp
// 簡易的な日本語音素変換
var phonemeMap = new Dictionary<string, string[]>
{
    { "こ", new[] { "k", "o" } },
    { "ん", new[] { "N" } },
    { "に", new[] { "n", "i" } },
    { "ち", new[] { "ch", "i" } },  // "ch"はPUAに変換される
    { "は", new[] { "w", "a" } },    // 助詞の"は"は"wa"
};
```

機能：
- 日本語テキスト入力
- モデル選択（ja_JP-test-medium/test_voice）
- 音声の生成と再生
- TextMeshProとInput System対応

### 4. サポートクラス

#### AudioClipBuilder
音声データからAudioClipへの変換と正規化：
- float配列からAudioClipの作成
- 音声データの正規化（-1.0〜1.0）
- ステレオ/モノラル対応

#### UnityMainThreadDispatcher
Unity APIのメインスレッド実行：
- async/awaitパターンのサポート
- CancellationToken対応
- エディタとランタイムの両対応

#### PlatformHelper
プラットフォーム依存処理：
- ライブラリ拡張子の自動選択（.dll/.so/.dylib）
- WebGL非対応の適切な処理

### 5. テスト実装

- `InferenceAudioGeneratorTests.cs` - 初期化とエラーハンドリングのテスト
- `PhonemeEncoderTests.cs` - エンコーディングとPUAマッピングのテスト
- `AudioClipBuilderTests.cs` - 音声データ変換のテスト

## 動作確認結果

### 成功事項

1. **音声生成の成功**
   - 「こんにちは」の音声生成と再生が成功
   - モデルの読み込みと推論が正常動作
   - 音声データの適切な正規化/増幅

2. **Unity統合**
   - Unity.InferenceEngineのWorker APIの正常動作
   - メインスレッド実行の適切な処理
   - デモシーンでの安定動作

3. **コード品質**
   - dotnet formatによるスタイル統一
   - 不要なTODOコメントの削除
   - 適切なエラーハンドリング

### 既知の問題

1. **日本語発音の精度**
   - 「ち」が「ちゅ」のように聞こえる
   - 原因：簡易的な音素変換（OpenJTalk未使用）
   - 解決：Phase 1.10でOpenJTalk統合予定

2. **GPU推論の制限**
   - MetalバックエンドでShaderエラー発生
   - 現在はCPUバックエンドを使用
   - 将来的にGPU対応を検討

3. **WebGL非対応**
   - Unity.InferenceEngineの制限
   - 代替手段の検討が必要

## 技術的詳細

### モデル入力形式

Piperモデルは以下の3つの入力を必要とします：

1. **input** (int32[1, sequence_length])
   - 音素IDの配列
   - PUA文字にマッピングされた多文字音素を含む

2. **input_lengths** (int32[1])
   - 入力シーケンスの長さ

3. **scales** (float32[3])
   - [noise_scale, length_scale, noise_w]
   - デフォルト: [0.667, 1.0, 0.8]

### 音声データ処理

1. **推論結果の取得**
   ```csharp
   var outputTensor = _worker.PeekOutput(outputName) as Tensor<float>;
   var readableTensor = outputTensor.ReadbackAndClone();
   ```

2. **音声データの増幅**
   ```csharp
   if (maxVal < 0.1f) {
       float amplificationFactor = 0.5f / maxVal;
       processedAudio = audioData.Select(x => x * amplificationFactor).ToArray();
   }
   ```

## PR情報

- **PR #24**: Phase 1.9 - Unity.InferenceEngine（旧Sentis）統合によるONNXモデル推論の実装
- **マージ日**: 2025年1月19日

## 次のステップ

### Phase 1.10: OpenJTalk統合
- OpenJTalkPhonemizerとの連携
- 正確な日本語音素変換
- アクセント情報の活用

### Phase 1.11: 統合とサンプル
- エンドツーエンドの動作確認
- パフォーマンス最適化
- ユーザー向けサンプルの作成