# [M1.2] Migration guide lint

**親マイルストーン**: [M1 Defensive Foundations](./M1-overview.md)
**親調査**: [ci-expansion-2026-05.md §Top 10 #3](../proposals/ci-expansion-2026-05.md#5-真に追加する価値があるトップ-10)
**Top 10 内番号**: #3
**ステータス**: 着手中 (PR draft)
**想定工数**: 1 PR (~6h)
**優先度**: 高
**作成日**: 2026-05-18

---

## 1. タスクの目的とゴール

- **目的**: `CHANGELOG.md` の `[Unreleased] > Breaking` 節と `docs/migration/v*.md` の cross-ref を構造的に強制する。 v1.11 → v1.12 で発生した「migration doc が後追いで作成される」問題を再発させない。
- **ゴール (Definition of Done)**:
  - [ ] 新規 workflow `migration-guide-lint.yml` (または既存 `migration-changelog-parity.yml` 拡張) が PR で `[Unreleased] > Breaking` entry を検出
  - [ ] 検出時、 対応する `docs/migration/v<X>-to-v<Y>.md` の存在と `[Unreleased] > Breaking` から該当 migration anchor へのリンク存在を assert
  - [ ] keep-a-changelog parser `scripts/check_migration_xref.py` (新規) が CHANGELOG を AST 化し、 missing anchor / 404 link を fail として報告
  - [ ] PR label `breaking` 付き or `[Unreleased] > Breaking` 節に entry がある場合のみ enforce、 patch / minor PR は skip
  - [ ] pre-commit hook (`migration-guide-lint`) として CI 前にローカルで検出可能

---

## 2. 実装する内容の詳細

### 背景

v1.12.0 で `Generator` 削除 + `phonemize()` 戻り値型変更という 2 件の breaking change を導入したが、 `docs/migration/v1.11-to-v1.12.md` は **breaking commit より後に作成** された。 親調査 §4 「breaking change の真のコスト」で指摘されている通り、 これは CI で防げる drift で、 「CHANGELOG breaking 記述 ↔ migration doc」の双方向リンクを強制すれば構造的に塞げる。

既存の `migration-changelog-parity.yml` は CHANGELOG と migration doc の **存在対応** のみチェックしており、 内容の **anchor link cross-ref** は未検査。 本 ticket でこの穴を埋める。

### アーキテクチャ概要

keep-a-changelog 準拠の AST parser を `scripts/check_migration_xref.py` に実装し、 以下 3 段階で検証する。

```mermaid
flowchart TD
    A[PR diff includes CHANGELOG.md] --> B{Has [Unreleased] > Breaking entries?}
    B -- No --> C[Skip - PASS]
    B -- Yes --> D[Parse CHANGELOG to AST]
    D --> E[Extract anchor links in Breaking entries]
    E --> F{All anchors resolve<br/>to docs/migration/v*.md?}
    F -- No --> G[FAIL: list missing anchors]
    F -- Yes --> H{Migration doc has<br/>matching anchor heading?}
    H -- No --> I[FAIL: doc missing heading]
    H -- Yes --> J[PASS]
```

### 具体的な変更内容

- 新規: `scripts/check_migration_xref.py`
  - keep-a-changelog parser (regex ベースで `## [version] - YYYY-MM-DD` / `### Breaking` 階層を読む、 既存 `scripts/check_changelog_unreleased.py` を継承)
  - 各 breaking entry から markdown link `[text](docs/migration/v<X>-to-v<Y>.md#anchor)` を抽出
  - 該当 file の存在チェック + heading anchor (`## anchor-name` を kebab-case 化) のチェック
  - exit 0 / 1 + 人間可読 diagnostic
- 改修 or 新規: `.github/workflows/migration-guide-lint.yml`
  - 既存 `migration-changelog-parity.yml` を拡張する選択肢もあるが、 責務分離のため **新規 workflow を推奨**
  - trigger: `pull_request` for `paths: [CHANGELOG.md, docs/migration/**]`
  - condition: `contains(github.event.pull_request.labels.*.name, 'breaking')` または CHANGELOG diff に `### Breaking` 追加検出
- 改修: `.pre-commit-config.yaml`
  - hook `migration-guide-lint` を追加 (local hook、 Python script を呼ぶ)
  - stage: `commit` (CHANGELOG または `docs/migration/` 変更時のみ)
- 改修: `CHANGELOG.md` の `[Unreleased]` template
  - `### Breaking` entry 記入時の link 規約をコメントで明示
  - 例: `- foo bar が削除されました ([移行ガイド](docs/migration/v1.12-to-v1.13.md#foo-bar-removal))`
- 新規: `tests/scripts/test_check_migration_xref.py`
  - 6-8 シナリオの pytest
- 改修: `docs/migration/README.md` (存在しなければ新規)
  - migration doc の規約 (heading anchor 命名規則、 `## v<X>-to-v<Y>` セクション必須 等) を明文化

### 設定 / API 例

`scripts/check_migration_xref.py` の擬似コード:

```python
import re
import pathlib
import sys

ANCHOR_LINK_RE = re.compile(r"\[([^\]]+)\]\((docs/migration/v[\d\.]+-to-v[\d\.]+\.md)(#[a-z0-9-]+)?\)")

def parse_changelog(path: pathlib.Path) -> dict:
    """keep-a-changelog AST を構築。 returns {version: {section: [entries]}}"""
    # 既存 scripts/check_changelog_unreleased.py から共通化
    ...

def slugify(heading: str) -> str:
    """GitHub markdown anchor slug 規約 (kebab-case, ascii alpha+num+hyphen)"""
    s = heading.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s_]+", "-", s).strip("-")

def main() -> int:
    changelog = parse_changelog(pathlib.Path("CHANGELOG.md"))
    breaking_entries = changelog.get("Unreleased", {}).get("Breaking", [])

    if not breaking_entries:
        print("No [Unreleased] > Breaking entries; skip.")
        return 0

    errors = []
    for entry in breaking_entries:
        links = ANCHOR_LINK_RE.findall(entry["raw"])
        if not links:
            errors.append(f"Breaking entry missing migration link: {entry['raw'][:80]}")
            continue
        for _text, doc_path, anchor in links:
            p = pathlib.Path(doc_path)
            if not p.exists():
                errors.append(f"Migration doc not found: {doc_path}")
                continue
            if anchor:
                headings = {slugify(h) for h in extract_headings(p)}
                if anchor.lstrip("#") not in headings:
                    errors.append(f"Anchor not found in {doc_path}: {anchor}")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

`.github/workflows/migration-guide-lint.yml`:

```yaml
name: Migration Guide Lint
on:
  pull_request:
    paths:
      - CHANGELOG.md
      - docs/migration/**

permissions:
  contents: read
  pull-requests: read

jobs:
  lint:
    runs-on: ubuntu-22.04
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@<pinned-sha>
      - uses: astral-sh/setup-uv@<pinned-sha>
      - name: Check migration cross-ref
        run: |
          uv run python scripts/check_migration_xref.py
```

---

## 3. エージェントチームの役割と人数

| ロール | 人数 | 担当範囲 |
|--------|------|---------|
| Python script author | 1 | `scripts/check_migration_xref.py` 実装、 既存 `check_changelog_unreleased.py` の AST 部を共通化、 pytest 6-8 ケース |
| GitHub Actions author | 1 | `migration-guide-lint.yml` workflow 設計、 `paths` filter と label conditional の組合せ、 既存 `migration-changelog-parity.yml` との分担明確化 |
| Docs writer | 1 | `docs/migration/README.md` 規約整備、 `CHANGELOG.md` の `[Unreleased]` template にコメント追記、 CONTRIBUTING.md へ一文追加 |
| Reviewer | 1 | 既存 migration doc (v1.11-to-v1.12.md) を script でテストし retroactive な fail / pass を確認、 false positive を観測 |

合計 4 名規模。

---

## 4. 提供範囲とテスト項目

### 提供範囲 (Scope)

**IN-SCOPE**:

- CHANGELOG.md `[Unreleased] > Breaking` 節のリンク強制
- `docs/migration/v<X>-to-v<Y>.md` 存在 + heading anchor 一致
- pre-commit hook + CI workflow の二重化
- 既存 v1.11-to-v1.12.md に retroactive 適用 (drift 検出のテスト)

**OUT-OF-SCOPE**:

- リリース済み version (v1.12.0 等) の遡及修正 (現状 release notes は HF Hub / GitHub Releases に手動で書いているため、 retroactive 修正は別 task)
- 8 言語翻訳された migration doc の同期検査 (i18n 軸、 親調査 §3.7 で別途扱う)
- CHANGELOG entry の意味的妥当性検査 (「これは本当に breaking か」は人間判断)
- non-Markdown ドキュメント (mkdocs / RST 等) への拡張 (piper-plus は Markdown 統一)

### Unit テスト (シナリオレベル)

- **fixture 1: 完全形 (PASS)**: CHANGELOG に `### Breaking` + link `[移行ガイド](docs/migration/v1.12-to-v1.13.md#foo-removal)`、 migration doc に `## foo-removal` heading → exit 0
- **fixture 2: link 欠落 (FAIL)**: `### Breaking` entry が plain text のみ → exit 1、 "missing migration link"
- **fixture 3: file 不存在 (FAIL)**: link 先 `docs/migration/v9.9-to-v10.0.md` が存在しない → exit 1、 "Migration doc not found"
- **fixture 4: anchor mismatch (FAIL)**: link `#foo-removal` だが doc に `## bar-removal` のみ → exit 1、 "Anchor not found"
- **fixture 5: anchor なし (PASS, lenient)**: link が `docs/migration/v1.12-to-v1.13.md` のみで anchor なし → exit 0 (anchor 省略は許可、 一般的な migration overview link として正当)
- **fixture 6: [Unreleased] に Breaking なし (PASS)**: `### Added` のみ → exit 0 (skip)
- **fixture 7: 既存 v1.11-to-v1.12.md retroactive (regression test)**: 実 CHANGELOG を入力にして fail/pass のどちらが返るかを記録、 期待値を retroactive に追加してテスト
- **fixture 8: kebab-case 異体字 (PASS)**: heading に全角数字 / 日本語が混じる場合の slug 化挙動を pinning

fixture path: `tests/scripts/fixtures/migration_xref/{changelog_*.md, doc_*.md}` (組み合わせで 8 シナリオ)

### E2E / 統合テスト

- **実 PR シナリオ A**: `CHANGELOG.md` に `### Breaking` + 正しい link を追加した PR → workflow PASS
- **実 PR シナリオ B**: `### Breaking` を追加したが link を忘れた PR → workflow FAIL、 PR check に diagnostic 表示
- **実 PR シナリオ C**: docs 変更のみ (CHANGELOG なし) PR → paths filter で skip、 余計に走らない
- **実 PR シナリオ D**: `breaking` label を後付けで付与した PR → re-run でラベル condition が再評価される

### 手動検証項目

- 既存 `docs/migration/v1.11-to-v1.12.md` を入力にした場合、 retroactive に PASS/FAIL のどちらが期待値か確認 (既存 CHANGELOG にリンクが書かれていない場合は **FAIL を期待値として fixture 化** し、 修正 PR を別途切る)
- `pre-commit run migration-guide-lint --all-files` でローカル実行確認
- `breaking` label の付与/除去で PR 上の check が再評価されるか確認 (GitHub の挙動上は label change で workflow が re-trigger される)

---

## 5. 懸念事項とレビュー観点

### 懸念事項 (Risks)

1. **breaking change の粒度が一律でない**: 「内部実装の breaking」と「user-facing breaking」が CHANGELOG で混在する可能性。 → `### Breaking` 節は user-facing 限定とし、 内部実装変更は `### Changed` に分類するルールを `docs/migration/README.md` に明記。
2. **anchor slug 規約の不安定性**: GitHub Markdown の slug 化は仕様文書化されていない部分があり、 emoji / 全角 / 連続ハイフン等で差異が出る。 → `slugify()` は GitHub 互換を目指すが、 fixture テストで pinning し drift が出たら slug を手動指定する逃げ道を用意。
3. **false positive: 過剰 friction**: 全 PR で breaking 検査を走らせると軽微な内部変更でも fail する可能性。 → `breaking` label or CHANGELOG diff の `### Breaking` 追加検出のみで enforce、 patch PR は skip。
4. **migration doc の heading 命名規則と既存 doc の drift**: 既存 v1.11-to-v1.12.md が新規規約に合わない場合、 retroactive 修正が必要。 → 規約は緩く設定し、 既存 doc は別 PR で順次対応 (本 PR の scope 外)。
5. **CHANGELOG parser の脆さ**: 既存 `check_changelog_unreleased.py` の regex parser を流用するが、 keep-a-changelog 仕様外の書式 (絵文字 / 表組み 等) で誤動作する可能性。 → AST 化を欲張らず、 「`### Breaking` 行直下 ~50 行」を簡素に走査する保守的 parser に留める。

### レビュー観点 (Review checklist)

- [ ] `scripts/check_migration_xref.py` が既存 `check_changelog_unreleased.py` と AST 共通化されており、 二重実装になっていない
- [ ] `### Breaking` 検出は CHANGELOG diff 増分のみで動作し、 既存 `### Breaking` 節に手を加えない PR では skip される (false positive 防止)
- [ ] `breaking` label と CHANGELOG diff の OR 条件が workflow conditional で正しく組まれている
- [ ] anchor slug 化が GitHub 互換、 fixture pinning が網羅的
- [ ] `docs/migration/README.md` に migration doc 命名規則 (`v<X>-to-v<Y>.md`) と heading 規約が明記
- [ ] `CHANGELOG.md` の `[Unreleased]` template にコメントで link 規約を追記
- [ ] pre-commit hook が CHANGELOG / docs/migration 変更時のみ走る (`files: ^(CHANGELOG\.md|docs/migration/)`)
- [ ]既存 migration doc (v1.11-to-v1.12.md) に対する retroactive 結果を明示
- [ ] PR body は pull_request_template の section 構造 (Test Plan 大文字、 Risk Level 1 つ)
- [ ] PR title に M1 等のマイルストーン番号を含めない
- [ ] GitHub Actions は SHA pin
- [ ] backward compat: 既存 PR の `CHANGELOG.md` 編集を破壊しない

---

## 6. 一から作り直すとしたら (Reinvention thought experiment)

ゼロから設計するなら、 そもそも **CHANGELOG の手書き運用を廃止**し、 conventional commits → release-please / changesets で CHANGELOG を auto-generate する pipeline が理想。 breaking change は commit footer `BREAKING CHANGE:` で機械的に拾え、 migration doc は PR template の checkbox + GitHub Issue forms で必須化できる。 これなら「`### Breaking` 節が書かれていない breaking」を作る余地がそもそも存在しない。

採用しなかった代案:

- **release-please 全面導入**: piper-plus は 7 ランタイム × 複数 publish target (PyPI/npm/crates/NuGet/Maven/HF) で release 戦略が複雑、 release-please 単独で全 target を管理するのは現状非現実的。 段階移行が必要だが scope 過大。
- **changesets (Atlassian)**: monorepo 想定の tool で piper-plus の構造 (Cargo workspace + Python flat + Go module + C# solution + npm) と相性が悪い。 不採用。
- **GitHub Issue forms + bot による migration doc 自動生成**: doc を bot に書かせると低品質になりがち、 例文 + frontmatter テンプレ手書きが現実的。
- **branch protection で `docs/migration/` 変更を CODEOWNERS で必須 review**: file 変更を要求するのは強いが、 「breaking が CHANGELOG にあるのに docs/migration/ 変更がない」cross-ref は protection rule で表現不能。 やはり CI lint が現実解。

別 layer での実装も検討した: GitHub Apps で merge command を gating する案 (e.g. `/migration-docs-ok` で maintainer override) も考えたが、 lint workflow に bypass label (`skip-migration-lint`) を 1 つ用意すれば十分で、 GitHub Apps 化は overengineering。

**結論**: 6h 規模で得られる ROI を考えると、 既存 keep-a-changelog parser を継承した軽量 lint script + 1 workflow + pre-commit hook の組合せが最も合理的。 release-please 全面導入は M-Stretch (Month 4+) に候補として残す。

---

## 7. 後続タスクへの連絡事項 (Handoff)

- **M1.3 への連絡**: first-PR fast lane では本 lint も警告に降格対象とするか? → **対象とする**。 初回 contributor は migration doc の規約を知らないため、 warning に留め、 maintainer が `/run-full-gate` label で blocker 化する。 M1.3 で `migration-guide-lint.yml` の conditional に `author_association` 判定を組込む。
- **M2 / M3 への連絡**: M2 (audio MOS proxy) / M3.1 (Public ABI snapshot) は breaking change を伴う可能性が高い。 これら作業時には `### Breaking` + `docs/migration/v*.md` の cross-ref を必ず書く運用を `docs/migration/README.md` で徹底。
- **既存 v1.11-to-v1.12.md への retroactive 適用**: 本 PR の script で fail する場合、 別 PR で `docs/migration/v1.11-to-v1.12.md` の heading 構造を新規約に合わせる修正を行う (Issue 化、 本 PR の scope 外)。
- **release-please 移行調査** Issue: M-Stretch 候補として登録、 7 ランタイム release 戦略と整合する形を Month 4+ で検討。
- **net flat policy 宿題**: 本 PR で 1 workflow + 1 script + 1 docs file 追加。 削除候補として既存 `migration-changelog-parity.yml` を **本 PR で吸収統合** することも検討 (責務分離の観点で別 workflow のままにする方が望ましいので、 単なる削除でなく統合可否を検討する Issue を起票)。

---

## 8. 関連ファイル

### 既存ファイル (改修対象)

- `CHANGELOG.md` (template コメント追記、 既存 entry の retroactive 修正は別 PR)
- `.github/workflows/migration-changelog-parity.yml` (本 PR では触らない、 統合可否は別 Issue)
- `.pre-commit-config.yaml` (local hook 追加)
- `scripts/check_changelog_unreleased.py` (AST 部の共通化対象)
- `docs/migration/v1.11-to-v1.12.md` (retroactive テスト対象、 必要なら別 PR で修正)
- `CONTRIBUTING.md` (一文追記、 M1.3 で詳細化)

### 新規作成ファイル

- `.github/workflows/migration-guide-lint.yml`
- `scripts/check_migration_xref.py`
- `tests/scripts/test_check_migration_xref.py`
- `tests/scripts/fixtures/migration_xref/changelog_pass.md`
- `tests/scripts/fixtures/migration_xref/changelog_missing_link.md`
- `tests/scripts/fixtures/migration_xref/changelog_no_breaking.md`
- `tests/scripts/fixtures/migration_xref/doc_pass.md`
- `tests/scripts/fixtures/migration_xref/doc_missing_anchor.md`
- `docs/migration/README.md` (規約整備)

### 仕様 toml / docs

- 専用 spec.toml は不要 (lint logic が小規模、 toml 化のコストが上回る)
- `docs/migration/README.md` を canonical reference として運用

---

## 9. 参照

- [親マイルストーン §M1.2](../proposals/ci-expansion-milestones.md#m12--migration-guide-lint-top-10-3)
- [親調査 §Top 10 #3](../proposals/ci-expansion-2026-05.md#5-真に追加する価値があるトップ-10)
- [親調査 §3.7 Docs / i18n / CHANGELOG](../proposals/ci-expansion-2026-05.md#37-docs--i18n--changelog)
- [親調査 §4 "breaking change の真のコスト"](../proposals/ci-expansion-2026-05.md#4-批判的観点--なぜ追加しないが-default-か)
- [docs/migration/v1.11-to-v1.12.md](../migration/v1.11-to-v1.12.md) — breaking change の参考事例
- [keep-a-changelog 1.1.0 仕様](https://keepachangelog.com/en/1.1.0/)
- 関連 PR / Issue: v1.12.0 リリース系 PR (`PR #507` 等)
