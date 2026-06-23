# Multi-6lang Zero-Shot TTS スクラッチ学習 (v7) — 実施結果と根本原因の解析

**期間**: 2026-05-08 ~ 2026-05-16 (8 日連続)
**ブランチ**: `feat/zero-shot-tts` (commit `95e74cb` 時点)
**データセット**: `dataset-multilingual-6lang-filtered-new` (571話者/6lang/497,519発話)
**GPU**: Tesla V100-PCIE-16GB × 4

---

## 1. 概要

`dev` リベース後の Zero-Shot TTS を multi-6lang データセットでスクラッチ学習する試行。
複数の障害を順に解消し、最終的に v7 として安定動作 + epoch 20 まで完走 + 評価成功。

---

## 2. 直面した問題と真の根本原因

### 2.1 「CUDA illegal memory access」は **偽装症状** だった

学習を始めると step 149 / 600 / 2400 など**毎回ランダムな位置**で `CUDA error: an illegal memory access was encountered` が発生し、プロセスが死亡していた。

| 設定 | 死亡 step | 原因と推測されていたもの |
|---|---|---|
| `batch=20` 32-true | 149 で NaN | 勾配発散 |
| `batch=20` + grad_clip=1.0 | 149 で NaN | clip 不足 |
| `batch=20` + lr=1e-4 + grad_clip=0.5 | 149 で NaN | やはり NaN |
| `batch=10` + 全対策 | **299-2400 で CUDA illegal** | GPU memory fragmentation? |

`CUDA_LAUNCH_BLOCKING=1` + `devices=1` + `c_spk=0` でも再発したことから、データ起因・DDP 起因・SCL 起因をすべて否定。

**最終的に判明した真因**:

```text
WARNING:vits.lightning:Non-finite loss_g at step=236 → batch skip
[Rank 3] ALLREDUCE 1800002ms timeout → 全 rank 終了
```

NaN skip が rank ごとにバラつき、DDP の `all_reduce` が mismatch、NCCL collective が
**30 分タイムアウト** → プロセス終了。エラー出力には CUDA stacktrace が連鎖して出るため
「CUDA illegal access」のように見えていた。

### 2.2 NaN 発散の根本原因: **Multi-scale FiLM の欠落**

`MBiSTFTGenerator` (現行 decoder) の speaker conditioning が `conv_pre` 直後の 1 回加算のみで、
upsample 各段に伝わっていなかった (`mb_istft.py:236`)。リベース時に旧 `Generator +
Multi-scale FiLM` クラスが廃止されたが、MBiSTFT 側への移植が未実施だったため。

過去の成功事例との比較で確定:

| Decoder | Speaker conditioning | precision | zero-shot で安定 |
|---|---|---|---|
| 旧 `Generator + Multi-scale FiLM` (廃止) | 全 4 upsample 段に FiLM | 16-mixed | ✅ v9 で 200ep 成功 |
| 現行 `MBiSTFTGenerator` (元) | 加算 1 回のみ | 32-true | ❌ step 149 で NaN |
| 現行 + **Multi-scale FiLM 復活** | input + 各段 FiLM | 32-true | **✅ v7 で完全安定** |

### 2.3 `loss_dino = 0.00` の永続化

L2 再正規化を入れた v6 でも `loss_dino` が step ~1249 で突如 0.00 に貼り付く。

原因の連鎖:

1. CAM++ 出力 (norm=1) に `+ σ × N(0, I)` noise を加えた後、**L2 再正規化していなかった**
2. 期待 norm が `√(1 + σ² × dim) ≈ 1.22` に増加
3. spk_proj の入力分布が train/inference で 22% magnitude 不一致
4. 学習進行とともに spk_proj の重みが大きくなり、`log_softmax(student_emb / τ)` で発散
5. `losses.py:113-115` の NaN マスクで 0 化
6. NaN teacher_emb が EMA で `dino_center` を汚染
7. 汚染後の全 step で dino_loss が NaN → 0 マスク → DINO が永続停止

### 2.4 OOM (Memory cgroup out of memory)

`num_workers=4` × DDP 4 ranks = 16 DataLoader workers が各 13 GB の jsonl entries を独立 load、
合計 ~208 GB → cgroup 上限 100 GB を突破。`num_workers=1` まで下げて対処。

---

## 3. 修正コミット (5 件)

| commit | 内容 | 効果 |
|---|---|---|
| `5cdfafb` | **MBiSTFTGenerator に Multi-scale FiLM 復活** | 32-true での zero-shot 学習成立 |
| `34ad257` | **DDP-synced NaN skip** (`_ddp_synced_is_finite`) | NCCL mismatch 解消、学習継続性確保 |
| `5e700d4` | `dino_loss` 診断 log | NaN 原因の特定が可能に |
| `ba71e16` | **speaker_embedding noise 加算後 L2 再正規化** | DINO 0 化解消、train/inference 入力分布一致 |
| `95e74cb` | **dino_center を NaN 汚染から防御** | spk_proj 稀な NaN で center 永続汚染を防止 |

実装位置:

- `src/python/piper_train/vits/mb_istft.py:212-265, 274-285`: Multi-scale FiLM + `_apply_film`
- `src/python/piper_train/vits/lightning.py:79-99`: `_ddp_synced_is_finite`
- `src/python/piper_train/vits/lightning.py:786-797`: noise 加算 + L2 再正規化
- `src/python/piper_train/vits/lightning.py:944-983`: 有限性チェック付き EMA + center 更新
- `src/python/piper_train/vits/losses.py:84-148`: dino_loss 入力検証 + 警告

テスト:

- `tests/test_mb_istft_film.py`: 15 ケース (FiLM 数値挙動、構造、forward、勾配)
- `tests/test_ddp_synced_finite.py`: 11 ケース (DDP all_reduce mock)
- `tests/test_dino_loss_diagnostics.py`: 12 ケース (NaN 入力分類)
- `tests/test_speaker_embedding_perturbation.py`: 7 ケース (L2 再正規化数学)

---

## 4. v7 最終学習設定

```bash
export WANDB_MODE=disabled
export NCCL_DEBUG=WARN NCCL_P2P_DISABLE=1 NCCL_IB_DISABLE=1
export PYTHONPATH=/data/piper-plus-zero-shot/src/python
export PIPER_FORCE_CPU_ORT=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
# LD_LIBRARY_PATH: PyTorch 同梱 cuDNN を ORT に見せる (memory/env_setup.md 参照)

cd /data/piper-plus-zero-shot
nohup /data/piper/.venv/bin/python -u -m piper_train \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered-new \
  --prosody-dim 16 \
  --accelerator gpu --devices 4 --precision 32-true \
  --max_epochs 200 --batch-size 20 --samples-per-speaker 4 \
  --checkpoint-epochs 1 --quality medium \
  --base_lr 2e-4 --disable_auto_lr_scaling \
  --ema-decay 0.9995 --num-workers 2 --no-pin-memory --no-wavlm \
  --max-phoneme-ids 400 \
  --spk-emb-noise-sigma 0.05 \
  --d-update-interval 1 \
  --lr-scheduler cosine --lr-warmup-epochs 5 --lr-min 1e-5 \
  --kl-annealing-epochs 10 \
  --c-dino 0.5 --c-spk 1.0 \
  --c-sub-stft 1.0 \
  --gradient-clip-val 0 \
  --speaker-encoder-path /data/piper/models/campplus.onnx \
  --val-every-n-epochs 1 --audio-log-epochs 5 \
  --default_root_dir /data/piper/output-zero-shot-multi-6lang-v7
```

ポイント:

- `precision=32-true`: V100 で FP16-mixed は backward 27 sec → 32-true で 5.3 sec (5x 高速)
- `num_workers=2`: cgroup 100GB 制約 (DataLoader worker × devices × 13GB)
- `gradient-clip-val=0`: 過去成功事例 (v9, 6lang-mb) いずれも grad_clip=null
- `samples-per-speaker=4`: SCL/DINO のため同一話者 4 サンプル

---

## 5. 学習結果

### 速度

- **1 epoch ≈ 8 時間 53 分** (極めて安定)
- step あたり ≈ 5.3 sec (32-true)
- GPU 利用率 87-96% (全 4 枚)

### Loss 推移

| Loss | 開始 | epoch 10 | epoch 15 | **epoch 20** | 全期間改善率 |
|---|---|---|---|---|---|
| loss_gen_all | 135.80 | 43.39 | 43.88 | 46.18 | -66% |
| loss_disc_all | 5.21 | 1.37 | 1.25 | **0.98** | **-81%** |
| loss_mel | 110.51 | 23.71 | 22.48 | 23.28 | -79% |
| loss_kl | 10.83 | 2.09 | 2.23 | 2.20 | -80% |
| loss_dur | 2.67 | 1.91 | 1.79 | 1.92 | -28% |
| **loss_dino** | 0.88 | 0.061 | 0.031 | 0.054 | **-94%** |
| **loss_spk** | 0.99 | 0.864 | 0.809 | **0.803** | -19% |
| loss_sub_stft | 4.35 | 1.83 | 1.96 | 1.76 | -60% |

### SECS (Speaker Embedding Cosine Similarity)

| ペア | epoch 10 | **epoch 20** | 変化 |
|---|---|---|---|
| 既知 ref ↔ 既知 synth | 0.5612 | **0.5943** | +5.9% ✅ |
| **未知 ref ↔ 未知 synth (zero-shot)** | **0.6622** | 0.6388 | -3.5% |
| 既知 ref ↔ 未知 synth (相違) | 0.6018 | 0.6159 | +2.3% |
| 未知 ref ↔ 既知 synth (相違) | 0.5575 | 0.5982 | +7.3% |

CLAUDE.md の基準値 (out-of-domain 0.55-0.70 = 良好) との比較で、
**zero-shot は epoch 10 から既に「良好」域に到達**。epoch 20 ではわずか低下するも依然「良好」内。

### 防御機構の挙動 (8 日連続観測)

| 警告 | 累計 (epoch 20 時点) | 解釈 |
|---|---|---|
| Non-finite batch skip (DDP 同期) | 2,548 (率 2.5%) | 学習継続性確保 |
| `student_emb` non-finite (spk_proj 出力) | 637 件 | 検出して dino_loss を 0 化 |
| `dino_center update skipped` | 637 件 | center 防御発動 |
| **`dino_center` 汚染** | **0 件** | 防御完璧 ✅ |
| **NCCL collective timeout** | **0 件** | DDP 同期 skip 効果 ✅ |

---

## 6. 残された課題と今後の方針

### 課題

1. **区別性 (4 ペアの SECS が 0.59-0.64 に集中)**: 話者個性の表現がまだ不十分。
   - 推測される要因: epoch 不足 (dev base は 75 epoch でようやく成熟)
   - epoch 20 → epoch 50 / 75 で改善見込み
2. **V100 で 75 epoch 完走に 28 日**: 計算リソース制約。A100 移行で大幅短縮可能
3. **`student_emb` の稀な NaN (率 0.6%)**: spk_proj 内部の数値不安定。LayerNorm eps 調整等で改善余地

### 今後の方針

| Phase | 内容 | 所要時間 |
|---|---|---|
| 短期 | A100 等で続き学習 (epoch 21 → 50) | 1 週間 |
| 中期 | epoch 50 評価 → 必要なら 75 epoch | 1-2 週間 |
| 長期 | Phase 3 改善 (InfoNCE / R1 / data 拡充) | 別検討 |

---

## 7. 参考ドキュメント

- [`zero-shot-quality-improvement-plan.md`](zero-shot-quality-improvement-plan.md): Tier 1-4 改善ロードマップ
- [`zero-shot-speaker-similarity-research.md`](zero-shot-speaker-similarity-research.md): 10 エージェント研究調査
- [`v9-training-handoff.md`](v9-training-handoff.md): 旧 zero-shot 20speakers 学習引き継ぎ
