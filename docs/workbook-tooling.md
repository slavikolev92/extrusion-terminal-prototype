# Production Workbook Tooling

The Shift Manager workbook tooling has been moved out of this repository.

Repository:

```text
https://github.com/slavikolev92/production-workbook-tooling
```

This `extrusion-terminal` repository owns the workstation/admin web app runtime:
CSV import, planning/release, terminal production execution, corrections, and
printing.

The `production-workbook-tooling` repository owns the Excel workbook side:
workbook inspection, recipe-builder macros, export-validation macros, native
workbook helper macros, actuals-capture experiments, and related interim
costing/workbook process planning.

Real Shift Manager workbook files may contain production and customer data and
should remain local-only. Do not commit workbook binaries to this app repo.
