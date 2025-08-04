# Streaming Mode

Piper now supports a streaming synthesis mode that reduces latency by processing text in chunks and outputting audio progressively.

## Usage

Add the `--streaming` flag when using raw audio output:

```bash
# Text input
echo "Your text here" | piper --model model.onnx --output-raw --streaming

# Raw phonemes input (also supported)
echo "h ə l oʊ w ɜː l d" | piper --model model.onnx --output-raw --streaming --raw-phonemes
```

## How It Works

### Text Mode
1. **Text Chunking**: Input text is split into smaller chunks at natural boundaries (punctuation, conjunctions)
2. **Progressive Synthesis**: Each chunk is phonemized and synthesized independently
3. **Immediate Output**: Audio is output as soon as each chunk is ready

### Raw Phonemes Mode
1. **Phoneme Chunking**: Input phonemes are split into configurable chunks (default: 10 phonemes)
2. **Progressive Synthesis**: Each chunk is synthesized with proper BOS/EOS token handling
3. **Immediate Output**: Audio chunks are output progressively

## Performance

Streaming mode provides the most benefit for longer texts:
- Short texts (< 20 chars): ~2% improvement
- Medium texts (20-50 chars): Minimal improvement
- Long texts (> 100 chars): 10-15% improvement

## Language Support

- **English**: Splits on punctuation and common conjunctions
- **Japanese**: Splits on Japanese punctuation (。、！？)
- **Other languages**: Falls back to punctuation-based splitting

## Limitations

- Currently only works with `--output-raw` mode
- Audio quality at chunk boundaries may vary slightly

## API Usage

For developers using the C++ API:

```cpp
#include "piper.hpp"

// Callback receives audio chunks as they're ready
auto chunkCallback = [](const std::vector<int16_t>& chunk) {
    // Process or output chunk immediately
};

piper::textToAudioStreaming(config, voice, text, audioBuffer, 
                            result, chunkCallback);
```

## Future Improvements

- Fine-grained chunking at word/syllable level
- Progressive phonemization for even lower latency
- Support for WAV output mode
- Configurable chunk size for raw phonemes mode via command-line flag