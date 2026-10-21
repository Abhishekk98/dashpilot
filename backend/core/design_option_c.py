"""Design method C: design from a reference image (spec 9.3).

The reference image only yields a style profile (core.style_profile). The layout always comes from
the Dashboard Plan. Two variants are generated through the same AI + design-contract loop as
Option B (core.design_ai.generate_styled): "close to reference" uses the reference's colors,
"reference + brand" keeps its look but uses the brand accent. Without AI, or after 2 failed
retries, a template themed with the profile is used. Selecting a variant writes selected.html
exactly like Option B, so Design Import and the PBIP build are unchanged.

Files: storage/{id}/design/reference.{png|jpg|webp} and design/option_c.json.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel

from core.context import BusinessContext
from core.context_service import get_context
from core.design_ai import DesignVariant, _hex_rgba, generate_paged, plan_signature, template_html
from core.design_import import contrast
from core.planner import DashboardPlan
from core.projects import Project, ProjectStore
from core.style_profile import MAX_IMAGE_BYTES, StyleError, StyleProfile, build_profile
from llm import LLMProvider

STATE_FILE = "design/option_c.json"
VARIANTS = [
    ("reference_close", "Close to Reference", "the reference's own colors"),
    ("reference_brand", "Reference + Brand Colors", "the reference look with the brand accent color"),
]
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class ReferenceImage(BaseModel):
    filename: str
    mime: str
    width: int
    height: int
    size_bytes: int
    sha: str
    uploaded_at: datetime


class OptionCState(BaseModel):
    image: ReferenceImage | None = None
    profile: StyleProfile | None = None
    profile_note: str | None = None
    edited: bool = False
    variants: list[DesignVariant] = []
    plan_signature: str | None = None
    generated_at: datetime | None = None
    stale: bool = False  # the plan or the profile changed after the variants were generated


# --- theme ----------------------------------------------------------------------------------------

FONTS = {
    "geometric sans": ("Outfit", "Inter", "https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Inter:wght@400;500;600&display=swap"),
    "humanist sans": ("Segoe UI", "Segoe UI", ""),
    "serif": ("Georgia", "Segoe UI", ""),
    "mono": ("JetBrains Mono", "Inter", "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap"),
}


def theme(profile: StyleProfile, accent: str) -> dict[str, str]:
    """The template theme (same keys as design_ai._theme) for a style profile."""
    dark = profile.mode == "dark"
    bg = profile.background.colors
    canvas = f"linear-gradient(135deg, {bg[0]} 0%, {bg[-1]} 100%)" if profile.background.type == "gradient" else bg[0]
    text, card = profile.palette.text, profile.card_color
    card_fill = {
        "glass": _hex_rgba(card, 0.10 if dark else 0.55),
        "outlined": _hex_rgba(card, 0.25 if dark else 0.4),
    }.get(profile.card_style, card)
    border = {
        "glass": f"1px solid {_hex_rgba('#FFFFFF', 0.14 if dark else 0.7)}",
        "outlined": f"1px solid {_hex_rgba(accent if dark else text, 0.45 if dark else 0.18)}",
    }.get(profile.card_style, f"1px solid {_hex_rgba(text, 0.06)}")
    shadow = {
        "none": "none",
        "soft": f"0 12px 32px -12px {_hex_rgba('#000000', 0.35 if dark else 0.14)}",
        "deep": f"0 24px 48px -16px {_hex_rgba('#000000', 0.55 if dark else 0.28)}",
        "glow": f"0 0 24px -4px {_hex_rgba(accent, 0.45)}",
    }[profile.shadow]
    return {
        "page": bg[0], "canvas": canvas, "card": card_fill, "border": border, "radius": f"{profile.radius_px}px",
        "shadow": "none" if profile.card_style == "outlined" and profile.shadow == "soft" else shadow,
        "title": text, "muted": profile.palette.muted, "area": _hex_rgba(text, 0.04), "accent": accent,
        "kpi_bar": accent, "blur": "blur(14px)" if profile.card_style == "glass" else "none",
    }


def _accent(variant: str, profile: StyleProfile, context: BusinessContext) -> str:
    if variant == "reference_brand":
        brand = context.palette.accent
        # A brand accent that disappears on the reference's cards would be useless; keep the reference one.
        return brand if contrast(brand, profile.card_color) >= 1.3 else profile.palette.primary
    return profile.palette.primary


def _style_text(profile: StyleProfile, accent: str) -> str:
    bg = " to ".join(profile.background.colors)
    return (f"Reference style (take the style only, never a layout or text from the reference): {profile.mode} theme, "
            f"{profile.background.type} background {bg}, {profile.card_style} cards in {profile.card_color}, "
            f"{profile.radius_px}px corners, {profile.shadow} shadow, {profile.font_character} headings, "
            f"{profile.spacing} spacing, text {profile.palette.text}, muted {profile.palette.muted}, accent {accent}.")


def variant_template(plan: DashboardPlan, context: BusinessContext, profile: StyleProfile, variant: str,
                     arrangement=None, chip: str = "") -> str:
    return template_html(plan, context, theme=theme(profile, _accent(variant, profile, context)), fonts=FONTS[profile.font_character],
                         arrangement=arrangement, page_label=chip)


def generate_variants(plan: DashboardPlan, context: BusinessContext, profile: StyleProfile, llm: LLMProvider | None,
                      prefer_browser: bool = True) -> list[DesignVariant]:
    out = []
    ai = llm
    layouts = ["grid"] * len(plan.pages)
    for vid, label, _ in VARIANTS:
        accent = _accent(vid, profile, context)
        palette = {"accent": accent, "background": profile.background.colors, "card": profile.card_color,
                   "text": profile.palette.text, "muted": profile.palette.muted}
        variant, usable = generate_paged(
            plan, vid, label, layouts,
            lambda placed, arr, chip, vid=vid: variant_template(placed, context, profile, vid, arr, chip),
            _style_text(profile, accent), palette, profile.font_character, ai, prefer_browser)
        if ai is None and llm is not None:
            variant.note = "AI skipped after an earlier quota/key error; profile-themed template used."
        elif variant.note:
            variant.note = variant.note.replace("built-in template", "profile-themed template")
        if not usable:
            ai = None
        out.append(variant)
    return out


# --- storage + service --------------------------------------------------------------------------------

def _plan(store: ProjectStore, project: Project) -> DashboardPlan:
    from core.planner_service import PLAN_FILE, PlanError  # local: planner_service imports this module

    stored = store.read_json(project.id, PLAN_FILE).get("plan")
    if not stored:
        raise PlanError("Build the dashboard plan first (top of this page).")
    return DashboardPlan.model_validate(stored)


def _signature(plan: DashboardPlan, profile: StyleProfile | None) -> str:
    raw = plan_signature(plan) + (profile.model_dump_json() if profile else "")
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def get_state(store: ProjectStore, project: Project) -> OptionCState:
    state = OptionCState.model_validate(store.read_json(project.id, STATE_FILE))
    if state.variants:
        try:
            state.stale = state.plan_signature != _signature(_plan(store, project), state.profile)
        except ValueError:
            state.stale = True
    return state


def _save(store: ProjectStore, project: Project, state: OptionCState) -> OptionCState:
    (store.project_dir(project.id) / "design").mkdir(parents=True, exist_ok=True)
    store.write_json(project.id, STATE_FILE, state.model_dump(mode="json", exclude={"stale"}))
    return get_state(store, project)


def style_profile_limit() -> int:
    return MAX_IMAGE_BYTES


def image_path(store: ProjectStore, project: Project):
    state = get_state(store, project)
    if not state.image:
        return None, None
    return store.project_dir(project.id) / "design" / f"reference.{EXT[state.image.mime]}", state.image.mime


def upload_reference(store: ProjectStore, project: Project, llm: LLMProvider | None, filename: str, data: bytes) -> OptionCState:
    try:
        profile, mime, img, note = build_profile(data, llm)
    except StyleError as exc:
        from core.planner_service import PlanError  # noqa: PLC0415

        raise PlanError(str(exc)) from None
    folder = store.project_dir(project.id) / "design"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("reference.*"):
        old.unlink()
    (folder / f"reference.{EXT[mime]}").write_bytes(data)
    state = OptionCState(
        image=ReferenceImage(filename=filename[:120], mime=mime, width=img.width, height=img.height, size_bytes=len(data),
                             sha=hashlib.sha256(data).hexdigest(), uploaded_at=datetime.now(timezone.utc)),
        profile=profile, profile_note=note,
    )
    return _save(store, project, state)


def save_profile(store: ProjectStore, project: Project, profile: StyleProfile) -> OptionCState:
    state = get_state(store, project)
    if not state.image:
        from core.planner_service import PlanError  # noqa: PLC0415

        raise PlanError("Upload a reference image first.")
    state.profile = profile
    state.edited = True
    return _save(store, project, state)


def generate(store: ProjectStore, project: Project, llm: LLMProvider | None) -> tuple[OptionCState, list[str]]:
    from core.planner_service import PlanError  # noqa: PLC0415

    state = get_state(store, project)
    if not state.profile:
        raise PlanError("Upload a reference image first.")
    plan = _plan(store, project)
    if not plan.valid:
        raise PlanError("Fix the dashboard plan first: " + "; ".join(plan.issues[:3]))
    state.variants = generate_variants(plan, get_context(store, project), state.profile, llm)
    state.plan_signature = _signature(plan, state.profile)
    state.generated_at = datetime.now(timezone.utc)
    ai = sum(v.source == "ai" for v in state.variants)
    notes = [f"{ai} of {len(state.variants)} designs made by AI in the reference style; {len(state.variants) - ai} from the profile-themed template."]
    notes += [f"{v.label}: {v.note}" for v in state.variants if v.note]
    return _save(store, project, state), notes
