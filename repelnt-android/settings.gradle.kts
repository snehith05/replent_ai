pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "repelnt-android"

// One module on purpose. The engine lives in io.repelnt.core and imports nothing
// from Android, so it stays portable and can be compiled and tested on its own
// with kotlinc (see spine-check/). Splitting it into a :core Gradle module needs
// the org.jetbrains.kotlin.jvm plugin, which is a one-line change once that
// plugin is available locally.
include(":app")
