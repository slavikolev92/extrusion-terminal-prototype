# Semicolon Recipe Category Design

Status: approved direction for implementation planning.

Date: 2026-07-13

## Goal

Update the extrusion terminal recipe contract so Excel owns category validity,
the terminal app accepts multi-word categories, and print output remains compact.

## Background

The terminal app currently parses imported recipe cells by splitting the material
identity on the first space. That assumes the category is one word and the rest
of the identity is the planned material name. This breaks for real multi-word
categories such as `UV Protection`.

The app also has a hard-coded approved category list. That duplicates the Excel
recipe catalog and creates extra terminal-app maintenance whenever the workbook
adds or changes categories. For the current pilot, Excel is the owner of the
recipe catalog and category validity.

## New Recipe Cell Contract

New Excel exports should write recipe cells as:

```text
Category; Material name | Percent
```

Examples:

```text
UV Protection; Additech UV Shield XZ-204 | 2%
LDPE; Rompetrol Midilena TR-130 B20/03 | 38%
LLDPE; HIP Petrohemija TR-130 | 20%
```

Rules:

- `;` separates category from material name.
- `|` separates material identity from percent.
- category is required.
- material name is required.
- percent is required, numeric, and greater than zero.
- non-empty recipe rows must total exactly `100%`.
- category text can contain spaces.
- material name can contain spaces.
- semicolons inside category or material names are not supported by this pilot
  contract.

## Terminal App Responsibilities

The terminal app validates structure only:

- required CSV headers still exist;
- row has an order number;
- row has a usable extrusion step;
- recipe rows follow the contract above;
- recipe total is exactly `100%`;
- target quantity remains valid for release;
- duplicate, stale overwrite, machine, sequence, and production-data
  preservation rules remain unchanged.

The terminal app must not validate category text against a hard-coded business
allow-list. If Excel exported the category, the terminal treats it as the
category to display.

## Import Behavior

Recipe validation moves to CSV import for extrusion rows.

If a CSV row has invalid recipe structure, the row is blocked and reported in
the import result. Other valid rows in the same CSV continue importing. This
matches existing import behavior for row-level errors such as duplicates,
missing order numbers, no-extrusion rows, and stale overwrite rows.

File-level blockers remain limited to file/header problems, such as no header
row or missing required columns.

## Storage

The app keeps storing original imported recipe text on the card fields such as
`raw_material_a`, `linear_pe`, and `masterbatch`.

The derived `recipe_components` rows continue to store:

- `source_text`
- `material_category`
- `planned_material`
- `recipe_percent`

`material_category` must accept arbitrary category text. The SQLite check
constraint that limits it to the old approved category list must be removed for
new databases and migrated away for existing databases.

The app does not add producer, brand family, grade code, material ID, or
inventory sync in this change.

## Admin Behavior

Admin recipe editing keeps separate category, material, and percent controls.

The category control changes from a fixed dropdown to free text, because the app
no longer owns the category list.

Any admin save that changes recipe fields writes the new source text format:

```text
Category; Material name | Percent
```

Existing old-format rows may be read as a fallback, but admin save normalizes
them to the new semicolon format.

## Terminal Display

The terminal continues to show category, planned material, percent, planned kg,
actual material, and batch/lot in separate columns.

For semicolon-format rows:

- category column displays the text before `;`;
- planned material column displays the text between `;` and `|`;
- percent column displays the parsed percent.

## Print Output

Print output should be compact. For parsed rows, print only:

```text
Material name Percent
```

Examples:

```text
Additech UV Shield XZ-204 2%
Rompetrol Midilena TR-130 B20/03 38%
```

Print output should omit:

- category;
- semicolon;
- pipe delimiter.

## Backward Compatibility

The app may keep a fallback parser for old one-word category rows:

```text
LDPE Rompetrol Midilena B20/03 | 38%
```

Fallback behavior:

- first token becomes category;
- remaining identity becomes material name;
- percent is parsed after `|`.

This fallback exists only to keep current cards and development fixtures
readable. The supported export contract going forward is semicolon format.

## Out Of Scope

This change does not add:

- inventory/material master;
- material IDs;
- Excel sync;
- terminal-side category management;
- terminal-side display-name rules;
- separate producer, brand family, or grade-code storage.
