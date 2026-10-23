"""Design fidelity: does the Power BI page look like the design?

The Power BI page is the clean background PNG with visuals drawn in each card's content area. So
everywhere outside those areas the background must equal the design. The reference is the design
tool's own screenshot (Stitch's screen.png) when the export has one, else our render of its HTML.

- overall: share of matching pixels outside all content areas
- cards: the same per card (card minus its content area), so a mismatch can be pointed at
- render_match: our render of the HTML vs the tool's screenshot (fonts/images/scaling problems)

Pixels match when every channel differs by at most TOLERANCE after a light blur (anti-aliasing
and sub-pixel text rendering are not design differences).
"""

from __future__ import annotations

import io
from typing import Literal

import numpy as np
from PIL import Image, ImageFilter
from pydantic import BaseModel

from core.design_contract import CANVAS_H, CANVAS_W
from core.design_import import DetectedBox, MappingItem

try:
    from app.config import get_settings
    _settings = get_settings()
    THRESHOLD = float(getattr(_settings, "fidelity_threshold", 0.80))
    CARD_THRESHOLD = float(getattr(_settings, "fidelity_card_threshold", 0.80))
    BLOCK_THRESHOLD = float(getattr(_settings, "fidelity_block_threshold", 0.70))
except Exception:
    THRESHOLD = 0.80  # overall default ~80%
    CARD_THRESHOLD = 0.80
    BLOCK_THRESHOLD = 0.70
TOLERANCE = 28
SCALE = 2  # compare at 640x360


class CardFidelity(BaseModel):
    box_id: str
    visual_id: str | None
    title: str
    score: float
    passed: bool


class FidelityReport(BaseModel):
    overall: float
    passed: bool
    threshold: float = THRESHOLD
    card_threshold: float = CARD_THRESHOLD
    block_threshold: float = BLOCK_THRESHOLD
    reference: Literal["screenshot", "render"]
    render_match: float | None = None  # our HTML render vs the tool's screenshot
    cards: list[CardFidelity] = []
    notes: list[str] = []


def _img(png: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png)).convert("RGB")


def _prep(img: Image.Image) -> np.ndarray:
    small = img.resize((CANVAS_W // SCALE, CANVAS_H // SCALE), Image.Resampling.BOX).filter(ImageFilter.BoxBlur(1))
    return np.asarray(small, dtype=np.int16)


def reference_from_screenshot(screen: bytes, original: bytes, source_w: int, source_h: int, scale: float) -> tuple[Image.Image | None, str | None]:
    """The tool's screenshot laid out like our 1280x720 canvas, or (None, why not)."""
    try:
        shot = _img(screen)
    except Exception:
        return None, "The export's screen.png could not be read; compared against the HTML render."
    aspect = shot.width / shot.height
    if abs(aspect - CANVAS_W / CANVAS_H) / (CANVAS_W / CANVAS_H) < 0.02:
        return shot.resize((CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS), None
    if source_h and abs(aspect - source_w / source_h) / (source_w / source_h) < 0.02:
        # The screenshot shows the whole page: fit it exactly like the HTML was fitted.
        w, h = round(source_w * scale), round(source_h * scale)
        canvas = _img(original)
        canvas.paste(shot.resize((w, h), Image.Resampling.LANCZOS), ((CANVAS_W - w) // 2, (CANVAS_H - h) // 2))
        return canvas, None
    return None, f"The export's screen.png is {shot.width}x{shot.height}, which does not match the design; compared against the HTML render."


def content_rect(item: MappingItem, box: DetectedBox | None) -> tuple[int, int, int, int]:
    """Where Power BI draws for this mapping (same rule as the PBIP builder)."""
    if item.pbi_title or box is None or not box.inset:
        return item.x, item.y, item.w, item.h
    left, top, right, bottom = box.inset
    return item.x + left, item.y + top, item.w - left - right, item.h - top - bottom


def _ratio(a: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    total = int(mask.sum())
    if total == 0:
        return 1.0
    ok = (np.abs(a - b).max(axis=2) <= TOLERANCE) & mask
    return round(int(ok.sum()) / total, 4)


def score(original: bytes, background: bytes, boxes: list[DetectedBox], mapping: list[MappingItem], titles: dict[str, str],
          screen: bytes | None = None, source_w: int = CANVAS_W, source_h: int = CANVAS_H, scale: float = 1.0) -> FidelityReport:
    notes: list[str] = []
    ref_img, why = (reference_from_screenshot(screen, original, source_w, source_h, scale) if screen else (None, None))
    if why:
        notes.append(why)
    rendered = _prep(_img(original))
    reference = _prep(ref_img) if ref_img is not None else rendered
    clean = _prep(_img(background))
    h, w = clean.shape[:2]

    by_box = {b.id: b for b in boxes}
    covered = np.zeros((h, w), dtype=bool)
    areas: dict[str, tuple[int, int, int, int]] = {}
    for m in mapping:
        if not m.placed:
            continue
        x, y, cw, ch = content_rect(m, by_box.get(m.box_id or ""))
        areas[m.box_id or m.visual_id] = (x, y, cw, ch)
        covered[max(0, y // SCALE): (y + ch) // SCALE, max(0, x // SCALE): (x + cw) // SCALE] = True
    outside = ~covered
    overall = _ratio(reference, clean, outside)

    cards: list[CardFidelity] = []
    for m in mapping:
        box = by_box.get(m.box_id or "")
        if not m.placed or box is None:
            continue
        region = np.zeros((h, w), dtype=bool)
        region[box.y // SCALE: (box.y + box.h) // SCALE, box.x // SCALE: (box.x + box.w) // SCALE] = True
        region &= outside
        s = _ratio(reference, clean, region)
        cards.append(CardFidelity(box_id=box.id, visual_id=m.visual_id, title=titles.get(m.visual_id, box.title), score=s, passed=s >= CARD_THRESHOLD))

    render_match = _ratio(reference, rendered, np.ones((h, w), dtype=bool)) if ref_img is not None else None
    if render_match is not None and render_match < THRESHOLD:
        notes.append(f"The HTML renders {render_match:.1%} like the design tool's screenshot (fonts or images may differ).")
    if scale < 0.999:
        notes.append(f"The design is {source_w}x{source_h}px, not 1280x720; it was scaled to {scale:.0%} to fit the Power BI page.")
    passed = overall >= THRESHOLD and all(c.passed for c in cards)
    return FidelityReport(overall=overall, passed=passed, reference="screenshot" if ref_img is not None else "render",
                          render_match=render_match, cards=cards, notes=notes)
