# 日本語TTS学習の推奨設定

## 概要

PR #98以降のPiper TTSで高品質な日本語音声を生成するための学習設定ガイドです。

## アーキテクチャの変更による影響

### v1.3.0（PR #98前）
- シンプルなVITSアーキテクチャ
- 必要エポック数: 1000-1500
- CSS10（5時間）でも十分な品質

### v1.4.0以降（PR #98後）
- F0 Predictor + AccentProcessor追加
- 必要エポック数: 3000-5000
- より大規模なデータセット推奨

## データセット別推奨設定

### 小規模データセット（CSS10、5時間）

```bash
# 初回学習
python -m piper_train \
    --dataset-dir dataset/ \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 16 \
    --num-workers 16 \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --max_epochs 5000 \
    --checkpoint-epochs 100 \
    --precision 16-mixed \
    --accumulate_grad_batches 2
```

**ポイント：**
- 5000エポック必要（PR #98前の3倍以上）
- 学習時間: L4×4で約2日
- 品質: 個人利用には十分

### 中規模データセット（JVS、30時間）

```bash
python -m piper_train \
    --dataset-dir jvs_dataset/ \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 20 \
    --num-workers 16 \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --max_epochs 3000 \
    --checkpoint-epochs 50 \
    --precision 16-mixed
```

**ポイント：**
- 3000エポックで高品質
- 学習時間: L4×4で約3-4日
- 品質: 商用利用可能レベル

### 大規模データセット（600時間以上）

```bash
python -m piper_train \
    --dataset-dir large_dataset/ \
    --accelerator gpu \
    --devices 8 \
    --strategy ddp_find_unused_parameters_true \
    --batch-size 14 \
    --num-workers 32 \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --max_epochs 2000 \
    --checkpoint-epochs 25 \
    --precision 16-mixed \
    --gradient_clip_val 1.0
```

**ポイント：**
- 2000エポックで収束
- 学習時間: L4×8で約10-14日
- 品質: 最高品質、多話者対応

## 学習戦略

### 1. 段階的学習（推奨）

```bash
# ステップ1: 基本モデル学習（F0 Predictorなし）
# config.jsonでf0_predictorをfalseに設定して学習

# ステップ2: F0 Predictor追加でファインチューニング
python -m piper_train \
    --resume_from_checkpoint step1_model.ckpt \
    --base_lr 5e-5 \
    --max_epochs 1000
```

### 2. 転移学習

```bash
# 大規模データで事前学習済みモデルから開始
python -m piper_train \
    --resume_from_single_speaker_checkpoint pretrained_jp.ckpt \
    --dataset-dir target_speaker/ \
    --base_lr 1e-4 \
    --max_epochs 500
```

## トラブルシューティング

### 発音が不明瞭な場合

1. **エポック数不足**
   - 最低3000エポックまで学習
   - 学習曲線が平坦化するまで継続

2. **学習率が高すぎる**
   - `--base_lr 1e-4`以下に設定
   - 追加学習時は`5e-5`推奨

3. **データセット品質**
   - 音声の前後の無音部分を統一
   - テキストの正規化を確認

### メモリ不足

```bash
# バッチサイズを減らして勾配累積を増やす
--batch-size 8 --accumulate_grad_batches 4

# Mixed Precisionを使用
--precision 16-mixed

# メモリ断片化対策
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

## 品質評価の目安

| エポック数 | 期待される品質 |
|-----------|--------------|
| 500 | 音素は認識可能だが不自然 |
| 1000 | 基本的な発音は正しい |
| 1500 | v1.3.0相当（F0なし） |
| 3000 | 自然な韻律 |
| 5000 | 高品質、製品レベル |

## まとめ

PR #98以降は高品質な日本語TTSが可能になりましたが、その分学習に必要なリソースも増加しています。データセットのサイズと用途に応じて適切な設定を選択してください。