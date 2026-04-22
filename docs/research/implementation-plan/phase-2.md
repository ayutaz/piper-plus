# Phase 2 実装計画: ONNX エクスポート + 5 ランタイム対応

**Phase 2 工数**: 2 週間 (並列化で 4〜5 日に短縮可能)
**依存**: Phase 1 完了 (Style vector conditioning 学習側統合)
**後続**: Phase 5 (fine-tune 実験で ONNX 動作確認が必要)

---

## 2.1 本家の speaker_embedding マスクパターン分析

### 2.1.1 ONNX エクスポート時 (export_onnx.py)

`speaker_embedding` は以下の方式で ONNX 入力に組み込まれている:

```python
# src/python/piper_train/export_onnx.py:495-514 付近
speaker_emb_dim = 256  # ECAPA-TDNN デフォルト
dummy_speaker_embedding = torch.zeros(1, speaker_emb_dim, dtype=torch.float32)
dummy_speaker_embedding_mask = torch.ones(1, 1, dtype=torch.int64)

# 常に入力に追加 (optional ではない、ランタイムで mask で制御)
dummy_input_list.append(dummy_speaker_embedding)
input_names.append("speaker_embedding")
dynamic_axes["speaker_embedding"] = {0: "batch_size"}

dummy_input_list.append(dummy_speaker_embedding_mask)
input_names.append("speaker_embedding_mask")
dynamic_axes["speaker_embedding_mask"] = {0: "batch_size"}
```

**重要点**:
- `speaker_embedding` と `speaker_embedding_mask` は **常に ONNX グラフに含まれる** (optional ではない)
- `speaker_embedding_mask` が **条件フラグ**: mask=0 → speaker_id 使用、mask=1 → embedding 使用
- モデル側で mask 値による制御フロー分岐は不要。ランタイムが mask を作成・渡す

### 2.1.2 ランタイム側処理パターン

**Python (infer_onnx.py)**:
```python
if has_spk_emb:
    if spk_emb_array is not None:
        inputs["speaker_embedding"] = spk_emb_array
        inputs["speaker_embedding_mask"] = np.array([[1]], dtype=np.int64)
    else:
        inputs["speaker_embedding"] = np.zeros((1, emb_dim), dtype=np.float32)
        inputs["speaker_embedding_mask"] = np.array([[0]], dtype=np.int64)
```

**C++ (piper_plus_c_api.cpp)**:
```cpp
if (effectiveOpts.speaker_embedding && effectiveOpts.speaker_embedding_dim > 0) {
    synthConfig.speakerEmbedding.assign(
        effectiveOpts.speaker_embedding,
        effectiveOpts.speaker_embedding + effectiveOpts.speaker_embedding_dim);
} else {
    synthConfig.speakerEmbedding.clear();
}
```

**Rust (piper-core/src/engine.rs)**:
```rust
let speaker_emb_tensor = if self.capabilities.has_speaker_embedding {
    if let Some(ref emb) = request.speaker_embedding {
        create_tensor([1, emb.len()], emb)
    } else {
        create_tensor([1, 256], &vec![0.0; 256])
    }
} else {
    None
};
```

---

## 2.2 ONNX エクスポート設計

### 2.2.1 入力シグネチャ案 (採用)

**案A (推奨)**: `style_vector` を独立した optional 入力として追加

```
既存入力: input, input_lengths, scales, sid, lid, prosody_features,
          speaker_embedding, speaker_embedding_mask

新規入力: style_vector, style_vector_mask
  - style_vector: [batch, style_vector_dim] float32
  - style_vector_mask: [batch, 1] int64  (0 = disabled/zeros, 1 = enabled)
```

**利点**:
- `speaker_embedding` と同じマスクパターンで統一
- ONNX メタデータに `style_vector_dim` を埋め込み、既存モデル (dim=0) との互換性確保
- ランタイムが metadata を読んで入力の有無を判定可能

### 2.2.2 dynamic_axes 設定

```python
dynamic_axes = {
    # 既存
    "speaker_embedding": {0: "batch_size"},
    "speaker_embedding_mask": {0: "batch_size"},
    # 新規
    "style_vector": {0: "batch_size"},
    "style_vector_mask": {0: "batch_size"},
}
```

### 2.2.3 metadata への style_vector_dim 埋め込み

```python
import onnx
model = onnx.load(str(args.output))
model.metadata_props.extend([
    onnx.helper.make_attribute_proto("style_vector_dim", str(style_vector_dim)),
    onnx.helper.make_attribute_proto(
        "style_condition_mode",
        getattr(model_g, "style_condition_mode", "global")
    ),
])
onnx.save(model, str(args.output))
```

**フォールバック**: ONNX metadata 読み込みに失敗した場合、`config.json` の `style_vector_dim` をランタイム側で参照。

### 2.2.4 export_onnx.py への patch (概要)

**追加位置**: `torch.onnx.export()` 呼び出し直前

```python
# Style vector inputs (新規追加)
style_vector_dim = getattr(model_g, "style_vector_dim", 0)
if style_vector_dim > 0:
    dummy_style_vector = torch.zeros(1, style_vector_dim, dtype=torch.float32)
    dummy_style_vector_mask = torch.ones(1, 1, dtype=torch.int64)

    dummy_input_list.append(dummy_style_vector)
    input_names.append("style_vector")
    dynamic_axes["style_vector"] = {0: "batch_size"}

    dummy_input_list.append(dummy_style_vector_mask)
    input_names.append("style_vector_mask")
    dynamic_axes["style_vector_mask"] = {0: "batch_size"}

    _LOGGER.info(
        "Exporting model with style_vector support (dim=%d, mode=%s)",
        style_vector_dim,
        getattr(model_g, "style_condition_mode", "global"),
    )

# torch.onnx.export() 実行後、メタデータを付与
if style_vector_dim > 0:
    import onnx
    model = onnx.load(str(args.output))
    model.metadata_props.extend([
        onnx.helper.make_attribute_proto("style_vector_dim", str(style_vector_dim)),
        onnx.helper.make_attribute_proto(
            "style_condition_mode",
            getattr(model_g, "style_condition_mode", "global")
        ),
    ])
    onnx.save(model, str(args.output))
```

**行数**: +60 行程度

---

## 2.3 ランタイム別実装計画

### 2.3.1 Python (infer_onnx.py)

**追加行数**: 約 40 行

```python
# モデル capability 検出 (既存パターン)
has_style_vector = "style_vector" in input_names

# Inputs 構築
if has_style_vector:
    style_vector_dim = config.get("style_vector_dim", 0)
    if args.style_vector and style_vector_dim > 0:
        style_vec = np.load(args.style_vector).astype(np.float32)
        if style_vec.ndim == 1:
            style_vec = style_vec.reshape(1, -1)
        inputs["style_vector"] = style_vec
        inputs["style_vector_mask"] = np.array([[1]], dtype=np.int64)
    else:
        inputs["style_vector"] = np.zeros((1, style_vector_dim), dtype=np.float32)
        inputs["style_vector_mask"] = np.array([[0]], dtype=np.int64)

# CLI オプション追加
parser.add_argument(
    "--style-vector",
    default=None,
    metavar="PATH",
    help="Path to a .npy file containing style_vector",
)
```

**後方互換性**: `config.json` に `style_vector_dim` がない場合は `0` 既定 → `style_vector` 入力は構築されず、既存モデルのまま動作。

### 2.3.2 C++ (piper_plus.h, piper_plus_c_api.cpp)

**追加行数**: 約 50 行

**piper_plus.h の変更**:

```c
typedef struct PiperPlusSynthOptions {
    int32_t speaker_id;
    int32_t language_id;
    float   noise_scale;
    float   length_scale;
    float   noise_w;
    float   sentence_silence_sec;
    const float *speaker_embedding;
    int32_t      speaker_embedding_dim;

    // 新規フィールド
    const float *style_vector;
    int32_t      style_vector_dim;

    int32_t _reserved[3];  // ABI safe (既存 _reserved[5] → [3])
} PiperPlusSynthOptions;
```

**piper_plus_c_api.cpp の変更**:

```cpp
// piper_plus_default_options() で初期化
opts.style_vector = NULL;
opts.style_vector_dim = 0;

// piper_plus_synthesize() 内で処理
if (effectiveOpts.style_vector && effectiveOpts.style_vector_dim > 0) {
    synthConfig.styleVector.assign(
        effectiveOpts.style_vector,
        effectiveOpts.style_vector + effectiveOpts.style_vector_dim);
} else {
    synthConfig.styleVector.clear();
}
```

**piper.hpp の変更**:

```cpp
struct SynthesisConfig {
    // 既存
    std::vector<float> speakerEmbedding;
    // 新規
    std::vector<float> styleVector;
};
```

**synthesize() 内でテンソル化** (speaker_embedding と同じ処理パターン):

```cpp
if (!config.styleVector.empty()) {
    inputTensors.push_back(create_tensor(config.styleVector, {1, config.styleVector.size()}));
    int64_t maskValue = 1;
    inputTensors.push_back(create_tensor(&maskValue, {1, 1}));
} else {
    std::vector<float> zeros(config.styleVectorDim, 0.0f);
    inputTensors.push_back(create_tensor(zeros, {1, config.styleVectorDim}));
    int64_t maskValue = 0;
    inputTensors.push_back(create_tensor(&maskValue, {1, 1}));
}
```

### 2.3.3 Rust (piper-core)

**追加行数**: 約 45 行

```rust
// src/rust/piper-core/src/engine.rs
pub struct SynthesisRequestData {
    // 既存フィールド
    pub speaker_embedding: Option<Vec<f32>>,
    // 新規
    pub style_vector: Option<Vec<f32>>,
}

impl Default for SynthesisRequestData {
    fn default() -> Self {
        Self {
            speaker_embedding: None,
            style_vector: None,  // 新規
        }
    }
}

pub struct ModelCapabilities {
    pub has_speaker_embedding: bool,
    // 新規
    pub has_style_vector: bool,
    pub style_vector_dim: u32,
}

// synthesize() 内
let style_vector_tensor = if self.capabilities.has_style_vector {
    if let Some(ref vec) = request.style_vector {
        create_tensor([1, vec.len()], vec)?
    } else {
        let zeros = vec![0.0; self.capabilities.style_vector_dim as usize];
        create_tensor([1, self.capabilities.style_vector_dim as usize], &zeros)?
    }
} else {
    None
};

if let Some(t) = style_vector_tensor {
    input_tensors.push(t);
    let mask = if request.style_vector.is_some() { 1i64 } else { 0i64 };
    input_tensors.push(create_tensor([1, 1], &[mask])?);
}
```

**piper-cli への追加**:

```rust
#[arg(long, value_name = "PATH")]
style_vector: Option<PathBuf>,

// CLI 処理内
if let Some(style_path) = args.style_vector {
    let style_vec = load_f32_vec_from_npy(&style_path)?;
    request.style_vector = Some(style_vec);
}
```

### 2.3.4 C# (PiperPlus.Core + PiperPlus.Cli)

**追加行数**: 約 50 行

```csharp
// SynthesisRequest
public float[]? StyleVector { get; set; }

// ModelCapabilities
public bool HasStyleVector { get; set; }
public int StyleVectorDim { get; set; }

// Synthesize() 内
if (HasStyleVector && StyleVectorDim > 0)
{
    if (request.StyleVector != null && request.StyleVector.Length == StyleVectorDim)
    {
        inputs["style_vector"] = OrtValue.CreateTensorValueFromMemory(
            request.StyleVector,
            new long[] { 1, StyleVectorDim });
        inputs["style_vector_mask"] = OrtValue.CreateTensorValueFromMemory(
            new long[] { 1 },
            new long[] { 1, 1 });
    }
    else
    {
        var zeros = new float[StyleVectorDim];
        inputs["style_vector"] = OrtValue.CreateTensorValueFromMemory(zeros, new long[] { 1, StyleVectorDim });
        inputs["style_vector_mask"] = OrtValue.CreateTensorValueFromMemory(new long[] { 0 }, new long[] { 1, 1 });
    }
}
```

**CLI**:
```csharp
{ "style-vector=", "Path to style_vector .npy file",
  v => request.StyleVector = NumpyLoader.LoadFloat32Array(v) },
```

### 2.3.5 Go (piperplus)

**追加行数**: 約 40 行

```go
type SynthesisRequest struct {
    // 既存フィールド
    SpeakerEmbedding []float32
    // 新規
    StyleVector []float32
}

type ModelCapabilities struct {
    HasSpeakerEmbedding bool
    // 新規
    HasStyleVector bool
    StyleVectorDim int32
}

// Synthesize() 内
if engine.capabilities.HasStyleVector {
    if len(request.StyleVector) == int(engine.capabilities.StyleVectorDim) {
        inputs["style_vector"] = ort.NewTensor(
            []int64{1, int64(engine.capabilities.StyleVectorDim)}, request.StyleVector)
        inputs["style_vector_mask"] = ort.NewTensor([]int64{1, 1}, []int64{1})
    } else {
        zeros := make([]float32, engine.capabilities.StyleVectorDim)
        inputs["style_vector"] = ort.NewTensor(
            []int64{1, int64(engine.capabilities.StyleVectorDim)}, zeros)
        inputs["style_vector_mask"] = ort.NewTensor([]int64{1, 1}, []int64{0})
    }
}
```

**CLI**:
```go
styleVectorPath := flag.String("style-vector", "", "Path to style_vector .npy file")

if *styleVectorPath != "" {
    styleVec, err := loadFloat32Npy(*styleVectorPath)
    if err != nil {
        log.Fatalf("Failed to load style_vector: %v", err)
    }
    request.StyleVector = styleVec
}
```

### 2.3.6 WASM/JS (piper-wasm + npm)

**追加行数**: 約 55 行

**Rust (piper-wasm/lib.rs)**:
```rust
#[wasm_bindgen]
pub struct SynthesizeOptions {
    speaker_embedding: Option<Vec<f32>>,
    style_vector: Option<Vec<f32>>,  // 新規
}

#[wasm_bindgen]
impl SynthesizeOptions {
    #[wasm_bindgen(getter)]
    pub fn style_vector(&self) -> Option<Vec<f32>> {
        self.style_vector.clone()
    }

    #[wasm_bindgen(setter)]
    pub fn set_style_vector(&mut self, vec: Vec<f32>) {
        self.style_vector = Some(vec);
    }
}
```

**TypeScript (types/index.d.ts)**:
```typescript
export interface SynthesizeOptions {
    speakerId?: number;
    languageId?: number;
    noiseScale?: number;
    lengthScale?: number;
    noiseW?: number;
    speakerEmbedding?: Float32Array;
    styleVector?: Float32Array;  // 新規
}

export async function synthesize(
    text: string,
    options?: SynthesizeOptions
): Promise<AudioBuffer>;
```

**JS 実装**:
```typescript
const opts = WasmSynthesizeOptions.new();
if (options?.styleVector) {
    opts.set_style_vector(Array.from(options.styleVector));
}
```

---

## 2.4 後方互換性戦略

### 2.4.1 既存 ONNX モデル (style_vector_dim=0) の扱い

| シナリオ | 動作 |
|--------|-----|
| Metadata なし (Phase 1 以前モデル) | ONNX グラフに `style_vector` 入力なし → ランタイムは `has_style_vector=false` で検出、入力構築スキップ |
| `style_vector_dim=0` metadata | ランタイムが 0 を検出、`has_style_vector=false` として扱う |
| `style_vector_dim>0` (新モデル) | `has_style_vector=true`、入力構築 |

### 2.4.2 既存ユーザーコードの扱い

| 言語 | 後方互換性 |
|-----|----------|
| C | `PiperPlusSynthOptions opts = {0}; ...` で style_vector=NULL 自動、既存コード動作 |
| Python | `--style-vector` は optional、既存スクリプト動作 |
| Rust/Go/C#/JS | `style_vector: None/null` がデフォルト、既存コード動作 |

---

## 2.5 テスト計画

### 2.5.1 既存テストへの影響

- `tests/test_export_onnx.py`: dim=0 モデルで既存テスト通過確認、dim>0 モデルで新規テスト追加
- `tests/test_infer_onnx.py`: `--style-vector` なし動作、あり動作の両方
- 各ランタイムの既存テスト: `SynthesisRequest.style_vector=None` で動作継続確認

### 2.5.2 追加テスト (各ランタイム)

**ONNX エクスポート** (`tests/test_export_onnx.py`):

```python
def test_export_with_style_vector_dim_0():
    model = create_test_model(style_vector_dim=0)
    onnx_path = export_onnx(model)
    session = ort.InferenceSession(onnx_path)
    input_names = [inp.name for inp in session.get_inputs()]
    assert "style_vector" not in input_names

def test_export_with_style_vector_dim_256():
    model = create_test_model(style_vector_dim=256)
    onnx_path = export_onnx(model)
    session = ort.InferenceSession(onnx_path)
    input_names = [inp.name for inp in session.get_inputs()]
    assert "style_vector" in input_names
    assert "style_vector_mask" in input_names

    # metadata 確認
    model_onnx = onnx.load(onnx_path)
    metadata = {mp.key: mp.value for mp in model_onnx.metadata_props}
    assert metadata.get("style_vector_dim") == "256"
```

**Python 推論** (`tests/test_infer_onnx.py`):
```python
def test_infer_without_style_vector():
    result = infer_onnx(model, text="Hello", style_vector=None)
    assert result.audio.size > 0

def test_infer_with_style_vector():
    style_vec = np.random.randn(256).astype(np.float32)
    result = infer_onnx(model, text="Hello", style_vector=style_vec)
    assert result.audio.size > 0
```

**C++ テスト** (`src/cpp/tests/test_style_vector.cpp`):
```cpp
TEST(PiperPlusStyleVector, NoStyleVector) {
    auto opts = piper_plus_default_options();
    // style_vector=NULL, dim=0 で動作確認
}

TEST(PiperPlusStyleVector, WithStyleVector) {
    auto opts = piper_plus_default_options();
    float style_vec[256] = { /* ... */ };
    opts.style_vector = style_vec;
    opts.style_vector_dim = 256;
    // synthesize 実行・検証
}
```

---

## 2.6 工数内訳

| タスク | 工数 |
|-------|-----|
| ONNX エクスポート (export_onnx.py + テスト) | 1.5 日 |
| Python (infer_onnx.py + テスト) | 1 日 |
| C++ (piper_plus.h, piper_plus_c_api.cpp + テスト) | 2 日 |
| Rust (piper-core + CLI + テスト) | 1.5 日 |
| C# (PiperPlus.Core + CLI + テスト) | 1.5 日 |
| Go (piperplus + CLI + テスト) | 1.5 日 |
| WASM/JS (piper-wasm + npm + テスト) | 1.5 日 |
| 統合テスト + 互換性確認 | 1 日 |
| ドキュメント (CLAUDE.md 更新等) | 1 日 |
| **合計** | **~14 日 (2 週間)** |

**並列化**: Python/C++/Rust/C#/Go/WASM は独立作業のため、3〜4 人チームなら 4〜5 日に短縮可能。

---

## 2.7 分割 PR 案

| PR | タイトル | ファイル | 工数 |
|----|--------|---------|-----|
| PR-C | `feat(export): style_vector を ONNX 入力に追加 (mask パターン)` | `export_onnx.py`, `test_export_onnx.py` | 1.5 日 |
| PR-D-Py | `feat(infer): Python ONNX 推論で style_vector サポート` | `infer_onnx.py`, `test_infer_onnx.py` | 1 日 |
| PR-D-Cpp | `feat(runtime): C++ API に style_vector サポート追加` | `piper_plus.h`, `piper_plus_c_api.cpp`, `piper.hpp`, テスト | 2 日 |
| PR-D-Rust | `feat(rust): piper-core と CLI に style_vector 追加` | `engine.rs`, `main.rs`, テスト | 1.5 日 |
| PR-D-CSharp | `feat(csharp): PiperPlus.Core と CLI に style_vector 追加` | `PiperPlusEngine.cs`, `Program.cs`, テスト | 1.5 日 |
| PR-D-Go | `feat(go): Go エンジンに style_vector サポート追加` | `engine.go`, `main.go`, テスト | 1.5 日 |
| PR-D-Wasm | `feat(wasm): JS/WASM API で style_vector エクスポート` | `piper-wasm/lib.rs`, `index.d.ts`, テスト | 1.5 日 |
| PR-D-Docs | `docs(phase2): style_vector 実装ガイド` | CLAUDE.md, README.md | 1 日 |

**マージ順序**: PR-C → PR-D-Py → (PR-D-Cpp/Rust/CSharp/Go/Wasm 並列) → PR-D-Docs

---

## 2.8 リスクと対策

| リスク | 影響度 | 対策 |
|-------|-------|-----|
| speaker_embedding_mask の解釈差異 | 中 | 各ランタイムで mask 処理を統一テスト、ONNX グラフ制御の検証 |
| ONNX metadata 読み込み未標準化 | 中 | `config.json` に `style_vector_dim` を明示記載 (フォールバック) |
| 既存 dim=0 モデルで新規テンソル expected される | 低 | `has_style_vector` フラグで入力有無判定、ONNX グラフ検査テスト |
| style_vector_dim 大きい時のメモリ効率 | 低 | dim=256 で +1KB/sample、動的割り当てで影響最小 |
| float32/float64 型不一致 | 低 | ONNX export で float32 統一、ランタイムで `astype(np.float32)` 明示 |

---

## 参考

- 前提 Phase 1: [phase-0-1.md](phase-0-1.md)
- 後続 Phase 5: [phase-5.md](phase-5.md)
- 全体調査: `../peav-style-conditioning.md`
- Speaker embedding 先例: `src/cpp/piper_plus.h`, `src/python/piper_train/export_onnx.py`
