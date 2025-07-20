# Multi-GPU Training Guide for Piper VITS

このガイドでは、Piper VITSでマルチGPU学習を行う方法について説明します。

## 前提条件

- PyTorch Lightning 2.x以上
- 複数のGPU環境
- CUDA対応環境

## 基本的な使用方法

### DDP（Distributed Data Parallel）戦略

最も推奨される戦略です：

```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 16 \
    --devices 4 \
    --strategy ddp \
    --auto_lr_scaling \
    --num-workers 16 \
    --max_epochs 1000
```

### パラメータ説明

- `--devices N`: 使用するGPU数
- `--strategy ddp`: DDP戦略を使用
- `--auto_lr_scaling`: GPUに応じて学習率を自動スケーリング
- `--num-workers N`: DataLoaderのワーカー数（推奨: GPUあたり4ワーカー）

## 推奨設定

### 2-4 GPUs環境

```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 8 \
    --devices 4 \
    --strategy ddp \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --num-workers 16 \
    --max_epochs 1000 \
    --precision 16-mixed
```

### 8+ GPUs環境

```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 4 \
    --devices 8 \
    --strategy ddp \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --num-workers 32 \
    --max_epochs 1000 \
    --precision 16-mixed \
    --accumulate_grad_batches 2
```

## DDP戦略の最適化

### 自動最適化設定

以下の最適化が自動的に適用されます：

- `find_unused_parameters=False`: パフォーマンス向上
- `gradient_as_bucket_view=True`: メモリ効率向上
- `static_graph=True`: VITSの固定グラフ構造に最適化

### DataLoader最適化

- `persistent_workers=True`: ワーカーの再利用
- `pin_memory=True`: GPU転送最適化
- 自動num_workers調整

## 学習率スケーリング

### 自動スケーリング（推奨）

```bash
--auto_lr_scaling --base_lr 2e-4
```

実効学習率 = base_lr × (effective_batch_size / 16)

### 手動設定

```bash
--learning_rate 8e-4  # 4 GPUs, batch_size=8の場合
```

## メモリ最適化

### Mixed Precision Training

```bash
--precision 16-mixed
```

### Gradient Accumulation

```bash
--accumulate_grad_batches 2
```

## テスト手順

### 1. ダミーデータセットでのテスト

```bash
python scripts/test_multi_gpu.py --create-dataset
python scripts/test_multi_gpu.py --num-gpus 2
```

### 2. 実際のデータセットでのテスト

```bash
# シングルGPUで動作確認
python -m piper_train --dataset-dir /path/to/dataset --devices 1 --fast_dev_run

# マルチGPUで動作確認
python -m piper_train --dataset-dir /path/to/dataset --devices 2 --strategy ddp --fast_dev_run
```

## トラブルシューティング

### よくある問題

1. **CUDA Out of Memory**
   - batch_sizeを小さくする
   - `--precision 16-mixed`を使用
   - `--accumulate_grad_batches`を使用

2. **DataLoader関連エラー**
   - `--num-workers`を調整
   - `--persistent_workers`を無効化

3. **DDP初期化エラー**
   - ファイアウォール設定を確認
   - `NCCL_DEBUG=INFO`環境変数で詳細ログ

### デバッグ環境変数

```bash
export NCCL_DEBUG=INFO
export TORCH_DISTRIBUTED_DEBUG=INFO
```

## パフォーマンス監視

### GPU使用率確認

```bash
nvidia-smi -l 1
```

### ログ確認

```bash
# 学習ログ
tail -f lightning_logs/version_*/events.out.tfevents.*

# DDP通信ログ
grep "DDP" training.log
```

## ベンチマーク例

| GPUs | Batch Size | Effective LR | Training Time (1000 epochs) |
|------|------------|--------------|------------------------------|
| 1    | 16         | 2e-4         | ~48 hours                    |
| 2    | 8×2        | 4e-4         | ~24 hours                    |
| 4    | 8×4        | 8e-4         | ~12 hours                    |
| 8    | 4×8        | 8e-4         | ~6 hours                     |

*上記は参考値です。実際の性能は環境とデータセットに依存します。

## 高度な設定

### カスタム戦略

FSDP（Fully Sharded Data Parallel）を使用する場合：

```bash
--strategy fsdp --precision 16-mixed
```

注意: FSSDPは大型モデルに適していますが、VITSでは通常DDPで十分です。