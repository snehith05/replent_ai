import io.repelnt.core.Deterministic
import io.repelnt.core.ShadowIdentity

/** Checks the derivation actually varies, and that nothing collapses to a constant. */
fun main() {
    println("=== jitter on both axes, across seeds ===")
    repeat(8) { i ->
        val id = ShadowIdentity.derive("device-$i")
        println(
            "  seed %d  %-14s home %s  work %s".format(
                i, id.city, id.home.toString(), id.work.toString()
            )
        )
    }

    println()
    println("=== raw doubles: are they spread, or stuck? ===")
    val d = Deterministic("spread-test")
    val values = (0 until 12).map { d.double("lon.$it", -6.0, 6.0) }
    values.forEach { print("  %+.3f".format(it)) }
    println()
    println("  min %.3f  max %.3f  distinct %d".format(
        values.min(), values.max(), values.distinct().size))

    println()
    println("=== int() uniformity over 12000 draws into 8 buckets ===")
    val counts = IntArray(8)
    val e = Deterministic("uniform-test")
    for (i in 0 until 12000) counts[e.int("draw.$i", 8)]++
    println("  " + counts.joinToString("  "))
    println("  expected 1500 each; spread ${counts.min()}..${counts.max()}")

    println()
    println("=== no two devices share an identity ===")
    val names = (0 until 500).map { ShadowIdentity.derive("dev-$it").name }
    println("  500 devices -> ${names.distinct().size} distinct names " +
        "(collisions expected: 16 x 15 = 240 possible combinations)")
    val phones = (0 until 500).map { ShadowIdentity.derive("dev-$it").phone }
    println("  500 devices -> ${phones.distinct().size} distinct phone numbers")
}
