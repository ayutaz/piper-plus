# コールドスタート最適化 調査レポート

> **調査日:** 2026-04-02
> **背景:** piper-plus を Mobmate (Windows) に組み込む際、初回発話が ~2秒、2回目以降は ~100ms になるコールドスタート問題の原因特定と対策

---

## 1. 問題の概要

| 指標 | 初回発話 | 2回目以降 |
|------|---------|----------|
| レイテンシ | ~2,000ms | ~100ms |
| 原因 | モデル・辞書・ランタイムの初期化が全て初回に集中 | キャッシュ済みリソースの再利用のみ |

---

## 2. コールドスタート ~2秒の内訳

### 2.1 共通要因（全プラットフォーム）

| 処理 | 推定時間 | 原因 | 該当コード |
|------|---------|------|-----------|
| ONNX セッション初期化 + グラフ最適化 | ~1,000ms | モデル読み込み・パース・ノード融合・定数畳み込み・レイアウト変換 | Rust: `engine.rs:88-106`, C#: `SessionFactory.cs:67-103` |
| 日本語辞書ロード (jpreprocess/MeCab) | ~300ms | NAIST-JDIC バイナリインデックス構築 | Rust: `japanese.rs:343-384`, C#: `DotNetG2PEngine.cs:22-34` |
| 英語辞書ロード (CMU Dict) | ~200ms | JSON 15万エントリ → HashMap パース | Rust: `english.rs:549-641` |
| 中国語辞書ロード (Pinyin) | ~400ms | JSON 20万+エントリ → HashMap パース | Rust: `chinese.rs:773-840` |
| GPU デバイス検出 | ~100ms | CUDA/DirectML プロバイダ初期化 | Rust: `gpu.rs:122-149` |
| **合計** | **~2,000ms** | | |

### 2.2 Rust 固有

- 辞書は `OnceLock` でキャッシュ（CMU: `english.rs:549`, Pinyin: `chinese.rs:773`）
- jpreprocess は `PiperVoice` インスタンスに保持
- 多言語モデルの場合、`create_language_phonemizer()` で全言語の辞書を同時ロード（`voice.rs:110-154`）

### 2.3 C# 固有

- `DictionaryManager.EnsureDictionaryAsync()` を `GetAwaiter().GetResult()` で同期ブロック（`DotNetG2PEngine.cs:26`）
- `SessionFactory.cs:91` で `GraphOptimizationLevel = ORT_DISABLE_ALL` — グラフ最適化を完全に無効化
- .NET JIT (Tier 0) による初回メソッドコンパイルのオーバーヘッド

### 2.4 WASM 固有

- WASM バイナリ (63MB) の初回ロード: `piper_plus_wasm_bg.wasm`
- ONNX モデルのネットワーク取得 + IndexedDB キャッシュ
- `graphOptimizationLevel: 'extended'`（`webgpu-session-manager.js:35`）の初回コスト
- HuggingFace API への毎回問い合わせ（`model-manager.js:182`）

---

## 3. なぜ2回目以降は ~100ms なのか

| リソース | 初回 | 2回目以降 |
|---------|------|----------|
| ONNX セッション | 作成 + 最適化 | インスタンス再利用 |
| 日本語辞書 | ファイル読み込み + インデックス構築 | メモリ常駐 |
| 英語辞書 | JSON パース → HashMap | `OnceLock` キャッシュ |
| 中国語辞書 | JSON パース → HashMap | `OnceLock` キャッシュ |
| GPU プロバイダ | 検出 + 初期化 | 初期化済み再利用 |
| .NET JIT | Tier 0 コンパイル | ネイティブコード実行 |

2回目以降の内訳: テンソル構築 ~20ms + ONNX 推論 ~50-80ms + 出力処理 ~10ms

---

## 4. 対策一覧（効果が高い順）

### 4.1 Warmup（ダミー推論）

**効果: 最大 / 実装難度: 低**

アプリ起動時にバックグラウンドでダミーデータを1-3回推論実行。全キャッシュ・JIT最適化が完了し、ユーザーの初回発話が実質「2回目以降」扱いになる。

```rust
// Rust: engine.rs の load() 末尾、または CLI に --warmup オプション
let dummy_ids = ndarray::Array2::<i64>::from_shape_vec((1, 5), vec![1,2,3,4,5]).unwrap();
let dummy_lengths = ndarray::Array1::<i64>::from_vec(vec![5]);
for _ in 0..3 {
    let _ = session.run(ort::inputs![dummy_ids.view(), dummy_lengths.view()]?)?;
}
```

```csharp
// C#: SessionFactory.Create() の後
var dummyInput = new DenseTensor<long>(new long[] { 1, 2, 3, 4, 5 }, new int[] { 1, 5 });
for (int i = 0; i < 3; i++)
    session.Run(runOptions, inputs, outputNames);
```

**重要:** ダミー入力のテンソル形状は本番データと同程度にすること（異なる形状だと再最適化が走る）。

### 4.2 非同期バックグラウンド初期化

**効果: 大（体感） / 実装難度: 中**

セッション作成 + 辞書ロード + warmup をバックグラウンドスレッドで実行し、UI をブロックしない。

```csharp
// C# WinUI / WPF 向け
private Task<PiperSession>? _sessionTask;

public void InitializeAsync()
{
    _sessionTask = Task.Run(() =>
    {
        var session = SessionFactory.Create(modelPath);
        WarmUp(session, runs: 3);
        return new PiperSession(session);
    });
}

public async Task<byte[]> SynthesizeAsync(string text)
{
    var session = await _sessionTask!;
    return session.Synthesize(text);
}
```

```rust
// Rust: tokio::spawn_blocking
let engine = tokio::task::spawn_blocking(move || {
    let engine = OnnxEngine::load(&model_path, &config, "cpu")?;
    engine.warmup(3)?;
    Ok::<_, PiperError>(engine)
}).await??;
```

### 4.3 オフライングラフ最適化（事前最適化済みモデル配布）

**効果: 大 / 実装難度: 中**

`optimized_model_filepath` で最適化済みモデルを事前生成・配布し、ランタイムのグラフ最適化をスキップ。

```python
# ビルド時: 最適化実行 + 保存
import onnxruntime as ort
opts = ort.SessionOptions()
opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
opts.optimized_model_filepath = "model_optimized.onnx"
session = ort.InferenceSession("model.onnx", opts)
```

```csharp
// ランタイム: 最適化済みモデルを使用（最適化をスキップ）
var opts = new SessionOptions();
opts.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;  // スキップ可能
var session = new InferenceSession("model_optimized.onnx", opts);
```

**注意:** 最適化済みモデルは同じ Execution Provider・同じハードウェアで使う必要がある。

### 4.4 辞書のバイナリ形式化

**効果: 中〜大 / 実装難度: 中**

CMU Dict / Pinyin 辞書が現在 JSON 形式 → バイナリ（bincode / MessagePack 等）に事前変換すればパース時間を大幅削減。

| 辞書 | 現在 (JSON) | バイナリ化後 (推定) |
|------|------------|-------------------|
| CMU Dict (15万エントリ) | ~200ms | ~20-30ms |
| Pinyin (20万+エントリ) | ~400ms | ~30-50ms |

### 4.5 C# `GraphOptimizationLevel` 修正

**効果: 中 / 実装難度: 低**

現在 `SessionFactory.cs:91` で `ORT_DISABLE_ALL` に設定 → 事前最適化モデルを使わない場合は `ORT_ENABLE_ALL` に変更すべき。

### 4.6 SessionOptions チューニング

**効果: 中 / 実装難度: 低**

```csharp
// C# 推奨設定
var options = new SessionOptions();
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;
options.EnableMemoryPattern = true;
options.EnableCpuMemArena = true;
options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;

// Windows: スレッドスピニング有効化（レイテンシ優先）
options.AddSessionConfigEntry("session.intra_op.allow_spinning", "1");
options.AddSessionConfigEntry("session.inter_op.allow_spinning", "1");

// スレッド数を物理コア数に設定
options.IntraOpNumThreads = Environment.ProcessorCount / 2;
options.InterOpNumThreads = 1;
```

```rust
// Rust: ort crate
let session = Session::builder()?
    .with_optimization_level(ort::GraphOptimizationLevel::Level3)?
    .with_intra_threads(num_cpus::get_physical())?
    .with_inter_threads(1)?
    .commit_from_file(model_path)?;
```

### 4.7 DirectML 形状事前宣言（DirectML 使用時）

**効果: 中 / 実装難度: 低**

```csharp
// DirectML では必須
options.EnableMemoryPattern = false;
options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;

// 動的次元の固定
options.AddFreeDimensionOverrideByName("batch_size", 1);
options.AddFreeDimensionOverrideByName("phoneme_length", 200);
```

### 4.8 FP16 モデル

**効果: 中 / 実装難度: 済み**

piper-plus では `export_onnx.py` で FP16 変換がデフォルト有効。モデルサイズ ~50% 削減により、ファイル読み込み + メモリアロケーション時間を削減済み。

### 4.9 .NET ReadyToRun (R2R)

**効果: 小〜中 / 実装難度: 低**

```xml
<!-- PiperPlus.Cli.csproj -->
<PropertyGroup>
  <PublishReadyToRun>true</PublishReadyToRun>
</PropertyGroup>
```

JIT warmup コスト (~100-200ms) を AOT コンパイルで排除。

### 4.10 ORT 形式 (.ort) への事前変換

**効果: 小〜中 / 実装難度: 低**

```bash
python -m onnxruntime.tools.convert_onnx_models_to_ort model.onnx
# -> model.ort 生成（protobuf 解析オーバーヘッド排除）
```

デスクトップ環境では効果限定的（数十ms程度の改善）。モバイル/WASM 向けには有効。

---

## 5. Mobmate 組み込み時の推奨戦略

### ベストプラクティス: アプリ起動時プリロード + warmup

```
アプリ起動
  ├─ UI 表示（即座）
  └─ バックグラウンドスレッド
      ├─ (1) モデルファイル読み込み
      ├─ (2) ONNX セッション作成
      ├─ (3) 辞書ロード（使用言語のみ）
      ├─ (4) Warmup ダミー推論 x3
      └─ (5) Ready 状態に遷移
          ↓
  ユーザーの初回 TTS リクエスト → ~100ms で応答
```

### 言語別の遅延最適化

使用言語が事前にわかる場合、不要な辞書ロードをスキップ可能:

| 言語 | 辞書ロード時間 | 備考 |
|------|-------------|------|
| JA のみ | ~300ms | jpreprocess のみ |
| EN のみ | ~200ms | CMU Dict のみ |
| JA + EN | ~500ms | 両方ロード |
| 全言語 | ~900ms | JP + EN + ZH 辞書全て |
| ES/FR/PT/SV | ~0ms | 規則ベース（辞書不要） |

### 期待される改善効果

| 対策の組み合わせ | 初回発話レイテンシ | 備考 |
|----------------|------------------|------|
| 現状（何もしない） | ~2,000ms | |
| Warmup のみ | ~200ms | 起動後の待機時間は残る |
| バックグラウンド初期化 + Warmup | ~100ms* | *初期化完了後。完了前は ~2s |
| + 事前最適化モデル | ~100ms* | 初期化時間自体が ~1s に短縮 |
| + 辞書バイナリ化 | ~100ms* | 初期化時間が ~0.5s に短縮 |

---

## 6. 参考情報

- [ONNX Runtime Graph Optimizations](https://onnxruntime.ai/docs/performance/model-optimizations/graph-optimizations.html)
- [ONNX Runtime ORT Format Models](https://onnxruntime.ai/docs/performance/model-optimizations/ort-format-models.html)
- [ONNX Runtime Threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
- [DirectML Execution Provider](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html)
- [GitHub Issue #19177 - Why run first inference so slow](https://github.com/microsoft/onnxruntime/issues/19177)
- [I Cut My Model Inference Time from 2.3s to 87ms](https://markaicode.com/fixing-model-deployment-latency-onnx-runtime/)
