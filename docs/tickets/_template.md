# T-XXX: チケット タイトル (placeholder)

**チケット ID**: `T-XXX`
**Milestone**: [M? name](../milestones/M%3F-slug.md)
**Proposal 項目**: `#?` (`項目名`)
**Tier**: Tier ? (informational / blocker)
**Status**: 計画中 / 着手 / レビュー中 / 完了
**PR**: (未作成) / `#NNN`
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: 依存チケットがあれば list、 なければ なし

---

## 1. タスク目的とゴール

### 目的

<本タスクが解決する問題、 PR #511 後の現状の gap>

### ゴール (Done definition)

- [ ] <Acceptance Criteria を要求定義 / 要件定義書から転記>
- [ ] <数値化可能な目標 (wall clock / CVE 削減率 / etc.)>

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `.github/workflows/NAME.yml` | 新規 | trigger / schedule / matrix |
| `scripts/NAME.py` | 新規 | 検出 logic |
| `tests/scripts/test_NAME.py` | 新規 | fixture-based test |
| `baseline / spec file` | 新規 | data model |

### 2.2 処理シーケンス

```text
1. step
2. step
3. silent-zero guard: `Collected UNIT (N): ...` を必ず stderr に出力
```

### 2.3 既存資産との接続

- **流用**: 既存 script / pattern
- **共存**: 併存する gate
- **補完関係**: 重複しないことの確認

---

## 3. エージェントチームの役割と人数

> 並列実装可能な単位で agent team を構成。 各 agent は独立して動作し、 不整合は merge 前 review で検出する。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | core logic 実装 | `scripts/check_*.py`, workflow YAML |
| **Test author** | 1 | fixture + unit test | `tests/scripts/test_*.py` |
| **Spec / Doc author** | 1 | spec toml / docs | `docs/spec/*.toml`, `docs/reference/*.md` |
| **Reviewer** | 1 | cross-cutting consistency | review |

**並列度**: <1〜3 worker 同時実行可、 / 逐次必須> (依存関係明示)

**Agent prompt の与え方**: <例: Explore subagent で関連 spec を先に dump、 general-purpose で実装と test を並列、 最後に main agent で integrate>

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- <機能 A>
- <機能 B>

**Out of scope**:

- <別チケット / 別 milestone>

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | function | fixture A | pass/fail/exit code |
| UT-2 | function | fixture B (silent-zero pattern) | `::warning::` 発火 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full workflow run | `act` または `workflow_dispatch` |
| E2E-2 | PR base trigger | sticky comment が期待 markdown を投稿 |
| E2E-3 | silent-zero 再現 | fixture 経由で baseline 半減 → warning 発火 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)
- [ ] 既存 workflow との `concurrency` group 衝突なし
- [ ] silent-zero 防御: `Collected <unit> (N): ...` が stderr に出力

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | silent-zero 再発 | defensive log + fixture test | unit test |
| C-2 | CI minute 圧迫 | cache 利用 + paths filter | `gh run list --json` 観測 |
| C-3 | 既存資産との重複 | 補完関係を spec に明示 | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] silent-zero pattern を踏んでいないか (`Collected <unit>: 0` が success にならないか)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (sliding `@v<major>` 禁止)
- [ ] `permissions:` が least privilege か (default `contents: read`)
- [ ] paths filter が **誤検出しない / 取り漏れしない**
- [ ] sticky comment が「期待値 vs 実測値」 を明示しているか
- [ ] fixture が intentional violation を再現できるか
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] 既存 spec / check / workflow との重複を proposal で確認したか
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか

---

## 6. 一から作り直すとしたら

> 既存実装 / 既存ドキュメントから離れて、 同じ目的を達成する別アプローチを 1-3 案、 思考実験として記載。 「現実装が劣っているか」 ではなく、 **次世代版 (v2) の設計時に再考すべき選択肢** を残すことを目的とする。

### 案 A: <別アプローチ名>

- **概要**: <データフロー / 配置 / 検出方法>
- **長所**: <現実装に対する優位点>
- **短所**: <現実装が選ばれた理由>
- **採否**: <現時点では採用しない / 採用する / 将来検討>

### 案 B: <別アプローチ名>

- (同上)

### 結論

現時点での選択は 案 N (理由: 既存資産との親和性 / 実装 cost / 学習 cost)。 v2 設計時には案 M を再評価する余地あり。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: <T-???>
- **連携 milestone**: <M?>
- **依存解消**: <本チケット完了で blockedBy が外れるチケット>

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。 git history では拾えない context を残す。

- <例: baseline 生成は `workflow_dispatch` で `--update-baseline` flag を渡す必要がある>
- <例: sanitize rule に新 timestamp 形式が出たら `*.toml` に rule 追加>
- <例: 1 image / 1 PR cadence を守ること (まとめ移行禁止)>

### 7.3 未解決の質問

- [ ] <user 判断待ち項目>
- [ ] <次フェーズで再評価>

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §<該当節>
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §<該当節>
- 関連 spec: `docs/spec/<spec>.toml`
- 関連 workflow: `.github/workflows/<name>.yml`

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| YYYY-MM-DD | 初版 | Claude Code |
