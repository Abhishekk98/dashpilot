You are a senior UI designer. The image is a screenshot of a dashboard someone likes.

Describe only its visual STYLE so another dashboard can be designed in the same style. Do not
describe or reuse its layout, its text, its numbers, its charts or its logos.

Return JSON with:
- card_style: "glass" (translucent, blurred), "solid" (flat filled cards), "outlined" (thin borders,
  little or no fill) or "elevated" (filled cards lifted by a shadow)
- radius_px: typical card corner radius in pixels at 1280 px width (0-40)
- shadow: "none", "soft", "deep" or "glow" (colored light around cards)
- font_character: "geometric sans", "humanist sans", "serif" or "mono" (headings)
- spacing: "compact", "regular" or "airy" (white space between and inside cards)
- layout_pattern: one short phrase only, e.g. "kpi-row-top + 2x2 charts" (for information; it is not copied)
