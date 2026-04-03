# M4-3: G2P 単独利用 API

> **Phase:** 4 -- 拡張 (将来)
> **見積り:** 中
> **依存:** Phase 3 完了
> **ブロック:** なし (独立実装可能)
> **マイルストーン:** [c-api-milestones.md](../design/c-api-milestones.md#m4-3-g2p-単独利用-api)
> **要求定義書:** [c-api-shared-library.md](../design/c-api-shared-library.md)
> **技術調査:** [c-api-technical-investigation.md](../design/c-api-technical-investigation.md)
> **Status:** Open

---

## 1. タスク目的とゴール

テキストから音素列への変換 (G2P) を ONNX 推論なしで単独実行できる C API を追加する。TTS アプリケーション以外でも G2P 機能を利用したいケース (音素ベースの検索インデックス、発音辞書生成、学習データ前処理、リップシンク用音素列取得) に対応する。

**現状:** C++ 内部では `piper.cpp` L1067-1309 の音素化ループ (`textToAudio` 内) と各言語の `phonemize_*` 関数 (`openjtalk_phonemize.hpp`, `english_phonemize.hpp` 等) が利用可能。しかし、これらは `textToAudio()` の内部にインラインで埋め込まれており、C API から直接呼び出す手段がない。Rust 側では `piper-plus-g2p` クレートの `ffi.rs` が既に `piper_plus_g2p_create` / `piper_plus_g2p_phonemize` / `piper_plus_g2p_free` の C FFI を提供しているが、C++ 共有ライブラリでは未対応。

**ゴール:** C API に `piper_plus_phonemize()` 関数を追加し、テキストを音素 (IPA 文字列) に変換する機能を公開する。モデルロード済みのエンジンから G2P を呼び出す設計とし、各言語の辞書データ (CMU dict, pinyin dict, OpenJTalk) を自動的に利用する。

---

## 2. 実装する内容の詳細

### 2.1 ヘッダー追加 (`src/cpp/piper_plus.h`)

```c
/* ===== G2P (Phase 4) ===== */

/** Phonemize result. Owned by the engine; valid until next phonemize or synthesis call. */
typedef struct PiperPlusPhonemeResult {
    const char  *phonemes;       /* IPA phoneme string (UTF-8, space-separated) */
    const char  *language;       /* Detected/specified language code (e.g. "ja", "en") */
    int32_t      num_phonemes;   /* Number of phoneme tokens */
} PiperPlusPhonemeResult;

/** Phonemize text to IPA phonemes without ONNX inference.
 *  Uses the engine's loaded model config for phoneme mapping and language detection.
 *
 *  @param engine   A valid engine created by piper_plus_create().
 *  @param text     UTF-8 input text.
 *  @param language Language code ("ja", "en", "zh", etc.) or NULL for auto-detect.
 *  @param out      Caller-provided struct; callee fills fields.
 *  @return PIPER_PLUS_OK on success, PIPER_PLUS_ERR on failure. */
PIPER_PLUS_API int32_t piper_plus_phonemize(
    PiperPlusEngine             *engine,
    const char                  *text,
    const char                  *language,
    PiperPlusPhonemeResult      *out);

/** Get available language codes as comma-separated string (e.g. "ja,en,zh,es,fr,pt").
 *  The returned string is valid for the lifetime of the engine.
 *  @return Language list or NULL if engine is NULL. */
PIPER_PLUS_API const char *piper_plus_available_languages(
    const PiperPlusEngine *engine);
```

### 2.2 内部ストレージ (`src/cpp/piper_plus_c_api.cpp`)

**PiperPlusEngine 構造体拡張:**

```cpp
struct PiperPlusEngine {
    piper::PiperConfig config;
    piper::Voice       voice;
    bool               inProgress;
    // Phase 4: G2P 結果バッファ
    std::string g2pPhonemeStr;       // 音素文字列 (スペース区切り)
    std::string g2pLanguage;         // 検出/指定言語コード
    std::string availableLanguages;  // キャッシュ (初回構築)
};
```

### 2.3 音素化ロジックの抽出

`piper.cpp` L1067-1309 の音素化ループは `textToAudio()` 内にインラインで実装されている。M2-1 (音素化ループ抽出) が完了していれば抽出済みの `phonemizeText()` を利用する。M2-1 未完了の場合は、M4-3 内で以下のヘルパー関数を `piper.cpp` に追加する:

```cpp
namespace piper {

/** Phonemize text using the voice's configuration.
 *  Returns phonemes as a vector of Phoneme (char32_t) codepoints.
 *  Does NOT run ONNX inference. */
std::vector<Phoneme> phonemizeText(
    Voice &voice,
    const std::string &text,
    const std::string &language = "");

} // namespace piper
```

この関数は `textToAudio()` の L1067-1309 から音素化部分のみを抽出する。入力テキストの `[[ phoneme ]]` 記法パース、`UnicodeLanguageDetector` による言語セグメント分割、各言語の `phonemize_*` 関数呼び出しを含む。ONNX 推論 (L1319-) と音声合成部分は含まない。

### 2.4 `piper_plus_phonemize` 実装

```cpp
int32_t piper_plus_phonemize(
    PiperPlusEngine        *engine,
    const char             *text,
    const char             *language,
    PiperPlusPhonemeResult *out
) {
    if (!engine || !text || !out) {
        g_last_error = "NULL argument";
        return PIPER_PLUS_ERR;
    }
    PIPER_PLUS_TRY

    // カスタム辞書適用 (M4-1 が実装済みの場合)
    std::string processedText = text;
    if (engine->customDict) {
        processedText = engine->customDict->applyToText(processedText);
    }

    // 言語指定がある場合、synthesisConfig.languageId を一時的に設定
    auto savedLangId = engine->voice.synthesisConfig.languageId;
    if (language && language[0] != '\0') {
        if (engine->voice.modelConfig.languageIdMap) {
            auto it = engine->voice.modelConfig.languageIdMap->find(language);
            if (it != engine->voice.modelConfig.languageIdMap->end()) {
                engine->voice.synthesisConfig.languageId = it->second;
            }
        }
        engine->g2pLanguage = language;
    } else {
        engine->g2pLanguage = "auto";
    }

    // 音素化
    auto phonemes = piper::phonemizeText(engine->voice, processedText,
                                          language ? language : "");

    // 復元
    engine->voice.synthesisConfig.languageId = savedLangId;

    // Phoneme (char32_t) → UTF-8 文字列変換
    std::string phonemeStr;
    int count = 0;
    for (auto ph : phonemes) {
        if (!phonemeStr.empty()) phonemeStr += ' ';
        std::string utf8;
        utf8::append(static_cast<uint32_t>(ph), std::back_inserter(utf8));
        phonemeStr += utf8;
        count++;
    }

    engine->g2pPhonemeStr = std::move(phonemeStr);
    out->phonemes = engine->g2pPhonemeStr.c_str();
    out->language = engine->g2pLanguage.c_str();
    out->num_phonemes = count;

    PIPER_PLUS_CATCH(PIPER_PLUS_ERR)
    return PIPER_PLUS_OK;
}
```

### 2.5 変更対象ファイル

| ファイル | 変更内容 |
|----------|----------|
| `src/cpp/piper_plus.h` | `PiperPlusPhonemeResult` 構造体 + `piper_plus_phonemize()` + `piper_plus_available_languages()` 宣言 |
| `src/cpp/piper_plus_c_api.cpp` | `PiperPlusEngine` に G2P バッファ追加、`phonemize` + `available_languages` 実装 |
| `src/cpp/piper.hpp` | `phonemizeText()` 関数宣言 (M2-1 未完了の場合) |
| `src/cpp/piper.cpp` | `phonemizeText()` 関数実装 (L1067-1309 から抽出。M2-1 未完了の場合) |
| `src/cpp/tests/test_c_api.cpp` | G2P テストケース追加 |

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当内容 |
|------|------|----------|
| 実装エージェント | 1 | 音素化ロジック抽出 + C API ラッパー + テスト |
| レビューエージェント | 1 | Rust `ffi.rs` との API 整合性レビュー |

合計 2 名。音素化ロジックの抽出は `textToAudio()` 内部の複雑なコードを扱うため、M2-1 との依存に注意が必要。

---

## 4. 提供範囲とテスト項目

### スコープ

- C API に G2P 関数を追加 (`piper_plus_phonemize`, `piper_plus_available_languages`)
- 全 8 言語 (JA, EN, ZH, KO, ES, FR, PT, SV) の音素化に対応
- `[[ phoneme ]]` インライン音素記法のパススルー
- カスタム辞書 (M4-1) との統合 (M4-1 が先行実装された場合)

### ユニットテスト (モデル不要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestPhonemizeNullEngine` | `piper_plus_phonemize(NULL, ...)` | `PIPER_PLUS_ERR` + クラッシュなし |
| `TestPhonemizeNullText` | `piper_plus_phonemize(engine, NULL, ...)` | `PIPER_PLUS_ERR` |
| `TestPhonemizeNullOutput` | `piper_plus_phonemize(engine, text, NULL)` | `PIPER_PLUS_ERR` |
| `TestAvailableLanguagesNull` | `piper_plus_available_languages(NULL)` | `NULL` |
| `TestPhonemeResultLayout` | `PiperPlusPhonemeResult` のサイズ確認 | Dart ffigen 互換 |

### E2E テスト (モデル必要)

| テスト | 内容 | 期待結果 |
|--------|------|----------|
| `TestPhonemizeJapanese` | 「こんにちは」を音素化 | 有効な IPA 音素列、`language == "ja"` |
| `TestPhonemizeEnglish` | "Hello world" を音素化 | 有効な IPA 音素列、`language == "en"` |
| `TestPhonemizeAutoDetect` | `language = NULL` で混合テキスト | 言語自動検出が動作 |
| `TestPhonemizeInlinePhonemes` | `[[ h e l o ]]` 記法 | 音素がパススルーされる |
| `TestAvailableLanguages` | 多言語モデルで言語一覧取得 | "ja,en,zh,es,fr,pt" 等のカンマ区切り文字列 |
| `TestPhonemizeThenSynthesize` | G2P 呼び出し後に合成 | 合成が正常に動作すること (状態破壊なし) |

---

## 5. 懸念事項とレビュー項目

### 懸念事項

| リスク | 影響度 | 対策 |
|--------|--------|------|
| `textToAudio` 内の音素化ループの抽出難易度 | 高 | L1067-1309 は言語検出、OpenJTalk 呼び出し、BOS/EOS ストリッピング、prosody 計算が混在。M2-1 の `phonemizeText()` 抽出が前提。M2-1 が未完了なら M4-3 内で抽出するが、工数が増加する |
| `synthesisConfig.languageId` の副作用 | 中 | `phonemizeText()` 内で `detectDominantLanguage()` が `voice.synthesisConfig.languageId` を変更する (L1279)。呼び出し前に save、呼び出し後に restore が必須 |
| Rust `ffi.rs` との API 名衝突 | 中 | Rust FFI は `piper_plus_g2p_phonemize` (g2p プレフィックス付き)、C API は `piper_plus_phonemize` (エンジンベース) で名前が異なる。同一プロセスで両方ロードしてもシンボル衝突しない |
| CMU dict / pinyin dict の依存 | 低 | EN は CMU dict、ZH は pinyin dict が `loadVoice()` 時に `voice.cmuDict` / `voice.pinyinSingleDict` にロードされる。エンジン作成時にモデルをロードしていれば辞書も利用可能 |
| 日本語 OpenJTalk の辞書依存 | 低 | JA 音素化は OpenJTalk 辞書が必要。Phase 1 の `dict_dir` 設定で解決済み |

### レビュー時の確認項目

1. `phonemizeText()` の抽出が `textToAudio()` に副作用を与えないこと
2. G2P 呼び出し後に `synthesisConfig` が完全に復元されること
3. 返却される `phonemes` ポインタの寿命が明確であること (次回 `phonemize` or `synthesize` まで)
4. Rust `ffi.rs` の API 設計 (JSON 返却) と C API (構造体返却) の設計差異が意図的であること
5. `piper_plus_available_languages()` が `modelConfig.languageIdMap` を正しく参照すること

---

## 6. 一から作り直すとしたら

**エンジン非依存の G2P API:** 現在の設計は「モデルロード済みエンジン」に紐づく G2P だが、G2P はモデル非依存の機能である。Rust `piper-plus-g2p` の `ffi.rs` はまさにエンジン非依存の設計 (`PiperG2pHandle` はモデルなし)。

理想的には C API でも独立した G2P ハンドルを提供すべき:

```c
typedef struct PiperPlusG2pHandle PiperPlusG2pHandle;

PiperPlusG2pHandle *piper_plus_g2p_create(const char *languages, const char *dict_dir);
int32_t             piper_plus_g2p_phonemize(PiperPlusG2pHandle *h, const char *text,
                                              const char *language, PiperPlusPhonemeResult *out);
void                piper_plus_g2p_free(PiperPlusG2pHandle *h);
```

ただし、これは C++ の各 `phonemize_*` 関数を独立して初期化可能にするリファクタリングが必要 (現在は `loadVoice()` 内で CMU dict 等がロードされる)。Phase 4 ではエンジン紐づきの簡易版で十分だが、将来的にはエンジン非依存版も検討すべき。

**Rust FFI との統合:** Rust `piper-plus-g2p` は既に `piper_plus_g2p_*` の C FFI を提供している。C++ 共有ライブラリの G2P API と統合するか、それぞれ独立して提供するかの判断が必要。現時点では独立提供 (C++ は `piper_plus_phonemize`、Rust は `piper_plus_g2p_phonemize`) が適切。

---

## 7. 後続タスクへの連絡事項

- **M2-1 (音素化ループ抽出) との依存:** M2-1 で `phonemizeText()` が抽出されていれば M4-3 の工数が大幅に削減される。M2-1 が未完了の場合、M4-3 で抽出を行い、M2-1 のスコープに反映する。
- **M4-1 (カスタム辞書) との統合:** G2P API でもカスタム辞書を適用する。`piper_plus_phonemize()` 内で `customDict->applyToText()` を呼ぶ。
- **出力形式:** 現在の設計はスペース区切り IPA 文字列。将来的に `phoneme_ids` (整数配列) の出力も求められる可能性がある。`PiperPlusPhonemeResult` の `_reserved` フィールドで拡張可能にしておく。
- **Rust FFI との命名規則:** C++ C API は `piper_plus_phonemize` (エンジンベース)、Rust FFI は `piper_plus_g2p_phonemize` (独立ハンドル)。同一プロセスでの混在利用時にシンボル衝突しない。
