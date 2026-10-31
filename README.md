# Eldritch Pursuit

Eldritch Pursuit is a co-operative cosmic horror game for the terminal. You control a team of 1 to 4
investigators who travel a 1926 world map. They seal rifts, fight monsters, and perform rites before an
Old One wakes up and ends the world.

The game is a single-player, hot-seat game. All of the content (investigators, Old Ones, encounters,
assets, monsters, conditions, and portents) is in JSON files that you can edit.

## Requirements

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- A terminal that is at least 100 columns wide

## Play

```sh
uv run eldritch-pursuit
```

The main menu lets you start a new game, continue the last game, load a save, or read the rules.

### How a game goes

1. Choose an Old One, a difficulty, and 1 to 4 investigators.
2. Each round has three phases:
   - **Day.** Each investigator takes 2 different actions, for example Travel, Rest, Investigate,
     Seal the rift, Raise funds, or Perform rite. The market, trading, and collecting belongings
     are free.
   - **Encounters.** Each investigator fights or evades the monsters at their location. Then they
     have an encounter at that location, or they step through a rift there.
   - **Night.** Doom advances, a portent card resolves, the Old One acts, and conditions can come
     due.
3. You win when the investigators complete the Old One's rites.
4. If Doom reaches 0, the Old One wakes. You then have a few nights to complete one final rite.

The **How to play** screen in the game has the full rules. `docs/design.md` has the rules and the
design of the code.

### Keys

On the action menu, type the number of an option. These keys open views:

| Key | View                         |
| --- | ---------------------------- |
| `m` | World map                    |
| `i` | Investigators                |
| `r` | Rites and the Old One        |
| `k` | Market                       |
| `l` | Log of recent events         |
| `h` | Help                         |
| `s` | Save                         |
| `q` | Quit to the main menu        |

### Saves

The game saves automatically at the start of each Day turn. You can also save with `s`.
The saves go to `$XDG_DATA_HOME/eldritch-pursuit/saves` (usually `~/.local/share/eldritch-pursuit/saves`).
On Windows, they go to `%APPDATA%\eldritch-pursuit\saves`. To use a different folder, set
`PURSUIT_SAVES`.

## Content

The game data is in `src/pursuit/data/`. The game checks all of it when it starts. If a file has an
error, the game stops and shows the JSON path of the error, for example
`city.json[0].effects[1]: unknown effect type 'summon_cake'`.

To play with your own copy of the data, copy the folder and set `PURSUIT_DATA`:

```sh
cp -r src/pursuit/data ~/my-data
PURSUIT_DATA=~/my-data uv run eldritch-pursuit
```

`docs/design.md` describes each file and every effect type.

## Development

```sh
uv run pytest                     # unit, rules, UI, and short bot-game tests
uv run pytest -m soak             # 200 full games with random bots
uv run ruff check src tests       # lint
uv run ruff format src tests      # format
uv run mypy                       # type check
```

To measure balance, run bot games:

```sh
uv run python -m pursuit.sim --games 200 --bot heuristic --players 2 --old-one cthulhu
```

The command shows the win rate, the average number of rounds, and how the games ended.

## Layout

```
src/pursuit/
  content/     JSON reader, content definitions, loader, and cross-reference checks
  effects/     effect registry and every effect type that content can use
  engine/      game state, rules, dice, combat, actions, phases, setup, save and load
  ui/          rich terminal UI, renderers, and ASCII art
  data/        all game content as JSON
  bots.py      RandomBot and HeuristicBot controllers
  sim.py       bot game runner for balance checks
tests/         pytest suite
docs/          design document
```
