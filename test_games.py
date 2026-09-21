import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from games.game1024 import Game1024
from games.tetris_v2 import TetrisV2


def test_tetris_random_invariants():
    env = TetrisV2(seed=42)
    steps = 0
    while env.alive and steps < 200:
        acts = env.legal_actions()
        assert acts, "legal_actions must not be empty while alive"
        env.step(env.rng.choice(acts))
        steps += 1
    s = env.summary()
    print("tetris_v2 random:", s)
    assert s["pieces"] == steps or not env.alive
    assert len(env.grid) == env.h and all(len(r) == env.w for r in env.grid)


def test_tetris_state_render():
    t = TetrisV2(seed=3)
    txt = t.state_for_model()
    assert "Tetris board" in txt and "Current piece" in txt


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
    a, b = TetrisV2(seed=99), TetrisV2(seed=99)
    assert a.queue == b.queue and a.legal_actions() == b.legal_actions()
    x, y = Game1024(seed=99), Game1024(seed=99)
    xa, xb = x._empty_cells(), y._empty_cells()
    assert xa == xb


def test_state_render():
    env = Game1024(seed=3)
    txt = env.state_for_model()
    assert "1024 board" in txt and "row0:" in txt  # v2 coordinate labels


if __name__ == "__main__":
    test_tetris_random_invariants()
    test_tetris_state_render()
    test_1024_random()
    test_1024_merge_math()
    test_determinism()
    test_state_render()
    print("ALL GAME TESTS PASS")
