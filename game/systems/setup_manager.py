from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum


class GameDifficulty(Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    INSANE = "insane"
    STAGED = "staged"


@dataclass
class SetupConfig:
    """Configuration for game setup"""

    num_players: int
    ancient_one_id: int
    investigator_ids: int
    difficulty: GameDifficulty = GameDifficulty.NORMAL
    # future: add expansion ids


class SetupManager:
    def __init__(self, state, factories=None):
        self.state = state
        self.factories = factories

    def initialize_game(self, config: SetupConfig) -> None:
        self.state.setup_config = config

        # 1. choose investigators

        # 2. choose ancient one

        # 3. initalize decks/stacks/etc

        # 4. resolve other starting effects

    def _choose_investigators(self) -> List[int]:
        pass

    def _setup_investigators(self, investigator_ids: List[int]) -> None:
        pass

    def _choose_ancient_one(self) -> int:
        pass

    def _setup_ancient_one(self, ancient_one_id: int) -> None:
        pass

    def _resolve_starting_effects(self):
        pass
