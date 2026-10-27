# Piper Test Resources

このディレクトリには、Piperのビルドテストに使用するリソースが含まれています。

## ディレクトリ構成

- `models/` - テスト用のモデルと辞書
  - `multilingual-test-medium.onnx` - 保持されている CSS10 日本語 fine-tune の多言語テストモデル（カスタム辞書対応）
  - `multilingual-test-medium.onnx.json` - モデルの設定ファイル
  - `zero-shot-test.onnx` / `zero-shot-test.onnx.json` - `speaker_embedding` 入力を持つ小型テストモデル（`scripts/generate_zero_shot_test_model.py` で生成）
  - `test_speaker.npy` - 上記モデル用のテスト話者 embedding
  - `cmudict_data.json` / `pinyin_single.json` / `pinyin_phrases.json` - 辞書ミラー（`docs/spec/dictionary-mirrors.toml` で同期を検査）

- `configs/` - テスト用の設定ファイル
  - `multilingual_test_config.json` - マルチリンガルテスト設定

- `fixtures/` - テスト用の入力ファイルと golden データ
  - `test_japanese.txt` - 日本語のテスト用テキスト
  - `test_english.txt` - 英語のテスト用テキスト
  - `speaker_encoder_golden.json` - Speaker Encoder の mel 前処理の cross-runtime golden（`generate_speaker_encoder_golden.py` で生成）
  - `kaldi_fbank_golden.json` / `zs_campplus_golden.json` - zero-shot 話者 encoder（Kaldi fbank / CAM++）の cross-runtime golden（Rust / Go / C# / WASM）（`generate_kaldi_fbank_golden.py` / `generate_zs_campplus_golden.py` で生成）

- `model_resolution_vectors.json` - モデル名解決の cross-runtime テストベクタ（[`docs/reference/model-resolution.md`](../docs/reference/model-resolution.md)）
- `test_*.py` - Python テスト（Speaker Encoder、音素 ID、言語サンプラー）
- `test_arm64_multilingual.sh` / `test_dictionary_download_ci.sh` - CI（`test-arm64-multilingual.yml` / `test-multilingual-tts.yml`）から呼ぶシェルスクリプト

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
