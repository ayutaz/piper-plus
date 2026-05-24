# Changelog

All notable changes to piper-plus will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

<!--
  Breaking changes must be listed under `### Breaking` and each entry must
  include at least one `[label](docs/migration/v<X>-to-v<Y>.md#anchor)`
  link. See `docs/migration/README.md` for the anchor slug rules.
  `scripts/check_migration_xref.py` (workflow `Migration Guide Lint`)
  enforces this automatically.
-->

## [1.13.0] - 2026-06-13

### Breaking

#### Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一 (Issue #527)

Docker 全 image + CI workflow + ドキュメントを **Python 3.13 + CUDA 12.8 + Ubuntu 24.04** で完全統一する fully-aligned 戦略 migration。 新 GPU (T4 / RTX 6000 Ada / RTX 5090) サポート + TF32 / bf16-mixed default 化。

- **Default Docker images now require CUDA 12.8 + host NVIDIA driver R570+**
  ([`docker/python-train/Dockerfile`](docker/python-train/Dockerfile),
  [`docker/python-inference/Dockerfile`](docker/python-inference/Dockerfile)).
  Base image bumped from `nvidia/cuda:12.6.3-...-ubuntu22.04` to
  `nvidia/cuda:12.8.1-...-ubuntu24.04`. Hosts running NVIDIA driver R525
  (12.6) or older will fail to start the new images. See
  [Docker base image upgrade](docs/migration/v1.12-to-v1.13.md#docker-base-image-upgrade).
- **Default Python interpreter inside Docker images is 3.13** (was 3.11).
  `requires-python = ">=3.11"` is unchanged; PyPI installs on Python
  3.11/3.12 remain supported. Only the Docker image default has shifted.
  See [Python 3.13 default](docs/migration/v1.12-to-v1.13.md#python-313-default).
- **PyTorch wheel bumped from 2.2.1+cu121 to 2.11.0+cu128** in the
  training image. Required for RTX 5090 (Blackwell sm_120) support.
  See [PyTorch upgrade](docs/migration/v1.12-to-v1.13.md#pytorch-upgrade).
- **Loading checkpoints generated with torch 2.2 is no longer supported**
  in v1.13 training images. Existing ONNX models continue to work for
  inference. Users who need to continue fine-tuning from a torch-2.2
  checkpoint must stay on the v1.12 Docker image tag (preserved
  indefinitely in registry).
  See [Checkpoint resume non-support](docs/migration/v1.12-to-v1.13.md#checkpoint-resume-non-support).
- **distroless final images bumped from debian12 to debian13**
  ([`docker/python-inference/Dockerfile.cpu.distroless`](docker/python-inference/Dockerfile.cpu.distroless),
  [`docker/webui/Dockerfile.distroless`](docker/webui/Dockerfile.distroless)).
  Internal Python paths shifted from `/usr/local/lib/python3.11` to
  `/usr/local/lib/python3.13`.
  See [distroless image upgrade](docs/migration/v1.12-to-v1.13.md#distroless-image-upgrade).
- **TF32 is now enabled by default in training** via
  `torch.backends.cuda.matmul.allow_tf32 = True` and
  `torch.backends.cudnn.allow_tf32 = True`. This is a noop on sm_75 and
  older GPUs (T4 included). For Ada Lovelace / Blackwell, matmul/conv
  are ~1.3-1.5x faster but lose bit-exact reproducibility vs strict FP32.
  See [TF32 default ON](docs/migration/v1.12-to-v1.13.md#tf32-default-on).
- **Canonical training precision in CLAUDE.md Template A/B is now
  `--precision bf16-mixed`** (was `--precision 32-true`). The `32-true`
  option remains available for legacy V100 compatibility / strict
  numerical reproducibility, but is no longer the recommended default.
  New GPU (Ada 6000 / RTX 5090) users get BF16 Tensor Core acceleration
  by default.
  See [bf16-mixed Template default](docs/migration/v1.12-to-v1.13.md#bf16-mixed-template-default).

### Changed

#### Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一 (Issue #527)

- **CI workflow**: 20 個の workflow で `python-version` を `'3.11'` から
  `'3.13'` に bump (matrix workflow `python-tests` / `g2p-python-ci` /
  `build-phonemize-wheels` は 3.11/3.12/3.13 網羅で据置)。
- **Library floor pins**: 17 library の floor drift を root と member で統一
  (`scipy>=1.17.1` / `pytorch-lightning>=2.4.0` / `transformers>=4.50.0`
  / `onnxruntime>=1.26.0` / `numba>=0.61.0` 等、 DR-002)。
- **CLAUDE.md Template A/B**: `--precision 32-true` → `--precision bf16-mixed`、
  `--no-wavlm` を削除 (Ada/Blackwell では WavLM 有効が canonical)。
- **docs/guides/training/**: V100 言及を新 GPU (T4 / Ada 6000 / RTX 5090)
  前提に置換。

### Added

#### Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一 (Issue #527)

- **`docs/reference/python-313/`**: Issue #527 設計ドキュメント群
  (`requirements.md` / `specifications.md` / `milestones.md` /
  `open-questions.md` / `README.md`、 計 5 文書 約 3700 行)。
- **`docs/migration/v1.12-to-v1.13.md`**: 本マイグレーションガイド。
- **`torch.backends.cuda.matmul.allow_tf32 = True`** in
  [`src/python/piper_train/__main__.py`](src/python/piper_train/__main__.py)
  (DR-007、 Ada/Blackwell で TF32 Tensor Core 透過適用)。

#### G2P 文単位並列化 + ORT 推論オーバーラップ (Issue #383)

G2P (音素化) を文単位で並列化し、全 5 ランタイム (Python/Rust/C#/Go/C++) に展開。Python は ORT 推論との pipeline 化で長文の TTFB を短縮 (代表値: Go N=20 で約 3.96x、Python で約 -19%)。新 env var `PIPER_G2P_PARALLELISM` で並列度を全ランタイム共通制御でき、`PIPER_G2P_PARALLELISM=1` で逐次の旧挙動に戻せる (Breaking なし)。PR #403。

#### 2 image distroless trial Dockerfiles + CI (webui / cpp-inference)

PR #523 (python-inference) で確立した distroless trial pattern を、 deploy 検証要件のない 2 image に bundle 適用。 既存 `Dockerfile` / `docker-compose` / 関連 CI は **不変更で残し**、 並行 `Dockerfile.distroless` を 2 枚追加して build / size A/B / smoke test を CI で実証する scope。 promotion (canonical 置換) は image 別に別 PR。

- **`docker/webui/Dockerfile.distroless`** (Python + Gradio): multi-stage、 builder = `python:3.11-slim-trixie`、 final = `gcr.io/distroless/python3-debian12`。 PR #523 と同型 Debian-glibc ABI 統一、 `/usr/bin/python3` 絶対パス起動、 arch-neutral lib staging。 site-packages + NLTK data を builder から COPY、 ENTRYPOINT は `python3 /app/app.py` (canonical の `entrypoint.sh` は shell なしのため使えず、 実体は同等の単一行 exec)、 明示的 `USER 65532` を Trivy DS-0002 対応
- **`docker/cpp-inference/Dockerfile.distroless`** (C++ runtime): builder = `debian:12-slim` (canonical の ubuntu:24.04 から変更、 distroless/cc-debian12 = Debian 12 glibc 2.36 との ABI 一致のため)、 final = `gcr.io/distroless/cc-debian12`。 piper binary + ONNX Runtime / libgomp shared lib + OpenJTalk 辞書を COPY。 libgomp は arch-neutral staging で bring-over。 canonical の `entrypoint.sh` (shell) → ENTRYPOINT に直接 `/usr/local/bin/piper` 化
- **新規 CI workflow** (`.github/workflows/docker-distroless-trial.yml`): PR base + workflow_dispatch、 2 image matrix で build (canonical baseline + distroless trial) → size 比較 → smoke (webui: Gradio import / cpp-inference: piper --version) → aggregate sticky comment 投稿
- **既存 workflow chain 統合**: `hadolint.yml` matrix に 2 Dockerfile 追加、 `trivy-container-scan.yml` matrix に 2 target 追加、 `docker-build.yml` の `build-distroless-trials` matrix job (multi-arch linux/arm64 + linux/amd64) に統合 (PR #523 で導入した python-inference distroless と合わせて 3 image trial が 1 job matrix で並走)
- **hadolint config 拡張**: `.hadolint.yaml` の `trustedRegistries` に `cgr.dev` を allow-list 追加 (将来の Wolfi 採用に備えた forward-compat、 本 PR では未使用)
- **promotion path**: 各 trial で build + size 効果が確認できた後、 image 別に canonical 置換 PR を作成 (webui は webui-test.yml smoke、 cpp-inference は container test gate での実モデル E2E が前提)
- **cpp-dev distroless は scope-out 確定** (旧 T-016、 PR #526 で確定): wolfi-base trial で OpenJTalk / mecab tooling chain が Debian apt package 前提のため Wolfi で source build を full chain で組むには iconv / libtool / gettext 等の missing package 連鎖が判明。 加えて cpp-dev は dev image (production 推論経路なし、 cmake / clang / gdb を final stage に同居必須) で distroless 哲学と本質的に不整合、 大目的 (production image の CVE 80% / size 50% 削減) への寄与が限定的。 PR #524 で webui + cpp-inference trial bundle により spike 目的 (multi-stage pattern / glibc ABI 整合 / entrypoint 移植) は達成済のため、 M3 distroless は 5 image → 4 image に scope 縮小し ticket file 削除

#### `python-inference` distroless trial Dockerfile + CI (`Dockerfile.cpu.distroless`)

`docker/python-inference/` の distroless 化を derisk する **trial PR**。 既存 `Dockerfile.cpu` と `docker-compose.yml` / `.github/workflows/deploy-huggingface.yml` (HF Space deploy 経路) は **不変更で残し**、 並行 `Dockerfile.cpu.distroless` を新設して build / size / smoke test を CI で実証する scope。

- **新規 Dockerfile** (`docker/python-inference/Dockerfile.cpu.distroless`): multi-stage build (builder = `python:3.11-slim-trixie`、 final = `gcr.io/distroless/python3-debian12`)。 base image は Debian-glibc baseline 統一で選定: builder と final が同じ glibc ABI を共有するため、 onnxruntime の pre-built C 拡張 (`onnxruntime_pybind11_state.so`) と soundfile の libsndfile dlopen が byte-for-byte 一致で resolve する。 Wolfi 系 (`cgr.dev/chainguard/python`) は当初候補だったが、 Wolfi の glibc / Python build が Debian と別 ABI で onnxruntime が import 不可と判明したため Debian baseline に確定。 builder で `piper_plus_g2p[all]` + `piper_train[inference]` + Gradio WebUI requirements + NLTK data を install、 final へ Python site-packages + `/usr/local/bin/uvicorn` + 必要な shared libs (libsndfile / libgomp / libFLAC / libvorbis / libogg / libopus / libmpg123) を COPY
- **新規 CI workflow** (`.github/workflows/python-inference-distroless-trial.yml`): PR base + workflow_dispatch、 canonical `Dockerfile.cpu` を baseline として build、 distroless trial を build、 image size を比較、 import smoke test 2 種 (ONNX Runtime / piper_train / FastAPI / soundfile import 確認) を実行、 PR コメントに distroless trial report を sticky 投稿
- **scope 限定**: linux/amd64 single-arch CI build のみ (multi-arch は別 PR で buildx)、 `/v1/audio/speech` E2E は CI に ONNX model fixture 配置が前提のため別 PR、 CVE 比較 (Trivy) も canonical 置換 PR 側で実施。 HF Space staging deploy 検証は user 手動 step (Claude Code は実行不可)
- **promotion path**: trial PR で「build 成立 + size 削減効果」 が確認できた後、 別 PR で `Dockerfile.cpu` 自体を置換 (HF Space staging で cold start 検証後)

#### docs/ fenced code blocks の execution gate (`scripts/check_doc_examples.py execute`)

audit gate (`scripts/check_doc_examples.py audit`) で生成した canonical snapshot を入力に、 `executable` category の block を **syntax-validation default** で sandbox 実行する informational tier gate を追加。 加えて `test-flake-retry-contract.toml` の `applies_to` を 4 → 8 runtime に拡張し full scope 化。

- **execute サブモード** (`scripts/doc_examples/executor.py`): bash + python の 2 runner を v1 で実装 (executable scope の 95%+ を担保)。 default は **syntax 検証のみ** (`bash -n` / `python -m py_compile`) で destructive 操作 (`rm` / `curl` 等) を呼ばない。 `--actually-run` 明示時のみ subprocess で実行、 bash は `set -euo pipefail` 注入。 残 4 言語 (rust / csharp / go / wasm) は runner 未登録、 `runner_unsupported` で集計のみ
- **stale audit 検知**: audit JSON の `hash_sha1` と現在の block hash を再計算で比較、 不一致なら `::warning::Audit JSON stale: <file>:<line>` を出力 (block の実行自体は継続)
- **sticky comment 生成**: 「期待値 (audit.totals.executable) vs 実測値」 / outcome 内訳 (pass / fail / timeout / runner_unsupported / runner_missing) / fail 一覧テーブル / stale audit 一覧 を markdown で書き出し (`--sticky-comment`)
- **新規 workflow** (`.github/workflows/doc-examples-gate.yml`): PR base + Tuesday 06:00 UTC schedule + workflow_dispatch、 informational tier (`continue-on-error: true`)、 sticky-pull-request-comment で PR に投稿
- **silent-zero defensive log**: `Collected executable blocks (N=...): bash=A python=B ...` + `Expected from audit.totals.executable=N` を必ず stderr 出力。 N=0 で `::warning::`、 N < expected/2 で `::warning::`
- **8 runtime test flake retry**: `test-flake-retry-contract.toml` の `applies_to` を `[python, rust, go, csharp, wasm, cpp, kotlin, swift]` に拡張、 4 新規 runtime (WASM jest / C++ ctest --repeat / Kotlin gradle test-retry / Swift `swift test -- --test-iterations`) を spec に追加 (status=proposed、 既存 gate の `check_proposed_runtime` で shape validation)
- **Unit tests 26 件追加** (`test_check_doc_examples_execute.py` 13 件 + `test_check_test_flake_retry.py` 既存テスト 8 runtime 対応)
- **実 docs での効果**: syntax-only run で 185 block を validate (165 bash + 20 python)、 既存 docs から **5 件の bash 構文エラー** を検出 (mutation-testing.md / M3-supply-chain.md / T-019/T-020/T-021 SLSA ticket)。 これらは informational tier として sticky comment に記録され、 後続 PR で個別修正候補

#### docs/ fenced code blocks の audit gate (`scripts/check_doc_examples.py audit`)

`docs/` 配下 (~150 markdown) の GFM fenced code blocks を全件抽出し、 3 カテゴリ (executable / needs_placeholder / skip_warranted) に分類する audit 機能を新規実装。 後続の execution gate / blocker 化判定の前提となる canonical 入力 (`tests/fixtures/doc_examples_audit/audit.json`) を生成する。

- **新規 spec**: `docs/spec/doc-examples-contract.toml` で audit 対象 glob / 言語 alias / placeholder 正規表現 / skip directive / 環境依存パターン / silent-zero 防御方針を pin
- **新規モジュール**: `scripts/doc_examples/{extractor,classifier}.py` (markdown-it-py の `commonmark` preset で GFM 三連バッククォート fenced block を抽出、 6 canonical 言語 + 多数の alias を正規化、 placeholder/skip directive/env-dep を deterministic に分類)
- **新規 CLI**: `scripts/check_doc_examples.py audit` (`--config` / `--output` / `--check-snapshot` / `--generated-at` をサポート)。 silent-zero 防御 `Collected blocks (total=N): bash=A python=B ...` を必ず stderr 出力、 total=0 で `::warning::`
- **canonical snapshot**: 現状の audit 結果を `tests/fixtures/doc_examples_audit/audit.json` に commit (464 block: executable 215 / needs_placeholder 2 / skip_warranted 247、 言語別内訳付き、 非 canonical 言語は `unknown` bucket に集約)。 docs 編集で snapshot が drift したら `--check-snapshot` が exit 1
- **既存 `scripts/check_readme_code_examples.py` (シンボル grep) は維持** — 「シンボル存在 vs 実行可否」 の役割分担を spec contract に明記、 重複なし
- **Unit tests 11 件追加** (extractor / classifier 各カテゴリ / 言語 alias 正規化 / silent-zero / snapshot drift / 実 docs snapshot 一致)

実 docs 内訳 (本 PR snapshot):

| 言語 | executable | needs_placeholder | skip_warranted |
|------|-----------|------------------|----------------|
| bash | 165 | 2 | 24 |
| python | 20 | 0 | 0 |
| rust | 11 | 0 | 0 |
| csharp | 5 | 0 | 0 |
| go | 4 | 0 | 0 |
| wasm | 10 | 0 | 0 |
| `unknown` (非 canonical: json/yaml/text/dockerfile/kotlin/etc) | 0 | 0 | 213 |

#### Spec contract gates: model-sha256-manifest / artifact-retention / test-flake-retry (T-005/T-006/T-008)

5 件の spec sync gate 穴のうち未実装だった 3 件を新規 gate 化、 既存実装 (T-004/T-007) は `[meta].direction` 明文化のみで closeout。 各 gate に silent-zero defensive log を inline 実装し M1 で確立した pattern を踏襲。

- **T-005 model-sha256-manifest gate** (`scripts/check_model_sha256_manifest.py`): `docs/spec/model-sha256-manifest.toml` の 6 model entry が CLAUDE.md 「学習済みモデル」 表と一致するか、 `<computed-on-publish>` placeholder か 64-char lowercase hex SHA256 のいずれかか、 `[meta]` 必須 key (spec_version / canonical_source / hash_algorithm / hash_encoding / update_policy / forward_compat_policy) が揃っているかを検証。 `MAX_KNOWN_SCHEMA_VERSION = 2` で forward-compat (loanword sync gate と同型) を pin
- **T-006 artifact-retention gate** (`scripts/check_artifact_retention.py`): 全 `.github/workflows/*.y*ml` (40 workflow / 63 upload step) の `retention-days:` を抽出し、 `[[categories]]` 許容値 [1, 7, 30, 90] と突合。 同 PR 内で初期 baseline 違反 6 件を sweep (cpp-abi-check/fuzz-smoke 4 件: 14d→30d / cppcheck: 14d→7d / scorecard: 5d→7d / typosquatting-watch: 365d→90d) し `[meta].mode = "fail"` で導入完了
- **T-008 test-flake-retry gate** (`scripts/check_test_flake_retry.py`): 4 runtime (python / rust / go / csharp) のうち `status = "phase-1"`/`"phase-2"` の runtime に pyproject 依存 + `--reruns N` flag が wire-up されているか、 全 runtime の retry 値が `retry_count_max = 2` 不変条件を満たすか、 `[[invariants]]` 3 件 (no-blanket-retry / retry-count-max-2 / ci-only-retry) が削除されていないかを検証
- **direction 明文化 (closeout)**: `release-versions.toml` (post-hoc) と `swift-g2p-contract.toml` (pre-impl) の `[meta].direction` を追加。 これら 2 件は既存 `scripts/check_version_manifest_sync.py` / `scripts/check_swift_g2p_contract.py` が gate 化済み
- **CI 統合**: `.github/workflows/contract-gates-extended.yml` の matrix に 3 contract id (model-sha256-manifest / artifact-retention / test-flake-retry) を追加、 既存 `.pre-commit-config.yaml` に 3 hook 追加 (path filter で fast-path)
- **Unit tests**: 41 件追加 (`tests/scripts/test_check_{model_sha256_manifest,artifact_retention,test_flake_retry}.py`)
- **M1 status 反映**: PR #513 merge を受けて `docs/tickets/{README.md,milestones/M1-foundations.md,tickets/T-00{1,2,3}-*.md}` の Status を 「完了」 + PR #513 を記録

#### Kotlin/Android G2P AAR を Maven Central に公開 (Issue #388)

8 言語マルチリンガル G2P を Android アプリから利用するための **engine-less Kotlin AAR** を新設。Maven coordinates `io.github.ayutaz:piper-plus-g2p-android`。`implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")` 1 行で導入できる。

- **Engine-less C API 拡張**: `piper_plus_g2p_create` / `_phonemize` / `_available_languages` / `_load_custom_dict` / `_set_zh_en_dispatch` / `_is_zh_en_dispatch_enabled` / `_free` の 7 関数を C API に追加 (`src/cpp/piper_plus.h`)。ONNX モデル不要で 8 言語 (ja=0, en=1, zh=2, es=3, fr=4, pt=5, ko=6, sv=7) を phonemize 可能。既存 `piper_plus_phonemize()` と同じ `piper::phonemizeText` を共有するため byte-for-byte 互換 (FR-CAPI-3)。既存 ABI (`PIPER_PLUS_API_VERSION 1`) を破壊しない追加のみ。
- **JNI bridge**: `android/piper-plus-g2p/src/main/cpp/piper_plus_g2p_jni.cpp`。既存 TTS フル AAR (`android/piper-plus/`) と同じ `JNIStringGuard` RAII / `JNI_OnLoad` 例外 GlobalRef キャッシュ / BORROWED ポインタ即 `NewStringUTF` コピーパターンを踏襲
- **Kotlin パブリック API**: `PiperPlusG2p` (`AutoCloseable` + `@Synchronized`) / `PhonemeResult` data class / `PiperPlusG2pException` / `OpenJTalkDictionary` (`fromAssets` / `fromPath`) / `DictionaryDownloader` (`downloadFromHuggingFace` suspend、SHA-256 検証付)
- **Gradle module**: `android/piper-plus-g2p/build.gradle.kts` で vanniktech `gradle-maven-publish-plugin` 0.30.0 + `SonatypeHost.CENTRAL_PORTAL` 採用。3 ABI (arm64-v8a / armeabi-v7a / x86_64)、`-Wl,-z,max-page-size=16384` で 16 KB page size 対応 (Android 15+)、minSdk 24 / compileSdk 35 / Kotlin 2.1.0 / JDK 17。Gradle Managed Devices で Pixel 6 API 34 emulator 自動起動
- **CI 自動テスト 5 層**: `.github/workflows/kotlin-g2p-ci.yml` で L1 (Pure Kotlin unit) / L3 (Android instrumented on Gradle Managed Devices) / L4 (parity 雛形) / L5 (`readelf -lW` で 16 KB align gate + AAR サイズ < 10 MB gate) を全 PR で実行
- **Maven Central 自動公開**: `.github/workflows/release-kotlin-g2p.yml` がタグ `kotlin-g2p-v*` push を検知して GPG in-memory key + Sonatype Central Portal credentials で `publishAndReleaseToMavenCentral` を実行。PR では `publishToMavenLocal` の dry-run のみ
- **辞書配布 3 パターン**: AAR には OpenJTalk 辞書 (~102MB) を同梱せず、(1) App assets バンドル (`OpenJTalkDictionary.fromAssets`)、(2) Play Asset Delivery (`fromPath`)、(3) Runtime DL from Hugging Face Hub (`DictionaryDownloader.downloadFromHuggingFace` + SHA-256 検証) の 3 通りを提供。詳細: `docs/guides/platform/android-g2p-dictionary.md`
- **GTest 26 ケース** (`src/cpp/tests/test_c_api_g2p.cpp`): lifecycle / NULL safety / `available_languages` order / 規則ベース 3 言語 (es/fr/pt) / ZH-EN dispatch toggle / borrowed pointer 寿命 / custom dict
- **L4 byte-for-byte parity**: `tools/generate_g2p_golden.py` で Python `MultilingualPhonemizer` から 70 ケースの IPA 列を pre-compute し `tests/fixtures/g2p/phoneme_test_cases_golden.json` に固定。Kotlin instrumented `PhonemeFixtureParityTest.byte_for_byte_parity_with_python_golden` が strict diff で drift を検知 (FR-CAPI-3 / FR-TEST-1)
- **サンプル Compose アプリ**: `examples/android-g2p-sample/` (8 言語タブ + TextField → phonemize → カード表示)。Gradle composite build で in-repo AAR を直接消費。`.github/workflows/kotlin-g2p-ci.yml` の `sample-app` ジョブで `assembleDebug` を CI gate (AC-10)
- **設計・要件**: `docs/spec/kotlin-g2p-{design,requirements}.md`
- **10 並列エージェント自己監査による 22 件の修正** (2026-05-07):
  - **CI 修正**: NDK install を 4 つの Gradle ジョブ (unit-tests / build-aar / instrumented-tests / sample-app) と release publish に追加 (externalNativeBuild が常に NDK を要求するため、無いと全失敗していた)。`concurrency` block 追加でブランチ重複実行を防止。L4 専用 `parity-golden` ジョブ追加: Linux で eunjeon インストール後に `tools/generate_g2p_golden.py` を再実行し、`tools/compare_g2p_golden.py` で `expected_phonemes` の drift だけを strict 検査 (KO の skip / failed_cases メタデータは platform 固有なので除外)。
  - **L4 default_latin_language の golden 修正**: 既存 golden は `default_latin_language="en"` で全ケース生成していたため PT/ES/FR/SV テキストが英語 G2P 経由で誤った IPA を保持していた (例: `"hola"` → `h ˈ o ʊ l ə` 英語フォニックス)。C API 側 `piper.cpp` は `synthesisConfig.languageId` から `defaultLatin` を選ぶため runtime と divergence。`generate_g2p_golden.py` を per-case `default_latin_language=lang` に修正 + golden を再生成 (`"hola"` → `ˈ o l a` Spanish)。`schema_version: 2` で `failed_cases` / `skipped_ko_cases` を追加。
  - **VERSION_NAME = 1.0.0 統一**: `android/gradle.properties` が `0.1.0` のままだったためタグ push 時に 0.1.0 が public される状態だった。`build.gradle.kts` のフォールバックも合わせて 1.0.0 に。`GROUP=io.github.ayutaz` も明示。
  - **AndroidManifest INTERNET permission 追加**: `DictionaryDownloader` が HF Hub 接続するのに必要だが空 manifest のままだった。consumer apps へ manifest merger 経由で伝播。
  - **DictionaryDownloader セキュリティ強化 (NFR-SEC-2)**: (a) `host` パラメータを **allowlist** (`huggingface.co` / `hf-mirror.com`) に固定 + `https://` 強制、(b) ustar の `prefix` (155B) field を `name` field と連結、(c) symlink/hardlink/device entry を `IOException` で reject、(d) per-entry 64MB / total 256MB の上限ガード (TAR-bomb 対策)、(e) 中間ディレクトリ → `renameTo` でほぼ atomic な extract (.complete marker)、(f) `withContext(Dispatchers.IO)` + `currentCoroutineContext().ensureActive()` で coroutine cancellation 対応。
  - **PiperPlusG2pException に `cause` 引数追加**: 設計書要求の `Exception(message, cause)` に整合。`DictionaryDownloader` などの内部 IOException を chain 可能に。
  - **build.gradle.kts**: `ndkVersion = "26.1.10909125"` pin (再現性 NFR-PUB-1)、`targetSdk = 34` 追加 (Play Store 必須)、vanniktech と `android.publishing { singleVariant }` の二重設定を解消、`org.jetbrains.dokka` plugin を適用 (空 javadoc.jar が Sonatype 品質ゲートで弾かれる対策、FR-DOCS-4)、kotlinx-coroutines-android 依存追加。
  - **Kotlin API 仕様整合**: `OpenJTalkDictionary.path` を `internal val` に降格 (公開 API 表面汚染解消、`absolutePath()` 関数のみ public)、`PhonemeResult.phonemeList` を `Collections.unmodifiableList` でラップ、`version()` に `@Synchronized` 追加 (設計書「全 native 呼び出し同期」充足)、`extractAssetTree` に path traversal 防御 (canonical-path 検査) 追加。
  - **L1 ユニットテスト 5 → 18 件**: `DictionaryDownloaderTest` (host allowlist) / `OpenJTalkDictionaryTest` (`fromPath` / `exists` / `absolutePath`) / `PiperPlusG2pNativeTest` (JNI shape reflection) / `PhonemeResultTest` (immutability) / `PiperPlusG2pExceptionTest` (cause) を追加。
  - **L3 instrumented 拡充**: `OpenJTalkDictionaryInstrumentedTest` で 3 辞書配布パターン (assets / fromPath / Downloader allowlist) と `create(context, dict)` 統合を網羅 (FR-DICT-1 / FR-TEST-4)。`PhonemeFixtureParityTest.byte_for_byte_parity_with_python_golden` を `assumeTrue(false)` silent skip → `AssertionError` に変更し golden 欠落を loud fail に。
  - **release-kotlin-g2p.yml**: SemVer regex を SemVer 2.0.0 §10 準拠 (pre-release **+** build metadata 同時許可)、4 つの publishing secrets の fail-fast 検査追加、workflow_dispatch にも version regex を適用。
  - **ドキュメント整備**: `docs/guides/platform/android-g2p-integration.md` (FR-DOCS-2、新規)、`tools/build-openjtalk-dict-archive.sh` (M6 で参照されていたが未実装だったビルドスクリプト)、`tools/compare_g2p_golden.py` (CI 用 golden diff)、`CONTRIBUTING.md` に `kotlin-g2p-v*` tag 規約と Maven Central リリース順序追加。`piper_plus.h` の `findG2pDictFile` 経路に関する誤解を招く記述を訂正。

- **残作業全消化** (2026-05-07、ユーザー指示「すべてこのブランチで対応」):
  - **L2 (linuxTest) ジョブ追加**: 設計書 §9.2 / AC-3 要求の「JVM JNI smoke on Linux .so」を `kotlin-g2p-ci.yml:linux-jvm-smoke` で実装。Linux x86_64 で `libpiper_plus.so` + `libpiper_plus_g2p_jni.so` をネイティブビルドし、JVM から `System.load` + 主要メソッド呼び出し (nativeCreate / nativeVersion / nativeAvailableLanguages / nativePhonemize) で symbol-resolution / ABI mismatch を catch。L3 emulator より約 10x 高速で fail。
  - **ASan CI ジョブ追加 (NFR-SEC-4)**: `kotlin-g2p-ci.yml:asan-tests` で `libpiper_plus.so` + GTest を `-fsanitize=address` 下でビルド・実行。`test_c_api --gtest_filter='G2p*'` で 23 ケースを leak/UAF/heap-OOB 検出付きで実行。`tests/asan_lsan_suppressions.txt` で ORT / OpenJTalk のプロセス終了時に発火する benign leak のみを suppress (実害ある leak は通過させる)。
  - **8 言語×50 ケース fixture 拡充 (FR-TEST-1)**: `tests/fixtures/g2p/phoneme_test_cases.json` を 81 → 419 ケースに拡充 (en 50 / es 50 / fr 54 / pt 52 / sv 51 / zh 56 / ja 53 / ko 53)。`tools/expand_g2p_fixtures.py` で systematic に追加 (数字 / 句読点 / 長文 / 言語固有 (ñ/ç/å/ö/ü/...) / loanword / 単一 char edge case)。Python golden も再生成 (313 ケース、JA/KO は CI Linux で再生成)。
  - **Gradle wrapper 追加**: `android/gradlew` / `gradlew.bat` / `gradle/wrapper/gradle-wrapper.{jar,properties}` (Gradle 8.11.1) を整備。ローカル開発者の `./gradlew` 体験を担保。`.gitattributes` に `gradlew text eol=lf` / `*.jar binary` を追加し OS 間で line ending が壊れないように pin。

#### ZH-EN code-switching を全 7 ランタイムに展開 (Issue #384)

中国語テキストに混在する英単語 (acronyms / loanwords / per-letter fallback) を米国英語ではなく Mandarin pinyin で発音する機能を、Python (PR #397 で先行リリース) に続いて Rust × 2 crate / Go / C# / WASM / C++ の **5 ランタイムへ byte-for-byte 同期展開**。

- **canonical**: `src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` (acronyms 65 / loanwords 40 / A-Z fallback、131 entries)
- **mirror 7 箇所** + **fixture 6 箇所**: CI gate `ZH-EN Loanword Sync Gate / json-sync` が SHA256 一致を強制 (`scripts/check_loanword_consistency.py` + `/check-loanword` skill)。helper script 自体の挙動を verify する `helper-self-check` job (`--diff` / `--fix` 冪等性) も同 workflow に同居
- **API**: 各ランタイムの `MultilingualPhonemizer` が `[zh,en,zh]` / `[zh,en]` / `[en,zh]` パターンを自動検出し、英語 segment を loanword 経路にディスパッチ。runtime opt-out: `enable_zh_en_dispatch(false)` (Rust) / `SetZhEnDispatch(false)` (Go) / `EnableZhEnDispatch = false` (C#) / `setZhEnDispatch(false)` (WASM)
- **Forward-compatible loader (YELLOW-5)**: 全 7 ランタイム (Python + Rust × 2 / Go / C# / WASM / C++) で `schema_version: 2` の未来フィールドを silent ignore する挙動を pinning test で固定
- **Two-layer model**: コンパイル時 (Cargo feature `chinese` / csproj `<EmbeddedResource>` / Go `//go:embed` / C++ CMake) + ランタイム (default-on opt-out) の二層管理 (TICKET-01 §7 懸念 5)
- **ランタイム test カバレッジ**: Rust × 2 / Go / C# / WASM / C++ + Python の各 ZH-EN test スイートで `phonemize_embedded_english` の lookup priority / forward-compat / dispatch / opt-out / per-token prosody (a1=tone, a2=a3=1) を検証
- **Issue #384 例**: `请打开 GPS` / `我喜欢用 Python 写代码` / `让我用 ChatGPT 写代码` を Python リファレンス test がカバー。各ランタイムの `phonemize_embedded_english` は同 JSON (byte-for-byte 同期) と同 lookup ロジックで動くため Python と等価な IPA 列を返す。設計と運用契約: [`docs/reference/zh-en-loanword/README.md`](docs/reference/zh-en-loanword/README.md)。

##### 既知の制約 / 別 PR フォローアップ予定

本 PR では JSON 同期と各ランタイムへの dispatch wiring を成立させたが、以下の hardening / 拡張は別 PR で取り組む:

- **Cross-runtime IPA parity CI**: `tests/fixtures/g2p/zh_en_loanword_matrix.json` の各 case を全ランタイムに食わせて token 列が一致することを検証する gate (現状は per-runtime に loadable + per-case `expected_token_count` strict check のみ — Python が IPA 列を JSONL で pre-compute して全ランタイムが同じ列を返すか確認する parity job は未実装)。
- **Loader hardening (Tier 1-2 セキュリティガード)**: `MAX_LOANWORD_FILE_SIZE` / `MAX_LOANWORD_ENTRIES` / `MAX_LOANWORD_DEPTH` をユーザー指定 override path 受付経路 (`--zh-en-loanword-dict-paths` 等) に追加。bundled JSON は安全だが攻撃者が用意した巨大/深い JSON を読ませた場合の DoS 防止。
- **Python opt-out API parity**: 現状 Python は `set_zh_en_dispatch` を持たず常時 ON。他 6 ランタイムと API parity を取るために将来 `MultilingualPhonemizer.set_zh_en_dispatch(bool)` を no-op or 実機能として追加検討 (test `test_dispatch_no_optout_api_exposed` で現状を pin 中)。
- **WASM JS 実配線**: `ChineseG2P.setZhEnDispatch` の wrapper は整備済だが、`G2P.create()` も `piper-plus` 側もまだ `wasmPhonemizer` を注入していないため、JS-only 実行では dispatch は no-op (Rust WASM 直叩きでは動作)。`G2P.create({ wasmPhonemizer })` 統合が次フェーズ。
- **Rust piper-core / piper-plus-g2p の chinese.rs 重複**: `piper-core/src/phonemize/chinese.rs` は piper-plus-g2p の ~470 行のコピー (CI parity test で drift 防止)。`pub use piper_plus_g2p::chinese::*` への置換で長期メンテナンスコストを下げる予定。
- **Rust `last_eos` Mutex のセマンティクス改善**: 現状 `Mutex<String>` は単一スレッド前提で安全だが論理的にはスナップショット。中期的には `phonemize_with_prosody` の戻り値型に EOS を含める設計に変更予定。

#### Swift G2P 単独利用サポート (Issue #387)

iOS / Swift から piper-plus の G2P (Grapheme-to-Phoneme) を **ONNX Runtime 非依存で**単独利用可能に。8 言語 (ja/en/zh/ko/es/fr/pt/sv) 対応、辞書はバイナリ埋込で iOS App Sandbox でも動作。

- 新 SPM product: `PiperPlusG2P` (`Package.swift` の `.library(name: "PiperPlusG2P", ...)`)
- 新 artifact: `libpiper_plus_g2p-ios-v${VERSION}.xcframework.zip` (合成エンジン xcframework と独立、ORT 非依存、~3-5MB zip)
- Swift API: `Phonemizer(languages:)` / `phonemize(_:language:)` / `availableLanguages` (`Sources/PiperPlusG2P/`)
- Rust 側変更:
  - `piper-plus-g2p` crate に `[lib] crate-type = ["staticlib", "cdylib", "rlib"]` 追加
  - `bundled-dicts` feature 新設 (cmudict + pinyin JSON を `include_str!` / `include_bytes!` で埋込)
  - `EnglishPhonemizer::new_bundled()` / `ChinesePhonemizer::new_bundled()` 追加
  - `ffi.rs::register_one()` を `bundled-dicts` 有効時に新コンストラクタ経由に変更
- `cbindgen.toml` 新設 — `piper_plus_g2p.h` を CI で自動生成
- CI: `release-shared-lib.yml` に `build-g2p-ios` matrix + `assemble-g2p-xcframework` ジョブ追加。`release` ジョブは G2P xcframework の sha256 と `Package.swift` の `g2pChecksum` 一致を verify
- ドキュメント: [`docs/reference/swift-g2p.md`](docs/reference/swift-g2p.md) (仕様)、[`docs/guides/platform/swift-g2p-integration.md`](docs/guides/platform/swift-g2p-integration.md) (利用ガイド)、[`docs/spec/swift-g2p-contract.toml`](docs/spec/swift-g2p-contract.toml) (FFI/ABI/JSON 契約)
- 第三者ライセンス: `src/rust/piper-plus-g2p/THIRD_PARTY_LICENSES.md` に CMU Pronouncing Dictionary (BSD-style) と pypinyin (MIT) のセクションを追加 (bundled-dicts で埋込む辞書の attribution)
- FFI: `default_languages()` 関数を新設し、有効な Cargo features と `bundled-dicts` の有無に応じて `piper_plus_g2p_create(NULL)` の言語セットを動的構築 (`src/rust/piper-plus-g2p/src/ffi.rs`)
- 並行性検証: `tests/PiperPlusG2PTests/ConcurrencyTests.swift` を追加。`Phonemizer.@unchecked Sendable` を 60 並列 phonemize / 20 並列 init / 100 反復 deinit で実証
- README 更新: [`README.md`](README.md) / [`README_EN.md`](README_EN.md) Interfaces セクションに iOS Swift G2P (SPM) 行追加。`docs/guides/platform/ios-integration.md` Distribution Selection 表に G2P-only 行追加。crate `src/rust/piper-plus-g2p/README.md` を v0.4 に統一、Feature Flags 表に `ffi` / `bundled-dicts` 追加、C FFI 章を iOS 統合向けに拡充
- ビルド成果物の `.gitignore`: `*.xcframework/` / `*.xcframework.zip` / `build-g2p-ios/` / `.build/` / `.swiftpm/` / `*.xcodeproj/` / `DerivedData/` を追加
- **CI 整備 (PR で実行されるようにした)**:
  - `release-shared-lib.yml` に `pull_request` trigger と path filter を追加。`build-g2p-ios` / `assemble-g2p-xcframework` のみ PR で smoke run、`build-shared` / `build-ios` / `assemble-xcframework` / `build-android` / `release` は `if: github.event_name != 'pull_request'` で tag push 限定を維持
  - `.github/workflows/swift-g2p-ci.yml` 新設 — macOS runner で `cargo build --target {aarch64,x86_64}-apple-darwin` で staticlib を universal 化、`cbindgen` でヘッダ生成、`xcodebuild -create-xcframework` で local macOS xcframework 組立、`Package.swift` を CI 専用 path-based manifest に置換 (workspace ephemeral)、`swift test --filter PiperPlusG2PTests` を実行。`PhonemizerTests` / `GoldenPhonemeTests` / `ConcurrencyTests` 全 3 ファイルを **PR で自動検証**できる
- **テスト追加**:
  - `src/rust/piper-plus-g2p/src/ffi.rs::tests`: `default_languages()` の各 feature 組合せ (full / rule-based / no-bundled-dicts) と `register_one()` の正常系・UnsupportedLanguage / Phonemize エラー系を 7 件追加。lib tests 396 → **403** に増加 (`cargo test --features all-languages,naist-jdic,bundled-dicts,ffi`)
  - `tests/PiperPlusG2PTests/PhonemizerTests.swift`: assertion を Golden fixture と整合する形で強化。`isEmpty` チェックのみだった 8 言語テストに、具体トークン照合 (en `h`, ja `k/o/n/i/a`, es `o/l/a`, fr `b`, pt `o`)、最小トークン数の `XCTAssertGreaterThanOrEqual`、中国語の PUA tone marker 検出 (E000–F8FF) を追加

#### iOS shared-lib を xcframework として配布開始 (Issue #377)

iOS 利用シナリオ (Dart FFI / Godot / Swift / SPM) に対応する xcframework 配布を成立させた。device (arm64) + simulator (arm64+x86_64 universal) の両 slice を含む。

- 新 artifact: `libpiper_plus-ios-v${VERSION}.xcframework.zip` (device slice + simulator universal slice)
- **`piper_plus.xcframework` は static archive** — Xcode では **"Do Not Embed"** で取り込む (リンクのみ)。`onnxruntime.xcframework` は dynamic framework のため **"Embed & Sign"** が必須
- 利用者ガイド: [`docs/guides/platform/ios-integration.md`](docs/guides/platform/ios-integration.md) (Dart / Godot / Swift 横断、トラブルシューティング、App Store 提出チェックリスト含む)
- Swift プロジェクト向け手順: [`examples/swift/README.md`](examples/swift/README.md)

#### Swift `import PiperPlus` を有効化する `module.modulemap` 同梱

- xcframework の各 slice の `Headers/` に `module.modulemap` を CMake で自動生成して同梱
- Swift consumer は `import PiperPlus` で `piper_plus.h` の C API surface 全体にアクセス可能
- 仕様: 非 framework 形式の `module PiperPlus { umbrella header "piper_plus.h" export * module * { export * } }`

#### Swift Package Manager マニフェスト (`Package.swift`) を repo 直下に配置

- consumer は `Package.swift` 一行 (`from: "1.13.0"`) のみで `import PiperPlus` 利用可能 — ORT は wrapper target 経由で **transitive 解決**される
- 内部構造: Swift `target` (`PiperPlus`、`@_exported import PiperPlusBinary` で C API を再エクスポート) + `binaryTarget` (`PiperPlusBinary`、xcframework.zip 参照) + `dependencies: [onnxruntime-swift-package-manager]`
- `platforms: [.iOS(.v15)]` のみ宣言 (macOS / visionOS / Mac Catalyst slice は v1.13.0 では無し、M5 候補)
- メンテナがリリースタグ push **前** に `Package.swift` の version + checksum を `dev` 上で手動更新する運用 (sherpa-onnx 方式、`Package.swift` 冒頭コメントに手順記載)
- リリース時に `release` ジョブが Package.swift の checksum が placeholder ("0000...") でないこと、および xcframework zip の SHA-256 と一致することを CI ガード

#### iOS shared-lib 取得経路を Microsoft 公式 CDN に切替

ONNX Runtime の旧 GitHub Releases zip は Microsoft が配布チャネルを CocoaPods/SPM/CDN に一本化したため削除されており、v1.11.0 以降 `Build iOS arm64` ジョブが連続失敗していた。**release ジョブの巻き添えで Linux/Windows/macOS/Android shared-lib も Releases に上がっていなかった問題を解消**。

- curl URL を `https://download.onnxruntime.ai/pod-archive-onnxruntime-c-${VERSION}.zip` に変更
- sha256 検証ステップ追加 (1.17.0 = `1623e1150507d9e5...db871`)
- CDN zip は Mach-O dylib のみで static `.a` 不在のため、利用者は `Embed & Sign Frameworks` で組込

#### `PrivacyInfo.xcprivacy` informational reference を xcframework に同梱

- xcframework root に空の Privacy Manifest (`NSPrivacyTracking=false`、3 配列空) を配置
- **注意:** Apple App Store の Privacy Manifest スキャナは `*.framework` bundle root の `PrivacyInfo.xcprivacy` を読む。static archive xcframework のルート配置は **informational reference のみ** — consumer app target で `PrivacyInfo.xcprivacy` を別途用意する必要あり
- 推奨 declaration テンプレートと Required Reason API カテゴリ (SystemBootTime / FileTimestamp / DiskSpace) を [`docs/guides/platform/ios-integration.md`](docs/guides/platform/ios-integration.md#app-store-submission-checklist) に記載

#### iOS リンクエラー検出 CI ガード

- `release-shared-lib.yml` の `Verify symbol resolution` を 2 段階チェックに強化
  - ORT-prefix 系 (`_Ort*` 等) の未解決 → fail (ORT version drift 検出)
  - project-internal 系 (`_piper_plus_*`, `_openjtalk_*`, `__ZN<N>piper`) の未解決 → fail (iOS 除外バグ検出)
- desktop-only TU を iOS で除外して呼び出し側だけ残るバグ (例: `openjtalk_phonemize.cpp` から `openjtalk_is_available` を呼ぶ場合) を CI で検出

#### Voice Cloning + SSML を C++/WASM ランタイムに展開

v1.12.0 で 5 ランタイム (Python/Rust/C#/Go/WASM) に展開した SSML / Voice Cloning を、残る C++ と WASM の TTS 統合面に拡張。

- **C++ SSML parser** (`src/cpp/ssml.{hpp,cpp}`, CLI `--ssml`) — W3C subset (`<speak>`, `<break>`, `<prosody rate>`) を CLI バイナリで処理可能に。C API には未エクスポート (FFI 経由は次フェーズ)。Issue #444, PR #477
- **WASM SSML parser** (`src/wasm/openjtalk-web/src/index.js::synthesizeSsml`) — `isSsml` で自動 dispatch、`synthesizeSsml` で silence 挿入 + length_scale 切替。`@piper-plus/g2p` の `parseSsml` を再利用。PR #479
- **WASM Voice Cloning 統合** — `synthesizeFromReferenceAudio` / `speakerEmbedding` option を `PiperPlus` クラスに追加 (`src/wasm/openjtalk-web/src/synth.js`)。Rust 側 wasm bindings は v1.12.0 で既に提供済みだったが、`piper-plus` npm 経由の API として完成。PR #478
- **C++ Voice Cloning CLI フラグ** — `--reference-audio` / `--speaker-embedding` / `--speaker-encoder-model` を CLI バイナリに追加 (C API は `speaker_embedding` テンソル経路で動作、ECAPA-TDNN 推論 API はスタブ)。PR #475, #476

これにより SSML サポートは **Python/Rust/C#/Go/WASM/C++ の 6 ランタイム**、Voice Cloning は **6 ランタイム**で利用可能。

#### マルチランタイム RTF ベンチマーク

7 ランタイム横断の Real-Time Factor (RTF) ベンチマーク基盤を整備し、GitHub Pages に常時公開。

- `tools/benchmark/multi-runtime/` で Python/Rust/C#/Go/WASM/C++ + CLI の RTF を統一フォーマットで計測 (baseline_v1.json)
- 結果を GitHub Pages (`https://ayutaz.github.io/piper-plus/bench/multi-runtime/`) にプッシュ。`dev` ブランチへの merge ごとに自動更新 (`.github/workflows/pages-multi-runtime-bench.yml`)
- v1.12.0 baseline と差分回帰検出用に CI gate を準備 (PR #484, #480, #483, #485, commits 4367e958 / f08cd417 / 2177dbd9 / 7bf3dc59)
- README.md に公開 URL リンクを追加 (2177dbd9)

#### サーバー機能拡張

- **真のストリーミングチャンク + Phoneme Timing 配線** — `?streaming=true` で文単位の真のチャンク配信 + 各チャンクに phoneme-timing メタデータを同梱 (Python/Go ランタイム)。`/api/phoneme-timing` で streaming にも対応。PR #481
- **Bearer Token 認証 + Rate Limit** — `docker/python-inference/inference.py` (OpenAI 互換 Docker サーバー) に `PIPER_API_KEYS` 環境変数 (カンマ区切りリスト) による bearer auth と `slowapi` ベースの rate limit を追加。PR #475

#### Post-v1.12.0 fixes

- npm: `piper-plus` の subpath exports に types フィールドを追加 (`./timing`, `./streaming` 等は types 提供、`./phonemizer` / `./wasm/*` は意図的 skip)。PR #465 (ec4c5b7d)
- `piper.http_server` の `/v1/audio/speech/languages` で `sv` (スウェーデン語) が欠落していた問題を修正。commit 2f4efaf9

#### Post-v1.12.0 documentation

- v1.12.0 リリース直後のドキュメントドリフト一括修正 (HiFi-GAN archived 注記、CLAUDE.md / README 整合)。PR #466 (3414bb7c)
- README.md / CHANGELOG / docs/spec の v1.12 以降サイクル整合監査 (本 PR)

#### Post-v1.12.0 tests

- Go: `voice` / `download` カバレッジを 793 → 拡充 (LJSpeech 互換性パス含む)。PR #469 (4f49d27a)
- G2P: zh-en loanword / pt dialect / SSML エッジケースのテスト拡充。PR #472 (4ff0eb7b)

#### Post-v1.12.0 chore

- Docker: arm64 build/test matrix を CI に追加 (`docker-build-test.yml`)。PR #473 (16fa5091)
- Docker: GitHub Actions runner の disk 枯渇対策 (build artifact prune + buildx cache strategy)。PR #482 (22c78236)
- CodeQL: `cpp/loop-variable-changed` をルール全体で suppress (false positive 多数のため)。PR #492 (cd6a9d8a)
- CI: `deploy-huggingface.yml` / `release-shared-lib.yml` に `scripts/generate_model_card.py` 駆動の `MODEL_CARD.md` + `LICENSE_ATTRIBUTIONS.md` 生成 step を注入。 HF Space deploy / GitHub Release artifact に attribution が確実に同梱され、 dataset attribution の脱落を構造的に防止 (M3.2 / PR #511 実装完了)
- CI: OpenSSF Scorecard を週次 + dev push で実行する `scorecard.yml` を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.6 Week 1 由来、 Top 10 外の supply-chain hardening)。 SARIF を code scanning に upload + `scorecard.dev` に publish、 PR を block しない informational tier
- CI: `scripts/check_changelog_format.py` + `changelog-format.yml` + pre-commit hook (`changelog-format`) で keep-a-changelog 形式 validator を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #1 由来)。 H1 / Unreleased / バージョン header date format / 降順を error tier、 セクション名 / 重複を warning tier として検査。 既存 historic な絵文字付きセクションは bootstrap baseline として allowlist 化
- CI: `scripts/check_readme_heading_tree.py` + `readme-heading-tree-parity.yml` で multilingual README の heading tree parity を informational tier で追加 (`docs/proposals/ci-expansion-2026-05.md` §3.7 Tier S #2 由来)。 既存 `check_readme_h2_parity.py` (H2 個数のみ) を補強し、 H2/H3/H4 の structure と H2 section 内の H3 count を比較。 default tolerance ±5 で既存翻訳 drift を bootstrap baseline 吸収、 新規 drift 拡大のみ警告。 PR を block しない
- CI: `scripts/ci_observability_snapshot.py` + `ci-observability-snapshot.yml` で 週次の CI flake / cancel / skip trend snapshot を追加 (`docs/proposals/ci-expansion-2026-05.md` §3.9 #1 由来、 Top 10 外の CI observability)。 過去 7 日の `gh run list` を workflow 単位に集計し、 cancellation_rate > 10% の workflow を "flake watch" 候補として artifact 出力。 M1.1 cancelled baseline alarm (PR 単位の silent skip gate) の trend 観測層
- CI: `.github/workflows/rust-miri-nightly.yml` で nightly Rust miri を週次実行 (`docs/proposals/ci-expansion-2026-05.md` §3.1 Sanitizer 拡張 #8 由来、 Top 10 外)。 piper-plus-g2p crate の 27 箇所の unsafe ブロック (FFI 系を除く Rust internals) に対する Undefined Behavior / stacked borrow / aliasing 違反を `cargo +nightly miri test --skip ffi` で informational 検出。 timeout 60 min、 PR を block しない

### Limitations (v1.13.0 iOS xcframework)

| Item | Status | Notes |
|------|--------|-------|
| ONNX Runtime bundling | ✗ | xcframework に同梱されない。SPM 経由なら transitive 解決、それ以外は consumer が CocoaPods / 手動 DL で取得 + Embed & Sign |
| OpenJTalk 辞書 (日本語 TTS 必須) | ✗ | App Sandbox で auto-DL 不可。consumer app が `open_jtalk_dic_utf_8-1.11/` を bundle に同梱して `dict_dir` で渡す ([guide](docs/guides/platform/ios-integration.md#step-4-japanese-tts-only-bundle-the-openjtalk-dictionary)) |
| macOS / Mac Catalyst slice | ✗ | M5 候補 — 現状 xcframework は iOS のみ。`Package.swift` も `platforms: [.iOS(.v15)]` のみ |
| visionOS / tvOS / watchOS slice | ✗ | M5 候補 — ORT visionOS 対応待ち |
| `.dSYM` for crash symbolication | ✗ | xcframework binary は stripped、別 issue 追跡 |
| App Extension / App Clip | ✗ | piper-plus + ORT (~35 MB) が 32 MB / 10 MB 制限を超過 |
| Privacy Manifest 自動スキャン | ✗ | static archive xcframework は Apple スキャナの読取り対象外、consumer app target に追加要 |
| C++ symbol leak (ODR) | ⚠ | `fmt::` / `spdlog::` / `piper::` symbols は static archive に export される。他 C++ 静的ライブラリと衝突する場合は Other Linker Flags に `-Wl,-load_hidden,...libpiper_plus.a` を追加 |

### Deprecated

#### `libpiper_plus-ios-arm64-${VERSION}.tar.gz` (device-only、`.framework` 同梱 tar.gz)

- v1.13.0 では新 xcframework.zip と並行配布 (移行期間)
- **v1.14.0 で削除予定** — `libpiper_plus-ios-v${VERSION}.xcframework.zip` への移行を推奨
- v1.13.0 の `release-shared-lib.yml` は tar.gz 生成時に `::warning::` を出力するため利用者が deprecation を即時認識可能

### Fixed

#### Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一 (Issue #527)

- **`monotonic_align/setup.py`**: `from distutils.core import setup` →
  `from setuptools import setup`。 distutils は Python 3.12 で stdlib から
  削除済 (PEP 632)、 setuptools shim 経由で偶然動いていた状態を明示化。

#### その他

- iOS / Linux / Windows / macOS / Android shared-lib リリースパイプラインを復旧 (Issue #377、v1.11.0 以降の停止)
  - `release` ジョブの `needs:` が `build-ios` 失敗で全 OS artifact のアップロードを止めていた
- Bundle size gate: Android AAR ビルドが prebuilt `libpiper_plus.so` 欠如で永久 SKIP となっていた問題を修正 (Issue #494)
  - `bundle-size-gate.yml` に `build-android-shared-libs` matrix job (arm64-v8a / armeabi-v7a / x86_64) を追加し、`release-shared-lib.yml` と同じ NDK r26c + ORT 1.20.0 + 16 KB page-align で `libpiper_plus.so` をビルド。bundle-size ジョブが artifact を `android/piper-plus-g2p/src/main/jniLibs/<ABI>/` に配置してから `assembleRelease` を実行することで `maven::piper-plus-g2p-android` の Observed サイズが取得可能に
  - `scripts/check_ort_versions.py` の `TARGETS` に `bundle-size-gate.yml` を追加し、ORT バージョン drift gate の対象に統合 (Copilot review fix)
- スウェーデン語 (sv) の単語単位 言語判定 (per-word LID) を全 7 ランタイムで復旧・統一 (Issue #539)。`å`/`ä`/`ö` を含む語 (例: `så` / `och` / `för` / `är`) が英語と誤判定されていた回帰を修正 (#297 で全ランタイム実装 → #300 の g2p パッケージ抽出で Python/Rust から脱落 → 残存コピーが drift、WASM は char-level の別実装)。**保守的ポリシー** (strong indicator = `å`/`Å` または 46 語の function-word リスト完全一致のみ。`ä`/`ö` 単独は独語/フィンランド語/借用語と共有のため不十分) で再実装。全ランタイムが byte-identical な `sv_function_words.json` をロードし、新規 sync gate (`scripts/check_swedish_lid_consistency.py` + `docs/spec/swedish-lid-mirrors.toml`、ZH-EN loanword gate と同型) が 7 データミラー + 6 fixture ミラーの byte-for-byte 一致を強制。cross-runtime parity fixture matrix で一致を実証。学習済み 6lang モデルは sv 未含有のためデフォルト推論は不変、独立 G2P 用途と将来の sv モデルに影響
- v1.12.0 で配布された config.json (つくよみちゃん / 6lang base) に未 PUA 化の multi-codepoint 音素 (`ɔɪ` / `œ̃` / `ɐ̃`) が混入し、Windows の C++ 推論が `is not a single codepoint` で失敗していた問題を修正 (Issue #385、PR #389)。`pua.json` を v1 → v2 化して該当音素を PUA 割り当て + 全 6 ランタイムの PUA テーブルを同期 + `map_token(strict=True)` で未知トークンを fail-fast 化
- Windows の C++ ランタイム (`piper.exe`) でつくよみちゃん 6lang モデルの `--download-model` が PowerShell `-Command $args` のバグにより URL / 出力先が空になりダウンロードできなかった問題を修正 (PR #557)。あわせて multi-codepoint 音素 (`ɔɪ` / `œ̃` / `ɐ̃` 等) の raw キーが C++ パーサに漏れ、Windows のつくよみ / base config で推論が失敗していた v1.12.0 の回帰をガードする regression CI を追加 (実 config / `pua.json` データ修正は上記 PR #389、本 PR は再発防止 CI)
- 推論の EOS region trim を全 6 ランタイム (Python / Rust / Go / C# / WASM / C++) で全入力に対し適用し、ファインチューニング済みモデル (つくよみちゃん等) で末尾音節が二重に聞こえる問題を修正 (Issue #499、PR #506 / #507)。**挙動変更注記:** 本修正により全モデル・全ランタイムで出力音声の末尾フレーム (`ceil(durations[-1])` 由来の EOS region) が trim され、v1.12.0 比で出力音声長・末尾が変化する。バグ修正だがデフォルト出力が変わるため明示 (破壊的変更ではない)
- Go の text splitter を Python / Rust の canonical 実装 (post-consume 方式) に統一し、CJK 句読点 + 閉じ括弧パターンが 1 文として誤結合されていた問題を修正 (Issue #346、PR #504)
- リリース QA で判明した Windows ビルドの諸問題を修正 (PR #505): `.gitattributes` の `eol=lf` catch-all 追加 (CRLF チェックアウトで gofmt / byte-sync gate が破損)、contract gate スクリプトの cp932 / cp1252 コンソール `UnicodeEncodeError` crash、`check_secret_path_reference` の Windows パス処理
- v1.12.0 の MB-iSTFT-VITS2 ONNX (つくよみちゃん等) を Docker python-inference / webui サーバや Rust / C++ ランタイムで実行すると `Required inputs (speaker_embedding, speaker_embedding_mask) are missing` で 500 エラー / ロード失敗していた問題を修正 (Issue #426、PR #443)。推論側 4 箇所で speaker_embedding 入力の有無を ONNX セッションから動的判定し、未使用時は zero embedding + mask=0 を feed する fallback を追加。実モデルでの回帰を防ぐ integration gate も追加

### Security

- `release-shared-lib.yml` の workflow-level permissions を `contents: read` に縮小、`release` ジョブのみ `contents: write` を opt-in
- tag validator の regex を `^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$` に anchored 化 (例: `1.0.0-malicious$(rm)` 形のタグ injection を拒否)
- `src/python_run/requirements.txt`: `g2p-en` 経由 transitive 依存 (`g2p-en` → `nltk` → `joblib`) にセキュリティ下限を明示 (`nltk>=3.9.4` / `joblib>=1.5.0`)。診断手順を `docs/getting-started/troubleshooting.md` ("Security Audit CI Issues") に追加
  - 2026-05 の `Security Audit / pip-audit (Python)` dev push 失敗は **上流 advisory データ欠陥** が原因で piper-plus 側のコード/依存問題ではない: `nltk` `PYSEC-2026-97` (CVE-2026-0846) と `joblib` `PYSEC-2024-277` (CVE-2024-34997) が 2026-05-20 に `last_affected` 欠落で生成され、安全な `nltk 3.9.4` / `joblib 1.5.3` を含む全バージョンが flag された (同一 commit が後の schedule run では pass)。`pypa/advisory-database` PR #289 ("Update records generated incorrectly", 2026-05-21) で修正済み
  - 下限ピンは将来の dependency resolution が真に脆弱なバージョンへ退行するのを防ぐ regression insurance
- `.github/workflows/security-audit.yml`: pull_request `paths` に `src/python_run/requirements.txt` を追加。従来 `setup.py` のみが対象で、実際の依存定義 source (setup.py がパースする requirements.txt) の変更が PR の pip-audit gate を通らなかった漏れを修正
- 依存ライブラリの脆弱性対応: `protobufjs` 7.5.6 → 7.5.8 (CVE-2026-45740、PR #530)、`idna` 3.10 → 3.15 (CVE-2026-45409、PR #531)、`gitpython` 3.1.49 → 3.1.50 (GHSA-mv93-w799-cj2w、PR #437)、Dependabot security alert 対応で `urllib3` (high) / `@protobufjs/utf8` (medium) を更新 (PR #450)
- HTTP サーバーのログインジェクション対策 (CodeQL `py/log-injection`、PR #435)、および C# の `cs/unsafe-double-checked-lock` 修正 + CodeQL ノイズ削減 (PR #434)
- Rust の `pyo3` advisory RUSTSEC-2026-0176 / RUSTSEC-2026-0177 を `.cargo/audit.toml` で ignore (rust-numpy が `pyo3` 0.24 系に pin しており上流更新待ち、PR #558 / #559)

## [1.12.0] - 2026-05-04

### Changed (Breaking)

#### Decoder を MB-iSTFT-VITS2 に統一 (HiFi-GAN Generator 削除)

VITS の Decoder を **MB-iSTFT (Multi-Band inverse STFT) + PQMF** に完全に置き換え、HiFi-GAN `Generator` クラスを削除。`upsample_rates(16x) * iSTFT_hop(4x) * PQMF_subbands(4x) = 256x` で従来と同じ総倍率を維持しつつ Decoder 計算量を削減し、CPU 推論を **2.21x 高速化** (Mean infer 168.2ms → 76.2ms, RTF 0.066 → 0.037, 100 phoneme p50)。ONNX 互換 iSTFT は DFT 行列方式 (`OnnxISTFT`) で `F.conv_transpose1d` に展開し opset 15 で動作。出力形状 `[B, 1, T]` を維持しているため、C#/Rust/Go/WASM/C++ ランタイム は変更不要 (既存 HiFi-GAN ONNX も推論側は引き続き動作)。`--quality high` も MB-iSTFT で対応 (resblock="1" + 512ch + (4,4) upsample)。

**Breaking changes:**

- `--mb-istft` フラグは廃止 (常に有効)。
- `Generator` クラス削除 — 既存 HiFi-GAN `.ckpt` からの学習再開・FT は不可。MB-iSTFT 対応の base モデル (`piper-plus-base`) と追加モデル (`piper-plus-tsukuyomi-chan` 等) を本マージ時に再公開。
- `_check_decoder_architecture_compatibility` 削除 (不要になったため)。
- `mb_istft` hparam 削除。

**保持される CLI:**

- `--c-sub-stft` (sub-band STFT loss 重み, デフォルト 1.0)
- `--sub-stft-fft-sizes` / `--sub-stft-hop-sizes` / `--sub-stft-win-sizes`

**学習済みモデル:** 6lang MB-iSTFT 75 epoch ベース + つくよみちゃん MB-iSTFT 500 epoch FT。
**実装:** `vits/mb_istft.py`, `vits/stft_onnx.py`, `vits/stft_loss.py`。Issue #268, PR #320。

#### .NET 全プロジェクトを `net10.0` LTS に移行

C# プロジェクト (`PiperPlus.Core`, `PiperPlus.Cli`, テスト、Bench) の Target Framework を **`net10.0` LTS** に直接移行。`net6.0` / `net8.0` / `net9.0` のサポートは廃止。NuGet パッケージ `PiperPlus.Core 0.3.0` / `PiperPlus.Cli 0.3.0` 以降は **`net10.0` LTS のみ**。詳細: PR #374 (本 v1.12.0 Chore 内記載)。

#### `PiperVoice.phonemize()` の戻り値セマンティック変更

戻り値**型** `list[list[str]]` は v1.11.0 から変更ないが、**意味論が変わった**:

- **v1.11.0 以前**: 入力テキスト全体を 1 つの phoneme シーケンスとして音素化し、常に **1 要素** のリスト (`[whole_text_phonemes]`) を返していた。
- **v1.12.0 以降**: 入力テキストを終止符で文単位に分割し、文ごとに音素化して **N 要素** のリストを返す。SSML (`<speak>...`) 入力は単一ユニットとして構造保持。

**影響を受ける呼び出しパターン:**

- `phonemes_list = voice.phonemize(text); ids = voice.phonemes_to_ids(phonemes_list[0])` のように **`[0]` で固定アクセスしている既存コードは複数文を渡すと壊れる** (1 文目のみ処理されることになる)。
- 全文を一括処理したい場合は `for phonemes in voice.phonemize(text): ids = voice.phonemes_to_ids(phonemes)` に書き換える、または事前に `text` を 1 文に絞る。

**移行ガイド:** `docs/migration/v1.11-to-v1.12.md` 参照。
**実装:** `src/python_run/piper/voice.py:phonemize()` (#367)

### Added

#### 全7ランタイムで短テキスト合成品質改善 (Strategy A/B/C)

短テキスト (1-2文節) 合成時のノイズ・歪み・0秒出力問題に対する緩和策を全7ランタイム (Python/Rust/C#/C++/Go/JS-WASM/CLI) に並列実装。VITS の構造的制限 (rhasspy/piper#252) に起因する既知問題を解消。Silence Padding + Post-trim (Strategy A)、Dynamic Scales Adjustment (Strategy B)、SSML `<break>` Auto-injection (Strategy C, SSML対応4ランタイムのみ) を組み合わせる。設定仕様: `docs/spec/short-text-contract.toml` (#337)

#### Voice Cloning + SSML + Wyoming Docker 統合 (#331)

- **Voice Cloning**: 5ランタイム (Rust/C#/Go/WASM/C++) に Speaker Encoder (ECAPA-TDNN) + `speaker_embedding` テンソル対応を統合。参照音声から話者特徴を抽出し、未知話者の声質で TTS 合成可能。
- **SSML 基本サポート**: `<speak>`, `<break>`, `<prosody rate="...">` を Python/Rust/C#/Go の 4 ランタイムで実装 (W3C SSML サブセット準拠、Python 62 / Rust 39 / C# 59 / Go 67 テスト)。
- **MOS ベンチマークツール**: サンプル生成、PESQ/STOI 等メトリクス計算、調査フォーム生成 (`tools/benchmark/`)。
- **iOS/Android ビルド CI**: libpiper_plus のモバイルクロスコンパイル (iOS arm64 + Android arm64-v8a/armeabi-v7a/x86_64)。
- **Wyoming Docker**: HA 統合用の Docker Compose 環境 + ガイド (`docker/wyoming/`, `docs/guides/integration/home-assistant.md`)。
- **モデル投稿ガイド**: `CONTRIBUTING_MODELS.md` + GitHub Issue テンプレート。

#### 汎用 Colab ファインチューニングノートブック (#324)

LJSpeech 形式 (`wavs/` + `metadata.csv`) のカスタムデータセットで piper-plus モデルをファインチューニング可能な汎用 Colab ノートブックを追加。事前学習済みベースモデル (6lang/つくよみちゃん等) からの転移学習に対応。

#### Python ランタイム ストリーミング文単位分割 (新規)

[Zenn スクラップ (kun432 氏)](https://zenn.dev/kun432/scraps/cddbfcd75b8b34) で指摘された「Python ランタイムだけ `synthesize_stream_raw()` に文単位分割が無く、HTTP `?streaming=true` でも単一チャンクで返ってしまう」問題を解消。

**新規モジュール:**

- `piper.text_splitter` (`src/python_run/piper/text_splitter.py`)
  - `split_sentences(text) -> list[str]` — 終止符 `.`/`!`/`?`/`。`/`！`/`？` および直後の閉じ括弧 (`」 』 ） ］ 】 ｣ ” ’ »` 等) を扱う
  - Rust `piper-core/src/streaming.rs::split_sentences` と同等の挙動 (post-consume 戦略)

**PiperVoice 修正:**

- `phonemize()` が複数文の入力を文ごとに音素化し `list[list[str]]` を **N 要素** で返すよう変更 (v1.11 までは常に 1 要素) — **挙動が破壊的に変わるため上記 "Changed (Breaking)" セクション参照**
- SSML (`<speak>...`) は単一ユニットとして扱い構造保持
- 既存呼び出し側 (`synthesize_stream_raw` / `synthesize_with_timing`) は無修正で複数チャンク化が動作

**互換性:**

- HTTP `?streaming=true` (PR #361 の FastAPI `StreamingResponse`) も真のチャンク配信になる
- `phonemize()` を直接呼んでいる外部コードは戻り値の要素数前提を見直す必要あり

**設定仕様:**

- `docs/spec/text-splitter-contract.toml` の Implementations 一覧に Python 実装を追加
- 終止符 6/7、閉じ括弧 14/14 (Rust と同状態、U+FF0E は spec 通り未対応)

**テスト:**

- `tests/test_text_splitter.py` (18 件) — Rust テストスイートを移植
- `tests/test_voice_streaming.py` (8 件) — `synthesize_stream_raw()` の文単位 yield と SSML ハンドリング

**関連:** PR #367 (続編元: PR #361 FastAPI 移行)

#### Python ランタイム Phoneme Timing 機能 (新規)

Python ランタイムに完全な phoneme timing 出力機能を追加。VITS Duration Predictor から音素ごとの開始時刻・終了時刻・継続時間を抽出し、JSON/TSV/SRT 形式で出力可能。

**新規モジュール:**

- `piper.timing` モジュール (`src/python_run/piper/timing.py`)
  - `PhonemeTimingInfo`, `TimingResult` データクラス
  - `durations_to_timing()`, `timing_to_json/tsv/srt()`, `timing_to_json_compact()`
  - `build_phoneme_id_reverse_map()` (PUA char 対応)

**PiperVoice 拡張:**

- `synthesize_with_timing(text, wav_file=None, ...) -> tuple[bytes, TimingResult | None]`
- `has_duration_output` プロパティ (モデル対応判定)
- `_synthesize_ids_core()` 内部メソッド (durations 取得 + original_phoneme_ids 保持)

**HTTP エンドポイント:**

- `POST/GET /api/phoneme-timing` (FastAPI、`format=json|tsv` 対応)
- `language` / `language_id` クエリパラメータで多言語対応

**設定:**

- `PiperConfig.hop_size` フィールド追加 (デフォルト 256、`config.json` の `audio.hop_size` から読込)

**互換性:**

- Rust/Go/C++/C# の既存実装と byte-for-byte 互換
- 既存の `synthesize()`, `synthesize_stream_raw()`, `synthesize_ids_to_raw()` API は完全な後方互換性を維持

**テスト:**

- `tests/test_phoneme_timing.py` (44 テスト)
- `tests/test_voice_timing.py` (22 テスト)
- `tests/test_http_timing.py` (14 テスト)
- `tests/test_config_fallback.py` に hop_size テスト 5 件追加

### Removed

- 死んだコード `src/python_run/piper/espeak_phonemizer.py` を削除 (piper-plus は推論時に espeak-ng に依存しない)
- Python ランタイムから HTS voice 依存を完全除去 (#342) — Python は pyopenjtalk-plus パスのみ。C++/Go/Rust/WASM の OpenJTalk バックエンドは引き続き利用
- Unity UPM を削除し関連ドキュメント整理 (#341)

### Changed

- HTTP server を Flask から **FastAPI に移行**、`?streaming=true` で `StreamingResponse` による真のチャンク配信に対応 (#361)
- Go Docker — Debian 化 + ORT 修正 + OpenJTalk 日本語 G2P + `serve` サブコマンド対応 (#332, #334)

### Fixed

- 短文「こんにちは。」が「あこんにちはた」と崩壊する問題を修正 (C++ ランタイム、UTF-8 コードポイントベースの文分割への置換 + 終止符直後の閉じ括弧を消費するロジック) (#363, #347, #348)
- Wyoming HA 統合エラー + Docker g2p import + リリース配布を解決 (#362)
- Go Dockerfile を `TARGETARCH` で arm64 対応 (multi-arch ビルド) (#366)
- WavLM Discriminator: safetensors 未公開モデルに合わせて `use_safetensors=False` に変更 (#353)
- Dependabot セキュリティアラート対応 (低リスク 7 件 + 高リスク 4 件) (#352, #364)
- テスト品質監査 — 全 18 件の再実装テスト修正 + 本番コード改善 (#338)
- C++ テスト全実行化 + 表面化した 11 テスト不具合修正 (#340)
- CI `changes` ジョブに checkout ステップを追加 (#339)
- crates.io 公開順序を修正 (#327)
- Pages デプロイを `dev` ブランチに限定 (#328)

### Documentation

- README の「30秒で試す」を OS 別ワンライナー化 + CLI バイナリ選択ガイド追加 (#360)
- 監査結果に基づくドキュメント全面同期 (v1.11.0 以降の差分を一括反映) (#368)
- エコシステム調査に基づく認知度・コントリビューション改善 (#329)
- npm 公開に伴うバージョン表記更新 (#330)

### Chore

- GitHub Actions runner を `ubuntu-24.04` に、Docker base を Debian trixie に更新 (#373)
- .NET 全プロジェクトを `net10.0` LTS に直接移行 (#374)
- EOL ランタイム (Node 18, Python 3.8) を更新 (#370)
- Node.js バージョンを 24 LTS に統一 (#345)
- MB-iSTFT 公開用 ckpt 変換スクリプトを復活 + `.gitignore` 補完 (#369)
- black を 26.3.1 へ更新 (Dependabot #145, #146) (#365)
- Claude Code hooks + skills で開発ワークフロー自動化 (#350)

### Tests

- 196 → 212 passed (リグレッション 0 件)

## [1.11.0] - 2026-04-06

### Added

- OpenAI 互換 TTS API エンドポイント追加 — `/v1/audio/speech` で既存の OpenAI クライアントから利用可能 (#321)
- C API 共有ライブラリ — opaque handle + ストリーミング + 配布パッケージ + FFI サンプル (#309)
- Go 推論バインディング — 6言語 G2P・ONNX 推論・CLI・サーバー (#260, #270)
- piper-g2p 独立 G2P パッケージ (Python + Rust + JS/WASM) (#300)
- 韓国語 G2P 対応 — C#・Go・npm/WASM 実装 + ドキュメント更新 (#299)
- スウェーデン語 G2P 対応 — 全プラットフォーム実装 (#297)
- WASM G2P — ES/FR/PT/ZH 実装 + テスト 841 件 (#316)
- WebUI: entrypoint 自動モデル DL — `PIPER_MODEL` 環境変数で起動時取得 (#313)
- README 多言語化 — 7言語追加 (KO/ES/PT/DE/RU/SV/HI) (#310)

### Changed

- CPU 推論 Tier 2 Quick Wins — warmup/cache/JA phonemize 全実装統一 (#318)
- dynamic_block_base + メモリアリーナ/パターン — 全実装統一 (#317)
- ONNX Runtime SessionOptions 最適化 — 全実装間で設定統一 (#315)
- コールドスタート最適化 — 初回発話レイテンシ ~2s → ~300ms (Rust/C#/WASM) (#302)
- WASM/npm パッケージ最適化 — 辞書外部化・feature gate・CI 改善 (#301)

### Fixed

- WebUI: NLTK tagger データ追加 — 英語推論の LookupError 解消 (#314)
- セキュリティ脆弱性対応 — Dependabot アラート 17 件解消 (#311)
- npm: config.json フォールバック追加 — HuggingFace 404 解消 (#304)
- Dependabot セキュリティアラート対応 — Python/Rust 依存更新 (#298)

### Documentation

- npm インストール手順追加 + NVDA リンク更新 (#293)
- npm バージョン参照を 0.1.1 に更新 (#292)
- 完了済みチケット削除 + ドキュメント誤記修正 (#312)
- 完了済み WASM G2P チケット・計画文書を削除 (#319)

### Chore

- 不要ドキュメント・壊れたデモ・WIP ワークフロー削除 (#303)

## [1.10.0] - 2026-03-28

### Changed

- PyPI パッケージ名を `piper-tts-plus` から `piper-plus` に変更 — 全レジストリ (npm, crates.io, NuGet) で名前統一 (#289)
  - `pip install piper-plus` でインストール可能に
  - 旧パッケージ `piper-tts-plus` はスタブリリースで `piper-plus` へリダイレクト予定

### Fixed

- npm: DictManager の辞書ダウンロードを GitHub Releases (r9y9/open_jtalk) に統一 — Rust/C#/C++ と同一ソース (#288)
  - 旧: HuggingFace 個別ファイル (404 エラー) → 新: tar.gz 一括 DL + SHA-256 検証 + DecompressionStream 展開
  - voice ファイル (mei_normal.htsvoice) を HuggingFace `piper-plus-base` にアップロード
  - PiperPlus._init() が DictManager.loadDictionary() + IndexedDB キャッシュを使用するように修正
  - SimpleUnifiedPhonemizer にプリロード済みデータ受け取り対応 (dictData/voiceData)
  - npm パッケージ v0.1.1 としてリリース

## [1.9.0] - 2026-03-28

### Added

- npm パッケージ `piper-plus` v0.1.0 — ブラウザ内で完全オフラインの多言語 TTS (JA/EN/ZH/ES/FR/PT) を提供 (#285)
  - OpenJTalk WASM (JA)、SimpleEnglishPhonemizer (EN)、キャラクタベース (ZH/ES/FR/PT)
  - `onnxruntime-web` による ONNX 推論、eSpeak-ng 不使用 (GPL リスク回避)
  - `PiperPlus`, `ModelManager`, `DictManager`, `AudioResult` 高レベル API
  - HuggingFace モデル自動 DL + IndexedDB キャッシュ
  - 282 テスト、CI (`npm-publish.yml`)
- PyPI パッケージ (`piper-tts-plus`) にプロジェクト説明 (README.md) を追加 (#286)

## [1.8.2] - 2026-03-24

### Added

- `export_onnx` で `emb_lang` 自動統一 (`--unify-emb-lang` / `--no-unify-emb-lang`) — シングルスピーカー多言語モデルで自動有効化 (#266, #279)
- `export_onnx` に `--unify-emb-lang-source N` オプション追加 (ソース言語インデックス指定)
- `docs/design/issue-266-auto-unify-emb-lang.md` 設計ドキュメント追加
- `emb_lang` 自動統一のユニットテスト7件 + ONNX統合テスト2件 (`test_export_onnx.py`)
- テスト用マルチリンガルモデルフィクスチャ追加 (`conftest.py`)

### Fixed

- `preprocess.py` の Windows 互換性修正 — `_HAS_SIGALRM` ガードで `signal.SIGALRM` 未対応プラットフォームでのクラッシュを回避 (#282)
- `preprocess.py` で `--timeout-seconds` が SIGALRM 未対応時にサイレント no-op になる問題に警告ログ追加

### Changed

- CLAUDE.md, training-guide.md を Issue #266 の自動 emb_lang 統一に合わせて更新
- `export_onnx` のドキュメントに `--simplify`, `--debug` オプションを追加
- `.gitignore` に `datasets/`, `models/`, `__pycache__/` 追加
- `pyproject.toml` に `VERSION` ファイルの package-data 設定追加

## [1.8.1] - 2026-03-22

### Fixed

- PyPI パッケージ (`piper-tts-plus`) の日本語音素化が空結果を返す致命的バグを修正
  - HTS ラベルパーシングを学習側と同じ正規表現ベースに書き換え (Kurihara method)
- `piper.__version__` が wheel インストール時に `"unknown"` を返す問題を修正
- wheel に `tests/` パッケージが含まれていた問題を修正

### Added

- EN/ZH/ES/FR/PT の phonemizer を runtime パッケージに追加 (6言語マルチリンガル対応)
- `MultilingualPhonemizer` (Unicode ベース言語自動検出 + ルーティング) を追加
- N バリアント規則・疑問詞マーカーを runtime 側に追加 (学習側と一致)
- 6言語統合テスト (`test_multilingual_integration.py`)
- CI: `python-tests.yml` に runtime テストステップ追加 (3 OS)
- CI: `dev-build-all.yml` に wheel ビルド後の6言語スモークテスト追加

### Changed

- `token_mapper.py` を全87エントリの多言語 PUA マッピングに更新
- `voice.py` を `piper_train` 不要のローカル `MultilingualPhonemizer` に切り替え
- `pyopenjtalk-plus>=0.4`, `g2p-en>=2.1.0`, `pypinyin>=0.50` を依存関係に追加

## [1.8.0] - 2026-03-22

### Added

#### C# (.NET) CLI

- モデル名/エイリアス自動解決 + 未ダウンロード時自動ダウンロード (`--model tsukuyomi`)
- `[[ phoneme ]]` インライン音素記法サポート
- カスタム辞書の大小文字分離・単語境界マッチング (C++パリティ)
- デフォルト辞書自動読み込み (`data/dictionaries/`)
- DotNetG2P + DotNetG2P.MeCab による日本語G2P
- DotNetG2P.English による英語G2P
- 中国語PUAマッピング + トーンマーカー修正
- `lid` (言語ID) テンソル対応
- OpenJTalk辞書自動ダウンロード (`DictionaryManager`)
- ストリーミング文分割 (`TextSplitter`)
- カスタム辞書 JSON v1/v2 形式対応
- NuGet パッケージ公開準備 (PiperPlus.Core, PiperPlus.Cli v0.1.0)

#### Rust CLI

- モデル名/エイリアス自動解決 + 自動ダウンロード (`find_model`, `resolve_model_path`)
- `--download-model` / `--model-dir` オプション追加
- `--quiet`, `--test-mode`, `--output-raw` オプション追加
- `--sentence-silence`, `--phoneme-silence` オプション追加
- `--list-models` 言語フィルタ (`--list-models ja`)
- カスタム辞書CLI統合 (テキスト/バッチ/ストリーミング全パス)
- 環境変数サポート (PIPER_DEFAULT_MODEL, PIPER_DEFAULT_CONFIG, PIPER_MODEL_DIR)
- naist-jdic をデフォルトfeatureに変更 (辞書バンドル)
- PyO3 0.22→0.23 アップグレード
- crates.io パッケージ公開準備 (piper-plus, piper-plus-cli v0.1.0)

#### CI/CD

- Rust CLIバイナリビルド (PR時3OS、リリース時5ターゲット)
- NuGet/crates.io 自動publishジョブ
- GitHub Actions を Node.js 24 対応バージョンに全面更新
- CI concurrencyグループ追加
- ARM64 QEMU DNS修正

#### 全言語共通

- `--output-file` 省略時に `output.wav` デフォルト出力
- Python モデルカタログ・ダウンロード機能追加

### Fixed

- C# ONNX推論の `lid` テンソル未送信バグ修正
- C# 中国語音素マッピング修正 (「你好」3 IDs → 15 IDs、「你好，今天天气很好。」3 IDs → 51 IDs)
- Rust 多言語推論で各言語に正しいPhonemizerを使用するよう修正
- Rust JA辞書未発見時のPassthroughPhonemizerフォールバック追加
- C# CLI統合テストの global.json rollForward修正
- C# テストのstderrレースコンディション修正
- リリースアーティファクト名衝突解消 (C#/Rust)

### Changed

- Rustクレート名: piper-core→piper-plus, piper-cli→piper-plus-cli
- C#/Rust バージョンはPyPIと独立管理 (v0.1.0)

## [1.7.0] - 2026-03-18

### 🚀 Major Features

#### Added

- **GPL-free 6言語マルチリンガルTTS** — 日本語・英語・中国語・スペイン語・フランス語・ポルトガル語の学習パイプライン + C++ G2P。espeak-ng (GPL) 不要で6言語推論が可能 (#218)
- **WebブラウザTTS高速化基盤** — ベンチマーク・キャッシュ・WebGPU・ストリーミング対応。全97テストパス (#246)
- **C++ CLI UX大幅改善** — `--text`による直接テキスト入力、`--list-models`/`--download-model`によるモデル管理、`--version`表示 (#244)
- **C++/Python音素化パイプライン同期** — プロソディマーク挿入・文脈依存Nバリアント・疑問詞マーカー・BOS/EOS制御をC++に実装。OpenJTalkフロントエンドをpyopenjtalk-plus Cライブラリに統一。fullcontext完全一致を達成 (#229)
- **Docker テスト強化・推論テスト統合** — 8テキスト比較テスト(8/8 PASS)、python-inferenceとwebui統合、CI回帰テスト (#230)
- **ONNXエクスポートFP16デフォルト化** — `export_onnx`でFP16変換をデフォルト適用し、モデルサイズを約50%削減。`--no-fp16`フラグで無効化可能。LayerNormalization/Sigmoid/SoftmaxはFP32を維持し数値安定性を確保 (#239)

#### Changed

- **全ONNXモデルをFP16に統一 + モデル参照を6lang版に更新** — テストモデル・HuggingFace Spacesモデルを6lang FP16版に統一し、モデルカタログ(piper_plus_voices.json)を6lang版に更新。モデルサイズ約50%削減（77MB→39MB） (#256)
- CMake ExternalProjectをpyopenjtalk-plus PyPI sdistベースに統一（全プラットフォーム共通）
- OpenJTalkをスタンドアロンバイナリから静的ライブラリリンクに変更
- `openjtalk_dictionary_manager.c`にバイナリ相対パスでの辞書検索を追加
- ブランディング統一: "Piper TTS" → "piper-plus" (#232)

### 🎯 Performance

- **ORT SessionOptions最適化** — ONNX Runtimeのセッションオプション調整で10-15%速度向上 (#250)
- **WebUI ONNXセッションキャッシュ** — セッション再利用により83%高速化 (#242)

### 🔧 Improvements

#### Fixed

- **C++マルチリンガルphonemizerの全6言語動作修正** — JA以外の5言語(EN/ZH/ES/FR/PT)が動作しない問題を修正。辞書ファイル(CMU/pypinyin)をビルド成果物に同梱し、辞書検索パスを3段階探索(モデルDir→exe相対→環境変数)に拡充。`--language`指定でラテン文字言語の検出精度向上、辞書未ロード時のgraceful degradation対応 (#254)
- **config.jsonフォールバック検索の統一** — 全コンポーネントで一貫したconfig検索ロジック (#243)
- **Windows学習互換性** — Windows環境での学習パイプライン修正 + prosodyモデル置換 (#232)
- **Dockerビルドトリガー修正** — トリガーブランチをdevに修正 (#228)
- **HuggingFace Spacesデプロイ修正** — Python API呼び出しに変更 (#224)
- ExternalProject並列ダウンロードのレースコンディション修正
- `phoneme_ids.cpp`の`interspersePad=false`パスで未知phonemeによるクラッシュを防止
- CIテストをM1.5のアーキテクチャ変更(静的リンク)に適合

### 📚 Documentation

- **CLAUDE.md大幅リファクタリング** — 6言語対応完了に伴い約60%削減 (#252)
- **ユーザビリティ改善ドキュメント** — クイックスタート再構成・Windows対応ガイド追加 (#241)
- **ドキュメント全面整理・README刷新** (#225)
- READMEにバッジ追加 & 事前学習済みモデルセクション追加 (#217)

### 🧹 Maintenance

- ルートPythonスクリプト整理 (#231)
- Docker環境全面整理・CPU化 (#221)
- 未使用workflow整理 & Python最低バージョン3.11化 (#227)
- Gradio 6.9.0更新 (#226)

## [1.6.0] - 2026-02-11

### 🚀 Major Features

#### Added

- **FP16 Mixed Precisionデフォルト化** + マルチスピーカーモデル修正 (#195)
  - 学習速度2-3倍向上、GPUメモリ約50%削減
  - デフォルトで有効 (`--precision 16-mixed`)
- **OpenJTalk A1/A2/A3 prosody values** の抽出・活用 (#196)
  - Duration Predictorへの韻律情報注入
  - `--prosody-dim 16` でデフォルト有効
- **WavLM Discriminator** (#198, #212)
  - WavLMベースの知覚品質判別器
  - デフォルトで有効（学習時のみ使用、推論に影響なし）
  - FP16 Mixed Precision対応済み
- **GPL-free 英語G2P** - g2p-en (Apache-2.0) ベース (#213)
  - espeak-ng/piper-phonemize (GPL) なしで英語推論が可能
  - ストレスマーカー、機能語処理、文脈依存変換対応
- **Phonemizer ABC + 言語レジストリ** (#215)
  - 抽象基底クラスによるif/elif分岐の解消
  - 新言語追加が容易なプラグイン構造
- **疑問詞マーカー拡張 + 文脈依存「ん」バリアント** (#204, #207, #210)
  - 強調疑問 (`?!`)、平叙疑問 (`?.`)、確認疑問 (`?~`) の区別
  - 後続音に応じた「ん」の発音バリアント (N_m, N_n, N_ng, N_uvular)

#### Changed

- **デフォルト辞書の拡充** — 誤読防止エントリ追加 (#208)

### 🔧 Improvements

#### Fixed

- **ONNXエクスポートで常にdurationsを出力** (#209, #211)
- **英語G2P espeak-ng互換性の改善** (#214)

## [1.5.5] - 2025-09-25

### 🔧 Improvements

#### Fixed

- **Windows環境での日本語TTS文字化け問題** を修正 (#185)
- **Windows PowerShellビルドエラー** 修正 + ワークフローリファクタリング (#182)
- **ARMv7ビルド失敗の修正** + デバッグ機能追加 (#184)

### 📦 Build System

#### Added

- **piper-phonemize-bundled パッケージ** — クロスプラットフォームwheel対応 (#189)
- **ARMビルド用Dockerfile** の追加 (#183)

#### Changed

- PyPIリリースバージョン形式制限の削除 (#190)
- 動的VERSIONファイル更新対応 (dev/pre-release builds) (#191)
- リリースワークフローのバージョン検証順序修正 (#192)

## [1.5.2] - 2025-09-18

### 🚀 Major Features

#### Added

- **Windows版日本語音声合成の完全サポート** (#180)
  - OpenJTalkバイナリをWindows版リリースに含める
  - naist-jdic辞書（40MB）を全プラットフォームに自動同梱
  - Windows環境での日本語TTSが追加設定なしで動作

### 🔧 Improvements

#### Fixed

- **Windows環境でのパス処理の改善**
  - スペースを含むパスでの実行問題を解決
  - 8.3形式短縮パス名の自動使用
  - 一時ファイル処理の最適化

### 📦 Build System

#### Changed

- **CI/CDワークフローの強化**
  - 全プラットフォームでOpenJTalk辞書を自動ダウンロード
  - ビルドアーティファクトに日本語TTS機能を含める
  - Windows/Linux/macOSで統一された日本語音声合成機能

## [1.5.1] - 2025-09-17

### 🔧 Improvements

#### Fixed

- **piper_phonemize UTF-8エンコーディング対応** (#178)
  - テキスト処理でのエンコーディング問題を解決
  - 多言語テキストの安定した処理を実現

- **Windows 11 espeak-ng-dataディレクトリ検出問題** (#177)
  - Windows 11環境でのディレクトリ検出ロジックを改善
  - 自動ダウンロード機能との互換性向上

### 📚 Documentation

#### Added

- **日本語TTS品質向上の技術レポート** (#176)
  - 品質問題の詳細な分析
  - 改善提案と実装ロードマップ

#### Changed

- **ブランディング更新** (#175)
  - プロジェクトロゴの刷新
  - 視覚的アイデンティティの強化

### 🧪 Developer Experience

#### Added

- **PyPiパッケージ改善** (#172)
  - 音素マップモジュールをパッケージに含める
  - インストール後すぐに使える完全な機能セット


## Older Releases

Releases v1.5.0 and prior are archived in [CHANGELOG-archive.md](CHANGELOG-archive.md) for readability.
