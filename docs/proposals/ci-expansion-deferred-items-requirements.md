# CI/CD 拡張 Deferred 8 項目 — 要求定義 (Requirements Specification)

**バージョン**: 0.1 (initial draft)
**作成日**: 2026-05-19
**基準ブランチ / HEAD**: `docs/ci-expansion-deferred-items-organize` / `4f2ff86c`
**前提ドキュメント**: [`ci-expansion-deferred-items.md`](ci-expansion-deferred-items.md) (proposal)
**ステータス**: draft (本 doc は 8 項目を実装可能 PR scope に落とすための要求定義)

本ドキュメントは proposal (`ci-expansion-deferred-items.md`) を実装可能な要件に変換したもの。 各項目について **FR (機能要件) / NFR (非機能要件) / AC (受け入れ基準) / CON (制約) / DEP (依存)** を ID 付きで列挙する。 ID 体系は **`<type>-<項目番号>.<連番>`** (例: `FR-3.1` = #3 の機能要件 1 番)。

---

## 1. 目的とゴール

- **G-1**: PR #511 (Defensive Foundations) に乗らなかった 8 項目を、 実装可能な PR scope に分解する。
- **G-2**: 「**Claude Code が実装する部分**」 と「**user の明示判断が必要な部分**」 の責任分界を、 各要件ごとに明文化する。
- **G-3**: 受け入れ基準を **自動検証可能** な形に落とし、 PR Test Plan のテンプレート化に資する。
- **G-4**: 各項目の優先度・依存関係を明示し、 Tier 1 (即着手) / Tier 2 (個別 PR) / Tier 3 (別 milestone) に振り分ける。

---

## 2. 用語定義

| 用語 | 定義 |
|------|------|
| **Tier 1** | PR #511 直後に着手可能な単独・小規模 PR (~半日 Claude Code 実装) |
| **Tier 2** | 個別 PR で 1 spec / 1 phase ずつ進める中規模 PR |
| **Tier 3** | 別 milestone (Distroless / SLSA L3 / mkdocs) として独立、 設計判断要 |
| **informational tier** | workflow が `continue-on-error: true` で job 自体は green を返す gate。 drift は sticky comment / report で可視化 |
| **blocker tier** | drift 検出時に PR を block (CI fail) する gate |
| **canonical** | 単方向 truth source (例: Python が canonical、 他 runtime は mirror) |
| **silent-zero** | PR #511 phase 2 で発覚した failure mode: 集計値が 0 のまま success 扱いされる落とし穴 |
| **drift** | canonical と mirror、 docs と impl の不一致 |

---

## 3. スコープ

### 3.1 対象 (in scope)

- 8 項目 (`#1` Distroless / `#2` SLSA L3 / `#3` Rekor + SHA drift / `#4` CLI help / `#5` spec sync / `#6` mkdocs / `#7` doc examples / `#8` test aggregation)
- 既存 31 spec / 62 check script / 108 workflow との **補完関係** での拡張

### 3.2 対象外 (out of scope)

- Wave 3 deferred T14-T28 系 (`docs/spec/wave3-deferred-proposals.toml` で管理される別線、 ~155 件)
- PR #511 で既実装の Top 10 + §3 軽量 5 件
- 学習側 (`src/python/piper_train/`) / runtime ロジック / G2P 言語追加
- piper-plus model 学習・配布 (HF release は #6 / #8 の dashboard 化対象外)

---

## 4. 機能要件 (Functional Requirements)

### 4.1 #1 Distroless / Chainguard 移行

**FR-1.1**: 6 Dockerfile (`python-inference` / `webui` / `wyoming` / `cpp-inference` / `cpp-dev` / `python-train`) のうち、 distroless 化対象を user が選定可能であること。 `python-train` は GPU CUDA toolkit 依存のため **対象外** と明示区別する。

**FR-1.2**: 各対象 image は base image を `cgr.dev/chainguard/<base>` または `gcr.io/distroless/<base>` に置換しても entrypoint が正常起動すること。 multi-stage build (builder stage で gcc/make、 final stage で distroless) を許容する。

**FR-1.3**: **1 PR で 1 image** を canary 移行する。 全 image 一括移行は **禁止**。 PR template に「対象 image 名」 を必須項目として記載する。

**FR-1.4**: 移行後 image の **image size** と **CVE 数** を baseline と比較するレポートを PR コメントに自動投稿する (`docker/<image>/distroless-report.md` 形式)。

**FR-1.5**: image tag 戦略を user が明示決定する (a) 既存 tag を置換、 (b) `piper-plus:<ver>-distroless` を別 tag で並行配信。

**AC-1.1**: 各 image 移行 PR は以下を満たすこと:

- (a) `docker compose up <service>` で起動成功
- (b) image size **50%+ 削減** (例: 150MB → 75MB 以下)
- (c) `trivy image --severity HIGH,CRITICAL` で CVE 数 **80%+ 削減**

**AC-1.2**: HF Space (`python-inference`) と Home Assistant (`wyoming`) の deploy 後動作確認手順を、 各 PR の Test Plan に user 手動 step として記載すること。

**CON-1.1**: `python-train` は GPU base image (`nvidia/cuda:12.x`) 制約により distroless 化対象外。 ドキュメントに明示。

**CON-1.2**: `pyopenjtalk` C 拡張 build は multi-stage builder で対応 (final stage は distroless)。

**DEP-1.1**: `hadolint.yml` (既存) の rule pass を維持。

**DEP-1.2**: `docker-build.yml` / `docker-test.yml` matrix に新 image を追加。

---

### 4.2 #2 SLSA Build L3

**FR-2.1**: SLSA L3 attestation の対象 release workflow を、 本ブランチ HEAD 時点の **実態の release path** から再選定する:

| 候補 | 既存 / 新設 |
|------|-----------|
| `release-shared-lib.yml` (xcframework / AAR) | 既存 |
| `release-kotlin-g2p.yml` (Maven Central) | 既存 |
| `g2p-rust-publish.yml` (crates.io) | 既存 |
| `g2p-go-publish.yml` (Go module tag) | 既存 |
| `npm-publish.yml` (npm) | 既存 |
| `release-pypi.yml` (PyPI) | **新設要否を user 判断** |
| `release-nuget.yml` (NuGet) | **新設要否を user 判断** |

**FR-2.2**: 各 workflow に `slsa-framework/slsa-github-generator/.github/workflows/generator_generic_slsa3.yml` を sub-workflow として追加し、 provenance attestation (`*.intoto.jsonl`) を release asset に upload する。

**FR-2.3**: **1 PR で 1 registry**。 各 PR は以下 3 set を含む:

- (a) workflow 改変
- (b) `v1.13.0-rc.X` での RC release 実行
- (c) `slsa-verifier verify-artifact` で attestation 検証

**FR-2.4**: hermetic build 化のため `workflow_dispatch.inputs.version` 入力は廃止、 `git tag` から version を抽出する pattern に統一する。

**FR-2.5**: SLSA verifier の使い方を `docs/reference/slsa-verify.md` (新規) に記載する (downstream user が手元で検証可能にする)。

**AC-2.1**: 各 registry PR は以下コマンドが exit 0 を返すこと:

```bash
slsa-verifier verify-artifact <asset> \
  --provenance-path <intoto.jsonl> \
  --source-uri github.com/ayutaz/piper-plus \
  --source-tag v1.13.0-rc.X
```

**AC-2.2**: OpenSSF Scorecard で `Token-Permissions` / `SAST` 以外の項目で score が下がらないこと (baseline = PR #511 マージ後の Scorecard 値)。

**AC-2.3**: Maven Central (AAR / JAR) は既存 GPG 署名と attestation が **共存** すること (GPG 検証も SLSA verify も両方 pass)。

**CON-2.1**: PyPI / NuGet dedicated release workflow が現状不在のため、 (a) 新設、 (b) `dev-create-release.yml` 経路活用、 のどちらを取るかは user 判断。

**CON-2.2**: Maven Central は AAR と JAR で classifier が違うため、 attestation の `subject` 構成は別途設計。

**DEP-2.1**: `cosign-release-artifacts.yml` の keyless 署名と SLSA provenance 生成を併用し、 干渉しないこと。

**DEP-2.2**: 各 release workflow で `permissions: id-token: write` を確保 (OIDC token 必須)。

---

### 4.3 #3 Sigstore Rekor + Action SHA drift 監視

**FR-3.1**: Rekor verify workflow `.github/workflows/rekor-verify.yml` を新設 (**informational tier**、 weekly schedule `0 3 * * 1`)。 直近 N=10 release の cosign 署名を Rekor transparency log 経由で再検証する。

**FR-3.2**: Action SHA drift detector `scripts/check_action_sha_drift.py` (~100 行) を新設。 全 `.github/workflows/*.yml` から `uses: <action>@<sha>` を抽出し、 GitHub API (`/repos/{owner}/{repo}/commits/{sha}`) で resolve、 dangling / force-pushed を検出する。

**FR-3.3**: baseline JSON `scripts/action_sha_baseline.json` を初回 scan で生成し、 commit する (既知 OK を吸収)。

**FR-3.4**: `.github/workflows/action-sha-drift.yml` (informational tier、 weekly `0 4 * * 1`) で上記 script を実行。

**FR-3.5** *(silent-zero 防止)*: informational tier の落とし穴回避のため、 sticky comment / report に以下を **初版から組み込む**:

- 期待値との大きな乖離 (例: 集計が 0 件) を検出した場合に `::warning::` を立てる
- defensive log `Collected pins (N actions): ...` を必ず stderr に echo

**FR-3.6**: drift 検出時に **Issue auto-create** する (`gh issue create --label "action-sha-drift" --title "Action SHA drift: <action>"`)。

**AC-3.1**: weekly run **4 週連続で false positive 0**、 または検出された false positive を baseline で吸収可能。

**AC-3.2**: GitHub API rate limit (5000 req/h) 内に収まる (現行 pin 約 270 個 × 1 req = 270 req、 safety margin 大)。

**AC-3.3**: silent-zero 防止が機能: 「Pins compared: N」 の N が baseline の半分未満なら `::warning::` 出力 (fixture test で再現)。

**AC-3.4**: Rekor verify-blob が最新 10 release で exit 0、 cosign 導入前の古い release は skip 条件分岐で除外。

**CON-3.1**: blocker tier 化は false positive 4 週間観測後に user 判断。 初版は informational tier 固定。

**CON-3.2**: org / repo deletion (`unmaintained/some-action`) と force-push attack は区別困難 → trend 化で対応。

**DEP-3.1**: `cosign-release-artifacts.yml` (既存) で生成された `.sig` / `.pem` を artifact として再 download 可能。

**DEP-3.2**: `action-pin-gate.yml` の baseline (`scripts/action_pins_baseline.txt`) を流用可能 (形式は併存)。

---

### 4.4 #4 7 runtime CLI help auto-extract

**FR-4.1**: 残 6 runtime (Rust / C# / Go / WASM / C++ / G2P-py) の `--help` 出力を `docs/reference/cli-help/<runtime>.txt` に自動抽出する。 Python は既存 `cli-help-docs-sync.yml` を **統合または並存** で扱う。

**FR-4.2**: `.github/workflows/cli-help-extract.yml` (weekly + manual + PR base trigger) で全 runtime を build → `--help` 出力 → `git diff --exit-code` で drift 検出。

**FR-4.3**: non-determinism (version string `piper-plus 1.12.0-dev` / build timestamp / absolute path) を post-process で sanitize する rule を runtime ごとに spec 化し、 `scripts/sanitize_cli_help.py` (~80 行) に集約する。

**FR-4.4**: auto-commit 戦略は **「drift 検出時 CI fail のみ、 auto-commit しない」** に固定 (branch protection と互換)。 drift 修正は人手 PR で対応。

**FR-4.5**: Android G2P (CLI 不在) は対象外、 Swift G2P `examples/swift-g2p/HelloG2P` は library 本体ではないため対象外と明示。

**AC-4.1**: 6 runtime ぶんの `<runtime>.txt` が repo に commit され、 weekly run で drift 0 (informational tier)、 PR 変更で drift 検出時に CI fail。

**AC-4.2**: 既存 `cli-help-docs-sync.yml` の Python path 動作を破壊しない (`--mode stale-only` + 13 flag allow-list を維持または統合先に migrate)。

**AC-4.3**: build cache (Rust target / WASM emsdk / C++ ORT) を利用し、 wall clock **10 分以内** (NFR-1.1 準拠)。

**CON-4.1**: CI minute 増 (build matrix で +約 8 分 wall clock、 concurrent queue 圧迫)。 user が CI minute 影響を merge 前に確認 (NFR-1.1 で抑制)。

**CON-4.2**: 各 runtime の `--help` 表示順序が build target 切替で変わるケースは sanitizer で吸収。

**DEP-4.1**: 既存 `cli-flag-contract.toml` + `check_cli_flag_parity.py` (flag **存在**) と補完関係、 重複なし (本 FR は **wording 出力**)。

---

### 4.5 #5 spec contract toml ↔ impl 同期 gate

**FR-5.1**: 残カバレッジ穴 5 spec について個別 gate を実装する。 **1 spec / 1 PR** の cadence:

| spec | 状態 | 推奨実装順 |
|------|------|----------|
| `release-versions.toml` | 穴 | 1 (高 ROI、 release 事故予防) |
| `model-sha256-manifest.toml` | 穴 | 2 (release artifact 完全性) |
| `artifact-retention-contract.toml` | 穴 | 3 (workflow retention 一貫性) |
| `swift-g2p-contract.toml` | 穴 | 4 (Swift package surface) |
| `test-flake-retry-contract.toml` | 穴 | 5 (retry policy) |

**FR-5.2**: 各 gate は以下 3 set を備える:

- (a) check script `scripts/check_<spec>.py`
- (b) pre-commit hook 統合 (`.pre-commit-config.yaml`)
- (c) workflow 統合 (`<spec>-gate.yml` または既存 `contract-gates-extended.yml` に追加)

**FR-5.3**: 一部 spec が「**実装側 canonical const が存在せず、 toml は post-hoc snapshot 用途**」 と判明した場合、 spec doc を rewrite して位置付けを変更する (例: `release-versions.toml` = git tag の snapshot)。

**FR-5.4**: 全 gate は `tests/scripts/test_check_<spec>.py` で **fixture-based** な intentional violation の検出を保証する。

**AC-5.1**: 各 spec gate は以下を満たすこと:

- (a) intentional violation を fixture で再現
- (b) 検出 → exit 1 で fail
- (c) 修正 → exit 0 で pass

**AC-5.2**: `pre-commit run --all-files` で全 check script の合計 wall clock が **30 秒以内** (NFR-1.2 準拠)。

**AC-5.3**: 5 spec gate 全完了後、 `docs/spec/` のカバレッジ穴が **0** になり、 `wave3-deferred-proposals.toml` 等の別線 spec は対象外として明示される。

**CON-5.1**: 「universal な validator」 は構造的に作れない、 個別実装が現実解 (CON-5 として記録)。

**CON-5.2**: 優先順位は user の運用判断、 上記 FR-5.1 の順序は **推奨** のみ。

**DEP-5.1**: 既存 [meta] schema (`scripts/check_spec_meta.py`) に各新 spec が準拠。

**DEP-5.2**: `release-versions.toml` の gate は git tag を canonical 入力として扱う (cross-ref で `release-shared-lib.yml` の tag 抽出 logic を再利用)。

---

### 4.6 #6 mkdocs-material 統合配信

**FR-6.1**: `mkdocs.yml` を新設、 nav 階層 (Getting Started → Runtimes → API Reference → Migration → Spec) と i18n plugin (`mkdocs-static-i18n`) と内蔵検索を構成する。

**FR-6.2**: `.github/workflows/docs-deploy.yml` で build + Pages deploy。 既存 `deploy-webassembly-demo.yml` (WASM demo) / `deploy-huggingface.yml` (HF Space) と Pages site path が衝突しないこと (path namespace 設計)。

**FR-6.3** *(user 明示判断必要)*: 公開範囲を user が決定する:

- `.claude/` (内部用) → 除外
- `docs/proposals/` (roadmap) → user 判断
- `docs/migration/` / `docs/guides/` / `docs/reference/` → 公開

**FR-6.4** *(user 明示判断必要)*: i18n 戦略を user が決定する:

- (a) 既存 `README.md` / `README-ja.md` 二重 mirror を維持
- (b) `mkdocs-static-i18n` の `i18n/{en,ja}/` 構造に移行

**FR-6.5** *(user 明示判断必要)*: Pages 配信先を user が決定する:

- (a) GitHub Pages (`piper-plus.github.io/piper-plus/`)
- (b) Cloudflare Pages / Netlify (`docs.piper-plus.dev` 等の custom domain)
- (c) HuggingFace Spaces

**FR-6.6**: 既存 `~150 .md` の link 修正 (相対 path → mkdocs nav-relative) を mass edit で実施。 修正対象数は約 500 箇所と見積もる。

**AC-6.1**: deploy 後の dashboard URL が公開アクセス可能、 内蔵検索が `q=ssml` 等の query で適切な doc を返す。

**AC-6.2**: 既存 `https://github.com/ayutaz/piper-plus/blob/dev/docs/migration/v1.11-to-v1.12.md` 等の inbound link は **維持** (mkdocs 配信は重複 URL として共存、 dead link 化させない)。

**AC-6.3**: `link-check.yml` (既存) が mkdocs nav-relative path に対応した上で全 link が解決。

**CON-6.1**: 設計判断 3 件 (FR-6.3 / FR-6.4 / FR-6.5) は user の明示意思決定が必要。 **proposal → user 承認 → 実装** の 2 phase を取る。

**CON-6.2**: 別 milestone (Docs Infra) として独立、 本 8 項目とは別線。 本要求定義からは「**user 承認待ち**」 として entry のみ残す。

**DEP-6.1**: `link-check.yml` の検査対象 path を mkdocs build 後に追従。

**DEP-6.2**: Sphinx (Python) / Rustdoc / TypeDoc 等の API doc 生成物との external section 連携は別 PR。

---

### 4.7 #7 Code example execution test

**FR-7.1**: 既存 `scripts/check_readme_code_examples.py` (シンボル grep) と **補完関係** の実行ベース doctest gate を新設する (既存 script は置換しない)。

**FR-7.2**: `scripts/check_doc_examples.py` (~200 行) で `docs/` 配下の fenced code block を言語別 (`bash` / `python` / `rust` / `csharp` / `go` / `wasm`) に抽出し、 以下を skip:

- placeholder pattern (`<path>` / `<{placeholder}>`)
- `# doctest:skip` directive
- `# noexec` directive

Skip 条件に該当しないブロックを実 subprocess で実行する。

**FR-7.3** *(user 明示判断必要)*: placeholder 規約を user 合意のもと制定する。 推奨:

- `<{placeholder}>` 形式に統一
- `# doctest:skip` directive で明示 skip
- bash 例は `set -euo pipefail` 強制注入

**FR-7.4** *(audit phase)*: PR-A として **既存 docs の audit** を先行実施。 `check_doc_examples.py --audit` で全 example の実行可否を JSON 化、 Issue 化して user 確認 (修正 / skip / placeholder 化 の 3 カテゴリ振り分け)。

**FR-7.5** *(gate phase)*: PR-B で doctest gate を **informational tier** で導入。 audit 結果を反映した skip directive 付き。

**FR-7.6** *(promotion phase)*: PR-C で **1 ヶ月の informational 観測**後に **blocker tier 昇格判定** を user に提示。 昇格 / 据え置きは user 判断。

**AC-7.1** *(audit phase)*: audit で「修正可能 / skip 妥当 / placeholder 化適切」 の 3 カテゴリ集計が完了し、 件数別に Issue 化されること。

**AC-7.2** *(gate phase)*: doctest gate informational tier 1 ヶ月運用で **false positive 率 5% 以下**。

**AC-7.3**: ONNX model download は GitHub Actions cache (~250MB) に乗せ、 doctest 実行ごとの再 download を避ける (HF rate limit / 安定性回避)。

**AC-7.4**: bash 例の falsy success (`;` 連結で中間 step 失敗) を `set -euo pipefail` 注入で防止 (fixture test で再現)。

**CON-7.1**: 既存 `check_readme_code_examples.py` (識別子 grep) を置換せず、 補完関係を維持。

**CON-7.2**: 7 runtime + 8 言語 + ONNX model + GPU optional の組合せを 1 workflow に詰めると CI 30+ 分。 matrix 分割と cache 戦略で抑制。

**DEP-7.1**: ONNX model fixture (`/data/piper/...` または HF download) が CI 環境で利用可能。

**DEP-7.2**: 各 runtime の toolchain setup (Rust / dotnet / emsdk / etc.) が既存 CI 環境にある。

---

### 4.8 #8 Test result aggregation

**FR-8.1**: 7 runtime の test 結果を **JUnit XML 形式** で統一出力する設定を各 CI workflow に追加する:

| runtime | reporter |
|---------|----------|
| Python | `pytest --junit-xml=test-results.xml` (既出) |
| Rust | `cargo test -- --format json \| cargo2junit` (追加) |
| C# | `dotnet test --logger:junit` (既出) |
| Go | `gotestsum --junitfile=test-results.xml` (追加 — gotestsum 導入) |
| WASM | `jest --reporters=jest-junit` (追加) |
| C++ | `ctest --output-junit` (既出、 CMake 3.21+) |
| Kotlin | gradle test (JUnit XML 自動出力、 既出) |

**FR-8.2**: `scripts/aggregate_test_results.py` (~150 行) で 7 runtime artifact から JUnit XML を集約、 `test-aggregate.json` を生成する。

**FR-8.3**: aggregated JSON を `runtime-parity-deep` workflow と同型 pattern で sticky comment 化 (audio parity の 15-pair sticky の **test 結果版**)。

**FR-8.4**: `/check-cross-runtime` skill との住み分けを明文化する:

- **skill** = loanword / PUA / G2P parity 検証 (内容)
- **aggregator** = test 統計 (件数 / pass-fail / skip / duration)

**FR-8.5**: flake retry 履歴を集計対象に含める (retry 1 回で pass を「pass with retry」 として可視化、 silent flake 検出)。

**AC-8.1**: 7 runtime 全 test 結果が 1 sticky comment に集約され、 各 runtime の pass / fail / skip / duration / retry-count が一覧表示。

**AC-8.2**: 「**last green commit が全 runtime で揃っているか**」 の judgment column を sticky に含む (release readiness signal)。

**AC-8.3**: aggregator script は audio parity gate (`compare job` の argparse `nargs="*"` last-wins bug) と同型の落とし穴を踏まない: 集計件数を必ず defensive log で stderr に出力 (silent-zero 防止)。

**CON-8.1**: 「test 1 件」 の定義が runtime 間で揃わない (Rust mod / C# class / WASM jest statement) → 集計時に粒度を明示注記。

**CON-8.2**: dashboard 配信 (mkdocs) は別線 (#6)、 本項目は **JSON artifact + sticky comment** までで完了とする。

**CON-8.3**: aggregator が「retry 1 回で pass」 を「pass」 単純カウントすると flake 検出が機能しない → retry 履歴必須 (FR-8.5)。

**DEP-8.1**: 既存 `coverage-aggregation.yml` の artifact pattern を流用。

**DEP-8.2**: Go test に `gotestsum` 導入が必要 (Go 標準ではない)、 別 PR で先行導入推奨。

**DEP-8.3**: `runtime-parity-deep` workflow (PR #511 で導入) の sticky comment pattern を流用。

---

## 5. 非機能要件 (Non-Functional Requirements)

### NFR-1 性能

**NFR-1.1**: 各新規 workflow の wall clock は **10 分以内** (build 重ワークフロー基準、 既存 `cpp-tests.yml` 等と整合)。
**NFR-1.2**: `pre-commit run --all-files` の wall clock は **30 秒以内** (現状運用 budget)。
**NFR-1.3**: GitHub API 利用 workflow の rate limit safety margin は **30%+** (`GITHUB_TOKEN` 5000 req/h 制限内)。

### NFR-2 セキュリティ

**NFR-2.1**: GITHUB_TOKEN permissions は `contents: read` を default、 必要時のみ `write` (least privilege)。
**NFR-2.2**: 新規 action 利用は SHA pin (`@v<X.Y.Z>` または 40-hex SHA) 必須、 sliding `@v<major>` 禁止 (`action-pin-gate.yml` で強制)。
**NFR-2.3**: secret は環境変数として渡し、 workflow YAML に hardcode しない (`check_secret_path_reference.py` で検出)。

### NFR-3 保守性

**NFR-3.1**: 新規 check script は `scripts/check_<topic>.py` 命名規約に従い、 必ず `tests/scripts/test_check_<topic>.py` を伴う。
**NFR-3.2**: informational tier の workflow は **silent-zero 落とし穴** を回避する defensive log (`Collected <unit> (N runtimes): ...` パターン) を必須実装。
**NFR-3.3**: spec contract toml は `[meta]` schema (`check_spec_meta.py`) 準拠。
**NFR-3.4**: 新規 workflow は既存 `concurrency:` group / `paths:` filter / `timeout-minutes:` を踏襲。

### NFR-4 互換性

**NFR-4.1**: 既存 31 spec / 62 check script / 108 workflow との重複検証なし、 **補完関係のみ**。
**NFR-4.2**: Python 3.11 / 3.13、 Rust stable、 Go 1.26、 dotnet 10、 Node 20+ の matrix に対応。
**NFR-4.3**: pre-commit hook version pin は `.pre-commit-config.yaml` の `rev:` と CI workflow / `pyproject.toml` の 6 箇所 sync (`check_ruff_version_sync.py` 準拠)。

### NFR-5 観測性

**NFR-5.1**: 各新規 informational gate は drift trend を **Issue auto-create** で可視化する。
**NFR-5.2**: sticky comment に「**期待値 vs 実測値**」 を明示、 silent zero (0 件 silent 成功) を構造的に防止 (NFR-3.2 と対)。
**NFR-5.3**: 各 workflow run に `Collected <unit>: N` を必ず stderr に echo (PR #511 phase 2 argparse bug の教訓)。

---

## 6. 優先度マトリクス (実装順)

| Tier | 項目 | 推奨実装順 | 単独 PR 可否 | user 判断 |
|------|------|---------|-----------|----------|
| Tier 1 | `#3` Rekor + SHA drift | 1 | ✅ | informational tier 固定 |
| Tier 1 | `#4` CLI help auto-extract | 2 | ✅ | CI minute 影響確認 |
| Tier 2 | `#5` (a) `release-versions.toml` | 3 | ✅ | spec rewrite 必要可 |
| Tier 2 | `#5` (b) `model-sha256-manifest.toml` | 4 | ✅ | — |
| Tier 2 | `#7` (a) audit phase (PR-A) | 5 | ✅ | placeholder 規約決定 |
| Tier 2 | `#5` (c-e) 残 3 spec | 6-8 | ✅ | 優先順位 |
| Tier 2 | `#7` (b) doctest informational (PR-B) | 9 | ✅ | — |
| Tier 2 | `#7` (c) blocker 昇格 (PR-C) | 10 | ✅ | 昇格判定 |
| Tier 3 | `#1` Distroless (1 image/PR × 5) | 11-15 | ✅ | image 戦略 + HF/HA 検証 |
| Tier 3 | `#2` SLSA L3 (1 registry/PR × 5-7) | 16-22 | ✅ | release path 選定 |
| Tier 3 | `#6` mkdocs | 別 milestone | (proposal phase) | 公開範囲 / i18n / 配信先 |
| Tier 3 | `#8` Test aggregation | `#6` と coupling | ✅ (#6 後) | aggregator vs skill 住み分け |

---

## 7. リスク

### R-1: informational tier silent-zero pattern 再発

**影響**: PR #511 phase 2 と同型の bug が新規 gate で発生 → 数週間気付かない。
**緩和**: NFR-5.2 / NFR-5.3 で sticky comment の期待値明示と defensive log を必須化。 fixture test で silent-zero 再現を保証 (AC-3.3 / AC-8.3)。

### R-2: SLSA L3 release breakage blast radius

**影響**: 5 release workflow を同時改変すると next release 全 registry が ship 不能。
**緩和**: 1 registry / 1 PR で段階導入 (FR-2.3)、 各 PR で v1.13.0-rc.X RC release 検証。

### R-3: mkdocs link 移行による外部 inbound link 死亡

**影響**: GitHub Issue / 外部 blog 記事からの `https://github.com/ayutaz/piper-plus/blob/dev/docs/...` link が dead 化。
**緩和**: GitHub raw URL を canonical 互換維持 (AC-6.2)、 mkdocs 配信は重複 URL として共存。

### R-4: Distroless 移行による HF Space / HA 互換性破壊

**影響**: HF Space cold start 失敗、 HA addon supervisor 互換性喪失。
**緩和**: 1 image / 1 PR (FR-1.3)、 user による手動 deploy 動作確認を Test Plan に必須化 (AC-1.2)。

### R-5: spec sync gate 追加で pre-commit 時間 budget 超過

**影響**: pre-commit hook が 30 秒超過 → developer experience 悪化。
**緩和**: 各 check script を fast-path 実装 (`changed-files` 限定実行 / cache 利用)、 NFR-1.2 を超えた場合は pre-push tier に移行。

### R-6: doctest gate が ONNX model download で flake

**影響**: HF rate limit / 通信不安定で CI が間欠 fail。
**緩和**: AC-7.3 で GitHub Actions cache に乗せる、 retry policy を `test-flake-retry-contract.toml` (#5 にて gate 化) で統一。

### R-7: 7 runtime CLI help auto-extract で CI minute 圧迫

**影響**: 6 build matrix で +8 min wall clock、 PR cycle time 悪化。
**緩和**: build cache 利用 (AC-4.3)、 weekly schedule に集約、 PR base trigger は `paths:` で限定。

---

## 8. 受け入れ基準サマリー

各項目の主要 AC を要約:

| 項目 | 主要 AC | 検証方法 |
|------|--------|---------|
| `#1` Distroless | image size 50%+ 削減 + CVE 80%+ 削減 + HF/HA 動作 | `trivy image` + user 手動 deploy |
| `#2` SLSA L3 | `slsa-verifier verify-artifact` exit 0 + Scorecard 維持 | CI workflow + Scorecard re-run |
| `#3` Rekor + SHA drift | weekly 4 週連続 false positive 0 + silent-zero 検出 | informational tier 観測 + fixture test |
| `#4` CLI help | 6 runtime help.txt commit + drift 0 | `git diff --exit-code` |
| `#5` spec sync | 5 spec gate 完備 + `test_check_*` 全 pass | unit test (`pytest tests/scripts/`) |
| `#6` mkdocs | dashboard 公開 + 検索動作 + inbound 維持 | manual + `link-check.yml` |
| `#7` doc examples | audit Issue + informational 1 ヶ月 fp 5% 以下 | trend metric + sticky comment |
| `#8` test aggregation | 7 runtime test 集約 sticky + last-green column | sticky comment 表示 |

---

## 9. 用語と参照

- **親 proposal**: [`ci-expansion-deferred-items.md`](ci-expansion-deferred-items.md)
- **既存 spec contract**: `docs/spec/*.toml` (31 件)
- **既存 check script**: `scripts/check_*.py` (62 件)
- **既存 workflow**: `.github/workflows/*.yml` (108 件)
- **skill / hook 仕様**: [`.claude/README.md`](../../.claude/README.md)
- **Wave 3 deferred 別線**: [`docs/spec/wave3-deferred-proposals.toml`](../spec/wave3-deferred-proposals.toml)
- **PR #511 (Defensive Foundations)**: 本要求定義の前提となる 10 CI gate + 軽量 5 件の実装 PR
- **PR #498 (Wave workflow 自動化)**: spec 穴を 12→5 に縮小した実装 PR

---

## 10. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 (v0.1 draft) — ブランチ `docs/ci-expansion-deferred-items-organize` で proposal から要求定義を抽出。 8 項目 × FR/NFR/AC/CON/DEP の ID 付き要件、 優先度マトリクス、 リスク 7 件、 受け入れ基準サマリーを定義。 | Claude Code |
