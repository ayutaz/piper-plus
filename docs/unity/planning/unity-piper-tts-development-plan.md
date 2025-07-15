# Unity Piper TTS Plugin 詳細開発計画書

## 目次
1. [プロジェクト概要](#1-プロジェクト概要)
2. [プロジェクト構造](#2-プロジェクト構造)
3. [開発フェーズと詳細タスク](#3-開発フェーズと詳細タスク)
4. [テスト戦略（TDDベース）](#4-テスト戦略tddベース)
5. [CI/CDパイプライン](#5-cicdパイプライン)
6. [パッケージ配布戦略](#6-パッケージ配布戦略)
7. [品質保証](#7-品質保証)
8. [開発スケジュール](#8-開発スケジュール)

---

## 1. プロジェクト概要

### 1.1 プロジェクト名
**Unity Piper TTS** - Cross-platform Text-to-Speech Unity Plugin

### 1.2 バージョニング戦略
- セマンティックバージョニング（SemVer）準拠
- 初期リリース: v0.1.0（アルファ版）
- 安定版: v1.0.0

### 1.3 ライセンス
- Apache License 2.0（Piper本体と同じ）
- サードパーティライセンス管理の徹底

### 1.4 サポートプラットフォーム（優先順位順）
| プラットフォーム | Unity最小バージョン | アーキテクチャ | 優先度 | 実装フェーズ |
|-----------------|-------------------|--------------|--------|------------|
| Windows | 6000.0.35f1 | x64 | ★★★★★ | Phase 1 |
| Linux | 6000.0.35f1 | x64 | ★★★★★ | Phase 1 |
| Android | 6000.0.35f1 | arm64-v8a, armeabi-v7a | ★★★★☆ | Phase 2 |
| WebGL | 6000.0.35f1 | WASM | ★★★☆☆ | Phase 3 |
| macOS | 6000.0.35f1 | x64, Apple Silicon | ★★☆☆☆ | Phase 4 |
| iOS | 6000.0.35f1 | arm64 | ★☆☆☆☆ | Phase 5 |

### 1.5 Unity 6 新機能の活用
- **C# 11**: 最新言語機能（required members、file-scoped types等）
- **Burst Compiler 1.8+**: より高速なネイティブコード生成
- **Unity Sentis 2.1.2**: ONNXモデルによる音声合成（ONNX Runtime不要）
- **WebGPU対応**: WebGL版でのSentis高速実行

---

## 2. プロジェクト構造

### 2.1 リポジトリ構造
```
unity-piper-tts/
├── .github/
│   ├── workflows/
│   │   ├── ci.yml              # メインCI/CDワークフロー
│   │   ├── release.yml         # リリースワークフロー
│   │   └── nightly.yml         # ナイトリービルド
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md
├── Assets/
│   └── PiperTTS/
│       ├── package.json        # Unity Package Manager定義
│       ├── Runtime/
│       │   ├── Scripts/
│       │   │   ├── Core/       # コアAPI
│       │   │   ├── Phonemizers/ # 音素化エンジン
│       │   │   └── Platform/   # プラットフォーム別実装
│       │   └── Plugins/        # ネイティブライブラリ
│       ├── Editor/
│       │   ├── Scripts/
│       │   └── BuildTools/
│       ├── Tests/
│       │   ├── Runtime/        # PlayModeテスト
│       │   └── Editor/         # EditModeテスト
│       ├── Samples~/           # サンプルプロジェクト
│       └── Documentation~/     # ドキュメント
├── NativeSources/              # ネイティブコードソース
│   ├── openjtalk-wrapper/
│   ├── espeak-wrapper/
│   └── build-scripts/
├── Tools/
│   ├── build.sh               # ビルドスクリプト
│   ├── test-runner.sh         # テスト実行スクリプト
│   └── package-validator/     # パッケージ検証ツール
├── Tests/
│   ├── Integration/           # 統合テスト
│   └── Performance/           # パフォーマンステスト
├── Docs/
│   ├── API/                   # APIドキュメント
│   ├── GettingStarted.md
│   └── Contributing.md
├── CHANGELOG.md
├── LICENSE
└── README.md
```

### 2.2 Unity Package構造
```
com.piper.tts/
├── package.json
├── Runtime/
│   ├── com.piper.tts.asmdef
│   ├── Core/
│   │   ├── IPiperTTS.cs          # 主要インターフェース
│   │   ├── PiperTTS.cs           # メイン実装
│   │   ├── PiperConfig.cs        # 設定クラス
│   │   └── AudioFormat.cs        # オーディオフォーマット定義
│   ├── Phonemizers/
│   │   ├── IPhonemizer.cs        # 音素化インターフェース
│   │   ├── OpenJTalkPhonemizer.cs
│   │   ├── EspeakPhonemizer.cs
│   │   └── PhonemizerFactory.cs
│   ├── Platform/
│   │   ├── PlatformBase.cs
│   │   ├── WindowsPlatform.cs
│   │   ├── AndroidPlatform.cs
│   │   ├── WebGLPlatform.cs
│   │   └── IOSPlatform.cs
│   └── Utilities/
│       ├── AudioClipHelper.cs
│       ├── ThreadingHelper.cs
│       └── CacheManager.cs
├── Editor/
│   ├── com.piper.tts.editor.asmdef
│   ├── PiperSettingsProvider.cs
│   ├── BuildPreprocessor.cs
│   └── MenuItems.cs
├── Tests/
│   ├── Runtime/
│   │   ├── com.piper.tts.tests.asmdef
│   │   └── PiperTTSTests.cs
│   └── Editor/
│       └── PiperEditorTests.cs
├── Models/             # ONNXモデルファイル
│   └── Resources/      # Sentis用モデル
└── Plugins/
    ├── Windows/        # 音素化ライブラリのみ
    ├── Android/        # 音素化ライブラリのみ
    ├── iOS/           # 音素化ライブラリのみ
    └── WebGL/         # 音素化ライブラリのみ
```

---

## 3. 開発フェーズと詳細タスク（プラットフォーム優先順位対応版）

### Phase 0: Unity 6対応確認とプロトタイプ（1週間）

#### 0.1 Unity 6環境確認
- [ ] Unity 6000.0.35f1でのネイティブプラグイン動作テスト
- [ ] C# 11機能の利用可能性確認
- [ ] Sentis 2.1.2パッケージのインストールと動作確認
- [ ] PiperのONNXモデルとSentisの互換性確認

#### 0.2 既存Piper実装の評価
- [ ] 音素化専用ビルド（hts_engine_stub）の動作確認
- [ ] openjtalk_optimized キャッシュ機能の評価
- [ ] Unity向けビルドスクリプトの作成

#### 0.3 最小プロトタイプ作成
- [ ] Windows向け音素化DLLビルド（OpenJTalkのみ）
- [ ] Unity P/Invoke基本実装（音素化API）
- [ ] Sentisでの音声合成実装
- [ ] 日本語テキスト→音声の完全パイプライン動作確認
- [ ] パフォーマンス初期測定（音素化 vs Sentis推論）

### Phase 1: Windows/Linux基盤構築（2週間）

#### 1.1 プロジェクトセットアップ
- [ ] GitHubリポジトリ作成（uPiperフォーク）
- [ ] Unity Package構造セットアップ（uPiper/Assets/PiperTTS）
- [ ] .gitignore, .gitattributes設定
- [ ] EditorConfig設定
- [ ] 基本的なREADME作成

#### 1.2 開発環境構築
- [ ] Unity Test Framework統合
- [ ] コードフォーマッター設定（Unity Code Analysis）
- [ ] Windows/Linuxビルド環境構築
- [ ] CMakeビルドシステムセットアップ

#### 1.3 Windows/Linux 音素化実装
- [ ] OpenJTalk音素化専用ラッパー作成
- [ ] Windows DLL（x64）ビルド - 音素化のみ
- [ ] Linux SO（x64）ビルド - 音素化のみ
- [ ] Unity P/Invokeバインディング実装
- [ ] Sentis音声合成モジュール実装
- [ ] Windows/Linux統合テスト

#### 1.4 コアAPI設計（TDD）
```csharp
// Windows/Linux向けテストファースト実装（Unity 6 / C# 11 + Sentis）
[Test]
[Platform(Include = "Win, Linux")]
public async Task GenerateSpeech_OnDesktop_ReturnsValidAudioClip()
{
    // Arrange
    var tts = new PiperTTS();
    var config = new PiperConfig 
    { 
        Language = "ja",
        UseCache = true,  // 既存のキャッシュ機能を活用
        ModelPath = "Models/japanese_voice_v1.onnx",  // Sentis用ONNXモデル
        SentisBackend = BackendType.GPUCompute  // Sentis実行バックエンド
    };
    await tts.InitializeAsync(config);
    
    // Act
    var audioClip = await tts.GenerateSpeechAsync("こんにちは");
    
    // Assert
    Assert.NotNull(audioClip);
    Assert.Greater(audioClip.length, 0);
    Assert.AreEqual(22050, audioClip.frequency);
}
```

### Phase 2: Android実装（3週間）

#### 2.1 Android NDK環境構築
- [ ] Android NDKセットアップ
- [ ] クロスコンパイル環境構築
- [ ] arm64-v8a/armeabi-v7a対応

#### 2.2 OpenJTalk Android統合
- [ ] OpenJTalk Android Portの統合
- [ ] JNIラッパー実装
- [ ] Android固有のファイルI/O処理
- [ ] StreamingAssetsからの辞書読み込み

#### 2.3 Android向けビルド最適化
- [ ] APKサイズ最適化
- [ ] 辞書ファイル圧縮
- [ ] メモリ使用量最適化
- [ ] 実機パフォーマンステスト

#### 2.4 Android統合とテスト
- [ ] Unity Androidプロジェクト設定
- [ ] AAR/SOライブラリ統合
- [ ] 実機デバイステスト（複数機種）
- [ ] Google Play要件準拠確認

### Phase 3: WebGL実装（2週間）

#### 3.1 Emscripten環境構築
- [ ] Emscripten SDKセットアップ
- [ ] WebAssemblyビルド設定
- [ ] Unity WebGL統合準備

#### 3.2 WebGL向け音素化実装
- [ ] OpenJTalkのWASMビルド
- [ ] JavaScriptブリッジ実装
- [ ] 辞書ファイルの効率的ロード
- [ ] Web Worker統合（バックグラウンド処理）

#### 3.3 Sentis WebGL統合
- [ ] WebGPUバックエンド設定
- [ ] メモリプール最適化
- [ ] ブラウザ互換性対応（Chrome, Firefox, Edge）
- [ ] パフォーマンステスト

#### 3.4 WebGL最適化
- [ ] ダウンロードサイズ最適化（gzip圧縮）
- [ ] 初期化時間短縮（遅延ロード）
- [ ] メモリ使用量削減（2GB制限対応）
- [ ] PWA対応（オフライン動作）

### Phase 4: macOS実装（2週間）

#### 4.1 macOS開発環境
- [ ] Xcode環境セットアップ
- [ ] Universal Binary対応（Intel/Apple Silicon）
- [ ] macOS固有のセキュリティ設定

#### 4.2 macOSネイティブ実装
- [ ] macOS用dylibビルド（音素化のみ）
- [ ] Gatekeeperコード署名
- [ ] App Sandboxing対応
- [ ] macOS統合テスト

### Phase 5: iOS実装（2週間）

#### 5.1 iOS開発環境
- [ ] iOS SDK環境構築
- [ ] Bitcodeサポート検討
- [ ] App Store要件確認

#### 5.2 iOS向け最適化実装
- [ ] SharpOpenJTalkの統合
- [ ] iOS用静的ライブラリビルド
- [ ] メモリ制限への対応
- [ ] バックグラウンド制限対応

#### 5.3 iOS統合とテスト
- [ ] Unity iOS設定
- [ ] 実機テスト（iPhone/iPad）
- [ ] App Store審査準備

### Phase 6: 多言語対応と統合（2週間）

#### 6.1 espeak-ng統合
- [ ] 全プラットフォーム向けespeak-ngビルド
- [ ] 言語自動検出
- [ ] フォールバック機構

#### 6.2 統一インターフェース
- [ ] プラットフォーム抽象化層の完成
- [ ] 言語切り替えAPI
- [ ] パフォーマンス最適化

### Phase 7: 品質保証とリリース（1週間）

#### 7.1 最終テストと品質保証
- [ ] 全プラットフォーム統合テスト
- [ ] パフォーマンスベンチマーク
- [ ] メモリリークチェック
- [ ] セキュリティ監査

#### 7.2 ドキュメントとリリース
- [ ] APIドキュメント完成
- [ ] サンプルプロジェクト作成
- [ ] リリースノート作成
- [ ] 配布パッケージ準備

---

## 4. テスト戦略（TDDベース）

### 4.1 テストピラミッド
```
         /\
        /  \  E2Eテスト（5%）
       /    \ - 実際のUnityプロジェクトでの動作確認
      /------\ 
     /        \ 統合テスト（15%）
    /          \ - プラットフォーム別動作確認
   /            \ - 多言語切り替えテスト
  /--------------\
 /                \ ユニットテスト（80%）
/                  \ - 各クラス・メソッドの単体テスト
                     - モック・スタブを活用した高速テスト
```

### 4.2 TDDサイクル
1. **Red**: 失敗するテストを書く
2. **Green**: テストが通る最小限の実装
3. **Refactor**: コードの改善

### 4.3 テストカテゴリ

#### ユニットテスト
```csharp
[TestFixture]
public class PhonemizeTests
{
    private IPhonemizer _phonemizer;
    
    [SetUp]
    public void Setup()
    {
        _phonemizer = new MockPhonemizer();
    }
    
    [Test]
    public void Phonemize_EmptyString_ReturnsEmptyArray()
    {
        // Arrange
        var input = "";
        
        // Act
        var result = _phonemizer.Phonemize(input);
        
        // Assert
        Assert.IsEmpty(result);
    }
    
    [TestCase("hello", new[] {"h", "e", "l", "o"})]
    [TestCase("world", new[] {"w", "o", "r", "l", "d"})]
    public void Phonemize_ValidInput_ReturnsExpectedPhonemes(
        string input, string[] expected)
    {
        // Act
        var result = _phonemizer.Phonemize(input);
        
        // Assert
        Assert.AreEqual(expected, result);
    }
}
```

#### 統合テスト
```csharp
[TestFixture]
public class PlatformIntegrationTests
{
    [Test]
    [Platform(Include = "Android")]
    public async Task AndroidPlatform_GenerateSpeech_WorksOnDevice()
    {
        // デバイス上での実際の動作確認
    }
    
    [Test]
    [Platform(Include = "WebGL")]
    public async Task WebGLPlatform_LoadsInBrowser()
    {
        // ブラウザでの動作確認
    }
}
```

### 4.4 テストツール
- **Unity Test Framework**: Unity標準のテストフレームワーク
- **NUnit**: アサーションライブラリ
- **NSubstitute**: モッキングフレームワーク
- **BenchmarkDotNet**: パフォーマンステスト

---

## 5. CI/CDパイプライン

### 5.1 GitHub Actions ワークフロー

#### メインCIワークフロー（.github/workflows/ci.yml）
```yaml
name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    name: Test Unity Package
    runs-on: ubuntu-latest
    strategy:
      matrix:
        unityVersion:
          - 6000.0.35f1
          - 2023.3.0f1  # LTS fallback
          - 2022.3.15f1  # Previous LTS
    
    steps:
    - uses: actions/checkout@v3
      with:
        lfs: true
    
    - uses: game-ci/unity-test-runner@v3
      with:
        unityVersion: ${{ matrix.unityVersion }}
        testMode: all
        artifactsPath: test-artifacts
        githubToken: ${{ secrets.GITHUB_TOKEN }}
        checkName: Test Results ${{ matrix.unityVersion }}
        coverageOptions: 'generateAdditionalMetrics;generateHtmlReport;generateBadgeReport'
    
    - uses: actions/upload-artifact@v3
      if: always()
      with:
        name: Test results for ${{ matrix.unityVersion }}
        path: test-artifacts

  build-native:
    name: Build Native Libraries
    strategy:
      matrix:
        include:
          - os: windows-latest
            platform: Windows
          - os: ubuntu-latest
            platform: Linux
          - os: ubuntu-latest
            platform: Android
          - os: macos-latest
            platform: macOS
          - os: macos-latest
            platform: iOS
    
    runs-on: ${{ matrix.os }}
    
    steps:
    - uses: actions/checkout@v3
      with:
        submodules: recursive
    
    - name: Setup build environment
      run: |
        ./Tools/setup-build-env.sh ${{ matrix.platform }}
    
    - name: Build native libraries
      run: |
        ./Tools/build-native.sh ${{ matrix.platform }}
    
    - uses: actions/upload-artifact@v3
      with:
        name: native-${{ matrix.platform }}
        path: build/output/

  validate-package:
    name: Validate Unity Package
    runs-on: ubuntu-latest
    needs: [test, build-native]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Download artifacts
      uses: actions/download-artifact@v3
    
    - name: Validate package structure
      run: |
        npm install -g unity-package-validator
        unity-package-validator ./Assets/PiperTTS
    
    - name: Check package dependencies
      run: |
        ./Tools/check-dependencies.sh
    
    - name: Validate samples
      run: |
        ./Tools/validate-samples.sh
```

#### リリースワークフロー（.github/workflows/release.yml）
```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  create-release:
    name: Create Release
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Build Release Package
      run: |
        ./Tools/build-release.sh ${{ github.ref_name }}
    
    - name: Create Unity Package
      run: |
        ./Tools/create-unitypackage.sh
    
    - name: Generate Release Notes
      run: |
        ./Tools/generate-release-notes.sh > RELEASE_NOTES.md
    
    - name: Create GitHub Release
      uses: softprops/action-gh-release@v1
      with:
        files: |
          *.unitypackage
          package.tgz
        body_path: RELEASE_NOTES.md
        draft: false
        prerelease: ${{ contains(github.ref, '-beta') || contains(github.ref, '-alpha') }}

  publish-openupm:
    name: Publish to OpenUPM
    needs: create-release
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Publish to OpenUPM
      env:
        NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
      run: |
        npm config set @piper:registry https://package.openupm.com
        npm config set //package.openupm.com/:_authToken $NODE_AUTH_TOKEN
        npm publish ./Assets/PiperTTS
```

### 5.2 品質ゲート
- コードカバレッジ: 80%以上
- すべてのテストがパス
- 静的解析エラーなし
- ドキュメント更新確認
- CHANGELOGエントリ確認

---

## 6. パッケージ配布戦略

### 6.1 配布チャネル

#### OpenUPM
```json
{
  "name": "com.piper.tts",
  "displayName": "Piper TTS",
  "version": "1.0.0",
  "unity": "2020.3",
  "description": "Cross-platform Text-to-Speech Unity plugin powered by Piper",
  "keywords": [
    "tts",
    "text-to-speech",
    "audio",
    "voice",
    "japanese",
    "multilingual"
  ],
  "author": {
    "name": "Piper TTS Contributors",
    "email": "support@piper-tts.dev",
    "url": "https://github.com/your-org/unity-piper-tts"
  },
  "dependencies": {
    "com.unity.nuget.newtonsoft-json": "3.0.2",
    "com.unity.sentis": "2.1.2",
    "com.unity.burst": "1.8.12",
    "com.unity.collections": "2.4.0"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/your-org/unity-piper-tts.git"
  },
  "publishConfig": {
    "registry": "https://package.openupm.com"
  }
}
```

#### Unity Package Manager（Git URL）
```
https://github.com/your-org/unity-piper-tts.git#upm
```

#### Unity Asset Store
- 後日申請（v1.0.0以降）
- 有料/無料の検討

### 6.2 バージョン管理
- **開発版**: 0.x.x
- **ベータ版**: 1.0.0-beta.x
- **安定版**: 1.x.x
- **LTS版**: 毎年1回指定

---

## 7. 品質保証

### 7.1 コード品質基準
- **命名規則**: C# Coding Conventions準拠
- **コメント**: XMLドキュメントコメント必須
- **複雑度**: サイクロマティック複雑度 < 10
- **重複**: コード重複率 < 5%

### 7.2 パフォーマンス基準
| メトリクス | 目標値 |
|-----------|--------|
| 初期化時間 | < 100ms |
| 音素化処理 | < 10ms/文 |
| 音声生成 | < 50ms/秒 |
| メモリ使用量 | < 100MB |
| GCアロケーション | < 1KB/生成 |

### 7.3 セキュリティ
- 依存関係の脆弱性スキャン（Dependabot）
- コード署名（リリースビルド）
- サンドボックス環境でのテスト

---

## 8. 開発スケジュール

### マイルストーン（プラットフォーム優先順位対応）
| フェーズ | 期間 | 成果物 | リリースバージョン |
|---------|------|--------|------------------|
| Phase 0 | 1週間 | Unity 6対応プロトタイプ | - |
| Phase 1 | 2週間 | Windows/Linux版 + 基本API | v0.1.0-alpha |
| Phase 2 | 3週間 | Android版統合 | v0.3.0-beta |
| Phase 3 | 2週間 | WebGL版追加 | v0.5.0-beta |
| Phase 4 | 2週間 | macOS版追加 | v0.7.0-beta |
| Phase 5 | 2週間 | iOS版追加 | v0.9.0-rc |
| Phase 6 | 2週間 | 多言語対応完成 | v1.0.0-rc2 |
| Phase 7 | 1週間 | 品質保証とリリース | v1.0.0 |
| **合計** | **15週間** | **全プラットフォーム対応版** | **v1.0.0** |

### 段階的リリース計画
1. **v0.1.0-alpha** (3週間後)
   - Unity 6完全対応
   - Windows/Linux対応
   - 基本的な日本語TTS機能（音素化専用モード対応）
   - Unity Package Manager対応

2. **v0.3.0-beta** (6週間後)
   - Android対応追加
   - モバイル最適化
   - 主要プラットフォーム（PC+Android）で使用可能

3. **v0.5.0-beta** (8週間後)
   - WebGL対応追加
   - ブラウザベースのデモ公開
   - Sentis WebGPU対応

4. **v0.7.0-beta** (10週間後)
   - macOS対応追加
   - Universal Binary対応
   - デスクトップ全プラットフォーム対応完了

5. **v0.9.0-rc** (12週間後)
   - iOS対応追加
   - 全プラットフォーム基本対応完了

6. **v1.0.0** (15週間後)
   - 多言語対応（50言語以上）
   - 全機能実装完了
   - プロダクション対応

### 早期アクセスプログラム
- Phase 1完了時点で早期アクセス開始
- Windows/Linuxユーザー向けにフィードバック収集
- Phase 2でAndroidユーザーも参加可能
- Phase 3でWebGLデモ公開（最も幅広いユーザーにリーチ）

### 長期ロードマップ
- **Q1 2025**: v1.0.0リリース、初期フィードバック対応
- **Q2 2025**: パフォーマンス最適化、追加言語サポート
- **Q3 2025**: Unity 2023 LTS対応、エンタープライズ機能
- **Q4 2025**: カスタムボイスモデル対応、クラウド統合オプション

---

## 付録A: 開発環境セットアップ

### 必要なツール
```bash
# Unity Hub
# Unity 6000.0.35f1
# Visual Studio 2022 or Rider（C# 11対応）
# Git LFS
# Docker Desktop
# Android Studio (Android開発用)
# Xcode 15+ (iOS開発用)
# CMake 3.20+
# Ninja Build

# セットアップスクリプト
./Tools/setup-dev-env.sh
```

### 開発開始手順
```bash
# リポジトリクローン
git clone --recursive https://github.com/your-org/unity-piper-tts.git
cd unity-piper-tts

# LFSファイル取得
git lfs pull

# 開発環境セットアップ
./Tools/setup-dev-env.sh

# Unityプロジェクトを開く
# Unity Hubから開くか、以下のコマンド
./Tools/open-in-unity.sh

# テスト実行
./Tools/run-tests.sh

# ローカルビルド
./Tools/build-local.sh
```

---

## 付録B: トラブルシューティング

### よくある問題
1. **ネイティブライブラリが見つからない**
   - プラットフォーム設定確認
   - Pluginsフォルダ構造確認

2. **日本語が文字化けする**
   - UTF-8エンコーディング確認
   - 辞書ファイルパス確認

3. **WebGLビルドエラー**
   - Emscriptenバージョン確認
   - メモリ設定調整

---

この開発計画書は生きたドキュメントとして、プロジェクトの進行に応じて更新されます。