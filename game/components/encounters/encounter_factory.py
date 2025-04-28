import json
import os
import random
import logging
from typing import Dict, List, Optional, Any

from game.components.encounters.encounter import Encounter
from game.components.encounters.components.narrative import NarrativeComponent
from game.components.encounters.components.skill_test import SkillTestComponent

from game.components.encounters.components.asset_gain import AssetGainComponent
from game.components.encounters.components.condition_gain import ConditionGainComponent
from game.components.location import LocationType
from game.enums import EncounterType, EncounterSubType, AssetType


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
            self.logger.warning(f"Encounter file not found: {file_path}")
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
                    f"Loaded {len(encounters_data)} {encounter_type} encounters"
                )
        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON in {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading encounters from {file_path}: {str(e)}")

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
                component = self._create_component(component_data)
                if component:
                    encounter.add_component(component)

            return encounter
        except Exception as e:
            self.logger.error(f"Error creating encounter {data.get('id')}: {str(e)}")
            return None

    def _create_component(self, data: Dict[str, Any]) -> Any:
        """Create an encounter component from JSON data"""
        component_type = data.get("type")

        if component_type == "narrative":
            return self._create_narrative_component(data)
        elif component_type == "skill_test":
            return self._create_skill_test_component(data)
        elif component_type == "asset_gain":
            return self._create_asset_gain_component(data)
        elif component_type == "condition_gain":
            return self._create_condition_gain_component(data)
        else:
            self.logger.warning(f"Unknown component type: {component_type}")
            return None

    def _create_skill_test_component(self, data: Dict[str, Any]) -> SkillTestComponent:
        """Create a skill test component from JSON data"""
        skill = data.get("skill")
        modifier = data.get("modifier", 0)
        if skill is None:
            error_msg = f"Skill test component missing required 'skill' field: {data}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # Create success components
        success_components = []
        for success_data in data.get("success_components", []):
            component = self._create_component(success_data)
            if component:
                success_components.append(component)

        # Create failure components
        failure_components = []
        for failure_data in data.get("failure_components", []):
            component = self._create_component(failure_data)
            if component:
                failure_components.append(component)

        return SkillTestComponent(
            skill, modifier, success_components, failure_components
        )

    def _create_narrative_component(self, data: Dict[str, Any]) -> NarrativeComponent:
        """Create a narrative component from JSON data"""
        text = data.get("text", "")
        return NarrativeComponent(text)

    def _create_asset_gain_component(self, data: Dict[str, Any]) -> AssetGainComponent:
        """Create an asset gain component from JSON data"""
        asset_type = data.get("asset_type")
        count = data.get("count", 1)
        source = data.get("source")
        options = data.get("options", [])

        if asset_type is None or source is None:
            error_msg = f"Asset gain component missing required field: {data}"
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        # Convert string asset type to enum if needed
        asset_type_value = asset_type
        try:
            asset_type_value = AssetType(asset_type).value
        except ValueError:
            # If not a valid enum value, keep the original string
            pass

        return AssetGainComponent(asset_type_value, count, source, options)

    def _create_condition_gain_component(
        self, data: Dict[str, Any]
    ) -> ConditionGainComponent:
        """Create a condition gain component from JSON data"""
        condition = data.get("condition")

        if condition is None:
            error_msg = (
                f"Condition gain component missing required 'condition' field: {data}"
            )
            self.logger.error(error_msg)
            raise ValueError(error_msg)

        return ConditionGainComponent(condition)

    def create_encounter(
        self, encounter_type: str, subtype: Optional[str] = None
    ) -> Optional[Encounter]:
        """
        Create an encounter of the specified type and subtype

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
            self.logger.warning(f"No encounters found for type: {encounter_type}")
            return None

        # If subtype is specified and we have encounters for that subtype, return one
        if subtype:
            key = (encounter_type, subtype)
            if key in self.encounters_by_subtype and self.encounters_by_subtype[key]:
                return random.choice(self.encounters_by_subtype[key])

        # For encounter types that don't use subtypes (like other_world)
        # or if we couldn't find a matching subtype
        return random.choice(self.encounters[encounter_type])

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
