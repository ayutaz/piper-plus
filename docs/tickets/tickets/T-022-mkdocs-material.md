# T-022: mkdocs-material 統合配信

**チケット ID**: `T-022`
**Milestone**: [M4 Docs Infra](../milestones/M4-docs-infra.md)
**Proposal 項目**: `#6` (`mkdocs-material 統合配信`)
**Tier**: Tier 3 (別 milestone)
**Status**: 計画中 (proposal phase, user 判断 3-4 件待ち)
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**:

- M3 (Distroless + SLSA L3) merge 完了
- user 明示判断 **3 件** 完了 (FR-6.3 公開範囲 / FR-6.4 i18n 戦略 / FR-6.5 配信先)
- 加えて M4 milestone §4 で議論された **FR-6.6 dashboard 統合 yes/no** (T-023 集約結果を mkdocs に統合するか) を 4 件目の判断項目として user に提示
- 着手前に **`docs/proposals/mkdocs-deployment-strategy.md`** を新規作成して user 判断資料 (各選択肢の長短 / 採用事例 / cost) を提示する proposal phase を経る

---

## 1. タスク目的とゴール

### 目的

piper-plus は `docs/` 配下に約 150 .md ファイル (~500 link) を抱え、 仕様 (`docs/spec/*.toml`) / マイグレーション (`docs/migration/`) / リファレンス (`docs/reference/`) / ガイド (`docs/guides/`) / proposal (`docs/proposals/`) が GitHub raw URL でしか navigate できない。 内蔵検索が無く、 i18n は `README.md` / `README-ja.md` の二重 mirror に限定。 7 ランタイム + 8 言語 G2P + 学習基盤の多面的 OSS にもかかわらず、 「初学者が landing → install → 使用 → API reference」 の動線が **GitHub repo の README 1 枚** に集約されている状態。

本チケットは要求定義 §4.6 (FR-6.1〜FR-6.6 + AC-6.1〜AC-6.3) を実装し、 **mkdocs-material** による統合ドキュメント配信を立ち上げる。 ただし FR-6.3 / FR-6.4 / FR-6.5 の 3 件 + 派生 FR-6.6 の 計 4 件は **user の明示判断必須** のため、 実装前段で proposal phase を挟む。

### ゴール (Done definition)

- [ ] **AC-6.1**: deploy 後の dashboard URL が公開アクセス可能、 内蔵検索が `q=ssml` 等の query で関連 doc を返す
- [ ] **AC-6.2**: 既存 `https://github.com/ayutaz/piper-plus/blob/dev/docs/...` 形式の inbound link が **dead 化しない** (GitHub raw URL を canonical 互換維持、 mkdocs 配信は重複 URL として共存)
- [ ] **AC-6.3**: `link-check.yml` (既存) が mkdocs nav-relative path に対応した上で **全 ~500 link が解決**
- [ ] user 判断 4 件が `docs/proposals/mkdocs-deployment-strategy.md` 経由で確定し、 proposal phase を終了
- [ ] 既存 `~150 .md` の link 修正 (相対 path → mkdocs nav-relative) を **mass edit** で実施、 約 500 箇所
- [ ] mkdocs build が wall clock **10 分以内** (NFR-1.1 準拠、 deploy workflow 含む)

---

## 2. 実装内容の詳細

### 2.0 Proposal phase (着手前に user 判断 4 件を確定)

着手前に **`docs/proposals/mkdocs-deployment-strategy.md`** を新規作成し、 以下 4 件の選択肢 (長短 / 採用事例 / cost) を user に提示。

#### 判断 1: FR-6.3 公開範囲

| 範囲 | 含める / 除外 | 備考 |
|------|-------------|------|
| `.claude/` (内部用 skill / hook) | 除外 (確定) | 開発 internal、 外部公開価値なし |
| `docs/proposals/` (roadmap) | **user 判断** | roadmap 公開リスク (競合に進捗が見える) vs 透明性 |
| `docs/migration/` | 公開 (推奨) | release notes と coupling |
| `docs/guides/` | 公開 (推奨) | 初学者動線の中心 |
| `docs/reference/` | 公開 (推奨) | API doc / CLI ref |
| `docs/spec/` | **user 判断** | 内部設計 toml、 contributor 向け価値あり |
| `docs/tickets/` | 除外 (推奨) | proposal の派生、 公開する価値低 |

#### 判断 2: FR-6.4 i18n 戦略

| 案 | 概要 | 長所 | 短所 |
|----|------|------|------|
| (a) 二重 mirror 維持 | 既存 `README.md` / `README-ja.md` 体制を `docs/en/*` / `docs/ja/*` に拡張 | 既存 workflow との整合性、 学習 cost 低 | maintain 2x、 翻訳遅延で drift |
| (b) `mkdocs-static-i18n` plugin | nav 階層内に `i18n: en` / `i18n: ja` を埋め込み、 build 時に 2 site 生成 | 公式 plugin、 fallback 自動 | 既存 .md の i18n metadata 追記 ~150 file |

#### 判断 3: FR-6.5 配信先

| 案 | URL 例 | 長所 | 短所 |
|----|--------|------|------|
| (a) GitHub Pages | `https://ayutaz.github.io/piper-plus/` | free / 既存 `ayutaz` 認証 | bandwidth 100GB/月 制約、 build minute 圧迫 |
| (b) Cloudflare Pages | `https://docs.piper-plus.dev` 等 custom domain | unlimited bandwidth、 edge CDN | DNS 設定 + Cloudflare account 要 |
| (c) Netlify | 同上 | preview deploy / branch deploy 強い | free tier 制限 (build 300 min/月) |
| (d) HF Spaces | `https://huggingface.co/spaces/<org>/piper-plus-docs` | 既存 HF account 流用、 model と同居 | Space は app 用途、 静的 docs は overkill |

#### 判断 4 (新規追加): FR-6.6 dashboard 統合 yes/no

M4 milestone §4 で議論された設計分岐: T-023 (test result aggregation) の sticky comment / JSON artifact を **mkdocs site 内 dashboard page として埋め込むか**。

| 案 | 概要 | 長所 | 短所 |
|----|------|------|------|
| (a) **統合**: mkdocs に test trend dashboard を組み込む | T-023 の `test-aggregate.json` を mkdocs build 時に取り込み、 `/dashboard/` で時系列表示 | 「project 健全性」 を 1 URL で外部に見せられる、 マーケティング価値 | mkdocs plugin 自作 (~100 行)、 build に test artifact 取得依存、 trend データを HF / Pages に蓄積する必要 |
| (b) **分離**: T-023 は PR sticky comment + Issue で完結、 mkdocs は docs のみ | T-022 / T-023 の依存解消、 並行着手可能 | dashboard plugin 不要、 mkdocs build が test artifact に依存しない | release readiness signal が PR 上の sticky に限定、 過去 release trend を追えない |

#### 既存 deploy / coverage workflow との namespace 衝突回避

| 既存 workflow | path namespace | 衝突回避策 |
|-------------|---------------|----------|
| `deploy-webassembly-demo.yml` | `/wasm-demo/` (Pages 内 sub-path) | mkdocs を `/` に配信、 demo は `/wasm-demo/` で共存 |
| `deploy-huggingface.yml` | HF Space (別ホスト) | 衝突なし |
| `coverage-aggregation.yml` | artifact のみ、 Pages 配信なし | 衝突なし (FR-6.6 統合判断次第で coupling) |

### 2.1 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docs/proposals/mkdocs-deployment-strategy.md` | 新規 | user 判断 4 件の選択肢提示 |
| `mkdocs.yml` | 新規 | nav 階層 + i18n + theme (material) + search + plugins |
| `.github/workflows/docs-deploy.yml` | 新規 | mkdocs build + Pages deploy (paths filter / permissions) |
| `requirements-docs.txt` | 新規 | `mkdocs-material` / `mkdocs-static-i18n` / `mkdocs-redirects` 等 pin |
| `docs/index.md` | 新規 | landing page (現 `README.md` 抜粋) |
| `docs/getting-started/*.md` | 新規 | install / quickstart (現 `README.md` 抜粋) |
| `docs/**/*.md` (~150 file) | 修正 | 相対 path → mkdocs nav-relative path に mass edit (~500 箇所) |
| `link-check.yml` (既存) | 修正 | mkdocs build 後の path に対応 (AC-6.3) |

### 2.2 `mkdocs.yml` schema 案

```yaml
site_name: Piper Plus
site_url: <FR-6.5 で確定>
repo_url: https://github.com/ayutaz/piper-plus
repo_name: ayutaz/piper-plus
theme:
  name: material
  features:
    - navigation.tabs
    - navigation.sections
    - search.highlight
    - search.suggest
nav:
  - Home: index.md
  - Getting Started:
    - Installation: getting-started/install.md
    - Quickstart: getting-started/quickstart.md
  - Runtimes:
    - Python: runtimes/python.md
    - Rust: runtimes/rust.md
    - C#: runtimes/csharp.md
    - Go: runtimes/go.md
    - WASM: runtimes/wasm.md
    - C/C++: runtimes/cpp.md
    - Kotlin/Android: runtimes/android.md
  - API Reference: reference/*.md
  - Migration: migration/*.md
  - Spec (contributor): spec/*.md  # FR-6.3 で公開判断
plugins:
  - search
  - i18n:                          # FR-6.4 (b) 採用時
      default_language: en
      languages:
        - locale: en
          name: English
        - locale: ja
          name: 日本語
```

### 2.3 `docs-deploy.yml` schema 案

```yaml
name: Docs Deploy
on:
  push:
    branches: [dev]
    paths:
      - 'docs/**'
      - 'mkdocs.yml'
      - 'requirements-docs.txt'
      - '.github/workflows/docs-deploy.yml'
  workflow_dispatch:
permissions:
  contents: read
  pages: write         # FR-6.5 (a) GitHub Pages 時のみ
  id-token: write      # OIDC (Pages deploy)
concurrency:
  group: docs-deploy
  cancel-in-progress: true
jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - run: pip install -r requirements-docs.txt
      - run: mkdocs build --strict
      - uses: actions/upload-pages-artifact@v3
        with: { path: site/ }
      - uses: actions/deploy-pages@v4
```

### 2.4 既存資産との接続

- **流用**: `link-check.yml` (既存) を mkdocs nav-relative path 対応に修正、 `pre-commit run --all-files` で path 検証
- **共存**: `deploy-webassembly-demo.yml` (WASM demo を `/wasm-demo/`)、 `deploy-huggingface.yml` (HF Space は別ホスト) と path namespace 分離
- **補完関係**: `coverage-aggregation.yml` の artifact は FR-6.6 (a) 採用時のみ取り込み、 (b) なら無関係
- **canonical 互換維持**: `https://github.com/ayutaz/piper-plus/blob/dev/docs/...` URL を **削除しない** (AC-6.2)、 mkdocs 配信は重複 URL として共存

### 2.5 処理シーケンス (deploy)

```text
1. PR merge → push to dev with paths: ['docs/**', 'mkdocs.yml']
2. docs-deploy workflow trigger
3. mkdocs build --strict (nav-relative link 不一致で fail-fast)
4. site/ artifact upload
5. Pages deploy (or Cloudflare / Netlify / HF Spaces)
6. link-check.yml が mkdocs build 後の path で全 ~500 link を再検証
7. silent-zero guard: Collected pages (N): ... を必ず stderr に出力
```

---

## 3. エージェントチームの役割と人数

> proposal phase + 大規模 mass edit + UI/UX を含むため **5-6 人** 構成。 並列度高め (mass edit と nav 設計を分離して 並行)。

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | `mkdocs.yml` + `docs-deploy.yml` + `requirements-docs.txt` | nav 階層 / theme / plugin pin |
| **Migration engineer** | 1-2 | ~150 .md の 相対 path → mkdocs nav-relative mass edit (~500 箇所) | `docs/**/*.md` modify (mass edit script + 検証) |
| **Doc reviewer** | 1 | landing / quickstart / getting-started の wording 再構成 | `docs/index.md`, `docs/getting-started/*.md` 新設 |
| **UI/UX reviewer** | 1 | mkdocs-material theme カスタマイズ / favicon / og:image / nav 動線 | theme overrides + screenshot レビュー |
| **SEO / inbound link auditor** | 1 | 既存 inbound link (issue / blog / PR) の dead 化リスク検証 | `scripts/audit_inbound_links.py` (option) + AC-6.2 確認 |
| **Maintainer** | 1 | proposal phase の user 判断 4 件 + merge gate | review + merge |

**並列度**: proposal phase 完了後、 Implementer / Migration / Doc / UI/UX は **並行可**。 SEO auditor は merge 直前。

**Agent prompt の与え方**: Explore subagent で既存 .md ~150 file の link pattern を dump → general-purpose で mass edit script 作成 + 並行で `mkdocs.yml` 起草 → main agent で integrate して `mkdocs build --strict` が通るまで iterate。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `mkdocs.yml` + nav 階層 (Getting Started → Runtimes → API Reference → Migration → Spec)
- `docs-deploy.yml` (FR-6.5 で確定した配信先)
- i18n plugin (FR-6.4 (b) 採用時) または二重 mirror 維持 ((a) 採用時)
- ~150 .md の mass edit (~500 link)
- 既存 `link-check.yml` の mkdocs path 対応
- proposal phase: `docs/proposals/mkdocs-deployment-strategy.md`

**Out of scope**:

- T-023 (test aggregation) との dashboard 統合 — FR-6.6 (a) 採用時のみ別 PR で接続
- Sphinx / Rustdoc / TypeDoc 等 API doc 自動生成連携 (DEP-6.2、 別 PR)
- HF Space (`python-inference`) の docs 同梱 (HF Space は app 用途)
- custom domain 取得・DNS 設定 (FR-6.5 (b)(c) 採用時、 user の運用作業)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | `mkdocs build --strict` | 通常 nav | exit 0 |
| UT-2 | `mkdocs build --strict` | 故意に壊した nav-relative link | exit 1 (link resolve fail) |
| UT-3 | `link-check.yml` | mkdocs build 後の site/ | 全 ~500 link 解決 |
| UT-4 | i18n plugin (FR-6.4 (b) 時) | `i18n: ja` metadata 欠落 | fallback で en を返す |
| UT-5 | `audit_inbound_links.py` | GitHub raw URL list | 全 URL が canonical 互換維持 (AC-6.2) |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | PR で `docs/**` を変更 | `docs-deploy.yml` が trigger、 staging deploy (preview) で動作 |
| E2E-2 | 内蔵検索 | `q=ssml` / `q=phoneme-timing` / `q=MB-iSTFT` で関連 doc 上位 3 件 |
| E2E-3 | inbound link 維持 | 既存 `https://github.com/ayutaz/piper-plus/blob/dev/docs/migration/v1.11-to-v1.12.md` が 200 OK |
| E2E-4 | mobile responsive | mkdocs-material default theme の mobile breakpoint 確認 |

### 4.4 リグレッション確認

- [ ] 既存 `pre-commit run --all-files` が 30 秒以内 (NFR-1.2)、 mkdocs build は pre-commit に組み込まない
- [ ] 既存 `deploy-webassembly-demo.yml` の `/wasm-demo/` path が `docs-deploy.yml` で上書きされない
- [ ] mkdocs build 時の `--strict` 失敗が CI で fail-fast (silent 続行禁止)
- [ ] silent-zero 防御: `Collected pages (N): ...` が stderr に出力

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | user 判断 4 件が長期化、 M4 全体が stall (M4-R2 と対) | proposal phase で各選択肢の長短 / 採用事例 / cost を提示、 30 日内 decision 目標 | proposal review |
| C-2 | mass edit ~500 箇所で link 死亡 (R-3 = 要求定義 §7) | GitHub raw URL を canonical 互換維持 (AC-6.2)、 `audit_inbound_links.py` で merge 前検証 | E2E-3 |
| C-3 | `mkdocs build --strict` が通らないままで CI 通過 | `--strict` フラグ必須、 broken link を fail-fast | UT-2 |
| C-4 | i18n 移行で既存 `README-ja.md` が orphan 化 | (a) 採用なら維持、 (b) 採用なら明示移行 + redirect | proposal phase で判断 |
| C-5 | mkdocs-material plugin の version drift (insiders 版 vs OSS 版) | OSS 版固定、 insiders 機能不使用 | `requirements-docs.txt` pin |
| C-6 | Pages bandwidth 100GB/月 制約 (FR-6.5 (a) 時) | trend 監視、 超過時 Cloudflare 移行 | GitHub Pages dashboard |
| C-7 | FR-6.6 dashboard 統合採用 → T-023 完了が前提となり M4 stall | proposal phase で (b) 分離を 推奨候補として user に提示 | proposal phase で判断 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] proposal phase document (`mkdocs-deployment-strategy.md`) が user 判断 4 件 + 既存事例 + cost を網羅
- [ ] `mkdocs.yml` nav 階層が「初学者動線 (install → quickstart → API)」 を満たす
- [ ] `mkdocs build --strict` が CI fail-fast (silent pass 禁止)
- [ ] 既存 GitHub raw URL inbound link が canonical 互換維持 (AC-6.2)
- [ ] `link-check.yml` が mkdocs build 後の path で全 ~500 link 解決 (AC-6.3)
- [ ] action SHA pin `@v<X.Y.Z>` または 40-hex (sliding `@v<major>` 禁止)
- [ ] `permissions:` が least privilege (default `contents: read`、 deploy 時のみ `pages: write` / `id-token: write`)
- [ ] paths filter (`docs/**` / `mkdocs.yml`) が誤検出しない
- [ ] silent-zero pattern を踏んでいない (`Collected pages: 0` が success にならない)
- [ ] FR-6.6 採用時、 T-023 への依存が明示され circular 化していない
- [ ] markdownlint / ruff / codespell 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠

---

## 6. 一から作り直すとしたら

> M4 milestone §4 で議論済みの代替案 3 件を ticket level で再掲。 次世代版 (v2 docs infra) 設計時に再評価する余地を残す。

### 案 A: mkdocs ではなく Docusaurus / Astro / Hugo を採用

- **概要**: SSG (Static Site Generator) を mkdocs-material から React-based (Docusaurus) / multi-framework (Astro) / Go-based (Hugo) に変更
- **長所**:
  - **Docusaurus**: versioning 標準サポート (v1.11 / v1.12 docs を併存可能、 piper-plus の release cadence と整合)、 i18n が plugin 不要 (FR-6.4 二択を回避)、 React component で「合成試聴 player」 等 interactive doc が可能
  - **Astro**: build 高速、 部分 hydration で performance 良好
  - **Hugo**: build 極めて高速 (~1秒)、 plugin 不要設計
- **短所**:
  - **Docusaurus**: Python community との culture mismatch、 Node.js toolchain 必須、 既存 link 移行 cost が mkdocs より高い
  - **Astro / Hugo**: i18n / search plugin が成熟度低、 markdown 拡張記法が独自
- **採否**: 現時点では採用しない (FR-6.1 で mkdocs-material 固定)。 v2 設計時、 特に「versioning 標準サポート」 が必要になった段階で **Docusaurus を再評価**。

### 案 B: dashboard 統合 vs 分離

- **概要**: T-022 (mkdocs docs) と T-023 (test aggregation) を **同一 dashboard で配信** する vs 完全分離する
- **長所 (分離)**:
  - T-022 / T-023 の依存が完全に解け、 T-023 が M1 sticky 完了直後に並行着手可能
  - mkdocs plugin 拡張 (test result 表示 plugin の自作) が不要
  - sticky comment / Issue は GitHub native で merge readiness 判定が PR 上で完結
- **短所 (分離)**:
  - 「release readiness signal」 を見る場所が分散 (PR sticky vs mkdocs)
  - 過去 release の test 結果 trend が PR 上の sticky では追えない
  - マーケティング目的 (project 健全性を外部に見せる) の dashboard 価値が下がる
- **採否**: proposal phase で **FR-6.6 として user 判断**。 v1 デフォルト推奨は **分離** (依存解消 + 並行着手可能)。

### 案 C: i18n を二重 mirror で維持 (mkdocs-static-i18n 不採用)

- **概要**: FR-6.4 (a) を採用、 既存 `README.md` / `README-ja.md` 体制を `docs/en/*` / `docs/ja/*` に拡張
- **長所**: 既存 workflow / contributor の慣れと整合、 学習 cost ゼロ、 fallback ロジック不要
- **短所**: maintain 2x、 翻訳遅延で content drift、 nav 階層を 2 重定義
- **採否**: 短期は (a) 採用候補 (cost 低)、 中期で content drift が顕在化したら (b) `mkdocs-static-i18n` に移行。 proposal phase で user 判断。

### 結論

現時点 (proposal phase) では **mkdocs-material 維持 + 分離 + i18n は user 判断** を推奨候補とする。 v2 (M4 retrospective 後) で「versioning が必要 / マーケティング dashboard が必要」 と判明したら、 Docusaurus + 統合に再評価。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-023 (test aggregation) との dashboard 統合 (FR-6.6 (a) 採用時のみ別 PR で接続)
- **連携 milestone**: M4 retrospective (mkdocs ↔ test dashboard 統合の採否再評価)
- **依存解消**: 本チケット完了で release notes に mkdocs URL 追加が可能になる

### 7.2 引き継ぎ事項 (Handoff)

> 本チケットで判明した「次の人が知らないとハマる」 情報。

- **mass edit ~500 箇所の手順**: `scripts/migrate_md_links.py` (option) で 一括変換、 ただし `[[ ]]` inline phoneme 記法と衝突するので除外 regex 必須
- **`mkdocs build --strict` は CI で必須**: strict mode 無しだと broken link が silent 通過、 PR #511 phase 2 の silent-zero 同型バグになる
- **GitHub raw URL canonical 維持**: 既存 issue / blog の inbound link は **削除しない**、 mkdocs 配信は重複 URL として共存 (AC-6.2)
- **i18n plugin 採用時の metadata**: `mkdocs-static-i18n` は frontmatter に `i18n: { language: ja }` を全 .md に追記する必要、 mass edit script で一括対応
- **配信先選定の DNS**: FR-6.5 (b)(c) 採用時、 user が DNS / Cloudflare / Netlify account を所有していること
- **release notes 更新**: 完了後、 各 release notes template に「Documentation」 セクションを追加 (mkdocs URL を明示)

### 7.3 未解決の質問

- [ ] FR-6.3 公開範囲 (`docs/proposals/` / `docs/spec/` を公開するか)
- [ ] FR-6.4 i18n 戦略 (二重 mirror vs `mkdocs-static-i18n`)
- [ ] FR-6.5 配信先 (GitHub Pages / Cloudflare / Netlify / HF Spaces)
- [ ] **FR-6.6 dashboard 統合 yes/no** (T-023 の test aggregation を mkdocs に取り込むか) — M4 milestone §4 で議論

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.6 (FR-6.1〜FR-6.6 / AC-6.1〜AC-6.3 / CON-6.1〜CON-6.2 / DEP-6.1〜DEP-6.2)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.5
- Milestone: [`M4 Docs Infra`](../milestones/M4-docs-infra.md) §3 (AC) / §4 (Phase rethink)
- 関連 workflow: `.github/workflows/deploy-webassembly-demo.yml`, `.github/workflows/deploy-huggingface.yml`, `.github/workflows/link-check.yml`
- 後続 ticket: [T-023](T-023-test-aggregation.md) (FR-6.6 dashboard 統合採用時)
- proposal 起草先 (新規): `docs/proposals/mkdocs-deployment-strategy.md`
- 親 index: [`../README.md`](../README.md)

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 (proposal phase 着手前 ticket) — FR-6.3/6.4/6.5 + 追加 FR-6.6 dashboard 統合の 4 件 user 判断項目、 mass edit ~500 link 計画、 既存 deploy / link-check workflow との namespace 衝突回避、 Docusaurus / 分離 / 二重 mirror の 3 代替案を記録 | Claude Code |
