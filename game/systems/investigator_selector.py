from typing import List, Dict, Any, Optional, Set
import logging

from game.factories.investigator_factory import InvestigatorFactory


class InvestigatorSelector:
    """
    Handles the logic for selecting investigators.
    """
    
    def __init__(self, investigator_factory: InvestigatorFactory):
        self.investigator_factory = investigator_factory
        self.selected_investigators: Set[int] = set()
        self.logger = logging.getLogger(__name__)
        
    def get_available_investigators(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all available investigators that haven't been selected yet.
        
        Returns:
            Dict of investigator_id -> investigator data for available investigators
        """
        all_investigators = self.investigator_factory.get_all_investigator_data()
        return {
            investigator_id: investigator_data
            for investigator_id, investigator_data in all_investigators.items()
            if investigator_id not in self.selected_investigators
        }
        
    def select_investigator(self, investigator_id: int) -> bool:
        """
        Select an investigator.
        
        Args:
            investigator_id: ID of the investigator to select
            
        Returns:
            True if the selection was successful, False otherwise
        """
        # Check if the investigator exists
        if investigator_id not in self.investigator_factory.get_all_investigator_data():
            self.logger.error(f"Investigator with ID {investigator_id} not found")
            return False
            
        # Check if the investigator is already selected
        if investigator_id in self.selected_investigators:
            self.logger.error(f"Investigator with ID {investigator_id} is already selected")
            return False
            
        # Select the investigator
        self.selected_investigators.add(investigator_id)
        return True
        
    def deselect_investigator(self, investigator_id: int) -> bool:
        """
        Deselect an investigator.
        
        Args:
            investigator_id: ID of the investigator to deselect
            
        Returns:
            True if the deselection was successful, False otherwise
        """
        if investigator_id not in self.selected_investigators:
            self.logger.error(f"Investigator with ID {investigator_id} is not selected")
            return False
            
        self.selected_investigators.remove(investigator_id)
        return True
        
    def reset_selections(self) -> None:
        """
        Reset all selections.
        """
        self.selected_investigators.clear()
        
    def get_selected_investigators(self) -> Set[int]:
        """
        Get the IDs of all selected investigators.
        
        Returns:
            Set of selected investigator IDs
        """
        return self.selected_investigators
        
    def get_investigator_summary(self, investigator_id: int) -> Dict[str, Any]:
        """
        Get a summary of an investigator's data.
        
        Args:
            investigator_id: ID of the investigator to get a summary for
            
        Returns:
            Dict containing a summary of the investigator's data
        """
        investigator_data = self.investigator_factory.get_investigator_data(investigator_id)
        if not investigator_data:
            return {}
            
        return {
            "id": investigator_id,
            "name": investigator_data.get("name", "Unknown"),
            "occupation": investigator_data.get("occupation", "Unknown"),
            "role": investigator_data.get("role", "Unknown"),
            "max_health": investigator_data.get("max_health", 0),
            "max_sanity": investigator_data.get("max_sanity", 0),
            "skills": investigator_data.get("skills", {}),
            "starting_location": investigator_data.get("starting_location", "London"),
        }
