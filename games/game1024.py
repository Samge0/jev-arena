"""1024 (Threes-family merge game) driven by System-One style decisions.

4x4 grid. Each turn the controller chooses ONE direction (up/down/left/right).
Random tiles (value 2) spawn after moves that change the board. Win = any tile
reaches 1024; death = no legal move. Score = sum of merged tile values.

For the models the board is rendered as a 4x4 numeric table with the chosen
direction's consequences described in the question's option descriptions only
in generic terms (merge basics), never revealing the answer.
"""
from __future__ import annotations

import random

DIRS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}


class Game1024:
    name = "1024"

    def __init__(self, seed: int, size: int = 4, win: int = 1024, horizon: int = 600):
        self.size = size
        self.win_value = win
        self.rng = random.Random(seed)
        self.seed = seed
        self.grid = [[0] * size for _ in range(size)]
        self.horizon = horizon
        self.score = 0
        self.moves = 0
        self.max_tile = 0
        self.alive = True
        self.outcome = None
        self._spawn()
        self._spawn()
        self._refresh_max()

    # ---------- helpers ----------
    def _empty_cells(self):
        return [(r, c) for r in range(self.size) for c in range(self.size) if self.grid[r][c] == 0]

    def _spawn(self):
        cells = self._empty_cells()
        if not cells:
            return False
        r, c = self.rng.choice(cells)
        self.grid[r][c] = 2
        return True

    def _refresh_max(self):
        self.max_tile = max(v for row in self.grid for v in row)

    @staticmethod
    def _slide_row_left(row):
        """Return (new_row, gained)."""
        tiles = [v for v in row if v]
        out = []
        gained = 0
        i = 0
        while i < len(tiles):
            if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
                merged = tiles[i] * 2
                out.append(merged)
                gained += merged
                i += 2
            else:
                out.append(tiles[i])
                i += 1
        out += [0] * (len(row) - len(out))
        return out, gained

    def _move(self, direction):
        """Apply move in place. Returns gained score (0 = no-op)."""
        gained_total = 0
        n = self.size
        if direction in ("left", "right"):
            for r in range(n):
                row = self.grid[r]
                if direction == "right":
                    row = row[::-1]
                new, gained = self._slide_row_left(row)
                if direction == "right":
                    new = new[::-1]
                self.grid[r] = new
                gained_total += gained
        else:
            for c in range(n):
                col = [self.grid[r][c] for r in range(n)]
                if direction == "down":
                    col = col[::-1]
                new, gained = self._slide_row_left(col)
                if direction == "down":
                    new = new[::-1]
                for r in range(n):
                    self.grid[r][c] = new[r]
                gained_total += gained
        return gained_total

    def _can_move(self):
        if self._empty_cells():
            return True
        for r in range(self.size):
            for c in range(self.size):
                v = self.grid[r][c]
                if c + 1 < self.size and self.grid[r][c + 1] == v:
                    return True
                if r + 1 < self.size and self.grid[r + 1][c] == v:
                    return True
        return False

    # ---------- controller API ----------
    def legal_actions(self):
        if not self.alive:
            return []
        out = []
        for d in DIRS:
            snapshot = [row[:] for row in self.grid]
            gained = self._move(d)
            changed = any(self.grid[r][c] != snapshot[r][c]
                          for r in range(self.size) for c in range(self.size))
            self.grid = snapshot
            if changed or gained:
                out.append(d)
        return out

    def action_descriptions(self):
        """Per-direction REAL outcome data (like the reference site's planner):
        merge count, gained score, empty cells after. The model still judges
        which outcome is best; identical data goes to every engine."""
        desc = {}
        for d in self.legal_actions():
            snapshot = [row[:] for row in self.grid]
            before_empty = sum(1 for row in snapshot for v in row if v == 0)
            gained = self._move(d)
            merges = 0
            # recompute merge events: gained/2 summed over merged pairs count
            # count by comparing tile sums: merges = gained / (2 * value-per-pair-sum)? simpler: count pairs
            # recount directly on a fresh replay
            self.grid = [row[:] for row in snapshot]
            merges = self._count_merges(d)
            after_empty = sum(1 for row in self.grid for v in row if v == 0)
            self.grid = snapshot
            arrow = {"up": "toward row 0", "down": "toward row 3",
                     "left": "toward column 0", "right": "toward column 3"}[d]
            desc[d] = (f"slide {d} ({arrow}): {merges} merge{'s' if merges != 1 else ''} "
                       f"(+{gained} points), {after_empty} empty cells after "
                       f"(now {before_empty})")
        return desc

    def _count_merges(self, direction):
        n = self.size
        merges = 0
        grid = [[v for v in row] for row in self.grid]
        if direction in ("left", "right"):
            for r in range(n):
                row = grid[r]
                if direction == "right":
                    row = row[::-1]
                tiles = [v for v in row if v]
                i = 0
                while i + 1 < len(tiles):
                    if tiles[i] == tiles[i + 1]:
                        merges += 1
                        i += 2
                    else:
                        i += 1
        else:
            for c in range(n):
                col = [grid[r][c] for r in range(n)]
                if direction == "down":
                    col = col[::-1]
                tiles = [v for v in col if v]
                i = 0
                while i + 1 < len(tiles):
                    if tiles[i] == tiles[i + 1]:
                        merges += 1
                        i += 2
                    else:
                        i += 1
        return merges

    def step(self, action: str):
        if not self.alive:
            return
        if action not in DIRS:
            raise ValueError(f"bad action {action}")
        gained = self._move(action)
        self.moves += 1
        if gained:
            self.score += gained
            self._spawn()
        self._refresh_max()
        if self.max_tile >= self.win_value:
            self.alive = False
            self.outcome = "win"
            return
        if not self._can_move():
            self.alive = False
            self.outcome = "stuck"
            return
        if self.moves >= self.horizon:
            self.alive = False
            self.outcome = "horizon"

    # ---------- rendering ----------
    def state_text(self):
        return "\n".join(" ".join(f"{v:4d}" if v else "   ." for v in row) for row in self.grid)

    def state_payload(self):
        return {"game": "1024", "size": self.size, "grid": self.grid}

    def state_for_model(self):
        return "\n".join([
            f"1024 board 4x4, after move #{self.moves}. Numbers are tile values, 0 shown as '.'. After your chosen slide, a new tile (value 2) appears in a random empty cell.",
            f"Score so far: {self.score}. Largest tile: {self.max_tile}. Goal: reach 1024. Game ends when no slide changes the board.",
            "Board:",
            self.state_text(),
        ])

    def summary(self):
        return {
            "score": self.score,
            "max_tile": self.max_tile,
            "steps": self.moves,
            "outcome": self.outcome or "alive",
            "success": self.outcome == "win",
        }
