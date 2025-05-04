from dataclasses import dataclass, field
from typing import List
from game.enums import AncientOneDifficulty, Expansion
from game.entities.cards.monster import Monster
import random


@dataclass
class MythosDeckStage:
    """Defines the composition of the Mythos deck for each ancient one"""

    green: int = 0
    yellow: int = 0
    blue: int = 0


@dataclass
class AncientOne:
    """Represents an Ancient One in the game."""

    name: str
    difficulty: AncientOneDifficulty
    subTitle: str
    description: str
    starting_doom: int
    mysteries_to_solve: int
    expansion: Expansion

    mythos_deck_stages: List[MythosDeckStage] = field(default_factory=list)

    awakened: bool = False
    defeated: bool = False
    ui = None  # UI reference for the ancient one methods. Temporary hack.

    def set_ui(self, ui):
        """Set the UI reference for Ancient One."""
        self.ui = ui

    def on_setup(self, game_state):
        """Called when the Ancient One is set up for the game."""
        game_state.mythos_deck = self._build_mythos_deck(game_state)
        game_state.doom_track = self.starting_doom

        # Free memory by clearing the factory
        game_state._mythos_factory = None

    def on_reckoning(self, game_state):
        """Called when the Ancient One's Reckoning is triggered."""
        pass

    def on_omen_advance(self, game_state):
        """Called when an Omen is advanced."""
        pass

    def on_awakening(self, game_state):
        """Called when the Ancient One awakens."""
        pass

    def on_investigator_move(self, game_state, investigator):
        """Called when an investigator moves to a new location."""
        pass

    def get_cultist(self, game_state) -> Monster:
        """Returns the Cultist monster for this Ancient One."""
        monster = Monster()
        return monster

    def check_defeat_conditions(self, game_state) -> tuple[bool, bool]:
        """
        Checks for win or loss conditions.
        Returns:
            tuple: (game_over, investigators_win)
        """
        if not self.awakened and game_state.mysteries_solved >= self.mysteries_to_solve:
            self.defeated = True
            return True, True
        elif not self.awakened and game_state.doom_track == 0:
            self.defeated = True
            return True, False
        elif self.awakened:
            # Ancient one specific conditions
            return self._check_awakened_defeat_conditions(game_state)

        return False, False

    def _build_mythos_deck(self, game_state):
        """Builds the Mythos deck for this Ancient One."""
        stage_decks = []

        # mythos_deck_stages=[
        #     MythosDeckStage(green=1, yellow=2, blue=1),  # Stage I
        #     MythosDeckStage(green=2, yellow=3, blue=0),  # Stage II
        #     MythosDeckStage(green=2, yellow=4, blue=0)   # Stage III
        # ]

        for i, stage in enumerate(self.mythos_deck_stages):
            stage_deck = self._build_stage_deck(game_state, stage, i)
            stage_decks.append(stage_deck)

        final_deck = []
        for deck in reversed(stage_decks):
            final_deck.extend(deck)

        return final_deck

    def _build_stage_deck(self, game_state, stage, stage_number):
        """Builds a deck for a specific stage."""
        stage_cards = []
        difficulty = game_state.difficulty

        if stage.green > 0:
            green_cards = game_state.mythos_factory.get_cards(
                "green", stage.green, difficulty
            )
            stage_cards.extend(green_cards)
        if stage.yellow > 0:
            yellow_cards = game_state.mythos_factory.get_cards(
                "yellow", stage.yellow, difficulty
            )
            stage_cards.extend(yellow_cards)
        if stage.blue > 0:
            blue_cards = game_state.mythos_factory.get_cards(
                "blue", stage.blue, difficulty
            )
            stage_cards.extend(blue_cards)

        random.shuffle(stage_cards)

        return stage_cards

    def _check_awakened_defeat_conditions(self, game_state):
        """Checks for defeat conditions when the Ancient One is awakened."""
        pass
