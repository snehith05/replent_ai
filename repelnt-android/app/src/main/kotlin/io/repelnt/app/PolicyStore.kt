package io.repelnt.app

import android.content.Context
import io.repelnt.core.Action
import java.util.UUID

/**
 * Per-device seed and per-app policy, persisted.
 *
 * The seed is written once and never rewritten. A shadow identity that changes
 * between runs is a shadow identity that has been detected, so losing this value
 * is worse than losing the app's settings.
 */
class PolicyStore(context: Context) {

    private val prefs = context.getSharedPreferences("repelnt", Context.MODE_PRIVATE)

    val deviceSeed: String
        get() = prefs.getString(KEY_SEED, null) ?: UUID.randomUUID().toString().also {
            prefs.edit().putString(KEY_SEED, it).apply()
        }

    fun actionFor(packageName: String): Action =
        prefs.getString(prefix(packageName), null)
            ?.let { runCatching { Action.valueOf(it) }.getOrNull() }
            ?: Action.ALLOW

    fun setAction(packageName: String, action: Action) {
        prefs.edit().putString(prefix(packageName), action.name).apply()
    }

    /** Cycles through the three actions a user can pick per app. */
    fun cycle(packageName: String): Action {
        val next = when (actionFor(packageName)) {
            Action.ALLOW -> Action.POISON
            Action.POISON -> Action.BLOCK
            else -> Action.ALLOW
        }
        setAction(packageName, next)
        return next
    }

    fun counts(packages: List<String>): Map<Action, Int> =
        packages.groupingBy { actionFor(it) }.eachCount()

    private fun prefix(packageName: String) = "app.$packageName"

    private companion object {
        const val KEY_SEED = "device.seed"
    }
}
