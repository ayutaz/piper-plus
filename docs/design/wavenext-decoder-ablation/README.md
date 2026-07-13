# WaveNeXt Decoder Ablation (piper-plus v1.13+ 検討)

> **ブランチ**: `feat/wavenext-decoder-ablation` (dev から派生、起点 commit `d594cea2`、2026-07-14)
> **ステータス**: 調査完了 → 実装未着手 (blocker 解消 PR から段階着手予定)
> **目的**: 現行 MB-iSTFT-VITS2 decoder を GAN-WaveNeXt2 / WaveNeXt v1 に置換可能かを検証し、CPU 速度・保守負荷・zero-shot 品質のトレードオフを実測する

---

## TL;DR

- **完全置換 (現時点)**: ❌ 見送り — WaveNeXt 2 は IEEE copyright + 公式実装なし、品質改善は統計的にゼロ (UTMOS 4.04 vs HiFi-GAN 4.05)
- **WaveNeXt v1 の opt-in ablation**: ✅ 検証する価値あり — CPU 4x 高速化と ONNX グラフ 30-40% 縮小の実利を測定可能、失敗しても知見が Matcha-TTS / iSTFTNet2-MB / StyleTTS2 の設計判断に転移
- **GAN-WaveNeXt2 移植**: 🟡 Stage 1/2 が成功した場合の Stage 3 として位置付け (paper 再実装で XL 規模)
- **v8 本走との関係**: 独立ブランチで並行、v8 (MB-iSTFT のまま) の投資回収を妨げない

## この folder の構成

| ファイル | 内容 |
|---------|------|
| [`01-feasibility-investigation.md`](01-feasibility-investigation.md) | 18 エージェント workflow による 8 dimension 調査結果 (現行 decoder の coupling surface + WaveNeXt2 技術要件 + adversarial verify + 総合判定) |
| [`02-pros-cons-analysis.md`](02-pros-cons-analysis.md) | 置換によるメリット (6 軸) / デメリット (10 軸) の対照分析、paper 実測 MOS/RTF 数値含む |
| [`03-ablation-plan.md`](03-ablation-plan.md) | 3-stage 実装計画 (Stage 1: WaveNeXt v1 baseline / Stage 2: piper-plus 統合強化 / Stage 3: WaveNeXt 2 反復版)、blocker 解消 PR から始まる段階着手 |

## Quick reference

### 現行 decoder (置換対象)

- `src/python/piper_train/vits/mb_istft.py` (351 行) — MBiSTFTGenerator + PQMF
- `src/python/piper_train/vits/stft_onnx.py` (138 行) — iSTFT を Conv1d/ConvTranspose1d で実装
- `src/python/piper_train/vits/stft_loss.py` (143 行) — MultiResolutionSTFTLoss
- `src/python/piper_train/vits/lightning.py:361-368,1017-1022` — sub-band STFT loss 適用
- **合計 ~630 行が置換で削除可能 (deprecated 期間中は保持)**

### 置換候補モデル

| Model | Params | CPU RTF | UTMOS | 公式実装 | 22050Hz compat |
|---|---|---|---|---|---|
| **MB-iSTFT-VITS2** (現行) | ~30M | (27ms/25phoneme baseline) | 未計測 | ✅ piper-plus 内 | ✅ |
| **WaveNeXt v1** (Okamoto ASRU 2023) | 13.68M | 未実測 (推定 MB-iSTFT × 0.8-0.9) | 未計測 | 🟡 unofficial (wetdog MIT / BSC-LT Apache-2.0) | ✅ (BSC-LT/wavenext-mel が byte-compat) |
| **GAN-WaveNeXt 2** (paper arXiv:2605.25506) | **59.94M (4 iter)** | 0.20 (paper 実測) | 4.04 ± 0.09 | ❌ **なし (IEEE)** | ❌ (24kHz/hop=300) |
| HiFi-GAN V1 (参考) | 13.9M | 0.80 (paper 実測) | 4.05 ± 0.11 | ✅ | — |

### critical blocker (先行修正必須)

- `src/python/piper_train/__main__.py:39-53` — `_is_legacy_hifigan_checkpoint()` が `subband_conv_post`/`pqmf` 欠如を「レガシー HiFi-GAN」と誤検出。**WaveNeXt ckpt 書き出し瞬間に RuntimeError → tri-state 化が唯一の解**。副作用ゼロで v8 branch にも先行適用可。

## 関連ドキュメント

- [`docs/research/improvement-survey-2026-06-15.md`](../../research/improvement-survey-2026-06-15.md) — 31 アクションロードマップ (A-1 iSTFTNet2-MB / A-4 Matcha-TTS / A-5 StyleTTS2 と並列関係)
- [`docs/research/decoder-upgrades-istftnet2-and-mswavehax.md`](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) — vocoder 候補比較
- [`docs/design/zero-shot-v8-dataset-scaling-plan.md`](../zero-shot-v8-dataset-scaling-plan.md) — 並行進行中の v8 本走 (影響を受けない)
- [`docs/design/multi-6lang-zero-shot-v7-training-results.md`](../multi-6lang-zero-shot-v7-training-results.md) — v7 SECS 0.6879 baseline (Stage 1 のゴールライン)

## タイムライン (2026-07-14 時点)

| 日付 | イベント |
|------|---------|
| 2026-07-12 | 初期調査 (WaveNeXt2 とは何か / piper-plus での使用状況確認) |
| 2026-07-13 | ultracode workflow で 18 agent 調査完了、置換可能性判定 (moderate-refactor) |
| 2026-07-13 | pros/cons 分析 (paper 実測 MOS/RTF 統合) |
| 2026-07-14 | 独立検証方針で合意、`feat/wavenext-decoder-ablation` branch 作成 |
| — 未実施 — | Stage 0: `_is_legacy_hifigan_checkpoint` の tri-state 化 (blocker 解消) |
| — 未実施 — | Stage 1: WaveNeXt v1 baseline 実装 + smoke 学習 |
| — 未実施 — | Stage 2: piper-plus 統合強化 (Multi-scale FiLM 移植等) |
| — 未実施 — | Stage 3: WaveNeXt 2 反復版 (Stage 2 の go サイン後のみ) |
