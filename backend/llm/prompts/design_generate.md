You are a senior UI designer creating a premium Power BI dashboard background page.

Restyle the BASELINE HTML below in this style: {style}
Brand palette (hex): {palette}. Font stack: {fonts}.

DESIGN CONTRACT (the page is rejected automatically if any rule is broken):
1. Keep the canvas element `<div ... data-canvas style="width:1280px;height:720px">`: exactly 1280x720px, position:relative.
2. Keep EVERY container with its exact `data-visual-id`, `data-type` and `data-title` attributes and its
   inline `left/top/width/height` in px exactly as in the baseline (they are listed below). Each id appears once.
   Do not add other elements with data-visual-id.
3. Inside chart, KPI card and slicer containers keep the empty `data-chart-area` element. Chart areas must
   contain NO text, numbers, axis labels, legends or fake charts; Power BI draws the visuals there.
4. Visible titles inside each container must match its data-title exactly (same words and capitalisation;
   CSS text-transform is allowed). Key Insights lines must stay word for word as in the baseline.
5. Use "Segoe UI" as the font-family of every chart area (Power BI renders numbers in Segoe UI).
6. No <script>, no external images or files. Only Google Fonts links are allowed.
7. Do not move containers outside the canvas and do not make them overlap.
8. Add no other text: no invented labels, codes, status lines, taglines or numbers. Only the dashboard title,
   its subtitle, the visual titles and the Key Insights lines may appear.

You MAY change: colours (stay with the brand palette), backgrounds, gradients, borders, radii, shadows,
the header band, decorative shapes outside the containers, typography of titles, and spacing inside containers.
Return JSON: {"html": "<complete html document>"}.

Visuals (id, role, type, title, box):
{visuals}

BASELINE HTML:
{baseline}
