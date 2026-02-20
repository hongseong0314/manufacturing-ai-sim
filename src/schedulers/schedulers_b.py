# -*- coding: utf-8 -*-
"""Assignment schedulers for process B."""

from typing import Any, Dict, List, Optional, Tuple


BatchSelection = Optional[Tuple[List[int], Optional[str]]]


class BaseScheduler:
    """Assignment-only scheduler interface for process B."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.process_time = config.get("process_time_B", 4)

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


class FIFOBaseline(BaseScheduler):
    """FIFO assignment scheduler for process B."""

    def should_schedule(self) -> bool:
        return True

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        return self._select_with_rework_priority(wait_pool_uids, rework_pool_uids, batch_size)


class RuleBasedScheduler(BaseScheduler):
    """Rule-based assignment scheduler for process B.

    In assignment-only mode, queue priority remains rework-first FIFO.
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
    """RL placeholder scheduler for process B."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.fallback = RuleBasedScheduler(config)

    def should_schedule(self) -> bool:
        return True

    def select_batch(
        self,
        wait_pool_uids: List[int],
        rework_pool_uids: List[int],
        batch_size: int,
    ) -> BatchSelection:
        return self.fallback.select_batch(wait_pool_uids, rework_pool_uids, batch_size)
