# ADR-037 Gate Status Snapshot

> Live observability dashboard. GitHub remains source of truth; bots alert only.

## Operational closure

| Field | Value |
|-------|-------|
| **STATUS** | **CLOSED** |
| Model | `ADR037UnifiedState` + state contract + validators |
| Next work | Operational UX (A) or read-only simulation (B) only |
| Reference | `docs/adr037-final-operational-form.md` |

> A single computed state system governed by validated transitions and human-approved mutation.

## Current State

| Field | Value |
|-------|-------|
| Phase | `M0_ACTIVE` |
| Last gate | `M0_TO_M1` |
| Last decision | `DEGRADED` |
| Evaluated at | `2026-06-03T20:38:43Z` |
| Risk heat | **CRITICAL** |
| Active incidents | 1 |
| Unacknowledged | 1 |

## Risk Heat Indicator

**CRITICAL** — 2 active HIGH/CRITICAL risk(s) in registry.

| Risk | Level | Title |
|------|-------|-------|
| RISK-007 | CRITICAL | Dual-write schema drift during M2 |
| RISK-009 | HIGH | Story cluster persistence regression |

## Active Incidents

| ID | Severity | Gate | Ack | Status | Reason |
|----|----------|------|-----|--------|--------|
| INC-20260603-AEA028 | CRITICAL | — | **no** | OPEN | Critical risk active: RISK-007 — Dual-write schema drift during M2 |

## Incident Summary

- Total incidents: **1**
- Active: **1**
- Resolved: **0**
- Awaiting ack: **1**

## Last Gate Evaluation

**Warnings:**
- Offline: cannot verify P1-E06-01 on GitHub
- Offline: cannot verify P1-E01-01 on GitHub
- Offline: cannot verify P1-E01-02 on GitHub
- Offline: cannot verify P1-E01-03 on GitHub
- Offline: cannot verify P1-E01-04 on GitHub
- Offline: cannot verify P1-E01-05 on GitHub
- Offline: cannot verify P1-E01-06 on GitHub
- Automated check UNKNOWN: AC-M0-M1-01
- Automated check UNKNOWN: AC-M0-M1-02
- Automated check UNKNOWN: AC-M0-M1-03
- … and 7 more

## Event Stream (last 10)

```json
[
  {
    "timestamp": "2026-06-03T20:38:10Z",
    "phase": "M0_ACTIVE",
    "event_type": "GATE_RESULT",
    "gate": "M0_TO_M1",
    "status": "NO_GO",
    "blockers": [
      "Active Critical risk: RISK-007"
    ],
    "risk_level": "CRITICAL",
    "source": "gate_evaluation_history.jsonl",
    "extra": {
      "warnings": [
        "Offline: cannot verify P1-E06-01 on GitHub",
        "Offline: cannot verify P1-E01-01 on GitHub",
        "Offline: cannot verify P1-E01-02 on GitHub",
        "Offline: cannot verify P1-E01-03 on GitHub",
        "Offline: cannot verify P1-E01-04 on GitHub",
        "Offline: cannot verify P1-E01-05 on GitHub",
        "Offline: cannot verify P1-E01-06 on GitHub",
        "Automated check UNKNOWN: AC-M0-M1-01",
        "Automated check UNKNOWN: AC-M0-M1-02",
        "Automated check UNKNOWN: AC-M0-M1-03",
        "Automated check UNKNOWN: AC-M0-M1-04",
        "Automated check UNKNOWN: AC-M0-M1-05",
        "Automated check UNKNOWN: AC-M0-M1-06",
        "Manual check UNKNOWN: MC-M0-M1-01",
        "Manual check UNKNOWN: MC-M0-M1-02",
        "Manual check UNKNOWN: MC-M0-M1-03",
        "Manual check UNKNOWN: MC-M0-M1-04"
      ],
      "gate_label": "M0 → M1"
    }
  },
  {
    "timestamp": "2026-06-03T20:38:17Z",
    "phase": "M0_ACTIVE",
    "event_type": "GATE_RESULT",
    "gate": "M0_TO_M1",
    "status": "NO_GO",
    "blockers": [
      "Active Critical risk: RISK-007"
    ],
    "risk_level": "CRITICAL",
    "source": "gate_evaluation_history.jsonl",
    "extra": {
      "warnings": [
        "Offline: cannot verify P1-E06-01 on GitHub",
        "Offline: cannot verify P1-E01-01 on GitHub",
        "Offline: cannot verify P1-E01-02 on GitHub",
        "Offline: cannot verify P1-E01-03 on GitHub",
        "Offline: cannot verify P1-E01-04 on GitHub",
        "Offline: cannot verify P1-E01-05 on GitHub",
        "Offline: cannot verify P1-E01-06 on GitHub",
        "Automated check UNKNOWN: AC-M0-M1-01",
        "Automated check UNKNOWN: AC-M0-M1-02",
        "Automated check UNKNOWN: AC-M0-M1-03",
        "Automated check UNKNOWN: AC-M0-M1-04",
        "Automated check UNKNOWN: AC-M0-M1-05",
        "Automated check UNKNOWN: AC-M0-M1-06",
        "Manual check UNKNOWN: MC-M0-M1-01",
        "Manual check UNKNOWN: MC-M0-M1-02",
        "Manual check UNKNOWN: MC-M0-M1-03",
        "Manual check UNKNOWN: MC-M0-M1-04"
      ],
      "gate_label": "M0 → M1"
    }
  },
  {
    "timestamp": "2026-06-03T20:38:43Z",
    "phase": "M0_ACTIVE",
    "event_type": "GATE_RESULT",
    "gate": "M0_TO_M1",
    "status": "DEGRADED",
    "blockers": [],
    "risk_level": "MEDIUM",
    "source": "gate_evaluation_history.jsonl",
    "extra": {
      "warnings": [
        "Offline: cannot verify P1-E06-01 on GitHub",
        "Offline: cannot verify P1-E01-01 on GitHub",
        "Offline: cannot verify P1-E01-02 on GitHub",
        "Offline: cannot verify P1-E01-03 on GitHub",
        "Offline: cannot verify P1-E01-04 on GitHub",
        "Offline: cannot verify P1-E01-05 on GitHub",
        "Offline: cannot verify P1-E01-06 on GitHub",
        "Automated check UNKNOWN: AC-M0-M1-01",
        "Automated check UNKNOWN: AC-M0-M1-02",
        "Automated check UNKNOWN: AC-M0-M1-03",
        "Automated check UNKNOWN: AC-M0-M1-04",
        "Automated check UNKNOWN: AC-M0-M1-05",
        "Automated check UNKNOWN: AC-M0-M1-06",
        "Manual check UNKNOWN: MC-M0-M1-01",
        "Manual check UNKNOWN: MC-M0-M1-02",
        "Manual check UNKNOWN: MC-M0-M1-03",
        "Manual check UNKNOWN: MC-M0-M1-04"
      ],
      "gate_label": "M0 → M1"
    }
  },
  {
    "timestamp": "2026-06-03T20:49:46Z",
    "phase": "M0_ACTIVE",
    "event_type": "RISK_TRIGGER",
    "blockers": [
      "Dual-write schema drift during M2"
    ],
    "risk_level": "CRITICAL",
    "risk_id": "RISK-007",
    "message": "Dual-write schema drift during M2",
    "source": "risk_registry.yaml",
    "extra": {
      "impacted_issues": [
        "P1-E04-02",
        "P1-E01-08"
      ]
    }
  },
  {
    "timestamp": "2026-06-03T20:49:46Z",
    "phase": "M0_ACTIVE",
    "event_type": "RISK_TRIGGER",
    "blockers": [
      "Story cluster persistence regression"
    ],
    "risk_level": "HIGH",
    "risk_id": "RISK-009",
    "message": "Story cluster persistence regression",
    "source": "risk_registry.yaml",
    "extra": {
      "impacted_issues": [
        "P1-E01-07"
      ]
    }
  },
  {
    "timestamp": "2026-06-03T20:49:46Z",
    "phase": "M0_ACTIVE",
    "event_type": "INCIDENT_OPENED",
    "status": "OPEN",
    "blockers": [
      "Critical risk active: RISK-007 — Dual-write schema drift during M2"
    ],
    "risk_level": "CRITICAL",
    "incident_id": "INC-20260603-AEA028",
    "message": "Mitigate risk or update manual_gate_signals before next gate run.",
    "source": "incidents_store.yaml"
  },
  {
    "timestamp": "2026-06-03T21:05:28Z",
    "phase": "M0_ACTIVE",
    "event_type": "RISK_TRIGGER",
    "blockers": [
      "Dual-write schema drift during M2"
    ],
    "risk_level": "CRITICAL",
    "risk_id": "RISK-007",
    "message": "Dual-write schema drift during M2",
    "source": "risk_registry.yaml",
    "extra": {
      "impacted_issues": [
        "P1-E04-02",
        "P1-E01-08"
      ]
    }
  },
  {
    "timestamp": "2026-06-03T21:05:28Z",
    "phase": "M0_ACTIVE",
    "event_type": "RISK_TRIGGER",
    "blockers": [
      "Story cluster persistence regression"
    ],
    "risk_level": "HIGH",
    "risk_id": "RISK-009",
    "message": "Story cluster persistence regression",
    "source": "risk_registry.yaml",
    "extra": {
      "impacted_issues": [
        "P1-E01-07"
      ]
    }
  }
]
```

## Last Telegram Alert

_No Telegram alerts sent yet._

_Updated: 2026-06-04T03:42:16Z_
