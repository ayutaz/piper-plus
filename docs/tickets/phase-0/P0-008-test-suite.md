# [P0-008] テストスイート

> Phase: 0 (MVP)
> マイルストーン: v0.1.0 -- Python MVP (JA+EN)
> 対応要求: NFR-001
> 依存チケット: P0-004, P0-005, P0-006, P0-007
> ステータス: TODO

---

## 1. 目的とゴール

### 目的
Phase 0 のスコープ (JA + EN + encode + 互換シム) に対して十分なテストカバレッジを確保する。`piper_g2p` パッケージの品質を保証し、後続フェーズでのリグレッションを防止する。

### ゴール
- JA: 10+ テストケース (音素化、N 変異 4 パターン、疑問詞マーカー 4 パターン、韻律記号)
- EN: 6+ テストケース (音素化、ストレスマーカー、機能語ストレス除去)
- encode: 8+ テストケース (PUA 変換、BOS/EOS 挿入、パディング、ID マップ変換)
- 互換シム: 4+ テストケース
- カバレッジ 90%+ (コア + JA + EN + encode)
- `uv run pytest` で全テストが実行できる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/tests/__init__.py` | テストパッケージ |
| `src/python/g2p/tests/test_base.py` | Phonemizer ABC, ProsodyInfo のテスト |
| `src/python/g2p/tests/test_registry.py` | レジストリのテスト |
| `src/python/g2p/tests/test_japanese.py` | JapanesePhonemizer のテスト (10+) |
| `src/python/g2p/tests/test_english.py` | EnglishPhonemizer のテスト (6+) |
| `src/python/g2p/tests/test_encode.py` | PiperEncoder, PUA, ID マップのテスト (8+) |
| `src/python/g2p/tests/test_compat.py` | piper_train 互換シムのテスト (4+) |
| `src/python/g2p/tests/conftest.py` | 共通フィクスチャ (JA/EN 依存チェック等) |
| `src/python/g2p/pyproject.toml` | `[tool.pytest.ini_options]` セクション追加 |

### 実装手順

1. **conftest.py の作成**

   ```python
   # tests/conftest.py
   import pytest

   def _has_pyopenjtalk():
       try:
           import pyopenjtalk_plus  # noqa: F401
           return True
       except ImportError:
           try:
               import pyopenjtalk  # noqa: F401
               return True
           except ImportError:
               return False

   def _has_g2p_en():
       try:
           from g2p_en import G2p  # noqa: F401
           return True
       except ImportError:
           return False

   requires_ja = pytest.mark.skipif(
       not _has_pyopenjtalk(), reason="pyopenjtalk not installed"
   )
   requires_en = pytest.mark.skipif(
       not _has_g2p_en(), reason="g2p-en not installed"
   )
   ```

2. **test_base.py** (P0-003 チケットのテスト計画に対応)

3. **test_registry.py** (P0-003 チケットのテスト計画に対応)

4. **test_japanese.py** (10+ ケース)

   ```python
   # tests/test_japanese.py
   import pytest
   from tests.conftest import requires_ja

   @requires_ja
   class TestJapanesePhonemizerBasic:
       def test_basic_phonemize(self):
           from piper_g2p import get_phonemizer
           ja = get_phonemizer("ja")
           tokens = ja.phonemize("こんにちは")
           assert isinstance(tokens, list)
           assert len(tokens) > 0
           assert "^" not in tokens
           assert "$" not in tokens

       def test_no_pua_characters(self):
           from piper_g2p import get_phonemizer
           ja = get_phonemizer("ja")
           tokens = ja.phonemize("テスト文です。")
           for token in tokens:
               for ch in token:
                   assert not (0xE000 <= ord(ch) <= 0xF8FF)

       def test_prosody_symbols(self):
           from piper_g2p import get_phonemizer
           ja = get_phonemizer("ja")
           tokens = ja.phonemize("今日は良い天気ですね。")
           assert any(t in {"#", "[", "]"} for t in tokens)

   @requires_ja
   class TestNPhonemeVariants:
       def test_n_bilabial(self):
           """N + m/b/p -> N_m (新聞: しんぶん)"""
           from piper_g2p import get_phonemizer
           tokens = get_phonemizer("ja").phonemize("新聞")
           assert "N_m" in tokens

       def test_n_alveolar(self):
           """N + n/t/d -> N_n (こんにちは)"""
           from piper_g2p import get_phonemizer
           tokens = get_phonemizer("ja").phonemize("こんにちは")
           assert "N_n" in tokens

       def test_n_velar(self):
           """N + k/g -> N_ng (文化: ぶんか)"""
           from piper_g2p import get_phonemizer
           tokens = get_phonemizer("ja").phonemize("文化")
           assert "N_ng" in tokens

       def test_n_uvular(self):
           """語末の N -> N_uvular (本: ほん)"""
           from piper_g2p import get_phonemizer
           tokens = get_phonemizer("ja").phonemize("本")
           assert "N_uvular" in tokens

   @requires_ja
   class TestQuestionMarkers:
       def test_generic_question(self):
           tokens = get_phonemizer("ja").phonemize("何？")
           assert "?" in tokens

       def test_emphatic_question(self):
           tokens = get_phonemizer("ja").phonemize("何？！")
           assert "?!" in tokens

       def test_neutral_question(self):
           tokens = get_phonemizer("ja").phonemize("何。？")
           assert "?." in tokens

       def test_tag_question(self):
           tokens = get_phonemizer("ja").phonemize("何～？")
           assert "?~" in tokens

   @requires_ja
   class TestJapaneseProsody:
       def test_prosody_length_matches(self):
           from piper_g2p import get_phonemizer
           ja = get_phonemizer("ja")
           tokens, prosody = ja.phonemize_with_prosody("こんにちは")
           assert len(tokens) == len(prosody)

       def test_prosody_has_values(self):
           from piper_g2p import get_phonemizer, ProsodyInfo
           ja = get_phonemizer("ja")
           _, prosody = ja.phonemize_with_prosody("こんにちは")
           non_none = [p for p in prosody if p is not None]
           assert len(non_none) > 0
           assert all(isinstance(p, ProsodyInfo) for p in non_none)
   ```

5. **test_english.py** (6+ ケース)

   ```python
   # tests/test_english.py
   @requires_en
   class TestEnglishPhonemizerBasic:
       def test_basic_phonemize(self):
           tokens = get_phonemizer("en").phonemize("Hello")
           assert isinstance(tokens, list)
           assert len(tokens) > 0

       def test_word_boundary(self):
           tokens = get_phonemizer("en").phonemize("Hello world")
           assert " " in tokens

   @requires_en
   class TestStressMarkers:
       def test_primary_stress(self):
           tokens = get_phonemizer("en").phonemize("happy")
           assert "ˈ" in tokens

       def test_secondary_stress(self):
           tokens = get_phonemizer("en").phonemize("multiplication")
           assert "ˌ" in tokens

   @requires_en
   class TestFunctionWords:
       def test_function_word_no_stress(self):
           _, prosody = get_phonemizer("en").phonemize_with_prosody("the cat")
           assert prosody[0].a2 == 0  # "the" はストレスなし

       def test_prosody_a1_zero(self):
           _, prosody = get_phonemizer("en").phonemize_with_prosody("Hello")
           for p in prosody:
               if p is not None:
                   assert p.a1 == 0
   ```

6. **test_encode.py** (8+ ケース) -- P0-006 のテスト計画参照

7. **test_compat.py** (4+ ケース) -- P0-007 のテスト計画参照

8. **pyproject.toml にテスト設定追加**

   ```toml
   [tool.pytest.ini_options]
   testpaths = ["tests"]

   [project.optional-dependencies]
   dev = [
       "pytest>=8.0",
       "pytest-cov>=5.0",
       "ruff>=0.8.0",
       "mypy>=1.13",
   ]
   ```

### API / インターフェース

なし (テストコードのみ)。

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| テスト実装 | 1 | 全テストファイルの作成 |
| カバレッジ検証 | 1 | pytest-cov による 90%+ カバレッジ確認 |

---

## 4. テスト計画

### 提供範囲

| モジュール | テスト数 | カバレッジ目標 |
|-----------|---------|-------------|
| base.py | 4 | 100% |
| registry.py | 4 | 95%+ |
| japanese.py | 12 | 90%+ |
| english.py | 7 | 90%+ |
| encode/ | 10 | 90%+ |
| 互換シム | 4 | 80%+ |
| **合計** | **41+** | **90%+** |

### Unit テスト

各チケットのテスト計画セクションに記載されたテストケースを統合して実装する。

### E2E テスト

```python
# test_e2e.py

@requires_ja
def test_ja_text_to_ids():
    """日本語: テキスト -> phonemize -> encode -> phoneme_ids。"""
    ja = get_phonemizer("ja")
    tokens = ja.phonemize("テスト")
    from piper_g2p.encode import PiperEncoder, get_phoneme_id_map
    encoder = PiperEncoder(get_phoneme_id_map("ja"))
    ids = encoder.encode(tokens)
    assert all(isinstance(i, int) for i in ids)
    assert ids[0] != 0  # BOS は pad (0) ではない

@requires_en
def test_en_text_to_ids():
    """英語: テキスト -> phonemize -> encode -> phoneme_ids。"""
    en = get_phonemizer("en")
    tokens = en.phonemize("Hello")
    from piper_g2p.encode import PiperEncoder, get_phoneme_id_map
    encoder = PiperEncoder(get_phoneme_id_map("en"))
    ids = encoder.encode(tokens)
    assert all(isinstance(i, int) for i in ids)

@requires_ja
def test_ja_prosody_pipeline():
    """日本語: prosody 付き全パイプライン。"""
    ja = get_phonemizer("ja")
    tokens, prosody = ja.phonemize_with_prosody("こんにちは")
    from piper_g2p.encode import PiperEncoder, get_phoneme_id_map
    encoder = PiperEncoder(get_phoneme_id_map("ja"))
    ids, features = encoder.encode_with_prosody(tokens, prosody)
    assert len(ids) == len(features)
```

### カバレッジ実行

```bash
cd src/python/g2p
uv run pytest --cov=piper_g2p --cov-report=term-missing --cov-fail-under=90
```

---

## 5. 懸念事項とレビュー項目

### 懸念事項
- **pyopenjtalk のテスト環境**: CI 環境 (特に Windows / macOS ARM) で pyopenjtalk のインストールが失敗する可能性がある。`requires_ja` マーカーでスキップする仕組みを用意するが、カバレッジ計測に影響する。
- **g2p-en のバージョン差**: g2p-en のバージョンによって出力が微妙に異なる場合がある。テストケースは出力の構造 (トークン列の型、長さ > 0、特定トークンの存在) を検証し、完全一致は避ける。
- **互換シムテストの scope**: `piper_train` のテスト (`tests/`) は `piper_g2p` パッケージの外にある。`test_compat.py` は `piper_g2p` のテストディレクトリに置くが、`piper_train` のインストールが必要。CI で両方をインストールする設定が必要。

### レビュー項目
- テストケースが各チケットの受入条件を網羅していること
- `requires_ja` / `requires_en` マーカーが正しく機能していること
- テストの独立性 (テスト間の順序依存がないこと)
- カバレッジ 90% 以上を達成していること

---

## 6. 一から作り直すとしたら

- **スナップショットテスト**: 各テキスト入力に対する期待出力を JSON ファイルとして保存し、`pytest-snapshot` で比較する方式。テストケースの追加が容易で、出力変更時の差分も分かりやすい。ただし pyopenjtalk / g2p-en のバージョン更新で大量のスナップショット更新が発生するリスクがある。
- **property-based testing (Hypothesis)**: `hypothesis` ライブラリで「任意の日本語テキストに対して `phonemize()` が PUA 文字を含まない」「`len(tokens) == len(prosody)`」等のプロパティをテストする。エッジケースの発見に有効だが、pyopenjtalk の処理時間が長く、テスト実行時間が増加する。
- **テストを piper_g2p パッケージ外に置く**: `tests/` をリポジトリルートに置き、`piper_g2p` と `piper_train` の両方のテストを統合する。パッケージのリリースには含まれないが、CI では一括実行できる。

---

## 7. 後続タスクへの連絡事項

- **P0-009 (CI)**: テストの実行コマンドは `cd src/python/g2p && uv run pytest`。CI ワークフローでこのコマンドを 3 OS x 2 Python で実行すること。`--cov-fail-under=90` をCI でも有効化する。
- **Phase 1**: 残り 5 言語 (ZH, KO, ES, PT, FR) のテストを追加する。各言語 6+ ケース。`conftest.py` に `requires_zh`, `requires_ko` 等のマーカーを追加する。ES/PT/FR はルールベースなので外部依存なく常に実行可能。
- **Phase 1**: `MultilingualPhonemizer` のテスト (言語自動検出、複合コード) を追加する。
