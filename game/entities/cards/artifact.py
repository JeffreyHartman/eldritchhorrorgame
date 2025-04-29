from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from game.entities.base.card import Card, CardType, CardSize, Expansion


# TODO: untested and incomplete, probably garbage code
class ArtifactTrait(Enum):
    ITEM = 1
    TOME = 2
    MAGICAL = 3
    MAGICAL_WEAPON = 4


class ArtifactCard(Card):
    def __init__(
        self,
        name: str,
        traits: List[str],
        components: List[Dict[str, Any]] = None,
        expansion=Expansion.CORE,
    ):
        super().__init__(name, CardType.ARTIFACT, CardSize.MINI, False, expansion)

        # Convert string traits to enum values
        self.traits = [ArtifactTrait[trait] for trait in traits]

        # Initialize components
        self.components = []
        if components:
            self._build_components(components)

    def _build_components(self, component_data):
        """Build card components from data"""
        from game.entities.cards.component_registry import create_component

        for comp_data in component_data:
            component = create_component(comp_data)
            if component:
                self.components.append(component)

    def has_component_type(self, component_type):
        """Check if card has a specific component type"""
        return any(isinstance(comp, component_type) for comp in self.components)

    def get_components_by_type(self, component_type):
        """Get all components of a specific type"""
        return [comp for comp in self.components if isinstance(comp, component_type)]

    def apply_component(
        self, component_type, game_state, card_owner, target=None, **kwargs
    ):
        """Apply all components of a given type"""
        results = []
        for comp in self.get_components_by_type(component_type):
            results.append(comp.apply(game_state, card_owner, target, **kwargs))
        return results
