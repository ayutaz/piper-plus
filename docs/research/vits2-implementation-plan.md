# VITS2 アーキテクチャ導入計画

> **調査日**: 2026-03-14
> **目的**: piper-plusのVITSベースアーキテクチャにVITS2の改良を段階的に導入し、推論速度・モデルサイズを維持しつつ音質を向上させる
> **制約**: モバイル/Raspberry Piでの動作を前提とし、推論速度低下・モデルサイズ増大を許容しない
> **論文**: [VITS2 (arXiv:2307.16430)](https://arxiv.org/abs/2307.16430) — Interspeech 2023

---

## 1. VITS2の5つの改良点

| # | 改良 | 内容 | MOS貢献 |
|---|------|------|---------|
| A | 敵対的Duration Predictor | Flow-based SDP → GAN的訓練のDPに置換 | **+0.14** |
| B | Normalizing Flow + Transformer | 畳み込みFlowにTransformerブロックを残差接続で追加 | **+0.06** |
| C | Noise-Scaled MAS | MASのQ値にガウスノイズを追加（学習初期のみ） | **+0.15（最大）** |
| D | Speaker-Conditioned Text Encoder | TextEncoderの第3層に話者ベクトルを条件付け | 話者類似度 **+0.20** |
| E | Mel Posterior Encoder | Linear Spec (513ch) → Mel Spec (80ch) に変更 | メモリ効率化 |

> **MOS貢献の読み方**: 論文のablation study (Table 1) より、VITS2フル構成 (MOS 4.47) から各改良を除去した場合のMOS低下量。例: Noise-Scaled MAS を除去すると MOS 4.47→4.32 に低下するため、この改良は +0.15 の品質向上に貢献している。

### VITS2論文の報告値

| 指標 | VITS | VITS2 | 差分 |
|------|------|-------|------|
| 自然性MOS (LJSpeech) | 4.38 | **4.47** | +0.09 |
| 話者類似度MOS (VCTK) | 3.79 | **3.99** | **+0.20** |
| 合成速度 | 1,779 kHz | 2,144 kHz | **+22.7%** |
| 学習速度 | 1.227 s/step | 0.951 s/step | **+22.5%** |

---

## 2. 推論グラフ影響分析

### piper-plusのONNX推論グラフに含まれるモジュール

export_onnx.py の `infer_forward()` を分析した結果:

```
ONNX推論グラフ (infer_forward)
├── enc_p (TextEncoder)              ← 推論時に実行される
├── dp (DurationPredictor)           ← 推論時に実行される
├── flow (ResidualCouplingBlock)     ← 推論時に実行される (reverse=True)
├── dec (Generator/HiFi-GAN)        ← 推論時に実行される
├── emb_g (Speaker Embedding)       ← マルチスピーカー時のみ
└── prosody_proj (Linear)           ← Prosody有効時のみ
```

### 推論グラフに含まれないモジュール（学習時のみ）

```
学習時のみ使用
├── enc_q (PosteriorEncoder)         ← 推論グラフに含まれない
├── MultiPeriodDiscriminator         ← 推論グラフに含まれない
├── WavLMDiscriminator               ← 推論グラフに含まれない
└── MAS (Monotonic Alignment Search) ← 推論グラフに含まれない
    └── 推論時は generate_path() で代替
```

### 各改良の推論影響判定

| 改良 | 推論影響 | ONNXサイズ | 推論速度 | **判定** |
|------|---------|-----------|---------|---------|
| **(C) Noise-Scaled MAS** | なし | ±0MB | ±0% | **導入推奨** |
| **(A) 敵対的Duration Predictor** | なし | ±0MB | ±0% | **導入推奨** |
| **(E) Mel Posterior Encoder** | なし | ±0MB | ±0% | **導入推奨** |
| **(D) Speaker-Conditioned TextEncoder** | 軽微 | +0.1MB | +1-2% | **導入可** |
| **(B) Transformer Flow** | あり | +7-8MB | +8-15% | **ラズパイ非推奨** |

---

## 3. 各改良の詳細分析

### (C) Noise-Scaled MAS — 導入推奨

**概要**: MASのコスト行列 `neg_cent` にガウスノイズを追加し、学習初期のアライメント探索を多様化。

**仕様 (p0p4k/vits2_pytorch参照)**:
- ノイズスケール初期値: `0.01`
- 減衰量: ステップごとに `2×10⁻⁶`
- ノイズ消失ステップ: `0.01 / 2e-6 = 5,000ステップ`（学習初期のみ）

**変更箇所**:
- `models.py` SynthesizerTrn: `mas_noise_scale` 属性追加、forward()のMAS計算にノイズ注入（~20行）

**推論への影響**: なし（MASは学習時のみ使用。推論時はDuration Predictorの出力からgenerate_path()で直接パス生成）

**既存チェックポイント互換性**: 互換あり（新属性はforward()内のみ使用、モデル重みに影響なし）

---

### (A) 敵対的Duration Predictor — 導入推奨

**概要**: Duration Predictorの出力を敵対的に判別するDuration Discriminatorを追加。

**Duration Discriminator構造 (p0p4k/vits2_pytorch参照)**:
```
DurationDiscriminatorV2
├── conv_1: Conv1d(192→192, k=3) + LayerNorm + ReLU
├── conv_2: Conv1d(192→192, k=3) + LayerNorm + ReLU
├── dur_proj: Conv1d(1→192, k=1)    ← log durationの投影
├── pre_out_conv_1: Conv1d(384→192, k=3) + LayerNorm + ReLU
├── pre_out_conv_2: Conv1d(192→192, k=3) + LayerNorm + ReLU
└── output_layer: Linear(192→1) + Sigmoid
```
- パラメータ数: **約556K**（学習時のみ使用）

**変更箇所**:
- `models.py`: DurationDiscriminatorV2クラス新規追加（~100行）
- `lightning.py`: 3つ目のオプティマイザ追加、Duration Discriminator学習ループ（~200行）
- `config.py`: `use_duration_discriminator` フラグ追加（~5行）

**推論への影響**: なし（Duration Discriminatorは学習時のみ。推論グラフにはDuration Predictor Generatorのみ含まれ、構造は変更なし）

**既存チェックポイント互換性**: Duration Discriminatorは新規モジュールのため再学習が必要

---

### (E) Mel Posterior Encoder — 導入推奨

**概要**: PosteriorEncoderの入力をLinear Spectrogram (513ch) → Mel Spectrogram (80ch) に変更。

**現在の構造**:
```
PosteriorEncoder (enc_q)
├── pre: Conv1d(513→192)    ← ここが 80→192 に変更
├── enc: WN (16層)
└── proj: Conv1d(192→192×2)
```

**変更箇所**:
- `models.py`: PosteriorEncoderの`in_channels`を513→80に変更（~5行）
- `lightning.py`/`dataset.py`: 学習時のスペクトログラム計算をMel Specに変更（~20行）

**推論への影響**: なし（enc_qは推論グラフに含まれない。パラメータ削減: (513-80)×192 = 83Kパラメータ減）

**既存チェックポイント互換性**: `enc_q.pre`の重みサイズが変わるため再学習が必要

---

### (D) Speaker-Conditioned TextEncoder — 導入可

**概要**: TextEncoderの第3 Transformerブロック（6層中）に話者ベクトルを加算条件付け。

**現在のTextEncoder構造**:
```
TextEncoder
├── emb: Embedding(n_vocab, 192)
├── encoder: Transformer Encoder (6層)
│   └── 各層: MultiHeadAttention(2heads) + FFN(192→768→192) + LayerNorm×2
└── proj: Conv1d(192, 192×2, 1)
```

**現在の話者埋め込み使用箇所** (emb_g):
- PosteriorEncoder (enc_q) — 学習時のみ
- ResidualCouplingBlock (flow) — 推論時
- DurationPredictor (dp) — 推論時
- Generator (dec) — 推論時
- **TextEncoder (enc_p) — 未使用** ← ここに追加

**追加モジュール**:
```python
cond_proj = Conv1d(gin_channels=512, hidden_channels=192, kernel_size=1)
# パラメータ: 512×192 + 192 = 98,688個 (~0.1MB)
```

**変更箇所**:
- `models.py` TextEncoder: `gin_channels`パラメータ追加、forward()に`g`引数追加（~15行）
- `attentions.py` Encoder: 第3層の後に`x = x + cond_proj(g)`を挿入（~10行）
- `models.py` SynthesizerTrn: `enc_p(x, x_lengths)` → `enc_p(x, x_lengths, g=g)`に変更（~5行）
- `export_onnx.py`: 同様にenc_p呼び出しを変更（~3行）

**推論への影響**: +0.1MB（ONNXサイズ74MB→74.1MB、+0.1%）、推論速度+1-2%低下（Conv1d 1層の加算のみ）

**既存チェックポイント互換性**: `gin_channels=0`でデフォルト無効化すれば後方互換可能。有効化時は`cond_proj`が新規初期化されるためファインチューニング推奨

---

### (B) Transformer Flow — ラズパイ非推奨

**概要**: ResidualCouplingBlockの各フローレイヤーにTransformer Encoderを追加。

**追加構造 (1フローレイヤーあたり)**:
```
TransformerCouplingLayer (pre_conv型)
├── pre_transformer: Encoder(hidden=96, 2層, 2heads)  ~111Kパラメータ
├── pre: Conv1d(96→192)                               ~18Kパラメータ
├── enc: WN(4層)                                      ~370Kパラメータ
├── post_transformer: Encoder(hidden=192, 2層, 2heads) ~444Kパラメータ
└── post: Conv1d(192→96)                               ~18Kパラメータ
```
- 1フローレイヤー: **~960Kパラメータ**
- 4フロー合計: **~3.8Mパラメータ**（既存Flow ~1.5Mに対し+2.3M増）

**推論への影響**:
- ONNXサイズ: +7-8MB（74MB→81-82MB、+10%）
- 推論速度: +8-15%低下（Self-Attention O(T²)計算追加）
- ラズパイ4でのRTF: 2-5× → 2.3-5.75×（リアルタイム比がさらに悪化）

**判定**: PC用途では許容範囲だが、**モバイル/ラズパイ制約では非推奨**

---

## 4. piper-plus独自拡張との互換性

| 既存機能 | Phase 1 (C,A,E) | Phase 2 (D) | 備考 |
|---------|-----------------|-------------|------|
| Prosody Features (A1/A2/A3) | 互換 | 互換 | DurationPredictor入力は変更なし |
| WavLM Discriminator | 互換 | 互換 | 独立Discriminatorとして維持 |
| SpeakerBalancedBatchSampler | 互換 | 互換 | バッチ構成は変更不要 |
| EMA (Generator) | 互換 | 互換 | HiFi-GANに変更なし |
| FP16 Mixed Precision | 互換 | 互換 | VITS2論文でもMixed Precision使用 |

---

## 5. 導入ロードマップ

### Phase 1: 推論影響ゼロの改良（推奨）

| 順序 | 改良 | 変更量 | 期待効果 | リスク |
|------|------|--------|----------|--------|
| 1 | Noise-Scaled MAS (C) | ~20行 | アライメント安定化 | なし |
| 2 | 敵対的Duration Predictor (A) | ~300行 | MOS +0.14、リズム自然性向上 | 学習ループ複雑化 |
| 3 | Mel Posterior Encoder (E) | ~25行 | 学習メモリ効率化 | 前処理パイプライン変更 |

**合計**: ONNXサイズ ±0MB、推論速度 ±0%

### Phase 2: 軽微な影響の改良（オプション）

| 順序 | 改良 | 変更量 | 期待効果 | リスク |
|------|------|--------|----------|--------|
| 4 | Speaker-Conditioned TextEncoder (D) | ~30行 | 話者類似度+0.20 | ONNX +0.1MB |

### 導入しない改良

| 改良 | 理由 |
|------|------|
| Transformer Flow (B) | ONNXサイズ+7-8MB、推論速度+8-15%低下。ラズパイでのRTF悪化が許容不可 |

---

## 6. VITS2以降のTTSアーキテクチャ動向

### VITS3は存在するか？

**正式な「VITS3」は存在しない。** VITS原著者チームによる後継論文はVITS2以降発表されていない。

### TTSアーキテクチャの世代変遷

```
2021-2023: VITS系 (VAE + Normalizing Flow + GAN)
    ↓
2023-2024: Diffusion / Flow Matching系 (Matcha-TTS, StyleTTS2, F5-TTS)
    ↓
2024-2026: LLM + Codec系 ← 現在の主流
           (CosyVoice, Fish Speech, IndexTTS, Spark-TTS)
```

### 主要モデル比較

| モデル | 年 | 方式 | 日本語 | OSS | 特徴 |
|--------|-----|------|--------|-----|------|
| **StyleTTS 2** | 2023 | Style Diffusion + WavLM | 未 | MIT | 人間超えCMOS |
| **Matcha-TTS** | 2024 | Flow Matching | 不明 | MIT | 少ステップで高品質 |
| **F5-TTS** | 2024 | Flow Matching + DiT | 対応 | OSS | アライメント不要 |
| **CosyVoice 3.0** | 2025 | LLM + Flow Matching | 対応 | Apache-2.0 | 9言語+18方言 |
| **Fish Speech 1.5** | 2024 | Dual-AR + GFSQ | 対応 | Apache-2.0 | 30万時間学習 |
| **Kokoro-82M** | 2025 | StyleTTS2ベース | 対応 | Apache-2.0 | 82Mで軽量高品質 |
| **Chatterbox** | 2025 | Llama 500M | 対応 | MIT | Zero-shot cloning |

### VITSの現在地

VITSは「最先端」ではないが、**軽量・高速・エッジ展開**において依然として強み:
- モデルサイズ: 数十MB（LLM系は0.5B+）
- 推論速度: リアルタイム×80以上
- 学習コスト: 少量データ・少計算量で十分な品質

### piper-plusの次世代移行候補

| 候補 | モデルサイズ | メリット | デメリット |
|------|------------|---------|-----------|
| **VITS2段階的導入** (本計画) | ~74MB (現行同等) | 既存資産を活用、最小コスト | 改善幅は限定的 |
| **Kokoro-82M方式** | ~82M | 軽量で高品質、$1000学習 | アーキテクチャ全面書換え |
| **F5-TTS方式** | 数百MB | 音質大幅改善 | モデルサイズ増大 |
| **CosyVoice方式** | 0.5B+ | 最高品質、多言語 | エッジ展開困難 |

---

## 7. 参考実装

| リポジトリ | Stars | ライセンス | 備考 |
|-----------|-------|-----------|------|
| [p0p4k/vits2_pytorch](https://github.com/p0p4k/vits2_pytorch) | 547 | MIT | 全機能フラグ制御可。**参考実装として最適** |
| [daniilrobnikov/vits2](https://github.com/daniilrobnikov/vits2) | 634 | MIT | WIP |
| [fishaudio/Bert-VITS2](https://github.com/fishaudio/Bert-VITS2) | 8,700 | — | メンテ終了 |
| [litagin02/Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2) | 1,200 | AGPL-3.0 | 日本語特化 |

---

## 参考文献

- [VITS2 論文 (arXiv:2307.16430)](https://arxiv.org/abs/2307.16430)
- [VITS2 デモページ](https://vits-2.github.io/demo/)
- [p0p4k/vits2_pytorch](https://github.com/p0p4k/vits2_pytorch)
- [StyleTTS 2 (NeurIPS 2023)](https://arxiv.org/abs/2306.07691)
- [Matcha-TTS (ICASSP 2024)](https://arxiv.org/abs/2309.03199)
- [F5-TTS](https://arxiv.org/abs/2410.06885)
- [CosyVoice 2](https://arxiv.org/abs/2412.10117)
- [Fish Speech 1.5](https://arxiv.org/abs/2411.01156)
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)
- [Benchmarking VITS vs Style-BERT-VITS2 for Japanese](https://arxiv.org/html/2505.17320v1)
