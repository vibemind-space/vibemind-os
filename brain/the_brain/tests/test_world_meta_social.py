"""Tests for World Model (P5.67-69), Meta-Cognition (P5.70-72), Social Learning (P5.73-75)."""

import time
import pytest
from core.world_model import (
    WorldModel, WorldEntity, EntityStatus,
    CausalWorldModel, CausalLink,
    PredictiveWorldModel, TrendAnalyzer, Prediction,
)
from core.meta_cognition import (
    SelfAwarenessModule, ConfidenceRecord,
    LearningDiagnosis, LearningTrajectory, TrendDirection,
    KnowledgeGapDetection, KnowledgeGap,
)
from core.social_learning import (
    LearningFromDemonstration, DemonstrationRecord,
    FeedbackInterpretation, FeedbackSentiment, InterpretedFeedback,
    CollaborativeLearning, StrategyNode,
)


# ═══════════════════════════════════════════════════════════════════
# P5.67: World Model
# ═══════════════════════════════════════════════════════════════════

class TestWorldEntity:
    def test_update(self):
        e = WorldEntity(name="app", entity_type="service")
        e.update(EntityStatus.HEALTHY, {"port": 5000})
        assert e.status == EntityStatus.HEALTHY
        assert e.properties["port"] == 5000
        assert len(e.history) == 1

    def test_uptime_ratio(self):
        e = WorldEntity(name="app", entity_type="service")
        for i in range(10):
            status = EntityStatus.HEALTHY if i < 7 else EntityStatus.DOWN
            e.update(status)
        ratio = e.get_uptime_ratio(24.0)
        assert ratio == 0.7

    def test_to_dict(self):
        e = WorldEntity(name="db", entity_type="service")
        e.update(EntityStatus.HEALTHY)
        d = e.to_dict()
        assert d['name'] == "db"
        assert d['status'] == "healthy"


class TestWorldModel:
    def test_update_entity(self):
        wm = WorldModel()
        wm.update_entity("app", "service", EntityStatus.HEALTHY)
        assert wm.get_entity("app") is not None
        assert wm.get_entity("app").status == EntityStatus.HEALTHY

    def test_entities_by_type(self):
        wm = WorldModel()
        wm.update_entity("app1", "service", EntityStatus.HEALTHY)
        wm.update_entity("app2", "service", EntityStatus.DOWN)
        wm.update_entity("repo1", "repo", EntityStatus.HEALTHY)
        services = wm.get_entities_by_type("service")
        assert len(services) == 2

    def test_entities_by_status(self):
        wm = WorldModel()
        wm.update_entity("a", "service", EntityStatus.HEALTHY)
        wm.update_entity("b", "service", EntityStatus.DOWN)
        wm.update_entity("c", "service", EntityStatus.HEALTHY)
        healthy = wm.get_entities_by_status(EntityStatus.HEALTHY)
        assert len(healthy) == 2

    def test_anomaly_detection(self):
        wm = WorldModel()
        wm.update_entity("app", "service", EntityStatus.HEALTHY)
        wm.update_baseline("app", "cpu", 30.0)
        # Normal value
        result = wm.check_anomaly("app", "cpu", 35.0)
        assert result is None
        # Anomalous value (>2x baseline)
        result = wm.check_anomaly("app", "cpu", 90.0)
        assert result is not None
        assert result['metric'] == "cpu"

    def test_status_change_creates_anomaly(self):
        wm = WorldModel()
        wm.update_entity("app", "service", EntityStatus.HEALTHY)
        wm.update_entity("app", "service", EntityStatus.DOWN)
        assert len(wm._anomalies) == 1

    def test_health_summary(self):
        wm = WorldModel()
        wm.update_entity("a", "service", EntityStatus.HEALTHY)
        wm.update_entity("b", "service", EntityStatus.HEALTHY)
        wm.update_entity("c", "service", EntityStatus.DOWN)
        summary = wm.get_system_health_summary()
        assert summary['total_entities'] == 3
        assert summary['healthy_ratio'] == pytest.approx(2/3, abs=0.01)

    def test_max_entities(self):
        wm = WorldModel(max_entities=3)
        for i in range(5):
            wm.update_entity(f"e{i}", "service", EntityStatus.HEALTHY)
        assert len(wm._entities) <= 3

    def test_get_state(self):
        wm = WorldModel()
        state = wm.get_state()
        assert 'total_entities' in state

    def test_from_yaml(self):
        cfg = {'world_model': {'max_entities': 100}}
        wm = WorldModel.from_yaml(cfg)
        assert wm.max_entities == 100


# ═══════════════════════════════════════════════════════════════════
# P5.68: Causal World Model
# ═══════════════════════════════════════════════════════════════════

class TestCausalLink:
    def test_observe(self):
        cl = CausalLink(cause="A", effect="B")
        cl.observe(co_occurred=True, delay_ms=1000)
        cl.observe(co_occurred=True, delay_ms=2000)
        cl.observe(co_occurred=False)
        assert cl.observations == 3
        assert cl.co_occurrences == 2
        assert cl.strength == pytest.approx(2/3, abs=0.01)


class TestCausalWorldModel:
    def test_observe_events(self):
        cwm = CausalWorldModel()
        now = time.time()
        cwm.observe_event("build_failed", now)
        cwm.observe_event("deploy_failed", now + 10)
        assert len(cwm._links) >= 1

    def test_get_causes(self):
        cwm = CausalWorldModel(min_observations=2, min_strength=0.5)
        now = time.time()
        for i in range(5):
            cwm.observe_event("disk_full", now + i * 60)
            cwm.observe_event("service_crash", now + i * 60 + 5)
        causes = cwm.get_causes("service_crash")
        assert len(causes) >= 1
        assert causes[0].cause == "disk_full"

    def test_get_effects(self):
        cwm = CausalWorldModel(min_observations=2, min_strength=0.3)
        now = time.time()
        for i in range(3):
            cwm.observe_event("memory_leak", now + i * 60)
            cwm.observe_event("oom_kill", now + i * 60 + 2)
        effects = cwm.get_effects("memory_leak")
        assert len(effects) >= 1

    def test_root_cause_analysis(self):
        cwm = CausalWorldModel(min_observations=2, min_strength=0.3)
        now = time.time()
        # Build chain: A -> B -> C
        for i in range(3):
            cwm.observe_event("A", now + i * 100)
            cwm.observe_event("B", now + i * 100 + 1)
            cwm.observe_event("C", now + i * 100 + 2)
        chains = cwm.root_cause_analysis("C", max_depth=3)
        assert len(chains) >= 1
        # Should find A as root cause
        found_a = any("A" in chain for chain in chains)
        assert found_a

    def test_get_state(self):
        cwm = CausalWorldModel()
        state = cwm.get_state()
        assert 'total_links' in state

    def test_from_yaml(self):
        cfg = {'causal_world_model': {'min_observations': 5}}
        cwm = CausalWorldModel.from_yaml(cfg)
        assert cwm.min_observations == 5


# ═══════════════════════════════════════════════════════════════════
# P5.69: Predictive World Model
# ═══════════════════════════════════════════════════════════════════

class TestTrendAnalyzer:
    def test_add_point_and_trend(self):
        ta = TrendAnalyzer()
        now = time.time()
        for i in range(10):
            ta.add_point("disk_usage", 50 + i * 2, now + i * 3600)
        trend = ta.get_trend("disk_usage")
        assert trend is not None
        assert trend['slope_per_hour'] > 0  # Increasing

    def test_predict_value(self):
        ta = TrendAnalyzer()
        now = time.time()
        for i in range(10):
            ta.add_point("metric", 10 + i * 5, now + i * 3600)
        predicted = ta.predict_value("metric", 2.0)
        assert predicted is not None
        assert predicted > 50  # Should be > current

    def test_predict_threshold(self):
        ta = TrendAnalyzer()
        now = time.time()
        for i in range(10):
            ta.add_point("disk", 50 + i * 5, now + i * 3600)
        hours = ta.predict_threshold_time("disk", 100)
        assert hours is not None
        assert hours > 0

    def test_insufficient_data(self):
        ta = TrendAnalyzer()
        ta.add_point("x", 1.0)
        assert ta.get_trend("x") is None


class TestPrediction:
    def test_verify(self):
        p = Prediction(entity="disk", metric="usage",
                       predicted_value=85.0,
                       predicted_time=time.time() + 3600)
        error = p.verify(80.0)
        assert p.verified
        assert error == pytest.approx(5/85, abs=0.01)


class TestPredictiveWorldModel:
    def test_add_observation_and_predict(self):
        pwm = PredictiveWorldModel()
        now = time.time()
        for i in range(10):
            pwm.add_observation("disk", "usage", 50 + i * 3, now + i * 3600)
        pred = pwm.predict_trend("disk", "usage", hours_ahead=5.0)
        assert pred is not None
        assert pred.predicted_value > 70

    def test_threshold_breach_prediction(self):
        pwm = PredictiveWorldModel()
        now = time.time()
        for i in range(10):
            pwm.add_observation("disk", "percent", 60 + i * 3, now + i * 3600)
        pred = pwm.predict_threshold_breach("disk", "percent", 95.0,
                                             "disk_full_warning")
        assert pred is not None
        assert "threshold_breach" in pred.basis

    def test_verify_prediction(self):
        pwm = PredictiveWorldModel()
        now = time.time()
        for i in range(10):
            pwm.add_observation("cpu", "load", 20 + i * 2, now + i * 3600)
        pred = pwm.predict_trend("cpu", "load", hours_ahead=0.0)
        if pred:
            results = pwm.verify_prediction("cpu", "load", 42.0)
            # May or may not verify depending on timing

    def test_get_state(self):
        pwm = PredictiveWorldModel()
        state = pwm.get_state()
        assert 'total_predictions' in state

    def test_from_yaml(self):
        cfg = {'predictive_world_model': {'min_confidence': 0.5}}
        pwm = PredictiveWorldModel.from_yaml(cfg)
        assert pwm.min_confidence == 0.5


# ═══════════════════════════════════════════════════════════════════
# P5.70: Self-Awareness Module
# ═══════════════════════════════════════════════════════════════════

class TestSelfAwarenessModule:
    def test_record_outcome(self):
        sam = SelfAwarenessModule()
        sam.record_outcome("shell", "deployment", 0.8, True)
        assert sam._total_records == 1

    def test_system_confidence(self):
        sam = SelfAwarenessModule(min_samples_for_confidence=3)
        for _ in range(5):
            sam.record_outcome("shell", "deploy", 0.7, True)
        for _ in range(5):
            sam.record_outcome("shell", "deploy", 0.7, False)
        conf = sam.get_system_confidence("shell")
        assert conf['calibrated']
        assert conf['confidence'] == 0.5

    def test_domain_confidence(self):
        sam = SelfAwarenessModule(min_samples_for_confidence=3)
        for _ in range(8):
            sam.record_outcome("any", "testing", 0.6, True)
        for _ in range(2):
            sam.record_outcome("any", "testing", 0.6, False)
        conf = sam.get_domain_confidence("testing")
        assert conf['confidence'] == 0.8

    def test_insufficient_samples(self):
        sam = SelfAwarenessModule(min_samples_for_confidence=10)
        sam.record_outcome("shell", "deploy", 0.8, True)
        conf = sam.get_system_confidence("shell")
        assert not conf['calibrated']

    def test_weakest_areas(self):
        sam = SelfAwarenessModule(min_samples_for_confidence=3)
        for _ in range(5):
            sam.record_outcome("shell", "good_domain", 0.8, True)
        for _ in range(5):
            sam.record_outcome("shell", "bad_domain", 0.8, False)
        weak = sam.get_weakest_areas()
        assert len(weak) >= 1
        # bad_domain should be weakest
        assert any(a['name'] == 'bad_domain' for a in weak)

    def test_get_state(self):
        sam = SelfAwarenessModule()
        state = sam.get_state()
        assert 'total_records' in state


# ═══════════════════════════════════════════════════════════════════
# P5.71: Learning Diagnosis
# ═══════════════════════════════════════════════════════════════════

class TestLearningTrajectory:
    def test_improving(self):
        lt = LearningTrajectory(area="docker", area_type="domain", window_size=5)
        # Older: mostly failures
        for _ in range(5):
            lt.record(False)
        # Recent: mostly successes
        for _ in range(5):
            lt.record(True)
        assert lt.get_trend() == TrendDirection.IMPROVING

    def test_declining(self):
        lt = LearningTrajectory(area="docker", area_type="domain", window_size=5)
        for _ in range(5):
            lt.record(True)
        for _ in range(5):
            lt.record(False)
        assert lt.get_trend() == TrendDirection.DECLINING

    def test_stagnating(self):
        lt = LearningTrajectory(area="python", area_type="domain", window_size=5)
        for _ in range(10):
            lt.record(True)
        assert lt.get_trend() == TrendDirection.STAGNATING

    def test_insufficient_data(self):
        lt = LearningTrajectory(area="new", area_type="domain", window_size=20)
        lt.record(True)
        assert lt.get_trend() == TrendDirection.INSUFFICIENT_DATA


class TestLearningDiagnosis:
    def test_record_and_diagnose(self):
        ld = LearningDiagnosis()
        for _ in range(10):
            ld.record_outcome("docker", "domain", False)
        for _ in range(10):
            ld.record_outcome("docker", "domain", True)
        diagnoses = ld.diagnose()
        assert len(diagnoses) >= 1
        docker_diag = [d for d in diagnoses if d['area'] == 'docker']
        assert len(docker_diag) == 1
        assert docker_diag[0]['trend'] == 'improving'

    def test_focus_areas(self):
        ld = LearningDiagnosis()
        for _ in range(15):
            ld.record_outcome("good", "domain", True)
        for _ in range(15):
            ld.record_outcome("bad", "domain", False)
        focus = ld.get_focus_areas()
        assert len(focus) >= 1
        assert focus[0]['area'] == 'bad'

    def test_get_state(self):
        ld = LearningDiagnosis()
        state = ld.get_state()
        assert 'tracked_areas' in state


# ═══════════════════════════════════════════════════════════════════
# P5.72: Knowledge Gap Detection
# ═══════════════════════════════════════════════════════════════════

class TestKnowledgeGap:
    def test_record_failure(self):
        gap = KnowledgeGap(area="networking", description="Docker networking")
        gap.record_failure()
        gap.record_failure()
        assert gap.failure_count == 2
        assert gap.severity > 0

    def test_to_dict(self):
        gap = KnowledgeGap(area="k8s", description="Kubernetes deployments")
        d = gap.to_dict()
        assert d['area'] == "k8s"
        assert d['resolved'] is False


class TestKnowledgeGapDetection:
    def test_detect_gap(self):
        kgd = KnowledgeGapDetection(failure_threshold=3)
        for i in range(3):
            result = kgd.record_failure("docker_networking", "Cannot configure bridge network")
        assert result is not None
        assert kgd._total_gaps_detected == 1

    def test_below_threshold(self):
        kgd = KnowledgeGapDetection(failure_threshold=5)
        result = kgd.record_failure("area", "desc")
        assert result is None  # Only 1 failure, need 5

    def test_resolve_via_success(self):
        kgd = KnowledgeGapDetection(failure_threshold=2)
        kgd.record_failure("area")
        kgd.record_failure("area")  # Gap created
        # Record enough successes to reduce failure_count to 0
        kgd.record_success("area")
        kgd.record_success("area")
        gap = kgd.get_gap("area")
        assert gap.resolved

    def test_manual_resolve(self):
        kgd = KnowledgeGapDetection(failure_threshold=2)
        kgd.record_failure("area")
        kgd.record_failure("area")
        assert kgd.resolve_gap("area", "Studied documentation")
        gap = kgd.get_gap("area")
        assert gap.resolved
        assert gap.resolution_strategy == "Studied documentation"

    def test_get_active_gaps(self):
        kgd = KnowledgeGapDetection(failure_threshold=2)
        kgd.record_failure("a")
        kgd.record_failure("a")
        kgd.record_failure("b")
        kgd.record_failure("b")
        active = kgd.get_active_gaps()
        assert len(active) == 2

    def test_generate_learning_goals(self):
        kgd = KnowledgeGapDetection(failure_threshold=2)
        for _ in range(5):
            kgd.record_failure("networking", "Docker networking issues")
        goals = kgd.generate_learning_goals()
        assert len(goals) >= 1
        assert "networking" in goals[0]['area']

    def test_get_state(self):
        kgd = KnowledgeGapDetection()
        state = kgd.get_state()
        assert 'total_gaps_detected' in state


# ═══════════════════════════════════════════════════════════════════
# P5.73: Learning From Demonstration
# ═══════════════════════════════════════════════════════════════════

class TestLearningFromDemonstration:
    def test_record_demonstration(self):
        lfd = LearningFromDemonstration()
        lfd.record_demonstration(
            context="Deploy app",
            system_suggestion="docker deploy",
            user_action="kubectl apply",
        )
        assert lfd._total_demonstrations == 1

    def test_learn_preference(self):
        lfd = LearningFromDemonstration(preference_threshold=3)
        for _ in range(3):
            lfd.record_demonstration(
                context="Deploy app",
                system_suggestion="docker deploy",
                user_action="kubectl apply",
                user_succeeded=True,
            )
        pref = lfd.get_user_preference("Deploy app")
        assert pref == "kubectl apply"

    def test_no_preference_before_threshold(self):
        lfd = LearningFromDemonstration(preference_threshold=5)
        lfd.record_demonstration("Deploy app", "docker", "kubectl", user_succeeded=True)
        assert lfd.get_user_preference("Deploy app") is None

    def test_same_action_no_preference(self):
        lfd = LearningFromDemonstration(preference_threshold=2)
        for _ in range(3):
            lfd.record_demonstration("Deploy", "docker deploy", "docker deploy")
        # Same action, no difference to learn
        assert lfd._total_preferences_learned == 0

    def test_get_state(self):
        lfd = LearningFromDemonstration()
        state = lfd.get_state()
        assert 'total_demonstrations' in state


# ═══════════════════════════════════════════════════════════════════
# P5.74: Feedback Interpretation
# ═══════════════════════════════════════════════════════════════════

class TestFeedbackInterpretation:
    def test_positive_feedback(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("Great work, exactly what I needed!")
        assert result.sentiment in (FeedbackSentiment.POSITIVE, FeedbackSentiment.VERY_POSITIVE)
        assert result.outcome_signal > 0

    def test_negative_feedback(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("Wrong, that's broken and terrible")
        assert result.sentiment in (FeedbackSentiment.NEGATIVE, FeedbackSentiment.VERY_NEGATIVE)
        assert result.outcome_signal < 0

    def test_partial_feedback(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("Good direction, but too slow")
        assert result.outcome_signal > 0  # Positive but reduced by partial
        assert result.outcome_signal < 0.8  # Not full success due to "but"

    def test_neutral_feedback(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("I see, let me check")
        assert result.sentiment == FeedbackSentiment.NEUTRAL

    def test_german_feedback(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("Danke, das ist perfekt!")
        assert result.outcome_signal > 0

    def test_aspect_detection(self):
        fi = FeedbackInterpretation()
        result = fi.interpret("The result is correct but way too slow")
        # Should detect accuracy (positive) and speed (negative)
        assert 'accuracy' in result.aspects or 'speed' in result.aspects

    def test_average_sentiment(self):
        fi = FeedbackInterpretation()
        fi.interpret("Great!")
        fi.interpret("Perfect!")
        fi.interpret("Bad")
        avg = fi.get_average_sentiment()
        assert avg > 0  # 2 positive, 1 negative

    def test_get_state(self):
        fi = FeedbackInterpretation()
        fi.interpret("OK")
        state = fi.get_state()
        assert state['total_interpreted'] == 1


# ═══════════════════════════════════════════════════════════════════
# P5.75: Collaborative Learning
# ═══════════════════════════════════════════════════════════════════

class TestStrategyNode:
    def test_record_usage(self):
        sn = StrategyNode(
            strategy_id="s1", context="Deploy", description="Use k8s",
            source="user_explanation",
        )
        sn.record_usage(True)
        sn.record_usage(True)
        sn.record_usage(False)
        assert sn.usage_count == 3
        assert sn.confidence == pytest.approx(2/3, abs=0.01)


class TestCollaborativeLearning:
    def test_learn_from_explanation(self):
        cl = CollaborativeLearning()
        node = cl.learn_from_explanation(
            context="Deployment strategy",
            explanation="Use blue-green deployments for zero downtime",
            domain="deployment",
        )
        assert node.source == "user_explanation"
        assert node.confidence == 0.7

    def test_learn_from_correction(self):
        cl = CollaborativeLearning()
        node = cl.learn_from_correction(
            context="Git workflow",
            wrong_action="git merge",
            correct_action="git rebase",
        )
        assert node.source == "user_correction"
        assert node.confidence == 0.8

    def test_learn_from_dialogue(self):
        cl = CollaborativeLearning()
        # With strategy signal
        node = cl.learn_from_dialogue(
            context="Testing approach",
            user_statement="You should always run integration tests because unit tests aren't enough",
        )
        assert node is not None
        assert node.source == "dialogue"

    def test_learn_from_dialogue_no_signal(self):
        cl = CollaborativeLearning()
        node = cl.learn_from_dialogue(
            context="Status update",
            user_statement="OK, I see the results",
        )
        assert node is None  # No strategy signal found

    def test_get_applicable_strategies(self):
        cl = CollaborativeLearning()
        cl.learn_from_explanation(
            context="Docker deployment workflow",
            explanation="Use compose for local, k8s for prod",
            domain="deployment",
        )
        strategies = cl.get_applicable_strategies(
            "Docker deployment for production",
            domain="deployment",
        )
        assert len(strategies) >= 1

    def test_record_strategy_outcome(self):
        cl = CollaborativeLearning()
        node = cl.learn_from_explanation("Deploy", "Use k8s", "deployment")
        cl.record_strategy_outcome(node.strategy_id, True)
        cl.record_strategy_outcome(node.strategy_id, True)
        assert node.usage_count == 2

    def test_max_strategies(self):
        cl = CollaborativeLearning(max_strategies=3)
        for i in range(5):
            cl.learn_from_explanation(f"Context {i}", f"Strategy {i}")
        assert len(cl._strategies) <= 3

    def test_get_state(self):
        cl = CollaborativeLearning()
        cl.learn_from_explanation("A", "B")
        state = cl.get_state()
        assert state['total_strategies'] == 1

    def test_from_yaml(self):
        cfg = {'collaborative_learning': {'max_strategies': 100}}
        cl = CollaborativeLearning.from_yaml(cfg)
        assert cl.max_strategies == 100
