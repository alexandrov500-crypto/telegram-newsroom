"""Acquisition attribution — experiment IDs for forward/save correlation."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AcquisitionAttribution:
    experiment_id: str
    loop_stage: str
    cta_variant_id: str
    format_profile: str
    deep_link_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "loop_stage": self.loop_stage,
            "cta_variant_id": self.cta_variant_id,
            "format_profile": self.format_profile,
            "deep_link_hint": self.deep_link_hint,
        }


def build_acquisition_attribution(
    *,
    draft_body: str,
    loop_stage: str,
    cta_variant_id: str,
    format_profile: str,
    channel_username: str = "",
) -> AcquisitionAttribution:
    day = time.strftime("%Y%m%d", time.gmtime())
    body_hash = hashlib.sha256((draft_body or "").encode("utf-8")).hexdigest()[:12]
    experiment_id = f"cp_{day}_{body_hash}"
    channel = (channel_username or "channel").lstrip("@")
    deep_link = f"https://t.me/{channel}?start=ref_{experiment_id}"

    return AcquisitionAttribution(
        experiment_id=experiment_id,
        loop_stage=loop_stage,
        cta_variant_id=cta_variant_id,
        format_profile=format_profile,
        deep_link_hint=deep_link,
    )
