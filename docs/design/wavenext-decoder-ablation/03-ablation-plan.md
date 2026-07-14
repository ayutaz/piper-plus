# 03. Ablation Plan — 3-Stage 段階着手計画

> **前提**: `feat/wavenext-decoder-ablation` (dev 起点、`d594cea2`) で独立実施、v8 本走との干渉なし
> **ゴール**: 各 Stage で明確な GO/NO-GO 判断基準を設け、次 Stage 着手を実測データで gate 化
> **全 Stage 完走見込み**: Stage 0-2 で 6-9 週間、Stage 3 追加時は +2-3 ヶ月
> **更新 (2026-07-14)**: Stage 0 着手前検証 ([`04-pre-stage0-verification.md`](04-pre-stage0-verification.md)) の確定事項を反映済み — 行番号更新 / tri-state マーカー仕様確定 / opset 方針変更 / loss 計画修正 / loader 仕様明記 / Stage 3 数値確定

---

## Stage 0: Blocker 解消 (先行、~1 週間)

副作用ゼロで実装できる **silent bomb 解除** + factory インフラ構築。WaveNeXt 実装本体は含まず、MB-iSTFT 動作は完全維持。

### 実装内容

| ファイル:行 | 変更 |
|-----------|------|
| `src/python/piper_train/__main__.py:39-53` | `_is_legacy_hifigan_checkpoint()` を **tri-state 分類器 (`mb_istft` / `hifigan` / `wavenext`)** に refactor。positive detection: (a) `checkpoint["hyper_parameters"].get("decoder_arch")` タグがあればそれを採用 (state_dict マーカーと矛盾時は **warning log + タグ採用**)、(b) fallback で state_dict マーカーを判定 (下記「マーカー仕様」参照)。**decoder キーが 1 つもない部分 ckpt は `None` を返し raise しない** (第 4 状態 — 現行 False 挙動保存、v8 部分 transfer 保護)。**bool 互換 wrapper を維持**し既存 tests (`test_hifigan_ckpt_rejection.py` 12 + `test_export_onnx.py` 1 + `test_python313_migration.py` 1) を無変更 PASS |
| `src/python/piper_train/__main__.py:285-291` | `--decoder-arch {mb_istft,wavenext,wavenext2}` CLI flag 追加 (default `mb_istft`)。`VitsModel.add_model_specific_args` にも同 arg を追加し hparams.yaml に永続化 |
| `src/python/piper_train/__main__.py:479,854` | `_is_legacy_hifigan_checkpoint(...)` の call site は **2 箇所のみ**: `479` (`load_multispeaker_checkpoint`、無条件) と `854` (trainer.fit 失敗後の graceful-resume fallback 内のみ)。旧記載の 607/981/1063 は stale。呼び出しを新 tri-state 分類器に置換、arch mismatch 時は `WRONG_DECODER_ARCH_MESSAGE` (新規、partial-transfer FT 手順への URL 込) を raise |
| `src/python/piper_train/__main__.py:696-697` | `dict_args['upsample_rates']=(4,4)` / `upsample_kernel_sizes=(16,16)` を `if args.decoder_arch == 'mb_istft':` で gate 化 (WaveNeXt 分岐は Stage 1 で追加) |
| `src/python/piper_train/vits/models.py:757-766` | `SynthesizerTrn.__init__` で factory dispatch: `if decoder_arch == 'mb_istft': self.dec = MBiSTFTGenerator(...) elif decoder_arch == 'wavenext': self.dec = WaveNeXtGenerator(...)` (WaveNeXtGenerator は Stage 1 で追加、Stage 0 では `NotImplementedError` stub)。旧記載の 810-820 は stale (810 は emb_lang 領域)。**`decoder_arch` 引数は必ず default='mb_istft' の keyword 引数にする** — `tests/fixtures/mb_istft_speaker_embedding/build_fixture.py` が e2e-issue-426 / integration-tests-issue-426 / release-shared-lib の 3 CI workflow で毎回 `SynthesizerTrn` を直接 instantiate するため、後方互換なしでは即赤化 (逆にこの fixture が factory の無償 smoke test になる) |
| `src/python/piper_train/vits/lightning.py:320` | (Stage 1 実装だが**正当性要件として Stage 0 で明文化**) `self.model_g.dec.pqmf = self.pqmf` は decoder 種別によらず**無条件実行**される。gate し忘れると WaveNeXt ckpt に `model_g.dec.pqmf.*` buffer が混入 → tri-state fallback マーカーが mb_istft に**誤分類** (かつ現行 bi-state ではこの blocker 自体が発火しない → Stage 1 gating への暗黙依存)。cleanliness ではなく**正当性要件** |

**tri-state マーカー仕様 (04 doc で確定)**:

- マーカーは**完全修飾 prefix + 末尾ドット必須**:
  - mb_istft: `startswith(("model_g.dec.subband_conv_post.", "model_g.dec.pqmf.", "model_g.dec.istft."))` を hifigan 判定より**先に**評価 (`istft.inverse_basis` にマッチする `model_g.dec.istft.` を第 3 マーカーとして追加)
  - wavenext: `startswith(("model_g.dec.convnext.", "model_g.dec.head."))` (モジュール命名は wetdog/BSC-LT 準拠に pin — Stage 1 参照。旧記載の `convnext_blocks.*` は実装名と不一致のため訂正)
  - hifigan: 上記いずれもなく `model_g.dec.ups.` 系が存在
- **footgun**: `conv_post` は `subband_conv_post` の部分文字列 — substring (`in`) 判定は**禁止**

### テスト

- 既存 `test_hifigan_ckpt_rejection.py` (12 tests) + `test_export_onnx.py` (1) + `test_python313_migration.py` (1) は **bool 互換 wrapper 維持により無変更 PASS** (更新不要 — 04 doc verify で確認)
- 新規 `test_decoder_arch_dispatch.py`: `--decoder-arch mb_istft` で MB-iSTFT が instantiate されることを確認
- 新規: **wavenext ckpt (模擬 state_dict) に `model_g.dec.pqmf.*` が無い**ことを assert (pqmf 注入 gate の正当性要件。Stage 1 で実 ckpt に対して再検証)

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
# モジュール命名は wetdog/BSC-LT 準拠に pin (04 doc):
#   embed (Conv1d) / norm / convnext (ModuleList) / final_layer_norm / head
#   - "conv_pre" 命名は HiFi-GAN / MB-iSTFT / WaveNeXt の 3 アーキ衝突で禁止
#   - BSC-LT キー backbone.convnext.{N}.* とのリネームマップも最小化できる
class ConvNeXtBlock(nn.Module):
    """
    depthwise Conv1d(k=7, groups=dim) → LayerNorm → Linear(dim, intermediate_dim)
      → GELU → Linear(intermediate_dim, dim)
      → LayerScale(γ_init = 1/num_layers = 0.125)  # wetdog models.py L57 default
                                                    # (旧記載の 1e-6 は誤り — 04 doc)
      → residual
    """
    def __init__(self, dim=512, intermediate_dim=1536, adanorm_num_embeddings=0):
        ...  # AdaLayerNorm 経路は speaker/language conditioning 用に予約

class WaveNextHead(nn.Module):
    """
    Linear(512, 1026) → Linear(1026, hop_length=256, bias=False)
      → view(B, -1) → clip(-1, 1)
    """

class WaveNeXtGenerator(nn.Module):
    """
    Input:  z * y_mask  [B, inter_channels=192, L]
    Output: waveform    [B, 1, T=L*hop_length]
      # unsqueeze(1) は infer 出口ではなく generator forward 内で実施 —
      # MPD/WavLM/SCL/mel の全 loss が [B,1,T] rank-3 前提のため training 経路でも必須

    返却契約 (04 doc で確定): training 時は (o, None) の 2-tuple /
      onnx_export_mode 時は single tensor
      → models.py:990/1100 のハード unpack と lightning.py:883 の既存 guard が
        無変更で成立する

    Pipeline:
      embed = Conv1d(192, 512, k=7, padding=3)  # wetdog 準拠 (k=1 ではない)。
                                                 # この意図的選択は wavenext.py の
                                                 # コメントに明記予定
      → norm = LayerNorm                         # post-embed LayerNorm (wetdog 準拠)
      → convnext = 8 × ConvNeXtBlock(dim=512, intermediate_dim=1536)
      → final_layer_norm = LayerNorm
      → head = WaveNextHead
    """
    def remove_weight_norm(self):
        pass  # no-op stub (export_onnx.py などから呼ばれるため必須)

    def set_export_mode(self, mode):
        pass  # onnx_export_mode 属性の互換用

    # gin_channels > 0 の場合、Multi-scale FiLM を AdaLayerNorm 経由で
    # 各 ConvNeXtBlock の LayerNorm に注入 (v7 の speaker conditioning 経路)
```

**`wavenext.py` ヘッダ attribution 要件 (04 doc)**: (1) Vocos (Copyright 2023 Charactr Inc., MIT)、(2) wetdog/wavenext_pytorch@d45d544 (WaveNextHead 追加分、MIT)、(3) Okamoto et al. ASRU 2023 (DOI 10.1109/ASRU57964.2023.10389765)。BSC-LT 重み利用時は Apache-2.0 NOTICE 保持。

### 統合ポイント

| ファイル:行 | 変更 |
|-----------|------|
| `src/python/piper_train/vits/models.py:11` | `from .wavenext import WaveNeXtGenerator` 追加 |
| `src/python/piper_train/vits/models.py:757-766` | Stage 0 で用意した factory dispatch の `wavenext` 分岐を有効化 |
| `src/python/piper_train/vits/models.py:990,1100` | **書き換え不要 (04 doc で確定)** — 返却契約「training=(o, None) 2-tuple / onnx_export_mode=single」により 990/1100 のハード unpack は無変更で成立。~~旧記載の 1068,1187 isinstance 書き換え~~ は不要 (infer 1073-1076 は既に isinstance 対応済) |
| `src/python/piper_train/vits/wavenext.py` (generator forward) | `unsqueeze(1)` は **generator forward 内**で実施 — ~~旧記載の `SynthesizerTrn.infer` 出口挿入~~ は撤回 (MPD/WavLM/SCL/mel の全 loss が `[B,1,T]` rank-3 前提のため training 経路でも必須) |
| `src/python/piper_train/__main__.py:696-697` | WaveNeXt 分岐で `wavenext_dim=512 / intermediate_dim=1536 / num_blocks=8 / head_hop_length=256` を注入 |
| `src/python/piper_train/vits/lightning.py:24,31` | import を gate 化: WaveNeXt 選択時は `PQMF` / `MultiResolutionSTFTLoss` (sub-band 用) を skip |
| `src/python/piper_train/vits/lightning.py:320` | pqmf 注入 `self.model_g.dec.pqmf = self.pqmf` を `decoder_arch == 'mb_istft'` で gate 化 — **正当性要件** (gate し忘れると WaveNeXt ckpt に `model_g.dec.pqmf.*` 混入 → tri-state マーカー誤分類。Stage 0 節参照) |
| `src/python/piper_train/vits/lightning.py:317-325` | `if decoder_arch == 'wavenext':` で PQMF / sub_stft_loss の instantiate を skip。mel loss は「追加」ではなく**維持 or 置換の明示的設計判断** — wetdog の `MelSpecReconstructionLoss` (一次確認: 128-mel / f_max 11025 / slaney / clip 1e-5 / L1、coeff=45) をそのまま追加すると既存 `loss_mel` (80-mel L1 log-mel、`c_mel=45`、`lightning.py:874`) と**二重計上**になる。`MultiResolutionDiscriminator` (DAC band-split 型、fft 2048/1024/512、channels 32、hinge、coeff=0.1) を追加 |
| `src/python/piper_train/vits/lightning.py:883-887` | `if o_mb is not None:` guard は既存 (`lightning.py:883`)、`decoder_arch='wavenext'` で `o_mb=None` なら自動 skip → fullband path で `loss_mrstft` + `loss_mrd_gen + loss_mrd_fm` を追加 (fullband MR-STFT は既存 `MultiResolutionSTFTLoss` の別サイズ再インスタンスで済む) |
| `src/python/piper_train/vits/lightning.py:1264-1267,693-696` | `configure_optimizers` の d_params (1264-1267) と D grad clip (693-696) に MRD パラメータを追加 |
| `src/python/piper_train/export_onnx.py:27` | ~~OPSET_VERSION 15 → 17 の一括 bump~~ は**撤回 (本計画で唯一の確定 CI 赤化要因、04 doc)** — `scripts/check_onnx_export_contract.py:27` の `EXPECTED_TTS_OPSET=15` ハードコードで model-quality-gate (blocking) が確定的に落ち、`onnx-export-contract.toml:116-118` の「opset bump = 全公式 ONNX 再生成 + 全 7 runtime 検証」義務が発火する。対応: **wavenext 分岐のみ opset 17** とし、新定数名は check script の regex `OPSET_VERSION\s*=\s*(\d+)` (re.search 先頭一致、部分文字列にもマッチ) を踏まない命名 (例 `OPSET_VERSION_WAVENEXT`) にするか、contract toml + check script を同 PR で更新。rationale は「機能的必然」ではなく「convert_fp16 の LN keep-list safeguard 有効化 + ORT fusion/.opt.onnx キャッシュ非依存化」(opset 15 でも動作は PoC 実証済: 314 nodes→ORT fusion / opset 17 なら native LN で 214 nodes / parity 1.13e-06)。互換性: 全 8 runtime pin (min ORT>=1.20、Rust は ort rc.12 + api-24 feature = ORT 1.24 ターゲット) で opset 17 受理を確認済み、既存 opset 15 配布物との混在も可 → **既存モデル再 export 不要** |

### 新規 loss module

**`src/python/piper_train/vits/wavenext_losses.py`** — 新規実装スコープは **MRD 本体 + hinge loss (採用時) に縮小** (04 doc §6):
- `MultiResolutionDiscriminator` 本体 (DAC band-split 型、fft 2048/1024/512、channels 32) + hinge loss (採用時)
- mel loss は新規実装ではなく既存 `loss_mel` との**維持 or 置換判断** (統合ポイント参照)。**128-mel 採用時は `mel_processing.py` の global cache 使用禁止** — cache キーが fmax のみで num_mels を無視するため silent に 80-mel basis が返る。`losses.py:_get_mel_basis` を使用
- fullband MR-STFT は既存 `MultiResolutionSTFTLoss` の別サイズ再インスタンスで済む (新規実装不要)
- feature matching loss (既存を再利用可能なら流用)
- **GAN loss 形式の明示的設計判断 (Stage 1)**: wetdog は hinge + sub-discriminator 数正規化 (MPD /5、MRD /3)、piper 既存は LSGAN 非正規化和 — 係数 45/0.1 の実効スケールが異なるため、**一本化 (LSGAN=diff 最小) or ablation** を Stage 1 で確定する
- **optimizer 差分 (design decision として注記)**: wetdog は AdamW betas=(0.8,0.9) + cosine warmup 500 step (piper 既存設定と異なる)

### テスト

- `test_wavenext_generator.py`: forward pass shape 検証、gin_channels 条件付け、`remove_weight_norm()` no-op 動作
- `test_synthesizer_trn_wavenext.py`: `decoder_arch='wavenext'` で SynthesizerTrn が正常構築
- `test_export_onnx_wavenext.py`: opset 17 (wavenext 分岐) で export 成功、output shape `[1, 1, T]`、**`LayerNormalization` node ×10 (post-embed 1 + block 8 + final 1) 存在** assert
- **wavenext ckpt に `model_g.dec.pqmf.*` buffer が混入しない**ことを assert (pqmf 注入 gate の正当性要件、Stage 0 の模擬 state_dict テストを実 ckpt で再検証)
- 既存 `test_*_mb_istft.py` 系は `decoder_arch='mb_istft'` を明示して継続動作

### Smoke 学習

**環境**: A100×1、bf16-mixed、6-lang partial-transfer FT

**`--wavenext-init` loader 仕様 (04 doc で確定、BSC-LT `pytorch_model.bin` = 83 keys / 13.72M params)**:

- (a) `feature_extractor.*` 2 buffer を **drop**
- (b) `backbone.embed.weight` (512,80,7) を **skip** し 192ch スクラッチ init (`embed.bias` 再利用は選択制)
- (c) BSC-LT キー名 `backbone.convnext.{N}.*` → piper モジュール名への**リネームマップ**
- 転送可能テンソルは **83 中 80**
- **standalone sanity check の注意**: piper の `mel_spectrogram_torch` デフォルト (fmax=None) は使用禁止 — f_max=8000/slaney で計算するか同梱 `mel_spec_22khz_wavenext.onnx` を使用する
- `pytorch_model.bin` は **generator のみで discriminator を含まない** → Stage 1 の MPD/MRD は**必ずスクラッチ**

```bash
# Option A: BSC-LT/wavenext-mel init から (推奨)
# 1. HF から BSC-LT/wavenext-mel の decoder weight を download
# 2. 入力 embed (192-latent) のみスクラッチ、backbone + head は BSC-LT init (上記 loader 仕様)

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
    --c-mrstft 1.0 --c-mrd 0.1 \
    --pretrain-mel-steps 5000 \
    --default_root_dir /data/piper/output-wavenext-v1-smoke \
    > wavenext-smoke.log 2>&1 &
```

期間目安: A100×1 で 3-5 日 (batch=32、6-lang 50k steps 想定)。

> **コマンド注記 (Stage 1 実装で確定)**: mel loss は既存 `loss_mel` (80-mel, `c_mel=45`) を**維持**に確定 — `--mel-loss-coeff` flag は存在しない (128-mel MelSpecReconstructionLoss は二重化罠 + mel cache バグ回避のため不採用、04 doc §6)。`--c-mrstft` は **default 0.0 (OFF)** — 上記コマンドの `1.0` は Unknown #9 (JA/ZH サ行) 保険の明示 opt-in。`--pretrain-mel-steps 5000` は wetdog default 0 からの **piper 側変更** (機構自体は wetdog experiment.py L289-293 に存在)。pretrain 窓では MPD/MRD/WavLM の adversarial 項と D 更新のみを skip し、**SCL/DINO は gate しない** (CAM++ SCL は no_grad で勾配なし、DINO は decoder 非依存の spk_proj 学習のため停止する理由がない — 意図的決定)。

### 評価

- **SECS (CAM++)**: v7 zero-shot ep32 baseline **0.6879 (未知話者)** と比較
- **CPU RTF**: ✅ **キルスイッチ測定済み (2026-07-14、GPU 投資前に確定)** — canonical 実機 (Xeon E5-2650 v4) は ssh 到達不可のため **CI runner (ubuntu-24.04 / AMD EPYC 7763 4vCPU、multi-runtime-rtf gate と同一環境) を canonical 代理**に採用、`scripts/bench_wavenext_rtf.py` + `.github/workflows/wavenext-rtf-killswitch.yml` (run 29306153982) で contract 準拠実測。**decoder 単体 p50 ratio (WaveNeXt/MB-iSTFT): fp32 1.24-1.26x / fp16 1.34-1.39x 劣位 (T=60/150/400 全て一貫)**。配布実モデルの ORT profiling で decoder ノード時間比 ~0.34 → **end-to-end 影響は +8〜12% 程度と推定** (27ms → ~30ms 相当)。絶対 RTF は両者とも 0.012-0.017 で real-time 比 60-85x 高速。学習後モデルでの再計測は不要 (速度はグラフ構造のみに依存)
- **ONNX size**: FP16 export 後のファイルサイズ、現行と比較 (04 doc PoC: decoder 単体 fp32 で 8.5x 増の prior)
- **PESQ/STOI (JA/ZH サ行)**: 既知話者音声との A/B、既知弱点音素の退化検出
- **主観 A/B**: つくよみちゃん FT ONNX の再現、MB-iSTFT 版と聴き比べ
- **学習後の head bias floor**: z=0 出力 RMS vs `_trim_silence` 閾値 0.01 の再測定 (PoC 時 init 状態で abs_max 0.045 — 04 doc)
- **FP16 export 品質**: 学習後の LayerScale γ 分布確認 (init 0.125 が subnormal 域に落ちていないか) + `convert_fp16 --validate` 通過

### GO/NO-GO 判断基準

| 結果パターン | 判定 | 次アクション |
|-------------|------|------------|
| SECS ≥ 0.6879 && CPU RTF < 現行 && MOS 同等 | ✅ GO (default 昇格候補) | Stage 2 で統合強化 + 6-lang scratch で本格投入 |
| SECS ~ 0.65-0.68 && 速度 win / 品質同等 | 🟡 CONDITIONAL GO (opt-in flag) | Stage 2 で Multi-scale FiLM 移植を試す、駄目なら opt-in flag として merge |
| SECS < 0.65 or JA/ZH サ行大幅退化 | ❌ NO-GO (Stage 2 に進まない) | 知見を Matcha-TTS / iSTFTNet2-MB / StyleTTS2 の設計判断に転用、ablation を `docs/research/` に log |

> **「CPU RTF < 現行」gate は判定済み: ❌ 不成立** (2026-07-14 キルスイッチ測定、上記「評価」節)。ローカル Ryzen (30-40% 劣位) と canonical 代理 EPYC (24-39% 劣位) の 2 環境で一貫しており、学習結果に依存しないため覆らない。したがって **✅ GO (default 昇格) の行は到達不能**で、残る現実的ゴールは 🟡 CONDITIONAL GO (opt-in flag、品質同等 + 保守性/bf16/WaveNeXt 2 足場が動機、end-to-end +8〜12% の速度コストを許容) か ❌ NO-GO。smoke 学習に進むかは「品質同等の確認に A100×1 3-5 日を投資する価値があるか」の判断となる。

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

Stage 2 で WaveNeXt v1 が v1.13 default 候補になった場合のみ、更なる品質改善候補として WaveNeXt 2 の反復版 (paper headline は 4 sub-models — 04 doc で確定) を検討。

### 実装内容 (paper §2-3 からの再実装)

**S3-A. Residual denoising path**
- Generator は noise `n_t` を予測、`y_{t-1} = y_t - n_t` で feedback
- 前波形の STFT (real + imag、Hann window) を auxiliary input として mel-spec と concat

**S3-B. Sub-modeling (4 sub-models — paper headline 構成、04 doc で確定)**
- WaveFit-style unrolled iteration を ONNX single-pass に展開 — ~~旧記載の「3-pass fixed-point iteration」~~ は誤りで、headline は **4 sub-models** (paper Table 1 で 2-5 を ablation 済、5 は UTMOS 向上なしで param のみ増)
- opset 17 の native `STFT` op を利用 (float32 only、FP16 STFT 非対応)
- ~~sub-model weight 共有 vs 独立の 2 案 ablation~~ → **de-scope (04 doc)**: paper 準拠は **weight 独立で確定** (Table 1 の param 線形性)。共有版 (~15M×4 compute) は param 削減目的の **piper 独自 optional** に降格

**S3-C. WaveFit loss 係数 (pin 済 — 逆算不要、04 doc で完了扱い)**
- ~~WaveFit paper §3.3 を読み込み係数 λ を逆算~~ → 誤ポインタだった。**§4.2 (定義) / §4.4 (STFT resolution) / §5.1 (λ 値) で pin 済**。係数セット (LibriTTS 構成): **λ_FM=10 / λ_STFT=2.5 / mel-MAE 除外 / adversarial は MelGAN MSD×3 (raw/2x/4x downsample) hinge / MR-STFT win 360/900/1800・hop 80/150/300・fft 512/1024/2048 / 全 T output の 1/T 平均 / gain adjustment・初期ノイズなし**
- **discriminator セット非互換の注記**: Stage 1 (Vocos 系 MPD+MRD) と Stage 3 (WaveFit MelGAN MSD×3、MPD/MRD 不使用) は非互換 — Stage 3 で Stage 1 の D を流用すると paper 再現から乖離する
- Diff-WaveNeXt 2 (Diff mode) は Stage 3 では対象外 (paper の UTMOS 3.87 < GAN mode 4.04 のため実利小)

### リスク

- IEEE copyright、公式 reference 実装なし → 実装差異による品質 drift の判別困難
- 4x パラメータ数 (**59.94M = 4×14.99M、weight 独立で確定** — 隠れ倍率なし、04 doc) → CPU on-device / mobile fit で不利
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
- **CI 赤化リスク回避**: opt-in 追加なら**既存 fixture 再生成ゼロ** (04 doc で旧 D8 blocker を格下げ)。WaveNeXt 新 fixture (tiny ONNX 1 個 + parity contract 1 エントリ + manifest 1 エントリ、additive) は Stage 2 以降に先送り可。fixture 再生成 / HF 再アップが必要になるのは完全置換時のみ (PR #5)、PR #1-3 は既存 fixture のまま緑維持
- **将来 hop≠256 化 (Stage 3 / 24kHz) の前提整理**: hop_length のハードコードが 4 箇所 (WASM `index.js:1070` / Rust `main.rs:637-641` / Go `main.go:599` / C# `TimingWriter.cs:76` + `Program.cs` 2 経路) + `phoneme-timing-contract.toml:26` に存在 — config 読み取り化が別途必要。WaveNeXt v1 は hop=256 維持のため Stage 1 では非該当 (`audio.hop_size` の config.json 明示 emit は `preprocess.py:292-306` / `prepare_multilingual_dataset.py:1428-1447` での optional hygiene fix)
- **`decoder_arch` の config.json stamp**: 全 6 runtime lenient 確認済でゼロリスク (optional provenance、04 doc)
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
