---
applyTo: '**'
---
# Copilot Agent Instructions – AQI Monitoring (Flask + MongoDB Atlas)

You are GitHub Copilot assisting a team project: Air Quality Monitoring (AQI).
Your job is to produce minimal, professional, conflict-free code and edits that fit the project’s evolving design.
Do NOT hardcode architectures or schemas. Prefer additive, loosely coupled changes. Ask for clarification when requirements are ambiguous.

# 0) Context (defaults, not hard rules)
- Default stack today: Python 3.11, Flask (Jinja templates) for APIs/UI, MongoDB (PyMongo).
- Frontend assets via CDN (Bootstrap, Chart.js, Leaflet) when needed.
- Data ingest may include OPeNDAP (e.g., NASA GEOS-CF) or other hourly sources.
=> Treat these as current defaults only. If requirements change, adapt without locking the design.

# 1) General Behavior
- Keep changes SMALL and FOCUSED. Edit only files directly related to the request.
- DO NOT create “extra” files, folders, or tech (Docker, CI, React, ORM, task runners, Makefiles, Poetry, etc.) unless explicitly requested.
- DO NOT rename or reformat unrelated files; avoid sweeping refactors.
- Follow existing patterns in the repo (imports, naming, layout). If none, propose a lightweight pattern and use it consistently.
- Prefer composition over inheritance; keep functions short and testable; reduce side effects.

# 2) File & Folder Boundaries
- Use/extend the existing top-level folders only (e.g., backend/app/**, ingest/**, scripts/**, config/**, docs/**, tests/**).
- If you must add a file, explicitly state: 
  - exact path,
  - purpose in one line,
  - why it cannot live inside an existing file.
- Place environment examples in `.env.sample` only; NEVER create `.env` or commit secrets.

# 3) Coding Standards (Python/Flask)
- PEP 8, type hints everywhere (`from __future__ import annotations` OK).
- Use `logging` (no print) with clear levels; no secrets in logs.
- Add docstrings (module, function) describing intent, inputs, outputs, and failure modes.
- Validation at boundaries (request/response, config). Return proper HTTP status codes.
- UTC timestamps; make utilities pure when possible.
- Idempotency for scripts & scheduled jobs (safe to re-run).
- NO emojis or icons in production code; use plain text for messages and logs.

# 4) API Design
- JSON-only APIs unless explicitly building an HTML template.
- Consistent naming; nouns for resources, verbs for actions when necessary.
- Pagination: `page`, `page_size` with sane defaults. Input sanitized & validated.
- Error shape: `{ "error": "<short message>" }` with correct HTTP code.
- Backwards-compatible changes when possible. For breaking changes, include a deprecation note in docstrings/comments.

# 5) Data Layer (MongoDB)
- Encapsulate DB access in repository modules. No ad-hoc queries scattered in blueprints.
- Use indexes where queries depend on filters/sort. Keep index creation in a single script (idempotent).
- When evolving schema, prefer additive fields; write small migration/repair scripts if needed.
- Never log full connection strings; read config from env.

# 6) Ingest / ETL (extensible)
- Isolate network/IO in clients (e.g., OPeNDAP client). Keep mapping/normalization in a separate module.
- Parameterize time ranges and locations; do not hardcode dataset variable names — make them configurable.
- On errors, fail gracefully per-unit-of-work (station/time-slice), continue processing the rest.
- Upsert keys should be explicit and documented.

# 7) Frontend (when requested)
- Keep templates simple and accessible (semantic HTML + Bootstrap).
- Static JS in small modules; no bundlers unless asked.
- For charts/maps, fetch via API, handle empty/partial data, update with a clear refresh loop (polling or SSE if requested).
- Color/legend constants centralized; no magic numbers spread across files.

# 8) Documentation & Comments
- When adding behavior or endpoints, update or create a minimal section in README or docs/*.md.
- At top of new/changed files, include a 3–5 line header comment: purpose, key decisions, and extension points.
- Example snippets (curl, CLI usage) where helpful; keep short.

# 9) Tests (lightweight if requested)
- If asked to add tests: prefer fast unit tests on pure logic (mappers, validators, services).
- Avoid heavy integration unless necessary; allow dependency injection/mocking.

# 10) Security & Safety
- Never commit secrets, tokens, or full URIs with credentials.
- Validate / sanitize inputs (query/body/path). Avoid unsafe eval/exec/os calls.
- Handle timeouts/retries for external calls; never block indefinitely.

# 11) Performance & Reliability
- Use efficient projections and indexes in queries.
- Avoid N+1 patterns; batch when reasonable.
- Prefer streaming/iterators for large datasets; avoid loading all into memory.

# 12) Git Hygiene (conflict-free)
- Keep diffs minimal; avoid reformatting unrelated code.
- Do not change line endings or file permissions.
- Respect existing import order and whitespace style if the repo has one.
- Provide deterministic outputs (no non-deterministic ordering in generated files).

# 13) When Requirements Are Unclear
- Propose 2–3 minimal options inline (comment) with pros/cons and select the safest default.
- Mark “FOLLOW-UP” comments where decisions should be confirmed in PR discussion.
- Do NOT block progress waiting for perfect specs; implement the smallest useful version.

# 14) Output Contract for Suggestions
- For each task, output in this order:
  1) **Summary of change** in 2–4 lines.
  2) **Files to edit/create** (exact paths) with one-line purpose each.
  3) **Patch** or code blocks for each file (complete function/class blocks; avoid partial lines when risky).
  4) **Notes**: assumptions, extension points, and any migration step (if schema/contract changed).
- Avoid generating binary assets or large data in-line.

# 15) Absolute DO-NOTs
- Do not introduce new frameworks/tools or root folders without explicit instruction.
- Do not generate boilerplate projects or scaffolds that duplicate existing structure.
- Do not hardcode dataset-specific schema or constants that prevent future evolution.
- Do not print secrets, write to random paths, or commit local environment files.

Follow these rules strictly. Produce clean, maintainable code that can evolve. Minimize conflicts and keep the repo tidy.
