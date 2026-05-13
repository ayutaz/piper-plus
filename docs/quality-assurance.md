# 品質保証 (QA) 体制

piper-plus の現状の自動化・テスト・CI 構成をまとめたリファレンス。
PR を出す前、もしくは新ランタイムを追加するときに「どこに gate があり、何を満たせば merge できるか」を一目で把握するためのドキュメント。

> **Snapshot date:** 2026-05-13  (調査時点の `dev` ブランチ。workflow 数や test 数は時間とともに変動する)

---

## 1. 全体像 — 7 層の品質ゲート

piper-plus はローカル commit から release publish まで、7 層構造の gate で品質を担保している。
各層は「同じ違反を後段でも捕まえる」ように二重化されており、PR #401 のような format drift の再発を防ぐ。

| 層 | 実行タイミング | 主な責務 |
|----|----------------|----------|
| **L1: pre-commit** | `git commit` 時 (ローカル) | auto-fix + 衛生チェック + 同期 gate |
| **L2: Lint** | PR / push | ruff / clippy / dotnet format / clang-tidy / actionlint |
| **L3: Test** | PR / push | 各ランタイムの unit / integration / golden parity |
| **L4: Type** | PR / push | mypy (Python) |
| **L5: Sync** | PR / push | byte-for-byte mirror + forward-compat + meta-test |
| **L6: Security** | PR + weekly | pip/cargo/npm/govulncheck/nuget-audit + Trivy + CodeQL + secret-scan |
| **L7: Release** | tag push | tag ↔ package version 検証 + multi-platform build |

---

## 2. L1 — pre-commit hooks

clone 直後の必須セットアップ:

```bash
pip install pre-commit
pre-commit install      # .git/hooks/pre-commit を生成
```

> **未 install 検出:** `pre-commit.yml` workflow が PR で同じ hook を再実行するため、install 忘れても CI 段階で必ず捕捉される。

### 2.1 Auto-fix される項目

| Hook | 対象 |
|------|------|
| `ruff` (v0.15.12) | Python lint + auto-fix |
| `ruff-format` | Python format |
| `cargo-fmt` | Rust (`src/rust`) |
| `dotnet-format` | C# (CI のみ、ローカル skip 可) |
| `trailing-whitespace` | 全テキスト (Markdown 強制改行の 2 スペース + LF は除外) |
| `end-of-file-fixer` / `mixed-line-ending` | LF 統一 (`.bat`/`.ps1`/`.cmd` 除外) |

### 2.2 検出のみ

- **構文 / 衛生:** `check-yaml`, `check-json`, `check-toml`, `check-merge-conflict`, `check-added-large-files` (2048KB)
- **秘密検出:** `detect-private-key`, `gitleaks` (v8.21.2)
- **型 / 静的解析:** `mypy-g2p`, `cargo clippy -D warnings`, `go vet`, `golangci-lint`, `gofumpt`
- **Lint:** `markdownlint-cli2`, `codespell`, `editorconfig-checker`, `validate-pyproject`, `hadolint` (`docker/` 限定)
- **オプション:** `ktlint`, `swiftformat`, `taplo`

### 2.3 クロスランタイム同期 gate

| Hook | 保証内容 |
|------|----------|
| `pua-cross-runtime-consistency` | PUA テーブル 7 copy + 6 fixture byte 一致 |
| `pua-fixture-drift` | fixture 自動再生成検出 |
| `loanword-consistency` | ZH-EN loanword 10 mirror + 8 fixture byte 一致 |
| `loanword-forward-compat` | `schema_version: 2` 未来フィールド受理 |
| `ruff-version-sync` | 6 箇所 ruff pin 一致 (PR #401 再発防止) |
| `dictionary-consistency` | OpenJTalk 辞書 → WASM asset 同期 |
| `ort-version-sync` | ORT version pin (cmake + workflow + workspace) |
| `voice-catalog-parity` | 音声カタログ 5 runtime mirror |
| `action-pin-gate` | GitHub Actions sliding-tag (`@v3` 等) 検出 |
| `language-id-map-contract` | 言語 ID マップ 6 runtime 同期 |

### 2.4 スキップ方法

```bash
git commit --no-verify              # 全 hook bypass (CI で必ず再検出)
SKIP=cargo-clippy git commit ...    # 特定 hook のみ除外
```

> `--no-verify` は CLAUDE.md / プロジェクトルールで原則禁止。CI fail を後追いで直すサイクルが PR #401 で2回繰り返した。

---

## 3. L2-L7 — GitHub Actions CI

70 ワークフローを 7 カテゴリに分類。

### 3.1 マスターゲート: `ci.yml`

```text
changes (paths-filter)
    ├→ cpp-tests          (3 OS × Release+Debug, reusable)
    ├→ csharp-tests       (3 OS × dotnet 10.0)
    ├→ csharp-build       (6 RID matrix, cross-compile)
    ├→ python-tests       (Ubuntu, Python 3.11)
    ├→ rust-tests         (2 OS, naist-jdic feature)
    ├→ npm-package-tests  (WASM, openjtalk-web)
    └→ lint               (Python ruff)
        → ci-required     (all-success gate; branch protection から参照)
```

paths-filter で変更ファイルに応じて該当 runtime のみ実行 → 平均 CI 時間を抑制。

### 3.2 主要 workflow 一覧

| Workflow | Trigger | 責務 |
|----------|---------|------|
| `ci.yml` | push/PR (dev) | マスター gate (6 runtime) |
| `python-tests.yml` | workflow_call, PR/push | Python 3.11 + coverage |
| `rust-tests.yml` | workflow_call, PR/push | cargo test + clippy + rustfmt + naist-jdic |
| `csharp-ci.yml` | PR/push | dotnet 10.0 build/test + XPlat coverage |
| `go-ci.yml` | PR/push | Go unit + integration |
| `cpp-tests.yml` | PR (限定 path) | ASAN/UBSAN dispatch, C API ABI break 検出, iOS toolchain smoke |
| `wasm-build.yml` | PR/push | WASM ビルド + vitest |
| `kotlin-g2p-ci.yml` | PR/push | native ビルド + 3 ABI エミュレータ (~15-30分) |
| `swift-g2p-ci.yml` | PR/push | Swift G2P テスト (macOS 上で local xcframework ビルド + `swift test`) |
| `python-lint.yml` | PR/push | ruff 0.15.12 check + format |
| `pre-commit.yml` | PR | 全 hook 再実行 (35分 timeout) |
| `actionlint.yml` | PR | GitHub Actions 構文検証 |
| `zh-en-loanword-sync.yml` | PR/push | 9 copy + 8 fixture byte 一致 + forward-compat + meta-test |
| `pua-consistency.yml` | PR/push | 7 runtime + 4 不変条件 |
| `ruff-version-sync.yml` | PR/push | 6 箇所 pin 一致 |
| `parity-hub.yml` | PR (dev) | 7 parity check (CLI flag, language-id, ORT, SSML, splitter, voice catalog) |
| `contract-gates-extended.yml` | PR (dev) | 6 contract (audio-format, ort-provider, streaming-api, swift-g2p, pt-dialect, speaker-encoder) |
| `timing-parity.yml` | PR | phoneme timing 4 runtime 一致 |
| `security-audit.yml` | weekly + PR | pip/cargo/npm/govulncheck/nuget-audit + Trivy |
| `codeql.yml` | PR + schedule | static analysis |
| `dependency-review.yml` | PR | ライセンス + High 以上 CVE で fail |
| `secret-scan.yml` | PR | secret 検出 |
| `sbom.yml` | release | SBOM 生成 |
| `public-api-diff.yml` | PR | C API public header の ABI break 検出 |
| `npm-publish.yml` | `npm-v*` tag | openjtalk-web → npm (version 検証) |
| `g2p-rust-publish.yml` | `rust-g2p-v*` tag | piper-plus-g2p → crates.io |
| `g2p-go-publish.yml` | tag | Go module publish |
| `release-shared-lib.yml` | `v*` tag / dispatch | Linux/macOS/iOS/Android shared lib build → GH Release (iOS は xcframework, SPM 対応) |
| `release-kotlin-g2p.yml` | tag | Maven Central publish |
| `deploy-huggingface.yml` | release | HF Hub publish |

---

## 4. L3 — テストスイート

合計 **~620 テストファイル** + 7 ランタイムが共有する golden fixture (`tests/fixtures/g2p/phoneme_test_cases.json`)。

| Runtime | ファイル数 | 主なカバー領域 | CI workflow |
|---------|------------|----------------|-------------|
| **Python** | ~330 | G2P 全 8 言語, ONNX export, VITS, 多言語推論, custom dict, golden | `python-tests`, `g2p-python-ci`, `g2p-cross-platform-ci` |
| **C# (xUnit v3)** | 78 | 言語別 G2P, ORT, custom dict, CLI integration | `csharp-ci`, `g2p-cross-platform-ci` |
| **Rust (cargo)** | 37 | G2P golden, ORT/short-text contract, SSML attack, timing parity, speaker embedding E2E | `rust-tests`, `g2p-rust-ci`, `g2p-cross-platform-ci` |
| **Go** | 53 | engine, ORT contract, streaming stress, timing parity, ZH-EN loanword | `go-ci`, `g2p-cross-platform-ci` |
| **WASM/npm (vitest)** | ~70 | G2P 言語別, SSML, golden, custom dict, ZH-EN | `g2p-wasm-ci`, `test-webassembly` |
| **C++** | 42 | PUA 不変式, C API (concurrent JA), SSML attack, OpenJTalk security, speaker encoder E2E | `cpp-tests`, `_build-test-cpp` |
| **Kotlin/Android** | 12 | golden parity (L4), loanword matrix, native JNI | `kotlin-g2p-ci` (native + 3 ABI emulator) |
| **Swift (XCTest)** | 7 (G2P 1,095 行) + 1 (synthesis smoke) | G2P phonemizer, golden, concurrency, edge case, PUA, JSON byte parity, ZH-EN loanword | `swift-g2p-ci` (Package.ci.swift で local xcframework swap → `swift test --filter PiperPlusG2PTests`) |

### 4.1 横断テストパターン

| 種別 | 対象ランタイム | 仕様 / fixture |
|------|----------------|----------------|
| **Golden parity** | Python / Rust / Go / WASM / C# / C++ / Kotlin | `tests/fixtures/g2p/phoneme_test_cases.json` (共有), `token_count_min` + `expected_contains` |
| **Phoneme timing parity** | Python / Rust / Go / C++ | `phoneme-timing-contract.toml` (hop_length/sample_rate × 1000) |
| **ORT session contract** | Rust / Go / C++ / C# | `ort-session-contract.toml` (graph_opt_level, warmup_phoneme_length) |
| **Short-text contract** | Python×2 / Rust / Go / WASM / C# / C++ | `short-text-contract.toml` (Strategy A/B/C) |
| **ZH-EN loanword** | 全 7+ runtime | `zh_en_loanword.json` + fixture |
| **PUA invariants** | 全 7+ runtime | `pua-contract.toml` (4 不変条件) |
| **Custom dict** | Python / Rust / Go / C# / WASM / Kotlin | JSON v1/v2 + TSV |

---

## 5. L5 — 仕様 contract と sync gate

`docs/spec/` 配下に **20 個の宣言的 contract ファイル** を持ち、それぞれに対応する検証スクリプト + CI gate を備える。

### 5.1 Contract 一覧

| Contract | 保証内容 | 影響ランタイム |
|----------|----------|----------------|
| `loanword-mirrors.toml` | ZH-EN loanword 7 runtime + 6 fixture 同期 | Python/Rust×2/Go/C#/WASM/C++/Kotlin/Swift |
| `pua-contract.toml` | PUA 4 不変条件 (canonical 唯一性, inventory, id_map, compat version) | Python/Rust/Go/C#/WASM/JS/C++ |
| `short-text-contract.toml` | Strategy A/B/C (padding, scales, SSML silence) | 7 runtime |
| `text-splitter-contract.toml` | 句点判定・分割ルール | Python/Rust/Go ほか |
| `phoneme-timing-contract.toml` | timing JSON/TSV/SRT 形式 | Python/WASM/Rust/Go/C++/C# |
| `ort-session-contract.toml` | ORT セッション設定 | Python/Rust/C++/C# |
| `ort-provider-contract.toml` | EP matrix (CPU/CUDA/CoreML/NNAPI) | — |
| `ort-version-manifest.toml` | ORT バージョン pin | — |
| `audio-format-contract.toml` | WAV 出力 (22050 Hz, int16, mono) | 8 runtime |
| `pt-dialect-contract.toml` | PT BR/EU 5 差分 | 8 runtime |
| `language-id-map-contract.toml` | 言語 code ↔ language ID | 6 runtime |
| `ssml-contract.toml` | `<speak>/<break>/<prosody>` 解析 | Python/Rust/Go/C#/WASM |
| `streaming-api-contract.toml` | HTTP endpoint 仕様 | Python/FastAPI |
| `swift-g2p-contract.toml` | Swift FFI binding | Swift |
| `speaker-encoder-contract.md` | 256 次元 L2 正規化 | 全 runtime |
| `model-sha256-manifest.toml` | 学習済みモデル SHA256 | — |
| `release-versions.toml` | runtime 版番号同期 | — |
| `dictionary-mirrors.toml` | OpenJTalk カスタム辞書 mirror | WASM |
| `inference-input-contract.toml` | 推論入力スキーマ | — |
| `onnx-export-contract.toml` | ONNX エクスポート仕様 | Python |

### 5.2 Canonical → Mirror フロー (例: ZH-EN loanword)

```text
[Python Canonical]
    ↓
zh_en_loanword.json  (src/python/g2p/piper_plus_g2p/data/)
    ↓
[SHA256 mirror to ...]
    ├─ src/python_run/piper/phonemize/data/      (Python runtime)
    ├─ src/rust/piper-{plus-g2p,core}/data/      (Rust ×2 crate)
    ├─ src/go/phonemize/data/
    ├─ src/csharp/PiperPlus.Core/Phonemize/Data/
    ├─ src/wasm/g2p/data/
    ├─ src/cpp/data/
    ├─ android/.../assets/                       (Kotlin AAR)
    └─ Sources/PiperPlusG2P/Resources/           (Swift SPM)
        + 6 fixture mirror
    ↓
[CI Gate] scripts/check_loanword_consistency.py
    ├─ Schema validation (JSON structure)
    ├─ Byte-for-byte hash check (9 + 8)
    ├─ Forward-compat (schema_version: 2 accept)
    └─ Meta-test (drift detection)
```

### 5.3 Skill 化済みのローカル検証

| Skill | 内容 |
|-------|------|
| `/check-loanword` | 7 copy + 6 fixture, schema + forward-compat |
| `/check-pua` | 4 不変条件 + fixture drift |
| `/check-pr-ready` | PR 提出前の最終チェック |

---

## 6. L6 — Security

| Gate | 実行 | 内容 |
|------|------|------|
| `dependency-review.yml` | PR | 新規依存のライセンス + High 以上 CVE で fail |
| `pip-audit` | PR (warning) + weekly (fail) | Python 脆弱性 (PR 時は `continue-on-error`、weekly で厳密) |
| `cargo-audit` | weekly + push | Rust 脆弱性 |
| `npm-audit` | weekly | npm 脆弱性 |
| `govulncheck` | weekly | Go 脆弱性 |
| `nuget-audit` | weekly | .NET 脆弱性 |
| `trivy` | weekly | Docker image スキャン |
| `codeql.yml` | PR + schedule | static analysis |
| `secret-scan.yml` + `gitleaks` (hook) | PR + commit | 秘密検出 (二層) |
| `sbom.yml` | release | SBOM 生成 |
| `public-api-diff.yml` | PR | C API ABI break 検出 |

---

## 7. L7 — Release

| Tag pattern | Workflow | publish 先 |
|-------------|----------|------------|
| `v*` | `release-shared-lib.yml` | GitHub Release (Linux/macOS/iOS xcframework/Android) |
| `npm-v*` | `npm-publish.yml` | npm (`piper-plus`) |
| `rust-g2p-v*` | `g2p-rust-publish.yml` | crates.io (`piper-plus-g2p`) |
| (Go module tag) | `g2p-go-publish.yml` | Go module |
| (Kotlin tag) | `release-kotlin-g2p.yml` | Maven Central (`io.github.ayutaz:piper-plus-g2p-android`) |
| (release) | `deploy-huggingface.yml` | HF Hub |
| (release) | `release-verify.yml` | tag ↔ package version 一致確認 |

---

## 8. PR を出す前のチェックリスト

```bash
# 1. pre-commit が有効か (clone 直後 1 回)
pre-commit install

# 2. 手動で全 hook 実行
pre-commit run --all-files

# 3. ZH-EN loanword を編集した場合
/check-loanword       # Claude Code skill (推奨)
# または: python scripts/check_loanword_consistency.py

# 4. PUA を編集した場合
/check-pua

# 5. ruff version を bump した場合
python scripts/check_ruff_version_sync.py

# 6. ランタイム別テスト (該当する場合のみ)
uv run pytest src/python_run/tests/
cd src/rust && cargo test
cd src/csharp && dotnet test
cd src/go && go test ./...
cd src/wasm/openjtalk-web && npm test
```

---

## 9. 観点別深掘り調査

> **Note:** 本セクションは時点情報 (Snapshot: 2026-05-13)。実装が進むと陳腐化するため、変更時に併せて更新する。

7 層 gate の現状を 10 観点で深掘り。

### 9.1 テストカバレッジ実測値

| Runtime | 計測機構 | Threshold | 実測値 | CI 自動計測 | Codecov |
|---------|----------|-----------|--------|-------------|---------|
| Python | pytest-cov | 70% | ≥70% (g2p は 80%) | ✓ | ✓ |
| C# | XPlat + reportgenerator | 70% line | line 78.5% / branch 72.2% / method 80.7% | ✓ (Ubuntu のみ) | ✓ |
| Rust | **なし** | — | 不明 | ✗ | — |
| Go | `go tool cover` (Makefile) | — | 不明 | ✗ | — |
| WASM/JS | **なし** | — | 不明 | ✗ | — |
| C++ | lcov/gcov (infra ready) | — | フラグ未 enable | ✓ (空) | ✓ (ready) |

**弱いエリア:**

- Rust: 機能テストは充実だが coverage 数値化なし → tarpaulin / llvm-cov 導入
- Go: `make coverage` 存在だが CI 非統合
- WASM/JS: node --test ベース、JS coverage 計測なし
- C++: CMakeLists.txt の `-fprofile-arcs -ftest-coverage` 未有効化

### 9.2 CI 実行時間とボトルネック

| Workflow | timeout | 実測 | 主因 |
|----------|---------|------|------|
| `docker-build` (cpp-inference) | 240 min | ~120 min | arm64 QEMU + ORT ExternalProject |
| `test-arm64-ml` | 90 min | ~40 min | QEMU emulation |
| `dev-build-all` | 90 min | ~30 min | 15 job 並列 |
| `npm-tests` | 25 min | ~4-5 min | WASM 3 variant 順次 |
| `ci` (master) | 25 min | ~6 min | paths-filter で大半 skip |
| `cpp-tests` | 30 min | ~10 min | ASAN/UBSAN |

**ボトルネック Top 5:**

1. `docker-build` の arm64 QEMU emulation (native 比 2-3 倍)
2. ONNX Runtime SourceForge mirror が cache miss で 20 分+
3. arm64 multilingual Docker buildx
4. WASM 3 variant (multilingual/ja/ja-lite) の順次ビルド
5. C++ ASAN/UBSAN

**改善余地 (低コスト順):** WASM variant 並列ビルド (-15分) / ONNX を GitHub Release proxy に切替 (-5分) / cpp-inference に ccache 導入 (-30分) / cpp-tests split。

**強み:** `dorny/paths-filter` で 9 path 条件で skip 制御、`Swatinem/rust-cache` (20 箇所)、`actions/cache v5` (16 箇所)。

### 9.3 Flaky test

**Retry 設定:** 全ランタイムで **なし** (`pytest-rerunfailures` / `cargo-nextest --retries` / vitest retry いずれも未導入)。Go のみ `-race` 有効、C# は `--blame-hang-timeout 30s`。

**`continue-on-error: true` で握りつぶされている job (30+):**

- `model-quality-gate.yml`: dictionary versions / ORT version drift / model checksums
- `python-tests.yml`: Codecov upload
- `clang-tidy.yml` 5 job (既存ノイズ許容)
- `security-audit.yml` 2 job (PR 時は warning 化、weekly で厳密)

**Timing-sensitive テスト (race 高リスク):**

| ファイル | 行 | パターン | リスク |
|----------|-----|----------|--------|
| `test_training_integration.py` | 113/118/166/308 | `time.sleep(0.3/0.2/2)` + `threading.Event()` | 🔴 高 |
| `test_training_manager.py` | 313 | `time.sleep(0.1)` | 🟡 中 |
| `test_voice_g2p_parallel.py` | — | `time.sleep(0.05)` | 🟡 中 |

**推奨:** P0 = `test_training_integration.py` を `multiprocessing.Event` ベースに修正 / P1 = `pytest-rerunfailures` 導入 + `@pytest.mark.flaky(reruns=2)`。

### 9.4 依存管理 (Dependabot)

| Ecosystem | Schedule | Group | Major ignore | 特記 |
|-----------|----------|-------|--------------|------|
| github-actions | 月次 | gh-actions | ✓ | — |
| uv (Python) | 月次 | python-uv-workspace | ✓ | root `uv.lock` が 3 workspace member を統括 |
| cargo | 月次 | cargo | ✓ | — |
| npm ×2 | 月次 | npm-openjtalk-web / npm-g2p | ✓ | `^` pinning |
| gomod | 月次 | gomod | ✓ | **`onnxruntime_go` minor 手動 ignore** (Issue #372) |
| gradle | 月次 | gradle | ✓ | — |
| swift | 月次 | swift | ✓ | — |
| docker ×3 | 月次 | docker-* | ✓ | **python / nvidia/cuda minor 手動 ignore** |

**既知 drift リスク:** ruff version 6 箇所同期 (gate あり) / ORT version Go frozen / uv-workspace PR の lock 遅延 (PR #418 で部分解決) / Python・CUDA base image minor は手動判断。

### 9.5 パフォーマンス回帰検出

**ベンチマークスクリプト:**

- `scripts/benchmark.py` — ONNX 推論 (RTF / Latency P50 / メモリ / モデルサイズ)
- `scripts/benchmark_streaming_comparison.py` — streaming vs non-streaming
- `tools/benchmark/generate_samples.py` + `compute_metrics.py` — MOS 用 (RMS/peak/silence/UTMOS)
- `tools/benchmark/issue-383/` — MB-iSTFT ベースライン (Rust/Go/C# 並列化効果)

**CI 自動実行:** `tools/benchmark/test_benchmark.py` のみ。実機 RTF/Latency 計測は手動。

**ベースライン管理:** issue-383 配下に JSON 結果を手動 commit。自動差分検出なし。

**穴:**

1. Rust/Go/C++/C# ランタイムの RTF 継続計測 (issue-383 1 回のみ)
2. PESQ / STOI 未実装
3. 推論ループ内ピークメモリ
4. cold cache RTF の自動追跡 gate
5. WASM / iOS パフォーマンス計測スクリプト無し
6. Criterion (Rust) / github-action-benchmark 統合無し

### 9.6 ドキュメント整合性

**結論: critical drift なし。**

| Runtime | CLAUDE.md | 実 manifest | 一致 |
|---------|-----------|-------------|------|
| Python | 1.12.0 | VERSION: 1.12.0 | ✓ |
| C# | 0.3.0 | `PiperPlus.Core.csproj` | ✓ |
| Rust | 0.4.0 | `src/rust/Cargo.toml` | ✓ |
| JS/WASM | 0.6.0 | `package.json` | ✓ |
| iOS SPM | 1.13.0+ (M4) | `Package.swift: 1.13.0` | ✓ |

`docs/` 配下 40 参照すべて存在 (リンク切れ 0)。多言語 README EN/ZH/FR/KO/ES/PT/DE/RU/SV/HI/JA 全 11 言語。CHANGELOG は v1.12.0 リリース後 50 commits を `[Unreleased]` セクションに継続追記中。

**微弱な点:** `docs/spec/` 20+ contract ファイルの参照度が低く、CLAUDE.md「実装済み機能」表に明示反映されていない。

### 9.7 PR / Issue テンプレート

**整備済み:**

- `.github/pull_request_template.md` (Summary / Affected Components / Type / Test Plan / Checklist)
- Issue: `bug_report.yml`, `feature_request.yml`, `model-request.yml` (日本語), `model-submission.yml` (日本語、voices.json entry まで)
- `config.yml` で Discussions + CONTRIBUTING_MODELS.md にリンク

**抜けている定型:**

1. **CODEOWNERS** ✗ — 7 ランタイムでの auto-reviewer 機会未活用
2. **release-drafter** ✗ — リリースノート手動
3. **Stale Issue Closer** ✗
4. **PR Size Labeler** ✗
5. **Welcome Bot** ✗
6. **Semantic PR title check** ✗

### 9.8 CI 観測性 (Observability)

| カテゴリ | 状態 | 詳細 |
|----------|------|------|
| Artifact 収集 | ○ | `actions/upload-artifact v7.0.1`、test-results / htmlcov を 7-30 日保管 |
| Test Report 形式 | △ | .NET TRX ✓ / pytest coverage.xml ✓ / vitest ✗ |
| Test Reporter Action | ✗ | `dorny/test-reporter` 未導入 → GitHub Checks tab に集約されていない |
| Coverage 集約 | ○ | `codecov/codecov-action v5.5.4` で Python/Rust/Go/C# を統合 |
| SARIF | ○ | CodeQL + trivy で security-events 書き込み |
| Slack/Discord 通知 | ✗ | webhook 通知なし |
| CI Badge | ○ | README に `ci.yml` badge |
| Pages dashboard | △ | WebAssembly demo は gh-pages 配置、test dashboard なし |

### 9.9 セキュリティ posture

| 項目 | 状態 | 備考 |
|------|------|------|
| `SECURITY.md` | ○ | 報告窓口、SLA (初期 72h / triage 30d)、サポートバージョン |
| CodeQL | ○ | 最小権限 (`actions: read / contents: read / security-events: write`) |
| Secret Scan (gitleaks) | ○ | PR / push / 月次 schedule、`.gitleaks.toml` allowlist |
| Dependabot | ○ | 月次、major ignore、PR 上限 5 |
| **Action Pin Gate** | ○ | カスタム `scripts/check_action_pins.py` + `baseline.txt` (grandfathered 39 件) |
| SLSA Provenance | ○ | `attest-build-provenance v3.2.0` (tag push 時) |
| SBOM | ○ | SPDX + CycloneDX、リポジトリ全体 + 言語別 |
| permissions 最小化 | ◎ | 全 workflow で明示、workflow + job レベル二重 |
| dependency-review | ○ | `v4.9.0`、PR 時新規依存チェック |
| OpenSSF Scorecard | ✗ | **未導入** |

**Sliding-tag 残存:** `DavidAnson/markdownlint-cli2-action@v17` (markdownlint.yml) → `@v17.x.x` または SHA pin に更新推奨。

**Supply chain attestation:** PyPI: `gh-action-pypi-publish@release/v1` で SLSA provenance 自動 attach / npm / crates.io: `attest-build-provenance` 使用 / release artifact に SBOM 同梱。

**総評:** 多言語ポリglot リポジトリとして業界平均超 (Action pin gate / SLSA / 多重 SBOM は特筆)。

### 9.10 エコシステム認知度・ユーザビリティ

#### パッケージ publish 状況

| Registry | Package | 最新版 | 状態 |
|----------|---------|--------|------|
| PyPI | `piper-plus` | 1.12.0 | ✅ 連動 |
| NuGet | `PiperPlus.Core` / `PiperPlus.Cli` | 0.3.0 | ⚠ Python と乖離 |
| crates.io | `piper-plus-g2p` / `piper-plus-cli` | 0.4.0 | ✅ |
| npm | `piper-plus` / `@piper-plus/g2p` | 0.6.0 | ⚠ 遅れ気味 |
| Maven Central | `io.github.ayutaz:piper-plus-g2p-android` | 1.0.0 | ✅ 新規 (2026-05) |
| HuggingFace | `ayousanz/piper-plus-*` | 複数 | ✅ |

#### Discoverability スコア

| 項目 | スコア | コメント |
|------|--------|----------|
| Badge | 5/5 | CI/PyPI/License/HF/WASM |
| README 品質 | 4/5 | 11 言語対応、ベンチマーク・機能表充実。**npm/NuGet/Go version badge は不足** |
| Examples | 3/5 | C API / iOS Swift / Dart / Godot / Android / Swift あり。**Python/Rust/Go/C# 公式サンプル無** |
| Demo / Integration | 5/5 | WebAssembly demo + HF Spaces + Home Assistant / Open WebUI / Unity uPiper |
| Blog / Release Notes | 2/5 | CHANGELOG 充実だが個人ブログ 3 記事のみ、英語記事無し、Releases ページ未活用 |

---

## 10. 統合改善 Top 10

| # | 改善 | 観点 | コスト | 効果 |
|---|------|------|--------|------|
| 1 | **Kotlin / Swift CI を `ci.yml` の `ci-required` ゲートに統合** (現状は個別 workflow) | 9.2 / 9.7 | 中 | 高 |
| 2 | CODEOWNERS 追加 (ランタイム別 reviewer) | 9.7 | 低 | 中 |
| 3 | Version Sync Dashboard / GitHub Releases 自動化 | 9.10 | 低 | 高 |
| 4 | OpenSSF Scorecard workflow 追加 | 9.9 | 低 | 中 |
| 5 | `test_training_integration.py` の race 修正 | 9.3 | 中 | 中 |
| 6 | Rust tarpaulin / Go CI coverage 統合 | 9.1 | 中 | 中 |
| 7 | WASM variant 並列ビルド + ccache | 9.2 | 低 | 中 (-15〜45 分) |
| 8 | RTF 回帰検出 gate (criterion + benchmark action) | 9.5 | 高 | 高 |
| 9 | `dorny/test-reporter` で Checks tab 可視化 | 9.8 | 低 | 中 |
| 10 | release-drafter で release note 自動化 | 9.7, 9.10 | 低 | 中 |

**Python 3.11 単一バージョン** / **`csharp-ci.yml` / `go-ci.yml` / `swift-g2p-ci.yml` が `workflow_call` 非対応** / **PR 時の `pip-audit` が `continue-on-error`** も既知の改善候補。

> **2026-05-13 訂正:** 当初 #1 に「Swift G2P テスト実装 (空)」を挙げていたが、誤調査だった。実際には `tests/PiperPlusG2PTests/` (小文字) に 7 ファイル / 1,095 行の XCTest が実装済みで、`swift-g2p-ci.yml` が `Package.ci.swift` を経由して macOS 上で実行している。#1 は Kotlin/Swift CI のマスター gate 統合に差し替えた。

---

## 11. 関連ドキュメント

- [CLAUDE.md](../CLAUDE.md) — 開発環境セットアップ、ruff version pin の同期ルール
- [docs/spec/](spec/) — 各 contract ファイル
- [scripts/](../scripts/) — 検証スクリプト群 (`check_*.py`)
- [.pre-commit-config.yaml](../.pre-commit-config.yaml) — hook 定義
- [.github/workflows/](../.github/workflows/) — CI workflow 定義
- [.claude/skills/](../.claude/skills/) — Skill 定義 (`check-loanword`, `check-pua`)
