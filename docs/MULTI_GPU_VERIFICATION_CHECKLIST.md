# Multi-GPU Verification Checklist

このドキュメントは、Piper VITSのマルチGPU実装の動作確認を行う際のチェックリストです。

## 環境確認

### 1. GPU環境の確認
- [ ] GPUの台数確認
  ```bash
  nvidia-smi
  ```
- [ ] CUDA版確認
  ```bash
  nvcc --version
  ```
- [ ] PyTorchのGPU認識確認
  ```bash
  python -c "import torch; print(f'GPU count: {torch.cuda.device_count()}')"
  ```

### 2. 依存関係の確認
- [ ] PyTorch Lightning 2.x以上
  ```bash
  python -c "import pytorch_lightning as pl; print(pl.__version__)"
  ```
- [ ] NCCL通信ライブラリ
  ```bash
  python -c "import torch.distributed as dist; print('NCCL available')"
  ```

## 基本動作確認

### 3. シングルGPU動作確認
- [ ] 通常の学習が動作することを確認
  ```bash
  python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 16 \
    --devices 1 \
    --max_epochs 1 \
    --fast_dev_run
  ```

### 4. マルチGPU初期化確認
- [ ] DDP戦略での起動確認
  ```bash
  python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 16 \
    --devices 2 \
    --strategy ddp \
    --max_epochs 1 \
    --fast_dev_run
  ```
- [ ] プロセス起動ログの確認（GPU数分のプロセスが起動）
- [ ] NCCL初期化成功の確認

## 機能別確認

### 5. 学習率自動スケーリング
- [ ] `--auto_lr_scaling`オプションの動作確認
  ```bash
  python -m piper_train \
    --dataset-dir /path/to/dataset \
    --batch-size 8 \
    --devices 2 \
    --strategy ddp \
    --auto_lr_scaling \
    --base_lr 2e-4 \
    --max_epochs 1 \
    --fast_dev_run
  ```
- [ ] ログで学習率スケーリングメッセージ確認
  - 期待値: "Auto-scaled learning rate from 2e-4 to 4e-4 for 2 GPUs"

### 6. データ並列処理
- [ ] 各GPUに異なるバッチが配分されることを確認
- [ ] DataLoaderのワーカー数が自動調整されることを確認
- [ ] `pin_memory`と`persistent_workers`が有効化されていることを確認

### 7. 勾配同期
- [ ] 各ステップで勾配が同期されることを確認
- [ ] ログで同期タイミングを確認
  ```bash
  export NCCL_DEBUG=INFO
  python -m piper_train ... 2>&1 | grep NCCL
  ```

## パフォーマンス確認

### 8. 速度向上確認
- [ ] 1 GPU vs 2 GPUの学習速度比較
  ```bash
  # 1 GPU
  time python -m piper_train --devices 1 --max_epochs 10 ...
  
  # 2 GPUs
  time python -m piper_train --devices 2 --strategy ddp --max_epochs 10 ...
  ```
- [ ] 理想的には1.5-1.8倍の速度向上

### 9. GPU使用率確認
- [ ] 両GPUが効率的に使用されていることを確認
  ```bash
  nvidia-smi dmon -s u -d 1
  ```
- [ ] GPU使用率が70%以上であることを確認

### 10. メモリ使用量確認
- [ ] 各GPUのメモリ使用量がほぼ均等であることを確認
  ```bash
  nvidia-smi --query-gpu=memory.used --format=csv -l 1
  ```

## エラーハンドリング確認

### 11. 異常系テスト
- [ ] 1つのGPUが利用不可の場合のエラーメッセージ確認
- [ ] バッチサイズがGPU数で割り切れない場合の動作確認
- [ ] OOM（Out of Memory）発生時の適切なエラーメッセージ

### 12. チェックポイント機能
- [ ] マルチGPU学習のチェックポイント保存
- [ ] チェックポイントからの再開（resume）
  ```bash
  python -m piper_train \
    --resume_from_checkpoint /path/to/checkpoint \
    --devices 2 \
    --strategy ddp
  ```

## 高度な確認項目

### 13. Mixed Precision Training
- [ ] `--precision 16-mixed`での動作確認
- [ ] メモリ使用量の削減確認
- [ ] 学習の安定性確認

### 14. Gradient Accumulation
- [ ] `--accumulate_grad_batches`との併用確認
  ```bash
  python -m piper_train \
    --devices 2 \
    --strategy ddp \
    --batch-size 4 \
    --accumulate_grad_batches 4
  ```

### 15. 異なるGPU構成
- [ ] 異なるメモリ容量のGPUでの動作（該当する場合）
- [ ] 3台以上のGPUでの動作確認（利用可能な場合）

## ログとモニタリング

### 16. TensorBoardログ確認
- [ ] 各GPUからのメトリクスが正しく集約されている
- [ ] 学習曲線が正常
  ```bash
  tensorboard --logdir lightning_logs/
  ```

### 17. システムモニタリング
- [ ] CPUボトルネックがないことを確認
- [ ] ネットワーク通信量の確認（GPU間通信）
- [ ] ディスクI/Oがボトルネックになっていないことを確認

## 最終確認

### 18. 本番相当の学習実行
- [ ] 実際のデータセットで数エポック学習
- [ ] 音声品質の確認（生成された音声が正常）
- [ ] シングルGPU学習と同等の品質であることを確認

## トラブルシューティング用コマンド

### デバッグ情報の取得
```bash
# 詳細なDDPログ
export NCCL_DEBUG=INFO
export TORCH_DISTRIBUTED_DEBUG=INFO

# GPU情報の詳細表示
nvidia-smi -q

# PyTorch環境情報
python -m torch.utils.collect_env
```

### よくある問題と対処法

1. **NCCL初期化エラー**
   - ファイアウォール設定確認
   - `export NCCL_SOCKET_IFNAME=lo`

2. **不均等なGPU使用率**
   - バッチサイズがGPU数の倍数か確認
   - DataLoaderのshuffle設定確認

3. **OOMエラー**
   - バッチサイズを削減
   - gradient_accumulation_stepsを使用
   - mixed precisionを有効化

---

## チェックリスト記入例

```
実施日: 2024-XX-XX
実施者: [名前]
環境: 
- GPU: Tesla T4 x 2
- CUDA: 12.4
- PyTorch: 2.5.1
- PyTorch Lightning: 2.5.2

結果:
- [x] GPU環境の確認 - OK
- [x] 依存関係の確認 - OK
- [x] シングルGPU動作確認 - OK
- [x] マルチGPU初期化確認 - OK
...
```

## 備考

- このチェックリストは基本的な確認項目です
- 環境や要件に応じて項目を追加/削除してください
- 問題が発生した場合は、ログとともに記録を残してください