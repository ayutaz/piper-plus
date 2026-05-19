# M4: Docs Infra (別 milestone、 user 判断待ち)

**Milestone ID**: `M4`
**Tier**: Tier 3 (別 milestone)
**Status**: user 明示判断待ち (3 件)
**期間目安**: M3 merge 後、 user 判断完了から 4 週間
**前提**: M3 完了 + user による 3 件判断完了 (FR-6.3 公開範囲 / FR-6.4 i18n 戦略 / FR-6.5 配信先)

---

## 1. 目的

`#6 mkdocs-material` (統合ドキュメント配信) と `#8 test result aggregation` (7 runtime test 統計の sticky 集約) を、 docs infra の 1 milestone として独立扱い。 両者は **dashboard 化** という共通テーマで coupling (`#8` の集約結果を `#6` の dashboard で公開する含意あり)。

ただし `#6` は **user 明示判断 3 件** を経ないと proposal phase から進めない:

- FR-6.3 公開範囲 (`docs/proposals/` を含めるか、 etc.)
- FR-6.4 i18n 戦略 (二重 mirror 維持 vs mkdocs-static-i18n 移行)
- FR-6.5 配信先 (GitHub Pages / Cloudflare / Netlify / HF Spaces)

`#8` は独立性が高く、 `#6` 完了前でも sticky comment 形式までは実装可能。 ただし「dashboard 化」 まで含めると `#6` 完了が前提。

---

## 2. 配下チケット

| ID | タイトル | 提案項目 | 着手条件 | Status | PR |
|----|--------|---------|--------|--------|----|
| [T-022](../tickets/T-022-mkdocs-material.md) | mkdocs-material 統合配信 | `#6` | user 明示判断 3 件完了 | 計画中 (proposal phase) | — |
| [T-023](../tickets/T-023-test-aggregation.md) | 7 runtime test result aggregation | `#8` | M1 sticky pattern 確立済 | 計画中 | — |

### 依存関係

- T-022 は user 判断待ち、 着手前に **`docs/proposals/mkdocs-deployment-strategy.md`** で 3 件判断資料を提示する必要 (T-022 内に proposal phase 明記)
- T-023 は sticky comment 部分は M1 直後でも着手可能、 dashboard 統合部分は T-022 完了が前提

---

## 3. 受け入れ基準 (Milestone レベル)

### T-022 (mkdocs)

- [ ] dashboard URL が公開アクセス可能 (AC-6.1)
- [ ] 内蔵検索が `q=ssml` 等の query で適切な doc を返す (AC-6.1)
- [ ] 既存 `https://github.com/ayutaz/piper-plus/blob/dev/docs/.../...` link が **維持** (AC-6.2、 dead link 化禁止)
- [ ] `link-check.yml` (既存) が mkdocs nav-relative path に対応した上で全 link 解決 (AC-6.3)

### T-023 (test aggregation)

- [ ] 7 runtime 全 test 結果が 1 sticky comment に集約、 各 runtime の pass/fail/skip/duration/retry-count が一覧表示 (AC-8.1)
- [ ] 「last green commit が全 runtime で揃っているか」 の judgment column を sticky に含む (AC-8.2)
- [ ] aggregator script が silent-zero pattern を踏まない: defensive log `Collected <unit>: N` を必ず stderr に出力 (AC-8.3)

---

## 4. 一から作り直すとしたら (Phase rethink)

### 設計思考: docs と test を同一 dashboard にする vs 分離する

現方針は T-022 (mkdocs docs) と T-023 (test aggregation) を **同一 dashboard で配信** する含意がある (`#6 / #8` coupling)。

代替案: **完全に分離する** — docs は mkdocs / Pages、 test aggregation は GitHub Actions の sticky comment + Issue で完結、 dashboard 化は **しない**。

#### 長所

- T-022 と T-023 の依存が完全に解ける (T-023 が M1 と並行着手可能)
- mkdocs の plugin 拡張 (test result 表示 plugin の自作) が不要
- sticky comment / Issue は GitHub native で merge readiness 判定が PR 上で完結 (dashboard を別途見に行かない)

#### 短所

- 「release readiness signal」 を見る場所が分散 (PR sticky vs mkdocs)
- 過去 release の test 結果 trend が PR 上の sticky では追えない (sticky は per-PR、 mkdocs なら time-series 可)
- マーケティング目的 (project 健全性を外部に見せる) の dashboard 価値が下がる

#### 結論

**v1 では「分離」 を採用候補に追加**。 T-022 着手前 (proposal phase) で user に提示する 3 件判断 (FR-6.3 / FR-6.4 / FR-6.5) に **「FR-6.6 dashboard 統合 yes/no」 を追加** することを提案。 これは T-022 ticket の §1 で明示する。

### 設計思考: mkdocs ではなく Astro / Docusaurus / Hugo を採用するなら

要求定義 FR-6.1 は mkdocs-material 固定だが、 ドキュメント SSG (Static Site Generator) には他選択肢がある:

代替案 A: **Docusaurus** (React-based、 Meta 製) — TypeScript / React で plugin 拡張、 i18n 標準、 versioning 標準
代替案 B: **Astro** (multi-framework) — markdown + 部分 hydration、 build 高速
代替案 C: **Hugo** (Go-based) — build が極めて高速、 plugin 不要設計

#### 長所 (Docusaurus)

- versioning 標準サポート (v1.11 / v1.12 docs を併存可能、 piper-plus の release cadence と整合)
- i18n が plugin 不要 (mkdocs-static-i18n の二択 = FR-6.4 を回避可能)
- React component 埋め込みで「合成試聴 player」 のような interactive doc が作れる (WASM demo との統合)

#### 短所 (Docusaurus)

- Python community との culture mismatch (mkdocs は Python 系、 piper-plus の主要 audience と整合)
- Node.js toolchain 必須 (現状 docs build に Node 不要)
- 既存 link 移行 cost が mkdocs より高い (path namespace が異なる)

#### 結論

**v1 では mkdocs-material 維持 (FR-6.1 通り)**。 Astro / Docusaurus 採用判断は **本ticket の proposal phase (T-022)** で user に提示する 3 件判断のうち FR-6.5 (配信先) と coupling して再評価。

### 設計思考: test aggregation を SaaS (Datadog / BuildPulse) に委譲するなら

T-023 は self-hosted な aggregation (`scripts/aggregate_test_results.py` + sticky comment) を構築する設計。 SaaS 製品で同等機能を提供するものがある。

代替案: **BuildPulse** (flaky test detection 専門) / **Datadog CI Visibility** / **TestRail**

#### 長所

- flake detection / trend analysis / pass-rate dashboard が built-in
- self-hosted code の maintenance 0 (PR #511 phase 2 の argparse bug 系の落とし穴を踏まない)
- 7 runtime の JUnit XML を upload するだけで dashboard が育つ

#### 短所

- **OSS project にとって SaaS 依存は政治的に重い** (piper-plus は MIT / Apache の文化、 vendor lock-in 嫌悪)
- 月額 cost (Datadog / BuildPulse とも seat-based 課金)
- user account 管理 / SSO 等の運用が増える
- 「project が SaaS 経由でしか健全性を示せない」 状態は contributor 離れの原因に

#### 結論

**v1 では self-hosted を維持 (FR-8.1 〜 FR-8.5 通り)**。 ただし「flake detection 専門」 機能だけ BuildPulse を **限定使用** する案を後続で検討余地あり。 M4 retrospective で「self-hosted aggregator の維持 cost vs SaaS の vendor lock-in cost」 を秤量。

---

## 5. リスクと対策 (Milestone 共通)

| ID | リスク | 対策 |
|----|------|------|
| M4-R1 | mkdocs 移行で外部 inbound link 死亡 (R-3 = 要求定義 §7) | GitHub raw URL を canonical 互換維持 (AC-6.2)、 mkdocs 配信は重複 URL として共存 |
| M4-R2 | T-022 user 判断 3 件が長期化、 M4 全体が stall | T-022 proposal phase で user に判断資料 (各選択肢の長短 + 採用事例 + cost) を提示、 30 日内に決定を期待 |
| M4-R3 | T-023 silent-zero pattern (`Collected <unit>: 0` が success) | M1 で学習済みの defensive log pattern を T-023 で必須化、 fixture test で再現 (AC-8.3) |
| M4-R4 | 7 runtime の test 件数が runtime 間で「test 1 件」 の粒度がずれる (CON-8.1) | sticky comment 内に「Rust mod 単位、 C# class 単位、 ...」 と粒度注記 |

---

## 6. 後続 Milestone への申し送り

### post-M4 retrospective へ

- mkdocs ↔ test dashboard 統合の採否 (本ドキュメント §4 「分離」 vs 「統合」)
- 自前 aggregator の維持 cost vs SaaS (BuildPulse 等) の vendor lock-in cost 比較
- mkdocs-material 以外の SSG (Docusaurus / Astro) 採用余地

### release workflow へ

- T-022 完了で各 release notes に「Documentation」 セクション追加 (mkdocs URL を明示)
- T-023 完了で release readiness signal が sticky comment で可視化 → release tag 切り出し前の go/no-go 判定基準に組み込む

### 外部 contributor 向け

- mkdocs site 公開後、 `CONTRIBUTING.md` の「Documentation contributions」 章を更新 (mkdocs path への変換規則を明示)
- test aggregation sticky を contributor が PR review で「全 runtime green か」 自己判定する基準として周知

---

## 7. 関連ドキュメント

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.6 / §4.8
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.5 / §4.6
- 既存 docs deploy: `.github/workflows/deploy-webassembly-demo.yml`, `deploy-huggingface.yml`
- 既存 coverage: `.github/workflows/coverage-aggregation.yml`
- 親 index: [`../README.md`](../README.md)

---

## 8. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
