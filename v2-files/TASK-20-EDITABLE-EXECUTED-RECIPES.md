# Task 20: Editable Executed Recipes And Material Catalogue

Status: scope approved on August 11, 2026. The initial forward-looking phase is
ready for implementation. Application, schema, and production deployment work
have not yet started.

## Purpose

Give extrusion workers one recipe table that represents what was actually used
to produce the order while preserving the recipe supplied by the Shift Manager
as a separate planned record.

The planned recipe and the executed recipe have different meanings:

- the **planned recipe** is the recipe ordered by the Shift Manager and imported
  from the Shift Manager CSV;
- the **executed recipe** is the complete recipe that workers or an administrator
  save as the recipe actually followed in production; and
- the **effective recipe** is the executed recipe when one has been saved,
  otherwise the current planned recipe.

The initial phase is deliberately forward-looking. It creates empty executed-
recipe storage and does not reinterpret historical operator text. Existing
pre-deployment cards therefore resolve to their planned recipe until someone
deliberately saves an executed recipe for that card or the later historical
migration is performed. For production started after this feature is deployed,
the first start automatically freezes the current recipe as executed.

This task combines the editable-recipe workflow and the CSV-managed material
catalogue into one coherent feature. The catalogue is the normal source for
material selection; the executed-recipe snapshot is the durable production
record.

## Business Model

### Planned Recipe

The planned recipe remains owned by the Shift Manager import and the existing
structured recipe contract:

- source fields remain the seven extrusion recipe fields imported from
  `AH:AN`;
- the original source strings remain on `cards`;
- normalized planned rows remain in `recipe_components`;
- each non-empty row contains category, planned material, and percentage;
- every percentage is greater than zero; and
- the complete non-empty recipe totals exactly `100%`.

An overwrite re-import may update these planned values. It must continue to use
the existing import validation and planned-row synchronization.

### Executed Recipe

An executed recipe is a complete snapshot, not a sparse set of differences.
Once it exists, every effective recipe row comes from that snapshot. The
application must never mix some planned rows with some executed rows for the
same card.

Each executed row records:

- the owning card;
- one stable hidden component slot from the existing seven recipe slots;
- a display position from `1` through `7`;
- material category;
- operator-facing material name;
- canonical full material name when the row was selected from the catalogue;
- whether the material came from an automatic planned snapshot, a deliberate
  catalogue selection, or the explicit free-text exception;
- recipe percentage;
- creation and update timestamps.

The selected catalogue data is copied into the executed row. Executed recipes
must not depend on a mutable catalogue row remaining present after a future
catalogue replacement.

The earlier of these events creates the complete executed snapshot:

1. a successful explicit recipe save, including an unchanged recipe; or
2. the card's first production start, if no executed snapshot exists yet.

Later recipe saves replace that card's entire executed snapshot atomically.

### Effective Recipe Resolution

Every screen or future consumer that needs the recipe actually applicable to
the card must use one shared rule:

1. If the card has at least one valid executed-recipe row, return all of its
   executed rows in display order.
2. Otherwise, return all current planned `recipe_components` rows in their
   existing recipe order.

Because a valid recipe cannot be empty, the existence of executed rows is an
unambiguous whole-recipe override. There is no per-row fallback and no merge.

Consequences of this rule:

- an unstarted card that has never been edited follows its current planned
  recipe;
- first production start freezes that recipe as executed even when workers make
  no changes;
- saving an unchanged recipe creates equal planned and executed records;
- saving a changed material, percentage, added row, or removed row makes the
  saved executed snapshot the source of truth for that card;
- a valid re-import of an unstarted card without an executed recipe changes its
  effective recipe; and
- after production starts, re-import can align the plan with the executed
  recipe but cannot introduce a different planned recipe for that card.

### First-Start Snapshot

On the first transition from pending to running, the backend must create a
complete executed snapshot from the current planned `recipe_components` when
the card does not already have one.

The snapshot and the existing start operation belong to one transaction:

1. validate the card version, lifecycle, active shift, machine rules, target
   quantity, and structured planned recipe using the existing start rules;
2. if no executed rows exist, copy every planned row's category, material, and
   percentage into executed-recipe storage in the same order;
3. mark automatically copied material values as `planned_snapshot` rather than
   falsely claiming a catalogue selection;
4. perform the normal status, timing, and card-version changes; and
5. commit everything together.

If start fails, neither the lifecycle nor executed-recipe data changes. If
workers or Admin already saved an executed recipe before start, the start
transaction uses and preserves that snapshot; it never replaces it with the
plan. The snapshot does not add a second card-version increment beyond the
normal successful start update.

Pause, resume, finish, awaiting-rewinding transition, and finalization never
create a second snapshot or reset the executed recipe.

## Initial Forward-Looking Data Change

### Migration Classification

The initial implementation requires a **schema-only migration**. Determine its
version from the ordered registry in `app/migrations.py` at implementation time.
As of this specification the registry ends at M006, but this document does not
reserve a migration number.

The migration adds:

1. executed-recipe component storage;
2. active material-catalogue storage; and
3. minimal catalogue-import/version metadata.

The migration must not insert executed-recipe rows for any existing card. It
must not transform, normalize, delete, or reinterpret any existing production
value.

### Required Initial State

Immediately after migration:

- the executed-recipe table is empty;
- the material catalogue is empty until the first successful catalogue upload;
- every existing card resolves to its planned recipe;
- existing `recipe_components` remain unchanged;
- existing `recipe_actual_entries.actual_material_used` values remain stored
  exactly as they were;
- existing batch/lot values remain stored exactly as they were; and
- rolls, weights, timing, shifts, pallets, statuses, imports, card versions, and
  all other production data remain unchanged.

The old actual-material text is preserved for the later historical
normalization phase described below. It is not automatically treated as an
executed recipe in the forward-looking phase.

### Executed-Recipe Invariants

The database and backend must enforce, where practical:

- no more than seven executed rows per card;
- one row per component slot per card;
- one display position per card;
- positions restricted to `1..7`;
- a non-empty category and material name;
- a positive percentage on every row;
- a complete recipe total of exactly `100%` before saving;
- a catalogue-selected row has a canonical full-name snapshot;
- a planned snapshot is explicitly marked and may lack canonical catalogue
  identity;
- a free-text row is explicitly marked as free text rather than pretending to
  be catalogue-backed; and
- deleting a card deletes its executed rows through the existing card ownership
  relationship.

Recipe replacement must run in the same transaction as the card-version check
and version increment. A failure at any point leaves the previous executed
recipe completely intact.

## Material Catalogue

### Source Contract

The catalogue is maintained as a UTF-8 CSV corresponding to the Shift Manager
workbook's `RecipeCatalogExtrusion` worksheet. It has exactly these seven
headers in this order:

```text
Category,Producer,BrandFamily,GradeCode,FullMaterialName,TechnologyCardDisplayName,Notes
```

Meanings:

| Column | Meaning |
| --- | --- |
| `Category` | Material category used for the first filter. |
| `Producer` | Manufacturer/producer search and disambiguation metadata. |
| `BrandFamily` | Brand-family search and disambiguation metadata. |
| `GradeCode` | Grade/code search and disambiguation metadata. |
| `FullMaterialName` | Canonical catalogue identity and durable full-name snapshot. |
| `TechnologyCardDisplayName` | Familiar operator-facing material label. |
| `Notes` | Optional reference information retained with the catalogue row. |

`FullMaterialName` is the canonical identity. The UI primarily presents
`TechnologyCardDisplayName`, but search results must also show enough of the
full name, producer, brand family, and grade to disambiguate similar materials.
An executed row stores both the display name and full-name snapshot.

### Known Source Characteristics

The source reviewed for this contract is:

`source-files/Production Orders (Marco) V14.07.xlsm`

The workbook reviewed during the earlier catalogue investigation contained 26
rows in these categories:

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

Known source-quality issues must remain visible during implementation and
verification:

- two different full masterbatch materials used the same display name,
  `LyondellBasell 3011E GREEN`;
- `VLA 66 NAT` had leading whitespace; and
- `CONSTAB` had trailing whitespace.

Surrounding and accidentally repeated whitespace may be normalized. Duplicate
full material names are invalid case-insensitively. Duplicate display names are
allowed only when the full material names differ; the upload result must report
them as warnings and the selector must visibly disambiguate them. The importer
must not silently collapse distinct materials because their display names
match.

### Import Validation

The server must parse and validate the entire CSV before changing active
catalogue data. A valid upload replaces the whole active catalogue in one
transaction. An invalid upload leaves the previous catalogue and its metadata
unchanged.

Validation must:

1. require the exact seven headers in the documented order;
2. require at least one data row;
3. require `Category`, `FullMaterialName`, and
   `TechnologyCardDisplayName` on every row;
4. allow the other four fields to be blank;
5. normalize harmless surrounding and repeated whitespace;
6. reject duplicate full names case-insensitively;
7. report duplicate display names as explicit non-blocking warnings when the
   full names are distinct;
8. require the full material name to begin with its category followed by a
   space, matching the current workbook rule;
9. reject reserved semicolons in category and full material name; and
10. report CSV line numbers and field-specific errors.

The active import metadata must show:

- original filename;
- successful import timestamp;
- active row count;
- monotonically changing catalogue version; and
- warnings produced by the successful import.

A catalogue replacement changes future searches and selections only. It never
rewrites planned recipes, executed snapshots, legacy actual-material text,
batch/lot values, or any other card data.

### Catalogue Administration

Provide one `Каталог материали` section under `/admin/settings` with:

- CSV file selection and upload;
- active filename, timestamp, row count, and version;
- validation errors that do not discard the current catalogue;
- successful-import warnings; and
- a clear empty-catalogue state.

The CSV is the maintenance interface. Individual catalogue-item create, edit,
and delete screens are not required for this phase.

### Refresh And Concurrent Editing

A successful upload is available to newly opened Admin and Terminal pages
immediately. An already open page must learn that the catalogue version changed
through the terminal's existing refresh/update mechanism or an equivalent
lightweight version check.

Catalogue replacement must not increment a production card version or make a
card appear changed. If a worker is already editing a recipe when the catalogue
changes, the browser must preserve the entered form. Save then follows the
catalogue-version rules below: unchanged snapshot values may be retained, while
new catalogue selections are checked against the active version. The page must
never silently replace typed or selected material with another catalogue row.

### Catalogue Maintenance Procedure

The operating procedure for a catalogue update is:

1. The designated Shift Manager/admin updates the seven-column source data when
   a material, name, category, producer, brand family, or grade changes.
2. The maintainer exports the agreed UTF-8 CSV without changing the header
   contract.
3. The maintainer uploads it through `Каталог материали`.
4. The app either retains the prior catalogue and reports blocking errors, or
   atomically activates the complete new catalogue.
5. After success, the maintainer confirms filename, timestamp, row count,
   version, and any duplicate-display-name warnings.
6. Blocking errors are corrected in the source and the complete file is
   uploaded again; rows are never patched around an invalid import.

The application records which catalogue is active, but it does not infer who
should approve commercial or inventory-master naming. Assigning the real
maintainer is an operational deployment prerequisite.

## Recipe Editing Workflow

### Read Mode

The terminal recipe panel normally shows the effective recipe. Its columns are:

- category;
- material;
- percentage;
- calculated kilograms; and
- batch/lot.

The redundant `Actual Material Used`/`Вложени материали` input is removed from
this workflow. The material displayed in the effective recipe row is already
the material that applies to production.

An `Edit` button appears at the top-right of the recipe panel when the current
card and lifecycle state permit the existing production-material corrections.

Batch/lot remains a normal independently saved production input. Opening recipe
edit mode must not disable it, copy it into the executed recipe, or make recipe
save responsible for persisting it.

### Entering Edit Mode

Selecting `Edit` changes only the recipe fields:

- category becomes selectable;
- material becomes category-filtered and searchable;
- percentage becomes editable;
- each row gains a remove control;
- a `+` control can add another row while fewer than seven rows exist; and
- `Edit` is replaced by `Save` and `Cancel`.

Calculated kilograms remain read-only. They use the existing recipe-table rule,
`ordered_gross_kg × recipe percentage`, update from the entered percentage for
immediate feedback, and are recalculated from authoritative values when the
server renders the saved recipe.

The edit form starts from the recipe currently displayed:

- an unedited card starts from its current planned recipe; and
- a card with an executed snapshot starts from that snapshot.

Entering edit mode alone writes nothing.

### Category And Material Selection

Choosing a category limits initial material suggestions to that category.
Category comparison ignores surrounding whitespace and case. Typing searches
within the selected category across:

- display name;
- full material name;
- producer;
- brand family; and
- grade code.

Selecting a catalogue result copies the catalogue category, display name, and
canonical full name into the editable row. The save request must identify the
selected catalogue record or equivalent versioned value so the backend can
verify it; the browser must not be trusted to invent a catalogue-backed full
name.

If a legitimate production material is missing, the operator may deliberately
choose a clearly labelled free-text exception. The exception:

- requires an explicit action rather than silently accepting arbitrary text in
  the normal selector;
- retains the selected/existing category;
- requires a non-empty material name;
- stores no false catalogue identity;
- is visibly distinguishable while editing and in Admin review; and
- remains a valid executed-recipe row so production is not blocked by an
  incomplete catalogue.

Workers cannot create permanent catalogue categories or catalogue items from
the recipe editor. Permanent additions belong in the maintained CSV and a later
atomic catalogue upload.

An existing planned or executed material that is no longer in the active
catalogue must remain displayable and must not be silently replaced. The editor
may preserve it as an explicit unmatched/free-text value. Any deliberate new
catalogue selection uses the current active catalogue.

### Adding And Removing Rows

The recipe remains bounded to seven rows for this pilot.

- `+` appends a new row at the next display position and assigns an unused
  hidden component slot.
- The add control is unavailable when seven rows are present.
- A new row starts without a material or percentage and cannot be saved until
  valid.
- Removing a row closes the visible gap by normalizing display positions.
- At least one valid row must remain.
- Row reordering is not part of this phase.

Recipe save does not modify batch/lot values. Component slots remain stable for
unchanged rows so existing batch inputs continue to refer to the same visible
row. A row with a non-empty batch/lot cannot be removed until the operator
deliberately clears that batch through its independent input. This prevents a
removed slot from hiding a batch or later attaching the old batch to a newly
added material. Changing a row's material does not silently clear its batch;
the batch remains visible so the operator can deliberately keep or correct it.

### Save

`Save` submits the entire editable recipe with the card version and catalogue
version used to build the editor.

The backend must:

1. verify the card exists and the lifecycle permits the same class of
   production correction currently allowed for material/batch editing;
2. enforce the current terminal active-shift rule where that rule applies;
3. reject a stale card version with the existing reload-required conflict
   behavior;
4. validate row count, positions, unique slots, categories, materials,
   catalogue selections, free-text markers, and positive percentages;
5. require the total percentage to equal exactly `100%`;
6. replace the complete executed snapshot in one transaction;
7. increment the card version exactly once; and
8. return the newly resolved effective recipe.

Comma decimal percentages remain accepted and normalized to dot decimals.
Errors use concise Bulgarian messages, identify the affected row where
applicable, preserve the unsaved form values, and leave the previous executed
snapshot unchanged.

If the catalogue changes after the editor opens, unchanged snapshot values may
still be preserved, but any newly selected catalogue identity must be
revalidated against the active catalogue. The application must not silently
substitute a different item from the replacement catalogue.

### Cancel

`Cancel` returns to read mode and restores the last server-saved effective
recipe. It performs no request that changes card or catalogue data.

### Batch/Lot

Batch/lot retains its existing meaning and independent save path:

- it identifies the actual batch/lot used for the recipe row;
- it remains editable without entering recipe edit mode;
- it continues to use optimistic card-version conflict handling;
- it is preserved by recipe saves, catalogue replacements, and re-imports; and
- it is not duplicated into the executed-recipe table.

After the actual-material input is removed, the batch-only save path must update
only `batch_lot`. It must not submit an empty replacement for, or otherwise
erase, the preserved legacy `actual_material_used` value.

The existing `recipe_actual_entries.actual_material_used` field is no longer
the material-entry control for new work. The same table may continue to carry
batch/lot until a later separately justified storage cleanup; its legacy actual-
material values remain untouched for historical normalization.

## Admin Workflow

Admin must be able to create and correct the executed recipe for any card whose
existing production-correction rules allow material correction.

The Admin card keeps the two meanings separate:

- imported/planned recipe fields remain part of the existing source-data
  correction path; and
- the production-material area displays the effective recipe and edits the
  executed snapshot using the same validation and catalogue rules as Terminal.

Saving through the executed-recipe editor must never write planned recipe
fields. Saving planned/imported fields must never write or delete an executed
snapshot.

Admin and Terminal must share the same recipe resolver, catalogue search,
normalization, validation, and snapshot-writing behavior. Admin is not a second
naming convention or a bypass around data rules.

Free-text exception rows must be visibly identifiable in Admin so they can be
normalized later. This phase does not require an acknowledgement workflow.

## Re-import Contract

Re-import remains row-atomic and can never overwrite an executed recipe. It
gains one defensive recipe-conflict rule for cards whose production has already
started.

### Unstarted Cards

For an unstarted card without an executed snapshot, overwrite re-import keeps
its existing behavior:

- update the imported `cards` source fields;
- replace/synchronize normalized planned `recipe_components`;
- increment the card version through the existing overwrite path; and
- preserve terminal-entered production data.

The updated planned recipe remains the effective recipe.

### Started Or Completed Cards

For a card that has started production and has an executed snapshot, parse the
incoming planned recipe and compare it with the complete executed recipe before
updating any field on that card.

The comparison includes:

- material category;
- material identity/name;
- recipe percentage;
- row count; and
- added, removed, or repositioned rows.

Batch/lot is deliberately excluded. It is production metadata saved outside
the planned recipe and does not participate in re-import compatibility.

The comparison is semantic but never fuzzy:

- surrounding/repeated whitespace and letter case are ignored;
- percentages are compared as normalized decimal values;
- internal database IDs are ignored, but the normalized recipe row positions
  are compared and duplicate row occurrences are still counted;
- for a catalogue-backed executed row, an incoming material is equal when its
  category and exact normalized full or display name resolve unambiguously to
  the same canonical catalogue material;
- for a `planned_snapshot` or free-text executed row without canonical
  identity, category and material must match exactly after the documented text
  normalization; and
- substring, spelling-distance, approximate-name, and guessed-alias matching
  are forbidden.

This permits a corrected Shift Manager recipe to align with what workers
actually used. For example, if the original plan named `ROM Petrol B20`, workers
saved `ExxonMobil G300`, and the next import also names the same catalogue
`ExxonMobil G300`, the recipes match.

When the incoming and executed recipes match:

- allow the whole order row to import normally;
- update the planned recipe and other imported fields;
- leave the executed snapshot and batch/lot untouched;
- keep the effective Terminal recipe unchanged; and
- make the planned and executed recipes equal for the later mismatch view.

When any compared recipe value differs:

- reject the entire order row before changing any imported or production field;
- leave its planned recipe, executed recipe, other imported fields, card
  version, and import-source record unchanged;
- continue processing independent rows in the same CSV; and
- report that the order has started or completed and its actually used recipe
  differs, so re-import cannot resolve the discrepancy.

The user-visible Bulgarian message should follow this meaning:

```text
Поръчката е започната или завършена и реално използваната рецепта
(материали или проценти) е променена.
Повторният импорт не може да я замени. Коригирайте реалната рецепта през
Админ/Терминал или импортирайте съвпадаща планирана рецепта.
```

The Shift Manager therefore has two deliberate resolution paths:

1. correct the executed recipe through Admin or have workers correct it through
   Terminal when the newly planned recipe is what production should use; or
2. correct the Shift Manager source so the incoming plan matches the recipe
   actually used, then re-import.

There is no worker warning for a blocked re-import because the worker's
effective recipe never changes.

Expected cases:

| Card state and recipes | Re-import result | Effective recipe afterward |
| --- | --- | --- |
| Unstarted, no executed recipe | Whole row imports | Updated planned recipe |
| Started/completed, incoming plan equals executed | Whole row imports | Existing executed recipe |
| Started/completed, incoming plan differs from executed | Whole row is rejected | Existing executed recipe and existing plan remain unchanged |

Every successful or blocked path must be proven not to insert, update, or delete
executed-recipe rows or catalogue data. An editor opened before a successful
re-import holds an old card version and receives the normal stale-write warning.

## Historical Data Policy For The Initial Phase

For initial delivery, all historical cards are treated as having followed their
planned recipe unless and until an administrator deliberately creates an
executed recipe.

Specifically:

- no historical card receives an automatically generated executed snapshot;
- no legacy actual-material text is assumed to be authoritative;
- repeated entries that merely echo the planned material are not interpreted;
- misspellings, abbreviations, or free-form names are not automatically mapped;
- historical percentages remain only in the planned recipe; and
- historical cards continue to render through the planned fallback.

This is an intentional safe starting state. It avoids guessing from inconsistent
operator text and makes the first migration schema-only.

An administrator may later correct an individual historical card through the
normal executed-recipe editor. Direct database correction is permitted only
through a separately prepared, validated, SQLite-safe data operation—not an ad
hoc live edit.

## Verification Requirements For Initial Delivery

### Migration And Preservation

Automated migration tests must prove:

- fresh initialization creates the new schema;
- every supported predecessor schema migrates successfully;
- executed-recipe and catalogue tables begin empty;
- no historical executed rows are synthesized;
- planned recipe source text and normalized rows are unchanged;
- legacy actual-material and batch/lot values are unchanged;
- all unrelated production tables and values are unchanged;
- injected migration failure rolls back atomically;
- a second initialization is a no-op;
- `PRAGMA integrity_check` returns `ok`; and
- `PRAGMA foreign_key_check` returns no rows.

Implementation and later deployment must follow
`docs/implementation-notes/sqlite-migration-and-deployment-playbook.md`.

### Catalogue

Tests must cover:

- exact-header and encoding validation;
- empty file and missing required values;
- whitespace normalization;
- duplicate canonical full-name rejection;
- distinct full names sharing a display name and producing visible warnings;
- category/full-name and reserved-semicolon validation;
- line- and field-specific error reporting;
- successful whole-catalogue replacement;
- failed import preserving the previous catalogue and metadata;
- monotonically changing catalogue version;
- open-page catalogue-version refresh without a production-card version bump;
- preservation of an in-progress recipe edit during catalogue replacement;
- case-insensitive category filtering;
- search across every documented search field;
- disambiguated search results;
- catalogue-selected snapshots remaining unchanged after catalogue replacement;
- explicit free-text exceptions; and
- catalogue data surviving the normal SQLite backup and restore process.

### Recipe Resolution And Persistence

Tests must cover:

- planned fallback for unstarted and pre-feature historical cards when no
  executed rows exist;
- a first explicit save creating a complete snapshot;
- first start creating a complete `planned_snapshot` when none exists;
- first start preserving an executed recipe saved before start;
- failed start rolling back both lifecycle and snapshot writes;
- successful start incrementing the card version only through its normal start
  update;
- equal planned/executed recipes resolving to executed rows after save;
- changed material and changed percentage;
- adding and removing rows within the seven-row bound;
- rejection of zero rows, more than seven rows, duplicate slots/positions,
  missing values, non-positive percentages, and totals other than `100%`;
- comma-decimal normalization;
- atomic rollback on invalid save or injected failure;
- card-version increment exactly once;
- stale Terminal and Admin saves being rejected;
- batch/lot preservation across recipe edits;
- legacy actual-material text preservation;
- Admin and Terminal using the same resolver and validation;
- successful row-atomic re-import when incoming planned and executed recipes
  are semantically equal;
- whole-row rejection for category, material, percentage, added-row,
  removed-row, and row-position differences after start;
- proof that batch/lot does not create a false conflict;
- exact normalization and canonical catalogue equality without fuzzy matching;
- a blocked row preserving its imported fields, planned recipe, executed
  recipe, card version, and import-source record; and
- independent rows in the same CSV continuing after one recipe-conflict row is
  blocked.

### Browser Workflow

Run focused live Playwright checks against a temporary SQLite database at both
supported workstation viewport sizes. Verify at least:

- recipe read mode and top-right `Edit`;
- `Edit`/`Save`/`Cancel` transitions;
- category filtering and material search;
- visually disambiguated duplicate display names;
- the explicit free-text exception;
- live percentage/kilogram feedback;
- add/remove behavior and the seven-row limit;
- inline save errors without input loss;
- independent batch/lot editing;
- first start leaving the visible effective recipe unchanged while creating its
  executed snapshot;
- stale-write/reload behavior;
- completed-card correction where currently permitted;
- no horizontal overflow or obscured recipe context; and
- no console or page errors.

Store screenshots and any trace/video evidence under
`artifacts/ui-checks/editable-executed-recipes/`. Tests must never mutate the
real runtime database.

### Final Agent Review

Because no human code review is planned, implementation is not complete until
the implementing agent has:

1. reviewed every changed database and route path for preservation and stale-
   write safety;
2. reviewed the Terminal and Admin workflows against this specification;
3. run focused tests and the complete Python suite;
4. run syntax/import checks and `git diff --check`;
5. inspected the required Playwright screenshots; and
6. corrected all issues found before presenting the UI to the user.

The user's acceptance activity is limited to trying the UI and commenting on
the visible workflow. It is not a substitute for the automated verification or
agent review above.

## Initial Delivery Estimate

Estimated active agent work for the approved forward-looking phase is
approximately **10-14 hours**, including implementation, automated tests,
browser verification, screenshot inspection, and the final agent review.

That estimate covers the executed-recipe schema and resolver, catalogue import
and search, Terminal/Admin editing, migration tests, workflow tests, and UI
verification. The later work below is recorded for continuity and will be
estimated separately when activated.

## Required Future Follow-Ups

These follow-ups are not throwaway possibilities. The initial schema and
snapshot semantics must be designed so they can be added without redefining
what planned and executed recipes mean.

### 1. Normalize And Migrate Historical Completed Recipes

After the forward-looking workflow has been used and before the production
database is treated as fully normalized, perform a separate historical-data
project.

Expected procedure:

1. Stop treating the development database as representative and take a fresh
   SQLite-safe production backup under an authorized maintenance procedure.
2. Work only on immutable/disposable copies of that backup.
3. Profile completed and archived cards, their planned recipes, legacy
   `actual_material_used` text, and batch/lot rows.
4. Normalize whitespace, casing, abbreviations, duplicate echoes of planned
   material, misspellings, and known catalogue aliases without guessing.
5. Build an explicit mapping from each meaningful historical material string to
   a catalogue item or a documented unresolved free-text value.
6. For each eligible historical card, construct one complete executed snapshot:
   copy the planned category and percentage for every historical row, then apply
   only confirmed material substitutions from the legacy actual text.
7. Treat historical actual text equal to the planned material as confirmation
   of the same material, not as a separate recipe difference.
8. Leave ambiguous rows unresolved until they are manually decided; do not infer
   material identity from weak similarity.
9. Rehearse the deterministic conversion, verify exact before/after invariants,
   and produce a reviewable exception report.
10. Apply the approved migration only through the SQLite migration/deployment
    playbook, with rollback evidence and a final production comparison.

The desired end state is a complete executed snapshot for every historical
completed card included in the approved migration, even when that snapshot is
identical to the plan. Historical percentages default to the planned
percentages because workers previously had no percentage-editing workflow; any
claimed historical percentage difference requires independent evidence and a
separate explicit mapping.

Legacy source text should be retained at least through verification and rollback.
Deleting or repurposing old columns/tables is a later cleanup decision after the
new history is proven complete.

### 2. Shift Manager Recipe-Difference Notifications

Add a Shift Manager notification/tray workflow derived from planned-versus-
executed differences.

The comparison should detect:

- a changed material;
- a changed percentage;
- an added executed row;
- a removed planned row; and
- an explicit free-text material without a catalogue identity.

No notification is needed when:

- no executed recipe exists and effective resolution therefore uses the plan;
  or
- the complete executed snapshot is equal to the planned recipe after agreed
  normalization.

Worker/Admin executed-recipe edits may create a mismatch. A later re-import is
allowed to remove that mismatch only when the complete incoming planned recipe
semantically equals the executed recipe. A differing re-import is blocked and
therefore cannot create a new mismatch or alter the existing comparison. The
tray must derive its state from the current planned and executed records rather
than overwrite either record.

The later design must decide presentation, acknowledgement state, whether
acknowledgement is stored or derived, and how corrected recipes clear or update
the notification. It must not pretend the Shift Manager can reject material
that has already been used in completed production.

### 3. Inventory-Application Communication And Consumption

Design how the extrusion terminal will communicate completed production and
material consumption to the future inventory application.

The consumption rule is already defined conceptually:

1. Resolve the card's effective recipe—executed when present, otherwise
   planned.
2. Use the actual produced net amount for the card.
3. For each effective recipe row, calculate theoretical consumption as:

   ```text
   actual produced net amount × recipe percentage
   ```

4. Attribute that theoretical quantity to the catalogue/canonical material
   identity represented by the effective row.
5. Resolve planned fallback rows that lack a canonical catalogue identity
   through an explicit catalogue mapping before inventory posting.
6. Treat free-text or historically unresolved materials as explicit exceptions
   that must also be mapped before inventory posting.

This is theoretical consumption. Workers are not expected to weigh the exact
input quantity for every order. At month end, theoretical material stock will
be compared with physical stock; loss, waste, process variation, and other
differences will be handled by a later monthly reconciliation/reallocation rule
across the relevant materials and orders.

When the inventory application exists, decide the transport boundary—such as a
validated export, an authenticated API, or another explicit integration—plus
idempotency, correction/reposting behavior, material identifiers, period close,
and reconciliation ownership. The recipe editor itself must not directly
deplete inventory; it provides the executed source data that the later
integration consumes.

## Durable Decisions

1. Planned and executed recipes are separate records with separate meanings.
2. Executed recipe is the source of truth whenever it exists; otherwise planned
   recipe is the source of truth.
3. Executed recipes are complete snapshots, never sparse row overlays.
4. First production start atomically snapshots the current planned recipe when
   no executed snapshot already exists.
5. Re-import cannot overwrite an executed snapshot. After production starts,
   its whole order row is accepted only when the incoming planned recipe
   semantically equals the executed recipe; otherwise that row is rejected
   without any changes.
6. Recipe compatibility compares category, material identity, percentage, and
   ordered row membership without fuzzy matching; only Batch/Lot is outside the
   comparison.
7. Initial deployment is forward-looking and performs no historical data
   backfill.
8. Existing legacy actual-material text is preserved for later normalization
   but is not used as the new executed recipe automatically.
9. The normal material-entry path is a category-filtered catalogue selection;
   a deliberate free-text exception remains available so production is not
   blocked by catalogue lag.
10. Catalogue selections are snapshotted into production data and do not depend
   on the mutable active catalogue.
11. The recipe is limited to seven rows in this pilot.
12. Category, material, and percentage are editable; kilograms are calculated;
    batch/lot remains independently editable.
13. The first successful save creates the complete executed snapshot even when
    it equals the plan.
14. Historical normalization, recipe-difference notifications, and inventory
    communication are required later work and must preserve these meanings.
