---
name: check-loanword
description: ZH-EN code-switching loanword の同期と forward-compat を 1 コマンドで検査。zh_en_loanword.json を編集したり 5 ランタイムのいずれかに新規エントリを追加する前後に呼ぶ。Python source を canonical とし、Rust×2 / Go / C# / WASM / C++ の 6 mirror + Python runtime mirror = 計 7 copy + 6 fixture mirror が byte-for-byte 一致しているかを確認。
disable-model-invocation: false
allowed-tools: Bash(python *) Bash(uv run *) Bash(cargo test *) Bash(go test *) Bash(node *) Bash(dotnet test *) Bash(git diff *) Bash(git status *)
---

# ZH-EN Loanword Consistency Check

ZH-EN code-switching (Issue #384) で使う loanword 辞書 (`zh_en_loanword.json`) を 5 ランタイムに展開する際の同期チェック。`pua-contract.toml` の PUA 同期と同じ哲学で、Python source を **唯一の真実** とし、CI で 7 copy + 6 fixture mirror が byte-for-byte 一致することを保証する。

## 何をチェックするか

`docs/reference/zh-en-loanword/README.md` の不変条件:

1. **7 mirror byte-for-byte sync** — Python source と以下の 6 mirror が SHA256 一致:
   - Python runtime (`src/python_run/piper/phonemize/data/zh_en_loanword.json`)
   - Rust 2 crate (`src/rust/piper-plus-g2p/data/`, `src/rust/piper-core/data/`)
   - Go (`src/go/phonemize/data/zh_en_loanword.json`)
   - C# (`src/csharp/PiperPlus.Core/Phonemize/Data/zh_en_loanword.json`)
   - WASM (`src/wasm/g2p/data/zh_en_loanword.json`)
   - C++ (`src/cpp/data/zh_en_loanword.json`)
2. **Schema validation** — Python の `_load_loanword_data` と同じ書式 (`'<section>.<key>' must be list[str]`) でエラーを出すこと
3. **6 fixture mirror sync** — `tests/fixtures/g2p/zh_en_loanword_matrix.json` と以下の mirror が一致:
   - `src/go/phonemize/testdata/`
   - `src/csharp/PiperPlus.Core.Tests/Phonemize/TestData/`
   - `src/cpp/tests/fixtures/`
   - `src/wasm/g2p/test/fixtures/`
   - `src/rust/piper-plus-g2p/tests/fixtures/`, `src/rust/piper-core/tests/fixtures/`
4. **Forward-compat (YELLOW-5)** — 各ランタイムの loader が `schema_version: 2` 未来の追加フィールドを silent ignore すること

## 実行ステップ

### 1. ローカルで sync 状態を確認

```bash
python scripts/check_loanword_consistency.py
```

期待: `OK All 7 copies + 6 fixture mirrors in sync` で終了 (exit 0)。

### 2. drift 発見時は自動修復

Python source を canonical とした **一方向コピー** で復元:

```bash
python scripts/check_loanword_consistency.py --diff   # 差分確認 (dry-run)
python scripts/check_loanword_consistency.py --fix    # 6 mirror + 6 fixture を Python source に揃える
```

> **注意**: Mirror を直接編集しても `--fix` で上書きされる。JSON 変更を提案する場合は **必ず Python source (`src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json`) を編集** すること。

### 3. Schema validation のみ確認 (CI 用)

```bash
python scripts/check_loanword_consistency.py --schema-only
```

### 4. 各ランタイムの forward-compat loader test を回す

各ランタイムに `*Loader*Schema*V2*` 系の test が存在し、未来の `schema_version: 2` を受理することを pinning している:

```bash
# Rust (両 crate)
cd src/rust && cargo test test_zh_en_loader_accepts_unknown_fields_in_schema_v2

# Go
cd src/go && go test ./phonemize/... -run TestLoaderAcceptsUnknownFieldsInSchemaV2

# C#
cd src/csharp && dotnet test --filter "FullyQualifiedName~Loader_AcceptsUnknownFieldsInSchemaV2"

# WASM
node --test src/wasm/g2p/test/test-chinese-zh-en.js  # forward-compat assertion 含む
```

### 5. CI workflow が green か確認

```bash
gh workflow view "ZH-EN Loanword Sync Gate" --branch <branch>
```

`json-sync` job (5 分以内) が PASS していれば OK。

## 確認すべき事項

- [ ] `python scripts/check_loanword_consistency.py` が `OK All 7 copies + 6 fixture mirrors in sync` を返す
- [ ] schema validation でエラーなし
- [ ] 5 ランタイムの forward-compat loader test が PASS
- [ ] CI workflow `ZH-EN Loanword Sync Gate / json-sync` が green
- [ ] `git diff src/python/g2p/piper_plus_g2p/data/zh_en_loanword.json` が意図した変更のみ
- [ ] PR description に "loanword JSON updated, 6 mirrors auto-synced via `--fix`" を明記

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `MISMATCH src/.../zh_en_loanword.json` | `--fix` で復元、または Python source の意図しない変更を revert |
| `MISSING src/.../zh_en_loanword.json` | `--fix` で作成、または該当ランタイム実装が未着手 (Phase 6a 想定なら `--allow-missing` を一時利用) |
| `'acronyms.GPS' must be list[str]` | Python source で値型が間違っている。`["ji4", "pi4", "ai1", "si4"]` の形式に修正 |
| `FIXTURE OUT OF SYNC` | `tests/fixtures/g2p/zh_en_loanword_matrix.json` を更新後 `--fix` で 6 mirror に展開 |
| Windows で `sha256` 不一致が常時出る | `.gitattributes` の `*.json text eol=lf` で CRLF 強制 LF。再正規化: `git rm --cached <file> && git add <file>` |

## 関連ドキュメント

- [ZH-EN runtime rollout 設計書](docs/reference/zh-en-loanword/README.md)
- [Cross-runtime fixture matrix](tests/fixtures/g2p/zh_en_loanword_matrix.json)
- [Workflow](.github/workflows/zh-en-loanword-sync.yml)
- [PUA sync skill (template)](.claude/skills/check-pua/SKILL.md)
