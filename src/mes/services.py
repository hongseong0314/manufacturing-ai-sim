# -*- coding: utf-8 -*-
"""High-level MES shell services around the simulator kernel."""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence

from src.agents.factory import MESPolicyStack, build_mes_policy_stack
from src.environment.process_a_env import (
    BETA,
    BETA_K,
    B_BASE,
    DELTA_B,
    DELTA_W1,
    DELTA_W12,
    W12_BASE,
    W1_BASE,
    W2_BASE,
    W3_BASE,
)
from src.mes.adapters import SimulatorMESAdapter
from src.mes.domain import AIRecommendation, FeatureSnapshot, RuleValidationResult
from src.mes.recommendations import create_recommendation
from src.mes.rule_engine import MESRuleEngine
from src.objects import Task


class MESDecisionService:
    """Small orchestration surface for the first simulator-backed MES MVP."""

    def __init__(
        self,
        adapter: Optional[SimulatorMESAdapter] = None,
        rule_engine: Optional[MESRuleEngine] = None,
        config: Optional[Dict[str, Any]] = None,
        policy_stack: Optional[MESPolicyStack] = None,
    ):
        self.adapter = adapter or SimulatorMESAdapter()
        self.rule_engine = rule_engine or MESRuleEngine()
        self.policy_stack = policy_stack or build_mes_policy_stack(config or {})

    def decision_state_to_mes(self, decision_state: Dict[str, Any]) -> Dict[str, Any]:
        return self.adapter.decision_state_to_mes(decision_state)

    def create_feature_snapshot(
        self,
        decision_state: Dict[str, Any],
        layer_id: str,
        correlation_id: Optional[str] = None,
        features: Optional[Dict[str, Any]] = None,
    ) -> FeatureSnapshot:
        return self.adapter.feature_snapshot_from_state(
            decision_state,
            layer_id=layer_id,
            correlation_id=correlation_id,
            features=features,
        )

    def dispatch_candidates(
        self,
        decision_state: Dict[str, Any],
        stage: str = "A",
    ) -> List[Dict[str, Any]]:
        """Generate rule-only candidate actions from idle simulator machines."""
        return self.l1_candidate_portfolio(decision_state, stages=[stage])

    def l1_candidate_portfolio(
        self,
        decision_state: Dict[str, Any],
        stages: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate local L1 candidate portfolios before upper-layer selection."""
        requested_stages = [
            str(stage).upper()
            for stage in (stages or ("A", "B", "C"))
            if str(stage).upper() in {"A", "B", "C"}
        ]
        portfolio: List[Dict[str, Any]] = []
        for stage in requested_stages:
            if stage == "C":
                portfolio.extend(self._c_pack_candidates(decision_state))
            else:
                portfolio.extend(self._ab_dispatch_candidates(decision_state, stage))
        return portfolio

    def annotate_candidate_portfolio(
        self,
        decision_state: Dict[str, Any],
        candidate_portfolio: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Attach L2 process annotations to every L1 candidate."""
        annotated: List[Dict[str, Any]] = []
        for candidate in candidate_portfolio:
            candidate_copy = dict(candidate)
            candidate_copy["l2_annotation"] = self.process_annotation_for_candidate(
                decision_state,
                candidate_copy,
            )
            annotated.append(candidate_copy)
        return annotated

    def process_annotation_for_candidate(
        self,
        decision_state: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the L2 annotation contract for one candidate."""
        stage = str(candidate.get("stage", "")).upper()
        if stage == "A":
            return self._a_process_annotation(decision_state, candidate)
        if stage == "B":
            return self._b_process_annotation(candidate)
        if stage == "C":
            return self._c_process_annotation(candidate)
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": stage,
            "quality_risk": "UNKNOWN",
            "selection_reason": "unknown_stage_process_annotation",
        }

    def process_action_for_selected_candidate(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the final L2 APC action through the factory policy stack."""
        stage = str(stage).upper()
        if stage == "A":
            return self._a_selected_process_action(decision_state, dispatch_action)
        if stage == "B":
            return self._b_selected_process_action(decision_state, dispatch_action)
        return self._c_selected_process_action(dispatch_action)

    def _ab_dispatch_candidates(
        self,
        decision_state: Dict[str, Any],
        stage: str,
    ) -> List[Dict[str, Any]]:
        stage = stage.upper()
        stage_state = decision_state.get(stage, {})
        wait_pool = self._wait_pool(stage, stage_state)
        rework_pool = [int(uid) for uid in stage_state.get("rework_pool_uids", [])]
        if not wait_pool and not rework_pool:
            return []

        candidates: List[Dict[str, Any]] = []
        used_uids = set()
        scheduler = self._scheduler_for_stage(stage)
        for equipment_id, machine in sorted(stage_state.get("machines", {}).items()):
            if not self._is_machine_available(machine, decision_state):
                continue
            batch_size = int(machine.get("batch_size", 1))
            wait_candidates = [uid for uid in wait_pool if uid not in used_uids]
            rework_candidates = [uid for uid in rework_pool if uid not in used_uids]
            if not wait_candidates and not rework_candidates:
                continue
            context = self._scheduler_context(
                decision_state=decision_state,
                stage_state=stage_state,
                machine_state=machine,
                wait_candidates=wait_candidates,
                rework_candidates=rework_candidates,
            )
            task_uids, task_type = self._select_batch(
                scheduler=scheduler,
                wait_candidates=wait_candidates,
                rework_candidates=rework_candidates,
                batch_size=batch_size,
                context=context,
            )
            if not task_uids:
                continue
            used_uids.update(task_uids)
            candidates.append(
                self._candidate_action(
                    decision_state,
                    stage=stage,
                    equipment_id=str(equipment_id),
                    task_uids=task_uids,
                    candidate_type="DISPATCH",
                    task_type=task_type,
                    reason="rule_eligible_idle_equipment",
                )
            )
        return self._rank_candidates(candidates)

    def _c_pack_candidates(self, decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        strategy = str(
            self.policy_stack.config.get(
                "mes_l1_C",
                self.policy_stack.config.get("packing_C", "fifo"),
            )
        ).lower()
        if strategy in {"grouped", "group", "candidate-portfolio"}:
            return self._c_grouped_pack_candidates(decision_state)
        return self._c_packer_candidates(decision_state)

    def _c_grouped_pack_candidates(
        self,
        decision_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        stage = "C"
        stage_state = decision_state.get(stage, {})
        pool = self._candidate_pool(stage, stage_state)
        if not pool:
            return []

        idle_equipment = [
            str(equipment_id)
            for equipment_id, machine in sorted(stage_state.get("machines", {}).items())
            if self._is_machine_available(machine, decision_state)
        ]
        if not idle_equipment:
            return []

        tasks_by_group: Dict[tuple[str, str, str], List[int]] = {}
        for uid in pool:
            row = self._task_row(decision_state, uid)
            group = (
                str(row.get("customer_id", "UNKNOWN")),
                str(row.get("material_type", "PRODUCT_DEFAULT")),
                str(row.get("material_type", "PRODUCT_DEFAULT")),
            )
            tasks_by_group.setdefault(group, []).append(uid)

        candidates: List[Dict[str, Any]] = []
        used_signatures = set()
        equipment_id = idle_equipment[0]
        batch_size = int(
            stage_state.get("machines", {}).get(equipment_id, {}).get("batch_size", 1)
        )
        for group, group_uids in sorted(tasks_by_group.items()):
            if len(group_uids) < batch_size:
                continue
            for task_uids in self._best_c_group_combos(
                decision_state,
                group_uids,
                batch_size=batch_size,
                current_time=int(decision_state.get("time", 0) or 0),
            ):
                signature = tuple(task_uids)
                if signature in used_signatures:
                    continue
                used_signatures.add(signature)
                candidates.append(
                    self._candidate_action(
                        decision_state,
                        stage=stage,
                        equipment_id=equipment_id,
                        task_uids=task_uids,
                        candidate_type="PACK",
                        task_type="pack",
                        reason="same_customer_product_group",
                    )
                )

        if not candidates and len(pool) >= batch_size:
            candidates.append(
                self._candidate_action(
                    decision_state,
                    stage=stage,
                    equipment_id=equipment_id,
                    task_uids=pool[:batch_size],
                    candidate_type="PACK",
                    task_type="pack",
                    reason="mixed_group_fallback",
                )
            )
        return self._rank_candidates(candidates)

    def _c_packer_candidates(self, decision_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        stage = "C"
        stage_state = decision_state.get(stage, {})
        pool = self._candidate_pool(stage, stage_state)
        if not pool:
            return []

        idle_equipment = [
            str(equipment_id)
            for equipment_id, machine in sorted(stage_state.get("machines", {}).items())
            if self._is_machine_available(machine, decision_state)
        ]
        if not idle_equipment:
            return []

        current_time = int(decision_state.get("time", 0) or 0)
        remaining_tasks = [
            self._task_from_row(self._task_row(decision_state, uid))
            for uid in pool
            if self._task_row(decision_state, uid)
        ]
        candidates: List[Dict[str, Any]] = []
        for equipment_id in idle_equipment:
            if not remaining_tasks:
                break
            selected_pack = self.policy_stack.packer_c.select_pack(
                list(remaining_tasks),
                current_time,
            )
            if not selected_pack:
                break
            task_uids = [int(task.uid) for task in selected_pack]
            candidates.append(
                self._candidate_action(
                    decision_state,
                    stage=stage,
                    equipment_id=equipment_id,
                    task_uids=task_uids,
                    candidate_type="PACK",
                    task_type="pack",
                    reason=f"{self.policy_stack.config.get('packing_C', 'fifo')}_packer",
                )
            )
            selected_uid_set = set(task_uids)
            remaining_tasks = [
                task for task in remaining_tasks if int(task.uid) not in selected_uid_set
            ]
        return self._rank_candidates(candidates)

    def _best_c_group_combos(
        self,
        decision_state: Dict[str, Any],
        group_uids: List[int],
        batch_size: int,
        current_time: int,
    ) -> List[List[int]]:
        if len(group_uids) == batch_size:
            return [list(group_uids)]
        scored = []
        for combo in combinations(group_uids, batch_size):
            features = self._candidate_features(decision_state, list(combo), current_time)
            scored.append((features["local_score"], list(combo)))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [combo for _, combo in scored[:3]]

    def _candidate_action(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        equipment_id: str,
        task_uids: List[int],
        candidate_type: str,
        task_type: str,
        reason: str,
    ) -> Dict[str, Any]:
        current_time = int(decision_state.get("time", 0) or 0)
        task_rows = self._task_rows(decision_state, task_uids)
        group_key = self._group_key(task_rows, stage, task_type)
        features = self._candidate_features(decision_state, task_uids, current_time)
        candidate = {
            "candidate_id": "",
            "stage": stage,
            "candidate_type": candidate_type,
            "group_key": group_key,
            "equipment_id": str(equipment_id),
            "task_uids": [int(uid) for uid in task_uids],
            "operation_id": stage,
            "task_type": task_type,
            "local_score": features["local_score"],
            "local_rank": 0,
            "features": features,
            "reasons": self._candidate_reasons(task_rows, reason),
            "rule_precheck_status": "ELIGIBLE",
            "policy_source": {
                "factory": self.policy_stack.factory_name,
                "l1_policy_id": self.policy_stack.l1_policy_id,
                "scheduler": self._stage_l1_policy_name(stage),
            },
        }
        candidate["candidate_id"] = self._candidate_id(candidate)
        return candidate

    def _stage_l1_policy_name(self, stage: str) -> str:
        if stage == "A":
            return str(self.policy_stack.config.get("scheduler_A", "fifo"))
        if stage == "B":
            return str(self.policy_stack.config.get("scheduler_B", "fifo"))
        return str(self.policy_stack.config.get("packing_C", "fifo"))

    def _scheduler_for_stage(self, stage: str) -> Any:
        if stage == "A":
            return self.policy_stack.scheduler_a
        if stage == "B":
            return self.policy_stack.scheduler_b
        raise ValueError(f"stage {stage!r} does not use an A/B assignment scheduler")

    def _wait_pool(self, stage: str, stage_state: Dict[str, Any]) -> List[int]:
        wait_pool = [int(uid) for uid in stage_state.get("wait_pool_uids", [])]
        if stage == "B":
            incoming = [int(uid) for uid in stage_state.get("incoming_from_A_uids", [])]
            return self._dedupe(incoming + wait_pool)
        return self._dedupe(wait_pool)

    def _scheduler_context(
        self,
        decision_state: Dict[str, Any],
        stage_state: Dict[str, Any],
        machine_state: Dict[str, Any],
        wait_candidates: List[int],
        rework_candidates: List[int],
    ) -> Dict[str, Any]:
        tasks = decision_state.get("tasks", {})
        return {
            "wait_pool_tasks": [
                tasks[uid] for uid in wait_candidates if uid in tasks
            ],
            "rework_pool_tasks": [
                tasks[uid] for uid in rework_candidates if uid in tasks
            ],
            "tasks_by_uid": {
                uid: tasks[uid]
                for uid in self._dedupe(rework_candidates + wait_candidates)
                if uid in tasks
            },
            "machine_state": machine_state,
            "queue_info": {
                "wait_pool_size": len(wait_candidates),
                "rework_pool_size": len(rework_candidates),
                "rework_queue_size": len(rework_candidates),
            },
            "current_time": int(decision_state.get("time", 0) or 0),
            "stage_state": stage_state,
        }

    def _select_batch(
        self,
        scheduler: Any,
        wait_candidates: List[int],
        rework_candidates: List[int],
        batch_size: int,
        context: Dict[str, Any],
    ) -> tuple[List[int], Optional[str]]:
        selector = getattr(scheduler, "select_batch_with_context", None)
        if callable(selector):
            selection = selector(
                wait_candidates,
                rework_candidates,
                batch_size,
                context=context,
            )
        else:
            selection = scheduler.select_batch(
                wait_candidates,
                rework_candidates,
                batch_size,
            )
        if not selection:
            return [], None
        selected_uids, task_type = selection
        return [int(uid) for uid in selected_uids], task_type

    @staticmethod
    def _dedupe(values: List[int]) -> List[int]:
        seen = set()
        ordered = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _task_from_row(self, row: Dict[str, Any]) -> Task:
        spec_a_raw = row.get("spec_a", (45.0, 55.0))
        spec_b_raw = row.get("spec_b", (20.0, 80.0))
        task = Task(
            uid=int(row.get("uid")),
            job_id=str(row.get("job_id", "UNKNOWN")),
            due_date=int(row.get("due_date", 0)),
            spec_a=(float(spec_a_raw[0]), float(spec_a_raw[1])),
            spec_b=(float(spec_b_raw[0]), float(spec_b_raw[1])),
            arrival_time=int(row.get("arrival_time", 0)),
        )
        task.customer_id = row.get("customer_id", "UNKNOWN")
        task.location = row.get("location", "QUEUE_C")
        task.rework_count = int(row.get("rework_count", 0))
        task.material_type = row.get("material_type", "plastic")
        task.color = row.get("color", "red")
        task.margin_value = float(row.get("margin_value", 0.5))
        task.realized_qa_A = float(row.get("realized_qa_A", -1.0))
        task.realized_qa_B = float(row.get("realized_qa_B", -1.0))
        return task

    def _rank_candidates(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ranked = sorted(
            candidates,
            key=lambda item: (
                str(item.get("stage", "")),
                -float(item.get("local_score", 0.0) or 0.0),
                str(item.get("equipment_id", "")),
                list(item.get("task_uids", [])),
            ),
        )
        for index, candidate in enumerate(ranked, start=1):
            candidate["local_rank"] = index
            candidate["candidate_id"] = self._candidate_id(candidate)
        return ranked

    def _candidate_id(self, candidate: Dict[str, Any]) -> str:
        group = candidate.get("group_key", {})
        group_parts = [
            self._slug(str(group.get("customer_id", "UNKNOWN"))),
            self._slug(str(group.get("product_id", "PRODUCT_DEFAULT"))),
            self._slug(str(group.get("material_type", "MATERIAL_DEFAULT"))),
        ]
        uids = "_".join(str(uid) for uid in candidate.get("task_uids", []))
        rank = int(candidate.get("local_rank", 0) or 0)
        return (
            f"CAND_{candidate.get('stage', 'X')}_"
            f"{'_'.join(group_parts)}_"
            f"{self._slug(str(candidate.get('equipment_id', 'EQ')))}_"
            f"{rank:03d}_{self._slug(uids)}"
        )

    def _slug(self, value: str) -> str:
        cleaned = "".join(char if char.isalnum() else "_" for char in value.upper())
        return cleaned.strip("_") or "NA"

    def _group_key(
        self,
        task_rows: List[Dict[str, Any]],
        stage: str,
        task_type: str,
    ) -> Dict[str, str]:
        customer_id = self._single_or_mixed(task_rows, "customer_id", "UNKNOWN")
        material_type = self._single_or_mixed(task_rows, "material_type", "PRODUCT_DEFAULT")
        return {
            "customer_id": customer_id,
            "product_id": material_type,
            "material_type": material_type,
            "operation_id": stage,
            "task_type": task_type,
        }

    def _single_or_mixed(
        self,
        task_rows: List[Dict[str, Any]],
        key: str,
        default: str,
    ) -> str:
        values = {str(row.get(key, default)) for row in task_rows}
        if len(values) == 1:
            return next(iter(values))
        if not values:
            return default
        return "MIXED"

    def _candidate_features(
        self,
        decision_state: Dict[str, Any],
        task_uids: List[int],
        current_time: int,
    ) -> Dict[str, Any]:
        task_rows = self._task_rows(decision_state, task_uids)
        if not task_rows:
            return {
                "avg_quality": 0.0,
                "compatibility": 0.0,
                "avg_wait_time": 0.0,
                "min_due_date": current_time,
                "due_date_pressure": 0.0,
                "margin_value": 0.0,
                "batch_size": 0,
                "local_score": 0.0,
            }

        qualities = [
            float(row.get("realized_qa_B", row.get("realized_qa_A", 50.0)) or 50.0)
            for row in task_rows
        ]
        margins = [float(row.get("margin_value", 0.5) or 0.5) for row in task_rows]
        arrivals = [int(row.get("arrival_time", current_time) or 0) for row in task_rows]
        due_dates = [int(row.get("due_date", current_time) or current_time) for row in task_rows]
        avg_quality = sum(qualities) / len(qualities)
        margin_value = sum(margins) / len(margins)
        avg_wait_time = sum(current_time - arrival for arrival in arrivals) / len(arrivals)
        min_due_date = min(due_dates)
        due_date_pressure = max(0.0, float(current_time - min_due_date))
        compatibility = self._compatibility(task_rows)
        local_score = (
            avg_quality
            + compatibility * 25.0
            + margin_value * 20.0
            + min(avg_wait_time, 100.0) * 0.05
        )
        return {
            "avg_quality": round(avg_quality, 4),
            "compatibility": round(compatibility, 4),
            "avg_wait_time": round(avg_wait_time, 4),
            "min_due_date": min_due_date,
            "due_date_pressure": round(due_date_pressure, 4),
            "margin_value": round(margin_value, 4),
            "batch_size": len(task_rows),
            "local_score": round(local_score, 4),
        }

    def _compatibility(self, task_rows: List[Dict[str, Any]]) -> float:
        if len(task_rows) < 2:
            return 1.0
        same_material = len({str(row.get("material_type", "")) for row in task_rows}) == 1
        same_color = len({str(row.get("color", "")) for row in task_rows}) == 1
        same_customer = len({str(row.get("customer_id", "")) for row in task_rows}) == 1
        score = 0.4
        if same_material:
            score += 0.25
        if same_color:
            score += 0.2
        if same_customer:
            score += 0.15
        return min(1.0, score)

    def _candidate_reasons(
        self,
        task_rows: List[Dict[str, Any]],
        primary_reason: str,
    ) -> List[str]:
        reasons = [primary_reason]
        if task_rows and self._single_or_mixed(task_rows, "customer_id", "UNKNOWN") != "MIXED":
            reasons.append("same_customer")
        if task_rows and self._single_or_mixed(task_rows, "material_type", "PRODUCT_DEFAULT") != "MIXED":
            reasons.append("same_product_material")
        if task_rows and self._compatibility(task_rows) >= 0.95:
            reasons.append("high_compatibility")
        return reasons

    def _task_row(self, decision_state: Dict[str, Any], uid: int) -> Dict[str, Any]:
        tasks = decision_state.get("tasks", {})
        row = tasks.get(uid) or tasks.get(str(uid))
        return dict(row) if isinstance(row, dict) else {}

    def _task_rows(
        self,
        decision_state: Dict[str, Any],
        task_uids: List[int],
    ) -> List[Dict[str, Any]]:
        return [row for uid in task_uids if (row := self._task_row(decision_state, uid))]

    def _a_process_annotation(
        self,
        decision_state: Dict[str, Any],
        candidate: Dict[str, Any],
    ) -> Dict[str, Any]:
        task_rows = self._task_rows(decision_state, candidate.get("task_uids", []))
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        recipe = [10.0, 2.0, 1.0]
        predicted_qa = target
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "A",
            "recipe_id": "SIM_A_BASE",
            "recipe": recipe,
            "parameters": {"temp": recipe[0], "flow": recipe[1], "duration": recipe[2]},
            "replace_consumable": False,
            "predicted_qa": round(predicted_qa, 4),
            "target_spec": {"low": spec_low, "high": spec_high, "target": target},
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "apc_policy": "A_BASE_PRESELECT",
            "quality_risk": "LOW" if spec_low <= predicted_qa <= spec_high else "HIGH",
            "selection_reason": "a_candidate_process_annotation",
        }

    def _b_process_annotation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        recipe = [50.0, 50.0, 30.0]
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "B",
            "recipe_id": "SIM_B_DEFAULT",
            "recipe": recipe,
            "parameters": {"chem_a": recipe[0], "chem_b": recipe[1], "time": recipe[2]},
            "replace_solution": False,
            "predicted_risk": "LOW",
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "quality_risk": "LOW",
            "selection_reason": "b_candidate_process_annotation",
        }

    def _c_process_annotation(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        features = dict(candidate.get("features", {}) or {})
        compatibility = float(features.get("compatibility", 0.0) or 0.0)
        if compatibility >= 0.9:
            quality_risk = "LOW"
        elif compatibility >= 0.75:
            quality_risk = "MEDIUM"
        else:
            quality_risk = "HIGH"
        return {
            "candidate_id": candidate.get("candidate_id"),
            "stage": "C",
            "recipe_id": "SIM_C_NO_RECIPE",
            "recipe": [],
            "pack_quality_prediction": features.get("avg_quality"),
            "compatibility": compatibility,
            "pack_mode": "STANDARD",
            "quality_risk": quality_risk,
            "apc_mode": "L2_PRESELECT_ANNOTATION",
            "selection_reason": "c_candidate_process_annotation",
        }

    def _a_selected_process_action(
        self,
        decision_state: Dict[str, Any],
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        machine_state = self._machine_state(
            decision_state,
            "A",
            str(dispatch_action.get("equipment_id", "")),
        )
        task_rows = self._task_rows(decision_state, dispatch_action.get("task_uids", []))
        spec_low, spec_high = self._spec_window(task_rows, "spec_a", (47.1, 52.9))
        target = (spec_low + spec_high) / 2.0
        recipe = self.policy_stack.tuner_a.get_recipe(
            task_rows=task_rows,
            machine_state=machine_state,
            queue_info={
                "wait_pool_size": len(decision_state.get("A", {}).get("wait_pool_uids", [])),
                "rework_pool_size": len(decision_state.get("A", {}).get("rework_pool_uids", [])),
            },
            current_time=int(decision_state.get("time", 0) or 0),
        )
        replace_consumable = self.policy_stack.tuner_a.should_replace_consumable(
            machine_state,
        )
        current_u = float(machine_state.get("u", 0))
        current_age = float(machine_state.get("m_age", 0))
        predicted_qa = self._predict_a_qa(
            recipe=recipe,
            current_u=current_u,
            current_age=current_age,
            replace_consumable=replace_consumable,
        )
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": self._a_recipe_id(recipe),
            "recipe": recipe,
            "parameters": {"temp": recipe[0], "flow": recipe[1], "duration": recipe[2]},
            "replace_consumable": bool(replace_consumable),
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "A_RULE_BASED_TUNER",
            "policy_source": self._l2_policy_source("A"),
            "predicted_qa": round(float(predicted_qa), 4),
            "target_spec": {"low": spec_low, "high": spec_high, "target": target},
            "machine_state": {"u": current_u, "m_age": current_age},
            "quality_risk": "LOW" if spec_low <= predicted_qa <= spec_high else "HIGH",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _b_selected_process_action(
        self,
        decision_state: Dict[str, Any],
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        machine_state = self._machine_state(
            decision_state,
            "B",
            str(dispatch_action.get("equipment_id", "")),
        )
        task_rows = self._task_rows(decision_state, dispatch_action.get("task_uids", []))
        recipe = self.policy_stack.tuner_b.get_recipe(
            task_rows=task_rows,
            machine_state=machine_state,
            queue_info={
                "wait_pool_size": len(decision_state.get("B", {}).get("wait_pool_uids", [])),
                "rework_pool_size": len(decision_state.get("B", {}).get("rework_pool_uids", [])),
            },
            current_time=int(decision_state.get("time", 0) or 0),
        )
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": "SIM_B_RULE_BASED",
            "recipe": recipe,
            "parameters": {"chem_a": recipe[0], "chem_b": recipe[1], "time": recipe[2]},
            "replace_solution": bool(
                self.policy_stack.tuner_b.should_replace_solution(machine_state)
            ),
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "B_RULE_BASED_TUNER",
            "policy_source": self._l2_policy_source("B"),
            "quality_risk": "LOW",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _c_selected_process_action(
        self,
        dispatch_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        features = dict(dispatch_action.get("features", {}) or {})
        compatibility = float(features.get("compatibility", 0.0) or 0.0)
        return {
            "candidate_id": dispatch_action.get("candidate_id"),
            "recipe_id": "SIM_C_NO_RECIPE",
            "recipe": [],
            "apc_mode": "L1L2_COMPOSED",
            "apc_policy": "C_RULE_BASED_PACK_QUALITY",
            "policy_source": self._l2_policy_source("C"),
            "pack_quality_prediction": features.get("avg_quality"),
            "compatibility": compatibility,
            "pack_mode": "STANDARD",
            "quality_risk": "LOW" if compatibility >= 0.8 else "MEDIUM",
            "selection_reason": "factory_rule_based_apc_for_selected_candidate",
        }

    def _l2_policy_source(self, stage: str) -> Dict[str, str]:
        if stage == "A":
            policy = str(self.policy_stack.config.get("tuner_A", "rule-based"))
        elif stage == "B":
            policy = str(self.policy_stack.config.get("tuner_B", "rule-based"))
        else:
            policy = "rule-based"
        return {
            "factory": self.policy_stack.factory_name,
            "l2_policy_id": self.policy_stack.l2_policy_id,
            "apc_policy": policy,
        }

    def _a_recipe_id(self, recipe: List[float]) -> str:
        known = {
            (10.0, 2.0, 1.0): "SIM_A_BASE",
            (12.0, 2.5, 1.2): "SIM_A_MEDIUM_APC",
            (15.0, 3.0, 1.5): "SIM_A_STRONG_APC",
            (18.0, 4.0, 2.0): "SIM_A_AGE_APC",
        }
        key = tuple(float(value) for value in recipe)
        return known.get(key, "SIM_A_RULE_BASED")

    def _machine_state(
        self,
        decision_state: Dict[str, Any],
        stage: str,
        equipment_id: str,
    ) -> Dict[str, Any]:
        machines = decision_state.get(stage, {}).get("machines", {})
        if equipment_id in machines and isinstance(machines[equipment_id], dict):
            return machines[equipment_id]
        suffix = equipment_id.split("_")[-1]
        for machine_id, machine_state in machines.items():
            if (
                str(machine_id).split("_")[-1] == suffix
                and isinstance(machine_state, dict)
            ):
                return machine_state
        return {}

    def _predict_a_qa(
        self,
        recipe: List[float],
        current_u: float,
        current_age: float,
        replace_consumable: bool,
    ) -> float:
        s1, s2, s3 = recipe
        expected_u = 1.0 if replace_consumable else current_u + 1.0
        expected_age = current_age + 1.0
        w1 = W1_BASE * (1 - DELTA_W1 * expected_age)
        w12 = W12_BASE * (1 - DELTA_W12 * expected_age)
        b = B_BASE - DELTA_B * expected_age
        g_s = (w1 * s1 + W2_BASE * s2 + W3_BASE * s3 + b) + (w12 * s1 * s2)
        effectiveness = 1 - BETA * math.tanh(BETA_K * expected_u)
        return float(g_s * effectiveness)

    def _spec_window(
        self,
        task_rows: List[Dict[str, Any]],
        key: str,
        default: tuple[float, float],
    ) -> tuple[float, float]:
        lows = []
        highs = []
        for row in task_rows:
            spec = row.get(key)
            if not isinstance(spec, (list, tuple)) or len(spec) != 2:
                continue
            lows.append(float(spec[0]))
            highs.append(float(spec[1]))
        if not lows or not highs:
            return default
        return max(lows), min(highs)

    def build_rule_only_dispatch_recommendation(
        self,
        decision_state: Dict[str, Any],
        stage: str = "A",
        correlation_id: Optional[str] = None,
    ) -> Optional[AIRecommendation]:
        """Create a baseline L1 recommendation without introducing AI yet."""
        candidates = self.dispatch_candidates(decision_state, stage=stage)
        if not candidates:
            return None
        snapshot = self.create_feature_snapshot(
            decision_state,
            layer_id="L1",
            correlation_id=correlation_id,
            features={"stage": stage.upper(), "candidate_count": len(candidates)},
        )
        return create_recommendation(
            recommendation_type="DISPATCH",
            layer_id="L1",
            objective_id="OBJ_RULE_ONLY_BASELINE",
            policy_id="RULE_ONLY_DISPATCH_BASELINE",
            model_id="rule-engine",
            model_version="0.1.0",
            feature_snapshot_id=snapshot.feature_snapshot_id,
            correlation_id=snapshot.correlation_id,
            candidate_actions=candidates,
            recommended_action=candidates[0],
            score=1.0,
            confidence=1.0,
            reasons=["first_available_rule_candidate"],
        )

    def validate_recommendations(
        self,
        decision_state: Dict[str, Any],
        recommendations: Sequence[AIRecommendation],
    ) -> RuleValidationResult:
        return self.rule_engine.validate_recommendations(decision_state, recommendations)

    def simulator_actions_from_validation(
        self,
        validation: RuleValidationResult,
    ) -> Dict[str, Dict[str, Any]]:
        if not validation.passed:
            return {"A": {}, "B": {}, "C": {}}
        return self.adapter.command_to_simulator_actions(validation.validated_command)

    def _candidate_pool(self, stage: str, stage_state: Dict[str, Any]) -> List[int]:
        pool = [int(uid) for uid in stage_state.get("rework_pool_uids", [])]
        pool.extend(int(uid) for uid in stage_state.get("wait_pool_uids", []))
        if stage == "B":
            pool = [int(uid) for uid in stage_state.get("incoming_from_A_uids", [])] + pool
        if stage == "C":
            pool = pool + [int(uid) for uid in stage_state.get("incoming_from_B_uids", [])]
        seen = set()
        ordered = []
        for uid in pool:
            if uid in seen:
                continue
            seen.add(uid)
            ordered.append(uid)
        return ordered

    def _is_machine_available(
        self,
        machine_state: Dict[str, Any],
        decision_state: Dict[str, Any],
    ) -> bool:
        status = str(machine_state.get("status", ""))
        if status == "idle":
            return True
        if status != "busy":
            return False
        try:
            finish_time = int(machine_state.get("finish_time", -1))
            current_time = int(decision_state.get("time", 0))
        except (TypeError, ValueError):
            return False
        return finish_time <= current_time
