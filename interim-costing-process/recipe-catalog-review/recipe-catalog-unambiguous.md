# Recipe Catalog - Unambiguous Candidates

Status: review workspace. These rows are candidates for the active `RecipeCatalogExtrusion` sheet after business review.

Rule used for this file: a row appears here only when the source evidence supports all three dropdown fields: `Category`, `Producer`, and `GradeCode`. Percentages are intentionally excluded because they are order-specific.

Source files inspected:

- `interim-costing-process/source-files/raw-materials-for-naming-convention.xlsx`
- `interim-costing-process/source-files/PO-OC - Marco.XLSM`, `Database!AM:AS`
- `interim-costing-process/interim-naming-convention-report.md`

The paste-ready catalog columns are the first four columns below. `Source evidence` is for review only and should not be pasted into Excel.

| Category | Producer | GradeCode | Notes | Source evidence |
| --- | --- | --- | --- | --- |
| LDPE | SABIC | 2100N0 W |  | LDPE SABIC 2100N0 W (4 rows, 70125 kg; КАСКАДА ООД x2, Каскада ООД x2); LDPE SABIC 2100N0 W /MFR 0.3 no adds (1 rows, 23375 kg; КАСКАДА ООД x1) |
| LDPE | SABIC | HP0722NN |  | LDPE SABIC HP0722NN MFI 0.75 1500KG/Pallet (1 rows, 20975 kg; КАСКАДА ООД x1) |
| LDPE | DOW | 1200E |  | LDPE DOW 1200E - NTP - полиетилен (1 rows, 15775 kg; Петробул БГ ООД x1) |
| LDPE | HIPTEN | F22003 |  | LDPE HIPTEN F22003 (1 rows, 2500 kg; Полимери Индъстрис ООД x1) |
| LDPE | ExxonMobil | LD 165BW1 | Invoice row also references `LD 03322.BW1`; report example normalizes to `LD 165BW1`. | LDPE LD165BW1 / ExxonMobil LD 03322.BW1 (1 rows, 22000 kg; АФКО ЕООД x1) |
| LDPE | ExxonMobil | LD 150BW | Completed from online evidence. | Invoice: `LDPE LD150BW`; ExxonMobil product guide lists `LD 150 AC, BW`; LookPolymers lists `ExxonMobil LDPE LD 150BW`. |
| LDPE | ExxonMobil | LD 03529 | Completed from online evidence. Legacy/commercial alias: `Nexxstar LDPE 00328`. | Invoice: `NEXXSTAR 00328/ExxonMobil LD 03529 ПЕВН`; ExxonMobil Signature Polymers finder maps `Nexxstar LDPE 00328` to `ExxonMobil LD 03529`. |
| LDPE | Midilena | B20/03 |  | MIDILENA PE B 20/03 - полиетилен (7 rows, 145750 kg; Петробул БГ ООД x7); MIDILENA PE B 20/03 - полиетилен (LDPE) (1 rows, 23375 kg; Петробул БГ ООД x1) |
| LDPE | Midilena | B20/07 |  | MIDILENA PE B 20/07 - полиетилен (1 rows, 23375 kg; Петробул БГ ООД x1) |
| LDPE | Midilena | B21/05 |  | MIDILENA PE B 21/05 - полиетилен (3 rows, 42625 kg; Петробул БГ ООД x3) |
| LDPE | Midilena | B22/07 |  | MIDILENA PE B 22/07 - полиетилен (4 rows, 93500 kg; Петробул БГ ООД x4); MIDILENA PE B 22/07 - полиетилен (LDPE) (1 rows, 23375 kg; Петробул БГ ООД x1); MIDILENA PE В 22/07 - полиетилен (1 rows, 23375 kg; Петробул БГ ООД x1) |
| LDPE | Petilen | G03-21T | Report example uses this canonical spelling. | ПЕВН PETILEN G03-21T (4 rows, 88500 kg; ГЛОБЪЛ ЛИНКС ЕООД x3, ГОЛОБЪЛ ЛИНКС ЕООД x1); ПЕВН PETILEN G03-21T (LDPE) (1 rows, 9000 kg; ГЛОБЪЛ ЛИНКС ЕООД x1) |
| LDPE | Petkim | G03-5 | Report example uses this canonical spelling; `PETKIN` remains an invoice typo/alias to handle separately. | PETKIM LDPE G03-5 - полиетилен (1 rows, 22500 kg; Петробул БГ ООД x1) |
| LLDPE | Borealis | FB4230 |  | LLDPE - BOREALIS FB4230 (1 rows, 1375 kg; НОВИЗ АД x1) |
| LLDPE | Ciplas | 1118F |  | LLDPE CIPLAS 1118F (1 rows, 15000 kg; НОВИЗ АД x1) |
| LLDPE | Ciplas | 1121F6 |  | LLDPE CIPLAS 1121F6 (линеен полиетилен) (1 rows, 2750 kg; Петробул БГ ООД x1); LLDPE CIPLAS 1121F6 - линеен полиетилен (3 rows, 8250 kg; Петробул БГ ООД x3) |
| LLDPE | Copap | 118-B8 |  | LLDPE Copap 118 - B8 (1 rows, 22500 kg; Петробул БГ ООД x1) |
| LLDPE | SABIC | 119ZJ |  | LLDPE SABIC 119ZJ (1 rows, 23375 kg; НОВИЗ АД x1); LLDPE-SABIC 119ZJ (2 rows, 2750 kg; НОВИЗ АД x2) |
| LLDPE | Shell | 18F1B |  | LLDPE SHELL 18F1B (3 rows, 13500 kg; НОВИЗ АД x3); LLDPE Shell 18F1B - линеен полиетилен (1 rows, 6000 kg; Петробул БГ ООД x1) |
| LLDPE | Lotrene | Q1018H |  | Линеен ПЕВН LOTRENE Q1018H (1 rows, 24000 kg; ГЛОБЪЛ ЛИНКС ЕООД x1) |
| LLDPE | ExxonMobil | C4LL 1018.AV | Completed from online evidence. Legacy/commercial alias: `LL 1001AV`. | Invoice: `LLDPE C4 LL1001AV`; ExxonMobil datasheet identifies `C4LL 1018.AV`; trade evidence lists `C4LL1018.AV/LL1001AV`. |
| MDPE | ETHYDCO Advancene | EE-3914-AAH | Completed from online evidence. Treat `MDPE 3914` as shorthand/alias unless business evidence says it is a separate item. | Invoice: `ПЕВН (MDPE – ADVANCENE – EE-3914-AAH)`; ETHYDCO product page lists `EE-3914-AAH`; distributor evidence lists factory `ETHYDCO`, brand `ADVANCENE`, code `EE-3914-AAH`. |
| reLDPE | N/A | N/A | Approved omission: recycled LDPE without stable producer/grade. The macro prints only `reLDPE` before the percentage delimiter. | Invoice: `LDPE регранулат натурален`; business rule uses `N/A` for intentionally absent producer and grade. |
| Antistatic | CONSTAB | AT 04673 LD | Completed from online evidence. CONSTAB is part of Kafrit Group. | Invoice: `Добавка Antistatic AT 04673 LD`; Kafrit/CONSTAB evidence identifies `AT 04673 LD` as an antistatic masterbatch. |
| Masterbatch | Polibach | White 800 ET |  | Полибач бял 800 ЕТ (1 rows, 100 kg; АМЗ ООД x1) |
| Masterbatch | Polibach | White 8000 ET |  | Полибач бял 8000 ЕТ (2 rows, 450 kg; АМЗ ООД x2) |
| Masterbatch | Polibach | VLA 66 |  | Полибач ВЛА 66 (5 rows, 6250 kg; АМЗ ООД x5) |
| Masterbatch | Polibach | LCC 90 |  | Полибач ЛЦЦ 90 (1 rows, 1250 kg; АМЗ ООД x1) |
| Masterbatch | Polibach | Orange L 1014 |  | Полибач оранж Л 1014 (1 rows, 75 kg; АМЗ ООД x1) |
| Masterbatch | Polibach | Blue AG L 4535 |  | Полибач син АГ Л 4535 (1 rows, 500 kg; АМЗ ООД x1) |
| UV | Polibach | UV 1952 Natural | Report example treats this as a UV additive candidate rather than generic color masterbatch. | Полибач УВ 1952 натурален (1 rows, 200 kg; АМЗ ООД x1) |
| Masterbatch | Polibach | Black 7200 |  | Полибач черен 7200 (1 rows, 100 kg; АМЗ ООД x1) |
| Masterbatch | Plastika Kritis | Green 51817 | Completed from Marco alias evidence plus online catalog evidence. | Marco alias: `GREEN 51817`; Plastika Kritis masterbatch catalogue lists `GREEN 51817`. |
| Antislip | POLYBATCH | SAS | Completed from Marco alias evidence plus online evidence. POLYBATCH is now a LyondellBasell brand; legacy supplier may appear as A. Schulman. | Marco alias: `SAS анти-слип`; SpecialChem lists `POLYBATCH SAS` by LyondellBasell as an anti-slip masterbatch. |
