# M-Stretch: Strategic Bets — Phase Overview

**親マイルストーン**: [ci-expansion-milestones.md §M-Stretch](../proposals/ci-expansion-milestones.md#m-stretch-strategic-bets-month-4-候補)
**親調査**: [ci-expansion-2026-05.md §3](../proposals/ci-expansion-2026-05.md)
**期間**: Month 4 以降 (M1-M4 完了後の判定で各候補を個別 milestone として起動)
**作成日**: 2026-05-18
**ステータス**: 候補出し段階 (個別チケットなし)

---

## フェーズの狙い

Top 10 外で **unlimited CI を本気で活かすなら検討に値する候補** を 8 件列挙。 親調査 §4 の批判的観点 (「追加しない」が default) を再適用した上で、 工数 / 申請プロセス / dependency が重く Top 10 から外れたが、 中長期で piper-plus エコシステムに大きな価値を生む候補のみを残した。

各候補は **独立した別 milestone** として議論可能で、 本 phase overview はあくまで「候補一覧と判断基準」を提示する。 個別チケットは作らず、 昇格判定後に M5 / M6 等として再ドキュメント化する。

---

## 候補一覧

各候補について以下を記載:

- **目的 / 期待効果**: 何を達成し、 ユーザー / メンテナにどう便益するか
- **主な障壁**: 申請プロセス / 工数 / dependency
- **依存**: どの M を完了している必要があるか
- **概略の実装方針**: workflow ファイル名候補、 想定アーキテクチャ
- **一から設計するなら**: 200-300 字の reinvention
- **個別チケット化する判断基準**: どんな状況になったら正式 milestone に昇格させるか

---

### S1. OSS-Fuzz 申請

**目的 / 期待効果**: Google の無料 fuzz インフラ (OSS-Fuzz) に piper-plus の C API / SSML parser / G2P を harness 登録し、 24/7 fuzz + 自動 Issue 起票 + Google bug bounty 対象化。 親調査 §3.3 で「採択されれば 24/7 fuzz + 自動 Issue 起票 + bug bounty 対象で最大 ROI」と評価された候補。 M4.1 の forward-compat fuzz の延長として位置付け可能。

**主な障壁**:

- OSS-Fuzz 審査プロセス 1-2 週間 (project metadata.yaml 提出 + maintainer email verification)
- libFuzzer 互換 harness の整備 (C API は比較的容易、 Rust は `cargo-fuzz` 経由、 Python は `atheris` 経由で別 harness 必要)
- corpus seed の整備と、 OSS-Fuzz と GitHub Issue の双方向同期設定

**依存**: M4.1 (forward-compat fuzz の harness を libFuzzer 互換に書き換え可能な構造で実装済みであること)

**概略の実装方針**:

- `oss-fuzz/projects/piper-plus/` を OSS-Fuzz 本体 repo に提出 (PR ベース)
- `fuzz/` 配下に harness を 3 種類追加 (`fuzz_c_api.cc`, `fuzz_ssml_rust.rs`, `fuzz_g2p_python.py`)
- `.github/workflows/oss-fuzz-build-check.yml` で OSS-Fuzz 公式の `build_fuzzers` action を CI 化、 push 時に harness 壊れていないか検証
- corpus は `tests/fixtures/fuzz_corpus/` に commit、 OSS-Fuzz 側と sync

**一から設計するなら**: OSS-Fuzz への提出は「外部インフラへの依存追加」というコストがあるが、 piper-plus 規模なら自前 fuzz farm 構築コスト (CI runner + Slack 通知 + Issue auto-create) と比較して圧倒的に安い。 ただし harness 3 種類を 1 度に出すのは reviewer の負荷が高く、 まず C API harness 1 本で申請、 採択後に SSML / G2P を順次追加する段階的アプローチが reviewer experience として最良。 corpus seed は piper-plus 既存 fixture (zh_en_loanword / pua / golden audio fixture) から minimal subset を選定し、 Bloom filter で coverage を上げる戦略を取る。

**個別チケット化する判断基準**:

- M4.1 forward-compat fuzz が完了し、 真の bug を 1 件以上検出した時点
- piper-plus の C API binary が安定し ABI break が 3 ヶ月以上発生していない時点
- メンテナ 1 名が OSS-Fuzz 通知 (Issue auto-create) を確実に対応できる体制が整った時点

---

### S2. Bencher dashboard 導入

**目的 / 期待効果**: 7 ランタイム横断の perf trend を 1 つの dashboard に集約、 PR ごとの sticky comment で regression を可視化、 statistical boundary 検出で「true regression vs noise」を自動判定。 親調査 §3.5 で「Bencher (primary) + GitHub Pages (secondary)」が選定済。 M4 informational tier の dashboard を Bencher に統合可能。

**主な障壁**:

- Bencher project セットアップ + API token 管理
- 既存 gh-pages baseline (`docs/ci-dashboard/data/*.jsonl` 形式) からの移行作業
- 7 ランタイム × N benchmark の adapter 実装 (Bencher は Rust criterion / Python pytest-benchmark / Node.js / Go test -bench / C# BenchmarkDotNet の公式 adapter あり、 C++ Google Benchmark も対応、 Swift / Kotlin は custom adapter 必要)

**依存**: M2 (audio quality moat) の MOS proxy gate が安定後、 trend 表示の data source として活用可能。 M4 (informational tier) の dashboard data を Bencher schema に統一する前提作業を完了していること。

**概略の実装方針**:

- Bencher OSS plan に project 登録 (`piper-plus` namespace)
- `.github/workflows/bencher-publish.yml` を新規追加、 PR / push / schedule 全てで perf data を upload
- `BENCHER_API_TOKEN` を GitHub secret に追加 (OIDC 連携も検討)
- 既存 `multi-runtime-rtf.yml` / `memory-regression.yml` / `bundle-size-gate.yml` の output を Bencher BMF 形式に変換
- Bencher の `bencher run --threshold` でこれまでの informational signal を統合 alerting 化

**一から設計するなら**: 既存 gh-pages 自前 dashboard は維持コストが累積する設計で、 JSON schema / HTML template / publish workflow の 3 重メンテが必要。 Bencher に移行することで JSON schema は Bencher 標準、 HTML は Bencher が hosting、 publish は `bencher run` 1 コマンドに集約され、 piper-plus 側の責務は「BMF 形式に変換」だけになる。 ただし Bencher の OSS plan が将来制限される (storage quota / retention period) リスクがあり、 contingency として「Bencher API で全 raw data を定期 backup → gh-pages に保管」を併用する 2-tier 構成が望ましい。 Bencher は primary、 gh-pages は cold archive、 という役割分担で運用する。

**個別チケット化する判断基準**:

- M4 の dashboard data が 1 ヶ月以上 (~30 data point) 蓄積された時点
- 既存 gh-pages dashboard のメンテに月 5h 以上かかっていることが定量的に確認できた時点
- Bencher の OSS plan policy が安定し、 storage quota が piper-plus の data 量 (現状推定 < 100MB) で十分なことを確認できた時点

---

### S3. Real-device farm

**目的 / 期待効果**: iOS 実機 / Android 実機 / Safari WebKit / Samsung Internet / WeChat WebView 等、 GitHub Actions x86_64 では発見不能な platform-specific bug を CI で検出。 親調査 §3.4 で「iOS 18 WebKit SAB block, Android x86 emulator SIGBUS, M3 Pro Metal MPSGraph assertion, Pi Zero 2W NEON fp16 fallback, Samsung Internet autoplay policy, WeChat WebView WASM SIMD trap」が具体例として列挙された領域。

**主な障壁**:

- Firebase Test Lab (Android 実機 OSS plan) / BrowserStack App Live OSS / Xcode Cloud の各 OSS plan 申請プロセス (それぞれ 1-3 週間)
- 各 service の API integration 工数 (Firebase は `gcloud firebase test android run`、 BrowserStack は REST API、 Xcode Cloud は workflow YAML)
- 実機固有 flake への suppression メンテ (typical real-device farm の最大コスト要因)

**依存**: M3 (ABI hardening) の public ABI snapshot が安定し、 mobile binary が ABI 安定保証された後でないと実機 test の意味が薄い

**概略の実装方針**:

- `.github/workflows/real-device-android.yml`: Firebase Test Lab で API 24-35 + Pixel / Samsung / Xiaomi
- `.github/workflows/real-device-ios.yml`: Xcode Cloud workflow + BrowserStack App Live で iPhone 15/16, iPad, iOS 17/18/26
- `.github/workflows/real-device-browser.yml`: BrowserStack Live + Playwright で Safari iOS, Samsung Internet, WeChat
- service credential は GitHub Environments `real-device-farm` で保護、 fork PR からは access 不可
- 実コスト ≈ ¥200/月 (Raspberry Pi 5 self-hosted の電気代のみ、 親調査 §3.4 参照)

**一から設計するなら**: real-device farm は「3 service × N device」の組み合わせ爆発を抑えるのが設計の中心。 piper-plus は audio output の検証が中心で、 device-specific bug は (a) audio device permission, (b) WASM SIMD instruction support, (c) NEON fp16 fallback の 3 軸に集約される。 ゼロから設計するなら、 これら 3 軸を representative device 1 台ずつ (= 3 device 合計) で daily 検査する minimum coverage を目標とし、 親調査 §3.4 のフル matrix は month-end nightly schedule で隔離する。 PR ごとに real-device を回すと feedback loop が長くなり contributor friction を生むため、 PR では emulator (既存) のみ、 schedule で real-device、 という分離が望ましい。

**個別チケット化する判断基準**:

- M3.1 (Public ABI snapshot) で iOS Swift / Kotlin Android の ABI が 3 ヶ月以上安定維持できた時点
- ユーザーから real-device 固有 bug 報告が 3 件以上累積し、 個別調査コストが累計 10h を超えた時点
- 各 OSS plan service の申請プロセスを並列 1 名で 2 週間で完了できる体制が整った時点

---

### S4. SLSA Build L3 公式 generator 移行

**目的 / 期待効果**: 現状 SLSA L2-3 ハイブリッド相当の release 自動化を、 `slsa-framework/slsa-github-generator` 公式 generator に移行することで **SLSA Build L3 正式準拠 + OpenSSF Scorecard 9.3+** を達成。 親調査 §3.6 で「Week 5-6: SLSA Build L3 公式 generator 移行」と planning 済。

**主な障壁**:

- 5 registry (PyPI / npm / crates.io / NuGet / Maven Central) × 2 PR 程度の作業量
- `slsa-github-generator` の generic generator + container generator + go generator 等の selection
- 既存 cosign 署名 / SBOM 生成との整合性確保 (重複 attestation を避ける)

**依存**: なし (独立に進められる)

**概略の実装方針**:

- 各 publish workflow (`publish-pypi.yml`, `publish-npm.yml`, `publish-crates.yml`, `publish-nuget.yml`, `publish-maven.yml`) に `slsa-framework/slsa-github-generator` の reusable workflow を呼び出すよう書き換え
- 既存 OIDC token 発行経路を維持しつつ、 provenance attestation を Sigstore Rekor に publish
- `release-shared-lib.yml` (C API binary) は generic_generator で対応
- OpenSSF Scorecard の `Signed-Releases` check が 9-10 点になることを確認

**一から設計するなら**: SLSA L3 は「ephemeral build environment + non-falsifiable provenance + isolated build」の 3 条件を満たす必要があり、 GitHub Actions の reusable workflow を介すれば自動的に L3 相当が達成できる。 ゼロから設計するなら自前 publish workflow をすべて捨てて `slsa-framework/slsa-github-generator` のテンプレートに差し替えるのが最短だが、 piper-plus は publish workflow に micro-customization (HF Hub upload, model card 自動注入 等) が多く、 一括移行は破壊的。 段階的に PyPI → npm → crates → NuGet → Maven の順 (依存規模が小さい順) で 5 PR 個別に移行する。 各 PR で破壊変更が起きないよう staging publish (TestPyPI 等) で sanity check するチェーンを設計する。

**個別チケット化する判断基準**:

- M3 完了後、 publish workflow に新規 customization を加える PR が 1 ヶ月以上ない (= 安定期に入った) 時点
- OpenSSF Scorecard score が 8.5 を下回るような new dependency / supply chain regression が起きた時点
- SLSA L3 準拠が政府 / enterprise 顧客の調達要件になったケースが報告された時点

---

### S5. Distroless / Chainguard 移行

**目的 / 期待効果**: `docker/python-inference/Dockerfile`, `docker/webui/Dockerfile`, `docker/wyoming/Dockerfile` 等の container image を distroless (Google) または Chainguard image に移行することで、 attack surface を ~90% 削減 (shell / package manager / system utility を image から除外)。 親調査 §3.6 で「Week 3-4: Distroless / Chainguard 移行」と planning 済。

**主な障壁**:

- piper-plus の Docker image は 7 個 (python-inference, webui, wyoming, csharp-cli, rust-cli, go-cli, c-api) で段階的書き換え必要
- distroless image は debugging が困難 (sh が無い) で troubleshooting 経験の習得コスト
- Python 系は `gcr.io/distroless/python3` が available だが ONNX Runtime の glibc 依存と非互換の可能性

**依存**: なし (独立に進められる) だが、 M2 / M3 完了後の方が image 仕様変更が少なく安定して移行できる

**概略の実装方針**:

- multi-stage build を全 Dockerfile に統一適用: builder stage で deps install + binary build、 runtime stage は distroless
- `cgr.dev/chainguard/python:latest` または `gcr.io/distroless/python3-debian12` を base に選定
- 既存 `.github/workflows/docker-build.yml` の trivy scan + cosign 署名は維持
- 移行順序: webui (Gradio で軽量) → wyoming → python-inference (ONNX 依存で最も検証コスト高)

**一から設計するなら**: distroless 移行の本質は「build-time deps と runtime deps の厳密分離」であり、 Dockerfile を書き換えるだけでなく piper-plus の Python wheel / native dependency 構造を見直す機会でもある。 ゼロから設計するなら、 全 Docker image を `chainguard/<lang>` で統一し、 Chainguard Enterprise の vulnerability tracking と組み合わせる方が長期コスト最適だが、 Chainguard Enterprise は有料。 OSS では `cgr.dev/chainguard/*:latest-dev` で十分。 ただし `:latest-dev` は内容が頻繁に変わるため SHA pin が必須で、 Dependabot 連携を Dockerfile FROM 行で有効化する設計を併せて入れる。

**個別チケット化する判断基準**:

- M3.3 (Typosquatting watch) が安定し、 supply chain 監視体制が整った時点
- container image の CVE 報告が 1 件以上発生し、 base image 更新の必要性が顕在化した時点
- Docker Hub の rate limit や image pull cost が問題化した時点 (Chainguard は無料 image を提供)

---

### S6. Sanitizer 拡張 (全 7 runtime)

**目的 / 期待効果**: C++ ASan / UBSan / TSan、 Rust miri / `-Z sanitizer=address`、 Python `pytest-leaks` + tracemalloc growth、 C# dotMemory Unit、 WASM heap snapshot、 iOS / Android leak nightly を網羅的に有効化することで、 UB / leak / race condition を CI で構造的に検出。 親調査 §3.1 で詳細実装順が定義済。

**主な障壁**:

- ORT 既知 leak の suppression file 維持コスト (各 sanitizer ごとに別 file)
- C++ TSan は false positive が多く、 真の race condition 抽出に試行錯誤
- Rust miri は std collections の internal で false alarm を出すケースあり
- CI 実時間が ~20,400 min/月 (親調査 §3.1) で public repo 無料だが concurrent slot は消費

**依存**: M1.1 (cancelled silent skip 防止) が前提。 sanitizer job が timeout で cancelled になると silent skip リスクが高い

**概略の実装方針**:

- `tools/sanitizer/` ディレクトリに 8 種類の suppression file を集約 (ASan / UBSan / TSan / LSan / miri / dotMemory / heap-snapshot / leak-nightly)
- `ort-known-leaks.md` で ORT 既知 leak の justification を一元管理
- 段階的有効化: PR gate (C++ ASan + UBSan) → nightly (Rust sanitizer, Python pytest-leaks) → weekly (TSan, Valgrind, miri) → monthly (iOS / Android leak)
- 各 sanitizer の output を統一 JSON 形式に変換 (`sanitizer-report-schema.json` 新規) してダッシュボード化

**一から設計するなら**: sanitizer は「false positive 率」と「真の bug 検出率」のトレードオフが各 sanitizer で大きく異なる。 ASan / UBSan は false positive 低く blocker 化可能、 TSan / miri は false positive 高く informational 維持が妥当、 Python pytest-leaks は ORT の C++ leak と区別困難。 ゼロから設計するなら、 各 sanitizer を「tier 化」して PR blocker (ASan/UBSan) / nightly informational (TSan/miri) / weekly research (Valgrind) の 3 段階に明示分類し、 各 tier の昇格基準 (false positive < 5% で 1 ヶ月以上維持) を spec.toml で公式化する。 これにより「sanitizer を有効化するだけで開発が止まる」という典型的失敗パターンを回避できる。

**個別チケット化する判断基準**:

- M4 informational tier の運用が 3 ヶ月以上安定し、 false positive 管理プロセスが確立した時点
- C++ / Rust の UB / memory bug 報告が 1 件以上発生し、 sanitizer の ROI が定量化できた時点
- メンテナ 1 名が sanitizer suppression file の maintenance に月 5h 以下を維持できる見通しが立った時点

---

### S7. Cross-runtime differential testing 完全版

**目的 / 期待効果**: 親調査 §3.2 で列挙された 7 項目 (golden phoneme IDs / golden ONNX inputs / golden audio / streaming vs batch parity / SSML parse tree parity / speaker embedding parity / phoneme timing 7 runtime 拡張) を **新規 workflow `runtime-parity-deep.yml` に集約** して網羅実施。 M4.2 timing monotonicity property test の invariant DSL 化も本 phase でカバー。

**主な障壁**:

- 各ランタイムに `--dump-ort-inputs`, `--dump-ssml-ast`, `--dump-wav`, `--dump-embedding` の 4 種類 dump CLI flag を追加する工数 (7 runtime × 4 flag = 28 cell)
- 浮動小数差を許容する閾値設計 (各ランタイムの ORT provider × OS で drift パターンが異なる)
- 既存 13 parity workflow との重複整理 (PUA / loanword / ORT / version / CLI / lang-id / timing / SSML / text-splitter / voice-catalog / migration / ABI / API-diff)

**依存**: M2.2 (Cross-runtime audio byte parity) が安定後、 残り 6 項目を順次追加していく

**概略の実装方針**:

- 新規 `docs/spec/runtime-parity-deep-contract.toml` で 7 項目の検査 spec を統合管理
- 新規 `.github/workflows/runtime-parity-deep.yml` で 7 job (各項目 1 job) を matrix 化
- 各ランタイムに dump CLI flag を追加 (既存実装で対応していれば flag 名統一のみ)
- 既存 `parity-hub.yml` / `timing-parity.yml` / `ssml-parity.yml` 等は subset として継続、 deep workflow が superset

**一から設計するなら**: piper-plus の既存 13 parity workflow は時系列で incremental に増えた結果、 各 workflow が独自の fixture / 閾値 / report format を持ち、 cross-runtime regression を全体俯瞰できる単一ダッシュボードが存在しない。 ゼロから設計するなら、 全 13 workflow を `runtime-parity-deep.yml` に統合し、 各検査項目を 1 つの `[parity.<category>]` セクションで管理する monolith approach が長期的に最適。 ただし統合は大規模 refactoring で破壊リスクが高いため、 M-Stretch §S7 として独立 milestone 化し、 並走で旧 workflow を deprecate していく 3-6 ヶ月計画を取る。

**個別チケット化する判断基準**:

- M2.2 (Cross-runtime audio byte parity) が 3 ヶ月以上 stable 維持された時点
- 既存 13 parity workflow のメンテコストが月 10h を超えた時点 (統合 ROI が顕在化)
- 真の cross-runtime drift bug が 3 件以上発生し、 各 workflow が個別に検出した重複の整理が必要になった時点

---

### S8. PR preview + nightly canary

**目的 / 期待効果**: PR ごとに preview build (GHCR container / WASM / TestPyPI) を publish して reviewer / contributor が live で動作確認可能にする。 nightly canary で release 前に early adopter community が新機能を試せる体制を構築。 親調査 §3.8 で「Secret 漏洩リスク回避」を重点設計として列挙済。

**主な障壁**:

- fork PR からの secret 漏洩リスク (典型的 Dependabot vulnerability pattern)
- HF Space preview のコスト (CPU runtime / storage)
- crates.io / Maven の immutability 制約 (一度 publish したら yank しかできない、 versioning に注意)
- telemetry / auto-yank は community RFC 必須

**依存**: M1 (defensive foundations) 完了で gateway workflow による fail-closed 化が前提。 M3.3 (typosquatting watch) で supply chain 監視が機能していること

**概略の実装方針**:

- 段階 1: GHCR + WASM preview (secret 不要・最小リスク)
- 段階 2: TestPyPI nightly (yank 容易)
- 段階 3: HF Space preview (cost 中、 環境 isolation 設計後)
- 段階 4: crates.io / Maven は週次 canary に格下げ (immutability リスク)
- 段階 5: telemetry / auto-yank (opt-in 設計と community RFC 必須)
- fork PR は `pull_request_target` + `actions/checkout` の `ref: head.sha` + workflow file は base branch のものを使う安全 pattern (親調査 §3.8 参照)
- HF / Docker token は GitHub Environments `pr-preview-fork` で manual approval gate

**一から設計するなら**: PR preview の本質は「reviewer に live artifact を渡す」だけでなく、 contributor が自分の PR を別 cli installer で試せる self-service feedback loop を作ること。 ゼロから設計するなら、 preview artifact は OSS 標準命名 (`piper-plus-pr-<number>-<sha>`) で統一し、 PR description に installer 1-line command (`pip install piper-plus --index-url ...` 等) を自動 append する PR comment bot を併設するのが UX 最良。 これにより contributor は CI green を待たずに自分の build を `pip install` できる。 ただし fork PR からの secret 漏洩を完全排除する設計 (`pull_request_target` 制約) が前提で、 1 度でも漏洩すると repo 全体の signing key が compromise されるため、 設計レビューを M1 完了の maintainer 2 名以上で実施する必要がある。

**個別チケット化する判断基準**:

- M3 完了後、 publish 経路の security 監査 (OpenSSF Scorecard 9.0+) が達成された時点
- contributor PR が月 5 件以上に達し、 「PR の動作確認のためのローカル build」が contributor friction として顕在化した時点
- HF Hub / Docker Hub の OSS plan が piper-plus の preview cost (推定 月数 GB storage + 数千 pull) を吸収できる確認が取れた時点

---

## マイルストーン昇格判定の共通フレームワーク

各候補が個別 milestone (M5 / M6 / ...) に昇格するかは、 以下の共通フレームワークで判定する。

### 判定タイミング

- M1-M4 完了後 (Month 4 序盤) に 1 度目のレビュー
- 以降、 quarterly (3 ヶ月ごと) に再評価
- 緊急昇格 (例: real-device 固有 bug 報告 / supply chain attack 発生) は ad-hoc に判定可

### 判定 checklist

各候補について以下を満たすかを確認:

- [ ] 親 doc §4 の批判的観点 (「追加しない」が default) を再適用したか
- [ ] 「既存と排他的でない / 既存 gate では構造的に検出不可能 / user-visible damage を防ぐ」の 3 条件のいずれかを満たすか
- [ ] 該当する判断基準 (各 S 節末尾) を全て満たしたか
- [ ] net flat policy: 削除候補とセットになっているか (新規 workflow 追加と同数の削除候補を同時に提示)
- [ ] contributor friction の累積監視: PR comment / Issue で friction 報告が 3 件以下に収まっているか

### net flat policy の徹底

M-Stretch 候補は M1-M4 と比較して **追加 workflow 数が多い** 傾向 (S2 Bencher は 1-2 workflow だが S6 Sanitizer 拡張は 8 種類)。 net flat policy を厳格に適用しないと、 piper-plus の CI 基盤が second-order codebase 化を加速する。

各候補の昇格 PR では:

- 同期間 (1 milestone = 4 週間) に削除候補となる workflow / pre-commit hook / skill を **同数以上** 特定
- 削除候補が見つからない場合は **候補そのものを informational tier に降格** または **延期**
- 削除実施は milestone 完了の必須条件 (4 週間以内に削除しない場合は milestone 未完了扱い)

### contributor friction の累積監視

PR comment / Issue でのフィードバックを `feedback` ラベル付きで集計し、 quarterly review で:

- 「CI が遅すぎる」「contract gate が多すぎる」等の friction 報告が 3 件以上 → 該当 milestone を rollback 検討
- 「初回 PR で何を pass すればいいか分からない」報告 → M1.3 first-PR fast lane の拡張で対応
- 「sanitizer が flake で merge できない」報告 → S6 sanitizer 拡張を informational に降格

---

## 関連リンク

- [親マイルストーン: §M-Stretch](../proposals/ci-expansion-milestones.md#m-stretch-strategic-bets-month-4-候補)
- [親調査: §3 前向き提案 (横断テーマ)](../proposals/ci-expansion-2026-05.md)
- [親調査: §4 批判的観点](../proposals/ci-expansion-2026-05.md)
- [M1 overview](./M1-overview.md)
- [M4 overview](./M4-overview.md) (informational tier との連携)
- [`docs/spec/README.md`](../spec/README.md) (S7 で参照する既存 contract spec 一覧)
- [`.claude/README.md`](../../.claude/README.md) (既存 skill / hook / pre-commit gate)
- [CLAUDE.md](../../CLAUDE.md) (プロジェクト概要)

## 変更履歴

| 日付 | 変更 | 関連 |
|------|------|------|
| 2026-05-18 | 初版作成 (Top 10 外 8 候補を S1-S8 として整理、 共通フレームワーク追加) | M4 overview と同時作成 |
