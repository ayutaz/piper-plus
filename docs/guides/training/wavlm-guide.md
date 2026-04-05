# WavLM Discriminator ガイド

## 目次
- [概要](#概要)
- [学習時の使い方](#学習時の使い方)
- [ONNX変換](#onnx変換)
- [推論時の推奨設定](#推論時の推奨設定)
- [トラブルシューティング](#トラブルシューティング)

---

## 概要

WavLM Discriminator は Microsoft WavLM をベースにした知覚品質判別器です。通常の VITS 判別器に加えて、WavLM の特徴量を用いた追加の判別器として機能し、生成音声の知覚品質を向上させます。

### 主な特徴

| 項目 | 内容 |
|------|------|
| 期待効果 | MOS +0.15-0.25 向上 |
| デフォルト状態 | **有効** (特別な設定は不要) |
| 使用タイミング | 学習時のみ (推論グラフには含まれない) |
| 推論速度への影響 | なし |
| GPUメモリ追加 | 約1-2GB/GPU |
| 重み係数 (c_wavlm) | デフォルト 0.5 |
| FP16 対応 | 対応済み (内部でfloat32変換) |

### 実装ファイル

| ファイル | 内容 |
|----------|------|
| `src/python/piper_train/vits/models.py` | `WavLMDiscriminator` クラス |
| `src/python/piper_train/vits/lightning.py` | 学習ループへの統合 |

---

## 学習時の使い方

### 基本的な使い方

WavLM Discriminator はデフォルトで有効なため、特別なフラグは不要です。通常の学習コマンドをそのまま実行できます。

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /path/to/output
```

> **⚠️ 注意:** V100 GPU では `--precision 16-mixed` は backward pass が極端に遅くなる問題があります。V100 では `--precision 32-true` を推奨します。A100 以降の GPU では `16-mixed` が利用可能です。

WavLM が有効な場合、GPUメモリが約1-2GB増加するため、`--batch-size` を従来より下げる必要がある場合があります（例: 20 → 12）。

### WavLM を無効化する場合

WavLM を完全に無効化するには `--no-wavlm` を指定します。モデルの読み込み自体がスキップされるため、GPU メモリが約1-2GB 節約されます。

```bash
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --no-wavlm \
  ...
```

損失重みのみをゼロにする場合は `--c-wavlm 0` を指定しますが、この場合 WavLM モデル自体は GPU メモリに読み込まれたままです。メモリ節約が目的の場合は `--no-wavlm` を使用してください。

```bash
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --c-wavlm 0 \
  ...
```

### c_wavlm パラメータの調整

`--c-wavlm` は WavLM 判別器の損失に対する重み係数です。値を変更することで WavLM の影響度を調整できます。

| 値 | 用途 |
|----|------|
| `0.5` (デフォルト) | 標準的な学習 |
| `0.2` | 音割れ(クリッピング)が発生する場合の緩和策 |
| `0` | WavLM 損失を無効化（メモリ節約には `--no-wavlm` 推奨） |

c_wavlm を下げて再学習する例:

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --c-wavlm 0.2 \
  --default_root_dir /path/to/output
```

---

## ONNX変換

デフォルトのエクスポートで stochastic モード（`noise_scale` によるサンプリング有効）+ EMA 重み適用が有効です。WavLM で学習したモデルはそのまま変換できます。

EMA 重みはチェックポイントに存在すれば自動適用されるため、明示的に指定する必要はありません。

### WavLM モデルの変換

```bash
# デフォルト: stochastic + EMA（推奨）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

deterministic エクスポート（デバッグ用）が必要な場合は `--no-stochastic` を使用します:

```bash
# deterministic（デバッグ用）
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
  --no-stochastic \
  /path/to/checkpoint.ckpt \
  /path/to/output.onnx
```

### エクスポートオプション一覧

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--no-stochastic` | - | noise_scale サンプリングを無効化（デバッグ用） |
| `--no-fp16` | - | FP16 変換を無効化（デフォルト: FP16 有効、モデルサイズ~50%削減） |
| EMA | (EMA state があれば適用) | チェックポイントに EMA state があれば自動適用 |

変換時は `CUDA_VISIBLE_DEVICES=""` を指定して CPU モードで実行することを推奨します。

---

## 推論時の推奨設定

WavLM で学習したモデルでは、`--noise-scale 0.5` を推奨します（デフォルト: 0.667）。`noise_scale` を下げることで発音がより安定します。

### Python 推論

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/wavlm-model.onnx \
  --config /path/to/config.json \
  --output-dir /path/to/output \
  --text "こんにちは、今日は良い天気ですね。" \
  --speaker-id 0 --noise-scale 0.5
```

### C++ CLI 推論

```bash
echo "こんにちは" | ./piper --model model.onnx --noise_scale 0.5 --output_file out.wav
```

### noise_scale の調整目安

| 値 | 特性 |
|----|------|
| `0.667` (デフォルト) | 標準的な変動。WavLM モデルでは音割れが発生する可能性あり |
| `0.5` (推奨) | WavLM モデル向けの推奨値。安定した発音 |
| `0.3` | より安定。音割れが解消しない場合に試す |

---

## トラブルシューティング

### 音割れ（クリッピング）が発生する場合

WavLM Discriminator により高振幅音声が生成される傾向があります。WavLM なしのモデルでは発生しない場合、以下の対処法を順に試してください。

**対処法1: 学習を継続する**

200 epoch 以降で改善することがあります。まずは学習を完了させてから判断してください。

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --default_root_dir /path/to/output \
  --resume_from_checkpoint /path/to/last.ckpt
```

**対処法2: c_wavlm を下げて再学習する**

`--c-wavlm` を 0.5 から 0.2 に下げることで、WavLM の影響を緩和しつつ品質向上の恩恵を受けられます。

```bash
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
uv run python -m piper_train \
  --dataset-dir /path/to/dataset \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 16-mixed \
  --max_epochs 200 --batch-size 12 --samples-per-speaker 2 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 0 --no-pin-memory \
  --c-wavlm 0.2 \
  --default_root_dir /path/to/output-cwavlm02
```

**対処法3: 推論時に noise_scale を下げる**

学習済みモデルを変更せずに、推論時のパラメータで対処する方法です。

```bash
CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.infer_onnx \
  --model /path/to/wavlm-model.onnx \
  --config /path/to/config.json \
  --output-dir /path/to/output \
  --text "テストテキスト" \
  --speaker-id 0 --noise-scale 0.3
```

### GPUメモリ不足 (OOM)

WavLM は約1-2GB/GPU の追加メモリを必要とします。OOM が発生する場合は以下の対処法を試してください。

**対処法1: batch-size を下げる**

```bash
uv run python -m piper_train \
  --batch-size 12 \   # 例: 20 → 12 に削減
  ...
```

**対処法2: WavLM の損失重みをゼロにする**

`--c-wavlm 0` で WavLM の損失への寄与をゼロにできます。

```bash
uv run python -m piper_train \
  --c-wavlm 0 \
  --batch-size 12 \
  ...
```

> **注意**: `--c-wavlm 0` は損失重みをゼロにするだけで、WavLM モデル自体は GPU メモリに残ります（約1-2GB）。完全にモデルの読み込みを無効化するには `--no-wavlm` を使用してください。

**GPU メモリの目安:**

| 構成 | WavLM あり (c_wavlm > 0) | WavLM あり (c_wavlm = 0) | 備考 |
|------|--------------------------|--------------------------|------|
| batch-size 12 | 約14-15 GB | 約14-15 GB | c_wavlm=0 でもモデルは読み込まれる |
| batch-size 20 | 約18-20 GB | 約18-20 GB | batch-size の調整で対処 |

上記は medium quality、FP16 Mixed Precision 有効時の目安です。実際の使用量はデータセットや発話長により変動します。
