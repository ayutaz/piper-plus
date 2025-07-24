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
echo "今日は [[ ky o o w a ]] いい天気です" | piper --model ja_JP-test-medium.onnx -f weather.wav

# Foreign name in katakana context
echo "私は [[ m a i k u r u ]] です" | piper --model ja_JP-test-medium.onnx -f michael.wav
```

### Phoneme Systems

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

### Advanced Usage

#### Mixed Text and Phonemes
```bash
# English with specific pronunciation hints
echo "The word 'read' can be [[ r iː d ]] or [[ r ɛ d ]]" | piper --model en_US-lessac-medium.onnx -f read.wav

# Japanese with furigana-like pronunciation
echo "漢字[[ k a N j i ]]の読み方" | piper --model ja_JP-test-medium.onnx -f kanji.wav
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

| Phoneme | PUA Codepoint |
|---------|---------------|
| ky      | U+E000        |
| gy      | U+E001        |
| sy/sh   | U+E002        |
| zy/jy   | U+E003        |
| ty/ch   | U+E004        |
| dy      | U+E005        |
| ny      | U+E006        |
| hy      | U+E007        |
| by      | U+E008        |
| py      | U+E009        |
| my      | U+E00A        |
| ry      | U+E00B        |
| ts      | U+E00C        |
| dz      | U+E00D        |
| kw      | U+E00E        |
| f       | U+E00F        |
| gw      | U+E010        |
| v       | U+E011        |

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

- [PHONEME_MAPPING.md](../PHONEME_MAPPING.md) - Technical details on phoneme mapping
- [JAPANESE_USAGE.md](../JAPANESE_USAGE.md) - Japanese-specific features
- [TRAINING.md](../TRAINING.md) - Training models with custom phoneme sets