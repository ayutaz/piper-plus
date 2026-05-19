# T-008: `test-flake-retry-contract.toml` ↔ runtime test retry 設定同期 gate

**チケット ID**: `T-008`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#5-5` (`test-flake-retry-contract.toml`)
**Tier**: Tier 2 (blocker、 pre-impl direction)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (M2 内他 ticket と並列可)

---

## 1. タスク目的とゴール

### 目的

`docs/spec/test-flake-retry-contract.toml` (既存 snapshot) は 各 runtime の test retry 設定 (pytest-rerunfailures / cargo-nextest retry / dotnet test rerun / gotestsum rerun / jest retryTimes / ctest --repeat / Gradle test retry / Swift XCTest retry) を canonical に定義し、 runtime ごとに retry budget / timeout / classifier (flake vs real fail) を統一する spec。

現状は各 runtime CI workflow が個別に retry 設定をしており、 (a) retry budget が一致しない (Python は 3 回 / Rust は 0 回 / etc.)、 (b) retry 1 回 pass を「pass」 単純カウントして silent flake を見逃す (CON-8.3 の話と coupling)、 (c) doctest (T-009/T-010) の flake と runtime flake が同じ retry policy で扱われない、 という問題がある。

本 spec の direction は **pre-impl** (spec が canonical、 各 runtime CI YAML / test config が mirror)。 8 runtime の test config と spec の retry policy を CI gate / pre-commit hook で強制する。

M4 (T-023 test aggregation) で「retry 1 回 pass」 を可視化する FR-8.5 と coupling する pre-requisite であり、 本 ticket 完了が M4 aggregation の retry-count column 設計を確定させる。

### ゴール (Done definition)

- [ ] `scripts/check_test_flake_retry.py` (~140 行) を新設、 8 runtime の test config / CI YAML から retry 設定を抽出し spec の `[runtimes.<name>]` と突合 (FR-5.1, FR-5.2 (a))
- [ ] `.pre-commit-config.yaml` に hook 統合 (CI workflow / test config 変更時のみ fast-path) (FR-5.2 (b))
- [ ] `.github/workflows/test-flake-retry-gate.yml` 新設 または `contract-gates-extended.yml` に job 追加 (FR-5.2 (c))
- [ ] `tests/scripts/test_check_test_flake_retry.py` で fixture-based intentional violation を再現 (AC-5.1)
- [ ] `pre-commit run --all-files` の合計 wall clock 30 秒以内維持 (NFR-1.2, AC-5.2)
- [ ] spec に retry classifier (flake vs real fail) の判定方針を明文化 (M4 aggregation 設計の input)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_test_flake_retry.py` | 新規 | 8 runtime の test retry 設定 ↔ spec 突合 |
| `tests/scripts/test_check_test_flake_retry.py` | 新規 | fixture-based unit test |
| `.github/workflows/test-flake-retry-gate.yml` | 新規 (または既存 gate に統合) | PR base trigger + weekly schedule |
| `.pre-commit-config.yaml` | 変更 | 新 hook 追加 |
| `docs/spec/test-flake-retry-contract.toml` | 変更 | `[meta].direction = "pre-impl"`、 retry classifier 方針追記、 8 runtime entry の整理 |
| `tests/fixtures/test-flake-retry/` | 新規 | sample CI YAML + test config (aligned / drift) |

### 2.2 処理シーケンス

```text
1. `test-flake-retry-contract.toml` を load し `[runtimes.<name>]` table を dict 化
   (例: { python = { tool = "pytest-rerunfailures", max_retries = 2, timeout_sec = 600, ... } })
2. 各 runtime の CI workflow / test config から retry 設定を抽出:
   - Python: `pyproject.toml` の `[tool.pytest.ini_options]` の `--reruns` 引数 + `python-tests.yml` の override
   - Rust: `.cargo/config.toml` または `cargo-nextest.toml` の `[profile.ci].retries`
   - C#: `dotnet test --rerun-failures` 系 + `.csproj` の TestRunSettings
   - Go: `gotestsum --rerun-fails` 引数 (`go-ci.yml`)
   - WASM: `jest.config.js` の `testRetries` または `--retries` CLI
   - C++: `ctest --repeat until-pass:N` (`cpp-tests.yml`)
   - Kotlin: Gradle test plugin `retry` config (`kotlin-g2p-ci.yml`)
   - Swift: XCTest `XCTRetries` env var (`Tests/PiperPlusG2PTests/`)
3. spec ↔ 各 runtime 設定の (tool, max_retries, timeout_sec, classifier_mode) が一致するか検証
4. 不一致時は exit 1、 一致時は exit 0
5. silent-zero guard: `Collected retry policies (runtimes=N, aligned=M): ...` を必ず stderr に出力
6. retry classifier 方針 (例: `retried_pass_counts_as_flake = true`) を spec から runtime 設定に propagate する rule を明示
```

### 2.3 既存資産との接続

- **流用**: T-005 で確立する 8 runtime walker pattern (model-sha256-manifest と同じ runtime 集合) を再利用
- **共存**: T-006 (`artifact-retention-contract.toml`) の category 設計と独立、 ただし retry log artifact の retention category を T-006 で `test_retry_log` として追加検討
- **補完関係**: M4 T-023 test aggregation で「retry 1 回 pass を flake column に集計」 する logic は本 ticket の `retried_pass_counts_as_flake` policy を引用する

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | check script + 8 runtime config extractor | `scripts/check_test_flake_retry.py` |
| **Runtime scanner** | 1 | 8 runtime の retry 設定抽出 pattern dump | `scripts/_lib/runtime_test_config.py` (新規) |
| **Test author** | 1 | fixture + intentional violation 再現 | `tests/scripts/test_check_test_flake_retry.py`, `tests/fixtures/test-flake-retry/` |
| **Spec / Doc author** | 1 | retry classifier 方針明文化 + spec [meta] + workflow YAML | `docs/spec/test-flake-retry-contract.toml`, `.github/workflows/test-flake-retry-gate.yml` |

**並列度**: 4 並列可。 runtime scanner の出力が implementer の input になる軽い逐次依存。 spec author の classifier 方針は M4 T-023 と相談する必要があり、 user 判断が 1 回入る (~30 分)。

**Agent prompt の与え方**: Explore subagent で 8 runtime の現状 retry 設定 (どの workflow にどの retry flag があるか) を dump。 spec author は dump 結果を input に「全 runtime で揃えるべき retry policy」 を spec 化。 implementer は spec が確定してから着手。 retry classifier 方針は **user 判断が必要** (silent flake をどこまで許容するか) なので、 spec author が 2 案提示し user 選択を待つ。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 8 runtime (Python / Rust / C# / Go / WASM / C++ / Kotlin / Swift) の test retry 設定と spec の突合
- retry tool 名 / max_retries / timeout_sec / classifier_mode (flake vs real fail) の policy 統一
- pre-commit hook + workflow gate の 2 系統統合
- M4 T-023 aggregation で参照される `retried_pass_counts_as_flake` policy の spec 化

**Out of scope**:

- 実際の test 実行と retry 動作の検証 (本 gate は **設定の同期** のみ、 動作確認は各 runtime CI 自体が担当)
- doctest (T-010) の retry policy (`#7` 範囲、 別 ticket)
- flaky test の root cause 分析 / 修正 (個別 PR で対応)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `parse_spec` | aligned spec toml | dict[runtime, RetryPolicy] |
| UT-2 | `extract_pytest_reruns` | `pyproject.toml` with `--reruns=2` | 2 |
| UT-3 | `extract_nextest_retries` | `.cargo/config.toml` with `retries = 2` | 2 |
| UT-4 | `check_alignment` | 8 runtime aligned | exit 0 |
| UT-5 | `check_alignment` | Python max_retries が 1 (spec=2 から drift) | exit 1, runtime=python, expected=2 / actual=1 |
| UT-6 | `check_alignment` | spec の `[runtimes]` table が空 (silent-zero pattern) | `::warning::` 発火 (runtimes=0 ガード) |
| UT-7 | classifier_mode | `retried_pass_counts_as_flake = true` 設定下で retry 1 pass → flake column | (M4 への申し送り用 contract test) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (PR base trigger) | `workflow_dispatch` で実行 → 現状 baseline 全 pass |
| E2E-2 | intentional drift PR (Rust の `retries = 0` を `retries = 1` に変更、 spec=0) | sticky comment が「runtime=rust, expected=0 / actual=1」 を明示 |
| E2E-3 | silent-zero 再現 | fixture で spec の `[runtimes]` を空にして check → `runtimes=0` で `::warning::` |
| E2E-4 | classifier propagate | spec の `retried_pass_counts_as_flake = true` を変更 → 全 runtime CI の `--rerun-fails-report` 等 flag 必須に |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 8 runtime CI workflow が baseline で全 pass (初回 commit で current state を吸収)
- [ ] silent-zero 防御: `Collected retry policies (runtimes=N, aligned=M): ...` が stderr に出力
- [ ] 既存 `.cargo/config.toml` / `pyproject.toml` / `jest.config.js` 等の touch が hook 起動して全 pass

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | retry 設定は CI YAML と test config の 2 箇所に分散 (Python は workflow override が pyproject を上書き等)、 抽出 logic が fragile | spec で「**最終 effective value**」 を canonical とし、 抽出は workflow override 含めた解決後の値を採用。 unresolved な場合は exit 2 | UT-2/UT-3 で override fixture |
| C-2 | retry classifier 方針 (silent flake を許容するか) は user 判断 | spec 着手時に 2 案提示 (`retried_pass_counts_as_flake = true/false`) して user 選択待ち。 採用案を spec [meta] に明記 | review |
| C-3 | retry 0 (retry なし) を強制すると flake CI が増え developer experience 悪化 | spec で runtime 別に max_retries の範囲 (例: 0〜3) を許容、 過剰 retry (>3) を block。 既存 silent flake は M4 aggregation で可視化して根本修正に誘導 | review |
| C-4 | spec の `[runtimes]` が空で success の silent-zero | `Collected retry policies (runtimes=N): ...` defensive log + UT-6 | fixture test |
| C-5 | gotestsum 等 retry tool の version 互換 (gotestsum 1.10 で `--rerun-fails` 形式変更等) | spec [meta] に tool version pin、 抽出 logic を version 別 path で吸収 | review |
| C-6 | Swift XCTest の retry 設定が project 内に存在しない (env var 経由のみ) | Swift は env var override を `release-shared-lib.yml` 内で明示 set、 spec の `runtime.swift.via` を `env_var` と記録 | UT |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`runtimes=0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] paths filter が **誤検出しない / 取り漏れしない** (8 runtime の test config + CI YAML を網羅)
- [ ] sticky comment が runtime / expected / actual を明示しているか
- [ ] fixture が intentional violation を再現できるか (UT-5)
- [ ] classifier_mode の policy が spec [meta] と PR 本文両方に記載されているか
- [ ] M4 T-023 への申し送り (`retried_pass_counts_as_flake` 引用) が ticket 内で明示されているか
- [ ] markdownlint / ruff / codespell 全 pass

---

## 6. 一から作り直すとしたら

### 案 A: retry を spec 化 vs CI 内 retry を全撤廃 (flaky test を必ず修正)

- **概要**: retry 設定 spec を廃止し、 全 runtime の CI 内 retry を 0 に統一。 flake が出たら必ず root cause 修正で対応 (retry で隠さない)。
- **長所**: silent flake が構造的に発生し得ない、 test 品質が継続的に向上する強い incentive を作る。 spec を維持するコストが消える。
- **短所**: 環境依存 flake (network / GPU / clock skew) を test 側で修正できないケースで CI が常時不安定化、 developer velocity 悪化。 OSS contributor の PR が flake で merge 困難になる。
- **採否**: 現時点では採用しない (環境依存 flake が現実には存在)。 retry を許容しつつ aggregation で可視化する方針 (現方針) のほうが現実的。 ただし `max_retries` の上限を spec で厳しく pin (例: 2 まで) し、 retry に頼った flake 放置を抑制。

### 案 B: spec 単一化 vs runtime 別 spec に分割

- **概要**: `test-flake-retry-contract.toml` を 8 spec (`test-flake-retry-python.toml` / `...-rust.toml` / ...) に分割。
- **長所**: runtime ごとに独立して spec を update できる、 PR 影響範囲が小さい。
- **短所**: 横断 view が消失 (M4 aggregation で「全 runtime 揃って retry=2 か」 等の cross-runtime 整合性検証が散逸)。 spec ファイル数が +7 で navigation cost 増。
- **採否**: 現時点では採用しない (横断 view が aggregation の前提)。

### 案 C: retry log artifact から動的に policy を決める (spec 廃止)

- **概要**: spec 廃止、 過去 30 日の CI run の retry log artifact (T-006 で retention 制御) を集計し、 「retry 1 回 pass が runtime ごとに X% を超えたら自動で max_retries を + 1」 等 dynamic policy にする。
- **長所**: 環境変化 (flake 増減) に追従、 spec 更新の手動メンテ不要。
- **短所**: policy が CI 履歴に依存し再現性が下がる、 「なぜ今 max_retries=3 なのか」 を後から読み解けない。 dynamic policy 計算が独立 workflow 化必要で複雑度増。
- **採否**: 現時点では採用しない (再現性低下)。 v3 以降で M4 aggregation が完備した後に retry policy 提案 dashboard として実装する余地あり。

### 結論

現時点での選択は **現方針 (spec が canonical、 8 runtime CI YAML / test config が mirror、 retry を許容しつつ classifier で flake 可視化)**。 理由: 環境依存 flake の現実 + horizontal view の必要性 + 再現可能性。 v2 以降、 M4 aggregation 運用実績を見て案 C (dynamic policy) の検討余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: M4 T-023 test aggregation で本 spec の `retried_pass_counts_as_flake` policy を引用 (FR-8.5 / AC-8.1 の retry-count column)
- **連携 milestone**: M4 (`#8` Test result aggregation) と coupling
- **依存解消**: 本 ticket 完了で T-023 設計から retry classifier 議論が分離 (spec を引用するだけで済む)

### 7.2 引き継ぎ事項 (Handoff)

> 本 ticket で判明した「次の人が知らないとハマる」 情報。

- **classifier 方針は user 判断必須**: 着手時に `retried_pass_counts_as_flake = true` (silent flake を flake column に集計、 厳格) と `false` (retry pass は pass) の 2 案を提示し、 user 決定を spec [meta] に明記
- **effective value 抽出**: workflow override が test config を上書きする runtime (Python / Go / Kotlin) があるため、 抽出 logic は「最終 effective value」 を採用。 spec author は extraction priority を spec [meta] に明文化
- **gotestsum / nextest の version pin**: tool version によって retry flag 形式が変わるため、 spec [meta] に tool version を pin。 dependabot で tool 更新時は spec も同 PR で update
- **Swift retry は env var 経由**: `XCTRetries` env var を `release-shared-lib.yml` 内で set する形式が canonical、 spec の `runtimes.swift.via = "env_var"` と明示
- **silent-zero defensive log**: `Collected retry policies (runtimes=N, aligned=M): ...` を必ず stderr に出力。 N=0 で `::warning::`、 N<8 で `::notice::`
- **M4 T-023 と coupling**: 本 ticket の `classifier_mode` 決定が T-023 の sticky comment column 構成を決める。 T-023 着手時に本 spec を参照すること

### 7.3 未解決の質問

- [ ] `retried_pass_counts_as_flake` を true / false どちらにするか (user 判断)
- [ ] max_retries の許容範囲 (0〜2 か 0〜3 か) を spec で何にするか
- [ ] doctest (T-010) の retry policy を本 spec に含めるか別 spec にするか

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 (FR-5.1 #5-5, AC-5.1), §4.8 (FR-8.5, CON-8.3)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 (`test-flake-retry-contract.toml`)
- Milestone: [`M2`](../milestones/M2-spec-and-docs.md)
- 関連 spec: `docs/spec/test-flake-retry-contract.toml`
- 関連 workflow: `.github/workflows/test-flake-retry-gate.yml` (新設) / 各 runtime CI workflow (`python-tests.yml` / `go-ci.yml` / `cpp-tests.yml` / 他)
- 関連 ticket: T-005 (8 runtime walker 流用)、 T-006 (retry log artifact retention category)、 T-023 (M4 test aggregation で retry-count column)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
