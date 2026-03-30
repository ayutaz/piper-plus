# FR-03 Rule-based G2P エンジン 実装仕様書

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| 対象要件 | FR-03a -- FR-03g (`swedish-requirements.md`) |
| 設計参照 | `swedish-g2p-design.md` セクション 2--8 |
| 実装ファイル | `src/python/piper_train/phonemize/swedish.py` |
| テストファイル | `test/test_swedish_phonemizer.py` |

---

## 目次

1. [全体アーキテクチャ](#1-全体アーキテクチャ)
2. [FR-03a: Soft/Hard 子音分岐](#2-fr-03a-softhard-子音分岐)
3. [FR-03b: レトロフレックス同化](#3-fr-03b-レトロフレックス同化)
4. [FR-03c: sj-sound パターン](#4-fr-03c-sj-sound-ɧ-パターン)
5. [FR-03d: 母音長 (Complementary Quantity)](#5-fr-03d-母音長-complementary-quantity)
6. [FR-03e: 非強勢母音短縮](#6-fr-03e-非強勢母音短縮)
7. [FR-03f: ストレス検出](#7-fr-03f-ストレス検出)
8. [FR-03g: ローンワード規則](#8-fr-03g-ローンワード規則)
9. [処理パイプライン統合](#9-処理パイプライン統合)

---

## 1. 全体アーキテクチャ

### 1.1 処理ステージと呼び出し順序

```
入力: テキスト (str)
  │
  [Stage 0] 正規化 & トークン化
  │  小文字変換 + Unicode NFC + トークン分割
  │
  ▼ 単語ごとに:
  ├─ [Stage 1] NST辞書ルックアップ → ヒット時は Stage 5 へ
  │
  ▼ (辞書ミス: OOV語)
  [Stage 2] detect_loanword_suffix(word)     ← FR-03g
  │  接尾辞の音素列を確定し、残余語幹を native 規則へ渡す
  │
  ▼
  [Stage 3] detect_loanword_prefix(word)     ← FR-03g (接頭辞/字母)
  │  sch/ch/sh/ph/th を処理
  │
  ▼
  [Stage 4] _convert_word_native(word)       ← FR-03a, FR-03c, FR-03d, FR-03e
  │  Soft/Hard 子音分岐 + sj-sound + 母音長 + 非強勢母音短縮
  │  内部で _convert_consonant() と get_vowel_phoneme() を呼び出す
  │
  ▼
  [Stage 5] apply_retroflex(phonemes)        ← FR-03b
  │  r+C → レトロフレックス同化 (後処理)
  │
  ▼
  [Stage 6] detect_stress(word) + apply_stress(phonemes)  ← FR-03f
  │  ストレスマーカー (ˈ/ˌ) を挿入
  │
  ▼
  [Stage 7] ProsodyInfo 構築 + トークンマッピング (PUA)
  │  a1=0, a2=ストレス, a3=単語音素数 / 多文字→PUA変換
  │
  ▼
  出力: list[str] (IPA音素列)
```

### 1.2 モジュール公開API

`swedish.py` は Spanish/French と同じパターンで `__all__` をエクスポートする:

```python
__all__ = [
    "phonemize_swedish",
    "phonemize_swedish_with_prosody",
    "SwedishPhonemizer",
]
```

### 1.3 共通定数

```python
# 前母音 (口蓋化を引き起こす文字)
FRONT_VOWELS: frozenset[str] = frozenset({"e", "i", "y", "ä", "ö"})

# 後母音 (口蓋化なし)
BACK_VOWELS: frozenset[str] = frozenset({"a", "o", "u", "å"})

# 全母音文字
ALL_VOWELS: frozenset[str] = FRONT_VOWELS | BACK_VOWELS

# 子音文字
CONSONANTS: frozenset[str] = frozenset(
    "bcdfghjklmnpqrstvwxz"
)

# sk + 後母音 で例外的に /ɧ/ になる語 (語中の sk)
SK_BACK_VOWEL_EXCEPTIONS: frozenset[str] = frozenset({
    "människa",     # person (sk + a → /ɧ/)
    "marskalk",     # marshal (sk + a → /ɧ/)
})

# 句読点 (トークン化で保持)
PUNCTUATION: frozenset[str] = frozenset(",.;:!?")

# トークン分割正規表現
RE_TOKEN: re.Pattern = re.compile(
    r"([a-zåäöàáéèüñ]+|[,.;:!?]+)", re.IGNORECASE
)
```

---

## 2. FR-03a: Soft/Hard 子音分岐

### 2.1 関数シグネチャ

```python
def _convert_consonant(
    word: str,
    pos: int,
    is_word_initial: bool,
) -> tuple[str, int]:
    """子音グラフェムをIPA音素に変換する。

    Parameters
    ----------
    word : str
        処理対象の単語全体 (小文字正規化済み)。
    pos : int
        現在の文字位置 (0-indexed)。
    is_word_initial : bool
        pos が語頭位置かどうか。dj/gj/hj/lj 規則は語頭のみ適用。

    Returns
    -------
    tuple[str, int]
        (IPA音素文字列, 消費した文字数)。
        複数音素を返す場合はスペース区切り (例: "s k" で2音素)。

    Notes
    -----
    規則は最長一致順で評価する。sk → k → g の順序を厳守すること。
    """
```

### 2.2 規則テーブル (17規則、優先順位順)

以下の規則を上から順に評価し、最初にマッチしたものを適用する。

| 優先度 | マッチ条件 | 出力IPA | 消費文字数 | 備考 |
|--------|-----------|---------|-----------|------|
| 1 | `skj` | `ɧ` | 3 | 無条件。skjorta, skjuta |
| 2 | `stj` | `ɧ` | 3 | 無条件。stjärna, stjälk |
| 3 | `sk` + 前母音 | `ɧ` | 2 | sk の2文字を消費、後続母音は別途処理。sked, sky, skön |
| 4 | `sk` + 後母音 | `s k` | 2 | /s/ + /k/ の2音素。skola, skog, skatt。**例外**: `SK_BACK_VOWEL_EXCEPTIONS` → /ɧ/ |
| 5 | `sk` + 子音 | `s k` | 2 | /s/ + /k/。skriva, skratt |
| 6 | `sk` + 語末 | `s k` | 2 | /s/ + /k/。risk, disk |
| 7 | `sj` | `ɧ` | 2 | 無条件。sjö, sjuk, sjunga |
| 8 | `sch` | `ɧ` | 3 | 無条件。schema, schack (Stage 3 でも処理可) |
| 9 | `sh` | `ɧ` | 2 | 無条件。show, shopping |
| 10 | `tj` | `ɕ` | 2 | 無条件。tjugo, tjock |
| 11 | `kj` | `ɕ` | 2 | 無条件。kjol, kjortel |
| 12 | `k` + 前母音 | `ɕ` | 1 | **例外リスト確認**。kind, köp, kör |
| 13 | `k` + 後母音/子音/語末 | `k` | 1 | kal, ko, kram |
| 14 | `dj` (語頭) | `j` | 2 | djur, djup |
| 15 | `gj` (語頭) | `j` | 2 | gjord, gjorde |
| 16 | `hj` (語頭) | `j` | 2 | hjälp, hjärta |
| 17 | `lj` (語頭) | `j` | 2 | ljus, ljud |
| 18 | `ng` | `ŋ` | 2 | kung, lång, finger |
| 19 | `g` + 前母音 | `j` | 1 | **例外リスト確認**。genom, göra |
| 20 | `g` + 後母音/子音/語末 | `ɡ` | 1 | gata, glas, grov |

**注意**: 規則12と19は例外リストとの照合が必要。以下 2.3 で詳述する。

### 2.3 アルゴリズム疑似コード

```python
def _convert_consonant(word: str, pos: int, is_word_initial: bool) -> tuple[str, int]:
    ch = word[pos]
    remaining = word[pos:]
    next_ch = word[pos + 1] if pos + 1 < len(word) else ""
    next2 = word[pos + 2] if pos + 2 < len(word) else ""

    # --- 優先度 1-2: skj, stj (3文字、無条件) ---
    if remaining.startswith("skj"):
        return ("ɧ", 3)
    if remaining.startswith("stj"):
        return ("ɧ", 3)

    # --- 優先度 3-6: sk + 文脈 ---
    if remaining.startswith("sk"):
        after_sk = word[pos + 2] if pos + 2 < len(word) else ""
        if after_sk in FRONT_VOWELS:
            return ("ɧ", 2)         # sk + 前母音 → /ɧ/
        elif word in SK_BACK_VOWEL_EXCEPTIONS:
            return ("ɧ", 2)         # sk + 後母音 例外 → /ɧ/ (människa 等)
        else:
            return ("s k", 2)       # sk + 後母音/子音/語末 → /s k/

    # --- 優先度 7: sj (無条件) ---
    if remaining.startswith("sj"):
        return ("ɧ", 2)

    # --- 優先度 8: sch (無条件) ---
    if remaining.startswith("sch"):
        return ("ɧ", 3)

    # --- 優先度 9: sh (無条件) ---
    if remaining.startswith("sh"):
        return ("ɧ", 2)

    # --- 優先度 10-11: tj, kj (無条件) ---
    if remaining.startswith("tj"):
        return ("ɕ", 2)
    if remaining.startswith("kj"):
        return ("ɕ", 2)

    # --- 優先度 12-13: k + 文脈 ---
    if ch == "k":
        if next_ch in FRONT_VOWELS:
            # 例外リスト確認: 形態論ヒューリスティック + 静的リスト
            if _is_hard_k(word, pos):
                return ("k", 1)
            return ("ɕ", 1)
        return ("k", 1)

    # --- 優先度 14-17: dj, gj, hj, lj (語頭のみ) ---
    if is_word_initial:
        if remaining.startswith("dj"):
            return ("j", 2)
        if remaining.startswith("gj"):
            return ("j", 2)
        if remaining.startswith("hj"):
            return ("j", 2)
        if remaining.startswith("lj"):
            return ("j", 2)

    # --- 優先度 18: ng ---
    if remaining.startswith("ng"):
        return ("ŋ", 2)

    # --- 優先度 19-20: g + 文脈 ---
    if ch == "g":
        if next_ch in FRONT_VOWELS:
            if _is_hard_g(word, pos):
                return ("ɡ", 1)
            return ("j", 1)
        return ("ɡ", 1)

    # --- デフォルト: 子音をそのままIPAに ---
    return (_CONSONANT_DEFAULT.get(ch, ch), 1)
```

```python
# その他の子音のデフォルト変換
_CONSONANT_DEFAULT: dict[str, str] = {
    "b": "b",
    "c": "k",      # デフォルト (ce/ci は別途処理)
    "d": "d",
    "f": "f",
    "h": "h",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "p": "p",
    "q": "k",
    "r": "r",
    "s": "s",
    "t": "t",
    "v": "v",
    "w": "v",      # スウェーデン語では w → /v/
    "x": "k s",    # /ks/
    "z": "s",      # スウェーデン語では z → /s/
}
```

### 2.4 例外リスト (HARD_K_WORDS)

`k` + 前母音で硬い /k/ を保持する語。約80語。

```python
HARD_K_WORDS: frozenset[str] = frozenset({
    # --- ローンワード (外来語) ---
    "kille",        # guy (boy)
    "kissa",        # pee
    "kiosk",        # kiosk
    "kebab",        # kebab
    "kennel",       # kennel
    "keps",         # cap
    "ketchup",      # ketchup
    "kick",         # kick
    "kilt",         # kilt
    "kimono",       # kimono
    "kitsch",       # kitsch
    "kibbutz",      # kibbutz
    "kiwi",         # kiwi
    "kilo",         # kilo
    "kille",        # guy
    "kiosk",        # kiosk
    "kex",          # cracker/biscuit
    "kent",         # (proper name, also adjective "known")
    "kerna",        # churn
    "keso",         # cottage cheese
    "kikare",       # binoculars
    "kines",        # Chinese person
    "kinesisk",     # Chinese (adj)

    # --- 語幹が /k/ で終わる活用形 ---
    # lek- (play)
    "leker",        # plays
    "leken",        # the play / playful
    "lekerska",     # playmate (f)
    # stek- (roast/fry)
    "steker",       # fries
    "steket",       # the roast (neut def)
    # sök- (seek)
    "söker",        # seeks
    "söket",        # the search (neut def)
    # tänk- (think)
    "tänker",       # thinks
    "tänket",       # the thinking (neut def)
    # dyk- (dive)
    "dyker",        # dives
    "dyket",        # the dive (neut def)
    # ryk- (jerk/snatch)
    "ryker",        # smokes / is pulled
    # rök- (smoke)
    "röker",        # smokes
    "röket",        # the smoke (neut def)
    # smek- (caress)
    "smeker",       # caresses
    # läk- (heal)
    "läker",        # heals
    "läket",        # the medicine (neut def)
    # märk- (mark/notice)
    "märker",       # notices
    "märket",       # the mark (neut def)
    # räck- (suffice/reach)
    "räcker",       # suffices
    # väck- (wake)
    "väcker",       # wakes
    # vik- (fold)
    "viker",        # folds
    # stryk- (stroke/iron)
    "stryker",      # strokes/irons
    # sjunk- (sink)
    "sjunker",      # sinks
    # stick- (stick/sting)
    "sticker",      # stings

    # --- 語中の -ke- / -ki- (形態素境界で /k/) ---
    "pojke",        # boy
    "fröken",       # miss / teacher
    "onkel",        # uncle
    "sockel",       # base/pedestal
    "socker",       # sugar
    "ocker",        # usury
    "märke",        # mark/brand
    "mörker",       # darkness
    "tecken",       # sign
    "vacker",       # beautiful
    "naken",        # naked
    "säker",        # safe/sure
    "enkel",        # simple/single
    "paket",        # package
    "raket",        # rocket
    "staket",       # fence
    "silke",        # silk
    "vinkel",       # angle
    "skelett",      # skeleton
    "ficka",        # pocket
    "dricka",       # drink
    "docka",        # doll
    "backe",        # hill
    "flicka",       # girl
    "bricka",       # tray
    "trycke",       # print/press
    "skicka",       # send
    "rike",         # kingdom
    "kirke",        # church (dialect)
    "hammarskiöld", # (proper name, /k/)
})
```

### 2.5 例外リスト (HARD_G_WORDS)

`g` + 前母音で硬い /ɡ/ を保持する語。約60語。

```python
HARD_G_WORDS: frozenset[str] = frozenset({
    # --- 名詞 ---
    "bagel",        # bagel
    "bageri",       # bakery
    "bygel",        # hanger
    "bygge",        # construction
    "båge",         # bow/arch
    "dager",        # daylight
    "flygel",       # grand piano / wing
    "gecko",        # gecko
    "hage",         # garden/pasture
    "hagel",        # hail/shot
    "hunger",       # hunger
    "lager",        # stock/layer
    "läge",         # position/situation
    "läger",        # camp
    "mage",         # stomach
    "nagel",        # nail (finger)
    "regel",        # rule/bolt
    "segel",        # sail
    "seger",        # victory
    "stege",        # ladder
    "tagel",        # horsehair
    "tegel",        # brick
    "tiger",        # tiger
    "tygel",        # rein
    "finger",       # finger
    "ängel",        # angel
    "fågel",       # bird
    "spegel",       # mirror
    "fogel",        # (archaic) bird

    # --- 活用形 (語幹が /ɡ/) ---
    "duger",        # is sufficient
    "flyger",       # flies
    "ligger",       # lies (position)
    "ljuger",       # lies (untruth)
    "lägger",       # puts/places
    "stiger",       # rises/steps
    "suger",        # sucks
    "tigger",       # begs
    "väger",        # weighs
    "äger",         # owns
    "dröger",       # delays (archaic)
    "drager",       # drags (archaic)
    "beger",        # (archaic form)
    "ger",          # gives (語幹 g+e)

    # --- -era 動詞 (ラテン語由来、g は常に硬い) ---
    "agera",        # act
    "delegera",     # delegate
    "reagera",      # react
    "segregera",    # segregate
    "tangera",      # touch upon/tangent
    "engagera",     # engage
    "arrangera",    # arrange
    "ignorera",     # ignore
    "navigera",     # navigate
    "negera",       # negate
    "intrigera",    # intrigue

    # --- その他 ---
    "ge",           # give
    "gel",          # gel
    "berg",         # mountain (g は語末で黙字だが参考)
    "borg",         # castle (同上)
    "berg",         # mountain
})
```

### 2.6 形態論ヒューリスティック (語尾剥がし)

活用語尾を剥がし、語幹末の子音が k/g かを判定する。例外リストを補完する。

```python
# 剥がし対象の接尾辞 (長い順に試行)
_MORPHOLOGICAL_SUFFIXES: tuple[str, ...] = (
    "ernas",    # 5文字: 定冠詞複数属格
    "arnas",    # 5文字: 定冠詞複数属格
    "erna",     # 4文字: 定冠詞複数
    "arna",     # 4文字: 定冠詞複数
    "ande",     # 4文字: 現在分詞
    "ning",     # 4文字: 名詞化接尾辞
    "ade",      # 3文字: 過去形
    "are",      # 3文字: 比較級 / agent
    "ast",      # 3文字: 最上級
    "igt",      # 3文字: 中性形容詞
    "er",       # 2文字: 現在形 / 複数
    "en",       # 2文字: 定冠詞 / 過去分詞
    "et",       # 2文字: 中性定冠詞
    "ar",       # 2文字: 複数
    "or",       # 2文字: 複数
    "ad",       # 2文字: 過去分詞
    "ig",       # 2文字: 形容詞
)

def _is_hard_k(word: str, pos: int) -> bool:
    """k + 前母音 の位置で、硬い /k/ を保持すべきか判定する。

    Parameters
    ----------
    word : str
        処理中の単語。
    pos : int
        'k' の位置。

    Returns
    -------
    bool
        True なら硬い /k/、False なら軟化して /ɕ/。
    """
    # 1. 静的例外リストを確認
    if word in HARD_K_WORDS:
        return True

    # 2. 形態論ヒューリスティック: 語尾を剥がして語幹を確認
    for suffix in _MORPHOLOGICAL_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            stem = word[: -len(suffix)]
            # 語幹末が k で、k の位置が語幹末に対応する場合
            if stem.endswith("k") and stem in HARD_K_STEMS:
                return True
            # 語幹末が ck の場合 (常に硬い)
            if stem.endswith("ck"):
                return True

    # 3. ck は常に硬い /k/ (becken, sickel etc.)
    if pos > 0 and word[pos - 1] == "c":
        return True

    return False


def _is_hard_g(word: str, pos: int) -> bool:
    """g + 前母音 の位置で、硬い /ɡ/ を保持すべきか判定する。

    Parameters
    ----------
    word : str
        処理中の単語。
    pos : int
        'g' の位置。

    Returns
    -------
    bool
        True なら硬い /ɡ/、False なら軟化して /j/。
    """
    # 1. 静的例外リストを確認
    if word in HARD_G_WORDS:
        return True

    # 2. -era 動詞は常に硬い g
    if word.endswith("era") or word.endswith("erar") or word.endswith("erade"):
        return True

    # 3. 形態論ヒューリスティック
    for suffix in _MORPHOLOGICAL_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix) + 1:
            stem = word[: -len(suffix)]
            if stem.endswith("g") and stem in HARD_G_STEMS:
                return True
            # gg は常に硬い
            if stem.endswith("gg"):
                return True

    # 4. gg は常に硬い (ligger, tigger)
    if pos + 1 < len(word) and word[pos + 1] == "g":
        return True

    return False
```

```python
# 語幹辞書: 語尾剥がし後の語幹で硬い k/g を持つもの
HARD_K_STEMS: frozenset[str] = frozenset({
    "lek",      # play
    "stek",     # fry/roast
    "sök",      # seek
    "tänk",     # think
    "dyk",      # dive
    "ryk",      # jerk
    "rök",      # smoke
    "smek",     # caress
    "läk",      # heal
    "märk",     # mark/notice
    "räck",     # reach/suffice
    "väck",     # wake
    "vik",      # fold
    "stryk",    # iron/stroke
    "sjunk",    # sink
    "stick",    # sting
    "back",     # reverse / hill
    "block",    # block
    "trick",    # trick
    "tryck",    # print/press
    "skick",    # send / condition
    "flick",    # girl
    "brick",    # tray
    "drick",    # drink
    "dock",     # doll
    "fick",     # pocket
    "sick",     # (part of words)
    "tack",     # thanks
    "sack",     # sack
    "pack",     # pack
    "lock",     # lid/lock
    "sock",     # (part of words)
    "rock",     # coat/rock
})

HARD_G_STEMS: frozenset[str] = frozenset({
    "lig",      # lie (position)
    "stig",     # rise
    "sug",      # suck
    "tig",      # be silent / beg
    "väg",      # weigh / road
    "äg",       # own
    "flyg",     # fly
    "ljug",     # lie (untruth)
    "lägg",     # put
    "dug",      # suffice
    "drag",     # drag
    "lag",      # team/law
    "dag",      # day
    "mag",      # stomach
    "nag",      # resentment
    "bag",      # bake
    "byg",      # build
    "tag",      # take
    "seg",      # tough
    "vag",      # vague
    "reg",      # rule
})
```

### 2.7 テストケース

```python
# TC-03a-01: sk + 前母音 → /ɧ/
assert _convert_consonant("sked", 0, True) == ("ɧ", 2)
assert _convert_consonant("sky", 0, True) == ("ɧ", 2)
assert _convert_consonant("skön", 0, True) == ("ɧ", 2)
assert _convert_consonant("skörd", 0, True) == ("ɧ", 2)
assert _convert_consonant("skär", 0, True) == ("ɧ", 2)

# TC-03a-02: sk + 後母音 → /sk/
assert _convert_consonant("skola", 0, True) == ("s k", 2)
assert _convert_consonant("skog", 0, True) == ("s k", 2)
assert _convert_consonant("skatt", 0, True) == ("s k", 2)
assert _convert_consonant("skåp", 0, True) == ("s k", 2)
assert _convert_consonant("skugg", 0, True) == ("s k", 2)

# TC-03a-03: skj/stj → /ɧ/ (無条件、最優先)
assert _convert_consonant("skjorta", 0, True) == ("ɧ", 3)
assert _convert_consonant("skjuta", 0, True) == ("ɧ", 3)
assert _convert_consonant("stjärna", 0, True) == ("ɧ", 3)
assert _convert_consonant("stjälk", 0, True) == ("ɧ", 3)

# TC-03a-04: k + 前母音 → /ɕ/ (デフォルト)
assert _convert_consonant("kind", 0, True) == ("ɕ", 1)
assert _convert_consonant("köp", 0, True) == ("ɕ", 1)
assert _convert_consonant("kyrka", 0, True) == ("ɕ", 1)

# TC-03a-05: k + 前母音、例外 → /k/
assert _convert_consonant("kille", 0, True) == ("k", 1)
assert _convert_consonant("kebab", 0, True) == ("k", 1)
assert _convert_consonant("kex", 0, True) == ("k", 1)

# TC-03a-06: g + 前母音 → /j/ (デフォルト)
assert _convert_consonant("genom", 0, True) == ("j", 1)
assert _convert_consonant("göra", 0, True) == ("j", 1)

# TC-03a-07: g + 前母音、例外 → /ɡ/
assert _convert_consonant("ger", 0, True) == ("ɡ", 1)
assert _convert_consonant("agera", 1, False) == ("ɡ", 1)  # pos=1 の g

# TC-03a-08: 活用形の形態論ヒューリスティック
assert _is_hard_k("söker", 0) == True    # sök + er → 硬い k
assert _is_hard_k("tänker", 0) == True   # tänk + er → 硬い k
assert _is_hard_g("ligger", 0) == True   # lig + ger → 硬い g (gg)
assert _is_hard_g("stiger", 0) == True   # stig + er → 硬い g

# TC-03a-09: dj/gj/hj/lj (語頭のみ)
assert _convert_consonant("djur", 0, True) == ("j", 2)
assert _convert_consonant("hjälp", 0, True) == ("j", 2)
assert _convert_consonant("ljus", 0, True) == ("j", 2)

# TC-03a-10: ng → /ŋ/
assert _convert_consonant("kung", 2, False) == ("ŋ", 2)
```

### 2.8 エッジケースと注意事項

- **ck**: 常に /k/ (hardening)。`ck` + 前母音 でも軟化しない。`flicka` → /flɪka/
- **語末 sk**: 語末の `sk` は常に /sk/。`risk` → /rɪsk/
- **固有名詞**: 固有名詞はNST辞書でカバー。OOV固有名詞は誤りの可能性あり (許容)
- **sk 後に母音がない場合**: 語末 sk → /sk/、sk + 子音 → /sk/

---

## 3. FR-03b: レトロフレックス同化

### 3.1 関数シグネチャ

```python
def apply_retroflex(phonemes: list[str]) -> list[str]:
    """音素列にレトロフレックス同化を適用する。

    /r/ + 歯茎音 (t, d, s, n, l) → レトロフレックス化。
    連鎖 (cascade) 規則あり: /r/ + s + t → /ʂʈ/。
    rr はブロック: /rr/ + 歯茎音 → レトロフレックス化しない。

    Parameters
    ----------
    phonemes : list[str]
        ベースG2Pからの音素リスト。各要素は単一IPA音素。

    Returns
    -------
    list[str]
        レトロフレックス同化適用後の音素リスト。

    Notes
    -----
    処理ステージ: ベースG2P後、ストレス付与前。
    語境界を跨いだ適用は呼び出し元で制御する (Phase 1 では非対応)。
    """
```

### 3.2 定数

```python
# 歯茎音 → レトロフレックス変換マップ
RETROFLEX_MAP: dict[str, str] = {
    "t": "ʈ",
    "d": "ɖ",
    "s": "ʂ",
    "n": "ɳ",
    "l": "ɭ",
}

# カスケード伝播可能なレトロフレックス音素
# ɭ は伝播を停止する (rl → ɭ の後は連鎖しない)
PROPAGATING_RETROFLEXES: frozenset[str] = frozenset({"ʈ", "ɖ", "ʂ", "ɳ"})
```

### 3.3 状態マシン仕様

```
状態: NORMAL → R_DETECTED → CASCADING

NORMAL:
  入力が "r" → R_DETECTED に遷移
  入力がその他 → 出力に追加、NORMAL を維持

R_DETECTED:
  入力が "r" → "rː" を出力 (rr, 重子音)、NORMAL に遷移  [ブロック]
  入力が RETROFLEX_MAP のキー →
    変換後のレトロフレックス音素を出力
    変換結果が PROPAGATING_RETROFLEXES に含まれる → CASCADING に遷移
    変換結果が ɭ → NORMAL に遷移 (ɭ は伝播停止)
  入力がその他 → "r" を出力、入力を再処理、NORMAL に遷移

CASCADING:
  入力が RETROFLEX_MAP のキー →
    変換後のレトロフレックス音素を出力
    変換結果が PROPAGATING_RETROFLEXES に含まれる → CASCADING を維持
    変換結果が ɭ → NORMAL に遷移
  入力がその他 → 入力を出力、NORMAL に遷移
```

### 3.4 アルゴリズム疑似コード

```python
def apply_retroflex(phonemes: list[str]) -> list[str]:
    result: list[str] = []
    i = 0
    n = len(phonemes)

    while i < n:
        ph = phonemes[i]

        if ph == "r":
            # 次の音素を確認
            if i + 1 < n:
                next_ph = phonemes[i + 1]

                # rr ブロック: 重子音 r、レトロフレックス化しない
                if next_ph == "r":
                    result.append("rː")
                    i += 2
                    continue

                # レトロフレックス変換
                if next_ph in RETROFLEX_MAP:
                    # /r/ を消費し、次の歯茎音をレトロフレックスに変換
                    j = i + 1
                    while j < n and phonemes[j] in RETROFLEX_MAP:
                        retro = RETROFLEX_MAP[phonemes[j]]
                        result.append(retro)
                        j += 1
                        # ɭ (retroflex lateral) はカスケードを停止
                        if retro not in PROPAGATING_RETROFLEXES:
                            break
                    i = j
                    continue

            # /r/ の後にレトロフレックス対象なし: /r/ をそのまま出力
            result.append("r")
            i += 1
            continue

        # /r/ 以外: そのまま出力
        result.append(ph)
        i += 1

    return result
```

### 3.5 rr 検出アルゴリズム

`rr` はベースG2Pの段階で検出する必要がある。綴り字レベルでの `rr` がレトロフレックスブロックの根拠。

```python
def _detect_geminate_r(word: str, pos: int) -> bool:
    """綴り字レベルで rr を検出する。

    Parameters
    ----------
    word : str
        単語全体。
    pos : int
        最初の 'r' の位置。

    Returns
    -------
    bool
        True なら rr (重子音)。
    """
    return (
        pos + 1 < len(word)
        and word[pos] == "r"
        and word[pos + 1] == "r"
    )
```

ベースG2Pでは、`rr` を検出した場合に `["r", "r"]` (2つの /r/) として出力する。`apply_retroflex()` がこれを `["rː"]` に変換し、その後の歯茎音はレトロフレックス化されない。

### 3.6 語境界処理 (Cross-word boundary)

Phase 1 では語境界を跨いだレトロフレックスは非対応。理由:

1. piper-plus のアーキテクチャは単語単位で音素化する
2. VITS モデルが暗黙的に学習する (同化は音声レベルで自然に発生)
3. NST辞書は単語内のレトロフレックスのみ記録

Phase 2 で対応する場合、`phonemize_sentence()` レベルで前の単語の末尾音素と次の単語の先頭音素を結合して `apply_retroflex()` に渡す。

### 3.7 テストケース

```python
# TC-03b-01: 基本レトロフレックス変換
assert apply_retroflex(["k", "ɔ", "r", "t"]) == ["k", "ɔ", "ʈ"]           # kort
assert apply_retroflex(["b", "uː", "r", "d"]) == ["b", "uː", "ɖ"]        # bord
assert apply_retroflex(["f", "ɔ", "r", "s"]) == ["f", "ɔ", "ʂ"]           # fors
assert apply_retroflex(["b", "ɑː", "r", "n"]) == ["b", "ɑː", "ɳ"]        # barn
assert apply_retroflex(["k", "ɑː", "r", "l"]) == ["k", "ɑː", "ɭ"]        # karl

# TC-03b-02: カスケード (連鎖)
assert apply_retroflex(["f", "œ", "r", "s", "t"]) == ["f", "œ", "ʂ", "ʈ"]        # först
assert apply_retroflex(["ɡ", "ɑː", "r", "n", "s"]) == ["ɡ", "ɑː", "ɳ", "ʂ"]    # garns

# TC-03b-03: ɭ でカスケード停止
assert apply_retroflex(["k", "ɑː", "r", "l", "s"]) == ["k", "ɑː", "ɭ", "s"]     # karls (ɭ後は伝播しない)

# TC-03b-04: rr ブロック
assert apply_retroflex(["b", "ɔ", "r", "r", "s"]) == ["b", "ɔ", "rː", "s"]       # borrs (レトロフレックス化しない)
assert apply_retroflex(["h", "ɛ", "r", "r", "ɛ"]) == ["h", "ɛ", "rː", "ɛ"]       # herre

# TC-03b-05: r + 非歯茎音 (変換なし)
assert apply_retroflex(["b", "ɑː", "r", "k"]) == ["b", "ɑː", "r", "k"]           # bark (r+k は変換しない)
assert apply_retroflex(["f", "ɑː", "r"]) == ["f", "ɑː", "r"]                     # far (語末 r はそのまま)

# TC-03b-06: 複合語内のレトロフレックス
assert apply_retroflex(["b", "ɑː", "r", "n", "d", "uː", "m"]) == ["b", "ɑː", "ɳ", "d", "uː", "m"]  # barndom (rn→ɳ、d は独立)

# TC-03b-07: 空リスト
assert apply_retroflex([]) == []
```

### 3.8 エッジケースと注意事項

- **入力の `/r/` 表現**: ベースG2Pからの音素リストでは `/r/` は `"r"` として出力される。長母音 `"rː"` は入力に含まれない (rr は `["r", "r"]` で渡される)
- **母音の `/r/` との混同**: IPA音素として `"r"` のみがトリガー。母音音素 (`"ɛr"` 等) は単一トークンなのでマッチしない
- **順序依存**: `apply_retroflex()` は左から右の単一パスで処理。逆方向のスキャンは不要

---

## 4. FR-03c: sj-sound (/ɧ/) パターン

### 4.1 概要

sj-sound (/ɧ/) はスウェーデン語固有の摩擦音で、多くの綴りパターンから生成される。FR-03a (Soft/Hard 子音分岐) と密接に統合され、特に `sk` + 前母音規則は共有される。

### 4.2 パターン優先テーブル

| 優先度 | パターン | 出力 | 条件 | 処理ステージ | 備考 |
|--------|---------|------|------|-------------|------|
| 1 | `-tion` (語末接尾辞) | `ɧ uː n` | 語末のみ | Stage 2 (FR-03g) | station, nation |
| 2 | `-sion` (語末接尾辞) | `ɧ uː n` | 語末のみ | Stage 2 (FR-03g) | passion, version |
| 3 | `-ssion` (語末接尾辞) | `ɧ uː n` | 語末のみ | Stage 2 (FR-03g) | permission, mission |
| 4 | `-age` (語末接尾辞) | `ɑː ɧ` | 語末のみ | Stage 2 (FR-03g) | garage, massage |
| 5 | `skj` | `ɧ` | 無条件 | Stage 4 (FR-03a) | skjorta, skjuta |
| 6 | `stj` | `ɧ` | 無条件 | Stage 4 (FR-03a) | stjärna, stjälk |
| 7 | `sch` | `ɧ` | 無条件 | Stage 3 (FR-03g) | schema, schack |
| 8 | `sh` | `ɧ` | 無条件 | Stage 3 (FR-03g) | show, shopping |
| 9 | `ch` | `ɧ` | 無条件 | Stage 3 (FR-03g) | chef, choklad |
| 10 | `sk` + 前母音 | `ɧ` | 前母音の前 | Stage 4 (FR-03a) | sked, sky |
| 11 | `sj` | `ɧ` | 無条件 | Stage 4 (FR-03a) | sjö, sjuk |

### 4.3 接尾辞検出アルゴリズム

```python
def _detect_sj_suffix(word: str) -> tuple[str, str] | None:
    """sj-sound を生成する接尾辞を検出する。

    Parameters
    ----------
    word : str
        処理対象の単語。

    Returns
    -------
    tuple[str, str] | None
        (語幹, 接尾辞の音素列) または None。

    Examples
    --------
    >>> _detect_sj_suffix("station")
    ("sta", "ɧ uː n")
    >>> _detect_sj_suffix("garage")
    ("gar", "ɑː ɧ")
    >>> _detect_sj_suffix("hund")
    None
    """
    # -ssion (5文字) — -sion より先に確認
    if word.endswith("ssion"):
        return (word[:-5], "ɧ uː n")
    # -tion (4文字)
    if word.endswith("tion"):
        return (word[:-4], "ɧ uː n")
    # -sion (4文字)
    if word.endswith("sion"):
        return (word[:-4], "ɧ uː n")
    # -age (3文字、語末のみ)
    if word.endswith("age"):
        return (word[:-3], "ɑː ɧ")
    return None
```

### 4.4 ローンワード例外辞書 (~30語幹)

`ch` がスウェーデン語ではデフォルト /ɧ/ だが、一部の語では /k/ または /tɕ/ になる場合がある。これらはNST辞書でカバーされるが、OOVフォールバック時の参考として記載。

```python
# ch → /ɧ/ がデフォルト。以下は辞書が必要な例外:
# (Phase 1 では ch → /ɧ/ 固定。例外はNST辞書に依存)
CH_EXCEPTIONS_K: frozenset[str] = frozenset({
    # ch → /k/ (ギリシャ語由来)
    "kör",          # choir (respelled)
    "karaktär",     # character (respelled)
    "kristus",      # Christ (respelled)
    "krom",         # chrome (respelled)
    "kronisk",      # chronic (respelled)
    # 注: スウェーデン語では多くのギリシャ語由来 ch が k に再綴りされている
})

# -age → /ɑːɧ/ がデフォルト。以下は例外候補:
AGE_LOANWORDS: frozenset[str] = frozenset({
    "garage",       # garage
    "massage",      # massage
    "sabotage",     # sabotage
    "baggage",      # baggage (英語借用)
    "bandage",      # bandage
    "collage",      # collage
    "dressage",     # dressage
    "equipage",     # equipage
    "espionage",    # espionage
    "etage",        # floor/story
    "fuselage",     # fuselage
    "kamuflage",    # camouflage
    "menage",       # menagerie
    "montage",      # montage
    "passage",      # passage
    "personage",    # personage
    "plumage",      # plumage
    "potage",       # potage
    "prestige",     # prestige (注: -ige は別パターン)
    "reportage",    # reportage
    "revansch",     # revenge (注: -sch 終わり)
    "stage",        # internship/stage
    "suffrage",     # suffrage (まれ)
    "tonnage",      # tonnage
    "trikotage",    # knitwear
    "visage",       # visage
    "voltage",      # voltage
    "vintage",      # vintage
})
```

### 4.5 /ɧ/ と /ɕ/ の区別 (FR-03a との統合)

以下の規則は FR-03a の `_convert_consonant()` 内で統合処理される。ここでは区別の仕様を明確にする。

| 綴り | 出力 | 音声学的区分 |
|------|------|------------|
| sk + 前母音 | `/ɧ/` | sj-sound (後方調音) |
| sj, skj, stj, sch, sh, ch | `/ɧ/` | sj-sound |
| k + 前母音 | `/ɕ/` | tj-sound (前方調音) |
| tj, kj | `/ɕ/` | tj-sound |

**実装上の注意**: `ɧ` と `ɕ` は別の IPA 記号 (U+0267 vs U+0255) で、PUA 割り当ても不要 (単一コードポイント)。混同するとネイティブ話者にとって明確に異なる音に聞こえるため、これらの区別は必須。

### 4.6 テストケース

```python
# TC-03c-01: 無条件パターン
assert "ɧ" in convert_word("sjö")       # sj → /ɧ/
assert "ɧ" in convert_word("sjuk")      # sj → /ɧ/
assert "ɧ" in convert_word("skjorta")   # skj → /ɧ/
assert "ɧ" in convert_word("stjärna")   # stj → /ɧ/
assert "ɧ" in convert_word("schema")    # sch → /ɧ/

# TC-03c-02: 条件付き sk + 前母音
assert "ɧ" in convert_word("sked")      # sk + e → /ɧ/
assert "ɧ" in convert_word("sky")       # sk + y → /ɧ/
assert "ɧ" in convert_word("skön")      # sk + ö → /ɧ/
assert "ɧ" not in convert_word("skola") # sk + o → /sk/ (NOT /ɧ/)
assert "ɧ" not in convert_word("skog")  # sk + o → /sk/

# TC-03c-03: 接尾辞
assert convert_word("station")[-3:] == ["ɧ", "uː", "n"]    # -tion
assert convert_word("passion")[-3:] == ["ɧ", "uː", "n"]    # -sion
assert convert_word("garage")[-2:] == ["ɑː", "ɧ"]          # -age (語末)

# TC-03c-04: /ɧ/ と /ɕ/ の区別
assert "ɧ" in convert_word("sked")  and "ɕ" not in convert_word("sked")   # sk → ɧ
assert "ɕ" in convert_word("kind")  and "ɧ" not in convert_word("kind")   # k → ɕ
assert "ɕ" in convert_word("tjugo") and "ɧ" not in convert_word("tjugo")  # tj → ɕ

# TC-03c-05: ch/sh (ローンワード)
assert "ɧ" in convert_word("chef")      # ch → /ɧ/
assert "ɧ" in convert_word("choklad")   # ch → /ɧ/
assert "ɧ" in convert_word("show")      # sh → /ɧ/
assert "ɧ" in convert_word("shopping")  # sh → /ɧ/
```

---

## 5. FR-03d: 母音長 (Complementary Quantity)

### 5.1 関数シグネチャ

```python
def get_vowel_phoneme(
    grapheme: str,
    is_stressed: bool,
    following_consonants: int,
    has_geminate_following: bool,
    is_before_r_plus_c: bool,
    is_word_final: bool,
    is_function_word: bool,
    word: str,
) -> str:
    """母音グラフェムを長短を考慮したIPA音素に変換する。

    Parameters
    ----------
    grapheme : str
        母音文字 (a, e, i, o, u, y, å, ä, ö)。
    is_stressed : bool
        この母音が強勢音節内かどうか。
    following_consonants : int
        この母音の直後に続く子音の数 (0, 1, 2+)。
    has_geminate_following : bool
        直後が重子音 (tt, ss, ll, nn, etc.) かどうか。
    is_before_r_plus_c : bool
        母音の後が r + 子音のパターンかどうか (例外: 長母音を維持)。
    is_word_final : bool
        母音が語末にあるかどうか。
    is_function_word : bool
        単語が機能語リストに含まれるかどうか。
    word : str
        単語全体 (語末 m 例外の検出用)。

    Returns
    -------
    str
        IPA母音音素 (長母音は "ː" 付き、例: "ɑː", "a")。
    """
```

### 5.2 母音変換テーブル (9グラフェム x 長/短 = 18音素)

| グラフェム | 長母音 (強勢+単子音前/語末) | 短母音 (強勢+重子音前/クラスタ前) | 非強勢 | 例 (長) | 例 (短) |
|-----------|--------------------------|-------------------------------|--------|---------|---------|
| a | ɑː | a | a | glas /ɡlɑːs/ | glass /ɡlas/ |
| e | eː | ɛ | ɛ | vet /veːt/ | vett /vɛt/ |
| i | iː | ɪ | ɪ | vit /viːt/ | vitt /vɪt/ |
| o | uː (デフォルト) / oː (例外) | ɔ | ɔ | bok /buːk/, son /soːn/ | bott /bɔt/ |
| u | ʉː | ɵ | ɵ | hus /hʉːs/ | hund /hɵnd/ |
| y | yː | ʏ | ʏ | ful /fyːl/ | full /fʏl/ |
| å | oː | ɔ | ɔ | åt /oːt/ | ått /ɔt/ |
| ä | ɛː | ɛ | ɛ | säl /sɛːl/ | säll /sɛl/ |
| ö | øː | œ | œ | öl /øːl/ | öst /œst/ |

```python
# 長母音マッピング
_LONG_VOWEL_MAP: dict[str, str] = {
    "a": "ɑː",
    "e": "eː",
    "i": "iː",
    "o": "uː",    # デフォルト。/oː/ は例外リスト参照
    "u": "ʉː",
    "y": "yː",
    "å": "oː",
    "ä": "ɛː",
    "ö": "øː",
}

# 短母音マッピング
_SHORT_VOWEL_MAP: dict[str, str] = {
    "a": "a",
    "e": "ɛ",
    "i": "ɪ",
    "o": "ɔ",
    "u": "ɵ",
    "y": "ʏ",
    "å": "ɔ",
    "ä": "ɛ",
    "ö": "œ",
}
```

### 5.3 "o" の長母音 /oː/ 例外語リスト

`o` のデフォルト長母音は /uː/ だが、以下の語では /oː/。歴史的に古い基本語彙 (stora vokaldansen の例外)。

```python
O_LONG_AS_OO: frozenset[str] = frozenset({
    # 基本語彙
    "son",          # son
    "mor",          # mother
    "bror",         # brother
    "lov",          # permission / holiday
    "dom",          # judgment / they (colloquial)
    "ton",          # tone / ton
    "zon",          # zone
    "fon",          # phone (unit)
    "ion",          # ion
    "ko",           # cow (一部方言で /koː/)
    "lo",           # lynx
    "ro",           # calm/row
    "tro",          # believe/faith
    "bo",           # live/reside
    "god",          # good
    "jord",         # earth/soil
    "ord",          # word
    "kol",          # coal/carbon
    "pol",          # pole
    "kontroll",     # control (仏語由来)
    "roll",         # role (仏語由来)
    "mol",          # (music) minor key
    "fot",          # foot
    "rot",          # root
    "blod",         # blood
    "flod",         # river/flood
    "mod",          # courage
    "nod",          # node
    "rod",          # (root of "rode")
    "tog",          # took (past tense of "ta")
})
```

**注意**: この区別は規則だけでは不完全 (~70% 精度)。NST辞書でカバーされない場合のフォールバックとして使用する。

### 5.4 子音カウントアルゴリズム

```python
def _count_following_consonants(word: str, vowel_pos: int) -> tuple[int, bool, bool]:
    """母音位置の後に続く子音の数と特性を計算する。

    Parameters
    ----------
    word : str
        単語全体。
    vowel_pos : int
        母音の位置。

    Returns
    -------
    tuple[int, bool, bool]
        (子音数, 重子音フラグ, r+C パターンフラグ)

    Examples
    --------
    >>> _count_following_consonants("glass", 2)   # a の後に ss
    (2, True, False)
    >>> _count_following_consonants("glas", 2)    # a の後に s
    (1, False, False)
    >>> _count_following_consonants("barn", 1)    # a の後に rn
    (2, False, True)
    """
    count = 0
    has_geminate = False
    is_r_plus_c = False
    i = vowel_pos + 1

    while i < len(word) and word[i] in CONSONANTS:
        count += 1
        i += 1

    # 重子音の検出
    if count >= 2:
        first_c = word[vowel_pos + 1]
        second_c = word[vowel_pos + 2]
        if first_c == second_c:
            has_geminate = True

    # r + C パターンの検出
    if count >= 2 and word[vowel_pos + 1] == "r":
        is_r_plus_c = True

    return (count, has_geminate, is_r_plus_c)
```

### 5.5 Complementary Quantity 判定ロジック

```python
def get_vowel_phoneme(
    grapheme: str,
    is_stressed: bool,
    following_consonants: int,
    has_geminate_following: bool,
    is_before_r_plus_c: bool,
    is_word_final: bool,
    is_function_word: bool,
    word: str,
) -> str:
    # 1. 非強勢母音 → 常に短母音
    if not is_stressed:
        return _SHORT_VOWEL_MAP[grapheme]

    # 2. 機能語 → 常に短母音 (短母音 + 短子音 を許容)
    if is_function_word:
        return _SHORT_VOWEL_MAP[grapheme]

    # 3. r + C 例外: 母音が長いまま
    #    例: bord → /buːrd/, barn → /bɑːrn/, fart → /fɑːrt/
    if is_before_r_plus_c:
        if grapheme == "o":
            if word in O_LONG_AS_OO:
                return "oː"
            return "uː"
        return _LONG_VOWEL_MAP[grapheme]

    # 4. 語末 m 例外: 重子音化されないが短母音
    #    例: hem → /hɛm/, rum → /rɵm/, fem → /fɛm/
    if _is_final_m_exception(word, grapheme):
        return _SHORT_VOWEL_MAP[grapheme]

    # 5. 重子音 / 子音クラスタ (2つ以上) の前 → 短母音
    if following_consonants >= 2 or has_geminate_following:
        return _SHORT_VOWEL_MAP[grapheme]

    # 6. 単子音の前 / 語末 → 長母音
    if following_consonants <= 1:
        # "o" の特殊処理: /uː/ vs /oː/
        if grapheme == "o":
            if word in O_LONG_AS_OO:
                return "oː"
            return "uː"
        return _LONG_VOWEL_MAP[grapheme]

    # フォールバック
    return _SHORT_VOWEL_MAP[grapheme]
```

### 5.6 語末 m 例外リスト

```python
FINAL_M_SHORT_WORDS: frozenset[str] = frozenset({
    "hem",          # home
    "rum",          # room
    "fem",          # five
    "lem",          # limb
    "kam",          # comb / came
    "dam",          # lady / dam
    "ham",          # harbor (archaic)
    "lam",          # lamb / paralyzed
    "ram",          # frame
    "stam",         # tribe / stem
    "tom",          # empty
    "som",          # who/which/as
    "dom",          # they (colloquial) / judgment
    "dum",          # stupid
    "gum",          # (part of "gummi")
    "glöm",         # forget (imperative)
    "dröm",         # dream
    "ström",        # stream/current
})

def _is_final_m_exception(word: str, grapheme: str) -> bool:
    """語末 m 例外を検出する。

    語末が m で終わる強勢音節は、m が重子音化されないにもかかわらず
    短母音を持つ。

    Returns
    -------
    bool
        True なら短母音を使用。
    """
    return word in FINAL_M_SHORT_WORDS and word.endswith("m")
```

### 5.7 機能語リスト

```python
FUNCTION_WORDS: frozenset[str] = frozenset({
    # 代名詞
    "jag",          # I
    "du",           # you
    "han",          # he
    "hon",          # she
    "vi",           # we
    "de",           # they
    "dem",          # them
    "den",          # it (common)
    "det",          # it (neuter)
    "sig",          # self (reflexive)
    "sin",          # his/her/its (own)
    "min",          # my
    "din",          # your
    # 前置詞
    "av",           # of/by
    "i",            # in
    "på",           # on
    "för",          # for
    "med",          # with
    "om",           # about/if
    "till",         # to
    "från",         # from
    "hos",          # at (someone's place)
    "ur",           # out of
    # 接続詞
    "och",          # and
    "men",          # but
    "att",          # that/to
    "som",          # who/which/as
    "när",          # when
    "var",          # where
    # 冠詞
    "en",           # a (common)
    "ett",          # a (neuter)
    # その他
    "är",           # is
    "har",          # has
    "kan",          # can
    "ska",          # shall
    "vill",         # want
    "inte",         # not
})
```

### 5.8 テストケース

```python
# TC-03d-01: 最小対 (長/短)
assert get_vowel_phoneme("a", True, 1, False, False, False, False, "glas") == "ɑː"   # glas (長)
assert get_vowel_phoneme("a", True, 2, True, False, False, False, "glass") == "a"     # glass (短)
assert get_vowel_phoneme("i", True, 1, False, False, False, False, "vit") == "iː"     # vit (長)
assert get_vowel_phoneme("i", True, 2, True, False, False, False, "vitt") == "ɪ"      # vitt (短)

# TC-03d-02: r + C 例外 (長母音を維持)
assert get_vowel_phoneme("a", True, 2, False, True, False, False, "barn") == "ɑː"     # barn (r+n、長)
assert get_vowel_phoneme("o", True, 2, False, True, False, False, "bord") == "uː"     # bord (r+d、長)

# TC-03d-03: 語末 m 例外 (短母音)
assert get_vowel_phoneme("e", True, 1, False, False, False, False, "hem") == "ɛ"      # hem (語末m、短)
assert get_vowel_phoneme("u", True, 1, False, False, False, False, "rum") == "ɵ"      # rum (語末m、短)

# TC-03d-04: "o" の分岐
assert get_vowel_phoneme("o", True, 1, False, False, False, False, "sol") == "uː"     # sol (デフォルト /uː/)
assert get_vowel_phoneme("o", True, 1, False, False, False, False, "son") == "oː"     # son (例外 /oː/)
assert get_vowel_phoneme("o", True, 2, False, False, False, False, "komma") == "ɔ"    # komma (短 /ɔ/)

# TC-03d-05: 機能語 (常に短母音)
assert get_vowel_phoneme("a", True, 1, False, False, False, True, "han") == "a"        # han (機能語、短)
assert get_vowel_phoneme("o", True, 1, False, False, False, True, "som") == "ɔ"        # som (機能語、短)

# TC-03d-06: 語末母音 (長)
assert get_vowel_phoneme("a", True, 0, False, False, True, False, "ja") == "ɑː"       # ja (語末、長)

# TC-03d-07: "å" の変換
assert get_vowel_phoneme("å", True, 1, False, False, False, False, "lås") == "oː"     # lås (長)
assert get_vowel_phoneme("å", True, 2, True, False, False, False, "åtta") == "ɔ"      # åtta (短)
```

---

## 6. FR-03e: 非強勢母音短縮

### 6.1 関数シグネチャ

```python
def get_unstressed_vowel(
    grapheme: str,
    suffix_context: str | None,
) -> str:
    """非強勢位置の母音をIPAに変換する。

    Central Standard Swedish ではシュワー (/ə/) を使用しない。
    非強勢位置では各母音の短い変種を使用する。

    Parameters
    ----------
    grapheme : str
        母音文字。
    suffix_context : str | None
        この母音が含まれる語末接尾辞。None なら一般的な非強勢位置。
        例: "a" (語末-a), "en" (語末-en), "er" (語末-er), "ar" (語末-ar),
            "or" (語末-or), "ig" (語末-ig), "lig" (語末-lig)

    Returns
    -------
    str
        IPA母音音素 (常に短母音)。
    """
```

### 6.2 接尾辞別短縮テーブル

| 語末パターン | 母音グラフェム | IPA出力 | 接尾辞全体のIPA | 例 |
|------------|-------------|---------|---------------|-----|
| `-a` | a | `a` | `a` | gata → ɡɑːta, flicka → flɪka |
| `-e` | e | `ɛ` | `ɛ` | pojke → pɔjkɛ, gamle → ɡamlɛ |
| `-en` | e | `ɛ` | `ɛ n` | vatten → vatɛn, liten → liːtɛn |
| `-er` | e | `ɛ` | `ɛ r` | söker → søːkɛr, vacker → vakɛr |
| `-el` | e | `ɛ` | `ɛ l` | enkel → ɛŋkɛl, fågel → fɔːɡɛl |
| `-ar` | a | `a` | `a r` | bilar → biːlar, flickar → flɪkar |
| `-or` | o | `ɔ` | `ɔ r` | flickor → flɪkɔr |
| `-ig` | i | `ɪ` | `ɪ ɡ` | viktig → vɪktɪɡ, rolig → ruːlɪɡ |
| `-lig` | i | `ɪ` | `l ɪ ɡ` | möjlig → møːjlɪɡ, vanlig → vɑːnlɪɡ |
| (一般) | 各文字 | `_SHORT_VOWEL_MAP` | - | - |

### 6.3 アルゴリズム疑似コード

```python
# 非強勢接尾辞の検出 (長い順)
_UNSTRESSED_SUFFIXES: tuple[tuple[str, list[str]], ...] = (
    ("lig",  ["l", "ɪ", "ɡ"]),
    ("ning", ["n", "ɪ", "ŋ"]),
    ("ande", ["a", "n", "d", "ɛ"]),
    ("erna", ["ɛ", "r", "n", "a"]),
    ("arna", ["a", "r", "n", "a"]),
    ("en",   ["ɛ", "n"]),
    ("er",   ["ɛ", "r"]),
    ("el",   ["ɛ", "l"]),
    ("et",   ["ɛ", "t"]),
    ("ar",   ["a", "r"]),
    ("or",   ["ɔ", "r"]),
    ("ig",   ["ɪ", "ɡ"]),
    ("ad",   ["a", "d"]),
    ("a",    ["a"]),
    ("e",    ["ɛ"]),
    ("o",    ["ɔ"]),
)

def _apply_unstressed_suffix(word: str) -> tuple[str, list[str]] | None:
    """非強勢接尾辞を検出し、語幹と接尾辞音素列を返す。

    単音節語は接尾辞剥がしの対象外 (全体が強勢音節)。

    Returns
    -------
    tuple[str, list[str]] | None
        (語幹, 接尾辞の音素リスト)。None なら接尾辞なし。
    """
    # 単音節語はスキップ
    vowel_count = sum(1 for c in word if c in ALL_VOWELS)
    if vowel_count <= 1:
        return None

    for suffix, phonemes in _UNSTRESSED_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            return (word[:-len(suffix)], phonemes)

    return None


def get_unstressed_vowel(grapheme: str, suffix_context: str | None) -> str:
    # 接尾辞コンテキストがある場合は接尾辞テーブルに従う
    if suffix_context is not None:
        # 接尾辞内の母音は常に短母音
        return _SHORT_VOWEL_MAP.get(grapheme, grapheme)

    # 一般的な非強勢位置: 短母音を使用
    return _SHORT_VOWEL_MAP.get(grapheme, grapheme)
```

### 6.4 テストケース

```python
# TC-03e-01: 語末 -a (短い [a])
# gata → [ɡ, ɑː, t, a]  (NOT [ɡ, ɑː, t, ɑː])
assert get_unstressed_vowel("a", "a") == "a"
# 統合テスト: 語末 -a は長母音化しない
assert convert_word("gata")[-1] == "a"
assert convert_word("flicka")[-1] == "a"

# TC-03e-02: 語末 -e (短い [ɛ])
assert get_unstressed_vowel("e", "e") == "ɛ"
assert convert_word("pojke")[-1] == "ɛ"

# TC-03e-03: 語末 -en
assert get_unstressed_vowel("e", "en") == "ɛ"
# vatten → [..., v, a, t, ɛ, n]
assert convert_word("vatten")[-2:] == ["ɛ", "n"]

# TC-03e-04: 語末 -er
assert get_unstressed_vowel("e", "er") == "ɛ"
assert convert_word("söker")[-2:] == ["ɛ", "r"]

# TC-03e-05: 語末 -ar
assert get_unstressed_vowel("a", "ar") == "a"
assert convert_word("bilar")[-2:] == ["a", "r"]

# TC-03e-06: 語末 -or
assert get_unstressed_vowel("o", "or") == "ɔ"
assert convert_word("flickor")[-2:] == ["ɔ", "r"]

# TC-03e-07: 語末 -ig
assert get_unstressed_vowel("i", "ig") == "ɪ"
assert convert_word("viktig")[-2:] == ["ɪ", "ɡ"]

# TC-03e-08: 語末 -lig
assert get_unstressed_vowel("i", "lig") == "ɪ"
# möjlig → [..., m, øː, j, l, ɪ, ɡ]
assert convert_word("möjlig")[-3:] == ["l", "ɪ", "ɡ"]
```

---

## 7. FR-03f: ストレス検出

### 7.1 関数シグネチャ

```python
from enum import IntEnum

class StressLevel(IntEnum):
    """ストレスレベル。"""
    NONE = 0        # 非強勢
    SECONDARY = 1   # 副ストレス (ˌ)
    PRIMARY = 2     # 主ストレス (ˈ)


def detect_stress(word: str) -> list[StressLevel]:
    """単語の各音節のストレスレベルを検出する。

    Parameters
    ----------
    word : str
        小文字正規化済みの単語。

    Returns
    -------
    list[StressLevel]
        各音節のストレスレベル。リスト長 = 音節数。

    Notes
    -----
    優先順位:
      1. 機能語 → ストレスなし (文レベルで弱化)
      2. 単音節語 → 主ストレス
      3. ストレス吸引接尾辞 → 接尾辞にストレス
      4. 非ストレス接頭辞 → 第2音節にストレス
      5. デフォルト → 第1音節に主ストレス

    Examples
    --------
    >>> detect_stress("flicka")
    [StressLevel.PRIMARY, StressLevel.NONE]
    >>> detect_stress("station")
    [StressLevel.NONE, StressLevel.PRIMARY]
    >>> detect_stress("berätta")
    [StressLevel.NONE, StressLevel.PRIMARY, StressLevel.NONE]
    """
```

### 7.2 優先順位アルゴリズム (5レベル)

```
Level 1: 機能語チェック
  word が FUNCTION_WORDS に含まれる
  → [StressLevel.NONE] * 音節数
  (文レベルのプロソディで弱化。ただし単独発話では主ストレスを付与する
   ことも可能。Phase 1 では機能語は非強勢扱いとする。)

Level 2: 単音節語チェック
  音節数 == 1
  → [StressLevel.PRIMARY]

Level 3: ストレス吸引接尾辞チェック
  word が STRESS_ATTRACTING_SUFFIXES のいずれかで終わる
  → 接尾辞の最初の音節に PRIMARY、他は NONE

Level 4: 非ストレス接頭辞チェック
  word が UNSTRESSED_PREFIXES のいずれかで始まる
  → 接頭辞直後の音節に PRIMARY、他は NONE

Level 5: デフォルト
  → 第1音節に PRIMARY、他は NONE
```

### 7.3 非ストレス接頭辞リスト

```python
UNSTRESSED_PREFIXES: tuple[str, ...] = (
    "be",       # betala, berätta, besvara
    "för",      # förklara, förstå, försöka
    "ge",       # gestalta (まれ)
    "er",       # erfara, erbjuda, erkänna
    "an",       # anmäla, anlända (注: 一部は第1音節ストレス)
)
```

**注意**: `an-` は複合語の前要素として第1音節ストレスを持つ場合もある (`anbud` = AN-bud)。Phase 1 では `an-` を非ストレス接頭辞として扱い、辞書でカバーされない場合のみ影響する。

### 7.4 ストレス吸引接尾辞リスト

```python
STRESS_ATTRACTING_SUFFIXES: tuple[tuple[str, int], ...] = (
    # (接尾辞, 接尾辞内のストレス音節オフセット)
    # オフセット: 接尾辞の先頭からの音節数 (0-indexed)
    ("tion",   0),    # sta-TION, na-TION
    ("sion",   0),    # pas-SION, ver-SION
    ("ssion",  0),    # mis-SION, per-mis-SION
    ("itet",   0),    # kva-li-TET, rea-li-TET
    ("eri",    0),    # ba-ge-RI, fis-ke-RI
    ("era",    0),    # re-a-GE-ra (注: 実際は -era の前の音節)
    ("ist",    0),    # ar-TIST, tu-RIST
    ("ör",     0),    # di-rek-TÖR, re-dak-TÖR
    ("ment",   0),    # mo-MENT, do-ku-MENT
    ("ans",    0),    # ba-LANS, tole-RANS
    ("ens",    0),    # exi-STENS, konse-KVENS
    ("ell",    0),    # for-MELL, of-fi-ci-ELL
    ("ent",    0),    # stu-DENT, pa-ti-ENT
    ("ant",    0),    # ele-GANT, re-le-VANT
    ("ik",     0),    # mu-SIK, fa-BRIK, pla-STIK
    ("ur",     0),    # na-TUR, kul-TUR, struk-TUR
    ("al",     0),    # na-tio-NELL → -al: for-MAL, lo-KAL
    ("ös",     0),    # ner-VÖS, gene-RÖS
)
```

### 7.5 音節分割アルゴリズム (簡易版)

```python
def _count_syllables(word: str) -> int:
    """単語の音節数を母音の塊から推定する。

    連続する母音は1音節として扱う (二重母音扱い)。
    """
    count = 0
    prev_vowel = False
    for ch in word:
        if ch in ALL_VOWELS:
            if not prev_vowel:
                count += 1
            prev_vowel = True
        else:
            prev_vowel = False
    return max(count, 1)  # 最低1音節


def _get_syllable_index(word: str, char_pos: int) -> int:
    """文字位置から音節インデックスを推定する。

    Returns
    -------
    int
        0-indexed の音節番号。
    """
    syllable = 0
    prev_vowel = False
    for i, ch in enumerate(word):
        if i >= char_pos:
            break
        if ch in ALL_VOWELS:
            if not prev_vowel:
                syllable += 1
            prev_vowel = True
        else:
            prev_vowel = False
    return syllable
```

### 7.6 アルゴリズム疑似コード

```python
def detect_stress(word: str) -> list[StressLevel]:
    n_syllables = _count_syllables(word)

    # Level 1: 機能語 → ストレスなし
    if word in FUNCTION_WORDS:
        return [StressLevel.NONE] * n_syllables

    # Level 2: 単音節語 → 主ストレス
    if n_syllables == 1:
        return [StressLevel.PRIMARY]

    # Level 3: ストレス吸引接尾辞
    for suffix, offset in STRESS_ATTRACTING_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            # 接尾辞の開始位置を特定
            suffix_start = len(word) - len(suffix)
            stressed_syllable = _get_syllable_index(word, suffix_start) + offset

            result = [StressLevel.NONE] * n_syllables
            if stressed_syllable < n_syllables:
                result[stressed_syllable] = StressLevel.PRIMARY
            else:
                result[-1] = StressLevel.PRIMARY
            return result

    # Level 4: 非ストレス接頭辞 → 第2音節にストレス
    for prefix in UNSTRESSED_PREFIXES:
        if word.startswith(prefix) and len(word) > len(prefix) + 1:
            # 接頭辞の後の最初の母音がある音節にストレス
            result = [StressLevel.NONE] * n_syllables
            if n_syllables >= 2:
                result[1] = StressLevel.PRIMARY
            else:
                result[0] = StressLevel.PRIMARY
            return result

    # Level 5: デフォルト → 第1音節に主ストレス
    result = [StressLevel.NONE] * n_syllables
    result[0] = StressLevel.PRIMARY
    return result
```

### 7.7 ストレスマーカー挿入

```python
def _apply_stress_markers(
    phonemes: list[str],
    stress_pattern: list[StressLevel],
    syllable_boundaries: list[int],
) -> list[str]:
    """音素列にストレスマーカー (ˈ/ˌ) を挿入する。

    Parameters
    ----------
    phonemes : list[str]
        音素列。
    stress_pattern : list[StressLevel]
        各音節のストレスレベル。
    syllable_boundaries : list[int]
        各音節の開始位置 (音素列内のインデックス)。

    Returns
    -------
    list[str]
        ストレスマーカー挿入後の音素列。
    """
    result: list[str] = []
    boundary_set = set(syllable_boundaries)

    syllable_idx = 0
    for i, ph in enumerate(phonemes):
        if i in boundary_set:
            stress = stress_pattern[syllable_idx] if syllable_idx < len(stress_pattern) else StressLevel.NONE
            if stress == StressLevel.PRIMARY:
                result.append("ˈ")
            elif stress == StressLevel.SECONDARY:
                result.append("ˌ")
            syllable_idx += 1
        result.append(ph)

    return result
```

### 7.8 テストケース

```python
# TC-03f-01: デフォルト第1音節ストレス
assert detect_stress("flicka") == [StressLevel.PRIMARY, StressLevel.NONE]
assert detect_stress("vatten") == [StressLevel.PRIMARY, StressLevel.NONE]
assert detect_stress("huset") == [StressLevel.PRIMARY, StressLevel.NONE]

# TC-03f-02: 単音節語
assert detect_stress("bil") == [StressLevel.PRIMARY]
assert detect_stress("hus") == [StressLevel.PRIMARY]

# TC-03f-03: ストレス吸引接尾辞
assert detect_stress("station") == [StressLevel.NONE, StressLevel.PRIMARY]
assert detect_stress("universitet") == [StressLevel.NONE, StressLevel.NONE, StressLevel.NONE, StressLevel.PRIMARY]  # -itet
assert detect_stress("bageri") == [StressLevel.NONE, StressLevel.NONE, StressLevel.PRIMARY]  # -eri
assert detect_stress("artist") == [StressLevel.NONE, StressLevel.PRIMARY]  # -ist

# TC-03f-04: 非ストレス接頭辞
assert detect_stress("betala") == [StressLevel.NONE, StressLevel.PRIMARY, StressLevel.NONE]
assert detect_stress("förklara") == [StressLevel.NONE, StressLevel.PRIMARY, StressLevel.NONE]
assert detect_stress("erkänna") == [StressLevel.NONE, StressLevel.PRIMARY, StressLevel.NONE]

# TC-03f-05: 機能語 (ストレスなし)
assert detect_stress("och") == [StressLevel.NONE]
assert detect_stress("men") == [StressLevel.NONE]
assert detect_stress("att") == [StressLevel.NONE]

# TC-03f-06: ストレス吸引 + 接頭辞 (接尾辞が優先)
assert detect_stress("beställning")[0] == StressLevel.NONE  # be- は非ストレス
# beställning: be-STÄLL-ning → 第2音節
```

---

## 8. FR-03g: ローンワード規則

### 8.1 関数シグネチャ

```python
def detect_loanword_suffix(word: str) -> tuple[str, str] | None:
    """ローンワード接尾辞を検出し、語幹と接尾辞音素列を返す。

    ネイティブG2P規則の前に適用される (Stage 2)。

    Parameters
    ----------
    word : str
        処理対象の単語 (小文字正規化済み)。

    Returns
    -------
    tuple[str, str] | None
        (語幹, 接尾辞の音素列文字列)。None なら該当なし。
        音素列はスペース区切り。

    Examples
    --------
    >>> detect_loanword_suffix("station")
    ("sta", "ɧ uː n")
    >>> detect_loanword_suffix("garage")
    ("gar", "ɑː ɧ")
    >>> detect_loanword_suffix("museum")
    ("mus", "eː ɵ m")
    >>> detect_loanword_suffix("hund")
    None
    """


def detect_loanword_prefix(
    word: str,
    pos: int,
) -> tuple[str, int] | None:
    """ローンワード接頭辞/字母パターンを検出する。

    ネイティブG2P規則の前に適用される (Stage 3)。
    _convert_consonant() が処理できないパターンを補完する。

    Parameters
    ----------
    word : str
        処理対象の単語。
    pos : int
        現在の文字位置。

    Returns
    -------
    tuple[str, int] | None
        (IPA音素文字列, 消費した文字数)。None なら該当なし。

    Examples
    --------
    >>> detect_loanword_prefix("filosofi", 0)
    None  # ph- ではない
    >>> detect_loanword_prefix("photo", 0)
    ("f", 2)  # ph → /f/
    """
```

### 8.2 接尾辞規則テーブル

接尾辞は長い順にマッチさせる (最長一致)。

```python
_LOANWORD_SUFFIX_RULES: tuple[tuple[str, str], ...] = (
    # (接尾辞パターン, 音素列 (スペース区切り))
    # --- 5文字 ---
    ("ssion",  "ɧ uː n"),      # permission, mission
    # --- 4文字 ---
    ("tion",   "ɧ uː n"),      # station, nation, information
    ("sion",   "ɧ uː n"),      # passion, version, television
    # --- 3文字 ---
    ("age",    "ɑː ɧ"),        # garage, massage, sabotage
    ("eur",    "øː r"),         # (respelled -ör が多いが、原語保持もあり)
    ("eum",    "eː ɵ m"),       # museum
    ("ium",    "ɪ ɵ m"),        # stadium, medium
)
```

### 8.3 接頭辞/字母規則テーブル

```python
_LOANWORD_PREFIX_RULES: tuple[tuple[str, str, int], ...] = (
    # (パターン, IPA出力, 消費文字数)
    # 注: sch, sh, ch は FR-03a の _convert_consonant() でも処理されるが、
    #     Stage 3 として明示的にローンワード規則を先行適用する場合に使用。
    ("sch",  "ɧ",  3),         # schema, schack, schweizisk
    ("sh",   "ɧ",  2),         # show, shopping, shampoo
    ("ch",   "ɧ",  2),         # chef, choklad, chans, charm
    ("ph",   "f",  2),         # photo → foto (多くは再綴り済み)
    ("th",   "t",  2),         # teater → teater (多くは再綴り済み)
)
```

### 8.4 処理順序

```
1. detect_loanword_suffix(word)
   → マッチ: 語幹を切り出し、語幹部分をネイティブ規則で処理。
             接尾辞音素列を語幹音素列の後に結合。
   → ミス:  Stage 3 へ。

2. _convert_consonant() 内で sch/sh/ch/ph/th を処理
   → これらはネイティブ規則テーブル (2.2) に統合済み。
   → detect_loanword_prefix() は _convert_consonant() が処理しない
     追加パターンがある場合のみ使用。Phase 1 では全てのローンワード
     字母パターンが _convert_consonant() に統合されているため、
     detect_loanword_prefix() は将来拡張用。

3. ネイティブ G2P 規則 (Stage 4)
```

### 8.5 アルゴリズム疑似コード

```python
def detect_loanword_suffix(word: str) -> tuple[str, str] | None:
    for suffix, phonemes in _LOANWORD_SUFFIX_RULES:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if len(stem) >= 1:  # 語幹が空でないこと
                return (stem, phonemes)
    return None


def detect_loanword_prefix(word: str, pos: int) -> tuple[str, int] | None:
    remaining = word[pos:]
    for pattern, ipa, consumed in _LOANWORD_PREFIX_RULES:
        if remaining.startswith(pattern):
            return (ipa, consumed)
    return None


def _convert_word_with_loanwords(word: str) -> list[str]:
    """ローンワード規則を適用した上で単語を音素化する。

    1. 接尾辞規則を先に確認
    2. 語幹部分をネイティブ規則で音素化
    3. 接尾辞音素列を結合
    """
    phonemes: list[str] = []

    # Stage 2: 接尾辞検出
    suffix_result = detect_loanword_suffix(word)
    if suffix_result is not None:
        stem, suffix_phonemes = suffix_result
        # 語幹をネイティブ規則で処理
        stem_phonemes = _convert_word_native(stem)
        # 接尾辞音素を追加
        phonemes = stem_phonemes + suffix_phonemes.split()
        return phonemes

    # Stage 3-4: 接頭辞/字母は _convert_consonant() に統合済み
    phonemes = _convert_word_native(word)
    return phonemes
```

### 8.6 テストケース

```python
# TC-03g-01: -tion 接尾辞
assert detect_loanword_suffix("station") == ("sta", "ɧ uː n")
assert detect_loanword_suffix("nation") == ("na", "ɧ uː n")
assert detect_loanword_suffix("information") == ("informa", "ɧ uː n")

# TC-03g-02: -sion 接尾辞
assert detect_loanword_suffix("passion") == ("pas", "ɧ uː n")
assert detect_loanword_suffix("version") == ("ver", "ɧ uː n")
assert detect_loanword_suffix("television") == ("televi", "ɧ uː n")

# TC-03g-03: -ssion 接尾辞 (-sion より優先)
assert detect_loanword_suffix("mission") == ("mi", "ɧ uː n")
assert detect_loanword_suffix("permission") == ("permi", "ɧ uː n")

# TC-03g-04: -age 接尾辞
assert detect_loanword_suffix("garage") == ("gar", "ɑː ɧ")
assert detect_loanword_suffix("massage") == ("mass", "ɑː ɧ")
assert detect_loanword_suffix("sabotage") == ("sabot", "ɑː ɧ")

# TC-03g-05: -eum/-ium 接尾辞
assert detect_loanword_suffix("museum") == ("mus", "eː ɵ m")
assert detect_loanword_suffix("stadium") == ("stad", "ɪ ɵ m")

# TC-03g-06: 接頭辞/字母 (sch/sh/ch/ph/th)
assert detect_loanword_prefix("schema", 0) == ("ɧ", 3)
assert detect_loanword_prefix("shopping", 0) == ("ɧ", 2)
assert detect_loanword_prefix("chef", 0) == ("ɧ", 2)
assert detect_loanword_prefix("photo", 0) == ("f", 2)
assert detect_loanword_prefix("thema", 0) == ("t", 2)

# TC-03g-07: 該当なし
assert detect_loanword_suffix("hund") is None
assert detect_loanword_suffix("flicka") is None
assert detect_loanword_prefix("hund", 0) is None

# TC-03g-08: 統合テスト (接尾辞 + ネイティブ語幹)
# station → sta (ネイティブ) + ɧuːn (接尾辞)
result = _convert_word_with_loanwords("station")
assert "ɧ" in result
assert "uː" in result
assert "n" in result

# TC-03g-09: -eur 接尾辞
assert detect_loanword_suffix("chaufför") is None  # -för は -eur に非該当 (再綴り済み)
# 注: スウェーデン語では多くの -eur が -ör に再綴りされている

# TC-03g-10: 語幹が空の場合は None
assert detect_loanword_suffix("tion") is None  # 語幹なし (4文字全体が接尾辞)
```

---

## 9. 処理パイプライン統合

### 9.1 _convert_word_native() の統合アルゴリズム

```python
def _convert_word_native(word: str) -> list[str]:
    """ネイティブG2P規則で単語を音素列に変換する。

    FR-03a (Soft/Hard), FR-03c (sj-sound), FR-03d (母音長) を統合。
    レトロフレックス (FR-03b) とストレス (FR-03f) は後段で適用。

    Parameters
    ----------
    word : str
        処理対象の単語 (小文字正規化済み)。

    Returns
    -------
    list[str]
        IPA音素のリスト。
    """
    phonemes: list[str] = []
    i = 0
    n = len(word)

    # ストレス検出 (母音長判定に必要)
    stress_pattern = detect_stress(word)
    is_function = word in FUNCTION_WORDS

    # 音節カウンター (簡易: 母音ごとにインクリメント)
    syllable_idx = 0
    prev_was_vowel = False

    while i < n:
        ch = word[i]

        # --- 母音処理 ---
        if ch in ALL_VOWELS:
            if not prev_was_vowel:
                # 新しい音節の開始
                is_stressed = (
                    syllable_idx < len(stress_pattern)
                    and stress_pattern[syllable_idx] == StressLevel.PRIMARY
                )
            prev_was_vowel = True

            # 非強勢接尾辞の処理 (FR-03e)
            suffix_result = _apply_unstressed_suffix(word)
            if suffix_result and i >= len(word) - len(_get_suffix_text(suffix_result)):
                # 接尾辞内の母音: 常に短母音
                phonemes.append(_SHORT_VOWEL_MAP[ch])
                i += 1
                continue

            # 母音長の判定 (FR-03d)
            following_c, has_gem, is_r_c = _count_following_consonants(word, i)
            vowel = get_vowel_phoneme(
                grapheme=ch,
                is_stressed=is_stressed,
                following_consonants=following_c,
                has_geminate_following=has_gem,
                is_before_r_plus_c=is_r_c,
                is_word_final=(i == n - 1),
                is_function_word=is_function,
                word=word,
            )
            phonemes.append(vowel)
            i += 1
            continue

        # --- 子音処理 ---
        prev_was_vowel = False

        # 音節カウンター更新
        # (母音→子音の遷移で音節をインクリメント)
        # 注: 実際のインクリメントは次の母音で行う

        # FR-03a: Soft/Hard 子音分岐 + FR-03c: sj-sound
        ipa, consumed = _convert_consonant(word, i, is_word_initial=(i == 0))

        # 複数音素の場合 (例: "s k" → ["s", "k"])
        for ph in ipa.split():
            phonemes.append(ph)

        # 重子音の検出 (同一文字の連続)
        if consumed == 1 and i + 1 < n and word[i + 1] == ch and ch in CONSONANTS:
            # 重子音: 長子音として出力 (例: tt → tː)
            # ただし、_convert_consonant() が2文字消費した場合は不要
            phonemes.append(ch + "ː") if False else None  # 重子音は省略 (短母音で表現)
            # スウェーデン語では重子音は音韻的に [短母音] + [単子音] として実現される
            # 重子音記号は使用しない (短母音の方で区別)

        i += consumed
        if not prev_was_vowel and ch in ALL_VOWELS:
            syllable_idx += 1

    return phonemes
```

### 9.2 単語レベルの統合パイプライン

> **設計ノート: インスタンスメソッド vs モジュールレベル関数**
>
> 実装では `_phonemize_word` は `SwedishPhonemizer._g2p_word(self, word)` として
> **インスタンスメソッド** になる。Spanish/French の `_g2p_word()` がモジュールレベル関数
> であるのと異なり、SwedishPhonemizer は NST辞書への参照 (`self._dict`) を保持する必要が
> あるため、`self` アクセスが必須となる。

```python
def _phonemize_word(word: str, dict_data: dict[str, str] | None) -> list[str]:
    """単語を音素列に変換する統合パイプライン。

    Parameters
    ----------
    word : str
        処理対象の単語 (小文字正規化済み)。
    dict_data : dict[str, str] | None
        NST辞書。None なら rule-based のみ。

    Returns
    -------
    list[str]
        IPA音素のリスト。
    """
    # Stage 1: NST辞書ルックアップ
    if dict_data and word in dict_data:
        return list(dict_data[word])  # 辞書のIPA文字列を音素リストに

    # Stage 2-4: Rule-based G2P (ローンワード規則 + ネイティブG2P + 非強勢母音短縮)
    phonemes = _convert_word_with_loanwords(word)  # FR-03g + FR-03a/c/d/e

    # Stage 5: レトロフレックス同化 (FR-03b)
    phonemes = apply_retroflex(phonemes)

    # Stage 6: ストレスマーカー挿入 (FR-03f)
    stress_pattern = detect_stress(word)
    syllable_bounds = _find_syllable_boundaries_phoneme(phonemes)
    phonemes = _apply_stress_markers(phonemes, stress_pattern, syllable_bounds)

    return phonemes
```

### 9.3 処理順序の根拠

| 処理 | タイミング | 根拠 |
|------|----------|------|
| ローンワード接尾辞 (FR-03g) | 最初 | 接尾辞を切り離してからネイティブ規則を適用。-tion を t+i+o+n として処理させない |
| Soft/Hard (FR-03a) | ネイティブG2P内 | 子音変換の基盤。他の全規則の前提 |
| sj-sound (FR-03c) | FR-03a に統合 | sk + 前母音規則は Soft/Hard と共有 |
| 母音長 (FR-03d) | ネイティブG2P内 | ストレス情報が必要だが、ストレスマーカー挿入前に母音選択を確定 |
| 非強勢短縮 (FR-03e) | ネイティブG2P内 | 母音長判定の一部として処理 |
| レトロフレックス (FR-03b) | ネイティブG2P後 | 音素レベルの後処理。r+C のパターンマッチは音素列に対して行う |
| ストレス (FR-03f) | 最後 | ストレスマーカーは音素列の完成後に挿入 |

### 9.4 エラーハンドリング

```python
# 空文字列
def _phonemize_word("", None) -> []

# 句読点のみ
# → トークン化段階で句読点と単語を分離。句読点はそのまま透過。

# 未知の文字 (数字、記号等)
# → Phase 1 では無視 (空出力)。数字展開は Phase 4。
# 警告ログを出力:
#   _LOGGER.warning("Unknown character '%s' in word '%s'", ch, word)

# 辞書ファイルの欠如
# → dict_data=None で rule-based のみ動作。エラーにしない。
# 初期化時のログ:
#   _LOGGER.info("No dictionary loaded; using rule-based G2P only")
```

---

## 付録 A: 全テストケースサマリ

| カテゴリ | ID範囲 | テスト数 | 対象FR |
|---------|--------|---------|--------|
| Soft/Hard 基本 | TC-03a-01 -- TC-03a-05 | 25 | FR-03a |
| Soft/Hard 例外 | TC-03a-06 -- TC-03a-08 | 10 | FR-03a |
| Soft/Hard 語頭 | TC-03a-09 -- TC-03a-10 | 5 | FR-03a |
| レトロフレックス基本 | TC-03b-01 | 5 | FR-03b |
| レトロフレックスカスケード | TC-03b-02 -- TC-03b-03 | 3 | FR-03b |
| レトロフレックスブロック | TC-03b-04 -- TC-03b-05 | 4 | FR-03b |
| レトロフレックス複合 | TC-03b-06 -- TC-03b-07 | 2 | FR-03b |
| sj-sound 無条件 | TC-03c-01 | 5 | FR-03c |
| sj-sound 条件付き | TC-03c-02 | 5 | FR-03c |
| sj-sound 接尾辞 | TC-03c-03 | 3 | FR-03c |
| sj-sound 区別 | TC-03c-04 -- TC-03c-05 | 7 | FR-03c |
| 母音長 最小対 | TC-03d-01 | 4 | FR-03d |
| 母音長 r+C例外 | TC-03d-02 | 2 | FR-03d |
| 母音長 語末m | TC-03d-03 | 2 | FR-03d |
| 母音長 "o" 分岐 | TC-03d-04 | 3 | FR-03d |
| 母音長 機能語 | TC-03d-05 | 2 | FR-03d |
| 母音長 語末/å | TC-03d-06 -- TC-03d-07 | 3 | FR-03d |
| 非強勢 語末母音 | TC-03e-01 -- TC-03e-02 | 4 | FR-03e |
| 非強勢 接尾辞 | TC-03e-03 -- TC-03e-08 | 12 | FR-03e |
| ストレス デフォルト | TC-03f-01 | 3 | FR-03f |
| ストレス 単音節 | TC-03f-02 | 2 | FR-03f |
| ストレス 吸引接尾辞 | TC-03f-03 | 4 | FR-03f |
| ストレス 接頭辞 | TC-03f-04 | 3 | FR-03f |
| ストレス 機能語 | TC-03f-05 -- TC-03f-06 | 4 | FR-03f |
| ローンワード 接尾辞 | TC-03g-01 -- TC-03g-05 | 14 | FR-03g |
| ローンワード 接頭辞 | TC-03g-06 | 5 | FR-03g |
| ローンワード 境界 | TC-03g-07 -- TC-03g-10 | 6 | FR-03g |
| **合計** | | **~145** | |

---

## 付録 B: 音素出力形式

### B.1 音素リスト形式

各関数の出力は `list[str]` で、各要素は以下のいずれか:

| 種別 | 例 | 説明 |
|------|-----|------|
| 単一IPA音素 | `"b"`, `"ɧ"`, `"ɕ"` | 1コードポイントの音素 |
| 長母音 | `"ɑː"`, `"iː"`, `"uː"` | 2コードポイント (母音+長音記号) |
| ストレスマーカー | `"ˈ"`, `"ˌ"` | 音素の前に挿入 |

### B.2 _convert_consonant() の返値形式

`_convert_consonant()` はスペース区切り文字列を返す。呼び出し元が `.split()` で分割する。

| 返値 | 分割後 | 例 |
|------|--------|-----|
| `"ɧ"` | `["ɧ"]` | sk + 前母音 |
| `"s k"` | `["s", "k"]` | sk + 後母音 |
| `"ɕ"` | `["ɕ"]` | k + 前母音 |
| `"ŋ"` | `["ŋ"]` | ng |
| `"k s"` | `["k", "s"]` | x のデフォルト変換 |
