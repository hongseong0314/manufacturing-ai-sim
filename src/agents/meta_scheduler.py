# -*- coding: utf-8 -*-
"""Meta scheduler interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseMetaScheduler(ABC):
    """Interface for external orchestration policy."""

    @abstractmethod
    def decide(self, state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Return V1 environment actions for A/B/C."""
        raise NotImplementedError
