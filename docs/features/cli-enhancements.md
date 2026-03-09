# Piper CLI Enhancements

This document describes the enhanced CLI features added to Piper TTS, inspired by OHF-Voice Piper but implemented independently.

## New Features

### 1. Volume Control

Adjust the output volume using the `--volume` parameter:

```bash
# Normal volume (default)
echo "Hello world" | piper --model en_US-lessac-medium.onnx -f output.wav

# 50% volume
echo "Hello world" | piper --model en_US-lessac-medium.onnx -f output.wav --volume 0.5

# 150% volume (louder)
echo "Hello world" | piper --model en_US-lessac-medium.onnx -f output.wav --volume 1.5
```

**Range**: 0.1 to 2.0 (default: 1.0)

### 2. Auto-Play

Automatically play the generated audio after synthesis:

```bash
# Generate and play immediately
echo "Hello world" | piper --model en_US-lessac-medium.onnx --auto-play

# Save to file and play
echo "Hello world" | piper --model en_US-lessac-medium.onnx -f output.wav --auto-play
```

**Supported platforms**:
- Linux: Uses `aplay`, `play` (sox), or `ffplay`
- macOS: Uses `afplay`
- Windows: Uses PowerShell's Media.SoundPlayer

### 3. Direct Text Input

Pass text directly as a command-line argument:

```bash
# Direct text input
piper "Hello world" --model en_US-lessac-medium.onnx -f output.wav

# With other options
piper "こんにちは世界" --model ja_JP-test-medium.onnx --auto-play --volume 1.2
```

### 4. File Input

Read text from one or more files:

```bash
# Single file
piper --model en_US-lessac-medium.onnx --input-file story.txt -f story.wav

# Multiple files (concatenated)
piper --model en_US-lessac-medium.onnx --input-file chapter1.txt --input-file chapter2.txt -f book.wav

# Process files line by line to directory
piper --model en_US-lessac-medium.onnx --input-file sentences.txt -d output_dir/
```

### 5. Inference Configuration

A new `InferenceConfig` dataclass provides a structured way to manage all synthesis parameters:

```python
from piper.inference_config import InferenceConfig

config = InferenceConfig(
    model_path="en_US-lessac-medium.onnx",
    volume=1.2,
    auto_play=True,
    sentence_silence=0.5,
    noise_scale=0.667,
    length_scale=1.0,
    noise_w=0.8
)

# Use with PiperVoice
voice = PiperVoice.load(config.model_path, config_path=config.config_path)
voice.synthesize(text, wav_file, **config.to_synthesize_args())
```

## Usage Examples

### Basic Usage with New Features

```bash
# Simple text-to-speech with auto-play
piper "Welcome to the enhanced Piper TTS" --model en_US-lessac-medium.onnx --auto-play

# Quiet narration from file
piper --model en_GB-southern_english-medium.onnx --input-file story.txt --volume 0.7 -f quiet_story.wav

# Loud announcement
piper "Attention please!" --model en_US-danny-low.onnx --volume 1.8 --auto-play
```

### Japanese Example

```bash
# Japanese text with adjusted parameters
piper "今日はいい天気ですね" \
  --model ja_JP-test-medium.onnx \
  --volume 1.1 \
  --length-scale 1.2 \
  --auto-play
```

### Batch Processing

```bash
# Process multiple text files
for file in texts/*.txt; do
  piper --model en_US-lessac-medium.onnx \
    --input-file "$file" \
    -f "audio/$(basename "$file" .txt).wav"
done
```

## Implementation Details

### Volume Adjustment
- Applied during audio normalization in `audio_float_to_int16()`
- Multiplies the audio signal before clipping and int16 conversion
- Preserves the dynamic range while adjusting overall level

### Auto-Play Implementation
- Platform detection using `platform.system()`
- Fallback mechanisms for Linux (tries multiple players)
- Temporary file creation for stdout mode
- Automatic cleanup after playback

### Input Priority
1. Direct text argument (highest priority)
2. `--input-file` option(s)
3. Standard input (default)

## Backward Compatibility

All existing Piper functionality remains unchanged:
- Standard input/output behavior preserved
- Existing command-line options work as before
- No changes to model loading or synthesis algorithms

## GPU Device Selection (v1.5.0+)

Select specific GPU devices for multi-GPU systems:

> **Note**: `--gpu-device-id` and the `PIPER_GPU_DEVICE_ID` environment variable are available in the **C++ CLI only**, not the Python CLI.

```bash
# Use default GPU (device 0)
piper "Hello" --model model.onnx --use-cuda -f output.wav

# Use GPU device 1
piper "Hello" --model model.onnx --use-cuda --gpu-device-id 1 -f output.wav

# Set via environment variable
export PIPER_GPU_DEVICE_ID=2
piper "Hello" --model model.onnx --use-cuda -f output.wav
```

**Priority**: CLI argument > Environment variable > Default (0)

For detailed GPU configuration, see [GPU Configuration Guide](gpu-configuration.md).

## Phoneme Input Support (v1.5.0+)

Direct phoneme input using `[[ phonemes ]]` notation:
```bash
# English example
echo "Say [[ h ə l oʊ ]] clearly" | piper --model en_US-lessac.onnx -f hello.wav

# Japanese example  
echo "名前は [[ m a i k u r u ]] です" | piper --model ja_JP-test.onnx -f name.wav
```

For detailed usage, see [Phoneme Input Guide](phoneme-input.md).

## Future Enhancements

Planned features for future releases:
- Volume normalization options
- Audio format selection (MP3, OGG, etc.)
- Playlist generation for batch processing
- Integration with audio effects