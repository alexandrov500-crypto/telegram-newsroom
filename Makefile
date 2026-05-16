# Production-lite developer / operator shortcuts (no orchestration).
# Override paths, e.g.: make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=./ops_out

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

RUNTIME_DIR ?= ./var/runtime
OUTPUT_DIR ?= ./runtime_ops_output
DASHBOARD_OUT ?= var/reports/operational_dashboard.html
RUNTIME_BUNDLE ?=
QUAL_JSON ?=
REGR_JSON ?=

# Bounded lint/format scope (frozen governance modules; not whole-repo migration).
LINT_SCOPE := observability newsroom tests/contracts

.PHONY: help runtime-help demo-runtime docs-map install-dev test ci-test ci-nightly ci-release-check \
	chaos-test chaos-validate soak-test soak-validate drift-validate resilience-validate \
	governance-validate release-readiness security-validate security-readiness \
	scalability-test scalability-validate scalability-diagnostics \
	intelligence-test intelligence-validate ops-summary \
	architecture-validate strategy-test \
	semantics-test semantics-validate semantics-guardrails \
	traceability-test traceability-validate history-guardrails \
	preservation-test preservation-validate preservation-guardrails \
	legacy-test legacy-validate legacy-guardrails \
	live-validation-test live-validation-validate live-telegram-diagnostics \
	staging-verify staging-validate production-validate stabilization-validate ops-tooling-validate \
	lint format-check contracts smoke quality release-check release-qualify \
	runtime-preflight runtime-nightly runtime-dashboard \
	runtime-health runtime-report runtime-report-json runtime-manifest \
	verify-runtime verify-runtime-json validate-recovery replay-runtime \
	check-compatibility check-compatibility-json audit-runtime audit-runtime-json \
	create-baseline compare-baseline compare-baseline-json \
	inspect-capabilities inspect-capabilities-json inspect-policy inspect-policy-json \
	runtime-index runtime-index-json release-check \
	runtime-ops-preflight runtime-ops-nightly

help:
	@echo "Targets: install-dev test ci-test runtime-help demo-runtime docs-map"
	@echo "  make runtime-help   — grouped runtime inspection commands"
	@echo "  make demo-runtime   — suggested demo / inspection sequence"
	@echo "  make docs-map       — key documentation index"
	@echo "  make quality      — contracts + smoke + lint + format-check"
	@echo "  ci-test: runtime → smoke → contracts (sectioned)"
	@echo "  make release-check  — v1.0.0 readiness (contracts+smoke+quality+packaging)"
	@echo "  runtime-nightly / release-qualify — see make runtime-help"
	@echo "  Maintenance: docs/MAINTENANCE_MODE.md | Triage: docs/ISSUE_TRIAGE.md"
	@echo "  Onboarding: docs/START_HERE.md | Pre-tag: make release-check"

demo-runtime:
	@echo "Suggested operational demo (production-lite)"
	@echo ""
	@echo "  1. Install:  make install-dev && cp .env.example .env"
	@echo "  2. Nightly:    make runtime-nightly RUNTIME_DIR=$(RUNTIME_DIR) OUTPUT_DIR=$(OUTPUT_DIR)"
	@echo "  3. Catalog:    make runtime-index OUTPUT_DIR=$(OUTPUT_DIR)"
	@echo "  4. Verify:     make verify-runtime OUTPUT_DIR=$(OUTPUT_DIR)"
	@echo "  5. Recovery:   make validate-recovery OUTPUT_DIR=$(OUTPUT_DIR)"
	@echo ""
	@echo "Dry-run scripts: examples/demo_walkthrough/ (DEMO_RUN=1 to execute)"
	@echo "Sample JSON:     examples/runtime_samples/"
	@echo "CLI transcripts: examples/demo_outputs/"
	@echo "Narrative:       docs/DEMO_WALKTHROUGH.md | Map: docs/ARCHITECTURE_MAP.md"

docs-map:
	@echo "Documentation map (see docs/START_HERE.md)"
	@echo ""
	@echo "  START_HERE.md           — onboarding hub"
	@echo "  ARCHITECTURE_MAP.md     — ASCII flows (runtime, inspection, release)"
	@echo "  ENGINEERING_PHILOSOPHY.md — design rationale"
	@echo "  FAQ.md                  — why not K8s/Prometheus/orchestration"
	@echo "  CONTRIBUTING.md         — contributor rules + contract freeze"
	@echo "  OPERATOR_QUICKSTART.md  — 5-minute runtime inspection"
	@echo "  DEPLOYMENT_QUICKSTART.md — 15-minute production-lite deploy"
	@echo "  RUNTIME_OPS.md          — nightly-check and CLI reference"
	@echo "  RELEASE_PROCESS.md      — tagging and verification"
	@echo "  REPRODUCIBILITY.md      — guaranteed vs not guaranteed"
	@echo "  REPOSITORY_STANDARDS.md — naming and Makefile philosophy"
	@echo "  MAINTENANCE_MODE.md     — post-v1 maintenance-first discipline"
	@echo "  OPERATIONAL_CONFIDENCE.md — v1.0.0 validation summary"
	@echo "  REAL_WORLD_VALIDATION.md — operator friction findings"
	@echo "  BURN_IN_REPORT.md       — production burn-in checklist"
	@echo "  FAILURE_DRILLS.md       — failure drill scenarios"
	@echo "  post_v1_hardening.md    — post-v1 roadmap (planning; opt-in)"
	@echo "  v1_1_operational_validation_report.md — chaos validation summary"
	@echo "  v1_3_operational_envelope.md — long-running deployment limits"
	@echo "  v1_3_resilience_validation_report.md — soak/drift validation"
	@echo "  compatibility_policy.md   — upgrade & freeze rules"
	@echo "  release_governance.md     — release classes & gates"
	@echo "  v1_4_release_governance_report.md"
	@echo "  security/                 — secrets, trust, integrity"
	@echo "  v1_6_security_hardening_report.md"
	@echo "  scalability/            — topologies, capacity, governance (v1.8)"
	@echo "  v1_8_scalability_boundaries_report.md"
	@echo "  runbooks/               — operator recovery playbooks"
	@echo "  runbooks/scaling/       — queue, WAL, retry, Redis, snapshot scaling"
	@echo "  operational_intelligence.md — v1.9 advisory intelligence"
	@echo "  v1_9_operational_intelligence_report.md"
	@echo "  architecture/ (preservation, v2 strategy, complexity budget)"
	@echo "  v2_transition_strategy_report.md"
	@echo "  semantics/              — invariants, forbidden states, recovery (v2.x)"
	@echo "  v2x_operational_semantics_report.md"
	@echo "  stewardship/            — ADR lineage, release archaeology (v2.x)"
	@echo "  v2x_historical_traceability_report.md"
	@echo "  preservation/             — aging, recovery, survivable profile (v2.x)"
	@echo "  v2x_preservation_readiness_report.md"
	@echo "  legacy/                 — legacy state, controlled sunset (v2.x)"
	@echo "  v2x_legacy_stewardship_report.md"
	@echo "  ISSUE_TRIAGE.md         — how issues are classified"
	@echo "  architecture/           — ADRs, RUNTIME_CONTRACTS, RUNTIME_MATURITY"

runtime-help:
	@echo "Runtime inspection (OUTPUT_DIR=$(OUTPUT_DIR))"
	@echo ""
	@echo "Inspect / catalog:"
	@echo "  make runtime-index          python -m newsroom.cli runtime-index"
	@echo "  make runtime-health         health snapshot"
	@echo "  make runtime-report         incident report"
	@echo ""
	@echo "Verify:"
	@echo "  make verify-runtime         manifest + checksums"
	@echo "  make check-compatibility    schema versions"
	@echo ""
	@echo "Recovery:"
	@echo "  make validate-recovery      recovery_report"
	@echo "  make replay-runtime         bundle extract inspection"
	@echo ""
	@echo "Audit:"
	@echo "  make audit-runtime          qualification history + audit snapshot"
	@echo ""
	@echo "Baseline:"
	@echo "  make create-baseline        snapshot known-good"
	@echo "  make compare-baseline       drift vs baseline"
	@echo ""
	@echo "Governance (frozen contracts):"
	@echo "  make inspect-capabilities   deployment profile"
	@echo "  make inspect-policy         operational guardrails"
	@echo ""
	@echo "Pipeline:"
	@echo "  make runtime-nightly        full nightly-check (writes all artifacts)"
	@echo "  make runtime-preflight      preflight only"
	@echo ""
	@echo "Deploy: docs/DEPLOYMENT_QUICKSTART.md | Release: docs/RELEASE_PROCESS.md"
	@echo "Release gate: make release-check | docs/RELEASE_CHECKLIST.md"
	@echo "Maintenance: docs/MAINTENANCE_MODE.md | Report: docs/ISSUE_TRIAGE.md"
	@echo "Contracts: docs/architecture/RUNTIME_CONTRACTS.md (frozen)"

install-dev:
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	$(PIP) install -r requirements-dev.txt
	$(PIP) install -e . --no-deps

test:
	$(PYTHON) -m pytest tests/runtime -q

contracts:
	@echo "=== contracts (runtime + release layout + docs navigation) ==="
	$(PYTHON) -m pytest tests/contracts -q --tb=short

smoke:
	@echo "=== smoke (artifact builders) ==="
	$(PYTHON) -m pytest tests/smoke -q --tb=short

lint:
	@echo "=== lint (governance scope: $(LINT_SCOPE)) ==="
	$(PYTHON) -m ruff check $(LINT_SCOPE)

format-check:
	@echo "=== format-check (governance scope) ==="
	$(PYTHON) -m ruff format --check $(LINT_SCOPE)

quality:
	@echo "=== quality (deterministic section order) ==="
	@$(MAKE) contracts
	@$(MAKE) smoke
	@$(MAKE) lint
	@$(MAKE) format-check
	@echo "=== quality: OK ==="

chaos-test:
	$(PYTHON) -m pytest tests/chaos -q --tb=short

chaos-validate:
	$(PYTHON) tools/chaos_validate.py

soak-test:
	$(PYTHON) -m pytest tests/soak -q --tb=short

soak-validate:
	$(PYTHON) tools/soak_validate.py

drift-validate:
	$(PYTHON) -m pytest tests/soak/test_drift_monitor.py -q --tb=short

resilience-validate: chaos-validate soak-validate
	@echo "=== resilience-validate: OK ==="

governance-validate:
	$(PYTHON) -m pytest tests/contracts/test_v1_4_governance_docs.py tests/contracts/test_release_readiness_tool.py -q --tb=short
	$(PYTHON) tools/release_readiness.py --strict --skip-pytest
	@echo "=== governance-validate: OK ==="

release-readiness:
	$(PYTHON) tools/release_readiness.py --strict

security-validate:
	$(PYTHON) -m pytest tests/contracts/test_v1_6_security_docs.py tests/test_security_redaction.py -q --tb=short
	$(PYTHON) tools/security_readiness.py --strict --skip-tools
	@echo "=== security-validate: OK ==="

security-readiness:
	$(PYTHON) tools/security_readiness.py --strict

scalability-test:
	$(PYTHON) -m pytest tests/scalability -q --tb=short

scalability-diagnostics:
	$(PYTHON) tools/scalability_diagnostics.py

scalability-validate:
	$(PYTHON) -m pytest tests/scalability tests/contracts/test_v1_8_scalability_docs.py -q --tb=short
	$(PYTHON) tools/scalability_diagnostics.py
	@echo "=== scalability-validate: OK ==="

intelligence-test:
	$(PYTHON) -m pytest tests/intelligence -q --tb=short

ops-summary:
	$(PYTHON) tools/ops_summary.py

intelligence-validate:
	$(PYTHON) -m pytest tests/intelligence tests/contracts/test_v1_9_intelligence_docs.py -q --tb=short
	$(PYTHON) tools/ops_summary.py --json > /dev/null
	@echo "=== intelligence-validate: OK ==="

strategy-test:
	$(PYTHON) -m pytest tests/strategy -q --tb=short

architecture-validate:
	$(PYTHON) -m pytest tests/strategy tests/contracts/test_v2_transition_strategy_docs.py -q --tb=short
	$(PYTHON) tools/architecture_guardrails.py
	@echo "=== architecture-validate: OK ==="

semantics-test:
	$(PYTHON) -m pytest tests/semantics -q --tb=short

semantics-guardrails:
	$(PYTHON) tools/semantics_guardrails.py

semantics-validate:
	$(PYTHON) -m pytest tests/semantics tests/contracts/test_v2x_semantics_docs.py -q --tb=short
	$(PYTHON) tools/semantics_guardrails.py
	@echo "=== semantics-validate: OK ==="

traceability-test:
	$(PYTHON) -m pytest tests/traceability -q --tb=short

history-guardrails:
	$(PYTHON) tools/history_guardrails.py

traceability-validate:
	$(PYTHON) -m pytest tests/traceability tests/contracts/test_v2x_traceability_docs.py -q --tb=short
	$(PYTHON) tools/history_guardrails.py
	@echo "=== traceability-validate: OK ==="

preservation-test:
	$(PYTHON) -m pytest tests/preservation -q --tb=short

preservation-guardrails:
	$(PYTHON) tools/preservation_guardrails.py

preservation-validate:
	$(PYTHON) -m pytest tests/preservation tests/contracts/test_v2x_preservation_docs.py -q --tb=short
	$(PYTHON) tools/preservation_guardrails.py
	@echo "=== preservation-validate: OK ==="

legacy-test:
	$(PYTHON) -m pytest tests/legacy -q --tb=short

legacy-guardrails:
	$(PYTHON) tools/legacy_guardrails.py

legacy-validate:
	$(PYTHON) -m pytest tests/legacy tests/contracts/test_v2x_legacy_docs.py -q --tb=short
	$(PYTHON) tools/legacy_guardrails.py
	@echo "=== legacy-validate: OK ==="

live-validation-test:
	$(PYTHON) -m pytest tests/live -q --tb=short -m "not live_telegram"

live-telegram-diagnostics:
	$(PYTHON) tools/live_telegram_diagnostics.py

live-validation-validate:
	$(PYTHON) -m pytest tests/live tests/contracts/test_v3_live_validation_docs.py -q --tb=short -m "not live_telegram"
	$(PYTHON) tools/live_telegram_diagnostics.py
	@echo "=== live-validation-validate: OK ==="

staging-verify:
	$(PYTHON) tools/staging_environment_verify.py

staging-validate:
	$(PYTHON) -m pytest tests/staging tests/contracts/test_staging_signoff_docs.py -q --tb=short
	$(PYTHON) tools/staging_environment_verify.py
	@echo "=== staging-validate: OK ==="

production-validate:
	$(PYTHON) -m pytest tests/contracts/test_production_activation_docs.py -q --tb=short
	@echo "=== production-validate: OK ==="

stabilization-validate:
	$(PYTHON) -m pytest tests/contracts/test_v3_2_stabilization_docs.py -q --tb=short
	@echo "=== stabilization-validate: OK ==="

ops-tooling-validate:
	$(PYTHON) -m pytest tests/tools tests/contracts/test_observability_contracts.py tests/contracts/test_v3_2_p1_docs.py -q --tb=short
	$(PYTHON) tools/ops_metrics_snapshot.py --summary-only > /dev/null
	@echo "=== ops-tooling-validate: OK ==="

ci-test:
	@echo "=== CI: runtime tests ==="
	$(PYTHON) -m pytest tests/runtime -q --tb=short --maxfail=1
	@echo "=== CI: smoke tests ==="
	$(PYTHON) -m pytest tests/smoke -q --tb=short --maxfail=1
	@echo "=== CI: contract tests ==="
	$(PYTHON) -m pytest tests/contracts -q --tb=short --maxfail=1
	@echo "=== CI: complete ==="

ci-nightly:
	bash scripts/nightly_runtime.sh

ci-release-check:
	bash scripts/release_check.sh

runtime-preflight:
	$(PYTHON) tools/runtime_preflight.py $(if $(RUNTIME_DIR),--runtime-dir $(RUNTIME_DIR),)

runtime-nightly:
	$(PYTHON) tools/runtime_ops.py nightly-check \
	  --runtime-dir "$(RUNTIME_DIR)" \
	  --output-dir "$(OUTPUT_DIR)" \
	  --short-soak --strict

runtime-dashboard:
	@mkdir -p "$(dir $(DASHBOARD_OUT))"
	$(PYTHON) tools/build_operational_dashboard.py \
	  $(if $(RUNTIME_BUNDLE),--runtime-bundle $(RUNTIME_BUNDLE),) \
	  $(if $(QUAL_JSON),--qualification-report $(QUAL_JSON),) \
	  $(if $(REGR_JSON),--regression-report $(REGR_JSON),) \
	  --output "$(DASHBOARD_OUT)"

runtime-health:
	$(PYTHON) -m newsroom.cli health --path "$(OUTPUT_DIR)"

runtime-report:
	$(PYTHON) -m newsroom.cli health --path "$(OUTPUT_DIR)" --report

runtime-report-json:
	$(PYTHON) -m newsroom.cli health --path "$(OUTPUT_DIR)" --report --json

runtime-manifest:
	$(PYTHON) -c "from pathlib import Path; from observability.runtime_manifest import rebuild_runtime_manifest; rebuild_runtime_manifest(Path('$(OUTPUT_DIR)'))"

verify-runtime:
	$(PYTHON) -m newsroom.cli verify-runtime --path "$(OUTPUT_DIR)"

verify-runtime-json:
	$(PYTHON) -m newsroom.cli verify-runtime --path "$(OUTPUT_DIR)" --json

validate-recovery:
	$(PYTHON) -m newsroom.cli validate-recovery --path "$(OUTPUT_DIR)" --write

replay-runtime:
	$(PYTHON) -m newsroom.cli replay-runtime --path "$(OUTPUT_DIR)"

check-compatibility:
	$(PYTHON) -m newsroom.cli check-compatibility --path "$(OUTPUT_DIR)" --write

check-compatibility-json:
	$(PYTHON) -m newsroom.cli check-compatibility --path "$(OUTPUT_DIR)" --json

audit-runtime:
	$(PYTHON) -m newsroom.cli audit-runtime --path "$(OUTPUT_DIR)"

audit-runtime-json:
	$(PYTHON) -m newsroom.cli audit-runtime --path "$(OUTPUT_DIR)" --json

create-baseline:
	$(PYTHON) -m newsroom.cli create-baseline --path "$(OUTPUT_DIR)"

compare-baseline:
	$(PYTHON) -m newsroom.cli compare-baseline --path "$(OUTPUT_DIR)"

compare-baseline-json:
	$(PYTHON) -m newsroom.cli compare-baseline --path "$(OUTPUT_DIR)" --json

inspect-capabilities:
	$(PYTHON) -m newsroom.cli inspect-capabilities --path "$(OUTPUT_DIR)" --write

inspect-capabilities-json:
	$(PYTHON) -m newsroom.cli inspect-capabilities --path "$(OUTPUT_DIR)" --json --write

inspect-policy:
	$(PYTHON) -m newsroom.cli inspect-policy --path "$(OUTPUT_DIR)" --write

inspect-policy-json:
	$(PYTHON) -m newsroom.cli inspect-policy --path "$(OUTPUT_DIR)" --json --write

runtime-index:
	$(PYTHON) -m newsroom.cli runtime-index --path "$(OUTPUT_DIR)" --write

runtime-index-json:
	$(PYTHON) -m newsroom.cli runtime-index --path "$(OUTPUT_DIR)" --json --write

release-check:
	@echo "=== release-check: v1.0.0 readiness ==="
	@$(MAKE) contracts
	@$(MAKE) smoke
	@$(MAKE) quality
	@echo "=== release-check: packaging consistency ==="
	$(PYTHON) -m pytest tests/contracts/test_packaging_consistency.py -q --tb=short
	@echo "=== release-check: OK ==="

release-qualify:
	@if [ -z "$(RUNTIME_BUNDLE)" ] || [ -z "$(BASELINE)" ]; then \
		echo "Usage: make release-qualify RUNTIME_BUNDLE=path/to/current.zip BASELINE=path/to/baseline.zip"; \
		exit 2; \
	fi
	@echo "=== release-qualify: bundle qualification ==="
	$(PYTHON) tools/release_qualification.py \
	  --runtime-bundle "$(RUNTIME_BUNDLE)" \
	  --baseline "$(BASELINE)"

# Back-compat aliases (older docs)
runtime-ops-preflight: runtime-preflight

runtime-ops-nightly: runtime-nightly
