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
- 要求トレーサビリティ (セクション 13)

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
13. [要求トレーサビリティ](#13-要求トレーサビリティ)

---

## 1. Python パッケージ (`piper-g2p`) 機能要求

> 技術調査により、`phonemize/` は `piper_train` 他モジュール (学習・推論・データセット準備) への依存がゼロであることが確認済み。移動対象 22 ファイル、`piper_train` 側の互換シムが必要なファイルは 6 つ (`preprocess.py`, `update_model_config.py`, `vits/lightning.py`, `tools/prepare_bilingual_dataset.py`, `tools/prepare_multilingual_dataset.py`, `tools/add_prosody_features.py`)。PUA エントリは全プラットフォーム 87 で一致済みのため差分タスクは不要。

### FR-P-001: コア API (Phonemizer ABC + レジストリ)

**説明**: `Phonemizer` 抽象基底クラス、`ProsodyInfo` データクラス、および言語レジストリ (`get_phonemizer()`, `register_language()`, `available_languages()`) をパッケージの公開 API として提供する。

**現在の API**:
```python
# base.py
@dataclass
class ProsodyInfo:
    a1: int; a2: int; a3: int

class Phonemizer(ABC):
    @abstractmethod
    def phonemize(self, text: str) -> list[str]: ...
    @abstractmethod
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    @abstractmethod
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...
    def post_process_ids(self, phoneme_ids, prosody_features, phoneme_id_map, eos_token="$") -> tuple[list[int], list[dict | None]]: ...

# registry.py
def register_language(code: str, phonemizer: Phonemizer): ...
def get_phonemizer(language: str) -> Phonemizer: ...
def available_languages() -> list[str]: ...
```

**受入条件**:
- `from piper_g2p import Phonemizer, ProsodyInfo, get_phonemizer, register_language, available_languages` でインポートできる
- `Phonemizer` は `phonemize()`, `phonemize_with_prosody()`, `get_phoneme_id_map()` を抽象メソッドとして持つ
- `post_process_ids()` のデフォルト実装 (BOS/EOS/パディング挿入) が動作する
- `get_phonemizer("ja")` で `JapanesePhonemizer` が返る (pyopenjtalk インストール時)
- `get_phonemizer("ja-en")` で `MultilingualPhonemizer(["en", "ja"])` が返る (canonical sorted order に正規化)
- 依存が未インストールの言語はレジストリ自動登録時にスキップされ `ImportError` にならない
- `register_language("custom", MyPhonemizer())` でカスタム言語を登録できる
- 既存の `piper_train.phonemize.base` / `piper_train.phonemize.registry` と型シグネチャが同一

---

### FR-P-002: 言語別 Phonemizer (7 言語)

**説明**: 7 言語の Phonemizer を個別にインスタンス化して使用可能にする。各言語の外部依存はオプショナル。

| 言語 | クラス | 外部依存 (optional) | 主な特徴 |
|------|--------|-------------------|---------|
| JA | `JapanesePhonemizer` | `pyopenjtalk-plus` (BSD-3) | 栗原法韻律記号、N 音素変異 (N_m/N_n/N_ng/N_uvular)、疑問詞マーカー (`?!`/`?.`/`?~`)、カスタム辞書 |
| EN | `EnglishPhonemizer` | `g2p-en>=2.1.0` (Apache-2.0) | ARPAbet-to-IPA、機能語ストレス除去 (97 語)、OOV 形態素フォールバック |
| ZH | `ChinesePhonemizer` | `pypinyin>=0.50` (MIT) | 漢字→ピンイン→IPA、声調サンドヒ (3 声/一/不)、儿化音、コーパス高速パス (`phonemize_from_pinyin_syllables()`) |
| KO | `KoreanPhonemizer` | `g2pk2>=0.0.3` (Apache-2.0) | Hangul 分解 + IPA、音韻規則 (連音化/鼻音化/激音化/硬音化)、g2pk2 未インストール時のフォールバック |
| ES | `SpanishPhonemizer` | なし (Pure Python) | ルールベース、Latin American seseo、音節分割、ストレス推定 |
| PT | `PortuguesePhonemizer` | なし (Pure Python) | ルールベース、ブラジル PT、鼻母音化、l 母音化、t/d 口蓋化 |
| FR | `FrenchPhonemizer` | なし (Pure Python) | ルールベース、鼻母音、母音ダイグラフ、語末子音サイレンス |

**JapanesePhonemizer の変更点**: 現在の実装にはコンストラクタがなく `custom_dict` は関数 API (`phonemize_japanese()`) のみで利用可能。独立パッケージ化時に `JapanesePhonemizer.__init__(self, custom_dict=None)` を追加し、クラスレベルでカスタム辞書を保持できるよう拡張する。

```python
# 変更後の JapanesePhonemizer
class JapanesePhonemizer(Phonemizer):
    def __init__(self, custom_dict: CustomDictionary | str | list[str] | None = None): ...
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # returns None
    def post_process_ids(self, ...): ...  # no-op (JA handles BOS/EOS inline)
```

**受入条件**:
- 各言語の import パスが `from piper_g2p.<lang> import <Lang>Phonemizer, phonemize_<lang>` 形式で動作する
- 各言語の `phonemize_with_prosody()` が `(list[str], list[ProsodyInfo | None])` を返す
- 全言語の `get_phoneme_id_map()` は `None` を返す (ID マップは FR-P-004 の別モジュールで提供)
- JA: `JapanesePhonemizer(custom_dict="path/to/dict.json")` でカスタム辞書付きインスタンスを生成できる
- JA: PUA マッピング (`token_mapper`) によって多文字トークンが 1 コードポイントに変換される
- JA: `post_process_ids()` は no-op (BOS/EOS はインライン処理)
- EN: ProsodyInfo で `a1=0`, `a2=stress_level (0/1/2)`, `a3=word_phoneme_count`
- ZH: ProsodyInfo で `a1=tone (1-5)`, `a2=syllable_position`, `a3=word_length`
- ZH: `phonemize_from_pinyin_syllables()` でコーパスの事前解析済みピンインから直接変換可能
- KO: g2pk2 未インストール時は音韻規則なしのフォールバック (warning ログ)

---

### FR-P-003: 多言語 Phonemizer

**説明**: `MultilingualPhonemizer` (Unicode 言語自動検出 + セグメント分割 + 委譲) と、旧バイリンガルモデルとの後方互換のための `BilingualPhonemizer` を提供する。

**現在の API**:
```python
# multilingual.py
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

# bilingual.py
class BilingualPhonemizer(MultilingualPhonemizer):
    def __init__(self, languages: list[str]): ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...
```

**受入条件**:
- `from piper_g2p.multilingual import MultilingualPhonemizer, UnicodeLanguageDetector`
- `from piper_g2p.bilingual import BilingualPhonemizer`
- CJK 曖昧性解消 (かな文脈で漢字を JA/ZH 判定) が正しく動作する
- 個別セグメントの BOS/EOS は除去され、全体で 1 つの BOS/EOS が付加される
- `get_phonemizer("ja-en-zh")` でレジストリから自動生成される
- `BilingualPhonemizer(["ja", "en"])` で旧バイリンガル ID マップが返る
- スレッド安全性の制約を API ドキュメントに明記する (Python の `_last_eos` はスレッド非安全)

---

### FR-P-004: トークンマッパー + ID マップ

**説明**: 多文字音素トークンを Unicode PUA の 1 コードポイントに変換するトークンマッパー (87 エントリ固定) と、各言語の音素インベントリを定義する ID マップモジュール群を提供する。

**現在の API**:
```python
# token_mapper.py
FIXED_PUA_MAPPING: dict[str, int]  # 87 entries (全プラットフォーム一致済み)
TOKEN2CHAR: dict[str, str]
CHAR2TOKEN: dict[str, str]
def register(token: str) -> str: ...
def map_sequence(seq: list[str]) -> list[str]: ...

# multilingual_id_map.py
def get_multilingual_id_map(languages: list[str]) -> dict[str, list[int]]: ...
LANGUAGE_PHONEMES: dict[str, list[str]]
```

**受入条件**:
- `from piper_g2p.token_mapper import map_sequence, register, TOKEN2CHAR, CHAR2TOKEN, FIXED_PUA_MAPPING`
- `from piper_g2p.multilingual_id_map import get_multilingual_id_map`
- 固定 PUA マッピングが全 87 エントリで Python/Rust/C# 間と一致する
- `map_sequence()` で多文字トークンが PUA 1 コードポイントに変換される。単一コードポイントのトークンはそのまま返す
- `get_multilingual_id_map(["ja", "en", "zh"])` で 3 言語統合の `dict[str, list[int]]` が返る
- 共有音素 (例: `"b"`, `"d"`, `"m"`) は 1 つの ID に統一される
- Piper TTS の `config.json` 形式と互換性がある
- 動的 PUA 割り当て (U+E059~) はパッケージ外部 (学習パイプライン) の機能として分離

---

### FR-P-005: カスタム辞書

**説明**: JSON v1.0/v2.0 形式のカスタム辞書をロードし、テキスト前処理で単語を読みに置換する。

**現在の API**:
```python
# custom_dict.py
class CustomDictionary:
    def __init__(self, dict_paths: str | list[str] | None = None, load_defaults: bool = True): ...
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
- 大文字小文字混在ワードの case-sensitive マッチ、全大文字/全小文字は case-insensitive マッチ
- 適用順は longest-match-first、優先度 (0-10) による競合解決
- デフォルト辞書ディレクトリは `piper_g2p` パッケージ内の `data/dictionaries/` にバンドルする、またはランタイム設定可能にする (現在のハードコードパス `Path(__file__).parent.../"data"/"dictionaries"` を汎用化)
- `CustomDictionary(load_defaults=False)` でデフォルト辞書の読み込みをスキップできる (既存動作を維持)
- `piper-train` 側のデフォルト辞書パスとの整合性を保つ

---

## 2. Python パッケージ 非機能要求

### NFR-P-001: パッケージング + optional dependencies

**説明**: `piper-g2p` として PyPI に公開可能な形式で配布し、言語別の外部依存を optional extras として管理する。

**pyproject.toml 概要**:
```toml
[build-system]
requires = ["setuptools>=45", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "piper-g2p"
version = "0.1.0"
description = "Multi-language G2P (Grapheme-to-Phoneme) library for TTS — eSpeak-ng free"
license = {text = "MIT"}
requires-python = ">=3.11"
dependencies = []  # コア依存なし

[project.optional-dependencies]
ja = ["pyopenjtalk-plus>=0.4"]
en = ["g2p-en>=2.1.0"]
zh = ["pypinyin>=0.50"]
ko = ["g2pk2>=0.0.3"]
es = []
fr = []
pt = []
all = ["piper-g2p[ja,en,zh,ko]"]
dev = ["pytest>=7.0", "ruff>=0.12", "mypy>=1.0"]
```

**受入条件**:
- `uv pip install piper-g2p` でインストールできる (C コンパイラ不要)
- パッケージ名: `piper-g2p` (PyPI), インポート名: `piper_g2p`
- ライセンス: MIT。全依存が MIT / Apache-2.0 / BSD-3-Clause (GPL 汚染ゼロ)
- Python: `>=3.11` (pyopenjtalk-plus 0.4.x の最低サポートバージョンと整合)
- ビルド/公開: `uv build` + `uv publish`
- `uv pip install piper-g2p[ja]` で `pyopenjtalk-plus` がインストールされる
- `uv pip install piper-g2p[all]` で全言語の依存がインストールされる
- 外部依存なしでもコアモジュール (base, registry, token_mapper, custom_dict, es, fr, pt) が利用可能

---

### NFR-P-002: piper-train との後方互換性

**説明**: `piper-train` パッケージが `piper-g2p` を依存として使用し、既存の import パスを互換シムで維持する。技術調査で特定された 6 ファイルの import を `piper_g2p` への re-export で解決する。

**互換シム**:
```python
# piper_train/phonemize/__init__.py (移行後)
import warnings
warnings.warn(
    "piper_train.phonemize is deprecated. Use piper_g2p instead.",
    DeprecationWarning, stacklevel=2,
)
from piper_g2p import *  # re-export
```

**受入条件**:
- `from piper_train.phonemize import Phonemizer, ProsodyInfo, get_phonemizer` が引き続き動作する (DeprecationWarning 付き)
- `piper-train` の `pyproject.toml` に `piper-g2p` が依存として追加される
- 既存のテストが変更なしでパスする
- 互換シムの対象: `preprocess.py`, `update_model_config.py`, `vits/lightning.py`, `tools/prepare_bilingual_dataset.py`, `tools/prepare_multilingual_dataset.py`, `tools/add_prosody_features.py`
- 互換シムは少なくとも 2 マイナーバージョン (6 か月以上) 維持される

---

### NFR-P-003: テスト

**説明**: 独立パッケージとして十分なテストカバレッジを持ち、CI で自動検証する。

**受入条件**:
- 全公開関数/クラスに対するユニットテストが存在する
- CI (`g2p-python-ci.yml`) で 3 OS (Linux, macOS, Windows) x Python 3.11/3.12/3.13 で実行される
- テスト実行: `uv run pytest tests/ -v --cov=piper_g2p`
- 各言語 Phonemizer の基本的な入出力テスト (最低 3 ケース/言語)
- `MultilingualPhonemizer` のコードスイッチングテスト (JA+EN 混在文、JA+EN+ZH 3 言語混在)
- `CustomDictionary` の JSON v1.0/v2.0 ロードテスト
- `token_mapper` の PUA マッピング 87 エントリ一貫性テスト (Rust/C# との一致検証)
- 共通テストフィクスチャ `test/fixtures/g2p-compatibility.json` を使用したクロスプラットフォーム互換テスト
- lint: `uv run ruff check` + `uv run ruff format --check` + `uv run mypy --strict --ignore-missing-imports`
- 80% 以上のコードカバレッジ

---

### NFR-P-004: パフォーマンス

**説明**: 独立パッケージ化によるパフォーマンス劣化がないこと。

**受入条件**:
- レジストリの自動登録 (`_auto_register`) はインポート時に 1 回のみ実行
- G2p (英語)、pyopenjtalk (日本語) のインスタンスはモジュールレベルでキャッシュ
- `phonemize_from_pinyin_syllables()` (中国語コーパス高速パス) が利用可能
- JA 100 文字テキストの `phonemize_with_prosody()` が 10ms 以内
- EN 100 文字テキストの `phonemize_with_prosody()` が 5ms 以内

---

## 3. Rust crate (`piper-g2p`) 機能要求

> 技術調査レポート (`g2p-technical-investigation.md` セクション 3) の結果を反映。
> 断ち切る依存は `PhonemeIdMap` と `PiperError` の 2 点のみ。
> `phoneme_converter` は 2 分割: `tokens_to_ids()` は piper-g2p、`build_synthesis_request()` は piper-core に残す。
> PUA エントリは全プラットフォーム 87 で一致済み (差分調査タスク不要)。

### FR-R-001: コア型とエラー型の定義

**説明**: `piper-core` への依存を断ち切るため、G2P 固有の型とエラー型を `piper-g2p` crate 内に定義する。現在 `piper-core` が提供する `PhonemeIdMap` (型エイリアス) と `PiperError` (エラー enum) のうち、G2P に関連するサブセットのみを `piper-g2p` で再定義する。

**受入条件**:
- `piper-g2p` crate 内に以下が定義されている:
  ```rust
  pub type PhonemeIdMap = HashMap<String, Vec<i64>>;

  #[derive(thiserror::Error, Debug)]
  pub enum G2pError {
      #[error("unsupported language: {code}")]
      UnsupportedLanguage { code: String },
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
  ```
- `piper-core` 側に `impl From<G2pError> for PiperError` が実装されている
- `piper-g2p` は `piper-core` の型に一切依存しない

---

### FR-R-002: Phonemizer trait と関連データ型

**説明**: 現在の `Phonemizer` trait、`ProsodyInfo`、`ProsodyFeature`、`PhonemizerRegistry` を `piper-g2p` の公開 API として提供する。エラー型を `G2pError` に差し替える以外、シグネチャは現行のまま維持する。

**現在の API** (`src/rust/piper-core/src/phonemize/mod.rs`):
```rust
#[derive(Debug, Clone, Copy)]
pub struct ProsodyInfo { pub a1: i32, pub a2: i32, pub a3: i32 }

pub type ProsodyFeature = [i32; 3];

pub trait Phonemizer: Send + Sync {
    fn phonemize_with_prosody(&self, text: &str)
        -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), G2pError>;
    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap>;
    fn post_process_ids(&self, ids: Vec<i64>, prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);
    fn language_code(&self) -> &str;
    fn detect_primary_language(&self, _text: &str) -> &str { self.language_code() }
}

pub struct PhonemizerRegistry { /* ... */ }
impl PhonemizerRegistry {
    pub fn new() -> Self;
    pub fn register(&mut self, lang_code: &str, phonemizer: Box<dyn Phonemizer>);
    pub fn get(&self, lang_code: &str) -> Option<&dyn Phonemizer>;
    pub fn available_languages(&self) -> Vec<&str>;
}
impl Default for PhonemizerRegistry { /* ... */ }
```

**受入条件**:
- `use piper_g2p::{Phonemizer, ProsodyInfo, ProsodyFeature, PhonemeIdMap, PhonemizerRegistry}` でインポートできる
- `Phonemizer` trait は `Send + Sync` を要求する (マルチスレッド安全)
- `PhonemizerRegistry` に `Default` trait が実装されている (空のレジストリ)
- `PiperError` への依存箇所は全て `G2pError` に置き換えられている

---

### FR-R-003: 7 言語 Phonemizer

**説明**: 現行の 7 言語 Phonemizer を全て `piper-g2p` crate に移動する。日本語のみ feature flag で条件付きコンパイル、他 6 言語は Pure Rust でデフォルト有効。

| 言語 | 構造体 | feature flag | 外部依存 | コンストラクタ |
|------|--------|-------------|---------|--------------|
| JA | `JapanesePhonemizer` | `japanese` | `jpreprocess 0.9` (MIT) | `new()`, `new_bundled()`, `new_with_dict(&Path)` |
| EN | `EnglishPhonemizer` | (不要) | なし (CMU 辞書 JSON 組み込み) | `new()`, `new_with_dict(&Path)`, `new_with_hashmap(HashMap)` |
| ZH | `ChinesePhonemizer` | (不要) | なし | `new()` |
| KO | `KoreanPhonemizer` | (不要) | なし | `new()` |
| ES | `SpanishPhonemizer` | (不要) | なし | `new()` |
| FR | `FrenchPhonemizer` | (不要) | なし | `new()` |
| PT | `PortuguesePhonemizer` | (不要) | なし | `new()` |

**受入条件**:
- 全 Phonemizer が `Phonemizer` trait を実装し、エラー型は `G2pError`
- JA: `#[cfg(feature = "japanese")]` で条件付きコンパイル。栗原法韻律マーカー (`^`, `$`, `?`, `?!`, `?.`, `?~`, `_`, `#`, `[`, `]`)、文脈依存 N 音素変異 (`N_m`, `N_n`, `N_ng`, `N_uvular`)、PUA マッピングが動作する
- EN: ARPAbet-to-IPA 変換、機能語ストレス除去 (97 語)、OOV 形態素フォールバック (-ing, -ed, -s, -er, -ly, -est) が動作する
- ZH: 声調サンドヒ (3 声、一/不) が正しく適用される
- `post_process_ids()`: JA は no-op (BOS/EOS をインラインで処理)、他 6 言語は `default_post_process_ids()` に委譲

---

### FR-R-004: MultilingualPhonemizer と言語検出

**説明**: Unicode 言語検出 (`UnicodeLanguageDetector`) + セグメント分割 (`segment_text()`) + 言語別 Phonemizer 委譲の多言語メタ Phonemizer。Python/C# 実装と同一ロジック。

**現在の API** (`src/rust/piper-core/src/phonemize/multilingual.rs`):
```rust
pub struct UnicodeLanguageDetector { /* ... */ }
impl UnicodeLanguageDetector {
    pub fn new(languages: &[String], default_latin_language: &str) -> Self;
    pub fn detect_char(&self, ch: char, context_has_kana: bool) -> Option<&str>;
    pub fn has_kana(&self, text: &str) -> bool;
}

pub fn segment_text(text: &str, detector: &UnicodeLanguageDetector) -> Vec<(String, String)>;

pub struct MultilingualPhonemizer { /* ... */ }
impl MultilingualPhonemizer {
    pub fn new(languages: Vec<String>, default_latin_language: String,
        phonemizers: HashMap<String, Box<dyn Phonemizer>>) -> Self;
}

pub fn default_post_process_ids(ids: Vec<i64>, prosody: Vec<Option<ProsodyFeature>>,
    id_map: &PhonemeIdMap, eos_token: &str) -> (Vec<i64>, Vec<Option<ProsodyFeature>>);
```

**受入条件**:
- CJK 曖昧性解消 (仮名コンテキストで漢字を JA 判定) が Python 実装と同一の結果を返す
- `default_post_process_ids()` が EN/ZH/KO/ES/PT/FR で共通利用される
- 動的 EOS トークン追跡 (`last_eos: Mutex<String>`) がスレッドセーフに動作する
- `segment_text()` が公開関数として利用可能

---

### FR-R-005: カスタム辞書

**説明**: JSON v1.0/v2.0 形式のカスタム辞書ロード・テキスト前処理。Python 実装と同一のマッチングロジック。

**現在の API** (`src/rust/piper-core/src/phonemize/custom_dict.rs`):
```rust
pub struct DictEntry { pub pronunciation: String, pub priority: i32 }

pub struct CustomDictionary { /* ... */ }
impl CustomDictionary {
    pub fn new() -> Self;
    pub fn load_dictionary(&mut self, path: &Path) -> Result<(), G2pError>;
    pub fn apply_to_text(&self, text: &str) -> String;
    pub fn add_word(&mut self, word: &str, pronunciation: &str, priority: i32);
}
```

**受入条件**:
- `use piper_g2p::custom_dict::{CustomDictionary, DictEntry}`
- JSON v1.0/v2.0 のデシリアライズが動作する
- case-sensitive (大文字小文字混在キー) / case-insensitive (全大文字・全小文字キー) マッチが正しく動作する
- `//` で始まるキーがコメントとしてスキップされる
- longest-match-first の適用順序が保証されている
- `pattern_cache: Mutex<HashMap<String, Regex>>` による `Send + Sync` 安全な interior mutability

---

### FR-R-006: PUA トークンマップと phoneme_converter (tokens_to_ids)

**説明**: (1) 固定 PUA マッピングテーブル (87 エントリ) と (2) `phoneme_converter` の G2P 部分 (`tokens_to_ids()`, `prosody_to_features()`) を `piper-g2p` に含める。推論パイプライン部分 (`build_synthesis_request()`) は `piper-core` に残す。

**現在の API**:
```rust
// token_map.rs
pub static FIXED_PUA_MAP: LazyLock<Vec<(&'static str, u32)>>;   // 87 エントリ
pub static TOKEN_TO_PUA: LazyLock<HashMap<&'static str, char>>;
pub static PUA_TO_TOKEN: LazyLock<HashMap<char, &'static str>>;
pub fn token_to_pua(token: &str) -> Option<char>;

// phoneme_converter.rs (piper-g2p に移動する部分)
pub fn tokens_to_ids(tokens: &[String], phoneme_id_map: &PhonemeIdMap)
    -> Result<Vec<i64>, G2pError>;
pub fn prosody_to_features(prosody: &[Option<ProsodyInfo>]) -> Vec<ProsodyFeature>;
```

**受入条件**:
- `use piper_g2p::token_map::{token_to_pua, FIXED_PUA_MAP, TOKEN_TO_PUA, PUA_TO_TOKEN}`
- `token_to_pua()` の戻り値は `Option<char>`
- Python の `FIXED_PUA_MAPPING` (87 エントリ) と全エントリが一致する
- `tokens_to_ids()` と `prosody_to_features()` が `piper-g2p` から公開される
- `build_synthesis_request()` は `piper-core` に残り、`piper-g2p` の `tokens_to_ids()` を内部で呼び出す

---

## 4. Rust crate 非機能要求

### NFR-R-001: crate 構成と公開設定

**説明**: `piper-g2p` を独立 crate として workspace に追加し、`piper-core` がこれに依存する形にする。

**受入条件**:
- `src/rust/piper-g2p/Cargo.toml` が存在し、`workspace.package` を継承する
- workspace `Cargo.toml` の `members` に `"piper-g2p"` が含まれる
- `piper-core` の `Cargo.toml` に `piper-g2p = { path = "../piper-g2p" }` が依存として記述される
- `cargo publish -p piper-g2p --dry-run` が成功する
- ライセンス: MIT (workspace 設定と同一)

---

### NFR-R-002: feature flags と依存構成

**説明**: 言語別の feature flags で外部依存を制御する。日本語以外は Pure Rust で追加 crate 不要。

**Cargo.toml 設計**:
```toml
[features]
default = ["naist-jdic", "multilingual"]
japanese = ["dep:jpreprocess"]
naist-jdic = ["japanese", "jpreprocess/naist-jdic"]
multilingual = ["english", "chinese", "spanish", "french", "portuguese", "korean"]
english = []
chinese = []
spanish = []
french = []
portuguese = []
korean = []

[dependencies]
thiserror = "2"
regex = "1"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
jpreprocess = { version = "0.9", optional = true }
```

**受入条件**:
- `default` features で全言語有効
- feature `japanese` が `dep:jpreprocess` を有効化
- feature `naist-jdic` が `japanese` + `jpreprocess/naist-jdic` を有効化 (辞書バンドル)
- 全依存が MIT / Apache-2.0 / BSD-3-Clause (GPL 汚染ゼロ)

---

### NFR-R-003: スレッド安全性とパフォーマンス

**説明**: 全ての Phonemizer 実装が `Send + Sync` を満たし、TTS パイプラインのボトルネックにならない処理速度を維持する。

**受入条件**:
- `Phonemizer` trait bound が `Send + Sync` を含む (現在の実装を維持)
- `CustomDictionary` の `pattern_cache: Mutex<HashMap<String, Regex>>` パターンで interior mutability を安全に提供
- `MultilingualPhonemizer` の `last_eos: Mutex<String>` がスレッドセーフ
- コンパイル時に全実装型が `Send + Sync` を満たすことを検証するテストを含む:
  ```rust
  fn assert_send_sync<T: Send + Sync>() {}
  #[test] fn phonemizer_is_send_sync() {
      assert_send_sync::<EnglishPhonemizer>();
      assert_send_sync::<CustomDictionary>();
  }
  ```
- JA/EN 100 文字テキストの `phonemize_with_prosody()` が 10ms 以内

---

### NFR-R-004: MSRV と piper-core 後方互換性

**説明**: workspace の MSRV と整合し、`piper-core` の既存公開 API を維持する。

**受入条件**:
- `Cargo.toml` に `rust-version = "1.88"` を記述 (workspace 設定に準拠)
- `LazyLock` (Rust 1.80+)、`OnceLock` (Rust 1.70+) の使用が MSRV と互換
- CI で MSRV でのビルド検証を実施
- `piper-core` の `src/phonemize/` モジュールが `pub use piper_g2p::*;` で re-export
- `piper-core` を利用する既存コード (`piper-cli`, `piper-python`) のコンパイルがゼロ変更で通る
- `piper-core` 側に `impl From<G2pError> for PiperError` が実装されている

---

### NFR-R-005: テストとドキュメント

**説明**: 独立 crate として十分なテストカバレッジと API ドキュメントを持つ。

**受入条件 (テスト)**:
- 各言語 Phonemizer の基本入出力テスト (最低 3 ケース/言語)
- `MultilingualPhonemizer` のコードスイッチングテスト (JA+EN+ZH 混在)
- `CustomDictionary` の JSON v1.0/v2.0 ロード + apply テスト
- PUA マッピングの Python 実装との 87 エントリ完全一致テスト
- `Send + Sync` のコンパイルタイムチェック
- `tokens_to_ids()` / `prosody_to_features()` の単体テスト
- CI で 3 OS (Linux, macOS, Windows) 実行

**受入条件 (ドキュメント)**:
- `#![deny(missing_docs)]` を `lib.rs` に設定
- 全 `pub` アイテムに doc comment が付与されている
- `cargo doc --no-deps` が warning なしで成功する
- crate レベルの doc comment にクイックスタート例を含める:
  ```rust
  //! # piper-g2p
  //!
  //! Multi-language G2P (Grapheme-to-Phoneme) library for TTS.
  //! eSpeak-ng free, MIT licensed.
  //!
  //! ## Quick Start
  //!
  //! ```rust
  //! use piper_g2p::Phonemizer;
  //! use piper_g2p::english::EnglishPhonemizer;
  //!
  //! let phonemizer = EnglishPhonemizer::new()?;
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

## 7. JS/WASM npm パッケージ (`@piper-plus/g2p`) 機能要求 -- Phase 2

> **Phase 位置づけ:** Phase 2 (旧 Phase 3)。Phase 1 (Python + Rust) 完了後に着手する。
> **推定工数:** 3-4 週
> **技術的前提:** G2P レイヤーは `onnxruntime-web` に依存しない (技術調査で確認済み)。主要作業は OpenJTalk WASM 初期化の DI 化と `SimpleUnifiedPhonemizer` の分離である。

### FR-W-001: G2P 統一 API

**説明:** 現在の `SimpleUnifiedPhonemizer` を推論パイプラインから分離し、`@piper-plus/g2p` として独立利用可能な G2P API を提供する。OpenJTalk WASM の初期化を DI パターンに変更し、`onnxruntime-web` への依存を排除する。

**現在の API** (`src/wasm/openjtalk-web/src/simple_unified_api.js`):
```javascript
class SimpleUnifiedPhonemizer {
    constructor(options = {})
    async initialize(config)                         // OpenJTalk WASM ロード + 辞書読み込み
    async textToPhonemes(text, language = null)       // -> string (JA labels) | string[] | number[]
    extractPhonemes(labels, language = 'ja')          // -> string[] | number[]
    setPhonemeIdMap(phonemeIdMap)                     // ZH/ES/FR/PT フォールバック用
    getPhonemeIdMap(language)
    detectLanguage(text)                             // -> 'ja' | 'zh' | 'en'
    dispose()
}
```

**新規 API:**
```typescript
// @piper-plus/g2p
export class G2P {
    static async create(options?: G2POptions): Promise<G2P>;

    phonemize(text: string, options?: PhonemizeOptions): PhonemizeResult;

    phonemizeWithProsody(text: string, options?: PhonemizeOptions): PhonemizeResult;

    encode(text: string, phonemeIdMap: Record<string, number[]>,
           options?: PhonemizeOptions): EncodeResult;

    detectLanguage(text: string): Language;

    segmentText(text: string): Array<{ language: Language; text: string }>;

    dispose(): void;
}

interface G2POptions {
    languages?: Language[];            // 有効にする言語 (省略時は全言語)
    openjtalkModule?: any;             // 外部注入の OpenJTalk WASM モジュール (DI)
    jaDict?: JaDictData;               // 日本語辞書データ (DictLoader から取得)
    customDicts?: CustomDictionary[];  // カスタム辞書インスタンス
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
- `G2P.create()` が非同期初期化 (WASM ロード含む) を行い `Promise<G2P>` を返す
- `phonemize()` / `phonemizeWithProsody()` は初期化後に同期的に呼び出せる
- `phonemize()` は `phonemizeWithProsody()` の prosody なし版として実装 (prosody フィールドは常に null 配列)
- `encode()` が `phonemeIdMap` を受け取り BOS(1)/PAD(0)/EOS(2) を含む最終 ID 列を返す
- `segmentText()` が混在テキストを言語セグメントに分割して返す
- `onnxruntime-web` への依存がゼロである (`peerDependencies` にも含まない)
- OpenJTalk WASM モジュールが `G2POptions.openjtalkModule` で外部注入可能である (現在の `initializeOpenJTalk()` 内部のハードコードパス解決を排除)
- 現在の `SimpleUnifiedPhonemizer` の全言語処理フローが新 API でカバーされている

---

### FR-W-002: 日本語 G2P + Prosody 抽出

**説明:** OpenJTalk WASM ベースの日本語 G2P を独立モジュールとして提供する。既存の `japanese_phoneme_extract.js` には `RE_A1`/`RE_A2`/`RE_A3` 正規表現による full-context label パースが実装済みであり、A1/A2/A3 prosody 値の抽出は小規模な拡張で実現可能 (技術調査で確認済み)。

**現在の処理フロー** (`japanese_phoneme_extract.js`):
```
text -> OpenJTalk WASM (_openjtalk_synthesis_labels)
     -> full-context labels (文字列)
     -> extractPhonemesFromLabels()
       -> sil -> ^/$ (BOS/EOS)
       -> pau -> _ (短ポーズ)
       -> A1/A2/A3 抽出 -> Kurihara 韻律マーカー: ], #, [
       -> N 変異: N_m, N_n, N_ng, N_uvular (applyNPhonemeRules)
       -> PUA マッピング (mapToPUA, PUA_MAP 24 entries)
```

**変更点:** `extractPhonemesFromLabels()` の戻り値を `{ tokens: string[], prosody: (ProsodyInfo | null)[] }` に拡張する。A1/A2/A3 値は既に各行からパースしており (`parseInt(mA1[1])` 等)、韻律マーカー挿入の判定にのみ使用されている。これを `ProsodyInfo` オブジェクトとしても返す。

**受入条件:**
- OpenJTalk WASM の初期化が `G2P.create({ languages: ['ja'], jaDict })` で行える
- 辞書データは `DictLoader` 経由の `JaDictData` として外部注入する
- `extractPhonemesFromLabels()`, `applyNPhonemeRules()`, `mapToPUA()` が独立エクスポートされている
- `phonemizeWithProsody()` が JA テキストに対して `ProsodyInfo` (a1/a2/a3) を返す
- 韻律マーカー (Kurihara `]`, `#`, `[`)・N 変異 (`N_m`/`N_n`/`N_ng`/`N_uvular`)・PUA マッピング (24 エントリ) が Python 実装と一致する
- prosody が不要な位置 (BOS/EOS/ポーズ/韻律マーカー) は `null` で表現される

---

### FR-W-003: 辞書ローダー (DictLoader)

**説明:** 現在の `DictManager` から辞書ダウンロード + IndexedDB キャッシュ機能を G2P パッケージ向けに分離する。G2P 単体利用時は HTS voice ファイルのダウンロードが不要なため、デフォルトで辞書のみをロードする。

**現在の API** (`src/wasm/openjtalk-web/src/dict-manager.js`):
```javascript
class DictManager {
    constructor(options = {})               // { cachePrefix: 'piper-plus-dict' }
    async loadDictionary(options = {})      // -> { dictFiles, voiceData }
    async isCached()                        // -> boolean
    async clearCache()                      // -> void
    resolveUrls(options = {})               // -> { dictUrl, voiceUrl }
}
```

**新規 API:**
```typescript
export class DictLoader {
    constructor(options?: { cachePrefix?: string });

    async loadJaDict(options?: {
        dictUrl?: string;
        includeVoice?: boolean;         // default: false (G2P のみなら不要)
        voiceUrl?: string;
        onProgress?: (info: { loaded: number; total: number }) => void;
    }): Promise<JaDictData>;

    async isCached(): Promise<boolean>;
    async clearCache(): Promise<void>;
}

interface JaDictData {
    dictFiles: Record<string, ArrayBuffer>;   // 8 辞書ファイル
    voiceData?: ArrayBuffer;                   // includeVoice=true 時のみ
}
```

**受入条件:**
- GitHub Releases から tar.gz をダウンロードし SHA-256 を検証する
- IndexedDB キャッシュにより 2 回目以降は即座にロードされる
- `dictUrl` で独自の辞書 URL を指定できる
- G2P 単体利用時は `includeVoice: false` がデフォルト
- 進捗コールバックが byte レベルで報告される
- 8 辞書ファイル (`char.bin`, `matrix.bin`, `sys.dic`, `unk.dic`, `left-id.def`, `pos-id.def`, `rewrite.def`, `right-id.def`) がすべて検証される

---

### FR-W-004: 言語自動検出・テキスト分割

**説明:** Unicode 文字範囲に基づく言語検出とテキスト分割を提供する。現在の `detectLanguage()` を拡張し、FR-G-003 (共通要求) の仕様に準拠させる。

**現在の実装** (`simple_unified_api.js`):
```javascript
detectLanguage(text) {
    let hasKana = false, hasCJK = false;
    for (const char of text) {
        const code = char.charCodeAt(0);
        if ((code >= 0x3040 && code <= 0x309F) ||
            (code >= 0x30A0 && code <= 0x30FF)) {
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
- Hiragana/Katakana -> JA、CJK Ideographs (仮名なしコンテキスト) -> ZH、Latin -> デフォルト言語 (EN)
- CJK + 仮名混在テキストで JA が優先される
- 全角ラテン文字 (U+FF21-FF5A) が Latin として扱われる (Python/C#/Rust 実装と同等)
- `segmentText()` が混在テキストを `[{ language, text }]` に分割する
- ES/FR/PT の文字レベル区別は不可能なことを API ドキュメントに明記する
- Hangul (U+AC00-D7AF) -> KO として将来対応用の予約をする

---

### FR-W-005: カスタム辞書・英語 G2P・フォールバック G2P

**説明:** 現在の `CustomDictionary`、`SimpleEnglishPhonemizer`、ZH/ES/FR/PT キャラクタベースフォールバックをそのまま `@piper-plus/g2p` に含める。

**受入条件 -- カスタム辞書:**
- 現在の `CustomDictionary` クラスの API を維持する
- JSON v1.0 / v2.0 形式の辞書ファイルをロードできる
- 優先度ベースの競合解決・大文字小文字混在キーの case-sensitive マッチ・longest-match-first の適用順序が保証されている
- `processText()` が正規表現キャッシュを使用してパフォーマンスを維持する

**受入条件 -- 英語 G2P:**
- 現在の辞書ベース方式 (~70 語 + 26 文字 letter-to-phoneme ルール) を維持する
- CMU Pronouncing Dictionary サブセット (上位 5,000 語) をオプションバンドルとして将来提供可能な設計にする
- バンドルサイズ: CMU 辞書なし < 10KB gzip

**受入条件 -- フォールバック G2P (ZH/ES/FR/PT):**
- `phonemize()` がキャラクタ単位のトークン列を返す
- `encode()` が `phonemeIdMap` を受け取り BOS(1)/PAD(0)/EOS(2) を含む phoneme ID 列を返す
- 未知文字はスキップされる (現状と同一動作)
- 将来的に pypinyin WASM / 規則ベース G2P へアップグレード可能な設計 (関数差し替え可能な構造)

---

## 8. JS/WASM npm パッケージ 非機能要求 -- Phase 2

### NFR-W-001: バンドルサイズ・パッケージ構成

**説明:** G2P パッケージ単体のサイズを最小化し、tree-shaking で未使用言語を除外可能にする。

| コンポーネント | サイズ上限 (gzip) |
|---------------|-----------------|
| JS コード (全言語) | < 30KB |
| OpenJTalk WASM | < 400KB |
| 辞書 (tar.gz, 実行時 DL) | ~5MB (既存同一) |
| 合計 (JA なし) | < 30KB |
| 合計 (JA 込み、辞書除く) | < 430KB |

**パッケージ構成:**
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
      phoneme-extract.js  # full-context label パーサー + prosody 抽出
    en/
      index.js            # EnglishG2P (辞書ベース)
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
- JA 言語なしの場合 WASM ファイルが含まれない
- `@piper-plus/g2p` のインストールサイズが 1MB 未満 (WASM 込み、辞書除く)
- 辞書は実行時 `DictLoader` 経由でダウンロード (パッケージに含まない)
- `peerDependencies` に `onnxruntime-web` を含めない
- `engines.node` >= `18.0.0`
- npm publish 時に `dist/`, `src/`, `types/` のみが含まれる (`files` フィールドで制御)

---

### NFR-W-002: ブラウザ互換性・ランタイム

**説明:** 主要モダンブラウザおよび Node.js で動作すること。

**受入条件:**
- Chrome 80+, Firefox 113+, Safari 16.4+ で動作する
- Node.js 18+ でも動作する (WASM 含む)
- `DecompressionStream` API が利用可能 (辞書 tar.gz 解凍)
- `crypto.subtle` が利用可能 (SHA-256 検証、HTTPS 環境)
- `indexedDB` が利用可能 (辞書キャッシュ)

---

### NFR-W-003: 既存 piper-plus パッケージとの互換性

**説明:** 既存の `piper-plus` npm パッケージが `@piper-plus/g2p` を内部依存として利用でき、公開 API に破壊的変更がないこと。

**受入条件:**
- `piper-plus` の `package.json` に `"@piper-plus/g2p": "^1.0.0"` が dependencies として追加される
- `piper-plus` の `SimpleUnifiedPhonemizer` が内部で `@piper-plus/g2p` の `G2P` クラスに委譲する
- 既存の `piper-plus` ユーザー API (`PiperPlus.initialize()`, `PiperPlus.synthesize()`) に破壊的変更がない
- 既存 subpath export `piper-plus/phonemizer` が `@piper-plus/g2p` への re-export として維持される

---

### NFR-W-004: TypeScript 型定義・テスト

**説明:** 完全な TypeScript 型定義を提供し、十分なテストカバレッジを確保する。

**受入条件 -- 型定義:**
- `types/index.d.ts` がすべての公開 API をカバーしている
- `G2P`, `DictLoader`, `CustomDictionary` クラスの型定義
- `PhonemizeResult`, `EncodeResult`, `ProsodyInfo`, `Language`, `G2POptions`, `PhonemizeOptions`, `JaDictData` 型のエクスポート
- subpath export (`@piper-plus/g2p/ja` 等) の型定義提供
- `tsc --noEmit` でエラーなし

**受入条件 -- テスト:**
- Node.js test runner (`node --test`) でテスト実行可能
- JA G2P: full-context label パーサー (Kurihara 韻律マーカー、N 変異、PUA マッピング、prosody 抽出)
- EN G2P: 辞書ベース + letter-to-phoneme ルールフォールバック
- 言語検出: CJK 曖昧性解消、全角ラテン文字処理、`segmentText()` の混在テキスト分割
- `encode()`: BOS/PAD/EOS 挿入の正確性
- カスタム辞書: JSON v1.0/v2.0 ロード + テキスト変換 + 優先度競合解決
- Python 実装との JA phoneme 出力一致検証 (共通テストフィクスチャ JSON 参照)
- CI: `g2p-wasm-ci.yml` で 3 OS x Node 18/20/22 マトリクス実行

---

## 9. 共通機能要求 (FR-G)

> 対象: Python (`piper-g2p`), Rust (`piper-g2p`), JS/WASM (`@piper-plus/g2p`) の 3 プラットフォーム。C# は DotNetG2P (NuGet) が既に独立 G2P パッケージとして公開済みのため対象外。
>
> 技術調査 (g2p-technical-investigation.md) で判明した事項を反映済み:
> - PUA マッピングは全プラットフォーム 87 エントリで一致確認済み (差分調査タスク不要)
> - インライン音素記法 `[[ ... ]]` は Phase 2 以降
> - TTS 統合ガイドは Phase 1 v1.0.0 リリース後

### FR-G-001: 統一 Phonemizer インターフェース

**タイトル:** 全プラットフォームで概念的に同一の Phonemizer インターフェースを提供する

**説明:**
各プラットフォームの言語慣習に従いつつ、以下の 4 つの操作を全パッケージで公開する。`phonemize()` は `phonemize_with_prosody()` の prosody 除去版として実装し、DRY を保つ。

| 操作 | Python | Rust | JS/WASM |
|------|--------|------|---------|
| 音素化 | `phonemize(text) -> list[str]` | `phonemize(text) -> Result<Vec<String>>` | `phonemize(text) -> PhonemizeResult` |
| 音素化+韻律 | `phonemize_with_prosody(text) -> (list[str], list[ProsodyInfo\|None])` | `phonemize_with_prosody(text) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>)>` | `phonemize(text) -> PhonemizeResult` (prosody フィールド含む) |
| ID マップ取得 | `get_phoneme_id_map() -> dict\|None` | `get_phoneme_id_map() -> Option<&PhonemeIdMap>` | `getPhonemeIdMap(language) -> Record<string, number[]>` |
| 後処理 | `post_process_ids(ids, prosody, map) -> (ids, prosody)` | `post_process_ids(ids, prosody, map) -> (ids, prosody)` | `encode(text, map) -> EncodeResult` (内包) |

**受入条件:**
1. 各パッケージが上記 4 操作に相当する API を公開している
2. `phonemize()` は `phonemize_with_prosody()` の prosody 捨て版として実装される
3. API リファレンスにプラットフォーム間の対応表が記載されている
4. `ProsodyInfo` は 3 フィールド (a1, a2, a3) の整数構造体として全プラットフォームで定義されている

---

### FR-G-002: 言語レジストリと自動検出

**タイトル:** 言語コードからの Phonemizer 解決と Unicode ベースの言語自動検出を提供する

**説明:**
単一言語コード (例: `"ja"`) と複合言語コード (例: `"ja-en-zh"`) の両方を受け付け、適切な Phonemizer を返す。複合コードの場合は `MultilingualPhonemizer` を自動生成・キャッシュする。テキスト入力時は `UnicodeLanguageDetector` で言語を自動検出し、セグメント分割を行う。

**言語自動検出ルール:**

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
1. `get_phonemizer("ja")` 相当の API が全プラットフォームで利用可能
2. `get_phonemizer("ja-en-zh")` 相当で `MultilingualPhonemizer` が自動生成される
3. 言語コードの正規化 (`"en-ja"` == `"ja-en"` ソート済み) が全プラットフォームで統一
4. `available_languages()` 相当で登録済み言語の一覧を取得可能
5. 上記ルール表をパスする共通テストスイートが存在する
6. `segment_text("こんにちはHello你好")` が `[("ja", "こんにちは"), ("en", "Hello"), ("zh", "你好")]` を返す
7. CJK 曖昧性解消: 仮名を含むテキスト内の漢字は ja に分類される
8. 全中立文字のみの場合は default_latin にフォールバック

---

### FR-G-003: PUA マッピングテーブル

**タイトル:** 多文字音素トークンから単一 Unicode コードポイントへの固定マッピングを全プラットフォームで共有する

**説明:**
技術調査により、現在の HEAD では Python / Rust とも **87 エントリで完全一致** していることが確認済み。学習済みモデルの重みに直接依存するため、コードポイントの変更は不可。

テーブル構成 (87 エントリ):
- JA: U+E000-E01C (29 エントリ) -- 長母音, 促音, 口蓋化子音, 疑問詞マーカー, N 変異
- 共有: U+E01D-E01E (2 エントリ) -- `rr` (ES), `y_vowel` (ZH/FR)
- ZH: U+E020-E04A (43 エントリ) -- 有気音, 二重母音, 鼻韻, 声調マーカー
- KO: U+E04B-E052 (8 エントリ) -- 硬音, 内破音
- ES/PT: U+E054-E055 (2 エントリ) -- 破擦音
- FR: U+E056-E058 (3 エントリ) -- 鼻母音

**受入条件:**
1. 全 3 パッケージ (Python / Rust / JS) のマッピングテーブルが 87 エントリ完全一致する
2. CI でテーブル整合性を検証するクロスプラットフォームテストが実行される
3. PUA テーブルは各パッケージ内に静的定義として含まれ、外部ファイル依存なし
4. 言語追加時に全プラットフォーム同期を CI で保証する仕組みが存在する
5. 動的 PUA 割り当て (U+E059~) はパッケージ外部 (学習パイプライン) の機能として分離

---

### FR-G-004: 音素体系の互換性

**タイトル:** 同一テキスト入力から Python / Rust で同一の phoneme_ids シーケンスを生成する

**説明:**
独立パッケージ化の最重要要件。phonemize -> token mapping -> ID 変換 -> post_process_ids のパイプライン全体を通じて、同一入力に対して同一出力を保証する。

```
テキスト -> phonemize_with_prosody() -> [tokens, prosody]
         -> token_to_id (PUA + phoneme_id_map) -> [phoneme_ids, prosody_features]
         -> post_process_ids() -> [final_ids, final_prosody]  (BOS/PAD/EOS 挿入)
```

**受入条件:**
1. 以下の参照テストケースが Python / Rust で同一結果を生成する:
   - JA: `"こんにちは"` -> phoneme_ids (参照値を JSON で定義)
   - EN: `"Hello world"` -> phoneme_ids
   - ZH: `"你好"` -> phoneme_ids
   - 混在: `"こんにちはHello你好"` -> phoneme_ids
2. 参照テストケースは共通 JSON ファイルとして各パッケージの test fixtures に含まれる
3. **JS/WASM の例外**: JA のみ OpenJTalk WASM で完全一致を要求。EN/ZH/ES/FR/PT はキャラクタベースのため phoneme_ids は他プラットフォームと異なりうる。テストに `"wasm_skip": true` フラグで分離

---

### FR-G-005: カスタム辞書

**タイトル:** JSON v1.0/v2.0 形式のカスタム辞書を全プラットフォームで共通仕様とする

**説明:**
カスタム辞書はテキスト前処理段階で単語を読みに置換する機能。

**JSON v1.0:**
```json
{ "version": "1.0", "entries": { "API": "エーピーアイ" } }
```

**JSON v2.0:**
```json
{
  "version": "2.0",
  "entries": {
    "API": { "pronunciation": "エーピーアイ", "priority": 8 }
  }
}
```

**共通仕様:**
- `//` で始まるキーはコメントとしてスキップ
- 優先度: 0-10 の整数、デフォルト 5、高い方が勝つ
- 大文字小文字混在キー (例: `"GitHub"`) は case-sensitive マッチ
- 全大文字/全小文字キーは case-insensitive マッチ (lowercase 正規化)
- 非 ASCII キー (日本語等) は単純部分文字列マッチ、ASCII キーは単語境界マッチ
- 適用順: longest-match-first

**受入条件:**
1. 同一辞書ファイルを全プラットフォームに渡した場合、同一テキストに対して同一の置換結果を返す
2. v1.0/v2.0 の両フォーマットが全プラットフォームで読み込み可能
3. case-sensitive / case-insensitive の振り分けロジックが全プラットフォームで統一
4. 優先度による上書きルールが全プラットフォームで統一
5. Python: `CustomDictionary` のデフォルト辞書パスは `piper_g2p` パッケージ内の `data/dictionaries/` にバンドル。`CustomDictionary(load_defaults=False)` でスキップ可能

---

### FR-G-006: 多言語音素化と言語別 Phonemizer

**タイトル:** 7 言語の Phonemizer を個別/多言語統合で利用可能にする

**説明:**
各言語の Phonemizer は個別にインスタンス化して使用可能。依存ライブラリは言語ごとにオプショナル。`MultilingualPhonemizer` は N 言語の任意の組み合わせでコードスイッチングテキストを処理する。

**言語別依存:**

| 言語 | Python 依存 | Rust feature | JS/WASM |
|------|------------|-------------|---------|
| JA | pyopenjtalk-plus (BSD-3) | `japanese` (jpreprocess, MIT) | OpenJTalk WASM (BSD-3) |
| EN | g2p-en (Apache-2.0) | (ルールベース) | SimpleEnglishPhonemizer (辞書ベース) |
| ZH | pypinyin (MIT) | (ルールベース) | キャラクタベース |
| KO | g2pk2 (Apache-2.0) | (ルールベース) | (未実装) |
| ES/FR/PT | (ルールベース) | (ルールベース) | キャラクタベース |

**MultilingualPhonemizer の処理フロー:**
1. `UnicodeLanguageDetector` でテキストを言語セグメントに分割
2. 各セグメントを対応する言語 Phonemizer に委譲
3. 各セグメントの BOS/EOS を除去し、結果を連結
4. 最後に見た EOS トークン (疑問詞マーカー `?!`, `?.`, `?~` を含む) を記録
5. `post_process_ids()` で統一的な BOS + PAD + ... + EOS を付与

**受入条件:**
1. `piper-g2p[ja]` (Python) / `piper-g2p = { features = ["japanese"] }` (Rust) のように言語別のオプショナル依存で導入可能
2. 依存が未インストールの言語は明確なエラーメッセージで失敗する
3. 混在テキストの分割・再結合が Python / Rust で同一結果を生成する
4. EOS トークンの追跡 (疑問詞マーカー含む) が正しく動作する
5. 統一 phoneme_id_map の生成 (`get_multilingual_id_map()`) がパッケージ内に含まれる
6. Python の `MultilingualPhonemizer` はスレッド非安全な `_last_eos` を持つことを API ドキュメントに明記する

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

**受入条件:**
1. ProsodyInfo は全プラットフォームで 3 フィールド (a1, a2, a3) の整数タプルとして定義
2. `phonemize_with_prosody()` が返す prosody リストは tokens リストと同長
3. prosody が不要な位置 (句読点, 特殊トークン) は null/None/Option::None で表現
4. JS/WASM では Phase 2 で `phonemize_with_prosody()` を追加し、OpenJTalk WASM の full-context label から A1/A2/A3 を抽出する (既存の `RE_A1`/`RE_A2`/`RE_A3` 正規表現で実現可能)
5. ONNX 入力用のフラット化 (`[a1_0, a2_0, a3_0, a1_1, ...]`) はパッケージ外部 (推論パイプライン側) の責務

---

## 10. 共通非機能要求 (NFR-G)

### NFR-G-001: ライセンスクリーンとゼロ C/C++ ビルド依存

**タイトル:** 全依存が MIT / Apache-2.0 / BSD-3-Clause、かつ C/C++ コンパイラなしでインストール可能

**説明:**
GPL 汚染ゼロが本パッケージの最大の差別化ポイント。eSpeak-ng (GPL-3.0) への依存は一切持たない。また、eSpeak-ng / pyopenjtalk の C++ ビルド失敗は最頻出 Issue であり、ビルド依存の排除も重要。

**受入条件:**
1. 各パッケージの依存ツリーに GPL ライセンスの依存が存在しない
2. CI でライセンスチェックを実行する: `cargo deny check licenses` (Rust), `uv run pip-licenses` (Python)
3. パッケージの LICENSE ファイルが MIT で提供される
4. Python: `uv pip install piper-g2p` が C コンパイラなしで完了する (JA の `pyopenjtalk-plus` は wheel に依存。wheel 未提供環境ではエラーメッセージでビルド要件を案内)
5. Rust: `cargo build` に C/C++ ツールチェーンが不要
6. JS/WASM: OpenJTalk はプリコンパイル済み WASM バイナリとして配布

---

### NFR-G-002: テスト網羅と互換性検証

**タイトル:** 80% 以上のコードカバレッジ、共通テストフィクスチャによるクロスプラットフォーム検証

**説明:**
各パッケージが独立したテストスイートを持ち、加えて共通テストフィクスチャ (JSON) によるクロスプラットフォーム互換性テストを実施する。

**テストフィクスチャ JSON スキーマ:**
```json
{
  "version": "1.0",
  "test_cases": [
    {
      "id": "ja_001",
      "language": "ja",
      "input_text": "こんにちは",
      "expected_phonemes": ["^", "k", "o", "N_n", "n", "i", "ch", "i", "h", "a", "$"],
      "expected_prosody": [null, {"a1":0,"a2":1,"a3":5}, "..."],
      "wasm_skip": false,
      "note": "N_n before n (alveolar)"
    }
  ]
}
```

**テストケース一覧 (6 言語 + 混在):**

| ID | 言語 | 入力 | 検証ポイント |
|----|------|------|------------|
| ja_001 | JA | こんにちは | N_n (歯茎音前) |
| ja_002 | JA | 何ですか？ | 疑問詞マーカー |
| ja_003 | JA | さんぽ | N_m (両唇音前) |
| en_001 | EN | Hello world | ストレス + 語境界 |
| en_002 | EN | the cat | 機能語ストレス除去 |
| zh_001 | ZH | 你好 | 声調サンドヒ (T3+T3) |
| zh_002 | ZH | 中国 | 複数音節 |
| es_001 | ES | Hola mundo | 語境界 |
| fr_001 | FR | Bonjour | 鼻母音 |
| pt_001 | PT | Ola mundo | 強勢母音 |
| multi_001 | JA+EN | こんにちはHello | BOS/EOS 除去・連結 |
| multi_002 | JA | 漢字を | CJK 曖昧性解消 (仮名あり -> JA) |
| multi_003 | JA+EN+ZH | こんにちはHello你好 | 3 言語混在 |

**受入条件:**
1. 各パッケージで 80% 以上の行カバレッジ
2. 共通テストフィクスチャ `tests/fixtures/g2p/phoneme_test_cases.json` が上記テストケースを含む
3. 各プラットフォームの CI がこのフィクスチャに対してパスする
4. PUA マッピングの全 87 エントリ一致検証テストが含まれる
5. `MultilingualPhonemizer` のコードスイッチングテスト、`CustomDictionary` の JSON v1.0/v2.0 ロードテストが含まれる

---

### NFR-G-003: パフォーマンス

**タイトル:** 一般的なテキスト (100 文字程度) の音素化が 10ms 以内

**説明:**
TTS パイプラインのボトルネックにならない処理速度を確保する。

**受入条件:**
1. JA 100 文字テキストの `phonemize_with_prosody()` が 10ms 以内 (Python / Rust)
2. EN 100 文字テキストの `phonemize_with_prosody()` が 5ms 以内 (Python / Rust)
3. Python: レジストリの `_auto_register()` はインポート時に 1 回のみ実行。g2p-en / jpreprocess インスタンスはモジュールレベルでキャッシュ
4. 各パッケージにベンチマークスクリプト/テストが含まれる

---

### NFR-G-004: API ドキュメント

**タイトル:** 全パッケージに言語慣習に沿った API ドキュメントを提供する

**受入条件:**
1. Python: docstring (Google スタイル)。クイックスタート例を含む
2. Rust: `#![deny(missing_docs)]` を `lib.rs` に設定。全 `pub` アイテムに doc comment。`cargo doc --no-deps` が warning なしで成功。クイックスタート例を含む
3. JS/WASM: JSDoc + TypeScript 型定義 (`index.d.ts`)。全公開 API の型カバレッジ

---

## 11. 統合・マイグレーション要求 (FR-I)

### FR-I-001: Python import パス互換性

**タイトル:** 既存 `piper_train.phonemize` からの段階的マイグレーションパスを提供する

**Phase 割り当て:** Phase 1

**説明:**
既存ユーザーが `from piper_train.phonemize import ...` を使用している。新パッケージは `from piper_g2p import ...` を正式パスとして提供しつつ、`piper_train.phonemize` を `DeprecationWarning` 付き re-export シムとして維持する。技術調査により、phonemize ディレクトリは piper_train の他モジュールへの依存がゼロであることが確認済み。

**互換シム実装:**
```python
# piper_train/phonemize/__init__.py (移行後)
import warnings
warnings.warn(
    "piper_train.phonemize is deprecated. Use piper_g2p instead.",
    DeprecationWarning, stacklevel=2,
)
from piper_g2p import *  # re-export
```

**piper_train 側で互換シムが必要なファイル (6 ファイル):**
- `preprocess.py`, `update_model_config.py`, `vits/lightning.py`
- `tools/prepare_bilingual_dataset.py`, `tools/prepare_multilingual_dataset.py`, `tools/add_prosody_features.py`

**受入条件:**
1. `from piper_g2p import get_phonemizer, Phonemizer, ProsodyInfo` が動作する
2. `from piper_g2p.japanese import JapanesePhonemizer` が動作する
3. `from piper_train.phonemize import get_phonemizer` が `piper_g2p` に委譲される (`DeprecationWarning` 付き)
4. `piper_train` の `pyproject.toml` に `piper-g2p` が依存として追加される
5. 互換シムは少なくとも 2 マイナーバージョン (6 か月以上) 維持される
6. 既存の piper_train テストが変更なしでパスする

---

### FR-I-002: Rust crate 分離

**タイトル:** `piper-core` から `piper-g2p` crate を分離し、`piper-core` が依存として使用する

**Phase 割り当て:** Phase 1

**説明:**
現在の `piper-core/src/phonemize/` (12 ファイル) を新 crate `piper-g2p` に移動する。技術調査により、断ち切りが必要な依存は `PhonemeIdMap` 型、`PiperError` 型、`SynthesisRequest` (phoneme_converter 内) の 3 点に限定されることが判明済み。

**依存断ち切り:**

| 依存 | 解決方針 |
|------|---------|
| `crate::config::PhonemeIdMap` | `piper-g2p` 内で `pub type PhonemeIdMap = HashMap<String, Vec<i64>>` を再定義 |
| `crate::error::PiperError` | `piper-g2p` 内で `G2pError` を新規定義。`From<G2pError> for PiperError` で変換 |
| `crate::engine::SynthesisRequest` | `phoneme_converter.rs` を 2 分割: `tokens_to_ids()` は piper-g2p、`build_synthesis_request()` は piper-core に残す |

**受入条件:**
1. `piper-g2p` crate が `piper-core` から独立してコンパイル可能
2. `piper-core` の `phonemize` モジュールが `pub use piper_g2p::*;` で re-export
3. `piper-g2p` は `PiperError` に依存せず、独自の `G2pError` を定義する
4. workspace `Cargo.toml` の `members` に `"piper-g2p"` が含まれる
5. 既存の `piper-core` / `piper-cli` / `piper-python` のコンパイルが通る (ユーザーコード変更ゼロ)
6. `cargo publish -p piper-g2p --dry-run` が成功する

---

### FR-I-003: JS/WASM パッケージ分離

**タイトル:** `piper-plus` npm パッケージから G2P レイヤーを `@piper-plus/g2p` として分離する

**Phase 割り当て:** Phase 2

**説明:**
`SimpleUnifiedPhonemizer` クラスを独立パッケージに切り出す。技術調査により、G2P レイヤー自体は `onnxruntime-web` に依存していないことが確認済み。OpenJTalk WASM の初期化を DI パターンに変更する。

**受入条件:**
1. `@piper-plus/g2p` が `piper-plus` なしでインストール・使用可能
2. OpenJTalk WASM モジュールはコンストラクタへの注入で提供 (ハードコード依存の排除)
3. `DictManager` の辞書ダウンロード機能は `@piper-plus/g2p` に `DictLoader` として含まれる
4. `piper-plus` は `@piper-plus/g2p` を dependency として使用
5. 既存の `piper-plus` ユーザー API に破壊的変更がない
6. TypeScript 型定義 (`index.d.ts`) が `@piper-plus/g2p` に含まれる

---

### FR-I-004: TTS フレームワーク統合ガイド

**タイトル:** 主要 TTS フレームワークへの組み込み方法をドキュメント化する

**Phase 割り当て:** Phase 1 v1.0.0 リリース後

**説明:**
eSpeak-ng を `piper-g2p` で置き換えるための統合ガイドを提供する。

**受入条件:**
1. VITS / VITS2 への統合例 (Python):
   ```python
   from piper_g2p import get_phonemizer
   phonemizer = get_phonemizer("ja-en")
   tokens, prosody = phonemizer.phonemize_with_prosody(text)
   ```
2. Coqui TTS への統合例 (Python): phonemizer バックエンドの差し替え手順
3. ブラウザ TTS (JS) への統合例: npm install + initialize + phonemize

---

### FR-I-005: CI/CD パイプライン

**タイトル:** 各パッケージの CI/CD を独立して構築する

**Phase 割り当て:** Phase 1 (Python / Rust), Phase 2 (JS/WASM)

**説明:**
各パッケージが独立した CI ワークフローを持ち、テスト・ビルド・パブリッシュを自動化する。既存 CI とは paths filter とタグパターンで分離し、`ci.yml`, `python-tests.yml`, `rust-tests.yml` は変更不要。

**ワークフロー一覧:**

| ワークフロー | paths filter | タグトリガー | レジストリ |
|-----------|------------|-----------|----------|
| `g2p-python-ci.yml` | `src/python/g2p/**` | `python-g2p-v*` | PyPI |
| `g2p-rust-ci.yml` | `src/rust/piper-g2p/**` | `rust-g2p-v*` | crates.io |
| `g2p-wasm-ci.yml` | `src/wasm/g2p/**` | `wasm-g2p-v*` | npm |

**Python CI ジョブ:**
- lint: `uv run ruff check` + `uv run ruff format --check` + `uv run mypy --strict`
- test: 3 OS x Python 3.11/3.12/3.13, `uv run pytest tests/ -v --cov=piper_g2p`
- publish: `uv build && uv publish` (タグトリガー)

**Rust CI ジョブ:**
- `cargo fmt -- --check` + `cargo clippy --all-features -- -D warnings`
- `cargo test --all-features` (3 OS x stable)
- `cargo publish -p piper-g2p` (タグトリガー)

**JS/WASM CI ジョブ:**
- `node --test` (3 OS x Node 18/20/22)
- パッケージサイズ検証 (< 10MB)
- `npm publish --provenance --access public` (タグトリガー)

**受入条件:**
1. 各 CI ワークフローが PR / push で自動実行される
2. タグトリガーでパッケージレジストリへの自動パブリッシュが動作する
3. 共通テストフィクスチャに対するテストが全 CI で実行される

---

## 12. リリース戦略

### 12.1 フェーズ定義

#### Phase 1: Python + Rust (最優先)

| 項目 | 内容 |
|------|------|
| **スコープ** | `piper-g2p` (PyPI) + `piper-g2p` (crates.io) |
| **推定工数** | 2-3 週 |
| **対象要求** | FR-G-001~007, NFR-G-001~004, FR-I-001, FR-I-002, FR-I-005 |
| **理由** | TTS 開発者の大半は Python / Rust ユーザー。eSpeak-ng 置き換え需要が最も高い |

**Phase 1 実施タスク:**

| # | タスク | 備考 |
|---|--------|------|
| 1 | Python パッケージ構造の作成 (`piper_g2p/`) | 22 ファイル移動 (技術調査 2.1) |
| 2 | `pyproject.toml` の整備 (言語別 optional deps) | 技術調査 2.4 の設計案ベース |
| 3 | `piper_train.phonemize` 互換シム作成 | 6 ファイルで re-export が必要 |
| 4 | `JapanesePhonemizer` に `custom_dict` コンストラクタ引数追加 | 現状は関数レベルのみ |
| 5 | `CustomDictionary` のデフォルト辞書パスを汎用化 | パッケージ内 `data/dictionaries/` にバンドル |
| 6 | Rust crate `piper-g2p` の作成 | 12 ファイル移動 (技術調査 3.1) |
| 7 | `PiperError` -> `G2pError`, `PhonemeIdMap` 型エイリアス | 依存断ち切り (技術調査 3.2) |
| 8 | `phoneme_converter.rs` の 2 分割 | 技術調査 8.2 |
| 9 | `piper-core` からの re-export 設定 | 後方互換性維持 |
| 10 | 共通テストフィクスチャ JSON の作成 | 技術調査 6.1-6.3 のスキーマ・ケース |
| 11 | CI ワークフローの構築 | `g2p-python-ci.yml`, `g2p-rust-ci.yml` |
| 12 | API ドキュメントの作成 | Python docstring, Rust doc comment |

**Phase 1 スコープ外:**
- インライン音素記法 `[[ ... ]]` (Python/Rust 新規実装は Phase 2 以降)
- TTS フレームワーク統合ガイド (v1.0.0 リリース後)
- JS/WASM パッケージ分離 (Phase 2)

**Phase 1 マイルストーン:**

| バージョン | 内容 | 公開先 |
|-----------|------|--------|
| v0.1.0 | 内部リリース。piper_train からの互換確認、既存テスト全パス | - |
| v0.2.0 | ベータ公開。外部ユーザーからのフィードバック収集 | PyPI / crates.io |
| v1.0.0 | 安定版リリース。API 凍結 | PyPI / crates.io |

#### Phase 2: JS/WASM リファクタリング

| 項目 | 内容 |
|------|------|
| **スコープ** | `@piper-plus/g2p` (npm) |
| **推定工数** | 3-4 週 |
| **対象要求** | FR-I-003, FR-I-005 (JS/WASM 分), FR-G-007 受入条件 4 (prosody 追加) |
| **開始条件** | Phase 1 v1.0.0 リリース後 |
| **理由** | 推論パイプラインとの結合度が高く工数大。ブラウザ TTS 市場の成長に合わせて実施 |

**Phase 2 実施タスク:**

| # | タスク |
|---|--------|
| 1 | `SimpleUnifiedPhonemizer` の分離リファクタリング |
| 2 | OpenJTalk WASM の DI 化 (コンストラクタ注入) |
| 3 | `DictManager` -> `DictLoader` の分離 |
| 4 | `phonemize_with_prosody()` API の追加 (A1/A2/A3 抽出) |
| 5 | インライン音素記法 `[[ ... ]]` の実装 (Python/Rust/JS) |
| 6 | TypeScript 型定義の整備 |
| 7 | npm パブリッシュ設定 + CI ワークフロー |

**Phase 2 マイルストーン:**

| バージョン | 内容 | 公開先 |
|-----------|------|--------|
| v0.1.0 | npm ベータ公開 | npm |
| v1.0.0 | 安定版リリース。Python/Rust v1.x と MAJOR バージョン同期 | npm |

---

### 12.2 バージョニング戦略

全パッケージで **SemVer 2.0.0** を採用する。

| バージョン変更 | 条件 | 例 |
|--------------|------|-----|
| **MAJOR** (x.0.0) | PUA テーブルの変更、phoneme_ids 互換性の破壊、API の破壊的変更 | PUA エントリ追加/削除 |
| **MINOR** (0.x.0) | 新言語の追加、新機能の追加、新フォーマット対応 | Swedish 言語追加 |
| **PATCH** (0.0.x) | バグ修正、パフォーマンス改善、ドキュメント修正 | 声調サンドヒのバグ修正 |

**重要ルール:**
- **PUA マッピングテーブルは MAJOR バージョンでのみ変更可能** (学習済みモデルの重みに直接依存)
- **MAJOR バージョンは全パッケージで同期** (v1.x.x の Python は v1.x.x の Rust / v1.x.x の JS と互換)
- MINOR / PATCH は各パッケージで独立して進行可能

---

### 12.3 パッケージレジストリ公開手順

#### Python (PyPI)

```bash
# ビルド + テスト
uv build
uv run pytest tests/

# テスト公開 (TestPyPI)
uv publish --publish-url https://test.pypi.org/legacy/

# 本番公開
uv publish
```

**CI タグトリガー:** `python-g2p-v*` (例: `python-g2p-v1.0.0`)

#### Rust (crates.io)

```bash
# ビルド + テスト
cargo build --release -p piper-g2p
cargo test -p piper-g2p --all-features

# 公開
cargo publish -p piper-g2p
```

**CI タグトリガー:** `rust-g2p-v*` (例: `rust-g2p-v1.0.0`)

#### JS/WASM (npm)

```bash
# テスト
node --test test/

# 公開
npm publish --provenance --access public
```

**CI タグトリガー:** `wasm-g2p-v*` (例: `wasm-g2p-v1.0.0`)

---

## 13. 要求トレーサビリティ

### 統合・整理マップ

以下は旧要求 ID と新要求 ID の対応を示す。重複する要求は統合し、技術調査の結果を反映して更新した。

| 旧 ID | 新 ID | 変更内容 |
|--------|-------|---------|
| FR-G-001 (統一インターフェース) | **FR-G-001** | C# 列を除外。JS/WASM 列を追加 |
| FR-G-002 (言語レジストリ) + FR-G-003 (言語自動検出) | **FR-G-002** | 統合。レジストリと自動検出は密結合のため一体化 |
| FR-G-004 (PUA マッピング) | **FR-G-003** | PUA 差分が存在しないことを反映 (87 エントリ一致確認済み)。C# 参照を除外 |
| FR-G-005 (音素体系互換性) | **FR-G-004** | JS/WASM の例外を明文化 |
| FR-G-006 (カスタム辞書) | **FR-G-005** | TSV サポートを除外 (C# 固有)。Python の辞書パス汎用化を追加 |
| FR-G-008 (MultilingualPhonemizer) + FR-G-009 (言語別 Phonemizer) | **FR-G-006** | 統合。個別言語と多言語統合は同一要求として管理 |
| FR-G-007 (ProsodyInfo) | **FR-G-007** | JS/WASM の Phase 2 追加を明記 |
| FR-G-010 (インライン音素記法) | Phase 2 タスク | 要求から Phase 2 タスクに降格 |
| NFR-G-001 (ライセンス) + NFR-G-002 (ゼロ C/C++ ビルド依存) | **NFR-G-001** | 統合。両方ともデプロイ容易性の要件 |
| NFR-G-003 (テスト網羅) | **NFR-G-002** | テストフィクスチャスキーマ・ケース一覧を技術調査から統合 |
| NFR-G-004 (パフォーマンス) | **NFR-G-003** | C# の要件を除外 |
| NFR-G-005 (API ドキュメント) | **NFR-G-004** | C# の要件を除外 |
| FR-I-001 (Python 互換性) | **FR-I-001** | 互換シム実装と対象ファイル一覧を技術調査から追加 |
| FR-I-002 (Rust crate 分離) | **FR-I-002** | 依存断ち切り詳細を技術調査から追加 |
| FR-I-003 (C# 分離) | **削除** | DotNetG2P が独立パッケージとして公開済みのため対象外 |
| FR-I-004 (JS/WASM 分離) | **FR-I-003** | Phase 2 に割り当て |
| FR-I-005 (TTS 統合ガイド) | **FR-I-004** | Phase 1 v1.0.0 リリース後に割り当て |
| FR-I-006 (CI/CD) | **FR-I-005** | C# ワークフローを除外。技術調査 7.1-7.7 の設計を統合 |

### 要求数サマリ

| カテゴリ | 旧 | 新 | 削減理由 |
|---------|-----|-----|---------|
| 共通機能要求 (FR-G) | 10 | 7 | 統合 3 件 (レジストリ+自動検出, Multilingual+言語別, インライン音素->Phase2タスク) |
| 共通非機能要求 (NFR-G) | 5 | 4 | 統合 1 件 (ライセンス+ビルド依存) |
| 統合要求 (FR-I) | 6 | 5 | 削除 1 件 (C# 分離) |
| **合計** | **21** | **16** | |
