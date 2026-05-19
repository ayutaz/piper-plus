# CI/CD 拡張 Deferred 8 項目 — チケット index

**作成日**: 2026-05-19
**ベース**: `docs/proposals/ci-expansion-deferred-items{,-requirements,-system-requirements}.md`
**ブランチ**: `docs/ci-expansion-deferred-items-organize`

本ディレクトリは proposal → 要求定義 → 要件定義書 (3 ドキュメント chain) を **PR 着手可能な単位** に分解したチケット集約。 各 milestone と各チケットは相互 link で進捗可視化する。

---

## ドキュメント階層

```text
docs/proposals/
  ci-expansion-deferred-items.md                (proposal v0.2)
  ci-expansion-deferred-items-requirements.md   (要求定義 v0.1, FR/NFR/AC ID 列挙)
  ci-expansion-deferred-items-system-requirements.md (要件定義書 v0.1)
                ↓
docs/tickets/                                   (本ディレクトリ)
  milestones/M*.md                              (実装 phase の括り)
  tickets/T-*.md                                (PR 1 件 = チケット 1 件)
                ↓
.github/workflows/, scripts/, docs/spec/        (実装成果物)
```

---

## マイルストーン × チケット 対応表

完了済みの milestone / チケットは ticket index から削除し、 完了履歴は git log (`git log --oneline --grep='T-00'`) と本リポジトリの merged PR (`#513` / `#517` / `#520` / `#521`) を canonical reference として参照する。 上流 proposal docs の `進捗状況` table も同じ status を保持する。

| Milestone | 範囲 | 着手 tier | チケット | 状態 |
|-----------|------|----------|---------|------|
| [M2 Spec & Docs Gates](milestones/M2-spec-and-docs.md) | doc examples 3 phase の残作業 | Tier 2 | [T-011](tickets/T-011-doc-examples-blocker.md) | 計画中 (informational 1 ヶ月観測後の blocker promote 判断、 PR #521 merge 後の cadence) |
| [M3 Supply Chain](milestones/M3-supply-chain.md) | Distroless 5 image + SLSA L3 5 registry | Tier 3 | [T-012](tickets/T-012-distroless-python-inference.md), [T-013](tickets/T-013-distroless-webui.md), [T-014](tickets/T-014-distroless-wyoming.md), [T-015](tickets/T-015-distroless-cpp-inference.md), [T-016](tickets/T-016-distroless-cpp-dev.md), [T-017](tickets/T-017-slsa-shared-lib.md), [T-018](tickets/T-018-slsa-kotlin-g2p.md), [T-019](tickets/T-019-slsa-rust-g2p.md), [T-020](tickets/T-020-slsa-go-g2p.md), [T-021](tickets/T-021-slsa-npm.md) | 計画中 |
| [M4 Docs Infra](milestones/M4-docs-infra.md) | mkdocs + test aggregation | Tier 3 (別 milestone) | [T-022](tickets/T-022-mkdocs-material.md), [T-023](tickets/T-023-test-aggregation.md) | 計画中 (user 判断待ち) |

---

## 要求定義との対応 (proposal #1〜#8 → チケット)

| Proposal | チケット | Milestone | 状態 |
|---------|--------|----------|------|
| `#1` Distroless | T-012〜T-016 (5 image) | M3 | 計画中 |
| `#2` SLSA L3 | T-017〜T-021 (5 registry) | M3 | 計画中 |
| `#3` Rekor + SHA drift | (旧 T-001 / T-002) | (旧 M1) | **完了 (PR #513)** |
| `#4` CLI help auto-extract | (旧 T-003) | (旧 M1) | **完了 (PR #513)** |
| `#5` spec sync gate × 5 | (旧 T-004〜T-008) | M2 | **完了 (PR #517)** |
| `#6` mkdocs-material | T-022 | M4 | 計画中 |
| `#7` doc examples × 3 phase | (旧 T-009 / T-010) + T-011 | M2 | 一部完了 (audit = PR #520、 gate = PR #521、 blocker promote = T-011 計画中) |
| `#8` test result aggregation | T-023 | M4 | 計画中 |

---

## チケットのライフサイクル

```text
計画中 (planned)
   ↓ user 着手指示
着手 (in_progress)        ← ticket header の Status を更新
   ↓ PR 作成
レビュー中 (in_review)    ← PR 番号を ticket に追記
   ↓ merge
完了 (done)               ← ticket 末尾に完了 log + 後続への申し送り
```

---

## チケットテンプレート

新規チケットは [`_template.md`](_template.md) を copy して使用。 既存 9 セクション (タスク目的とゴール / 実装詳細 / エージェント team / 提供範囲とテスト / 懸念事項とレビュー項目 / 一から作り直すなら / 後続への申し送り / 参照 / 変更履歴) は省略不可。

---

## 進捗可視化

各 milestone 内に **進捗 table** を持つ (チケット status + PR# を ticket header から index 化)。 milestone と ticket は相互 link で navigate 可能。

---

## 関連

- 上流 proposal: [`docs/proposals/ci-expansion-deferred-items.md`](../proposals/ci-expansion-deferred-items.md)
- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../proposals/ci-expansion-deferred-items-requirements.md)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../proposals/ci-expansion-deferred-items-system-requirements.md)
- 既存 skill / hook: [`.claude/README.md`](../../.claude/README.md)
