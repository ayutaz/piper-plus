# Unity Piper TTS タスクチェックリスト

## 現在のPR範囲（フェーズ1: Windows/Linux基盤）

### ✅ 完了済みタスク

- [x] **Core API設計（TDD）**
  - [x] IPiperTTS インターフェース定義
  - [x] PiperConfig 実装（バリデーション付き）
  - [x] PiperTTS 実装（非同期初期化）
  - [x] TestMode サポート
  - [x] 単体テスト作成

- [x] **音素化インターフェース** ✅ Phase 1.4-1.6完了
  - [x] IPhonemizer インターフェース定義
  - [x] PhonemeResult データ構造
  - [x] BasePhonemizer 実装（LRUキャッシュ付き）
  - [x] MockPhonemizer 実装（テスト用）
  - [x] テキスト正規化機能（多言語対応）
  - [x] LRUキャッシュ実装（スレッドセーフ）
  - [x] LanguageInfo メタデータ管理
  - [x] 包括的単体テスト（126個）

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

- [x] **OpenJTalk音素化ライブラリ** ✅ Phase 1.7-1.8完了
  - [x] C++ラッパー作成（openjtalk_wrapper_full.c）
  - [x] ビルドシステム（CMake）
  - [x] CI/CDでのビルド
  - [x] ✅ 実際のOpenJTalk統合（pyopenjtalk互換の完全実装）
  - [x] ✅ P/Invokeバインディング実装
  - [x] ✅ 辞書ファイル管理（sys.dic, unk.dic, char.bin）
  - [x] ✅ 動作テスト

- [x] **OpenJTalkPhonemizer実装** ✅ Phase 1.8完了
  ```csharp
  public class OpenJTalkPhonemizer : BasePhonemizer
  {
      [DllImport("openjtalk_wrapper")]
      private static extern IntPtr openjtalk_create(string dict_path);
      // ... P/Invoke定義完了
  }
  ```

- [x] **音素IDマッピング** ✅
  - [x] Piperフォーマットの音素ID変換
  - [x] 日本語音素マッピングテーブル

- [x] **実動作サンプル** ✅
  - [x] エディター実行用サンプル（PiperTTSDemo, OpenJTalkPhonemizerDemo）
  - [x] 統合テストスクリプト（OpenJTalkPhonemizerTest）

### ✅ 完了済みタスク（Phase 1.9）

- [x] **ONNX モデル統合（Phase 1.9）** ✅ 2025年1月19日完了
  - [x] Unity.InferenceEngineを使用したONNXモデル読み込み
  - [x] 音素列から音声波形への変換
  - [x] リアルタイム音声生成
  - [x] InferenceAudioGenerator実装
  - [x] PhonemeEncoder実装（PUAマッピング対応）
  - [x] デモシーン作成（日本語音声生成確認）

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
- [x] OpenJTalkPhonemizerTests ✅ Phase 1.8完了

### ❌ 必要なテスト

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
- [x] OpenJTalk音素化 ✅ Phase 1.8完了
- [x] PiperTTSとの統合動作 ✅

#### ✅ Phase 1.9で確認済み

- [x] 実際のONNXモデル読み込み ✅
- [x] 音声生成（日本語）✅
- [x] CPUバックエンドでの動作確認 ✅

#### ⚠️ 要改善/確認

- [ ] 日本語発音精度（Phase 1.10でOpenJTalk統合）
- [ ] GPUバックエンド対応
- [ ] リアルタイムパフォーマンス最適化
- [ ] メモリ使用量の詳細計測

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