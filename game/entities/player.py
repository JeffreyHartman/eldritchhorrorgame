from dataclasses import dataclass
from typing import Optional

from game.entities.investigator import Investigator


@dataclass
class Player:
    """
    Represents a player in the game.
    A player is distinct from an investigator - a player controls an investigator.
    """
    
    # Required parameters
    player_id: int
    name: str
    
    # Optional parameters
    investigator: Optional[Investigator] = None
    is_lead_investigator: bool = False
    
    def set_investigator(self, investigator: Investigator) -> None:
        """
        Set the investigator for this player.
        
        Args:
            investigator: The investigator to assign to this player
        """
        self.investigator = investigator
        
    def set_as_lead_investigator(self, is_lead: bool = True) -> None:
        """
        Set this player as the lead investigator.
        
        Args:
            is_lead: Whether this player is the lead investigator
        """
        self.is_lead_investigator = is_lead
