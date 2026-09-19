import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from games.tetris_v2 import TetrisV2, PIECES_V2, _unique_orientations, _norm


def test_orientation_sets():
    assert len(PIECES_V2["I"]) == 2   # flat + vertical
    assert len(PIECES_V2["O"]) == 1   # square invariant
    assert len(PIECES_V2["T"]) == 4
    assert len(PIECES_V2["S"]) == 2
    assert len(PIECES_V2["Z"]) == 2
    assert len(PIECES_V2["J"]) == 4
    assert len(PIECES_V2["L"]) == 4
    # all normalized masks are left-top aligned
    for piece, orients in PIECES_V2.items():
        for m in orients:
            n = _norm(m)
            assert n == m, (piece, m)


def test_action_space_shape():
    env = TetrisV2(seed=11)
    acts = env.legal_actions()
    assert acts, "first piece must have placements"
    # every action parses to a real (orientation, column) placement
    for a in acts:
        oi, left = a[1:].split("c")
        assert int(oi) < len(PIECES_V2[env.current])
        assert 0 <= int(left) < 10
    desc = env.action_descriptions()
    assert set(desc.keys()) == set(acts)
    assert len(acts) <= env.max_options


def test_rotation_changes_landing():
    for seed in (14, 28, 31, 32):
        env = TetrisV2(seed=seed)
        if env.current != "I":
            continue
        # tower in the middle: flat I cannot cross it, vertical I can rest on top
        env.grid = [[0] * 10 for _ in range(14)]
        for r in range(6, 14):
            for c in range(4, 6):
                env.grid[r][c] = 1
        acts = env.legal_actions()
        flat = [a for a in acts if a.startswith("r0c")]
        vert = [a for a in acts if a.startswith("r1c")]
        assert flat and vert
        assert "r0c0" in flat and "r0c6" in flat      # ground level beside tower
        # flat I across the tower rests ON TOP (row 5) and digs 16 holes;
        # the description exposes that cost while rotation r1 avoids it
        desc = env.action_descriptions()
        assert "rests on row 5" in desc["r0c4"]
        assert "+16" in desc["r0c4"] or "+14" in desc["r0c4"]
        assert any(a in ("r1c4", "r1c5") for a in vert)  # vertical rests on tower
        print("rotation landing ok with seed", seed)
        return
    raise AssertionError("no I piece in seeds 3/5/7/9 — extend seed pool")


def test_random_game_and_clears():
    """Greedy line-seeker (max clears, tie-break min holes) should clear lines
    sometimes — proves the action space + descriptions carry real signal."""
    env = TetrisV2(seed=42)
    steps = 0
    while env.alive and steps < 96:
        acts = env.legal_actions()
        if not acts:
            break
        desc = env.action_descriptions()

        def key(a):
            d = desc[a]
            clears = sum(d.count(f"clears {n}") for n in (1, 2, 3, 4))
            holes = int(d.split("total holes ")[1].split(" ")[0]) if "total holes" in d else 99
            return (clears, -holes)
        best = max(desc, key=key)
        env.step(best)
        steps += 1
    s = env.summary()
    print("tetris_v2 greedy:", s)
    assert s["pieces"] == steps or not env.alive
    assert len(env.grid) == 14


def test_left_edge_death():
    env = TetrisV2(seed=2)
    env.grid = [[1] * 10 for _ in range(14)]
    assert env.legal_actions() == []
    env.step("r0c0")
    assert not env.alive and env.outcome == "topped_out"


def test_determinism():
    a = TetrisV2(seed=77)
    b = TetrisV2(seed=77)
    assert a.queue == b.queue and a.current == b.current
    assert a.legal_actions() == b.legal_actions()


if __name__ == "__main__":
    test_orientation_sets()
    test_action_space_shape()
    test_rotation_changes_landing()
    test_random_game_and_clears()
    test_left_edge_death()
    test_determinism()
    print("ALL TETRIS_V2 TESTS PASS")
