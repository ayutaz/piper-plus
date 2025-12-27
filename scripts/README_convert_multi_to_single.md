# マルチスピーカーモデルから単一話者モデルへの変換

このスクリプトは、マルチスピーカーモデルから単一話者用の追加学習（ファインチューニング）用モデルを作成します。

## 概要

事前学習されたマルチスピーカーモデルを特定の単一話者データセットでファインチューニングする場合、以下の処理が必要です：

1. **話者埋め込み層の削除** - マルチスピーカーモデルの話者関連レイヤーを削除
2. **オプティマイザ状態の初期化** - 新しい学習のためオプティマイザをリセット
3. **エポックカウンタのリセット** - 学習を0エポックから開始するためリセット
4. **設定の更新** - `num_speakers`を0に変更

## 使用方法

### 1. 基本的な実行

```bash
# デフォルトパスで実行
python scripts/convert_multi_to_single_speaker.py

# カスタムパスを指定
python scripts/convert_multi_to_single_speaker.py \
  --input-checkpoint /path/to/multi_speaker_model.ckpt \
  --output-checkpoint /path/to/base_model.ckpt

# 環境変数を使用
export INPUT_CHECKPOINT=/path/to/multi_speaker_model.ckpt
export OUTPUT_CHECKPOINT=/path/to/base_model.ckpt
python scripts/convert_multi_to_single_speaker.py
```

### 2. コマンドライン引数

- `--input-checkpoint`: 入力マルチスピーカーモデルのパス
- `--output-checkpoint`: 出力単一話者ベースモデルのパス

環境変数 `INPUT_CHECKPOINT` と `OUTPUT_CHECKPOINT` でデフォルト値を設定可能です。

### 3. config.jsonの作成

変換後は、対応するconfig.jsonも作成する必要があります：

```python
import json

# 元のconfig.jsonを読み込み
with open('original_config.json', 'r') as f:
    config = json.load(f)

# 単一話者用に修正
config['num_speakers'] = 0
if 'speaker_id_map' in config:
    del config['speaker_id_map']

# 保存
with open('base_model_config.json', 'w') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
```

## 削除されるレイヤー

以下のレイヤーが自動的に削除されます：

- `model_g.emb_g.weight` - 話者埋め込み層
- `model_g.dec.cond.*` - デコーダーの条件付けレイヤー
- `model_g.enc_q.enc.cond_layer.*` - エンコーダーの条件付けレイヤー
- `model_g.dp.cond.*` - Duration Predictorの条件付けレイヤー
- `model_g.flow.flows.*.enc.cond_layer.*` - フローの条件付けレイヤー

## ファインチューニング例

### 単一話者データセットの準備

```bash
# LJSpeech形式のデータセットを前処理
python -m piper_train.preprocess \
  --language ja \
  --input-dir /path/to/wav/files \
  --output-dir /path/to/dataset \
  --dataset-format ljspeech \
  --single-speaker \
  --sample-rate 22050
```

### ファインチューニングの実行

```bash
python -m piper_train \
  --dataset-dir /path/to/dataset \
  --resume_from_checkpoint /path/to/base_model.ckpt \
  --accelerator gpu \
  --devices 1 \
  --batch-size 32 \
  --learning-rate 1e-4 \
  --max_epochs 500 \
  --checkpoint-epochs 50 \
  --default_root_dir /path/to/output
```

## 注意事項

- 変換前のモデルと同じサンプルレート、言語設定を使用してください
- ファインチューニング時の学習率は、事前学習時より低めに設定することを推奨します（例：1e-4）
- 十分なVRAMがある場合は、バッチサイズを大きくすることで学習を高速化できます

## トラブルシューティング

### Unexpected keysエラー

ファインチューニング時に「Unexpected keys」のエラーが発生した場合、話者関連のレイヤーが正しく削除されていない可能性があります。スクリプトを再実行するか、手動で該当キーを削除してください。

### サイズ不一致エラー

モデルアーキテクチャが異なる場合（例：品質設定が異なる）、レイヤーサイズが一致しないことがあります。同じ品質設定（medium/high）のモデルを使用してください。

### エポック不一致エラー

「You restored a checkpoint with current_epoch=X, but you have set Trainer(max_epochs=Y)」というエラーが発生した場合、エポックカウンタが正しくリセットされていません。

以下の項目がリセットされている必要があります：

```python
checkpoint["epoch"] = 0
checkpoint["global_step"] = 0
checkpoint["loops"]["fit_loop"]["epoch_loop.current_epoch"] = 0
checkpoint["loops"]["fit_loop"]["epoch_progress"] = {
    'total': {'ready': 0, 'completed': 0, 'started': 0, 'processed': 0},
    'current': {'ready': 0, 'completed': 0, 'started': 0, 'processed': 0}
}
```

変換スクリプト `convert_multi_to_single_speaker.py` はこれらを自動的にリセットします。手動で変換した場合は上記の項目を確認してください。