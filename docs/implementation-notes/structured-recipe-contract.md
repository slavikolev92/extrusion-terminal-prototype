# Structured Recipe Contract

Status: locked contract for the structured extrusion recipe redesign.

Created: 2026-06-24.

This note records the app-side recipe convention agreed during the structured
recipe redesign discussion. `open-issues.md` tracks the implementation roadmap
under `OI-003`.

## Purpose

The app will continue importing the shift-manager workbook recipe fields from
the cleaned extrusion columns `AH:AN`. Those cells will use a parseable text
convention so the app can display and store clean recipe-component rows while
still preserving the original imported workbook text.

This redesign supports app-side terminal/admin usability and future exports from
the prototype. It does not add costing, pricing, inventory, material master
management, or ERP functionality.

## Source Columns

The source recipe fields remain:

| Workbook column | App field | Current label |
| --- | --- | --- |
| `AH` | `raw_material_a` | Raw material A |
| `AI` | `raw_material_b` | Raw material B |
| `AJ` | `raw_material_c` | Raw material C |
| `AK` | `linear_pe` | Linear PE |
| `AL` | `antistatic` | Antistatic |
| `AM` | `masterbatch` | Masterbatch |
| `AN` | `chalk` | Chalk |

The original imported source text in these fields remains stored on `cards`.
Print output parses that text and renders a compact material-plus-percent view.

## Accepted Cell Format

The normal final source-cell format is:

```text
Category; Material name | Percent
```

Example:

```text
LDPE; Rompetrol Midilena B20/03 | 77%
LLDPE; SABIC 119ZJ | 18%
UV Protection; Additech UV Shield XZ-204 | 2%
Masterbatch; Polibach White 8000 ET | 3%
```

The app requires both sides of the `;` delimiter. If the material is reusable
LDPE and the only useful display text is also the category-like name, Excel
should still export a non-empty material name:

```text
reLDPE; Recycled LDPE | 80%
```

The parser splits on the final `|`. The text before the final `|` is the
material identity. Within that identity, the first `;` separates category from
material name. The text after the final `|` is the recipe percentage.

Extra whitespace is not meaningful. For example, these should parse the same:

```text
LDPE; Rompetrol Midilena B20/03 | 77%
LDPE  ;  Rompetrol Midilena B20/03  |  77 %
```

## Category Ownership

Excel owns the recipe catalog and category validity. The terminal app validates
recipe structure only. It does not keep an approved category list and does not
decide whether category text such as `UV Protection` is valid business data.

The app stores whatever category text Excel exports, as long as the source cell
matches the structural contract. Category and material names must not contain
the reserved `;` delimiter in this pilot contract.

## Percentage Rule

All non-empty recipe rows in `AH:AN` are part of one recipe percentage pool.
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
| `material_category` | Text before the `;` delimiter, such as `LDPE` or `UV Protection` |
| `planned_material` | Non-empty text after the `;` delimiter and before the final `|` |
| `recipe_percent` | Percentage of final product |

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

CSV import validates recipe structure for extrusion rows before saving the row.
Invalid recipe rows are blocked per row, while valid rows in the same CSV still
import.

Import and admin recipe saves are blocked when:

- any non-empty `AH:AN` row cannot be parsed;
- any non-empty row has missing category or material text;
- any non-empty row has missing or invalid percentage text;
- any non-empty row has a zero or negative percentage;
- parsed recipe percentages do not sum to exactly `100%`;
- category or material text contains the reserved `;` delimiter.

Release to the terminal also blocks when target gross weight is missing, zero,
or invalid.

Validation messages shown to admins/operators should be concise Bulgarian
messages. The general form should be:

```text
Рецептата не може да бъде пусната: [reason]. Коригирайте рецептата и опитайте отново.
```

Row-specific reasons should identify the source field or row and use wording in
this style:

- `липсва разделител |`
- `липсва разделител ;`
- `липсва категория`
- `липсва материал след категория`
- `неподдържан разделител ; в материала`
- `липсва процент`
- `процентът трябва да е по-голям от 0%`
- `сборът на процентите трябва да е точно 100%`
- `липсват планирани кг/поръчано количество`

The Excel export macro should eventually validate the same contract before
writing CSV files. The macro must remain read-only with respect to workbook
cells.

## Print Output

Print output renders compact parsed recipe text:

```text
Material name Percent
```

Examples:

```text
Additech UV Shield XZ-204 2%
Rompetrol Midilena B20/03 77%
```

The print view omits the category, semicolon, and pipe delimiter for valid
parsed rows.

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

1. Excel owns category validity; the app validates structure only and stores
   arbitrary category text.
2. Dot decimal percentages are canonical; comma decimals are accepted and
   normalized. The `%` symbol is required, and row percentages must be greater
   than `0`.
3. Category text is preserved from the source cell; the app does not canonicalize
   it against an approved list.
4. Parsed recipe percentages must sum to exactly `100%`.
5. Missing, zero, or invalid target gross weight blocks release.
6. The new admin/terminal recipe column labels are the Bulgarian labels listed
   above.
7. Release/admin validation messages use concise Bulgarian wording with
   row-specific reasons.
8. Category-only rows are no longer valid. Excel should export a category and a
   non-empty material name, even when those texts are similar.
