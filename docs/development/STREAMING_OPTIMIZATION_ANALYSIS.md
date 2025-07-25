# Streaming Optimization Analysis

## Baseline Performance Results

### English Model (test_voice.onnx)
- Average first-byte latency: 157.7ms (raw), 162.3ms (WAV)
- Latency range: 151.4-175.0ms (relatively consistent)
- No correlation with text length (12-196 chars all ~150-160ms)

### Japanese Model (ja_JP-test-medium.onnx)
- Average first-byte latency: 469.7ms (raw), 479.7ms (WAV)
- Latency range: 451.4-518.9ms
- Also no correlation with text length

## Key Findings

1. **High Initial Latency**: Both models show 150-500ms latency before first audio byte
2. **No Progressive Output**: Latency is constant regardless of text length, confirming full-sentence processing
3. **Model Loading Overhead**: Japanese model has 3x higher latency, likely due to OpenJTalk initialization

## Identified Bottlenecks

1. **Full Sentence Processing**: Current implementation in `textToAudio()` processes entire sentences before any output
2. **Phonemization Overhead**: Especially for Japanese (OpenJTalk), entire text is phonemized upfront
3. **No Chunking**: Audio synthesis happens in one large batch

## Implementation Strategy

### Phase 1: Sub-sentence Chunking
- Implement chunk-based processing in `piper.cpp`
- Add new `textToAudioStreaming()` function
- Process text in smaller segments (e.g., phrases/clauses)

### Phase 2: Progressive Phonemization
- Modify phonemization to work incrementally
- For Japanese, detect clause boundaries (、。！？)
- For English, use punctuation and conjunctions

### Phase 3: Audio Buffer Optimization
- Implement ring buffer for audio output
- Start outputting as soon as first chunk is ready
- Overlap synthesis with output

### Target Metrics
- First-byte latency: < 50ms for English, < 150ms for Japanese
- Maintain audio quality and natural flow