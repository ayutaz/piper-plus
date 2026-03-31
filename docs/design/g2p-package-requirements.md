# piper-g2p 独立パッケージ 要求定義 v2

> 作成日: 2026-03-31
> ベース: `g2p-standalone-package.md` (調査レポート), `g2p-technical-investigation.md` (技術調査)
> ステータス: 10 人レビュー合意事項反映済み

---

## 設計方針

### IPA-first

`phonemize()` は **IPA トークン列** を返す。PUA エンコード (Private Use Area 1 文字マッピング) は行わない。
現在の実装では `token_mapper.map_sequence()` が多文字トークンを PUA 1 文字に変換してから返しているが、
独立パッケージではこの変換を行わず、IPA 表記のままのトークンを返す。

```python
# 現在 (piper_train.phonemize)
tokens = phonemizer.phonemize("こんにちは")
# -> PUA 混在: ["^", "k", "o", "\ue019", "n", "i", "\ue00e", "i", "h", "a", "$"]

# 新パッケージ (piper_g2p)
tokens = phonemizer.phonemize("こんにちは")
# -> IPA: ["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]
#    (BOS/EOS/パディングなし、PUA 変換なし)
```

### エンコード分離

Piper TTS 固有のエンコーディング処理は `piper_g2p.encode` モジュールに分離する。
以下の処理はコア `Phonemizer` ABC に含めない:

| 処理 | 現在の所在 | 新パッケージでの所在 |
|------|-----------|-------------------|
| `get_phoneme_id_map()` | `Phonemizer` ABC (抽象メソッド) | `piper_g2p.encode.PiperEncoder` |
| `post_process_ids()` | `Phonemizer` ABC (デフォルト実装) | `piper_g2p.encode.PiperEncoder` |
| PUA マッピング (`token_mapper.py`) | `phonemize/token_mapper.py` | `piper_g2p.encode.pua` |
| BOS/EOS/パディング挿入 | `post_process_ids()` 内 | `piper_g2p.encode.PiperEncoder.encode()` |
| ID マップ生成 (`*_id_map.py`) | 各言語の `*_id_map.py` | `piper_g2p.encode.id_maps` |

### Phonemizer ABC の責務

ABC は **2 メソッドのみ**:

| メソッド | 責務 |
|---------|------|
| `phonemize(text) -> list[str]` | テキストを IPA トークン列に変換 |
| `phonemize_with_prosody(text) -> tuple[list[str], list[ProsodyInfo \| None]]` | テキストを IPA トークン列 + 韻律情報に変換 |

**現在の ABC との差分**:

| 項目 | 現在 (`piper_train`) | 新 (`piper_g2p`) | 理由 |
|------|---------------------|-----------------|------|
| `get_phoneme_id_map()` | 抽象メソッド | **削除** (encode モジュールへ) | G2P とエンコードの責務分離 |
| `post_process_ids()` | デフォルト実装 | **削除** (encode モジュールへ) | 同上 |
| `phonemize()` の戻り値 | PUA エンコード済み文字列 (JA) | IPA トークン列 | IPA-first 方針 |
| BOS(`^`)/EOS(`$`) の扱い | `phonemize()` が含める (JA) | **含めない** | エンコーダが付与 |

---

## Phase 一覧

| Phase | スコープ | ランタイム | 期間目安 |
|-------|---------|-----------|---------|
| **0 (MVP)** | Python JA + EN、コア API + encode | Python | 1 週間 |
| 1 | 残り 5 言語 + MultilingualPhonemizer + カスタム辞書 | Python | 1-2 週間 |
| 2 | Rust crate (`piper-g2p`) | Rust | 需要検証後 |
| 3 | JS/WASM (`@piper-plus/g2p`) | JavaScript | 需要に応じて |

### 対象外

- **C# (DotNetG2P)**: 既に独立パッケージとして NuGet 公開済み
- **学習パイプライン統合**: `piper_train` からの互換シムは Phase 1 完了後に実施
- **ニューラル G2P**: 本パッケージはルールベース / 辞書ベースの G2P のみ

---

## 目次

1. [Phase 0: MVP (Python JA+EN)](#phase-0-mvp-python-jaen)
   - [機能要求 (FR-001 -- FR-007)](#機能要求)
   - [非機能要求 (NFR-001 -- NFR-004)](#非機能要求)
2. [コア API 設計](#コア-api-設計)
   - [Phonemizer ABC](#phonemizer-abc)
   - [ProsodyInfo](#prosodyinfo)
   - [レジストリ](#レジストリ)
   - [PiperEncoder](#piperencoder)
3. (後続セクション: Phase 1 以降は別ドキュメントで定義)

---

## Phase 0: MVP (Python JA+EN)

> 目標: `uv pip install piper-g2p[ja,en]` で日本語 + 英語の IPA 音素化が動作する。
> 期間: 1 週間スプリント。

### 機能要求

#### FR-001: Phonemizer ABC

**説明**: G2P の抽象基底クラスを提供する。`phonemize()` と `phonemize_with_prosody()` の 2 メソッドのみを抽象メソッドとして定義する。

**受入条件**:
- `from piper_g2p import Phonemizer, ProsodyInfo` でインポートできる
- `Phonemizer` は `phonemize()` と `phonemize_with_prosody()` のみを `@abstractmethod` として持つ
- `get_phoneme_id_map()` および `post_process_ids()` は ABC に含まれない
- `ProsodyInfo` は `a1: int`, `a2: int`, `a3: int` を持つ dataclass である
- サードパーティがサブクラス化して独自言語の Phonemizer を実装できる

---

#### FR-002: 言語レジストリ

**説明**: 言語コードから Phonemizer インスタンスを取得するレジストリ機構を提供する。

**受入条件**:
- `from piper_g2p import get_phonemizer, register_language, available_languages` でインポートできる
- `get_phonemizer("ja")` で `JapanesePhonemizer` が返る (pyopenjtalk インストール時)
- `get_phonemizer("en")` で `EnglishPhonemizer` が返る (g2p-en インストール時)
- 依存が未インストールの言語はレジストリ自動登録時にスキップされ、`ImportError` にならない
- `register_language("custom", my_phonemizer)` でユーザ定義 Phonemizer を登録できる
- `available_languages()` がインストール済み言語のリストを返す
- Phase 0 では複合コード (`"ja-en"`) による `MultilingualPhonemizer` 自動生成は不要 (Phase 1)

---

#### FR-003: JapanesePhonemizer

**説明**: OpenJTalk ベースの日本語 G2P を提供する。IPA トークン列を返し、BOS/EOS/PUA 変換を行わない。

**受入条件**:
- `get_phonemizer("ja").phonemize("こんにちは")` が IPA トークン列を返す
  - 例: `["k", "o", "N_n", "n", "i", "ch", "i", "h", "a"]`
  - `"^"`, `"$"`, PUA 文字を含まない
- `phonemize_with_prosody("こんにちは")` が `(tokens, prosody_list)` を返す
  - `prosody_list` の各要素は `ProsodyInfo(a1, a2, a3)` または `None`
  - 韻律記号 (`"#"`, `"["`, `"]"`) は含む (音素列の構造情報として)
  - 疑問詞マーカー (`"?"`, `"?!"`, `"?."`, `"?~"`) は含む (文末情報として)
- 文脈依存 N 音素変異 (`N_m`, `N_n`, `N_ng`, `N_uvular`) が適用される
- `pyopenjtalk` / `pyopenjtalk-plus` 未インストール時は `ImportError` (即座に、利用時に)
- **現在の `phonemize_japanese()` との差分**:
  - BOS `"^"` / EOS `"$"` を出力しない
  - `map_sequence()` (PUA 変換) を呼ばない
  - 韻律記号・疑問詞マーカー・N 変異はそのまま保持

---

#### FR-004: EnglishPhonemizer

**説明**: g2p-en ベースの英語 G2P を提供する。ARPAbet → IPA 変換済みの IPA トークン列を返す。

**受入条件**:
- `get_phonemizer("en").phonemize("Hello world")` が IPA トークン列を返す
  - 例: `["h", "ʌ", "ˈ", "l", "oʊ", " ", "ˈ", "w", "ɜː", "l", "d"]`
- ストレスマーカー (`"ˈ"`, `"ˌ"`) が IPA 規約通りに含まれる
- 機能語 (97 語) のストレス除去が適用される
- `phonemize_with_prosody()` が `ProsodyInfo(a1=0, a2=stress_level, a3=word_phoneme_count)` を返す
- `g2p-en` 未インストール時は `ImportError` (利用時に)
- **現在の `phonemize_english()` との差分**: なし (現在の実装は既に IPA を返している)

---

#### FR-005: PiperEncoder (encode モジュール)

**説明**: IPA トークン列を Piper TTS の phoneme_ids に変換するエンコーダを `piper_g2p.encode` モジュールとして提供する。

**受入条件**:
- `from piper_g2p.encode import PiperEncoder` でインポートできる
- `PiperEncoder(phoneme_id_map, pua_table=None)` でインスタンス化
  - `phoneme_id_map`: `dict[str, list[int]]` (Piper の config.json 由来)
  - `pua_table`: PUA マッピングテーブル (デフォルト: 組み込みテーブル)
- `encoder.encode(tokens)` が `list[int]` を返す:
  1. 多文字トークンを PUA 1 文字にマッピング
  2. phoneme_id_map でトークン → ID に変換
  3. BOS (`^`) / EOS (`$`) / inter-phoneme パディング (`_`) を挿入
- `encoder.encode_with_prosody(tokens, prosody_list)` が `(list[int], list[dict | None])` を返す:
  - 上記に加え、パディング位置に `None` を挿入した prosody_features を返す
- `encoder.encode(tokens, eos_token="?!")` で EOS トークンを指定できる
- `from piper_g2p.encode import get_phoneme_id_map` で言語別 ID マップを取得できる:
  - `get_phoneme_id_map("ja")` → 日本語 ID マップ
  - `get_phoneme_id_map("en")` → 英語 ID マップ (Phase 0 は JA + EN)
- **PUA テーブル**: `from piper_g2p.encode import FIXED_PUA_MAPPING` で 87 エントリの固定テーブルにアクセスできる

---

#### FR-006: pyproject.toml と言語別 optional deps

**説明**: パッケージメタデータと言語別オプショナル依存を定義する。

**受入条件**:
- `uv pip install piper-g2p` でコアのみインストール (外部依存なし)
- `uv pip install piper-g2p[ja]` で JA 依存 (`pyopenjtalk-plus`) を追加
- `uv pip install piper-g2p[en]` で EN 依存 (`g2p-en>=2.1.0`) を追加
- `uv pip install piper-g2p[ja,en]` で両方インストール
- `requires-python = ">=3.11"`
- ライセンス: MIT
- パッケージ名: `piper-g2p`、インポート名: `piper_g2p`

---

#### FR-007: piper_train 互換シム

**説明**: 既存の `piper_train.phonemize` からの import を維持する互換レイヤーを提供する。

**受入条件**:
- `from piper_train.phonemize import get_phonemizer, Phonemizer, ProsodyInfo` が引き続き動作する
- `from piper_train.phonemize.japanese import phonemize_japanese` が引き続き動作する (BOS/EOS/PUA 含む従来の出力形式)
- `piper_train.phonemize` は内部で `piper_g2p` を使用し、従来の出力形式 (BOS/EOS/PUA 含む) に変換するラッパーを提供する
- 既存テストが変更なしで pass する
- `DeprecationWarning` は Phase 0 では発行しない (Phase 1 で検討)

---

### 非機能要求

#### NFR-001: テストカバレッジ

**説明**: Phase 0 のスコープ (JA + EN + encode) に対して十分なテストを提供する。

**受入条件**:
- `uv run pytest` でテストが実行できる
- JA: 音素化、N 変異 4 パターン、疑問詞マーカー 4 パターン、韻律記号の最低 10 テストケース
- EN: 音素化、ストレスマーカー、機能語ストレス除去の最低 6 テストケース
- encode: PUA 変換、BOS/EOS 挿入、パディング、ID マップ変換の最低 8 テストケース
- 互換シム: `piper_train.phonemize` 経由の動作確認の最低 4 テストケース
- カバレッジ 90% 以上 (コア + JA + EN + encode)

---

#### NFR-002: ゼロコンパイル依存

**説明**: C/C++ コンパイルなしでインストール可能にする (pyopenjtalk を除く)。

**受入条件**:
- `piper-g2p` コア + EN は Pure Python (C 拡張なし)
- JA の `pyopenjtalk-plus` は wheel 配布が存在するプラットフォーム (Linux x64, macOS arm64, Windows x64) でビルド不要
- ES, FR, PT (Phase 1) はルールベースのため外部依存なし

---

#### NFR-003: パフォーマンス

**説明**: 既存実装と同等以上のパフォーマンスを維持する。

**受入条件**:
- JA: 1 文 (20 文字程度) の音素化が 10ms 以下 (pyopenjtalk のオーバーヘッドは含まない)
- EN: 1 文 (10 語程度) の音素化が 5ms 以下
- encode: 100 トークンのエンコードが 1ms 以下

---

#### NFR-004: CI ワークフロー

**説明**: PR ごとに自動テストを実行する GitHub Actions ワークフローを提供する。

**受入条件**:
- `g2p-python-ci.yml` が `src/python/g2p/**` の変更で起動する
- テストマトリクス: 3 OS (ubuntu, macos, windows) x 2 Python (3.11, 3.13)
- lint: `ruff check` + `ruff format --check`
- 型チェック: `mypy --strict` (Phase 1 で検討。Phase 0 は `--ignore-missing-imports`)
- タグ `python-g2p-v*` で PyPI publish ジョブが起動する

---

## コア API 設計

### Phonemizer ABC

現在の `src/python/piper_train/phonemize/base.py` から `get_phoneme_id_map()` と `post_process_ids()` を除去し、純粋な G2P インターフェースとする。

```python
# piper_g2p/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProsodyInfo:
    """韻律情報。言語によって a1/a2/a3 の意味が異なる。

    日本語:
        a1: アクセント核からの相対位置
        a2: アクセント句内のモーラ位置 (1-based)
        a3: アクセント句内の総モーラ数
    英語:
        a1: 0 (未使用)
        a2: ストレスレベル (0=なし, 1=secondary, 2=primary)
        a3: 単語内の音素数
    """

    a1: int
    a2: int
    a3: int


class Phonemizer(ABC):
    """G2P 抽象基底クラス。

    phonemize() は IPA トークン列を返す。
    BOS/EOS/パディング/PUA エンコードは含めない。
    Piper TTS 固有のエンコーディングは piper_g2p.encode.PiperEncoder が担う。
    """

    @abstractmethod
    def phonemize(self, text: str) -> list[str]:
        """テキストを IPA トークン列に変換する。

        Parameters
        ----------
        text : str
            入力テキスト。

        Returns
        -------
        list[str]
            IPA トークンのリスト。各要素は 1 音素または韻律記号。
            BOS/EOS は含まない。PUA エンコードは行わない。
        """

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """テキストを IPA トークン列 + 韻律情報に変換する。

        Parameters
        ----------
        text : str
            入力テキスト。

        Returns
        -------
        tuple[list[str], list[ProsodyInfo | None]]
            (tokens, prosody_list) のタプル。
            tokens: IPA トークンのリスト (phonemize() と同一形式)。
            prosody_list: 各トークンに対応する ProsodyInfo または None。
            len(tokens) == len(prosody_list) が保証される。
        """
```

**現在の ABC (`piper_train.phonemize.base.Phonemizer`) との差分**:

```python
# --- 削除されるメソッド ---

# 1. get_phoneme_id_map() -- encode モジュールへ移動
#    現在: Phonemizer ABC の抽象メソッド
#    理由: phoneme ID マップは G2P ではなくエンコーディングの責務
@abstractmethod
def get_phoneme_id_map(self) -> dict[str, list[int]] | None: ...  # 削除

# 2. post_process_ids() -- encode モジュールへ移動
#    現在: Phonemizer ABC のデフォルト実装 (60 行)
#    理由: BOS/EOS/パディング挿入は Piper TTS 固有のエンコーディング
def post_process_ids(self, phoneme_ids, prosody_features, phoneme_id_map,
                     eos_token="$") -> tuple[list[int], list[dict | None]]: ...  # 削除
```

---

### ProsodyInfo

現在の `ProsodyInfo` と同一。変更なし。

```python
# piper_g2p/base.py (上記 Phonemizer ABC と同ファイル)

@dataclass
class ProsodyInfo:
    a1: int
    a2: int
    a3: int
```

互換性のため `piper_train.phonemize.base.ProsodyInfo` は `piper_g2p.ProsodyInfo` を re-export する。

---

### レジストリ

現在の `registry.py` のコア機能を維持しつつ、`MultilingualPhonemizer` 自動生成は Phase 1 に延期する。

```python
# piper_g2p/registry.py

from .base import Phonemizer

_REGISTRY: dict[str, Phonemizer] = {}


def register_language(code: str, phonemizer: Phonemizer) -> None:
    """言語コードに Phonemizer を登録する。"""
    _REGISTRY[code] = phonemizer


def get_phonemizer(language: str) -> Phonemizer:
    """言語コードから Phonemizer を取得する。

    Parameters
    ----------
    language : str
        言語コード ("ja", "en" 等)。

    Returns
    -------
    Phonemizer
        登録済みの Phonemizer インスタンス。

    Raises
    ------
    ValueError
        未登録の言語コードが指定された場合。
    """
    if language in _REGISTRY:
        return _REGISTRY[language]
    raise ValueError(
        f"Unsupported language: {language}. "
        f"Available: {list(_REGISTRY.keys())}"
    )


def available_languages() -> list[str]:
    """登録済み言語コードのリストを返す。"""
    return list(_REGISTRY.keys())


def _auto_register() -> None:
    """インポート時に利用可能な言語 Phonemizer を自動登録する。"""
    try:
        from .japanese import JapanesePhonemizer
        register_language("ja", JapanesePhonemizer())
    except ImportError:
        pass
    try:
        from .english import EnglishPhonemizer
        register_language("en", EnglishPhonemizer())
    except ImportError:
        pass
    # Phase 1: zh, ko, es, pt, fr をここに追加


_auto_register()
```

**現在の `registry.py` との差分**:

| 項目 | 現在 | Phase 0 |
|------|------|---------|
| 複合コード (`"ja-en"`) | `MultilingualPhonemizer` 自動生成 | 未実装 (Phase 1) |
| canonical sorted order | `"en-ja"` に正規化 | 未実装 (Phase 1) |
| `_detect_default_latin()` | 実装済み | 未実装 (Phase 1) |
| `BilingualPhonemizer` 登録 | `"ja-en"` / `"en-ja"` を自動登録 | 未実装 (Phase 1) |
| 7 言語自動登録 | JA/EN/ZH/KO/ES/PT/FR | JA/EN のみ |

---

### PiperEncoder

現在は `Phonemizer.post_process_ids()` + `token_mapper.py` + `*_id_map.py` に分散している処理を、単一クラスに統合する。

```python
# piper_g2p/encode/__init__.py

from .encoder import PiperEncoder
from .pua import FIXED_PUA_MAPPING
from .id_maps import get_phoneme_id_map

__all__ = ["PiperEncoder", "FIXED_PUA_MAPPING", "get_phoneme_id_map"]
```

```python
# piper_g2p/encode/encoder.py

from __future__ import annotations


class PiperEncoder:
    """IPA トークン列を Piper TTS の phoneme_ids に変換する。

    責務:
    1. 多文字 IPA トークン → PUA 1 文字マッピング
    2. PUA 文字 / IPA 文字 → phoneme_id_map による ID 変換
    3. BOS (^) / EOS ($) / inter-phoneme パディング (_) の挿入

    Parameters
    ----------
    phoneme_id_map : dict[str, list[int]]
        Piper の config.json 由来の phoneme_id_map。
        キー: 1 文字の音素トークン (PUA 含む)
        値: phoneme ID のリスト (通常は 1 要素)
    pua_table : dict[str, int] | None
        多文字トークン → PUA コードポイントのマッピング。
        None の場合は組み込みの FIXED_PUA_MAPPING を使用。
    """

    def __init__(
        self,
        phoneme_id_map: dict[str, list[int]],
        pua_table: dict[str, int] | None = None,
    ) -> None:
        self._phoneme_id_map = phoneme_id_map
        if pua_table is None:
            from .pua import FIXED_PUA_MAPPING
            pua_table = FIXED_PUA_MAPPING
        # token -> PUA char の変換テーブルを構築
        self._token_to_char: dict[str, str] = {}
        for token, codepoint in pua_table.items():
            self._token_to_char[token] = chr(codepoint)

    def encode(
        self,
        tokens: list[str],
        eos_token: str = "$",
    ) -> list[int]:
        """IPA トークン列を phoneme_ids に変換する。

        処理順序:
        1. 多文字トークンを PUA 1 文字にマッピング
        2. phoneme_id_map で ID に変換
        3. inter-phoneme パディングを挿入
        4. BOS/EOS で囲む

        Parameters
        ----------
        tokens : list[str]
            IPA トークン列 (Phonemizer.phonemize() の出力)。
        eos_token : str
            EOS トークン。日本語の疑問詞マーカー ("?", "?!" 等) を指定可能。

        Returns
        -------
        list[int]
            Piper TTS 用の phoneme_ids。
        """
        ids, _ = self.encode_with_prosody(tokens, prosody_list=None,
                                          eos_token=eos_token)
        return ids

    def encode_with_prosody(
        self,
        tokens: list[str],
        prosody_list: list[dict | None] | None = None,
        eos_token: str = "$",
    ) -> tuple[list[int], list[dict | None]]:
        """IPA トークン列を phoneme_ids + prosody_features に変換する。

        Parameters
        ----------
        tokens : list[str]
            IPA トークン列。
        prosody_list : list[dict | None] | None
            各トークンに対応する韻律情報。None の場合は全て None として扱う。
            ProsodyInfo は {"a1": int, "a2": int, "a3": int} の dict に変換済みを想定。
        eos_token : str
            EOS トークン。

        Returns
        -------
        tuple[list[int], list[dict | None]]
            (phoneme_ids, prosody_features) のタプル。
            パディング・BOS・EOS 位置には None が挿入される。
        """
        id_map = self._phoneme_id_map
        pad_ids = id_map.get("_", [0])
        bos_ids = id_map.get("^")
        eos_ids = id_map.get(eos_token, id_map.get("$"))

        if prosody_list is None:
            prosody_list = [None] * len(tokens)

        # Step 1-2: トークン → PUA → ID
        raw_ids: list[int] = []
        raw_prosody: list[dict | None] = []
        for token, prosody in zip(tokens, prosody_list, strict=True):
            # 多文字トークンを PUA に変換
            mapped = self._token_to_char.get(token, token)
            # 各文字を ID に変換
            for ch in mapped:
                ch_ids = id_map.get(ch)
                if ch_ids:
                    raw_ids.extend(ch_ids)
                    raw_prosody.extend([prosody] * len(ch_ids))

        # Step 3: inter-phoneme パディング挿入
        padded_ids: list[int] = []
        padded_prosody: list[dict | None] = []
        for phoneme_id, prosody in zip(raw_ids, raw_prosody, strict=True):
            padded_ids.append(phoneme_id)
            padded_prosody.append(prosody)
            if phoneme_id not in pad_ids:
                padded_ids.extend(pad_ids)
                padded_prosody.extend([None] * len(pad_ids))

        # Step 4: BOS/EOS
        if bos_ids:
            padded_ids = bos_ids + [pad_ids[0]] + padded_ids
            padded_prosody = [None] * (len(bos_ids) + 1) + padded_prosody
        if eos_ids:
            padded_ids = padded_ids + eos_ids
            padded_prosody = padded_prosody + [None] * len(eos_ids)

        return padded_ids, padded_prosody
```

```python
# piper_g2p/encode/pua.py

"""PUA (Private Use Area) マッピングテーブル。

多文字 IPA トークンを Unicode PUA の 1 文字にマッピングする。
Piper TTS の全プラットフォーム (Python/Rust/C#) で共通の 87 エントリ。

注意: コードポイントの値は学習済みモデルに焼き込まれているため変更不可。
"""

FIXED_PUA_MAPPING: dict[str, int] = {
    # 日本語 (JA) -- 29 エントリ
    "a:": 0xE000,
    "i:": 0xE001,
    # ... (現在の token_mapper.py の FIXED_PUA_MAPPING と同一)

    # 共有 -- 2 エントリ
    "rr": 0xE01D,
    "y_vowel": 0xE01E,

    # 中国語 (ZH) -- 43 エントリ (Phase 1)
    # 韓国語 (KO) -- 8 エントリ (Phase 1)
    # スペイン語/ポルトガル語 (ES/PT) -- 2 エントリ (Phase 1)
    # フランス語 (FR) -- 3 エントリ (Phase 1)
}

# Phase 0 では JA + EN + 共有に必要なエントリのみ。
# Phase 1 で全 87 エントリを含める。
```

```python
# piper_g2p/encode/id_maps.py

"""言語別 phoneme ID マップ生成。

Piper TTS の config.json に書き込む phoneme_id_map を生成する。
"""

from __future__ import annotations


def get_phoneme_id_map(language: str) -> dict[str, list[int]]:
    """言語コードに対応する phoneme_id_map を返す。

    Parameters
    ----------
    language : str
        言語コード ("ja", "en" 等)。

    Returns
    -------
    dict[str, list[int]]
        phoneme_id_map (トークン文字列 → ID リスト)。
    """
    if language == "ja":
        from ._ja_id_map import get_japanese_id_map
        return get_japanese_id_map()
    if language == "en":
        from ._en_id_map import get_english_id_map
        return get_english_id_map()
    raise ValueError(f"Unsupported language for ID map: {language}")
```

**現在の実装との対応関係**:

| 現在のファイル | 新パッケージでの所在 | 変更点 |
|--------------|-------------------|--------|
| `token_mapper.py` (`FIXED_PUA_MAPPING`, `TOKEN2CHAR`, `map_sequence()`, `register()`) | `piper_g2p/encode/pua.py` | `map_sequence()` は `PiperEncoder` 内部に統合。`register()` (動的割当) は Phase 0 では不要 |
| `jp_id_map.py` (`get_japanese_id_map()`) | `piper_g2p/encode/_ja_id_map.py` | 変更なし |
| `bilingual_id_map.py` (EN phonemes) | `piper_g2p/encode/_en_id_map.py` | EN 部分のみ抽出 |
| `multilingual_id_map.py` (`get_multilingual_id_map()`) | Phase 1 で実装 | -- |
| `base.py` (`post_process_ids()`) | `piper_g2p/encode/encoder.py` (`PiperEncoder`) | メソッド → クラスに昇格 |
| `base.py` (`get_phoneme_id_map()`) | `piper_g2p/encode/id_maps.py` | ABC メソッド → スタンドアロン関数に変更 |
## Phase 1: 全言語展開 (全言語 + MultilingualPhonemizer + カスタム辞書)

> Phase 1 は全 7 言語 Phonemizer、MultilingualPhonemizer、カスタム辞書を独立パッケージとして機能させるためのスコープを定義する。既存セクション 9-10 の共通要求 (FR-G / NFR-G) が上位仕様であり、本セクションはその実装フェーズとして具体的な受入条件と既知制限を補足する。
>
> **前提**: 技術調査 (g2p-technical-investigation.md) で以下が確認済み:
> - `phonemize/` は `piper_train` 他モジュールへの依存がゼロ (22 ファイル自己完結)
> - PUA マッピングは全プラットフォーム 87 エントリで一致
> - サードパーティ依存は全て条件付き import (pyopenjtalk, g2p_en, pypinyin, g2pk2)

### 1 機能要求 (FR-100~)

#### FR-100: 7 言語 Phonemizer の IPA トークン列出力

**タイトル:** 全言語の `phonemize()` / `phonemize_with_prosody()` は IPA トークン列を返す

**説明:**
全 7 言語の Phonemizer は IPA (International Phonetic Alphabet) ベースのトークン列を一貫した出力形式として返す。多文字 IPA トークン (`tʃ`, `ɛ̃`, `tɕʰ` 等) は PUA マッピング (FR-G-003) により単一コードポイントに変換済みの状態で返される。言語固有の中間表現 (ピンイン、ARPAbet 等) はパッケージ内部に閉じ込め、公開 API には露出しない。

**言語別仕様:**

| 言語 | クラス | 外部依存 (optional) | phonemize() 出力 |
|------|--------|-------------------|-----------------|
| JA | `JapanesePhonemizer` | pyopenjtalk-plus (BSD-3) | OpenJTalk full-context -> IPA + PUA (29 JA エントリ) |
| EN | `EnglishPhonemizer` | g2p-en (Apache-2.0) | ARPAbet -> IPA 変換済みトークン列 |
| ZH | `ChinesePhonemizer` | pypinyin (MIT) | ピンイン -> IPA + PUA (43 ZH エントリ) + tone{1-5} マーカー |
| KO | `KoreanPhonemizer` | g2pk2 (Apache-2.0) | Hangul 分解 -> IPA + PUA (8 KO エントリ) |
| ES | `SpanishPhonemizer` | なし | ルールベース -> IPA + ストレスマーカー |
| FR | `FrenchPhonemizer` | なし | ルールベース -> IPA + 鼻母音 PUA (3 FR エントリ) |
| PT | `PortuguesePhonemizer` | なし | ルールベース -> IPA + BR 後処理 (t/d 口蓋化, l 母音化) |

**受入条件:**
1. 各言語の `phonemize("テスト文")` が IPA トークンの `list[str]` を返す
2. 多文字トークンは `token_mapper.map_sequence()` により PUA 変換済み
3. `phonemize_with_prosody()` が `(list[str], list[ProsodyInfo | None])` を返し、両リストは同長
4. 言語固有の中間表現 (ピンイン, ARPAbet) が公開 API の戻り値に含まれない

---

#### FR-101: MultilingualPhonemizer (N 言語コードスイッチング)

**タイトル:** 任意の言語組み合わせで混在テキストを音素化する MultilingualPhonemizer を提供する

**説明:**
`MultilingualPhonemizer` は `UnicodeLanguageDetector` でテキストを言語セグメントに分割し、各セグメントを対応する言語 Phonemizer に委譲する。セグメントの BOS/EOS は除去し、最終的な `post_process_ids()` で統一的な BOS/PAD/EOS を付与する。

**既知制限 -- ラテン文字言語の区別不可:**

ES/FR/PT はいずれもラテン文字を使用するため、`UnicodeLanguageDetector` による文字レベルの自動判別は不可能。ラテン文字セグメントは `default_latin_language` (デフォルト: `"en"`) に一律マッピングされる。ES/FR/PT 固有テキストを正しく音素化するには以下のいずれかを使用する:
- 単一言語 Phonemizer を直接インスタンス化 (`SpanishPhonemizer()` 等)
- `default_latin_language` を変更 (`MultilingualPhonemizer(["ja", "es"], default_latin_language="es")`)

**受入条件:**
1. `MultilingualPhonemizer(["ja", "en", "zh"])` で 3 言語混在テキストを処理可能
2. 個別セグメントの BOS/EOS が除去され、全体で 1 つの BOS/EOS が付加される
3. CJK 曖昧性解消 (仮名コンテキストで漢字を JA 判定) が正しく動作する
4. `get_phonemizer("ja-en-zh")` でレジストリから自動生成される
5. 最後に見た EOS トークン (疑問詞マーカー `?!`/`?.`/`?~` 含む) が `post_process_ids()` に反映される
6. ラテン文字言語の区別不可を API ドキュメント (docstring) に明記する

---

#### FR-102: カスタム辞書 (JSON v1.0/v2.0)

**タイトル:** JSON v1.0/v2.0 形式のカスタム辞書を安全にロード・適用する

**説明:**
`CustomDictionary` はテキスト前処理段階で単語を読みに置換する。FR-G-005 の共通仕様に加え、Phase 1 では入力バリデーションを強化する。

**入力バリデーション要求:**

| 脅威 | 対策 |
|------|------|
| 巨大 JSON (DoS) | `load_dictionary()` で最大ファイルサイズを制限 (デフォルト 10MB, 設定可能)。上限超過時は `ValueError` |
| パストラバーサル | `dict_paths` の各パスを `Path.resolve()` で正規化し、`..` を含むパスを拒否。Python: `os.path.commonpath()` で許可ディレクトリ外アクセスを検出 |
| ReDoS | `_get_word_pattern()` が生成する正規表現パターンは `re.escape()` 済みの固定文字列 + 定数量指定子のみで構成される (既存実装で対策済み)。新規エントリ追加時もこの制約を維持する |

**受入条件:**
1. JSON v1.0/v2.0 の両フォーマットがロード可能
2. 10MB 超の辞書ファイルをロードしようとすると `ValueError` が発生する
3. `../../../etc/passwd` のようなパストラバーサルパスが拒否される
4. `CustomDictionary(load_defaults=False)` でデフォルト辞書のスキップが可能
5. `JapanesePhonemizer(custom_dict="path/to/dict.json")` でクラスレベルでカスタム辞書を保持可能
6. 同一辞書ファイルを Python / Rust に渡した場合、同一テキストに対して同一の置換結果を返す

---

#### FR-103: 言語別 Phonemizer のオプショナル依存

**タイトル:** 各言語の外部依存はオプショナルとし、未インストール時に明確なエラーを返す

**説明:**
JA/EN/ZH/KO は外部ライブラリに依存するが、全てオプショナル。パッケージのコアインストール (`pip install piper-g2p`) は依存ゼロ。ES/FR/PT は Pure Python で追加依存なし。

```toml
[project.optional-dependencies]
ja = ["pyopenjtalk-plus>=0.4"]
en = ["g2p-en>=2.1.0"]
zh = ["pypinyin>=0.50"]
ko = ["g2pk2>=0.0.3"]
all = ["piper-g2p[ja,en,zh,ko]"]
```

**受入条件:**
1. `pip install piper-g2p` が依存ゼロで完了する
2. `pip install piper-g2p[ja]` で JA 依存のみがインストールされる
3. 依存未インストールの言語を使用すると `ImportError` と具体的なインストール手順が表示される
4. レジストリの自動登録時に依存未インストールの言語はスキップされ、トップレベル `import piper_g2p` が失敗しない
5. Rust: `features = ["japanese"]` / `features = ["multilingual"]` 等の feature flag で同等の制御が可能

---

### 2 非機能要求 (NFR-100~)

#### NFR-100: IPA-first の出力一貫性

**タイトル:** 全言語の phonemize 出力が IPA トークン列であることをテストで保証する

**説明:**
FR-100 の IPA-first 原則をテストレベルで検証する。各言語に対して最低 2 つのテストケース (基本テスト + エッジケース) が共通テストフィクスチャに含まれ、出力が IPA トークン列であることを検証する。

**受入条件:**
1. 共通テストフィクスチャ (`phoneme_test_cases.json`) に 7 言語 x 2 ケース以上のテストケースが含まれる
2. 各テストケースの `expected_phonemes` が IPA トークン (+ PUA 変換済み文字) で定義されている
3. Python / Rust の CI がこのフィクスチャに対してパスする
4. JS/WASM は JA のみ完全一致、他言語は `"wasm_skip": true` で分離

---

#### NFR-101: 言語別既知制限の明文化と API ドキュメント記載

**タイトル:** 各言語 Phonemizer の既知制限をドキュメントと docstring に明記する

**説明:**
レビュー指摘を受けて、各言語の既知の音韻処理制限を明文化する。これらは Phase 1 では修正対象外 (Won't Fix) であり、将来的な改善候補として記録する。

**言語別既知制限テーブル:**

| 言語 | 制限事項 | 影響 | 現在の動作 | 将来の改善候補 |
|------|---------|------|-----------|--------------|
| ZH | 連続 3 声の再帰サンドヒ未実装 | 3 音節以上の連続 3 声列 (例: "你也好") で 2 番目以降の T3->T2 変換が不正確 | 隣接ペアのみの 1 パス処理 (`_apply_tone_sandhi` で前から順にペア評価) | 右端から左端への再帰適用、または jieba 分詞による語境界検出との統合 |
| KO | g2pk2 未インストール時のフォールバック品質が低い | 連音化 (연음화)、鼻音化 (비음화)、激音化 (격음화)、硬音化 (경음화) が全て未適用 | Hangul 分解のみの素朴な IPA 変換 (warning ログ出力) | フォールバック品質の改善、または g2pk2 の必須化検討 |
| FR | リエゾン (liaison) 未実装 | 語間の子音連結が再現されない (例: "les amis" の /z/ リエゾン) | 各単語を独立に音素化 (`_convert_word` が単語単位) | 語ペアの形態統語的解析による必須/任意リエゾン判定 |
| PT | ブラジルポルトガル語 (BR-PT) 固定、欧州ポルトガル語 (EU-PT) 非対応 | 母音弱化、coda /s/ の実現、/ʁ/ の異音など EU-PT 固有の規則が適用されない | `_apply_br_postprocessing()` で BR 固有規則のみ適用 (t/d 口蓋化, l 母音化, 語末母音弱化) | 方言パラメータの導入 (`dialect="br"` / `"eu"`) |
| ES | Latin American seseo 固定 | カスティーリャ方言の /θ/ (distincion) が再現されない | `c` before `e/i` -> `s`, `z` -> `s` で固定 | 方言パラメータの導入 (`dialect="latam"` / `"castilian"`) |

**受入条件:**
1. 上記 5 言語の既知制限が各 Phonemizer クラスの docstring に英語で記載されている
2. `piper-g2p` パッケージの README (またはドキュメント) に既知制限テーブルが含まれる
3. 各制限に対応する GitHub Issue が作成され、ラベル `enhancement` が付与されている

---

### 3 要求サマリ

| ID | 種別 | タイトル | 親要求 |
|----|------|---------|--------|
| FR-100 | 機能 | 7 言語 Phonemizer の IPA トークン列出力 | FR-G-001, FR-G-006 |
| FR-101 | 機能 | MultilingualPhonemizer (N 言語コードスイッチング) | FR-G-002, FR-G-006 |
| FR-102 | 機能 | カスタム辞書 (JSON v1.0/v2.0) + 入力バリデーション | FR-G-005 |
| FR-103 | 機能 | 言語別 Phonemizer のオプショナル依存 | FR-G-006, NFR-G-001 |
| NFR-100 | 非機能 | IPA-first の出力一貫性テスト | FR-G-004, NFR-G-002 |
| NFR-101 | 非機能 | 言語別既知制限の明文化 | NFR-G-004 |


## Phase 2: Rust crate (`piper-g2p`) 機能要求

> **開始条件**: PyPI `piper-g2p` が月間 **1,000 DL を超過**した時点で着手する。Phase 1 (Python) で需要を検証し、Rust ユーザーへの展開判断を行う。
>
> 技術調査レポート (`g2p-technical-investigation.md` セクション 3) の結果を反映。
> 断ち切る依存は `PhonemeIdMap` と `PiperError` の 2 点のみ。
> `phoneme_converter` は 2 分割: IPA 変換 + エンコード (`tokens_to_ids()`) は piper-g2p、推論リクエスト構築 (`request_builder`) は piper-core に残す。
> PUA エントリは全プラットフォーム 87 で一致済み (差分調査タスク不要)。
>
> **アーキテクチャ原則**: Python Phase 1 と同様の **IPA-first + エンコード分離** を採用する。Phonemizer は IPA トークン列を返し、`tokens_to_ids()` (piper-g2p) が phoneme_id_map でエンコードする。推論リクエスト構築 (`request_builder`) は piper-core の責務。

### FR-200: IPA-first アーキテクチャと request_builder 分離

**説明**: `phoneme_converter.rs` を 2 モジュールに分割し、G2P レイヤーと推論レイヤーの責務を明確に分離する。Python 実装と同様、Phonemizer は IPA トークン列を返し、エンコード (`tokens_to_ids`) は別関数として分離する。piper-core 側の推論リクエスト構築は `request_builder` モジュールにリネームする。

**分割設計**:
```
piper-g2p (G2P レイヤー):
  phonemize_with_prosody() -> (Vec<String>, Vec<Option<ProsodyInfo>>)  # IPA トークン
  tokens_to_ids()          -> Vec<i64>                                  # エンコード
  prosody_to_features()    -> Vec<ProsodyFeature>

piper-core (推論レイヤー):
  request_builder::build_synthesis_request()  # 旧 phoneme_converter の残り
```

**受入条件**:
- `piper-g2p` から `tokens_to_ids()` と `prosody_to_features()` が公開される
- piper-core 側のモジュール名が `phoneme_converter` から `request_builder` にリネームされている
- `request_builder::build_synthesis_request()` は内部で `piper_g2p::tokens_to_ids()` を呼び出す
- 既存の `piper-cli`, `piper-python` のコンパイルがゼロ変更で通る (re-export による)

---

### FR-201: コア型・エラー型と Phonemizer trait

**説明**: `piper-core` への依存を断ち切るため、G2P 固有の型 (`PhonemeIdMap`, `G2pError`) と `Phonemizer` trait を `piper-g2p` crate 内に定義する。

**受入条件**:
- `use piper_g2p::{Phonemizer, ProsodyInfo, ProsodyFeature, PhonemeIdMap, PhonemizerRegistry, G2pError}` でインポートできる
- `Phonemizer` trait は `Send + Sync` を要求する
- エラー型は `G2pError` (6 バリアント: `UnsupportedLanguage`, `Phonemize`, `DictionaryLoad`, `JPreprocessInit`, `LabelParse`, `PhonemeIdNotFound`)
- `piper-core` 側に `impl From<G2pError> for PiperError` が実装されている
- `piper-g2p` は `piper-core` の型に一切依存しない

---

### FR-202: 7 言語 Phonemizer + PUA トークンマップ + カスタム辞書

**説明**: 現行の 7 言語 Phonemizer、固定 PUA マッピングテーブル (87 エントリ)、カスタム辞書を全て `piper-g2p` crate に含める。

| 言語 | 構造体 | feature flag | 外部依存 |
|------|--------|-------------|---------|
| JA | `JapanesePhonemizer` | `japanese` | `jpreprocess >=0.9, <0.14` (MIT) |
| EN | `EnglishPhonemizer` | (不要) | なし (CMU 辞書 JSON 組み込み) |
| ZH | `ChinesePhonemizer` | (不要) | なし |
| KO | `KoreanPhonemizer` | (不要) | なし |
| ES | `SpanishPhonemizer` | (不要) | なし |
| FR | `FrenchPhonemizer` | (不要) | なし |
| PT | `PortuguesePhonemizer` | (不要) | なし |

**受入条件**:
- 全 Phonemizer が `Phonemizer` trait を実装し、エラー型は `G2pError`
- JA: `#[cfg(feature = "japanese")]` で条件付きコンパイル。栗原法韻律マーカー、N 音素変異、PUA マッピングが動作する
- EN: ARPAbet-to-IPA 変換、機能語ストレス除去 (97 語)、OOV 形態素フォールバック (-ing, -ed, -s, -er, -ly, -est) が動作する
- PUA トークンマップ: `token_to_pua()`, `FIXED_PUA_MAP` (87 エントリ)、Python 実装と全エントリ一致
- カスタム辞書: JSON v1.0/v2.0 ロード、longest-match-first、case-sensitive/insensitive マッチ

---

### FR-203: jpreprocess vs pyopenjtalk 互換性テスト

**説明**: jpreprocess (Rust) と pyopenjtalk (Python) の fullcontext label 出力の互換性を検証するテストスイートを作成する。両ライブラリは同一の OpenJTalk アルゴリズムを異なる言語で再実装しているが、互換性は公式に保証されていない。

**受入条件**:
- 共通テストフィクスチャ (`tests/fixtures/g2p/jpreprocess_compat.json`) に以下を含む:
  - 基本テキスト 10 件以上 (平仮名、漢字、カタカナ、記号混在)
  - 各テキストに対する期待 phoneme トークン列
  - N 音素変異のバリデーション (N_m, N_n, N_ng, N_uvular)
  - 韻律マーカー (Kurihara `]`, `#`, `[`) の位置
- Python (`pyopenjtalk`) と Rust (`jpreprocess`) で同一テキストの phoneme 出力を比較する CI ジョブ
- 既知の差異は `known_differences` セクションに文書化し、テストで `#[should_panic]` / `xfail` マークする
- A1/A2/A3 prosody 値が同一テキストで +-1 以内の一致を示す

---

### FR-204: MultilingualPhonemizer と言語検出

**説明**: Unicode 言語検出 (`UnicodeLanguageDetector`) + セグメント分割 (`segment_text()`) + 言語別 Phonemizer 委譲の多言語メタ Phonemizer。

**受入条件**:
- CJK 曖昧性解消 (仮名コンテキストで漢字を JA 判定) が Python 実装と同一の結果を返す
- `default_post_process_ids()` が EN/ZH/KO/ES/PT/FR で共通利用される
- `segment_text()` が公開関数として利用可能

---

### 既知制限 (Phase 2)

| ID | 制限事項 | 影響 | 回避策 |
|----|---------|------|--------|
| KL-200 | **英語 OOV が無音になる**: `EnglishPhonemizer` は CMU 辞書 + 形態素フォールバック (-ing, -ed 等) に依存しており、辞書に存在しない固有名詞・新語は phoneme ID が生成されず無音になる | 英語の固有名詞・新造語が発話されない | カスタム辞書で個別登録。将来的には letter-to-phoneme ニューラルモデルの統合を検討 |
| KL-201 | **jpreprocess vs pyopenjtalk の出力差異**: 同一アルゴリズムの異言語実装だが、fullcontext label の細部 (特に記号・数字の読み) で差異が生じる可能性がある | JA の phoneme 出力が Python/Rust で異なるケースがある | FR-203 の互換性テストで差異を検出・文書化。重大な差異は issue として追跡 |
| KL-202 | **naist-jdic バンドルによるバイナリサイズ**: `naist-jdic` feature 有効時、辞書データ (~30MB) が crate に組み込まれる | バイナリサイズが大きくなる | `default = ["multilingual"]` にし、`naist-jdic` は opt-in で使用。外部辞書パス指定 (`new_with_dict()`) も提供 |

---

## Phase 2: Rust crate 非機能要求

### NFR-200: feature flags と依存構成

**説明**: 言語別の feature flags で外部依存を制御する。`default` features を軽量に保ち、naist-jdic は opt-in とする。

**Cargo.toml 設計**:
```toml
[features]
default = ["multilingual"]
japanese = ["dep:jpreprocess"]
naist-jdic = ["japanese", "jpreprocess/naist-jdic"]
multilingual = ["japanese", "english", "chinese", "spanish", "french", "portuguese", "korean"]
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
jpreprocess = { version = ">=0.9, <0.14", optional = true }
```

**受入条件**:
- `default = ["multilingual"]`: naist-jdic を含まず全言語有効。JA は外部辞書パス指定 (`new_with_dict()`) で動作
- `naist-jdic` は opt-in: `cargo add piper-g2p --features naist-jdic` で辞書バンドル
- `jpreprocess` バージョン: `>=0.9, <0.14` (現在のロック: 0.9.1。将来の 0.13.x までの互換を許容)
- 全依存が MIT / Apache-2.0 / BSD-3-Clause (GPL 汚染ゼロ)
- crate 構成: workspace `members` に追加、`piper-core` が path 依存

---

### NFR-201: スレッド安全性とパフォーマンス

**説明**: 全ての Phonemizer 実装が `Send + Sync` を満たし、TTS パイプラインのボトルネックにならない処理速度を維持する。

**受入条件**:
- `Phonemizer` trait bound が `Send + Sync` を含む
- コンパイル時に全実装型が `Send + Sync` を満たすことを検証するテストを含む
- JA/EN 100 文字テキストの `phonemize_with_prosody()` が 10ms 以内

---

### NFR-202: MSRV と piper-core 後方互換性

**説明**: workspace の MSRV と整合し、`piper-core` の既存公開 API を維持する。

**受入条件**:
- `Cargo.toml` に `rust-version = "1.88"` を記述 (workspace 設定に準拠)
- CI で MSRV でのビルド検証を実施
- `piper-core` の `src/phonemize/` モジュールが `pub use piper_g2p::*;` で re-export
- `piper-core` を利用する既存コード (`piper-cli`, `piper-python`) のコンパイルがゼロ変更で通る

---

### NFR-203: テストとドキュメント

**説明**: 独立 crate として十分なテストカバレッジと API ドキュメントを持つ。

**受入条件 (テスト)**:
- 各言語 Phonemizer の基本入出力テスト (最低 3 ケース/言語)
- `MultilingualPhonemizer` のコードスイッチングテスト (JA+EN+ZH 混在)
- PUA マッピングの Python 実装との 87 エントリ完全一致テスト
- jpreprocess vs pyopenjtalk 互換性テスト (FR-203)
- CI で 3 OS (Linux, macOS, Windows) 実行

**受入条件 (ドキュメント)**:
- `#![deny(missing_docs)]` を `lib.rs` に設定
- 全 `pub` アイテムに doc comment が付与されている
- crate レベルの doc comment にクイックスタート例を含める

---

**(Phase 2 の要求はここまで。Phase 2 合計: FR 5 件 + NFR 4 件 = 9 件)**

---

## Phase 3: JS/WASM npm パッケージ (`@piper-plus/g2p`) 機能要求

> **開始条件**: 以下のいずれかを満たした時点で着手する:
> 1. PyPI `piper-g2p` + crates.io `piper-g2p` の合計月間 DL が **2,000 を超過**
> 2. ブラウザ TTS ユースケースからの Issue/Feature Request が **3 件以上**蓄積
>
> **推定工数:** 3-4 週
> **技術的前提:** G2P レイヤーは `onnxruntime-web` に依存しない (技術調査で確認済み)。主要作業は OpenJTalk WASM 初期化の DI 化と `SimpleUnifiedPhonemizer` の分離である。

### FR-300: G2P 統一 API

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

### FR-301: 日本語 G2P + Prosody 抽出

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

### FR-302: 辞書ローダー (DictLoader)

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

**(Phase 3 の機能要求はここまで。旧 FR-W-004 (言語自動検出) と FR-W-005 (カスタム辞書・EN G2P・フォールバック) は FR-300 の受入条件に統合済み。)**

---

## Phase 3: JS/WASM npm パッケージ 非機能要求

### NFR-300: バンドルサイズ・パッケージ構成

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

### NFR-301: ブラウザ互換性・ランタイム

**説明:** 主要モダンブラウザおよび Node.js で動作すること。

**受入条件:**
- Chrome 80+, Firefox 113+, Safari 16.4+ で動作する
- Node.js 18+ でも動作する (WASM 含む)
- `DecompressionStream` API が利用可能 (辞書 tar.gz 解凍)
- `crypto.subtle` が利用可能 (SHA-256 検証、HTTPS 環境)
- `indexedDB` が利用可能 (辞書キャッシュ)

---

### NFR-302: 既存 piper-plus パッケージとの互換性

**説明:** 既存の `piper-plus` npm パッケージが `@piper-plus/g2p` を内部依存として利用でき、公開 API に破壊的変更がないこと。

**受入条件:**
- `piper-plus` の `package.json` に `"@piper-plus/g2p": "^1.0.0"` が dependencies として追加される
- `piper-plus` の `SimpleUnifiedPhonemizer` が内部で `@piper-plus/g2p` の `G2P` クラスに委譲する
- 既存の `piper-plus` ユーザー API (`PiperPlus.initialize()`, `PiperPlus.synthesize()`) に破壊的変更がない
- 既存 subpath export `piper-plus/phonemizer` が `@piper-plus/g2p` への re-export として維持される

---

**(Phase 3 の非機能要求はここまで。旧 NFR-W-004 (TypeScript 型定義・テスト) は NFR-300 (型定義は `types/` に含む) と NFR-302 (テストは CI に統合) に統合済み。Phase 3 合計: FR 3 件 + NFR 3 件 = 6 件)**

---

## リリース戦略

### 12.1 フェーズ定義とタイムライン

```
Phase 0: パッケージ名予約                    ← 即時
Phase 1: Python (`piper-g2p` PyPI)           ← 最優先、2-3 週
    ↓ 需要検証: PyPI 月間 1,000 DL 超過
Phase 2: Rust (`piper-g2p` crates.io)        ← 条件付き、2-3 週
    ↓ 需要検証: PyPI+crates.io 合計 2,000 DL 超過 or Issue 3 件以上
Phase 3: JS/WASM (`@piper-plus/g2p` npm)     ← 条件付き、3-4 週
```

#### Phase 0: パッケージ名予約 (即時)

| パッケージ名 | レジストリ | 状態 |
|-------------|-----------|------|
| `piper-g2p` | PyPI | 予約する (空パッケージ publish) |
| `piper-g2p` | crates.io | 予約する (`cargo publish` with placeholder) |
| `@piper-plus/g2p` | npm | 予約する (org scope で `npm init --scope=@piper-plus`) |

**注意**: crates.io はスクワッティング対策があるため、最低限の `lib.rs` を含む crate を公開する。PyPI / npm も同様に description + README のみの placeholder をパブリッシュする。

#### Phase 1: Python (最優先)

| 項目 | 内容 |
|------|------|
| **スコープ** | `piper-g2p` (PyPI) |
| **推定工数** | 2-3 週 |
| **対象要求** | FR-P-001~005, NFR-P-001~004, FR-G-001~007, NFR-G-001~004, FR-I-001, FR-I-005 (Python 分) |
| **理由** | TTS 開発者の大半は Python ユーザー。eSpeak-ng 置き換え需要が最も高い |

**Phase 1 実施タスク:**

| # | タスク | 備考 |
|---|--------|------|
| 1 | Python パッケージ構造の作成 (`piper_g2p/`) | 22 ファイル移動 (技術調査 2.1) |
| 2 | `pyproject.toml` の整備 (言語別 optional deps) | 技術調査 2.4 の設計案ベース。ビルドは uv ベース |
| 3 | `piper_train.phonemize` 互換シム作成 | 6 ファイルで re-export が必要 |
| 4 | `JapanesePhonemizer` に `custom_dict` コンストラクタ引数追加 | 現状は関数レベルのみ |
| 5 | `CustomDictionary` のデフォルト辞書パスを汎用化 | パッケージ内 `data/dictionaries/` にバンドル |
| 6 | 共通テストフィクスチャ JSON の作成 | 技術調査 6.1-6.3 のスキーマ・ケース |
| 7 | CI ワークフロー (`g2p-python-ci.yml`) の構築 | uv ベース。`uv sync`, `uv run pytest`, `uv build`, `uv publish` |
| 8 | API ドキュメントの作成 | Python docstring |

**Phase 1 マイルストーン:**

| バージョン | 内容 | 公開先 |
|-----------|------|--------|
| v0.1.0 | 内部リリース。piper_train からの互換確認、既存テスト全パス | - |
| v0.2.0 | ベータ公開。外部ユーザーからのフィードバック収集 | PyPI |
| v1.0.0 | 安定版リリース。API 凍結 | PyPI |

**Phase 1 スコープ外:**
- Rust crate 分離 (Phase 2: 需要検証後)
- JS/WASM パッケージ分離 (Phase 3: 需要検証後)
- インライン音素記法 `[[ ... ]]` (Phase 2 以降のタスク)
- TTS フレームワーク統合ガイド (v1.0.0 リリース後)

#### Phase 2: Rust (需要検証後)

| 項目 | 内容 |
|------|------|
| **スコープ** | `piper-g2p` (crates.io) |
| **推定工数** | 2-3 週 |
| **対象要求** | FR-200~204, NFR-200~203, FR-I-002, FR-I-005 (Rust 分) |
| **開始条件** | PyPI `piper-g2p` 月間 **1,000 DL 超過** |
| **理由** | Rust TTS エコシステムは Python より小規模。需要確認後に投資判断 |

**Phase 2 実施タスク:**

| # | タスク | 備考 |
|---|--------|------|
| 1 | Rust crate `piper-g2p` の作成 | 12 ファイル移動 (技術調査 3.1) |
| 2 | `PiperError` -> `G2pError`, `PhonemeIdMap` 型エイリアス | 依存断ち切り (技術調査 3.2) |
| 3 | `phoneme_converter` -> `request_builder` リネーム + 2 分割 | FR-200 |
| 4 | jpreprocess vs pyopenjtalk 互換性テスト作成 | FR-203 |
| 5 | `piper-core` からの re-export 設定 | 後方互換性維持 |
| 6 | CI ワークフロー (`g2p-rust-ci.yml`) の構築 | 3 OS x stable/beta |

**Phase 2 マイルストーン:**

| バージョン | 内容 | 公開先 |
|-----------|------|--------|
| v0.1.0 | ベータ公開。piper-core からの互換確認 | crates.io |
| v1.0.0 | 安定版リリース | crates.io |

#### Phase 3: JS/WASM (需要検証後)

| 項目 | 内容 |
|------|------|
| **スコープ** | `@piper-plus/g2p` (npm) |
| **推定工数** | 3-4 週 |
| **対象要求** | FR-300~302, NFR-300~302, FR-I-003, FR-I-005 (JS/WASM 分) |
| **開始条件** | PyPI+crates.io 合計月間 **2,000 DL 超過** or ブラウザ TTS Issue **3 件以上** |
| **理由** | 推論パイプラインとの結合度が高く工数大。ブラウザ TTS 市場の成長に合わせて実施 |

**Phase 3 実施タスク:**

| # | タスク |
|---|--------|
| 1 | `SimpleUnifiedPhonemizer` の分離リファクタリング |
| 2 | OpenJTalk WASM の DI 化 (コンストラクタ注入) |
| 3 | `DictManager` -> `DictLoader` の分離 |
| 4 | `phonemizeWithProsody()` API の追加 (A1/A2/A3 抽出) |
| 5 | TypeScript 型定義の整備 |
| 6 | npm パブリッシュ設定 + CI ワークフロー |

**Phase 3 マイルストーン:**

| バージョン | 内容 | 公開先 |
|-----------|------|--------|
| v0.1.0 | npm ベータ公開 | npm |
| v1.0.0 | 安定版リリース | npm |

---

### 12.2 バージョニング戦略

全パッケージで **SemVer 2.0.0** を採用する。**MAJOR バージョンの全パッケージ同期は廃止**し、PUA compat バージョンで互換性を管理する。

#### PUA compat バージョン

PUA マッピングテーブルの互換性は **MAJOR バージョンではなく PUA compat バージョン** で管理する。各パッケージは独立してバージョンを進行させ、PUA compat バージョンが同一であれば互換性を保証する。

```
piper-g2p (Python) v1.2.0  [pua-compat: 1]
piper-g2p (Rust)   v1.0.3  [pua-compat: 1]  ← 同一 PUA compat = 互換
@piper-plus/g2p    v1.1.0  [pua-compat: 1]  ← 同一 PUA compat = 互換
```

| バージョン変更 | 条件 | 例 |
|--------------|------|-----|
| **MAJOR** (x.0.0) | API の破壊的変更 | `phonemize()` シグネチャ変更 |
| **MINOR** (0.x.0) | 新言語追加、新機能追加、PUA エントリ追加 | Swedish 言語追加、PUA +9 エントリ |
| **PATCH** (0.0.x) | バグ修正、パフォーマンス改善 | 声調サンドヒのバグ修正 |

**PUA compat バージョンのルール:**
- PUA テーブルのエントリ **削除・変更** → PUA compat バージョンを +1 (全パッケージで同時)
- PUA テーブルのエントリ **追加** → MINOR バージョン (既存モデルとの後方互換あり。新エントリは新モデルでのみ使用)
- 各パッケージの `pyproject.toml` / `Cargo.toml` / `package.json` に `pua_compat_version` メタデータを記載

**利点**: Python が活発にリリースされ Rust がゆっくり追従するシナリオで、不要な MAJOR bump を回避できる。

---

### 12.3 CI/CD

#### Python CI (`g2p-python-ci.yml`) -- uv ベース

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv run ruff check src/python/g2p/
      - run: uv run ruff format --check src/python/g2p/

  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ['3.11', '3.12', '3.13']
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --all-extras
        working-directory: src/python/g2p
      - run: uv run pytest tests/ -v --cov=piper_g2p
        working-directory: src/python/g2p

  publish:
    if: startsWith(github.ref, 'refs/tags/python-g2p-v')
    needs: [lint, test]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v6
      - run: uv build
        working-directory: src/python/g2p
      - run: uv publish
        working-directory: src/python/g2p
```

**タグトリガー:** `python-g2p-v*`

#### Rust CI (`g2p-rust-ci.yml`)

- `cargo fmt -- --check`, `cargo clippy --all-features -- -D warnings`
- `cargo test --all-features` (3 OS x stable)
- MSRV (1.88) でのビルド検証
- `cargo publish -p piper-g2p` (タグトリガー: `rust-g2p-v*`)

#### JS/WASM CI (`g2p-wasm-ci.yml`)

- `node --test` (3 OS x Node 18/20/22)
- パッケージサイズ検証 (< 1MB、辞書除く)
- `npm publish --provenance --access public` (タグトリガー: `wasm-g2p-v*`)

#### 共通テストフィクスチャ

全 CI で `tests/fixtures/g2p/phoneme_test_cases.json` を参照し、クロスプラットフォーム互換性を検証。

---

### 12.4 パッケージ名の予約

Phase 0 で以下のパッケージ名を即座に予約する。各レジストリの名前スクワッティングポリシーに準拠し、最低限のメタデータ (description, license, README) を含む placeholder をパブリッシュする。

| レジストリ | パッケージ名 | 予約方法 | 注意事項 |
|-----------|------------|---------|---------|
| PyPI | `piper-g2p` | `uv build && uv publish` (v0.0.1 placeholder) | PyPI は名前予約の明示的手段がないため空パッケージを publish |
| crates.io | `piper-g2p` | `cargo publish` (v0.0.1 placeholder) | crates.io はスクワッティング対策あり。最低限の `lib.rs` + `Cargo.toml` が必要 |
| npm | `@piper-plus/g2p` | `npm publish --access public` (v0.0.1 placeholder) | `@piper-plus` org scope で管理。org 管理者権限が必要 |

---

## 要求トレーサビリティ

### 統合・整理マップ

以下は旧要求 ID と新要求 ID の対応を示す。重複する要求は統合し、技術調査の結果とレビュー指摘を反映して更新した。

| 旧 ID | 新 ID | 変更内容 |
|--------|-------|---------|
| FR-G-001 (統一インターフェース) | **FR-G-001** | C# 列を除外。JS/WASM 列を追加 |
| FR-G-002 (言語レジストリ) + FR-G-003 (言語自動検出) | **FR-G-002** | 統合。レジストリと自動検出は密結合のため一体化 |
| FR-G-004 (PUA マッピング) | **FR-G-003** | PUA 差分が存在しないことを反映 (87 エントリ一致確認済み)。C# 参照を除外 |
| FR-G-005 (音素体系互換性) | **FR-G-004** | JS/WASM の例外を明文化 |
| FR-G-006 (カスタム辞書) | **FR-G-005** | TSV サポートを除外 (C# 固有)。Python の辞書パス汎用化を追加 |
| FR-G-008 (MultilingualPhonemizer) + FR-G-009 (言語別 Phonemizer) | **FR-G-006** | 統合。個別言語と多言語統合は同一要求として管理 |
| FR-G-007 (ProsodyInfo) | **FR-G-007** | JS/WASM の Phase 3 追加を明記 |
| FR-G-010 (インライン音素記法) | Phase 2 以降タスク | 要求から降格 |
| NFR-G-001 (ライセンス) + NFR-G-002 (ゼロ C/C++ ビルド依存) | **NFR-G-001** | 統合。両方ともデプロイ容易性の要件 |
| NFR-G-003 (テスト網羅) | **NFR-G-002** | テストフィクスチャスキーマ・ケース一覧を技術調査から統合 |
| NFR-G-004 (パフォーマンス) | **NFR-G-003** | C# の要件を除外 |
| NFR-G-005 (API ドキュメント) | **NFR-G-004** | C# の要件を除外 |
| FR-I-001 (Python 互換性) | **FR-I-001** | 互換シム実装と対象ファイル一覧を技術調査から追加 |
| FR-I-002 (Rust crate 分離) | **FR-I-002** | 依存断ち切り詳細を技術調査から追加 |
| FR-I-003 (C# 分離) | **削除** | DotNetG2P が独立パッケージとして公開済みのため対象外 |
| FR-I-004 (JS/WASM 分離) | **FR-I-003** | Phase 3 に割り当て |
| FR-I-005 (TTS 統合ガイド) | **FR-I-004** | Phase 1 v1.0.0 リリース後に割り当て |
| FR-I-006 (CI/CD) | **FR-I-005** | C# ワークフローを除外。技術調査 7.1-7.7 の設計を統合 |
| FR-R-001~006 (Rust 機能) | **FR-200~204** | Phase 2 に再割り当て。開始条件追加 (PyPI 月間 1,000 DL)。phoneme_converter -> request_builder リネーム反映。FR-203 (jpreprocess 互換性テスト) 新規追加 |
| NFR-R-001~005 (Rust 非機能) | **NFR-200~203** | Phase 2 に再割り当て。`default = ["multilingual"]` に変更 (naist-jdic opt-in)。jpreprocess `>=0.9, <0.14` に拡大。既知制限テーブル追加 |
| FR-W-001~005 (JS/WASM 機能) | **FR-300~302** | Phase 3 に再割り当て。開始条件追加。FR-W-004, FR-W-005 を FR-300 に統合 |
| NFR-W-001~004 (JS/WASM 非機能) | **NFR-300~302** | Phase 3 に再割り当て。NFR-W-004 を NFR-300, NFR-302 に統合 |

### 要求数サマリ

| カテゴリ | 旧 | 新 | 削減理由 |
|---------|-----|-----|---------|
| 共通機能要求 (FR-G) | 10 | 7 | 統合 3 件 (レジストリ+自動検出, Multilingual+言語別, インライン音素->タスク降格) |
| 共通非機能要求 (NFR-G) | 5 | 4 | 統合 1 件 (ライセンス+ビルド依存) |
| 統合要求 (FR-I) | 6 | 5 | 削除 1 件 (C# 分離) |
| Phase 2 Rust (FR-200~) | 6 FR + 5 NFR | 5 FR + 4 NFR | 統合 (コア型+trait, 言語+PUA+辞書)。互換性テスト新規追加 |
| Phase 3 JS/WASM (FR-300~) | 5 FR + 4 NFR | 3 FR + 3 NFR | 統合 (言語検出+辞書+EN G2P -> FR-300 に統合、型定義+テスト -> NFR に統合) |
| **Phase 2+3 合計** | **20** | **15** | 要求上限 15 件を遵守 |

---
