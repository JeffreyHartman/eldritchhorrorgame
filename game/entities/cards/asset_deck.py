from typing import List, Optional
from game.entities.base.deck import Deck
from game.entities.cards.asset import Asset


class AssetDeck(Deck):
    """
    Represents a deck of asset cards.
    Extends the base Deck class with asset-specific functionality.
    """

    def __init__(self, assets: List[Asset] = None, name: str = "Asset Deck"):
        super().__init__(assets, name)
        self.reserve: List[Asset] = []
        self.reserve_size = 4  # Default reserve size

    def setup_reserve(self, size: int = 4) -> None:
        """
        Set up the reserve of face-up assets.
        
        Args:
            size: Number of assets in the reserve
        """
        self.reserve_size = size
        self.refill_reserve()

    def refill_reserve(self) -> None:
        """Refill the reserve to its full size."""
        while len(self.reserve) < self.reserve_size and (self.cards or self.discard_pile):
            drawn = self.draw()
            if drawn:
                self.reserve.append(drawn)

    def draw_specific(self, asset_id: str) -> Optional[Asset]:
        """
        Draw a specific asset from the deck by ID.
        
        Args:
            asset_id: ID of the asset to draw
            
        Returns:
            The asset if found, None otherwise
        """
        # Check in the main deck
        for i, asset in enumerate(self.cards):
            if asset.id == asset_id:
                return self.cards.pop(i)
                
        # Check in the discard pile
        for i, asset in enumerate(self.discard_pile):
            if asset.id == asset_id:
                asset = self.discard_pile.pop(i)
                return asset
                
        return None

    def take_from_reserve(self, index: int) -> Optional[Asset]:
        """
        Take an asset from the reserve.
        
        Args:
            index: Index of the asset in the reserve
            
        Returns:
            The asset if the index is valid, None otherwise
        """
        if 0 <= index < len(self.reserve):
            asset = self.reserve.pop(index)
            self.refill_reserve()
            return asset
        return None

    def get_reserve(self) -> List[Asset]:
        """Get the current reserve of face-up assets."""
        return self.reserve.copy()
