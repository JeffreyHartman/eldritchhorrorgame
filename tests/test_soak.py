"""Bots play whole games. Every game must end, never crash, and keep the state valid."""

from __future__ import annotations

import pytest

from conftest import check_invariants
from pursuit.bots import HeuristicBot, RandomBot
from pursuit.content.loader import Content
from pursuit.controller import Controller
from pursuit.engine import phases
from pursuit.engine.setup import GameConfig, new_game

ROUND_LIMIT = 60


def play_checked(content: Content, config: GameConfig, ctl: Controller) -> str:
    game = new_game(content, config, ctl)
    check_invariants(game)
    while game.outcome is None:
        phases.step(game)
        check_invariants(game)
        assert game.round <= ROUND_LIMIT, f"seed {config.seed} did not end"
    assert game.outcome in ("win", "loss")
    return game.outcome


CASES = [
    (old, players, seed)
    for seed, (old, players) in enumerate(
        [(o, p) for o in ("azathoth", "yog_sothoth", "shub_niggurath", "cthulhu") for p in (1, 2, 3, 4)]
    )
]


@pytest.mark.parametrize(("old_one", "players", "seed"), CASES)
def test_random_bot_games_end_cleanly(content: Content, old_one: str, players: int, seed: int) -> None:
    roster = sorted(content.investigators)
    picks = tuple(roster[(seed + i * 3) % len(roster)] for i in range(players))
    difficulty = ("easy", "normal", "hard")[seed % 3]
    play_checked(content, GameConfig(old_one, picks, difficulty, seed), RandomBot(seed))


@pytest.mark.parametrize("seed", range(8))
def test_heuristic_bot_games_end_cleanly(content: Content, seed: int) -> None:
    old = sorted(content.old_ones)[seed % len(content.old_ones)]
    roster = sorted(content.investigators)
    picks = (roster[seed % len(roster)], roster[(seed + 5) % len(roster)])
    play_checked(content, GameConfig(old, picks, "normal", 1000 + seed), HeuristicBot(seed))


@pytest.mark.soak
@pytest.mark.parametrize("seed", range(200))
def test_long_random_soak(content: Content, seed: int) -> None:
    """Run with: uv run pytest -m soak"""
    roster = sorted(content.investigators)
    old = sorted(content.old_ones)[seed % 4]
    players = 1 + seed % 4
    picks = tuple(roster[(seed * 7 + i) % len(roster)] for i in range(players))
    play_checked(content, GameConfig(old, picks, "normal", 5000 + seed), RandomBot(seed))
