# Android TTS エンジン 実装計画 (M1〜M3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Android のシステム TTS エンジンとして piper-plus を登録し、6 言語 (ja/en/zh/es/fr/pt) の音声合成を任意のアプリから利用できるようにする。

**Architecture:** 既存の `android/piper-plus` AAR (JNI → `libpiper_plus.so`) に依存する application モジュール `android/piper-plus-tts-engine` を新設する。Kotlin 側は `TextToSpeechService` の実装とパラメータ変換に限定し、G2P・推論は C++ 実装をそのまま使う。合成オプションを JNI 境界に通すため、AAR 側にも拡張を加える。

**Tech Stack:** Kotlin / Android Gradle Plugin / NDK (CMake) / JUnit 4 / ONNX Runtime 1.20.0

**設計書:** [android-tts-engine-design.md](./android-tts-engine-design.md)

## Global Constraints

- `minSdk = 24`、`compileSdk = 35` (既存 `android/piper-plus` と揃える)
- Java / Kotlin JVM target は `11`
- 対応 ABI は `arm64-v8a` / `armeabi-v7a` / `x86_64` の 3 つ
- 64-bit ABI は 16 KB page alignment (`-Wl,-z,max-page-size=16384`) が必須。`armeabi-v7a` は対象外
- ONNX Runtime のバージョンは `1.20.0` (`.github/workflows/android-build.yml` の `ONNXRUNTIME_VERSION` と一致させる)
- `language_id_map` は全 6lang モデル共通で `{ja:0, en:1, zh:2, es:3, fr:4, pt:5}`
- 音声出力は 22050 Hz / PCM 16-bit / mono
- Kotlin のテストは `src/test/java/com/piperplus/tts/` に置く (既存 `piper-plus-g2p` の配置に合わせる)
- Lint は `android/detekt.yml` の設定に従う
- `PiperPlusSynthOptions._reserved[5]` は必ずゼロ埋めする (`src/cpp/piper_plus.h` の規約)

## File Structure

| ファイル | 責務 |
|---------|------|
| `android/settings.gradle.kts` | `:piper-plus-tts-engine` を include (修正) |
| `android/piper-plus-tts-engine/build.gradle.kts` | application モジュールのビルド定義 (新規) |
| `.../src/main/AndroidManifest.xml` | `TTS_SERVICE` intent-filter とエンジン宣言 (新規) |
| `.../src/main/res/xml/tts_engine.xml` | TTS エンジンのメタデータ (新規) |
| `.../src/main/java/com/piperplus/tts/LocaleResolver.kt` | ISO-3 言語コード → `language_id` / 可用性判定。Android 依存なし (新規) |
| `.../src/main/java/com/piperplus/tts/SynthesisParams.kt` | `speechRate` → `lengthScale` 変換。Android 依存なし (新規) |
| `.../src/main/java/com/piperplus/tts/model/ModelPaths.kt` | モデル・辞書のパス解決とインストール判定 (新規) |
| `.../src/main/java/com/piperplus/tts/EngineHolder.kt` | `PiperPlus` インスタンスの生成・キャッシュ・破棄 (新規) |
| `.../src/main/java/com/piperplus/tts/PiperPlusTtsService.kt` | `TextToSpeechService` 実装 (新規) |
| `android/piper-plus/src/main/cpp/piper_plus_jni.cpp` | 合成オプション付き JNI 関数を追加 (修正) |
| `android/piper-plus/src/main/java/com/piperplus/PiperPlusNative.kt` | `external fun` を追加 (修正) |
| `android/piper-plus/src/main/java/com/piperplus/SynthOptions.kt` | 合成オプションのデータクラス (新規) |
| `android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt` | オプション付き `synthesize` / `synthesizeStream` を追加 (修正) |
| `android/piper-plus/build.gradle.kts` | `abiFilters` を 3 ABI に拡張 (修正) |
| `.github/workflows/android-build.yml` | AAR + APK ビルド job を追加 (修正) |

---

## Task 1: TTS エンジンモジュールの雛形

**Files:**
- Modify: `android/settings.gradle.kts`
- Create: `android/piper-plus-tts-engine/build.gradle.kts`
- Create: `android/piper-plus-tts-engine/src/main/AndroidManifest.xml`
- Create: `android/piper-plus-tts-engine/src/main/res/xml/tts_engine.xml`
- Create: `android/piper-plus-tts-engine/proguard-rules.pro`
- Test: `android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/ModuleSanityTest.kt`

**Interfaces:**
- Consumes: なし (最初のタスク)
- Produces: Gradle モジュール `:piper-plus-tts-engine`、パッケージ `com.piperplus.tts`

- [ ] **Step 1: モジュールを settings.gradle.kts に登録**

`android/settings.gradle.kts` の末尾を次のように変更する。

```kotlin
rootProject.name = "piper-plus-android"
include(":piper-plus")
include(":piper-plus-g2p")
include(":piper-plus-tts-engine")
```

- [ ] **Step 2: build.gradle.kts を作成**

`android/piper-plus-tts-engine/build.gradle.kts`:

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.piperplus.tts"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.piperplus.tts"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = "11"
    }

    testOptions {
        // android.jar のスタブメソッドが例外を投げず既定値を返すようにする。
        // LocaleResolver のテストで TextToSpeech の定数を参照するため必要。
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(project(":piper-plus"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    testImplementation("junit:junit:4.13.2")
}
```

- [ ] **Step 3: proguard-rules.pro を作成**

`android/piper-plus-tts-engine/proguard-rules.pro`:

```proguard
# JNI から参照されるクラスは難読化しない
-keep class com.piperplus.PiperPlusNative { *; }
-keep class com.piperplus.PiperPlusException { *; }
```

- [ ] **Step 4: AndroidManifest.xml を作成**

`android/piper-plus-tts-engine/src/main/AndroidManifest.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <application
        android:allowBackup="false"
        android:label="piper-plus TTS">

        <service
            android:name=".PiperPlusTtsService"
            android:exported="true"
            android:label="piper-plus TTS">
            <intent-filter>
                <action android:name="android.intent.action.TTS_SERVICE" />
                <category android:name="android.intent.category.DEFAULT" />
            </intent-filter>
            <meta-data
                android:name="android.speech.tts"
                android:resource="@xml/tts_engine" />
        </service>
    </application>
</manifest>
```

- [ ] **Step 5: tts_engine.xml を作成**

`android/piper-plus-tts-engine/src/main/res/xml/tts_engine.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<tts-engine xmlns:android="http://schemas.android.com/apk/res/android" />
```

> `android:settingsActivity` は設定画面を実装する後続計画 (M4) で追加する。

- [ ] **Step 6: .gitignore を更新**

`.gitignore` には `android/piper-plus-g2p/` のビルド成果物しか登録されていない
(262-273 行)。同じブロックの末尾に、`piper-plus` / `piper-plus-tts-engine` の
成果物と、マシン固有の SDK パスを追加する。

```gitignore
android/piper-plus/build/
android/piper-plus/.cxx/
# CI が build-android artifact から配置する native ライブラリ (Task 9)
android/piper-plus/src/main/jniLibs/
android/piper-plus-tts-engine/build/
android/piper-plus-tts-engine/.cxx/
# Android SDK の場所はマシン固有。コミットしない
android/local.properties
```

- [ ] **Step 7: サニティテストを書く**

`android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/ModuleSanityTest.kt`:

```kotlin
package com.piperplus.tts

import org.junit.Assert.assertTrue
import org.junit.Test

/** モジュールの JVM テストハーネスが動作することを確認する。 */
class ModuleSanityTest {
    @Test
    fun `unit test harness runs`() {
        assertTrue(true)
    }
}
```

- [ ] **Step 8: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest`
Expected: PASS (1 test)

このタスクの時点では Service クラスがまだ存在しないため、`assembleDebug` は失敗する。ユニットテストのみ実行すること。

> **前提**: Android Gradle Plugin 8.x は JDK 17 以上を要求する。`java -version` が
> 1.8 を返す環境では `brew install --cask temurin@17` などで JDK 17 を入れ、
> `JAVA_HOME=$(/usr/libexec/java_home -v 17)` を設定してから実行する。
> Android SDK の場所は `android/local.properties` に `sdk.dir=/path/to/sdk` として
> 書くか、`ANDROID_HOME` を設定する。

- [ ] **Step 9: コミット**

```bash
git add .gitignore android/settings.gradle.kts android/piper-plus-tts-engine
git commit -m "feat(android): TTS エンジンモジュールの雛形を追加"
```

---

## Task 2: LocaleResolver

**Files:**
- Create: `android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/LocaleResolver.kt`
- Test: `android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/LocaleResolverTest.kt`

**Interfaces:**
- Consumes: Task 1 のモジュール
- Produces:
  - `LocaleResolver.languageIdOf(iso3Language: String): Int?`
  - `LocaleResolver.availability(iso3Language: String, modelInstalled: Boolean): Int`
  - `LocaleResolver.SUPPORTED_ISO3: List<String>`

- [ ] **Step 1: 失敗するテストを書く**

`android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/LocaleResolverTest.kt`:

```kotlin
package com.piperplus.tts

import android.speech.tts.TextToSpeech
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class LocaleResolverTest {

    @Test
    fun `maps all six supported languages to their language ids`() {
        assertEquals(0, LocaleResolver.languageIdOf("jpn"))
        assertEquals(1, LocaleResolver.languageIdOf("eng"))
        assertEquals(2, LocaleResolver.languageIdOf("zho"))
        assertEquals(3, LocaleResolver.languageIdOf("spa"))
        assertEquals(4, LocaleResolver.languageIdOf("fra"))
        assertEquals(5, LocaleResolver.languageIdOf("por"))
    }

    @Test
    fun `accepts cmn as an alias for zho`() {
        assertEquals(2, LocaleResolver.languageIdOf("cmn"))
    }

    @Test
    fun `is case insensitive`() {
        assertEquals(0, LocaleResolver.languageIdOf("JPN"))
        assertEquals(1, LocaleResolver.languageIdOf("Eng"))
    }

    @Test
    fun `returns null for unsupported languages`() {
        assertNull(LocaleResolver.languageIdOf("kor"))
        assertNull(LocaleResolver.languageIdOf("swe"))
        assertNull(LocaleResolver.languageIdOf(""))
    }

    @Test
    fun `reports NOT_SUPPORTED for an unsupported language even when a model exists`() {
        assertEquals(
            TextToSpeech.LANG_NOT_SUPPORTED,
            LocaleResolver.availability("kor", modelInstalled = true),
        )
    }

    @Test
    fun `reports MISSING_DATA when the language is supported but no model is installed`() {
        assertEquals(
            TextToSpeech.LANG_MISSING_DATA,
            LocaleResolver.availability("jpn", modelInstalled = false),
        )
    }

    @Test
    fun `reports AVAILABLE when the language is supported and a model is installed`() {
        assertEquals(
            TextToSpeech.LANG_AVAILABLE,
            LocaleResolver.availability("jpn", modelInstalled = true),
        )
    }

    @Test
    fun `exposes exactly the six supported iso3 codes`() {
        assertEquals(
            listOf("jpn", "eng", "zho", "spa", "fra", "por"),
            LocaleResolver.SUPPORTED_ISO3,
        )
    }
}
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*LocaleResolverTest*'`
Expected: FAIL — `Unresolved reference: LocaleResolver` でコンパイルエラー

- [ ] **Step 3: 最小実装を書く**

`android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/LocaleResolver.kt`:

```kotlin
package com.piperplus.tts

import android.speech.tts.TextToSpeech

/**
 * Android の ISO-639-3 言語コードを piper-plus の `language_id` に対応付ける。
 *
 * `language_id_map` は 6lang モデル共通で `{ja:0, en:1, zh:2, es:3, fr:4, pt:5}`。
 * 1 つの 6lang モデルが 6 言語すべてを話すため、言語切替はモデルの入れ替えでは
 * なく `language_id` の変更で行う。
 *
 * 国・方言コードは区別しない。`ja-JP` と `ja` は同一に扱うため
 * `LANG_COUNTRY_AVAILABLE` は返さない。
 */
object LocaleResolver {

    /** ISO-639-3 → language_id。`cmn` は Android が返す `zho` の別名として受理する。 */
    private val ISO3_TO_LANGUAGE_ID: Map<String, Int> = mapOf(
        "jpn" to 0,
        "eng" to 1,
        "zho" to 2,
        "cmn" to 2,
        "spa" to 3,
        "fra" to 4,
        "por" to 5,
    )

    /** `onGetLanguage` などで提示する代表コード (`cmn` の別名は含めない)。 */
    val SUPPORTED_ISO3: List<String> = listOf("jpn", "eng", "zho", "spa", "fra", "por")

    /** 対応言語なら `language_id`、非対応なら null を返す。 */
    fun languageIdOf(iso3Language: String): Int? =
        ISO3_TO_LANGUAGE_ID[iso3Language.lowercase()]

    /**
     * `TextToSpeechService.onIsLanguageAvailable` / `onLoadLanguage` の戻り値を求める。
     *
     * @param modelInstalled モデルと辞書が端末に揃っているか
     */
    fun availability(iso3Language: String, modelInstalled: Boolean): Int = when {
        languageIdOf(iso3Language) == null -> TextToSpeech.LANG_NOT_SUPPORTED
        !modelInstalled -> TextToSpeech.LANG_MISSING_DATA
        else -> TextToSpeech.LANG_AVAILABLE
    }
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*LocaleResolverTest*'`
Expected: PASS (8 tests)

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/LocaleResolver.kt \
        android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/LocaleResolverTest.kt
git commit -m "feat(android): ISO-3 言語コードから language_id を解決する LocaleResolver を追加"
```

---

## Task 3: SynthesisParams (speechRate → lengthScale)

**Files:**
- Create: `android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/SynthesisParams.kt`
- Test: `android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/SynthesisParamsTest.kt`

**Interfaces:**
- Consumes: Task 1 のモジュール
- Produces: `SynthesisParams.lengthScaleOf(speechRate: Int): Float`

Android TTS は `SynthesisRequest.speechRate` を「100 = 等速」の整数で渡す。piper-plus の `length_scale` は「大きいほど遅い」ため、逆数関係になる。

- [ ] **Step 1: 失敗するテストを書く**

`android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/SynthesisParamsTest.kt`:

```kotlin
package com.piperplus.tts

import org.junit.Assert.assertEquals
import org.junit.Test

class SynthesisParamsTest {

    @Test
    fun `maps the default speech rate to a unit length scale`() {
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(100), TOLERANCE)
    }

    @Test
    fun `doubling the speech rate halves the length scale`() {
        assertEquals(0.5f, SynthesisParams.lengthScaleOf(200), TOLERANCE)
    }

    @Test
    fun `halving the speech rate doubles the length scale`() {
        assertEquals(2.0f, SynthesisParams.lengthScaleOf(50), TOLERANCE)
    }

    @Test
    fun `clamps the maximum android speech rate`() {
        assertEquals(0.25f, SynthesisParams.lengthScaleOf(400), TOLERANCE)
    }

    @Test
    fun `falls back to a unit length scale for non-positive rates`() {
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(0), TOLERANCE)
        assertEquals(1.0f, SynthesisParams.lengthScaleOf(-10), TOLERANCE)
    }

    private companion object {
        const val TOLERANCE = 1e-6f
    }
}
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*SynthesisParamsTest*'`
Expected: FAIL — `Unresolved reference: SynthesisParams`

- [ ] **Step 3: 最小実装を書く**

`android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/SynthesisParams.kt`:

```kotlin
package com.piperplus.tts

/** Android TTS の合成パラメータを piper-plus の scales に変換する。 */
object SynthesisParams {

    /** Android TTS が等速を表す値 (`SynthesisRequest.speechRate`)。 */
    private const val NORMAL_SPEECH_RATE = 100

    /**
     * `speechRate` を piper-plus の `length_scale` に変換する。
     *
     * Android は「大きいほど速い」、piper-plus の `length_scale` は
     * 「大きいほど遅い」ため逆数を取る。
     * 0 以下は不正値として等速にフォールバックする (ゼロ除算の回避も兼ねる)。
     */
    fun lengthScaleOf(speechRate: Int): Float =
        if (speechRate <= 0) 1.0f else NORMAL_SPEECH_RATE.toFloat() / speechRate.toFloat()
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*SynthesisParamsTest*'`
Expected: PASS (5 tests)

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/SynthesisParams.kt \
        android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/SynthesisParamsTest.kt
git commit -m "feat(android): speechRate から length_scale への変換を追加"
```

---

## Task 4: ModelPaths

**Files:**
- Create: `android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/model/ModelPaths.kt`
- Test: `android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/model/ModelPathsTest.kt`

**Interfaces:**
- Consumes: Task 1 のモジュール
- Produces:
  - `ModelPaths(filesDir: File)`
  - `.modelDir(modelId: String): File` / `.modelFile(modelId)` / `.configFile(modelId)` / `.dictDir(): File`
  - `.isInstalled(modelId: String): Boolean`
  - `ModelPaths.DEFAULT_MODEL_ID: String` = `"css10-6lang"`

- [ ] **Step 1: 失敗するテストを書く**

`android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/model/ModelPathsTest.kt`:

```kotlin
package com.piperplus.tts.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ModelPathsTest {

    @get:Rule
    val temp = TemporaryFolder()

    @Test
    fun `resolves model and config paths under a per-model directory`() {
        val paths = ModelPaths(temp.root)
        assertEquals(
            "${temp.root}/models/my-voice",
            paths.modelDir("my-voice").path,
        )
        assertEquals(
            "${temp.root}/models/my-voice/model.onnx",
            paths.modelFile("my-voice").path,
        )
        assertEquals(
            "${temp.root}/models/my-voice/model.onnx.json",
            paths.configFile("my-voice").path,
        )
    }

    @Test
    fun `resolves the dictionary directory at the files root`() {
        val paths = ModelPaths(temp.root)
        assertEquals("${temp.root}/open_jtalk_dic", paths.dictDir().path)
    }

    @Test
    fun `reports not installed when nothing exists`() {
        assertFalse(ModelPaths(temp.root).isInstalled("my-voice"))
    }

    @Test
    fun `reports not installed when the config is missing`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.dictDir().mkdirs()
        assertFalse(paths.isInstalled("my-voice"))
    }

    @Test
    fun `reports not installed when the dictionary is missing`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.configFile("my-voice").writeText("{}")
        assertFalse(paths.isInstalled("my-voice"))
    }

    @Test
    fun `reports installed when model config and dictionary all exist`() {
        val paths = ModelPaths(temp.root)
        paths.modelDir("my-voice").mkdirs()
        paths.modelFile("my-voice").writeText("onnx")
        paths.configFile("my-voice").writeText("{}")
        paths.dictDir().mkdirs()
        assertTrue(paths.isInstalled("my-voice"))
    }

    @Test
    fun `exposes the default model id`() {
        assertEquals("css10-6lang", ModelPaths.DEFAULT_MODEL_ID)
    }
}
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*ModelPathsTest*'`
Expected: FAIL — `Unresolved reference: ModelPaths`

- [ ] **Step 3: 最小実装を書く**

`android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/model/ModelPaths.kt`:

```kotlin
package com.piperplus.tts.model

import java.io.File

/**
 * 端末上のモデル・辞書のパスを解決する。
 *
 * 配置は次の通り (すべて内部ストレージ `context.filesDir` 配下):
 * ```
 * models/<model-id>/model.onnx
 * models/<model-id>/model.onnx.json
 * open_jtalk_dic/
 * ```
 *
 * @param filesDir アプリの内部ストレージルート (`context.filesDir`)
 */
class ModelPaths(private val filesDir: File) {

    fun modelDir(modelId: String): File = File(File(filesDir, MODELS_DIR), modelId)

    fun modelFile(modelId: String): File = File(modelDir(modelId), MODEL_FILE)

    fun configFile(modelId: String): File = File(modelDir(modelId), CONFIG_FILE)

    fun dictDir(): File = File(filesDir, DICT_DIR)

    /**
     * モデル・設定・辞書がすべて揃っているか。
     *
     * 辞書は日本語合成にのみ必要だが、初版では言語によらず必須として扱う
     * (言語ごとの遅延取得は複雑さに見合わない)。
     */
    fun isInstalled(modelId: String): Boolean =
        modelFile(modelId).isFile && configFile(modelId).isFile && dictDir().isDirectory

    companion object {
        /**
         * 初版で使う既定モデル (6 言語すべてを話す)。
         *
         * `piper-core` の組込みレジストリ (`model_download.rs:builtin_registry`)
         * のモデル名と一致させてある。
         */
        const val DEFAULT_MODEL_ID = "css10-6lang"

        private const val MODELS_DIR = "models"
        private const val MODEL_FILE = "model.onnx"
        private const val CONFIG_FILE = "model.onnx.json"
        private const val DICT_DIR = "open_jtalk_dic"
    }
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*ModelPathsTest*'`
Expected: PASS (7 tests)

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/model/ModelPaths.kt \
        android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/model/ModelPathsTest.kt
git commit -m "feat(android): モデルと辞書のパス解決を追加"
```

---

## Task 5: AAR に合成オプションを追加 (Kotlin 側)

**Files:**
- Create: `android/piper-plus/src/main/java/com/piperplus/SynthOptions.kt`
- Test: `android/piper-plus/src/test/java/com/piperplus/SynthOptionsTest.kt`

**Interfaces:**
- Consumes: なし
- Produces: `com.piperplus.SynthOptions(speakerId, languageId, lengthScale, noiseScale, noiseW, sentenceSilenceSec)`

既定値は `src/cpp/piper_plus.h` の `PiperPlusSynthOptions` のドキュメントに合わせる (`language_id = -1` は auto-detect)。

- [ ] **Step 1: 失敗するテストを書く**

`android/piper-plus/src/test/java/com/piperplus/SynthOptionsTest.kt`:

```kotlin
package com.piperplus

import org.junit.Assert.assertEquals
import org.junit.Test

class SynthOptionsTest {

    @Test
    fun `defaults match the C API defaults`() {
        val options = SynthOptions()
        assertEquals(0, options.speakerId)
        assertEquals(-1, options.languageId)
        assertEquals(1.0f, options.lengthScale, TOLERANCE)
        assertEquals(0.4f, options.noiseScale, TOLERANCE)
        assertEquals(0.5f, options.noiseW, TOLERANCE)
        assertEquals(0.2f, options.sentenceSilenceSec, TOLERANCE)
    }

    @Test
    fun `allows overriding individual fields`() {
        val options = SynthOptions(languageId = 2, lengthScale = 0.5f)
        assertEquals(2, options.languageId)
        assertEquals(0.5f, options.lengthScale, TOLERANCE)
        // 未指定のフィールドは既定値のまま
        assertEquals(0, options.speakerId)
    }

    private companion object {
        const val TOLERANCE = 1e-6f
    }
}
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd android && ./gradlew :piper-plus:testDebugUnitTest --tests '*SynthOptionsTest*'`
Expected: FAIL — `Unresolved reference: SynthOptions`

- [ ] **Step 3: 最小実装を書く**

`android/piper-plus/src/main/java/com/piperplus/SynthOptions.kt`:

```kotlin
package com.piperplus

/**
 * 合成オプション。C API の `PiperPlusSynthOptions` に 1:1 対応する。
 *
 * 既定値は `src/cpp/piper_plus.h` の規定に合わせてある。
 *
 * @param speakerId          話者インデックス (0 始まり)
 * @param languageId         言語インデックス。-1 で自動判定
 * @param lengthScale        大きいほど遅い
 * @param noiseScale         VITS noise_scale
 * @param noiseW             VITS noise_w
 * @param sentenceSilenceSec 文間の無音 (秒)
 */
data class SynthOptions(
    val speakerId: Int = 0,
    val languageId: Int = -1,
    val lengthScale: Float = 1.0f,
    val noiseScale: Float = 0.4f,
    val noiseW: Float = 0.5f,
    val sentenceSilenceSec: Float = 0.2f,
)
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus:testDebugUnitTest --tests '*SynthOptionsTest*'`
Expected: PASS (2 tests)

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus/src/main/java/com/piperplus/SynthOptions.kt \
        android/piper-plus/src/test/java/com/piperplus/SynthOptionsTest.kt
git commit -m "feat(android): 合成オプションのデータクラスを追加"
```

---

## Task 6: JNI に合成オプションを通す

**Files:**
- Modify: `android/piper-plus/src/main/cpp/piper_plus_jni.cpp`
- Modify: `android/piper-plus/src/main/java/com/piperplus/PiperPlusNative.kt`
- Modify: `android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt:158-206`

**Interfaces:**
- Consumes: `SynthOptions` (Task 5)
- Produces:
  - `PiperPlusNative.nativeSynthesizeWithOptions(handle, text, speakerId, languageId, lengthScale, noiseScale, noiseW, sentenceSilenceSec): ShortArray`
  - `PiperPlusNative.nativeSynthStartWithOptions(handle, text, speakerId, languageId, lengthScale, noiseScale, noiseW, sentenceSilenceSec): Int`
  - `PiperPlus.synthesize(text: String, options: SynthOptions): ShortArray`
  - `PiperPlus.synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray>`

既存の `synthesize(text, speakerId)` / `synthesizeStream(text, speakerId)` は後方互換のため残す。

- [ ] **Step 1: JNI 関数を追加**

`android/piper-plus/src/main/cpp/piper_plus_jni.cpp` の `nativeSynthesize` (191-223 行) の直後に追加する。既存の関数は変更しない。

```cpp
/**
 * Synthesis with explicit options.
 *
 * Mirrors nativeSynthesize but lets the caller set every field of
 * PiperPlusSynthOptions except speaker_embedding (voice cloning is not
 * exposed through the Android TTS engine).
 */
JNIEXPORT jshortArray JNICALL
Java_com_piperplus_PiperPlusNative_nativeSynthesizeWithOptions(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring text,
        jint speakerId,
        jint languageId,
        jfloat lengthScale,
        jfloat noiseScale,
        jfloat noiseW,
        jfloat sentenceSilenceSec) {

    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    JNIStringGuard textUtf8(env, text);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return nullptr; }

    // piper_plus_default_options() zeroes _reserved[5] as the header requires.
    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id           = static_cast<int32_t>(speakerId);
    opts.language_id          = static_cast<int32_t>(languageId);
    opts.length_scale         = lengthScale;
    opts.noise_scale          = noiseScale;
    opts.noise_w              = noiseW;
    opts.sentence_silence_sec = sentenceSilenceSec;

    float   *samples     = nullptr;
    int32_t  numSamples  = 0;
    int32_t  sampleRate  = 0;

    PiperPlusStatus status = piper_plus_synthesize(
            engine, textUtf8.get(), &opts,
            &samples, &numSamples, &sampleRate);

    if (status != PIPER_PLUS_OK) {
        throwPiperException(env, status);
        return nullptr;
    }

    jshortArray result = floatsToShortArray(env, samples, numSamples);
    piper_plus_free_audio(samples);
    return result;
}
```

- [ ] **Step 2: ストリーミング開始の JNI 関数を追加**

`nativeSynthStart` (229-252 行) の直後に追加する。既存の `nativeSynthStart` は変更しない。
チャンク取得は `nativeSynthNext` を共用するため、追加は開始側だけでよい。

```cpp
/**
 * Start iterator-based streaming synthesis with explicit options.
 * Returns the sample rate (> 0) on success, or throws.
 *
 * Chunk retrieval is shared with nativeSynthNext -- only the start call
 * needs an options-aware variant.
 */
JNIEXPORT jint JNICALL
Java_com_piperplus_PiperPlusNative_nativeSynthStartWithOptions(
        JNIEnv *env,
        jobject /* thiz */,
        jlong handle,
        jstring text,
        jint speakerId,
        jint languageId,
        jfloat lengthScale,
        jfloat noiseScale,
        jfloat noiseW,
        jfloat sentenceSilenceSec) {

    auto *engine = reinterpret_cast<PiperPlusEngine *>(handle);
    JNIStringGuard textUtf8(env, text);
    if (!textUtf8) { throwPiperException(env, PIPER_PLUS_ERR); return 0; }

    PiperPlusSynthOptions opts = piper_plus_default_options();
    opts.speaker_id           = static_cast<int32_t>(speakerId);
    opts.language_id          = static_cast<int32_t>(languageId);
    opts.length_scale         = lengthScale;
    opts.noise_scale          = noiseScale;
    opts.noise_w              = noiseW;
    opts.sentence_silence_sec = sentenceSilenceSec;

    PiperPlusStatus status = piper_plus_synth_start(engine, textUtf8.get(), &opts);

    // JNIStringGuard destructor releases textUtf8 here.

    if (status != PIPER_PLUS_OK) {
        throwPiperException(env, status);
        return 0;
    }
    return piper_plus_sample_rate(engine);
}
```

- [ ] **Step 3: Kotlin の external 宣言を追加**

`android/piper-plus/src/main/java/com/piperplus/PiperPlusNative.kt` の `nativeSynthesize` 宣言の直後に追加する。

```kotlin
    /**
     * Synthesize with explicit options.
     *
     * @return PCM 16-bit samples.
     */
    external fun nativeSynthesizeWithOptions(
        handle: Long,
        text: String,
        speakerId: Int,
        languageId: Int,
        lengthScale: Float,
        noiseScale: Float,
        noiseW: Float,
        sentenceSilenceSec: Float,
    ): ShortArray

    /**
     * Start streaming synthesis with explicit options.
     *
     * @return Sample rate in Hz.
     */
    external fun nativeSynthStartWithOptions(
        handle: Long,
        text: String,
        speakerId: Int,
        languageId: Int,
        lengthScale: Float,
        noiseScale: Float,
        noiseW: Float,
        sentenceSilenceSec: Float,
    ): Int
```

- [ ] **Step 4: 高レベル API を追加**

`android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt` の既存 `synthesize` (158 行) と `synthesizeStream` (182 行) を残したまま、オーバーロードを追加する。

```kotlin
    /**
     * Synthesize text to audio in one shot with explicit options.
     *
     * @param text    Text to synthesize (UTF-8). May contain multiple sentences.
     * @param options Synthesis options (language, speed, noise scales).
     * @return PCM 16-bit audio samples at [sampleRate] Hz.
     * @throws PiperPlusException on synthesis failure.
     * @throws IllegalStateException if the engine has been closed.
     */
    fun synthesize(text: String, options: SynthOptions): ShortArray {
        synchronized(lock) {
            checkNotClosed()
            return PiperPlusNative.nativeSynthesizeWithOptions(
                nativeHandle,
                text,
                options.speakerId,
                options.languageId,
                options.lengthScale,
                options.noiseScale,
                options.noiseW,
                options.sentenceSilenceSec,
            )
        }
    }

    /**
     * Synthesize text as a [Flow] of chunks with explicit options.
     *
     * Semantics match [synthesizeStream] (String, Int): one chunk per sentence,
     * cancellation-safe via try-finally, collected on [Dispatchers.IO].
     *
     * @param text    Text to synthesize (UTF-8). Will be split into sentences.
     * @param options Synthesis options (language, speed, noise scales).
     * @return Cold [Flow] of PCM 16-bit audio chunks.
     */
    fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> = flow {
        synchronized(lock) {
            checkNotClosed()
            check(!synthesizing) { "A streaming synthesis is already in progress" }
            synthesizing = true
        }
        try {
            synchronized(lock) {
                PiperPlusNative.nativeSynthStartWithOptions(
                    nativeHandle,
                    text,
                    options.speakerId,
                    options.languageId,
                    options.lengthScale,
                    options.noiseScale,
                    options.noiseW,
                    options.sentenceSilenceSec,
                )
            }

            while (true) {
                coroutineContext.ensureActive()
                val chunk = synchronized(lock) {
                    PiperPlusNative.nativeSynthNext(nativeHandle)
                } ?: break
                emit(chunk)
            }
        } finally {
            synthesizing = false
        }
    }.flowOn(Dispatchers.IO)
```

- [ ] **Step 5: ビルドが通ることを確認**

Run: `cd android && ./gradlew :piper-plus:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

> ネイティブのビルドには `jniLibs/<abi>/libpiper_plus.so` が必要 (Task 9 で CI から供給する)。ローカルに `.so` がない場合、`assembleDebug` は失敗するが Kotlin のコンパイルは通る。

- [ ] **Step 6: コミット**

```bash
git add android/piper-plus/src/main/cpp/piper_plus_jni.cpp \
        android/piper-plus/src/main/java/com/piperplus/PiperPlusNative.kt \
        android/piper-plus/src/main/java/com/piperplus/PiperPlus.kt
git commit -m "feat(android): JNI 境界に language_id と length_scale を通す"
```

---

## Task 7: EngineHolder

**Files:**
- Create: `android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/EngineHolder.kt`
- Test: `android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/EngineHolderTest.kt`

**Interfaces:**
- Consumes: `ModelPaths` (Task 4)、`com.piperplus.PiperPlus`
- Produces:
  - `EngineHolder(paths: ModelPaths, factory: EngineFactory)`
  - `fun interface EngineFactory { fun create(modelPath: String, configPath: String, dictDir: String): PiperPlusEngine }`
  - `interface PiperPlusEngine { fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray>; fun close() }`
  - `.acquire(modelId: String): PiperPlusEngine`
  - `.release()`

`PiperPlus` を直接持つと JVM テストで JNI ロードが走ってしまうため、`PiperPlusEngine` インターフェース越しに扱い、本番では `PiperPlus` を包む実装を注入する。

- [ ] **Step 1: 失敗するテストを書く**

`android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/EngineHolderTest.kt`:

```kotlin
package com.piperplus.tts

import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flowOf
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class EngineHolderTest {

    @get:Rule
    val temp = TemporaryFolder()

    private class FakeEngine : PiperPlusEngine {
        var closed = false
        override fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray> =
            flowOf(ShortArray(4))
        override fun close() { closed = true }
    }

    private fun installModel(paths: ModelPaths, modelId: String) {
        paths.modelDir(modelId).mkdirs()
        paths.modelFile(modelId).writeText("onnx")
        paths.configFile(modelId).writeText("{}")
        paths.dictDir().mkdirs()
    }

    @Test
    fun `creates an engine on first acquire`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var created = 0
        val holder = EngineHolder(paths) { _, _, _ -> created++; FakeEngine() }

        holder.acquire("voice-a")

        assertEquals(1, created)
    }

    @Test
    fun `reuses the cached engine for the same model`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var created = 0
        val holder = EngineHolder(paths) { _, _, _ -> created++; FakeEngine() }

        val first = holder.acquire("voice-a")
        val second = holder.acquire("voice-a")

        assertEquals(1, created)
        assertSame(first, second)
    }

    @Test
    fun `closes the previous engine when the model changes`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        installModel(paths, "voice-b")
        val engines = mutableListOf<FakeEngine>()
        val holder = EngineHolder(paths) { _, _, _ -> FakeEngine().also { engines.add(it) } }

        holder.acquire("voice-a")
        holder.acquire("voice-b")

        assertEquals(2, engines.size)
        assertTrue(engines[0].closed)
        assertTrue(!engines[1].closed)
    }

    @Test
    fun `passes resolved paths to the factory`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        var seenModel = ""
        var seenConfig = ""
        var seenDict = ""
        val holder = EngineHolder(paths) { model, config, dict ->
            seenModel = model; seenConfig = config; seenDict = dict; FakeEngine()
        }

        holder.acquire("voice-a")

        assertEquals(paths.modelFile("voice-a").absolutePath, seenModel)
        assertEquals(paths.configFile("voice-a").absolutePath, seenConfig)
        assertEquals(paths.dictDir().absolutePath, seenDict)
    }

    @Test(expected = IllegalStateException::class)
    fun `rejects acquiring a model that is not installed`() {
        val holder = EngineHolder(ModelPaths(temp.root)) { _, _, _ -> FakeEngine() }
        holder.acquire("missing-voice")
    }

    @Test
    fun `release closes the cached engine`() {
        val paths = ModelPaths(temp.root)
        installModel(paths, "voice-a")
        val engines = mutableListOf<FakeEngine>()
        val holder = EngineHolder(paths) { _, _, _ -> FakeEngine().also { engines.add(it) } }

        holder.acquire("voice-a")
        holder.release()

        assertTrue(engines[0].closed)
    }

    @Test
    fun `release is idempotent`() {
        val holder = EngineHolder(ModelPaths(temp.root)) { _, _, _ -> FakeEngine() }
        holder.release()
        holder.release()
    }
}
```

- [ ] **Step 2: テストを実行して失敗を確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*EngineHolderTest*'`
Expected: FAIL — `Unresolved reference: EngineHolder`

- [ ] **Step 3: 最小実装を書く**

`android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/EngineHolder.kt`:

```kotlin
package com.piperplus.tts

import com.piperplus.PiperPlus
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import kotlinx.coroutines.flow.Flow

/**
 * 合成エンジンの抽象。
 *
 * [PiperPlus] を直接扱うと JVM ユニットテストで JNI のロードが走るため、
 * この境界を挟んでテスト時に差し替えられるようにする。
 */
interface PiperPlusEngine {
    fun synthesizeStream(text: String, options: SynthOptions): Flow<ShortArray>
    fun close()
}

/** モデルのパスからエンジンを生成する。 */
fun interface EngineFactory {
    fun create(modelPath: String, configPath: String, dictDir: String): PiperPlusEngine
}

/**
 * エンジンインスタンスの生存管理。
 *
 * モデルのロードは数百 ms かかるため、同じモデルの間はインスタンスを再利用する。
 * モデルが切り替わったときは前のインスタンスを確実に閉じる。
 */
class EngineHolder(
    private val paths: ModelPaths,
    private val factory: EngineFactory,
) {
    private val lock = Any()
    private var engine: PiperPlusEngine? = null
    private var loadedModelId: String? = null

    /**
     * 指定モデルのエンジンを取得する。キャッシュがあれば再利用する。
     *
     * @throws IllegalStateException モデルまたは辞書が未インストールの場合
     */
    fun acquire(modelId: String): PiperPlusEngine = synchronized(lock) {
        val cached = engine
        if (cached != null && loadedModelId == modelId) {
            return cached
        }
        check(paths.isInstalled(modelId)) { "Model is not installed: $modelId" }

        cached?.close()
        engine = null
        loadedModelId = null

        val created = factory.create(
            paths.modelFile(modelId).absolutePath,
            paths.configFile(modelId).absolutePath,
            paths.dictDir().absolutePath,
        )
        engine = created
        loadedModelId = modelId
        return created
    }

    /** キャッシュ中のエンジンを解放する。複数回呼んでも安全。 */
    fun release() = synchronized(lock) {
        engine?.close()
        engine = null
        loadedModelId = null
    }
}
```

- [ ] **Step 4: テストを実行して通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest --tests '*EngineHolderTest*'`
Expected: PASS (7 tests)

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/EngineHolder.kt \
        android/piper-plus-tts-engine/src/test/java/com/piperplus/tts/EngineHolderTest.kt
git commit -m "feat(android): エンジンインスタンスの生存管理を追加"
```

---

## Task 8: PiperPlusTtsService

**Files:**
- Create: `android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/PiperPlusTtsService.kt`
- Test: `android/piper-plus-tts-engine/src/androidTest/java/com/piperplus/tts/PiperPlusTtsServiceTest.kt`

**Interfaces:**
- Consumes: `LocaleResolver` (Task 2)、`SynthesisParams` (Task 3)、`ModelPaths` (Task 4)、`SynthOptions` (Task 5)、`EngineHolder` / `PiperPlusEngine` (Task 7)
- Produces: `com.piperplus.tts.PiperPlusTtsService`

- [ ] **Step 1: Service を実装**

`android/piper-plus-tts-engine/src/main/java/com/piperplus/tts/PiperPlusTtsService.kt`:

```kotlin
package com.piperplus.tts

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import android.util.Log
import com.piperplus.PiperPlus
import com.piperplus.SynthOptions
import com.piperplus.tts.model.ModelPaths
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.runBlocking

/**
 * piper-plus を Android のシステム TTS エンジンとして公開する。
 *
 * 6lang モデル 1 つが 6 言語すべてを話すため、言語切替はモデルの入れ替えでは
 * なく [SynthOptions.languageId] の変更で行う。
 */
class PiperPlusTtsService : TextToSpeechService() {

    private lateinit var paths: ModelPaths
    private lateinit var engines: EngineHolder

    /** 現在の合成を中断するためのフラグ。onStop から立てる。 */
    private val stopRequested = AtomicBoolean(false)

    /** 直近に load された言語 (onGetLanguage が返す)。 */
    @Volatile
    private var currentIso3: String = DEFAULT_ISO3

    override fun onCreate() {
        paths = ModelPaths(filesDir)
        engines = EngineHolder(paths) { modelPath, configPath, dictDir ->
            val native = PiperPlus.create(this, modelPath, configPath, dictDir)
            object : PiperPlusEngine {
                override fun synthesizeStream(text: String, options: SynthOptions) =
                    native.synthesizeStream(text, options)
                override fun close() = native.close()
            }
        }
        // super.onCreate() は onGetLanguage を呼ぶため、初期化の後に呼ぶ。
        super.onCreate()
    }

    override fun onDestroy() {
        engines.release()
        super.onDestroy()
    }

    override fun onIsLanguageAvailable(lang: String?, country: String?, variant: String?): Int =
        LocaleResolver.availability(
            lang.orEmpty(),
            paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID),
        )

    override fun onLoadLanguage(lang: String?, country: String?, variant: String?): Int {
        val result = onIsLanguageAvailable(lang, country, variant)
        if (result == TextToSpeech.LANG_AVAILABLE) {
            currentIso3 = lang.orEmpty().lowercase(Locale.ROOT)
        }
        return result
    }

    override fun onGetLanguage(): Array<String> = arrayOf(currentIso3, "", "")

    override fun onStop() {
        stopRequested.set(true)
    }

    override fun onSynthesizeText(request: SynthesisRequest?, callback: SynthesisCallback?) {
        if (request == null || callback == null) return
        stopRequested.set(false)

        val iso3 = request.language.orEmpty()
        val languageId = LocaleResolver.languageIdOf(iso3)
        if (languageId == null) {
            callback.error(TextToSpeech.ERROR_INVALID_REQUEST)
            return
        }
        if (!paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID)) {
            callback.error(TextToSpeech.ERROR_NOT_INSTALLED_YET)
            return
        }

        val text = request.charSequenceText?.toString().orEmpty()
        if (text.isBlank()) {
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)
            callback.done()
            return
        }

        val options = SynthOptions(
            languageId = languageId,
            lengthScale = SynthesisParams.lengthScaleOf(request.speechRate),
        )

        try {
            val engine = engines.acquire(ModelPaths.DEFAULT_MODEL_ID)
            callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, CHANNEL_COUNT)

            runBlocking {
                // takeWhile で打ち切ることで、onStop 後に残りのチャンクを
                // 生成し続けないようにする (collect 内の早期 return では
                // 上流の生成が止まらない)。
                engine.synthesizeStream(text, options)
                    .takeWhile { !stopRequested.get() }
                    .collect { chunk -> emitChunk(callback, chunk) }
            }
            callback.done()
        } catch (e: Exception) {
            // ネイティブ層の失敗でサービスを落とさない。
            Log.e(TAG, "Synthesis failed", e)
            callback.error(TextToSpeech.ERROR_SERVICE)
        }
    }

    /**
     * PCM チャンクを [SynthesisCallback.getMaxBufferSize] 以下に分割して渡す。
     *
     * ShortArray を little-endian の ByteArray に詰め替える。
     */
    private fun emitChunk(callback: SynthesisCallback, chunk: ShortArray) {
        val bytes = ByteArray(chunk.size * BYTES_PER_SAMPLE)
        for (i in chunk.indices) {
            val value = chunk[i].toInt()
            bytes[i * BYTES_PER_SAMPLE] = (value and 0xFF).toByte()
            bytes[i * BYTES_PER_SAMPLE + 1] = ((value shr 8) and 0xFF).toByte()
        }

        val maxBufferSize = callback.maxBufferSize
        var offset = 0
        while (offset < bytes.size) {
            if (stopRequested.get()) return
            val length = minOf(maxBufferSize, bytes.size - offset)
            callback.audioAvailable(bytes, offset, length)
            offset += length
        }
    }

    private companion object {
        const val TAG = "PiperPlusTts"
        const val SAMPLE_RATE = 22050
        const val CHANNEL_COUNT = 1
        const val BYTES_PER_SAMPLE = 2
        const val DEFAULT_ISO3 = "jpn"
    }
}
```

- [ ] **Step 2: Kotlin のコンパイルが通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: instrumented テストを書く**

`android/piper-plus-tts-engine/src/androidTest/java/com/piperplus/tts/PiperPlusTtsServiceTest.kt`:

```kotlin
package com.piperplus.tts

import android.speech.tts.TextToSpeech
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.piperplus.tts.model.ModelPaths
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

/**
 * モデル未導入の端末での可用性判定を確認する。
 *
 * 実モデルを使った合成の検証は、モデルを配置できる CI ジョブで別途行う。
 */
@RunWith(AndroidJUnit4::class)
class PiperPlusTtsServiceTest {

    @Test
    fun `reports missing data for a supported language when no model is installed`() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val paths = ModelPaths(context.filesDir)
        // 事前条件: 既定モデルが未導入であること
        assertEquals(false, paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID))

        assertEquals(
            TextToSpeech.LANG_MISSING_DATA,
            LocaleResolver.availability("jpn", paths.isInstalled(ModelPaths.DEFAULT_MODEL_ID)),
        )
    }

    @Test
    fun `reports not supported for an unsupported language`() {
        assertEquals(
            TextToSpeech.LANG_NOT_SUPPORTED,
            LocaleResolver.availability("kor", modelInstalled = true),
        )
    }
}
```

`android/piper-plus-tts-engine/build.gradle.kts` の `dependencies` に追加する。

```kotlin
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
```

同じく `defaultConfig` に追加する。

```kotlin
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
```

- [ ] **Step 4: ユニットテストが引き続き通ることを確認**

Run: `cd android && ./gradlew :piper-plus-tts-engine:testDebugUnitTest`
Expected: PASS (全テスト)

> instrumented テストの実行にはエミュレータが必要。ローカルにない場合は Task 9 の CI で実行する。

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus-tts-engine
git commit -m "feat(android): TextToSpeechService を実装"
```

---

## Task 9: 3 ABI 対応と CI 統合

**Files:**
- Modify: `android/piper-plus/build.gradle.kts:24-27`
- Modify: `.github/workflows/android-build.yml`

**Interfaces:**
- Consumes: Task 1-8 のすべて
- Produces: CI で APK がビルドされること

- [ ] **Step 1: AAR を 3 ABI 対応にする**

`android/piper-plus/build.gradle.kts` の `ndk` ブロックを変更する。

```kotlin
        ndk {
            // release-shared-lib.yml / android-build.yml と同じ 3 ABI
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
```

- [ ] **Step 2: CI に AAR + APK ビルド job を追加**

`.github/workflows/android-build.yml` の末尾に job を追加する。既存の `build-android` job が
`piper-plus-android-<abi>` という名前で `libpiper_plus.so` を artifact として上げているので、
それを `jniLibs/<abi>/` に展開してから Gradle を回す。

```yaml
  build-tts-engine:
    name: Build TTS engine APK
    needs: build-android
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6.0.3
        with:
          submodules: true

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Download native libraries
        uses: actions/download-artifact@v4
        with:
          pattern: piper-plus-android-*
          path: native-artifacts

      - name: Stage libpiper_plus.so into jniLibs
        run: |
          set -euo pipefail
          for abi in arm64-v8a armeabi-v7a x86_64; do
            dest="android/piper-plus/src/main/jniLibs/${abi}"
            mkdir -p "${dest}"
            find native-artifacts -path "*${abi}*" -name "libpiper_plus.so" \
              -exec cp {} "${dest}/" \;
            find native-artifacts -path "*${abi}*" -name "libonnxruntime.so" \
              -exec cp {} "${dest}/" \;
            test -f "${dest}/libpiper_plus.so" || {
              echo "::error::libpiper_plus.so missing for ${abi}"
              exit 1
            }
          done

      - name: Run unit tests
        working-directory: android
        run: ./gradlew :piper-plus:testDebugUnitTest :piper-plus-tts-engine:testDebugUnitTest

      - name: Build APK
        working-directory: android
        run: ./gradlew :piper-plus-tts-engine:assembleDebug

      - name: Upload APK
        uses: actions/upload-artifact@v4
        with:
          name: piper-plus-tts-engine-debug
          path: android/piper-plus-tts-engine/build/outputs/apk/debug/*.apk
```

- [ ] **Step 3: ローカルでユニットテストが全て通ることを確認**

Run: `cd android && ./gradlew :piper-plus:testDebugUnitTest :piper-plus-tts-engine:testDebugUnitTest`
Expected: PASS (全テスト)

- [ ] **Step 4: CHANGELOG に追記**

`CHANGELOG.md` の Unreleased セクションに追加する (pre-push gate が Unreleased の更新を要求するため)。

```markdown
### Added

- Android システム TTS エンジン (`android/piper-plus-tts-engine`)。6 言語 (ja/en/zh/es/fr/pt) に対応し、任意のアプリからオフライン音声合成を利用できる
- `com.piperplus.SynthOptions` — Android AAR から `language_id` / `length_scale` などの合成オプションを指定可能に
```

- [ ] **Step 5: コミット**

```bash
git add android/piper-plus/build.gradle.kts .github/workflows/android-build.yml CHANGELOG.md
git commit -m "ci(android): TTS エンジン APK のビルドを追加し AAR を 3 ABI 対応に"
```

---

## 後続計画 (本計画のスコープ外)

M3 の完了時点では、モデルを `adb push` などで手動配置する必要がある。実用的な配布には次の 2 つが残る。

**M4: モデル管理と設定 UI**

- `ModelCatalog` — 配布モデルの定義 (HF repo / ファイル名 / SHA256 / サイズ)
- `ModelDownloader` — HF からの取得、進捗通知、チェックサム検証、一時ファイル経由の atomic move
- `SettingsActivity` — モデル一覧・ダウンロード・削除 UI、モデルごとのライセンス表示 (利用規約を持つモデルは同意を必須にする)
- `res/xml/tts_engine.xml` に `android:settingsActivity` を追加

**M5: 配布**

- `release-shared-lib.yml` に Android 3 ABI のリリースアセットを追加
- APK の署名と GitHub Releases への添付
- `fdroiddata` への Merge Request (初回のみ)。以降は `UpdateCheckMode: Tags` + `AutoUpdateMode: Version` で tag push に自動追従

いずれも設計は [android-tts-engine-design.md](./android-tts-engine-design.md) の §6.5 / §9 に記載済み。実装着手時に本計画と同じ粒度へ展開する。
