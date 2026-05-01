# -*- coding: utf-8 -*-
"""In-memory audit store for the simulator-backed MES shell.

The first production target is a PostgreSQL-backed repository. This in-memory
implementation gives the harness a real persistence boundary now, while keeping
the simulator kernel untouched.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.mes.adapters import wafer_id_from_task_uid
from src.mes.domain import (
    AIRecommendation,
    Event,
    FeatureSnapshot,
    MESCommand,
    RuleValidationResult,
)
from src.mes.recommendations import make_id


RECOMMENDATION_EVENT_TYPES = {
    "OBJECTIVE": "OBJECTIVE_SELECTED",
    "STAGE_PRIORITY": "STAGE_PRIORITY_UPDATED",
    "DISPATCH": "DISPATCH_RECOMMENDED",
    "PACK": "PACK_RECOMMENDED",
    "RECIPE": "RECIPE_RECOMMENDED",
    "MAINTENANCE": "RECIPE_RECOMMENDED",
}


class InMemoryMESStore:
    """Small repository for recommendation, command, and event audit records."""

    def __init__(self):
        self._feature_snapshots: Dict[str, FeatureSnapshot] = {}
        self._recommendations: Dict[str, AIRecommendation] = {}
        self._validations: List[RuleValidationResult] = []
        self._commands: Dict[str, MESCommand] = {}
        self._events: List[Event] = []

    def record_harness_result(
        self,
        generated: Any,
        _evaluation: Any,
    ) -> Optional[MESCommand]:
        """Persist one planner -> generator -> evaluator decision artifact."""
        validation = generated.validation
        command = self._command_from_validation(
            validation,
            generated.simulator_actions,
        )

        for snapshot in getattr(generated, "feature_snapshots", []):
            self.add_feature_snapshot(snapshot)

        for recommendation in generated.recommendations:
            recommendation.rule_validation_status = validation.validation_status
            recommendation.rule_validation_reasons = list(validation.reasons)
            if command is not None:
                recommendation.final_command_id = command.command_id
            self.add_recommendation(recommendation)
            self.add_event(self._recommendation_event(recommendation))

        self.add_validation(validation)
        self.add_event(self._validation_event(validation, generated.recommendations))

        if command is not None:
            self.add_command(command)
            self.add_event(self._command_event(command, event_type="COMMAND_CREATED"))

        return command

    def add_feature_snapshot(self, snapshot: FeatureSnapshot) -> None:
        self._feature_snapshots[snapshot.feature_snapshot_id] = snapshot

    def add_recommendation(self, recommendation: AIRecommendation) -> None:
        self._recommendations[recommendation.recommendation_id] = recommendation

    def add_validation(self, validation: RuleValidationResult) -> None:
        self._validations.append(validation)

    def add_command(self, command: MESCommand) -> None:
        self._commands[command.command_id] = command

    def add_event(self, event: Event) -> None:
        self._events.append(event)

    def feature_snapshots(
        self,
        correlation_id: Optional[str] = None,
    ) -> List[FeatureSnapshot]:
        snapshots = list(self._feature_snapshots.values())
        if correlation_id is None:
            return snapshots
        return [
            snapshot
            for snapshot in snapshots
            if snapshot.correlation_id == correlation_id
        ]

    def recommendations(
        self,
        correlation_id: Optional[str] = None,
    ) -> List[AIRecommendation]:
        recommendations = list(self._recommendations.values())
        if correlation_id is None:
            return recommendations
        return [
            recommendation
            for recommendation in recommendations
            if recommendation.correlation_id == correlation_id
        ]

    def validations(
        self,
        correlation_id: Optional[str] = None,
    ) -> List[RuleValidationResult]:
        if correlation_id is None:
            return list(self._validations)
        return [
            validation
            for validation in self._validations
            if validation.correlation_id == correlation_id
        ]

    def commands(
        self,
        correlation_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[MESCommand]:
        commands = list(self._commands.values())
        if correlation_id is not None:
            commands = [
                command
                for command in commands
                if command.correlation_id == correlation_id
            ]
        if status is not None:
            commands = [command for command in commands if command.status == status]
        return commands

    def events(
        self,
        correlation_id: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> List[Event]:
        events = list(self._events)
        if correlation_id is not None:
            events = [
                event
                for event in events
                if event.correlation_id == correlation_id
            ]
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        return events

    def record_command_executed(
        self,
        command_id: str,
        step_result: Optional[Dict[str, Any]] = None,
        post_decision_state: Optional[Dict[str, Any]] = None,
    ) -> Optional[MESCommand]:
        command = self._commands.get(command_id)
        if command is None:
            return None
        command.status = "EXECUTED"
        self.add_event(
            self._command_event(
                command,
                event_type="COMMAND_EXECUTED",
                payload={
                    "command": command.to_dict(),
                    "step_result": dict(step_result or {}),
                    "post_time": (post_decision_state or {}).get("time"),
                    "num_completed": (post_decision_state or {}).get("num_completed"),
                },
            )
        )
        return command

    def _command_from_validation(
        self,
        validation: RuleValidationResult,
        simulator_actions: Dict[str, Dict[str, Any]],
    ) -> Optional[MESCommand]:
        if not validation.passed:
            return None
        command = dict(validation.validated_command)
        return MESCommand(
            command_id=make_id("CMD"),
            command_type=str(command.get("command_type", "RESERVE_AND_TRACK_IN")),
            correlation_id=validation.correlation_id,
            validation_status=validation.validation_status,
            validated_command=command,
            simulator_actions=simulator_actions,
            reasons=list(validation.reasons),
        )

    def _recommendation_event(self, recommendation: AIRecommendation) -> Event:
        action = dict(recommendation.recommended_action or {})
        return Event(
            event_id=make_id("EVT"),
            event_type=RECOMMENDATION_EVENT_TYPES.get(
                recommendation.recommendation_type,
                f"{recommendation.recommendation_type}_RECOMMENDED",
            ),
            correlation_id=recommendation.correlation_id,
            actor_type="AI",
            recommendation_id=recommendation.recommendation_id,
            parent_recommendation_id=recommendation.parent_recommendation_id,
            layer_id=recommendation.layer_id,
            lot_id=action.get("lot_id"),
            wafer_ids=self._wafer_ids(action),
            equipment_id=action.get("equipment_id"),
            operation_id=action.get("operation_id") or action.get("stage"),
            recipe_id=action.get("recipe_id"),
            payload=recommendation.to_dict(),
        )

    def _validation_event(
        self,
        validation: RuleValidationResult,
        recommendations: List[AIRecommendation],
    ) -> Event:
        return Event(
            event_id=make_id("EVT"),
            event_type=(
                "RULE_VALIDATION_PASSED"
                if validation.passed
                else "RULE_VALIDATION_REJECTED"
            ),
            correlation_id=validation.correlation_id,
            actor_type="RULE_ENGINE",
            payload={
                "validation": validation.to_dict(),
                "recommendation_ids": [
                    recommendation.recommendation_id
                    for recommendation in recommendations
                ],
            },
        )

    def _command_event(
        self,
        command: MESCommand,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Event:
        command_payload = payload or {"command": command.to_dict()}
        validated_command = command.validated_command
        return Event(
            event_id=make_id("EVT"),
            event_type=event_type,
            correlation_id=command.correlation_id,
            actor_type="SYSTEM",
            equipment_id=validated_command.get("equipment_id"),
            operation_id=validated_command.get("operation_id")
            or validated_command.get("stage"),
            wafer_ids=self._wafer_ids(validated_command),
            recipe_id=validated_command.get("recipe_id"),
            payload=command_payload,
        )

    def _wafer_ids(self, action: Dict[str, Any]) -> List[str]:
        wafer_ids = action.get("wafer_ids")
        if isinstance(wafer_ids, list):
            return [str(wafer_id) for wafer_id in wafer_ids]
        task_uids = action.get("task_uids")
        if not isinstance(task_uids, list):
            return []
        return [wafer_id_from_task_uid(int(uid)) for uid in task_uids]
