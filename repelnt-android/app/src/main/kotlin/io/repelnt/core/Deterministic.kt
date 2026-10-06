package io.repelnt.core

import java.security.MessageDigest

/**
 * Values derived from a seed by hashing, not by a library random generator.
 *
 * A shadow identity that changes is a shadow identity that has been detected, so
 * this derivation has to give the same answer on every device, every Android
 * version and every future release of the standard library. `kotlin.random.Random`
 * is deterministic for a given seed, but its algorithm is an implementation
 * detail that is free to change. SHA-256 is specified, so every value here comes
 * straight out of a digest.
 *
 * Each value is keyed by its own label rather than by position in a sequence.
 * That way adding a new field later cannot disturb the fields already generated,
 * which matters because a stored identity must survive an app update unchanged.
 */
class Deterministic(private val seed: String) {

    private fun unsigned(label: String): Long {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest("$seed|$label".toByteArray())
        var value = 0L
        // Seven bytes: comfortably inside Long, no sign to worry about.
        for (i in 0 until 7) value = (value shl 8) or (digest[i].toLong() and 0xff)
        return value
    }

    fun int(label: String, bound: Int): Int {
        require(bound > 0) { "bound must be positive" }
        return (unsigned(label) % bound).toInt()
    }

    fun range(label: String, from: Int, until: Int): Int {
        require(until > from) { "empty range" }
        return from + int(label, until - from)
    }

    fun <T> choice(label: String, items: List<T>): T {
        require(items.isNotEmpty()) { "no items to choose from" }
        return items[int(label, items.size)]
    }

    fun double(label: String, low: Double, high: Double): Double =
        low + (unsigned(label).toDouble() / MAX) * (high - low)

    companion object {
        private const val MAX = 72057594037927935.0 // 2^56 - 1
    }
}
