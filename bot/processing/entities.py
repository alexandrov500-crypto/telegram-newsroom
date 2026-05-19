from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from bot.config import bootstrap_env, get_openai_api_key, get_openai_model

logger = logging.getLogger(__name__)

ENTITY_COMPANY = "company"
ENTITY_PERSON = "person"
ENTITY_COUNTRY = "country"
ENTITY_CRYPTO = "crypto"
ENTITY_PRODUCT = "product"
ENTITY_ORGANIZATION = "organization"
ENTITY_TOPIC = "topic"

TOPIC_AI = "AI"
TOPIC_CRYPTO = "Crypto"
TOPIC_REGULATION = "Regulation"
TOPIC_SECURITY = "Security"
TOPIC_MARKETS = "Markets"
TOPIC_STARTUPS = "Startups"

_ALL_TOPICS = (
    TOPIC_AI,
    TOPIC_CRYPTO,
    TOPIC_REGULATION,
    TOPIC_SECURITY,
    TOPIC_MARKETS,
    TOPIC_STARTUPS,
)

# normalized_key -> (display_name, entity_type)
_ALIAS_MAP: dict[str, tuple[str, str]] = {
    "sec": ("SEC", ENTITY_ORGANIZATION),
    "u.s. securities and exchange commission": ("SEC", ENTITY_ORGANIZATION),
    "securities and exchange commission": ("SEC", ENTITY_ORGANIZATION),
    "комиссия sec": ("SEC", ENTITY_ORGANIZATION),
    "komisja sec": ("SEC", ENTITY_ORGANIZATION),
    "komisja pap": ("SEC", ENTITY_ORGANIZATION),
    "openai": ("OpenAI", ENTITY_COMPANY),
    "microsoft": ("Microsoft", ENTITY_COMPANY),
    "google": ("Google", ENTITY_COMPANY),
    "apple": ("Apple", ENTITY_COMPANY),
    "amazon": ("Amazon", ENTITY_COMPANY),
    "meta": ("Meta", ENTITY_COMPANY),
    "tesla": ("Tesla", ENTITY_COMPANY),
    "nvidia": ("NVIDIA", ENTITY_COMPANY),
    "anthropic": ("Anthropic", ENTITY_COMPANY),
    "bitcoin": ("Bitcoin", ENTITY_CRYPTO),
    "ethereum": ("Ethereum", ENTITY_CRYPTO),
    "btc": ("Bitcoin", ENTITY_CRYPTO),
    "eth": ("Ethereum", ENTITY_CRYPTO),
    "united states": ("United States", ENTITY_COUNTRY),
    "u.s.": ("United States", ENTITY_COUNTRY),
    "usa": ("United States", ENTITY_COUNTRY),
    "china": ("China", ENTITY_COUNTRY),
    "european union": ("European Union", ENTITY_COUNTRY),
    "gpt": ("GPT", ENTITY_PRODUCT),
    "gpt-4": ("GPT-4", ENTITY_PRODUCT),
    "chatgpt": ("ChatGPT", ENTITY_PRODUCT),
}

_KNOWN_PHRASES: tuple[tuple[str, str, str], ...] = (
    ("OpenAI", "openai", ENTITY_COMPANY),
    ("Bitcoin ETF", "bitcoin etf", ENTITY_CRYPTO),
    ("Bitcoin", "bitcoin", ENTITY_CRYPTO),
    ("Ethereum", "ethereum", ENTITY_CRYPTO),
    ("SEC", "sec", ENTITY_ORGANIZATION),
    ("Federal Reserve", "federal reserve", ENTITY_ORGANIZATION),
    ("Wall Street", "wall street", ENTITY_TOPIC),
)

_TOPIC_TAG_MAP: dict[str, str] = {
    "ai": TOPIC_AI,
    "artificial_intelligence": TOPIC_AI,
    "machine_learning": TOPIC_AI,
    "openai": TOPIC_AI,
    "crypto": TOPIC_CRYPTO,
    "cryptocurrency": TOPIC_CRYPTO,
    "bitcoin": TOPIC_CRYPTO,
    "ethereum": TOPIC_CRYPTO,
    "etf": TOPIC_CRYPTO,
    "regulation": TOPIC_REGULATION,
    "regulatory": TOPIC_REGULATION,
    "sec": TOPIC_REGULATION,
    "security": TOPIC_SECURITY,
    "cybersecurity": TOPIC_SECURITY,
    "hack": TOPIC_SECURITY,
    "markets": TOPIC_MARKETS,
    "stocks": TOPIC_MARKETS,
    "finance": TOPIC_MARKETS,
    "startup": TOPIC_STARTUPS,
    "startups": TOPIC_STARTUPS,
    "venture": TOPIC_STARTUPS,
}

_ENTITY_TOPIC_MAP: dict[str, list[str]] = {
    "openai": [TOPIC_AI, TOPIC_STARTUPS],
    "anthropic": [TOPIC_AI, TOPIC_STARTUPS],
    "sec": [TOPIC_REGULATION, TOPIC_MARKETS],
    "bitcoin": [TOPIC_CRYPTO, TOPIC_MARKETS],
    "ethereum": [TOPIC_CRYPTO],
    "gpt": [TOPIC_AI],
    "chatgpt": [TOPIC_AI],
}


@dataclass(frozen=True)
class ExtractedEntity:
    display_name: str
    entity_type: str
    normalized_key: str


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)


def normalize_entity_key(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def canonical_entity_key(name: str) -> str:
    """Cross-language alias resolution to a stable canonical key."""
    key = normalize_entity_key(name)
    if key in _ALIAS_MAP:
        display, _ = _ALIAS_MAP[key]
        return normalize_entity_key(display)
    return key


def resolve_entity(name: str, entity_type: str | None = None) -> ExtractedEntity | None:
    key = normalize_entity_key(name)
    if not key or len(key) < 2:
        return None
    if key in _ALIAS_MAP:
        display, etype = _ALIAS_MAP[key]
        canonical = canonical_entity_key(display)
        logger.info(
            "event=entity_normalization_applied raw=%r canonical=%r",
            name,
            display,
        )
        return ExtractedEntity(
            display_name=display,
            entity_type=etype,
            normalized_key=canonical,
        )

    etype = entity_type or ENTITY_TOPIC
    display = name.strip()
    if etype == ENTITY_TOPIC:
        display = display.title()
    elif len(display) <= 5 and display.isupper():
        pass
    elif display.islower():
        display = display.title()
    return ExtractedEntity(display_name=display, entity_type=etype, normalized_key=key)


def _add_entity(bucket: dict[str, ExtractedEntity], entity: ExtractedEntity | None) -> None:
    if entity is None:
        return
    existing = bucket.get(entity.normalized_key)
    if existing is None:
        bucket[entity.normalized_key] = entity
        return
    if existing.entity_type == ENTITY_TOPIC and entity.entity_type != ENTITY_TOPIC:
        bucket[entity.normalized_key] = entity


def _extract_from_tags(tags: list[str]) -> list[ExtractedEntity]:
    found: dict[str, ExtractedEntity] = {}
    for tag in tags:
        key = normalize_entity_key(str(tag))
        if not key:
            continue
        topic = _TOPIC_TAG_MAP.get(key.replace(" ", "_"))
        if topic:
            _add_entity(
                found,
                ExtractedEntity(
                    display_name=topic,
                    entity_type=ENTITY_TOPIC,
                    normalized_key=normalize_entity_key(topic),
                ),
            )
        entity = resolve_entity(str(tag), ENTITY_TOPIC)
        _add_entity(found, entity)
    return list(found.values())


def _extract_rule_based(title: str, summary: str | None, tags: list[str]) -> ExtractionResult:
    text = f"{title}\n{summary or ''}"
    found: dict[str, ExtractedEntity] = {}

    for display, key, etype in _KNOWN_PHRASES:
        if re.search(rf"\b{re.escape(display)}\b", text, re.IGNORECASE):
            _add_entity(found, resolve_entity(display, etype))

    for tag_entity in _extract_from_tags(tags):
        _add_entity(found, tag_entity)

    token_pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")
    for match in token_pattern.findall(text):
        if match.lower() in {"the", "and", "for", "with", "new", "says"}:
            continue
        guessed_type = ENTITY_COMPANY
        if any(word in match.lower() for word in ("fed", "commission", "bank")):
            guessed_type = ENTITY_ORGANIZATION
        _add_entity(found, resolve_entity(match, guessed_type))

    topics: set[str] = set()
    for entity in found.values():
        topics.update(_ENTITY_TOPIC_MAP.get(entity.normalized_key, []))
    for tag in tags:
        topic = _TOPIC_TAG_MAP.get(normalize_entity_key(str(tag)).replace(" ", "_"))
        if topic:
            topics.add(topic)

    entities = list(found.values())[:12]
    return ExtractionResult(entities=entities, topics=sorted(topics))


async def _extract_openai(title: str, summary: str | None, tags: list[str]) -> list[ExtractedEntity]:
    api_key = get_openai_api_key()
    if not api_key:
        return []
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=8.0, max_retries=0)
        response = await client.chat.completions.create(
            model=get_openai_model(),
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract named entities from a news item. "
                        "Return JSON: {\"entities\":[{\"name\":\"...\",\"type\":\"company|person|"
                        "country|crypto|product|organization|topic\"}]}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"title": title, "summary": summary or "", "tags": tags},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=200,
        )
        content = response.choices[0].message.content
        if not content:
            return []
        payload = json.loads(content)
        raw_entities = payload.get("entities") or []
        results: list[ExtractedEntity] = []
        for item in raw_entities:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            etype = str(item.get("type", ENTITY_TOPIC)).strip().lower()
            if etype not in {
                ENTITY_COMPANY,
                ENTITY_PERSON,
                ENTITY_COUNTRY,
                ENTITY_CRYPTO,
                ENTITY_PRODUCT,
                ENTITY_ORGANIZATION,
                ENTITY_TOPIC,
            }:
                etype = ENTITY_TOPIC
            entity = resolve_entity(name, etype)
            if entity:
                results.append(entity)
        return results[:8]
    except Exception:
        logger.exception("event=entity_openai_failed")
        return []


async def extract_entities(
    title: str,
    summary: str | None,
    tags: list[str] | None = None,
    *,
    use_openai: bool = True,
) -> ExtractionResult:
    """
    Extract entities and topics. Never raises.
    """
    bootstrap_env()
    tag_list = list(tags or [])
    try:
        base = _extract_rule_based(title, summary, tag_list)
        merged: dict[str, ExtractedEntity] = {
            entity.normalized_key: entity for entity in base.entities
        }
        if use_openai:
            for entity in await _extract_openai(title, summary, tag_list):
                _add_entity(merged, entity)

        entities = list(merged.values())[:15]
        topics = set(base.topics)
        for entity in entities:
            topics.update(_ENTITY_TOPIC_MAP.get(entity.normalized_key, []))
        for tag in tag_list:
            topic = _TOPIC_TAG_MAP.get(normalize_entity_key(str(tag)).replace(" ", "_"))
            if topic:
                topics.add(topic)

        for entity in entities:
            logger.info(
                "event=entity_extracted name=%r type=%s",
                entity.display_name,
                entity.entity_type,
            )

        return ExtractionResult(entities=entities, topics=sorted(topics))
    except Exception:
        logger.exception("event=entity_extract_failed")
        return ExtractionResult()
