"""Runtime lifecycle for the simulator-backed MES API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from src.environment.manufacturing_env import ManufacturingEnv
from src.mes import MESDevelopmentHarness
from src.mes.recommendations import make_id
from src.mes.sqlite_store import SQLiteMESStore


def build_default_env() -> ManufacturingEnv:
    env = ManufacturingEnv(
        {
            "num_machines_A": 5,
            "num_machines_B": 3,
            "num_machines_C": 3,
            "batch_size_A": 3,
            "batch_size_B": 2,
            "batch_size_C": 4,
            "max_packs_per_step": 3,
            "process_time_A": 20,
            "process_time_B": 8,
            "process_time_C": 2,
            "deterministic_mode": True,
        }
    )
    env.reset(seed=11)
    return env


def default_db_path() -> Path:
    return Path(os.environ.get("MES_DB_PATH", "data/mes_mvp.sqlite3"))


class MESAPIContext:
    """Mutable runtime state shared by API routes."""

    def __init__(self) -> None:
        self.env = build_default_env()
        self.store = SQLiteMESStore(default_db_path())
        self.store.clear_runtime_state()
        self.run_id = ""
        self._run_sequence = len(self.store.runs())
        self._start_new_run("startup")
        self.harness = MESDevelopmentHarness(config=self.env.config, store=self.store)
        self.autoplay_enabled = False
        self.autoplay_target_stage = "AUTO"
        self.autoplay_generate_every = 20
        self.last_generation_time: Optional[int] = None
        self.last_correlation_id: Optional[str] = None
        self.last_cycle: Optional[Dict[str, Any]] = None
        self.scenario_snapshots: Dict[str, Dict[str, Any]] = {}
        self.experiment_results: Dict[str, Dict[str, Any]] = {}

    def reset_runtime(self) -> None:
        self.env = build_default_env()
        self.store.clear_runtime_state()
        self._start_new_run("reset")
        self.autoplay_enabled = False
        self.autoplay_target_stage = "AUTO"
        self.last_generation_time = None
        self.last_correlation_id = None
        self.last_cycle = None
        self.scenario_snapshots.clear()
        self.experiment_results.clear()

    def _start_new_run(self, reason: str) -> None:
        self._run_sequence += 1
        self.run_id = make_id("RUN")
        self.store.start_run(
            self.run_id,
            reason=reason,
            time=int(self.env.time),
            metadata={
                "sequence": self._run_sequence,
                "config": dict(self.env.config),
            },
        )
        self.store.record_state_snapshot(
            source=f"runtime_{reason}",
            decision_state=self.env.get_decision_state(),
            run_id=self.run_id,
        )
