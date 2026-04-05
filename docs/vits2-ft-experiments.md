# VITS2 実験記録 (2026-03-25 〜 2026-04-05)

## 概要

VITS2アーキテクチャで6言語ベースモデルを学習し、つくよみちゃん(100発話)へのシングルスピーカーFTを試行。
FT実験（gin256 v1-v5, gin512 v1-v3）およびベースモデル構成変更実験（B1, B2）を実施。
全構成でVITS1の品質を下回った。

**結論: VITS2は現時点の実装ではVITS1の品質に到達できていない。** Feature E (Mel Posterior Encoder) の個別検証でも品質劣化が確認され、VITS2固有機能は全て品質に悪影響を与える可能性が高い。

---

## 実験一覧

### FT実験

| # | ベース | gin_channels | 主要設定 | 結果 | 根本原因 |
|---|--------|-------------|---------|------|---------|
| gin256 v1 | VITS2 60ep | 256 | freeze-dp | duration 30-130%長い | frozen DPの特性 |
| gin256 v2 | VITS2 60ep | 256 | DurDisc + no-freeze-dp | 改善するも依然長い | DPの適応不足 |
| gin256 v3 | VITS2 60ep | 256 | warmup, cosine, keep-emb-g | 外国人っぽいJA発音 | emb_g_mean が全話者平均 |
| **gin256 v4** | VITS2 60ep | 256 | JA話者mean + no-freeze-dp + DurDisc | **ノイズ** | **~~容量不足~~ → speaker_cond_enc silent drop (誤診)** |
| **gin512 v1** | VITS2 60ep | 512 | Template D (no-freeze-dp, dp-lr, DurDisc) | 機械音 + 遅い | speaker_cond_enc無効 + DP過学習 |
| **gin512 v2** | VITS2 60ep | 512 | freeze-dp, speaker_cond_enc, 2-optimizer | 雑音 + 遅い | ベースモデルの高周波欠損 |
| **gin512 v3** | VITS2 200ep | 512 | (ベースモデルのみ、FTなし) | 水中感 (こもり) | conditioning比率過剰 |
| **gin256 v5** | VITS2 60ep | 256 | freeze-dp, speaker_cond_enc=True, 2-optimizer | 周波数はVITS1同等、だが速度・声質で劣る | frozen DP遅延 + VITS2固有の品質差 |
| **VITS1 FT** | VITS1 75ep | 512 | freeze-dp (auto), SDP, 2-optimizer | **品質OK (参照)** | — |

### ベースモデル構成変更実験 (2026-04-01 〜 2026-04-04)

FT品質の根本原因がベースモデルにあると判断し、ベースモデルの構成自体を変更して再検証。

| # | Posterior Encoder | gin_channels | LRスケジューラ | VITS2機能 | 結果 | 根本原因 |
|---|------------------|-------------|--------------|----------|------|---------|
| **B1** | Linear Spec (513ch) | 256 | ExponentialLR | DurDisc, speaker-cond enc, noise MAS | **hi-mid=-31.3, 全帯域で劣悪** | gin256がlinspec 513chに対して小さすぎ、prior-posterior KL乖離 |
| **B2** | Linear Spec (513ch) | 512 | ExponentialLR | DurDisc, speaker-cond enc, noise MAS | **hi-mid=-86.0 (JA), rms=0.072** | VITS2機能 (A-D) の複合的悪影響。学習step数もVITS1の49% |

### 個別機能検証実験 (2026-04-05)

VITS1ベースラインに1機能ずつ追加して影響を測定する短縮テスト (20 epoch)。

| # | 構成 | 追加機能 | 結果 | 根本原因 |
|---|------|---------|------|---------|
| **T-E** | VITS1 + `--mel-posterior-encoder` | Feature E のみ | **mid=-27.2dB, hi=-54.9dB, 全帯域NG** | 80ch mel入力では潜在表現の情報量不足、デコーダが高周波を学習不能 |

---

## 発見したバグ・誤診

### 1. TextEncoder cond_proj バグ (models.py:218)

**発見日:** 2026-03-26

`TextEncoder.forward()` が `g` を `self.encoder()` に渡していなかったため、`attentions.Encoder.cond_proj` (中間層speaker injection) が**一度も実行されていなかった**。

```python
# 修正前 (バグ): cond_proj が dead weight
x = self.encoder(x * x_mask, x_mask)

# 修正後: cond_proj が有効化
x = self.encoder(x * x_mask, x_mask, g=g)
```

- `cond_proj` の ~37K パラメータが dead weight だった
- VITS2論文の設計意図（中間層speaker injection）が未実装だった
- gin512 200ep ベースモデルはこの修正を適用して再学習
- **ただし、gin256ベースモデルは修正前のコードで学習されている**ため、gin256 FTでは修正を**revert**する必要がある

**現在の状態:** gin256 FTのためrevert済み。gin512で再学習する場合は修正を再適用すること。

### 2. gin256 v4「容量不足」誤診

**発見日:** 2026-03-30 (Agent調査で判明)

v4の「ノイズ」問題を「gin_channels=256の容量限界」と診断してgin512に移行したが、**これは誤りだった**。

**真の原因:** v4は `speaker_conditioned_encoder=False` でFTを実行したが、ベースモデルは `speaker_conditioned_encoder=True` で学習されていた。`strict=False` ロードにより `cond_layer` と `cond_proj` の重みが**silent drop**され、TextEncoderの学習済みconditioning経路が消失。

**根拠:**
- v4ログの Unexpected keys に `model_g.enc_p.cond_layer.weight`, `model_g.enc_p.encoder.cond_proj.weight` が含まれている
- gin512 v2 FTでは `speaker_conditioned_encoder=True` を使い、cond_layer/cond_projがロードされて部分的に成功
- gin256 v5 FTでも `speaker_conditioned_encoder=True` を使い、Missing keys=[] で正常ロード

**教訓:** `--resume-from-multispeaker-checkpoint` 使用時は、ベースモデルの `speaker_conditioned_encoder` 設定を必ず継承すること。

### 3. gin_channels自動設定の不整合

**発見日:** 2026-03-30

`__main__.py` がgin_channelsを常に512に自動設定するため、gin256ベースからのFTでshape mismatchエラーが発生。

**修正:** ベースチェックポイントからgin_channelsを継承する検出ロジックを追加。

```python
# 修正後: ベースモデルのgin_channelsを自動継承
base_ckpt_path = dict_args.get("resume_from_multispeaker_checkpoint")
if base_ckpt_path:
    _base = torch.load(base_ckpt_path, map_location="cpu", weights_only=False)
    dict_args["gin_channels"] = _base.get("hyper_parameters", {}).get("gin_channels", 512)
```

---

## gin512 ベースモデル品質問題の詳細調査

### 問題: 高周波欠損（水中感）

gin512ベースモデルは全epochを通じて高周波成分が著しく欠損。

**周波数帯域分析（同一テキスト「こんにちは、今日は良い天気ですね。」speaker 0）:**

| モデル | bass (100-1k) | mid (1-4k) | hi-mid (4-8k) | highs (8-11k) | RMS |
|--------|--------------|------------|---------------|---------------|-----|
| VITS1 Base (75ep, gin512) | +40.8 | +26.5 | **+11.0** | **+3.1** | 0.201 |
| VITS2 gin256 Base (60ep) | +41.7 | +25.8 | **+11.2** | **+5.3** | 0.204 |
| VITS2 gin512 Base v1 (60ep) | +35.6 | +16.3 | **-21.1** | **-17.7** | 0.086 |
| VITS2 gin512 Base v2 (200ep) | +35.6 | +23.4 | **-2.7** | **-29.8** | 0.104 |
| VITS2 gin512 Base v2 (g*0.5) | +40.3 | +28.6 | **+17.5** | **+6.9** | 0.163 |

### 原因1: CosineAnnealingLR + 大パラメータ数 = 有効学習不足

| 指標 | VITS1 gin512 | VITS2 gin256 | VITS2 gin512 |
|------|-------------|-------------|--------------|
| パラメータ数 | 77.6M | 38.9M | 77.1M |
| LRスケジューラ | ExponentialLR (γ=0.999875) | CosineAnnealingLR | CosineAnnealingLR |
| 有効epoch数 (LR > 1e-5) | **75** | **52** | **52** |
| 有効ステップ数 | **505,000** | 172,000 | 172,000 |
| ステップ/パラメータ | **6.5** | **4.4** | **2.2** |

ExponentialLR(γ=0.999875)はLR≒0.0002を全epoch維持。CosineAnnealingLRはepoch 50でLR≒0.000015に低下。
gin512のパラメータあたり有効ステップは2.2で、gin256の半分、VITS1の1/3。

**対策:** gin512を200 epochで再学習（v2）。有効ステップは~564Kに増加したが、高周波問題は改善されず。

### 原因2: デコーダのconditioning/acoustic比率が2倍過剰

**デコーダ信号比率の実測値:**

| モデル | cond/conv_pre比 | dec.cond weight norm |
|--------|----------------|---------------------|
| VITS1 gin512 | **2.97** | 38.10 |
| VITS2 gin256 | **2.90** | 12.88 |
| VITS2 gin512 (60ep) | **6.00** | 15.73 |
| VITS2 gin512 (200ep) | **6.16** | **25.64** |

- gin512のconditioning比率はVITS1/gin256の**約2倍**
- **学習が進むほどdec.cond weight normが肥大化** (15.73→25.64)、問題が悪化
- g*0.5でconditioning比率を~3に下げると高周波が回復（hi-mid: -2.7→+17.5）
- ただしg*0.5でも知覚品質はVITS1に劣る（水中感は改善するが声質が不自然）

### 原因3: Epoch比較 — 学習が進むほど高周波が劣化

| Epoch | hi-mid | highs | 備考 |
|-------|--------|-------|------|
| 99 | **+3.5** | -13.8 | ベスト |
| 149 | -3.1 | -13.2 | |
| 199 | -2.7 | **-25.0** | 最悪 |

デコーダがconditioningに依存する度合いが学習とともに増大し、音響信号の高周波成分が相対的に埋没。

### gin512で試した対策とその結果

| 対策 | 結果 |
|------|------|
| 200 epochに延長 | hi-mid改善 (-21→-2.7) だが依然不十分 |
| FP32 ONNX (FP16無効) | 変化なし |
| EMA無効 | 変化なし |
| noise_scale=0.0 (deterministic) | 音声長変化なし、品質変化なし |
| cond_proj ゼロ化 | hi-mid微改善 (-2.7→+5.7)、highs変化なし |
| **g vector * 0.5** | **hi-mid: +17.5、highs: +6.9** (周波数回復だが知覚品質はVITS1に劣る) |
| length_scale=0.8 | 音声長のみ短縮 (2.83s→1.93s) |

### VITS1 gin512 が成功する理由

VITS1とVITS2はgin_channelsの使い方は同じだが、以下の違いが品質差を生む:

1. **Posterior Encoder入力**: VITS1は513ch (linear spec)、VITS2は80ch (mel spec) → 学習中の潜在空間の品質に影響
2. **TextEncoder conditioning**: VITS1は1箇所、VITS2は2箇所 (cond_proj + cond_layer) → over-conditioning
3. **Duration Predictor**: VITS1はSDP (確率的)、VITS2はDP (決定的) → frozen時の速度差
4. **Embedding norms**: VITS2の emb_g/emb_lang は VITS1より27-57%高い → conditioning信号が強い
5. **ExponentialLR vs CosineAnnealingLR**: VITS1は全epoch LR≒0.0002維持、VITS2は後半ほぼ0

---

## gin256 v5 FT (2026-03-30)

v4の真の失敗原因（speaker_conditioned_encoder silent drop）を修正してgin256で再FT。

### 設定

```bash
export WANDB_API_KEY=$(grep WANDB_API_KEY /data/piper/.env | cut -d= -f2) && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
CUDNN_BENCHMARK=0 TORCH_CUDNN_V8_API_DISABLED=1 \
nohup uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-tsukuyomi-finetune-6lang \
  --prosody-dim 16 \
  --accelerator gpu --devices 1 --precision 32-true \
  --max_epochs 500 --batch-size 4 --samples-per-speaker 4 \
  --checkpoint-epochs 50 --quality medium \
  --base_lr 2e-5 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --val-every-n-epochs 50 \
  --audio-log-epochs 50 \
  --mas-noise-start 0 \
  --mel-posterior-encoder \
  --no-sdp \
  --speaker-conditioned-encoder \
  --keep-emb-g \
  --resume-from-multispeaker-checkpoint \
    /data/piper/output-vits2-6lang/checkpoints/epoch=59-step=198855.ckpt \
  --default_root_dir /data/piper/output-tsukuyomi-finetune-vits2-gin256 \
  > /data/piper/training_tsukuyomi_vits2_gin256.log 2>&1 &
```

### v4との主な違い

| 設定 | v4 (失敗) | v5 |
|------|-----------|-----|
| `speaker_conditioned_encoder` | **False (根本原因)** | **True** |
| `freeze_dp` | False (no-freeze-dp) | **True (auto)** |
| `use_duration_discriminator` | True (3-optimizer) | **False (2-optimizer)** |
| `dp_lr` | 1e-4 | なし (DPは凍結) |
| `cosine_scheduler` | True | **False** |
| `warmup_epochs` | 3 | **0** |
| Missing keys at load | [] | [] |
| Unexpected keys | **cond_layer, cond_proj** (silent drop!) | emb_g, DurDisc のみ (想定通り) |

### v5の設計思想

「VITS1の成功レシピをVITS2アーキテクチャフラグで再現」

- freeze-dp (auto) — VITS1と同じ
- 2-optimizer (G+D) — VITS1と同じ
- cosine/warmup なし — VITS1と同じ
- speaker_conditioned_encoder=True — **ベースモデルと一致させる (v4の修正)**
- keep-emb-g — JA話者mean初期化

### 結果

| モデル | bass | mid | hi-mid | highs | RMS | 音声長 |
|--------|------|-----|--------|-------|-----|--------|
| **gin256 v5 FT** | **+41.8** | **+26.4** | **+12.4** | **+4.8** | **0.173** | 2.71s |
| VITS1 FT (参照) | +40.2 | +25.9 | +12.3 | +2.6 | 0.178 | 1.95s |

- **周波数特性はVITS1と完全に一致** (hi-mid: +12.4 vs +12.3)
- **ただし知覚品質ではVITS1が上** — 速度 (2.71s vs 1.95s) と声質の両方
- 速度差はfrozen deterministic DP (VITS2) vs frozen SDP (VITS1) の特性差
- 声質差はmel posterior encoder (80ch) vs linear spec (513ch) の情報量差が影響の可能性

### 推論結果

| 言語 | 音声長 | RTF |
|------|--------|-----|
| JA | 2.71s | 0.05 |
| EN | 1.67s | 0.14 |
| ZH | 1.60s | 0.07 |
| ES | 1.70s | 0.19 |
| FR | 1.74s | 0.13 |
| PT | 2.21s | 0.12 |

### ファイル

- チェックポイント: `output-tsukuyomi-finetune-vits2-gin256/checkpoints/epoch=499-step=22000.ckpt`
- 後処理済み: `output-tsukuyomi-finetune-vits2-gin256/checkpoints/epoch=499-step=22000-postprocessed.ckpt`
- ONNX (FP16): `output-tsukuyomi-finetune-vits2-gin256/tsukuyomi-vits2-gin256.onnx` (33.4 MB)

---

## gin512 v2 ベースモデル再学習 (2026-03-26 〜 2026-03-30)

TextEncoder cond_projバグ修正後、gin512を200 epochで再学習。

### 設定

- 200 epoch, batch_size=24, 4x V100
- CosineAnnealingLR + warmup 3ep
- cond_projバグ修正適用
- 学習時間: ~93時間

### 結果

- `output-vits2-6lang-gin512-v2/checkpoints/epoch=199-step=663042.ckpt`
- ONNX: `output-vits2-6lang-gin512-v2/vits2-gin512-200ep.onnx` (37.4 MB FP16)
- loss_gen_all: ~64 (60epと同等、改善なし)
- **高周波欠損は改善されず** — conditioning比率過剰が根本原因

---

## gin512 FT実験 v1-v2 詳細

### gin512 v1 FT (2026-03-25)

Template D構成 (no-freeze-dp, dp-lr=1e-4, DurDisc, 3-optimizer)。

**問題:** 機械音 + 発音がゆっくり

**原因 (15エージェント調査):**
1. `speaker_conditioned_encoder=False` → ベースモデル(True)との不整合でencoder出力分布ミスマッチ
2. `no-freeze-dp + dp-lr=1e-4` → 100発話でDP過学習
3. DurDisc LR (2e-5) と DP LR (1e-4) の不整合

### gin512 v2 FT (2026-03-26)

v1の4つの修正を適用。

**変更点:**
1. `speaker_conditioned_encoder=True` (追加)
2. freeze-dp (auto) — no-freeze-dp削除
3. dp-lr削除
4. DurDisc削除 (2-optimizer)

**結果:** duration改善 (2.41s) だが雑音残存。
**原因:** gin512ベースモデル自体に高周波欠損 → ベースモデルの品質問題。

---

## gin256 conditioning比率分析

gin256はVITS1と同等のbalanced conditioning比率を持つ。

| 指標 | VITS1 gin512 | VITS2 gin256 | VITS2 gin512 |
|------|-------------|-------------|--------------|
| g norm (speaker 0) | 19.08 | 20.69 | 26.31 |
| dec.cond(g) norm | 122.23 | 45.85 | 129.25 |
| dec.conv_pre weight norm | 41.15 | 15.80 | 24.30 |
| **cond/conv_pre比** | **2.97** | **2.67** | **5.32** |

gin256の比率2.67はVITS1の2.97と同等。gin512の5.32は2倍過剰。

---

## B1: gin256 + Linear Spec ベースモデル (2026-04-01)

VITS2のMel Posterior Encoder (80ch) をVITS1と同じLinear Spec (513ch) に戻し、他のVITS2機能は維持。gin256で検証。

### 設定

```bash
nohup uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 75 --batch-size 32 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm --audio-log-epochs 5 \
  --mas-noise-start 0.01 --mas-noise-decay 2e-6 \
  --no-sdp --use-duration-discriminator --speaker-conditioned-encoder \
  --default_root_dir /data/piper/output-vits2-6lang-linspec
```

注: `--mel-posterior-encoder` なし（linear spec使用）、`--cosine-scheduler` なし（ExponentialLR使用）

### 結果

| 指標 | B1 (gin256+linspec) | VITS1 (参照) |
|------|-------------------|-------------|
| hi-mid | **-31.3** | +11.0 |
| highs | **-23.3** | +3.1 |
| RMS | **0.090** | 0.201 |

**全帯域でVITS1を大幅に下回る。**

### 原因分析

gin256 (小さいconditioning) + Linear Spec 513ch (大きいposterior) のアンバランス:
- Posterior Encoder (enc_q) が513chの豊かなスペクトル情報から精密なzを生成
- Prior (enc_p) はgin256の小さなconditioning (256次元g) で条件付けされた分布
- Priorがposteriorの精度に追いつけず、KL乖離が大きい
- 推論時はpriorからzをサンプリングするため、低品質なzが生成される

**結論:** gin_channelsとposterior encoder入力はバランスが必要。gin256↔mel(80ch)、gin512↔linspec(513ch) が適正な組み合わせ。

### ファイル

- チェックポイント: `output-vits2-6lang-linspec/checkpoints/epoch=74-step=*.ckpt`

---

## B2: gin512 + Linear Spec + ExponentialLR ベースモデル (2026-04-02 〜 04-04)

B1の失敗を受けて、gin512 + Linear Spec (VITS1と同じ構成) にVITS2機能を追加。LRもExponentialLRに統一。

### 仮説

gin512 + linspec 513ch はVITS1で実績のあるバランス構成。これにVITS2の有用な機能（DurDisc, speaker-conditioned encoder, noise-scaled MAS）を追加すれば品質向上するはず。

### 設定

```bash
nohup uv run python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 75 --batch-size 24 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --max-phoneme-ids 400 --no-wavlm --audio-log-epochs 5 \
  --mas-noise-start 0.01 --mas-noise-decay 2e-6 \
  --no-sdp --use-duration-discriminator --speaker-conditioned-encoder \
  --default_root_dir /data/piper/output-vits2-6lang-gin512-linspec
```

注: `--mel-posterior-encoder` なし、`--cosine-scheduler` なし、batch_size=24 (V100 16GBでgin512にはメモリ制約)

### VITS1との差分

| 項目 | B2 (VITS2) | VITS1 |
|------|-----------|-------|
| Duration Predictor | Deterministic DP | SDP (flow-based) |
| Duration Discriminator | あり (3-optimizer) | なし (2-optimizer) |
| Speaker-Cond Encoder | あり (cond_proj + cond_layer) | なし |
| Noise-Scaled MAS | あり (0.01→0) | なし |
| Posterior Encoder | Linear Spec 513ch | Linear Spec 513ch (**同じ**) |
| gin_channels | 512 | 512 (**同じ**) |
| LRスケジューラ | ExponentialLR | ExponentialLR (**同じ**) |
| batch_size | 24 | 20 |

### 結果

| 指標 | B2 JA (sp=0) | VITS1 JA (sp=0) | B2 EN (sp=20) | VITS1 EN (sp=20) |
|------|-------------|----------------|--------------|-----------------|
| dur | 2.89s | 2.51s | 1.32s | 1.01s |
| rms | **0.072** | 0.192 | **0.099** | 0.216 |
| lo | -52.9 | -44.4 | -50.4 | -42.8 |
| mid | -65.6 | -58.3 | -61.9 | -59.6 |
| hi-mid | **-86.0** | -69.2 | **-100.0** | -74.1 |
| hi | **-98.8** | -74.9 | -89.6 | -85.7 |

**全周波数帯でVITS1より大幅に劣る。RMSは1/3以下。**

### 原因分析

1. **gradient update数の不足**: batch_size=24でstep/epochがVITS1の約半分
   - VITS2: 248,739 steps × 24 batch × 4 GPU = 23.9M sample-updates
   - VITS1: 504,712 steps × 20 batch × 4 GPU = 40.4M sample-updates
   - **VITS2はVITS1の59%しか学習していない**

2. **dec.cond weight norm低下**: VITS2=25.1 vs VITS1=38.1 → speaker conditioning学習が不足

3. **3-optimizer干渉**: G, D, DurDiscの3つのoptimizerが同時に学習。Gへの勾配シグナルが分散。

4. **VITS2固有機能の複合的悪影響**: Deterministic DP, DurDisc, speaker-conditioned encoder, noise-scaled MASの4機能がVITS1と異なる。どれが品質低下の原因かは個別検証が必要。

### パラメータ比較

| コンポーネント | VITS1 | B2 (VITS2) | 差分 |
|--------------|-------|-----------|------|
| enc_p | 6,424,320 | 6,522,816 | +98,496 (cond_proj+cond_layer) |
| dec | 1,796,096 | 1,796,096 | 0 |
| enc_q | 10,396,032 | 10,396,032 | 0 |
| flow | 10,260,096 | 10,260,096 | 0 |
| dp | 1,643,440 | 464,849 | -1,178,591 (SDP→DP) |
| **Total G** | **30,815,472** | **29,735,378** | **-1,080,094** |
| **Total D** | **46,747,132** | **47,401,469** | **+654,337** (DurDisc) |

dec, enc_q, flowは完全に同一。品質差はenc_p, dp, およびDurDiscの学習ダイナミクスに起因。

### ファイル

- チェックポイント: `output-vits2-6lang-gin512-linspec/checkpoints/epoch=74-step=248739.ckpt`
- ONNX: `output-vits2-6lang-gin512-linspec/vits2-gin512-linspec-75ep.onnx` (37.3 MB FP16)
- WandB: https://wandb.ai/yousan/piper-tts/runs/2lhm3kuu

---

## gin_channelsとPosterior Encoderのバランス則

全実験から導出された構成の適合性マトリクス:

| gin_channels | Posterior Encoder | 理論的バランス | 実験結果 |
|-------------|------------------|--------------|---------|
| 256 | Mel (80ch) | ✅ balanced | gin256 v5: 周波数OK、速度・声質でVITS1に劣る |
| 256 | Linear Spec (513ch) | ❌ posterior過剰 | B1: hi-mid=-31.3、全帯域劣悪 |
| 512 | Mel (80ch) | ❌ conditioning過剰 | gin512 v1-v3: 水中感、高周波欠損 |
| 512 | Linear Spec (513ch) | ✅ balanced | B2: 全帯域でVITS1より劣る（VITS2機能の影響） |

**結論:** バランスが取れていても (gin256+mel, gin512+linspec)、VITS2固有機能 (A-D) がVITS1を下回る品質をもたらす。バランスは必要条件だが十分条件ではない。

---

## VITS2固有機能 (A-E) の整理

| ID | 機能 | CLIフラグ | 論文上のメリット | リスク |
|----|------|----------|---------------|--------|
| **A** | Deterministic DP (SDP廃止) | `--no-sdp` | 推論時のduration安定性・再現性、パラメータ1/3 | SDPのflow-based表現力を失う |
| **B** | Duration Discriminator V2 | `--use-duration-discriminator` | GANベースで自然な発話リズム学習 | 3-optimizer化で学習不安定 |
| **C** | Speaker-Conditioned TextEncoder | `--speaker-conditioned-encoder` | 話者固有の音韻ダイナミクス学習 | enc_p過学習リスク |
| **D** | Noise-Scaled MAS | `--mas-noise-start 0.01` | アライメント学習初期の多様性確保 | 低リスク（ノイズは減衰） |
| **E** | Mel Posterior Encoder | `--mel-posterior-encoder` | enc_qパラメータ削減、学習メモリ節約 | スペクトル情報欠落 |

### Eの検証状況

- gin512+mel (E=ON, A-Dも全ON): 高周波欠損 → ❌
- gin256+mel (E=ON, A-Dも全ON): FT品質VITS1以下 → ❌
- gin512+linspec (E=OFF, A-Dは全ON): 全帯域VITS1以下 → ❌ (B2)
- **VITS1+Eのみ (A-Dなし): ❌ 検証済み (T-E)** — mid -25dB, hi -39dB, 単体でも深刻な品質劣化

**結論: Feature E は単体でも品質を大幅に劣化させる。軽量化メリットがあっても採用不可。**

### 個別検証計画

VITS1ベースラインに1機能ずつ追加して影響を測定（20 epoch短縮テスト）:

| テスト | 構成 | 追加機能 | 目的 | 状態 |
|--------|------|---------|------|------|
| T0 | VITS1そのまま (20ep) | なし | ベースライン | T-Eの比較対象として使用 (epoch=19) |
| **T-E** | **VITS1 + E** | **Mel Posterior Encoder** | **軽量化の可否** | **❌ 完了 — 全帯域でNG (mid -25dB, hi -39dB)** |
| T1 | VITS1 + A | Deterministic DP (no-sdp) | SDPなしの品質影響 | 未実施 |
| T2 | VITS1 + A + B | + DurDisc | 3-optimizer干渉の影響 | 未実施 |
| T3 | VITS1 + C | Speaker-Conditioned Encoder | enc_p品質への影響 | 未実施 |
| T4 | VITS1 + D | Noise-Scaled MAS | アライメント品質への影響 | 未実施 |

### 旧: 未テストのFT構成

gin256 v4の失敗原因が判明したため、以下のFT構成がテスト可能（ベースモデル品質問題が解決した場合）:

| 設定 | v4 (失敗) | v5 (実施済み) | **v6 (未テスト)** |
|------|-----------|-------------|-----------------|
| speaker_cond_enc | False (原因) | True | True |
| freeze_dp | False | True (遅い) | **False** |
| dp_lr | 1e-4 | - | **5e-5 (控えめ)** |
| DurDisc | True | False | **True** |
| gin_channels | 256 | 256 | 256 |

---

## コード変更履歴

| 日付 | ファイル | 変更 | 状態 |
|------|---------|------|------|
| 2026-03-26 | `vits/models.py:218` | TextEncoder cond_proj バグ修正 (g→encoder) | gin256 FTのためrevert済み |
| 2026-03-30 | `__main__.py:507-521` | gin_channels自動検出 (ベースcheckpoint継承) | 適用中 |

---

## T-E 実験: VITS1 + Mel Posterior Encoder (2026-04-05)

### 目的

Feature E (Mel Posterior Encoder) を**VITS1に単体で追加**した場合に品質が維持されるか検証。
enc_qは推論グラフに含まれないため、品質が維持されれば学習時メモリ節約のメリットがある。

### 構成

```
VITS1そのまま + --mel-posterior-encoder のみ
--mas-noise-start 0 (MASノイズ無効化で純粋なVITS1+E)
他のVITS2機能: 全てOFF (SDP有効, DurDiscなし, speaker-cond-encなし)
LRスケジューラ: ExponentialLR (VITS1と同一)
20 epoch, batch_size=20, 4x V100, dataset-multilingual-6lang-filtered
```

### 学習コマンド

```bash
export WANDB_API_KEY=... && \
NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1 \
nohup /data/piper/.venv/bin/python -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 20 --batch-size 20 --samples-per-speaker 2 \
  --checkpoint-epochs 5 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 \
  --max-phoneme-ids 400 \
  --no-wavlm \
  --audio-log-epochs 5 \
  --mas-noise-start 0 \
  --mel-posterior-encoder \
  --default_root_dir /data/piper/output-vits1-mel-pe-test \
  > /data/piper/training_vits1_mel_pe_test.log 2>&1 &
```

### スペクトル比較結果 (epoch 19, JA+EN 6発話平均)

| 指標 | VITS1 baseline | VITS1+MelPE | 差分 | 判定 |
|------|---------------|-------------|------|------|
| duration | 2.31s | 2.52s | +0.22s | OK |
| RMS | 0.2122 | 0.1195 | -43% | **NG** |
| lo (100-1k) | +13.2dB | +7.1dB | **-6.1dB** | **NG** |
| mid (1k-4k) | -2.2dB | -27.2dB | **-25.0dB** | **NG** |
| hi-mid (4k-8k) | -8.7dB | -34.7dB | **-26.0dB** | **NG** |
| hi (8k+) | -16.1dB | -54.9dB | **-38.8dB** | **NG** |

**JA単独:**

| 指標 | VITS1 | VITS1+MelPE | 差分 |
|------|-------|-------------|------|
| lo | +12.9dB | +5.4dB | -7.5dB |
| mid | -2.1dB | -32.8dB | **-30.7dB** |
| hi-mid | -8.1dB | -38.1dB | **-30.0dB** |
| hi | -15.5dB | -60.4dB | **-44.8dB** |

**EN単独:**

| 指標 | VITS1 | VITS1+MelPE | 差分 |
|------|-------|-------------|------|
| lo | +13.4dB | +8.8dB | -4.6dB |
| mid | -2.4dB | -21.6dB | **-19.3dB** |
| hi-mid | -9.2dB | -31.2dB | **-22.0dB** |
| hi | -16.8dB | -49.4dB | **-32.7dB** |

### 結論

**Feature E (Mel Posterior Encoder) は単体でも深刻な品質劣化を引き起こす。**

enc_qは推論グラフに含まれないが、学習中のenc_qが生成する潜在表現の品質がデコーダの学習に直接影響する。80ch mel入力では513ch linear specと比べて情報量が不足し、デコーダが高周波を再現する能力を獲得できない。

軽量化メリット（学習時のenc_qパラメータ削減）があっても品質上採用不可。

### ファイル

- チェックポイント: `output-vits1-mel-pe-test/checkpoints/epoch=19-step=134630.ckpt`
- ONNX: `output-vits1-mel-pe-test/vits1-mel-pe-20ep.onnx` (38.0 MB FP16)
- VITS1ベースライン: `output-vits1-mel-pe-test/vits1-baseline-20ep.onnx` (38.0 MB FP16)
- WandB: https://wandb.ai/yousan/piper-tts/runs/fxyujaot

---

## Template D 修正提案

現行Template Dの `--speaker-conditioned-encoder を外す` は**誤り**。ベースモデルが `speaker_conditioned_encoder=True` で学習されている場合、FTでも**必ず保持**すること。外すと `cond_layer`/`cond_proj` がsilent dropされて品質劣化する。

```diff
- --speaker-conditioned-encoder を削除: 単一話者FTでは不要
+ --speaker-conditioned-encoder を保持: ベースモデルと一致させる（外すとcond_layer/cond_projがsilent drop）
```
