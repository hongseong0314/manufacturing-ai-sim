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
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

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

    SCHEMA_VERSION = "run_index_v1"
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
    INDEX_TABLES = (
        "run_index",
        "task_index",
        "lot_index",
        "assignment_index",
        "equipment_timeline_index",
        "command_ledger_index",
        "event_ledger_index",
        "state_snapshot_index",
        "genealogy_edge_index",
    )

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.cache_limit = int(os.environ.get("MES_STORE_CACHE_LIMIT", "5000"))
        self._db_lock = threading.RLock()
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        super().__init__()
        legacy = not self._table_exists("schema_meta")
        self._init_schema()
        if legacy or self._schema_version() != self.SCHEMA_VERSION:
            self.clear_all_persistent_state()
            self._set_schema_version(self.SCHEMA_VERSION)
        self._load_cache()

    def start_run(
        self,
        run_id: str,
        reason: str = "startup",
        time: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        row = super().start_run(run_id, reason=reason, time=time, metadata=metadata)
        payload = dict(row)
        with self._db_lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO run_index(run_id, start_time, reason, status, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload["run_id"],
                    int(payload.get("start_time", 0) or 0),
                    payload.get("reason", ""),
                    payload.get("status", "ACTIVE"),
                    self._json(payload),
                ),
            )
            self._conn.commit()
        return row

    def add_feature_snapshot(self, snapshot: FeatureSnapshot) -> None:
        super().add_feature_snapshot(snapshot)
        self._upsert(
            "feature_snapshots",
            snapshot.feature_snapshot_id,
            snapshot.correlation_id,
            snapshot.to_dict(),
        )
        self.record_state_snapshot(
            source=f"feature_snapshot:{snapshot.layer_id}",
            decision_state=snapshot.decision_state,
            correlation_id=snapshot.correlation_id,
            layer_id=snapshot.layer_id,
            snapshot_id=snapshot.feature_snapshot_id,
            run_id=snapshot.run_id,
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
        self._index_command(command)

    def add_event(self, event: Event) -> None:
        super().add_event(event)
        self._insert("events", event.event_id, event.correlation_id, event.to_dict())
        self._index_event(event)

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
        with self._db_lock:
            for table in ("lots", "wafers", "equipment", "recipes"):
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()

    def clear_audit_state(self) -> None:
        super().clear_audit_state()
        with self._db_lock:
            for table in (
                "feature_snapshots",
                "recommendations",
                "commands",
                "validations",
                "events",
            ):
                self._conn.execute(f"DELETE FROM {table}")
            for table in self.INDEX_TABLES:
                self._conn.execute(f"DELETE FROM {table}")
            self._conn.commit()

    def clear_all_persistent_state(self) -> None:
        super().clear_runtime_state()
        super().clear_audit_state()
        with self._db_lock:
            for table in tuple(self.TABLES) + self.INDEX_TABLES:
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
            self._index_command(command)
        return command

    def record_state_snapshot(
        self,
        source: str,
        decision_state: Dict[str, Any],
        correlation_id: str = "",
        layer_id: str = "",
        snapshot_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = super().record_state_snapshot(
            source=source,
            decision_state=decision_state,
            correlation_id=correlation_id,
            layer_id=layer_id,
            snapshot_id=snapshot_id,
            run_id=run_id,
        )
        resolved_run_id = row["run_id"]
        with self._db_lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO state_snapshot_index(
                    run_id, snapshot_id, source, correlation_id, layer_id, time, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resolved_run_id,
                    row["snapshot_id"],
                    row["source"],
                    row["correlation_id"],
                    row["layer_id"],
                    row["time"],
                    self._json(row),
                ),
            )
            self._index_tasks_and_lots(resolved_run_id, decision_state)
            self._conn.commit()
        return row

    def normalized_index_counts(self, run_id: Optional[str] = None) -> Dict[str, int]:
        return {
            table: self._count_table(table, run_id=run_id)
            for table in self.INDEX_TABLES
        }

    def normalized_index_rows(
        self,
        index_name: str,
        run_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        name = str(index_name)
        if name not in self.INDEX_TABLES:
            raise ValueError(f"unknown ledger index: {name}")
        limit = max(1, min(1000, int(limit)))
        with self._db_lock:
            if run_id is None:
                rows = self._conn.execute(
                    f"""
                    SELECT *
                    FROM {name}
                    ORDER BY row_id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    f"""
                    SELECT *
                    FROM {name}
                    WHERE run_id = ?
                    ORDER BY row_id DESC
                    LIMIT ?
                    """,
                    (run_id, limit),
                ).fetchall()
        return [self._index_row_to_dict(row) for row in reversed(rows)]

    def runs(self) -> List[Dict[str, Any]]:
        with self._db_lock:
            rows = self._conn.execute(
                """
                SELECT payload
                FROM run_index
                ORDER BY row_id ASC
                """
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
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
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT UNIQUE NOT NULL,
                start_time INTEGER,
                reason TEXT,
                status TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                task_uid INTEGER NOT NULL,
                wafer_id TEXT,
                lot_id TEXT,
                latest_location TEXT,
                time INTEGER,
                payload TEXT NOT NULL,
                UNIQUE(run_id, task_uid)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lot_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                lot_id TEXT NOT NULL,
                task_count INTEGER,
                payload TEXT NOT NULL,
                UNIQUE(run_id, lot_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assignment_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                command_id TEXT NOT NULL,
                correlation_id TEXT,
                candidate_id TEXT,
                stage TEXT,
                equipment_id TEXT,
                task_uid INTEGER,
                task_uids TEXT,
                start_time INTEGER,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_timeline_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                equipment_id TEXT,
                time INTEGER,
                event_type TEXT,
                command_id TEXT,
                correlation_id TEXT,
                task_uids TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS command_ledger_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                command_id TEXT UNIQUE NOT NULL,
                correlation_id TEXT,
                status TEXT,
                validation_status TEXT,
                equipment_id TEXT,
                stage TEXT,
                task_uids TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_ledger_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_id TEXT UNIQUE NOT NULL,
                correlation_id TEXT,
                event_type TEXT,
                actor_type TEXT,
                equipment_id TEXT,
                operation_id TEXT,
                time INTEGER,
                task_uids TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS state_snapshot_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                snapshot_id TEXT UNIQUE NOT NULL,
                source TEXT,
                correlation_id TEXT,
                layer_id TEXT,
                time INTEGER,
                payload TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS genealogy_edge_index (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                parent_type TEXT,
                parent_id TEXT,
                child_type TEXT,
                child_id TEXT,
                operation_id TEXT,
                equipment_id TEXT,
                event_id TEXT,
                correlation_id TEXT,
                payload TEXT NOT NULL
            )
            """
        )
        for table in self.INDEX_TABLES:
            self._conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table}_run ON {table}(run_id)"
            )
        self._conn.commit()

    def _load_cache(self) -> None:
        self._runs = self.runs()
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

    def _index_command(self, command: MESCommand) -> None:
        payload = command.to_dict()
        validated = dict(command.validated_command or {})
        task_uids = [int(uid) for uid in validated.get("task_uids", [])]
        stage = str(validated.get("stage") or self._stage_from_equipment(validated.get("equipment_id")))
        with self._db_lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO command_ledger_index(
                    run_id, command_id, correlation_id, status, validation_status,
                    equipment_id, stage, task_uids, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command.run_id,
                    command.command_id,
                    command.correlation_id,
                    command.status,
                    command.validation_status,
                    validated.get("equipment_id"),
                    stage,
                    self._json(task_uids),
                    self._json(payload),
                ),
            )
            self._conn.execute(
                "DELETE FROM assignment_index WHERE command_id = ?",
                (command.command_id,),
            )
            for uid in task_uids:
                row = {
                    "run_id": command.run_id,
                    "command_id": command.command_id,
                    "correlation_id": command.correlation_id,
                    "candidate_id": validated.get("candidate_id"),
                    "stage": stage,
                    "equipment_id": validated.get("equipment_id"),
                    "task_uid": uid,
                    "task_uids": task_uids,
                    "start_time": validated.get("start_time", 0),
                    "command": payload,
                }
                self._conn.execute(
                    """
                    INSERT INTO assignment_index(
                        run_id, command_id, correlation_id, candidate_id, stage,
                        equipment_id, task_uid, task_uids, start_time, payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["run_id"],
                        row["command_id"],
                        row["correlation_id"],
                        row["candidate_id"],
                        row["stage"],
                        row["equipment_id"],
                        row["task_uid"],
                        self._json(task_uids),
                        int(row["start_time"] or 0),
                        self._json(row),
                    ),
                )
                self._index_genealogy_edge(
                    run_id=command.run_id,
                    parent_type="TASK",
                    parent_id=str(uid),
                    child_type="COMMAND",
                    child_id=command.command_id,
                    operation_id=stage,
                    equipment_id=str(validated.get("equipment_id") or ""),
                    event_id="",
                    correlation_id=command.correlation_id,
                    payload=row,
                )
            self._conn.commit()

    def _index_event(self, event: Event) -> None:
        payload = event.to_dict()
        task_uids = self._task_uids_from_event_payload(payload)
        event_time = self._event_time_from_payload(payload)
        with self._db_lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO event_ledger_index(
                    run_id, event_id, correlation_id, event_type, actor_type,
                    equipment_id, operation_id, time, task_uids, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    event.event_id,
                    event.correlation_id,
                    event.event_type,
                    event.actor_type,
                    event.equipment_id,
                    event.operation_id,
                    event_time,
                    self._json(task_uids),
                    self._json(payload),
                ),
            )
            if event.equipment_id:
                self._conn.execute(
                    """
                    INSERT INTO equipment_timeline_index(
                        run_id, equipment_id, time, event_type, command_id,
                        correlation_id, task_uids, payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.run_id,
                        event.equipment_id,
                        event_time,
                        event.event_type,
                        self._command_id_from_event_payload(payload),
                        event.correlation_id,
                        self._json(task_uids),
                        self._json(payload),
                    ),
                )
            for uid in task_uids:
                self._index_genealogy_edge(
                    run_id=event.run_id,
                    parent_type="TASK",
                    parent_id=str(uid),
                    child_type="EVENT",
                    child_id=event.event_id,
                    operation_id=str(event.operation_id or ""),
                    equipment_id=str(event.equipment_id or ""),
                    event_id=event.event_id,
                    correlation_id=event.correlation_id,
                    payload=payload,
                )
            self._conn.commit()

    def _index_tasks_and_lots(self, run_id: str, decision_state: Dict[str, Any]) -> None:
        tasks = decision_state.get("tasks", {}) or {}
        lot_counts: Dict[str, int] = {}
        for row in tasks.values():
            if not isinstance(row, dict):
                continue
            uid = row.get("uid")
            if uid is None:
                continue
            task_uid = int(uid)
            lot_id = str(row.get("job_id") or "")
            lot_counts[lot_id] = lot_counts.get(lot_id, 0) + 1
            self._conn.execute(
                """
                INSERT OR REPLACE INTO task_index(
                    run_id, task_uid, wafer_id, lot_id, latest_location, time, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_uid,
                    f"WAFER_{task_uid}",
                    lot_id,
                    str(row.get("location") or ""),
                    int(decision_state.get("time", 0) or 0),
                    self._json(row),
                ),
            )
        for lot_id, task_count in lot_counts.items():
            payload = {
                "run_id": run_id,
                "lot_id": lot_id,
                "task_count": task_count,
            }
            self._conn.execute(
                """
                INSERT OR REPLACE INTO lot_index(run_id, lot_id, task_count, payload)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, lot_id, task_count, self._json(payload)),
            )

    def _index_genealogy_edge(
        self,
        run_id: str,
        parent_type: str,
        parent_id: str,
        child_type: str,
        child_id: str,
        operation_id: str,
        equipment_id: str,
        event_id: str,
        correlation_id: str,
        payload: Dict[str, Any],
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO genealogy_edge_index(
                run_id, parent_type, parent_id, child_type, child_id,
                operation_id, equipment_id, event_id, correlation_id, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                parent_type,
                parent_id,
                child_type,
                child_id,
                operation_id,
                equipment_id,
                event_id,
                correlation_id,
                self._json(payload),
            ),
        )

    def _rows(
        self,
        table: str,
        limit: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        if limit is not None and limit > 0:
            with self._db_lock:
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

        with self._db_lock:
            rows = self._conn.execute(
                f"SELECT payload FROM {table} ORDER BY row_id ASC"
            ).fetchall()
        for row in rows:
            yield json.loads(row["payload"])

    def _table_exists(self, table: str) -> bool:
        with self._db_lock:
            row = self._conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name = ?
                """,
                (table,),
            ).fetchone()
        return row is not None

    def _schema_version(self) -> str:
        with self._db_lock:
            row = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
        return str(row["value"]) if row else ""

    def _set_schema_version(self, version: str) -> None:
        with self._db_lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO schema_meta(key, value)
                VALUES ('schema_version', ?)
                """,
                (version,),
            )
            self._conn.commit()

    def _count_table(self, table: str, run_id: Optional[str] = None) -> int:
        with self._db_lock:
            if run_id is None:
                row = self._conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()
            else:
                row = self._conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table} WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
        return int(row["count"] if row else 0)

    def _index_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        item = {key: row[key] for key in row.keys()}
        payload = item.get("payload")
        if isinstance(payload, str):
            try:
                item["payload"] = json.loads(payload)
            except json.JSONDecodeError:
                item["payload"] = payload
        for key in ("task_uids",):
            value = item.get(key)
            if isinstance(value, str):
                try:
                    item[key] = json.loads(value)
                except json.JSONDecodeError:
                    item[key] = value
        return item

    def _json(self, payload: Any) -> str:
        return json.dumps(payload, sort_keys=True)

    def _stage_from_equipment(self, equipment_id: Any) -> str:
        if not equipment_id:
            return ""
        first = str(equipment_id)[0].upper()
        return first if first in {"A", "B", "C"} else ""

    def _event_time_from_payload(self, event_payload: Dict[str, Any]) -> int:
        payload = dict(event_payload.get("payload") or {})
        if payload.get("post_time") is not None:
            return int(payload.get("post_time") or 0)
        command = dict(payload.get("command") or {})
        validated = dict(command.get("validated_command") or {})
        if validated.get("start_time") is not None:
            return int(validated.get("start_time") or 0)
        return 0

    def _command_id_from_event_payload(self, event_payload: Dict[str, Any]) -> str:
        payload = dict(event_payload.get("payload") or {})
        command = dict(payload.get("command") or {})
        return str(command.get("command_id") or payload.get("command_id") or "")

    def _task_uids_from_event_payload(self, event_payload: Dict[str, Any]) -> List[int]:
        payload = dict(event_payload.get("payload") or {})
        candidates: List[Any] = []
        for source in (
            payload,
            dict(payload.get("recommended_action") or {}),
            dict(payload.get("validation", {}).get("validated_command") or {}),
            dict(payload.get("command", {}).get("validated_command") or {}),
        ):
            values = source.get("task_uids")
            if isinstance(values, list):
                candidates.extend(values)
        for wafer_id in event_payload.get("wafer_ids") or []:
            suffix = str(wafer_id).split("_")[-1]
            if suffix.isdigit():
                candidates.append(int(suffix))
        return sorted({int(uid) for uid in candidates if str(uid).isdigit()})

    def _upsert(
        self,
        table: str,
        record_id: str,
        correlation_id: str,
        payload: Dict[str, Any],
    ) -> None:
        with self._db_lock:
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
        with self._db_lock:
            self._conn.execute(
                f"""
                INSERT INTO {table}(record_id, correlation_id, payload)
                VALUES (?, ?, ?)
                """,
                (record_id, correlation_id, json.dumps(payload, sort_keys=True)),
            )
            self._conn.commit()
