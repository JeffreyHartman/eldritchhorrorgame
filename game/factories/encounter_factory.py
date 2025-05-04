import json
import os
import random
import logging
from typing import Dict, List, Optional, Any

from game.entities.cards.encounter import Encounter
from game.entities.location import LocationType
from game.enums import EncounterType, EncounterSubType
from game.entities.components.component_factory import create_component


class EncounterFactory:
    """
    Factory class for creating encounters from JSON data
    This factory is responsible for:
    1. Loading encounter definitions from JSON files
    2. Creating encounter objects with the appropriate components
    3. Providing encounters based on type and subtype
    """

    def __init__(self):
        self.encounters = {}  # Dict of encounter_type -> list of encounters
        self.encounters_by_subtype = (
            {}
        )  # Dict of (encounter_type, subtype) -> list of encounters
        self.loaded_types = set()  # Track which encounter types have been loaded
        self.logger = logging.getLogger(__name__)

    def _load_encounters(self, encounter_type: str):
        """Load encounters of the specified type from JSON files"""
        file_path = f"game/data/encounters/{encounter_type}.json"

        if not os.path.exists(file_path):
            self.logger.warning("Encounter file not found: %s", file_path)
            return

        try:
            with open(file_path, "r") as file:
                encounters_data = json.load(file)

                # Initialize encounter lists if needed
                if encounter_type not in self.encounters:
                    self.encounters[encounter_type] = []

                # Process each encounter
                for encounter_data in encounters_data:
                    encounter = self._create_encounter(encounter_data)
                    if encounter:
                        self.encounters[encounter_type].append(encounter)

                        # Index by subtype if present
                        subtype = encounter_data.get("subtype")
                        if subtype:
                            key = (encounter_type, subtype)
                            if key not in self.encounters_by_subtype:
                                self.encounters_by_subtype[key] = []
                            self.encounters_by_subtype[key].append(encounter)

                # Mark this type as loaded
                self.loaded_types.add(encounter_type)

                self.logger.info(
                    "Loaded %d %s encounters", len(encounters_data), encounter_type
                )
        except json.JSONDecodeError:
            self.logger.error("Error parsing JSON in %s", file_path)
        except Exception as e:
            self.logger.error("Error loading encounters from %s: %s", file_path, str(e))

    def _create_encounter(self, data: Dict[str, Any]) -> Optional[Encounter]:
        """Create an encounter from JSON data"""
        try:
            encounter_id = data.get("id")
            if encounter_id is None:
                error_msg = f"Encounter missing required 'id' field: {data}"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            title = data.get("title", "Unnamed Encounter")
            encounter_type = data.get("encounter_type")
            subtype = data.get("subtype")

            # Determine location type for general encounters
            location_type = LocationType.NONE
            if encounter_type == EncounterType.GENERAL.value:
                if subtype == EncounterSubType.CITY.value:
                    location_type = LocationType.CITY
                elif subtype == EncounterSubType.WILDERNESS.value:
                    location_type = LocationType.WILDERNESS
                elif subtype == EncounterSubType.SEA.value:
                    location_type = LocationType.SEA

            # Create the encounter
            encounter = Encounter(encounter_id, title, location_type)

            # Add components
            components_data = data.get("components", [])
            for component_data in components_data:
                component = create_component(component_data)
                if component:
                    encounter.add_component(component)

            return encounter
        except Exception as e:
            self.logger.error(f"Error creating encounter {data.get('id')}: {str(e)}")
            return None

    def create_encounter(
        self, encounter_type: str, subtype: Optional[str] = None
    ) -> Optional[Encounter]:
        """
        Create an encounter of the specified type and subtype

        NOTE: This method is deprecated and will be removed in a future version.
        Use GameState.draw_encounter() instead, which properly handles deck management.

        Args:
            encounter_type: The type of encounter (general, research, other_world, etc.)
            subtype: Optional subtype (city, wilderness, sea, ancient_one_name, expedition_location)

        Returns:
            A random encounter of the specified type and subtype, or None if not found
        """
        # Check if we need to load this encounter type
        if encounter_type not in self.loaded_types:
            self._load_encounters(encounter_type)

        # If no encounters of this type, return None
        if encounter_type not in self.encounters or not self.encounters[encounter_type]:
            self.logger.warning("No encounters found for type: %s", encounter_type)
            return None

        # If subtype is specified and we have encounters for that subtype, return one
        if subtype:
            key = (encounter_type, subtype)
            if key in self.encounters_by_subtype and self.encounters_by_subtype[key]:
                return random.choice(self.encounters_by_subtype[key])

        # For encounter types that don't use subtypes (like other_world)
        # or if we couldn't find a matching subtype
        return random.choice(self.encounters[encounter_type])

    def get_all_encounters_by_type(self, encounter_type: str) -> List[Encounter]:
        """
        Get all encounters of a specific type.

        Args:
            encounter_type: The type of encounter (general, research, other_world, etc.)

        Returns:
            List of all encounters of the specified type
        """
        # Check if we need to load this encounter type
        if encounter_type not in self.loaded_types:
            self._load_encounters(encounter_type)

        return self.encounters.get(encounter_type, [])

    def load_all_encounter_types(self):
        """Load all encounter types"""
        encounter_types = [
            EncounterType.GENERAL.value,  # City, wilderness, sea encounters
            EncounterType.AMERICA.value,  # America continent encounters
            EncounterType.EUROPE.value,  # Europe continent encounters
            EncounterType.ASIA.value,  # Asia continent encounters
            EncounterType.RESEARCH.value,  # Research encounters (subtypes by Ancient One)
            EncounterType.OTHER_WORLD.value,  # Other world encounters (no subtypes)
            EncounterType.EXPEDITION.value,  # Expedition encounters (subtypes by location)
            EncounterType.SPECIAL.value,  # Special encounters (subtypes by Ancient One)
        ]

        for encounter_type in encounter_types:
            self._load_encounters(encounter_type)
