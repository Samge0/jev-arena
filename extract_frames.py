"""Extract 3 frames from each recording for visual inspection."""
import subprocess
import os

OUT = r"F:\Space\PRO\test\jev-arena\docs-media"
for game in ("1024", "tetris"):
    src = os.path.join(OUT, f"arena_{game}.mov")
    for i, t in enumerate((0.5, 2.5, 4.5)):
        dst = os.path.join(OUT, f"check_{game}_{i}.png")
        subprocess.run(["ffmpeg", "-y", "-ss", str(t), "-i", src, "-frames:v", "1", dst],
                       capture_output=True)
        print(dst, os.path.getsize(dst) if os.path.exists(dst) else "MISSING")
