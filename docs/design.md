# Eldritch Pursuit: design

This document has three parts:

1. The rules of the game.
2. The structure of the code.
3. The content files and the effect types that they use.

All numbers in the rules come from `src/pursuit/data/rules.json` and the Old One files. If you
change the data, the numbers here can become out of date.

## 1. Rules

### Setup

1. The player chooses an Old One, a difficulty, and 1 to 4 investigators.
2. Doom starts at the Old One's `doom` value plus the difficulty's `doom_mod`.
3. The game picks `rites_needed` rites (3) at random from the Old One's 5 rites.
4. Two rifts open at random rift sites. Each new rift brings a monster.
5. Four Clues appear at random locations that are not at sea.
6. Each investigator starts at their start location with their own assets, Funds, and Clues.
7. The market shows 4 assets.

### Investigators

An investigator has Health, Sanity, Funds, Clues, Trophies, and five skills:

| Skill | Used for                                         |
| ----- | ------------------------------------------------ |
| Lore  | sealing rifts, spells, and occult rites          |
| Charm | raising funds and talking                         |
| Wits  | investigating, evading, and noticing things      |
| Brawn | fighting                                         |
| Nerve | horror checks and resisting madness              |

An effect can improve a skill by +1, up to +2 over the printed value. Each investigator also has a
passive perk, an optional action ability, or both.

### Skill tests

A test rolls a number of six-sided dice equal to the skill, plus modifiers from assets and
conditions. Each 5 or 6 is one success. A test always rolls at least 1 die.

Before the roll, the player can use **boosts**. A boost adds dice for a cost, for example 1 Sanity,
discarding the asset, or exhausting it until the next round.

After the roll, if the test failed, the player can spend 1 Clue to reroll **every** failed die. The
player can do this again while they still have Clues.

### A round

Each round has three phases in this order.

#### Day

Each investigator takes a turn. On a turn, an investigator can take 2 actions. Each action works only
once per round.

| Action           | Rule                                                                                      |
| ---------------- | ----------------------------------------------------------------------------------------- |
| Travel           | Move 1 step on any route. Then move up to 2 more steps by rail or sea for 1 Funds each.    |
| Rest             | Recover 1 Health and 1 Sanity. Not possible if monsters are at the location.              |
| Investigate      | Test Wits. On a pass, take the Clue at the location.                                      |
| Seal the rift    | Test Lore. On a pass, close the rift and gain 1 Trophy. On a fail, lose 1 Sanity.         |
| Raise funds      | Only in a city. Test Charm. Gain 1 Funds plus 1 for each success.                          |
| Perform rite     | Give Clues, Funds, Trophies, or a relic to a rite, or test a skill for it.                |
| Use an asset     | Use the action of an asset. The asset exhausts until the next round.                      |
| Use your ability | Use the investigator's own action ability.                                                |
| Deal with ...    | Pay or test to remove a condition that has a cure.                                        |

These actions are free and can repeat:

- **Visit the market.** Only in a city. Buy assets at their price in Funds.
- **Trade.** Swap assets, Funds, or Clues with another investigator at the same location.
- **Collect belongings.** Take the assets that a defeated investigator left at the location.

#### Encounters

Each investigator does these steps in order:

1. **Combat.** The investigator faces each monster at the location, one at a time.
   1. If the monster has horror, test Nerve. On a fail, lose Sanity equal to its horror value.
   2. Choose Fight or Evade.
      - **Fight:** test Brawn. Each success is 1 wound. If the wounds reach the monster's
        toughness, the monster dies. If not, it strikes for its full damage.
      - **Evade:** test Wits. On a pass, the investigator slips away. On a fail, the monster strikes.
   3. Wounds stay on a monster. Investigators can wear down a tough monster over several rounds.
2. **Encounter.** If no monster struck the investigator, they choose one encounter:
   - **Explore the location.** Draw from the terrain deck (city, wilderness, or sea). A hub city
     (Providence, Rio de Janeiro, Paris, Cairo, Bombay, Peking) has its own deck.
   - **Step through the rift.** Only where a rift is open. These encounters are dangerous, but
     some of them seal the rift.

#### Night

These steps occur in order:

1. Doom advances by 1. If 4 or more rifts are open, Doom advances by 1 more.
2. A portent card resolves at the current Dread level.
3. The Old One acts (its night effect).
4. Each condition with a night trigger rolls a die. If the roll is equal to or less than its chance,
   the condition comes due.
5. The oldest market card goes away, and a new card replaces it.
6. A new round starts. Actions and exhausted assets reset.

### Doom, Dread, and portents

Doom counts down. Each Old One has two Dread thresholds in `dread_at`, for example `[10, 5]`.

| Doom                     | Dread |
| ------------------------ | ----- |
| above the first value    | 1     |
| at or below the first    | 2     |
| at or below the second   | 3     |
| after the Old One wakes  | 3     |

Dread never goes down, even if Doom retreats.

The portent deck controls how the difficulty rises:

- Each portent has one effect tier for each Dread level from its `min_dread` up to 3. When a
  portent resolves, it uses the tier for the current Dread.
- At the start, the deck holds only the portents with `min_dread` 1.
- When Dread rises to 2, the game shuffles the `min_dread` 2 portents into the deck. At Dread 3, it
  adds the `min_dread` 3 portents.

The result is that the same card becomes worse over time, and new, worse cards join the deck.

### Rifts

- When a rift opens at a location that has no rift, a monster appears there.
- When a rift opens at a location that already has a rift, the rift **widens**. A monster
  appears and Doom advances by 1.
- To close a rift, use the Seal action, an encounter, or an effect. The investigator gains 1 Trophy.
- Some Old Ones have a `rift_limit`. If that many rifts are open at the same time, the investigators
  lose.

### Conditions

A condition shows its name, its rules text, and its modifiers. Its **outcome** stays hidden until it
comes due.

Each condition has a trigger:

| Trigger     | When it comes due                                       |
| ----------- | ------------------------------------------------------- |
| `night`     | Each Night, on a die roll of `chance` or less            |
| `rest`      | When the investigator rests                              |
| `encounter` | After the investigator's next encounter                  |
| `never`     | Only when an effect resolves it                          |

When a condition comes due, the game picks one of its outcomes at random, by weight. An outcome can
hurt, help, or remove the condition. A condition can also block actions (for example, Wanted blocks
Raise funds and the market) or have a cure action.

### Rites and winning

Each Old One has 5 rites. The game uses 3 of them. There are four kinds:

| Kind    | How investigators complete it                                              |
| ------- | -------------------------------------------------------------------------- |
| `spend` | Give Clues, Funds, Trophies, or relics at the right place                  |
| `test`  | Test a skill at the right place. Successes add progress                    |
| `seal`  | Close rifts, sometimes only in one region                                  |
| `defeat`| Kill an epic monster that the rite places on the map                       |

Many rites need more progress for each investigator in the game. Epic monsters also have more
toughness for each investigator.

The investigators win when all of the chosen rites are complete.

### Awakening and losing

When Doom reaches 0, the Old One wakes:

1. Dread goes to 3.
2. One final rite becomes active. The normal rites no longer matter.
3. An endgame clock starts at the Old One's `nights` value. Anything that advances Doom now takes
   nights off the clock.
4. The Old One's night effect changes to a stronger one.

The investigators win if they complete the final rite. They lose if the clock reaches 0.

When an investigator reaches 0 Health or 0 Sanity, they are defeated:

1. Their assets stay at the location as belongings.
2. Before the awakening, Doom advances by 1, and the player chooses a new investigator. The new
   investigator acts from the next round.
3. After the awakening, or if no unused investigators remain, the investigator is eliminated.

The investigators lose if all of them are eliminated, if the clock runs out, or if the rift limit is
reached.

### Difficulty

| Difficulty | Doom | Funds per investigator | Rifts at the start |
| ---------- | ---- | ---------------------- | ------------------ |
| Easy       | +3   | +1                     | -1                 |
| Normal     | 0    | 0                      | 0                  |
| Hard       | -2   | -1                     | +1                 |

## 2. Code

### Packages

| Package             | Job                                                                       |
| ------------------- | ------------------------------------------------------------------------- |
| `pursuit.content`   | Reads JSON into frozen dataclasses and checks every cross-reference.      |
| `pursuit.effects`   | The effect registry and all effect types.                                 |
| `pursuit.engine`    | Game state, rules, dice, combat, actions, phases, setup, and save files.  |
| `pursuit.ui`        | The `rich` terminal UI, the renderers, and the ASCII art.                 |
| `pursuit.bots`      | `RandomBot` and `HeuristicBot`.                                           |
| `pursuit.sim`       | A command that runs many bot games and prints win rates.                  |

### The engine does no input or output

The engine never prints and never reads the keyboard. When it needs a decision, it calls the
`Controller` protocol in `pursuit/controller.py`:

| Method       | Use                                                                   |
| ------------ | --------------------------------------------------------------------- |
| `choose`     | Pick one `Option` from a list. Each option has a `kind`, for example `travel` or `combat`. |
| `confirm`    | Answer yes or no, for example to use a boost or reroll.              |
| `notify`     | Receive an `Event`, for example a dice roll, a portent, or a defeat. |
| `checkpoint` | Called before each Day turn. The terminal UI saves the game here.    |

Four controllers use this protocol:

- `TerminalController` shows menus and art and reads keys.
- `Script` in `tests/conftest.py` gives answers that a test sets in advance.
- `RandomBot` picks random valid options.
- `HeuristicBot` plays with simple goals. The balance numbers come from this bot.

Because all controllers use the same engine, a bot game runs the same code as a human game.

### Game state

`engine/state.py` holds all mutable state in plain dataclasses: `Game`, `Investigator`,
`LocationState`, `MonsterInst`, `AssetCard`, `ConditionInst`, `RiteState`, and a generic `Deck`.
The state refers to content by id. It never copies the content.

All randomness goes through `game.rng`, which is a seeded `random.Random`. The same seed and the same
choices give the same game. Tests replace `game.roll` to set the dice.

### The round loop

`engine/phases.py` runs the game. `step()` runs one phase. `play()` calls `step()` until the game
has an outcome. The phase and the turn index are part of the state, so a loaded save continues at
the same investigator's Day turn.

### Effects

Content describes what happens as a list of effects. Each effect type is a small frozen dataclass
in `effects/library.py` with the `@register("name")` decorator. Each type has:

- `parse(reader)` to read its JSON and reject bad fields.
- `apply(ctx)` to change the game.
- `children()` so that checks can walk nested effects.
- `refs()` to list the ids of other content that it uses.
- `needs_investigator()` to tell if it needs a current investigator.

`Ctx` carries the game, the current investigator (or `None`), the source, and the condition that
resolves (if any). If an investigator is defeated during a list of effects, the rest of the list
stops.

### Content checks

`content/loader.py` loads every file through `content/reader.py`. The `Reader` rejects unknown
fields, wrong types, and bad enum values. Each error names the file and the JSON path.

After the load, `_Checker` checks these items:

- Every route goes to a known location, and every location can reach every other location.
- Every id that an effect, an investigator, an asset, a rite, or an Old One uses exists.
- Each portent has the correct number of tiers for its `min_dread`.
- Each hub city has its own encounter deck, and each deck file has a valid name.
- Portents and Old One night effects do not use an investigator effect (for example, `health`)
  unless an `each_investigator` or `one_investigator` effect wraps it.

### Save files

`engine/save.py` writes the full state, including the RNG state, as JSON. It writes to a temporary
file and then renames it, so a crash cannot leave half a save. A load checks every id in the save
against the content. The file has a version number (`SAVE_VERSION`).

### UI

`ui/app.py` has the title screen, the main menu, the new game wizard, and the end screen.
`ui/terminal.py` has `TerminalController`. `ui/render.py` makes the `rich` panels, tables, the map,
and the dice. The ASCII art is in `ui/art/*.txt`.

### Tests

| File                       | What it tests                                                       |
| -------------------------- | ------------------------------------------------------------------- |
| `test_content.py`          | The shipped data loads. Broken data fails with a clear message. Every encounter, portent tier, Old One effect, ability, and condition outcome runs. |
| `test_dice_and_combat.py`  | Dice pools, boosts, rerolls, horror, fight, and evade.              |
| `test_actions.py`          | Each Day action and its limits.                                     |
| `test_effects.py`          | Each effect type, and bad effect data.                              |
| `test_encounter_choices.py` | Optional costs on encounter cards: accept, refuse, and cannot pay. |
| `test_rules.py`            | Doom, Dread, rifts, rites, defeats, and the awakening.              |
| `test_phases.py`           | The round loop and full games to a win and to a loss.               |
| `test_save.py`             | A save and a load give the same game, and bad saves fail clearly.   |
| `test_ui.py`               | The menus, the wizard, the views, and a random player through the UI. |
| `test_soak.py`             | Bot games end without a crash and keep the state valid.             |

`uv run pytest -m soak` runs 200 more full games.

## 3. Content

### Files

All files are in `src/pursuit/data/`. Any object can have a `_comment` key. The loader ignores it.

| File                      | Content                                                           |
| ------------------------- | ----------------------------------------------------------------- |
| `rules.json`              | Core numbers and difficulty levels                                |
| `map.json`                | Locations (id, code, name, terrain, region, position) and routes  |
| `investigators.json`      | Investigators                                                     |
| `old_ones.json`           | Old Ones, their rites, and their awakening                        |
| `assets.json`             | Items, allies, and services for the market                        |
| `spells.json`             | Spells                                                            |
| `relics.json`             | Relics                                                            |
| `conditions.json`         | Conditions                                                        |
| `monsters.json`           | Monsters and epic monsters                                        |
| `portents.json`           | Portents                                                          |
| `encounters/<deck>.json`  | One file per encounter deck: `city`, `wilderness`, `sea`, `rift`, and each hub city id |

### Example: an encounter

```json
{
  "id": "city_light_touch",
  "title": "A Light Touch",
  "text": "A boy in a cloth cap bumps into you in the crowd and keeps walking a little too fast.",
  "effects": [
    {
      "type": "test",
      "skill": "wits",
      "pass": [{"type": "clues", "amount": 1}],
      "fail": [{"type": "funds", "amount": -2}]
    }
  ]
}
```

### Example: a portent with tiers

```json
{
  "id": "veil_thins",
  "name": "The Veil Thins",
  "min_dread": 2,
  "flavor": "For an hour at midnight, you can see through walls into somewhere else.",
  "tiers": [
    {"text": "Two rifts open.", "effects": [{"type": "open_rift", "count": 2}]},
    {"text": "Two rifts open, and Doom advances by 1.",
     "effects": [{"type": "open_rift", "count": 2}, {"type": "advance_doom", "amount": 1}]}
  ]
}
```

`min_dread` 2 means two tiers: the first for Dread 2 and the second for Dread 3.

### Example: a condition with hidden outcomes

```json
{
  "id": "paranoia",
  "name": "Paranoia",
  "traits": ["madness"],
  "text": "They are watching. All of them. -1 Charm. Something may happen at night.",
  "modifiers": [{"amount": -1, "skill": "charm"}],
  "trigger": "night",
  "chance": 2,
  "outcomes": [
    {"weight": 1, "text": "You hide in your room for a day.", "effects": [{"type": "delay"}]},
    {"weight": 1, "text": "A long talk with a friend helps.", "effects": [{"type": "remove_self"}]}
  ],
  "cure": {"text": "Talk it through: test Nerve to discard it.", "skill": "nerve"}
}
```

### Effect types

Investigator effects apply to the current investigator. World effects need no investigator.

#### Investigator effects

| Type                 | Fields                                                    | Result                                             |
| -------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| `health`, `sanity`, `funds`, `clues`, `trophies` | `amount` (not 0)              | Change the value                                   |
| `improve_skill`      | `skill` (or `choose`), `amount`                           | Improve a skill, up to the cap                     |
| `test`               | `skill`, `mod`, `context`, `pass`, `fail`                 | Run a skill test, then one branch                  |
| `gain_asset`         | `id`, `kind`, or `trait`; `source` (`deck` or `market`); `count` | Gain assets                                  |
| `lose_asset`         | `id`, `kind`, `trait`, or `all`; `count`                  | Discard assets                                     |
| `gain_condition`     | `id`                                                      | Gain a condition                                   |
| `remove_condition`   | `id` or `trait`                                           | Remove conditions                                  |
| `remove_self`        | none                                                      | Remove the condition that resolves now             |
| `resolve_conditions` | `trait`                                                   | Make matching conditions come due now              |
| `move`               | `to` (location id, `nearest_city`, `random_city`, `start`, `choose_adjacent`, `nearest_rift`, `choose_within`), `range` | Move the investigator |
| `delay`              | `chosen`                                                  | The investigator loses the next Day turn. `chosen` marks a voluntary Delay, which perks cannot stop |
| `claim_clue`         | `bonus`                                                   | Gain the Clue token here, plus `bonus` Clues       |
| `discard_clue`       | none                                                      | Discard 1 Clue token here with no gain             |
| `choice`             | `prompt`, `options` (each with `label`, `requires`, `effects`) | The player picks one option. With one enabled option, it resolves with no prompt |
| `pay`                | `prompt`, `cost`, `then`, `else`                          | Offer to pay a cost                                |
| `if`                 | `has` (an investigator filter), `then`, `else`            | Branch on what the investigator has                |
| `ambush`             | `id`                                                      | Spawn a monster here and fight it now              |
| `close_rift`         | none                                                      | Close the rift here                                |

#### World effects

| Type                 | Fields                                                    | Result                                             |
| -------------------- | --------------------------------------------------------- | -------------------------------------------------- |
| `discard_gate`       | none                                                      | Discard 1 open Gate of the player's choice         |
| `text`               | `text`                                                    | Show text                                          |
| `advance_doom`, `retreat_doom` | `amount`                                        | Move Doom                                          |
| `random`             | `outcomes` (each with `weight`, `effects`)                | Pick one outcome by weight                         |
| `each_investigator`  | `where` (an investigator filter), `here`, `effects`       | Run effects for each matching investigator         |
| `one_investigator`   | `pick` (`lowest_sanity`, `lowest_health`, `most_clues`, `most_funds`, `random`, `choose`), `effects` | Run effects for one investigator |
| `open_rift`          | `count`                                                   | Open rifts from the rift deck                      |
| `spawn_monster`      | `count`, `id`, `at` (`here`, `rifts`, `random_rift_site`, or a location id) | Spawn monsters          |
| `spawn_clue`         | `count`                                                   | Place Clues                                        |
| `monsters_move`      | none                                                      | Each roaming monster moves 1 step toward the nearest investigator |
| `monsters_heal`      | none                                                      | Remove all wounds from monsters                    |
| `refresh_market`     | none                                                      | Replace the market cards                           |
| `rite_progress`      | `amount`                                                  | Add progress to an active rite                     |

#### Filters

A **location filter** has these optional fields: `id`, `terrain`, `region`, `hub`, `rift`, `clue`,
and `monsters`.

An **investigator filter** has these optional fields: `condition`, `condition_trait`, `asset`,
`asset_kind`, `asset_trait`, `funds_at_least`, `clues_at_least`, `trophies_at_least`,
`sanity_at_most`, `health_at_most`, `at` (a location filter), `alone`, and `delayed`.

### Add an Old One

1. Add an entry to `old_ones.json` with `doom`, `dread_at`, 5 `rites`, `rites_needed`, a `night`
   effect list, and an `awakening` with a `final_rite`.
2. If a rite has the kind `defeat`, add its epic monster to `monsters.json` with `"epic": true`.
3. Add a portrait to `src/pursuit/ui/art/<art>.txt`.
4. Run `uv run pytest`. The content tests run every effect of the new Old One.
5. Run `uv run python -m pursuit.sim --games 200 --old-one <id>` and compare the win rate with the
   other Old Ones.

### Balance

These are the win rates for `HeuristicBot` with 2 investigators on Normal. Each row is 200 games
with seeds 0 to 199.

| Old One            | Label  | Bot win rate | Average rounds |
| ------------------ | ------ | ------------ | -------------- |
| The King in Yellow | low    | 66%          | 12.2           |
| Cthulhu            | high   | 40%          | 13.1           |
| Yog-Sothoth        | medium | 36%          | 13.3           |
| Nyarlathotep       | medium | 40%          | 11.5           |

The bot plays simply. A human player usually wins more often.
