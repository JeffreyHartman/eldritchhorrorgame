import sys
import os
import pytest
from typing import Dict, List

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.game_state import GameState
from game.entities.cards.asset import Asset
from game.entities.cards.asset_deck import AssetDeck
from game.factories.asset_factory import AssetFactory
from game.enums import AssetTrait, AssetSecondaryTrait
from game.entities.base.card import Expansion


@pytest.fixture
def asset_factory():
    """Create an asset factory for testing."""
    factory = AssetFactory()
    factory.load_all_assets()
    return factory


@pytest.fixture
def asset_deck(asset_factory):
    """Create an asset deck for testing."""
    all_assets = list(asset_factory.assets.values())
    deck = AssetDeck(all_assets)
    deck.shuffle()
    return deck


@pytest.fixture
def game_state():
    """Create a game state for testing."""
    state = GameState()
    state._setup_asset_deck()
    return state


class TestAssetFactory:
    """Tests for the AssetFactory class."""

    def test_load_all_assets(self, asset_factory):
        """Test loading all assets."""
        # Verify that assets were loaded
        assert len(asset_factory.assets) > 0

        # Verify that assets are indexed by trait
        for trait in AssetTrait:
            assets = asset_factory.get_assets_by_trait(trait)
            if trait in [AssetTrait.ITEM, AssetTrait.TRINKET, AssetTrait.ALLY]:
                assert len(assets) > 0

    def test_get_asset(self, asset_factory):
        """Test getting a specific asset."""
        # Get an asset that should exist
        derringer = asset_factory.get_asset("derringer")
        assert derringer is not None
        assert derringer.id == "derringer"
        assert derringer.name == ".18 Derringer"
        assert derringer.primary_trait == AssetTrait.TRINKET
        assert AssetSecondaryTrait.WEAPON in derringer.secondary_traits

        # Get an asset that shouldn't exist
        nonexistent = asset_factory.get_asset("nonexistent")
        assert nonexistent is None

    def test_get_assets_by_trait(self, asset_factory):
        """Test getting assets by trait."""
        # Get assets by trait
        item_assets = asset_factory.get_assets_by_trait(AssetTrait.ITEM)
        assert len(item_assets) > 0
        for asset in item_assets:
            assert asset.primary_trait == AssetTrait.ITEM


class TestAsset:
    """Tests for the Asset class."""

    def test_asset_creation(self):
        """Test creating an asset."""
        # Create a simple asset
        asset = Asset(
            asset_id="test_asset",
            name="Test Asset",
            cost=2,
            primary_trait=AssetTrait.ITEM,
            secondary_traits=[AssetSecondaryTrait.MAGICAL],
            effects={
                "passive": {"type": "skill_bonus", "skill": "lore", "bonus": 1},
                "action": None,
                "discard": None
            },
            skill_bonus={"lore": 1},
            expansion=Expansion.CORE
        )

        # Verify asset properties
        assert asset.id == "test_asset"
        assert asset.name == "Test Asset"
        assert asset.cost == 2
        assert asset.primary_trait == AssetTrait.ITEM
        assert len(asset.secondary_traits) == 1
        assert AssetSecondaryTrait.MAGICAL in asset.secondary_traits
        assert asset.has_passive_effect
        assert not asset.has_action_effect
        assert not asset.has_discard_effect
        assert asset.get_skill_bonus("lore") == 1
        assert asset.get_skill_bonus("strength") == 0

    def test_asset_serialization(self):
        """Test serializing and deserializing an asset."""
        # Create an asset
        original = Asset(
            asset_id="test_asset",
            name="Test Asset",
            cost=2,
            primary_trait=AssetTrait.ITEM,
            secondary_traits=[AssetSecondaryTrait.MAGICAL],
            effects={
                "passive": {"type": "skill_bonus", "skill": "lore", "bonus": 1},
                "action": None,
                "discard": None
            },
            skill_bonus={"lore": 1},
            expansion=Expansion.CORE
        )

        # Convert to dict and back
        asset_dict = original.to_dict()
        recreated = Asset.from_dict(asset_dict)

        # Verify properties match
        assert recreated.id == original.id
        assert recreated.name == original.name
        assert recreated.cost == original.cost
        assert recreated.primary_trait == original.primary_trait
        assert len(recreated.secondary_traits) == len(original.secondary_traits)
        assert recreated.has_passive_effect == original.has_passive_effect
        assert recreated.has_action_effect == original.has_action_effect
        assert recreated.has_discard_effect == original.has_discard_effect


class TestAssetDeck:
    """Tests for the AssetDeck class."""

    def test_draw_and_discard(self, asset_deck):
        """Test drawing and discarding cards."""
        # Get initial deck size
        initial_size = len(asset_deck.cards)
        assert initial_size > 0

        # Draw a card
        card = asset_deck.draw()
        assert card is not None
        assert len(asset_deck.cards) == initial_size - 1

        # Discard the card
        asset_deck.discard(card)
        assert len(asset_deck.discard_pile) == 1

        # Draw all cards to empty the deck
        while asset_deck.cards:
            card = asset_deck.draw()
            assert card is not None

        # Draw again - should reshuffle discard pile
        card = asset_deck.draw()
        assert card is not None
        assert len(asset_deck.discard_pile) == 0

    def test_reserve(self, asset_deck):
        """Test the reserve functionality."""
        # Set up reserve
        asset_deck.setup_reserve(3)
        assert len(asset_deck.reserve) == 3

        # Take from reserve
        card = asset_deck.take_from_reserve(0)
        assert card is not None
        assert len(asset_deck.reserve) == 3  # Should refill

        # Invalid index
        card = asset_deck.take_from_reserve(10)
        assert card is None


class TestGameStateAssetIntegration:
    """Tests for asset integration with GameState."""

    def test_game_state_asset_setup(self, game_state):
        """Test that the game state sets up assets correctly."""
        assert game_state.asset_factory is not None
        assert len(game_state.asset_factory.assets) > 0

        assert game_state.asset_deck is not None
        assert len(game_state.asset_deck.cards) > 0
        assert len(game_state.asset_deck.reserve) == 4
