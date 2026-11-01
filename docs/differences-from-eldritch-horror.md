# Differences from Eldritch Horror

This file records how the game compares to the Eldritch Horror base game.

Sources:

- `eh01_rulebook.pdf` (the rulebook).
- The Eldritch Horror Fandom wiki, through `scripts/sync_wiki.py`, for card text.

The Reference Guide was not available for this check. Rules that only the Reference Guide
gives are not confirmed against it, and that includes the difficulty options in `rules.json`.

## Systems that match

| System | What the game does |
| --- | --- |
| Round | Action, Encounter, and Mythos Phases, with the Lead Investigator pass at the end |
| Actions | 2 actions each round, and each action once per round |
| Tests | 5 and 6 are successes, the highest bonus applies, and each test rolls at least 1 die |
| Clue rerolls | Allowed on every die. The game offers extra rerolls only when more successes count |
| Mythos | Seven icon steps in rulebook order. An Ongoing card enters play at the last step |
| Omen and Doom | Four-space Omen track. Matching Gates advance Doom |
| Combat | Will test, then Strength test, with all Monster text on hook lists in `MonsterDef` |
| Reckoning | Rulebook order. Each Monster effect applies to that Monster only |
| Epic Monsters | Cannot be moved or discarded. A defeated Epic Monster leaves the game |
| Cultists | Stats come from the side of the Ancient One sheet that is faceup |
| Defeat | An investigator defeated after the awakening is eliminated. One whose defeat causes it is not |
| Ancient Ones | Setup, Reckoning, awakening, and Final Mystery follow the sheet text |
| Mysteries | All 16 Core Mysteries follow the card text and solve at the end of the Mythos Phase |
| Final Mysteries | They solve at once. Yog-Sothoth and Cthulhu wait for 3 solved Mysteries, as the sheets say |
| Special Encounters | 6 cards for R'lyeh Risen and 6 for The Key and the Gate |

The game follows the wiki for one conflict with the rulebook. The rulebook page 16 picture
shows Shub-Niggurath spawning on a random space. The wiki gives The Heart of Africa as the
printed text, so the game uses The Heart of Africa.

## Known gaps

### Components

| Component | Rulebook | Game |
| --- | --- | --- |
| Mythos cards | 51 (18 green, 21 yellow, 12 blue) | 23 (10, 9, 4) |
| Gate spaces | 9 | 12 |
| Asset cards | 40 | 58 |
| Artifacts | 14 | 7 |
| Spells | 20 | 19 |

The game draws a world when a Gate spawns, and uses nine small Other World decks. The
rulebook uses one 24-card deck. The total of 24 cards matches.

### Mythos cards

- Patrolling the Border: the Delayed effect at entry is missing.
- Buying Information: gives 2 Clues, not the test result.
- The Wind-Walker: deals 3 Health. The card says 6. It also has a Lore encounter that is not
  in the card text.
- The Wind-Walker and Web Between Worlds: defeating the Epic Monster does not solve the Rumor.
- Mysterious Lights: "Gates cannot be closed" has no code.
- Driven to Bankruptcy: the reserve refills at once. The card forbids this.
- Web Between Worlds: the option to spend Clues at Reckoning is missing.
- Legitimate Banking: the Debt back is random. The card treats all die rolls as 1's.

### Conditions

- Injury and Madness: the Rest roll that discards the card has no code.
- Detained: blocks only Travel and Prepare for Travel. The card blocks all other actions and
  replaces the encounter with a flip.
- A second Blessed or Cursed Condition gives no flip.

### Investigators and Assets

- Silas Marsh has 7 Health and 5 Sanity. The rulebook page 8 shows 8 and 4.
- Lily Chen's action moves 1 point. The card says any number.
- Arcane Tome: the Rest test uses Lore -1, and the data adds an action that is not on the card.
- The Axe rerolls all failed dice. The card lets the player choose the dice.

### Simplifications

- A space holds 1 Clue token. When a Mystery moves Clues, each Clue goes to the nearest
  matching space that has no Clue.
- The Dunwich Horror Prelude text has no effect, because the game has no Preludes.
- If no Gate can spawn, nothing happens. The wiki says that Doom advances by 1.

## Wiki sync

Monster `text` in `monsters.json` also holds the spawn and Reckoning text, so the UI can show
it. `scripts/sync_wiki.py --apply` compares only the special abilities field, and it removes
that text. Do not apply the `monsters.json` text changes from that report.

## Bot results

`HeuristicBot` almost never wins. The bot won 0 of 240 games at 3 investigators on the final
data, and 4 of 240 before the rebuild. It spends Clues on rerolls and solves about 0.1 Mysteries
each game. These numbers measure the bot and do not measure game balance.
