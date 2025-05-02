import json
import os
import logging
import random
from typing import Dict, List, Optional, Any

from game.entities.cards.condition import Condition
from game.entities.base.card import Expansion
from game.entities.base.component import CardComponent


class ConditionFactory:
    """
    Factory class for creating conditions from JSON data.
    This factory is responsible for:
    1. Loading condition definitions from JSON files
    2. Creating condition objects with appropriate components
    3. Providing conditions by ID or trait
    """

    def __init__(self):
        self.conditions: Dict[str, Condition] = {}  # Dict of condition_id -> Condition
        self.conditions_by_trait: Dict[str, List[Condition]] = {}  # Dict of trait -> list of conditions
        self.logger = logging.getLogger(__name__)

    def load_all_conditions(self) -> None:
        """Load all conditions from the data directory."""
        conditions_file = "game/data/conditions.json"
        
        if os.path.exists(conditions_file):
            self.load_conditions_from_file(conditions_file)
        else:
            self.logger.warning(f"Conditions file not found: {conditions_file}")

    def load_conditions_from_file(self, file_path: str) -> None:
        """
        Load multiple conditions from a single JSON file.

        Args:
            file_path: Path to the JSON file containing conditions
        """
        try:
            with open(file_path, "r") as file:
                conditions_data = json.load(file)

                # Process each condition
                for condition_data in conditions_data:
                    self._process_condition_data(condition_data)

                self.logger.info(f"Loaded conditions from: {file_path}")
        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON in {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading conditions from {file_path}: {str(e)}")

    def _process_condition_data(self, condition_data: Dict[str, Any]) -> None:
        """
        Process a single condition's data and add it to the factory.

        Args:
            condition_data: Data for a single condition
        """
        try:
            condition = self._create_condition(condition_data)
            if condition:
                condition_id = condition.id

                # Skip if we already have this condition
                if condition_id in self.conditions:
                    return

                self.conditions[condition_id] = condition

                # Index by traits
                for trait in condition.traits:
                    if trait not in self.conditions_by_trait:
                        self.conditions_by_trait[trait] = []
                    self.conditions_by_trait[trait].append(condition)

                self.logger.debug(f"Loaded condition: {condition_id}")
        except Exception as e:
            self.logger.error(f"Error processing condition {condition_data.get('id')}: {str(e)}")

    def _create_condition(self, data: Dict[str, Any]) -> Optional[Condition]:
        """
        Create a condition from JSON data.

        Args:
            data: Condition data from JSON

        Returns:
            The created condition if successful, None otherwise
        """
        try:
            condition_id = data.get("id")
            if not condition_id:
                self.logger.error("Condition missing required 'id' field")
                return None

            # Get basic condition properties
            traits = data.get("traits", [])
            expansion_str = data.get("expansion", "CORE")
            
            # Convert expansion string to enum
            try:
                expansion = Expansion[expansion_str]
            except KeyError:
                self.logger.warning(f"Unknown expansion '{expansion_str}', defaulting to CORE")
                expansion = Expansion.CORE
            
            # Get condition flags
            effect = data.get("effect", "false").lower() == "true"
            action = data.get("action", "false").lower() == "true"
            reckoning = data.get("reckoning", "false").lower() == "true"
            variants = data.get("variants", 1)
            
            # Get front and back data
            front = data.get("front", {})
            backs = data.get("backs", [])
            
            # Create the condition
            condition = Condition(
                condition_id=condition_id,
                traits=traits,
                expansion=expansion,
                front=front,
                backs=backs,
                effect=effect,
                action=action,
                reckoning=reckoning,
                variants=variants
            )
            
            # TODO: Process components for front and back sides
            # This would involve creating the appropriate CardComponent objects
            # and adding them to the condition sides
            
            return condition
        except Exception as e:
            self.logger.error(f"Error creating condition {data.get('id')}: {str(e)}")
            return None

    def get_condition(self, condition_id: str) -> Optional[Condition]:
        """
        Get a condition by ID.

        Args:
            condition_id: ID of the condition to get

        Returns:
            The condition if found, None otherwise
        """
        return self.conditions.get(condition_id)

    def get_conditions_by_trait(self, trait: str) -> List[Condition]:
        """
        Get all conditions with a specific trait.

        Args:
            trait: Trait to filter by (e.g., "madness")

        Returns:
            List of conditions with the specified trait
        """
        return self.conditions_by_trait.get(trait, [])
    
    def get_random_condition(self) -> Optional[Condition]:
        """
        Get a random condition from all available conditions.
        
        Returns:
            A random condition, or None if no conditions are available
        """
        if not self.conditions:
            return None
        
        return random.choice(list(self.conditions.values()))
    
    def get_random_condition_by_trait(self, trait: str) -> Optional[Condition]:
        """
        Get a random condition with the specified trait.
        
        Args:
            trait: Trait to filter by (e.g., "madness")
            
        Returns:
            A random condition with the specified trait, or None if none are available
        """
        conditions = self.get_conditions_by_trait(trait)
        if not conditions:
            return None
        
        return random.choice(conditions)
