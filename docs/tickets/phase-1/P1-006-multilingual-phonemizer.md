# P1-006: MultilingualPhonemizer + UnicodeLanguageDetector

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-101
> 依存チケット: P1-001, P1-002, P1-003, P1-004, P1-005 (全言語 Phonemizer)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージに多言語混在テキスト対応の Phonemizer を追加する。複合言語コード ("ja-en-zh") で混在テキストを自動分割・各言語に委譲して音素化する。Phase 0 のレジストリ拡張として、複合コードの自動解決機構も導入する。

### ゴール

- `get_phonemizer("ja-en-zh")` で MultilingualPhonemizer が自動生成される
- UnicodeLanguageDetector がテキストを言語セグメントに分割する
- CJK 曖昧性解消 (JA vs ZH) がかなの有無で判定される
- 各言語セグメントが独立に音素化され、結果が連結される
- 正規化されたキャノニカルキー ("en-ja-zh") でキャッシュされる

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/multilingual.py` | MultilingualPhonemizer + UnicodeLanguageDetector |
| `src/python/g2p/piper_g2p/registry.py` | 複合コード自動解決ロジック追加 |
| `src/python/g2p/tests/test_multilingual.py` | 単体テスト |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/multilingual.py` をベースにコピー
2. 以下の変更を適用:
   - `multilingual_id_map` / `token_mapper` への依存を除去
   - `get_phoneme_id_map()` メソッドを削除
   - `post_process_ids()` メソッドを削除 (PiperEncoder が担う)
   - BOS/EOS ストリッピングロジックの簡素化: IPA-first のため BOS/EOS は各言語 Phonemizer が出力しない。ストリッピング不要。
   - `_last_eos` のトラッキングも不要 (EOS は PiperEncoder の責務)
   - インポートパスを `piper_g2p` に変更
3. `UnicodeLanguageDetector` をそのまま移植:
   - かな検出 (U+3040-30FF, U+31F0-31FF)
   - CJK 統合漢字 (U+4E00-9FFF, U+3400-4DBF, U+F900-FAFF)
   - ハングル (U+AC00-D7AF, U+1100-11FF, U+3130-318F)
   - ラテン文字 (A-Z, a-z, diacritics)
   - 全角文字の処理
4. `_segment_text_multilingual()` を移植:
   - 中立文字 (空白/数字/句読点) は前のセグメントに吸収
   - 言語検出できない文字のみのテキストはデフォルト言語にフォールバック
5. `registry.py` に複合コード解決ロジックを追加:
   - `-` 区切りの複合コードを分割
   - ソート済みキャノニカルキーでキャッシュ
   - 全構成言語が登録済みであることを検証
   - `_detect_default_latin()` の実装
6. テストケースを作成

### API / インターフェース

```python
from piper_g2p import get_phonemizer

# 複合コードで自動生成
phonemizer = get_phonemizer("ja-en-zh")

# 混在テキストの音素化
tokens = phonemizer.phonemize("こんにちはHello你好")
# -> JA セグメント: ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
# -> EN セグメント: ["h", "ʌ", "l", "oʊ"]
# -> ZH セグメント: ["n", "i", "tone3", "x", "aʊ", "tone3"]
# 全体が連結されて返る

# キャノニカルキーの正規化
p1 = get_phonemizer("ja-en-zh")
p2 = get_phonemizer("zh-en-ja")
# p1 is p2  (同一インスタンス、canonical key = "en-ja-zh")

# UnicodeLanguageDetector 単体利用
from piper_g2p.multilingual import UnicodeLanguageDetector
detector = UnicodeLanguageDetector(["ja", "en", "zh"])
assert detector.detect_char("あ") == "ja"
assert detector.detect_char("A") == "en"
# CJK 曖昧性: かなが文脈にある → ja、ない → zh
assert detector.detect_char("漢", context_has_kana=True) == "ja"
assert detector.detect_char("漢", context_has_kana=False) == "zh"
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | multilingual.py の移植・簡素化、registry.py の複合コード対応 |
| テストエージェント | 1 | セグメント分割・CJK 曖昧性・キャッシュのテスト |

---

## 4. テスト計画

### 提供範囲

MultilingualPhonemizer が混在テキストを正しくセグメント分割し、各言語に委譲して音素化すること。レジストリの複合コード解決が正しいこと。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| JA+EN 混在 | `"こんにちはHello"` | JA トークン + EN トークンが連結 |
| JA+ZH 混在 (かなあり) | `"東京は大きい"` | 漢字 → ja (かなが文脈に存在) |
| ZH のみ (かななし) | `"北京很大"` | 漢字 → zh |
| EN+ES 混在 | `"Hello Hola"` | 全てデフォルト Latin 言語 (en) に |
| ハングル検出 | `"안녕Hello"` | ko + en セグメント |
| 中立文字吸収 | `"Hello, 你好!"` | 句読点が前のセグメントに吸収 |
| 空テキスト | `""` | 空リスト |
| 数字のみ | `"12345"` | デフォルト言語にフォールバック |
| キャノニカルキー | `"zh-en-ja"` == `"en-ja-zh"` | 同一インスタンス |
| 未登録言語 | `"ja-xx"` | ValueError |
| detect_char: かな | `"あ"` | `"ja"` |
| detect_char: ハングル | `"가"` | `"ko"` |
| detect_char: ラテン | `"A"` | default_latin_language |
| detect_char: 中立 | `" "` | `None` |
| PUA なし | 任意 | PUA 文字が含まれない |
| BOS/EOS なし | 任意 | `"^"` `"$"` が含まれない |

### E2E テスト

- `get_phonemizer("ja-en")` でインスタンスが生成されること
- 7 言語全ての組み合わせで動作すること (依存がインストール済みの言語)
- `available_languages()` に個別言語と複合コードの両方が含まれること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **BOS/EOS ストリッピングの除去**: 現在の実装では各言語 Phonemizer が BOS/EOS を含むため MultilingualPhonemizer がストリッピングしている。IPA-first 化により各言語が BOS/EOS を出力しなくなるため、ストリッピングロジックは不要になるが、Phase 0 の JA/EN 実装と整合性を取る必要がある。
- **ラテン文字の曖昧性**: EN/ES/FR/PT が同時に有効な場合、ラテン文字テキストはすべて `default_latin_language` (通常 en) に割り当てられる。各ラテン言語固有のテキスト検出 (diacritics の種類による判定等) は未実装。
- **スレッド安全性**: 現在の実装の `_last_eos` トラッキングはスレッドセーフではないが、IPA-first 化により不要になるため問題は解消される。ただしレジストリのグローバル `_REGISTRY` は依然としてスレッドセーフではない。

### レビュー項目

- [ ] BOS/EOS ストリッピングが不要になっていること (IPA-first)
- [ ] `_last_eos` / `post_process_ids()` が削除されていること
- [ ] キャノニカルキーの正規化が正しいこと
- [ ] CJK 曖昧性解消 (かなの有無) が正しく動作すること
- [ ] 未登録言語の複合コードで `ValueError` が発生すること
- [ ] `_detect_default_latin()` の優先順位 (en > es > pt > fr) が正しいこと

---

## 6. 一から作り直すとしたら

現在の Unicode ベースの言語検出は文字単位の分類に依存しており、ラテン文字間の言語判定ができない。一から作り直すなら、N-gram ベースの軽量言語識別 (fastText lid.176 等) を optional 依存として組み込み、ラテン文字セグメントの言語をより正確に判定する。Unicode 検出はフォールバックとして残す。

---

## 7. 後続タスクへの連絡事項

- P1-008 (pyproject.toml): `[all]` extra で全言語の依存をインストール可能にする
- P1-010 (テストフィクスチャ): 混在テキストのテストケースを追加
- P1-011 (API 凍結): MultilingualPhonemizer の API が安定版 v1.0.0 に含まれる
- piper_train 互換シム: `get_phonemizer("ja-en-zh-ko-es-fr-pt")` が従来の MultilingualPhonemizer と互換動作すること
