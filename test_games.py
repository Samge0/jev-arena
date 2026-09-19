import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from games.game1024 import Game1024
from games.tetris import Tetris


def test_tetris_random():
    env = Tetris(seed=42)
    steps = 0
    while env.alive and steps < 200:
        acts = env.legal_actions()
        assert acts, "legal_actions must not be empty while alive"
        env.step(env.rng.choice(acts))
        steps += 1
    s = env.summary()
    print("tetris random:", s)
    assert s["pieces"] == steps or not env.alive
    assert 0 <= s["holes"] <= 10 * 14
    # replay render payload sane
    assert len(env.grid) == 14 and all(len(r) == 10 for r in env.grid)


def test_tetris_left_column_stack():
    """Column-0 stacking eventually tops out (no legal placement anywhere);
    the constructed full board must also top out."""
    env = Tetris(seed=1)
    steps = 0
    while env.alive and steps < 200:
        env.step("0")
        steps += 1
    assert not env.alive and env.outcome == "topped_out", env.outcome
    # constructed top-out: completely full board -> next piece cannot enter
    env2 = Tetris(seed=2)
    env2.grid = [[1] * 10 for _ in range(14)]
    env2.step("0")
    assert not env2.alive and env2.outcome == "topped_out", env2.outcome
    print("tetris top-out checks pass")


def test_tetris_landing():
    env = Tetris(seed=7)
    mask = [[1, 1, 1, 1]]
    assert env.landing_top(mask, 0) == 13  # I piece flat on empty board bottom
    # whatever the first piece is, after one drop the board must still be
    # 14 rows and contain exactly the dropped cells at the bottom row
    first = env.current
    env.step("0")
    assert len(env.grid) == 14
    assert any(v != 0 for v in env.grid[13])
    print("tetris landing ok, first piece was", first)


def test_1024_random():
    env = Game1024(seed=42)
    steps = 0
    while env.alive and steps < 600:
        acts = env.legal_actions()
        env.step(env.rng.choice(acts))
        steps += 1
    s = env.summary()
    print("1024 random:", s)
    assert s["max_tile"] >= 4  # random play reaches at least a 4 sometimes
    assert env.alive is False or steps == 600


def test_1024_merge_math():
    env = Game1024(seed=5)
    env.grid = [
        [2, 2, 4, 4],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [0, 0, 0, 0],
    ]
    gained = env._move("left")
    assert env.grid[0] == [4, 8, 0, 0]
    assert gained == 4 + 8
    # no legal move detection on frozen board
    env.grid = [
        [2, 4, 2, 4],
        [4, 2, 4, 2],
        [2, 4, 2, 4],
        [4, 2, 4, 2],
    ]
    assert env.legal_actions() == []
    assert not env._can_move()


def test_determinism():
    a = Tetris(seed=99)
    b = Tetris(seed=99)
    assert a.queue == b.queue
    x = Game1024(seed=99)
    y = Game1024(seed=99)
    xa, xb = x._empty_cells(), y._empty_cells()
    assert xa == xb


def test_state_render():
    env = Game1024(seed=3)
    txt = env.state_for_model()
    assert "1024 board" in txt and "Board:" in txt
    t = Tetris(seed=3)
    txt = t.state_for_model()
    assert "Tetris board" in txt and "Current piece" in txt


if __name__ == "__main__":
    test_tetris_random()
    test_tetris_left_column_stack()
    test_tetris_landing()
    test_1024_random()
    test_1024_merge_math()
    test_determinism()
    test_state_render()
    print("ALL GAME TESTS PASS")
