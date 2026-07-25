# Shift Manager Export/Import Field Correctness

Status: implemented contract and current behavior record.

Date: 2026-07-25.

Latest verified workbook and export:

```text
source-files/Production Orders (Marco) V14.04.xlsm
source-files/extrusion_orders_20260725_110012.csv
```

V14.04 and its exact 29-column CSV are authoritative for the app import
contract. Older workbooks and CSV formats are historical only.

## Decision

The app aligns to the V14.04 Shift Manager export structure only.

Do not support a second old CSV quantity format. The old quantity/unit header is
dead and there is no transition compatibility requirement.

Do not add micro perforation to the app. It is not part of the final V14.04
contract; examples appear only in free-text product or notes values.

There is no `extrusion_flag` in the new CSV contract. The new export uses
numeric operation route sequencing. `extrusion_sequence` must equal `1` for every
exported terminal row, and that is the app-side extrusion eligibility signal.

The final canonical CSV header is:

```csv
order_number,order_date,delivery_date,customer,city,product_type,ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units,product_form,material,size_thickness,notes,printing_sequence,extrusion_sequence,rewinding_slitting_sequence,confection_sequence,extrusion_next_operation,extrusion_folding,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
```

Representative anonymized sample CSV:

```csv
order_number,order_date,delivery_date,customer,city,product_type,ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units,product_form,material,size_thickness,notes,printing_sequence,extrusion_sequence,rewinding_slitting_sequence,confection_sequence,extrusion_next_operation,extrusion_folding,extrusion_treatment,raw_material_a,raw_material_b,raw_material_c,linear_pe,antistatic,masterbatch,chalk,packaging_method
90001,25/07/2026,01/08/2026,Примерен клиент,София,ТСФ 500/0.050,500,20,15000,40000,плоско,LDPE,500/0.050,"Анонимизирана тестова поръчка, без реални клиентски данни",2,1,3,4,Printing,,,LDPE; Rompetrol B20/03 | 66%,,HDPE; HIP Petrohemija TR-130 | 17%,LLDPE; ExxonMobil C4LL1018 BT | 6%,Antistatic; LyondellBasell VLA 66 NAT | 2%,,Filler; Noviz FM80-41 | 9%,1 голям палет
```

## Current Workbook Structure

The latest workbook `Database` sheet uses these structured order quantity
columns:

| Workbook column | Header | App field |
| --- | --- | --- |
| `G` | `Поръчано Бруто /кг/` | `ordered_gross_kg` |
| `H` | `Поръчани ролки /бр./` | `ordered_rolls` |
| `I` | `Поръчани метри /м/` | `ordered_meters` |
| `J` | `Поръчани бройки /бр./` | `ordered_units` |

The relevant route fields are:

| Workbook column | Header / source meaning | App field |
| --- | --- | --- |
| `Q` | printing route sequence | `printing_sequence` |
| `R` | extrusion route sequence | `extrusion_sequence` |
| `S` | rewinding/slitting route sequence | `rewinding_slitting_sequence` |
| `T` | confection route sequence | `confection_sequence` |

The relevant extrusion fields are:

| Workbook column/source | Header / source meaning | App field |
| --- | --- | --- |
| `C` | `Дата на доставка` | `delivery_date` |
| `AE` | `фалдиране` | `extrusion_folding` |
| route calculation | next operation after extrusion, or blank if final | `extrusion_next_operation` |
| `AF` | `третиране` | `extrusion_treatment` |
| `AH` | `Cуровина А` | `raw_material_a` |
| `AI` | `Суровина B` | `raw_material_b` |
| `AJ` | `Суровина C` | `raw_material_c` |
| `AK` | `линеен РЕ` | `linear_pe` |
| `AL` | `антистатик` | `antistatic` |
| `AM` | `мастербач` | `masterbatch` |
| `AN` | `креда` | `chalk` |
| `AO` | `начин на опаковка` | `packaging_method` |

The workbook uses numeric route sequencing in `Q:T`. The export macro requires
`extrusion_sequence` / `Database!R` to be `1` for terminal export.

## Export Validation Rules

The corrected export macro is expected to enforce these rules before writing
CSV:

- export must be run from `Database` with a range selection containing at least
  one production-order row;
- exported order numbers must be nonblank and unique within the selected rows;
- `Database!Q:T` must contain a valid numeric route: whole-number sequences from
  `1` through `4`, unique and contiguous from `1`;
- `Database!R` must equal `1`, making extrusion the first operation;
- if confection is scheduled, it must be the final operation;
- `Database!G` / `ordered_gross_kg` must contain a positive numeric value;
- at least one exportable extrusion-detail field in `AE`, `AF`, or `AH:AO`,
  excluding system column `AG`, must be populated;
- every populated recipe field in `AH:AN` must use exactly
  `Category; Material | N%`;
- every recipe material must exist in `RecipeCatalogExtrusion`;
- recipe percentages must be whole numbers from `1` through `100` and total
  exactly `100%`;
- the required `Database` and `RecipeCatalogExtrusion` sheets and expected
  recipe-catalog structure must exist before export.

## Resolved Pre-Update Mismatch

Before this correction, the app used two generic quantity/unit pairs and a
yes/no extrusion flag. That model could not represent the structured G:J order
values or the numeric Q:T route values correctly.

The active importer, storage, release rules, admin pages, and terminal now use
the final structured fields. Old physical SQLite columns may still exist in
legacy databases, but they are not active import, edit, display, or target-gross
sources.

## Implemented App Behavior

- The exact 29-column header is mandatory in exact order. Aliases, extra
  columns, missing columns, and reordered columns are rejected.
- `ordered_gross_kg` is the only target-gross source.
- `extrusion_sequence == "1"` is the only import-eligibility signal. A
  sequence-1 row may import with blank extrusion detail and recipe fields.
- Positive target gross and recipe completeness remain independent release
  validations.
- Admin import results link successful rows to their current card.
- Admin planning and card lists show compact ordered-gross information; the
  cards list also shows delivery date.
- Admin card detail edits the four structured ordered values. The four imported
  route-sequence values remain stored and preserved but are intentionally hidden
  because they are not actionable there.
- The admin extrusion subsection contains `Фалдиране`, `Следваща операция`, and
  `Третиране`; packaging is in the order subsection.
- Terminal selected-card details show the accepted two-row layout: company,
  ordered gross, product type, size/thickness, and folding on row one; product
  form, next operation, treatment, and packaging on row two.
- Terminal details do not show ordered rolls, ordered meters, ordered units,
  delivery date, material, or maximum roll weight.
- Active queue rows show ordered gross only. Produced-history rows show actual
  produced gross only.
- Maximum roll weight is absent from active UI/request/save/release behavior.
  The legacy `cards.max_roll_weight` column remains inert.
- Terminal cancellation, restore, and print controls remain absent.

## Final Export Direction

The workbook export writes the corrected canonical ordered-amount fields:

```text
ordered_gross_kg,ordered_rolls,ordered_meters,ordered_units
```

with these source mappings:

```text
ordered_gross_kg <- Database!G
ordered_rolls    <- Database!H
ordered_meters   <- Database!I
ordered_units    <- Database!J
```

It also exports the numeric route fields:

```text
printing_sequence           <- Database!Q
extrusion_sequence          <- Database!R
rewinding_slitting_sequence <- Database!S
confection_sequence         <- Database!T
```

The app accepts this corrected extract only and does not expect or accept an old
extrusion flag.

## Migration And Task 6 Verification Record

- The ordered migration runner records versions in `schema_migrations` and
  applies each migration inside the caller transaction with savepoint rollback.
- M001 adds the eight final ordered/route columns to `cards` and
  `card_import_sources` without copying or inferring legacy values.
- Production rolls, timing, tare, status, assignment, queue, actual material,
  version, and timestamps remain unchanged.
- A later production profile must decide whether any legacy values can be
  converted safely. M001 deliberately performs no such conversion.
- Task 6 verification ran:

  ```bash
  .venv/bin/python -m compileall app scripts tests
  .venv/bin/python -m pytest -q
  git diff --check
  ```

  `compileall` and the diff check passed; the full suite reported **485
  passed**.
- The live FastAPI verification used the fresh temporary database
  `.test-runtime/v2-final.roRhVV/extrusion_terminal.sqlite3`, with no access to
  `data/extrusion_terminal.sqlite3`. The current V14.04 export imported 3 of
  3 rows: 3 imported, 3 created, 0 skipped.
- Orders 25450-25452 were released to machine 1 in sequence positions 1-3.
  The live workflow covered terminal production entry through completion and
  an admin production correction.
- Admin print produced exactly two A4 pages. The browser screenshots and PDF
  evidence are under `artifacts/ui-checks/v2/final/`.
- The only recorded migration is M001. No later migration was added, and no
  production database was opened or modified.
