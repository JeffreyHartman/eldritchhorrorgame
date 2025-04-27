import json
from game.components.location import Location
from game.components.investigator import Investigator


class GameState:
    """
    Core game state manager, tracks all game variables
    """

    def __init__(self):
        self.doom_track = 0
        self.max_doom = 15
        self.mysteries_solved = 0
        self.current_phase = "Action"

        self.locations = {}
        self.investigator = {}

    def reset_game(self):
        self.doom_track = 0
        self.mysteries_solved = 0
        self.current_phase = "Action"

        self.load_locations()
        # TODO: test investigator, replace with character selection
        self.investigator = Investigator(
            name="Anna Blackwood",
            health=4,
            max_health=5,
            sanity=5,
            max_sanity=5,
            skills={
                "lore": 2,
                "influence": 3,
                "observation": 2,
                "strength": 1,
                "will": 3,
            },
            items=[],
            clue_tokens=2,
            tickets=0,
            is_delayed=False,
            actions=2,
            current_location="London",
        )

    def load_locations(self):
        """Load location data from JSON file."""
        with open("game/data/locations.json", "r") as file:
            location_data = json.load(file)

        self.locations = {}
        for name, data in location_data.items():
            self.locations[name] = Location(
                name,
                data["description"],
                data["connections"],
                data["has_gate"],
                data["clues"],
            )

    def reset_action_phase(self):
        self.current_phase = "Action"
        self.investigator.actions = 2

    def use_action(self):
        """Use an action, return True if actions remaining, False if no actions left"""
        if self.investigator.actions > 0:
            self.investigator.actions -= 1
            return True
        return False

    def has_actions_left(self):
        return self.investigator.actions > 0
