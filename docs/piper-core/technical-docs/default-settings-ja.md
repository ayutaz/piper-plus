# デフォルト設定について

## 概要

v3実装では、品質向上に寄与し、副作用が少ない機能をデフォルトで有効にしています。

## デフォルトで有効な機能

### 1. EMA (Exponential Moving Average) ✅
- **理由**: 学習の安定性向上、推論時の品質向上
- **副作用**: ほぼなし（わずかなメモリ使用増加のみ）
- **無効化**: `--no-ema`

### 2. STFT Discriminator ✅
- **理由**: 音声品質の大幅な向上（特に高周波成分）
- **副作用**: 学習時間が約1.2倍
- **無効化**: `--no-stft-discriminator`

### 3. Duration Regularization ✅
- **理由**: 音声の長さの安定性向上
- **副作用**: ほぼなし
- **無効化**: `--no-duration-regularization`

### 4. Conditional Flow Matching ✅
- **理由**: より安定した学習、品質向上
- **副作用**: 推論がわずかに遅い（約1.1倍）
- **無効化**: `--no-flow-matching`

## デフォルトで無効な機能

### 1. WavLM Discriminator ❌
- **理由**: メモリ使用量が大きい（+1.5GB）、学習が遅い（約1.5倍）
- **有効化**: `--use-wavlm-discriminator`
- **推奨**: 高品質が必要な場合は有効化

### 2. Japanese BERT Encoder ❌
- **理由**: 日本語専用、メモリ使用量増加（+500MB）
- **有効化**: `--use-bert-encoder`
- **推奨**: 日本語音声合成では有効化を推奨

## 推奨設定

### 標準品質（デフォルト）
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --accelerator gpu \
    --devices 1
```

### 高品質（日本語）
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --accelerator gpu \
    --devices 1 \
    --quality high \
    --gin-channels 768 \
    --use-bert-encoder \
    --use-wavlm-discriminator
```

### 最高品質（全機能有効）
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --accelerator gpu \
    --devices 1 \
    --quality high \
    --gin-channels 768 \
    --use-bert-encoder \
    --bert-weight 0.3 \
    --use-wavlm-discriminator \
    --wavlm-weight 0.5 \
    --batch-size 16 \
    --precision 16
```

### 低メモリ環境
```bash
python -m piper_train \
    --dataset-dir /path/to/dataset \
    --accelerator gpu \
    --devices 1 \
    --quality x-low \
    --batch-size 8 \
    --no-flow-matching \
    --no-stft-discriminator
```

## パフォーマンス影響

### デフォルト設定での影響
- **学習時間**: 基本設定の約1.3倍
- **メモリ使用**: +200MB程度
- **推論速度**: 約1.1倍遅い
- **品質向上**: MOS +0.15-0.25

### 全機能有効時の影響
- **学習時間**: 基本設定の約2.5倍
- **メモリ使用**: +2GB
- **推論速度**: 約1.2倍遅い（BERT事前計算時）
- **品質向上**: MOS +0.77-1.26

## 設定の選び方

1. **プロトタイピング**: デフォルト設定で開始
2. **本番用モデル**: 言語に応じて追加機能を有効化
3. **研究/評価用**: 全機能有効で最高品質を追求

## 注意事項

- WavLMとBERTを同時に有効にする場合は、十分なGPUメモリ（16GB以上推奨）が必要
- バッチサイズは環境に応じて調整が必要
- 日本語以外の言語ではBERTエンコーダーは使用不可