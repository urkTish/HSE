# HSE Platform

Digital HSE management platform for an HSE Manager on construction and airport projects in the Kingdom of Saudi Arabia.

- `backend/` — FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, KPI engine, AI layer (Claude API with tool use)
- `frontend/` — Next.js (App Router), TypeScript, Tailwind, shadcn/ui, next-intl (English + Arabic, full RTL)
- `docs/specs/` — Module Specs written by the HSE Consultant (requirements authority)
- `docs/contracts/openapi.yaml` — API contract between backend and frontend
- `docs/PROGRESS.md` — current phase, done / next / parked / open questions
- `docs/DECISIONS.md` — non-obvious decisions

Build order is fixed: Foundation → Dashboard (with AI) → Site/Airport permits → PTW → 3rd-party certification → Training certificates → other essentials.

## How to run

Demo login (every demo user has the same password): **faisal.harbi@example.com** / **Demo-Passw0rd!2026** (HSE Manager). Other roles are listed in `backend/app/seed.py`.

### On a phone or any browser (GitHub Codespaces, no install)

1. Open https://codespaces.new/urkTish/HSE?ref=claude/hse-platform-build-kannxy in the browser and tap **Create codespace** (or on github.com: **Code → Codespaces → Create codespace** on this branch).
2. Wait for the first build (several minutes). It starts everything and loads the demo data by itself.
3. Open the **Ports** tab and open port **3000** ("HSE app"), then log in with the demo account above.

Codespaces is free within GitHub's monthly allowance. Stop the codespace when you are done.

### On a laptop with Docker (simplest)

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend python -m app.seed   # demo data, safe to re-run
```

Open http://localhost:3000.

### On a laptop without Docker

Needs PostgreSQL 16 (user/password/database `hse`), [uv](https://docs.astral.sh/uv/) and Node.js 22.

```bash
cp .env.example .env
set -a; . ./.env; set +a      # load the settings into this shell

cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --port 8000      # keep running

# in a second terminal
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000.
