from enum import Enum
from typing import List, Optional


class LocationType(Enum):
    CITY = "city"
    WILDERNESS = "wilderness"
    SEA = "sea"
    NONE = "none"


class Location:
    def __init__(
        self,
        name: str,
        description: str,
        connections: List[str],
        has_gate: bool = False,
        clues: int = 0,
        monsters: List[str] = [],
        location_type: LocationType = LocationType.CITY,
        train_paths: List[str] = None,
        ship_paths: List[str] = None,
        real_world_location: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.connections = connections
        self.has_gate = has_gate
        self.clues = clues
        self.monsters = monsters
        self.location_type = location_type
        self.train_paths = train_paths or []
        self.ship_paths = ship_paths or []
        self.real_world_location = real_world_location

    def has_train_connection(self):
        return len(self.train_paths) > 0

    def has_ship_connection(self):
        return len(self.ship_paths) > 0

    def add_clue(self):
        self.clues += 1

    def remove_clue(self, amount=1):
        if self.clues >= amount:
            self.clues -= amount
            return True
        return False

    def open_gate(self):
        self.has_gate = True

    def close_gate(self):
        if self.has_gate:
            self.has_gate = False
            return True
        return False

