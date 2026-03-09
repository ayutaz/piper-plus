# Phoneme Mapping Reference

Piper Plus の音素体系と ID マッピングのリファレンス。

## アーキテクチャ

音素変換は **Phonemizer ABC + 言語レジストリ** で管理される。

```
テキスト → registry.get_phonemizer(language) → phonemize() → phoneme_ids → モデル
```

- `Phonemizer` 抽象基底クラス (`phonemize/base.py`)
- 言語レジストリ (`phonemize/registry.py`) に `ja` / `en` が自動登録
- 各言語が `phonemize()`, `phonemize_with_prosody()`, `get_phoneme_id_map()`, `post_process_ids()` を実装

---

## 日本語音素体系 (65トークン)

**ソース**: `phonemize/jp_id_map.py`, `phonemize/token_mapper.py`

### 特殊トークン (10個)

| ID | トークン | 用途 |
|----|---------|------|
| 0 | `_` | 短ポーズ / パディング |
| 1 | `^` | 文頭 (BOS) |
| 2 | `$` | 文末・平叙文 (EOS) |
| 3 | `?` | 文末・疑問文 (汎用) |
| 4 | `?!` | 文末・強調疑問 (Issue #204) |
| 5 | `?.` | 文末・平叙疑問 (Issue #204) |
| 6 | `?~` | 文末・確認疑問 (Issue #204) |
| 7 | `#` | アクセント句境界 |
| 8 | `[` | ピッチ上昇マーク |
| 9 | `]` | ピッチ下降マーク (アクセント核) |

### 母音 (15個)

| 種類 | 音素 | 説明 |
|------|------|------|
| 有声母音 | `a` `i` `u` `e` `o` | 通常の母音 |
| 無声化母音 | `A` `I` `U` `E` `O` | 大文字で表記。例: です → `d e s U` |
| 長母音 | `a:` `i:` `u:` `e:` `o:` | PUA マッピングで1文字化 |

### 撥音「ん」バリアント (5個) — Issue #207

後続音に応じて文脈依存の異音に変換される。

| 音素 | 条件 | 例 |
|------|------|-----|
| `N` | 汎用 (後方互換用) | — |
| `N_m` | m/b/p の前 (両唇音同化) | さんぽ → `s a N_m p o` |
| `N_n` | n/t/d/ts/ch の前 (歯茎音同化) | あんない → `a N_n n a i` |
| `N_ng` | k/g の前 (軟口蓋音同化) | ぎんこう → `g i N_ng k o o` |
| `N_uvular` | 語末・母音の前 (口蓋垂音) | ほん → `h o N_uvular` |

### 促音 (2個)

| 音素 | 説明 |
|------|------|
| `cl` | 促音 / 閉鎖 |
| `q` | 促音 (別表記) |

### 子音 (33個)

| 分類 | 音素 |
|------|------|
| 破裂音 | `k` `ky` `kw` `g` `gy` `gw` `t` `ty` `d` `dy` `p` `py` `b` `by` |
| 破擦音・摩擦音 | `ch` `ts` `s` `sh` `z` `j` `zy` `f` `h` `hy` `v` |
| 鼻音・接近音 | `n` `ny` `m` `my` `r` `ry` `w` `y` |

---

## PUA (Private Use Area) マッピング — 全29エントリ

複数文字音素を Unicode PUA (U+E000〜) の1コードポイントにマッピングし、内部で1文字として処理する。

**ソース**: `phonemize/token_mapper.py` の `FIXED_PUA_MAPPING`

| 音素 | PUA コード | 分類 |
|------|-----------|------|
| `a:` | U+E000 | 長母音 |
| `i:` | U+E001 | 長母音 |
| `u:` | U+E002 | 長母音 |
| `e:` | U+E003 | 長母音 |
| `o:` | U+E004 | 長母音 |
| `cl` | U+E005 | 促音 |
| `ky` | U+E006 | 口蓋化子音 |
| `kw` | U+E007 | 唇音化子音 |
| `gy` | U+E008 | 口蓋化子音 |
| `gw` | U+E009 | 唇音化子音 |
| `ty` | U+E00A | 口蓋化子音 |
| `dy` | U+E00B | 口蓋化子音 |
| `py` | U+E00C | 口蓋化子音 |
| `by` | U+E00D | 口蓋化子音 |
| `ch` | U+E00E | 破擦音 |
| `ts` | U+E00F | 破擦音 |
| `sh` | U+E010 | 摩擦音 |
| `zy` | U+E011 | 摩擦音 |
| `hy` | U+E012 | 口蓋化子音 |
| `ny` | U+E013 | 鼻音 |
| `my` | U+E014 | 鼻音 |
| `ry` | U+E015 | 流音 |
| `?!` | U+E016 | 強調疑問マーカー (Issue #204) |
| `?.` | U+E017 | 平叙疑問マーカー (Issue #204) |
| `?~` | U+E018 | 確認疑問マーカー (Issue #204) |
| `N_m` | U+E019 | 撥音・両唇音同化 (Issue #207) |
| `N_n` | U+E01A | 撥音・歯茎音同化 (Issue #207) |
| `N_ng` | U+E01B | 撥音・軟口蓋音同化 (Issue #207) |
| `N_uvular` | U+E01C | 撥音・口蓋垂音 (Issue #207) |

U+E020 以降は動的割り当て用に予約されている。

---

## 英語音素体系

**ソース**: `phonemize/english.py`
**G2P エンジン**: g2p-en (Apache-2.0) — espeak-ng (GPL) 不要

### ARPAbet → IPA 変換表

| ARPAbet | IPA | ARPAbet | IPA |
|---------|-----|---------|-----|
| AA | ɑ | N | n |
| AE | æ | NG | ŋ |
| AH | ʌ (stress>0), ə (stress=0) | OW | oʊ |
| AO | ɔː | OY | ɔɪ |
| AW | aʊ | P | p |
| AY | aɪ | R | ɹ |
| B | b | S | s |
| CH | tʃ | SH | ʃ |
| D | d | T | t |
| DH | ð | TH | θ |
| EH | ɛ | UH | ʊ |
| ER | ɚ (stress=0), ɜː (stress=1) | UW | uː |
| EY | eɪ | V | v |
| F | f | W | w |
| G | ɡ | Y | j |
| HH | h | Z | z |
| IH | ɪ | ZH | ʒ |
| IY | iː | | |
| JH | dʒ | | |
| K | k | | |
| L | l | | |
| M | m | | |

### 文脈依存規則

| パターン | 変換 | 例 |
|---------|------|-----|
| AA + R | ɑːɹ | car → kɑːɹ |
| ER (stress=1) | ɜː | bird → bɜːd |
| AH (stress=0) | ə | about → əbaʊt |

### ストレスマーカー

| 記号 | 意味 |
|------|------|
| `ˈ` | 第1ストレス (母音の前に挿入) |
| `ˌ` | 第2ストレス (母音の前に挿入) |

機能語 (a, the, are, you 等 75語) はストレスが自動除去される。

### 英語の後処理 (post_process_ids)

英語では espeak-ng 互換のため、`EnglishPhonemizer.post_process_ids()` が以下を行う:

1. 各音素 ID の間にパディング (`_`, ID=0) を挿入
2. 先頭に BOS (`^`) + パディング を付加
3. 末尾に EOS (`$`) を付加

日本語ではこの後処理は行われない (音素列がそのまま使用される)。

---

## Prosody Features (A1/A2/A3)

両言語で `ProsodyInfo(a1, a2, a3)` を生成するが、意味が異なる。

| フィールド | 日本語 | 英語 |
|-----------|--------|------|
| `a1` | アクセント核からの相対位置 | 固定 0 |
| `a2` | アクセント句内のモーラ位置 (1-based) | ストレスレベル (0=なし, 1=第2, 2=第1) |
| `a3` | アクセント句内の総モーラ数 | 単語内の音素数 |

---

## 音素 ID マッピングの仕組み

1. テキストを `registry.get_phonemizer(language)` で音素列に変換
2. 複数文字音素を PUA コードポイントにマッピング (`token_mapper.register()`)
3. `phoneme_id_map` (config.json 由来) で各音素を ID に変換
4. `post_process_ids()` で言語固有の後処理 (英語: BOS/EOS/パディング)
5. ID 列をモデルに入力

日本語の `phoneme_id_map` は `jp_id_map.get_japanese_id_map()` で自動生成される。
英語は学習済みモデルの `config.json` に含まれる `phoneme_id_map` を使用する。
