"""Hard editorial gate — reject low-signal / meme content before draft pipeline."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from ops.pipeline.paths import runtime_root
from utils.metrics import inc

logger = logging.getLogger(__name__)

_MEME = re.compile(
    r"(невозможно\s+отказаться|лол|rofl|😂|🤣|мем\b|meme\b|прикол|"
    r"шутк[аи]|to\s+the\s+moon|not\s+financial\s+advice)",
    re.I,
)
_SUBJECTIVE_FLUFF = re.compile(
    r"(мне\s+кажется|я\s+думаю|на\s+мой\s+взгляд|возможно\s+скоро|"
    r"интересно\s+будет|worth\s+watching|might\s+happen)",
    re.I,
)
_GENERIC_FLUFF = re.compile(
    r"(всё\s+меняется|мир\s+не\s+будет\s+прежним|остаётся\s+наблюдать|"
    r"time\s+will\s+tell|we'll\s+see)",
    re.I,
)

_EVENT_TRIGGER = re.compile(
    r"(принял[аи]?\s+решение|утвердил|запретил|санкци|tariff|"
    r"regulat|policy\s+change|приватизац|privatiz|acquisition|merger|"
    r"ipo\b|earnings|отчётност|launch|shutdown|default|банкрот|"
    r"rate\s+(hike|cut)|ключев.*ставк|войн|invasion|resign|отставк|"
    r"угрожает|threaten|exit(?:s|ing)?\s+market|relocation|реестр|registry)",
    re.I,
)

_ENTITY = re.compile(
    r"\b(ASML|Apple|Google|Tesla|Samsung|Microsoft|Sber|Газпром|Lada|Лада|Aeroflot|Аэрофлот|"
    r"Germany|Германи|Russia|Росси|EU\b|ЕС\b|ECB|Fed|ФРС|ЦБ|SEC|НАТО|NATO|"
    r"Reuters|Bloomberg|Росстат|Минфин|Минюст|Parliament|правительств)\b",
    re.I,
)
_INSTITUTION = re.compile(
    r"(центральн.*банк|central\s+bank|министерств|regulator|бирж[аи]|"
    r"exchange|commission|commission|суд\b|court|парламент)",
    re.I,
)
_GEO_ACTOR = re.compile(
    r"(Украин|Ukraine|Китай|China|США|USA|Washington|Брюссел|Brussels|"
    r"Москв|Moscow|Кремл|Kremlin)",
    re.I,
)

_ACTION_VERB = re.compile(
    r"(угрожает|threaten|покинул|exit|запускает|launch|повысил|снизил|"
    r"штраф|fine|арест|arrest|подписал|signed|одобрил|approved|"
    r"запретил|banned|ввёл|introduced|обновил|updated|расширяет|expand)",
    re.I,
)

_NUMERIC = re.compile(
    r"(\d+[\.,]?\d*\s*%|\$\s*\d|€\s*\d|₽\s*\d|\d+\s*(млрд|млн|bn|mn|billion|million)|"
    r"\d{4}\s*год)",
    re.I,
)
_LEGAL_REG = re.compile(
    r"(закон|законопроект|regulation|regulatory|лицензи|license|"
    r"compliance|санкци|sanction|decree|указ|постановлен)",
    re.I,
)

_MIN_FACT_CHARS = 45


@dataclass(frozen=True)
class GateVerdict:
    allowed: bool
    reason: str
    entity_hint: str = ""
    score_boost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(item: dict[str, Any]) -> str:
    return str(item.get("text") or item.get("content") or "").strip()


def _source(item: dict[str, Any]) -> str:
    return str(item.get("source") or item.get("channel_name") or item.get("channel") or "?")


def _detect_entity_hint(text: str) -> str:
    for rx in (_ENTITY, _INSTITUTION, _GEO_ACTOR):
        m = rx.search(text)
        if m:
            return m.group(0)[:80]
    return "none"


def _has_entity_and_action(text: str) -> bool:
    has_actor = bool(_ENTITY.search(text) or _INSTITUTION.search(text) or _GEO_ACTOR.search(text))
    has_action = bool(_ACTION_VERB.search(text) or _EVENT_TRIGGER.search(text))
    return has_actor and has_action


def _has_event_trigger(text: str) -> bool:
    return bool(_EVENT_TRIGGER.search(text) or _LEGAL_REG.search(text))


def _has_numeric_or_structural(text: str) -> bool:
    return bool(_NUMERIC.search(text))


def _quality_boost(text: str) -> float:
    boost = 0.0
    if _NUMERIC.search(text):
        boost += 0.1
    if _LEGAL_REG.search(text):
        boost += 0.1
    if _ENTITY.search(text) or _INSTITUTION.search(text) or _GEO_ACTOR.search(text):
        boost += 0.1
    return round(min(0.25, boost), 3)


def evaluate_editorial_gate(item: dict[str, Any]) -> GateVerdict:
    text = _text(item)
    if len(text) < 25:
        return GateVerdict(False, "too_short", entity_hint="none")

    if _MEME.search(text):
        return GateVerdict(False, "meme_or_joke", entity_hint=_detect_entity_hint(text))

    if _SUBJECTIVE_FLUFF.search(text) and not _has_event_trigger(text) and not _NUMERIC.search(text):
        return GateVerdict(False, "subjective_without_facts", entity_hint=_detect_entity_hint(text))

    if _GENERIC_FLUFF.search(text) and not _has_entity_and_action(text):
        return GateVerdict(False, "generic_fluff", entity_hint=_detect_entity_hint(text))

    accept_event = _has_event_trigger(text)
    accept_entity_action = _has_entity_and_action(text)
    accept_numeric = _has_numeric_or_structural(text)

    if not (accept_event or accept_entity_action or accept_numeric):
        if len(text) < _MIN_FACT_CHARS:
            return GateVerdict(False, "low_information_density", entity_hint="none")
        if not (_ENTITY.search(text) or _INSTITUTION.search(text) or _GEO_ACTOR.search(text)):
            return GateVerdict(False, "no_named_entity_or_event", entity_hint="none")
        return GateVerdict(False, "no_verifiable_event", entity_hint=_detect_entity_hint(text))

    boost = _quality_boost(text)
    return GateVerdict(
        True,
        "passed_editorial_gate",
        entity_hint=_detect_entity_hint(text),
        score_boost=boost,
    )


def editorial_gate(item: dict[str, Any]) -> bool:
    """Hard filter: True only if item may enter editorial pipeline."""
    return evaluate_editorial_gate(item).allowed


def apply_gate_boost(item: dict[str, Any], verdict: GateVerdict) -> dict[str, Any]:
    if not verdict.allowed or verdict.score_boost <= 0:
        return item
    fs = float(item.get("final_score") or 0.0)
    boosted = round(min(1.0, fs + verdict.score_boost), 4)
    out = {**item, "final_score": boosted, "gate_boost": verdict.score_boost}
    rank = out.get("editorial_rank")
    if isinstance(rank, dict):
        rank = {**rank, "final_score": boosted}
        out["editorial_rank"] = rank
    return out


def log_editorial_drop(item: dict[str, Any], verdict: GateVerdict) -> None:
    source = _source(item)
    logger.info(
        "[EDITORIAL_DROP] reason=%s entity=%s source=%s id=%s",
        verdict.reason,
        verdict.entity_hint or "none",
        source,
        str(item.get("news_id") or item.get("message_id") or "?"),
    )


def persist_gate_rejection(
    runtime_dir: str | None,
    item: dict[str, Any],
    verdict: GateVerdict,
) -> None:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "article_id": str(item.get("news_id") or item.get("ingest_key") or "")[:32],
        "source": _source(item),
        "text_preview": _text(item)[:500],
        "gate": verdict.to_dict(),
    }
    path = runtime_root(runtime_dir) / "gate_rejected_items.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def gate_filter_items(
    items: list[dict[str, Any]],
    *,
    runtime_dir: str | None = None,
    persist: bool = True,
) -> list[dict[str, Any]]:
    """Filter list through hard gate; log and persist drops."""
    passed: list[dict[str, Any]] = []
    for it in items:
        verdict = evaluate_editorial_gate(it)
        if not verdict.allowed:
            log_editorial_drop(it, verdict)
            if persist:
                persist_gate_rejection(runtime_dir, it, verdict)
            inc("editorial_gate_rejected_total")
            continue
        inc("editorial_gate_passed_total")
        passed.append(apply_gate_boost(it, verdict))
    return passed
