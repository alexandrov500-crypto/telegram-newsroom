from __future__ import annotations

from tests.conftest import minimal_test_settings
from utils.runtime_reports import (
    build_editorial_activity_report,
    build_runtime_summary_report,
    write_report,
)


def test_runtime_reports_json_and_html(tmp_path) -> None:
    s = minimal_test_settings()
    r = build_runtime_summary_report(s)
    assert r["report"] == "runtime_summary"
    p1 = tmp_path / "r.json"
    write_report(p1, r, fmt="json")
    assert p1.read_text(encoding="utf-8").startswith("{")

    p2 = tmp_path / "r.html"
    write_report(p2, r, fmt="html")
    assert "<html" in p2.read_text(encoding="utf-8").lower()


def test_editorial_report_shape(tmp_path) -> None:
    s = minimal_test_settings()
    rep = build_editorial_activity_report(s)
    assert rep.get("report") == "editorial_activity"
    assert "insights" in rep
