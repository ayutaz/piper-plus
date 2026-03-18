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
- GPG secrets validation in publish workflow
- Android Lint in CI/CD pipelines
- Sample app build/lint in CI
- 49 new unit tests (PiperConfigValidation, PiperAudioEdgeCase, AudioPlayer, ModelManagerInfo)
- BIND_TEXT_TO_SPEECH permission to TTS Service

### Fixed
- Fixed CMake source directory in build scripts (was pointing to root instead of Android JNI CMakeLists.txt)
- Fixed missing dependency variables (ONNXRUNTIME_DIR, OPENJTALK_DIR, SPDLOG_DIR, FMT_DIR) in build scripts
- Fixed JNI env thread safety in streaming callback
- Fixed path traversal vulnerabilities in asset copying and model management
- Fixed TTS Service callback protocol (start/done sequence)
- Fixed race conditions on nativeHandle with synchronized access
- Fixed AudioPlayer thread safety with @Volatile and synchronized
- Added text length validation (max 10,000 characters)
- Added speaker ID bounds checking
- Added PiperConfig parameter validation

### Changed
- Changed VERSION_NAME from 0.1.0-SNAPSHOT to 0.1.0 for release readiness
- Improved ProGuard rules with complete class coverage
- Improved error message sanitization in JNI layer
