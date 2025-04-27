from rich.console import Console
from rich.rule import Rule
from rich.panel import Panel
from rich.align import Align
from pyfiglet import Figlet
import os

class UIManager():
    def __init__(self, grahpic_height=12, screen_width=80):
        self.console = Console()
        self.console_methods = [f for f in dir(self.console) if not f.startswith("__")]
        self.fig = Figlet(font="banner")
        
    def __getattr__(self, name):
        # any attr not found on me, delegate to console
        if name in self.console_methods:
            return getattr(self.console, name)
        else:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
    def show_main_menu(self):
        self.clear_screen()
        ascii_title = self.fig.renderText("Eldritch Pursuit")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(Align.center("[green]1.[/] New Game   [green]2.[/] Instructions   [green]3.[/] Quit"))
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
        
    def show_action_phase(self, state):
        self.clear_screen()
        # TODO: replace wtih location art
        location_fig = Figlet(font="slant")
        location_name = state.current_location
        ascii_title = location_fig.renderText(location_name)
        location_desc = state.locations[state.current_location].description        
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.print(Align.center(f"[italic cyan]{location_desc}[/]"))
        
        self.rule(style="bright_yellow")
        self.print(f"Current Location: [bold]{state.current_location}[/bold]")
        self.print(f"Current Phase: [bold]{state.current_phase}[/bold]")
        
        if state.locations[state.current_location].has_gate:
            self.print("[red]WARNING: There is an open Gate here![/]")
            
        if state.locations[state.current_location].clues > 0:
            self.print(f"[yellow]There are {state.locations[state.current_location].clues} clues to be found here.[/]")
            
        # Display investigator status
        self.print(f"\nHealth: {state.investigator.health}/{state.investigator.max_health} | " +
          f"Sanity: {state.investigator.sanity}/{state.investigator.max_sanity} | " +
          f"Clue Tokens: {state.investigator.clue_tokens} | " +
          f"Tickets: {state.investigator.tickets}")
        
        # Display available actions
        self.print("\nAvailable Actions:")
        self.print("1. Travel")
        self.print("2. Rest (heal 1 Health and 1 Sanity)")
        
        if state.locations[state.current_location].clues > 0:
            self.print("3. Investigate (gather clues)")
        
        if state.locations[state.current_location].has_gate:
            self.print("4. Close Gate")
        
        self.print("9. Advance to Encounter Phase")
        
        choice = self.input("\n[bold cyan]Enter your choice[/] [yellow](1-4, 9)[/]: ")
        return choice
        
    def show_victory_screen(self):
        self.clear_screen()
        ascii_title = self.fig.renderText("VICTORY")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(Align.center("You have successfully solved three mysteries and averted the apocalypse!"))
        self.print(Align.center("The Ancient One stirs in its slumber but remains bound for another age."))
        self.print(Align.center("For now, humanity is safe... but for how long?"))
        self.rule(style="bright_yellow")
        self.input("\n[bold cyan]Press Enter to return to the main menu...[/]")
        
    def show_defeat_screen(self, reason):
        self.clear_screen()
        ascii_title = self.fig.renderText("DEFEAT")
        self.print(Align.center(f"[bold magenta]{ascii_title}[/]"), highlight=False)
        self.rule(style="bright_yellow")
        self.print(Align.center(f"[red]{reason}[/red]"))
        self.print(Align.center("The Ancient One stirs and the world trembles before its power."))
        self.print(Align.center("Darkness falls across the Earth as humanity faces its final hour."))
        self.rule(style="bright_yellow")
        self.input("\n[bold cyan]Press Enter to return to the main menu...[/]")


