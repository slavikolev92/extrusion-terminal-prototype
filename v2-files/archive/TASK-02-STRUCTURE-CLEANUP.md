# Task 02 — Shift Manager Structure Cleanup

This retained completion record documents the finished Shift Manager downstream
cleanup. Keep this file: the explicit instruction to retain it overrides its
former self-delete wording. It is not the master weekend plan.

**Goal:** Complete the July 25-26 application cleanup while preserving
production data. Production migration profiling and deployment rehearsal remain
separate later gates that require an immutable backup.

**Architecture:** Keep the strict final Shift Manager CSV contract, direct
SQLite/FastAPI architecture, and server-rendered UI. Implement each admin,
terminal, documentation, print, and production-tracking slice independently.
Use the ordered migration runner only when existing stored data or schema must
change.

**Tech Stack:** FastAPI, Jinja2, direct `sqlite3`, pytest with temporary
databases, repo-local Playwright, HTML/CSS print output.

## Global Constraints

- Follow repository-root `AGENTS.md` and `README.md`.
- Accept only the final exact 29-column CSV header in exact order.
- Do not restore old CSV compatibility or accept two formats.
- Do not add `micro_perforation`.
- `ordered_gross_kg` is the only target-gross source.
- `extrusion_sequence == "1"` is the only extrusion eligibility signal.
- Preserve production roll, timing, tare, status, assignment, queue, and actual
  material data.
- Keep optimistic version/conflict checks.
- Keep terminal cancellation, restoration, and printing absent.
- Use temporary databases for tests and production-snapshot copies for
  rehearsals.
- Do not stage or commit unless the user explicitly asks.
- Stop for review after every task.

## Current Checkpoint

- Completed: Tasks 1-6 and the entire Shift Manager downstream application
  cleanup: M001, admin and terminal cleanup, documentation, print contract,
  and full verification.
- Task 6 commands and results:

  ```bash
  .venv/bin/python -m compileall app scripts tests
  .venv/bin/python -m pytest -q
  git diff --check
  ```

  `compileall` and `git diff --check` passed; the full suite reported **485
  passed**.
- Live verification used only the fresh temporary database
  `.test-runtime/v2-final.roRhVV/extrusion_terminal.sqlite3`. The V14.04 CSV
  imported 3/3/3/0 (three rows seen, imported, and created; zero skipped), and
  orders 25450-25452 released to machine 1 in sequence positions 1-3.
- The live browser workflow covered admin import/planning/cards/detail, terminal
  production through completion, and an admin production correction. Admin
  print generated exactly two A4 pages. Screenshots and PDF evidence are under
  `artifacts/ui-checks/v2/final/`.
- No production database was opened or modified. M001 remains the only
  migration; no additional migration was introduced.
- Final adversarial review found no code issues. The resulting corrections were
  documentation-only.
- Tasks 7 and 8 remain later production-release gates once an immutable
  SQLite-safe backup is supplied; they are not incomplete application cleanup.
- Next feature workstream: explore the current app and database for the
  already-approved shift-management specification in
  `v2-files/TASK-01-SHIFT-MANAGEMENT.md`, then brainstorm and write its
  implementation plan. Do not modify that specification.
- Printing uses the four final ordered amounts in equal-width front cells and
  preserves the accepted two-page A4 output.
- Current Task 1 verification: 9 migration tests passed; 57 combined
  migration/baseline tests passed; compileall and `git diff --check` passed.
- Current Task 2 verification: 99 focused admin tests and 48 baseline tests
  passed; temporary SQLite database
  `.test-runtime/v2-admin.IInXK2/extrusion_terminal.sqlite3` was used; no new
  migration was introduced. Original evidence:
  `artifacts/ui-checks/v2/admin/import-result.png`,
  `artifacts/ui-checks/v2/admin/planning.png`,
  `artifacts/ui-checks/v2/admin/cards.png`, and
  `artifacts/ui-checks/v2/admin/card-detail.png`. Fully populated order-26000
  evidence: `artifacts/ui-checks/v2/admin/order-26000-import.png`,
  `artifacts/ui-checks/v2/admin/order-26000-planning.png`,
  `artifacts/ui-checks/v2/admin/order-26000-cards.png`, and
  `artifacts/ui-checks/v2/admin/order-26000-detail.png`; import was 1/1/1/0
  and all 29 values populated and matched. Human acceptance: the current
  planning table dimensions and gross/sequence/machine columns are acceptable.
- Current Task 3 verification: 102 focused terminal tests and 430 comprehensive
  non-print tests passed; `compileall` and `git diff --check` passed; the real
  runtime database was unchanged. Accepted 1280x720 evidence:
  `artifacts/ui-checks/v2/accepted/terminal-selected-card-1280x720.png`,
  `artifacts/ui-checks/v2/accepted/admin-card-detail-1280x720.png`,
  `artifacts/ui-checks/v2/accepted/admin-planning-1280x720.png`,
  `artifacts/ui-checks/v2/accepted/terminal-queue-drawer-1280x720.png`, and
  `artifacts/ui-checks/v2/accepted/terminal-produced-history-drawer-1280x720.png`.
  Final adversarial review: one Important terminal drawer-semantics finding was
  corrected; scoped re-review approved with 1 addressed, 0 open, and 0 new
  findings.
- Current Task 4 verification: 430 comprehensive non-print tests passed;
  `compileall`, the structured-sample UI script syntax check, and
  `git diff --check` passed. No application behavior or schema changed, no new
  migration was introduced, printing remained untouched, and the real runtime
  database was not opened or modified.
- Current Task 5 verification: 61 focused print/fixture/structured-sample tests
  passed; `compileall` and `git diff --check` passed. Order 25450 was verified
  through the real admin print link on the temporary database
  `.test-runtime/v2-admin.IInXK2/extrusion_terminal.sqlite3`: `500 кг`,
  `24 ролки`, `500 метра`, and `25000 бр.` rendered in four equal-width cells.
  The PDF contained exactly two A4 pages. Evidence:
  `artifacts/ui-checks/v2/print/order-25450/current-print-output.pdf`,
  `artifacts/ui-checks/v2/print/order-25450/current-print-output-1.png`, and
  `artifacts/ui-checks/v2/print/order-25450/current-print-output-2.png`. No new
  migration was introduced and the real runtime database was not used.
- Do not deploy the current chain by itself. Existing production cards retain
  legacy quantity/unit pairs until the required production profile determines
  whether a separate data migration is safe.

## Final Shift Manager Contract

The exact accepted header is:

```text
order_number,order_date,delivery_date,customer,city,product_type,ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units,product_form,material,size_thickness,notes,printing_sequence,extrusion_sequence,rewinding_slitting_sequence,confection_sequence,extrusion_next_operation,extrusion_folding,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
```

Verified source files:

- workbook: `source-files/Production Orders (Marco) V14.04.xlsm`;
- CSV: `source-files/extrusion_orders_20260725_110012.csv`.

Verified integration evidence before this plan:

- exact CSV header matched;
- 3 rows seen, 3 imported, 3 created, 0 skipped;
- orders 25450-25452 released to machine 1 at sequences 1-3;
- mapped workbook fields matched CSV rows 5401-5403;
- `/terminal/cards/1` and `/admin/cards/1` returned 200;
- non-print suite passed 389 tests;
- full suite had 419 passes and 47 print-related failures because printing was
  intentionally not updated.

## Accepted Display And Print Decisions

Admin:

- Import results stay compact and link successful rows to the current card.
- Planning shows ordered gross kilograms for drafts and active queues.
- Cards index shows delivery date and ordered gross kilograms.
- Card detail edits all four ordered amounts. The four route-sequence values
  remain imported, stored, and preserved but are intentionally hidden because
  they are not actionable there.
- Use the workbook label `Фалдиране`.

Terminal:

- Machine tiles show actual produced gross against `ordered_gross_kg`.
- Active queue rows show compact ordered gross kilograms only.
- Produced rows show actual produced gross, never requested quantities.
- Selected detail uses the accepted five-plus-four layout: company, ordered
  gross, product type, size/thickness, and folding on row one; product form,
  next operation, treatment, and packaging on row two.
- Selected detail does not show ordered rolls, ordered meters, ordered units,
  delivery date, material, or maximum roll weight.
- At 1280x720, the recipe through `Креда` must remain visible.
- Do not add terminal print, cancel, or restore controls.

Print:

- Preserve the accepted two-page A4 structure.
- Front quantity cells are ordered gross kilograms, rolls, meters, and units.
- When populated, the reference display is
  `500 кг | 20 ролки | 15000 метра | 40000 бр`.
- Blank values remain blank; units are determined by field meaning.
- Do not print route sequences, machine assignment, queue position, status, or
  maximum roll weight.
- Preserve back-page roll, timing, gross, tare, and net behavior.

## Task Status

| Task | State | Next gate |
| --- | --- | --- |
| 1. Migration runner and M001 | Complete | Production profile remains required |
| 2. Admin visibility | Complete | Task 3 terminal semantics/layout |
| 3. Terminal semantics/layout | Complete | Task 4 current docs/non-print tests |
| 4. Current docs/non-print tests | Complete | Task 5 print contract |
| 5. Print contract | Complete | Task 6 full verification/dev reset |
| 6. Full verification/dev reset | Complete | Later production-release gates only |
| 7. Production legacy-data profile | Waiting | Immutable production backup |
| 8. Release-candidate rehearsal | Waiting | Complete approved migration chain |

---

### Task 1: Migration Runner And Schema-Only M001

**Status:** Complete.

**Files:** `app/migrations.py`, `app/db.py`, and `tests/test_migrations.py`.

Implemented behavior:

- `schema_migrations(version, name, applied_at)` records ordered migrations.
- `apply_pending_migrations(connection) -> tuple[int, ...]` requires an active
  caller transaction and uses a savepoint.
- Registry errors, unknown versions, name mismatches, and non-prefix histories
  fail safely.
- M001 adds the eight final ordered/route columns to `cards` and
  `card_import_sources`.
- M001 does not transform legacy quantity/unit fields or `extrusion_flag`.
- Existing final values and all production data remain unchanged.
- Failed schema/data work and its record roll back together.

Evidence:

```bash
.venv/bin/python -m pytest tests/test_migrations.py -q
# 9 passed

.venv/bin/python -m pytest tests/test_migrations.py tests/test_baseline.py -q
# 57 passed

.venv/bin/python -m compileall app tests
git diff --check
# passed
```

Migration decision: schema migration required and implemented as M001. Legacy
data conversion is intentionally deferred pending the Task 7 production profile.

---

### Task 2: Admin Visibility

**Status:** Complete.

**Files:** `app/db.py`, `app/main.py`, `app/templates/admin_import.html`,
`app/templates/admin_planning.html`, `app/templates/admin_cards.html`,
`app/templates/admin_card_detail.html`, `tests/test_admin_routes.py`,
`tests/test_admin_planning.py`, `tests/test_admin_card_review.py`, and
`tests/test_admin_card_detail_redesign.py`.

- [ ] Add failing tests proving successful import rows link to the current card,
  planning shows `Поръчано бруто, кг`, cards index shows delivery and gross, and
  detail renders/saves all four ordered values while preserving hidden route
  sequences.
- [ ] Assert `Фалдиране` and absence of old import-field, route-sequence, and
  maximum-roll input names.
- [ ] Extend only required query/view models; do not copy all 29 fields into list
  tables or duplicate imported snapshots in `import_batch_rows`.
- [ ] Update the four admin templates with compact overview values.
- [ ] Run:

  ```bash
  .venv/bin/python -m pytest tests/test_admin_routes.py tests/test_admin_planning.py tests/test_admin_card_review.py tests/test_admin_card_detail_redesign.py -q
  git diff --check
  ```

- [ ] Review data integrity and messages, update this checkpoint, and stop. Run
  the database migration system workflow when the user invokes its trigger.

---

### Task 3: Terminal Semantics And 1280x720 Layout

**Status:** Complete.

**Files:** `app/main.py`, `app/templates/terminal.html`,
`tests/test_terminal_v8_render.py`, `tests/test_terminal_detail.py`, and
untracked `artifacts/ui-checks/v2/terminal/`.

- [ ] Add failing tests for target gross on machine tiles, compact requested
  gross in queue rows, actual gross in produced rows, the accepted selected-card
  detail fields, `Фалдиране`, and absence of terminal cancel/restore/print
  controls.
- [ ] Split requested-gross and produced-gross display helpers by meaning.
- [ ] Compact selected details to the accepted five-plus-four field set while
  keeping all other imported values stored and available to admin/backend use.
- [ ] Run:

  ```bash
  .venv/bin/python -m pytest tests/test_terminal_v8_render.py tests/test_terminal_detail.py tests/test_terminal_sync.py -q
  ```

- [ ] Start FastAPI with a temporary database and capture 1280x720 Playwright
  evidence for selected detail through `Креда`, active queue, and produced drawer.
- [ ] Run `git diff --check`, update this checkpoint, and stop. Run the database
  migration system workflow when the user invokes its trigger.

---

### Task 4: Current Documentation And Non-Print Tests

**Status:** Complete.

**Files:** `README.md`, current implementation notes, and affected non-print
tests.

- [ ] Record V14.04, the final 29 fields, route sequence rules,
  `ordered_gross_kg` target behavior, admin-only printing, and migration process
  in authoritative/current documentation.
- [ ] Mark superseded implementation notes clearly; keep dated historical plans
  historical.
- [ ] Classify every remaining old-field match as migration code, rejection
  coverage, print work reserved for Task 5, or historical documentation:

  ```bash
  rg -n "quantity_1|unit_1|quantity_2|unit_2|extrusion_flag" app tests scripts README.md docs v2-files
  ```

- [ ] Run:

  ```bash
  .venv/bin/python -m pytest --ignore=tests/test_print_output.py --ignore=tests/test_print_template_fixture_script.py -q
  git diff --check
  ```

- [ ] Update this checkpoint and stop. Run the database migration system
  workflow when the user invokes its trigger.

---

### Task 5: Print Contract

**Status:** Complete.

**Files:** `app/printing.py`, `app/templates/print_card.html`, optional
`app/static/css/print.css`, `scripts/create_print_template_fixture.py`,
`tests/test_print_output.py`, `tests/test_print_template_fixture_script.py`,
`docs/implementation-notes/print-output-reference.md`, and untracked
`artifacts/ui-checks/v2/print/`.

- [x] Convert fixtures to the final contract with
  `extrusion_sequence="1"` and the four ordered values.
- [x] Add tests for the four fixed-meaning cells, blank optional cells,
  absence of old keys/unit cells, and absence of route sequences.
- [x] Map final stored text to four print view-model values without parsing or
  recalculating source amounts.
- [x] Preserve print readiness, 120 roll slots, summaries, and two-page output.
- [x] Run focused print tests.
- [x] Render two-page A4 PDF and page images; inspect quantity cells, front/back
  landmarks, roll positions, totals, and exact page count.
- [x] Run `git diff --check`, update this checkpoint, and stop. Run the database
  migration system workflow when the user invokes its trigger.

---

### Task 6: Full Verification And Disposable Development Reset

**Status:** Complete.

- [x] Run the complete static and automated checks:

  ```bash
  .venv/bin/python -m compileall app scripts tests
  .venv/bin/python -m pytest -q
  git diff --check
  ```

  Result: `compileall` and `git diff --check` passed; `pytest -q` reported 485
  passed.

- [x] Initialize and use only the fresh temporary database
  `.test-runtime/v2-final.roRhVV/extrusion_terminal.sqlite3`; confirm machines
  1-4 and M001. No production database was opened or reset.
- [x] Import `source-files/extrusion_orders_20260725_110012.csv`: 3 rows seen,
  3 imported, 3 created, 0 skipped; release orders 25450-25452 to machine 1 in
  positions 1-3.
- [x] Smoke-test admin import/planning/cards/detail, terminal
  tiles/queue/detail, production entry/history, and admin correction.
- [x] Verify admin print as exactly two A4 pages. Evidence, including
  screenshots and PDF, is under `artifacts/ui-checks/v2/final/`.
- [x] Complete adversarial review: no code findings; documentation corrections
  only.

---

### Task 7: Production Legacy-Data Profile

**Status:** Later production-release gate. Waiting for an immutable SQLite-safe
production backup.

- [ ] Fingerprint the immutable backup: timestamp, deployed revision, size,
  SHA-256, integrity result, migration versions, and high-level counts.
- [ ] Clone it under an ignored temporary path; query only the copy.
- [ ] Record production invariants and profile quantity/unit pairs in both
  `cards` and `card_import_sources` without recording customer-level rows in git.
- [ ] Count existing final values, card/source disagreements, unit spellings,
  unitless quantities, quantity-less units, and ambiguous mappings.
- [ ] Run the database migration system workflow to recommend whether a separate
  unit-aware migration is required. Do not guess or register a version before
  rules are approved.
- [ ] Persist the count-based profile through that workflow, update this
  checkpoint, and stop.

---

### Task 8: Release-Candidate Rehearsal And Runbook

**Status:** Later production-release gate. Waiting for the complete approved
migration chain and a fresh immutable production backup.

- [ ] Fingerprint the fresh immutable backup and clone it for rehearsal.
- [ ] Capture pre-migration status, queue, roll, gross/net, tare, timing, material,
  foreign-key, import-source, and approved mapping totals.
- [ ] Run the full chain on the copy; record versions, duration, logs, integrity,
  and exit status.
- [ ] Compare invariants and require exactly the approved transformations, no
  ambiguous changes, no duplicate queues, and no foreign-key violations.
- [ ] Smoke-test health, admin import/planning/detail, terminal cards, and
  completed-card printing against the migrated copy.
- [ ] Write measured maintenance commands: stop app, make final SQLite-safe
  backup, migrate, validate, restart, and smoke-test.
- [ ] Define rollback as restoring the final pre-migration backup and previous
  application revision.
- [ ] Persist rehearsal evidence through the database migration system workflow,
  update this checkpoint, and stop. Never touch production without explicit
  maintenance approval.

## Definition Of Done For Every Task

- Required behavior is covered by tests that failed before implementation.
- Focused tests pass with observed counts.
- Relevant regression tests pass.
- UI work has live Playwright evidence.
- `git diff --check` passes.
- Changed code is reviewed for data integrity and user-visible failures.
- If the user invokes “maintain the database migration system,” that workflow is
  completed and its assessment is recorded.
- This file states the completed task and exact next action.
- No runtime or production database was accidentally touched.
- Nothing is staged or committed without explicit user approval.
