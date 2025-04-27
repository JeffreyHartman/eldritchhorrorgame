"""Action phase implementation"""

from game.phases.base_phase import GamePhase


class ActionPhase(GamePhase):
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
            elif choice == "9":
                break

        # Show final location view before advancing to the next phase
        self.ui.show_action_phase(self.state)

        self.state.current_phase = "Encounter"
        self.ui.show_message("Advancing to Encounter Phase...")

    def travel_action(self, ticket_used=False):
        """Travel between locations."""
        choice = self.ui.show_travel_menu(self.state)
        if choice == "0":
            return

        try:
            choice_idx = int(choice) - 1
            connections = self.state.locations[
                self.state.investigator.current_location
            ].connections

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

                # Offer to use travel tickets for additional movement if available
                if self.state.investigator.tickets > 0:
                    use_ticket = self.ui.ask_yes_no(
                        f"You have {self.state.investigator.tickets} travel tickets. Use one to travel further?"
                    )
                    if use_ticket:
                        self.state.investigator.tickets -= 1
                        self.travel_action(ticket_used=True)
            else:
                self.ui.show_message("Invalid location choice.")
        except ValueError:
            self.ui.show_message("Invalid location choice.")

    def rest_action(self):
        current_location = self.state.investigator.current_location
        location = self.state.locations[current_location]

        # Check if there are monsters at the current location
        if location.monsters:
            self.ui.show_message("You cannot rest while monsters are present!")
            return
        else:
            if self.state.use_action():
                self.state.investigator.health = min(
                    self.state.investigator.health + 1,
                    self.state.investigator.max_health,
                )
                self.state.investigator.sanity = min(
                    self.state.investigator.sanity + 1,
                    self.state.investigator.max_sanity,
                )
                self.ui.show_message("You rest and recover...")
            else:
                self.ui.show_message("Err: No actions remaining.")

    def trade_action(self):
        self.ui.show_message("Trade action not implemented yet.")
        pass

    def prepare_for_travel_action(self):
        if self.state.use_action():
            self.state.investigator.tickets += 1
            self.ui.show_message("You prepare for travel and gain a ticket.")
        else:
            self.ui.show_message("Err: No actions remaining.")

    def acquire_assets_action(self):
        self.ui.show_message("Acquire assets action not implemented yet.")
        pass

    def perform_component_action(self):
        self.ui.show_message("Perform component action not implemented yet.")
        pass
