# G2P 独立パッケージ化 -- 要求定義

> 作成日: 2026-03-31
> ベースドキュメント: `docs/design/g2p-standalone-package.md`

本ドキュメントは全 3 プラットフォームの要求定義を定める。C# は DotNetG2P (NuGet) が既に独立 G2P パッケージとして機能しているため対象外。

- Phase 1: Python + Rust (セクション 1-4)
- ~~Phase 2: C# NuGet~~ → **対象外**: DotNetG2P が既に独立 G2P パッケージとして公開済み (セクション 5-6 は参考情報として残す)
- Phase 2: JS/WASM npm (旧 Phase 3、セクション 7-8)
- 共通機能要求 (セクション 9)
- 共通非機能要求 (セクション 10)
- 統合・マイグレーション要求 (セクション 11)
- リリース戦略 (セクション 12)
- 現状からの差分サマリ (セクション 13)

**プラットフォーム別要求 (セクション 1-8)** は各プラットフォーム固有の実装詳細を定義し、**共通要求 (セクション 9-10)** は全プラットフォーム横断の統一仕様を定義する。共通要求はプラットフォーム別要求より優先する。

---

## 目次

1. [Python パッケージ (`piper-g2p`) 機能要求](#1-python-パッケージ-piper-g2p-機能要求)
2. [Python パッケージ 非機能要求](#2-python-パッケージ-非機能要求)
3. [Rust crate (`piper-g2p`) 機能要求](#3-rust-crate-piper-g2p-機能要求)
4. [Rust crate 非機能要求](#4-rust-crate-非機能要求)
5. [C# NuGet パッケージ (`PiperPlus.Phonemize`) 機能要求](#5-c-nuget-パッケージ-piperplusphonemize-機能要求)
6. [C# NuGet パッケージ 非機能要求](#6-c-nuget-パッケージ-非機能要求)
7. [JS/WASM npm パッケージ (`@piper-plus/g2p`) 機能要求](#7-jswasm-npm-パッケージ-piper-plusg2p-機能要求)
8. [JS/WASM npm パッケージ 非機能要求](#8-jswasm-npm-パッケージ-非機能要求)
9. [共通機能要求 (FR-G)](#9-共通機能要求-fr-g)
10. [共通非機能要求 (NFR-G)](#10-共通非機能要求-nfr-g)
11. [統合・マイグレーション要求 (FR-I)](#11-統合マイグレーション要求-fr-i)
12. [リリース戦略](#12-リリース戦略)
13. [現状からの差分サマリ](#13-現状からの差分サマリ)

---

## 1. Python パッケージ (`piper-g2p`) 機能要求

### FR-P-001: Phonemizer 抽象基底クラスの公開

**説明**: 現在の `Phonemizer` ABC と `ProsodyInfo` データクラスを、パッケージの公開 API として提供する。全言語 Phonemizer はこの ABC を継承する。

**現在の API**:
```python
# src/python/piper_train/phonemize/base.py

@dataclass
class ProsodyInfo:
    a1: int  # 言語依存のプロソディ次元1
    a2: int  # 言語依存のプロソディ次元2
    a3: int  # 言語依存のプロソディ次元3

class Phonemizer(ABC):
    @abstractmethod
    def phonemize(self, text: str) -> list[str]: ...

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]: ...

    @abstractmethod
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
        eos_token: str = "$",
    ) -> tuple[list[int], list[dict | None]]: ...
```

**受入条件**:
- `from piper_g2p import Phonemizer, ProsodyInfo` でインポートできる
- `Phonemizer` は `phonemize()`, `phonemize_with_prosody()`, `get_phoneme_id_map()` を抽象メソッドとして持つ
- `post_process_ids()` のデフォルト実装 (BOS/EOS/パディング挿入) が動作する
- 既存の `piper_train.phonemize.base` と型シグネチャが同一

---

### FR-P-002: 言語レジストリ

**説明**: `get_phonemizer()`, `register_language()`, `available_languages()` を公開し、言語コードによる Phonemizer の取得・登録を可能にする。マルチリンガルコンボコード (例: `"ja-en-zh-es-fr-pt"`) を渡すと自動的に `MultilingualPhonemizer` を生成しキャッシュする。

**現在の API**:
```python
# src/python/piper_train/phonemize/registry.py

def register_language(code: str, phonemizer: Phonemizer): ...
def get_phonemizer(language: str) -> Phonemizer: ...
def available_languages() -> list[str]: ...
```

**受入条件**:
- `from piper_g2p import get_phonemizer, register_language, available_languages`
- `get_phonemizer("ja")` で `JapanesePhonemizer` が返る (pyopenjtalk インストール時)
- `get_phonemizer("ja-en")` で `MultilingualPhonemizer(["en", "ja"])` が返る
- 言語コードは canonical sorted order に正規化される (例: `"en-ja"` == `"ja-en"`)
- 依存が未インストールの言語は自動スキップされ `ImportError` にならない
- ユーザーが `register_language("custom", MyPhonemizer())` でカスタム言語を登録できる

---

### FR-P-003: 日本語 Phonemizer

**説明**: OpenJTalk ベースの日本語 G2P。栗原法による韻律記号 (`^`, `$`, `?`, `_`, `#`, `[`, `]`)、文脈依存 N 音素変異 (`N_m`, `N_n`, `N_ng`, `N_uvular`)、疑問詞マーカー拡張 (`?!`, `?.`, `?~`)、カスタム辞書対応を含む。

**現在の API**:
```python
# src/python/piper_train/phonemize/japanese.py

def phonemize_japanese(
    text: str,
    custom_dict: CustomDictionary | str | list[str] | None = None,
) -> list[str]: ...

def phonemize_japanese_with_prosody(
    text: str,
    custom_dict: CustomDictionary | str | list[str] | None = None,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class JapanesePhonemizer(Phonemizer):
    def __init__(self, custom_dict: CustomDictionary | str | list[str] | None = None): ...
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
    def post_process_ids(self, ...): ...  # no-op (JA handles BOS/EOS inline)
```

**注**: 現在の実装では `JapanesePhonemizer` にコンストラクタがなく、`custom_dict` は `phonemize_japanese()` 関数のみで使用可能。独立パッケージ化時にクラスレベルでも `custom_dict` を受け取れるよう拡張する。

**受入条件**:
- `from piper_g2p.japanese import JapanesePhonemizer, phonemize_japanese, phonemize_japanese_with_prosody`
- `JapanesePhonemizer(custom_dict="path/to/dict.json")` でカスタム辞書付きインスタンスを作成できる
- `pyopenjtalk-plus` (BSD-3-Clause) または `pyopenjtalk` が必要 (optional dependency)
- ProsodyInfo の a1/a2/a3 値が OpenJTalk ラベルから正しく抽出される
- PUA マッピング (`token_mapper`) によって多文字トークンが1コードポイントに変換される
- カスタム辞書パスを引数で渡せる

---

### FR-P-004: 英語 Phonemizer

**説明**: g2p-en (Apache-2.0) ベースの英語 G2P。ARPAbet-to-IPA 変換、文脈依存ルール (AA+R, stressed ER)、機能語のストレス除去、espeak-ng 互換出力を含む。

**現在の API**:
```python
# src/python/piper_train/phonemize/english.py

def phonemize_english(text: str) -> list[str]: ...
def phonemize_english_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class EnglishPhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.english import EnglishPhonemizer, phonemize_english`
- `g2p-en>=2.1.0` (Apache-2.0) が必要 (optional dependency)
- ProsodyInfo: `a1=0`, `a2=stress_level (0/1/2)`, `a3=word_phoneme_count`
- 97 個の機能語 (`_FUNCTION_WORDS`) のストレスが正しく除去される

---

### FR-P-005: 中国語 (Mandarin) Phonemizer

**説明**: pypinyin (MIT) ベースの中国語 G2P。漢字→ピンイン→IPA 変換、声調サンドヒ (3声/一/不)、儿化音処理を含む。

**現在の API**:
```python
# src/python/piper_train/phonemize/chinese.py

def phonemize_chinese(text: str) -> list[str]: ...
def phonemize_chinese_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...
def phonemize_from_pinyin_syllables(
    pinyin_syllables: list[str],
    chinese_text: str = "",
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class ChinesePhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.chinese import ChinesePhonemizer, phonemize_chinese, phonemize_from_pinyin_syllables`
- `pypinyin>=0.50` (MIT) が必要 (optional dependency)
- ProsodyInfo: `a1=tone (1-5)`, `a2=syllable_position`, `a3=word_length`
- 声調サンドヒ (3声連続、一/不 変調) が正しく適用される
- `phonemize_from_pinyin_syllables()` でコーパスの事前解析済みピンインから直接変換可能

---

### FR-P-006: 韓国語 Phonemizer

**説明**: g2pk2 (Apache-2.0) + Hangul 分解ベースの韓国語 G2P。音韻規則 (連音化、鼻音化、激音化、硬音化) 適用後、Hangul jamo を IPA に変換。

**現在の API**:
```python
# src/python/piper_train/phonemize/korean.py

def phonemize_korean(text: str) -> list[str]: ...
def phonemize_korean_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class KoreanPhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.korean import KoreanPhonemizer, phonemize_korean`
- `g2pk2>=0.0.3` (Apache-2.0) が必要 (optional dependency)
- g2pk2 が未インストールの場合、音韻規則なしのフォールバック動作 (warning ログ)

---

### FR-P-007: スペイン語 Phonemizer

**説明**: ルールベースのスペイン語 G2P。外部依存なし。Latin American Spanish 発音 (seseo)。音節分割、ストレス推定、複合子音 (ch, ll, rr, qu, gu, gu) 対応。

**現在の API**:
```python
# src/python/piper_train/phonemize/spanish.py

def phonemize_spanish(text: str) -> list[str]: ...
def phonemize_spanish_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class SpanishPhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.spanish import SpanishPhonemizer, phonemize_spanish`
- 外部依存なし (Pure Python)
- 機能語のストレスマーカー除去が正しく動作する

---

### FR-P-008: ポルトガル語 Phonemizer

**説明**: ルールベースのブラジルポルトガル語 G2P。外部依存なし。鼻母音化、l の母音化 (/l/ -> [w])、t/d の口蓋化 (ti -> tSi, di -> dZi)、語末母音の弱化を含む。

**現在の API**:
```python
# src/python/piper_train/phonemize/portuguese.py

def phonemize_portuguese(text: str) -> list[str]: ...
def phonemize_portuguese_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class PortuguesePhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.portuguese import PortuguesePhonemizer, phonemize_portuguese`
- 外部依存なし (Pure Python)

---

### FR-P-009: フランス語 Phonemizer

**説明**: ルールベースのフランス語 G2P。外部依存なし。鼻母音 (ɛ̃, ɑ̃, ɔ̃)、母音ダイグラフ (ou, au, eau, ai, oi 等)、無音字、語末子音サイレンス、母音間 s の有声化、-er 動詞語尾処理を含む。

**現在の API**:
```python
# src/python/piper_train/phonemize/french.py

def phonemize_french(text: str) -> list[str]: ...
def phonemize_french_with_prosody(
    text: str,
) -> tuple[list[str], list[ProsodyInfo | None]]: ...

class FrenchPhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
```

**受入条件**:
- `from piper_g2p.french import FrenchPhonemizer, phonemize_french`
- 外部依存なし (Pure Python)

---

### FR-P-010: MultilingualPhonemizer (コードスイッチング対応)

**説明**: Unicode 文字範囲による言語自動検出とセグメント分割を行い、各セグメントを言語固有 Phonemizer に委譲するメタ Phonemizer。N 言語の任意の組み合わせに対応。

**現在の API**:
```python
# src/python/piper_train/phonemize/multilingual.py

class UnicodeLanguageDetector:
    def __init__(self, languages: list[str], default_latin_language: str = "en"): ...
    def detect_char(self, ch: str, context_has_kana: bool = False) -> str | None: ...
    def has_kana(self, text: str) -> bool: ...

class MultilingualPhonemizer(Phonemizer):
    def __init__(self, languages: list[str], default_latin_language: str = "en"): ...
    @property
    def languages(self) -> list[str]: ...
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...
    def post_process_ids(self, ...): ...  # dynamic EOS token
```

**受入条件**:
- `from piper_g2p.multilingual import MultilingualPhonemizer, UnicodeLanguageDetector`
- CJK 曖昧性解消 (かな文脈で漢字を JA/ZH 判定) が正しく動作する
- 個別セグメントの BOS/EOS は除去され、全体で1つの BOS/EOS が付加される
- `get_phonemizer("ja-en-zh")` でレジストリから自動生成される

---

### FR-P-011: カスタム辞書

**説明**: JSON 形式 (v1.0/v2.0) のカスタム辞書をロードし、テキスト前処理で単語を読みに置換する。大文字小文字の区別、優先度制御、動的エントリ追加/削除、辞書保存に対応。

**現在の API**:
```python
# src/python/piper_train/phonemize/custom_dict.py

class CustomDictionary:
    def __init__(
        self,
        dict_paths: str | list[str] | None = None,
        load_defaults: bool = True,
    ): ...
    def load_dictionary(self, dict_path: str) -> None: ...
    def apply_to_text(self, text: str) -> str: ...
    def get_pronunciation(self, word: str) -> str | None: ...
    def add_word(self, word: str, pronunciation: str, priority: int = 5) -> None: ...
    def remove_word(self, word: str) -> bool: ...
    def save_dictionary(self, output_path: str) -> None: ...
    def get_stats(self) -> dict[str, int]: ...

def create_default_dictionary() -> CustomDictionary: ...
def apply_custom_dictionary(text: str, dict_paths: str | list[str] | None = None) -> str: ...
```

**受入条件**:
- `from piper_g2p import CustomDictionary, apply_custom_dictionary`
- JSON v1.0 (`{"entries": {"API": "エーピーアイ"}}`) と v2.0 (`{"entries": {"API": {"pronunciation": "エーピーアイ", "priority": 5}}}`) の両形式に対応
- デフォルト辞書ディレクトリのパスは相対パスまたは設定可能にする (現在はハードコードされたプロジェクト相対パス `data/dictionaries/` を使用しており、独立パッケージではこのパスの解決方法を変更する必要がある)
- 大文字小文字混在ワードの case-sensitive マッチが動作する

---

### FR-P-012: トークンマッパー (PUA マッピング)

**説明**: 多文字音素トークン (例: `"ch"`, `"tɕʰ"`, `"N_m"`) を Unicode Private Use Area の1コードポイントに変換する。全言語 87 エントリの固定マッピング + 動的割り当てを提供。学習済みモデルとの互換性のため、固定マッピングは変更不可。

**現在の API**:
```python
# src/python/piper_train/phonemize/token_mapper.py

FIXED_PUA_MAPPING: dict[str, int]  # 88 entries (JA/ZH/KO/ES/PT/FR) -- 注: Rust/C# は 87 エントリ。差分を調査し統一すること
TOKEN2CHAR: dict[str, str]         # token -> PUA char
CHAR2TOKEN: dict[str, str]         # PUA char -> token

def register(token: str) -> str: ...
def map_sequence(seq: list[str]) -> list[str]: ...
```

**受入条件**:
- `from piper_g2p.token_mapper import map_sequence, register, TOKEN2CHAR, CHAR2TOKEN, FIXED_PUA_MAPPING`
- 固定 PUA マッピングが Python/Rust/C++ 間で一致する
- `map_sequence()` で任意のトークン列を1コードポイント列に変換できる
- 単一コードポイントのトークンはそのまま返す

---

### FR-P-013: 言語別 ID マップ

**説明**: 各言語の音素インベントリを定義する ID マップモジュール群と、多言語モデル用の統合 ID マップビルダーを提供する。

**現在のモジュール**:
- `jp_id_map.py` -- `JAPANESE_PHONEMES`, `SPECIAL_TOKENS`
- `zh_id_map.py` -- `CHINESE_PHONEMES`
- `ko_id_map.py` -- `KOREAN_PHONEMES`
- `es_id_map.py` -- `SPANISH_PHONEMES`
- `pt_id_map.py` -- `PORTUGUESE_PHONEMES`
- `fr_id_map.py` -- `FRENCH_PHONEMES`
- `bilingual_id_map.py` -- `get_bilingual_id_map()`, `ENGLISH_PHONEMES`
- `multilingual_id_map.py` -- `get_multilingual_id_map(languages: list[str])`, `LANGUAGE_PHONEMES`

**受入条件**:
- `from piper_g2p.multilingual_id_map import get_multilingual_id_map`
- `get_multilingual_id_map(["ja", "en", "zh"])` で3言語統合の `dict[str, list[int]]` が返る
- 共有音素 (例: `"b"`, `"d"`, `"m"`) は1つの ID に統一される
- Piper TTS の `config.json` 形式と互換性がある

---

### FR-P-014: BilingualPhonemizer (後方互換)

**説明**: 旧 JA+EN バイリンガルモデルとの後方互換のため、`BilingualPhonemizer` を `MultilingualPhonemizer` のサブクラスとして提供する。

**現在の API**:
```python
# src/python/piper_train/phonemize/bilingual.py

class BilingualPhonemizer(MultilingualPhonemizer):
    def __init__(self, languages: list[str]): ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...
```

**受入条件**:
- `from piper_g2p.bilingual import BilingualPhonemizer`
- `BilingualPhonemizer(["ja", "en"])` で旧バイリンガル ID マップが返る
- `MultilingualPhonemizer` の全機能を継承

---

## 2. Python パッケージ 非機能要求

### NFR-P-001: パッケージング

**説明**: `piper-g2p` として PyPI に公開可能な形式で配布する。

**受入条件**:
- `pip install piper-g2p` でインストールできる
- パッケージ名: `piper-g2p` (PyPI), インポート名: `piper_g2p`
- `pyproject.toml` に `[build-system]`, `[project]` セクションが正しく記述されている
- ライセンス: MIT
- Python: `>=3.11` (pyopenjtalk-plus 0.4.x の最低サポートバージョンと整合)
- ビルドバックエンド: `setuptools` (既存と同一)

---

### NFR-P-002: 言語別 optional dependencies

**説明**: 各言語の外部依存を optional extras として宣言し、不要な言語の依存をインストールせずに使えるようにする。

**受入条件**:
- `pip install piper-g2p[ja]` で `pyopenjtalk-plus` がインストールされる
- `pip install piper-g2p[en]` で `g2p-en>=2.1.0` がインストールされる
- `pip install piper-g2p[zh]` で `pypinyin>=0.50` がインストールされる
- `pip install piper-g2p[ko]` で `g2pk2>=0.0.3` がインストールされる
- `pip install piper-g2p[es]`, `pip install piper-g2p[fr]`, `pip install piper-g2p[pt]` は外部依存なし (extras としては存在するが空)
- `pip install piper-g2p[all]` で全言語の依存がインストールされる
- 外部依存なしでもコアモジュール (base, registry, token_mapper, custom_dict, es, fr, pt) が利用可能

**依存一覧**:

| extra | パッケージ | ライセンス |
|-------|-----------|----------|
| `ja` | `pyopenjtalk-plus` | BSD-3-Clause |
| `en` | `g2p-en>=2.1.0` | Apache-2.0 |
| `zh` | `pypinyin>=0.50` | MIT |
| `ko` | `g2pk2>=0.0.3` | Apache-2.0 |
| `es` | (なし) | - |
| `fr` | (なし) | - |
| `pt` | (なし) | - |

---

### NFR-P-003: piper-train との後方互換性

**説明**: `piper-train` パッケージが `piper-g2p` を依存として使用できるよう、API の後方互換性を維持する。

**受入条件**:
- `piper_train.phonemize` から `piper_g2p` への re-export レイヤーを `piper-train` 側に追加する
- `from piper_train.phonemize import Phonemizer, ProsodyInfo, get_phonemizer` が引き続き動作する
- `piper-train` の `pyproject.toml` に `piper-g2p` が依存として追加される
- 既存のテストが変更なしでパスする

---

### NFR-P-004: テスト

**説明**: 独立パッケージとして十分なテストカバレッジを持つ。

**受入条件**:
- 全公開関数/クラスに対するユニットテストが存在する
- CI で `pytest` が全言語 (optional deps インストール済み) で実行される
- 各言語 Phonemizer の基本的な入出力テスト (最低 3 ケース/言語)
- `MultilingualPhonemizer` のコードスイッチングテスト
- `CustomDictionary` の JSON v1.0/v2.0 ロードテスト
- `token_mapper` の PUA マッピング一貫性テスト

---

### NFR-P-005: パフォーマンス

**説明**: 独立パッケージ化によるパフォーマンス劣化がないこと。

**受入条件**:
- レジストリの自動登録 (`_auto_register`) はインポート時に1回のみ実行
- G2p (英語)、jpreprocess (日本語) のインスタンスはモジュールレベルでキャッシュ
- `phonemize_from_pinyin_syllables()` (中国語コーパス高速パス) が利用可能

---

### NFR-P-006: カスタム辞書パスの汎用化

**説明**: 現在の `CustomDictionary` はデフォルト辞書ディレクトリを `Path(__file__).parent.parent.parent.parent.parent / "data" / "dictionaries"` としてハードコードしている。独立パッケージでは、このパスの解決方法を汎用化する必要がある。

**受入条件**:
- デフォルト辞書ディレクトリは `piper_g2p` パッケージ内の `data/dictionaries/` にバンドルする、またはランタイム設定可能にする
- `CustomDictionary(load_defaults=False)` でデフォルト辞書の読み込みをスキップできる (既存動作を維持)
- `piper-train` 側のデフォルト辞書パスとの整合性を保つ

---

## 3. Rust crate (`piper-g2p`) 機能要求

### FR-R-001: Phonemizer trait の公開

**説明**: 現在の `Phonemizer` trait を独立 crate の公開 API として提供する。推論エンジン (`piper-plus` crate) から分離し、G2P のみの利用を可能にする。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/mod.rs

#[derive(Debug, Clone, Copy)]
pub struct ProsodyInfo {
    pub a1: i32,
    pub a2: i32,
    pub a3: i32,
}

pub type ProsodyFeature = [i32; 3];

pub trait Phonemizer: Send + Sync {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError>;

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap>;

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);

    fn language_code(&self) -> &str;

    fn detect_primary_language(&self, _text: &str) -> &str {
        self.language_code()
    }
}
```

**受入条件**:
- `use piper_g2p::{Phonemizer, ProsodyInfo, ProsodyFeature}` でインポートできる
- `Phonemizer` trait は `Send + Sync` を要求する (マルチスレッド安全)
- `PiperError` への依存を `piper-g2p` 固有のエラー型 (`G2pError`) に置き換える
- `PhonemeIdMap` への依存を `HashMap<String, Vec<i64>>` 型エイリアスとして crate 内に定義する

**変更点 (現在のコードからの差分)**:
```rust
// 新しい G2P 専用エラー型
#[derive(thiserror::Error, Debug)]
pub enum G2pError {
    #[error("unsupported language: {code}")]
    UnsupportedLanguage { code: String },

    #[error("unknown phoneme: {phoneme}")]
    UnknownPhoneme { phoneme: String },

    #[error("phonemization error: {0}")]
    Phonemize(String),

    #[error("dictionary load error: {path}")]
    DictionaryLoad { path: String },

    #[error("jpreprocess initialization error: {0}")]
    JPreprocessInit(String),

    #[error("label parse error: {0}")]
    LabelParse(String),

    #[error("phoneme ID not found: {phoneme}")]
    PhonemeIdNotFound { phoneme: String },
}

// PhonemeIdMap は crate 内で再定義
pub type PhonemeIdMap = HashMap<String, Vec<i64>>;
```

---

### FR-R-002: PhonemizerRegistry

**説明**: 言語コードによる Phonemizer の登録・取得を提供する。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/mod.rs

pub struct PhonemizerRegistry {
    registry: HashMap<String, Box<dyn Phonemizer>>,
}

impl PhonemizerRegistry {
    pub fn new() -> Self;
    pub fn register(&mut self, lang_code: &str, phonemizer: Box<dyn Phonemizer>);
    pub fn get(&self, lang_code: &str) -> Option<&dyn Phonemizer>;
    pub fn available_languages(&self) -> Vec<&str>;
}
```

**受入条件**:
- `use piper_g2p::PhonemizerRegistry`
- `registry.register("ja", Box::new(JapanesePhonemizer::new()?))` で登録できる
- `registry.get("ja")` で `Option<&dyn Phonemizer>` が返る
- `Default` trait が実装されている (空のレジストリ)

---

### FR-R-003: 日本語 Phonemizer (feature: `japanese`)

**説明**: jpreprocess (MIT) ベースの日本語 G2P。Python 実装と同一の栗原法、N 音素変異、疑問詞マーカー拡張を実装。feature flag `japanese` で有効化。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/japanese.rs

pub struct JapanesePhonemizer { ... }

impl JapanesePhonemizer {
    pub fn new() -> Result<Self, PiperError>;
    pub fn with_custom_dict(custom_dict: CustomDictionary) -> Result<Self, PiperError>;
}

impl Phonemizer for JapanesePhonemizer {
    fn phonemize_with_prosody(&self, text: &str) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError>;
    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap>;  // returns None
    fn post_process_ids(&self, ...) -> ...;  // no-op (JA handles BOS/EOS inline)
    fn language_code(&self) -> &str;  // "ja"
}
```

**受入条件**:
- `#[cfg(feature = "japanese")]` で条件付きコンパイル
- feature `japanese` は `dep:jpreprocess` を有効化
- feature `naist-jdic` は `japanese` + `jpreprocess/naist-jdic` を有効化 (辞書バンドル)
- `PiperError` は `G2pError` に置き換え

---

### FR-R-004: 英語 Phonemizer

**説明**: CMU 辞書 (JSON) + ARPAbet-to-IPA 変換ベースの英語 G2P。Python 実装と同一の変換ルール、機能語ストレス除去、OOV 形態素フォールバックを実装。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/english.rs

pub struct EnglishPhonemizer { ... }

impl EnglishPhonemizer {
    pub fn new() -> Self;
    pub fn from_cmudict_path(path: &Path) -> Result<Self, PiperError>;
}

impl Phonemizer for EnglishPhonemizer { ... }
```

**受入条件**:
- デフォルトで有効 (feature flag 不要、CMU 辞書は組み込み JSON)
- OOV 形態素フォールバック (-ing, -ed, -s, -er, -ly, -est) が動作する

---

### FR-R-005: 中国語 Phonemizer

**説明**: ルールベースの中国語 G2P。ピンイン-IPA 変換テーブル、声調サンドヒ。Python と同一の変換ロジック。

**現在の位置**: `src/rust/piper-core/src/phonemize/chinese.rs`

**受入条件**:
- デフォルトで有効 (Pure Rust、外部 crate 不要)
- 声調サンドヒ (3声、一/不) が正しく適用される

---

### FR-R-006: 韓国語 Phonemizer

**説明**: Hangul 分解 + IPA 変換の韓国語 G2P。g2pk2 相当の音韻規則は Rust では未実装 (分解のみ)。

**現在の位置**: `src/rust/piper-core/src/phonemize/korean.rs`

**受入条件**:
- デフォルトで有効 (Pure Rust)

---

### FR-R-007: スペイン語 / ポルトガル語 / フランス語 Phonemizer

**説明**: ルールベースの G2P。Pure Rust、外部 crate 不要。Python 実装と同一のルール。

**現在の位置**:
- `src/rust/piper-core/src/phonemize/spanish.rs`
- `src/rust/piper-core/src/phonemize/portuguese.rs`
- `src/rust/piper-core/src/phonemize/french.rs`

**受入条件**:
- デフォルトで有効 (Pure Rust)

---

### FR-R-008: MultilingualPhonemizer

**説明**: Unicode 言語検出 + セグメント分割 + 委譲の多言語メタ Phonemizer。Python 実装と同一ロジック。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/multilingual.rs

pub struct UnicodeLanguageDetector { ... }

impl UnicodeLanguageDetector {
    pub fn new(languages: &[String], default_latin_language: &str) -> Self;
    pub fn detect_char(&self, ch: char, context_has_kana: bool) -> Option<&str>;
    pub fn has_kana(text: &str) -> bool;
}

pub struct MultilingualPhonemizer { ... }

impl MultilingualPhonemizer {
    pub fn new(languages: Vec<String>, phonemizers: HashMap<String, Box<dyn Phonemizer>>) -> Self;
}

impl Phonemizer for MultilingualPhonemizer { ... }

pub fn default_post_process_ids(
    ids: Vec<i64>,
    prosody: Vec<Option<ProsodyFeature>>,
    id_map: &PhonemeIdMap,
) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);
```

**受入条件**:
- CJK 曖昧性解消が Python 実装と同一の結果を返す
- `default_post_process_ids()` が EN/ZH/KO/ES/PT/FR で共通利用される

---

### FR-R-009: カスタム辞書

**説明**: JSON v1.0/v2.0 形式のカスタム辞書。Python 実装と同一のマッチングロジック。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/custom_dict.rs

pub struct DictEntry {
    pub pronunciation: String,
    pub priority: i32,
}

pub struct CustomDictionary { ... }

impl CustomDictionary {
    pub fn new() -> Self;
    pub fn load_dictionary(&mut self, path: &Path) -> Result<(), PiperError>;
    pub fn apply_to_text(&self, text: &str) -> String;
    pub fn add_word(&mut self, word: &str, pronunciation: &str);
    pub fn add_entry(&mut self, word: &str, entry: DictEntry);
}
```

**受入条件**:
- `use piper_g2p::custom_dict::{CustomDictionary, DictEntry}`
- JSON v1.0/v2.0 のデシリアライズが動作する
- case-sensitive / case-insensitive マッチが正しく動作する

---

### FR-R-010: PUA トークンマップ

**説明**: Python `token_mapper.py` と同一の固定 PUA マッピング (87 エントリ)。

**現在の API**:
```rust
// src/rust/piper-core/src/phonemize/token_map.rs

pub static FIXED_PUA_MAP: LazyLock<Vec<(&'static str, u32)>>;

pub fn token_to_pua(token: &str) -> Option<char>;
pub fn build_token2char() -> HashMap<String, char>;
pub fn build_char2token() -> HashMap<char, String>;
```

**受入条件**:
- `use piper_g2p::token_map::{token_to_pua, FIXED_PUA_MAP}`
- Python の `FIXED_PUA_MAPPING` と全エントリが一致する

---

## 4. Rust crate 非機能要求

### NFR-R-001: crate 構成

**説明**: `piper-g2p` を独立 crate として workspace に追加し、`piper-plus` (旧 `piper-core`) がこれに依存する形にする。

**受入条件**:
- `src/rust/piper-g2p/Cargo.toml` が存在する
- workspace `Cargo.toml` の `members` に `"piper-g2p"` が含まれる
- `piper-plus` (piper-core) の `Cargo.toml` に `piper-g2p` が依存として記述される
- `piper-g2p` は crates.io に公開可能な状態 (`cargo publish --dry-run` が成功する)
- ライセンス: MIT

---

### NFR-R-002: feature flags

**説明**: 言語別の feature flags で依存を制御する。

**受入条件**:
- `default` features: 全言語有効 (japanese 以外は Pure Rust で追加コスト無し)
- feature `japanese`: `dep:jpreprocess` を有効化
- feature `naist-jdic`: `japanese` + `jpreprocess/naist-jdic` (辞書バンドル)
- 以下の依存構成:

| feature | 依存 crate | ライセンス |
|---------|-----------|----------|
| (なし / default) | `regex 1`, `serde 1`, `serde_json 1`, `thiserror 2` | Apache-2.0/MIT |
| `japanese` | `jpreprocess 0.9` | MIT |
| `naist-jdic` | `jpreprocess 0.9` + `naist-jdic` feature | MIT + BSD-3-Clause |

---

### NFR-R-003: Send + Sync

**説明**: 全ての Phonemizer 実装が `Send + Sync` を満たし、マルチスレッド環境 (tokio, rayon 等) で安全に使用できること。

**受入条件**:
- `Phonemizer` trait bound が `Send + Sync` を含む (現在の実装を維持)
- `CustomDictionary` の `pattern_cache: Mutex<HashMap<String, Regex>>` パターンで interior mutability を安全に提供
- コンパイル時にすべての実装型が `Send + Sync` を満たすことを検証するテストを含む

---

### NFR-R-004: MSRV (Minimum Supported Rust Version)

**説明**: workspace の `rust-version` と整合する MSRV を設定する。

**受入条件**:
- `Cargo.toml` に `rust-version = "1.88"` を記述 (workspace 設定に準拠)
- `LazyLock`, `OnceLock` の使用が MSRV と互換 (Rust 1.80+ で安定化済み)
- CI で MSRV でのビルド検証を実施

---

### NFR-R-005: piper-plus との後方互換性

**説明**: `piper-plus` crate が `piper-g2p` を依存として使用する形にリファクタリングしても、既存の公開 API が維持されること。

**受入条件**:
- `piper-plus` の `src/phonemize/` が `piper-g2p` からの re-export になる
- `piper-plus` を利用する既存コード (`piper-cli`, `piper-python`) のコンパイルが通る
- `piper-g2p` の `G2pError` は `PiperError` と `From` trait で相互変換可能

---

### NFR-R-006: テスト

**説明**: 独立 crate として十分なテストカバレッジを持つ。

**受入条件**:
- 各言語 Phonemizer の基本入出力テスト (最低 3 ケース/言語)
- `MultilingualPhonemizer` のコードスイッチングテスト
- `CustomDictionary` の JSON v1.0/v2.0 ロードテスト
- PUA マッピングの Python 実装との一致テスト
- `Send + Sync` のコンパイルタイムチェック
- CI (`rust-tests.yml`) で 3 OS (Linux, macOS, Windows) での実行

---

### NFR-R-007: ドキュメント

**説明**: crate ドキュメントを充実させ、外部利用者が API を理解できるようにする。

**受入条件**:
- `#![deny(missing_docs)]` を lib.rs に設定
- 全 `pub` アイテムに doc comment が付与されている
- `cargo doc --no-deps` が warning なしで成功する
- crate レベルの doc comment にクイックスタート例を含める:

```rust
//! # piper-g2p
//!
//! Multi-language G2P (Grapheme-to-Phoneme) library for TTS.
//!
//! ## Quick Start
//!
//! ```rust
//! use piper_g2p::{Phonemizer, ProsodyInfo};
//! use piper_g2p::english::EnglishPhonemizer;
//!
//! let phonemizer = EnglishPhonemizer::new();
//! let (tokens, prosody) = phonemizer.phonemize_with_prosody("Hello, world!")?;
//! ```
```

---

## 5. C# NuGet パッケージ (`PiperPlus.Phonemize`) 機能要求

> **対象外**: C# の G2P は DotNetG2P (NuGet) が既に独立パッケージとして公開済みのため、`PiperPlus.Phonemize` の新規作成は不要。以下は参考情報として残す。DotNetG2P が Piper Plus の G2P バックエンドとして機能し、PiperPlus.Core の Phonemize レイヤー (PUA マッピング、MultilingualPhonemizer 等) は PiperPlus.Core 内に留まる。

### FR-C-001: IPhonemizer インターフェースの公開

**説明:**
現在 `PiperPlus.Core.Phonemize` 名前空間に定義されている `IPhonemizer` インターフェースと `ProsodyInfo` レコードを、新パッケージの公開 API として提供する。既存のシグネチャを維持し、ONNX 推論パイプラインへの依存を持たないようにする。

**現在の API** (`src/csharp/PiperPlus.Core/Phonemize/IPhonemizer.cs`):
```csharp
public record struct ProsodyInfo(int A1, int A2, int A3);

public interface IPhonemizer
{
    List<string> Phonemize(string text);

    (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text);

    Dictionary<string, int[]>? GetPhonemeIdMap();

    (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds,
        List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap)
    { return (phonemeIds, prosodyFeatures); }
}
```

**受入条件:**
- `IPhonemizer`, `ProsodyInfo` が `PiperPlus.Phonemize` 名前空間から公開されている
- `PiperPlus.Core` への参照なしにコンパイル・利用できる
- `PostProcessIds` のデフォルト実装 (no-op) が維持されている
- 既存の `PiperPlus.Core.Phonemize.IPhonemizer` は `[TypeForwardedTo]` で新型へ転送する

---

### FR-C-002: 言語別 G2P エンジンインターフェースの公開

**説明:**
現在の G2P エンジン抽象化インターフェースを公開する。外部ユーザーは独自のバックエンドを差し替え・モックしてテストできる。

**現在の API:**
```csharp
// 日本語 (JapanesePhonemizer.cs)
public record G2PResult(string[] Phonemes, int[] A1, int[] A2, int[] A3);
public interface IJapaneseG2PEngine
{
    G2PResult Convert(string text);
}

// 英語 (EnglishPhonemizer.cs)
public interface IEnglishG2PEngine
{
    List<List<string>> ConvertToArpabet(string text);
}

// 中国語 (IChineseG2PEngine.cs)
public record ChineseG2PResult(
    IReadOnlyList<string> Phonemes,
    IReadOnlyList<int> A1, IReadOnlyList<int> A2, IReadOnlyList<int> A3);
public interface IChineseG2PEngine
{
    ChineseG2PResult Convert(string text);
}

// ES/FR/PT (ISpanishG2PEngine.cs, IFrenchG2PEngine.cs, IPortugueseG2PEngine.cs)
public interface ISpanishG2PEngine    { List<string> ToPhonemeList(string text); }
public interface IFrenchG2PEngine     { List<string> ToPhonemeList(string text); }
public interface IPortugueseG2PEngine { List<string> ToPhonemeList(string text); }
```

**受入条件:**
- 上記 7 インターフェース + 2 result 型がすべて公開されている
- 各インターフェースに XML ドキュメントコメントがある
- `IJapaneseG2PEngine` を実装する DotNetG2P アダプターが別パッケージ (`PiperPlus.Phonemize.DotNetG2P`) として提供される

---

### FR-C-003: 6 言語 Phonemizer 実装の提供

**説明:**
現在の 6 言語 Phonemizer 実装をすべて新パッケージ内に含める。

| クラス | 言語 | コンストラクタ引数 | PostProcessIds |
|--------|------|-------------------|---------------|
| `JapanesePhonemizer` | ja | `IJapaneseG2PEngine` | no-op (デフォルト) |
| `EnglishPhonemizer` | en | `IEnglishG2PEngine` | `DefaultPostProcessIds` |
| `ChinesePhonemizer` | zh | `IChineseG2PEngine` | `DefaultPostProcessIds` |
| `SpanishPhonemizer` | es | `ISpanishG2PEngine` | `DefaultPostProcessIds` |
| `FrenchPhonemizer` | fr | `IFrenchG2PEngine` | `DefaultPostProcessIds` |
| `PortuguesePhonemizer` | pt | `IPortugueseG2PEngine` | `DefaultPostProcessIds` |

**受入条件:**
- 6 クラスすべてが `IPhonemizer` を実装している
- 各 Phonemizer はコンストラクタ DI で対応する `I*G2PEngine` を受け取る
- JA: 疑問詞マーカー (`?!`, `?.`, `?~`)、文脈依存 N 変異 (`N_m`, `N_n`, `N_ng`, `N_uvular`)、Kurihara 韻律マーカー (`]`, `#`, `[`)、PUA マッピングが動作する
- EN: ARPAbet -> IPA 変換 (`ArpabetToIPAConverter`)、function-word ストレス除去、コンテキスト依存マージ (`AA+R -> arphr`, stressed `ER1 -> erchr`) が動作する
- ES: ストレスマーカー出力 + 母音への A2=2 伝播が動作する
- FR: 末尾母音ストレス (固定末音節アクセント) が動作する
- PT: ストレスマーカー除去 + ストレス位置記録が動作する
- ZH/ES/FR/PT: `DefaultPostProcessIds` による BOS+PAD+EOS 挿入が動作する
- Python 実装と同一の phoneme トークン列を生成するテストが存在する

---

### FR-C-004: MultilingualPhonemizer の提供

**説明:**
`MultilingualPhonemizer` と `UnicodeLanguageDetector` を新パッケージに含め、多言語コードスイッチングを提供する。

**現在の API** (`src/csharp/PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs`):
```csharp
public sealed class MultilingualPhonemizer : IPhonemizer
{
    public MultilingualPhonemizer(
        Dictionary<string, IPhonemizer> phonemizers,
        string defaultLatinLanguage = "en");
}
```

**現在の API** (`src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs`):
```csharp
public sealed class UnicodeLanguageDetector
{
    public UnicodeLanguageDetector(
        IReadOnlyList<string> languages,
        string defaultLatinLanguage = "en");
    public string? DetectChar(char ch, bool contextHasKana = false);
    public bool HasKana(string text);
    public List<(string Lang, string Text)> SegmentText(string text);
    public string DefaultLatinLanguage { get; }
}
```

**受入条件:**
- `MultilingualPhonemizer` が任意の `IPhonemizer` 辞書で構成できる
- `UnicodeLanguageDetector` が CJK 曖昧性解消 (仮名有無による JA/ZH 判定) を正しく行う
- 全角ラテン文字 (U+FF21-FF5A) が Latin として扱われる (JA 判定にならない)
- スレッドセーフ性が維持されている (`_lastEos` が `ThreadLocal<string>`)
- セグメント間の BOS/EOS ストリッピング + 最終 EOS トークン追跡が正しく動作する
- `PostProcessIds` が動的 EOS トークン (`?`, `?!`, `?.`, `?~`, `$`) を正しく解決する

---

### FR-C-005: PhonemeEncoder の提供

**説明:**
テキストからモデル入力 (phoneme ID 列 + prosody 配列) を生成する統合 API を提供する。

**現在の API** (`src/csharp/PiperPlus.Core/Phonemize/PhonemeEncoder.cs`):
```csharp
public static class PhonemeEncoder
{
    public static void SetLogger(ILogger logger);

    // phonemize -> token-to-ID mapping -> PostProcessIds パイプライン
    public static (List<int> PhonemeIds, List<ProsodyInfo?> ProsodyFeatures) Encode(
        IPhonemizer phonemizer, string text,
        Dictionary<string, int[]> phonemeIdMap);

    // ONNX テンソル直接生成用 (long[] + interleaved prosody)
    public static (long[] PhonemeIds, long[]? ProsodyFlat) EncodeDirect(
        IPhonemizer phonemizer, string text,
        Dictionary<string, int[]> phonemeIdMap);
}
```

**受入条件:**
- `Encode` がトークン -> ID マッピング + `PostProcessIds` をパイプライン化している
- `EncodeDirect` が `long[]` 配列を返し、ONNX テンソルへの直接変換に利用可能
- `ProsodyFlat` レイアウト: `[a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...]`
- prosody が全て null の場合 `ProsodyFlat = null` を返す
- 未知の phoneme に対して `ILogger` 経由で警告が出力される

---

### FR-C-006: PUA トークンマッピングの公開

**説明:**
`OpenJTalkToPiperMapping` (87 エントリの PUA マッピングテーブル) を新パッケージに含める。現在 `PiperPlus.Core.Mapping` 名前空間にあり、`PiperPhonemeConverter.MapSequence()` から参照されている。

**現在の API** (`src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs`):
```csharp
public static class OpenJTalkToPiperMapping
{
    // multi-char token -> PUA char (87 entries)
    public static IReadOnlyDictionary<string, char> TokenToChar { get; }
    // PUA char -> multi-char token (reverse)
    public static IReadOnlyDictionary<char, string> CharToToken { get; }
    // single token mapping (cached string return)
    public static string MapToken(string token);
    // batch mapping
    public static IReadOnlyList<string> MapSequence(List<string> tokens);
}
```

**受入条件:**
- JA 29 + ZH 43 + ES/FR/PT 15 = 87 エントリがすべて含まれる
- 双方向変換 (`TokenToChar` / `CharToToken`) が公開されている
- `PiperPhonemeConverter.MapSequence()` が内部的にこのマッピングを使用する
- `PiperPhonemeConverter` 内の `DefaultPostProcessIds`, `ApplyNPhonemeRules`, `GetQuestionType` も公開

---

### FR-C-007: ユーティリティクラスの提供

**説明:**
以下のユーティリティクラスを新パッケージに含める。

| クラス | 現在のパス | 用途 |
|--------|-----------|------|
| `ArpabetToIPAConverter` | `Phonemize/ArpabetToIPAConverter.cs` | ARPAbet -> IPA 変換、function-word 判定、コンテキスト依存マージ |
| `PiperPhonemeConverter` | `Phonemize/PiperPhonemeConverter.cs` | 疑問詞マーカー判定、N 変異適用、PUA マッピング、`DefaultPostProcessIds` |
| `IpaTokenizer` | `Phonemize/IpaTokenizer.cs` | IPA 文字列のトークン分割 (ダイグラフ + combining mark 対応) |
| `TextSplitter` | `Phonemize/TextSplitter.cs` | 文分割 (CJK `。！？` + 西洋 `.!?` + closing punct 消費) |
| `CustomDictionary` | `Phonemize/CustomDictionary.cs` | カスタム辞書 (TSV / JSON v1.0 / JSON v2.0) |
| `InlinePhonemeParser` | `Phonemize/InlinePhonemeParser.cs` | `[[ phoneme ]]` インライン音素記法パーサー |
| `RawPhonemeParser` | `Phonemize/RawPhonemeParser.cs` | スペース区切り phoneme 文字列 -> phoneme ID 配列 |

**受入条件:**
- 各クラスが ONNX Runtime への依存なしにコンパイル可能
- `TextSplitter.SplitSentences()` が CJK 文末記号 + closing punctuation を正しく処理する
- `CustomDictionary` が longest-match-first + priority-based 競合解決を提供する
- `InlinePhonemeParser.Parse()` が `TextOrPhonemes` レコード列を返す
- `RawPhonemeParser.Parse()` が PUA マッピング経由のトークン解決を行う

---

### FR-C-008: DI コンテナ対応ファクトリ

**説明:**
Microsoft.Extensions.DependencyInjection との統合用拡張メソッドを提供する。

**新規 API (案):**
```csharp
public static class PhonemizerServiceExtensions
{
    /// <summary>
    /// 指定言語の IPhonemizer を DI コンテナに登録する。
    /// G2P エンジン実装はコンテナから自動解決される。
    /// </summary>
    public static IServiceCollection AddPiperPhonemizer(
        this IServiceCollection services,
        params string[] languages);

    /// <summary>
    /// MultilingualPhonemizer を DI コンテナに登録する。
    /// 登録済みの全 IPhonemizer を自動収集して構成する。
    /// </summary>
    public static IServiceCollection AddPiperMultilingualPhonemizer(
        this IServiceCollection services,
        string defaultLatinLanguage = "en");
}
```

**利用例:**
```csharp
services.AddSingleton<IJapaneseG2PEngine, DotNetG2PJapaneseEngine>();
services.AddSingleton<IEnglishG2PEngine, DotNetG2PEnglishEngine>();
services.AddPiperPhonemizer("ja", "en");
services.AddPiperMultilingualPhonemizer();
```

**受入条件:**
- `AddPiperPhonemizer("ja", "en")` で JA+EN の Phonemizer が登録される
- G2P エンジンインターフェースの実装が事前に登録されていない場合、分かりやすい例外メッセージが出る
- `AddPiperMultilingualPhonemizer()` で `MultilingualPhonemizer` が Singleton として登録される
- DI 拡張は別パッケージ (`PiperPlus.Phonemize.DependencyInjection`) またはメインパッケージのオプショナル部分として提供

---

## 6. C# NuGet パッケージ 非機能要求

> **対象外**: セクション 5 と同様。DotNetG2P が既に独立パッケージとして公開済み。

### NFR-C-001: Target Framework

**説明:** `net8.0` をターゲットとする。.NET 8 は 2024-2026 の LTS であり、Unity 6 (2024.1+) でもサポートされる。

**受入条件:**
- `<TargetFrameworks>net8.0</TargetFrameworks>` (将来的に `net9.0` 追加可能)
- C# 12 機能 (`GeneratedRegex`, `file-scoped namespaces` 等) を使用可能

---

### NFR-C-002: NuGet パッケージ構成

**説明:** 以下のパッケージ構成で NuGet に公開する。

| パッケージ ID | 内容 | 依存 |
|--------------|------|------|
| `PiperPlus.Phonemize` | インターフェース + 6 言語 Phonemizer + ユーティリティ + PUA マッピング | `Microsoft.Extensions.Logging.Abstractions` (>=8.0) のみ |
| `PiperPlus.Phonemize.DotNetG2P` | DotNetG2P ベースの G2P エンジン実装アダプター | `PiperPlus.Phonemize`, `DotNetG2P` 1.8.0, `DotNetG2P.MeCab` 1.8.0, `DotNetG2P.English` 1.8.0, `DotNetG2P.Chinese` 1.7.0, `DotNetG2P.Spanish` 1.7.0, `DotNetG2P.French` 1.7.0, `DotNetG2P.Portuguese` 1.7.0 |

**受入条件:**
- `PiperPlus.Phonemize` は `Microsoft.Extensions.Logging.Abstractions` 以外の外部依存を持たない
- 現在の `PiperPlus.Core.csproj` にある `Microsoft.ML.OnnxRuntime.Managed` への依存を G2P パッケージに含めない
- `PiperPlus.Phonemize` 単体で G2P エンジンのモック実装によるテストが可能
- `PiperPlus.Phonemize.DotNetG2P` をインストールすると実際の G2P バックエンドが利用可能になる

---

### NFR-C-003: スレッドセーフ性

**説明:** すべての Phonemizer 実装がスレッドセーフであること。

**受入条件:**
- `MultilingualPhonemizer._lastEos` が `ThreadLocal<string>` で管理されている (現状維持)
- 各単一言語 Phonemizer が内部可変状態を持たない (G2P エンジン呼び出しのみ)
- `CustomDictionary._sorted` キャッシュが `lock` で保護されている (現状維持)
- `PhonemeEncoder` が static メソッドのみで状態を持たない (現状維持)
- 並行呼び出しのテストが存在する (最低 2 スレッドでの同時 `PhonemizeWithProsody` 検証)

---

### NFR-C-004: 依存管理とライセンス

**説明:** GPL 汚染リスクゼロを維持する。

**受入条件:**
- 直接依存はすべて MIT / Apache-2.0 / BSD-3-Clause
- `PiperPlus.Phonemize`: `Microsoft.Extensions.Logging.Abstractions` (MIT) のみ
- `PiperPlus.Phonemize.DotNetG2P`: `DotNetG2P.*` (Apache-2.0) のみ
- eSpeak-ng / phonemizer (GPL-3.0) への依存が一切ない
- `<PackageLicenseExpression>MIT</PackageLicenseExpression>` を設定

---

### NFR-C-005: PiperPlus.Core との互換性

**説明:** `PiperPlus.Core` が新パッケージを参照する形にリファクタリングし、既存ユーザーへの破壊的変更を最小化する。

**受入条件:**
- `PiperPlus.Core` が `PiperPlus.Phonemize` を PackageReference で参照する
- 既存の `PiperPlus.Core.Phonemize.*` 名前空間から `[TypeForwardedTo]` で新型へ転送
- `PiperPlus.Core.Mapping.OpenJTalkToPiperMapping` も同様に TypeForward
- 既存 `PiperPlus.Core` ユーザーのコードがソース変更なしでコンパイルできる
- 829 件の既存テスト (`PiperPlus.Core.Tests`) が全て PASS する

---

### NFR-C-006: テストカバレッジ

**説明:** 独立パッケージとしての十分なテストを提供する。

**受入条件:**
- 各言語 Phonemizer に対する単体テスト (Python 実装との出力一致検証含む)
- `MultilingualPhonemizer` のコードスイッチングテスト (JA+EN 混在文等)
- `PhonemeEncoder.Encode` / `EncodeDirect` のエンドツーエンドテスト
- `CustomDictionary` の TSV / JSON v1.0 / JSON v2.0 ロード + テキスト変換テスト
- PUA マッピングの全 87 エントリ一致検証テスト
- テストプロジェクト: `PiperPlus.Phonemize.Tests` (xUnit v3)
- CI: `csharp-ci.yml` に統合 (3 OS x 2 .NET バージョン)

---

## 7. JS/WASM npm パッケージ (`@piper-plus/g2p`) 機能要求

### FR-W-001: 統一 Phonemizer API

**説明:**
現在の `SimpleUnifiedPhonemizer` クラスをリファクタリングし、推論パイプラインから分離された純粋な G2P API を提供する。`onnxruntime-web` への依存を完全に排除する。

**現在の API** (`src/wasm/openjtalk-web/src/simple_unified_api.js`):
```javascript
class SimpleUnifiedPhonemizer {
    constructor(options = {})
    async initialize(config)          // OpenJTalk WASM ロード + 辞書読み込み
    async textToPhonemes(text, language = null)  // -> string (JA labels) | string[] | number[]
    extractPhonemes(labels, language = 'ja')     // -> string[] | number[]
    setPhonemeIdMap(phonemeIdMap)      // ZH/ES/FR/PT フォールバック用
    getPhonemeIdMap(language)
    detectLanguage(text)              // -> 'ja' | 'zh' | 'en'
    dispose()
}
```

**新規 API (案):**
```typescript
// @piper-plus/g2p
export class G2P {
    static async create(options?: G2POptions): Promise<G2P>;

    phonemize(text: string, options?: PhonemizeOptions): PhonemizeResult;

    encode(text: string, phonemeIdMap: Record<string, number[]>,
           options?: PhonemizeOptions): EncodeResult;

    detectLanguage(text: string): Language;

    dispose(): void;
}

interface G2POptions {
    languages?: Language[];            // 有効にする言語 (省略時は全言語)
    jaDict?: JaDictData;               // 日本語辞書データ (DictLoader から取得)
    customDicts?: string[];            // カスタム辞書 URL 配列
}

interface PhonemizeOptions {
    language?: Language;               // 言語を明示指定 (省略時は自動検出)
}

interface PhonemizeResult {
    tokens: string[];                  // phoneme トークン配列
    prosody: (ProsodyInfo | null)[];   // per-token prosody (null = 該当なし)
    language: Language;                // 検出/指定された言語
}

interface EncodeResult {
    phonemeIds: number[];              // BOS/PAD/EOS 挿入済み phoneme ID 列
    prosodyFlat: number[] | null;      // [a1,a2,a3, a1,a2,a3, ...] or null
}

interface ProsodyInfo { a1: number; a2: number; a3: number; }
type Language = 'ja' | 'en' | 'zh' | 'es' | 'fr' | 'pt';
```

**受入条件:**
- `G2P.create()` が非同期初期化 (WASM ロード) を行い Promise を返す
- `phonemize()` が初期化後は同期的に呼び出せる
- `encode()` が `phonemeIdMap` を受け取り BOS/PAD/EOS を含む最終 ID 列を返す
- `onnxruntime-web` への依存がない
- 現在の `SimpleUnifiedPhonemizer` の全言語処理フローが新 API でカバーされている

---

### FR-W-002: 日本語 G2P (OpenJTalk WASM)

**説明:**
現在の OpenJTalk WASM 統合を分離し、日本語 G2P 専用モジュールとして提供する。

**現在の処理フロー** (`japanese_phoneme_extract.js`):
```
text -> OpenJTalk WASM (_openjtalk_synthesis_labels)
     -> full-context labels (文字列)
     -> extractPhonemesFromLabels()
       -> sil -> ^/$ (BOS/EOS)
       -> pau -> _ (短ポーズ)
       -> Kurihara 韻律マーカー: ], #, [
       -> N 変異: N_m, N_n, N_ng, N_uvular (applyNPhonemeRules)
       -> PUA マッピング (mapToPUA, PUA_MAP 24 entries)
```

**受入条件:**
- OpenJTalk WASM の初期化が `G2P.create({ languages: ['ja'], jaDict })` で行える
- 辞書データは外部注入 (`DictLoader` 経由の `JaDictData`)
- `extractPhonemesFromLabels()`, `applyNPhonemeRules()`, `mapToPUA()` が独立エクスポートされている
- A1/A2/A3 prosody 値が `ProsodyInfo` として返される。技術的に実現可能: OpenJTalk WASM は full-context label を返しており、既存の正規表現 (`RE_A1`/`RE_A2`/`RE_A3`) で抽出可能。`extractPhonemesFromLabels()` の戻り値を `[tokens, prosodyInfo]` のタプルに拡張する
- 韻律マーカー・N 変異・PUA マッピングが Python 実装と一致する

---

### FR-W-003: 英語 G2P

**説明:**
現在の `SimpleEnglishPhonemizer` (辞書 ~70 語 + letter-to-phoneme ルール) を改良する。

**現在の API** (`src/wasm/openjtalk-web/src/simple_english_phonemizer.js`):
```javascript
class SimpleEnglishPhonemizer {
    constructor()                  // 内蔵辞書 (~70 語) + letter rules (26 文字)
    textToPhonemes(text)           // -> string[] (IPA phonemes)
    phonemesToIPA(phonemes)        // -> string[] (pass-through)
}

function createEnglishPhonemeMap()  // -> { phoneme: [id], ... } (~50 entries)
```

**受入条件:**
- 現在の辞書ベース方式 (~70 語) を維持
- CMU Pronouncing Dictionary サブセット (上位 5,000 語) をオプションバンドルとして提供
- BOS/PAD/EOS 挿入 (`PostProcessIds` 相当) が `encode()` 内で行われる
- バンドルサイズ: CMU 辞書なし < 10KB gzip, CMU 辞書あり < 100KB gzip

---

### FR-W-004: 辞書ローダー (DictLoader)

**説明:**
現在の `DictManager` から辞書ダウンロード + IndexedDB キャッシュ機能を分離する。

**現在の API** (`src/wasm/openjtalk-web/src/dict-manager.js`):
```javascript
class DictManager {
    constructor(options = {})               // { cachePrefix: 'piper-plus-dict' }
    async loadDictionary(options = {})      // -> { dictFiles, voiceData }
    async isCached()                        // -> boolean
    async clearCache()                      // -> void
    resolveUrls(options = {})               // -> { dictUrl, voiceUrl }
}
// 内部:
// - DICT_TAR_GZ_URL (GitHub Releases)
// - SHA-256 検証 (verifySha256)
// - tar.gz 解凍 (DecompressionStream API)
// - tar パース (parseTar)
// - IndexedDB キャッシュ (DB_NAME='piper-plus-dict')
```

**新規 API (案):**
```typescript
export class DictLoader {
    constructor(options?: { cachePrefix?: string });

    async loadJaDict(options?: {
        dictUrl?: string;               // カスタム辞書 URL
        includeVoice?: boolean;         // HTS voice もダウンロードするか (default: false)
        voiceUrl?: string;              // カスタム voice URL
        onProgress?: (info: DictProgress) => void;
    }): Promise<JaDictData>;

    async isCached(): Promise<boolean>;
    async clearCache(): Promise<void>;
}

interface JaDictData {
    dictFiles: Record<string, ArrayBuffer>;   // 8 辞書ファイル
    voiceData?: ArrayBuffer;                   // HTS voice (includeVoice=true 時のみ)
}
```

**受入条件:**
- GitHub Releases から tar.gz をダウンロードし SHA-256 を検証する
- IndexedDB キャッシュにより 2 回目以降は即座にロードされる
- `dictUrl` で独自の辞書 URL を指定できる
- G2P 単体利用時は `includeVoice: false` がデフォルト (voice ダウンロード不要)
- 進捗コールバックが byte レベルで報告される
- DICT_FILES (8 ファイル: `char.bin`, `matrix.bin`, `sys.dic`, `unk.dic`, `left-id.def`, `pos-id.def`, `rewrite.def`, `right-id.def`) がすべて検証される

---

### FR-W-005: 中国語 / ラテン系言語のフォールバック G2P

**説明:**
現在の character-based fallback を独立メソッドとして提供する。

**現在の処理** (`simple_unified_api.js`):
```javascript
// 中国語: 文字単位で phoneme_id_map を参照
phonemizeChinese(text) {
    const phonemeIds = [1]; // BOS
    for (const char of text) {
        if (phonemeIdMap[char]) {
            phonemeIds.push(...phonemeIdMap[char]);
            phonemeIds.push(0); // PAD
        }
    }
    phonemeIds.push(2); // EOS
    return phonemeIds;
}

// ラテン系 (es/fr/pt): 小文字化 + 文字単位で phoneme_id_map 参照
phonemizeLatinFallback(text) { /* 同様のロジック */ }
```

**受入条件:**
- `G2P.phonemize(text, { language: 'zh' })` がトークン列を返す (ID 列ではなく)
- `G2P.encode(text, phonemeIdMap, { language: 'zh' })` が phoneme ID 列を返す
- BOS(1)/PAD(0)/EOS(2) の挿入が正しく行われる
- 未知文字はスキップされる (現状と同一動作)
- 将来的に pypinyin WASM / 規則ベース G2P へアップグレード可能な設計

---

### FR-W-006: 言語自動検出

**説明:**
`UnicodeLanguageDetector` と同等の精度を持つ言語検出を提供する。

**現在の実装** (`simple_unified_api.js`):
```javascript
detectLanguage(text) {
    let hasKana = false, hasCJK = false;
    for (const char of text) {
        const code = char.charCodeAt(0);
        if ((code >= 0x3040 && code <= 0x309F) ||   // Hiragana
            (code >= 0x30A0 && code <= 0x30FF)) {    // Katakana
            hasKana = true; break;
        }
        if (code >= 0x4E00 && code <= 0x9FFF) hasCJK = true;
    }
    if (hasKana) return 'ja';
    if (hasCJK) return 'zh';
    return 'en';
}
```

**受入条件:**
- Hiragana/Katakana -> JA
- CJK Ideographs (仮名なしコンテキスト) -> ZH
- Hangul -> KO (将来対応用の予約)
- Latin -> 設定されたデフォルト言語 (デフォルト: EN)
- CJK + 仮名混在テキストで JA が優先される
- 全角ラテン文字 (U+FF21-FF5A) が Latin として扱われる (現在の C# 実装と同等)
- `segmentText()` メソッドが提供され、テキスト分割に利用可能
- ES/FR/PT の文字レベル区別は不可能なことを API ドキュメントに明記する

---

### FR-W-007: カスタム辞書サポート

**説明:**
現在の `CustomDictionary` クラスを G2P パッケージに含める。

**現在の API** (`src/wasm/openjtalk-web/src/custom_dictionary.js`):
```javascript
class CustomDictionary {
    constructor()
    async loadFromJSON(urls)                      // URL から辞書ロード (single or array)
    addEntry(word, reading)                       // エントリ追加
    addEntryWithPriority(word, pronunciation, priority)  // 優先度付き追加
    processText(text)                             // テキスト変換 (longest-match-first)
    getReading(word)                              // 読み取得
    removeEntry(word)                             // エントリ削除
    exportToJSON()                                // JSON v1.0 エクスポート
    clear()                                       // クリア
    get size                                      // エントリ数
    hasWord(word)                                 // 存在確認
}
```

**受入条件:**
- JSON v1.0 / v2.0 形式の辞書ファイルをロードできる
- 優先度ベースの競合解決が動作する
- 大文字小文字混在キー (例: "PyTorch") の case-sensitive マッチが動作する
- longest-match-first の適用順序が保証されている
- `processText()` が正規表現キャッシュを使用してパフォーマンスを維持する

---

## 8. JS/WASM npm パッケージ 非機能要求

### NFR-W-001: バンドルサイズ

**説明:** G2P パッケージ単体のサイズを最小化する。

| コンポーネント | サイズ上限 (gzip) |
|---------------|-----------------|
| JS コード (全言語) | < 30KB |
| OpenJTalk WASM | < 400KB |
| 辞書 (tar.gz, 実行時 DL) | ~5MB (既存同一) |
| CMU Dict (optional) | < 100KB |
| 合計 (JA なし) | < 30KB |
| 合計 (JA 込み、辞書除く) | < 430KB |

**受入条件:**
- JA 言語なしの場合 WASM ファイルが含まれない
- `@piper-plus/g2p` のインストールサイズが 1MB 未満 (WASM 込み、辞書除く)
- 辞書は実行時 `DictLoader` 経由でダウンロード (パッケージに含まない)

---

### NFR-W-002: ブラウザ互換性

**説明:** 主要モダンブラウザで動作すること。

**受入条件:**
- Chrome 80+, Firefox 113+, Safari 16.4+ で動作する
- `DecompressionStream` API が利用可能 (辞書 tar.gz 解凍)
- `crypto.subtle` が利用可能 (SHA-256 検証、HTTPS 環境)
- `indexedDB` が利用可能 (辞書キャッシュ)
- Node.js 18+ でも動作する (WASM 含む)

---

### NFR-W-003: Tree-shaking 対応

**説明:** 使用しない言語のコードがバンドルから除外されること。

**受入条件:**
- ESM (`import`/`export`) 形式で提供
- 各言語が独立した subpath export として利用可能:
  ```json
  {
    "exports": {
      ".":              "./src/index.js",
      "./ja":           "./src/ja/index.js",
      "./en":           "./src/en/index.js",
      "./zh":           "./src/zh/index.js",
      "./detect":       "./src/detect.js",
      "./dict":         "./src/dict-loader.js",
      "./custom-dict":  "./src/custom-dictionary.js"
    }
  }
  ```
- `import { G2P } from '@piper-plus/g2p'` で全言語利用可能
- `import { JapaneseG2P } from '@piper-plus/g2p/ja'` で JA のみ利用可能
- webpack / Vite / Rollup で未使用言語がバンドルから除外される

---

### NFR-W-004: パッケージ構成

**説明:** npm パッケージとしての構成。

```
@piper-plus/g2p
  src/
    index.js              # G2P クラス (統合エントリ)
    detect.js             # UnicodeLanguageDetector
    dict-loader.js        # DictLoader (IndexedDB + fetch)
    custom-dictionary.js  # CustomDictionary
    encode.js             # phoneme ID エンコーダー (BOS/PAD/EOS)
    pua-map.js            # PUA マッピングテーブル (87 entries)
    ja/
      index.js            # JapaneseG2P
      phoneme-extract.js  # full-context label パーサー
    en/
      index.js            # EnglishG2P
      dictionary.js       # 発音辞書
      arpabet-to-ipa.js   # ARPAbet -> IPA 変換 (optional)
    zh/
      index.js            # ChineseG2P (character fallback)
    es/
      index.js            # SpanishG2P (character fallback)
    fr/
      index.js            # FrenchG2P (character fallback)
    pt/
      index.js            # PortugueseG2P (character fallback)
  dist/
    openjtalk.wasm        # OpenJTalk WASM バイナリ
    openjtalk.js          # Emscripten glue code
  types/
    index.d.ts            # TypeScript 型定義 (全 API)
  package.json
```

**受入条件:**
- `"type": "module"` (ESM only)
- `"types"` フィールドが設定されている
- `peerDependencies` に `onnxruntime-web` を含めない (G2P は推論不要)
- `engines.node` >= `18.0.0`
- npm publish 時に `dist/`, `src/`, `types/` のみが含まれる (`files` フィールドで制御)

---

### NFR-W-005: piper-plus パッケージとの互換性

**説明:** 既存の `piper-plus` npm パッケージが `@piper-plus/g2p` を内部依存として利用できること。

**受入条件:**
- `piper-plus` の `package.json` に `"@piper-plus/g2p": "^1.0.0"` が dependencies として追加される
- `piper-plus` の `SimpleUnifiedPhonemizer` が内部で `@piper-plus/g2p` の `G2P` クラスを使用する
- 既存の `piper-plus` ユーザー API (`PiperPlus.initialize()`, `PiperPlus.synthesize()`) に破壊的変更がない
- 既存 subpath export `piper-plus/phonemizer` が `@piper-plus/g2p` への re-export として維持される

---

### NFR-W-006: TypeScript 型定義

**説明:** 完全な TypeScript 型定義を提供する。

**受入条件:**
- `types/index.d.ts` がすべての公開 API をカバーしている
- `G2P`, `DictLoader`, `CustomDictionary` クラスの型定義
- `PhonemizeResult`, `EncodeResult`, `ProsodyInfo`, `Language`, `G2POptions`, `PhonemizeOptions`, `JaDictData` 型のエクスポート
- subpath export (`@piper-plus/g2p/ja` 等) の型定義提供
- `tsc --noEmit` でエラーなし

---

### NFR-W-007: テストカバレッジ

**説明:** 独立パッケージとしての十分なテストを提供する。

**受入条件:**
- Node.js test runner (`node --test`) でテスト実行可能
- JA G2P: full-context label パーサー (Kurihara 韻律マーカー、N 変異、PUA マッピング)
- EN G2P: 辞書ベース + letter-to-phoneme ルールフォールバック
- 言語検出: CJK 曖昧性解消、全角ラテン文字処理
- `encode()`: BOS/PAD/EOS 挿入の正確性
- カスタム辞書: JSON v1.0/v2.0 ロード + テキスト変換 + 優先度競合解決
- Python 実装との出力一致検証 (JA + EN、参照データ JSONL)

---

## 9. 共通機能要求 (FR-G)

### FR-G-001: 統一 Phonemizer インターフェース

**タイトル:** 全プラットフォームで概念的に同一の Phonemizer インターフェースを提供する

**説明:**
各プラットフォームの言語慣習に従いつつ、以下の 4 メソッドを概念的に統一する。現状の各実装は既にほぼ同一のシグネチャを持っている。

| 概念 | Python (ABC) | Rust (trait) | C# (interface) | JS/WASM (class) |
|------|-------------|-------------|----------------|-----------------|
| 音素化 | `phonemize(text) -> list[str]` | (phonemize_with_prosody 経由) | `Phonemize(text) -> List<string>` | `phonemize(text) -> string[]` |
| 音素化+韻律 | `phonemize_with_prosody(text) -> (list[str], list[ProsodyInfo\|None])` | `phonemize_with_prosody(text) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>)>` | `PhonemizeWithProsody(text) -> (List<string>, List<ProsodyInfo?>)` | (未実装) |
| ID マップ取得 | `get_phoneme_id_map() -> dict\|None` | `get_phoneme_id_map() -> Option<&PhonemeIdMap>` | `GetPhonemeIdMap() -> Dictionary<string, int[]>?` | (暗黙) |
| 後処理 | `post_process_ids(ids, prosody, map) -> (ids, prosody)` | `post_process_ids(ids, prosody, map) -> (ids, prosody)` | `PostProcessIds(ids, prosody, map) -> (ids, prosody)` | (暗黙) |

**受入条件:**
1. 各パッケージが上記 4 メソッドに相当する API を公開している
2. API リファレンスにメソッドの対応表が記載されている
3. `phonemize()` は `phonemize_with_prosody()` の prosody 捨て版として実装される (DRY)

---

### FR-G-002: 言語レジストリ

**タイトル:** 言語コードからの Phonemizer 解決メカニズムを提供する

**説明:**
単一言語コード (例: `"ja"`) と複合言語コード (例: `"ja-en-zh-es-fr-pt"`) の両方を受け付け、適切な Phonemizer を返す。複合コードの場合は自動的にソート済みの正規化キーを使用し、MultilingualPhonemizer を生成してキャッシュする。

現状の実装:
- **Python**: `registry.py` -- `get_phonemizer(language)` が `_REGISTRY` 辞書を参照。`_auto_register()` でインポート時に自動登録。
- **Rust**: `PhonemizerRegistry` 構造体 -- `register()` / `get()` メソッド。feature flag で言語を選択。
- **C#**: 各 Phonemizer をコンストラクタ DI で組み立て。明示的なレジストリは未実装。独立パッケージ化時に `PhonemizerRegistry` クラスを新設し、static `Get()` ファサード + 内部 DI で Python/Rust と同等の API を提供する。
- **JS/WASM**: `G2P.create({ languages: ['ja', 'en'] })` でファクトリ初期化。レジストリパターンではないが、`G2P.availableLanguages()` で言語一覧を取得可能。

**受入条件:**
1. `get_phonemizer("ja")` 相当の API が全プラットフォームで利用可能 (Python/Rust: `get_phonemizer()`, C#: `PhonemizerRegistry.Get()`, JS: `G2P.create()`)
2. `get_phonemizer("ja-en-zh")` 相当で MultilingualPhonemizer が自動生成される
3. 言語コードの正規化 (`"en-ja"` -> `"en-ja"` ソート済み) が全プラットフォームで統一
4. `available_languages()` 相当で登録済み言語の一覧を取得可能

---

### FR-G-003: 言語自動検出 (UnicodeLanguageDetector)

**タイトル:** Unicode 文字範囲に基づく言語自動検出を全プラットフォームで統一する

**説明:**
`UnicodeLanguageDetector` は以下のルールでテキストを言語セグメントに分割する。この仕様は既に Python / Rust / C# で同一実装を持っており、独立パッケージ化後も変更しない。

| 文字範囲 | 判定言語 | 条件 |
|---------|---------|------|
| U+3040-30FF, U+31F0-31FF (仮名) | ja | 常時 |
| U+AC00-D7AF, U+1100-11FF, U+3130-318F (ハングル) | ko | 常時 |
| U+4E00-9FFF, U+3400-4DBF, U+F900-FAFF (CJK 漢字) | ja / zh | コンテキストに仮名があれば ja, なければ zh |
| U+FF21-FF3A, U+FF41-FF5A (全角ラテン) | default_latin | ラテン扱い (ja ではない) |
| U+3000-303F, U+FF00-FF20, U+FF3B-FFEF (CJK 句読点/全角記号、全角ラテン除く) | ja | 常時 |
| A-Za-z, U+00C0-00FF (ラテン文字) | default_latin | en > es > pt > fr の優先順 |
| その他 (空白, 数字, 句読点) | null (中立) | 直前セグメントに吸収 |

**受入条件:**
1. 上記ルール表が全プラットフォームの実装でパスする共通テストスイートが存在する
2. `segment_text("こんにちはHello你好")` が `[("ja", "こんにちは"), ("en", "Hello"), ("zh", "你好")]` を返す
3. CJK 曖昧性解消: 仮名を含むテキスト内の漢字は ja に分類される
4. 全言語セグメントが空でないことが保証される (全中立文字のみの場合は default_latin にフォールバック)

---

### FR-G-004: PUA (Private Use Area) マッピングテーブル

**タイトル:** 多文字音素トークンから単一 Unicode コードポイントへの固定マッピングを全プラットフォームで共有する

**説明:**
固定 PUA マッピングテーブルが Python (`token_mapper.py`), Rust (`token_map.rs`), C# (`OpenJTalkToPiperMapping.cs`) で同一の値を持つ。学習済みモデルの重みに依存するため、**コードポイントの変更は不可**。

**注**: 現状 Python は 88 エントリ、Rust/C# は 87 エントリで 1 エントリの差分がある。独立パッケージ化時に差分を調査し、全プラットフォームで統一すること。

テーブル構成:
- JA: U+E000-E01C (29 エントリ) -- 長母音, 促音, 口蓋化子音, 疑問詞マーカー, N 変異
- 共有: U+E01D-E01E (2 エントリ) -- `rr` (ES), `y_vowel` (ZH/FR)
- ZH: U+E020-E04A (43 エントリ) -- 有気音, 二重母音, 鼻韻, 声調マーカー
- KO: U+E04B-E052 (8 エントリ) -- 硬音, 内破音
- ES/PT: U+E054-E055 (2 エントリ) -- 破擦音
- FR: U+E056-E058 (3 エントリ) -- 鼻母音

**受入条件:**
1. 全 4 プラットフォームのマッピングテーブルが 87 エントリ完全一致する
2. CI でテーブル整合性を検証するクロスプラットフォームテストが実行される
3. PUA テーブルは各パッケージ内に静的定義として含まれ、外部ファイル依存なし
4. 動的 PUA 割り当て (U+E059~) はパッケージ外部 (学習パイプライン) の機能として分離

---

### FR-G-005: 音素体系の互換性

**タイトル:** 同一テキスト入力から全プラットフォームで同一の phoneme_ids シーケンスを生成する

**説明:**
独立パッケージ化の最重要要件。各プラットフォームの phonemize -> token mapping -> ID 変換 -> post_process_ids のパイプライン全体を通じて、同一入力に対して同一出力を保証する。

パイプライン:
```
テキスト -> phonemize_with_prosody() -> [tokens, prosody]
         -> token_to_id (PUA + phoneme_id_map) -> [phoneme_ids, prosody_features]
         -> post_process_ids() -> [final_ids, final_prosody]  (BOS/PAD/EOS 挿入)
```

**受入条件:**
1. 以下の参照テストケースが全プラットフォームで同一結果を生成する:
   - JA: `"こんにちは"` -> phoneme_ids (参照値を定義)
   - EN: `"Hello world"` -> phoneme_ids (参照値を定義)
   - ZH: `"你好"` -> phoneme_ids (参照値を定義)
   - 混在: `"こんにちはHello你好"` -> phoneme_ids (参照値を定義)
2. 参照テストケースは JSON ファイルとして各パッケージの test fixtures に含まれる
3. **例外**: JS/WASM は JA のみ OpenJTalk WASM、他言語はキャラクタベースのため、EN/ZH/ES/FR/PT の phoneme_ids は他プラットフォームと異なりうる。JA の phoneme_ids は完全一致を要求する

---

### FR-G-006: カスタム辞書

**タイトル:** JSON v1.0/v2.0 + TSV 形式のカスタム辞書を全プラットフォームで共通仕様とする

**説明:**
カスタム辞書はテキスト前処理段階で単語を読みに置換する機能。以下の 3 フォーマットを全プラットフォームでサポートする。

**JSON v1.0:**
```json
{ "version": "1.0", "entries": { "API": "エーピーアイ" } }
```

**JSON v2.0:**
```json
{
  "version": "2.0",
  "entries": {
    "API": { "pronunciation": "エーピーアイ", "priority": 8 },
    "// comment": { "pronunciation": "ignored", "priority": 0 }
  }
}
```

**TSV (C# 追加サポート):**
```
# コメント行
API	エーピーアイ
```

共通仕様:
- `//` で始まるキーはコメントとしてスキップ
- 優先度: 0-10 の整数、デフォルト 5、高い方が勝つ
- 大文字小文字混在キー (例: `"GitHub"`) は case-sensitive マッチ
- 全大文字/全小文字キーは case-insensitive マッチ (lowercase 正規化)
- 非 ASCII キー (日本語等) は単純部分文字列マッチ
- ASCII キーは単語境界マッチ
- 適用順: 長いキーから順 (longest-match-first)

**受入条件:**
1. 同一辞書ファイルを全プラットフォームに渡した場合、同一テキストに対して同一の置換結果を返す
2. v1.0/v2.0 の両フォーマットが全プラットフォームで読み込み可能
3. case-sensitive / case-insensitive の振り分けロジックが全プラットフォームで統一
4. 優先度による上書きルールが全プラットフォームで統一

---

### FR-G-007: ProsodyInfo (韻律情報)

**タイトル:** A1/A2/A3 の 3 次元韻律情報を全プラットフォームで共通構造として提供する

**説明:**
`ProsodyInfo` は phoneme 単位に付与される韻律情報。言語により意味が異なる。

| フィールド | JA | EN | ZH/ES/FR/PT |
|-----------|-----|-----|-------------|
| A1 | アクセント核からの相対位置 | 0 (固定) | 0 (固定) |
| A2 | アクセント句内モーラ位置 (1-based) | ストレスレベル (0/1/2) | 0 (固定) |
| A3 | アクセント句の総モーラ数 | 単語内音素数 | 0 (固定) |

現状の実装:
- **Python**: `@dataclass ProsodyInfo(a1: int, a2: int, a3: int)`
- **Rust**: `pub struct ProsodyInfo { pub a1: i32, pub a2: i32, pub a3: i32 }`
- **C#**: `public record struct ProsodyInfo(int A1, int A2, int A3)`
- **JS/WASM**: 未実装 (phoneme_ids のみ)

**受入条件:**
1. ProsodyInfo は全プラットフォームで 3 フィールド (a1, a2, a3) の整数タプルとして定義
2. phonemize_with_prosody() が返す prosody リストは tokens リストと同長
3. prosody が不要な位置 (句読点, 特殊トークン) は null/None/Option::None で表現
4. ONNX 入力用のフラット化 (`[a1_0, a2_0, a3_0, a1_1, a2_1, a3_1, ...]`) はパッケージ外部 (推論パイプライン側) の責務

---

### FR-G-008: 多言語音素化 (MultilingualPhonemizer)

**タイトル:** N 言語のコードスイッチングテキストを統一音素空間で処理する

**説明:**
MultilingualPhonemizer は以下の処理を行う:
1. `UnicodeLanguageDetector` でテキストを言語セグメントに分割
2. 各セグメントを対応する言語 Phonemizer に委譲
3. 各セグメントの BOS/EOS を除去し、結果を連結
4. 最後に見た EOS トークン (疑問詞マーカーを含む) を記録
5. `post_process_ids()` で統一的な BOS + PAD + ... + EOS を付与

現状の実装:
- **Python**: `MultilingualPhonemizer(Phonemizer)` -- `_last_eos` でスレッド非安全な EOS 追跡
- **Rust**: `MultilingualPhonemizer` -- `Mutex<String>` で EOS を保護
- **C#**: `MultilingualPhonemizer : IPhonemizer` -- `ThreadLocal<string>` でスレッド安全
- **JS/WASM**: `SimpleUnifiedPhonemizer` -- 概念的に同等だが API が異なる

**受入条件:**
1. 混在テキストの分割・再結合が全プラットフォームで同一結果を生成する
2. EOS トークンの追跡 (疑問詞マーカー `?!`, `?.`, `?~` を含む) が正しく動作する
3. Python パッケージではスレッド安全性の制約を API ドキュメントに明記する
4. 統一 phoneme_id_map の生成 (`get_multilingual_id_map()`) がパッケージ内に含まれる

---

### FR-G-009: 言語別 Phonemizer

**タイトル:** 7 言語の Phonemizer を独立して利用可能にする

**説明:**
各言語の Phonemizer は個別にインスタンス化して使用可能とする。依存ライブラリは言語ごとにオプショナルとする。

| 言語 | Phonemizer | Python 依存 | Rust feature | C# NuGet | JS/WASM |
|------|-----------|------------|-------------|----------|---------|
| JA | JapanesePhonemizer | pyopenjtalk-plus (BSD-3) | `japanese` (jpreprocess, MIT) | DotNetG2P + MeCab (Apache-2.0) | OpenJTalk WASM (BSD-3) |
| EN | EnglishPhonemizer | g2p-en (Apache-2.0) | (ルールベース) | DotNetG2P.English (Apache-2.0) | SimpleEnglishPhonemizer (辞書ベース) |
| ZH | ChinesePhonemizer | pypinyin (MIT) | (ルールベース) | DotNetG2P.Chinese (Apache-2.0) | キャラクタベース |
| KO | KoreanPhonemizer | g2pk2 (Apache-2.0) | (ルールベース) | (未実装) | (未実装) |
| ES | SpanishPhonemizer | (ルールベース) | (ルールベース) | DotNetG2P.Spanish (Apache-2.0) | キャラクタベース |
| FR | FrenchPhonemizer | (ルールベース) | (ルールベース) | DotNetG2P.French (Apache-2.0) | キャラクタベース |
| PT | PortuguesePhonemizer | (ルールベース) | (ルールベース) | DotNetG2P.Portuguese (Apache-2.0) | キャラクタベース |

**受入条件:**
1. `piper-g2p[ja]` (Python) のように言語別のオプショナル依存でインストール可能
2. Rust: `piper-g2p = { features = ["japanese"] }` で言語選択可能
3. C#: メタパッケージ `PiperPlus.Phonemize` で全言語、個別パッケージ `PiperPlus.Phonemize.Japanese` 等で言語選択可能
4. 依存がインストールされていない言語の `get_phonemizer()` はインポートエラー/コンパイルエラーで明確に失敗する

---

### FR-G-010: インライン音素記法

**タイトル:** `[[ phoneme ]]` 記法によるテキスト中の直接音素指定をサポートする

**Phase 割り当て:** Phase 2 以降 (Phase 1 スコープ外。C# は既存実装を移行、Python/Rust は新規実装)

**説明:**
テキスト中に `[[ k o N n i ch i w a ]]` のように直接音素を指定できる記法。現在 C# (`InlinePhonemeParser.cs`, `RawPhonemeParser.cs`) で実装済み。独立パッケージとして Python / Rust にも展開する。

**受入条件:**
1. `[[ ... ]]` で囲まれた部分はそのまま音素トークンとして出力される
2. 通常テキストとインライン音素の混在が可能
3. PUA マッピングはインライン音素にも適用される

---

## 10. 共通非機能要求 (NFR-G)

### NFR-G-001: ライセンスクリーン

**タイトル:** 全依存が MIT / Apache-2.0 / BSD-3-Clause のいずれかである

**説明:**
GPL 汚染ゼロが本パッケージの最大の差別化ポイント。eSpeak-ng (GPL-3.0) への依存は一切持たない。

**受入条件:**
1. 各パッケージの依存ツリーに GPL ライセンスの依存が存在しない
2. CI で `cargo deny check licenses` (Rust), `pip-licenses` (Python), `dotnet-project-licenses` (C#) によるライセンスチェックが実行される
3. パッケージの LICENSE ファイルが MIT (Python/Rust/JS) または MIT + Apache-2.0 デュアル (Rust) で提供される

---

### NFR-G-002: ゼロ C/C++ ビルド依存 (Python/Rust/C#)

**タイトル:** C/C++ コンパイラなしでインストール可能

**説明:**
eSpeak-ng / pyopenjtalk の C++ ビルド失敗は最頻出 Issue。Python パッケージは pure Python + wheel 提供、Rust は pure Rust、C# は managed code のみとする。

**受入条件:**
1. Python: `pip install piper-g2p` が C コンパイラなしで完了する (JA は `pyopenjtalk-plus` の wheel に依存。macOS/Linux/Windows の主要プラットフォームで wheel 提供済みを確認済み。wheel 未提供環境では `piper-g2p[ja]` インストール時にエラーメッセージでビルド要件を案内する)
2. Rust: `cargo build` に C/C++ ツールチェーンが不要
3. C#: `dotnet build` のみで完了する
4. 例外: JS/WASM の OpenJTalk はプリコンパイル済み WASM バイナリとして配布

---

### NFR-G-003: テスト網羅

**タイトル:** 80% 以上のコードカバレッジと共通テストフィクスチャ

**説明:**
各パッケージが独立したテストスイートを持ち、クロスプラットフォーム互換性テストとして共通テストフィクスチャ (JSON) を使用する。

**受入条件:**
1. 各パッケージで 80% 以上の行カバレッジ
2. 共通テストフィクスチャ `test/fixtures/g2p-compatibility.json` が以下を含む:
   - 入力テキスト
   - 期待 phoneme tokens
   - 期待 phoneme_ids (phoneme_id_map 適用後)
   - 期待 prosody features
3. 各プラットフォームの CI がこのフィクスチャに対してパスする

---

### NFR-G-004: パフォーマンス

**タイトル:** 一般的なテキスト (100 文字程度) の音素化が 10ms 以内

**説明:**
TTS パイプラインのボトルネックにならない処理速度を確保する。

**受入条件:**
1. JA 100 文字テキストの phonemize_with_prosody() が 10ms 以内 (Python/Rust/C#)
2. EN 100 文字テキストの phonemize_with_prosody() が 5ms 以内
3. 各パッケージにベンチマークスクリプト/テストが含まれる

---

### NFR-G-005: API ドキュメント

**タイトル:** 全パッケージに言語慣習に沿った API ドキュメントを提供する

**受入条件:**
1. Python: docstring (Google スタイル) + Sphinx/MkDocs による HTML ドキュメント
2. Rust: `/// ` doc comment + `cargo doc` による HTML ドキュメント
3. C#: XML doc comment + README
4. JS/WASM: JSDoc + TypeScript 型定義 (`index.d.ts`)

---

## 11. 統合・マイグレーション要求 (FR-I)

### FR-I-001: Python import パス互換性

**タイトル:** 既存 `piper_train.phonemize` からの段階的マイグレーションパスを提供する

**説明:**
既存ユーザーが `from piper_train.phonemize import ...` を使用している。新パッケージは `from piper_g2p import ...` を提供しつつ、`piper_train.phonemize` を互換シム (re-export) として維持する。

**受入条件:**
1. `from piper_g2p import get_phonemizer, Phonemizer, ProsodyInfo` が動作する
2. `from piper_g2p.japanese import JapanesePhonemizer` が動作する
3. `from piper_train.phonemize import get_phonemizer` が `piper_g2p` に委譲される (DeprecationWarning 付き)
4. `piper_train` パッケージの `pyproject.toml` に `piper-g2p` が依存として追加される
5. 互換シムは少なくとも 2 マイナーバージョン (6 か月以上) 維持される

---

### FR-I-002: Rust crate 分離

**タイトル:** `piper-core` から `piper-g2p` crate を分離し、`piper-core` が依存として使用する

**説明:**
現在の `piper-core/src/phonemize/` ディレクトリを新 crate `piper-g2p` に移動する。`piper-core` は `piper-g2p` を依存として追加し、re-export する。

**受入条件:**
1. `piper-g2p` crate が `piper-core` から独立してコンパイル可能
2. `piper-core` の `phonemize` モジュールが `pub use piper_g2p::*;` で re-export
3. `piper-g2p` は `PiperError` に依存せず、独自のエラー型 `G2pError` を定義する
4. `piper-g2p` の `PhonemeIdMap` は `HashMap<String, Vec<i64>>` 型エイリアスとして定義 (piper-core の config 依存を排除)
5. 既存の `piper-core` ユーザーのコード変更がゼロ

---

### ~~FR-I-003: C# プロジェクト分離~~ → 対象外

DotNetG2P が既に独立 G2P パッケージとして NuGet に公開済みのため、`PiperPlus.Phonemize` の分離は不要。PiperPlus.Core の Phonemize レイヤー (PUA マッピング、MultilingualPhonemizer、PhonemeEncoder 等) は PiperPlus.Core 内に留まる。

---

### FR-I-004: JS/WASM パッケージ分離

**タイトル:** `piper-plus` npm パッケージから G2P レイヤーを `@piper-plus/g2p` として分離する

**説明:**
`SimpleUnifiedPhonemizer` クラスを独立パッケージに切り出す。OpenJTalk WASM の初期化と辞書ダウンロードは外部注入パターンに変更する。

**受入条件:**
1. `@piper-plus/g2p` が `piper-plus` なしでインストール・使用可能
2. OpenJTalk WASM モジュールはコンストラクタへの注入で提供 (ハードコード依存の排除)
3. `DictManager` の辞書ダウンロード機能は `@piper-plus/g2p` に含まれる
4. `piper-plus` は `@piper-plus/g2p` を dependency として使用
5. TypeScript 型定義 (`index.d.ts`) が `@piper-plus/g2p` に含まれる

---

### FR-I-005: TTS フレームワーク統合ガイド

**タイトル:** 主要 TTS フレームワークへの組み込み方法をドキュメント化する

**Phase 割り当て:** Phase 1 v1.0.0 リリース後のドキュメントタスク

**説明:**
eSpeak-ng を `piper-g2p` で置き換えるための統合ガイドを提供する。

**受入条件:**
1. VITS / VITS2 への統合例 (Python):
   ```python
   from piper_g2p import get_phonemizer
   phonemizer = get_phonemizer("ja-en")
   tokens, prosody = phonemizer.phonemize_with_prosody(text)
   ```
2. Fish Speech への統合例 (Python): 同上
3. Coqui TTS への統合例 (Python): phonemizer バックエンドの差し替え手順
4. Unity (C#) への統合例: NuGet パッケージ参照 + 基本使用法
5. ブラウザ TTS (JS) への統合例: npm install + initialize + phonemize

---

### FR-I-006: CI/CD パイプライン

**タイトル:** 各パッケージの CI/CD を独立して構築する

**説明:**
各パッケージが独立した CI ワークフローを持ち、テスト・ビルド・パブリッシュを自動化する。

**受入条件:**
1. Python: GitHub Actions で pytest + mypy + ruff チェック、PyPI パブリッシュ (タグトリガー)
2. Rust: GitHub Actions で cargo test + cargo clippy + cargo fmt、crates.io パブリッシュ (タグトリガー)
3. C#: GitHub Actions で dotnet test + dotnet build、NuGet パブリッシュ (タグトリガー)
4. JS/WASM: GitHub Actions で node --test、npm パブリッシュ (タグトリガー)
5. クロスプラットフォーム互換性テスト: 共通フィクスチャに対するテストが全 CI で実行される

---

## 12. リリース戦略

### 12.1 フェーズ定義

#### Phase 1: Python + Rust (最優先)

| 項目 | 内容 |
|------|------|
| **スコープ** | `piper-g2p` (PyPI) + `piper-g2p` (crates.io) |
| **優先度** | 最高 |
| **推定工数** | 2-3 週 |
| **理由** | TTS 開発者の大半は Python / Rust ユーザー。eSpeak-ng 置き換え需要が最も高い |

**タスク:**
1. PUA エントリ数の差分調査・統一 (Python 88 vs Rust/C# 87)
2. Python パッケージ構造の作成 (`piper_g2p/`)
3. `piper_train.phonemize` からのコード移動 + 互換シム作成
4. `pyproject.toml` の整備 (言語別 optional deps)
5. `JapanesePhonemizer` に `custom_dict` コンストラクタ引数を追加
6. Rust crate 作成 (`piper-g2p/`)
7. `piper-core` からの phonemize モジュール移動 + re-export
8. 共通テストフィクスチャ JSON の作成
9. CI ワークフローの構築
10. API ドキュメントの作成

**Phase 1 に含まれる共通要求:** FR-G-001~009, NFR-G-001~005, FR-I-001, FR-I-002
**Phase 1 スコープ外:** FR-G-010 (インライン音素記法), FR-I-005 (TTS 統合ガイド)

**マイルストーン:**
- v0.1.0: 内部リリース (piper_train からの互換確認)
- v0.2.0: PyPI / crates.io へのベータ公開
- v1.0.0: 安定版リリース

#### ~~Phase 2: C# NuGet パッケージ~~ → 対象外

DotNetG2P (NuGet) が既に独立 G2P パッケージとして公開済みのため、`PiperPlus.Phonemize` の新規作成は不要。

#### Phase 2: JS/WASM リファクタリング (旧 Phase 3)

| 項目 | 内容 |
|------|------|
| **スコープ** | `@piper-plus/g2p` (npm) |
| **優先度** | 低 (ただし将来的に重要) |
| **推定工数** | 3-4 週 |
| **理由** | 結合度が高く工数大。ブラウザ TTS 市場の成長に合わせて実施 |

**タスク:**
1. `SimpleUnifiedPhonemizer` の分離リファクタリング
2. OpenJTalk WASM の DI 化
3. `DictManager` の分離
4. `phonemize_with_prosody()` API の追加
5. TypeScript 型定義の整備
6. npm パブリッシュ設定

**マイルストーン:**
- v0.1.0: npm ベータ公開
- v1.0.0: 安定版リリース

---

### 12.2 バージョニング戦略

全パッケージで SemVer (Semantic Versioning) 2.0.0 を採用する。

| バージョン変更 | 条件 |
|--------------|------|
| MAJOR (x.0.0) | PUA テーブルの変更、phoneme_ids 互換性の破壊、API の破壊的変更 |
| MINOR (0.x.0) | 新言語の追加、新機能の追加、新フォーマット対応 |
| PATCH (0.0.x) | バグ修正、パフォーマンス改善、ドキュメント修正 |

**重要ルール:**
- PUA マッピングテーブルは MAJOR バージョンでのみ変更可能 (学習済みモデルとの互換性)
- 全 4 パッケージの MAJOR バージョンは同期する (v1.x.x の Python は v1.x.x の Rust と互換)
- MINOR / PATCH は各パッケージで独立して進行可能

---

### 12.3 パッケージレジストリ公開手順

#### Python (PyPI)

```bash
# ビルド
uv build

# テスト
uv run pytest tests/

# テスト公開 (TestPyPI)
uv publish --publish-url https://test.pypi.org/legacy/

# 本番公開
uv publish
```

**トリガー:** `v*-python` タグ (例: `v1.0.0-python`)

#### Rust (crates.io)

```bash
# ビルド + テスト
cargo build --release -p piper-g2p
cargo test -p piper-g2p

# 公開
cargo publish -p piper-g2p
```

**トリガー:** `v*-rust` タグ (例: `v1.0.0-rust`)

#### C# (NuGet)

```bash
# ビルド + テスト
dotnet build src/csharp/PiperPlus.Phonemize/
dotnet test src/csharp/PiperPlus.Phonemize.Tests/

# パック + 公開
dotnet pack -c Release
dotnet nuget push *.nupkg --source https://api.nuget.org/v3/index.json
```

**トリガー:** `v*-csharp` タグ (例: `v1.0.0-csharp`)

#### JS/WASM (npm)

```bash
# テスト
node --test test/

# 公開
npm publish --access public
```

**トリガー:** `v*-npm` タグ (例: `v1.0.0-npm`)

---

## 13. 現状からの差分サマリ

以下は、独立パッケージ化に際して各プラットフォームで必要な主な変更をまとめたものである。

### Python

| 項目 | 現状 | 変更 |
|------|------|------|
| パッケージ名 | `piper_train` (G2P は submodule) | `piper_g2p` (独立パッケージ) |
| import パス | `from piper_train.phonemize import ...` | `from piper_g2p import ...` + 互換シム |
| 依存 | piper_train の全依存を引き込む | 言語別 optional deps のみ |
| custom_dict パス | `Path(__file__).parent..../"data"/"dictionaries"` (相対パス) | 設定可能なパスに変更 |

### Rust

| 項目 | 現状 | 変更 |
|------|------|------|
| crate 名 | `piper-core` (phonemize は submodule) | `piper-g2p` (独立 crate) |
| エラー型 | `PiperError` | `G2pError` (独自定義) |
| PhonemeIdMap | `crate::config::PhonemeIdMap` | `HashMap<String, Vec<i64>>` 型エイリアス |

### C# → 対象外

DotNetG2P が既に独立 G2P パッケージとして NuGet に公開済み。PiperPlus.Core の変更なし。

### JS/WASM

| 項目 | 現状 | 変更 |
|------|------|------|
| パッケージ名 | `piper-plus` (G2P は内包) | `@piper-plus/g2p` (独立パッケージ) |
| OpenJTalk 初期化 | コンストラクタ内でハードコード | DI パターン (外部注入) |
| phonemize API | `synthesize()` に内包 | 独立 `phonemize()` メソッド |
| prosody | 未実装 | `phonemizeWithProsody()` を追加 |
