# Admin Dashboard Day Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the shift manager retain the rolling latest-24-hours dashboard by default and select any completed Sofia calendar day for the same machine-time and productivity review.

**Architecture:** Extend the existing dashboard view-model builder with an optional `date` and derive one explicit UTC window from either the request time or Sofia local midnights. The existing read-only GET route will accept a strict ISO `day` query parameter, while the current Jinja page adds a native date input and a canonical reset link; no database, schema, or productivity-matching changes are required.

**Tech Stack:** Python 3.12, FastAPI, direct `sqlite3`, Jinja2, existing CSS and browser JavaScript, pytest, repo-local Playwright.

**Spec:** `docs/superpowers/specs/2026-08-24-admin-machine-time-dashboard-design.md` (this bounded plan extends its “Time Window And Presentation” section with the user-approved calendar-day behavior restated below).

## Global Constraints

- `GET /admin/dashboard` with no query continues to show the rolling 24 hours ending at request time.
- `GET /admin/dashboard?day=YYYY-MM-DD` shows that complete `Europe/Sofia` calendar date, from local midnight to the following local midnight.
- Only completed Sofia dates through yesterday are selectable; today, future dates, and malformed values redirect to canonical `/admin/dashboard`.
- A selected daylight-saving transition date uses its real elapsed duration: 23, 24, or 25 hours. Timeline widths, clipping, idle complement, and active percentage all use that same duration.
- The selected window controls both the machine timeline and which orders appear in the productivity table. Existing exact-dimension historical comparison rules do not change.
- Productivity for an order remains based on its complete currently recorded order totals. Do not combine all-time roll kilograms with timing truncated at the selected historical day.
- The page remains read-only and must not mutate the configured SQLite database.
- Do not add a schema migration, API, dependency, background job, polling, or general reporting framework.
- Tests and browser checks use temporary SQLite paths, never `data/extrusion_terminal.sqlite3` or any database under `production-db/`.
- Preserve unrelated working-tree changes. Do not stage or commit without explicit user authorization.

---

## File Map

- `app/production_dashboard.py` — resolve rolling/calendar windows, apply dynamic duration to the existing timeline model, and expose strict day parsing.
- `app/main.py` — validate the optional `day` query and pass one consistent request time into parsing and view-model construction.
- `app/templates/admin_dashboard.html` — render the date form, selected/default caption, reset action, and auto-submit behavior.
- `app/static/css/app.css` — style only the compact dashboard controls and their responsive/focus states.
- `tests/test_admin_machine_dashboard.py` — cover window bounds, daylight saving, clipping, productivity cutoff separation, route validation, and rendered controls.
- `artifacts/ui-checks/admin-dashboard-day-selection/` — ignored temporary database, verification script, screenshots, and browser-check output.

---

### Task 1: Add A Calendar-Day-Aware Dashboard Window

**Files:**
- Modify: `app/production_dashboard.py:4-16,35-148,548-565`
- Modify: `tests/test_admin_machine_dashboard.py:1-16,130-305`

**Interfaces:**
- Produces: `parse_dashboard_day(value: str | None, reference_time: datetime) -> date | None`
- Extends: `build_machine_time_dashboard(reference_time: datetime | None = None, selected_day: date | None = None) -> dict[str, Any]`
- Produces window keys: `mode`, `selected_day`, `max_selectable_day`, `start_utc`, `end_utc`, `seconds`, and `range_display`.
- Preserves all existing `axis` and `machines` interfaces consumed by `admin_dashboard.html`.

- [ ] **Step 1: Write failing tests for strict input and ordinary-day bounds**

Add `date` to the datetime imports and import `parse_dashboard_day`. Keep the existing `REFERENCE_TIME` unchanged for the established rolling-window tests and add a separate reference whose Sofia date is 25 August 2026:

```python
DAY_SELECTION_REFERENCE_TIME = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)


def test_dashboard_day_parser_accepts_only_completed_iso_dates():
    assert parse_dashboard_day(None, DAY_SELECTION_REFERENCE_TIME) is None
    assert parse_dashboard_day("", DAY_SELECTION_REFERENCE_TIME) is None
    assert parse_dashboard_day("2026-08-24", DAY_SELECTION_REFERENCE_TIME) == date(2026, 8, 24)

    for value in ("24-08-2026", "20260824", "not-a-date", "2026-08-25", "2026-08-26"):
        with pytest.raises(ValueError):
            parse_dashboard_day(value, DAY_SELECTION_REFERENCE_TIME)


def test_selected_sofia_day_has_local_midnight_bounds(connection):
    dashboard = build_machine_time_dashboard(
        DAY_SELECTION_REFERENCE_TIME,
        selected_day=date(2026, 8, 24),
    )

    assert dashboard["window"] == {
        "mode": "calendar_day",
        "selected_day": "2026-08-24",
        "max_selectable_day": "2026-08-24",
        "start_utc": "2026-08-23T21:00:00Z",
        "end_utc": "2026-08-24T21:00:00Z",
        "seconds": 86_400,
        "range_display": "24 авг. 00:00 – 25 авг. 00:00",
    }
    assert dashboard["axis"][0]["display"] == "00:00"
    assert dashboard["axis"][-1]["display"] == "00:00"
    assert dashboard["axis"][0]["position"] == 0
    assert dashboard["axis"][-1]["position"] == 100
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_machine_dashboard.py::test_dashboard_day_parser_accepts_only_completed_iso_dates \
  tests/test_admin_machine_dashboard.py::test_selected_sofia_day_has_local_midnight_bounds -q
```

Expected: collection/signature failures because `parse_dashboard_day` and `selected_day` do not exist.

- [ ] **Step 3: Implement strict parsing and explicit window resolution**

Import `date` and `time`. Keep parsing and window calculations deterministic from the same supplied reference time:

```python
def parse_dashboard_day(
    value: str | None,
    reference_time: datetime,
) -> date | None:
    if value is None or value == "":
        return None
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid dashboard day.")
    try:
        selected_day = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid dashboard day.") from exc
    reference_utc = _canonical_reference_time(reference_time)
    max_day = reference_utc.astimezone(SOFIA_ZONE).date() - timedelta(days=1)
    if selected_day > max_day:
        raise ValueError("Dashboard day must be complete.")
    return selected_day
```

Add one focused internal resolver. It must calculate historical boundaries by constructing each local midnight independently, then converting both to UTC:

```python
def _resolve_dashboard_window(
    reference_time: datetime | None,
    selected_day: date | None,
) -> tuple[datetime, datetime, datetime, date]:
    reference_utc = _canonical_reference_time(reference_time)
    max_day = reference_utc.astimezone(SOFIA_ZONE).date() - timedelta(days=1)
    if selected_day is None:
        return reference_utc, reference_utc - WINDOW_DURATION, reference_utc, max_day
    if selected_day > max_day:
        raise ValueError("Dashboard day must be complete.")
    start_local = datetime.combine(selected_day, time.min, tzinfo=SOFIA_ZONE)
    end_local = datetime.combine(
        selected_day + timedelta(days=1),
        time.min,
        tzinfo=SOFIA_ZONE,
    )
    return (
        reference_utc,
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
        max_day,
    )
```

In `build_machine_time_dashboard`, derive `window_seconds = int((end_utc - start_utc).total_seconds())`. Use it for `window.seconds` and `active_percent` instead of `WINDOW_SECONDS`. Add the mode, selected value, and maximum date to `window` exactly as follows:

```python
"mode": "calendar_day" if selected_day is not None else "rolling",
"selected_day": selected_day.isoformat() if selected_day is not None else "",
"max_selectable_day": max_day.isoformat(),
```

Keep two cutoffs distinct:

```python
reference_utc, start_utc, end_utc, max_day = _resolve_dashboard_window(
    reference_time,
    selected_day,
)
_attach_card_metrics(cards, roll_rows, reference_utc)

for card in cards:
    events = _card_events(card, end_utc)
```

The timeline uses `end_utc`; complete-order productivity uses `reference_utc`.

- [ ] **Step 4: Implement a proportional axis for the resolved window**

Change `_build_axis` to receive both boundaries and the optional selected day. Rolling mode retains nine absolute three-hour ticks. Calendar mode creates local civil ticks for 00:00, 03:00, …, 24:00 and converts each to UTC. In both modes compute each position from elapsed UTC seconds rather than `index * 12.5`:

```python
position = (
    (tick_utc - start_utc).total_seconds()
    / (end_utc - start_utc).total_seconds()
    * 100
)
```

This keeps segment widths and grid positions on the same scale on 23- and 25-hour dates. Force the first and last stored positions to exact `0` and `100` to avoid floating-point edge drift.

- [ ] **Step 5: Add DST and productivity-cutoff regression tests**

Add parameterized assertions for Sofia’s 2026 transitions:

```python
@pytest.mark.parametrize(
    ("selected_day", "expected_start", "expected_end", "expected_seconds"),
    [
        (date(2026, 3, 29), "2026-03-28T22:00:00Z", "2026-03-29T21:00:00Z", 23 * 3600),
        (date(2026, 10, 25), "2026-10-24T21:00:00Z", "2026-10-25T22:00:00Z", 25 * 3600),
    ],
)
def test_selected_day_uses_real_dst_duration(
    connection,
    selected_day,
    expected_start,
    expected_end,
    expected_seconds,
):
    reference = datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc)
    dashboard = build_machine_time_dashboard(reference, selected_day=selected_day)
    assert dashboard["window"]["start_utc"] == expected_start
    assert dashboard["window"]["end_utc"] == expected_end
    assert dashboard["window"]["seconds"] == expected_seconds
    assert dashboard["axis"][0]["position"] == 0
    assert dashboard["axis"][-1]["position"] == 100
```

Create one completed order that overlaps 24 August but finishes on 25 August. Give it two hours of total active time and 200 kg. Assert its selected-day timeline is clipped at the 24 August boundary while its productivity row remains `100 kg/h`, proving that later complete timing and total rolls use the same cutoff rather than mixing 200 kg with one truncated hour.

- [ ] **Step 6: Run all dashboard model tests and review Task 1**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_machine_dashboard.py -q
```

Review the diff for host-timezone dependence, fixed 86,400-second assumptions, off-by-one midnight errors, future-date acceptance, and any change to exact-dimension baseline selection. Do not stage or commit.

---

### Task 2: Add The Read-Only Date Control And Canonical Query Handling

**Files:**
- Modify: `app/main.py:3-15,94,909-918`
- Modify: `app/templates/admin_dashboard.html:9-18,182-279`
- Modify: `app/static/css/app.css:1864-1916,2476-2600`
- Modify: `tests/test_admin_machine_dashboard.py:90-112,579-659`

**Interfaces:**
- Consumes: `parse_dashboard_day(day, reference_time)` and `build_machine_time_dashboard(reference_time, selected_day=...)` from Task 1.
- Produces: `GET /admin/dashboard?day=YYYY-MM-DD` for valid completed dates.
- Produces: a 303 redirect to `/admin/dashboard` for malformed, today, or future values.
- Produces selectors: `[data-dashboard-day-form]`, `#dashboard-day`, and `[data-dashboard-window-reset]` for browser verification.

- [ ] **Step 1: Write failing route and rendering tests**

Freeze the route’s request time with a `datetime` subclass and `monkeypatch` so the maximum date is deterministic:

```python
class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = DAY_SELECTION_REFERENCE_TIME
        return value if tz is None else value.astimezone(tz)


def test_admin_dashboard_renders_selected_day_control(connection, monkeypatch):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")

    response = asyncio.run(
        endpoint(make_request("/admin/dashboard?day=2026-08-24"), day="2026-08-24")
    )
    html = response.body.decode("utf-8")

    assert response.status_code == 200
    assert 'action="/admin/dashboard"' in html
    assert 'method="get"' in html
    assert 'type="date"' in html
    assert 'name="day"' in html
    assert 'value="2026-08-24"' in html
    assert 'max="2026-08-24"' in html
    assert "Избран ден" in html
    assert 'data-dashboard-window-reset' in html


@pytest.mark.parametrize("day", ["bad", "2026-08-25", "2026-08-26"])
def test_admin_dashboard_rejects_invalid_or_incomplete_day(connection, monkeypatch, day):
    monkeypatch.setattr("app.main.datetime", FixedDateTime)
    endpoint = next(route.endpoint for route in app.routes if route.path == "/admin/dashboard")
    response = asyncio.run(endpoint(make_request("/admin/dashboard"), day=day))
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"
```

Extend the existing default-render test to assert an empty date value, `Последни 24 часа`, no reset link, and unchanged refresh button.

- [ ] **Step 2: Run route/render tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_admin_machine_dashboard.py::test_admin_dashboard_renders_selected_day_control \
  tests/test_admin_machine_dashboard.py::test_admin_dashboard_rejects_invalid_or_incomplete_day -q
```

Expected: endpoint argument or markup assertion failures.

- [ ] **Step 3: Implement canonical GET handling**

Import `timezone` in `app.main` and import `parse_dashboard_day` beside the builder. Use one captured request time so validation, `max`, the default rolling end, and open-segment metrics cannot disagree at a clock boundary:

```python
@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, day: str | None = None):
    reference_time = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        selected_day = parse_dashboard_day(day, reference_time)
    except ValueError:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "admin_section": "dashboard",
            "dashboard": build_machine_time_dashboard(
                reference_time,
                selected_day=selected_day,
            ),
        },
    )
```

Do not show an error banner for a manually altered URL; the canonical redirect intentionally restores the clean default page.

- [ ] **Step 4: Render the compact date form**

Replace the right-hand refresh-only wrapper with a compact controls group. Keep a real GET form and an accessible label:

```html
<div class="dashboard-controls">
  <form class="dashboard-day-form" action="/admin/dashboard" method="get" data-dashboard-day-form>
    <label class="visually-hidden" for="dashboard-day">Избери завършен ден</label>
    <input
      class="dashboard-day-input"
      id="dashboard-day"
      name="day"
      type="date"
      value="{{ dashboard.window.selected_day }}"
      max="{{ dashboard.window.max_selectable_day }}"
    >
  </form>
  {% if dashboard.window.mode == "calendar_day" %}
    <a class="dashboard-window-reset" href="/admin/dashboard" data-dashboard-window-reset>Последни 24 часа</a>
  {% endif %}
  <button class="refresh-button" type="button">Обнови</button>
</div>
```

The subtitle is conditional and contains no explanatory copy:

```html
<p>{% if dashboard.window.mode == "calendar_day" %}Избран ден{% else %}Последни 24 часа{% endif %} · {{ dashboard.window.range_display }}</p>
```

Add one JavaScript listener without changing tooltip behavior:

```javascript
const dayForm = document.querySelector("[data-dashboard-day-form]");
const dayInput = document.getElementById("dashboard-day");
dayInput.addEventListener("change", () => dayForm.requestSubmit());
```

Submitting an empty cleared value is valid and resolves back to rolling mode. The existing refresh listener continues to use `window.location.reload()`, which preserves the active `day` query.

- [ ] **Step 5: Add scoped responsive and focus styling**

Add `.dashboard-controls`, `.dashboard-day-form`, `.dashboard-day-input`, and `.dashboard-window-reset` beside the existing dashboard header styles. Match the current 40px refresh control height, use existing border/accent variables, and include both input and reset link in `:focus-visible`. At `max-width: 820px`, allow the controls to wrap without introducing document-level horizontal overflow. Do not change timeline segment sizing or productivity-table layout.

- [ ] **Step 6: Run focused tests and review Task 2**

Run:

```bash
.venv/bin/python -m pytest tests/test_admin_machine_dashboard.py tests/test_admin_routes.py -q
```

Review template escaping, keyboard form submission, invalid-query canonicalization, absence of database writes, query preservation on refresh, and no new dashboard prose. Do not stage or commit.

---

### Task 3: Verify The Complete Feature In A Live Browser

**Files:**
- Create ignored: `artifacts/ui-checks/admin-dashboard-day-selection/seed.py`
- Create ignored: `artifacts/ui-checks/admin-dashboard-day-selection/verify.mjs`
- Create ignored: `artifacts/ui-checks/admin-dashboard-day-selection/default-24-hours.png`
- Create ignored: `artifacts/ui-checks/admin-dashboard-day-selection/selected-day.png`
- Modify production/test files only if verification exposes an in-scope defect.

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: repeatable evidence that default, selected, refresh, reset, responsive layout, and timeline proportions work through live FastAPI.

- [ ] **Step 1: Create a deterministic temporary browser fixture**

Create the ignored artifact directory and a seed script that initializes a database through `app.db.init_db()`, then inserts:

- one Machine 1 order crossing the chosen day’s opening boundary;
- one pause entirely inside the chosen day;
- one Machine 2 order crossing the chosen day’s closing boundary;
- roll entries sufficient to render productivity rows;
- Machines 3 and 4 with no production so their full idle bars remain visible.

Use the fixed completed Sofia date `2026-08-24`, matching the deterministic model and route cases above. Write only under `.test-runtime/admin-dashboard-day-selection/`.

- [ ] **Step 2: Start FastAPI against only that temporary database**

Run:

```bash
mkdir -p .test-runtime/admin-dashboard-day-selection artifacts/ui-checks/admin-dashboard-day-selection
EXTRUSION_DB_PATH="$PWD/.test-runtime/admin-dashboard-day-selection/fixture.sqlite3" \
  .venv/bin/python artifacts/ui-checks/admin-dashboard-day-selection/seed.py
EXTRUSION_DB_PATH="$PWD/.test-runtime/admin-dashboard-day-selection/fixture.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8016
```

Keep the server in a managed session and stop it after verification.

- [ ] **Step 3: Run a task-specific repo-local Playwright check**

Create `verify.mjs` using the installed `playwright` package. The script must:

```javascript
await page.goto(`${baseURL}/admin/dashboard`, { waitUntil: "networkidle" });
assert.match(await page.locator(".dashboard-title p").innerText(), /^Последни 24 часа/);
assert.equal(await page.locator("#dashboard-day").inputValue(), "");
assert.equal(await page.locator("[data-dashboard-window-reset]").count(), 0);

await page.locator("#dashboard-day").fill(selectedDay);
await page.locator("#dashboard-day").dispatchEvent("change");
await page.waitForURL(`**/admin/dashboard?day=${selectedDay}`);
assert.match(await page.locator(".dashboard-title p").innerText(), /^Избран ден/);
assert.equal(await page.locator("#dashboard-day").inputValue(), selectedDay);
assert.equal(await page.locator("[data-machine-row]").count(), 4);

await page.getByRole("button", { name: "Обнови" }).click();
await page.waitForLoadState("networkidle");
assert.ok(page.url().endsWith(`?day=${selectedDay}`));

await page.locator("[data-dashboard-window-reset]").click();
await page.waitForURL("**/admin/dashboard");
assert.equal(await page.locator("#dashboard-day").inputValue(), "");
assert.equal(
  await page.evaluate(() => document.documentElement.scrollWidth === document.documentElement.clientWidth),
  true,
);
```

Also collect console/page errors, verify the input’s `max` equals yesterday in Sofia, confirm selected-day order rows match only overlapping orders, and confirm each machine track’s child flex widths sum to the track width within browser rounding tolerance. Repeat the overflow assertion at 1440×1024, 1024×1024, and 820×1024.

Save `default-24-hours.png` and `selected-day.png` under the artifact directory. Run with:

```bash
BASE_URL=http://127.0.0.1:8016 \
ARTIFACT_DIR="$PWD/artifacts/ui-checks/admin-dashboard-day-selection" \
node artifacts/ui-checks/admin-dashboard-day-selection/verify.mjs
```

- [ ] **Step 4: Run final automated verification**

Run fresh commands after all fixes:

```bash
.venv/bin/python -m pytest tests/test_admin_machine_dashboard.py tests/test_admin_routes.py -q
.venv/bin/python -m pytest
git diff --check
git status --short
```

Expected: focused and full suites pass, `git diff --check` is silent, browser verification exits `0`, and no runtime/production database, artifact, or unrelated user file is staged.

- [ ] **Step 5: Review the final feature slice**

Review only the scoped diff for:

- correct Sofia local-day boundaries and 23/25-hour behavior;
- a single consistent request timestamp;
- no mixed productivity numerator/denominator cutoff;
- safe invalid-query handling;
- no database mutation or schema change;
- preservation of the approved dashboard design and existing timeline proportions;
- accessibility and responsive layout of the new controls.

Resolve every Critical or Important finding, rerun the covering checks, and report the work as review-ready without staging or committing it.
