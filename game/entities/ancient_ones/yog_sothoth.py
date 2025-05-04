from dataclasses import dataclass
from typing import Optional
from game.enums import AncientOneDifficulty, Expansion
from game.entities.ancient_ones.ancient_one import AncientOne, MythosDeckStage
from game.entities.cards.monster import Monster


class YogSothoth(AncientOne):

    def __init__(self):
        super().__init__(
            name="Yog-Sothoth",
            difficulty=AncientOneDifficulty.LOW,
            subTitle="The Lurker at the Threshold",
            description="For eons, sorcerers have called upon the power of Yog-Sothoth to bend reality to their will. This incomprehensible Ancient One exists parallel to all places and times, but is bound to the space between dimensions. Gates between worlds continue to open with more frequency and soon, Yog-Sothoth will be free.",
            starting_doom=14,
            mysteries_to_solve=3,
            expansion=Expansion.CORE,
            awakened=False,
            defeated=False,
        )

        # Define mythos deck stages based on the game rules
        self.mythos_deck_stages = [
            MythosDeckStage(green=0, yellow=2, blue=1),  # Stage I
            MythosDeckStage(green=2, yellow=3, blue=1),  # Stage II
            MythosDeckStage(green=3, yellow=4, blue=0),  # Stage III
        ]

        # Ancient One specific properties
        self.gates_on_ancient_one = 0
        self.eldritch_tokens_on_final_mystery = 0

    def on_reckoning(self, game_state):
        """
        Called when the Ancient One's Reckoning is triggered.
        Each investigator on a space containing a Gate advances Doom by 1
        unless they discard 1 Spell.
        """
        reckoning_text = "Each investigator on a space containing a Gate advances Doom Doom by 1 unless he discards 1 Spell"
        game_state.ui.show_message(reckoning_text)

        for investigator in game_state.investigators:
            current_space = investigator.current_location
            if current_space.has_gate:
                # Check if investigator has a spell to discard
                if investigator.has_spell():
                    # Offer choice to discard spell
                    if game_state.ui.confirm_choice(
                        f"{investigator.name} is on a Gate space. Discard a Spell to prevent Doom advance?"
                    ):
                        # Discard a spell
                        spell = game_state.ui.choose_item(
                            "Choose a Spell to discard:", investigator.get_all_spells()
                        )
                        investigator.remove_asset(spell)
                    else:
                        # Advance doom
                        game_state.current_doom -= 1
                        game_state.ui.show_message(
                            f"{investigator.name} advanced Doom by 1!"
                        )
                else:
                    # No spell to discard, doom advances
                    game_state.current_doom -= 1
                    game_state.ui.show_message(
                        f"{investigator.name} has no Spell to discard. Doom advances!"
                    )

    def on_awakening(self, game_state):
        """
        Called when Yog-Sothoth awakens.
        Implements the "Lurker at the Threshold" awakened ability.
        """
        self.awakened = True
        game_state.ui.show_message(
            "Yog-Sothoth has awakened! The ancient horror tears apart the walls between worlds, pouring itself through the cracks in reality."
        )

        # TODO:
        # Implement "Lurker at the Threshold" ability
        # Each time a Gate would cause Doom to advance, place that Gate on this sheet instead.
        # Each time any other effect would cause Doom to advance, place 1 Gate from the Gate stack on this sheet instead.
        # If there are 3 or more Gates on this sheet, investigators lose the game.

        # Add reckoning effect for ancient one

    def on_setup(self, game_state):
        """Called when the Ancient One is set up for the game."""
        # Call the parent method to build the mythos deck
        super().on_setup(game_state)

        # Initialize any Yog-Sothoth specific setup

        self.ui.show_message(
            "For eons, sorcerers have called upon the power of Yog-Sothoth to bend reality to their will. This incomprehensible Ancient One exists parallel to all places and times, but is bound to the space between dimensions. Gates between worlds continue to open with more frequency and soon, Yog-Sothoth will be free."
        )

    def get_cultist(self, game_state) -> Monster:
        """
        Returns the Cultist monster for Yog-Sothoth.
        Cultists have toughness 1 and a special effect related to Spells.
        """
        raise NotImplementedError
        # TODO: Implement Monster class before uncommenting
        # from game.entities.cards.monster import Monster

        # cultist = Monster()
        # cultist.name = "Cultist of Yog-Sothoth"
        # cultist.toughness = 1
        # cultist.horror = 1
        # cultist.damage = 1
        # cultist.special_effect = (
        #     "Before resolving the test, lose 1 Sanity for each Spell you have."
        # )

        # return cultist

    def _check_awakened_defeat_conditions(self, game_state) -> tuple[bool, bool]:
        """
        Checks for win or loss conditions.
        Returns:
            tuple: (game_over, investigators_win)
        """
        # Check for gates on the Ancient One sheet
        if self.gates_on_ancient_one >= 3:
            game_state.ui.show_message(
                "There are 3 or more Gates on Yog-Sothoth! The investigators lose!"
            )
            return True, False

        # Check for Eldritch tokens on the Final Mystery
        if (
            game_state.eldritch_tokens_on_final_mystery
            >= game_state.investigators_count // 2
        ):
            self.defeated = True
            game_state.ui.show_message(
                "The investigators have bound Yog-Sothoth beyond the threshold! The Ancient One is defeated!"
            )
            return True, True

        return False, False
