# 01. Feasibility Investigation — WaveNeXt 置換調査結果

> **調査方法**: ultracode workflow (18 agents / 2.23M tokens / 22 分) で 8 dimension を fan-out map → adversarial verify → 総合判定
> **調査日**: 2026-07-13
> **総合判定**: **moderate-refactor** — 技術的に置換可能だが drop-in ではない
> **workflow output**: `~/.claude/.../tasks/w97ys0g5k.output` (240KB)

---

## 1. 現行 decoder (MB-iSTFT-VITS2) の coupling surface

### 1.1 Decoder 内部完結 (置換で丸ごと消える)

| ファイル | 行数 | 役割 |
|---------|------|------|
| `src/python/piper_train/vits/mb_istft.py` | 351 | PQMF (25-130) + MBiSTFTGenerator (133-350) 全体。conv_pre → 2 段 ConvTranspose1d upsample (4x × 4x = 16x) → subband_conv_post → OnnxISTFT (×4x) → PQMF synthesis (×4x) = 256x。Multi-scale FiLM (231-244, 255-266, 286-302) は speaker conditioning 経路で decoder 内部完結 |
| `src/python/piper_train/vits/stft_onnx.py` | 138 | OnnxISTFT layer (Conv1d/ConvTranspose1d で iSTFT を実装、opset 15 互換)。**MBiSTFTGenerator からのみ import され dead code 候補** |
| **合計** | **489** | 置換で丸ごと除去可能 |

### 1.2 Decoder 外への漏洩 (置換時に必修改修)

| ファイル:行 | 何が漏れているか | replacement impact |
|-----------|----------------|---------------------|
| `stft_loss.py:106-143` | `MultiResolutionSTFTLoss` (`--c-sub-stft`) が sub-band 信号 `[B, subbands, T]` を前提。WaveNeXt では sub-band が存在しない | 削除 or MRD (fft 2048/1024/512) に代替 |
| `models.py:11,708-716,810-820,1068,1077,1160-1163,1187` | `SynthesizerTrn.dec` が MBiSTFTGenerator、`SynthesizerOutput.decoder_subbands` に sub-band を格納、`infer` が tuple/single を isinstance 分岐、`voice_conversion` が tuple 前提 unpack | factory dispatch (`decoder_arch` hparam) + `.unsqueeze(1)` 挿入 |
| `lightning.py:24,31,170-172,231-234,290,301,361-368,917-935,1017-1022` | **最も強く coupling**。PQMF を直接 import して `self.pqmf = PQMF(subbands=4)` を自前保持、`self.model_g.dec.pqmf = self.pqmf` で decoder 内 PQMF に上書きインジェクト、`MultiResolutionSTFTLoss` を hparams 込みで instantiate、`training_step_g:935` で `decoder_subbands` 取り出し、`1018-1022` で `y_mb = self.pqmf.analysis(y)` と `sub_stft_loss(o_mb, y_mb)` を loss_gen_all に加算 | sub_stft path 削除 (gate 化) + `MelSpecReconstructionLoss` + MRD 追加 |
| `__main__.py:39-53,891-910,968` | **MB-iSTFT 構造をハード決め打ち**。`upsample_rates=(4,4)` / `upsample_kernel_sizes=(16,16)` を無条件上書き。`_is_legacy_hifigan_checkpoint` (39-53) は `model_g.dec.subband_conv_post.*` / `model_g.dec.pqmf.*` の存在で「MB-iSTFT ckpt かどうか」を判定 → **新 decoder では別マーカーに置換必須 (放置すると新 ckpt が legacy 誤検出で即詰み)** | tri-state 化 (`mb_istft` / `hifigan` / `wavenext`) + `--decoder-arch` CLI flag |
| `ema.py:118-134,189-205` | EMA を `model.model_g.dec` に適用。decoder が丸ごと差し替わると shadow_params のキーが不一致 → 過去 MB-iSTFT ckpt からの EMA restore が warning のみで silently drop | 意図した挙動 (fresh EMA init、`skipped` log で観測可能) — **無変更で継続動作** |
| `export_onnx.py:67-72,122-129,342-345,494-522,553,643` | EMA を `model_g.dec.named_parameters()` に対して復元、`model_g.dec.remove_weight_norm()` を必ず呼ぶ、`onnx_export_mode` を set_export_mode で全 submodule に伝播、`infer_forward` が `o = model_g.dec((z * y_mask), g=g)` で single output を期待 | 新 decoder も同名 method を expose (or no-op stub) |
| `{infer,export_torchscript,export_generator,export_onnx_streaming,voice_conversion}.py` | 全 export/inference エントリで `model_g.dec.remove_weight_norm()` を必須メソッドとして呼び出し | no-op stub で対応 |

### 1.3 Cross-runtime 契約 (audio-parity contract)

- `docs/spec/audio-parity-contract.toml` — Tier-1 SHA256 fixture 4 モデル (`multilingual_test_medium` / `tsukuyomi_6lang_v2` / `mb_istft_base` / `zero_shot_test_model`) は decoder 交換で必ず drift → **6 runtime 分の ONNX 再エクスポート + baseline 再取得が必要**
- `tests/fixtures/mb_istft_speaker_embedding/model.onnx` — Rust/C#/C++ 統合テスト参照 → 再生成必須
- `test_*_mb_istft.py` 系 **~11 モジュール** — 再生成 or 書き換え

---

## 2. GAN-WaveNeXt2 / WaveNeXt v1 技術要件

### 2.1 Architecture

**WaveNeXt v1 (Okamoto ASRU 2023、drop-in 候補)**:
```
Backbone (VocosBackbone): N=8 ConvNeXtBlock、dim=512、intermediate_dim=1536
各 block:
  x_res = x                                             # [B, C=512, L]
  x = Conv1d(dim, dim, k=7, padding=3, groups=dim)(x)   # depthwise conv
  x = x.transpose(1, 2) → LayerNorm(dim, eps=1e-6)
  x = Linear(dim, 1536) → GELU → Linear(1536, dim)
  x = gamma * x                                          # LayerScale (γ init 1e-6)
  x = x.transpose(1, 2) → x_res + x                     # residual

Head (WaveNextHead, iSTFT を置換):
  x = Linear(512, 1026)                                  # linear_1 with bias
  x = Linear(1026, 256, bias=False)                      # linear_2
  audio = x.view(B, -1)                                  # [B, L * hop_length]
  audio = torch.clip(audio, -1.0, 1.0)
```

**GAN-WaveNeXt 2 (arXiv:2605.25506)**: 上記 + (a) residual denoising (generator が noise `n_t` を予測、`y_{t-1} = y_t - n_t` を feedback、前波形の STFT を auxiliary input) + (b) sub-modeling (3-pass fixed-point iteration、WaveFit-style)

### 2.2 Input/Output contract

| 項目 | WaveNeXt v1 (BSC-LT/wavenext-mel) | piper-plus MB-iSTFT | Compat |
|---|---|---|---|
| Sample rate | 22050 Hz | 22050 Hz | ✅ |
| n_fft | 1024 | 1024 | ✅ |
| hop_length | 256 | 256 | ✅ |
| win_length | 1024 | 1024 | ✅ |
| n_mels | 80 | 80 | ✅ |
| f_min / f_max | 0 / 8000 | 同等 | ✅ |
| Output shape | `[B, T]` (rank-2) | `[B, 1, T]` (rank-3) | 🟡 `.unsqueeze(1)` 追加必要 |

**→ BSC-LT/wavenext-mel は piper-plus と byte-for-byte 互換**、warm-start init として使用可能。

**GAN-WaveNeXt 2 (paper)**: 24 kHz / hop=300 → piper-plus 22050Hz と非互換、22050Hz 適合は再学習必須。

### 2.3 ONNX ops (必要な演算)

- Conv1d (kernel=7, groups=dim=512, depthwise) — opset 11+
- LayerNorm — native opset 17+ / opset 15 emulated
- GELU — native opset 20+ / opset<20 は decomposition
- Linear (MatMul + Add) — 全対応
- Transpose / Mul / Add / Clip / Reshape — 全対応
- **NOT needed**: iSTFT, complex tensor, PQMF (現行 decoder より simpler)
- **WaveNeXt 2 additional**: `aten::stft` (opset 17+ native) + iterative loop (3-pass unrolled)

### 2.4 Loss requirements

- **MelSpecReconstructionLoss**: `L1(log MelSpec(y) - log MelSpec(ŷ))`、**128-mel bin** analysis mel、coeff=45 (Vocos default)
- **MPD** (HiFi-GAN periods 2,3,5,7,11) — hinge loss、coeff=1.0
- **MRD** (DAC-style, fft 2048/1024/512) — hinge loss、coeff=0.1 (Vocos default)
- **FeatureMatchingLoss** — L1 across discriminator feature maps
- **NOT needed**: `--c-sub-stft`, sub-band STFT loss
- **WaveNeXt 2**: 上記 + WaveFit STFT loss (multi-resolution mag+phase) + 3-pass unrolling loss

### 2.5 Training recipe (BSC-LT/wavenext-mel 参考)

- 1,000,000 steps ≈ 96 epochs、batch=16、num_samples=16384 (~0.74s)
- Optimizer: AdamW、LR=1e-4、num_warmup_steps=500、cosine scheduler
- Datasets: LibriTTS-R (585h) + LJSpeech (24h) + Festcat (22h) + OpenSLR69 (5h) = ~636h
- Model size: **13.68M params** (backbone 512×8 + WaveNextHead)
- License: MIT (wetdog code) / Apache-2.0 (BSC-LT checkpoint)

### 2.6 Warm-start feasibility

1. **BSC-LT/wavenext-mel checkpoint 直用**: ✅ mel config byte-identical、speaker/language conditioning を上乗せ実装
2. **6-lang scratch**: A100×4 で 800k-1M steps、~2-3 週間
3. **v7 MB-iSTFT ckpt warm-start**: ❌ **不可能** — weight tensor 名 overlap ゼロ

---

## 3. 8 dimension × adversarial verify 結果

| Dimension | Verdict | Blockers | 主要 findings |
|-----------|---------|----------|--------------|
| training-vits | moderate-refactor | high | v7/v8 ckpt weight overlap ゼロ、decoder + EMA 再学習必須 |
| onnx-export | drop-in-possible | low | `.unsqueeze(1)` 1 行追加のみ |
| runtime-python | drop-in-possible | (なし) | audio.hop_size を config.json に明示 emit (hygiene fix) |
| runtime-non-python | drop-in-possible | (なし) | **6 ランタイム変更ゼロで受け入れ可能** — Conv1d/LayerNorm/GELU/Linear/Clip 全対応 |
| training-loop-losses | moderate-refactor | medium | sub_stft 撤去 → MRD 追加、DINO/CAM++/WavLM との数値安定性未検証 |
| checkpoint-config | **blocker-found** | **critical** | `_is_legacy_hifigan_checkpoint()` 誤検出 → tri-state 化必須 |
| cross-runtime-parity | moderate-refactor | medium | Tier-1 fixture 4×6=24 個の再エクスポート、CI 赤化リスク |
| super-mas-wavlm | drop-in-possible | (なし) | Super-MAS / WavLM Disc / prosody_features / freeze-dp / EMA は decoder-agnostic で無変更 |

---

## 4. Blocker サマリ (severity 別、workflow 総合判定)

| severity | area | 内容 |
|---|---|---|
| **critical** | checkpoint-config | `_is_legacy_hifigan_checkpoint()` の誤検出 (先行修正必須、副作用ゼロで v8 branch にも適用可) |
| **high** | training-vits | v7/v8/Tsukuyomi ckpt の decoder weight overlap ゼロ、再学習 A100×4 で 2-3 週間 |
| **medium** | new-dependencies | WaveNeXt 2 は IEEE copyright + 公式実装なし、v1.13 は WaveNeXt v1 に絞るべき |
| **medium** | cross-runtime-parity | Tier-1 fixture 4 モデル × 6 runtime = 24 個の再エクスポート、CI が 1-2 週間赤化リスク |
| **medium** | training-loop-losses | MRD が sub_stft を代替できるか (JA/ZH サ行) 未検証、bf16 + WaveNeXt + DINO の数値安定性未検証 |
| **low** | onnx-export | `SynthesizerTrn.infer` 出口の `.unsqueeze(1)` 1 行 (忘れると全ランタイム破綻) |

---

## 5. Unknowns (paper 単独では確定できない項目、smoke 学習で解消要)

1. **WaveNeXt 2 sub-model weight sharing (GAN mode)**: paper は "fixed-point iteration strategy introduced in WaveFit" とのみ記述、shared vs separate 不明確 → 最悪 3x パラメータ数 (**~179M**)
2. **WaveNeXt 2 損失係数 λ**: "same discriminators and loss functions as WaveFit [9]" のみ、WaveFit §3.3 から逆算必要
3. **公式コード/重み release**: v1 も v2 も公式なし、unofficial (wetdog MIT / BSC-LT Apache-2.0) のみ、IEEE copyright
4. **22050Hz WaveNeXt 2 config**: paper は 24kHz のみ、22050Hz への転移可否未実証
5. **VITS + WaveNeXt end-to-end 学習の安定性**: Multi-scale FiLM + DINO + CAM++ SCL との組合せは precedent なし
6. **AdaLayerNorm 経由の zero-shot conditioning**: v7 の 5 サイト Multi-scale FiLM と同等の SECS を出せるか未検証
7. **v7 encoder half の partial-transfer**: encoder/flow/dp は transfer 可のはず、decoder は必ずスクラッチ
8. **短テキスト strategy 相互作用**: WaveNeXt の `torch.clip(-1,1)` と post-trim silence 検出の相性
9. **Sub-band STFT loss 撤去の音質影響**: JA/ZH サ行子音 (piper-plus 既知弱点) で MRD が同等品質を出せるか

---

## 6. Effort 見積 (3 パス)

| パス | サイズ | 内訳 |
|---|---|---|
| **WaveNeXt v1 opt-in 並走** | **M** (4-6 週) | コード改修 1-2 週 + test 3-5 日 + fixture 2-3 日 + smoke FT 3-5 日 + 6 runtime CI 緑化 3-5 日 |
| **MB-iSTFT 完全撤去 + WaveNeXt v1 に置換** | **L** (数ヶ月) | 上記 + 6-lang scratch 800k-1M steps (A100×4 で 2-3 週) + Tsukuyomi 再 FT + HF 6 リポジトリ再アップロード |
| **WaveNeXt 2 (反復 3-pass) 移植** | **XL** (半年〜1年) | IEEE paper 再実装 + λ ablation + 24kHz→22050Hz 適合 + 反復展開 ONNX 化 + WaveFit 係数逆算 |

---

## 7. 参考文献

- **WaveNeXt (v1)**: Okamoto et al., "WaveNeXt: ConvNeXt-Based Fast Neural Vocoder Without ISTFT layer", ASRU 2023 — https://www.okamotocamera.com/preprint_asru_2023_okamoto.pdf
- **WaveNeXt 2**: "WaveNeXt 2: ConvNeXt-Based Fast Neural Vocoders With Residual Denoising and Sub-Modeling for GAN and Diffusion Models", arXiv:2605.25506 (ICASSP 2026) — https://arxiv.org/abs/2605.25506
- **WaveFit** (loss 係数の逆算元): Koizumi et al., Interspeech 2022
- **BSC-LT/wavenext-mel**: https://huggingface.co/BSC-LT/wavenext-mel (Apache-2.0)
- **wetdog/wavenext_pytorch**: https://github.com/wetdog/wavenext_pytorch (MIT)
- **NICT WaveNeXt デモ**: https://ast-astrec.nict.go.jp/demo_samples/asru_2023_okamoto/
