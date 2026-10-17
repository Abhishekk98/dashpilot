# AI Power BI Analyst — Project Specification

> Working name: **DashPilot** (final brand name + domain availability check karna hai)
> Version: 1.0 draft · October 2026
> Build tools: Claude AI / Claude Code / Google Antigravity

---

## 1. Product Summary

An AI tool that does the full Power BI data analyst workflow. The user uploads data, and the tool:

1. Profiles and cleans the data
2. Builds the data model (star schema, relationships, date table)
3. Understands the business context and writes business questions
4. Creates KPIs and DAX measures
5. Generates insights
6. Creates the dashboard design with one of **three design methods** (see Module 9):
   - **A. Design with Google Stitch** — the tool writes a custom Stitch prompt (brand, KPIs, business questions); the analyst designs in Stitch and **uploads the design back** (HTML export preferred, image as fallback)
   - **B. Design with DashPilot (AI)** — the AI generates the 1280×720 HTML design directly from the plan, KPIs and brand
   - **C. Design from Reference Image** — the AI takes the *style* of a reference image and generates a new design for this project's own KPIs
7. Every method produces a 1280×720 HTML design that goes through the **same Design Import → PBIP Build pipeline**
8. The tool builds the **real Power BI dashboard in the exact same design** and gives a ready-to-open Power BI Project (PBIP)

**Goal:** Cut dashboard building time from days to under an hour, with premium, futuristic, elegant designs that clients love.

**Positioning:** "Your AI co-analyst for Power BI" — automates ~80% of the work; the analyst reviews and finalises. Not a replacement for the analyst.

---

## 2. Why This Works (Market Gap)

- Power BI's new **PBIR** report format and **TMDL** model format are text/JSON based and officially support programmatic creation by scripts and AI agents → we can generate full Power BI projects.
- Microsoft Copilot in Power BI can generate report pages, but needs paid Fabric (F2+) or Premium capacity — does **not** work with Power BI Pro alone. Freelancers, students, small companies and many analysts don't have it.
- Copilot output is functional but plain. Our differentiator: **brand-matched premium designs** + **end-to-end workflow** (cleaning → model → DAX → insights → design → build).

---

## 3. Target Users

| User | Problem | Value |
|---|---|---|
| Freelance data analysts (Fiverr/Upwork/direct) | Dashboards take days per client | Deliver 3–5x faster, take more clients |
| In-house analysts (small/mid companies) | Repetitive report building | Faster delivery, better design |
| Small & mid businesses without analysts | Can't afford a full-time analyst | Professional dashboards at low cost |
| Agencies (marketing, consulting) | Client reporting is slow | Branded dashboards per client |
| Students / job seekers | Need strong portfolio dashboards | Portfolio-grade projects quickly |

---

## 4. End-to-End Workflow

```
Upload Data
   ↓
1. Data Profiling ──→ 2. Data Cleaning (Power Query M)
   ↓
3. Business Context (company, industry, audience, brand)
   ↓
4. Data Model (star schema, relationships, date table)
   ↓
5. KPIs + DAX Measures ──→ 6. Business Questions + Insights
   ↓
7. Dashboard Plan (pages, visuals, layout)
   ↓
8. Choose Design Method
   ├─ A. Google Stitch: prompt generated → analyst designs in Stitch → uploads HTML (or image)
   ├─ B. DashPilot AI: LLM generates HTML → validator (≤2 retries, then template) → 2–3 variants → user picks
   └─ C. Reference Image: LLM vision → style profile (editable) → Option B with that style
   ↓
9. 1280×720 HTML design (one format for all three methods)
   ↓
10. Design Import (shared) → layout + colors extracted
   ↓
11. Power BI Build (PBIP: semantic model + report + background + theme)
   ↓
12. Validation → Download → Open in Power BI Desktop
```

---

## 5. Modules

### Module 1 — Data Upload
- Formats: CSV, Excel (multiple sheets) — V1
- Later: Google Sheets, SQL Server, PostgreSQL, MySQL
- Multiple files supported (e.g. Orders, Customers, Products)
- File size limit for V1: ~100 MB

### Module 2 — Data Profiling
For each table and column:
- Data type detection (number, text, date, boolean, currency, percentage, ID, category, location)
- Row count, null %, distinct count, duplicates
- Min / max / mean / median for numbers; date range for dates
- Outlier detection
- Semantic role detection with AI: "this is an Order ID", "this is Revenue", "this is City"
- Output: **Data Quality Report** shown to the user

### Module 3 — Data Cleaning
- Auto-suggested cleaning steps (user can accept/reject each):
  - Fix data types, trim spaces, standardise text case
  - Remove duplicates, handle nulls (remove / fill / flag)
  - Split/merge columns, parse dates, fix currency/number formats
  - Standardise categories (e.g. "Delhi", "delhi", "New Delhi")
- Generates **Power Query M code** for every step (so cleaning happens inside Power BI and refresh works)
- Also applies the same cleaning in Python for preview

### Module 4 — Business Context
User provides (or tool suggests from data):
- Company name, industry (retail, food delivery, e-commerce, finance, HR, healthcare, SaaS, manufacturing, logistics, education, marketing…)
- Dashboard audience: CEO/leadership, sales, marketing, operations, finance, HR
- Business goal: e.g. "track delivery performance", "find sales growth drivers"
- Brand: logo upload, brand colors (or tool suggests a palette), light/dark preference

### Module 5 — Data Modelling
- Detect fact vs dimension tables
- Build **star schema**: split a flat file into fact + dimensions when useful
- Detect and create relationships (keys, cardinality, filter direction)
- Auto-generate a **Date table** (with Year, Quarter, Month, Week, Day, Fiscal year option) and mark it as date table
- Hide technical columns (IDs, keys) from report view
- Output: model diagram preview + TMDL files

### Module 6 — KPIs & DAX
- Industry-based KPI library (e.g. Retail: Revenue, Orders, AOV, Margin %, Return Rate; HR: Headcount, Attrition %, Avg Tenure)
- AI picks relevant KPIs based on data + business context
- Generates DAX measures with:
  - Base measures (Total Sales, Total Orders, Distinct Customers)
  - Ratios (Margin %, Conversion %, AOV)
  - Time intelligence (MTD, QTD, YTD, Previous Month, YoY %, MoM %)
  - Rankings and Top N
- Measures organised in display folders, with format strings and descriptions
- **Validation:** every measure is checked (syntax + test calculation against the Python preview; flag mismatches)

### Module 7 — Business Questions & Insights
- 5–10 business questions the dashboard should answer (per audience)
- Auto insights: top/bottom performers, trends, anomalies, period comparisons, contribution analysis
- Insights written in plain language, ready to place in the dashboard "Key Insights" card

### Module 8 — Dashboard Plan
- Number of pages (V1: 1 main page; later multi-page)
- For each visual: chart type, title, measure(s), dimension(s), sort, purpose (which business question it answers)
- **Allowed visuals (Power BI native only):** KPI/card, line, area, clustered bar/column, stacked bar/column, donut, map/filled map, table, matrix, slicer (dropdown/date range/buttons), gauge, scatter, waterfall, funnel, text box

### Module 9 — Dashboard Design (three methods)

At the design stage the user picks one method on a **"Choose design method"** screen. All three methods must output the same thing — **one 1280×720 HTML design** — which then goes through the **shared Design Import (Module 10) → PBIP Build (Module 11) pipeline**. There is exactly one import pipeline and one builder; a method may only add its own way of *producing* the HTML (no duplicated import/build code).

| Method | Who designs | Input | Output |
|---|---|---|---|
| **A. Design with Google Stitch** | Analyst, in Google Stitch | Stitch prompt (9.1) | Uploaded Stitch HTML export (or image → Module 10B) |
| **B. Design with DashPilot (AI)** | LLM via `backend/llm/` | Plan, KPIs, business questions, brand, style preset | Generated HTML that passes the design contract |
| **C. Design from Reference Image** | LLM via `backend/llm/` | Reference image → editable style profile | Generated HTML (Option B with the style profile) |

#### 9.0 Design contract (Options B and C; Option A's import must also satisfy it after mapping)
- Canvas exactly **1280×720**; nothing positioned outside it
- Every chart/card container carries `data-visual-id` (id from the Dashboard Plan), `data-type` (Power BI visual type from the Module 8 allowed list) and `data-title` (exact visual title)
- Only Power BI-supported visual types (Module 8 list)
- Chart areas are left **empty** (no fake charts, numbers or axis text); only the card, its shape/shadow and the title are drawn
- Chart text font **Segoe UI** (headings may use the brand heading font)
- Self-contained HTML/CSS: no scripts, no external images except the uploaded logo; fonts from an allow-list

#### 9.1 Option A — Design with Google Stitch (existing flow)
Stitch prompt generator below → analyst designs in Stitch → uploads HTML export (or image fallback). The upload goes into the shared Design Import.

Generates a ready-to-paste prompt containing:
- Canvas: **1280×720 (16:9)**
- Brand theme: colors (hex), background, card style, corner radius, glow/shadow style
- Style direction: premium, futuristic, elegant (with variants: Dark Futuristic, Light Elegant, Glassmorphism, Minimal Corporate, Neon Tech)
- Fonts: headings in a premium font (e.g. Sora / Space Grotesk / Poppins), **all chart labels and numbers in Segoe UI** (to match Power BI rendering)
- Exact layout: every KPI card and chart with type, title, data and position
- Business questions the dashboard answers
- **Build rules:**
  - Use only Power BI-supported chart types
  - Every chart/card area must be a clearly separated container with its exact title text (titles are used to match visuals during import)
  - No text inside chart areas except the title
  - Keep consistent spacing and alignment on a grid

Prompt template (filled automatically):

```
Design a premium, futuristic, elegant Power BI dashboard UI on a 1280x720 canvas for {company_name}, a {industry} company. Audience: {audience}.

BRAND THEME: Primary {primary_hex}, background {bg_hex}, cards {card_hex} with {card_style}, {radius}px rounded corners, accents {accent_hexes}. Headings in "{heading_font}", all chart labels and numbers in "Segoe UI". Style: {style_variant}.

LAYOUT:
- Top bar: logo placeholder (left), title "{dashboard_title}", slicers: {slicers} (right)
- Row 1: {n} KPI cards: {kpi_list} — each with value, % change and small trend
{visual_rows}

BUSINESS QUESTIONS THIS DASHBOARD ANSWERS:
{business_questions}

RULES: Use only chart types available in Power BI. Each chart/card is a separate container showing its exact title. Leave chart areas as clean placeholders. Premium, minimal, high contrast, generous spacing, aligned grid, no clutter.
```

#### 9.2 Option B — Design with DashPilot (AI)
1. **Inputs:** Dashboard Plan (Module 8), KPIs/DAX (Module 6), business questions (Module 7), brand palette, logo, light/dark mode and fonts (Module 4), and a **style preset**: Dark Futuristic, Light Elegant, Glassmorphism, Minimal Corporate, Neon Tech (default = the archetype chosen in Business Context)
2. **Generate:** the active LLM (Gemini now, Claude later — always through `backend/llm/`, prompt in `llm/prompts/`) writes the HTML/CSS following the design contract (9.0)
3. **Design validator** (pure Python, runs on the rendered 1280×720 layout):
   - no overlapping containers
   - every container fully inside the canvas
   - every planned visual has **exactly one** container (`data-visual-id` match), no unknown ids, `data-type` allowed and equal to the planned type
   - contract checks: canvas size, Segoe UI in chart text, empty chart areas, no scripts/external resources
4. **Repair loop:** on failure, send the validator's error list back to the LLM and retry — **max 2 retries**. If it still fails (or no AI key / AI error), **fall back to a built-in HTML template** for the chosen preset, filled with the plan's visuals and brand colors (templates live in `backend/templates/designs/` and always pass the validator)
5. **Variants:** generate **2–3 variants**, render each to a **preview image** (PNG); the user picks one
6. **Iterate:** the user can change the style preset or colors and regenerate
7. The chosen HTML goes to the shared Design Import (Module 10A path)

#### 9.3 Option C — Design from Reference Image
1. User uploads a **reference image** (PNG/JPG of any dashboard they like)
2. LLM vision extracts a **style profile** (JSON), shown in an editable form:
   ```json
   {
     "palette": {"primary": "#...", "accents": ["#..."], "text": "#..."},
     "background": {"type": "solid|gradient", "colors": ["#..."]},
     "card_style": "glass|solid|outlined|elevated",
     "radius_px": 16,
     "shadow": "none|soft|deep|glow",
     "font_character": "geometric sans|humanist sans|serif|mono",
     "spacing": "compact|regular|airy",
     "layout_pattern": "kpi-row-top + 2x2 charts | sidebar + grid | ..."
   }
   ```
3. Option B then generates a **new** design with this style profile in place of the preset, using the project's own KPIs and visuals. Rule: **take the style, never copy the reference layout exactly** (the layout always comes from the Dashboard Plan)
4. Same validator, retries, template fallback, variants and shared import as Option B

### Module 10 — Design Import (shared by all three design methods)
One pipeline, used by Options A, B and C. B and C already emit contract HTML with `data-visual-id`, so step 3 below is an exact id match for them; Stitch HTML (Option A) uses title matching.

Two input options:

**A. HTML (Stitch export, or generated by Option B / C) — recommended, most accurate**
1. Render HTML in a headless browser (Playwright) at 1280×720
2. Extract every container's position (x, y, width, height), colors, border radius, fonts
3. Match containers to planned visuals: by `data-visual-id` when present (Options B/C), otherwise by title text (fuzzy match + AI fallback)
4. Create a **clean background PNG**: hide chart placeholder contents and KPI values, keep cards, shapes, shadows, headers, logo, static titles
5. Extract palette → generate **Power BI theme JSON** (data colors, background, foreground, fonts, visual styles)

**B. Image upload (Option A fallback only)**
1. AI vision (active LLM provider: Gemini now, Claude later) detects layout regions and their titles
2. Estimate positions and colors
3. Ask the user to confirm/adjust mapping in a simple editor

**Mapping editor (UI):** shows the design with numbered boxes; user can reassign which visual goes in which box, or adjust box positions.

### Module 11 — Power BI Builder (PBIP)
Generates a complete Power BI Project folder:

```
{Project}.pbip
{Project}.SemanticModel/
    definition/
        model.tmdl
        tables/*.tmdl          ← columns, Power Query M, measures
        relationships.tmdl
{Project}.Report/
    definition/
        report.json
        pages/{page}/page.json  ← canvas size, background image
        pages/{page}/visuals/{id}/visual.json  ← type, position, fields, formatting
    StaticResources/
        RegisteredResources/   ← background PNG, logo, theme JSON
Data/                          ← cleaned source files (or original files + M cleaning steps)
```

- Visual positions exactly from Design Import
- Visual formatting: transparent backgrounds (so the designed card shows through), no default borders, title/label colors from theme, Segoe UI fonts
- Data source path set as a **Power Query parameter** so the user can repoint it easily
- **Important build practice:** keep reference templates — save sample reports from Power BI Desktop as PBIP for each visual type and use them as JSON templates. Always validate generated files against Microsoft's PBIP/PBIR/TMDL documentation and schemas.

### Module 12 — Validation & Delivery
- JSON schema validation of all report files
- TMDL syntax check
- DAX check (syntax + test values)
- Layout check: no overlapping visuals, everything inside canvas (same rules as the Module 9 design validator, reused, not reimplemented)
- Output: ZIP download of the PBIP project + a short "how to open" guide
- Optional: documentation PDF (data dictionary, measures list with explanations, model diagram) — useful for clients

---

## 6. Tech Stack

| Layer | V1 (fast MVP) | Later (SaaS) |
|---|---|---|
| UI | Streamlit (Python) | Next.js + Tailwind |
| Backend | Python | FastAPI |
| Data processing | pandas / Polars, DuckDB | same |
| AI | Gemini API (free tier, Flash model) for now, through a provider-agnostic LLM layer in backend/llm/ (analysis, DAX, M code, insights, Stitch prompt, vision). Switch to Claude later via LLM_PROVIDER in .env | Claude API |
| Design import | Playwright (render HTML, get positions, screenshot background) | same |
| Image processing | Pillow | same |
| PBIP generation | Python (Jinja2 templates for TMDL/JSON) | same |
| Storage | Local files | S3 / Supabase Storage |
| Database | SQLite | PostgreSQL (Supabase) |
| Auth & payments | — | Supabase Auth, Razorpay / Stripe |
| Hosting | Local / Streamlit Cloud | Railway / Render / AWS |

Why Streamlit for V1: pure Python, fastest way to a working demo, and fits a data analyst's skill set.

---

## 7. Project Folder Structure (V1)

```
dashpilot/
├── app.py                     # Streamlit UI (step-by-step wizard)
├── core/
│   ├── upload.py              # read CSV/Excel
│   ├── profiling.py           # data quality report
│   ├── cleaning.py            # cleaning suggestions + M code
│   ├── context.py             # business context, brand
│   ├── modelling.py           # star schema, relationships, date table
│   ├── dax.py                 # KPI selection + DAX generation + validation
│   ├── insights.py            # business questions + insights
│   ├── planner.py             # dashboard plan (visuals, layout)
│   ├── stitch_prompt.py       # Option A: Stitch prompt generator
│   ├── design_ai.py           # Option B: LLM HTML design + repair loop + variants
│   ├── design_style.py        # Option C: reference image → style profile JSON
│   ├── design_contract.py     # design validator (shared by B, C and import checks)
│   ├── design_import.py       # shared: HTML/image → layout, background, theme
│   ├── pbip_builder.py        # write PBIP project
│   └── validator.py           # schema + DAX + layout checks
├── llm/
│   ├── client.py              # provider-agnostic LLM layer (Gemini now, Claude later)
│   └── prompts/               # prompt files per module
├── templates/
│   ├── tmdl/                  # TMDL templates
│   ├── visuals/               # visual.json templates per visual type
│   ├── themes/                # base theme JSON
│   └── designs/               # built-in HTML design templates per style preset (Option B fallback)
├── kpi_library/               # industry KPI definitions (JSON)
├── samples/                   # sample datasets for testing
├── output/                    # generated projects
├── requirements.txt
└── README.md
```

---

## 8. Pricing

### 8.1 Software (SaaS — after MVP is stable)

| Plan | Price / month (India) | Includes |
|---|---|---|
| Free | ₹0 | 1 dashboard/month, watermark, sample datasets; design method **B (DashPilot AI)** |
| Student | ₹299 – ₹499 | 5 dashboards/month, portfolio use; design method **B (DashPilot AI)** |
| Pro (freelancers/analysts) | ₹999 – ₹1,999 | 25 dashboards/month, all design styles, documentation PDF; design methods **A, B and C** |
| Team / Agency | ₹4,999 – ₹9,999 | Unlimited (fair use), multiple users, brand kits per client, multi-page dashboards; **all design methods + custom brand kits** |

- **Pay-per-dashboard option:** ₹199 – ₹499 per dashboard
- **International:** $9 – $19 (Pro), $49 – $99 (Team)
- Design methods per plan: Free/Student = B only; Pro = A, B, C; Agency = all + custom brand kits (enforced with the V4 usage limits)

### 8.2 Service (start earning while building the SaaS)
Use your own tool to sell dashboard services:

| Service | Price (India) |
|---|---|
| Single-page dashboard | ₹5,000 – ₹10,000 |
| Multi-page dashboard + documentation | ₹15,000 – ₹35,000 |
| Monthly dashboard maintenance / refresh | ₹3,000 – ₹10,000/month |
| International clients (Upwork/Fiverr/direct) | $100 – $500+ per dashboard |

### 8.3 Cost estimate
- AI API: Gemini free tier during development (₹0, rate-limited; public/sample data only). Claude API later: roughly ₹20 – ₹150 per dashboard (depends on data size and retries)
- Hosting: low in V1 (local/Streamlit Cloud)
- Healthy margin on all plans.

*All prices are estimates — check current API pricing and competitor rates before finalising.*

---

## 9. Build Roadmap

| Version | Timeline | Scope |
|---|---|---|
| **V1 — MVP** | 2–3 weeks | CSV/Excel upload, profiling, cleaning (M code), single-table + auto date table model, 10–15 DAX measures, business questions + insights, design method B (DashPilot AI design + validator + template fallback), shared HTML design import, single-page PBIP build, ZIP download |
| **V2** | +2–3 weeks | Multi-table star schema, relationships, design method C (reference image style profile), design method A (Stitch prompt + Stitch HTML import), image upload fallback with mapping editor, industry KPI library (5 industries), documentation PDF |
| **V3** | +3–4 weeks | Multi-page dashboards, drill-through pages, more visual types, style variants, brand kits |
| **V4** | +4 weeks | Next.js SaaS frontend, login, billing, usage limits, cloud storage |
| **V5** | later | Database connectors (SQL, Google Sheets), Power BI Service publish via API, team features |

**First niche for V1 testing:** Sales / e-commerce data (easy to find sample datasets, KPIs are standard).

---

## 10. How We Build It with Claude / Antigravity

### Working rules
- Build **one module at a time**, test it with a sample dataset, then move on
- Keep this spec file in the project folder and tell the AI to follow it
- Commit to Git after every working module
- Before building the PBIP builder: create 2–3 sample reports in Power BI Desktop, **save as PBIP** (File → Save as → Power BI Project), and give these files to the AI as reference — this is the single most important step for getting valid output
- Test every generated PBIP by opening it in Power BI Desktop

### Build order (one prompt/session per step)
1. Project setup: folder structure, requirements, Streamlit wizard skeleton, LLM provider layer (Gemini now, Claude later)
2. Upload + profiling (Data Quality Report UI)
3. Cleaning suggestions + Power Query M generation
4. Business context form + brand palette
5. Date table + simple model + DAX measures (with validation against pandas)
6. Business questions + insights
7. Dashboard planner + "Choose design method" screen
8. **PBIP builder** (start with: one card + one line chart + one bar chart, open in Power BI Desktop, then expand)
9. Shared design import from contract HTML (positions, background PNG, theme JSON) — built once, used by all three methods
10. Design method **B** — DashPilot AI design: design contract + validator, LLM repair loop (max 2 retries), built-in HTML templates per style preset as fallback, 2–3 variants with preview images, restyle/regenerate
11. Design method **C** — reference image → editable style profile JSON → Option B generation with that style
12. Design method **A** — Stitch prompt generator + Stitch HTML/image upload into the shared import
13. Validator + ZIP download
14. End-to-end test with 3 different datasets → fix → record demo video

### Day 1 checklist
- [ ] Install Python 3.11+, VS Code / Antigravity, Git, Power BI Desktop (Windows)
- [ ] Get a free Gemini API key from Google AI Studio (Claude API key later)
- [ ] Download 2–3 sample datasets (sales, food delivery orders, HR attrition)
- [ ] In Power BI Desktop, enable PBIP/PBIR save options if needed, build one tiny report (card + line + bar), save as PBIP → keep as reference
- [ ] Create the project folder and complete build step 1 and 2

---

## 11. Success Metrics
- Time from upload to working dashboard: target < 30 minutes
- % of generated PBIP projects that open in Power BI Desktop without errors: target > 95%
- % of DAX measures that pass validation: target > 95%
- Design match: generated dashboard visually matches the chosen design — Stitch, AI or reference-styled (manual review score)
- AI designs (Options B/C) that pass the design validator without the template fallback: target > 90%
- First 10 paying users / first 5 service clients

---

## 12. Career Angle
- Post the build journey on LinkedIn (weekly updates + demo video)
- Put it on GitHub with a clear README and screenshots
- In interviews: explain data modelling, DAX, Power Query, design thinking and automation — all in one project
