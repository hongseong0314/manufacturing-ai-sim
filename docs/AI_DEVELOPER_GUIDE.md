# AI Developer Guide: Manufacturing Simulation Toolkit

**Target Audience:** AI Assistants (Gemini, Claude, Copilot, etc.) & Research Engineers
**Purpose:** strict, code-centric instructions for implementing new manufacturing logic without breaking the core architecture.

---

## 1. System Intent & Architecture
This repository is a **Modular Research Sandbox** for manufacturing decision-making.
- **Core Goal:** Allow researchers to plug in new algorithms (Schedulers, Tuners, Packers) or new process physics (Env) *without* rewriting the orchestration loop.
- **Key Abstraction:**
  - `Environment`: Handles physics, state transitions, and logging. (The "Body")
  - `Agents/Schedulers`: Handle decision logic. (The "Brain")
  - `Interface`: A strict dictionary-based contract for State and Actions.

## 2. Architectural Safety Rules (Read Before Modifying)

The rules depend on your goal. Are you building a **New Algorithm** or a **New Factory**?

### Mode A: Algorithm Researcher (Default)
*Goal: Test a new Scheduler, Tuner, or Packer on the EXISTING A->B->C process.*

1.  **DO NOT modify `src/environment/manufacturing_env.py`.**
    - *Why:* You want to benchmark against the standard baseline. Changing the environment invalidates the comparison.
2.  **DO NOT modify `src/objects.py`.**
    - *Why:* Your algorithm should work with standard Task/Machine definitions.
3.  **NEVER access `self.env` inside a Scheduler/Tuner.**
    - *Why:* Policies must rely *only* on the `decision_state` snapshot. No backdoors allowed.

### Mode B: Environment Architect (Advanced)
*Goal: Model a DIFFERENT factory (e.g., Chemical Plant, Parallel Lines, New Attributes).*

1.  **Modify `src/objects.py` to define Physics.**
    - *Action:* Add fields like `task.viscosity`, `machine.temperature`, `task.chemical_composition`.
    - *Constraint:* Keep classes as **Data Containers** (dataclasses). Do not add complex simulation logic methods here; keep logic in `Env`.
2.  **Modify `src/environment/manufacturing_env.py` to define Topology.**
    - *Action:* Change `step()` to rewire the flow (e.g., A -> C -> B, or A -> Split -> B/D).
    - *Constraint:* You MUST preserve the `step(actions) -> (obs, reward, done, info)` signature to keep Agent compatibility.
3.  **Update `get_decision_state()`**.
    - *Action:* If you added `machine.temperature`, you must expose it in the `decision_state` dictionary so Agents can see it.

---

## 3. Interface Contracts (Type Hints & Signatures)

### 3.1 Data Structures (`src/objects.py`)
AI must use these structures when parsing state.

```python
@dataclass
class Task:
    uid: int
    job_id: str
    due_date: int
    spec_a: Tuple[float, float]
    spec_b: Tuple[float, float]
    location: str          # e.g., "QUEUE_A", "PROC_1"
    realized_qa_A: float   # Outcome of Process A
    realized_qa_B: float   # Outcome of Process B
    history: List[Dict]    # Event log
```

### 3.2 Scheduler Interface (`src/schedulers/*`)
**Role:** Select *which* tasks to process next.
**Input:** Pool of waiting task UIDs.
**Output:** A list of UIDs to process (batch).

```python
# Contract
class BaseScheduler:
    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> Tuple[List[int], Optional[str]]:
        """
        Returns:
            (batch_uids, task_type)
            - batch_uids: List of task IDs to process.
            - task_type: "new" or "rework" (cannot mix in one batch).
            - Return (None, None) if no batch is selected.
        """
        raise NotImplementedError
```

### 3.3 Tuner Interface (`src/tuners/*`)
**Role:** Decide *how* to process the selected batch (Recipe & Maintenance).
**Input:** Selected task data + Machine state.
**Output:** Recipe parameters (float vector).

```python
# Contract
class BaseRecipeTuner:
    def get_recipe(
        self,
        task_rows: List[Dict[str, Any]],  # Data of selected tasks
        machine_state: Dict[str, Any],    # e.g., {"u": 10, "m_age": 5}
        queue_info: Dict[str, Any],       # e.g., {"queue_size": 50}
        current_time: int,
    ) -> List[float]:
        """
        Returns:
            List[float]: The recipe vector (e.g., [temp, pressure, time]).
        """
        raise NotImplementedError

    def should_replace_consumable(self, machine_state: Dict[str, Any]) -> bool:
        """
        Returns:
            bool: True if maintenance is needed BEFORE this batch.
        """
        return False
```

### 3.4 Packer Interface (`src/schedulers/packers_c.py`)
**Role:** Group finished tasks into a shipment.
**Input:** Pool of completed tasks.
**Output:** A list of UIDs to pack.

```python
# Contract
class BasePacker:
    def select_pack(
        self,
        wait_pool_uids: List[int],
        wait_pool_map: Dict[int, Any],  # uid -> Task object/dict
        batch_size: int,
        current_time: int,
    ) -> List[int]:
        """
        Returns:
            List[int]: List of task UIDs to form a pack.
        """
        raise NotImplementedError
```

---

## 4. Implementation Templates (Copy-Paste-Modify)

### [TEMPLATE-SCHEDULER] Adding a New Scheduling Logic
**Location:** `src/schedulers/schedulers_a.py` or `src/schedulers/schedulers_b.py`

```python
class MyCustomScheduler(BaseScheduler):
    def should_schedule(self) -> bool:
        return True

    def select_batch(self, wait_pool_uids, rework_pool_uids, batch_size):
        # 1. Rework Priority Logic (Recommended)
        if rework_pool_uids:
            return rework_pool_uids[:batch_size], "rework"
        
        # 2. Custom Logic (e.g., Longest Processing Time, Due Date)
        # Note: You only have UIDs here. If you need task data, 
        # you must use the 'context' aware method or inject data.
        # For simple logic:
        selected = wait_pool_uids[:batch_size]
        
        if not selected:
            return None, None
            
        return selected, "new"
```

### [TEMPLATE-TUNER] Adding a New Control Logic
**Location:** `src/tuners/tuners_a.py` or `src/tuners/tuners_b.py`

```python
class MySmartTuner(BaseRecipeTuner):
    def get_recipe(self, task_rows, machine_state, queue_info, current_time):
        # 1. Extract State
        usage = machine_state.get("u", 0)  # Consumable usage
        
        # 2. Logic (e.g., Compensate for wear)
        base_temp = 10.0
        compensation = 0.1 * usage
        
        return [base_temp + compensation, 2.0, 1.0]

    def should_replace_consumable(self, machine_state) -> bool:
        # Maintenance Logic
        return machine_state.get("u", 0) > 20
```

### [TEMPLATE-ENV] Adding a New Process (Process D)
**Location:** `src/environment/process_d_env.py`

1.  Create `ProcessD_Env` inheriting from base logic.
2.  Implement `step(actions)`.
3.  Register in `ManufacturingEnv`.

```python
class ProcessD_Env:
    def __init__(self, config):
        self.config = config
        self.machines = [BaseMachine(i) for i in range(config["num_machines_D"])]
        
    def step(self, actions, current_time):
        # 1. Parse Actions
        # 2. Update Machine State
        # 3. Return (results, info)
        pass
```

## 5. Configuration & Wiring
To activate your new class, you MUST register it in `src/agents/factory.py`.

```python
# src/agents/factory.py

def _build_assignment_scheduler_a(config):
    algo = config.get("scheduler_A", "fifo")
    if algo == "my_custom":
        return MyCustomScheduler(config)  # <--- WIRING
    # ...
```

## 6. Validation Protocol
After implementing, run these commands to verify integrity:

1.  **Sanity Check:** `conda run -n batch_env python -m tests.test_env_validation_matrix`
2.  **Integration:** `conda run -n batch_env python -m tests.test_gantt_validation`

**Success Criteria:**
- No AssertionErrors.
- `results/*.png` are generated.
- Event logs contain your new agent's decisions.

## 7. Process Optimization Objectives (Research Reference)

These are the formal objective functions used by the reference implementations.
Use them as baselines when designing reward functions for RL agents.

### Process A — Machining / Processing

```
maximize  J_A = w_t · Throughput − w_r · ReworkRate − w_d · Tardiness
```

| Term | Definition |
|---|---|
| `Throughput` | Tasks completed per step |
| `ReworkRate` | Fraction of tasks requiring rework (QA failed spec_a) |
| `Tardiness` | Mean positive deviation from `due_date` |
| Default weights | `w_t=1.0, w_r=2.0, w_d=0.5` |

**Decision variables:** recipe `[s1, s2, s3]`, consumable replacement timing.

### Process B — Chemical Cleaning / Wet Process

```
maximize  J_B = w_p · PassRate − w_fp · FalsePassRate − w_r · ReworkLoad
```

| Term | Definition |
|---|---|
| `PassRate` | Fraction of tasks with `spec_b[0] < realized_qa_B < spec_b[1]` |
| `FalsePassRate` | Tasks that passed B but required A-rework (upstream mismatch) |
| `ReworkLoad` | Volume of tasks re-entering the B queue |
| Default weights | `w_p=1.0, w_fp=1.5, w_r=1.0` |

**Decision variables:** recipe `[r1, r2, r3]`, flow speed `v`, replacement timing.

### Process C — Packaging / Bin-Packing

```
maximize  Score(Pack) = α · Quality + β · Compatibility + γ · Margin − δ · TimePenalty
```

| Term | Formula |
|---|---|
| `Quality` | `mean(realized_qa_B for t in Pack)` |
| `Compatibility` | `mean(Compat(ti, tj) for all pairs in Pack)` |
| `Margin` | `mean(t.margin_value for t in Pack)` |
| `TimePenalty` | `max(0, current_time − min(t.due_date for t in Pack))` |
| Default weights | `α=1.0, β=0.5, γ=0.3, δ=0.2` |

**Decision variables:** pack composition (which tasks to group together).

All weights are configurable via the `config` dictionary passed to the respective
agent constructors. Override them in `configs/` scenario files to tune the
trade-off surface for your research objectives.
