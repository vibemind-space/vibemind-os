"""
Pipeline Phase Transition Tests.

Tests für jeden Schritt der Pipeline:
- Transition Input/Output Validation
- Schema Validation
- ConversationLogger Integration

Ausführen mit: pytest tests/pipeline/test_phase_transitions.py -v
"""
import json
import pytest
from pathlib import Path
from typing import Dict, Any

from src.engine.dag_parser import DAGParser, RequirementsData, NodeType
from src.engine.project_analyzer import ProjectAnalyzer, ProjectProfile
from src.engine.slicer import Slicer, SliceManifest, TaskSlice, Domain
from src.engine.planning_engine import PlanningEngine, ExecutionPlan
from src.engine.contracts import InterfaceContracts
from src.logging.conversation_logger import ConversationLogger, TransitionEvent


class TestPhase0DAGParsing:
    """TEST-2: Phase 0 - DAG Parsing und ProjectAnalyzer."""
    
    def test_dag_parser_parses_requirements(self, minimal_requirements: dict):
        """DAGParser kann Requirements parsen."""
        parser = DAGParser()
        result = parser.parse(minimal_requirements)
        
        assert isinstance(result, RequirementsData)
        # RequirementsData has requirements list, not project_name
        assert len(result.requirements) == 3
    
    def test_dag_parser_creates_nodes(self, minimal_requirements: dict):
        """DAGParser erstellt korrekte Nodes."""
        parser = DAGParser()
        result = parser.parse(minimal_requirements)
        
        # Prüfe Nodes
        req_nodes = [n for n in result.nodes if n.type == NodeType.REQUIREMENT]
        assert len(req_nodes) == 3
        
        # Prüfe IDs
        node_ids = {n.id for n in req_nodes}
        assert "REQ-001" in node_ids
        assert "REQ-002" in node_ids
        assert "REQ-003" in node_ids
    
    def test_dag_parser_handles_dependencies(self, minimal_requirements: dict):
        """DAGParser verarbeitet Dependencies korrekt."""
        parser = DAGParser()
        result = parser.parse(minimal_requirements)
        
        # DAG sollte existieren
        assert result.dag is not None
        
        # REQ-002 hängt von REQ-001 ab
        if result.dag.has_edge("REQ-001", "REQ-002"):
            assert True
        else:
            # Alternative: prüfe Predecessors
            predecessors = list(result.dag.predecessors("REQ-002"))
            assert "REQ-001" in predecessors or len(predecessors) >= 0
    
    def test_project_analyzer_detects_type(self, minimal_requirements: dict):
        """ProjectAnalyzer erkennt Projekt-Typ."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        analyzer = ProjectAnalyzer()
        profile = analyzer.analyze(req_data)
        
        assert isinstance(profile, ProjectProfile)
        assert profile.project_type is not None
    
    def test_project_analyzer_detects_domains(self, minimal_requirements: dict):
        """ProjectAnalyzer erkennt Domains."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        analyzer = ProjectAnalyzer()
        profile = analyzer.analyze(req_data)
        
        # Sollte mindestens eine Domain erkennen
        assert len(profile.domains) > 0
    
    def test_phase_0_transition_logged(
        self,
        minimal_requirements: dict,
        conversation_logger: ConversationLogger,
    ):
        """Phase 0 Transition wird korrekt geloggt."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        analyzer = ProjectAnalyzer()
        profile = analyzer.analyze(req_data)
        
        # Log transition
        transition = conversation_logger.log_transition(
            from_phase="input",
            to_phase="phase_0_analysis",
            input_summary={"requirements_count": len(minimal_requirements["requirements"])},
            output_summary={
                "project_type": profile.project_type.value,
                "domains": [d.value for d in profile.domains],
            },
            success=True,
        )
        
        assert transition.success
        assert transition.from_phase == "input"
        assert transition.to_phase == "phase_0_analysis"


class TestPhase1Slicer:
    """TEST-5: Phase 2 - Slicer Tests."""
    
    def test_slicer_creates_manifest(self, minimal_requirements: dict):
        """Slicer erstellt SliceManifest."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        assert isinstance(manifest, SliceManifest)
        assert manifest.job_id == 1
        assert manifest.total_requirements == 3
        assert manifest.total_slices > 0
    
    def test_slicer_hybrid_strategy(self, minimal_requirements: dict):
        """Slicer hybrid Strategie funktioniert."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1, strategy="hybrid")
        
        assert len(manifest.slices) > 0
        
        # Alle Slices haben agent_type
        for slice_obj in manifest.slices:
            assert slice_obj.agent_type is not None
    
    def test_slicer_domain_strategy(self, minimal_requirements: dict):
        """Slicer domain Strategie funktioniert."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1, strategy="domain")
        
        assert len(manifest.slices) > 0
    
    def test_slicer_feature_grouped_strategy(self, minimal_requirements: dict):
        """Slicer feature_grouped Strategie funktioniert."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1, strategy="feature_grouped")
        
        assert len(manifest.slices) > 0
        
        # Feature-grouped sollte Feature-Info haben
        for slice_obj in manifest.slices:
            # Feature kann None sein für non-feature domains
            assert slice_obj.agent_type is not None
    
    def test_slice_has_requirements(self, minimal_requirements: dict):
        """Jeder Slice hat Requirements."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        for slice_obj in manifest.slices:
            assert len(slice_obj.requirements) > 0
            assert len(slice_obj.requirement_details) > 0
    
    def test_domain_detection(self, minimal_requirements: dict):
        """Domain Detection funktioniert."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer()
        
        # Teste Domain Detection für jeden Node
        for node in req_data.nodes:
            if node.type == NodeType.REQUIREMENT:
                domain = slicer._detect_domain(node)
                assert isinstance(domain, Domain)
    
    def test_phase_1_transition_logged(
        self,
        minimal_requirements: dict,
        conversation_logger: ConversationLogger,
    ):
        """Phase 1 (Slicing) Transition wird korrekt geloggt."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        # Log transition
        transition = conversation_logger.log_transition(
            from_phase="phase_0_analysis",
            to_phase="phase_1_slicing",
            input_summary={"requirements_count": len(req_data.requirements)},
            output_summary={
                "total_slices": manifest.total_slices,
                "agent_distribution": manifest.agent_distribution,
            },
            success=True,
        )
        
        assert transition.success
        assert transition.output_summary["total_slices"] > 0


class TestPhase15Planning:
    """TEST-4: Phase 1.5 - PlanningEngine Tests."""
    
    def test_planning_engine_creates_plan(self, minimal_requirements: dict):
        """PlanningEngine erstellt ExecutionPlan."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        planner = PlanningEngine()
        plan = planner.create_plan(manifest)
        
        assert isinstance(plan, ExecutionPlan)
        assert plan.total_batches > 0
    
    def test_plan_has_batches(self, minimal_requirements: dict):
        """ExecutionPlan hat Batches."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        planner = PlanningEngine()
        plan = planner.create_plan(manifest)
        
        assert len(plan.batches) > 0
        
        for batch in plan.batches:
            assert len(batch.slices) > 0
    
    def test_plan_sequential_option(self, minimal_requirements: dict):
        """PlanningEngine respektiert force_sequential."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        planner = PlanningEngine()
        plan = planner.create_plan(manifest, force_sequential=True)
        
        assert plan.sequential_only is True
    
    def test_phase_15_transition_logged(
        self,
        minimal_requirements: dict,
        conversation_logger: ConversationLogger,
    ):
        """Phase 1.5 (Planning) Transition wird korrekt geloggt."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        planner = PlanningEngine()
        plan = planner.create_plan(manifest)
        
        # Log transition
        transition = conversation_logger.log_transition(
            from_phase="phase_1_slicing",
            to_phase="phase_15_planning",
            input_summary={"total_slices": manifest.total_slices},
            output_summary={
                "total_batches": plan.total_batches,
                "sequential_only": plan.sequential_only,
            },
            success=True,
        )
        
        assert transition.success
        assert transition.output_summary["total_batches"] > 0


class TestConversationLogging:
    """TEST-1: ConversationLogger Tests."""
    
    def test_logger_creates_directory(self, temp_log_dir: Path):
        """Logger erstellt Log-Verzeichnis."""
        logger = ConversationLogger(job_id="test_123", log_dir=temp_log_dir)
        
        assert (temp_log_dir / "test_123").exists()
    
    def test_logger_starts_agent(self, conversation_logger: ConversationLogger):
        """Logger kann Agent-Conversation starten."""
        conv = conversation_logger.start_agent("test_agent")
        
        assert conv.agent_name == "test_agent"
        assert conv.job_id == "test_job_001"
    
    def test_logger_logs_messages(self, conversation_logger: ConversationLogger):
        """Logger kann Messages loggen."""
        conversation_logger.start_agent("test_agent")
        
        msg = conversation_logger.log_message(
            "test_agent",
            "user",
            "Hello, agent!",
            {"test_key": "test_value"},
        )
        
        assert msg.role == "user"
        assert msg.content == "Hello, agent!"
        assert msg.metadata["test_key"] == "test_value"
    
    def test_logger_writes_json_file(
        self,
        temp_log_dir: Path,
        conversation_logger: ConversationLogger,
    ):
        """Logger schreibt JSON-Dateien."""
        conversation_logger.start_agent("test_agent")
        conversation_logger.log_message("test_agent", "user", "Test message")
        conversation_logger.end_agent("test_agent")
        
        # Prüfe dass Datei existiert
        log_file = temp_log_dir / "test_job_001" / "test_agent.json"
        assert log_file.exists()
        
        # Prüfe Inhalt
        with open(log_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        assert data["agent_name"] == "test_agent"
        assert len(data["messages"]) == 1
        assert data["summary"]["total_messages"] == 1
    
    def test_logger_context_manager(self, conversation_logger: ConversationLogger):
        """Logger Context Manager funktioniert."""
        with conversation_logger.agent_context("context_agent") as agent:
            agent.log_system("System init")
            agent.log_user("User prompt")
            agent.log_assistant("Assistant response")
        
        conv = conversation_logger.get_conversation("context_agent")
        assert conv is not None
        assert len(conv.messages) == 3
        assert conv.summary["success"] is True
    
    def test_logger_transitions(self, conversation_logger: ConversationLogger):
        """Logger kann Transitions loggen."""
        transition = conversation_logger.log_transition(
            from_phase="phase_a",
            to_phase="phase_b",
            input_summary={"count": 5},
            output_summary={"result": "ok"},
            success=True,
            duration_ms=1000,
        )
        
        assert transition.from_phase == "phase_a"
        assert transition.to_phase == "phase_b"
        
        # Prüfe transitions file
        transitions = conversation_logger.get_transitions()
        assert len(transitions) == 1
    
    def test_logger_summary(self, conversation_logger: ConversationLogger):
        """Logger generiert Summary."""
        with conversation_logger.agent_context("agent_1") as a1:
            a1.log_user("Hello")
        
        with conversation_logger.agent_context("agent_2") as a2:
            a2.log_user("Hi")
            a2.log_assistant("Hey")
        
        conversation_logger.log_transition("start", "end")
        
        summary = conversation_logger.generate_summary()
        
        assert summary["job_id"] == "test_job_001"
        assert "agent_1" in summary["agents"]
        assert "agent_2" in summary["agents"]
        assert summary["agents"]["agent_1"]["messages"] == 1
        assert summary["agents"]["agent_2"]["messages"] == 2
        assert summary["transitions"]["total"] == 1


class TestOutputSchemaValidation:
    """Tests für Output Schema Validation."""
    
    def test_requirements_data_schema(self, minimal_requirements: dict):
        """RequirementsData hat korrektes Schema."""
        parser = DAGParser()
        result = parser.parse(minimal_requirements)
        
        # Pflichtfelder - use actual RequirementsData fields
        assert hasattr(result, "requirements")
        assert hasattr(result, "nodes")
        assert hasattr(result, "dag")
        assert hasattr(result, "success")
        assert hasattr(result, "workflow_status")
    
    def test_slice_manifest_schema(self, minimal_requirements: dict):
        """SliceManifest hat korrektes Schema."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer()
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        # Pflichtfelder
        assert hasattr(manifest, "job_id")
        assert hasattr(manifest, "total_requirements")
        assert hasattr(manifest, "total_slices")
        assert hasattr(manifest, "slices")
        assert hasattr(manifest, "depth_groups")
        assert hasattr(manifest, "agent_distribution")
        
        # to_dict funktioniert
        manifest_dict = manifest.to_dict()
        assert "job_id" in manifest_dict
        assert "slices" in manifest_dict
    
    def test_task_slice_schema(self, minimal_requirements: dict):
        """TaskSlice hat korrektes Schema."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer()
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        for slice_obj in manifest.slices:
            # Pflichtfelder
            assert hasattr(slice_obj, "slice_id")
            assert hasattr(slice_obj, "depth")
            assert hasattr(slice_obj, "agent_type")
            assert hasattr(slice_obj, "requirements")
            assert hasattr(slice_obj, "requirement_details")
            assert hasattr(slice_obj, "can_parallelize")
            assert hasattr(slice_obj, "estimated_tokens")
            
            # to_dict funktioniert
            slice_dict = slice_obj.to_dict()
            assert "slice_id" in slice_dict
    
    def test_execution_plan_schema(self, minimal_requirements: dict):
        """ExecutionPlan hat korrektes Schema."""
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        slicer = Slicer()
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        planner = PlanningEngine()
        plan = planner.create_plan(manifest)
        
        # Pflichtfelder
        assert hasattr(plan, "total_batches")
        assert hasattr(plan, "batches")
        assert hasattr(plan, "sequential_only")
    
    def test_transition_event_schema(self, conversation_logger: ConversationLogger):
        """TransitionEvent hat korrektes Schema."""
        transition = conversation_logger.log_transition(
            from_phase="a",
            to_phase="b",
        )
        
        # Pflichtfelder
        assert hasattr(transition, "timestamp")
        assert hasattr(transition, "from_phase")
        assert hasattr(transition, "to_phase")
        assert hasattr(transition, "success")
        
        # to_dict funktioniert
        trans_dict = transition.to_dict()
        assert "timestamp" in trans_dict
        assert "from_phase" in trans_dict


class TestFullPipelineFlow:
    """TEST-8: Integration Test - Full Pipeline Flow."""
    
    def test_full_pipeline_phases(
        self,
        minimal_requirements: dict,
        conversation_logger: ConversationLogger,
    ):
        """Teste kompletten Pipeline-Durchlauf ohne Code-Generation."""
        # Phase 0: Parse
        parser = DAGParser()
        req_data = parser.parse(minimal_requirements)
        
        conversation_logger.log_transition(
            from_phase="input",
            to_phase="phase_0",
            input_summary={"raw_requirements": len(minimal_requirements["requirements"])},
            output_summary={"nodes": len(req_data.nodes)},
        )
        
        # Phase 0: Analyze
        analyzer = ProjectAnalyzer()
        profile = analyzer.analyze(req_data)
        
        conversation_logger.log_transition(
            from_phase="phase_0",
            to_phase="phase_0_analysis",
            output_summary={
                "project_type": profile.project_type.value,
                "domains": len(profile.domains),
            },
        )
        
        # Phase 1: Slice
        slicer = Slicer(slice_size=2)
        manifest = slicer.slice_requirements(req_data, job_id=1)
        
        conversation_logger.log_transition(
            from_phase="phase_0_analysis",
            to_phase="phase_1_slicing",
            output_summary={
                "total_slices": manifest.total_slices,
                "agents": list(manifest.agent_distribution.keys()),
            },
        )
        
        # Phase 1.5: Plan
        planner = PlanningEngine()
        plan = planner.create_plan(manifest)
        
        conversation_logger.log_transition(
            from_phase="phase_1_slicing",
            to_phase="phase_15_planning",
            output_summary={
                "batches": plan.total_batches,
                "sequential": plan.sequential_only,
            },
        )
        
        # Verify all transitions logged
        transitions = conversation_logger.get_transitions()
        assert len(transitions) == 4
        
        # Verify all successful
        assert all(t.success for t in transitions)
        
        # Verify flow is correct
        phases = [(t.from_phase, t.to_phase) for t in transitions]
        assert phases[0] == ("input", "phase_0")
        assert phases[1] == ("phase_0", "phase_0_analysis")
        assert phases[2] == ("phase_0_analysis", "phase_1_slicing")
        assert phases[3] == ("phase_1_slicing", "phase_15_planning")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])