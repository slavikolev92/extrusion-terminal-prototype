# Structured Recipe Contract

Status: locked contract for the structured extrusion recipe redesign.

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

The normal final source-cell format is still:

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

The Excel recipe builder also supports intentional producer and/or grade
omissions through `N/A` values in `RecipeCatalog`. `N/A` is a catalog control
value only. It is not printed into the final `AM:AS` source cell. When both
producer and grade are `N/A`, the final source cell is category-only before the
delimiter:

```text
reLDPE | 80%
```

When only one of producer or grade is `N/A`, the final source cell contains the
category plus the remaining non-`N/A` text:

```text
LDPE Midilena | 77%
LDPE B20/03 | 77%
```

The parser should split on the final `|`. The text before the final `|` is the
material identity. The text after the final `|` is the recipe percentage.

Extra whitespace is not meaningful. For example, these should parse the same:

```text
LDPE Rompetrol Midilena B20/03 | 77%
LDPE  Rompetrol Midilena B20/03  |  77 %
```

## Approved Categories

The material category is a controlled app contract list. The initial approved
categories are:

- `LDPE`
- `LLDPE`
- `MDPE`
- `reLDPE`
- `Antistatic`
- `Masterbatch`
- `Filler`
- `UV`
- `Antislip`

`Processing Aid` is not approved for the initial list.

The list can be amended after operational review, including the planned monthly
reconciliation on 2026-07-01. Any category change that affects existing imported
or normalized recipe data requires an explicit data-normalization decision before
the contract is changed.

Category matching should be case-insensitive and should normalize accepted input
to the canonical category spelling listed above. For example, `uv`, `UV`, and
`Uv` all normalize to `UV`; `reldpe` normalizes to `reLDPE`.

## Percentage Rule

All non-empty recipe rows in `AM:AS` are part of one recipe percentage pool.
Together they must sum to exactly `100%`.

The canonical percentage format uses a dot decimal, such as `2.5%`. Comma
decimal input, such as `2,5%`, should be accepted and normalized to `2.5%` to
avoid keyboard-layout errors. Spaces around the number and `%` are allowed.
Comma normalization is only for the decimal separator, not thousands separators.
The `%` symbol is required. Percentages must be greater than `0`; use an empty
source cell instead of a `0%` recipe row.

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
| `planned_material` | Remaining material identity after the category; empty string when the Excel builder intentionally omitted both producer and grade |
| `recipe_percent` | Percentage of final product |

For structured admin/terminal display, category-only rows should use the
canonical category as the visible planned material fallback. The normalized
stored value remains an empty string so the app does not invent producer or
grade data that did not exist in the workbook.

Planned kilograms are calculated from `recipe_percent * target_gross_weight`.
They do not need to be authoritative stored source data unless a later
implementation step deliberately chooses to persist them as a derived snapshot.

Target gross weight is required before release. Release should be blocked when
target gross weight is missing, zero, or invalid. The later Excel export macro
validation should also treat missing, zero, or invalid target gross weight as a
blocking export error.

The structured admin/terminal recipe display should use these Bulgarian column
labels:

| Meaning | Bulgarian label |
| --- | --- |
| Material category | Категория |
| Planned material | Планирани материали |
| Recipe percent | % |
| Planned kilograms | КГ |
| Actual material used | Вложени материали |
| Batch/lot | Партида |

## Validation Intent

The app should allow imported draft cards to exist so an admin can correct bad
recipe source text before release.

Release to the terminal should be blocked when:

- any non-empty `AM:AS` row cannot be parsed;
- any non-empty row has missing identity text before `|`, an unapproved
  category, or invalid category text;
- any non-empty row has missing or invalid percentage text;
- any non-empty row has a zero or negative percentage;
- parsed recipe percentages do not sum to exactly `100%`;
- target gross weight is missing, zero, or invalid.

Validation messages shown to admins/operators should be concise Bulgarian
messages. The general form should be:

```text
Рецептата не може да бъде пусната: [reason]. Коригирайте рецептата и опитайте отново.
```

Row-specific reasons should identify the source field or row and use wording in
this style:

- `липсва разделител |`
- `непозната категория`
- `липсва процент`
- `процентът трябва да е по-голям от 0%`
- `сборът на процентите трябва да е точно 100%`
- `липсват планирани кг/поръчано количество`

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

## Locked Contract Decisions

The locked contract decisions were initially approved on 2026-06-24 and extended
by later structured-recipe follow-up work:

1. The approved category list is controlled and amendable, with the initial
   categories listed above.
2. Dot decimal percentages are canonical; comma decimals are accepted and
   normalized. The `%` symbol is required, and row percentages must be greater
   than `0`.
3. Category matching is case-insensitive and normalizes accepted input to the
   canonical approved spelling.
4. Parsed recipe percentages must sum to exactly `100%`.
5. Missing, zero, or invalid target gross weight blocks release.
6. The new admin/terminal recipe column labels are the Bulgarian labels listed
   above.
7. Release/admin validation messages use concise Bulgarian wording with
   row-specific reasons.
8. Intentional producer/grade omissions from the Excel recipe builder are valid
   when represented by omitted text in the final source cell. The app allows
   category-only rows for all approved categories because it imports final cell
   text, not the Excel `RecipeCatalog`.
