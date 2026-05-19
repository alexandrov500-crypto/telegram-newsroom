from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bot.adaptive.feedback import EditorialFeedbackLoop
from bot.adaptive.policies import OperationalMode, PolicyEngine
from bot.adaptive.service import AdaptiveOperationsService
from bot.adaptive.tuning import SelfTuningEngine
from bot.control_plane.service import ControlPlane
from bot.learning.analytics import LearningAnalyticsEngine
from bot.learning.memory_index import LongTermMemoryIndex
from bot.learning.types import OutcomeLabel
from bot.replay.engine import ReplayEngine
from bot.signals.types import PriorityDecision
from bot.storage.db import init_database
from bot.storage.learning_repository import LearningRepository


class PolicyEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = LearningRepository(self.db_path)
        self.engine = PolicyEngine(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mode_switch(self) -> None:
        policy = self.engine.set_mode(OperationalMode.SAFE_MODE.value)
        self.assertEqual(policy.mode, OperationalMode.SAFE_MODE.value)
        self.assertTrue(policy.require_multi_source_confirmation)
        self.assertGreater(policy.escalation_threshold, 0.8)

    def test_policy_update(self) -> None:
        self.engine.set_mode(OperationalMode.NORMAL.value)
        updated = self.engine.update_policy(escalation_threshold=0.8)
        self.assertAlmostEqual(updated.escalation_threshold, 0.8)


class AdaptiveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.cp = ControlPlane.build(self.db_path, sources=None)
        self.adaptive = AdaptiveOperationsService(self.cp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_policy_suppress_low_priority(self) -> None:
        decision = PriorityDecision(
            editorial_priority_score=0.2,
            action="digest_only",
            reason="test",
        )
        result = self.adaptive.apply_policy_to_priority(
            decision,
            source_count=1,
            importance=0.2,
        )
        self.assertEqual(result.action, "suppress")

    def test_decision_audit_persisted(self) -> None:
        decision = PriorityDecision(
            editorial_priority_score=0.7,
            action="wait_confirmation",
            reason="test_audit",
        )
        self.adaptive.audit_priority_decision(
            decision,
            pending_news_id=1,
            story_id=2,
            signal_id=None,
            scores={"priority": 0.7},
        )
        audits = self.cp.learning.list_recent_audits(limit=1)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["action"], "wait_confirmation")


class FeedbackAndTuningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = LearningRepository(self.db_path)
        self.policies = PolicyEngine(self.repo)
        self.feedback = EditorialFeedbackLoop(self.repo)
        self.tuning = SelfTuningEngine(self.repo, self.policies, self.feedback)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_feedback_loop_outcomes(self) -> None:
        self.feedback.record_signal_outcome(
            signal_id=1,
            story_id=2,
            escalated=True,
            became_major=True,
        )
        self.feedback.record_signal_outcome(
            signal_id=2,
            story_id=3,
            escalated=True,
            became_major=False,
        )
        signals = self.feedback.derive_feedback_signals(window_hours=168)
        self.assertTrue(signals)

    def test_bounded_tuning_rollback(self) -> None:
        self.policies.set_mode(OperationalMode.NORMAL.value)
        self.tuning.sync_from_policy()
        default = self.tuning.rollback_param("escalation_threshold")
        self.assertAlmostEqual(default, 0.72, places=2)


class MemoryAndReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = LearningRepository(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_memory_recall(self) -> None:
        memory = LongTermMemoryIndex(self.repo)
        memory.index_story(
            title="Ukraine ceasefire talks resume",
            summary="Delegates meet in Istanbul.",
            entities=["ukraine"],
        )
        hits = memory.recall("Ukraine ceasefire", limit=3)
        self.assertTrue(hits)

    def test_replay_empty_window(self) -> None:
        policies = PolicyEngine(self.repo)
        engine = ReplayEngine(
            self.db_path,
            learning=self.repo,
            policies=policies,
        )
        result = engine.run(
            from_ts="2099-01-01T00:00:00+00:00",
            to_ts="2099-01-02T00:00:00+00:00",
            run_label="test",
        )
        self.assertEqual(result.events_processed, 0)


class LearningAnalyticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = LearningRepository(self.db_path)
        self.analytics = LearningAnalyticsEngine(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_compute_scores(self) -> None:
        from bot.learning.types import EditorialOutcome

        self.repo.record_outcome(
            EditorialOutcome(
                outcome_type="publish",
                label=OutcomeLabel.POSITIVE.value,
                score=0.8,
                source="reuters",
            ),
        )
        scores = self.analytics.compute_scores(window_hours=168)
        self.assertGreater(scores.signal_precision_score, 0.0)
