# -*- coding: utf-8 -*-
"""SQLite-backed MES audit store.

This keeps the same public surface as ``InMemoryMESStore`` while adding a real
local database for the FastAPI MVP. The schema stores each domain record as JSON
so we can stabilize API behavior before introducing a normalized PostgreSQL
schema.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.mes.domain import (
    AIRecommendation,
    Equipment,
    Event,
    FeatureSnapshot,
    Lot,
    MESCommand,
    Recipe,
    RuleValidationResult,
    Wafer,
)
from src.mes.store import InMemoryMESStore


class SQLiteMESStore(InMemoryMESStore):
    """Write-through SQLite store with an in-memory query cache."""

    TABLES = {
        "lots": "lot_id",
        "wafers": "wafer_id",
        "equipment": "equipment_id",
        "recipes": "recipe_id",
        "feature_snapshots": "feature_snapshot_id",
        "recommendations": "recommendation_id",
        "commands": "command_id",
        "validations": "",
        "events": "",
    }

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.cache_limit = int(os.environ.get("MES_STORE_CACHE_LIMIT", "5000"))
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        super().__init__()
        self._load_cache()

    def add_feature_snapshot(self, snapshot: FeatureSnapshot) -> None:
        super().add_feature_snapshot(snapshot)
        self._upsert(
            "feature_snapshots",
            snapshot.feature_snapshot_id,
            snapshot.correlation_id,
            snapshot.to_dict(),
        )

    def add_recommendation(self, recommendation: AIRecommendation) -> None:
        super().add_recommendation(recommendation)
        self._upsert(
            "recommendations",
            recommendation.recommendation_id,
            recommendation.correlation_id,
            recommendation.to_dict(),
        )

    def add_validation(self, validation: RuleValidationResult) -> None:
        super().add_validation(validation)
        self._insert(
            "validations",
            None,
            validation.correlation_id,
            validation.to_dict(),
        )

    def add_command(self, command: MESCommand) -> None:
        super().add_command(command)
        self._upsert(
            "commands",
            command.command_id,
            command.correlation_id,
            command.to_dict(),
        )

    def add_event(self, event: Event) -> None:
        super().add_event(event)
        self._insert("events", event.event_id, event.correlation_id, event.to_dict())

    def upsert_lot(self, lot: Lot) -> None:
        super().upsert_lot(lot)
        self._upsert("lots", lot.lot_id, "", lot.to_dict())

    def upsert_wafer(self, wafer: Wafer) -> None:
        super().upsert_wafer(wafer)
        self._upsert("wafers", wafer.wafer_id, "", wafer.to_dict())

    def upsert_equipment(self, equipment: Equipment) -> None:
        super().upsert_equipment(equipment)
        self._upsert("equipment", equipment.equipment_id, "", equipment.to_dict())

    def upsert_recipe(self, recipe: Recipe) -> None:
        super().upsert_recipe(recipe)
        self._upsert("recipes", recipe.recipe_id, "", recipe.to_dict())

    def clear_runtime_state(self) -> None:
        super().clear_runtime_state()
        for table in ("lots", "wafers", "equipment", "recipes"):
            self._conn.execute(f"DELETE FROM {table}")
        self._conn.commit()

    def record_command_executed(
        self,
        command_id: str,
        step_result: Optional[Dict[str, Any]] = None,
        post_decision_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[MESCommand]:
        command = super().record_command_executed(
            command_id,
            step_result=step_result,
            post_decision_state=post_decision_state,
        )
        if command is not None:
            self._upsert(
                "commands",
                command.command_id,
                command.correlation_id,
                command.to_dict(),
            )
        return command

    def _init_schema(self) -> None:
        for table in self.TABLES:
            self._conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    record_id TEXT,
                    correlation_id TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_corr ON {table}(correlation_id)"
            )
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_record ON {table}(record_id)"
            )
        self._conn.commit()

    def _load_cache(self) -> None:
        for payload in self._rows("lots", limit=self.cache_limit):
            lot = Lot(**payload)
            self._lots[lot.lot_id] = lot
        for payload in self._rows("wafers", limit=self.cache_limit):
            wafer = Wafer(**payload)
            self._wafers[wafer.wafer_id] = wafer
        for payload in self._rows("equipment", limit=self.cache_limit):
            equipment = Equipment(**payload)
            self._equipment[equipment.equipment_id] = equipment
        for payload in self._rows("recipes", limit=self.cache_limit):
            recipe = Recipe(**payload)
            self._recipes[recipe.recipe_id] = recipe
        for payload in self._rows("feature_snapshots", limit=self.cache_limit):
            snapshot = FeatureSnapshot(**payload)
            self._feature_snapshots[snapshot.feature_snapshot_id] = snapshot
        for payload in self._rows("recommendations", limit=self.cache_limit):
            recommendation = AIRecommendation(**payload)
            self._recommendations[recommendation.recommendation_id] = recommendation
        for payload in self._rows("validations", limit=self.cache_limit):
            self._validations.append(RuleValidationResult(**payload))
        for payload in self._rows("commands", limit=self.cache_limit):
            command = MESCommand(**payload)
            self._commands[command.command_id] = command
        for payload in self._rows("events", limit=self.cache_limit):
            self._events.append(Event(**payload))

    def _rows(
        self,
        table: str,
        limit: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        if limit is not None and limit > 0:
            rows = self._conn.execute(
                f"""
                SELECT payload FROM (
                    SELECT row_id, payload
                    FROM {table}
                    ORDER BY row_id DESC
                    LIMIT ?
                )
                ORDER BY row_id ASC
                """,
                (int(limit),),
            ).fetchall()
            for row in rows:
                yield json.loads(row["payload"])
            return

        rows = self._conn.execute(
            f"SELECT payload FROM {table} ORDER BY row_id ASC"
        ).fetchall()
        for row in rows:
            yield json.loads(row["payload"])

    def _upsert(
        self,
        table: str,
        record_id: str,
        correlation_id: str,
        payload: Dict[str, Any],
    ) -> None:
        existing = self._conn.execute(
            f"SELECT row_id FROM {table} WHERE record_id = ? ORDER BY row_id DESC LIMIT 1",
            (record_id,),
        ).fetchone()
        data = json.dumps(payload, sort_keys=True)
        if existing is None:
            self._insert(table, record_id, correlation_id, payload)
            return
        self._conn.execute(
            f"""
            UPDATE {table}
            SET correlation_id = ?, payload = ?
            WHERE row_id = ?
            """,
            (correlation_id, data, existing["row_id"]),
        )
        self._conn.commit()

    def _insert(
        self,
        table: str,
        record_id: Optional[str],
        correlation_id: str,
        payload: Dict[str, Any],
    ) -> None:
        self._conn.execute(
            f"""
            INSERT INTO {table}(record_id, correlation_id, payload)
            VALUES (?, ?, ?)
            """,
            (record_id, correlation_id, json.dumps(payload, sort_keys=True)),
        )
        self._conn.commit()
