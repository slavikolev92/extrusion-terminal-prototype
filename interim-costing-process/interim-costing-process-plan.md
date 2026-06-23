# Interim Costing Process Plan

Status: working planning document.

Last updated: 2026-06-22.

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
- Simple production actuals ledger app.
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

### Existing Relevant Fields

Important workbook fields for the interim costing process:

- `A`: production order number
- `D`: customer
- `F`: product/type
- `G:J`: ordered quantities and units
- `L`: material
- `M`: size/thickness
- `O`: price
- `V:Y`: planned operation flags
- `Z`: printing next operation
- `AA`: printing cylinder size
- `AB:AI`: printing ink station slots 1-8
- `AM:AS`: extrusion recipe/costing material fields

Production-order key:

- `A` / production order number is the required join key between the
  shift-manager workbook and the production actuals app.
- The shift-manager process and paper operational cards are centered on this
  number, so the app must use it to reference the production order.
- Multiple operational-card actual rows may link to the same production order
  number, one per completed operation card or split/rerun card.
- Production order numbers are treated as unique across the current
  shift-manager files.

Customer and legacy product fields:

- `D` is the customer field.
- `F` is the existing legacy product/type free-text field.
- These fields are production-order-level descriptive fields and can be pulled
  from the workbook if needed.
- They are not required costing calculation inputs for the current planning
  stage.
- Do not rely on `F` as the preferred final-product identity because it is
  dirty and unstructured.
- A forward-looking final-product nomenclature is preferred if practical.

Legacy ordered quantity fields:

- `G:J` are existing ordered quantity and unit fields.
- Do not use `G:J` as costing inputs because the current shift-manager usage is
  not reliable enough across files.
- Required costing quantity fields should be separate from these legacy workbook
  fields.
- Actual output quantities for costing come from the production actuals app.

Legacy material and size fields:

- `L` / material and `M` / size-thickness are existing descriptive/spec fields.
- Do not use `L:M` as authoritative costing inputs.
- Required costing material identity should come from the forward-looking
  recipe/material convention, not from these legacy descriptive fields.
- Final product identity should be handled through a forward-looking product
  nomenclature if practical, not inferred from legacy descriptive text.

Other legacy/admin fields:

- Treat `B:C`, `E`, `K`, `N`, `P`, `R:T`, `U`, `Z:AA`, and `AJ:AL` as
  legacy/admin/workflow/spec fields, not costing inputs.
- Workbook dates in `B:C` are planning/admin dates. Costing completion dates
  must come from operational-card actuals.
- `E` city, `P` payment terms, and `R:T` invoice/contact/delivery fields are
  customer/admin/logistics context only.
- `K`, `N`, `Z:AA`, and `AJ:AL` may describe production/spec workflow, but they
  do not drive the current costing method.
- `U` cliché payment is not part of the current per-order production costing
  inputs unless direct tooling/cliché allocation is explicitly added later.
- The later full field index may promote one of these fields only if it has a
  concrete, repeatable costing use.

Workbook field-index direction:

- Create an index of all fields in the current `Database` worksheets from the
  shift-manager files before finalizing workbook ownership and app gaps.
- For each field, classify whether it is usable as-is, usable only after a
  forward-looking convention change, shift-manager-owned/ignored for costing, or
  unavailable in the workbook and therefore app-captured.
- The purpose is to extract as much useful planned/specification data from the
  existing workbook as practical without changing fields that shift managers use
  for their own workflow.

Excluded workbook fields:

- `Q` / `Изработено количество` remains shift-manager-owned free text.
- Do not change its meaning, format, or workflow for the interim costing
  process.
- Do not use `Q` as an authoritative source for costing actuals.
- Required production actuals must come from the production actuals app.

Planned operation flags:

- `V`: flexo printing
- `W`: extrusion
- `X`: rewinding/slitting
- `Y`: confection
- These fields are the canonical planned-operation source for completeness
  checks.
- The `Технологични Карти` worksheet formulas are gated by these flags. If the
  relevant `Database!V:Y` flag is not `Да`, the corresponding operation-card
  block does not populate.

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
| `AQ` | Antistatic | Additive over base |
| `AR` | Masterbatch | Additive over base |
| `AS` | Chalk | Additive/filler over base |

Column identity defines the costing role. Do not add `BASE` or `ADD` markers to
the cell text.

Each costable material cell should use:

```text
[Material Category] [Manufacturer] [Grade or Density] | [%]
```

Examples:

```text
LDPE Rompetrol B20/03 | 60%
MDPE Ethydco 3914 | 20%
LLDPE KJ | 20%
Ampacet Antistatic | 2%
UV Masterbatch | 3%
```

Parsing rule:

- The percentage after the final `|` is the recipe percentage.
- This allows material names to become longer without breaking the format.

Recipe rule:

- Base polymers are entered in `AM:AP`.
- Base polymer percentages in `AM:AP` must sum to `100%`.
- Additives and fillers are entered in `AQ:AS`.
- Additive percentages are percentages over the base polymer blend.
- Additives are not included in the base `100%`.

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

Open detail:

- Shift managers must confirm whether they receive price information in a way
  that supports this numeric-only convention.
- Shift managers must confirm whether prices can always be entered as net of
  VAT.
- Shift managers must confirm whether the canonical sales price unit can always
  be EUR/kg.
- If an order is priced per piece/carton, the actuals app must capture enough
  output quantity data to convert revenue to a comparable unit such as EUR/kg.

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
[Ink/Color Name] | [Anilox lines/cm]
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

Solvents:

- Solvent consumption remains monthly allocated.
- Solvents are not expected to be tied to a specific printed order/card in this
  interim process.

### Workbook Validation Rules

Recipe validation:

- Material cells used for costing must contain a final `|` delimiter.
- The text after the final `|` must contain one numeric percentage.
- Percentages in base columns `AM:AP` must sum to `100%`.
- Additive columns `AQ:AS` may be blank or may contain valid percentages.
- Bag-count formulas such as `1.5 kg/bag`, `1 bag`, or similar shorthand are
  not valid for costing unless converted to percentages first.
- Free-text material names without percentages are not valid for costing.

Sales price validation:

- If the numeric-only convention is approved, price must contain one numeric
  value.
- The value is interpreted as EUR/kg excluding VAT.
- Non-kg pricing exceptions need a defined conversion rule before they can be
  used for margin.

Planning/spec validation:

- Production order number must exist.
- Planned operation flags should be clear enough to support the daily
  completeness check against actuals.

Printing ink validation:

- Filled ink station cells in `AB:AI` should contain a final `|` delimiter.
- The text before the final `|` must contain an accepted ink/color name.
- The text after the final `|` must contain one anilox value.
- Blank ink station cells are allowed.

### Questions For Shift Managers

Sales price:

- Can column `O` be entered as a numeric value only?
- Can that numeric value always mean EUR per kg, excluding VAT?
- How do shift managers receive agreed sales prices today, and are prices ever
  provided with VAT included?
- Are any orders priced per piece, carton, roll, or another unit instead of kg?
- If non-kg prices exist, what information is available at order creation time
  to convert the agreed price to EUR/kg?

Printing colors/inks:

- Can both shift managers use the forward-looking ink station convention
  `[Ink/Color Name] | [Anilox lines/cm]` in `AB:AI`?
- Which ink names/codes should be accepted for standard process colors and
  special colors?
- Can the accepted ink/color names be aligned with invoice-style ink names where
  possible, such as `White`, `Yellow`, `Cyan`, `Magenta`, `Black`,
  `Pantone 485`, `Gold 871`, and `Reflex Blue`?

### Workbook Open Decisions

- Final approved material naming catalog for ERP-compatible raw material names.
- Whether sales price can use the numeric-only EUR/kg excluding-VAT convention.
- Conversion rule for orders priced in a unit other than kg.
- Which required costing data already exists in the current shift-manager
  workbook.
- Final accepted ink/color naming catalog for printing station cells.
- Where workbook-side validation should run: Excel, macro, separate checker, or
  costing tool.

### Workbook Tasks

1. Define the material naming catalog.
2. Confirm the sales price convention for column `O`.
3. Define accepted printing ink/color names.
4. Confirm both shift managers can use `Ink/Color Name | Anilox lines/cm` in
   printing station cells.
5. Create a `Database` worksheet field index across the current
   shift-manager files.
6. Map required costing data to existing workbook fields.
7. Identify required workbook convention or field changes.
8. Decide where recipe and price validation will run.
9. Update the shift-manager process so recipe cells follow `Material | %`.
10. Update the shift-manager process so price follows the approved column `O`
   convention.
11. Update the shift-manager process so printing ink station cells follow
    `Ink/Color Name | Anilox lines/cm`.

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
- The final correction/voiding rule is still open. It must be defined before
  export summing is treated as final, otherwise mistaken duplicate entries could
  overstate minutes or output quantities.

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
should sum numeric values where summing is meaningful:

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
- Correction/voiding rule for mistaken duplicate entries.
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
5. Define the exact export columns.
6. Define the minimum app screens.
7. Define backup/export/recovery requirements.
8. Decide implementation location.

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

Recipe parts normalization:

```text
material kg = output basis * material parts / total recipe parts
```

Example:

```text
AM LDPE Rompetrol B20/03 | 60%
AO MDPE Ethydco 3914 | 20%
AP LLDPE KJ | 20%
AQ Ampacet Antistatic | 2%
AR UV Masterbatch | 3%
```

Total recipe parts:

```text
100 base parts + 5 additive parts = 105 total parts
```

If output basis is `1000 kg`, consumption is:

```text
LDPE       = 1000 * 60 / 105
MDPE       = 1000 * 20 / 105
LLDPE      = 1000 * 20 / 105
Antistatic = 1000 * 2 / 105
UV         = 1000 * 3 / 105
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
