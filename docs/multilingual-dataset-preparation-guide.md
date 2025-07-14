# マルチ言語データセット準備ガイド

このガイドでは、マルチ言語TTSモデルの学習に必要なデータセットの準備方法を説明します。

## 必要なデータセット形式

### LJSpeech形式（推奨）

各言語のデータセットは以下の構造である必要があります：

```
dataset_directory/
├── metadata.csv          # テキストと音声ファイルの対応表
└── wav/ (または wavs/)   # 音声ファイルディレクトリ
    ├── audio_001.wav
    ├── audio_002.wav
    └── ...
```

#### metadata.csv の形式

```csv
audio_001|こんにちは、今日はいい天気ですね。
audio_002|ありがとうございます。
audio_003|日本語の音声合成システムです。
```

または話者ID付き：

```csv
audio_001|speaker1|こんにちは、今日はいい天気ですね。
audio_002|speaker1|ありがとうございます。
audio_003|speaker2|日本語の音声合成システムです。
```

### 音声ファイルの要件

- **形式**: WAV (推奨) または他の一般的な音声形式
- **サンプリングレート**: 任意（前処理で22050Hzに変換されます）
- **チャンネル**: モノラル推奨
- **ビット深度**: 16bit以上推奨

## データセット準備手順

### 1. 言語別データセットの準備

各言語について個別にデータセットを準備します。

#### 日本語データセット例
```
japanese_dataset/
├── metadata.csv
└── wav/
    ├── jp_001.wav
    ├── jp_002.wav
    └── ...
```

#### 英語データセット例
```
english_dataset/
├── metadata.csv
└── wav/
    ├── en_001.wav
    ├── en_002.wav
    └── ...
```

### 2. 設定ファイルの作成

`multilingual_config.json`を作成：

```json
{
  "datasets": [
    {
      "language": "ja",
      "input_dir": "/path/to/japanese_dataset",
      "speaker_id_offset": 0
    },
    {
      "language": "en",
      "input_dir": "/path/to/english_dataset",
      "speaker_id_offset": 100
    }
  ]
}
```

### 3. 前処理の実行

#### 方法1: シェルスクリプトを使用

```bash
# 設定ファイルを使用
./scripts/run_multilingual_preprocessing.sh \
  -c multilingual_config.json \
  -o output_dataset

# または直接ディレクトリを指定
./scripts/run_multilingual_preprocessing.sh \
  -j /path/to/japanese_dataset \
  -e /path/to/english_dataset \
  -o output_dataset
```

#### 方法2: Pythonスクリプトを直接実行

```bash
python scripts/preprocess_multilingual_dataset.py \
  --config-file multilingual_config.json \
  --output-dir output_dataset \
  --sample-rate 22050 \
  --max-workers 4
```

### 4. 出力の確認

前処理が完了すると、以下のファイルが生成されます：

```
output_dataset/
├── dataset.jsonl         # 学習用データ
├── validation.jsonl      # 検証用データ
├── config.json          # データセット設定
├── phoneme_map.json     # 音素マッピング
└── cache/               # キャッシュされた音声データ
    └── 22050/
        ├── *.norm.npy   # 正規化された音声
        └── *.spec.npy   # スペクトログラム
```

## 混合言語データの追加（オプション）

コードスイッチング（文内での言語切り替え）を含むデータを追加する場合：

### metadata.csv の例

```csv
mixed_001|今日のmeetingは3時からです。
mixed_002|このsoftwareはopen sourceです。
mixed_003|Let's go to 東京 tomorrow!
```

システムが自動的に言語を検出し、適切な音素化を行います。

## データセット品質のガイドライン

### 推奨事項

1. **音声品質**
   - 録音環境: 静かな環境での録音
   - ノイズレベル: -40dB以下
   - 音声の明瞭性: はっきりとした発音

2. **テキスト品質**
   - 正確な書き起こし
   - 適切な句読点
   - 数字は読み方に変換（例: "3時" → "さんじ"）

3. **データ量**
   - 各言語: 最低1時間、推奨10時間以上
   - 話者あたり: 最低30分、推奨1時間以上

### データ検証

前処理後、以下を確認してください：

```python
# データセットの統計を確認
import json

with open('output_dataset/config.json') as f:
    config = json.load(f)
    
print(f"言語: {config['languages']}")
print(f"話者数: {config['num_speakers']}")
print(f"学習データ数: {config['utterance_counts']['train']}")
print(f"検証データ数: {config['utterance_counts']['validation']}")
```

## トラブルシューティング

### よくある問題と解決方法

1. **音声ファイルが見つからない**
   - metadata.csv のファイル名と実際のファイル名が一致しているか確認
   - 拡張子（.wav）の有無を確認

2. **文字エンコーディングエラー**
   - metadata.csv がUTF-8で保存されているか確認
   - BOMなしUTF-8を使用

3. **メモリ不足**
   - `--max-workers` を減らす
   - データセットを分割して処理

4. **音素化エラー**
   - 日本語: pyopenjtalkがインストールされているか確認
   - その他: espeak-ngがインストールされているか確認

## 次のステップ

データセットの準備が完了したら、モデルの学習を開始できます：

```bash
python -m piper_train.train_multilingual \
  --dataset-dir output_dataset \
  --max_epochs 1000 \
  --batch-size 16 \
  --quality medium
```

詳細は[マルチ言語モデル学習ガイド](multilingual-training-guide.md)を参照してください。