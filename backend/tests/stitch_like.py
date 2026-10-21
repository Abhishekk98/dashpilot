"""A realistic Stitch-style export for a plan: Tailwind CDN + config, Google fonts, Material Symbols icons,
fake SVG/div charts, KPI values with deltas, slicer pills, header with logo, static labels beside titles."""
import html as htmllib


def stitch_export(plan, accent="#F8CF4B", dark=False, rename: dict | None = None, wrapper_padding=0, size=(1280, 720)) -> str:
    rename = rename or {}
    bg, card, text, muted = ("#111215", "#1B1C20", "#F2F0F0", "#9A9DA6") if dark else ("#F4F1EA", "#FFFFFF", "#1B1C1C", "#6B6B6B")
    sx, sy = size[0] / 1280, size[1] / 720
    cards = []
    for v in plan.visuals:
        b = v.box
        x, y, w, h = round(b.x * sx), round(b.y * sy), round(b.w * sx), round(b.h * sy)
        t = htmllib.escape(rename.get(v.id, v.title))
        pos = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px"
        if v.role == "slicer":
            cards.append(f'<div class="absolute rounded-full bg-surface flex items-center gap-2 px-3 shadow-sm" style="{pos}"><span class="text-[11px] text-muted font-medium">{t}</span><div class="ml-auto flex items-center gap-1 rounded-full bg-canvas px-2 py-1 text-[11px]">All<span class="material-symbols-outlined text-[14px]">expand_more</span></div></div>')
        elif v.role == "kpi":
            cards.append(f'<div class="absolute rounded-2xl bg-surface p-4 shadow-sm flex flex-col" style="{pos}"><div class="flex items-center justify-between"><span class="text-[12px] font-semibold text-ink">{t}</span><span class="material-symbols-outlined text-[16px] text-muted">trending_up</span></div><span class="mt-2 text-[24px] font-semibold text-ink" style="font-family:Segoe UI">$1.48M</span><span class="text-[11px] text-accent font-semibold">+14.2% YoY</span></div>')
        elif v.role == "insights":
            cards.append(f'<div class="absolute rounded-2xl bg-surface p-4 shadow-sm border-l-4 border-accent" style="{pos}"><h3 class="text-[13px] font-semibold text-ink mb-2">{t}</h3><ul class="text-[12px] text-ink list-disc pl-4 space-y-1"><li>Revenue grew 12% versus last month.</li><li>Delhi leads all cities.</li></ul></div>')
        else:
            chart = ('<svg class="w-full h-full" viewBox="0 0 300 120" preserveAspectRatio="none"><polygon points="0,110 60,70 120,85 180,40 240,55 300,20 300,120 0,120" fill="ACC" fill-opacity="0.35"/><polyline points="0,110 60,70 120,85 180,40 240,55 300,20" fill="none" stroke="ACC" stroke-width="3"/></svg>'
                     if v.type in ("line", "area") else
                     '<div class="flex h-full items-end gap-2">' + "".join(f'<div class="flex-1 rounded-t bg-accent" style="height:{p}%"></div>' for p in (35, 80, 55, 92, 40, 66)) + "</div>")
            cards.append(f'<div class="absolute rounded-2xl bg-surface p-4 shadow-sm flex flex-col" style="{pos}"><div class="flex items-center justify-between mb-2"><h3 class="text-[13px] font-semibold text-ink">{t}</h3><span class="text-[10px] text-muted">Last 12 months</span></div><div class="flex-1 min-h-0">{chart.replace("ACC", accent)}</div><div class="mt-1 flex justify-between text-[9px] text-muted"><span>Jan</span><span>Jun</span><span>Dec</span></div></div>')
    pad = f"padding:{wrapper_padding}px;" if wrapper_padding else ""
    return f"""<!DOCTYPE html>
<html class="light" lang="en"><head><meta charset="utf-8"/><meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600&amp;family=Inter:wght@400;500&amp;display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&amp;display=swap" rel="stylesheet"/>
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<script id="tailwind-config">tailwind.config = {{theme: {{extend: {{colors: {{canvas: "{bg}", surface: "{card}", ink: "{text}", muted: "{muted}", accent: "{accent}"}}, fontFamily: {{display: ["Outfit"], body: ["Inter"]}}}}}}}};</script>
</head><body class="bg-canvas font-body" style="margin:0;{pad}">
<div class="relative overflow-hidden bg-canvas" style="width:{size[0]}px;height:{size[1]}px">
  <div class="absolute flex items-center gap-3" style="left:24px;top:14px"><div class="w-9 h-9 rounded-xl bg-accent flex items-center justify-center font-display font-semibold text-ink">C</div><div><h1 class="font-display text-[22px] font-semibold text-ink leading-tight">{htmllib.escape(plan.title)}</h1><p class="text-[11px] text-muted">Executive overview</p></div></div>
  {"".join(cards)}
</div></body></html>"""
