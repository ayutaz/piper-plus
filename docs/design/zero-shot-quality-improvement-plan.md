# Zero-Shot TTS 精度向上計画

> **ステータス更新 (2026-06-26)**:
>
> - **Tier 1 (未実装機能の修正): ✅ 完了** — v7 multi-6lang スクラッチ学習 (32 epoch 完走) で全 5 修正実装済 (5cdfafb / 34ad257 / 5e700d4 / ba71e16 / 95e74cb)。 SECS (zero-shot) 0.6622 → 0.6879 達成。 Tsukuyomi FT で SECS 0.7749 を確認。 詳細: [`multi-6lang-zero-shot-v7-training-results.md`](multi-6lang-zero-shot-v7-training-results.md)
> - **Tier 2/3 (学習改善 / アーキ微調整): 🟡 active future work** — InfoNCE / R1 regularizer / データ拡充は引き続き計画段階。 CLAUDE.md L139 + [`docs/handoff/zero-shot-tts-handoff-2026-06-20.md`](../handoff/zero-shot-tts-handoff-2026-06-20.md) から参照中
> - 「1. 重大発見: 未実装/不完全な機能」 セクションの記述は **当初調査時 (2026-03-31) の snapshot** で、 現在は v7 で fix 済の項目を含みます。 historical context として残しています

> 調査日: 2026-03-31 (復元完了: 2026-04-01)
> ブランチ: `feat/zero-shot-tts`
> 制約: モデルサイズ (~74MB ONNX) 不変、推論速度低下なし

---

## 目次

1. [重大発見: 未実装/不完全な機能](#1-重大発見-未実装不完全な機能)
2. [改善提案一覧](#2-改善提案一覧)
   - [Tier 1: 未実装機能の修正](#tier-1-未実装機能の修正最優先コスト極小)
   - [Tier 2: 学習改善](#tier-2-学習改善モデルサイズ不変)
   - [Tier 3: アーキテクチャ微調整](#tier-3-アーキテクチャ微調整パラメータ数不変)
   - [Tier 4: データ・推論時改善](#tier-4-データ推論時改善)
3. [最新論文からの知見](#3-最新論文からの知見)
4. [評価パイプライン設計](#4-評価パイプライン設計)
5. [推奨実行順序](#5-推奨実行順序)
6. [参考文献](#6-参考文献)

---

## 1. 重大発見: 未実装/不完全な機能

CLAUDE.mdに「実装済み」と記載されているが、コードレビューの結果**実際には動作していない**機能が複数発見された。
これらを修正するだけで、モデルサイズ・推論速度を変えずに大幅な品質向上が見込める。

| # | 機能 | CLAUDE.md記載 | 実態 | 影響度 |
|---|------|-------------|------|--------|
| 1 | **KLアニーリング** | `kl_weight = c_kl * (0.1 + 0.9 * epoch / N)` で線形増加 | ✅ **FIXED** (2026-04-01): `training_step_g` にアニーリング重み適用を復元 | ~~CRITICAL~~ |
| 2 | **DINO自己蒸留** | EMA teacher (`spk_proj_teacher`, momentum=0.996) + `dino_center` バッファ | ✅ **FIXED** (2026-04-01): `spk_proj_teacher` 初期化 + `dino_center` 登録 + `dino_loss()` 呼び出し復元 | ~~HIGH~~ |
| 3 | **DP cond_scale** | `scale = sigmoid(cond_scale(g)) + 0.5`、`x = x * scale + cond(g)` | 意図的に削除 (ac8e456: "Duration Predictor簡素化")。Multi-scale FiLMで代替 | **要検討** |
| 4 | **Flow dilation_rate=2** | 指数的受容野拡大 (1→3→7→15→...) | ✅ **FIXED** (2026-04-01): `dilation_rate=2` 復元（受容野: 61フレーム） | ~~MEDIUM~~ |
| 5 | **spk_proj EMA** | `EMACallback` が spk_proj もEMA追跡 | ✅ **FIXED** (2026-04-01): `ema.py` にspk_proj追跡を復元 | ~~MEDIUM~~ |
| 6 | **self.speaker_encoder** | CamPPSpeakerEncoder初期化 | ✅ **FIXED** (2026-04-01): `self.speaker_encoder = None` 初期化 + CamPPクラス復元 | ~~CRITICAL~~ |
| 7 | **max_epochs** | CLAUDE.md: 100ep | メモリ記録: v7で200ep推奨が検証済み。100epでは未収束・音割れ発生 | **CRITICAL** |

### 各問題の技術詳細

#### 1.1 KLアニーリング ✅ FIXED

**場所**: `lightning.py` training_step_g内

```python
# 復元済み (2026-04-01)
if (
    self.hparams.kl_annealing_epochs > 0
    and self.current_epoch < self.hparams.kl_annealing_epochs
):
    kl_weight = self.hparams.c_kl * (
        0.1 + 0.9 * self.current_epoch / self.hparams.kl_annealing_epochs
    )
else:
    kl_weight = self.hparams.c_kl
loss_kl = kl_loss(z_p, logs_q, m_p, logs_p, z_mask) * kl_weight
```

**経緯**: `7d75fff` (3/17) で実装 → `11fab06` (3/30) squash-rebase時に脱落 → `474722a` (4/1) で復元。
`loss_dur` の `clamp(min=-100.0)` も同時に復元。

#### 1.2 DINO自己蒸留 ✅ FIXED

**場所**: `losses.py` (定義)、`lightning.py` (**init** + training_step_g)

**復元済み** (2026-04-01):

1. ✅ `VitsModel.__init__` で `spk_proj_teacher` を `spk_proj` のdeep copyとして作成（勾配凍結）
2. ✅ `dino_center` バッファを登録
3. ✅ `training_step_g` で teacher出力を計算し `dino_loss()` を呼び出す
4. ✅ 各ステップ後にteacherをEMA更新 (momentum=0.996)
5. ✅ centerを更新・クランプ (min=-10, max=10)

**経緯**: `078a43a` (3/17) で実装 → NaN対策修正 (`08590dc`, `f42e3ce`) → `11fab06` (3/30) squash時に脱落 → `474722a` (4/1) で復元。

#### 1.3 Duration Predictor cond_scale

**場所**: `models.py` StochasticDurationPredictor / DurationPredictor

```python
# 現状
x = x + self.cond(g)

# あるべき姿
scale = torch.sigmoid(self.cond_scale(g)) + 0.5  # [0.5, 1.5]
x = x * scale + self.cond(g)
```

**影響**: 話者固有の発話速度・リズムを乗算スケーリングでモデリングできない。加算のみでは話者間20-50%の速度差を表現不可。

#### 1.4 Flow dilation_rate ✅ FIXED

**場所**: `models.py` line 850

```python
# 復元済み (2026-04-01)
self.flow = ResidualCouplingBlock(inter_channels, hidden_channels, 5, 2, 4, gin_channels=gin_channels)
#                                                                     ^ dilation_rate=2 ✅
```

**経緯**: `7d75fff` (3/17) で1→2に変更 → `f98d381` (3/22) で維持を明記 → `ac8e456` (3/30) squash時に暗黙的に1に戻った → `474722a` (4/1) で2に復元。

---

## 2. 改善提案一覧

### Tier 1: 未実装機能の修正（最優先、コスト極小）

| # | 施策 | 変更量 | 期待効果 | 状態 |
|---|------|--------|---------|------|
| 1 | ✅ KLアニーリング実装 | 5行 | 高 | **DONE** |
| 2 | ✅ DINO loss有効化 | ~30行 | 高 | **DONE** |
| 3 | Duration Predictor cond_scale追加 | ~15行 | 高 | 要検討 (意図的削除) |
| 4 | ✅ Flow dilation_rate=1→2 | 1行 | 中 | **DONE** |
| 5 | ✅ max_epochs=200 | 設定変更 | 高 | **DONE** (v9コマンドで設定済み) |
| 6 | ✅ spk_proj EMA追跡 | ~20行 | 中 | **DONE** |

**Tier 1は6件中5件完了。残りはDP cond_scale検討のみ。包括レビュー修正（2026-04-12）で追加8件完了。**

### Tier 2: 学習改善（モデルサイズ不変）

| # | 施策 | 詳細 | 期待効果 |
|---|------|------|---------|
| 7 | **InfoNCE対比学習loss** | spk_proj出力 (512次元) でバッチ内の正負ペアを識別。`SpeakerBalancedBatchSampler` (samples_per_speaker=4) が自然な正負ペアを提供。`c_contrastive=0.1` | 高 |
| 8 | **R1勾配ペナルティ** | `R1 = \|\|grad(D(x_real))\|\|^2`。D過学習によるG mode collapse防止。係数10.0。`d_update_interval=1` で毎ステップD更新する構成では特に重要 | 中-高 |
| 9 | **G/D/spk_proj別学習率** | D: 1e-4, spk_proj: 5e-5, G(other): 2e-4。各コンポーネントの収束速度に合わせたパラメータグループ分離 | 中 |
| 10 | **embedding noiseスケジュール** | 固定 σ=0.05 → cosineスケジュール (0.1→0.02)。初期は強い正則化、後半は精密学習 | 中 |
| 11 | **embedding mixup** | 同話者の異なる発話embedding間で補間: `e_mix = α*e1 + (1-α)*e2`, `α ~ Beta(0.2, 0.2)`。20話者で連続空間学習を補強 | 中 |
| 12 | **multi-scale mel SCL** | 現在のmean/std L1に加え、delta(1次差分)統計も比較。話者の発話ダイナミクスを捕捉 | 低-中 |

### Tier 3: アーキテクチャ微調整（パラメータ数不変）

| # | 施策 | 変更内容 | 期待効果 | コスト |
|---|------|---------|---------|--------|
| 13 | **TextEncoder pre-encoder条件付け** | speaker条件付けをself-attention後→前に移動。6層のattentionが話者依存テキスト表現を学習可能に | 高 | 0パラメータ、1行移動 |
| 14 | **FiLM活性化 1+tanh** | `sigmoid(x)+0.5` → `1+tanh(x)`。スケール範囲[0.5,1.5]→[0,2]、初期化時勾配4倍改善、チャネル完全抑制可能 | 中-高 | 0パラメータ、1行変更 |
| 15 | **spk_proj残差接続** | Linear1出力をLinear2出力に加算。非線形ボトルネックでの情報損失を防止 | 中 | 0パラメータ、1行追加 |
| 16 | **Snake活性化** | DecoderのLeakyReLU→Snake (`x + sin²(αx)/α`)。周期信号生成に特化 (BigVGAN実証済み) | 中 | +1,824パラメータ (~3.6KB) |
| 17 | **PosteriorEncoder dilation=2** | 訓練時のみ使用 (ONNX非含有)。受容野65→1021フレーム | 中 | 推論コスト0 |
| 18 | **spk_projスペクトル正規化** | 2層目のLinearに `spectral_norm` 適用。未知話者embeddingの出力変動を制限 | 中 | 0パラメータ |

### Tier 4: データ・推論時改善

| # | 施策 | 期待効果 | 備考 |
|---|------|---------|------|
| 19 | **話者数拡大 20→100+** | **最高** | JVS (100話者), JVNV (100話者), AISHELL-3 (218話者), LibriTTS-R (2,456話者) |
| 20 | **推論時Energy VAD** | 中 | 参照音声の無音除去。`energy_vad_numpy()` は既存関数 |
| 21 | **複数参照音声平均** | 中 | `--speaker-audio-dir` で3-5発話平均。抽出コードは既存 |
| 22 | **speed perturbation** | 中 | 0.9x-1.1x。実効3倍データ増強、話者同一性は保持 |
| 23 | **ITU-R BS.1770 ラウドネス正規化** | 低-中 | 話者間音量差を削減 |
| 24 | **参照音声テンポラルaugmentation** | 中 | 訓練時にmelをクリップ+シャッフル (Fox-TTS)。content漏洩を削減 |

---

## 3. 最新論文からの知見

### 適用推奨 (VITS ~74MB, CPU推論互換)

| 手法 | 出典 | 概要 | 期待効果 | 実装難度 |
|------|------|------|---------|---------|
| **Negated Speaker Representations** | AAAI 2024 | content情報をembeddingから減算。話者純度向上 | 中-高 | 中 |
| **参照音声テンポラルaugmentation** | Fox-TTS 2024 | 訓練時にmel時間軸シャッフル。content漏洩削減 | 中 | 低 |
| **TextEncoder per-layer CLN** | VITS2 / AdaSpeech | TextEncoderの各attention層にConditional LayerNorm | 中-高 | 中 (+~1.2Mパラメータ) |
| **Multi-layer SCL (TLA-SA)** | arXiv 2511.09995 | decoder中間層でもSCL計算。層ごとの話者情報量で重み付け | 中 | 中-高 |
| **Embedding Interpolation/Mixup** | DiffGAN-ZSTTS 2025 | 訓練時に話者embedding間を補間。連続空間の汎化向上 | 中-高 | 低 |

### 非推奨

| 手法 | 理由 |
|------|------|
| SEED (Diffusion on embeddings) | 推論時に複数denoiseステップ必要。CPUリアルタイム制約違反 |
| Codec系 (VALL-E, MaskGCT, F5-TTS) | アーキテクチャが根本的に異なる。VITSには適用不可 |
| CosyVoice 2 LLM backbone | >500MBモデル。サイズ制約違反 |
| Adversarial speaker classifier | 話者情報を除去する方向の学習。zero-shot TTSには逆効果 |

---

## 4. 評価パイプライン設計

### 現状

- 体系的な評価パイプラインが**存在しない**
- WandBで学習lossを監視するのみ、定量的な話者類似度測定なし

### 推奨メトリクス

| メトリクス | 説明 | ツール | 優先度 |
|-----------|------|--------|--------|
| **SECS** (Speaker Embedding Cosine Similarity) | 入力embeddingと生成音声embeddingのcosine類似度 | CAM++ ONNX | **最重要** |
| **Speaker Verification EER** | 正例/負例ペアのEqual Error Rate | CAM++ | 高 |
| **MCD** (Mel Cepstral Distortion) | 生成/実音声のスペクトル距離 | librosa | 中 |
| **F0相関** | ピッチレンジ・パターンの一致度 | librosa.pyin | 中 |
| **t-SNE可視化** | embedding空間の視覚的診断 | sklearn | 診断用 |

### 目標値

| メトリクス | 不良 | 許容 | 良好 | 優秀 |
|-----------|------|------|------|------|
| SECS (in-domain) | < 0.5 | 0.5-0.65 | 0.65-0.80 | > 0.80 |
| SECS (out-of-domain) | < 0.4 | 0.4-0.55 | 0.55-0.70 | > 0.70 |
| EER | > 15% | 8-15% | 4-8% | < 4% |
| MCD (dB) | > 8.0 | 6.0-8.0 | 4.5-6.0 | < 4.5 |

参考: VALL-E SECS ~0.68, NaturalSpeech 2 ~0.72, CosyVoice ~0.75 (LibriTTS test-clean)

### 評価プロトコル

- **テスト話者**: 訓練20話者から5話者を選択 (in-domain)
- **enrollment**: 話者あたり1発話 (5-10秒、テスト発話とは別)
- **テスト発話**: 話者あたり10文 (計50合成サンプル)
- **テキスト**: `scripts/evaluation/evaluation_texts_ja.txt` (52文、多様なカテゴリ)
- **所要時間**: ONNX CPU推論で2-3分/モデル

---

## 5. 推奨実行順序

### Phase 1.5: multi-6lang v7 学習で判明・修正された追加バグ (2026-05-08 ~ 2026-05-16)

`dev` リベース後の multi-6lang スクラッチ学習で発覚した 5 件の致命的バグを修正。
詳細は [`multi-6lang-zero-shot-v7-training-results.md`](multi-6lang-zero-shot-v7-training-results.md)。

| # | バグ | commit | 解決した症状 |
|---|------|--------|--------------|
| A | **Multi-scale FiLM が `MBiSTFTGenerator` で未移植** | `5cdfafb` | 32-true zero-shot 学習で step 149 NaN 発散 |
| B | DDP で NaN skip 判断が rank ごとにバラつき → all_reduce mismatch → NCCL timeout | `34ad257` | 「CUDA illegal access」と偽装されていた死亡の真因 |
| C | `dino_loss` の NaN マスクが原因情報を出さない | `5e700d4` | どの入力が NaN か特定可能に |
| D | **speaker_embedding noise 加算後の L2 再正規化忘れ** (本文書 #1 の既知バグ) | `ba71e16` | `loss_dino` が step 1249 から 0 に永続貼り付く現象を解消 |
| E | `dino_center` が NaN teacher_emb で永続汚染される | `95e74cb` | spk_proj 稀な NaN で DINO 全停止する現象を防止 |

A の Multi-scale FiLM は本文書 50 行目「**TestGeneratorFiLMConditioning** : skip 設定済み — 必要なら MBiSTFT への FiLM 移植を検討」を実装完了したもの。

### Phase 1: 未実装機能の修正

```text
進捗: 5/7完了 (2026-04-03更新) + 包括レビュー修正 (2026-04-12)
期待効果: 話者類似度 +15-25% (復元済み分で +10-15%)
```

1. ✅ KLアニーリング実装 (5行) — **DONE**
2. ✅ DINO loss有効化 (30行) — **DONE**
3. Duration Predictor cond_scale (15行) — 意図的に削除されたため要検討
4. ✅ Flow dilation_rate=2 (1行) — **DONE**
5. ✅ max_epochs=200 (設定変更) — **DONE** (v9コマンドで設定済み)
6. FiLM活性化 1+tanh (1行) — 未実施
7. TextEncoder pre-encoder条件付け (行移動) — 未実施

**包括レビュー修正 (2026-04-12) — 追加完了:**

1. ✅ C#/Rust/Go SpeakerEncoder mel shape 修正 `[1,80,T]`→`[1,T,80]` — **DONE**
2. ✅ C#/Rust/Go SpeakerEncoder FFT window 512→400 (Kaldi 25ms@16kHz) — **DONE**
3. ✅ C#/Rust/Go SpeakerEncoder CMVN 追加（バンド単位平均減算） — **DONE**
4. ✅ EMA CPU/GPU デバイスミスマッチ修正（チェックポイントリジューム後） — **DONE**
5. ✅ DINO center dtype ミスマッチ修正（FP16 学習時） — **DONE**
6. ✅ SCL dtype ミスマッチ修正（CamPP FP32 vs FP16） — **DONE**
7. ✅ TextEncoder speaker conditioning の `x_mask` 未適用修正 — **DONE**
8. ✅ `noise_scale` デフォルト全言語更新 0.667/0.8 → 0.4/0.5 — **DONE**

### Phase 2: 学習改善 + 評価基盤

```text
所要時間: 3-5日
期待効果: 話者類似度 +5-10% (Phase 1比)
```

1. 評価パイプライン構築 (`scripts/evaluation/evaluate_zero_shot.py`)
2. InfoNCE対比学習loss追加
3. R1勾配ペナルティ
4. G/D/spk_proj別学習率
5. embedding noiseスケジュール

### Phase 3: データ拡充 + 推論改善

```text
所要時間: 1-2週間 (データ準備含む)
期待効果: 話者類似度 +10-20% (Phase 2比)
```

1. JVS/JVNV等から話者追加 (目標100+話者)
2. speed perturbation
3. 推論時VAD適用
4. 複数参照音声平均 (`--speaker-audio-dir`)

### 全Phase合計の期待効果

- **Phase 1のみ**: +15-25% (未実装機能の修正)
- **Phase 1+2**: +20-35%
- **Phase 1+2+3**: +30-50%

---

## 6. 参考文献

- [Negated Speaker Representations - AAAI 2024](https://arxiv.org/abs/2401.02014)
- [Fox-TTS - Temporal Augmentation](https://openreview.net/forum?id=pWdkM9NNCA)
- [Time-Layer Adaptive Alignment - arXiv 2511.09995](https://arxiv.org/abs/2511.09995)
- [SEED - Speaker Embedding Enhancement Diffusion](https://arxiv.org/abs/2505.16798)
- [Information Perturbation for Zero-Shot TTS](https://pmc.ncbi.nlm.nih.gov/articles/PMC10708733/)
- [StyleTTS 2 - NeurIPS 2023](https://arxiv.org/abs/2306.07691)
- [CosyVoice 2](https://arxiv.org/html/2412.10117v1)
- [VITS2 - Interspeech 2023](https://www.isca-archive.org/interspeech_2023/kong23_interspeech.html)
- [DiffGAN-ZSTTS 2025](https://www.nature.com/articles/s41598-025-90507-0)
- [AdaSpeech 4 - Zero-Shot CLN](https://ar5iv.labs.arxiv.org/html/2204.00436)
- [Voice Cloning Survey 2025](https://arxiv.org/pdf/2505.00579)
- [BigVGAN - Snake Activation](https://arxiv.org/abs/2206.04658)
- [YourTTS - VITS Zero-Shot](https://arxiv.org/abs/2112.02418)
