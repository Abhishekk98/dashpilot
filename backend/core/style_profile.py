"""Style profile from a reference dashboard image (design method C, spec 9.3).

Two layers:
1. `pillow_profile` — deterministic colors: background (from the image border), gradient, card
   color, text, muted and accent colors, light/dark mode.
2. `ai_refine` — the LLM's vision describes what pixels cannot: card style, corner radius, shadow,
   font character, spacing. Its answer is schema-checked and merged; colors stay deterministic.
   Any AI failure (no key, quota, bad answer) keeps the Pillow-only profile.

Only the style is taken; layout, text and logos of the reference are never used.
"""

from __future__ import annotations

import colorsys
import io
from collections import Counter
import logging
import re
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator

from core.design_import import contrast, luminance
from llm import LLMError, LLMProvider

logger = logging.getLogger(__name__)
PROMPT = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "design_style.md"
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
_HEX = re.compile(r"^#[0-9A-F]{6}$")

CardStyle = Literal["glass", "solid", "outlined", "elevated"]
Shadow = Literal["none", "soft", "deep", "glow"]
FontCharacter = Literal["geometric sans", "humanist sans", "serif", "mono"]
Spacing = Literal["compact", "regular", "airy"]


class StyleError(ValueError):
    """User-facing problem with the reference image."""


def _hex(value: str) -> str:
    v = value.strip().upper()
    if not v.startswith("#"):
        v = "#" + v
    if len(v) == 4:
        v = "#" + "".join(c * 2 for c in v[1:])
    if not _HEX.match(v):
        raise ValueError(f"{value!r} is not a #RRGGBB color")
    return v


class ProfilePalette(BaseModel):
    primary: str  # main accent
    accents: list[str] = Field(default_factory=list, max_length=4)
    text: str
    muted: str

    @field_validator("primary", "text", "muted")
    @classmethod
    def _color(cls, v: str) -> str:
        return _hex(v)

    @field_validator("accents")
    @classmethod
    def _colors(cls, v: list[str]) -> list[str]:
        return [_hex(c) for c in v]


class ProfileBackground(BaseModel):
    type: Literal["solid", "gradient"] = "solid"
    colors: list[str] = Field(min_length=1, max_length=2)

    @field_validator("colors")
    @classmethod
    def _colors(cls, v: list[str]) -> list[str]:
        return [_hex(c) for c in v]


class StyleProfile(BaseModel):
    """The editable style profile (spec 9.3), shown on the Design Method screen."""

    palette: ProfilePalette
    background: ProfileBackground
    card_color: str
    card_style: CardStyle = "elevated"
    radius_px: int = Field(default=16, ge=0, le=40)
    shadow: Shadow = "soft"
    font_character: FontCharacter = "geometric sans"
    spacing: Spacing = "regular"
    mode: Literal["light", "dark"] = "light"
    layout_pattern: str = Field(default="", max_length=160)  # informational only: the layout comes from the plan
    source: Literal["pillow", "ai"] = "pillow"

    @field_validator("card_color")
    @classmethod
    def _color(cls, v: str) -> str:
        return _hex(v)


# --- image ---------------------------------------------------------------------------------------

MIME = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


def sniff(data: bytes) -> str | None:
    """Image type from the file's magic bytes (never the extension)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def open_image(data: bytes) -> tuple[Image.Image, str]:
    """(RGB image, mime type); raises StyleError for anything that is not a sane PNG/JPEG/WebP."""
    if not data:
        raise StyleError("The image is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise StyleError("Reference images must be 10 MB or smaller.")
    kind = sniff(data)
    if kind is None:
        raise StyleError("Upload a PNG, JPG or WebP image (the file content is not one of these).")
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.format != kind:
            raise StyleError("The file content does not match a PNG, JPG or WebP image.")
        if probe.width * probe.height > MAX_PIXELS:
            raise StyleError("The image is too large (over 40 megapixels).")
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise StyleError(f"The image could not be read ({type(exc).__name__}).") from None
    if img.width < 200 or img.height < 120:
        raise StyleError("The image is too small; use a screenshot of at least 200×120 px.")
    return img.convert("RGB"), MIME[kind]


# --- deterministic layer --------------------------------------------------------------------------------

def _to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(c) for c in rgb[:3]))


def _dist(a: str, b: str) -> float:
    pa, pb = (tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in (a, b))
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


def _sat_light(h: str) -> tuple[float, float]:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return sat, light


def _mix(a: str, b: str, t: float) -> str:
    pa, pb = (tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in (a, b))
    return _to_hex([round(x * (1 - t) + y * t) for x, y in zip(pa, pb)])


def _avg(img: Image.Image, box: tuple[int, int, int, int]) -> str:
    region = img.crop(box).resize((1, 1), Image.Resampling.BOX)
    return _to_hex(region.getpixel((0, 0)))


def vivid_colors(img: Image.Image, limit: int = 5) -> list[str]:
    """Accent colors: saturated pixels grouped by hue (small elements like KPI bars and glows count;
    quantizing the whole image would merge them into the neutrals)."""
    small = img.copy()
    small.thumbnail((800, 800), Image.Resampling.NEAREST)  # nearest: thin bars keep their exact color
    buckets: dict[int, list[tuple[int, int, int]]] = {}
    pixels = list(small.getdata())
    for rgb in pixels:
        r, g, b = (c / 255 for c in rgb)
        hue, light, sat = colorsys.rgb_to_hls(r, g, b)
        if sat > 0.4 and 0.3 < light < 0.85 and max(rgb) - min(rgb) > 40:
            buckets.setdefault(int(hue * 24) % 24, []).append(rgb)
    floor = max(30, len(pixels) // 4000)  # at least 0.025% of the image
    ranked = sorted((b for b in buckets.values() if len(b) >= floor), key=lambda b: -len(b))
    # Secondary accents must be real fills, not the colored fringes of anti-aliased text.
    ranked = [b for b in ranked if len(b) >= 0.15 * len(ranked[0])] if ranked else []
    out: list[str] = []
    for group in ranked:
        # The most frequent exact color: solid fills (bars, logos) win over glow and anti-aliasing blends.
        color = _to_hex(Counter(group).most_common(1)[0][0])
        if all(_dist(color, o) > 0.15 for o in out):
            out.append(color)
        if len(out) == limit:
            break
    return out


def pillow_profile(img: Image.Image) -> StyleProfile:
    small = img.copy()
    small.thumbnail((320, 320))
    w, h = small.size
    q = small.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: 16 * 3]
    colors = {i: _to_hex(pal[i * 3: i * 3 + 3]) for i in range(16)}
    counts = {i: n for n, i in q.getcolors(w * h) or []}
    total = sum(counts.values()) or 1

    # Background: the most common color on the image border.
    border: dict[int, int] = {}
    px = q.load()
    for x in range(w):
        for y in (0, 1, h - 2, h - 1):
            border[px[x, y]] = border.get(px[x, y], 0) + 1
    for y in range(h):
        for x in (0, 1, w - 2, w - 1):
            border[px[x, y]] = border.get(px[x, y], 0) + 1
    bg = colors[max(border, key=border.get)]
    tl, br = _avg(small, (0, 0, w // 6, h // 6)), _avg(small, (w - w // 6, h - h // 6, w, h))
    gradient = _dist(tl, br) > 0.08
    background = ProfileBackground(type="gradient" if gradient else "solid", colors=[tl, br] if gradient else [bg])

    weighted = sorted(((colors[i], n / total) for i, n in counts.items()), key=lambda t: -t[1])
    card = next((c for c, wgt in weighted if wgt >= 0.04 and _dist(c, bg) > 0.04 and _sat_light(c)[0] < 0.45), bg)
    text = max((c for c, wgt in weighted if wgt >= 0.004), key=lambda c: contrast(c, card), default="#1B1C1C")
    if contrast(text, card) < 3:
        text = "#F2F0F0" if luminance(card) < 0.4 else "#1B1C1C"
    accents = [c for c in vivid_colors(img) if _dist(c, bg) > 0.1 and _dist(c, card) > 0.1]
    primary = accents[0] if accents else ("#F8CF4B" if luminance(card) < 0.4 else "#232323")
    mode = "dark" if luminance(bg) < 0.25 else "light"
    if _dist(card, bg) < 0.04:
        card_style: CardStyle = "outlined"
    elif mode == "dark" and luminance(card) - luminance(bg) < 0.06:
        card_style = "solid"
    else:
        card_style = "elevated"
    return StyleProfile(
        palette=ProfilePalette(primary=primary, accents=accents[1:5], text=text, muted=_mix(text, card, 0.4)),
        background=background, card_color=card, card_style=card_style,
        shadow="glow" if mode == "dark" and accents else "soft", mode=mode, source="pillow",
    )


# --- AI layer -----------------------------------------------------------------------------------

class _AIStyle(BaseModel):
    card_style: CardStyle
    radius_px: int
    shadow: Shadow
    font_character: FontCharacter
    spacing: Spacing
    layout_pattern: str = ""


def ai_refine(profile: StyleProfile, image: bytes, mime: str, llm: LLMProvider) -> StyleProfile:
    answer = llm.analyze_image(image, PROMPT.read_text(encoding="utf-8"), mime_type=mime, json_schema=_AIStyle)
    return profile.model_copy(update={
        "card_style": answer.card_style, "radius_px": max(0, min(40, int(answer.radius_px))), "shadow": answer.shadow,
        "font_character": answer.font_character, "spacing": answer.spacing,
        "layout_pattern": " ".join(answer.layout_pattern.split())[:160], "source": "ai",
    })


def build_profile(data: bytes, llm: LLMProvider | None) -> tuple[StyleProfile, str, Image.Image, str | None]:
    """(profile, mime, image, note). The note explains a Pillow-only profile."""
    img, mime = open_image(data)
    profile = pillow_profile(img)
    if llm is None:
        return profile, mime, img, "No AI key: colors were read from the image; card style, radius and fonts are defaults you can edit."
    try:
        # Send a moderate-size copy: enough for style, cheaper for the vision call.
        preview = img.copy()
        preview.thumbnail((1600, 1600))
        buf = io.BytesIO()
        preview.save(buf, "PNG")
        return ai_refine(profile, buf.getvalue(), "image/png", llm), mime, img, None
    except (LLMError, Exception) as exc:  # vision is optional; colors are already known
        logger.warning("Style vision skipped: %s", exc)
        text = str(exc).split(" (", 1)[0][:120] if isinstance(exc, LLMError) else type(exc).__name__
        return profile, mime, img, f"AI style reading unavailable ({text}); colors come from the image, other fields are defaults you can edit."
