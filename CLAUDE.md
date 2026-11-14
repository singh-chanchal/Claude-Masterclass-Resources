# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

HireTrack AI: a job-seeker app (resume ↔ job AI matching + application Kanban + dashboard). The source spec is `Final-Specification-Doc.pdf` (product/tech spec, Nov 2026); `README.md` lists the product decisions taken where the spec was silent.

## Commands

Backend (run from `backend/`, venv at `backend/.venv`):
- Dev server: `.venv/bin/uvicorn app.main:app --reload --port 8000` (OpenAPI docs at `/docs`)
- All tests: `.venv/bin/python -m pytest -q`
- Single test: `.venv/bin/python -m pytest -q tests/test_api.py::test_dashboard_metrics`
- Demo data: `.venv/bin/python seed.py` (recreates `demo@hiretrack.ai` / `demo1234`)
- Offline AI: `AI_PROVIDER=fake` (env or `.env`, e.g. `AI_PROVIDER=fake .venv/bin/uvicorn ...`) swaps Claude for a keyword matcher. With `AI_PROVIDER=claude` and an empty `ANTHROPIC_API_KEY`, every match request returns 502.

Frontend (run from `frontend/`):
- `npm run dev` (port 5173; Vite proxies `/api` → `localhost:8000`), `npm run build`
- No linter, formatter or frontend tests are configured; `npm run build` is the only frontend check.

## Architecture

Three tiers: React SPA → FastAPI JSON API with a Bearer JWT → SQLite (SQLAlchemy 2.0, sync). Only the backend talks to the DB and to Claude.

Backend layering (`backend/app/`), per spec §6 — keep it this way:
- `routers/` only validate (Pydantic schemas in `schemas.py`) and delegate. Every route except signup/login takes `get_current_user` and passes `user.id` down.
- `services/` hold the rules: stage transitions and `applied_date` (`application_service`), dashboard maths incl. response-rate definition and Monday–Sunday week (`dashboard_service`), match flow (`match_service`), one-active-resume invariant (`resume_service`). Services raise `services/errors.py` `NotFound`/`BadRequest`, mapped to 404/400 in `main.py`.
- `ai/client.py` is the only module that knows about Claude. Services depend on the `AIClient` protocol; `get_ai` in `deps.py` is the injection point (tests override it with `FakeAIClient`). Claude is called via `client.beta.messages.parse` with a Pydantic `MatchResult` output schema, `effort: low` (for the <15s target) and server-side refusal fallbacks. All SDK failures become `AIError` → HTTP 502 with a user-safe message.

Data rules worth knowing:
- Ownership: `users` → `resumes`/`matches`/`applications` carry `user_id`; `interviews` are owned through their application. Ownership checks live in the services (`get_owned`, `_get_owned`) — a foreign row is reported as 404, never 403.
- SQLite needs `PRAGMA foreign_keys = ON` per connection for `ON DELETE CASCADE`; `database.make_engine` does this (and the test fixture repeats it). `applications.match_id` is `ON DELETE SET NULL`.
- Tables are created with `Base.metadata.create_all` on startup (no migrations). Changing a column on an existing DB means deleting `backend/hiretrack.db` and re-seeding.
- Timestamps are naive **local** time (`default=datetime.now`), and interviews are stored naive local as typed in the browser's `datetime-local` input; keep that consistent, because "interviews this week" compares against `datetime.now()`.
- `missing_skills` / `suggested_bullets` are JSON-encoded TEXT columns; `match_service.to_out` decodes them.

Auth (`security.py`, `services/auth_service.py`):
- Passwords are bcrypt-hashed (`hash_password` / `verify_password`). JWTs are stateless with nothing stored server-side, so logout and change-password don't revoke issued tokens. Adding revocation would need a new `users` column, which means a DB reset (see "no migrations" above).
- Password schemas use `max_length=72`, which counts characters, but bcrypt 5 raises `ValueError` above 72 **bytes**. A long non-ASCII password therefore currently causes a 500 error.
- Because `api.js` logs the user out on any 401, an in-session credential check that fails (e.g. a wrong current password on `/api/auth/change-password`) must return 400 (`BadRequest`), not 401.

Frontend (`frontend/src/`): plain JS + React Router, no state library. `api.js` is the single fetch wrapper (adds the JWT from localStorage, turns FastAPI `detail` into messages, triggers logout on 401). `auth.jsx` holds the user context. Pages: Dashboard, Pipeline (native HTML5 drag-and-drop, optimistic stage moves, plus a per-card stage `<select>` for touch/keyboard), MatchPage, ResumePage. Styling is one `styles.css` with CSS variables and a dark-mode override.

Tests (`backend/tests/`) use an in-memory SQLite `StaticPool` plus dependency overrides for `get_db` and `get_ai`; they never call the real Claude API. `conftest.py` provides the `client` and `auth` (headers for a signed-up user) fixtures and a `signup(client, email=..., name=...)` helper for multi-user tests; the test password is `password123`.
