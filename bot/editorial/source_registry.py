from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceDisplay:
    key: str
    name: str
    short: str
    emoji: str = "📡"


_SOURCES: dict[str, SourceDisplay] = {
    "ap": SourceDisplay("ap", "Associated Press", "AP", "📡"),
    "associated press": SourceDisplay("ap", "Associated Press", "AP", "📡"),
    "reuters": SourceDisplay("reuters", "Reuters", "Reuters", "🌐"),
    "bloomberg": SourceDisplay("bloomberg", "Bloomberg", "Bloomberg", "📈"),
    "bbc": SourceDisplay("bbc", "BBC News", "BBC", "🇬🇧"),
    "bbc news": SourceDisplay("bbc", "BBC News", "BBC", "🇬🇧"),
    "cnn": SourceDisplay("cnn", "CNN", "CNN", "📺"),
    "nyt": SourceDisplay("nyt", "The New York Times", "NYT", "📰"),
    "new york times": SourceDisplay("nyt", "The New York Times", "NYT", "📰"),
    "the guardian": SourceDisplay("guardian", "The Guardian", "Guardian", "📰"),
    "guardian": SourceDisplay("guardian", "The Guardian", "Guardian", "📰"),
    "afp": SourceDisplay("afp", "Agence France-Presse", "AFP", "📡"),
    "financial times": SourceDisplay("ft", "Financial Times", "FT", "📈"),
    "ft": SourceDisplay("ft", "Financial Times", "FT", "📈"),
    "wsj": SourceDisplay("wsj", "The Wall Street Journal", "WSJ", "📈"),
    "wall street journal": SourceDisplay("wsj", "The Wall Street Journal", "WSJ", "📈"),
}


def normalize_source_key(raw: str | None) -> str:
    if not raw:
        return ""
    key = raw.strip().lower()
    if key.startswith("http"):
        return key
    return key.replace("_", " ").strip()


def resolve_source_display(raw: str | None) -> SourceDisplay:
    key = normalize_source_key(raw)
    if key in _SOURCES:
        return _SOURCES[key]
    if key:
        title = raw.strip() if raw else "Source"
        if len(title) <= 4:
            return SourceDisplay(key, title.upper(), title.upper(), "📡")
        return SourceDisplay(key, title, title[:24], "📡")
    return SourceDisplay("unknown", "Newsroom", "News", "📡")


def format_source_attribution(raw: str | None) -> str:
    """Plain-text attribution for logs; HTML via presentation layer."""
    src = resolve_source_display(raw)
    if src.short and src.short != src.name:
        return f"{src.name} ({src.short})"
    return src.name
