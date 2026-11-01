# Differences from Eldritch Horror

This file records how the game compares to the Eldritch Horror base game.

Sources:

- `eh01_rulebook.pdf` (the rulebook).
- `EH01 Reference Guide.pdf` (the Reference Guide). The guide overrules the rulebook.
- The Eldritch Horror Fandom wiki, through `scripts/sync_wiki.py`, for card text.

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
| Components | 51 Mythos cards, 9 Gates, 40 Assets, 14 Artifacts, 20 Spells, and 1 Other World deck of 24 cards |
| Encounters | All 186 cards in 12 decks follow the wiki text. Each pass and fail line is an effect, and `tests/test_card_text.py` checks the wording |
| Mythos cards | All 51 cards follow the wiki text, including the Rumor and Ongoing rules |
| Assets and Artifacts | Each card follows the wiki text, and each Asset has 1 copy |
| Conditions | All 11 Conditions use the wiki Reckoning text and the Core back of each card |
| Difficulty | Easy removes hard Mythos cards and Hard removes easy Mythos cards. Doom does not change |
| Solo game | One investigator removes the cards with the Teamwork trait |
| Spells | Each of the 20 cards has its own Core back. Triggers, chosen targets, and result lines follow the wiki |
| Investigators | Stats, starting possessions, abilities, and Defeated Encounters follow the wiki |
| Optional rules | The Starting Rumor option and the Reference Guide score |

The game follows the wiki for one conflict with the rulebook. The rulebook page 16 picture
shows Shub-Niggurath spawning on a random space. The wiki gives The Heart of Africa as the
printed text, so the game uses The Heart of Africa.

The wiki does not list the icons of each Mythos card, so the game uses these rules:

- Yellow cards: Advance Omen, Reckoning, and Spawn Gates. The wiki Gate page gives this.
- Green cards: Advance Omen, Monster Surge, and Spawn Clues. The From Beyond page gives this.
- Blue cards: Spawn Clues, and the Rumor and Eldritch icons from each wiki page. The Reference
  Guide mentions the Spawn Clues icon on Rumors.

The wiki lists no starting travel tickets for any investigator, so no investigator starts with
one.

Norman Withers can use Sanity in place of a Clue on a cost or a Clue reroll. Other Clue spends,
such as a group spend, take only Clues.

Conjuration can gain cards from both its test line and its back line, because the card does
not say "instead".

The Reference Guide does not say that The Silver Key applies to a Clue reroll, so the
discount applies only to a Clue cost.

"Gain a Madness Condition" and "gain an Injury Condition" give a random matching Condition
that the investigator does not have. The rulebook does not say who picks.

A "you may" or "unless" cost that the investigator cannot pay is not offered. An investigator
who is already Delayed cannot "become Delayed" to pay a cost, and one who already holds a
Condition cannot gain it to pay a cost. Each such option stays disabled.

If a card ambushes with a named Monster and no such Monster is available, no combat occurs and
neither the "defeat it" branch nor the "do not defeat it" branch resolves. Only
`research_shub_niggurath_wilderness_2` prints a fallback to a random Monster.

## Known gaps

### Simplifications

- The Dunwich Horror Prelude text has no effect, because the game has no Preludes.
- The Rest roll for an Injury or Madness Condition always occurs, because it has no downside.
- A Rumor Epic Monster stays on the board if its Rumor ends with no Eldritch tokens.

## Wiki sync

Monster `text` in `monsters.json` also holds the spawn and Reckoning text, so the UI can show
it. `scripts/sync_wiki.py --apply` compares only the special abilities field, and it removes
that text. Do not apply the `monsters.json` text changes from that report.

## Bot results

`HeuristicBot` almost never wins. The bot won 0 of 240 games at 3 investigators on the final
data. It spends Clues on rerolls and solves few Mysteries. These numbers measure the bot and
do not measure game balance.
