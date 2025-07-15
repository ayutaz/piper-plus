# Unity Piper TTS タスクチェックリスト

## 現在のPR範囲（フェーズ1: Windows/Linux基盤）

### ✅ 完了済みタスク

- [x] **Core API設計（TDD）**
  - [x] IPiperTTS インターフェース定義
  - [x] PiperConfig 実装（バリデーション付き）
  - [x] PiperTTS 実装（非同期初期化）
  - [x] TestMode サポート
  - [x] 単体テスト作成

- [x] **音素化インターフェース**
  - [x] IPhonemizer インターフェース定義
  - [x] BasePhonemizer 実装（LRUキャッシュ付き）
  - [x] MockPhonemizer 実装（テスト用）
  - [x] テキスト正規化機能
  - [x] 単体テスト作成

- [x] **Sentis音声合成（基本実装）**
  - [x] SentisAudioGenerator クラス
  - [x] Unity Sentis 2.1.3 API対応
  - [x] TestMode サポート
  - [x] エラーハンドリング
  - [x] 単体テスト作成

- [x] **プラットフォーム抽象化**
  - [x] PlatformHelper 実装
  - [x] プラットフォーム検出
  - [x] ライブラリ名解決
  - [x] 単体テスト作成

- [x] **CI/CD基盤**
  - [x] GitHub Actions 設定
  - [x] Unity Test Runner 統合（Docker方式）
  - [x] ネイティブライブラリビルド（Windows/Linux/macOS）
  - [x] マルチプラットフォームテスト

### ⚠️ 部分的実装（要改善）

- [ ] **OpenJTalk音素化ライブラリ**
  - [x] C++ラッパー作成（openjtalk_wrapper.cpp）
  - [x] ビルドシステム（CMake）
  - [x] CI/CDでのビルド
  - [ ] ❌ 実際のOpenJTalk統合（現在はシステムコマンド呼び出し）
  - [ ] ❌ P/Invokeバインディング実装
  - [ ] ❌ 辞書ファイル管理
  - [ ] ❌ 動作テスト

### ❌ 未実装タスク（このPR範囲）

- [ ] **OpenJTalkPhonemizer実装**
  ```csharp
  public class OpenJTalkPhonemizer : BasePhonemizer
  {
      [DllImport("openjtalk_wrapper")]
      private static extern IntPtr openjtalk_create();
      // ... P/Invoke定義
  }
  ```

- [ ] **音素IDマッピング**
  - [ ] Piperフォーマットの音素ID変換
  - [ ] 言語別マッピングテーブル

- [ ] **実動作サンプル**
  - [ ] エディター実行用サンプルシーン
  - [ ] 統合テストスクリプト

## 今後のフェーズ

### フェーズ2: Android実装（第4-6週）

- [ ] Android NDKビルド環境
- [ ] JNIラッパー実装
- [ ] Unity Android統合
- [ ] APKサイズ最適化
- [ ] 実機テスト

### フェーズ3: WebGL実装（第7-8週）

- [ ] Emscriptenビルド設定
- [ ] WAMSモジュール作成
- [ ] Sentis WebGPU対応
- [ ] ブラウザテスト
- [ ] PWA機能

### フェーズ4: macOS実装（第9-10週）

- [ ] Universal Binary対応
- [ ] コード署名
- [ ] ノータリゼーション
- [ ] M1ネイティブテスト

### フェーズ5: iOS実装（第11-12週）

- [ ] 静的ライブラリビルド
- [ ] Bitcodeサポート
- [ ] App Store準拠
- [ ] TestFlight配布

### フェーズ6: 多言語サポート（第13-14週）

- [ ] espeak-ng統合
- [ ] 50+言語対応
- [ ] 言語自動検出
- [ ] 国際化テスト

### フェーズ7: QAとリリース（第15週）

- [ ] パフォーマンステスト
- [ ] ドキュメント完成
- [ ] Unity Package作成
- [ ] v1.0.0リリース

## CI/CDチェックリスト

### ✅ 実装済み

- [x] Unity 6ビルド対応
- [x] Unity Test Framework統合
- [x] ネイティブライブラリビルド（Windows/Linux/macOS）
- [x] アーティファクト管理
- [x] PRごとの自動テスト

### ❌ 今後実装

- [ ] コードカバレッジレポート
- [ ] パフォーマンステスト自動化
- [ ] マルチUnityバージョンテスト
- [ ] ナイトリービルド
- [ ] リリース自動化

## テストチェックリスト

### ✅ 実装済みテスト

- [x] PiperConfigTests
- [x] PiperTTSTests
- [x] SentisAudioGeneratorTests
- [x] PhonemizersTests（MockPhonemizer）
- [x] PlatformHelperTests

### ❌ 必要なテスト

- [ ] OpenJTalkPhonemizerTests
- [ ] 統合テスト（E2E）
- [ ] パフォーマンステスト
- [ ] ストレステスト
- [ ] プラットフォーム固有テスト

## 動作確認チェックリスト

### Unity Editor（M1 Mac）での確認項目

#### ✅ 現在確認可能

- [x] Core API初期化（TestMode）
- [x] MockPhonemizer動作
- [x] プラットフォーム検出
- [x] 単体テスト実行
- [x] キャッシュ機能

#### ❌ 要実装後確認

- [ ] OpenJTalk音素化
- [ ] 実際のONNXモデル読み込み
- [ ] 音声生成（日本語）
- [ ] リアルタイムパフォーマンス
- [ ] メモリ使用量

## 品質基準チェックリスト

### ✅ 達成済み

- [x] コーディング規約準拠
- [x] 非同期API設計
- [x] エラーハンドリング
- [x] ログ出力
- [x] テスト可能な設計

### ⚠️ 要改善

- [ ] コードカバレッジ80%以上（現在: 未測定）
- [ ] パフォーマンス基準達成（未測定）
- [ ] メモリリーク確認
- [ ] スレッドセーフティ確認

## ドキュメントチェックリスト

### ✅ 作成済み

- [x] PR説明文
- [x] コードコメント（基本）
- [x] このタスクチェックリスト
- [x] 実装ロードマップ

### ❌ 要作成

- [ ] APIリファレンス
- [ ] インテグレーションガイド
- [ ] トラブルシューティング
- [ ] パフォーマンスガイド
- [ ] サンプルプロジェクト