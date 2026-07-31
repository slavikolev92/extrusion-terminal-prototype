# Fixed Pallet Print Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop page-2 and overflow pallet-summary tables from stretching sparse rows while preserving their fixed widths, fixed row heights, values, ordering, capacities, and A4 pagination.

**Architecture:** Keep the existing Jinja tables, print-data aggregation, and `8 + 8` / `48` row split unchanged. Add a focused CSS alignment rule to the two grid containers so each child table uses its declared physical row heights and natural content height. Protect the rule with a fast CSS contract test and guarded Chromium/PDF geometry checks using temporary one-pallet, two-pallet, full, and overflow fixtures.

**Tech Stack:** FastAPI/Jinja-rendered HTML, print-only CSS with physical `mm` dimensions, pytest, temporary SQLite fixtures, repository-local Playwright/Chromium, `pdfinfo`, and `pdftoppm`.

## Global Constraints

- Read root `AGENTS.md`, `README.md`, `v2-files/AGENTS.md`, the approved design at `docs/superpowers/specs/2026-07-31-fixed-pallet-print-table-design.md`, `docs/implementation-notes/print-output-reference.md`, and `docs/implementation-notes/roll-pallet-assignment.md` before implementation.
- Do not modify pallet grouping, sorting, roll counts, gross/net calculations, `PALLET_BACK_COLUMN_CAPACITY = 8`, or `PALLET_OVERFLOW_PAGE_CAPACITY = 48`.
- Do not modify `app/printing.py`, `app/templates/print_card.html`, database schema, migrations, routes, production writes, terminal behavior, or admin behavior unless new evidence proves the approved CSS-only diagnosis false. Stop and return to systematic debugging if that happens.
- A pallet table contains one fixed-height header and exactly one fixed-height data row per rendered pallet. Do not create filler rows or fixed-height empty table frames.
- Keep existing fixed horizontal geometry unchanged: page-2 pallet columns remain `53.5mm` wide and the overflow table retains its existing fixed page width and column proportions. Row count must not affect width.
- A short pallet table must leave blank page space below it. It must not stretch itself, adjacent pallet tables, or the left production-summary table.
- A taller pallet table must not stretch the left production-summary rows.
- A partially filled final overflow page must contain only its repeated identification/header and remaining pallet rows, with blank page space below.
- Preserve normal two-page A4 output, whole-summary overflow beginning on page 3, and the current number of pages produced by the 97-row guarded overflow fixture.
- Use only the repository-local `.venv` and `node_modules`; do not install or download Python, Node, Playwright, or browser dependencies.
- All browser and PDF checks must use a database below `.test-runtime/` and artifacts below `artifacts/ui-checks/`. Never open or mutate `data/extrusion_terminal.sqlite3` or a production database/backup.
- Preserve the user's unrelated working-tree changes: deleted `design-qa.md`, modified `v2-files/PLAN.md`, untracked `docs/implementation-notes/excel-csv-import-contract-debug-handoff.md`, and untracked `v2-files/MIGRATION-REPORT-2026-07-28.md`.
- Do not stage or commit. The repository policy requires separate explicit user authorization.

## File Map

- Modify `tests/test_print_output.py`: add a fast regression asserting both print grid containers explicitly disable grid stretching.
- Modify `app/static/css/print.css`: top-align child tables in `.print-summary` and `.print-page-pallet-overflow`; make no other visual change.
- Modify `scripts/create_roll_pallet_fixture.py`: add completed temporary cards that derive exactly one and exactly two pallet-summary rows.
- Modify `scripts/verify_roll_pallet_ui.mjs`: measure sparse/full row and width geometry, check the final overflow page, assert PDF page counts, and save focused evidence.
- Modify `tests/test_roll_pallet_ui_script_safety.py`: verify the expanded fixture contract and require the new geometry result from the guarded live verifier.
- Modify `docs/implementation-notes/print-output-reference.md`: record the fixed-row/no-filler/no-stretch print contract.
- Modify `docs/implementation-notes/roll-pallet-assignment.md`: record the sparse and overflow table behavior and verification coverage.
- Modify `v2-files/AGENTS.md`: append the completed feature's display-only/no-migration assessment after the implementation diff and verification are final.

No application Python, Jinja template, or SQLite file changes are expected.

---

### Task 1: Add The Sparse-Table Regression And Correct Grid Alignment

**Files:**
- Modify: `tests/test_print_output.py:1538-1565`
- Modify: `scripts/create_roll_pallet_fixture.py:218-320`
- Modify: `tests/test_roll_pallet_ui_script_safety.py:405-565`
- Modify: `scripts/verify_roll_pallet_ui.mjs:25-37, 840-1080`
- Modify: `app/static/css/print.css:48-70, 535-544`

**Interfaces:**
- Consumes: existing `insert_card()`, `add_rolls()`, and `add_timing()` fixture helpers; existing `/cards/{card_id}/print`; existing `inspectActualPrint()`, `pdfToPng()`, and guarded artifact-path checks.
- Produces: fixture IDs `cards.completed_one_pallet` and `cards.completed_two_pallets`; `summary.print.fixedTableGeometry`; CSS rules that content-size both summary-grid table contexts.

- [ ] **Step 1: Add the failing fast CSS contract test**

Add this focused test beside the existing print CSS tests in `tests/test_print_output.py`:

```python
def test_print_css_summary_grids_do_not_stretch_child_tables():
    css = PRINT_CSS_PATH.read_text(encoding="utf-8")

    for selector in (".print-summary", ".print-page-pallet-overflow"):
        assert re.search(
            rf"{re.escape(selector)}\s*\{{[^}}]*align-items:\s*start;",
            css,
            flags=re.DOTALL,
        ), selector

    assert re.search(
        r"\.print-summary\s*\{[^}]*grid-template-columns:\s*63mm\s+53\.5mm\s+53\.5mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.print-pallet-summary th,\s*\.print-pallet-summary td\s*\{[^}]*height:\s*4\.6mm;",
        css,
        flags=re.DOTALL,
    )
    assert re.search(
        r"\.print-pallet-overflow-table th,\s*\.print-pallet-overflow-table td\s*\{[^}]*height:\s*5mm;",
        css,
        flags=re.DOTALL,
    )
```

This test intentionally checks the two grid containers rather than adding a
generic table-height override. The root cause is grid-item stretching. The
remaining assertions lock the already accepted physical column and row sizes;
they do not introduce new geometry.

- [ ] **Step 2: Run the CSS contract test and observe the intended failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_print_output.py::test_print_css_summary_grids_do_not_stretch_child_tables \
  -q
```

Expected: `FAIL`; neither existing selector declares `align-items: start`.

- [ ] **Step 3: Expand the guarded fixture contract with one- and two-pallet cards**

In `tests/test_roll_pallet_ui_script_safety.py`, rename
`test_roll_pallet_fixture_creates_only_the_four_required_card_kinds` to
`test_roll_pallet_fixture_creates_only_the_six_required_card_kinds` and require:

```python
assert set(payload["cards"]) == {
    "running",
    "completed_mixed",
    "completed_all_blank",
    "completed_one_pallet",
    "completed_two_pallets",
    "completed_overflow",
}
assert len(set(payload["cards"].values())) == 6
```

Read the two sparse summary counts from SQLite using the same temporary
database connection:

```python
sparse_pallet_counts = {
    key: connection.execute(
        """
        SELECT COUNT(DISTINCT pallet_number)
        FROM roll_entries
        WHERE card_id = ? AND pallet_number IS NOT NULL
        """,
        (payload["cards"][key],),
    ).fetchone()[0]
    for key in ("completed_one_pallet", "completed_two_pallets")
}
```

Then require both new cards to be `completed` and require:

```python
assert sparse_pallet_counts == {
    "completed_one_pallet": 1,
    "completed_two_pallets": 2,
}
assert payload["expected_summary_rows"]["completed_one_pallet"] == 1
assert payload["expected_summary_rows"]["completed_two_pallets"] == 2
```

- [ ] **Step 4: Run the expanded fixture test and observe the intended failure**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_roll_pallet_ui_script_safety.py::test_roll_pallet_fixture_creates_only_the_six_required_card_kinds \
  -q
```

Expected: `FAIL`; the fixture JSON still contains only the original four card
kinds.

- [ ] **Step 5: Add the two printable sparse cards to the temporary fixture**

In `scripts/create_roll_pallet_fixture.py`, after the all-blank completed card
and before the overflow card, create two completed cards with ordinary closed
timing:

```python
completed_one_pallet_id = insert_card(
    connection,
    order_number="PALLET-UI-ONE",
    status=STATUS_COMPLETED,
    machine_id=2,
    machine_sequence=None,
    current_pallet_number=1,
)
add_rolls(
    connection,
    card_id=completed_one_pallet_id,
    order_number="PALLET-UI-ONE",
    pallet_numbers=[1, 1],
    shift_occurrence_id=None,
)
add_timing(connection, completed_one_pallet_id, running=False)

completed_two_pallets_id = insert_card(
    connection,
    order_number="PALLET-UI-TWO",
    status=STATUS_COMPLETED,
    machine_id=3,
    machine_sequence=None,
    current_pallet_number=2,
)
add_rolls(
    connection,
    card_id=completed_two_pallets_id,
    order_number="PALLET-UI-TWO",
    pallet_numbers=[1, 2],
    shift_occurrence_id=None,
)
add_timing(connection, completed_two_pallets_id, running=False)
```

Add both IDs to `payload["cards"]` and exact counts to
`payload["expected_summary_rows"]`:

```python
"completed_one_pallet": completed_one_pallet_id,
"completed_two_pallets": completed_two_pallets_id,
```

```python
"completed_one_pallet": 1,
"completed_two_pallets": 2,
```

Do not remove or repurpose the all-blank, full page-2, or 97-row overflow
fixtures.

- [ ] **Step 6: Run the fixture safety test and confirm the temporary data contract passes**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_roll_pallet_ui_script_safety.py::test_roll_pallet_fixture_creates_only_the_six_required_card_kinds \
  -q
```

Expected: `PASS`; all six IDs are distinct, both sparse cards are completed,
and their derived distinct pallet counts are exactly one and two.

- [ ] **Step 7: Require fixed geometry in the guarded verifier integration test**

Extend
`test_roll_pallet_verifier_completes_current_pencil_editor_workflow()` after it
loads `verification-summary.json`:

```python
fixed_geometry = summary["print"]["fixedTableGeometry"]
assert fixed_geometry["onePallet"]["bodyRowCount"] == 1
assert fixed_geometry["twoPallets"]["bodyRowCount"] == 2
assert fixed_geometry["onePallet"]["pdfPages"] == 2
assert fixed_geometry["twoPallets"]["pdfPages"] == 2
assert fixed_geometry["overflow"]["lastPageBodyRowCount"] == 1
assert fixed_geometry["overflow"]["pdfPages"] == 5
assert fixed_geometry["widthsStable"] is True
assert fixed_geometry["pageTwoRowsStable"] is True
assert fixed_geometry["productionRowsStable"] is True
assert fixed_geometry["overflowRowsStable"] is True
```

Run this test once after Steps 8-11 add the verifier behavior and before the
CSS correction in Step 13. The live verifier must fail on the current stretched
geometry rather than silently recording a passing summary.

- [ ] **Step 8: Register the new guarded evidence outputs**

Add these names to `evidenceOutputNames` in
`scripts/verify_roll_pallet_ui.mjs` so the existing preflight rejects symlinks
or non-regular files before browser/database activity:

```javascript
"one-pallet-print.pdf",
"one-pallet-back-page.png",
"two-pallet-print.pdf",
"two-pallet-back-page.png",
"print-pallet-overflow-last-page.png",
```

Do not weaken or bypass `assertEvidenceOutputLeaves()`.

- [ ] **Step 9: Add exact geometry and PDF-page helpers to the verifier**

Add these helpers beside the current print helpers:

```javascript
const GEOMETRY_TOLERANCE_PX = 0.5;

function assertNear(actual, expected, label) {
  assert(
    Math.abs(actual - expected) <= GEOMETRY_TOLERANCE_PX,
    `${label}: expected ${expected}px ± ${GEOMETRY_TOLERANCE_PX}px, found ${actual}px.`,
  );
}

function assertEveryHeight(heights, expected, label) {
  assert(heights.length > 0, `${label} has no rows.`);
  heights.forEach((height, index) => {
    assertNear(height, expected, `${label} row ${index + 1}`);
  });
}

function pdfPageCount(pdfPath) {
  const result = spawnSync("pdfinfo", [pdfPath], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  assert(
    result.status === 0,
    `Could not inspect ${pdfPath}: ${normalizeText(result.stderr)}`,
  );
  const match = result.stdout.match(/^Pages:\s+(\d+)$/m);
  assert(match, `pdfinfo did not report a page count for ${pdfPath}.`);
  return Number(match[1]);
}
```

Add a page-2 measurement helper that uses the real rendered print route:

```javascript
async function measurePageTwoTables(page, cardId) {
  await page.goto(`${baseURL}/cards/${cardId}/print`, {
    waitUntil: "networkidle",
  });
  await page.emulateMedia({ media: "print" });
  return await page.evaluate(() => {
    const geometry = (table) => {
      const tableBox = table.getBoundingClientRect();
      return {
        width: tableBox.width,
        headerHeights: Array.from(table.querySelectorAll("thead tr"), (row) =>
          row.getBoundingClientRect().height
        ),
        bodyHeights: Array.from(table.querySelectorAll("tbody tr"), (row) =>
          row.getBoundingClientRect().height
        ),
        columnWidths: Array.from(table.querySelectorAll("thead th"), (cell) =>
          cell.getBoundingClientRect().width
        ),
      };
    };
    const pallet = document.querySelector(
      ".print-page-back [data-pallet-summary-table='middle']",
    );
    const production = document.querySelector(
      ".print-page-back [data-summary-table='production']",
    );
    if (!pallet || !production) {
      throw new Error("Expected page-2 production and middle pallet tables.");
    }
    return {
      pageContainers: document.querySelectorAll(".print-page").length,
      pallet: geometry(pallet),
      production: geometry(production),
    };
  });
}
```

Keep floating-point measurements unrounded; the tolerance helper handles
renderer subpixels.

- [ ] **Step 10: Add one-, two-, and full-page-2 assertions and evidence**

At the start of `verifyPrints(page)`, after capacity calibration, measure:

```javascript
const onePallet = await measurePageTwoTables(
  page,
  fixture.cards.completed_one_pallet,
);
const twoPallets = await measurePageTwoTables(
  page,
  fixture.cards.completed_two_pallets,
);
const fullPageTwo = await measurePageTwoTables(
  page,
  fixture.cards.completed_mixed,
);
```

Use the full pallet block's first body row as the expected page-2 row height
and the one-pallet production table's first body row as the expected production
row height:

```javascript
const pageTwoRowHeight = fullPageTwo.pallet.bodyHeights[0];
const pageTwoHeaderHeight = fullPageTwo.pallet.headerHeights[0];
const productionRowHeight = onePallet.production.bodyHeights[0];

assertEqual(onePallet.pageContainers, 2, "one-pallet page containers");
assertEqual(twoPallets.pageContainers, 2, "two-pallet page containers");
assertEqual(onePallet.pallet.bodyHeights.length, 1, "one-pallet body row count");
assertEqual(twoPallets.pallet.bodyHeights.length, 2, "two-pallet body row count");

for (const [label, measured] of [
  ["one-pallet", onePallet],
  ["two-pallet", twoPallets],
  ["full page-2", fullPageTwo],
]) {
  assertEveryHeight(measured.pallet.headerHeights, pageTwoHeaderHeight, `${label} header`);
  assertEveryHeight(measured.pallet.bodyHeights, pageTwoRowHeight, `${label} pallet`);
  assertNear(measured.pallet.width, fullPageTwo.pallet.width, `${label} table width`);
  measured.pallet.columnWidths.forEach((width, index) => {
    assertNear(width, fullPageTwo.pallet.columnWidths[index], `${label} column ${index + 1}`);
  });
  assertEveryHeight(
    measured.production.bodyHeights,
    productionRowHeight,
    `${label} production`,
  );
}
```

Generate a PDF for each sparse card, assert exactly two pages, and rasterize
page 2:

```javascript
const sparseCases = [
  ["onePallet", fixture.cards.completed_one_pallet, "one-pallet"],
  ["twoPallets", fixture.cards.completed_two_pallets, "two-pallet"],
];
const sparsePdfPages = {};
for (const [key, cardId, artifactStem] of sparseCases) {
  await page.goto(`${baseURL}/cards/${cardId}/print`, { waitUntil: "networkidle" });
  await page.emulateMedia({ media: "print" });
  const pdfPath = path.join(artifactDir, `${artifactStem}-print.pdf`);
  await page.pdf({
    path: pdfPath,
    format: "A4",
    printBackground: true,
    margin: { top: "0", right: "0", bottom: "0", left: "0" },
  });
  recordArtifact(`${artifactStem}-print.pdf`);
  sparsePdfPages[key] = pdfPageCount(pdfPath);
  assertEqual(sparsePdfPages[key], 2, `${artifactStem} PDF page count`);
  pdfToPng(pdfPath, 2, `${artifactStem}-back-page.png`);
}
```

- [ ] **Step 11: Assert fixed geometry on every overflow page, including the sparse last page**

Extend the object returned by `inspectActualPrint()` so each overflow page also
reports table width, header-row heights, body-row heights, and column widths.
Inside its existing `page.evaluate()` callback, add:

```javascript
const tableGeometry = (table) => {
  const tableBox = table.getBoundingClientRect();
  return {
    width: tableBox.width,
    headerHeights: Array.from(table.querySelectorAll("thead tr"), (row) =>
      row.getBoundingClientRect().height
    ),
    bodyHeights: Array.from(table.querySelectorAll("tbody tr"), (row) =>
      row.getBoundingClientRect().height
    ),
    columnWidths: Array.from(table.querySelectorAll("thead th"), (cell) =>
      cell.getBoundingClientRect().width
    ),
  };
};

const overflowGeometry = overflowPages.map((printPage) => {
  const table = printPage.querySelector(
    "[data-pallet-summary-table='overflow']",
  );
  if (!table) {
    throw new Error("Expected an overflow pallet table on every overflow page.");
  }
  return tableGeometry(table);
});
```

Add `overflowGeometry` to the callback's returned object beside `overflow` and
`overflowPageCount`. After the existing overflow row-integrity checks, require:

```javascript
const firstOverflow = overflow.overflowGeometry[0];
const lastOverflow = overflow.overflowGeometry.at(-1);
const overflowRowHeight = firstOverflow.bodyHeights[0];
const overflowHeaderHeight = firstOverflow.headerHeights[0];

for (const [pageIndex, measured] of overflow.overflowGeometry.entries()) {
  assertEveryHeight(
    measured.headerHeights,
    overflowHeaderHeight,
    `overflow page ${pageIndex + 3} header`,
  );
  assertEveryHeight(
    measured.bodyHeights,
    overflowRowHeight,
    `overflow page ${pageIndex + 3} pallet`,
  );
  assertNear(measured.width, firstOverflow.width, `overflow page ${pageIndex + 3} width`);
  measured.columnWidths.forEach((width, index) => {
    assertNear(
      width,
      firstOverflow.columnWidths[index],
      `overflow page ${pageIndex + 3} column ${index + 1}`,
    );
  });
}

assertEqual(lastOverflow.bodyHeights.length, 1, "last overflow body row count");
const overflowPdfPages = pdfPageCount(overflowPdf);
assertEqual(overflowPdfPages, 5, "overflow PDF page count");
pdfToPng(
  overflowPdf,
  overflowPdfPages,
  "print-pallet-overflow-last-page.png",
);
```

Set the guarded result after every assertion passes:

```javascript
summary.print.fixedTableGeometry = {
  onePallet: {
    bodyRowCount: onePallet.pallet.bodyHeights.length,
    pdfPages: sparsePdfPages.onePallet,
  },
  twoPallets: {
    bodyRowCount: twoPallets.pallet.bodyHeights.length,
    pdfPages: sparsePdfPages.twoPallets,
  },
  overflow: {
    lastPageBodyRowCount: lastOverflow.bodyHeights.length,
    pdfPages: overflowPdfPages,
  },
  widthsStable: true,
  pageTwoRowsStable: true,
  productionRowsStable: true,
  overflowRowsStable: true,
};
```

The boolean fields are proof markers written only after their corresponding
assertions. Do not set them before the checks.

- [ ] **Step 12: Run syntax, fixture, and guarded live verification against the current CSS and observe the geometry failure**

Run:

```bash
node --check scripts/verify_roll_pallet_ui.mjs
.venv/bin/python -m pytest \
  tests/test_roll_pallet_ui_script_safety.py::test_roll_pallet_fixture_creates_only_the_six_required_card_kinds \
  -q
.venv/bin/python -m pytest \
  tests/test_roll_pallet_ui_script_safety.py::test_roll_pallet_verifier_completes_current_pencil_editor_workflow \
  -q
```

Expected: JavaScript syntax and fixture checks pass. The guarded live verifier
test fails on a sparse row-height comparison. The previously measured current
behavior is approximately `86.88px` for the one-pallet row versus `17.38px`
for a fixed page-2 row; the exact subpixel value may differ slightly.

- [ ] **Step 13: Implement the minimal CSS correction**

Add `align-items: start` inside the two existing rules in
`app/static/css/print.css`:

```css
.print-page-pallet-overflow {
  display: grid;
  grid-template-rows: auto 1fr;
  align-content: start;
  align-items: start;
  gap: 5mm;
  padding: 14mm 18mm 10mm;
}
```

```css
.print-summary {
  display: grid;
  grid-template-columns: 63mm 53.5mm 53.5mm;
  align-items: start;
  justify-content: space-between;
  gap: 2mm;
  width: 174mm;
  margin: 1.6mm auto 0;
  font-size: 7.6pt;
  line-height: 1.05;
}
```

Do not add explicit table heights, empty rows, JavaScript sizing, or changes to
the existing width/typography declarations.

- [ ] **Step 14: Run focused automated checks and confirm the correction passes**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_print_output.py \
  tests/test_roll_pallet_ui_script_safety.py \
  -q
node --check scripts/verify_roll_pallet_ui.mjs
```

Expected: all focused Python tests pass and Node syntax checking exits `0`.
The guarded verifier test proves the page-2 sparse rows, full-block production
rows, and last overflow row all retain their reference heights.

- [ ] **Step 15: Run the reusable browser verifier explicitly and inspect its evidence**

Create only ignored temporary/evidence directories:

```bash
mkdir -p \
  .test-runtime/fixed-pallet-print-table \
  artifacts/ui-checks/fixed-pallet-print-table
```

Create the guarded fixture:

```bash
.venv/bin/python scripts/create_roll_pallet_fixture.py \
  --db-path .test-runtime/fixed-pallet-print-table/fixture.sqlite3 \
  --output .test-runtime/fixed-pallet-print-table/fixture.json
```

Start the app in a separate terminal:

```bash
EXTRUSION_DB_PATH="$PWD/.test-runtime/fixed-pallet-print-table/fixture.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port 8018
```

Run the verifier from the repository root:

```bash
BASE_URL=http://127.0.0.1:8018 \
FIXTURE_JSON=.test-runtime/fixed-pallet-print-table/fixture.json \
ARTIFACT_DIR=artifacts/ui-checks/fixed-pallet-print-table \
  node scripts/verify_roll_pallet_ui.mjs
```

Expected:

- exit status `0`;
- `verification-summary.json` reports `status: passed`;
- measured capacities remain `back=8` and `overflow=48`;
- one- and two-pallet PDFs each contain exactly two A4 pages;
- the 97-row overflow PDF contains exactly five A4 pages;
- one-pallet page 2 shows one header plus one normal-height row;
- two-pallet page 2 shows one header plus two equal normal-height rows;
- the final overflow page shows one normal-height row beneath its header;
- table/column widths are equal within each established print context;
- the production-summary rows retain their sparse-case height beside a full
  pallet block; and
- no console or page errors are reported.

Open and inspect at least:

- `artifacts/ui-checks/fixed-pallet-print-table/one-pallet-back-page.png`;
- `artifacts/ui-checks/fixed-pallet-print-table/two-pallet-back-page.png`;
- `artifacts/ui-checks/fixed-pallet-print-table/print-pallet-back-page.png`; and
- `artifacts/ui-checks/fixed-pallet-print-table/print-pallet-overflow-last-page.png`.

Confirm there are no filler rows and blank page space begins immediately below
the final pallet row. Stop Uvicorn with `Ctrl+C` after verification.

- [ ] **Step 16: Review the completed code/test slice before documentation**

Run:

```bash
git diff -- \
  app/static/css/print.css \
  scripts/create_roll_pallet_fixture.py \
  scripts/verify_roll_pallet_ui.mjs \
  tests/test_print_output.py \
  tests/test_roll_pallet_ui_script_safety.py
git diff --check
git status --short
```

Review specifically that:

- only the two grid alignment declarations change application behavior;
- no width, font, border, page-break, capacity, or calculation changed;
- fixture paths remain guarded below `.test-runtime/`;
- artifact leaves remain guarded before any live request or reset;
- exact one/two/source row counts are asserted;
- the last overflow page is measured and captured, not only the first full
  overflow page; and
- every unrelated pre-existing working-tree change is intact.

Do not stage or commit.

---

### Task 2: Record The Contract, Assess Migration Impact, And Verify The Whole Repository

**Files:**
- Modify: `docs/implementation-notes/print-output-reference.md:256-285`
- Modify: `docs/implementation-notes/roll-pallet-assignment.md:105-118`
- Modify: `v2-files/AGENTS.md` migration assessment log

**Interfaces:**
- Consumes: the verified CSS behavior and `summary.print.fixedTableGeometry` evidence from Task 1.
- Produces: durable print-maintenance guidance and an explicit no-migration record for the completed display-only fix.

- [ ] **Step 1: Update the durable print-output contract**

In `docs/implementation-notes/print-output-reference.md`, add these requirements
to the back-page pallet-summary section immediately before the measured
capacities:

```markdown
- Every pallet block is a content-height table: one fixed-height header and one
  fixed-height row per rendered pallet. One or two pallets therefore render one
  or two data rows only; no filler row or table-cell stretching is permitted.
- Page-2 pallet tables, the adjacent production summary, and every overflow
  table are top-aligned independently. A short table leaves blank page space
  below it, and a taller table must not stretch a neighboring table.
- Table and column widths remain fixed within their established page-2 and
  overflow layouts and never depend on the number of pallet rows.
- A partially filled final overflow page repeats the identification and pallet
  headings, renders only its remaining fixed-height rows, and leaves the rest
  of the page blank.
```

Do not change the documented `8 + 8` / `48` capacities or aggregation rules.

- [ ] **Step 2: Update the pallet-assignment implementation note**

In `docs/implementation-notes/roll-pallet-assignment.md`, extend the print
section with:

```markdown
Pallet print tables use fixed physical widths and fixed header/data-row
heights. The CSS grid containers top-align each table so a sparse table ends
after its final row instead of distributing unused height into its cells. The
same rule applies to the production-summary peer and to partially filled final
overflow pages. Guarded Chromium/PDF verification covers one row, two rows,
full page-2 blocks, and a one-row final overflow page.
```

- [ ] **Step 3: Perform and record the V2 migration assessment**

Inspect the final implementation diff. Confirm it changes only print CSS,
temporary fixture/verifier code, tests, and documentation. Append one row to
the migration assessment log in `v2-files/AGENTS.md`:

```markdown
| 2026-07-31 | Fixed pallet print-table geometry | No migration | Top-aligned existing print-grid children and added sparse/full/overflow Chromium/PDF regression coverage plus documentation. No table, column, constraint, migration record, stored value, persisted meaning, pallet calculation, or historical data changed; no production snapshot is needed. |
```

Do not add a migration version and do not open a production database.

- [ ] **Step 4: Run syntax/import and focused verification**

Run:

```bash
.venv/bin/python -m compileall -q app scripts tests
node --check scripts/verify_roll_pallet_ui.mjs
.venv/bin/python -m pytest \
  tests/test_print_output.py \
  tests/test_roll_pallet_ui_script_safety.py \
  -q
```

Expected: every command exits `0`.

- [ ] **Step 5: Run the full Python suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: the complete suite passes using temporary databases and does not
touch `data/extrusion_terminal.sqlite3`.

- [ ] **Step 6: Re-run final diff and whitespace checks**

Run:

```bash
git diff --check
git diff -- \
  app/static/css/print.css \
  scripts/create_roll_pallet_fixture.py \
  scripts/verify_roll_pallet_ui.mjs \
  tests/test_print_output.py \
  tests/test_roll_pallet_ui_script_safety.py \
  docs/implementation-notes/print-output-reference.md \
  docs/implementation-notes/roll-pallet-assignment.md \
  v2-files/AGENTS.md
git status --short
```

Confirm the final slice remains within the approved print-only scope and the
unrelated working-tree changes listed in Global Constraints remain untouched.

- [ ] **Step 7: Prepare the review handoff without staging or committing**

Report:

- the two CSS declarations that prevent grid stretching;
- the one-, two-, full-, and final-overflow measured row heights;
- the stable page-2 and overflow table/column widths;
- the unchanged `8 + 8` / `48` capacities;
- the two-page sparse PDFs and five-page overflow PDF;
- focused and full-suite test counts;
- artifact paths for the four inspected screenshots and PDFs;
- the no-migration conclusion; and
- confirmation that no runtime/production database, unrelated file, staging
  area, or commit was changed.

Stop after the review handoff and wait for explicit user authorization before
staging or committing.
