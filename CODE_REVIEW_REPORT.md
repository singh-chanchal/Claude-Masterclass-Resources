# HireTrack AI — Codebase Review Report

Date: 2026-11-14 · Scope: `backend/` (FastAPI), `frontend/` (React/Vite), repo hygiene, tests, docs.
Method: full read of every source file, `pytest` (21 passed), `npm run build` (OK), plus small probe requests against an in-memory DB to reproduce suspected bugs.

**Legend:** ✅ reproduced by running it · 🔎 found by reading the code (not executed) · Severity: High / Medium / Low

## 0. Executive summary

The architecture is clean (routers → services → AI adapter, ownership checks, 404-not-403, injectable AI client) and the happy paths work. The problems are mostly at the edges:

| # | Finding | Sev | Status |
|---|---|---|---|
| 1 | `.env`, `hiretrack.db` and `__pycache__` are tracked in the nested `backend` git repo; the outer repo only stores `backend` as a gitlink | High | ✅ |
| 2 | Non-ASCII password (>72 bytes, ≤72 chars) → HTTP 500 on signup and change-password | High | ✅ |
| 3 | `PATCH /applications/{id}` with `company: null` / `role: null` → HTTP 500 | High | ✅ |
| 4 | Default/placeholder JWT secret with no startup guard (PyJWT already warns the key is too short) | High | ✅ |
| 5 | `/api/matches` has no rate limit or quota; each call is a paid Claude request | High | 🔎 |
| 6 | Blocking AI call holds a DB connection and a worker thread for up to ~60 s | High | 🔎 |
| 7 | `async def upload_resume` runs PDF parsing + DB writes on the event loop | High | 🔎 |
| 8 | Stateless JWT: change-password revokes nothing | Medium | 🔎 (documented) |
| 9 | Timezone handling: naive server-local time; tz-aware input silently stripped | Medium | ✅ |
| 10 | "One active resume" and "one application per match" are not enforced by the DB | Medium | 🔎 |
| 11 | Input validation gaps (blank strings, `javascript:` URLs, unbounded text) | Medium | ✅ |
| 12 | Missing indexes on FK columns | Medium | ✅ |
| 13 | Frontend: transient `/me` failure logs the user out; Enter on stage `<select>` opens modal; misleading errors | Medium/Low | 🔎 |
| 14 | Test gaps (no tests for the new bugs, PDF success path, AI client, cross-user resume/match/interview access) | Medium | 🔎 |

---

## 1. Repository & configuration

### 1.1 Secrets and runtime state are committed (High) ✅
- `backend/` is its **own git repository** (`git -C backend rev-parse --show-toplevel` → `backend`). In the outer repo it is a bare gitlink (no `.gitmodules`), so outer commits do **not** contain backend source and cloning the outer repo gives an empty `backend/`.
- The outer `.gitignore` rules (`backend/.env`, `backend/*.db`, `__pycache__/`) only apply to the outer repo. The inner repo has **no `.gitignore`**, and `git -C backend ls-files` includes `.env`, `hiretrack.db` and many `*.pyc`. That is why `git status` shows `hiretrack.db` and `.pyc` files as modified.
- `.env` currently holds only the placeholder secret and an empty API key, but the next person who pastes a real `ANTHROPIC_API_KEY` will commit it.
- Also: `.CLAUDE.md.swp` (vim swap file) is untracked in the root; `CLAUDE.md` is modified and open in an editor.

**Fix:** decide on one repo. Either remove `backend/.git` and track `backend/` in the root repo, or add a proper `.gitmodules`. Then:
```bash
cd backend && printf '.venv/\n.env\n*.db\n__pycache__/\n.pytest_cache/\n' > .gitignore
git rm -r --cached .env hiretrack.db app/__pycache__ app/*/__pycache__ tests/__pycache__
```
Add `*.swp` to the root `.gitignore`. If a real key was ever committed, rotate it. History still contains `.env` and the DB, so purge it with `git filter-repo` if that matters.

### 1.2 Weak default JWT secret (High) ✅
`config.py` defaults `jwt_secret` to `"dev-secret-change-me"` (20 bytes). Running with it produced PyJWT's `InsecureKeyLengthWarning`. If someone deploys without a `.env`, anyone can forge tokens for any user id.
**Fix:** make the setting required (no default) or fail on startup when it equals a known placeholder or is shorter than 32 bytes. `python -c "import secrets;print(secrets.token_urlsafe(48))"` for generation.

### 1.3 Dependency pinning (Medium) 🔎
`requirements.txt` uses only lower bounds (`anthropic>=0.70`, installed is 2.8.0). `client.py` relies on `fallbacks=`, `output_config=` and a dated beta header, which older SDKs lack. A fresh install resolving an old version gets a `TypeError`, which `ClaudeAIClient` re-raises as a 500. There is no Python lockfile. `package.json` uses `^` ranges (a lockfile exists).
**Fix:** pin with `pip-compile`/`uv lock`, raise the `anthropic` floor to the version you tested, and wrap `TypeError` handling more narrowly (see 4.3).

### 1.4 Minor config items (Low) 🔎
- `/docs`, `/openapi.json` and `/api/health` (which reveals `ai_provider`) are exposed in every environment.
- `logging.basicConfig(level=INFO)` makes httpx log every outbound request line.
- README says Python 3.11+, the venv is 3.14; there's no CI to catch drift.
- `seed.py` creates a known `demo@hiretrack.ai / demo1234` account with no environment guard. Never run it against a real DB.

---

## 2. Backend bugs

### 2.1 Non-ASCII password causes a 500 (High) ✅
`SignupIn`/`ChangePasswordIn` use `max_length=72` (characters). bcrypt 5 raises `ValueError` above 72 **bytes**. `verify_password` catches it, `hash_password` doesn't. Reproduced: a 40-character password of `é` (80 bytes) → `POST /api/auth/signup` = **500**. The new `change-password` endpoint has the same hole, and the frontend modal's `maxLength={72}` has the same character-vs-byte gap.
**Fix (either):**
```python
# schemas.py
from pydantic import field_validator
def _bcrypt_len(v: str) -> str:
    if len(v.encode()) > 72:
        raise ValueError("Password must be at most 72 bytes (long non-ASCII passwords count extra).")
    return v
# add @field_validator("password") on SignupIn and @field_validator("new_password") on ChangePasswordIn
```
or pre-hash with SHA-256 + base64 before bcrypt (removes the limit; do it in one place, `security.py`, and keep verifying old hashes if you already have users). Add a test with `"é"*40`.

### 2.2 `PATCH /api/applications/{id}` accepts explicit nulls for required fields (High) ✅
`ApplicationUpdate.company/role` are `str | None`. The router uses `model_dump(exclude_unset=True)`, so `{"company": null}` is "set", then `setattr(app, "company", None)` violates `NOT NULL` → **500**. Reproduced for both `company` and `role`.
**Fix:** reject nulls for non-nullable fields:
```python
@model_validator(mode="after")
def _no_null_required(self):
    for f in ("company", "role"):
        if f in self.model_fields_set and getattr(self, f) is None:
            raise ValueError(f"{f} cannot be null")
    return self
```
(or define them as `str = Field(min_length=1, ...)` with a default sentinel and rely on `exclude_unset`).

### 2.3 Blank / whitespace-only values pass validation (Medium) ✅
`{"company": "  "}` creates an application with a blank company (min_length counts spaces). `SaveMatchIn` strips in the service but `ApplicationIn/Update` don't strip `company`/`role`.
**Fix:** `str_strip_whitespace=True` in `model_config` (or a `field_validator` that strips, then `min_length=1`).

### 2.4 Unvalidated `job_url` (Medium) ✅
`javascript:alert(1)` was accepted and stored. The UI currently doesn't render `job_url` as a link, so it's latent. The moment someone adds `<a href={app.job_url}>` it becomes stored XSS.
**Fix:** `job_url: AnyHttpUrl | None` (store `str(url)`) or a validator that allows only `http`/`https`; apply to `ApplicationIn`, `ApplicationUpdate`, `SaveMatchIn`. Also add max lengths to `job_url`, `notes` (both models) — currently unbounded `Text`.

### 2.5 Resume PDF text isn't length-capped (Medium) 🔎
Pasted text is limited to 50 000 chars (`ResumeTextIn`), but text extracted from a PDF is not. A 5 MB PDF can yield hundreds of thousands of characters that are stored and then sent to Claude on every match (cost + context limit → 502).
**Fix:** enforce the same cap in `resume_service.create_resume`/`extract_pdf_text` (reject or truncate with a notice).

### 2.6 Upload handler blocks the event loop (High) 🔎
`upload_resume` is `async def` but calls the synchronous `extract_pdf_text` (CPU-bound pypdf) and sync SQLAlchemy inside it. While a large PDF parses, the **entire server stalls**.
**Fix:** make it `def` and read via `file.file.read(MAX+1)` (FastAPI runs it in the threadpool), or `await run_in_threadpool(...)` for the parse and DB calls.
Related 🔎: `extract_pdf_text` only catches `PdfReadError, ValueError, KeyError`. Other pypdf failures (e.g. `DependencyError` for AES-encrypted PDFs without `cryptography`, `NotImplementedError`, `RecursionError` on crafted files) would be 500s. Garbage/empty/truncated inputs I tried were all correctly 400. Consider `except Exception` → `BadRequest` around the parse, plus a page-count cap.

### 2.7 Signup race and login enumeration (Low/Medium) 🔎
- Two concurrent signups with the same email both pass the `select` check; the second hits the unique constraint → `IntegrityError` → 500. Catch `IntegrityError` and raise `BadRequest`.
- `authenticate` returns before running bcrypt when the user doesn't exist, so response time reveals which emails are registered. Run a dummy `verify_password` against a fixed hash in that branch.
- Queries use `func.lower(User.email)`, which defeats the unique index (emails are already stored lowercase; compare `User.email == email`).
- Login has no throttling/lockout (see 3.2).

### 2.8 Dashboard semantics (Low/Medium) 🔎
- An application moved back to **Wishlist** keeps its `applied_date`, so it still counts as "sent" (`applied_date is not None`) and inflates/deflates the response rate.
- Interviews belonging to **Rejected** applications are still counted in "this week" and "upcoming".
- "This week" counts interviews already in the past this week; the label doesn't say so.
- A Rejected application with an `applied_date` counts as a *reply* even if it was an auto-rejection or ghosted-then-closed. These are product decisions recorded in the README; just confirm they're intended.
- `get_dashboard` loads every application row into Python; fine now, use SQL aggregates if volumes grow.

### 2.9 Application list and API surface (Low) 🔎
`GET /applications` and `GET /resumes` are unpaginated; `list_matches` is capped at 20 with no way to page. Ordering by `updated_at desc` makes Kanban cards jump after any edit. There is no endpoint to edit an interview, delete a match, delete the account, or reset a forgotten password. `delete_interview` doesn't bump the parent's `updated_at` (add does).

---

## 3. Security

### 3.1 Token model (Medium) 🔎
JWTs live 24 h in `localStorage`, are never revoked, and `change-password` does not invalidate them (documented in CLAUDE.md). A user who changes their password because a token leaked is still exposed for up to a day. Any XSS also exfiltrates the token.
**Fix:** add `users.token_version` (int) embedded as a claim and checked in `get_current_user`; bump it on password change (requires the DB reset noted in CLAUDE.md, or introduce Alembic). Optionally shorten expiry plus refresh tokens in an `HttpOnly` cookie.

### 3.2 No abuse controls (High for `/matches`, Medium for login) 🔎
- `POST /api/matches` triggers a paid Claude call per request with no per-user quota, rate limit, or daily cap. One script can burn the API budget. Add a per-user limiter (e.g. `slowapi`, or count rows in `matches` per day) and a global spend guard.
- No rate limiting/lockout on `/login` or `/signup`; bcrypt makes brute force slower, not impossible.
- No request-body size limit besides the PDF read cap; large JSON bodies are parsed before validation.

### 3.3 Prompt-injection surface (Low) 🔎
The resume and JD are interpolated between `<resume>`/`<job_description>` tags. A JD containing `</job_description>` can break out of the tag structure. The system prompt tells the model to treat the content as data, which helps, but escape or strip those tag strings from user input. Output is schema-constrained and sanitised in `_normalise`, so impact is limited to a manipulated score.

### 3.4 Misc (Low) 🔎
CORS is correctly restricted to configured origins. Add security headers (CSP, `X-Content-Type-Options`) at the proxy for production. Error messages from the AI layer are user-safe; good.

---

## 4. AI integration (`ai/client.py`, `match_service.py`)

### 4.1 Latency budget (High) 🔎
`timeout=30` with `max_retries=1` means a failing call can take ~60 s+ before the user sees an error, against the spec's 15 s target. The UI text says "usually 5–15 seconds" and has no cancel.
**Fix:** lower the timeout (e.g. 20 s total), disable retries for timeouts, or enforce an overall deadline.

### 4.2 DB connection and thread held during the AI call (High) 🔎
`run_match` is a sync route: it opens a session (Depends `get_db`), reads the active resume, then blocks in the Claude call. The default pool for file SQLite is 5 + 10 overflow, and Starlette's threadpool is ~40, so ~15 concurrent matches (or fewer slow ones) exhaust the pool and other requests start timing out after 30 s.
**Fix:** read the resume text, `db.close()`/release the transaction, call the AI, then open a short write transaction; or run the AI call via an async client with a semaphore.

### 4.3 Brittle error handling (Medium) 🔎
- `except TypeError` with `"authentication" in str(e)` depends on SDK message wording; anything else is re-raised as a 500 (including the old-SDK case in 1.3). Check for the missing key up front in `get_ai_client()` and raise `AIError` there.
- `fit_score` has no bounds in the schema (clamped later in `_normalise`; fine, but add `ge=0, le=100` to give the model the constraint). `suggested_bullets` "exactly three" is only prompt-enforced; fewer is silently accepted.
- Refusals, `max_tokens` stops, and parse failures all log nothing; add a warning log with the stop reason to make production issues diagnosable.
- The dated beta header (`server-side-fallback-2026-07-01`) is a moving target; put it behind a setting so it can be turned off without a deploy.

### 4.4 Match persistence (Medium) 🔎
`save_as_application` checks "already saved" with a SELECT, but `applications.match_id` has no unique constraint, so two concurrent clicks create duplicates. Add `UniqueConstraint("match_id")` (NULLs are allowed multiple times in SQLite and Postgres).
`company`/`role` guesses are returned only on the creation response, not in history, so re-opening a past match from "Recent matches" loses the prefilled Save form values.

---

## 5. Data model & database

### 5.1 Invariants not enforced in the schema (Medium) 🔎
- **One active resume per user** is application logic only. Concurrent uploads (or the non-atomic `delete` → `activate` in `resume_service.delete`, which commits twice) can leave zero or two active rows; `get_active` then silently returns an arbitrary one.
  Fix: partial unique index `CREATE UNIQUE INDEX uq_resume_active ON resumes(user_id) WHERE is_active` (SQLAlchemy: `Index(..., unique=True, sqlite_where=..., postgresql_where=...)`) and do delete+promote in one transaction.
- `applications.stage` is a free `String(16)` with no `CHECK` constraint.

### 5.2 Missing indexes (Medium) ✅
Existing indexes: `applications(user_id)`, `applications(user_id, stage)`, `matches(user_id)`, `interviews(scheduled_at)`, `resumes(user_id)`. Missing on foreign keys that are filtered, joined, or cascaded on: `interviews.application_id` (every dashboard join, `selectinload`, and cascade delete), `applications.match_id`, `matches.resume_id`. SQLite doesn't auto-index FKs; Postgres doesn't either.

### 5.3 No migrations (Medium) 🔎
`create_all` only. Every schema change (including the `token_version` and constraints above) means deleting `hiretrack.db`. Adopt Alembic before real users exist.

### 5.4 Time handling (Medium) ✅
All timestamps and `date.today()` use the **server's** local naive time, while interviews are the browser's local time. This is consistent only when browser and server share a timezone (true on a dev laptop, false once deployed to a UTC host): "interviews this week", "upcoming", and `applied_date` will be off by the offset. Additionally the router does `scheduled_at.replace(tzinfo=None)` which **drops** the offset instead of converting; probe: `2026-11-14T09:00:00+05:30` was stored as `09:00` unchanged (and a `Z` timestamp would be misread the same way). The frontend currently sends naive strings, so this is latent.
**Fix:** store UTC (timezone-aware) and send the browser's IANA zone (or compute week bounds client-side) for the dashboard; or at minimum convert with `astimezone(local).replace(tzinfo=None)` and document the single-timezone assumption.

### 5.5 Test runs touch the real database (Low) 🔎
`conftest.py` overrides `get_db`, but `TestClient(app)` still runs the app's `lifespan` → `init_db()` on the **real** engine, so every `pytest` run creates/updates `backend/hiretrack.db` (consistent with the DB showing as modified). Set `DATABASE_URL=sqlite://` in a fixture/`conftest` before importing the app, or patch `init_db` out.

---

## 6. Frontend

| # | Where | Issue | Sev |
|---|---|---|---|
| F1 | `auth.jsx:19` | On startup, *any* `/me` failure (network blip, 500) clears the token → user is logged out. Only clear on 401. | Medium |
| F2 | `Pipeline.jsx:9` | `onKeyDown` on the card fires for Enter pressed in the inner stage `<select>` (event bubbles) and opens the modal. Guard with `e.target === e.currentTarget`. | Medium |
| F3 | `Pipeline.jsx:39-47` | Optimistic move rolls back to a stale `prev` snapshot; two quick moves can restore wrong state. Roll back only the one card. | Low |
| F4 | `MatchPage.jsx:90` | If `/resumes/active` errors, the page shows "You need a resume first" instead of the real error. | Low |
| F5 | `MatchPage.jsx:145` | History rows are clickable `<li>`s with no keyboard support/role (a11y); clicking one drops the company/role guess (see 4.4). | Low |
| F6 | `MatchPage.jsx:39` | Clipboard promise has no `.catch` (denied permission → unhandled rejection, no feedback). | Low |
| F7 | `ui.jsx` Modal | No focus trap or focus restore; `useEffect` re-subscribes the Esc handler on every render because `onClose` is an inline lambda. | Low |
| F8 | `Dashboard.jsx` | "Change password" is a button on the dashboard only (not in the header/user menu), and unreachable if the dashboard request fails. The new modal also enforces 72 *characters* (see 2.1) and never tells the user other sessions stay signed in. | Low |
| F9 | `api.js:44` | Network error text hard-codes "backend running on port 8000". Any 401 elsewhere logs the user out, which is correct, but make sure new endpoints never use 401 for business errors. | Low |
| F10 | `ApplicationModal.jsx:68-85` | Save does two sequential requests (PATCH fields then PATCH stage). If the second fails, the first is already persisted and the user sees an error with half-saved data. Consider a single endpoint accepting `stage`. | Low |
| F11 | `ResumePage.jsx` | Deleting a resume also deletes its matches (cascade) and detaches saved applications; the confirm text mentions matches but not that applications lose their "AI matched" link. | Low |
| F12 | `index`/build | `npm run build` passes; no linter, formatter, or tests exist, so none of the above is caught automatically. | Medium |

---

## 7. Tests

21 tests pass and cover auth basics, one-active resume, match/save, stage rules, dashboard maths, cross-user access for applications, and the new change-password flow. Gaps worth closing (several would have caught bugs above):
- Non-ASCII password (2.1), null/blank PATCH (2.2/2.3), URL scheme (2.4).
- Cross-user access for **resumes, matches, and interviews** (only applications are tested).
- Resume activate/delete flows and the promote-next-active rule; PDF upload happy path, encrypted PDF, oversize, and text >50 k.
- `ClaudeAIClient` error mapping (mock `anthropic` exceptions → `AIError` messages, refusal, `parsed_output is None`).
- Timezone and week-boundary cases (Sunday 23:59 / Monday 00:00, tz-aware input).
- Duplicate-save race; signup race (`IntegrityError`).
- Frontend: add at least Vitest + React Testing Library smoke tests, and ESLint.
- `test_dashboard_metrics` uses `now + 30 min`; near midnight on Sunday it could cross the week boundary assumptions only if assertions on week were added: keep time injected via the `now` parameter that `get_dashboard` already accepts.

---

## 8. Recommended order of work

1. **Today (small, high value):** fix repo hygiene (1.1), JWT-secret guard (1.2), bcrypt byte-length validation (2.1), null-PATCH validation (2.2), strip/URL validation (2.3, 2.4).
2. **This week:** make upload handler non-blocking (2.6), release DB before AI call + tighten timeout (4.1, 4.2), per-user match rate limit (3.2), partial unique index and FK indexes (5.1, 5.2, 4.4), pin dependencies (1.3), isolate test DB (5.5).
3. **Before real users:** timezone strategy (5.4), token versioning + Alembic (3.1, 5.3), login throttling and timing fix (2.7), frontend fixes F1/F2, add the tests in §7 and a CI job running `pytest` + `npm run build`.
4. **Backlog:** pagination, interview editing, account deletion/password reset, accessibility items F5/F7, dashboard semantics review (2.8).

_Files I did not execute against live services: the real Claude call path (no API key in the environment), browser behaviour of the React UI (analysed by reading; `npm run build` only), and concurrency issues (🔎 items are reasoned from the code, not load-tested)._
