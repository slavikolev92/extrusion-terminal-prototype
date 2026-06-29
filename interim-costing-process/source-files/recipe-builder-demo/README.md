# Recipe Builder

This folder documents the accepted Excel-side controlled-entry design for the
shift-manager workbook.

The goal is to keep the existing workbook and the existing `Database` sheet
structure, while making structured entry hard to mistype.

The installer owns one `Database` double-click event and routes by column range:

- `AB:AI` - printing ink/anilox builder.
- `AM:AS` - extrusion raw-material builder.

## Why This Changed

The first accepted design only handled extrusion raw materials in `AM:AS`. We
then agreed to add the same controlled-entry mechanism for printing ink stations
in `AB:AI`, but with a simpler convention:

```text
Ink / Color Identity
Ink / Color Identity/Anilox lines/cm
```

The installer was extended instead of creating a second installer because there
can only be one clean `Worksheet_BeforeDoubleClick` procedure on the `Database`
sheet. If separate installers each tried to manage that event, they would
overwrite each other or create duplicate/ambiguous VBA procedures. One installer
now owns the event and routes by cell range.

The extrusion helper sheet was also renamed from the earlier generic
`RecipeCatalog` name to `RecipeCatalogExtrusion`, because printing now has its
own catalog. The installer preserves existing extrusion catalog rows by renaming
an old `RecipeCatalog` sheet to `RecipeCatalogExtrusion` when needed.

Current workbook helper sheets:

```text
RecipeCatalogExtrusion
RecipeCatalogPrinting
```

## Extrusion Builder

Extrusion recipe cells use:

```text
[Material Category] [Producer] [Grade / Code] | [% of final product]
```

Example:

```text
LDPE Midilena B20/03 | 77%
```

If a reviewed catalog item genuinely has no producer or no grade/code, enter
`N/A` in that helper-sheet field. `N/A` is a control value: it is valid in
`RecipeCatalogExtrusion`, but it is not printed in the final recipe cell.

Example catalog row:

```text
reLDPE | N/A | N/A | approved recycled LDPE without stable producer/grade
```

Output:

```text
reLDPE | 80%
```

The extrusion form opens when the user double-clicks `Database!AM:AS`. It has:

- `Material Category`
- `Producer`
- `Grade / Code`
- `Percentage`
- read-only preview
- `Insert` / `Cancel`

The dropdowns cascade:

1. Choosing `Material Category` filters the available producers.
2. Choosing `Producer` filters the available grades/codes.
3. Entering `Percentage` updates the preview.
4. `Insert` writes one canonical value into the original cell.

## Printing Builder

Printing ink station cells use:

```text
[Ink / Color Identity]
[Ink / Color Identity]/[Anilox lines/cm]
```

Examples:

```text
White
Pantone 485/110
Black/255
```

The printing form opens when the user double-clicks `Database!AB:AI`. It has:

- `Find Ink / Color`
- matching ink list
- `Anilox Roller`
- read-only preview
- `Insert` / `Cancel`

The ink selector uses a search box plus a filtered matching list. This avoids
the weak Excel UserForm dropdown scrollbar behavior: the user types part of the
ink/color identity, then chooses the matching controlled value from the list.
The anilox value remains a simple dropdown because that list is short.

`Ink / Color` is required. `Anilox Roller` is optional. The anilox dropdown
includes a blank choice; choosing the blank value writes only the ink/color name.
If an anilox value is selected, the builder writes it after a slash with no
spaces.

The printing form is arranged as two equal-width columns. The left column is for
finding and selecting the ink, with a taller matching-inks list so many more
filtered rows are visible at once. The right column is for the anilox roller,
preview, and action buttons.

The workbook-facing printing convention intentionally does not include ink
supplier or product code. Supplier/product-code mapping remains outside this
form unless the process later changes.

## Helper Sheets

The installer creates or preserves two helper sheets.

### `RecipeCatalogExtrusion`

This is the controlled list used by the extrusion dropdowns:

```text
Category | Producer | GradeCode | Notes
```

Example rows:

```text
LDPE        | Midilena | B20/03        | optional note
LDPE        | Midilena | B20/07        | optional note
LLDPE       | SABIC    | 119ZJ         | optional note
Masterbatch | Polibach | White 8000 ET | optional note
reLDPE      | N/A      | N/A           | approved omission
```

Recommended extrusion rules:

- keep `Category`, `Producer`, and `GradeCode` filled in;
- use `N/A` for `Producer` or `GradeCode` only when the missing value is an
  approved intentional omission;
- blank cells still mean incomplete catalog data;
- `N/A` is not printed in the final recipe cell;
- do not put percentages in the catalog, because percentages are order-specific.

If an older workbook already has `RecipeCatalog` and does not yet have
`RecipeCatalogExtrusion`, the installer renames `RecipeCatalog` to
`RecipeCatalogExtrusion` to preserve existing catalog rows.

### `RecipeCatalogPrinting`

This is the controlled list used by the printing dropdowns:

```text
Type | Value | Notes
```

Use `Type = Ink` for ink/color identities and `Type = Anilox` for anilox roller
values.

Example rows:

```text
Ink    | White       |
Ink    | Pantone 485 |
Ink    | Black       |
Anilox | 110         |
Anilox | 220         |
Anilox | 240         |
Anilox | 255         |
Anilox | 300         |
```

Recommended printing rules:

- `Type` must be either `Ink` or `Anilox`;
- `Value` must contain the exact dropdown value to show;
- ink values should be canonical English color identities, not suppliers;
- anilox values should be numeric lines/cm values;
- leave `Notes` blank for the current prototype.

## Files

- `README.md` - this explanation and operating guide.
- `modRecipeBuilderCascadingInstaller.bas` - installer module. It creates or
  preserves helper sheets, creates the extrusion and printing UserForms, and
  installs the double-click router.

No catalog spreadsheet is stored in this folder. Catalog data is controlled
inside the installed workbook helper sheets.

## Install In A Workbook

1. Open the target workbook, or use a copy first if testing installation.
2. Press `Alt+F11` to open the VBA editor.
3. Remove older recipe-builder modules/forms if duplicate-name errors exist.
4. Use `File > Import File...` and import:
   - `modRecipeBuilderCascadingInstaller.bas`
5. Run this macro:
   - `InstallRecipeBuilderV2`
6. Save the workbook as `.xlsm`.
7. Fill or paste reviewed catalog rows into the helper sheets.
8. Return to Excel and double-click a supported `Database` cell.

If a catalog sheet has only headers and no rows, the related form will open but
the dropdowns will be empty. That is expected.

## Updating Catalogs

The installation and catalog data are separate.

Install the mechanism once:

- `modRecipeBuilderCascadingInstaller.bas`
- `InstallRecipeBuilderV2`

Then maintain catalog content by editing or pasting rows into:

- `RecipeCatalogExtrusion`
- `RecipeCatalogPrinting`

You do not need to reinstall the macro just to update catalog rows.

If the installer is rerun later to update forms or double-click behavior, it
preserves existing catalog rows and only ensures the header rows exist.

## Required Excel Setting

The installer creates forms and a worksheet event inside the workbook. Excel may
block that unless this setting is enabled:

```text
File > Options > Trust Center > Trust Center Settings > Macro Settings >
Trust access to the VBA project object model
```

If the setting is off, the installer will still create/preserve helper sheets,
then show a warning that form/event installation was blocked.

After the installer has successfully run, this setting can be turned off again.
Normal use of the builders does not require ongoing access to the VBA project
object model.

## Relationship To Validation

These builders are data-entry aids, not the final validation gate.

The final validation should still happen when exporting/importing workbook data
into the app. The builders reduce mistakes before export by making the correct
format the easiest way to enter materials and printing stations.
