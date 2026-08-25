# Admin Machine-Time Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved read-only admin dashboard for the previous 24 hours of machine execution and exact-dimension historical productivity comparisons.

**Architecture:** A focused `app.production_dashboard` module will bulk-read existing SQLite records and build a deterministic server-rendered view model. `app.main` will expose one GET route, while one Jinja template plus scoped existing-app CSS and small tooltip JavaScript will reproduce the approved prototype without introducing an API, background process, or schema change.

**Tech Stack:** Python 3.12, FastAPI, direct `sqlite3`, Jinja2, existing CSS, browser JavaScript, pytest, repo-local Playwright.

**Spec:** `docs/superpowers/specs/2026-08-24-admin-machine-time-dashboard-design.md`

## Global Constraints

- The page is read-only and must not mutate the configured SQLite database.
- Tests use temporary SQLite paths, never `data/extrusion_terminal.sqlite3` or a production backup.
- Stored timestamps are UTC and visible timestamps are `Europe/Sofia` civil time.
- No database migration, dependency, API endpoint, polling, WebSocket, automatic verdict, or material matching.
- The production page follows `ui-prototypes/admin-machine-time-dashboard.html` and contains no educational or explanatory dashboard copy.
- Do not stage or commit without explicit user authorization.

---

### Task 1: Build The Twenty-Four-Hour Timeline View Model

**Files:**
- Create: `app/production_dashboard.py`
- Create: `tests/test_admin_machine_dashboard.py`

**Interfaces:**
- Produces: `build_machine_time_dashboard(reference_time: datetime | None = None) -> dict[str, Any]`
- Produces: a dashboard dictionary containing `window`, `axis`, and four `machines`; each machine contains `timeline`, `active_seconds`, `active_duration`, `active_percent`, and `orders`.
- Consumes: existing `app.db.connect()` and `app.timekeeping` UTC/Sofia rules.

- [ ] **Step 1: Write failing timeline tests**

Create temporary-database tests that insert cards and timing segments spanning
the boundary and assert:

```python
dashboard = build_machine_time_dashboard(
    datetime(2026, 8, 24, 10, 0, tzinfo=timezone.utc)
)
assert [machine["id"] for machine in dashboard["machines"]] == [1, 2, 3, 4]
assert dashboard["window"]["seconds"] == 24 * 60 * 60
assert [part["kind"] for part in dashboard["machines"][0]["timeline"]] == [
    "idle", "order", "pause", "order", "idle"
]
assert dashboard["machines"][0]["active_seconds"] == expected_active_seconds
```

Include open running and paused cards, clipping at both boundaries, a machine
with no records, nine three-hour axis labels, and Sofia display values.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_machine_dashboard.py -q
```

Expected: collection or import failure because `app.production_dashboard` and
`build_machine_time_dashboard` do not exist.

- [ ] **Step 3: Implement the minimal timeline builder**

Implement `app/production_dashboard.py` with:

```python
def build_machine_time_dashboard(
    reference_time: datetime | None = None,
) -> dict[str, Any]:
    end_utc = _canonical_reference_time(reference_time)
    start_utc = end_utc - timedelta(hours=24)
    with db.connect() as connection:
        machines = _fetch_machines(connection)
        cards = _fetch_dashboard_cards(connection, end_utc)
    return _build_dashboard_view(machines, cards, start_utc, end_utc)
```

Use parameterized bulk SELECTs, strict UTC parsing through existing timekeeping
helpers, clipped half-open intervals, pause intervals derived from
`end_reason='pause'`, and gray complement intervals. Merge only adjacent
intervals of the same kind and same order. Format visible times in Sofia.

- [ ] **Step 4: Run focused timeline tests and verify GREEN**

Run the focused file until all Task 1 tests pass.

- [ ] **Step 5: Review Task 1**

Inspect the diff for hidden writes, N+1 SQL, host-timezone dependence, interval
overlaps, and mutation of fetched records. Do not stage or commit.

### Task 2: Add Exact-Dimension Productivity Comparisons

**Files:**
- Modify: `app/production_dashboard.py`
- Modify: `tests/test_admin_machine_dashboard.py`

**Interfaces:**
- Produces: `normalize_dimensions(value: Any) -> tuple[Decimal, Decimal] | None`
- Extends each machine `orders` row with total `net_kg`, total
  `active_seconds`, `productivity`, and either `baseline=None` or a baseline
  containing `minimum`, `maximum`, `sample_count`, `samples`, and gauge
  positions.
- Consumes: Task 1 card, timing-segment, and roll aggregates.

- [ ] **Step 1: Write failing productivity tests**

Add tests proving:

```python
assert normalize_dimensions("400/0.050") == normalize_dimensions("400 / 0,05")
assert normalize_dimensions("not-a-size") is None
```

Construct recent and historical orders to prove same-machine and exact numeric
dimensions, earlier-completed-only matching, complete-order net kilograms and
active time, zero/one/multiple samples, reviewed-order exclusion, min/max,
latest-seven ordering, and a current marker outside the range.

- [ ] **Step 2: Run the new tests and verify RED**

Run the focused test names and confirm they fail because the baseline data is
absent, not because the fixtures are invalid.

- [ ] **Step 3: Implement minimal productivity aggregation**

Parse dimensions with `Decimal` after comma normalization. Sum saved
`roll_entries.net_weight`, sum complete timing segments up to finish/request
time, compute kilograms per hour only for positive values, and round display
values with explicit decimal half-up behavior. Use prior production-complete
(`completed` or `archived`) exact-match orders without filtering recorded
outliers. Return only the latest seven
sample rows while retaining the complete `sample_count`.

Compute one stable gauge scale from historical bounds and current value with
padding at both ends. With one sample, set minimum and maximum to the same
value and render it later as a point.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run all dashboard model tests and confirm they pass.

- [ ] **Step 5: Review Task 2**

Check exact matching, rounding, divide-by-zero behavior, no silent fuzzy
matching, no material input, and deterministic sample ordering.

### Task 3: Integrate The Admin Route And Approved UI

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/_admin_nav.html`
- Create: `app/templates/admin_dashboard.html`
- Modify: `app/static/css/app.css`
- Modify: `tests/test_admin_routes.py`
- Modify: `tests/test_admin_machine_dashboard.py`
- Modify: `README.md`
- Modify: `AGENTS.md`

**Interfaces:**
- Consumes: `build_machine_time_dashboard()` from Tasks 1 and 2.
- Produces: `GET /admin/dashboard` and `/admin -> /admin/dashboard`.
- Produces: template context `admin_section='dashboard'` and `dashboard=<view model>`.

- [ ] **Step 1: Write failing route and rendering tests**

Assert route registration, the new redirect, active navigation, four machine
rows/groups, title and column units, timeline kinds, blank no-baseline area,
one-sample and multi-sample gauge markup, tooltip data capped at seven, no
click dialog, and the absence of `Обновено`, `Нетна производителност`, and
educational status copy.

- [ ] **Step 2: Run route/render tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_routes.py tests/test_admin_machine_dashboard.py -q
```

Expected: `/admin/dashboard` is missing and `/admin` still redirects to
`/admin/import`.

- [ ] **Step 3: Implement the GET route and navigation**

Add:

```python
@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "admin_section": "dashboard",
            "dashboard": build_machine_time_dashboard(),
        },
    )
```

Redirect `/admin` to the dashboard, add `Табло` as the first navigation link,
and make the admin logo link to it.

- [ ] **Step 4: Implement the accepted server-rendered design**

Translate the approved prototype to Jinja loops over the view model. Retain
semantic headings, tables, `<time>` values, focusable hover targets, ARIA
labels, customer ellipsis, duration-only pause/idle labels, and the accepted
gauge structure. Add scoped `.machine-dashboard-*` styles to `app.css` and
small template JavaScript for tooltip placement, pointer/focus lifecycle, and
`window.location.reload()` on Refresh. Do not add a dialog or click handler to
orders.

- [ ] **Step 5: Update confirmed scope documentation**

Move the bounded read-only admin machine execution/productivity dashboard into
confirmed scope in `README.md` and `AGENTS.md`. Keep automated performance
judgments and general-purpose downtime/MES expansion out of scope.

- [ ] **Step 6: Run focused route/render tests and verify GREEN**

Run both focused test files until all tests pass.

- [ ] **Step 7: Review Task 3**

Check prototype fidelity, template escaping, no unsafe HTML construction,
keyboard behavior, read-only GET behavior, and no unrelated refactor.

### Task 4: Browser Verification And Final Hardening

**Files:**
- Create ignored evidence below: `artifacts/ui-checks/admin-machine-time-dashboard/`
- Modify production/test files only when verification exposes a covered defect.

**Interfaces:**
- Consumes: the completed local route and a temporary test database.
- Produces: focused screenshots and an exact recorded browser verification command.

- [ ] **Step 1: Run focused automated tests**

```bash
.venv/bin/python -m pytest tests/test_admin_machine_dashboard.py tests/test_admin_routes.py -q
```

- [ ] **Step 2: Start the local app with a temporary SQLite database**

Use environment-scoped paths and the repo-local virtualenv. Never point the
server at the runtime or production database.

- [ ] **Step 3: Run a task-specific Playwright check**

At 1440x1024 and 1024x1024, assert the accepted title, four machines, timeline
axis, order/pause/idle tooltips, gauge tooltip total count and maximum seven
rows, customer ellipsis, functional Refresh reload, no dialog, no console/page
errors, and `document.documentElement.scrollWidth === document.documentElement.clientWidth`.

- [ ] **Step 4: Save evidence**

Save full-page, timeline, productivity, order-hover, pause-hover, idle-hover,
productivity-hover, and responsive screenshots under the specified artifact
directory.

- [ ] **Step 5: Run full verification**

```bash
.venv/bin/python -m pytest
git diff --check
```

Review `git status --short` and the feature diff. Confirm no local database,
artifact, node module, or unrelated user file was staged or added.

- [ ] **Step 6: Independent final review**

Provide the specification, plan, and feature diff to one independent reviewer.
Resolve all Critical and Important findings, rerun covering tests, and perform
one final scoped verification before reporting the change review-ready.
