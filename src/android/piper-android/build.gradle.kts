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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        consumerProguardFiles("consumer-rules.pro")

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }

        // TODO: No externalNativeBuild (CMake/ndk-build) configuration is defined here.
        // Native .so files must be pre-built using the scripts in `scripts/` and placed
        // in `src/main/jniLibs/<abi>/` manually.
        // For Gradle-integrated native builds, an `externalNativeBuild` block would be
        // needed in this `defaultConfig` section (or at the `android` level).
        // This is intentionally omitted because the native build requires external
        // dependencies (ONNX Runtime, OpenJTalk, spdlog, fmt) that must be
        // cross-compiled for Android first.
    }

    buildTypes {
        release {
            // Library modules should not minify; the consuming app is responsible for minification
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

    // Note: publishing { singleVariant("release") } is handled automatically
    // by the vanniktech maven-publish plugin. Do NOT add it manually here
    // as it causes "singleVariant publishing DSL multiple times" error.
}

dependencies {
    implementation(libs.onnxruntime.android)
    implementation(libs.coroutines.android)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
}

mavenPublishing {
    publishToMavenCentral(
        com.vanniktech.maven.publish.SonatypeHost.CENTRAL_PORTAL
    )

    signAllPublications()

    coordinates(
        groupId = "io.github.ayousanz",
        artifactId = "piper-android",
        version = providers.gradleProperty("VERSION_NAME").getOrElse("0.1.0-SNAPSHOT")
    )

    pom {
        name.set("Piper Android TTS")
        description.set("Neural text-to-speech for Android with VITS architecture - 6 languages supported")
        url.set("https://github.com/ayutaz/piper-plus")
        inceptionYear.set("2026")

        licenses {
            license {
                name.set("MIT License")
                url.set("https://opensource.org/licenses/MIT")
            }
        }

        developers {
            developer {
                id.set("ayousanz")
                name.set("ayousanz")
                url.set("https://github.com/ayousanz")
            }
        }

        scm {
            url.set("https://github.com/ayutaz/piper-plus")
            connection.set("scm:git:git://github.com/ayutaz/piper-plus.git")
            developerConnection.set("scm:git:ssh://github.com/ayutaz/piper-plus.git")
        }
    }
}
