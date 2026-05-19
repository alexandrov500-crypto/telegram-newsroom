# Timeweb production-lite — run from deploy/timeweb/
COMPOSE := docker compose -f docker-compose.yml
SERVICE := newsroom

.PHONY: up down logs rebuild restart shell health pull

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

rebuild:
	$(COMPOSE) build --no-cache $(SERVICE)
	$(COMPOSE) up -d $(SERVICE)

restart:
	$(COMPOSE) restart $(SERVICE)

shell:
	$(COMPOSE) exec $(SERVICE) /bin/sh

health:
	$(COMPOSE) exec $(SERVICE) python /app/docker/healthcheck.py
	$(COMPOSE) exec $(SERVICE) python /app/docker/healthcheck.py --readiness

pull:
	$(COMPOSE) pull || true
