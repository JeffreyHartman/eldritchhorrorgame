import pytest
from game.entities.components.change_health import ChangeHealthComponent
from game.entities.investigator import Investigator

class TestChangeHealthComponent:
    @pytest.fixture
    def investigator(self):
        return Investigator(
            name="Test Investigator",
            health=5,
            max_health=7,
            sanity=4,
            max_sanity=6,
            skills={"observation": 3}
        )
    
    def test_process_heal(self, investigator):
        # Test healing component
        component = ChangeHealthComponent(2)
        result = component.process({}, investigator)
        
        assert result["type"] == "change_health"
        assert result["amount"] == 2
        assert result["healed"] is True
        assert result["final_health"] == 7
        assert result["is_zero"] is False
        assert investigator.health == 7
    
    def test_process_damage(self, investigator):
        # Test damage component
        component = ChangeHealthComponent(-3)
        result = component.process({}, investigator)
        
        assert result["type"] == "change_health"
        assert result["amount"] == -3
        assert result["damaged"] is True
        assert result["final_health"] == 2
        assert result["is_zero"] is False
        assert investigator.health == 2
    
    def test_process_fatal_damage(self, investigator):
        # Test fatal damage component
        component = ChangeHealthComponent(-6)
        result = component.process({}, investigator)
        
        assert result["type"] == "change_health"
        assert result["amount"] == -6
        assert result["damaged"] is True
        assert result["final_health"] == 0
        assert result["is_zero"] is True
        assert investigator.health == 0