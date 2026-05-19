# T-010: doc examples informational gate (PR-B)

**チケット ID**: `T-010`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#7-B` (Code example execution test — informational gate phase)
**Tier**: Tier 2 (informational)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: **T-009 (doc examples audit, PR-A) merge 済み**。 audit JSON (`tests/fixtures/doc_examples_audit/audit.json`) と placeholder 規約 (FR-7.3、 user 決定済み) が前提。 audit 未完で本 PR に着手すると skip directive 設計が空回りする

---

## 1. タスク目的とゴール

### 目的

T-009 で生成された audit JSON を入力として、 `scripts/check_doc_examples.py --execute` で **実 subprocess 実行ベース** の doctest gate を **informational tier** (`continue-on-error: true`) で導入する。 1 ヶ月の informational 運用で false positive 率を計測し、 T-011 (blocker 化判定) の判断材料を集める。

既存 `scripts/check_readme_code_examples.py` (シンボル grep) と本 gate は **補完関係** で並存 (CON-7.1)、 置換しない。 silent-zero 落とし穴は PR #511 phase 2 argparse bug の教訓を活かし、 期待値 (audit JSON の `totals.executable`) と実測値の乖離検出で防御する。

### ゴール (Done definition)

- [ ] `scripts/check_doc_examples.py --execute` の subprocess 実行モードを実装 (T-009 で audit subcommand のみ実装済み、 本 PR で execute mode を追加)
- [ ] `.github/workflows/doc-examples-gate.yml` を informational tier (`continue-on-error: true`) で新設 (weekly schedule + PR base trigger、 paths filter `docs/**` / `scripts/check_doc_examples.py` / `scripts/doc_examples/**`)
- [ ] audit JSON の `blocks[].category == "executable"` のみ実行候補とし、 `needs_placeholder` / `skip_warranted` は skip
- [ ] bash 例の falsy success 防止: heredoc 内に `set -euo pipefail` を自動注入 (AC-7.4、 fixture test で再現)
- [ ] ONNX model fixture を GitHub Actions cache (`actions/cache@<sha>`、 ~250MB) に乗せる (AC-7.3、 R-6 緩和)
- [ ] silent-zero 防御: `Collected executable blocks (N=...): bash=A python=B ...` を必ず stderr に出力、 `N == 0` または `audit.totals.executable` から半分以下なら `::warning::` 発火 (NFR-5.2 / NFR-5.3)
- [ ] sticky comment に「期待値 (audit total) vs 実測値 (実行数 / pass / fail / skip)」 を明示
- [ ] 1 ヶ月 informational 観測で false positive 率 5% 以下 (AC-7.2) — informational 期間中の data point は 4 weekly run + 該当期間 PR で集計
- [ ] stale audit 警告: audit JSON 内 `hash_sha1` と現在の block hash が異なる場合 `::warning::Audit JSON stale: <file>:<line>` を出力 (T-009 から引き継ぎ)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_doc_examples.py` | 修正 (T-009 で新規) | `--execute` subcommand を追加 |
| `scripts/doc_examples/executor.py` | 新規 | subprocess 実行 / heredoc injection / timeout / capture |
| `scripts/doc_examples/runners/bash.py` | 新規 | bash heredoc + `set -euo pipefail` 注入 |
| `scripts/doc_examples/runners/python.py` | 新規 | python `-c` または tempfile 経由実行 |
| `scripts/doc_examples/runners/rust.py` | 新規 | `cargo script` または `rustc` tempfile 実行 |
| `scripts/doc_examples/runners/csharp.py` | 新規 | `dotnet run --project` tempfile 実行 |
| `scripts/doc_examples/runners/go.py` | 新規 | `go run` tempfile 実行 |
| `scripts/doc_examples/runners/wasm.py` | 新規 | `node --experimental-vm-modules` 実行 |
| `.github/workflows/doc-examples-gate.yml` | 新規 | informational tier workflow (weekly + PR base) |
| `tests/scripts/test_check_doc_examples_execute.py` | 新規 | fixture-based execute test (silent-zero / falsy success / stale audit) |
| `tests/fixtures/doc_examples_execute/` | 新規 | runner 別 fixture markdown (各 3-5 件) |
| `docs/spec/doc-examples-contract.toml` | 修正 (T-009 で新規) | `[execute]` section を追加: timeout / runner mapping / heredoc injection rule |
| `docs/reference/doc-examples-gate.md` | 新規 | gate の運用手順 / skip directive 書き方 / placeholder 規約の最終決定 |

### 2.2 処理シーケンス

```text
1. --execute mode 起動、 `tests/fixtures/doc_examples_audit/audit.json` を load (--audit-input で path 上書き可)
2. audit JSON の blocks[] を iterate、 category == "executable" のみ runner に dispatch
3. blocks[].hash_sha1 を現 file 内容と再計算、 mismatch なら ::warning::Audit stale で flag (skip せず実行は続行)
4. runner 別実行 (詳細 §2.3):
   - bash: tempfile に `set -euo pipefail` + 本体 → `bash -c <tempfile>` (timeout 30s)
   - python: tempfile に `# -*- coding: utf-8 -*-` + 本体 → `python <tempfile>` (timeout 60s)
   - rust: cargo new --bin → src/main.rs に貼付 → `cargo run` (timeout 120s、 重い)
   - csharp: `dotnet new console` → Program.cs に貼付 → `dotnet run` (timeout 120s)
   - go: tempfile → `go run` (timeout 60s)
   - wasm: tempfile js → `node` (timeout 60s)
5. exit code / stdout / stderr / duration / cache hit を per-block record
6. 全 block 実行後、 silent-zero 防御 log を stderr に出力:
   Collected executable blocks (N=42): bash=12 python=18 rust=4 csharp=3 go=3 wasm=2
   Expected from audit.totals.executable=42, observed=42 → OK
   (observed < expected * 0.5 → ::warning::)
7. sticky comment 生成 (期待値 vs 実測値、 fail 一覧、 stale audit 一覧)
8. continue-on-error: true により informational tier として exit 0
   (PR-C / T-011 の blocker 昇格時に continue-on-error 削除)
```

### 2.3 heredoc injection 規約

`scripts/doc_examples/runners/bash.py` の injection logic:

```python
HEREDOC_TEMPLATE = """\
#!/usr/bin/env bash
set -euo pipefail
{user_code}
"""
```

bash example が既に `set -e` 等を含む場合は重複注入を避ける (idempotent)。 semicolon (`;`) 連結による中間 step 失敗 silent ignore (AC-7.4 で fixture 再現) を防ぐ。 spec contract:

```toml
# docs/spec/doc-examples-contract.toml の [execute] section (T-010 で追加)
[execute]
schema_version = 1

[execute.bash]
inject_strict_mode = true
strict_mode_directive = "set -euo pipefail"
timeout_sec = 30
skip_if_present = ["set -e", "set -o errexit", "set -euxo", "set -eu"]

[execute.python]
inject_utf8_coding = true
timeout_sec = 60

[execute.rust]
strategy = "cargo_new_tempdir"
timeout_sec = 120

[execute.placeholder_regex]
# T-009 audit で決まった規約。 user 判断 (FR-7.3) を反映
pattern = "<\\{[a-zA-Z_][a-zA-Z0-9_]*\\}>"
legacy_pattern = "<[A-Z_][A-Z0-9_]*>"
# legacy は T-011 までに mass edit で `<{var}>` 形式に統一する移行戦略
```

### 2.4 ONNX model fixture cache

`actions/cache@<sha>` で HF download model を Actions cache に乗せる (AC-7.3、 R-6 緩和):

```yaml
- name: Cache ONNX model fixture
  uses: actions/cache@<40-hex>  # @v4.x.y SHA pin
  with:
    path: ~/.cache/piper-plus/models
    key: doc-examples-onnx-${{ hashFiles('tests/fixtures/doc_examples_execute/model-manifest.txt') }}
    restore-keys: doc-examples-onnx-
```

`tests/fixtures/doc_examples_execute/model-manifest.txt` で必要 ONNX model の HF path + SHA256 を declarative 化。 cache key が manifest 変更で invalidate される。 T-005 (`model-sha256-manifest.toml` gate) と spec を共有する余地は post-M2 retrospective で評価。

### 2.5 既存資産との接続

- **流用**: T-009 で生成された audit JSON 入力、 `markdown-it-py` (T-009 共通)、 `actions/cache` (既存 workflow で使用済み)
- **共存**: `scripts/check_readme_code_examples.py` (シンボル grep) は別 entrypoint、 本 gate と並存。 spec contract で役割分担を declarative 化
- **補完関係**: `runtime-parity-deep.yml` (PR #511) の sticky comment pattern を流用 (FR-8.3 流用)、 T-008 (`test-flake-retry-contract.toml`) の retry policy が定義され次第本 gate にも適用

---

## 3. エージェントチームの役割と人数

> runner 6 言語の実装が並列化のメインボトルネック。 ただし共通 executor 基盤が先行必要 (依存関係あり)。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer (executor core)** | 1 | `executor.py` + `--execute` subcommand + audit JSON loader + stale hash 検出 | `scripts/doc_examples/executor.py` |
| **Implementer (runners)** | 1 | 6 runner (bash / python / rust / csharp / go / wasm) の subprocess 実行 | `scripts/doc_examples/runners/*.py` |
| **Implementer (workflow)** | 1 | `doc-examples-gate.yml` + ONNX cache + sticky comment 生成 | `.github/workflows/doc-examples-gate.yml` |
| **Test author** | 1 | fixture markdown (6 言語 × 各 3-5 件) + silent-zero / falsy success / stale audit 再現 unit test | `tests/scripts/test_check_doc_examples_execute.py` |
| **Reviewer** | 1 | cross-cutting (audit JSON 入力 schema との一致確認 / silent-zero 防御の有効性) | review |

**並列度**: Implementer (executor core) 先行 → 完了後に runners + workflow + test author を 3 並列。 Test author は fixture を先に書いて TDD 入力にする。

**Agent prompt の与え方**: Explore subagent で T-009 の audit JSON schema と既存 `runtime-parity-deep.yml` の sticky comment 実装を先に dump、 general-purpose で executor core を実装後、 6 runner + workflow + test を並列、 最後に main agent で integration smoke を回す。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `--execute` subcommand と 6 runner 実装
- informational tier workflow (`continue-on-error: true`)
- bash `set -euo pipefail` 自動注入と heredoc preserve
- ONNX model fixture Actions cache 化
- silent-zero 防御 (期待値 vs 実測値 sticky)
- 1 ヶ月 informational 観測 (本 PR merge 時点から起算、 weekly run + PR base trigger で data 集積)
- T-009 audit JSON の `executable` カテゴリのみ実行、 stale hash で warning

**Out of scope**:

- blocker 化 (T-011 PR-C、 `continue-on-error: true` の削除はそこで)
- 各 runner toolchain の inplace 更新 (既存 CI toolchain を借用)
- audit JSON の再生成 (T-009 範疇、 本 PR では consume のみ)
- ONNX model SHA manifest の自動 gate 化 (T-005 範疇)
- placeholder 規約の決定 (T-009 ticket で user 判断済み前提、 本 PR では適用のみ)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `executor.execute_blocks()` | audit JSON (executable 5 件) + 該当 markdown | 5 件全実行、 exit code / duration / stdout が record |
| UT-2 | `runners.bash.run()` | semicolon (`;`) 連結で中間 step が失敗する bash block | `set -euo pipefail` 注入により exit 1 (AC-7.4) |
| UT-3 | `runners.bash.run()` | 既に `set -e` を含む bash block | 重複注入なし、 idempotent |
| UT-4 | `runners.python.run()` | UnicodeDecodeError を起こす UTF-8 文字含む python | `# -*- coding: utf-8 -*-` 注入で pass |
| UT-5 | `runners.rust.run()` | `fn main() { ... }` 含む rust block | `cargo run` で exit 0 |
| UT-6 (silent-zero) | `--execute` | audit JSON `totals.executable=42`、 実行で 0 件のみ実測 | `::warning::Collected executable blocks: 0, expected 42` |
| UT-7 (silent-zero) | `--execute` | observed が expected の半分以下 (例: 42 expected → 20 observed) | `::warning::Significant drop: 20/42 (47%)` |
| UT-8 (stale audit) | `--execute` | audit JSON の hash_sha1 が現 file と mismatch | `::warning::Audit stale: <file>:<line>`、 実行は続行 |
| UT-9 | timeout | 30s 超過する bash block | timeout で kill、 fail record (exit code 124) |
| UT-10 | sticky comment 生成 | UT-1 の出力 | markdown table に `expected=42 observed=42 pass=40 fail=2 skip=N` |
| UT-11 | placeholder skip | audit JSON で `needs_placeholder` カテゴリ | 実行されない (実測カウントに含まれない) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | weekly run (workflow_dispatch) | `gh workflow run doc-examples-gate.yml`、 sticky comment が PR-less でも Issue に投稿 |
| E2E-2 | PR base trigger | `docs/guides/home-assistant.md` の bash block を編集 → PR で gate run、 sticky comment 投稿 |
| E2E-3 | silent-zero 再現 | audit JSON を fixture で書き換え (`totals.executable=42` だが実行 0)、 `::warning::` 発火 |
| E2E-4 | ONNX cache hit | 2 回目以降の run で cache hit 確認 (`gh run view --log` で `Cache hit` 確認、 wall clock 短縮) |
| E2E-5 | continue-on-error の効果 | runner が 1 件 fail しても workflow job は exit 0 (informational tier) |
| E2E-6 | 1 ヶ月運用 false positive | merge 後 4 weekly run + 該当期間 PR で fp 件数 / 全実行件数 ≤ 5% (AC-7.2) |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)、 本 gate は pre-commit に含めない (重い、 ONNX 必要)
- [ ] 既存 `link-check.yml` / `runtime-parity-deep.yml` workflow と `concurrency` group 衝突なし
- [ ] silent-zero 防御: `Collected executable blocks: N` が必ず stderr に出力 (UT-6 / UT-7)
- [ ] `scripts/check_readme_code_examples.py` の動作不変

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | ONNX model download で HF rate limit / 通信不安定で CI flake (R-6) | Actions cache (~250MB) に乗せる (AC-7.3)、 cache miss 時は HF retry policy (T-008 spec 化で gate 化) | E2E-4 / gh run history monitor |
| C-2 | bash heredoc injection で multi-line string が破壊 | tempfile 方式 (`bash -c <tempfile>`) に統一、 stdin heredoc 方式は使わない | UT-2 / UT-3 |
| C-3 | rust runner の wall clock が長すぎる (cargo new + build で 60-120s) | timeout 120s、 audit phase で rust executable 件数 ≤ 5 件を user 承認、 cache が無効化される hash_sha1 trigger は spec 化 | wall clock metric in sticky |
| C-4 | csharp runner の dotnet new がネットワーク必要 (NuGet restore) | NuGet cache を Actions cache に乗せる、 offline オプション検討 | wall clock + cache metric |
| C-5 | informational tier が 1 ヶ月 fp 5% を超過 → T-011 promote 不可 | sticky comment で fp 集計を自動化、 superseded skip directive で audit JSON 更新を T-009 に return | sticky 観測 + 月次 retrospective |
| C-6 | informational tier の silent-zero (workflow job が green でも実行 0 件) | NFR-5.2 / NFR-5.3 の defensive log を必須実装、 `observed < expected * 0.5` で warning | UT-6 / UT-7 (fixture test で再現) |
| C-7 | audit JSON が stale (T-009 merge から本 PR merge までに docs が変動) | stale hash 検出で warning、 必要なら本 PR 着手前に T-009 を再実行 (`/audit` re-run) | UT-8 / E2E-2 |
| C-8 | placeholder 規約 (FR-7.3) が user 決定前 | ticket header で着手前提として明記、 未決定なら本 PR 着手しない | ticket 運用 |
| C-9 | continue-on-error の使い方を間違えると T-011 で削除し忘れ | spec contract に「PR-C で削除すべき行」 を明示 marker `# DELETE_FOR_BLOCKER_T011` で diff 検索容易化 | T-011 ticket で参照 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected executable blocks: 0` が success にならないか UT-6)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (sliding `@v<major>` 禁止、 `actions/cache` 含む)
- [ ] `permissions:` が least privilege か (default `contents: read`、 `pull-requests: write` は sticky comment 投稿時のみ)
- [ ] `paths:` filter が `docs/**` / `scripts/check_doc_examples.py` / `scripts/doc_examples/**` / `.github/workflows/doc-examples-gate.yml` を漏れなくカバー
- [ ] sticky comment が「期待値 vs 実測値」 を明示しているか (NFR-5.2)
- [ ] fixture が intentional violation (falsy success / silent-zero / stale audit) を再現できるか
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 `check_readme_code_examples.py` との重複検証なし、 `doc-examples-contract.toml` に補完関係明記
- [ ] `continue-on-error: true` の行に `# DELETE_FOR_BLOCKER_T011` marker comment が付いているか (T-011 連携)
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか
- [ ] ONNX cache の `key` が manifest hash で invalidate される設計か (model 更新で stale cache を防ぐ)

---

## 6. 一から作り直すとしたら

### 案 A: subprocess 実行 vs sandbox (docker / firejail) で隔離

- **概要**: 本 PR は subprocess + tempfile で実行しているが、 ephemeral docker container (`docker run --rm <runner-image>`) や firejail で isolation を強化する案
- **長所**: ONNX model download / file system 改変が host を汚さない、 hermetic build 寄りで release readiness signal が clean
- **短所**: docker container startup overhead で wall clock が +1-2 分 / block、 GHA runner で docker-in-docker は複雑、 既存 CI toolchain (Rust target cache / etc.) を再利用できない
- **採否**: v1 では subprocess + tempfile を維持。 host 汚染リスクは Actions runner ephemeral 性 (1 job = 1 VM) で十分緩和される。 host が長寿命な local dev で実行する場合のみ docker option を future 検討

### 案 B: placeholder 規約を `<{var}>` ではなく Jinja2 `{{var}}` で統一

- **概要**: T-009 で `<{var}>` 推奨を決めたが、 T-010 着手時に Jinja2 syntax (`{{var}}`) に変更する余地を検討
- **長所**: Python / mkdocs / ansible で標準的、 IDE syntax highlight が効く、 既存 `mkdocs.yml` (T-022) との親和性
- **短所**: bash / rust / csharp の `{{` `}}` が format-string と competing、 既存 `~150 .md` の mass edit が破壊的、 audit JSON の再生成が必要
- **採否**: v1 では `<{var}>` を維持 (T-009 で user 決定済み前提)。 v2 (`schema_version: 2`) でランタイム別 placeholder syntax を spec 化する余地

### 案 C: 各 runner の toolchain を「常駐」 vs 「都度新規」

- **概要**: 本 PR は cargo / dotnet / go を都度 `--new` で project 生成。 代替案は repo 内に `tests/doc_examples_runners/{rust,csharp,go}/` の常駐 project を用意し、 fenced block を該当 project の src/ に「貼り替えるだけ」 で `cargo run` 等を回す
- **長所**: project 生成 overhead がなく wall clock 短縮、 dependency (Cargo.toml / *.csproj) が固定で再現性高い
- **短所**: fenced block が複数 dependency を要求する場合に project の Cargo.toml と矛盾、 dependency 追加の合意形成が手動
- **採否**: v1 では「都度新規」 を維持 (依存問題なし)、 wall clock 計測結果が 10 分超 (NFR-1.1) に近接した場合のみ「常駐」 に switch

### 結論

現時点では **subprocess + tempfile + 都度新規 + `<{var}>` placeholder** の組合せ。 1 ヶ月 informational 観測の wall clock / fp 統計を見て、 T-011 の blocker 昇格時に再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-011 (blocker 化判定、 1 ヶ月観測後)
- **連携 milestone**: M2 (本チケット含む) → M4 mkdocs (T-022) で「docs site 全 code example が実行可能」 を blocker 化する前提
- **依存解消**: 本チケット merge + 1 ヶ月運用観測完了で T-011 の blockedBy が外れる

### 7.2 引き継ぎ事項 (Handoff)

> 1 ヶ月 informational 運用での観測 / 計測 / T-011 への引き継ぎ情報。

- **観測開始 timing**: 本 PR merge 日が day 0、 day 30 以降に T-011 着手可能
- **fp 計測 method**: sticky comment の `fail` 集計を週次 retrospective で人手 triage、 「実装側の真のバグ」 vs 「fixture / network flake」 を分類。 `tests/fixtures/doc_examples_execute/fp_log.json` に追記累積 (新規 fixture file)
- **continue-on-error 削除手順 (T-011 で実行)**: `grep -n 'DELETE_FOR_BLOCKER_T011' .github/workflows/doc-examples-gate.yml` で該当行を特定、 削除 + spec contract の `[execute].tier` を `informational` → `blocker` 変更
- **audit JSON 更新 trigger**: 月次で `python scripts/check_doc_examples.py --audit` を re-run、 diff があれば T-009 の更新 PR を出す。 本 PR では re-audit を gate に組み込まない (cycle 短期化のため)
- **ONNX cache key 設計の理由**: `tests/fixtures/doc_examples_execute/model-manifest.txt` の hash で invalidate。 model 更新時は manifest を bump、 stale cache を防ぐ
- **wall clock budget**: NFR-1.1 (10 分以内) に対して実測 budget。 超過時は runner 別に matrix 化検討
- **silent-zero 防御の testability**: UT-6 / UT-7 で fixture re-creation する場合、 audit JSON も同時に書き換える必要 (path: `tests/fixtures/doc_examples_audit/audit.json`)

### 7.3 未解決の質問

- [ ] 1 ヶ月運用 fp が 5% を超過した場合の対応 (gate を退去 vs informational 継続延長、 user 判断、 T-011 で再評価)
- [ ] ONNX model 以外の network 依存 (HF Hub / npm registry / crates.io) を offline 化するか (T-011 もしくは別 PR)
- [ ] runner 別 fp 率の格差 (rust / csharp が高い場合に runner 別 informational 段階を分ける)
- [ ] stale audit warning の閾値 (現状: 全 mismatch で warning。 「1% 以下なら無視」 等の noise 削減判断)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.7 (FR-7.5 / AC-7.2〜7.4 / CON-7.2 / DEP-7.1〜7.2)、 §6 (Tier 2 doctest informational PR-B)、 §7 R-6 (ONNX cache 緩和)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.2 (`#7` overview)、 §5.1 (NFR-1.1)、 §5.5 (NFR-5.2 / NFR-5.3)
- 既存資産: [`scripts/check_readme_code_examples.py`](../../../scripts/check_readme_code_examples.py) (シンボル grep gate、 本 PR で置換しない)
- 関連 spec: `docs/spec/doc-examples-contract.toml` (T-009 で新規、 本 PR で `[execute]` section 追加)
- 関連 workflow: `.github/workflows/doc-examples-gate.yml` (本 PR で新規)、 `runtime-parity-deep.yml` (sticky comment pattern 流用)
- 前提: [`T-009-doc-examples-audit.md`](T-009-doc-examples-audit.md) (audit JSON 入力)
- 後続: [`T-011-doc-examples-blocker.md`](T-011-doc-examples-blocker.md)
- 親 milestone: [`../milestones/M2-spec-and-docs.md`](../milestones/M2-spec-and-docs.md)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
