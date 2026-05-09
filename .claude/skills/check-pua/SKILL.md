---
name: check-pua
description: PUA テーブル / fixture / config の整合性を 1 コマンドで検査。pua.json を編集したり ɔɪ/œ̃/ɐ̃ のような multi-codepoint 音素を扱う前後に呼ぶ。docs/spec/pua-contract.toml の 4 不変条件を全部チェック。
disable-model-invocation: false
allowed-tools: Bash(python *) Bash(uv run *) Bash(cargo test *) Bash(go test *) Bash(node *) Bash(git diff *) Bash(git status *)
---

# PUA Consistency Check

PUA (Private Use Area) 関連の不変条件を一括検査します。`pua.json` を編集する PR や、新しい多コードポイント音素 (例: 韓国語の濃音、追加母音等) を追加する作業で必ず呼んでください。

## 何をチェックするか

`docs/spec/pua-contract.toml` の 4 不変条件:

1. **Cross-runtime consistency** — `pua.json` と 6 ランタイム (Python/Rust/Go/JS/C#/C++) のテーブルが byte-for-byte 一致
2. **Inventory coverage** — `id_maps.py` の language inventory に出てくる multi-codepoint token は全て `pua.json` に登録済み
3. **Generated id_map keys** — `phoneme_id_map` の全 key が単一コードポイント (C++ runtime の制約)
4. **PUA_COMPAT_VERSION sync** — 全ランタイムの compat version が `pua.json` の version 値と一致

加えて:

1. **Fixture drift** — `tests/fixtures/g2p/phoneme_test_cases.json` の `pua_map` / `pua_map_count` が `pua.json` と一致 (PR #389 で踏んだバグ class)

## 実行ステップ

### 1. Cross-runtime consistency

```bash
python scripts/check_pua_consistency.py --verbose --check-version
```

期待: `OK: pua.json matches all 6 runtime tables` で終了。

### 2. Inventory + fail-fast invariants (Python)

```bash
cd src/python/g2p
uv sync --extra all --extra dev
uv run pytest tests/test_pua_invariants.py -v
```

期待: 全 PASS。

### 3. Pre-flight config validator

```bash
cd src/python
uv sync --extra test
uv run pytest tests/test_update_model_config.py -v
```

期待: 全 PASS。

### 4. Fixture drift detection

```bash
python scripts/regenerate_test_fixture.py --check
```

期待: `OK: tests/fixtures/g2p/phoneme_test_cases.json already in sync with pua.json`。

drift があれば `python scripts/regenerate_test_fixture.py` を引数なしで再実行して fixture を更新、commit。

### 5. (任意) ランタイム別 PUA テーブルテスト

時間がある時のみ:

```bash
# Rust
cd src/rust && cargo test -p piper-plus-g2p --lib -- token_map

# Go
cd src/go && go test ./phonemize/... -run "TestFixedPUA"

# JS
cd src/wasm/g2p && node --test test/test-pua-map.js
```

## 失敗時の典型的な対応

| 失敗内容 | 対応 |
|---------|------|
| Cross-runtime mismatch | 該当ランタイムの PUA テーブル (`token_map.rs` / `pua.go` / `pua-map.js` / `OpenJTalkToPiperMapping.cs` / `phoneme_parser.cpp`) を `pua.json` と一致させる |
| Inventory coverage fail | 失敗した token を `src/python/g2p/piper_plus_g2p/data/pua.json` の `entries` に追加 (codepoint range は `docs/spec/pua-contract.toml` の `[ranges]` セクション参照) |
| Fixture drift | `python scripts/regenerate_test_fixture.py` で fixture を更新 |
| compat version mismatch | `pua.json` の `version` を bump したら、`src/python/g2p/piper_plus_g2p/encode/pua.py` の `PUA_COMPAT_VERSION` と `src/wasm/g2p/src/pua-map.js` の `PUA_COMPAT_VERSION` と `src/rust/piper-plus-g2p/src/token_map.rs` の `PUA_COMPAT_VERSION` を全部同じ値に揃える |

## 関連リソース

- ルール定義: `docs/spec/pua-contract.toml`
- 新音素追加手順: `docs/guides/adding-pua-codepoint.md`
- CI gate: `.github/workflows/pua-consistency.yml`
- 配布前検証: `scripts/upload_model_to_hf.py` (config) / `scripts/check_onnx_inputs.py` (onnx)
