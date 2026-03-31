# [P2-008] jpreprocess vs pyopenjtalk 互換性テスト

> Phase: 2 (Rust crate)
> マイルストーン: v0.1.0
> 対応要求: FR-203
> 依存チケット: P2-004
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
jpreprocess (Rust) と pyopenjtalk (Python) は同一の OpenJTalk アルゴリズムを異なる言語で再実装しているが、互換性は公式に保証されていない。共通テストフィクスチャで JA の phoneme 列が一致することを検証し、差異を文書化する。これにより、Python `piper-g2p` と Rust `piper-g2p` のユーザーが同じ入力に対して同じ (または予測可能に異なる) 出力を得られることを保証する。

### ゴール
- 共通テストフィクスチャ (`tests/fixtures/g2p/jpreprocess_compat.json`) に 10 件以上のテストケースが含まれる
- Rust 側テストで jpreprocess の出力がフィクスチャと一致する
- Python 側テスト (別リポジトリまたは CI ジョブ) で pyopenjtalk の出力がフィクスチャと一致する
- 既知の差異が `known_differences` セクションに文書化されている
- A1/A2/A3 prosody 値が同一テキストで +-1 以内の一致を示す

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 操作 | 内容 |
|---------|------|------|
| `src/rust/piper-g2p/tests/fixtures/g2p/jpreprocess_compat.json` | 新規 | テストフィクスチャ (10+ テストケース) |
| `src/rust/piper-g2p/tests/test_jpreprocess_compat.rs` | 新規 | Rust 互換性テスト |
| `src/python/piper_g2p/tests/test_jpreprocess_compat.py` | 新規 | Python 互換性テスト |
| `docs/design/jpreprocess-pyopenjtalk-compat.md` | 新規 | 差異の文書化 |

### 実装手順

1. **テストフィクスチャ作成**
   ```json
   {
     "version": "1.0",
     "description": "jpreprocess vs pyopenjtalk compatibility test fixtures",
     "test_cases": [
       {
         "id": "basic_hiragana",
         "input": "こんにちは",
         "expected_tokens": ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"],
         "expected_prosody": [
           {"a1": -3, "a2": 1, "a3": 5},
           {"a1": -3, "a2": 1, "a3": 5},
           {"a1": -2, "a2": 2, "a3": 5},
           {"a1": -2, "a2": 2, "a3": 5},
           {"a1": -1, "a2": 3, "a3": 5},
           {"a1": -1, "a2": 3, "a3": 5},
           {"a1": 0, "a2": 4, "a3": 5},
           {"a1": 1, "a2": 5, "a3": 5},
           {"a1": 1, "a2": 5, "a3": 5}
         ],
         "notes": null
       },
       {
         "id": "kanji_basic",
         "input": "東京都",
         "expected_tokens": "...",
         "notes": null
       },
       {
         "id": "katakana",
         "input": "コンピュータ",
         "expected_tokens": "...",
         "notes": null
       },
       {
         "id": "mixed_script",
         "input": "AIは人工知能です",
         "expected_tokens": "...",
         "notes": "数字・英字の読みで差異が生じやすい"
       },
       {
         "id": "n_variant_m",
         "input": "さんぽ",
         "expected_tokens": ["...", "N_m", "..."],
         "notes": "N_m: 両唇音前の「ん」"
       },
       {
         "id": "n_variant_n",
         "input": "あんない",
         "expected_tokens": ["...", "N_n", "..."],
         "notes": "N_n: 歯茎音前の「ん」"
       },
       {
         "id": "n_variant_ng",
         "input": "まんが",
         "expected_tokens": ["...", "N_ng", "..."],
         "notes": "N_ng: 軟口蓋音前の「ん」"
       },
       {
         "id": "n_variant_uvular",
         "input": "パン",
         "expected_tokens": ["...", "N_uvular"],
         "notes": "N_uvular: 語末の「ん」"
       },
       {
         "id": "question_generic",
         "input": "明日は晴れますか？",
         "expected_tokens": "...",
         "notes": "疑問詞マーカーの検証"
       },
       {
         "id": "long_sentence",
         "input": "吾輩は猫である。名前はまだ無い。",
         "expected_tokens": "...",
         "notes": "複数アクセント句のprosody検証"
       },
       {
         "id": "symbol_number",
         "input": "2024年3月31日",
         "expected_tokens": "...",
         "notes": "数字の読みは差異が生じやすい (KL-201)"
       },
       {
         "id": "punctuation",
         "input": "はい、そうです。",
         "expected_tokens": "...",
         "notes": "句読点のpau処理"
       }
     ],
     "known_differences": [
       {
         "id": "KD-001",
         "description": "記号の読みが異なる場合がある",
         "affected_test_ids": ["symbol_number"],
         "severity": "low"
       }
     ]
   }
   ```
   注: `expected_tokens` の `"..."` は実際の実装時に jpreprocess と pyopenjtalk の両方で生成し、一致するものを正解値として記録する。

2. **Rust テスト作成**
   ```rust
   // src/rust/piper-g2p/tests/test_jpreprocess_compat.rs

   #[cfg(feature = "naist-jdic")]
   mod compat_tests {
       use piper_g2p::japanese::JapanesePhonemizer;
       use piper_g2p::Phonemizer;
       use serde::Deserialize;

       #[derive(Deserialize)]
       struct CompatFixture {
           test_cases: Vec<TestCase>,
           known_differences: Vec<KnownDifference>,
       }

       #[derive(Deserialize)]
       struct TestCase {
           id: String,
           input: String,
           expected_tokens: Vec<String>,
           // prosody は Option (一致しない場合もある)
       }

       #[derive(Deserialize)]
       struct KnownDifference {
           id: String,
           affected_test_ids: Vec<String>,
       }

       fn load_fixture() -> CompatFixture {
           let json = include_str!("fixtures/g2p/jpreprocess_compat.json");
           serde_json::from_str(json).expect("fixture parse")
       }

       #[test]
       fn test_phoneme_compatibility() {
           let fixture = load_fixture();
           let phonemizer = JapanesePhonemizer::new().unwrap();
           let known_diff_ids: std::collections::HashSet<_> = fixture
               .known_differences
               .iter()
               .flat_map(|kd| kd.affected_test_ids.iter())
               .collect();

           for tc in &fixture.test_cases {
               let result = phonemizer.phonemize(&tc.input);
               if known_diff_ids.contains(&tc.id) {
                   // 既知の差異: 差異を記録するが fail しない
                   if let Ok(tokens) = &result {
                       if tokens != &tc.expected_tokens {
                           eprintln!("KNOWN DIFF [{}]: expected {:?}, got {:?}",
                                    tc.id, tc.expected_tokens, tokens);
                       }
                   }
               } else {
                   let tokens = result.unwrap();
                   assert_eq!(tokens, tc.expected_tokens,
                             "test case '{}' failed", tc.id);
               }
           }
       }
   }
   ```

3. **Python テスト作成**
   ```python
   # src/python/piper_g2p/tests/test_jpreprocess_compat.py

   import json
   import pytest
   from pathlib import Path

   FIXTURE_PATH = Path(__file__).parents[4] / "rust" / "piper-g2p" / "tests" / "fixtures" / "g2p" / "jpreprocess_compat.json"

   @pytest.fixture
   def fixture():
       with open(FIXTURE_PATH) as f:
           return json.load(f)

   @pytest.fixture
   def known_diff_ids(fixture):
       ids = set()
       for kd in fixture.get("known_differences", []):
           ids.update(kd.get("affected_test_ids", []))
       return ids

   def test_phoneme_compatibility(fixture, known_diff_ids):
       from piper_g2p import get_phonemizer
       phonemizer = get_phonemizer("ja")

       for tc in fixture["test_cases"]:
           tokens = phonemizer.phonemize(tc["input"])
           if tc["id"] in known_diff_ids:
               if tokens != tc["expected_tokens"]:
                   pytest.skip(f"Known difference: {tc['id']}")
           else:
               assert tokens == tc["expected_tokens"], f"test case '{tc['id']}' failed"
   ```

4. **差異文書の作成**
   テスト実行結果に基づいて `docs/design/jpreprocess-pyopenjtalk-compat.md` に以下を記録:
   - 一致するケースの一覧
   - 差異が発生するケースの詳細 (入力、期待値、実際値)
   - 差異の原因分析 (数字読み、記号処理、辞書エントリの差等)
   - 影響度評価 (TTS 出力音声への影響)

### API / インターフェース

テスト専用。公開 API への変更なし。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| Rust エンジニア | 1 | フィクスチャ作成、Rust テスト |
| Python エンジニア | 1 | Python テスト、差異文書化 |

---

## 4. テスト計画

### 提供範囲
jpreprocess (Rust) と pyopenjtalk (Python) の phoneme 出力互換性検証。

### Unit テスト
- 基本テキスト 10 件以上の phoneme トークン列一致
- N 音素変異 4 パターン (N_m, N_n, N_ng, N_uvular) の検証
- 韻律マーカー (`]`, `#`, `[`) の位置一致
- A1/A2/A3 prosody 値の +-1 以内一致

### E2E テスト
```bash
# Rust (naist-jdic 必要)
cargo test -p piper-g2p --features naist-jdic -- compat_tests

# Python
uv run pytest src/python/piper_g2p/tests/test_jpreprocess_compat.py
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **既知制限 KL-201**: jpreprocess と pyopenjtalk で fullcontext label の細部が異なる可能性がある。特に数字の読み (「2024年」が「にせんにじゅうよねん」vs「にーぜろにーよんねん」)、英字の読み、記号の処理で差異が生じやすい。これらは `known_differences` として文書化し、テストでは xfail/skip 扱いにする。
- **jpreprocess のバージョン差**: jpreprocess 0.9 と将来の 0.13.x で出力が変わる可能性がある。フィクスチャのバージョンをメタデータに記録する。
- **フィクスチャの正解値決定方法**: 両方の実装で出力が一致するテキストを正解値として採用する。一致しないテキストは `known_differences` に分類する。

### レビュー項目
- テストフィクスチャが最低 10 件のテストケースを含むこと
- N 音素変異 4 パターンが全て含まれること
- `known_differences` が合理的な理由で分類されていること
- A1/A2/A3 の許容誤差 (+-1) が妥当であること

---

## 6. 一から作り直すとしたら

- フィクスチャを JSON ではなく TOML にして Rust との親和性を高める案。ただし Python 側でも読む必要があるため、JSON が汎用性が高い。
- pyopenjtalk と jpreprocess の両方を CI で実行して自動的にフィクスチャを更新するスクリプトを作成する案。メンテナンスコストは下がるが、「何が正解か」の判断が自動化できないため、手動フィクスチャが現実的。

---

## 7. 後続タスクへの連絡事項

- **P2-009**: CI ワークフローに jpreprocess 互換性テストジョブを追加する。`--features naist-jdic` が必要 (辞書バンドル)。
- **P2-010**: v1.0.0 リリースまでに `known_differences` の件数を最小化する。重大な差異がある場合は jpreprocess の upstream に issue を立てる。
- **Phase 1 Python チーム**: 同一フィクスチャを Python テストでも使用する。フィクスチャのパスは `src/rust/piper-g2p/tests/fixtures/g2p/` に配置し、Python テストからは相対パスで参照する。将来的にフィクスチャをリポジトリルートの `tests/fixtures/g2p/` に移動することを検討する。
