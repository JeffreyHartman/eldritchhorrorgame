import pytest
from unittest.mock import MagicMock
from game.entities.components.asset_gain import AssetGainComponent
from game.enums import AssetTrait

class TestAssetGainComponent:
    @pytest.fixture
    def mock_state(self):
        state = MagicMock()
        # Setup mock asset factory and deck
        mock_asset = MagicMock(id="test_asset")

        state.asset_factory.get_asset.return_value = mock_asset

        random_asset = MagicMock(id="random_asset")
        state.asset_deck.draw.return_value = random_asset

        reserve_asset = MagicMock(id="reserve_asset")
        state.asset_deck.take_from_reserve.return_value = reserve_asset

        return state
    
    @pytest.fixture
    def mock_ui(self):
        ui = MagicMock()
        ui.show_choice.return_value = "random"  # Default choice
        return ui
    
    @pytest.fixture
    def investigator(self):
        investigator = MagicMock()
        investigator.assets = []  # Initialize assets list

        investigator.add_asset.side_effect = lambda asset: investigator.assets.append(asset)

        return investigator
    
    def test_specific_asset_gain(self, mock_state, investigator):
        # Test gaining a specific asset
        component = AssetGainComponent(
            asset_type="item",
            specific_asset_id="test_asset"
        )
        result = component.process(mock_state, investigator)

        assert result["type"] == "asset_gain"
        assert "test_asset" in result["gained_assets"]

        mock_state.asset_factory.get_asset.assert_called_once_with("test_asset")
        investigator.add_asset.assert_called_once()

        assert len(investigator.assets) == 1
        assert investigator.assets[0].id == "test_asset"
    
    def test_random_asset_gain(self, mock_state, investigator):
        # Test random asset gain
        component = AssetGainComponent(
            asset_type="item",
            count=2,
            source="random"
        )

        result = component.process(mock_state, investigator)
        
        # Verify results
        assert result["type"] == "asset_gain"
        assert result["source"] == "random"
        assert len(result["gained_assets"]) == 2

        # Verify calls to mock state
        assert mock_state.asset_deck.draw.call_count == 2
        
        # Verify side effects
        assert len(investigator.assets) == 2
        assert all(asset.id == "random_asset" for asset in investigator.assets)

    def test_reserve_asset_gain(self, mock_state, mock_ui, investigator):
        # Configure UI mock to simulate user choices
        mock_ui.show_choice.side_effect = ["reserve", "1"]  # First choose reserve, then choose first item
        
        component = AssetGainComponent(
            asset_type="item",
            count=1,
            source="choice",
            options=["reserve", "random"]
        )
        
        result = component.process(mock_state, investigator, mock_ui)
        
        # Verify correct UI interactions
        assert mock_ui.show_choice.call_count == 2

        # Verify results
        assert result["choice"] == "reserve"
        assert result["choice_type"] == "reserve"
        assert "reserve_asset" in result["gained_assets"]

        # assert mock interactions
        mock_state.asset_deck.take_from_reserve.assert_called_once()

        # Verify side effects
        assert len(investigator.assets) == 1
        assert investigator.assets[0].id == "reserve_asset"
