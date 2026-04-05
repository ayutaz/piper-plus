# CPU 推論速度最適化ガイド

> **調査日**: 2026-04-05
> **対象**: Windows / Linux / macOS の CPU 環境における ONNX 推論速度改善

---

## 目次

1. [現状のパフォーマンス](#現状のパフォーマンス)
2. [推論パイプラインとボトルネック分析](#推論パイプラインとボトルネック分析)
3. [発見された重大な問題](#発見された重大な問題)
4. [最適化提案 (優先度順)](#最適化提案-優先度順)
5. [各実装の最適化状況](#各実装の最適化状況)
6. [プラットフォーム別推奨設定](#プラットフォーム別推奨設定)
7. [ONNX Runtime 最適設定リファレンス](#onnx-runtime-最適設定リファレンス)
8. [VITSアーキテクチャレベルの高速化手法](#vitsアーキテクチャレベルの高速化手法)
9. [量子化に関する注意事項](#量子化に関する注意事項)
10. [音素化パフォーマンス](#音素化パフォーマンス)
11. [Execution Provider 比較](#execution-provider-比較)
12. [ベンチマーク方法](#ベンチマーク方法)
13. [参考資料](#参考資料)

---

## 現状のパフォーマンス

外部ベンチマーク (KittenTTS issue #40) による比較:

| モデル | RTF | モデルサイズ | 備考 |
|--------|-----|-------------|------|
| Matcha FP32 + Vocos | 0.163 | 71+52 MB | 2モデル構成 |
| **Piper FP16** | **0.192** | **38 MB** | 現在のデフォルト |
| Piper FP32 | 0.276 | 75 MB | |
| Piper INT8 | 0.523 | 22 MB | 逆効果 |
| KittenTTS FP16 | 0.693 | 23 MB | |
| Kokoro FP32 | 1.880 | 330 MB | |

> **RTF (Real-Time Factor)** = 推論時間 / 音声長。1.0 未満 = リアルタイムより高速。値が小さいほど良い。

現在の Piper Plus は RTF ~0.19 で、**リアルタイムの約 5 倍速**で合成可能。

---

## 推論パイプラインとボトルネック分析

### パイプライン全体

```
テキスト → [音素化] → [テンソル構築] → [ONNX推論] → [float→int16] → 音声出力
           10-150ms      0.5-5ms        50-500ms       0.1-1ms
```

### VITS 推論グラフの内部構造

```
phoneme_ids
    │
    ▼
TextEncoder (Transformer: Self-Attention + FFN × n_layers)
    │
    ├─→ m_p, logs_p (潜在分布の平均・分散)
    │
    ▼
StochasticDurationPredictor (Flow × 5段)
    │
    ├─→ duration per phoneme
    │
    ▼
Attention Path 生成 (phoneme → frame 拡張)
    │
    ▼
Flow (ResidualCouplingBlock × 4, reverse=True)
    │
    ▼
Generator / HiFi-GAN Decoder ← ★ 最大のボトルネック
    │
    ├─→ ConvTranspose1d × n_upsamples (段階的アップサンプリング)
    ├─→ ResBlock × num_kernels (各 upsample 後)
    │
    ▼
float32 audio [1, 1, samples]
```

### 各コンポーネントの推定コスト割合

| コンポーネント | 推定割合 | 計算量の特徴 |
|-------------|---------|------------|
| **Generator (HiFi-GAN)** | **60-70%** | ConvTranspose1d のアップサンプリングが支配的 |
| Flow (ResidualCoupling) | 15-20% | WaveNet 4段の拡張畳み込み |
| TextEncoder | 5-10% | Self-Attention O(T^2D) + FFN O(TD^2) |
| Duration Predictor | 3-5% | StochasticDurationPredictor (Flow逆流) |
| 音素化 (言語依存) | 5-15% | 日本語が最も重い (pyopenjtalk/jpreprocess) |

---

## 発見された重大な問題

### 知見 1: FP16 モデルは CPU でも有効

ベンチマーク結果:

| モデル | RTF | サイズ |
|--------|-----|--------|
| **Piper FP16** | **0.192** | 38 MB |
| Piper FP32 | 0.276 | 75 MB |

一般的に CPU EP は FP16 演算子の大半を未サポートで、内部で `FP16→FP32→FP16` キャストノードが自動挿入される。しかし **Piper の VITS モデルでは FP16 の方が約 30% 高速**。

これは以下の理由による:

1. **モデルサイズ半減** (75MB→38MB) によるメモリ帯域・CPU キャッシュ効率の大幅改善
2. VITS の推論はメモリバウンド寄り (大量の Conv1d 重み読み出し) のため、重みサイズ半減の効果がキャストオーバーヘッドを上回る
3. Piper の FP16 変換は **LayerNorm/Sigmoid/Softmax を FP32 で保持** (`convert_fp16.py:38-43`) しているため、数値的に敏感な演算でのキャストが最小限

> **注意**: 他のモデル/アーキテクチャでは FP16 が CPU で逆効果になる報告もある (ONNX Runtime Issue #25824)。Piper の小型 VITS モデルではメモリ帯域削減の効果が勝る。

**結論**: 現在の FP16 デフォルトエクスポートは CPU 推論でも正しい選択。変更不要。

### 問題 2: Python 推論スクリプトの最適化欠如

`src/python/piper_train/infer_onnx.py:288-299` で `SessionOptions()` がデフォルトのまま:

```python
# 現状 (最適化なし)
sess_options = onnxruntime.SessionOptions()
```

C# (`SessionFactory.cs`) と Rust (`engine.rs`) は全て最適化済みだが、**Python だけ未対応**:
- `intra_op_num_threads` 未設定 (全コア使用 → オーバーヘッド)
- `graph_optimization_level` 未設定
- `execution_mode` 未設定
- メモリ最適化 (`enable_cpu_mem_arena`, `enable_mem_pattern`) 未設定

### 問題 3: INT8 動的量子化は VITS に不適

VITS は CNN (Conv1d / ConvTranspose1d) 主体のアーキテクチャ。動的量子化の quantize/dequantize オーバーヘッドが推論時間を上回り、**FP16 比で 2.7 倍遅くなる** (RTF 0.523 vs 0.192)。

sherpa-onnx でも INT8 量子化 TTS モデルが FP32 の数百倍遅い報告あり (19-27s vs 0.05-0.08s)。

---

## 最適化提案 (優先度順)

### Tier 1: 即座に実装可能 (再学習不要)

| # | 施策 | 期待改善 | 対象 | 実装コスト |
|---|------|---------|------|----------|
| 1 | Python `infer_onnx.py` に ORT 最適化設定追加 | RTF 10-30% 改善 | Python | 数行 |
| 2 | Rust warmup 機能追加 (C# には実装済み) | 初回推論 500-800ms 短縮 | Rust | 低 |
| 3 | `session.dynamic_block_base=4` 追加 | レイテンシ分散低減 | 全実装 | 1行 |
| 4 | Rust/C++ にメモリアリーナ・パターン有効化 | RTF 5-15% 改善 | Rust/C++ | 数行 |

### Tier 2: 中期施策 (再学習不要、検証必要)

| # | 施策 | 期待改善 | 対象 | 実装コスト |
|---|------|---------|------|----------|
| 6 | CoreML EP ベンチマーク検証 | RTF 50-300% 改善の可能性 | macOS | 中 |
| 7 | OpenVINO EP 対応追加 | RTF 50-200% 改善の可能性 | Intel CPU | 中 |
| 8 | 静的 INT8 量子化 (選択的、calibration 付き) | RTF 30-80% 改善 | x86 VNNI | 高 |
| 9 | 音素化キャッシュ (特に日本語) | 音素化 50% 短縮 | 全実装 | 中 |
| 10 | ストリーミング推論改善 (文分割最適化) | TTFA 50-80% 短縮 | 全実装 | 中 |

### Tier 3: 長期施策 (再学習必要、最大効果)

| # | 施策 | 期待改善 | 実装コスト |
|---|------|---------|----------|
| 11 | **iSTFT デコーダ置換 (MB-iSTFT-VITS)** | **4-8x 高速化** | 高 (再学習) |
| 12 | **知識蒸留 (Nix-TTS 方式)** | **3-5x 高速化、モデル 80% 削減** | 高 (再学習) |
| 13 | **Vocos デコーダ統合** | **デコーダ部分 13x 高速化** | 非常に高 |
| 14 | Flow ステップ数削減 (4→2) | 1.5x 高速化 | 中 (再学習) |
| 15 | VITS2 アーキテクチャ移行 | 1.2x 高速化 + 品質向上 | 非常に高 |

---

## 各実装の最適化状況

### 実装間の設定比較

| 設定項目 | Rust | C# | C++ | Python |
|---------|------|-----|-----|--------|
| `ORT_ENABLE_ALL` | OK | OK | OK | **未設定** |
| `intra_threads=min(cores/2, 4)` | OK | OK | OK | **未設定** |
| `inter_threads=1` | OK | OK | - | **未設定** |
| `ORT_SEQUENTIAL` | OK | OK | - | **未設定** |
| 最適化モデルキャッシュ (.opt.onnx) | OK | OK | N/A | **未実装** |
| センチネルファイル (.ok) | OK | OK | N/A | **未実装** |
| Warmup 推論 (2回) | **未実装** | OK | **未実装** | **未実装** |
| メモリアリーナ (cpu_mem_arena) | **未設定** | **未設定** | OK | **未設定** |
| メモリパターン (mem_pattern) | **未設定** | **未設定** | - | **未設定** |
| GPU EP (CUDA/CoreML/DirectML) | OK | OK (CUDA) | OK | OK (CUDA) |

### Rust エンジンの現在の設定

`src/rust/piper-core/src/engine.rs`:

```rust
const MAX_INTRA_THREADS: usize = 4;  // VITS 小モデル向け上限

let num_intra_threads = std::thread::available_parallelism()
    .map(|n| n.get())
    .unwrap_or(2)
    .min(MAX_INTRA_THREADS);
// inter_threads = 1 (固定)
// GraphOptimizationLevel: 初回 ALL、キャッシュ後 Disable
```

### C# エンジンの現在の設定

`src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`:

```csharp
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;
options.IntraOpNumThreads = Math.Min(Environment.ProcessorCount / 2, 4);
options.InterOpNumThreads = 1;
options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;
// + 最適化モデルキャッシュ + センチネルファイル + Warmup (2回)
```

### C++ エンジンの現在の設定

`src/cpp/piper.cpp:412-520`:

```cpp
session.options.SetIntraOpNumThreads(numThreads);
session.options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
session.options.DisableProfiling();
// + CPU メモリアリーナ (デフォルト有効)
// + GPU EP: CUDA, CoreML, DirectML 対応
```

---

## プラットフォーム別推奨設定

### Windows (x86-64)

| 項目 | 推奨 |
|------|------|
| Execution Provider | CPU EP (標準) |
| モデル形式 | FP16 (デフォルト、CPU でも高速) |
| スレッド | `intra=min(cores/2, 4)`, `inter=1` |
| GPU がある場合 | DirectML EP (既に `--device directml` で利用可能) |
| 追加施策 | FP32 モデル + スレッド最適化 |

### Linux (x86-64)

| 項目 | 推奨 |
|------|------|
| Execution Provider | CPU EP / OpenVINO EP (Intel CPU) |
| モデル形式 | FP16 (デフォルト、CPU でも高速) |
| Intel VNNI 対応 CPU | 静的 INT8 量子化を検討 |
| サーバー環境 | `allow_spinning=0` で CPU 使用率削減 |
| NUMA 環境 | スレッドを単一 NUMA ノードにアフィニティ設定 (~20% 改善) |

### macOS (Apple Silicon)

| 項目 | 推奨 |
|------|------|
| Execution Provider | CoreML EP (要検証) → CPU EP (フォールバック) |
| モデル形式 | FP16 (CPU EP / CoreML EP 両方で有効) |
| CoreML 設定 | `MLComputeUnits=CPUAndNeuralEngine` |
| キャッシュ | `ModelCacheDirectory` 必須 (初回コンパイル回避) |
| スレッド | `intra=4` (P-core 数と一致) |

---

## ONNX Runtime 最適設定リファレンス

### Python (推奨設定)

```python
import os
import onnxruntime

sess_options = onnxruntime.SessionOptions()

# グラフ最適化: 最大レベル (定数畳み込み、演算子融合、レイアウト最適化)
sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

# メモリ最適化: 全有効 (速度優先)
sess_options.enable_cpu_mem_arena = True   # メモリ事前確保・再利用
sess_options.enable_mem_pattern = True     # 入力パターンに基づく一括確保
sess_options.enable_mem_reuse = True       # 中間テンソルのメモリ再利用

# 実行モード: Sequential (VITS は線形グラフ、並列サブグラフが少ない)
sess_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL

# スレッド: 物理コアの半分、最大4 (VITS 小モデル向け最適値)
sess_options.intra_op_num_threads = min(os.cpu_count() // 2 or 1, 4)
sess_options.inter_op_num_threads = 1

# レイテンシ分散低減
sess_options.add_session_config_entry("session.dynamic_block_base", "4")

# オフラインキャッシュ (2回目以降の起動高速化)
# sess_options.optimized_model_filepath = "model.opt.onnx"

session = onnxruntime.InferenceSession(
    "model.onnx",
    sess_options=sess_options,
    providers=["CPUExecutionProvider"],
)
```

### スレッド設定の根拠

| 設定 | 値 | 根拠 |
|------|-----|------|
| `intra_op_num_threads` | `min(物理コア/2, 4)` | VITS は 15-75MB の小モデル。4以上では同期オーバーヘッドが支配的 |
| `inter_op_num_threads` | `1` | VITS は線形グラフで並列サブグラフが少ない |
| `execution_mode` | `SEQUENTIAL` | 独立ノードが少ないため PARALLEL はオーバーヘッドのみ増加 |
| `allow_spinning` | `1` (デフォルト) | CLI/デスクトップ向け。サーバーでは `0` を検討 |

### メモリ最適化の効果

| 設定 | 効果 |
|------|------|
| `enable_cpu_mem_arena = True` | BFCArena でメモリを事前確保し再利用。推論速度 ~10-15% 向上 |
| `enable_mem_pattern = True` | 入力形状パターンに基づく一括メモリ確保。アロケーション回数削減 |
| `enable_mem_reuse = True` | 中間テンソルのメモリ再利用。常に有効にすべき |

---

## VITS アーキテクチャレベルの高速化手法

最大のボトルネックである HiFi-GAN デコーダの置換が、最も大きな速度改善をもたらす。

### 手法 A: MB-iSTFT-VITS (推奨)

HiFi-GAN の最後数段のアップサンプリングを iSTFT (逆短時間フーリエ変換) に置換。

| 項目 | 値 |
|------|-----|
| CPU RTF | 0.066 (VITS 0.271 から **4.1x 高速化**) |
| 音質 (MOS) | VITS と統計的に有意差なし |
| 参考実装 | [MasayaKawamura/MB-iSTFT-VITS](https://github.com/MasayaKawamura/MB-iSTFT-VITS) |

**Piper Plus への適用**: `vits/models.py` の `Generator` クラスを iSTFT ベースに置換。既存の学習パイプラインの `dec` を差し替えるだけで統合可能だが、再学習が必要。

### 手法 B: FLY-TTS (ConvNeXt + iSTFT)

HiFi-GAN 全体を ConvNeXt ブロック + iSTFT に置換。

| 項目 | 値 |
|------|-----|
| CPU RTF | 0.0139 (VITS 0.1221 から **8.8x 高速化**) |
| パラメータ | 17.89M (VITS 28.11M から 36.4% 削減) |
| 音質 (MOS) | 4.12 vs VITS 4.15 (ほぼ同等) |

### 手法 C: Vocos デコーダ

ConvNeXt + iSTFT の統一構造。アップサンプリング層なし。

| 項目 | 値 |
|------|-----|
| 速度 | HiFi-GAN 比 **13x 高速** |
| パラメータ | 13.5M |

### 手法 D: 知識蒸留 (Nix-TTS 方式)

Module-wise Distillation で大モデルから小モデルを蒸留。

| 項目 | 値 |
|------|-----|
| Teacher | VITS 29.08M → Student: Nix-TTS 5.23M (**89.34% 削減**) |
| Intel i7 CPU | **3.04x 高速化** |
| Raspberry Pi 3B | **8.36x 高速化** |
| 音質 (CMOS) | -0.27 (Teacher 比でわずかな低下) |

### 手法 E: アーキテクチャパラメータ削減

| 変更 | 改善 | 音質影響 |
|------|------|---------|
| Flow ステップ 4→2 | ~1.5x | 最小限 |
| Encoder レイヤー 6→3-4 | ~1.2x | 軽微 |
| Hidden channels 192→128 | ~1.3x (パラメータ 30% 削減) | 中程度 |

---

## 量子化に関する注意事項

### 動的 INT8 量子化: VITS には非推奨

VITS の CNN 主体アーキテクチャでは、動的量子化のオーバーヘッドが推論時間を上回る。

| 報告元 | 結果 |
|--------|------|
| KittenTTS benchmark | Piper INT8 RTF 0.523 vs FP16 RTF 0.192 (**2.7x 遅い**) |
| Coqui TTS Discussion #2991 | VITS 動的量子化が **2 倍以上遅くなった** |
| sherpa-onnx #575 | INT8 TTS が FP32 の **数百倍遅い** (19-27s vs 0.05-0.08s) |

### 静的 INT8 量子化: 条件付きで有効

静的量子化はキャリブレーションデータが必要だが、CNN モデルには動的より適切。

```python
from onnxruntime.quantization import quantize_static, CalibrationDataReader, QuantType

class PiperCalibrationReader(CalibrationDataReader):
    """キャリブレーション用データリーダー"""
    def __init__(self, calibration_data):
        self.data = calibration_data
        self.idx = 0

    def get_next(self):
        if self.idx >= len(self.data):
            return None
        result = self.data[self.idx]
        self.idx += 1
        return result

quantize_static(
    model_input="model_fp32.onnx",
    model_output="model_int8_static.onnx",
    calibration_data_reader=reader,
    quant_format=QuantFormat.QDQ,
    per_channel=True,           # 精度改善
    weight_type=QuantType.QInt8,
    activation_type=QuantType.QUInt8,
)
```

**注意**: Intel VNNI / AMX 対応 CPU で最大効果。古い CPU では逆効果の可能性あり。

### FP16 モデル: CPU でも有効 (Piper VITS の場合)

| 環境 | FP16 の効果 |
|------|-----------|
| GPU (CUDA/CoreML) | 有効 (FP16 カーネルが使われる、メモリ 50% 削減) |
| CPU (Piper VITS) | **有効** (メモリ帯域削減がキャストオーバーヘッドを上回る。RTF 0.192 vs FP32 0.276) |
| CPU (大規模モデル) | モデル依存 (キャストオーバーヘッドが支配的になる場合あり) |

---

## 音素化パフォーマンス

### 言語別推定処理時間 (短文 <100 文字)

| 言語 | Python | Rust | C# | ボトルネック |
|------|--------|------|-----|------------|
| **日本語** | 50-150ms | 20-80ms | 30-100ms | pyopenjtalk/jpreprocess フルコンテキスト生成 |
| **英語** | 5-30ms (初回 +100-500ms) | 3-15ms | 5-20ms | G2p 初期化 (キャッシュ後は軽量) |
| **中国語** | 30-100ms (最適化パス: 2-5ms) | 15-50ms | - | pypinyin 辞書参照 |
| **韓国語** | 10-30ms | - | - | g2pk2 音韻規則 |
| **ES/FR/PT/SV** | 3-8ms | 3-8ms | 3-8ms | 規則ベース (軽量) |

### 多言語テキスト処理例

```
テキスト: "こんにちは Hello 世界"
処理フロー:
1. SegmentText()  → [("ja","こんにちは"), ("en"," Hello "), ("ja","世界")]  [1-2ms]
2. 言語別音素化:
   - JA: 50-80ms
   - EN: 5-10ms (キャッシュ後)
   - JA: 30-50ms
3. トークンマッピング: 0.5-1ms
4. プロソディ処理: 2-5ms
合計: ~90-150ms
```

### 音素化の最適化案

1. **日本語キャッシュ**: 形態素解析結果のメモ化 → 20-30% 改善
2. **中国語高速パス**: 事前計算ピンイン利用時は `phonemize_from_pinyin_syllables()` → 29x 高速
3. **Rust 実装への移行**: 平均 50% の処理時間削減

---

## Execution Provider 比較

### CPU 向け EP 一覧

| EP | 対象 | VITS での効果 | 注意点 |
|----|------|-------------|--------|
| **CPU EP (デフォルト)** | 全プラットフォーム | 基準値 | 安定、追加依存なし。**推奨** |
| **OpenVINO EP** | Intel CPU | 0.8-1.5x (モデル依存) | 小モデルでは逆効果の可能性あり。要ベンチマーク |
| **CoreML EP** | macOS (Apple Silicon) | 1.5-4x (Neural Engine 活用時) | 動的形状でペナルティ。`ModelCacheDirectory` 必須 |
| **XNNPACK EP** | ARM (Android/iOS) | 1.2-2x | モバイル向け。現在の Piper Plus では優先度低 |
| **ACL EP** | ARM サーバー (Graviton) | 1.1-1.2x | サーバーサイド ARM 環境向け |

### Piper Plus での実装状況

| EP | Rust | C# | C++ | Python |
|----|------|-----|-----|--------|
| CPU | OK | OK | OK | OK |
| CUDA | OK | OK | OK | OK |
| CoreML | OK | N/A | OK | N/A |
| DirectML | OK | OK | OK | N/A |
| TensorRT | OK | N/A | N/A | N/A |
| OpenVINO | **未実装** | **未実装** | **未実装** | **未実装** |

### SIMD 自動活用状況

ONNX Runtime の MLAS ライブラリが実行時に CPUID 検出を行い、最適カーネルを自動選択。追加設定不要。

| 命令セット | 対象 | 自動検出 |
|-----------|------|---------|
| AVX2 | x86-64 Haswell 以降 | はい |
| AVX-512 | Skylake-X, Ice Lake, Zen 4+ | はい |
| AVX-VNNI | Alder Lake+, Zen 5+ | はい (INT8 量子化時に効果) |
| NEON | ARM v8+ (全 Apple Silicon) | はい |
| ARM DOT | ARM v8.2+ | はい (INT8 量子化時に効果) |

---

## ベンチマーク方法

### Python (benchmark_onnx.py)

```bash
# JSONL 形式の入力を使用
cat utterances.jsonl | python src/benchmark/benchmark_onnx.py \
    -m model.onnx \
    -c config.json

# 出力例 (JSON)
# {"load_sec": 0.5, "rtf_mean": 0.15, "rtf_stdev": 0.02, "rtfs": [0.14, 0.15, ...]}
```

### Rust CLI

```bash
# RTF はログに自動出力される
piper-plus --model model.onnx --text "テスト文"

# バッチ処理の RTF 集計
echo "テスト文1\nテスト文2" | piper-plus --model model.onnx --output-dir ./out
```

### パフォーマンステスト (pytest)

```bash
# benchmark マーカー付きテストを実行
uv run pytest tests/ -v -m "benchmark"
```

---

## 参考資料

### ONNX Runtime 公式ドキュメント

- [Threading Management](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
- [Graph Optimizations](https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html)
- [Quantization](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
- [Memory Optimization](https://onnxruntime.ai/docs/performance/tune-performance/memory.html)
- [Float16 and Mixed Precision](https://onnxruntime.ai/docs/performance/model-optimizations/float16.html)

### TTS 高速化に関する論文・リポジトリ

- [MB-iSTFT-VITS](https://github.com/MasayaKawamura/MB-iSTFT-VITS) - iSTFT ベース高速 VITS
- [FLY-TTS](https://arxiv.org/html/2407.00753v1) - ConvNeXt + iSTFT で 8.8x 高速化
- [Nix-TTS](https://ar5iv.labs.arxiv.org/html/2203.15643) - Module-wise 知識蒸留
- [Vocos](https://arxiv.org/html/2306.00814v3) - iSTFT ベース vocoder
- [VITS2](https://arxiv.org/abs/2307.16430) - 改良版 VITS
- [Paroli](https://github.com/marty1885/paroli) - ストリーミング Piper (C++)

### ベンチマーク・コミュニティ

- [CPU speed comparison (KittenTTS #40)](https://github.com/KittenML/KittenTTS/issues/40)
- [Optimizing TTS for CPU Inference Part 1](https://medium.com/@mllopart.bsc/optimizing-a-multi-speaker-tts-model-for-faster-cpu-inference-part-1-165908627829)
- [Optimizing TTS for CPU Inference Part 2](https://medium.com/@mllopart.bsc/optimizing-a-multi-speaker-tts-model-for-faster-cpu-inference-part-2-fa9fc48d9635)
- [ONNX Runtime FP16 CPU Issue #25824](https://github.com/microsoft/onnxruntime/issues/25824)
- [VITS Quantization Issues (Coqui TTS #2991)](https://github.com/coqui-ai/TTS/discussions/2991)
