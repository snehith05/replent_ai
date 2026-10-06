package io.repelnt.core

/**
 * One stable, coherent lie.
 *
 * This is why the four defence surfaces belong in one app. If the fake location
 * an ad SDK receives disagrees with the fake location an on-device agent sees,
 * and both disagree with the metadata on a published photo, the lies refute each
 * other and anyone cross-referencing two sources catches the deception at once.
 * Poisoning only survives an adversary when every exit path draws on the same
 * persona.
 *
 * Generated once per device from a stored seed, then never regenerated.
 */
data class Contact(val name: String, val phone: String)

data class ShadowIdentity(
    val seed: String,
    val name: String,
    val phone: String,
    val email: String,
    val city: String,
    val state: String,
    val language: String,
    val home: Pair<Double, Double>,
    val work: Pair<Double, Double>,
    val birthdate: String,
    val carrier: String,
    val device: String,
    val contacts: List<Contact>,
) {

    /** A stable but moving position: the same shadow person, keeping the same routine. */
    fun location(tick: Int = 0): Pair<Double, Double> {
        val d = Deterministic("$seed|loc|$tick")
        val base = if (tick % 24 in 9..18) work else home
        return Pair(
            round4(base.first + d.double("lat", -0.004, 0.004)),
            round4(base.second + d.double("lon", -0.004, 0.004)),
        )
    }

    companion object {
        /** Real coordinates and languages, so a fake place survives a reverse geocode. */
        private val CITIES = listOf(
            City("Mangaluru", 12.9141, 74.8560, "Karnataka", "kn"),
            City("Pune", 18.5204, 73.8567, "Maharashtra", "mr"),
            City("Kochi", 9.9312, 76.2673, "Kerala", "ml"),
            City("Jaipur", 26.9124, 75.7873, "Rajasthan", "hi"),
            City("Bhubaneswar", 20.2961, 85.8245, "Odisha", "or"),
            City("Coimbatore", 11.0168, 76.9558, "Tamil Nadu", "ta"),
            City("Nagpur", 21.1458, 79.0882, "Maharashtra", "mr"),
            City("Visakhapatnam", 17.6868, 83.2185, "Andhra Pradesh", "te"),
        )
        private val FIRST = listOf(
            "Aditi", "Rohan", "Kavya", "Nikhil", "Sanjana", "Varun", "Ishita",
            "Aniket", "Devika", "Harsha", "Lakshmi", "Pranav", "Rhea",
            "Siddharth", "Tanvi", "Yash",
        )
        private val LAST = listOf(
            "Shetty", "Nair", "Deshpande", "Kulkarni", "Reddy", "Bhat", "Pillai",
            "Joshi", "Rao", "Menon", "Chauhan", "Mahapatra", "Iyer", "Gowda",
            "Sardesai",
        )
        private val CARRIERS = listOf("Jio", "Airtel", "Vi", "BSNL")
        private val DEVICES = listOf(
            "SM-A546E", "Redmi Note 13", "Pixel 7a", "realme 12 Pro", "OnePlus Nord CE4",
        )
        private val PHONE_LEAD = listOf("6", "7", "8", "9")

        fun derive(seed: String, contactCount: Int = 40): ShadowIdentity {
            val d = Deterministic("repelnt-identity:$seed")
            val city = d.choice("city", CITIES)
            val first = d.choice("first", FIRST)
            val last = d.choice("last", LAST)

            // About 111 km to a degree; keeps the point inside the right city.
            fun near(label: String, km: Double) = Pair(
                round4(city.lat + d.double("$label.lat", -km, km) / 111.0),
                round4(city.lon + d.double("$label.lon", -km, km) / 111.0),
            )

            return ShadowIdentity(
                seed = seed,
                name = "$first $last",
                phone = phone(d, "phone"),
                email = "${first.lowercase()}.${last.lowercase()}" +
                    "${d.range("emailnum", 11, 100)}@gmail.com",
                city = city.name,
                state = city.state,
                language = city.language,
                home = near("home", 6.0),
                work = near("work", 12.0),
                birthdate = "%04d-%02d-%02d".format(
                    d.range("birthyear", 1985, 2005),
                    d.range("birthmonth", 1, 13),
                    d.range("birthday", 1, 29),
                ),
                carrier = d.choice("carrier", CARRIERS),
                device = d.choice("device", DEVICES),
                contacts = (0 until contactCount).map { i ->
                    Contact(
                        name = "${d.choice("contact.$i.first", FIRST)} " +
                            d.choice("contact.$i.last", LAST),
                        phone = phone(d, "contact.$i.phone"),
                    )
                },
            )
        }

        private fun phone(d: Deterministic, label: String): String {
            val rest = (0 until 9).joinToString("") { d.int("$label.$it", 10).toString() }
            return "+91${d.choice("$label.lead", PHONE_LEAD)}$rest"
        }

        private fun round4(v: Double) = Math.round(v * 10_000.0) / 10_000.0

        private data class City(
            val name: String, val lat: Double, val lon: Double,
            val state: String, val language: String,
        )
    }
}
