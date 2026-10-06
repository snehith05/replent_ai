package io.repelnt.app

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.app.Activity
import io.repelnt.core.Action
import io.repelnt.core.PolicyEngine
import io.repelnt.core.Resource
import io.repelnt.core.ResourceKind
import io.repelnt.core.Rule
import io.repelnt.core.ShadowIdentity
import io.repelnt.core.Subject
import io.repelnt.core.defaultRules

/**
 * The real apps on this device, each with a policy you set, resolved through the
 * same engine the gateway uses.
 *
 * Views rather than Compose, deliberately: this screen is a list of rows and a
 * header, and keeping the dependency surface small keeps the build reproducible.
 */
class MainActivity : Activity() {

    private lateinit var store: PolicyStore
    private lateinit var shadow: ShadowIdentity
    private var packages: List<String> = emptyList()
    private var engine = PolicyEngine()
    private var feeding = false

    private val ink = Color.parseColor("#1c2b33")
    private val paper = Color.parseColor("#f5f8f8")
    private val kelp = Color.parseColor("#2f6f6b")
    private val rust = Color.parseColor("#a3322a")
    private val slate = Color.parseColor("#5b707b")

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        store = PolicyStore(this)
        shadow = ShadowIdentity.derive(store.deviceSeed)
        // Registering a test provider needs the location permission as well as
        // the mock-location appop; ask for the first, the second is granted
        // outside the app.
        requestPermissions(
            arrayOf(android.Manifest.permission.ACCESS_FINE_LOCATION,
                    android.Manifest.permission.POST_NOTIFICATIONS),
            1,
        )
        setContentView(buildScreen())
    }

    private fun buildScreen(): View {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(paper)
        }
        root.addView(header())

        val apps = launchableApps()
        packages = apps.map { it.packageName }
        rebuildEngine()

        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        for (app in apps) list.addView(appRow(app))

        root.addView(
            ScrollView(this).apply { addView(list) },
            LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f)
        )
        return root
    }

    private fun header(): View {
        val (lat, lon) = shadow.location(tick = java.time.LocalTime.now().hour)
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(ink)
            setPadding(dp(20), dp(24), dp(20), dp(20))
        }
        box.addView(label("SHADOW IDENTITY", 12f, Color.parseColor("#7fbfb8"), bold = true))
        box.addView(label(shadow.name, 22f, paper, bold = true, topMargin = 6))
        box.addView(
            label(
                "${shadow.city}, ${shadow.state}  ·  ${shadow.phone}",
                13f, Color.parseColor("#bfd2d6"), topMargin = 2
            )
        )
        box.addView(
            label(
                "every surface reports $lat, $lon  ·  a person who does not exist",
                12f, Color.parseColor("#8fa3ab"), topMargin = 10
            )
        )
        box.addView(
            label(
                "tap an app to change what it receives",
                12f, Color.parseColor("#8fa3ab"), topMargin = 14
            )
        )

        val toggle = label("", 13f, paper, bold = true, topMargin = 18).apply {
            setPadding(dp(14), dp(10), dp(14), dp(10))
            isClickable = true
        }
        fun renderToggle() {
            toggle.text = if (feeding) "FEEDING SHADOW LOCATION  ·  tap to stop"
            else "START FEEDING SHADOW LOCATION"
            toggle.setTextColor(if (feeding) rust else Color.parseColor("#7fbfb8"))
        }
        renderToggle()
        toggle.setOnClickListener {
            feeding = !feeding
            if (feeding) ShadowLocationService.start(this)
            else ShadowLocationService.stop(this)
            renderToggle()
        }
        box.addView(toggle)
        return box
    }

    /** Apps with a launcher entry: visible without the restricted all-packages permission. */
    private fun launchableApps(): List<ApplicationInfo> {
        val main = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return packageManager.queryIntentActivities(main, 0)
            .mapNotNull { it.activityInfo?.applicationInfo }
            .distinctBy { it.packageName }
            .filter { it.packageName != packageName }
            .sortedBy { packageManager.getApplicationLabel(it).toString().lowercase() }
    }

    private fun appRow(info: ApplicationInfo): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(20), dp(14), dp(20), dp(14))
            isClickable = true
        }

        val text = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val name = packageManager.getApplicationLabel(info).toString()
        text.addView(label(name, 15f, ink))
        text.addView(label(info.packageName, 11f, slate, topMargin = 2))
        row.addView(text, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))

        val chip = label("", 12f, ink, bold = true).apply {
            setPadding(dp(10), dp(6), dp(10), dp(6))
        }
        row.addView(chip)

        fun render() {
            val decision = decide(info.packageName)
            chip.text = decision.action.name
            chip.setTextColor(
                when (decision.action) {
                    Action.ALLOW -> kelp
                    Action.POISON -> rust
                    else -> slate
                }
            )
        }
        render()

        row.setOnClickListener {
            store.cycle(info.packageName)
            rebuildEngine()
            render()
        }
        return row
    }

    /**
     * The user's per-app choices are rules, not a flag.
     *
     * Collapsing three choices into a single `harvester` boolean lost BLOCK
     * entirely: a harvester asking for location matches the "known harvester"
     * rule and always resolves to POISON, so the third tap had no visible
     * effect. Expressing each choice as a rule in front of the defaults keeps
     * the engine authoritative -- the same engine the gateway runs -- while
     * still honouring what was picked.
     */
    private fun rebuildEngine() {
        val overrides = packages
            .map { it to store.actionFor(it) }
            .filter { (_, action) -> action != Action.ALLOW }
            .map { (pkg, action) -> Rule(action, "set by you", subjectGlob = pkg) }
        engine = PolicyEngine(overrides + defaultRules())
    }

    private fun decide(packageName: String) =
        engine.decide(Subject.fromApp(packageName), Resource(ResourceKind.LOCATION))

    private fun label(
        text: String,
        sizeSp: Float,
        colour: Int,
        bold: Boolean = false,
        topMargin: Int = 0,
    ) = TextView(this).apply {
        this.text = text
        setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp)
        setTextColor(colour)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        layoutParams = LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT).apply {
            if (topMargin > 0) this.topMargin = dp(topMargin)
        }
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()
}
