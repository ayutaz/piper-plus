# T-006: `artifact-retention-contract.toml` ↔ workflow `retention-days:` 同期 gate

**チケット ID**: `T-006`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#5-3` (`artifact-retention-contract.toml`)
**Tier**: Tier 2 (blocker、 pre-impl direction)
**Status**: 完了 (sweep 6 件 + mode=fail flip まで同 PR 内で完了)
**PR**: #517 (merge: 2026-05-19、 commit f3ef12cd)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (T-004 / T-005 と並列可)

---

## 1. タスク目的とゴール

### 目的

`docs/spec/artifact-retention-contract.toml` (既存 snapshot) は CI artifact / log の保持期間を全 workflow 横断で統制することを目的とする。 現在 108+ workflow が個別に `actions/upload-artifact@v4` の `retention-days:` を指定しており、 値が `1` / `3` / `7` / `14` / `30` / `90` / `365` と散逸 (一部明示無し = GitHub default 90 日)。 これにより:

1. supply-chain forensics (SLSA / Rekor) で必要な artifact が予期せず expire し、 incident response が困難
2. 大型 artifact (cpp build / docker image) が長期保管されストレージ圧迫
3. retention-days 値の **意図** (なぜ 7 日なのか) が散逸し、 PR review で都度判断が要る

本 spec の direction は **pre-impl** (spec が許容値域 `7 / 30 / 90 / 365` のいずれかを定義、 workflow YAML が mirror)。 全 workflow の `retention-days:` を抽出し、 spec で定義された許容値域に収束しているかを CI gate / pre-commit hook で強制する。

### ゴール (Done definition)

- [ ] `scripts/check_artifact_retention.py` (~130 行) を新設、 `.github/workflows/*.yml` の `actions/upload-artifact@<sha>` の `retention-days:` を抽出し spec の許容値域 (categorized) と突合 (FR-5.1, FR-5.2 (a))
- [ ] `.pre-commit-config.yaml` に hook 統合 (workflow YAML 変更時のみ fast-path) (FR-5.2 (b))
- [ ] `.github/workflows/artifact-retention-gate.yml` 新設 または `contract-gates-extended.yml` に job 追加 (FR-5.2 (c))
- [ ] `tests/scripts/test_check_artifact_retention.py` で fixture-based intentional violation を再現 (AC-5.1)
- [ ] `pre-commit run --all-files` の合計 wall clock 30 秒以内維持 (NFR-1.2, AC-5.2)
- [ ] spec の `[categories]` table に「retention 期間の意図 (rationale)」 を category 単位で記載

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_artifact_retention.py` | 新規 | 全 workflow YAML の `retention-days:` 抽出 + spec 突合 |
| `tests/scripts/test_check_artifact_retention.py` | 新規 | fixture-based unit test |
| `.github/workflows/artifact-retention-gate.yml` | 新規 (または既存 gate に統合) | PR base trigger + weekly schedule |
| `.pre-commit-config.yaml` | 変更 | 新 hook 追加 |
| `docs/spec/artifact-retention-contract.toml` | 変更 | category 別の許容値域 + rationale を明文化、 `[meta].direction = "pre-impl"` |
| `tests/fixtures/artifact-retention/` | 新規 | sample workflow YAML (許容 / 違反 / silent 0) |

### 2.2 処理シーケンス

```text
1. `artifact-retention-contract.toml` を load し `[categories.<name>]` table を dict 化
   (例: { "build_artifact" = { values_allowed = [7, 30], rationale = "..." } })
2. `.github/workflows/*.yml` 108 件を walk し:
   - `uses: actions/upload-artifact@<sha>` の step を抽出
   - `with.retention-days:` value (未指定なら GitHub default 90 を sentinel として使う)
   - `with.name:` から category を推定 (prefix pattern: `build-*` → build_artifact, `coverage-*` → coverage, ...)
3. 各 step の (category, retention_days) が spec の `values_allowed` に含まれるか検証
4. 違反時は exit 1 (workflow / step / 値 / 期待値 を明示)、 全 pass で exit 0
5. silent-zero guard: `Collected upload steps (workflows=N, steps=M): ...` を必ず stderr に出力
6. category 推定不能な step は exit 2 (drift とは別扱い、 category 追加 PR を要求)
```

### 2.3 既存資産との接続

- **流用**: `scripts/check_action_pin_baseline.py` の YAML walk pattern を流用
- **共存**: 既存 `action-pin-gate.yml` (SHA pin 検証) は同じ `uses:` step を検証するが独立 (本 gate は `with:` 内のみ対象)
- **補完関係**: M3 SLSA L3 (T-017〜) で attestation artifact の retention を `values_allowed = [90, 365]` に絞る category を別途追加することになる → 本 ticket では category schema を将来拡張に耐える形にする

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | check script + YAML walk logic | `scripts/check_artifact_retention.py` |
| **Test author** | 1 | fixture (許容 / 違反 / category 不明) + intentional violation | `tests/scripts/test_check_artifact_retention.py`, `tests/fixtures/artifact-retention/` |
| **Spec / Doc author** | 1 | category 設計 + rationale 文書化 + workflow YAML | `docs/spec/artifact-retention-contract.toml`, `.github/workflows/artifact-retention-gate.yml` |
| **Reviewer** | 1 | category 設計の妥当性、 silent-zero guard、 既存 108 workflow の baseline 確認 | review |

**並列度**: implementer / test author / spec author の 3 並列可。 ただし category 設計は spec author が先行する逐次依存あり (implementer の抽出 logic と category 推定 logic は spec の table に依存)。

**Agent prompt の与え方**: Explore subagent でまず `.github/workflows/*.yml` 内の全 `retention-days:` 値を集計 (現状 baseline)、 結果を spec author に渡して category 設計の input にする。 implementer は spec author の category schema が確定してから着手。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `.github/workflows/*.yml` 内の `actions/upload-artifact@*` step の `retention-days:` 抽出と spec 突合
- category schema (例: `build_artifact` / `coverage` / `slsa_attestation` / `sbom` / `release` / `debug_log`) と各 category の許容値域
- pre-commit hook + workflow gate の 2 系統統合

**Out of scope**:

- GitHub Pages の build artifact retention (Pages 側で別管理)
- Docker image registry retention (GHCR / Docker Hub 側設定)
- HF Hub model release retention (運用判断)
- artifact name に category prefix を強制する規約 (将来別 PR で)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `parse_workflow_uploads` | aligned workflow YAML | list[UploadStep] (workflow, step_name, name, retention) |
| UT-2 | `infer_category` | name=`build-py-3.13` | category=`build_artifact` |
| UT-3 | `infer_category` | name=`coverage-go` | category=`coverage` |
| UT-4 | `check_alignment` | 全 step aligned | exit 0 |
| UT-5 | `check_alignment` | 1 step が `retention-days: 5` (許容外) | exit 1, 違反 workflow / step / 値 を表示 |
| UT-6 | `check_alignment` | category 推定不能な step (`name: misc-stuff`) | exit 2 |
| UT-7 | silent-zero | upload step が 0 件の workflow fixture | `Collected upload steps (steps=0)` で `::warning::` |
| UT-8 | default retention (未指定) | `with:` に retention-days 行なし | spec の `default_when_unspecified` (90) で検証 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (PR base trigger) | `workflow_dispatch` で実行 → 現状 baseline 全 pass |
| E2E-2 | intentional drift PR (`retention-days: 1` を加える) | sticky comment が「期待値 [7, 30] vs 実測値 1」 を明示 |
| E2E-3 | category 追加 PR | 新 category を spec に追加 + 該当 step を migrate → gate green |
| E2E-4 | silent-zero 再現 | fixture で全 workflow から upload step 削除 → `::warning::` 発火 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 108 workflow が baseline で全 pass (初回 commit で current state を吸収)
- [ ] silent-zero 防御: `Collected upload steps (workflows=N, steps=M): ...` が stderr に出力
- [ ] action-pin-gate.yml との `concurrency` 衝突なし (同じ YAML を walk するが独立 job)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | category 推定が `name:` prefix に依存し fragile (運用が prefix 規約を破ると false positive) | exit code 2 で「category 不明」 を drift と区別、 spec の `[categories.<name>].name_patterns` regex で柔軟に拡張可能に | UT-6 |
| C-2 | spec で許容値を固定すると、 新たな retention 要件 (例: SLSA L3 で 365 日必須) が発生した時に migration cost | category schema を将来拡張に耐える形 (新 category 追加で対応)、 `default_when_unspecified` も spec で pin | review |
| C-3 | silent-zero (upload step 0 件 workflow が success) | `Collected upload steps (steps=N): ...` defensive log + UT-7 | fixture test |
| C-4 | YAML matrix step (`uses: actions/upload-artifact@<sha>` を `${{ matrix.target }}` で動的展開) の抽出失敗 | matrix expand を行わず、 step 単位で抽出。 動的 name は category 推定で `name_patterns` に regex を使う | E2E-3 |
| C-5 | 既存 108 workflow の baseline migration で「許容外」 値が大量に出る | 初回 spec 設計で current state を category 化、 100% pass baseline を作る (drift は今後の PR で検出) | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`steps=0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か (`contents: read` + `pull-requests: write`)
- [ ] paths filter が **誤検出しない / 取り漏れしない** (`.github/workflows/*.yml` のみ、 `*.yaml` も含むか確認)
- [ ] sticky comment が「期待値 vs 実測値」 を明示しているか
- [ ] fixture が intentional violation を再現できるか (UT-5)
- [ ] category schema が将来拡張可能か (新 category 追加 PR で migration できるか)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 108 workflow が baseline で全 pass しているか (初回コミット時に full scan で確認)

---

## 6. 一から作り直すとしたら

### 案 A: retention 規則を spec ではなく `.github/workflows/_retention.yml` reusable に集約

- **概要**: spec toml を廃止し、 すべての upload-artifact step を `uses: ./.github/workflows/_retention.yml@main` reusable workflow 経由で呼ぶ規約に変更。 retention-days は reusable 内で category 別に hardcode。
- **長所**: drift が構造的に起き得ない (reusable 内で唯一の値が定義される)。 新 category 追加は reusable workflow PR 1 件で済む。
- **短所**: 108 workflow を全て reusable 経由に書き換える blast radius が極めて大きい。 GitHub Actions の reusable workflow は input/output 制約が強く、 全 step を reusable 化するのは現実的でない (matrix step / conditional step 等)。
- **採否**: 現時点では採用しない (blast radius 過大)。 v2 で全 release workflow が SLSA L3 経由になった後、 一部 step のみ reusable 化を検討。

### 案 B: spec で固定値強制 vs 範囲を許容 (今回のアプローチ)

- **概要**: 現方針 = category 別に `values_allowed = [7, 30]` のような複数値を許容する。 代替案は category 別に `value = 30` のように単一値固定 (1 category 1 値)。
- **長所**: 単一値固定なら drift 判定が明快、 PR review で都度判断する必要が消える。
- **短所**: 単一値固定は柔軟性ゼロ (例: debug log を 7 日 / 30 日でどちらか選べない)、 既存 workflow の category 細分化が必要になり category 数が肥大化。
- **採否**: 範囲許容 (現方針) を採用。 単一値固定は v2 で「全 workflow を SLSA L3 経由」 まで進んでから再評価。

### 案 C: retention 規則を GitHub repository setting + branch protection で強制 (CI gate を排除)

- **概要**: GitHub の repository-level 設定 (Settings → Actions → Artifact retention) でデフォルトを統制し、 個別 `retention-days:` を禁止する規約に変更。
- **長所**: GitHub の機能で強制されるため drift が起きない。 CI gate 不要。
- **短所**: category 別の差別化 (build = 7 日 / SLSA = 365 日) が不可能、 GitHub default は all-or-nothing。 SLSA L3 attestation 等の長期保存要件と整合しない。
- **採否**: 現時点では採用しない (category 別管理が必須)。

### 結論

現時点での選択は **現方針 (spec で category 別に許容値域を pin、 workflow YAML が mirror)**。 理由: 108 workflow の独立性を維持しつつ、 SLSA L3 等の長期 retention 要件と build artifact 短期 retention を共存可能。 v2 設計時には案 A (reusable workflow 化) を SLSA L3 推進と coupling で再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: M3 SLSA L3 (T-017〜T-021) で attestation artifact の retention category を spec に追加 (`slsa_attestation = { values_allowed = [365] }` 等)
- **連携 milestone**: M4 (T-023 test aggregation) で aggregated JSON の retention 期間を category として追加
- **依存解消**: 本 ticket 完了で M3 SLSA L3 設計から retention 議論が分離 (spec を引用するだけで済む)

### 7.2 引き継ぎ事項 (Handoff)

> 本 ticket で判明した「次の人が知らないとハマる」 情報。

- **初回 baseline migration が重い**: 108 workflow 全部 scan して current state を category 化する必要あり。 spec author は最低 1 日確保
- **category 推定 logic は exit 2 と分ける**: 「category 不明」 は drift とは別 (PR で category 追加が必要)、 exit code を分けて運用判断を明確化
- **`actions/upload-artifact@v3` と `@v4` で `retention-days:` の挙動が異なる**: v3 では default 90、 v4 では明示必須化の noise。 spec の `default_when_unspecified` で吸収
- **silent-zero defensive log**: `Collected upload steps (workflows=N, steps=M): ...` を必ず stderr に出力。 N=0 (workflow 0 件) で `::warning::` (paths filter ミス検出)

### 7.3 未解決の質問

- [ ] category schema を `[categories.<name>]` flat にするか `[categories.<group>.<sub>]` ネストにするか (current state の category 数で判断)
- [ ] `actions/download-artifact@*` 側の検証は対象外で良いか (download は retention に影響しない、 一旦 out of scope)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 (FR-5.1 #5-3, AC-5.1)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 (`artifact-retention-contract.toml`)
- Milestone: [`M2`](../milestones/M2-spec-and-docs.md)
- 関連 spec: `docs/spec/artifact-retention-contract.toml`
- 関連 workflow: `.github/workflows/artifact-retention-gate.yml` (新設) / `action-pin-gate.yml` (共存)
- 関連 ticket: T-017〜T-021 (M3 SLSA L3 で attestation category 追加)、 T-023 (M4 test aggregation category 追加)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
