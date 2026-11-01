# Matching Eldritch Horror: encounters and monster stats

Status: implemented. Monster stats and test flags come from the wiki templates, the
encounter decks hold one card per physical card, Location and General cards use sections,
and each Gate is paired with one of the nine Other Worlds. The Core Special Encounters are in
`special_cthulhu.json` and `special_yog_sothoth.json`.

## Monster stats

The wiki monster templates carry the full stat line, so this is mechanical. The current
data differs for almost every monster that ships:

| Monster | Current horror / damage / toughness | Wiki horror / damage / toughness |
| --- | --- | --- |
| Ghoul | 1, Will +0 / 2, Str +0 / 2 | 1, Will +1 / 2, Str +0 / 1 |
| Goat Spawn | 1, Will -1 / 2, Str +0 / 2 | 1, Will +0 / 2, Str -2 / 2 |
| Dark Young | 2, Will -1 / 3, Str -1 / 3 | 3, Will -1 / 3, Str -3 / 5 |
| Deep One | 1, Will +0 / 2, Str +0 / 2 | 2, Will +0 / 1, Str -1 / 2 |
| Star Spawn | 3, Will -1 / 3, Str -2 / 3 | 3, Will -1 / 3, Str -3 / 5 |
| Hound of Tindalos | 2, Will -1 / 2, Str -1 / 2 | 2, Will +0 / 3, Str -1 / 3 |
| Byakhee | 1, Will +0 / 2, Str +0 / 2 | matches |
| Mi-go | 1, Will -1 / 1, Str +0 / 2 | 1, Will +0 / 2, Str -2 / 3 |
| Nightgaunt | 1, Will -1 / 1, Str +0 / 2 | 2, Will +0 / 1, Str -2 / 2 |
| Chthonian | 2, Will -1 / 3, Str -1 / 3 | 2, Will -1 / 3, Str -2 / 4 |
| Vampire | 1, Will +0 / 2, Str -1 / 2 | 1, Will +0 / 2, Str -2 / 3 |
| Warlock | 1, Will -1 / 1, Str -2 / 2 | 1, Will +0 / 1, Str -1 / 1 |
| Zombie | 1, Will +0 / 2, Str +0 / 3 | 1, Will +0 / 2, Str -1 / 2 |
| Shoggoth | 2, Will -1 / 3, Str -1 / 3 | 3, Will +0 / 2, Str -2 / 4 |
| Wind-Walker | 2, Will -1 / 3, Str -1 / 4 | 2, Will +0 / 2, Str -2 / N+2 |
| Shub-Niggurath (epic) | 3, Will -2 / 3, Str -2 / 3+1/inv | 4, Will -1 / 5, Str -3 / N+3 |
| Cthulhu (epic) | 3, Will -2 / 3, Str -2 / 3+1/inv | 5, Will -2 / 4, Str -2 / N+3 |
| Nug, Cthylla, Spinner of Webs | approximate, already close | see templates |
| Men from Leng, Dagon Priest | invented | no Core Game page, delete |

Mapping into this engine:

- `horror_value` becomes `horror`.
- The modifier in `horror_test` (`Will - 1`) becomes `horror_mod`; `Will + 1` is `+1`.
- `damage_value` becomes `damage`; the modifier in `damage_test` becomes `fight_mod`.
- `toughness_value` of `investigators + N` becomes `toughness = N`, `toughness_per_investigator = 1`.
- Flat toughness (`5`) becomes `toughness = 5`, `toughness_per_investigator = 0`.

Two modelling gaps to fix first:

1. Some monsters have a horror test with value 0 (`Witch`, `Cultist` variants). `combat.py`
   skips the Will test when `horror == 0`, so the test disappears. Add a `horror_test`
   boolean to `MonsterDef` and gate on that instead.
2. Some have no damage test (Cultist under Azathoth, `Colour Out of Space`, `Ghost`).
   Add a `damage_test` boolean, and let combat skip the Strength test and wounds.

Missing Core monsters to add (all have wiki pages, none ship today): Colour Out of Space,
Elder Thing, Ghost, Gnoph-Keh, Gug, Lloigor, Maniac, Mummy, Riot, Serpent People, Skeleton,
Witch, Wraith, Zombie Horde, Tick Tock Men.

Counts (how many copies go in the cup) are not in the monster template. Take them from the
game components list or the physical box, not from the wiki infobox.

Plan:

1. Add `horror_test` and `damage_test` to `MonsterDef` and `combat.py`, plus `monster_panel`.
2. Extend `scripts/sync_wiki.py` with `--apply-stats` that writes the four stat fields and
   the two booleans from the templates (same template cache as the prose sync).
3. Add the missing monsters and delete the two invented ones.
4. Re-baseline the soak suite, since the cup and every fight change.

Tests that hard-code stats and must be updated: `tests/test_dice_and_combat.py` (ghoul,
star spawn, cultist, cthylla), `tests/test_phases.py` (zombie), `tests/test_rules.py`
(goat spawn roaming, monster surge).

## Encounters

The real Core Game decks are much larger than the current data, and each Location and
General card carries three sections, one per space type or named city:

| Deck | Core cards | Shape |
| --- | --- | --- |
| Americas, Europe, Asia/Australia | 8 each | one card, three city sections |
| General | 12 | one card, city / wilderness / sea sections |
| Expedition | 18 | one card per location, initial / pass / fail text |
| Research | 24 per Ancient One | one card per terrain |
| Other World | about 24 across 9 types | one card per type, pass / fail text |

The current `EncounterDef` holds one `text` and one `effects` list, so it cannot represent
the three sections of a Location or General card.

### Schema change

Add an optional `sections` list to `EncounterDef`, and keep `text` / `effects` for decks
whose cards really are single-section (expedition, research, other world):

```json
{
  "id": "americas_3",
  "deck": "americas",
  "title": "Call of the Chthonian",
  "sections": [
    {"location": "arkham", "text": "...", "effects": []},
    {"location": "san_francisco", "text": "...", "effects": []},
    {"location": "buenos_aires", "text": "...", "effects": []}
  ]
}
```

General cards use `terrain` instead of `location` in each section.

Changes:

- `content/defs.py`: add `EncounterSection` and `EncounterDef.sections`.
- `content/loader.py`: parse sections, and in `_Checker.check_encounters` validate section
  locations and terrains.
- `engine/phases.py`, `_draw_and_run_encounter`: pick the section matching
  `inv.location` (or the location's terrain for general) before running effects. The
  general deck no longer needs `draw_where` terrain filtering.
- The deck keeps one entry per physical card, so reshuffles, discards, and odds stay right.
  Splitting each card into three JSON entries would inflate the deck and is not the plan.

### Other World

The real game pairs each Gate with one of nine Other Worlds. The current model only stores
a map location, and `encounter_turn` draws from one shared `other_world` deck. To match:

- Draw an Other World type when a Gate spawns and store it on `LocationState` (this changes
  the save format, so bump `SAVE_VERSION`).
- Build one encounter deck per Other World (`other_world_yuggoth`, ...) and draw from the
  type on the Gate's space.
- Until then, the shared deck can be kept as a documented simplification.

### Effect vocabulary

Most encounter prose maps to existing effects (`test`, `pay`, `choice`, `move`, `ambush`,
`gain_condition`, `close_gate`, `spawn_clue`, `improve_skill`). These few need new effects:

- `discard_monster`: choose one, or discard all on a space.
- `recover_all`: refill Health and/or Sanity.
- `nearest_terrain`: move to the nearest city, wilderness, or sea space.
- `remove_any_condition`: discard a Condition without naming it.
- `move_monster_here`: move a chosen non-epic Monster to this space and encounter it.

### Work order

1. **Research encounters** (96 cards): no schema change, one card per terrain. Replace the
   four `research_*.json` files and author effects.
2. **Expedition encounters** (18 cards): no schema change. Replace `expedition.json`.
3. **General encounters** (12 cards): add `sections`, then replace `general.json`.
4. **Location encounters** (24 cards, 72 sections): add `sections`, then replace the three
   region files.
5. **Other World encounters**: add gate-to-Other-World mapping, then the per-type decks.
6. **Special, mystery, and rumor encounters** last; they are referenced by Mysteries and
   need per-card wiring.

Each step: extend the wiki script to emit a skeleton (title, section text, empty `effects`)
from the parsed tables, fill in effects by hand, then run `pytest` and a short soak.

### Test impact

- `tests/test_content.py::test_every_encounter_resolves_without_error` covers every new
  effect automatically.
- `tests/test_phases.py` expects deck names and draw counts; update for section selection.
- `tests/test_soak.py` runs whole games, so it is the safety net for the new effects.

## Resuming after a context reset

```sh
python scripts/sync_wiki.py --offline          # verify prose is still in sync
python scripts/sync_wiki.py --apply-stats      # after that flag exists
uv run pytest && uv run pytest -m soak
```

Start with the Research decks: they need no schema change, and they exercise the effect
additions that the later decks reuse.
