# Multi-GPU Training Guide for Piper VITS

このガイドでは、Piper VITSでマルチGPU学習を行う方法について説明します。大規模データセット（600時間〜2000時間）での事前学習を含む、効率的なマルチGPU学習の設定方法とハードウェア推奨構成を説明します。

## 目次
- [前提条件](#前提条件)
- [ハードウェア推奨構成](#ハードウェア推奨構成)
- [データセット規模別の設定](#データセット規模別の設定)
- [基本的な使用方法](#基本的な使用方法)
- [パフォーマンス最適化](#パフォーマンス最適化)
- [トラブルシューティング](#トラブルシューティング)

## 前提条件

- PyTorch Lightning 2.x以上
- 複数のGPU環境
- CUDA対応環境

## ハードウェア推奨構成

### GPU選択基準とコスト効率

| GPU | VRAM | 時間単価 | 用途 | コスト効率 |
|-----|------|----------|------|------------|
| L4 24GB | 24GB | ¥50 | 小-中規模学習、最高コスト効率 | ⭐⭐⭐⭐⭐ |
| A100 40GB | 40GB | ¥200 | 高性能学習 | ⭐⭐⭐ |
| A100 80GB | 80GB | ¥295 | 従来の大規模学習 | ⭐⭐ |

### データセット規模別推奨構成

#### 小規模データセット（～50時間、LJSpeech等）
```
推奨: L4 24GB × 2台
- コスト: ¥100/時間
- 学習時間: 1-3日
- A100 80GB比: 66%コスト削減
```

#### 中規模データセット（50-200時間、JVS等）
```
推奨: L4 24GB × 4台
- コスト: ¥200/時間  
- 学習時間: 3-7日
- A100 80GB比: 32%コスト削減、2.5倍高速
```

#### 大規模データセット（600-2000時間、事前学習）
```
推奨: L4 24GB × 8台
- コスト: ¥400/時間
- 学習時間: 10-30日（2000時間データセット）
- A100 80GB比: 55%コスト削減、3倍高速
```

### 大規模データセットでのコスト比較

#### 2000時間データセット事前学習
```
A100 80GB × 1台:
- 学習時間: 90日 (2160時間)
- コスト: 2160 × ¥295 = ¥637,200

L4 × 8台:
- 学習時間: 30日 (720時間)
- コスト: 720 × ¥400 = ¥288,000
- 削減額: ¥349,200（55%削減）
- 高速化: 3倍
```

#### 600時間データセット事前学習
```
A100 80GB × 1台:
- 学習時間: 30日 (720時間)
- コスト: 720 × ¥295 = ¥212,400

L4 × 8台:
- 学習時間: 12日 (288時間)
- コスト: 288 × ¥400 = ¥115,200
- 削減額: ¥97,200（46%削減）
- 高速化: 2.5倍
```

## データセット規模別の設定

### 小規模データセット（LJSpeech、個人音声等）
```bash
# L4 24GB × 2台での最適設定
python -m piper_train \
    --dataset-dir /path/to/ljspeech \
    --accelerator gpu \
    --devices 2 \
    --strategy ddp \
    --batch-size 40 \               # GPU毎40、合計80
    --precision 16-mixed \
    --num-workers 8 \               # GPU毎4ワーカー
    --gradient_clip_val 1.0 \
    --max_epochs 2000 \
    --checkpoint-epochs 100
```

### 中規模データセット（JVS、CSS10等）
```bash
# L4 24GB × 4台での最適設定
python -m piper_train \
    --dataset-dir /path/to/jvs \
    --accelerator gpu \
    --devices 4 \
    --strategy ddp \
    --batch-size 28 \               # GPU毎28、合計112
    --precision 16-mixed \
    --num-workers 16 \              # GPU毎4ワーカー
    --gradient_clip_val 1.0 \
    --max_epochs 1500 \
    --checkpoint-epochs 50
```

### 大規模データセット（600時間以上の事前学習）
```bash
# L4 24GB × 8台での最適設定
python -m piper_train \
    --dataset-dir /path/to/large_dataset \
    --accelerator gpu \
    --devices 8 \
    --strategy ddp \
    --batch-size 30 \               # GPU毎30、合計240
    --precision 16-mixed \
    --num-workers 32 \              # GPU毎4ワーカー
    --gradient_clip_val 1.0 \
    --max_epochs 1000 \             # 大規模データは少ないエポック数
    --checkpoint-epochs 25 \
    --save-top-k 3                  # 上位3個のチェックポイントを保持
```

### GPU数によるスケーリング効率
```
GPU数    理論速度    実際の速度向上    効率    推奨用途
1        1.0x        1.0x            100%    テスト・小規模
2        2.0x        1.6-1.8x        80-90%  小規模データセット
4        4.0x        2.5-3.2x        65-80%  中規模データセット
8        8.0x        3.5-4.5x        45-55%  大規模データセット
```

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
    --precision 16-mixed
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


### VRAM断片化対策

長時間の学習でVRAMが断片化してOOMエラーが発生する場合:

```bash
# PyTorchのメモリアロケータを最適化
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

この環境変数により:
- メモリの断片化を削減
- 長時間学習での安定性向上
- チェックポイント保存時のOOM回避

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
   - VRAM断片化対策として環境変数を設定:
     ```bash
     export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
     ```

2. **ONNX変換時のCUDAデバイスエラー**
   マルチGPU学習で作成されたチェックポイントをONNX変換する際、デバイス不一致エラーが発生する場合:
   ```bash
   # CUDAを無効化してCPUで変換
   CUDA_VISIBLE_DEVICES="" python3 -m piper_train.export_onnx \
     /path/to/checkpoint.ckpt \
     /path/to/output.onnx
   ```
   
   **原因**: マルチGPU学習のチェックポイントには複数のGPU情報が含まれ、ONNX変換時にデバイス混在が発生

3. **DataLoader関連エラー**
   - `--num-workers`を調整
   - `--persistent_workers`を無効化

4. **DDP初期化エラー**
   - ファイアウォール設定を確認
   - `NCCL_DEBUG=INFO`環境変数で詳細ログ

### デバッグ環境変数

```bash
export NCCL_DEBUG=INFO
export TORCH_DISTRIBUTED_DEBUG=INFO
```

## VRAM使用量とバッチサイズ最適化

### L4 24GB での推奨バッチサイズ
```
データ特性別の推奨バッチサイズ:
- 通常発話（平均3-5秒）: 16-20 per GPU
- 長い発話多数（5-10秒）: 10-14 per GPU  
- 非常に長い発話（10秒以上）: 6-10 per GPU
- max_phoneme_ids 400使用時: 最大20 per GPU
```

### VRAM使用量の目安
```
L4 24GB での実際の使用量:
- batch_size 20 + precision 16-mixed: ~20GB使用
- batch_size 16 + precision 32: ~22GB使用
- batch_size 10 + precision 32: ~18GB使用
```

### バッチサイズ決定のコツ
1. 小さなバッチサイズから開始（8-10）
2. OOMが発生しない最大サイズを見つける
3. 複数GPUで実効バッチサイズを調整

```bash
# 例: GPU毎batch_size 32で実効128を実現  
--batch-size 32  # 32×4GPU = 128
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