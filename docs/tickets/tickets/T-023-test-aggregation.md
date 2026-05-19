# T-023: 7 runtime test result aggregation

**チケット ID**: `T-023`
**Milestone**: [M4 Docs Infra](../milestones/M4-docs-infra.md)
**Proposal 項目**: `#8` (`Test result aggregation`)
**Tier**: Tier 3 (別 milestone、 ただし sticky comment 部分は M1 sticky pattern 確立後即着手可能)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- M1 sticky pattern (T-001 Rekor verify / T-002 Action SHA drift / T-003 CLI help) 確立済み
  - defensive log `Collected <unit> (N): ...` を必ず stderr に出力する pattern
  - sticky comment markdown template (`runtime-parity-deep` pattern 踏襲)
  - silent-zero 防止 fixture test の書き方
- 既存 `coverage-aggregation.yml` の artifact pattern (DEP-8.1)
- 既存 `runtime-parity-deep` workflow の sticky comment pattern (DEP-8.3、 PR #511)
- user 判断 **不要** (sticky comment 段階までは独立着手可能、 dashboard 統合は T-022 FR-6.6 で判断)

---

## 1. タスク目的とゴール

### 目的

piper-plus は **7 runtime** (Python / Rust / C# / Go / WASM / C++ / Kotlin) で test を走らせているが、 結果が runtime 単位の workflow に分散している。 PR で「全 runtime green か」 を確認するには 7 workflow を個別に open する必要があり、 **release readiness signal が 1 箇所に集約されていない**。 さらに retry 1 回 pass の silent flake、 last green commit の runtime 間 drift が PR review で見落とされやすい。

本チケットは要求定義 §4.8 (FR-8.1〜FR-8.5 + AC-8.1〜AC-8.3) を実装し、 7 runtime の test 結果を **JUnit XML 統一 → aggregator script → sticky comment** の 3 段階で集約する。 **silent-zero 防御** (PR #511 phase 2 で発覚した argparse `nargs="*"` last-wins bug の同型を踏まない) を初版から必須実装。

### ゴール (Done definition)

- [ ] **AC-8.1**: 7 runtime 全 test 結果が **1 sticky comment** に集約、 各 runtime の pass / fail / skip / duration / retry-count が 一覧表示
- [ ] **AC-8.2**: **last green commit が全 runtime で揃っているか** の judgment column を sticky に含む (release readiness signal)
- [ ] **AC-8.3**: aggregator script は silent-zero pattern を踏まない: 集計件数を必ず defensive log で stderr に出力、 baseline 半減で `::warning::` 発火
- [ ] `runtime-parity-deep` workflow と同型 sticky pattern (DEP-8.3 流用)
- [ ] FR-8.5: retry 履歴を「pass with retry」 として可視化 (silent flake 検出)
- [ ] FR-8.4: `/check-cross-runtime` skill との 住み分けを SKILL.md / aggregator README に明文化 (skill = parity 検証、 aggregator = test 統計)
- [ ] NFR-1.1 wall clock **10 分以内** (aggregator step 単体)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/aggregate_test_results.py` | 新規 (~150 行) | 7 runtime artifact から JUnit XML を集約 → `test-aggregate.json` |
| `tests/aggregate/test-results.schema.json` | 新規 | aggregator JSON schema (runtime / pass / fail / skip / duration / retry / commit_sha) |
| `tests/scripts/test_aggregate_test_results.py` | 新規 | fixture-based silent-zero 検出 test (AC-8.3) |
| `tests/scripts/fixtures/junit_xml/` | 新規 | 7 runtime ぶんの sample JUnit XML + intentional violation fixture |
| `.github/workflows/test-aggregation.yml` | 新規 | PR base trigger、 7 runtime workflow の artifact を download → aggregator → sticky |
| `.github/workflows/python-ci.yml` (既存) | 修正 | `pytest --junit-xml=test-results.xml` を artifact upload に追加 |
| `.github/workflows/rust-ci.yml` (既存) | 修正 | `cargo2junit` 導入、 artifact upload 追加 |
| `.github/workflows/csharp-ci.yml` (既存) | 修正 | `--logger:junit` 出力を artifact upload に追加 |
| `.github/workflows/go-ci.yml` (既存) | 修正 | `gotestsum --junitfile=test-results.xml` 導入 |
| `.github/workflows/wasm-tests.yml` (既存) | 修正 | `jest-junit` reporter 追加 |
| `.github/workflows/cpp-tests.yml` (既存) | 修正 | `ctest --output-junit test-results.xml` (CMake 3.21+) |
| `.github/workflows/kotlin-g2p-ci.yml` (既存) | 修正 | gradle test の JUnit XML を artifact upload |
| `.claude/skills/check-cross-runtime/SKILL.md` (既存) | 修正 | aggregator との住み分け明文化 (FR-8.4) |
| `scripts/README-aggregator.md` | 新規 | aggregator 仕様 + skill との住み分け figure |

### 2.2 JUnit XML 統一化 (各 runtime 追加内容)

| runtime | reporter | 既出 / 追加 | 追加内容 |
|---------|----------|----------|---------|
| Python | `pytest --junit-xml` | 既出 | artifact upload step 追加のみ |
| Rust | `cargo test -- --format json \| cargo2junit` | **追加** | `cargo2junit` を `Cargo.toml` の dev-dependencies に追加 |
| C# | `dotnet test --logger:junit` | 既出 | artifact upload step 追加のみ |
| Go | `gotestsum --junitfile=test-results.xml` | **追加** | `gotestsum` を Go install で導入 (Go 標準ではない、 DEP-8.2) |
| WASM | `jest --reporters=jest-junit` | **追加** | `jest-junit` を devDependencies に追加 |
| C++ | `ctest --output-junit test-results.xml` | 既出 | CMake 3.21+ 確認 (現状 3.27+ で OK) |
| Kotlin | gradle test (自動) | 既出 | `build/test-results/test/*.xml` を artifact upload |

### 2.3 `test-results.schema.json` schema 案

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["aggregator_version", "collected_runtimes", "runtimes"],
  "properties": {
    "aggregator_version": { "type": "string" },
    "collected_runtimes": { "type": "integer", "minimum": 0 },
    "expected_runtimes": { "type": "integer", "const": 7 },
    "runtimes": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["name", "pass", "fail", "skip", "duration_sec", "retry_count", "commit_sha", "test_unit_granularity"],
        "properties": {
          "name": { "enum": ["python", "rust", "csharp", "go", "wasm", "cpp", "kotlin"] },
          "pass": { "type": "integer" },
          "fail": { "type": "integer" },
          "skip": { "type": "integer" },
          "duration_sec": { "type": "number" },
          "retry_count": { "type": "integer", "description": "pass with retry を区別" },
          "commit_sha": { "type": "string", "description": "last green commit SHA" },
          "test_unit_granularity": {
            "enum": ["function", "mod", "class", "statement", "test_case"],
            "description": "CON-8.1 粒度差異を明示"
          }
        }
      }
    },
    "last_green_alignment": {
      "type": "object",
      "description": "AC-8.2 全 runtime で last green commit が揃っているか",
      "properties": {
        "aligned": { "type": "boolean" },
        "drift_sha_set": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

### 2.4 sticky comment markdown format

`runtime-parity-deep` pattern を踏襲 (DEP-8.3)、 §6.1 (要件定義書 sticky comment template) 準拠:

```markdown
## Test Result Aggregation (7 runtimes)

**Collected runtimes (7/7): all green** | **last green aligned: yes**

| runtime | pass | fail | skip | duration | retry | granularity | commit |
|---------|------|------|------|----------|-------|-------------|--------|
| python  | 1234 | 0    | 12   | 145s     | 0     | function    | abc123 |
| rust    | 567  | 0    | 0    | 89s      | 0     | mod         | abc123 |
| csharp  | 1003 | 0    | 5    | 67s      | 0     | class       | abc123 |
| go      | 793  | 0    | 2    | 34s      | 0     | function    | abc123 |
| wasm    | 1198 | 0    | 0    | 78s      | 1     | statement   | abc123 |
| cpp     | 234  | 0    | 0    | 56s      | 0     | test_case   | abc123 |
| kotlin  | 145  | 0    | 0    | 23s      | 0     | function    | abc123 |

Summary: total=5174, pass=5174, fail=0, skip=19, retry=1
Last green commit: all 7 runtimes at `abc123` (aligned)
Note: granularity differs per runtime (CON-8.1) — counts not directly comparable across rows.

Artifact: <link to test-aggregate.json>
```

### 2.5 retry-count 集約 logic

JUnit XML の `<testcase>` element に `<flaky>` / `<rerun>` element が含まれる場合は 「pass with retry」 として retry_count を +1。

| reporter | retry element | 抽出方法 |
|----------|--------------|---------|
| pytest (pytest-rerunfailures) | `<rerun>` | aggregator で count |
| cargo2junit | retry なし (`cargo test` は retry なし) | retry_count = 0 |
| dotnet test | `<rerunFailure>` (XunitV3) | aggregator で count |
| gotestsum | `--rerun-fails` flag option | count or 0 |
| jest | `jest-junit` `retry` attribute | count |
| ctest | `--repeat until-pass` flag option | count or 0 |
| gradle | `retry` extension (org.gradle.test-retry) | count or 0 |

retry_count > 0 は **silent flake 警告**: sticky comment で `retry: N` を強調表示。

### 2.6 既存資産との接続

- **流用**: `coverage-aggregation.yml` の artifact download pattern (DEP-8.1)
- **流用**: `runtime-parity-deep` workflow の sticky comment markdown template (DEP-8.3)
- **共存**: `/check-cross-runtime` skill (loanword / PUA / G2P parity 検証 = **内容**) と本 aggregator (test 統計 = **件数**) は **補完関係**、 重複しない
- **補完関係**: PR #511 phase 2 の argparse `nargs="*"` last-wins bug は本 aggregator で同型を踏まないため `argparse` 使用時は `nargs="+"` または `action="append"` 必須 + fixture test で検証

### 2.7 処理シーケンス

```text
1. PR の各 runtime workflow が完了 → JUnit XML を artifact upload
2. test-aggregation.yml が PR base trigger で発火
3. 7 runtime workflow の artifact を download (`actions/download-artifact@v4`)
4. aggregate_test_results.py を実行:
   a. 各 XML を parse、 pass / fail / skip / duration / retry_count を抽出
   b. last green commit を git log で確認 (各 runtime の最新 green commit が揃っているか)
   c. defensive log: Collected runtimes (N/7): ... を必ず stderr に出力
   d. collected_runtimes < expected_runtimes/2 (= 4) なら ::warning:: 発火 (silent-zero 防御)
   e. test-aggregate.json を artifact 出力
5. sticky comment を PR に投稿 (runtime-parity-deep pattern)
6. retry_count > 0 の runtime があれば sticky の retry 列を強調表示
```

---

## 3. エージェントチームの役割と人数

> M1 sticky pattern 確立済みなので **4-5 人** 構成。 各 runtime の JUnit 化は並列可能。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `aggregate_test_results.py` + `test-aggregation.yml` + schema | core script + workflow + JSON schema |
| **Test infra engineer** | 1 | 7 runtime workflow の JUnit XML 出力統一 (DEP-8.2 含む) | 既存 7 workflow 修正 + cargo2junit / gotestsum / jest-junit 導入 |
| **Test author** | 1 | fixture-based silent-zero 検出 test (AC-8.3) | `tests/scripts/test_aggregate_test_results.py` + fixtures |
| **Runtime owner reviewer** | 1-2 | 各 runtime の test 1 件粒度差異 (CON-8.1) 注記 / retry 設定確認 | sticky comment granularity column レビュー |
| **Maintainer** | 1 | skill との 住み分け確認 (FR-8.4) + merge gate | review + merge |

**並列度**: Implementer / Test infra engineer (7 runtime 修正) / Test author は **並列可**。 Runtime owner reviewer は merge 直前 1 pass。

**Agent prompt の与え方**: Explore subagent で 7 runtime workflow の現状 test output 形式を dump → general-purpose で 並行: (a) aggregator script 作成、 (b) 7 workflow を 並列 修正、 (c) fixture-based test 作成 → main agent で integrate して `act` または `workflow_dispatch` で E2E 確認。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `aggregate_test_results.py` (~150 行) + JSON schema
- 7 runtime workflow の JUnit XML 出力統一 (cargo2junit / gotestsum / jest-junit 導入含む)
- `test-aggregation.yml` (PR base trigger + sticky comment)
- fixture-based silent-zero 検出 test (AC-8.3)
- `/check-cross-runtime` skill との住み分け明文化 (FR-8.4)
- last green commit alignment 判定 (AC-8.2)
- retry 履歴集約 (FR-8.5)

**Out of scope**:

- dashboard 統合 (T-022 FR-6.6 採用時のみ別 PR で接続)、 本 ticket は **JSON artifact + sticky comment** までで完了 (CON-8.2)
- SaaS (BuildPulse / Datadog CI Visibility) 連携 — 本 ticket は self-hosted のみ
- Issue auto-create (本 ticket は sticky comment のみ、 Issue 化は M4 retrospective で判断)
- 過去 release の trend グラフ表示 (mkdocs dashboard 経由になるため別 ticket)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `aggregate_test_results.py` | 7 runtime ぶんの正常 JUnit XML fixture | `collected_runtimes=7`、 `last_green_alignment.aligned=true` |
| UT-2 | `aggregate_test_results.py` | 4 runtime ぶんしか artifact 無し (silent-zero pattern) | `collected_runtimes=4` + `::warning::` 発火 (AC-8.3) |
| UT-3 | `aggregate_test_results.py` | 1 runtime に retry 1 回 pass が含まれる | `retry_count=1` で集計 (FR-8.5) |
| UT-4 | `aggregate_test_results.py` | last green commit が runtime 間で drift | `aligned=false` + `drift_sha_set` に分岐 commit list |
| UT-5 | `aggregate_test_results.py` | argparse `--runtime python --runtime rust` (PR #511 同型 bug 検証) | 両方受理 (last-wins しない、 nargs 設計の regression test) |
| UT-6 | JSON schema 検証 | 不正 enum (`name: "kotlin-android"`) | schema validation fail |
| UT-7 | sticky comment markdown 生成 | 正常 aggregate JSON | runtime-parity-deep pattern に準拠した markdown |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | 7 runtime workflow を `workflow_dispatch` で 実行 → `test-aggregation.yml` を 実行 | aggregator が sticky comment を PR に投稿 |
| E2E-2 | 1 runtime をわざと skip して PR 提出 | sticky に `collected_runtimes=6/7` + `::warning::` |
| E2E-3 | retry 1 回 pass の test を含む PR | sticky の retry 列に強調表示 |
| E2E-4 | last green commit が drift する PR (1 runtime のみ HEAD-1) | sticky の last green alignment に `false` + drift 表示 |
| E2E-5 | silent-zero pattern (artifact 全 0 件) | `::warning::` 発火 + sticky に明示 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2、 aggregator は CI のみ)
- [ ] 既存 7 runtime workflow の test 動作が変わらない (JUnit XML 追加 = additive only)
- [ ] `/check-cross-runtime` skill の動作が変わらない (FR-8.4 住み分け明文化のみ)
- [ ] silent-zero 防御: `Collected runtimes (N/7): ...` が stderr に必須出力
- [ ] argparse `nargs="*"` last-wins bug を踏まない (UT-5 で検証)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 / CON-8.1 | 「test 1 件」 の粒度が runtime 間で揃わない (Rust mod / C# class / WASM statement) | sticky comment の granularity 列で明示注記、 row 間直接比較禁止 | sticky markdown |
| C-2 / CON-8.3 | retry 1 回 pass を 「pass」 単純カウントすると flake 検出が機能しない | FR-8.5 で retry_count を別 column 化 | UT-3 |
| C-3 | silent-zero pattern (PR #511 phase 2 同型 bug 再発) | NFR-3.2 defensive log + AC-8.3 fixture test + argparse `nargs` 検証 | UT-2 / UT-5 / E2E-5 |
| C-4 | DEP-8.2 gotestsum 導入が Go workflow build cache に影響 | `actions/setup-go` cache key に gotestsum を含める | go-ci.yml レビュー |
| C-5 | `cargo2junit` の維持状況 (last release が古い場合) | crates.io activity 確認、 不活発なら `cargo-nextest --message-format=junit` 代替候補 | DEP review |
| C-6 | dashboard 統合採用時 (T-022 FR-6.6) に aggregator output 形式が変わる必要 | JSON schema を versioning (`aggregator_version` field) | schema 検証 |
| C-7 | `/check-cross-runtime` skill との混同 (両方 test 統計を返すと思われる risk) | FR-8.4 で SKILL.md と aggregator README に住み分け figure を明記 | review |
| C-8 | last green commit 判定で「PR HEAD 時点の各 runtime workflow が完了していない」 ケース | aggregator は `gh run list --status=completed` で確実な commit のみ参照 | UT-4 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected runtimes: 0` が success にならないか) — AC-8.3
- [ ] argparse `nargs="*"` last-wins bug を踏まないか (PR #511 phase 2 同型) — UT-5
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex (sliding `@v<major>` 禁止)
- [ ] `permissions:` が least privilege (`contents: read` + sticky 投稿用 `pull-requests: write`)
- [ ] paths filter が誤検出 / 取り漏れしない
- [ ] sticky comment が「期待値 vs 実測値」 を明示 (`collected_runtimes=N/7`)
- [ ] fixture が intentional violation (silent-zero / retry / commit drift) を再現できる
- [ ] retry_count 集約 logic が全 7 reporter で正しい (FR-8.5)
- [ ] granularity 注記が sticky に必須表示 (CON-8.1)
- [ ] `/check-cross-runtime` skill SKILL.md に住み分け明文化 (FR-8.4)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠

---

## 6. 一から作り直すとしたら

> M4 milestone §4 で議論済みの代替案 3 件を ticket level で再掲。 次世代版 (v2 test infra) 設計時の判断材料を残す。

### 案 A: self-hosted aggregator vs SaaS (BuildPulse / Datadog CI Visibility / TestRail)

- **概要**: 本 ticket の self-hosted `aggregate_test_results.py` + sticky comment を、 SaaS 製品 (BuildPulse / Datadog CI Visibility / TestRail) に置き換える
- **長所**:
  - flake detection / trend analysis / pass-rate dashboard が built-in
  - self-hosted code の maintenance 0 (PR #511 phase 2 argparse bug 系の落とし穴を踏まない)
  - 7 runtime の JUnit XML を upload するだけで dashboard が育つ (BuildPulse)
- **短所**:
  - **OSS project にとって SaaS 依存は政治的に重い** (piper-plus は MIT / Apache の文化、 vendor lock-in 嫌悪)
  - 月額 cost (Datadog / BuildPulse とも seat-based 課金、 contributor 増加で linear に増)
  - user account 管理 / SSO 等の運用が増える
  - 「project が SaaS 経由でしか健全性を示せない」 状態は contributor 離れの原因に
- **採否**: 現時点では採用しない (FR-8.1〜FR-8.5 通り self-hosted)。 v2 で「flake detection 専門機能だけ BuildPulse を限定使用」 する案を M4 retrospective で再評価。

### 案 B: sticky comment vs Issue auto-create vs dashboard

- **概要**: 集約結果の可視化 surface を sticky comment (本 ticket 採用) / Issue auto-create / mkdocs dashboard の 3 案で比較
- **長所 (Issue auto-create)**: drift を long-lived な discussion thread として残せる、 trend を Issue label で集計可能
- **長所 (dashboard)**: 時系列 trend をマーケティング向けに公開可能 (project 健全性アピール)、 release readiness signal を PR 外でも確認可能
- **短所 (Issue)**: Issue noise が増える、 通知疲労
- **短所 (dashboard)**: T-022 完了が前提、 plugin 自作 cost、 build に test artifact 取得依存
- **採否**: v1 は sticky comment のみ (本 ticket scope)。 dashboard は T-022 FR-6.6 で user 判断、 Issue auto-create は M4 retrospective で再評価。

### 案 C: last green commit judgment を自前 vs `mergify` 等の merge queue 標準

- **概要**: AC-8.2 「last green commit alignment」 判定を本 ticket の `aggregate_test_results.py` 内で実装する vs `mergify` / GitHub Merge Queue 等の標準機能に委譲する
- **長所 (merge queue)**: GitHub native (Merge Queue) または industry standard (mergify) で判定、 自前 logic 不要
- **短所 (merge queue)**:
  - GitHub Merge Queue は public repo で free だが、 7 runtime workflow が **all required** 設定でないと alignment 判定にならない (branch protection 設定 cost)
  - mergify は SaaS 依存 (案 A と同じ vendor lock-in リスク)
  - 「last green commit が runtime 間で揃う」 のは alignment であって merge queue 機能とは厳密には異なる (merge queue は queue ordering、 alignment は status snapshot)
- **採否**: v1 は self-hosted 判定 (本 ticket scope)。 M4 retrospective で「branch protection で 7 workflow を all required にする」 + Merge Queue 採用を再評価。

### 結論

現時点での選択は **self-hosted aggregator + sticky comment + 自前 alignment 判定** (理由: 既存 `runtime-parity-deep` pattern 流用、 vendor lock-in 回避、 実装 cost 小)。 v2 設計時には案 A (BuildPulse 限定) と案 C (Merge Queue) を再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-022 (mkdocs-material) で FR-6.6 dashboard 統合採用時、 `test-aggregate.json` を mkdocs build に取り込む別 PR
- **連携 milestone**: M4 retrospective (SaaS 限定使用 / Merge Queue 採用 / dashboard 統合採否)
- **依存解消**: 本チケット完了で各 release の go/no-go 判定 (release readiness signal) が sticky comment で 1 surface 化

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。

- **argparse `nargs="*"` last-wins bug**: PR #511 phase 2 で発覚した同型 bug を踏まない。 `--runtime` を repeatable にする場合は `nargs="+"` または `action="append"` 必須、 fixture test (UT-5) で regression 防御
- **DEP-8.2 gotestsum 導入**: Go 標準 test reporter ではない。 `go install gotest.tools/gotestsum@latest` を CI 各 job で実施、 build cache key に含める必要
- **`cargo2junit` 維持状況**: crates.io activity が低下した場合の代替候補は `cargo-nextest --message-format=junit`、 NEXTEST の方が active
- **CON-8.1 粒度差異**: sticky の row を直接比較しないこと (Rust mod / C# class / WASM statement)、 granularity 列を必ず表示
- **silent-zero 防御**: `Collected runtimes (N/7): ...` を stderr に必須出力、 N < 4 で `::warning::` 発火 (AC-8.3)
- **/check-cross-runtime skill との 住み分け**: skill = parity 検証 (内容: loanword / PUA / G2P) 、 aggregator = test 統計 (件数: pass / fail / skip / duration / retry)。 SKILL.md と `scripts/README-aggregator.md` の両方に figure を明記
- **dashboard 統合判断 (T-022 FR-6.6)**: 採用時は `aggregator_version` で schema 後方互換を維持、 不採用なら sticky comment のみで完結
- **SLSA attestation subject 拡張 (M3 retrospective)**: T-018 SLSA L3 (Kotlin G2P) の attestation `subject` 構成議論で「test-aggregate.json を attestation に含めるか」 が論点になった。 含める場合は本 ticket と SLSA workflow の依存追加が必要

### 7.3 未解決の質問

- [ ] T-022 (mkdocs) FR-6.6 dashboard 統合採否確定後、 `test-aggregate.json` 取り込み PR の scope
- [ ] M4 retrospective で BuildPulse 限定使用 (flake detection のみ) 採否
- [ ] M4 retrospective で GitHub Merge Queue + branch protection all required 採否
- [ ] retry_count > 0 を Issue auto-create するか (本 ticket では sticky comment のみ、 M4 retrospective で判断)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.8 (FR-8.1〜FR-8.5 / AC-8.1〜AC-8.3 / CON-8.1〜CON-8.3 / DEP-8.1〜DEP-8.3)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.6 / §6.1 (sticky comment template)
- Milestone: [`M4 Docs Infra`](../milestones/M4-docs-infra.md) §3 (AC) / §4 (Phase rethink: SaaS / 分離)
- 既存 workflow (流用): `.github/workflows/coverage-aggregation.yml` (DEP-8.1)、 `.github/workflows/runtime-parity-deep.yml` (DEP-8.3、 sticky comment pattern)
- 既存 skill (住み分け): `.claude/skills/check-cross-runtime/SKILL.md` (FR-8.4)
- 前提 ticket: [T-001 Rekor](T-001-rekor-verify.md) / [T-002 Action SHA drift](T-002-action-sha-drift.md) / [T-003 CLI help](T-003-cli-help-extract.md) (M1 sticky pattern 確立)
- 関連 ticket: [T-022](T-022-mkdocs-material.md) (FR-6.6 dashboard 統合判断)
- PR #511 phase 2 argparse `nargs="*"` last-wins bug (silent-zero 教訓の源流)
- 親 index: [`../README.md`](../README.md)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 — 7 runtime JUnit XML 統一 (cargo2junit / gotestsum / jest-junit 追加導入)、 aggregator script + JSON schema、 sticky comment (runtime-parity-deep pattern 踏襲)、 retry-count 集約 (silent flake 検出)、 last green commit alignment 判定、 silent-zero 防御 fixture test、 /check-cross-runtime skill との住み分け、 SaaS / Issue / dashboard / Merge Queue の 3 代替案を記録 | Claude Code |
