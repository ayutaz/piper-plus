# uPiper アーキテクチャ設計書

## 1. 全体アーキテクチャ

### 1.1 システム概要

uPiperは、Piper TTSエンジンをUnityで使用可能にするプラグインです。テキストから音声を生成する完全なパイプラインを提供します。

### 1.2 コンポーネント関係図

```
┌─────────────────────────────────────────────────────────────┐
│                        Unity Application                      │
├─────────────────────────────────────────────────────────────┤
│                          uPiper API                          │
│                    IPiperTTS (public interface)              │
├─────────────────────┬───────────────────────────────────────┤
│   Text Processing   │           Audio Generation             │
├─────────────────────┼───────────────────────────────────────┤
│    Phonemizer      │        Synthesis Engine                │
│  ┌─────────────┐   │    ┌──────────────────────┐          │
│  │BasePhonemizer│   │    │ InferenceAudioGenerator│         │
│  └──────┬──────┘   │    └──────────┬───────────┘          │
│         │          │                │                       │
│  ┌──────┴──────┐   │    ┌──────────┴───────────┐          │
│  │OpenJTalk    │   │    │Unity AI Interface    │          │
│  │Phonemizer   │   │    │(Inference Engine)    │          │
│  └──────┬──────┘   │    └──────────┬───────────┘          │
├─────────┴──────────┴────────────────┴───────────────────────┤
│                    Native Libraries                          │
│  ┌─────────────┐              ┌──────────────┐             │
│  │OpenJTalk    │              │ONNX Runtime  │             │
│  │(.dll/.so)   │              │(Unity内蔵)   │             │
│  └─────────────┘              └──────────────┘             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 データフロー

```
入力テキスト
    ↓
[テキスト正規化]
    ↓
[音素化処理] ← キャッシュ
    ↓
音素列 (例: "k o N n i ch i w a")
    ↓
[音素ID変換]
    ↓
音素IDテンソル [25, 11, 22, 50, 8, ...]
    ↓
[ONNX推論]
    ↓
音声波形データ (float[])
    ↓
[AudioClip生成]
    ↓
Unity AudioClip (再生可能)
```

### 1.4 主要インターフェース

#### IPiperTTS (メインAPI)
```csharp
public interface IPiperTTS
{
    // 同期API
    AudioClip GenerateAudio(string text);
    AudioClip GenerateAudio(string text, PiperVoiceConfig config);
    
    // 非同期API
    Task<AudioClip> GenerateAudioAsync(string text);
    Task<AudioClip> GenerateAudioAsync(string text, PiperVoiceConfig config);
    
    // ストリーミングAPI
    IAsyncEnumerable<AudioChunk> StreamAudioAsync(string text);
    
    // 設定
    PiperConfig Configuration { get; set; }
    bool IsInitialized { get; }
    
    // 初期化
    Task InitializeAsync();
    void Dispose();
}
```

#### IPhonemizer (音素化インターフェース)
```csharp
public interface IPhonemizer
{
    string Language { get; }
    Task<PhonemeResult> PhonemizeAsync(string text);
    bool CanPhonemize(string language);
}
```

#### IAudioGenerator (音声生成インターフェース)
```csharp
public interface IAudioGenerator
{
    Task<float[]> GenerateAudioAsync(int[] phonemeIds);
    AudioGeneratorConfig Configuration { get; set; }
    void LoadModel(string modelPath);
}
```

## 2. パッケージ構造設計

### 2.1 ディレクトリ構造

```
Assets/
└── uPiper/
    ├── package.json                 # Unity Package Manager定義
    ├── README.md                    # パッケージドキュメント
    ├── LICENSE                      # ライセンスファイル
    ├── CHANGELOG.md                 # 変更履歴
    │
    ├── Runtime/                     # ランタイムコード
    │   ├── uPiper.Runtime.asmdef   # アセンブリ定義
    │   ├── Core/                   # コアAPI
    │   │   ├── IPiperTTS.cs
    │   │   ├── PiperTTS.cs
    │   │   ├── PiperConfig.cs
    │   │   └── PiperException.cs
    │   │
    │   ├── Phonemizers/            # 音素化システム
    │   │   ├── IPhonemizer.cs
    │   │   ├── BasePhonemizer.cs
    │   │   ├── OpenJTalkPhonemizer.cs
    │   │   ├── PhonemeResult.cs
    │   │   └── PhonemeCache.cs
    │   │
    │   ├── Synthesis/              # 音声合成
    │   │   ├── IAudioGenerator.cs
    │   │   ├── InferenceAudioGenerator.cs
    │   │   ├── AudioGeneratorConfig.cs
    │   │   └── AudioClipBuilder.cs
    │   │
    │   ├── Models/                 # モデル管理
    │   │   ├── IModelLoader.cs
    │   │   ├── PiperModelLoader.cs
    │   │   ├── ModelInfo.cs
    │   │   └── VoiceConfig.cs
    │   │
    │   ├── Native/                 # ネイティブバインディング
    │   │   ├── OpenJTalkNative.cs
    │   │   ├── NativeLibraryLoader.cs
    │   │   └── PlatformHelper.cs
    │   │
    │   └── Utils/                  # ユーティリティ
    │       ├── Logger.cs
    │       ├── TextNormalizer.cs
    │       ├── LRUCache.cs
    │       └── AsyncHelper.cs
    │
    ├── Editor/                      # エディタ拡張
    │   ├── uPiper.Editor.asmdef
    │   ├── Inspector/
    │   │   ├── PiperTTSInspector.cs
    │   │   └── ModelImporter.cs
    │   └── Windows/
    │       └── PiperSettingsWindow.cs
    │
    ├── Plugins/                     # ネイティブライブラリ
    │   ├── Windows/
    │   │   └── x64/
    │   │       └── openjtalk.dll
    │   ├── Linux/
    │   │   └── x64/
    │   │       └── libopenjtalk.so
    │   ├── Android/
    │   │   ├── arm64-v8a/
    │   │   └── armeabi-v7a/
    │   ├── iOS/
    │   │   └── libopenjtalk.a
    │   └── WebGL/
    │       └── openjtalk.wasm
    │
    ├── Models/                      # TTSモデルファイル
    │   └── ja_JP/
    │       ├── ja_JP-test-medium.onnx
    │       └── ja_JP-test-medium.onnx.json
    │
    ├── Tests/                       # テスト
    │   ├── Runtime/
    │   │   ├── uPiper.Tests.asmdef
    │   │   └── (test files)
    │   └── Editor/
    │       ├── uPiper.EditorTests.asmdef
    │       └── (editor test files)
    │
    └── Samples~/                    # サンプル (Package Manager用)
        └── BasicTTS/
            ├── BasicTTSDemo.unity
            ├── Scripts/
            └── README.md
```

### 2.2 アセンブリ分割

```
uPiper.Runtime
├── 依存: Unity.InferenceEngine, Unity.Burst, Newtonsoft.Json
├── 定義: コアランタイム機能
└── プラットフォーム: すべて

uPiper.Editor
├── 依存: uPiper.Runtime, UnityEditor
├── 定義: エディタ拡張機能
└── プラットフォーム: エディタのみ

uPiper.Tests
├── 依存: uPiper.Runtime, Unity.TestFramework
├── 定義: ランタイムテスト
└── プラットフォーム: すべて

uPiper.EditorTests
├── 依存: uPiper.Editor, Unity.TestFramework
├── 定義: エディタテスト
└── プラットフォーム: エディタのみ
```

### 2.3 依存関係

```
外部依存:
- Unity.InferenceEngine (2.2.x)
- Unity.Burst (1.8.x)
- Newtonsoft.Json (3.2.x)

内部依存:
Core → Phonemizers, Synthesis, Models
Phonemizers → Native, Utils
Synthesis → Models, Utils
Native → Utils
```

### 2.4 Unity Package Manager準拠

package.json構造:
```json
{
  "name": "com.yousan.upiper",
  "version": "0.1.0",
  "displayName": "uPiper - Unity Piper TTS",
  "description": "Text-to-Speech plugin for Unity using Piper TTS engine",
  "unity": "2022.3",
  "dependencies": {
    "com.unity.ai.inference": "2.2.1",
    "com.unity.burst": "1.8.20",
    "com.unity.nuget.newtonsoft-json": "3.2.1"
  },
  "keywords": [
    "tts",
    "text-to-speech",
    "piper",
    "audio",
    "voice"
  ],
  "author": {
    "name": "ayutaz",
    "email": "ka1357amnbpdr@gmail.com",
    "url": "https://github.com/ayutaz"
  }
}
```

## 3. 設計原則

### 3.1 SOLID原則の適用
- **S**: 各クラスは単一の責任を持つ
- **O**: 拡張に対して開いており、修正に対して閉じている
- **L**: 派生クラスは基底クラスと置換可能
- **I**: インターフェースは分離されている
- **D**: 抽象に依存し、具象に依存しない

### 3.2 非同期優先
- すべての重い処理は非同期API提供
- Unity のメインスレッドをブロックしない
- キャンセレーショントークンのサポート

### 3.3 プラットフォーム抽象化
- プラットフォーム固有コードは抽象化レイヤーの背後に隠蔽
- 条件付きコンパイルの最小化
- ランタイムでのプラットフォーム検出

### 3.4 エラーハンドリング
- 明確な例外階層
- リカバリ可能なエラーと致命的エラーの区別
- 詳細なエラーメッセージとコンテキスト

## 4. パフォーマンス考慮事項

### 4.1 メモリ管理
- オブジェクトプーリングの活用
- 大きなバッファの再利用
- ガベージコレクション圧力の最小化

### 4.2 キャッシング戦略
- 音素化結果のLRUキャッシュ
- モデルのプリロード
- 頻繁に使用される音声のキャッシュ

### 4.3 並列処理
- バッチ処理のサポート
- Job Systemの活用（可能な場合）
- 非同期I/O操作

## 5. 拡張性

### 5.1 新しい音素化エンジンの追加
- IPhonemizer インターフェースの実装
- プラグイン形式でのロード

### 5.2 新しい音声モデルの追加
- モデル設定ファイルの標準化
- 自動モデル検証

### 5.3 カスタム後処理
- 音声エフェクトパイプライン
- ユーザー定義フィルター