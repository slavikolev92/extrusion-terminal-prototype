# Milestone 9 Bundle 2 Handoff - Admin Card Detail Redesign

You are continuing work on the extrusion terminal pilot repository at:

`C:\Users\slavi\Dropbox (Personal)\03 KolevOOD\7 Extrusion Terminal Prototype`

The immediate task is a correction pass on **Milestone 9 Bundle 2: Admin Card Index And Full Card Detail/Review**.

The current Bundle 2 implementation is functionally present but the user rejected the admin card detail page structure. The correction must happen before starting Milestone 9 Bundle 3.

## Communication Constraint

Keep user-facing updates short. The user explicitly objected to long answers. Use concise status updates and concise final summaries.

Use 30-second or lower timeouts for normal checks unless there is a clear reason otherwise. Do not spend time trying repeated local server/browser launches if they become flaky. Prefer automated checks and direct file/template review unless the user asks for a manual browser run.

## Required First Reads

Read these files before editing:

1. `AGENTS.md`
2. `README.md`
3. `IMPLEMENTATION_PLAN.md`
4. `prompts/milestone-9-bundle-2-admin-card-review.md`
5. this handoff prompt

Then inspect these implementation files:

- `app/main.py`
- `app/db.py`
- `app/constants.py`
- `app/rules.py`
- `app/importer.py`
- `app/templates/admin_cards.html`
- `app/templates/admin_card_detail.html`
- `app/templates/terminal.html`
- `app/templates/_admin_nav.html`
- `app/static/css/app.css`
- `tests/test_admin_card_review.py`
- `tests/test_admin_routes.py`

Then inspect the prototype:

- `ui-prototypes/workstation-v4.html`

Use `workstation-v4.html` as the primary UI structure reference. Older prototype files exist, but V4 is the current target unless the user says otherwise.

## Current Working Tree Context

There are intentional pre-existing/unrelated housekeeping changes in the working tree. Do not revert them:

- `.gitignore` modified
- `IMPLEMENTATION_HANDOFF.md` deleted
- top-level `excel-macros/` deleted/moved
- `source-files/README.md` modified
- `source-files/excel-macros/` untracked
- `prompts/` untracked
- `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` untracked

There are also uncommitted Bundle 2 changes from the current session. Treat them as intentional and build on them:

- `app/templates/admin_cards.html` added
- `app/templates/admin_card_detail.html` added
- `tests/test_admin_card_review.py` added
- `app/db.py`, `app/main.py`, `app/constants.py`, `app/rules.py`, `app/static/css/app.css`, `_admin_nav.html`, `tests/test_admin_routes.py`, and `IMPLEMENTATION_PLAN.md` modified

Do not run destructive git commands. Do not revert user/housekeeping changes.

## Current Functional State

Bundle 2 currently has:

- `/admin/cards`
  - card index
  - filters by order number, customer, product, status
  - text filters are case-insensitive
  - date filters and date columns were removed from the index
  - includes all current statuses except removed `draft`

- `/admin/cards/{card_id}`
  - current page exists but is badly structured
  - currently renders imported fields as a raw loop in CSV/database order
  - currently uses English/internal labels
  - currently has a separate "Machine-side material" box
  - user rejected this layout

- `/admin/cards/{card_id}/imported-fields`
  - saves imported/front-card field corrections
  - uses loaded `version` conflict checks
  - blocks stale saves
  - blocks duplicate order number
  - blocks no-extrusion-causing edits
  - safe order-number edits update related `roll_entries.order_number`
  - preserves production-side data

- `/admin/cards/{card_id}/delete`
  - deletes only unreleased `imported` cards
  - blocks delete after release
  - blocks delete if production data exists

- `draft` status was removed
  - current valid statuses should be: `imported`, `pending`, `running`, `paused`, `completed`, `cancelled`

Recent checks passed before this handoff:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

At that point pytest collected `69` tests and all passed.

## User Feedback To Treat As Requirements

The user rejected the current admin card detail page because:

- it is not structured like the operational card
- it is just raw CSV/database fields in a grid
- fields like `Unit 1`, `Quantity 2`, and `Unit 2` are meaningless as standalone UI
- visible labels must be Bulgarian
- the page must align with the prototype
- the separate `Machine-side material` section is wrong
- actual material/brand/batch belongs in the same material/recipe area, not a random separate panel
- low-level workflow metadata should not dominate the page

The user approved making a handoff first. Do not proceed with implementation unless this prompt is used as the next-session execution instruction.

## Prototype Structure To Follow

`ui-prototypes/workstation-v4.html` structures the working card roughly as:

1. Header / topbar
   - order number
   - elapsed/production time
   - action buttons

2. `Карта`
   - `Вид изделие`
   - `Фирма`
   - `Количество`
   - `Размер/дебелина`
   - `Вид заготовка`
   - `Материал`
   - notes below

3. `Рецепта`
   Table columns:
   - `Позиция`
   - `Вид суровина`
   - `Марка №`
   - `Партиден №`

   Rows:
   - `A`
   - `B`
   - `C`
   - `Линеен`
   - `Антистатик`
   - `Мастербач`
   - `Креда`

4. `Произведено количество`
   - `Бруто общо`
   - `Нето общо`
   - `Прогрес` if useful and safely computable

5. `Ролки`
   - `Шпула` / tare
   - roll gross weights

For the admin detail page, do not copy terminal action controls. This page is for shift-manager review/correction, not kiosk operation. But the information structure and labels should follow the prototype.

## Recommended Fix

Rebuild `app/templates/admin_card_detail.html` from raw-field loop into explicit grouped sections.

### Section 1: Card Header

Use Bulgarian labels:

- title: `Поръчка № {{ card.order_number }}`
- status pill with Bulgarian status label
- machine/sequence shown compactly: `Машина {{ card.machine_id }} / ред {{ card.machine_sequence }}`
- version/update metadata should be small/secondary

Do not make workflow metadata the first large card on the page.

### Section 2: `Карта`

Show/edit imported front-card fields in operational-card grouping:

- `№ поръчка` -> `order_number`
- `Дата` -> `order_date`
- `Срок` or `Дата доставка` -> `delivery_date`
- `Фирма` -> `customer`
- `Град` -> `city`
- `Вид изделие` -> `product_type`
- `Количество` -> combine `quantity_1 + unit_1`, and if `quantity_2/unit_2` exist show them as a second quantity line/value, not standalone random fields
- `Вид заготовка` -> `product_form`
- `Материал` -> `material`
- `Размер/дебелина` -> `size_thickness`
- `Забележки` -> `notes`

Implementation options:

- simplest: keep the same POST endpoint and field names, but arrange fields manually with Bulgarian labels
- quantity fields can be shown in a grouped mini-grid under one `Количество` heading while still saving `quantity_1`, `unit_1`, `quantity_2`, `unit_2`
- do not show `Unit 1`, `Quantity 2`, `Unit 2` as top-level labels

### Section 3: `Екструзия`

Show/edit extrusion operation fields with Bulgarian labels:

- `Екструзия` -> `extrusion_flag`
- `Фалцоване` -> `extrusion_folding`
- `Следваща операция` -> `extrusion_next_operation`
- `Третиране` -> `extrusion_treatment`
- `Опаковка` -> `packaging_method`

This section can be a small grid.

### Section 4: `Рецепта`

Replace the current separate raw material/additive fields with a table based on the prototype.

Rows and planned/imported field mapping:

| Row label | Planned/imported field |
| --- | --- |
| `A` | `raw_material_a` |
| `B` | `raw_material_b` |
| `C` | `raw_material_c` |
| `Линеен` | `linear_pe` |
| `Антистатик` | `antistatic` |
| `Мастербач` | `masterbatch` |
| `Креда` | `chalk` |

Columns:

- `Позиция`
- `Вид суровина`
- `Марка №`
- `Партиден №`

Important data-model caveat:

- The current DB has only one set of terminal material fields:
  - `actual_raw_material_used`
  - `raw_material_brand_grade`
  - `raw_material_batch_lot`
- It does **not** yet have per-row brand/batch columns for A/B/C/additives.
- Do not invent a large schema migration in this cleanup unless absolutely necessary and explicitly justified.
- For now, display the imported planned material/additive values in the `Вид суровина` column.
- If showing terminal-entered actual brand/batch, place the existing values in the recipe table in a restrained way, likely on row `A` only, with a small note if needed. Do not keep the separate `Machine-side material` box.
- If this mapping feels too misleading, do not show brand/batch in the admin detail until Bundle 4 production-side correction. In that case, keep the columns visually but blank/disabled/read-only, or add a small secondary note. Prefer clarity over pretending the schema supports per-row actual material data.

### Section 5: `Произведено количество`

Show read-only production totals:

- `Бруто общо`
- `Нето общо`
- optionally `Ролки`

Use current computed fields:

- `card.total_gross_weight`
- `card.total_net_weight`
- `card.roll_count`

Progress is optional. If used, do not create fake precision. It could be based on `quantity_1` only if numeric parsing is reliable. If not reliable, omit progress.

### Section 6: `Ролки`

Read-only for this cleanup:

- `Шпула` -> `tare_weight`
- roll table:
  - `№`
  - `Бруто тегло, кг`
  - `Нето тегло, кг`

Admin editing rolls is Bundle 4, not this cleanup.

### Section 7: `Време`

Read-only for this cleanup:

- total duration
- first started
- finished
- cancelled
- timing segments if present

Admin timing correction is Bundle 4, not this cleanup.

### Section 8: System/Admin Metadata

Move low-level metadata to the bottom or a visually secondary section:

- validation status
- import batch
- version
- created/updated timestamps

This should not dominate the first screen.

## Backend Shaping Helpers

It is acceptable to add small helper data shaping in `app/main.py` or `app/db.py`, for example:

- `status_labels`
- `validation_labels`
- `quantity_display` or grouped quantity context
- `recipe_rows`

Prefer simple explicit Python dictionaries/lists over abstraction.

Do not change the DB schema unless the cleanup cannot be done correctly without it. The likely correct move is **template/context restructuring only**.

## Keep Existing Backend Rules

Do not break:

- version conflict checks
- safe order-number edit
- no-extrusion edit blocking
- duplicate order-number blocking
- preservation of production data
- release rules
- safe delete of unreleased imported cards only
- case-insensitive card index filters
- removal of `draft`
- removal of order/delivery date filters and columns from `/admin/cards`

## Tests To Add/Update

Existing tests are backend-heavy. Add targeted tests only where useful.

Recommended:

- test admin detail context includes `recipe_rows` if you add a context helper
- test quantity grouping helper combines `quantity_1/unit_1` and `quantity_2/unit_2` without losing values
- test route registration remains unchanged
- existing preservation/edit tests should continue passing

Do not add browser dependencies.

## CSS/UI Notes

Reuse the current app stylesheet, but it is acceptable to add admin-specific classes inspired by the prototype:

- card/work area grid
- info grid
- recipe table
- production metric boxes
- secondary metadata section

Keep visual style consistent with the existing app:

- simple server-rendered HTML
- compact, work-focused
- no marketing layout
- no decorative graphics
- no nested cards

## Explicit Non-Scope

Do not implement in this correction:

- Bundle 3 reassignment/resequencing
- admin-side production correction
- admin roll editing
- admin timing editing
- print output
- login/users/permissions
- large schema redesign
- terminal UI full rewrite, unless a tiny label/partial reuse is necessary and clearly justified

## Verification Commands

Run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m compileall app tests
.\.test-runtime\codex-venv\Scripts\python.exe -m pytest
git diff --check
```

Use explicit timeouts if running through tools. If a local manual server check is attempted and it fails once due to process/browser issues, stop and report that manual UI check was not completed. Do not keep retrying.

## Final Response Expectations

Keep final answer short:

- what changed
- tests passed
- what the user should inspect

Do not provide long explanatory essays unless asked.
