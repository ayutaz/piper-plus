# C++ Multilingual G2P Implementation Specification

> Branch: `feat/cpp-multilingual-g2p` (based on `feat/bilingual-phonemizer`)
> Date: 2026-03-16

## 1. Overview

Python側の多言語音素化パイプライン(7言語: JA/EN/ZH/KO/ES/FR/PT)をC++推論側に対応させるための技術仕様書。

### 1.1 現状のギャップ

| 機能 | Python | C++ |
|------|--------|-----|
| 言語検出 | UnicodeLanguageDetector | なし |
| `lid` テンソル | ONNX入力として送信 | 未実装（クラッシュ） |
| `language_id_map` | config.jsonから読込 | 未パース |
| 多言語音素化ルーティング | 7言語レジストリ | 3エンジン固定 |
| コードスイッチング | セグメント分割+言語別処理 | 不可 |

### 1.2 実装フェーズ

| Phase | 内容 | 工数目安 |
|-------|------|---------|
| **Phase 1** | ONNX `lid` テンソル + config解析 + アダプター層 | 小 |
| **Phase 2** | UnicodeLanguageDetector + MultilingualPhonemizer | 中 |
| **Phase 3** | ES/FR/PT ルールベースG2Pポート | 中 |
| **Phase 4** | EN g2p-en互換(CMU辞書) / ZH pinyin変換テーブル / KO ハングル分解 | 大 |

---

## 2. Phase 1: ONNX `lid` テンソル統合

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

### 2.2 piper.hpp 変更

```cpp
// line 22 の後に追加
typedef int64_t LanguageId;

// SynthesisConfig に追加 (line 75 の後)
std::optional<LanguageId> languageId;

// ModelConfig に追加
int numLanguages = 1;
std::optional<std::map<std::string, LanguageId>> languageIdMap;

// ModelSession に追加 (line 96 の後)
bool hasLanguageInput = false;

// PhonemeType enum に追加
enum PhonemeType {
  eSpeakPhonemes,
  TextPhonemes,
  OpenJTalkPhonemes,
  MultilingualPhonemes  // NEW
};
```

### 2.3 piper.cpp 変更

**parseModelConfig()** — `num_languages` と `language_id_map` を読込:
```cpp
if (configRoot.contains("num_languages")) {
  modelConfig.numLanguages = configRoot["num_languages"].get<int>();
}
if (configRoot.contains("language_id_map")) {
  modelConfig.languageIdMap.emplace();
  for (auto &item : configRoot["language_id_map"].items()) {
    (*modelConfig.languageIdMap)[item.key()] = item.value().get<LanguageId>();
  }
}
```

**loadModel()** — `"lid"` 入力検出:
```cpp
} else if (name == "lid") {
  session.hasLanguageInput = true;
  spdlog::debug("Model supports multi-language (lid input)");
}
```

**synthesize()** — `lid` テンソル構築（`sid` の後、`prosody_features` の前）:
```cpp
std::vector<int64_t> languageId{(int64_t)synthesisConfig.languageId.value_or(0)};
std::vector<int64_t> languageIdShape{(int64_t)languageId.size()};

if (session.hasLanguageInput) {
  inputTensors.push_back(Ort::Value::CreateTensor<int64_t>(
      memoryInfo, languageId.data(), languageId.size(),
      languageIdShape.data(), languageIdShape.size()));
  inputNamesVec.push_back("lid");
}
```

### 2.4 main.cpp 変更

- `--language` (`-l`) CLIオプション追加
- 言語コード or 数値IDを受け付け、`language_id_map` から解決
- JSON入力で `language_id` / `language` フィールドサポート

### 2.5 後方互換性

- 単言語モデル: `hasLanguageInput = false` → `lid` テンソルは作成されない → 動作変更なし
- `--language` 未指定時: `languageId = 0`（デフォルト、通常は日本語）

---

## 3. Phase 2: UnicodeLanguageDetector

### 3.1 Unicode範囲チェック

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

### 3.2 CJK曖昧性解消

テキスト全体を事前スキャンし `context_has_kana` フラグを計算:
- 仮名あり → CJK漢字は **JA**
- 仮名なし → CJK漢字は **ZH**

### 3.3 テキストセグメンテーション

文字ごとに言語を判定し、言語が変わるたびにセグメント境界を作成。ニュートラル文字（空白・数字・句読点）は直前のセグメントに付随。

```
"今日はgoodですね" → [("ja","今日は"), ("en","good"), ("ja","ですね")]
```

### 3.4 C++実装

```cpp
// src/cpp/phonemizer/language_detector.hpp
class UnicodeLanguageDetector {
public:
  UnicodeLanguageDetector(const std::vector<std::string>& languages,
                          const std::string& defaultLatinLang = "en");
  std::string detectChar(char32_t ch, bool contextHasKana) const;
  bool hasKana(const std::string& utf8Text) const;
  std::vector<LangSegment> segmentText(const std::string& utf8Text) const;
};
```

ICU不要。既存の `utf8.h` によるコードポイント範囲チェックで実装可能。

---

## 4. Phase 3: ルールベースG2Pポート (ES/FR/PT)

外部依存なし、純粋な文字列処理のみ。

### 4.1 Spanish Phonemizer

**ソース**: `src/python/piper_train/phonemize/spanish.py` (868行)

**パイプライン**: テキスト → 正規化 → トークン化 → G2P(文字走査) → 音節分割 → ストレス割当 → 異音変換 → PUAマッピング

**主要ルール**:
- **Seseo**: c+e/i → `s`, z → `s` (ラテンアメリカ発音)
- **Yeismo**: ll → `ʝ`, y → `ʝ`
- **異音変換 (b/d/g)**: 語頭・鼻音後・l後 → 閉鎖音、それ以外 → 摩擦音
- **rr**: 語頭r, l/n/s後r → 顫動音 `rr` (PUA U+E01D)
- **qu**: qu → `k` (u無音)
- **Digraphs**: ch→`tʃ`, ll→`ʝ`, rr→`rr`

**音節分割**: 不可分オンセットクラスタ 12個: bl, br, cl, cr, dr, fl, fr, gl, gr, pl, pr, tr, tl

**ストレス**: アクセント記号優先 → デフォルト（母音/n/s終わり=後ろから2番目、それ以外=最後）、機能語27語はストレスなし

**データ量**: 静的テーブル合計 < 1KB。外部依存なし。

### 4.2 French Phonemizer

**ソース**: `src/python/piper_train/phonemize/french.py` (776行)

**パイプライン**: テキスト → 正規化 → トークン化(アポストロフィ対応) → G2P(左→右最長一致) → PUAマッピング

**主要ルール**:
- **鼻母音**: an/en→`ɑ̃`, in→`ɛ̃`, on→`ɔ̃`, un→`ɛ̃` (後続が母音 or nn/mm の場合は非鼻音化)
- **-tion**: `s j ɔ̃`（stion の場合は `t j ɔ̃`）
- **-ille**: `i j`（例外: ville, mille, tranquille → `i l`）
- **-er**: 多音節語 → `e`（例外13語: hiver, enfer, amer, cancer, super, laser, hamster, master, poster, cluster, starter, leader, transfer）
- **eau**: `o`、ou → `u`、oi → `w a`、ai → `ɛ`、eu → `ø`/`œ`
- **語末黙字**: d, g, h, m, n, p, s, t, x, z
- **母音間 s 有声化**: s → `z`
- **u+i**: `ɥ i` (半母音)

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
- **Digraphs**: nh→`ɲ`, lh→`ʎ`, ch→`ʃ`, rr→`ʁ`, ss→`s`

---

## 5. Phase 4: 外部依存言語

### 5.1 English — 推奨戦略

**注意**: 現在の多言語モデルは g2p-en で学習されている。espeak-ng を使うとフラッピング・ストレス・縮約形で系統的な不一致が発生し、音質が劣化する。

**推奨**: CMU辞書バンドル（~134K語、Public Domain）をPhase 1として実装。95-98%カバレッジで工数も低い。

| 戦略 | 精度 | 工数 | GPL | 備考 |
|------|------|------|-----|------|
| espeak-ng | g2p-en学習モデルでは劣化 | なし | GPL | letter, better 等でt→ɾ不一致 |
| **CMU辞書のみ（推奨）** | **95-98%** | **低** | **Apache-2.0** | OOV語はフォールバック必要 |
| CMU辞書 + GRU | 99%+ | 中-高 | Apache-2.0 | 将来的に追加 |

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

## 6. C++ アーキテクチャ設計

### 6.1 ディレクトリ構成

```
src/cpp/phonemizer/
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
  static PhonemizerRegistry& instance();
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
```

---

## 7. 多言語Phoneme IDマップ

### 7.1 統一IDマップ構造

config.json の `phoneme_id_map` はそのままC++で使用可能。全キーはPUA変換済みの単一コードポイント。

**ID配置（概念）**:
```
[0..9]     特殊トークン (_, ^, $, ?, ?!, ?., ?~, #, [, ])
[10..63]   日本語音素 (共有音素含む: a, k, b, ...)
[64..86]   英語固有音素 (23個: ɑ, æ, ʌ, ː, ŋ, ɹ, ʃ, ...)
[87+]      ZH固有(~49) → KO固有(~11) → ES固有(~7) → PT固有(~11) → FR固有(~6)
```

合計: ~171 シンボル（7言語、重複排除後）

### 7.2 PUA固定マッピング (U+E000-E01E)

| Codepoint | Token | 言語 |
|-----------|-------|------|
| U+E000-E015 | JA長母音・口蓋化子音・促音 | JA |
| U+E016-E018 | 疑問詞マーカー (?!, ?., ?~) | JA |
| U+E019-E01C | Nバリアント (N_m, N_n, N_ng, N_uvular) | JA |
| U+E01D | `rr` (顫動音) | ES |
| U+E01E | `y_vowel` (前舌円唇母音) | ZH, FR |

### 7.3 PUA動的マッピング (U+E020+)

ZH: 送気音・そり舌音・複合韻母・声調マーカー (~30トークン)
KO: 緊張子音・無解放終声 (~8トークン)
EN: 二重母音・破擦音 (~3トークン)
FR/PT: 鼻母音 (~3-5トークン)

### 7.4 BOS/EOS/パディング

多言語モデルは統一パディング方式: `BOS _ ph1 _ ph2 _ ... _ phN _ EOS`

- `interspersePad = true`（すべての言語セグメント共通）
- 日本語セグメントのBOS/EOSはストリップされ、最終的に統一方式で再付与
- EOS選択: 最後のセグメントの言語に依存（日本語疑問文→PUA疑問マーカー）

---

## 8. config.json フォーマット

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

---

## 9. テストケース概要

各言語のテストケースは Python テストファイルに完全に定義済み:

| 言語 | テストファイル | テスト数 |
|------|-------------|---------|
| ES | `test/test_spanish_phonemizer.py` | ~30 |
| FR | `test/test_french_phonemizer.py` | ~50 |
| PT | `test/test_portuguese_phonemizer.py` | ~40 |
| ZH | `test/test_chinese_phonemizer.py` | ~20 |
| KO | `test/test_korean_phonemizer.py` | ~25 |
| 多言語 | `test/test_multilingual_phonemizer.py` | ~20 |
| バイリンガル | `test/test_bilingual_phonemizer.py` | ~15 |
| パディング | `src/python/tests/test_intersperse_padding.py` | ~30 |

C++側のテストはこれらのPythonテストケースの入出力ペアを移植して検証する。

---

## Appendix A: レビュー指摘事項と対策

### A.1 クリティカル（実装前に解決必須）

**[ARCH-1] ProsodyFeature / PhonemeType の二重定義（ODR違反）**

`piper.hpp` と `phonemizer/phonemizer.hpp` が同じ namespace で同名の enum / struct を定義している。同一翻訳単位でインクルードするとコンパイルエラー。

→ **対策**: `src/cpp/piper_types.hpp` に共通型を切り出し、両方からインクルード。`phonemizer.hpp` は enum を拡張（値 3-10 を追加）しつつ元の値 0-2 を保持。

**[ARCH-2] BOS/EOS/パディングの二重適用リスク**

既存の `phonemes_to_ids()` (piper-phonemize ライブラリ) と新しい `post_process_ids()` が両方実行されると二重パディングになる。

→ **対策**: `MultilingualPhonemes` タイプの場合は phonemizer の `post_process_ids()` を使い、既存の `phonemes_to_ids()` はスキップ。レガシータイプは既存パスを維持。

**[ARCH-3] parsePhonemizeConfig に `"multilingual"` 未対応**

Phase 1 で `parseModelConfig` に `language_id_map` を追加するだけでは不十分。`parsePhonemizeConfig` も `"phoneme_type": "multilingual"` を認識して `interspersePad = true` を設定する必要がある。

### A.2 高優先度（統合時のバグ原因）

**[REG-1] Registry 初期化のレースコンディション**

`instance()` の `initialized_` チェックが mutex 外。複数スレッドから同時にアクセスすると `auto_register()` が二重実行される。

→ **対策**: `std::call_once` を使用。

**[EN-1] espeak-ng は g2p-en 学習モデルに不適**

現在の多言語モデルは g2p-en で学習済み。espeak-ng で推論すると flapping (t→ɾ)、ストレス、縮約形で系統的に不一致。

→ **対策**: EN は CMU 辞書ルックアップ (Apache-2.0) を Phase 1 として実装。

### A.3 中優先度

**[G2P-1] ES/FR/PT の仕様書に記載漏れのルール**

各言語で一部のルールが仕様に未記載:
- **ES**: silent h、gu+e/i、gü diaeresis、sc/xc、語末y→/i/、v=b (betacismo)、hiatus/diphthong rules
- **FR**: yn/ym nasal、-aille/-eille/-ouille/-euille patterns、eil→/ɛj/、ien/oin/ain/ein nasal composites、i→/j/ gliding、ph/th digraphs、double consonant simplification、context-dependent e/o
- **PT**: ss/sc/qu/gu/ou digraphs、x context-dependent、ç/soft c/g、open vs closed vowels (accent-dependent)

→ **対策**: 実装時は仕様書ではなく Python ソースコードを正とする。仕様書はハイレベルガイドとして参照。

**[IDM-1] 言語登録順序**

コードの正規順序: `ja, en, zh, ko, es, pt, fr`（config.json の `language_id_map` もこの順序）。KO はデータセットにはないが Phonemizer は実装済み。

**[ZH-1] map_sequence() の PUA 変換が必須**

中国語・韓国語の多文字 IPA トークン（`tɕʰ`、`aɪ`、`k͈` 等）は PUA 単一コードポイントに変換しないと `phoneme_id_map` と一致しない。C++ 側にも同等の変換処理が必要。
