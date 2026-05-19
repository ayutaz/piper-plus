# T-004: `release-versions.toml` ↔ git tag / 5 registry 同期 gate

**チケット ID**: `T-004`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#5-1` (`release-versions.toml`)
**Tier**: Tier 2 (blocker、 ただし direction 判定で post-hoc snapshot に倒れる場合は informational 起点)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (M1 完了が望ましいが、 並列着手可)

---

## 1. タスク目的とゴール

### 目的

`docs/spec/release-versions.toml` は既に snapshot として存在するが、 「git tag 実態と spec が一致しているか」 を検証する check script / pre-commit hook / workflow gate が**未実装** (PR #511 後の残カバレッジ穴の 1 つ)。 release 事故 (例: `Cargo.toml` だけ bump し忘れ、 PyPI 1.12.0 / crates 0.3.0 / NuGet 0.3.0 のような mismatch が ship する) を **commit / PR 時点で検出**することが目的。

特に本 spec は要求定義 FR-5.3 で **post-hoc snapshot 候補**と判定されている。 すなわち 「git tag が canonical、 toml は snapshot」 という direction を前提に gate を実装する。 着手前に 30 分の探査 spike (M2 リスク M2-R3) で direction を確定させ、 ticket header に記録する。

### ゴール (Done definition)

- [ ] `scripts/check_release_versions.py` (~120 行) を新設、 `release-versions.toml` の `[snapshot]` table と git tag / 5 registry metadata (PyPI / NuGet / crates.io / npm / Maven Central) の version field を突合 (FR-5.1, FR-5.2 (a))
- [ ] `.pre-commit-config.yaml` に hook 統合 (`release-versions.toml` または対象 manifest が変更された場合のみ走る fast-path) (FR-5.2 (b))
- [ ] `.github/workflows/release-versions-gate.yml` 新設 または `contract-gates-extended.yml` に job 追加 (FR-5.2 (c))
- [ ] `tests/scripts/test_check_release_versions.py` で fixture-based intentional violation を再現 (AC-5.1)
- [ ] direction 判定結果 (post-hoc / pre-impl) を ticket header と spec `[meta]` 並びにコミットメッセージに明記
- [ ] `pre-commit run --all-files` の合計 wall clock 30 秒以内維持 (NFR-1.2, AC-5.2)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_release_versions.py` | 新規 | git tag / 5 registry manifest と `release-versions.toml` を突合 |
| `tests/scripts/test_check_release_versions.py` | 新規 | fixture-based unit test (violation 再現) |
| `.github/workflows/release-versions-gate.yml` | 新規 (または既存 gate に統合) | PR base trigger + weekly schedule |
| `.pre-commit-config.yaml` | 変更 | 新 hook 追加 (paths filter で fast-path) |
| `docs/spec/release-versions.toml` | 変更 | `[meta].direction` の明文化 (post-hoc / pre-impl)、 schema_version bump 検討 |
| `tests/fixtures/release-versions/` | 新規 | sample toml + sample manifest (drift / aligned) |

### 2.2 処理シーケンス

```text
1. `release-versions.toml` を load し `[snapshot]` table を dict 化 (key=tag, value={pypi, nuget, crates, npm, maven})
2. リポジトリ内 5 manifest から canonical version field を抽出:
   - `pyproject.toml` (PyPI) / `src/csharp/PiperPlus.Core/PiperPlus.Core.csproj` (NuGet)
   - `src/rust/piper-cli/Cargo.toml` (crates.io) / `package.json` (npm)
   - Maven Central は `android/piper-plus-g2p/build.gradle.kts` または gradle property
3. direction = post-hoc: 「現 HEAD の tag (latest tag via `git describe --tags --abbrev=0`) に対応する spec entry が **存在** し、 5 manifest と一致するか」 を検証
   direction = pre-impl: 「5 manifest の現在値が spec の latest entry と一致するか」 を検証 (drift があれば spec 更新を要求)
4. 不一致時は exit 1、 一致時は exit 0
5. silent-zero guard: `Collected versions (registries=5, tag=<tag>): pypi=..., nuget=..., crates=..., npm=..., maven=...` を必ず stderr に出力 (NFR-3.2, NFR-5.3)
```

### 2.3 既存資産との接続

- **流用**: M3 SLSA L3 (DEP-5.2) で git tag 抽出 logic を共通化する想定 → `scripts/_lib/git_tag.py` (新規) に切り出し、 T-017 系で再利用
- **共存**: 既存 `cargo-lock-duplicates-baseline.toml` gate は依存 graph 検証で、 本 gate は version field のみ。 重複なし
- **補完関係**: PR template (`pull_request_template.md`) の Risk Level checkbox に「release-versions drift」 を 1 項目追加検討 (out of scope だが申し送り)

---

## 3. エージェントチームの役割と人数

> 並列実装可能な単位で agent team を構成。 spec direction が事前 spike で確定していれば、 implementer / test author / spec author の 3 並列が可能。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | check script 実装、 5 manifest reader 抽象化 | `scripts/check_release_versions.py`, `scripts/_lib/git_tag.py` |
| **Test author** | 1 | fixture 構築 + intentional violation 再現 | `tests/scripts/test_check_release_versions.py`, `tests/fixtures/release-versions/` |
| **Spec / Doc author** | 1 | `[meta].direction` 明文化、 docs/spec README 追記、 workflow YAML | `docs/spec/release-versions.toml` (meta 編集), `.github/workflows/release-versions-gate.yml` |
| **Reviewer** | 1 | direction 妥当性、 silent-zero guard、 pre-commit budget 検証 | review |

**並列度**: implementer / test author / spec author の 3 並列可。 reviewer は最終統合時。 ただし spec direction 確定 spike (~30 分) を agent 起動前に main agent が実施する逐次 phase が前提。

**Agent prompt の与え方**: Explore subagent でまず `pyproject.toml` / `Cargo.toml` / `package.json` / `*.csproj` / `build.gradle.kts` の version field 抽出 pattern を dump、 結果を common knowledge として 3 agent に配布。 implementer / test author は同一 fixture set を共有し、 review 時に diff 検証。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 5 registry (PyPI / NuGet / crates.io / npm / Maven Central) の version field と spec snapshot table の突合
- git tag (`vX.Y.Z`) を canonical 入力とする post-hoc snapshot 設計の確定
- pre-commit hook (paths filter で fast-path) + workflow gate の 2 系統統合

**Out of scope**:

- 学習側 (`src/python/piper_train/`) の internal version
- C++ shared lib (`libpiper_plus.so`) の `soname` (別 spec 候補、 本 ticket では扱わない)
- Swift Package version (T-007 で扱う)
- HF Hub の model release tag (T-005 で扱う)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `parse_pyproject_version` | aligned `pyproject.toml` | `"1.12.0"` |
| UT-2 | `parse_cargo_version` | aligned `Cargo.toml` | `"0.4.0"` |
| UT-3 | `check_alignment` | 5 manifest aligned + tag 一致 | exit 0 |
| UT-4 | `check_alignment` | `Cargo.toml` のみ古い (drift) | exit 1, 差分メッセージに `crates` を含む |
| UT-5 | `check_alignment` | `release-versions.toml` の `[snapshot]` が空 (silent-zero pattern) | `::warning::` 発火 (registries=0 ガード) |
| UT-6 | direction=post-hoc | git tag が `v1.13.0` だが spec に entry がない | exit 1 (entry 追加を要求) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (PR base trigger) | `workflow_dispatch` で実行 → exit 0 |
| E2E-2 | intentional drift PR (npm `package.json` のみ未 bump) | sticky comment が「期待値 1.12.0 vs 実測値 1.11.0」 を明示 |
| E2E-3 | silent-zero 再現 | fixture で `[snapshot]` を空にして check → `Collected versions (registries=0)` で `::warning::` |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 workflow との `concurrency` group 衝突なし
- [ ] silent-zero 防御: `Collected versions (registries=N, tag=...): ...` が stderr に出力
- [ ] `release-versions.toml` 内の既存 entries が hook を起動して全 pass

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | direction (post-hoc / pre-impl) を確定しないまま実装すると、 後で gate semantics が反転する破壊的変更が要る | 着手前 spike (~30 分) で direction を確定、 ticket header に記録 | spike 結果を PR 本文に転記 |
| C-2 | Maven Central version 抽出が `build.gradle.kts` ベースで安定しない (gradle property 経由のケース) | 抽出 logic は両方サポート、 fallback 順序を spec [meta] に明文化 | UT-2 と並列の UT で fixture |
| C-3 | git tag の monotonic 性が崩れる release 履歴 (rc tag / 一時的 revert) | `--tag-pattern` regex を spec で pin、 rc tag は別検証 path | UT で rc tag fixture |
| C-4 | release-versions silent-zero (entry 0 件で success) | `Collected versions (registries=N): ...` defensive log + fixture test | UT-5 / E2E-3 |
| C-5 | 5 manifest 抽出のため CI で `actions/checkout@v5 + fetch-depth: 0` 等 tag 履歴必須 | workflow YAML に `fetch-depth: 0` 明記、 wall clock 影響を計測 | NFR-1.1 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected versions (registries=0)` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (sliding `@v<major>` 禁止)
- [ ] `permissions:` が least privilege か (default `contents: read`、 sticky comment 用に `pull-requests: write` のみ追加)
- [ ] paths filter が **誤検出しない / 取り漏れしない** (5 manifest + spec toml を網羅)
- [ ] sticky comment が「期待値 vs 実測値」 を明示しているか
- [ ] fixture が intentional violation を再現できるか (UT-4 / UT-6)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 spec / check / workflow との重複を proposal 内で確認したか
- [ ] direction 判定根拠が spec [meta] と PR 本文両方に記載されているか

---

## 6. 一から作り直すとしたら

> 既存実装 / 既存ドキュメントから離れて、 同じ目的を達成する別アプローチを思考実験として記載。

### 案 A: git tag 抽出を runtime build に組み込む (CI gate を排除)

- **概要**: 各 runtime の build 時に `git describe --tags --abbrev=0` を埋め込み、 `cargo build` / `pip wheel` 等が tag と manifest 不一致を **build error**として fail させる。 spec toml 自体を廃止し、 CI gate も不要にする。
- **長所**: drift が build 時点で発覚 (CI 待ちより早い)。 spec を docs として維持する必要がない。
- **短所**: build script 改変が 5 runtime 全てに必要、 hermetic build (FR-2.4) で `git` 依存を持ち込むと SLSA L3 (M3) 設計と矛盾。 OSS contributor の手元 build にも tag 履歴が必要になり friction が高い。
- **採否**: 現時点では採用しない (M3 SLSA L3 hermetic build と衝突)。

### 案 B: version 5 列を 5 spec に分割する

- **概要**: `release-versions.toml` を廃止し、 `release-versions-pypi.toml` / `release-versions-nuget.toml` / ... と 5 spec に分割。 各 registry の release workflow に近接配置 (例: `release-pypi.yml` と同 commit でしか update できない pre-commit hook)。
- **長所**: 各 registry が独立して release できる (1 spec / 1 PR cadence と整合)。 drift 検出の粒度が細かい。
- **短所**: 「5 registry 横断で version が揃っているか」 の **横断 view** が失われ、 release readiness signal (M3 / M4 で必要) が散逸。 spec ファイル数が +4 で navigation cost 増。
- **採否**: 現時点では採用しない (横断 view が release 事故防止の本質)。

### 結論

現時点での選択は **現方針 (単一 `release-versions.toml`、 direction=post-hoc snapshot)**。 理由: M3 SLSA L3 が git tag を canonical とする hermetic build を想定しているため、 spec が tag の snapshot として整合する方が自然。 v2 設計時 (M5 Spec Framework 候補) には案 B (5 分割) を再評価する余地あり (M2 完了後に M2 retrospective の中で判定)。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-005 (`model-sha256-manifest.toml`) と同型 pattern で実装するので、 抽出 logic を `scripts/_lib/` 経由で共有
- **連携 milestone**: M3 SLSA L3 (T-017〜T-021) で git tag 抽出 logic を再利用 (DEP-5.2)
- **依存解消**: 本 ticket 完了で T-005 / T-006 / T-007 / T-008 の `scripts/_lib/git_tag.py` 流用 path が空く

### 7.2 引き継ぎ事項 (Handoff)

> 本ticket で判明した「次の人が知らないとハマる」 情報。

- **direction 判定 spike は着手前必須**: ticket 着手時に最初の 30 分で「git tag が canonical か / spec が canonical か」 を spec 編集履歴と release workflow から判定。 判定結果は ticket header + spec [meta].direction + PR 本文 3 箇所に記録 (M2 retrospective で全 spec の direction 分類を集計するため)
- **5 manifest 抽出は `scripts/_lib/` 経由で共有**: T-005 以降が同型 pattern を踏むので、 implementer は最初から `_lib/` への切り出しを念頭に置く
- **rc tag 扱い**: `v1.13.0-rc.1` のような pre-release tag は M3 SLSA L3 で RC release 検証に使う (FR-2.3)。 本 ticket では `--tag-pattern` 正規表現で release tag のみに絞る (rc 扱いは別 PR)
- **silent-zero defensive log**: `Collected versions (registries=N, tag=<tag>): pypi=..., ...` という具体 pattern を踏襲。 N=0 で `::warning::`、 N<5 で `::notice::` の 2 段階

### 7.3 未解決の質問

- [ ] direction は post-hoc snapshot で確定するか、 pre-impl spec として運用するか (spike 後に user 判断)
- [ ] Maven Central version 抽出を gradle property 経由にするか、 `build.gradle.kts` 直接 parse にするか
- [ ] rc tag を gate 対象に含めるか、 release tag のみに絞るか

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 (FR-5.1 #5-1, AC-5.1, DEP-5.2)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 (`release-versions.toml`)
- Milestone: [`M2`](../milestones/M2-spec-and-docs.md)
- 関連 spec: `docs/spec/release-versions.toml`
- 関連 workflow: `.github/workflows/release-versions-gate.yml` (新設) / `release-shared-lib.yml` (tag 抽出 logic の reference)
- 関連 ticket: T-005 (同型 spec gate)、 T-017〜T-021 (M3 SLSA L3 で git tag 抽出 logic 再利用)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
