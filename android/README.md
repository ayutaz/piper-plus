# piper-plus Android AAR

Android AAR library for [piper-plus](https://github.com/ayutaz/piper-plus) -- offline multilingual neural text-to-speech.

Wraps the piper-plus C shared library via JNI and exposes a Kotlin-friendly API with `AutoCloseable` lifecycle management and `Flow`-based streaming synthesis.

## Requirements

- Android SDK: compileSdk 35, minSdk 24
- NDK (for JNI compilation)
- Pre-built `libpiper_plus.so` for arm64-v8a (from [M4-4 NDK build](../docs/tickets/M4-4-android-ndk-build.md))

## Project structure

```
android/
  build.gradle.kts              Root Gradle build
  settings.gradle.kts           Project settings
  gradle.properties             Version and Android properties
  piper-plus/
    build.gradle.kts            AAR library Gradle build
    consumer-rules.pro          ProGuard rules shipped in the AAR
    proguard-rules.pro          Build-time ProGuard rules
    src/main/
      AndroidManifest.xml
      cpp/
        CMakeLists.txt          CMake build for JNI wrapper
        piper_plus_jni.cpp      JNI C++ wrapper over C API
      java/com/piperplus/
        PiperPlus.kt            High-level Kotlin API
        PiperPlusNative.kt      JNI bridge (external functions)
        PiperPlusException.kt   Exception type for native errors
      jniLibs/
        arm64-v8a/              Place libpiper_plus.so here
      assets/
        open_jtalk_dic/         OpenJTalk dictionary (optional)
```

## Build

### 1. Place native libraries

Copy the pre-built shared libraries into `jniLibs/arm64-v8a/`:

```bash
cp /path/to/libpiper_plus.so android/piper-plus/src/main/jniLibs/arm64-v8a/
```

### 2. Build the AAR

```bash
cd android
./gradlew :piper-plus:assembleRelease
```

The AAR is produced at `piper-plus/build/outputs/aar/piper-plus-release.aar`.

### 3. OpenJTalk dictionary (for Japanese)

If your model uses Japanese, place the OpenJTalk dictionary files in
`src/main/assets/open_jtalk_dic/`. The library auto-extracts them to
internal storage on first use. Alternatively, pass a `dictDir` path
to `PiperPlus.create()`.

## Usage

### Gradle dependency

For local development, add the AAR as a file dependency:

```kotlin
dependencies {
    implementation(files("path/to/piper-plus-release.aar"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
```

When published to GitHub Packages:

```kotlin
repositories {
    maven {
        url = uri("https://maven.pkg.github.com/ayutaz/piper-plus")
        credentials {
            username = System.getenv("GITHUB_ACTOR")
            password = System.getenv("GITHUB_TOKEN")
        }
    }
}

dependencies {
    implementation("com.piperplus:piper-plus:0.1.0")
}
```

### One-shot synthesis

```kotlin
import com.piperplus.PiperPlus

// Create engine (auto-extracts OpenJTalk dict from assets)
PiperPlus.create(context, modelPath).use { tts ->
    val pcm: ShortArray = tts.synthesize("Hello, world!")
    // pcm contains 16-bit PCM at tts.sampleRate Hz
    // Play with AudioTrack, write to WAV, etc.
}
```

### Streaming synthesis (Flow)

```kotlin
import com.piperplus.PiperPlus

PiperPlus.create(context, modelPath).use { tts ->
    tts.synthesizeStream("Long text with multiple sentences.").collect { chunk ->
        // Each chunk is one sentence of 16-bit PCM audio.
        // Feed to AudioTrack for low-latency playback.
    }
}
```

### Specifying speaker

```kotlin
// Multi-speaker model: select speaker by index
val audio = tts.synthesize("Text", speakerId = 5)
```

### Model info

```kotlin
tts.sampleRate    // e.g. 22050
tts.numSpeakers   // e.g. 571
tts.numLanguages  // e.g. 6
```

## ProGuard / R8

The AAR ships `consumer-rules.pro` which automatically keeps JNI methods
and public API classes. No additional ProGuard configuration is needed in
consuming apps.

## API reference

### PiperPlus

| Method | Description |
|--------|-------------|
| `PiperPlus.create(context, modelPath, configPath?, dictDir?)` | Create engine |
| `synthesize(text, speakerId)` | One-shot synthesis, returns `ShortArray` |
| `synthesizeStream(text, speakerId)` | Streaming synthesis via `Flow<ShortArray>` |
| `sampleRate` | Sample rate in Hz |
| `numSpeakers` | Number of speakers |
| `numLanguages` | Number of languages |
| `close()` | Free native resources |

### PiperPlusException

Thrown on native errors. The message is from `piper_plus_get_last_error()`.

## Architecture support

Currently arm64-v8a only. To add armeabi-v7a or x86_64, build `libpiper_plus.so`
for those ABIs and place them in the corresponding `jniLibs/` subdirectories,
then add the ABI to `abiFilters` in `build.gradle.kts`.

## License

MIT -- see [LICENSE.md](../LICENSE.md).
