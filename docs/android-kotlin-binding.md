# Android Kotlin/Java 推論バインディング -- 技術設計書

> Issue: [#257](https://github.com/ayutaz/piper-plus/issues/257)
> ブランチ: `feat/android-kotlin-binding`
> 作成日: 2026-03-19

---

## 1. 概要

Android向けのネイティブTTS推論バインディングをKotlin-firstで実装する。ONNX Runtimeの公式Java API (Maven) を基盤とし、piper-plusのC++コアをJNI経由でKotlinから呼び出すアーキテクチャを採用する。

### アーキテクチャ全体像

```
┌─────────────────────────────────────────────────┐
│              Android アプリ層                      │
│  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Jetpack      │  │ TextToSpeechService      │  │
│  │ Compose UI   │  │ (システムTTSエンジン)      │  │
│  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                     │                   │
│  ┌──────▼─────────────────────▼───────────────┐  │
│  │        Kotlin API (PiperTts)                │  │
│  │  - suspend synthesize()                     │  │
│  │  - Flow<ShortArray> ストリーミング            │  │
│  │  - data class PiperConfig                   │  │
│  └──────────────────┬─────────────────────────┘  │
│                     │ JNI                        │
│  ┌──────────────────▼─────────────────────────┐  │
│  │        C++ コア (libpiper_jni.so)           │  │
│  │  - piper.cpp (推論エンジン)                   │  │
│  │  - *_phonemize.cpp (6言語G2P)               │  │
│  │  - ONNX Runtime C++ API                     │  │
│  └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

---

## 2. 技術的意思決定

### 2.1 C++ JNIラップ vs ONNX Runtime Java API 直接使用

| 観点 | C++ JNIラップ (採用) | Java API 直接使用 |
|------|---------------------|-------------------|
| 開発コスト | 高い | 低い |
| 前後処理統合 | C++で一貫 (phonemizer含む) | Kotlin側に別途実装が必要 |
| JNI越境回数 | 1回 (text→audio) | 複数回 (phonemize + tensor構築 + 推論) |
| 実績 | sherpa-onnxで同パターン実証済み | - |
| APKサイズ | `libonnxruntime.so` + `libpiper_jni.so` | `libonnxruntime.so` + `libonnxruntime4j_jni.so` |
| Phonemizer | 既存C++実装をそのまま利用 | 6言語分をKotlinに移植 (12-15人日) |

**決定: C++ JNIラップを採用**

理由:
1. piper-plusは既にC++で6言語のPhonemizer (OpenJTalk, CMU dict G2P, pypinyin互換等) を完備している
2. Kotlinへの6言語Phonemizer移植は12-15人日の大規模作業であり、Python版との同期も必要
3. sherpa-onnxが同パターンでPiper TTSモデルの推論実績がある
4. JNI越境を1回 (text→audio) に集約でき、レイテンシ最小化

### 2.2 ビルド方式: 分離ビルド vs Gradle統合

| 観点 | 分離ビルド (採用) | Gradle externalNativeBuild |
|------|------------------|---------------------------|
| ビルド時間 | CI/CDで事前ビルド→jniLibs配置 | 毎回CMakeクロスコンパイル |
| 依存管理 | CMakeで完結 | Gradle+CMake混在 |
| sherpa-onnx実績 | 同パターン採用 | - |
| デバッグ | NDK toolchain直接 | Android Studio統合 |

**決定: 分離ビルド**

CMakeでクロスコンパイル → `.so`をCI/CDでビルド → `jniLibs/`に配置する方式。

---

## 3. プロジェクト構造

```
src/android/
├── settings.gradle.kts
├── build.gradle.kts                    # ルートプロジェクト
├── gradle/
│   └── libs.versions.toml              # バージョンカタログ
│
├── piper-android/                      # AARライブラリモジュール
│   ├── build.gradle.kts
│   ├── consumer-rules.pro
│   ├── src/
│   │   ├── main/
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── kotlin/
│   │   │   │   └── com/github/ayousanz/piper/
│   │   │   │       ├── PiperTts.kt              # メインAPI
│   │   │   │       ├── PiperConfig.kt            # 設定data class
│   │   │   │       ├── PiperAudio.kt             # 音声データdata class
│   │   │   │       ├── PiperTtsService.kt        # TextToSpeechService実装
│   │   │   │       └── internal/
│   │   │   │           └── NativeBridge.kt       # JNIブリッジ
│   │   │   └── jniLibs/                          # 事前ビルド済みネイティブライブラリ
│   │   │       ├── arm64-v8a/
│   │   │       │   ├── libpiper_jni.so
│   │   │       │   └── libonnxruntime.so
│   │   │       ├── armeabi-v7a/
│   │   │       │   └── ...
│   │   │       └── x86_64/
│   │   │           └── ...
│   │   └── test/
│   │       └── kotlin/                           # ユニットテスト
│   └── CMakeLists.txt                            # (参考: ローカルビルド用)
│
├── sample-app/                         # サンプルアプリモジュール
│   ├── build.gradle.kts
│   └── src/main/
│       ├── kotlin/                     # Jetpack Compose UI
│       └── AndroidManifest.xml
│
└── scripts/
    ├── build-android-arm64-v8a.sh      # ARM64クロスコンパイル
    ├── build-android-armeabi-v7a.sh    # ARMv7クロスコンパイル
    └── build-android-x86_64.sh         # x86_64クロスコンパイル
```

---

## 4. C++ JNIブリッジ設計

### 4.1 既存C++コアのAPI

piper-plusのC++コアは以下の主要APIを提供する:

```cpp
// 初期化・終了
void initialize(PiperConfig &config);
void terminate(PiperConfig &config);

// モデルロード
void loadVoice(PiperConfig &config, std::string modelPath,
               std::string modelConfigPath, Voice &voice, ...);

// テキスト→音声 (ハイレベルAPI)
void textToAudio(PiperConfig &config, Voice &voice, std::string text,
                 std::vector<int16_t> &audioBuffer, SynthesisResult &result, ...);

// ストリーミング合成
void textToAudioStreaming(PiperConfig &config, Voice &voice, std::string text,
                          std::vector<int16_t> &audioBuffer, SynthesisResult &result,
                          const std::function<void(const std::vector<int16_t>&)> &chunkCallback, ...);
```

### 4.2 ONNXモデル入出力テンソル

| 入力名 | 型 | 形状 | 説明 |
|--------|-----|------|------|
| `input` | int64 | [1, seq_len] | 音素ID列 |
| `input_lengths` | int64 | [1] | inputの長さ |
| `scales` | float32 | [3] | [noise_scale, length_scale, noise_w] |
| `sid` (opt) | int64 | [1] | Speaker ID |
| `lid` (opt) | int64 | [1] | Language ID |
| `prosody_features` (opt) | int64 | [1, seq_len, 3] | A1/A2/A3値 |

| 出力名 | 型 | 形状 | 説明 |
|--------|-----|------|------|
| `output` | float32 | [1, audio_len] | PCMサンプル (浮動小数) |

音声出力仕様: **22050 Hz / 16-bit signed / Mono**

### 4.3 JNIブリッジ実装

sherpa-onnxのパターンを踏襲し、thin JNI layerを実装する。

**ネイティブポインタ管理パターン:**

```cpp
// 作成: C++ポインタ → jlong にキャスト
JNIEXPORT jlong JNICALL Java_..._nativeCreate(...) {
    auto* engine = new PiperEngine(modelPath, configPath);
    return reinterpret_cast<jlong>(engine);
}

// 使用: jlong → C++ポインタに復元
JNIEXPORT jshortArray JNICALL Java_..._nativeSynthesize(
    JNIEnv *env, jobject thiz, jlong handle, jstring text, ...) {
    auto* engine = reinterpret_cast<PiperEngine*>(handle);
    // ...
}

// 破棄: 明示的に delete
JNIEXPORT void JNICALL Java_..._nativeDestroy(
    JNIEnv *env, jobject thiz, jlong handle) {
    delete reinterpret_cast<PiperEngine*>(handle);
}
```

**例外安全パターン:**

```cpp
#define PIPER_JNI_TRY_CATCH(env, returnOnError, block) \
    try { block } \
    catch (const Ort::Exception& e) { \
        env->ThrowNew(env->FindClass("java/lang/RuntimeException"), e.what()); \
        return returnOnError; \
    } catch (const std::exception& e) { \
        env->ThrowNew(env->FindClass("java/lang/RuntimeException"), e.what()); \
        return returnOnError; \
    }
```

**音声データ返却 (C++ → Kotlin):**

```cpp
// int16_t配列 → jshortArray
jshortArray result = env->NewShortArray(audioBuffer.size());
env->SetShortArrayRegion(result, 0, audioBuffer.size(), audioBuffer.data());
return result;
```

---

## 5. Kotlin API設計

### 5.1 メインAPI

```kotlin
package com.github.ayousanz.piper

data class PiperConfig(
    val modelPath: String,
    val configPath: String,
    val speakerId: Int = 0,
    val noiseScale: Float = 0.667f,
    val lengthScale: Float = 1.0f,
    val noiseW: Float = 0.8f,
)

data class PiperAudio(
    val samples: ShortArray,
    val sampleRate: Int = 22050,
) {
    fun save(path: String) { /* WAV書き出し */ }
}

class PiperTts private constructor(
    private var nativeHandle: Long,
    val config: PiperConfig,
) : AutoCloseable {

    companion object {
        init { System.loadLibrary("piper_jni") }

        fun load(config: PiperConfig): PiperTts { /* ... */ }

        // Android Assets対応
        fun load(context: Context, assetModelPath: String): PiperTts { /* ... */ }
    }

    // 基本合成
    suspend fun synthesize(
        text: String,
        language: String = "ja",
        speakerId: Int = config.speakerId,
    ): PiperAudio = withContext(Dispatchers.Default) {
        PiperAudio(nativeSynthesize(nativeHandle, text, language, speakerId))
    }

    // ストリーミング合成
    fun synthesizeStream(
        text: String,
        language: String = "ja",
        speakerId: Int = config.speakerId,
    ): Flow<ShortArray> = callbackFlow {
        nativeSynthesizeStreaming(nativeHandle, text, language, speakerId) { chunk ->
            trySend(chunk)
        }
        awaitClose { /* cancel native */ }
    }.flowOn(Dispatchers.Default)

    override fun close() {
        if (nativeHandle != 0L) {
            nativeDestroy(nativeHandle)
            nativeHandle = 0L
        }
    }

    // JNI native declarations
    private external fun nativeSynthesize(
        handle: Long, text: String, language: String, speakerId: Int
    ): ShortArray

    private external fun nativeSynthesizeStreaming(
        handle: Long, text: String, language: String, speakerId: Int,
        callback: (ShortArray) -> Unit
    )

    private external fun nativeDestroy(handle: Long)
}
```

### 5.2 Java互換

```kotlin
// @JvmStatic で Java から PiperTts.load() として呼べるようにする
companion object {
    @JvmStatic
    fun load(config: PiperConfig): PiperTts { /* ... */ }
}

// @JvmOverloads でデフォルト引数をJavaから利用可能にする
@JvmOverloads
suspend fun synthesize(
    text: String,
    language: String = "ja",
    speakerId: Int = config.speakerId,
): PiperAudio
```

### 5.3 使用例

```kotlin
// Kotlin
val piper = PiperTts.load(PiperConfig(modelPath = "/path/to/model.onnx", configPath = "/path/to/config.json"))
piper.use { tts ->
    val audio = tts.synthesize("こんにちは", language = "ja")
    audioTrack.write(audio.samples, 0, audio.samples.size)
}

// ストリーミング
piper.synthesizeStream("長い文章...", language = "ja")
    .buffer(2)
    .collect { chunk -> audioTrack.write(chunk, 0, chunk.size) }

// Java
PiperTts piper = PiperTts.load(new PiperConfig("/path/to/model.onnx", "/path/to/config.json"));
PiperAudio audio = piper.synthesize("Hello", "en", 0);
```

---

## 6. Android TextToSpeechService統合

```kotlin
class PiperTtsService : TextToSpeechService() {
    private lateinit var engine: PiperTts
    private val supportedLanguages = setOf("ja", "en", "zh", "es", "fr", "pt")

    override fun onCreate() {
        super.onCreate()
        engine = PiperTts.load(context = this, assetModelPath = "model.onnx")
    }

    override fun onIsLanguageAvailable(lang: String, country: String, variant: String): Int {
        return if (lang.lowercase() in supportedLanguages)
            TextToSpeech.LANG_AVAILABLE
        else
            TextToSpeech.LANG_NOT_SUPPORTED
    }

    override fun onLoadLanguage(lang: String, country: String, variant: String): Int =
        onIsLanguageAvailable(lang, country, variant)

    override fun onGetLanguage(): Array<String> = arrayOf("ja", "JPN", "")

    override fun onSynthesizeText(request: SynthesisRequest, callback: SynthesisCallback) {
        val text = request.charSequenceText?.toString() ?: return callback.error()
        val lang = request.language ?: "ja"

        callback.start(22050, AudioFormat.ENCODING_PCM_16BIT, 1)

        // 推論実行 (同期、専用スレッドで呼ばれる)
        val audio = runBlocking { engine.synthesize(text, language = lang) }

        // PCMチャンク送信
        val byteBuffer = ByteBuffer.allocate(audio.samples.size * 2)
            .order(ByteOrder.LITTLE_ENDIAN)
        audio.samples.forEach { byteBuffer.putShort(it) }
        val bytes = byteBuffer.array()

        val maxBytes = callback.maxBufferSize
        var offset = 0
        while (offset < bytes.size) {
            val size = minOf(maxBytes, bytes.size - offset)
            callback.audioAvailable(bytes, offset, size)
            offset += size
        }
        callback.done()
    }

    override fun onStop() { /* キャンセル処理 */ }

    override fun onDestroy() {
        engine.close()
        super.onDestroy()
    }
}
```

**AndroidManifest.xml:**

```xml
<service android:name=".PiperTtsService" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.TTS_SERVICE" />
        <category android:name="android.intent.category.DEFAULT" />
    </intent-filter>
    <meta-data android:name="android.speech.tts" android:resource="@xml/tts_engine" />
</service>
```

---

## 7. ビルドシステム

### 7.1 Gradle設定

**gradle/libs.versions.toml:**

```toml
[versions]
agp = "8.7.3"
kotlin = "2.1.0"
compileSdk = "35"
minSdk = "24"
onnxruntime = "1.24.2"
composeBom = "2025.01.01"

[libraries]
onnxruntime-android = { group = "com.microsoft.onnxruntime", name = "onnxruntime-android", version.ref = "onnxruntime" }

[plugins]
android-library = { id = "com.android.library", version.ref = "agp" }
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
```

**piper-android/build.gradle.kts:**

```kotlin
plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    id("com.vanniktech.maven.publish") version "0.30.0"
}

android {
    namespace = "com.github.ayousanz.piper"
    compileSdk = 35

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    publishing {
        singleVariant("release") {
            withSourcesJar()
            withJavadocJar()
        }
    }
}

dependencies {
    implementation(libs.onnxruntime.android)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
```

### 7.2 クロスコンパイルスクリプト

**scripts/build-android-arm64-v8a.sh:**

```bash
#!/bin/bash
set -euo pipefail

ANDROID_NDK=${ANDROID_NDK:-$ANDROID_HOME/ndk/27.0.12077973}
BUILD_DIR=build-android-arm64-v8a
INSTALL_DIR=install-android-arm64-v8a

cmake -S . -B $BUILD_DIR \
    -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-24 \
    -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=$INSTALL_DIR \
    -DBUILD_ANDROID_JNI=ON

cmake --build $BUILD_DIR --parallel $(nproc)
cmake --install $BUILD_DIR --strip
```

### 7.3 ProGuard/R8

**consumer-rules.pro:**

```proguard
-keepclasseswithmembers class com.github.ayousanz.piper.** { native <methods>; }
-keep public class com.github.ayousanz.piper.PiperTts { public *; }
-keep public class com.github.ayousanz.piper.PiperConfig { *; }
-keep public class com.github.ayousanz.piper.PiperAudio { *; }
-keep class ai.onnxruntime.** { *; }
-dontwarn ai.onnxruntime.**
```

---

## 8. CI/CD

### 8.1 GitHub Actions ワークフロー

**.github/workflows/android-build.yml:**

```yaml
name: Android Build & Test

on:
  push:
    branches: [dev]
    paths: ['src/android/**', 'src/cpp/**']
  pull_request:
    paths: ['src/android/**', 'src/cpp/**']

jobs:
  build-native:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        abi: [arm64-v8a, armeabi-v7a, x86_64]
    steps:
      - uses: actions/checkout@v4
      - uses: nttld/setup-ndk@v1
        with:
          ndk-version: r27
      - run: scripts/build-android-${{ matrix.abi }}.sh
      - uses: actions/upload-artifact@v4
        with:
          name: native-${{ matrix.abi }}
          path: install-android-${{ matrix.abi }}/lib/*.so

  build-aar:
    needs: build-native
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17' }
      - uses: gradle/actions/setup-gradle@v4
      - uses: actions/download-artifact@v4
        with:
          path: src/android/piper-android/src/main/jniLibs/
          merge-multiple: true
      - run: cd src/android && ./gradlew :piper-android:assembleRelease
      - uses: actions/upload-artifact@v4
        with:
          name: piper-android-aar
          path: src/android/piper-android/build/outputs/aar/*.aar

  test:
    needs: build-aar
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17' }
      - uses: gradle/actions/setup-gradle@v4
      - run: cd src/android && ./gradlew testDebugUnitTest
```

### 8.2 Maven Central公開ワークフロー

```yaml
name: Publish to Maven Central

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: temurin, java-version: '17' }
      - uses: gradle/actions/setup-gradle@v4
      - run: cd src/android && ./gradlew publishAndReleaseToMavenCentral
        env:
          ORG_GRADLE_PROJECT_mavenCentralUsername: ${{ secrets.MAVEN_CENTRAL_USERNAME }}
          ORG_GRADLE_PROJECT_mavenCentralPassword: ${{ secrets.MAVEN_CENTRAL_PASSWORD }}
          ORG_GRADLE_PROJECT_signingInMemoryKey: ${{ secrets.GPG_SIGNING_KEY }}
          ORG_GRADLE_PROJECT_signingInMemoryKeyPassword: ${{ secrets.GPG_SIGNING_PASSWORD }}
```

**Maven座標:** `io.github.ayousanz:piper-android:1.0.0`

---

## 9. ONNX Runtime Android仕様

| 項目 | 値 |
|------|-----|
| Maven依存 | `com.microsoft.onnxruntime:onnxruntime-android:1.24.2` |
| 対応ABI | arm64-v8a, armeabi-v7a, x86_64 |
| 最小Android | API 24 (Android 7.0) |
| FP16サポート | CPUバックエンドでロード可 (内部FP32キャスト) |
| NNAPIサポート | API 27+ で利用可能 |
| 推奨スレッド数 | 2-4 (モバイル) |

**セッション作成例 (Kotlin/Java API):**

```kotlin
val env = OrtEnvironment.getEnvironment()
val options = OrtSession.SessionOptions().apply {
    setIntraOpNumThreads(4)
    setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT)
}
val session = env.createSession(modelBytes, options)
```

---

## 10. Phonemizer対応状況

piper-plusのC++コアには6言語のPhonemizerが実装済み。JNI経由でそのまま利用する。

| 言語 | C++実装 | 依存 | 状態 |
|------|---------|------|------|
| ja | `openjtalk_phonemize.cpp` | OpenJTalk (C) | 実装済み |
| en | `english_phonemize.cpp` | CMU dict G2P (内蔵) | 実装済み |
| zh | `chinese_phonemize.cpp` | pypinyin互換 (内蔵) | 実装済み |
| es | `spanish_phonemize.cpp` | 規則ベース (依存なし) | 実装済み |
| fr | `french_phonemize.cpp` | 規則ベース (依存なし) | 実装済み |
| pt | `portuguese_phonemize.cpp` | 規則ベース (依存なし) | 実装済み |

**APKサイズへの影響:**
- OpenJTalk辞書: ~3-5MB
- G2P辞書 (CMU dict): ~1MB
- 中国語辞書: ~2MB
- 合計: ~6-8MB (JNIライブラリ含む)

---

## 11. 実装フェーズ

### Phase 1: プロジェクト構造・ビルドシステム

- [ ] `src/android/` ディレクトリ作成
- [ ] Gradle Kotlin DSL設定 (settings.gradle.kts, build.gradle.kts)
- [ ] ONNX Runtime Android AAR依存追加
- [ ] CMakeLists.txt: Android JNIビルド対応追加
- [ ] クロスコンパイルスクリプト (arm64-v8a, armeabi-v7a, x86_64)
- [ ] GitHub Actions: ネイティブビルド + AARビルド + テスト

### Phase 2: JNIブリッジ + コア推論

- [ ] `piper_jni.cpp`: JNIエントリーポイント実装
  - `nativeCreate(modelPath, configPath)` → jlong
  - `nativeSynthesize(handle, text, language, speakerId)` → jshortArray
  - `nativeSynthesizeStreaming(handle, text, language, speakerId, callback)`
  - `nativeDestroy(handle)`
- [ ] Kotlin API: `PiperTts`, `PiperConfig`, `PiperAudio`
- [ ] Speaker ID / Language ID 対応
- [ ] Prosody features 対応
- [ ] ユニットテスト

### Phase 3: Android統合

- [ ] `PiperTtsService` (TextToSpeechService) 実装
- [ ] AndroidManifest.xml TTSエンジン登録
- [ ] AudioTrackリアルタイム再生
- [ ] Kotlin Coroutines非同期推論 (viewModelScope統合)
- [ ] ストリーミング出力 (Flow + buffer)

### Phase 4: サンプルアプリ

- [ ] Jetpack Composeサンプルアプリ
- [ ] テキスト入力 → 音声合成 → 再生のデモ
- [ ] 言語切り替え・話者切り替えUI

### Phase 5: 配布

- [ ] Maven Central公開設定 (vanniktech plugin)
- [ ] GPG署名設定
- [ ] GitHub Actions自動リリースワークフロー
- [ ] KDoc APIドキュメント
- [ ] ProGuard/R8設定

---

## 12. 技術仕様サマリー

| 項目 | 値 |
|------|-----|
| 言語 | Kotlin (Java互換) |
| 最小SDK | API 24 (Android 7.0) |
| ONNX Runtime | `onnxruntime-android:1.24.2` |
| ビルドシステム | Gradle Kotlin DSL |
| ネイティブビルド | CMake + NDK r27 (分離ビルド) |
| 配布 | Maven Central (AAR) |
| 対応ABI | arm64-v8a, armeabi-v7a, x86_64 |
| 対応言語 | 6言語 (ja, en, zh, es, fr, pt) |
| 音声フォーマット | 22050 Hz / 16-bit signed / Mono |
| TTSエンジン | TextToSpeechService対応 |
| 非同期 | Kotlin Coroutines (suspend + Flow) |
| Maven座標 | `io.github.ayousanz:piper-android` |

---

## 13. 参考実装

| プロジェクト | 参考ポイント |
|------------|-------------|
| [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | C++ → JNI → Kotlin パターン、TTS Engine実装 |
| [ONNX Runtime Android](https://onnxruntime.ai/docs/get-started/with-java.html) | Java API、セッション管理 |
| [eSpeak NG Android](https://github.com/espeak-ng/espeak-ng) | TextToSpeechService実装 |
| [RHVoice Android](https://github.com/RHVoice/RHVoice) | 多言語TTS Engine、モデルダウンロード管理 |
| [AOSP RobotSpeakTtsService](https://android.googlesource.com/platform/development/+/master/samples/TtsEngine/) | 公式最小TTS Engine実装 |
