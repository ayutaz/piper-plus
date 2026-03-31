# P1-004: FrenchPhonemizer (ルールベース)

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-100
> 依存チケット: P0-003 (コア抽象)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージにフランス語の G2P 機能を追加する。外部依存なしのルールベース実装で、フランス語の正書法規則に基づいて IPA トークン列を返す。鼻母音 (ɑ̃/ɛ̃/ɔ̃)、母音二重字 (ou/au/eau/ai/oi 等)、無音文字 (h muet/final consonants) を正しく処理する。

### ゴール

- `get_phonemizer("fr").phonemize("Bonjour le monde")` が IPA トークン列を返す
- 鼻母音が正しく生成される
- 語末無音子音が正しくスキップされる
- 母音間 s の有声化 (s → z) が適用される
- 外部依存なしでインストール可能

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/french.py` | FrenchPhonemizer 実装 (IPA-first) |
| `src/python/g2p/piper_g2p/registry.py` | `_auto_register()` に fr を追加 |
| `src/python/g2p/tests/test_french.py` | 単体テスト |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/french.py` をベースにコピー
2. 以下の変更を適用:
   - `map_sequence()` 呼び出しと `token_mapper` インポートを削除
   - `get_phoneme_id_map()` メソッドを削除
   - インポートパスを `piper_g2p.base` に変更
3. 以下の機能をそのまま移植:
   - 鼻母音: an/am/en/em → ɑ̃, in/im → ɛ̃, on/om → ɔ̃, un/um → ɛ̃
   - 母音二重字: eau → o, ou → u, au → o, oi → wa, ai → ɛ, ei → ɛ, eu → ø/œ
   - 子音二重字: ch → ʃ, gn → ɲ, ph → f, th → t, qu → k, gu+e/i → ɡ
   - 無音文字: h muet, 語末 d/g/h/m/n/p/s/t/x/z
   - -er 動詞末: 多音節語末 -er → /e/
   - -ille パターン: aille → aj, eille → ɛj, ouille → uj, ille → ij (例外: ville/mille → il)
   - -tion → sjɔ̃
   - 母音間 s → z
   - 語末ストレス (フランス語は最終音節にストレス)
4. エリジオン対応: アポストロフィ (l'ami, l'ami) を単語境界として処理
5. `registry.py` に fr ブロックを追加
6. テストケースを作成

### API / インターフェース

```python
from piper_g2p import get_phonemizer

phonemizer = get_phonemizer("fr")

# 基本音素化
tokens = phonemizer.phonemize("Bonjour")
# -> ["b", "ɔ̃", "ʒ", "u", "ʁ"]

# prosody 付き
tokens, prosody = phonemizer.phonemize_with_prosody("Comment allez-vous?")
# prosody[i].a1 = 0
# prosody[i].a2 = stress level (最終音節で 2)
# prosody[i].a3 = word phoneme count
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | french.py の移植・IPA-first 化 |
| テストエージェント | 1 | 鼻母音・無音文字・ストレスのテスト |

---

## 4. テスト計画

### 提供範囲

FrenchPhonemizer の音素化出力が正しい IPA であること、鼻母音・無音文字・母音間 s 有声化が正しいこと。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| 鼻母音 an | `"enfant"` | `"ɑ̃"` が 2 回出現 |
| 鼻母音 on | `"bonjour"` | `"ɔ̃"` が含まれる |
| 鼻母音 in | `"vin"` | `"ɛ̃"` が含まれる |
| 母音二重字 eau | `"beau"` | `"o"` |
| 母音二重字 ou | `"pour"` | `"u"` |
| 母音二重字 oi | `"moi"` | `"w"`, `"a"` |
| 無音 h | `"homme"` | h なし |
| 語末無音 t | `"petit"` | 末尾の t なし |
| 母音間 s → z | `"maison"` | `"z"` |
| -er 動詞末 | `"parler"` | 末尾 `"e"` (not ɛʁ) |
| -er 例外 | `"hiver"` | 末尾 `"ɛ"`, `"ʁ"` |
| ch → ʃ | `"chat"` | `"ʃ"` |
| gn → ɲ | `"montagne"` | `"ɲ"` |
| -ille | `"fille"` | `"i"`, `"j"` |
| -ille 例外 | `"ville"` | `"i"`, `"l"` |
| -tion | `"nation"` | `"s"`, `"j"`, `"ɔ̃"` |
| エリジオン | `"l'ami"` | 別単語として処理 |
| PUA なし | 任意 | PUA 文字が含まれない |
| BOS/EOS なし | 任意 | `"^"` `"$"` が含まれない |

### E2E テスト

- `get_phonemizer("fr")` が常に成功すること
- `available_languages()` に `"fr"` が含まれること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **liaison 未実装**: フランス語のリエゾン (語末子音が次の語頭母音と結合する現象、e.g., "les amis" → /lez‿ami/) は文脈依存のため未実装。正確な liaison 実装には品詞情報と統語構造が必要で、ルールベースでの完全対応は困難。
- **schwa の扱い**: e muet (ə) の脱落規則は方言・発話速度・韻律に依存する。現在の実装は保守的 (語末以外のeをəとして保持)。
- **y_vowel トークン**: フランス語の /y/ は `"y_vowel"` としてエンコードされる (中国語の /y/ と同一トークン)。MultilingualPhonemizer で衝突しないことを確認する必要がある。

### レビュー項目

- [ ] IPA トークンに PUA 文字が混入していないこと
- [ ] 鼻母音 4 種 (ɑ̃/ɛ̃/ɔ̃) が正しく生成されること (ɛ̃ は in/un/aim/ein で共通)
- [ ] 語末無音子音が正しくスキップされること
- [ ] 母音間 s → z の有声化が適用されること
- [ ] -er 動詞末と例外リスト (_ER_AS_EHR) が正しく処理されること
- [ ] エリジオン (アポストロフィ) が単語境界として機能すること

---

## 6. 一から作り直すとしたら

フランス語の G2P は例外が多く、`_convert_word()` 内の if-chain が長大 (約 600 行)。一から作り直すなら、ルールをデータ駆動 (優先度付きルールテーブル) に変換し、ルールの追加・修正を容易にする。また liaison の部分対応 (obligatory liaison のみ) を初期バージョンから含める設計にする。

---

## 7. 後続タスクへの連絡事項

- P1-006 (MultilingualPhonemizer): フランス語はラテン文字のため `default_latin_language` の候補になる。en が存在する場合は en が優先される
- P1-008 (pyproject.toml): `[fr]` extra は空 (外部依存なし)
- P1-010 (テストフィクスチャ): 鼻母音パターンのテストケースを重点的に追加
- P1-009 (ドキュメント): liaison 未実装の制限を明記
