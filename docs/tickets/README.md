# Tickets — CI/CD 拡張プラン

**親調査**: [proposals/ci-expansion-2026-05.md](../proposals/ci-expansion-2026-05.md) (30 エージェント統合調査)
**親マイルストーン**: [proposals/ci-expansion-milestones.md](../proposals/ci-expansion-milestones.md) (Top 10 → M1-M4 + M-Stretch 分解)

このディレクトリは [親マイルストーン doc](../proposals/ci-expansion-milestones.md) を実装単位のチケットに分解したものです。 マイルストーン doc が "全体マップ / 採用判断 / phase レベル運用ルール" を扱うのに対し、 phase overview は "実装当時の設計動機 / Reinvention 視点" を残します。

---

## M1-M4 実装ステータス

M1.1〜M4.2 の **10 チケットは全て PR #511 で実装完了**。 個別チケット .md は実装ログとしての役目を終えたため削除済み (実装時の設計判断は PR 本文 / 各 workflow docstring / `CHANGELOG.md` Post-v1.12.0 節に集約)。

| Phase | Overview | 完了 ticket |
|-------|----------|------------|
| **M1** Defensive Foundations | [M1-overview.md](./M1-overview.md) | M1.1 cancelled baseline alarm / M1.2 migration guide lint / M1.3 first-PR fast lane |
| **M2** Audio Quality Moat | [M2-overview.md](./M2-overview.md) | M2.1 audio MOS proxy / M2.2 cross-runtime audio parity (両者 informational bootstrap) |
| **M3** ABI & Ecosystem Hardening | [M3-overview.md](./M3-overview.md) | M3.1 public ABI snapshot / M3.2 model card / license auto-injection / M3.3 typosquatting weekly scan |
| **M4** Informational Tier | [M4-overview.md](./M4-overview.md) | M4.1 loanword/PUA forward-compat fuzz / M4.2 phoneme timing monotonicity |
| **M-Stretch** Strategic Bets | [M-Stretch-overview.md](./M-Stretch-overview.md) | (個別ticket未起票、候補 S1-S8、 未着手) |

---

## 運用ルール (各 phase 共通)

[ci-expansion-milestones.md §マイルストーン横断の運用ルール](../proposals/ci-expansion-milestones.md#マイルストーン横断の運用ルール) を参照。 informational tier の昇格判定 (4 週間観測 → blocker 昇格 / 維持 / 削除) は親 doc が canonical。

---

## 関連ドキュメント

- [親調査 ci-expansion-2026-05.md](../proposals/ci-expansion-2026-05.md) — Top 10 選定根拠 / 30 エージェント統合
- [親マイルストーン ci-expansion-milestones.md](../proposals/ci-expansion-milestones.md) — phase 全体マップ / 採用判断 framework
- [既存 spec INDEX](../spec/README.md) — 18+ contract toml
- [既存 reference INDEX](../reference/README.md) — 設計書
- [.claude/README.md](../../.claude/README.md) — 既存 skill / hook / pre-commit gate

## 変更履歴

| 日付 | 変更 | 関連 PR |
|------|------|---------|
| 2026-05-18 | 初版作成 (10 チケット + 5 overview / 計 5314 行 / 4 エージェント並列執筆) | — |
| 2026-05-18 | M1-M4 全 10 個別ticket .md を削除 (実装完了で役目終了、 PR #511 マージ前提) | #511 |
