# M4: 日本語音素化キャッシュ

> **マイルストーン**: [M4](../../guides/cpu-inference-tier2-milestones.md#m4-日本語音素化キャッシュ)
> **設計書**: [cpu-inference-tier2-design.md](../../guides/cpu-inference-tier2-design.md#施策-4-日本語音素化キャッシュ)
> **ステータス**: 完了
> **依存**: なし (独立して実装可能、ただし M1/M3 完了後のコミットが望ましい)
> **後続**: [M5](M5-integration.md)

---

## 1. タスク目的とゴール

### 目的

日本語音素化の主要ボトルネックである `pyopenjtalk.extract_fullcontext()` (MeCab 形態素解析 + フルコンテキストラベル生成) は 1 回あたり 50-150ms かかる。WebUI やサーバー環境で同一テキストの繰り返し処理時に、この再計算コストが無駄に積み重なる。`functools.lru_cache` を用いた文単位キャッシュを導入し、キャッシュヒット時のレイテンシを 1ms 未満に削減する。

### ゴール

- 同一文の 2 回目以降の音素化が **< 1ms** で完了する (キャッシュヒット時)
- WebUI/Docker 推論サーバーでの繰り返しリクエストが **10-50x 高速化** される
- キャッシュ導入により既存の音素化結果が**一切変化しない** (出力の bit-exact 一致)
- `prosody=True` と `prosody=False` で**別のキャッシュエントリ**が生成される
- カスタム辞書変更時に `cache_clear()` で安全にキャッシュ無効化できる

### 非ゴール

- Rust / C# 側のキャッシュ実装 (Phase 2 で検討)
- 文を跨いだコンテキスト依存キャッシュ (文単位分割で回避)
- ディスク永続化キャッシュ (メモリ内 LRU のみ)

---

## 2. 実装内容の詳細

### 2-1. 背景: コンテキスト依存性の問題

A1/A2/A3 prosody 値はテキスト中の文脈位置によって変化する:

```python
# 同じ「こんにちは」でも前後の文脈で A2/A3 が異なる可能性
pyopenjtalk.extract_fullcontext("こんにちは")        # 単独: A2=X
pyopenjtalk.extract_fullcontext("私はこんにちは")    # 文中: A2=Y (異なる可能性)
```

**対策**: `_split_long_text()` で**文単位に分割した後**にキャッシュする。文単位であればコンテキストは固定されるため安全。

### 2-2. piper_train 側 (G2P パッケージ): `src/python/g2p/piper_plus_g2p/japanese.py`

piper_train の日本語音素化は `_phonemize_core()` 関数が核であり、`pyopenjtalk.extract_fullcontext()` を呼び出して HTS ラベルから音素トークンと prosody 情報を抽出する。

**変更点:**

1. `functools.lru_cache` を import
2. `_phonemize_core()` の結果をキャッシュする `_phonemize_core_cached()` を追加
3. `lru_cache` は mutable な引数 (list) をキャッシュキーにできないため、戻り値を tuple に変換して返す
4. `JapanesePhonemizer.phonemize()` と `JapanesePhonemizer.phonemize_with_prosody()` からキャッシュ版を呼び出す
5. `clear_phonemize_cache()` 関数を公開 API として追加
6. `__all__` に `"clear_phonemize_cache"` を追加する (現在は `__all__ = ["JapanesePhonemizer"]` のみ)

```python
# src/python/g2p/piper_plus_g2p/japanese.py (変更イメージ)

from functools import lru_cache

@lru_cache(maxsize=2000)
def _phonemize_core_cached(text: str) -> tuple[tuple[str, ...], tuple[ProsodyInfo | None, ...]]:
    """単一文の音素化結果をキャッシュする。
    
    lru_cache はハッシュ可能な引数のみ受け付けるため、
    戻り値の list を tuple に変換してキャッシュに格納する。
    """
    tokens, prosody_info = _phonemize_core(text)
    return tuple(tokens), tuple(prosody_info)

def clear_phonemize_cache() -> None:
    """音素化キャッシュをクリアする (カスタム辞書変更時等に呼び出す)。"""
    _phonemize_core_cached.cache_clear()
```

**`JapanesePhonemizer` の変更:**

```python
class JapanesePhonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]:
        text = self._apply_custom_dict(text)
        text = self._sanitize_input(text)
        if not text:
            return []
        tokens_tuple, _prosody_tuple = _phonemize_core_cached(text)
        return list(tokens_tuple)

    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        text = self._apply_custom_dict(text)
        text = self._sanitize_input(text)
        if not text:
            return [], []
        tokens_tuple, prosody_tuple = _phonemize_core_cached(text)
        return list(tokens_tuple), list(prosody_tuple)
```

**注意**: `_apply_custom_dict()` はキャッシュの**前**に適用される。カスタム辞書によるテキスト変換後の文字列がキャッシュキーになるため、同一辞書設定下では辞書変更時に古い結果が返ることはない。ただし、**カスタム辞書変更時は `clear_phonemize_cache()` を必ず呼び出すこと**。辞書エントリの追加・変更・削除により、同一入力テキストに対するカスタム辞書適用後の文字列が変わる場合があり、キャッシュに残った古いエントリが不正な結果を返す可能性がある。

### 2-3. python_run 側 (ランタイムパッケージ): `src/python_run/piper/phonemize/japanese.py`

python_run 側は `phonemize_japanese()` 関数がメインエントリで、`_split_long_text()` で文分割した後にチャンクごとに**自分自身を再帰呼び出し**する構造になっている。

**現在のコード構造 (再帰):**

```python
def phonemize_japanese(text, custom_dict=None, prosody=True):
    ...
    chunks = _split_long_text(text)
    if len(chunks) > 1:
        for chunk in chunks:
            chunk_tokens = phonemize_japanese(chunk, prosody=prosody)  # ← 再帰
            ...
    # 単一チャンクの場合: HTS ラベル解析 + prosody マーク挿入
    labels = pyopenjtalk.extract_fullcontext(text)
    ...
```

この再帰構造では `phonemize_japanese()` 自体が分割ロジック + 単一文処理 + BOS/EOS 付与を兼ねており、`@lru_cache` を直接付与するとキャッシュキーに `custom_dict` オブジェクト (unhashable) が含まれて失敗する。

**必要なリファクタリング: 単一文処理の関数分離**

キャッシュを導入するには、まず単一文の音素化処理 (HTS ラベル解析 + prosody マーク挿入 + N バリアント適用 + `map_sequence()`) を `_phonemize_sentence_core()` として抽出し、再帰構造を解消する必要がある:

**変更点:**

1. `functools.lru_cache` を import
2. `phonemize_japanese()` の**単一文処理部分** (L189-253 の `prosody=False` 分岐 + `prosody=True` の HTS ラベル解析) を `_phonemize_sentence_core(sentence, prosody)` に抽出
3. `_phonemize_sentence_core()` をラップする `_phonemize_sentence_cached()` に `@lru_cache` を付与
4. キャッシュキーは `(sentence_text, prosody_flag)` のタプル
5. `phonemize_japanese()` は分割 + custom_dict 適用 + BOS/EOS 管理のみ担当し、各チャンクに対してキャッシュ版を呼び出す (再帰を解消)
6. `clear_phonemize_cache()` を公開

```python
# src/python_run/piper/phonemize/japanese.py (変更イメージ)

from functools import lru_cache

def _phonemize_sentence_core(sentence: str, prosody: bool) -> list[str]:
    """単一文 (分割済み) の音素化処理。BOS/EOS なし。
    
    phonemize_japanese() から抽出した HTS ラベル解析 + prosody マーク挿入 +
    N バリアント適用 + map_sequence() を担当する。
    """
    if not prosody:
        phoneme_str = pyopenjtalk.g2p(sentence)
        tokens = phoneme_str.split()
        tokens = _apply_n_phoneme_rules(tokens)
        return map_sequence(tokens)
    
    labels = pyopenjtalk.extract_fullcontext(sentence)
    tokens: list[str] = []
    # ... (既存の HTS ラベル解析ロジックをここに移動、BOS/EOS は含めない)
    tokens = _apply_n_phoneme_rules(tokens)
    return map_sequence(tokens)

@lru_cache(maxsize=2000)
def _phonemize_sentence_cached(sentence: str, prosody: bool) -> tuple[str, ...]:
    """単一文 (分割済み) の音素化結果をキャッシュする。"""
    return tuple(_phonemize_sentence_core(sentence, prosody=prosody))

def clear_phonemize_cache() -> None:
    """音素化キャッシュをクリアする。"""
    _phonemize_sentence_cached.cache_clear()
```

**`phonemize_japanese()` の変更 (再帰を解消):**

```python
def phonemize_japanese(
    text: str, custom_dict: CustomDictionary | None = None, prosody: bool = True
) -> list[str]:
    if custom_dict:
        text = custom_dict.apply(text)

    chunks = _split_long_text(text)
    if len(chunks) > 1:
        all_tokens: list[str] = []
        for chunk in chunks:
            chunk_tokens = list(_phonemize_sentence_cached(chunk, prosody))
            inner = [t for t in chunk_tokens if t not in ("^", "$", "?")]
            all_tokens.extend(inner)
        eos = _get_question_type(text) if prosody else "$"
        return map_sequence(["^"] + all_tokens + [eos])

    # 単一チャンク
    tokens = list(_phonemize_sentence_cached(text, prosody))
    eos = _get_question_type(text) if prosody else "$"
    return map_sequence(["^"] + tokens + [eos])
```

**リファクタリングの注意点:**

- 既存の `phonemize_japanese()` 内のコード (L189-253) をそのまま `_phonemize_sentence_core()` に移動するが、BOS (`"^"`) / EOS (`"$"`, `"?"` 系) は `phonemize_japanese()` 側で付与するよう変更する
- `_phonemize_sentence_core()` は `sil` ラベルを BOS/EOS に変換するロジックを**含めない** (外側で管理)
- 再帰呼び出し (`phonemize_japanese(chunk, prosody=prosody)`) をすべて `_phonemize_sentence_cached(chunk, prosody)` に置き換える

### 2-4. `voice.py` (python_run) の呼び出し側変更

`src/python_run/piper/voice.py` の `PiperVoice.phonemize()` は `phonemize_japanese()` を呼び出すだけなので、キャッシュは japanese.py 内部で自動適用される。呼び出し側の変更は不要。

### 2-5. キャッシュパラメータ

| パラメータ | 値 | 根拠 |
|-----------|-----|------|
| `maxsize` | 2000 | **典型ケース**: 文単位で ~100 文字/文 x 2000 = ~200KB キー + ~50 トークン/文 x 2000 = ~400KB 値。合計 ~1-2MB。**最悪ケース**: `_split_long_text()` の上限 (2000 文字) まで使い切るエントリが 2000 件の場合、2000 エントリ x 1000 文字平均 x 2B (UTF-16) = ~4MB キー + ~200 トークン/文 x 2000 = ~1.6MB 値。合計 ~2-4MB (プロセスメモリに対して無視可能) |
| スレッド安全性 | Python 3.2+ の `lru_cache` は内部ロック付き | GIL + `lru_cache` の `_lru_cache_wrapper` が atomic |
| 無効化 API | `clear_phonemize_cache()` | カスタム辞書変更時に呼び出し |

### 2-6. Rust 英語キャッシュとの対比 (参考)

Rust 実装 (`src/rust/piper-core/src/phonemize/english.rs`) では CMU 辞書の**ファイルレベル**キャッシュを bincode で永続化している:

| 項目 | Rust (英語辞書) | Python (日本語音素化) |
|------|----------------|---------------------|
| キャッシュ対象 | CMU 辞書 HashMap (~6MB) | 文ごとの音素化結果 (~50 トークン) |
| 格納形式 | bincode ファイル (`.json.bincode`) | メモリ内 LRU |
| 永続化 | あり (ディスク) | なし (プロセス内のみ) |
| 無効化 | ソース JSON の mtime 比較 | `cache_clear()` 手動呼び出し |
| スレッド安全性 | `OnceLock` (Rust) | `lru_cache` 内部ロック (Python) |

Rust と Python では用途が異なるが、「重い初期化/計算を 1 回だけ実行してキャッシュする」というパターンは共通。

---

## 3. エージェントチームの構成

本タスクは単一エージェントで完了可能な小規模変更。

| ロール | 担当 | 作業内容 |
|--------|------|---------|
| **実装エージェント** | 1名 | piper_train (G2P) + python_run 両パッケージの lru_cache 導入、テスト作成、lint 修正 |

**所要時間**: 約 1-2 時間

**作業順序:**

1. piper_train 側 (`src/python/g2p/piper_plus_g2p/japanese.py`) にキャッシュ導入 + `__all__` 更新
2. python_run 側 (`src/python_run/piper/phonemize/japanese.py`) の再帰構造を解消: `_phonemize_sentence_core()` 抽出 + キャッシュ導入
3. テスト作成
4. 既存テスト全 PASS 確認
5. lint / format チェック

---

## 4. 提供範囲とテスト

### 4.1 提供範囲 (スコープ)

**変更対象ファイル:**

| ファイル | 変更内容 |
|----------|---------|
| `src/python/g2p/piper_plus_g2p/japanese.py` | `_phonemize_core_cached()` + `clear_phonemize_cache()` 追加、`__all__` に `"clear_phonemize_cache"` 追加、`JapanesePhonemizer` のメソッドをキャッシュ版に切替 |
| `src/python_run/piper/phonemize/japanese.py` | `phonemize_japanese()` の再帰構造を解消: 単一文処理を `_phonemize_sentence_core()` に抽出、`_phonemize_sentence_cached()` + `clear_phonemize_cache()` 追加、各チャンクからキャッシュ版を呼び出す構造に変更 |
| `src/python/g2p/tests/test_japanese.py` (追記) | キャッシュ関連テスト追加 |
| `src/python_run/tests/test_japanese_phonemization.py` (追記) | キャッシュ関連テスト追加 |

**スコープ外:**

- Rust / C# / C++ 側のキャッシュ
- ディスク永続化
- 英語・中国語等 他言語のキャッシュ
- WebUI / Docker 側の呼び出し変更 (japanese.py 内部で自動適用のため不要)

### 4.2 ユニットテスト

以下のテストを `src/python/g2p/tests/test_japanese.py` (piper_train 側) および `src/python_run/tests/test_japanese_phonemization.py` (python_run 側) に追加する。

| テスト名 | 内容 | 検証方法 |
|----------|------|---------|
| `test_cache_hit_returns_same_result` | 同一文を 2 回呼出 → 結果が完全一致 | `assert result1 == result2` |
| `test_cache_hit_is_fast` | 同一文を 2 回呼出 → 2 回目は < 5ms | `time.perf_counter()` で計測、初回は warm-up |
| `test_cache_miss_different_text` | 異なる文 → 別の結果 | `assert result_a != result_b` |
| `test_cache_prosody_flag_separate` | `prosody=True` と `prosody=False` → 別キャッシュエントリ (**python_run のみ**) | cache_info の misses をチェック |
| `test_cache_clear` | `clear_phonemize_cache()` 後に再計算 | cache_info の hits/misses をリセット確認 |
| `test_cache_with_custom_dict` | カスタム辞書適用後のテキストがキャッシュキー | 辞書変更前後で異なる結果 |
| `test_existing_tests_unchanged` | 既存テスト全 PASS | 回帰テスト (既存テストの実行確認) |

**piper_train 側固有テスト:**

| テスト名 | 内容 |
|----------|------|
| `test_phonemize_core_cached_returns_tuples` | `_phonemize_core_cached()` が tuple を返すことを検証 |
| `test_phonemize_with_prosody_cached` | `phonemize_with_prosody()` がキャッシュを通して正しい `ProsodyInfo` を返す |

**python_run 側固有テスト:**

| テスト名 | 内容 |
|----------|------|
| `test_split_long_text_cache` | 長文分割後の各チャンクがキャッシュされる |
| `test_cache_info_stats` | `_phonemize_sentence_cached.cache_info()` で hits/misses を確認 |

### 4.3 E2E テスト

手動テストとして以下を実施:

| テスト | コマンド | 期待結果 |
|--------|---------|---------|
| 推論 (piper_train) | `uv run python -m piper_train.infer_onnx --model ... --text "こんにちは" --language ja ...` を 2 回実行 | 2 回目の音素化ステップが高速 (ログで確認) |
| 推論 (python_run) | `PiperVoice.synthesize()` で同一テキストを 2 回呼出 | 同一 WAV 出力、2 回目高速 |
| WebUI | 同一テキストで TTS を連続実行 | レスポンス時間の改善を体感確認 |

---

## 5. 懸念事項とレビュー項目

### 5.1 懸念事項

| # | 懸念 | 影響度 | 対策 |
|---|------|--------|------|
| 1 | **コンテキスト依存で prosody が不正確** | 中 | 文単位キャッシュで回避。`_split_long_text()` の分割境界は `。！？\n` で安定しており、同一文には同一コンテキストが保証される |
| 2 | **カスタム辞書変更後に古い結果が返る** | 中 | (a) カスタム辞書はキャッシュの**前**に適用されるため、辞書による変換後テキストがキャッシュキーとなる。(b) **カスタム辞書変更時は `clear_phonemize_cache()` を必ず呼び出すこと** (REQUIRED)。辞書エントリの追加・変更・削除によりキャッシュ内の古いエントリが不正な結果を返す可能性がある |
| 3 | **長時間稼働でメモリ増加** | 低 | `maxsize=2000` で上限あり。典型ケースで ~1-2MB、最悪ケース (2000 文字/エントリ) でも ~2-4MB。LRU 退去で自動管理 |
| 4 | **`lru_cache` の戻り値が共有参照** | 中 | `lru_cache` は同じオブジェクト参照を返す。呼び出し元が戻り値を変更すると全キャッシュが汚染される。**対策**: キャッシュ関数は immutable な `tuple` を返し、呼び出し側で `list()` に変換する |
| 5 | **piper_train 側に `_split_long_text()` がない** | 低 | piper_train の `JapanesePhonemizer` は `_phonemize_core()` を直接呼ぶため、OpenJTalk のバッファ上限 (~2700 chars) を超える入力は呼び出し元 (MultilingualPhonemizer の `TextSplitter` 等) で分割される前提。キャッシュキーは分割済みテキスト |
| 6 | **マルチプロセス環境 (DDP 学習) でキャッシュ共有不可** | 極低 | 学習時は音素化済み `phoneme_ids` を前処理で生成するため、推論時のキャッシュは影響なし |

### 5.2 レビューチェックリスト

- [x] `_phonemize_core_cached()` が **tuple** を返し、呼び出し側で `list()` に変換しているか (mutable aliasing 防止)
- [x] `@lru_cache(maxsize=2000)` のデコレータが正しい位置に付与されているか
- [x] `clear_phonemize_cache()` が `__all__` に含まれ、外部から呼び出し可能か (G2P 側の現在の `__all__` は `["JapanesePhonemizer"]` のみ — `"clear_phonemize_cache"` を追加すること)
- [x] カスタム辞書の `apply()` / `apply_to_text()` がキャッシュ参照の**前**に実行されているか
- [x] python_run 側で `prosody` フラグがキャッシュキーに含まれているか
- [x] piper_train 側で `ProsodyInfo` が正しく tuple 化/復元されているか (`ProsodyInfo` は `NamedTuple` or `dataclass` のため hashable か確認)
- [x] python_run 側で `phonemize_japanese()` の再帰構造が解消され、`_phonemize_sentence_core()` が正しく抽出されているか
- [x] 既存の全テスト (`test_japanese.py`, `test_japanese_phonemization.py`, `test_phonemize.py`) が変更なく PASS するか
- [x] `uv run ruff check && uv run ruff format --check` PASS
- [x] キャッシュヒット時のレイテンシ < 5ms (手動確認)

---

## 6. 一から作り直すとしたら

もしこの機能をゼロから設計し直すなら、以下のアプローチを検討する:

### 統一キャッシュレイヤー

現状は piper_train と python_run で**別々の**キャッシュ関数を実装する必要がある (パッケージが分離されているため)。理想的には:

1. **共通 G2P パッケージ (`piper_plus_g2p`) に一本化**: 現在 `src/python/g2p/` に新しい G2P パッケージが存在する。python_run 側をこのパッケージに依存させれば、キャッシュ実装は 1 箇所で済む
2. **キャッシュデコレータの共通化**: `@cached_phonemize(maxsize=2000)` のような汎用デコレータを作り、日本語以外の言語 (中国語の `pypinyin` 等) にも適用可能にする

### ディスク永続化 (bincode 方式)

Rust の英語 CMU 辞書キャッシュは bincode ファイルに永続化している。日本語音素化でも:

1. `shelve` / `diskcache` / `pickle` でディスクキャッシュを構築
2. プロセス再起動後もキャッシュヒット可能
3. ただし、pyopenjtalk のバージョン変更やカスタム辞書変更時のキャッシュ無効化が複雑になるため、現時点ではメモリ内 LRU が最もシンプルで安全

### OpenJTalk 呼び出しの最適化

キャッシュ以前の根本的なアプローチとして:

1. `extract_fullcontext()` の内部で MeCab + NJD パイプラインの一部をスキップする軽量版 API
2. jpreprocess (Rust) への移行で MeCab 呼び出し自体を高速化 (現在 WASM 版で実現済み)
3. ただしこれらは pyopenjtalk/jpreprocess の上流変更が必要で、本タスクのスコープ外

---

## 7. 後続タスクへの連絡事項

### M5 (最終統合) への引き継ぎ

1. **import パスの確認**: `clear_phonemize_cache` が以下の場所から正しく import 可能であること
   - `from piper_plus_g2p.japanese import clear_phonemize_cache`
   - `from piper.phonemize.japanese import clear_phonemize_cache`

2. **CI テスト**: 新規追加テストが CI マトリクス (3 OS x Python バージョン) で全 PASS すること。pyopenjtalk / pyopenjtalk-plus が CI 環境にインストールされている前提

3. **WebUI / Docker 推論サーバー**: キャッシュは japanese.py 内部で自動適用されるため、呼び出し側 (`docker/webui/app.py`, `docker/python-inference/inference.py`) の変更は不要。ただし、WebUI のカスタム辞書更新機能がある場合は、辞書更新時に `clear_phonemize_cache()` を呼び出す処理を追加すること

4. **ベンチマーク**: PR の description に以下のベンチマーク結果を記載すること
   - キャッシュミス時 (初回): X ms
   - キャッシュヒット時 (2 回目): X ms (< 1ms を期待)
   - `cache_info()` の hits/misses 統計

5. **ドキュメント更新**: `docs/guides/cpu-inference-optimization.md` の Tier 2 テーブルで施策 #4 を完了状態に更新すること

### Phase 2 への技術的メモ

- Rust 側でも同等の文単位キャッシュを導入する場合は `lru` クレート (or `moka`) の利用を検討
- C# 側は `System.Runtime.Caching.MemoryCache` または `ConcurrentDictionary` + LRU 退去で実装可能
- 日本語以外の言語 (中国語 `pypinyin`) も同一パターンでキャッシュ可能だが、中国語は音素化自体が軽量 (~5ms) なため優先度は低い
