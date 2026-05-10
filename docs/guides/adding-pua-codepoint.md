# 新しい多コードポイント音素を PUA に登録する手順

新しい言語サポートや既存言語の音素拡張で **複数 Unicode コードポイントから成る音素** (例: `ɔɪ`, `œ̃`, `pʰ`, `t͡ʃ`) を扱う場合、PUA (Private Use Area) に単一コードポイントとして登録する必要があります。これは C++ runtime の `std::map<char32_t, ...>` 制約と、トレーニング済みモデルの `phoneme_id_map` 互換性の両方を満たすためです。

> **背景**: PR #389 で v1.12.0 の ɔɪ/œ̃/ɐ̃ leak (multi-codepoint key が `phoneme_id_map` に残り C++ inference が失敗) を修正した経緯。詳細は `docs/spec/pua-contract.toml` 参照。

## 全体フロー

```text
[1] pua.json 編集     ← canonical source
[2] 6 ランタイムのテーブル更新
[3] inventory に登録
[4] fixture 再生成
[5] PUA_COMPAT_VERSION bump (必要時)
[6] /check-pua で検証
[7] PR
```

## ステップ詳細

### 1. `src/python/g2p/piper_plus_g2p/data/pua.json` に entry 追加

```json
{
  "version": 2,
  "description": "...",
  "entries": [
    ...
    {
      "token": "ɔɪ",
      "codepoint": "0xE062",
      "language": "en",
      "description": "English diphthong (OY)"
    },
    ...
  ]
}
```

**codepoint の選び方**: `docs/spec/pua-contract.toml` の `[ranges]` セクションを見て、未割当の連続する空き範囲から取る。Examples:

- 既存最大 `0xE064` の次は `0xE065`
- 言語別ブロック (例: 韓国語拡張なら `0xE04B-E052` の次の空き) に詰めるのが好ましい

**禁則**:

- 既存 entry の codepoint は **絶対に変更しない** (トレーニング済みモデルが壊れる)
- 既存 entry を **削除しない** (古いモデルとの互換性)
- version は **下げない**

### 2. 6 ランタイムのテーブルを更新

`pua.json` を canonical として、以下を **byte-for-byte 一致** させる:

| ランタイム | ファイル |
|-----------|---------|
| Python (G2P) | `src/python/g2p/piper_plus_g2p/encode/pua.py` (`pua.json` を読むので自動) |
| Python (runtime) | `src/python_run/piper/phonemize/token_mapper.py` |
| Rust | `src/rust/piper-plus-g2p/src/token_map.rs` |
| Go | `src/go/phonemize/pua.go` |
| JS / WASM | `src/wasm/g2p/src/pua-map.js` |
| C# | `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` |
| C++ | `src/cpp/phoneme_parser.cpp` |

挿入位置は既存 entry の並び (codepoint 昇順) に合わせる。

### 3. Inventory に追加 (該当言語のみ)

新音素が `id_maps.py` の language inventory に出現するなら、追加:

```python
# src/python/g2p/piper_plus_g2p/encode/id_maps.py
_ENGLISH_PHONEMES = [
    ...,
    "ɔɪ",  # 追加
    ...,
]
```

これがないと `test_pua_invariants.py::test_inventory_multi_codepoint_tokens_have_pua_mapping` が PASS でも、actual ID map に key が出ないので意味がない。

### 4. テスト fixture を再生成

```bash
python scripts/regenerate_test_fixture.py
```

`tests/fixtures/g2p/phoneme_test_cases.json` の `pua_map` / `pua_map_count` が自動更新される。手動編集は禁止 (drift detection が落ちる)。

`pua_spot_checks` 配列に新 entry を追加するかは任意。代表的な entry なら追加すると便利。

### 5. `PUA_COMPAT_VERSION` を bump (必要時)

「**既存の学習済みモデルと挙動が変わる**」変更を加えた場合 (例: 古いモデルが受理しない新音素を追加) は version を bump:

- `src/python/g2p/piper_plus_g2p/data/pua.json` の `version`
- `src/python/g2p/piper_plus_g2p/encode/pua.py` の `PUA_COMPAT_VERSION`
- `src/wasm/g2p/src/pua-map.js` の `PUA_COMPAT_VERSION`
- `src/rust/piper-plus-g2p/src/token_map.rs` の `PUA_COMPAT_VERSION`
- `tests/fixtures/g2p/phoneme_test_cases.json` の `pua_compat_version`

「**既存モデルでも問題なく動く** (= 新音素は追加された言語専用で、既存モデルの inventory に出てこない)」場合は bump 不要。

### 6. ローカル検証

```text
/check-pua
```

または手動で:

```bash
# Cross-runtime
python scripts/check_pua_consistency.py --verbose --check-version

# Invariants
cd src/python/g2p && uv run pytest tests/test_pua_invariants.py -v

# Pre-flight
cd src/python && uv run pytest tests/test_update_model_config.py -v

# Fixture drift
python scripts/regenerate_test_fixture.py --check
```

### 7. PR

CI が:

- `PUA Consistency Gate` workflow (6 jobs: cross-runtime, inventory, fixture drift, Rust/Go/JS PUA tests, pre-flight)
- `cross-platform consistency` workflow (Python/Rust/Go/JS/C# 出力比較)
- 各ランタイムの個別 test suite

を全て pass するまでマージできない設計。

## チェックリスト (PR レビュー時)

- [ ] `pua.json` の codepoint が **既存 entry を変更/削除していない**
- [ ] 6 ランタイム全てのテーブルに同じ entry が追加されている
- [ ] `id_maps.py` の inventory に該当言語の entry が追加されている
- [ ] fixture が `regenerate_test_fixture.py` で再生成済み (手動編集していない)
- [ ] `PUA_COMPAT_VERSION` が必要に応じて bump されている (4 箇所すべて)
- [ ] CI の `PUA Consistency Gate` 全 6 jobs が green

## トラブルシューティング

### Q. C++ runtime が `phoneme_id_map` を読み込めない (multi-codepoint key 警告)

A. `pua.json` 登録漏れ。新 entry を `pua.json` に追加し、`update_model_config.py --validate-only` を通すこと (`scripts/upload_model_to_hf.py` 経由なら自動)。

### Q. fixture drift CI が失敗する

A. `python scripts/regenerate_test_fixture.py` を引数なしで実行して再生成、commit。

### Q. cross-runtime job だけ失敗する

A. `python scripts/check_pua_consistency.py --verbose` で差分を見て、該当ランタイムのテーブルを `pua.json` に揃える。

## 関連リソース

- 仕様: `docs/spec/pua-contract.toml`
- skill: `/check-pua` (`.claude/skills/check-pua/SKILL.md`)
- 配布パイプライン: `scripts/upload_model_to_hf.py`, `.github/workflows/release-model-config.yml`
- 既存 PR 例: #389 (v1.12.0 ɔɪ/œ̃/ɐ̃ leak 修正)
