# Interim Costing Process Plan

Status: working planning document.

Last updated: 2026-06-23.

This is the single planning file for the interim product-costing process. It
records approved decisions, open decisions, and remaining tasks for the
shift-manager workbook, the production actuals app, and the costing process that
uses both sources.

## 1. Project Definition

### Purpose

The purpose of this project is to calculate interim product/order profitability
before the full ERP rollout is complete.

The profitability object is the production order/item, not a calendar month.

The process is forward-looking. It is intended to collect clean costing data for
new production orders, not to reconstruct historical unit costs from old
workbook rows.

The process should answer:

- what product/order was produced
- which operations were performed
- how much usable output each relevant operation produced
- how much time each operation took
- which recipe should be applied for extrusion material consumption
- what agreed sales price should be used
- what estimated material, operation, and allocated indirect costs belong to the
  product/order

### Scope And Boundaries

In scope:

- Clean forward-looking recipe convention for extrusion.
- Clean forward-looking sales price convention.
- Simple production actuals app with workbook import of expected operations.
- CSV export, and XLSX export if needed.
- Production-order-level export for costing.
- Manual or semi-manual daily completeness checks.
- Monthly allocation of untracked smaller consumables and indirect costs.

Out of scope for this interim costing process:

- Recovering historical costing data from old workbook rows.
- Full ERP implementation.
- Invoice/shipping-document integration.
- Inventory reservation or stock control.
- User roles, approvals, or permission workflows.
- Complex downtime/performance analytics.
- Exact per-order ink/solvent measurement.
- Exact extrusion waste tracking, unless added later.

Accepted simplification:

- Extrusion waste remains out of scope.
- Initial extrusion material basis is extrusion net produced kg.
- Material cost may be understated where extrusion waste exists.

### Overall Process

The interim costing process uses three practical parts:

1. Shift-manager workbook
   - Holds planned/specification data.
   - Holds production order number, operations, recipe, product context, and
     agreed sales price.
2. Production actuals app
   - Holds actual information transcribed from completed paper operational
     cards.
   - Stores one row per completed operational card/operation actual.
   - Exports a production-order-level summary for costing.
3. Costing layer
   - Joins shift-manager workbook data, production actuals, raw material prices,
     and monthly allocation inputs.
   - Calculates material consumption, operation cost allocation, revenue, and
     estimated margin.

Planning order:

1. Define the costing methodology.
2. Define the data required by that methodology.
3. Inspect what required data already exists in the shift-manager workbook.
4. Decide what workbook conventions or fields must change.
5. Identify the remaining data gaps.
6. Design the production actuals app last, after the workbook/data gaps are
   known.

## 2. Shift-Manager Workbook

### Role

The shift-manager workbook remains the canonical source for production-order
planning and specification data.

It owns:

- production order number
- customer/product/order context
- planned operation flags
- extrusion recipe fields
- agreed sales price

The workbook should not become the repository for completed operation actuals.
Those actuals belong in the production actuals app.

### Database Field Index

The current shift-manager `Database` worksheets have been classified for the
interim costing process. The classifications below are final for this planning
stage unless the user explicitly reopens a field after new evidence appears.

Classification meanings:

- `Required as-is`: usable workbook input without a convention change.
- `Required after convention`: workbook input needed for costing, but only after
  the forward-looking entry convention is adopted.
- `Import for navigation`: useful context for shift-manager screens, not a
  costing calculation input.
- `Ignore for costing`: preserve existing workbook use, but do not use for
  costing.
- `App-captured`: required information is not reliable in the workbook and must
  be captured in the production actuals app.

| Column | Existing meaning | Classification | Interim costing treatment |
| --- | --- | --- | --- |
| `A` | Production order number | Required as-is | Required join key between the workbook, expected operation slots, actuals, and final produced item. |
| `B` | Workbook/order date | Import for navigation | Planning/admin date only. Use for list context if helpful; costing completion dates come from app actuals. |
| `C` | Delivery date | Import for navigation | Planning/admin date only. Use for list context if helpful. |
| `D` | Customer | Import for navigation | Useful for list/search context. Not a costing calculation input. |
| `E` | City | Ignore for costing | Customer/admin context only. |
| `F` | Legacy product/type free text | Import for navigation | Useful for list/search context. Do not use as preferred final-product identity because it is dirty and unstructured. |
| `G:J` | Ordered quantities and units | Ignore for costing | Usage is not reliable enough across files. Actual output quantities come from app actuals. |
| `K` | Type of blank/preparation | Ignore for costing | Descriptive production/spec field only for the current method. |
| `L` | Legacy material | Ignore for costing | Descriptive/spec field only. Costing material identity comes from recipe/material convention. |
| `M` | Size/thickness | Ignore for costing | Descriptive/spec field only. Final product identity should come from a forward-looking nomenclature if practical. |
| `N` | Notes | Ignore for costing | Free text, not parseable costing data. |
| `O` | Sales price | Required after confirmation | Must use the approved numeric-only convention if shift managers confirm it is workable. |
| `P` | Payment terms | Ignore for costing | Sales/admin context only. |
| `Q` | Produced quantity / `Изработено количество` | Ignore for costing | Shift-manager-owned free text. Do not change meaning, format, or workflow. Actuals come from the app. |
| `R:T` | Invoice, contact, delivery fields | Ignore for costing | Admin/logistics context only. |
| `U` | Cliche payment | Ignore for costing | Not part of current per-order production costing unless direct tooling/cliche allocation is explicitly added later. |
| `V` | Flexo printing flag | Required as-is | `Да` means printing actuals are expected. |
| `W` | Extrusion flag | Required as-is | `Да` means extrusion actuals are expected. |
| `X` | Rewinding/slitting flag | Required as-is | `Да` means rewinding/slitting actuals are expected. |
| `Y` | Confection flag | Required as-is | `Да` means confection actuals are expected. |
| `Z` | Printing next operation | Ignore for costing | Workflow/spec context only. |
| `AA` | Printing cylinder size | Ignore for costing | Printing spec context only; not a current costing input. |
| `AB:AI` | Printing ink station slots 1-8 | Required after convention | Must use `Color Identity | Anilox lines/cm`. Ink/color identity supports ink allocation; anilox is preserved for later refinement. |
| `AJ:AL` | Extrusion/workflow-adjacent fields | Ignore for costing | Workflow/spec context only. |
| `AM:AP` | Base polymer recipe slots | Required after convention | Must use `Material Name | %`; all non-empty `AM:AS` percentages share one final-product recipe pool and must sum to `100%`. |
| `AQ:AS` | Additive/filler recipe slots | Required after convention | Must use `Material Name | %`; additives/fillers are part of the same final-product `100%` recipe pool, not percentages over a base blend. |

No existing `Database` column is classified as `App-captured`. App-captured data
is identified in the later workbook/app gap-fit step.

### Workbook-Owned Costing Inputs

The shift-manager workbook owns the following data for the interim costing
process:

- `A`: production order number.
  - Production order numbers are treated as unique across the current
    shift-manager files.
  - `source_workbook` should still be retained by the import process for
    provenance and review.
- `V:Y`: expected operation flags.
- `O`: agreed sales price, if the numeric EUR/kg excluding-VAT convention is
  confirmed by shift managers.
- `AB:AI`: printing ink/color and anilox values after the new convention is
  adopted.
- `AM:AS`: extrusion recipe material names and percentages after the new
  convention is adopted.

The workbook can also provide navigation context for the app:

- `B:C`: workbook/order and delivery dates.
- `D`: customer.
- `F`: legacy product/type free text.

### Workbook-Ignored Fields

The following workbook fields are not costing inputs for this interim process:

- `E`, `G:N`, `P:U`, `Z:AA`, and `AJ:AL`.
- These fields should remain available for the shift managers' existing
  workbook workflow where they are useful.
- The interim costing process should not change their meaning, format, or
  workflow.
- `Q` specifically remains shift-manager-owned free text and must not be used as
  authoritative production actuals.
- Required production actuals must come from the production actuals app.

### Workbook Analysis Conclusion

For the interim costing process, the shift-manager workbook can provide the
production-order key, expected operations, agreed sales price after
confirmation, recipe data after convention changes, printing ink/color data
after convention changes, and navigation context for the app.

The workbook cannot provide reliable production actuals, reliable output
quantities, or a reliable final-product/material identity from legacy free-text
fields alone. The app must import expected operations from the workbook and
capture operational-card actuals against those expected slots.

### Planned Operation Flags

- `V`: flexo printing.
- `W`: extrusion.
- `X`: rewinding/slitting.
- `Y`: confection.
- These fields are the canonical planned-operation source for app expected
  operation slots and completeness checks.
- A `Да` value means the operation is expected and actuals are required.
- The `Технологични Карти` worksheet formulas are also gated by these flags. If
  the relevant `Database!V:Y` flag is not `Да`, the corresponding
  operation-card block does not populate.

### Required Convention Changes

The workbook needs three forward-looking conventions:

1. Recipe material cells must use a parseable material-and-percentage format.
2. Sales price must use a parseable normalized format.
3. Printing ink station cells must split ink identity from anilox value.

These changes are required because the costing layer must be able to calculate
material consumption, revenue, cost per unit, and margin from the workbook and
actuals export.

The workbook printing convention is needed because current ink station entries
mix inconsistent ink/color names with anilox values in free text.

### Recipe Rules

Use existing extrusion material columns in the `Database` worksheet.

| Column | Existing meaning | Costing role |
| --- | --- | --- |
| `AM` | Raw material A | Base polymer |
| `AN` | Raw material B | Base polymer |
| `AO` | Raw material C | Base polymer |
| `AP` | Linear PE | Base polymer |
| `AQ` | Antistatic | Additive/filler slot in final-product recipe pool |
| `AR` | Masterbatch | Additive/filler slot in final-product recipe pool |
| `AS` | Chalk | Additive/filler slot in final-product recipe pool |

Column identity defines the costing role. Do not add `BASE` or `ADD` markers to
the cell text.

Each costable material cell should use the approved raw-material item naming
rule:

```text
[Material Category] [Producer or Brand] [Full Commercial Grade/Code] | [%]
```

For PE raw materials, `Material Category` means the polymer family such as
`LDPE`, `LLDPE`, `MDPE`, or `reLDPE`.

For additives, `Material Category` means the additive family such as
`Antistatic`, `Masterbatch`, `Filler`, `Processing Aid`, or another accepted
additive category.

Approved ERP item identity rule:

- For normal PE raw materials and extrusion additives, the ERP item identity is
  defined by material/additive family, producer or brand, and full commercial
  grade/code.
- Melt-flow index, density, processing temperatures, food-contact status,
  additive package, technical datasheets, and certificate values are item or lot
  specification fields, not normal item-name components.
- Recycled/regranulate, off-spec, non-prime, or trader-blended materials may
  need a separate naming rule if they do not have a stable producer grade/spec.

Examples:

```text
LDPE Rompetrol Midilena B20/03 | 60%
LDPE SABIC 2100N0W | 40%
LLDPE SABIC 119ZJ | 20%
Antistatic Novachem AT 04673 LD | 2%
Masterbatch Polibach White 8000 ET | 3%
```

Parsing rule:

- The percentage after the final `|` is the recipe percentage.
- This allows material names to become longer without breaking the format.

Recipe rule:

- Base polymers are normally entered in `AM:AP`.
- Additives and fillers are normally entered in `AQ:AS`.
- All non-empty recipe cells in `AM:AS` share one final-product recipe pool.
- Parsed recipe percentages across `AM:AS` must sum to exactly `100%`.
- There is no separate "base polymers sum to `100%`, then additives/fillers are
  added over the base" interpretation for the July 2026 interim costing
  process.

### Sales Price Rules

The workbook already has a sales price field in `Database` column `O`, labelled
`Цена`.

Approved direction:

- No sales linkage ledger is needed for this interim costing process.
- Shift managers should enter the agreed sales price at production-order
  creation time.
- Revenue and cost must be normalized to a common unit before margin is
  calculated.

Working assumption to verify:

- Column `O` should contain only the numeric agreed sales price.
- The value should mean EUR per kg of item, excluding VAT.
- Currency does not need to be entered if all sales prices are in EUR.
- Unit does not need to be entered if the canonical sales price unit is always
  per kg.
- The column label/process should make the implicit meaning clear.

Shift-manager confirmation needed:

- Shift managers must confirm whether this numeric EUR/kg excluding-VAT
  convention is acceptable and implementable for forward-looking tracked
  production orders.
- No alternate unit or alternate sales-price convention is approved at this
  planning stage.

### Printing Ink Rules

Use existing printing ink station columns in the `Database` worksheet.

| Column range | Existing meaning | Costing role |
| --- | --- | --- |
| `AB:AI` | Printing ink station slots 1-8 | Ink/color presence and anilox value |

Current workbook values such as `W/110`, `Y/255`, `P 485/110`, `W 110`, and
`Black 255` are legacy free-text ink station entries.

Resolved interpretation:

- The letter/name/code is the ink or color identity.
- The trailing number is the anilox roller specification in lines/cm.
- The anilox value controls ink transfer volume.
- The anilox value should be preserved separately because it may support more
  precise ink allocation later.

Each filled printing ink station cell should use:

```text
[Color Identity] | [Anilox lines/cm]
```

Examples:

```text
White | 110
Yellow | 220
Yellow | 240
Magenta | 255
Cyan | 255
Black | 110
Pantone 485 | 110
Gold 871 | 110
Reflex Blue | 110
```

Parsing rule:

- The text before the final `|` is the ink/color identity.
- The text after the final `|` is the anilox value.
- Initial monthly ink allocation should use the ink/color identity.
- The anilox value should be kept for later allocation refinement but is not
  required for the initial allocation method.
- For the interim prototype/workbook, the color identity is an accepted
  color/color-standard name. Manufacturer and invoice product code are not part
  of the workbook-facing color identity.
- ERP ink-item identity remains open. It depends on whether equivalent colors
  from different manufacturers are interchangeable in practice.

Solvents:

- Solvent consumption remains monthly allocated.
- Solvents are not expected to be tied to a specific printed order/card in this
  interim process.

### Workbook Validation Rules

Recipe validation:

- Material cells used for costing must contain a final `|` delimiter.
- The text after the final `|` must contain one numeric percentage.
- Percentages across all non-empty recipe cells in `AM:AS` must sum to exactly
  `100%`.
- Additive/filler columns `AQ:AS` may be blank or may contain valid
  final-product percentages.
- Bag-count formulas such as `1.5 kg/bag`, `1 bag`, or similar shorthand are
  not valid for costing unless converted to percentages first.
- Free-text material names without percentages are not valid for costing.

Sales price validation:

- If the numeric-only convention is approved, price must contain one numeric
  value.
- The value is interpreted as EUR/kg excluding VAT.
- Non-numeric, unit-labelled, VAT-labelled, or mixed price entries are not valid
  under the approved direction.

Planning/spec validation:

- Production order number must exist.
- Planned operation flags should be clear enough to support the daily
  completeness check against actuals.

Printing ink validation:

- Filled ink station cells in `AB:AI` should contain a final `|` delimiter.
- The text before the final `|` must contain an accepted color identity.
- The text after the final `|` must contain one anilox value.
- Blank ink station cells are allowed.

### Questions For Shift Managers

Sales price:

- Do shift managers approve using column `O` as one numeric value that always
  means EUR/kg, excluding VAT, for forward-looking tracked production orders?

Naming conventions:

- Do shift managers approve the proposed naming conventions, and are they easy
  enough to use consistently?
  - Extrusion raw materials/additives:
    `[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code]`
  - Recipe cells: `Material Name | %`
  - Printing ink station fields: `Color Identity | Anilox lines/cm`
  - Polypropylene film:
    `[Film Type] [Product Series] [Thickness] [Width mm]`
- What is the preferred way to help shift managers use the new names and
  formats: month-start raw-material/additive inventory list, workbook dropdowns,
  separate reference sheet/document, workbook verification macro, app-side
  validation on workbook upload, or some combination?
- Are equivalent colors from different ink suppliers/manufacturers
  interchangeable in production, so manufacturer can be excluded from the
  workbook-facing color identity?

Extrusion recipe structure:

- Do real extrusion recipes fit within four base polymer slots `AM:AP` and three
  additive/filler slots `AQ:AS`?
- Is the current final-product interpretation clear and workable: all non-empty
  recipe percentages across `AM:AS`, including additives/fillers, sum to exactly
  `100%`?
- Do shift managers need a reference table or calculator to convert current
  shorthand such as ratios, bag counts, or `20% KJ` into percentages?

Solvents:

- How is solvent usage currently captured, if at all?
- If solvent usage is not captured per order/card, should solvent cost be
  allocated monthly?

### Workbook Open Decisions

- Whether the raw-material/additive reference list should be implemented as
  workbook dropdowns, a separate reference sheet, or a separate document for the
  interim month-start process.
- Final approved ink/color naming catalog, prepared from legacy workbook values
  and invoice/expense ink names and then verified with shift managers.
- Final approved final-product/item nomenclature. This is a deferred user-owned
  decision, not a shift-manager question for the current workbook step.
- Whether sales price can use the numeric-only EUR/kg excluding-VAT convention.
- Final solvent monthly allocation naming/grouping:
  - whether generic `СОЛВЕНТ` and `Солвент` invoice rows map to
    `Solvent SOL115A0000`;
  - whether `Methoxypropanol` and `Ethyl acetate` are separate monthly
    allocation buckets or merged into a broader solvent bucket;
  - whether solvents remain separate from inks in month-end reporting or are
    grouped into one printing-consumables allocation line;
  - whether any additional solvent names exist outside the inspected invoice
    workbook.
- Where workbook-side validation should run: Excel, macro, separate checker, or
  costing tool.
- Exact starting production order number for the July 2026 import cutoff in each
  shift-manager file. This is an internal tracking setup item, not a
  shift-manager question.

### Workbook Tasks

1. Use the questions in this plan to collect shift-manager answers.
2. Prepare the starting raw-material/additive inventory reference list for the
   beginning of the tracked month, using the approved naming convention.
3. Decide whether the raw-material/additive reference list is provided as
   workbook dropdowns, a separate workbook/reference sheet, or a document.
4. Define the simple update process for adding newly received stock to the
   controlled raw-material/additive list during the month.
5. Confirm the sales price convention for column `O`.
6. Confirm shift-manager approval and usability of the raw-material/additive,
   recipe-cell, ink/color, and PP film naming conventions.
7. Confirm the preferred support method for using the new names and formats:
   reference list, dropdowns, separate document, workbook macro, app-side upload
   validation, or a combination.
8. Confirm whether current recipes fit within `AM:AS`.
9. Confirm whether the final-product percentage interpretation across `AM:AS`
   matches the way shift managers currently build extrusion recipes.
10. Confirm whether shift managers need a reference table or calculator to
   convert current shorthand into percentages.
11. Confirm whether equivalent colors from different ink suppliers are
   interchangeable in production.
12. Confirm how solvent usage is captured today, if at all, and whether monthly
   allocation is required.
13. After June 30, record the July 2026 starting production order numbers for
   each shift-manager file.
14. Decide where workbook validation will run: Excel, macro, separate checker,
   or costing/import tool.
15. Update the shift-manager process so recipe cells follow `Material | %`.
16. Update the shift-manager process so price follows the approved column `O`
   convention.
17. Update the shift-manager process so printing ink station cells follow
    `Color Identity | Anilox lines/cm`.
18. At month end, map the actual material names used in the shift-manager files
    to the costing/invoice file and actual cost per kg.

## 3. Production Actuals App

### Role

The production actuals app is a structured digital repository for information
currently present on paper operational cards.

Approved app boundaries:

- It should import expected production orders and operations from the
  shift-manager workbook.
- It should verify actuals entry against imported expected operation slots.
- It does not create ERP-like parent production orders.
- It stores operational-card actual rows.
- The production order number is the required grouping and join key for linking
  operation actuals back to the shift-manager workbook row and final produced
  item.
- Multiple operation actuals may share the same production order number.
- The app design should be finalized only after the costing methodology,
  workbook data review, and workbook gap analysis are complete.

### Workbook Import And Expected Operations

The app should include a simple shift-manager workbook import before actuals
entry.

Import purpose:

- Read tracked production order rows from the shift-manager workbook.
- Create expected operation slots from `Database!V:Y`.
- Use those expected slots to structure actuals entry and completeness review.
- Keep useful descriptive fields such as customer, relevant workbook dates, and
  legacy product/type text for list navigation and shift-manager review.

Tracking range:

- The initial pilot import should ignore historical workbook noise.
- Tracking should begin from the first production order numbers created on or
  after July 1, 2026.
- The exact starting production order number for each shift-manager file should
  be set after the June 30, 2026 cutoff is known.

Import behavior:

- The import should be an upsert, not a destructive reload.
- Re-importing the workbook may add new production orders, update descriptive
  planned/spec fields, and propose newly expected operation slots.
- Newly added or modified expected operations should be shown for review before
  they affect the active work queue.
- Nothing should be silently deleted.
- If a re-import removes or changes an expected operation that already has
  actuals, the app should flag it for review rather than deleting or overwriting
  the actuals.

Expected operation rules:

- A `Да` value in `V:Y` means that operation is expected and actuals are
  required.
- Actuals entry should be allowed only for imported expected operation slots.
- If an operation was missed in the workbook, the shift manager should update
  and re-import the workbook before entering that operation's actuals.
- A production order should not be considered complete until all expected
  operation slots have completed actuals.

### Operation Types

Approved operation types:

```text
extrusion
printing
rewinding_slitting
confection
```

Rewinding and slitting are treated as one operation because this operation is
less significant for the interim costing process.

### Data Model

Recommended internal storage shape:

```text
imported_production_orders
- id
- production_order_number
- source_workbook
- workbook_row
- customer
- workbook_date
- delivery_date
- legacy_product_type
- created_at
- updated_at

expected_operation_slots
- id
- production_order_number
- operation
- status
- created_from_import_id
- created_at
- updated_at

operation_actuals
- id
- expected_operation_slot_id
- production_order_number
- operation
- actual_card_number
- start_datetime
- stop_datetime
- total_minutes
- gross_kg
- tare_count
- tare_weight_kg
- net_kg
- waste_kg
- pp_film_material
- pp_film_quantity_kg
- total_unit_count
- produces_final_item
- finished_item_id
- voided_at
- void_reason
- notes
- created_at
- updated_at
```

Start and stop values must be full datetimes, not clock-only times. The
operational-card completion date/month is derived from `stop_datetime`.

Tare fields are generic internally. The interface can label them by operation:
for roll operations, `tare_count` and `tare_weight_kg` mean roll count and core
weight; for confection, they mean container count and container weight.

The final schema may keep unused operation-specific fields nullable rather than
creating one table per operation. The export can pivot the rows into separate
operation columns by production order.

Duplicate and split work direction:

- Do not allow arbitrary operation actuals that are not tied to an imported
  expected operation slot.
- Do not strictly block multiple actual rows against the same expected operation
  slot.
- Warn if actuals already exist for the same production order and operation.
- Allow saving against the expected slot because split work, corrections,
  partial production, or reruns may happen in reality.
- Each saved actual row represents one physical operational card actual.
- Assign a visible sequential `actual_card_number` per production order and
  operation, for example `1`, `2`, `3`.
- If an actual already exists for the same production order and operation, the
  app must show a clear warning before saving another row.
- Saving an additional row should require an explicit confirmation such as
  `Save as additional operational card`.
- The UI should support an optional reason/note for additional rows, such as
  split production, shortfall correction, rework, or duplicate correction.
- Mistaken duplicate actuals should be voided, not physically deleted, so the
  audit trail remains inspectable.
- Voided actuals must be excluded from costing/export summations, while
  remaining visible for review.
- The exact voiding UI, required/optional void reason, and correction workflow
  details still need final design before implementation.

Finished-output direction:

- An operation actual may be marked as producing a final item.
- Use a field such as `produces_final_item`, not a vague "last operation"
  marker, because the costing event is that this operational card yielded the
  finished product/item.
- When `produces_final_item` is true, the app should require a structured
  finished-item identity.
- Finished-item identity should use controlled fields and numeric dimension
  inputs instead of free text, similar in spirit to the workbook recipe builder.
- The dirty legacy workbook product/type text should not become the finished
  item identity.
- Customer should remain separate from item identity unless the later
  nomenclature design explicitly decides that a product is customer-specific.
- The exact finished-item nomenclature fields are deferred until the user
  provides the intended structure from the separate nomenclature work.

### Fields By Operation

This is settled for the current planning stage.

Settled extrusion fields:

- `production_order_number`
- `operation = extrusion`
- `start_datetime`
- `stop_datetime`
- `gross_kg`
- `tare_count` / roll count
- `tare_weight_kg` / core weight
- `net_kg`
- `total_minutes`
- optional `waste_kg`

Extrusion calculated fields:

- `total_minutes = stop_datetime - start_datetime`
- `net_kg = gross_kg - (tare_count * tare_weight_kg)`

Extrusion authoritative costing fields:

- `total_minutes`
- `net_kg`

Extrusion override rules:

- Start and stop datetimes are always saved.
- `stop_datetime` determines the operational-card completion date/month.
- If `total_minutes` is manually entered or changed, it overrides the
  calculated time for costing.
- If `net_kg` is manually entered or changed, it overrides the calculated net kg
  for costing.
- If `waste_kg` is present, extrusion recipe material basis is
  `net_kg + waste_kg`.
- If `waste_kg` is absent, waste is treated as zero and extrusion recipe
  material basis is `net_kg`.

Settled printing fields:

- `production_order_number`
- `operation = printing`
- `start_datetime`
- `stop_datetime`
- `gross_kg`
- `tare_count` / roll count
- `tare_weight_kg` / core weight
- `net_kg`
- `total_minutes`
- optional `pp_film_material`
- optional `pp_film_quantity_kg`

Printing calculated fields:

- `total_minutes = stop_datetime - start_datetime`
- `net_kg = gross_kg - (tare_count * tare_weight_kg)`

Printing authoritative costing fields:

- `total_minutes`
- `net_kg`

Printing override rules:

- Start and stop datetimes are always saved.
- `stop_datetime` determines the operational-card completion date/month.
- If `total_minutes` is manually entered or changed, it overrides the
  calculated time for costing.
- If `net_kg` is manually entered or changed, it overrides the calculated net kg
  for costing.

PP film input direction:

- PP film input fields are used for CPP/BOPP film consumed in non-extrusion
  operations.
- The app should capture PP film material/name and PP film quantity in kg when
  PP film is consumed.
- CPP/BOPP purchased-film material/name should use the approved controlled-list
  convention:
  `[Film Type] [Product Series] [Thickness] [Width mm]`, for example
  `BOPP FXC 30 960mm` or `CPP PLCBZ 28 1040mm`.
- Do not include the micron symbol in the PP film item name.
- The product series remains in the name because `FXC`, `PLCB`, and `PLCBZ` are
  formal Plastchim-T product types.
- The inspected invoice workbook currently yields 40 distinct purchased PP film
  identities after normalizing obvious wording variants and excluding
  transport/correction rows.
- PP film fields are optional at entry because the shift-manager workbook can be
  used later to validate which production orders are PP orders.

Settled rewinding/slitting fields:

- `production_order_number`
- `operation = rewinding_slitting`
- `start_datetime`
- `stop_datetime`
- `gross_kg`
- `tare_count` / roll count
- `tare_weight_kg` / core weight
- `net_kg`
- `total_minutes`
- optional `pp_film_material`
- optional `pp_film_quantity_kg`

Rewinding/slitting calculated fields:

- `total_minutes = stop_datetime - start_datetime`
- `net_kg = gross_kg - (tare_count * tare_weight_kg)`

Rewinding/slitting authoritative costing fields:

- `total_minutes`
- `net_kg`

Rewinding/slitting override rules:

- Start and stop datetimes are always saved.
- `stop_datetime` determines the operational-card completion date/month.
- If `total_minutes` is manually entered or changed, it overrides the
  calculated time for costing.
- If `net_kg` is manually entered or changed, it overrides the calculated net kg
  for costing.
- No rewinding/slitting-specific fields are needed.

Settled confection fields:

- `production_order_number`
- `operation = confection`
- `start_datetime`
- `stop_datetime`
- `gross_kg`
- `tare_count` / container count
- `tare_weight_kg` / container weight
- `net_kg`
- `total_minutes`
- `total_unit_count`
- optional `pp_film_material`
- optional `pp_film_quantity_kg`

Confection calculated fields:

- `total_minutes = stop_datetime - start_datetime`
- `net_kg = gross_kg - (tare_count * tare_weight_kg)`

Confection authoritative costing/reporting fields:

- `total_minutes`
- `net_kg`
- `total_unit_count`

Confection override rules:

- Start and stop datetimes are always saved.
- `stop_datetime` determines the operational-card completion date/month.
- If `total_minutes` is manually entered or changed, it overrides the
  calculated time for costing.
- If `net_kg` is manually entered or changed, it overrides the calculated net kg
  for costing.

### App Validation Rules

General validation:

- Production order number is required.
- Operation type is required.
- The production order and operation must match an imported expected operation
  slot.
- Required fields depend on operation type.
- Numeric fields must be numeric and non-negative where applicable.
- Start and stop values must be full datetimes.
- Stop datetime cannot be before start datetime.
- Total minutes is the authoritative time field for costing.
- Existing actual rows for the same expected operation slot should trigger a
  warning, not a hard block.

Extrusion validation:

- Start datetime and stop datetime are required.
- Gross kg, tare count, tare weight, net kg, and total minutes are
  required.
- Waste kg is optional and must be non-negative if entered.
- The app should calculate total minutes from start and stop datetime by
  default.
- Manual total minutes overrides calculated total minutes for costing.
- The app should calculate net kg from gross kg, tare count, and tare
  weight by default.
- Manual net kg overrides calculated net kg for costing.

Printing validation:

- Start datetime and stop datetime are required.
- Gross kg, tare count, tare weight, net kg, and total minutes are
  required.
- The app should calculate total minutes from start and stop datetime by
  default.
- Manual total minutes overrides calculated total minutes for costing.
- The app should calculate net kg from gross kg, tare count, and tare
  weight by default.
- Manual net kg overrides calculated net kg for costing.
- PP film material and PP film quantity kg are optional at entry.
- If PP film material is entered, PP film quantity kg is required.
- If PP film quantity kg is entered, PP film material is required.
- PP film quantity kg must be non-negative if entered.

Rewinding/slitting validation:

- Start datetime and stop datetime are required.
- Gross kg, tare count, tare weight, net kg, and total minutes are
  required.
- The app should calculate total minutes from start and stop datetime by
  default.
- Manual total minutes overrides calculated total minutes for costing.
- The app should calculate net kg from gross kg, tare count, and tare
  weight by default.
- Manual net kg overrides calculated net kg for costing.
- PP film material and PP film quantity kg are optional at entry.
- If PP film material is entered, PP film quantity kg is required.
- If PP film quantity kg is entered, PP film material is required.
- PP film quantity kg must be non-negative if entered.

Confection validation:

- Start datetime and stop datetime are required.
- Gross kg, tare count, tare weight, net kg, total minutes, and total unit count
  are required.
- The app should calculate total minutes from start and stop datetime by
  default.
- Manual total minutes overrides calculated total minutes for costing.
- The app should calculate net kg from gross kg, tare count, and tare weight by
  default.
- Manual net kg overrides calculated net kg for costing.
- PP film material and PP film quantity kg are optional at entry.
- If PP film material is entered, PP film quantity kg is required.
- If PP film quantity kg is entered, PP film material is required.
- PP film quantity kg must be non-negative if entered.
- Total unit count must be non-negative.

Export readiness validation:

- Rows missing required fields should be visible before export or clearly marked
  in the export.
- After joining app data with the shift-manager workbook, PP orders should be
  checked for missing PP film consumption in the relevant non-extrusion
  operation.

### App Export

Approved export purpose:

- Input and storage are operational-card-level.
- Export is production-order-level.
- The export should give the costing layer one row per production order.
- Operation data must remain separated by operation because operation cost rates
  can differ.

Provisional export shape:

```text
production_order_number
extrusion_total_minutes
extrusion_net_kg
extrusion_gross_kg
extrusion_tare_count
extrusion_tare_weight_kg
printing_total_minutes
printing_net_kg
printing_gross_kg
printing_tare_count
printing_tare_weight_kg
printing_pp_film_material
printing_pp_film_quantity_kg
rewinding_slitting_total_minutes
rewinding_slitting_net_kg
rewinding_slitting_gross_kg
rewinding_slitting_tare_count
rewinding_slitting_tare_weight_kg
rewinding_slitting_pp_film_material
rewinding_slitting_pp_film_quantity_kg
confection_total_minutes
confection_net_kg
confection_gross_kg
confection_tare_count
confection_tare_weight_kg
confection_total_unit_count
confection_pp_film_material
confection_pp_film_quantity_kg
```

This export shape is still provisional until the final costing/export design is
approved, but the required fields by operation are settled for the current
planning stage.

If multiple actual rows exist for the same expected operation slot, export
should exclude voided rows and sum active numeric values where summing is
meaningful:

```text
total_minutes = sum
net_kg = sum
gross_kg = sum where relevant
tare_count = sum where relevant
total_unit_count = sum where relevant
```

No combined all-operation total time is required for costing. Each operation's
minutes stay separate.

### App Open Decisions

- Whether any additional non-costing operational notes should be captured.
- Exact correction/voiding workflow details for mistaken duplicate entries,
  including whether a void reason is required.
- Structured finished-item nomenclature fields required when an actual row
  produces the final item.
- Exact export column list.
- Whether export must be CSV only at first or CSV plus XLSX.
- Whether the app should be separate or a clearly separated module beside the
  existing FastAPI/SQLite pilot.

### App Tasks

1. Complete the blocking workbook/data investigations.
2. Define the workbook import and expected-operation review workflow.
3. Translate the settled operation fields and validation rules into the app
   schema and interface.
4. Define correction/voiding behavior.
5. Define the structured finished-item nomenclature fields required when
   `produces_final_item` is true.
6. Define the exact export columns.
7. Define the minimum app screens.
8. Define backup/export/recovery requirements.
9. Decide implementation location.

## 4. Costing Layer And Operating Process

### Costing Inputs

Inputs:

- shift-manager workbook production-order data
- normalized recipe fields
- normalized sales price
- production actuals app export
- raw material price table, maintained separately
- expenses file / cost pools, maintained separately
- monthly consumable and indirect-cost totals

### Costing Rules

Costing components:

- Direct/raw material costs.
- Indirect or allocated expenses.

Direct/raw material costs:

- Extrusion direct materials are polyethylene pellets and additives.
- Printing direct materials are inks and solvents.
- Rewinding/slitting has no direct raw materials for this costing process.
- Confection has no direct raw materials for this costing process.
- Smaller consumables are not tracked per order/card and are allocated monthly.

Recipe percentage normalization:

```text
material kg = output basis * recipe percent / 100
```

Example:

```text
AM LDPE Rompetrol Midilena B20/03 | 77%
AP LLDPE SABIC 119ZJ | 18%
AQ Antistatic Novachem AT 04673 LD | 2%
AR Masterbatch Polibach White 8000 ET | 3%
```

Total recipe percentage:

```text
77% + 18% + 2% + 3% = 100%
```

If output basis is `1000 kg`, consumption is:

```text
LDPE        = 1000 * 77 / 100 = 770 kg
LLDPE       = 1000 * 18 / 100 = 180 kg
Antistatic  = 1000 * 2 / 100  = 20 kg
Masterbatch = 1000 * 3 / 100  = 30 kg
```

Initial output basis:

```text
extrusion material basis = extrusion net produced kg
```

If waste is added later:

```text
extrusion material basis = extrusion net produced kg + extrusion waste kg
```

Operation costing:

- Operation minutes stay separate by operation.
- Each operation may have a different cost-per-minute rate.
- No combined all-operation time is required for costing.
- Each operational card is costed using the cost rates and allocation rates from
  the month in which that operational card was completed.
- All operational-card costs roll up to the production order/item.
- A production order/item may contain operation costs from multiple months.

Indirect and allocated expenses:

- Examples include electricity, utilities, personnel expenses, and machine
  expenses.
- Cost pools/categories must come from the separately maintained expenses file.
- Operation-specific personnel and machine costs are expected to be allocated by
  operation time, unless later analysis shows a better basis.
- Some production expenses may need kg-based allocation.
- General and administrative expenses should be shown separately from
  manufacturing margin at first.
- A fully loaded margin including general and administrative expenses is still
  desired, but the allocation method remains open.

Monthly allocation:

- Small or difficult-to-track consumables do not need production-order-level
  tracking in this interim costing process.
- Monthly totals can be allocated using simple bases.
- Inks and solvents can be allocated to printed orders using that color,
  initially by printed kg or another simple agreed basis.
- Monthly ink and solvent consumption should be determined by inventory
  reconciliation: starting quantity plus additions minus ending quantity.
- Ink allocation should use the ink/color identity from the workbook printing
  ink station convention.
- Solvent consumption remains monthly allocated and is not expected to be tied
  to a specific printed order/card in this interim process.
- Smaller consumables can be allocated by kg or operation minutes.
- Indirect expenses can be allocated by operation minutes, machine minutes, kg,
  or another monthly basis to be defined.

Revenue and margin:

- Revenue comes from workbook sales price and comparable output quantity.
- Cost and revenue must be normalized to comparable units before margin is
  calculated.
- Estimated margin is calculated per production order/product.
- Sales date is not relevant for this interim costing process because the
  agreed sales price comes from the shift-manager workbook.

Monthly cost-rate periods:

- The interim costing process does not calculate monthly profitability.
- Months are used to establish cost rates, material prices, and allocation rates.
- Each operational card uses the rates from its own completion month.
- The final production-order/item margin can combine rates from multiple months.
- Extrusion material cost uses recipe-derived consumption and the extrusion
  material price for the operational-card completion month.
- Printing inks and solvents use monthly allocation because reliable per-card
  consumption data is not currently available.

### Daily Control Process

The biggest risk is consistency, not software complexity.

Required operating discipline:

- Shift managers import the current workbook to create or update expected
  operation slots.
- Shift managers enter actuals from completed paper operational cards against
  those expected slots.
- A daily or every-few-days review compares expected operation slots against
  completed actual rows in the app.
- Missing actuals are followed up by finding the paper operational card and
  entering the data.
- Validation should make missing or malformed fields obvious.

Completeness should be visible in the app from the imported expected operation
slots. A production order remains open until all expected operations have
completed actuals.

### Month-End Process

Expected month-end flow:

1. Export or collect shift-manager workbook data.
2. Export production actuals summary from the app.
3. Join both sources by production order number.
4. Add raw material price table.
5. Add monthly consumable and indirect-cost totals.
6. Establish monthly material prices, cost-per-minute rates, consumable
   allocation rates, and indirect-cost allocation rates.
7. Calculate extrusion material consumption and material cost using the
   operational-card completion month.
8. Calculate operation time cost by operation using the operational-card
   completion month.
9. Allocate monthly consumables and indirect expenses.
10. Calculate revenue from normalized sales price.
11. Calculate estimated margin per production order/product.

### Costing And Process Open Decisions

- Final allocation bases for inks, solvents, smaller consumables, and indirect
  expenses.
- How to mark a production order as ready for final margin calculation once all
  required operational-card actuals exist.
- What cost pools/categories exist in the expenses file.
- Which cost pools should be allocated by operation time vs kg.
- How general and administrative expenses should be handled for fully loaded
  margin.
- Which output basis is needed per operation.
- Final month-end output report format.
- How strict completeness must be before month close.
- Whether the costing layer will be Excel, Python, SQLite, Power Query, or
  another simple tool.

### Costing And Process Tasks

1. Define the costing methodology.
2. Define the data required by the methodology.
3. Map required data to the shift-manager workbook and production actuals app.
4. Identify workbook changes before finalizing app design.
5. Define monthly allocation bases.
6. Define month-end costing output columns.
7. Define completeness review checklist.
8. Decide the first costing calculation tool.
9. Define the month-close routine.
