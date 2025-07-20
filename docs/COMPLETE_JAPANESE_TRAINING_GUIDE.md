# Piper TTS 日本語モデル学習 完全ガイド

このドキュメントは、Piper TTS を使って高品質な日本語の音声合成モデルをゼロから学習し、ファインチューニングを行うまでの完全なワークフローをまとめたものです。

## 1. 学習環境の準備

高品質なモデル学習には、適切なハードウェアとソフトウェア環境が不可欠です。

### ハードウェア要件

**GPU**: NVIDIA A100 80GB のような、十分なVRAMとTensorコアを搭載したGPUを推奨します。

**OS**: Linuxベースの環境（Dockerコンテナなど）が一般的です。

### Python環境

**Python環境**: uv や venv を使って、プロジェクト専用の仮想環境を構築します。

### 主要ライブラリ

**PyTorch**: bf16 や fp16 混合精度をフル活用するため、最新の安定版またはNightly版をインストールします。CUDAバージョンに合った公式ホイールを使用するのが重要です。

**NumPy**: PiperのC++拡張機能との互換性のため、1.x 系（例: 1.26.4）にバージョンを固定します。

**PyTorch Lightning**: Piperが依存する学習フレームワークです。バージョン間の互換性に注意が必要です（1.9.5 などで動作確認）。

**その他**: pyopenjtalk-plus, pyworld など、日本語処理や音声処理に必要なライブラリをインストールします。

## 2. データセットの準備

モデルの品質はデータセットの品質で決まります。

### データセット形式

**形式**: LJ Speech 互換フォーマットに準拠します。

```
dataset/
├── wavs/           # 音声ファイル（.wav）を格納するディレクトリ
└── metadata.csv    # 音声とテキストの対応を記述するファイル
```

### 音声ファイル要件

- **サンプルレート**: 22050Hz
- **チャンネル**: モノラル (1ch)
- **フォーマット**: 16-bit PCM WAV

ffmpeg を使って、データセット全体の形式を事前に統一しておくことを強く推奨します。

### メタデータファイル (metadata.csv)

- **単一話者モデルの場合**: `ファイルID|テキスト` の2カラム形式
- **複数話者モデルの場合**: `ファイルID|話者ID|テキスト` の3カラム形式
- **テキスト**: ヘッダー行は含めず、生の日本語テキスト（漢字かな混じり文）を記載します

## 3. 前処理 (piper_train.preprocess)

生のデータセットを、モデルが学習できる内部形式に変換します。

### 音素化

Piperの日本語対応ブランチでは、`--language ja` を指定することで、espeak-ng よりも高品質な pyopenjtalk ベースの音素化が自動的に行われます。これにより、日本語のアクセントや韻律がより正確に扱われます。

### 堅牢性の確保

大規模データセットには、処理をハングさせる「問題のあるファイル」が含まれることがあります。これを解決するため、preprocess.py スクリプトを以下のように修正します。

**タイムアウト機能の実装**: 個々のファイルの処理に時間制限（例: 60秒）を設け、ハングした場合でも自動でスキップするように、multiprocessing.Pool の使い方を imap_unordered から apply_async と result.get(timeout=...) を使うロジックに変更します。

**逐次書き込み**: 処理結果をメモリに溜め込まず、1件終わるごとに dataset.jsonl に追記するように修正します。これにより、途中で中断しても進捗が失われません。

### 実行コマンド例（複数話者）

```bash
python3 -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/dataset \
  --output-dir /path/to/preprocessed_data \
  --dataset-format ljspeech \
  --sample-rate 22050 \
  --max-workers 45
```

### 実行コマンド例（単一話者）

```bash
python3 -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/dataset \
  --output-dir /path/to/preprocessed_data \
  --dataset-format ljspeech \
  --single-speaker \
  --sample-rate 22050 \
  --max-workers 45
```

## 4. 学習 (piper_train)

前処理済みデータを使って、モデルを学習します。

### 学習の種類

**ゼロからの学習**: `--resume_from_checkpoint` を指定せずに実行します。大規模データセット（例: Moe-speech 600時間）で、汎用的な日本語能力を持つ「基盤モデル」を作成する際に用います。

**追加学習（ファインチューニング）**: `--resume_from_checkpoint` に事前学習済みのモデルのパスを指定します。基盤モデルを、特定の単一話者（例: つくよみちゃん）の声に特化させる際に用います。

### 重要なハイパーパラメータ（A100 80GB向け）

- `--quality`: medium（スマホ向けなどバランス重視）または high（大規模データで最高品質を目指す場合）
- `--precision`: 16 (fp16混合精度) が速度とメモリ効率の観点から推奨されます。bf16 は torch.stft との互換性問題があるため、PyTorchのバージョンに注意が必要です
- `--batch-size`: VRAMに収まる範囲でできるだけ大きく設定します（例: fp16 なら 96 や 128）
- `--max_epochs` / `--max_steps`: 学習期間をエポック数または総ステップ数で指定します
- `--num-workers`: データ読み込みを高速化するための引数。lightning.py を修正してコマンドラインから指定できるようにしました
- `--save-top-k`: チェックポイントの保存方法を制御する引数。__main__.py を修正して追加しました。-1 を指定すると、全てのチェックポイントが保存されます

### 実行コマンド例（ゼロから）

```bash
python3 -m piper_train \
  --dataset-dir /path/to/preprocessed_data \
  --accelerator 'gpu' \
  --devices 1 \
  --quality medium \
  --precision 16 \
  --batch-size 64 \
  --max_epochs 500 \
  --checkpoint-epochs 10 \
  --save-top-k -1 \
  --num-workers 45
```

### マルチGPU学習の例

```bash
python3 -m piper_train \
  --dataset-dir /path/to/preprocessed_data \
  --accelerator gpu \
  --devices 4 \
  --strategy ddp \
  --batch-size 14 \
  --accumulate_grad_batches 2 \
  --precision 16-mixed \
  --num-workers 80 \
  --gradient_clip_val 1.0 \
  --max_epochs 1500 \
  --checkpoint-epochs 50 \
  --save-top-k -1
```

## 5. 評価と推論

学習したモデルの品質を確認し、音声ファイルを生成します。

### ONNXへの変換

学習で得られたチェックポイント（.ckpt）は、推論に適したONNX形式に変換します。

```bash
python3 -m piper_train.export_onnx \
  /path/to/your/model.ckpt \
  /path/to/output/model.onnx

# config.jsonも忘れずにコピー
cp /path/to/preprocessed_data/config.json /path/to/output/model.onnx.json
```

### 推論の実行

piper コマンドラインツールで音声を生成します。

```bash
echo "これはテスト用の日本語音声です。" | \
  piper -m /path/to/output/model.onnx -c /path/to/output/model.onnx.json \
  --output_file test.wav
```

複数話者モデルの場合: `--speaker <話者ID>` を追加で指定します。

### 品質評価

**主観評価**: 複数のチェックポイントから生成した音声を実際に聞き比べ、最も自然で高品質なモデルを選定します。

**客観評価**: RTF（リアルタイム係数）を計測して推論速度を評価します。

## 6. ライセンス

モデルを公開する際は、使用したデータセットやツールのライセンスを遵守する必要があります。

- **JVSコーパス**: 無料ダウンロード版は非営利。商用利用には別途ライセンス契約が必要です
- **CSS10コーパス**: Apache License 2.0 であり、商用利用可能です
- **piper-tts**: MITライセンス、pyopenjtalk は MIT/BSDライセンスで、共に自由度が高いです

## 関連ドキュメント

- [基本的な日本語使用方法](../JAPANESE_USAGE.md)
- [マルチGPU学習ガイド](MULTI_GPU_TRAINING.md)
- [日本語クイックスタート](quick_start_japanese.md)
- [学習ガイド](../TRAINING.md)