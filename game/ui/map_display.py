from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.box import SIMPLE


class MapDisplay:
    def __init__(self, screen_width=100):
        self.screen_width = screen_width
        self.console = Console(width=screen_width)

    def display_world_map(self, game_state):
        """Display a structured ASCII world map with locations and connections"""
        map_table = Table(
            box=SIMPLE, show_header=True, header_style="bold magenta", padding=(0, 2)
        )

        # Define regions as columns
        regions = [
            "North America",
            "Europe",
            "Asia",
            "Pacific",
            "South America",
            "Africa",
        ]

        # Add columns with better spacing
        for region in regions:
            map_table.add_column(region, justify="center")

        # Define locations by region (organized for better visual layout)
        region_locations = {
            "North America": ["Arkham", "San Francisco", "Space 1", "Space 4"],
            "Europe": ["London", "Rome", "Istanbul", "Space 7", "Space 8"],
            "Asia": ["Tokyo", "Shanghai", "Space 11", "Space 12"],
            "Pacific": ["Sydney", "Space 2", "Space 3"],
            "South America": ["Buenos Aires", "Space 5", "Space 6"],
            "Africa": ["Cairo", "Space 9", "Space 10"],
        }

        # Maximum number of locations in any region
        max_locations = max(len(locations) for locations in region_locations.values())

        # Build the map row by row
        for i in range(max_locations):
            row = []
            for region in regions:
                locations = region_locations.get(region, [])
                if i < len(locations):
                    location_name = locations[i]
                    location = game_state.locations.get(location_name)

                    # Skip if location doesn't exist in game state
                    if not location:
                        row.append("")
                        continue

                    # Build location display with status indicators
                    location_text = Text()

                    # Show if player is here
                    if game_state.investigator.current_location == location_name:
                        location_text.append("* ", style="bold green")

                    # Add location name
                    location_text.append(f"{location_name}")

                    # Add indicators for gates, clues, monsters
                    indicators = []
                    if location.has_gate:
                        indicators.append("G")
                    if location.clues > 0:
                        indicators.append(f"C{location.clues}")
                    if location.monsters:
                        indicators.append(f"M{len(location.monsters)}")

                    if indicators:
                        location_text.append(
                            f" [{','.join(indicators)}]", style="bold red"
                        )

                    row.append(location_text)
                else:
                    row.append("")
            map_table.add_row(*row)

        # Display the map
        self.console.print(map_table)

        # Display legend
        self.console.print("\n[bold]Legend:[/bold]")
        self.console.print("* [green]Your location[/green]")
        self.console.print("G [red]Gate[/red]")
        self.console.print("C# [red]Clues (number)[/red]")
        self.console.print("M# [red]Monsters (number)[/red]")

    def display_connection_diagram(self, game_state):
        """Display a text-based connection diagram showing how locations connect"""
        conn_table = Table(
            title="Location Connections",
            show_header=True,
            box=SIMPLE,
            header_style="bold cyan",
            padding=(0, 1),
            width=self.screen_width,  # Use full screen width
        )

        conn_table.add_column("Location", style="cyan", no_wrap=True)
        conn_table.add_column("Connected To", style="green")
        conn_table.add_column("Train Routes", style="yellow")
        conn_table.add_column("Ship Routes", style="blue")

        # Add rows for each location
        for name, location in game_state.locations.items():
            # Build location display with status indicators
            location_text = Text()

            # Show if player is here
            if game_state.investigator.current_location == name:
                location_text.append("* ", style="bold green")

            # Add location name
            location_text.append(f"{name}")

            # Add indicators for gates, clues, monsters
            indicators = []
            if location.has_gate:
                indicators.append("G")
            if location.clues > 0:
                indicators.append(f"C{location.clues}")
            if location.monsters:
                indicators.append(f"M{len(location.monsters)}")

            if indicators:
                location_text.append(f" [{','.join(indicators)}]", style="bold red")

            conn_text = "\n".join(location.connections)
            train_text = (
                "\n".join(location.train_paths) if location.train_paths else "-"
            )
            ship_text = "\n".join(location.ship_paths) if location.ship_paths else "-"

            conn_table.add_row(location_text, conn_text, train_text, ship_text)

        # Display the connections
        self.console.print(conn_table)

        # Display legend
        self.console.print("\n[bold]Legend:[/bold]")
        self.console.print("* [green]Your location[/green]")
        self.console.print("G [red]Gate[/red]")
        self.console.print("C# [red]Clues (number)[/red]")
        self.console.print("M# [red]Monsters (number)[/red]")

    def display_graphical_map(self, game_state):
        """Display a more graphical ASCII map with better visual separation"""
        self.console.print("[bold]GRAPHICAL WORLD MAP[/bold]")

        # Define a more visual map layout with Unicode box characters
        # This is a simplified representation - locations are positioned roughly by geography

        # Map layout - each location has x,y coordinates
        map_layout = {
            "Arkham": (10, 2),
            "London": (25, 2),
            "Tokyo": (45, 2),
            "Sydney": (55, 2),
            "Buenos Aires": (15, 3),
            "San Francisco": (5, 4),
            "Rome": (30, 4),
            "Shanghai": (50, 4),
            "Space 1": (2, 5),
            "Space 2": (20, 5),
            "Space 3": (40, 5),
            "Space 4": (5, 6),
            "Space 5": (15, 6),
            "Space 6": (25, 6),
            "Istanbul": (35, 6),
            "Space 7": (45, 6),
            "Space 8": (55, 6),
            "Space 9": (10, 7),
            "Space 10": (30, 7),
            "Space 11": (50, 7),
            "Space 12": (60, 7),
            "Space 13": (20, 8),
            "Space 14": (40, 8),
            "Space 15": (60, 8),
            "Cairo": (30, 9),
        }

        # Create a grid for the map
        grid_height = 12
        grid_width = 70
        grid = [[" " for _ in range(grid_width)] for _ in range(grid_height)]

        # Place locations on the grid
        for name, (x, y) in map_layout.items():
            if name not in game_state.locations:
                continue

            location = game_state.locations[name]

            # Create location marker
            marker = name

            # Add indicators
            indicators = []
            if location.has_gate:
                indicators.append("G")
            if location.clues > 0:
                indicators.append(f"C{location.clues}")
            if location.monsters:
                indicators.append(f"M{len(location.monsters)}")

            # Place on grid (simplified - just the first character and indicators)
            if y < len(grid) and x < len(grid[y]):
                # Player marker
                if game_state.investigator.current_location == name:
                    grid[y][x] = "*"
                else:
                    grid[y][x] = name[0]  # First letter of location

                # Add indicators if they exist
                if indicators and x + 1 < len(grid[y]):
                    grid[y][x + 1] = "["
                    for i, ind in enumerate(indicators):
                        if x + 2 + i < len(grid[y]):
                            grid[y][x + 2 + i] = ind[0]  # First character of indicator
                    if x + 2 + len(indicators) < len(grid[y]):
                        grid[y][x + 2 + len(indicators)] = "]"

        # Print the grid
        for row in grid:
            self.console.print("".join(row))
