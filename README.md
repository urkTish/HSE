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

## Sending email

Emails (invites, password resets, alerts, report packs) are written to the `email_outbox` table and sent by the `scheduler` service every minute over SMTP. Any provider works (Microsoft 365, Google Workspace, Amazon SES, SendGrid, Mailgun, a local relay). Without settings nothing is sent and the emails wait in the outbox.

Set these in `.env` (see `.env.example`) and restart `backend` and `scheduler`:

| Setting | Example | Notes |
|---|---|---|
| `SMTP_HOST` | `smtp.office365.com` | empty = sending off |
| `SMTP_PORT` | `587` | 587 for STARTTLS, 465 for SSL |
| `SMTP_SECURITY` | `starttls` | `starttls`, `ssl` or `none` (only for a relay on the same server) |
| `SMTP_USER` / `SMTP_PASSWORD` | `hse@client.sa` / app password | leave empty if the relay needs no login |
| `SMTP_FROM` | `HSE Platform <hse@client.sa>` | must be an address the provider lets you send from |

Check the settings with a test message:

```bash
docker compose exec backend python -m app.services.mailer test you@example.sa
```

Failed messages are retried with growing waits (1, 2, 4 … minutes, `EMAIL_MAX_ATTEMPTS` tries); a message refused by the server (5xx) is marked failed at once. Emails older than `EMAIL_MAX_AGE_HOURS` (72) are not sent any more (their links would have expired). Report-pack emails to external members carry the PDF / XLSX files (at most 20 MB); their delivery log shows queued, sent or failed.
