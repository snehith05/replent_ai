// Versions pinned to what is already in the local Gradle cache, so a first build
// does not depend on fetching a new toolchain.
plugins {
    // 8.9.1 pairs with Gradle 8.11.1, which is what the wrapper pins.
    id("com.android.application") version "8.9.1" apply false
    id("org.jetbrains.kotlin.android") version "2.0.0" apply false
}
