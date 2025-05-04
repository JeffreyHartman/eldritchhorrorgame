from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class EncounterComponent(ABC):
    @abstractmethod
    def process(self, state, investigator, ui=None) -> Dict[str, Any]:
        """
        Process this component's effect

        Args:
            state: The current game state
            investigator: The investigator this component affects
            ui: Optional UI manager for user interaction

        Returns:
            A dictionary containing the results of processing this component
        """
        pass

    @classmethod
    @abstractmethod
    def from_data(cls, data: Dict[str, Any]) -> "EncounterComponent":
        """Create a component from data dictionary"""
        pass


class CardComponent(ABC):
    @abstractmethod
    def process(self, state, investigator, target=None, **kwargs):
        """Apply this comonent's effect"""
        pass

    @classmethod
    @abstractmethod
    def from_data(cls, data: Dict[str, Any]) -> "CardComponent":
        """Create a component from data dictionary"""
        pass
