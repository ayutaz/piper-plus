// piper-plus-g2p (Android G2P AAR) — Issue #388
//
// Coordinates: io.github.ayutaz:piper-plus-g2p-android
//
// This module wraps the engine-less G2P entrypoints in libpiper_plus.so so
// Android apps can do text→phoneme conversion without bundling an ONNX model.
// Maven Central publishing uses the vanniktech plugin to keep the release
// pipeline aligned with the other piper-plus G2P packages (PyPI / npm /
// crates.io / NuGet / Go module).

import com.vanniktech.maven.publish.AndroidSingleVariantLibrary
import com.vanniktech.maven.publish.SonatypeHost

plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("com.vanniktech.maven.publish")
    id("org.jetbrains.dokka")
}

android {
    namespace  = "com.piperplus.g2p"
    compileSdk = 35
    // Pin the NDK so reproducibility holds across CI hosts and developer
    // workstations (NFR-PUB-1). r26d is the LTS the rest of piper-plus uses.
    ndkVersion = "26.1.10909125"

    defaultConfig {
        minSdk    = 24
        targetSdk = 34
        consumerProguardFiles("consumer-rules.pro")

        externalNativeBuild {
            cmake {
                cppFlags("-std=c++17")
                arguments(
                    "-DANDROID_STL=c++_shared",
                    // 16 KB page size compat (Android 15+, NFR-COMPAT-4).
                    // Doubled here so the JNI .so itself is 16 KB-aligned;
                    // the linker flag is also set in CMakeLists.txt for safety.
                    "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384",
                )
            }
        }

        ndk {
            // FR-DIST-2: ship arm64-v8a (production), armeabi-v7a (legacy),
            // and x86_64 (Gradle Managed Devices emulator).
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
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

    externalNativeBuild {
        cmake {
            path    = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        managedDevices {
            allDevices {
                create<com.android.build.api.dsl.ManagedVirtualDevice>("pixel6api34") {
                    device           = "Pixel 6"
                    apiLevel         = 34
                    systemImageSource = "aosp"
                }
            }
        }
    }

    // Note: variant publishing is configured via the vanniktech
    // `AndroidSingleVariantLibrary(...)` block below — do NOT also declare
    // `android.publishing { singleVariant(...) }` here, otherwise the
    // variant gets configured twice and Gradle warns / fails.
}

dependencies {
    // DictionaryDownloader uses kotlinx-coroutines for IO dispatch + cancellation.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("org.json:json:20240303")
    androidTestImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
}

// Copy the cross-runtime G2P fixture into androidTest assets so the L4 parity
// instrumented test can read it via `assets.open(...)`. We copy the file
// rather than symlink so Windows hosts work too.
val syncG2pFixture = tasks.register<Copy>("syncG2pFixture") {
    from(rootProject.layout.projectDirectory.dir("../tests/fixtures/g2p"))
    include("phoneme_test_cases.json", "phoneme_test_cases_golden.json")
    into(layout.projectDirectory.dir("src/androidTest/assets/g2p_fixtures"))
}
tasks.matching {
    it.name.startsWith("merge") && it.name.endsWith("AndroidTestAssets")
}.configureEach { dependsOn(syncG2pFixture) }
tasks.matching { it.name == "preBuild" }.configureEach { dependsOn(syncG2pFixture) }

mavenPublishing {
    publishToMavenCentral(SonatypeHost.CENTRAL_PORTAL)

    // Only sign when GPG credentials are available. PR / dry-run builds
    // run `publishToMavenLocal` without secrets and would otherwise fail
    // the `signMavenPublication` task with `Cannot perform signing task
    // ... because it has no configured signatory`. The release workflow
    // (release-kotlin-g2p.yml) provides ORG_GRADLE_PROJECT_signingInMemoryKey
    // (or signingKey) so signing only kicks in for actual Maven Central
    // publishes.
    val hasSigningKey = listOf(
        "signingInMemoryKey", "signing.key", "signingKey",
    ).any { project.findProperty(it) != null }
    if (hasSigningKey) {
        signAllPublications()
    }

    val publishVersion = project.findProperty("VERSION_NAME") as? String ?: "1.0.0"
    coordinates(
        groupId    = "io.github.ayutaz",
        artifactId = "piper-plus-g2p-android",
        version    = publishVersion,
    )

    // sourcesJar=true → publish a sources.jar alongside the AAR.
    // publishJavadocJar=true → vanniktech wires up the dokkaHtml/dokkaJavadoc
    // task automatically when the dokka plugin is applied above, so the
    // generated javadoc actually has API content (not just LICENSE.md).
    configure(AndroidSingleVariantLibrary(variant = "release", sourcesJar = true, publishJavadocJar = true))

    pom {
        name.set("piper-plus-g2p (Android)")
        description.set(
            "Multilingual G2P (text-to-phoneme) library for Android — engine-less, " +
            "espeak-ng-free. Supports 8 languages: ja, en, zh, ko, es, fr, pt, sv.",
        )
        url.set("https://github.com/ayutaz/piper-plus")
        inceptionYear.set("2026")

        licenses {
            license {
                name.set("MIT")
                url.set("https://opensource.org/licenses/MIT")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("ayutaz")
                name.set("ayutaz")
                url.set("https://github.com/ayutaz")
            }
        }
        scm {
            connection.set("scm:git:git://github.com/ayutaz/piper-plus.git")
            developerConnection.set("scm:git:ssh://git@github.com/ayutaz/piper-plus.git")
            url.set("https://github.com/ayutaz/piper-plus")
        }
    }
}
