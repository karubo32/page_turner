#!/usr/bin/env python3
"""Pirate Audio LCD (240x240): page turner state, page count and UNMET recognition.

- State and pages come from the page turner GUI, which writes STATUS_PATH.
- UNMET results come from unmet.service (run.py writes UNMET_RESULTS_PATH after
  each reading); UNMET itself does the speaking.
Run with the UNMET venv (it has st7789): ~/unmet_raspberrypi/.venv/bin/python pirate_display.py
"""
import json
import logging
import os
import time
from pathlib import Path

import st7789
from PIL import Image, ImageDraw, ImageFont

STATUS_PATH = Path(f"/run/user/{os.getuid()}/page_turner_status.json")
UNMET_RESULTS_PATH = Path(f"/run/user/{os.getuid()}/unmet_results.json")
UNMET_STALE_AFTER = 90.0  # UNMET reads every 30 s; older results mean it stopped
REFRESH = 0.5           # seconds between screen updates
STALE_AFTER = 10.0      # status older than this means the GUI is closed
# Needs both Japanese and Latin digits (DroidSansFallback alone has no ASCII).
FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
)
FONT_PATH = next((f for f in FONT_CANDIDATES if Path(f).exists()), FONT_CANDIDATES[-1])

W = H = 240
BG = (24, 16, 10)
FG = (245, 239, 230)
DIM = (176, 144, 112)
STATES = {
    "running":      ("再生中", (90, 160, 90)),
    "paused":       ("一時停止", (198, 124, 42)),
    "idle":         ("待機中", (139, 94, 60)),
    "rewinding":    ("1pへ戻し中", (79, 70, 229)),
    "linked":       ("UNMET待ち", (37, 99, 160)),
    "disconnected": ("未接続", (110, 110, 110)),
    "no_gui":       ("GUI停止中", (110, 110, 110)),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOG = logging.getLogger("pirate_display")


def font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


F_STATE, F_PAGE, F_SMALL, F_LABEL = font(30), font(40), font(15), font(22)
F_NAMES = [F_LABEL, font(19), font(16)]


def read_unmet() -> list[tuple[str, float]] | None:
    """Latest UNMET Top-3 as (name, score), or None when UNMET is not running."""
    try:
        data = json.loads(UNMET_RESULTS_PATH.read_text())
    except (OSError, ValueError):
        return None
    if time.time() - data.get("updated", 0) > UNMET_STALE_AFTER:
        return None
    # Show only the first synonym ("ノートパソコン、ラップトップ" -> "ノートパソコン").
    return [(r["ja"].split("、", 1)[0], r["score"]) for r in data.get("results", [])]


def read_status() -> dict:
    try:
        status = json.loads(STATUS_PATH.read_text())
    except (OSError, ValueError):
        return {"state": "no_gui"}
    if time.time() - status.get("updated", 0) > STALE_AFTER:
        return {"state": "no_gui"}
    return status


def fit(draw: ImageDraw.ImageDraw, text: str, fnt, width: int) -> str:
    while text and draw.textlength(text, font=fnt) > width:
        text = text[:-1]
    return text


def render(status: dict, results: list[tuple[str, float]] | None) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # State banner
    label, colour = STATES.get(status.get("state"), STATES["idle"])
    d.rectangle((0, 0, W, 44), fill=colour)
    d.text((W // 2, 22), label, font=F_STATE, fill=FG, anchor="mm")

    # Pages
    d.text((10, 48), "ページ", font=F_SMALL, fill=DIM)
    page, total = status.get("page"), status.get("total")
    page_text = f"{page if page is not None else '—'} / {total if total else '—'}"
    d.text((W // 2, 84), page_text, font=F_PAGE, fill=FG, anchor="mm")
    if page and total:
        d.rectangle((10, 108, W - 10, 114), outline=DIM)
        d.rectangle((10, 108, 10 + int((W - 20) * min(1.0, page / total)), 114), fill=FG)

    # UNMET (Top-3)
    d.line((10, 122, W - 10, 122), fill=DIM)
    d.text((10, 126), "UNMET", font=F_SMALL, fill=DIM)
    if results is None:
        d.text((10, 150), "UNMET停止中", font=F_LABEL, fill=DIM)
    elif not results:
        d.text((10, 150), "該当なし", font=F_LABEL, fill=DIM)
    for i, (ja, score) in enumerate(results or []):
        y = 148 + i * 30
        pct = f"{score * 100:.0f}%"
        d.text((W - 10, y), pct, font=F_LABEL, fill=DIM if i else FG, anchor="ra")
        name_w = W - 30 - int(d.textlength(pct, font=F_LABEL))
        # Shrink long names before cutting them off.
        f_name = next((F for F in F_NAMES if d.textlength(ja, font=F) <= name_w), F_NAMES[-1])
        d.text((10, y + (F_LABEL.size - f_name.size) // 2), fit(d, ja, f_name, name_w),
               font=f_name, fill=DIM if i else FG)
    return img


def main() -> None:
    disp = st7789.ST7789(port=0, cs=1, dc=9, backlight=13, width=W, height=H,
                         rotation=90, spi_speed_hz=80_000_000)
    if hasattr(disp, "begin"):
        disp.begin()
    LOG.info("display running")
    while True:
        disp.display(render(read_status(), read_unmet()))
        time.sleep(REFRESH)


if __name__ == "__main__":
    main()
