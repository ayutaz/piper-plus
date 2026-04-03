# M4-1: カスタム辞書 API

> **Phase:** 4 -- 拡張 (将来)
> **利用者視点の優先度:** 高 -- 技術用語の発音修正は全利用者に必要
> **見積り:** 中
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-1-カスタム辞書-api)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

既存の C++ `CustomDictionary` クラス (`src/cpp/custom_dictionary.cpp`) を C API でラップし、共有ライブラリ利用者がカスタム辞書をランタイムで読み込み・管理できるようにする。

**現状:** `custom_dictionary.hpp` は C++ クラスとして `loadDictionary()`, `addWord()`, `removeWord()`, `applyToText()` 等のメソッドを提供しているが、C API 境界に公開されていない。Rust / C# / CLI はそれぞれ独自にカスタム辞書を実装済みだが、C API 共有ライブラリ経由で利用する Flutter/Dart/Godot からはアクセス不可。

**ゴール:** C API に辞書の読み込み・クリア・個別単語登録・テキスト前処理の 4 関数を追加し、JSON v1.0/v2.0 形式の辞書ファイルをランタイムで利用可能にする。

---

## 2. 実装する内容の詳細

### 2.1 ヘッダー追加 (`src/cpp/piper_plus.h`)

```c
/* ===== Custom Dictionary (Phase 4) ===== */

/** Load a custom dictionary from JSON file (v1.0/v2.0 format).
 *  Multiple calls accumulate entries; later entries override earlier ones
 *  for the same word based on priority.
 *  @return PIPER_PLUS_OK on success, PIPER_PLUS_ERR on failure. */
PIPER_PLUS_API int32_t piper_plus_load_custom_dict(
    PiperPlusEngine *engine,
    const char      *dict_path);

/** Clear all custom dictionary entries (including defaults). */
PIPER_PLUS_API int32_t piper_plus_clear_custom_dict(
    PiperPlusEngine *engine);

/** Add a single word/pronunciation pair at runtime.
 *  @param priority 0-10 (higher = takes precedence). Default: 5. */
PIPER_PLUS_API int32_t piper_plus_add_dict_word(
    PiperPlusEngine *engine,
    const char      *word,
    const char      *pronunciation,
    int32_t          priority);

/** Get the number of currently loaded dictionary entries. */
PIPER_PLUS_API int32_t piper_plus_dict_entry_count(
    const PiperPlusEngine *engine);
```

### 2.2 C API 実装 (`src/cpp/piper_plus_c_api.cpp`)

**PiperPlusEngine 構造体拡張:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice       voice;
    bool               inProgress;
    // Phase 4: カスタム辞書
    std::unique_ptr<piper::CustomDictionary> customDict;
};
```

**関数実装:**

- `piper_plus_load_custom_dict`: NULL チェック -> `customDict` が未初期化なら `std::make_unique<CustomDictionary>()` で生成 -> `customDict->loadDictionary(dict_path)` を呼び出し。例外は `PIPER_PLUS_CATCH` で捕捉。
- `piper_plus_clear_custom_dict`: `customDict.reset()` で辞書を破棄。
- `piper_plus_add_dict_word`: `customDict->addWord(word, pronunciation, priority)` をラップ。`customDict` が未初期化なら自動生成。
- `piper_plus_dict_entry_count`: `customDict->getStats().totalEntries` を返す。NULL なら 0。

**合成時のテキスト前処理:**

`piper_plus_synthesize` / `piper_plus_synth_start` の内部で、テキストを `textToAudio()` に渡す前に `customDict->applyToText(text)` を適用する。

```cpp
// synthesize 内部 (疑似コード)
std::string processedText = text;
if (engine->customDict) {
    processedText = engine->customDict->applyToText(processedText);
}
piper::textToAudio(engine->config, engine->voice, processedText, ...);
```

### 2.3 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | 4 関数の宣言を追加 |
| `src/cpp/piper_plus_c_api.cpp` | 4 関数の実装 + 合成時の `applyToText()` 呼び出し |
| `src/cpp/tests/test_c_api.cpp` | カスタム辞書テストケース追加 |

**変更不要:** `custom_dictionary.cpp` / `custom_dictionary.hpp` は既存のまま利用。

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | C API ラッパー実装 + テスト |

合計 1 名。既存の `CustomDictionary` クラスをラップするだけで新規ロジックは不要。

---

## 4. 提供範囲とテスト項目

### スコープ

- C API に辞書管理関数 4 つを追加
- 合成パイプラインへの辞書テキスト前処理の統合
- テスト用 JSON 辞書ファイル作成

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestLoadCustomDictNull` | `piper_plus_load_custom_dict(NULL, ...)` | `PIPER_PLUS_ERR` + クラッシュなし |
| `TestLoadCustomDictInvalidPath` | 存在しないパスで辞書読み込み | `PIPER_PLUS_ERR` + `get_last_error()` にメッセージ |
| `TestClearCustomDictNull` | `piper_plus_clear_custom_dict(NULL)` | `PIPER_PLUS_ERR` + クラッシュなし |
| `TestAddDictWordNull` | NULL エンジンへの単語追加 | `PIPER_PLUS_ERR` |
| `TestDictEntryCountNull` | NULL エンジンのエントリ数 | 0 |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestLoadAndSynthesize` | 辞書ロード -> 合成 -> テキストが辞書で変換されること | 辞書エントリ数 > 0 + 合成成功 |
| `TestAddWordAndSynthesize` | `add_dict_word("GPU", "ジーピーユー", 5)` -> JA テキスト合成 | 合成成功 |
| `TestClearAndSynthesize` | 辞書ロード -> クリア -> 合成 | エントリ数 = 0 + 合成成功 (辞書なし) |
| `TestMultipleDictFiles` | 2 つの辞書を順次ロード | 両方のエントリが有効 |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `CustomDictionary` のデフォルト辞書パス | 中 | `CustomDictionary()` コンストラクタが `findDictDir()` で `getDictExeDir()` を使う。共有ライブラリではホストアプリのパスが返るため、デフォルト辞書が見つからない。対策: C API 経由では空の辞書から開始し、明示的な `load_custom_dict()` を推奨 |
| 正規表現パフォーマンス | 低 | `applyToText()` は辞書エントリごとに `std::regex_replace` を実行。大量のエントリでは遅くなる可能性があるが、典型的な辞書サイズ (数百エントリ) では問題なし |
| スレッドセーフティ | 低 | `CustomDictionary` はスレッドセーフではないが、`PiperPlusEngine` 自体が単一スレッド利用前提のため問題なし |

### レビュー時の確認項目

1. `customDict` の lazy initialization が正しく動作すること (`load` / `add_dict_word` の両方で)
2. 合成パイプラインで `applyToText()` がストリーミング/Iterator の両方で適用されること
3. NULL ポインタチェックが全関数にあること
4. JSON v1.0 / v2.0 の両形式のテストがあること
5. `piper_plus_clear_custom_dict` 後にエンジンが正常に合成できること

---

## 6. 一から作り直すとしたら

**辞書適用のレイヤー配置:** 現在の `CustomDictionary::applyToText()` はテキストレベルの文字列置換 (正規表現ベース) で実装されている。より正確な G2P 統合を目指すなら、音素化パイプラインの内部 (単語分割後、G2P 変換前) で辞書を参照する方が適切。ただし、これは `piper.cpp` の `textToAudio()` 内部の大幅なリファクタリングが必要であり、Phase 4 の範囲を超える。

**代替設計:** Rust `piper-plus-g2p` の `ffi.rs` は辞書を `PhonemizerRegistry` に統合する設計。C API でも同様に `piper_plus_create()` の `PiperPlusConfig` に `custom_dict_paths` フィールドを追加し、エンジン作成時に辞書を初期化する方法もある。ただし、ランタイムの辞書追加・削除ができなくなるトレードオフがある。

---

## 7. 後続タスクへの連絡事項

- **M4-3 (G2P 単独 API):** G2P API でもカスタム辞書を適用したい場合、`piper_plus_phonemize()` 内でも `applyToText()` を呼ぶ必要がある。M4-3 の実装時に考慮すること。
- **デフォルト辞書のパス問題:** 共有ライブラリでは `findDictDir()` の `getDictExeDir()` がホストアプリのパスを返す問題がある (M4-6 の `dladdr` 改善で解消予定)。M4-6 完了後にデフォルト辞書の自動読み込みも検討可能。
- **辞書フォーマット:** 現在は JSON v1.0/v2.0 のみ対応。TSV 形式 (C# 実装で対応済み) の追加は将来検討。
