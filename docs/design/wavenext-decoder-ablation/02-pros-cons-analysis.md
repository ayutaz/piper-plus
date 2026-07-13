# 02. Pros/Cons Analysis — 置換による利害の対照

> **前提**: WaveNeXt 2 paper (arXiv:2605.25506) の実測値 + workflow findings + BSC-LT/wavenext-mel の実装調査を統合
> **数値の出所**: paper Figure 4 / Table 1 (LibriTTS-R 24kHz、単一 GPU / CPU 計測)
> **piper-plus 側 baseline**: `CLAUDE.md` Benchmark 表 (Xeon E5-2650 v4 / 25 phoneme / warmup 5 + 30 runs で 27ms) + v7 SECS 0.6879 (zero-shot 未知話者)

---

## 1. メリット (置換で得られるもの)

### M1. CPU 速度: **4x 高速化の可能性** (最大の実利)

paper 実測 CPU RTF (LibriTTS-R 24kHz):

| Model | CPU RTF | GPU RTF | Params |
|---|---|---|---|
| **GAN-WaveNeXt 2** (4 iter) | **0.20** | 0.0066 | 59.94M |
| **Diff-WaveNeXt 2** | **0.16** ← 最速 | 0.0164 | 57.68M |
| HiFi-GAN V1 | 0.80 | 0.0110 | 13.9M |
| WaveFit (5 iter) | 5.36 | 0.0226 | 15.51M |
| FastDiff | 0.80 | 0.0282 | 62.52M |

- **HiFi-GAN 比で 4x CPU 高速化** (0.80 → 0.20)
- **WaveNeXt v1** は iSTFT/PQMF がないぶん、MB-iSTFT より **10-15% 高速** (推定、workflow Requirements Phase)
- piper-plus 現行 end-to-end 27ms/25phoneme が実測 4x 高速なら **~7ms/25phoneme** 帯到達
- **組込 / mobile / Wyoming HA / エッジ配布での意味が決定的**

### M2. ONNX グラフの 30-40% 縮小 + 保守負荷減

置換で消えるコンポーネント:
- `mb_istft.py` (351 行) の PQMF + iSTFT 実装
- `stft_onnx.py` (138 行) の iSTFT を Conv1d/ConvTranspose1d で実装するトリック
- `stft_loss.py` (143 行) の sub-band 前提 loss
- complex tensor 分離 / exp(mag) / sin(phase) 演算
- PQMF analysis/synthesis filter 定数

**合計 ~630 行削除** + ONNX 定数テンソル削減 → **モデル配布サイズも FP16 で 5-10% 縮小見込**。

### M3. 6 ランタイム変更ゼロ (最大の隠れメリット)

C# / Rust / Go / WASM / C++ は `[B, 1, T] float32` tensor のみ consume。ORT 1.20.0 canonical / ort 2.0.0-rc.12 (Rust) は WaveNeXt ops (Conv1d / LayerNorm / GELU / Linear / Clip) **全対応 (workflow で file:line 確認済)**。

**cross-runtime parity 修正が 1 行も不要** — piper-plus 史上おそらく最後のこのタイプの opportunity。他候補との比較:

| 候補 decoder | 6 ランタイム修正 |
|---|---|
| **WaveNeXt v1** | **0 行** |
| iSTFTNet2-MB (A-1) | 2D Conv の ONNX op coverage 検証必要 |
| Matcha-TTS (A-4) | ODE solver の ONNX op coverage 検証必要 |
| StyleTTS2 (A-5) | style encoder 統合で複数箇所改修 |

### M4. bf16 学習の根本安定化

v8 で踏んだ **cuFFT bf16 bug** (fix commit `11ff71fc`) の原因は iSTFT complex 演算。WaveNeXt は complex tensor 一切ない → **bf16 非決定的挙動の温床が消える**。v9+ の学習パイプライン全体に恒久改善。

### M5. 学習補助機構がほぼ全部維持

decoder-agnostic で無変更継続:
- Super-MAS Triton-GPU MAS accelerator (19-72x MAS 高速化)
- WavLM Discriminator
- prosody_features (A1/A2/A3)
- spk_proj + DINO 自己蒸留 + CAM++ SCL
- freeze-dp
- EMA
- channels_last

**新旧 decoder 共通の学習パイプラインが維持できる** = ablation 比較の統制条件が clean。

### M6. WaveNeXt 2 本命への足場

WaveNeXt 2 は IEEE + 公式実装なしで直接着手は XL リスク。しかし WaveNeXt v1 が動く branch があれば、そこに **residual denoising + 3-pass iteration を差分実装**するだけで v2 到達可能 (v1 の reference 実装は BSC-LT の Apache-2.0 で入手可能)。

**v1 検証は v2 実装コストを L → M に下げる**。

---

## 2. デメリット (置換で失うもの・被るコスト)

### D1. 品質改善は統計的にゼロ (最大の caveat)

paper 実測 UTMOS / NISQA (LibriTTS-R):

| Model | UTMOS | NISQA |
|---|---|---|
| Ground Truth | 4.11 ± 0.09 | 4.08 ± 0.19 |
| **HiFi-GAN V1** | **4.05 ± 0.11** | 3.99 ± 0.22 |
| **GAN-WaveNeXt 2** | **4.04 ± 0.09** | 4.01 ± 0.20 |
| WaveFit | 4.04 ± 0.09 | 4.02 ± 0.19 |
| **Diff-WaveNeXt 2** | **3.87 ± 0.05** ← 劣化 | 3.81 ± 0.19 |

- GAN-WaveNeXt 2 と HiFi-GAN の UTMOS 差は **0.01 (誤差範囲内)**
- Diff 版は明確に劣化
- 「品質向上」を売りにできない
- piper-plus の 6lang / 571 話者 / zero-shot 条件は **paper のスコープ外**、MOS 向上への期待値ほぼゼロ

### D2. v7/v8/Tsukuyomi ckpt から decoder warm-start 不可

state_dict 名 overlap:
- MB-iSTFT: `subband_conv_post` / `ups` / `resblocks` / `pqmf` / `cond_layers`
- WaveNeXt: `convnext_blocks.*` / `head.linear_{1,2}` / `norm`
- **overlap = 数学的にゼロ**

影響:
- v7 zero-shot ep32 (SECS 0.6879) → decoder 部分は再学習
- v8 完走後 (7-lang / 5,100 speakers) → 同じく decoder 部分は再学習
- Tsukuyomi FT (SECS 0.7749) → 再 FT 必須
- EMA shadow_params も全 mismatch → fresh EMA init

**A100×4 で 6-lang scratch 800k-1M steps ≈ 2-3 週間の GPU 時間**が追加。

### D3. Zero-shot 品質退化リスク

v7 の SECS 0.6879 (未知話者) / Tsukuyomi FT 0.7749 は **Multi-scale FiLM を 5 サイト (input-stage + 各 upsample 段) に注入**する piper-plus 独自設計の結果。WaveNeXt の AdaLayerNorm 経由 speaker conditioning が同等の zero-shot 能力を出せるかは **論文に記載なし**。

SECS 退化する場合、Multi-scale FiLM を ConvNeXtBlock ラッパーとして再実装 → **標準 WaveNeXt から乖離**し、BSC-LT ckpt 互換性も損なう。

### D4. JA/ZH サ行子音品質の未検証

`--c-sub-stft 1.0` (sub-band STFT loss) は MB-iSTFT の高域忠実度に寄与していた。WaveNeXt では MRD (fft 2048/1024/512) が代替担当 → **piper-plus 既知弱点の JA サ行 / ZH 声調子音で品質退化するリスク**。

- MOS/PESQ/STOI 測定必須
- 悪化する場合は言語別 mel loss coefficient tuning が必要

### D5. WaveNeXt 2 は公式実装なし / IEEE copyright

- 公式 GitHub / HF なし、community port もなし
- GAN mode の sub-model weight 共有可否が paper 内不明確 (最悪 3x パラメータ数 = **~179M**)
- 損失係数 λ が「WaveFit と同じ」としか書かれず、WaveFit paper §3.3 から逆算作業必要
- 24kHz/hop=300 は piper-plus 22050Hz/hop=256 と非互換 → 22050Hz 適合検証コスト
- **WaveNeXt 2 実装は XL 規模 (半年〜1年)** → v1.13 では現実的候補は WaveNeXt v1 のみ

### D6. パラメータ数の増加 (WaveNeXt 2 の場合のみ)

| Model | Params |
|---|---|
| MB-iSTFT-VITS2 decoder 部分 | ~15M 相当 |
| **WaveNeXt v1 (BSC-LT)** | **13.68M** ← 現行同等 |
| **GAN-WaveNeXt 2 (4 iter)** | **59.94M (4x!)** |
| GAN-WaveNeXt 2 (5 iter) | 74.93M |
| Diff-WaveNeXt 2 | 57.68M |

paper 自身が "The overall parameters will grow with the number of sub-models. **This is an issue of the proposed methods.**" と述べる **公認の欠点**。piper-plus の CPU/on-device / mobile fit にはネガティブ。

### D7. Critical blocker (silent bomb)

`_is_legacy_hifigan_checkpoint()` (`src/python/piper_train/__main__.py:39-53`) が `subband_conv_post`/`pqmf` 欠如を「レガシー HiFi-GAN」と誤検出 → **WaveNeXt ckpt 書き出し瞬間に `--resume-from-multispeaker-checkpoint` と graceful resume 両経路で `RuntimeError` 発生**。

手を付ける前に必ず先行修正 (幸い副作用ゼロで v8 branch にも先行適用可)。

### D8. Cross-runtime fixture の大量再生成

- audio-parity-contract.toml の Tier-1 SHA256 fixture 4 モデル × 6 runtime = **24 個の ONNX 再エクスポート**
- `tests/fixtures/mb_istft_speaker_embedding/model.onnx` (Rust/C#/C++ 統合テスト参照)
- `test_*_mb_istft.py` 系 **~11 モジュール**の再生成 / 書き換え
- HF リポジトリ 6 件 (`piper-plus-base` / `piper-plus-tsukuyomi-chan` / `piper-plus-css10-ja-6lang` / `piper-plus-zero-shot-multi-6lang-v7` / `piper-plus-zero-shot-tsukuyomi` / CAM++ mirror) 再アップロード

**CI が landing 前後で 1-2 週間赤化するリスク**、PR 分割設計失敗で review コスト膨大。

### D9. hparams 互換性の落とし穴

v7/v8 の `c_sub_stft` / `sub_stft_{fft,hop,win}_sizes` が Lightning `save_hyperparameters()` で ckpt に永続化されている → **DeprecationWarning + accept-but-ignore で保持しないと `load_from_checkpoint` が例外**。`decoder_arch` を新規 hparam として追加する際は default='mb_istft' で v7/v8 ckpt が silent に MB-iSTFT として読まれる設計が必須。

### D10. Test coverage の一時的低下

MB-iSTFT 系 11 test module を deprecated branch として維持 → WaveNeXt 側の test を揃えるまで **両 decoder path で test 数倍増**、メンテナンス負荷。

---

## 3. トレードオフ表 (パス別)

| 軸 | **WaveNeXt v1 opt-in 並走** (推奨) | **WaveNeXt 2 完全移植** |
|---|---|---|
| **CPU 速度** | ✅ +10-15% (BSC-LT init) | ✅ +50-60% (paper 実測 4x vs HiFi-GAN) |
| **品質 MOS** | 🟡 未検証 (paper データなし) | 🟡 HiFi-GAN と同等 (統計誤差内) |
| **Zero-shot SECS** | 🟡 v7 の 0.6879 を超えるか未検証 | 🟡 同左 |
| **JA/ZH サ行** | 🟡 sub-band 廃止で退化リスク | 🟡 同左 |
| **ONNX 保守** | ✅ 30-40% グラフ縮小 | ✅ 同左 (+反復展開で複雑化) |
| **6 ランタイム修正** | ✅ 変更ゼロ | ✅ 変更ゼロ (opset 17 STFT だけ注意) |
| **パラメータ数** | ✅ 13.68M (現行同等) | ❌ 59.94M (4x) |
| **公式実装** | 🟡 unofficial (MIT/Apache-2.0) | ❌ なし (IEEE copyright) |
| **v7/v8 warm-start** | ❌ decoder 再学習必須 | ❌ 同左 |
| **Effort** | M (4-6 週) | XL (半年〜1年) |

---

## 4. Risk-adjusted 総合判定

**メリット中で確度の高いもの (paper 実測 / workflow 検証済)**:
1. CPU 4x 高速化 (paper 実測、piper-plus で追試すれば白黒つく)
2. ONNX グラフ 30-40% 縮小 (workflow で確認済、計算可能)
3. 6 ランタイム変更ゼロ (ORT op coverage で確認済)
4. bf16 数値安定化 (cuFFT complex 演算の消失、確実)
5. 学習補助機構の維持 (workflow で 8 dim × file:line 確認済)

**デメリット中で確度の高いもの (paper 実測 / workflow 検証済)**:
1. 品質 MOS 改善はゼロ (paper 実測、誤差範囲内)
2. v7/v8 decoder warm-start 不可 (weight overlap 数学的にゼロ、確実)
3. WaveNeXt 2 は IEEE + 公式実装なし (fact、変更不可)
4. Fixture 大量再生成 (workflow で 24 個 + 11 test module 特定済)

**メリット中で不確実 (smoke 学習で解消要)**:
- CPU 4x が piper-plus 6lang 条件でも成り立つか
- BSC-LT init からの partial-transfer FT が v7 SECS baseline を超えるか

**デメリット中で不確実 (smoke 学習で解消要)**:
- Zero-shot SECS 退化するか
- JA/ZH サ行子音品質退化するか
- Multi-scale FiLM 経路の再実装が必要か

**判定**: 「メリット中の確度の高いもの (5 軸)」× 「デメリット中の確度の高いもの (4 軸)」を天秤にかけると、**品質改善がゼロでも 6 ランタイム変更ゼロ + CPU 4x + bf16 安定化の実利は大きい**。ただし v7/v8 decoder 再学習の GPU コストが確実に発生するため、**opt-in flag として merge し、default 昇格は v7 SECS baseline 超えを smoke 学習で確認できた場合のみ**という段階設計が最も期待値が高い。

不確実性 (品質・zero-shot・サ行) は **A100×1 で 3-5 日の smoke 学習で決着可能** — 検証しないまま WaveNeXt を諦めるのは決定コストの見合いが取れない。

**→ Stage 1 (WaveNeXt v1 opt-in) は着手推奨、Stage 3 (WaveNeXt 2 完全移植) は Stage 1/2 の結果次第で GO/NO-GO 判断**。

詳細は [`03-ablation-plan.md`](03-ablation-plan.md) 参照。
