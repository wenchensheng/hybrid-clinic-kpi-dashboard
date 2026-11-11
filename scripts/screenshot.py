"""Serve docs/ locally, load the dashboard in headless Chromium, fail on JS errors, save screenshots to images/.

Usage: python scripts/screenshot.py [--chrome /path/to/chrome]
Requires: pip install -r requirements-dev.txt && python -m playwright install chromium
(or pass --chrome to use an installed Chrome/Chromium).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = {
    "dashboard_overview.png": "",
    "dashboard_filtered_riverbend.png": "?clinic=C05&mods=in_person,video,audio&from=2025-01&to=2025-12",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chrome", help="path to a Chrome/Chromium executable (optional)")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT / "docs"))
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errors: list[str] = []
    (ROOT / "images").mkdir(exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chrome) if args.chrome else p.chromium.launch()
            for name, query in SHOTS.items():
                page = browser.new_page(viewport={"width": 1366, "height": 900}, device_scale_factor=1)
                page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
                page.goto(f"http://127.0.0.1:{args.port}/index.html{query}", wait_until="networkidle")
                page.wait_for_selector("body[data-ready='1']", timeout=20000)
                page.wait_for_timeout(800)
                n_plots = page.evaluate("document.querySelectorAll('.js-plotly-plot').length")
                page.screenshot(path=str(ROOT / "images" / name), full_page=True)
                print(f"[screenshot] images/{name}  ({n_plots} charts rendered)")
                page.close()
            browser.close()
    finally:
        srv.shutdown()
    if errors:
        print("JS errors:\n  " + "\n  ".join(errors))
        return 1
    print("[screenshot] no JS errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
