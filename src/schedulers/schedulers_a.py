# -*- coding: utf-8 -*-
"""Assignment schedulers for process A."""

from typing import Any, Dict, List, Optional, Tuple


BatchSelection = Optional[Tuple[List[int], Optional[str]]]


class BaseScheduler:
    """Assignment-only scheduler interface for process A."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process_time = config.get("process_time_A", 15)

    def should_schedule(self) -> bool:
        """Return whether scheduler is active for the current policy mode."""
        raise NotImplementedError

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        """Select a batch of task UIDs and task type (`new`/`rework`)."""
        raise NotImplementedError

    def select_batch_with_context(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
        context: Optional[Dict[str, Any]] = None,
    ) -> BatchSelection:
        """Optional context-aware selection hook.

        Default behavior is backward-compatible and delegates to `select_batch`.
        Custom schedulers can override this method to leverage richer signals,
        for example due-date/spec/quality snapshots from the decision state.
        """
        _ = context
        return self.select_batch(wait_pool_uids, rework_pool_uids, batch_size)

    @staticmethod
    def _select_with_rework_priority(
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        if batch_size <= 0:
            return None, None

        batch: List[int] = []
        task_type: Optional[str] = None

        for uid in rework_pool_uids:
            if len(batch) >= batch_size:
                break
            batch.append(uid)
            task_type = "rework"

        for uid in wait_pool_uids:
            if len(batch) >= batch_size:
                break
            if uid in batch:
                continue
            batch.append(uid)
            if task_type is None:
                task_type = "new"

        if not batch:
            return None, None
        return batch, task_type


class FIFOScheduler(BaseScheduler):
    """FIFO assignment scheduler for process A."""

    def should_schedule(self) -> bool:
        return True

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        return self._select_with_rework_priority(wait_pool_uids, rework_pool_uids, batch_size)


class AdaptiveScheduler(BaseScheduler):
    """Adaptive scheduler for process A.

    In assignment-only mode, this class still prioritizes rework and FIFO ordering.
    """

    def should_schedule(self) -> bool:
        return True

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        return self._select_with_rework_priority(wait_pool_uids, rework_pool_uids, batch_size)


class RLBasedScheduler(BaseScheduler):
    """RL placeholder scheduler for process A.

    Fallback behavior is rework-priority FIFO assignment.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = FIFOScheduler(config)

    def should_schedule(self) -> bool:
        return True

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        return self.fallback.select_batch(wait_pool_uids, rework_pool_uids, batch_size)
