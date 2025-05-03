from rich.console import Console
from rich.rule import Rule
from rich.panel import Panel
from rich.align import Align
from rich.table import Table
from pyfiglet import Figlet  # type: ignore
import os
from game.ui.map_display import MapDisplay
from game.enums import GamePhase, TicketType
from game.entities.location import Location


class UIManager:
    def __init__(self, graphic_height=12, screen_width=80):
        self.console = Console()
        self.console_methods = [f for f in dir(self.console) if not f.startswith("__")]
        self.fig = Figlet(font="banner")
        self.map_display = MapDisplay(screen_width)

    # Add a new method to show the map
    def show_map(self, state):
        """Display the game map with multiple view options"""
        while True:
            self.clear_screen()
            self.print(Align.center("[bold magenta]WORLD MAP[/bold magenta]"))
            self.rule(style="bright_yellow")

            # Show map options
            self.print("[bold]Map View Options:[/bold]")
            self.print("1. Region-based Map (organized by continent)")
            self.print("2. Connection Diagram (shows travel routes)")
            self.print("3. Return to previous screen")

            choice = self.input("\n[bold cyan]Select map view[/] [yellow](1-3)[/]: ")

            if choice == "1":
                self.clear_screen()
                self.print(Align.center("[bold magenta]REGION MAP[/bold magenta]"))
                self.rule(style="bright_yellow")
                self.map_display.display_world_map(state)
                self.input("\n[bold cyan]Press Enter to return to map menu...[/]")
            elif choice == "2":
                self.clear_screen()
                self.print(
                    Align.center("[bold magenta]CONNECTION DIAGRAM[/bold magenta]")
                )
                self.rule(style="bright_yellow")
                self.map_display.display_connection_diagram(state)
                self.input("\n[bold cyan]Press Enter to return to map menu...[/]")
            elif choice == "3":
                break

    def __getattr__(self, name):
        # any attr not found on me, delegate to console
        if name in self.console_methods:
            return getattr(self.console, name)
        else:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}'"
            )

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def show_message(self, message, wait_for_input=True):
        """Display a message to the player."""
        self.print(f"\n[italic]{message}[/italic]")
        if wait_for_input:
            self.input("\n[bold cyan]Press Enter to continue...[/]")

    def ask_yes_no(self, question):
        """Ask the player a yes/no question."""
        while True:
            answer = self.input(f"{question} [yellow](y/n)[/]")
            if answer.lower() == "y":
                return True
            elif answer.lower() == "n":
                return False
            else:
                self.print("Please answer 'y' or 'n'.")

    def show_main_menu(self):
        self.clear_screen()
        ascii_title = self.fig.renderText("Eldritch Pursuit")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(
            Align.center(
                "[green]1.[/] New Game   [green]2.[/] Instructions   [green]3.[/] Quit"
            )
        )
        self.rule(style="bright_yellow")
        return self.input("\n[bold cyan]Enter your choice[/] [yellow](1-3)[/]: ")

    def show_instructions(self):
        self.clear_screen()
        instr = """\
Eldritch Pursuit is based on the board game Eldritch Horror.

Your goal is to solve [bold]3 mysteries[/bold] before the Ancient One awakens.

Each round consists of three phases:
  • [bold]Action Phase[/]: Travel, rest, or acquire assets
  • [bold]Encounter Phase[/]: Deal with monsters or location events
  • [bold]Mythos Phase[/]: Face random events, often dangerous

The doom track advances throughout the game. If it reaches maximum,
the Ancient One awakens and the final mystery begins.

Good luck, investigator. The fate of the world is in your hands.
"""
        panel = Panel.fit(
            instr,
            title="[bold yellow]INSTRUCTIONS[/bold yellow]",
            border_style="bright_blue",
            padding=(1, 2),
        )
        self.print(panel)
        self.input("\n[bold cyan]Press Enter to return to the main menu...[/]")

    def show_player_count_selection(self):
        """Display player count selection menu."""
        self.clear_screen()
        self.print(Align.center("[bold magenta]NEW GAME[/bold magenta]"))
        self.rule(style="bright_yellow")

        self.print("\n[bold]Select Number of Players:[/bold]")
        for i in range(1, 9):
            self.print(f"[green]{i}.[/green] {i} Player{'s' if i > 1 else ''}")

        while True:
            choice = self.input("\n[bold cyan]Enter your choice[/] [yellow](1-8)[/]: ")
            try:
                player_count = int(choice)
                if 1 <= player_count <= 8:
                    return player_count
                else:
                    self.print(
                        "[red]Invalid choice. Please enter a number between 1 and 8.[/red]"
                    )
            except ValueError:
                self.print("[red]Invalid input. Please enter a number.[/red]")

    def show_player_name_entry(self, player_number):
        """
        Prompt for a player's name.

        Args:
            player_number: The player number (1-based)

        Returns:
            The player's name
        """
        self.clear_screen()
        self.print(Align.center("[bold magenta]PLAYER SETUP[/bold magenta]"))
        self.rule(style="bright_yellow")

        self.print(f"\n[bold]Player {player_number}[/bold]")

        while True:
            name = self.input("\n[bold cyan]Enter player name[/]: ")
            if name.strip():
                return name
            else:
                self.print("[red]Name cannot be empty. Please enter a name.[/red]")

    def show_investigator_selection(self, available_investigators, player_name):
        """
        Display investigator selection menu.

        Args:
            available_investigators: Dict of investigator_id -> investigator data
            player_name: Name of the player selecting an investigator

        Returns:
            The selected investigator ID, or None if canceled
        """
        self.clear_screen()
        self.print(Align.center("[bold magenta]INVESTIGATOR SELECTION[/bold magenta]"))
        self.rule(style="bright_yellow")

        self.print(f"\n[bold]Player: {player_name}[/bold]")
        self.print("\n[bold]Choose your investigator:[/bold]")

        # Create a table for investigators
        table = Table(show_header=True, header_style="bold")
        table.add_column("#", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Occupation", style="green")
        table.add_column("Role", style="yellow")
        table.add_column("Health", style="red")
        table.add_column("Sanity", style="blue")

        # Sort investigators by ID
        sorted_investigators = sorted(
            available_investigators.items(), key=lambda x: x[0]
        )

        # Add investigators to the table
        for i, (investigator_id, data) in enumerate(sorted_investigators, 1):
            table.add_row(
                str(i),
                data["name"],
                data["occupation"],
                data["role"],
                str(data["max_health"]),
                str(data["max_sanity"]),
            )

        self.print(table)

        # Get user choice
        while True:
            choice = self.input(
                f"\n[bold cyan]Enter your choice[/] [yellow](1-{len(sorted_investigators)})[/]: "
            )
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(sorted_investigators):
                    return sorted_investigators[choice_idx][
                        0
                    ]  # Return the investigator ID
                else:
                    self.print(
                        f"[red]Invalid choice. Please enter a number between 1 and {len(sorted_investigators)}.[/red]"
                    )
            except ValueError:
                self.print("[red]Invalid input. Please enter a number.[/red]")

    def show_investigator_details(self, investigator_data):
        """
        Display detailed information about an investigator.

        Args:
            investigator_data: Dict containing investigator data

        Returns:
            True if the player confirms the selection, False otherwise
        """
        self.clear_screen()
        self.print(Align.center("[bold magenta]INVESTIGATOR DETAILS[/bold magenta]"))
        self.rule(style="bright_yellow")

        # Create a panel for the investigator
        name = investigator_data["name"]
        occupation = investigator_data["occupation"]
        role = investigator_data["role"]

        # Basic info
        self.print(f"[bold cyan]{name}[/bold cyan], [italic]{occupation}[/italic]")
        self.print(f"Role: [yellow]{role}[/yellow]")
        self.print(
            f"Starting Location: [green]{investigator_data.get('starting_location', 'London')}[/green]"
        )

        # Stats
        self.print("\n[bold]Stats:[/bold]")
        self.print(f"Health: [red]{investigator_data['max_health']}[/red]")
        self.print(f"Sanity: [blue]{investigator_data['max_sanity']}[/blue]")

        # Skills
        self.print("\n[bold]Skills:[/bold]")
        skills = investigator_data["skills"]
        for skill, value in skills.items():
            self.print(f"{skill.capitalize()}: {value}")

        # Quote and bio
        if "quote" in investigator_data:
            self.print(f"\n[italic]\"{investigator_data['quote']}\"[/italic]")

        if "bio" in investigator_data:
            bio_panel = Panel(
                investigator_data["bio"], title="[bold]Biography[/bold]", width=80
            )
            self.print(bio_panel)

        # Abilities
        if "abilities" in investigator_data and investigator_data["abilities"]:
            self.print("\n[bold]Abilities:[/bold]")
            for ability in investigator_data["abilities"]:
                ability_type = ability.get("type", "").capitalize()
                ability_text = ability.get("text", "")
                self.print(f"[yellow]{ability_type}:[/yellow] {ability_text}")

        # Confirm selection
        return self.ask_yes_no("\nConfirm this investigator selection?")

    def show_action_phase(self, state):
        self.clear_screen()

        # Get current player and investigator using player_manager
        player_manager = state.player_manager
        current_player = player_manager.get_current_player()
        
        if not current_player or not current_player.investigator:
            self.show_message("Error: No current player or investigator found!")
            return "9"  # End turn

        # Get current investigator
        current_investigator = current_player.investigator
        player_name = current_player.name if current_player else "Unknown"

        # Get location info
        location_name = current_investigator.current_location
        location: Location = state.locations[location_name]
        real_location = location.real_world_location
        location_desc = location.description

        # Create ASCII art title - use just the primary location name
        location_fig = Figlet(font="slant")
        ascii_title = location_fig.renderText(location_name)

        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)

        # For Space X locations, show real world location as a subtitle
        if location_name.startswith("Space ") and real_location:
            self.print(Align.center(f"[bold blue]{real_location}[/bold blue]"))

        self.print(Align.center(f"[italic cyan]{location_desc}[/]"))

        self.rule(style="bright_yellow")

        # Display player info
        if current_player:
            self.print(f"Current Player: [bold]{player_name}[/bold]")
            if current_player.is_lead_investigator:
                self.print("[yellow]Lead Investigator[/yellow]")

        # Display current location with real world location for Space X locations
        if location_name.startswith("Space ") and real_location:
            self.print(
                f"Current Location: [bold]{location_name}[/bold] ([italic]{real_location}[/italic])"
            )
        else:
            self.print(f"Current Location: [bold]{location_name}[/bold]")

        self.print(f"Current Phase: [bold]{state.current_phase.value}[/bold]")
        self.print(
            f"Actions Remaining: [bold green]{current_investigator.actions}[/bold green]"
        )

        if location.has_gate:
            self.print("[red]WARNING: There is an open Gate here![/]")

        if location.has_clue:
            self.print(f"[yellow]There is a clue to be found here.[/]")

        # Display investigator status
        self.print(
            f"\nHealth: {current_investigator.health}/{current_investigator.max_health} | "
            + f"Sanity: {current_investigator.sanity}/{current_investigator.max_sanity} | "
            + f"Clue Tokens: {current_investigator.clue_tokens}"
        )

        # Display tickets
        self.print(
            f"Train Tickets: {current_investigator.train_tickets} | Ship Tickets: {current_investigator.ship_tickets}"
        )

        # Display available actions
        if current_investigator.actions > 0:
            self.print("\nAvailable Actions:")
            self.print("1. Travel")
            self.print("2. Rest (heal 1 Health and 1 Sanity)")
            self.print("3. Trade with another investigator")
            self.print("4. Prepare for Travel (gain 1 ticket of your choice)")
            self.print("5. Acquire Assets")
            self.print("6. Perform a Component Action")

            self.print("\nOther Options:")
            self.print("7. View Map")
            self.print("9. End Turn (Advance to Encounter Phase)")

            choice = self.input(
                "\n[bold cyan]Enter your choice[/] [yellow](1-7, 9)[/]: "
            )
            return choice
        else:
            self.print("\n[bold red]You have no actions remaining![/]")
            self.input("\n[bold cyan]Press Enter to continue to Encounter Phase...[/]")
            return "9"

    def show_travel_menu(self, state):
        """Display travel options for the current location"""
        self.clear_screen()

        # Get current investigator
        current_investigator = state.get_current_investigator()
        if not current_investigator:
            self.show_message("Error: No current investigator found!")
            return "0"  # Cancel

        connections = state.locations[current_investigator.current_location].connections

        self.print(
            f"\n[bold]Travel from {current_investigator.current_location}[/bold]"
        )
        self.rule(style="bright_yellow")

        self.print("\nConnected locations:")
        for i, location in enumerate(connections, 1):
            # Only show real world location for Space X locations
            if location.startswith("Space "):
                real_location = state.locations[location].real_world_location
                if real_location:
                    self.print(
                        f"[green]{i}.[/green] {location} ([italic]{real_location}[/italic])"
                    )
                else:
                    self.print(f"[green]{i}.[/green] {location}")
            else:
                self.print(f"[green]{i}.[/green] {location}")

        self.print("[green]0. Cancel[/green]")

        choice = self.input(
            f"\n[bold cyan]Enter your choice[/] [yellow](0-{len(connections)})[/]: "
        )
        return choice

    def show_ticket_travel_menu(self, state, ticket_type, destinations):
        """Display travel options for ticket-based travel"""
        self.clear_screen()

        # Get current investigator
        current_investigator = state.get_current_investigator()
        if not current_investigator:
            self.show_message("Error: No current investigator found!")
            return "0"  # Cancel

        self.print(
            f"\n[bold]Travel by {ticket_type.capitalize()} from "
            f"{current_investigator.current_location}[/bold]"
        )
        self.rule(style="bright_yellow")

        self.print(f"\nAvailable {ticket_type} destinations:")
        for i, location in enumerate(destinations, 1):
            # Only show real world location for Space X locations
            if location.startswith("Space "):
                real_location = state.locations[location].real_world_location
                if real_location:
                    self.print(
                        f"[green]{i}.[/green] {location} ([italic]{real_location}[/italic])"
                    )
                else:
                    self.print(f"[green]{i}.[/green] {location}")
            else:
                self.print(f"[green]{i}.[/green] {location}")

        self.print("[green]0. Cancel[/green]")

        choice = self.input(
            f"\n[bold cyan]Enter your choice[/] [yellow](0-{len(destinations)})[/]: "
        )
        return choice

    def show_ticket_choice(self):
        """Display ticket type choice menu"""
        self.clear_screen()

        self.print("\n[bold]Choose Ticket Type[/bold]")
        self.rule(style="bright_yellow")

        self.print("\nAvailable ticket types:")
        self.print(f"[green]1.[/green] {TicketType.TRAIN.value.capitalize()} Ticket")
        self.print(f"[green]2.[/green] {TicketType.SHIP.value.capitalize()} Ticket")

        choice = self.input("\n[bold cyan]Enter your choice[/] [yellow](1-2)[/]: ")

        if choice == "1":
            return TicketType.TRAIN.value
        elif choice == "2":
            return TicketType.SHIP.value
        else:
            self.show_message("Invalid choice. Defaulting to train ticket.")
            return TicketType.TRAIN.value

    def show_victory_screen(self):
        self.clear_screen()
        ascii_title = self.fig.renderText("VICTORY")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(
            Align.center(
                "You have successfully solved three mysteries and averted the apocalypse!"
            )
        )
        self.print(
            Align.center(
                "The Ancient One stirs in its slumber but remains bound for another age."
            )
        )
        self.print(Align.center("For now, humanity is safe... but for how long?"))
        self.rule(style="bright_yellow")
        self.input("\n[bold cyan]Press Enter to return to the main menu...[/]")

    def show_defeat_screen(self, reason):
        self.clear_screen()
        ascii_title = self.fig.renderText("DEFEAT")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(Align.center(f"[red]{reason}[/red]"))
        self.print(
            Align.center(
                "The Ancient One stirs and the world trembles before its power."
            )
        )
        self.print(
            Align.center(
                "Darkness falls across the Earth as humanity faces its final hour."
            )
        )
        self.rule(style="bright_yellow")
        self.input("\n[bold cyan]Press Enter to return to the main menu...[/]")

    def show_choose_encounter(self, available_decks, current_location):
        """Display encounter deck options for the current location"""
        self.clear_screen()

        self.print(Align.center("[bold magenta]CHOOSE ENCOUNTER[/bold magenta]"))
        self.rule(style="bright_yellow")

        self.print(f"Current Location: [bold]{current_location}[/bold]")

        # Display available encounter decks
        self.print("\n[bold]Available Encounter Decks:[/bold]")
        for i, (deck_name, description) in enumerate(available_decks, 1):
            self.print(
                f"[green]{i}.[/green] {deck_name} - [italic]{description}[/italic]"
            )

        # Get user choice
        choice = self.input(
            f"\n[bold cyan]Choose an encounter deck[/] [yellow](1-{len(available_decks)})[/]: "
        )

        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(available_decks):
                selected_deck = available_decks[choice_idx][0]
                return selected_deck
            else:
                self.show_message("Invalid choice. Defaulting to General encounters.")
                return "General"
        except ValueError:
            self.show_message("Invalid choice. Defaulting to General encounters.")
            return "General"

    def show_choice(self, prompt, options, allow_cancel=True):
        """Display a list of options and return the user's choice.

        Args:
            prompt: The question or prompt to display
            options: List of options to choose from
            allow_cancel: Whether to allow canceling (defaults to True)

        Returns:
            The selected option or None if canceled
        """
        self.clear_screen()
        self.print(f"\n[bold]{prompt}[/bold]")
        self.rule(style="bright_yellow")

        # Display options
        for i, option in enumerate(options, 1):
            self.print(f"[green]{i}.[/green] {option}")

        # Add cancel option if allowed
        if allow_cancel:
            self.print("[green]0.[/green] Cancel")

        # Get user choice
        max_choice = len(options)
        min_choice = 0 if allow_cancel else 1

        choice = self.input(
            f"\n[bold cyan]Enter your choice[/] [yellow]({min_choice}-{max_choice})[/]: "
        )

        try:
            choice_idx = int(choice)
            if min_choice <= choice_idx <= max_choice:
                if choice_idx == 0:
                    return None  # Canceled
                return options[choice_idx - 1]

            self.show_message("Invalid choice.")
            return self.show_choice(prompt, options, allow_cancel)
        except ValueError:
            self.show_message("Invalid input. Please enter a number.")
            return self.show_choice(prompt, options, allow_cancel)

    def show_player_turn_transition(self, player_name, investigator_name):
        """
        Display a transition screen when switching to a new player's turn.

        Args:
            player_name: Name of the player whose turn is starting
            investigator_name: Name of the investigator controlled by the player
        """
        self.clear_screen()
        self.print(Align.center("[bold magenta]PLAYER TURN[/bold magenta]"))
        self.rule(style="bright_yellow")

        self.print(Align.center(f"[bold cyan]{player_name}[/bold cyan]'s Turn"))
        self.print(Align.center(f"Playing as [bold]{investigator_name}[/bold]"))

        self.input("\n[bold cyan]Press Enter to begin your turn...[/]")
