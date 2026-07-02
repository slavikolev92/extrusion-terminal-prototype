# Workbook Inspection For Actuals Capture

Status: discovery note for Excel Actuals Capture V1 planning.

Inspection date: 2026-07-02.

Scope: real workbook files under
`interim-costing-process/source-evidence/workbooks/`.

Method: read-only ZIP/XML inspection of `.xlsx` / `.xlsm` files with Python
standard-library code, followed by a read-only subagent audit using the
repo-local `.venv/bin/python`, `openpyxl 3.1.5`, and raw workbook XML where
useful. The initial inspection used `/usr/bin/python`, where `openpyxl` was
not installed; later workbook inspection should use `.venv/bin/python`. The
workbooks were not opened in Excel and were not saved or modified.

User clarification added after the initial inspection: V1 rules should not be
applied to all historical rows in `Database`. Each shift-manager workbook will
have a configured cutoff row and cutoff production order ID. Rows/orders after
that cutoff are expected to follow the normalized values and nomenclature. In
addition, some specific pre-cutoff production orders may need to be included in
Actuals Entry/Review/Validation for the current month; those inclusions should
be identified by exact row and production order ID.

Approved defaults for implementation planning:

1. Store cutoff and explicit inclusion configuration in `ActualsConfig` as
   simple helper tables.
2. Validate only the configured included row set. Duplicate production order
   numbers inside that included set are hard validation errors.
3. Use a workbook-local master installer that requires all managed bundle files,
   replaces managed code, preserves itself, installs in fixed order, and stops
   before changing anything if required files are missing.
4. Homogenize native workbook macros to one shared Marko-based standard for
   both shift-manager workbooks.

## Workbook Inventory

| File | Extension | Size | Modified | Macro-enabled? | Notes |
| --- | --- | ---: | --- | --- | --- |
| `raw-materials-for-naming-convention.xlsx` | `.xlsx` | 68,121 bytes | 2026-06-30 12:21 | No | Raw-materials evidence workbook, not a shift-manager order workbook. |
| `Поръчки-2026-Елена.xlsm` | `.xlsm` | 1,997,008 bytes | 2026-07-02 09:37 | Yes, contains `xl/vbaProject.bin` | Real shift-manager workbook. |
| `Поръчки-2026-Марко.xlsm` | `.xlsm` | 1,196,000 bytes | 2026-07-02 09:37 | Yes, contains `xl/vbaProject.bin` | Real shift-manager workbook. |

No obvious duplicate, backup, or temporary workbook files were present in this
folder. The two `.xlsm` workbooks appear to be separate shift-manager books,
not backups of each other.

## Sheet Inventory

### `raw-materials-for-naming-convention.xlsx`

| Sheet | Visibility | Used range | Notes |
| --- | --- | --- | --- |
| `Sheet3` | Visible | `A1:Q498` | No macros, no filters, no tables, no protection, no merged cells. |

### `Поръчки-2026-Елена.xlsm`

| Sheet | Visibility | Used range | Notes |
| --- | --- | --- | --- |
| `Database` | Visible | `A1:BO8171` | AutoFilter on `A4:AT8171`; frozen panes at row 4 / column A; 20 merged header ranges; row 1 hidden; no sheet protection; no tables; no data validation rules. Actual nonblank data only extends through `AT`. |
| `Technology Cards` | Visible | `A1:BD106` | 310 merged ranges; no sheet protection; has drawing/VML button artifacts for print macros. |

Workbook structure protection was not present. No hidden or very hidden sheets
were detected. No external workbook links or ActiveX parts were detected.

### `Поръчки-2026-Марко.xlsm`

| Sheet | Visibility | Used range | Notes |
| --- | --- | --- | --- |
| `Database` | Visible | `A1:AT5313` | AutoFilter on `A4:AS5313`; frozen panes at row 4 / column A; 20 merged header ranges; row 1 hidden; no sheet protection; no tables; no data validation rules. |
| `Technology Cards` | Visible | `A1:BD106` | 310 merged ranges; no sheet protection; has drawing/VML button artifacts for print macros. |

Workbook structure protection was not present. No hidden or very hidden sheets
were detected. No external workbook links or ActiveX parts were detected.

## Database Sheet Reality

Both shift-manager workbooks use the exact sheet name `Database`.

The relevant structure is consistent:

- Row 1 contains numeric column helper values.
- Row 3 contains the main Bulgarian headers.
- Row 4 contains operation/recipe subheaders and should not be treated as a
  production-order row even though `A4` contains an order-looking number.
- Production data begins at row 5.
- Production order numbers are in column `A`.
- Customer/company is in column `D`.
- City is in column `E`.
- Product/type text is in column `F`.
- Gross ordered quantity is in column `G`, headed `Количество\nбруто КГ`.
- Operation flags are in `Q:T`:
  - `Q`: флексопечат / Printing
  - `R`: Екструдиране / Extrusion
  - `S`: Разролване / Rewinding / Slitting
  - `T`: Конфекция / Confection
- Existing helper macro target ranges exist:
  - `W:AD` are printing station columns, with row 4 labels `1` through `8`.
  - `AH:AN` are extrusion material columns, with row 4 labels `Cуровина А`,
    `Суровина B`, `Суровина C`, `линеен РЕ`, `антистатик`, `мастербач`,
    `креда`.

Additional columns that may matter for Actuals Review context or future
planning:

- `B`: order date.
- `C`: delivery date; Marko row 3 has `Дата  на доставка`, while Elena row 3
  lacks a visible `C` header.
- `P`: `Изработено количество`; contains historical produced-quantity text and
  should not be treated as V1 structured actuals storage.
- `U`: next operation.
- `V`: print cylinder size.
- `AE`: folding.
- `AF`: next operation.
- `AG`: differs between books; Elena row 4 is `7`, Marko row 4 is
  `третиране`.
- `AO`: packaging method.
- `AP`: product size.
- `AQ`: scraps.
- `AR`: folding.
- `AS`: packaging method.
- `AT`: ventilation holes.

Database merged header ranges in both workbooks include:

```text
B3:B4
C3:C4
D3:D4
E3:E4
F3:F4
G3:G4
H3:H4
I3:I4
J3:J4
K3:K4
L3:L4
M3:M4
N3:N4
O3:O4
P3:P4
Q3:T3
U3:AD3
AE3:AO3
AP3:AQ3
AR3:AT3
```

No `Database` tables were detected. Both `Database` sheets have AutoFilter and
frozen panes. Neither `Database` sheet is protected.

Additional `Database` facts from the deeper read-only audit:

- Both workbooks hide row `1`.
- No hidden columns were detected.
- No Excel data validation rules were detected.
- No Excel tables were detected.
- Elena has grouped/outlined helper areas including `W:AD` and `AF:AO`.
- Marko has grouped/outlined helper areas including `W:AO`.
- Elena has 273 legacy notes and 122 threaded comments, mostly on product cells
  such as column `F`; any future copy/rewrite operation must preserve them.
- Elena has one external mail hyperlink at `N19`.
- Marko has no detected comments, threaded comments, hyperlinks, or drawings
  on `Database`.
- No nonblank `Database` cells beyond `AT` were found in either workbook, even
  though Elena's persisted dimension extends to `BO`.
- Marko's AutoFilter range is `A4:AS5313`, excluding `AT` even though `AT` has
  header/value usage.

## Production Order And Quantity Counts

Counts below use row 5 onward only.

| Workbook | Production rows with `A` value | First order rows | Last order rows | Duplicate order examples |
| --- | ---: | --- | --- | --- |
| `Поръчки-2026-Елена.xlsm` | 8,165 | `3`, `3001`, `3002`, `3003`, `3004` | `15411`, `15412`, `15413`, `15414`, `15415` | `3004` appears twice; `3012` appears three times. |
| `Поръчки-2026-Марко.xlsm` | 5,309 | `20000`, `20001`, `20002`, `20003`, `20004` | `25356`, `25357`, `25358`, `25359`, `25360` | None detected in this file. |

Here, "duplicate order" means exactly two or more `Database` rows with the
same production order number in column `A`.

`Database!G` is the gross ordered quantity column, but values are not always
plain numeric kilograms.

| Workbook | Numeric-like `G` | Blank `G` | Non-numeric `G` | Example non-numeric values |
| --- | ---: | ---: | ---: | --- |
| `Поръчки-2026-Елена.xlsm` | 7,130 | 65 | 970 | `1т.`, `1 т.`, `50 кг`, `30 т.`, `4 х 20 кг`, `600 кг`, `1/2` |
| `Поръчки-2026-Марко.xlsm` | 5,132 | 158 | 19 | `40+40`, `2000+2000`, `100-200`, `150 кг.`, `4500+4500` |

Implication: V1 can read `Database!G` as the ordered gross context. The user
confirmed new normalized orders will have numeric `G` values, and historical
rows that matter for the current month will be normalized or explicitly
included. The implementation plan should therefore scope strict `G` validation
to the configured actuals population: post-cutoff rows/orders plus configured
pre-cutoff inclusions.

## Operation Flag Values In `Q:T`

The current actual flag convention is not exactly uppercase `Да`.

### `Поръчки-2026-Елена.xlsm`

| Column | Blank | `да` | `Да` | Other variant |
| --- | ---: | ---: | ---: | --- |
| `Q` Printing | 3,067 | 5,091 | 7 | None in data rows |
| `R` Extrusion | 6,320 | 1,776 | 68 | `да ` once |
| `S` Rewinding / Slitting | 6,686 | 1,477 | 2 | None in data rows |
| `T` Confection | 2,906 | 5,244 | 12 | `да ` three times |

### `Поръчки-2026-Марко.xlsm`

| Column | Blank | `да` | `Да` | Other variant |
| --- | ---: | ---: | ---: | --- |
| `Q` Printing | 4,676 | 629 | 4 | None in data rows |
| `R` Extrusion | 17 | 5,212 | 80 | None in data rows |
| `S` Rewinding / Slitting | 5,010 | 292 | 0 | `да ` seven times |
| `T` Confection | 4,091 | 1,214 | 4 | None in data rows |

Implication: V1 validation should treat operation flags by trimming whitespace
and comparing case-insensitively against Bulgarian `да`. Requiring exact `Да`
would reject most real expected-operation flags.

## Sample Data Conventions

Representative row examples:

```text
Елена row 8169:
A=15413
D=Хлебозавод АД
F=СПП плик 235/480/0.028 +40   УС  Типов 650 гр.
G=1
H=топче
Q=да
T=да
W=W
X=Y
Y=M
AB=K
AC=Р126
AD=Р 354

Елена row 8170:
A=15414
F=СПП плик 235/480/0.028 +40    УС Добруджа 650
G=1/2
Q=да
T=да

Марко row 5311:
A=25358
D=Пелети Атлантик Уей
F=ТСФ 960/0.09  + Репер
G=60
Q=да
R=да
W=W
AB=Black
AH=LDPE тв.- ExxonMobil 3529
AJ=HDPE  - 20 %
AK=20% -KJ
```

Historical data quality issues found before the configured cutoffs:

- lowercase `да` is the normal operation flag value;
- some flag cells include trailing spaces;
- ordered gross quantity may include units, fractions, ranges, or arithmetic
  expressions instead of a number;
- some production order numbers are duplicated in the Elena workbook;
- row 4 has an order-looking value in column `A` but is a header/control row;
- the visible column headers differ slightly between books, for example
  `Възложител` versus `Фирма` in column `D`.

The implementation plan should not let these old-row issues weaken validation
for the normalized V1 population. Instead, it should define the included row
set first, then apply the stricter V1 rules to that row set.

## Existing Sheet Name Collision Risks

These planned Actuals V1 sheets do not currently exist in either real
shift-manager workbook:

```text
Actuals Entry
Actuals Review
Actuals Validation
ActualsData
ActualsStatus
ActualsConfig
```

These existing helper sheets also do not currently exist in either real
shift-manager workbook:

```text
ExportConfig
RecipeCatalogPrinting
RecipeCatalogExtrusion
RecipeCatalog
```

The actuals installer can create the planned actuals sheets without immediate
sheet-name collision in the inspected workbooks.

## Existing Macro, Shape, And Button Artifacts

Both `.xlsm` workbooks contain existing VBA projects.

Both `Technology Cards` sheets contain drawing/VML button artifacts with labels:

```text
Флексопечат
Екструдиране
Разролване
Конфекция
```

Both workbooks show button macro references:

```text
[0]!Sheet5.PrintFlexprinting
[0]!Sheet5.PrintExtrusion
[0]!Sheet5.PrintRerolling
[0]!Sheet5.PrintConfection
```

VBA binary string inspection also found references to:

```text
Sheet5
PrintFlexprinting
PrintExtrusion
PrintRerolling
PrintConfection
ApplyDatabaseFilters
```

`Поръчки-2026-Марко.xlsm` additionally has export-related VBA strings such as:

```text
ExportFolderPath
ExportSelectedExtrusionOrdersCsv
ExportExtrusionOrders
EXPORT_FOLDER_NAME
DATABASE_SHEET_NAME
```

No `Worksheet_BeforeDoubleClick`, `RecipeBuilderInstaller`, `ExportValidation`,
or actuals-specific strings were detected through basic binary string search,
but this is not a full VBA source-code export.

The deeper audit also found:

- raw VBA binary strings containing `Worksheet_Change`;
- no detected `Workbook_Open` or `Auto_Open` strings;
- `Technology Cards` formulas use `VLOOKUP(Database!$A$4, Database!$A$5:...)`,
  so `Database!A4` is the selected/current order for the print-card workflow,
  not metadata;
- `Technology Cards` formulas reference up to `CJ` in Elena and `CE` in Marko;
- `Database` has one large conditional-formatting expression involving
  `VLOOKUP($A$4,$R$1,0)="Да"`;
- `Technology Cards` has one conditional-formatting rule on `G4:K5` checking
  for `FALSE`;
- protection style scan did not reveal meaningful unlocked/hidden style
  patterns while sheet protection is off.

Print area findings:

- Elena has no workbook defined print areas detected.
- Marko has a stale/broken `Database!#REF!` print area plus
  `'Technology Cards'!$A$1:$K$55`.

## Existing Native VBA Source Review

The real workbook VBA was extracted read-only with `olevba` into
`artifacts/vba-inspection/` for inspection. The workbook files were not opened
or saved.

Both shift-manager workbooks currently have the same VBA component set:

| Component | Workbook mapping | Procedures |
| --- | --- | --- |
| `ThisWorkbook` | workbook document module | empty |
| `Sheet7` | `Database` sheet document module | `Worksheet_Change`, `ApplyDatabaseFilters` |
| `Sheet5` | `Technology Cards` sheet document module | `Copy_MoveWS`, `FixPrintMargins`, `PrintFlexprinting`, `PrintExtrusion`, `PrintRerolling`, `PrintConfection` |

No standard `.bas` modules, class modules, UserForms, old export-tool modules,
or app/database-integration modules were present in either real workbook.

`Sheet7` / `Database` behavior:

- `Worksheet_Change` watches `C2,D2,F2`.
- It calls `ApplyDatabaseFilters`.
- `ApplyDatabaseFilters` filters:
  - delivery date on column `C` / field `3`;
  - firm/customer on column `D` / field `4`;
  - product/type on column `F` / field `6`.
- It disables events and screen updating while applying filters.

`Sheet5` / `Technology Cards` behavior:

- `Copy_MoveWS` copies `Technology Cards` to a new workbook and breaks Excel
  external links.
- `FixPrintMargins` sets narrow print margins, centering, and one-page fit.
- Four print macros print the operation-specific front range plus a back-side
  operational-card range:
  - `PrintFlexprinting`
  - `PrintExtrusion`
  - `PrintRerolling`
  - `PrintConfection`

Native VBA differences between the two real workbooks:

- Elena `ApplyDatabaseFilters` uses `Me.Range("A4:AT30000")`.
- Marko `ApplyDatabaseFilters` uses `Me.Range("A4:AX30000")`.
- Elena print macros use back-side range `AS56:BC106`.
- Marko print macros use back-side range `AS55:BC105`.
- The front-side print ranges are the same:
  - flexprinting: `A1:K55`;
  - extrusion: `L1:V55`;
  - rerolling: `W1:AG55`;
  - confection: `AH1:AR55`.

User decision after review: these differences should not create workbook-
specific macro branches. Marko's native macro behavior should be treated as the
canonical standard, and Elena should be homogenized to the same managed native
macro behavior during install/update:

- canonical filter range: `A4:AX30000`;
- canonical back-side print range: `AS55:BC105`;
- one shared native macro bundle for both shift-manager workbooks.

If Elena has a layout mismatch that prevents the shared macro behavior from
working, the installer/setup plan should either normalize the workbook shape or
document a required precondition. Do not design separate Elena and Marko macro
implementations for V1.

Native VBA installer implications:

- The future `shift-manager-native-macros.bas` bundle cannot be only a normal
  standard-module import if it needs to preserve current behavior exactly,
  because the current native code lives in sheet document modules.
- The master installer must write/install code into the `Database` and
  `Technology Cards` sheet code modules, or it must import standard-module
  procedures and leave sheet-module wrapper procedures that preserve the
  existing button/event entry points.
- Existing form-control buttons currently call sheet-code macros such as
  `[0]!Sheet5.PrintFlexprinting`. If the print procedures move to a standard
  module, the installer must retarget those button macro assignments.
- The safer compatibility direction is to keep thin sheet-code entry points for
  `Database.Worksheet_Change` and the four `Technology Cards` print macros, and
  route shared implementation into managed standard modules if needed.
- The installer should locate the target sheets by visible sheet names
  `Database` and `Technology Cards`, then update those sheet code modules. The
  inspected workbooks currently use codenames `Sheet7` and `Sheet5`, but the
  implementation should not depend only on those codenames.
- The native macro bundle should follow Marko's current ranges as the canonical
  standard and update both workbooks to that shared behavior.

## Compatibility With Existing Helpers

Findings from the existing helper code:

- `RecipeBuilderInstaller` uses `ThisWorkbook`.
- `RecipeBuilderInstaller` creates or preserves `RecipeCatalogExtrusion` and
  `RecipeCatalogPrinting`.
- `RecipeBuilderInstaller` rewrites the single
  `Database.Worksheet_BeforeDoubleClick` procedure and routes only:
  - `Database!W:AD`
  - `Database!AH:AN`
- `RecipeBuilderInstaller` requires trusted VBA project access because it
  creates UserForms and writes worksheet event code.
- `ExportValidation` uses `ActiveWorkbook`.
- `ExportValidation` creates or preserves `ExportConfig`,
  `RecipeCatalogPrinting`, and `RecipeCatalogExtrusion`.
- `ExportValidation` hides `ExportConfig`.
- `ExportValidation` does not install worksheet/workbook event handlers.

Confirmed future installer/update direction:

- There should be a fourth master installer macro used as the normal install
  and update entry point.
- The master installer should prompt the user to select the folder containing
  the known workbook-tool `.bas` files.
- It should recognize only these exact filenames:
  - `shift-manager-native-macros.bas`
  - `recipe-builder-installer.bas`
  - `export-validation.bas`
  - `actuals-capture-installer.bas`
- It should not import arbitrary `.bas` files from the selected folder.
- All four files are required for a full managed install/update. If any is
  missing, the master installer should stop before changing the workbook.
- For updates, it should remove known existing tool modules/forms/components
  before importing the new versions, so repeated installs do not stack duplicate
  modules.
- The master installer should preserve itself, then replace the managed native
  sheet-code and tool components from the bundle.
- If the master installer itself changes, the user may still need to import the
  updated master installer manually before running it; a running VBA module
  should not try to replace itself.

Coexistence implications:

- Actuals V1 should avoid `Database` worksheet events. Button-driven macros on
  actuals sheets are safer and avoid competing with the recipe-builder
  double-click owner.
- Actuals V1 should not create, rename, clear, hide, or re-header
  `RecipeCatalogPrinting`, `RecipeCatalogExtrusion`, `RecipeCatalog`, or
  `ExportConfig`.
- Actuals V1 sheet names are currently unique in both real workbooks.
- Because both inspected targets are end-user workbooks into which installer
  modules are imported, the actuals installer should target the workbook that
  contains the imported installer code. `ThisWorkbook` is safer after import,
  because it avoids accidentally installing into the wrong active workbook if
  multiple workbooks are open.
- If the actuals installer is ever run from a separate add-in or central
  installer workbook, the target-workbook strategy would need to change. That
  is not how the existing recipe-builder installer is documented.

Installation-order risks:

- Running Recipe Builder after any future installer that installs a
  `Database.Worksheet_BeforeDoubleClick` handler would overwrite that handler.
  Actuals V1 should not install one.
- Existing `Technology Cards` print buttons and macros should be preserved.
  Actuals V1 should create buttons only on its own sheets.
- Marko appears to contain older export-related VBA strings without the current
  `ExportConfig` helper sheet. The actuals plan should not assume export-helper
  installation state is uniform across workbooks.
- Existing `Technology Cards` formulas depend on `Database!A4`; actuals logic
  must not repurpose or clear `A4`.
- Marko's stale `Database!#REF!` print area should be preserved or deliberately
  ignored; actuals installation should not attempt unrelated print-area cleanup.
- The master installer must manage current native sheet code as part of the
  bundle, specifically `Database.Worksheet_Change` and the `Technology Cards`
  print/copy procedures.

## Implementation-Plan Facts To Use Later

- Target workbook shape is a real `.xlsm` workbook with visible `Database` and
  `Technology Cards` sheets.
- Production data starts at row 5.
- `Database!A` is the production order number.
- `Database!D` is customer/company.
- `Database!F` is product/type text.
- `Database!G` is the ordered gross quantity context, but it may be text.
- `Database!Q:T` are the expected-operation flags.
- Expected-operation flag parsing must trim and accept lowercase `да` as well
  as `Да`.
- Actuals V1 should operate on a configured included row set, not the entire
  historical `Database`: post-cutoff rows/orders plus exact pre-cutoff
  row/order inclusions supplied by the user.
- `W:AD` and `AH:AN` exist and are already aligned with the recipe/export
  helper assumptions.
- No planned actuals sheet names collide with current workbook sheets.
- No planned recipe/export helper sheets currently exist in the inspected real
  workbooks.
- Existing workbooks are not protected today; V1 protection will be newly
  introduced on actuals sheets if implemented.
- Existing print buttons live on `Technology Cards`; actuals should not alter
  that sheet.
- Actuals should be button-driven and should not depend on `Database` events.
- Actuals helper sheets should be hidden after creation, but the workbooks
  currently have no hidden sheets.
- `Database!A4` is part of the current print-card selection workflow and should
  be left alone.
- Avoid inserting columns into existing `Database` business/helper regions.
  Actuals V1 is already planned to store data outside `Database`; this remains
  the lower-risk direction.
- If any future macro copies rows or rewrites `Database` ranges, Elena comments
  and threaded comments must be preserved.

## Risks And Blockers

- The functional plan currently says a `Да` value means an operation is
  expected. Workbook reality shows lowercase `да` is dominant. Exact-match
  validation would be wrong.
- Historical `Database!G` is not reliably numeric. The plan should avoid
  validating all historical rows and should apply strict numeric checks only to
  the configured V1 included row set.
- Production order numbers are not guaranteed globally unique across the full
  historical workbook. Elena has duplicated order numbers. Actuals keyed only
  by production order may need a clear policy if duplicates appear in the V1
  included row set.
- Existing VBA source was not fully exported. Binary string search confirms
  relevant macro names but not full procedure bodies or workbook/sheet event
  code.
- Marko may already contain older export-related code, but not the current
  helper sheet structure. The implementation plan should include coexistence
  testing on both books.
- A `Worksheet_Change` string exists in the VBA project. The full VBA source
  should be reviewed before any installer changes that could interact with
  sheet events.

## Confirmed Assumptions

- The real workbooks are macro-enabled `.xlsm` files.
- The real workbooks contain `Database` exactly, not a renamed equivalent.
- The real workbooks have production order numbers in column `A`.
- The real workbooks use `Database!G` for gross ordered quantity context.
- The real workbooks use `Database!Q:T` for expected operation flags.
- The existing recipe-builder target ranges `W:AD` and `AH:AN` exist.
- The planned actuals sheet names are currently available.
- The workbooks have no workbook/sheet protection that would block installer
  sheet creation in the current files.

## Corrections Needed In `excel-actuals-capture-plan.md`

Do not edit the plan yet, but these corrections should be applied when the user
asks for the next planning pass:

- Replace the exact statement that `Да` means expected with a rule that trims
  the cell and treats Bulgarian `да` case-insensitively as expected.
- Clarify that `Database!G` is the ordered gross quantity source/context, and
  that strict numeric validation applies to the configured V1 included rows,
  not every historical row.
- Clarify that production data starts at row 5 and row 4 is an operation/header
  row even when `A4` contains an order-looking value.
- Add cutoff/inclusion configuration: each workbook needs a cutoff row and
  cutoff production order ID, plus optional exact pre-cutoff row/order
  inclusions.
- Add a duplicate-order-number policy for actuals lookup and save behavior if
  duplicates occur inside the configured V1 included row set.
- Note that current real workbooks do not yet contain the recipe/export helper
  sheets, and one workbook may contain older export-related code.
- Note that `Database!A4` is used by the current `Technology Cards` formulas as
  the selected order.
- Note that Marko has a stale `Database!#REF!` print area and a filter range
  ending at `AS` while `AT` exists.

## Remaining Questions Before Implementation Planning

1. What exact cutoff row and cutoff production order ID should be configured
   for each workbook?
2. Which exact pre-cutoff row/order pairs should be included in the V1 actuals
   population for the current month?
3. If a duplicate production order number appears inside the configured V1
   included row set, should V1 block it as ambiguous until the workbook is
   corrected, or should it identify orders by row number plus production order?
4. Should a future pass export/review the existing VBA project source before
   actuals installation testing, especially because `Worksheet_Change` and
   older export-related strings were detected?
