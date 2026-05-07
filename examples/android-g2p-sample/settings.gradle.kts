pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Use the local AAR module while developing in this repo. After the
        // 1.0.0 release the consumer can drop this and rely on Maven Central.
        mavenLocal()
    }
}

rootProject.name = "android-g2p-sample"
include(":app")

// Composite build: pull the AAR module from this repo so the sample stays
// in sync with the library source. Comment this out and switch to Maven
// Central in app/build.gradle.kts if copying the sample outside the repo.
includeBuild("../../android") {
    dependencySubstitution {
        substitute(module("io.github.ayutaz:piper-plus-g2p-android"))
            .using(project(":piper-plus-g2p"))
    }
}
