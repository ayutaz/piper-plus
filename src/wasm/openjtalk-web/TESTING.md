# Testing Guide for Multilingual TTS

## Overview

This guide explains how to test the multilingual Text-to-Speech (TTS) implementation that supports both Japanese (OpenJTalk) and English (Simple Phonemizer).

## Quick Start

1. **Start the test server:**
   ```bash
   python3 test-server.py
   ```
   Or use Python's built-in server:
   ```bash
   python3 -m http.server 8080
   ```

2. **Open test pages in your browser:**
   - Simple Multilingual Demo: http://localhost:8080/test/multilingual-demo/simple-multilingual.html
   - Japanese Demo: http://localhost:8080/test/multilingual-demo/index.html

## Test Scenarios

### 1. Basic Functionality Test

**Japanese:**
- Input: "こんにちは、世界！"
- Expected: Clear Japanese speech output
- Phonemes should show Japanese phonemes (e.g., k, o, n, n, i, ch, i, w, a)

**English:**
- Input: "Hello world!"
- Expected: English speech output (may sound robotic with simple phonemizer)
- Phonemes should show IPA symbols (e.g., h, ɛ, l, oʊ)

### 2. Language Switching Test

1. Start with Japanese text
2. Generate audio
3. Switch to English
4. Enter English text
5. Generate audio
6. Verify model switches correctly

### 3. Edge Cases

**Mixed Language:**
- Input: "Hello 世界" (Mixed English/Japanese)
- System should detect primary language

**Unknown Words (English):**
- Input: "Supercalifragilisticexpialidocious"
- Should fall back to letter-by-letter phonemization

**Special Characters:**
- Input: "Hello! How are you?"
- Punctuation should be handled gracefully

## Implementation Status

### Completed ✅
- Japanese TTS using OpenJTalk
- Simple English phonemizer (dictionary-based)
- Language switching UI
- Basic ONNX model integration
- Test pages and demos

### In Progress 🚧
- Full eSpeak-ng WebAssembly integration
- Comprehensive English pronunciation dictionary
- Performance optimization

### Limitations
- English pronunciation is simplified (no eSpeak-ng yet)
- Limited English word dictionary (~60 common words)
- Unknown English words use basic letter-to-sound rules

## Troubleshooting

### Common Issues

1. **"CORS policy" errors:**
   - Use the provided test server, not file:// URLs
   - Ensure you're accessing via http://localhost:8080

2. **Model loading fails:**
   - Check that .onnx files exist in models/ directory
   - Verify model config JSON files are valid

3. **No audio output:**
   - Check browser console for errors
   - Ensure audio is not muted
   - Try a different browser

4. **Phonemes show as "undefined":**
   - Check phoneme_id_map in model config
   - Verify phoneme extraction logic

## Development Notes

### Model Configuration

The multilingual model accepts phonemes from all supported languages. Current implementation maps:
- Simple phonemes / IPA symbols → Model IDs

See `models/multilingual-test-medium.onnx.json` for phoneme mappings.

## Next Steps

1. Complete eSpeak-ng WebAssembly integration for better English
2. Add more languages
3. Implement streaming synthesis
4. Add voice selection UI