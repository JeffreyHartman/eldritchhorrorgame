from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
from game.entities.cards.monster import Monster


class LocationType(Enum):
    CITY = "city"
    WILDERNESS = "wilderness"
    SEA = "sea"
    NONE = "none"


@dataclass
class Location:
    # Required parameters
    name: str
    description: str
    connections: List[str]

    # Optional parameters with defaults
    location_type: LocationType = LocationType.CITY
    train_paths: List[str] = field(default_factory=list)
    ship_paths: List[str] = field(default_factory=list)
    real_world_location: Optional[str] = None
    continent: Optional[str] = None
    monsters: List = field(default_factory=list)
    has_gate: bool = False
    has_clue: bool = False
    has_expedition: bool = False
    has_rumor: bool = False
    rumor_name: Optional[str] = None

    def has_train_connection(self):
        return len(self.train_paths) > 0

    def has_ship_connection(self):
        return len(self.ship_paths) > 0

    def add_clue(self):
        self.has_clue = True

    def remove_clue(self):
        if self.has_clue:
            self.has_clue = False
            return True
        return False

    def open_gate(self):
        self.has_gate = True

    def close_gate(self):
        if self.has_gate:
            self.has_gate = False
            return True
        return False

    def has_continent_encounter_deck(self) -> Optional[str]:
        """Returns the continent encounter deck name if this location uses one, otherwise None"""
        # Major cities that use continent-specific encounter decks
        continent_deck_cities: Dict[str, Set[str]] = {
            "America": {"Arkham", "San Francisco", "Buenos Aires"},
            "Europe": {"London", "Rome", "Istanbul"},
            "Asia/Australia": {"Shanghai", "Tokyo", "Sydney"},
        }

        if not self.continent:
            return None

        for continent, cities in continent_deck_cities.items():
            if self.continent == continent and self.name in cities:
                return continent

        return None
