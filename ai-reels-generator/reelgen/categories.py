"""Video categories for the library: Claude picks one for every new video; older videos
(made before categories existed) are sorted by keywords in their topic and title."""

from __future__ import annotations

import re

CATEGORIES = (
    "Sports", "Money", "Science & Space", "Tech", "History", "Nature & Animals", "Weather",
    "Entertainment", "India", "Life & People", "Stories", "Comedy",
)

# Checked in order: the first category with a matching word wins.
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Sports", ("cricket", "odi", "one-day", "international", "bcci", "fifa", "coach", "team", "player", "captain", "league", "stadium", "test match", "ipl", "football", "soccer", "kabaddi", "hockey", "tennis", "olympic",
                "match", "cup", "series", "wicket", "goal", "athlete", "chess", "f1", "race", "tournament", "ashes")),
    ("Money", ("money", "rupee", "₹", "crore", "lakh", "price", "gold", "stock", "market", "sensex", "nifty", "salary",
               "tax", "bank", "loan", "invest", "saving", "wealth", "upi", "gst", "inflation", "budget", "compound")),
    ("Science & Space", ("space", "planet", "earth", "sun", "asteroid", "comet", "venus", "mars", "saturn", "jupiter", "moon", "star", "nasa", "isro",
                         "galaxy", "orbit", "satellite", "science", "physics", "chemistry", "brain", "body", "dna")),
    ("Tech", ("tech", "ai", "phone", "iphone", "android", "app", "internet", "computer", "chip", "robot", "software",
              "launch", "gadget", "5g", "microwave", "invention")),
    ("Weather", ("rain", "monsoon", "cloud", "cyclone", "heat", "weather", "storm", "flood", "temperature", "imd")),
    ("Nature & Animals", ("animal", "wildlife", "tiger", "elephant", "bird", "ocean", "forest", "nature", "superpower",
                          "species", "sea", "river")),
    ("History", ("history", "ancient", "pillar", "fort", "temple", "rust", "founded", "empire", "king", "war", "1967", "1971", "century", "origin",
                 "invented", "discovery", "penicillin", "road", "sweden")),
    ("Entertainment", ("movie", "film", "song", "music", "series", "netflix", "actor", "trailer", "bollywood", "game")),
    ("India", ("india", "indian", "mumbai", "delhi", "bharat", "पक्ष", "भारत")),
]


def categorize(report: dict) -> str:
    """Best-guess category for a video that has none saved."""
    if report.get("category") in CATEGORIES:
        return report["category"]
    style = report.get("style")
    if style == "comedy":
        return "Comedy"
    if style == "story":
        return "Stories"
    text = " ".join(str(report.get(k, "")) for k in ("topic", "title", "youtube_title", "subject", "caption")).lower()
    words = set(re.findall(r"[\w₹-]+", text))

    def hit(key: str) -> bool:
        if " " in key or "-" in key:
            return key in text
        # the word or its plural ("crores", "internationals"), never a longer word ("started" isn't "star")
        return key in words or f"{key}s" in words or f"{key}es" in words

    for category, keys in KEYWORDS:
        if any(hit(k) for k in keys):
            return category
    return "Life & People"
