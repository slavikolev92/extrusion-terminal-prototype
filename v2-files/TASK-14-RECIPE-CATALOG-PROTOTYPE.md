# Task 14: CSV-Managed Extrusion Recipe Catalogue Prototype

Status: discussion concluded and preserved on July 27, 2026. This task is
deferred until the current UI work and the planned production-data migration
are complete. No application, database, or production deployment work is
authorized by this document.

## Purpose

Add a bounded prototype that helps operators enter consistent actual material
names without changing what existing production records mean.

The current actual/input-material cells remain text fields. Focusing a cell
should open a category-filtered list of known materials, typing should narrow
that list, and selecting a result should place the chosen material name into
the existing field. If the required material is not in the catalogue, the
operator must still be able to enter free-form text.

The prototype is intended to normalize most day-to-day entry while preserving
the exceptions needed during production. It is also intended to test the human
process for keeping a material catalogue current before the application adopts
a stricter material or inventory model.

## Relationship To Task 6

This is the first deliberately bounded prototype slice of Task 6, **Worker
recipe edit functionality**. It does not implement all of Task 6.

In particular, this task covers catalogue maintenance and assisted entry of the
existing actual material text. Editing percentages, adding recipe rows or
categories during production, acknowledgement/audit workflows, and a complete
inventory-backed recipe editor remain part of the wider Task 6 design.

## Complexity And Timing Assessment

- User-visible concept: simple.
- Overall implementation complexity: medium.
- Working estimate: approximately 6-10 engineering hours for implementation,
  validation, automated tests, and live browser verification after the task is
  resumed and its open choices are approved.

The estimate is not caused by a difficult data transformation. The care is in
making catalogue replacement atomic, validating imperfect source data,
preserving in-progress operator input, keeping terminal and admin behavior
consistent, and testing the import and searchable-entry failure paths.

## Current Application Baseline

- Planned recipe material and operator-entered actual material are deliberately
  separate today.
- Actual material is stored as free-form text in
  `recipe_actual_entries.actual_material_used`.
- Terminal and admin correction flows save the same text value through the
  existing production-data path.
- Existing trimming, persistence, and optimistic conflict/version checks should
  remain in force.
- Re-import updates imported/front-card fields while preserving terminal-entered
  production data, including actual material entries.
- No historical actual-material row currently depends on a catalogue identity.

This baseline means assisted entry can be added without changing or converting
the existing actual-material values. The catalogue is reference data for future
entry, not a reinterpretation of historical production.

## Source Workbook Evidence

The initial source was reviewed in:

`/home/sk/projects/extrusion-terminal/source-files/Production Orders (Marco) V14.07.xlsm`

The visible `RecipeCatalogExtrusion` worksheet contains 26 material rows in
`A1:G27` and uses these seven columns, in this order:

```text
Category,Producer,BrandFamily,GradeCode,FullMaterialName,TechnologyCardDisplayName,Notes
```

### Current Catalogue Profile

| Category | Rows |
| --- | ---: |
| LDPE | 4 |
| LLDPE | 8 |
| HDPE | 1 |
| Masterbatch | 7 |
| Antistatic | 2 |
| UV Protection | 1 |
| Filler | 2 |
| reLDPE | 1 |

The workbook treats `FullMaterialName` as the canonical material identity and
`TechnologyCardDisplayName` as the shorter name presented on technology cards.
Its recipe builder cascades through category, producer, brand family, and grade,
then stores the full material identity and percentage. Recent structured recipe
categories match the catalogue case-insensitively; the catalogue additionally
contains `UV Protection`.

`FullMaterialName` is constructed from category, producer, and grade in the
current workbook. `BrandFamily` is useful search and disambiguation metadata but
is not part of that generated full name.

### Source-Data Issues Already Observed

- Worksheet rows 16 and 17 represent different full masterbatch materials but
  both use `LyondellBasell 3011E GREEN` as
  `TechnologyCardDisplayName`. Row 17's full material is `Masterbatch
  LyondellBasell Polywhite 8000`, so the duplicate display value appears
  erroneous or at least ambiguous.
- Worksheet row 22 has leading whitespace in the display name ` VLA 66 NAT`.
- Worksheet row 23 has trailing whitespace in the display name `CONSTAB `.
- The full material names are unique and the required identifying values are
  otherwise populated in the reviewed sheet.

These findings must not be silently hidden by the importer. Harmless surrounding
whitespace can be normalized, but ambiguous names must be rejected and reported
or resolved in the source before activation.

## Chosen Prototype Design

### 1. Keep Production Actuals As Text

The prototype must not replace `actual_material_used` with a foreign key or
make existing production data depend on the current catalogue. A selected
suggestion writes a normalized text value into the same field and follows the
same save behavior as typed text.

This preserves all historical values, keeps free-form exceptions possible, and
ensures that later catalogue edits or removals cannot rewrite an operational
card.

### 2. Persist The Catalogue In SQLite

Use a small SQLite reference-catalogue table plus minimal import metadata rather
than reading a loose CSV file at runtime.

This is the recommended robust pilot approach because the active catalogue then:

- survives application restarts;
- participates in the existing SQLite-safe backup and restore process;
- can be replaced transactionally;
- can expose a clear active version/import timestamp;
- does not depend on a workstation file remaining mounted or unchanged.

The CSV remains the simple maintenance and transfer format. Individual
catalogue-item create/edit/delete screens are not needed for this prototype.

### 3. Replace The Whole Catalogue Atomically

Provide a simple admin upload, recommended as a **Каталог материали** section
under `/admin/settings`.

The server must parse and validate the entire file before changing active data.
A valid upload replaces the complete catalogue in one transaction. An invalid
upload leaves the previous catalogue completely active and shows useful
file/row errors; partial replacement is forbidden.

Replacing the catalogue affects future suggestions only. It must never update
existing cards, saved actual-material text, imported recipes, or production
history.

### 4. Provide Category-Filtered Searchable Suggestions

On both the terminal entry surface and the corresponding admin correction
surface:

- focusing or clicking an actual/input-material cell opens its suggestions;
- the initial suggestions are limited to the recipe row's selected category;
- category comparison is case-insensitive and surrounding whitespace is ignored;
- typing filters within that category across display name, full name, producer,
  brand family, and grade code;
- the result presentation should show enough detail to distinguish similar
  grades and producers;
- choosing a result immediately places the agreed material text into the
  existing field and uses the normal save path;
- if no catalogue entry is suitable, any non-empty free-form value remains
  valid and saveable.

Example: opening an LDPE row initially shows all LDPE entries. Typing `ROM`
should narrow the list to matching Rompetrol materials without requiring the
operator to know which catalogue column contains that text.

The catalogue is advisory in this prototype. A typed value that exactly matches
no item may be visually distinguishable, but it must not be rejected.

### 5. Establish A Catalogue-Update Process

The feature is only useful if someone is accountable for keeping the file
current. Before pilot use, the operating process must identify who:

1. updates the catalogue when new or changed materials arrive;
2. validates and exports the agreed seven-column CSV;
3. uploads it through the admin screen;
4. confirms the displayed import time, filename, row count, and success state;
5. corrects and re-uploads files rejected by validation.

The prototype tests this operational ownership as much as it tests the
autocomplete control.

## Recommended CSV Contract

The initial import should deliberately mirror the reviewed worksheet:

1. Require the exact seven headers in the documented order.
2. Accept a UTF-8 CSV with one material per row and at least one valid data row.
3. Require `Category`, `FullMaterialName`, and
   `TechnologyCardDisplayName`.
4. Permit `Producer`, `BrandFamily`, `GradeCode`, and `Notes` to be empty where
   the source material legitimately lacks them.
5. Trim leading and trailing whitespace and normalize accidental repeated
   whitespace without changing meaningful characters.
6. Reject duplicate full names case-insensitively.
7. Reject duplicate display names case-insensitively unless a deliberate
   disambiguation rule is approved before implementation. The safer prototype
   default is rejection.
8. Validate that `FullMaterialName` begins with its category followed by a
   space, matching the workbook's current rule.
9. Reject semicolons in category and full material name, matching the workbook
   validation rule.
10. Report line numbers and field-specific errors without activating any part
    of an invalid upload.

The active catalogue metadata should expose at least the original filename,
successful import timestamp, active row count, and a catalogue version or
equivalent change token.

## Selection Text Decision

The catalogue must retain both full and display names, regardless of which one
is written to the production field.

Recommended prototype behavior is to write `TechnologyCardDisplayName` because
it matches the familiar technology-card presentation, while showing the full
identity and metadata in search results. This recommendation is not yet a final
decision: the observed duplicate display name must first be corrected or a
clear uniqueness/disambiguation rule approved.

Whichever text is selected, only that text is snapshotted into the existing
actual-material field. Historical rows must not be linked to mutable catalogue
records.

## Refresh And Concurrent-Editing Safety

- A successful catalogue upload should make the new catalogue available to
  newly opened pages immediately.
- Already-open terminal pages need a clear, tested refresh path. The preferred
  implementation is to include the catalogue version in the terminal's existing
  update signature or equivalent polling mechanism.
- If an operator is actively typing when the catalogue changes, the application
  must preserve the existing updates-available/reload behavior and must not
  silently replace their field value.
- Catalogue changes must not increment or otherwise modify production-card
  versions merely because suggestion data changed.
- Terminal and admin should use the same normalized catalogue/query behavior so
  corrections do not produce a second naming convention.

## Data Preservation And Migration Assessment

### Migration required

Yes, for the robust SQLite-backed catalogue only. The production actual-material
field itself does not change.

### Migration type

Schema-only, expected to be the next available migration (currently anticipated
as M005 when this task is resumed). It should add catalogue storage and minimal
import/version metadata.

### Existing production data affected

None. There is no historical transformation, backfill, normalization, or
reinterpretation. Existing actual-material text, recipe rows, rolls, timing,
tare, statuses, versions, and imported fields remain byte-for-byte governed by
their current behavior.

### Initial state

The new catalogue is empty after migration and becomes usable only after a
successful admin CSV import. Runtime catalogue replacement is ordinary
application data, not another schema migration.

### Deployment safety

Deploy the application and schema migration together after the normal
SQLite-safe backup. This feature does not need a production-data snapshot for a
content conversion because no production content is converted. It does not
remove or weaken the independent M001 production-profile and final
release-candidate rehearsal gates.

The existing `v2-files/AGENTS.md` migration-maintenance workflow must be followed
when implementation is explicitly authorized. This task record by itself does
not activate or complete that workflow.

## Validation And Verification Requirements

When this task is resumed, implementation should include at least:

- schema migration tests from every supported predecessor state;
- empty-catalogue behavior;
- successful seven-column import and complete replacement;
- header, encoding, empty-file, missing-value, duplicate, category/full-name,
  semicolon, and whitespace validation;
- proof that a failed import leaves the prior catalogue unchanged;
- case-insensitive category pre-filtering;
- search across display name, full name, producer, brand family, and grade;
- selection into the unchanged actual-material field;
- free-form entry when no result exists;
- consistent terminal and admin correction behavior;
- preservation through recipe re-import and catalogue replacement/removal;
- production-card stale-write behavior while catalogue data changes;
- SQLite backup/restore coverage for catalogue data and import metadata;
- focused FastAPI tests and the full automated suite;
- a live Playwright workflow against a temporary SQLite database, including a
  relevant screenshot under `artifacts/ui-checks/`;
- manual confirmation at both supported workstation viewport sizes that the
  suggestion list is usable without hiding the active recipe context.

Tests and browser verification must not mutate the real runtime database.

## Prototype Learning Goals

The prototype should provide evidence for the eventual material model. During
use, review:

- how often the catalogue must be updated;
- who actually maintains it and whether updates reach terminals promptly;
- how often operators use free-form entry and why;
- which missing, duplicate, or unclear names cause exceptions;
- whether category-first filtering matches the operators' mental model;
- whether producer, brand family, grade, full name, and display name are all
  useful search terms;
- whether the display name is sufficiently unique and familiar to store as the
  production snapshot;
- whether admin corrections use the same conventions as terminal entry;
- whether the proven workflow is reliable enough to support a future single
  editable material field and, later, strict catalogue enforcement.

A practical success signal is that ordinary production entry is overwhelmingly
selected from the catalogue while legitimate exceptions remain possible and
visible. The previously discussed 95% normalization target is an aspiration to
measure, not a hard validation rule for the prototype.

## Future Direction If The Prototype Is Successful

The likely later design is one material field that is prefilled from the recipe.
Workers leave it unchanged when the planned material was used and replace it
when production used something else. Lot/batch fields remain separate.

That future change is not merely this autocomplete control. It would collapse
the current planned-versus-actual presentation, require a deterministic and
approved data migration, and need careful reporting/audit semantics. It should
only proceed after the catalogue-update process and operator workflow have been
proven with real use.

Free-form entry may eventually be disabled after a reliable inventory/material
master process exists. At that point, allowed-list enforcement must be a backend
rule, not only a browser restriction, and handling for genuinely new materials
must be operationally available before production begins.

## Explicitly Out Of Scope For This Prototype

- inventory quantities, availability, receipts, issues, depletion, costing, or
  ERPNext integration;
- treating presence in the catalogue as proof that material is physically in
  stock;
- strict allowed-list enforcement;
- converting or cleaning historical actual-material values;
- collapsing the planned material and actual/input material fields;
- percentage editing or a complete worker recipe editor;
- individual catalogue-item CRUD screens;
- catalogue approval history or a full audit workflow beyond current import
  metadata;
- automatic reading from or writing back to the Excel workbook;
- production deployment during the current UI-fix work.

## Alternatives Considered

### Read A Loose CSV At Runtime

This avoids a schema migration but weakens restart behavior, transactional
replacement, backup/restore coverage, and visibility into which file is active.
It is not the recommended robust pilot approach.

### Integrate With Live Inventory Now

The application does not yet have a reliable material receipt/stock process.
Calling the catalogue “inventory” would imply availability the prototype cannot
prove and would couple a small normalization experiment to a much larger system.

### Require Catalogue Selection Immediately

Strict selection would block real production exceptions before the catalogue
maintenance process has been proven. Free-form fallback is therefore an
intentional prototype requirement.

### Link Production Rows To Mutable Catalogue Items

This would create lifecycle and historical-meaning questions without helping
the immediate normalization goal. The existing text snapshot is safer for this
stage.

## Open Decisions Before Implementation

1. Confirm whether selection writes `TechnologyCardDisplayName` as recommended,
   or `FullMaterialName`.
2. Correct the duplicate/whitespace issues in the source and decide whether
   duplicate display names are always invalid.
3. Confirm the exact admin location and Bulgarian labels for catalogue upload,
   status, and errors.
4. Confirm the exact empty-category behavior when a recipe category has no
   catalogue rows; free-form input must still work.
5. Decide how catalogue-origin versus free-form values should be visually
   indicated to the operator and Shift Manager without changing the saved data
   contract.
6. Approve the exact M005 schema and import metadata after the migration workflow
   has assessed the then-current production schema.

## Resume Conditions

Resume this task only after:

- the current UI correction work is complete;
- the planned production/data migration and its release gates are complete;
- the source catalogue has an assigned maintainer and its known ambiguity is
  resolved;
- the user explicitly authorizes design finalization and implementation.

Until then, this file is the persistent record of the discussion and the basis
for the next design pass. It is not an implementation authorization.
