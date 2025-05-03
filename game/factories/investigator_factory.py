import json
import os
import logging
import glob
from typing import Dict, List, Optional, Any

from game.entities.investigator import Investigator


class InvestigatorFactory:
    """
    Factory class for creating investigators from JSON data.
    This factory is responsible for:
    1. Loading investigator definitions from JSON files
    2. Creating investigator objects
    3. Providing investigators by ID or name
    """

    def __init__(self):
        self.investigators: Dict[int, Dict[str, Any]] = (
            {}
        )  # Dict of investigator_id -> investigator data
        self.logger = logging.getLogger(__name__)

    def load_all_investigators(self) -> None:
        """Load all investigators from the data directory."""
        investigators_dir = "game/data/investigators"

        # Get all JSON files in the investigators directory
        json_files = glob.glob(f"{investigators_dir}/*.json")

        for file_path in json_files:
            # Skip the template file
            if "template.json" in file_path:
                continue

            self.load_investigators_from_file(file_path)

    def load_investigators_from_file(self, file_path: str) -> None:
        """
        Load investigators from a JSON file.

        Args:
            file_path: Path to the JSON file containing investigators
        """
        try:
            with open(file_path, "r") as file:
                investigators_data = json.load(file)

                # Process each investigator
                for investigator_data in investigators_data:
                    self._process_investigator_data(investigator_data)

                self.logger.info(f"Loaded investigators from: {file_path}")
        except json.JSONDecodeError:
            self.logger.error(f"Error parsing JSON in {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading investigators from {file_path}: {str(e)}")

    def _process_investigator_data(self, investigator_data: Dict[str, Any]) -> None:
        """
        Process a single investigator's data and add it to the factory.

        Args:
            investigator_data: Data for a single investigator
        """
        try:
            investigator_id = investigator_data.get("id")
            if not investigator_id:
                self.logger.error("Investigator missing required 'id' field")
                return

            # Skip if we already have this investigator
            if investigator_id in self.investigators:
                return

            self.investigators[investigator_id] = investigator_data
            self.logger.debug(
                f"Loaded investigator: {investigator_id} - {investigator_data.get('name')}"
            )
        except Exception as e:
            self.logger.error(
                f"Error processing investigator {investigator_data.get('id')}: {str(e)}"
            )

    def get_investigator_data(self, investigator_id: int) -> Optional[Dict[str, Any]]:
        """
        Get investigator data by ID.

        Args:
            investigator_id: ID of the investigator to get

        Returns:
            The investigator data if found, None otherwise
        """
        return self.investigators.get(investigator_id)

    def get_all_investigator_data(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all investigator data.

        Returns:
            Dict of investigator_id -> investigator data
        """
        return self.investigators

    def create_investigator(self, investigator_id: int) -> Optional[Investigator]:
        """
        Create an investigator object from the stored data.

        Args:
            investigator_id: ID of the investigator to create

        Returns:
            The created investigator if successful, None otherwise
        """
        investigator_data = self.get_investigator_data(investigator_id)
        if not investigator_data:
            self.logger.error(f"Investigator with ID {investigator_id} not found")
            return None

        try:
            # Create the investigator using the data
            return Investigator(
                name=investigator_data["name"],
                health=investigator_data["max_health"],
                max_health=investigator_data["max_health"],
                sanity=investigator_data["max_sanity"],
                max_sanity=investigator_data["max_sanity"],
                skills=investigator_data["skills"],
                clue_tokens=investigator_data.get("starting_clues", 0),
                current_location=investigator_data.get("starting_location", "London"),
            )
        except Exception as e:
            self.logger.error(
                f"Error creating investigator {investigator_id}: {str(e)}"
            )
            return None
