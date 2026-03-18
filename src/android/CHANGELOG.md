# Changelog

All notable changes to the Piper Android SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial Android SDK implementation
- `PiperTts` - Main TTS API with suspend `synthesize()` and `Flow` `synthesizeStream()`
- `PiperConfig` - Configuration data class with Java compatibility (@JvmField, @JvmOverloads)
- `PiperAudio` - Audio data class with WAV save support
- `AudioPlayer` - AudioTrack-based streaming playback helper
- `ModelManager` - Model file management (install/list/delete)
- `PiperTtsService` - Android TextToSpeechService integration
- `NativeBridge` - JNI bridge to C++ core engine
- 6 language support: ja, en, zh, es, fr, pt
- Streaming synthesis via Kotlin Flow
- Android Assets model loading
- Sample app with Jetpack Compose UI
- GitHub Actions CI/CD (build, test, Maven Central publish)
- Maven Central publishing configuration (vanniktech plugin)
- Cross-compilation scripts for arm64-v8a, armeabi-v7a, x86_64
