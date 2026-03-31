# P1-005: PortuguesePhonemizer (ルールベース)

> Phase: 1 (全言語展開)
> マイルストーン: v0.2.0
> 対応要求: FR-100
> 依存チケット: P0-003 (コア抽象)
> ステータス: TODO

---

## 1. 目的とゴール

### 目的

piper-g2p パッケージにポルトガル語 (ブラジル) の G2P 機能を追加する。外部依存なしのルールベース実装で、ブラジルポルトガル語 (BR-PT) の正書法規則に基づいて IPA トークン列を返す。BR-PT 固有の音韻プロセス (t/d の口蓋化、l の母音化、語末母音弱化) を適用する。

### ゴール

- `get_phonemizer("pt").phonemize("Olá mundo")` が IPA トークン列を返す
- BR-PT の音韻規則が適用される (t/d 口蓋化、coda-l → w、語末 e → i / o → u)
- 鼻母音が正しく生成される
- 外部依存なしでインストール可能

---

## 2. 実装詳細

### 作成/変更するファイル

| ファイル | 内容 |
|---------|------|
| `src/python/g2p/piper_g2p/portuguese.py` | PortuguesePhonemizer 実装 (IPA-first) |
| `src/python/g2p/piper_g2p/registry.py` | `_auto_register()` に pt を追加 |
| `src/python/g2p/tests/test_portuguese.py` | 単体テスト |

### 実装手順

1. 現在の `src/python/piper_train/phonemize/portuguese.py` をベースにコピー
2. 以下の変更を適用:
   - `map_sequence()` 呼び出しと `token_mapper` インポートを削除
   - `get_phoneme_id_map()` メソッドを削除
   - インポートパスを `piper_g2p.base` に変更
3. 以下の機能をそのまま移植:
   - 子音二重字: nh → ɲ, lh → ʎ, ch → ʃ, rr → ʁ, ss → s
   - r の環境依存: 母音間 → ɾ (tap), その他 → ʁ (uvular)
   - 鼻母音: ã → ã, vowel+n/m+consonant → nasal vowel
   - ストレス決定: アクセント記号 > 末尾規則 (paroxytone/oxytone)
   - BR-PT 後処理 (3 段階パイプライン):
     1. `_remove_duplicate_nasal_coda()`: 鼻母音後の重複鼻子音除去
     2. `_apply_coda_l_vocalization()`: coda-l → w (Brasil → [bɾaziw])
     3. `_apply_br_postprocessing()`: t+i → tʃ, d+i → dʒ, 語末 e → i, o → u
   - 二重字: qu+e/i → k, qu+a/o → kw, gu+e/i → ɡ
4. `registry.py` に pt ブロックを追加
5. テストケースを作成

### API / インターフェース

```python
from piper_g2p import get_phonemizer

phonemizer = get_phonemizer("pt")

# 基本音素化
tokens = phonemizer.phonemize("Olá mundo")
# -> ["o", "l", "a", " ", "m", "ũ", "d", "u"]

# BR-PT 後処理の例
tokens = phonemizer.phonemize("cidade")
# -> ["s", "i", "d", "a", "dʒ", "i"]
# (d before i → dʒ, final e → i)

# prosody 付き
tokens, prosody = phonemizer.phonemize_with_prosody("Brasil")
# prosody[i].a1 = 0
# prosody[i].a2 = stress level (0 or 2)
# prosody[i].a3 = word phoneme count
```

---

## 3. エージェントチーム構成

| 役割 | 人数 | 担当内容 |
|------|------|---------|
| 実装エージェント | 1 | portuguese.py の移植・IPA-first 化 |
| テストエージェント | 1 | BR-PT 後処理・鼻母音のテスト |

---

## 4. テスト計画

### 提供範囲

PortuguesePhonemizer の出力が正しい IPA であること、BR-PT 固有の音韻規則が適用されること。

### Unit テスト

| テストケース | 入力 | 期待出力 (概要) |
|-------------|------|---------------|
| 基本 | `"olá"` | `["o", "l", "a"]` (oxytone stress) |
| t 口蓋化 | `"time"` | t before i → `"tʃ"` |
| d 口蓋化 | `"cidade"` | d before i → `"dʒ"` |
| coda-l 母音化 | `"Brasil"` | final l → `"w"` |
| coda-l 語中 | `"alto"` | l before consonant → `"w"` |
| 語末 e 弱化 | `"grande"` | final e → `"i"` |
| 語末 o 弱化 | `"carro"` | final o → `"u"` |
| 鼻母音 ã | `"irmã"` | `"ã"` |
| 鼻母音 vowel+n/m | `"tempo"` | `"ẽ"` |
| rr → ʁ | `"carro"` | `"ʁ"` |
| r 母音間 | `"para"` | `"ɾ"` (tap) |
| nh → ɲ | `"banho"` | `"ɲ"` |
| lh → ʎ | `"filho"` | `"ʎ"` |
| qu+e/i | `"quero"` | `"k"` (u silent) |
| 重複鼻子音除去 | `"bom"` | nasal vowel + no trailing m |
| PUA なし | 任意 | PUA 文字が含まれない |
| BOS/EOS なし | 任意 | `"^"` `"$"` が含まれない |

### E2E テスト

- `get_phonemizer("pt")` が常に成功すること
- `available_languages()` に `"pt"` が含まれること

---

## 5. 懸念事項とレビュー項目

### 懸念事項

- **BR-PT のみ**: EU-PT (ヨーロッパポルトガル語) は非対応。EU-PT は母音弱化パターン、s の実現 ([ʃ] vs [s])、語末子音の処理が大きく異なる。方言切替パラメータの追加は将来の拡張として検討。
- **ストレス計算の複雑さ**: `_count_vowel_groups()` と `_find_stress_position()` が二重字 (qu/gu/ou) を考慮した母音グループ計算を行っており、新しい二重字パターンの追加時にストレス位置がずれるリスクがある。
- **後処理パイプラインの順序依存**: 3 段階の後処理 (鼻子音除去 → coda-l → BR 後処理) は順序に依存しており、順序を変えると結果が変わる。

### レビュー項目

- [ ] IPA トークンに PUA 文字が混入していないこと
- [ ] BR-PT 3 段階後処理がすべて適用されること
- [ ] 鼻母音後の重複鼻子音が除去されていること
- [ ] coda-l が正しい環境でのみ w に変換されること
- [ ] t/d 口蓋化が i の前でのみ適用されること
- [ ] ストレス位置がアクセント記号・末尾規則に基づいて正しいこと

---

## 6. 一から作り直すとしたら

BR-PT の後処理 3 段階は音素列の再走査を繰り返しており効率が悪い。一から作り直すなら、G2P 変換時に BR-PT 規則を直接適用し、後処理パイプラインを不要にする設計にする。また EU-PT 対応を見据えて、方言プロファイルをパラメータ化する (e.g., `PortuguesePhonemizer(variant="br")`)。

---

## 7. 後続タスクへの連絡事項

- P1-006 (MultilingualPhonemizer): ポルトガル語はラテン文字のため `default_latin_language` 候補だが、en/es/fr が優先される
- P1-008 (pyproject.toml): `[pt]` extra は空 (外部依存なし)
- P1-010 (テストフィクスチャ): BR-PT 後処理の入出力ペアを重点的に追加
- P1-009 (ドキュメント): BR-PT のみ・EU-PT 非対応の制限を明記
