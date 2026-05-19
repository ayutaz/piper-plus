# CI/CD 拡張 Deferred 8 項目 — 要件定義書 (System Requirements Definition)

**バージョン**: 0.1 (initial draft)
**作成日**: 2026-05-19
**基準ブランチ / HEAD**: `docs/ci-expansion-deferred-items-organize` / `00ea9fde`
**ステータス**: draft (Tier 1 = #3 / #4 を詳細化、 Tier 2 / Tier 3 は overview レベル、 後続フェーズで詳細化)
**読者**: 実装者 (Claude Code) と maintainer / reviewer

---

## 1. 概要

### 1.1 目的

本ドキュメントは [`ci-expansion-deferred-items-requirements.md`](ci-expansion-deferred-items-requirements.md) (要求定義 v0.1) で定義された FR / NFR / AC / CON / DEP を、 **実装可能な仕様レベル** まで詳細化することを目的とする:

- **I/O 仕様**: 各 workflow / script の入出力 (型 / format / path)
- **データ構造**: baseline JSON schema / config TOML schema
- **API / CLI インタフェース**: コマンドライン引数 / exit code / 環境変数
- **処理シーケンス**: 各機能のステップ列 (mermaid 図 or 番号付きフロー)
- **トリガー条件**: workflow の event / paths filter / schedule
- **既存資産との接続点**: 既存 31 spec / 62 check script / 108 workflow との具体的 wiring

### 1.2 上流ドキュメントとの階層

```text
ci-expansion-deferred-items.md                          (proposal v0.2、 PR #511 後の整理版)
        │
        ├──→ ci-expansion-deferred-items-requirements.md  (要求定義 v0.1、 FR/NFR/AC/CON/DEP の ID 付き列挙)
        │           │
        │           └──→ 本ドキュメント (要件定義書、 Tier 1 を I/O・シーケンス・data model まで詳細化)
        │
        └──→ docs/spec/*.toml                            (実装後の不変条件、 本ドキュメントから派生)
```

**用途の住み分け**:

| ドキュメント | 答える問い |
|------------|----------|
| proposal | **何が defer されたか、 何故か** |
| 要求定義 (v0.1) | **何を満たせば良いか** (FR/NFR/AC) |
| 要件定義書 (本書) | **どう実装するか** (I/O / data model / sequence) |
| spec contract toml | **実装後、 何を不変に保つか** (post-implementation) |

### 1.3 スコープ

**Tier 1 (本書で詳細化、 即実装可能なレベル)**:

- §3.1 `#3` Sigstore Rekor + Action SHA drift 監視
- §3.2 `#4` 7 runtime CLI help auto-extract

**Tier 2 / Tier 3 (本書では overview のみ、 後続要件定義 PR で詳細化)**:

- §4.1 `#5` spec contract toml ↔ impl 同期 gate (5 spec)
- §4.2 `#7` Code example execution test
- §4.3 `#1` Distroless / Chainguard 移行
- §4.4 `#2` SLSA Build L3
- §4.5 `#6` mkdocs-material 統合配信
- §4.6 `#8` Test result aggregation

---

## 2. システム全体構成

### 2.1 既存 CI システム概要

本ブランチ HEAD 時点の関連資産:

| 資産 | 数 | 役割 |
|------|----|------|
| `.github/workflows/*.yml` | 108 | CI gate / build / deploy |
| `scripts/check_*.py` | 62 | gate logic 本体 (canonical) |
| `docs/spec/*.toml` | 31 | 不変条件 spec (single source of truth) |
| `tests/scripts/test_check_*.py` | 14 | gate logic の unit test |
| `.pre-commit-config.yaml` | 1 | pre-commit hook 集約 (50+ hook) |
| `.codespell-ignore-words.txt` | 1 | codespell exception list |

### 2.2 既存資産との接続点 (Tier 1 範囲)

```text
#3 Rekor + SHA drift
   │
   ├──→ scripts/check_action_pins.py        (既存)  ← pattern 流用 (REPO_ROOT / regex / classify)
   ├──→ scripts/action_pins_baseline.txt    (既存)  ← baseline 形式の参考
   ├──→ .github/workflows/action-pin-gate.yml (既存) ← 形式 gate (本機能と併存)
   ├──→ .github/workflows/cosign-release-artifacts.yml (既存) ← Rekor 発行側
   └──→ marocchino/sticky-pull-request-comment@v2.9.4 ← sticky pattern

#4 CLI help auto-extract
   │
   ├──→ .github/workflows/cli-help-docs-sync.yml (既存) ← Python path 統合先候補
   ├──→ scripts/check_cli_help_drift.py     (既存)  ← Python drift 検出 logic
   ├──→ docs/spec/cli-flag-contract.toml    (既存)  ← runtime 6 件の path 定義
   ├──→ scripts/check_cli_flag_parity.py    (既存)  ← flag 存在検証 (補完関係)
   └──→ docs/guides/development/cli-usage.md (既存) ← canonical 出力先候補
```

### 2.3 新規追加資産の総量見積もり

| 項目 | 新規 workflow | 新規 script | 新規 doc / fixture | 新規 spec toml |
|------|-------------|------------|------------------|-------------|
| `#3` | 2 (`rekor-verify.yml`, `action-sha-drift.yml`) | 2 (`check_action_sha_drift.py`, `verify_rekor_releases.py`) | 1 (`action_sha_baseline.json`) | 0 |
| `#4` | 1 (`cli-help-extract.yml`) | 1 (`sanitize_cli_help.py`) | 6 (`docs/reference/cli-help/*.txt`) | 0 (`cli-flag-contract.toml` 流用) |
| **Tier 1 合計** | **3** | **3** | **7** | **0** |

---

## 3. 機能要件詳細 (Tier 1)

### 3.1 `#3` Sigstore Rekor + Action SHA drift 監視

#### 3.1.1 機能概要

本機能は 2 つの独立した監視 (3a / 3b) を 1 つの目的 (供給網改竄検出) で束ねる:

- **3a Rekor verify**: 自前 release artifact の cosign 署名を Rekor transparency log で再検証 (発行 → 検証の双方向化)
- **3b Action SHA drift**: 全 workflow の `uses:` SHA pin を GitHub API で resolve、 dangling / force-pushed を検出 (`action-pin-gate.yml` の形式強制を補完)

両者とも **informational tier** で開始、 4 週間運用後に blocker 昇格を maintainer 判定。

#### 3.1.2 ユースケース

| UC ID | アクター | シナリオ |
|-------|--------|---------|
| UC-3.1 | weekly cron | 月曜 03:00 UTC に Rekor verify が直近 10 release を検証、 全 pass なら artifact 保存のみ |
| UC-3.2 | weekly cron | 月曜 04:00 UTC に SHA drift detector が全 pin (~270 件) を resolve、 dangling 検出時 Issue auto-create |
| UC-3.3 | maintainer | 手動 `workflow_dispatch` で baseline 再生成 (`--update-baseline`) |
| UC-3.4 | PR contributor | 新 action pin 追加時、 PR の SHA drift gate が新規 pin を baseline 経由で許容 |
| UC-3.5 | incident response | force-push attack 疑い時、 `verify_rekor_releases.py --release v1.13.0` で個別 release を検証 |

#### 3.1.3 入力仕様

**3a Rekor verify**:

| 入力 | 型 | source |
|------|----|----|
| release tag list | `string[]` | `gh release list -L 10 --json tagName` |
| artifact URL | `string` | `gh release view <tag> --json assets` |
| `.sig` / `.pem` | `bytes` | release asset (cosign 生成) |

**3b SHA drift detector**:

| 入力 | 型 | source |
|------|----|----|
| workflow YAML | `string[]` | `.github/workflows/*.yml` (glob) |
| `uses:` ref | `string` (例: `actions/checkout@abc123...`) | regex 抽出 |
| baseline JSON | `dict` | `scripts/action_sha_baseline.json` |
| GitHub API response | `dict` | `GET /repos/{owner}/{repo}/commits/{sha}` |

#### 3.1.4 出力仕様

**3a Rekor verify**:

- **artifact**: `rekor-verify-report.md` (markdown 表、 release × verify status)
- **stderr 必須 log**: `Verified releases (N total): tag=v1.13.0 status=pass ...`
- **exit code**: 0 = 全 pass / 1 = いずれかの release verify 失敗 (informational tier では 1 でも CI green)
- **Issue auto-create 条件**: 1+ release が verify 失敗 (label: `rekor-verify-failure`)

**3b SHA drift detector**:

- **stdout sticky markdown** (PR run 時):

  ```markdown
  ## Action SHA drift report

  **Collected pins (N actions): <list of `org/repo@sha` summary>**

  | Action | Pinned SHA | Resolved | Status |
  |--------|------------|----------|--------|
  | actions/checkout | abc123... | abc123... → tag `v6.0.2` | OK |
  | foo/bar | def456... | (404 not found) | **DANGLING** |

  Summary: total=270, ok=268, dangling=1, force-pushed=1
  ```

- **exit code**: 0 = no drift / 1 = drift 検出 (informational tier では `continue-on-error: true`)
- **`::warning::` 出力条件**: `total < baseline.expected_total * 0.5` (silent-zero 防止、 NFR-5.3 準拠)

#### 3.1.5 データ構造

**`scripts/action_sha_baseline.json` schema**:

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-19T03:00:00Z",
  "expected_total_pins": 270,
  "allowlist": [
    {
      "action": "actions/checkout",
      "sha": "abc123def4567890abc123def4567890abc12345",
      "resolved_tag": "v6.0.2",
      "verified_at": "2026-05-19T03:00:00Z",
      "note": "(optional) why allowed"
    }
  ],
  "ignore_actions": [
    "unmaintained/some-action"
  ]
}
```

**`tests/fixtures/rekor-verify/golden_release.json`** (3a 用 fixture):

```json
{
  "release_tag": "v1.13.0",
  "assets": [
    {"name": "libpiper_plus-linux-x64.tar.gz", "sig": "...", "pem": "..."}
  ],
  "expected_verify": "pass"
}
```

#### 3.1.6 処理シーケンス

**3b SHA drift detector** (毎週月曜 04:00 UTC):

```text
1. checkout repo                                          ← actions/checkout@v6.0.2
2. setup-python (3.13)                                    ← actions/setup-python@v5.6.0
3. pip install requests                                   ← GitHub API client
4. python scripts/check_action_sha_drift.py
   a. glob .github/workflows/*.yml
   b. regex `uses: ([^\s#]+)@([0-9a-f]{40})` で抽出
   c. baseline JSON load
   d. 各 SHA を GET /repos/{owner}/{repo}/commits/{sha} で resolve
      - 200 OK + tag/branch 紐付け → ok
      - 200 OK だが tag/branch なし → dangling
      - 404 → force-pushed 疑い (要追加調査、 dangling として report)
   e. silent-zero check: total < expected_total * 0.5 なら stderr に ::warning::
   f. markdown report 生成
   g. summary を artifact upload
5. PR run: marocchino/sticky-pull-request-comment で投稿
6. drift 検出時 + scheduled run: gh issue create (label: action-sha-drift)
```

**3a Rekor verify** (毎週月曜 03:00 UTC):

```text
1. checkout repo
2. install cosign (sigstore/cosign-installer@v3.X)
3. for tag in $(gh release list -L 10 --json tagName -q '.[].tagName'):
   a. gh release download $tag --pattern '*.tar.gz' --pattern '*.sig' --pattern '*.pem'
   b. cosign verify-blob --rekor-url https://rekor.sigstore.dev \
        --certificate-identity-regexp "https://github.com/ayutaz/piper-plus" \
        --certificate-oidc-issuer https://token.actions.githubusercontent.com \
        --signature <sig> --certificate <pem> <artifact>
   c. 結果を /tmp/rekor-report.md に append
4. 全 pass → artifact upload only / 1+ fail → gh issue create
```

#### 3.1.7 トリガー条件

| workflow | trigger | paths filter | schedule | concurrency |
|---------|---------|-------------|---------|-------------|
| `rekor-verify.yml` | `schedule` + `workflow_dispatch` | — | `0 3 * * 1` (月曜 03:00 UTC) | `rekor-verify-${{ github.run_id }}` (concurrent 不可) |
| `action-sha-drift.yml` | `schedule` + `pull_request` + `workflow_dispatch` | `.github/workflows/**.yml`, `scripts/check_action_sha_drift.py`, `scripts/action_sha_baseline.json` | `0 4 * * 1` (月曜 04:00 UTC) | `action-sha-drift-${{ github.head_ref \|\| github.ref }}` |

#### 3.1.8 エラーケース / 例外処理

| ケース | 期待動作 |
|-------|---------|
| GitHub API rate limit 到達 | `time.sleep(60)` + 最大 3 回 retry、 全失敗で exit 2 (informational tier では noop) |
| `cosign verify-blob` exit ≠ 0 | release を「verify 失敗」 として記録、 ループ継続 |
| baseline JSON 不在 | 初回 scan で生成、 `--update-baseline` flag 必要時に明示 |
| `gh release list` 0 件 | silent-zero check が `::warning::` を発火、 fail 扱い |
| `uses: ./.github/actions/...` (ローカル) | classify=`local`、 検証対象外 |
| `uses: foo/bar@release/v1` (release branch ref) | baseline allowlist 経由でのみ許容 |

#### 3.1.9 既存資産との接続

- **流用**: `scripts/check_action_pins.py` の REPO_ROOT / WORKFLOW_DIR / USES_RE / SHA_RE 定数と classify 関数の構造
- **共存**: `action-pin-gate.yml` (形式強制) と `action-sha-drift.yml` (生存検証) は併存、 trigger / paths が異なる
- **再利用**: `marocchino/sticky-pull-request-comment@v2.9.4` (`runtime-parity-deep.yml` と同一 version)、 `header: action-sha-drift` で sticky 区別
- **artifact 命名**: `action-sha-drift-${{ github.run_id }}` (`runtime-parity-deep` pattern 踏襲)

---

### 3.2 `#4` 7 runtime CLI help auto-extract

#### 3.2.1 機能概要

6 runtime (`#4` proposal の「7 runtime」 は実態 6 runtime + Python 既存統合の意、 Android G2P / Swift G2P は CLI 不在で対象外) の `--help` 出力を `docs/reference/cli-help/<runtime>.txt` に **canonical artifact** として commit し、 weekly run と PR 変更で drift を検出する。

既存 `cli-help-docs-sync.yml` (Python のみ、 `--mode stale-only` で informational) は **本機能に統合** または **並存** (FR-4.1 で user 判断、 推奨は段階移行)。

#### 3.2.2 ユースケース

| UC ID | アクター | シナリオ |
|-------|--------|---------|
| UC-4.1 | weekly cron | 月曜 05:00 UTC に全 6 runtime build → `--help` → diff、 drift 0 なら artifact upload のみ |
| UC-4.2 | PR contributor | CLI flag 追加 / 変更を含む PR で gate が走り、 `docs/reference/cli-help/<runtime>.txt` 未更新なら CI fail |
| UC-4.3 | maintainer | 手動 `workflow_dispatch` で baseline 再生成 (`--regenerate`)、 PR で `<runtime>.txt` を更新 |
| UC-4.4 | release manager | release 直前に `<runtime>.txt` の git diff が release notes の `### Changed` 一次資料 |

#### 3.2.3 入力仕様

各 runtime ごとの build + `--help` 取得コマンド:

| runtime | build (cache 利用) | `--help` 取得 |
|---------|-----------------|--------------|
| python (runtime) | `uv pip install --system -e src/python_run` | `python -m piper --help` |
| python (g2p) | `uv pip install --system -e src/python/g2p` | `python -m piper_plus_g2p --help` |
| rust | `cargo build --release -p piper-plus-cli` (target cache) | `./target/release/piper-cli --help` |
| csharp | `dotnet build src/csharp/PiperPlus.Cli -c Release` | `dotnet src/csharp/PiperPlus.Cli/bin/Release/net10.0/PiperPlus.Cli.dll --help` |
| go | `go build -o /tmp/piper-plus ./src/go/cmd/piper-plus` | `/tmp/piper-plus --help` |
| wasm (cli) | `npm --prefix src/wasm/openjtalk-web run build:cli` | `node src/wasm/openjtalk-web/dist/cli.js --help` |
| cpp | `cmake --build build --target piper_plus` (ORT cache) | `./build/piper_plus --help` |

#### 3.2.4 出力仕様

**`docs/reference/cli-help/<runtime>.txt`** (canonical artifact、 git commit):

```text
# Auto-generated by .github/workflows/cli-help-extract.yml at <ISO8601>
# Source: <build command>
# Runtime: <runtime>
# Version: <piper-plus version>  (sanitized: build timestamp / absolute path removed)

usage: piper [-h] [--model MODEL] [--text TEXT] ...

Synthesize speech from text.

optional arguments:
  -h, --help            show this help message and exit
  --model MODEL         path to ONNX model
  ...
```

**workflow output**:

- **drift 検出時**: `git diff --exit-code docs/reference/cli-help/<runtime>.txt` で exit 1、 sticky comment に diff 投稿
- **drift なし**: artifact `cli-help-${{ github.run_id }}` に全 `<runtime>.txt` を upload (debugging 用)
- **defensive log**: `Collected helps (N runtimes): python rust csharp go wasm cpp` を必ず stderr に echo

#### 3.2.5 データ構造

**`scripts/sanitize_cli_help.py`** の sanitization rule (TOML 化候補):

```toml
# scripts/sanitize_cli_help_rules.toml (新規、 spec toml 化検討)
[[rules]]
runtime = "python"
pattern = "piper-plus \\d+\\.\\d+\\.\\d+.*"
replace_with = "piper-plus <VERSION>"

[[rules]]
runtime = "rust"
pattern = "/home/runner/.*"
replace_with = "<RUNNER_PATH>"

[[rules]]
runtime = "*"
pattern = "\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}"
replace_with = "<TIMESTAMP>"

[[rules]]
runtime = "csharp"
pattern = "PiperPlus\\.Cli, Version=\\d+\\.\\d+\\.\\d+\\.\\d+, Culture=neutral, PublicKeyToken=null"
replace_with = "PiperPlus.Cli, Version=<VERSION>"
```

#### 3.2.6 処理シーケンス

```text
1. checkout repo
2. matrix job per runtime (parallel):
   a. setup toolchain (cache: ~/.cargo, ~/.dotnet, ~/go/pkg/mod, ~/.npm)
   b. build CLI (release mode)
   c. run <runtime> --help > /tmp/help_<runtime>_raw.txt
   d. python scripts/sanitize_cli_help.py \
        --runtime <runtime> \
        --in /tmp/help_<runtime>_raw.txt \
        --out /tmp/help_<runtime>.txt
   e. cp /tmp/help_<runtime>.txt docs/reference/cli-help/<runtime>.txt
   f. artifact upload (per-runtime)
3. drift-check job (depends on all matrix):
   a. download artifacts
   b. git diff --exit-code docs/reference/cli-help/
   c. drift 検出時:
      - PR run: sticky comment + CI fail
      - schedule run: gh issue create (label: cli-help-drift)
   d. defensive log: "Collected helps (N runtimes): ..."
```

#### 3.2.7 トリガー条件

| trigger | paths filter | schedule | wall clock target |
|---------|-------------|---------|------------------|
| `schedule` | — | `0 5 * * 1` (月曜 05:00 UTC) | 10 min (NFR-1.1) |
| `pull_request` | `src/python_run/**`, `src/rust/piper-cli/**`, `src/csharp/PiperPlus.Cli/**`, `src/go/cmd/piper-plus/**`, `src/wasm/openjtalk-web/bin/**`, `src/cpp/main.cpp`, `src/python/g2p/piper_plus_g2p/__main__.py`, `docs/reference/cli-help/**`, `scripts/sanitize_cli_help.py`, `.github/workflows/cli-help-extract.yml` | — | 同上 |
| `workflow_dispatch` | — | — | 同上 |

#### 3.2.8 エラーケース / 例外処理

| ケース | 期待動作 |
|-------|---------|
| build 失敗 (例: cargo build error) | matrix job 単位で fail、 drift-check job は他 runtime のみで継続 (partial drift report) |
| `--help` 実行が non-zero exit | 多くの CLI は `--help` で exit 0 だが、 念のため `\|\| true` で吸収、 stderr 内容を txt に含める |
| sanitize rule miss (新 timestamp 形式) | drift として検出、 maintainer が `sanitize_cli_help_rules.toml` 更新 |
| `<runtime>.txt` 初回不在 | `git diff` で「new file」 として検出、 PR で commit して baseline 化 |
| Android / Swift G2P | 対象外 (CLI 不在)、 workflow paths filter / matrix から除外 |

#### 3.2.9 既存資産との接続

- **統合候補**: `cli-help-docs-sync.yml` を本 workflow に migrate (`--mode stale-only` + 13 flag allow-list を sanitize 側に移管)。 段階移行案: phase 1 で並存、 phase 2 で statin 統合
- **流用**: `scripts/check_cli_help_drift.py` の drift detection logic は本機能の strict mode (PR base) で再利用可能
- **補完**: `docs/spec/cli-flag-contract.toml` の `[[runtimes]]` 6 件と本機能の matrix 対象が一致 (除外: `python_train` は library 内部ユーティリティのため本機能対象外、 spec 側は維持)
- **canonical 関係**:
  - flag **存在**: `cli-flag-contract.toml` + `check_cli_flag_parity.py` が canonical
  - flag **wording**: `docs/reference/cli-help/<runtime>.txt` が canonical (本機能)
  - flag **usage 説明**: `docs/guides/development/cli-usage.md` が canonical (`cli-help-docs-sync.yml` 維持)

---

## 4. 機能要件概要 (Tier 2 / Tier 3)

Tier 2 / Tier 3 は実装着手時の **後続要件定義 PR** で詳細化する。 本書では overview と「詳細化時に着目すべき点」 のみ列挙。

### 4.1 `#5` spec contract toml ↔ impl 同期 gate (5 spec)

| spec | 詳細化時の着目点 |
|------|---------------|
| `release-versions.toml` | git tag を canonical 入力とする post-hoc snapshot 設計 (FR-5.3 の「spec rewrite」 対象候補)、 5 registry (PyPI / NuGet / crates.io / npm / Maven) の version 列を sync |
| `model-sha256-manifest.toml` | HF release の SHA256 を canonical、 各 runtime の model loader が読む manifest との parity |
| `artifact-retention-contract.toml` | 全 workflow の `retention-days:` を抽出、 spec で許容値域 (例: 7 / 30 / 90 / 365) のいずれかに収束しているか |
| `swift-g2p-contract.toml` | Swift package ABI surface、 `Package.swift` の export と一致 |
| `test-flake-retry-contract.toml` | 各 runtime の test retry 設定 (pytest-rerunfailures / cargo nextest retry / etc.) を spec 化 |

### 4.2 `#7` Code example execution test

3 phase (PR-A audit / PR-B informational / PR-C blocker 昇格) の各 phase で要件定義 PR を出す。 詳細化時の着目点:

- audit phase: 既存 `~150 .md` の fenced code block を全件抽出、 言語別件数を集計、 「実行可能 / placeholder 必要 / skip 妥当」 の 3 カテゴリ判定 logic
- placeholder 規約: `<{var}>` 形式 vs `<var>` 形式の選定、 既存 docs の混在状況調査
- doctest sandbox: ONNX model fixture を Actions cache に乗せる方式 (key 設計)、 bash 例の `set -euo pipefail` 注入 (heredoc preserve)

### 4.3 `#1` Distroless / Chainguard 移行

1 image / 1 PR で 5 image (`python-train` 除く 6 image 中 5 image) を段階移行。 詳細化時の着目点:

- base image 選定: `cgr.dev/chainguard/python:latest` vs `gcr.io/distroless/python3-debian12`、 update cadence と CVE 対応 lag の比較
- multi-stage build: `pyopenjtalk` C 拡張の builder stage 設計
- HF Space / HA addon の互換性検証手順 (user 手動 step を含む Test Plan)

### 4.4 `#2` SLSA Build L3

1 registry / 1 PR で対象 release workflow に `slsa-github-generator` を追加。 詳細化時の着目点:

- 対象 workflow 確定 (PyPI / NuGet dedicated 新設要否は user 判断)
- hermetic build 化: `workflow_dispatch.inputs.version` 廃止、 `git tag` 抽出 logic
- attestation `subject` 構成 (Maven AAR / JAR classifier 別)
- `slsa-verifier` 使用法 doc (`docs/reference/slsa-verify.md`)

### 4.5 `#6` mkdocs-material 統合配信

別 milestone (Docs Infra) として独立。 詳細化前に user 明示判断 3 件:

- 公開範囲 (`docs/proposals/` を含めるか)
- i18n 戦略 (二重 mirror 維持 vs mkdocs-static-i18n 移行)
- 配信先 (GitHub Pages / Cloudflare / Netlify / HF Spaces)

詳細化時の着目点: nav 階層設計、 既存 `~500` link の mass edit pattern、 既存 Pages site (`deploy-webassembly-demo.yml` / `deploy-huggingface.yml`) との path namespace 衝突回避。

### 4.6 `#8` Test result aggregation

`#6` mkdocs と coupling、 詳細化時の着目点:

- 7 runtime の JUnit XML 出力統一 (gotestsum 導入 / jest-junit 設定 / etc.)
- aggregator JSON schema (`tests/aggregate/test-results.schema.json`)
- sticky comment format (`runtime-parity-deep` pattern 踏襲)
- `/check-cross-runtime` skill との住み分け (FR-8.4) を skill SKILL.md に明文化

---

## 5. 非機能要件詳細

### 5.1 性能要件 (具体的数値)

| ID | 指標 | 目標値 | 検証方法 |
|----|------|-------|---------|
| NFR-1.1 | workflow wall clock (single job) | 10 分以内 | `gh run view <run-id> --json jobs -q '.jobs[].completed_at - .jobs[].started_at'` |
| NFR-1.2 | pre-commit run --all-files | 30 秒以内 | `time pre-commit run --all-files` |
| NFR-1.3 | GitHub API safety margin | 30%+ (request 数 / 5000 req/h ≤ 70%) | rate limit response header 監視 |
| NFR-1.4 | `#4` CLI help matrix wall clock | 10 分以内 (cache hit 時) | NFR-1.1 と同手法 |
| NFR-1.5 | `#3` SHA drift detector | 5 分以内 (270 pin × API resolve) | NFR-1.1 と同手法 |

### 5.2 セキュリティ要件

| ID | 要件 | 検証 |
|----|------|------|
| NFR-2.1 | least privilege: 各 workflow の `permissions:` は default `contents: read` | `actionlint` (既存) で permissions 必須化、 grep で `contents: write` の override 監視 |
| NFR-2.2 | SHA pin 必須 | `action-pin-gate.yml` (既存) で強制 |
| NFR-2.3 | secret hardcoding 禁止 | `check_secret_path_reference.py` (既存) + `Detect hardcoded secrets` (pre-commit) |
| NFR-2.4 | OIDC token (`id-token: write`) は SLSA / cosign 用途のみ | grep で workflow 単位の明示化 |

### 5.3 可用性 / 信頼性要件

| ID | 要件 | 検証 |
|----|------|------|
| NFR-3.1 | informational tier 4 週連続 false positive 0 | `gh run list --workflow=<wf> --json conclusion` で集計 |
| NFR-3.2 | silent-zero 検出機能 | fixture test (`tests/scripts/test_check_action_sha_drift.py`) で silent-zero pattern 再現 |
| NFR-3.3 | retry policy | flaky test を NFR-1.5 内の budget で retry (pytest-rerunfailures 等)、 spec は `#5` 範囲 |

### 5.4 保守性要件

| ID | 要件 | 検証 |
|----|------|------|
| NFR-4.1 | 新規 script は `tests/scripts/test_check_<topic>.py` を伴う | git diff で対応 pair 確認 |
| NFR-4.2 | informational tier workflow は defensive log 必須 | grep で `Collected <unit>` pattern 確認 |
| NFR-4.3 | spec toml [meta] schema 準拠 | `check_spec_meta.py` (既存) |
| NFR-4.4 | docstring / comment は why に集中、 what は最小 | code review + CLAUDE.md 規約 |

### 5.5 互換性要件

| ID | 要件 | 検証 |
|----|------|------|
| NFR-5.1 | 既存 31 spec / 62 check script / 108 workflow との重複なし | 新規追加時に補完関係を要件定義書に明示 |
| NFR-5.2 | Python 3.11 / 3.13、 Rust stable、 Go 1.26、 dotnet 10、 Node 20+ matrix 対応 | CI matrix で実検証 |
| NFR-5.3 | pre-commit hook version pin 6 箇所 sync | `check_ruff_version_sync.py` (既存) |

### 5.6 観測性要件

| ID | 要件 | 検証 |
|----|------|------|
| NFR-6.1 | drift trend を Issue auto-create で可視化 | `gh issue list --label <topic>-drift` で件数監視 |
| NFR-6.2 | sticky comment に「期待値 vs 実測値」 明示 | fixture test で sticky markdown を assert |
| NFR-6.3 | `Collected <unit>: N` を stderr 必須 echo | unit test で stderr capture して assert |

---

## 6. インタフェース仕様

### 6.1 sticky comment format (汎用)

全 informational tier gate が踏襲する template:

```markdown
## <gate name>

**Collected <unit> (N <noun>): <one-line summary>**

<detailed table or list>

Summary: total=<N>, ok=<M>, drift=<D>, skipped=<S>

<closing note / link to artifact>
```

例: `#3` SHA drift (§3.1.4)、 `#4` CLI help drift (§3.2.4)、 `#8` test aggregation (§4.6)。

### 6.2 Issue auto-create format

```text
Title: "[<gate-label>] <one-line summary>"
Labels: <gate-label>-drift (例: action-sha-drift, cli-help-drift, rekor-verify-failure)
Body:
  ## Summary

  <auto-generated, with link to failing workflow run>

  ## Affected

  <list of failing items>

  ## Suggested action

  <baseline 更新 / spec 修正 / etc.>
```

### 6.3 baseline JSON schema (汎用)

```json
{
  "schema_version": <integer>,
  "generated_at": "<ISO8601>",
  "expected_total_<unit>": <integer>,
  "allowlist": [
    { "<key>": "<value>", "note": "<optional>" }
  ],
  "ignore_<unit>s": ["<value>"]
}
```

新規 baseline JSON はこの shape を踏襲 (`#3` `action_sha_baseline.json`、 将来の `#5` 関連 baseline)。

### 6.4 CLI help txt format

各 `<runtime>.txt` ファイルの先頭 4 行は固定 header:

```text
# Auto-generated by .github/workflows/cli-help-extract.yml at <ISO8601>
# Source: <build command>
# Runtime: <runtime>
# Version: <piper-plus version>
```

5 行目以降が `--help` 出力本体 (sanitize 済)。

---

## 7. データモデル (Tier 1)

### 7.1 `action_sha_baseline.json` の field 定義

| field | 型 | required | 説明 |
|-------|----|----|------|
| `schema_version` | integer | yes | 現行 1、 schema 変更時 increment |
| `generated_at` | string (ISO8601 UTC) | yes | baseline 生成時刻 |
| `expected_total_pins` | integer | yes | silent-zero 検出用の baseline 値 |
| `allowlist` | array | yes | OK と判定する pin 列、 各要素は below |
| `allowlist[].action` | string | yes | `org/repo` 形式 |
| `allowlist[].sha` | string (40-hex) | yes | pin SHA |
| `allowlist[].resolved_tag` | string | yes | 検証時の tag / branch / "(commit-only)" |
| `allowlist[].verified_at` | string (ISO8601) | yes | 検証時刻 |
| `allowlist[].note` | string | no | 補足 (force-pushed と紛らわしい case 等) |
| `ignore_actions` | array of string | yes | 監視対象外 (`org/repo` のみ、 SHA 問わず) |

### 7.2 `sanitize_cli_help_rules.toml` の field 定義

| field | 型 | required | 説明 |
|-------|----|----|------|
| `[[rules]]` | array of table | yes | sanitization 規則の集合 |
| `runtime` | string | yes | 適用対象 (`python`, `rust`, ..., または `*` = 全 runtime) |
| `pattern` | string (regex) | yes | matching regex |
| `replace_with` | string | yes | 置換後文字列 (placeholder 形式) |
| `note` | string | no | 規則の意図 |

---

## 8. 制約条件

### 8.1 環境制約

- **CI runner**: `ubuntu-22.04` / `ubuntu-24.04` / `windows-2022` / `macos-14` を既存 matrix と合わせる
- **CI minute**: OSS public で unlimited だが、 concurrent runner 上限 (free tier: 20 jobs) に注意
- **GitHub API**: rate limit 5000 req/h per token (NFR-1.3)
- **HuggingFace download**: rate limit / 安定性を考慮、 cache 必須

### 8.2 運用制約

- **branch protection**: dev / main は require pull request、 auto-commit は branch protection 経由 PR で
- **maintainer 帯域**: 1 PR / 1 機能、 大規模 PR (#511 のような 96 ファイル / +10047 行) は **避ける**
- **release cadence**: SLSA L3 / Distroless / mkdocs は release タイミングと整合 (release 直前は変更凍結)

### 8.3 人的制約

- **user 明示判断必要**: FR-1.5 (image tag 戦略) / FR-2.1 (release path) / FR-6.3-6.5 (公開範囲 / i18n / 配信先) / FR-7.3 (placeholder 規約) — 全て本書では「user 判断」 と明示し、 自律実装で先回りしない
- **review 帯域**: maintainer 1 名想定、 PR は **logically 分割可能な最小単位** に保つ

---

## 9. 検証計画

### 9.1 単体テスト

| 対象 | テストファイル | 主な assertion |
|------|------------|--------------|
| `check_action_sha_drift.py` | `tests/scripts/test_check_action_sha_drift.py` (新規) | OK / dangling / force-pushed の 3 分類、 silent-zero 発火、 baseline 更新 logic |
| `verify_rekor_releases.py` | `tests/scripts/test_verify_rekor_releases.py` (新規) | cosign verify 成功 / 失敗、 古い release の skip |
| `sanitize_cli_help.py` | `tests/scripts/test_sanitize_cli_help.py` (新規) | runtime 別 rule 適用、 timestamp / path 正規化 |

### 9.2 結合テスト

| 対象 | 検証方法 |
|------|---------|
| `action-sha-drift.yml` full run | `act` または `workflow_dispatch` で実 GitHub API を叩き、 270 pin 全部 resolve |
| `rekor-verify.yml` full run | 直近 10 release で `cosign verify-blob` exit 0 |
| `cli-help-extract.yml` full run | 6 runtime build 成功、 `<runtime>.txt` 生成、 diff 0 |

### 9.3 受け入れテスト (Tier 1)

要求定義 v0.1 §8 の AC を満たすこと:

| AC | 受け入れ条件 |
|----|-----------|
| AC-3.1 | weekly run 4 週連続で false positive 0 |
| AC-3.2 | GitHub API rate limit 30%+ 余裕 |
| AC-3.3 | silent-zero 検出が `tests/scripts/test_check_action_sha_drift.py` の fixture で再現 |
| AC-3.4 | 最新 10 release で Rekor verify exit 0 |
| AC-4.1 | 6 `<runtime>.txt` が repo に commit、 weekly drift 0 |
| AC-4.2 | `cli-help-docs-sync.yml` の既存 Python path 動作維持 (allow-list 13 flag が sanitize 側に移管) |
| AC-4.3 | wall clock 10 分以内 (cache hit 時) |

---

## 10. リスクと対策

要求定義 §7 の R-1〜R-7 を本書で詳細化し、 検出機構を明示:

| ID | リスク | 対策 | 検出機構 |
|----|------|------|---------|
| R-1 | informational tier silent-zero 再発 | NFR-6.3 で defensive log を全 gate に必須化、 fixture test で再現 | `tests/scripts/test_check_action_sha_drift.py` |
| R-2 | SLSA release breakage blast radius | 1 registry / 1 PR (`#2` 詳細化時) | RC release verify、 各 PR の Test Plan |
| R-3 | mkdocs link 移行 inbound 死 | canonical link 維持、 段階移行 (`#6` 詳細化時) | `link-check.yml` (既存) |
| R-4 | Distroless 互換性破壊 | 1 image / 1 PR、 user 手動 deploy 検証 (`#1` 詳細化時) | PR Test Plan の user step |
| R-5 | pre-commit budget 超過 | NFR-1.2 で 30 秒以内を絶対基準、 超過時 pre-push tier 移行 | `time pre-commit run --all-files` |
| R-6 | doctest flake (HF download) | Actions cache に乗せる (`#7` 詳細化時) | NFR-1.3 + retry policy |
| R-7 | CI minute 圧迫 | build cache 利用、 weekly schedule に集約 (NFR-1.4) | `gh run list --json conclusion,run-started-at` で trend |

---

## 11. 用語集

| 用語 | 定義 |
|------|------|
| **canonical** | 単方向 truth source (例: Python = canonical、 他 runtime = mirror) |
| **drift** | canonical と mirror、 docs と impl の不一致 |
| **silent-zero** | PR #511 phase 2 で発覚した failure mode: 集計値 0 のまま success 扱い (本書 NFR-6.3 で対策) |
| **dangling SHA** | git db に commit は存在するが、 upstream の tag / branch / default ref から参照されていない状態 |
| **force-pushed SHA** | upstream で同一 SHA への force-push が起き、 元 commit と内容が不一致 (`tj-actions/changed-files` 2025-03 事件 pattern) |
| **informational tier** | workflow level `continue-on-error: true` で job が green を返す gate |
| **blocker tier** | drift 検出時に CI fail し PR を block する gate |
| **rekor** | Sigstore の transparency log (artifact 署名の改竄不可能性証明インフラ) |
| **in-toto attestation** | SLSA L3 で生成される build provenance の標準形式 (`*.intoto.jsonl`) |
| **sticky comment** | `marocchino/sticky-pull-request-comment` で更新する PR 上の単一 comment |

---

## 12. 参照

- 上流 proposal: [`ci-expansion-deferred-items.md`](ci-expansion-deferred-items.md)
- 要求定義 v0.1: [`ci-expansion-deferred-items-requirements.md`](ci-expansion-deferred-items-requirements.md)
- 既存 skill / hook: [`.claude/README.md`](../../.claude/README.md)
- 既存 spec contract: `docs/spec/*.toml` (31 件)
- 既存 check script: `scripts/check_*.py` (62 件)
- Sigstore Rekor: <https://docs.sigstore.dev/logging/overview/>
- SLSA framework: <https://slsa.dev/spec/v1.0/>
- in-toto attestation: <https://github.com/in-toto/attestation>

---

## 13. 変更履歴

| 日付 | バージョン | 変更内容 | 担当 |
|------|---------|--------|------|
| 2026-05-19 | 0.1 (draft) | 初版。 上流 proposal / 要求定義 v0.1 を受けて、 Tier 1 (`#3` Rekor + SHA drift / `#4` CLI help) を I/O 仕様・データ構造・処理シーケンス・トリガー条件・エラーケース・既存資産との接続まで詳細化。 Tier 2 / Tier 3 は overview レベル (後続要件定義 PR で詳細化)。 NFR を 6 カテゴリ (性能 / セキュリティ / 信頼性 / 保守性 / 互換性 / 観測性) に再整理し、 検証可能な数値・手法を明示。 sticky comment / Issue auto-create / baseline JSON / CLI help txt の汎用 interface format を §6 で集約。 silent-zero 対策 (PR #511 phase 2 教訓) を NFR-6.3 / AC-3.3 / fixture test で 3 重に構造化。 | Claude Code (ブランチ `docs/ci-expansion-deferred-items-organize`) |
