from typing import Dict, List, Optional, Any
from game.entities.base.card import Card, CardType
from game.entities.base.component import CardComponent
from game.enums import Expansion


class ConditionSide:
    """Represents one side of a condition card."""

    def __init__(
        self, title: str, text: str, components: Optional[List[CardComponent]] = None
    ):
        """Initialize a condition side.

        Args:
            title: The title of this side of the condition
            text: The descriptive text for this side
            components: Optional list of components that can be triggered
        """
        self.title = title
        self.text = text
        self.components = components or []

    def add_component(self, component: CardComponent):
        """Add a component to this side of the condition."""
        self.components.append(component)

    def process_components(self, state, investigator, **kwargs):
        """Process all components on this side of the condition.

        Args:
            state: The current game state
            investigator: The investigator this condition affects
            **kwargs: Additional arguments to pass to components

        Returns:
            List of results from processing each component
        """
        results = []
        for component in self.components:
            result = component.process(state, investigator, **kwargs)
            results.append(result)
        return results


class Condition(Card):
    """Represents a condition card with front and back sides."""

    def __init__(
        self,
        condition_id: str,
        traits: List[str],
        expansion: Expansion,
        front: Dict[str, Any],
        backs: List[Dict[str, Any]],
        effect: bool = False,
        action: bool = False,
        reckoning: bool = False,
        variants: int = 1,
    ):
        """Initialize a condition card.

        Args:
            condition_id: Unique identifier for this condition
            traits: List of traits this condition has (e.g., "madness")
            expansion: The expansion this condition is from
            front: Data for the front side of the condition
            backs: List of data for possible back sides (variants)
            effect: Whether this condition has a passive effect
            action: Whether this condition has an action
            reckoning: Whether this condition has a reckoning effect
            variants: Number of variant backs this condition has
        """
        super().__init__(
            name=front.get("title", "Unknown Condition"),
            type=CardType.CONDITION,
            size=None,  # Use default size
            double_sided=True,
            expansion=expansion,
        )

        self.id = condition_id
        self.traits = traits
        self.has_effect = effect
        self.has_action = action
        self.has_reckoning = reckoning
        self.variant_count = variants

        # Create front side
        self.front = ConditionSide(
            title=front.get("title", "Unknown Condition"), text=front.get("text", "")
        )

        # Create back variants
        self.backs = []
        for back_data in backs:
            back = ConditionSide(
                title=back_data.get("title", "Unknown Effect"),
                text=back_data.get("text", ""),
            )
            self.backs.append(back)

        # Track which side is currently active (0 = front, 1+ = back variant index)
        self.active_side = 0

        # Track which back variant is selected (if any)
        self.selected_variant: Optional[int] = None

    @property
    def active_side_obj(self) -> ConditionSide:
        """Get the currently active side of the condition."""
        if self.active_side == 0:
            return self.front
        else:
            variant_idx = self.selected_variant or 0
            if variant_idx < len(self.backs):
                return self.backs[variant_idx]
            return self.front  # Fallback to front if variant is invalid

    def flip(self, variant_index: Optional[int] = None):
        """Flip the condition to its other side.

        Args:
            variant_index: Optional index of the back variant to use.
                           If not provided and no variant is already selected,
                           the condition will not be flipped.

        Returns:
            The active side object after flipping
        """
        if self.active_side == 0:
            # Going from front to back
            if variant_index is not None:
                # Use the provided variant index
                self.select_variant(variant_index)

            # Only flip if we have a selected variant
            if self.selected_variant is not None:
                self.active_side = 1
        else:
            # Going from back to front
            self.active_side = 0

        return self.active_side_obj

    def select_variant(self, variant_index: int):
        """Select a specific back variant.

        Args:
            variant_index: Index of the back variant to select

        Returns:
            The selected variant or None if invalid
        """
        if 0 <= variant_index < len(self.backs):
            self.selected_variant = variant_index
            return self.backs[variant_index]
        return None

    def process(self, state, investigator, **kwargs):
        """Process the active side of this condition.

        Args:
            state: The current game state
            investigator: The investigator this condition affects
            **kwargs: Additional arguments to pass to components

        Returns:
            Results from processing the active side's components
        """
        return self.active_side_obj.process_components(state, investigator, **kwargs)
