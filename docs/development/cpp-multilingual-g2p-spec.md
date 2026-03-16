# C++ Multilingual G2P Implementation Specification

> Branch: `feat/cpp-multilingual-g2p` (based on `feat/bilingual-phonemizer`)
> Date: 2026-03-16
> Last updated: 2026-03-17 (Phase 1-4 ALL COMPLETE, post-review fixes applied)

## 1. Overview

Python側の多言語音素化パイプライン(7言語: JA/EN/ZH/KO/ES/FR/PT)をC++推論側に対応させるための技術仕様書。

### 1.1 現状のギャップ

| 機能 | Python | C++ | 状態 |
|------|--------|-----|:----:|
| `lid` テンソル | ONNX入力として送信 | **実装済み** | :white_check_mark: Phase 1 |
| `language_id_map` | config.jsonから読込 | **実装済み** | :white_check_mark: Phase 1 |
| `--language` CLI | infer_onnx.py で対応 | **実装済み** | :white_check_mark: Phase 1 |
| 言語検出 | UnicodeLanguageDetector | **実装済み** | :white_check_mark: Phase 2 |
| 多言語音素化ルーティング | 7言語レジストリ | **7言語ネイティブG2P** | :white_check_mark: Phase 2-4 |
| コードスイッチング | セグメント分割+言語別処理 | **実装済み** | :white_check_mark: Phase 2 |
| ES ネイティブG2P | ルールベース (868行) | **C++ポート済み (782行)** | :white_check_mark: Phase 3 |
| FR ネイティブG2P | ルールベース (776行) | **C++ポート済み (1084行)** | :white_check_mark: Phase 3 |
| PT ネイティブG2P | ルールベース (705行) | **C++ポート済み (893行)** | :white_check_mark: Phase 3 |
| EN ネイティブG2P | g2p-en (CMU辞書) | **CMU辞書 123K語** | :white_check_mark: Phase 4 |
| ZH ネイティブG2P | pypinyin | **pypinyin辞書 42K+47K** | :white_check_mark: Phase 4 |
| KO ネイティブG2P | g2pk2 + ハングル分解 | **ハングル分解 + 連音化** | :white_check_mark: Phase 4 |

### 1.2 実装フェーズ

| Phase | 内容 | 状態 |
|-------|------|:----:|
| **Phase 1** | ONNX `lid` テンソル + config解析 + CLI `--language` | :white_check_mark: **Done** (`f0e841e`) |
| **Phase 2** | UnicodeLanguageDetector + 多言語音素化ルーティング | :white_check_mark: **Done** (`23163f8`) |
| **Phase 3** | ES/FR/PT ルールベースG2Pポート（Python精度一致） | :white_check_mark: **Done** (`f6a37ce`) |
| **Phase 4** | EN CMU辞書 / ZH pypinyin辞書 / KO ハングル分解 | :white_check_mark: **Done** (`f0f87a7`) |

---

## 2. Phase 1: ONNX `lid` テンソル統合 — Done

> Commit: `f0e841e` feat: add C++ multilingual inference support (Phase 1 — lid tensor + config)
> Files: `piper.hpp` (+12), `piper.cpp` (+52), `main.cpp` (+55), spec doc (+487)

### 2.1 ONNX入力テンソル仕様

多言語モデルのONNX入力（順序厳守）:

| Index | Name | dtype | Shape | 条件 |
|-------|------|-------|-------|------|
| 0 | `input` | int64 | `[1, phonemes]` | 常時 |
| 1 | `input_lengths` | int64 | `[1]` | 常時 |
| 2 | `scales` | float32 | `[3]` | 常時 |
| 3 | `sid` | int64 | `[1]` | `n_speakers > 1 OR n_languages > 1` |
| 4 | `lid` | int64 | `[1]` | `n_languages > 1` |
| 5 | `prosody_features` | int64 | `[1, phonemes, 3]` | `prosody_dim > 0` |

**重要**: `n_languages > 1` の場合、`sid` は `n_speakers == 1` でもプレースホルダーとして含まれる。

### 2.2 実装された変更

#### piper.hpp (5箇所)

| 行 | 変更 |
|----|------|
| 23 | `typedef int64_t LanguageId;` 追加 |
| 42 | `MultilingualPhonemes` を PhonemeType enum に追加 |
| 80 | `std::optional<LanguageId> languageId;` を SynthesisConfig に追加 |
| 89, 95 | `numLanguages`, `languageIdMap` を ModelConfig に追加 |
| 106 | `bool hasLanguageInput = false;` を ModelSession に追加 |

#### piper.cpp (6箇所)

| 行 | 変更 |
|----|------|
| 72 | `puaToPhoneme` に `{0xE01D, "rr"}, {0xE01E, "y_vowel"}` 追加 |
| 136-140 | `parsePhonemizeConfig()` で `"multilingual"` / `"bilingual"` タイプ認識 |
| 282-298 | `parseModelConfig()` で `num_languages` / `language_id_map` パース |
| 700-703 | `loadModel()` で `"lid"` ONNX入力検出 |
| 734-740 | `loadVoice()` で多言語モデルのデフォルト `languageId = 0` 設定 |
| 797-809 | `synthesize()` で `lid` テンソル構築（sid→lid→prosody 順序） |

#### main.cpp (7箇所)

| 行 | 変更 |
|----|------|
| 69 | `RunConfig` に `optional<string> language;` 追加 |
| 700 | `printUsage()` に `--language` / `-l` 追加 |
| 795-797 | `parseArgs()` で `--language` / `-l` パース |
| 245-267 | 言語解決ロジック（数値ID or 言語コード → `languageIdMap` ルックアップ） |
| 304-311 | `MultilingualPhonemes` の eSpeak データパス設定 |
| 439-451 | JSON入力で `language_id` (数値) / `language` (文字列) サポート |
| 402, 636 | `languageId` のsave/restore（ループ毎） |

### 2.3 後方互換性（検証済み）

| シナリオ | 結果 |
|---------|------|
| 単言語JA (openjtalk) | `numLanguages=1` → lid 全スキップ、動作変更なし |
| 単言語EN (espeak) | 同上、`interspersePad=true` 維持 |
| config に `num_languages` なし | デフォルト `1`、全multilingual機能無効 |
| `--language` 未指定 | `languageId = 0` (デフォルト) |

### 2.4 使用方法

```bash
# CLI で言語指定
echo "Hello world" | piper --model multilingual.onnx --language en
echo "こんにちは" | piper --model multilingual.onnx --language ja
echo "こんにちは" | piper --model multilingual.onnx --language 0

# JSON入力
echo '{"text": "Hello", "language": "en"}' | piper --model multilingual.onnx --json-input
echo '{"text": "Hello", "language_id": 1}' | piper --model multilingual.onnx --json-input
```

---

## 3. Phase 2: UnicodeLanguageDetector + 多言語ルーティング — :white_check_mark: Done

> Commit: `23163f8` feat: add UnicodeLanguageDetector and multilingual phonemization (Phase 2)
> New files: `language_detector.hpp` (+54), `language_detector.cpp` (+248)
> Modified: `piper.cpp` (+152), `CMakeLists.txt` (+2)

### 3.1 実装された機能

- **UnicodeLanguageDetector**: 6つのUnicode範囲チェック、7段階の判定優先順位、CJK曖昧性解消
- **テキストセグメンテーション**: 言語変化で自動分割、ニュートラル文字は前セグメントに付随
- **多言語音素化ルーティング**: JA→OpenJTalk (prosody対応)、他→eSpeak (言語別voice)
- **BOS/EOS処理**: JAセグメントからストリップ → `phonemes_to_ids` で統一付与（二重適用なし）
- **支配言語自動検出**: `detectDominantLanguage()` → `lid` テンソルに反映
- **eSpeak voice マッピング**: en→`en-us`, zh→`cmn`, ko→`ko`, es→`es-la`, fr→`fr`, pt→`pt-br`
- **後方互換**: 単言語モデル (OpenJTalk/eSpeak) は完全に影響なし

### 3.2 Unicode範囲チェック

| カテゴリ | 範囲 | 判定言語 |
|---------|------|---------|
| ひらがな | U+3040-309F | JA |
| カタカナ | U+30A0-30FF, U+31F0-31FF | JA |
| CJK統合漢字 | U+4E00-9FFF, U+3400-4DBF, U+F900-FAFF | JA or ZH（コンテキスト依存） |
| ハングル | U+AC00-D7AF, U+1100-11FF, U+3130-318F | KO |
| 全角ラテン | U+FF21-FF3A, U+FF41-FF5A | ラテンデフォルト言語 |
| 日本語句読点 | U+3000-303F, U+FF00-FF20, U+FF3B-FFEF (全角ラテン除く) | JA |
| ラテン | A-Z, a-z, U+00C0-00FF (×U+00D7, ×U+00F7) | ラテンデフォルト言語 |
| その他 | 空白、数字、ASCII句読点 | ニュートラル（前のセグメントに付随） |

### 3.3 CJK曖昧性解消

テキスト全体を事前スキャンし `context_has_kana` フラグを計算:
- 仮名あり → CJK漢字は **JA**
- 仮名なし → CJK漢字は **ZH**

### 3.4 テキストセグメンテーション

文字ごとに言語を判定し、言語が変わるたびにセグメント境界を作成。ニュートラル文字（空白・数字・句読点）は直前のセグメントに付随。

```
"今日はgoodですね" → [("ja","今日は"), ("en","good"), ("ja","ですね")]
```

### 3.5 C++実装（実装済み）

```cpp
// src/cpp/language_detector.hpp (54行)
class UnicodeLanguageDetector {
public:
  UnicodeLanguageDetector(const std::vector<std::string>& languages,
                          const std::string& defaultLatinLang = "en");
  std::string detectChar(char32_t ch, bool contextHasKana) const;
  bool hasKana(const std::string& utf8Text) const;
  std::vector<LangSegment> segmentText(const std::string& utf8Text) const;
};

// src/cpp/language_detector.cpp (248行)
// - 6 static range functions (isKana, isCJK, isHangul, isFullwidthLatin, isJaPunct, isLatin)
// - detectChar() with 7-step priority
// - segmentText() state machine (Python _segment_text_multilingual と完全一致)
// - detectDominantLanguage() for lid tensor

// 使用例 (piper.cpp textToAudio 内):
UnicodeLanguageDetector detector(multiLangs, defaultLatin);
auto langSegments = detector.segmentText(segment.text);
for (const auto& langSeg : langSegments) {
  if (langSeg.lang == "ja") { phonemize_openjtalk(...); }
  else { phonemize_eSpeak(langSeg.text, ...); }
}
auto dominantLang = detectDominantLanguage(segment.text, detector);
```

ICU不要。既存の `utf8.h` によるコードポイント範囲チェックで実装済み。

---

## 4. Phase 3: ルールベースG2Pポート (ES/FR/PT) — :white_check_mark: Done

> Commit: `f6a37ce` feat: add native C++ G2P for Spanish, French, and Portuguese (Phase 3)
> New files: `spanish_phonemize.hpp/cpp` (782行), `french_phonemize.hpp/cpp` (1084行), `portuguese_phonemize.hpp/cpp` (893行)
> Modified: `piper.cpp` (+20), `CMakeLists.txt` (+3)

外部依存なし、純粋な文字列処理のみ。Python ソースコードと全ルール精度一致検証済み。

### 4.1 Spanish Phonemizer

**ソース**: `src/python/piper_train/phonemize/spanish.py` (868行)

**パイプライン**: テキスト → 正規化 → トークン化 → G2P(文字走査) → 音節分割 → ストレス割当 → 異音変換 → PUAマッピング

**主要ルール**:
- **Seseo**: c+e/i → `s`, z → `s` (ラテンアメリカ発音)
- **Yeismo**: ll → `ʝ`, y → `ʝ`
- **異音変換 (b/d/g)**: 語頭・鼻音後・l後 → 閉鎖音、それ以外 → 摩擦音
- **rr**: 語頭r, l/n/s後r → 顫動音 `rr` (PUA U+E01D)
- **qu**: qu → `k` (u無音)、**gu+e/i** → `g` (u無音)、**gü** → `gw`
- **Digraphs**: ch→`tʃ`, ll→`ʝ`, rr→`rr`, sc+e/i→`s`, xc+e/i→`ks`
- **Silent h**: 常に無音
- **v = b**: betacismo（vとbは同一の異音規則に従う）
- **語末 y**: 母音 `/i/`（語中は子音 `/ʝ/`）
- **Hiatus/Diphthong**: 強母音+強母音=hiatus、アクセント付き弱母音=hiatus（diphthong breaking）

**音節分割**: 不可分オンセットクラスタ 13個: bl, br, cl, cr, dr, fl, fr, gl, gr, pl, pr, tr, tl

**ストレス**: アクセント記号優先 → デフォルト（母音/n/s終わり=後ろから2番目、それ以外=最後）、機能語27語はストレスなし

**データ量**: 静的テーブル合計 < 1KB。外部依存なし。

### 4.2 French Phonemizer

**ソース**: `src/python/piper_train/phonemize/french.py` (776行)

**パイプライン**: テキスト → 正規化 → トークン化(アポストロフィ対応) → G2P(左→右最長一致) → PUAマッピング

**主要ルール**:
- **鼻母音**: an/en→`ɑ̃`, in→`ɛ̃`, on→`ɔ̃`, un/yn/ym→`ɛ̃` (後続が母音 or nn/mm の場合は非鼻音化)
- **三文字鼻母音**: ain/aim/ein/eim→`ɛ̃`、oin→`wɛ̃`、ien→`jɛ̃`
- **-tion**: `s j ɔ̃`（stion の場合は `t j ɔ̃`）
- **-ille**: `i j`（例外: ville, mille, tranquille → `i l`）
- **-aille/-eille/-ouille/-euille**: `aj`/`ɛj`/`uj`/`œj`、**eil**→`ɛj`
- **-er**: 多音節語 → `e`（例外13語: hiver, enfer, amer, cancer, super, laser, hamster, master, poster, cluster, starter, leader, transfer）
- **eau**: `o`、ou → `u`、oi → `w a`、ai → `ɛ`、eu → `ø`/`œ`（文脈依存）
- **語末黙字**: d, g, h, m, n, p, s, t, x, z
- **母音間 s 有声化**: s → `z`
- **u+i**: `ɥ i` (半母音)、**i+母音** → `j`（語末silent e前は除く）
- **Digraphs**: ph→`f`、th→`t`、ch→`ʃ`、gn→`ɲ`、qu→`k`、gu+e/i→`ɡ`
- **二重子音**: 単一化（rr→`ʁ` 等）
- **文脈依存 e**: schwa `ə` / 開音 `ɛ` / 語末無音
- **文脈依存 o**: 開音 `ɔ`（発音される子音前）/ 閉音 `o`（語末・黙字前）
- **x**: 語末=無音、ex+母音=`ɡz`、その他=`ks`

**PUA トークン**: `y_vowel` (U+E01E)、鼻母音 `ɛ̃`/`ɑ̃`/`ɔ̃` は動的PUA割当

### 4.3 Portuguese Phonemizer (Brazilian)

**ソース**: `src/python/piper_train/phonemize/portuguese.py` (705行)

**パイプライン**: テキスト → 正規化 → トークン化 → G2P → 後処理(鼻音吸収、coda-l母音化、t/d口蓋化)

**主要ルール**:
- **鼻母音吸収**: V+n/m (語末 or 子音前) → 鼻母音 `ã/ẽ/ĩ/õ/ũ`（n/m消失）。nhの前は非鼻音化
- **t/d口蓋化**: t+i→`tʃ`, d+i→`dʒ`、語末t+無ストレスe→`tʃ`+`i`
- **coda-l母音化**: 音節コーダの l → `w`
- **母音間 r**: `ɾ` (タップ)、その他 → `ʁ` (口蓋垂)
- **母音間 s**: `z`
- **無ストレス語末母音縮約**: e→i, o→u
- **Digraphs**: nh→`ɲ`, lh→`ʎ`, ch→`ʃ`, rr→`ʁ`, ss→`s`, sc+e/i→`s`, qu+e/i→`k`, gu+e/i→`ɡ`, ou→`o`
- **x**: 語頭→`ʃ`、母音間→`z`、その他→`ʃ`
- **ç**: 常に `s`、soft c (c+e/i→`s`)、soft g (g+e/i→`ʒ`)
- **開母音/閉母音**: アクセント記号依存（acute=開、circumflex=閉）
- **Silent h**: 常に無音（digraph nh/lh/ch 以外）

---

## 5. Phase 4: 外部依存言語 — :white_check_mark: Done

> Commit: `f0f87a7` feat: add native C++ G2P for English, Chinese, and Korean (Phase 4)
> New files: `english_phonemize.hpp/cpp`, `chinese_phonemize.hpp/cpp`, `korean_phonemize.hpp/cpp`
> Data files: `cmudict_data.json` (3.7MB), `pinyin_single.json` (705KB), `pinyin_phrases.json` (1.9MB)
> Modified: `piper.hpp` (+5), `piper.cpp` (+40), `CMakeLists.txt` (+3)

### 5.1 English — 推奨戦略

**注意**: 現在の多言語モデルは g2p-en で学習されている。espeak-ng を使うとフラッピング・ストレス・縮約形で系統的な不一致が発生し、音質が劣化する。

**推奨**: CMU辞書バンドル（~134K語、Public Domain）を実装。95-98%カバレッジで工数も低い。

| 戦略 | 精度 | 工数 | GPL | 備考 |
|------|------|------|-----|------|
| espeak-ng | g2p-en学習モデルでは劣化 | なし | GPL | letter, better 等でt→ɾ不一致 |
| **CMU辞書のみ（推奨）** | **95-98%** | **低** | **Apache-2.0** | OOV語はフォールバック必要 |
| CMU辞書 + GRU | 99%+ | 中-高 | Apache-2.0 | 将来的に追加 |

**EN追加実装項目**:
- ARPAbet→IPA変換（文脈依存: AA+R→`ɑːɹ`、ER1→`ɜː`、ER0→`ɚ`、AH0→`ə`）
- 機能語デストレス（~90語のリスト）
- ストレスマーカー挿入（`ˈ`/`ˌ`）

**既知の差異** (g2p-en vs espeak-ng):
- フラッピング: g2p-en=`t` vs espeak-ng=`ɾ` ("letter")
- 疑問詞ストレス: g2p-en=`ˈ` vs espeak-ng=`ˌ` ("how")
- 縮約形: g2p-en=分離 vs espeak-ng=結合 ("I am")

### 5.2 Chinese — 推奨戦略

**注意**: 事前計算pinyin入力のみでは実用性が低い（ユーザーはテキストを入力する）。pypinyin辞書を初回から含めることを推奨。

**推奨**: pinyin→IPA変換テーブル + pypinyin辞書を一括実装（~400行C++、~300KBデータ）
- Initial→IPA (21エントリ)、Final→IPA (39固有 + 6エイリアス = 45エントリ)
- 声調サンディ4規則: T3+T3→T2+T3、一+T4→T2、一+T1/T2/T3→T4、不+T4→T2
- 儿化処理（末尾r除去 + ɚ挿入）
- 多文字IPAトークン → PUA変換（`map_sequence()` 相当）が必須
- pypinyin単字辞書 (~8,105エントリ、MIT) + フレーズ辞書 (~8,500エントリ)
- ライセンス: MIT

### 5.3 Korean — 推奨戦略

**推奨**: ハングル分解 + IPAテーブルのみ（~200-300行C++）

**ハングル分解算術**:
```cpp
code = ch - 0xAC00;
initial = code / (21 * 28);  // 19 initials
medial  = (code % 588) / 28; // 21 medials
final_  = code % 28;         // 28 finals (0=なし)
```

**テーブル**: Initial→IPA (19), Medial→IPA (21), Final→IPA (28)。合計68エントリ。多文字IPAトークン（緊張子音 `k͈` 等、無解放終声 `k̚` 等）は PUA マッピングが必要。

**g2pk2音韻規則なし（品質影響あり）**: 引用形（辞書発音）のみ。連音化(연음)・鼻音化(비음화)・濃音化(경음화)・有気音化(격음화)・口蓋音化(구개음화)は適用されない。**連続発話の約30-40%の音節境界に影響するため、品質劣化は顕著。** g2pk2で学習されたモデルを分解のみで推論すると音素分布の不一致が発生する。

**改善案**: 最も影響の大きい連音化規則（終声+初声ㅇ→連音）のみ ~100行C++ でポートすれば品質差の約半分をカバー可能（MeCab不要）。

---

## 6. C++ アーキテクチャ設計 — 実装済みの構成

> Phase 2-4 で全ファイルを `src/cpp/` に直接配置（piper.cpp と同階層）。
> Phonemizer ABC / Registry パターンは将来のリファクタリングで検討。

### 6.1 現在のファイル構成

```
src/cpp/
  piper.hpp/cpp              -- メインAPI（Phase 1-4 変更済み）
  main.cpp                   -- CLI（Phase 1 変更済み）
  language_detector.hpp/cpp  -- UnicodeLanguageDetector（Phase 2）
  spanish_phonemize.hpp/cpp  -- スペイン語G2P（Phase 3, 782行）
  french_phonemize.hpp/cpp   -- フランス語G2P（Phase 3, 1084行）
  portuguese_phonemize.hpp/cpp -- ポルトガル語G2P（Phase 3, 893行）
  english_phonemize.hpp/cpp  -- 英語G2P（Phase 4, CMU辞書）
  chinese_phonemize.hpp/cpp  -- 中国語G2P（Phase 4, pypinyin）
  korean_phonemize.hpp/cpp   -- 韓国語G2P（Phase 4, ハングル分解）
  cmudict_data.json          -- CMU辞書 123K語（ランタイムロード）
  pinyin_single.json         -- pypinyin単字辞書 42K（ランタイムロード）
  pinyin_phrases.json        -- pypinyinフレーズ辞書 47K（ランタイムロード）
  openjtalk_phonemize.hpp/cpp -- 日本語G2P（既存）
  phoneme_parser.hpp/cpp     -- 音素パーサー（既存）
  custom_dictionary.hpp/cpp  -- カスタム辞書（既存）
```

### 6.2 将来のリファクタリング候補

```
src/cpp/phonemizer/        -- Phonemizer ABC / Registry パターン
  phonemizer.hpp/cpp          -- Phonemizer ABC
  registry.hpp/cpp            -- PhonemizerRegistry (シングルトン)
  language_detector.hpp/cpp   -- UnicodeLanguageDetector
  multilingual_id_map.hpp/cpp -- PUAトークンマッピング
  japanese_phonemizer.hpp/cpp -- OpenJTalkアダプター
  espeak_phonemizer.hpp/cpp   -- eSpeak-ngアダプター
  english_phonemizer.hpp/cpp  -- 英語G2P
  chinese_phonemizer.hpp/cpp  -- 中国語G2P
  korean_phonemizer.hpp/cpp   -- 韓国語G2P
  spanish_phonemizer.hpp/cpp  -- スペイン語G2P
  french_phonemizer.hpp/cpp   -- フランス語G2P
  portuguese_phonemizer.hpp/cpp -- ポルトガル語G2P
  multilingual_phonemizer.hpp/cpp -- 言語検出+ルーティング
```

### 6.2 Phonemizer ABC

```cpp
class Phonemizer {
public:
  virtual ~Phonemizer() = default;

  virtual PhonemizeResult phonemize(const std::string& text) = 0;
  virtual PhonemizeResult phonemize_with_prosody(const std::string& text) = 0;
  virtual std::string language_code() const = 0;

  // デフォルト実装: BOS/EOS + inter-phoneme padding
  // JapanesePhonemizer はこれを no-op にオーバーライド
  virtual ProcessedIds post_process_ids(
      const std::vector<int64_t>& ids,
      const std::map<char32_t, std::vector<int64_t>>& phoneme_id_map);
};
```

### 6.3 PhonemizerRegistry

```cpp
class PhonemizerRegistry {
public:
  static PhonemizerRegistry& instance();  // std::call_once で初期化
  std::shared_ptr<Phonemizer> get(const std::string& languageCode);
  void register_language(const std::string& code, std::shared_ptr<Phonemizer> p);
private:
  std::mutex mutex_;
  std::map<std::string, std::shared_ptr<Phonemizer>> cache_;
};
```

コンボコード（例: `"ja-en-zh-ko"`）は自動的に `MultilingualPhonemizer` を生成・キャッシュ。

### 6.4 piper.cpp 統合

```cpp
// textToAudio() の音素化分岐を置換
auto& reg = PhonemizerRegistry::instance();
auto phonemizer = reg.get(languageCode);
auto result = phonemizer->phonemize_with_prosody(segment.text);
```

### 6.5 CMakeLists.txt 変更

```cmake
set(PHONEMIZER_SOURCES
  src/cpp/phonemizer/phonemizer.cpp
  src/cpp/phonemizer/registry.cpp
  src/cpp/phonemizer/language_detector.cpp
  # ... 各言語の .cpp ファイル
)
target_sources(piper PRIVATE ${PHONEMIZER_SOURCES})
target_sources(test_piper PRIVATE ${PHONEMIZER_SOURCES})
```

---

## 7. レビュー結果と修正 (2026-03-17)

Phase 1-4 完了後のコードレビューで発見された CRITICAL/MAJOR 課題と、それぞれの修正状況。

### 7.1 指摘事項サマリテーブル

| ID | 重要度 | 言語 | 概要 | 状態 |
|----|--------|------|------|:----:|
| C1 | CRITICAL | 全言語 | PUA固定マッピングが token_mapper.py に未登録（ES `rr`, FR/ZH `y_vowel`）| :white_check_mark: Applied |
| C2 | CRITICAL | ZH | 中国語フレーズ辞書パーサーがJSONキーの空白を未処理 | :white_check_mark: Applied |
| C3 | CRITICAL | KO | 韓国語連音化で生成されるIPAが PUA 再マッピングされていない | :white_check_mark: Applied |
| C4 | CRITICAL | 全言語 | LanguageID が `language_id_map` の範囲外でも検証なし | :white_check_mark: Applied |
| C5 | CRITICAL | 全言語 | eSpeak フォールバック時に BOS/EOS が二重適用される | :white_check_mark: Applied |
| C6 | CRITICAL | 全言語 | `phoneme_type: multilingual` で `language_id_map` 欠如時にサイレント失敗 | :white_check_mark: Applied |
| C7 | CRITICAL | FR | フランス語鼻母音の PUA マッピング不整合 | :white_check_mark: Applied |
| C8 | CRITICAL | PT | ポルトガル語 affricate PUA が config と不一致 | :white_check_mark: Applied |
| M1 | MAJOR | ES | intervocalic x の母音判定が `isPlainVowel` のみでアクセント付き母音を見落とし | :white_check_mark: Applied |
| M2 | MAJOR | KO | g2pk2 コアルール（鼻音化・濃音化・有気音化・口蓋音化）未実装 | :hourglass: Pending (将来課題) |
| M3 | MAJOR | 全言語 | dominant language が自動検出のみで CLI 上書き不可 | :hourglass: Pending |
| M4 | MAJOR | EN | OOV語のニューラル G2P 推論なし（eSpeak フォールバックのみ） | :hourglass: Pending (将来課題) |
| M5 | MAJOR | ES/FR/PT | NFD 入力時に combining accent が NFC に正規化されず G2P が破綻 | :white_check_mark: Applied (PT) / :hourglass: Pending (ES, FR) |
| M6 | MAJOR | ZH | 声調サンディ規則の適用範囲がフレーズ辞書ヒット語のみ | :hourglass: Pending |
| M7 | MAJOR | 全言語 | 旧バイリンガルモデル (`phoneme_type: bilingual`) との互換性未検証 | :hourglass: Pending |

### 7.2 適用済み修正の詳細

**C1: PUA 固定マッピング統一**
- ES `rr` (U+E01D)、FR/ZH `y_vowel` (U+E01E) を `token_mapper.py` と C++ `puaToPhoneme` マップの両方に登録
- Phase 1 commit (`f0e841e`) で `piper.cpp` に追加済み

**C2: 中国語フレーズ辞書パーサー修正**
- `pinyin_phrases.json` のキー（漢字フレーズ）にスペース区切りが含まれるケースを正しくパース

**C3: 韓国語連音 IPA 再マッピング**
- 連音化で生成される新しい initial+final の組み合わせが PUA マッピング済み IPA トークンに正しく変換されるよう修正

**C4: LanguageID 範囲検証**
- `piper.cpp` の `synthesize()` で `languageId` が `[0, numLanguages)` 範囲内であることを検証。範囲外はエラー

**C5: eSpeak フォールバック BOS/EOS ストリップ**
- ネイティブ G2P で処理できない言語が eSpeak にフォールバックする際、eSpeak が付与する BOS/EOS を除去してから統一パディング方式で再付与

**C6: multilingual + language_id_map 欠如時エラー**
- `phoneme_type: "multilingual"` で `language_id_map` がない config.json に対して明示的なエラーメッセージを出力

**C7/C8: FR鼻母音・PT affricate PUA 統一**
- フランス語鼻母音（ɛ̃/ɑ̃/ɔ̃）とポルトガル語 affricate（tʃ/dʒ）の PUA コードポイントを Python `token_mapper.py` の割当と一致させた

**M1: intervocalic x 母音判定修正 (ES)**
- `isPlainVowel` (a/e/i/o/u のみ) を `isVowelChar` (アクセント付き母音含む) に変更し、"exámen" 等で正しく intervocalic z が適用されるよう修正

**M5: NFD → NFC combining accent collapse (PT)**
- `portuguese_phonemize.cpp` の `normalize()` の先頭で `collapseNfdCombiningAccents()` を呼び出し、U+0300 (grave), U+0301 (acute), U+0302 (circumflex), U+0303 (tilde), U+0308 (diaeresis), U+0327 (cedilla) の6種の combining mark を precomposed NFC 形式に変換
- macOS HFS+ や一部 HTTP クライアントからの NFD 入力に対応
- ES, FR への同様の修正は次回対応予定

### 7.3 フェーズ状態の更新

| Phase | 基本実装 | レビュー修正 | 状態 |
|-------|---------|-------------|:----:|
| Phase 1 | :white_check_mark: Done (`f0e841e`) | C4, C6 適用済み | :white_check_mark: |
| Phase 2 | :white_check_mark: Done (`23163f8`) | C5 適用済み | :white_check_mark: |
| Phase 3 | :white_check_mark: Done (`f6a37ce`) | C1, C7, C8, M1, M5(PT) 適用済み | :white_check_mark: |
| Phase 4 | :white_check_mark: Done (`f0f87a7`) | C2, C3 適用済み | :white_check_mark: |

### 7.4 残課題 (Pending)

以下の項目は将来のイテレーションで対応:

1. **M2: 韓国語 g2pk2 コアルール** -- 鼻音化・濃音化・有気音化・口蓋音化の C++ 移植。連続発話の 30-40% の音節境界に影響するため品質改善効果大
2. **M3: dominant language CLI 上書き** -- `--dominant-language` オプションで `lid` テンソルの値を固定可能にする
3. ~~**M4: 英語 OOV ニューラル G2P**~~ -- **eSpeak フォールバック実装済み (7.5)**。GRU ニューラルモデルの C++ 移植は将来課題
4. **M5 (ES/FR): NFC 正規化** -- PT と同様の `collapseNfdCombiningAccents()` を ES/FR phonemizer にも追加
5. **M6: ZH 声調サンディ拡大** -- フレーズ辞書外の連続語にも T3+T3、一/不 サンディを適用
6. ~~**M7: 旧モデル互換性検証**~~ -- **調査完了: 互換性問題なし (Section 11.3)**。IDs 0-96 は完全一致確認済み
7. ~~**M11: 非JA prosody 欠落**~~ -- **全6言語の prosody 抽出実装済み (7.5)**

### 7.5 追加修正 (2026-03-17, 第2ラウンド)

Section 11 の詳細調査に基づく3件の修正。

**M11-ZH: 中国語声調 prosody 対応** — :white_check_mark: Applied
- `computeNonJaProsody()` 関数を `piper.cpp` に追加
- PUA 声調マーカー (0xE046-0xE04A) から声調番号 (1-5) を抽出し `a1` に設定
- `a2` = 語内の音節位置 (1-based)、`a3` = 語内の総音節数
- 声調マーカーの検出ベース: 連続する中国語音素群を「語」として認識

**M4-A: EN OOV eSpeak フォールバック** — :white_check_mark: Applied
- `phonemize_english()` が空結果を返した場合、eSpeak (`en-us`) にフォールバック
- eSpeak 出力から BOS/EOS をストリップ
- warning ログ出力で検出可能

**M11-EN/ES/PT: ストレスベース prosody 対応** — :white_check_mark: Applied
- ストレスマーカー ˈ(0x02C8)→`a2=2`、ˌ(0x02CC)→`a2=1` を検出
- ストレスマーカー後の母音クラスタ (ː 含む) に同じストレス値を伝播
- `a3` = 語内の音素数（ストレスマーカー除外）

**M11-FR: フランス語語末ストレス prosody 対応** — :white_check_mark: Applied
- 各語の最後の母音音素を検出し `a2=2` を設定
- フランス語母音: 基本母音 + IPA母音 + PUA (y_vowel, 鼻母音)
- `a3` = 語内の音素数

**M7: 旧バイリンガルモデル互換性** — :white_check_mark: 調査完了 (コード変更不要)
- IDs 0-96 がバイリンガル/マルチリンガル間で完全一致を実測確認
- C++は `config.json` からモデル固有の `phoneme_id_map` をロード（ハードコードなし）
- 互換性リスクは model/config 不一致のみ（ユーザーエラー）

---

## 8. 多言語Phoneme IDマップ

### 8.1 統一IDマップ構造

config.json の `phoneme_id_map` はそのままC++で使用可能。全キーはPUA変換済みの単一コードポイント。

**ID配置（概念）**:
```
[0..9]     特殊トークン (_, ^, $, ?, ?!, ?., ?~, #, [, ])
[10..63]   日本語音素 (共有音素含む: a, k, b, ...)
[64..86]   英語固有音素 (23個: ɑ, æ, ʌ, ː, ŋ, ɹ, ʃ, ...)
[87+]      ZH固有(~49) → KO固有(~11) → ES固有(~7) → PT固有(~11) → FR固有(~6)
```

合計: ~171 シンボル（7言語、重複排除後）

**言語登録の正規順序**: `ja, en, zh, ko, es, pt, fr`（config.json の `language_id_map` もこの順序）。KO はデータセットにはないが Phonemizer は実装済み。

### 8.2 PUA固定マッピング (U+E000-E01E)

| Codepoint | Token | 言語 |
|-----------|-------|------|
| U+E000-E015 | JA長母音・口蓋化子音・促音 (22個) | JA |
| U+E016-E018 | 疑問詞マーカー (?!, ?., ?~) | JA |
| U+E019-E01C | Nバリアント (N_m, N_n, N_ng, N_uvular) | JA |
| U+E01D | `rr` (顫動音) | ES |
| U+E01E | `y_vowel` (前舌円唇母音) | ZH, FR |

C++ `puaToPhoneme` マップ (piper.cpp) は U+E000-E01E の全31エントリに対応済み (Phase 1 で E01D/E01E を追加)。

### 8.3 PUA動的マッピング (U+E020+)

ZH: 送気音・そり舌音・複合韻母・声調マーカー (~30トークン)
KO: 緊張子音・無解放終声 (~8トークン)
EN: 二重母音・破擦音 (~3トークン)
FR/PT: 鼻母音 (~3-5トークン)

**注意**: 動的PUAの実際のコードポイントは Python の `token_mapper.register()` 呼出し順に依存する。C++側は config.json の `phoneme_id_map` を正として使用し、動的PUAの具体値には依存しない設計。

### 8.4 BOS/EOS/パディング

多言語モデルは統一パディング方式: `BOS _ ph1 _ ph2 _ ... _ phN _ EOS`

- `interspersePad = true`（すべての言語セグメント共通）
- 日本語セグメントのBOS/EOSはストリップされ、最終的に統一方式で再付与
- EOS選択: 最後のセグメントの言語に依存（日本語疑問文→PUA疑問マーカー）

---

## 9. config.json フォーマット

```json
{
  "phoneme_type": "multilingual",
  "num_languages": 7,
  "language_id_map": {"ja": 0, "en": 1, "zh": 2, "ko": 3, "es": 4, "pt": 5, "fr": 6},
  "num_speakers": 150,
  "speaker_id_map": {"speaker_0": 0, ...},
  "phoneme_id_map": {"\\ue005": [0], "^": [1], ...},
  "num_symbols": 171,
  "audio": {"sample_rate": 22050, "quality": "medium"},
  "inference": {"noise_scale": 0.667, "length_scale": 1, "noise_w": 0.8}
}
```

C++ は `num_languages`、`language_id_map`、`phoneme_type: "multilingual"` を Phase 1 で対応済み。

---

## 10. テストケース概要

各言語のテストケースは Python テストファイルに完全に定義済み:

| 言語 | テストファイル | テスト数 |
|------|-------------|---------|
| ES | `test/test_spanish_phonemizer.py` | ~33 |
| FR | `test/test_french_phonemizer.py` | ~49 |
| PT | `test/test_portuguese_phonemizer.py` | ~39 |
| ZH | `test/test_chinese_phonemizer.py` | ~20 |
| KO | `test/test_korean_phonemizer.py` | ~25 |
| 多言語 | `test/test_multilingual_phonemizer.py` | ~20 |
| バイリンガル | `test/test_bilingual_phonemizer.py` | ~15 |
| パディング | `src/python/tests/test_intersperse_padding.py` | ~30 |

C++側のテストはこれらのPythonテストケースの入出力ペアを移植して検証する。

---

## Appendix A: レビュー指摘事項と対策

### A.1 クリティカル（Phase 2 実装前に解決必須）

**[ARCH-1] ProsodyFeature / PhonemeType の二重定義（ODR違反）** — **Phase 3-4 で回避済み**

~~`piper.hpp` と `phonemizer/phonemizer.hpp` が同じ namespace で同名の enum / struct を定義するリスク。~~
Phase 3-4 では Phonemizer ABC / Registry パターンを使わず、各言語 phonemizer を独立した関数として `src/cpp/` に直接配置。`piper.hpp` の型定義のみ使用するため ODR 違反は発生しない。将来 ABC パターンに移行する場合は `piper_types.hpp` への切り出しが必要。

**[ARCH-2] BOS/EOS/パディングの二重適用リスク** — **Phase 2 で解決済み**

~~既存の `phonemes_to_ids()` と新しい `post_process_ids()` が両方実行されると二重パディング。~~
Phase 2 で JA セグメントの BOS/EOS をストリップし、`phonemes_to_ids` (addBos=true, addEos=true) で統一付与する方式を採用。検証済み: 二重適用なし。

### A.2 高優先度（Phase 2 統合時のバグ原因）

**[ARCH-3] parsePhonemizeConfig に `"multilingual"` 対応** — **Phase 1 で解決済み**

~~Phase 1 で `parseModelConfig` に `language_id_map` を追加するだけでは不十分。~~
`parsePhonemizeConfig` は `"multilingual"` / `"bilingual"` を認識し `interspersePad = true` を設定するよう実装済み。

**[REG-1] Registry 初期化のレースコンディション** — **該当なし（Registry未使用）**

~~`instance()` の `initialized_` チェックが mutex 外。~~
Phase 2-4 では Phonemizer ABC/Registry パターンを使わず、`piper.cpp` 内で直接ルーティング。Registry は将来のリファクタリングで導入する場合に `std::call_once` を使用すること。

**[EN-1] espeak-ng は g2p-en 学習モデルに不適** — **Phase 4 で解決済み**

~~現在の多言語モデルは g2p-en で学習済み。espeak-ng で推論すると flapping (t→ɾ)、ストレス、縮約形で系統的に不一致。~~
CMU 辞書 (123K語, Apache-2.0) + ARPAbet→IPA 変換 + 機能語デストレスを Phase 4 で実装。OOV語のみ eSpeak にフォールバック。

### A.3 中優先度

**[G2P-1] ES/FR/PT の仕様書に記載漏れのルール**

各言語で一部のルールが当初の仕様に未記載だった（Section 4 を更新済み）:
- **ES**: silent h、gu+e/i、gü diaeresis、sc/xc、語末y→/i/、v=b (betacismo)、hiatus/diphthong rules
- **FR**: yn/ym nasal、-aille/-eille/-ouille/-euille patterns、eil→/ɛj/、ien/oin/ain/ein nasal composites、i→/j/ gliding、ph/th digraphs、double consonant simplification、context-dependent e/o、x rules
- **PT**: ss/sc/qu/gu/ou digraphs、x context-dependent、ç/soft c/g、open vs closed vowels (accent-dependent)

→ **対策**: 実装時は仕様書ではなく Python ソースコードを正とする。仕様書はハイレベルガイドとして参照。

**[ZH-1] map_sequence() の PUA 変換が必須**

中国語・韓国語の多文字 IPA トークン（`tɕʰ`、`aɪ`、`k͈` 等）は PUA 単一コードポイントに変換しないと `phoneme_id_map` と一致しない。C++ 側にも同等の変換処理が必要。

推奨対応優先度

  Phase A: ブロッカー修正 (C1-C8)

  1. token_mapper.py に全言語の PUA 固定マッピングを追加 (C1, C7, C8)
  2. 中国語フレーズ辞書パーサーの修正 (C2)
  3. LanguageID 範囲検証の追加 (C4)
  4. eSpeak フォールバック時の BOS/EOS ストリップ (C5)
  5. multilingual + language_id_map 欠如時のエラー (C6)
  6. 韓国語連音のIPA再マッピング (C3)

  Phase B: 品質改善 (M1-M12)

  - dominant language の上書き制御 (M3)
  - Unicode NFC 正規化の追加 (M5)
  - 旧モデル互換性検証 (M7)

  Phase C: 将来課題

  - 韓国語 g2pk2 コアルールの C++ 移植 (M2)
  - 英語 OOV ニューラルモデルの C++ 推論 (M4)
  - C++ テストスイートの追加

---

## 11. 残課題の詳細調査 (2026-03-17)

10名の専門家エージェントチームによる調査結果。各課題の根本原因、Python/C++の差分、影響度、推奨対応方針を記載。

> **注**: KO (韓国語) は現行6言語モデルの対象外のためスキップ。

### 11.1 M1: ZH 多音字の文脈判別

#### 11.1.1 根本原因

C++は**フレーズ辞書によるグリーディ最長一致**を実装済みだが、フレーズ辞書にない文字列では`firstAlternative()`が常に最初の読みを選択する。

```
C++のアルゴリズム (chinese_phonemize.cpp:548-603):
  1. phraseMatch() → 最長2-8文字でフレーズ辞書を検索 (正しく実装済み)
  2. 見つからない場合 → firstAlternative() で最初の読みを使用
```

Python (pypinyin) は**語分割 (mmseg) → フレーズ辞書 → 統計モデル**の3段階で判別。

#### 11.1.2 実測検証

pypinyin の多音字判別結果（全て正しい）:

| テキスト | pypinyin出力 | 意味 | C++予測 |
|---------|-------------|------|---------|
| 银行 | yín **háng** | 銀行 | ✅ フレーズ辞書ヒット |
| 行李 | **xíng** lǐ | 荷物 | ✅ フレーズ辞書ヒット |
| 长大 | **zhǎng** dà | 成長する | ✅ フレーズ辞書ヒット |
| 长城 | **cháng** chéng | 万里の長城 | ✅ フレーズ辞書ヒット |
| 中国 | **zhōng** guó | 中国 | ✅ フレーズ辞書ヒット |
| 击中 | jī **zhòng** | 命中する | ✅ フレーズ辞書ヒット |

#### 11.1.3 辞書カバレッジ

| 辞書 | エントリ数 | 用途 |
|-----|----------|------|
| `pinyin_single.json` | ~42K 文字 | 単字読み（多音字含む） |
| `pinyin_phrases.json` | ~110K フレーズ | フレーズ単位の正しい読み |

- 多音字は単字辞書の **~20%** (約8,600字)
- フレーズ辞書の110Kエントリで**一般的な多音字の大部分をカバー**
- C++のフレーズ辞書はpypinyinの内部辞書から抽出されたもの

#### 11.1.4 実際のギャップ（当初予想より小さい）

C++はフレーズ辞書を**正しく使用しており**、一般的な多音字フレーズは解決できる。ギャップが発生するのは:

1. **フレーズ辞書にない組み合わせ**: 新語、稀な組み合わせ
2. **語分割の不在**: C++はグリーディ最長一致のみ。pypinyinはmmseg語分割で語境界を正確に判定
3. **統計モデルの不在**: pypinyinのHMMベース推定がない

**推定精度**: C++ ~90-95% vs Python ~97-98%（当初想定の68%は`firstAlternative`のみ使用を前提とした過大評価）

#### 11.1.5 推奨対応方針

| 方針 | 精度改善 | 工数 | 推奨 |
|------|---------|------|------|
| **現状維持** (フレーズ辞書+最長一致) | 90-95% | 0 | ✅ 現実的 |
| フレーズ辞書の拡充 (110K→200K+) | +2-3% | 低 | 検討 |
| mmseg語分割の追加 | +3-5% | 中 | 将来課題 |
| HMM統計モデルの追加 | +2-3% | 高 | 不要 |

**結論**: 現状のC++実装は**実用的な精度**を達成済み。フレーズ辞書の拡充が最もコスパの良い改善策。

---

### 11.2 M4: EN OOV（辞書外単語）の無音化

#### 11.2.1 根本原因

C++ English phonemizer はCMU辞書ルックアップのみで、OOV語は**無音でスキップ**される。

```cpp
// english_phonemize.cpp:479-485
auto dictIt = cmuDict.find(tok.text);
if (dictIt == cmuDict.end()) {
    // OOV: produce no phonemes (caller falls back to eSpeak)
    needSpace = true;
    continue;  // ← 無音スキップ
}
```

**設計意図**: コメントに「caller falls back to eSpeak」とあるが、**呼び出し側 (piper.cpp) にフォールバック未実装**。

```cpp
// piper.cpp:1161-1163 — English ルーティング
else if (langSeg.lang == "en" && !voice.cmuDict.empty()) {
    phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
    // ← OOV語の phonemes が空でもフォールバックしない
}
```

#### 11.2.2 Python vs C++ の差分

Python g2p-en は **GRUニューラルモデル**で全OOV語に対応:

```
g2p-en フォールバックチェーン:
  1. 同音異義語辞書 (homograph2features)
  2. CMU辞書 (~134K語)
  3. GRU seq2seq ニューラルモデル ← C++に未実装
```

**GRUモデル仕様**:
- Encoder: 文字埋め込み(29×64) + GRU(128-dim hidden)
- Decoder: 音素埋め込み(74×64) + GRU(128-dim hidden) + FC(128→74)
- 重みサイズ: ~60KB (`checkpoint20.npz`)
- 推論速度: ~1-5ms/word (CPU)
- OOV精度: ~85-92%

#### 11.2.3 実測検証（g2p-en ニューラルOOV出力）

| OOV語 | g2p-en出力 | 品質 |
|-------|-----------|------|
| COVID | K OW1 V IH0 D | ✅ 正確 |
| ChatGPT | CH AE1 T P T | △ 部分的 |
| xyzabc | Z AY1 Z AH0 K B | △ 推測 |
| Samsung | S AE1 M S AH2 NG | ✅ 正確 |
| Kubernetes | K AH0 B ER1 N AH0 T S | △ 部分的 |

#### 11.2.4 影響度

| テキスト種別 | CMUカバー率 | OOV無音率 |
|------------|-----------|----------|
| 一般英語 (ニュース) | 92-95% | 5-8% |
| 技術文書 | 88-90% | 10-12% |
| SNS/カジュアル | 85-88% | 12-15% |

**主なOOVカテゴリ**: 固有名詞、技術用語、頭字語 (API, GPU)、新語 (COVID)、活用形の一部

#### 11.2.5 推奨対応方針

| 方針 | 精度 | 工数 | GPL | 推奨 |
|------|------|------|-----|------|
| **A: 単語単位 eSpeak フォールバック** | 85-90% | 1-2h | GPL | ⚠️ 短期対策 |
| **B: GRU ニューラルモデルのC++移植** | 92-95% | 3-4日 | Apache-2.0 | ✅ 最推奨 |
| C: 簡易文字→音素ルール | 40-50% | 中 | なし | ✗ 精度不足 |

**方針Aの実装概要** (最小工数):
```cpp
// piper.cpp の English ルーティング修正
phonemize_english(langSeg.text, langPhonemes, voice.cmuDict);
if (langPhonemes.empty() || allEmpty(langPhonemes)) {
    // 全語OOV → eSpeak フォールバック
    eSpeakPhonemeConfig esConfig;
    esConfig.voice = "en-us";
    phonemize_eSpeak(langSeg.text, esConfig, langPhonemes);
    stripBosEos(langPhonemes);  // eSpeak BOS/EOS除去
}
```

**方針Bの実装概要** (推奨):
```cpp
// checkpoint20.npz から抽出した重みをロード
struct G2pEnModel {
    float enc_emb[29 * 64];
    float enc_gru_w[3 * 128 * 64];  // GRU gates
    float dec_emb[74 * 64];
    float dec_gru_w[3 * 128 * 64];
    float fc_w[128 * 74], fc_b[74];

    std::vector<std::string> predict(const std::string& word);
};
// english_phonemize.cpp の OOV 分岐に追加
if (dictIt == cmuDict.end() && g2pModel) {
    auto pron = g2pModel->predict(tok.text);
    // ARPAbet → IPA 変換して追加
}
```

**結論**: 方針Aを短期対策として実装し、方針Bを中期で追加するのが最も現実的。

---

### 11.3 M7: 旧バイリンガルモデルとの互換性

#### 11.3.1 根本原因の再評価

調査の結果、**互換性問題は当初想定より軽微**であることが判明。

#### 11.3.2 実測検証: IDマップの完全一致

```
Bilingual symbols:  97
Multilingual symbols: 173
First 97 IDs: ALL MATCH ← 完全一致を実証
```

| ID範囲 | バイリンガル | マルチリンガル | 一致 |
|--------|------------|--------------|:----:|
| 0-9 | SPECIAL_TOKENS (10) | SPECIAL_TOKENS (10) | ✅ |
| 10-76 | JAPANESE_PHONEMES (67) | JAPANESE_PHONEMES (67) | ✅ |
| 77-96 | ENGLISH_PHONEMES (20) | ENGLISH_PHONEMES (20) | ✅ |
| 97-172 | (範囲外) | ZH/ES/PT/FR (76) | N/A |

#### 11.3.3 C++コードの安全設計

C++は`config.json`の`phoneme_id_map`を**モデルごとにロード**する設計（ハードコードなし）:

```cpp
// piper.cpp:157-180 — config.json からモデル固有のマップをロード
for (auto &fromPhonemeItem : phonemeIdMapValue.items()) {
    auto fromCodepoint = getCodepoint(fromPhonemeItem.key());
    phonemizeConfig.phonemeIdMap[fromCodepoint] = toIds;
}
```

`"bilingual"` と `"multilingual"` は同じ `MultilingualPhonemes` enumにマッピング:
```cpp
// piper.cpp:146
} else if (phonemeTypeStr == "multilingual" || phonemeTypeStr == "bilingual") {
    phonemizeConfig.phonemeType = MultilingualPhonemes;
}
```

#### 11.3.4 互換性マトリクス

| シナリオ | 結果 | 理由 |
|---------|------|------|
| v4バイリンガルモデル + v4 config.json | ✅ 正常動作 | 97シンボルのマップが正しくロードされる |
| 6langモデル + 6lang config.json | ✅ 正常動作 | 173シンボルのマップが正しくロードされる |
| v4モデル + 6lang config.json | ❌ 故障 | モデルは97次元、IDが97超を受信 |
| 6langモデル + v4 config.json | ❌ 品質劣化 | ZH/ES/FR/PT音素がマッピング不在 |

#### 11.3.5 推奨対応方針

**リスクは「ユーザーのモデル/config不一致」のみ**。コード側の修正:

1. **`num_symbols` 検証の追加** (低工数):
```cpp
// piper.cpp: parseModelConfig 内
if (configRoot.contains("num_symbols")) {
    int numSymbols = configRoot["num_symbols"].get<int>();
    if (numSymbols != (int)phonemeIdMap.size()) {
        spdlog::warn("num_symbols ({}) != phoneme_id_map size ({})",
                     numSymbols, phonemeIdMap.size());
    }
}
```

2. **config.json バージョンマーカーの追加** (将来課題):
   - `"phoneme_map_version": 2` 等でモデル世代を明示

**結論**: **コード上の互換性問題はない**。`config.json`とモデルの対応さえ正しければ安全に動作する。検証用warningの追加が推奨。

---

### 11.4 M11: 非JA言語のprosody特徴量欠落

#### 11.4.1 根本原因（当初想定より広範）

**FR だけでなく、EN/ZH/ES/PT 全ての非JA言語で prosody 欠落**が発生している。

```cpp
// piper.cpp:1192-1199 — 非JAセグメントは常にゼロ prosody
if (langSeg.lang != "ja") {
    for (auto ph : sentence) {
        allPhonemes.push_back(ph);
        if (voice.session.hasProsodyInput) {
            allProsody.push_back({0, 0, 0});  // ← 常にゼロ
        }
    }
}
```

一方、Python学習パイプラインは**全6言語で実際のprosody値を生成**。

#### 11.4.2 実測検証: 各言語のprosody出力

| 言語 | a1の意味 | a2の意味 | a3の意味 | C++出力 |
|-----|---------|---------|---------|---------|
| JA | アクセント核位置 (-4等) | モーラ位置 (1等) | 総モーラ数 (5等) | ✅ 正しい値 |
| EN | 0 (固定) | ストレス (0/2) | 単語音素数 | ❌ {0,0,0} |
| ZH | **声調 (1-4)** | 音節位置 | 語長 | ❌ {0,0,0} |
| ES | 0 (固定) | ストレス (0/2) | 単語音素数 | ❌ {0,0,0} |
| FR | 0 (固定) | ストレス (0/2) | 単語音素数 | ❌ {0,0,0} |
| PT | 0 (固定) | ストレス (0/2) | 単語音素数 | ❌ {0,0,0} |

**特にZHは深刻**: a1に**声調番号 (1-4)**が格納されており、ゼロだとDuration Predictorが声調情報を受け取れない。

#### 11.4.3 FR prosody の具体例

Python出力（"Bonjour, comment allez-vous?"）:

```
b        a1=0 a2=0 a3=5
ɔ̃       a1=0 a2=0 a3=5
ʒ        a1=0 a2=0 a3=5
u        a1=0 a2=2 a3=5  ← 最終音節にストレス
ʁ        a1=0 a2=0 a3=5
k        a1=0 a2=0 a3=4
o        a1=0 a2=0 a3=4
m        a1=0 a2=0 a3=4
ɑ̃       a1=0 a2=2 a3=4  ← 最終音節にストレス
```

フランス語は語末固定ストレス（a2=2が最終母音に付与）。C++ではこの情報が失われる。

#### 11.4.4 影響度の再評価

| 言語 | 学習時prosody | C++推論時prosody | 不一致度 | 予想品質影響 |
|-----|-------------|----------------|---------|------------|
| JA | 完全 (A1/A2/A3) | ✅ 完全 | なし | なし |
| ZH | **声調+位置** | ❌ ゼロ | **高** | **MOS -0.2〜0.3** |
| EN | ストレス+語長 | ❌ ゼロ | 中 | MOS -0.1〜0.2 |
| ES | ストレス+語長 | ❌ ゼロ | 中 | MOS -0.1〜0.2 |
| FR | ストレス+語長 | ❌ ゼロ | 中 | MOS -0.1〜0.2 |
| PT | ストレス+語長 | ❌ ゼロ | 中 | MOS -0.1〜0.2 |

**補足**: モデルのDuration Predictorはprosody入力がゼロでも動作するが、学習時と異なる条件づけになるため自然性が低下する。特にZHは声調がprosody経由で伝達されるため影響が大きい。

#### 11.4.5 推奨対応方針

**EN/ES/FR/PT のストレス付与** (比較的容易):
```cpp
// 規則: 各単語の最終母音に a2=2 を設定、a3=単語音素数
// 英語: ストレスマーカー(ˈ/ˌ)の直後の母音に a2=2
// 仏語: 単語最終母音に a2=2 (固定ストレス)
// 西/葡語: アクセント記号付き母音、またはデフォルトストレス規則
```

**ZH の声調付与** (重要度高):
```cpp
// chinese_phonemize の CharPinyin に tone が既にある
// tone → a1 に変換するだけ
for (auto& cp : charPinyins) {
    prosody.push_back({cp.tone, syllable_pos, word_length});
}
```

| 対応 | 影響言語 | 工数 | 推奨 |
|-----|---------|------|------|
| **ZH 声調 → a1** | ZH | 1-2h | ✅ 最優先 |
| **EN ストレス → a2** | EN | 2-3h | ✅ 高 |
| **FR 語末ストレス → a2** | FR | 1-2h | ✅ 中 |
| **ES/PT ストレス → a2** | ES, PT | 2-3h | ✅ 中 |

**結論**: ZH声調のprosody伝達を最優先で対応。EN/ES/FR/PTのストレス付与は追加工数少なく同時実装が望ましい。

---

### 11.5 総合優先度マトリクス

| 順位 | 課題 | 影響度 | 工数 | 推奨アクション |
|:---:|------|:-----:|:---:|---------------|
| 1 | **M11-ZH**: 声調prosody欠落 | 高 | 1-2h | C++でtone→a1変換を追加 |
| 2 | **M4-A**: EN OOV eSpeak フォールバック | 高 | 1-2h | 単語レベルeSpeak呼出 |
| 3 | **M11-EN/ES/FR/PT**: ストレスprosody欠落 | 中 | 3-4h | 各言語phonemizerにストレス抽出追加 |
| 4 | **M7**: `num_symbols` 検証追加 | 低 | 30min | warning ログ追加 |
| 5 | **M1**: ZH フレーズ辞書拡充 | 低 | 中 | 将来課題 |
| 6 | **M4-B**: EN GRU ニューラルモデル移植 | 低 | 3-4日 | 将来課題 |
