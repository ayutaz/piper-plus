# FR-01 / FR-02 要件定義書 -- NST辞書ルックアップ & SAMPA→IPA変換ツール

## 文書情報

| 項目 | 値 |
|------|-----|
| 作成日 | 2026-03-30 |
| 対象機能 | FR-01 (NST辞書ルックアップ), FR-02 (SAMPA→IPA変換ツール) |
| 上位文書 | `swedish-requirements.md` (要求定義), `nst-dictionary-integration.md` (辞書設計) |
| 関連設計 | `swedish-g2p-design.md` Section 9 |
| Issue | #296 |

---

## 目次

1. [FR-01: NST辞書ルックアップ](#fr-01-nst辞書ルックアップ)
   - 1.1 [概要](#11-概要)
   - 1.2 [データフロー](#12-データフロー)
   - 1.3 [辞書ファイルフォーマット仕様](#13-辞書ファイルフォーマット仕様)
   - 1.4 [単語正規化アルゴリズム](#14-単語正規化アルゴリズム)
   - 1.5 [ルックアップアルゴリズム](#15-ルックアップアルゴリズム)
   - 1.6 [複数発音の取り扱い](#16-複数発音の取り扱い)
   - 1.7 [メモリレイアウトとロード戦略](#17-メモリレイアウトとロード戦略)
   - 1.8 [エラーハンドリング](#18-エラーハンドリング)
   - 1.9 [API仕様](#19-api仕様)
   - 1.10 [設定仕様](#110-設定仕様)
   - 1.11 [テストケース](#111-テストケース)
2. [FR-02: SAMPA→IPA変換ツール](#fr-02-sampaipa変換ツール)
   - 2.1 [概要](#21-概要)
   - 2.2 [SAMPA→IPA完全マッピングテーブル](#22-sampaipa完全マッピングテーブル)
   - 2.3 [パースアルゴリズム](#23-パースアルゴリズム)
   - 2.4 [出力フォーマット仕様](#24-出力フォーマット仕様)
   - 2.5 [フィルタリング規則](#25-フィルタリング規則)
   - 2.6 [CLIインターフェース仕様](#26-cliインターフェース仕様)
   - 2.7 [検証ステップ](#27-検証ステップ)
   - 2.8 [エッジケース処理](#28-エッジケース処理)
   - 2.9 [テストケース](#29-テストケース)

---

# FR-01: NST辞書ルックアップ

## 1.1 概要

NST辞書 (822K語, CC0ライセンス) を事前にSAMPA→IPA変換した JSON 辞書ファイルを読み込み、入力単語に対応するIPA発音文字列を返すルックアップ機構を提供する。`SwedishPhonemizer` 内部の最優先ステージとして機能し、辞書ヒット時は rule-based G2P をバイパスする。

| 項目 | 値 |
|------|-----|
| 成果物パス | `src/python/piper_train/phonemize/swedish.py` 内 |
| 辞書ファイルパス | ランタイム指定 (デフォルト: なし / 環境変数 / コンストラクタ引数) |
| 辞書フォーマット | JSON (`dict[str, str]`), gzip 圧縮対応 |
| 辞書ティア | Core (~238K語, ~2.3 MB gzip) をデフォルト |
| 受入基準 | 辞書内の語に対して100%正確なIPA出力 |

---

## 1.2 データフロー

```
[1. ファイルロード]
    辞書ファイルパスを解決
    → .json.gz または .json を検出
    → ファイルをバイナリ読み込み
    |
    v
[2. パース]
    gzip 展開 (拡張子が .gz の場合)
    → UTF-8 デコード
    → JSON デシリアライズ → Python dict
    |
    v
[3. 正規化]
    全キーが小文字であることを検証 (変換ツール側で保証済み)
    → キーの Unicode NFC 正規化を確認
    |
    v
[4. 格納]
    self._dict: dict[str, str] に代入
    → メモリ上にフラット HashMap として保持
    |
    v
[5. ルックアップ (単語入力時)]
    入力単語を正規化 (小文字, 句読点除去, NFC)
    → self._dict.get(normalized_word)
    → ヒット → IPA 文字列を返却
    → ミス → 複合語分割を試行
    → ミス → None を返却 (rule-based フォールバックへ)
    |
    v
[6. 返却]
    IPA 文字列 (ストレスマーカー ˈ/ˌ 含む)
    → SwedishPhonemizer が音素トークンリストに分割
    → PUA マッピング適用
    → phoneme_ids 生成
```

### データフロー図 (詳細)

```
dict_path (str)
    |
    +--- ファイル存在確認 ----[FileNotFoundError]
    |
    +--- 拡張子判定
    |     .json.gz → gzip.open("rt", encoding="utf-8")
    |     .json    → open("r", encoding="utf-8")
    |
    +--- json.load(fp) ----[json.JSONDecodeError]
    |
    +--- 型検証 isinstance(data, dict) ----[TypeError]
    |
    +--- self._dict = data   # dict[str, str]
    |
    |    (ルックアップ時)
    |
    +--- normalize_for_lookup(word)
    |     → word.strip(".,;:!?\"'()[]{}—–…")
    |     → word.lower()
    |     → unicodedata.normalize("NFC", word)
    |
    +--- self._dict.get(normalized) → str | None
    |     ヒット → return IPA文字列
    |
    +--- (ミス) compound_decompose(normalized)
    |     → 分割点を右から左へ走査
    |     → 結合形素 ("s", "e", "o") を考慮
    |     → 両パーツが辞書内 → IPA結合 (主+副ストレス)
    |     → ヒット → return 結合IPA文字列
    |
    +--- (ミス) return None  →  rule-based G2P へ委譲
```

---

## 1.3 辞書ファイルフォーマット仕様

### 1.3.1 JSON スキーマ

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Piper-Plus Swedish IPA Dictionary",
  "description": "NST辞書をSAMPA→IPA変換した単語→発音マッピング",
  "type": "object",
  "additionalProperties": {
    "type": "string",
    "description": "IPA発音文字列 (ストレスマーカー含む)",
    "pattern": "^[\\u0020-\\u007E\\u00C0-\\u024F\\u0250-\\u02FF\\u0300-\\u036F]*$"
  },
  "propertyNames": {
    "type": "string",
    "description": "小文字正規化済みのスウェーデン語単語",
    "pattern": "^[a-zåäö\\u00C0-\\u024F'-]+$"
  }
}
```

### 1.3.2 ファイル例

```json
{
  "barn": "ˈbɑːɳ",
  "sjukhus": "ˈɧʉːkˌhʉːs",
  "station": "staˈɧuːn",
  "sked": "ˈɧeːd",
  "skola": "ˈskuːla",
  "flicka": "ˈflɪka",
  "kind": "ˈɕɪnd",
  "bord": "ˈbuːɖ",
  "karl": "ˈkɑːɭ",
  "fors": "ˈfɔʂ"
}
```

### 1.3.3 ファイル命名規則

| ティア | ファイル名 | サイズ (gzip) | エントリ数 |
|--------|-----------|-------------|----------|
| Core | `sv_lexicon_core.json.gz` | ~2.3 MB | ~238,000 |
| Full | `sv_lexicon_full.json.gz` | ~10.6 MB | ~821,000 |

### 1.3.4 キーの制約

- 全て小文字 (NST原本は全大文字だが、変換ツールで小文字化)
- Unicode NFC 正規化済み
- スウェーデン語固有文字 (å, ä, ö) を含む
- ハイフン含有語を許容 (例: "t-shirt")
- アポストロフィ含有語を許容 (例: "o'clock" は存在しないが将来のため)

### 1.3.5 値の制約

- IPA文字列 (Unicode)
- ストレスマーカー: ˈ (U+02C8, 主ストレス), ˌ (U+02CC, 副ストレス)
- 空文字列は許容しない (最低1音素)
- 長母音は2文字表現 (例: "ɑː", "eː") -- PUA変換前の状態

---

## 1.4 単語正規化アルゴリズム

### 1.4.1 仕様

| ステップ | 処理 | 入力例 | 出力例 |
|---------|------|--------|--------|
| 1 | 先頭・末尾の句読点除去 | `"barn,"` | `"barn"` |
| 2 | 小文字変換 | `"Barn"` | `"barn"` |
| 3 | Unicode NFC 正規化 | `"a\u030a"` (合成å) | `"å"` (NFC) |
| 4 | 複数空白の正規化 | (単語単位のため不要) | -- |

### 1.4.2 擬似コード

```
FUNCTION normalize_for_lookup(word: str) -> str:
    # ステップ1: 句読点除去
    STRIP_CHARS = ".,;:!?\"'()[]{}—–…«»"
    word = word.strip(STRIP_CHARS)

    # ステップ2: 空文字チェック
    IF word == "":
        RETURN ""

    # ステップ3: 小文字変換
    word = word.lower()

    # ステップ4: Unicode NFC正規化
    # å (U+00E5) と a + combining ring above (U+0061 U+030A) を統一
    # ä (U+00E4) と a + combining diaeresis (U+0061 U+0308) を統一
    # ö (U+00F6) と o + combining diaeresis (U+006F U+0308) を統一
    word = unicodedata.normalize("NFC", word)

    RETURN word
```

### 1.4.3 句読点除去対象文字

```python
_STRIP_PUNCTUATION = frozenset(".,;:!?\"'()[]{}—–…«»‹›„""''")
```

**注意**: ハイフン (`-`) は除去対象に**含めない**。スウェーデン語にはハイフン含有語 (例: "t-shirt") が辞書に存在するため。

### 1.4.4 å/ä/ö の取り扱い

スウェーデン語固有の文字 å, ä, ö は正規化で**保持**する。NFCで正規化することにより、以下の合成形と事前合成形の差異を吸収する:

| 事前合成形 (NFC) | 合成形 (NFD) | 処理 |
|:---------------:|:----------:|:----:|
| å (U+00E5) | a + ̊ (U+0061 U+030A) | NFC で統一 |
| ä (U+00E4) | a + ̈ (U+0061 U+0308) | NFC で統一 |
| ö (U+00F6) | o + ̈ (U+006F U+0308) | NFC で統一 |

### 1.4.5 ハイフン含有語の処理

1. まず元のハイフン含有形でルックアップ: `"t-shirt"` → 辞書検索
2. ヒットしない場合、ハイフンで分割して各パーツを個別ルックアップ
3. 全パーツがヒットした場合、IPA を結合して返却 (第2パーツ以降に副ストレス)

### 1.4.6 エラー条件

| 条件 | 処理 |
|------|------|
| 入力が空文字 | `""` を返却 (ルックアップでミス扱い) |
| 入力が数字のみ | 正規化後そのまま返却 (辞書ミス → rule-based へ) |
| 入力に制御文字 | 除去せずそのまま (辞書ミス → rule-based へ) |

### 1.4.7 テストケース

| # | 入力 | 期待出力 | 説明 |
|---|------|---------|------|
| N-1 | `"Barn"` | `"barn"` | 大文字→小文字 |
| N-2 | `"barn,"` | `"barn"` | 末尾句読点除去 |
| N-3 | `"\"barn\""` | `"barn"` | 引用符除去 |
| N-4 | `"SJUKHUS"` | `"sjukhus"` | 全大文字→小文字 |
| N-5 | `"ÅKA"` | `"åka"` | スウェーデン語固有文字 |
| N-6 | `""` | `""` | 空入力 |
| N-7 | `"!!!"` | `""` | 句読点のみ |
| N-8 | `"t-shirt"` | `"t-shirt"` | ハイフン保持 |
| N-9 | `"a\u030aka"` (NFD) | `"åka"` (NFC) | 合成形→事前合成形 |
| N-10 | `"  barn  "` | `"barn"` | 前後空白は strip_chars で除去 |

---

## 1.5 ルックアップアルゴリズム

### 1.5.1 処理フロー

```
入力: word (正規化前の単語文字列)
出力: str | None (IPA文字列 or None)

FUNCTION lookup(word: str) -> str | None:
    # Phase 1: 正規化
    normalized = normalize_for_lookup(word)
    IF normalized == "":
        RETURN None

    # Phase 2: 完全一致ルックアップ
    result = self._dict.get(normalized)
    IF result IS NOT None:
        RETURN result

    # Phase 3: 複合語分割試行
    result = self._try_compound_decomposition(normalized)
    IF result IS NOT None:
        RETURN result

    # Phase 4: ミス
    RETURN None
```

### 1.5.2 完全一致ルックアップ

```
FUNCTION exact_lookup(normalized_word: str) -> str | None:
    RETURN self._dict.get(normalized_word, None)
```

- 計算量: O(1) 平均 (Python dict のハッシュテーブル)
- 辞書キーは小文字正規化済み
- 大文字小文字を区別しない (正規化ステップで吸収)

### 1.5.3 複合語分割アルゴリズム

スウェーデン語は空白なしで複合語を形成する。辞書にない複合語を分割して各パーツを個別にルックアップする。

```
FUNCTION try_compound_decomposition(word: str) -> str | None:
    # 最小パーツ長: 3文字 (1-2文字の単語は構成要素として不十分)
    MIN_PART_LENGTH = 3

    # 結合形素 (Linking morpheme)
    LINKING_MORPHEMES = ["s", "e", "o", ""]

    # 分割点を右から左へ走査 (右側=主辞が長い方が望ましい)
    FOR split_pos FROM (len(word) - MIN_PART_LENGTH) DOWNTO MIN_PART_LENGTH:
        right_part = word[split_pos:]

        # 右パーツを辞書で検索
        right_ipa = self._dict.get(right_part)
        IF right_ipa IS None:
            CONTINUE

        # 左パーツ + 結合形素のパターンを試行
        left_candidate = word[:split_pos]
        FOR link IN LINKING_MORPHEMES:
            IF link == "":
                left_base = left_candidate
            ELIF left_candidate.endswith(link):
                left_base = left_candidate[:-len(link)]
            ELSE:
                CONTINUE

            IF len(left_base) < MIN_PART_LENGTH:
                CONTINUE

            left_ipa = self._dict.get(left_base)
            IF left_ipa IS NOT None:
                # 複合語のストレス調整:
                # 第1要素 = 主ストレス (既存のまま)
                # 第2要素 = 副ストレスに降格
                right_ipa_demoted = _demote_stress(right_ipa)
                RETURN left_ipa + right_ipa_demoted

    RETURN None  # 分割不可


FUNCTION _demote_stress(ipa: str) -> str:
    """主ストレス ˈ を副ストレス ˌ に降格する。"""
    # 先頭の ˈ のみ ˌ に変換 (既存の ˌ はそのまま)
    IF ipa.startswith("ˈ"):
        RETURN "ˌ" + ipa[1:]
    RETURN ipa
```

### 1.5.4 結合形素の詳細

| 形素 | 出現頻度 | 例 |
|------|---------|-----|
| -s- | 最頻出 | arbets + plats → arbetsplats (職場) |
| -e- | 一般的 | bild + bok → bildebok (絵本) — 稀 |
| -o- | 稀 | (ラテン語由来の複合語) |
| (なし) | 一般的 | sjuk + hus → sjukhus (病院) |

### 1.5.5 ルックアップ計算量

| フェーズ | 計算量 |
|---------|--------|
| 正規化 | O(n) (n = 単語長) |
| 完全一致 | O(1) 平均 |
| 複合語分割 | O(n * L * m) (n = 単語長, L = 結合形素数, m = 辞書ルックアップ O(1)) → 実質 O(n) |
| 合計 | O(n) |

### 1.5.6 テストケース

| # | 入力 | 辞書状態 | 期待出力 | 説明 |
|---|------|---------|---------|------|
| L-1 | `"barn"` | 辞書に存在 | `"ˈbɑːɳ"` | 完全一致ヒット |
| L-2 | `"sjukhus"` | 辞書に存在 | `"ˈɧʉːkˌhʉːs"` | 複合語 (辞書に直接存在) |
| L-3 | `"xyzabc"` | 辞書に不在 | `None` | 完全ミス |
| L-4 | `"arbetsplats"` | "arbetsplats" 不在, "arbete"+"plats" 存在 | 結合IPA | 複合語分割 (結合形素 -s-) |
| L-5 | `"Barn"` | "barn" 存在 | `"ˈbɑːɳ"` | 正規化後ヒット |
| L-6 | `""` | -- | `None` | 空入力 |
| L-7 | `"t-shirt"` | "t-shirt" 存在 | 辞書値 | ハイフン含有語 |
| L-8 | `"station"` | 辞書に存在 | `"staˈɧuːn"` | ストレス位置が語頭でない |

---

## 1.6 複数発音の取り扱い

### 1.6.1 方針

NST辞書には 2,105語が複数の発音バリアントを持つ。SAMPA→IPA変換ツール (FR-02) の段階で**最初のバリアント (最も標準的/一般的な発音) のみを採用**し、JSON辞書には1語1発音で格納する。

### 1.6.2 複数発音語の例

| 単語 | 第1発音 (採用) | 第2発音 (不採用) | 理由 |
|------|--------------|----------------|------|
| son | ˈsuːn | ˈsoːn | 第1がRiksvenska標準 |
| accent | akˈsɛnt | akˈsaŋ | 第1がスウェーデン語標準 |
| karl | ˈkɑːɭ | ˈkɑːr | 第1がレトロフレックス形 (中央方言) |
| du | ˈdyː | ˈdʉː | 第1が標準形 |

### 1.6.3 将来の拡張

Phase 2 以降でカスタム辞書 (`--custom-dict`) による上書き、または複数発音辞書のサポートを検討する。現時点では1語1発音で十分。

---

## 1.7 メモリレイアウトとロード戦略

### 1.7.1 メモリ使用量見積り

| ティア | エントリ数 | gzip サイズ | 展開後 JSON サイズ | Python dict メモリ |
|--------|----------|------------|------------------|-------------------|
| Core | ~238,000 | ~2.3 MB | ~7.8 MB | ~30-40 MB |
| Full | ~821,000 | ~10.6 MB | ~30 MB | ~100-120 MB |

**Python dict のメモリオーバーヘッド**: キーあたり約 100-130 バイト (ハッシュテーブルエントリ + str オブジェクト + IPA値の str オブジェクト)。

### 1.7.2 ロード戦略

```
FUNCTION _load_dict(self, dict_path: str) -> None:
    """辞書ファイルをロードして self._dict に格納する。"""

    path = Path(dict_path)

    # ファイル存在チェック
    IF NOT path.exists():
        RAISE FileNotFoundError(f"Swedish dictionary not found: {dict_path}")

    # 拡張子に応じた読み込み
    IF path.suffix == ".gz":
        # gzip圧縮されたJSON
        WITH gzip.open(path, "rt", encoding="utf-8") AS fp:
            data = json.load(fp)
    ELIF path.suffix == ".json":
        # 非圧縮JSON
        WITH open(path, "r", encoding="utf-8") AS fp:
            data = json.load(fp)
    ELSE:
        RAISE ValueError(f"Unsupported dictionary format: {path.suffix}")

    # 型検証
    IF NOT isinstance(data, dict):
        RAISE TypeError(
            f"Dictionary must be a JSON object, got {type(data).__name__}"
        )

    # エントリ数検証 (最低限のサニティチェック)
    IF len(data) == 0:
        _LOGGER.warning("Swedish dictionary is empty: %s", dict_path)

    self._dict = data
    _LOGGER.info(
        "Loaded Swedish dictionary: %d entries from %s",
        len(data), dict_path
    )
```

### 1.7.3 遅延ロード vs 即時ロード

**方針: 即時ロード (Eager loading)**

| 方式 | 利点 | 欠点 |
|------|------|------|
| **即時ロード (採用)** | 初回ルックアップのレイテンシなし、エラーの早期検出 | 起動時に数秒のオーバーヘッド |
| 遅延ロード | 起動時間ゼロ | 初回ルックアップで突然のレイテンシ |

**理由**: 辞書ロード時間は Core ティアで ~1秒 (NFR-02 要件: <=3秒) であり、起動時のオーバーヘッドとして許容範囲内。学習パイプラインでは初期化は1回のみ。

### 1.7.4 辞書なし動作

`dict_path` が指定されない場合 (`None`)、辞書は空の `dict` で初期化される。全単語が辞書ミスとなり、rule-based フォールバックのみで動作する。これはテスト時や辞書ファイル未配置環境での動作を保証する。

```python
def __init__(self, dict_path: str | None = None):
    self._dict: dict[str, str] = {}
    if dict_path is not None:
        self._load_dict(dict_path)
```

---

## 1.8 エラーハンドリング

### 1.8.1 エラー一覧

| # | エラー条件 | 例外型 | メッセージ | 動作 |
|---|-----------|--------|----------|------|
| E-1 | 辞書ファイルが存在しない | `FileNotFoundError` | `"Swedish dictionary not found: {path}"` | 例外送出 (致命的) |
| E-2 | gzip展開失敗 (破損) | `gzip.BadGzipFile` | `"Failed to decompress dictionary: {path}"` | 例外送出 (致命的) |
| E-3 | JSONパースエラー | `json.JSONDecodeError` | `"Failed to parse dictionary JSON: {path}"` | 例外送出 (致命的) |
| E-4 | JSONのルート型がdictでない | `TypeError` | `"Dictionary must be a JSON object, got {type}"` | 例外送出 (致命的) |
| E-5 | エンコーディングエラー (非UTF-8) | `UnicodeDecodeError` | (標準メッセージ) | 例外送出 (致命的) |
| E-6 | 辞書が空 (0エントリ) | -- (警告のみ) | `"Swedish dictionary is empty: {path}"` | 警告ログ、動作継続 |
| E-7 | 辞書パス未指定 (None) | -- (正常) | -- | 辞書なしで動作 (rule-basedのみ) |
| E-8 | ルックアップで不正なキー (空文字) | -- (正常) | -- | None を返却 |

### 1.8.2 エラーハンドリング擬似コード

```
FUNCTION _load_dict_safe(self, dict_path: str) -> None:
    TRY:
        self._load_dict(dict_path)
    CATCH FileNotFoundError AS e:
        _LOGGER.error("Swedish dictionary not found: %s", dict_path)
        RAISE
    CATCH gzip.BadGzipFile AS e:
        _LOGGER.error("Corrupted gzip dictionary: %s", dict_path)
        RAISE
    CATCH json.JSONDecodeError AS e:
        _LOGGER.error(
            "Invalid JSON in dictionary %s at line %d col %d: %s",
            dict_path, e.lineno, e.colno, e.msg
        )
        RAISE
    CATCH UnicodeDecodeError AS e:
        _LOGGER.error(
            "Encoding error in dictionary %s: expected UTF-8, got %s at position %d",
            dict_path, e.encoding, e.start
        )
        RAISE
```

### 1.8.3 ロード時のファイル検出優先順位

`dict_path` が指定されない場合の自動検出:

```
1. 環境変数 PIPER_SV_DICT_PATH が設定されていれば使用
2. None のまま → 辞書なしで動作
```

**注意**: ファイルの自動探索 (カレントディレクトリ等) は行わない。明示的なパス指定を要求する設計とする。

---

## 1.9 API仕様

### 1.9.1 コンストラクタ

```python
class SwedishPhonemizer(Phonemizer):
    def __init__(self, dict_path: str | None = None) -> None:
        """SwedishPhonemizerを初期化する。

        Parameters
        ----------
        dict_path : str | None
            NST辞書ファイルのパス。None の場合、辞書なしで
            rule-based G2P のみで動作する。
            .json.gz (gzip圧縮) と .json (非圧縮) をサポート。
            環境変数 PIPER_SV_DICT_PATH からのフォールバックあり。

        Raises
        ------
        FileNotFoundError
            dict_path が指定されたがファイルが存在しない場合。
        json.JSONDecodeError
            辞書ファイルのJSONパースに失敗した場合。
        TypeError
            辞書ファイルのルート要素がJSONオブジェクトでない場合。
        """
```

### 1.9.2 辞書ルックアップ (内部メソッド)

```python
def _lookup(self, word: str) -> str | None:
    """辞書から単語のIPA発音を検索する。

    Parameters
    ----------
    word : str
        正規化前の単語。内部で正規化を実行する。

    Returns
    -------
    str | None
        IPA発音文字列 (ストレスマーカー含む)。
        辞書に存在しない場合は None。
    """
```

### 1.9.3 正規化 (内部関数)

```python
def _normalize_for_lookup(word: str) -> str:
    """辞書ルックアップ用の単語正規化。

    Parameters
    ----------
    word : str
        入力単語。

    Returns
    -------
    str
        小文字・NFC正規化・句読点除去済みの文字列。
        入力が句読点のみの場合は空文字列。
    """
```

### 1.9.4 複合語分割 (内部メソッド)

```python
def _try_compound_decomposition(self, word: str) -> str | None:
    """複合語分割を試行し、パーツの発音を結合する。

    Parameters
    ----------
    word : str
        正規化済みの単語 (完全一致でミスした後に呼ばれる)。

    Returns
    -------
    str | None
        結合IPA文字列。分割できない場合は None。
        第1要素は主ストレス、第2要素は副ストレスに降格。
    """
```

### 1.9.5 辞書プロパティ

```python
@property
def dict_size(self) -> int:
    """ロードされた辞書のエントリ数を返す。"""
    return len(self._dict)

@property
def has_dict(self) -> bool:
    """辞書がロードされているかを返す。"""
    return len(self._dict) > 0
```

### 1.9.6 IPA文字列→音素トークンリスト分割

辞書から返却された IPA 文字列を、`SwedishPhonemizer.phonemize()` 内で音素トークンリストに分割する。

```python
def _split_ipa_to_tokens(self, ipa: str) -> list[str]:
    """IPA文字列を個別音素トークンのリストに分割する。

    Parameters
    ----------
    ipa : str
        辞書から取得した IPA 文字列 (例: "ˈbɑːɳ")。

    Returns
    -------
    list[str]
        音素トークンのリスト (例: ["ˈ", "b", "ɑː", "ɳ"])。
        多文字トークン (長母音 "ɑː" 等) は1要素として保持。
    """
```

**分割規則**:
1. ストレスマーカー (ˈ, ˌ) → 独立トークン
2. 長母音 (母音 + ː) → 1トークン (例: "ɑː")
3. 二重母音 (aʊ, ɛʊ) → 1トークン
4. 単一文字の子音/母音 → 1トークン

---

## 1.10 設定仕様

### 1.10.1 コンストラクタパラメータ

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|----------|------|
| `dict_path` | `str \| None` | `None` | 辞書ファイルパス |

### 1.10.2 環境変数

| 変数名 | 型 | 説明 |
|--------|-----|------|
| `PIPER_SV_DICT_PATH` | str | 辞書ファイルパス。コンストラクタの `dict_path` が None の場合にフォールバック |

### 1.10.3 優先順位

```
1. コンストラクタ引数 dict_path (最優先)
2. 環境変数 PIPER_SV_DICT_PATH
3. None (辞書なし動作)
```

### 1.10.4 設定解決の擬似コード

```
FUNCTION _resolve_dict_path(dict_path: str | None) -> str | None:
    IF dict_path IS NOT None:
        RETURN dict_path

    env_path = os.environ.get("PIPER_SV_DICT_PATH")
    IF env_path IS NOT None AND env_path != "":
        RETURN env_path

    RETURN None
```

---

## 1.11 テストケース

### 1.11.1 辞書ロードテスト

| # | テスト名 | 入力 | 期待結果 | 種別 |
|---|---------|------|---------|------|
| DL-1 | `test_load_json_dict` | 有効な .json ファイル | `dict_size > 0` | unit |
| DL-2 | `test_load_gzip_dict` | 有効な .json.gz ファイル | `dict_size > 0` | unit |
| DL-3 | `test_load_nonexistent_file` | 存在しないパス | `FileNotFoundError` | unit |
| DL-4 | `test_load_corrupt_gzip` | 破損した .gz ファイル | `gzip.BadGzipFile` | unit |
| DL-5 | `test_load_invalid_json` | 不正なJSON内容 | `json.JSONDecodeError` | unit |
| DL-6 | `test_load_json_array_root` | `[...]` (配列ルート) | `TypeError` | unit |
| DL-7 | `test_load_empty_dict` | `{}` | `dict_size == 0`, 警告ログ | unit |
| DL-8 | `test_no_dict_path` | `dict_path=None` | `dict_size == 0`, エラーなし | unit |

### 1.11.2 正規化テスト

| # | テスト名 | 入力 | 期待出力 |
|---|---------|------|---------|
| NM-1 | `test_normalize_lowercase` | `"Barn"` | `"barn"` |
| NM-2 | `test_normalize_strip_trailing_punct` | `"barn."` | `"barn"` |
| NM-3 | `test_normalize_strip_quotes` | `"\"barn\""` | `"barn"` |
| NM-4 | `test_normalize_preserve_hyphen` | `"t-shirt"` | `"t-shirt"` |
| NM-5 | `test_normalize_swedish_chars` | `"ÅKA"` | `"åka"` |
| NM-6 | `test_normalize_nfc` | `"a\u030aka"` | `"åka"` |
| NM-7 | `test_normalize_empty` | `""` | `""` |
| NM-8 | `test_normalize_punct_only` | `"!!!"` | `""` |

### 1.11.3 ルックアップテスト

| # | テスト名 | 辞書 | 入力 | 期待出力 |
|---|---------|------|------|---------|
| LK-1 | `test_lookup_exact_match` | `{"barn": "ˈbɑːɳ"}` | `"barn"` | `"ˈbɑːɳ"` |
| LK-2 | `test_lookup_case_insensitive` | `{"barn": "ˈbɑːɳ"}` | `"Barn"` | `"ˈbɑːɳ"` |
| LK-3 | `test_lookup_miss` | `{"barn": "ˈbɑːɳ"}` | `"xyz"` | `None` |
| LK-4 | `test_lookup_empty_word` | `{"barn": "ˈbɑːɳ"}` | `""` | `None` |
| LK-5 | `test_lookup_with_trailing_punct` | `{"barn": "ˈbɑːɳ"}` | `"barn,"` | `"ˈbɑːɳ"` |
| LK-6 | `test_lookup_swedish_special_chars` | `{"åka": "ˈoːka"}` | `"åka"` | `"ˈoːka"` |
| LK-7 | `test_lookup_no_dict` | `{}` (辞書なし) | `"barn"` | `None` |

### 1.11.4 複合語分割テスト

| # | テスト名 | 辞書 | 入力 | 期待動作 |
|---|---------|------|------|---------|
| CD-1 | `test_compound_sjukhus_in_dict` | 辞書に "sjukhus" 直接存在 | `"sjukhus"` | 完全一致で返却 (分割不要) |
| CD-2 | `test_compound_split_with_s_link` | "arbete" + "plats" あり, "arbetsplats" なし | `"arbetsplats"` | 分割成功 |
| CD-3 | `test_compound_no_valid_split` | "abc"/"xyz" なし | `"abcxyz"` | `None` |
| CD-4 | `test_compound_too_short_parts` | 2文字パーツ | `"abcd"` | `None` (最小3文字) |
| CD-5 | `test_compound_stress_demotion` | "sjuk" → "ˈɧʉːk", "hus" → "ˈhʉːs" | `"sjukhus"` (辞書に不在) | 結合: "ˈɧʉːk" + "ˌhʉːs" |

### 1.11.5 環境変数テスト

| # | テスト名 | 環境変数 | コンストラクタ引数 | 期待動作 |
|---|---------|---------|-----------------|---------|
| EV-1 | `test_env_var_fallback` | `PIPER_SV_DICT_PATH=/path/to/dict.json` | `None` | 環境変数のパスからロード |
| EV-2 | `test_constructor_overrides_env` | `PIPER_SV_DICT_PATH=/env/path` | `"/arg/path"` | コンストラクタ引数を優先 |
| EV-3 | `test_no_env_no_arg` | 未設定 | `None` | 辞書なし動作 |

---

# FR-02: SAMPA→IPA変換ツール

## 2.1 概要

NST辞書の元ファイル (`lexicon.txt`, TSV形式, SAMPA表記) を読み込み、SAMPA→IPA変換を適用して、piper-plus で使用可能な JSON 辞書ファイルを生成する前処理ツール。

| 項目 | 値 |
|------|-----|
| 成果物パス | `src/python/piper_train/tools/convert_nst_dictionary.py` |
| 入力 | OpenSLR `lexicon.txt` (TSV: WORD\tSAMPA) |
| 出力 | JSON dict (`{word: ipa}`) + オプションで gzip 圧縮 |
| 実行タイミング | ビルド前処理 (1回のみ実行、成果物をコミット/配布) |
| 受入基準 | スポットチェック20語全正解 |

---

## 2.2 SAMPA→IPA完全マッピングテーブル

### 2.2.1 長母音 (9音素)

| # | SAMPA | IPA | Unicode | PUA | 説明 | 例 (NST) |
|---|-------|-----|---------|-----|------|----------|
| 1 | `A:` | ɑː | U+0251 U+02D0 | 0xE05E | 開後舌非円唇 | GATA "g A: t a |
| 2 | `e:` | eː | U+0065 U+02D0 | 0xE05B | 半閉前舌非円唇 | HELA "h e: l a |
| 3 | `E:` | ɛː | U+025B U+02D0 | 0xE05C | 半開前舌非円唇 | ATA "E: t a |
| 4 | `i:` | iː | U+0069 U+02D0 | 0xE059 | 閉前舌非円唇 | FIN "f i: n |
| 5 | `o:` | oː | U+006F U+02D0 | 0xE05F | 半閉後舌円唇 | SON "s o: n |
| 6 | `u:` | uː | U+0075 U+02D0 | 0xE060 | 閉後舌円唇 | SOL "s u: l |
| 7 | `}:` | ʉː | U+0289 U+02D0 | 0xE061 | 閉中舌円唇 | HUS "h }: s |
| 8 | `y:` | yː | U+0079 U+02D0 | 0xE05A | 閉前舌円唇 | SYN "s y: n |
| 9 | `2:` | øː | U+00F8 U+02D0 | 0xE05D | 半閉前舌円唇 | OL "2: l |

### 2.2.2 短母音 (9音素)

| # | SAMPA | IPA | Unicode | PUA | 説明 | 例 (NST) |
|---|-------|-----|---------|-----|------|----------|
| 10 | `a` | a | U+0061 | -- | 開前舌 | KATT "k a t |
| 11 | `e` | e | U+0065 | -- | 半閉前舌 (非強勢) | GATA "g A: t a |
| 12 | `E` | ɛ | U+025B | -- | 半開前舌 | FEST "f E s t |
| 13 | `I` | ɪ | U+026A | -- | 近閉前舌 | FLICKA "f l I k a |
| 14 | `O` | ɔ | U+0254 | -- | 半開後舌 | OM "O m |
| 15 | `U` | ʊ | U+028A | -- | 近閉後舌 | OST "U s t |
| 16 | `u0` | ʉ | U+0289 | -- | 閉中舌円唇 (短) | BUSS "b u0 s |
| 17 | `Y` | ʏ | U+028F | -- | 近閉前舌円唇 | FYLLA "f Y l a |
| 18 | `9` | œ | U+0153 | -- | 半開前舌円唇 | MORK "m 9 r k |

### 2.2.3 基本子音 (16音素)

| # | SAMPA | IPA | Unicode | 説明 |
|---|-------|-----|---------|------|
| 19 | `b` | b | U+0062 | 有声両唇破裂音 |
| 20 | `d` | d | U+0064 | 有声歯茎破裂音 |
| 21 | `f` | f | U+0066 | 無声唇歯摩擦音 |
| 22 | `g` | ɡ | U+0261 | 有声軟口蓋破裂音 (注: IPA は U+0261) |
| 23 | `h` | h | U+0068 | 無声声門摩擦音 |
| 24 | `j` | j | U+006A | 有声硬口蓋接近音 |
| 25 | `k` | k | U+006B | 無声軟口蓋破裂音 |
| 26 | `l` | l | U+006C | 有声歯茎側面接近音 |
| 27 | `m` | m | U+006D | 有声両唇鼻音 |
| 28 | `n` | n | U+006E | 有声歯茎鼻音 |
| 29 | `p` | p | U+0070 | 無声両唇破裂音 |
| 30 | `r` | r | U+0072 | 有声歯茎ふるえ音 |
| 31 | `s` | s | U+0073 | 無声歯茎摩擦音 |
| 32 | `t` | t | U+0074 | 無声歯茎破裂音 |
| 33 | `v` | v | U+0076 | 有声唇歯摩擦音 |
| 34 | `N` | ŋ | U+014B | 有声軟口蓋鼻音 |

### 2.2.4 特殊子音 (2音素)

| # | SAMPA | IPA | Unicode | 説明 |
|---|-------|-----|---------|------|
| 35 | `S` | ɧ | U+0267 | sj-sound (無声背面硬口蓋/軟口蓋摩擦音) |
| 36 | `s'` | ɕ | U+0255 | tj-sound (無声歯茎硬口蓋摩擦音) |

### 2.2.5 レトロフレックス子音 (5音素)

| # | SAMPA | IPA | Unicode | 説明 |
|---|-------|-----|---------|------|
| 37 | `n\`` | ɳ | U+0273 | レトロフレックス鼻音 |
| 38 | `t\`` | ʈ | U+0288 | レトロフレックス無声破裂音 |
| 39 | `d\`` | ɖ | U+0256 | レトロフレックス有声破裂音 |
| 40 | `l\`` | ɭ | U+026D | レトロフレックス側面音 |
| 41 | `s\`` | ʂ | U+0282 | レトロフレックス摩擦音 |

### 2.2.6 二重母音 (2音素)

| # | SAMPA | IPA | Unicode | PUA | 説明 |
|---|-------|-----|---------|-----|------|
| 42 | `a*U` | aʊ | U+0061 U+028A | 要PUA | 開前舌+近閉後舌 |
| 43 | `E*U` | ɛʊ | U+025B U+028A | 要PUA | 半開前舌+近閉後舌 |

### 2.2.7 ストレスマーカー (接頭辞)

| SAMPA | IPA | Unicode | 処理 |
|-------|-----|---------|------|
| `"` (引用符) | ˈ | U+02C8 | トークン先頭の `"` を除去し、ˈ を出力に挿入 |
| `%` | ˌ | U+02CC | トークン先頭の `%` を除去し、ˌ を出力に挿入 |

### 2.2.8 Python 辞書定数

```python
NST_SAMPA_TO_IPA: dict[str, str] = {
    # 長母音
    "A:": "ɑː",
    "e:": "eː",
    "E:": "ɛː",
    "i:": "iː",
    "o:": "oː",
    "u:": "uː",
    "}:": "ʉː",
    "y:": "yː",
    "2:": "øː",
    # 短母音
    "a":  "a",
    "e":  "e",
    "E":  "ɛ",
    "I":  "ɪ",
    "O":  "ɔ",
    "U":  "ʊ",
    "u0": "ʉ",
    "Y":  "ʏ",
    "9":  "œ",
    # 基本子音
    "b": "b", "d": "d", "f": "f", "g": "ɡ",
    "h": "h", "j": "j", "k": "k", "l": "l",
    "m": "m", "n": "n", "p": "p", "r": "r",
    "s": "s", "t": "t", "v": "v",
    "N": "ŋ",
    # 特殊子音
    "S":  "ɧ",
    "s'": "ɕ",
    # レトロフレックス
    "n`": "ɳ",
    "t`": "ʈ",
    "d`": "ɖ",
    "l`": "ɭ",
    "s`": "ʂ",
    # 二重母音
    "a*U": "aʊ",
    "E*U": "ɛʊ",
}
```

---

## 2.3 パースアルゴリズム

### 2.3.1 入力フォーマット

NST辞書 (`lexicon.txt`) の各行:

```
WORD\tSAMPA_PRONUNCIATION
```

- `WORD`: 全大文字のスウェーデン語単語 (UTF-8)
- `\t`: タブ区切り
- `SAMPA_PRONUNCIATION`: スペース区切りの SAMPA 音素列 (ストレス接頭辞付き)

### 2.3.2 行パースの擬似コード

```
FUNCTION parse_nst_line(line: str) -> tuple[str, str] | None:
    """NST辞書の1行をパースする。

    Returns
    -------
    tuple[str, str] | None
        (小文字単語, SAMPA発音) のタプル。
        無効な行の場合は None。
    """
    # 改行除去
    line = line.rstrip("\n\r")

    # 空行スキップ
    IF line == "":
        RETURN None

    # タブ分割
    parts = line.split("\t")
    IF len(parts) != 2:
        _LOGGER.warning("Skipping malformed line (expected 2 columns): %r", line)
        RETURN None

    word = parts[0].strip()
    sampa = parts[1].strip()

    # 空の単語/発音をスキップ
    IF word == "" OR sampa == "":
        _LOGGER.warning("Skipping empty word or pronunciation: %r", line)
        RETURN None

    # 小文字変換
    word_lower = word.lower()

    RETURN (word_lower, sampa)
```

### 2.3.3 SAMPA→IPA変換の擬似コード

```
FUNCTION convert_sampa_to_ipa(sampa: str) -> str:
    """スペース区切りのSAMPA発音をIPA文字列に変換する。

    Parameters
    ----------
    sampa : str
        NST SAMPA 発音文字列 (例: '"b A: n`')

    Returns
    -------
    str
        IPA 文字列 (例: 'ˈbɑːɳ')
    """
    ipa_parts: list[str] = []

    FOR token IN sampa.split():
        stress_prefix = ""

        # ストレス接頭辞の処理
        # 注意: '%"' (副+主) の組み合わせも稀に存在する
        IF token.startswith('%"'):
            stress_prefix = "ˌˈ"
            token = token[2:]
        ELIF token.startswith('"'):
            stress_prefix = "ˈ"
            token = token[1:]
        ELIF token.startswith('%'):
            stress_prefix = "ˌ"
            token = token[1:]

        # ストレスのみ (後続音素なし) の場合
        IF token == "":
            IF stress_prefix != "":
                ipa_parts.append(stress_prefix)
            CONTINUE

        # SAMPA→IPA変換
        ipa = NST_SAMPA_TO_IPA.get(token)
        IF ipa IS NOT None:
            ipa_parts.append(stress_prefix + ipa)
        ELSE:
            # 未知のSAMPAトークン → 警告を出してそのまま通す
            _LOGGER.warning("Unknown SAMPA token: %r (passing through)", token)
            ipa_parts.append(stress_prefix + token)

    RETURN "".join(ipa_parts)
```

### 2.3.4 パース順序の注意点

SAMPA トークンのルックアップは完全一致 (スペース区切りの各トークンをそのまま検索) であるため、部分一致の曖昧さは発生しない。ただし以下に注意:

1. **`s'` vs `s`**: スペース区切りで `s'` は1トークン。`s` と `'` が分離することはない。
2. **`n\`` vs `n`**: バッククォート付きはレトロフレックス。スペース区切りで1トークン。
3. **`u0` vs `u`**: `u0` は1トークン (短い ʉ)。`u` 単独は存在しない (常に `u:` または `u0`)。
4. **`a*U` vs `a`**: `a*U` は1トークン (二重母音)。
5. **`2:` vs `2`**: `2:` は1トークン (長い øː)。`2` 単独は NST 辞書に存在しない。

---

## 2.4 出力フォーマット仕様

### 2.4.1 JSON出力

```json
{
  "barn": "ˈbɑːɳ",
  "sjukhus": "ˈɧʉːkˌhʉːs",
  "station": "staˈɧuːn",
  "sked": "ˈɧeːd",
  "skola": "ˈskuːla"
}
```

### 2.4.2 出力制約

| 項目 | 制約 |
|------|------|
| エンコーディング | UTF-8 (BOMなし) |
| キー | 小文字正規化済み、ソート済み (再現性のため) |
| 値 | IPA文字列、空文字列禁止 |
| 改行 | `\n` (Unix) |
| インデント | なし (1行JSON、gzip圧縮時のサイズ最適化) |
| gzip出力 | `--gzip` オプションで `.json.gz` を生成 |

### 2.4.3 出力統計情報 (stderr)

変換完了時に以下の統計を stderr に出力する:

```
NST Dictionary Conversion Summary:
  Input lines:     822,740
  Valid entries:    820,572
  Skipped (filter): 2,168
    !SIL:           1
    <UNK>:          1
    Hyphen prefix:  44
    Empty pron:     0
    Duplicate:      2,122 (first variant kept)
  Unknown SAMPA:    0
  Output entries:   820,572
  Output file:      sv_lexicon_full.json.gz (10.6 MB)
```

---

## 2.5 フィルタリング規則

### 2.5.1 除外対象エントリ

| # | パターン | 判定条件 | 除外理由 | 例 |
|---|---------|---------|---------|-----|
| F-1 | `!SIL` | `word == "!SIL"` (大文字小文字不問) | 無音記号、語彙でない | `!SIL\t...` |
| F-2 | `<UNK>` | `word == "<UNK>"` | 未知語プレースホルダ | `<UNK>\t...` |
| F-3 | ハイフン接頭断片 | `word.startswith("-")` | 接尾辞断片、独立語でない | `-TION\t...` |
| F-4 | 空の発音 | `sampa.strip() == ""` | 発音情報なし | `WORD\t` |
| F-5 | 重複エントリ (2件目以降) | 同一単語の2回目以降の出現 | 最初のバリアントのみ採用 | 2,105語 |

### 2.5.2 フィルタリング擬似コード

```
FUNCTION should_skip_entry(word: str, sampa: str, seen: set[str]) -> tuple[bool, str]:
    """エントリをスキップすべきか判定する。

    Returns
    -------
    tuple[bool, str]
        (スキップすべきか, スキップ理由)
    """
    word_upper = word.upper().strip()

    # F-1: !SIL
    IF word_upper == "!SIL":
        RETURN (True, "silence_marker")

    # F-2: <UNK>
    IF word_upper == "<UNK>":
        RETURN (True, "unknown_marker")

    # F-3: ハイフン接頭断片
    IF word_upper.startswith("-"):
        RETURN (True, "hyphen_prefix")

    # F-4: 空の発音
    IF sampa.strip() == "":
        RETURN (True, "empty_pronunciation")

    # F-5: 重複 (2件目以降)
    word_lower = word.lower().strip()
    IF word_lower IN seen:
        RETURN (True, "duplicate")

    RETURN (False, "")
```

### 2.5.3 ティア別フィルタリング (Core vs Full)

Core ティアでは追加のフィルタリングを適用して、単純語のみを抽出する:

```
FUNCTION is_simple_word(word: str, sampa: str) -> bool:
    """Coreティア用: 複合語でない単純語を判定する。

    判定基準: SAMPAに副ストレス (%) が含まれない語は単純語。
    """
    RETURN "%" NOT IN sampa
```

| ティア | フィルタ | 結果 |
|--------|---------|------|
| Full | F-1 ~ F-5 のみ | ~821,000 語 |
| Core | F-1 ~ F-5 + 単純語フィルタ | ~238,000 語 |

---

## 2.6 CLIインターフェース仕様

### 2.6.1 コマンド

```bash
python -m piper_train.tools.convert_nst_dictionary \
    --input /path/to/lexicon.txt \
    --output /path/to/sv_lexicon.json \
    [--gzip] \
    [--tier core|full] \
    [--validate] \
    [--stats]
```

### 2.6.2 引数仕様

| 引数 | 短縮 | 型 | デフォルト | 必須 | 説明 |
|------|------|-----|----------|------|------|
| `--input` | `-i` | str (パス) | -- | 必須 | NST辞書入力ファイル (`lexicon.txt`) |
| `--output` | `-o` | str (パス) | -- | 必須 | 出力JSONファイル (`.json` or `.json.gz`) |
| `--gzip` | -- | フラグ | False | 任意 | 出力をgzip圧縮する |
| `--tier` | `-t` | `core\|full` | `full` | 任意 | 出力ティア (core=単純語のみ, full=全語) |
| `--validate` | `-v` | フラグ | False | 任意 | スポットチェック検証を実行 |
| `--stats` | `-s` | フラグ | True | 任意 | 変換統計を stderr に出力 |
| `--quiet` | `-q` | フラグ | False | 任意 | 警告ログを抑制 |

### 2.6.3 終了コード

| コード | 意味 |
|--------|------|
| 0 | 正常完了 |
| 1 | 入力ファイルが見つからない |
| 2 | 入力ファイルのフォーマットエラー (パース不可能な行が多すぎる) |
| 3 | 出力ファイルの書き込みエラー |
| 4 | 検証失敗 (`--validate` 時にスポットチェック不合格) |

### 2.6.4 使用例

```bash
# Full辞書 (gzip圧縮)
python -m piper_train.tools.convert_nst_dictionary \
    -i lexicon.txt \
    -o sv_lexicon_full.json.gz \
    --gzip --tier full --validate

# Core辞書 (gzip圧縮)
python -m piper_train.tools.convert_nst_dictionary \
    -i lexicon.txt \
    -o sv_lexicon_core.json.gz \
    --gzip --tier core --validate
```

### 2.6.5 主処理の擬似コード

```
FUNCTION main(args):
    # 1. 入力ファイル読み込み
    IF NOT exists(args.input):
        print_error("Input file not found: " + args.input)
        EXIT(1)

    # 2. 変換ループ
    result: dict[str, str] = {}
    seen: set[str] = set()
    stats = Counter()

    WITH open(args.input, "r", encoding="utf-8") AS fp:
        FOR line_num, line IN enumerate(fp, 1):
            # 行パース
            parsed = parse_nst_line(line)
            IF parsed IS None:
                stats["malformed"] += 1
                CONTINUE

            word, sampa = parsed

            # フィルタリング
            skip, reason = should_skip_entry(word, sampa, seen)
            IF skip:
                stats[reason] += 1
                CONTINUE

            # ティアフィルタ
            IF args.tier == "core" AND NOT is_simple_word(word, sampa):
                stats["compound_filtered"] += 1
                CONTINUE

            # SAMPA→IPA変換
            ipa = convert_sampa_to_ipa(sampa)

            # 結果格納
            result[word] = ipa
            seen.add(word)
            stats["converted"] += 1

    # 3. 検証 (--validate)
    IF args.validate:
        ok = run_spot_check(result)
        IF NOT ok:
            print_error("Spot check failed!")
            EXIT(4)

    # 4. 出力
    TRY:
        # キーでソートして出力 (再現性)
        sorted_result = dict(sorted(result.items()))
        IF args.gzip:
            WITH gzip.open(args.output, "wt", encoding="utf-8") AS fp:
                json.dump(sorted_result, fp, ensure_ascii=False, separators=(",", ":"))
        ELSE:
            WITH open(args.output, "w", encoding="utf-8") AS fp:
                json.dump(sorted_result, fp, ensure_ascii=False, separators=(",", ":"))
    CATCH IOError AS e:
        print_error("Failed to write output: " + str(e))
        EXIT(3)

    # 5. 統計出力
    IF args.stats:
        print_stats(stats, args.output)

    EXIT(0)
```

---

## 2.7 検証ステップ

### 2.7.1 スポットチェック検証テーブル

`--validate` オプション指定時に以下の20語をチェックする。全語が期待値と一致しない場合は終了コード4で失敗する。

| # | 単語 | NST SAMPA | 期待 IPA | カテゴリ |
|---|------|-----------|---------|---------|
| V-1 | barn | `"b A: n\`` | ˈbɑːɳ | レトロフレックス |
| V-2 | sked | `"S e: d` | ˈɧeːd | sj-sound |
| V-3 | skola | `"s k u: l a` | ˈskuːla | sk + 後母音 |
| V-4 | kind | `"s' I n d` | ˈɕɪnd | tj-sound |
| V-5 | sjuk | `"S }: k` | ˈɧʉːk | sj-sound + ʉː |
| V-6 | flicka | `"f l I k a` | ˈflɪka | 短母音 |
| V-7 | station | `s t a "S u: n` | staˈɧuːn | ストレス語中 |
| V-8 | chef | `"S e: f` | ˈɧeːf | ローンワード sj |
| V-9 | bord | `"b u: d\`` | ˈbuːɖ | レトロフレックス |
| V-10 | fors | `"f O s\`` | ˈfɔʂ | レトロフレックス |
| V-11 | kung | `"k u0 N` | ˈkʉŋ | ŋ |
| V-12 | hus | `"h }: s` | ˈhʉːs | 長母音 ʉː |
| V-13 | gata | `"g A: t a` | ˈɡɑːta | 長母音 ɑː |
| V-14 | fest | `"f E s t` | ˈfɛst | 短母音 ɛ |
| V-15 | sol | `"s u: l` | ˈsuːl | "o" = uː |
| V-16 | son | `"s o: n` | ˈsoːn | "o" = oː |
| V-17 | kort | `"k O t\`` | ˈkɔʈ | 短母音 + レトロフレックス |
| V-18 | öl | `"2: l` | ˈøːl | 長母音 øː |
| V-19 | syn | `"s y: n` | ˈsyːn | 長母音 yː |
| V-20 | ost | `"U s t` | ˈʊst | 短母音 ʊ |

### 2.7.2 検証擬似コード

```
SPOT_CHECK_TABLE: list[tuple[str, str]] = [
    ("barn",    "ˈbɑːɳ"),
    ("sked",    "ˈɧeːd"),
    ("skola",   "ˈskuːla"),
    ("kind",    "ˈɕɪnd"),
    ("sjuk",    "ˈɧʉːk"),
    ("flicka",  "ˈflɪka"),
    ("station", "staˈɧuːn"),
    ("chef",    "ˈɧeːf"),
    ("bord",    "ˈbuːɖ"),
    ("fors",    "ˈfɔʂ"),
    ("kung",    "ˈkʉŋ"),
    ("hus",     "ˈhʉːs"),
    ("gata",    "ˈɡɑːta"),
    ("fest",    "ˈfɛst"),
    ("sol",     "ˈsuːl"),
    ("son",     "ˈsoːn"),
    ("kort",    "ˈkɔʈ"),
    ("öl",      "ˈøːl"),
    ("syn",     "ˈsyːn"),
    ("ost",     "ˈʊst"),
]

FUNCTION run_spot_check(result: dict[str, str]) -> bool:
    passed = 0
    failed = 0

    FOR word, expected_ipa IN SPOT_CHECK_TABLE:
        actual_ipa = result.get(word)
        IF actual_ipa IS None:
            print_error(f"  FAIL: '{word}' not found in dictionary")
            failed += 1
        ELIF actual_ipa != expected_ipa:
            print_error(
                f"  FAIL: '{word}' expected '{expected_ipa}' got '{actual_ipa}'"
            )
            failed += 1
        ELSE:
            passed += 1

    print_info(f"Spot check: {passed}/{passed + failed} passed")
    RETURN failed == 0
```

---

## 2.8 エッジケース処理

### 2.8.1 空の発音

```
WORD\t
```

→ `sampa.strip() == ""` → フィルタリング規則 F-4 で除外。

### 2.8.2 不正な行 (タブなし)

```
WORDWITHOUTAB
```

→ `line.split("\t")` で `len(parts) == 1` → `parse_nst_line()` が None を返却、警告ログ。

### 2.8.3 重複単語

```
SON\t"s u: n
SON\t"s o: n
```

→ 1行目: `seen` に "son" を追加、IPA を格納。
→ 2行目: `seen` に "son" が存在 → フィルタリング規則 F-5 で除外。

### 2.8.4 未知のSAMPAトークン

```
WORD\t"x y z
```

`x`, `y`, `z` が `NST_SAMPA_TO_IPA` に無い場合:
- 警告ログ: `Unknown SAMPA token: 'x'`
- そのままパススルー: IPA出力に `x` が残る
- 未知トークンが多い場合は辞書品質の問題を示唆するため、統計で集計する

### 2.8.5 ストレスのみのトークン

```
WORD\t"
```

→ `token.startswith('"')` で `stress_prefix = "ˈ"`, `token = ""` → ストレスのみ出力。
→ 実際にはNST辞書でこのパターンは存在しないが、防御的にハンドリング。

### 2.8.6 非ASCII文字を含む単語

```
GÖTEBORG\t"j 2: t e %b O r j
```

→ `word.lower()` → `"göteborg"` (ö は小文字のまま保持)
→ SAMPA変換は通常通り

### 2.8.7 非常に長い単語

NST辞書には 30 文字以上の複合語が存在する:

```
SOCIALFÖRSÄKRINGSKONTOR\t...
```

→ 正常に処理される (特別な制限なし)

### 2.8.8 バックスラッシュ含有SAMPAトークン

レトロフレックスの SAMPA 表記にはバッククォート (`` ` ``) が含まれる:

```
BARN\t"b A: n`
```

**注意**: Python でのファイル読み込み時にバッククォートはエスケープ文字として解釈されない (バッククォートであり、バックスラッシュではない)。NST辞書の表記は `n`\`` (n + バッククォート) であり、`n\`` (n + バックスラッシュ + バッククォート) ではない。ただし `nst-dictionary-integration.md` のマークダウン表記ではエスケープされている場合があるため、実データとの照合が必要。

---

## 2.9 テストケース

### 2.9.1 SAMPA→IPA変換テスト

| # | テスト名 | 入力 (SAMPA) | 期待出力 (IPA) | 説明 |
|---|---------|-------------|---------------|------|
| CV-1 | `test_convert_long_vowel` | `'"b A: n\``' | `"ˈbɑːɳ"` | 長母音 + レトロフレックス |
| CV-2 | `test_convert_sj_sound` | `'"S e: d'` | `"ˈɧeːd"` | sj-sound |
| CV-3 | `test_convert_secondary_stress` | `'"S }: k %h }: s'` | `"ˈɧʉːkˌhʉːs"` | 主+副ストレス |
| CV-4 | `test_convert_mid_word_stress` | `'s t a "S u: n'` | `"staˈɧuːn"` | 語中ストレス |
| CV-5 | `test_convert_tj_sound` | `'"s\' I n d'` | `"ˈɕɪnd"` | tj-sound |
| CV-6 | `test_convert_retroflex_all` | `'"k O t\`'` | `"ˈkɔʈ"` | レトロフレックス ʈ |
| CV-7 | `test_convert_diphthong` | `'"a*U d'` | `"ˈaʊd"` | 二重母音 |
| CV-8 | `test_convert_short_u0` | `'"b u0 s'` | `"ˈbʉs"` | 短い ʉ |
| CV-9 | `test_convert_ng` | `'"k u0 N'` | `"ˈkʉŋ"` | ŋ |
| CV-10 | `test_convert_oe` | `'"m 9 r k'` | `"ˈmœrk"` | 短い œ |

### 2.9.2 行パーステスト

| # | テスト名 | 入力行 | 期待出力 | 説明 |
|---|---------|-------|---------|------|
| PL-1 | `test_parse_normal_line` | `'BARN\t"b A: n\`'` | `("barn", '"b A: n\`')` | 正常な行 |
| PL-2 | `test_parse_empty_line` | `""` | `None` | 空行 |
| PL-3 | `test_parse_no_tab` | `"WORDONLY"` | `None` + 警告 | タブなし |
| PL-4 | `test_parse_empty_pronunciation` | `"WORD\t"` | `None` + 警告 | 空発音 |
| PL-5 | `test_parse_swedish_chars` | `'GÖTEBORG\t"j 2: t e ...'` | `("göteborg", ...)` | 特殊文字 |
| PL-6 | `test_parse_preserves_tabs_in_sampa` | (該当なし) | (該当なし) | SAMPAにタブは含まれない |

### 2.9.3 フィルタリングテスト

| # | テスト名 | 入力 | 期待動作 | 説明 |
|---|---------|------|---------|------|
| FL-1 | `test_filter_silence` | `"!SIL\t..."` | スキップ | F-1: 無音 |
| FL-2 | `test_filter_unknown` | `"<UNK>\t..."` | スキップ | F-2: 未知語 |
| FL-3 | `test_filter_hyphen_prefix` | `"-TION\t..."` | スキップ | F-3: 接頭断片 |
| FL-4 | `test_filter_empty_pron` | `"WORD\t"` | スキップ | F-4: 空発音 |
| FL-5 | `test_filter_duplicate_first_kept` | 同一語2行 | 1行目のみ採用 | F-5: 重複 |
| FL-6 | `test_filter_normal_word` | `"BARN\t..."` | 採用 | フィルタ非該当 |

### 2.9.4 ティアフィルタテスト

| # | テスト名 | 入力SAMPA | ティア | 期待動作 | 説明 |
|---|---------|-----------|--------|---------|------|
| TF-1 | `test_core_simple_word` | `'"b A: n\`'` (% なし) | core | 採用 | 単純語 |
| TF-2 | `test_core_compound_filtered` | `'"S }: k %h }: s'` (% あり) | core | 除外 | 複合語 |
| TF-3 | `test_full_compound_kept` | `'"S }: k %h }: s'` (% あり) | full | 採用 | Fullは全語含む |

### 2.9.5 エンドツーエンドテスト

| # | テスト名 | 説明 |
|---|---------|------|
| E2E-1 | `test_convert_small_lexicon` | 10行のミニ辞書を変換し、全エントリの IPA を検証 |
| E2E-2 | `test_convert_with_gzip_output` | gzip 出力が正しく読み込めることを検証 |
| E2E-3 | `test_convert_spot_check_passes` | `--validate` でスポットチェック全通過 |
| E2E-4 | `test_convert_core_tier_smaller` | Core ティアが Full ティアより少ないエントリ数であることを検証 |
| E2E-5 | `test_convert_keys_are_sorted` | 出力 JSON のキーがソート済みであることを検証 |

### 2.9.6 エッジケーステスト

| # | テスト名 | 入力 | 期待動作 | 説明 |
|---|---------|------|---------|------|
| EC-1 | `test_unknown_sampa_token` | `"x y z"` | 警告 + パススルー | 未知トークン |
| EC-2 | `test_stress_only_token` | `'"'` | ストレスマーカーのみ出力 | ストレスだけ |
| EC-3 | `test_very_long_word` | 30文字超の複合語 | 正常変換 | 長い語 |
| EC-4 | `test_combined_stress_percent_quote` | `'%"x'` | `"ˌˈ..."` | 副+主ストレス |
| EC-5 | `test_empty_input_file` | 0行のファイル | 空の JSON `{}` | 空入力 |

---

## 付録A: 既存ファイルへの影響

本仕様 (FR-01/FR-02) で変更が必要な既存ファイル:

| ファイル | 変更内容 | FR |
|---------|---------|-----|
| `src/python/piper_train/phonemize/token_mapper.py` | SV用 PUA 11個を `FIXED_PUA_MAPPING` に追加, `_PUA_START` を 0xE064 に更新 | FR-01 (依存) |
| `src/python/piper_train/phonemize/registry.py` | `_auto_register()` に `SwedishPhonemizer` 登録, `_detect_default_latin` に `"sv"` 追加 | FR-01 (依存) |

**新規作成ファイル:**

| ファイル | 説明 | FR |
|---------|------|-----|
| `src/python/piper_train/phonemize/swedish.py` | SwedishPhonemizer (FR-01 のルックアップ含む) | FR-01 |
| `src/python/piper_train/tools/convert_nst_dictionary.py` | SAMPA→IPA変換ツール | FR-02 |
| `src/python/piper_train/phonemize/sv_id_map.py` | スウェーデン語音素インベントリ | FR-01 (依存) |

---

## 付録B: PUA割り当て詳細

`token_mapper.py` の `FIXED_PUA_MAPPING` に追加する SV 用エントリ:

```python
# =======================================================================
# Swedish (SV) -- Long vowels + Diphthongs
# =======================================================================
"i\u02D0": 0xE059,   # iː  close front unrounded (long)
"y\u02D0": 0xE05A,   # yː  close front rounded (long)
"e\u02D0": 0xE05B,   # eː  close-mid front (long)
"\u025B\u02D0": 0xE05C,  # ɛː  open-mid front (long)
"\u00F8\u02D0": 0xE05D,  # øː  close-mid front rounded (long)
"\u0251\u02D0": 0xE05E,  # ɑː  open back unrounded (long)
"o\u02D0": 0xE05F,   # oː  close-mid back rounded (long)
"u\u02D0": 0xE060,   # uː  close back rounded (long)
"\u0289\u02D0": 0xE061,  # ʉː  close central rounded (long)
"a\u028A": 0xE062,   # aʊ  diphthong (open front + near-close back)
"\u025B\u028A": 0xE063,  # ɛʊ  diphthong (open-mid front + near-close back)
```

**注意**: `aʊ` (0xE062) は中国語の `aʊ` (0xE02A) とは異なるトークンとして扱う。中国語の `aʊ` はピンイン "ao" の音素であり、SAMPA → IPA の直接マッピング結果である SV の `aʊ` とは音声学的文脈が異なる。ただし、将来的に統一を検討する場合は中国語側の PUA (0xE02A) を再利用できる可能性がある。

`_PUA_START` の更新:

```python
_PUA_START = 0xE064  # 0xE063 が最後の SV 固定割り当て
```

---

## 付録C: パフォーマンス要件 (NFR-02 参照)

| 指標 | 要件 | 測定方法 |
|------|------|---------|
| 辞書ロード時間 (Core, 238K語) | <= 3秒 | `time.perf_counter()` で `_load_dict()` を計測 |
| 辞書ロード時間 (Full, 821K語) | <= 10秒 | 同上 |
| 単語ルックアップ (辞書ヒット) | <= 0.01ms | 10,000語ルックアップの平均 |
| 単語ルックアップ (複合語分割) | <= 1ms | 分割成功ケースの平均 |
| メモリ使用量 (Core) | <= 50 MB | `tracemalloc` で計測 |
| メモリ使用量 (Full) | <= 150 MB | 同上 |
| SAMPA→IPA変換 (全辞書) | <= 60秒 | `convert_nst_dictionary.py` の実行時間 |
