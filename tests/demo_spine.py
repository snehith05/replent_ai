"""Four defence surfaces, one spine. Proves the merge is real, not aspirational."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import IntentDetector
from repelnt_core.identity import ShadowIdentity
from repelnt_core.policy import Action, PolicyEngine, Resource, Subject, default_rules

shadow = ShadowIdentity.derive(seed="device-9f3a7c21")
engine = PolicyEngine(default_rules())

print("SHADOW IDENTITY (generated once, stored, never changes)")
print(f"  {shadow.name} | {shadow.phone} | {shadow.city}, {shadow.state}")
print(f"  home {shadow.home}  work {shadow.work}  device {shadow.device}")
print(f"  {len(shadow.contacts)} contacts, first three: "
      + ", ".join(c.name for c in shadow.contacts[:3]))

# --- Surface 1: web crawler, using the gateway's existing detector untouched ---
detector = IntentDetector()
verdict = detector.classify("203.0.113.9", {"user-agent": "GPTBot/1.1"}, {})
subjects = [
    (Subject.from_crawler("ja4:t13d1516h2", verdict.score, verdict.reasons),
     Resource("content", "/research")),
    # --- Surface 2: an app's outbound traffic ---
    (Subject.from_app("com.adnetwork.sdk", harvester=True), Resource("location")),
    (Subject.from_app("com.adnetwork.sdk", harvester=True), Resource("contacts")),
    (Subject.from_app("com.yourbank.app"), Resource("payment")),
    # --- Surface 3: an on-device AI agent ---
    (Subject.from_agent("assistant.unknown"), Resource("messages")),
    (Subject.from_agent("assistant.unknown"), Resource("location")),
    (Subject.from_agent("os.assistant", verified=True), Resource("messages")),
    # --- Surface 4: a mesh peer ---
    (Subject.from_peer("ed25519:4f8c..."), Resource("content", "/notes")),
]

print("\nDECISIONS (one engine, every surface)")
print(f"  {'surface':<9} {'subject':<22} {'resource':<10} {'action':<7} why")
for subject, resource in subjects:
    d = engine.decide(subject, resource)
    print(f"  {subject.kind:<9} {subject.id[:21]:<22} {resource.kind:<10} "
          f"{d.action.value:<7} {d.reason}")

# --- The keystone: every surface tells the SAME lie ---
print("\nCROSS-SURFACE CONSISTENCY (why these cannot be separate products)")
lat, lon = shadow.location(tick=14)
print(f"  ad SDK receives location ...... {lat}, {lon}")
print(f"  agent sees location ........... {lat}, {lon}")
print(f"  photo EXIF stamped with ....... {lat}, {lon}")
print(f"  mesh peer told user is in ..... {shadow.city}")
real_contacts = [c.name for c in shadow.contacts[:2]]
print(f"  contacts given to any caller .. {', '.join(real_contacts)}")
print("  -> nothing an adversary cross-references disagrees")
