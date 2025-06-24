# Piper日本語サポート

PiperはOpenJTalkを使用して日本語テキストの音声合成をサポートしています。

## 機能

- 日本語テキストの音素化（OpenJTalk使用）
- 日本語音声モデルのサポート
- 全プラットフォーム対応（Linux、macOS、Windows*）

*注: Windows版は現在OpenJTalkサポートを一時的に無効化しています。

## 必要なファイル

日本語音声合成には以下が必要です：

1. **OpenJTalk辞書**: 自動的にダウンロードされ、以下の場所に配置されます：
   - Linux/macOS: `<install_dir>/share/piper/openjtalk-dict/`
   - ビルドディレクトリ: `build/naist-jdic/`

2. **日本語音声モデル**: 日本語対応のONNXモデルファイル

## 使用方法

```bash
# 日本語テキストの音声合成
echo "こんにちは、世界" | piper --model ja_JP_model.onnx --output_file output.wav

# OpenJTalkサポートの確認
piper --help | grep openjtalk
```

## 環境変数

辞書の場所を手動で指定する場合：

```bash
export OPENJTALK_DICTIONARY_DIR=/path/to/naist-jdic
```

## トラブルシューティング

### "OpenJTalk failed"エラーが出る場合

1. 辞書ファイルが正しい場所にあるか確認
2. 環境変数`OPENJTALK_DICTIONARY_DIR`を設定
3. 辞書ファイルの権限を確認

### Windows版での制限

現在、Windows版ではOpenJTalkサポートが無効になっています。日本語テキストはespeak-ngで処理されますが、音質が劣る可能性があります。

## ビルド方法

OpenJTalkサポートを有効にしてビルドする場合：

```bash
cmake -B build -DUSE_OPENJTALK=ON
cmake --build build
```

## 今後の予定

- Windows版でのOpenJTalkサポート
- より高品質な日本語音声モデルの提供
- リアルタイム音声合成の最適化