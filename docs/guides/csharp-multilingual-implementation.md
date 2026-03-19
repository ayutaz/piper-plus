# C# CLI 6言語マルチリンガル対応 — 実装ガイド

## 概要

C# CLI (`PiperPlus.Cli`) に中国語 (zh)、スペイン語 (es)、フランス語 (fr)、ポルトガル語 (pt) の4言語を追加し、Python/Rust と同等の6言語マルチリンガル対応を実現する。

**現状:** JA + EN の2言語のみ対応
**目標:** JA + EN + ZH + ES + FR + PT の6言語対応

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
// → IPA tokens with tone markers

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

### 既存実装パターン

| 実装 | G2P Engine Interface | PostProcessIds | GetPhonemeIdMap |
|------|---------------------|----------------|-----------------|
| `JapanesePhonemizer` | `IJapaneseG2PEngine` | デフォルト (no-op) | `null` (config.json) |
| `EnglishPhonemizer` | `IEnglishG2PEngine` | BOS/EOS/PAD挿入 | `null` (config.json) |

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
| PostProcessIds | BOS + pad-between + EOS (末尾padなし) |

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
| PostProcessIds | BOS + pad-between + EOS (末尾padなし) |

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
| PostProcessIds | BOS + pad + id + pad + ... + pad + EOS (末尾padあり) |

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
| PostProcessIds | BOS + pad + id + pad + ... + pad + EOS (末尾padあり) |

**ポルトガル語固有フォネーム (12個):**
`ã`, `ẽ`, `ĩ`, `õ`, `ũ`, `tʃ`, `dʒ`, `ʎ`, `ʁ`, `—`, `–`, `…`

---

## PostProcessIds パターンの差異

| 言語 | パターン | 図式 |
|------|---------|------|
| JA | no-op (BOS/EOSはフォネームトークンとして処理) | `^ ... $ or ?` |
| EN | BOS + inter-pad + EOS | `^ _ id0 _ id1 _ ... _ idN _ $` |
| ZH, ES | BOS + inter-pad + EOS (末尾padなし) | `^ id0 _ id1 _ ... _ idN $` |
| FR, PT | BOS + pad + inter-pad + EOS (末尾padあり) | `^ _ id0 _ id1 _ ... _ idN _ $` |

**重要:** FR/PT は EN と同じレイアウト。ZH/ES は末尾の pad がない点が異なる。

---

## PUA トークンマッピング全体像

Python の `token_mapper.py` に定義された固定 PUA マッピング (89エントリ) のうち、C# 側で新規に必要なもの:

### 中国語用 (U+E020–U+E04A, 43エントリ)
子音: `pʰ`, `tʰ`, `kʰ`, `tɕ`, `tɕʰ`, `tʂ`, `tʂʰ`, `tsʰ`
母音: `aɪ`, `eɪ`, `aʊ`, `oʊ`, `an`, `ən`, `aŋ`, `əŋ`, `uŋ`
複合母音: `ia`, `iɛ`, `iou`, `iaʊ`, `iɛn`, `in`, `iaŋ`, `iŋ`, `iuŋ`, `ua`, `uo`, `uaɪ`, `ueɪ`, `uan`, `uən`, `uaŋ`, `uəŋ`, `yɛ`, `yɛn`, `yn`, `ɻ̩`
声調: `tone1`–`tone5`

### スペイン語/ポルトガル語用
`tʃ` → U+E054, `dʒ` → U+E055, `rr` → U+E01D

### フランス語用
`ɛ̃` → U+E056, `ɑ̃` → U+E057, `ɔ̃` → U+E058

### 共有 (既に JA/EN に存在する可能性あり)
`y_vowel` → U+E01E, `ts` → U+E00F

---

## 実装チェックリスト

### Phase 1: G2P Engine Interfaces

新規作成するインターフェース:

```
src/csharp/PiperPlus.Core/Phonemize/
├── IChineseG2PEngine.cs      ← NEW
├── ISpanishG2PEngine.cs      ← NEW
├── IFrenchG2PEngine.cs       ← NEW
└── IPortugueseG2PEngine.cs   ← NEW
```

各インターフェースは dot-net-g2p の対応エンジンをラップする最小限のメソッドを定義。

#### IChineseG2PEngine
```csharp
public interface IChineseG2PEngine
{
    /// <summary>piper-plus互換IPA + ProsodyInfo を返す</summary>
    ChineseG2PResult Convert(string text);
}

public record ChineseG2PResult(
    IReadOnlyList<string> Phonemes,  // PUA-mapped tokens
    IReadOnlyList<int> A1,           // tone (1-5)
    IReadOnlyList<int> A2,           // syllable position
    IReadOnlyList<int> A3            // word length
);
```

#### ISpanishG2PEngine / IFrenchG2PEngine / IPortugueseG2PEngine
```csharp
public interface ISpanishG2PEngine
{
    /// <summary>IPA phoneme list を返す</summary>
    List<string> ToPhonemeList(string text);
}
// French, Portuguese も同様の最小インターフェース
```

### Phase 2: Phonemizer Classes

新規作成する Phonemizer:

```
src/csharp/PiperPlus.Core/Phonemize/
├── ChinesePhonemizer.cs       ← NEW
├── SpanishPhonemizer.cs       ← NEW
├── FrenchPhonemizer.cs        ← NEW
└── PortuguesePhonemizer.cs    ← NEW
```

各クラスは `IPhonemizer` を実装:

| クラス | GetPhonemeIdMap | PostProcessIds |
|-------|----------------|----------------|
| `ChinesePhonemizer` | `null` (config.json) | override: BOS + inter-pad + EOS (末尾padなし) |
| `SpanishPhonemizer` | `null` (config.json) | override: BOS + inter-pad + EOS (末尾padなし) |
| `FrenchPhonemizer` | `null` (config.json) | override: BOS + pad + inter-pad + EOS (末尾padあり) |
| `PortuguesePhonemizer` | `null` (config.json) | override: BOS + pad + inter-pad + EOS (末尾padあり) |

**中国語の特殊処理:**
- dot-net-g2p `ToPuaPhonemes()` が PUA マッピング済みトークンを返すため、C# 側での PUA 変換は不要
- `ToIpaWithProsody()` で Prosody 情報も取得可能
- 全角句読点→半角変換はエンジン側で処理

**ES/FR/PT の共通処理:**
- dot-net-g2p `ToIPA()` が IPA 文字列を返す
- C# 側でストレスマーカー挿入 + Prosody 生成が必要
- multi-char トークン (`tʃ`, `dʒ`, `rr`, `ɛ̃` 等) → PUA マッピングが必要

### Phase 3: PUA Token Mapping 拡張

`OpenJTalkToPiperMapping.cs` を拡張して新言語の PUA エントリを追加。

現在 29 エントリ (JA のみ) → 中国語43 + ES/PT/FR共通数エントリ追加で約80エントリに拡大。

**注意:** `OpenJTalkToPiperMapping` という名前は JA 固有なので、リネームまたは新クラス `MultilingualPuaMapping` の作成を検討。

### Phase 4: CLI 統合

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

### Phase 5: MultilingualPhonemizer (オプション)

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

### Phase 6: テスト

```
src/csharp/PiperPlus.Core.Tests/
├── ChinesePhonemizerTests.cs      ← NEW
├── SpanishPhonemizerTests.cs      ← NEW
├── FrenchPhonemizerTests.cs       ← NEW
├── PortuguesePhonemizerTests.cs   ← NEW
└── MultilingualPhonemizerTests.cs ← NEW (Phase 5)
```

テストパターン (既存 JA/EN テストに準拠):
- xUnit v3 (`[Fact]`, `[Theory]` + `[InlineData]`)
- Hand-written stubs (モッキングフレームワークなし)
- `Assert.Equal` でシーケンス比較
- `tokens.Count == prosody.Count` 不変条件チェック
- PostProcessIds の BOS/EOS/PAD レイアウト検証
- PUA マッピング検証

### Phase 7: NuGet 依存関係

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

### 新規作成ファイル (14ファイル)

| ファイル | 内容 |
|---------|------|
| `PiperPlus.Core/Phonemize/IChineseG2PEngine.cs` | 中国語G2Pインターフェース |
| `PiperPlus.Core/Phonemize/ISpanishG2PEngine.cs` | スペイン語G2Pインターフェース |
| `PiperPlus.Core/Phonemize/IFrenchG2PEngine.cs` | フランス語G2Pインターフェース |
| `PiperPlus.Core/Phonemize/IPortugueseG2PEngine.cs` | ポルトガル語G2Pインターフェース |
| `PiperPlus.Core/Phonemize/ChinesePhonemizer.cs` | 中国語Phonemizer |
| `PiperPlus.Core/Phonemize/SpanishPhonemizer.cs` | スペイン語Phonemizer |
| `PiperPlus.Core/Phonemize/FrenchPhonemizer.cs` | フランス語Phonemizer |
| `PiperPlus.Core/Phonemize/PortuguesePhonemizer.cs` | ポルトガル語Phonemizer |
| `PiperPlus.Core.Tests/ChinesePhonemizerTests.cs` | 中国語テスト |
| `PiperPlus.Core.Tests/SpanishPhonemizerTests.cs` | スペイン語テスト |
| `PiperPlus.Core.Tests/FrenchPhonemizerTests.cs` | フランス語テスト |
| `PiperPlus.Core.Tests/PortuguesePhonemizerTests.cs` | ポルトガル語テスト |
| `PiperPlus.Core/Phonemize/MultilingualPhonemizer.cs` | 多言語ルーター (Phase 5) |
| `PiperPlus.Core/Phonemize/UnicodeLanguageDetector.cs` | 言語判別 (Phase 5) |

### 変更ファイル (4ファイル)

| ファイル | 変更内容 |
|---------|---------|
| `PiperPlus.Core/Mapping/OpenJTalkToPiperMapping.cs` | PUA エントリ追加 (ZH/ES/FR/PT) |
| `PiperPlus.Cli/Program.cs` | `ResolveTextModePhonemizer()` に4言語追加 + `--language` Description 更新 |
| `PiperPlus.Cli/PiperPlus.Cli.csproj` | NuGet PackageReference 追加 |
| `.github/workflows/ci.yml` | C# テストに新言語テスト追加 (必要に応じて) |

### 変更不要ファイル

以下は言語非依存のため変更不要:
- `PhonemeEncoder.cs` — 言語に依存しない汎用エンコーダ
- `PiperModel.cs` / `PiperSession.cs` — ONNX推論レイヤー
- `PiperConfig.cs` — config.json の phoneme_id_map で対応
- `SessionFactory.cs` — 推論セッション管理

---

## dot-net-g2p 出力 → piper-plus フォネーム 変換戦略

### 中国語: 最小変換

dot-net-g2p の `ToPuaPhonemes()` / `ToIpaWithProsody()` が piper-plus 互換出力を直接提供するため、C# Phonemizer は薄いラッパーで済む。

```
dot-net-g2p.ToPuaPhonemes() → PUA-mapped tokens (直接利用可能)
dot-net-g2p.ToIpaWithProsody() → IPA + A1/A2/A3 (直接利用可能)
```

### ES/FR/PT: IPA → PUA 変換必要

dot-net-g2p は IPA 文字列を返すが、multi-char IPA トークン (`tʃ`, `dʒ`, `rr`, `ɛ̃` 等) を PUA single-codepoint に変換する処理が C# 側で必要。

```
dot-net-g2p.ToIPA() → IPA string
  → tokenize (multi-char IPA 分割)
  → PUA mapping (OpenJTalkToPiperMapping 拡張)
  → stress marker insertion (ˈ before stressed vowel)
  → prosody generation (A1=0, A2=stress, A3=count)
```

---

## 実装優先順

| 優先度 | Phase | 内容 | 見積り |
|--------|-------|------|--------|
| 1 | Phase 1 | G2P Engine Interfaces (4ファイル) | 小 |
| 2 | Phase 2 | Phonemizer Classes (4ファイル) | 中〜大 |
| 3 | Phase 3 | PUA Mapping 拡張 | 小 |
| 4 | Phase 4 | CLI 統合 | 小 |
| 5 | Phase 6 | テスト (4ファイル) | 中 |
| 6 | Phase 7 | NuGet 依存関係 | 小 |
| 7 | Phase 5 | Multilingual Phonemizer (オプション) | 大 |

Phase 1–4, 6–7 で単一言語モード (`--language zh` 等) が動作。Phase 5 は言語自動検出が必要な場合のみ。
