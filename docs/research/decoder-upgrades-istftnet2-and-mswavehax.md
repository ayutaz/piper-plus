# Decoder Upgrade 深堀り: iSTFTNet2-MB (A-1) と MS-Wavehax (A-2)

統合改善調査レポート [`improvement-survey-2026-06-15.md`](improvement-survey-2026-06-15.md) の A-1 / A-2 に対する深堀りコンパニオン文書。 v1.12.0 で導入済みの **MB-iSTFT-VITS** との差分を**コード位置と数値で明示**し、 「既存実装の置き換え」 ではなく **「枠組み流用 + 増築」** であることを示す。

> [!NOTE]
> **本ドキュメントの目的:**
>
> - A-1 / A-2 はどちらも名前に "iSTFT" を含み既存 MB-iSTFT-VITS と紛らわしいため、 差分を一文書に集約。
> - 統合判断 (J 章) で「Matcha-TTS / StyleTTS2 とは別軸で並走させる」と整理した根拠 (既存資産流用度) を可視化。
> - 実装着手時の「既に対応済みでは?」という誤解を防ぐ。
>
> **2026-06-15 Phase 4 deep-research 完了:** §2.5 のリスク再評価 (**Risk 1: 中→低** / Risk 2: 中→高 / **Risk 3: 中→低**)、 Q10-Q20 全 11 件分類完了 (§2.5 末尾の総括表参照)。 残るオープンクエスチョンは PoC 待ち。

**メタ情報:**

- 作成日: 2026-06-15
- 対象バージョン: v1.13.0 (`dev`, commit 7d3aa34e)
- 参照: `src/python/piper_train/vits/mb_istft.py` (実装済み)、 `src/python/piper_train/vits/stft_onnx.py`
- 出典:
  - 既存実装の論文: [arXiv 2210.15975](https://arxiv.org/abs/2210.15975) (Kawamura et al., MB-iSTFT-VITS, ICASSP 2023)
  - A-1: [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) (Kaneko et al., iSTFTNet2, Interspeech 2023, NTT)
  - A-2: [arXiv 2506.03554](https://arxiv.org/html/2506.03554) (Yoneyama et al., MS-Wavehax, Interspeech 2025)

---

## 1. 既存実装の正確な押さえ — MB-iSTFT-VITS (v1.12.0 以降)

### 1.1 ソースコード上の事実

`src/python/piper_train/vits/mb_istft.py:14` の import を確認すると:

```python
from torch.nn import Conv1d, ConvTranspose1d, functional as F
```

**`Conv2d` を import すらしていない。** つまり **1D CNN のみで構成された backbone**。

`MBiSTFTGenerator` クラス (`mb_istft.py:133-216`) の主要設定:

| 要素 | 値 | コード行 |
|------|----|---------|
| Backbone op | `Conv1d` / `ConvTranspose1d` のみ | L14 / L167 / L180 |
| `upsample_rates` | `(4, 4)` → 神経 upsampling **16x** | L148 |
| Sub-band 数 (PQMF) | 4 | `PQMF` クラス L25 |
| iSTFT hop | 4x | (出力段) |
| 合計 upsampling | **16x × 4x × 4x = 256x** | docstring L139 |
| 出力 shape | `[B, 1, T]` | (HiFi-GAN と互換) |

`src/python/piper_train/vits/stft_onnx.py:5` のコメント:

```python
# are expressible with Conv1d / ConvTranspose1d (ONNX opset 15).
```

→ **STFT/iSTFT の ONNX 化も Conv1d ベース**で構成されている。

### 1.2 ベンチマーク (PR #320 内部 A/B、 [`docs/spec/audio-parity-contract.toml`](../spec/audio-parity-contract.toml))

| メトリック | 値 |
|-----------|----|
| Decoder 単体 CPU 推論 (100 phoneme p50) | **76.2ms** (vs HiFi-GAN 168.2ms = **2.21x 高速**) |
| End-to-end Latency P50 (canonical: Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs) | **27ms** |
| 7 ランタイム互換 | 出力 shape `[B, 1, T]` 維持で C# / Rust / Go / WASM / C++ 変更不要 |

### 1.3 「枠組み」と「中身」の分離

MB-iSTFT-VITS が piper-plus に提供しているもの:

| レイヤー | 中身 | 状態 |
|---------|------|------|
| **出力段の枠組み** | multi-band 生成 + iSTFT + PQMF (4 sub-band × iSTFT 4x) | ✅ 完成 |
| **Backbone CNN** | 1D Conv のみで時間軸方向にモデル化 | ✅ 完成 (が、 ここに改善余地) |
| **CLI / 学習統合** | `--c-sub-stft` (sub-band STFT loss 係数) 他 | ✅ 完成 |
| **ONNX export** | `vits/stft_onnx.py` で torch.stft/istft を conv に置換 | ✅ 完成 |
| **7 ランタイム実装** | 出力 shape 互換で全 runtime 動作 | ✅ 完成 |

→ A-1 / A-2 はこの**枠組みを再利用しつつ、 別の軸で性能を伸ばす提案**。 置換対象ではない。

---

## 2. A-1: iSTFTNet2-MB — backbone 置換による CPU 高速化

### 2.1 核心の差分

| 観点 | 既存 MB-iSTFT-VITS | iSTFTNet2-MB |
|------|-------------------|--------------|
| **Backbone** | **1D CNN のみ** (Conv1d) | **1D + 2D ハイブリッド** (1D→2D 変換を前倒し、 2D CNN で**スペクトログラム時間×周波数構造**をモデル化) |
| **神経 upsampling rate** | 16x (`(4, 4)`) | **8x (`(2, 2)`)** ← **半減** |
| **iSTFT hop** | 4x | 4x (同じ) |
| **PQMF sub-band 数** | 4 | 4 (同じ) |
| **合計 upsampling** | 256x | **128x** (16x×8x 削減) |
| **論文** | Kawamura et al., ICASSP 2023 | Kaneko et al., **iSTFTNet 原著者**, Interspeech 2023 |

### 2.2 なぜ 2D CNN で速くなるのか (直感)

- 1D CNN は時間軸のみで上下に層を重ねて up を稼ぐ → 神経 upsampling 16x が必要
- 2D CNN は**スペクトログラム上の時間 × 周波数の局所相関**を直接モデル化できる → 周波数軸の構造をネットワークが学習するので、 神経 upsampling は **8x** で済む
- 結果: 2D conv の計算コスト < 削減された 1D up のコスト → **正味で速くなる**

### 2.3 数値 (論文値、 LJSpeech / Intel i7-12700H シングルスレッド CPU 実測)

| モデル | RTF | MOS | params |
|--------|-----|-----|--------|
| HiFi-GAN V2 (baseline) | 0.052 | 4.21 | — |
| iSTFTNet-MB (= **既存 piper-plus 相当**) | — | 4.05 | — |
| **iSTFTNet2-MB** | **0.011** (HiFi-GAN V2 の **21%**) | **4.25** | **0.83M** |
| iSTFTNet2-Small | 0.018 | 4.22 (HiFi-GAN V2 と統計的に区別不可, p>0.05) | 0.79M |

**着目点:**

- iSTFTNet2-MB は 1D 版 iSTFTNet-MB を MOS・cFW2VD 両方で**有意に上回る** (品質劣化なし)
- 0.83M params は極小 → footprint も改善
- RTF 0.011 = HiFi-GAN V2 の **21%** = 約 5x 高速

### 2.4 既存実装からの差分作業

| 作業項目 | 流用度 | 内容 |
|---------|-------|------|
| **PQMF (4 sub-band)** | 100% 流用 | `mb_istft.py:25` の `PQMF` クラスはそのまま |
| **iSTFT (4x hop)** | 100% 流用 | `stft_onnx.py:19` の `OnnxISTFT` はそのまま |
| **CLI / 学習統合** | 100% 流用 | `--c-sub-stft` 他のハイパーパラメータはそのまま |
| **MBiSTFTGenerator backbone** | **書き換え** | `Conv1d` / `ConvTranspose1d` を 1D-2D ハイブリッドに置換 |
| `upsample_rates` | **変更** | `(4, 4)` → `(2, 2)` |
| **ONNX export** | 検証必要 | Conv2d が opset / 7 ランタイムで op gap なく動くか |
| **6lang base 再学習** | 必要 | backbone が変わるため weights 再学習必須 |

→ **「出力段の枠組み (multi-band + iSTFT + PQMF) は 100% 流用、 backbone のみ 1D-2D 改造」**。 統合作業は限定的だが**学習リソースは必要**。

### 2.5 主要リスク (2026-06-15 deep-research で 1 次ソース実証済み)

> **調査方法:** ORT 公式ドキュメント (NNAPI EP / XNNPACK EP / CoreML EP / Quantization)、 GitHub の WebGPU operators テーブル、 Kaneko らの NTT 公式 iSTFTNet2 プロジェクトページ、 関連 OSS 実装 (FENRlR/MB-iSTFT-VITS2 / hcy71o/MB-iSTFT-VITS-with-AutoVocoder) を WebFetch + WebSearch で直接検証。

#### Risk 1: Conv2d / ConvTranspose2d の ONNX op coverage —  **中→低** (実は機会)

ORT 1.20+ の各 EP × {Conv2d / ConvTranspose2d / QLinearConv (INT8) / INT4} マトリクス:

| EP | Conv2d | ConvTranspose2d | QLinearConv (INT8) | INT4 Conv | ソース |
|----|--------|-----------------|---------------------|-----------|--------|
| **CPU EP (全 OS)** | ✅ Full | ✅ Full | ✅ Full | N/A | ORT docs |
| **CUDA EP** | ✅ Full | ✅ Full | ✅ Full | N/A | ORT docs |
| **DirectML EP** | ✅ Full | ✅ Full | ✅ Full | N/A | ORT docs |
| **OpenVINO EP** | ✅ Full | ✅ Full | ✅ Full | N/A | ORT docs |
| **CoreML EP (MLProgram)** | ✅ **1D/2D 両対応** | ✅ 制約あり (kernel_shape default、 SAME_UPPER/LOWER padding 不可) | ❌ 未掲載 | N/A | [CoreML EP doc](https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html) |
| **CoreML EP (NeuralNetwork)** | ✅ 1D/2D 両対応 | ❌ 未掲載 → CPU fallback | ❌ 未掲載 | N/A | 同上 |
| **WebGPU EP** | ✅ opset 1+ (kernel perf 最適化未完) | ✅ opset 1+ (kernel perf 最適化未完) | ❌ **QLinearConv 未掲載**、 QDQ (DequantizeLinear + fp32 Conv) で代用 | MatMulNBits のみ | [WebGPU operators](https://github.com/microsoft/onnxruntime/blob/main/js/web/docs/webgpu-operators.md) |
| **NNAPI EP** | ✅ **2D 専用**、 weights/bias 定数必須 | ❌ **未掲載** → CPU fallback | ✅ 2D 専用、 quant params 定数必須 | N/A | [NNAPI EP doc](https://onnxruntime.ai/docs/execution-providers/NNAPI-ExecutionProvider.html) |
| **XNNPACK EP** | ✅ **2D 専用** (1D 非対応) | ✅ 2D 専用 (ORT 1.14+) | ✅ 2D 専用 | N/A | [XNNPACK EP doc](https://onnxruntime.ai/docs/execution-providers/Xnnpack-ExecutionProvider.html) |
| **INT4 (全 EP 横断)** | — | — | — | ❌ **Conv 全般で未対応**、 MatMul + Gather のみ | [ORT Quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) |

**逆転発見 — A-1 (2D 化) は mobile EP にとって「むしろ朗報」:**

- **XNNPACK は 1D Conv 非対応 (2D 専用)** → 既存 piper-plus の 1D MB-iSTFT は XNNPACK 最適化を受けられていない。 **A-1 で 2D 化することで XNNPACK 適用範囲に入る**。
- **NNAPI も Conv は 2D 専用** → A-1 で 2D conv 中心になれば NNAPI ハードウェアアクセラレーション対象に。
- **CoreML は 1D / 2D 両対応**なので invariant。
- INT8 (QLinearConv) も XNNPACK / NNAPI とも 2D 専用サポート → 量子化路線で 2D 化は positive。

**残る真のリスク (2 件):**

1. **ConvTranspose2d の coverage gap:** NNAPI EP と CoreML NeuralNetwork で ConvTranspose が未掲載 → CPU fallback。 iSTFTNet2-MB の 2D upsampling 段が ConvTranspose を使う場合、 NNAPI / 古い CoreML での GPU/NPU 加速が効かない。 **対策:** PixelShuffle (Reshape + Transpose) で代用、 または ConvTranspose を最上層のみに局所化し他は CoreML MLProgram (iOS 15+) / XNNPACK でカバー。
2. **Conv の INT4 量子化はネイティブ非対応:** ORT の INT4 weight-only は MatMul と Gather のみ。 Conv backbone を INT4 化したい場合は QDQ + DequantizeLinear + INT8 Conv の hybrid 戦略しかない。 **B-6 (INT4) の適用範囲は MatMul-rich モデルに限定**される事実が確定。

**結論:** リスク 1 は当初想定 (op gap 多発) より**軽い** → **中 → 低**。 むしろ A-1 自体が mobile EP の最適化サポートを引き込む方向に働く。

#### Risk 2: End-to-end 統合の先行例 — **高** (zero prior art 確定)

調査結果 (1 次ソース照合):

| 統合実例 | iSTFTNet2 ベースか | end-to-end VITS 統合か | 数値 |
|---------|-------------------|----------------------|------|
| **MB-iSTFT-VITS** ([Kawamura 2022](https://arxiv.org/pdf/2210.15975)、 piper-plus 既存) | ❌ iSTFTNet**1** | ✅ VITS | RTF 0.066 (Intel i7) |
| [FENRlR/MB-iSTFT-VITS2](https://github.com/FENRlR/MB-iSTFT-VITS2) | ❌ 1D Conv のみ、 iSTFTNet2 言及なし | ✅ VITS2 | — |
| [hcy71o/MB-iSTFT-VITS-with-AutoVocoder](https://github.com/hcy71o/MB-iSTFT-VITS-with-AutoVocoder) | ❌ AutoVocoder で iSTFT 置換 | ✅ VITS | 別系統 |
| **FLY-TTS** ([Guo 2024 Interspeech](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf)) | ❌ 別アーキ | ✅ end-to-end | MOS **4.12** (vs MB-iSTFT 4.08)、 fewer params |
| **iSTFTNet3 / 後続 Kaneko 論文** | — | — | **存在せず** (Kaneko らは 2024 から discriminator 系へ移行) |

→ **iSTFTNet2 (1D-2D hybrid) を end-to-end VITS/VITS2 に統合した OSS / 論文は皆無**。 A-1 は完全な未開拓領域。 論文値 (RTF 0.011 / MOS 4.25 / 0.83M params) が end-to-end VITS2 統合後にどう変わるか**先行データなし**。

**ただし救い:** FLY-TTS (Interspeech 2024) が MB-iSTFT を超える MOS 4.12 を達成しており、 **piper-plus が併走候補として検討すべき選択肢**になる。 「iSTFTNet2 にこだわらない」ならよりリスクの低い経路あり。

**結論:** リスク 2 は **高 (zero prior art)**。 対策は (a) 小規模 PoC (1 言語 50 epoch) で end-to-end 性能を最初に測る、 (b) FLY-TTS を並走候補に追加して保険を掛ける。

#### Risk 3: 2D conv の memory locality / mobile CPU 性能 — **低** (誤解、 むしろ機会)

調査結果:

- **im2col + GEMM が mobile CPU の標準**: ARM Cortex-A / XNNPACK / CMSIS-NN / NEON すべて im2col 戦略で 2D conv を吸収。 cache 局所性は GEMM 最適化で対応済み (参照: [arXiv 2005.06410](https://arxiv.org/pdf/2005.06410) High Performance Convolution Operators for ARM-based Multicore Processors)。
- **im2col のメモリ overhead 問題は kernel size に依存**: 3x3 / 3x5 のような小 kernel ではフットプリント拡大が無視できる範囲。 iSTFTNet2 の 2D conv は周波数軸方向の小 kernel 想定 → 問題化しにくい。
- **ND→1D 分解の最適化**: 2D kernel を 2 つの 1D kernel に分解する手法 (O(MNk²)→O(2MNk)) があり、 1D-2D hybrid は pure 2D より cache friendly になる余地あり。
- **XNNPACK の 2D conv 最適化が手厚い**: SIMD tiling / Winograd / im2col 最適化が 2D に集中投資されている (1D は非対応)。 A-1 の 2D 化はこれを引き出せる。

**Mobile / 組込実用化の shape constraints:**

| 制約 | 推奨値 | 根拠 |
|------|--------|------|
| 2D kernel size | 3x3 〜 3x5 程度に抑制 | im2col フットプリント増加を回避 |
| 2D stride | 1 か 2 (3 以上は XNNPACK 最適化が薄い) | XNNPACK 実装の sweet spot |
| ConvTranspose | 上層 1 〜 2 段に局所化 | NNAPI / CoreML NN 未サポートを最小化 |
| Conv2d 比 1D conv 比率 | 1D : 2D = 1:1 〜 2:1 | im2col メモリ overhead と SIMD 効率のバランス |

**結論:** リスク 3 は **低 (誤解)**。 「2D は cache unfriendly で遅い」は一般化しすぎで、 modern mobile EP の im2col + GEMM 最適化で吸収される。 むしろ XNNPACK / NNAPI の 2D 最適化に乗れる利点が勝つ。

#### 統合判定: 当初リスク評価の更新

| Risk | 当初評価 (Phase 1) | 1 次ソース実証後 (Phase 2) | 主因 |
|------|--------------------|----------------------------|------|
| 1. ONNX op coverage | 中 | **低** | XNNPACK / NNAPI は 2D 専用 → A-1 で 2D 化は機会 |
| 2. End-to-end 統合 | 中 | **高** | zero prior art 確定 |
| 3. 2D conv memory locality | 中 | **低** | im2col + GEMM で吸収、 小 kernel なら overhead 無視可 |

**真の主要リスクは Risk 2 (zero prior art) に集中**。 残り 2 件は誤った懸念だった。

**Phase 1 の PoC 設計改訂:**

1. **A-1 PoC を**「リスク 2 解消のための small-scale ablation」**に再定義** — 1 言語 (JA) / 50 epoch で end-to-end VITS2 + iSTFTNet2-MB の MOS / RTF / footprint を測る。 失敗時 (MOS ドロップ大) は FLY-TTS に切替。
2. **量子化路線 (B-4 / B-6) との互換性検証**は別 track で並走 — Conv の INT4 がネイティブ未対応のため、 配布サイズ最適化は MatMul-rich モデル (Transformer 系) に分散させる戦略を検討。
3. **ConvTranspose を上層 1-2 段に局所化**するアーキ制約を Phase 1 から導入 — NNAPI / CoreML NN での CPU fallback 範囲を最小化。

#### 追加調査結果 (Phase 2 オープンクエスチョン Q10〜Q12 の 1 次ソース実証)

##### Q10. WebGPU EP の量子化対応 — **部分解決** (weight-only path のみ確実に動作)

- 確定: WebGPU operators テーブルに **DequantizeLinear ✅ サポート** / **QuantizeLinear ❌ 未掲載**
- 2025 年の WebGPU + ORT Web 実装ガイドは「INT8 / FP16 / INT4 で deploy」を active practice として推奨 ([WebGPU + ORT Web inference guides](https://medium.com/@Modexa/8-webgpu-onnx-runtime-web-inference-guides-4220cff29ad8))
- ORT の主要 quantization 路線は **MatMulNBits (INT4 weight-only)** で MatMul に対する WebGPU 最適化に集中投資 (Conv は対象外)
- **対策パス (確定):**
  - **入力 / 出力は FP32**、 **重みのみ INT8** (DequantizeLinear 経由) なら WebGPU で確実に動作
  - 入出力 INT8 (full QDQ) が必要な場合は CPU EP fallback、 WebGPU は MatMul-rich モデル (Transformer 系) に限定使用
  - piper-plus の MB-iSTFT-VITS / iSTFTNet2-MB は **weight-only quantization で配布サイズ削減を主目的**にし、 WebGPU レイテンシは FP16 で確保するのが現実解
- 残る未確定: 量子化 Conv の output が float か int かは ORT GitHub issue #24427 で議論中、 piper-plus の MB-iSTFT export 時に実機検証必要

##### Q11. NNAPI EP の長期サポート — **substantially 解決** (移行戦略確定)

- 確定: **NDK NNAPI は Android 15 で OS 側 deprecated** ([Android NNAPI Migration Guide](https://developer.android.com/ndk/guides/neuralnetworks/migration-guide))。 NNAPI Runtime は modular system として継続サポートだが、 Google は TensorFlow Lite in Play Services / AICore を推奨。
- ORT 側の動き:
  - 公式 NNAPI EP doc には deprecation 明記なし (継続サポートの建前)
  - 公式 [mobile tutorial](https://onnxruntime.ai/docs/tutorials/mobile/) は「**量子化モデル → CPU EP、 非量子化 → XNNPACK**」を推奨 → NNAPI EP は主流から外れている
  - **Qualcomm が 2026-05 に QNN EP の Plugin EP を公開** ([Qualcomm blog 2026-05](https://www.qualcomm.com/developer/blog/2026/05/qualcomm-launches-the-first-onnx-runtime-plugin-execution-provider)) — Snapdragon SoC 向けの専用高速パス。 NPU / Hexagon DSP 活用
- **piper-plus 向け移行戦略 (確定):**
  - **Snapdragon (Qualcomm SoC) Android** → **QNN EP** (専用、 NPU/Hexagon 加速)
  - **その他 Android (MediaTek / Exynos 等)** → **XNNPACK EP** (汎用、 量子化対応、 1.14+ で ConvTranspose 2D サポート)
  - **iOS** → CoreML EP (MLProgram) + XNNPACK fallback
  - **CPU EP** → 全 OS の最終 fallback
- 含意: **B-1 (Android NNAPI EP) は 「短期的な互換性確保のため最初に投入」**、 **中期は B-2 (Android XNNPACK) + 新規施策 「QNN EP 統合」 へ重心シフト** が妥当
- **A-1 への影響:** 1D-2D ハイブリッド化は **XNNPACK / QNN 両方とも 2D Conv に最適化を集中投資**しているため、 long-term path でも追い風

##### Q12. iSTFTNet2 + VITS2 統合の MOS 劣化幅 — **一般則は確定**、 iSTFTNet2 specific は依然 zero prior art

- 一般則 (確定): **standalone vocoder の MOS は end-to-end TTS 統合で 0.2〜0.5 ポイント劣化が典型**。 主因は (a) ground-truth mel で学習した vocoder が predicted mel で動く際の distribution gap (Tacotron + WaveNet 事例: MOS 2.91 → fine-tune 後 3.43 = 0.52 改善 = 統合 baseline は 0.5 ポイント低い)、 (b) acoustic model 側の mel 予測誤差の伝播。
- **対策パス (確定):**
  - **End-to-end joint training (VITS 系のスタンス)** は cascade TTS より劣化が小さい — piper-plus は元々 VITS2 ベースなのでこの利点を継承
  - **Vocoder fine-tuning on predicted mel** で gap 縮小可能 (PoC 時に実施推奨)
  - **大型 discriminator (WavLM 等)** で perceptual quality を上げる — piper-plus はすでに WavLM Discriminator 実装済み (`CLAUDE.md` 記載) なので転用可能
- **FLY-TTS (Interspeech 2024) 詳細判明 (代替候補として濃厚):** [PDF](https://www.isca-archive.org/interspeech_2024/guo24c_interspeech.pdf)
  - **decoder = ConvNeXt blocks × 6** で Fourier spectral coefficients 生成 → iSTFT (nfft=1024, hop=256)
  - **grouped parameter-sharing** を text encoder (g₁=2, m₁=3) と flow-based model (g₂=2, m₂=2) に導入
  - MB-iSTFT-VITS より少ない params で同等以上の MOS を達成
  - iSTFTNet2 と異なり **2D-CNN を使わず ConvNeXt (1D で深い受容野)** → mobile EP 互換性が iSTFTNet2 より高い可能性
- **iSTFTNet2-specific の劣化幅は依然不明**。 ただし一般則から **0.2〜0.5 MOS ドロップを覚悟**して PoC を計画すべき。 論文値 4.25 が end-to-end で 3.75〜4.05 まで落ちる可能性。 vs FLY-TTS の 4.12 と並ぶかは PoC で測る。

#### Phase 3 追加調査結果 (Q13〜Q16 の 1 次ソース実証)

##### Q13. iSTFTNet2 specific の end-to-end MOS — **依然 zero prior art**、 ただし周辺データで PoC リスクを定量化

- 確認: 2024-2025 の 2D-CNN vocoder を VITS / VITS2 に統合した実装・論文は引き続き見つからず
- 関連先行例 (周辺データ):
  - **DurIAN-E 2** ([arXiv 2410.13288](https://arxiv.org/pdf/2410.13288)) — Duration Informed Attention + adaptive VAE + adversarial、 expressive TTS。 別系統だが「decoder family を刷新しつつ VITS スタイルの adversarial training を維持」した実例
  - **Wave-U-Net Discriminator** ([arXiv 2303.13909](https://arxiv.org/pdf/2303.13909)) — 軽量 discriminator 系の補強パッチ。 PoC で discriminator 側の負荷を抑えるオプションとして検討対象
- **PoC 設計案 (Q13 への対応):**
  - Phase 1 (1 言語 / 50 epoch) で iSTFTNet2-MB end-to-end MOS を **3.75〜4.05 想定**で測定 (論文 4.25 から 0.2-0.5 ドロップ想定、 Q12 一般則)
  - 失敗判定基準 = MOS < 3.75 または既存 MB-iSTFT-VITS から有意低下 (p<0.05)
  - 失敗時の切替先 = **FLY-TTS (ConvNeXt × 6 + iSTFT)** が最有力 (MOS 4.12 実証済み、 2D-CNN 不使用で mobile EP 互換性高)
- **結論:** Q13 は依然 zero prior art だが、 PoC のスコープ・成功基準・代替路線が確定 → 「不確定要素 → 計画されたリスク」に格下げ可能

##### Q14. 量子化 Conv の WebGPU 動作 — **practical な full QDQ は依然 limited**、 weight-only 一択

- ORT 公式 quantization tooling の WebGPU 互換性に関する具体例は GitHub に見つからず
- 関連 active issue:
  - [#24427](https://github.com/microsoft/onnxruntime/issues/24427) "Internal computational problems using quantified model inference" — 未解決、 QDQ 周辺の精度問題が active development 中
  - [#14707](https://github.com/microsoft/onnxruntime/issues/14707) "[Performance] why is the inference latency of onnx QDQ similar to float32" — QDQ がサイズ削減はできるが速度効果が出ない既知問題
- WebGPU specific の practical QDQ INT8 inference example は OSS で見つからず、 ORT-Web の主要量子化路線は **MatMulNBits (INT4 weight-only)** に集中投資
- **結論:** Q14 は **「WebGPU 上の Conv quantization は実運用 unsupported に近い」** と確定。 piper-plus の最終戦略:
  - **WebGPU 配布 = FP16 + weight-only INT8 (DequantizeLinear 経由)** のみ
  - input/output INT8 化が必要なら **WASM EP / CPU EP fallback**
  - 「WebGPU で速くて軽い」を狙うなら Conv 系より MatMul-rich モデル (将来の Matcha-TTS / StyleTTS2 ライン) に重心
- piper-plus B-4 (INT8) / B-6 (INT4) との整合: **「mobile = INT8 OK / WebGPU = weight-only に限定」** のレイヤード戦略を明示

##### Q15. QNN EP のオペレータ coverage — **fully 解決** (1D-2D hybrid Conv は QNN HTP で full acceleration)

[QNN EP doc](https://onnxruntime.ai/docs/execution-providers/QNN-ExecutionProvider.html) と Qualcomm 公式ドキュメントの直接検証結果:

| Operator | QNN EP サポート | Backend (CPU/GPU/HTP) |
|----------|----------------|----------------------|
| `ai.onnx:Conv` (1D / 2D / 3D) | ✅ 全次元 (3D は ORT 1.18+) | HTP (NPU) で fully accelerated |
| `ai.onnx:ConvTranspose` (1D / 2D / 3D) | ✅ 全次元 (3D は ORT 1.18+) | HTP で accelerated |
| `com.microsoft:QuantizeLinear` / `DequantizeLinear` | ✅ | HTP |
| `QLinearConv` | ❌ 未掲載 | — (QDQ format で代用) |
| `STFT` / `IFFT` / `DFT` / `ComplexMul` | ❌ 未掲載 | CPU fallback または Conv 実装 |
| Dynamic shapes | ❌ **未サポート** | fixed shape 必須 |

- **HTP backend 制約 (確定):** **HTP は quantized only** → INT8 weights + INT16 activations を ORT QNN QDQ flow で生成、 calibration dataset 必要 (Hexagon NPU 推奨設定)
- piper-plus への含意:
  - A-1 の 1D-2D hybrid Conv は **QNN HTP で fully accelerated** ← Snapdragon 端末で最高速
  - iSTFT 段は piper-plus 既存 `stft_onnx.py` の Conv 実装パターンを継承すれば QNN にも乗る
  - **Dynamic shape 制約への対応**: piper-plus は phoneme 長が可変 → max length で fixed padding する変換が必要 (NNAPI / CoreML でも同様の手法あり)
  - 学習時に QAT (Quantization-Aware Training) を入れる必要が出てくる (B-5 量子化品質回帰測定スイートで担保)
- **結論:** Q15 は **fully 解決**、 A-1 は QNN HTP で最も恩恵を受ける路線。 dynamic shape 対応は別途実装課題として顕在化 (新規 open question 17)

##### Q16. CC-BY-4.0 → Apache-2.0 派生関係 — **compatible** (legal grey zone は限定)

- 確定 ([Creative Commons 公式](https://creativecommons.org/about/cclicenses/)):
  - CC BY 4.0 は **「distribute, remix, adapt, and build upon the material in any medium or format」を許可**
  - 義務は **attribution (帰属表示)** のみ — share-alike なし
  - 派生作品のライセンス選択は自由 (CC-BY-SA と違い再ライセンス可能)
- 確定 (Linux Foundation [OpenMDW](https://lfaidata.foundation/blog/2025/07/22/simplifying-ai-model-licensing-with-openmdw/)):
  - **推奨パターン**: **CC-BY-4.0 for data components (datasets, model weights, evaluation data)** / **Apache-2.0 or MIT for code (architecture, training scripts, inference code)**
  - piper-plus の現状 (CC-BY-4.0 CML-TTS → Apache-2.0 inference code + 学習済み model weights 配布) はこのパターンと整合
- 残る legal grey zone:
  - 学習済み model weight が dataset の "derivative work" に該当するかの**法的判断は司法判断未確定**
  - ただし主流コミュニティ実践 (Hugging Face / OpenSLR / ESPnet / Coqui-TTS) は **CC-BY-4.0 データから派生した weights を Apache-2.0 で公開すること自体は問題視されていない**
  - **必須対応:** 配布物 (model card / README) で**データセット出典 (CML-TTS) を明示**することで CC-BY-4.0 attribution 義務を履行
- **結論:** Q16 は **practical には compatible**、 piper-plus の **HF model card に CML-TTS attribution を明記** することで対応完了。 完璧な法的安全性が必要なら別途 legal counsel 推奨だが、 OSS 慣行としては成熟したパターン。

#### Phase 4 追加調査結果 (Q17 の 2 ラウンド調査で converge)

##### Q17. QNN HTP の dynamic shape 回避策 — **CONVERGED** (bucketed pre-compile + encoder-decoder 分離 hybrid を確定)

**確定戦略 (Round 1 + Round 2 統合):**

| 要素 | 推奨実装 | 根拠 |
|------|---------|------|
| **回避方式** | (a) bucketed fixed shapes (b) encoder/decoder 分離 hybrid の併用 | Kokoro CoreML / Whisper QIDK / ExecuTorch QNN Llama すべて同パターン |
| **Bucket 数** | **3-4 段** (例: 64 / 128 / 256 / 400 phoneme) | Hexagon HTP の 32-bit virtual address space + TCM 8 MiB / L2 1 MiB 制約 |
| **固定化ツール** | `python -m onnxruntime.tools.make_dynamic_shape_fixed --input_name <name> --input_shape ...` | ORT 公式 CLI、 CI に組込可能 |
| **HTP / CPU 分離** | encoder + DP + flow → **QNN HTP** (bucketed) / MB-iSTFT decoder (iSTFT/PQMF 含む) → **CPU fallback** | Whisper QIDK 公式パターン: "Encoder(Quantized-a16w8) fixed (1,80,3000) / Decoder variable as TFLite" |
| **量子化** | INT8 weights + INT16 activations (Hexagon NPU 推奨) | QNN HTP は quantized only |
| **Context binary** | `ep.context_enable=1` で per-bucket pre-compile | ORT EP-Context Design でロード時間最小化 |
| **7 ランタイム parity 観点** | HTP 経路は Python / C++ / C# / Rust の optional feature、 Go / WASM / Kotlin / Swift は CPU 維持 | contract 違反にならない (CoreML 経路は Swift で Kokoro 流 per-size 適用余地あり) |

**主要 1 次ソース:**

- [Qualcomm QIDK Whisper 公式](https://github.com/quic/qidk/blob/master/Solutions/NLPSolution3-AutomaticSpeechRecognition-Whisper/README.md) — encoder NPU + decoder CPU/TFLite の二分割パターン
- [ORT make_dynamic_shape_fixed](https://onnxruntime.ai/docs/tutorials/mobile/helpers/make-dynamic-shape-fixed.html) — bucket 化の公式 CLI
- [Kokoro-CoreML](https://github.com/mattmireles/kokoro-coreml) — TTS 専用の per-size export 実装 (32/64/128/256/320/384/512 tokens)
- [ExecuTorch QNN Llama](https://github.com/pytorch/executorch/blob/main/examples/models/llama/non_cpu_backends.md) — Static-Shape NPU + Dynamic-Shape CPU 分離パターン
- [Hexagon HTP architecture (arXiv 2509.23324)](https://arxiv.org/html/2509.23324v1) — TCM 8 MiB / 32-bit address space 制約

**残る不確定要素 (実機 PoC 必須):**

- piper-plus VITS の bucket 構成 (64/128/256/400 が optimal か) と Snapdragon 実機 latency
- HTP 32-bit address space 制約下で 4 bucket × 多入力 (phoneme_ids / speaker_id / prosody_features / speaker_embedding) の context binary 合計サイズ
- MB-iSTFT decoder の iSTFT/PQMF を Conv 実装で QNN HTP に乗せた場合の op-coverage 詳細 (Q20 と連動、 PoC 必須)

→ **Q17 はインフォメーションとしては converge、 残りは implementation detail で PoC 待ち**。 `docs/spec/ort-session-contract.toml` に QNN HTP bucket 仕様を追加すべき。

##### Q18. QAT (Quantization-Aware Training) の piper-plus 学習 pipeline 組込み — **IRREDUCIBLE**

- QNN HTP が quantized only のため、 A-1 を QNN 経路で最適化する場合は**学習時に QAT を入れる必要**がある。
- 既存の EMA / WavLM Discriminator / prosody_features (A1/A2/A3) / FP16 ONNX export / emb_lang 自動統一との相性は **実コードで検証必要**。
- 一般則: QAT は forward に fake quant op を挿入し勾配は STE で逆伝播、 EMA / Discriminator との二重訓練は数値不安定を起こしやすい。 piper-plus 規模 (508k 発話 / 6 言語) での実証データ皆無。
- **状態:** piper-plus 固有の training experiment が必須。 Phase 1 PoC (A-1 small-scale ablation) と同時並走で QAT 試験を組み込むのが効率的。

##### Q19. Dataset attribution の運用方法 — **IRREDUCIBLE**

- Q16 で CC-BY-4.0 → Apache-2.0 法的整合性は確定したため、 **piper-plus の HF model card と `/v1/models` API のメタデータ**に CML-TTS / 他データセット (LibriTTS-R / AISHELL-3 / MOE-Speech) の attribution を**機械可読形式**で含める仕様が必要。
- 候補スキーマ: Hugging Face model card YAML frontmatter (datasets フィールド)、 OpenMDW manifest format、 SPDX-License-Identifier 互換 metadata。
- **状態:** 統合レポート D-4 (HF model cards 整備 + voice marketplace 露出) と統合して進める具体的設計タスク。 実装着手で確定。

##### Q20. iSTFT 段の QNN 量子化精度 — **IRREDUCIBLE**

- Q15 で iSTFT 関連 op (STFT/IFFT/DFT/ComplexMul) は QNN 未サポートと判明したため、 piper-plus 既存の `stft_onnx.py` (Conv 実装で iSTFT を表現) パターンを QNN で動かす際に、 **Conv 実装の精度劣化** (INT8 weights + INT16 activations + Hexagon DSP 数値特性) が実用範囲か。
- 一般論: STFT を Conv で表現する場合、 Conv kernel が FFT basis (cosine / sine) を学習または固定値で持ち、 INT8 量子化で位相精度が劣化しやすい (聴感上ノイズ・キャラクタ歪み)。
- **状態:** Snapdragon 実機 PoC 必須 (Q17 と連動)。 失敗時は MB-iSTFT decoder 全体を CPU fallback に残し、 encoder+DP のみ QNN HTP に offload する Whisper QIDK パターンが現実解。

#### Phase 2-4 オープンクエスチョン総括 (Q10〜Q20 全 11 件)

| Q | Title | 分類 | 理由 |
|---|-------|------|------|
| Q10 | WebGPU EP の量子化対応 | **CONVERGED** | weight-only path (DequantizeLinear のみ) は確実、 full QDQ は CPU fallback |
| Q11 | NNAPI EP の長期サポート | **CONVERGED** | Android 15 で NDK NNAPI deprecated、 Snapdragon→QNN / その他→XNNPACK の移行戦略確定 |
| Q12 | iSTFTNet2 + VITS2 統合の MOS 劣化幅 (一般則) | **CONVERGED** | 一般則 0.2-0.5 MOS drop 確定、 FLY-TTS 並走候補確定 |
| Q13 | iSTFTNet2 specific end-to-end MOS | **IRREDUCIBLE** | Zero prior art、 1 言語 / 50 epoch PoC 必須 |
| Q14 | 量子化 Conv の WebGPU full QDQ 動作 | **IRREDUCIBLE** | ORT GitHub issues active dev、 weight-only 一択で実用化 |
| Q15 | QNN EP のオペレータ coverage | **RESOLVED** | Conv 1D/2D/3D + ConvTranspose + QuantizeLinear/DequantizeLinear all ✅ |
| Q16 | CC-BY-4.0 → Apache-2.0 派生関係 | **RESOLVED** | CC 公式 + Linux Foundation OpenMDW で compatible 確定 |
| Q17 | QNN HTP の dynamic shape 回避策 | **CONVERGED** | bucketed (3-4 段) + encoder/decoder 分離 hybrid 確定、 残り PoC |
| Q18 | QAT の piper-plus 学習 pipeline 組込み | **IRREDUCIBLE** | EMA / WavLM Discriminator / prosody_features 相性は実コード検証必要 |
| Q19 | Dataset attribution の運用方法 | **IRREDUCIBLE** | legal は Q16 で確定、 D-4 model cards との統合は実装タスク |
| Q20 | iSTFT 段の QNN 量子化精度 | **IRREDUCIBLE** | Snapdragon 実機 PoC 必須 (Q17 と連動) |

**集計:** RESOLVED 2 / CONVERGED 4 / IRREDUCIBLE 5 (計 11)。 統合レポート §G (9 件: R3/C3/I3) と合わせ、 **全 20 件 = R5/C7/I8** が両ドキュメントの最終分類状態。 文献調査による closure は完了、 残りはすべて piper-plus 固有の PoC / 実装タスクであり、 これ以上の web 調査は ROI 低い。 統合レポート [`improvement-survey-2026-06-15.md`](improvement-survey-2026-06-15.md) §G のオープンクエスチョン (G-A1〜G-D9) も同 workflow で分類済 (詳細は同レポート §G 参照)。

---

## 3. A-2: MS-Wavehax — streaming 専用の独立 vocoder

### 3.1 核心の差分: 「decoder 置換」ではなく「streaming 用 vocoder 追加」

| 観点 | 既存 MB-iSTFT-VITS | MS-Wavehax |
|------|-------------------|------------|
| **位置付け** | **TTS 統合 decoder** (acoustic model + vocoder 一体) | **独立 vocoder** (mel → waveform のみ) |
| **想定使用シーン** | 1 文単位の合成 (通常モード) | **sub-80ms チャンクの低レイテンシ streaming** |
| **params** | (decoder 全体) | **0.332M** = HiFi-GAN V1 の **2.4%** (極小) |
| **CPU 環境** | piper-plus canonical: Xeon E5-2650 v4 | **AMD EPYC 7302 シングルスレッド** で計測 |

### 3.2 競合 vocoder を凌駕する条件

論文の比較で **sub-80ms チャンク**条件で:

- HiFi-GAN を上回る
- iSTFTNet を上回る
- Vocos を上回る
- **MS-iSTFTNet (= 既存 piper-plus MB-iSTFT の直接対応物) を凌駕**

**重要な caveat:** 大きいチャンクでは 2D conv のデータ転送増で **Vocos が勝つ**。 → **優位性は低レイテンシ領域に限定**。 piper-plus の通常モード (1 文単位 ~ 数百ms) では MS-Wavehax の勝ちは保証されない。

### 3.3 ONNX 化リスクの低さ

論文の全比較 vocoder は torch.stft/istft を conv 実装に置換して ONNX 化:

> [from MS-Wavehax paper] All compared vocoders replace torch.stft/torch.istft with convolution-based implementations for ONNX export.

→ **piper-plus が `vits/stft_onnx.py:5` で既に使っている手法と同一**。 ONNX export の新規リスクは低い。

### 3.4 既存実装との関係: dual vocoder 構成

既存 MB-iSTFT-VITS は**通常モードで残す**。 streaming モード時のみ MS-Wavehax を呼び出す**デュアル vocoder 構成**:

```text
入力テキスト
   │
   ▼
[TextEncoder + DP + Flow + 中間表現 z]  ← acoustic model 部分 (共通)
   │
   ├─ 通常モード ──► [既存 MBiSTFTGenerator (1D CNN)] ──► waveform
   │
   └─ streaming モード ──► [新 MS-Wavehax vocoder] ──► waveform (sub-80ms チャンク)
```

`text_splitter.py` が文単位 streaming で yield する時のみ MS-Wavehax 経路を使う。

### 3.5 既存実装からの差分作業

| 作業項目 | 流用度 | 内容 |
|---------|-------|------|
| **既存 MBiSTFTGenerator** | 100% 流用 | 通常モードのまま温存 |
| **acoustic model (TextEncoder / DP / Flow)** | 100% 流用 | vocoder 前段はそのまま |
| **iSTFT 手法 (Conv 実装)** | 100% 流用 | `stft_onnx.py` のパターンを再利用 |
| **MS-Wavehax 本体** | **新規追加** | 0.332M params の独立 vocoder |
| **モード切替パス** | **新規設計** | `text_splitter.py` の streaming 経路で vocoder を分岐 |
| **学習** | **新規 vocoder のみ** | acoustic model は既存 6lang base を使い、 vocoder のみ MS-Wavehax で学習 |
| **7 ランタイム実装** | **追加実装** | 新 vocoder ノードを 7 ランタイムで動かす (incremental だが工数あり) |

→ **「既存実装は完全に温存、 streaming 専用 vocoder を併設」**。 既存ベンチマークへの回帰リスクは原理的にゼロ。

### 3.6 主要リスク

1. **適用領域の狭さ:** 優位性は **sub-80ms チャンクのみ**。 piper-plus の通常モード (1 文単位) では benefit が薄いか、 逆に悪化する可能性。
2. **dual vocoder の保守負荷:** 2 つの vocoder を維持するため、 ONNX export / 学習 / 7 ランタイム / 配布の各レイヤーで 2 系統管理が必要。
3. **モード切替の境界:** どこから「streaming」と判定するか、 ハイブリッドモード (短い文の streaming + 長い文の通常) の設計が必要。

---

## 4. A-1 vs A-2 — 並走戦略

### 4.1 競合ではなく補完関係

| 軸 | A-1 (iSTFTNet2-MB) | A-2 (MS-Wavehax) |
|----|---------------------|------------------|
| **置換 vs 併設** | 既存 backbone を**置換** | 既存と**併設** (streaming 専用) |
| **狙う改善** | 通常モード全般の CPU 高速化 + MOS↑ | 文単位 streaming のレイテンシ最小化 |
| **既存資産流用度** | 出力段 100% 流用 / backbone 書換 | ほぼ独立、 stft_onnx 手法のみ共通 |
| **互換性影響** | ONNX グラフ変化 (Conv2d 追加) | ONNX グラフ追加 (新 vocoder ノード) |
| **学習リソース** | 6lang base 全部再学習 | 新 vocoder のみ追加学習 |
| **mobile EP 適合性 (Phase 4)** | **QNN HTP / XNNPACK fully accelerated** (2D 化が機会、 Risk 1=低 確定) | **streaming 専用なので EP 影響中立** (デフォルト CPU EP で十分) |
| **ロールバック** | A-1 失敗時は **FLY-TTS に切替** (Phase 1 で並走検証済み) | A-2 失敗時は streaming で既存 vocoder を使う |

→ **両方並走可能**で、 互いをブロックしない。 Phase 4 deep-research 後の最新整理は §2.5 参照。

### 4.2 統合レポート (A 章) との位置付け

`improvement-survey-2026-06-15.md` の A 章では:

- **A-1 (iSTFTNet2-MB)** ★★★ — 最有力増分 (06-03 #1 由来、 既存資産の流用度が最も高い)
- **A-2 (MS-Wavehax)** ★★ — streaming 専用 (06-03 #3 由来、 適用領域が狭いが補強として有効)
- **A-4 (Matcha-TTS)** ★ / **A-5 (StyleTTS2)** ★ — decoder ファミリーごと刷新する high-ceiling 候補 (1 年スパン)

A-1 / A-2 は **「既存 MB-iSTFT-VITS の枠組みを保ったまま増築する低リスク路線」**、 A-4 / A-5 は **「decoder ファミリーを丸ごと刷新する high-risk / high-ceiling 路線」**。 同じ A 軸の中で**フェーズが違う**。

---

## 5. 推奨実装フェーズ (Phase 4 結果反映)

> **注記:** §2.5 Phase 4 deep-research の知見 (Risk 1 中→低 / Q15 QNN HTP fully accelerated / Q17 bucketing 戦略 / FLY-TTS 並走候補) を反映済。

### Phase 1 (短期 3-6 ヶ月、 v1.14〜v1.15)

**A-1 の PoC を 1 言語で先行:**

1. 既存 `mb_istft.py:MBiSTFTGenerator` の backbone を 1D-2D ハイブリッドに書き換えるブランチを作成
2. **設計制約 (Phase 4 知見反映):**
   - **ConvTranspose を上層 1-2 段に局所化** — NNAPI / CoreML NeuralNetwork で未サポートのため CPU fallback 範囲を最小化
   - **2D kernel size は 3x3〜3x5 に抑制** — im2col フットプリント増加を回避
   - **WebGPU は weight-only quantization 一択** — full QDQ は実運用 limited (Q14)
3. JA 単言語 (CSS10 JA データセット使用、 50 epoch) で **既存 vs iSTFTNet2-MB** の MOS / RTF / footprint を比較
4. ONNX export して 7 ランタイムで動作確認 (Conv2d op coverage チェック)
5. **FLY-TTS 並走 PoC (保険):** ConvNeXt × 6 + iSTFT (nfft=1024, hop=256) で同時測定、 MOS 4.12 ベースラインとの比較
6. 結果次第で 6lang base への適用 / dispatch

**A-2 は B-1〜B-3 (Mobile EP) 完了後に着手:**

- streaming モードは Mobile / Web で価値が高いため、 mobile EP 整備後の方が ROI が高い

### Phase 2 (中期 1 年、 v1.16+ または v2.0+ ※)

> ※ PR #537 (v2.0.0 候補、 Ready for review) merge 状況によりバージョン表記が v2.0.x にスライドする可能性あり。

**A-1 が成功:**

- 6lang base を iSTFTNet2-MB backbone で再学習 → v1.16.0 の主力 decoder
- A-2 を併設して streaming モード強化
- **QNN HTP 経路の Snapdragon 検証 (Q17 CONVERGED 戦略):** `make_dynamic_shape_fixed` で 4 bucket (64/128/256/400 phoneme) を pre-compile、 encoder NPU + MB-iSTFT decoder CPU の hybrid 構成 (Whisper QIDK パターン)

**A-1 が失敗 (例えば ConvTranspose2d の NNAPI / CoreML NN gap で CPU fallback が大量発生し RTF 退化):**

- 既存 MB-iSTFT-VITS を継続、 **FLY-TTS** を本命に昇格 (Phase 1 で並走検証済み)
- A-4 (Matcha-TTS) / A-5 (StyleTTS2) の中期プロトタイプに資源を移す
- A-2 は独立しているため A-1 の結果に関わらず併走可能

### Phase 3 (中期 1 年、 A-4/A-5 と統合判断)

- A-1 (採用) + A-4 (Matcha) + A-5 (StyleTTS2) の **3-way A/B** を 6 ヶ月走らせる
- 同一 6lang データセットで MOS / RTF / footprint / 多言語品質を測定
- 勝者を v1.17.x の次世代主力 decoder に昇格

---

## 6. オープンクエスチョン (Phase 1 初版 — §2.5 で Q10-Q20 に再採番済)

> [!IMPORTANT]
> **本節 #1〜#8 は Phase 1 初版の旧番号体系**で、 §2.5 で **Q10-Q20 に再採番した拡張版が canonical**。 統合レポート §G の参照は §2.5 と §2.5 末尾の「Phase 2-4 オープンクエスチョン総括表」を指す。 本節は履歴保存目的で残置。

### A-1 (iSTFTNet2-MB) 固有

1. **end-to-end VITS2 統合後の数値** → §2.5 **Q13** (IRREDUCIBLE、 1 言語 / 50 epoch PoC 必須、 FLY-TTS 保険確定)
2. **2D conv の ONNX op coverage** → §2.5 **Risk 1 で 中→低 に解決済** (XNNPACK / NNAPI は 2D 専用 = 機会、 残るのは ConvTranspose を上層局所化のみ)
3. **量子化 (B-4 / B-6) との相性** → §2.5 **Q14 / Q15 / Risk 1 で確定**: WebGPU は weight-only 一択、 QNN HTP は INT8w + INT16a で fully accelerated、 INT4 Conv はネイティブ未対応

### A-2 (MS-Wavehax) 固有 (依然 open)

1. **piper-plus 通常モードでの benefit 有無:** 論文の優位性は sub-80ms チャンク限定。 piper-plus の 1 文単位通常モード (~ 数百 ms) で MS-Wavehax を使った時に既存 MB-iSTFT より速くなる/品質が上がるか?
2. **モード切替の閾値:** 何文字 / 何 ms のしきい値で streaming と通常を切り替えるか、 ユーザ体感 A/B が必要。
3. **dual vocoder の配布 footprint:** 2 つの vocoder を含む配布パッケージサイズが INT8 (B-4) 適用後でも実用範囲に収まるか? (実装段階で A/B 測定)

### 両者共通

1. **WavLM Discriminator / EMA / prosody_features / emb_lang 自動統一の転移** → 統合レポート §G-C6 で **IRREDUCIBLE** 確定、 3 ヶ月 small-scale ablation 待ち。 A-4 / A-5 と同じ open question。
2. **多言語多話者でのベンチマーク:** 論文値は LJSpeech (単一話者・英語) 中心。 piper-plus の 6 言語多話者設定での品質差は未証明 — §G-A2 で **CONVERGED** (Matxa-TTS / Voicebox 等の多話者多言語 flow-matching 知見と統合)。

---

## 7. 関連ドキュメント

- **統合改善調査レポート:** [`improvement-survey-2026-06-15.md`](improvement-survey-2026-06-15.md) (A-1 / A-2 は §A、 並走戦略は §A の NOTE)
- **既存実装:**
  - `src/python/piper_train/vits/mb_istft.py` — `MBiSTFTGenerator` (現行 decoder)
  - `src/python/piper_train/vits/stft_onnx.py` — Conv ベース iSTFT
  - `docs/spec/audio-parity-contract.toml` — 7 ランタイム間音声 parity 規約
- **論文:**
  - [arXiv 2210.15975](https://arxiv.org/abs/2210.15975) Kawamura et al. "MB-iSTFT-VITS" (ICASSP 2023) — **既存実装の論文**
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) Kaneko et al. "iSTFTNet2" (Interspeech 2023, NTT) — **A-1 出典**
  - [arXiv 2506.03554](https://arxiv.org/html/2506.03554) Yoneyama et al. "MS-Wavehax" (Interspeech 2025) — **A-2 出典**
- **関連仕様:**
  - [`docs/spec/ort-session-contract.toml`](../spec/ort-session-contract.toml) — EP / opset 規約 (A-1 の Conv2d 検証ポイント、 §2.5 Q17 で **QNN HTP bucket 仕様 (3-4 段、 例 64/128/256/400 phoneme) の追記提言あり**)
  - [`docs/spec/text-splitter-contract.toml`](../spec/text-splitter-contract.toml) — streaming 分割規約 (A-2 のモード切替ポイント)
  - [`docs/spec/audio-parity-contract.toml`](../spec/audio-parity-contract.toml) — 7 ランタイム間音声 parity 規約

- **今後追記予定の項目 (Phase 4 提言):**
  - QNN HTP bucketed inference (encoder NPU + decoder CPU 分離、 `make_dynamic_shape_fixed` 経由の per-bucket pre-compile)
  - ConvTranspose 上層 1-2 段局所化制約 (NNAPI / CoreML NeuralNetwork の CPU fallback 範囲最小化)
  - WebGPU weight-only quantization 制約 (full QDQ は実運用 limited、 DequantizeLinear のみ確実)
