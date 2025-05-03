from typing import List, Optional, Dict, Any
import logging

from game.entities.player import Player
from game.entities.investigator import Investigator
from game.factories.investigator_factory import InvestigatorFactory


class PlayerManager:
    """
    Manages players, turn order, and the lead investigator.
    """
    
    def __init__(self, investigator_factory: InvestigatorFactory):
        self.players: List[Player] = []
        self.current_player_index: int = 0
        self.lead_investigator_index: int = 0
        self.investigator_factory = investigator_factory
        self.logger = logging.getLogger(__name__)
        
    def add_player(self, player_id: int, name: str, investigator_id: int) -> Optional[Player]:
        """
        Add a new player with the specified investigator.
        
        Args:
            player_id: Unique ID for the player
            name: Player's name
            investigator_id: ID of the investigator to assign to this player
            
        Returns:
            The created player if successful, None otherwise
        """
        # Check if player_id already exists
        if any(player.player_id == player_id for player in self.players):
            self.logger.error(f"Player with ID {player_id} already exists")
            return None
            
        # Create the investigator
        investigator = self.investigator_factory.create_investigator(investigator_id)
        if not investigator:
            self.logger.error(f"Failed to create investigator with ID {investigator_id}")
            return None
            
        # Create the player
        player = Player(
            player_id=player_id,
            name=name,
            investigator=investigator,
            is_lead_investigator=(len(self.players) == 0)  # First player is lead by default
        )
        
        # Add the player to the list
        self.players.append(player)
        
        # If this is the first player, set them as the lead investigator
        if len(self.players) == 1:
            self.lead_investigator_index = 0
            
        return player
        
    def get_current_player(self) -> Optional[Player]:
        """
        Get the current player.
        
        Returns:
            The current player, or None if there are no players
        """
        if not self.players:
            return None
            
        return self.players[self.current_player_index]
        
    def get_lead_investigator(self) -> Optional[Player]:
        """
        Get the lead investigator.
        
        Returns:
            The lead investigator, or None if there are no players
        """
        if not self.players:
            return None
            
        return self.players[self.lead_investigator_index]
        
    def advance_turn(self) -> Optional[Player]:
        """
        Advance to the next player's turn.
        
        Returns:
            The new current player, or None if there are no players
        """
        if not self.players:
            return None
            
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        return self.get_current_player()
        
    def reset_turn_order(self) -> None:
        """
        Reset the turn order to start with the lead investigator.
        """
        self.current_player_index = self.lead_investigator_index
        
    def set_lead_investigator(self, player_id: int) -> bool:
        """
        Set a player as the lead investigator.
        
        Args:
            player_id: ID of the player to set as lead investigator
            
        Returns:
            True if successful, False otherwise
        """
        for i, player in enumerate(self.players):
            if player.player_id == player_id:
                # Update the old lead investigator
                if self.lead_investigator_index < len(self.players):
                    self.players[self.lead_investigator_index].set_as_lead_investigator(False)
                
                # Set the new lead investigator
                self.lead_investigator_index = i
                player.set_as_lead_investigator(True)
                return True
                
        return False
        
    def get_player_by_id(self, player_id: int) -> Optional[Player]:
        """
        Get a player by ID.
        
        Args:
            player_id: ID of the player to get
            
        Returns:
            The player if found, None otherwise
        """
        for player in self.players:
            if player.player_id == player_id:
                return player
                
        return None
        
    def get_all_players(self) -> List[Player]:
        """
        Get all players.
        
        Returns:
            List of all players
        """
        return self.players
        
    def get_player_count(self) -> int:
        """
        Get the number of players.
        
        Returns:
            Number of players
        """
        return len(self.players)
