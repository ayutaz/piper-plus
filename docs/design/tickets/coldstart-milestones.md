# コールドスタート最適化 実装マイルストーン

> **関連:** [coldstart-optimization.md](../coldstart-optimization.md)
> **ブランチ:** `feat/coldstart-optimization`
> **目標:** 初回発話 ~2,000ms → ~300ms、2回目以降 ~100ms 維持

---

## マイルストーン一覧

| # | タイトル | 期間 | 期待削減量 | 対象 | リスク |
|---|---------|------|-----------|------|--------|
| M1 | クイックウィン（ORT設定修正） | 1週間 | ~300–500ms | Rust / C# | 低 |
| M2 | Warmup（ダミー推論） | 1–2週間 | ~800ms（初回） | 全プラットフォーム | 低〜中 |
| M3 | 非同期バックグラウンド並列化 | 1–2週間 | ~200–400ms | 全プラットフォーム | 中 |
| M4 | 辞書バイナリ形式化 | 2週間 | ~350–600ms | Rust / WASM | 中 |
| M5 | 事前最適化済みモデル配布 | 2週間 | ~500ms（2回目以降も） | Rust / C# | 中〜高 |
| M6 | .NET ReadyToRun + GPU 検出キャッシュ | 1週間 | ~100–200ms | C# / Rust | 低 |

**M1–M3 完了後の予測:** 初回発話 ~300ms、2回目以降 ~100ms（目標達成）

---

## M1: クイックウィン（ORT設定修正）

### 目標

コード変更が最小限のものから実施し、最大 ~500ms の削減を達成する。

### 対策

#### A. C# `GraphOptimizationLevel` 修正 — 効果: ~200–400ms

`SessionFactory.cs:91` の1行変更。現在 `ORT_DISABLE_ALL` は「C++ piper.cpp に合わせる」という過去のコメントがあるが、現在は C# 独自実装のため制約が不要。

```csharp
// Before
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_DISABLE_ALL;
// After
options.GraphOptimizationLevel = GraphOptimizationLevel.ORT_ENABLE_ALL;
```

> **注意:** `ORT_ENABLE_ALL` はセッション作成時間が伸びる可能性があるため、セッション作成と first inference のトレードオフを計測すること。音声品質の回帰テストも必須。

#### B. Rust `SessionBuilder` スレッド設定 — 効果: ~50–100ms

`engine.rs:95` の `Session::builder()` 後に `with_intra_threads()` / `with_inter_threads()` を追加。VITS は小モデルのため物理コア数上限を設ける。

```rust
// engine.rs
Session::builder()?
    .with_intra_threads(std::thread::available_parallelism()?.get().min(4))?
    .with_inter_threads(1)?
    // ...
```

#### C. C# DirectML 形状事前宣言 — 効果: ~200ms（DirectML 使用時のみ）

DirectML 使用時に `FreeDimensionOverrideByName` で入力形状をヒントとして付与し、初回推論時の再最適化を排除。

```csharp
options.EnableMemoryPattern = false;  // DirectML 必須
options.ExecutionMode = ExecutionMode.ORT_SEQUENTIAL;
options.AddFreeDimensionOverrideByName("batch_size", 1);
options.AddFreeDimensionOverrideByName("phoneme_length", 200);
```

### 成功基準

- C# 初回発話: 2,000ms → 1,500ms 以下
- Rust 初回発話: 2,000ms → 1,800ms 以下
- 既存テストスイート全パス
- 音声品質回帰なし（音声比較テスト）

### 該当ファイル

- `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs:91`
- `src/rust/piper-core/src/engine.rs:95–106`

---

## M2: Warmup（ダミー推論）

### 目標

ユーザーの最初の発話リクエスト前に ORT グラフ最適化キャッシュ・CUDA カーネルロード・CPU JIT を完了させ、初回発話を **2,000ms → 200ms 以下** に削減する。

### 背景

現状の遅延は2段階:
1. `OnnxEngine::load()` セッション作成時 (~1,000ms)
2. 最初の `synthesize()` 時に ORT 内部の最適化実行 (~500ms)

ダミー推論3回で第2フェーズを起動時に前倒し消化できる。

### 対策

#### Rust — `OnnxEngine::warmup()` メソッド追加

```rust
// engine.rs
pub fn warmup(&self) -> Result<(), PiperError> {
    let dummy_ids = ndarray::Array2::<i64>::zeros((1, 5));
    let dummy_lengths = ndarray::Array1::<i64>::from_vec(vec![5]);
    for _ in 0..3 {
        let _ = self.session.run(ort::inputs![
            dummy_ids.view(),
            dummy_lengths.view()
        ]?)?;
    }
    Ok(())
}
```

`voice.rs` の `PiperVoice::load()` 末尾、または CLI で `tokio::spawn_blocking` でバックグラウンド実行。CLI には `--warmup` フラグ（デフォルト有効）を追加。

#### C# — `PiperModel.WarmupAsync()` 追加

```csharp
// PiperModel.cs
public async Task WarmupAsync(int runs = 3)
{
    // ダミーテンソルで推論実行
}

// Program.cs 初期化後
_ = Task.Run(() => model.WarmupAsync());
```

#### WASM — `_init()` に warmup フェーズ追加

```javascript
// index.js の _init() 末尾
this._warmupPromise = this._warmup(3);  // バックグラウンドで起動

// synthesize() 内
await this._warmupPromise;  // 完了を待ってから推論
```

### 成功基準

- Rust / C# / WASM 全てで初回発話 ≤ 200ms（warmup 完了後）
- warmup 中に次の呼び出しが来た場合、完了を待って ~100ms で応答
- `--no-warmup` フラグでバイパス可能（CI/テスト環境向け）
- warmup 3回で効果が頭打ちになることを計測で確認

### 注意点

- ダミー入力は最低1つの有効 phoneme ID が必要（空配列はエラー）
- GPU 使用時は warmup がより長くかかる可能性
- バッチ処理 CLI (`-f input.jsonl`) では warmup コストが無駄になるためスキップを検討

### 該当ファイル

- `src/rust/piper-core/src/engine.rs`
- `src/rust/piper-core/src/voice.rs`
- `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`
- `src/wasm/openjtalk-web/src/index.js`

---

## M3: 非同期バックグラウンド並列化

### 目標

現在逐次実行されている「ONNX セッション作成」と「辞書ロード」を並列化し、体感の初期化時間を **200–400ms 削減** する。

### 背景

`voice.rs` では以下が逐次実行されており、依存関係はない:

```rust
// 現状（逐次）
let phonemizer = Self::create_phonemizer(...)?; // JA:300ms / EN:200ms / ZH:400ms
let engine = OnnxEngine::load(...)?;            // ~1,000ms
```

### 対策

#### Rust — `std::thread::spawn` による並列初期化

`piper-core` は現状 tokio 依存なし。`std::thread` で並列化:

```rust
// voice.rs
pub fn load(model_path, config_path, device) -> Result<Self, PiperError> {
    let config_clone = config.clone();
    let model_dir_clone = model_dir.clone();

    let phonemizer_handle = std::thread::spawn(move || {
        Self::create_phonemizer(&config_clone, model_dir_clone.as_deref())
    });
    let engine = OnnxEngine::load(model_path, &config, device)?;
    let phonemizer = phonemizer_handle.join().map_err(|_| PiperError::...)??;
    // ...
}
```

> **確認必須:** `jpreprocess` の初期化がスレッドセーフかどうかを確認すること。

#### C# — `Task.WhenAll` による並列初期化

```csharp
// Program.cs
var sessionTask = Task.Run(() => SessionFactory.Create(modelPath));
var engineTask = Task.Run(() => new DotNetG2PEngine());  // 辞書ロードを並列化

await Task.WhenAll(sessionTask, engineTask);
```

#### WASM — `Promise.all` による並列化

```javascript
// index.js の _init()
const [session, _phonemizer] = await Promise.all([
    WebGPUSessionManager.createSession(modelUrl, ortModule),
    SimpleUnifiedPhonemizer.initialize(configJson),
]);
```

### 期待削減時間

| 言語 | 現状 | 並列化後 |
|------|------|---------|
| JA | jpreprocess 300ms + ORT 1,000ms = 1,300ms | max(300, 1,000) = 1,000ms |
| EN | CMU 200ms + ORT 1,000ms = 1,200ms | max(200, 1,000) = 1,000ms |
| ZH | Pinyin 400ms + ORT 1,000ms = 1,400ms | max(400, 1,000) = 1,000ms |

### 成功基準

- 日本語モデルの `PiperVoice::load()` が ~1,300ms → 1,000ms 以下
- 既存の公開 API を破壊的変更なしで実装
- `jpreprocess` スレッドセーフ性が確認済みまたは適切にラップされていること

### 該当ファイル

- `src/rust/piper-core/src/voice.rs:26–102`
- `src/csharp/PiperPlus.Cli/Program.cs:689–720`
- `src/wasm/openjtalk-web/src/index.js:195–252`

---

## M4: 辞書バイナリ形式化（JSON → bincode）

### 目標

CMU Dict（15万エントリ / ~200ms）と Pinyin辞書（20万+エントリ / ~400ms）の JSON パース時間を排除し、bincode デシリアライズ（~20–40ms）に置き換える。

### 技術的根拠

現状の辞書ロードは:
1. `std::fs::read_to_string()` — ファイルI/O
2. `serde_json::from_str()` — JSON パース（最大ボトルネック）
3. `HashMap` 構築

`bincode` はバイナリフォーマットのため手順2のコストを 5–10x 削減できる。

### 対策

#### ビルドスクリプト — JSON → bincode 事前変換

`piper-core/build.rs` に、ビルド時に辞書 JSON を bincode に変換するスクリプトを追加。

#### Rust — ローダー関数の変更

```rust
// english.rs の load_cmu_dict()
fn load_cmu_dict() -> HashMap<String, String> {
    // .bincode ファイルが存在すればそちらを使用
    if let Ok(bytes) = include_bytes!("cmu_dict.bincode") {
        return bincode::deserialize(bytes).unwrap();
    }
    // fallback: JSON
    let json = include_str!("cmu_dict.json");
    serde_json::from_str(json).unwrap()
}
```

#### 配布物の更新

辞書ファイルを JSON から bincode に変更。変換ツール（`piper --convert-dict`）を提供。

### 成功基準

- 英語辞書ロード: 200ms → 30ms 以下
- 中国語辞書ロード: 400ms → 50ms 以下
- bincode ファイル不在時に JSON フォールバックが機能すること
- 全テストパス

### 注意点

- `bincode` crate を `Cargo.toml` に追加
- bincode v2 は v1 と非互換。バージョンを固定すること
- 辞書配布形式変更はユーザー向けドキュメント更新が必要
- WASM では bincode ファイルサイズが JSON 圧縮より大きい可能性 → 転送サイズとパース速度のトレードオフを確認

### 該当ファイル

- `src/rust/piper-core/src/phonemize/english.rs:549–641`
- `src/rust/piper-core/src/phonemize/chinese.rs:666–840`
- `src/rust/piper-core/Cargo.toml`

---

## M5: 事前最適化済みモデル配布

### 目標

ORT グラフ最適化（~500ms）を初回起動時のみ実行し、結果をキャッシュ・配布することで2回目以降の起動コストをゼロにする。

### 技術的根拠

ORT の `optimized_model_filepath` オプションで最適化結果を `.onnx` ファイルに保存でき、次回以降はロードするだけで最適化フェーズをスキップできる。さらに `.ort` 形式（ORT 独自バイナリ）はロード自体も高速。

### 対策

#### Rust — `SessionBuilder` に最適化キャッシュ設定

```rust
// engine.rs
let optimized_path = model_path.with_extension("opt.onnx");
let builder = Session::builder()?
    .with_optimization_level(GraphOptimizationLevel::Level3)?;

let builder = if optimized_path.exists() {
    // 最適化済みモデルをロード（最適化スキップ）
    builder
} else {
    // 最適化実行 + 保存
    builder.with_optimized_model_filepath(&optimized_path)?
};
```

#### C# — `SessionOptions.OptimizedModelFilePath` 設定

```csharp
// SessionFactory.cs
var optimizedPath = Path.ChangeExtension(modelPath, ".opt.onnx");
if (!File.Exists(optimizedPath))
    options.OptimizedModelFilePath = optimizedPath;
```

#### モデル変換スクリプト提供

`scripts/optimize_model.py` または `cargo run --bin piper-optimize` で `.ort` 形式への変換ツールを提供。HuggingFace 配布モデルには事前最適化済みを添付。

### 成功基準

- 2回目以降の起動でグラフ最適化コスト (~500ms) がゼロ
- `{model}.opt.onnx` 生成が自動・透過的に機能
- 最適化済みモデルの音声品質が元モデルと同等

### 注意点

- 最適化済みモデルは ORT バージョンに依存 → バージョン変更時は再生成が必要
- DirectML/CUDA の最適化済みモデルは CPU では動作しない → ファイル名にデバイス情報を含める設計が必要（例: `model.opt.cpu.onnx`, `model.opt.dml.onnx`）
- ディスク領域: 最適化済みモデルは元の 1–1.5x サイズになる可能性
- `.ort` 形式は Experimental API のため安定性を確認すること

### 該当ファイル

- `src/rust/piper-core/src/engine.rs:88–106`
- `src/csharp/PiperPlus.Core/Inference/SessionFactory.cs`

---

## M6: .NET ReadyToRun + GPU 検出キャッシュ

### 目標

C# の .NET JIT コンパイルコストと Rust の GPU 検出コストを削減し、起動時間を全体的に短縮する。

### 対策

#### C# — ReadyToRun 発行

```xml
<!-- PiperPlus.Cli.csproj -->
<PropertyGroup>
  <PublishReadyToRun>true</PublishReadyToRun>
</PropertyGroup>
```

CI の `dotnet publish` コマンドに `-p:PublishReadyToRun=true` を追加。プラットフォーム固有のバイナリを生成するため、CI マトリクス（linux-x64 / win-x64 / osx-arm64）それぞれでビルドが必要。

#### Rust — GPU 検出結果のキャッシュ

`gpu.rs:122–149` の `auto_detect_device()` は毎回 CUDA/DirectML の検出を行う (~100ms)。検出結果を設定ファイル（`~/.piper/device_cache.json`）にキャッシュする機能を追加。

```rust
// gpu.rs
fn auto_detect_device() -> GpuDevice {
    if let Some(cached) = read_device_cache() {
        return cached;
    }
    let device = detect_device_internal();
    write_device_cache(&device);
    device
}
```

### 成功基準

- C# CLI の起動から first inference ready まで ~100–200ms 短縮
- `dotnet publish` の出力バイナリサイズが 50MB 以下を維持
- GPU 検出キャッシュが有効な場合 `auto_detect_device()` が ~5ms 以下

### 注意点

- `DotNetG2P.MeCab` が native DLL を使っているため完全な Native AOT は現時点で困難
- GPU 検出キャッシュはドライバ更新時に無効化する仕組みが必要
- ReadyToRun は AOT と異なりフォールバック JIT がある → 完全なウォームアップではない

### 該当ファイル

- `src/csharp/PiperPlus.Cli/PiperPlus.Cli.csproj`
- `src/rust/piper-core/src/gpu.rs:118–149`
- `.github/workflows/csharp-ci.yml`

---

## 優先度の根拠

```
M1 (1週間) → M2 (1-2週間) → M3 (1-2週間) → M4 (2週間) → M5 (2週間) → M6 (1週間)
 クイックウィン   最大効果     並列化          辞書高速化    モデルキャッシュ   .NET最適化
  低リスク        全対応       アーキ変更       配布変更      配布変更          ビルド変更
```

| 順序 | 理由 |
|------|------|
| M1 が最初 | `ORT_DISABLE_ALL` は1行変更で ~200–400ms 改善の可能性。リスク最小。 |
| M2 が2番目 | アーキテクチャを変えず、ORT 内部状態を事前構築するだけ。全実装に適用できコスパが最も高い。 |
| M3 が3番目 | 並列化で M2 で削減しきれない辞書ロード時間を解消。`jpreprocess` スレッドセーフ性の確認が必要なため M2 より後。 |
| M4 が4番目 | 辞書自体の高速化だが配布形式変更を伴う。M3 と組み合わせると辞書ロードがほぼゼロになる。 |
| M5 が5番目 | 最も効果的だが、モデル管理・バージョン管理・デバイス依存性など複雑さが高い。 |
| M6 が最後 | 効果が小さく (~50–100ms)、CI ビルドの変更を伴うため後回し。 |

---

## 計測方法

各マイルストーン前後で以下を計測:

```rust
// Rust
let start = std::time::Instant::now();
let voice = PiperVoice::load(...)?;
let init_time = start.elapsed();

let start = std::time::Instant::now();
voice.synthesize_text("テスト")?;
let first_inference_time = start.elapsed();
```

```csharp
// C#
var sw = Stopwatch.StartNew();
var session = SessionFactory.Create(modelPath);
Console.WriteLine($"Session init: {sw.ElapsedMilliseconds}ms");

sw.Restart();
session.Run(...);
Console.WriteLine($"First inference: {sw.ElapsedMilliseconds}ms");
```

計測結果はマイルストーンの PR に記載すること。
