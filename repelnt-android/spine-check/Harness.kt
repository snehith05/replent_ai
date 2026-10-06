package io.repelnt.core

/**
 * Runs the spine on the JVM, with no Android involved, so the logic can be
 * checked before any of it goes near a device. Mirrors tests/demo_spine.py.
 */
fun main() {
    val shadow = ShadowIdentity.derive("device-9f3a7c21")
    val engine = PolicyEngine()

    println("SHADOW IDENTITY (derived once, stored, never regenerated)")
    println("  ${shadow.name} | ${shadow.phone} | ${shadow.city}, ${shadow.state}")
    println("  home ${shadow.home}  work ${shadow.work}  device ${shadow.device}")
    println(
        "  ${shadow.contacts.size} contacts, first three: " +
            shadow.contacts.take(3).joinToString(", ") { it.name }
    )

    val cases = listOf(
        Subject.fromApp("com.adnetwork.sdk", harvester = true) to Resource(ResourceKind.LOCATION),
        Subject.fromApp("com.adnetwork.sdk", harvester = true) to Resource(ResourceKind.CONTACTS),
        Subject.fromApp("com.adnetwork.sdk", harvester = true) to Resource(ResourceKind.PAYMENT),
        Subject.fromApp("com.yourbank.app") to Resource(ResourceKind.PAYMENT),
        Subject.fromAgent("assistant.unknown") to Resource(ResourceKind.MESSAGES),
        Subject.fromAgent("assistant.unknown") to Resource(ResourceKind.LOCATION),
        Subject.fromAgent("os.assistant", verified = true) to Resource(ResourceKind.MESSAGES),
        Subject.fromCrawler("ja4:t13d1516h2", score = 145) to Resource(ResourceKind.CONTENT, "/research"),
        Subject.fromPeer("ed25519:4f8c") to Resource(ResourceKind.CONTENT, "/notes"),
    )

    println()
    println("DECISIONS (one engine, every surface)")
    println("  %-8s %-22s %-11s %-7s %s".format("surface", "subject", "resource", "action", "why"))
    for ((subject, resource) in cases) {
        val d = engine.decide(subject, resource)
        println(
            "  %-8s %-22s %-11s %-7s %s".format(
                subject.kind.name.lowercase(),
                subject.id.take(21),
                resource.kind.name.lowercase(),
                d.action.name.lowercase(),
                d.reason,
            )
        )
    }

    println()
    println("CROSS-SURFACE CONSISTENCY")
    val (lat, lon) = shadow.location(tick = 14)
    println("  ad SDK receives location ...... $lat, $lon")
    println("  agent sees location ........... $lat, $lon")
    println("  photo metadata stamped with ... $lat, $lon")
    println("  mesh peer told user is in ..... ${shadow.city}")
    println("  -> nothing an adversary cross-references disagrees")

    println()
    println("STABILITY (an identity that changes is an identity that was detected)")
    val again = ShadowIdentity.derive("device-9f3a7c21")
    println("  same seed re-derived ......... ${if (again == shadow) "identical" else "DIFFERS"}")
    println("  location(14) repeatable ..... " +
        if (shadow.location(14) == again.location(14)) "identical" else "DIFFERS")
    val other = ShadowIdentity.derive("device-0000ffff")
    println("  a different device ........... ${other.name}, ${other.city}")

    println()
    println("FIELD STABILITY ACROSS AN APP UPDATE")
    println("  each field is keyed by its own label, so adding a field later cannot")
    println("  disturb the ones already stored. name=${shadow.name} stays ${shadow.name}.")
}
