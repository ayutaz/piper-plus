# T-011: doc examples blocker 昇格 (PR-C)

**チケット ID**: `T-011`
**Milestone**: [M2 Spec & Docs Gates](../milestones/M2-spec-and-docs.md)
**Proposal 項目**: `#7-C` (Code example execution test — blocker promotion phase)
**Tier**: Tier 2 (blocker — user 判断で昇格)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review (**user 明示判断必須**)
**着手前提**: **T-009 merge 済み + T-010 merge 済み + T-010 merge 後 1 ヶ月の informational 観測完了**。 1 ヶ月運用での false positive 率データ (AC-7.2 ≤ 5%) を集計し、 user に blocker 昇格 / 据え置きを判断してもらった上で着手

---

## 1. タスク目的とゴール

### 目的

T-010 で informational tier (`continue-on-error: true`) として運用してきた doc examples gate を、 1 ヶ月の観測データに基づき **blocker tier に昇格** するかを user 判断材料と共に提示し、 昇格決定の場合に `continue-on-error: true` を削除する PR を提出する。 据え置きの場合は本 PR を closed without merge とし、 観測延長 (例: 追加 1 ヶ月) または gate 取り下げを ticket に記録する。

本 chain (T-009 → T-010 → T-011) の終端で、 「実行可能 docs」 という不変条件を CI gate で構造的に強制するか否かを決定する重大判断 phase。 user 判断が必須 (FR-7.6) で、 Claude Code は判断材料の収集と昇格 PR のドラフト作成までを行う。

### ゴール (Done definition)

- [ ] 1 ヶ月 informational 観測のメトリクス集計レポートを `docs/reference/doc-examples-1month-retrospective.md` (新規) に出力 (fp 率 / wall clock / cache hit 率 / runner 別 fp 内訳 / sticky 警告発火件数)
- [ ] AC-7.2 (fp 5% 以下) の達成可否を data driven で結論
- [ ] blocker 昇格判断基準を ticket に明示 (達成かつ user 承認 → 昇格 / 達成せず → 据え置き → 観測延長 or 取り下げ)
- [ ] user 判断結果 (昇格 / 据え置き / 取り下げ) を本 ticket §7.3 に記録
- [ ] 昇格の場合: `.github/workflows/doc-examples-gate.yml` の `continue-on-error: true` 行 (および `# DELETE_FOR_BLOCKER_T011` marker) を削除、 `docs/spec/doc-examples-contract.toml` の `[execute].tier` を `informational` → `blocker` 変更
- [ ] 据え置きの場合: 本 PR を closed without merge、 observation 延長計画 (追加 1 ヶ月 / 取り下げ) を ticket に記録
- [ ] 昇格時の **rollback path** を ticket に明記 (blocker 化後 1 週間以内に fp 率急増した場合の revert PR 手順)

---

## 2. 実装内容の詳細

### 2.1 追加 / 変更ファイル (昇格判定後)

| path | 種別 | 概要 |
|------|------|------|
| `docs/reference/doc-examples-1month-retrospective.md` | 新規 | 1 ヶ月観測メトリクス集計レポート (人手 + 自動集計の混在) |
| `scripts/aggregate_doc_examples_metrics.py` | 新規 (任意) | 1 ヶ月分の sticky comment / workflow run から fp 率 / wall clock を集計する補助 script (~120 行) |
| `tests/scripts/test_aggregate_doc_examples_metrics.py` | 新規 | aggregate script の fixture test |
| `.github/workflows/doc-examples-gate.yml` | 修正 | **昇格時のみ**: `continue-on-error: true` 削除 + tier marker comment 削除 |
| `docs/spec/doc-examples-contract.toml` | 修正 | **昇格時のみ**: `[execute].tier = "blocker"` に変更 + 昇格日 / 昇格判定根拠を `[execute.history]` に追記 |
| `docs/reference/doc-examples-gate.md` | 修正 | **昇格時のみ**: 「blocker tier」 として運用変更 |
| `docs/tickets/tickets/T-011-doc-examples-blocker.md` | 新規 | 本ファイル (user 判断結果を §7.3 に append) |

### 2.2 処理シーケンス (昇格判定)

```text
1. T-010 merge 日 (day 0) から day 30+ で本 PR 着手
2. 観測 data 収集 (人手 + script):
   a. `gh run list --workflow=doc-examples-gate.yml --created '>=YYYY-MM-DD' --json conclusion,databaseId,createdAt`
   b. 各 run の sticky comment / workflow log から fp / pass / skip / wall clock / cache hit を集計
   c. fp 件数の triage (実装側バグ / fixture flake / network flake / 真の docs drift) を人手分類
3. retrospective レポート生成 (`docs/reference/doc-examples-1month-retrospective.md`):
   - 全体 fp 率 = 真の docs drift / 全実行件数
   - runner 別 fp 率 (rust / csharp などが偏っていないか)
   - wall clock p50 / p95
   - cache hit 率 (AC-7.3 ONNX cache 効果計測)
   - silent-zero 警告発火回数 (NFR-5.3 防御の有効性)
4. AC-7.2 達成判定:
   - fp 率 ≤ 5% かつ silent-zero warning が想定通り発火している → 昇格候補
   - fp 率 > 5% or runner 偏り 大 → 据え置き
5. user に判断提示 (本 ticket §7.3 への記入を依頼):
   - 昇格 → continue-on-error 削除の PR をドラフト化、 user 承認後 merge
   - 据え置き → 観測延長 (追加 1 ヶ月) or 取り下げ を user 選択
   - 取り下げ → gate workflow を `disabled` 化 or 削除する別 PR
6. 昇格時の rollback path 文書化:
   - blocker 化後 1 週間以内に fp が 10% 超過した場合の revert 手順
   - 緊急時 `continue-on-error: true` 再付与の hotfix PR template
```

### 2.3 blocker 化判定基準 (concrete)

| 条件 | 閾値 | 判定 |
|------|------|------|
| 全体 fp 率 (真の docs drift / 全実行) | ≤ 5% (AC-7.2) | **必須** |
| runner 別 fp 率の偏り (max - min) | ≤ 15 ポイント | 偏りが大きいなら runner 別段階昇格を検討 |
| weekly wall clock p95 | ≤ 10 分 (NFR-1.1) | **必須** |
| ONNX cache hit 率 | ≥ 80% (4 weekly run のうち 3 回以上 cache hit) | **必須** (cache 効果が出ていない = R-6 mitigation 失敗) |
| silent-zero warning false positive | observation 期間で 0 件 (期待発火なら fixture test で再現済み) | 推奨 |
| docs drift Issue 量 | open Issue が 5 件以下 (triage が追いついている) | 推奨 |

**全 must 条件 (必須) を満たした上で user 明示承認** → 昇格。 必須を 1 つでも欠く → 据え置き。

### 2.4 昇格 diff の最小化

continue-on-error 削除以外の機能変更は本 PR で行わない (rollback 容易性確保):

```yaml
# .github/workflows/doc-examples-gate.yml
jobs:
  doc-examples:
    runs-on: ubuntu-latest
-   continue-on-error: true  # DELETE_FOR_BLOCKER_T011
    steps:
      - uses: ...
```

```toml
# docs/spec/doc-examples-contract.toml
[execute]
- tier = "informational"
+ tier = "blocker"
+
+ [execute.history]
+ promoted_to_blocker_at = "2026-06-19"
+ promotion_pr = "#XXX"
+ observation_period_days = 30
+ observed_fp_rate = "3.2%"
+ observed_runs = 4  # weekly
+ user_approval = "YYYY-MM-DD ayousanz"
```

### 2.5 既存資産との接続

- **流用**: T-010 の `doc-examples-gate.yml` をそのまま流用 (1 行削除)、 T-009 / T-010 の audit JSON / contract toml をそのまま継続使用
- **共存**: `scripts/check_readme_code_examples.py` (シンボル grep) と並存維持 (CON-7.1)
- **補完関係**: M4 mkdocs (T-022) で blocker 化済み doc examples gate が「docs site の例が必ず実行可能」 という invariant を保証する前提となる

---

## 3. エージェントチームの役割と人数

> 本 PR は「観測 data 集計 + user 判断材料生成 + 昇格 diff 作成」 が中心、 実装新規は少ない。 並列度は低め (~3 worker)。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Aggregator** | 1 | 1 ヶ月分 workflow run / sticky comment から fp / wall clock / cache hit を集計、 retrospective レポート作成 | `scripts/aggregate_doc_examples_metrics.py` + `docs/reference/doc-examples-1month-retrospective.md` |
| **Triage analyst** | 1 | fp 件の人手分類 (実装バグ / fixture flake / network flake / 真の docs drift)、 user 提示用の判断材料 narrative 作成 | retrospective レポート内 §「fp triage」 |
| **Implementer (promotion diff)** | 1 | 昇格時のみ最小 diff (continue-on-error 削除 + spec toml 更新) | `.github/workflows/doc-examples-gate.yml`、 `docs/spec/doc-examples-contract.toml` |
| **Reviewer** | 1 | data 集計の正当性 + 昇格判定基準の適合性 review、 rollback path の妥当性 confirm | review |

**並列度**: Aggregator → Triage analyst は逐次 (data 集計が前提)、 Implementer は user 承認後に着手。 ~3 worker。

**Agent prompt の与え方**: Explore subagent で T-010 merge 後の 4-5 weekly run の `gh run list` を dump、 Aggregator + Triage analyst で集計、 main agent で user 判断材料を構造化して提示、 user 承認後に Implementer で昇格 diff を作成。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- 1 ヶ月観測 data の集計 (人手 + script 補助)
- retrospective レポート (`docs/reference/doc-examples-1month-retrospective.md`)
- 昇格判定基準の適用と user 提示
- 昇格時の最小 diff PR (`continue-on-error` 削除 + spec toml 更新)
- 据え置き / 取り下げ判断の ticket 記録

**Out of scope**:

- gate 自体の機能改善 (改善は別 PR、 本 PR は昇格判定のみ)
- runner 追加 / 削除 (T-010 範疇)
- audit JSON の更新 (T-009 範疇)
- M4 mkdocs (T-022) の docs site 連動 (別 milestone)
- 追加 1 ヶ月観測の実施 (据え置き決定後の別 ticket または T-011 reopen)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `aggregate_doc_examples_metrics.py` | fixture: `gh run list` JSON (5 件、 conclusion=success/failure 混在) | fp 率 / wall clock p50/p95 / cache hit 率を含む JSON |
| UT-2 | `aggregate_doc_examples_metrics.py` | fixture: silent-zero warning が 0 回発火 | retrospective に「silent-zero 防御未検証」 と注記 |
| UT-3 (silent-zero) | `aggregate_doc_examples_metrics.py` | fixture: workflow run が 0 件 (1 ヶ月運用が事実上行われていない) | exit 1 + `::warning::Insufficient observation data: 0 runs` (NFR-5.3) |
| UT-4 | 昇格判定 logic | fixture: fp 3% / wall clock 8 分 / cache 90% | `eligible_for_promotion=true` + user 承認待ち |
| UT-5 | 昇格判定 logic | fixture: fp 6% (閾値超過) | `eligible_for_promotion=false` + 据え置き推奨 |
| UT-6 | spec toml 更新 logic | 昇格 diff | `[execute.history]` に promotion 情報追記 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | 4 weekly run 経過後の本 PR | 実 `gh run list` data で aggregate 実行、 retrospective レポートが生成される |
| E2E-2 | 昇格決定後の `continue-on-error` 削除 | 削除後の workflow を `workflow_dispatch` で run、 1 件 fail 注入で workflow job も fail (blocker 動作) |
| E2E-3 | 据え置き決定 → 取り下げ | gate workflow を `disabled` 化 (`.github/workflows/doc-examples-gate.yml` 削除 or `if: false` 注入) で完了確認 |
| E2E-4 | 昇格後の rollback hotfix | `continue-on-error: true` を再付与する hotfix PR を 5 分以内に作成可能 (PR template 整備済み) |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2、 影響なし)
- [ ] T-010 merge 後の運用が **継続中** であること (observation 期間中に他要因で gate が disable されていないか)
- [ ] silent-zero 防御 (NFR-5.3) が観測期間で機能していたか (UT-2 / UT-3)
- [ ] 昇格時の rollback path が文書化されているか (`docs/reference/doc-examples-gate.md` の「Emergency rollback」 section)

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | 1 ヶ月 observation が「事実上 0 件」 (PR が出ず weekly のみで data 不足) | UT-3 で silent-zero に近い「観測 data 不足」 warning、 観測期間延長を user 提示 | UT-3 |
| C-2 | fp 率 5% を辛うじてクリアして blocker 化 → 直後の 1 週間で flake 急増 | 昇格後 1 週間の hyper care period を定義、 `gh run list` を毎日 check する skill (`/loop /watch-pr` 流用) | rollback hotfix PR template |
| C-3 | runner 別 fp 率の偏り (例: rust だけ 20%) を見落とし全体 5% で昇格 | retrospective レポートに「runner 別 fp matrix」 必須項目化、 偏り > 15pt なら user 提示で警告 | retrospective レポートの review |
| C-4 | 据え置き決定の場合の next step が曖昧 | ticket §7.3 に「据え置き → 追加 1 ヶ月観測 / 取り下げ」 の 2 択を明示、 user 選択を ticket に記録 | ticket 運用 |
| C-5 | blocker 化で外部 PR (contributor) が doc edit の 1 文字変更で fail | docs/ 配下の placeholder / skip directive 規約を `CONTRIBUTING.md` 反映、 PR template に「doc example の追加時は audit 経由」 を明記 | CONTRIBUTING 更新 PR (別 ticket) |
| C-6 | rollback 時の spec toml 更新忘れ (`tier=blocker` のまま continue-on-error が再付与) | rollback hotfix PR template に spec toml も同時 revert する step を含める | PR template |
| C-7 | retrospective レポート作成が agent の幻覚で水増し data になる | aggregator script の出力 JSON を ground truth、 retrospective の数値は全て JSON 由来であることを review で confirm | review |

### 5.2 レビュー項目 (チェックリスト)

- [ ] retrospective レポートの全数値が aggregator script 出力 JSON と一致しているか (幻覚防止)
- [ ] silent-zero pattern を踏んでいないか (`observation_runs: 0` が success にならないか UT-3)
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か (本 PR は新規 workflow なし、 T-010 から不変)
- [ ] `permissions:` が least privilege か (本 PR は workflow 構造変更なし)
- [ ] 昇格 diff が **最小**: continue-on-error 削除 + spec toml 1 行変更のみ、 機能変更を含まないこと
- [ ] rollback PR template が `docs/reference/doc-examples-gate.md` に存在し、 5 分以内に PR 作成可能か (E2E-4)
- [ ] 据え置き決定の場合、 ticket §7.3 に next step (観測延長 or 取り下げ) が user 明示で記録されているか
- [ ] runner 別 fp 偏りを retrospective が table 化しているか
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか
- [ ] user 承認 (本 PR で blocker 昇格を承認する旨) を PR review 内に明記してもらう

---

## 6. 一から作り直すとしたら

### 案 A: blocker 一気昇格 vs runtime 別段階昇格

- **概要**: 本 PR は 6 runner を一斉昇格 (continue-on-error 1 行削除)。 代替案は runner 別に `if: matrix.runner == 'bash'` 等で段階的に blocker 化、 fp 低い runner から順に昇格 (bash → python → go → wasm → rust → csharp)
- **長所**: rollback 時の blast radius が runner 1 つに限定、 runner 別 fp 偏りに対応可能、 contributor からの 1 言語の docs 変更で全 gate が落ちるリスク低減
- **短所**: spec contract / workflow YAML 構造が複雑化、 段階完了までに 6 回 PR を出す必要、 「blocker 化済み runner」 と「informational のままの runner」 の混在状態が長期化
- **採否**: v1 では一気昇格を維持 (1 ヶ月観測 data に基づき判断可能、 単純な diff で rollback も容易)。 ただし runner 別 fp が偏った場合 (C-3) は段階昇格に切替

### 案 B: blocker ではなく warn-only で永続運用

- **概要**: そもそも blocker 化を行わず、 informational tier (sticky comment + Issue auto-create) で永続運用。 CI 観点で「実行可能」 を強制せず、 contributor の friction を最小化
- **長所**: false positive で merge が止まるリスク 0、 contributor friendly、 docs の自由度確保
- **短所**: docs drift が累積する圧力減、 「実行可能 docs」 invariant の構造的保証が崩れる、 M4 mkdocs (T-022) の前提が成立しない
- **採否**: 本 chain (T-009 → T-010 → T-011) の終端としては不採用 (chain の目的が「blocker 化判定」 のため)。 ただし 1 ヶ月観測で fp が大きい場合は本案を「取り下げ」 選択肢として提示

### 案 C: blocker 化条件を fp 率ではなく「過去 4 weekly 連続 0 fp」 にする

- **概要**: 統計的 fp 率 (5%) ではなく「直近 N 回連続 fp 0」 の streak ベース判定。 PR #511 phase 2 で確立した「informational tier × 4 週連続 fp 0 で blocker 化」 pattern (`#3` Rekor + SHA drift と同型)
- **長所**: 統計的閾値より直感的、 既存 pattern との一貫性、 「最近の状態が green」 という時系列保証
- **短所**: 4 weekly = 1 ヶ月だが、 PR 起動 trigger を含めると data 量が weekly のみ より多い (~10-50 run / 月)、 streak ベースは breakage detection に弱い (1 fp で reset で観測延長必須)
- **採否**: v1 では「fp 率 ≤ 5% + 必須条件」 を主、 「4 weekly streak」 を補助条件として併用 (retrospective レポート §2.3 の table に streak も含める)

### 結論

現時点では **一気昇格 + fp 率 + streak 補助** の組合せ。 fp 偏りが大きい場合のみ案 A (段階昇格) に switch、 1 ヶ月で fp 率が想定大幅超過した場合のみ案 B (warn-only 永続) を user 選択肢として提示。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**:
  - 昇格決定 → なし (M2 完了)、 ただし M4 mkdocs (T-022) で blocker 化済み gate が前提として使われる
  - 据え置き決定 → T-011 reopen (追加 1 ヶ月観測後) or 取り下げ PR (gate disable)
- **連携 milestone**: M4 mkdocs (T-022) で「docs site の code example が必ず実行可能」 invariant を utilize、 M3 SLSA L3 (T-017〜) で release 直前の docs sanity check として活用候補
- **依存解消**: 本チケット完了で M2 milestone の `#7` chain (T-009 → T-010 → T-011) が完結

### 7.2 引き継ぎ事項 (Handoff)

> 昇格後 / 据え置き後の運用情報。 chain の最後なので「3 phase の総括」 を残す。

- **昇格後の運用**: blocker tier では PR 単位で gate が動作。 docs 変更 PR では必ず gate を pass させる、 fail 時は audit JSON 再生成 (T-009 re-run) または skip directive 追加で対応
- **rollback path**: `docs/reference/doc-examples-gate.md` の「Emergency rollback」 section に手順記載。 緊急時の hotfix PR は 5 分以内に作成可能 (template 整備済み)
- **chain 全体の retrospective**: 3 phase (T-009 / T-010 / T-011) の運用感想を `docs/reference/doc-examples-1month-retrospective.md` 末尾の「Chain retrospective」 に残し、 post-M2 retrospective で「3 phase 設計が妥当だったか」 を評価
- **据え置き決定時の next step**: ticket §7.3 に「追加 1 ヶ月観測 (T-011 reopen) / 取り下げ (gate disable PR)」 を明示記録
- **取り下げの場合**: gate workflow を `disabled` ではなく削除する、 spec contract の `[execute]` section も削除して docs/spec の consistency を保つ
- **昇格後の fp 監視**: 昇格後 1 週間は hyper care、 `/loop /watch-pr` skill 流用で daily check
- **`# DELETE_FOR_BLOCKER_T011` marker の意義**: 本 chain の last step で削除されることが marker 自身に書かれている。 future 同型 chain 設計時に同 pattern を流用可

### 7.3 未解決の質問 / user 判断記録欄

- [ ] **昇格 vs 据え置き vs 取り下げ 判断** (1 ヶ月観測完了後に user が記入):
  - 判断日: ___
  - 結果: 昇格 / 据え置き / 取り下げ
  - 根拠 (fp 率 / wall clock / cache hit 等の具体数値): ___
  - 据え置きの場合の next step (観測延長 / 取り下げ): ___
- [ ] runner 別 fp 偏りが大きい場合に段階昇格 (案 A) を採用するか
- [ ] 昇格後 1 週間以内に rollback 必要となった場合の事後分析 ticket を起こすか
- [ ] M4 mkdocs (T-022) 着手前に本 chain の retrospective を別 ticket 化するか

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.7 (FR-7.6 / AC-7.2)、 §6 (Tier 2 doctest blocker PR-C)、 §7 R-6 (rollback path)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.2 (`#7` overview)、 §5.1 (NFR-1.1)、 §5.5 (NFR-5.3 silent-zero 防御の observation 期間検証)
- 既存資産: [`scripts/check_readme_code_examples.py`](../../../scripts/check_readme_code_examples.py) (シンボル grep gate、 本 PR で置換しない、 並存維持)
- 関連 spec: `docs/spec/doc-examples-contract.toml` (T-009 で新規、 T-010 で `[execute]` 追加、 本 PR で tier 昇格)
- 関連 workflow: `.github/workflows/doc-examples-gate.yml` (T-010 で新規、 本 PR で `continue-on-error: true` 削除)
- 前提: [`T-009-doc-examples-audit.md`](T-009-doc-examples-audit.md), [`T-010-doc-examples-gate.md`](T-010-doc-examples-gate.md) (両方 merge 必須 + T-010 merge 後 1 ヶ月観測完了)
- 親 milestone: [`../milestones/M2-spec-and-docs.md`](../milestones/M2-spec-and-docs.md)
- 類似 chain (informational → blocker 昇格 pattern): `#3` Rekor + SHA drift (T-001 / T-002)、 CON-3.1 に同型 informational tier 固定 → 4 週連続 fp 0 で user 判断

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
