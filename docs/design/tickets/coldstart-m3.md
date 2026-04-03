# COLD-M3: 非同期バックグラウンド並列化

> **マイルストーン一覧:** [coldstart-milestones.md](coldstart-milestones.md)
> **チケット番号:** COLD-M3
> **ブランチ:** `feat/coldstart-m3-parallel-init`
> **依存:** M1 完了推奨。M2 とは独立して実装可能（並列化対象は `load()` フェーズ、M2 の warmup は `synthesize()` フェーズ）
> **期間:** 1–2 週間
> **期待削減量:** ~200–400ms
> **対象:** Rust / C# / WASM 全プラットフォーム
> **リスク:** 中

---

## 1. タスク目的とゴール

`PiperVoice::load()` / C# `Program.cs` 初期化 / WASM `_init()` において、現在**逐次実行**されている「ONNX セッション作成」と「辞書ロード（音素化器初期化）」を**並列実行**に変更する。

両処理はデータ依存関係がなく、並列化しても正確性に影響しない。

### 期待削減量

| 言語 | 逐次（現状） | 並列化後 | 削減量 |
|------|------------|---------|--------|
| JA | jpreprocess 300ms + ORT 1,000ms = 1,300ms | max(300, 1,000) = **1,000ms** | **-300ms** |
| EN | CMU Dict 200ms + ORT 1,000ms = 1,200ms | max(200, 1,000) = **1,000ms** | **-200ms** |
| ZH | Pinyin 400ms + ORT 1,000ms = 1,400ms | max(400, 1,000) = **1,000ms** | **-400ms** |

### 成功基準

- JA: `PiperVoice::load()` が 1,300ms → **1,000ms 以下**
- EN: 1,200ms → **1,000ms 以下**
- ZH: 1,400ms → **1,000ms 以下**
- 既存の公開 API（`PiperVoice::load` シグネチャ）を**破壊的変更なし**で実装
- `jpreprocess` のスレッドセーフ性が確認済みまたは適切にラップされていること
- 既存テストスイート全パス（Rust: `cargo test`、C#: 829テスト、npm: 282テスト）

---

## 2. 実装する内容の詳細

### 2-A. Rust — `std::thread::spawn` による並列初期化

**変更ファイル:** `src/rust/piper-core/src/voice.rs:26–42`

現状の逐次実行:

```rust
// voice.rs:34–35（現状）
let phonemizer = Self::create_phonemizer(&config, model_dir.as_deref())?;
let engine = OnnxEngine::load(model_path, &config, device)?;
```

並列化後:

```rust
// voice.rs の PiperVoice::load() 内
pub fn load(
    model_path: &Path,
    config_path: Option<&Path>,
    device: &str,
) -> Result<Self, PiperError> {
    let resolved_config = VoiceConfig::resolve_config_path(model_path, config_path)?;
    let config = VoiceConfig::load(&resolved_config)?;
    let model_dir = model_path.parent().map(|p| p.to_path_buf());

    // phonemizer の初期化をスレッドで並列実行
    let config_clone = config.clone();
    let model_dir_clone = model_dir.clone();
    let phonemizer_handle = std::thread::spawn(move || {
        Self::create_phonemizer(&config_clone, model_dir_clone.as_deref())
    });

    // メインスレッドで ONNX セッション作成（~1,000ms）
    let engine = OnnxEngine::load(model_path, &config, device)?;

    // スレッド結果を回収
    let phonemizer = phonemizer_handle
        .join()
        .map_err(|_| PiperError::PhonemizerInitFailed("phonemizer thread panicked".into()))??;

    Ok(Self {
        config,
        engine,
        phonemizer,
    })
}
```

**設計上の注意:**

- `piper-core` は現状 `tokio` 依存なし。`tokio` 追加はバイナリサイズ増大と WASM 非対応リスクがあるため `std::thread` を使用する。
- `Phonemizer` トレイトは `Send + Sync` を要求している（`src/rust/piper-core/src/phonemize/mod.rs:37`）。
- `JapanesePhonemizer` は `jpreprocess::JPreprocess<DefaultFetcher>` を内包している（`japanese.rs:334`）。スレッドセーフ性の確認については「懸念事項」セクションを参照。
- `VoiceConfig` に `Clone` が実装されていることを確認すること。実装がなければ `derive(Clone)` を追加する。

### 2-B. C# — `Task.WhenAll` による並列初期化

**変更ファイル:** `src/csharp/PiperPlus.Cli/Program.cs:689–720`

現状の逐次実行:

```csharp
// Program.cs:693–705（現状）
session = SessionFactory.Create(modelPath, useCuda: useCuda, gpuDeviceId: gpuDeviceId);
// ... その後 phonemizer を ResolveTextModePhonemizer(language) で初期化
```

並列化後:

```csharp
// Program.cs — セッション作成と音素化器初期化を並列実行
Task<InferenceSession> sessionTask = Task.Run(() =>
    SessionFactory.Create(modelPath, useCuda: useCuda, gpuDeviceId: gpuDeviceId));

Task<IPhonemizer> phonemizerTask = Task.Run(() =>
    ResolveTextModePhonemizer(language));

await Task.WhenAll(sessionTask, phonemizerTask);

var session = await sessionTask;
var phonemizer = await phonemizerTask;
```

**注意:** `ResolveTextModePhonemizer()` 内で `DotNetG2PEngine` が初期化され、MeCab native DLL のロードが発生する。DLL ロードはスレッドセーフであることを確認すること（Windows DLL ローダーは thread-safe）。

### 2-C. WASM — `Promise.all` による並列化

**変更ファイル:** `src/wasm/openjtalk-web/src/index.js:201–276`

現状の逐次実行:

```javascript
// _init() 内（現状）
// step 2: session 作成（~500–1,000ms）
this._session = await sessionManager.createSession(modelUrl);
// step 3: phonemizer 初期化（辞書 DL + jpreprocess WASM ロード）
await this._phonemizer.initialize({ openjtalk: { dictData, voiceData } });
```

ただし WASM では辞書ダウンロードのネットワーク待ち時間が大きく、ONNX セッション作成と辞書 DL を並列化することで体感待ち時間を削減できる。

**前提条件の分離が必要な変更:**

```javascript
async _init(options) {
    const ort = options.ort || globalThis.ort;
    // --- 1. Config 解決 ---
    const modelManager = new ModelManager();
    const { modelUrl, configUrl } = await modelManager.resolveUrls(options.model);
    this._config = await (await fetch(configUrl)).json();

    // --- 2 & 3. ONNX セッション作成 + 辞書ロードを並列実行 ---
    const dictManager = new DictManager();

    const [session, { dictFiles, voiceData }] = await Promise.all([
        // ONNX セッション作成
        sessionManager.createSession(modelUrl),
        // 辞書ダウンロード + キャッシュ読み込み
        dictManager.loadDictionary({
            dictUrl: options.dictUrl,
            voiceUrl: options.voiceUrl,
            onProgress: ({ phase, overallPercent }) => {
                progress({ stage: 'phonemizer', progress: overallPercent / 100 * 0.8, ... });
            },
        }),
    ]);

    this._session = session;

    // --- 4. 音素化器初期化（辞書ロード完了後）---
    this._phonemizer = new SimpleUnifiedPhonemizer();
    await this._phonemizer.initialize({ openjtalk: { dictData: dictFiles, voiceData } });

    this._initialized = true;
}
```

**注意:** `progress` コールバックの `stage` ラベルが ONNX 側と phonemizer 側で混在するため、進捗報告ロジックを整理すること。

---

## 3. エージェントチームの役割と人数

**推奨チーム構成: 2名**

| エージェント | 役割 | 担当範囲 |
|------------|------|---------|
| エージェント A | Rust 担当 | `voice.rs` 並列化 + スレッドセーフ確認 + Rust テスト追加 |
| エージェント B | C# / WASM 担当 | `Program.cs` `Task.WhenAll` + `index.js` `Promise.all` + npm テスト修正 |

エージェント A は M2 の Rust 実装担当者と同一が望ましい（`OnnxEngine` の内部構造を把握しているため）。

---

## 4. 提供範囲・テスト項目

### 提供範囲

| プラットフォーム | 変更ファイル | 変更内容 |
|---------------|------------|---------|
| Rust | `src/rust/piper-core/src/voice.rs` | `load()` 内の逐次→並列化 |
| Rust | `src/rust/piper-core/src/error.rs` | `PhonemizerInitFailed` エラーバリアント追加（未存在の場合） |
| C# | `src/csharp/PiperPlus.Cli/Program.cs` | セッション+音素化器の並列初期化 |
| WASM | `src/wasm/openjtalk-web/src/index.js` | `_init()` の ONNX+辞書 Promise.all 並列化 |

### Unit テスト

#### Rust — `src/rust/piper-core/tests/test_voice_api.rs` に追加

```rust
// 並列初期化が正常完了することを確認するテスト
#[test]
fn test_parallel_load_does_not_deadlock() {
    // 複数スレッドから同時に load() を呼んでも deadlock しないこと
    let handles: Vec<_> = (0..3).map(|_| {
        std::thread::spawn(|| {
            let result = PiperVoice::load(
                &PathBuf::from("/nonexistent/model.onnx"),
                None,
                "cpu",
            );
            assert!(result.is_err()); // ファイル不在エラー（deadlock しないことを確認）
        })
    }).collect();
    for h in handles {
        h.join().unwrap();
    }
}
```

#### npm — `src/wasm/openjtalk-web/test/js/` に追加

- `_init()` が並列化後も正常に完了することをモック環境で確認
- `Promise.all` が片方失敗した場合に適切にエラーが伝播することを確認

### E2E テスト

M2 で追加した初期化時間計測テストを流用し、並列化前後で計測値を比較：

- Rust: `cargo test --test test_timing` で初期化時間が目標値以内であることを確認
- C#: `dotnet test` で 829 テスト全パスを確認
- npm: `npm test` で 282 テスト全パスを確認

### 計測テスト（手動）

```bash
# Rust
cargo bench --bench coldstart -- parallel_load

# C#
dotnet run --project src/csharp/PiperPlus.Cli -- \
  --model test/models/multilingual-test-medium.onnx \
  --text "こんにちは" --language ja 2>&1 | grep -E "Loading|loaded"

# npm (Node.js モック環境)
node src/wasm/openjtalk-web/test/js/test-init-timing.js
```

---

## 5. 実装に関する懸念事項とレビュー項目

### 懸念事項 1: `jpreprocess` のスレッドセーフ性（重要度: 高）

`JapanesePhonemizer` は `jpreprocess::JPreprocess<DefaultFetcher>` を内包する（`japanese.rs:334`）。`JPreprocess` は辞書ファイルを `mmap` で読み込む可能性があり、**初期化時のスレッドセーフ性を事前確認**すること。

確認方法:
1. jpreprocess の `Cargo.toml` / ソースで `Send + Sync` の実装または `!Send` の明示を確認
2. `cargo test` 時に `RUST_LOG=debug` で jpreprocess 内部ログを確認
3. 複数スレッドから同時に `JPreprocess::from_config()` を呼ぶストレステストを実施

もしスレッドセーフでない場合の代替案:
- `std::sync::Mutex<JapanesePhonemizer>` でラップし、`phonemize_with_prosody` 呼び出し時のみロック取得
- または `OnceLock<JapanesePhonemizer>` をグローバルに使用（初期化を1度だけ保証）

### 懸念事項 2: `VoiceConfig` の `Clone` 実装

`voice.rs` の並列化では `config.clone()` が必要。`VoiceConfig` に `Clone` が実装されていない場合はコンパイルエラーになる。事前に `derive(Clone)` が付与されているか確認し、なければ追加する。

### 懸念事項 3: エラー処理の統一

`phonemizer_handle.join()` が `Err` を返す（スレッドパニック）場合、現在の `PiperError` にそのバリアントがなければ追加が必要。`PhonemizerInitFailed(String)` バリアントを `error.rs` に追加することを検討。

### 懸念事項 4: WASM の `progress` コールバック競合

`Promise.all` で ONNX と辞書 DL が並列実行される場合、両方が `onProgress` コールバックを同時に呼び出す可能性がある（JavaScript はシングルスレッドなので deadlock はないが、進捗が前後する可能性がある）。`stage` ラベル（`'model'` / `'phonemizer'`）で分けているため UI 側への影響は最小限だが、テストで確認すること。

### 懸念事項 5: C# `DotNetG2PEngine` の MeCab native DLL

`ResolveTextModePhonemizer("ja")` は `new DotNetG2PEngine()` を呼び出し、内部で MeCab native DLL をロードする。DLL ロード自体は Windows DLL ローダーがスレッドセーフに処理するが、**複数スレッドから同時に `DotNetG2PEngine` を生成した場合**に問題が出ないことを CI（linux-x64 / win-x64 / osx-arm64）でテストすること。

### レビュー項目チェックリスト

- [ ] `jpreprocess::JPreprocess` が `Send + Sync` を実装しているか確認済み
- [ ] `VoiceConfig` に `Clone` が実装されているか確認済み
- [ ] Rust: `voice.rs` の `load()` シグネチャが変更されていないこと
- [ ] C#: `ResolveTextModePhonemizer` が `Task.Run` 内から安全に呼び出せること
- [ ] WASM: `Promise.all` 失敗時のエラーメッセージが適切であること
- [ ] 全プラットフォームで既存テストが全パスすること
- [ ] 計測結果が PR に添付されていること

---

## 6. 一から作り直すとしたら

現在の設計（`PiperVoice` が phonemizer と engine を直接所有）は正しい方向性。一から設計するなら以下の構造を採用する：

**非同期ファクトリパターン:**

```rust
// 非同期対応ファクトリ（tokio 前提の場合）
impl PiperVoice {
    pub async fn load_async(model_path: &Path, ...) -> Result<Self, PiperError> {
        let (phonemizer, engine) = tokio::join!(
            tokio::task::spawn_blocking(|| Self::create_phonemizer(...)),
            tokio::task::spawn_blocking(|| OnnxEngine::load(...)),
        );
        // ...
    }
}
```

ただし `piper-core` を `tokio` に依存させることは:
- CLI/ライブラリとして使う場合にランタイムを強制する
- WASM ターゲットで `tokio` が非対応
- バイナリサイズ増大

という問題があるため、**現行の `std::thread` 方針が最も汎用的**。将来的に WASM や CLI を分離した場合のみ `tokio` 移行を検討する。

---

## 7. 後続タスクへの連絡事項

### M4（辞書バイナリ形式化）への引き継ぎ

M3 で並列化した「辞書ロード」は M4 で bincode 形式化される予定。M3 完了後は：

- Rust の `Self::create_phonemizer()` が `std::thread::spawn` 内で実行される
- M4 では `create_phonemizer()` 内部の `load_cmu_dict()` / `load_pinyin_dict()` を bincode に変更
- **M3 の並列化コードはそのまま M4 でも有効**（辞書ロードが高速化されるほど ORT のほうが支配的になり削減量は減るが、コードの変更は不要）

### M2（Warmup）との組み合わせ効果

M2 と M3 を両方実装した場合、以下の効果が得られる：

1. M3（並列化）: `load()` 時間が JA で 1,300ms → 1,000ms
2. M2（Warmup）: `synthesize()` の初回レイテンシが 500ms → 50ms 以下

組み合わせると初回発話合計が約 1,050ms → **目標の ~300ms にはまだ届かない**。M4/M5 の実装が目標達成に必須。

### M5（最適化済みモデル配布）への注意

M3 で並列化された `OnnxEngine::load()` は M5 で最適化済みモデルのロードに変更される。`engine.rs` の変更が `voice.rs` の並列化コードに影響しないよう、**`OnnxEngine::load()` のシグネチャを変更しないこと**。

---

## 付録: 参考ファイルパス

| 用途 | パス | 行番号 |
|------|------|--------|
| Rust 主要変更箇所 | `src/rust/piper-core/src/voice.rs` | 26–42 |
| Rust phonemizer トレイト定義 | `src/rust/piper-core/src/phonemize/mod.rs` | 37 |
| Rust Japanese phonemizer | `src/rust/piper-core/src/phonemize/japanese.rs` | 328–386 |
| Rust エラー型 | `src/rust/piper-core/src/error.rs` | — |
| C# 主要変更箇所 | `src/csharp/PiperPlus.Cli/Program.cs` | 689–720 |
| C# phonemizer 解決 | `src/csharp/PiperPlus.Cli/Program.cs` | 1389–1448 |
| WASM 主要変更箇所 | `src/wasm/openjtalk-web/src/index.js` | 195–276 |
| Rust テスト群 | `src/rust/piper-core/tests/` | — |
| C# テスト群 | `src/csharp/PiperPlus.Core.Tests/` | — |
| npm テスト群 | `src/wasm/openjtalk-web/test/js/` | — |
