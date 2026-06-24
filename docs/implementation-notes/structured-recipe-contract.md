# Structured Recipe Contract

Status: draft contract for the structured extrusion recipe redesign.

Created: 2026-06-24.

This note records the app-side recipe convention agreed during the structured
recipe redesign discussion. `open-issues.md` tracks the implementation roadmap
under `OI-003`.

## Purpose

The app will continue importing the shift-manager workbook recipe fields from
the existing extrusion columns `AM:AS`. Those cells will use a parseable text
convention so the app can display and store clean recipe-component rows while
still preserving the original imported workbook text.

This redesign supports app-side terminal/admin usability and future exports from
the prototype. It does not add costing, pricing, inventory, material master
management, or ERP functionality.

## Source Columns

The source recipe fields remain:

| Workbook column | App field | Current label |
| --- | --- | --- |
| `AM` | `raw_material_a` | Raw material A |
| `AN` | `raw_material_b` | Raw material B |
| `AO` | `raw_material_c` | Raw material C |
| `AP` | `linear_pe` | Linear PE |
| `AQ` | `antistatic` | Antistatic |
| `AR` | `masterbatch` | Masterbatch |
| `AS` | `chalk` | Chalk |

The original imported source text in these fields remains stored on `cards` and
continues to be used by print output.

## Accepted Cell Format

Each non-empty recipe source cell should use:

```text
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code] | [% of final product]
```

Example:

```text
LDPE Rompetrol Midilena B20/03 | 77%
LLDPE SABIC 119ZJ | 18%
Antistatic Novachem AT 04673 LD | 2%
Masterbatch Polibach White 8000 ET | 3%
```

The parser should split on the final `|`. The text before the final `|` is the
material identity. The text after the final `|` is the recipe percentage.

Extra whitespace is not meaningful. For example, these should parse the same:

```text
LDPE Rompetrol Midilena B20/03 | 77%
LDPE  Rompetrol Midilena B20/03  |  77 %
```

## Percentage Rule

All non-empty recipe rows in `AM:AS` are part of one recipe percentage pool.
Together they must sum to `100%`.

There is no separate "base blend plus additive over base" interpretation for
this app redesign. Additives, masterbatches, and fillers are included in the
same final-product percentage total as base polymers.

For a 1,000 kg target, this recipe:

| Category | Planned material | Percent | Planned kg |
| --- | --- | ---: | ---: |
| LDPE | Rompetrol Midilena B20/03 | 77% | 770 kg |
| LLDPE | SABIC 119ZJ | 18% | 180 kg |
| Antistatic | Novachem AT 04673 LD | 2% | 20 kg |
| Masterbatch | Polibach White 8000 ET | 3% | 30 kg |

sums to `100%` and `1,000 kg`.

## Normalized App Rows

The app will preserve the original source text and also create derived
recipe-component rows with the meaningful parts split into fields:

| Field | Meaning |
| --- | --- |
| `card_id` | Owning production card |
| `component_key` | Source app field, such as `raw_material_a` |
| `source_text` | Original imported/editable source cell text |
| `material_category` | First approved category token, such as `LDPE` |
| `planned_material` | Remaining material identity after the category |
| `recipe_percent` | Percentage of final product |

Planned kilograms are calculated from `recipe_percent * target_gross_weight`.
They do not need to be authoritative stored source data unless a later
implementation step deliberately chooses to persist them as a derived snapshot.

## Validation Intent

The app should allow imported draft cards to exist so an admin can correct bad
recipe source text before release.

Release to the terminal should be blocked when:

- any non-empty `AM:AS` row cannot be parsed;
- any non-empty row has an unapproved material category;
- any non-empty row has missing or invalid material identity text;
- any non-empty row has missing or invalid percentage text;
- parsed recipe percentages do not sum to `100%` within the accepted tolerance.

The Excel export macro should eventually validate the same contract before
writing CSV files. The macro must remain read-only with respect to workbook
cells.

## Print Output

Print output remains unchanged. It should continue to render the original
imported source text, including the `|` delimiter and percentage text.

## Out Of Scope

This redesign does not add:

- a costing engine;
- material price tables;
- inventory tracking;
- material master/catalog management inside the app;
- ERP workflow expansion;
- writing terminal-entered production data back to Excel;
- changes to print layout.

## Open Contract Decisions

These must be confirmed before implementation planning starts:

1. Approved material/additive category list.
2. Decimal format rules for percentages, including whether comma decimals are
   accepted.
3. Percentage total tolerance, for example exactly `100%` or `100 +/- 0.01`.
4. Release behavior when target gross weight is missing but recipe percentages
   are valid.
5. Final Bulgarian labels for the new admin/terminal recipe columns.
