// Root build.gradle.kts for piper-plus Android AAR project
plugins {
    id("com.android.library") version "8.7.3" apply false
    id("org.jetbrains.kotlin.android") version "2.1.0" apply false
    id("com.vanniktech.maven.publish") version "0.30.0" apply false
    // Dokka — generates the javadoc.jar that Maven Central ships alongside
    // the AAR (FR-DOCS-4). vanniktech's `publishJavadocJar = true` would
    // otherwise emit an empty javadoc, which fails Sonatype's quality gate.
    id("org.jetbrains.dokka") version "1.9.20" apply false
}

// Gradle dependency locking (Wave 3 — feedback_data_asset_distribution の
// reproducibility 強化)。 transitive deps を gradle.lockfile に固定し、 CI
// hosts と dev workstations の build 再現性を担保。 lockfile 更新は
//   ./gradlew :piper-plus-g2p:dependencies --write-locks
//   ./gradlew :piper-plus:dependencies --write-locks
// で実行。 CI 側は `--write-locks` を付けないため transitive bump があれば
// strict mode で fail-fast する。
subprojects {
    dependencyLocking {
        lockAllConfigurations()
        lockMode.set(LockMode.STRICT)
    }
}
