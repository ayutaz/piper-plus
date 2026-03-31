# NST Swedish Pronunciation Dictionary -- Integration Design

## 1. Dictionary Structure Analysis

### 1.1 File Format (OpenSLR Improved Version)

The OpenSLR version (by Emelie Kullmann) is a **simplified 2-column TSV** format, not the original 51-field semicolon-delimited NST format. The original full-format NST lexicon from Sprakbanken (Norwegian National Library) contained 51 fields with metadata including POS tags, morphological decomposition, frequency, and source quality indicators. Kullmann's improved version strips this to just word + pronunciation, which is what OpenSLR hosts.

| Property | Value |
|----------|-------|
| File | `lexicon.txt` from `lexicon-sv.tgz` (5.3 MB compressed) |
| Format | TSV (tab-delimited), 2 columns: `WORD\tPRONUNCIATION` |
| Encoding | UTF-8 |
| Total entries | 822,740 |
| Unique words | 820,572 |
| Words with multiple pronunciations | 2,105 |
| All words | UPPERCASE |
| Raw file size | ~30 MB |
| Transcription system | NST SAMPA (space-delimited phonemes with stress prefixes) |
| Special entries | `!SIL` (silence), `<UNK>` (unknown), 44 hyphen-prefix fragments |

### 1.2 Pronunciation Notation

Pronunciations use a space-delimited SAMPA variant with stress markers attached as prefixes:

```
"  = primary stress (on the following phoneme)
%  = secondary stress (on the following phoneme)
```

**Example entries:**
```
BARN    "b A: n`           → /bɑːɳ/   (retroflex n)
SJUKHUS "S }: k %h }: s    → /ɧʉːk ˌhʉːs/  (compound: sj-sound + secondary stress)
STATION s t a "S u: n      → /staˈɧuːn/  (-tion -> sj-sound)
GARAGE  g a "r A: s`       → /gaˈrɑːʂ/   (French loanword, retroflex final)
```

### 1.3 Phoneme Inventory (43 base symbols)

#### Vowels -- Long (9)

| SAMPA | IPA | Unicode | Description | Example |
|-------|-----|---------|-------------|---------|
| `A:` | ɑː | U+0251 U+02D0 | open back unrounded | GATA "g A: t a |
| `e:` | eː | U+0065 U+02D0 | close-mid front | HELA "h e: l a |
| `E:` | ɛː | U+025B U+02D0 | open-mid front | ÄTA "E: t a |
| `i:` | iː | U+0069 U+02D0 | close front | FIN "f i: n |
| `o:` | oː | U+006F U+02D0 | close-mid back rounded | SON "s o: n |
| `u:` | uː | U+0075 U+02D0 | close back rounded | SOL "s u: l |
| `}:` | ʉː | U+0289 U+02D0 | close central rounded | HUS "h }: s |
| `y:` | yː | U+0079 U+02D0 | close front rounded | SYN "s y: n |
| `2:` | øː | U+00F8 U+02D0 | close-mid front rounded | ÖL "2: l |

#### Vowels -- Short (9)

| SAMPA | IPA | Unicode | Description | Example |
|-------|-----|---------|-------------|---------|
| `a` | a | U+0061 | open front | KATT "k a t |
| `e` | e | U+0065 | close-mid front (unstressed) | GATA "g A: t a |
| `E` | ɛ | U+025B | open-mid front | FEST "f E s t |
| `I` | ɪ | U+026A | near-close front | FLICKA "f l I k a |
| `O` | ɔ | U+0254 | open-mid back | OM "O m |
| `U` | ʊ | U+028A | near-close back | OST "U s t |
| `u0` | ʉ | U+0289 | close central rounded (short) | BUSS "b u0 s |
| `Y` | ʏ | U+028F | near-close front rounded | FYLLA "f Y l a |
| `9` | œ | U+0153 | open-mid front rounded | MÖRK "m 9 r k |

**Key insight -- the "o" problem is fully resolved:**
- `u:` = /uː/ (SOL, BOK, STOL) -- letter "o" before single consonant, some words
- `o:` = /oː/ (SON, BROR) -- letter "o" in other contexts
- `O` = /ɔ/ (OM, ROST, POST) -- letter "o" before double consonant / cluster
- `U` = /ʊ/ (OST) -- letter "o" in specific words
- The dictionary resolves all four per-word, eliminating the hardest rule-based challenge.

#### Consonants (15 basic)

| SAMPA | IPA | Example |
|-------|-----|---------|
| `b d f g h j k l m n p r s t v` | (same) | standard |
| `N` | ŋ (U+014B) | KUNG "k u0 N |

#### Special Consonants (2)

| SAMPA | IPA | Unicode | Description | Example |
|-------|-----|---------|-------------|---------|
| `S` | ɧ | U+0267 | sj-sound (voiceless dorso-palatal/velar fricative) | SJUK "S }: k |
| `s'` | ɕ | U+0255 | tj-sound (voiceless alveolopalatal fricative) | KIND "s' I n d |

#### Retroflex Consonants (5)

| SAMPA | IPA | Unicode | Description | Example |
|-------|-----|---------|-------------|---------|
| `n\`` | ɳ | U+0273 | retroflex nasal | BARN "b A: n\` |
| `t\`` | ʈ | U+0288 | retroflex stop | KORT "k O t\` |
| `d\`` | ɖ | U+0256 | retroflex stop | BORD "b u: d\` |
| `l\`` | ɭ | U+026D | retroflex lateral | KARL "k A: l\` |
| `s\`` | ʂ | U+0282 | retroflex fricative | FORS "f O s\` |

#### Diphthongs (2, rare)

| SAMPA | IPA | Frequency | Example |
|-------|-----|-----------|---------|
| `a*U` | aʊ | 3,092 entries | AUD "a*U d |
| `E*U` | ɛʊ | 533 entries | EUGEN E*U "S e: n |

### 1.4 Stress Patterns

| Pattern | Count | Percentage |
|---------|-------|------------|
| Primary + secondary stress | 583,438 | 70.9% |
| Primary stress only | 239,273 | 29.1% |
| Secondary stress only | 17 | <0.01% |
| No stress | 12 | <0.01% |

The high percentage of words with both primary and secondary stress (70.9%) reflects the dominance of compound words in Swedish.

### 1.5 Tonal Accent

**CRITICAL FINDING: Tonal accent information (accent 1 vs accent 2) is NOT present in this dictionary.**

The original NST full-format lexicon encoded tonal accent in one of its 51 fields. The OpenSLR simplified version has lost this distinction entirely. All known minimal pairs (ANDEN, TOMTEN, BUREN, STEGEN, etc.) have only a single entry with no accent distinction.

**Impact:** For TTS purposes, this is acceptable because:
1. Tonal accent has low functional load in Swedish (~300 minimal pairs)
2. Context disambiguates in nearly all cases
3. Most TTS systems (including espeak-ng) do not model Swedish tonal accent
4. The accent can potentially be recovered via morphological rules (compound words default to accent 2, simple words to accent 1) as a post-processing step

### 1.6 Compound Words

**583,455 entries (70.9%)** have secondary stress, indicating compound structure. Swedish is highly productive with compounds, and the NST dictionary captures this extensively.

| Metric | Compound words | Simple words |
|--------|---------------|--------------|
| Count | 583,455 | 239,285 |
| Average word length | 12.9 chars | 9.1 chars |

The dictionary does NOT include explicit compound decomposition (that was in the original 51-field format). However, the presence of secondary stress markers implicitly indicates compound boundaries.

### 1.7 Multiple Pronunciations

2,105 words have multiple pronunciation variants. Examples:

| Word | Pronunciations | Note |
|------|---------------|------|
| SON | "s u: n, "s o: n | /uːn/ (son) vs /oːn/ (son, dialectal) |
| ACCENT | a k "s E n t, a k "s a N | Swedish vs French pronunciation |
| KARL | "k A: l\`, "k A: r | Retroflex vs non-retroflex |
| DU | "d y:, "d }: | Dialectal variation |
| KORT | "k O t\`, "k U t\` | Vowel quality variation |

**Design decision:** Use the first pronunciation variant (most standard/common) by default.

---

## 2. Quality Assessment

### 2.1 Origin and Generation Method

The NST (Nordisk Spraakteknologi) lexicon was originally created for ASR (speech recognition), not TTS. It contains approximately:
- **~250,000 manually verified entries** -- higher quality, core vocabulary
- **~677,000 machine-generated entries** -- generated by rule-based G2P (NOT espeak-ng; NST had its own proprietary Swedish G2P engine)

The OpenSLR version (822K entries) is Emelie Kullmann's "improved" edition, which:
1. Merged manual and machine entries
2. Corrected known errors
3. Simplified the format to word + pronunciation

### 2.2 Quality Indicators

**There is no explicit flag to distinguish manual vs machine entries** in the OpenSLR version. However, quality correlates with word type:

| Word type | Estimated quality | Count | Reasoning |
|-----------|------------------|-------|-----------|
| Short simple words (<=5 chars) | Very high (~99%) | 22,841 | Likely all manually verified |
| Common words (<=8 chars) | High (~97%) | 159,956 | Mix of manual + quality machine |
| Compound words (9-15 chars) | Good (~95%) | 563,331 | Machine G2P + compound rules |
| Long/rare compounds (16+ chars) | Moderate (~90%) | 98,125 | Primarily machine-generated |

**Known quality issues:**
- Some entries have questionable vowel quality for "o" in rare words
- A few loanword pronunciations may not match modern Swedish usage
- Compound word stress placement can be incorrect for novel compounds

### 2.3 Comparison with Other Resources

| Resource | Entries | Quality | License |
|----------|---------|---------|---------|
| **NST/OpenSLR** | **820,572** | **Good (95%+)** | **CC0** |
| Folkets lexikon | 21,000 | Very high (manually curated) | CC-BY-SA 2.5 |
| espeak-ng rules | N/A (rule-based) | Moderate (70%) | GPL-3.0 |
| Epitran rules | N/A (rule-based) | Poor (31%) | MIT |

The NST dictionary is the clear choice: it has 39x more entries than Folkets lexikon, CC0 license (no restrictions), and good quality.

### 2.4 Spot-Check Validation

Tested against known correct pronunciations from Wikipedia IPA references:

| Word | NST SAMPA | Converted IPA | Correct IPA | Match? |
|------|-----------|---------------|-------------|--------|
| BARN | "b A: n\` | ˈbɑːɳ | bɑːɳ | YES |
| SKED | "S e: d | ˈɧeːd | ɧeːd | YES |
| SKOLA | "s k u: l a | ˈskuːla | skuːla | YES |
| KIND | "s' I n d | ˈɕɪnd | ɕɪnd | YES |
| SJUK | "S }: k | ˈɧʉːk | ɧʉːk | YES |
| FLICKA | "f l I k a | ˈflɪka | flɪka | YES |
| STATION | s t a "S u: n | staˈɧuːn | staˈɧuːn | YES |
| CHEF | "S e: f | ˈɧeːf | ɧeːf | YES |
| BORD | "b u: d\` | ˈbuːɖ | buːɖ | YES |
| FORS | "f O s\` | ˈfɔʂ | fɔʂ | YES |

**10/10 spot checks pass.** The NST dictionary correctly handles all the categories where both Epitran and espeak-ng fail: soft/hard splits, retroflex assimilation, "o" disambiguation, sj-sound in loanwords, and compound stress.

---

## 3. SAMPA-to-IPA Conversion

### 3.1 Complete Conversion Table

```python
NST_SAMPA_TO_IPA = {
    # === Long vowels ===
    "A:": "ɑː",    # ɑ U+0251 + ː U+02D0
    "e:": "eː",
    "E:": "ɛː",    # ɛ U+025B
    "i:": "iː",
    "o:": "oː",
    "u:": "uː",
    "}:": "ʉː",    # ʉ U+0289
    "y:": "yː",
    "2:": "øː",    # ø U+00F8

    # === Short vowels ===
    "a":  "a",
    "e":  "e",
    "E":  "ɛ",
    "I":  "ɪ",     # ɪ U+026A
    "O":  "ɔ",     # ɔ U+0254
    "U":  "ʊ",     # ʊ U+028A
    "u0": "ʉ",     # ʉ U+0289 (short)
    "Y":  "ʏ",     # ʏ U+028F
    "9":  "œ",     # œ U+0153

    # === Basic consonants ===
    "b": "b", "d": "d", "f": "f", "g": "ɡ",  # ɡ U+0261
    "h": "h", "j": "j", "k": "k", "l": "l",
    "m": "m", "n": "n", "p": "p", "r": "r",
    "s": "s", "t": "t", "v": "v",
    "N": "ŋ",     # ŋ U+014B

    # === Special consonants ===
    "S":  "ɧ",    # ɧ U+0267 (sj-sound)
    "s'": "ɕ",    # ɕ U+0255 (tj-sound)

    # === Retroflex consonants ===
    "n`": "ɳ",    # ɳ U+0273
    "t`": "ʈ",    # ʈ U+0288
    "d`": "ɖ",    # ɖ U+0256
    "l`": "ɭ",    # ɭ U+026D
    "s`": "ʂ",    # ʂ U+0282

    # === Diphthongs ===
    "a*U": "aʊ",
    "E*U": "ɛʊ",

    # === Stress markers (prefix) ===
    # '"' before a phoneme -> ˈ (primary stress, IPA U+02C8)
    # '%' before a phoneme -> ˌ (secondary stress, IPA U+02CC)
}
```

### 3.2 Conversion Algorithm

```python
def convert_nst_to_ipa(nst_pronunciation: str) -> str:
    """Convert NST SAMPA pronunciation to IPA.

    Input:  '"b A: n`'  (space-delimited NST SAMPA)
    Output: 'ˈbɑːɳ'    (IPA string)
    """
    ipa_parts = []
    for token in nst_pronunciation.split():
        # Strip stress prefix
        stress = ""
        if token.startswith('"'):
            stress = "ˈ"
            token = token[1:]
        elif token.startswith('%"'):
            stress = "ˌˈ"  # rare: secondary + primary
            token = token[2:]
        elif token.startswith('%'):
            stress = "ˌ"
            token = token[1:]

        # Look up base phoneme
        ipa = NST_SAMPA_TO_IPA.get(token, token)
        ipa_parts.append(stress + ipa)

    return "".join(ipa_parts)
```

### 3.3 New IPA Symbols Required for piper-plus

These IPA symbols are NOT in the current piper-plus phoneme inventory and need PUA registration:

| IPA | Unicode | Description | PUA Candidate |
|-----|---------|-------------|---------------|
| ɧ | U+0267 | sj-sound | -- single codepoint, no PUA needed |
| ɳ | U+0273 | retroflex nasal | -- single codepoint, no PUA needed |
| ʈ | U+0288 | retroflex stop | -- single codepoint, no PUA needed |
| ɭ | U+026D | retroflex lateral | -- single codepoint, no PUA needed |
| ø | U+00F8 | front rounded vowel | -- single codepoint, no PUA needed |
| ʉ | U+0289 | central rounded vowel | -- single codepoint, no PUA needed |
| ɵ | U+0275 | mid central rounded | -- single codepoint, no PUA needed |

Multi-character tokens requiring PUA mapping:

| Token | IPA | PUA |
|-------|-----|-----|
| ɑː | ɑ + ː | needs PUA (2 chars) |
| ɛː | ɛ + ː | needs PUA (2 chars) |
| eː | e + ː | needs PUA (2 chars) |
| iː | i + ː | needs PUA (2 chars) |
| oː | o + ː | needs PUA (2 chars) |
| uː | u + ː | needs PUA (2 chars) |
| ʉː | ʉ + ː | needs PUA (2 chars) |
| yː | y + ː | needs PUA (2 chars) |
| øː | ø + ː | needs PUA (2 chars) |
| aʊ | a + ʊ | needs PUA (2 chars) |
| ɛʊ | ɛ + ʊ | needs PUA (2 chars) |

Total new PUA slots needed: ~11 (for multi-character tokens).

Note: ɕ (U+0255) and ʂ (U+0282) are already in the Chinese phonemizer inventory. ɖ (U+0256) is already in the piper-plus character set (used in retroflex contexts). ŋ (U+014B) is shared with Chinese and Korean.

---

## 4. Storage Format Design

### 4.1 Recommended Strategy: Tiered Dictionary

Given that 70.9% of entries are compound words (often predictable from their parts), and Zipf's law guarantees high-frequency coverage from a small core, we recommend a **tiered approach**:

| Tier | Content | Size (gzip) | Coverage |
|------|---------|-------------|----------|
| **Core** | All simple words (~238K, no compounds) | ~2.3 MB | ~95% of running text |
| **Extended** | + Common compounds (words <= 12 chars) | ~5.3 MB | ~98% |
| **Full** | All 821K words | ~10.6 MB | ~99.5% |

**Recommendation:** Ship the **Core tier (~238K simple words)** as the default, with rule-based fallback for compound decomposition and OOV words. The extended and full tiers can be optional downloads.

### 4.2 Platform-Specific Formats

#### Python: Gzipped JSON (dict lookup)

```python
# Storage: sv_lexicon.json.gz (~2.3 MB for core tier)
# Format: {"word": "ipa_pronunciation", ...}
# Load at startup, O(1) lookup via dict

import gzip, json

with gzip.open("sv_lexicon.json.gz", "rt", encoding="utf-8") as f:
    _LEXICON = json.load(f)

def lookup(word: str) -> str | None:
    return _LEXICON.get(word.upper())
```

**Size estimate:** Core tier ~2.3 MB gzipped, ~7.8 MB in-memory as Python dict.

#### Rust: Binary FST (fst crate) or Sorted Vec with binary search

```rust
// Option A: fst crate (prefix-compressed, ~40% smaller than raw)
// Build: fst::MapBuilder -> write to .fst file
// Lookup: fst::Map::new(mmap) -> map.get(word)
// Size: Core tier ~1.5 MB (FST is very compact for sorted string data)

// Option B: Sorted Vec + binary search (simpler, no extra crate)
// Load: deserialize sorted (word, pronunciation) pairs
// Lookup: binary_search_by_key on word
// Size: Core tier ~3 MB (bincode serialized)
```

**Recommendation:** Use `include_bytes!` with a compact binary format (sorted array + LZ4/zstd compression). The `fst` crate adds a dependency but gives optimal size.

#### C#: Gzipped binary dictionary or embedded resource

```csharp
// Storage: sv_lexicon.bin.gz as embedded resource
// Format: length-prefixed strings, sorted for binary search
// Load: decompress at startup into Dictionary<string, string>
// Size: Core tier ~2.3 MB embedded, ~8 MB in memory
```

#### WASM/JavaScript: Gzipped JSON in IndexedDB

```javascript
// Download: sv_lexicon.json.gz from CDN (~2.3 MB)
// Cache: IndexedDB (like DictManager pattern for OpenJTalk)
// Load: decompress + JSON.parse into Map
// Size: Core tier ~2.3 MB download, ~8 MB in memory
```

#### C++: Memory-mapped sorted array

```cpp
// Storage: sv_lexicon.bin (sorted word+pronunciation pairs)
// Lookup: binary search on memory-mapped file
// Size: Core tier ~3 MB on disk
```

### 4.3 Dictionary File Format (Cross-Platform Binary)

For maximum portability, define a single binary format that all platforms read:

```
Header (16 bytes):
  magic: "SVLX" (4 bytes)
  version: uint16 (2 bytes, currently 1)
  entry_count: uint32 (4 bytes)
  flags: uint16 (2 bytes: bit 0 = has_stress, bit 1 = has_tonal_accent)
  reserved: 4 bytes

Entry (variable length, packed sequentially):
  word_length: uint8 (1 byte, max 255 chars)
  word: UTF-8 bytes (word_length bytes, lowercase)
  pron_length: uint8 (1 byte)
  pronunciation: UTF-8 IPA string (pron_length bytes)

Index (for binary search, appended after entries):
  offsets: uint32[] (entry_count offsets into entry data)
```

This format is simple to parse in any language, compact (~3 MB for core tier), and supports efficient binary search via the offset index.

---

## 5. Lookup Flow Design

### 5.1 Architecture

```
Input: "Jag gillar att läsa böcker på biblioteket."
  |
  v
[1. Text normalization]
  - Lowercase
  - Unicode NFC normalization
  - Strip leading/trailing punctuation per word
  - Expand common abbreviations (t.ex. -> till exempel)
  |
  v
[2. Sentence splitting + word tokenization]
  - Split on whitespace + punctuation boundaries
  - Preserve punctuation tokens for prosody
  |
  v
[3. For each word token:]
  |
  +--[3a. Dictionary lookup (exact match)]
  |    - Normalize to uppercase for NST lookup
  |    - If found -> return IPA pronunciation
  |    |
  +--[3b. Compound decomposition (if not found)]
  |    - Try splitting at common compound boundaries
  |    - Swedish compound rules: look for known words
  |      from right to left (longest match)
  |    - Apply linking morpheme rules (-s-, -e-, -o-)
  |    - If both parts found -> combine pronunciations
  |      with secondary stress on second part
  |    |
  +--[3c. Rule-based G2P fallback]
       - Apply Swedish orthographic rules:
         * Soft/hard consonant splits (k/g/sk + front vowel)
         * Retroflex assimilation (r + t/d/n/l/s)
         * Vowel length (complementary quantity)
         * sj-sound patterns (sj, skj, stj, -tion, -sion)
       - This handles novel words, names, neologisms
  |
  v
[4. Stress assignment]
  - Dictionary entries already have stress
  - Rule-based: default penultimate stress
  - Compounds: primary on first part, secondary on second
  |
  v
[5. Post-processing]
  - Map multi-char IPA to PUA tokens
  - Add BOS/EOS padding
  - Generate prosody features (a1=0, a2=stress, a3=word_length)
```

### 5.2 Word Normalization

```python
def normalize_word(word: str) -> str:
    """Normalize word for dictionary lookup."""
    # 1. Strip leading/trailing punctuation
    word = word.strip(".,;:!?\"'()-")
    # 2. Uppercase (NST dictionary is all-caps)
    word = word.upper()
    # 3. Unicode NFC
    word = unicodedata.normalize("NFC", word)
    return word
```

### 5.3 Compound Word Decomposition

Swedish compounds are written without spaces. The dictionary handles most compounds directly, but for OOV compounds:

```python
def decompose_compound(word: str, lexicon: dict) -> list[str] | None:
    """Try to split a compound word into known parts.

    Strategy: try splits from right to left, preferring longer
    right-hand components (the semantic head in Swedish).
    """
    # Try all split points
    for i in range(len(word) - 2, 2, -1):
        left = word[:i]
        right = word[i:]

        # Check with common linking morphemes
        for link in ["", "S", "E", "O"]:
            if link and left.endswith(link):
                left_base = left[:-len(link)]
            else:
                left_base = left
                if link:
                    continue

            if left_base in lexicon and right in lexicon:
                return [left_base, right]

    return None  # Cannot decompose
```

### 5.4 Multiple Pronunciation Selection

For the 2,105 words with multiple variants, **always use the first entry** (the most common/standard pronunciation in the NST ordering). Users can override via custom dictionary if needed.

---

## 6. Coverage Estimates

### 6.1 Running Text Coverage by Dictionary Size

Based on Zipf's law for Swedish text (estimated from Swedish language statistics):

| Dictionary size | Estimated coverage | Note |
|-----------------|-------------------|------|
| Core tier (~238K simple) | ~95% of tokens | Most function words, common content words |
| + Rule-based fallback | ~99% effective | Rules handle regular OOV compounds |
| Extended (~505K, words <=12) | ~98% of tokens | Covers common compounds |
| Full (~821K) | ~99.5% of tokens | Includes rare names, technical terms |
| + Rule-based fallback | ~99.9%+ effective | Near-complete coverage |

### 6.2 Recommended Configuration

| Platform | Default tier | Download size | Memory |
|----------|-------------|---------------|--------|
| Python (training) | Full | 10.6 MB gz | ~40 MB dict |
| Rust CLI | Core | 2.3 MB embedded | ~8 MB |
| C# CLI | Core | 2.3 MB embedded | ~8 MB |
| WASM/Browser | Core | 2.3 MB download | ~8 MB |
| C++ embedded | Core | 2.3 MB embedded | ~8 MB |

The Core tier is optimal for shipping in binaries. The Full tier is appropriate for Python training pipelines where accuracy is paramount and binary size is irrelevant.

---

## 7. Comparison: Dictionary vs DeepPhonemizer

The research document (swedish-g2p-research.md) recommended DeepPhonemizer (Method B) as the primary approach. After this dictionary analysis, here is an updated comparison:

| Criterion | Dictionary + Rules (A) | DeepPhonemizer (B) |
|-----------|----------------------|---------------------|
| Accuracy on NST words | ~99%+ (direct lookup) | ~95-98% (learned) |
| OOV word handling | Rule-based (~88%) | Neural (~95%) |
| Compound handling | Decomposition + lookup | End-to-end |
| "o" disambiguation | 100% (in dictionary) | ~95-98% |
| Binary size | 2.3 MB (core) | 5-20 MB (ONNX) |
| Startup time | ~100ms (load dict) | ~200ms (load ONNX) |
| Cross-platform | Simple (JSON/binary) | ONNX Runtime required |
| Debuggability | High (inspect dict) | Low (black box) |
| Implementation effort | Medium | Medium-High |

**Updated recommendation:** **Method A (Dictionary + Rules)** is now preferred for the initial implementation, because:

1. The NST dictionary directly resolves the hardest problems ("o" disambiguation, retroflex, loanwords)
2. Dictionary lookup is simpler to implement across 5 platforms than ONNX G2P
3. The Core tier (2.3 MB) is smaller than a DeepPhonemizer ONNX model
4. Rule-based fallback handles OOV words (compounds, names) adequately
5. DeepPhonemizer can be added later as an optional OOV enhancer if needed

---

## 8. Implementation Plan

### Phase 1: Dictionary Conversion Tool
1. Script to download NST lexicon from OpenSLR
2. SAMPA-to-IPA conversion (using the table in Section 3)
3. Export to cross-platform binary format (Section 4.3)
4. Export Core tier (simple words only) and Full tier
5. Quality validation against known IPA references

### Phase 2: Python Phonemizer
1. `swedish.py` -- `SwedishPhonemizer` class
2. `sv_id_map.py` -- Swedish phoneme inventory
3. Dictionary loader (gzipped JSON for Python)
4. Rule-based G2P fallback (soft/hard, retroflex, vowel length, sj-sound)
5. Register in `registry.py` and `multilingual_id_map.py`
6. Tests

### Phase 3: Rust Integration
1. Binary dictionary loader in `piper-core`
2. `swedish.rs` phonemizer with dictionary lookup + rule fallback
3. Embed Core tier dictionary in binary

### Phase 4: C# Integration
1. Dictionary loader in `PiperPlus.Core`
2. `SwedishPhonemizer.cs` with dictionary lookup + rule fallback
3. Embed Core tier dictionary as resource

### Phase 5: WASM/npm Integration
1. Dictionary download via `DictManager` pattern
2. Swedish phonemizer in JavaScript
3. IndexedDB caching

---

## Appendix A: NST Dictionary Statistics

```
Total entries:           822,740
Unique words:            820,572
Multiple pronunciations:   2,105
Unique base phonemes:         43
Avg word length:            11.8 chars
Avg pronunciation length:   10.9 phones

Word length distribution:
  1-3 chars:     2,167 (0.3%)
  4-5 chars:    21,249 (2.6%)
  6-8 chars:   137,868 (16.8%)
  9-12 chars:  345,210 (42.0%)
  13-16 chars: 218,121 (26.5%)
  17+ chars:    98,125 (11.9%)

Compound vs simple:
  Compound (with secondary stress): 583,455 (70.9%)
  Simple (primary stress only):     239,285 (29.1%)

Non-Swedish characters: À Á Æ Ç È É Ê Ë Í Î Ï Ñ Ó Ø Û Ü Ÿ
  (found in loanwords and proper names)
```
