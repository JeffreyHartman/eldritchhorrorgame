from typing import List, Optional, Union
from game.entities.base.component import EncounterComponent
from game.enums import AssetTrait


class AssetGainComponent(EncounterComponent):
    def __init__(
        self,
        asset_type: Union[str, AssetTrait],
        count: int = 1,
        source: Optional[str] = None,
        options: Optional[List[str]] = None,
        specific_asset_id: Optional[str] = None,
    ):
        self.asset_type = asset_type
        self.count = count
        self.source = source
        self.options = options or []
        self.specific_asset_id = specific_asset_id

    def process(self, state, investigator, ui=None):  # investigator will be used by phase controller
        result = {
            "type": "asset_gain",
            "asset_type": self.asset_type.value if isinstance(self.asset_type, AssetTrait) else self.asset_type,
            "count": self.count,
            "source": self.source,
            "options": self.options,
            "specific_asset_id": self.specific_asset_id,
            "gained_assets": [],
        }

        # If we're gaining a specific asset
        if self.specific_asset_id:
            asset = state.asset_factory.get_asset(self.specific_asset_id)
            if asset:
                result["gained_assets"].append(asset.id)
                # The actual adding to investigator will be handled by the phase controller
            return result

        # If we're choosing from options
        if self.source == "choice" and self.options and ui:
            choice = ui.show_choice(
                f"Choose {self.count} {self.asset_type}(s):", self.options
            )
            result["choice"] = choice

            if choice == "reserve":
                # Choose from reserve
                if ui and state.asset_deck and state.asset_deck.reserve:
                    reserve_options = [f"{i+1}. {asset.name}" for i, asset in enumerate(state.asset_deck.reserve)]
                    reserve_choice = ui.show_choice("Choose an asset from the reserve:", reserve_options)
                    if reserve_choice and reserve_choice.isdigit():
                        index = int(reserve_choice) - 1
                        asset = state.asset_deck.take_from_reserve(index)
                        if asset:
                            result["gained_assets"].append(asset.id)

                result["choice_type"] = "reserve"
            elif choice == "random":
                # Draw random assets
                for _ in range(self.count):
                    if state.asset_deck:
                        asset = state.asset_deck.draw()
                        if asset:
                            result["gained_assets"].append(asset.id)

                result["choice_type"] = "random"
        elif self.source == "reserve":
            # Choose from reserve
            if ui and state.asset_deck and state.asset_deck.reserve:
                reserve_options = [f"{i+1}. {asset.name}" for i, asset in enumerate(state.asset_deck.reserve)]
                reserve_choice = ui.show_choice("Choose an asset from the reserve:", reserve_options)
                if reserve_choice and reserve_choice.isdigit():
                    index = int(reserve_choice) - 1
                    asset = state.asset_deck.take_from_reserve(index)
                    if asset:
                        result["gained_assets"].append(asset.id)

            result["source_type"] = "reserve"
        elif self.source == "random":
            # Draw random assets
            for _ in range(self.count):
                if state.asset_deck:
                    asset = state.asset_deck.draw()
                    if asset:
                        result["gained_assets"].append(asset.id)

            result["source_type"] = "random"

        # The actual adding to investigator will be handled by the phase controller
        return result
