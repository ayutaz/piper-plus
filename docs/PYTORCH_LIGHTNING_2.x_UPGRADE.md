# PyTorch Lightning 2.x Upgrade Guide

## 概要
このドキュメントは、Piper TTSのPyTorch Lightningを1.9.5から2.xへアップグレードするためのガイドです。

## なぜアップグレードすべきか

1. **PyTorch 2.xとの互換性向上**
   - PiperはすでにPyTorch 2.7.0を使用
   - PyTorch Lightning 2.xの方が相性が良い

2. **長期サポート**
   - 1.9.xは開発終了
   - 2.xが現在の安定版

3. **パフォーマンス向上**
   - マルチGPU学習の効率化
   - PyTorch 2.xの最適化機能をフル活用

4. **破壊的変更が少ない**
   - 主な変更点は引数パースのみ
   - 移行作業は2-3時間程度

## 破壊的変更と対応方法

### 1. Trainer.from_argparse_args() の削除

**現在のコード（1.9.5）:**
```python
# src/python/piper_train/__main__.py
parser = pl.Trainer.add_argparse_args(parser)
# ...
trainer = pl.Trainer.from_argparse_args(args)
```

**新しいコード（2.x）:**
```python
# オプション1: 手動でTrainerを初期化
def create_trainer_from_args(args):
    trainer_kwargs = {}
    
    # 必要な引数を手動でマッピング
    if hasattr(args, 'accelerator'):
        trainer_kwargs['accelerator'] = args.accelerator
    if hasattr(args, 'devices'):
        trainer_kwargs['devices'] = args.devices
    if hasattr(args, 'max_epochs'):
        trainer_kwargs['max_epochs'] = args.max_epochs
    if hasattr(args, 'precision'):
        trainer_kwargs['precision'] = args.precision
    if hasattr(args, 'accumulate_grad_batches'):
        trainer_kwargs['accumulate_grad_batches'] = args.accumulate_grad_batches
    if hasattr(args, 'gradient_clip_val'):
        trainer_kwargs['gradient_clip_val'] = args.gradient_clip_val
    
    # マルチGPU対応（前述のガイドと統合）
    if hasattr(args, 'strategy') and args.strategy:
        if args.strategy == 'ddp' and args.devices > 1:
            from pytorch_lightning.strategies import DDPStrategy
            trainer_kwargs['strategy'] = DDPStrategy(
                find_unused_parameters=True,
                gradient_as_bucket_view=True,
                static_graph=False
            )
        else:
            trainer_kwargs['strategy'] = args.strategy
    
    return pl.Trainer(**trainer_kwargs)

# オプション2: LightningCLIを使用（より高度）
from pytorch_lightning.cli import LightningCLI

# CLIベースの実装（より大きな変更が必要）
```

### 2. インポートの更新

**現在:**
```python
import pytorch_lightning as pl
from pytorch_lightning import Trainer
```

**新しい（変更なし、ただし警告が出る場合）:**
```python
import pytorch_lightning as pl
from pytorch_lightning import Trainer
# 必要に応じて警告を無視
import warnings
warnings.filterwarnings("ignore", ".*Consider switching to.*")
```

## 実装手順

### ステップ1: 依存関係の更新

1. **requirements.txt の更新:**
```bash
# メインのrequirements.txt
- pytorch-lightning==1.9.5
+ pytorch-lightning>=2.0.0,<3.0.0

# src/python/requirements.txt
- pytorch-lightning~=1.7.0
+ pytorch-lightning>=2.0.0,<3.0.0
```

2. **依存関係の確認:**
```bash
# 仮想環境で実行
pip install --upgrade pytorch-lightning>=2.0.0,<3.0.0
pip check  # 依存関係の競合をチェック
```

### ステップ2: コードの修正

**src/python/piper_train/__main__.py の修正:**
```python
import argparse
import sys
from pathlib import Path
import pytorch_lightning as pl
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import ModelCheckpoint

# ... その他のインポート ...

def create_trainer_from_args(args):
    """PyTorch Lightning 2.x 用のTrainer作成関数"""
    trainer_kwargs = {
        'default_root_dir': args.default_root_dir if hasattr(args, 'default_root_dir') else None,
        'max_epochs': args.max_epochs if hasattr(args, 'max_epochs') else 1000,
        'enable_checkpointing': True,
        'logger': True,
    }
    
    # デバイス設定
    if hasattr(args, 'accelerator'):
        trainer_kwargs['accelerator'] = args.accelerator
    if hasattr(args, 'devices'):
        trainer_kwargs['devices'] = args.devices
    
    # 精度設定
    if hasattr(args, 'precision'):
        trainer_kwargs['precision'] = args.precision
    
    # 勾配設定
    if hasattr(args, 'accumulate_grad_batches'):
        trainer_kwargs['accumulate_grad_batches'] = args.accumulate_grad_batches
    if hasattr(args, 'gradient_clip_val'):
        trainer_kwargs['gradient_clip_val'] = args.gradient_clip_val
    
    # マルチGPU対応
    if hasattr(args, 'devices') and args.devices > 1:
        from pytorch_lightning.strategies import DDPStrategy
        trainer_kwargs['strategy'] = DDPStrategy(
            find_unused_parameters=True,
            gradient_as_bucket_view=True,
            static_graph=False
        )
        trainer_kwargs['sync_batchnorm'] = True
        trainer_kwargs['use_distributed_sampler'] = True  # 2.xでの新しいオプション
    
    # コールバック
    callbacks = []
    if hasattr(args, 'checkpoint_epochs') and args.checkpoint_epochs > 0:
        callbacks.append(
            ModelCheckpoint(
                every_n_epochs=args.checkpoint_epochs,
                save_last=True,
                save_top_k=3,
                monitor='val/loss' if hasattr(args, 'val_split') else None
            )
        )
    
    if callbacks:
        trainer_kwargs['callbacks'] = callbacks
    
    return Trainer(**trainer_kwargs)

def main():
    parser = argparse.ArgumentParser()
    
    # Piper固有の引数
    parser.add_argument("--dataset-dir", required=True, help="Path to dataset directory")
    parser.add_argument("--checkpoint-epochs", type=int, default=1)
    parser.add_argument("--quality", default="medium")
    
    # Trainer引数を手動で追加（以前はadd_argparse_argsが行っていた）
    parser.add_argument("--accelerator", default="auto", help="Accelerator to use")
    parser.add_argument("--devices", type=int, default=1, help="Number of devices")
    parser.add_argument("--max-epochs", type=int, default=1000, help="Maximum epochs")
    parser.add_argument("--precision", type=str, default="32", help="Training precision")
    parser.add_argument("--accumulate-grad-batches", type=int, default=1)
    parser.add_argument("--gradient-clip-val", type=float, default=None)
    parser.add_argument("--strategy", type=str, default=None, help="Training strategy")
    
    args = parser.parse_args()
    
    # Trainerの作成（新しい方法）
    trainer = create_trainer_from_args(args)
    
    # ... 残りのコード ...
```

### ステップ3: テスト

1. **基本的な動作確認:**
```bash
# シングルGPUでのテスト
python -m piper_train \
    --dataset-dir ./test_data \
    --max-epochs 1 \
    --devices 1

# マルチGPUでのテスト（利用可能な場合）
python -m piper_train \
    --dataset-dir ./test_data \
    --max-epochs 1 \
    --devices 2 \
    --strategy ddp
```

2. **チェックポイントの互換性確認:**
```python
# 古いチェックポイントが読み込めることを確認
trainer.fit(model, ckpt_path="old_checkpoint.ckpt")
```

## 注意事項

1. **Python バージョン**
   - PyTorch Lightning 2.xはPython 3.8以上が必要
   - Python 3.7はサポート終了

2. **チェックポイントの互換性**
   - 1.9.xで保存したチェックポイントは2.xでも読み込み可能
   - ただし、念のためバックアップを推奨

3. **カスタムコールバック**
   - カスタムコールバックを使用している場合は、APIの変更を確認

## トラブルシューティング

### エラー: "No module named 'pytorch_lightning.utilities.distributed'"
```python
# 2.xでは場所が変更
# 旧: from pytorch_lightning.utilities.distributed import rank_zero_only
# 新: from pytorch_lightning.utilities import rank_zero_only
```

### 警告: "LightningModule.configure_optimizers` returned `None`"
```python
# 2.xではより厳密なチェック
# configure_optimizersが正しくオプティマイザーを返すことを確認
```

## まとめ

PyTorch Lightning 2.xへのアップグレードは：
- 作業量：2-3時間
- リスク：低
- メリット：高（長期サポート、パフォーマンス向上）

推奨される実装順序：
1. 開発環境でのテスト
2. 単体テストの実行
3. マルチGPU環境でのテスト
4. 本番環境への適用