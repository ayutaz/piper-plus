# P1-010: テストフィクスチャ + 言語テスト

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: NFR-100
> 依存チケット: P1-001 ~ P1-005 (全言語 Phonemizer)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージの全 7 言語について、共通テストフィクスチャを JSON 形式で提供し、言語間で一貫したテスト構造を実現する。各テストケースは入力テキストと期待される IPA 出力のペアを含み、回帰テストの基盤とする。

### ゴール

- `tests/fixtures/g2p/phoneme_test_cases.json` に 7 言語 x 2+ テストケースを含む共通フィクスチャが存在する
- 各言語の Phonemizer に対するパラメタライズドテストが動作する
- フィクスチャの追加だけで新しいテストケースを追加できる (コード変更不要)
- 全テストケースの期待出力が IPA-first (PUA なし、BOS/EOS なし) であること

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/tests/fixtures/g2p/phoneme_test_cases.json` | 共通テストフィクスチャ |
| `src/python/g2p/tests/test_phoneme_fixtures.py` | フィクスチャ駆動テスト |
| `src/python/g2p/tests/conftest.py` | pytest フィクスチャロード |

### 実装手順

1. テストフィクスチャ JSON を設計:

```json
{
  "version": "1.0",
  "description": "piper-g2p phoneme test cases for all languages",
  "test_cases": {
    "ja": [
      {
        "id": "ja-001",
        "input": "こんにちは",
        "expected_tokens": ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"],
        "description": "Basic Japanese greeting"
      },
      {
        "id": "ja-002",
        "input": "東京タワー",
        "expected_contains": ["t", "o"],
        "description": "Katakana + Kanji mix"
      }
    ],
    "en": [
      {
        "id": "en-001",
        "input": "Hello",
        "expected_contains": ["h", "l", "oʊ"],
        "description": "Basic English greeting"
      },
      {
        "id": "en-002",
        "input": "world",
        "expected_contains": ["w", "l", "d"],
        "description": "Common English word"
      }
    ],
    "zh": [
      {
        "id": "zh-001",
        "input": "你好",
        "expected_contains": ["tone2", "tone3"],
        "description": "T3 sandhi: ni3hao3 -> ni2hao3"
      },
      {
        "id": "zh-002",
        "input": "一定",
        "expected_contains": ["tone2"],
        "description": "Yi sandhi: yi1ding4 -> yi2ding4"
      }
    ],
    "ko": [
      {
        "id": "ko-001",
        "input": "안녕",
        "expected_contains": ["a", "n"],
        "description": "Basic Korean greeting"
      },
      {
        "id": "ko-002",
        "input": "감사합니다",
        "expected_contains": ["k", "a", "m"],
        "description": "Common Korean phrase"
      }
    ],
    "es": [
      {
        "id": "es-001",
        "input": "hola",
        "expected_tokens": ["ˈ", "o", "l", "a"],
        "description": "Basic Spanish greeting"
      },
      {
        "id": "es-002",
        "input": "cerveza",
        "expected_contains": ["s"],
        "expected_not_contains": ["θ"],
        "description": "Seseo: c before e -> s"
      }
    ],
    "fr": [
      {
        "id": "fr-001",
        "input": "bonjour",
        "expected_contains": ["b", "ɔ̃", "ʒ", "u", "ʁ"],
        "description": "Basic French greeting with nasal vowel"
      },
      {
        "id": "fr-002",
        "input": "maison",
        "expected_contains": ["z"],
        "description": "Intervocalic s -> z"
      }
    ],
    "pt": [
      {
        "id": "pt-001",
        "input": "Brasil",
        "expected_contains": ["w"],
        "description": "Coda-l vocalization"
      },
      {
        "id": "pt-002",
        "input": "cidade",
        "expected_contains": ["dʒ"],
        "description": "d palatalization before i"
      }
    ]
  }
}
```

2. テストランナーを実装:

```python
# tests/test_phoneme_fixtures.py
import json
import pytest
from pathlib import Path
from piper_g2p import get_phonemizer, available_languages

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "g2p" / "phoneme_test_cases.json"

def load_test_cases():
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    cases = []
    for lang, tests in data["test_cases"].items():
        for tc in tests:
            cases.append((lang, tc))
    return cases

@pytest.mark.parametrize("lang,tc", load_test_cases(), ids=lambda x: x["id"] if isinstance(x, dict) else x)
def test_phoneme_output(lang, tc):
    if lang not in available_languages():
        pytest.skip(f"Language {lang} not available")

    phonemizer = get_phonemizer(lang)
    tokens = phonemizer.phonemize(tc["input"])

    # PUA check
    for token in tokens:
        for ch in token:
            assert ord(ch) < 0xE000 or ord(ch) > 0xF8FF, \
                f"PUA character found: {ch!r} in token {token!r}"

    # BOS/EOS check
    assert "^" not in tokens, "BOS token found"
    assert "$" not in tokens, "EOS token found"

    # Expected tokens (exact match)
    if "expected_tokens" in tc:
        assert tokens == tc["expected_tokens"], \
            f"[{tc['id']}] Expected {tc['expected_tokens']}, got {tokens}"

    # Expected contains (partial match)
    if "expected_contains" in tc:
        for expected in tc["expected_contains"]:
            assert expected in tokens, \
                f"[{tc['id']}] Expected token {expected!r} not found in {tokens}"

    # Expected not contains
    if "expected_not_contains" in tc:
        for unexpected in tc["expected_not_contains"]:
            assert unexpected not in tokens, \
                f"[{tc['id']}] Unexpected token {unexpected!r} found in {tokens}"
```

3. `conftest.py` に共通フィクスチャを定義:

```python
# tests/conftest.py
import pytest
from piper_g2p import available_languages

@pytest.fixture
def all_languages():
    return available_languages()
```

4. 各言語の個別テストファイル (`test_chinese.py`, `test_korean.py` 等) も作成 (P1-001〜P1-005 の各チケットで定義済み)

### API / インターフェース

該当なし (テストインフラのみ)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テストエージェント | 1 | フィクスチャ JSON 作成、テストランナー実装 |
| レビューエージェント | 1 | 期待出力の正確性検証 (各言語の IPA が正しいか) |

---

## 4. テスト計画

### 提供範囲

フィクスチャ駆動テストの基盤が動作し、全 7 言語の基本テストケースが pass すること。

### Unit テスト

| テストケース | 検証内容 |
|-------------|---------|
| フィクスチャロード | JSON が正しくパースされること |
| パラメタライズ | 全テストケースが pytest パラメータとして展開されること |
| PUA チェック | 全言語の出力に PUA 文字が含まれないこと |
| BOS/EOS チェック | 全言語の出力に `"^"` / `"$"` が含まれないこと |
| expected_tokens | 完全一致テストケースが pass すること |
| expected_contains | 部分一致テストケースが pass すること |
| expected_not_contains | 否定テストケースが pass すること |
| 未インストール言語 | skip されること |

### E2E テスト

- `uv run pytest tests/test_phoneme_fixtures.py` が全テストケースを実行すること
- `uv run pytest tests/test_phoneme_fixtures.py -k "ja"` で日本語のみ実行できること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **期待出力の正確性**: 各言語の IPA 出力は言語学的に正確である必要がある。特に ZH の声調サンドヒ結果と FR の鼻母音出力はエッジケースが多い。初期リリースでは `expected_contains` (部分一致) を多用し、完全一致テストは安定したケースのみとする。
- **フィクスチャの肥大化**: 将来的にテストケースが増加した場合、単一 JSON ファイルが大きくなる。言語別ファイル分割 (e.g., `test_cases_ja.json`) への移行を Phase 2 以降で検討する。
- **g2pk2 依存テスト**: KO のテストケースは g2pk2 の有無で出力が変わる。フィクスチャでは g2pk2 ありの出力を期待値とし、g2pk2 なし環境では skip する。

### レビュー項目

- [ ] 全 7 言語にそれぞれ 2+ テストケースが存在すること
- [ ] 全テストケースの期待出力が IPA-first であること (PUA なし、BOS/EOS なし)
- [ ] フィクスチャ JSON のスキーマが一貫していること
- [ ] パラメタライズドテストが全ケースで動作すること
- [ ] 未インストール言語が skip されること

---

## 6. 一から作り直すとしたら

フィクスチャ形式を JSON ではなく YAML にして可読性を向上させる。また各テストケースに「この出力が正しい根拠」(e.g., IPA Handbook のページ番号、Wiktionary URL) を添付するメタデータフィールドを追加する。

---

## 7. 後続タスクへの連絡事項

- P1-009 (ドキュメント): フィクスチャ内の入出力例をドキュメントの IPA 出力例として参照できる
- P1-011 (API 凍結): v1.0.0 リリース前にフィクスチャの期待出力を再検証する
- CI: `g2p-python-ci.yml` でフィクスチャテストを自動実行する
- Rust/C#: 同一のフィクスチャ JSON を Rust/C# のテストでも共有できる (クロスランタイム一貫性)
