# 03. Ablation Plan — 3-Stage 段階着手計画

> **前提**: `feat/wavenext-decoder-ablation` (dev 起点、`d594cea2`) で独立実施、v8 本走との干渉なし
> **ゴール**: 各 Stage で明確な GO/NO-GO 判断基準を設け、次 Stage 着手を実測データで gate 化
> **全 Stage 完走見込み**: Stage 0-2 で 6-9 週間、Stage 3 追加時は +2-3 ヶ月

---

## Stage 0: Blocker 解消 (先行、~1 週間)

副作用ゼロで実装できる **silent bomb 解除** + factory インフラ構築。WaveNeXt 実装本体は含まず、MB-iSTFT 動作は完全維持。

### 実装内容

| ファイル:行 | 変更 |
|-----------|------|
| `src/python/piper_train/__main__.py:39-53` | `_is_legacy_hifigan_checkpoint()` を **tri-state 分類器 (`mb_istft` / `hifigan` / `wavenext`)** に refactor。positive detection: (a) ckpt hparams に `decoder_arch` タグがあればそれを採用、(b) fallback で state_dict のマーカー (`subband_conv_post`/`pqmf` → mb_istft, `convnext_blocks.*`/`head.linear_1` → wavenext, HiFi-GAN 固有 `conv_post` → hifigan) を検出 |
| `src/python/piper_train/__main__.py:285-291` | `--decoder-arch {mb_istft,wavenext,wavenext2}` CLI flag 追加 (default `mb_istft`)。`VitsModel.add_model_specific_args` にも同 arg を追加し hparams.yaml に永続化 |
| `src/python/piper_train/__main__.py:607,981,1063` | `_is_legacy_hifigan_checkpoint(...)` 呼び出しを新 tri-state 分類器に置換、arch mismatch 時は `WRONG_DECODER_ARCH_MESSAGE` (新規、partial-transfer FT 手順への URL 込) を raise |
| `src/python/piper_train/__main__.py:891-896` | `dict_args['upsample_rates']=(4,4)` / `upsample_kernel_sizes=(16,16)` を `if args.decoder_arch == 'mb_istft':` で gate 化 (WaveNeXt 分岐は Stage 1 で追加) |
| `src/python/piper_train/vits/models.py:810-820` | `SynthesizerTrn.__init__` で factory dispatch: `if decoder_arch == 'mb_istft': self.dec = MBiSTFTGenerator(...) elif decoder_arch == 'wavenext': self.dec = WaveNeXtGenerator(...)` (WaveNeXtGenerator は Stage 1 で追加、Stage 0 では `NotImplementedError` stub) |

### テスト

- 既存 `test_hifigan_ckpt_rejection.py` を tri-state 化に合わせて更新
- 新規 `test_decoder_arch_dispatch.py`: `--decoder-arch mb_istft` で MB-iSTFT が instantiate されることを確認

### GO/NO-GO 判断

- ✅ CI 全緑 + 既存の v7/v8 ckpt が `decoder_arch='mb_istft'` として silent に読み込まれる → Stage 1 へ
- ❌ 既存 test が落ちる、v7 ckpt resume が壊れる → 修正して retry

### この Stage の価値 (Stage 1 に進まなくても)

- WaveNeXt を将来採用しない場合でも **silent bomb 解除**は完了 → 誰かが WaveNeXt を試そうとしたときの詰みを予防
- **v8 branch に cherry-pick 可能** (副作用ゼロ) → v8 本走のリスクも下がる

---

## Stage 1: WaveNeXt v1 baseline 実装 + smoke 学習 (2-3 週間)

### 実装内容

**新規ファイル: `src/python/piper_train/vits/wavenext.py`**

```python
# 概要 (実装スケルトン)
class ConvNeXtBlock(nn.Module):
    """
    depthwise Conv1d(k=7, groups=dim) → LayerNorm → Linear(dim, intermediate_dim)
      → GELU → Linear(intermediate_dim, dim) → LayerScale(γ_init=1e-6) → residual
    """
    def __init__(self, dim=512, intermediate_dim=1536, adanorm_num_embeddings=0):
        ...  # AdaLayerNorm 経路は speaker/language conditioning 用に予約

class WaveNextHead(nn.Module):
    """
    Linear(512, 1026) → Linear(1026, hop_length=256, bias=False)
      → view(B, -1) → clip(-1, 1) → unsqueeze(1)  # [B, 1, T]
    """

class WaveNeXtGenerator(nn.Module):
    """
    Input:  z * y_mask  [B, inter_channels=192, L]
    Output: waveform    [B, 1, T=L*hop_length]

    Pipeline:
      Conv1d(192, 512, k=1)  # input projection
      → 8 × ConvNeXtBlock(dim=512, intermediate_dim=1536)
      → LayerNorm
      → WaveNextHead
    """
    def remove_weight_norm(self):
        pass  # no-op stub (export_onnx.py などから呼ばれるため必須)

    def set_export_mode(self, mode):
        pass  # onnx_export_mode 属性の互換用

    # gin_channels > 0 の場合、Multi-scale FiLM を AdaLayerNorm 経由で
    # 各 ConvNeXtBlock の LayerNorm に注入 (v7 の speaker conditioning 経路)
```

### 統合ポイント

| ファイル:行 | 変更 |
|-----------|------|
| `src/python/piper_train/vits/models.py:11` | `from .wavenext import WaveNeXtGenerator` 追加 |
| `src/python/piper_train/vits/models.py:810-820` | Stage 0 で用意した factory dispatch の `wavenext` 分岐を有効化 |
| `src/python/piper_train/vits/models.py:1068,1187` | `dec_out = self.dec(...); o, o_mb = dec_out if isinstance(dec_out, tuple) else (dec_out, None)` に書き換え |
| `src/python/piper_train/vits/models.py:1160-1163` | `SynthesizerTrn.infer` 出口で `if o.dim() == 2: o = o.unsqueeze(1)` を挿入 (rank-3 復元) |
| `src/python/piper_train/__main__.py:891-896` | WaveNeXt 分岐で `wavenext_dim=512 / intermediate_dim=1536 / num_blocks=8 / head_hop_length=256` を注入 |
| `src/python/piper_train/vits/lightning.py:24,31` | import を gate 化: WaveNeXt 選択時は `PQMF` / `MultiResolutionSTFTLoss` (sub-band 用) を skip |
| `src/python/piper_train/vits/lightning.py:361-368` | `if decoder_arch == 'wavenext':` で PQMF / sub_stft_loss の instantiate を skip、代わりに `MelSpecReconstructionLoss` (128-mel, coeff=45) + `MultiResolutionDiscriminator` (fft 2048/1024/512, hinge, coeff=0.1) を追加 |
| `src/python/piper_train/vits/lightning.py:1017-1022` | `if o_mb is not None:` guard は既存、`decoder_arch='wavenext'` で `o_mb=None` なら自動 skip → fullband path で `loss_mrstft` + `loss_mrd_gen + loss_mrd_fm` を追加 |
| `src/python/piper_train/export_onnx.py:27` | OPSET_VERSION 15 → 17 (opset 15 でも動作するが LayerNorm native op の cleanliness で推奨) |

### 新規 loss module

**`src/python/piper_train/vits/wavenext_losses.py`**:
- `MelSpecReconstructionLoss` (128-mel bin analysis、Vocos 準拠)
- `MultiResolutionDiscriminator` (DAC-style、fft 2048/1024/512)
- feature matching loss (既存を再利用可能なら流用)

### テスト

- `test_wavenext_generator.py`: forward pass shape 検証、gin_channels 条件付け、`remove_weight_norm()` no-op 動作
- `test_synthesizer_trn_wavenext.py`: `decoder_arch='wavenext'` で SynthesizerTrn が正常構築
- `test_export_onnx_wavenext.py`: opset 17 で export 成功、output shape `[1, 1, T]`
- 既存 `test_*_mb_istft.py` 系は `decoder_arch='mb_istft'` を明示して継続動作

### Smoke 学習

**環境**: A100×1、bf16-mixed、6-lang partial-transfer FT

```bash
# Option A: BSC-LT/wavenext-mel init から (推奨)
# 1. HF から BSC-LT/wavenext-mel の decoder weight を download
# 2. 入力 Conv1d (192-latent) のみスクラッチ、backbone + head は BSC-LT init

python -m piper_train \
    --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
    --decoder-arch wavenext \
    --wavenext-init /data/piper/models/wavenext-mel-bsclt.pt \
    --resume-from-multispeaker-checkpoint /data/piper/output-zero-shot-multi-6lang-v7/checkpoints/epoch=32-step=216326.ckpt \
    --resume-encoder-only \
    --accelerator gpu --devices 1 --precision bf16-mixed \
    --max_epochs 20 --batch-size 32 --samples-per-speaker 2 \
    --base_lr 1e-4 --disable_auto_lr_scaling \
    --ema-decay 0.9995 --max-phoneme-ids 400 \
    --c-mrstft 1.0 --c-mrd 0.1 --mel-loss-coeff 45 \
    --pretrain-mel-steps 5000 \
    --default_root_dir /data/piper/output-wavenext-v1-smoke \
    > wavenext-smoke.log 2>&1 &
```

期間目安: A100×1 で 3-5 日 (batch=32、6-lang 50k steps 想定)。

### 評価

- **SECS (CAM++)**: v7 zero-shot ep32 baseline **0.6879 (未知話者)** と比較
- **CPU RTF**: `docker/python-inference/inference.py` で 25 phoneme 英文 x 30 runs、Xeon E5-2650 v4 相当環境で計測、現行 MB-iSTFT `~27ms` baseline と比較
- **ONNX size**: FP16 export 後のファイルサイズ、現行と比較
- **PESQ/STOI (JA/ZH サ行)**: 既知話者音声との A/B、既知弱点音素の退化検出
- **主観 A/B**: つくよみちゃん FT ONNX の再現、MB-iSTFT 版と聴き比べ

### GO/NO-GO 判断基準

| 結果パターン | 判定 | 次アクション |
|-------------|------|------------|
| SECS ≥ 0.6879 && CPU RTF < 現行 && MOS 同等 | ✅ GO (default 昇格候補) | Stage 2 で統合強化 + 6-lang scratch で本格投入 |
| SECS ~ 0.65-0.68 && 速度 win / 品質同等 | 🟡 CONDITIONAL GO (opt-in flag) | Stage 2 で Multi-scale FiLM 移植を試す、駄目なら opt-in flag として merge |
| SECS < 0.65 or JA/ZH サ行大幅退化 | ❌ NO-GO (Stage 2 に進まない) | 知見を Matcha-TTS / iSTFTNet2-MB / StyleTTS2 の設計判断に転用、ablation を `docs/research/` に log |

---

## Stage 2: piper-plus 統合強化 (2-4 週間、Stage 1 が go の場合のみ)

Stage 1 で「WaveNeXt v1 が動くが v7 baseline に届かない」の場合、piper-plus 独自機構を新 decoder に移植して補償。

### 実装内容 (優先順位順)

**S2-A. Multi-scale FiLM の ConvNeXtBlock 移植**
- v7 の 5 サイト FiLM (input-stage + 4 upsample 段) を `ConvNeXtBlock.LayerNorm` の AdaLayerNorm 経路に注入
- 2 案 ablation:
  - (a) 全 8 block の LayerNorm に AdaLayerNorm 適用
  - (b) 前半 4 block + 後半 4 block でスケール切り替え (Multi-scale の再現)
- 目標: v7 SECS 0.6879 レベルの zero-shot 能力

**S2-B. sub-band → MRD 補償の言語別 tuning**
- Stage 1 で JA/ZH サ行退化した場合、`mel_loss_coeff` を言語別に調整
- MRD の fft_sizes を JA (2048/1024/512) と ZH (別セット) で個別最適化するか検討

**S2-C. Tsukuyomi FT の再現**
- v7 base → 100 utterance Tsukuyomi 再 FT、500 epoch
- 目標: SECS 0.7749 (現行 MB-iSTFT 版) レベルの再現性
- MB-iSTFT 版と主観 A/B 聴き比べ

**S2-D. 6-lang scratch 本格学習**
- Stage 1 smoke が go だった場合のみ
- A100×4、bf16-mixed、6-lang 800k-1M steps、~2-3 週間
- 目標: v7 SECS baseline (0.6879) 超え + CPU RTF < 現行

### 評価

- SECS (未知話者 / 既知話者)
- CPU RTF (Xeon E5-2650 v4 相当)
- ONNX FP16 size
- MOS 主観テスト (n=10 程度、JA/EN/ZH の 3 言語で pairwise A/B)
- PESQ/STOI (JA/ZH サ行を含む文セット)

### GO/NO-GO 判断基準

| 結果パターン | 判定 | 次アクション |
|-------------|------|------------|
| Multi-scale FiLM 移植で SECS ≥ 0.6879 && MOS 同等 or 上位 | ✅ v1.13 default 昇格候補 | v1.13 release として本格 merge、Stage 3 検討 |
| SECS 微増だが Tsukuyomi FT 品質が MB-iSTFT 版に届かない | 🟡 opt-in flag として merge (BC 維持) | 開発者向け experimental flag として release、default は MB-iSTFT |
| 全指標で改善なし or 退化 | ❌ 見送り | 知見を `docs/research/wavenext-ablation-results.md` に log、Matcha-TTS / iSTFTNet2-MB へ pivot |

---

## Stage 3: WaveNeXt 2 反復版 (2-3 ヶ月、Stage 2 が明確に superior な場合のみ)

Stage 2 で WaveNeXt v1 が v1.13 default 候補になった場合のみ、更なる品質改善候補として WaveNeXt 2 の 3-pass 反復版を検討。

### 実装内容 (paper §2-3 からの再実装)

**S3-A. Residual denoising path**
- Generator は noise `n_t` を予測、`y_{t-1} = y_t - n_t` で feedback
- 前波形の STFT (real + imag、Hann window) を auxiliary input として mel-spec と concat

**S3-B. Sub-modeling (3-pass fixed-point iteration)**
- WaveFit-style unrolled iteration を ONNX single-pass に展開
- opset 17 の native `STFT` op を利用 (float32 only、FP16 STFT 非対応)
- **sub-model weight 共有 vs 独立**の 2 案 ablation (paper 内不明確なため)

**S3-C. WaveFit loss 逆算**
- WaveFit paper §3.3 を読み込み、STFT loss (multi-resolution mag+phase) + fixed-point unrolling loss の係数 λ を pin
- Diff-WaveNeXt 2 (Diff mode) は Stage 3 では対象外 (paper の UTMOS 3.87 < GAN mode 4.04 のため実利小)

### リスク

- IEEE copyright、公式 reference 実装なし → 実装差異による品質 drift の判別困難
- 3-4x パラメータ数 (59.94M) → CPU on-device / mobile fit で不利
- 24kHz → 22050Hz 適合検証で追加の学習リソース必要

### GO/NO-GO 判断基準

- Stage 3 は「Stage 2 で WaveNeXt v1 が MB-iSTFT を SECS/MOS で明確に上回った場合のみ」の gate 付き着手
- パラメータ数 4x と品質 gain (paper で UTMOS +0.02 程度) の見合いが取れない場合は着手しない
- 代わりに WaveNeXt v1 + piper-plus 独自改善 (Multi-scale FiLM 発展) の方向を優先

---

## PR 分割戦略

Stage 単位ではなく、review しやすい粒度で分割:

| PR | 内容 | 依存 | 目安 lines changed |
|----|------|------|-------------------|
| **PR #1** | Stage 0: blocker 解消 (tri-state 化 + `--decoder-arch` factory) | 単独 (dev merge 可能) | ~200 |
| **PR #2** | `wavenext.py` + loss module + test (実装のみ、学習なし) | PR #1 | ~800 |
| **PR #3** | Stage 1 smoke 学習の結果 log + 評価スクリプト + `docs/research/wavenext-ablation-results.md` | PR #2 | ~300 (docs 中心) |
| **PR #4** | (条件付き) Stage 2 Multi-scale FiLM 移植 + Tsukuyomi FT | PR #3 の GO 判断後 | ~500 |
| **PR #5** | (条件付き) 6-lang scratch 学習の結果 + fixture 再生成 + HF アップロード | PR #4 の GO 判断後 | ~200 コード + 大量 fixture |

**PR #1 は独立で dev merge 可能** — WaveNeXt を最終採用しない場合でも silent bomb 解除だけ残せる (v8 branch に cherry-pick 済でも二重投入問題は最小)。

---

## タイムライン (最速シナリオ)

| Week | Stage | 内容 |
|------|-------|------|
| 1 | Stage 0 | blocker 解消 PR #1 landing |
| 2-3 | Stage 1 実装 | `wavenext.py` + loss module + test PR #2 |
| 4-5 | Stage 1 smoke 学習 | A100×1 で 3-5 日、評価 |
| 5 | Stage 1 判定 | GO/NO-GO 判断、PR #3 landing |
| 6-9 | Stage 2 (条件付き) | Multi-scale FiLM 移植 + 6-lang scratch |
| 10-12 | Stage 2 完了 | v1.13 release 判断、PR #4/#5 landing |
| 13+ | Stage 3 (条件付き) | WaveNeXt 2 反復版検証、~2-3 ヶ月 |

---

## Risk mitigation

- **v8 本走との干渉ゼロ**: 独立ブランチ、v8 は MB-iSTFT のまま完走
- **v7/v8 ckpt の BC 維持**: `decoder_arch` default `mb_istft` で silent load、DeprecationWarning + accept-but-ignore で hparams 互換
- **CI 赤化リスク回避**: fixture 再生成は Stage 2 完了後の PR #5 でまとめて、PR #1-3 は既存 fixture のまま緑維持
- **GPU コスト管理**: Stage 1 smoke (A100×1 で 3-5 日) の結果で全体 go/no-go 判断、無駄な A100×4 週次投入を回避
- **公式実装 drift 対応**: 将来 Okamoto 氏公式実装が出た場合の re-sync PR 用に `wavenext.py` に paper 参照 comment を残す

---

## 参考: 次アクション決定 flow

```
Stage 0 (blocker 解消 PR #1)
  ↓ CI 全緑
Stage 1 実装 (PR #2)
  ↓ merge 完了
Stage 1 smoke 学習 (A100×1, 3-5 日)
  ↓
  ├─ SECS ≥ 0.6879 && MOS 同等 → Stage 2 へ (default 昇格路線)
  ├─ SECS 0.65-0.68 → Stage 2 の S2-A (Multi-scale FiLM) のみ試す
  └─ SECS < 0.65 or JA/ZH 大幅退化 → 見送り、docs/research/ に log
       ↓
       WaveNeXt を諦めても Stage 0 の silent bomb 解除 + factory インフラは残る
       → v1.13 の Matcha-TTS / iSTFTNet2-MB 検討時に factory を再利用
```
