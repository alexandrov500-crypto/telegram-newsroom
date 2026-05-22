# Timeweb production-lite — run from deploy/timeweb/
COMPOSE := docker compose -f docker-compose.yml
SERVICE := newsroom

.PHONY: up down logs rebuild restart shell health pull gen-session go-live go-live-verify env-local

env-local:
	bash scripts/build-vps-env.sh

go-live:
	bash scripts/go-live-start.sh

go-live-verify:
	bash scripts/go-live-verify.sh

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

rebuild:
	GIT_SHA=$$(git -C ../.. rev-parse --short HEAD 2>/dev/null || echo unknown) \
	BUILD_TIMESTAMP=$$(date -u +%Y-%m-%dT%H:%M:%SZ) \
	BUILD_BRANCH=$$(git -C ../.. rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown) \
	BUILD_VERSION=$$(python3 -c "from newsroom._version import VERSION; print(VERSION)" 2>/dev/null || echo unknown) \
	$(COMPOSE) build --no-cache $(SERVICE)
	$(COMPOSE) up -d $(SERVICE)

restart:
	$(COMPOSE) restart $(SERVICE)

shell:
	$(COMPOSE) exec $(SERVICE) /bin/sh

gen-session:
	$(COMPOSE) run --rm -it $(SERVICE) python gen_session.py --write-env

health:
	$(COMPOSE) exec $(SERVICE) python /app/docker/healthcheck.py
	$(COMPOSE) exec $(SERVICE) python /app/docker/healthcheck.py --readiness

pull:
	$(COMPOSE) pull || true
