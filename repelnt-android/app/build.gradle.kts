plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "io.repelnt.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.repelnt.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    // Belt and braces: the Kotlin Android plugin adds src/main/kotlin, but saying
    // so explicitly means the layout cannot silently stop working.
    sourceSets["main"].java.srcDirs("src/main/kotlin")

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}

// No external dependencies at all: the screen is a header and a list of rows, and
// the platform's own Activity and theme cover both. Nothing to resolve, nothing to
// go stale, and the APK stays tiny.
dependencies {
}
