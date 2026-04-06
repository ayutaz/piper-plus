# Phoneme Input Feature

## Overview

The phoneme input feature allows users to directly specify phonemes using the `[[ phonemes ]]` notation within their text input. This provides fine-grained control over pronunciation, which is especially useful for:

- Proper names with specific pronunciations
- Technical terms or acronyms
- Non-standard pronunciations
- Mixed language content

## Usage

### Basic Syntax

Wrap phonemes in double square brackets:

```bash
echo "Hello [[ h ə l oʊ ]] world" | piper --model en_US-lessac-medium.onnx -f output.wav
```

### Examples

> **Note:** piper-plus は eSpeak-ng に依存しません。以下の eSpeak 音素形式はレガシー互換のための参考情報です。piper-plus の G2P パイプライン (`piper-plus-g2p`) は独自の IPA ベース音素を使用します。

#### English (eSpeak phonemes)
```bash
# Custom pronunciation for a name
echo "My name is [[ dʒ ɒ n ]] (John)" | piper --model en_US-lessac-medium.onnx -f john.wav

# Technical acronym
echo "The [[ aɪ diː iː ]] (IDE) is ready" | piper --model en_US-lessac-medium.onnx -f ide.wav
```

#### Japanese (OpenJTalk phonemes)
```bash
# Hiragana with custom reading
echo "今日は [[ ky o o w a ]] いい天気です" | piper --model multilingual-test-medium.onnx -f weather.wav

# Foreign name in katakana context
echo "私は [[ m a i k u r u ]] です" | piper --model multilingual-test-medium.onnx -f michael.wav
```

### Phoneme Systems

> **Note:** piper-plus は eSpeak-ng に依存しません。以下の eSpeak 音素形式はレガシー互換のための参考情報です。piper-plus の G2P パイプライン (`piper-plus-g2p`) は独自の IPA ベース音素を使用します。

#### eSpeak-ng (Most Languages)
- Uses IPA (International Phonetic Alphabet) symbols
- Space-separated phonemes
- Common symbols: `ə` (schwa), `ɪ` (near-close front unrounded), `ʊ` (near-close back rounded)
- Reference: [eSpeak-ng Phoneme Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/phonemes.md)

#### OpenJTalk (Japanese)
- Uses romanized Japanese phonemes
- Space-separated
- Multi-character phonemes supported: `ky`, `sh`, `ch`, `ts`, etc.
- Special phonemes:
  - `N` - moraic nasal (ん)
  - `q` - glottal stop (っ)
  - `sp` - short pause
  - `pau` - pause

#### Chinese (pypinyin-based IPA)
```bash
# Mandarin with tone markers
echo "今天 [[ tɕ in tone1 tʰ iaŋ tone1 ]] 很好" | piper --model multilingual-test-medium.onnx -f today.wav

# Pinyin "拼音"
echo "[[ pʰ in tone1 i in tone1 ]]" | piper --model multilingual-test-medium.onnx -f pinyin.wav
```

#### Spanish (rule-based IPA)
```bash
# Standard greeting
echo "[[ ˈ o l a ]]" | piper --model multilingual-test-medium.onnx -f hola.wav

# Mixed text and phoneme override
echo "Buenos [[ d i a s ]]" | piper --model multilingual-test-medium.onnx -f buenos_dias.wav
```

#### Portuguese (Brazilian IPA)
```bash
# "obrigado" with nasal vowel
echo "[[ o b ɾ i ɡ a d u ]]" | piper --model multilingual-test-medium.onnx -f obrigado.wav

# Nasal vowel example: "bom"
echo "[[ b õ ]]" | piper --model multilingual-test-medium.onnx -f bom.wav
```

#### French (rule-based IPA)
```bash
# "bonjour"
echo "[[ b ɔ̃ ʒ u ʁ ]]" | piper --model multilingual-test-medium.onnx -f bonjour.wav

# Nasal vowel example: "vin blanc"
echo "[[ v ɛ̃ b l ɑ̃ ]]" | piper --model multilingual-test-medium.onnx -f vin_blanc.wav
```

### Phoneme System Details

#### pypinyin IPA (Chinese / Mandarin)
- Uses pypinyin for character-to-pinyin conversion, then maps to IPA
- Space-separated IPA tokens
- Tone markers appended after each syllable: `tone1` through `tone5`
- Aspirated consonants use IPA superscript h: `pʰ`, `tʰ`, `kʰ`, `tɕʰ`, `tʂʰ`, `tsʰ`
- Compound finals are single tokens: `aɪ` (ai), `aʊ` (ao), `iɛn` (ian), `uan` (uan), etc.
- The close front rounded vowel (pinyin u) is represented as `y_vowel` to avoid collision with the Japanese glide `y`
- Tone sandhi is applied automatically by the phonemizer (e.g. T3+T3 -> T2+T3)

**Initials (consonants):**

| Pinyin | IPA     | Description                              |
|--------|---------|------------------------------------------|
| b      | p       | Voiceless bilabial (unaspirated)         |
| p      | pʰ      | Aspirated bilabial                       |
| d      | t       | Voiceless alveolar (unaspirated)         |
| t      | tʰ      | Aspirated alveolar                       |
| g      | k       | Voiceless velar (unaspirated)            |
| k      | kʰ      | Aspirated velar                          |
| j      | tɕ      | Voiceless alveolo-palatal affricate      |
| q      | tɕʰ     | Aspirated alveolo-palatal affricate      |
| x      | ɕ       | Voiceless alveolo-palatal fricative      |
| zh     | tʂ      | Voiceless retroflex affricate            |
| ch     | tʂʰ     | Aspirated retroflex affricate            |
| sh     | ʂ       | Voiceless retroflex fricative            |
| r      | ɻ       | Voiced retroflex approximant             |
| z      | ts      | Voiceless alveolar affricate             |
| c      | tsʰ     | Aspirated alveolar affricate             |
| h      | x       | Voiceless velar fricative                |
| m/n/l/f/s | m/n/l/f/s | Same as IPA                          |

**Finals (vowels and compound finals):**

| Pinyin | IPA     | Description                              |
|--------|---------|------------------------------------------|
| a      | a       | Open central vowel                       |
| o      | o       | Close-mid back rounded                   |
| e      | ɤ       | Close-mid back unrounded                 |
| i      | i       | Close front unrounded                    |
| u      | u       | Close back rounded                       |
| u (after j/q/x) | y_vowel | Close front rounded              |
| ai     | aɪ      | Diphthong                                |
| ei     | eɪ      | Diphthong                                |
| ao     | aʊ      | Diphthong                                |
| ou     | oʊ      | Diphthong                                |
| er     | ɚ       | Rhotacized schwa                         |

**Tone markers:**

| Marker | Tone      | Description     |
|--------|-----------|-----------------|
| tone1  | 阴平 (˥)  | High level      |
| tone2  | 阳平 (˧˥) | Rising          |
| tone3  | 上声 (˨˩˦)| Dipping         |
| tone4  | 去声 (˥˩) | Falling         |
| tone5  | 轻声      | Neutral tone    |

#### Rule-based IPA (Spanish)
- Uses IPA directly with rule-based grapheme-to-phoneme conversion
- Latin American pronunciation by default (seseo: c/z before e/i -> s, yeismo: ll/y -> ʝ)
- Space-separated IPA phonemes
- Stress marker `ˈ` placed before the stressed vowel
- Allophonic variation is captured: b/v -> β (intervocalic), d -> ð (intervocalic), g -> ɣ (intervocalic)

**Consonant phonemes:**

| Phoneme | Description                                | Example          |
|---------|--------------------------------------------|------------------|
| p       | Voiceless bilabial plosive                 | padre            |
| b       | Voiced bilabial plosive (initial/post-nasal)| bien            |
| β       | Bilabial fricative (intervocalic b/v)      | haber, ave       |
| t       | Voiceless alveolar plosive                 | tres             |
| d       | Voiced alveolar plosive (initial/post-nasal)| donde           |
| ð       | Dental fricative (intervocalic d)          | todo             |
| k       | Voiceless velar plosive                    | casa             |
| ɡ       | Voiced velar plosive (initial/post-nasal)  | gato             |
| ɣ       | Velar fricative (intervocalic g)           | agua             |
| tʃ      | Voiceless postalveolar affricate           | chico            |
| f       | Voiceless labiodental fricative            | fuego            |
| s       | Voiceless alveolar fricative               | sol, casa, zona  |
| x       | Voiceless velar fricative                  | jardín, gente    |
| ʝ       | Palatal fricative (y, ll)                  | yo, calle        |
| m       | Bilabial nasal                             | mesa             |
| n       | Alveolar nasal                             | no               |
| ɲ       | Palatal nasal (n)                          | año              |
| l       | Alveolar lateral                           | luz              |
| ɾ       | Alveolar tap (single r)                    | pero, caro       |
| rr      | Alveolar trill (rr, initial r)             | perro, rosa      |
| w       | Labio-velar approximant                    | hueso            |

**Vowel phonemes:**

| Phoneme | Description                                | Example          |
|---------|--------------------------------------------|------------------|
| a       | Open central vowel                         | casa             |
| e       | Close-mid front unrounded                  | mesa             |
| i       | Close front unrounded                      | si               |
| o       | Close-mid back rounded                     | todo             |
| u       | Close back rounded                         | tu               |

#### Rule-based IPA (Brazilian Portuguese)
- Uses IPA with rule-based grapheme-to-phoneme conversion
- Brazilian Portuguese pronunciation (carioca-style)
- T/D palatalization: t before i -> tʃ, d before i -> dʒ, also applies to unstressed final -e
- Nasal vowels: vowel + n/m before consonant or word-end produces a nasal vowel
- Coda-l vocalization: l in syllable coda -> w (e.g. Brasil -> [bɾaziw])
- Unstressed final vowel reduction: -e -> i, -o -> u

**Consonant phonemes:**

| Phoneme | Description                                | Example              |
|---------|--------------------------------------------|----------------------|
| p       | Voiceless bilabial plosive                 | pai                  |
| b       | Voiced bilabial plosive                    | bom                  |
| t       | Voiceless alveolar plosive                 | tudo                 |
| tʃ      | Voiceless postalveolar affricate (ti, te#) | tipo, gente          |
| d       | Voiced alveolar plosive                    | dado                 |
| dʒ      | Voiced postalveolar affricate (di, de#)    | dia, cidade          |
| k       | Voiceless velar plosive                    | casa                 |
| ɡ       | Voiced velar plosive                       | gato                 |
| f       | Voiceless labiodental fricative            | fogo                 |
| v       | Voiced labiodental fricative               | voz                  |
| s       | Voiceless alveolar fricative               | sol, ssc             |
| z       | Voiced alveolar fricative (intervocalic s) | casa, zero           |
| ʃ       | Voiceless postalveolar fricative           | xadrez, chave        |
| ʒ       | Voiced postalveolar fricative              | gente, janela        |
| ʁ       | Uvular fricative (rr, initial/coda r)      | carro, rio, mar      |
| ɾ       | Alveolar tap (intervocalic r)              | caro, para           |
| m       | Bilabial nasal                             | mesa                 |
| n       | Alveolar nasal                             | no                   |
| ɲ       | Palatal nasal (nh)                         | banho                |
| l       | Alveolar lateral (onset only)              | lua                  |
| ʎ       | Palatal lateral (lh)                       | filho                |
| w       | Labio-velar approximant (coda l, ou)       | Brasil, ouro         |

**Vowel phonemes (oral):**

| Phoneme | Description                                | Example              |
|---------|--------------------------------------------|----------------------|
| a       | Open central vowel                         | casa                 |
| e       | Close-mid front unrounded                  | mesa                 |
| ɛ       | Open-mid front unrounded (acute accent)    | cafe                 |
| i       | Close front unrounded                      | vida                 |
| o       | Close-mid back rounded                     | bolo                 |
| ɔ       | Open-mid back rounded (acute accent)       | avó                  |
| u       | Close back rounded                         | tu                   |

**Nasal vowels:**

| Phoneme | Description                                | Example              |
|---------|--------------------------------------------|----------------------|
| ã       | Nasalized a                                | mão, cã              |
| ẽ       | Nasalized e                                | bem, tem             |
| ĩ       | Nasalized i                                | sim, fim             |
| õ       | Nasalized o                                | bom, som             |
| ũ       | Nasalized u                                | um, algum            |

#### Rule-based IPA (French)
- Uses IPA with rule-based grapheme-to-phoneme conversion
- No external G2P engine required
- Nasal vowels: vowel + n/m before consonant or word-end produces a nasal vowel
- The close front rounded vowel [y] (u, u, u) is represented as `y_vowel` (same PUA mapping as Chinese u)
- Silent letters: final consonants (d, g, h, m, n, p, s, t, x, z) are typically silent
- Liaison and elision are handled at the word boundary level

**Consonant phonemes:**

| Phoneme | Description                                | Example              |
|---------|--------------------------------------------|----------------------|
| p       | Voiceless bilabial plosive                 | papa                 |
| b       | Voiced bilabial plosive                    | bon                  |
| t       | Voiceless alveolar plosive                 | tout                 |
| d       | Voiced alveolar plosive                    | dans                 |
| k       | Voiceless velar plosive                    | quand, cas           |
| ɡ       | Voiced velar plosive                       | gare                 |
| f       | Voiceless labiodental fricative            | fin, photo           |
| v       | Voiced labiodental fricative               | vin                  |
| s       | Voiceless alveolar fricative               | sol, ce              |
| z       | Voiced alveolar fricative (intervocalic s) | maison, zero         |
| ʃ       | Voiceless postalveolar fricative (ch)      | chat, chien          |
| ʒ       | Voiced postalveolar fricative (j, ge/gi)   | je, rouge            |
| ʁ       | Uvular fricative (French r)                | rouge, mer           |
| m       | Bilabial nasal                             | moi                  |
| n       | Alveolar nasal                             | non                  |
| ɲ       | Palatal nasal (gn)                         | montagne             |
| l       | Alveolar lateral                           | lune                 |
| j       | Palatal approximant                        | yeux, fille          |
| w       | Labio-velar approximant                    | oui, oiseau          |
| ɥ       | Labio-palatal approximant (u before i)     | nuit, lui            |

**Vowel phonemes (oral):**

| Phoneme  | Description                               | Example              |
|----------|-------------------------------------------|----------------------|
| a        | Open central vowel                        | patte, la            |
| e        | Close-mid front unrounded                 | ete, parler          |
| ɛ        | Open-mid front unrounded                  | pere, lait           |
| i        | Close front unrounded                     | ici, vie             |
| o        | Close-mid back rounded                    | mot, beau            |
| ɔ        | Open-mid back rounded                     | porte, or            |
| u        | Close back rounded                        | ou, pour             |
| y_vowel  | Close front rounded [y]                   | lune, tu, vu         |
| ə        | Schwa (e muet)                            | le, de               |
| ø        | Close-mid front rounded (eu closed)       | peu, jeu             |
| œ        | Open-mid front rounded (eu open)          | peur, fleur          |

**Nasal vowels:**

| Phoneme | Description                                | Example              |
|---------|--------------------------------------------|----------------------|
| ɛ̃       | Nasal open-mid front unrounded             | vin, pain, bain      |
| ɑ̃       | Nasal open back unrounded                  | France, temps, an    |
| ɔ̃       | Nasal open-mid back rounded                | bon, nom, son        |

### Advanced Usage

#### Mixed Text and Phonemes
```bash
# English with specific pronunciation hints
echo "The word 'read' can be [[ r iː d ]] or [[ r ɛ d ]]" | piper --model en_US-lessac-medium.onnx -f read.wav

# Japanese with furigana-like pronunciation
echo "漢字[[ k a N j i ]]の読み方" | piper --model multilingual-test-medium.onnx -f kanji.wav
```

#### Multiple Phoneme Segments
```bash
echo "Say [[ h ə l oʊ ]] and [[ g ʊ d b aɪ ]]" | piper --model en_US-lessac-medium.onnx -f greetings.wav
```

## Implementation Details

### Text Processing Flow
1. Input text is parsed for `[[ phonemes ]]` patterns
2. Text is split into segments (regular text and phoneme sections)
3. Regular text segments are phonemized normally
4. Phoneme segments are parsed directly
5. All segments are combined for synthesis

### Japanese Multi-Character Phonemes
Japanese phonemes like `ky`, `sh`, `ts` are automatically mapped to Private Use Area (PUA) Unicode codepoints for consistency with the training data:

| Phoneme    | PUA Codepoint | Description                    |
|------------|---------------|--------------------------------|
| a:         | U+E000        | Long vowel                     |
| i:         | U+E001        | Long vowel                     |
| u:         | U+E002        | Long vowel                     |
| e:         | U+E003        | Long vowel                     |
| o:         | U+E004        | Long vowel                     |
| cl         | U+E005        | Special consonant              |
| ky         | U+E006        | Palatalized consonant          |
| kw         | U+E007        | Palatalized consonant          |
| gy         | U+E008        | Palatalized consonant          |
| gw         | U+E009        | Palatalized consonant          |
| ty         | U+E00A        | Palatalized consonant          |
| dy         | U+E00B        | Palatalized consonant          |
| py         | U+E00C        | Palatalized consonant          |
| by         | U+E00D        | Palatalized consonant          |
| ch         | U+E00E        | Affricate                      |
| ts         | U+E00F        | Affricate                      |
| sh         | U+E010        | Special sound                  |
| zy         | U+E011        | Special sound                  |
| hy         | U+E012        | Special sound                  |
| ny         | U+E013        | Palatalized nasal              |
| my         | U+E014        | Palatalized nasal              |
| ry         | U+E015        | Palatalized liquid             |
| ?!         | U+E016        | Emphatic question marker       |
| ?.         | U+E017        | Neutral/rhetorical question    |
| ?~         | U+E018        | Tag question marker            |
| N_m        | U+E019        | N before m/b/p (bilabial)      |
| N_n        | U+E01A        | N before n/t/d/ts/ch (alveolar)|
| N_ng       | U+E01B        | N before k/g (velar)           |
| N_uvular   | U+E01C        | N at end or before vowels      |

### Chinese Multi-Character Phonemes
Chinese phonemes such as aspirated consonants, compound finals, and tone markers are automatically mapped to PUA codepoints:

| Phoneme    | PUA Codepoint | Description                    |
|------------|---------------|--------------------------------|
| pʰ         | U+E020        | Aspirated bilabial (pinyin p)  |
| tʰ         | U+E021        | Aspirated alveolar (pinyin t)  |
| kʰ         | U+E022        | Aspirated velar (pinyin k)     |
| tɕ         | U+E023        | Alveolo-palatal affricate (pinyin j) |
| tɕʰ        | U+E024        | Aspirated alveolo-palatal (pinyin q) |
| tʂ         | U+E025        | Retroflex affricate (pinyin zh)|
| tʂʰ        | U+E026        | Aspirated retroflex (pinyin ch)|
| tsʰ        | U+E027        | Aspirated alveolar affricate (pinyin c) |
| aɪ         | U+E028        | Diphthong (pinyin ai)          |
| eɪ         | U+E029        | Diphthong (pinyin ei)          |
| aʊ         | U+E02A        | Diphthong (pinyin ao)          |
| oʊ         | U+E02B        | Diphthong (pinyin ou)          |
| an         | U+E02C        | Nasal final (pinyin an)        |
| ən         | U+E02D        | Nasal final (pinyin en)        |
| aŋ         | U+E02E        | Nasal final (pinyin ang)       |
| əŋ         | U+E02F        | Nasal final (pinyin eng)       |
| uŋ         | U+E030        | Nasal final (pinyin ong)       |
| ia         | U+E031        | i-compound final               |
| iɛ         | U+E032        | i-compound final               |
| iou        | U+E033        | i-compound final               |
| iaʊ        | U+E034        | i-compound final               |
| iɛn        | U+E035        | i-compound final               |
| in         | U+E036        | i-compound final               |
| iaŋ        | U+E037        | i-compound final               |
| iŋ         | U+E038        | i-compound final               |
| iuŋ        | U+E039        | i-compound final               |
| ua         | U+E03A        | u-compound final               |
| uo         | U+E03B        | u-compound final               |
| uaɪ        | U+E03C        | u-compound final               |
| ueɪ        | U+E03D        | u-compound final               |
| uan        | U+E03E        | u-compound final               |
| uən        | U+E03F        | u-compound final               |
| uaŋ        | U+E040        | u-compound final               |
| uəŋ        | U+E041        | u-compound final               |
| yɛ         | U+E042        | u-compound final               |
| yɛn        | U+E043        | u-compound final               |
| yn         | U+E044        | u-compound final               |
| ɻ̩          | U+E045        | Syllabic retroflex             |
| tone1      | U+E046        | High level tone                |
| tone2      | U+E047        | Rising tone                    |
| tone3      | U+E048        | Dipping tone                   |
| tone4      | U+E049        | Falling tone                   |
| tone5      | U+E04A        | Neutral tone                   |

### Shared Multi-Character Phonemes (ES / PT / FR)
These multi-character phonemes are shared across Spanish, Portuguese, and French:

| Phoneme    | PUA Codepoint | Used by   | Description                    |
|------------|---------------|-----------|--------------------------------|
| rr         | U+E01D        | ES        | Spanish trill r                |
| y_vowel    | U+E01E        | ZH, FR    | Close front rounded vowel [y]  |
| tʃ         | U+E054        | ES, PT    | Voiceless postalveolar affricate |
| dʒ         | U+E055        | PT        | Voiced postalveolar affricate  |
| ɛ̃          | U+E056        | FR        | Nasal front unrounded vowel    |
| ɑ̃          | U+E057        | FR        | Nasal back unrounded vowel     |
| ɔ̃          | U+E058        | FR        | Nasal back rounded vowel       |

### Limitations

1. Phoneme notation cannot be nested
2. Invalid phonemes may produce unexpected results
3. Phonemes must match the model's training phoneme set
4. Whitespace within `[[ ]]` is used to separate phonemes

## Troubleshooting

### Common Issues

1. **No audio output for phoneme sections**
   - Ensure phonemes match the expected format for your language
   - Check that phonemes are space-separated
   - Verify the model supports the phonemes used

2. **Japanese multi-character phonemes not working**
   - Use the exact romanization expected by OpenJTalk
   - Common mistakes: using `sha` instead of `sh a` (should be separate)

3. **Unexpected pronunciation**
   - Verify phoneme symbols are correct for the language
   - Check spacing between phonemes
   - Ensure UTF-8 encoding for special characters

### Debug Mode

Enable debug logging to see phoneme processing:
```bash
echo "Test [[ t ɛ s t ]]" | piper --model model.onnx --debug -f test.wav
```

## See Also

- [Phoneme Mapping](../api-reference/phoneme-mapping.md) - Technical details on phoneme mapping
- Japanese Usage Guide - Japanese-specific features
- [Training Guide](../guides/training/training-guide.md) - Training models with custom phoneme sets