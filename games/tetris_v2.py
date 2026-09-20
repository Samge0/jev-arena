"""Tetris v2: full rotation set + (orientation, column) action space.

Action space per step = orientations × valid columns, each offered as ONE
choice option ("drop T rotated 90° CW at column 4"). This is the realistic
Tetris decision: the model must weigh shape fit AND horizontal position in a
single choice question. Same fixed gravity (hard drop), same full-line clears.

PIECES_V2[t][r] = mask for orientation r (0=spawn, then CW rotations).
"""
from __future__ import annotations

import random

CELL_EMPTY = 0


def _rot_cw(mask):
    """Rotate mask 90° clockwise: new[r][c] = old[R-1-c][r]."""
    rows = len(mask)
    cols = len(mask[0])
    return [[mask[rows - 1 - c][r] for c in range(rows)] for r in range(cols)]


def _norm(mask):
    """Trim empty rows/cols and left-top align."""
    filled_rows = [i for i, row in enumerate(mask) if any(row)]
    if not filled_rows:
        return [[1]]
    r0, r1 = min(filled_rows), max(filled_rows)
    cols = len(mask[0])
    filled_cols = [c for c in range(cols) if any(row[c] for row in mask)]
    c0, c1 = min(filled_cols), max(filled_cols)
    return [[1 if mask[r][c] else 0 for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]


def _unique_orientations(base):
    out = []
    seen = set()
    m = _norm(base)
    for _ in range(4):
        key = tuple(tuple(row) for row in m)
        if key not in seen:
            seen.add(key)
            out.append(m)
        m = _norm(_rot_cw(m))
    return out


_BASE = {
    "I": [[1, 1, 1, 1]],
    "O": [[1, 1], [1, 1]],
    "T": [[0, 1, 0], [1, 1, 1]],
    "S": [[0, 1, 1], [1, 1, 0]],
    "Z": [[1, 1, 0], [0, 1, 1]],
    "J": [[1, 0, 0], [1, 1, 1]],
    "L": [[0, 0, 1], [1, 1, 1]],
}
PIECES_V2 = {k: _unique_orientations(v) for k, v in _BASE.items()}
ROT_NAME = {0: "0°", 1: "90°", 2: "180°", 3: "270°"}


class TetrisV2:
    name = "tetris"

    def __init__(self, seed: int, width: int = 10, height: int = 20, max_options: int = 18):
        self.w = width
        self.h = height
        self.max_options = max_options
        self.rng = random.Random(seed)
        self.seed = seed
        self.grid = [[CELL_EMPTY] * width for _ in range(height)]
        self.queue = [self.rng.choice(list(PIECES_V2)) for _ in range(96)]
        self.idx = 0
        self.score = 0
        self.lines = 0
        self.pieces_dropped = 0
        self.alive = True
        self.outcome = None
        self.current = self.queue[self.idx]
        self._placements = []  # (orient_idx, left) tuples for current piece

    # ---------- geometry ----------
    def _valid(self, grid, mask, left, top):
        """Placement valid if all filled cells are in-bounds horizontally and
        below the ceiling (y >= 0) and don't overlap existing fill. Cells above
        the board (y < 0) count as EMPTY during the fall, but landing_top
        ultimately rejects settle positions that still stick out."""
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
        # start deep enough that the whole mask is above the board (rows < 0
        # are treated as empty in _valid), then let it fall
        top = -len(mask)
        if not self._valid(self.grid, mask, left, top):
            return None
        while self._valid(self.grid, mask, left, top + 1):
            top += 1
        if top < 0:
            return None
        return top

    def _placements_for(self, piece):
        out = []
        for oi, mask in enumerate(PIECES_V2[piece]):
            w = len(mask[0])
            for left in range(0, self.w - w + 1):
                top = self.landing_top(mask, left)
                if top is not None:
                    out.append((oi, left, mask, top))
        return out

    # ---------- controller API ----------
    def legal_actions(self):
        if not self.alive:
            return []
        self._placements = self._placements_for(self.current)
        if not self._placements:
            return []
        # cap the option count deterministically: prefer spread of columns
        if len(self._placements) > self.max_options:
            step = len(self._placements) / self.max_options
            picked = [self._placements[int(i * step)] for i in range(self.max_options)]
            self._placements = picked
        return [f"r{oi}c{left}" for oi, left, _, _ in self._placements]

    def action_descriptions(self):
        desc = {}
        holes_now = self._holes()
        for oi, left, mask, top in self._placements:
            bottom = top + len(mask) - 1
            trial = [row[:] for row in self.grid]
            for r, row in enumerate(mask):
                for c, cell in enumerate(row):
                    if cell:
                        trial[top + r][left + c] = 1
            # count cleared lines on trial
            cleared = sum(1 for row in trial if all(v != CELL_EMPTY for v in row))
            # holes created by this placement
            holes_after = 0
            for c in range(self.w):
                seen = False
                for r in range(self.h):
                    if trial[r][c] != CELL_EMPTY:
                        seen = True
                    elif seen:
                        holes_after += 1
            # aggregate height + bumpiness after (classic Dellacherie features)
            heights = []
            for c in range(self.w):
                hh = 0
                for r in range(self.h):
                    if trial[r][c] != CELL_EMPTY:
                        hh = self.h - r
                        break
                heights.append(hh)
            agg_h = sum(heights)
            bump = sum(abs(heights[i] - heights[i + 1]) for i in range(self.w - 1))
            max_h = max(heights)
            w = len(mask[0])
            tag = f"rotate {ROT_NAME[oi]}, " if len(PIECES_V2[self.current]) > 1 else ""
            line_part = f"clears {cleared} line{'s' if cleared != 1 else ''}" if cleared else "clears nothing"
            hole_part = (f"total holes {holes_after}" if holes_after == holes_now
                         else f"total holes {holes_after} ({holes_after - holes_now:+d})")
            desc[f"r{oi}c{left}"] = (
                f"{tag}left edge at column {left} (occupies columns {left}-{left + w - 1}, "
                f"rests on row {bottom}), {line_part}, {hole_part}, "
                f"resulting stack height sum {agg_h}, max column {max_h}, bumpiness {bump}")
        return desc

    def step(self, action: str):
        if not self.alive:
            return
        if not action.startswith("r") or "c" not in action:
            raise ValueError(f"bad action {action}")
        oi, left = action[1:].split("c")
        oi, left = int(oi), int(left)
        mask = PIECES_V2[self.current][oi]
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
        mask2_list = PIECES_V2[self.current]
        if all(len(self._placements_for_type(self.current, oi)) == 0 for oi in range(len(mask2_list))):
            self.alive = False
            self.outcome = "topped_out"

    def _placements_for_type(self, piece, oi):
        mask = PIECES_V2[piece][oi]
        w = len(mask[0])
        out = []
        for left in range(0, self.w - w + 1):
            if self.landing_top(mask, left) is not None:
                out.append(left)
        return out

    def next_piece(self):
        """Piece after the current one (for the state preview)."""
        if self.idx + 1 < len(self.queue):
            return self.queue[self.idx + 1]
        return None

    # ---------- rendering ----------
    def state_text(self):
        return "\n".join("".join("#" if v != CELL_EMPTY else "." for v in row) for row in self.grid)

    def state_payload(self):
        return {"game": "tetris", "width": self.w, "height": self.h,
                "grid": self.grid, "current_piece": self.current}

    def state_for_model(self):
        filled = sum(v != CELL_EMPTY for row in self.grid for v in row)
        shapes = "; ".join(
            f"{ROT_NAME[oi]}: " + "/".join("".join("#" if v else "." for v in row) for row in mask)
            for oi, mask in enumerate(PIECES_V2[self.current]))
        nxt = self.next_piece()
        nxt_shapes = ""
        if nxt:
            nxt_shapes = "; ".join(
                f"{ROT_NAME[oi]}: " + "/".join("".join("#" if v else "." for v in row) for row in mask)
                for oi, mask in enumerate(PIECES_V2[nxt]))
        return "\n".join([
            f"Tetris board {self.w}x{self.h}. Current piece: {self.current}. Its allowed orientations (row masks): {shapes}.",
            f"Next piece in the queue (plan ahead): {nxt}. Orientations: {nxt_shapes}.",
            f"Rows are listed top (row 0) to bottom (row {self.h - 1}). '#' is filled, '.' is empty. Dropped pieces never move again.",
            f"Board fill: {filled} cells. Holes (empty cells with fill above): {self._holes()}. Lines cleared so far: {self.lines}. Keep the stack flat and low so future pieces still fit.",
            "Board:",
            self.state_text(),
        ])

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
        return {"score": self.score, "lines": self.lines, "pieces": self.pieces_dropped,
                "holes": self._holes(), "max_height": self._max_height()}

    def _max_height(self):
        for r in range(self.h):
            if any(v != CELL_EMPTY for v in self.grid[r]):
                return self.h - r
        return 0

    def orientation_diversity(self):
        """Unique orientations actually used / available across the game."""
        used = set()
        for fr in getattr(self, "_used_actions", []):
            used.add(int(fr[1:].split("c")[0]))
        return len(used)

    def summary(self):
        m = self.metrics()
        outcome = "topped out" if self.outcome == "topped_out" else "horizon reached"
        return {"score": m["score"], "lines": m["lines"], "pieces": m["pieces"],
                "steps": self.pieces_dropped, "holes": m["holes"],
                "max_height": m["max_height"], "outcome": outcome,
                "success": m["lines"] >= 1}
