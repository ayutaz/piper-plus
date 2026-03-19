# C++ マルチリンガル Phonemizer 調査レポート

## 調査日: 2026-03-18

## 1. 問題の概要

Windows ビルド (v1.7.0) でテストした結果、**日本語のみ正常動作**し、他5言語 (EN/ZH/ES/FR/PT) は `No native phonemizer for language 'xx'; skipping segment` で空WAVを生成。

| 言語 | 結果 | WAVサイズ | エラー |
|------|------|----------|--------|
| ja | OK | 115KB | なし |
| en | NG | 44B (空) | `No native phonemizer for language 'en'` |
| zh | NG | 44B (空) | `No native phonemizer for language 'zh'` + OpenJTalkフォールバック失敗 |
| es | NG | 44B (空) | `No native phonemizer for language 'en'` (誤検出) |
| fr | NG | 44B (空) | `No native phonemizer for language 'en'` (誤検出) |
| pt | NG | 44B (空) | `No native phonemizer for language 'en'` (誤検出) |

---

## 2. 調査結果: C++側の既存実装

### 2.1 既にC++ファイルが存在する

調査の結果、**全6言語のC++ phonemizerファイルは既に存在**:

| 言語 | ヘッダ | 実装 | 外部依存 |
|------|--------|------|---------|
| ja | `openjtalk_phonemize.hpp` | `openjtalk_phonemize.cpp` | OpenJTalk C API |
| en | `english_phonemize.hpp` | `english_phonemize.cpp` (638行) | CMU辞書 (JSON) |
| zh | `chinese_phonemize.hpp` | `chinese_phonemize.cpp` (820行) | pypinyin辞書 (JSON) |
| es | `spanish_phonemize.hpp` | `spanish_phonemize.cpp` | なし (規則ベース) |
| fr | `french_phonemize.hpp` | `french_phonemize.cpp` | なし (規則ベース) |
| pt | `portuguese_phonemize.hpp` | `portuguese_phonemize.cpp` | なし (規則ベース) |
| ko | `korean_phonemize.hpp` | `korean_phonemize.cpp` | なし (Hangul分解) |

### 2.2 CMakeLists.txt にもソースが登録済み

```cmake
add_executable(piper
  src/cpp/main.cpp src/cpp/piper.cpp src/cpp/phoneme_parser.cpp
  src/cpp/language_detector.cpp
  src/cpp/openjtalk_phonemize.cpp src/cpp/openjtalk_phonemize_utils.cpp
  src/cpp/english_phonemize.cpp src/cpp/chinese_phonemize.cpp
  src/cpp/korean_phonemize.cpp src/cpp/spanish_phonemize.cpp
  src/cpp/french_phonemize.cpp src/cpp/portuguese_phonemize.cpp
  ...)
```

### 2.3 piper.cpp のディスパッチロジックも存在

`piper.cpp` (行1109-1138) に言語別分岐が実装済み:

```cpp
if (langSeg.lang == "ja") {
    phonemize_openjtalk(langSeg.text, langPhonemes);
} else if (langSeg.lang == "es") {
    phonemize_spanish(langSeg.text, langPhonemes);
} else if (langSeg.lang == "fr") {
    phonemize_french(langSeg.text, langPhonemes);
} else if (langSeg.lang == "pt") {
    phonemize_portuguese(langSeg.text, langPhonemes);
} else if (langSeg.lang == "en" && !voice.cmuDict.empty()) {
    phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
} else if (langSeg.lang == "zh" && !voice.pinyinSingleDict.empty()) {
    phonemize_chinese(langSeg.text, langPhonemes, ...);
} else if (langSeg.lang == "ko") {
    phonemize_korean(langSeg.text, langPhonemes);
}
```

---

## 3. 根本原因の特定

### 3.1 英語 — CMU辞書が見つからない

英語phonemizerは `!voice.cmuDict.empty()` を条件にしている。CMU辞書のロードは `loadVoice()` で実行:

```cpp
std::string cmuPath = modelDir + "/cmudict_data.json";
if (std::filesystem::exists(cmuPath)) {
    loadCmuDict(cmuPath, voice.cmuDict);
}
```

テストモデル (`test/models/multilingual-test-medium.onnx`) のディレクトリに `cmudict_data.json` が**存在しない**ため、英語phonemizerが起動しない。

### 3.2 中国語 — pypinyin辞書が見つからない

同様に:

```cpp
std::string pinyinSinglePath = modelDir + "/pinyin_single.json";
std::string pinyinPhrasePath = modelDir + "/pinyin_phrases.json";
if (std::filesystem::exists(pinyinSinglePath)) {
    loadPinyinDicts(pinyinSinglePath, pinyinPhrasePath, ...);
}
```

テストモデルディレクトリに `pinyin_single.json` / `pinyin_phrases.json` が**存在しない**。

### 3.3 スペイン語/フランス語/ポルトガル語 — 言語検出の問題

ログを見ると ES/FR/PT テキストが `No native phonemizer for language 'en'` と出力されている。

**原因**: UnicodeLanguageDetector はラテン文字を `defaultLatinLang` ("en") として検出。ES/FR/PT テキストもラテン文字なので全て "en" として分類される。英語phonemizerが辞書なしで起動できないため、全体がスキップされる。

**根本**: `--language` CLI引数が言語検出を上書きしていない、もしくは上書きロジックに問題がある。

### 3.4 まとめ

| 問題 | 影響言語 | 原因 |
|------|---------|------|
| CMU辞書不在 | en | `cmudict_data.json` がモデルディレクトリにない |
| pypinyin辞書不在 | zh | `pinyin_single.json` / `pinyin_phrases.json` がない |
| 言語検出がラテン→en固定 | es, fr, pt | `--language` がdetectorの `defaultLatinLang` を上書きしていない |
| 辞書なし時のフォールバックなし | en, zh | 辞書がない場合にwarningのみで音素が空 |

---

## 4. 修正方針

### Phase 1: 辞書バンドル + フォールバック (最優先)

1. **CMU辞書・pypinyin辞書をビルドアーティファクトに含める**
   - `cmudict_data.json` → `piper/share/` or モデル同梱
   - `pinyin_single.json` / `pinyin_phrases.json` → 同上
   - ビルドワークフロー (`build-piper.yml`) で辞書ファイルをコピー

2. **辞書検索パスの拡充**
   - モデルディレクトリ → exe相対パス (`share/`) → 環境変数 の順で探索

3. **辞書なし時のフォールバック**
   - 英語: 辞書なしでもbasic letter-to-phoneme変換で最低限動作
   - 中国語: 辞書なし時のwarningをより明確に

### Phase 2: 言語指定の修正

4. **`--language` CLI引数で `defaultLatinLang` を設定**
   - `--language es` 指定時 → detector の `defaultLatinLang = "es"`
   - ラテン文字テキストが正しくES/FR/PTとして検出される

5. **マルチリンガルモデルでの言語自動切り替え**
   - `config.json` の `language_id_map` からサポート言語を取得
   - 単一ラテン言語のみの場合はそれを `defaultLatinLang` に

### Phase 3: テスト・検証

6. **テストモデルに辞書を同梱**
   - `test/models/` に `cmudict_data.json`, `pinyin_single.json`, `pinyin_phrases.json`

7. **CIテスト拡充**
   - 全6言語の推論テストをCI (`test_multilingual_g2p.cpp`) に追加

---

## 5. Python vs C++ 実装対応表

### 5.1 英語 (g2p-en → CMU辞書)

| 機能 | Python | C++ | 一致 |
|------|--------|-----|------|
| ARPAbet→IPA変換 | `ARPABET_TO_IPA` (47エントリ) | `arpaToIpa()` テーブル | 要確認 |
| 文脈依存ルール (AA+R, ER stressed, AH unstressed) | `_convert_word_to_ipa()` | 実装あり | 要確認 |
| 機能語脱ストレス (97語) | `_FUNCTION_WORDS` | 実装あり | 要確認 |
| ストレスマーカー (ˈ, ˌ) | IPA U+02C8, U+02CC | 同上 | 一致 |
| 形態素フォールバック (-ing, -ed, -s) | `tryMorphologicalFallback()` | 実装あり | 要確認 |

### 5.2 中国語 (pypinyin → 辞書)

| 機能 | Python | C++ | 一致 |
|------|--------|-----|------|
| Pinyin正規化 (y/w/v→ü) | `_normalize_pinyin()` | 実装あり | 要確認 |
| トーン砂音 (T3+T3, yi, bu) | `_apply_tone_sandhi()` (4ルール) | 実装あり | 要確認 |
| Initial→IPA | テーブル (b→p, p→pʰ, etc.) | テーブル | 要確認 |
| Final→IPA | 複合韻母テーブル | テーブル | 要確認 |
| トーンマーカー (tone1-5) | PUA E046-E04A | PUA E046-E04A | 一致 |
| 児化音処理 | `_handle_erhua()` | 実装あり | 要確認 |

### 5.3 スペイン語 (規則ベース)

| 機能 | Python | C++ | 一致 |
|------|--------|-----|------|
| セセオ (c/z→/s/) | 実装済み | 要確認 | — |
| Yeísmo (ll→/ʝ/) | 実装済み | 要確認 | — |
| 音節化 | `_find_syllable_boundaries()` | 要確認 | — |
| ストレス判定 | `_get_stressed_syllable()` | 要確認 | — |
| Allophone (b→β, d→ð, g→ɣ) | 母音間弱化 | 要確認 | — |
| 機能語リスト | `_UNSTRESSED_FUNCTION_WORDS` | 要確認 | — |

### 5.4 フランス語 (規則ベース)

| 機能 | Python | C++ | 一致 |
|------|--------|-----|------|
| 鼻母音 (ɛ̃, ɑ̃, ɔ̃) | PUA E056-E058 | 要確認 | — |
| 前舌円唇母音 (ø, œ, y) | y_vowel=PUA E01E | 要確認 | — |
| tion→sjɔ̃ | 実装済み | 要確認 | — |
| 語末黙字 | `_SILENT_FINAL` | 要確認 | — |
| Intervocalic s→z | 実装済み | 要確認 | — |
| ストレス (最終音節) | 実装済み | 要確認 | — |

### 5.5 ポルトガル語 (規則ベース)

| 機能 | Python | C++ | 一致 |
|------|--------|-----|------|
| 鼻母音 (ã, ẽ, ĩ, õ, ũ) | 実装済み | 要確認 | — |
| Palatalization (ti→tʃi, di→dʒi) | `_apply_br_postprocessing()` | 要確認 | — |
| L vocalization (coda l→w) | `_apply_coda_l_vocalization()` | 要確認 | — |
| nh→ɲ, lh→ʎ | Digraph処理 | 要確認 | — |
| 鼻音重複除去 | `_remove_duplicate_nasal_coda()` | 要確認 | — |

---

## 6. PUA マッピング一覧 (全言語)

### 共有特殊トークン (ID 0-9)

| トークン | Unicode | 用途 |
|---------|---------|------|
| `_` | U+005F | PAD |
| `^` | U+005E | BOS |
| `$` | U+0024 | EOS (平叙) |
| `?` | U+003F | EOS (疑問) |
| `?!` | U+E016 | EOS (強調疑問) |
| `?.` | U+E017 | EOS (平叙疑問) |
| `?~` | U+E018 | EOS (確認疑問) |
| `#` | U+0023 | アクセント句境界 |
| `[` | U+005B | ピッチ上昇 |
| `]` | U+005D | アクセント核 |

### 日本語 PUA (U+E000-U+E01C)

| PUA | 音素 | 用途 |
|-----|------|------|
| E000-E004 | a:, i:, u:, e:, o: | 長母音 |
| E005 | cl | 促音 |
| E006-E015 | ky, kw, gy, gw, ty, dy, py, by, ch, ts, sh, zy, hy, ny, my, ry | 軟口蓋化子音 |
| E016-E018 | ?!, ?., ?~ | 疑問詞マーカー |
| E019-E01C | N_m, N_n, N_ng, N_uvular | Nバリアント |

### 多言語共有 PUA (U+E01D-U+E01E)

| PUA | 音素 | 用途 |
|-----|------|------|
| E01D | rr | スペイン語 trill r |
| E01E | y_vowel | 中国語 ü / フランス語 y |

### 中国語 PUA (U+E020-U+E04A)

| PUA | 音素 | 用途 |
|-----|------|------|
| E020-E022 | pʰ, tʰ, kʰ | 有気音 |
| E023-E024 | tɕ, tɕʰ | 硬口蓋音 |
| E025-E027 | tʂ, tʂʰ, tsʰ | 歯摩擦音 |
| E028-E030 | aɪ, eɪ, aʊ, oʊ, an, ən, aŋ, əŋ, uŋ | 複合韻母 |
| E031-E044 | ia, iɛ, iou, ... yɛ, yɛn, yn | i/u/ü-韻母 |
| E045 | ɻ̩ | 音節子音 |
| E046-E04A | tone1-5 | 声調マーカー |

### 韓国語 PUA (U+E04B-U+E053)

| PUA | 音素 | 用途 |
|-----|------|------|
| E04B-E04F | p͈, t͈, k͈, s͈, t͈ɕ | 緊音 |
| E050-E052 | k̚, t̚, p̚ | 内破音 |

### スペイン語/ポルトガル語共有 PUA (U+E054-U+E055)

| PUA | 音素 | 用途 |
|-----|------|------|
| E054 | tʃ | 無声破擦音 |
| E055 | dʒ | 有声破擦音 |

### フランス語 PUA (U+E056-U+E058)

| PUA | 音素 | 用途 |
|-----|------|------|
| E056 | ɛ̃ | 鼻母音 |
| E057 | ɑ̃ | 鼻母音 |
| E058 | ɔ̃ | 鼻母音 |

---

## 7. Prosody (A1/A2/A3) 計算の言語別仕様

| 言語 | a1 | a2 | a3 |
|------|----|----|-----|
| ja | アクセント核相対位置 | アクセント句内モーラ位置 | アクセント句内総モーラ数 |
| en | 0 | stress (0=none, 1=secondary, 2=primary) | 単語内IPA文字数 |
| zh | tone値 (1-5) | 語内音節位置 | 語の音節総数 |
| es | 0 | stress (0=none, 2=primary) | 単語内音素数 |
| fr | 0 | stress (0=none, 2=最終母音) | 単語内音素数 |
| pt | 0 | stress (0=none, 2=primary) | 単語内音素数 |
| ko | 0 | 0 | 0 |

---

## 8. ファイルパス一覧

### C++ ソース

| ファイル | 行数 | 用途 |
|---------|------|------|
| `src/cpp/piper.cpp` | 2000+ | コア推論 + 言語ディスパッチ |
| `src/cpp/language_detector.cpp/.hpp` | — | Unicode言語検出 |
| `src/cpp/phoneme_ids.hpp` | 102 | Phoneme→ID変換 + intersperse |
| `src/cpp/phoneme_parser.cpp/.hpp` | — | `[[phoneme]]` 記法パーサ |
| `src/cpp/openjtalk_phonemize.cpp/.hpp` | 204 | 日本語phonemizer |
| `src/cpp/openjtalk_phonemize_utils.cpp/.hpp` | 108 | PUA/N-variant/疑問詞 |
| `src/cpp/openjtalk_api.c/.h` | 359 | OpenJTalk C API |
| `src/cpp/english_phonemize.cpp/.hpp` | 638+42 | 英語phonemizer |
| `src/cpp/chinese_phonemize.cpp/.hpp` | 820 | 中国語phonemizer |
| `src/cpp/spanish_phonemize.cpp/.hpp` | — | スペイン語phonemizer |
| `src/cpp/french_phonemize.cpp/.hpp` | — | フランス語phonemizer |
| `src/cpp/portuguese_phonemize.cpp/.hpp` | — | ポルトガル語phonemizer |
| `src/cpp/korean_phonemize.cpp/.hpp` | — | 韓国語phonemizer |

### Python ソース (参照実装)

| ファイル | 行数 | 用途 |
|---------|------|------|
| `src/python/piper_train/phonemize/english.py` | 425 | 英語 (g2p-en) |
| `src/python/piper_train/phonemize/chinese.py` | 571 | 中国語 (pypinyin) |
| `src/python/piper_train/phonemize/spanish.py` | 868 | スペイン語 (規則) |
| `src/python/piper_train/phonemize/french.py` | 575 | フランス語 (規則) |
| `src/python/piper_train/phonemize/portuguese.py` | 684 | ポルトガル語 (規則) |
| `src/python/piper_train/phonemize/multilingual.py` | — | 言語検出+統合 |
| `src/python/piper_train/phonemize/token_mapper.py` | — | PUAマッピング |
| `src/python/piper_train/phonemize/multilingual_id_map.py` | — | 統合ID空間 (173シンボル) |

### テスト

| ファイル | テスト数 | 用途 |
|---------|---------|------|
| `src/cpp/tests/test_multilingual_g2p.cpp` | 21 | 言語検出+各言語G2P |
| `src/cpp/tests/test_n_variants.cpp` | 28 | Nバリアント |
| `src/cpp/tests/test_question_markers.cpp` | — | 疑問詞マーカー |
| `src/cpp/tests/test_phonemize.cpp` | 19 | 音素マッピング |

---

## 9. 具体的な修正計画

### 修正1: 辞書ファイルのビルドアーティファクト同梱

**現状**: `src/cpp/` に辞書ファイルが存在するが、配布パッケージにコピーされていない。

**辞書ファイル**:
- `src/cpp/cmudict_data.json` (3.7MB, 英語 123K語)
- `src/cpp/pinyin_single.json` (705KB, 中国語 42K文字)
- `src/cpp/pinyin_phrases.json` (1.9MB, 中国語 47Kフレーズ)

**修正箇所**:

#### A. CMakeLists.txt にinstallルール追加

```cmake
# OpenJTalk辞書のinstall行 (行659付近) の後に追加
install(
  FILES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/cmudict_data.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_single.json
    ${CMAKE_CURRENT_SOURCE_DIR}/src/cpp/pinyin_phrases.json
  DESTINATION share/piper/dicts
  OPTIONAL
)
```

#### B. build-piper.yml で配布パッケージに含める

OpenJTalk辞書コピーの処理の後に:
```bash
mkdir -p dist/piper/share/piper/dicts
cp src/cpp/cmudict_data.json dist/piper/share/piper/dicts/
cp src/cpp/pinyin_single.json dist/piper/share/piper/dicts/
cp src/cpp/pinyin_phrases.json dist/piper/share/piper/dicts/
```

### 修正2: 辞書検索パスの拡充 (piper.cpp)

**現状**: モデルディレクトリのみ検索 (`modelDir + "/cmudict_data.json"`)

**修正**: OpenJTalk辞書と同じパターンで複数パス探索

```cpp
// piper.cpp loadVoice() 内 (行526-547)
// 検索順序:
// 1. モデルディレクトリ (現状維持、モデル配布時の互換性)
// 2. exe相対パス (<exe_dir>/../share/piper/dicts/)
// 3. 環境変数 PIPER_DICTIONARIES_PATH

std::string cmuPath = findDictionaryFile("cmudict_data.json", modelDir);
if (!cmuPath.empty()) {
    loadCmuDict(cmuPath, voice.cmuDict);
}
```

### 修正3: `--language` によるdefaultLatinLang設定 (piper.cpp)

**現状**: `defaultLatinLang` が常に優先度順 (en > es > pt > fr) で決定される。`--language es` を指定してもラテン文字は "en" と判定。

**修正箇所**: `piper.cpp` 行1040-1047

```cpp
// Before:
std::string defaultLatin = "en";
for (const auto& lang : {"en", "es", "pt", "fr"}) {
    if (std::find(multiLangs.begin(), multiLangs.end(), lang) != multiLangs.end()) {
        defaultLatin = lang;
        break;
    }
}

// After:
std::string defaultLatin = "en";
// --language で明示的にラテン言語が指定された場合、それを使用
if (voice.synthesisConfig.languageId.has_value() && voice.modelConfig.languageIdMap) {
    auto langId = voice.synthesisConfig.languageId.value();
    for (const auto& [code, id] : *voice.modelConfig.languageIdMap) {
        if (id == langId && (code == "en" || code == "es" || code == "pt" || code == "fr")) {
            defaultLatin = code;
            break;
        }
    }
}
// フォールバック: 明示指定がない場合は優先度順
if (defaultLatin == "en") {
    for (const auto& lang : {"en", "es", "pt", "fr"}) {
        if (std::find(multiLangs.begin(), multiLangs.end(), lang) != multiLangs.end()) {
            defaultLatin = lang;
            break;
        }
    }
}
```

### 修正4: 辞書チェック条件の緩和 (piper.cpp)

**現状**: 英語は `!voice.cmuDict.empty()` が条件。辞書なしだとelse節に落ちてスキップ。

**修正箇所**: `piper.cpp` 行1118-1138 のディスパッチロジック

```cpp
// Before:
} else if (langSeg.lang == "en" && !voice.cmuDict.empty()) {
    phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
...
} else if (langSeg.lang == "zh" && !voice.pinyinSingleDict.empty()) {
    phonemize_chinese(langSeg.text, langPhonemes, ...);
...

// After:
} else if (langSeg.lang == "en") {
    if (voice.cmuDict.empty()) {
        spdlog::warn("English CMU dictionary not loaded; results may be degraded");
    }
    phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
...
} else if (langSeg.lang == "zh") {
    if (voice.pinyinSingleDict.empty()) {
        spdlog::warn("Chinese pinyin dictionaries not loaded; results may be degraded");
    }
    phonemize_chinese(langSeg.text, langPhonemes, ...);
...
```

### 修正5: テストモデルへの辞書配置

テスト用にシンボリックリンクまたはコピー:
```
test/models/cmudict_data.json → src/cpp/cmudict_data.json
test/models/pinyin_single.json → src/cpp/pinyin_single.json
test/models/pinyin_phrases.json → src/cpp/pinyin_phrases.json
```

---

## 10. 実装優先度

| 優先度 | 修正 | 影響 | 難易度 |
|--------|------|------|--------|
| **P0** | 修正3: defaultLatinLang | ES/FR/PTが全く動作しない | 低 (5行変更) |
| **P0** | 修正4: 辞書チェック緩和 | EN/ZHが辞書なしでスキップ | 低 (条件変更) |
| **P1** | 修正1: ビルド同梱 | 配布物に辞書が含まれない | 中 (CMake+WF) |
| **P1** | 修正2: 検索パス拡充 | exe相対パスで辞書が見つからない | 中 (関数追加) |
| **P2** | 修正5: テスト辞書 | テスト時に辞書なし | 低 (コピーのみ) |
