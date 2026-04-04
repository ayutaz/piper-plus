# Piper Test Resources

このディレクトリには、Piperのビルドテストに使用するリソースが含まれています。

## ディレクトリ構成

- `models/` - テスト用の音声合成モデル
  - `multilingual-test-medium.onnx` - 日本語テストモデル（カスタム辞書対応）
  - `multilingual-test-medium.onnx.json` - モデルの設定ファイル
  
- `configs/` - テスト用の設定ファイル
  - `multilingual_test_config.json` - マルチリンガルテスト設定

- `fixtures/` - テスト用の入力ファイル  
  - `test_japanese.txt` - 日本語のテスト用テキスト
  - `test_english.txt` - 英語のテスト用テキスト

## テスト内容

GitHub Actionsのビルドパイプラインで、各プラットフォーム（Linux、macOS、Windows）において：

1. ビルドされたPiperバイナリが正常に動作すること
2. 日本語テキストからの音声合成が可能であること
3. 生成される音声ファイルが適切なサイズ（100KB以上）であること

を確認します。

## モデルについて

### multilingual-test-medium.onnx
- 学習データ: CSS10日本語コーパス（6,841音声ファイル）
- モデルサイズ: 約60MB
- エポック数: 50（6言語ベースモデルからファインチューニング）
- 特徴: カスタム辞書による正確な日本語発音、EMA適用による安定した音質
- 音質: 高品質（複合語の正確な発音を実現）