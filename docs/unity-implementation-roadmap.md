# Unity Piper TTS 実装ロードマップ

## 概要

このドキュメントは、Piper TTS の Unity プラグイン実装における詳細なタスクリスト、マイルストーン、テスト計画、CI/CD 要件を定義します。計画書（`planning.md`、`architecture.md`、`unity-piper-planning.md`）に基づいて作成されています。

## 実装フェーズとスケジュール

全体スケジュール: 15週間（約3.5ヶ月）

### フェーズ 0: Unity 6 & Sentis 検証（第1週）

#### マイルストーン
- Unity 6000.0.35f1 と Unity Sentis 2.1.2 の互換性確認
- 最小限の動作プロトタイプ作成

#### タスク

##### 1. 環境セットアップと互換性テスト
- **ゴール**: Unity 6 と Sentis が正常に動作することを確認
- **成果物**: 
  - Unity 6 プロジェクトセットアップ
  - Sentis パッケージインストール確認
  - 基本的な ONNX モデル読み込みテスト
- **動作確認方法**:
  - Sentis で簡単な ONNX モデルを読み込み
  - テンソル操作の基本動作確認
  - GPU/CPU バックエンドの切り替えテスト
- **CI/CD テスト**:
  - Unity 6 対応 Docker イメージの準備
  - 基本的なビルドパイプラインの構築

##### 2. 最小プロトタイプ実装
- **ゴール**: 固定音素列から音声生成する最小実装
- **成果物**:
  - ハードコードされた音素 ID から AudioClip 生成
  - Unity エディタ上での音声再生確認
- **動作確認方法**:
  - エディタ上で Play ボタンを押して音声再生
  - 生成された AudioClip の波形確認
- **CI/CD テスト**:
  - Unity Test Framework の基本設定
  - エディタモードテストの実行

### フェーズ 1: Windows/Linux 基盤実装（第2-3週）✅ 現在のPR範囲

#### マイルストーン
- TDD による Core API 設計と実装
- ネイティブ音素化ライブラリの統合
- Sentis を使用した音声合成の実装

#### タスク

##### 1. Core API 設計（TDD アプローチ）
- **ゴール**: IPiperTTS、PiperConfig、PiperTTS の実装
- **成果物**:
  ```csharp
  public interface IPiperTTS : IDisposable
  {
      Task InitializeAsync(PiperConfig config);
      Task<AudioClip> GenerateSpeechAsync(string text, string language = "ja");
      bool IsInitialized { get; }
      PiperConfig CurrentConfig { get; }
  }
  ```
- **動作確認方法**:
  - 単体テストで全メソッドの動作確認
  - 非同期初期化の正常動作
  - エラーハンドリングの確認
- **CI/CD テスト**:
  - Unity Test Runner による自動テスト
  - コードカバレッジ 80% 以上
  - PR ごとの自動実行

##### 2. 音素化インターフェース実装
- **ゴール**: IPhonemizer、BasePhonemizer の実装
- **成果物**:
  - 音素化インターフェース定義
  - LRU キャッシュ機能
  - テキスト正規化機能
  - MockPhonemizer（テスト用）
- **動作確認方法**:
  - キャッシュヒット率の測定
  - 正規化機能のテスト（空白、改行処理）
  - 異なる言語での動作確認
- **CI/CD テスト**:
  - 単体テストの自動実行
  - パフォーマンステスト（キャッシュ効果測定）

##### 3. OpenJTalk 音素化ライブラリ実装
- **ゴール**: 音素化専用の軽量ネイティブライブラリ
- **成果物**:
  - Windows: `openjtalk_phonemizer.dll`
  - Linux: `libopenjtalk_phonemizer.so`
  - P/Invoke バインディング
- **動作確認方法**:
  ```csharp
  var phonemizer = new OpenJTalkPhonemizer();
  var phonemes = phonemizer.Phonemize("こんにちは", "ja");
  // 期待値: ["k", "o", "N", "n", "i", "ch", "i", "w", "a"]
  ```
- **CI/CD テスト**:
  - Windows/Linux でのネイティブビルド
  - DLL/SO の依存関係チェック
  - 日本語テキストの音素化テスト

##### 4. Sentis 音声合成実装
- **ゴール**: ONNX モデルから AudioClip 生成
- **成果物**:
  - SentisAudioGenerator クラス
  - 音素 ID マッピング機能
  - AudioClip 生成機能
- **動作確認方法**:
  - 音素 ID 配列から音声波形生成
  - 異なるバックエンド（GPU/CPU）での動作
  - 生成音声の品質確認
- **CI/CD テスト**:
  - モデル読み込みテスト
  - 推論実行時間の測定
  - メモリ使用量の監視

##### 5. プラットフォーム抽象化レイヤー
- **ゴール**: クロスプラットフォーム対応の基盤
- **成果物**:
  - PlatformHelper クラス
  - ネイティブライブラリローダー
  - プラットフォーム固有の設定管理
- **動作確認方法**:
  - Windows/Linux でのライブラリ読み込み
  - プラットフォーム検出の正確性
  - パス解決の動作確認
- **CI/CD テスト**:
  - マルチプラットフォームビルド
  - ライブラリ読み込みテスト

### フェーズ 2: Android 実装（第4-6週）

#### マイルストーン
- Android NDK によるネイティブビルド
- JNI を使用した Unity 統合
- モバイル向け最適化

#### タスク

##### 1. Android NDK ビルド環境構築
- **ゴール**: arm64-v8a、armeabi-v7a 向けビルド
- **成果物**:
  - Android.mk / CMakeLists.txt
  - `libopenjtalk_phonemizer.so`（各アーキテクチャ）
- **動作確認方法**:
  - NDK r21 でのビルド成功
  - 各アーキテクチャでのライブラリサイズ確認
- **CI/CD テスト**:
  - GitHub Actions での Android ビルド
  - AAR パッケージング

##### 2. JNI ラッパー実装
- **ゴール**: Unity から Android ネイティブコード呼び出し
- **成果物**:
  ```java
  public class OpenJTalkPhonemizer {
      static { System.loadLibrary("openjtalk_phonemizer"); }
      public native String[] phonemize(String text, String language);
  }
  ```
- **動作確認方法**:
  - Unity から JNI 経由での呼び出し
  - 日本語音素化の動作確認
- **CI/CD テスト**:
  - Android エミュレータでの自動テスト
  - 実機テスト（可能であれば）

##### 3. モバイル最適化
- **ゴール**: APK サイズとパフォーマンスの最適化
- **成果物**:
  - 最適化された辞書ファイル（圧縮版）
  - バックグラウンド処理対応
  - メモリ使用量の削減
- **動作確認方法**:
  - APK サイズの測定（目標: +10MB 以内）
  - 音素化処理時間の測定
  - メモリプロファイリング
- **CI/CD テスト**:
  - APK サイズの自動チェック
  - パフォーマンスベンチマーク

### フェーズ 3: WebGL 実装（第7-8週）

#### マイルストーン
- Emscripten による WebAssembly ビルド
- Sentis WebGPU 対応
- Progressive Web App 機能

#### タスク

##### 1. WASM ビルド設定
- **ゴール**: OpenJTalk の WebAssembly 版作成
- **成果物**:
  - `openjtalk_phonemizer.wasm`
  - JavaScript バインディング
  - WebGL プラグイン設定
- **動作確認方法**:
  - Chrome/Firefox での動作確認
  - WASM モジュールサイズ確認（目標: < 5MB）
- **CI/CD テスト**:
  - Emscripten ビルドの自動化
  - WASM サイズの監視

##### 2. Sentis WebGPU 統合
- **ゴール**: ブラウザでの ONNX 推論実装
- **成果物**:
  - WebGPU バックエンド設定
  - フォールバック実装（WebGL 2.0）
- **動作確認方法**:
  - 主要ブラウザでの動作テスト
  - 推論速度の測定
- **CI/CD テスト**:
  - Playwright によるブラウザ自動テスト
  - パフォーマンステスト

##### 3. Progressive Web App 対応
- **ゴール**: オフライン動作とキャッシング
- **成果物**:
  - Service Worker 実装
  - IndexedDB によるモデルキャッシュ
  - オフライン動作対応
- **動作確認方法**:
  - オフラインでの音声生成
  - キャッシュ動作の確認
- **CI/CD テスト**:
  - PWA 機能の自動テスト

### フェーズ 4: macOS 実装（第9-10週）

#### マイルストーン
- Universal Binary サポート（x86_64 + arm64）
- コード署名とノータリゼーション

#### タスク

##### 1. Universal Binary ビルド
- **ゴール**: Intel/Apple Silicon 両対応
- **成果物**:
  - `libopenjtalk_phonemizer.dylib`（Universal）
  - 適切な Info.plist 設定
- **動作確認方法**:
  ```bash
  lipo -info libopenjtalk_phonemizer.dylib
  # Architectures in the fat file: x86_64 arm64
  ```
- **CI/CD テスト**:
  - macOS ランナーでの自動ビルド
  - アーキテクチャ確認

##### 2. コード署名とノータリゼーション
- **ゴール**: macOS セキュリティ要件への準拠
- **成果物**:
  - 署名された dylib
  - ノータリゼーション済みパッケージ
- **動作確認方法**:
  - Gatekeeper での検証
  - 署名の確認
- **CI/CD テスト**:
  - 自動署名プロセス
  - ノータリゼーション状態の確認

### フェーズ 5: iOS 実装（第11-12週）

#### マイルストーン
- iOS 向け静的ライブラリビルド
- App Store 準拠

#### タスク

##### 1. iOS 静的ライブラリ
- **ゴール**: Bitcode 対応の .a ファイル
- **成果物**:
  - `libopenjtalk_phonemizer.a`
  - 適切な Build Settings
- **動作確認方法**:
  - Xcode プロジェクトでのビルド
  - iOS シミュレータ/実機での動作
- **CI/CD テスト**:
  - iOS ビルドの自動化
  - シミュレータテスト

##### 2. App Store 対応
- **ゴール**: 審査要件への準拠
- **成果物**:
  - Privacy Manifest
  - 適切なエンタイトルメント
  - IDFA 使用なし
- **動作確認方法**:
  - TestFlight でのテスト
  - 審査シミュレーション
- **CI/CD テスト**:
  - コンプライアンスチェック

### フェーズ 6: 多言語サポート（第13-14週）

#### マイルストーン
- espeak-ng 統合
- 50+ 言語サポート

#### タスク

##### 1. espeak-ng 音素化ライブラリ
- **ゴール**: 多言語音素化の実装
- **成果物**:
  - 各プラットフォーム向け espeak-ng ライブラリ
  - 言語別音素化ルール
- **動作確認方法**:
  - 各言語でのテキスト音素化
  - IPA 変換の確認
- **CI/CD テスト**:
  - 多言語テストスイート
  - 音素化精度の測定

##### 2. 言語自動検出
- **ゴール**: 入力テキストの言語自動判定
- **成果物**:
  - 言語検出アルゴリズム
  - フォールバック処理
- **動作確認方法**:
  - 混在テキストの処理
  - 検出精度の測定
- **CI/CD テスト**:
  - 言語検出テスト

### フェーズ 7: 品質保証とリリース（第15週）

#### マイルストーン
- 包括的なテストとベンチマーク
- ドキュメント完成
- v1.0.0 リリース

#### タスク

##### 1. パフォーマンステスト
- **ゴール**: 全プラットフォームでの性能検証
- **成果物**:
  - ベンチマーク結果
  - パフォーマンスレポート
  - 最適化提案
- **動作確認方法**:
  - リアルタイム係数測定（目標: < 0.5）
  - メモリ使用量測定
  - バッテリー消費測定（モバイル）
- **CI/CD テスト**:
  - 自動ベンチマーク実行
  - パフォーマンス回帰テスト

##### 2. ドキュメント作成
- **ゴール**: 完全なユーザー/開発者ドキュメント
- **成果物**:
  - API リファレンス
  - インテグレーションガイド
  - サンプルプロジェクト
  - トラブルシューティングガイド
- **動作確認方法**:
  - ドキュメントレビュー
  - サンプルコードの動作確認
- **CI/CD テスト**:
  - ドキュメントビルド自動化
  - リンクチェック

##### 3. リリース準備
- **ゴール**: v1.0.0 のリリース
- **成果物**:
  - Unity Package Manager パッケージ
  - GitHub Release
  - Asset Store 申請（オプション）
- **動作確認方法**:
  - パッケージインストールテスト
  - アップグレードパステスト
- **CI/CD テスト**:
  - リリース自動化
  - パッケージ検証

## CI/CD 統合要件

### ビルドマトリックス

```yaml
unity-versions:
  - 2022.3.0f1 (LTS)
  - 2023.3.0f1 (LTS)
  - 6000.0.35f1

platforms:
  - os: windows-latest
    name: Windows
  - os: ubuntu-latest
    name: Linux
  - os: macos-latest
    name: macOS
  - os: ubuntu-latest
    name: Android
  - os: macos-latest
    name: iOS
  - os: ubuntu-latest
    name: WebGL

architectures:
  - x64
  - arm64 (where applicable)
```

### 品質ゲート

1. **コードカバレッジ**
   - 最小要件: 80%
   - 推奨: 90%
   - 除外: 自動生成コード、プラットフォーム固有コード

2. **パフォーマンス基準**
   - リアルタイム係数: < 0.5
   - 初期化時間: < 1秒
   - メモリ使用量: < 100MB（モデル含む）

3. **バイナリサイズ制限**
   - ネイティブライブラリ: < 5MB/プラットフォーム
   - ONNX モデル: < 50MB/言語
   - 全体パッケージ: < 200MB

### 自動化パイプライン

1. **継続的インテグレーション**
   ```yaml
   on:
     pull_request:
       - ビルド検証
       - 単体テスト実行
       - コードカバレッジ測定
       - 静的解析
   ```

2. **ナイトリービルド**
   ```yaml
   schedule:
     - cron: '0 2 * * *'
       - 全プラットフォームビルド
       - 統合テスト実行
       - パフォーマンステスト
       - 長時間テスト
   ```

3. **リリース自動化**
   ```yaml
   on:
     tag:
       - パッケージビルド
       - 署名/ノータリゼーション
       - リリースノート生成
       - 配布
   ```

### モニタリング

1. **ビルド状態ダッシュボード**
   - 各プラットフォームのビルド状態
   - テスト結果サマリー
   - コードカバレッジトレンド

2. **パフォーマンストラッキング**
   - ベンチマーク結果の時系列グラフ
   - パフォーマンス回帰の自動検出
   - プラットフォーム別比較

3. **エラー監視**
   - ビルド失敗の通知
   - テスト失敗の詳細レポート
   - 自動 Issue 作成

## テスト戦略

### 単体テスト

```csharp
[TestFixture]
public class PiperTTSTests
{
    [Test]
    public async Task InitializeAsync_WithValidConfig_Succeeds()
    {
        // Arrange
        var config = new PiperConfig { TestMode = true };
        var tts = new PiperTTS();
        
        // Act
        await tts.InitializeAsync(config);
        
        // Assert
        Assert.IsTrue(tts.IsInitialized);
    }
}
```

### 統合テスト

```csharp
[TestFixture]
public class PiperIntegrationTests
{
    [Test]
    [Platform(Include = "Win,Linux,OSX")]
    public async Task GenerateSpeech_JapaneseText_ProducesAudio()
    {
        // End-to-end test with actual model
    }
}
```

### パフォーマンステスト

```csharp
[TestFixture]
public class PiperPerformanceTests
{
    [Test]
    [Performance]
    public void Phonemization_Performance()
    {
        Measure.Method(() => {
            phonemizer.Phonemize("テストテキスト", "ja");
        })
        .WarmupCount(10)
        .MeasurementCount(100)
        .Run();
    }
}
```

## リスク管理

### 技術的リスク

1. **Unity バージョン互換性**
   - リスク: Unity 6 の API 変更
   - 対策: 条件付きコンパイル、バージョン別実装

2. **プラットフォーム固有の問題**
   - リスク: ネイティブライブラリの互換性
   - 対策: 包括的なテスト、フォールバック実装

3. **パフォーマンス問題**
   - リスク: モバイルでの処理速度
   - 対策: 最適化、品質設定オプション

### スケジュールリスク

1. **依存関係の遅延**
   - リスク: Sentis アップデートの影響
   - 対策: バージョン固定、代替実装準備

2. **プラットフォーム審査**
   - リスク: iOS App Store 審査の遅延
   - 対策: 早期申請、審査ガイドライン準拠

## 成功指標

1. **技術指標**
   - 全プラットフォームでの動作
   - パフォーマンス目標達成
   - 高いコードカバレッジ

2. **品質指標**
   - バグ発生率 < 1%
   - クラッシュフリー率 > 99.9%
   - ユーザー満足度 > 4.5/5

3. **採用指標**
   - ダウンロード数
   - アクティブプロジェクト数
   - コミュニティ貢献

## まとめ

このロードマップは、Piper TTS の Unity 実装を体系的に進めるための包括的な計画です。各フェーズは前フェーズの成果に基づいて構築され、継続的なテストと品質保証により、高品質なクロスプラットフォーム TTS ソリューションの提供を目指します。

現在の PR（フェーズ 1）は、この全体計画の基盤となる重要な実装であり、後続のフェーズの成功の鍵となります。