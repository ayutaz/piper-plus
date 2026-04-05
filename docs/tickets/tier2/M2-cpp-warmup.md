# M2: C++ Warmup 実装

> **マイルストーン**: [M2](../../guides/cpu-inference-tier2-milestones.md#m2-c-warmup-実装)
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md#施策-7-onnx-runtime-warmup)
> **ステータス**: 未着手
> **依存**: [M1](M1-python-warmup.md) (参照実装、並行実装可能)
> **後続**: [M5](M5-integration.md)

---

## 1. タスク目的とゴール

**背景:**
ONNX Runtime は初回 `session.Run()` 時に JIT コンパイルとメモリアロケーション最適化を実行するため、500-800ms の遅延が発生する。Rust (`engine.rs:420-434`) および C# (`SessionFactory.cs:209-306`) では既にダミー推論による warmup を実装済みだが、C++ (`piper.cpp`) は未対応である。

**目的:**
C++ 推論エンジンに warmup 関数を追加し、初回ユーザー推論時の遅延を排除する。Rust/C# と同一のダミー入力パラメータ (100 phonemes, BOS/EOS, scales) を使用し、実装間の整合性を保つ。

**ゴール:**
- `piper.cpp` に `warmupModel()` 関数を追加し、`loadVoice()` 完了後に呼び出す
- `--no-warmup` CLI フラグで無効化可能にする
- warmup 失敗時はアプリケーションを停止せず、warning ログのみで続行する
- 3 OS (Windows/Linux/macOS) で C++ ビルドが成功する

**非ゴール:**
- Python 側の warmup 実装 (M1 のスコープ)
- モデルキャッシュ (.opt.onnx) の実装 (M3 のスコープ)
- warmup 回数のランタイム設定 (将来拡張として検討)

---

## 2. 実装内容の詳細

### 2.1 `warmupModel()` 関数 (`piper.cpp`)

既存の `synthesize()` 関数 (L659-856) と同じテンソル構築パターンを使用してダミー推論を実行する。`synthesize()` を直接呼び出すのではなく、同じパターンでテンソルを構築する方式を採用する。

> **注意:** `synthesize()` のシグネチャは `Voice *voice = nullptr` (オプション引数) であり、`voice=nullptr` で呼び出すこと自体は可能である。設計書 (`cpu-inference-tier2-design.md`) は当初「既存の `synthesize()` を呼び出す」方針を記載していたが、本チケットでは直接テンソル構築方式を採用する。理由は、`synthesize()` は `audioBuffer` への int16 変換、`SynthesisResult` への統計書き込み、duration テンソルのタイミング抽出など warmup に不要な出力処理を含んでおり、これらのオーバーヘッドを回避するためである。将来テンソル構築を共通ヘルパーに抽出した場合は、`synthesize()` 呼び出し方式への移行を検討する。

```cpp
// piper.cpp に追加
void warmupModel(ModelSession &session, int runs) {
    // 1. ダミー phoneme_ids 構築: BOS(1) + dummy(8)x98 + EOS(2) = 100 tokens
    // 2. scales: [0.667, 1.0, 0.8] (Rust/C# と同一)
    // 3. session.hasMultiSpeaker → sid=0 テンソル追加
    // 4. session.hasLidInput → lid=0 テンソル追加
    // 5. session.hasProsodyInput → ゼロ埋め prosody_features テンソル追加
    // 6. session.onnx.Run() を runs 回実行
    // 7. 各 run の実行時間を spdlog::debug で出力
    // 8. 全体の実行時間を spdlog::info で出力
}
```

**パラメータ詳細:**

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| phoneme_ids 長 | 100 | 本番入力 (50-200) と同程度。Rust `WARMUP_PHONEME_LENGTH=100`, C# `WarmupPhonemeLength=100` と同一 |
| BOS | 1 (ID: phonemeIds[0]) | 全実装共通。`PhonemizeConfig::idBos` のデフォルト値 (`piper.hpp` L52) |
| EOS | 2 (ID: phonemeIds[99]) | 全実装共通。`PhonemizeConfig::idEos` のデフォルト値 (`piper.hpp` L53) |
| dummy phoneme | 8 (ID: phonemeIds[1..98]) | Rust/C# と同一のダミー値 |
| scales | `[0.667, 1.0, 0.8]` | `noise_scale=0.667, length_scale=1.0, noise_w=0.8` (SynthesisConfig デフォルト) |
| runs | 2 (デフォルト) | ORT JIT キャッシュは 1-2 回で安定。Rust `DEFAULT_WARMUP_RUNS=2`, C# `DefaultWarmupRuns=2` |
| sid | 0 | `session.hasMultiSpeaker` が true の場合のみ |
| lid | 0 | `session.hasLidInput` が true の場合のみ |
| prosody_features | ゼロ埋め `[1, 100, 3]` | `session.hasProsodyInput` が true の場合のみ |

**テンソル構築の参照パターン** (`piper.cpp` L666-743):

> **注意:** BOS=1, EOS=2 は `PhonemizeConfig` のデフォルト値 (`piper.hpp` L52-53: `idBos=1`, `idEos=2`) を前提としている。カスタム `phoneme_id_map` で BOS/EOS を変更している場合は一致しない可能性があるが、現在の全モデルではデフォルト値を使用しているため問題ない。

```cpp
auto memoryInfo = Ort::MemoryInfo::CreateCpu(
    OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

// 1. input: int64 [1, phoneme_len]
std::vector<int64_t> phonemeIds(100, 8);
phonemeIds[0] = 1;   // BOS (PhonemizeConfig::idBos default)
phonemeIds[99] = 2;   // EOS (PhonemizeConfig::idEos default)
std::vector<int64_t> phonemeIdsShape{1, 100};

// 2. input_lengths: int64 [1]
std::vector<int64_t> phonemeIdLengths{100};

// 3. scales: float32 [3]
std::vector<float> scales{0.667f, 1.0f, 0.8f};

// 4-6. 条件付き入力 (sid, lid, prosody_features)
// session.hasMultiSpeaker / hasLidInput / hasProsodyInput に基づく
```

**例外処理:**

```cpp
try {
    // warmup 実行
} catch (const std::exception &e) {
    spdlog::warn("Warmup failed (non-fatal): {}", e.what());
} catch (...) {
    spdlog::warn("Warmup failed (non-fatal): unknown error");
}
```

Rust 実装 (`engine.rs:420-434`) では `warmup()` が `Result<(), PiperError>` を返し呼び出し側でエラーハンドリングする方式だが、C++ では関数内部で try-catch して非致命的にする。C# (`SessionFactory.cs:300-305`) と同じアプローチ。

### 2.2 `piper.hpp` にシグネチャ追加

```cpp
// piper.hpp の関数宣言セクションに追加
/// Warm up the ONNX session with dummy inference runs.
/// Reduces first-inference latency by 500-800ms.
/// Any exception is caught and logged as a warning (non-fatal).
void warmupModel(ModelSession &session, int runs = 2);
```

`piper` namespace 内、既存の `loadVoice()` 宣言の直後に配置する。

### 2.3 CLI 統合 (`main.cpp`)

**RunConfig に `noWarmup` フィールドを新規追加** (L45-127 の `struct RunConfig` 内):

> **注意:** `noWarmup` フィールドは現在存在しないため新規追加が必要。`RunConfig` の末尾、`modelDir` フィールド (L126) の直後に追加する。

```cpp
struct RunConfig {
    // ... 既存フィールド (L45-126) ...
    optional<filesystem::path> modelDir;
    
    // ↓ 新規追加
    // true to skip warmup after model loading
    bool noWarmup = false;
};
```

**parseArgs() に追加** (L812 開始の `for` ループ内、L921 `--test-mode` 分岐の後に追加):

```cpp
    } else if (arg == "--test-mode") {
      runConfig.testMode = true;
      spdlog::info("Test mode enabled - ONNX runtime will be skipped");
    // ↓ ここに挿入
    } else if (arg == "--no-warmup" || arg == "--no_warmup") {
      runConfig.noWarmup = true;
    } else if (arg == "--debug") {
```

**printUsage() に追加** (L699-767 の `printUsage()` 内、L755 `--model-dir` の後、L757 `--debug` の前に追加):

```cpp
  cerr << "   --model-dir        DIR        directory for downloaded models" << endl;
  // ↓ ここに挿入
  cerr << "   --no-warmup                   skip model warmup (faster startup, slower first inference)"
       << endl;
  cerr << endl;
  cerr << "   --debug                       print DEBUG messages to the console"
```

**knownFlags に追加** (L935-951 の `knownFlags` ベクタ内、L950 `"--no-stochastic"` の後に追加):

```cpp
        "--no-stochastic",
        // ↓ ここに追加
        "--no-warmup", "--no_warmup",
```

**warmup 呼び出し** (`loadVoice()` 完了後、言語解決ロジックの前に挿入):

挿入位置は L287 (`spdlog::info("Loaded voice in {} second(s)", ...)`) の直後、L289 (`// Resolve --language to a numeric language ID`) の直前。

```cpp
// L282-287: 既存コード
loadVoice(piperConfig, runConfig.modelPath.string(),
          runConfig.modelConfigPath.string(), voice, runConfig.speakerId,
          provider, runConfig.gpuDeviceId);
auto endTime = chrono::steady_clock::now();
spdlog::info("Loaded voice in {} second(s)",
             chrono::duration<double>(endTime - startTime).count());

// ↓ ここに挿入 (L288)
// Warmup
if (!runConfig.noWarmup && !runConfig.testMode) {
    piper::warmupModel(voice.session);
}

// L289: 既存コード (言語解決ロジック)
// Resolve --language to a numeric language ID
```

`testMode` の場合は ONNX ランタイムがスキップされるため warmup も不要。

### 2.4 Rust 参照実装との対応

| Rust (`engine.rs`) | C++ (`piper.cpp`) | 備考 |
|--------------------|-------------------|------|
| `WARMUP_PHONEME_LENGTH = 100` | 定数 100 (ローカル) | ヘッダ公開不要 |
| `DEFAULT_WARMUP_RUNS = 2` | デフォルト引数 `runs=2` | 同一値 |
| `warmup(&mut self, runs)` | `warmupModel(ModelSession&, int runs=2)` | self vs 引数渡し |
| `self.synthesize(&dummy_request)?` | 直接テンソル構築 + `session.onnx.Run()` | C++ の `synthesize()` は `Voice*=nullptr` で呼出可能だが、audioBuffer 変換・SynthesisResult 書込み等の不要な出力処理を回避するため直接構築 |
| `tracing::debug!(...)` | `spdlog::debug(...)` | 同等 |
| `Result<(), PiperError>` | `void` (内部 try-catch) | C# と同方式 |

---

## 3. エージェントチームの構成

本タスクは単一エージェントで実装可能。

| 役割 | 担当範囲 | 備考 |
|------|---------|------|
| **実装エージェント** | `piper.cpp`, `piper.hpp`, `main.cpp` の変更 | C++ ONNX Runtime API の理解が必要 |

**作業順序:**
1. `piper.hpp` にシグネチャ追加
2. `piper.cpp` に `warmupModel()` 実装
3. `main.cpp` の `RunConfig`, `parseArgs()`, `printUsage()`, `main()` に統合
4. ビルド確認 (CMake)
5. テスト実行

**推定工数:** 1-2 時間

---

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**変更ファイル:**

| ファイル | 変更内容 |
|----------|---------|
| `src/cpp/piper.hpp` | `warmupModel()` プロトタイプ宣言追加 |
| `src/cpp/piper.cpp` | `warmupModel()` 関数実装追加 |
| `src/cpp/main.cpp` | `RunConfig::noWarmup` フィールド追加、`parseArgs()` に `--no-warmup` 解析追加、`printUsage()` に説明追加、`main()` に warmup 呼び出し追加、`knownFlags` に追加 |

**変更しないファイル:**
- Python 関連ファイル (M1 のスコープ)
- Rust 関連ファイル (実装済み)
- C# 関連ファイル (実装済み)
- CMakeLists.txt (新ファイル追加なし、既存ファイルの変更のみ)
- CI ワークフロー (既存の C++ ビルド CI で検証)

### 4.2 ユニットテスト

C++ テストスイートに以下を追加。ただし、ONNX モデルの実ロードが必要なテストは CI 環境での実行可能性を考慮し、E2E テスト (4.3) として扱う。

| テスト | 内容 | 検証方法 |
|--------|------|---------|
| ダミー入力構築の正しさ | phonemeIds[0]=1 (BOS), phonemeIds[99]=2 (EOS), 中間=8 | ユニットテスト (モデル不要) |
| `--no-warmup` フラグ解析 | `parseArgs()` が `noWarmup=true` を設定 | ユニットテスト (モデル不要) |
| `--no-warmup` デフォルト値 | `RunConfig` 初期値が `false` | ユニットテスト (モデル不要) |

### 4.3 E2E テスト

| テスト | 内容 | 検証方法 |
|--------|------|---------|
| warmup 付き推論 | モデルロード → warmup → 推論 → 音声出力成功 | テストモデル (`test/models/`) で手動確認 |
| `--no-warmup` 付き推論 | `--no-warmup` → 推論 → 音声出力成功 (warmup ログなし) | 手動確認 |
| 3 OS ビルド成功 | Windows/Linux/macOS で CMake ビルド成功 | CI (`cmake-build.yml` 等) |
| `--test-mode` との組み合わせ | `--test-mode` 時に warmup がスキップされる | 手動確認 |

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 影響度 | 対策 |
|---|------|-------|------|
| 1 | **warmup 失敗でアプリケーション停止** | 高 | 全例外を try-catch でキャッチし `spdlog::warn()` のみ出力。C# と同方式 (`SessionFactory.cs:300-305`)。`catch (...)` で未知例外も捕捉 |
| 2 | **GPU OOM** | 中 | 本番と同じ形状 (100 phonemes) を使用。本番推論が動く環境なら warmup も動く。GPU の場合も同一セッションのメモリプール内で完結 |
| 3 | **テンソル構築ロジックの重複** | 中 | `synthesize()` と同じパターンだが関数内にインラインで記述。`synthesize()` は `Voice*=nullptr` で呼出可能だが、audioBuffer 変換等の不要処理を含むため直接構築を選択。将来的にテンソル構築を共通ヘルパーに抽出する余地あり。現時点では warmup 専用のシンプルな実装を優先 |
| 4 | **組込み環境での起動遅延** | 低 | `--no-warmup` フラグで完全無効化可能。環境変数 `PIPER_DISABLE_WARMUP` は Python 側のみで C++ には不要 (CLI フラグで十分) |
| 5 | **warmup 出力の音声バッファ** | 低 | `session.onnx.Run()` の戻り値 (outputTensors) は即時破棄。音声バッファへの書き込みは行わない |

### 5.2 レビューチェックリスト

- [ ] `warmupModel()` のダミー入力値が Rust/C# と一致している (BOS=1, EOS=2, dummy=8, scales=[0.667, 1.0, 0.8], length=100)
- [ ] `session.hasMultiSpeaker` (L700) / `hasLidInput` (L719) / `hasProsodyInput` (L729) の条件分岐が `synthesize()` と同一パターン
- [ ] 入力テンソル名の順序が ONNX モデル定義と一致: `input` → `input_lengths` → `scales` → `sid` → `lid` → `prosody_features`
- [ ] テンソルのライフタイムが `Run()` 完了まで保持されている (ローカル変数が if ブロック内で破棄されない)
- [ ] 出力テンソル名に `output` と `durations` の両方が含まれている (`session.hasDurationOutput` に基づく)
- [ ] 全例外がキャッチされている (`std::exception` + `...`)
- [ ] `spdlog::info` で warmup 完了メッセージが出力されている (回数 + 経過時間)
- [ ] `--no-warmup` が `knownFlags` に追加されている (未知フラグ検出で誤検知しない)
- [ ] `--test-mode` 時に warmup がスキップされている
- [ ] `printUsage()` に `--no-warmup` の説明が追加されている
- [ ] `RunConfig::noWarmup` のデフォルト値が `false` (warmup はデフォルト有効)

---

## 6. 一から作り直すとしたら

1. **テンソル構築の共通化**: 現在 `synthesize()` (L659-856) と `synthesizeFloat()` (L858+) でテンソル構築ロジックが重複している。warmup を追加すると 3 箇所目の重複になる。理想的には `buildInputTensors(phonemeIds, session)` のようなヘルパー関数を抽出し、`synthesize()`, `synthesizeFloat()`, `warmupModel()` の全てがそれを共有すべきである。共通化すれば warmup も `synthesize()` を `Voice*=nullptr` で呼び出す方式に統一可能。ただし、既存コードの大規模リファクタは本タスクのスコープ外とし、将来課題として残す。

2. **warmup を `loadVoice()` 内部に組み込む**: 現在の設計では `main.cpp` で `loadVoice()` の後に明示的に `warmupModel()` を呼ぶ。`loadVoice()` の最後に自動で warmup を実行する方式も検討できたが、ライブラリとしての柔軟性 (呼び出し側が warmup タイミングを制御) を優先して分離した。Rust も `engine.warmup(runs)` を別メソッドとして公開している。

3. **環境変数 `PIPER_DISABLE_WARMUP`**: Python 側は環境変数で制御するが、C++ CLI は `--no-warmup` フラグで十分。ただし、C++ をライブラリとして組み込む場合 (FFI 経由等) は環境変数の方が便利な場面がある。需要が出れば追加する。

---

## 7. 後続タスクへの連絡事項

### M5 (最終統合) への連絡

- `warmupModel()` のシグネチャ: `void warmupModel(ModelSession &session, int runs = 2)` (`piper.hpp` で宣言)
- `--no-warmup` フラグは `RunConfig::noWarmup` で管理
- warmup のログ出力: `spdlog::info("Warmup completed ({} runs in {}ms)", runs, elapsed_ms)` 形式
- CI では既存の C++ ビルドジョブで 3 OS ビルド成功を確認すること
- `--test-mode` と `--no-warmup` の両方が warmup をスキップする点に注意 (テスト時の挙動確認)

### 実装間整合性の確認ポイント

M5 統合時に以下の設定が全実装で統一されていることを確認すること:

| パラメータ | Rust | C# | C++ (本タスク) | Python (M1) |
|-----------|------|-----|---------------|-------------|
| phoneme_length | 100 | 100 | 100 | 100 |
| BOS/EOS | 1/2 | 1/2 | 1/2 | 1/2 |
| dummy phoneme | 8 | 8 | 8 | 8 |
| scales | [0.667, 1.0, 0.8] | [0.667, 1.0, 0.8] | [0.667, 1.0, 0.8] | [0.667, 1.0, 0.8] |
| default runs | 2 | 2 | 2 | 2 |
| 無効化 | N/A (API) | N/A (API) | `--no-warmup` | `PIPER_DISABLE_WARMUP=1` |
| 失敗時挙動 | `Result::Err` → 呼出側 | try-catch → warn | try-catch → warn | try-except → warn |
