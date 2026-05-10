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

    // Quality gates (Wave 1) — keep parity with the .NET / Rust / Go / Python
    // toolchains so Android contributions get caught locally instead of
    // surfacing late on CI. Versions are pinned (and synced with the Wave 2
    // CI workflow) to avoid drift on tooling auto-bumps.
    //
    // Spotless intentionally skipped — ktlint already covers Kotlin format +
    // lint, and adding Spotless on top duplicates the gradle task graph for
    // no extra coverage. Re-introduce only if we add Java sources.
    id("org.jlleitschuh.gradle.ktlint") version "12.1.1"
    id("io.gitlab.arturbosch.detekt") version "1.23.7"
    id("org.owasp.dependencycheck") version "10.0.4"
    jacoco
}

ktlint {
    // ktlint engine version is decoupled from the gradle plugin version
    // (12.1.1 is the gradle plugin; 1.3.1 is the engine ruleset).
    version.set("1.3.1")
    android.set(true)
    outputColorName.set("RED")
    // CI-fail by default — local devs see the violations and can run
    // `./gradlew ktlintFormat` to auto-fix.
    ignoreFailures.set(false)
    reporters {
        reporter(org.jlleitschuh.gradle.ktlint.reporter.ReporterType.PLAIN)
        reporter(org.jlleitschuh.gradle.ktlint.reporter.ReporterType.CHECKSTYLE)
    }
    filter {
        exclude("**/generated/**", "**/build/**")
    }
}

detekt {
    toolVersion = "1.23.7"
    config.setFrom(files("$rootDir/detekt.yml"))
    // buildUponDefaultConfig=true → detekt.yml only needs to override what
    // we want to differ from upstream defaults, so the file stays small.
    buildUponDefaultConfig = true
    autoCorrect = false
}

jacoco {
    toolVersion = "0.8.12"
}

// Wire jacoco onto the unit test task (the AGP `test` task is registered
// lazily once the android variants resolve, so use `matching` instead of
// `named` to avoid configure-time NPE if AGP order changes).
tasks.matching { it.name == "test" }.configureEach {
    finalizedBy(tasks.named("jacocoTestReport"))
}

tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn(tasks.matching { it.name == "test" })
    reports {
        xml.required.set(true)
        html.required.set(true)
        csv.required.set(false)
    }
    classDirectories.setFrom(
        files(
            classDirectories.files.map { dir ->
                fileTree(dir) { exclude("**/generated/**") }
            },
        ),
    )
}

tasks.register<JacocoCoverageVerification>("jacocoCoverageVerification") {
    violationRules {
        rule {
            limit {
                // 60% line coverage floor — matches the dev/Rust/Python
                // baselines. Bump this once the L3 instrumented tests are
                // wired into JVM coverage too.
                minimum = "0.60".toBigDecimal()
            }
        }
    }
}

tasks.matching { it.name == "check" }.configureEach {
    dependsOn(tasks.named("jacocoCoverageVerification"))
}

dependencyCheck {
    // CVSS 7.0 = "High" — fail the build on High/Critical vulnerabilities,
    // mirroring the OWASP guidance. Lower scores are reported but don't
    // block. Suppressions live in `dependency-check-suppressions.xml` at
    // the android root (created on demand when the first false-positive
    // shows up).
    failBuildOnCVSS = 7.0f
    suppressionFile = "$rootDir/dependency-check-suppressions.xml"
    formats = listOf("HTML", "JSON")
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
                    // c++_static so libc++_shared.so is NOT bundled into the
                    // AAR. NDK r26.1's bundled libc++_shared.so is not 16-KB
                    // aligned, which would fail the L5 page alignment gate
                    // and break load on Android 15+ (NFR-COMPAT-4). The JNI
                    // shim only uses std::memset / std::snprintf and never
                    // shares C++ types across the libpiper_plus.so boundary
                    // (the C API uses raw char* / handles), so c++_static is
                    // safe here.
                    "-DANDROID_STL=c++_static",
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
            devices {
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

    // detekt-formatting bundles the ktlint ruleset into detekt so the
    // `formatting` section in detekt.yml has rules to operate on. The
    // version must match `detekt { toolVersion = ... }` above.
    detektPlugins("io.gitlab.arturbosch.detekt:detekt-formatting:1.23.7")
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
