from typing import List, Optional
from game.entities.base.component import EncounterComponent


class AssetGainComponent(EncounterComponent):
    def __init__(
        self,
        asset_type: str,
        count: int = 1,
        source: Optional[str] = None,
        options: Optional[List[str]] = None,
    ):
        self.asset_type = asset_type
        self.count = count
        self.source = source
        self.options = options or []

    def process(self, state, investigator, ui=None):
        result = {
            "type": "asset_gain",
            "asset_type": self.asset_type,
            "count": self.count,
            "source": self.source,
            "options": self.options,
            "gained_assets": [],
        }

        if self.source == "choice" and self.options and ui:
            choice = ui.show_choice(
                f"Choose {self.count} {self.asset_type}(s):", self.options
            )
            result["choice"] = choice
            
            if choice == "reserve":
                result["choice_type"] = "reserve"
            elif choice == "random":
                result["choice_type"] = "random"
        elif self.source == "reserve":
            result["source_type"] = "reserve"
        elif self.source == "random":
            result["source_type"] = "random"

        # Add assets to investigator - this would be handled by the phase controller
        # based on the result information
        
        return result
