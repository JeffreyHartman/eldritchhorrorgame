"""Action phase implementation"""

from game.phases.base_phase import GamePhase
from game.enums import GamePhase as GamePhaseEnum, TicketType
from game.systems.player_manager import PlayerManager
from game.entities.player import Player


class ActionPhase(GamePhase):
    """Handles the Action phase of the game."""

    def execute(self):
        self.state.reset_action_phase()

        # Get player manager directly
        player_manager: PlayerManager = self.state.player_manager

        # Get current player
        current_player: Player = player_manager.get_current_player()
        if not current_player or not current_player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        # If we have multiple players, show the player turn transition
        if len(self.state.players) > 1:
            investigator_name = current_player.investigator.name
            self.ui.show_player_turn_transition(current_player.name, investigator_name)

        # Process player actions
        while current_player.investigator.actions > 0:
            choice = self.ui.show_action_phase(self.state)

            if choice == "1":
                self.travel_action(current_player)
            elif choice == "2":
                self.rest_action(current_player)
            elif choice == "3":
                self.trade_action(current_player)
            elif choice == "4":
                self.prepare_for_travel_action(current_player)
            elif choice == "5":
                self.acquire_assets_action(current_player)
            elif choice == "6":
                self.perform_component_action(current_player)
            elif choice == "7":
                self.ui.show_map(self.state)
            elif choice == "9":
                break

        # Show final location view before advancing to the next phase
        self.ui.show_action_phase(self.state)

        # If we have multiple players, advance to the next player
        if len(self.state.players) > 1:
            # If this is the last player, advance to Encounter phase
            next_player = self.state.advance_to_next_player()
            if next_player == player_manager.get_lead_investigator():
                self.state.current_phase = GamePhaseEnum.ENCOUNTER
                self.ui.show_message("Advancing to Encounter Phase...")
            else:
                # Stay in Action phase for the next player
                self.ui.show_message(f"Next player's turn: {next_player.name}")
                # Reset actions for the next player
                if next_player.investigator:
                    next_player.investigator.actions = 2
        else:
            # Single player, advance to Encounter phase
            self.state.current_phase = GamePhaseEnum.ENCOUNTER
            self.ui.show_message("Advancing to Encounter Phase...")

    def travel_action(self, player: Player, ticket_used=False):
        """Travel between locations."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        choice = self.ui.show_travel_menu(self.state)
        if choice == "0":
            return

        try:
            choice_idx = int(choice) - 1
            current_location = investigator.current_location
            connections = self.state.locations[current_location].connections

            if 0 <= choice_idx < len(connections):
                destination = connections[choice_idx]

                # If using a ticket, don't consume an action
                if ticket_used:
                    investigator.current_location = destination
                    self.ui.show_message(f"Traveling to {destination}...")
                # Otherwise, use an action
                elif investigator.actions > 0:
                    investigator.actions -= 1
                    investigator.current_location = destination
                    self.ui.show_message(f"Traveling to {destination}...")
                else:
                    self.ui.show_message("No actions remaining.")
                    return

                # Check for additional travel options with tickets
                self.offer_ticket_travel(player)
            else:
                self.ui.show_message("Invalid location choice.")
        except ValueError:
            self.ui.show_message("Invalid location choice.")

    def offer_ticket_travel(self, player: Player):
        """Offer additional travel options using tickets."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        current_location = investigator.current_location
        location = self.state.locations[current_location]

        # Check for train connections
        train_paths = location.train_paths
        if train_paths and investigator.train_tickets > 0:
            use_train = self.ui.ask_yes_no(
                f"You have {investigator.train_tickets} train tickets. "
                f"Use one to travel by train?"
            )
            if use_train:
                train_destination = self.ui.show_ticket_travel_menu(
                    self.state, TicketType.TRAIN.value, train_paths
                )
                if train_destination and train_destination != "0":
                    if investigator.use_ticket(TicketType.TRAIN.value, 1):
                        investigator.current_location = train_paths[
                            int(train_destination) - 1
                        ]
                        self.ui.show_message(
                            f"Traveling by train to {investigator.current_location}..."
                        )
                        # Recursively offer more ticket travel options
                        self.offer_ticket_travel(player)
                        return

        # Check for ship connections
        ship_paths = location.ship_paths
        if ship_paths and investigator.ship_tickets > 0:
            use_ship = self.ui.ask_yes_no(
                f"You have {investigator.ship_tickets} ship tickets. "
                f"Use one to travel by ship?"
            )
            if use_ship:
                ship_destination = self.ui.show_ticket_travel_menu(
                    self.state, TicketType.SHIP.value, ship_paths
                )
                if ship_destination and ship_destination != "0":
                    if investigator.use_ticket(TicketType.SHIP.value, 1):
                        investigator.current_location = ship_paths[
                            int(ship_destination) - 1
                        ]
                        self.ui.show_message(
                            f"Traveling by ship to {investigator.current_location}..."
                        )
                        # Recursively offer more ticket travel options
                        self.offer_ticket_travel(player)
                        return

    def rest_action(self, player: Player):
        """Rest to recover health and sanity."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        current_location = investigator.current_location
        location = self.state.locations[current_location]

        # Check if there are monsters at the current location
        if location.monsters:
            self.ui.show_message("You cannot rest while monsters are present!")
            return

        if investigator.actions > 0:
            investigator.actions -= 1
            investigator.heal(1)
            investigator.restore_sanity(1)
            self.ui.show_message("You rest and recover...")
        else:
            self.ui.show_message("Err: No actions remaining.")

    def trade_action(self, player: Player):
        """Trade items with another investigator."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        # Check if there are other players to trade with
        if len(self.state.players) <= 1:
            self.ui.show_message("There are no other investigators to trade with!")
            return

        # TODO: Implement trading between investigators
        self.ui.show_message("Trade action not implemented yet.")

    def prepare_for_travel_action(self, player: Player):
        """Prepare for travel by acquiring a ticket."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        if investigator.actions > 0:
            investigator.actions -= 1
            ticket_type = self.ui.show_ticket_choice()
            if ticket_type == TicketType.TRAIN.value:
                investigator.add_ticket(TicketType.TRAIN.value, 1)
                self.ui.show_message("You prepare for travel and gain a train ticket.")
            elif ticket_type == TicketType.SHIP.value:
                investigator.add_ticket(TicketType.SHIP.value, 1)
                self.ui.show_message("You prepare for travel and gain a ship ticket.")
            else:
                # Invalid choice, default to train ticket
                investigator.add_ticket(TicketType.TRAIN.value, 1)
                self.ui.show_message("You prepare for travel and gain a train ticket.")
        else:
            self.ui.show_message("Err: No actions remaining.")

    def acquire_assets_action(self, player: Player):
        """Acquire assets from the market."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        # TODO: Implement asset acquisition
        self.ui.show_message("Acquire assets action not implemented yet.")

    def perform_component_action(self, player: Player):
        """Perform an action from a component card."""
        if not player or not player.investigator:
            self.ui.show_message("Error: No current player or investigator found!")
            return

        investigator = player.investigator
        # TODO: Implement component actions
        self.ui.show_message("Perform component action not implemented yet.")

