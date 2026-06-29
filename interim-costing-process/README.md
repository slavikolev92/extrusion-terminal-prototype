# Interim Costing Process

This folder contains the planning, source evidence, catalog review, and Excel
workbook tooling for the July 2026 interim costing process.

The goal is to start collecting clean forward-looking data from July 1, 2026 so
that interim costing can be performed after July 31, 2026.

## Folder Map

- `planning/` - active process plan, decisions, open tasks, and app requirements.
- `source-evidence/workbooks/` - source workbooks used as evidence during
  analysis. These are not app fixtures or runtime files.
- `naming-conventions/` - naming convention evidence, conclusions, and preview
  material.
- `catalog-review/` - reviewed catalog candidates and generated catalog
  workbooks.
- `excel-tools/recipe-builder/` - workbook controlled-entry tooling for
  extrusion recipes and printing ink/anilox entries.
- `excel-tools/export-validation/` - workbook validation and CSV export macro.

## Boundaries

The production actuals app should be designed separately from this folder. This
folder records the interim costing process and supporting artifacts; it is not
the app runtime directory.

Do not use the source-evidence workbooks as mutable test fixtures. Copies for
manual Excel checks should be kept in local ignored runtime folders.
