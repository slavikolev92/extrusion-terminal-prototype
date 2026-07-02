# Excel Actuals Capture Plan

Status: V1 functional specification closed for the current planning stage.

Last updated: 2026-07-02.

This document records the current working design for implementing production
actuals capture as feature improvements inside the shift-manager Excel
workbooks, instead of creating a separate actuals app.

The goal of V1 is to capture completed operational-card actuals for costing
without adding a browser terminal, a separate database app, or a heavy
formula-driven workbook. The shift manager receives a completed paper
operational card, transcribes it into the workbook, and the workbook stores the
actuals in structured helper sheets for review and later costing use.

This document is a functionality/specification record, not an implementation
checklist. The English V1 behavior is specified well enough to move to a
separate implementation plan. Bulgarian labels/messages and later workbook
hardening remain deferred.

## 1. Implementation Phasing

### V1 - Actuals Capture

V1 is the immediate work and should be operational before workbook
modernization starts.

V1 includes:

- actual operational-card data entry inside the shift-manager workbook;
- validation that an actual card belongs to an existing production order;
- validation that the selected operation exists on that production order;
- hidden/helper storage for actual card rows;
- simple status tracking for manufacturing review;
- simple review/dashboard output;
- a workbook installer macro that creates/verifies the required structure.

V1 should keep the existing `Database` sheet as the planning/source sheet. The
V1 design must not burden `Database` with actuals or status columns.

The approved V1 behavior is summarized throughout this document. Section 11
records the current specification status.

### V2 - Workbook Modernization

V2 is deliberately deferred until V1 actuals capture works.

V2 may include:

- redesigning or replacing the current `Database` layout;
- creating cleaner normalized order, recipe, and actuals sheets;
- an order-duplication macro that safely copies production orders and forces
  required fields to be updated;
- broader workbook-helper installation consolidation;
- reducing existing workbook formula complexity by moving more behavior into
  controlled macros;
- reviewing whether recipes, orders, actuals, and statuses should become
  separate self-contained workbook areas;
- simplifying the main production-order sheet so shift managers do not have to
  work directly inside the current cluttered `Database` layout for ordinary
  workflows;
- exploring whether macros can replace fragile manual copy/paste operations and
  reduce permanent workbook mistakes;
- reconsidering the workbook's overall order-management structure.
- structured finished-product capture or a new finished-product nomenclature
  control point, if later needed.

V2 should not block V1. Any V2 idea discovered during V1 should be recorded but
not implemented until the actuals workflow is stable.

## 2. Confirmed V1 Scope

### Purpose

V1 exists to collect actual production data for costing.

It is not a live machine-terminal system. There is no browser-based operator
interface, no live queue screen, no start/pause/resume button workflow, and no
machine scheduling engine.

### Entry Source

The source of V1 entry is the completed paper operational card.

The operator completes the physical operational card at the machine and gives
it to the shift manager. The shift manager enters one completed operational card
at a time into Excel.

V1 is forward-looking. It is not intended to reconstruct historical actuals from
old workbook rows. Current planning assumes actuals capture starts with
operational cards started on or after 1 July 2026.

### Operation Types

V1 covers all four operation types from the start:

- `Extrusion`
- `Printing`
- `Rewinding / Slitting`
- `Confection`

The exact operation-specific field requirements still need final confirmation
against the paper cards and shift-manager workflow, but the storage and entry
design must support all four operations.

### Production Order Requirement

Every actual card must belong to a production order.

On save, Excel must validate:

- the production order number exists in `Database`;
- the selected operation is expected for that production order.

Expected operations should be read from these `Database` columns:

```text
Printing: Database!Q
Extrusion: Database!R
Rewinding / Slitting: Database!S
Confection: Database!T
```

An operation is expected when the relevant `Database!Q:T` cell, after trimming
whitespace, case-insensitively equals Bulgarian `да`.

Actuals Capture V1 scans and validates only the configured included row set:
rows at or after the workbook cutoff row/order plus exact configured pre-cutoff
row/order inclusions. Historical rows outside that set are ignored.

Duplicate production order numbers inside the configured included row set are
validation errors. The shift manager must correct the workbook before V1 can
treat those orders as valid.

If either check fails, save is blocked. The shift manager must fix the
production order in `Database` before entering the actual card.

There is no silent entry of operational cards that do not belong to a
production order.

### Operation Selection

The shift manager manually selects the operation from a simple fixed dropdown:

- `Extrusion`
- `Printing`
- `Rewinding / Slitting`
- `Confection`

V1 should not dynamically infer or reduce the dropdown options. Simpler is
preferred. Validation happens on save.

### Multiple Actual Cards Per Operation

Multiple actual cards for the same production order and operation are allowed.
This is normal for split work or large orders.

When saving a new actual card, if active actual cards already exist for the same
production order and operation, Excel should show a simple confirmation:

```text
This production order already has 1 Extrusion actual card.
Save this as an additional Extrusion actual card?
```

The confirmation is a safeguard only. It should not block legitimate split
production.

The entry fields should support an optional note/reason for additional cards,
such as split production, shortfall correction, rework, or duplicate correction.
This reason should help review but should not be required for V1.

### Auto-Assigned Actual Card Numbers

Excel assigns actual card numbers automatically per production order and
operation.

Example:

```text
Order 25278, Extrusion -> Card 1
Order 25278, Extrusion -> Card 2
Order 25278, Confection -> Card 1
```

If a card is voided, existing card numbers should not be renumbered. Stable
numbers are easier to understand during review.

### Editing Existing Cards

Existing saved cards can be loaded into the same entry fields and corrected.

Save behavior:

- saving a new card appends a new hidden/helper row;
- loading an existing card enters edit mode;
- saving in edit mode overwrites the same hidden/helper row after confirmation;
- `UpdatedAt` is refreshed;
- no correction history is required for V1.

Voiding remains available for excluding an entire mistaken card from totals.
Voided rows should remain stored but should be excluded from review totals and
any later costing/export process.

## 3. Workbook UX Concept

### Sheet Model

The workbook should behave like a small controlled data-entry tool, but it
should remain a normal Excel workbook.

Visible sheets should act as screens. Hidden/helper sheets should hold
structured data. Macros should perform data movement and validation only when
the shift manager clicks a button.

V1 likely needs these visible surfaces:

- `Database` - existing source/planning sheet.
- `Actuals Entry` - one-card-at-a-time actuals entry and correction.
- `Actuals Review` - macro-generated dashboard for missing actuals, totals,
  status, and ordered-vs-produced review.
- `Actuals Validation` - macro-generated error report for invalid or incomplete
  actuals/status data.

V1 likely needs hidden/helper storage for:

- actual operational-card rows;
- manufacturing status per production order;
- optional summary/cache data;
- operation time rules and working calendar configuration;
- optional validation/configuration lists.

V1 should use three core helper sheets:

```text
ActualsData
ActualsStatus
ActualsConfig
```

`ActualsData` stores one row per saved operational card.

`ActualsStatus` stores one row per production order with saved manufacturing
status and related status metadata.

`ActualsConfig` stores working calendar configuration, validation lists,
included-row-set configuration, and other settings needed by the actuals
workflow.

The helper sheets should use flat tables, no formulas, no pivots, and no live
links. Macros should read helper data into arrays/dictionaries, process in
memory, and write generated reports back in blocks.

Approved `ActualsData` columns:

```text
Actual card ID
Production order
Operation
Operation code
Actual card number
Produces finished product?
Start date
Start time
Stop date
Stop time
Start datetime normalized
Stop datetime normalized
Pause minutes
Extra minutes
Calculated total minutes
Total minutes override
Override reason
Total minutes
Gross kg
Tare count
Tare weight kg
Calculated net kg
Manual net kg override
Net kg
Waste kg
Meters produced
Units
PP film material
PP film quantity kg
Notes
Voided?
Void reason
CreatedAt
UpdatedAt
```

Approved `ActualsStatus` columns:

```text
Production order
Status
UpdatedAt
```

Approved `ActualsConfig` blocks:

```text
Settings
- default workday start/end
- workbook cutoff row/order for included Database rows
- exact pre-cutoff row/order inclusions for V1
- other workflow settings

Calendar exceptions
- date
- working day yes/no
- start time
- end time
- notes

Operation codes
- EXT = Extrusion
- PRN = Printing
- RWS = Rewinding / Slitting
- CON = Confection

Status list
- Planned
- In Production
- On Hold
- Completed
- Cancelled
```

The principle is confirmed: do not burden the existing `Database` sheet
further.

Manufacturing status should be stored outside `Database` in a hidden/helper
status table keyed by production order. If a production order has no explicit
status row, V1 should treat it as `Planned` by default.

All V1 actuals and status data should live outside `Database`. `Database`
remains the source/planning sheet for production-order context, ordered gross
kg, and expected operation flags.

For V1, `Actuals Entry` should use a static visible input form. All ordinary
actual-entry fields should remain visible instead of hiding and showing fields
by operation. This keeps the workbook simpler and avoids extra UI logic. The
selected operation should control validation and interpretation, not the visible
layout. This can be revised later if the entry page becomes overcrowded.

### Actuals Entry

`Actuals Entry` is the main working screen.

It should support this workflow:

1. Shift manager enters production order number.
2. Shift manager selects operation from the four fixed operations.
3. Shift manager clicks `Load / Start Entry`.
4. Excel loads basic order context from `Database`.
5. Excel lists existing saved cards for that production order.
6. Shift manager enters actual values from the completed paper card.
7. Shift manager clicks `Save New Card`.

The sheet should show useful context after load, such as:

- production order number;
- customer;
- product/type text;
- ordered gross/net/meters/units where available;
- expected operations;
- current manufacturing status.

`Actuals Entry` should show current manufacturing status as read-only context.
It should not be the main place where status is changed, because the entry
sheet is card-level functionality.

### Saved Cards List

After loading a production order, `Actuals Entry` should show a small read-only
list of saved actual cards for that order.

Example columns:

```text
Operation
Card #
Start
Stop
Pause minutes
Total minutes
Gross kg
Net kg
Status
UpdatedAt
Actual card ID
```

This list is generated by macro when the order is loaded. It should not be a
large live formula area.

The list supports:

- seeing whether cards already exist for the order;
- selecting a card to load into the entry fields;
- selecting a card to void.

### Entry Buttons

V1 buttons should be simple:

- `Load / Start Entry`
- `Save New Card`
- `Load Selected Card`
- `Save Changes`
- `Void Selected Card`
- `Clear Fields`

Buttons should be assigned to macros in the production workbook. In visual
prototypes, they can be styled cells.

### Actuals Review

`Actuals Review` is the main active manufacturing review/dashboard sheet.

It should be macro-generated on demand, not formula-heavy. The user clicks
`Refresh Review`, and the macro scans `Database` plus actuals/status helper data
and writes a fresh visible table.

The review should help shift managers answer:

- which production orders are planned, in production, or on hold;
- which expected operations are still missing actual cards;
- which orders have multiple cards for the same operation;
- how ordered amounts compare with actual produced amounts;
- which orders require review before completion.

Manufacturing status should be changed from `Actuals Review`, not from
`Actuals Entry`. Status is production-order-level review functionality, while
actuals entry is operational-card-level data capture.

`Actuals Review` should include a simple `Save` button. In V1, this button
saves status edits from the review table to the hidden/helper status table. The
button name should stay generic because later review-page edits may also be
saved through the same action.

V1 review buttons should be limited to:

```text
Refresh Review
Save
Run Validation
```

No additional filters are required for V1 because the review already uses two
fixed tables: `In Production / On Hold` and `Planned`.

When the user clicks `Run Validation`, the macro should regenerate `Actuals
Validation` and then switch the user to that worksheet so the result is
immediately visible.

The V1 `Actuals Review` layout is approved with this structure. It should be
treated as complete unless review of the real paper operational cards exposes a
missing field that must also be visible on the review page.

By default, `Actuals Review` should show only active manufacturing statuses:

- planned orders;
- in-production orders;
- on-hold orders;

Completed and cancelled orders should not be part of the default review
dashboard because they are not active manufacturing work. They can be retained
in helper data and handled by a separate archive/database-style view later if
needed.

The default review layout should use two generated tables:

1. `In Production / On Hold`
2. `Planned`

The `In Production / On Hold` table should appear above the `Planned` table
because it represents work that is already in the manufacturing flow. The
`Planned` table should appear underneath because it represents orders that exist
but have not yet been sent into production.

Within each table, rows should be sorted by production order number in ascending
order by default.

The tables should still make review conditions visible, including:

- ordered quantity and actual produced quantity differences;
- operation completion progress.

V1 review columns:

```text
Production order
Customer
Product/type
Manufacturing status
Operations entered / expected
Gross ordered kg
Finished product actual gross kg
Finished product actual net kg
Finished product actual meters
Finished product actual units
```

`Operations entered / expected` should display as a compact tracker such as
`3 / 4`. The denominator is the count of expected operations for the production
order from `Database`. The numerator is the count of expected operations that
have at least one active actual card entered. Multiple active actual cards for
the same operation still count as one entered operation for this tracker.

`Gross ordered kg` refers to the ordered gross weight of the final product.
`Database!G` is the gross ordered quantity source for V1 included rows and is
expected to be numeric for normalized orders. Historical non-included rows may
contain text and are not part of V1 validation.

`Finished product actual gross kg`, `Finished product actual net kg`, `Finished
product actual meters`, and `Finished product actual units` should be summed
only from active actual cards where `Produces finished product? = Yes`. This is
important because intermediate operation output, such as extrusion rolls waiting
for confection, is not finished product that can be sent to the customer.

Variance between ordered and actual quantities is a review aid only. It should
not be a hard validation rule in V1.

The review sheet should support the operating discipline behind the process: a
daily or every-few-days review should compare expected operations against saved
actual cards, make missing actuals visible, and help the shift manager find the
paper operational cards that still need to be entered.

Costing export is not part of the immediate V1 design discussion. Once actuals
are stored in structured helper data, an export can be designed later.

### Actuals Validation

`Actuals Validation` should be a separate visible worksheet generated by a
validation macro. The macro can be launched from `Actuals Review`, but the
structured validation output should not be stuffed into the review dashboard.

The `Actuals Validation` worksheet should have a stable report structure, but
its rows should be cleared and regenerated each time validation runs. This keeps
the report predictable while avoiding stale error rows.

The report should show when it was generated, for example:

```text
Validated at: 2026-07-02 14:30
```

If validation finds no errors, the generated report should show a clear success
message such as:

```text
No validation errors found.
```

The validation report should list errors in a clear table, with enough context
for the shift manager to fix the issue. V1 does not need separate warning
severity.

Example columns:

```text
Production order
Customer
Product/type
Status
Operation
Actual card number
Actual card ID
Issue
Suggested fix
Source
```

For order-level errors, such as a missing expected operation, `Actual card
number` and `Actual card ID` can be blank. For actual-card-level errors, both
should be filled so the shift manager can find and load the affected saved
card.

Expected V1 validation report examples:

- production order is marked `Completed`, but an expected operation has no
  active actual card;
- actual card exists for an operation that is no longer expected on the
  production order;
- actual card has malformed or missing required fields;
- PP film material is entered without PP film quantity kg, or vice versa;
- total minutes override exists without a reason.

Default V1 validation messages:

```text
Completed order is missing an actual card for the expected operation.
Actual card operation is not expected for this production order.
Actual card is missing required fields.
PP film material and PP film quantity kg must be entered together.
Total minutes override requires a reason.
```

The validation report is the V1 control mechanism for status correctness. V1
does not need a fragile hard-blocking completion workflow if the validation
sheet makes invalid completed orders obvious.

## 4. Simple Manufacturing Status Tracking

V1 status tracking is approved, but it must remain simple.

Approved English status list:

- `Planned`
- `In Production`
- `Completed`
- `On Hold`
- `Cancelled`

Definitions:

- `Planned`: the production order exists in the workbook, but manufacturing has
  not started or has not been sent into active production.
- `In Production`: manufacturing is active or actual operational cards are
  being returned/entered.
- `Completed`: manufacturing is finished; the final operational card has been
  completed and the customer-ordered item has been produced.
- `On Hold`: manufacturing is temporarily paused or blocked.
- `Cancelled`: the order should not be treated as active manufacturing work.

Status is manually set by shift managers in V1. No automatic status changes are
required for V1.

Status is for review/filtering, not full scheduling. Shipping, expedition, and
sales-side status are out of scope for V1.

Status changes should be performed from `Actuals Review`. `Actuals Entry`
should display the current status only as read-only context.

When a shift manager changes a status on `Actuals Review`, the change should be
saved only when the shift manager clicks the review sheet's `Save` button. The
save action writes the updated statuses to the hidden/helper status table. On
the next `Refresh Review`, the review should pull the saved status from the
helper table.

If no status has been saved for a production order, V1 should default it to
`Planned`. The shift manager can manually change it to `In Production` before
actual cards exist if that better reflects the real workflow.

V1 should not require a hard-blocking completion macro. A shift manager may set
an order to `Completed` manually, but validation must flag the order as invalid
if any expected operation from `Database` has no active actual card.

The separate `Actuals Validation` worksheet is the control mechanism. If a
production order is marked `Completed` before all expected operation actuals
are entered, the validation report should show an error listing the missing
operation or operations.

Bulgarian labels and runtime messages should be translated only after the
English V1 behavior is finalized.

## 5. Time Calculation

Time handling is approved for V1.

### Operation Time Rules

Extrusion runs continuously:

```text
Extrusion total minutes =
  Stop datetime normalized - Start datetime normalized
  - pause minutes
```

Printing, rewinding/slitting, and confection use working-time logic:

```text
Non-extrusion total minutes =
  working minutes between start and stop
  - pause minutes
  + extra minutes
```

Default non-extrusion working time:

```text
Monday-Friday, 08:00-17:00
```

Saturdays, Sundays, and configured non-working days are excluded by default.

### Calendar Configuration

V1 should include a hidden/config worksheet for working calendar data.

The calendar should be prepared manually for `2026-2027`. There is no online
holiday import in V1. The user can manually update the calendar if the process
continues later.

The calendar/configuration should live in `ActualsConfig`, hidden during normal
shift-manager use. V1 does not need a special admin editing workflow for this
sheet; it can be unhidden and edited manually when needed.

The calendar/config sheet should support company non-working days and official
holiday exceptions. Overtime/weekend work does not need complex calendar logic
in V1 because the shift manager can use extra minutes or manual override.

### Time Entry Fields

V1 should not require shift managers to type into a single Excel datetime field
such as `01/01/2026 15:00:00`. That format is too easy to damage while editing.

The visible entry form should split date and time:

```text
Start date
Start time
Stop date
Stop time
Pause minutes
Extra minutes
Calculated total minutes
Total minutes override
Override reason
Total minutes
```

Recommended display formats:

```text
Date: dd.mm.yyyy
Time: hh:mm
```

No seconds are needed in V1.

The save macro should combine start/stop date and time into normalized datetime
values stored in `ActualsData`:

```text
Start datetime normalized
Stop datetime normalized
```

If manual override is blank:

```text
Total minutes = calculated total minutes
```

If manual override exists:

```text
Total minutes = total minutes override
```

If manual override is entered, a reason should be required.

### Time Explanation

The entry sheet should show a readable calculation explanation so the shift
manager can see what Excel counted.

The explanation should include weekday names.

Example:

```text
Included working time:
Wednesday, 1 July 2026, 15:00-17:00 = 120 min
Thursday, 2 July 2026, 08:00-10:00 = 120 min

Pause minutes: -15
Extra minutes: +120
Calculated total: 345 min
Manual override: blank
Total minutes: 345 min
```

If override is used, the UI should clearly show that the override replaces the
automatic calculation.

## 6. Quantity And Output Fields

The final operation-specific field set is still open and should be confirmed
against the paper cards and shift-manager needs.

The earlier actuals-app planning defined fields by operation. For Excel V1,
these should be treated as the starting draft for the entry fields, storage
columns, and validation rules, pending confirmation against the real paper
operational cards.

### Common Fields

Every active actual card should store:

```text
Actual card ID
Production order number
Operation
Actual card number
Produces finished product? Yes/No
Start date
Start time
Stop date
Stop time
Start datetime normalized
Stop datetime normalized
Pause minutes
Extra minutes
Calculated total minutes
Total minutes override
Override reason
Total minutes
Gross kg
Tare/container count
Tare/container weight kg
Calculated net kg
Manual net kg override
Net kg
Waste kg
Meters produced
Units / total unit count
PP film material
PP film quantity kg
Notes
CreatedAt
UpdatedAt
VoidedAt
Void reason
```

`Actual card ID` should be a human-readable stable identifier based on the
production order, operation, and actual card number:

```text
PO[ProductionOrder]-[OperationCode]-[CardNumber]
```

Approved operation codes:

```text
EXT = Extrusion
PRN = Printing
RWS = Rewinding / Slitting
CON = Confection
```

Examples:

```text
PO25278-EXT-1
PO25278-PRN-1
PO25278-RWS-1
PO25278-CON-2
```

This identifier is used to find and overwrite the correct saved actual-card row
when editing existing cards, while remaining readable to the shift manager.

Start and stop values are entered as separate date and time fields, then stored
as normalized datetimes. The operational-card completion date/month is derived
from `Stop datetime normalized`.

Tare fields are generic internally. The visible label can change by operation:

- for roll operations, `Tare/container count` and `Tare/container weight kg`
  mean roll count and core weight;
- for confection, they can mean container count and container weight.

`Waste kg` is a common field for all operations. It should not be treated as
extrusion-only.

`Meters produced` and `Units / total unit count` are secondary quantity fields. They
should be available on the static entry form so printing, rewinding/slitting,
confection, or any later confirmed workflow can record them when present on the
paper card.

`Produces finished product?` is a simple V1 output tag, not a structured
finished-product nomenclature field. It defaults to `No`. If the shift manager
marks it `Yes`, the card's gross kg, net kg, meters produced, and units can be counted as
finished-product output for `Actuals Review`. The existing production-order
product/type context remains the finished-product reference for V1.

V1 should allow `Produces finished product? = Yes` on any operation. Any of the
four operations can produce a finished product in practice. V1 should not infer
or validate "last operation" from `Database` next-operation fields because that
data has not yet been proven trustworthy enough for controlled logic.

### Extrusion Draft Fields

Extrusion should capture:

```text
Production order number
Operation = Extrusion
Produces finished product? Yes/No
Start date
Start time
Stop date
Stop time
Gross kg
Tare/container count / roll count
Tare/container weight kg / core weight
Calculated net kg
Manual net kg override
Net kg
Total minutes
Waste kg
Meters produced, optional
Units / total unit count, optional
Notes
```

Calculated fields:

```text
Calculated net kg = gross kg - (tare/container count * tare/container weight kg)
```

Extrusion output fields:

```text
Total minutes
Net kg
Waste kg
Meters produced, if entered
Units / total unit count, if entered
```

If `Waste kg` is absent, waste is treated as zero.

### Printing Draft Fields

Printing should capture:

```text
Production order number
Operation = Printing
Produces finished product? Yes/No
Start date
Start time
Stop date
Stop time
Gross kg
Tare/container count / roll count
Tare/container weight kg / core weight
Calculated net kg
Manual net kg override
Net kg
Total minutes
PP film material, optional
PP film quantity kg, optional
Waste kg
Meters produced
Units / total unit count, optional
Notes
```

Printing-specific field:

```text
Meters produced
```

Printing output fields:

```text
Total minutes
Net kg
PP film material and PP film quantity kg, if entered
Waste kg
Meters produced
Units / total unit count, if entered
```

### Rewinding / Slitting Draft Fields

Rewinding / slitting should capture:

```text
Production order number
Operation = Rewinding / Slitting
Produces finished product? Yes/No
Start date
Start time
Stop date
Stop time
Gross kg
Tare/container count / roll count
Tare/container weight kg / core weight
Calculated net kg
Manual net kg override
Net kg
Total minutes
PP film material, optional
PP film quantity kg, optional
Waste kg
Meters produced, optional
Units / total unit count, optional
Notes
```

Rewinding / slitting output fields:

```text
Total minutes
Net kg
PP film material and PP film quantity kg, if entered
Waste kg
Meters produced, if entered
Units / total unit count, if entered
```

No additional rewinding/slitting-specific fields are currently expected.

### Confection Draft Fields

Confection should capture:

```text
Production order number
Operation = Confection
Produces finished product? Yes/No
Start date
Start time
Stop date
Stop time
Gross kg
Tare/container count
Tare/container weight kg
Calculated net kg
Manual net kg override
Net kg
Total minutes
Total unit count
PP film material, optional
PP film quantity kg, optional
Waste kg
Meters produced, optional
Notes
```

Confection output/reporting fields:

```text
Total minutes
Net kg
Total unit count
PP film material and PP film quantity kg, if entered
Waste kg
Meters produced, if entered
```

### PP Film Fields

PP film input fields are used for CPP/BOPP film consumed in non-extrusion
operations. They are a section of the static form, not a reason to create
separate operation-specific forms.

When PP film is consumed, V1 should capture both:

```text
PP film material
PP film quantity kg
```

If `PP film material` is entered, `PP film quantity kg` should be required. If
`PP film quantity kg` is entered, `PP film material` should be required.

The PP film material identity should follow this controlled naming convention:

```text
[Film Type] [Product Series] [Thickness] [Width mm]
```

Examples:

```text
BOPP FXC 30 960mm
CPP PLCBZ 28 1040mm
```

Do not include the micron symbol in the PP film item name. The product series
remains in the name because values such as `FXC`, `PLCB`, and `PLCBZ` are
formal product types.

### Additional Supported Fields

The storage design should also support:

```text
Gross kg
Net kg
Tare/container count
Tare/container weight kg
Meters produced
Units
Waste kg
PP film material
PP film quantity kg
Notes
```

Not every operation will use every field. This preserves room for operation
cards that carry secondary output metrics such as meters produced or units.

Expected examples:

- all operations need gross/net/tare or container information, time, waste,
  and notes;
- printing, rewinding/slitting, and confection may need PP film material and PP
  film quantity where applicable;
- printing and rewinding/slitting may need meters produced;
- confection needs units / total unit count and may also need other output
  quantities.

The V1 entry sheet should use one static common form. All fields should remain
visible, and fields that do not apply to the selected operation can remain
blank. Operation-specific rules should be handled by validation on save rather
than by rebuilding or hiding the form.

Net calculation should support:

```text
Calculated net kg = gross kg - (tare/container count * tare/container weight kg)
```

A manual net override may be needed for messy real-world cards. If manual net
override is used, the workbook should clearly show the final `Net kg` value.

## 7. Finished Product Capture

Structured finished-product identity capture is deferred from V1.

V1 should not add finished-product identity fields, a new finished-product
nomenclature form, or a separate finished-product builder. This avoids scope
creep and keeps actuals capture focused on operational-card quantities, time,
status, and review.

V1 should still include the simple `Produces finished product?` actual-card
field. This field answers only whether the output of that actual card should be
counted as finished-product output in `Actuals Review`.

For V1, the workbook should continue to use the existing product/type context
from the production order as the visible finished-product reference. When shift
managers mark an order as `Completed`, that means manufacturing is complete and
the existing production-order product/type context is treated as the produced
finished product for current review purposes.

Structured finished-product identity can be reconsidered in V2 if it proves
necessary. If that happens, the new structured fields can be tied to the same
`Produces finished product?` control.

## 8. Validation Rules

V1 validation should prioritize data quality without making the workbook heavy
or hard to use.

On actual-card save:

- production order number is required;
- production order number must exist in `Database`;
- operation is required;
- operation must be expected for that production order;
- `Produces finished product?` should default to `No` if left blank;
- start date, start time, stop date, and stop time are required unless a manual
  total-only path is explicitly approved later;
- normalized stop datetime cannot be before normalized start datetime;
- numeric fields must be numeric and non-negative;
- total minutes override requires a reason;
- manual net kg override, if used, should be visibly indicated;
- waste kg is common to all operations and must be non-negative if entered;
- meters produced must be non-negative if entered;
- units / total unit count must be non-negative if entered;
- PP film material and PP film quantity kg are optional for non-extrusion
  operations, but if one is entered, the other should be required;
- PP film quantity kg must be non-negative if entered;
- total unit count is required for confection and must be non-negative;
- saving an additional card for the same production order and operation
  requires confirmation.

On validation:

- if a production order is marked `Completed`, every expected operation from
  `Database` must have at least one active actual card;
- if any expected operation is missing an active actual card, the validation
  macro should write an error to `Actuals Validation`;
- V1 does not need to physically block the status value from being entered, but
  invalid completed orders must be visible in the validation output.

## 9. Installer Macro Direction

The production workbook should have one installer macro that creates or verifies
the V1 structure.

The actuals installer should implement the full approved V1 workflow as one
coherent installation. A partial installer that only installs isolated pieces of
the workflow is not useful for acceptance testing, because the workbook will be
used through the installed sheets, buttons, helper tables, and macros together.
Bulgarian translation and later hardening can still be deferred, but the English
V1 actuals workflow should be complete.

The actuals installer should be a separate installer from the recipe-builder
and export-validation installers. It should be independent, but it must be
designed and reviewed so all three helpers can coexist in the same real
shift-manager workbook without competing event handlers, duplicate helper-sheet
ownership, broken protection behavior, or installation-order surprises.

Installer responsibilities should include:

- create visible sheets if missing;
- create hidden/helper sheets if missing;
- create headers/tables if missing;
- preserve existing workbook data;
- preserve existing helper/catalog data;
- install or verify buttons/macros;
- install any required worksheet event handlers if events are used;
- install or verify workbook-open protection setup;
- protect controlled sheets/ranges without blocking macros;
- avoid duplicate or competing event handlers.

The installer must not clear or rewrite existing `Database` rows.

The installer should be compatible with existing workbook helper macros for
recipe building and export validation. Long term, workbook helper installation
should be consolidated so the shift manager does not need to run several setup
macros in a fragile order.

Implementation and testing should target a copy of a real shift-manager
workbook, not a clean synthetic workbook. V1 depends on the existing workbook
shape, especially `Database!G` and `Database!Q:T`, so acceptance depends on the
installer working in the workbook that shift managers actually use.

### Compatibility With Existing Workbook Macros

The actuals installer must coexist with the existing recipe-builder and
export-validation helpers.

Known existing helpers:

```text
RecipeBuilderInstaller
ExportValidation
```

Recipe-builder compatibility findings:

- `RecipeBuilderInstaller` creates/preserves `RecipeCatalogExtrusion` and
  `RecipeCatalogPrinting`.
- It creates UserForms for recipe/printing controlled entry.
- It installs one `Database.Worksheet_BeforeDoubleClick` handler and rewrites
  any existing `Worksheet_BeforeDoubleClick` procedure on `Database`.
- The double-click handler routes only recipe-builder ranges:
  - `Database!W:AD` for printing ink/anilox entry.
  - `Database!AH:AN` for extrusion recipe entry.
- It requires trusted access to the VBA project object model because it creates
  forms and writes worksheet event code.
- It uses `ThisWorkbook` internally.

Actuals V1 compatibility requirement:

- The actuals workflow should not install or overwrite any `Database`
  double-click handler.
- The actuals workflow should not depend on `Database` worksheet events.
- Actuals actions should be button-driven from `Actuals Entry`, `Actuals
  Review`, and `Actuals Validation`.
- Actuals should use unique sheet names and should not create, rename, clear,
  hide, or re-header `RecipeCatalogExtrusion` or `RecipeCatalogPrinting`.

Export-validation compatibility findings:

- `ExportValidation` creates/preserves `ExportConfig`,
  `RecipeCatalogPrinting`, and `RecipeCatalogExtrusion`.
- It hides `ExportConfig`.
- It does not install worksheet/workbook event handlers.
- It validates selected/configured `Database` rows and can export CSV files.
- It uses `ActiveWorkbook` as the target workbook.

Actuals V1 compatibility requirement:

- Actuals should use unique helper sheets: `ActualsData`, `ActualsStatus`, and
  `ActualsConfig`.
- Actuals should not use or modify `ExportConfig`.
- Actuals should not rely on export-validation state except that the same
  workbook may already contain the recipe catalog sheets.
- Actuals should not change existing export-validation behavior or CSV export
  assumptions.

Installation-order direction:

- The actuals installer should be independent of the recipe-builder and
  export-validation installers.
- The actuals installer should be safe to run before or after those installers.
- The actuals installer should preserve any existing helper sheets and headers
  owned by the other installers.
- If the actuals installer needs protection setup, it must not prevent existing
  recipe-builder double-click forms or export-validation macros from working.

Implementation direction:

- Prefer no new worksheet event handlers for V1 actuals.
- Prefer buttons/shapes assigned to public macros for user actions.
- Avoid requiring trusted VBA-project access for actuals if the V1 workflow can
  be installed without creating UserForms or writing code into sheet modules.
- Use clear actuals-specific module/procedure names to avoid collisions with
  `RecipeBuilderInstaller` and `ExportValidation`.
- Target a copy of the real shift-manager workbook during testing.

### Protection Model

V1 protection should be simple and practical. The goal is to prevent accidental
edits to generated cells, formulas, helper-controlled areas, and macro-sensitive
ranges. V1 does not need to be hardened against intentional attempts to break or
modify the workbook.

Recommended V1 behavior:

- `Actuals Entry`: input cells remain editable; generated context, calculated
  fields, and macro-controlled cells are protected.
- `Actuals Review`: status/editable cells remain editable until the user clicks
  `Save`; generated report columns are protected.
- `Actuals Validation`: generated report is protected/read-only.
- `ActualsData`, `ActualsStatus`, and `ActualsConfig`: hidden during normal use.

This protection model can be hardened later after the final workbook design is
settled.

## 10. Lightweight Workbook Principles

V1 should stay lightweight.

Use button-driven macros rather than live formulas wherever possible.

Preferred behavior:

- macros run on explicit button clicks;
- one small workbook-open setup macro may reapply protection;
- hidden/helper sheets are flat tables;
- review tables are generated on demand;
- avoid volatile formulas;
- avoid formulas copied across thousands of rows;
- avoid complex cross-sheet dependencies;
- save actual-card data immediately when the shift manager clicks save.

The workbook should remain usable on the shift-manager PCs.

## 11. V1 Specification Status

The V1 functional specification is closed for the current planning stage. The
operation fields, visible sheets, helper sheets, review workflow, validation
workflow, status model, time-entry UX, and protection direction have been
approved.

The helper-sheet structure has been derived from the approved visible workflow
and required stored data. It can still be revised if real paper-card review
exposes a missing required field.

Bulgarian labels and runtime messages are intentionally deferred until after the
English V1 behavior is implemented or otherwise ready for final wording.

## 12. Deferred V2 Discussion Backlog

The following items are explicitly deferred until after V1 Actuals Capture is
settled:

- order-duplication macro for safe copying of production orders;
- redesign or simplification of the current `Database` worksheet;
- possible normalized workbook structure with separate order, recipe, actuals,
  and status areas;
- broader workbook modernization to reduce formula complexity;
- macro-based replacements for fragile manual copy/paste workflows;
- consolidated installer for all workbook helper tools;
- costing export shape and output format;
- structured finished-product identity/nomenclature capture, if later needed;
- operation-sequence inference from `Database` next-operation fields, but only
  after those fields are reviewed and proven trustworthy;
- broader planning/scheduling functionality beyond simple manufacturing status;
- shipping, expedition, and sales-side statuses.

## 13. Related Prototype Files

Static visual prototypes currently exist under:

```text
interim-costing-process/planning/prototypes/
```

Relevant files:

- `excel-actuals-capture-wireframe.html`
- `excel-actuals-capture-wireframe.xlsx`
- `production-actuals-input.html`

These are discussion prototypes only. They do not define final functionality by
themselves and should be updated or replaced as V1 decisions are finalized.
