"""Probe the nanojev worker with a v4-sized state (20 rows) to see if predict() fails."""
import json
import subprocess
import sys

python = r"F:\Space\PRO\test\nanojev\.venv\Scripts\python.exe"
script = r"F:\Space\PRO\test\jev-arena\runner\nanojev_worker.py"
ckpt = r"F:\Space\PRO\test\nanojev\checkpoints\NanoJev"

proc = subprocess.Popen([python, script, ckpt], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
hello = proc.stdout.readline()
print("hello:", hello.strip())

state_lines = ["Tetris state:", "Grid 10x20. Coordinates are zero-based (row,column); row 0 is the top.",
               "Current piece: I. Allowed orientations (index: row masks): 0: ####; 1: #/#/#/#.",
               "Board:", "columns: 0 1 2 3 4 5 6 7 8 9"]
state_lines += [f"row {r}: " + " ".join("." for _ in range(10)) for r in range(20)]
state = "\n".join(state_lines)
req = {"mode": "multi", "state": state, "questions": {
    "action": {"type": "choice", "instructions": "Pick the best placement.",
               "criteria": {"r0c0": "flat at col 0", "r0c5": "flat at col 5", "r1c3": "vertical at col 3"}}}}
proc.stdin.write(json.dumps(req) + "\n")
proc.stdin.flush()
line = proc.stdout.readline()
print("reply:", line.strip()[:400])
proc.stdin.close()
err = proc.stderr.read()[:600]
if err:
    print("stderr:", err)
proc.terminate()
