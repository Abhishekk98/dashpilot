# DashPilot

Your AI co-analyst for Power BI: upload data → profile, clean, model, DAX, insights →
Google Stitch design prompt → design import → ready-to-open Power BI Project (PBIP).

See `ai-powerbi-analyst-project-spec.md` for the full spec and `CLAUDE.md` for stack and conventions.

## Prerequisites
- Node.js 20+ and npm
- Python 3.11
- A free Gemini API key (see below); a Claude API key only if you switch providers later

## Run the backend (FastAPI)

Windows (PowerShell):
```powershell
cd backend
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env      # then add your GEMINI_API_KEY (see "AI provider setup")
uvicorn app.main:app --reload --port 8000
```

macOS / Linux:
```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Check it: open http://localhost:8000/api/health (API docs at http://localhost:8000/docs).

Run tests: `pytest` (inside `backend/` with the venv active).

## Run the frontend (Next.js)

In a second terminal:
```bash
cd frontend
npm install
copy .env.example .env.local   # Windows (macOS/Linux: cp)
npm run dev
```

Open http://localhost:3000. The footer shows **System Status: Normal** when the backend is reachable.

Lint and production build: `npm run lint` and `npm run build`.

## AI provider setup (Gemini now, Claude later)

All AI calls go through `backend/llm/`, and `LLM_PROVIDER` in `backend/.env` decides which provider is used.

**1. Get a free Gemini API key**
1. Open https://aistudio.google.com/apikey and sign in with a Google account.
2. Click **Create API key** (pick or create a Google Cloud project when asked).
3. Copy the key. Free-tier limits per model are shown at https://aistudio.google.com/rate-limit.

**2. Create `backend/.env`**
```powershell
cd backend
copy .env.example .env        # macOS/Linux: cp .env.example .env
```
Open `backend/.env` and set:
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=                 # empty = gemini-3.6-flash
```
`.env` is git-ignored; never commit it or paste the key anywhere else.

**3. Check the key works**: start the backend and open http://localhost:8000/api/llm/test.
You should see `{"provider": "gemini", "model": "...", "response": "OK", ...}`.
A 503 means the key is missing, a 429 means the free-tier quota is used up (wait and retry).

> Free tier: Google may use free-tier prompts to improve its models, so only use public or
> sample datasets during development, never real client data.

**Switching to Claude later**
```
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=your-anthropic-key
CLAUDE_MODEL=                 # empty = claude-opus-5-5
```
Restart the backend and call `/api/llm/test` again. No code changes are needed.

## Try it with sample data

`backend/samples/sales/` has a small sales dataset (orders.csv, customers.xlsx, products.csv).
Open http://localhost:3000/project/upload and drop those three files in. Regenerate them with
`python samples/generate_samples.py` (inside `backend/`).

With an AI key configured, the active LLM refines the semantic roles; without one,
profiling still works with rule-based roles.

## API (so far)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + active AI provider/model and whether its key is set |
| GET | `/api/llm/test` | Sends "Reply with OK" to the active AI provider |
| POST | `/api/projects` | Create a project |
| GET | `/api/projects/{id}` | Project with its files |
| POST | `/api/projects/{id}/files` | Upload CSV/Excel (multipart `files`) |
| DELETE | `/api/projects/{id}/files/{file_id}` | Remove a file |
| GET | `/api/projects/{id}/profile` | Data Quality Report (`?refresh=true` to re-run) |
| GET | `/api/projects/{id}/profile/columns.csv` | Column profile export |

## Project layout
```
frontend/   Next.js app (App Router, TypeScript, Tailwind v4): app shell, routes, UI components
backend/    FastAPI app
  app/          main.py, config.py, api/routes/ (health)
  core/         spec modules (upload, profiling, cleaning, ... validator) - placeholders for now
  llm/          provider-agnostic AI layer (Gemini, Claude) + prompts/
  templates/    TMDL / visual / theme templates for the PBIP builder
  kpi_library/  industry KPI definitions
  samples/      sample datasets
  output/       generated Power BI projects (git-ignored)
  storage/      uploaded files + project JSON (git-ignored, created on first upload)
  tests/        pytest
stitch_dashpilot_ai_dashboard_studio/   Stitch designs (read-only)
ai-powerbi-analyst-project-spec.md      Product spec (read-only)
```
