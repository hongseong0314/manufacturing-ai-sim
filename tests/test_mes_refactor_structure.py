from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MES_ROOT = PROJECT_ROOT / "src" / "mes"


def test_mes_api_is_route_wiring_only() -> None:
    source = (MES_ROOT / "api.py").read_text()

    moved_helpers = [
        "def _build_default_env",
        "class MESAPIContext",
        "def _generate_tasks",
        "def _run_auto_cycle",
        "def _live_fab_state",
        "def _decision_chain",
        "def _equipment_detail",
        "def _gantt_state",
        "def _ready_stages",
        "def _run_parallel_stage",
    ]
    for helper in moved_helpers:
        assert helper not in source

    assert source.count("@app.") >= 20
    assert len(source.splitlines()) < 450


def test_control_room_ui_assets_are_separate_files() -> None:
    assert (MES_ROOT / "ui" / "templates" / "control_room.html").exists()
    assert (MES_ROOT / "ui" / "static" / "control_room.css").exists()
    assert (MES_ROOT / "ui" / "static" / "control_room.js").exists()

    live_ui = (MES_ROOT / "live_ui.py").read_text()
    assert 'LIVE_MES_HTML = """' not in live_ui


def test_mes_public_facades_export_core_classes() -> None:
    from src.mes.harness import MESDevelopmentHarness, MESGeneratorAgent, MESPlannerAgent
    from src.mes.services import MESDecisionService

    assert MESDecisionService.__name__ == "MESDecisionService"
    assert MESDevelopmentHarness.__name__ == "MESDevelopmentHarness"
    assert MESPlannerAgent.__name__ == "MESPlannerAgent"
    assert MESGeneratorAgent.__name__ == "MESGeneratorAgent"


def test_harness_and_service_facades_delegate_to_feature_modules() -> None:
    expected_modules = [
        MES_ROOT / "harnessing" / "planner.py",
        MES_ROOT / "harnessing" / "generator.py",
        MES_ROOT / "harnessing" / "evaluator.py",
        MES_ROOT / "decision" / "candidates.py",
        MES_ROOT / "decision" / "annotations.py",
        MES_ROOT / "decision" / "simulator_actions.py",
    ]
    for path in expected_modules:
        assert path.exists()

    harness_source = (MES_ROOT / "harness.py").read_text()
    service_source = (MES_ROOT / "services.py").read_text()
    assert "class MESPlannerAgent" not in harness_source
    assert "class MESGeneratorAgent" not in harness_source
    assert "class MESEvaluatorAgent" not in harness_source
    assert "def _ab_dispatch_candidates" not in service_source
    assert "def _a_selected_process_action" not in service_source
    assert "def simulator_actions_from_validation" not in service_source
    assert len(harness_source.splitlines()) < 160
    assert len(service_source.splitlines()) < 120
