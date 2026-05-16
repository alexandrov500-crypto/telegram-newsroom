from __future__ import annotations

from pathlib import Path

from utils import source_reputation as sr


def test_source_reputation_roundtrip(tmp_path: Path) -> None:
    base = str(tmp_path / "rt")
    sr.record_publish_for_channels(["@Alpha", "@alpha"], runtime_dir=base)
    sr.record_reject_for_channels(["@Beta"], runtime_dir=base)
    sr.record_duplicate_signal_for_channels(["@Gamma"], runtime_dir=base)
    m = sr.export_channel_scores_for_priority(base)
    assert "@alpha" in m
    assert m["@alpha"]["score"] > 0
