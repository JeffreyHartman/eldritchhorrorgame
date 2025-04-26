import random
import time
import os
from art import *

# Game constants
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
GAME_TITLE = "Eldritch Pursuit"

# Game state
doom_track = 0
max_doom = 15
mysteries_solved = 0
current_phase = "Action"  # "Action", "Encounter", "Mythos"
current_location = "London"

# Game data
locations = {
    "London": {
        "description": "Foggy streets conceal ancient secrets",
        "connections": ["Paris", "Rome"],
        "has_gate": False,
        "clues": 1
    },
    "Paris": {
        "description": "The city of lights casts long shadows",
        "connections": ["London", "Istanbul"],
        "has_gate": False,
        "clues": 0
    },
    "Rome": {
        "description": "The eternal city hides eternal horrors",
        "connections": ["London", "Istanbul"],
        "has_gate": True,
        "clues": 0
    },
    "Istanbul": {
        "description": "Where East meets West, and worlds collide",
        "connections": ["Paris", "Rome", "Shanghai"],
        "has_gate": False,
        "clues": 2
    },
    "Shanghai": {
        "description": "Ancient traditions clash with cosmic threats",
        "connections": ["Istanbul", "Tokyo"],
        "has_gate": False,
        "clues": 0
    },
    "Tokyo": {
        "description": "Modern metropolis with hidden occult dangers",
        "connections": ["Shanghai", "San Francisco"],
        "has_gate": True,
        "clues": 0
    },
    "San Francisco": {
        "description": "The Golden Gate to other dimensions",
        "connections": ["Tokyo", "Arkham"],
        "has_gate": False,
        "clues": 1
    },
    "Arkham": {
        "description": "Small town with a dark history",
        "connections": ["San Francisco", "London"],
        "has_gate": False,
        "clues": 0
    }
}

# Investigator stats
investigator = {
    "name": "Anna Blackwood",
    "health": 5,
    "max_health": 5,
    "sanity": 5,
    "max_sanity": 5,
    "skills": {
        "lore": 2,
        "influence": 3,
        "observation": 2,
        "strength": 1,
        "will": 3
    },
    "items": [],
    "clue_tokens": 2,
    "tickets": 0,
    "is_delayed": False
}

def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def draw_ascii_logo():
    """Draw a simple ASCII art logo for the game."""
    tprint("Eldritch Pursuit")

def show_main_menu():
    """Display the main menu and get player choice."""
    clear_screen()
    draw_ascii_logo()
    print("\n" + "=" * 80)
    print("1. New Game")
    print("2. Instructions")
    print("3. Quit")
    print("=" * 80)
    
    choice = input("\nEnter your choice (1-3): ")
    
    if choice == "1":
        start_game()
    elif choice == "2":
        show_instructions()
    elif choice == "3":
        print("\nThank you for playing!")
        exit()
    else:
        show_main_menu()

def show_instructions():
    """Show game instructions."""
    clear_screen()
    print("\n" + "=" * 80)
    print("                              INSTRUCTIONS")
    print("=" * 80)
    print("\nEldritch Pursuit is based on the board game Eldritch Horror.")
    print("\nYour goal is to solve 3 mysteries before the Ancient One awakens.")
    print("Each round consists of three phases:")
    print("  1. Action Phase: Travel, rest, or acquire assets")
    print("  2. Encounter Phase: Deal with monsters or location events")
    print("  3. Mythos Phase: Face random events, often dangerous")
    print("\nThe doom track advances throughout the game. If it reaches maximum,")
    print("the Ancient One awakens and the final mystery begins.")
    print("\nGood luck, investigator. The fate of the world is in your hands.")
    print("\n" + "=" * 80)
    
    input("\nPress Enter to return to the main menu...")
    show_main_menu()

def start_game():
    """Initialize and start a new game."""
    global doom_track, mysteries_solved, current_phase, current_location
    
    # Reset game state
    doom_track = 0
    mysteries_solved = 0
    current_phase = "Action"
    current_location = "London"
    
    # Reset investigator
    investigator["health"] = investigator["max_health"]
    investigator["sanity"] = investigator["max_sanity"]
    investigator["items"] = []
    investigator["clue_tokens"] = 2
    investigator["tickets"] = 0
    investigator["is_delayed"] = False
    
    # Start the game loop
    game_loop()

def game_loop():
    """Main game loop."""
    while doom_track < max_doom and mysteries_solved < 3:
        if current_phase == "Action":
            action_phase()
        elif current_phase == "Encounter":
            encounter_phase()
        elif current_phase == "Mythos":
            mythos_phase()
            
        # Check for game over conditions
        if investigator["health"] <= 0 or investigator["sanity"] <= 0:
            show_defeat_screen("Your investigator has been defeated!")
            return
    
    # Game ended - check win/loss
    if mysteries_solved >= 3:
        show_victory_screen()
    else:
        show_defeat_screen("The Ancient One has awakened!")

def action_phase():
    """Handle the action phase menu and actions."""
    global current_phase, current_location
    
    clear_screen()
    print("\n" + "=" * 80)
    print(f"Action Phase - Current Location: {current_location}")
    print("=" * 80)
    
    # Display location info
    location = locations[current_location]
    print(f"\n{location['description']}")
    
    if location["has_gate"]:
        print("\n[!] WARNING: There is an open Gate here!")
    
    if location["clues"] > 0:
        print(f"\n[?] There are {location['clues']} clues to be found here.")
    
    # Display investigator status
    print(f"\nHealth: {investigator['health']}/{investigator['max_health']} | " +
          f"Sanity: {investigator['sanity']}/{investigator['max_sanity']} | " +
          f"Clue Tokens: {investigator['clue_tokens']} | " +
          f"Tickets: {investigator['tickets']}")
    
    # Display available actions
    print("\nAvailable Actions:")
    print("1. Travel")
    print("2. Rest (heal 1 Health and 1 Sanity)")
    
    if location["clues"] > 0:
        print("3. Investigate (gather clues)")
    
    if location["has_gate"]:
        print("4. Close Gate")
    
    print("9. Advance to Encounter Phase")
    
    choice = input("\nEnter your choice: ")
    
    if choice == "1":
        travel_action()
    elif choice == "2":
        rest_action()
    elif choice == "3" and location["clues"] > 0:
        investigate_action()
    elif choice == "4" and location["has_gate"]:
        close_gate_action()
    elif choice == "9":
        current_phase = "Encounter"
    else:
        # Invalid choice, just redisplay the menu
        pass

def travel_action():
    """Handle travel between locations."""
    global current_location
    
    clear_screen()
    print("\n" + "=" * 80)
    print(f"Travel from {current_location}")
    print("=" * 80)
    
    connections = locations[current_location]["connections"]
    print("\nConnected locations:")
    
    for i, location in enumerate(connections, 1):
        print(f"{i}. {location}")
    
    print("0. Cancel")
    
    choice = input("\nEnter your choice: ")
    
    if choice == "0":
        return
    
    try:
        choice_idx = int(choice) - 1
        if 0 <= choice_idx < len(connections):
            current_location = connections[choice_idx]
            print(f"\nTraveling to {current_location}...")
            time.sleep(1.5)
    except ValueError:
        pass  # Invalid input, just return to action menu

def rest_action():
    """Rest to recover health and sanity."""
    investigator["health"] = min(investigator["health"] + 1, investigator["max_health"])
    investigator["sanity"] = min(investigator["sanity"] + 1, investigator["max_sanity"])
    
    print("\nYou take time to rest and recover...")
    time.sleep(1.5)
    print(f"Health: {investigator['health']}/{investigator['max_health']} | " +
          f"Sanity: {investigator['sanity']}/{investigator['max_sanity']}")
    
    input("\nPress Enter to continue...")

def investigate_action():
    """Investigate the current location for clues."""
    global locations, investigator
    
    print("\nYou begin investigating the area...")
    time.sleep(1.5)
    
    # Simple skill check for investigation
    success_needed = 1
    successes = skill_test("observation")
    
    if successes >= success_needed:
        print("\nYour investigation reveals hidden secrets!")
        investigator["clue_tokens"] += 1
        locations[current_location]["clues"] -= 1
        print(f"You now have {investigator['clue_tokens']} clue tokens.")
    else:
        print("\nYour investigation turns up nothing of value.")
    
    input("\nPress Enter to continue...")

def close_gate_action():
    """Attempt to close a gate at the current location."""
    global locations, doom_track, mysteries_solved
    
    print("\nYou begin the ritual to close the gate...")
    time.sleep(1.5)
    
    # Need clues to close a gate
    if investigator["clue_tokens"] < 2:
        print("\nYou need at least 2 clue tokens to attempt closing a gate.")
        input("\nPress Enter to continue...")
        return
    
    # Skill check to close gate
    success_needed = 2
    successes = skill_test("lore")
    
    if successes >= success_needed:
        print("\nThe gate collapses with a thunderous implosion!")
        locations[current_location]["has_gate"] = False
        investigator["clue_tokens"] -= 2
        
        # Solving a gate counts toward mysteries
        mysteries_solved += 1
        print(f"\nMysteries solved: {mysteries_solved}/3")
    else:
        print("\nThe ritual fails. The gate remains open.")
        # Failed attempt still costs clues
        investigator["clue_tokens"] -= 1
        
        # Failed attempt increases doom
        doom_track += 1
        print(f"\nDoom track advances to {doom_track}/{max_doom}")
    
    input("\nPress Enter to continue...")

def encounter_phase():
    """Handle the encounter phase."""
    global current_phase
    
    clear_screen()
    print("\n" + "=" * 80)
    print(f"Encounter Phase - {current_location}")
    print("=" * 80)
    
    # Generate a random encounter
    print("\nYou face an encounter at this location...")
    time.sleep(1.5)
    
    location = locations[current_location]
    
    # Priority: Gates -> Monsters -> Location event
    if location["has_gate"]:
        gate_encounter()
    else:
        # 30% chance of monster, 70% chance of location event
        if random.random() < 0.3:
            monster_encounter()
        else:
            location_encounter()
    
    # Move to next phase
    current_phase = "Mythos"

def gate_encounter():
    """Handle an encounter at a gate."""
    print("\nThe swirling gate pulses with eldritch energy!")
    
    # Gate causes a sanity check
    success_needed = 2
    successes = skill_test("will")
    
    sanity_loss = max(0, success_needed - successes)
    if sanity_loss > 0:
        investigator["sanity"] -= sanity_loss
        print(f"\nThe alien energies assault your mind! You lose {sanity_loss} Sanity.")
        print(f"Sanity: {investigator['sanity']}/{investigator['max_sanity']}")
    else:
        print("\nYou steel your mind against the gate's influence.")
    
    input("\nPress Enter to continue...")

def monster_encounter():
    """Handle a monster encounter."""
    monsters = ["Cultist", "Deep One", "Ghost", "Ghoul", "Byakhee"]
    monster = random.choice(monsters)
    
    print(f"\nA {monster} appears before you!")
    time.sleep(1)
    
    # Horror check first
    print("\nYou must face the horror of the creature...")
    horror_value = random.randint(1, 3)
    successes = skill_test("will")
    
    sanity_loss = max(0, horror_value - successes)
    if sanity_loss > 0:
        investigator["sanity"] -= sanity_loss
        print(f"\nThe sight of the {monster} shakes your sanity! You lose {sanity_loss} Sanity.")
        print(f"Sanity: {investigator['sanity']}/{investigator['max_sanity']}")
        
        if investigator["sanity"] <= 0:
            print("\nYour mind breaks under the cosmic horror!")
            input("\nPress Enter to continue...")
            return
    else:
        print("\nYou steel your mind against the horror.")
    
    # Combat check
    print("\nThe monster attacks! You must fight or flee...")
    
    choice = input("\nDo you want to fight (F) or flee (R)? ").upper()
    
    if choice == "F":
        # Fight the monster
        damage_value = random.randint(1, 3)
        toughness = random.randint(1, 4)
        
        print(f"\nThe {monster} attacks with {damage_value} damage and has {toughness} toughness.")
        
        successes = skill_test("strength")
        
        health_loss = max(0, damage_value - successes)
        if health_loss > 0:
            investigator["health"] -= health_loss
            print(f"\nThe {monster} wounds you! You lose {health_loss} Health.")
            print(f"Health: {investigator['health']}/{investigator['max_health']}")
            
            if investigator["health"] <= 0:
                print("\nYou are gravely wounded and fall unconscious!")
                input("\nPress Enter to continue...")
                return
        else:
            print("\nYou avoid the monster's attack.")
        
        # Did you defeat the monster?
        if successes >= toughness:
            print(f"\nYou defeat the {monster}!")
        else:
            print(f"\nThe {monster} is too tough! It remains at this location.")
    else:
        # Flee - take a health penalty
        investigator["health"] -= 1
        print("\nYou flee in terror, sustaining minor injuries.")
        print(f"Health: {investigator['health']}/{investigator['max_health']}")
    
    input("\nPress Enter to continue...")

def location_encounter():
    """Handle a random location encounter."""
    location_name = current_location
    
    encounters = [
        f"You meet a professor at {location_name} University who shares ancient lore.",
        f"A mysterious stranger in {location_name} offers you assistance.",
        f"While exploring {location_name}, you discover a hidden chamber.",
        f"The locals in {location_name} tell you tales of recent strange happenings.",
        f"You find an old tome in a {location_name} bookshop with useful information."
    ]
    
    encounter = random.choice(encounters)
    print(f"\n{encounter}")
    time.sleep(1.5)
    
    # 50% good outcome, 50% neutral/bad
    if random.random() < 0.5:
        good_outcomes = [
            "You gain valuable insight. +1 Clue token.",
            "The information helps calm your mind. +1 Sanity.",
            "You find a useful item that bolsters your resolve. +1 Health.",
            "You learn of a shortcut for future travels. +1 Ticket."
        ]
        
        outcome = random.choice(good_outcomes)
        print(f"\n{outcome}")
        
        if "Clue token" in outcome:
            investigator["clue_tokens"] += 1
        elif "Sanity" in outcome:
            investigator["sanity"] = min(investigator["sanity"] + 1, investigator["max_sanity"])
        elif "Health" in outcome:
            investigator["health"] = min(investigator["health"] + 1, investigator["max_health"])
        elif "Ticket" in outcome:
            investigator["tickets"] += 1
    else:
        neutral_outcomes = [
            "You spend time investigating but find nothing useful.",
            "The lead turns out to be a dead end.",
            "You're left with more questions than answers.",
            "Strange whispers follow you, but you cannot determine their source."
        ]
        
        outcome = random.choice(neutral_outcomes)
        print(f"\n{outcome}")
    
    input("\nPress Enter to continue...")

def mythos_phase():
    """Handle the mythos phase."""
    global current_phase, doom_track
    
    clear_screen()
    print("\n" + "=" * 80)
    print("Mythos Phase")
    print("=" * 80)
    
    print("\nDrawing a Mythos card...")
    time.sleep(2)
    
    # Simulate drawing a mythos card
    mythos_events = [
        "The stars align...",
        "Dark whispers echo across the world...",
        "Ancient seals weaken...",
        "The veil between worlds thins...",
        "Cultist activity increases..."
    ]
    
    event = random.choice(mythos_events)
    print(f"\n{event}")
    time.sleep(1.5)
    
    # Randomly determine mythos effects
    effects = []
    
    # 50% chance to advance doom
    if random.random() < 0.5:
        doom_track += 1
        effects.append(f"Doom advances to {doom_track}/{max_doom}")
    
    # 40% chance to spawn a gate
    if random.random() < 0.4:
        spawn_gate()
        effects.append("A gate opens somewhere in the world")
    
    # 30% chance to spawn clues
    if random.random() < 0.3:
        spawn_clues()
        effects.append("New clues appear")
    
    # If no effects, add a neutral one
    if not effects:
        effects.append("The world holds its breath... for now")
    
    # Display effects
    for effect in effects:
        print(f"\n> {effect}")
        time.sleep(1)
    
    input("\nPress Enter to continue to the next round...")
    
    # Move to next phase
    current_phase = "Action"

def spawn_gate():
    """Spawn a new gate at a random location."""
    # Filter locations without gates
    available_locations = [loc for loc, data in locations.items() if not data["has_gate"]]
    
    if available_locations:
        location = random.choice(available_locations)
        locations[location]["has_gate"] = True
        print(f"\nA gate tears open in {location}!")
    else:
        # All locations have gates - increase doom instead
        global doom_track
        doom_track += 1
        print("\nThe barriers between worlds weaken further...")

def spawn_clues():
    """Spawn new clues at random locations."""
    # Add 1-2 clues at random locations
    clue_count = random.randint(1, 2)
    
    for _ in range(clue_count):
        location = random.choice(list(locations.keys()))
        locations[location]["clues"] += 1

def skill_test(skill):
    """Perform a skill test and return number of successes."""
    skill_value = investigator["skills"][skill]
    print(f"\nPerforming a {skill.capitalize()} test (skill value: {skill_value})...")
    
    # Roll dice equal to skill value
    successes = 0
    rolls = []
    
    for _ in range(skill_value):
        roll = random.randint(1, 6)
        rolls.append(roll)
        if roll >= 5:  # 5-6 is a success
            successes += 1
    
    # Display rolls
    print(f"Rolls: {rolls}")
    print(f"Successes: {successes}")
    
    return successes

def show_victory_screen():
    """Display the victory screen."""
    clear_screen()
    print("\n" + "=" * 80)
    print("                                VICTORY")
    print("=" * 80)
    print("\nYou have successfully solved three mysteries and averted the apocalypse!")
    print("\nThe Ancient One stirs in its slumber but remains bound for another age.")
    print("\nFor now, humanity is safe... but for how long?")
    print("\n" + "=" * 80)
    
    input("\nPress Enter to return to the main menu...")
    show_main_menu()

def show_defeat_screen(reason):
    """Display the defeat screen."""
    clear_screen()
    print("\n" + "=" * 80)
    print("                                 DEFEAT")
    print("=" * 80)
    print(f"\n{reason}")
    print("\nThe Ancient One stirs and the world trembles before its power.")
    print("\nDarkness falls across the Earth as humanity faces its final hour.")
    print("\n" + "=" * 80)
    
    input("\nPress Enter to return to the main menu...")
    show_main_menu()

# Start the game
if __name__ == "__main__":
    show_main_menu()