# Raw Phoneme Input Feature

## Overview

The `--raw-phonemes` option allows users to provide phonemes directly as input, bypassing the text-to-phoneme conversion process entirely. This feature provides complete control over pronunciation and enables advanced use cases such as:

- Research and experimentation with novel phoneme sequences
- Direct phoneme-level control for precise pronunciation
- Testing and debugging phoneme mappings
- Creating custom pronunciations beyond standard text processing

## Usage

### Basic Syntax

```bash
echo "phoneme1 phoneme2 phoneme3" | piper --model model.onnx --raw-phonemes -f output.wav
```

Phonemes should be **space-separated** in the input.

### Examples

#### English (eSpeak phonemes)

```bash
# "hello world" as raw phonemes
echo "h ə l oʊ _ w ɜː l d" | piper --model en_US-lessac-medium.onnx --raw-phonemes -f hello_raw.wav

# Custom pronunciation sequence
echo "s ɪ ŋ _ ə _ s ɒ ŋ" | piper --model en_US-lessac-medium.onnx --raw-phonemes -f sing_song.wav
```

#### Japanese (OpenJTalk phonemes)

```bash
# "こんにちは" (konnichiwa) as raw phonemes
echo "k o N n i ch i w a" | piper --model ja_JP-test-medium.onnx --raw-phonemes -f konnichiwa_raw.wav

# "ありがとう" (arigatou) as raw phonemes
echo "a r i g a t o o" | piper --model ja_JP-test-medium.onnx --raw-phonemes -f arigatou_raw.wav
```

### Phoneme Systems

The phoneme system used depends on the model's configuration:

- **eSpeak models**: Use IPA phonemes (e.g., `ə`, `ɪ`, `ʊ`)
- **OpenJTalk models**: Use romanized Japanese phonemes (e.g., `ky`, `sh`, `ch`, `ts`)
- **Text models**: Use UTF-8 codepoints directly

### Important Notes

1. **Space Separation**: Phonemes must be separated by spaces
2. **Model Compatibility**: Phonemes must match the model's expected phoneme set
3. **No Text Processing**: The input bypasses all text normalization and phonemization
4. **Direct Control**: You have complete control over the phoneme sequence

## Comparison with Phoneme Notation

Piper supports two ways to specify phonemes:

### 1. Phoneme Notation (existing feature)
```bash
echo "Hello [[ h ə l oʊ ]] world" | piper --model model.onnx -f output.wav
```
- Mix text and phonemes in the same input
- Text portions are phonemized normally
- Phonemes in `[[ ]]` are used directly

### 2. Raw Phonemes (new feature)
```bash
echo "h ə l oʊ _ w ɜː l d" | piper --model model.onnx --raw-phonemes -f output.wav
```
- Entire input is treated as phonemes
- No text processing occurs
- Complete control over phoneme sequence

## Advanced Usage

### Multi-line Input

For longer phoneme sequences, you can use multi-line input:

```bash
cat phonemes.txt | piper --model model.onnx --raw-phonemes -f output.wav
```

Where `phonemes.txt` contains:
```
h ə l oʊ _ w ɜː l d
θ æ ŋ k s _ f ɔː _ j ʊə _ h ɛ l p
```

### JSON Input with Raw Phonemes

When using `--json-input` with `--raw-phonemes`, the text field should contain space-separated phonemes:

```bash
echo '{"text": "h ə l oʊ", "speaker_id": 0}' | piper --model model.onnx --raw-phonemes --json-input -f output.wav
```

### Streaming Output

Raw phonemes work with all output modes:

```bash
# WAV to stdout
echo "h ə l oʊ" | piper --model model.onnx --raw-phonemes -f -

# Raw audio streaming
echo "h ə l oʊ" | piper --model model.onnx --raw-phonemes --output_raw
```

## Phoneme Reference

### Common English Phonemes (eSpeak IPA)

| Sound | Phoneme | Example |
|-------|---------|---------|
| a in "cat" | æ | cat → k æ t |
| e in "bed" | ɛ | bed → b ɛ d |
| i in "see" | iː | see → s iː |
| o in "hot" | ɒ | hot → h ɒ t |
| u in "put" | ʊ | put → p ʊ t |
| schwa | ə | about → ə b aʊ t |
| th in "think" | θ | think → θ ɪ ŋ k |
| th in "this" | ð | this → ð ɪ s |
| sh | ʃ | ship → ʃ ɪ p |
| ch | tʃ | chip → tʃ ɪ p |
| ng | ŋ | sing → s ɪ ŋ |

### Common Japanese Phonemes (OpenJTalk)

| Sound | Phoneme | Kana |
|-------|---------|------|
| か | k a | か |
| き | k i | き |
| く | k u | く |
| け | k e | け |
| こ | k o | こ |
| きゃ | ky a | きゃ |
| きゅ | ky u | きゅ |
| きょ | ky o | きょ |
| し | sh i | し |
| ち | ch i | ち |
| つ | ts u | つ |
| ん | N | ん |
| っ | q | っ |
| ー | (vowel lengthening) | ー |

### Special Phonemes

- `_` - Word boundary / short pause
- `sp` - Short pause (Japanese)
- `pau` - Pause (Japanese)

## Troubleshooting

### Common Issues

1. **No audio output**
   - Verify phonemes match the model's expected format
   - Check that phonemes are space-separated
   - Ensure the model supports the phoneme set used

2. **Unexpected pronunciation**
   - Some phonemes may be missing from the model
   - Check console output for "Missing phoneme" warnings
   - Verify correct phoneme symbols (especially for IPA)

3. **Model compatibility**
   - eSpeak models: Use IPA phonemes
   - OpenJTalk models: Use romanized phonemes
   - Text models: May not support all phoneme types

### Debug Mode

Enable debug logging to see phoneme processing:

```bash
echo "h ə l oʊ" | piper --model model.onnx --raw-phonemes --debug -f test.wav
```

## Use Cases

### 1. Pronunciation Research
Test how different phoneme combinations sound:
```bash
echo "p l iː z _ t r aɪ _ ð ɪ s" | piper --model model.onnx --raw-phonemes -f test.wav
```

### 2. Custom Pronunciations
Create pronunciations not possible with standard text:
```bash
# Extended vowels
echo "h ə ə ə l oʊ oʊ oʊ" | piper --model model.onnx --raw-phonemes -f extended.wav
```

### 3. Language Learning
Generate precise pronunciations for teaching:
```bash
# Careful pronunciation of "thoroughly"
echo "θ ʌ r ə l i" | piper --model model.onnx --raw-phonemes -f thoroughly.wav
```

### 4. Accessibility
Create custom pronunciations for names or technical terms:
```bash
# Custom pronunciation for a name
echo "dʒ ɒ n _ s m ɪ θ" | piper --model model.onnx --raw-phonemes -f name.wav
```

## Limitations

1. **Phoneme Validation**: No validation is performed on input phonemes
2. **Model Dependency**: Output quality depends on model training
3. **Phoneme Coverage**: Not all possible phonemes may be supported by a given model
4. **No Prosody Control**: This feature controls phonemes only, not intonation or stress

## See Also

- [PHONEME_INPUT.md](PHONEME_INPUT.md) - Phoneme notation feature
- [PHONEME_MAPPING.md](PHONEME_MAPPING.md) - Technical details on phoneme mapping
- [TRAINING.md](TRAINING.md) - Training models with custom phoneme sets