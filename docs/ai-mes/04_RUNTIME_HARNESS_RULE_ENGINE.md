# Runtime, Harness, Rule Engine, And Commands

Status: canonical  
Last updated: 2026-05-06

## Purpose

This document defines how layered recommendations become validated commands and
simulator actions.

## Runtime Boundary

The simulator environment is strict external control:

```text
Environment:
  applies physics, queues, QA, machine state, event logs

Policies and MES:
  decide what to recommend, validate, and command
```

The runtime contract:

```python
decision_state = env.get_decision_state()
actions = {"A": {}, "B": {}, "C": {}}
observation, reward, done, info = env.step(actions)
```

The MES must never bypass this contract.

## Current Harness

`MESDevelopmentHarness` currently wires:

```text
MESPlannerAgent
  -> MESGeneratorAgent
  -> MESEvaluatorAgent
  -> InMemoryMESStore / SQLiteMESStore
```

Current `run()` flow:

```text
decision_state
  -> planner.plan()
  -> generator.generate()
  -> evaluator.evaluate()
  -> store.record_harness_result()
  -> evaluator.evaluate(..., store=store)
  -> HarnessRunResult
```

Current `run_and_step()` flow:

```text
run(decision_state)
  -> if evaluation passed and command exists:
       env.step(result.simulator_actions)
       store.record_command_executed(...)
```

This is a useful development harness. The target architecture should keep the
same audit discipline but replace the linear generation model with candidate
portfolio flow.

## Target Harness

Target harness phases:

```text
1. Capture decision_state
2. Generate L1 candidate portfolio
3. Annotate candidates through L2
4. Generate or reuse L4 objective
5. Select L3 stage/group using L4 weights and candidate portfolio
6. Finalize L1 concrete allocation from selected group
7. Finalize L2 recipe/APC/process fields
8. Validate all selected recommendations through Rule Engine
9. Persist recommendation, validation, command, and events
10. Execute command through simulator adapter when requested
11. Persist execution event and post-state summary
```

## Rule Engine Responsibility

`MESRuleEngine` is the only component that converts recommendations into a
validated command.

Current validation checks:

- recommendations exist,
- correlation ids match,
- L1 dispatch/pack recommendation exists,
- equipment id exists,
- stage is known,
- task uids exist and are available,
- equipment is available,
- L2 recipe fields can be copied into the command.

Target validation checks:

- current checks,
- L3 selected stage/group matches L1 selected candidate,
- L4 objective id matches all downstream recommendations,
- L1 selected candidate exists in the submitted candidate portfolio,
- L2 selected recipe/APC references the selected L1 candidate,
- recipe is approved and compatible with operation/equipment,
- duplicate candidate/task assignment is rejected across same cycle,
- command count respects L4/L3 budgets,
- operator approval is required when configured.

## Command Shape

Current command:

```python
{
    "command_type": "RESERVE_AND_TRACK_IN",
    "correlation_id": "...",
    "stage": "A",
    "equipment_id": "A_0",
    "task_uids": [1],
    "task_type": "new",
    "dispatch_recommendation_id": "REC_L1_...",
    "recipe_recommendation_id": "REC_L2_...",
    "recipe": [10.0, 2.0, 1.0],
    "replace_consumable": False
}
```

For C packing:

```python
{
    "command_type": "RESERVE_AND_TRACK_IN",
    "correlation_id": "...",
    "stage": "C",
    "equipment_id": "C_0",
    "task_uids": [101, 104, 109, 112],
    "task_type": "pack",
    "dispatch_recommendation_id": "REC_L1_...",
    "reason": "selected_by_layered_ai"
}
```

The simulator adapter converts commands into:

```python
{"A": {"A_0": {...}}, "B": {}, "C": {}}
```

or:

```python
{"A": {}, "B": {}, "C": {"C_0": {"task_uids": [...], "reason": "..."}}}
```

## Event Chain

The store must emit a chain of audit events:

```text
OBJECTIVE_SELECTED
STAGE_PRIORITY_UPDATED
DISPATCH_RECOMMENDED or PACK_RECOMMENDED
RECIPE_RECOMMENDED or PROCESS_ANNOTATED
RULE_VALIDATION_PASSED / RULE_VALIDATION_REJECTED
COMMAND_CREATED
COMMAND_EXECUTED
```

Simulator process event logs remain separate but should be linked through:

- `correlation_id`,
- `command_id`,
- `equipment_id`,
- `task_uids` / `wafer_ids`,
- `operation_id`,
- `recipe_id`,
- simulator time.

## Evaluator Responsibility

`MESEvaluatorAgent` checks development-time chain integrity.

Current checks:

- required layers exist,
- correlation ids match,
- feature snapshot ids exist,
- parent chain is valid,
- rule validation passed,
- simulator action matches command,
- store contains chain records,
- command and command event align.

Target checks:

- candidate portfolio exists before upper selection,
- selected L3 group appears in L1 portfolio,
- L2 annotation references selected L1 candidate,
- L4 objective weights are present,
- rule validation cites the exact L1/L2 recommendations used,
- command execution result links to post-decision state,
- rejected chains preserve rejection reasons and do not create commands.

## Runtime Modes

### Preview

Preview creates recommendations, validation, and optionally command preview
without stepping the simulator.

### Execute

Execute validates and calls `env.step()`.

### Auto

Current auto mode scans ready stages and may execute multiple commands in one
simulator tick. Target auto mode should source stage/group priority from L3
selection over candidate portfolios, not from a hard-coded C/B/A ready-stage
scan.

## Safety Rules

- No command executes without Rule Engine validation.
- Rejected validation creates events but no command.
- Duplicate task assignment in the same command batch is rejected or sanitized.
- Environment modules must not contain scheduling decisions.
- AI recommendation status must be updated after validation.
- Commands must keep the `correlation_id` that links the full chain.

