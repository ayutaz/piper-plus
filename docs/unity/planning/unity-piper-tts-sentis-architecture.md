# Unity Piper TTS - Sentis 2.1.2 統合アーキテクチャ

## 概要

Unity Sentis 2.1.2を使用することで、Piper TTSの音声合成部分をUnity内で完全に実行できるようになります。これにより、クロスプラットフォーム対応が大幅に簡素化されます。

## アーキテクチャの変更点

### 従来のアーキテクチャ
```
テキスト → [OpenJTalk/espeak-ng (Native)] → 音素 → [ONNX Runtime (Native)] → 音声
```

### Sentis統合アーキテクチャ
```
テキスト → [OpenJTalk/espeak-ng (Native)] → 音素 → [Unity Sentis] → 音声
```

## 主要な利点

### 1. プラットフォーム移植性の向上
- ONNX Runtimeのプラットフォーム別ビルドが不要
- SentisがサポートするすべてのプラットフォームでONNXモデル実行可能
- WebGLでも高速な推論が可能（WebGPU対応）

### 2. バイナリサイズの削減
| コンポーネント | 従来 | Sentis統合 | 削減量 |
|--------------|------|-----------|--------|
| ONNX Runtime | 15-20MB | 0MB | 100% |
| 音素化エンジン | 30-40MB | 30-40MB | 0% |
| **合計** | 45-60MB | 30-40MB | 33% |

### 3. 統合の簡素化
- Unity内で完結する音声合成パイプライン
- C#からの直接的なモデル制御
- Unity Profilerでのパフォーマンス分析

## 実装アーキテクチャ

### レイヤー構成
```csharp
// 1. 音素化レイヤー（ネイティブ）
public interface IPhonemizer
{
    string[] Phonemize(string text, string language);
}

// 2. 音声合成レイヤー（Sentis）
public class SentisVoiceSynthesizer
{
    private Model runtimeModel;
    private IWorker worker;
    
    public async Task<AudioClip> SynthesizeAsync(string[] phonemes)
    {
        // Sentisでの推論実行
        using var input = new TensorFloat(ConvertPhonemesToTensor(phonemes));
        worker.Execute(input);
        
        var output = worker.PeekOutput() as TensorFloat;
        return ConvertTensorToAudioClip(output);
    }
}

// 3. 統合API
public class PiperTTS
{
    private IPhonemizer phonemizer;
    private SentisVoiceSynthesizer synthesizer;
    
    public async Task<AudioClip> GenerateSpeechAsync(string text, string language = "ja")
    {
        // Step 1: 音素化（ネイティブ）
        var phonemes = phonemizer.Phonemize(text, language);
        
        // Step 2: 音声合成（Sentis）
        return await synthesizer.SynthesizeAsync(phonemes);
    }
}
```

## プラットフォーム別実装計画

### Phase 1: Windows/Linux（音素化のみネイティブ）
- OpenJTalk/espeak-ngのDLL/SO
- Sentisで音声合成

### Phase 2: Android
- 音素化ライブラリのJNIラッパー
- Sentisは自動的に対応

### Phase 3: macOS
- 音素化ライブラリのdylib
- Sentisは自動的に対応

### Phase 4: iOS
- 音素化ライブラリの静的リンク
- Sentisは自動的に対応

### Phase 5: WebGL
- 音素化をWebAssemblyで実装
- SentisのWebGPU対応により高速実行

## Sentis 2.1.2 の要件と制限

### 要件
- Unity 6000.0以降（推奨）
- Sentis Package 2.1.2
- 対応ONNX opset: 15以下

### パフォーマンス特性
| プラットフォーム | 推論バックエンド | 相対速度 |
|-----------------|----------------|----------|
| Windows/Linux | CPU/GPU | 1.0x |
| macOS | Metal | 0.8-1.2x |
| Android | NNAPI | 0.6-1.0x |
| iOS | Core ML | 0.8-1.2x |
| WebGL | WebGPU/WASM | 0.3-0.6x |

## 開発優先順位の再評価

Sentis統合により、WebGLの実装難易度が大幅に下がります：

### 更新された優先順位提案
1. **Windows/Linux** - 変更なし（最優先）
2. **Android** - 変更なし（高優先）
3. **WebGL** - 優先度上昇（Sentisにより実装が簡単に）
4. **macOS** - 中優先度
5. **iOS** - 低優先度

理由：
- WebGLでのONNX Runtime移植が不要
- SentisのWebGPU対応により実用的な速度を実現
- ブラウザベースのデモが早期に可能

## 実装上の注意点

### 1. ONNXモデルの互換性
- Piper音声モデルのONNX opsetバージョン確認
- 必要に応じてモデルの再エクスポート

### 2. メモリ管理
```csharp
// Sentisのメモリ管理例
public void Dispose()
{
    worker?.Dispose();
    runtimeModel?.Dispose();
}
```

### 3. 音素フォーマットの統一
- OpenJTalk/espeak-ngの出力をSentis入力形式に変換
- 音素IDマッピングテーブルの管理

## 移行計画

### 既存実装からの移行
1. ONNX Runtimeコードの削除
2. Sentis APIへの置き換え
3. モデルロード方式の変更（Resources/StreamingAssets）

### テスト計画
- 音質比較テスト（ONNX Runtime vs Sentis）
- パフォーマンスベンチマーク
- メモリ使用量測定

## まとめ

Sentis 2.1.2の採用により：
- ✅ クロスプラットフォーム対応が簡素化
- ✅ バイナリサイズが約33%削減
- ✅ WebGL対応が現実的に
- ✅ Unity内での統合がシームレスに

音素化部分のみネイティブ実装が必要ですが、音声合成はSentisで統一できるため、開発効率と保守性が大幅に向上します。