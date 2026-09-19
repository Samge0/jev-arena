"""Tetris environment driven by System-One style decisions.

The board is 10 wide. Height defaults to 14 (compact for replay). Pieces spawn
centered. Each decision step, the controller must pick ONE placement column
(0..9) for the current piece; rotation is fixed per piece type to keep the
question single-choice (drop the piece in that column, landing as low as it
can). Gravity, line clears and scoring are classic.

state_text() renders a compact textual board the models judge; the web replay
renders the true numeric grid.
"""
from __future__ import annotations

import random

# Fixed single rotation per piece, as row masks from the piece top-left.
# 0 = empty, 1 = filled. Widths vary; the runner slides a piece so its mask
# left-aligns, then the chosen column is the mask's LEFT edge (clamped).
PIECES = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}

CELL_EMPTY = 0


class Tetris:
    name = "tetris"

    def __init__(self, seed: int, width: int = 10, height: int = 14):
        self.w = width
        self.h = height
        self.rng = random.Random(seed)
        self.seed = seed
        self.grid = [[CELL_EMPTY] * width for _ in range(height)]
        self.queue = [self.rng.choice(list(PIECES)) for _ in range(64)]
        self.idx = 0
        self.score = 0
        self.lines = 0
        self.pieces_dropped = 0
        self.alive = True
        self.outcome = None  # set when game over or horizon
        self.current = self.queue[self.idx]

    # ---------- geometry ----------
    def _mask_width(self, mask):
        return max(len(row) for row in mask)

    def _valid(self, grid, mask, left, top):
        for r, row in enumerate(mask):
            for c, cell in enumerate(row):
                if not cell:
                    continue
                x, y = left + c, top + r
                if x < 0 or x >= self.w or y >= self.h:
                    return False
                if y >= 0 and grid[y][x] != CELL_EMPTY:
                    return False
        return True

    def landing_top(self, mask, left):
        """Top row where the piece settles if dropped at this left column.
        Returns None when the settle position would stick out above row 0."""
        top = -len(mask)
        if not self._valid(self.grid, mask, left, top):
            return None  # cannot even enter
        while self._valid(self.grid, mask, left, top + 1):
            top += 1
        if top < 0:
            return None  # piece does not fully fit -> that placement is fatal
        return top

    def _clamp_left(self, mask):
        w = self._mask_width(mask)
        # piece spawns centered; column choice is clamped to legal range
        return max(0, min(self.w - w, self.spawn_col))

    # ---------- step ----------
    def legal_actions(self):
        mask = PIECES[self.current]
        w = self._mask_width(mask)
        out = []
        for left in range(0, self.w - w + 1):
            if self.landing_top(mask, left) is not None:
                out.append(str(left))
        return out or [str(max(0, (self.w - w) // 2))]

    def action_descriptions(self):
        mask = PIECES[self.current]
        w = self._mask_width(mask)
        desc = {}
        for a in self.legal_actions():
            left = int(a)
            top = self.landing_top(mask, left)
            if top is None:
                desc[a] = f"drop at column {left}"
                continue
            bottom = top + len(mask) - 1
            # highest filled cell under each mask column after drop
            desc[a] = f"drop '{self.current}' with left edge at column {left} (occupies columns {left}-{left + w - 1}, rests on row {bottom})"
        return desc

    def step(self, action: str):
        if not self.alive:
            return
        mask = PIECES[self.current]
        w = self._mask_width(mask)
        left = int(action)
        left = max(0, min(self.w - w, left))
        top = self.landing_top(mask, left)
        if top is None:
            self.alive = False
            self.outcome = "topped_out"
            return
        color = self.idx % 5 + 1
        for r, row in enumerate(mask):
            for c, cell in enumerate(row):
                if cell:
                    self.grid[top + r][left + c] = color
        # clear FULL lines only (rows where every cell is filled)
        full = [row for row in self.grid if all(v != CELL_EMPTY for v in row)]
        cleared = len(full)
        self.grid = [row for row in self.grid if not all(v != CELL_EMPTY for v in row)]
        while len(self.grid) < self.h:
            self.grid.insert(0, [CELL_EMPTY] * self.w)
        self.lines += cleared
        self.score += {0: 0, 1: 40, 2: 100, 3: 300, 4: 1200}.get(cleared, 1200 + (cleared - 4) * 400)
        self.pieces_dropped += 1
        self.idx += 1
        if self.idx >= len(self.queue):
            self.alive = False
            self.outcome = "horizon"
            self.current = None
            return
        self.current = self.queue[self.idx]
        # game over check: the next piece has no fully-fitting placement
        mask2 = PIECES[self.current]
        w2 = self._mask_width(mask2)
        if all(self.landing_top(mask2, l) is None for l in range(0, self.w - w2 + 1)):
            self.alive = False
            self.outcome = "topped_out"

    # ---------- rendering for the models ----------
    def state_text(self):
        rows = []
        for r, row in enumerate(self.grid):
            rows.append("".join("#" if v != CELL_EMPTY else "." for v in row))
        return "\n".join(rows)

    def state_payload(self):
        return {
            "game": "tetris",
            "width": self.w,
            "height": self.h,
            "grid": self.grid,
            "current_piece": self.current,
        }

    def state_for_model(self):
        filled = sum(v != CELL_EMPTY for row in self.grid for v in row)
        holes = self._holes()
        lines = [
            f"Tetris board {self.w}x{self.h}. Current piece: {self.current} (fixed orientation, shown in its own rows).",
            f"Rows are listed top (row 0) to bottom (row {self.h - 1}). '#' is filled, '.' is empty. Dropped pieces never move again.",
            f"Board fill: {filled} cells. Holes (empty cells with fill somewhere above in the same column): {holes}. Lines cleared so far: {self.lines}.",
            "Board:",
            self.state_text(),
        ]
        return "\n".join(lines)

    def _holes(self):
        n = 0
        for c in range(self.w):
            seen = False
            for r in range(self.h):
                if self.grid[r][c] != CELL_EMPTY:
                    seen = True
                elif seen:
                    n += 1
        return n

    def metrics(self):
        return {
            "score": self.score,
            "lines": self.lines,
            "pieces": self.pieces_dropped,
            "holes": self._holes(),
            "max_height": self._max_height(),
        }

    def _max_height(self):
        for r in range(self.h):
            if any(v != CELL_EMPTY for v in self.grid[r]):
                return self.h - r
        return 0

    def summary(self):
        m = self.metrics()
        if self.outcome == "topped_out":
            outcome = "topped out"
        else:
            outcome = "horizon reached"
        return {
            "score": m["score"],
            "lines": m["lines"],
            "pieces": m["pieces"],
            "steps": self.pieces_dropped,
            "holes": m["holes"],
            "max_height": m["max_height"],
            "outcome": outcome,
            "success": m["lines"] >= 1,
        }
