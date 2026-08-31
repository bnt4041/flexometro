# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Flexómetro — a Spanish-language construction ERP (flexometro.online). FastAPI
backend + React/Vite frontend, multi-tenant, deployed via Docker Compose
behind Traefik. All code, comments, docstrings, commit messages, and UI text
are in Spanish. Follow that convention — do not switch to English mid-file.

The full narrative documentation (why each module exists, the exact
architectural reasoning behind non-obvious choices) lives in
[README.md](README.md). This file is the fast-start command/architecture
reference; read README.md when you need the reasoning behind a decision.

## Commands

All commands run through Docker Compose; there is no local venv/node_modules
convention — every service (`api`, `web`, `migrate`, `db`) runs in its own
container.

```bash
# Bring the stack up (first run / after a rebuild)
docker compose up -d

# Backend tests (pure-Python where possible, no DB fixtures/conftest.py —
# most test files import service/model code directly and assert on it)
docker compose exec -T api pytest -q
docker compose exec -T api pytest -q tests/test_planos_geometria.py   # single file
docker compose exec -T api pytest -q tests/test_planos_geometria.py::test_area_del_rectangulo  # single test

# Backend lint (ruff; config in backend/pyproject.toml — select = E,F,I,UP,B)
docker compose exec -T api ruff check app/
docker compose exec -T api ruff check --fix app/            # only for safe, mechanical fixes

# Frontend typecheck (no separate `tsc` script — `build` runs `tsc -b && vite build`)
docker compose exec -T web npx tsc --noEmit -p tsconfig.json

# Frontend build
docker compose exec -T web npm run build

# Apply pending Alembic migrations (all module branches merge to `heads`)
docker compose run --rm migrate

# Rebuild an image after changing requirements.txt / package.json
docker compose build api        # or: web

# Restart after a backend code change (bind-mounted, but the process needs a kick)
docker compose restart api
docker compose logs api --tail 30
```

There is no `docker compose exec -T db psql` shortcut defined — connect
directly: `docker exec -i obras-db-1 psql -U obras -d obras`.

## Architecture

### Multi-tenant isolation is the load-bearing invariant

Every business table (except `plexo.*`, see below) carries `organization_id`
and has **PostgreSQL Row-Level Security forced** (`FORCE ROW LEVEL SECURITY`,
not just `ENABLE`) via `activar_rls()` in `backend/app/core/rls.py`. The API
connects as a low-privilege role (`obras_app`), never as the migrations
admin — a superuser bypasses RLS unconditionally, so using a superuser
connection for API traffic would silently defeat all of this.

The organization for the current request lives in a `ContextVar`
(`app/core/tenancy.py`: `current_organization_id`/`set_organization_id`), set
by `TenancyMiddleware`. `TenancyMiddleware` is **hand-written ASGI**, not
`BaseHTTPMiddleware` — the latter runs the rest of the app in a separate
task, and a ContextVar set before `call_next` does not reliably reach the
endpoint. `get_session()` reads the ContextVar and issues
`SELECT set_config('app.organization_id', :id, true)` (session/transaction
scoped) at the start of each DB session — that `set_config` call is what RLS
policies actually check, not the ContextVar directly.

**To deliberately act as a different organization within one request**
(rare — a handful of legitimate cross-org cases exist), use
`fijar_organizacion_activa(session, org_id)` from `app/core/database.py`,
which re-issues that same `set_config`. Do **not** use
`tenancy.set_organization_id()` for this — it only moves the Python
ContextVar, not the Postgres session variable RLS reads, and downstream code
in the same request (numbering, `datos_autoria()`) would keep believing it's
in the original organization. See
`app/modules/compras/solicitud_service.py::avisar_si_tiene_cuenta` for
the canonical example: notifying a *different* organization's inbox from
inside a request running as your own, wrapped in `try/finally` to switch
back immediately after the one write that needs it.

Same-account sibling organizations can share **read-only** master data
(terceros, price bank) if `compartir_maestros` is on — that's
`activar_rls_maestro()`/`organizaciones_visibles()`, a *different, narrower*
mechanism than the cross-org case above: it only ever widens `SELECT`, never
`INSERT`/`UPDATE`/`DELETE`.

The `plexo` module is the first place two entirely unrelated organizations
(different accounts) reference each other in one row on purpose —
`plexo.vinculo` has no single `organization_id`, only
`organizacion_origen_id`/`organizacion_destino_id`, with a bespoke policy
(`SELECT`/`UPDATE` if either side matches, `INSERT` only as origin; the
state machine itself — who may accept/reject/revoke — lives in
`service.py`, not in the policy). `plexo.perfil` has a different, narrower
widening: `SELECT` is visible cross-org only where `visible = true`, same
shape as `activar_rls_maestro()` but keyed on a flag instead of "same
account". As of Fase 69 this only establishes the connection itself
(invite/accept/reject/revoke) — no business documents cross the boundary
yet.

### Module system

Each business module lives in `backend/app/modules/<code>/` and declares a
`ModuleSpec` (code, router, `depends_on`, nav entries) in its `__init__.py`.
Modules are **activated per organization** (`core.organization_module`); a
disabled module's router is still mounted but gated behind
`require_module(...)`, returning 404 rather than existing half-configured.
Activating a module pulls in its dependency closure automatically
(`registry.resolve_activation`).

**Registering a new module requires touching four places** — miss one and
the module silently doesn't load or its migration is never discovered:

1. `backend/app/modules/<code>/__init__.py` — the `ModuleSpec`.
2. `backend/app/modules/__init__.py` — import the spec, add it to
   `ALL_SPECS`, and add its `models` import inside `import_models()` (needed
   so SQLAlchemy's metadata knows the tables even though nothing else
   imports that module at startup).
3. `backend/alembic.ini` — append the module's migration directory to
   `version_locations` (space-separated), or `alembic upgrade heads` never
   finds its migrations.
4. Activate the module per organization in the DB (new orgs get whatever a
   seed/default grants; existing orgs need an explicit
   `INSERT INTO core.organization_module ...` — there's no UI-less
   auto-activation for existing tenants).

Each module owns its own PostgreSQL **schema** (not just a table prefix) and
its own Alembic **branch** (`branch_labels=("modulecode",)`,
`down_revision=None` for the first migration in that branch, merged at
`heads`). A new schema needs `conceder_privilegios_app(schema)` in its first
migration or the API role gets `permission denied for schema`.

### Permissions

Four actions per module — `ver`, `editar`, `crear`, `borrar`
(`app/core/permisos.py::ACCIONES`) — each with a scope, `Alcance.NINGUNO /
PROPIOS / TODOS`. `require_permiso(module_code, accion)` is a router
dependency returning the resolved scope so the endpoint knows whether to
filter by `creado_por_subject`. `verificar_propiedad()` is what turns
"PROPIOS but not yours" into a 404 (not 403) — not revealing that a record
exists is deliberate, matching how RLS fails on another organization's data.
API keys (`clave:` prefix on `subject`) get their permissions from scopes
recorded at key creation, not from group membership.

### Backend request flow

`Principal` (from Keycloak JWT, or an API key) → `TenancyMiddleware` sets the
org/user ContextVars → router dependency chain
(`require_module` → `require_permiso` → handler) → `AsyncSession` from
`get_session()` already has `app.organization_id` set for RLS. Handlers call
into a module's `service.py`, never touch models directly from the router
except trivial lookups. Cross-module calls use deferred imports inside the
function body (not top-of-file) specifically to avoid import cycles between
modules that need each other bidirectionally (e.g. `core` ⇄
`notificaciones`).

`Base.__mapper_args__ = {"eager_defaults": True}` — required because
`updated_at` is server-computed (`onupdate=func.now()`); without
`eager_defaults`, reading it back after an `UPDATE` triggers a lazy load
outside the greenlet context and raises `MissingGreenlet`.

### Frontend

Single-file API client: `frontend/src/lib/api.ts` — every module's calls and
TypeScript types live in one large file (not split per module), organized in
the same order as the backend module list. `App.tsx` has two lookup tables:
`PANTALLAS` (route path → list screen) and `MODALES` (parent path → child
routes for create/detail, rendered inside `ModalPantalla`). A module's nav
entries come from the backend (`ModuleSpec.nav`), not hardcoded in the
frontend — `workspace.tsx` fetches `api.modules()` on load and `AppShell.tsx`
builds the sidebar from whatever that returns for the active org.

Styling is one global stylesheet (`styles/global.css`) plus CSS custom
properties in `styles/tokens.css` — no CSS-in-JS, no per-component
stylesheets. Reuse existing class names (`.page-head`, `.form-section`,
`.btn--sm`, `.table-wrap`, etc.) rather than inventing new ones; check
`global.css` before adding a class.

### Things that bit us before (don't reintroduce)

- **PDF/binary fetches to authenticated endpoints must go through the app's
  `fetch` wrapper** (`traerBlob()` in `api.ts`), never a bare `<img src=...>`
  or handing pdf.js a raw URL — neither sends the `Authorization` header, and
  the request 401s.
- **A card border/CSS artifact isn't the only source of measurement error**
  when eyeballing a freehand-drawn shape against a known geometric answer —
  don't assume a small percentage discrepancy is a calibration bug before
  checking whether the test geometry itself was drawn to scale.
- **DXF blocks explode into the layer of the entity that's inside them
  unless that entity is on layer `"0"`**, in which case it inherits the
  `INSERT`'s layer — this is a DXF *rule*, not a bug, and skipping it makes
  every door/window/fixture landed via a block ignorable-but-not-actually
  hideable by its intended layer.
- **`ilike`/normal string comparison is not how you validate an AI-read
  scale denominator** — constrain it to the actual finite set of drafting
  scales in use (1, 2, 5, 10, 20, 25, 50, 100, …); an unconstrained integer
  from a vision model calibrates the whole sheet off a misread digit.
