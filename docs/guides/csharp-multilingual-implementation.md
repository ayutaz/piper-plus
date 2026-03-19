# C# CLI 6言語マルチリンガル対応 — 実装ガイド

## 概要

C# CLI (`PiperPlus.Cli`) に中国語 (zh)、スペイン語 (es)、フランス語 (fr)、ポルトガル語 (pt) の4言語を追加し、Python/Rust と同等の6言語マルチリンガル対応を実現する。

**状態:** 全 Phase 完了 — JA + EN + ZH + ES + FR + PT の6言語対応 + 多言語自動ルーティング

### 進捗状況

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 1 | G2P Engine Interfaces (4ファイル) | **完了** |
| Phase 2 | Phonemizer Classes (4ファイル) | **完了** |
| Phase 3 | PUA Mapping 拡張 (29→87エントリ) | **完了** |
| Phase 4 | CLI 統合 (`Program.cs` + ラッパー + `--language`) | **完了** |
| Phase 5 | MultilingualPhonemizer + UnicodeLanguageDetector | **完了** |
| Phase 6 | テスト (94テストケース追加) | **完了** |
| Phase 7 | NuGet 依存関係 (DotNetG2P.* v1.7.0) | **完了** |

---

## G2P エンジン: dot-net-g2p

**リポジトリ:** https://github.com/ayutaz/dot-net-g2p
**バージョン:** v1.7.0 (2026-03-18)
**ライセンス:** Apache-2.0
**ターゲット:** .NET Standard 2.1

### パッケージ構成

| パッケージ | 用途 | スレッド安全 |
|-----------|------|------------|
| `DotNetG2P.Chinese` | 中国語 G2P (pinyin-data dict, tone sandhi) | Yes |
| `DotNetG2P.Spanish` | スペイン語 G2P (rule-based, syllabification) | Yes |
| `DotNetG2P.French` | フランス語 G2P (rule-based + exception dict) | Yes |
| `DotNetG2P.Portuguese` | ポルトガル語 G2P (rule-based + exception dict) | Yes |
| `DotNetG2P.Multilingual` | 多言語ルーティング (Unicode range detection) | Yes |

### piper-plus 互換 API

dot-net-g2p は piper-plus との互換性が組み込まれている。

#### 中国語 (`ChineseG2PEngine`)
```csharp
var engine = new ChineseG2PEngine();

// piper-plus 互換 IPA (トーン付き)
string ipa = engine.ToPiperIPA("你好世界");

// PUA マッピング済みフォネーム
string[] pua = engine.ToPuaPhonemes("你好世界");
// → PUA codepoint mapped phonemes (U+E020–U+E04A)

// Prosody付き
var result = engine.ToIpaWithProsody("你好世界");
// → ChineseProsodyResult { Phonemes, Prosody }
// ChineseProsodyInfo: A1=tone(1-5), A2=syllable_pos(1-based), A3=word_length
```

#### スペイン語 (`SpanishG2PEngine`)
```csharp
var engine = new SpanishG2PEngine();
string ipa = engine.ToIPA("Hola, ¿cómo estás?");
IReadOnlyList<SpanishPhoneme> phonemes = engine.ToPhonemeList("Hola");
// SpanishPhoneme: Phoneme (enum), IsStressed (bool)
```

#### フランス語 (`FrenchG2PEngine`)
```csharp
var engine = new FrenchG2PEngine();
string ipa = engine.ToIPA("Bonjour, comment allez-vous?");
IReadOnlyList<FrenchPhoneme> phonemes = engine.ToPhonemeList("bonjour");
// FrenchPhoneme: Phoneme (enum), IsVowel, IsNasalVowel
```

#### ポルトガル語 (`PortugueseG2PEngine`)
```csharp
var engine = new PortugueseG2PEngine();
// Brazilian Portuguese (default)
string ipa = engine.ToIPA("Olá, como você está?");
IReadOnlyList<PortuguesePhoneme> phonemes = engine.ToPhonemeList("Brasil");
// PortuguesePhoneme: Phoneme (enum), IsStressed, IsNasalVowel
```

---

## C# アーキテクチャ

### IPhonemizer インターフェース

```csharp
public interface IPhonemizer
{
    List<string> Phonemize(string text);
    (List<string> Tokens, List<ProsodyInfo?> Prosody) PhonemizeWithProsody(string text);
    Dictionary<string, int[]>? GetPhonemeIdMap();

    // デフォルト実装 (no-op pass-through)
    (List<int> Ids, List<ProsodyInfo?> Prosody) PostProcessIds(
        List<int> phonemeIds, List<ProsodyInfo?> prosodyFeatures,
        Dictionary<string, int[]> phonemeIdMap);
}

public record ProsodyInfo(int A1, int A2, int A3);
```

### 実装パターン一覧

| 実装 | G2P Engine Interface | PostProcessIds | ストレス処理 |
|------|---------------------|----------------|-------------|
| `JapanesePhonemizer` | `IJapaneseG2PEngine` | no-op | Engine (アクセント核) |
| `EnglishPhonemizer` | `IEnglishG2PEngine` | EspeakPostProcessIds | ARPAbet stress数字 |
| `ChinesePhonemizer` | `IChineseG2PEngine` | EspeakPostProcessIds | Engine (tone 1-5) |
| `SpanishPhonemizer` | `ISpanishG2PEngine` | EspeakPostProcessIds | ˈ 読取・出力維持 |
| `FrenchPhonemizer` | `IFrenchG2PEngine` | EspeakPostProcessIds | 最終母音検出 |
| `PortuguesePhonemizer` | `IPortugueseG2PEngine` | EspeakPostProcessIds | ˈ 読取・除去 |
| `MultilingualPhonemizer` | 複数 IPhonemizer | 動的EOS対応 | 委譲先に依存 |

### パイプライン全体像

```
text
  → CustomDictionary.ApplyToText(text)        [optional]
  → phonemizer.PhonemizeWithProsody(text)
    → (List<string> tokens, List<ProsodyInfo?> prosody)
  → PhonemeEncoder.Encode(phonemizer, text, phonemeIdMap)
    → token → phonemeIdMap[token] → int[] ids
    → phonemizer.PostProcessIds(ids, prosody, map)
  → PhonemeEncoder.EncodeDirect(...)
    → long[] phonemeIds, long[]? prosodyFlat
  → PiperSession.Synthesize(input)
    → ONNX → float[] audio → short[] PCM
```

### 多言語パイプライン (MultilingualPhonemizer)

```
text "こんにちはhello"
  → UnicodeLanguageDetector.SegmentText(text)
    → [("ja", "こんにちは"), ("en", "hello")]
  → foreach segment:
    → phonemizers[lang].PhonemizeWithProsody(segment)
    → strip BOS/EOS, track _lastEos
  → concatenate all segments
  → PostProcessIds (dynamic EOS: $ or ? or ?! etc.)
```

---

## 各言語の音素化仕様

### 中国語 (zh)

| 項目 | 値 |
|------|-----|
| 方式 | pypinyin辞書ベース + IPA変換 |
| dot-net-g2p API | `ToPiperIPA()`, `ToPuaPhonemes()`, `ToIpaWithProsody()` |
| 声調 | tone1–tone5 (5=軽声) |
| 声調変調 | T3+T3→T2+T3, 一+T4→T2, 一+T1/T2/T3→T4, 不+T4→T2 |
| 児化音 | 末尾 r → ɚ 挿入 (standalone er は除外) |
| 句読点 | 全角→半角マッピング (。→. ，→, 等) |
| PUA範囲 | U+E020–U+E04A (固定43エントリ) |
| Prosody | A1=tone(1-5), A2=syllable_pos, A3=word_length |

### スペイン語 (es)

| 項目 | 値 |
|------|-----|
| 方式 | 完全ルールベース (外部依存なし) |
| 方言 | ラテンアメリカ (seseo, yeísmo) |
| 異音交替 | b/v (b↔β), d (d↔ð), g (ɡ↔ɣ) |
| PUA | `rr`→U+E01D, `tʃ`→U+E054 |
| Prosody | A1=0, A2=2(stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **出力に含む** (Python と同一) |

### フランス語 (fr)

| 項目 | 値 |
|------|-----|
| 方式 | ルールベース (最長一致左→右スキャン) |
| 特殊ルール | -er→/e/, -ille→/ij/ (ville/mille除外), -tion→/sjɔ̃/ |
| PUA | ɛ̃→U+E056, ɑ̃→U+E057, ɔ̃→U+E058, y_vowel→U+E01E |
| Prosody | A1=0, A2=2(last vowel=stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **出力に含まない** (Phonemizer が最終母音を検出) |

### ポルトガル語 (pt)

| 項目 | 値 |
|------|-----|
| 方式 | ルールベース (Brazilian Portuguese) |
| BP特有 | coda-l母音化 (l→w), t/d口蓋化 (ti→tʃi, di→dʒi), 末尾母音還元 (e→i, o→u) |
| PUA | `tʃ`→U+E054, `dʒ`→U+E055 |
| Prosody | A1=0, A2=2(stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **G2P から受信し除去** (出力には含まない) |

---

## PostProcessIds — 全非JA言語で共通

Python `base.py` の検証により、**全非JA言語が同一アルゴリズム**を使用。

```
[BOS, PAD, id0, PAD, id1, PAD, ..., idN, PAD, EOS]
 ^    _    id0  _    id1  _         idN  _    $
```

**C# 実装**: `PiperPhonemeConverter.EspeakPostProcessIds()` 共通ヘルパー。`MultilingualPhonemizer` は動的 EOS (日本語疑問マーカー ?/?\!/?./?~) に対応。

---

## PUA トークンマッピング

C# `OpenJTalkToPiperMapping.cs`: 87エントリ (Python `token_mapper.py` 89エントリのうち87を移植)。

| 言語グループ | 範囲 | エントリ数 |
|-------------|------|-----------|
| JA | U+E000–U+E01C | 29 |
| 共有 (rr, y_vowel) | U+E01D–U+E01E | 2 |
| ZH | U+E020–U+E04A | 43 |
| KO | U+E04B–U+E052 | 8 |
| ES/PT | U+E054–U+E055 | 2 |
| FR | U+E056–U+E058 | 3 |
| **合計** | | **87** |

---

## 実装詳細

### Phase 1: G2P Engine Interfaces — **完了**

```
src/csharp/PiperPlus.Core/Phonemize/
├── IChineseG2PEngine.cs      (ChineseG2PResult record 付き)
├── ISpanishG2PEngine.cs      (List<string> ToPhonemeList)
├── IFrenchG2PEngine.cs       (List<string> ToPhonemeList)
└── IPortugueseG2PEngine.cs   (List<string> ToPhonemeList)
```

**設計判断:**
- 中国語は `ChineseG2PResult` record で Prosody を一括返却 (engine が PUA + prosody を処理)
- ES/FR/PT はフラット `List<string>` (ストレス/prosody は Phonemizer 層で処理)

### Phase 2: Phonemizer Classes — **完了**

```
src/csharp/PiperPlus.Core/Phonemize/
├── ChinesePhonemizer.cs       (薄いラッパー、PUA変換不要)
├── SpanishPhonemizer.cs       (ˈ読取・維持、PUA mapping)
├── FrenchPhonemizer.cs        (最終母音ストレス検出、PUA mapping)
└── PortuguesePhonemizer.cs    (ˈ読取・除去、PUA mapping)
```

### Phase 3: PUA Token Mapping 拡張 — **完了**

- `OpenJTalkToPiperMapping.cs`: 29→87エントリ
- `PiperPhonemeConverter.cs`: `EspeakPostProcessIds()` 共通ヘルパー追加

### Phase 4: CLI 統合 — **完了**

**Program.cs 変更:**
- `ResolveTextModePhonemizer()` に zh/es/fr/pt の4言語を直接インスタンス化で追加
- 複合言語コード (`ja-en-zh-es-fr-pt`) で `MultilingualPhonemizer` を自動生成
- `--language` 説明を `"ja, en, zh, es, fr, pt, or combined (e.g. ja-en-zh-es-fr-pt)"` に更新

**G2P ラッパー (PiperPlus.Cli に新規作成):**

| ラッパー | dot-net-g2p クラス | インターフェース |
|---------|-------------------|----------------|
| `DotNetChineseG2PEngine` | `ChineseG2PEngine` | `IChineseG2PEngine` |
| `DotNetSpanishG2PEngine` | `SpanishG2PEngine` | `ISpanishG2PEngine` |
| `DotNetFrenchG2PEngine` | `FrenchG2PEngine` | `IFrenchG2PEngine` |
| `DotNetPortugueseG2PEngine` | `PortugueseG2PEngine` | `IPortugueseG2PEngine` |

**設計判断:**
- 新4言語は直接インスタンス化 (リフレクション不要)。既存 JA/EN はリフレクション維持
- ラッパーは `PiperPlus.Cli` に配置 (NuGet 参照がある場所)。`PiperPlus.Core` は依存なし

### Phase 5: MultilingualPhonemizer — **完了**

```
src/csharp/PiperPlus.Core/Phonemize/
├── UnicodeLanguageDetector.cs    (Unicode範囲で言語判別)
└── MultilingualPhonemizer.cs     (多言語ルーター)
```

**UnicodeLanguageDetector:**
- Kana (U+3040-30FF) → ja
- CJK (U+4E00-9FFF) → ja (仮名存在時) / zh (仮名なし)
- Hangul (U+AC00-D7AF) → ko
- Latin (A-Za-zÀ-ÿ) → defaultLatinLanguage (en/es/fr/pt)
- 全角Latin (U+FF21-FF5A) → Latin扱い (JA扱いしない)
- 中性文字 (空白/数字/句読点) → null (前セグメントに吸収)

**MultilingualPhonemizer:**
- テキストをセグメント分割し各言語 Phonemizer に委譲
- BOS/EOS をセグメント単位で除去 (^, $, ?, U+E016, U+E017, U+E018)
- `_lastEos` で日本語疑問マーカーを動的 EOS として追跡
- NOT thread-safe (`_lastEos` 可変状態のため)

### Phase 6: テスト — **完了**

| テストファイル | テスト数 | Phase |
|-------------|---------|-------|
| `ChinesePhonemizerTests.cs` | 9 | 2 |
| `SpanishPhonemizerTests.cs` | 10 | 2 |
| `FrenchPhonemizerTests.cs` | 11 | 2 |
| `PortuguesePhonemizerTests.cs` | 10 | 2 |
| `UnicodeLanguageDetectorTests.cs` | 15 | 5 |
| `MultilingualPhonemizerTests.cs` | 8 | 5 |
| `CliIntegrationTests.cs` (追加分) | 6 | 4+5 |
| **合計追加** | **69** | |

全594テストパス (既存525 + 新規69)。

### Phase 7: NuGet 依存関係 — **完了**

`PiperPlus.Cli.csproj` に追加済み:
```xml
<PackageReference Include="DotNetG2P.Chinese" Version="1.7.0" />
<PackageReference Include="DotNetG2P.Spanish" Version="1.7.0" />
<PackageReference Include="DotNetG2P.French" Version="1.7.0" />
<PackageReference Include="DotNetG2P.Portuguese" Version="1.7.0" />
```

`PiperPlus.Core.csproj` には追加なし (リフレクションで解決する既存パターンを維持)。

---

## ファイル変更サマリー

### 新規作成 (20ファイル)

| ファイル | 内容 | Phase |
|---------|------|-------|
| `PiperPlus.Core/Phonemize/IChineseG2PEngine.cs` | 中国語G2Pインターフェース + ChineseG2PResult | 1 |
| `PiperPlus.Core/Phonemize/ISpanishG2PEngine.cs` | スペイン語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/IFrenchG2PEngine.cs` | フランス語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/IPortugueseG2PEngine.cs` | ポルトガル語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/ChinesePhonemizer.cs` | 中国語Phonemizer | 2 |
| `PiperPlus.Core/Phonemize/SpanishPhonemizer.cs` | スペイン語Phonemizer | 2 |
| `PiperPlus.Core/Phonemize/FrenchPhonemizer.cs` | フランス語Phonemizer | 2 |
| `PiperPlus.Core/Phonemize/PortuguesePhonemizer.cs` | ポルトガル語Phonemizer | 2 |
| `PiperPlus.Cli/DotNetChineseG2PEngine.cs` | 中国語G2Pラッパー | 4 |
| `PiperPlus.Cli/DotNetSpanishG2PEngine.cs` | スペイン語G2Pラッパー | 4 |
| `PiperPlus.Cli/DotNetFrenchG2PEngine.cs` | フランス語G2Pラッパー | 4 |
| `PiperPlus.Cli/DotNetPortugueseG2PEngine.cs` | ポルトガル語G2Pラッパー | 4 |
| `PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` | 多言語ルーター | 5 |
| `PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` | 言語判別 | 5 |
| `PiperPlus.Core.Tests/ChinesePhonemizerTests.cs` | 中国語テスト (9件) | 6 |
| `PiperPlus.Core.Tests/SpanishPhonemizerTests.cs` | スペイン語テスト (10件) | 6 |
| `PiperPlus.Core.Tests/FrenchPhonemizerTests.cs` | フランス語テスト (11件) | 6 |
| `PiperPlus.Core.Tests/PortuguesePhonemizerTests.cs` | ポルトガル語テスト (10件) | 6 |
| `PiperPlus.Core.Tests/UnicodeLanguageDetectorTests.cs` | 言語判別テスト (15件) | 6 |
| `PiperPlus.Core.Tests/MultilingualPhonemizerTests.cs` | 多言語テスト (8件) | 6 |

### 変更 (6ファイル)

| ファイル | 変更内容 | Phase |
|---------|---------|-------|
| `PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` | PUA 29→87エントリ | 3 |
| `PiperPlus.Core/Phonemize/PiperPhonemeConverter.cs` | `EspeakPostProcessIds()` 追加 | 3 |
| `PiperPlus.Core.Tests/PhonemeConverterTests.cs` | エントリ数 29→87 | 3 |
| `PiperPlus.Cli/Program.cs` | 6言語 + 複合コード + MultilingualPhonemizer | 4+5 |
| `PiperPlus.Cli/PiperPlus.Cli.csproj` | DotNetG2P.* v1.7.0 × 4 | 7 |
| `PiperPlus.Core.Tests/CliIntegrationTests.cs` | zh/es/fr/pt + multilingual テスト | 4+5 |

### 変更不要ファイル

- `PhonemeEncoder.cs` — 言語に依存しない汎用エンコーダ
- `PiperModel.cs` / `PiperSession.cs` — ONNX推論レイヤー
- `PiperConfig.cs` — config.json の phoneme_id_map で対応
- `SessionFactory.cs` — 推論セッション管理

---

## CLI 使用例

### 単一言語モード
```bash
# 中国語
piper-plus --model model.onnx --text "你好世界" --language zh

# スペイン語
piper-plus --model model.onnx --text "Hola mundo" --language es

# フランス語
piper-plus --model model.onnx --text "Bonjour le monde" --language fr

# ポルトガル語
piper-plus --model model.onnx --text "Olá mundo" --language pt
```

### 多言語モード (コード切替)
```bash
# 日本語+英語+中国語
piper-plus --model model.onnx --text "こんにちはhello你好" --language ja-en-zh

# 全6言語
piper-plus --model model.onnx --text "テスト" --language ja-en-zh-es-fr-pt
```

### テストモード (推論なし)
```bash
piper-plus --test-mode --text "你好" --language zh
# → [test-mode] phoneme_ids(N): [...]
```
