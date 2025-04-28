from typing import List, Optional
from game.components.encounters.components.encounter_component import EncounterComponent


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

        if self.source == "choice" and self.options:
            # Let player choose from options
            choice = ui.show_choice(
                f"Choose {self.count} {self.asset_type}(s):", self.options
            )
            if choice == "reserve":
                # Draw from reserve
                raise NotImplementedError
            elif choice == "random":
                # Draw random assets
                raise NotImplementedError
        elif self.source == "reserve":
            # Draw directly from reserve
            raise NotImplementedError
        elif self.source == "random":
            # Draw random assets
            raise NotImplementedError

        # Add assets to investigator
        for asset in result["gained_assets"]:
            investigator.items.append(asset)

        return result
