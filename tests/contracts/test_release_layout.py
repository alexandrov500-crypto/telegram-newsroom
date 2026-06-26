"""Release packaging layout contracts (deploy templates, samples, docs)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from observability.health_snapshot import SNAPSHOT_KEY_ORDER
from observability.runtime_index import INDEX_KEY_ORDER
from observability.runtime_manifest import MANIFEST_KEY_ORDER
from observability.runtime_policy import REPORT_KEY_ORDER
from observability.runtime_report import REPORT_KEY_ORDER as RUNTIME_REPORT_KEY_ORDER

REPO = Path(__file__).resolve().parents[2]

DEPLOY_FILES = (
    "deploy/example.env.production-lite",
    "deploy/docker-compose.production-lite.yml",
    "deploy/systemd/newsroom-nightly.service",
    "deploy/systemd/newsroom-nightly.timer",
    "deploy/systemd/newsroom-docker-prune.service",
    "deploy/systemd/newsroom-docker-prune.timer",
    "deploy/timeweb/scripts/docker-prune.sh",
    "deploy/timeweb/scripts/install-docker-prune-timer.sh",
    "deploy/timeweb/scripts/install-docker-prune-cron.sh",
)

RUNTIME_SAMPLES = (
    "examples/runtime_samples/health_snapshot.json",
    "examples/runtime_samples/runtime_report.json",
    "examples/runtime_samples/runtime_manifest.json",
    "examples/runtime_samples/runtime_index.json",
    "examples/runtime_samples/policy_report.json",
)

RELEASE_DOCS = (
    "docs/DEPLOYMENT_QUICKSTART.md",
    "docs/DEMO_WALKTHROUGH.md",
    "docs/RELEASE_PROCESS.md",
    "docs/RELEASE_CHECKLIST.md",
    "CHANGELOG.md",
)

MARKDOWN_LINK_RE = re.compile(r"\]\(([^)]+)\)")


@pytest.mark.parametrize("rel", DEPLOY_FILES)
def test_deploy_files_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_root_env_example_exists() -> None:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=" in text
    assert "RUNTIME_STATE_DIR=" in text
    assert "TELEGRAM_API_ID=" in text


def test_production_lite_env_has_runtime_paths() -> None:
    text = (REPO / "deploy/example.env.production-lite").read_text(encoding="utf-8")
    assert "RUNTIME_STATE_DIR=" in text
    assert "RETENTION_PROCESSED_RAW_DAYS=" in text
    assert "LOG_LEVEL=" in text
    assert "PIPELINE_INTERVAL_MINUTES=" in text
    assert "sk-replace" in text or "replace" in text.lower()


def test_compose_production_lite_single_node() -> None:
    text = (REPO / "deploy/docker-compose.production-lite.yml").read_text(encoding="utf-8")
    assert "container_name: telegram-newsroom-production-lite" in text
    assert "restart: unless-stopped" in text
    assert "newsroom_runtime" in text
    assert "prometheus" not in text.lower()
    assert "grafana" not in text.lower()
    assert "redis:" not in text  # no redis service block


def test_systemd_nightly_references_output_dir() -> None:
    svc = (REPO / "deploy/systemd/newsroom-nightly.service").read_text(encoding="utf-8")
    timer = (REPO / "deploy/systemd/newsroom-nightly.timer").read_text(encoding="utf-8")
    assert "OUTPUT_DIR=" in svc
    assert "runtime-nightly" in svc
    assert "journalctl" in svc or "journal" in svc.lower()
    assert "newsroom-nightly.service" in timer


@pytest.mark.parametrize("rel", RUNTIME_SAMPLES)
def test_runtime_samples_valid_json(rel: str) -> None:
    path = REPO / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1


def test_health_sample_key_order() -> None:
    data = json.loads(
        (REPO / "examples/runtime_samples/health_snapshot.json").read_text(encoding="utf-8")
    )
    assert list(data.keys()) == list(SNAPSHOT_KEY_ORDER)
    assert data["pipeline_status"] == "OK"


def test_runtime_index_sample_consistent() -> None:
    data = json.loads(
        (REPO / "examples/runtime_samples/runtime_index.json").read_text(encoding="utf-8")
    )
    assert list(data.keys()) == list(INDEX_KEY_ORDER)
    assert data["index_status"] == "OK"
    assert data["artifact_count"] == len(data["artifacts"])
    assert data["runtime_model"] == "single-node"


def test_manifest_sample_key_order() -> None:
    data = json.loads(
        (REPO / "examples/runtime_samples/runtime_manifest.json").read_text(encoding="utf-8")
    )
    assert list(data.keys()) == list(MANIFEST_KEY_ORDER)
    assert data["bundle_status"] == "OK"


def test_runtime_report_sample_key_order() -> None:
    data = json.loads(
        (REPO / "examples/runtime_samples/runtime_report.json").read_text(encoding="utf-8")
    )
    assert list(data.keys()) == list(RUNTIME_REPORT_KEY_ORDER)
    assert data["incident_level"] == "NONE"


def test_policy_report_sample_key_order() -> None:
    data = json.loads(
        (REPO / "examples/runtime_samples/policy_report.json").read_text(encoding="utf-8")
    )
    assert list(data.keys()) == list(REPORT_KEY_ORDER)
    assert data["policy_validation_status"] == "OK"


@pytest.mark.parametrize("rel", RELEASE_DOCS)
def test_release_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_release_process_states_discipline() -> None:
    text = (REPO / "docs/RELEASE_PROCESS.md").read_text(encoding="utf-8")
    assert "Release discipline is preferred over deployment automation" in text


def test_deployment_quickstart_15_minute_walkthrough() -> None:
    text = (REPO / "docs/DEPLOYMENT_QUICKSTART.md").read_text(encoding="utf-8")
    assert "15-minute production-lite deployment walkthrough" in text


def test_changelog_has_rc1_section() -> None:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "1.0.0-rc1" in text
    assert "Governance freeze" in text or "governance freeze" in text.lower()


def _resolve_doc_link(source: Path, target: str) -> Path | None:
    if target.startswith("http://") or target.startswith("https://"):
        return None
    if target.startswith("#"):
        return None
    clean = target.split("#", 1)[0].strip()
    if not clean:
        return None
    return (source.parent / clean).resolve()


@pytest.mark.parametrize(
    "rel",
    [
        "docs/DEPLOYMENT_QUICKSTART.md",
        "docs/DEMO_WALKTHROUGH.md",
        "README.md",
    ],
)
def test_docs_cross_links_resolve(rel: str) -> None:
    source = REPO / rel
    text = source.read_text(encoding="utf-8")
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group(1).strip()
        resolved = _resolve_doc_link(source, target)
        if resolved is None:
            continue
        try:
            resolved.relative_to(REPO.resolve())
        except ValueError:
            continue
        assert resolved.exists(), f"{rel} broken link: {target} -> {resolved}"


def test_readme_maturity_statement() -> None:
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "operational simplicity over platform-scale extensibility" in text


def test_makefile_runtime_help_references_deploy_docs() -> None:
    proc = __import__("subprocess").run(
        ["make", "-C", str(REPO), "runtime-help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "RELEASE_CHECKLIST" in proc.stdout or "RELEASE" in proc.stdout
