# Recipe Catalog - Needs Review

Status: review workspace. Nothing in this file should be pasted into the active
`RecipeCatalogExtrusion` sheet until the open issue is resolved.

This file is intentionally not a dump of every old Marco workbook value. The
Marco workbook is legacy evidence. Most values there are percentages, ratios,
blend shorthand, color shorthand, or incomplete material names. The catalog
itself should be invoice-led, as stated in
`interim-costing-process/interim-naming-convention-report.md`.

## Catalog Decisions

These are real extrusion catalog candidates, but they are not yet paste-ready.
Use this section as the invoice/warehouse review checklist. The macro catalog
needs exactly this final shape:

```text
Category | Producer | GradeCode | Notes
```

| Candidate | Current information | Missing information to look for | Where to look | Promote when |
| --- | --- | --- | --- | --- |
| `Masterbatch Black` | Category is `Masterbatch`; color is black. Current invoice name is generic: `Мастербач - ЧЕРЕН`. | Producer/brand and commercial grade/code. Also confirm whether this is distinct from `Polibach Black 7200`. | Original invoice detail, supplier name, bag label, masterbatch COA, warehouse stock label. | We can identify a specific row such as `Masterbatch [Producer] [Black grade/code]`, or confirm it maps to an existing active row. |
| `Filler Vietnam 80-41` | Category is `Filler`; code-like value is `80-41`; invoice text is `ФИЛЕР - Виетнам-80-41`. | Whether `Vietnam` is producer, brand, origin, or just description. Need actual producer/brand if available. | Supplier invoice line, import documents, bag label, COA/spec sheet, supplier email. | We can fill `Producer` and `GradeCode`; for example `Filler [Producer] 80-41`. |
| `Crodamide / Кродамид` | Product family is a slip/additive family. Online evidence shows grades such as `Crodamide ER`, but Marco only says `Кродамид`. | Exact grade/code used in production: ER, E, VRX, another Crodamide grade, or a different successor brand such as Optislip. | Additive bag label, purchase invoice, supplier documentation, COA/SDS. | We can identify the exact grade/code and choose the category, probably `Slip` or another approved additive category. |
| `Ampacet` | Producer/brand is probably `Ampacet`; Marco has only percentage plus producer name. | Exact product code/grade and additive family: color masterbatch, white masterbatch, antiblock, UV, processing aid, etc. | Ampacet invoice line, bag label, COA/SDS, supplier product sheet. | We can fill both `Category` and `GradeCode`, for example `Masterbatch Ampacet [grade]` or `UV Ampacet [grade]`. |
| `Schulman` | Producer/brand is A. Schulman / POLYBATCH / LyondellBasell family. Marco has only `Schulman` with percentages. | Exact product name/code and additive family. | Old invoice line, bag label, COA/SDS; look for `POLYBATCH`, `A. Schulman`, or `LyondellBasell`. | We can identify a specific grade/code and category. |
| `CONSTAB GER generic` | Producer/brand is likely `CONSTAB`; one specific row, `CONSTAB AT 04673 LD`, is already resolved as antistatic. | Exact CONSTAB grade/code for the generic Marco entries. | CONSTAB/Kafrit invoice, bag label, COA/SDS. | We can identify a specific code such as `AT ...`, `UV ...`, `PA ...`, `AB ...`, etc. |
| `KJ` | Marco shows frequent `KJ` shorthand, but online research did not establish a reliable material identity. | Full material name: producer/brand, grade/code, and what additive family it belongs to. | Ask shift manager/operator what `KJ` meant; check old invoices around orders where `KJ` appears; check bags or stock labels. | We can translate `KJ` into a real commercial material row, or decide to ignore it as unusable shorthand. |

## Review Priority

Start with items that likely affect many recipes or are easy to identify from
physical stock:

1. `KJ` - appears frequently in Marco recipe fields, but currently has no
   reliable identity.
2. `Ampacet`, `Schulman`, and `CONSTAB GER generic` - likely real additives,
   but need exact grade/code.
3. `Crodamide / Кродамид` - likely real slip additive, but needs exact grade.
4. `Filler Vietnam 80-41` and `Masterbatch Black` - invoice evidence exists,
   but producer/grade is incomplete.

## Useful Marco Evidence

Marco `Database!AM:AS` is useful for finding aliases and high-frequency
shorthand that shift managers already use. It is not useful as a raw checklist
of catalog rows.

| Useful signal from Marco | How to use it |
| --- | --- |
| `LDPE тв.- румънско B20/03`, `LDPE тв.румънскоB20/03` | Alias evidence for `LDPE Midilena B20/03`. |
| `LDPE тв.румънскоB21/05` | Alias evidence for `LDPE Midilena B21/05`. |
| `LDPE тв.- румънско B22/07`, `LDPE тв.румънскоB22/07` | Alias evidence for `LDPE Midilena B22/07`. |
| `LDPE тв.- Sabik HP0722NN` | Alias/spelling evidence for `LDPE SABIC HP0722NN`. |
| `LDPE тв.- Sabik HP 2100`, `Sabik 2100 48.5%` | Alias/spelling evidence for `LDPE SABIC 2100N0 W`; do not treat percentage text as part of the item. |
| `LDPE тв.- Exxon 165BW1`, `ExxonMobile LD165 BW1` | Alias evidence for `LDPE ExxonMobil LD 165BW1`. |
| `LDPE тв.- DAW 1200 E`, `DAW1200 E` | Alias/spelling evidence for `LDPE DOW 1200E`. |
| `LDPE тв.- PETILEN G03-21`, `LDPE тв.- PETILEN G03-21Т` | Alias evidence for `LDPE Petilen G03-21T`. |
| `LDPE тв.- PETILEN G03-5`, `LDPE тв.- Petkim G03` | Alias evidence around Petilen/Petkim names; use the report-approved canonical rows, not the raw workbook spellings. |
| `20% - Лотрен Q1018H` | Alias evidence for `LLDPE Lotrene Q1018H`; remove percentage before mapping. |
| `20%-Ciplas 1118 F` | Alias evidence for `LLDPE Ciplas 1118F`; remove percentage before mapping. |
| `2 % Ampacet`, `1 % Ampacet`, `Schulman`, `Constab Ger`, `KJ`, `Кродамид` | Useful evidence that these additive families appear in recipes, but not enough by itself to create catalog rows without commercial producer/grade confirmation. |
| `син`, `зелен`, `бял`, `черен`, `Бяло` | Color/additive shorthand. Use only as alias evidence after mapping to a reviewed masterbatch row. |
| `GREEN 51817` | Resolved to `Masterbatch Plastika Kritis Green 51817` in the active candidate file. |
| `SAS анти-слип` | Resolved to `Antislip POLYBATCH SAS` in the active candidate file. |
| `0.01`, `0.02`, `0.03`, `0.2`, `0.25`, `1.5 кг./торба`, `5 %`, `20% без добавки`, ratios such as `50 % : 50 %` | Not material identities. These should not be reviewed as catalog materials. |

## Explicitly Ignored As Catalog Rows

The old workbook contains many rows that should not become catalog-review tasks:

- pure percentages;
- ratio instructions;
- bag-count shorthand;
- column placeholders such as `Суровина A/B/C`;
- generic words like `твърдо`, `меко`, `линеен PE`;
- colors without a producer/grade;
- operational notes such as `без добавки`.

These values may matter for interpreting old recipes, but they are not raw
material identities for the new recipe-builder dropdown.
