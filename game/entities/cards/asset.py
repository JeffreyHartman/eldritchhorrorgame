from typing import List, Dict, Any
from game.entities.base.card import Card, CardType, CardSize, Expansion
from game.enums import AssetTrait, AssetSecondaryTrait


class Asset(Card):
    """
    Represents an asset card in the game.
    Assets provide various benefits to investigators.
    """

    def __init__(
        self,
        asset_id: str,
        name: str,
        cost: int,
        primary_trait: AssetTrait,
        secondary_traits: List[AssetSecondaryTrait] = None,
        effects: Dict[str, Any] = None,
        skill_bonus: Dict[str, int] = None,
        reroll: bool = False,
        additional_dice: int = 0,
        flavor_text: str = None,
        expansion=Expansion.CORE,
    ):
        super().__init__(name, CardType.ASSET, CardSize.STANDARD, False, expansion)

        self.id = asset_id
        self.cost = cost
        self.primary_trait = primary_trait
        self.secondary_traits = secondary_traits or []
        self.effects = effects or {"passive": None, "action": None, "discard": None}
        self.skill_bonus = skill_bonus or {}
        self.reroll = reroll
        self.additional_dice = additional_dice
        self.flavor_text = flavor_text

    @property
    def has_passive_effect(self) -> bool:
        """Check if the asset has a passive effect."""
        return self.effects.get("passive") is not None

    @property
    def has_action_effect(self) -> bool:
        """Check if the asset has an action effect."""
        return self.effects.get("action") is not None

    @property
    def has_discard_effect(self) -> bool:
        """Check if the asset has a discard effect."""
        return self.effects.get("discard") is not None

    def get_primary_trait(self) -> AssetTrait:
        """Get the primary trait of the asset."""
        return self.primary_trait

    def has_secondary_trait(self, trait: AssetSecondaryTrait) -> bool:
        """Check if the asset has a specific secondary trait."""
        return trait in self.secondary_traits

    def get_skill_bonus(self, skill: str) -> int:
        """Get the bonus for a specific skill."""
        return self.skill_bonus.get(skill, 0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the asset to a dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "cost": self.cost,
            "primary_trait": self.primary_trait.value,
            "secondary_traits": [trait.value for trait in self.secondary_traits],
            "effects": self.effects,
            "expansion": self.expansion.name,
            "skill_bonus": self.skill_bonus,
            "reroll": self.reroll,
            "additional_dice": self.additional_dice,
            "flavor_text": self.flavor_text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Asset':
        """Create an asset from a dictionary representation."""
        # Convert string traits to enum values
        primary_trait = AssetTrait(data.get("primary_trait"))
        secondary_traits = [
            AssetSecondaryTrait(trait) for trait in data.get("secondary_traits", [])
        ]

        # Handle expansion
        expansion_str = data.get("expansion", "CORE")
        try:
            expansion = Expansion[expansion_str]
        except (KeyError, TypeError):
            expansion = Expansion.CORE

        # Create the asset
        return cls(
            asset_id=data.get("id"),
            name=data.get("name"),
            cost=data.get("cost"),
            primary_trait=primary_trait,
            secondary_traits=secondary_traits,
            effects=data.get("effects"),
            skill_bonus=data.get("skill_bonus"),
            reroll=data.get("reroll", False),
            additional_dice=data.get("additional_dice", 0),
            flavor_text=data.get("flavor_text"),
            expansion=expansion,
        )