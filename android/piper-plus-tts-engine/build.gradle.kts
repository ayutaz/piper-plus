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
}
