# A-1 / A-2 実装計画 (2026-06-16)

statistic 改善調査レポート [`improvement-survey-2026-06-15.md`](improvement-survey-2026-06-15.md) §A-1 (iSTFTNet2-MB backbone 1D→1D-2D 置換) と §A-2 (MS-Wavehax dual vocoder 併設) の **PoC 実装計画**。 companion deep-dive [`decoder-upgrades-istftnet2-and-mswavehax.md`](decoder-upgrades-istftnet2-and-mswavehax.md) の §2.5 Phase 4 deep-research 結果 (Risk 1=低 / Risk 2=高 / Risk 3=低) を前提とする。

**重要前提:** in-flight PR との衝突回避が本計画の核心。
- **PR #222** (Zero-shot TTS, CAM++ + DINO + Multi-scale FiLM): DRAFT + 25 日 stale、 mergeable=UNKNOWN、 emb_g 削除 + Flow dilation 変更 + MBiSTFTGenerator Multi-scale FiLM 化 + ONNX I/O 変更 (sid→speaker_embedding[192]) の **6 軸破壊的変更**を含むため **A-1/A-2 着手前のマージは強く非推奨**
- **PR #537** (Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一): OPEN/not-draft、 mergeable=CONFLICTING/DIRTY、 14 日 stale、 rebase 必須。 プラットフォーム層のみでコード衝突は NONE

**起点ブランチ:** `feat/decoder-istftnet2-mswavehax-poc` (off `dev` @ `fcddb997`)

**調査メタ情報:**
- 計画策定: 2026-06-16 (ultracode workflow w_zk0xg1g7)
- 4 phase: PR Inventory → Conflict Map → PoC Design → Synthesize
- PR 直接 diff 確認 + 9 ターゲットファイルの衝突マップ + 18 action items

---

## 1. Executive Summary

A-1 (iSTFTNet2-MB 1D-2D backbone) と A-2 (MS-Wavehax dual vocoder) を **CSS10 JA 単一話者**で並列 PoC し、 50 epoch baseline + 50 epoch A-1 + 30 epoch A-2 vocoder-only FT を **1 GPU 約 7 日**で完走する。 保険として **FLY-TTS** (ConvNeXt × 6 + iSTFT、 MOS 4.12 実証済み Interspeech 2024) を同条件で並走させ、 Q13 (zero prior art) 失敗時の即時切替先を確保する。

**核心トレードオフ 3 点:**

1. **PR #222 の Multi-scale FiLM 改造と HIGH conflict 必至** → A-1 は `MBiSTFTGenerator.forward` を `_forward_1d` (既存温存、 default) と `_forward_1d2d` (新規) に分離し、 `decoder_type` config 分岐で既存 1D 経路を保持。 PR #222 rebase コストを「FiLM の rank-aware 化のみ」に局所化
2. **A-2 dual vocoder の ONNX I/O 二重同期回避** → ONNX I/O を変えず **companion ONNX** (`tsukuyomi.wavehax.onnx`) として配布し 7 ランタイム ABI 同期は PR #222 既存 diff に乗せて 1 回に集約
3. **PR #537 の TF32-on / bf16-mixed / pytest 9 floor 移行** はプラットフォーム層なので**コード衝突なし**。 学習時のみ数値ドリフトを再 baseline 化 (audio-parity-contract.toml の tolerance 拡張)

---

## 2. PR #222 / #537 状態と Merge 順戦略

### 2.1 PR #222 (Zero-shot TTS) — 着手前 merge **強く非推奨**

| 項目 | 値 |
|------|----|
| status | **DRAFT (isDraft=true)** + 25 日 stale (updatedAt=2026-05-21) |
| mergeable | UNKNOWN (CI 再 trigger 必要) |
| 破壊的変更 | **6 軸** (emb_g 削除 / Flow dilation 1→2 / MBiSTFTGenerator Multi-scale FiLM 化 / ONNX I/O sid→speaker_embedding[192] / noise_scale デフォルト変更 / 7 ランタイム ABI 同期) |
| 残タスク | 200 epoch 再学習、 SECS/MCD 評価 |

**非推奨理由:**

- 既存 6lang base ckpt (`/data/piper/output-multilingual-6lang-mb-istft/`) が resume 不能になり、 A-1 PoC の warm start が失われる
- A-1 の backbone 置換は `MBiSTFTGenerator.forward` を再度書き換えるため #222 の Multi-scale FiLM 構造と衝突
- A-2 dual vocoder は `configure_optimizers` / EMA / WavLM Discriminator / `infer_forward` を二重化する必要があり #222 の単一 dec 前提と衝突
- PR #222 自体が「再学習未実施」「SECS/MCD 評価未実施」のまま DRAFT で stale、 マージ判断のための品質エビデンスが揃っていない

### 2.2 PR #537 (Python 3.13) — 並走可能、 merge 後に再 baseline

| 項目 | 値 |
|------|----|
| status | OPEN (not draft) + 14 日 stale (updatedAt=2026-06-01) |
| mergeable | **CONFLICTING (DIRTY)** — rebase 必須 |
| 影響範囲 | 108 ファイル、 +5003 / -446 (主にプラットフォーム層) |
| A-1/A-2 への影響 | コード衝突 **NONE**、 ただし TF32-on + bf16-mixed default で 1e-3 magnitude drift / pytest 9 fixture deprecation |

**並走戦略:**

- 現行 dev (torch 2.2 / py3.11 / CUDA 12.6) で A-1/A-2 PoC を完走
- PR #537 merge 後に bf16-mixed + pytest 9 で **再 benchmark** (audio-parity-contract.toml の tolerance 拡張)

### 2.3 推奨 Merge 順

```text
現在 → A-1 (本ブランチ) → A-2 (本ブランチ続行) → PR #537 → 再 baseline → PR #222 → 統合採否判定
       (1D 経路温存)     (companion ONNX)         (TF32 drift     (FiLM
                                                    再吸収)         rank-aware 化)
```

**この順序の利点:**

- A-1/A-2 を blocking なく即時着手可能
- PR #222 の 7 ランタイム ABI 同期 diff に A-1/A-2 の ONNX 変更が乗る形で 1 回完了
- PR #537 の数値ドリフトを A-1/A-2 PoC 後に 1 度だけ再 baseline 化 (audio-parity-contract.toml [mb_istft_1d] は不変)

---

## 3. Conflict Map (9 ターゲットファイル)

| ファイル | A-1/A-2 用途 | vs PR #222 | vs PR #537 | merge 順推奨 |
|---------|------------|-----------|-----------|------------|
| `src/python/piper_train/vits/mb_istft.py` | A-1 backbone 1D-2D 化、 `_forward_1d2d` 追加 | **HIGH** (Multi-scale FiLM 衝突) | NONE | **A-1 先行**、 PR #222 rebase で FiLM rank-aware 化 |
| `src/python/piper_train/vits/stft_onnx.py` | OnnxISTFT 追加 instance (FLY-TTS / A-2 用) | LOW | NONE | A-1/A-2 先行で OK |
| `src/python/piper_train/vits/models.py` | `dec_wavehax` sibling 追加、 `decoder_type` 受領 | **HIGH** (spk_proj 統合点) | NONE | **A-1/A-2 先行**で隔離 |
| `src/python/piper_train/vits/lightning.py` | `_collect_g_params` hook、 wavehax LR | MEDIUM (WavLM-D + DINO 拡張) | LOW (bf16-mixed) | A-1/A-2 先行で hook 化 |
| `src/python/piper_train/export_onnx.py` | A-1 Conv2d export、 `--decoder-branch wavehax` | MEDIUM (ONNX I/O 変更) | NONE | A-1/A-2 先行、 PR #222 rebase で I/O 同期 |
| `src/python_run/piper/text_splitter.py` | **編集禁止** (decoder-agnostic 維持) | NONE | NONE | 触らない |
| `src/python_run/piper/voice.py` | `wavehax_model_path` + streaming 閾値切替 | LOW | NONE | A-2 先行で OK |
| 7 ランタイム inference (Rust/C#/Go/WASM/C++/C-API) | A-2 companion ONNX load、 ABI 互換維持 | **HIGH** (PR #222 sid→speaker_embedding[192]) | LOW (Python 3.13 binding 影響なし) | **PR #222 と同時 sync** (二重同期回避) |
| `tools/benchmark/` + `tests/` | 3 variant 追加、 regression guard | NONE | LOW (pytest 9) | A-1/A-2 先行で OK |

---

## 4. PoC 設計 (Phase 1)

### 4.1 dataset: CSS10 JA

- **取得:** Kyubyong/css10 Japanese subset (約 14h)
- **配置:** `/data/piper/dataset-css10-ja-poc/`
- **前処理:** `prepare_multilingual_dataset.py --language ja --single-speaker --resample 22050` → LJSpeech 形式、 `add_prosody_features.py` で 16dim prosody 抽出
- **split:** train 6,200 / val 200 / test 200 utt、 `lid=0` 固定
- **disk:** ~8.3 GB (cached spec 含む)

### 4.2 A-1 iSTFTNet2-MB 1D-2D backbone

- **layer 構成:** Conv2d/ConvTranspose2d import、 `MBiSTFTGenerator.__init__` で `decoder_type` 受領
- **新規 `_forward_1d2d`:** `unsqueeze(F=1)` → **2D Block × 4** (kernel 3×3 / 3×5、 dilation (1,2)/(2,1)、 F: 1→2→4 pixel-shuffle) → squeeze → 既存 `subband_conv_post` → `OnnxISTFT(hop=4)` → PQMF
- **ConvTranspose 局所化:** `ups[0]/[1]` の 2 段のみで NNAPI/CoreML CPU fallback 最小化 (Phase 4 Risk 1 設計制約)
- **既存 `_forward_1d` 温存:** default 経路として残置、 6lang base ckpt の forward-only smoke 維持
- **目標 params:** 0.83M ± 0.05M
- **互換性制約:**
  - 出力 shape `[B, 1, T]` 不変
  - ONNX I/O 不変 (PR #222 と二重同期回避)
  - `subband_conv_post` / `OnnxISTFT` / `PQMF` は完全流用

### 4.3 A-2 MS-Wavehax dual vocoder

- **新規 `wavehax.py`:** spectral envelope + harmonic-aware shift + complex residual + `OnnxISTFT(n_fft=64, hop=16)`、 0.332M params
- **dual vocoder 統合:** `models.py:754` 直後で `enable_wavehax` 時に `self.dec_wavehax` を**既存 `self.dec` の sibling**として追加 (EMA `shadow_params` と `infer_forward model_g.dec(...)` 不変)
- **streaming 切替:** `PiperVoice.__init__` に `wavehax_model_path / streaming_threshold_phonemes=25` 引数追加、 `synthesize_stream` で `split_sentences` 後に phoneme 数で session 切替
- **配布:** **companion ONNX** (`tsukuyomi.wavehax.onnx`) として別ファイル化、 ONNX I/O 不変
- **text_splitter.py は touch しない** (decoder-agnostic 維持、 `text-splitter-contract.toml` も不変)

### 4.4 Training Plan

CLAUDE.md Template B (single-speaker FT) ベース:

- **epochs:** baseline 50 / A-1 50 / A-2 (vocoder-only FT) 30 / FLY-TTS 50
- **GPU:** 1 GPU (V100 想定なら `--precision 32-true` 必須、 `--no-wavlm` 推奨)
- **batch:** 4、 samples-per-speaker 4
- **base_lr:** 2e-5、 ema-decay 0.9995
- **推定時間 (1 GPU):**
  - baseline 50ep: ~36h
  - A-1 50ep: ~40h (2D conv で +10%)
  - A-2 30ep vocoder-only: ~12h
  - FLY-TTS 50ep: ~32h
  - **合計: 約 5 日 (並走で短縮)**

### 4.5 FLY-TTS 並走 (失敗時の保険)

- **rationale:** Q13 (iSTFTNet2 specific MOS) が zero prior art。 A-1 失敗時 (MOS 劣化 / RTF 退化) の即時切替先
- **architecture:** ConvNeXt × 6 (DepthwiseConv1d k=7 + LayerNorm + Conv1d 1×1 expand 4× + GELU + project) + 単一帯域 iSTFT (n_fft=1024, hop=256)、 0.63M params
- **PQMF 不使用、 sub-band loss 無効** (`--c-sub-stft 0.0`)
- **新規 `fly_decoder.py`** (~200 LoC)、 既存 `stft_onnx.py:OnnxISTFT` に追加 instance を生やすのみ
- **採否判断基準:** A-1 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) すべて baseline 超過なら A-1 採用、 1 つでも未達なら FLY-TTS 100 epoch 延長、 両方ダメなら 1D 継続 + A-4/A-5 (Matcha/StyleTTS2) ライン昇格

### 4.6 Benchmarks 目標値

- **CPU RTF (Xeon E5-2650 v4 / 25 phoneme 英文):** baseline 27ms → **target 18ms** (× 0.7)
- **MOS (UTMOS proxy、 200 test utt):** baseline ± 0.1 以内
- **footprint:** 0.83M params (A-1)、 0.332M params (A-2 companion)
- **7 ランタイム smoke:** Python/Rust/Go/C#/WASM/C++/C-API で `[1,1,T]` float32、 pairwise SNR ≥ 30 dB
- **regression guard:** [mb_istft_1d] 既存 baseline 完全不変 (CI gate で編集禁止)

---

## 5. Milestones (6 件、 機能名ベース)

| # | Milestone | Deliverable | Depends on | Weeks | Exit Criteria |
|---|-----------|-------------|------------|-------|---------------|
| 1 | **CSS10 JA PoC データセット整備** | `/data/piper/dataset-css10-ja-poc/processed` 完備 (train 6,200 / val 200 / test 200、 ~8.3GB) | — | 0.2 | `uv run python -m piper_train --dataset-dir` で 1 epoch sanity + WandB audio log |
| 2 | **iSTFTNet2-MB 1D-2D backbone PoC 動作確認** | `mb_istft.py` に `decoder_type` 分岐 + 0.83M params 1D-2D backbone、 forward + ONNX export + 50 epoch 学習完走 | 1 | 2 | test_istftnet2_generator.py green / default で 6lang base resume / UTMOS baseline ± 0.1 / Xeon p50 < 20ms |
| 3 | **FLY-TTS 並走 harness 構築** | `fly_decoder.py` (~200 LoC) + 50 epoch 学習 + ONNX export + 7 ランタイム smoke | 1 | 2 | proxy MOS baseline ± 0.1 / CPU RTF × 0.85 以下 / ONNX op Conv1d+LayerNorm のみ |
| 4 | **MS-Wavehax dual vocoder PoC 動作確認** | `wavehax.py` + sibling `dec_wavehax` + 30 epoch vocoder-only FT + streaming 閾値切替 | 2 | 1.5 | companion ONNX export / sub-80ms streaming chunk で MB-iSTFT 比低 p50 / MOS baseline ± 0.15 |
| 5 | **7 ランタイム ABI 検証 + audio-parity 再 baseline** | Python/Rust/Go/C#/WASM/C++/C-API で smoke + pairwise SNR≥30dB、 `audio-parity-contract.toml` に新 variant section | 2, 4 | 1.5 | 全 7 runtime [1,1,T] float32 / SNR≥30dB / ONNX op audit / README 27ms benchmark 再測定 |
| 6 | **PR #222 / #537 rebase 取込と統合判定** | PR #537 後の bf16-mixed + pytest 9 再 benchmark、 PR #222 後の FiLM rank-aware 化 + ONNX I/O 同期、 採否判定 | 5, 3, **PR #537 merge**, **PR #222 merge** | 2 | rebase 後 audio-parity test green / 採否判定 PR body 記載 |

**合計推定: 約 9 週間** (1-3 milestone は並走可能で短縮余地あり)

---

## 6. Action Items (18 件、 依存付き)

凡例: `[blocked by]` で前提を明示。

### Milestone 1: CSS10 JA PoC データセット整備

- **AI-01** CSS10 JA データセット取得 + 前処理 (0.5d、 blocked by: なし)
  - Kyubyong/css10 Japanese subset DL → `prepare_multilingual_dataset.py --language ja --single-speaker --resample 22050` → `add_prosody_features.py` で 16dim prosody → train/val/test split
- **AI-02** 既存 1D MB-iSTFT baseline 学習 50 epoch (1.5d、 blocked by: AI-01)
  - `decoder_type='mb_istft_1d'` で 6lang base ckpt から resume、 noise_scale=0.667 固定 (PR #222 default 変更影響を排除)

### Milestone 2: iSTFTNet2-MB 1D-2D backbone PoC

- **AI-03** iSTFTNet2-MB 1D-2D backbone 実装 (3d、 blocked by: AI-01)
  - `mb_istft.py:14` で `Conv2d`/`ConvTranspose2d` import、 `MBiSTFTGenerator.__init__` で `decoder_type` 受領
  - `_forward_1d2d` 新規: `unsqueeze(F=1)` + 2D Block × 4 + squeeze + 既存 `subband_conv_post` → `OnnxISTFT(hop=4)` → PQMF
  - **既存 `_forward_1d` は温存** (default 経路、 G-1.9 後方互換 gate)
- **AI-04** iSTFTNet2-MB ユニットテスト追加 (0.5d、 blocked by: AI-03)
  - `src/python/tests/test_istftnet2_generator.py` 新規、 既存 `test_mb_istft_generator.py` は touch しない
- **AI-05** iSTFTNet2-MB PoC 学習 50 epoch (1.5d、 blocked by: AI-03, AI-04)
  - `decoder_type='istftnet2_mb_1d2d'`、 6lang base ckpt から 1D 部分のみ warm start

### Milestone 3: FLY-TTS 並走 harness

- **AI-06** FLY-TTS ConvNeXt6 decoder 実装 (2d、 blocked by: AI-01)
  - `fly_decoder.py` 新規 (~200 LoC)、 ConvNeXt × 6 + Conv1d(256→1026) + OnnxISTFT(n_fft=1024, hop=256)、 PQMF 不使用
- **AI-07** FLY-TTS PoC 学習 50 epoch (1.5d、 blocked by: AI-06)
  - `--c-sub-stft 0.0` で sub-band loss 無効

### Milestone 4: MS-Wavehax dual vocoder PoC

- **AI-08** MS-Wavehax vocoder 実装 + dual vocoder 統合 (2.5d、 blocked by: AI-02)
  - `wavehax.py` 新規、 `models.py:754` で `enable_wavehax` 時に sibling `self.dec_wavehax`
- **AI-09** `configure_optimizers` に `_collect_g_params` hook 追加 (1d、 blocked by: AI-08)
  - PR #222 rebase 時の WavLM-D + DINO opt_d/opt_g 拡張と非衝突に保つ (B5 mitigation)
- **AI-10** MS-Wavehax vocoder-only FT 学習 30 epoch (1d、 blocked by: AI-09)
  - A-1 baseline ckpt を acoustic model として freeze、 `--enable-wavehax --freeze-acoustic --wavehax-lr 2e-4`
- **AI-11** `voice.py` に `wavehax_model_path` + streaming 閾値切替実装 (1d、 blocked by: AI-10)
  - `text_splitter.py` は decoder-agnostic 維持 (touch しない)

### Milestone 5: 7 ランタイム ABI 検証 + audio-parity 再 baseline

- **AI-12** `tools/benchmark/` に 3 variant 追加 + UTMOS proxy MOS (1.5d、 blocked by: AI-05, AI-07, AI-10)
  - `models.yaml` に css10-ja-1d-baseline / istftnet2-mb / fly-convnext6 の 3 entry、 `proxy_mos.py` 新規 (UTMOS v2 wrapper)
- **AI-13** 7 ランタイム smoke + pairwise SNR 検証 (3d、 blocked by: AI-12)
  - Rust new_with_wavehax / Go option pattern / C# optional named arg / C-API 新 entry、 ABI 互換維持
- **AI-14** `audio-parity-contract.toml` に新 variant section 追加 (1d、 blocked by: AI-13)
  - `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` 追加、 **`[mb_istft_1d]` は absolutely touch しない** (G-1.2 gate)
- **AI-15** regression guard CI gate 整備 (1.5d、 blocked by: AI-14)
  - default decoder_type assert、 ONNX I/O 不変 audit、 expected_p50_ms gate、 freeze-dp 互換 test、 PR #222/#537 衝突回避 checklist 機械 check

### Milestone 6: PR #222 / #537 rebase 取込と統合判定

- **AI-16** PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark (2d、 blocked by: AI-15, **PR #537 merge**)
  - ubuntu-24.04 + py3.13 + torch 2.11 で全 variant 5 epoch sanity + ONNX export + benchmark 再測定
  - TF32 が招く 1e-3 magnitude drift を audio-parity-contract.toml の tolerance に反映
- **AI-17** PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期 (3d、 blocked by: AI-16, **PR #222 merge**)
  - `_apply_film` を rank-aware (1D=split dim=1 / 2D=split dim=1 維持) に拡張、 `cond_layers` の channel schedule を `decoder_type` 別に保持
  - ONNX I/O の `sid → speaker_embedding[192]` 変更を A-1/A-2 export 経路 (companion ONNX 含む) で反映
  - 7 ランタイム ABI 同期は PR #222 既存 diff に乗る形で **1 回完了**
- **AI-18** 採否判定レポート作成と統合 PR 提出 (2d、 blocked by: AI-17)
  - 4 指標 (UTMOS / CPU RTF / ONNX op coverage / 7 ランタイム smoke) で採否判断
  - A-1 採用 / FLY-TTS 切替 / 1D 継続のいずれかを PR body に記載し `/create-pr` で提出

---

## 7. Risk Register (8 件)

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | PR #222 MBiSTFTGenerator の Multi-scale FiLM が A-1 1D-2D backbone と forward 構造で HIGH conflict、 `_apply_film` が channel-axis split (dim=1) 前提のため 4D ([B,C,F,T]) で破綻 | HIGH | HIGH | A-1 を PR #222 より**先行 merge**、 forward を `_forward_1d` / `_forward_1d2d` に分離、 PR #222 rebase 時に `_apply_film` を rank-aware に拡張する差分のみで吸収 |
| R2 | PR #222 の emb_g 完全削除 + Flow dilation 1→2 で 6lang MB-iSTFT base ckpt が resume 不能、 A-1 warm start (1D 部分の conv_pre/cond/iSTFT/PQMF 再利用) が失われる | HIGH | MEDIUM | A-1 PoC は PR #222 merge **前**の現行 dev で実施。 `--from-scratch` 並走の fall back を Day 0 から準備。 PR #222 に emb_g→spk_proj 重み移行スクリプト提出を依頼 |
| R3 | Q13 (iSTFTNet2-MB zero prior art) で 50 epoch 投資後に proxy MOS -0.3 以上の劣化、 または CPU RTF 退化で A-1 失敗 | MEDIUM | HIGH | FLY-TTS を同 CSS10 JA で並走、 Day 5 までに ONNX export + 7 ランタイム smoke 完了。 A-1 失敗時は Day 4 評価で即時 FLY-TTS 100 epoch 延長に切替。 両方ダメなら 1D 継続 + A-4/A-5 ライン昇格 |
| R4 | A-2 dual vocoder の companion ONNX 配布で `voice.py` / 7 ランタイム の `PiperVoice __init__` 引数追加が ABI 破壊と誤認、 もしくは PR #222 rebase 後の ONNX I/O 変更と二重同期 | MEDIUM | MEDIUM | optional named arg / Rust new_with_wavehax 新メソッド / Go option pattern / C-API 新 entry で既存 ABI 完全互換維持。 ONNX I/O は companion ONNX も同 contract に固定し PR #222 の 7 ランタイム同期 diff に乗せて 1 回で完了 |
| R5 | PR #537 の TF32-on + bf16-mixed default + NumPy 2.x が A-2 MS-Wavehax の torch.fft / wavelet ops を破壊、 または pytest 7→9 で既存 mb_istft fixture が deprecation で fail | MEDIUM | MEDIUM | A-2 PoC は PR #537 merge 前に現行 torch 2.2 で完走、 PR #537 merge 後に torch-2.11 sandbox で FFT op 互換 check + 5 epoch sanity 再学習。 pytest 9 deprecation は別 PR で独立追従し A-1/A-2 PR を blocking させない |
| R6 | `audio-parity-contract.toml` の baseline regression を A-1/A-2 が誤って書き換え、 既存 1D MB-iSTFT への regression を silently 招く | MEDIUM | HIGH | `[mb_istft_1d]` section 編集禁止 gate (`scripts/check_audio_parity_baseline.py` + `contract-gates.yml` workflow) を AI-14 で導入。 新 variant は必ず別 section として併載。 PR body checklist で機械 check |
| R7 | iSTFTNet2-MB の 2D op (Conv2d / Reshape / Transpose) が将来の iOS CoreML MLProgram / Android NNAPI でも CPU fallback が起きないことを PoC 段階で検証していない | LOW | MEDIUM | ConvTranspose を `ups[0]/[1]` の 2 段のみに局所化、 F 軸拡大は pixel-shuffle (Reshape+Transpose) で実装し ConvTranspose2d 完全不使用。 op set audit で Conv2d/Reshape/Transpose のみを CI で assert。 mobile EP smoke は PoC 範囲外 |
| R8 | 1 GPU 直列スケジュール (7 日) が GPU 占有他作業と衝突、 もしくは FLY-TTS 並走で Day 5-6 の GPU 確保ができず保険切替判断が遅延 | MEDIUM | LOW | FLY-TTS 並走は A-1 PoC 結果 (Day 4 評価) 次第で条件起動とし default で blocking しない。 2 GPU 確保できれば A-1 baseline + A-1 PoC 同時走行で 2 日短縮。 GPU 競合時は CSS10 JA 14h を 7h subset に絞り epoch 数 2 倍で代替 |

---

## 8. Immediate Next Steps (PR merge 待ちの間に着手可能)

PR #222 / #537 の状況に関係なく、 本ブランチで**即時着手できる**作業 5 件:

1. **AI-01 着手:** `/data/piper/dataset-css10-ja-poc/` を作成し Kyubyong/css10 Japanese subset の DL + `prepare_multilingual_dataset.py --language ja --single-speaker --resample 22050` で LJSpeech 形式化 + prosody npz 抽出を完了 (PR #222/#537 merge 不要、 現行 dev で即時実行可)
2. **AI-03 着手:** `mb_istft.py` に `decoder_type` 分岐を実装 (`_forward_1d` 温存 + `_forward_1d2d` 新規)。 既存 1D 経路を default に保つことで PR #222 / #537 merge 前後どちらでも単独完結する形にする。 同時に `test_istftnet2_generator.py` (AI-04) を **TDD** で先に書く
3. **AI-06 着手:** `fly_decoder.py` を `mb_istft.py` と独立した新ファイルとして実装 (~200 LoC)。 衝突マップで NONE / NONE と確定しているため PR #222/#537 merge 待ちなしで完了可能。 A-1 失敗時の Day 4 即時切替先として Day 2 までに forward + ONNX export smoke を通す
4. **AI-15 の部分着手:** `scripts/check_audio_parity_baseline.py` と `scripts/check_a1_a2_isolation.py` の skeleton を先に書き、 `.pre-commit-config.yaml` に commit-msg hook として登録。 これで PR #222/#537 衝突回避 checklist が以後の全 PR で機械 check される
5. **PR #222 / #537 状況監視:** `/loop /watch-pr 222` と `/loop /watch-pr 537` を週次で起動し、 DRAFT → ready / CONFLICTING → CLEAN 遷移を即時検知。 PR #222 が ready になり次第 reviewer として `_apply_film` rank-aware 化と emb_g→spk_proj 重み移行スクリプトをリクエスト

---

## 9. 関連ドキュメント

- 統合改善調査レポート: [`improvement-survey-2026-06-15.md`](improvement-survey-2026-06-15.md) §A-1, §A-2, §H Track 7
- Decoder Upgrade deep-dive: [`decoder-upgrades-istftnet2-and-mswavehax.md`](decoder-upgrades-istftnet2-and-mswavehax.md) §2.5 (Phase 4 Risk 評価) / §5 (推奨実装フェーズ)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537)
- 既存仕様:
  - [`docs/spec/audio-parity-contract.toml`](../spec/audio-parity-contract.toml) — `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` section 追加予定
  - [`docs/spec/ort-session-contract.toml`](../spec/ort-session-contract.toml) — QNN HTP bucket 仕様追記提言 (companion §7)
  - [`docs/spec/text-splitter-contract.toml`](../spec/text-splitter-contract.toml) — **編集禁止** (decoder-agnostic 維持)
- 論文:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023, NTT)
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) MS-Wavehax (Yoneyama et al., Interspeech 2025)
  - [FLY-TTS PDF (Guo Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf) ConvNeXt × 6 + iSTFT
