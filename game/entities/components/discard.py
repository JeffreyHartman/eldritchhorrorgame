from typing import Any, Dict, Optional
from game.entities.base.component import EncounterComponent


class DiscardComponent(EncounterComponent):
    def __init__(
        self,
        count: int,
        asset_type: str,
        condition_type: Optional[str] = None,
        optional: bool = False,
    ):
        self.count = count
        self.asset_type = asset_type
        self.condition_type = condition_type
        self.optional = optional

    @classmethod
    def from_data(cls, data: Dict[str, Any]) -> "DiscardComponent":
        """Create a discard component from data dictionary"""
        count = data.get("count", 1)
        asset_type = data.get("asset_type", "")
        condition_type = data.get("condition_type", None)
        optional = data.get("optional", False)
        return cls(count, asset_type, condition_type, optional)

    def process(self, state, investigator, ui=None):
        result = {
            "type": "discard",
            "count": self.count,
            "asset_type": self.asset_type,
            "condition_type": self.condition_type,
            "optional": self.optional,
            "discarded_items": [],
        }

        # For optional discards, we need UI interaction
        if self.optional and ui:
            should_discard = ui.ask_yes_no(
                f"Would you like to discard {self.count} {self.asset_type}?"
            )
            result["player_choice"] = should_discard

            if not should_discard:
                # Player chose not to discard
                return result

        # For actual discard implementation, we'll just record what should be discarded
        # The actual discard logic would be handled by the phase controller

        return result
