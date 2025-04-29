from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class EncounterComponent(ABC):
    @abstractmethod
    def process(self, state, investigator, ui=None) -> Dict[str, Any]:
        pass


class CardComponent(ABC):
    @abstractmethod
    def process(self, staet, investigator, target=None, **kwargs):
        """Apply this comonent's effect"""
        pass
