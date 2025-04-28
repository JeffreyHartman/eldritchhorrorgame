from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class EncounterComponent(ABC):
    @abstractmethod
    def process(self, state, investigator, ui=None) -> Dict[str, Any]:
        """
        Process this component's effect during an encounter

        Args:
            state: The current game state
            investigator: The investigator experiencing the encounter

        Returns:
            Dict containing results of processing this component
        """
        pass
