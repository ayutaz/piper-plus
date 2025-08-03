# Piper Test Resources

このディレクトリには、Piperのビルドテストに使用するリソースが含まれています。

## ディレクトリ構成

- `models/` - テスト用の音声合成モデル
  - `ja_JP-css10-medium.onnx` - CSS10日本語データセットで学習した中規模モデル（F0 Predictor対応）
  - `ja_JP-css10-medium.onnx.json` - モデルの設定ファイル
  - `ja_JP-test-medium.onnx` - 旧版テストモデル
  - `ja_JP-test-medium.onnx.json` - 旧版設定ファイル
  
- `fixtures/` - テスト用の入力ファイル  
  - `test_japanese.txt` - 日本語のテスト用テキスト

## テスト内容

GitHub Actionsのビルドパイプラインで、各プラットフォーム（Linux、macOS、Windows）において：

1. ビルドされたPiperバイナリが正常に動作すること
2. 日本語テキストからの音声合成が可能であること
3. 生成される音声ファイルが適切なサイズ（100KB以上）であること

を確認します。

## モデルについて

### ja_JP-css10-medium.onnx（最新版）
- 学習データ: CSS10日本語コーパス（6,841音声ファイル）
- モデルサイズ: 約61MB
- エポック数: 1499
- 特徴: F0 Predictor対応、prosody情報による自然な韻律制御
- 音質: 高品質（MOS改善 +0.18-0.26期待）

### ja_JP-test-medium.onnx（旧版）
- 学習データ: CSS10日本語コーパス
- モデルサイズ: 約60MB
- エポック数: 1999
- 音質: 中程度（テスト用途には十分）