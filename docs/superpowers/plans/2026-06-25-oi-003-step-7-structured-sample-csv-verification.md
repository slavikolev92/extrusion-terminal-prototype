# OI-003 Step 7 Structured Sample CSV Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify the completed structured-recipe parser/storage/sync/release/display/print contract with representative structured sample CSV data.

**Architecture:** Add a tracked sample CSV fixture and focused workflow tests that exercise import, admin correction, release, terminal structured display, material/batch saving, completion, and print source-text preservation. Keep the app behavior unchanged unless verification exposes a concrete bug in the existing Step 2-6.5 implementation.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, pytest with temporary SQLite databases, local Playwright against the live FastAPI app, existing Jinja2 templates.

---

## Repository Rules For Execution

- Work in `/home/sk/projects/extrusion-terminal` on branch `structured-recipe-redesign`.
- Follow `AGENTS.md`; `README.md` is authoritative if project docs conflict.
- This plan is for OI-003 Step 7 only.
- Do not implement Step 8 Excel macro validation.
- Do not add app-side catalog management, pricing, inventory, ERP behavior, users, roles, or permissions.
- Do not change print layout or print CSS.
- Do not write terminal-entered data back to Excel.
- Do not mutate `data/extrusion_terminal.sqlite3` during tests or manual verification.
- Use the repo-local virtualenv for Python commands.
- Use local Node Playwright installed in this repo for browser verification.
- Save browser artifacts under `artifacts/ui-checks/structured-sample-csv/`.
- Use a temporary live-app database under `.test-runtime/structured-sample-csv/extrusion_terminal.sqlite3`.
- Do not stage or commit unless the user explicitly asks.

## Context Loaded Before This Plan

- `AGENTS.md`
- `README.md`
- `IMPLEMENTATION_PLAN.md`
- `open-issues.md`
- `docs/implementation-notes/structured-recipe-contract.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-parser.md`
- `docs/superpowers/plans/2026-06-24-structured-recipe-storage.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-sync.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-release-gate.md`
- `docs/superpowers/plans/2026-06-25-structured-recipe-display-redesign.md`
- `docs/superpowers/plans/2026-06-25-oi-003-step-6-5-recipe-na-omissions.md`
- `app/importer.py`
- `app/db.py`
- `app/main.py`
- `app/rules.py`
- `app/recipe_parser.py`
- `app/printing.py`
- `app/templates/admin_import.html`
- `app/templates/admin_planning.html`
- `app/templates/admin_card_detail.html`
- `app/templates/terminal.html`
- `app/templates/print_card.html`
- `tests/test_recipe_parser.py`
- `tests/test_recipe_storage.py`
- `tests/test_recipe_sync.py`
- `tests/test_recipe_release_validation.py`
- `tests/test_admin_card_review.py`
- `tests/test_admin_card_detail_redesign.py`
- `tests/test_terminal_detail.py`
- `tests/test_terminal_v8_render.py`
- `tests/test_print_output.py`
- untracked prior manual artifacts under `.test-runtime/recipe-na-omissions/` and `.test-runtime/fast-audit-20260624/` inspected as precedent only

Current branch status before this plan showed pre-existing untracked plan/demo files:

```text
?? docs/superpowers/plans/2026-06-24-structured-recipe-storage.md
?? docs/superpowers/plans/2026-06-25-oi-003-step-6-5-recipe-na-omissions.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-display-redesign.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-release-gate.md
?? docs/superpowers/plans/2026-06-25-structured-recipe-sync.md
?? interim-costing-process/recipe-catalog-review/
?? interim-costing-process/source-files/recipe-builder-demo/
```

Do not clean up, stage, or revert those paths during Step 7.

## Exact Scope

Implement OI-003 Step 7 verification:

- Create several representative sample extrusion orders using the structured `AM:AS` source-cell convention.
- Verify CSV import creates persisted cards and normalized `recipe_components`.
- Verify admin review displays structured rows with category, planned material, percent, planned kg, actual material, and batch/lot.
- Verify admin correction can fix an imported draft recipe before release.
- Verify release accepts valid structured rows and blocks the intentionally invalid draft until corrected.
- Verify terminal display renders structured rows, category-only fallback rows, planned kg, and material/batch inputs.
- Verify terminal actual material and batch/lot save persists with loaded-version checks.
- Verify one sample card can be completed after timing, tare, and roll entry.
- Verify print output remains based on original source text, including the `|` delimiter and percent text.
- Capture at least one focused Playwright screenshot for admin and terminal structured sample data.
- Update `IMPLEMENTATION_PLAN.md` only after verification passes, marking OI-003 Step 7 complete.

## Explicit Non-Scope

Do not add:

- Excel macro validation or workbook export changes.
- App-side `RecipeCatalog` or material master management.
- Pricing, costing, inventory, ERP behavior, users, roles, permissions, or authentication.
- New print layout, print CSS, or print route behavior.
- New release rules beyond fixing a defect exposed by the sample workflow.
- Terminal data write-back to Excel.
- Any cleanup of unrelated untracked plan/demo files.

## File Map

Create:

- `tests/fixtures/structured_recipe_sample.csv`
  - Tracked sample CSV with several structured-recipe orders.

- `tests/test_structured_recipe_sample_csv.py`
  - Focused Step 7 workflow tests using the tracked CSV fixture and temporary SQLite databases.

- `scripts/verify_structured_sample_csv_ui.mjs`
  - Repeatable Playwright browser check against a live FastAPI app.
  - Writes screenshots and a small JSON summary only under `artifacts/ui-checks/structured-sample-csv/`.

Modify:

- `IMPLEMENTATION_PLAN.md`
  - Mark OI-003 Step 7 complete after automated and manual/live verification pass.

Modify only if verification exposes a real defect:

- `app/importer.py`
- `app/db.py`
- `app/main.py`
- `app/templates/admin_card_detail.html`
- `app/templates/terminal.html`
- focused tests near the defect

Files that should not change:

- `app/printing.py`
- `app/static/css/print.css`
- `source-files/excel-macros/**`
- `interim-costing-process/**`

## Sample CSV Data

Create `tests/fixtures/structured_recipe_sample.csv` exactly with these rows:

```csv
order_number,order_date,delivery_date,customer,city,product_type,quantity_1,unit_1,quantity_2,unit_2,product_form,material,size_thickness,notes,extrusion_flag,extrusion_folding,extrusion_next_operation,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
SR-SAMPLE-001,2026-06-25,2026-06-30,Structured Full Blend,Sofia,PE film,1000,kg,,rolls,flat,LDPE / LLDPE,600/0.050,Full structured recipe sample,da,single,rewind,corona,LDPE Rompetrol Midilena B20/03 | 77%,,,LLDPE SABIC 119ZJ | 18%,Antistatic Novachem AT 04673 LD | 2%,Masterbatch Polibach White 8000 ET | 3%,,rolls
SR-SAMPLE-002,2026-06-25,2026-07-01,Category Only Customer,Plovdiv,PE sheet,1250,kg,,rolls,flat,reLDPE,720/0.070,Category-only N/A omission sample,da,double,cutting,none,reLDPE | 80%,,,LLDPE SABIC 119ZJ | 20%,,,,rolls
SR-SAMPLE-003,2026-06-25,2026-07-02,One Sided Omission Customer,Varna,PE bag film,800,kg,,rolls,sleeve,LDPE,500/0.040,One-sided omission sample,da,single,rewind,corona,LDPE B20/03 | 95%,,,,,Masterbatch | 5%,,rolls
SR-SAMPLE-004,2026-06-25,2026-07-03,Correction Customer,Burgas,PE correction film,900,kg,,rolls,flat,LDPE / LLDPE,540/0.060,Imported invalid total then corrected in admin,da,single,rewind,corona,LDPE Correction A | 80%,,,LLDPE Correction L | 19%,,,,rolls
```

Meaning:

- `SR-SAMPLE-001`: normal full producer/grade structured recipe, total `100%`, target gross `1000 kg`.
- `SR-SAMPLE-002`: Excel-builder category-only final source cell, `reLDPE | 80%`, total `100%`, target gross `1250 kg`.
- `SR-SAMPLE-003`: one-sided omission and category-only additive final source cells, `LDPE B20/03 | 95%` and `Masterbatch | 5%`, total `100%`.
- `SR-SAMPLE-004`: intentionally invalid total `99%` that must import as a draft, block release, then be corrected in admin to `LDPE Correction A | 80%` and `LLDPE Correction L | 20%`.

## Task 1: Add The Structured Sample CSV Fixture

**Files:**

- Create: `tests/fixtures/structured_recipe_sample.csv`

- [ ] **Step 1: Create the fixture directory**

Run:

```bash
mkdir -p tests/fixtures
```

Expected: directory exists. This is a tracked test-fixture directory, unlike `.test-runtime/`.

- [ ] **Step 2: Create `tests/fixtures/structured_recipe_sample.csv`**

Add the exact CSV content from the “Sample CSV Data” section.

- [ ] **Step 3: Verify the fixture has four data rows**

Run:

```bash
source .venv/bin/activate
python - <<'PY'
import csv
from pathlib import Path

path = Path("tests/fixtures/structured_recipe_sample.csv")
rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
print(len(rows), [row["order_number"] for row in rows])
assert len(rows) == 4
assert [row["order_number"] for row in rows] == [
    "SR-SAMPLE-001",
    "SR-SAMPLE-002",
    "SR-SAMPLE-003",
    "SR-SAMPLE-004",
]
PY
```

Expected output:

```text
4 ['SR-SAMPLE-001', 'SR-SAMPLE-002', 'SR-SAMPLE-003', 'SR-SAMPLE-004']
```

## Task 2: Add Focused Sample CSV Workflow Tests

**Files:**

- Create: `tests/test_structured_recipe_sample_csv.py`
- Test fixture: `tests/fixtures/structured_recipe_sample.csv`

- [ ] **Step 1: Create `tests/test_structured_recipe_sample_csv.py` with helpers**

Add:

```python
from __future__ import annotations

from pathlib import Path

from app import db
from app.constants import STATUS_COMPLETED, STATUS_IMPORTED, STATUS_PENDING
from app.importer import IMPORT_FIELDS, import_cards_from_csv
from app.main import admin_card_detail_context, terminal_context
from app.printing import build_print_readiness


FIXTURE_PATH = Path("tests/fixtures/structured_recipe_sample.csv")
RECIPE_RELEASE_PREFIX = "Рецептата не може да бъде пусната"


def import_sample_csv() -> object:
    return import_cards_from_csv(
        "structured_recipe_sample.csv",
        FIXTURE_PATH.read_bytes(),
        overwrite_existing=False,
    )


def card_id_for_order(order_number: str) -> int:
    with db.connect() as connection:
        row = connection.execute(
            "SELECT id FROM cards WHERE order_number = ?",
            (order_number,),
        ).fetchone()
    assert row is not None
    return int(row["id"])


def component_summary(card_id: int) -> list[tuple[str, str, str, str, str]]:
    with db.connect() as connection:
        return [
            (
                str(row["component_key"]),
                str(row["source_text"]),
                str(row["material_category"]),
                str(row["planned_material"]),
                str(row["recipe_percent"]),
            )
            for row in db.fetch_recipe_components(connection, card_id)
        ]


def current_import_fields(card_id: int) -> dict[str, str]:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return {field: str(card[field] or "") for field in IMPORT_FIELDS}


def card_version(card_id: int) -> int:
    card = db.fetch_admin_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def terminal_card_version(card_id: int) -> int:
    card = db.fetch_terminal_card_detail(card_id)
    assert card is not None
    return int(card["version"])


def release_card(card_id: int, machine_id: int = 1, sequence: int = 1):
    return db.release_card(
        card_id,
        machine_id=machine_id,
        machine_sequence=sequence,
        loaded_version=card_version(card_id),
        max_roll_weight="64.50",
    )


def complete_card(card_id: int) -> None:
    assert db.start_production_timing(card_id, terminal_card_version(card_id)).ok
    assert db.update_tare_weight(card_id, terminal_card_version(card_id), "1.20").ok
    assert db.add_roll_gross_weight(card_id, terminal_card_version(card_id), "501.20").ok
    assert db.finish_card(card_id, terminal_card_version(card_id)).ok
```

- [ ] **Step 2: Add import and normalized storage test**

Append:

```python
def test_structured_sample_csv_imports_and_normalizes_recipe_components(connection):
    result = import_sample_csv()

    assert result.rows_seen == 4
    assert result.rows_imported == 4
    assert result.created == 4
    assert result.updated == 0
    assert result.skipped == 0
    assert result.row_errors == []

    full_id = card_id_for_order("SR-SAMPLE-001")
    category_only_id = card_id_for_order("SR-SAMPLE-002")
    one_sided_id = card_id_for_order("SR-SAMPLE-003")
    correction_id = card_id_for_order("SR-SAMPLE-004")

    assert component_summary(full_id) == [
        (
            "raw_material_a",
            "LDPE Rompetrol Midilena B20/03 | 77%",
            "LDPE",
            "Rompetrol Midilena B20/03",
            "77",
        ),
        ("linear_pe", "LLDPE SABIC 119ZJ | 18%", "LLDPE", "SABIC 119ZJ", "18"),
        (
            "antistatic",
            "Antistatic Novachem AT 04673 LD | 2%",
            "Antistatic",
            "Novachem AT 04673 LD",
            "2",
        ),
        (
            "masterbatch",
            "Masterbatch Polibach White 8000 ET | 3%",
            "Masterbatch",
            "Polibach White 8000 ET",
            "3",
        ),
    ]
    assert component_summary(category_only_id) == [
        ("raw_material_a", "reLDPE | 80%", "reLDPE", "", "80"),
        ("linear_pe", "LLDPE SABIC 119ZJ | 20%", "LLDPE", "SABIC 119ZJ", "20"),
    ]
    assert component_summary(one_sided_id) == [
        ("raw_material_a", "LDPE B20/03 | 95%", "LDPE", "B20/03", "95"),
        ("masterbatch", "Masterbatch | 5%", "Masterbatch", "", "5"),
    ]
    assert component_summary(correction_id) == [
        ("raw_material_a", "LDPE Correction A | 80%", "LDPE", "Correction A", "80"),
        ("linear_pe", "LLDPE Correction L | 19%", "LLDPE", "Correction L", "19"),
    ]
```

- [ ] **Step 3: Add release gate and admin correction test**

Append:

```python
def test_structured_sample_invalid_total_blocks_release_until_admin_correction(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-004")

    blocked = release_card(card_id)
    card = db.fetch_admin_card_detail(card_id)

    assert not blocked.ok
    assert blocked.messages == (
        f"{RECIPE_RELEASE_PREFIX}: сборът на процентите трябва да е точно 100%. "
        "Коригирайте рецептата и опитайте отново.",
    )
    assert card["status"] == STATUS_IMPORTED
    assert card["machine_id"] is None
    assert card["machine_sequence"] is None

    fields = current_import_fields(card_id)
    fields["linear_pe"] = "LLDPE Correction L | 20%"
    saved = db.update_admin_imported_fields(card_id, card_version(card_id), fields)
    assert saved.ok
    assert component_summary(card_id) == [
        ("raw_material_a", "LDPE Correction A | 80%", "LDPE", "Correction A", "80"),
        ("linear_pe", "LLDPE Correction L | 20%", "LLDPE", "Correction L", "20"),
    ]

    released = release_card(card_id, machine_id=2, sequence=1)
    released_card = db.fetch_admin_card_detail(card_id)

    assert released.ok
    assert released_card["status"] == STATUS_PENDING
    assert released_card["machine_id"] == 2
    assert released_card["machine_sequence"] == 1
```

- [ ] **Step 4: Add admin and terminal display test**

Append:

```python
def test_structured_sample_admin_and_terminal_display_structured_rows(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-002")
    assert release_card(card_id, machine_id=1, sequence=1).ok

    admin_context = admin_card_detail_context(card_id)
    terminal = terminal_context(card_id)
    assert admin_context is not None
    admin_rows = {row["field"]: row for row in admin_context["recipe_rows"]}
    terminal_rows = {row["field"]: row for row in terminal["recipe_rows"]}

    assert admin_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert admin_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert admin_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert admin_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert admin_rows["raw_material_a"]["planned_kg"] == "1000.00"
    assert admin_rows["raw_material_a"]["is_structured"] is True

    assert terminal_rows["raw_material_a"]["source_text"] == "reLDPE | 80%"
    assert terminal_rows["raw_material_a"]["material_category"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["planned_material"] == "reLDPE"
    assert terminal_rows["raw_material_a"]["recipe_percent"] == "80%"
    assert terminal_rows["raw_material_a"]["planned_kg"] == "1000.00"
    assert terminal_rows["linear_pe"]["planned_material"] == "SABIC 119ZJ"
    assert "masterbatch" not in terminal_rows
```

- [ ] **Step 5: Add terminal material/batch save and completion test**

Append:

```python
def test_structured_sample_terminal_material_save_and_completion(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-001")
    assert release_card(card_id, machine_id=1, sequence=1).ok

    saved = db.update_terminal_recipe_actual_entries(
        card_id,
        terminal_card_version(card_id),
        {
            "raw_material_a": {
                "actual_material_used": "Actual Rompetrol B20/03",
                "batch_lot": "LOT-A-77",
            },
            "linear_pe": {
                "actual_material_used": "Actual SABIC 119ZJ",
                "batch_lot": "LOT-L-18",
            },
            "antistatic": {
                "actual_material_used": "Actual AT 04673",
                "batch_lot": "LOT-AS-2",
            },
            "masterbatch": {
                "actual_material_used": "Actual White 8000",
                "batch_lot": "LOT-MB-3",
            },
        },
    )
    assert saved.ok

    terminal = terminal_context(card_id)
    rows = {row["field"]: row for row in terminal["recipe_rows"]}
    assert rows["raw_material_a"]["actual_material"] == "Actual Rompetrol B20/03"
    assert rows["raw_material_a"]["batch"] == "LOT-A-77"
    assert rows["masterbatch"]["actual_material"] == "Actual White 8000"

    complete_card(card_id)
    completed = db.fetch_admin_card_detail(card_id)
    assert completed["status"] == STATUS_COMPLETED
    assert completed["finished_at"]
    assert completed["total_gross_weight"] is not None
    assert completed["total_net_weight"] is not None
```

- [ ] **Step 6: Add unchanged print output boundary test**

Append:

```python
def test_structured_sample_print_output_uses_original_source_text(connection):
    import_sample_csv()
    card_id = card_id_for_order("SR-SAMPLE-001")
    assert release_card(card_id, machine_id=1, sequence=1).ok
    complete_card(card_id)

    readiness = build_print_readiness(card_id)

    assert readiness.ok
    assert readiness.data is not None
    rows = {
        row["component_key"]: row
        for row in readiness.data["front"]["recipe_rows"]
    }
    assert rows["raw_material_a"]["planned_material"] == (
        "LDPE Rompetrol Midilena B20/03 | 77%"
    )
    assert rows["linear_pe"]["planned_material"] == "LLDPE SABIC 119ZJ | 18%"
    assert rows["antistatic"]["planned_material"] == (
        "Antistatic Novachem AT 04673 LD | 2%"
    )
    assert rows["masterbatch"]["planned_material"] == (
        "Masterbatch Polibach White 8000 ET | 3%"
    )
    assert "material_category" not in rows["raw_material_a"]
```

- [ ] **Step 7: Run the new focused tests**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_structured_recipe_sample_csv.py -q
```

Expected:

```text
5 passed
```

If a test fails, fix only a concrete Step 7 verification defect or update a wrong test expectation. Do not add new product behavior.

## Task 3: Add A Repeatable Playwright Live-App Verification Script

**Files:**

- Create: `scripts/verify_structured_sample_csv_ui.mjs`
- Uses fixture: `tests/fixtures/structured_recipe_sample.csv`
- Writes artifacts under: `artifacts/ui-checks/structured-sample-csv/`

- [ ] **Step 1: Create `scripts/verify_structured_sample_csv_ui.mjs`**

Add:

```javascript
const { chromium } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const baseURL = process.env.BASE_URL || "http://127.0.0.1:8000";
const artifactDir = "artifacts/ui-checks/structured-sample-csv";
const fixturePath = "tests/fixtures/structured_recipe_sample.csv";

async function clickFirstMatching(page, names) {
  for (const name of names) {
    const locator = page.getByRole("button", { name });
    if (await locator.count()) {
      await locator.first().click();
      return;
    }
  }
  throw new Error(`No matching button found for ${names.map(String).join(", ")}`);
}

(async () => {
  fs.mkdirSync(artifactDir, { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
  const summary = {};

  await page.goto(`${baseURL}/admin/import`);
  await page.locator('input[type="file"][name="csv_file"]').setInputFiles(fixturePath);
  await clickFirstMatching(page, [/Импортирай CSV/i, /Импортирай/i]);
  await page.getByText("4 импортирани").waitFor();
  summary.importUrl = page.url();

  await page.goto(`${baseURL}/admin/planning`);
  const categoryOrder = page.getByRole("row").filter({ hasText: "SR-SAMPLE-002" });
  await categoryOrder.locator('select[name="machine_id"]').selectOption("1");
  await categoryOrder.locator('input[name="machine_sequence"]').fill("1");
  await categoryOrder.locator('input[name="max_roll_weight"]').fill("64.50");
  await categoryOrder.getByRole("button", { name: /Изпрати/i }).click();
  await page.waitForLoadState("networkidle");

  await page.goto(`${baseURL}/admin/cards`);
  await page.getByRole("link", { name: "SR-SAMPLE-002" }).click();
  await page.getByText("Категория").waitFor();
  await page.getByText("Планирани материали").waitFor();
  await page.getByText("reLDPE").waitFor();
  await page.getByText("1000.00").waitFor();
  await page.locator('input[name="planned_material__raw_material_a"][value="reLDPE | 80%"]').waitFor();
  await page.screenshot({
    path: path.join(artifactDir, "admin-category-only-structured-sample.png"),
    fullPage: true,
  });
  summary.adminUrl = page.url();

  await page.goto(`${baseURL}/terminal`);
  await page.getByText("SR-SAMPLE-002").waitFor();
  await page.getByText("Категория").waitFor();
  await page.getByText("Планирани материали").waitFor();
  await page.getByText("reLDPE").waitFor();
  await page.getByText("1000.00").waitFor();
  await page.locator('input[name="actual_material__raw_material_a"]').fill("Actual reLDPE UI");
  await page.locator('input[name="batch_lot__raw_material_a"]').fill("LOT-UI-80");
  await page.locator('input[name="batch_lot__raw_material_a"]').press("Enter");
  await page.waitForLoadState("networkidle");
  await page.reload();
  await page.getByDisplayValue("Actual reLDPE UI").waitFor();
  await page.getByDisplayValue("LOT-UI-80").waitFor();
  await page.screenshot({
    path: path.join(artifactDir, "terminal-category-only-structured-sample.png"),
    fullPage: true,
  });
  summary.terminalUrl = page.url();
  summary.screenshots = [
    path.join(artifactDir, "admin-category-only-structured-sample.png"),
    path.join(artifactDir, "terminal-category-only-structured-sample.png"),
  ];

  fs.writeFileSync(
    path.join(artifactDir, "structured-sample-ui-summary.json"),
    JSON.stringify(summary, null, 2),
  );

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
```

- [ ] **Step 2: Syntax-check the Playwright script**

Run:

```bash
node --check scripts/verify_structured_sample_csv_ui.mjs
```

Expected:

```text
no output
```

## Task 4: Run Focused Automated Verification

**Files:**

- No edits unless verification exposes a concrete defect.

- [ ] **Step 1: Run the focused Step 7 test**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_structured_recipe_sample_csv.py -q
```

Expected:

```text
5 passed
```

- [ ] **Step 2: Run the focused structured recipe suite**

Run:

```bash
source .venv/bin/activate
python -m pytest \
  tests/test_recipe_parser.py \
  tests/test_recipe_storage.py \
  tests/test_recipe_sync.py \
  tests/test_recipe_release_validation.py \
  tests/test_structured_recipe_sample_csv.py \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_terminal_detail.py \
  tests/test_terminal_v8_render.py \
  tests/test_print_output.py \
  -q
```

Expected: all selected tests pass.

- [ ] **Step 3: Run syntax/import checks**

Run:

```bash
source .venv/bin/activate
python -m compileall app
```

Expected: no syntax errors.

- [ ] **Step 4: Run the full Python suite**

Run:

```bash
source .venv/bin/activate
python -m pytest
```

Expected: full suite passes.

- [ ] **Step 5: Run diff whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

## Task 5: Manual Live FastAPI + Playwright Verification

**Files:**

- Writes artifacts only under `artifacts/ui-checks/structured-sample-csv/`
- Uses temp DB only at `.test-runtime/structured-sample-csv/extrusion_terminal.sqlite3`
- Runs script: `scripts/verify_structured_sample_csv_ui.mjs`

- [ ] **Step 1: Create runtime and artifact directories**

Run:

```bash
mkdir -p artifacts/ui-checks/structured-sample-csv .test-runtime/structured-sample-csv
```

- [ ] **Step 2: Start the app against a temporary database**

Run in one terminal:

```bash
source .venv/bin/activate
EXTRUSION_DB_PATH=.test-runtime/structured-sample-csv/extrusion_terminal.sqlite3 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If port `8000` is already occupied, use another local port such as `8001` and pass it to the Playwright script with `BASE_URL`.

- [ ] **Step 3: Run the Playwright check**

Run in a second terminal:

```bash
BASE_URL=http://127.0.0.1:8000 node scripts/verify_structured_sample_csv_ui.mjs
```

Expected:

- CSV imports successfully through `/admin/import`.
- `SR-SAMPLE-002` releases from `/admin/planning`.
- Admin detail shows structured columns, `reLDPE`, `80%`, `1000.00`, and source input value `reLDPE | 80%`.
- Terminal shows structured columns, `reLDPE`, `80%`, `1000.00`.
- Terminal actual material and batch/lot save and persist after reload.
- Screenshots are created:
  - `artifacts/ui-checks/structured-sample-csv/admin-category-only-structured-sample.png`
  - `artifacts/ui-checks/structured-sample-csv/terminal-category-only-structured-sample.png`
  - `artifacts/ui-checks/structured-sample-csv/structured-sample-ui-summary.json`

- [ ] **Step 4: Stop the dev server**

Stop the `uvicorn` process with `Ctrl-C`. Do not leave a server session running.

## Task 6: Update Milestone Tracker

**Files:**

- Modify: `IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Update the structured recipe follow-up note**

In `IMPLEMENTATION_PLAN.md`, add this bullet after the Step 6.5 bullet under “Structured recipe redesign follow-up”:

```markdown
- OI-003 Step 7 complete: structured sample CSV data now verifies import, normalized recipe-component sync, admin review/correction, release gating, terminal structured display, actual material/batch saving, completion behavior, and unchanged print source-text output. Focused pytest coverage uses `tests/fixtures/structured_recipe_sample.csv`, and live Playwright verification captures admin/terminal screenshots under `artifacts/ui-checks/structured-sample-csv/` with a temporary database under `.test-runtime/structured-sample-csv/`.
```

- [ ] **Step 2: Keep Step 8 future-scoped**

Confirm the Step 8 Excel macro validation bullet remains future work and no macro files were changed.

- [ ] **Step 3: Inspect the tracker diff**

Run:

```bash
git diff -- IMPLEMENTATION_PLAN.md
```

Expected: only the concise Step 7 status note changed.

## Task 7: Final Review And Status Check

**Files:**

- No edits unless the review finds a concrete Step 7 issue.

- [ ] **Step 1: Review changed file list**

Run:

```bash
git status --short
git diff --name-only
```

Expected tracked changes from Step 7:

```text
IMPLEMENTATION_PLAN.md
scripts/verify_structured_sample_csv_ui.mjs
tests/fixtures/structured_recipe_sample.csv
tests/test_structured_recipe_sample_csv.py
```

If code files changed because a verification bug was fixed, inspect those diffs carefully and include them in the final summary. Pre-existing untracked plans/demo directories may still appear and must not be reverted.

- [ ] **Step 2: Review Step 7 diff**

Run:

```bash
git diff -- \
  IMPLEMENTATION_PLAN.md \
  scripts/verify_structured_sample_csv_ui.mjs \
  tests/fixtures/structured_recipe_sample.csv \
  tests/test_structured_recipe_sample_csv.py
```

Check:

- fixture uses only structured source-cell data;
- invalid sample imports as draft and is corrected before release;
- tests use temporary DB fixtures and never mutate `data/extrusion_terminal.sqlite3`;
- print assertion checks original source text, not normalized display rows;
- Playwright artifacts stay under `artifacts/ui-checks/structured-sample-csv/`;
- temp live-app DB path stays under `.test-runtime/structured-sample-csv/`;
- no Excel macro, catalog, pricing, inventory, ERP, auth, or print-layout work slipped in.

- [ ] **Step 3: Final verification commands**

Run:

```bash
source .venv/bin/activate
python -m pytest tests/test_structured_recipe_sample_csv.py -q
python -m pytest \
  tests/test_recipe_parser.py \
  tests/test_recipe_storage.py \
  tests/test_recipe_sync.py \
  tests/test_recipe_release_validation.py \
  tests/test_structured_recipe_sample_csv.py \
  tests/test_admin_card_review.py \
  tests/test_admin_card_detail_redesign.py \
  tests/test_terminal_detail.py \
  tests/test_terminal_v8_render.py \
  tests/test_print_output.py \
  -q
python -m compileall app
python -m pytest
git diff --check
```

Expected: all commands pass.

- [ ] **Step 4: Confirm manual artifacts**

Run:

```bash
ls -1 artifacts/ui-checks/structured-sample-csv
```

Expected output includes:

```text
admin-category-only-structured-sample.png
structured-sample-ui-summary.json
terminal-category-only-structured-sample.png
```

- [ ] **Step 5: Report final status**

Report:

- focused Step 7 test result;
- focused structured recipe suite result;
- full Python suite result;
- `python -m compileall app` result;
- `git diff --check` result;
- Playwright screenshot artifact paths;
- temporary DB path used;
- confirmation that no staging or commit was performed.

## Self-Review

- Spec coverage: The plan covers sample structured CSV data, import, admin review/correction, release, terminal display, actual material/batch save, completion, unchanged print output, automated tests, live FastAPI/Playwright verification, screenshots under `artifacts/ui-checks/`, temp DB under `.test-runtime/`, `.venv` commands, and no staging/commit.
- Non-scope coverage: Excel macro validation, app-side catalog management, pricing, inventory, ERP behavior, auth, and print layout changes are explicitly excluded.
- Placeholder scan: No placeholder markers or unspecified test steps remain.
- Type/signature consistency: Tests use existing functions `import_cards_from_csv`, `db.release_card`, `db.update_admin_imported_fields`, `admin_card_detail_context`, `terminal_context`, `db.update_terminal_recipe_actual_entries`, `db.start_production_timing`, `db.update_tare_weight`, `db.add_roll_gross_weight`, `db.finish_card`, and `build_print_readiness`.
