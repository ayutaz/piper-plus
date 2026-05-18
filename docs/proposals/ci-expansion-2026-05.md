# CI/CD 拡張プラン (Unlimited CI 前提の網羅調査)

**作成日**: 2026-05-18
**前提条件**: 「CI 時間とマシンが無制限」(OSS public repo として GitHub Actions は実質無料、 concurrent slot のみ制限)
**目的**: piper-plus の **OSS としての品質** と **開発イテレーション速度** の向上
**調査体制**: 30 エージェント並列調査 (現状監査 10 + 領域別ギャップ分析 10 + 前向き提案 10)

> このドキュメントは「ロードマップ提案」であり、 実装決定ではない。 各項目は採用判断の議論起点として扱う。

---

## 目次

- [0. エグゼクティブサマリ](#0-エグゼクティブサマリ)
- [1. 現状診断](#1-現状診断)
- [2. 領域別ギャップ](#2-領域別ギャップ)
- [3. 前向き提案 (横断テーマ)](#3-前向き提案-横断テーマ)
- [4. 批判的観点 — なぜ追加しないが default か](#4-批判的観点--なぜ追加しないが-default-か)
- [5. 真に追加する価値があるトップ 10](#5-真に追加する価値があるトップ-10)
- [6. 3 ヶ月実装ロードマップ](#6-3-ヶ月実装ロードマップ)
- [7. 留保事項](#7-留保事項)

---

## 0. エグゼクティブサマリ

piper-plus は **93 workflow + 100+ pre-commit hook + 20 skill + 19 contract spec.toml** で構成された **第二級コードベース化した CI 基盤** を持つ、極めて成熟したプロジェクト。 「Unlimited CI」を額面通り受け取って網羅的に追加すると **メンテナンス税が逆に開発速度を毀損** する。

結論: **「追加すべきでない」を default として、 既存で構造的に検出不可能な領域に絞ってトップ 10 を選定**。 具体的には以下 3 軸:

1. **音声品質の user-visible regression** (現状は RTF / メモリ / バイナリサイズの gate のみで、 PESQ / UTMOS / WER が空白)
2. **7 ランタイム間の差分テスト深化** (現状は phoneme timing と fixture byte 一致のみで、 audio output / ORT input tensor / SSML AST / speaker embedding が空白)
3. **既存 gate の構造欠陥修復** (PR #419 で発覚した「cancelled silent skip」、 contributor onboarding 障壁)

---

## 1. 現状診断

### 1.1 全体規模

- **93 workflow** (PR trigger: 78%, push: 63%, schedule: 10%, release: 2%)
- **schedule cron 9 本のうち 6 本が月曜 UTC 朝に集中** → GitHub Actions outage 時の SPOF
- **paths filter 70% 適用** (差分 CI が機能している)
- **self-hosted / large runner ゼロ** (全 GitHub-hosted)

### 1.2 既存 gate のカバレッジ

| 領域 | 既存 | 評価 |
|------|------|------|
| Format / Lint | ruff / cargo-fmt / gofmt / golangci-lint / dotnet-format / mypy / pyright / clang-tidy / markdownlint / codespell / hadolint / actionlint | **過剰なほど厚い** |
| Cross-runtime parity | 13 workflow (PUA / loanword / ORT / version / CLI / lang-id / timing / SSML / text-splitter / voice-catalog / migration / ABI / API-diff) | **業界トップクラス** |
| 性能・品質 | RTF (6 runtime × 3 length) / memory / bundle size / mutation / fuzz smoke / parity-hub | **良好だが audio 品質と cross-runtime audio diff が空白** |
| セキュリティ | CodeQL / secret-scan / SBOM / Trivy / cosign / dependency-review / license / security-audit / action-pin | **SLSA L2-3 ハイブリッド相当、 OpenSSF Scorecard 7-8 推定** |
| Release / publish | PyPI / npm / crates / NuGet / Maven / HF Hub / GHCR / GitHub Releases、 全て SLSA provenance attestation 済 | **強い。 nightly / canary が空白** |

### 1.3 既存 CI の健康状態 (直近 1000 run / ~36h)

- success **92.0%** / cancelled **5.8%** / failure **1.9%**
- 真の test bug は 19 件、 ほぼ全部 issue-499 ブランチ作業中の差分
- cancelled 58 件のうち **49 件が 5 PR に集中** (force-push churn) — 単一ブランチで 33 件
- ARM64 (QEMU) と Docker レーンが平均 25-37 分で支配的、 重量級 4 レーン (ARM64×2 + Docker×2 + rust-tests) が CI 経過時間の大半

### 1.4 構造的弱点 (PR #419 教訓)

Multi-Runtime RTF / Memory regression / CodeQL の baseline 検証が **cancelled で silently skip** された履歴あり。 「validation green に見えるが実は何も verify されていない」リスクが現存。

---

## 2. 領域別ギャップ

### 2.1 各ランタイム ROI トップ提案

| Runtime | 即実装の最優先 | 理由 |
|---------|---------------|------|
| **Python** | (1) argparse snapshot, (2) import-time bench, (3) pip-audit, (4) wheel install smoke, (5) ORT version matrix 1.17-1.20, (6) Py 3.13t free-threading | 低コスト × 高 ROI が 6 個積み上がる |
| **Rust** | (1) `cargo-deny check all` gate、 (2) MSRV + stable + beta matrix、 (3) **cargo-semver-checks**、 (4) cargo-criterion 連続 bench | semver 違反は publish 後修正不可 |
| **C#** | (1) **NativeAOT publish smoke**、 (2) **NuGet 公開後 install smoke (matrix 6 cell)**、 (3) dotnet-format CI gate、 (4) Trim warning 0 gate、 (5) net8 / net9 / net10 multi-TFM matrix | LTS 用途と AOT は将来 mobile 配信の前提条件 |
| **Go** | (1) golangci `errorlint / revive / gocyclo` を warn → error 昇格、 (2) **go test -fuzz** を phonemize / ssml に、 (3) `go mod tidy -diff` drift gate、 (4) golden file drift detection | Go 1.18+ ネイティブ fuzz が piper-plus #346 / #499 系 drift に直結 |
| **JS / WASM** | (1) **Playwright Browser matrix** (Chrome / FF / WebKit)、 (2) Node 20 / 22 / 24 matrix、 (3) **Deno + Bun smoke**、 (4) **dist tarball install smoke**、 (5) heap snapshot leak、 (6) 3-bundler integration、 (7) TS API diff | npm 0.6.0 publish 事故 (data 漏れ) は publish 後でないと検出不可 |
| **C++ / C API** | (1) **TSan dedicated job**、 (2) **libFuzzer for C API**、 (3) **OSS-Fuzz 申請** (Google 無料インフラ)、 (4) gcov + Codecov、 (5) ABI baseline を libabigail abidiff に拡張、 (6) compiler matrix (gcc 11-14 / clang 16-19 / MSVC) | C API は外部入力点、 ABI 境界 crash 検出力最大 |
| **Mobile** | (1) **Android emulator matrix API 24-35** + Firebase Test Lab、 (2) iOS Simulator UI test、 (3) **JNI ABI compat check**、 (4) Privacy manifest validation、 (5) ARM64 simulator (M1+)、 (6) R8 / ProGuard 最適化検証 | 顧客報告 bug の温床、 unlimited CI なら network of devices で網羅可能 |

### 2.2 音声品質 (現状空白の最重要領域)

**Tier 1 (PR gate 候補)**:

1. **Cross-runtime audio byte parity** (SHA256 + RMSE 閾値 + chromaprint fingerprint)
2. **PESQ / STOI 自動評価** (つくよみちゃん 50 文 fixture × 6 言語)
3. **ASR-based WER** (Whisper-large-v3 で書き起こし → WER < 15%、 G2P regression を実音声で検出)
4. **Voice cloning identity verification** (reference WAV ↔ 合成 WAV の ECAPA-TDNN embedding cosine ≥ 0.7)
5. **Streaming vs batch 出力一致** (v1.12.0 breaking の core contract)

**Tier 2 (nightly)**: UTMOS / pitch contour / long-form / SSML タイミング / silence padding A/B/C 品質。

### 2.3 ONNX / モデル

1. **ONNX checker + shape inference clean pass** (低コスト・最優先)
2. ORT version matrix (1.16-1.20) で output MAE 検証
3. ONNX op coverage report (ORT mobile / WebGPU EP の supported op list と diff)
4. Tensor shape regression
5. **Speaker embedding L2 norm + cosine 一致 (全 6 runtime)**
6. HF artifact attestation (SHA256 pin と CLI auto-DL 検証)

### 2.4 学習パイプライン

**CPU で即着手** (低コスト・高 ROI):

- ONNX export E2E (tiny ckpt → export → inference → audio sanity)
- dataset 前処理 golden (`prepare_multilingual_dataset.py`)
- checkpoint loading regression
- VAD energy threshold (~25x 高速化変更後の品質 pinning)
- **HiFi-GAN ckpt 明示エラー regression** (v1.12.0 migration 契約保証)
- Phoneme ID consistency (PUA contract 連動)

**GPU runner 確保後**: training smoke (1 epoch tiny) / resume lossless / mixed precision drift。

---

## 3. 前向き提案 (横断テーマ)

### 3.1 Sanitizer 拡張

**実装順**:

1. C++ ASan + UBSan を PR gate に昇格 (既存 workflow_dispatch only を `pull_request` に昇格)
2. Rust `-Z sanitizer=address` pure crate のみ
3. Python `pytest-leaks` + tracemalloc growth gate
4. C# dotMemory Unit
5. WASM heap snapshot (Playwright + CDP `HeapProfiler`)
6. C++ TSan / Valgrind nightly
7. iOS / Android leak nightly
8. Rust miri nightly

**Suppression 一元管理**: `tools/sanitizer/` 配下に集約、 ORT 既知 leak は `ort-known-leaks.md` で justification 必須化。

**CI minutes**: ~20,400 min/月 (public repo 無料、 macOS billing も 10x で実質無料)。

### 3.2 Cross-runtime differential testing

新規 workflow `runtime-parity-deep.yml` に 7 項目を集約:

1. **Golden phoneme IDs** (Python canonical, byte 一致、 ZH-EN 混在 / SSML break / PUA / N バリアント網羅)
2. **Golden ONNX inputs** (`--dump-ort-inputs` flag を 7 runtime 全実装、 npz 比較)
3. **Golden audio** (SNR ≥ 60 dB / mel-spec MSE ≤ 1e-3、 浮動小数差を許容)
4. Streaming vs batch parity (各 runtime 内 self-consistency)
5. **SSML parse tree parity** (Rust canonical の AST JSON 化、 byte 一致)
6. Speaker embedding parity (cosine ≥ 0.9995)
7. Phoneme timing 7 ランタイム拡張 (Swift / Kotlin G2P 追加)

設計詳細は本ドキュメント末尾の関連 spec 候補 (`docs/spec/runtime-parity-deep-contract.toml` を将来作成) を参照。

### 3.3 Property-based & Fuzzing 拡張

**継続価値 Top 5**:

1. **OSS-Fuzz 連携** (c_api / SSML / G2P、 Google 無料計算インフラ、 申請 1-2 週間)
2. **Differential fuzzing: text_splitter 7 ランタイム** (#346 / #499 系 drift の構造的再発防止)
3. **Differential fuzzing: Python ↔ Rust G2P** (loanword / PUA 10 mirror 同期は byte gate 済みだが出力等価性未検証)
4. Python hypothesis を SSML / 8 言語 G2P / dict loader / PUA / timing / voice catalog に全展開
5. Rust proptest: streaming.rs 状態機械

**Mutation testing 拡張**: Go (gremlins) / JS (Stryker) / C++ (mull)。週次。

### 3.4 Real-device CI farm

**5 本柱**:

| 領域 | サービス | 用途 | コスト |
|---|---|---|---|
| Android 実機 | Firebase Test Lab | API 24-35 + Pixel / Samsung / Xiaomi 物理デバイス | OSS 5 device-hour/day 無料 |
| iOS 実機 | BrowserStack App Live OSS plan + Xcode Cloud | iPhone 15/16, iPad、 iOS 17/18/26 並走 | BS OSS = 5 並列無制限分; XC Cloud = 25h/month 無料 |
| ブラウザ | BrowserStack Live OSS + Playwright + GitHub Actions | Safari iOS、 Samsung Internet、 WeChat WebView 等 | OSS plan 無料 |
| Apple Silicon | GitHub Actions `macos-14` / `macos-15` (M1) + Xcode Cloud | M1 native runner は GA free | 無料 |
| Linux ARM | GitHub Actions `ubuntu-22.04-arm` + 自前 Raspberry Pi 5 self-hosted | Pi / Jetson の native build | 電気代のみ |

**実コスト ≈ ¥200/月 (電気代のみ)**。

**検出できる典型 bug** (GH Actions x86_64 では発見不能): iOS 18 WebKit SAB block, Android x86 emulator SIGBUS, M3 Pro Metal MPSGraph assertion, Windows ARM WoW64 遅延, Pi Zero 2W NEON fp16 fallback, Samsung Internet autoplay policy, WeChat WebView WASM SIMD trap。

### 3.5 Continuous performance dashboard

**Platform 選定**: **Bencher (primary) + GitHub Pages (secondary)**

- Codspeed は Rust / Python / Node のみで 7 ランタイム未対応のため不採用
- Datadog はエンタープライズ機能豊富だが OSS では費用構造が見合わない
- Bencher は OSS 無料 + multi-language adapter + statistical boundary 検出 + sticky PR comment

**継続収集すべき指標 (追加)**:

- インストール後 cold-start (process spawn → ready) 時間
- First-token latency (streaming で最初の音声 chunk 到達)
- Per-language MOS / PESQ / STOI を nightly で
- Bundle compressed sizes (gzip / br / zstd 3 種類)
- WASM compile time
- Import time / module load
- CI workflow duration (meta-metric)

### 3.6 Supply-chain hardening (推奨ロードマップ 6 週)

| Week | 実施 | Scorecard 予想 |
|------|------|----------------|
| 1 | **OpenSSF Scorecard CI 化** + branch protection audit + **typosquatting 防衛** (PyPI / npm scope 予約) | 7.5 → 8.5 |
| 2-3 | Sigstore Rekor verification + Action SHA drift 監視 (revoked / force-pushed 検出) | 8.5 → 9.0 |
| 3-4 | Distroless / Chainguard 移行 (python-inference / webui / wyoming) | 9.0 |
| 5-6 | SLSA Build L3 公式 generator (`slsa-framework/slsa-github-generator`) 移行 | 9.0 → 9.3 |
| 7+ | OSS-Fuzz 申請 → reproducible spot check (Rust / Go binary 限定) | — |

### 3.7 Docs / i18n / CHANGELOG

**Tier S (即効性高、 ROI 圧倒)**:

1. CHANGELOG keep-a-changelog 形式 validator + breaking-change → migration cross-ref 強制
2. **README.md ⇔ README-ja.md 構造一致 gate** (heading tree AST 比較)
3. 7 ランタイム CLI help auto-extract → `docs/reference/cli-help/<runtime>.txt` を auto-commit

**Tier A (中期)**: spec contract toml ⇔ implementation 同期 gate / mkdocs-material 統合配信 / code example execution test (multi-runtime doctest)。

### 3.8 PR preview & nightly canary

**実装順**:

1. GHCR + WASM preview (secret 不要・最小リスク)
2. TestPyPI nightly (yank 容易)
3. HF Space preview (cost 中、 環境 isolation 設計後)
4. crates.io / Maven は週次に格下げ (immutability リスク)
5. telemetry / auto-yank (opt-in 設計と community RFC 必須)

**Secret 漏洩リスク回避**: fork PR は `pull_request_target` で **必ず** `actions/checkout` の `ref: head.sha` + workflow file は base branch のものを使う (Dependabot vulnerability pattern 回避)。HF / Docker token は GitHub Environments `pr-preview-fork` で manual approval gate。

### 3.9 CI observability

**ROI トップ 3**:

1. **CI flake / cancel / skip dashboard** (`/watch-ci-patterns` skill の data layer 化、 PR #419 silent skip 再発防止)
2. **Test result aggregation** (7 runtime の test を統合表示、 `/check-cross-runtime` と接続)
3. **Build artifact size trend** (bundle-size-gate を dashboard 化)

**Datadog / Trunk / BuildPulse は不採用** (vendor lock-in、 自前 aggregator + GitHub Pages が piper-plus 文化に合う)。

---

## 4. 批判的観点 — なぜ「追加しない」が default か

piper-plus は既に 93 workflow + 100+ pre-commit hook を持ち、 **CI 基盤自体が second-order codebase** になっている。 新規追加を議論する前に、 以下の cost を直視すべき。

- **メンテナンス税の指数化**: workflow 1 つ ≒ 月 1h (action 版上げ / flaky 調査 / log 読解)。93 本なら 93h/月 = エンジニア 0.6 FTE 相当を「CI 守り」に費やしている計算。 **新規追加は既存削除とペアが原則**。
- **signal-to-noise の閾値割れ**: PR #419 で「cancelled が silently skip され baseline 検証が事実上 no-op」が起きた。 検査が多いほど誰も log を読まなくなり、 green / red の意味が空洞化する。 Hypothesis nightly や fuzzer のような確率的検査は特に「flake = 無視」が常態化する。
- **queue contention**: OSS public で minute 無制限でも、 concurrent runner 数は実用上シリアル化される。 Linux runner だけで 60+ ジョブ並ぶ PR では、 人間が結果を待つ tail latency が 30 分を超える。 これは contributor 体験を直接劣化させる。
- **"CI as a moat" 誤謬**: 18+ contract gate を通すための前提知識 (PUA contract、 loanword sync、 ORT pin、 ruff version 6 箇所同期) は初回 contributor には事実上 unlearnable で、 PR が merge されない原因になる。 Gate を増やすほど「メンテナ以外は PR を出せない」プロジェクトに収束する。
- **breaking change の真のコスト**: v1.11 → v1.12 で発生したのは CI でなく **migration doc / runtime parity** の問題。 CI で防げた割合は限定的で、 追加 gate の限界効用は逓減している。

**結論**: **「追加すべきでない」が baseline**。 以下のトップ 10 は「既存と排他的でない / 既存 gate では構造的に検出不可能 / user-visible damage を防ぐ」の 3 条件を満たすもののみ。

---

## 5. 真に追加する価値があるトップ 10

| # | 項目 | ROI | 難易度 | 検出 bug カテゴリ |
|---|------|-----|--------|------------------|
| 1 | **音声品質 MOS proxy gate** (PESQ / STOI / ViSQOL、 golden 10 sample) | 高 | 中 | 音声品質回帰 (user-visible 最致命) |
| 2 | **Cross-runtime audio byte-parity diff** (7 runtime × 3 model の waveform hash) | 高 | 中 | 計算順序差 / FP16 drift / decoder 差 |
| 3 | **Migration guide lint** (CHANGELOG breaking 節 ↔ `docs/migration/` cross-ref 強制) | 高 | 低 | doc drift / migration 欠落 |
| 4 | **Public ABI snapshot** (C API / Swift / Kotlin の JSON snapshot 化、 非互換変更で fail) | 高 | 中 | semver 違反 / silent ABI break |
| 5 | **First-PR fast lane** (新規 contributor の PR は contract gate を warning に降格、 コア lint のみ blocker。 merge 前に手動で full gate) | 高 | 低 | 新規 contributor 離脱 (斜め視点) |
| 6 | Loanword / PUA "未来仕様" forward-compat fuzz (`schema_version: 99` のランダム未来フィールドを 7 ランタイムに食わせ panic / exception しないこと) | 中 | 中 | forward-compat regression |
| 7 | **Model card / license 自動付与** (HF release 生成の ONNX 同梱物に LibriTTS-R / AISHELL-3 / CML-TTS の attribution を build 時 injection) | 中 | 低 | license 不備 (斜め視点、 法務リスク) |
| 8 | **Typosquatting / supply-chain 監視** (PyPI / npm / crates / NuGet / Maven の "piper-pIus" / "piper_plus_g2p" 類似名を週次 scan、 issue 起票) | 中 | 低 | supply chain (斜め視点) |
| 9 | Phoneme timing temporal monotonicity property test (Hypothesis で 1000 ケース、 ただし **PR ブロックせず informational** に留め signal noise を避ける) | 中 | 中 | timing 計算 bug |
| 10 | **Cancelled / skipped baseline alarm** (PR #419 再発防止: required check が cancelled で終わった場合、 merge button を block する gating job を 1 つだけ追加) | 高 | 低 | CI 構造欠陥 (既存 gate の盲点) |

**斜め視点採用**: #5 (onboarding) / #7 (license attribution の audio asset への自動付与) / #8 (typosquatting 監視、 ecosystem 認知の防衛側)。Carbon footprint は piper-plus が training を手動運用しているため CI で測る価値が薄く不採用。Issue auto-labeling は GitHub 標準で十分なため不採用。

---

## 6. 3 ヶ月実装ロードマップ

### Month 1 (defensive, ROI 即時回収)

`#10 cancelled baseline alarm` → `#3 migration lint` → `#5 first-PR fast lane` の 3 本。

いずれも難易度低、 既存 gate の構造欠陥 / contributor onboarding / breaking change discipline を底上げし、 新規メンテナンス税が最小。

### Month 2 (audio quality moat)

`#1 MOS proxy gate` を 10 golden sample + ViSQOL で導入し、 並行して `#2 cross-runtime byte-parity` の waveform hash diff を 3 model に絞って試験投入。

MOS gate は最初 4 週間 informational で false positive 率を測り、 安定したら blocker 化。

### Month 3 (ABI / ecosystem hardening)

`#4 public ABI snapshot` を C / Swift / Kotlin の 3 面で運用開始、 `#7 license attribution` を `release-shared-lib.yml` に組込、 `#8 typosquatting 週次 scan` を schedule 化、 `#6 / #9` forward-compat fuzz と timing property test は **informational tier** で追加し signal noise の蓄積を回避する。

### 運用ルール (重要)

各月末に **「追加 workflow と同数の既存 workflow を削除候補としてレビュー」** する maintenance budget rule を運用ルールとして固定化することを強く推奨する (net flat policy)。

---

## 7. 留保事項

- **GPU runner**: training smoke / WER (Whisper) / UTMOS は GPU 必要。 self-hosted (RTX 3090 / 中古 V100) を Tailscale で繋げば月 ¥3000 程度の電気代で実現可能。
- **Carbon footprint estimation**: training を手動運用しているため CI で測る価値が薄く不採用。
- **Issue auto-labeling**: GitHub 標準で十分。
- **Reproducible builds 完全実施**: Python wheel / NuGet の timestamp embed のため ROI 低、 Rust binary + Go binary の 2 つに絞り informational のみ。
- **OSS-Fuzz**: 審査 1-2 週間、 採択されれば 24/7 fuzz + 自動 Issue 起票 + bug bounty 対象で最大 ROI。
- **完全 hermetic build (Bazel / Nix への全面移行)**: 工数 200+ 時間、 ROI なし。 既存 GitHub Actions の OIDC + pinned runner image で「実用上 hermetic」と判定。
- **install-time cosign 強制 (失敗で install block)**: ユーザビリティ毀損、 verify は opt-in ドキュメント止まりが妥当。

---

## 関連ドキュメント

- [`docs/spec/README.md`](../spec/README.md) — 既存 contract spec の一覧 (19 toml)
- [`docs/reference/README.md`](../reference/README.md) — 既存設計書の一覧
- [`docs/migration/v1.11-to-v1.12.md`](../migration/v1.11-to-v1.12.md) — breaking change 事例
- [`.claude/README.md`](../../.claude/README.md) — 既存 skill / hook / pre-commit gate
- [`CLAUDE.md`](../../CLAUDE.md) — プロジェクト概要

## 調査体制 (備考)

本ドキュメントは 30 並列エージェントによる以下の調査結果を統合したもの:

- **Wave 1 (現状監査、 10 agents)**: workflow 全 93 本のトリガー集計 / pre-commit 全 hook の分類 / 7 ランタイム test カバレッジ / 性能・品質 gate / セキュリティ gate / parity gate / CI 健康レポート / release 自動化 / skill 自動化 / OS × version matrix
- **Wave 2 (領域別ギャップ、 10 agents)**: Python / Rust / C# / Go / JS-WASM / C++ / Mobile / Audio quality / ONNX-quantization / Training pipeline
- **Wave 3 (前向き提案、 10 agents)**: Sanitizer 拡張 / Cross-runtime differential / Property-fuzzing / Real-device farm / Performance dashboard / Supply-chain hardening / Docs-i18n-CHANGELOG / PR preview-canary / CI observability / 最終 synthesizer (批判的レビュー + Top 10 選定)
