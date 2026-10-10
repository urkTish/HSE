# Engineering conventions (shared by all agents)

These pin the details the build plan leaves open so backend and frontend integrate without negotiation.

## Repo
- `backend/` (Python 3.12, uv project, package `app`), `frontend/` (Next.js App Router, TypeScript strict), `docs/`.
- Root `docker-compose.yml`: `db` (postgres:16), `backend` (port 8000), `scheduler`, `frontend` (port 3000). Attachments are stored on local disk (`STORAGE_DIR`), so there is no object-storage service (MinIO was removed: its Docker Hub image no longer exists).
- CI: `.github/workflows/ci.yml` with a `backend` job and a `frontend` job.

## Backend
- Run: `cd backend && uv run uvicorn app.main:app --reload --port 8000`.
- API prefix: `/api/v1`. Health: `GET /api/v1/health`.
- DB URL env `DATABASE_URL`, default `postgresql+psycopg://hse:hse@localhost:5432/hse`; tests use `TEST_DATABASE_URL` default `postgresql+psycopg://hse:hse@localhost:5432/hse_test`.
- Migrations: Alembic (`uv run alembic upgrade head`). Seed: `uv run python -m app.seed` (password from env `SEED_PASSWORD`, dev default only in `.env.example`).
- Contract: generated from FastAPI and committed: `uv run python -m app.export_openapi` writes `docs/contracts/openapi.yaml`. CI fails if it is stale. `info.version` is bumped per module (`contract: <module> vX`).
- Errors: JSON `{"detail": {"code": "<machine_code>", "message": "<english text>", "message_ar": "<arabic text, optional>"}}`; 401 unauthenticated, 403 forbidden capability, 404 not found or out of scope, 409 invalid state transition, 422 validation.
- Auth: `POST /api/v1/auth/login` sets an httpOnly, SameSite=Lax cookie `hse_session` (JWT) and also returns `{access_token, user}`; the API accepts the cookie or `Authorization: Bearer`. `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- Lists: `?page=1&page_size=50` → `{items, total, page, page_size}`.
- Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`.

## Frontend
- Run: `cd frontend && npm run dev` (port 3000). Next.js rewrites `/api/v1/:path*` to `${BACKEND_URL:-http://localhost:8000}/api/v1/:path*`, so the browser is same-origin and the cookie just works.
- Types: `npm run gen:api` runs openapi-typescript on `../docs/contracts/openapi.yaml` → `src/lib/api/schema.d.ts`.
- Mock: `npm run mock` runs Prism on the contract (port 4010) for building before the backend is ready.
- i18n: next-intl, locales `en` and `ar` in the URL (`/en/...`, `/ar/...`), `dir="rtl"` for `ar`, messages in `messages/en.json` and `messages/ar.json`.
- Design tokens in one file (`src/styles/tokens.css` + Tailwind theme mapping).
- Checks: `npm run lint && npm run typecheck && npm run build && npm run test:e2e`.
- Playwright locally: Chromium at `/opt/pw-browsers` (do not run `playwright install` locally; CI installs it).
