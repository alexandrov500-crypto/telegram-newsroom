from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from bot.storage.learning_repository import LearningRepository


class OperationalMode(str, Enum):
    NORMAL = "normal"
    HIGH_NOISE = "high_noise"
    BREAKING_NEWS = "breaking_news"
    MARKET_CRISIS = "market_crisis"
    GEOPOLITICAL_CRISIS = "geopolitical_crisis"
    SAFE_MODE = "safe_mode"


_MODE_DEFAULTS: dict[str, dict] = {
    OperationalMode.NORMAL.value: {
        "escalation_threshold": 0.72,
        "auto_publish_threshold": 0.88,
        "alert_threshold": 0.75,
        "require_multi_source_confirmation": False,
        "anomaly_z_threshold": 2.8,
        "digest_min_score": 0.45,
        "suppress_below": 0.28,
        "max_daily_ai_cost_usd": 25.0,
        "use_cheap_model_below_importance": 0.35,
    },
    OperationalMode.HIGH_NOISE.value: {
        "escalation_threshold": 0.85,
        "auto_publish_threshold": 0.92,
        "alert_threshold": 0.82,
        "require_multi_source_confirmation": True,
        "anomaly_z_threshold": 2.2,
        "digest_min_score": 0.55,
        "suppress_below": 0.4,
        "max_daily_ai_cost_usd": 15.0,
        "use_cheap_model_below_importance": 0.5,
    },
    OperationalMode.BREAKING_NEWS.value: {
        "escalation_threshold": 0.65,
        "auto_publish_threshold": 0.82,
        "alert_threshold": 0.68,
        "require_multi_source_confirmation": False,
        "anomaly_z_threshold": 2.5,
        "digest_min_score": 0.4,
        "suppress_below": 0.22,
        "max_daily_ai_cost_usd": 40.0,
        "use_cheap_model_below_importance": 0.25,
    },
    OperationalMode.MARKET_CRISIS.value: {
        "escalation_threshold": 0.7,
        "auto_publish_threshold": 0.85,
        "alert_threshold": 0.72,
        "require_multi_source_confirmation": True,
        "anomaly_z_threshold": 2.4,
        "digest_min_score": 0.5,
        "suppress_below": 0.3,
        "max_daily_ai_cost_usd": 30.0,
        "use_cheap_model_below_importance": 0.4,
    },
    OperationalMode.GEOPOLITICAL_CRISIS.value: {
        "escalation_threshold": 0.68,
        "auto_publish_threshold": 0.84,
        "alert_threshold": 0.7,
        "require_multi_source_confirmation": True,
        "anomaly_z_threshold": 2.3,
        "digest_min_score": 0.48,
        "suppress_below": 0.25,
        "max_daily_ai_cost_usd": 35.0,
        "use_cheap_model_below_importance": 0.3,
    },
    OperationalMode.SAFE_MODE.value: {
        "escalation_threshold": 0.9,
        "auto_publish_threshold": 0.95,
        "alert_threshold": 0.88,
        "require_multi_source_confirmation": True,
        "anomaly_z_threshold": 3.2,
        "digest_min_score": 0.6,
        "suppress_below": 0.45,
        "max_daily_ai_cost_usd": 8.0,
        "use_cheap_model_below_importance": 0.7,
    },
}


@dataclass
class PolicyBundle:
    mode: str
    name: str
    escalation_threshold: float = 0.72
    auto_publish_threshold: float = 0.88
    alert_threshold: float = 0.75
    require_multi_source_confirmation: bool = False
    anomaly_z_threshold: float = 2.8
    digest_min_score: float = 0.45
    suppress_below: float = 0.28
    max_daily_ai_cost_usd: float = 25.0
    use_cheap_model_below_importance: float = 0.35
    agents_enabled: dict[str, bool] = field(
        default_factory=lambda: {
            "breaking_news_agent": True,
            "fact_check_agent": True,
            "market_watch_agent": True,
            "geopolitical_agent": True,
            "trend_agent": True,
            "digest_curator_agent": True,
            "risk_review_agent": True,
        },
    )

    @classmethod
    def from_dict(cls, mode: str, data: dict) -> PolicyBundle:
        default_agents = {
            "breaking_news_agent": True,
            "fact_check_agent": True,
            "market_watch_agent": True,
            "geopolitical_agent": True,
            "trend_agent": True,
            "digest_curator_agent": True,
            "risk_review_agent": True,
        }
        agents = data.get("agents_enabled")
        if not isinstance(agents, dict):
            agents = default_agents
        return cls(
            mode=mode,
            name=str(data.get("name", f"{mode}_v1")),
            escalation_threshold=float(data.get("escalation_threshold", 0.72)),
            auto_publish_threshold=float(data.get("auto_publish_threshold", 0.88)),
            alert_threshold=float(data.get("alert_threshold", 0.75)),
            require_multi_source_confirmation=bool(
                data.get("require_multi_source_confirmation", False),
            ),
            anomaly_z_threshold=float(data.get("anomaly_z_threshold", 2.8)),
            digest_min_score=float(data.get("digest_min_score", 0.45)),
            suppress_below=float(data.get("suppress_below", 0.28)),
            max_daily_ai_cost_usd=float(data.get("max_daily_ai_cost_usd", 25.0)),
            use_cheap_model_below_importance=float(
                data.get("use_cheap_model_below_importance", 0.35),
            ),
            agents_enabled=agents,
        )


class PolicyEngine:
    """Load and persist operational policies with mode overrides."""

    POLICY_KEY = "active_policy"
    MODE_KEY = "operational_mode"

    def __init__(self, repository: LearningRepository) -> None:
        self._repo = repository

    def current_mode(self) -> str:
        stored = self._repo.get_policy_json(self.MODE_KEY, {"mode": OperationalMode.NORMAL.value})
        return str(stored.get("mode", OperationalMode.NORMAL.value))

    def set_mode(self, mode: str) -> PolicyBundle:
        if mode not in _MODE_DEFAULTS:
            mode = OperationalMode.NORMAL.value
        self._repo.set_policy_json(self.MODE_KEY, {"mode": mode})
        return self.active_policy()

    def active_policy(self) -> PolicyBundle:
        mode = self.current_mode()
        base = dict(_MODE_DEFAULTS.get(mode, _MODE_DEFAULTS[OperationalMode.NORMAL.value]))
        overrides = self._repo.get_policy_json(self.POLICY_KEY, {})
        base.update(overrides.get(mode, {}))
        base["name"] = f"{mode}_v1"
        return PolicyBundle.from_dict(mode, base)

    def update_policy(self, **kwargs: object) -> PolicyBundle:
        mode = self.current_mode()
        current = self._repo.get_policy_json(self.POLICY_KEY, {})
        mode_overrides = dict(current.get(mode, {}))
        for key, value in kwargs.items():
            if key != "mode":
                mode_overrides[key] = value
        current[mode] = mode_overrides
        self._repo.set_policy_json(self.POLICY_KEY, current)
        from bot.observability.metrics import record_policy_change

        record_policy_change()
        return self.active_policy()

    def toggle_agent(self, agent_name: str, enabled: bool) -> PolicyBundle:
        policy = self.active_policy()
        agents = dict(policy.agents_enabled)
        agents[agent_name] = enabled
        return self.update_policy(agents_enabled=agents)
