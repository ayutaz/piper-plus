# TICKET-07: Docs / CHANGELOG / Release

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-07 |
| **マイルストーン** | Phase 7 (Day 15) ※ Day 16 は統合バッファ (cross-runtime PR review / 最終回帰) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §8.11 (リリース戦略) / §8.19 (API doc 統一) / §8.21 (データセット拡張運用) |
| **ステータス** | 📝 Draft |
| **依存元** | TICKET-01〜06 (全実装完了が前提) |
| **依存先** | なし |
| **追加 LOC** | ~300 (CHANGELOG / README / API doc / migration guide) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: 5 ランタイム + Python の README / CHANGELOG / API doc を統一書式で更新し、minor bump 一斉リリースを準備。利用者が「どのバージョンから使えるか」「どう使うか」「どう opt-out するか」を 1 ページで把握できる状態にする。

**ゴール**:
- 6 CHANGELOG (root + python-g2p + Rust workspace + C# csproj + npm + Go module) に "Added: ZH-EN code-switching" 一行を追加。
- 各ランタイム README に統一テンプレートで ZH-EN 例 (Issue 例 3 件) を追加。
- API doc を設計書 §8.19 のテンプレートに従って rustdoc / XML doc / JSDoc / docstring / godoc / doxygen で生成。
- Migration guide (`docs/migration/v1.13-zh-en.md`) で「opt-out 方法」「behavior 変更点」を明記。
- リリース手順 (cargo / npm / pip / nuget / git tag) のチェックリストを README に明記。
- `tools/gen_zh_en_fixture.py` を導入、fixture 自動再生成可能化。
- 共通用語集 (loanword / acronym / letter_fallback / zh_en_dispatch) を `docs/spec/` に固定化。

---

## 2. 実装する内容の詳細

### D1. CHANGELOG 更新 (6 箇所)

各 CHANGELOG の `[Unreleased]` セクションに以下を追加 (運用は §8.11 リリース戦略に従う):

```markdown
### Added
- ZH-EN code-switching: English words in Chinese context are now phonemized as Mandarin pinyin
  (e.g., `请打开 GPS` → "GPS" pronounced as `ji4-pi4-ai1-si4`). Default-on, opt-out via
  `enable_zh_en_dispatch=false`. Issue #384, PR #397 (Python) + this PR (5 runtimes).

### Internal
- Added `zh_en_loanword.json` (acronyms 65 + loanwords 40 + letter_fallback 26) shared
  across 7 source-of-truth copies, validated by `.github/workflows/zh-en-loanword-sync.yml`.
- Cross-runtime test fixture: `tests/fixtures/g2p/zh_en_loanword_matrix.json`.
```

**対象 CHANGELOG**:

| パッケージ | 場所 | bump |
|-----------|-----|------|
| Root (リポジトリ全体) | `CHANGELOG.md` | unreleased → 0.5.0 |
| `piper-plus-g2p` (Python) | `src/python/g2p/CHANGELOG.md` | 0.2.0 → 0.3.0 |
| `piper-plus-g2p` / `piper-core` / `piper-cli` (Rust) | `src/rust/Cargo.toml` workspace + 各 crate CHANGELOG | 0.4.0 → 0.5.0 |
| `PiperPlus.Core` / `PiperPlus.Cli` (C#) | `*.csproj` Version + `<PackageReleaseNotes>` | 0.3.0 → 0.4.0 |
| `@piper-plus/g2p` (npm) | `src/wasm/g2p/package.json` + `CHANGELOG.md` | 0.4.0 → 0.5.0 |
| Go module / C API | `git tag v1.13.0` (リポジトリレベル) | latest → v1.13.0 |

### D2. 各ランタイム README に ZH-EN 例追加 (統一テンプレート)

設計書 §8.19 の用語統一を反映、共通テンプレート:

```markdown
## ZH-EN Code-Switching (English in Chinese context)

When an English token (acronym, brand, technical term) appears next to a Chinese
segment, the multilingual phonemizer routes it through pinyin-based pronunciation
instead of US English. This matches how Chinese speakers naturally pronounce
inserted English words.

### Examples

| Input | Output explanation |
|-------|-------------------|
| `请打开 GPS` | "GPS" pronounced as `ji4-pi4-ai1-si4` (Mandarin pinyin) |
| `我喜欢用 Python 写代码` | "Python" → `pai4-sen1` (case-sensitive loanword) |
| `让我用 ChatGPT 写代码` | "ChatGPT" → 5 syllables (loanword 辞書) |
| `Hello world` | No zh context → standard g2p-en (unchanged) |

### Lookup priority

1. **case-sensitive `loanwords`** (e.g., `Python`, `iPhone`)
2. **`acronyms`** (uppercase fold, e.g., `GPS`, `HTTP`)
3. **`letter_fallback`** (A-Z, char-by-char; digits dropped)

### Opt-out

[Runtime-specific opt-out code example]
```

**ランタイム別 opt-out 例**:

| Runtime | 例 |
|--------|-----|
| Python | `MultilingualPhonemizer(enable_zh_en_dispatch=False)` |
| Rust | `MultilingualPhonemizer::builder().enable_zh_en_dispatch(false).build()` |
| Go | `phonemize.NewChinesePhonemizer(sc, ph, phonemize.WithZhEnDispatch(false))` |
| C# | `new MultilingualPhonemizerOptions { ZhEnDispatch = false }` |
| JS | `await G2P.create({ zhEnDispatch: false })` |
| C++ | `phonemizeChineseMixed(..., /* enable_zh_en_dispatch= */ false)` |
| C API | `piper_plus_set_zh_en_dispatch(handle, 0)` |

### D3. API doc generation (各ランタイム慣例)

設計書 §8.19 のテンプレート踏襲:

| Runtime | 形式 | 生成コマンド | 場所 |
|--------|-----|-------------|------|
| Rust | rustdoc `///` | `cargo doc --no-deps` | `src/rust/*/src/*.rs` |
| C# | XML doc `<summary>` | `dotnet build /p:GenerateDocumentationFile=true` | `src/csharp/*/Phonemize/*.cs` |
| TypeScript | JSDoc + `.d.ts` | `tsc --declaration` | `src/wasm/g2p/types/index.d.ts` |
| Python | Google docstring | `sphinx-build docs/ _build/` | `src/python_run/piper/phonemize/chinese.py` |
| Go | godoc (組込) | `go doc github.com/...` | `src/go/phonemize/chinese_loanword.go` |
| C++ | doxygen | `doxygen Doxyfile` | `src/cpp/chinese_loanword.hpp` (本 PR で **doxygen を新規セットアップ**) |

各 docstring に以下を含める (設計書 §8.19 共通要件):
1. 概要 (1-2 文)
2. パラメータの型 + 意味
3. 戻り値
4. エッジケース (kana 干渉、opt-out)
5. コード例
6. クロスリファレンス

### D4. Migration guide (`docs/migration/v1.13-zh-en.md`)

```markdown
# v1.13 ZH-EN Code-Switching Migration Guide

## What's new

When using the multilingual phonemizer with both Chinese and English languages,
embedded English tokens (e.g., "GPS", "Python") are now pronounced as Mandarin
pinyin instead of US English by default.

## Breaking changes

**None.** This is a non-breaking minor bump:
- Pure Chinese / pure English texts are unaffected (regression-tested).
- Multilingual texts that previously worked still work; output for embedded English
  in Chinese context now follows the new pinyin-based phonemization.

## Backward compatibility

If your downstream pipeline depends on the old US-English phonemization for embedded
English tokens, set `enable_zh_en_dispatch=false`:

[コード例 6 ランタイム]

## Customization

Override the default loanword dictionary with your own JSON:

```json
{
  "version": 1,
  "acronyms": { "MYORG": ["mai3", "owe1", "er1", "ji4"] },
  "loanwords": { "MyBrand": ["mai3", "blan1"] },
  "letter_fallback": { "A": ["ei1"], ... "Z": ["zai4"] }
}
```

[6 ランタイムの override API]

## Performance

- Net overhead: <5% on pure Chinese path (loanword lookup adds ~1μs/segment).
- Memory: +30 KB for default dictionary + +10 KB for parsed structures.
- WASM bundle: opt-in via `zh-en` feature flag, +12 KB compressed.

## Issue references

- Issue: [#384](https://github.com/ayutaz/piper-plus/issues/384)
- Python PR: [#397](https://github.com/ayutaz/piper-plus/pull/397)
- Multi-runtime PR: this PR
```

### D5. `tools/gen_zh_en_fixture.py` 新規 (TICKET-06 引き継ぎ)

```python
#!/usr/bin/env python3
"""Generate canonical ZH-EN test fixture from Python runtime.

Usage:
    python tools/gen_zh_en_fixture.py
    python tools/gen_zh_en_fixture.py --output tests/fixtures/g2p/zh_en_loanword_matrix.json

This regenerates the fixture by running the Python runtime on each test case.
Other runtimes (Rust/Go/C#/WASM/C++) compare their output against this fixture.
"""
import argparse
import json
from pathlib import Path
from piper_plus_g2p import get_phonemizer
from piper_plus_g2p.chinese import ChinesePhonemizer


CASES = [
    ("acronym_gps", "GPS"),
    ("loanword_python_case_sensitive", "Python"),
    ("loanword_chatgpt_5syllables", "ChatGPT"),
    ("letter_fallback_zz", "ZZ"),
    ("empty", ""),
    # ... 25 cases total
]

ISSUE_CASES = [
    ("issue_example_please_open_gps", "请打开 GPS"),
    ("issue_example_i_use_python", "我喜欢用 Python 写代码"),
    ("issue_example_let_me_use_chatgpt", "让我用 ChatGPT 写代码"),
]


def gen_fixture() -> dict:
    zh = ChinesePhonemizer()
    multi = get_phonemizer("zh-en")
    cases = []

    for name, input_text in CASES:
        tokens = zh.phonemize_embedded_english(input_text)
        cases.append({"name": name, "input": input_text, "expected": tokens})

    for name, input_text in ISSUE_CASES:
        tokens = multi.phonemize(input_text)
        cases.append({"name": name, "input": input_text, "expected": tokens})

    import piper_plus_g2p
    return {
        "schema_version": 1,
        "description": "Cross-runtime ZH-EN code-switching test matrix.",
        "metadata": {
            "source": "Python piper_plus_g2p",
            "py_runtime": "ChinesePhonemizer.phonemize_embedded_english",
            "py_runtime_version": piper_plus_g2p.__version__,
            "regen": "python tools/gen_zh_en_fixture.py",
            "regen_requirements": "piper_plus_g2p==0.3.0",
        },
        "cases": cases,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/g2p/zh_en_loanword_matrix.json"),
    )
    args = parser.parse_args()

    fx = gen_fixture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(fx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ wrote {len(fx['cases'])} cases to {args.output}")
```

### D6. 共通用語集の固定化 (`docs/spec/zh-en-loanword-glossary.md`)

設計書 §8.19 の用語表を独立ドキュメント化:

```markdown
# ZH-EN Code-Switching Glossary

Common terminology used across all 7 runtimes.

| Term | Definition |
|------|-----------|
| **embedded English** | English token appearing in Chinese context, phonemized via pinyin. |
| **loanword** | Entry in `loanwords` dict (case-sensitive, e.g., `Python`). |
| **acronym** | Entry in `acronyms` dict (uppercase fold, e.g., `GPS`). |
| **letter_fallback** | A-Z char-by-char fallback when no entry matches. |
| **zh_en_dispatch** | Behavior of `MultilingualPhonemizer` to route embedded EN through ZH path. |
| **kana 干渉 (kana interference)** | In `ja-en-zh` mode, presence of kana causes zh segments to be misclassified as ja. |
| **opt-out flag** | `enable_zh_en_dispatch=false` parameter to revert to old behavior. |
| **PUA tone marker** | U+E046-U+E04A range used for Mandarin tone numbers (1-5). |
| **source of truth** | `src/python/g2p/.../zh_en_loanword.json` is canonical; 6 mirrors are byte-equivalent. |
```

### D7. Release checklist を README に追加

`README.md` (root) または `RELEASING.md` (新規) に:

```markdown
## Releasing v1.13.0 (ZH-EN code-switching)

1. **CHANGELOG bump** (6 箇所、D1 参照)
2. **Cargo workspace** (`src/rust/Cargo.toml` workspace.package.version → 0.5.0)
3. **NPM** (`src/wasm/g2p/package.json` version → 0.5.0)
4. **NuGet** (`*.csproj` Version → 0.4.0)
5. **PyPI** (`pyproject.toml` version → 0.3.0)
6. **Cargo publish** (依存順): `piper-plus-g2p` → `piper-core` → `piper-cli`
7. **Git tag**: `git tag v1.13.0 && git push --tags`
   → Go module 自動公開、`release-shared-lib.yml` が iOS xcframework / Android .aar / GitHub Release を自動生成
8. **NPM publish**: Rust crates 完了後 `npm publish`
9. **PyPI publish**: `python -m build && twine upload dist/*`
10. **NuGet push**: `dotnet nuget push *.nupkg`
11. **Branch protection 追加** (TICKET-06 引き継ぎ):
    `gh api -X PUT repos/.../branches/dev/protection -F required_status_checks.contexts[]='ZH-EN Loanword Sync / json-sync'`
12. **GitHub Release notes** にこの migration guide リンク + Issue #384 を貼る
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | 全体統括、リリース順序の確認、版番号の整合 |
| **Tech Writer** | 1 | D1-D2-D4-D6 (CHANGELOG / README / migration guide / glossary) の執筆と統一書式チェック |
| **Python Dev** | 1 | D5 fixture generator 実装、テスト |
| **DevOps** | 1 | D7 リリース checklist 整備、actual release 実施 (cargo/npm/pip/nuget) |

**並列化**: D1 / D2 / D6 は並列、D4 (migration guide) は D2 完了後、D5 は独立、D7 は最後。

**コミット推奨**:
- `docs(changelog): ZH-EN code-switching を 6 changelog に追加 (D1)`
- `docs(readme): ZH-EN 統一例を 6 README に追加 (D2)`
- `docs(api): rustdoc / XML doc / JSDoc / docstring 統一 (D3)`
- `docs(migration): v1.13 ZH-EN migration guide 追加 (D4)`
- `tools: gen_zh_en_fixture.py 追加 (D5)`
- `docs(spec): zh-en-loanword-glossary.md 追加 (D6)`
- `docs(release): RELEASING.md チェックリスト追加 (D7)`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- 6 CHANGELOG 更新
- 6 README に ZH-EN 例
- 6 API doc 生成 (rustdoc / XML doc / JSDoc / sphinx / godoc / doxygen)
- Migration guide
- Fixture generator script
- Glossary
- Release checklist
- C++ doxygen 新規セットアップ (`Doxyfile` 雛形)

### Out of scope

- Performance benchmark CI (将来 PR、`g2p-phonemize-perf.yml` を別 PR で導入)
- 公式 release 実施 (本 PR は preparation のみ、merge 後に DevOps が手動実行)
- 他言語ペア (JA-EN / KO-EN) 用の docs (Phase 2 で実施)

### テスト項目

- `markdownlint` で 6 README + migration guide の lint pass
- `vale lint` で用語整合 (glossary 準拠) pass
- `changelog-lint` で 6 CHANGELOG format pass + `[Unreleased]` 日付一致
- `cargo doc --no-deps` warning ゼロ
- `dotnet build /p:GenerateDocumentationFile=true /p:TreatWarningsAsErrors=true` で XML doc 警告ゼロ
- `tsc --declaration` で `.d.ts` 生成成功
- `sphinx-build` で warning ゼロ
- `doxygen Doxyfile` で warning ゼロ (新規セットアップ)
- `python tools/gen_zh_en_fixture.py` 実行 → fixture と一致 (idempotent)
- `cargo test --doc` / `pytest --doctest-modules` / Go `Example_xxx` で doctest CI pass (Rust/Python/Go のみ)

---

## 5. Unit テスト

主に文書類なので unit テストは限定的。`tools/gen_zh_en_fixture.py` に対する pytest:

```python
# tests/test_gen_zh_en_fixture.py
import json
from tools.gen_zh_en_fixture import gen_fixture


def test_gen_fixture_has_schema_version():
    fx = gen_fixture()
    assert fx["schema_version"] == 1


def test_gen_fixture_includes_issue_examples():
    fx = gen_fixture()
    case_names = {c["name"] for c in fx["cases"]}
    assert "issue_example_please_open_gps" in case_names
    assert "issue_example_i_use_python" in case_names
    assert "issue_example_let_me_use_chatgpt" in case_names


def test_gen_fixture_idempotent(tmp_path):
    """同じ Python source で 2 回生成すれば byte 一致."""
    a = json.dumps(gen_fixture(), ensure_ascii=False, indent=2)
    b = json.dumps(gen_fixture(), ensure_ascii=False, indent=2)
    assert a == b
```

---

## 6. E2E テスト

### 利用者シナリオの手動確認

以下のシナリオを各ランタイムで実行、README 例どおりに動作することを確認:

1. **デフォルト動作** (zh-en dispatch 有効):
   ```bash
   piper --text "请打开 GPS" --language zh-en --output-phonemes phonemes.json
   # 期待: GPS が pinyin で展開
   ```

2. **opt-out**:
   ```bash
   piper --text "请打开 GPS" --language zh-en --no-zh-en-dispatch --output-phonemes phonemes.json
   # 期待: GPS が US English (`d͡ʒi pi ɛs`) で展開
   ```

3. **カスタム辞書**:
   ```bash
   piper --text "请打开 MYORG" --language zh-en --loanword-data my.json
   # 期待: MYORG が my.json の定義に従って展開
   ```

### Doc 生成 CI

`docs-generation.yml` (新規 or 既存拡張) で:
- `cargo doc` 実行 → Rust docs 生成
- `dotnet build` で XML doc 生成 → `bin/Release/*.xml` artifact
- `tsc --declaration` で `.d.ts` 生成
- `sphinx-build` で Python docs HTML 生成
- `doxygen` で C++ docs HTML 生成 (新規)

各 artifact をダウンロード可能にし、PR でレビュー可能化。

---

## 7. 実装に関する懸念事項

### 懸念 1: 6 CHANGELOG の文言乖離
- **影響**: Tech Writer が分散執筆すると微妙に文言が違う可能性。
- **緩和**: D1 のテンプレートを `.github/PULL_REQUEST_TEMPLATE/zh-en-release.md` (新規) に固定、コピー元を 1 つに。
- **責任**: Tech Writer。

### 懸念 2: C++ doxygen の新規セットアップ工数
- **影響**: 既存 doxygen 設定がない (`Doxyfile` なし)。CI で生成成功するまでの試行錯誤に半日程度。
- **緩和**: 雛形 `Doxyfile` を `docs/cpp/Doxyfile` で commit、最低限の設定 (INPUT, OUTPUT_DIRECTORY, EXTRACT_ALL=YES) で開始。完全な doc 生成は v1.0.0 で改善。
- **責任**: Phase Lead + Tech Writer。

### 懸念 3: Migration guide の opt-out コード例の正確性
- **影響**: 各ランタイムの API がチケット間で微妙に違う場合 (例: TICKET-02 では `WithZhEnDispatch(true)`、TICKET-04 では `setZhEnDispatch(true)`)、migration guide 内で 6 種類のシグネチャを正確に書く必要。
- **緩和**: TICKET-01〜05 の各 Section 9.2 を読み直し、確定したシグネチャを D4 に転記。各 Phase Lead が 1 行ずつ verify。
- **責任**: Tech Writer + 各 Phase Lead。

### 懸念 4: PyPI / NuGet / npm publish の権限
- **影響**: 現状 publish 権限を持つメンバーが限定 (`yousan` のみと推定)。
- **緩和**: D7 の checklist に「publish 権限保有者: yousan」を明記、他メンバーは PR のみ作成。GitHub Actions 経由の自動化は将来課題。
- **責任**: DevOps + Phase Lead。

### 懸念 5: Glossary 更新時の同期
- **影響**: 用語追加時に 6 README + migration guide + glossary が同期しないと用語混乱。
- **緩和**: glossary を **single source of truth** として、各 README は glossary へのリンクのみで定義参照を行う pattern に。本 PR でこの方針を README に明記。
- **責任**: Tech Writer。

### 懸念 6: Fixture generator の Python 依存
- **影響**: `tools/gen_zh_en_fixture.py` を実行するには Python 環境が必要。Rust / Go / C++ 開発者が単独で再生成できない。
- **緩和**: Python は **fixture を生成する立場のみ**、他ランタイムは「fixture を読んで比較」する立場。CI 上で Python から再生成 → 他ランタイムが通過、を保証する設計。利用者 / 開発者は手動再生成が必要なケースは稀。
- **責任**: Python Dev。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] 6 CHANGELOG が同じ文言テンプレート
- [ ] 6 README に統一書式の ZH-EN 例
- [ ] Issue 例 3 件が全 README に登場
- [ ] opt-out コードが各ランタイムで動作確認済 (TICKET-01〜05 で実装と整合)
- [ ] **D2 / D4 の opt-out コード snippet が、TICKET-01〜05 §9.2 と byte 等価** (シグネチャ命名差異ゼロ、特に Rust の `enable_zh_en_dispatch`)
- [ ] **D4 migration guide の 6 ランタイムシグネチャが、設計書 §8.12 の正規シグネチャと完全一致**
- [ ] `vale --glob='**/*.md' .` で用語 lint 通過
- [ ] `changelog-lint` で 6 CHANGELOG format pass
- [ ] Migration guide が `docs/migration/v1.13-zh-en.md` に存在
- [ ] Glossary が `docs/spec/zh-en-loanword-glossary.md` に存在、6 README から link
- [ ] `tools/gen_zh_en_fixture.py` が Python source から fixture を生成可能
- [ ] Doc 生成 CI が green (rustdoc / XML doc / JSDoc / sphinx / godoc / doxygen)
- [ ] Release checklist が `RELEASING.md` または `README.md` に存在
- [ ] Branch protection 追加コマンド (D7 step 11) が PR description に明記

### ドキュメントレビュー

- [ ] markdownlint passes
- [ ] 設計書 §8.19 の共通要件 6 項目を全 API doc が満たす
- [ ] 用語が glossary と完全一致 (loanword / acronym / letter_fallback / zh_en_dispatch)
- [ ] migration guide が breaking-change 0 を明示

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 の major bump 一斉リリースを目指す場合の docs 戦略。本 PR は v0.x の minor bump で完結。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **Glossary single source of truth + vale lint 強制** | 用語定義は `docs/spec/zh-en-loanword-glossary.md` のみ、6 README は link のみ。`vale` lint (`.vale.ini` + `styles/PiperPlus/Glossary.yml`) で禁止語/推奨語を機械検証 (例: `loanword dictionary` → `loanword data`、`code switch` → `code-switching`)。`docs-generation.yml` の prerequisite job に追加。 |
| 2 | **Fixture single source = Python (pinned version)** | `tools/gen_zh_en_fixture.py` で生成、`piper_plus_g2p==0.3.0` を `tools/requirements.txt` に pin。fixture metadata に `py_runtime_version` を埋め込み、CI で drift 検出。Python 側 breaking change は **fixture 再生成 + 5 ランタイム test 更新を同時 PR** で必須化 (cross-runtime invariant 宣言)。 |
| 3 | **Migration guide 1 ファイル / version** | `docs/migration/v{N}-{feature}.md` 命名、SemVer ごとに増える。冒頭に compatibility matrix を必須化 (9.2)。 |
| 4 | **Release checklist は実行可能** | shell コマンドを直接コピペで動作、手順書ではなく runbook。 |
| 5 | **API doc は IDE 補完で読まれる** | docstring の最初の 1 文が IDE tooltip に出る前提で、概要 → 詳細の順。 |
| 6 | **Examples は run-able (言語 asymmetry 容認)** | Rust / Python / Go は `cargo test --doc` / `pytest --doctest-modules` / `Example_xxx()` で **CI gate** 化。C# / TypeScript / C++ は doctest 機能なし → README の Issue 例 3 件を `tests/fixtures/g2p/zh_en_loanword_matrix.json` の同名 case (`issue_example_*`) と必ず同期、TICKET-06 cross-runtime test で間接的に検証。 |
| 7 | **CHANGELOG は keep-a-changelog 準拠 + 機械検証** | `[Unreleased]` / `[Added]` / `[Fixed]` / `[Internal]` セクション固定。`.github/workflows/changelog-lint.yml` (本 PR で新規) で `parse-changelog` lint + 6 CHANGELOG の `[Unreleased]` 日付一致を検証、format violation で PR block。 |

### 9.1 Doc 生成 pipeline

| Tool | 役割 | 統合方法 |
|------|-----|---------|
| **`cargo doc`** | Rust API doc | `rust-tests.yml` で artifact upload、`docs.rs` で auto publish |
| **`docfx`** | C# API doc | `docs/csharp-docfx.json` で設定、GitHub Pages publish |
| **`typedoc`** | TypeScript API doc | `docs/wasm-typedoc.json`、npm site にも記載 |
| **`sphinx`** | Python API doc | `docs/python/conf.py`、`readthedocs.org` 連携 |
| **`godoc`** (組込) | Go API doc | `pkg.go.dev` 自動公開 |
| **`doxygen`** | C++ API doc | `docs/cpp/Doxyfile`、GitHub Pages publish |

**統合 docs site** (**後続 Phase で別 PR** に降格):
- 工数見積: theme + 6 ツール doc 統合 + Actions deploy + custom domain で半月〜1 月。本 PR (Day 14) のスコープ外。
- 短期戦略: 各 registry の公式 doc page (`docs.rs`, `pkg.go.dev`, `npmjs.com`, `nuget.org`, ReadTheDocs) を README から直接 link、unified portal は **不要**。
- 統合 site が必要になる条件: クロスランタイム比較 guide / tutorial / blog コンテンツが揃った時。それまでは保留。
- 候補ツール (将来検討): `mkdocs-material` (markdown 専用、HTML doc は iframe)、`docusaurus` (React-based、versioning 強力)、`vitepress` (軽量、Vue-based)。

### 9.2 Migration guide 構造 (`docs/migration/`)

```
docs/migration/
├── README.md                       # index, 全 migration guide リスト
├── v1.11-to-v1.12.md               # 既存
├── v1.13-zh-en.md                  # 本 PR で新規
├── v1.0-to-v2.0.md                 # 将来 (major bump 用)
└── _template.md                    # 新規 migration guide の雛形
```

**`_template.md`** は新規 migration を書くたびにコピペ元として使用、構造の統一を担保。

**冒頭に compatibility matrix を必須化** (利用者が「私のコードは何を変える必要があるか」を 1 表で理解)。**4 軸 (API / SemVer / ABI / schema) で集約** (レビュー指摘 D1 反映、TICKET-01 §9.4 / TICKET-04 §9.9 / TICKET-05 §9.9 / TICKET-06 §9.5 のコンテンツを単一表に統合):

```markdown
## Compatibility matrix (v{prev} → v{this}) — API / SemVer / ABI / Schema 4 軸

### A. API シグネチャ + Default 動作

| Runtime | Default 動作変更 | 新 API (opt-out) | 既存利用者が行うこと |
|--------|---------------|---------------|------------|
| Python (`piper-plus-g2p` X → Y) | ZH-EN 経路 default-on | `phonemize(..., enable_zh_en_dispatch=False)` | **何もしない** または opt-out flag 追加 |
| Rust `piper-plus-g2p` (X → Y) | 同上 (Cargo `feature = "zh-en"` 有効時) | `MultilingualPhonemizer::builder().enable_zh_en_dispatch(false)` | feature 無効なら影響なし |
| Rust `piper-core` (X → Y) | 同上 | `.enable_zh_en_dispatch(false)` | 同上 |
| Go (X → Y) | 同上 | `multilingual.New(..., WithZhEnDispatch(false))` functional option | 同上 |
| C# (X → Y) | 同上 | `new MultilingualPhonemizerBuilder().EnableZhEnDispatch(false)` builder, または `MultilingualPhonemizerOptions { EnableZhEnDispatch = false }` | 同上 |
| JS / WASM (X → Y) | 同上 (Cargo `feature = "zh-en"` 有効時、bundle に含まれる時のみ) | `phonemizer.setZhEnDispatch(false)` instance method | feature 未有効版を使えば影響なし |
| C++ (vX → vY) | 同上 (デスクトップ default-on / Mobile build-time 設定) | `MultilingualPhonemizerOptions{ enable_zh_en_dispatch = false }` | 同上 |

### B. SemVer 影響 (TICKET-01 §9.4 / TICKET-04 §9.9 集約)

| Runtime | 本 PR の bump | 理由 | major bump 候補となる将来変更 |
|--------|-----------|------|---------------------|
| Python | minor (`X.Y.0`) | API 追加のみ、既存呼び出しは互換 | - |
| Rust | minor (`0.X+1.0` or `X.Y+1.0`) | trait method 追加、既存実装に default あり (semver compat) | trait に required method 追加、`piper-plus-g2p` と `piper-core` 統合 (v0.5.0 候補) |
| Go | minor | functional option 追加 | exported function signature 変更 |
| C# | minor (`0.X+1.0`) | new member on sealed class、AOT context 拡張 | sealed class → record class 変更、AOT context source-gen breaking |
| WASM/npm | minor (`0.X+1.0`) | new method on instance、Cargo `feature = "zh-en"` opt-in | feature default 有効化 (bundle size +30KB) |
| C++ | minor (lib soname 据え置き) | header-only struct 追加 (POD)、wrapper function 追加 | `phonemizeEmbeddedEnglish` を `chinese_phonemize.cpp` 内部関数の signature 変更 |

### C. ABI (C++ shared lib のみ、TICKET-05 §9.9 集約)

| 観点 | 状態 |
|------|------|
| `libpiper_plus.so` / `libpiper_plus.dylib` / `piper_plus.dll` SONAME | **据え置き** (本 PR で SO 番号変更なし) |
| ABI snapshot | `tests/abi/symbols.txt` に固定 (新規追加 export 関数のみ追加) |
| iOS xcframework symbol | `release-shared-lib.yml` で symbol check 強化 |
| inline namespace 使用 | `piper::v1::` を導入 (将来の major bump で `v2::` へ移行可能、co-installable) |
| `_Static_assert` で struct alignment 固定 | `LoanwordData` 等の POD 構造体に追加 |

### D. Schema migration (TICKET-06 §9.5 集約)

| 観点 | 状態 |
|------|------|
| Current schema | `schema_version: 1` (`acronyms` / `loanwords` / `letter_fallback` の 3 dict) |
| Forward-compat loader | 全 5 ランタイム + Python が `unknown field` を ignore (各テスト `test_loader_accepts_unknown_fields_in_schema_v2` で固定、YELLOW-5) |
| v2 schema 追加候補 | `tone_overrides`, `ja_en_loanwords`, `dialectal_variants` 等 |
| Breaking schema migration プロトコル | (1) Python source で v2 提案 → (2) forward-compat loader で全 5 ランタイム受理確認 → (3) major bump (Python `2.0.0` + Rust `1.0.0` + ...) で v1 サポート削除 |
| 5 ランタイム同時 PR は不要 | forward-compat loader 経由で段階的移行可能 |

> **TL;DR**: 純 ZH / 純 EN 利用者は何もする必要なし。本 PR は API / SemVer / ABI / Schema いずれの軸でも minor / 据え置きのみで、major breaking change なし。
```

### 9.3 Release automation

**現行**: 手動 (D7 checklist)。

**v1.0.0 候補**: GitHub Actions で **`release-please-action` (Google) を採用**。

**`release-please` を選ぶ理由**:
- piper-plus は 5 言語 monorepo (Python/Rust/Go/C#/JS) で、`release-please` は per-package PR モデルにより Rust workspace と PyPI と npm を **独立に bump 可能**。
- `semantic-release` は npm ecosystem 中心で、Rust / C# / Go の plugin maturity が低いため、5 言語対応のためには 3rd party plugin chain (`multi-semantic-release` 等) が必要。

**`release-please-config.json` 案**:

```json
{
  "packages": {
    "src/python/g2p": { "release-type": "python", "package-name": "piper-plus-g2p" },
    "src/rust/piper-plus-g2p": { "release-type": "rust" },
    "src/rust/piper-core": { "release-type": "rust" },
    "src/rust/piper-cli": { "release-type": "rust" },
    "src/wasm/g2p": { "release-type": "node", "package-name": "@piper-plus/g2p" },
    "src/csharp": { "release-type": "simple", "package-name": "PiperPlus.Core" },
    "src/go": { "release-type": "go-yoshi", "package-name": "github.com/ayutaz/piper-plus" }
  },
  "plugins": [
    { "type": "linked-versions", "groupName": "g2p",
      "components": ["src/python/g2p", "src/rust/piper-plus-g2p", "src/wasm/g2p"] }
  ]
}
```

**conventional commit prefix** (本 PR から採用推奨): `feat:`, `fix:`, `docs:`, `chore:`, `BREAKING CHANGE:`。本 PR の commit message は既に prefix 付きで互換あり。

`release-please` 自動化は:
- CHANGELOG 生成
- 版番号 bump
- git tag push
- GitHub Release 作成
- 各 registry への publish (別 workflow からの trigger)

### 9.4 Failure mode

| ケース | 動作 | 修復 |
|-------|------|-----|
| CHANGELOG conflict | merge 時に手動解決 | テンプレート踏襲、conflict marker を消す |
| Doc 生成 CI fail | PR block | 該当ランタイムの docstring を修正 |
| Fixture regenerate で diff | PR block | Python source を修正、または fixture を re-commit |
| Release publish fail (registry side) | manual retry | `cargo publish --dry-run` で事前確認 |

### 9.5 Observability

- リリース後、各 registry の DL 数を `docs/release-stats.md` に手動記録 (将来 dashboard 化)。
- `pkg.go.dev`, `crates.io`, `npmjs.com`, `pypi.org`, `nuget.org` のダウンロードグラフを weekly review。

---

## 10. 後続タスクへの連絡内容

### TICKET-01〜06 への遡及確認事項 (本チケットで全完成)

| 項目 | 確認 |
|------|------|
| API シグネチャ確定 | TICKET-01〜05 の §2.X / §9.2 と D4 (migration guide) のコード例が一致 |
| Branch protection | TICKET-06 S5 と D7 step 11 のコマンドが一致 |
| Fixture path | TICKET-06 S3 (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) と D5 (`tools/gen_zh_en_fixture.py --output`) が一致 |

### Phase 2 / 将来 PR への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **JA-EN / KO-EN docs** | Phase 2 で `docs/migration/v1.14-ja-en.md` 等を追加、本 PR の glossary を template として使う |
| **Doc 統合 site** | `mkdocs-material` で 6 ランタイム統一公開 (v1.0.0 候補) |
| **Release automation** | `release-please` 導入で CHANGELOG / tag / publish 自動化 (v1.0.0 候補) |
| **Performance benchmark CI** | `g2p-phonemize-perf.yml` を別 PR で導入、p99 latency / WASM size 監視 |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §8.11 / §8.19 / §8.21 から派生) |
