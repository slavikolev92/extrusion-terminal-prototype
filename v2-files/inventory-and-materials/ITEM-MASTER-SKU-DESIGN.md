# Item Master And SKU Design

Status: **latest consolidated design as of August 16, 2026**.

This document is the current design record for the Item Master, SKU identity,
temporary Excel authority, cross-process catalogue distribution, and the
relationship to Task 20 in the extrusion terminal.

Where this document conflicts with conclusions or provisional recommendations
in the two earlier research reports in this folder, this document controls. The
research reports remain useful evidence and background, but they are not the
latest design:

- `MATERIAL-IDENTITY-AND-CATALOGUE-RESEARCH.md`
- `material-identification-research.md`

This is a design and coordination record. It does not by itself implement the
Inventory Prototype, change Task 20, alter the extrusion-terminal database, or
authorize deployment.

## 1. Purpose

Create one durable identity and catalogue model for the purchased materials
that the company intends to track in inventory, then make that catalogue
available to the existing Excel processes and the extrusion terminal.

The design must work in two stages:

1. **Interim:** the Inventory Prototype Excel workbook owns the Item Master and
   publishes it to the other processes through a shared file.
2. **Permanent:** the future local Inventory Application owns the same Item
   Master and publishes the same logical contract through an API or equivalent
   application interface.

The transition must not renumber Items, reinterpret historical references, or
require the extrusion terminal to redesign its recipe storage.

## 2. Confirmed Scope

The current Item Master design covers purchased inventory inputs only:

1. **Extrusion raw materials**, including polymers and additives used in
   extrusion recipes.
2. **Purchased polypropylene film**, specifically BOPP and CPP film.
3. **Printing inks**.
4. **Printing solvents**.

The existing extrusion-material catalogue is the first concrete catalogue that
will use this design because Task 20 needs it for editable executed recipes.

### 2.1 Not Part Of The Current Design

The following are deliberately deferred:

- produced film rolls, bags, sheets, or other finished-product inventory;
- the rule for deciding when two produced outputs are the same stock Item;
- output recipe fingerprints and produced-output SKU allocation;
- individual roll, pallet, container, batch, lot, or serial identity;
- the full inventory ledger, stock valuation, receipts, consumption,
  reconciliation, or period-close design;
- the final Inventory Application UI and workflow;
- a purchasing module or supplier-management workflow; and
- final-product labels, barcodes, or dispatch identity.

Earlier discussion about whether different output recipes create different
finished-product SKUs is therefore not a current dependency and must not delay
the raw-material Item Master or Task 20.

## 3. Agreed Terminology

### 3.1 SKU

The **SKU is the Item Code**.

It is the one permanent identifier used to connect the same Item across:

- the authoritative Item Master;
- expense and cost tracking;
- Shift Manager workbooks where incorporated;
- the extrusion terminal;
- future inventory transactions;
- exports and imports; and
- the future Inventory Application API.

The SKU is:

- machine-assigned under one controlled sequence or allocation rule;
- unique within the company Item Master;
- immutable after allocation;
- never reused for another Item;
- retained when an Item becomes inactive; and
- the value used for automatic cross-process matching.

There is no separate business-facing `item_code` field in addition to SKU. SKU
and Item Code are two names for the same concept. The agreed term for the
contract is **SKU**.

### 3.2 No Separate Cross-System Item UUID

The shared Item Master contract does **not** require a separate UUID-style
`item_id` in addition to SKU.

A particular database may use an internal integer row key if convenient, but
that value:

- has no business meaning;
- does not leave that database;
- is not part of CSV or API integration; and
- is not another company-wide Item identity.

This supersedes the earlier provisional recommendation to expose both an
immutable UUID and a human Item Code. For the agreed central-authority model,
one immutable SKU is sufficient and simpler.

### 3.3 Item Name

**Item Name** is the system-generated, human-readable description of the Item.

The Item Name is generated from the structured characteristics defined for the
Item's family. Each Item family will have its own naming rule. Examples of the
kind of name intended are:

```text
ROMPETROL LDPE B20/0.3
BOPP PLCBZ25 1000mm 0.030mm
```

The term **Canonical Name** is not used in the current design. The field is
called **Item Name**.

The Item Name is expected to remain stable during normal work, but it is not
the identity and does not need to be technically immutable. A spelling,
formatting, or naming-rule correction may regenerate the Item Name while the
SKU remains unchanged.

If an identity-defining characteristic changes so that the result represents a
different inventory Item, the system creates a new SKU instead of renaming the
old Item into the new material.

### 3.4 Aliases

Aliases are alternative names associated with one SKU. They may include:

- familiar operator terminology;
- shortened names;
- historical names;
- supplier or invoice descriptions;
- names previously used in Excel processes; and
- process-specific display names such as the current extrusion technology-card
  display name.

Aliases help search, display, and controlled migration. They are not identity,
cannot create a second Item automatically, and do not replace SKU in stored
cross-process references.

### 3.5 Structured Characteristics

Each Item family has structured characteristics that define what the Item is.
Those characteristics serve two purposes:

1. determine whether an equivalent Item already exists; and
2. generate the Item Name.

Duplicate detection must use the normalized, identity-defining
characteristics. It must not rely only on Item Name or alias text.

The exact fields, normalization, uniqueness rules, and naming formulas for the
four current Item families remain to be completed in the Inventory Prototype
workstream.

## 4. Conceptual Item Master Structure

The Item Master contains a common Item record plus family-specific
characteristics and aliases.

### 4.1 Common Item Data

At minimum, every Item requires:

```text
SKU
ItemFamily
ItemName
BaseUOM
Active
Notes
```

The final contract may add publication and audit fields, but it should not add
a second company-wide Item identifier.

### 4.2 Family-Specific Data

Each current Item family will have its own structured characteristics and name
generation rule:

- extrusion polymers and additives;
- BOPP/CPP film;
- printing inks; and
- printing solvents.

The data may be represented in separate family tables or in another clean Excel
layout. The physical workbook layout is not yet fixed. The logical contract
must nevertheless define the family fields explicitly.

### 4.3 Alias Data

Aliases conceptually require:

```text
SKU
Alias
ContextOrSource
Active
```

Whether aliases are published in a separate table/file or as limited
process-specific columns in the first CSV is still to be decided when the exact
publication contract is written.

## 5. Item Creation And Maintenance

### 5.1 Creating An Item

The agreed creation sequence is:

1. Select the Item family.
2. Enter the required structured characteristics.
3. Normalize the values according to the family contract.
4. Search for an existing Item using the identity-defining characteristics.
5. If an existing Item matches, use its existing SKU and do not create a
   duplicate.
6. If no Item matches, allocate the next SKU.
7. Generate the Item Name from the family naming rule.
8. Add any known aliases.
9. Save the Item as active.

Individual consuming processes must not allocate their own SKUs.

### 5.2 Editing An Item

Editing must distinguish between:

- a descriptive correction that leaves the material identity unchanged; and
- a change to identity-defining characteristics that represents a new Item.

A descriptive correction keeps the SKU. The Item Name may be regenerated, and
the previous name can be retained as an alias.

An identity change creates a new SKU. The previous Item is retained and may be
made inactive when no longer available.

### 5.3 Removing An Item

Items referenced by history are not deleted and their SKUs are never reused.
They become inactive. Consuming processes exclude inactive Items from new
normal selection while retaining them for historical display and resolution.

## 6. Authority And Ownership

### 6.1 Interim Authority

The authoritative Item Master will initially sit inside the Inventory
Prototype Excel workbook.

That workbook is used both to:

- discover and validate the future Inventory Application's behavior; and
- maintain the real interim Item Master used by other processes.

Although the surrounding inventory workbook is a prototype, the allocated SKUs
and approved Item Master data are not disposable prototype fixtures. They are
intended to migrate unchanged into the future Inventory Application.

Only the authoritative Item Master may create, change, activate, or deactivate
Items. Copies in other workbooks and applications are read-only projections.

### 6.2 Permanent Authority

When the local Inventory Application is designed and implemented, it will
import the existing Item Master and become authoritative.

The transition must preserve:

- every SKU;
- Item family;
- Item Name;
- family characteristics;
- aliases;
- lifecycle status; and
- cross-process references already stored by SKU.

The Inventory Application then owns SKU allocation, duplicate checking, Item
Name generation, aliases, and activation/deactivation.

## 7. Interim Publication Through A Shared Folder

### 7.1 Published Snapshot

The Inventory Prototype must publish a complete Item Master snapshot to a
defined shared folder that the consuming processes can access.

The shared integration artifact should be an export such as UTF-8 CSV rather
than the live `.xlsm` workbook. The live workbook remains the editing surface;
the published file is the validated integration boundary.

Conceptually:

```text
Inventory Prototype Excel
        |
        | Publish Item Master
        v
Shared Folder / Item Master Snapshot
        |
        +--> Expense/Cost Tracking
        +--> Shift Manager Workbooks where needed
        +--> Extrusion Terminal
```

The exact shared path and file name remain deployment decisions. A stable name
such as `item-master.csv` is the expected direction.

### 7.2 Publish Behavior

The publication workflow should:

1. validate the complete Item Master;
2. refuse publication if the master contains blocking errors;
3. create a complete snapshot, not a partial patch;
4. include or accompany the snapshot with a schema version, catalogue version,
   and publication timestamp;
5. write to a temporary file first; and
6. replace the published snapshot only after the export completes.

Writing a temporary file and then replacing the published file prevents a
consumer from reading a half-written export.

The exact metadata representation and Excel macro implementation remain to be
designed in the Inventory Prototype repository.

### 7.3 Consumer Copies

Other workbooks may contain a local `ItemMaster` worksheet for lookup and data
validation, but that worksheet is a read-only imported copy.

A refresh button, Power Query, or a small macro may replace the local copy from
the published snapshot. Users of the consuming workbook must not edit that
copy to create or redefine Items.

The consuming process may display Item Name or aliases in its normal UI, but
its stored cross-process reference must be SKU.

## 8. Current Consuming Processes

### 8.1 Expense And Cost Tracking

Invoice or expense lines can be mapped to the correct SKU. Because this process
is controlled directly by the user, adoption of the Item Master can be handled
without a complex synchronization project.

Supplier descriptions or older invoice names may become aliases. New invoice
records should store SKU once the relevant Item exists.

### 8.2 Shift Manager Workbooks

The extrusion Shift Manager workbook currently has a structured
`RecipeCatalogExtrusion` table with normalized material names and useful
identifying fields. It does not yet have SKU.

The existing data should make the initial mapping comparatively direct:

1. assign an approved SKU to every existing catalogue Item;
2. associate the current full name with its SKU as Item Name or an agreed
   source name;
3. retain the technology-card display value as the extrusion alias; and
4. record any previous names as aliases where useful.

It is not mandatory to redesign the complete Shift Manager order-export macro
before the first Item Master can exist. The current clean names can be mapped
to SKU during the transition. Adding SKU behind future workbook selectors is a
later improvement that removes the remaining name-resolution step.

### 8.3 Other Processes

No other immediate consumer has been confirmed as requiring implementation
work. New consumers should use the same published contract and store SKU rather
than establish another naming-based mapping.

## 9. Extrusion Terminal Synchronization

### 9.1 Local Catalogue Copy

The extrusion terminal will maintain a local SQLite copy of the relevant Item
Master data. Task 20's recipe selector reads from this local copy so production
does not depend on the shared folder being available for every page render or
operator action.

The local copy is not authoritative. It exists for reliable local selection,
search, validation, and snapshots.

### 9.2 Manual Refresh

The terminal must provide an explicit Admin action such as `Refresh Item
Master`.

The first safe implementation may either:

- read the configured published file from the shared folder; or
- accept that same published file through an Admin upload when a reliable
  shared mount is not yet available.

Both use the same validator and transactional importer.

### 9.3 Automatic Refresh

A periodic check, tentatively every ten minutes, is a desired convenience once
the shared-folder path and access are reliable.

The terminal should first compare publication/catalogue metadata and import
only when the published version changed. Automatic refresh must call the same
import behavior as manual refresh; it must not have separate update semantics.

The precise polling interval, scheduling mechanism, and deployment path remain
implementation decisions. Manual refresh remains necessary for explicit
recovery and verification.

### 9.4 Refresh Safety

The terminal importer should:

- validate the complete snapshot before changing the active local catalogue;
- identify Items by SKU, never by Item Name alone;
- reject duplicate SKUs and invalid family data;
- avoid silently accepting an older catalogue over a newer one;
- update the complete active projection atomically;
- preserve inactive or historically referenced Items rather than hard-delete
  them;
- retain the prior good catalogue if refresh fails; and
- show the active catalogue version, publication time, row count, and last
  refresh result to Admin.

These are recommended implementation requirements to be incorporated into the
revised Task 20 specification after Item Master v1 is frozen.

## 10. Future Inventory API Connection

The final connection direction is:

```text
Today:
Inventory Prototype Excel -> Shared Snapshot -> Local Terminal Cache

Later:
Inventory Application API -> Local Terminal Cache
```

The future Inventory Application is expected to run locally and expose the Item
Master through an API or equivalent local application interface.

The API must preserve the same logical contract:

- SKU remains the identity;
- Item Name remains presentation data;
- family characteristics remain structured;
- aliases remain associated with SKU;
- inactive Items remain resolvable; and
- catalogue/version metadata supports safe refresh.

Only the transport adapter changes. The terminal's local catalogue, recipe SKU
references, historical snapshots, and effective-recipe rules must not require a
redesign.

A separate synchronization microservice is not required by the current design.

## 11. Historical And Transitional Mapping

Historical data created before SKU adoption often contains only names.

The transition should:

1. create and approve the initial Item Master;
2. assign one SKU to each verified Item;
3. build an explicit mapping from known historical names to SKU;
4. normalize only agreed harmless whitespace and case differences;
5. retain old or abbreviated names as aliases;
6. backfill SKU references where practical; and
7. send ambiguous or unmatched values for explicit review.

Automatic fuzzy matching must not decide Item identity.

The structured and normalized extrusion catalogue means data since July is
expected to be relatively easy to map, but this expectation must be verified
against actual rows rather than assumed.

Once SKU is present, later Item Name changes do not break the link. Historical
records may retain their original name text or a snapshot when exact historical
presentation matters.

## 12. Relationship To Task 20

Task 20 remains the extrusion-terminal feature that:

- preserves the imported Shift Manager recipe as the planned recipe;
- creates a complete executed-recipe snapshot;
- uses the executed recipe when present and the planned recipe otherwise;
- lets workers/Admin edit material, category, and percentage;
- supports adding/removing recipe rows within the seven-slot pilot limit;
- keeps Batch/Lot separate;
- snapshots the current recipe on first start when no executed recipe exists;
- protects production data during re-import; and
- retains an explicit free-text exception when the catalogue lags reality.

Those business decisions remain valid.

### 12.1 Task 20 Assumptions That Are Now Superseded

The current Task 20 specification and implementation plan still assume:

- the Shift Manager `RecipeCatalogExtrusion` worksheet is the catalogue
  authority;
- the catalogue has exactly seven CSV columns;
- `FullMaterialName` is the canonical identity; and
- a valid upload replaces an active name-identified catalogue.

These assumptions are superseded by the latest Item Master design.

Task 20 must not be implemented from its existing plan until the specification
and plan are revised.

### 12.2 Revised Task 20 Identity Direction

The revised design must use:

- SKU as the selected catalogue identity;
- Item Name as the human-readable full name;
- the extrusion display value as an alias/process label;
- category, producer, brand family, grade, and other approved fields as search
  and disambiguation metadata; and
- the published Item Master or an extrusion-specific projection of it as the
  catalogue source.

A catalogue-backed executed-recipe row should retain the SKU and the relevant
human-readable snapshots. Later Item Master updates must not rewrite executed
production history.

An explicit free-text recipe material has no invented SKU. It remains an
unresolved exception until deliberately mapped.

### 12.3 Planned Recipe Transition

The Shift Manager order import currently carries planned material text rather
than SKU. During the transition, the terminal may resolve a planned material to
SKU only when the value matches exactly one current Item Name or approved alias
under the agreed normalization rules.

Unmatched or ambiguous values remain unresolved and must not be fuzzily mapped.
Adding SKU to the Shift Manager workbook/export later is the durable improvement
that removes this transitional lookup.

### 12.4 Re-Import Compatibility

When both planned and executed material references are resolved, Task 20's
semantic re-import comparison should compare SKU rather than name text.

Two different names or aliases that resolve to the same SKU represent the same
material. Two equal-looking names that resolve to different SKUs are different
materials. Batch/Lot remains outside the comparison.

The previously agreed row-atomic rejection rule remains: after production has
started, a differing incoming planned recipe cannot overwrite the executed
recipe or partially update the order row.

### 12.5 Catalogue Refresh And Recipe History

Refreshing the terminal Item Master must never rewrite:

- planned recipe source text;
- normalized planned recipe rows already attached to cards;
- executed-recipe snapshots;
- legacy actual-material text;
- Batch/Lot values; or
- any other production data.

It changes future catalogue lookup and selection availability only. Historical
SKU references remain resolvable even when an Item becomes inactive.

### 12.6 Task 20 Start Condition

Task 20 can return to implementation planning after Item Master v1 defines:

- the SKU format and allocation rule;
- required common fields;
- the extrusion-material family/category fields;
- the Item Name rule;
- the alias representation needed by the terminal;
- lifecycle semantics; and
- the published snapshot schema and version metadata.

At that point, update both:

- `v2-files/TASK-20-EDITABLE-EXECUTED-RECIPES.md`; and
- `docs/superpowers/plans/2026-08-12-editable-executed-recipes.md`.

The existing Task 20 implementation estimate must then be revisited against the
changed source contract and synchronization behavior rather than reused without
review.

## 13. Decisions Superseded Or Rejected

The latest design explicitly supersedes or rejects these earlier ideas:

1. **`FullMaterialName` as identity:** rejected; SKU is identity.
2. **Display name as the cross-process join:** rejected except for controlled
   one-time legacy resolution.
3. **Separate UUID plus Item Code in the shared contract:** rejected as
   unnecessary for the agreed central-authority model.
4. **Separate SKU and Item Code fields:** rejected; they are the same concept.
5. **Canonical Name terminology:** replaced with Item Name.
6. **Each process maintains its own editable Item Master:** rejected; only one
   authority creates or changes Items.
7. **Terminal reads and depends directly on the live Excel workbook:** rejected;
   it consumes a validated published snapshot.
8. **Immediate API/server implementation before the Inventory Application:**
   rejected as premature.
9. **Final-product SKU and recipe-fingerprint design as a Task 20 dependency:**
   deferred and not relevant to the current raw-material inventory scope.

## 14. Remaining Decisions For The Inventory Prototype Workstream

The following work remains. It should be completed in the Inventory Prototype
repository/session so one authority owns the contract rather than the two
projects designing competing versions.

### 14.1 SKU Convention

Define:

- the exact prefix, numeric width, and starting value;
- how the next value is allocated safely in Excel;
- how skipped or voided numbers are treated; and
- how the same allocation continues after migration to the Inventory
  Application.

The current direction is a short, non-descriptive, sequential SKU such as
`ITM-000001`, but the exact format has not been finally approved.

### 14.2 Family Contracts

For each current family, define:

- required and optional characteristics;
- controlled values and units;
- normalization rules;
- the exact duplicate/identity key;
- the Item Name formula;
- validation messages; and
- representative real examples.

The families are:

1. extrusion polymers and additives;
2. BOPP/CPP film;
3. printing inks; and
4. printing solvents.

### 14.3 Alias Contract

Decide:

- whether aliases are many-per-SKU from the first version;
- how context/source is represented;
- whether duplicate aliases across different SKUs are allowed;
- how ambiguous aliases are reported; and
- how aliases are published to consumers.

### 14.4 Publication Contract

Define:

- exact file or files;
- exact headers and types;
- UTF-8 and delimiter rules;
- schema-version representation;
- catalogue-version representation;
- publication timestamp;
- completeness and active/inactive semantics;
- atomic file replacement behavior; and
- validation/error reporting in Excel.

### 14.5 Shared-Folder Operations

Confirm:

- the actual folder and machine/share ownership;
- access from the Linux VM running the extrusion terminal;
- read/write permissions;
- behavior when the folder is unavailable;
- backup and recovery of the authoritative workbook and published snapshot;
- the manual refresh procedure; and
- whether ten-minute automatic checking is appropriate after the mount is
  proven reliable.

### 14.6 Initial Data And Historical Mapping

Prepare:

- the approved initial Item list;
- SKUs for each verified Item;
- current Item Names;
- family characteristics;
- aliases from the Shift Manager and expense data;
- an exception list for ambiguous historical names; and
- evidence that the initial mapping does not collapse different materials.

## 15. Recommended Work Order

1. In the Inventory Prototype repository, write and approve Item Master v1.
2. Build the Item Master tables and publication mechanism in the Excel
   prototype.
3. Populate and verify the initial Items and SKU/name mappings.
4. Publish a representative versioned snapshot.
5. Bring the approved contract and sample snapshot into the extrusion-terminal
   repository.
6. Revise Task 20 and its implementation plan against the approved contract.
7. Implement the terminal's local catalogue, manual refresh, and Task 20 recipe
   workflow.
8. Add automatic shared-folder refresh only after manual refresh and the
   shared-folder deployment are proven reliable.
9. When the Inventory Application exists, replace the file-source adapter with
   its API while retaining the same Item Master meaning and SKUs.

## 16. Final Agreed Model

```text
One authoritative Item Master
    |
    +-- SKU
    |     immutable Item Code and cross-process identity
    |
    +-- Item Name
    |     machine-generated human-readable name
    |
    +-- Structured Characteristics
    |     family-specific identity, validation, and naming inputs
    |
    +-- Aliases
    |     historical, familiar, supplier, and process-specific names
    |
    +-- Active Status
          retains history without reusing or deleting SKU

Interim authority:
    Inventory Prototype Excel
        -> published shared-folder snapshot
        -> read-only copies and terminal local cache

Permanent authority:
    Local Inventory Application
        -> versioned API/snapshot
        -> the same consumers and SKU references
```

This is the foundation to carry into the Inventory Prototype contract and the
subsequent revision of Task 20.
