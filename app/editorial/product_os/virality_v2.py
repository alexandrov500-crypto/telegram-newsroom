"""Virality Engine v2 — reference-first growth (forwards > likes)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SURPRISE = re.compile(r"(breaking|срочно|впервые|unexpected|record|surge|обвал|jumped)", re.I)
_COMPRESS = re.compile(r"(единая|several\s+sources|несколько\s+источник|compress|world\s+signal|сводк)", re.I)
_IDENTITY = re.compile(r"(коллег|team|investor|инвестор|decision|решени|ваша\s+сфер)", re.I)
_CLARITY = re.compile(r"(что\s+произошло|почему\s+важ|why\s+it\s+matters|ментальн|what\s+changes)", re.I)
_CROSS = re.compile(r"(global|глобальн|cross.?domain|markets.*ai|геополит.*рынок)", re.I)


@dataclass(frozen=True)
class ReferenceForwardScore:
    clarity: float
    surprise: float
    usefulness: float
    compressibility: float
    identity_value: float
    total: float
    trigger_forward: bool
    forward_prediction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "clarity": round(self.clarity, 2),
            "surprise": round(self.surprise, 2),
            "usefulness": round(self.usefulness, 2),
            "compressibility": round(self.compressibility, 2),
            "identity_value": round(self.identity_value, 2),
            "total": round(self.total, 2),
            "trigger_forward": self.trigger_forward,
            "forward_prediction": round(self.forward_prediction, 2),
        }


def compute_reference_forward_score(
    text: str,
    *,
    cluster_size: int = 1,
    cross_domain_density: float = 0.0,
    has_why_it_matters: bool = False,
) -> ReferenceForwardScore:
    t = text or ""
    words = len(t.split())

    clarity = 40.0
    if _CLARITY.search(t):
        clarity += 35.0
    if words >= 80 and words <= 220:
        clarity += 15.0
    clarity = min(100.0, clarity)

    surprise = 35.0 + (25.0 if _SURPRISE.search(t) else 0.0)
    surprise = min(100.0, surprise)

    usefulness = 30.0 + (30.0 if has_why_it_matters or _CLARITY.search(t) else 0.0)
    usefulness += cross_domain_density * 25.0
    usefulness = min(100.0, usefulness)

    compressibility = 25.0 + (35.0 if _COMPRESS.search(t) else 0.0)
    compressibility += min(25.0, cluster_size * 8.0)
    compressibility = min(100.0, compressibility)

    identity = 30.0 + (25.0 if _IDENTITY.search(t) else 0.0)
    identity += 15.0 if _CROSS.search(t) else 0.0
    identity = min(100.0, identity)

    total = (clarity + surprise + usefulness + compressibility + identity) / 5.0
    trigger = (
        total >= 62
        and clarity >= 55
        and (compressibility >= 50 or cluster_size >= 2)
        and (usefulness >= 55 or has_why_it_matters)
    )
    forward_pred = min(100.0, total * 0.85 + (10 if trigger else 0))

    return ReferenceForwardScore(
        clarity=clarity,
        surprise=surprise,
        usefulness=usefulness,
        compressibility=compressibility,
        identity_value=identity,
        total=total,
        trigger_forward=trigger,
        forward_prediction=forward_pred,
    )
