"""Content Principle — WHAT / WHY / GLOBAL / MENTAL MODEL."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WHAT = re.compile(
    r"(что\s+произошло|what\s+happened|произошло|сообщает|объявил|raised|cut|introduced|presented)",
    re.I,
)
_WHY = re.compile(r"(почему\s+важ|why\s+it\s+matters|важн|значит|matters|риск|влияет)", re.I)
_GLOBAL = re.compile(r"(глобальн|global|international|world|систем|implication|контекст)", re.I)
_MENTAL = re.compile(
    r"(ментальн|mental\s+model|понимать|takeaway|вывод|одна\s+истор|decision|решени)",
    re.I,
)


@dataclass(frozen=True)
class ContentPrincipleResult:
    has_what: bool
    has_why: bool
    has_global: bool
    has_mental_model: bool
    complete: bool
    missing: tuple[str, ...]
    needs_rewrite: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "has_what": self.has_what,
            "has_why": self.has_why,
            "has_global": self.has_global,
            "has_mental_model": self.has_mental_model,
            "complete": self.complete,
            "missing": list(self.missing),
            "needs_rewrite": self.needs_rewrite,
        }


def evaluate_content_principle(text: str) -> ContentPrincipleResult:
    t = text or ""
    has_what = bool(_WHAT.search(t)) or len(t.split()) >= 30
    has_why = bool(_WHY.search(t))
    has_global = bool(_GLOBAL.search(t))
    has_mental = bool(_MENTAL.search(t))

    missing: list[str] = []
    if not has_what:
        missing.append("what")
    if not has_why:
        missing.append("why")
    if not has_global:
        missing.append("global")
    if not has_mental:
        missing.append("mental_model")

    complete = not missing
    needs_rewrite = len(missing) >= 2

    return ContentPrincipleResult(
        has_what=has_what,
        has_why=has_why,
        has_global=has_global,
        has_mental_model=has_mental,
        complete=complete,
        missing=tuple(missing),
        needs_rewrite=needs_rewrite,
    )


def enrich_content_principle(body: str) -> tuple[str, dict[str, Any]]:
    """Auto-rewrite missing layers via rule-based additions (delegates to AUH transformer)."""
    from app.editorial.audience_unification.auh_transformer import transform_for_unified_audience

    check = evaluate_content_principle(body)
    if check.complete:
        return body, {"rewritten": False, "principle": check.to_dict()}

    out, transform_meta = transform_for_unified_audience(body)
    additions: list[str] = []
    recheck = evaluate_content_principle(out)

    if not recheck.has_global:
        additions.append("Глобальный контекст: событие выходит за рамки одной отрасли.")
    if not recheck.has_mental_model:
        additions.append("Ментальная модель: один сигнал вместо нескольких разрозненных лент.")

    if additions:
        out = f"{out.rstrip()}\n\n" + "\n".join(additions)

    return out.strip(), {
        "rewritten": True,
        "principle_before": check.to_dict(),
        "principle_after": evaluate_content_principle(out).to_dict(),
        "transform": transform_meta,
    }
