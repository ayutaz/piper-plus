# WaveNeXt Decoder Ablation (piper-plus v1.13+ 検討)

> **ブランチ**: `feat/wavenext-decoder-ablation` (dev から派生、起点 commit `d594cea2`、2026-07-14)
> **ステータス**: Stage 1 コード実装完了 (wavenext.py + MRD + opset 17 export + tests 125 green) → **smoke 学習 (GPU) 待ち**。**本 ablation は単一ブランチ内で進行、途中 PR なし** (2026-07-14 方針)
> **目的**: 現行 MB-iSTFT-VITS2 decoder を GAN-WaveNeXt2 / WaveNeXt v1 に置換可能かを検証し、CPU 速度・保守負荷・zero-shot 品質のトレードオフを実測する

---

## TL;DR

- **完全置換 (現時点)**: ❌ 見送り — WaveNeXt 2 は IEEE copyright + 公式実装なし、品質改善は統計的にゼロ (UTMOS 4.04 vs HiFi-GAN 4.05)
- **WaveNeXt v1 の opt-in ablation**: ✅ 検証する価値あり — ただし速度前提は着手前検証の PoC 実測で**反転** ([`04-pre-stage0-verification.md`](04-pre-stage0-verification.md): ORT session contract 準拠スレッド設定で MB-iSTFT 比 **30-40% 遅い**、default threading では同等)。主目的は **bf16 安定化 + iSTFT/PQMF/complex トリック ~630 行撤去の保守性 + WaveNeXt 2 への足場 + canonical 環境 (Xeon) での速度白黒付け**に再定義。失敗しても知見が Matcha-TTS / iSTFTNet2-MB / StyleTTS2 の設計判断に転移
- **GAN-WaveNeXt2 移植**: 🟡 Stage 1/2 が成功した場合の Stage 3 として位置付け (paper 再実装で XL 規模)
- **v8 本走との関係**: 独立ブランチで並行、v8 (MB-iSTFT のまま) の投資回収を妨げない

## この folder の構成

| ファイル | 内容 |
|---------|------|
| [`01-feasibility-investigation.md`](01-feasibility-investigation.md) | 18 エージェント workflow による 8 dimension 調査結果 (現行 decoder の coupling surface + WaveNeXt2 技術要件 + adversarial verify + 総合判定) |
| [`02-pros-cons-analysis.md`](02-pros-cons-analysis.md) | 置換によるメリット (6 軸) / デメリット (10 軸) の対照分析、paper 実測 MOS/RTF 数値含む |
| [`03-ablation-plan.md`](03-ablation-plan.md) | 3-stage 実装計画 (Stage 1: WaveNeXt v1 baseline / Stage 2: piper-plus 統合強化 / Stage 3: WaveNeXt 2 反復版)、blocker 解消 PR から始まる段階着手 |
| [`04-pre-stage0-verification.md`](04-pre-stage0-verification.md) | Stage 0 着手前検証 (15-agent workflow + ローカル PoC) の結果 — 速度・サイズ前提の反転、fixture blocker 撤回、tri-state 分類器仕様確定、01-03 への正誤表 |

## Quick reference

### 現行 decoder (置換対象)

- `src/python/piper_train/vits/mb_istft.py` (351 行) — MBiSTFTGenerator + PQMF
- `src/python/piper_train/vits/stft_onnx.py` (138 行) — iSTFT を Conv1d/ConvTranspose1d で実装
- `src/python/piper_train/vits/stft_loss.py` (143 行) — MultiResolutionSTFTLoss
- `src/python/piper_train/vits/lightning.py:317-325,883-887` — sub-band STFT loss 適用 (PQMF/sub_stft instantiate + loss 加算)
- **合計 ~630 行が置換で削除可能 (deprecated 期間中は保持)**

### 置換候補モデル

| Model | Params | CPU RTF | UTMOS | 公式実装 | 22050Hz compat |
|---|---|---|---|---|---|
| **MB-iSTFT-VITS2** (現行) | ~30M (decoder 単体 1.65M 実測) | (27ms/25phoneme baseline) | 未計測 | ✅ piper-plus 内 | ✅ |
| **WaveNeXt v1** (Okamoto ASRU 2023) | 13.72M (80-mel 実測) / 14.12M (z=192) | PoC 実測: contract 準拠 (intra=4) で **MB-iSTFT 比 30-40% 遅い**、default threading では同等 (canonical Xeon 実測待ち、04 doc) | 未計測 | 🟡 unofficial (wetdog MIT / BSC-LT Apache-2.0) | ✅ (mel 設定は f_max のみ非互換 (8000 vs None→11025)、他は完全一致 — warm-start 可否は不変) |
| **GAN-WaveNeXt 2** (paper arXiv:2605.25506) | **59.94M (4 iter)** | 0.20 (paper 実測) | 4.04 ± 0.09 | ❌ **なし (IEEE)** | ❌ (24kHz/hop=300) |
| HiFi-GAN V1 (参考) | 13.9M | 0.80 (paper 実測) | 4.05 ± 0.11 | ✅ | — |

### critical blocker (先行修正必須)

- `src/python/piper_train/__main__.py:39-53` — `_is_legacy_hifigan_checkpoint()` が `subband_conv_post`/`pqmf` 欠如を「レガシー HiFi-GAN」と誤検出。発火は ~~ckpt 書き出し瞬間~~ ではなく**読み込み時の 2 経路** (call site は `__main__.py:479` = `--resume-from-multispeaker-checkpoint` で即時 raise / `:854` = trainer.fit 失敗後の graceful-resume fallback 内でのみ raise、04 doc で確定)。かつ `lightning.py:320` の pqmf 無条件注入が残る現行 bi-state では判定が False になり blocker 自体が発火しない (Stage 1 の pqmf gating への暗黙依存)。**tri-state 化が解**。副作用ゼロで v8 branch にも先行適用可。

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
| 2026-07-14 | Stage 0 着手前検証 (15-agent workflow + ローカル PoC) 完了 → [`04-pre-stage0-verification.md`](04-pre-stage0-verification.md) |
| 2026-07-14 | Stage 0 実装完了 (`a50d2b59`): tri-state 分類器 + `--decoder-arch` factory + tests 32 件 (blocker 解消) |
| 2026-07-14 | Stage 1 コード実装完了 (7-agent workflow): `wavenext.py` + `wavenext_losses.py` (MRD) + lightning/export 統合 + tests 52 件新規 (計 125 green) |
| — 未実施 — | Stage 1 smoke 学習 (GPU、A100×1 で 3-5 日) + GO/NO-GO 評価 |
| — 未実施 — | Stage 2: piper-plus 統合強化 (Multi-scale FiLM 移植等) |
| — 未実施 — | Stage 3: WaveNeXt 2 反復版 (Stage 2 の go サイン後のみ) |
