# P1-003: SpanishPhonemizer (ルールベース)

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-100
> 依存チケット: P0-003 (コア抽象)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージにスペイン語の G2P 機能を追加する。外部依存なしのルールベース実装で、スペイン語の正書法規則に基づいて IPA トークン列を返す。ラテンアメリカ発音 (seseo) をデフォルトとする。

### ゴール

- `get_phonemizer("es").phonemize("Hola mundo")` が IPA トークン列を返す
- ストレスマーカー (`"ˈ"`) が正しい音節に挿入される
- 異音規則 (b/d/g の fricative allophony) が適用される
- 外部依存なしでインストール可能

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/spanish.py` | SpanishPhonemizer 実装 (IPA-first) |
| `src/python/g2p/piper_g2p/registry.py` | `_auto_register()` に es を追加 |
| `src/python/g2p/tests/test_spanish.py` | 単体テスト |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/spanish.py` をベースにコピー
2. 以下の変更を適用:
   - `map_sequence()` 呼び出しと `token_mapper` インポートを削除
   - `get_phoneme_id_map()` メソッドを削除
   - インポートパスを `piper_g2p.base` に変更
3. 以下の機能をそのまま移植:
   - グラフェム分割 (`_segment_graphemes`): 二重字 (ch, ll, rr, qu, gu, gu, sc) の処理
   - 音節分割 (`_find_syllable_boundaries`): スペイン語の音節規則
   - ストレス決定 (`_get_stressed_syllable`): アクセント記号 / 末尾文字規則
   - ストレスマーカー挿入 (`_insert_stress_marker`)
   - 機能語のストレス除去 (`_UNSTRESSED_FUNCTION_WORDS`)
   - 異音規則: b/v → [β], d → [ð], g → [ɣ] (母音間)
4. `registry.py` の `_auto_register()` に es ブロックを追加 (外部依存なし、常に成功)
5. テストケースを作成

### API / インターフェース

```python
from piper_g2p import get_phonemizer

phonemizer = get_phonemizer("es")

# 基本音素化
tokens = phonemizer.phonemize("Hola mundo")
# -> ["ˈ", "o", "l", "a", " ", "m", "ˈ", "u", "n", "d", "o"]

# prosody 付き
tokens, prosody = phonemizer.phonemize_with_prosody("¿Cómo estás?")
# prosody[i].a1 = 0
# prosody[i].a2 = stress level (0 or 2)
# prosody[i].a3 = word phoneme count
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | spanish.py の移植・IPA-first 化 |
| テストエージェント | 1 | ストレス位置・異音規則のテスト |

---

## 4. テスト計画

### 提供範囲

SpanishPhonemizer の音素化出力が正しい IPA であること、ストレス位置が正しいこと、異音規則が適用されること。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| 基本 | `"hola"` | `["ˈ", "o", "l", "a"]` (penultimate stress) |
| seseo | `"cerveza"` | c before e → `"s"` (not θ) |
| yeismo | `"calle"` | ll → `"ʝ"` |
| b/v allophony (initial) | `"bueno"` | `"b"` (plosive) |
| b/v allophony (intervocalic) | `"cabo"` | `"β"` (fricative) |
| d allophony | `"nada"` | intervocalic d → `"ð"` |
| g allophony | `"fuego"` | intervocalic g → `"ɣ"` |
| アクセント記号 stress | `"café"` | ストレスが最終音節 |
| 機能語 unstressed | `"el gato"` | `"el"` にストレスマーカーなし |
| rr trill | `"perro"` | `"rr"` トークン |
| ñ | `"niño"` | `"ɲ"` |
| PUA なし | 任意 | PUA 文字が含まれない |
| BOS/EOS なし | 任意 | `"^"` `"$"` が含まれない |

### E2E テスト

- `get_phonemizer("es")` が常に成功すること (外部依存なし)
- `available_languages()` に `"es"` が含まれること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **seseo のみ**: ラテンアメリカ発音 (c/z → [s]) のみ実装。カスティーリャ発音 (c/z → [θ]) は未対応。方言切替パラメータの追加は将来の拡張として検討。
- **方言切替なし**: voseo、lleismo/yeismo、s-aspiration 等の方言差は実装していない。
- **ストレスマーカー位置**: `_insert_stress_marker()` は grapheme→phoneme のマッピングに依存しており、gü/x 等の複数音素を生成するグラフェムでずれが生じる可能性がある。現在の実装では `_phoneme_count_for_unit()` で補正しているが、新しいグラフェムを追加する場合はこの関数も更新が必要。

### レビュー項目

- [ ] IPA トークンに PUA 文字が混入していないこと
- [ ] ストレスマーカーが正しい音節の母音前に挿入されていること
- [ ] 異音規則 (b/d/g) が環境条件に基づいて正しく適用されること
- [ ] 外部依存がないこと (`import` 文に外部パッケージがないこと)
- [ ] 機能語リストが適切であること

---

## 6. 一から作り直すとしたら

現在の実装はグラフェム分割・音節分割・ストレス決定・G2P の 4 段階に分かれているが、各段階が独立しているため phoneme 出力とストレスマーカーの対応付けが複雑になっている。一から作り直すなら、グラフェム→音素変換と音節分割を同時に行い、音節単位でストレスマーカーを挿入する方がシンプルになる。ただし現在の実装は 168K 発話の学習で検証済み。

---

## 7. 後続タスクへの連絡事項

- P1-006 (MultilingualPhonemizer): スペイン語はラテン文字のため、`UnicodeLanguageDetector` の `default_latin_language` 設定が重要
- P1-008 (pyproject.toml): `[es]` extra は空 (外部依存なし) だが、定義自体は作成する
- P1-010 (テストフィクスチャ): ストレス位置と異音規則のテストケースを追加
- P1-009 (ドキュメント): seseo のみ・方言切替なしの制限を記載
