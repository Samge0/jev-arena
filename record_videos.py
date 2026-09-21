"""Record arena comparison videos v2 — watchable pacing.

Speed choices: 1024 → 8 steps/s (~24s for 194 steps), tetris → 2 steps/s
(~40s for 80 steps but capped ~30s by stepping to a good mid point then
playing). Simpler: play everything at a fixed steps/s and let it run to the
final frame, then hold 2.5s on the outcome badges.
"""
import os
import time

from playwright.sync_api import sync_playwright

OUT = r"F:\Space\PRO\test\jev-arena\docs-media"
os.makedirs(OUT, exist_ok=True)

GAMES = [
    # (hash, speed, settle_ms) — speed must match the select's options 4/8/16/32/64
    ("1024", "", 8),      # 194 steps -> ~24s
    ("tetris", "#tetris", 4),  # 80 steps -> ~20s
]


def record(game, hash_, speed):
    path_webm = os.path.join(OUT, f"arena_{game}.webm")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            record_video_dir=OUT,
            record_video_size={"width": 1440, "height": 1000},
        )
        page = ctx.new_page()
        page.goto("http://127.0.0.1:8775/" + hash_, wait_until="networkidle")
        page.wait_for_timeout(2500)
        snap = page.evaluate("window.jevArena.getSnapshot()")
        if not snap.get("ready"):
            raise RuntimeError(f"{game}: viewer not ready")
        total = snap["totalSteps"]
        print(f"{game}: {total} steps at {speed}/s ≈ {total/speed:.0f}s", flush=True)
        page.locator("#speed").select_option(str(speed))
        page.evaluate("window.jevArena.setFrame(pageGame(), 2026, 0)" if False else
                      f"window.jevArena.setFrame('{game}', 2026, 0)")
        page.wait_for_timeout(800)
        page.locator("#play").click()
        t0 = time.time()
        last = -1
        stall = 0
        while time.time() - t0 < 120:
            snap = page.evaluate("window.jevArena.getSnapshot()")
            step = snap["step"]
            if step == last:
                stall += 1
                if stall > 10 and not snap["playing"]:
                    break
            else:
                stall = 0
            last = step
            if step >= total:
                break
            page.wait_for_timeout(250)
        # hold on the final state so outcome badges are readable
        page.wait_for_timeout(2500)
        browser.close()
        # Playwright saves the video on context close; find newest webm
    files = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.endswith(".webm")]
    newest = max(files, key=os.path.getmtime)
    if newest != path_webm:
        os.replace(newest, path_webm)
    print(f"saved {path_webm} ({os.path.getsize(path_webm)//1024} KB)", flush=True)


for game, hash_, speed in GAMES:
    record(game, hash_, speed)
