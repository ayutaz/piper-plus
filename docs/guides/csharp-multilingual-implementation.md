# C# CLI 6言語マルチリンガル対応 — 実装ガイド

## 概要

C# CLI (`PiperPlus.Cli`) に中国語 (zh)、スペイン語 (es)、フランス語 (fr)、ポルトガル語 (pt) の4言語を追加し、Python/Rust と同等の6言語マルチリンガル対応を実現する。

**現状:** JA + EN の2言語のみ対応 (CLI統合未完了)
**目標:** JA + EN + ZH + ES + FR + PT の6言語対応

### 進捗状況

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 1 | G2P Engine Interfaces (4ファイル) | **完了** |
| Phase 2 | Phonemizer Classes (4ファイル) | **完了** |
| Phase 3 | PUA Mapping 拡張 (29→87エントリ) | **完了** |
| Phase 4 | CLI 統合 (`Program.cs` + `--language`) | 未着手 |
| Phase 5 | MultilingualPhonemizer (オプション) | 未着手 |
| Phase 6 | テスト (4ファイル, 40テストケース) | **完了** |
| Phase 7 | NuGet 依存関係 | 未着手 |

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
// → ChineseProsodyResult { Phonemes, ProsodyInfos }
// ProsodyInfo: A1=tone(1-5), A2=syllable_pos(1-based), A3=word_length
```

#### スペイン語 (`SpanishG2PEngine`)
```csharp
var engine = new SpanishG2PEngine();
string ipa = engine.ToIPA("Hola, ¿cómo estás?");
var phonemes = engine.ToPhonemeList("Hola");
var syllables = engine.ToSyllables("información");
```

#### フランス語 (`FrenchG2PEngine`)
```csharp
var engine = new FrenchG2PEngine();
string ipa = engine.ToIPA("Bonjour, comment allez-vous?");
var phonemes = engine.ToPhonemeList("bonjour");
```

#### ポルトガル語 (`PortugueseG2PEngine`)
```csharp
var engine = new PortugueseG2PEngine();
// Brazilian Portuguese (default)
string ipa = engine.ToIPA("Olá, como você está?");
var phonemes = engine.ToPhonemeList("Brasil");
```

---

## 現行 C# アーキテクチャ

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

| 実装 | G2P Engine Interface | PostProcessIds | GetPhonemeIdMap | 状態 |
|------|---------------------|----------------|-----------------|------|
| `JapanesePhonemizer` | `IJapaneseG2PEngine` | デフォルト (no-op) | `null` (config.json) | 既存 |
| `EnglishPhonemizer` | `IEnglishG2PEngine` | BOS/EOS/PAD挿入 | `null` (config.json) | 既存 |
| `ChinesePhonemizer` | `IChineseG2PEngine` | BOS/EOS/PAD挿入 (EN同一) | `null` (config.json) | **実装済** |
| `SpanishPhonemizer` | `ISpanishG2PEngine` | BOS/EOS/PAD挿入 (EN同一) | `null` (config.json) | **実装済** |
| `FrenchPhonemizer` | `IFrenchG2PEngine` | BOS/EOS/PAD挿入 (EN同一) | `null` (config.json) | **実装済** |
| `PortuguesePhonemizer` | `IPortugueseG2PEngine` | BOS/EOS/PAD挿入 (EN同一) | `null` (config.json) | **実装済** |

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

**主要 PUA マッピング (中国語固有):**

| トークン | PUA | 説明 |
|---------|-----|------|
| `pʰ` | U+E020 | 有気両唇音 (pinyin p) |
| `tʰ` | U+E021 | 有気歯茎音 (pinyin t) |
| `kʰ` | U+E022 | 有気軟口蓋音 (pinyin k) |
| `tɕ` | U+E023 | 歯茎硬口蓋破擦音 (pinyin j) |
| `tɕʰ` | U+E024 | 有気歯茎硬口蓋破擦音 (pinyin q) |
| `tʂ` | U+E025 | そり舌破擦音 (pinyin zh) |
| `tʂʰ` | U+E026 | 有気そり舌破擦音 (pinyin ch) |
| `tsʰ` | U+E027 | 有気歯茎破擦音 (pinyin c) |
| `aɪ` | U+E028 | 二重母音 (pinyin ai) |
| `eɪ` | U+E029 | 二重母音 (pinyin ei) |
| `aʊ` | U+E02A | 二重母音 (pinyin ao) |
| `oʊ` | U+E02B | 二重母音 (pinyin ou) |
| `tone1`–`tone5` | U+E046–U+E04A | 声調マーカー |

### スペイン語 (es)

| 項目 | 値 |
|------|-----|
| 方式 | 完全ルールベース (外部依存なし) |
| 方言 | ラテンアメリカ (seseo, yeísmo) |
| dot-net-g2p API | `ToIPA()`, `ToPhonemeList()`, `ToSyllables()` |
| ストレス | 音節構造から計算 (アクセント記号 > V/n/s末尾→次末 > その他→末尾) |
| 異音交替 | b/v (b↔β), d (d↔ð), g (ɡ↔ɣ) — 語頭/鼻音後=閉鎖音, その他=摩擦音 |
| 機能語 | 27語でストレス抑制 (el, la, de, que 等) |
| PUA | `rr`→U+E01D, `tʃ`→U+E054 |
| Prosody | A1=0, A2=2(stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **出力に含む** (Python と同一) |

**スペイン語固有フォネーム (9個):**
`ɲ`, `ɾ`, `rr`, `β`, `ɣ`, `x`, `ʝ`, `¡`, `¿`

### フランス語 (fr)

| 項目 | 値 |
|------|-----|
| 方式 | ルールベース (最長一致左→右スキャン) |
| dot-net-g2p API | `ToIPA()`, `ToPhonemeList()` |
| 鼻母音 | ɛ̃ (in/ain/ein), ɑ̃ (an/en), ɔ̃ (on) — un/um→ɛ̃ (現代フランス語の合流) |
| リエゾン | 未実装 (語単位処理の制約) |
| エリジオン | アポストロフィで語境界分割 |
| 特殊ルール | -er動詞語尾→/e/, -ille→/ij/ (ville/mille除外), -tion→/sjɔ̃/ |
| y_vowel | `y` (close front rounded /y/) — 日本語の /j/ との衝突回避 |
| PUA | ɛ̃→U+E056, ɑ̃→U+E057, ɔ̃→U+E058, y_vowel→U+E01E |
| Prosody | A1=0, A2=2(last vowel=stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **出力に含まない** (Phonemizer が最終母音を検出して A2 設定) |

**フランス語固有フォネーム (16個):**
`ɛ̃`, `ɑ̃`, `ɔ̃`, `ø`, `œ`, `y_vowel`, `ɔ`, `ə`, `ɥ`, `ɲ`, `ʁ`, `—`, `–`, `…`, `«`, `»`

### ポルトガル語 (pt)

| 項目 | 値 |
|------|-----|
| 方式 | ルールベース (Brazilian Portuguese) |
| dot-net-g2p API | `ToIPA()`, `ToPhonemeList()`, dialect: `PortugueseDialect.Brazilian` |
| 鼻母音 | ã, ẽ, ĩ, õ, ũ (NFC合成済みコードポイント) |
| BP特有 | coda-l母音化 (l→w), t/d口蓋化 (ti→tʃi, di→dʒi), 非強勢末尾母音還元 (e→i, o→u) |
| ストレス | アクセント記号 > paroxytone (a/e/o/am/em/en末尾) > oxytone |
| PUA | `tʃ`→U+E054, `dʒ`→U+E055, `ʁ`→共有 |
| Prosody | A1=0, A2=2(stressed)/0, A3=word_phoneme_count |
| ˈ マーカー | **G2P から受信し除去** (Python と同様、出力には含まない) |

**ポルトガル語固有フォネーム (12個):**
`ã`, `ẽ`, `ĩ`, `õ`, `ũ`, `tʃ`, `dʒ`, `ʎ`, `ʁ`, `—`, `–`, `…`

---

## PostProcessIds — 全非JA言語で共通

Python `base.py` の `post_process_ids()` を検証した結果、**全非JA言語が同一アルゴリズム**を使用することが判明。

### アルゴリズム (Python base.py)

```python
# 1. 各 phoneme_id の後に PAD を挿入 (既に PAD の場合はスキップ)
for phoneme_id in phoneme_ids:
    padded.append(phoneme_id)
    if phoneme_id not in pad_ids:
        padded.extend(pad_ids)

# 2. BOS + PAD を先頭に追加
phoneme_ids = bos_ids + [pad_ids[0]] + padded

# 3. EOS を末尾に追加
phoneme_ids = phoneme_ids + eos_ids
```

### 結果パターン (全非JA言語で共通)

```
[BOS, PAD, id0, PAD, id1, PAD, ..., idN, PAD, EOS]
 ^    _    id0  _    id1  _         idN  _    $
```

| 言語 | PostProcessIds |
|------|---------------|
| JA | no-op (BOS/EOSはフォネームトークンとして処理) |
| EN, ZH, ES, FR, PT | BOS + PAD + inter-pad + EOS (全て同一) |

**C# 実装**: `PiperPhonemeConverter.EspeakPostProcessIds()` として共通ヘルパーメソッドを追加。各 Phonemizer の `PostProcessIds()` からこのヘルパーを呼び出す。

> **注意:** 当初の調査では ZH/ES が「末尾 pad なし」、FR/PT が「末尾 pad あり」と記述していたが、Python ソースコードの検証により全言語同一であることを確認済み。

---

## PUA トークンマッピング全体像

Python の `token_mapper.py` に定義された固定 PUA マッピング (89エントリ) を C# `OpenJTalkToPiperMapping.cs` に移植済み (87エントリ、KO含む)。

### C# マッピングテーブル: 29→87エントリ

| 言語グループ | 範囲 | エントリ数 |
|-------------|------|-----------|
| JA (既存) | U+E000–U+E01C | 29 |
| 共有 (rr, y_vowel) | U+E01D–U+E01E | 2 |
| ZH | U+E020–U+E04A | 43 |
| KO | U+E04B–U+E052 | 8 |
| ES/PT | U+E054–U+E055 | 2 |
| FR | U+E056–U+E058 | 3 |
| **合計** | | **87** |

### 中国語用 (U+E020–U+E04A, 43エントリ)
子音: `pʰ`, `tʰ`, `kʰ`, `tɕ`, `tɕʰ`, `tʂ`, `tʂʰ`, `tsʰ`
母音: `aɪ`, `eɪ`, `aʊ`, `oʊ`, `an`, `ən`, `aŋ`, `əŋ`, `uŋ`
複合母音: `ia`, `iɛ`, `iou`, `iaʊ`, `iɛn`, `in`, `iaŋ`, `iŋ`, `iuŋ`, `ua`, `uo`, `uaɪ`, `ueɪ`, `uan`, `uən`, `uaŋ`, `uəŋ`, `yɛ`, `yɛn`, `yn`, `ɻ̩`
声調: `tone1`–`tone5`

### スペイン語/ポルトガル語用
`tʃ` → U+E054, `dʒ` → U+E055, `rr` → U+E01D

### フランス語用
`ɛ̃` → U+E056, `ɑ̃` → U+E057, `ɔ̃` → U+E058

### 共有
`y_vowel` → U+E01E, `ts` → U+E00F (JA既存)

---

## 実装チェックリスト

### Phase 1: G2P Engine Interfaces — **完了**

```
src/csharp/PiperPlus.Core/Phonemize/
├── IChineseG2PEngine.cs      ← 実装済
├── ISpanishG2PEngine.cs      ← 実装済
├── IFrenchG2PEngine.cs       ← 実装済
└── IPortugueseG2PEngine.cs   ← 実装済
```

#### IChineseG2PEngine
```csharp
public record ChineseG2PResult(
    IReadOnlyList<string> Phonemes,  // PUA-mapped tokens
    IReadOnlyList<int> A1,           // tone (1-5)
    IReadOnlyList<int> A2,           // syllable position
    IReadOnlyList<int> A3            // word length
);

public interface IChineseG2PEngine
{
    ChineseG2PResult Convert(string text);
}
```

#### ISpanishG2PEngine / IFrenchG2PEngine / IPortugueseG2PEngine
```csharp
public interface ISpanishG2PEngine
{
    List<string> ToPhonemeList(string text);
}
// French, Portuguese も同様の最小インターフェース
```

**設計判断:**
- 中国語は `ChineseG2PResult` record で Prosody を一括返却 (engine が PUA + prosody を一括処理)
- ES/FR/PT はフラット `List<string>` で IPA トークンを返す (ストレス/prosody は Phonemizer 層で処理)

### Phase 2: Phonemizer Classes — **完了**

```
src/csharp/PiperPlus.Core/Phonemize/
├── ChinesePhonemizer.cs       ← 実装済
├── SpanishPhonemizer.cs       ← 実装済
├── FrenchPhonemizer.cs        ← 実装済
└── PortuguesePhonemizer.cs    ← 実装済
```

| クラス | GetPhonemeIdMap | PostProcessIds | ストレス処理 |
|-------|----------------|----------------|-------------|
| `ChinesePhonemizer` | `null` | EspeakPostProcessIds (EN同一) | Engine が prosody を返す |
| `SpanishPhonemizer` | `null` | EspeakPostProcessIds (EN同一) | ˈ マーカーを読取、出力に維持 |
| `FrenchPhonemizer` | `null` | EspeakPostProcessIds (EN同一) | 最終母音を検出、ˈ なし |
| `PortuguesePhonemizer` | `null` | EspeakPostProcessIds (EN同一) | ˈ マーカーを読取後除去 |

**各言語の Phonemizer 実装詳細:**

#### ChinesePhonemizer (薄いラッパー)
- `IChineseG2PEngine.Convert()` が PUA マッピング済み + prosody を返す
- Phonemizer は結果をそのまま `(tokens, prosody)` に変換
- PUA 変換不要、ストレス検出不要

#### SpanishPhonemizer
- G2P engine が返すフラットリストに ˈ マーカーとスペース区切りを含む
- Phonemizer がワード分割 → ˈ 読取 → prosody 生成 → PUA mapping
- ˈ と直後の母音に A2=2、他は A2=0
- A3 = ˈ を除くワード内フォネーム数
- 母音: a, e, i, o, u

#### FrenchPhonemizer
- G2P engine が返すフラットリストに ˈ を含まない
- Phonemizer がワード分割 → 最終母音検出 → prosody 生成 → PUA mapping
- 最終母音に A2=2、他は A2=0
- 母音: a, e, ɛ, i, o, ɔ, u, y_vowel, ə, ø, œ, ɛ̃, ɑ̃, ɔ̃

#### PortuguesePhonemizer
- G2P engine が返すフラットリストに ˈ マーカーを含む
- Phonemizer がワード分割 → ˈ 読取 → ˈ 除去 → prosody 生成 → PUA mapping
- ˈ 直後のフォネームに A2=2、他は A2=0
- A3 = ˈ を除くワード内フォネーム数

### Phase 3: PUA Token Mapping 拡張 — **完了**

`OpenJTalkToPiperMapping.cs` を拡張: 29→87エントリ。

Python `token_mapper.py` の FIXED_PUA_MAPPING 全89エントリのうち87を C# に移植 (KO 8エントリ含む)。

**追加:** `PiperPhonemeConverter.EspeakPostProcessIds()` 共通ヘルパーメソッド。

### Phase 4: CLI 統合 — **未着手**

`Program.cs` の `ResolveTextModePhonemizer()` に4言語を追加:

```csharp
case "zh":
    // DotNetG2P.Chinese.ChineseG2PEngine via reflection
    return new ChinesePhonemizer(engine);
case "es":
    // DotNetG2P.Spanish.SpanishG2PEngine via reflection
    return new SpanishPhonemizer(engine);
case "fr":
    // DotNetG2P.French.FrenchG2PEngine via reflection
    return new FrenchPhonemizer(engine);
case "pt":
    // DotNetG2P.Portuguese.PortugueseG2PEngine via reflection
    return new PortuguesePhonemizer(engine);
```

`--language` オプションの Description を更新: `"ja, en, zh, es, fr, or pt"`

### Phase 5: MultilingualPhonemizer (オプション) — **未着手**

Python/Rust と同等の多言語自動ルーティング:

```
src/csharp/PiperPlus.Core/Phonemize/
├── MultilingualPhonemizer.cs      ← NEW
└── UnicodeLanguageDetector.cs     ← NEW
```

- Unicode 範囲で言語を自動判別
- テキストをセグメント分割して各言語 Phonemizer に委譲
- BOS/EOS はセグメント単位で strip → 全体で1つだけ付与
- `_last_eos` で日本語疑問文の EOS トークンを保持

### Phase 6: テスト — **完了**

```
src/csharp/PiperPlus.Core.Tests/
├── ChinesePhonemizerTests.cs      ← 実装済 (9テスト)
├── SpanishPhonemizerTests.cs      ← 実装済 (10テスト)
├── FrenchPhonemizerTests.cs       ← 実装済 (11テスト)
├── PortuguesePhonemizerTests.cs   ← 実装済 (10テスト)
└── MultilingualPhonemizerTests.cs ← Phase 5 で作成予定
```

テストパターン (既存 JA/EN テストに準拠):
- xUnit v3 (`[Fact]`)
- Hand-written stubs (モッキングフレームワークなし)
- `Assert.Equal` でシーケンス比較
- `tokens.Count == prosody.Count` 不変条件チェック
- PostProcessIds の BOS/EOS/PAD レイアウト検証

### Phase 7: NuGet 依存関係 — **未着手**

`PiperPlus.Core.csproj` には G2P パッケージを追加**しない** (現行パターンに従い reflection で解決)。

`PiperPlus.Cli.csproj` に追加:
```xml
<PackageReference Include="DotNetG2P.Chinese" Version="1.7.0" />
<PackageReference Include="DotNetG2P.Spanish" Version="1.7.0" />
<PackageReference Include="DotNetG2P.French" Version="1.7.0" />
<PackageReference Include="DotNetG2P.Portuguese" Version="1.7.0" />
```

---

## Python ↔ C# フォネーム対応表

### Python phoneme_id_map の173シンボルの構成

```
IDs 0–9:    特殊トークン (_, ^, $, ?, ?!, ?., ?~, #, [, ])
IDs 10–103: 日本語フォネーム (~94個)
IDs 104–123: 英語固有フォネーム (~20個, 共有除く)
IDs 124–153: 中国語固有フォネーム (~30個)
IDs 154–163: スペイン語固有フォネーム (~10個)
IDs 164–168: ポルトガル語固有フォネーム (~5個, 共有除く)
IDs 169–173: フランス語固有フォネーム (~5個, 共有除く)
```

**重複排除:** 各言語の ID マップは「その言語で新しく追加されるフォネームのみ」を定義。共通フォネーム (b, d, f, k, l, m, n, p, s, t, v, w, z 等) は最初に登録した言語の ID を共有。

---

## ファイル変更サマリー

### 実装済ファイル

#### 新規作成 (12ファイル)

| ファイル | 内容 | Phase |
|---------|------|-------|
| `PiperPlus.Core/Phonemize/IChineseG2PEngine.cs` | 中国語G2Pインターフェース + ChineseG2PResult | 1 |
| `PiperPlus.Core/Phonemize/ISpanishG2PEngine.cs` | スペイン語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/IFrenchG2PEngine.cs` | フランス語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/IPortugueseG2PEngine.cs` | ポルトガル語G2Pインターフェース | 1 |
| `PiperPlus.Core/Phonemize/ChinesePhonemizer.cs` | 中国語Phonemizer (薄いラッパー) | 2 |
| `PiperPlus.Core/Phonemize/SpanishPhonemizer.cs` | スペイン語Phonemizer (ˈ維持) | 2 |
| `PiperPlus.Core/Phonemize/FrenchPhonemizer.cs` | フランス語Phonemizer (最終母音ストレス) | 2 |
| `PiperPlus.Core/Phonemize/PortuguesePhonemizer.cs` | ポルトガル語Phonemizer (ˈ除去) | 2 |
| `PiperPlus.Core.Tests/ChinesePhonemizerTests.cs` | 中国語テスト (9件) | 6 |
| `PiperPlus.Core.Tests/SpanishPhonemizerTests.cs` | スペイン語テスト (10件) | 6 |
| `PiperPlus.Core.Tests/FrenchPhonemizerTests.cs` | フランス語テスト (11件) | 6 |
| `PiperPlus.Core.Tests/PortuguesePhonemizerTests.cs` | ポルトガル語テスト (10件) | 6 |

#### 変更済 (3ファイル)

| ファイル | 変更内容 | Phase |
|---------|---------|-------|
| `PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` | PUA 29→87エントリ (ZH/KO/ES/PT/FR) | 3 |
| `PiperPlus.Core/Phonemize/PiperPhonemeConverter.cs` | `EspeakPostProcessIds()` 共通ヘルパー追加 | 3 |
| `PiperPlus.Core.Tests/PhonemeConverterTests.cs` | エントリ数チェック 29→87 に更新 | 3 |

### 未着手ファイル

| ファイル | 変更内容 | Phase |
|---------|---------|-------|
| `PiperPlus.Cli/Program.cs` | `ResolveTextModePhonemizer()` に4言語追加 + `--language` Description 更新 | 4 |
| `PiperPlus.Cli/PiperPlus.Cli.csproj` | NuGet PackageReference 追加 | 7 |
| `PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` | 多言語ルーター (オプション) | 5 |
| `PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` | 言語判別 (オプション) | 5 |

### 変更不要ファイル

以下は言語非依存のため変更不要:
- `PhonemeEncoder.cs` — 言語に依存しない汎用エンコーダ
- `PiperModel.cs` / `PiperSession.cs` — ONNX推論レイヤー
- `PiperConfig.cs` — config.json の phoneme_id_map で対応
- `SessionFactory.cs` — 推論セッション管理

---

## dot-net-g2p 出力 → piper-plus フォネーム 変換戦略

### 中国語: 最小変換 (実装済)

dot-net-g2p の `ToPuaPhonemes()` / `ToIpaWithProsody()` が piper-plus 互換出力を直接提供するため、C# Phonemizer は薄いラッパーで済む。

```
IChineseG2PEngine.Convert(text) → ChineseG2PResult
  → Phonemes: PUA-mapped tokens (直接利用可能)
  → A1/A2/A3: prosody 値 (直接利用可能)
```

### ES/FR/PT: IPA → PUA 変換 (実装済)

dot-net-g2p は IPA フラットリストを返し、Phonemizer が以下を処理:

```
I*G2PEngine.ToPhonemeList(text) → flat IPA tokens
  → word split (スペース / 句読点で分割)
  → stress handling (言語別: ES=ˈ維持, FR=最終母音検出, PT=ˈ除去)
  → prosody generation (A1=0, A2=stress, A3=count)
  → PUA mapping (PiperPhonemeConverter.MapSequence)
```

---

## 実装優先順

| 優先度 | Phase | 内容 | 状態 |
|--------|-------|------|------|
| 1 | Phase 1 | G2P Engine Interfaces (4ファイル) | **完了** |
| 2 | Phase 2 | Phonemizer Classes (4ファイル) | **完了** |
| 3 | Phase 3 | PUA Mapping 拡張 (29→87) | **完了** |
| 4 | Phase 6 | テスト (4ファイル, 40ケース) | **完了** |
| 5 | Phase 4 | CLI 統合 | 未着手 |
| 6 | Phase 7 | NuGet 依存関係 | 未着手 |
| 7 | Phase 5 | Multilingual Phonemizer (オプション) | 未着手 |

Phase 4 + 7 で単一言語モード (`--language zh` 等) が動作。Phase 5 は言語自動検出が必要な場合のみ。
