package io.repelnt.core

/**
 * Surface-agnostic policy engine.
 *
 * One decision function for every surface. An app's outbound request, an
 * on-device agent reading messages, a mesh peer asking for a file and a web
 * crawler fetching a page are all the same shape: a subject of some trust level
 * wants a resource, and we answer allow / block / poison / charge.
 *
 * Keeping it to one engine is what lets the surfaces share a shadow identity
 * instead of contradicting one another.
 */
enum class Action { ALLOW, BLOCK, POISON, CHARGE }

enum class Trust {
    /** Cryptographically or DNS-confirmed identity. */
    VERIFIED,
    UNKNOWN,

    /** Known to collect for training or resale. */
    HARVESTER,
}

enum class SubjectKind { APP, AGENT, CRAWLER, PEER }

enum class ResourceKind {
    LOCATION, CONTACTS, PHOTOS, MESSAGES, CALENDAR,
    CONTENT, TELEMETRY, CREDENTIALS, PAYMENT,
}

/** Whoever is asking. [id] is a package name, agent id, fingerprint or peer key. */
data class Subject(
    val id: String,
    val kind: SubjectKind,
    val trust: Trust = Trust.UNKNOWN,
    val score: Int = 0,
    val evidence: List<String> = emptyList(),
) {
    companion object {
        fun fromApp(packageName: String, harvester: Boolean = false) = Subject(
            packageName, SubjectKind.APP,
            if (harvester) Trust.HARVESTER else Trust.UNKNOWN,
        )

        fun fromAgent(agentId: String, verified: Boolean = false) = Subject(
            agentId, SubjectKind.AGENT,
            if (verified) Trust.VERIFIED else Trust.UNKNOWN,
        )

        fun fromCrawler(
            fingerprint: String,
            score: Int,
            reasons: List<String> = emptyList(),
            verified: Boolean = false,
        ) = Subject(
            fingerprint, SubjectKind.CRAWLER,
            when {
                verified -> Trust.VERIFIED
                score >= 50 -> Trust.HARVESTER
                else -> Trust.UNKNOWN
            },
            score, reasons,
        )

        fun fromPeer(peerKey: String) = Subject(peerKey, SubjectKind.PEER, Trust.VERIFIED)
    }
}

/** What is being asked for. */
data class Resource(val kind: ResourceKind, val path: String = "*")

data class Rule(
    val action: Action,
    val reason: String,
    val kinds: Set<SubjectKind> = emptySet(),
    val trust: Set<Trust> = emptySet(),
    val resources: Set<ResourceKind> = emptySet(),
    val subjectGlob: String = "*",
    val pathGlob: String = "*",
    val minScore: Int? = null,
) {
    fun matches(s: Subject, r: Resource): Boolean =
        (kinds.isEmpty() || s.kind in kinds) &&
            (trust.isEmpty() || s.trust in trust) &&
            (resources.isEmpty() || r.kind in resources) &&
            glob(subjectGlob).matches(s.id) &&
            glob(pathGlob).matches(r.path) &&
            (minScore == null || s.score >= minScore)

    private companion object {
        private val cache = HashMap<String, Regex>()

        fun glob(pattern: String): Regex = cache.getOrPut(pattern) {
            val body = StringBuilder()
            for (c in pattern) {
                when (c) {
                    '*' -> body.append(".*")
                    '?' -> body.append('.')
                    else -> body.append(Regex.escape(c.toString()))
                }
            }
            Regex(body.toString())
        }
    }
}

data class Decision(
    val action: Action,
    val reason: String,
    val subject: Subject,
    val resource: Resource,
) {
    val poisoned: Boolean get() = action == Action.POISON
}

/** Ordered rules, first match wins. */
class PolicyEngine(
    private val rules: List<Rule> = defaultRules(),
    private val default: Action = Action.ALLOW,
) {
    fun decide(subject: Subject, resource: Resource): Decision {
        for (rule in rules) {
            if (rule.matches(subject, resource)) {
                return Decision(rule.action, rule.reason, subject, resource)
            }
        }
        return Decision(default, "no rule matched", subject, resource)
    }
}

/** A starting policy that errs toward keeping the device working. */
fun defaultRules(): List<Rule> = listOf(
    // Verified identities are never poisoned. This is the guard that stops a
    // detection miss from breaking something the user depends on.
    Rule(Action.ALLOW, "verified identity", trust = setOf(Trust.VERIFIED)),

    // Credentials and payment data are blocked outright for untrusted callers and
    // never poisoned: fake banking data breaks the user's own app rather than the
    // harvester. Trusted first-party apps fall through to the default.
    Rule(
        Action.BLOCK, "untrusted caller, sensitive resource",
        trust = setOf(Trust.HARVESTER),
        resources = setOf(ResourceKind.CREDENTIALS, ResourceKind.PAYMENT),
    ),
    Rule(
        Action.BLOCK, "unknown agent, sensitive resource",
        kinds = setOf(SubjectKind.AGENT), trust = setOf(Trust.UNKNOWN),
        resources = setOf(ResourceKind.CREDENTIALS, ResourceKind.PAYMENT),
    ),

    Rule(Action.POISON, "known harvester", trust = setOf(Trust.HARVESTER)),
    Rule(
        Action.POISON, "scores as a scraper",
        kinds = setOf(SubjectKind.CRAWLER), minScore = 50,
    ),

    // Unknown agents see decoys for personal data but real content otherwise.
    Rule(
        Action.POISON, "unknown agent reading personal data",
        kinds = setOf(SubjectKind.AGENT), trust = setOf(Trust.UNKNOWN),
        resources = setOf(
            ResourceKind.LOCATION, ResourceKind.CONTACTS,
            ResourceKind.MESSAGES, ResourceKind.PHOTOS,
        ),
    ),
)
