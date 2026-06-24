# Interim Naming Convention Report

Status: evidence and conclusions report.

Created: 2026-06-23.

Purpose: collect the source evidence behind the interim naming conventions for
costing inputs before the ERP rollout.

This file is not the central plan. Open questions, open decisions, and active
tasks are tracked in `interim-costing-process-plan.md`.

Source files inspected:

- `source-files/raw-materials-for-naming-convention.xlsx`
- `source-files/PO-OC - Elena.xlsm`, `Database` worksheet
- `source-files/PO-OC - Marco.XLSM`, `Database` worksheet

The naming work should be discussed in four separate tracks:

1. Extrusion raw materials.
2. Inks.
3. Solvents.
4. PP purchased film.

## 1. Extrusion Raw Materials

Status: naming convention approved. Conceptual discussion closed.

### Costing Role

Extrusion recipe materials are needed for order/product material-cost
calculation.

The forward-looking workbook convention is already settled:

```text
Material Name | %
```

Column role is supplied by the workbook column:

| Column | Role |
| --- | --- |
| `AM:AP` | Base polymer slots |
| `AQ:AS` | Additive/filler slots |

Base polymer percentages in `AM:AP` should sum to `100%`. Additives and fillers
in `AQ:AS` are percentages over the base blend.

### Invoice Evidence

The invoice workbook already classifies many extrusion-relevant items more
cleanly than the shift-manager workbooks.

Relevant invoice classifications:

| Invoice subcategory | Records | Distinct item names | Invoice item types |
| --- | ---: | ---: | --- |
| `Polymers & Resins` | 63 | 35 | `LDPE`, `LLDPE`, `MDPE`, `reLDPE` |
| `Additives & Masterbatches` | 20 | 12 | `Antistatic`, `Masterbatch` |

Observed polymer/resin invoice names:

- `LDPE 165 BW1`
- `LDPE DOW 1200E - NTP - полиетилен`
- `LDPE HIPTEN F22003`
- `LDPE LD150BW`
- `LDPE LD165BW1 / ExxonMobil LD 03322.BW1`
- `LDPE SABIC 2100N0 W`
- `LDPE SABIC 2100N0 W /MFR 0.3 no adds`
- `LDPE SABIC HP0722NN MFI 0.75 1500KG/Pallet`
- `MIDILENA PE B 20/03 - полиетилен`
- `MIDILENA PE B 20/03 - полиетилен (LDPE)`
- `MIDILENA PE B 20/07 - полиетилен`
- `MIDILENA PE B 21/05 - полиетилен`
- `MIDILENA PE B 22/07 - полиетилен`
- `MIDILENA PE B 22/07 - полиетилен (LDPE)`
- `MIDILENA PE В 22/07 - полиетилен`
- `NEXXSTAR 00328/ExxonMobil LD 03529 ПЕВН`
- `PETKIM LDPE G03-5 - полиетилен`
- `PETKIN LDPE G03-5 - полиетилен`
- `ПЕВН PETILEN G03-21T`
- `ПЕВН PETILEN G03-21T (LDPE)`
- `LLDPE - 118 - B8`
- `LLDPE - BOREALIS FB4230`
- `LLDPE C4 LL1001AV`
- `LLDPE CIPLAS 1118F`
- `LLDPE CIPLAS 1121F6 (линеен полиетилен)`
- `LLDPE CIPLAS 1121F6 - линеен полиетилен`
- `LLDPE Copap 118 - B8`
- `LLDPE SABIC 119ZJ`
- `LLDPE SHELL 18F1B`
- `LLDPE Shell 18F1B - линеен полиетилен`
- `LLDPE-SABIC 119ZJ`
- `Линеен ПЕВН LOTRENE Q1018H`
- `MDPE 3914`
- `ПЕВН (MDPE - ADVANCENE - EE-3914-AAH)`
- `LDPE регранулат натурален`

Observed additive/masterbatch invoice names:

- `Добавка Antistatic AT 04673 LD`
- `Добавка Антистатик АТ 04673 LD`
- `Мастербач - ЧЕРЕН`
- `Полибач бял 800 ЕТ`
- `Полибач бял 8000 ЕТ`
- `Полибач ВЛА 66`
- `Полибач ЛЦЦ 90`
- `Полибач оранж Л 1014`
- `Полибач син АГ Л 4535`
- `Полибач УВ 1952 натурален`
- `Полибач черен 7200`
- `ФИЛЕР - Виетнам-80-41`

### Shift-Manager Workbook Evidence

The `Database` recipe fields are not clean enough to become the naming catalog
directly.

Observed pattern by column:

- `AM` often contains material identities, but they are inconsistent and often
  include blend shorthand.
- `AN` and `AO` often contain additional materials, ratios, or percentages.
- `AP` often contains linear/metallocene/KJ shorthand and percentages.
- `AQ:AS` often contain additive percentages, bag-count shorthand, or color
  masterbatch shorthand.

Top observed `AM` values:

- `LDPE тв.- румънско`
- `LDPE тв.- 2420F3`
- `LDPE тв.`
- `LDPE тв.- PETILEN G03`
- `LDPE тв.- PETILEN G03-5`
- `LDPE тв.+меко 1/1`
- `LDPE тв.- 2420F8`
- `LDPE тв.-иранско L 2100 TN`
- `LDPE тв.- румънско B20/03`
- `LDPE тв.- Sabik HP0323NN`
- `95 % вторично`
- `LDPE тв.- PETILEN G08`
- `LDPE тв.- Exxon 165BW1`
- `LDPE тв. - Amir Kabir`
- `LDPE тв.- PETILEN G03-21`
- `LDPE тв.румънскоB21/05`
- `LDPE тв.- LOTRENE FE 8004`
- `LDPE тв.- 2420 F8`
- `LDPE тв.румънскоB20/03`
- `LDPE тв.- Sabik HP 2100`
- `LDPE тв.- румънско B22/07`
- `LDPE тв.- Lotrene FE300`
- `LDPE тв.- DAW 310`
- `LDPE тв.+меко 1/3`
- `LDPE тв.- Sabik HP0722NN`

Top observed `AN` values:

- `50 % : 50 %`
- `LDPE меко - B21/2- 1 част`
- `LDPE меко - B21/2`
- `DAW1200 E 40 %`
- `10 % вторично`
- `m-LLDPE - 79 %`
- `20 %- 2420F8`
- `50 % вторично`
- `2420F8 20 %`
- `1 % бяло`
- `20 % металоцен-Repsol`
- `20 % металоцен-Marlex`

Top observed `AO` values:

- `LDPE меко - B21/2`
- `LDPE меко -Sabic 2102 1 част`
- `20% - KJ`
- `1% - procesing`
- `UV- 1 %`
- `Marlex`
- `UV- 3 %`
- `1-2% - procesing`
- `10% - KJ`
- `Sabic 2102 N3W`

Top observed `AP` values:

- `20% без добавки`
- `20% -KJ`
- `20% KJ`
- `0.2`
- `20% - KJ`
- `20%- без добавки`
- `20% металоцен (Marlex)`
- `0.25`
- `1.5кг./торба - KJ`
- `25% Металоцен`
- `1.5кг./торба`
- `20%- KJ`
- `20%-KJ`
- `20% - Luban 7080`
- `Ethydco C6 20%`

Top observed `AQ` values:

- `0.01`
- `0.02`
- `2 % Ampacet`
- `1 % Ampacet`
- `2% - Schulman`
- `1% Schulman`
- `0.03`
- `2 % Schulman`
- `1% Ampacet`
- `2 %`
- `1% - сухия`
- `2% - 100098 - A`
- `1%`
- `1 %`

Top observed `AR` values:

- `син -1%`
- `Кродамид`
- `син -2-3 %`
- `UV-1%`
- `зелен`
- `син`
- `1 % SAS анти-слип`
- `1% SAS анти-слип`
- `бял`
- `Бял -3 %`
- `бял 1-3 %`
- `черен 1-2 %`

Top observed `AS` values:

- `5 %`
- `1.5 кг./торба`
- `0.05`
- `2-3 %`
- `1%`
- `10 %`
- `0.2`
- `2.5кг./торба`
- `кродамид`
- `2 %`
- `5 % креда`
- `5-6 %`

### Approved Naming Direction

The extrusion raw-material catalog should be invoice-led. Workbook values should
be treated as aliases that need mapping, not as canonical names.

Approved pattern:

```text
[Material Category] [Producer or Brand] [Full Commercial Grade/Code]
```

For PE raw materials, `Material Category` means the polymer family such as
`LDPE`, `LLDPE`, `MDPE`, or `reLDPE`.

For additives, `Material Category` means the additive family such as
`Antistatic`, `Masterbatch`, `Filler`, `Processing Aid`, or another accepted
additive category. Additives follow the same uniqueness logic as PE raw
materials: the accepted item identity is category/family, producer or brand, and
full commercial grade/code.

Melt-flow index, density, processing temperatures, food-contact status, additive
package, technical datasheets, and certificate values are item or lot
specification fields, not normal item-name components.

Recycled/regranulate, off-spec, non-prime, or trader-blended materials may need a
separate naming rule if they do not have a stable producer grade/spec.

Examples:

- `LDPE SABIC 2100N0 W`
- `LDPE SABIC HP0722NN`
- `LDPE ExxonMobil LD 165BW1`
- `LDPE DOW 1200E`
- `LDPE HIPTEN F22003`
- `LDPE Midilena B20/03`
- `LDPE Midilena B21/05`
- `LDPE Midilena B22/07`
- `LDPE Petilen G03-21T`
- `LDPE Petkim G03-5`
- `LLDPE LL1001AV`
- `LLDPE Borealis FB4230`
- `LLDPE Ciplas 1118F`
- `LLDPE Ciplas 1121F6`
- `LLDPE Copap 118-B8`
- `LLDPE SABIC 119ZJ`
- `LLDPE Shell 18F1B`
- `LLDPE Lotrene Q1018H`
- `MDPE 3914 / Advancene EE-3914-AAH`
- `reLDPE Natural Regranulate`
- `Antistatic AT 04673 LD`
- `Masterbatch Black`
- `Polibach White 800 ET`
- `Polibach White 8000 ET`
- `Polibach VLA 66`
- `Polibach LCC 90`
- `Polibach Orange L 1014`
- `Polibach Blue AG L 4535`
- `Polibach UV 1952 Natural`
- `Polibach Black 7200`
- `Filler Vietnam 80-41`

### Completed Conclusion

Use the following convention for PE raw materials and extrusion additives:

```text
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code]
```

This convention is approved as the ERP-compatible item identity rule for normal
PE raw materials and extrusion additives. Technical values such as melt-flow
index, density, processing temperatures, additive package, datasheets, and
certificate values are item or lot specification fields, not item-name
components.

### Catalog Cleanup Notes

The central plan tracks the remaining catalog decisions. Evidence issues
identified in this report:

- Producer and brand spelling/capitalization varies.
- Ambiguous invoice spellings include `PETKIM`, `PETKIN`, and `PETILEN`.
- `MDPE 3914` and `ADVANCENE EE-3914-AAH` may be aliases or separate materials.
- Recycled/regranulate entries may need a separate naming rule if no stable
  producer grade/spec exists.
- Old workbook values need aliases to canonical material names.

## 2. Inks

### Costing Role

Printing ink station values are needed to identify which ink/color was planned
for a printed order. Initial allocation uses ink/color identity. Anilox is
preserved for later refinement.

The forward-looking workbook convention is already settled:

```text
Color Identity | Anilox lines/cm
```

The station columns are `AB:AI`.

### Invoice Evidence

The invoice workbook has `Inks & Solvents` entries. Inside that group:

| Invoice item type | Records | Distinct names |
| --- | ---: | ---: |
| `Ink` | 158 | 80 |
| `Solvent` | 26 | 6 |

Observed ink invoice names:

- `Black DG Raster`
- `Cyan DG Raster`
- `FKD400W0000F БЯЛО`
- `Gecko GBT Pantone 168`
- `KPRB ПРОЦЕСНО СИНЬО`
- `MHD005Y2222 ЖЪЛТО`
- `MHD013R2222 МАГЕНТА`
- `MHD029S2222 ЧЕРНО`
- `MXD023B0000 РЕФЛЕКСНО СИНЬО`
- `MXD026B2222 ЦИАН`
- `MXD028G0000 ЗЕЛЕНО`
- `MXE100R0000 РУБИН РЕД`
- `MXK001O000 ОРАНЖ`
- `MXK001O0000 ОРАНХ`
- `MXK005R0000 ЧЕРВЕНО 485 C`
- `MXK032B0000 СИНЬО 072`
- `MXK3282G0000 ЗЕЛЕНО`
- `MXK362G0000 ЗЕЛЕНО`
- `Pantone Magenta; GBT; рубин мастило`
- `Pantone Red 35/485; GBT; червено мастило`
- `Pentone Red 35/485 (червено мастило)`
- `Yellow DG Raster`
- `Бяла боя (FKD400W0000F)`
- `БЯЛО`
- `Бяло`
- `Виолет`
- `ВИОЛЕТ`
- `Жълта боя (MHD005Y2222)`
- `ЖЪЛТО`
- `Жълто`
- `Жълто мастило`
- `ЖЪЛТО СВЕТЛОУСТОЙЧИВО`
- `Зелена боя (МXD028G0000)`
- `ЗЕЛЕНО`
- `Зелено`
- `ЗЕЛЕНО P.2427`
- `Зелено мастило`
- `ЗИАН`
- `ЗЛАТО 873`
- `КАФЯВО`
- `Кафяво`
- `КАФЯВО P.4104`
- `КАФЯВО p.4104`
- `МАГЕНТА`
- `Магента`
- `Магента боя (MHD013R2222)`
- `ОРАНЖ`
- `Оранж`
- `ПАНТОН ЗЛАТО 871`
- `Пантон Злато 871`
- `Розов`
- `РОЗОВ`
- `Рубин мастило`
- `РУБИН РЕД`
- `Рубин Ред`
- `СВЕТЛОУСТОЙЧИВА МАГЕНТА`
- `Синьо`
- `СИНЬО 072`
- `Синьо мастило`
- `Синьо мастило (Cyan)`
- `Синьо мастило (Pantone Blue)`
- `Топло червено`
- `ТОПЛО ЧЕРВЕНО`
- `Топло червено мастило`
- `ФЕРШНИТ`
- `Фершнит`
- `Циан`
- `ЦИАН`
- `Циан боя (MHD026B2222)`
- `Червено`
- `ЧЕРВЕНО 485`
- `ЧЕРВЕНО 485 В`
- `ЧЕРВЕНО 485 С`
- `Червено 485С`
- `Червено мастило`
- `червено мастило`
- `Черна боя (MHD029S2222)`
- `Черно`
- `ЧЕРНО`
- `Черно мастило`

### Shift-Manager Workbook Evidence

Legacy `AB:AI` values combine ink/color identity with anilox values in many
formats. There were 559 distinct non-empty legacy ink station strings across
Elena and Marco's current workbooks.

Common raw workbook variants:

- `W`
- `W/110`
- `W /110`
- `W 110`
- `Y`
- `Y/255`
- `Y/220`
- `Y /240`
- `Y 255`
- `M/255`
- `M/300`
- `М /255`
- `C/255`
- `C/300`
- `С/255`
- `K`
- `К`
- `Black`
- `K/110`
- `K/255`
- `Black 110`
- `Black 255`
- `Р 485`
- `P 485`
- `Р 485/110`
- `P 485/110`
- `110 / 485`
- `Р 137`
- `Р 137/110`
- `Р 021`
- `Р 021/110`
- `Р 072`
- `Р 122`
- `Р 122/110`
- `Р 483`
- `Р 483/110`
- `злато`
- `злато/110`
- `R.Blue/110`
- `Ref. blue`
- `Р 871`
- `Р871`

Frequent normalized legacy ink/color identities:

| Identity | Approx. observed station entries | Common variants |
| --- | ---: | --- |
| `White` | 6345 | `W`, `W/110`, `W 110`, `W /110` |
| `Black` | 4770 | `K`, `К`, `Black`, `K/110`, `Black 255` |
| `Yellow` | 3676 | `Y`, `Y/255`, `Y/220`, `Y /240` |
| `Magenta` | 2621 | `M`, `М`, `M/255`, `M/300` |
| `Pantone 485` / `P 485` | 1605 | `Р 485`, `P 485`, `Р 485/110` |
| `Cyan` | 1591 | `C`, `С`, `C/255`, `C/300` |
| `Pantone 137` / `P 137` | 725 | `Р 137`, `Р 137/110` |
| `Pantone 021` / `P 021` | 589 | `Р 021`, `P 021`, `Р 021/110` |
| `Pantone 072` / `P 072` | 482 | `Р 072`, `P 072`, `Р 072/110` |
| `Pantone 122` / `P 122` | 479 | `Р 122`, `Р 122/110`, `Р 122/240` |
| `Pantone 483` / `P 483` | 414 | `Р 483`, `Р 483/110`, `P 483/110` |
| `Gold` | 376 | `злато`, `Злато`, `злато/110` |
| `Pantone 168` / `P 168` | 363 | `Р 168`, `P 168`, `Р 168/110` |
| `Pantone 354` / `P 354` | 320 | `Р 354`, `Р 354/110` |
| `Pantone 375` / `P 375` | 312 | `375`, `P 375`, `P 375/110` |
| `Pantone 130` / `P 130` | 243 | `Р 130`, `Р 130/110`, `Р 130/240` |
| `Pantone 362` / `P 362` | 221 | `Р 362`, `Р 362/110`, `Р 362/255` |
| `Pantone 871` / `P 871` | 198 | `Р871`, `Р 871`, `Р 871/110` |
| `Pantone 1235` / `P 1235` | 187 | `Р 1235`, `Р 1235/240`, `P 1235/110` |
| `Pantone 186` / `P 186` | 183 | `Р 186`, `Р 186/110` |
| `Reflex Blue` | 145 | `R.Blue/110`, `Ref. blue`, `Refl. Blue` |
| `Pantone 3435` / `P 3435` | 144 | `P 3435`, `P 3435/110`, `110 / 3435` |
| `Pantone 484` / `P 484` | 129 | `P 484`, `Р 484`, `Р 484/110` |
| `Pantone 356` / `P 356` | 128 | `Р 356`, `356`, `Р 356/110` |
| `Pantone 102` / `P 102` | 100 | `Р 102`, `Р 102/240` |
| `Pantone 201` / `P 201` | 100 | `Р 201`, `Р 201/110` |

Common anilox values observed in legacy workbook entries:

- `110`
- `220`
- `240`
- `255`
- `300`

### Approved Prototype Naming Direction

For the interim prototype/workbook, the ink station catalog should use a limited
accepted list of color identities. The workbook cell then appends the anilox
value after the delimiter.

Approved prototype format:

```text
[Color Identity] | [Anilox lines/cm]
```

Manufacturer and invoice product code are not part of the workbook-facing color
identity for the prototype. They remain invoice/procurement/costing lookup
information.

For process colors and common colors:

- `White`
- `Yellow`
- `Magenta`
- `Cyan`
- `Black`
- `Orange`
- `Green`
- `Ruby Red`
- `Reflex Blue`
- `Gold`
- `Gray`
- `Violet`
- `Pink`
- `Warm Red`
- `Fershnit`

For numbered/special colors, use the accepted color identity that distinguishes
the color. Examples:

```text
Pantone 485 | 110
Pantone 871 Gold | 110
Reflex Blue | 110
```

### Prototype Conclusion

The prototype/workbook convention is settled as:

```text
Color Identity | Anilox lines/cm
```

The prepared catalog should map legacy and invoice variants to accepted color
identities. For example, `W`, `W/110`, `БЯЛО`, and `FKD400W0000F БЯЛО` can map
to `White` if shift managers confirm the identity is usable.

### ERP-Relevant Conclusion

The prototype workbook convention does not include manufacturer or invoice
product code in the color identity. The later ERP ink-item rule depends on
supplier-color interchangeability; that open decision is tracked only in the
central plan.

## 3. Solvents

### Costing Role

Solvents remain monthly allocated. They are not expected to be captured per
printed order/card in the interim process.

The naming convention is still useful because monthly invoice/expense mapping
needs consistent categories.

### Invoice Evidence

Solvents appear inside the invoice `Inks & Solvents` subcategory.

Observed solvent invoice names:

- `SOL115A0000 СОЛВЕНТ`
- `СОЛВЕНТ`
- `Солвент`
- `Солвент (SOL115A0000)`
- `МЕТОКСИПРОПАНОЛ`
- `ЕТИЛАЦЕТАТ`

Observed records:

- `СОЛВЕНТ`: 9
- `МЕТОКСИПРОПАНОЛ`: 8
- `Солвент`: 5
- `SOL115A0000 СОЛВЕНТ`: 2
- `ЕТИЛАЦЕТАТ`: 1
- `Солвент (SOL115A0000)`: 1

### Shift-Manager Workbook Evidence

No current `Database` column is being used as a solvent costing input.

The plan already treats solvents as monthly allocated, not order-specific. The
shift-manager ink station fields `AB:AI` are for ink/color and anilox, not
solvent quantity.

### Naming Direction

Solvents use a monthly allocation catalog, separate from the workbook
ink/color station catalog.

Initial candidate names:

- `Solvent SOL115A0000`
- `Methoxypropanol`
- `Ethyl acetate`
- `Generic Solvent`

### Conclusion

Solvents are not workbook-owned per-order inputs for the interim process. They
remain monthly allocated. The remaining solvent allocation naming/grouping
decisions are tracked only in the central plan.

## 4. PP Purchased Film

Status: CPP/BOPP purchased-film naming convention approved. Conceptual
discussion closed.

### Costing Role

PP purchased film is different from extrusion PE raw material. It is a purchased
input film rather than a polymer recipe material produced through extrusion.

For interim costing, PP film naming is needed so actual purchased-film
consumption can be tied to the correct material cost.

### Invoice Evidence

The invoice workbook classifies purchased film separately.

Relevant invoice classification:

| Invoice subcategory | Records | Distinct item names | Invoice item types |
| --- | ---: | ---: | --- |
| `Purchased Film` | 126 | 58 | `BOPP`, `CPP`, `Stretch Film` |

Observed `BOPP` invoice names:

- `Biaxially oriented polypropylene film FXC20 930mm`
- `Biaxially oriented polypropylene film FXC25 1000mm`
- `Biaxially oriented polypropylene film FXC30 1000mm`
- `Biaxially oriented polypropylene film FXC30 1080mm`
- `Biaxially oriented polypropylene film FXC30 800mm`
- `Biaxially oriented polypropylene film FXC30 900mm`
- `Biaxially oriented polypropylene film FXC30 930mm`
- `Biaxially oriented polypropylene film FXC30 960mm`
- `Biaxially oriented polypropylene film FXC35 800mm`
- `Biaxially oriented polypropylene film FXC35 960mm`
- `Biaxially oriented popypropylene film FXC35 960mm`
- `BOPP film FXC20 930mm`
- `BOPP film FXC25 1000mm`
- `BOPP film FXC30 1000mm`
- `BOPP film FXC30 1080mm`
- `BOPP film FXC30 800mm`
- `BOPP film FXC30 960mm`
- `BOPP film FXC35 800mm`
- `BOPP film FXC35 960mm`
- `BOPP film FXC40 370mm`

Observed `CPP` invoice names:

- `Cast polypropylene film PLCB25 1000mm`
- `Cast polypropylene film PLCB25 1020mm`
- `Cast polypropylene film PLCB25 1040mm`
- `Cast polypropylene film PLCB25 640mm`
- `Cast polypropylene film PLCB25 900mm`
- `Cast polypropylene film PLCB25 960mm`
- `Cast polypropylene film PLCB28 1000mm`
- `Cast polypropylene film PLCB28 1020mm`
- `Cast polypropylene film PLCB28 1040mm`
- `Cast polypropylene film PLCB28 1060mm`
- `Cast polypropylene film PLCB28 1100mm`
- `Cast polypropylene film PLCB28 1100mm (121839...)`
- `Cast polypropylene film PLCB28 740mm`
- `Cast polypropylene film PLCB28 960mm`
- `Cast polypropylene film PLCB281040mm`
- `Cast polypropylene film PLCB35 1020mm`
- `Cast polypropylene film PLCB35 1040mm`
- `Cast polypropylene film PLCBZ25 1020mm`
- `Cast polypropylene film PLCBZ25 900mm`
- `Cast polypropylene film PLCBZ25 960mm`
- `Cast polypropylene film PLCBZ28 1000mm`
- `Cast polypropylene film PLCBZ28 1020mm`
- `Cast polypropylene film PLCBZ28 1040mm`
- `Cast polypropylene film PLCBZ28 1060mm`
- `Cast polypropylene film PLCBZ28 1100mm`
- `Cast polypropylene film PLCBZ28 640mm`
- `Cast polypropylene film PLCBZ28 740mm`
- `Cast polypropylene film PLCBZ28 840mm`
- `Cast polypropylene film PLCBZ28 960mm`
- `Cast polypropylene film PLCBZ35 1020 mm`
- `Cast polypropylene film PLCBZ35 800mm`

Observed stretch-film names:

- `Стреч 23~18кг машинен 150%`
- `Стреч 23~18кг машинен White`

Non-material rows appeared inside purchased film evidence and are excluded from
material naming:

- `Transport`
- `Транспорт`
- `Нает транспорт`
- `Нает Транспорт`
- `Грешно осчетоводена фактура`

### Shift-Manager Workbook Evidence

No current `Database` column provides a clean purchased-PP-film material identity
for costing.

The old workbook fields `F`, `L`, and `M` may contain product/material/size
descriptions, but they were already classified as legacy or navigation fields,
not reliable costing material identity fields.

For PP film actual capture, the material used should be captured through the
app or through a forward-looking controlled field/list, not parsed from old
free-text descriptions.

### Approved Naming Direction

PP film should be its own catalog, separate from extrusion polymers.

Approved canonical pattern:

```text
[Film Type] [Product Series] [Thickness] [Width mm]
```

Do not include the micron symbol in the item name. Keep a visible space between
the product series and the thickness.

Examples:

- `BOPP FXC 20 930mm`
- `BOPP FXC 25 1000mm`
- `BOPP FXC 30 960mm`
- `BOPP FXC 35 800mm`
- `BOPP FXC 40 370mm`
- `CPP PLCB 25 1020mm`
- `CPP PLCB 28 1040mm`
- `CPP PLCB 35 1020mm`
- `CPP PLCBZ 25 960mm`
- `CPP PLCBZ 28 1000mm`
- `CPP PLCBZ 35 800mm`

The inspected invoice workbook contains 40 distinct purchased PP film identities
after normalizing obvious wording variants and excluding transport/correction
rows:

- 11 `BOPP` identities.
- 29 `CPP` identities.

These should be handled through a dropdown/controlled list rather than free
text.

### Completed Conclusion

Use the following controlled-list convention for CPP/BOPP purchased film:

```text
[Film Type] [Product Series] [Thickness] [Width mm]
```

Examples:

- `BOPP FXC 30 960mm`
- `CPP PLCB 28 1040mm`
- `CPP PLCBZ 28 1040mm`

Do not include the micron symbol in the item name. The product series remains in
the name because external evidence indicates `FXC`, `PLCB`, and `PLCBZ` are
formal Plastchim-T product types, not invoice noise. `PLCBZ` should remain
separate from `PLCB` because it is a distinct Plastchim-T product type designed
for winter conditions unless the business later confirms free interchangeability.

### Catalog Cleanup Conclusions

- `Biaxially oriented polypropylene film FXC30 960mm` and
  `BOPP film FXC30 960mm` normalize to one canonical item:
  `BOPP FXC 30 960mm`.
- `Cast polypropylene film PLCB281040mm` normalizes to
  `CPP PLCB 28 1040mm`.
- Stretch film remains outside the CPP/BOPP catalog unless it is later confirmed
  as a direct sold-product input.
- Transport and correction rows inside purchased-film invoices are excluded
  from material identity catalogs.

## Cross-Track Notes

### Current Evidence-Based Direction

- The invoice workbook should lead the canonical naming catalogs.
- The shift-manager workbooks are useful for identifying aliases, shorthand,
  and what the shift managers are used to seeing.
- The shift-manager workbook values should not be used directly as the
  canonical catalog because they mix identities, percentages, ratios, anilox,
  and operational shorthand.
- Shift managers should verify prepared catalogs for usability; they should not
  be asked to create the catalogs from scratch.

### Conclusion

The naming convention evidence in this file supports the prepared HTML preview
and the central-plan questions. Active questions and tasks are tracked only in
`interim-costing-process-plan.md`.
