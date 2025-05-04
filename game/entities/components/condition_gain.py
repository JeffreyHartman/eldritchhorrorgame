from typing import Any, Dict, Optional, Union, List
from game.entities.base.component import EncounterComponent
from game.entities.investigator import Investigator


class ConditionGainComponent(EncounterComponent):
    """Component that adds a condition to an investigator.

    This component can add either a specific condition by ID or a random
    condition with a specific trait.
    """

    def __init__(
        self,
        condition: str,
        trait: Optional[str] = None,
        prevent_duplicates: bool = True,
    ):
        """Initialize the component.

        Args:
            condition: The condition ID to add, or "random" to add a random condition
            trait: If condition is "random", the trait to filter by (e.g., "madness")
            prevent_duplicates: If True, won't add a condition the investigator already has
        """
        self.condition = condition
        self.trait = trait
        self.prevent_duplicates = prevent_duplicates

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "ConditionGainComponent":
        """Create a condition gain component from data dictionary"""
        condition = data.get("condition", "")
        trait = data.get("trait", None)
        prevent_duplicates = data.get("prevent_duplicates", True)
        return cls(condition, trait, prevent_duplicates)

    def process(self, state, investigator: Investigator, ui=None):
        """Process this component's effect.

        Args:
            state: The current game state
            investigator: The investigator to add the condition to
            ui: Optional UI manager for user interaction

        Returns:
            A dictionary containing the results of processing this component
        """
        result = {
            "type": "condition_gain",
            "condition": self.condition,
            "trait": self.trait,
            "gained_condition": None,
            "prevented": False,
        }

        # Check if condition deck is available
        if not hasattr(state, "condition_deck") or not state.condition_deck:
            result["error"] = "No condition deck available"
            return result

        # Handle specific condition
        if self.condition != "random":
            # Check if investigator already has this condition
            if self.prevent_duplicates and investigator.has_condition(self.condition):
                result["prevented"] = True
                return result

            # Try to draw the specific condition
            condition = state.draw_condition(condition_id=self.condition)

            if condition:
                # Add the condition to the investigator
                investigator.add_condition(condition.id)
                result["gained_condition"] = condition.id
            else:
                # Try to recycle from discard pile
                recycled = state.recycle_conditions(condition_id=self.condition)
                if recycled:
                    # Try again after recycling
                    condition = state.draw_condition(condition_id=self.condition)
                    if condition:
                        investigator.add_condition(condition.id)
                        result["gained_condition"] = condition.id
                    else:
                        result["error"] = f"Could not find condition: {self.condition}"
                else:
                    result["error"] = f"Could not find condition: {self.condition}"

        # Handle random condition or condition by trait
        else:
            # Draw a condition with the specified trait or a random one
            condition = None
            if self.trait:
                condition = state.draw_condition(trait=self.trait)
            else:
                condition = state.draw_condition()

            if condition:
                # Check for duplicates if needed
                if self.prevent_duplicates and investigator.has_condition(condition.id):
                    # Put the card back and try again, or just prevent if no other options
                    state.condition_deck.return_to_deck(condition)
                    result["prevented"] = True
                else:
                    # Add the condition to the investigator
                    investigator.add_condition(condition.id)
                    result["gained_condition"] = condition.id
            else:
                result["error"] = "No conditions available"

        return result
