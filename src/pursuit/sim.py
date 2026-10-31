"""Run many bot games and print win rates. Use it to find crashes and to check balance.

Example: uv run python -m pursuit.sim --games 200 --bot heuristic --players 2
"""

from __future__ import annotations

import argparse
import random
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field

from pursuit.bots import HeuristicBot, RandomBot
from pursuit.content.loader import Content, load_content
from pursuit.engine.phases import play
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import Game

# A game that runs past this many rounds has a rules bug that stops it from ending.
MAX_ROUNDS = 60


@dataclass
class SimResult:
    games: int = 0
    wins: int = 0
    rounds: list[int] = field(default_factory=list)
    reasons: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0


class RoundLimit(Exception):
    pass


def run_one(
    content: Content, seed: int, *, bot: str, players: int, old_one: str | None, difficulty: str
) -> tuple[str, int, str]:
    rng = random.Random(seed)
    roster = sorted(content.investigators)
    investigators = tuple(rng.sample(roster, players))
    target = old_one or rng.choice(sorted(content.old_ones))
    ctl = HeuristicBot(seed) if bot == "heuristic" else RandomBot(seed)
    game = new_game(content, GameConfig(target, investigators, difficulty, seed), ctl)
    original_step = game.ctl.checkpoint

    def guard(g: Game) -> None:
        if game.round > MAX_ROUNDS:
            raise RoundLimit(f"seed {seed}: still running after {MAX_ROUNDS} rounds")
        original_step(game)

    game.ctl.checkpoint = guard  # type: ignore[method-assign, assignment]
    outcome = play(game)
    return outcome, game.round, game.outcome_reason


def simulate(
    games: int,
    *,
    bot: str = "heuristic",
    players: int = 2,
    old_one: str | None = None,
    difficulty: str = "normal",
    seed: int = 0,
) -> SimResult:
    content = load_content()
    result = SimResult()
    for i in range(games):
        s = seed + i
        try:
            outcome, rounds, reason = run_one(
                content, s, bot=bot, players=players, old_one=old_one, difficulty=difficulty
            )
        except Exception:
            result.errors.append(f"seed {s}:\n{traceback.format_exc()}")
            continue
        result.games += 1
        result.wins += outcome == "win"
        result.rounds.append(rounds)
        result.reasons[reason.split(".")[0]] += 1
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--bot", choices=("heuristic", "random"), default="heuristic")
    parser.add_argument("--players", type=int, default=2)
    parser.add_argument("--old-one", default=None)
    parser.add_argument("--difficulty", default="normal")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    res = simulate(
        args.games, bot=args.bot, players=args.players, old_one=args.old_one, difficulty=args.difficulty, seed=args.seed
    )
    avg = sum(res.rounds) / len(res.rounds) if res.rounds else 0
    print(f"games {res.games}  wins {res.wins}  win rate {res.win_rate:.0%}  average rounds {avg:.1f}")
    for reason, count in res.reasons.most_common():
        print(f"  {count:4d}  {reason}")
    if res.errors:
        print(f"\n{len(res.errors)} game(s) crashed. First crash:\n{res.errors[0]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
