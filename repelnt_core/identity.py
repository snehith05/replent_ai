"""Shadow identity: one stable, coherent lie.

This is why all four defence surfaces belong in one product. If the fake
location an ad SDK receives disagrees with the fake location an on-device agent
sees, and both disagree with the EXIF on a published photo, the lies refute each
other and anyone cross-referencing two sources catches the deception at once.
Poisoning only survives an adversary if every exit path draws from a single
consistent persona.

Deterministic from a seed and JSON-serialisable: generated once per device,
stored, and reused forever. A shadow identity that changes is a shadow identity
that has been detected.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict

# Real coordinates and languages, so a fake location survives a reverse geocode.
CITIES = [
    ("Mangaluru", 12.9141, 74.8560, "Karnataka", "kn"),
    ("Pune", 18.5204, 73.8567, "Maharashtra", "mr"),
    ("Kochi", 9.9312, 76.2673, "Kerala", "ml"),
    ("Jaipur", 26.9124, 75.7873, "Rajasthan", "hi"),
    ("Bhubaneswar", 20.2961, 85.8245, "Odisha", "or"),
    ("Coimbatore", 11.0168, 76.9558, "Tamil Nadu", "ta"),
    ("Nagpur", 21.1458, 79.0882, "Maharashtra", "mr"),
    ("Visakhapatnam", 17.6868, 83.2185, "Andhra Pradesh", "te"),
]
FIRST = ["Aditi", "Rohan", "Kavya", "Nikhil", "Sanjana", "Varun", "Ishita", "Aniket",
         "Devika", "Harsha", "Lakshmi", "Pranav", "Rhea", "Siddharth", "Tanvi", "Yash"]
LAST = ["Shetty", "Nair", "Deshpande", "Kulkarni", "Reddy", "Bhat", "Pillai", "Joshi",
        "Rao", "Menon", "Chauhan", "Mahapatra", "Iyer", "Gowda", "Sardesai"]
CARRIERS = ["Jio", "Airtel", "Vi", "BSNL"]
DEVICES = ["SM-A546E", "Redmi Note 13", "Pixel 7a", "realme 12 Pro", "OnePlus Nord CE4"]


@dataclass
class Contact:
    name: str
    phone: str


@dataclass
class ShadowIdentity:
    """A plausible person who does not exist, derived entirely from `seed`."""

    seed: str
    name: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    state: str = ""
    language: str = ""
    home: tuple[float, float] = (0.0, 0.0)
    work: tuple[float, float] = (0.0, 0.0)
    birthdate: str = ""
    carrier: str = ""
    device: str = ""
    contacts: list[Contact] = field(default_factory=list)

    @classmethod
    def derive(cls, seed: str, contact_count: int = 40) -> ShadowIdentity:
        rng = random.Random(f"repelnt-identity:{seed}")
        city, lat, lon, state, lang = rng.choice(CITIES)
        first, last = rng.choice(FIRST), rng.choice(LAST)

        def near(km: float) -> tuple[float, float]:
            # ~111 km per degree; keeps the point inside the right city.
            return (round(lat + rng.uniform(-km, km) / 111, 4),
                    round(lon + rng.uniform(-km, km) / 111, 4))

        return cls(
            seed=seed,
            name=f"{first} {last}",
            phone=f"+91{rng.choice('6789')}{rng.randint(10**8, 10**9 - 1)}",
            email=f"{first.lower()}.{last.lower()}{rng.randint(11, 99)}@gmail.com",
            city=city, state=state, language=lang,
            home=near(6), work=near(12),
            birthdate=f"{rng.randint(1985, 2004)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            carrier=rng.choice(CARRIERS),
            device=rng.choice(DEVICES),
            contacts=[
                Contact(f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                        f"+91{rng.choice('6789')}{rng.randint(10**8, 10**9 - 1)}")
                for _ in range(contact_count)
            ],
        )

    def location(self, tick: int = 0) -> tuple[float, float]:
        """A stable but moving position: the same shadow person, same routine."""
        rng = random.Random(f"{self.seed}:loc:{tick}")
        base = self.work if 9 <= (tick % 24) <= 18 else self.home
        return (round(base[0] + rng.uniform(-0.004, 0.004), 4),
                round(base[1] + rng.uniform(-0.004, 0.004), 4))

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)
