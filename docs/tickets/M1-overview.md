# M1: Defensive Foundations — Phase Overview

**親マイルストーン**: [ci-expansion-milestones.md §M1](../proposals/ci-expansion-milestones.md#m1-defensive-foundations)
**親調査**: [ci-expansion-2026-05.md](../proposals/ci-expansion-2026-05.md)
**期間**: Month 1 (4 週)
**作成日**: 2026-05-18
**ステータス**: 未着手

---

## フェーズの狙い

piper-plus は既に 93 workflow + 100+ pre-commit hook を持つが、 **構造的弱点が 2 つ顕在化** している。

1. **既存 gate の盲点**: PR #419 で発覚した「required check が `cancelled` で終了した場合に GitHub UI 上は灰色チェックとなり、 baseline 検証が silently skip されたまま merge できてしまう」事故。 検査が多いほど log が読まれず、 green / red の意味が空洞化する。
2. **contributor onboarding 障壁**: 18+ contract gate (PUA / loanword / ORT pin / ruff version 6 箇所同期 等) を全て pass しないと merge できない構造のため、 初回 contributor は事実上 PR を出せず、 メンテナのみが寄与する閉鎖プロジェクトに収束しつつある。

M1 はこの 2 課題を「**merge gate の信頼性軸**」で同時に修復する。 加えて breaking change discipline (CHANGELOG ↔ migration doc の cross-ref) を底上げし、 M2 以降の audio quality moat / ABI hardening の前提条件を整える。 構成要素は全て **難易度 "低"** に限定し、 新規メンテナンス税を最小化する。

---

## 含まれるチケット

| ID | タイトル | Top 10 # | 想定工数 | 優先度 | ステータス |
|----|---------|----------|---------|--------|-----------|
| M1.1 | Cancelled / skipped baseline alarm | #10 | 1-2 PR (~8h) | 高 | 実装完了 (PR #511) |
| M1.2 | Migration guide lint | #3 | 1 PR (~6h) | 高 | 実装完了 (PR #511) |
| M1.3 | First-PR fast lane | #5 | 2 PR (~12h) | 高 | 実装完了 (PR #511) |

合計実工数: PR #511 同梱 (元見積もり 4-5 PR / ~26h)。

---

## 一から設計し直すとしたら (Phase-level reinvention)

### 1. アーキテクチャ: branch protection と CI gate の分離をやり直すなら?

現在は **GitHub branch protection の required check list** と **93 workflow の job name** が一対多で対応しており、 各 workflow が独自に「skip / fail / cancel」を返す。 PR #419 はこの設計のうち「protection が check 名で集合判定するが、 cancel 状態が pass 扱いされる」点に起因する。 ゼロから設計するなら、 **single gateway workflow** (`merge-gateway.yml`) を required にし、 その内部で各 workflow の conclusion を `gh api` で集計、 cancelled / skipped を明示 fail に変換する hub-and-spoke 構造が望ましい。 こうすれば protection rule は 1 行で済み、 個別 workflow の rename / 統廃合に追従しなくて済む。 M1.1 はこの方向へ第一歩を踏み出すが、 protection list の全面置き換えは scope 外とし、 補助 gate として始める。

### 2. 設計: "cancelled silent skip" と "first-PR friction" の同一 phase 統合の妥当性

両者は表面的には別軸 (前者は CI 構造欠陥、 後者は UX) に見えるが、 共通根は **「required check のセット設計が contributor / maintainer / CI 三者で食い違っている」** ことにある。 cancelled が silent skip するのは「maintainer は protection list を信用しているのに CI 側が pass 扱いを返す」ズレ、 first-PR friction は「全 contract gate が均一に required」という雑な protection 設計のズレ。 両者を同一 phase で扱うのは、 **protection rule を再設計する機会を 1 度だけ作る** ことで重複作業を減らすため。 M1.1 で gateway を作り、 M1.3 で gateway 内に「first-PR conditional softening」logic を埋め込めば、 protection list を 2 度書き換える事故を避けられる。

### 3. 実装: 既存 workflow 93 本がある中で、 新規追加すべきか既存改修すべきか

判断軸は **「変更の影響半径 × 既存 workflow の責務凝集度」**。

- 既存 workflow に新 logic を埋め込む選択 → 影響半径小だが、 例えば `parity-hub.yml` に「first-PR なら soft fail」を埋めると `parity-hub.yml` が「parity 検査 + contributor 判定」の 2 責務を持つ。 後で fast-lane を変更するたびに parity-hub に手を入れることになり、 凝集度が崩れる。
- 新規 workflow 追加 → 責務分離は綺麗だが、 93 → 95 への増加分は将来「同数削除」の対象としてレビューする必要がある (net flat policy)。

M1 の 3 タスクは全て **「新規 workflow 追加 + 既存 workflow は触らない (またはトリガー条件のみ追加)」** に倒す。 理由は (a) 既存 18+ contract gate は spec.toml と pre-commit hook で構造的に堅牢化されており触ると壊れる、 (b) M1 期間内で削除候補 2 本以上を特定する宿題を「M1 完了基準」に組み込み net flat を担保する。

### 4. 思考プロセス: PR #419 のような silent skip 事故を未然に防ぐとしたら

CI 検出で塞ぐのは事後対応であり、 根本的には **branch protection 設計時点の "fail-closed" 原則** を徹底する。 GitHub Actions の `cancelled` を「中立」とせず「明示的 fail」と読み替えるのが本来の安全設計。 これを protection rule で表現する手段は現状存在しない (GitHub の制約) ため、 piper-plus 側で gateway workflow を 1 枚噛ませることで fail-closed 化する。 これは「Postel の法則 (受信側は寛容に、 送信側は厳格に)」の反対側、 **"merge gate は paranoid に、 contributor は寛容に"** という非対称設計であり、 OSS の特性 (悪意ある PR と善意の初回 contributor が混在する) に最適化されたパターン。 別案として「protection rule を一切信用せず、 mergeable 状態を `pre-receive` hook (= GitHub では unavailable) で再判定する」も検討したが、 GitHub の制約上不可能で却下。

---

## 後続フェーズへの連絡事項

- **M2 (Audio Quality Moat) は M1.1 を前提とする**: informational tier の workflow (audio MOS proxy / cross-runtime audio parity) を追加する前に、 silent skip 経路を塞いでおく必要がある。 そうでないと「informational だから cancelled でも気にしない」が常態化し、 4 週後の blocker 昇格判断材料 (false positive 率) が取れない。
- **M1.3 で導入する `/run-full-gate` label workflow パターンは M2 / M3 でも再利用可能**: maintainer が informational tier を手動 promote する標準パスとして使える。 ラベル名規約 (`run-full-gate` / `run-mos-gate` / `run-abi-gate` 等) を M1.3 で確立する。
- **net flat policy の宿題**: M1 で 3 workflow 追加するため、 同期間に **3 本の workflow を削除候補としてレビュー** する。 候補 (M1 期間中に評価):
  - `older-action-pin-check.yml` (現在 `pin-action-sha-check.yml` と重複の疑い、 要確認)
  - `legacy-bilingual-*.yml` 系 (v2/v3/v4 アーカイブ移行後の残骸)
  - schedule cron が月曜朝に集中している 6 本のうち、 informational 系で deprecate 可能なもの
- **branch protection の dev branch 変更履歴**: M1.1 完了時に `required_status_check_gate` を required に追加。 M1.3 完了時にも protection に新 check が増える可能性あり。 変更前後の `gh api repos/:owner/:repo/branches/dev/protection` のスナップショットを `docs/reference/branch-protection-history.md` に追記する運用を M1.1 で定義する。

---

## 関連リンク

- [親マイルストーン: ci-expansion-milestones.md §M1](../proposals/ci-expansion-milestones.md#m1-defensive-foundations)
- [親調査: ci-expansion-2026-05.md](../proposals/ci-expansion-2026-05.md)
- feedback memory `feedback_ci_cancelled_baseline.md` (PR #419 教訓、 ユーザー固有 path)
- feedback memory `feedback_pr_body_validate_sections.md` (PR body 構造、 ユーザー固有 path)
- [CONTRIBUTING.md](../../CONTRIBUTING.md) (M1.3 で更新予定)
