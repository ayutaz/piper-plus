# TICKET-06: CI 同期ガード + Cross-runtime fixture

| 項目 | 値 |
|------|---|
| **チケット ID** | TICKET-06 |
| **マイルストーン** | Phase 6 (Day 13) |
| **親 INDEX** | [README.md](README.md) |
| **設計書参照** | §4.2 X5 / §8.3 (JSON 同期 CI) / §8.7 (テストデータ統一) / §8.15 (CI 整合性) |
| **ステータス** | 📝 Draft |
| **依存元** | TICKET-01〜05 (各ランタイム実装完了が前提、ただし JSON 同期 job のみは並列着手可) |
| **依存先** | TICKET-07 (Docs) |
| **追加 LOC** | ~150 (workflow YAML + Python helper script + fixture) |
| **作業ブランチ** | `feat/zh-en-loanword-runtimes` |

---

## 1. タスク目的とゴール

**目的**: 6 箇所に分散する `zh_en_loanword.json` の **byte-for-byte 一致**を CI で強制する。Cross-runtime 統一テスト fixture (`tests/fixtures/g2p/zh_en_loanword_matrix.json`) を導入し、5 ランタイム全てで同じケースをループ実行できるようにする。

**ゴール**:
- `.github/workflows/zh-en-loanword-sync.yml` が PR で hash mismatch を 100% 検出。
- `scripts/check_loanword_consistency.py` で開発者がローカルで同期確認・自動コピー (`--fix`) できる。
- `tests/fixtures/g2p/zh_en_loanword_matrix.json` に統一マトリックス (~25 ケース、`schema_version: 1` 必須) を配置。
- 各ランタイム test loader が fixture を読み込み、ループ実行で全件 PASS。
- `ci-required` (branch protection) に新 sync job を追加。
- CI 全体時間 +2 分以内に収める。
- pre-commit hook (`scripts/check_loanword_consistency.py --check`) が opt-in で動作。

---

## 2. 実装する内容の詳細

### S1. `.github/workflows/zh-en-loanword-sync.yml` 新規

設計書 §8.15 のスケッチを踏襲、追加で **Schema validation** と **fixture sync** も含める:

```yaml
name: ZH-EN Loanword Sync
on:
  pull_request:
    paths:
      - '**/zh_en_loanword.json'
      - 'tests/fixtures/g2p/zh_en_loanword_matrix.json'
      - '.github/workflows/zh-en-loanword-sync.yml'
      - 'scripts/check_loanword_consistency.py'
  workflow_dispatch:

jobs:
  json-sync:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with: { python-version: '3.13' }

      - name: 1. Byte-for-byte sync (sha256)
        run: |
          SOURCE=src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json
          HASH=$(sha256sum "$SOURCE" | cut -d' ' -f1)
          echo "Source: $HASH ($SOURCE)"
          fail=0
          for copy in \
            src/python_run/piper/phonemize/data/zh_en_loanword.json \
            src/rust/piper-plus-g2p/data/zh_en_loanword.json \
            src/rust/piper-core/data/zh_en_loanword.json \
            src/go/phonemize/data/zh_en_loanword.json \
            src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json \
            src/wasm/g2p/data/zh_en_loanword.json \
            src/cpp/data/zh_en_loanword.json; do
            [ -f "$copy" ] || { echo "::error::MISSING $copy"; fail=1; continue; }
            COPY_HASH=$(sha256sum "$copy" | cut -d' ' -f1)
            if [ "$HASH" != "$COPY_HASH" ]; then
              echo "::error::MISMATCH $copy ($COPY_HASH != $HASH)"
              fail=1
            fi
          done
          [ $fail -eq 0 ] || exit 1

      - name: 2. Schema validation (Python source of truth)
        run: |
          python3 scripts/check_loanword_consistency.py --schema-only

      - name: 3. Fixture matrix schema check
        run: |
          python3 -c "
          import json
          with open('tests/fixtures/g2p/zh_en_loanword_matrix.json') as f:
              fx = json.load(f)
          assert fx.get('schema_version') == 1, 'fixture schema_version must be 1'
          assert isinstance(fx.get('cases'), list)
          for c in fx['cases']:
              assert {'name','input','expected'}.issubset(c.keys())
          print(f'✓ fixture has {len(fx[\"cases\"])} cases')
          "

      - name: 4. Cross-runtime fixture sync (testdata/ コピー先確認)
        run: |
          # Go の testdata/, C# の TestData/, C++ の tests/fixtures/ がコピー反映済か
          for target in \
            src/go/phonemize/testdata/zh_en_loanword_matrix.json \
            src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/zh_en_loanword_matrix.json \
            src/cpp/tests/fixtures/zh_en_loanword_matrix.json; do
            [ -f "$target" ] || { echo "::error::missing fixture sync: $target"; exit 1; }
            diff "tests/fixtures/g2p/zh_en_loanword_matrix.json" "$target" \
              || { echo "::error::fixture diverged: $target"; exit 1; }
          done
          echo "✓ all fixture mirror copies in sync"
```

### S2. `scripts/check_loanword_consistency.py` 新規

PUA 同期 (`scripts/check_pua_consistency.py`) を踏襲。

```python
#!/usr/bin/env python3
"""ZH-EN loanword JSON 同期チェッカー.

7 箇所の zh_en_loanword.json を Python source と byte 一致させる。

Usage:
    python scripts/check_loanword_consistency.py            # チェックのみ (CI 用)
    python scripts/check_loanword_consistency.py --fix       # 自動コピー (開発者用)
    python scripts/check_loanword_consistency.py --schema-only  # schema のみ
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

SOURCE = Path("src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json")
COPIES = [
    Path("src/python_run/piper/phonemize/data/zh_en_loanword.json"),
    Path("src/rust/piper-plus-g2p/data/zh_en_loanword.json"),
    Path("src/rust/piper-core/data/zh_en_loanword.json"),
    Path("src/go/phonemize/data/zh_en_loanword.json"),
    Path("src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json"),
    Path("src/wasm/g2p/data/zh_en_loanword.json"),
    Path("src/cpp/data/zh_en_loanword.json"),
]
FIXTURE_SRC = Path("tests/fixtures/g2p/zh_en_loanword_matrix.json")
FIXTURE_MIRRORS = [
    Path("src/go/phonemize/testdata/zh_en_loanword_matrix.json"),
    Path("src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/zh_en_loanword_matrix.json"),
    Path("src/cpp/tests/fixtures/zh_en_loanword_matrix.json"),
    Path("src/wasm/g2p/test/fixtures/zh_en_loanword_matrix.json"),
    Path("src/rust/piper-core/tests/fixtures/zh_en_loanword_matrix.json"),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def validate_schema(p: Path) -> None:
    """Python と同じ schema validation を CI で再実行."""
    data = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(data.get("version"), int), "missing version"
    for section in ("acronyms", "loanwords", "letter_fallback"):
        m = data.get(section)
        assert isinstance(m, dict), f"{section} must be dict"
        for k, v in m.items():
            assert isinstance(v, list) and all(isinstance(e, str) for e in v), (
                f"{p}: '{section}.{k}' must be list[str]"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="copy from source")
    parser.add_argument("--schema-only", action="store_true", help="skip hash check")
    args = parser.parse_args()

    if not SOURCE.exists():
        print(f"ERROR: source missing: {SOURCE}", file=sys.stderr)
        return 1

    validate_schema(SOURCE)
    if args.schema_only:
        print(f"✓ schema OK: {SOURCE}")
        return 0

    src_hash = sha256(SOURCE)
    print(f"Source: {src_hash} ({SOURCE})")

    failed: list[str] = []
    for copy in COPIES:
        if not copy.exists():
            if args.fix:
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(SOURCE, copy)
                print(f"  [fixed] created {copy}")
                continue
            failed.append(f"MISSING {copy}")
            continue
        if sha256(copy) != src_hash:
            if args.fix:
                shutil.copy2(SOURCE, copy)
                print(f"  [fixed] {copy}")
                continue
            failed.append(f"MISMATCH {copy}")

    # fixture sync
    if FIXTURE_SRC.exists():
        fx_hash = sha256(FIXTURE_SRC)
        for mirror in FIXTURE_MIRRORS:
            if not mirror.exists() or sha256(mirror) != fx_hash:
                if args.fix:
                    mirror.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(FIXTURE_SRC, mirror)
                    print(f"  [fixed fixture] {mirror}")
                else:
                    failed.append(f"FIXTURE OUT OF SYNC {mirror}")

    if failed:
        for f in failed:
            print(f"  ✗ {f}", file=sys.stderr)
        print(
            f"\n{len(failed)} files out of sync. Run with --fix to copy from source.",
            file=sys.stderr,
        )
        return 1

    print(f"\n✓ All 7 copies + {len(FIXTURE_MIRRORS)} fixture mirrors in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

### S3. `tests/fixtures/g2p/zh_en_loanword_matrix.json` 新規

設計書 §4.3 統一テストマトリックスを fixture 化:

```json
{
  "schema_version": 1,
  "description": "Cross-runtime test matrix for ZH-EN code-switching. All runtimes must produce identical IPA token output.",
  "metadata": {
    "source": "Python piper_plus_g2p (PR #397)",
    "py_runtime": "src/python_run/piper/phonemize/chinese.py:_phonemize_embedded_english_raw",
    "version": 1
  },
  "cases": [
    { "name": "acronym_gps",
      "input": "GPS",
      "expected": ["t͡ɕ", "i", "˥˩", "p", "ʰ", "i", "˥˩", "aɪ", "˥˩", "s", "z̩", "˥˩"] },
    { "name": "loanword_python_case_sensitive",
      "input": "Python",
      "expected": ["pʰ", "aɪ", "˥˩", "s", "ə", "n", "˥"] },
    { "name": "loanword_chatgpt_5syllables",
      "input": "ChatGPT",
      "expected": ["t͡ʂ", "ɑ", "˥˩", "tʰ", "ɤ", "˥˩", "..."] },
    { "name": "letter_fallback_zz",
      "input": "ZZ",
      "expected": ["..."] },
    { "name": "empty",
      "input": "",
      "expected": [] },
    { "name": "punctuation_trailing_comma_equiv_gps",
      "input": "GPS,",
      "expected": ["...same as GPS..."] },
    { "name": "digits_z2z9_equiv_zz",
      "input": "Z2Z9",
      "expected": ["...same as ZZ..."] },
    { "name": "issue_example_please_open_gps",
      "input": "请打开 GPS",
      "expected": ["...full sentence IPA..."] },
    { "name": "issue_example_i_use_python",
      "input": "我喜欢用 Python 写代码",
      "expected": ["..."] },
    { "name": "issue_example_let_me_use_chatgpt",
      "input": "让我用 ChatGPT 写代码",
      "expected": ["..."] }
  ]
}
```

実際の `expected` は **Python ランタイムを実行して生成** (TICKET-07 で `tools/gen_zh_en_fixture.py` を導入予定、本 PR では python source からの 1 度生成 + commit)。

### S4. pre-commit hook (opt-in) `.pre-commit-hooks.yaml` 拡張

```yaml
- id: check-loanword-consistency
  name: ZH-EN loanword JSON sync (7 copies + fixture mirrors)
  entry: python3 scripts/check_loanword_consistency.py
  language: system
  files: '(?:zh_en_loanword\.json|zh_en_loanword_matrix\.json)$'
  pass_filenames: false
```

利用者 opt-in (既存の `.pre-commit-config.yaml` 慣習踏襲)。CI で同等のチェックが走るので必須ではない。

### S5. `ci-required` への追加

GitHub branch protection の `Required status checks` に `ZH-EN Loanword Sync / json-sync` を追加。

**手動操作の risk 低減**: PR description に以下のスクリプトを貼り、merge 直後にリポジトリオーナーが実行:

```bash
gh api -X PUT repos/ayutaz/piper-plus/branches/dev/protection \
  -F required_status_checks.contexts[]='ZH-EN Loanword Sync / json-sync'
```

将来 v1.0.0 後の改善 PR で全 workflow を `terraform-github-provider` または `branch-protection-rules-action` で IaC 化 (9.0 #8)。

### S6. `.claude/skills/check-loanword/SKILL.md` 新規 (skill 雛形)

PUA の `.claude/skills/check-pua/SKILL.md` を template にコピー、差分:

```markdown
---
name: check-loanword
description: ZH-EN loanword JSON の 7 copy + 5 fixture mirror が同期しているか確認、必要なら自動コピー。
allowed-tools: Bash(python3:*), Read, Edit
---

# ZH-EN Loanword Sync チェック

7 箇所の `zh_en_loanword.json` と 5 箇所の fixture mirror を Python source と byte 一致させる。

## ステップ

1. **schema validation のみ確認**:
   ```bash
   python3 scripts/check_loanword_consistency.py --schema-only
   ```

2. **byte 一致 + schema チェック**:
   ```bash
   python3 scripts/check_loanword_consistency.py
   ```

3. **問題があれば自動修復**:
   ```bash
   python3 scripts/check_loanword_consistency.py --fix
   ```

4. **修正をコミット**:
   ```bash
   git add -p
   git commit -m "chore: zh_en_loanword.json sync"
   ```

## 確認すべき事項

- [ ] Python source (`src/python/g2p/...`) が schema valid
- [ ] 7 copy 全てが byte-for-byte 一致
- [ ] 5 fixture mirror も一致
- [ ] CI workflow `ZH-EN Loanword Sync / json-sync` が green
```

工数: ~30 分。利用者は `/check-loanword` で 1 発確認可能、開発体験 ★★★。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 責任 |
|------|------|-----|
| **Phase Lead** | 1 | TICKET-01〜05 の JSON 配置パス確定確認、TICKET-07 への引き継ぎ |
| **DevOps** | 1 | S1 workflow YAML、S5 branch protection 設定 |
| **Python Dev** | 1 | S2 helper script、S3 fixture 生成 (Python ランタイム経由) |
| **QA / Test** | 1 | 各ランタイム test loader が fixture を読むことの確認、CI 実行ログレビュー |

**並列化**: S1 / S2 / S3 は並列着手可。S4 / S5 は最終工程。

**コミット推奨**:
- `chore(ci): zh-en-loanword-sync workflow 追加 (S1)`
- `chore(scripts): check_loanword_consistency.py 追加 (S2)`
- `test: cross-runtime fixture matrix 追加 (S3)`
- `chore: pre-commit hook と branch protection 設定 (S4+S5)`

---

## 4. 提供範囲とテスト項目

### 提供範囲 (in scope)

- `.github/workflows/zh-en-loanword-sync.yml`
- `scripts/check_loanword_consistency.py` (CLI helper)
- `tests/fixtures/g2p/zh_en_loanword_matrix.json` (source of truth fixture)
- 5 mirror fixture (Go / C# / C++ / WASM / Rust testdata)
- `.pre-commit-hooks.yaml` 拡張 (opt-in)
- `ci-required` への新 job 追加

### Out of scope

- 自動 PR 作成 bot (Python source 変更時に他 6 copy を自動更新)。9.1 の発動条件を満たした時点で v1.1.0 で再検討。
- Performance benchmark CI (TICKET-07 で導入)
- Branch protection の IaC 化 (9.0 #8 / TICKET-07 後の改善 PR で実施)

### テスト項目

- 7 copy の sha256 一致
- Python schema validation
- Fixture schema_version=1 確認
- 5 mirror fixture と source の一致
- 各ランタイム test (TICKET-01〜05) で fixture loader が動作することを確認

---

## 5. Unit テスト

`scripts/check_loanword_consistency.py` 自体に対する pytest テストを追加:

```python
# tests/test_check_loanword_consistency.py
import shutil
from pathlib import Path
import pytest
from scripts.check_loanword_consistency import sha256, validate_schema, COPIES, SOURCE


def test_source_exists():
    assert SOURCE.exists()


def test_source_schema_valid():
    validate_schema(SOURCE)


def test_all_copies_match_source():
    src_hash = sha256(SOURCE)
    for copy in COPIES:
        assert copy.exists(), f"missing {copy}"
        assert sha256(copy) == src_hash, f"out of sync: {copy}"


def test_fix_mode_creates_missing(tmp_path, monkeypatch):
    # fixture: 1 個削除して --fix で復活確認
    ...
```

---

## 6. E2E テスト

### CI 実行シミュレーション

ローカルで以下を実行し、すべて PASS することを確認:

```bash
# 1. clean state で sync 確認
python3 scripts/check_loanword_consistency.py
# 期待: ✓ All 7 copies in sync

# 2. 1 file 改変して fail 確認
echo " " >> src/rust/piper-plus-g2p/data/zh_en_loanword.json
python3 scripts/check_loanword_consistency.py  # 期待: exit 1
python3 scripts/check_loanword_consistency.py --fix  # 期待: 復元

# 3. workflow を act (https://github.com/nektos/act) で local 実行
act -j json-sync
```

### Branch protection 動作確認

- `feat/test-zh-en-broken-sync` ブランチで意図的に破壊 → PR 作成 → CI fail → マージブロック確認。

---

## 7. 実装に関する懸念事項

### 懸念 1: Windows CRLF 改行の混入
- **影響**: Windows 開発者が JSON を編集すると LF → CRLF 自動変換、sha256 不一致。
- **緩和**: `.gitattributes` で `*.json text eol=lf` を強制 (既存設定で対応済か確認、`.gitattributes` Line 1-3)。新規パスを追加。
- **責任**: DevOps。

### 懸念 2: workflow `paths` フィルタの抜け
- **影響**: 6 copy のうち 1 つだけ編集された PR で workflow が起動しないリスク。
- **緩和**: `paths: '**/zh_en_loanword.json'` で glob 対応、CI で該当 PR を捕捉。
- **責任**: DevOps。

### 懸念 3: Branch protection の手動設定漏れ
- **影響**: workflow を追加しても `ci-required` に登録されていなければ block にならない。
- **緩和**: PR description に「branch protection 設定要」を明記、merge 前に手動操作。GitHub の `auto_request_review` API で自動化検討 (将来課題)。
- **責任**: Phase Lead + リポジトリオーナー。

### 懸念 4: Pre-commit hook の Windows 互換
- **影響**: PowerShell 環境で `python3` 不在、`python` のみ。
- **緩和**: hook の `entry` を `python` に統一、`pre-commit run` が PATH 解決する慣習を信頼。
- **責任**: DevOps。

### 懸念 5: Fixture 生成の再現性
- **影響**: Python ランタイム実装が変わると `expected` も変わるが、手動更新だと反映漏れ。
- **緩和**: TICKET-07 で `tools/gen_zh_en_fixture.py` を導入、`make update-fixture` で自動再生成可能にする。本 PR では手動 1 回生成。
- **責任**: Python Dev (本 PR) + Tech Writer (TICKET-07)。

### 懸念 6: CI 並列実行時の race
- **影響**: 別 PR と並行で sync workflow が走る。同じ source を見ているため race なし。
- **緩和**: workflow は read-only、副作用なし。
- **責任**: なし (問題なし)。

---

## 8. レビュー項目

### コードレビューチェックリスト

- [ ] workflow `paths` で全 7 copy + fixture をカバー
- [ ] `sha256sum` が macOS / Linux / Windows runner 全てで動作 (`runs-on: ubuntu-latest` のみなので OK)
- [ ] `check_loanword_consistency.py` の `--fix` で全 7 copy を一発で同期
- [ ] schema validation が Python source / 6 mirror 全てに走る
- [ ] fixture `schema_version=1` がチェックされる
- [ ] 5 mirror fixture (Go/C#/C++/WASM/Rust) の同期確認
- [ ] `ci-required` に追加すべき job 名がドキュメントに明記
- [ ] pre-commit hook が opt-in (利用者の `.pre-commit-config.yaml` で有効化)
- [ ] CI 全体時間 +2 分以内

### ドキュメントレビュー

- [ ] 設計書 §8.3 / §8.15 と整合
- [ ] PR description に「branch protection 手動設定要」明記
- [ ] `docs/spec/zh-en-loanword-runtime-rollout.md` の関連セクションに新 workflow リンクを追加

---

## 9. 一から作り直すとしたら

> **前提**: v1.0.0 (`piper-plus-g2p` 1.0 系) を対象。本 PR は CI 整備に専念、機能変更なし。

### 9.0 思想

| # | 原則 | 説明 |
|---|------|------|
| 1 | **Single source of truth** | Python JSON が canonical、他 6 copy は機械的なミラー。 |
| 2 | **Byte-for-byte 一致** | 1 文字でも違えば CI block。spelling 違い / 改行 / encoding を全て検出。 |
| 3 | **`--fix` で開発者体験向上** | スクリプト 1 発で同期、手動 7 ファイル編集を撲滅。 |
| 4 | **Schema validation も同時** | hash 一致だけでなく型チェック (Python 同等 `list[str]`) も CI で。 |
| 5 | **Cross-runtime fixture も同期対象** | 5 mirror fixture も byte 一致を保証、test discovery 経路を破壊しない。 |
| 6 | **Pre-commit hook は opt-in** (PUA / Anthropic Claude Code / TF / K8s 同戦略) | 強制 install は `core.hooksPath` で bypass 可能、Windows で `python3` 不在問題で hook level fatal。CI gate が最終防衛。CONTRIBUTING.md で `pre-commit install` を推奨記載に留める。 |
| 7 | **`/check-loanword` skill 化を本 PR で実施** (S6) | PUA `/check-pua` パターン踏襲、開発体験 ★★★。Out of scope から外して提供範囲に追加。 |
| 8 | **Branch protection IaC は別 ticket** | 既存 PUA workflow も手動設定 (PR merge 後に admin が登録)。本 PR で IaC 化すると scope 膨張のため、TICKET-07 後の改善 PR で全 workflow 一斉化 (terraform-github-provider または `branch-protection-rules-action`)。 |

### 9.1 データ層

**現状の判断**: Python が source、ファイルコピー 7 + fixture mirror 5 = 計 12 ファイル。symlink は Windows 非対応で不採用。**ファイル コピー + CI 強制**が現実解。

**3 案比較** (operational コスト視点):

| 軸 | A (git submodule) | B (auto-sync bot) | C (build hook) |
|----|-------------------|-------------------|---------------|
| **PR notification 頻度** | 0 | **毎 source 変更で +1 PR** (年 ~30 PR) | 0 |
| **forking 制約** | submodule 認証で fork PR 不可 | bot PR が fork から作れない (`secrets.GITHUB_TOKEN` 制限) | 影響なし |
| **merge conflict 頻度** | 高 (submodule pin が衝突) | 中 (long-lived branch で stale) | 低 (build 時生成) |
| **release artifact 影響** | submodule init が distribute 後に必要 | 影響なし | tarball 配布で source-only consumer が壊れる |
| **review 負担** | submodule pin 1 行レビュー | **bot PR を毎回 approve (approve fatigue)** | 影響なし |

**推奨**: **現行案 (CI gate のみ) + `--fix` script を維持**。Option B (auto-sync bot) は operational コスト (notification 過多、fork PR で動かない、approve fatigue) が CI gate の一発検出を上回る価値を提供しない。auto-sync は `--fix` を開発者が手元で 1 回叩けば済む。

**将来 v1.1.0 で auto-sync bot を再検討する条件** (発動条件付き保留):
- Python source 変更頻度が四半期 ≥ 5 PR を超えた場合
- 開発者から「7 ファイルコピー忘れる」issue が四半期 ≥ 2 件

それ以下では現行案で十分。

### 9.2 API 層

```python
# scripts/check_loanword_consistency.py の API
def check(fix: bool = False, schema_only: bool = False) -> CheckResult:
    """7 copy + 5 fixture mirror を sync 確認。--fix で自動修復。"""
    ...
```

`CheckResult` は dataclass で `is_synced: bool`, `failed_files: list[str]`, `fixed_files: list[str]` を返す。CI で structured log 化。

### 9.3 CI Pipeline 設計

```
[PR 作成]
  ↓
[zh-en-loanword-sync] ← 本 PR で追加
  ↓ (ファイル一致 OK)
[各ランタイム tests] ← TICKET-01〜05 が追加
  ↓ (全件 PASS)
[g2p-cross-platform] ← 既存 workflow で fixture loop 実行
  ↓
[merge 可能]
```

**Concurrency 制御** (PUA workflow と同等):

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.head_ref || github.ref }}
  cancel-in-progress: true   # 同 PR 連続 push 時のみ canceling
```

`cancel-in-progress: true` は **同 workflow の同 ref に閉じる**。他 workflow (rust-tests, cpp-tests) は引き続き走るので「PR 作者が他 job ログを見られない」懸念は発生しない。`pua-consistency.yml` line 46 と同設定。

### 9.3 補足: CI 時間再見積もり

§8.15「+2 分以内」は **cache hit 前提**。cold cache 時の悲観値も併記:

| Workflow | 楽観 (cache hit) | 悲観 (cache miss) | timeout 設定 |
|---------|----------------|-----------------|------------|
| zh-en-loanword-sync (新規) | 30s | 90s | 5 分 (十分) |
| g2p-cross-platform 追加分 | +60s | +180s (C++ cold build) | 既存 20 分 |
| 各ランタイム単体 tests 追加分 | +30s | +60s | 既存設定 |

**risk**: C++ cache miss + WASM rebuild が重なると +3 分。
**緩和**: `Swatinem/rust-cache`, `actions/cache` for ccache を明示設定。各 TICKET-01〜05 のレビューで cache 設定確認を必須化。

### 9.4 Failure mode

| ケース | 動作 | 修復方法 |
|-------|------|---------|
| sha256 mismatch | CI fail | `python3 scripts/check_loanword_consistency.py --fix` |
| 1 mirror file 欠損 | CI fail | 同上 |
| schema 違反 (Python source) | CI fail | source を修正、validate_schema を通す |
| fixture schema_version != 1 | CI fail | 9.5 の migration プロトコルで forward-compat loader 経由 |
| pre-commit hook not enabled | hook 走らない | opt-in なので利用者責任、CI が catch する |

### 9.5 Schema migration プロトコル (v1 → v2)

**問題**: 本 ticket の親設計書 §1 は「5 ランタイム同時展開」を 1 ブランチで実施するが、schema bump で毎回 5 ランタイム同時展開ブランチを切るのは現実的でない。古い release tag からの regression test が継続できなくなる risk もある。

**Forward-compatible loader pattern**:

1. Fixture loader は `schema_version >= 1` を許容、`schema_version` を読んで case parser を分岐 (forward-compat)。
2. v2 fixture を導入する PR では:
   - v1 fixture を `tests/fixtures/g2p/zh_en_loanword_matrix_v1.json` に rename + 保持
   - v2 fixture を `_matrix.json` (canonical name) に置く
   - 全 loader が両方読めるよう `parse_v1()` / `parse_v2()` を実装
3. 1 マイナーバージョン後 (v1.2.0 など) に v1 fixture を削除する deprecation PR
4. CI で `_matrix_v*.json` 全部の sync を保証 (`FIXTURE_MIRRORS` を glob 化)

これにより古い release tag からの regression test が継続可能、5 ランタイム同時 PR を要求しない。

### 9.6 i18n 拡張パス

| Phase | 内容 | 必要な変更 |
|-------|------|-----------|
| Phase 1 (本 PR) | ZH-EN | `zh_en_loanword.json` 7 copy |
| Phase 2 | JA-EN / KO-EN | `data/loanword/{ja_en, ko_en}.json` 追加、CI workflow に追加 path |
| Phase 3 | 任意ペア | `LoanwordRegistry` mechanism、CI は dynamic にすべての `*_loanword.json` を検出 |

### 9.7 Observability

- workflow 実行ログを GitHub Actions の `::error::` annotation で出力、PR の "Files changed" タブに直接表示。
- 失敗時のメッセージ書式統一: `MISMATCH {file} ({actual} != {expected})`、自動修復コマンド `--fix` を併記。

---

## 10. 後続タスクへの連絡内容

### TICKET-07 (Docs) への引き継ぎ事項

| 項目 | 内容 |
|------|------|
| **Workflow 名** | `ZH-EN Loanword Sync / json-sync` (CI badge を README に追加可能) |
| **Helper script** | `scripts/check_loanword_consistency.py` の使用例を `docs/guides/development.md` に追加 |
| **Skill 化検討** | `/check-loanword` skill を `.claude/skills/check-loanword.md` で実装 (将来課題、PUA `/check-pua` 同等) |
| **Fixture 自動生成** | `tools/gen_zh_en_fixture.py` を TICKET-07 で実装 |

### 全 TICKET-01〜05 への遡及確認事項

| 項目 | 確認事項 |
|------|---------|
| **JSON 配置パス** | TICKET-01 R4 / TICKET-02 G4 / TICKET-03 C2 / TICKET-04 W2 / TICKET-05 P5 で確定したパスがそれぞれ workflow の COPIES list と一致 |
| **Fixture loader** | 各ランタイム test が `tests/fixtures/g2p/zh_en_loanword_matrix.json` (Go testdata 含む) を読み込めること |
| **Schema validation エラー文言** | 各ランタイムが Python と同じ書式 `'{section}.{key}' must be list[str]` を出すこと |

---

## 改訂履歴

| 日付 | 版 | 変更内容 |
|------|----|---------|
| 2026-05-07 | v1 | 初版 (設計書 §4.2 X5 / §8.3 / §8.7 / §8.15 から派生) |
