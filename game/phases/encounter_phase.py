"""Encounter phase implementation"""

from game.entities.location import Location
from game.phases.base_phase import GamePhase
from game.enums import GamePhase as GamePhaseEnum, EncounterType
from game.systems.player_manager import PlayerManager
from game.entities.player import Player


class EncounterPhase(GamePhase):
    """Handles the Encounter phase of the game."""

    def execute(self):
        # Get player manager directly
        player_manager: PlayerManager = self.state.player_manager

        # Get current player and investigator
        current_player = player_manager.get_current_player()
        if not current_player or not current_player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            self.state.current_phase = GamePhaseEnum.MYTHOS
            return

        # If we have multiple players, show the player turn transition
        if len(self.state.players) > 1:
            investigator_name = current_player.investigator.name
            self.ui.show_message(f"{investigator_name}'s Encounter Phase")

        # If there are monsters at the location, they must be encountered
        current_investigator = current_player.investigator
        location_name = current_investigator.current_location
        location: Location = self.state.locations[location_name]
        if location.monsters:
            self.resolve_monster_encounters()

            # check if monsters remain
            if not location.monsters:
                if self.ui.ask_yes_no(
                    "All monsters defeated. Would you like to encounter the space this turn?"
                ):
                    self.choose_encounter()
        else:
            self.choose_encounter()

        # If we have multiple players, advance to the next player
        if len(self.state.players) > 1:
            # If this is the last player, advance to Mythos phase
            next_player = self.state.advance_to_next_player()
            if next_player == player_manager.get_lead_investigator():
                self.state.current_phase = GamePhaseEnum.MYTHOS
            else:
                # Stay in Encounter phase for the next player
                pass
        else:
            # Single player, advance to Mythos phase
            self.state.current_phase = GamePhaseEnum.MYTHOS

    def resolve_monster_encounters(self):
        """Resolve encounters with monsters at the current location."""
        self.ui.show_message("Encountering monsters not implemented yet....")

    def get_available_encounter_decks(self):
        """Determine which encounter decks are available at the current location"""
        # Get current player and investigator
        player_manager: PlayerManager = self.state.player_manager
        current_player = player_manager.get_current_player()

        if not current_player or not current_player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return []

        current_investigator = current_player.investigator
        location_name = current_investigator.current_location
        location = self.state.locations[location_name]
        available_decks = []

        # General deck is always available
        available_decks.append(
            ("General", "General encounters that can occur anywhere")
        )

        # Continent-specific deck based on location
        continent_deck = location.has_continent_encounter_deck()
        if continent_deck:
            available_decks.append(
                (continent_deck, f"Encounters specific to {continent_deck}")
            )

        # Special encounter types based on location properties
        if location.has_clue:
            available_decks.append(
                ("Research", "Academic and investigative encounters")
            )

        if location.has_gate:
            available_decks.append(
                ("Other World", "Encounters with strange dimensions beyond our own")
            )

        if location.has_expedition:
            available_decks.append(
                ("Expedition", "Encounters during an active expedition")
            )

        if location.has_rumor:
            available_decks.append(
                (
                    f"Rumor: {location.rumor_name}",
                    f"Resolve the {location.rumor_name} rumor",
                )
            )

        # Check for defeated investigators at this location
        defeated_investigators = [
            inv
            for inv in self.state.defeated_investigators
            if inv.current_location == current_investigator.current_location
        ]
        for inv in defeated_investigators:
            available_decks.append(
                (
                    f"Investigator: {inv.name}",
                    f"Help the defeated investigator {inv.name}",
                )
            )

        return available_decks

    def choose_encounter(self):
        """Let the player choose which encounter deck to draw from"""
        # Get current player and investigator
        player_manager: PlayerManager = self.state.player_manager
        current_player = player_manager.get_current_player()

        if not current_player or not current_player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        current_investigator = current_player.investigator
        available_decks = self.get_available_encounter_decks()
        if not available_decks:
            self.ui.show_message("No encounter decks available.")
            return

        selected_deck = self.ui.show_choose_encounter(
            available_decks, current_investigator.current_location
        )

        # Handle the selected encounter deck
        if selected_deck.startswith("General"):
            self.resolve_general_encounter()
        elif selected_deck in ["America", "Europe", "Asia/Australia"]:
            self.resolve_continent_encounter(selected_deck)
        elif selected_deck == "Research":
            self.resolve_research_encounter()
        elif selected_deck == "Other World":
            self.resolve_other_world_encounter()
        elif selected_deck == "Expedition":
            self.resolve_expedition_encounter()
        elif selected_deck.startswith("Rumor:"):
            rumor_name = selected_deck.split(":", 1)[1].strip()
            self.resolve_rumor_encounter(rumor_name)
        elif selected_deck.startswith("Investigator:"):
            investigator_name = selected_deck.split(":", 1)[1].strip()
            self.resolve_defeated_investigator_encounter(investigator_name)
        else:
            # Fallback to general encounter
            self.resolve_general_encounter()

    def resolve_general_encounter(self):
        """Resolve an encounter from the general encounter deck"""
        # Get current player and investigator
        player_manager: PlayerManager = self.state.player_manager
        current_player = player_manager.get_current_player()

        if not current_player or not current_player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        current_investigator = current_player.investigator
        self.ui.show_message("Drawing from the General encounter deck...")

        # Get the current location type to filter encounters
        location_name = current_investigator.current_location
        location = self.state.locations[location_name]
        location_type_str = location.location_type.name.lower()

        # Draw from the encounter deck
        encounter = self.state.draw_encounter(
            EncounterType.GENERAL.value, location_type_str
        )

        if not encounter:
            self.ui.show_message("Error! No encounters found.")
            return

        # Use the resolve_encounter helper method
        self.resolve_encounter(encounter, current_investigator)

        # After resolving, discard the encounter
        general_deck = self.state.encounter_decks.get(EncounterType.GENERAL.value)
        if general_deck:
            general_deck.discard(encounter)

        self.ui.show_message("General encounter resolved.")

    def resolve_continent_encounter(self, continent):
        """Resolve an encounter from a continent-specific deck"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message(f"Drawing from the {continent} encounter deck...")

        # Convert continent name to encounter type
        continent_type = continent.lower()  # Convert "America" to "america", etc.

        # Draw from the encounter deck
        encounter = self.state.draw_encounter(continent_type)

        if not encounter:
            self.ui.show_message(f"Error! No {continent} encounters found.")
            return

        # Use the resolve_encounter helper method
        self.resolve_encounter(encounter, current_investigator)

        # After resolving, discard the encounter
        continent_deck = self.state.encounter_decks.get(continent_type)
        if continent_deck:
            continent_deck.discard(encounter)

        self.ui.show_message(f"{continent} encounter resolved.")

    def resolve_research_encounter(self):
        """Resolve a research encounter"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message("Drawing from the Research encounter deck...")

        # Draw from the research encounter deck
        encounter = self.state.draw_encounter(EncounterType.RESEARCH.value)

        if not encounter:
            self.ui.show_message("Error! No research encounters found.")
            return

        # Use the resolve_encounter helper method
        self.resolve_encounter(encounter, current_investigator)

        # After resolving, discard the encounter
        research_deck = self.state.encounter_decks.get(EncounterType.RESEARCH.value)
        if research_deck:
            research_deck.discard(encounter)

        self.ui.show_message("Research encounter resolved.")

    def resolve_other_world_encounter(self):
        """Resolve an Other World encounter"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message("Drawing from the Other World encounter deck...")

        # Draw from the other world encounter deck
        encounter = self.state.draw_encounter(EncounterType.OTHER_WORLD.value)

        if not encounter:
            self.ui.show_message("Error! No Other World encounters found.")
            return

        # Use the resolve_encounter helper method
        self.resolve_encounter(encounter, current_investigator)

        # After resolving, discard the encounter
        other_world_deck = self.state.encounter_decks.get(
            EncounterType.OTHER_WORLD.value
        )
        if other_world_deck:
            other_world_deck.discard(encounter)

        self.ui.show_message("Other World encounter resolved.")

    def resolve_expedition_encounter(self):
        """Resolve an expedition encounter"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message("Drawing from the Expedition encounter deck...")

        # Draw from the expedition encounter deck
        encounter = self.state.draw_encounter(EncounterType.EXPEDITION.value)

        if not encounter:
            self.ui.show_message("Error! No expedition encounters found.")
            return

        # Use the resolve_encounter helper method
        self.resolve_encounter(encounter, current_investigator)

        # After resolving, discard the encounter
        expedition_deck = self.state.encounter_decks.get(EncounterType.EXPEDITION.value)
        if expedition_deck:
            expedition_deck.discard(encounter)

        self.ui.show_message("Expedition encounter resolved.")

    def resolve_rumor_encounter(self, rumor_name):
        """Resolve a rumor-specific encounter"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message(f"Resolving the {rumor_name} rumor encounter...")
        # Placeholder for actual encounter resolution
        self.ui.show_message(f"Rumor encounter for {rumor_name} resolved.")

    def resolve_defeated_investigator_encounter(self, investigator_name):
        """Resolve an encounter with a defeated investigator"""
        # Get current investigator
        current_investigator = self.state.get_current_investigator()
        if not current_investigator:
            self.ui.show_message("Error: No current investigator found!")
            return

        self.ui.show_message(
            f"Resolving encounter with defeated investigator {investigator_name}..."
        )
        # Placeholder for actual encounter resolution
        self.ui.show_message(f"Encounter with {investigator_name} resolved.")

    def resolve_encounter(self, encounter, investigator):
        """Process all components of an encounter"""
        # Process all components
        results = []
        for component in encounter.components:
            result = component.process(self.state, investigator)
            results.append(result)

            # Handle UI updates based on component results
            self.handle_component_ui(result, investigator)

            # Check if we need to abort processing further components
            if isinstance(result, dict) and result.get("abort", False):
                break

        return results

    def handle_component_ui(self, result, investigator):
        """Update UI based on component results"""
        if not isinstance(result, dict):
            return

        if result.get("type") == "skill_test":
            # Display all messages from the skill test
            for message in result.get("messages", []):
                self.ui.show_message(message)

        elif result.get("type") == "change_health":
            # Display health change message
            if result.get("healed"):
                self.ui.show_message(
                    f"{investigator.name} gained {result['amount']} Health."
                )
            elif result.get("damaged"):
                self.ui.show_message(
                    f"{investigator.name} lost {abs(result['amount'])} Health."
                )

        elif result.get("type") == "narrative":
            # Display narrative text
            self.ui.show_message(result.get("text", ""))

        elif result.get("type") == "asset_gain":
            # Display asset gain message
            count = result.get("count", 1)
            asset_type = result.get("asset_type", "asset")
            self.ui.show_message(f"{investigator.name} gained {count} {asset_type}.")

        elif result.get("type") == "condition_gain":
            # Display condition gain message
            self.ui.show_message(
                f"{investigator.name} gained the {result.get('condition', 'condition')} condition."
            )
