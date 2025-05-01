import json
import os
import logging
from typing import Dict, List, Optional, Any

from game.entities.cards.asset import Asset
from game.enums import AssetTrait, AssetSecondaryTrait


class AssetFactory:
    """
    Factory class for creating assets from JSON data.
    This factory is responsible for:
    1. Loading asset definitions from JSON files
    2. Creating asset objects
    3. Providing assets by ID or trait
    """

    def __init__(self):
        self.assets: Dict[str, Asset] = {}  # Dict of asset_id -> Asset
        self.assets_by_trait: Dict[AssetTrait, List[Asset]] = {}  # Dict of trait -> list of assets
        self.logger = logging.getLogger(__name__)

    def load_all_assets(self) -> None:
        """Load all assets from the data directory."""
        assets_dir = "game/data/assets"

        # Load assets from each trait file
        for trait in AssetTrait:
            self.load_assets_by_trait_file(trait.value)

        # Also load the combined assets file if it exists
        combined_file = os.path.join(assets_dir, "all_assets.json")
        if os.path.exists(combined_file):
            self.load_assets_from_file(combined_file)

    def load_assets_by_trait_file(self, trait_name: str) -> None:
        """
        Load assets from a trait-specific file.

        Args:
            trait_name: Name of the trait (e.g., "item", "ally")
        """
        file_path = f"game/data/assets/{trait_name}_assets.json"
        if os.path.exists(file_path):
            self.load_assets_from_file(file_path)
        else:
            self.logger.info(f"Asset file not found (this is normal for new traits): {file_path}")

    def load_assets_from_file(self, file_path: str) -> None:
        """
        Load multiple assets from a single JSON file.

        Args:
            file_path: Path to the JSON file containing assets
        """
        try:
            with open(file_path, "r") as file:
                assets_data = json.load(file)

                # Handle both array and dictionary formats
                if isinstance(assets_data, list):
                    # Array of asset objects
                    for asset_data in assets_data:
                        self._process_asset_data(asset_data)
                elif isinstance(assets_data, dict):
                    # Dictionary with asset_id as keys
                    for asset_id, asset_data in assets_data.items():
                        # Ensure the asset_id is in the data
                        if "id" not in asset_data:
                            asset_data["id"] = asset_id
                        self._process_asset_data(asset_data)

                self.logger.info(f"Loaded assets from: {file_path}")
        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON in {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading assets from {file_path}: {str(e)}")

    def _process_asset_data(self, asset_data: Dict[str, Any]) -> None:
        """
        Process a single asset's data and add it to the factory.

        Args:
            asset_data: Data for a single asset
        """
        try:
            asset = self._create_asset(asset_data)
            if asset:
                asset_id = asset.id

                # Skip if we already have this asset
                if asset_id in self.assets:
                    return

                self.assets[asset_id] = asset

                # Index by primary trait
                trait = asset.get_primary_trait()
                if trait not in self.assets_by_trait:
                    self.assets_by_trait[trait] = []
                self.assets_by_trait[trait].append(asset)

                self.logger.debug(f"Loaded asset: {asset_id}")
        except Exception as e:
            self.logger.error(f"Error processing asset {asset_data.get('id')}: {str(e)}")

    def load_asset(self, asset_id: str) -> Optional[Asset]:
        """
        Load a specific asset by ID from an individual file.
        This is kept for backward compatibility but is not the preferred method.

        Args:
            asset_id: ID of the asset to load

        Returns:
            The asset if loaded successfully, None otherwise
        """
        file_path = f"game/data/assets/{asset_id}.json"

        if not os.path.exists(file_path):
            self.logger.warning(f"Asset file not found: {file_path}")
            return None

        try:
            with open(file_path, "r") as file:
                asset_data = json.load(file)
                asset = self._create_asset(asset_data)

                if asset:
                    self.assets[asset_id] = asset

                    # Index by primary trait
                    trait = asset.get_primary_trait()
                    if trait not in self.assets_by_trait:
                        self.assets_by_trait[trait] = []
                    self.assets_by_trait[trait].append(asset)

                    self.logger.info(f"Loaded asset: {asset_id}")
                    return asset

        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON in {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading asset from {file_path}: {str(e)}")

        return None

    def _create_asset(self, data: Dict[str, Any]) -> Optional[Asset]:
        """
        Create an asset from JSON data.

        Args:
            data: Asset data from JSON

        Returns:
            The created asset if successful, None otherwise
        """
        try:
            # Create the asset using the from_dict class method
            return Asset.from_dict(data)
        except Exception as e:
            self.logger.error(f"Error creating asset {data.get('id')}: {str(e)}")
            return None

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """
        Get an asset by ID.

        Args:
            asset_id: ID of the asset to get

        Returns:
            The asset if found, None otherwise
        """
        return self.assets.get(asset_id)

    def get_assets_by_trait(self, trait: AssetTrait) -> List[Asset]:
        """
        Get all assets with a specific primary trait.

        Args:
            trait: Primary trait to filter by

        Returns:
            List of assets with the specified trait
        """
        return self.assets_by_trait.get(trait, [])
