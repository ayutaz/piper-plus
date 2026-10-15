# Piper Test Resources

このディレクトリには、Piperのビルドテストに使用するリソースが含まれています。

## ディレクトリ構成

- `models/` - テスト用の音声合成モデル
  - `multilingual-test-medium.onnx` - 保持されている CSS10 日本語 fine-tune の多言語テストモデル（カスタム辞書対応）
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
3. 生成される WAV が空でなく、各テストの検証条件を満たすこと

を確認します。

## モデルについて

### multilingual-test-medium.onnx

- 学習データ: CSS10 日本語コーパス（6言語ベースからの fine-tune）。詳細は [`docs/spec/model-sha256-manifest.toml`](../docs/spec/model-sha256-manifest.toml) の保持テストフィクスチャ記録を参照
- 用途: クロスランタイム、辞書、CLI の回帰テスト用。公開品質の評価や現行の zero-shot 公開モデルを表すものではない
- 設定: 同名の `.onnx.json` sidecar を必ず併用する
