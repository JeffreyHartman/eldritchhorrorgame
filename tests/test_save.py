"""Tests for `engine.save`: a saved game loads back the same and plays on the same way."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest

from pursuit.bots import HeuristicBot
from pursuit.content.loader import Content
from pursuit.engine import phases, save
from pursuit.engine.setup import GameConfig, new_game
from pursuit.engine.state import Game


class StopAt(Exception):
    pass


def play_to_checkpoint(game: Game, count: int) -> None:
    """Run a game until its `count`-th Day-turn checkpoint, then stop."""
    seen = 0
    inner = game.ctl.checkpoint

    def checkpoint(g: Game) -> None:
        nonlocal seen
        seen += 1
        inner(g)
        if seen == count:
            raise StopAt

    game.ctl.checkpoint = checkpoint  # type: ignore[method-assign, assignment]
    with contextlib.suppress(StopAt):
        phases.play(game)
    game.ctl.checkpoint = inner  # type: ignore[method-assign]


def test_round_trip_is_exact(content: Content) -> None:
    game = new_game(
        content, GameConfig("cthulhu", ("mark_harrigan", "akachi_onyele", "lily_chen"), seed=11), HeuristicBot(1)
    )
    play_to_checkpoint(game, 7)
    data = save.to_dict(game)
    loaded = save.from_dict(content, json.loads(json.dumps(data)))
    again = save.to_dict(loaded)
    data.pop("saved_at")
    again.pop("saved_at")
    assert again == data


@pytest.mark.parametrize("stop", [1, 5, 13])
def test_loaded_game_plays_on_identically(content: Content, stop: int) -> None:
    config = GameConfig("shub_niggurath", ("silas_marsh", "charlie_kane"), seed=21)
    original = new_game(content, config, HeuristicBot(3))
    play_to_checkpoint(original, stop)
    snapshot = json.loads(json.dumps(save.to_dict(original)))

    loaded = save.from_dict(content, snapshot)
    loaded.ctl = HeuristicBot(3)
    original.ctl = HeuristicBot(3)
    assert phases.play(original) == phases.play(loaded)
    assert original.round == loaded.round
    assert original.log[-20:] == loaded.log[-20:]


def test_save_and_load_files(content: Content, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PURSUIT_SAVES", str(tmp_path))
    game = new_game(content, GameConfig("azathoth", ("mark_harrigan",), seed=5))
    path = save.saves_dir() / "slot.json"
    save.save_game(game, path)
    listed = save.list_saves()
    assert listed and listed[0][0] == path
    assert listed[0][1]["investigators"] == ["Mark Harrigan"]
    assert save.load_game(content, path).seed == 5


def test_damaged_save_is_rejected(content: Content, tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    with pytest.raises(save.SaveError, match="not valid JSON"):
        save.load_game(content, path)
    path.write_text(json.dumps({"version": save.SAVE_VERSION}))
    with pytest.raises(save.SaveError, match="damaged"):
        save.load_game(content, path)
    path.write_text(json.dumps({"version": 99}))
    with pytest.raises(save.SaveError, match="format 99"):
        save.load_game(content, path)


def test_save_with_unknown_content_is_rejected(content: Content) -> None:
    game = new_game(content, GameConfig("azathoth", ("mark_harrigan",), seed=5))
    data = save.to_dict(game)
    data["investigators"][0]["def_id"] = "somebody_deleted"
    with pytest.raises(save.SaveError, match="no longer exists"):
        save.from_dict(content, data)
