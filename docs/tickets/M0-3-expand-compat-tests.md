# M0-3: 互換テスト拡充 (全8言語 + マルチリンガル ID マップ)

> **マイルストーン**: M0
> **前提チケット**: なし
> **後続チケット**: なし (全 M1/M2/M3 タスクのリグレッション安全網)
> **見積り**: 中
> **リスク**: 低

## タスク目的とゴール

`src/python/g2p/tests/test_compat.py` には現在 4 件のテスト (JA トークン, PUA マッピング, JA ID マップ, EN 出力) しかない。
`piper_plus_g2p` が `piper_train` と同一出力を生成することを保証するため、残りの 6 言語 (ZH/KO/ES/FR/PT/SV) の音素化出力テストと、マルチリンガル ID マップの一致テストを追加する。

**ゴール**: 8 言語全ての `phonemize()` 出力と `phonemize_with_prosody()` 出力が `piper_train` と一致することをテストで保証する。マルチリンガル ID マップも一致することを確認する。後続のリファクタリングタスク全てが、このテストスイートをリグレッション安全網として使える状態。

## 実装する内容の詳細

### 変更箇所

**ファイル**: `src/python/g2p/tests/test_compat.py`

### 追加するテストクラスとメソッド

#### 1. ZH (中国語) 互換テスト

```python
@requires_zh
@requires_piper_train
class TestZHCompat:
    def test_zh_phonemize_matches(self):
        """piper_plus_g2p ZH output == piper_train phonemize_chinese()"""
        from piper_train.phonemize.chinese import phonemize_chinese
        from piper_plus_g2p.chinese import ChinesePhonemizer
        text = "你好，今天天气很好。"
        p = ChinesePhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_chinese(text)
        assert g2p_tokens == train_tokens

    def test_zh_phonemize_with_prosody_matches(self):
        """piper_plus_g2p ZH prosody output == piper_train phonemize_chinese_with_prosody()"""
        from piper_train.phonemize.chinese import phonemize_chinese_with_prosody
        from piper_plus_g2p.chinese import ChinesePhonemizer
        text = "你好，今天天气很好。"
        p = ChinesePhonemizer()
        g2p_tokens, g2p_prosody = p.phonemize_with_prosody(text)
        train_tokens, train_prosody = phonemize_chinese_with_prosody(text)
        assert g2p_tokens == train_tokens
```

#### 1a. JA (日本語) prosody 値比較テスト

```python
@requires_ja
@requires_piper_train
class TestJAProsodyCompat:
    def test_ja_prosody_a1_a2_a3_matches(self):
        """piper_plus_g2p JA prosody (a1/a2/a3) == piper_train phonemize_japanese_with_prosody()"""
        from piper_train.phonemize.japanese import phonemize_japanese_with_prosody
        from piper_plus_g2p.japanese import JapanesePhonemizer
        text = "今日は良い天気ですね。"
        p = JapanesePhonemizer()
        g2p_tokens, g2p_prosody = p.phonemize_with_prosody(text)
        train_tokens, train_prosody = phonemize_japanese_with_prosody(text)
        assert g2p_tokens == train_tokens
        # ProsodyInfo の a1/a2/a3 値が一致することを個別に検証
        assert len(g2p_prosody) == len(train_prosody)
        for i, (g, t) in enumerate(zip(g2p_prosody, train_prosody)):
            if g is None and t is None:
                continue
            assert g is not None and t is not None, (
                f"Prosody mismatch at index {i}: g2p={g}, train={t}"
            )
            assert g.a1 == t.a1, f"a1 mismatch at index {i}: {g.a1} != {t.a1}"
            assert g.a2 == t.a2, f"a2 mismatch at index {i}: {g.a2} != {t.a2}"
            assert g.a3 == t.a3, f"a3 mismatch at index {i}: {g.a3} != {t.a3}"
```

#### 2. KO (韓国語) 互換テスト

```python
@requires_ko
@requires_piper_train
class TestKOCompat:
    def test_ko_phonemize_matches(self):
        from piper_train.phonemize.korean import phonemize_korean
        from piper_plus_g2p.korean import KoreanPhonemizer
        text = "안녕하세요"
        p = KoreanPhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_korean(text)
        assert g2p_tokens == train_tokens
```

#### 3. ES (スペイン語) 互換テスト

```python
@requires_piper_train
class TestESCompat:
    def test_es_phonemize_matches(self):
        from piper_train.phonemize.spanish import phonemize_spanish
        from piper_plus_g2p.spanish import SpanishPhonemizer
        text = "Hola, ¿cómo estás hoy?"
        p = SpanishPhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_spanish(text)
        assert g2p_tokens == train_tokens
```

#### 4. FR (フランス語) 互換テスト

```python
@requires_piper_train
class TestFRCompat:
    def test_fr_phonemize_matches(self):
        from piper_train.phonemize.french import phonemize_french
        from piper_plus_g2p.french import FrenchPhonemizer
        text = "Bonjour, comment allez-vous?"
        p = FrenchPhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_french(text)
        assert g2p_tokens == train_tokens
```

#### 5. PT (ポルトガル語) 互換テスト

```python
@requires_piper_train
class TestPTCompat:
    def test_pt_phonemize_matches(self):
        from piper_train.phonemize.portuguese import phonemize_portuguese
        from piper_plus_g2p.portuguese import PortuguesePhonemizer
        text = "Olá, como você está hoje?"
        p = PortuguesePhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_portuguese(text)
        assert g2p_tokens == train_tokens
```

#### 6. SV (スウェーデン語) 互換テスト

```python
@requires_piper_train
class TestSVCompat:
    def test_sv_phonemize_matches(self):
        from piper_train.phonemize.swedish import phonemize_swedish
        from piper_plus_g2p.swedish import SwedishPhonemizer
        text = "Hej, hur mår du idag?"
        p = SwedishPhonemizer()
        g2p_tokens = p.phonemize(text)
        train_tokens = phonemize_swedish(text)
        assert g2p_tokens == train_tokens
```

#### 7. マルチリンガル ID マップ一致テスト

```python
@requires_piper_train
class TestMultilingualIDMapCompat:
    def test_multilingual_id_map_matches(self):
        """piper_plus_g2p get_phoneme_id_map('multilingual') ==
        piper_train get_multilingual_id_map(all_langs)"""
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        train_map = get_multilingual_id_map(["ja", "en", "zh", "es", "fr", "pt", "sv", "ko"])
        g2p_map = get_phoneme_id_map("multilingual")
        assert g2p_map == train_map

    def test_6lang_id_map_matches(self):
        """6言語サブセットの ID マップが一致"""
        from piper_train.phonemize.multilingual_id_map import get_multilingual_id_map
        from piper_plus_g2p.encode.id_maps import get_phoneme_id_map
        train_map = get_multilingual_id_map(["ja", "en", "zh", "es", "fr", "pt"])
        # piper_plus_g2p 側の 6lang サブセット取得方法に応じて修正
        g2p_map = get_phoneme_id_map("ja-en-zh-es-fr-pt")
        assert g2p_map == train_map
```

### import 追加

`conftest.py` から `requires_zh`, `requires_ko` を import に追加:

```python
from tests.conftest import requires_en, requires_ja, requires_zh, requires_ko
```

ES/FR/PT/SV はネイティブ Python 規則ベースのため `requires_*` マーカー不要。

## エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|---|---|---|
| テスト作成者 | 1 | 6言語互換テスト + マルチリンガル ID マップテスト作成 |
| レビュアー | 1 | テストカバレッジ確認、piper_train import パスの正確性確認 |

## 提供範囲とテスト

### 提供範囲

- `src/python/g2p/tests/test_compat.py` に以下を追加:
  - ZH/KO/ES/FR/PT/SV の `phonemize()` 出力一致テスト (各1件、計6件)
  - ZH の `phonemize_with_prosody()` 出力一致テスト (1件)
  - JA の prosody 値 (a1/a2/a3) 一致テスト (1件)
  - マルチリンガル ID マップ一致テスト (2件: 8言語全体 + 6言語サブセット)
- 合計 **10 件** のテスト追加 (既存4件 + 新規10件 = 14件)

### テスト項目

1. 各言語の `phonemize()` 出力が piper_train と完全一致すること
2. ZH の prosody 出力が piper_train と一致すること
3. JA の prosody 出力 (ProsodyInfo の a1/a2/a3 値) が piper_train と完全一致すること
4. マルチリンガル ID マップ (8言語) が piper_train と一致すること
5. 6言語サブセット ID マップが piper_train と一致すること
6. 依存ライブラリ未インストール時にテストが適切にスキップされること

### Unit テスト

このチケット自体がテスト作成チケットであり、上記の全テストがユニットテストに該当する。

### E2E テスト

追加のE2Eテストは不要。各言語テストが `piper_train` と `piper_plus_g2p` の両方を import して出力を比較すること自体がE2Eテストとして機能する。

## 懸念事項とレビュー項目

### 懸念事項

- **意図的な差異**: `piper_plus_g2p` で改善された言語処理がある場合、`piper_train` との出力が意図的に異なることがある。その場合はテスト内にコメントで理由を記載し、差異を許容するテスト設計にする
- **piper_train の import パス**: 各言語の `phonemize_*` 関数の import パスが正しいか確認する必要がある。特に `phonemize_chinese()` vs `phonemize_chinese_with_prosody()` の戻り値形式が異なる可能性がある (piper_train は PUA マッピング済みトークンを返すが、piper_plus_g2p は raw IPA を返す)
- **piper_train 側の phonemize 関数パスは実装時に要確認**: テスト例で使用している `from piper_train.phonemize.chinese import phonemize_chinese` 等の import パスは、piper_train 側のモジュール構造が異なる可能性がある (例: 関数名が `phonemize()` のみ、モジュールパスが `piper_train.phonemize.chinese` ではなく別の構成等)。実装時に `piper_train` の実際のエクスポート構造を確認し、import パスを修正すること
- **PUA マッピングの扱い**: JA テスト (`test_ja_tokens_ipa_to_pua`) と同様に、他言語でも PUA マッピング変換後に比較する必要がある可能性がある。各言語で piper_train がどの形式で出力するかを事前に確認すること
- **KO (g2pk2) の CI 環境**: g2pk2 は大きな依存 (MeCab + 韓国語辞書) を持つため、CI 環境で利用できない可能性がある。`requires_ko` マーカーで適切にスキップされる

### レビュー項目

- [ ] 各言語テストで使用するテスト文が適切であること (特殊文字、疑問文、数字等を含む)
- [ ] piper_train 関数の import パスが正しいこと
- [ ] PUA マッピングの適用有無が言語ごとに正しいこと
- [ ] skip マーカーが適切に設定されていること (ZH: requires_zh, KO: requires_ko, 他: なし)
- [ ] CI (GitHub Actions) で piper_train がインストールされていない環境でテストがスキップされること

## 一から作り直すとしたら

各言語テストをパラメタライズドテスト (`@pytest.mark.parametrize`) で実装し、テスト文のリストを言語ごとに定義する形式にする。これにより、テスト文の追加が容易になり、言語間のテスト構造が統一される。

```python
@pytest.mark.parametrize("lang,text,train_func,g2p_class", [
    ("ja", "こんにちは", phonemize_japanese, JapanesePhonemizer),
    ("en", "Hello", phonemize_english, EnglishPhonemizer),
    ...
])
def test_phonemize_compat(lang, text, train_func, g2p_class):
    ...
```

## 後続タスクへの連絡事項

- M1/M2/M3 の全タスクは、このテストスイートをリグレッション安全網として使用する
- テスト実行時に「意図的な差異」が見つかった場合、その言語と内容をチケット完了時に記載すること
- PUA マッピングの適用パターン (JA のみ必要 vs 全言語で必要) をチケット完了時に記載し、後続タスクがテスト設計を参照できるようにすること
