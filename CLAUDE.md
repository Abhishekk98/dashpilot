# DashPilot — working notes for Claude

Always follow ai-powerbi-analyst-project-spec.md and match the designs in designs/ exactly.

(The designs folder in this repo is `stitch_dashpilot_ai_dashboard_studio/` — that is what "designs/" refers to.)

## Project summary
DashPilot is "your AI co-analyst for Power BI". A user uploads CSV/Excel data and the tool profiles
and cleans it, builds the data model, writes KPIs/DAX and insights, generates a Google Stitch design
prompt, imports the finished Stitch design, and builds a ready-to-open Power BI Project (PBIP) in
exactly that design.

## Sources of truth (read-only — never edit, move, overwrite or delete)
- `ai-powerbi-analyst-project-spec.md` — product spec (modules, workflow, PBIP layout, roadmap)
- `stitch_dashpilot_ai_dashboard_studio/` — Stitch exports (`code.html` + `screen.png`) for Home and the
  9 workflow screens, plus the design system in `nordic_analytical_canvas/DESIGN.md`

## Tech stack
- `frontend/` — Next.js 15 (App Router, TypeScript, `src/` dir) + Tailwind CSS v4
- `backend/` — Python 3.11 + FastAPI, pydantic-settings, pandas later per module
- AI: Gemini API (free tier, Flash model) for now, through a provider-agnostic LLM layer in backend/llm/. Switch to Claude later by changing LLM_PROVIDER in .env. Only use public/sample datasets during development — never real client data on the free tier.
  (Defaults: `gemini-3.6-flash`, `claude-opus-5-5`; override with `GEMINI_MODEL` / `CLAUDE_MODEL`.)

The spec's V1 table suggests Streamlit; the user chose Next.js + FastAPI. The spec's build order
(section 10) is followed, adapted to this stack.

## Folder structure
```
CLAUDE.md, README.md, .gitignore
ai-powerbi-analyst-project-spec.md          # spec (read-only)
stitch_dashpilot_ai_dashboard_studio/       # designs (read-only)
frontend/
  src/app/                 # routes: / (Home), /project/[step] (9 workflow steps; step 7 = /project/design-method),
                           # /[section] (coming soon)
  src/app/globals.css      # design tokens (@theme) extracted from the Stitch exports + DESIGN.md
  src/components/layout/   # AppShell, TopNav, AppFooter
  src/components/ui/       # Card, PillButton, PillTag, StatNumber, StepTracker, IconButton, Icon, PlaceholderCard
  src/components/brand/    # DashPilotLogo
  src/lib/                 # steps.ts (pipeline steps), nav.ts, api.ts (backend client)
backend/
  app/                     # FastAPI: main.py (app factory), config.py (settings), api/routes/
  core/                    # one module per spec module: upload, profiling, cleaning, context, modelling,
                           # dax, insights, planner, stitch_prompt, design_import, pbip_builder, validator
                           # + planner_service, design_ai (method B), design_contract (shared render/measure +
                           #   contract checks, reuse in Design Import); planned: design_style (method C)
  llm/                     # base.py (LLMProvider interface, errors, retry), gemini.py, claude.py,
                           # factory.py (picks provider from LLM_PROVIDER), prompts/
  templates/               # tmdl/, visuals/, themes/ for the PBIP builder
  kpi_library/             # industry KPI definitions (JSON)
  samples/                 # sample datasets for testing
  output/                  # generated projects (git-ignored)
  storage/                 # per-project uploads, project.json, cached profile.json (git-ignored)
  tests/                   # pytest
```

## Dashboard design methods (spec Module 9)
At the design stage the user picks one method on `/project/design-method` (tracker step 7 "Design Method"):
- **A. Design with Google Stitch** — Stitch prompt → user designs in Stitch → uploads HTML (or image).
- **B. Design with DashPilot (AI)** — the LLM (via `backend/llm/` only) writes the HTML/CSS from the plan, KPIs,
  business questions, brand and a style preset (Dark Futuristic, Light Elegant, Glassmorphism, Minimal Corporate,
  Neon Tech). Design validator → on failure send the errors back and retry max 2 times → else built-in HTML
  template (`backend/templates/designs/`). 2–3 variants as preview images; user picks, can restyle/regenerate.
- **C. Design from Reference Image** — LLM vision → editable style-profile JSON → Option B generates a new design
  with that style (take the style, never copy the reference layout).

Design contract (B and C): 1280×720 canvas; every chart/card container has `data-visual-id`, `data-type`,
`data-title`; only Power BI-supported visual types; chart areas empty; chart text in Segoe UI; no scripts.
Validator: no overlaps, everything inside the canvas, exactly one container per planned visual.

**Rule:** all three methods only *produce* a 1280×720 HTML design; they all reuse the one shared
Design Import → PBIP Build pipeline (`core/design_import.py` → `core/pbip_builder.py`). Never duplicate import,
layout-check or build code per method. Build order: B (with template fallback) → C → A's Stitch import.
Plans: Free/Student = B; Pro = A, B, C; Agency = all + custom brand kits.

## Scope decisions (V1)
- Functionality follows the V1 spec: CSV/Excel uploads, ~100 MB limit, single-page PBIP.
- UI follows the designs exactly, including nav items outside V1 (Projects, Datasets, Templates,
  Brand Kits, Reports, Settings), which render a "Coming soon" page for now.

## Working rules
- Build one step at a time; do only the requested step, then stop and summarise.
- Show a short plan before writing code for a step.
- After each step run lint/build/tests, start the apps, and give the user exact run commands.
- Ask before deciding anything the spec leaves unclear.
- Replies to the user are in Hinglish; code, file names and comments are in English.
- Commit to git after every working step.

## Coding rules
- Keep code clean and modular; comment only where the logic is not obvious.
- Frontend
  - Port markup from the matching `code.html`; use theme tokens, not raw hex/arbitrary values, when a
    token exists (e.g. `shadow-card`, `rounded-card`, `bg-canvas-glow`, `bg-sunflower`).
  - Token names mirror the Stitch Tailwind config, so classes like `bg-surface-container-lowest/80`
    or `font-title-lg text-title-lg` work as-is.
  - Reuse `components/ui/*` before writing new markup; new shared pieces go there too.
  - Fonts: Outfit (headings/metrics), Inter (body), JetBrains Mono (code/DAX/M) via `next/font`;
    icons are Material Symbols Outlined via `<Icon name="..." />`.
  - Backend URL comes from `NEXT_PUBLIC_API_BASE_URL` (`src/lib/api.ts`).
- Backend
  - Uploaded data is read with every cell as text (`core/upload.py`); `core/profiling.py` detects types.
  - Projects live in `storage/{id}/` via `core.projects.ProjectStore`; the frontend carries `?project={id}`
    between steps.
  - Every router is mounted under `/api`. Business logic lives in `core/`, never in route handlers.
  - All AI calls go through the `llm` package only: `llm.generate_text(prompt, system=None, json_schema=None)`
    and `llm.analyze_image(image, prompt)`. Never import `google.genai` or `anthropic` outside `backend/llm/`
    (a test enforces this). Get the provider via the `get_llm` dependency (None when no key is set, so
    AI features must degrade gracefully). Structured output = pass a Pydantic model as `json_schema`.
  - Prompts live in `llm/prompts/`.
  - Tests never hit a real AI API — use `tests/fakes.FakeProvider`.
  - Type hints on public functions; settings only via `app/config.py`.

## Known design quirks
- The Stitch logo/avatar are hot-linked Google images, so the logo is rebuilt in markup
  (`components/brand/DashPilotLogo`) and the avatar shows initials until real assets are supplied.
- `main` uses `pt-28` (export has `pt-20`) so page titles do not sit under the fixed header.
- Step 9's export uses a different header; handle it when building that step.

## Commands
- Frontend: `cd frontend && npm install && npm run dev` (lint: `npm run lint`, build: `npm run build`)
- Backend: `cd backend`, create a 3.11 venv, `pip install -r requirements-dev.txt`,
  `uvicorn app.main:app --reload --port 8000`, tests: `pytest`
