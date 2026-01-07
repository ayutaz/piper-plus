# Phoneme Timing Information Output

Piper can output timing information for each phoneme during text-to-speech synthesis, enabling applications like lip-sync animation, karaoke-style highlighting, and precise subtitle synchronization.

## Overview

Piper extracts phoneme duration information from the synthesis process and outputs start/end times for each phoneme. Duration information is automatically included in all ONNX model exports.

## Requirements

1. **Model Support**: All ONNX models exported with piper_train include duration information by default:
   ```bash
   python -m piper_train.export_onnx checkpoint.ckpt model.onnx
   ```

2. **Piper Version**: Requires Piper built from this branch or later

## Usage

### Command Line Options

- `--output-timing FILE` - Output phoneme timing to FILE
- `--timing-format FORMAT` - Output format: `json` (default) or `tsv`

### Examples

#### JSON Output
```bash
echo "Hello world" | piper --model en_US-lessac-medium.onnx \
  --output-file speech.wav \
  --output-timing timing.json
```

Output format:
```json
{
  "phonemes": [
    {"phoneme": "h", "start": 0.000, "end": 0.045, "start_frame": 0, "end_frame": 4},
    {"phoneme": "ə", "start": 0.045, "end": 0.120, "start_frame": 4, "end_frame": 10},
    {"phoneme": "l", "start": 0.120, "end": 0.180, "start_frame": 10, "end_frame": 16},
    {"phoneme": "oʊ", "start": 0.180, "end": 0.300, "start_frame": 16, "end_frame": 26}
  ],
  "text": "Hello world",
  "total_duration": 1.234,
  "sample_rate": 22050,
  "frame_shift_ms": 11.61
}
```

#### TSV Output
```bash
echo "Hello world" | piper --model en_US-lessac-medium.onnx \
  --output-file speech.wav \
  --output-timing timing.tsv \
  --timing-format tsv
```

Output format:
```
phoneme	start	end	start_frame	end_frame
h	0.000	0.045	0	4
ə	0.045	0.120	4	10
l	0.120	0.180	10	16
oʊ	0.180	0.300	16	26
```

## Language-Specific Considerations

### Japanese
- Multi-character phonemes (e.g., "ky", "sh") are properly handled
- Special phonemes like "cl" (促音) have adjusted timing for natural synthesis
- Example:
  ```bash
  echo "こんにちは" | piper --model ja_JP-test.onnx \
    --output-file speech.wav \
    --output-timing timing.json
  ```

### English and Other Languages
- Uses eSpeak-ng phoneme notation
- Handles stress markers and special characters
- Padding symbols are excluded from output

## Applications

### 1. Lip-Sync Animation
Use timing data to synchronize character mouth movements:
```python
import json

with open('timing.json') as f:
    timing = json.load(f)

for phoneme in timing['phonemes']:
    # Map phoneme to viseme
    viseme = phoneme_to_viseme(phoneme['phoneme'])
    # Animate at specified time
    animate_mouth(viseme, phoneme['start'], phoneme['end'])
```

### 2. Karaoke-Style Highlighting
Highlight text as it's being spoken:
```javascript
const timing = JSON.parse(fs.readFileSync('timing.json'));
timing.phonemes.forEach(phoneme => {
    setTimeout(() => {
        highlightPhoneme(phoneme.phoneme);
    }, phoneme.start * 1000);
});
```

### 3. Subtitle Synchronization
Generate precise subtitles with word-level timing:
```python
# Group phonemes into words
words = group_phonemes_to_words(timing['phonemes'])
for word in words:
    print(f"{word['text']} @ {word['start']:.3f} - {word['end']:.3f}")
```

## Technical Details

### Timing Accuracy
- Frame-level precision based on model's hop size (typically ~11.6ms at 22050Hz)
- Actual accuracy depends on the duration predictor in the VITS model
- Best results with models trained on forced-aligned data

### Performance Impact
- Minimal overhead (<5% slower inference)
- Small memory increase for duration storage
- No impact on audio quality

### Limitations
1. **Frame Granularity**: Timing precision limited by hop size
2. **No Sub-phoneme Information**: Cannot provide timing for phoneme parts

## Compatibility with Older Models

Models exported before this change (without duration output) will still work for audio synthesis, but timing information will not be available. Re-export such models to enable timing support.

## Integration Example

```cpp
// C++ Integration
#include "piper.hpp"

piper::Voice voice;
piper::SynthesisResult result;
std::vector<int16_t> audioBuffer;

// Synthesize with timing
piper::textToAudio(config, voice, "Hello world", audioBuffer, result);

if (result.hasTimingInfo) {
    for (const auto& info : result.phonemeTimings) {
        printf("%s: %.3f - %.3f\n", 
               info.phoneme.c_str(), 
               info.start_time, 
               info.end_time);
    }
}
```

## See Also
- [Training Guide](guides/TRAINING.md) - For creating compatible models
- [Japanese Usage](guides/JAPANESE_USAGE.md) - Japanese-specific features
- [Phoneme Mapping](guides/PHONEME_MAPPING.md) - Phoneme notation details