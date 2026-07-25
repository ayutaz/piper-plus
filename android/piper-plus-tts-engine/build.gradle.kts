plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // :piper-plus-g2p と同じ設定・同じバージョンで揃える。片方だけ lint が
    // 掛かっていない状態はスタイルのドリフトを生む。
    id("org.jlleitschuh.gradle.ktlint") version "12.3.0"
    id("io.gitlab.arturbosch.detekt") version "1.23.8"
}

detekt {
    toolVersion = "1.23.7"
    config.setFrom(files("$rootDir/detekt.yml"))
    buildUponDefaultConfig = true
    autoCorrect = false
}

ktlint {
    version.set("1.3.1")
    android.set(true)
    outputColorName.set("RED")
    ignoreFailures.set(false)
    filter {
        exclude("**/generated/**", "**/build/**")
    }
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

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildFeatures {
        // ManifestWiringTest が applicationId を参照して manifest の
        // 相対クラス名を絶対名に解決するため。
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
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
        // android.jar のスタブメソッドが RuntimeException("Stub!") ではなく
        // 既定値を返すようにする。SynthesisSession の catch 節が Log.e を
        // 呼ぶため必要 (TextToSpeech.LANG_* / ERROR_* は static final int で
        // コンパイル時にインライン展開されるので、定数の参照には不要)。
        //
        // 副作用として android.jar 由来のオブジェクトはすべて無害な既定値を
        // 返す。SynthesisCallback をテストに渡す際に実スタブを使うと
        // maxBufferSize が 0 になるため、必ず FakeSynthesisCallback を使うこと。
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(project(":piper-plus"))
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    // detekt-formatting bundles the ktlint ruleset into detekt so the
    // `formatting` section in the shared detekt.yml has rules to operate on.
    // The version must match `detekt { toolVersion = ... }` above.
    detektPlugins("io.gitlab.arturbosch.detekt:detekt-formatting:1.23.8")
}
