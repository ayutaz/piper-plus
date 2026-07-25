plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("maven-publish")
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
    namespace = "com.piperplus"
    compileSdk = 35

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")

        externalNativeBuild {
            cmake {
                cppFlags("-std=c++17")
                arguments("-DANDROID_STL=c++_shared")
            }
        }

        ndk {
            // release-shared-lib.yml / android-build.yml と同じ 3 ABI
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
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = "11"
    }

    publishing {
        singleVariant("release") {
            withSourcesJar()
        }
    }
}

dependencies {
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    // detekt-formatting bundles the ktlint ruleset into detekt so the
    // `formatting` section in the shared detekt.yml has rules to operate on.
    // The version must match `detekt { toolVersion = ... }` above.
    detektPlugins("io.gitlab.arturbosch.detekt:detekt-formatting:1.23.8")
}

afterEvaluate {
    publishing {
        publications {
            create<MavenPublication>("release") {
                from(components["release"])

                groupId = "com.piperplus"
                artifactId = "piper-plus"
                version = project.findProperty("VERSION_NAME") as? String ?: "0.1.0"

                pom {
                    name.set("piper-plus")
                    description.set("Offline multilingual neural TTS for Android")
                    url.set("https://github.com/ayutaz/piper-plus")

                    licenses {
                        license {
                            name.set("MIT")
                            url.set("https://github.com/ayutaz/piper-plus/blob/dev/LICENSE.md")
                        }
                    }

                    scm {
                        connection.set("scm:git:git://github.com/ayutaz/piper-plus.git")
                        url.set("https://github.com/ayutaz/piper-plus")
                    }
                }
            }
        }

        repositories {
            maven {
                name = "GitHubPackages"
                url = uri("https://maven.pkg.github.com/ayutaz/piper-plus")
                credentials {
                    username = System.getenv("GITHUB_ACTOR") ?: ""
                    password = System.getenv("GITHUB_TOKEN") ?: ""
                }
            }
        }
    }
}
