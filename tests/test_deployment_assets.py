from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "deploy"


def test_deploy_examples_exist() -> None:
    assert (REPO / "docs" / "WORKER_RUNTIME.md").is_file()
    assert (DEPLOY / "bootstrap.sh").is_file()
    assert (DEPLOY / "docker-compose.prod.yml").is_file()
    assert (DEPLOY / "Dockerfile.example").is_file()
    assert (DEPLOY / "newsroom.service.example").is_file()
    assert (DEPLOY / "env.production.example").is_file()
    assert (DEPLOY / "docker-compose.postgres.yml").is_file()
    assert (DEPLOY / "env.postgres.example").is_file()
    assert (DEPLOY / "logrotate.newsroom.example").is_file()


def test_env_production_example_has_profile() -> None:
    raw = (DEPLOY / "env.production.example").read_text(encoding="utf-8")
    assert "APP_DEPLOYMENT_PROFILE=production" in raw
    assert "DATABASE_URL=" in raw
