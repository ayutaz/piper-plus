# Piper Android TTS SDK

Android向けの高品質ニューラルTTS (Text-to-Speech) ライブラリ。VITSアーキテクチャを採用し、6言語 (日本語, 英語, 中国語, スペイン語, フランス語, ポルトガル語) に対応。

## Features

- 6言語対応 (ja, en, zh, es, fr, pt)
- Kotlin-first API (Java互換)
- Kotlin Coroutines対応 (suspend + Flow)
- ストリーミング合成 (低遅延)
- Android TextToSpeechService 対応 (システムTTSエンジン)
- FP16モデル対応 (APKサイズ ~50%削減)
- ONNX Runtime推論 (CPU / NNAPI)

## Installation

### Gradle (Maven Central)

```groovy
dependencies {
    implementation("io.github.ayousanz:piper-android:1.0.0")
}
```

## Quick Start

### Kotlin

```kotlin
// Load model
val piper = PiperTts.load(
    PiperConfig(
        modelPath = "/path/to/model.onnx",
        configPath = "/path/to/config.json",
    )
)

// Synthesize
piper.use { tts ->
    val audio = tts.synthesize("こんにちは", language = "ja")

    // Play with AudioPlayer
    AudioPlayer(audio.sampleRate).use { player ->
        player.play(audio)
    }

    // Or save to WAV
    audio.save("/path/to/output.wav")
}
```

### Load from Assets

```kotlin
val piper = PiperTts.load(
    context = this,
    assetModelPath = "model.onnx",
)
```

### Streaming (Low Latency)

```kotlin
piper.synthesizeStream("Long text...", language = "en")
    .buffer(2)
    .collect { chunk ->
        audioTrack.write(chunk, 0, chunk.size)
    }
```

### Java

```java
PiperConfig config = new PiperConfig("/path/to/model.onnx", "/path/to/config.json");
PiperTts tts = PiperTts.load(config);

// Note: synthesize() is a suspend function.
// Use PiperTts from a coroutine scope in Java,
// or use the TextToSpeechService integration instead.
```

## Model Management

```kotlin
val manager = ModelManager(context)

// Install from assets
val model = manager.installFromAssets("my-model")

// List installed models
manager.listModels().forEach { info ->
    println("${info.name}: ${info.sizeDisplay}")
}

// Load model
val tts = PiperTts.load(model.toConfig())
```

## System TTS Engine

Piper TTS can be registered as an Android system TTS engine.
Copy model files to `<app>/files/piper/`, then select "Piper TTS"
in Android Settings > Text-to-Speech > Preferred engine.

## API Reference

### PiperTts

| Method | Description |
|--------|-------------|
| `load(config)` | Load model from file paths |
| `load(context, assetPath)` | Load model from Android assets |
| `synthesize(text, language, speakerId)` | Synthesize text to audio (suspend) |
| `synthesizeStream(text, language, speakerId)` | Streaming synthesis (Flow) |
| `close()` | Release native resources |
| `sampleRate` | Model sample rate (typically 22050) |
| `numSpeakers` | Number of speakers in model |
| `numLanguages` | Number of languages in model |

### PiperConfig

| Parameter | Default | Description |
|-----------|---------|-------------|
| `modelPath` | (required) | Path to ONNX model |
| `configPath` | (required) | Path to config.json |
| `speakerId` | 0 | Default speaker ID |
| `noiseScale` | 0.667 | Phoneme variability |
| `lengthScale` | 1.0 | Speech speed (< 1.0 = faster) |
| `noiseW` | 0.8 | Phoneme width variability |

### Supported Languages

| Code | Language |
|------|----------|
| `ja` | 日本語 |
| `en` | English |
| `zh` | 中文 |
| `es` | Español |
| `fr` | Français |
| `pt` | Português |

## Requirements

- Android API 24+ (Android 7.0)
- arm64-v8a, armeabi-v7a, or x86_64

## License

MIT License
