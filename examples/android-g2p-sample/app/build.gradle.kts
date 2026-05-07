plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace  = "com.piperplus.g2p.sample"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.piperplus.g2p.sample"
        minSdk        = 24
        targetSdk     = 34
        versionCode   = 1
        versionName   = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // Library under test. Composite build (settings.gradle.kts) wires this
    // to the local module; replace the substitution to consume from Maven
    // Central instead.
    implementation("io.github.ayutaz:piper-plus-g2p-android:1.0.0")

    // Compose
    val composeBom = platform("androidx.compose:compose-bom:2024.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Coroutines for the optional HF Hub dictionary download demo.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
