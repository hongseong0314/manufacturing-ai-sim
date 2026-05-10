# -*- coding: utf-8 -*-
"""L1 candidate portfolio generation for MES decisions."""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional, Sequence

from src.objects import Task


class CandidatePortfolioMixin:
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
