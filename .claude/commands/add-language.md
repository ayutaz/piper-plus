# 新言語追加ガイド

新しい言語を piper-plus に追加するためのガイドです。引数 `$ARGUMENTS` に言語コード (例: `de`, `it`, `da`) を指定してください。

## 前提条件

- Python テストは `uv run python -m pytest` で実行
- 各タスク完了ごとにコミット
- Python が参照実装、他言語は 1:1 ミラー
- eSpeak-ng 不使用 (MIT ライセンス維持)

## Phase 1: Python 音素定義 + G2P エンジン

### 1.1 音素インベントリ + PUA 割り当て

**新規作成:** `src/python/g2p/piper_plus_g2p/$ARGUMENTS.py`

```python
from .base import Phonemizer
# Implement the phonemizer class here. Register it in `registry.py`; the
# shared ID map is maintained in `encode/id_maps.py` and PUA data in
# `encode/pua.py` / `data/pua.json`.
```

**修正:** `src/python/g2p/piper_plus_g2p/encode/pua.py` と `data/pua.json`

- `FIXED_PUA_MAPPING` に PUA エントリ追加
- 現在の最終固定 PUA: PT = 0xE064 (`ɔɪ`=0xE062、`œ̃`=0xE063、`ɐ̃`=0xE064)、動的割り当て開始 = 0xE065
- 新言語は **0xE065 以降** に割り当て
- `_PUA_START` を新言語の最終 PUA + 3 に更新 (将来拡張用)

**衝突チェック:**

```text
JA: 0xE000-0xE01C (29), ZH: 0xE020-0xE04A (43), KO: 0xE04B-0xE052 (8)
ES/PT: 0xE054-0xE055 (2), FR: 0xE056-0xE058 (3), SV: 0xE059-0xE061 (9)
```

### 1.2 G2P エンジン作成

**新規作成:** `src/python/g2p/piper_plus_g2p/$ARGUMENTS.py`

必須クラス:

```python
class [Lang]Phonemizer(Phonemizer):
    def phonemize(self, text: str) -> list[str]: ...
    def phonemize_with_prosody(self, text: str) -> tuple[list[str], list[ProsodyInfo | None]]: ...
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        return None  # multilingual id_map を使用
```

G2P パイプライン (言語に応じて調整):

1. テキスト正規化 (NFC + lowercase)
2. トークン化 (単語/句読点分離)
3. 辞書ルックアップ (オプション)
4. 借用語ルール (接尾辞検出)
5. ネイティブ音素変換 (子音 + 母音)
6. 後処理 (同化、ストレスマーカー)

Prosody: `a1=0, a2=stress(0/1/2), a3=word_phoneme_count`

### 1.3 レジストリ + 多言語統合

**修正:** `src/python/g2p/piper_plus_g2p/registry.py`

```python
try:
    from .$ARGUMENTS import [Lang]Phonemizer
    register_language("$ARGUMENTS", [Lang]Phonemizer())
except ImportError:
    pass
```

- ラテン文字言語なら `latin_langs` にも追加

**修正:** `src/python/g2p/piper_plus_g2p/encode/id_maps.py`

```python
# Add the language inventory to the shared map and update
# `get_phoneme_id_map()` in encode/id_maps.py.
```

**修正 (ラテン文字言語のみ):** `src/python/g2p/piper_plus_g2p/multilingual.py`

- `_[LANG]_CHARS` 文字セット追加 (言語固有文字)
- `_[LANG]_FUNCTION_WORDS` 関数語セット追加 (~45語)
- `_refine_latin_segments_for_[lang]()` 精算関数追加
- `UnicodeLanguageDetector` に検出ロジック追加

### 1.4 推論パス対応

**修正:** `src/python/piper_train/infer_onnx.py`

- `--language` ヘルプテキストに `$ARGUMENTS` 追加
- `_DominantLanguageDetector.detect()` に新言語精算追加 (ラテン文字の場合)

**修正:** `src/python/piper_train/tools/prepare_multilingual_dataset.py`

- `LANGUAGE_ID_MAP` に `"$ARGUMENTS": N` 追加
- `ALL_LANGUAGES` に `"$ARGUMENTS"` 追加

### 1.5 Python テスト

**新規作成:** `src/python/g2p/tests/test_$ARGUMENTS.py` (または既存テストモジュールへの追加)

- 基本母音テスト (10+)
- 子音ルールテスト (15+)
- 言語固有ルール (20+)
- ストレス/韻律テスト (10+)
- 借用語テスト (10+)
- エッジケース (5+)
- 多言語検出テスト (5+)
- 全テスト `@pytest.mark.unit`

**新規作成:** `src/python/g2p/tests/test_$ARGUMENTS_contract.py` (必要な契約テスト)

- 音素インベントリ数チェック
- PUA 割り当て検証
- `_PUA_START` 検証
- 双方向マッピングテスト
- 7lang → Nlang ID マップテスト

実行: `cd src/python/g2p && uv run pytest tests/ -x -q`

---

## Phase 2: Rust 実装

**新規作成:** `src/rust/piper-core/src/phonemize/$ARGUMENTS.rs`

- Python 参照実装の全ルールを移植
- `Phonemizer` trait 実装

**修正:**

- `src/rust/piper-core/src/phonemize/mod.rs` — `pub mod $ARGUMENTS;`
- `src/rust/piper-core/src/voice.rs` — `"$ARGUMENTS"` ケース追加 + default_latin
- `src/rust/piper-plus-g2p/src/token_map.rs` — PUA エントリ追加 (core はこの module を re-export)
- `src/rust/piper-plus-g2p/src/multilingual.rs` — 言語検出追加 (ラテン文字; core は re-export)
- `src/rust/piper-cli/src/main.rs` — `SUPPORTED_LANGUAGES` に追加

テスト: `#[cfg(test)]` セクションに 30+ テスト、`cargo fmt` + `cargo clippy` 実行

---

## Phase 3: C++ 実装

**新規作成:**

- `src/cpp/$ARGUMENTS_phonemize.hpp` — ヘッダ
- `src/cpp/$ARGUMENTS_phonemize.cpp` — 全G2Pルール実装
- `src/cpp/tests/test_$ARGUMENTS_phonemize.cpp` — GoogleTest

**修正:**

- `src/cpp/piper.cpp` — `#include` + `"$ARGUMENTS"` ディスパッチ
- `src/cpp/language_detector.cpp/.hpp` — 言語検出 (ラテン文字)
- `CMakeLists.txt` — ソースファイル追加
- `src/cpp/tests/CMakeLists.txt` — テストターゲット追加

---

## Phase 4: C# 実装

**新規作成:**

- `src/csharp/PiperPlus.Core/Phonemize/[Lang]G2PEngine.cs` — フルG2Pエンジン
- `src/csharp/PiperPlus.Core/Phonemize/[Lang]Phonemizer.cs` — IPhonemizer ラッパー
- `src/csharp/PiperPlus.Core/Phonemize/I[Lang]G2PEngine.cs` — インターフェース
- `src/csharp/PiperPlus.Core.Tests/[Lang]PhonemizerTests.cs` — xUnit テスト

**修正:**

- `src/csharp/PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` — PUA エントリ追加
- `src/csharp/PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` — 検出追加 (ラテン文字)
- `src/csharp/PiperPlus.Cli/Program.cs` — `case "$ARGUMENTS":` 追加

テスト: `dotnet test --filter "[Lang]"` で 40+ テスト通過確認

---

## Phase 5: JS/WASM 実装

**修正:** `src/wasm/openjtalk-web/src/index.js`

- 文字検出セット + 関数語セット追加
- `_refineLatinSegmentsFor[Lang]()` 追加 (ラテン文字)
- `_classifyChar()` 拡張 (非ラテン文字)

**新規作成:** `src/wasm/openjtalk-web/test/js/test-$ARGUMENTS.js`

- 文字検出、関数語、スコアリング、混合言語テスト (30+)

**修正:** `src/wasm/openjtalk-web/types/index.d.ts` — Language 型に追加

---

## Phase 6: CI + ドキュメント

### CI

- `.github/workflows/cpp-tests.yml` — テスト実行リストに追加
- `.github/workflows/ci.yml` — テスト実行リストに追加
- `.github/workflows/dev-build-all.yml` — スモークテストに追加

### ドキュメント

- `CLAUDE.md` — フォネマイザーテーブル + ファイルパス追加
- `README.md`, `README_EN.md`, `README_ZH.md`, `README_FR.md` — 言語数更新
- `src/wasm/openjtalk-web/README.npm.md` — 言語テーブル追加
- `src/python_run/setup.py` — 言語リスト更新
- `docker/cpp-dev/Dockerfile` — コメント更新

---

## 実装順序 (依存関係)

```text
Phase 1.1 (音素定義) → Phase 1.2 (Python G2P) → Phase 1.3 (統合)
                                                    ↓
                                    ┌───────────────┼───────────────┐
                                    ↓               ↓               ↓
                              Phase 2 (Rust)  Phase 3 (C++)  Phase 4 (C#)
                                    ↓               ↓               ↓
                                    └───────────────┼───────────────┘
                                                    ↓
                                            Phase 5 (JS/WASM)
                                                    ↓
                                            Phase 6 (CI + Docs)
```
