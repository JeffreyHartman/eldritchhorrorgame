"""Action phase implementation"""

from game.phases.base_phase import GamePhase
from game.enums import GamePhase as GamePhaseEnum, TicketType


class ActionPhase(GamePhase):
    """Handles the Action phase of the game."""

    def execute(self):
        self.state.reset_action_phase()
        while self.state.has_actions_left():
            choice = self.ui.show_action_phase(self.state)

            if choice == "1":
                self.travel_action()
            elif choice == "2":
                self.rest_action()
            elif choice == "3":
                self.trade_action()
            elif choice == "4":
                self.prepare_for_travel_action()
            elif choice == "5":
                self.acquire_assets_action()
            elif choice == "6":
                self.perform_component_action()
            elif choice == "7":
                self.ui.show_map(self.state)
            elif choice == "9":
                break

        # Show final location view before advancing to the next phase
        self.ui.show_action_phase(self.state)

        self.state.current_phase = GamePhaseEnum.ENCOUNTER
        self.ui.show_message("Advancing to Encounter Phase...")

    def travel_action(self, ticket_used=False):
        """Travel between locations."""
        choice = self.ui.show_travel_menu(self.state)
        if choice == "0":
            return

        try:
            choice_idx = int(choice) - 1
            current_location = self.state.investigator.current_location
            connections = self.state.locations[current_location].connections

            if 0 <= choice_idx < len(connections):
                destination = connections[choice_idx]

                # If using a ticket, don't consume an action
                if ticket_used:
                    self.state.investigator.current_location = destination
                    self.ui.show_message(f"Traveling to {destination}...")
                # Otherwise, try to use an action
                elif self.state.use_action():
                    self.state.investigator.current_location = destination
                    self.ui.show_message(f"Traveling to {destination}...")
                else:
                    self.ui.show_message("No actions remaining.")
                    return

                # Check for additional travel options with tickets
                self.offer_ticket_travel()
            else:
                self.ui.show_message("Invalid location choice.")
        except ValueError:
            self.ui.show_message("Invalid location choice.")

    def offer_ticket_travel(self):
        """Offer additional travel options using tickets."""
        current_location = self.state.investigator.current_location
        location = self.state.locations[current_location]

        # Check for train connections
        train_paths = location.train_paths
        if train_paths and self.state.investigator.train_tickets > 0:
            use_train = self.ui.ask_yes_no(
                f"You have {self.state.investigator.train_tickets} train tickets. Use one to travel by train?"
            )
            if use_train:
                train_destination = self.ui.show_ticket_travel_menu(
                    self.state, TicketType.TRAIN.value, train_paths
                )
                if train_destination and train_destination != "0":
                    if self.state.investigator.use_ticket(TicketType.TRAIN.value, 1):
                        self.state.investigator.current_location = train_paths[
                            int(train_destination) - 1
                        ]
                        self.ui.show_message(
                            f"Traveling by train to {self.state.investigator.current_location}..."
                        )
                        # Recursively offer more ticket travel options
                        self.offer_ticket_travel()
                        return

        # Check for ship connections
        ship_paths = location.ship_paths
        if ship_paths and self.state.investigator.ship_tickets > 0:
            use_ship = self.ui.ask_yes_no(
                f"You have {self.state.investigator.ship_tickets} ship tickets. Use one to travel by ship?"
            )
            if use_ship:
                ship_destination = self.ui.show_ticket_travel_menu(
                    self.state, TicketType.SHIP.value, ship_paths
                )
                if ship_destination and ship_destination != "0":
                    if self.state.investigator.use_ticket(TicketType.SHIP.value, 1):
                        self.state.investigator.current_location = ship_paths[
                            int(ship_destination) - 1
                        ]
                        self.ui.show_message(
                            f"Traveling by ship to {self.state.investigator.current_location}..."
                        )
                        # Recursively offer more ticket travel options
                        self.offer_ticket_travel()
                        return

    def rest_action(self):
        """Rest to recover health and sanity."""
        current_location = self.state.investigator.current_location
        location = self.state.locations[current_location]

        # Check if there are monsters at the current location
        if location.monsters:
            self.ui.show_message("You cannot rest while monsters are present!")
            return

        if self.state.use_action():
            self.state.investigator.heal(1)
            self.state.investigator.restore_sanity(1)
            self.ui.show_message("You rest and recover...")
        else:
            self.ui.show_message("Err: No actions remaining.")

    def trade_action(self):
        """Trade items with another investigator."""
        self.ui.show_message("Trade action not implemented yet.")

    def prepare_for_travel_action(self):
        """Prepare for travel by acquiring a ticket."""
        if self.state.use_action():
            ticket_type = self.ui.show_ticket_choice()
            if ticket_type == TicketType.TRAIN.value:
                self.state.investigator.add_ticket(TicketType.TRAIN.value, 1)
                self.ui.show_message("You prepare for travel and gain a train ticket.")
            elif ticket_type == TicketType.SHIP.value:
                self.state.investigator.add_ticket(TicketType.SHIP.value, 1)
                self.ui.show_message("You prepare for travel and gain a ship ticket.")
            else:
                # Invalid choice, default to train ticket
                self.state.investigator.add_ticket(TicketType.TRAIN.value, 1)
                self.ui.show_message("You prepare for travel and gain a train ticket.")
        else:
            self.ui.show_message("Err: No actions remaining.")

    def acquire_assets_action(self):
        """Acquire assets from the market."""
        self.ui.show_message("Acquire assets action not implemented yet.")

    def perform_component_action(self):
        """Perform an action from a component card."""
        self.ui.show_message("Perform component action not implemented yet.")
