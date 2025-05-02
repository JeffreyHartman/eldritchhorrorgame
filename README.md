# Eldritch Pursuit

A text-based implementation of an Eldritch Horror-inspired board game, where players take on the role of investigators trying to solve mysteries before ancient cosmic horrors awaken.

## Project Goals

- Create a faithful digital adaptation of the Eldritch Horror board game experience
- Implement a text-based UI with rich formatting for an immersive experience
- Provide a challenging single-player experience with replayability
- Maintain the thematic elements and strategic depth of the original game

## Features Checklist

### Core Game Structure

- [x] Game engine with phase-based gameplay
- [x] Main menu and basic UI
- [x] Win/loss conditions\
- [ ] Implement action phase
  - [x] Travel between locations
  - [x] Rest action
  - [ ] Trade action
  - [x] Prepare for travel action
  - [ ] Acquire assets action
  - [ ] Perform component action
- [ ] Implement encouter phase
  - [x] Resolve encounters
  - [ ] Handle defeated investigators
- [ ] Implement mythos phase

### Game Components

- [x] Location system with connections
- [x] Train and ship ticket system
- [ ] Investigators
  - [x] Investigator class
  - [ ] Multiple investigators
  - [ ] Investigator selection
- [ ] Assets
  - [ ] Asset system
  - [ ] Allies
  - [ ] Artifacts
  - [ ] Items
  - [ ] Spells
- [ ] Gates
- [ ] Monsters
- [ ] Ancient Ones
- [ ] Conditions
- [/] Encounter Decks
- [ ] Mysteries
- [ ] Mythos deck
- [ ] Clues
- [ ] Complete world map visualization

### Investigator Features

- [ ] Investigator stats (health, sanity, skills)
- [x] Basic actions (travel, rest, prepare for travel)
- [ ] Multiple investigator options
- [ ] Character progression
- [ ] Inventory management

### Game Mechanics

- [x] Location movement mechanics
- [ ] Game setup
- [x] Skill tests
- [ ] Combat system
- [ ] Spell casting
- [ ] Item usage
- [ ] Gate mechanics
- [ ] Monster movement and encounters

### Technical Features

- [ ] Save/load game functionality
- [ ] Configuration options
- [ ] Difficulty settings
- [ ] Game statistics tracking

## Getting Started

1. Clone the repository
2. Install requirements: `pip install -r requirements.txt`
3. Run the game: `python main.py`
