# C++ Multilingual G2P Implementation Specification

> Branch: `feat/cpp-multilingual-g2p` (based on `feat/bilingual-phonemizer`)
> Date: 2026-03-16
> Last updated: 2026-03-16

## 1. Overview

Python側の多言語音素化パイプライン(7言語: JA/EN/ZH/KO/ES/FR/PT)をC++推論側に対応させるための技術仕様書。

### 1.1 現状のギャップ

| 機能 | Python | C++ | Phase 1 対応 |
|------|--------|-----|:---:|
| `lid` テンソル | ONNX入力として送信 | **実装済み** | **Done** |
| `language_id_map` | config.jsonから読込 | **実装済み** | **Done** |
| `--language` CLI | infer_onnx.py で対応 | **実装済み** | **Done** |
| 言語検出 | UnicodeLanguageDetector | 未実装 | Phase 2 |
| 多言語音素化ルーティング | 7言語レジストリ | 3エンジン固定 | Phase 2-4 |
| コードスイッチング | セグメント分割+言語別処理 | 未実装 | Phase 2 |

### 1.2 実装フェーズ

| Phase | 内容 | 状態 |
|-------|------|:----:|
| **Phase 1** | ONNX `lid` テンソル + config解析 + CLI `--language` | **Done** (commit `f0e841e`) |
| **Phase 2** | UnicodeLanguageDetector + MultilingualPhonemizer | TODO |
| **Phase 3** | ES/FR/PT ルールベースG2Pポート | TODO |
| **Phase 4** | EN CMU辞書 / ZH pypinyin辞書 / KO ハングル分解 | TODO |

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

## 3. Phase 2: UnicodeLanguageDetector — TODO

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

## 4. Phase 3: ルールベースG2Pポート (ES/FR/PT) — TODO

外部依存なし、純粋な文字列処理のみ。実装時は Python ソースコードを正とする。

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

## 5. Phase 4: 外部依存言語 — TODO

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

## 6. C++ アーキテクチャ設計 — Phase 2+ で実装

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

**言語登録の正規順序**: `ja, en, zh, ko, es, pt, fr`（config.json の `language_id_map` もこの順序）。KO はデータセットにはないが Phonemizer は実装済み。

### 7.2 PUA固定マッピング (U+E000-E01E)

| Codepoint | Token | 言語 |
|-----------|-------|------|
| U+E000-E015 | JA長母音・口蓋化子音・促音 (22個) | JA |
| U+E016-E018 | 疑問詞マーカー (?!, ?., ?~) | JA |
| U+E019-E01C | Nバリアント (N_m, N_n, N_ng, N_uvular) | JA |
| U+E01D | `rr` (顫動音) | ES |
| U+E01E | `y_vowel` (前舌円唇母音) | ZH, FR |

C++ `puaToPhoneme` マップ (piper.cpp) は U+E000-E01E の全31エントリに対応済み (Phase 1 で E01D/E01E を追加)。

### 7.3 PUA動的マッピング (U+E020+)

ZH: 送気音・そり舌音・複合韻母・声調マーカー (~30トークン)
KO: 緊張子音・無解放終声 (~8トークン)
EN: 二重母音・破擦音 (~3トークン)
FR/PT: 鼻母音 (~3-5トークン)

**注意**: 動的PUAの実際のコードポイントは Python の `token_mapper.register()` 呼出し順に依存する。C++側は config.json の `phoneme_id_map` を正として使用し、動的PUAの具体値には依存しない設計。

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

C++ は `num_languages`、`language_id_map`、`phoneme_type: "multilingual"` を Phase 1 で対応済み。

---

## 9. テストケース概要

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

**[ARCH-1] ProsodyFeature / PhonemeType の二重定義（ODR違反）**

`piper.hpp` と将来の `phonemizer/phonemizer.hpp` が同じ namespace で同名の enum / struct を定義するリスク。同一翻訳単位でインクルードするとコンパイルエラー。

→ **対策**: `src/cpp/piper_types.hpp` に共通型を切り出し、両方からインクルード。`phonemizer.hpp` は enum を拡張（値 3-10 を追加）しつつ元の値 0-2 を保持。

**[ARCH-2] BOS/EOS/パディングの二重適用リスク**

既存の `phonemes_to_ids()` (piper-phonemize ライブラリ) と新しい `post_process_ids()` が両方実行されると二重パディングになる。

→ **対策**: `MultilingualPhonemes` タイプの場合は phonemizer の `post_process_ids()` を使い、既存の `phonemes_to_ids()` はスキップ。レガシータイプは既存パスを維持。

### A.2 高優先度（Phase 2 統合時のバグ原因）

**[ARCH-3] parsePhonemizeConfig に `"multilingual"` 対応** — **Phase 1 で解決済み**

~~Phase 1 で `parseModelConfig` に `language_id_map` を追加するだけでは不十分。~~
`parsePhonemizeConfig` は `"multilingual"` / `"bilingual"` を認識し `interspersePad = true` を設定するよう実装済み。

**[REG-1] Registry 初期化のレースコンディション**

`instance()` の `initialized_` チェックが mutex 外。複数スレッドから同時にアクセスすると `auto_register()` が二重実行される。

→ **対策**: Phase 2 で `std::call_once` を使用。

**[EN-1] espeak-ng は g2p-en 学習モデルに不適**

現在の多言語モデルは g2p-en で学習済み。espeak-ng で推論すると flapping (t→ɾ)、ストレス、縮約形で系統的に不一致。

→ **対策**: EN は CMU 辞書ルックアップ (Apache-2.0) を Phase 4 で実装。

### A.3 中優先度

**[G2P-1] ES/FR/PT の仕様書に記載漏れのルール**

各言語で一部のルールが当初の仕様に未記載だった（Section 4 を更新済み）:
- **ES**: silent h、gu+e/i、gü diaeresis、sc/xc、語末y→/i/、v=b (betacismo)、hiatus/diphthong rules
- **FR**: yn/ym nasal、-aille/-eille/-ouille/-euille patterns、eil→/ɛj/、ien/oin/ain/ein nasal composites、i→/j/ gliding、ph/th digraphs、double consonant simplification、context-dependent e/o、x rules
- **PT**: ss/sc/qu/gu/ou digraphs、x context-dependent、ç/soft c/g、open vs closed vowels (accent-dependent)

→ **対策**: 実装時は仕様書ではなく Python ソースコードを正とする。仕様書はハイレベルガイドとして参照。

**[ZH-1] map_sequence() の PUA 変換が必須**

中国語・韓国語の多文字 IPA トークン（`tɕʰ`、`aɪ`、`k͈` 等）は PUA 単一コードポイントに変換しないと `phoneme_id_map` と一致しない。C++ 側にも同等の変換処理が必要。
