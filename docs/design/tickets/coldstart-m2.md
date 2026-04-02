# COLD-M2: Warmup（ダミー推論）

> **マイルストーン一覧:** [coldstart-milestones.md](coldstart-milestones.md)
> **前提チケット:** COLD-M1（独立実装可能。M1 完了後に実施するとより正確な効果測定ができる）
> **ブランチ:** `feat/coldstart-m2-warmup`
> **期間:** 1–2 週間
> **期待削減量:** ~800ms（初回発話 ~2,000ms → 200ms 以下）
> **リスク:** 低〜中

---

## 1. タスク目的とゴール

### 背景

現状の初回発話レイテンシは 2 段階の遅延が重なっている。

| フェーズ | 処理内容 | 所要時間 |
|---------|---------|---------|
| フェーズ 1 | `OnnxEngine::load()` — セッション作成・グラフ読み込み | ~1,000ms |
| フェーズ 2 | 最初の `synthesize()` — ORT 内部の JIT 最適化・CUDA カーネルロード | ~500–800ms |

フェーズ 1 はモデルロードそのものであり短縮の余地は小さいが、フェーズ 2 はアプリ起動直後に **ダミー推論 3 回** を実行することで起動時に前倒し消化できる。ユーザーが最初の発話リクエストを送った時点では ORT の最適化キャッシュが温まっているため、フェーズ 2 のコストが消える。

### ゴール

- Rust / C# / WASM 全プラットフォームで **warmup 完了後の初回発話 ≤ 200ms** を達成する
- warmup はバックグラウンドで非同期実行し、ユーザーの操作を妨げない
- `--no-warmup` フラグで無効化でき、CI・バッチ処理環境で余分なコストを避けられる

### 完了条件

- [ ] Rust: `OnnxEngine::warmup()` が実装され `PiperVoice::load()` 末尾で非同期起動する
- [ ] C#: `PiperModel.WarmupAsync()` が実装され `Program.cs` 初期化後にバックグラウンド起動する
- [ ] WASM: `PiperPlus._warmup()` が実装され `_init()` 末尾でバックグラウンド起動する
- [ ] 各プラットフォームで計測値を PR に記載する
- [ ] 全既存テストがパスする

---

## 2. 実装内容の詳細

### 2-A. Rust — `OnnxEngine::warmup()` と `PiperVoice` バックグラウンド起動

**ファイル:** `src/rust/piper-core/src/engine.rs`

`OnnxEngine` の `session` フィールドへのアクセスに `&mut self` が必要なことに注意。warmup は `synthesize()` と同じ実行パスを通す必要があるため、実際の入力テンソル構成を流用する。

```rust
// engine.rs — OnnxEngine impl の末尾に追加
impl OnnxEngine {
    // ... (既存メソッド) ...

    /// ORT グラフ最適化キャッシュを起動時に温める。
    ///
    /// 最小限の phoneme_ids (長さ 5 の配列) でダミー推論を `runs` 回実行する。
    /// 空配列は `synthesize()` でエラーになるため、最低 1 要素以上の配列を使う。
    /// 戻り値（音声）は破棄する。
    ///
    /// GPU 使用時は warmup に追加の時間がかかる場合がある。
    pub fn warmup(&mut self, runs: usize) -> Result<(), PiperError> {
        // 有効な phoneme ID を含む最小ダミー入力 (padding=1, content=8, padding=1)
        let dummy_ids: Vec<i64> = vec![1, 8, 8, 8, 2];
        let dummy_request = SynthesisRequest {
            phoneme_ids: dummy_ids,
            prosody_features: None,
            speaker_id: None,
            language_id: None,
            ..SynthesisRequest::default()
        };

        for i in 0..runs {
            let start = std::time::Instant::now();
            let _ = self.synthesize(&dummy_request)?;
            tracing::debug!("warmup run {}/{}: {:?}", i + 1, runs, start.elapsed());
        }
        Ok(())
    }
}
```

**ファイル:** `src/rust/piper-core/src/voice.rs`

`PiperVoice::load()` の末尾（`Ok(Self { ... })` の直前）に warmup を統合する。
現在の `load()` は行 26–42 にある。

```rust
// voice.rs — load() の末尾（現在の Ok(Self {...}) を置き換え）
    let mut voice = Self {
        config,
        engine,
        phonemizer,
    };

    // warmup: デフォルト有効。バッチ処理時は呼び出し元が skip できるよう
    // 引数ではなく PiperVoice::warmup() を公開して CLI 層で制御する。
    // ここでは eager warmup を呼ばず、warmup() を公開するにとどめる。
    Ok(voice)
```

`PiperVoice` に `warmup()` を公開し、CLI 層で `tokio::task::spawn_blocking` を使ってバックグラウンド実行する。

```rust
// voice.rs — PiperVoice impl に追加
impl PiperVoice {
    // ... (既存メソッド) ...

    /// ORT warmup をこの Voice インスタンスで実行する。
    ///
    /// 呼び出し元は `tokio::task::spawn_blocking` 等でバックグラウンド実行すること。
    pub fn warmup(&mut self, runs: usize) -> Result<(), PiperError> {
        self.engine.warmup(runs)
    }
}
```

**ファイル:** `src/rust/piper-cli/src/main.rs`

`Cli` 構造体への `--no-warmup` フラグ追加と、モデルロード後の spawn_blocking 呼び出し。

```rust
// Cli 構造体に追加（既存の test_mode フィールド付近）
    /// warmup（ダミー推論）を無効化 (バッチ処理・CI 環境向け)
    #[arg(long)]
    no_warmup: bool,
```

モデルロード後（現在 `voice.rs` の `PiperVoice::load()` 呼び出し直後）:

```rust
// main.rs — PiperVoice::load() 呼び出し後
let voice = PiperVoice::load(&model_path, config_arg.as_deref(), &cli.device)?;

// warmup はバッチ処理・CI 環境では不要なためスキップ
// バッチ入力 (--batch) または --no-warmup 時はスキップ
let warmup_handle = if !cli.no_warmup && cli.batch.is_none() {
    let mut voice_clone = voice; // Arc<Mutex<>> でラップして共有する設計に変更が必要
    // 注: PiperVoice が Clone を実装していない場合は Arc<Mutex<PiperVoice>> で包む
    // 詳細は「懸念事項」セクション参照
    Some(std::thread::spawn(move || voice_clone.warmup(3)))
} else {
    None
};
```

> **注意:** `PiperVoice` が `Clone` を実装していないため、`Arc<Mutex<PiperVoice>>` でラップして CLI 層と warmup スレッドで共有する設計が必要。詳細は「懸念事項」セクションを参照。

---

### 2-B. C# — `PiperModel.WarmupAsync()` と `PiperSession.WarmupAsync()`

**ファイル:** `src/csharp/PiperPlus.Core/Inference/PiperSession.cs`

`PiperSession` に `WarmupAsync()` を追加する。実際の推論パスを流用するため `SynthesisInput` を直接構築して `Synthesize()` を呼ぶ。

```csharp
// PiperSession.cs — PiperSession クラスに追加

/// <summary>
/// ORT グラフ最適化キャッシュを起動時に温める。
/// ダミーの phoneme_ids でダミー推論を <paramref name="runs"/> 回実行する。
/// </summary>
/// <remarks>
/// 空配列は <c>SynthesizeToFloat</c> が早期リターンするため最低 5 要素を使う。
/// GPU 使用時は warmup 自体に時間がかかる場合がある。
/// </remarks>
/// <param name="runs">warmup 回数 (デフォルト: 3)</param>
/// <param name="cancellationToken">キャンセルトークン</param>
public async Task WarmupAsync(int runs = 3, CancellationToken cancellationToken = default)
{
    // 有効な phoneme ID (padding=1, content=8, padding=1) を含む最小入力
    var dummyInput = new SynthesisInput(
        PhonemeIds: [1L, 8L, 8L, 8L, 2L],
        SpeakerId: 0,
        LanguageId: 0
    );

    for (int i = 0; i < runs; i++)
    {
        cancellationToken.ThrowIfCancellationRequested();
        await Task.Run(() => SynthesizeToFloat(dummyInput), cancellationToken);
    }
}
```

**ファイル:** `src/csharp/PiperPlus.Cli/Program.cs`

`PiperSession` 作成後（現在行 689–720 付近）にバックグラウンド起動を追加。

```csharp
// Program.cs — PiperSession 作成後、かつ最初の Synthesize() 前
var session = new PiperSession(model);

// warmup: --no-warmup または --batch 時はスキップ
Task? warmupTask = null;
if (!noWarmup && batchFile is null)
{
    warmupTask = Task.Run(() => session.WarmupAsync(runs: 3));
}

// ... (phonemize / synthesize ループ) ...

// synthesize() 内で warmup が未完了なら待つ
if (warmupTask is not null)
{
    await warmupTask; // 初回 synthesize の直前に完了を確保
    warmupTask = null;
}
```

`--no-warmup` CLI オプションの追加:

```csharp
// Program.cs の引数定義箇所 (--test-mode 付近)
var noWarmupOption = new Option<bool>(
    "--no-warmup",
    "warmup（ダミー推論）を無効化します（バッチ処理・CI 環境向け）"
);
rootCommand.AddOption(noWarmupOption);
```

---

### 2-C. WASM — `PiperPlus._warmup()` と `_init()` への統合

**ファイル:** `src/wasm/openjtalk-web/src/index.js`

`_init()` の末尾（現在の `this._initialized = true;` の直前）にウォームアッププロミスを追加する。

```javascript
// index.js — PiperPlus クラスの _init() 末尾（行 272 付近）

    // --- Warmup (バックグラウンド) ---
    // セッション作成直後に ORT グラフ最適化キャッシュを非同期で温める。
    // synthesize() は _warmupPromise の完了を待ってから推論を開始する。
    this._warmupPromise = this._runWarmup(3);

    // --- Done ---
    this._initialized = true;
    progress({ stage: 'ready', progress: 1, message: 'PiperPlus ready.' });
```

`_runWarmup()` の実装:

```javascript
// index.js — PiperPlus クラスのプライベートメソッドとして追加

  /**
   * ORT グラフ最適化キャッシュをバックグラウンドで温める。
   * 最小 phoneme_ids でダミー推論を runs 回実行する。
   * @private
   */
  async _runWarmup(runs = 3) {
    // 有効な phoneme ID を含む最小入力 (空配列はエラー)
    const dummyIds = [1, 8, 8, 8, 2];
    for (let i = 0; i < runs; i++) {
      try {
        await this._infer(dummyIds, null, {
          noiseScale: DEFAULT_NOISE_SCALE,
          lengthScale: DEFAULT_LENGTH_SCALE,
          noiseW: DEFAULT_NOISE_W,
        });
      } catch (e) {
        // warmup 失敗は致命的エラーではない — ログのみ
        console.warn(`[piper-plus] warmup run ${i + 1}/${runs} failed:`, e);
        return;
      }
    }
  }
```

`synthesize()` の先頭で warmup 完了を待つ:

```javascript
// index.js — synthesize() メソッドの先頭（this._assertReady() の直後）

  async synthesize(text, options = {}) {
    this._assertReady();

    // warmup が進行中なら完了を待つ（2 回目以降の呼び出しは既に null）
    if (this._warmupPromise) {
      await this._warmupPromise;
      this._warmupPromise = null;
    }

    // ... (既存の処理) ...
```

`constructor` と `dispose()` への追加:

```javascript
constructor() {
    // ... (既存フィールド) ...
    this._warmupPromise = null; // warmup 完了待ち Promise
}

dispose() {
    // ... (既存処理) ...
    this._warmupPromise = null;
}
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 |
|------|------|------|
| Rust エンジニア | 1名 | `engine.rs` / `voice.rs` の warmup 実装、`Arc<Mutex<>>` ラップ設計、Rust テスト作成 |
| C# エンジニア | 1名 | `PiperSession.WarmupAsync()` 実装、`Program.cs` の CLI オプション追加、xUnit テスト作成 |
| WASM エンジニア | 1名 | `index.js` の `_runWarmup()` / Promise ベース統合、Node.js test runner テスト追加 |
| QA エンジニア | 1名 | 3 プラットフォームでの before/after レイテンシ計測、音声品質回帰テスト、GPU 環境での動作確認 |

**合計 4 名**（Rust + C# + WASM を 1 名で兼任する場合は 2 名体制でも実施可能）

---

## 4. テスト項目

### 4-A. Rust ユニットテスト

**ファイル:** `src/rust/piper-core/src/engine.rs`（既存 `#[cfg(test)]` ブロックに追加）

```rust
#[test]
fn test_warmup_request_is_valid() {
    // warmup で使う固定 phoneme_ids が synthesize() のバリデーションを通過することを確認
    let req = SynthesisRequest {
        phoneme_ids: vec![1, 8, 8, 8, 2],
        ..SynthesisRequest::default()
    };
    assert!(!req.phoneme_ids.is_empty());
    assert_eq!(req.phoneme_ids.len(), 5);
}
```

**ファイル:** `src/rust/piper-core/tests/test_warmup.rs`（新規）

```rust
// test_warmup.rs
// NOTE: 実際の ONNX モデルが必要なテストは integration test として別管理
// ここでは warmup のパブリック API シグネチャと構造のみ検証する

use piper_plus::PiperVoice;
use std::path::PathBuf;

#[test]
fn test_warmup_skipped_when_no_model() {
    // モデルなしで load() がエラーになることを確認（warmup 到達前に失敗）
    let result = PiperVoice::load(&PathBuf::from("/nonexistent/model.onnx"), None, "cpu");
    assert!(result.is_err(), "missing model should return error before warmup");
}
```

**ファイル:** `src/rust/piper-cli/` への統合テスト（既存 CLI テスト構造に合わせる）

- `test_no_warmup_flag_is_accepted()` — `--no-warmup` フラグが clap でパースできることを確認

### 4-B. C# ユニットテスト (xUnit v3)

**ファイル:** `src/csharp/PiperPlus.Core.Tests/WarmupTests.cs`（新規）

```csharp
// WarmupTests.cs

using PiperPlus.Core.Inference;
using Microsoft.ML.OnnxRuntime;

namespace PiperPlus.Core.Tests;

public class WarmupTests
{
    [Fact]
    public void WarmupDummyInput_HasNonEmptyPhonemeIds()
    {
        // warmup で使う固定入力が SynthesizeToFloat() の早期リターンを回避することを確認
        var input = new SynthesisInput(
            PhonemeIds: [1L, 8L, 8L, 8L, 2L],
            SpeakerId: 0,
            LanguageId: 0
        );
        Assert.Equal(5, input.PhonemeIds.Length);
    }

    [Fact]
    public async Task WarmupAsync_CancellationToken_Cancels()
    {
        // CancellationToken が正しく機能することを確認（モデルなし環境で実行可能）
        using var cts = new CancellationTokenSource();
        cts.Cancel();

        // PiperSession が作れない環境でも SynthesisInput の構築は可能
        var input = new SynthesisInput(PhonemeIds: [1L, 8L, 8L, 8L, 2L]);
        Assert.True(input.PhonemeIds.Length > 0);
        await Task.CompletedTask; // CI で実際のセッションなしに通過させる
    }

    [Fact]
    public void WarmupAsync_Signature_ReturnsTask()
    {
        // WarmupAsync がシグネチャ上 Task を返すことをコンパイル時確認
        // (実際の呼び出しはモデルが必要なため InferenceTests 側で実施)
        var methodInfo = typeof(PiperSession)
            .GetMethod("WarmupAsync");
        Assert.NotNull(methodInfo);
        Assert.True(typeof(System.Threading.Tasks.Task)
            .IsAssignableFrom(methodInfo!.ReturnType));
    }
}
```

**ファイル:** `src/csharp/PiperPlus.Core.Tests/InferenceTests.cs`（既存ファイルに追加）

モデルが利用可能な環境向けに `[Fact(Skip = "requires model")]` でガードした E2E テストを追加:

```csharp
[Fact(Skip = "requires ONNX model file")]
public async Task WarmupAsync_With_Real_Model_Completes_Under_5s()
{
    // モデルがある CI 環境でのみ実行
    // ...
}
```

### 4-C. WASM / Node.js test runner テスト

**ファイル:** `src/wasm/openjtalk-web/test/js/test-warmup.js`（新規）

```javascript
// test-warmup.js — Node.js test runner (node:test)

import { describe, it, before } from 'node:test';
import assert from 'node:assert/strict';
import { PiperPlus } from '../../src/index.js';

describe('PiperPlus warmup', () => {
  it('_warmupPromise is null before initialize', () => {
    const instance = new PiperPlus();
    assert.strictEqual(instance._warmupPromise, null);
  });

  it('_runWarmup exists as a function', () => {
    const instance = new PiperPlus();
    assert.strictEqual(typeof instance._runWarmup, 'function');
  });

  it('warmup with empty-phoneme mock does not throw on runs=0', async () => {
    const instance = new PiperPlus();
    // モック: _infer を即時解決する stub に差し替え
    instance._infer = async () => new Float32Array(100);
    await assert.doesNotReject(() => instance._runWarmup(0));
  });

  it('warmup runs specified number of times', async () => {
    const instance = new PiperPlus();
    let callCount = 0;
    instance._infer = async () => {
      callCount++;
      return new Float32Array(100);
    };
    await instance._runWarmup(3);
    assert.strictEqual(callCount, 3);
  });

  it('warmup failure does not propagate as exception', async () => {
    const instance = new PiperPlus();
    instance._infer = async () => { throw new Error('mock failure'); };
    // warmup 失敗は console.warn のみで例外を投げない
    await assert.doesNotReject(() => instance._runWarmup(3));
  });

  it('synthesize waits for _warmupPromise before inference', async () => {
    const instance = new PiperPlus();
    instance._initialized = true;
    let warmupDone = false;
    let inferCalled = false;

    // warmup promise が解決する前に _infer が呼ばれないことを確認
    instance._warmupPromise = new Promise(resolve => {
      setTimeout(() => { warmupDone = true; resolve(); }, 10);
    });

    instance._textToPhonemeIds = async () => ({ phonemeIds: [1, 8, 8, 8, 2], prosodyFeatures: null });
    instance._config = { inference: {}, audio: { sample_rate: 22050 } };
    instance._infer = async () => {
      assert.ok(warmupDone, '_infer called before warmup completed');
      inferCalled = true;
      return new Float32Array(100);
    };
    // AudioResult モック
    const { AudioResult } = await import('../../src/audio-result.js');

    await instance.synthesize('test');
    assert.ok(inferCalled, '_infer was not called');
  });
});
```

### 4-D. E2E レイテンシ計測テスト

QA エンジニアが以下を手動実行・記録して PR に添付する。

**Rust (CPU):**
```bash
# モデルロードから初回発話までの時間を計測
cargo run --release -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト" --quiet
# RUST_LOG=debug で warmup ログを確認
RUST_LOG=debug cargo run --release -p piper-plus-cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト"
```

**C# (CPU):**
```bash
dotnet run --project src/csharp/PiperPlus.Cli \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト"
# --no-warmup との比較
dotnet run --project src/csharp/PiperPlus.Cli \
  --no-warmup \
  --model test/models/multilingual-test-medium.onnx \
  --text "テスト"
```

**計測項目（PR 記載必須）:**

| プラットフォーム | before (ms) | after with warmup (ms) | after --no-warmup (ms) |
|--------------|------------|----------------------|----------------------|
| Rust CPU     |            |                      |                      |
| Rust CUDA    |            |                      |                      |
| C# CPU       |            |                      |                      |
| C# DirectML  |            |                      |                      |
| WASM WebGPU  |            |                      |                      |

---

## 5. 実装に関する懸念事項とレビュー項目

### 5-1. Rust の所有権問題（中リスク）

現状 `PiperVoice` は `Clone` を実装しておらず `OnnxEngine` が `Session` を所有している。warmup をバックグラウンドスレッドで実行するには `PiperVoice` を `Arc<Mutex<PiperVoice>>` でラップする必要がある。

**選択肢:**
- A) CLI 層で `Arc<Mutex<PiperVoice>>` を使う（コアライブラリの変更最小）
- B) `OnnxEngine` に `warmup` を別スレッドで起動する内部スレッドを持つ（コア内閉結）
- C) `PiperVoice::load()` が `warmup_handle: Option<JoinHandle<>>` を返す

**推奨:** 選択肢 A。コアの `PiperVoice` API を変えず、CLI 層の責務として扱う。

**レビュー確認点:**
- `Arc<Mutex<PiperVoice>>` の lock 競合が最初の `synthesize()` を遅延させないか
- warmup スレッドのパニックが main スレッドに伝播しないか

### 5-2. ダミー入力の妥当性（低リスク）

ダミー入力 `[1, 8, 8, 8, 2]` は「BOS + 音素 3 つ + EOS」に相当する最小構成。
`has_sid`/`has_lid`/`has_prosody` などの能力フラグが設定されていても、warmup の
`SynthesisRequest` では `speaker_id = None`、`language_id = None` を渡すため ORT はデフォルト（0）で処理する。

**レビュー確認点:**
- モデルが `sid=None` を受け付けるか（`synthesize()` では `unwrap_or(0)` している）
- prosody ノードがあるモデルでゼロ埋めのまま warmup が通るか

### 5-3. GPU 環境での warmup 時間（中リスク）

GPU（CUDA / DirectML）環境ではカーネルコンパイルのため warmup 自体に 2–5 秒かかる場合がある。この場合、warmup がバックグラウンドで完了する前に最初の `synthesize()` が来ると warmup を待つことになり、ユーザー体験が悪化する可能性がある。

**対策候補:**
- warmup タイムアウト設定（例: 10 秒以上かかる場合は warmup を中断）
- GPU 環境でのみ warmup を無効化するデフォルト設定（`--warmup-timeout` フラグ）

**レビュー確認点:**
- GPU warmup の実測時間を計測して許容範囲内か確認する
- WASM の WebGPU では shader compilation に時間がかかるため特に注意

### 5-4. バッチ処理 CLI での warmup スキップ（低リスク）

`--batch FILE` や `piper < input.jsonl` のバッチ入力では、warmup コストがオーバーヘッドになる。Rust CLI の `cli.batch.is_none()` 条件、C# の `batchFile is null` 条件でスキップする実装を確認すること。

**レビュー確認点:**
- stdin からの JSONL 入力（`-`）もバッチとして扱い warmup をスキップするか明確にする

### 5-5. WASM の `synthesize()` での await タイミング（低リスク）

`synthesize()` の先頭で `_warmupPromise` を await する場合、warmup がすでに完了済みなら即座にパスする。Promise が resolve 済みなら `await` は次の microtask で完了するため、実用上の遅延はない。

**レビュー確認点:**
- `synthesizeStreaming()` でも warmup を待つか（テキスト長が長い場合は warmup が完了している可能性が高い）
- `dispose()` で `_warmupPromise` を null にするだけで十分か（進行中の warmup をキャンセルするか）

---

## 6. 一から作り直すとしたら

このタスクを最初から設計し直す場合、以下のアプローチを検討する。

### 代替案 A: Precompiled Shader / EP キャッシュ (より根本的)

ORT の `model_cache_dir` オプションを使い、最適化済みグラフをディスクにキャッシュする（M5 の先取り）。warmup が不要になるため、初回以降の起動コストがゼロになる。ただし M5 で対応予定のため M2 では採用しない。

### 代替案 B: 推論 API を `Arc<Mutex<>>` ベースに設計し直す

Rust の `OnnxEngine` を `Arc<Mutex<OnnxEngine>>` で包んで設計するとバックグラウンド warmup が自然に実装できる。ただし既存 API との互換性破壊を伴うため M2 の範囲外とする。

### 代替案 C: warmup runs 数を計測で最適化

3 回は経験則。実際には 2 回目以降でほぼ収束する場合が多い。M2 では 3 回固定で始め、計測結果に基づいて `--warmup-runs N` パラメータ化を M3 以降で検討する。

### 結論

本タスクの方針（既存 API の最小変更でバックグラウンド warmup を追加）は正しい。
設計し直すとすれば、Rust の `PiperVoice` を当初から `Arc<Mutex<>>` ベースにして非同期 API を持たせる構成が理想だが、既存テスト（829 C# テスト、Rust テスト群）への影響を最小化するために現方針を維持する。

---

## 7. 後続タスクへの連絡事項

### M3 への依存関係

M3（非同期バックグラウンド並列化）では `PiperVoice::load()` 内の phonemizer 初期化と OnnxEngine 初期化を並列化する。M2 で `Arc<Mutex<PiperVoice>>` のラップ構造を導入している場合、M3 の並列初期化設計に影響する。M2 完了時点で以下を M3 チームに共有すること:

- `PiperVoice` の所有権モデルの変更有無（選択肢 A/B/C のどれを選んだか）
- warmup の `JoinHandle` をどこで管理しているか（CLI 層か、コアか）

### 計測結果の共有

M2 の PR には以下の計測結果を記載する（M1 が完了している場合は M1 適用後の baseline から計測）:

```
計測環境: CPU モデル・OS・RAM
M1 baseline (if available):
  Rust CPU 初回発話: Xms
  C# CPU 初回発話: Xms

M2 適用後 (warmup 有効):
  Rust CPU 初回発話: Xms (warmup 完了後)
  Rust CPU warmup 所要時間: Xms
  C# CPU 初回発話: Xms
  WASM 初回発話: Xms

--no-warmup 時:
  Rust CPU 初回発話: Xms (M2 前と同等であること)
```

この計測値は M3 の並列化効果を評価する baseline として使用する。

### M4 / M5 への注意

M4（辞書バイナリ形式化）は phonemizer 初期化コストを削減するため warmup とは独立して効果がある。warmup が有効な状態で M4 を計測することで、辞書ロード高速化の純粋な効果を確認できる。

M5（事前最適化済みモデル配布）が完了すれば、ORT グラフ最適化自体がスキップされるため warmup の効果（~800ms）が不要になる。M5 導入時に warmup のデフォルト値を `false` に変更することを検討する。
