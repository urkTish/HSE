# HSE Platform

Digital HSE management platform for an HSE Manager on construction and airport projects in the Kingdom of Saudi Arabia.

- `backend/` — FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, KPI engine, AI layer (Claude API with tool use)
- `frontend/` — Next.js (App Router), TypeScript, Tailwind, shadcn/ui, next-intl (English + Arabic, full RTL)
- `docs/specs/` — Module Specs written by the HSE Consultant (requirements authority)
- `docs/contracts/openapi.yaml` — API contract between backend and frontend
- `docs/PROGRESS.md` — current phase, done / next / parked / open questions
- `docs/DECISIONS.md` — non-obvious decisions

Build order is fixed: Foundation → Dashboard (with AI) → Site/Airport permits → PTW → 3rd-party certification → Training certificates → other essentials.
