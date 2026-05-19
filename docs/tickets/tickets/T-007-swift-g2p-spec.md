# T-007: `swift-g2p-contract.toml` ↔ `Package.swift` Swift G2P ABI 同期 gate

**チケット ID**: `T-007`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#5-4` (`swift-g2p-contract.toml`)
**Tier**: Tier 2 (blocker、 pre-impl direction)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: なし (M2 内他 ticket と並列可)

---

## 1. タスク目的とゴール

### 目的

`docs/spec/swift-g2p-contract.toml` (既存 snapshot) は Swift G2P package (`PiperPlusG2P`, Issue #387) の ABI surface (公開 type / function / property 名) と semantic version を canonical に定義する。 Swift package は SemVer 厳格 (ABI breaking → major bump 必須) であり、 `Package.swift` の export 設定 + Swift source 公開 API と spec の同期が崩れた場合、 SwiftPM consumer が build error / runtime crash を起こす。

特に Apple platform は SemVer breakage が一度 Maven Central 同等の SPM registry に publish されると revert 不能 (deletion 不可、 yank のみ)、 release 前の ABI drift 検出が release readiness の必須条件。

本 spec の direction は **pre-impl** (spec が canonical、 `Package.swift` + Swift source が mirror)。 spec で定義された ABI surface (export product / library / target、 公開 type / function 名) と実装の差分を CI gate / pre-commit hook で強制する。

### ゴール (Done definition)

- [ ] `scripts/check_swift_g2p_contract.py` (~140 行) を新設、 `swift-g2p-contract.toml` と `Package.swift` の export 構造 + Swift source の `public` 宣言を突合 (FR-5.1, FR-5.2 (a))
- [ ] `.pre-commit-config.yaml` に hook 統合 (`Package.swift` / `Sources/PiperPlusG2P/` 変更時のみ fast-path) (FR-5.2 (b))
- [ ] `.github/workflows/swift-g2p-gate.yml` 新設 または `contract-gates-extended.yml` に job 追加 (FR-5.2 (c))
- [ ] `tests/scripts/test_check_swift_g2p_contract.py` で fixture-based intentional violation を再現 (AC-5.1)
- [ ] `pre-commit run --all-files` の合計 wall clock 30 秒以内維持 (NFR-1.2, AC-5.2)
- [ ] SemVer major/minor/patch の判定 logic を spec [meta] に明文化

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `scripts/check_swift_g2p_contract.py` | 新規 | spec ↔ `Package.swift` + Swift source 突合 |
| `tests/scripts/test_check_swift_g2p_contract.py` | 新規 | fixture-based unit test |
| `.github/workflows/swift-g2p-gate.yml` | 新規 (または既存 gate に統合) | PR base trigger + weekly schedule |
| `.pre-commit-config.yaml` | 変更 | 新 hook 追加 |
| `docs/spec/swift-g2p-contract.toml` | 変更 | `[meta].direction = "pre-impl"`、 ABI canonical schema 整理 |
| `tests/fixtures/swift-g2p/` | 新規 | sample `Package.swift` + Swift source (aligned / drift) |

### 2.2 処理シーケンス

```text
1. `swift-g2p-contract.toml` を load し以下を dict 化:
   - `[products.<name>]` (export 名 / type=library 等)
   - `[targets.<name>]` (dependencies / path)
   - `[public_api.<symbol>]` (kind=struct/class/enum/func, name, signature, since_version)
2. `Package.swift` を parse:
   - 案 a: `swift package dump-package` を実行し JSON 出力を canonical input
   - 案 b: `Package.swift` を Python regex/AST で walk (swift toolchain 不要)
   推奨は (a)、 ただし CI で swift toolchain build cost 高い場合は (b) fallback
3. Swift source (`Sources/PiperPlusG2P/**/*.swift`) を walk し `public` 宣言を抽出 (regex で OK、 `public (struct|class|enum|func|var|let)` pattern)
4. spec ↔ Package.swift dump ↔ Swift source の 3 way 突合:
   - product / target が一致するか
   - 公開 API symbol が aligned か
   - removed symbol が SemVer major bump を伴っているか
5. 不一致時は exit 1 (drift kind: added / removed / signature_changed を明示)
6. silent-zero guard: `Collected swift symbols (products=N, targets=M, public_symbols=K): ...` を必ず stderr に出力
```

### 2.3 既存資産との接続

- **流用**: T-005 の forward-compat schema_version pattern を流用
- **共存**: 既存 `release-shared-lib.yml` (xcframework build) は本 gate と独立 (本 gate は spec ↔ Package.swift、 release workflow は build/publish)
- **補完関係**: T-008 `test-flake-retry-contract.toml` で Swift `XCTest` の retry policy を別途 spec 化、 本 ticket は ABI のみ対象

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | check script + Package.swift parser + Swift source walker | `scripts/check_swift_g2p_contract.py` |
| **Test author** | 1 | fixture 構築 + drift kind 別の violation 再現 | `tests/scripts/test_check_swift_g2p_contract.py`, `tests/fixtures/swift-g2p/` |
| **Spec / Doc author** | 1 | ABI surface schema 整理 + SemVer judgment logic 明文化 + workflow YAML | `docs/spec/swift-g2p-contract.toml`, `.github/workflows/swift-g2p-gate.yml` |
| **Reviewer** | 1 | Swift エコシステム慣習との整合性、 silent-zero guard | review |

**並列度**: implementer / test author / spec author の 3 並列可。 spec author の ABI schema 確定が implementer の input になるため、 spec author が先行する逐次依存あり (~半日)。

**Agent prompt の与え方**: Explore subagent でまず `Sources/PiperPlusG2P/**/*.swift` の全 `public` 宣言を dump、 結果を spec author に渡して current ABI surface の baseline を作る。 implementer は `swift package dump-package` の JSON 出力を canonical input にする方針 (案 a) で先行実装し、 swift toolchain 不在環境向け fallback (案 b) は次フェーズ。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `Package.swift` の products / targets / dependencies と spec の突合
- Swift source の `public` 宣言 (struct / class / enum / protocol / func / var / let / typealias) と spec の `[public_api]` table 突合
- SemVer judgment (added / removed / signature_changed) の自動分類
- pre-commit hook + workflow gate の 2 系統統合

**Out of scope**:

- `internal` / `fileprivate` 宣言 (ABI 影響なし)
- Swift G2P 以外の Swift package (`PiperPlus` 本体、 別 ticket で対象化可能)
- xcframework build / publish 検証 (`release-shared-lib.yml` 範疇)
- `examples/swift-g2p/HelloG2P` CLI (library 本体ではないため対象外、 FR-4.5 と同様の理由)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `parse_spec` | aligned spec toml | dict (products, targets, public_api) |
| UT-2 | `parse_package_swift` | sample `Package.swift` | dict (products, targets) |
| UT-3 | `walk_swift_public` | sample Swift source | list[PublicSymbol] |
| UT-4 | `check_alignment` | aligned 3-way | exit 0 |
| UT-5 | `check_alignment` | spec に無い `public func` を Swift source に追加 (added drift) | exit 1, kind=added |
| UT-6 | `check_alignment` | spec の `public func` を Swift source から削除 (removed drift) | exit 1, kind=removed |
| UT-7 | `check_alignment` | signature 変更 (`func foo() -> Int` → `func foo() -> Double`) | exit 1, kind=signature_changed |
| UT-8 | silent-zero | Swift source 0 件 fixture | `public_symbols=0` で `::warning::` |
| UT-9 | SemVer judgment | removed drift + spec [meta].version が major bump 済み | exit 0 (intentional breaking change) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run (PR base trigger) | `workflow_dispatch` で実行 → 現状 baseline 全 pass |
| E2E-2 | intentional `public func` 追加 PR | sticky comment が「added: PiperPlusG2P.SomeStruct.newFunc(_: Int) -> String」 を明示 |
| E2E-3 | SemVer minor bump で added symbol 受理 | spec [meta].version 1.14.0 → 1.15.0 で added 受理 |
| E2E-4 | silent-zero 再現 | fixture で Sources/ 空にして check → `::warning::` 発火 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 `release-shared-lib.yml` の `concurrency` group 衝突なし
- [ ] silent-zero 防御: `Collected swift symbols (products=N, targets=M, public_symbols=K): ...` が stderr に出力
- [ ] 既存 `swift-g2p-contract.toml` の現状 entries が hook 起動後も全 pass (baseline aligned)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | `Package.swift` の DSL は Swift コードそのもの (静的 parse 困難)、 `swift package dump-package` を CI で実行すると swift toolchain が必要 (macOS / linux-swift) | 案 a (dump-package JSON) を canonical、 fallback として regex parse (案 b) を実装 + cache。 wall clock 影響は NFR-1.1 で計測 | NFR-1.1 |
| C-2 | Swift source の `public` 宣言を regex で walk すると extension / generic / nested type で抽出漏れ | tree-sitter-swift か SwiftSyntax を future option として spec [meta] に記録、 v1 は regex で覆える範囲のみ対象化 | UT-3 / E2E-2 |
| C-3 | SemVer major bump 受理 logic が「spec [meta].version の手動更新」 に依存 → 更新忘れで false positive | exit 1 時にメッセージで「major bump 要 or spec entry 更新要」 と明示、 PR review で双方確認 | review |
| C-4 | silent-zero (`public_symbols=0` で success) | `Collected swift symbols (public_symbols=K): ...` defensive log + UT-8 | fixture test |
| C-5 | CI で swift toolchain build cost (macos runner 必要) → wall clock 圧迫 | 案 b (regex parse) で linux runner 上動作可、 macos runner は release 時のみ起動 | NFR-1.1 |
| C-6 | Swift G2P 以外の Swift package (`PiperPlus` 本体 xcframework wrapper) との混同 | spec の `[products]` で `PiperPlusG2P` 限定と明示、 `Sources/` walk path も限定 | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`public_symbols=0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] paths filter が **誤検出しない / 取り漏れしない** (`Package.swift` + `Sources/PiperPlusG2P/**/*.swift`)
- [ ] sticky comment が drift kind (added / removed / signature_changed) を明示しているか
- [ ] fixture が 3 種の drift kind を全て再現できるか (UT-5/UT-6/UT-7)
- [ ] SemVer judgment が major bump 受理シナリオを通すか (UT-9)
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] `swift package dump-package` 不在環境での fallback path が機能するか (案 b)

---

## 6. 一から作り直すとしたら

### 案 A: `Package.swift` の export を canonical (spec を廃止)

- **概要**: spec toml を廃止し、 `Package.swift` 自体を canonical、 `swift package dump-package` の JSON 出力を baseline JSON として直接 commit。 drift は JSON diff で検出。
- **長所**: Swift エコシステム慣習に最も近い、 single source of truth、 spec の維持コスト 0。
- **短所**: SemVer judgment (major/minor/patch) を spec で明文化できない (JSON は version field のみ)、 「なぜこの API が public か」 の rationale を残せない。 added/removed の意図 (意図的か bug か) が PR diff からしか読み取れない。
- **採否**: 現時点では採用しない (rationale 保持と SemVer 明文化のため spec が必要)。 v2 で Swift エコシステムの慣習に合わせるなら再評価。

### 案 B: `swift package dump-package` output を canonical (spec は SemVer rationale のみ)

- **概要**: ABI surface 自体は `swift package dump-package` の JSON snapshot (`tests/fixtures/swift-g2p/package-dump.snapshot.json` を commit) を canonical input にする。 spec toml は SemVer judgment + rationale のみ。
- **長所**: ABI 抽出が Swift toolchain 任せ (regex の脆さを回避)、 spec は人間が読む rationale に集中。 release 時の version bump 判定が JSON diff で機械的に可能。
- **短所**: snapshot JSON が「ABI 1 行追加 = JSON 大量変更」 になりうる (formatter 差で noise が多い)、 PR review でノイズが増える。 swift toolchain 不在環境で baseline 更新が困難。
- **採否**: 現方針 (spec を canonical) と案 B (dump-package を canonical) を **両方併用**する方向で v1 では設計 (spec が ABI 表、 dump-package JSON が cross-check baseline)。

### 結論

現時点での選択は **現方針 (spec が canonical、 Package.swift + Swift source が mirror、 SemVer rationale は spec に明文化)**。 ただし `swift package dump-package` JSON を補助 baseline として併用 (案 B の利点を取り込む)。 理由: Apple platform の SemVer 厳格度に対し、 rationale / since_version / SemVer judgment を明示できる spec の価値が大きい。 v2 設計時には案 A (Package.swift 単独 canonical) を Swift エコシステム成熟度に合わせて再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: なし (M2 内独立)、 ただし `PiperPlus` 本体 (xcframework wrapper) の ABI gate を future PR で同型 pattern で実装する余地あり
- **連携 milestone**: M3 SLSA L3 (T-017) で xcframework release の attestation `subject` に Swift Package version を含める設計
- **依存解消**: なし (本 ticket 単独完了で release readiness 向上)

### 7.2 引き継ぎ事項 (Handoff)

> 本 ticket で判明した「次の人が知らないとハマる」 情報。

- **`swift package dump-package` の JSON は Swift toolchain version で微妙に変わる**: snapshot 更新時は Swift version を明記、 spec [meta] に `swift_toolchain_version` を pin
- **`public` 宣言の regex parse は generic / extension で抽出漏れる**: 将来 `tree-sitter-swift` か SwiftSyntax 統合を検討 (現状 v1 は regex で覆える範囲のみ対象、 抽出漏れを許容可能な ABI scope に限定)
- **SemVer judgment は手動連動**: spec [meta].version の bump 忘れで false positive、 PR review で双方確認するチェックリストを明文化
- **silent-zero defensive log**: `Collected swift symbols (products=N, targets=M, public_symbols=K): ...` を必ず stderr に出力。 N=0 / M=0 / K=0 で `::warning::`
- **macOS runner 必須化を避ける**: regex parse fallback (案 b) を維持し、 linux runner 上で gate が動作することを保証 (macOS は release workflow 側で別途検証)

### 7.3 未解決の質問

- [ ] tree-sitter-swift / SwiftSyntax への置換を v1 で行うか v2 で行うか
- [ ] `PiperPlus` 本体 (xcframework wrapper) の ABI gate を別 ticket 化するか
- [ ] `swift package dump-package` の cross-check を v1 から組み込むか v2 に回すか

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.5 (FR-5.1 #5-4, AC-5.1)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.1 (`swift-g2p-contract.toml`)
- Milestone: [`M2`](../milestones/M2-spec-and-docs.md)
- 関連 spec: `docs/spec/swift-g2p-contract.toml`
- 関連 workflow: `.github/workflows/swift-g2p-gate.yml` (新設) / `release-shared-lib.yml` (xcframework build)
- 関連 ticket: T-017 (M3 SLSA L3 で xcframework attestation subject に Swift Package version)
- 上流 Issue: #387 (Swift G2P package 導入)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
