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
// reproducibility 強化)。 transitive deps を gradle.lockfile に固定する
// 仕組み。 ただし STRICT mode は lockfile 必須 (`MissingLockStateException`)
// なので、 lockfile が generated されるまでは DEFAULT mode で運用。
//
// Phase 1 (現状): DEFAULT mode + lockAllConfigurations。 lockfile が
//   存在しなくても build 成功、 存在すれば検証。
// Phase 2 (別 PR): release-kotlin-g2p workflow に `./gradlew :piper-plus-g2p:
//   dependencies --write-locks` step を追加して gradle.lockfile を生成・
//   commit。 lockfile が repo に landed したら本 file の lockMode を STRICT
//   に切り替える。
//
// lockfile 更新方法:
//   ./gradlew :piper-plus-g2p:dependencies --write-locks
//   ./gradlew :piper-plus:dependencies --write-locks
subprojects {
    dependencyLocking {
        lockAllConfigurations()
        // STRICT mode は lockfile が必須 — generate されるまでは DEFAULT。
        // lockMode.set(LockMode.STRICT)
    }
}
