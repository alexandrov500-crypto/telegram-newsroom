"""Light editorial framing — interpretive but uncertainty-aware."""

from __future__ import annotations

import re
from dataclasses import dataclass

_UNCERTAINTY = re.compile(
    r"(вероятно|скорее\s+всего|может|could|likely|possibly|по\s+оценкам|"
    r"если\s+тренд\s+сохранится|при\s+текущих\s+условиях)",
    re.I,
)

_FORBIDDEN_OPINION = re.compile(
    r"(должен\s+упасть|точно\s+выраст|100%|гарантирован|"
    r"one\s+hundred\s+percent|will\s+definitely|buy\s+now|sell\s+now|"
    r"покупай|продавай|шорт|лонг\s+сейчас)",
    re.I,
)

_STANCE_TEMPLATES: dict[str, str] = {
    "macro": "При текущих условиях рынок, вероятно, переоценит ",
    "crypto": "Участники рынка, скорее всего, интерпретируют это как ",
    "geopolitics": "Геополитический контур может усилить ",
    "finance": "Инвесторы, вероятно, пересмотрят ",
    "energy": "Энергетический баланс может сместиться в сторону ",
    "corporate": "Сектор, вероятно, отреагирует на ",
}


@dataclass(frozen=True)
class OpinionFrame:
    text: str
    intensity: float
    safe: bool


def apply_light_framing(body: str, *, vertical: str = "general") -> OpinionFrame:
    t = " ".join((body or "").split()).strip()
    if not t or _FORBIDDEN_OPINION.search(t):
        return OpinionFrame(t, 0.0, False)
    if _UNCERTAINTY.search(t):
        return OpinionFrame(t, 0.25, True)

    first = t.split(".", 1)[0].strip()
    if len(first) < 20:
        return OpinionFrame(t, 0.0, True)

    tpl = _STANCE_TEMPLATES.get(vertical, _STANCE_TEMPLATES["macro"])
    hook = f"{tpl}{first.lower()[:80]}."
    if hook.lower() in t.lower()[:120]:
        return OpinionFrame(t, 0.2, True)

    # Single interpretive prefix, low intensity
    framed = f"{hook}\n\n{t}"
    return OpinionFrame(framed, 0.35, True)
