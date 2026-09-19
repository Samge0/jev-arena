"""Playwright verification of the arena site: load, interactions, console errors, screenshots."""
import json
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8775/"
OUT = r"F:\Space\PRO\test\jev-arena\shots"
import os
os.makedirs(OUT, exist_ok=True)

errors = []
results = {}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE, wait_until="networkidle")
    page.wait_for_timeout(800)

    # 1. viewer visible, three panels
    panels = page.locator(".model-panel")
    results["panels"] = panels.count()
    names = page.locator(".model-name").all_inner_texts()
    results["panel_names"] = names

    # 2. snapshot of initial state (1024)
    page.screenshot(path=f"{OUT}/01_1024_initial.png", full_page=True)

    # 3. step forward a few frames via next button
    for _ in range(3):
        page.locator("#next").click()
        page.wait_for_timeout(120)
    snap = page.evaluate("window.jevArena.getSnapshot()")
    results["step_after_3_next"] = snap["step"]
    results["prob_values_visible"] = page.locator(".probability-value").all_inner_texts()[:8]
    page.screenshot(path=f"{OUT}/02_1024_step3.png", full_page=True)

    # 4. play for a bit then pause
    page.locator("#play").click()
    page.wait_for_timeout(1500)
    page.locator("#play").click()
    results["playing_toggled"] = True

    # 5. jump near end via timeline set to max
    maxv = page.locator("#timeline").evaluate("el => Number(el.max)")
    page.locator("#timeline").evaluate(f"el => {{ el.value = {maxv}; el.dispatchEvent(new Event('input')) }}")
    page.wait_for_timeout(300)
    snap = page.evaluate("window.jevArena.getSnapshot()")
    results["final_step"] = snap["step"]
    results["total_steps"] = snap["totalSteps"]
    results["final_statuses"] = page.locator(".stat-status").all_inner_texts()
    page.screenshot(path=f"{OUT}/03_1024_final.png", full_page=True)

    # 6. switch to tetris via hash
    page.goto(BASE + "#tetris", wait_until="networkidle")
    page.wait_for_timeout(700)
    snap = page.evaluate("window.jevArena.getSnapshot()")
    results["tetris_game"] = snap["game"]
    results["tetris_step0"] = snap["step"]
    page.screenshot(path=f"{OUT}/04_tetris_initial.png", full_page=True)

    # tetris mid-play: jump to half
    maxv = page.locator("#timeline").evaluate("el => Number(el.max)")
    page.locator("#timeline").evaluate(f"el => {{ el.value = Math.floor({maxv}/2); el.dispatchEvent(new Event('input')) }}")
    page.wait_for_timeout(300)
    page.screenshot(path=f"{OUT}/05_tetris_mid.png", full_page=True)

    # tetris final
    page.locator("#timeline").evaluate(f"el => {{ el.value = {maxv}; el.dispatchEvent(new Event('input')) }}")
    page.wait_for_timeout(300)
    results["tetris_final_statuses"] = page.locator(".stat-status").all_inner_texts()
    page.screenshot(path=f"{OUT}/06_tetris_final.png", full_page=True)

    # 7. tallies table present
    page.locator("#aggregate").scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    results["tally_tables"] = page.locator("#tallyTables table").count()
    results["tally_rows"] = page.locator("#tallyTables tbody tr").count()
    page.screenshot(path=f"{OUT}/07_tallies.png", full_page=True)

    # 8. seed switch works
    page.locator("#seedSelect").select_option("901")
    page.wait_for_timeout(400)
    snap = page.evaluate("window.jevArena.getSnapshot()")
    results["seed_after_switch"] = snap["seed"]

    browser.close()

results["console_errors"] = errors
print(json.dumps(results, indent=1, ensure_ascii=False))
ok = (results["panels"] == 3 and not errors and results["final_step"] == results["total_steps"]
      and results["tally_tables"] >= 2 and results["seed_after_switch"] == 901)
print("SITE VERIFY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
