# ERP Production Card Pilot

This repository is for a pilot app that helps move the extrusion terminal from paper production cards to an app-driven workflow. This README is written for future agents. It should preserve the confirmed project facts, the inspected Excel workbook structure, and the current open decisions without turning discussion ideas into requirements.

Source inspection date: 2026-06-10.

This is not V1 of a product roadmap. This is the complete standalone pilot/prototype scope. After this pilot, the direction is to build the actual ERP on ERPNext, not to keep expanding this app.

## Agent Rules

- The Excel workbook structure is set in stone; automations may rely on that structure.
- It is acceptable to add macros/automation to the workbook if they only read/export data and do not edit existing workbook data.
- Do not add requirements unless the user confirms them.
- Do not plan future functionality for this app. The pilot scope is the whole scope.
- Treat the shift-manager workbook as the source of production-order information.
- Treat terminal-entered production data as app data unless the user later confirms that it must be written back to Excel.
- Pilot scope is extrusion only. Other workbook operations are context, not app scope.
- Printed output must match the existing Excel front/back operational card one-to-one, except for mild confirmed additions such as start time, stop/finish time, total gross weight, and total net weight.

## Confirmed Pilot Scope

The pilot is part of an ERP transition. The immediate goal is to educate people at the production terminal to use an app instead of paper.

This pilot is also a learning tool for the future ERPNext-based ERP: it tests how the workstation should look and how workers interact with digital operational cards. It is not intended to grow into the final ERP.

Confirmed workflow facts:

- There is one terminal.
- The extrusion area should be represented as four fixed machines in the app. One of the machines may not be operational, but it should still exist in the app.
- The app should model only simple machine assignment, sequencing, and navigation. It should not model detailed machine performance or downtime.
- The terminal receives and executes extrusion operational cards assigned to those machines.
- The shift manager continues using the existing Excel workbook.
- The shift manager assigns each released card to a machine and gives it a simple numeric queue position.
- Each row in the `Database` worksheet is one complete production order with all operational-card source data.
- The app is for the extrusion operation only.
- Operators should see the extrusion operational card front in the app.
- Operators should have a back/input view for entering gross roll weights.
- The terminal UI does not need to preserve a strict front-page/back-page split. It can combine the necessary operator-facing information into one compact working screen.
- The printed output must still preserve the old front/back operational-card format.
- The app needs one tare-weight field for the order.
- Tare weight means the actual weight of the roll core.
- The tare weight is the same for the whole order.
- Operators input gross weight for each roll.
- The app calculates net weight per roll from gross roll weight and order-level tare weight.
- The app calculates total net weight for the order from the roll net weights.
- At the end of the order, operators click `Finished`.
- After finishing, operators should be able to click `Print`.
- Printing should print the whole front and back.
- Completed data should be stored in the app.

The terminal UI can present information in whatever way is practical. The printed paper output has a stricter requirement: it must visually match the Excel front and back card layout as closely as possible.

## Order Lifecycle And Access Model

Confirmed model:

- The shift manager decides which orders/cards are loaded into the app.
- The shift manager decides which machine should produce each released card and the sequence within that machine queue.
- Operators use the terminal to execute loaded operational cards.
- The app should provide the simplest possible way to visualize several orders/cards.
- The terminal should have a main active queue/list and a separate completed cards section/list.
- The main terminal queue/list should make it clear which cards are pending, running, or paused.
- The terminal should have a fixed four-machine quick navigation strip.
- Each machine tile should show only key information: machine number, current or next order, customer, progress, and status color.
- Clicking a machine tile should open the running/paused card for that machine if one exists; otherwise it should open the next pending card for that machine by sequence.
- The completed section lets operators view previous completed cards, fix mistakes, and reprint when needed.
- Users should be able to click an order/card from the list to view it.
- `Finished` means the order/card is closed for workflow/status purposes, not locked for editing.
- Finishing/completing an order moves it out of the active terminal queue/list and into the terminal completed section.
- Finished/closed cards may still be changed, similar to how paper cards can be scratched out and overwritten.
- The pilot should avoid lock/reopen exception logic.
- The terminal may have multiple running cards at the same time.
- A machine cannot have more than one running card at the same time.
- A machine can have many pending cards.
- If a card is paused, treat that machine as occupied until the card is completed, cancelled, or reassigned.
- Operators should see machine queues in the shift-manager sequence. The app should keep corrections possible if real production changes.
- Running cards should be visually obvious, for example highlighted green, so operators do not forget that time is being tracked.
- There are no named users or logins for the pilot.
- The terminal has no individual operator identity.
- The shift manager has no app identity/login requirement.
- Access separation is practical rather than permission-based: the terminal runs `/terminal` in kiosk mode, while the shift manager opens `/admin` directly.

Lifecycle states:

| State | Meaning |
| --- | --- |
| `imported` / `draft` | Order/card exists in the app database after CSV import. It can be reviewed in the app, but is not yet released to the terminal execution view. |
| `pending` | Order/card has been released by the shift manager and is visible in the terminal queue, but production timing is not currently running. |
| `running` | Operators started production timing for the card. Multiple cards may be running at once. |
| `paused` | Production timing was paused for the card. |
| `completed` / `finished` | Operators have finished the order/card. It moves from the active terminal queue to the terminal completed section and remains available in app history/details. |
| `cancelled` | Operators or shift manager cancelled the card. It is no longer active, remains visible with completed/cancelled cards, and can be toggled back to `pending`. |

Canonical Bulgarian status labels:

| Internal status | Bulgarian label |
| --- | --- |
| `imported` | Импортирана |
| `pending` | Изчакване |
| `running` | Изработване |
| `paused` | Паузирана |
| `completed` | Завършена |
| `cancelled` | Анулирана |

The important distinction: CSV import should already create persistent app records. Submit/release should not be the first time the data is saved; it should change the order/card from an app-side draft into a terminal-visible card.

Screen/access model:

- Use one web app with separate pages/routes.
- Pages/routes:
  - `/terminal` for kiosk-mode operator workflow.
  - `/admin` for shift-manager import, draft review, release, and app data review.
- Do not build users, roles, or login permissions for the pilot.
- The terminal should run in kiosk mode pointed at `/terminal`.
- The terminal UI should not expose navigation to `/admin`.
- The shift manager can access `/admin` directly by URL from the shift-manager PC.
- This is practical segregation, not strong security.

## Workstation UI Direction

The workstation interface is the operator-facing `/terminal` screen used at the extrusion machines. It is separate from the shift-manager/admin interface and should remain as simple as possible.

Current active UI prototype:

- Use `ui-prototypes/workstation-v8.html` as the active workstation prototype baseline.
- Keep `ui-prototypes/workstation-v7.html` as the checkpoint before the top-machine-navigation restructure.
- Older workstation prototypes are not accepted as the design direction.
- The workstation UI should be optimized for clear use at the real terminal/workstation monitor, not for dense desktop administration.
- Text inside operational-card fields, notes, recipe rows, and weight inputs must be large enough to read without careful inspection.
- Avoid unnecessary subtitles and explanatory text. Use section headings only where they reduce confusion.

Confirmed workstation screen structure:

- Four fixed machine navigation buttons stay visible across the top of the screen.
- The top machine navigation is global terminal navigation and should be available from every workstation screen.
- Clicking a machine in the top navigation changes the selected machine/card; the screen content underneath is specific to that selected machine/order.
- The top machine navigation visually separates terminal-wide navigation from selected-machine/order details below.
- The top machine navigation should sit on a neutral gray band, not on the same white surface as the selected-order content and not on an input-like blue tint.
- Leave clear top, bottom, and side breathing room around the top machine buttons so they read as navigation, not squeezed content.
- Machine navigation buttons should be compact horizontally but tall enough to be prominent and readable.
- The selected-machine/order content below the navigation should stay flat on a full-width page surface with internal content padding; do not wrap the whole active order area in another inset page-shell box.
- The operator works on one focused card at a time.
- The focused card header should make the selected machine and order number obvious.
- Under the top machine navigation, the selected-machine/order page should use a flat structure rather than nested cards inside cards.
- Avoid repeated rounded panel wrappers for the page shell. Use section headings, whitespace, and simple dividers before adding another bordered container.
- Use bordered/boxed treatments only for actual controls, tables, repeated cards, and input groups where the frame helps interaction.
- Main visible actions are `Start`, a single `Pause/Resume` toggle, and `Finish`.
- `Print/Reprint` belongs in the overflow/burger menu.
- `Cancel/Restore` belongs in the overflow/burger menu.
- `История` belongs with the global top navigation because it is not specific to one active order.
- The roll panel should stay focused on tare, new gross roll entry, roll correction, and gross/net totals.
- New roll entry should sit directly above the roll list.
- Roll gross/net/remaining totals should be shown below the roll list, not above the entry controls.
- Gross total and remaining gross amount should be visually grouped because remaining amount is based on the gross target.
- Net total should be shown separately from gross/remaining, but all three totals should fit on one row in the workstation roll panel.
- The roll panel should be wide enough for four-digit kilogram values with one decimal place, such as `3000.0`, without truncating.
- Remaining amount should not use a strong warning color by default.
- The workstation roll table should not show always-visible delete buttons next to every roll row.
- Gross and net columns in the workstation roll table should use equal width.
- Tare/core weight should be labelled `Шпула, кг` on the workstation.
- `Шпула, кг` is an order-level editable field and should not dominate the repeated roll-entry workflow.
- `Шпула, кг` should save inline on `Enter` and on blur, using the same conflict/version checks as other terminal edits.
- Do not use a separate `Save` button for `Шпула, кг` unless inline save proves unreliable in testing.
- Show `Макс. тегло ролка, кг` next to `Шпула, кг`, on the left side.
- `Макс. тегло ролка, кг` is entered by the shift manager, read-only for machine operators, and informational only.
- `Макс. тегло ролка, кг` should not enforce roll-weight validation in this pilot.

Top machine navigation content:

- Each machine button should be compact but not cramped.
- Each machine button must clearly show the full Bulgarian machine label: `Машина 1`, `Машина 2`, `Машина 3`, or `Машина 4`.
- Each machine label may include a small machine/home-style icon before the label, matching the Figma navigation treatment.
- Each machine button should show the current status, such as `Изработване`, `Паузирана`, or `Свободна`.
- Each machine button should show the most important current order context in separate rows: customer name, then product/material identifier, then the progress bar.
- Do not combine customer and product in one line; long customer names and long product identifiers must not compete for the same horizontal space.
- If a machine has no active card, show `-` in the customer row and do not show next-card text.
- Do not show next-card text in the top machine navigation cards.
- Each machine button should show a progress bar with produced/target kilograms to the side of the bar, not underneath it.
- Top machine navigation is an overview, so produced/target kilograms should be rounded to whole kilograms with no decimals.
- Do not show waiting-card counts in the top machine buttons.
- The selected machine should be visually stronger than the other machine buttons.
- Machine-card borders should communicate selection, not status.
- Do not use status-colored top borders on machine cards when the status pill is already visible.
- Machine-card borders should use the Figma-style weight pattern: thicker top border and thinner side/bottom borders.
- Selected machine card should use a dark blue border derived from the input blue palette.
- Inactive/unselected machine cards should use neutral gray borders so the currently displayed machine is unambiguous.
- Idle/free machine cards should keep the same solid border pattern as other unselected cards; the status pill communicates that the machine is free.

The focused technology-card panel should be shown as:

1. `Технологична Карта`
2. Requested product/order fields without an extra `Заявено изделие` subtitle, because the panel title and field labels already make the section clear.
3. A separate `Забележки` section.
4. A separate `Рецепта` section.

Requested product/order fields:

- `Изделие`
- `Фирма`
- `Количество`
- `Размер`
- `Заготовка`
- `Материал`

Notes display:

- Workbook notes come from the technology card/order source data.
- In the workstation UI, notes should be labelled `Забележки`.
- Notes should be visually more prominent than a squeezed inline text row.
- Notes text should be larger and readable, but not bold by default.
- Leave enough vertical spacing between `Забележки` and `Рецепта` so the two sections read as separate parts of the card.

Recipe display:

- The recipe table represents a single-layer extrusion recipe.
- The row order should mimic the existing Excel technology card structure because the app imports the data from that structure.
- User-facing recipe row labels should be normalized for readability and should not blindly preserve all-caps source text unless it is a technical abbreviation.
- The first recipe column should label the type of raw material, not a generic "position".
- Use the Bulgarian header `Вид суровина` for the first recipe column.
- The second recipe column is the planned/source raw material from the technology card.
- Use the Bulgarian header `Заложена суровина` for the second recipe column.
- `Заложена суровина` is read-only on the workstation. Operators must not edit it.
- If operators use a different actual material than the planned/source material, they enter it in the third column.
- Use the Bulgarian header `Използван материал` for the third recipe column.
- `Използван материал` starts blank after import and is filled only by machine operators when needed.
- The fourth recipe column is `Партида`.
- `Партида` starts blank after import and is filled by machine operators with the actual batch/lot used for the order.

Confirmed recipe rows for the workstation table:

| Row label | Source field |
| --- | --- |
| `Вид суровина A` | Extrusion raw material A |
| `Вид суровина B` | Extrusion raw material B |
| `Вид суровина C` | Extrusion raw material C |
| `Линеен /mLLDPE/` | Extrusion linear PE |
| `Антистатик` | Extrusion antistatic |
| `Мастербач` | Extrusion masterbatch |
| `Креда` | Extrusion chalk |

Admin page behavior:

- The admin page is used by the shift manager.
- CSV import should show imported orders as a simple draft list.
- Each imported draft should be reviewable before release.
- Duplicate and overwrite outcomes should be shown through import actions/messages.
- Release should validate the current card fields directly before sending the card to the terminal.
- Rows with `no extrusion step` should be reported in the import result and skipped. They should not create cards because they cannot be used by the extrusion workstation.
- The shift manager can edit any field on an imported card/order from the admin page.
- Admin editing is broader than terminal editing; terminal editing is intentionally limited.
- The shift manager can cancel and restore terminal-visible cards from the admin card detail page.
- The shift manager can correct terminal-side material fields, tare weight, roll gross weights, and timing segments from the admin card detail page.
- Admin production corrections use the same loaded-version conflict checks as terminal edits, so stale correction forms are blocked and require reload.
- The admin page should provide a simple machine planning view split into four machine columns.
- Each machine column should show active queued cards for that machine sorted by numeric queue position.
- Machine assignment is mandatory before a card is released to the terminal.
- Sequence is a target display position assigned by the shift manager, not a production lock.
- Release, reassignment, and resequencing normalize each affected active machine queue to contiguous positions starting at `1`.
- Entering a position already used by another active card inserts the card there and shifts the other active cards.
- Release/submit can be one draft at a time. Do not add bulk release unless it becomes clearly necessary.

## Explicitly Out Of Scope For Now

- Printing / flexo operation workflow.
- Rewinding and slitting workflow.
- Confection workflow.
- Detailed machine-level tracking beyond simple machine assignment, sequencing, and quick navigation.
- Writing terminal-entered data back into the Excel workbook.
- Public internet exposure of the app.
- Persistent data or workflow features outside the confirmed app data model.
- Future-product roadmap features for this app. After this pilot, the expected direction is ERPNext-based ERP work.

## Source Workbook

Canonical file:

- `source-files/shift-manager-main-file.xlsm`

Observed companion file:

- `source-files/~$shift-manager-main-file.xlsm`
- This is an Excel lock/temp file, not a source workbook.

Workbook properties observed:

- Macro-enabled Excel workbook (`.xlsm`).
- Readable with `openpyxl`.
- `Get-FileHash` could not read it during inspection because another process had the workbook locked.
- Sheets:
  - `Database`
  - `Technology Cards`
  - `Page Back`

## Workbook Model

The workbook has one source-data worksheet and two print/layout worksheets.

| Worksheet | Role |
| --- | --- |
| `Database` | Durable source data. Each production order is one row. |
| `Technology Cards` | Front-side print layout. It contains four side-by-side operational card blocks. |
| `Page Back` | Back-side print layout. It contains the roll/weight grid. |

The layout sheets are derived from `Database`. They should not be treated as source data.

## `Database` Sheet

Observed metadata:

- Dimensions: `A1:BT12206`
- Meaningful source columns observed through `AY`
- Columns `AZ:BT` are within the worksheet dimension but appeared blank in inspected headers and data counts
- Freeze panes: `B5`
- Auto filter range: `A4:AX12206`
- Hidden row: `1`
- Actual production-order data rows: `5:12206`
- Non-empty order numbers in `A5:A12206`: `12200`

Important row roles:

| Row | Role |
| --- | --- |
| `1` | Numeric lookup indexes used by formulas. `A1` is `1`; `B1:AY1` continue with formulas like `=A1+1`. |
| `2` | Blank in the inspected range. |
| `3` | Main column labels and merged operation group labels. |
| `4` | Mixed selector/subheader row. `A4` is the currently selected order number; operation subheaders start at `V4`. |
| `5+` | Actual production-order records. |

The selected order during inspection was `Database!A4 = 25278`. The matching full data row was row `12205`.

Duplicate order numbers exist in historical data, for example `3004` and `3012`. If the app reads by order number from the workbook, duplicate handling must be designed explicitly. A full-row copy/paste import avoids that ambiguity.

## Database Column Groups

The user described these stable column groups:

| Columns | Group |
| --- | --- |
| `A:U` | General production-order fields |
| `V:Y` | Operation flags |
| `Z:AI` | Printing-specific fields |
| `AJ:AT` | Extrusion-specific fields |
| `AU:AV` | Rewinding/slitting-specific fields |
| `AW:AY` | Confection-specific fields |

The pilot needs the general fields plus the extrusion group.

## Pilot-Relevant Database Fields

These fields are the observed minimum needed to render the extrusion operational card front.

| Column | Meaning |
| --- | --- |
| `A` | Order number |
| `B` | Date |
| `C` | Delivery date |
| `D` | Company/customer |
| `E` | City |
| `F` | Product type |
| `G` | Quantity 1 |
| `H` | Unit 1 |
| `I` | Quantity 2 |
| `J` | Unit 2 |
| `K` | Blank/product form |
| `L` | Material |
| `M` | Size/thickness |
| `N` | Notes |
| `W` | Extrusion operation flag |
| `AJ` | Extrusion folding |
| `AK` | Extrusion next operation |
| `AL` | Extrusion treatment |
| `AM` | Extrusion raw material A |
| `AN` | Extrusion raw material B |
| `AO` | Extrusion raw material C |
| `AP` | Extrusion linear PE |
| `AQ` | Extrusion antistatic |
| `AR` | Extrusion masterbatch |
| `AS` | Extrusion chalk |
| `AT` | Extrusion packaging method |

The app should preserve raw workbook values as much as possible. The workbook contains mixed human-entered content: dates, numbers, quantities embedded in text, units, notes, Bulgarian labels, and inconsistent text casing.

## Operation Flags

The workbook has four operation flag columns:

| Operation | Flag column |
| --- | --- |
| Printing / flexo | `V` |
| Extrusion | `W` |
| Rewinding/slitting | `X` |
| Confection | `Y` |

The Excel formulas compare operation flags against `Да`. Inspected data also contained lowercase `да`, and Excel still displayed the matching cards. Treat operation flags case-insensitively.

For the pilot app, only the extrusion flag in `W` matters.

## Excel Formula Mechanism

The print/layout sheets use the selected order number in `Database!A4`.

General pattern:

1. Read selected order number from `Database!A4`.
2. Look up that order number in `Database!A5:CO1048576`.
3. Return fields from the matching row using numeric indexes from `Database!1:1`.
4. Show or hide each front-card block based on its operation flag.

Implications:

- The app does not need to reproduce the `A4` selector if it imports a full source row.
- If the app reads directly from the workbook by order number, it must account for Excel-style lookup behavior and duplicate order numbers.
- The formulas reference `A5:CO1048576`, but meaningful inspected source data stopped at `AY`.

## `Technology Cards` Sheet

Observed metadata:

- Dimensions: `A1:AR56`
- Formula cells: `78`
- Print area: none defined
- Page setup: portrait, scale `92`
- Gridlines hidden

This sheet contains four front-card blocks side by side:

| Card | Cell range | Operation flag |
| --- | --- | --- |
| Printing / flexo | `A1:K56` | `Database!V` |
| Extrusion | `L1:V56` | `Database!W` |
| Rewinding/slitting | `W1:AG56` | `Database!X` |
| Confection | `AH1:AR56` | `Database!Y` |

Pilot app printing should reproduce the extrusion block, not the other three blocks.

Extrusion front block uses:

- Common order fields from `A:M`
- Notes from `N`
- Extrusion fields from `AJ:AT`

For selected order `25278`, cached values showed that the printing and extrusion blocks displayed, while rewinding/slitting and confection did not. That matches the inspected operation flags for that row.

## `Page Back` Sheet

Observed metadata:

- Dimensions: `A1:K48`
- Formula cells: `3`
- Print area: `'Page Back'!$A$1:$K$48`
- Page setup: portrait, paper size `9`, fit-to-width `0`, fit-to-height `0`
- Gridlines hidden

Only three formula cells pull from `Database`:

| Cell | Source |
| --- | --- |
| `A2` | Order number from `Database!A` |
| `C2` | Company/customer from `Database!D` |
| `F2` | Product type from `Database!F` |

All other observed back-page content is fixed layout text, prefilled roll numbers, or blank input cells.

The back page has three repeated roll-entry groups:

| Group | Columns | Roll numbers |
| --- | --- | --- |
| Left | `A:C` | `1:40` |
| Middle | `E:G` | `41:80` |
| Right | `I:K` | `81:120` |

Each group has a date/shift column, roll number column, and kg column. Rows `47:48` contain total labels but no total formulas were observed.

## Back-Page App Model

Confirmed for the app:

- Operators enter gross roll weights.
- The app stores one order-level tare weight.
- Net roll weight is calculated from gross roll weight minus tare weight.
- Total gross order weight is the sum of gross roll weights.
- Total net order weight is the sum of net roll weights.

Confirmed date/shift behavior:

- Keep the existing `Дата / смяна` columns on the printed back page.
- Do not require date/shift entry in the terminal UI.
- Do not build shift tracking for the current prototype.
- Date/shift columns are print-layout compatibility fields only for now.
- If shift tracking becomes necessary during testing, the likely shape would be a simple `Change Shift` button that records a timestamp and short text marker, but this is explicitly not current scope.

## App Data Model

Use separate but related structures for imported operational-card data and terminal-entered roll data. These have different lifecycles:

- Imported operational-card data comes from Excel/CSV and describes the order/card.
- Roll data is created at the terminal while operators execute the order.

Recommended conceptual schema:

| Entity | Purpose |
| --- | --- |
| `orders` / `cards` | One row per imported extrusion operational card/order. Stores the structured fields imported from Excel, current status, order-level tare, and print/workflow timestamps. |
| `recipe_material_entries` | One row per recipe material line for a card. Stores the row type, imported/source material, operator-entered actual used material, and operator-entered batch/lot. |
| `roll_entries` | One row per produced roll. Linked to the parent order/card by internal ID and order number. Stores roll number, gross weight, and calculated net weight. |
| `production_time_segments` | One row per production run segment. Stores each start/resume and pause/finish interval so total production time can exclude pauses. |
| `imports` / `import_batches` | One row per CSV import event, so the app can show which file/import created drafts. |
| `machines` | Four fixed machine records used for assignment, sequencing, and terminal quick navigation. |

Confirmed storage behavior:

- Imported orders remain in the app after import.
- The user should be able to review imported orders later.
- Imported orders should be visible in app data/history even before they are released to the terminal.
- Submit/release makes an already-saved order/card visible at the terminal; it does not create the order for the first time.
- Machine assignment must exist before release to the terminal.
- Machine sequence is a simple display order within the assigned machine queue.
- Machine sequence inputs are treated as target positions. The app inserts the card at that position, clamps too-high values to the end of the queue, and normalizes active cards to `1..N`.
- Duplicate sequence numbers within the same active machine queue must not persist after save.
- Completed orders remain available in the app for review.
- Completed orders should clear from the terminal execution view.
- Imported operational-card fields should be stored as readable structured fields in the app.
- Imported/source recipe material values should remain separate from operator-entered actual material and batch values.
- Re-import/overwrite should update only imported/source recipe material values and should preserve operator-entered actual material and batch values.
- Roll weights entered at the terminal must be linked to the same order/card.
- Roll number is an index starting at `1` and increasing upward for the order.
- Gross weight is entered by workers after each roll is counted.
- Net weight is calculated as `gross weight - order tare weight`.
- Per-roll net weight formula: `roll_net_weight = roll_gross_weight - tare_weight`.
- Total net weight formula: `total_net_weight = total_gross_weight - (number_of_rolls * tare_weight)`.
- Tare weight is stored once on the order/card.
- The same tare weight applies to every roll in the order.
- Maximum roll weight is stored on the order/card when provided by the shift manager.
- Maximum roll weight is informational for operators and must not block or validate roll entry in this pilot.
- Roll entries do not need notes for the pilot.
- Keep only latest values; no change history is required for the pilot.
- Every operator action that changes production data must persist immediately. There should not be a separate "save all" button for roll entries or timing actions.
- Terminal roll entry should use one fixed gross-weight input for adding the next roll.
- Pressing `Enter` in the fixed gross-weight input or clicking the add button should save the new roll immediately and clear/focus the input for the next roll.
- Roll numbers are assigned automatically starting at `1`.
- Previous gross weights should remain editable.
- Clearing a gross-weight value removes it from totals while keeping the row visible for correction.
- Deleting a roll removes that row and automatically renumbers later rolls so the printed roll list remains continuous.
- Net weight per roll should be stored or calculatable, but does not need to be shown to operators per roll.
- Operators should see total gross weight so far and total net weight so far.
- Weight inputs should support up to two decimal places.
- Workstation kilogram values should be displayed with exactly one digit after the decimal point.
- Use normal decimal rounding rules for displayed kilograms.
- Storage/calculation should preserve the needed precision even when the workstation display rounds to one decimal place.

Confirmed production timing behavior:

- Operators need a button to record the start of production for an order.
- Operators need pause functionality.
- After pause, operators need to restart/resume production.
- Finishing an order closes any active production time segment and completes the card. There is no separate stop button in the terminal workflow.
- Total production time should be calculated from the sum of each start/resume to pause/finish interval.
- Do not calculate total time as one naive `finish time - start time` if pauses exist.
- Start, pause, resume, and finish actions must persist immediately when clicked.
- If an operator tries to input a roll while no timer is active for that card, the app should warn them.
- Printing is available only after the card is completed.

Finish validation:

- `Finished` should be blocked unless tare weight is entered.
- `Finished` should be blocked unless the timer was started at least once.
- `Finished` should be blocked unless at least one gross roll weight exists.
- The app should not allow final finish when there are empty roll gaps between filled roll entries.
- If `Finished` is clicked while the card is running, the app should close the active time segment and complete the card.

Cancellation behavior:

- Operators and shift manager/admin can cancel cards.
- Cancellation does not require a reason.
- Cancelling changes the card status to `cancelled`.
- Cancelled cards are no longer active and should not appear in the main active queue.
- Cancelled cards remain visible with completed/cancelled job cards.
- Cancelling is reversible: clicking the cancel action again on a cancelled card changes it back to `pending`.
- This reversible cancel behavior should be available both from the terminal and from the shift-manager/admin page.

Terminal editable fields:

- Most imported operational-card fields should be read-only on the terminal.
- Operators should be able to edit fields that reflect actual machine-side material usage:
  - `Използван материал`, when the actual raw material differs from the planned/source raw material
  - `Партида`, the actual batch/lot used for the order
- Planned/source recipe materials from the technology card remain read-only on the terminal.
- These operator-entered material and batch fields are not source fields from the Excel database. In the current paper process, they are written directly on the operational card for auditability.
- Operators should be able to edit tare weight.
- Operators should be able to edit gross roll weights.
- Operators should be able to correct start/pause/resume/finish timing data when needed.
- Operators should be able to correct machine assignment if the real production machine changes.
- Machine assignment correction should move the card to the other machine queue.
- Reassignment should not allow a machine to end up with two running cards.
- Shift manager/admin page may allow broader editing of imported card fields, but this is separate from the terminal editing rules.

Implementation detail:

- Even though duplicate detection uses order number alone, the database should still use an internal primary key for each order/card and link roll entries to that internal ID. This avoids brittle relations while preserving the order number as the business identifier.
- Storing the raw imported CSV row as a backup is optional, but the app must store the imported fields in a readable structured form. Do not store only an opaque raw CSV blob.

## Data Transfer Options

Confirmed context:

- The Excel workbook lives on the shift manager's PC.
- The shift manager's PC is connected by LAN to the same network as the app server and terminal.
- The app is expected to run on the server/VM and be accessed over LAN by both the shift manager and the terminal.
- The shift manager may perform manual work to load orders if that keeps the pilot simple and safe.
- The top priorities for transfer are:
  - do not corrupt or modify the Excel source data
  - keep the process simple enough for a fast pilot
  - avoid excessive validation work
  - allow the shift manager to verify transferred data before it appears on the terminal

Current preferred direction:

- Build an Excel-side export action for the shift manager.
- The shift manager selects or marks the orders/cards to export.
- Excel export should use the currently selected rows.
- The export action creates a `.csv` file.
- One CSV should be able to contain several selected orders, with one row per order, so the shift manager can prepare a small queue at once.
- The app imports that `.csv` and shows imported orders as drafts.
- The shift manager reviews each draft in the app and clicks `Submit`.
- Submitted cards enter the terminal queue/list.

Confirmed CSV scope:

- Export only the fields needed for the extrusion pilot rather than the full `A:AY` source row.
- Avoid carrying fields that the app will not read or use.
- The CSV may contain multiple selected orders, one row per order.
- Duplicate detection in the app should use order number alone.
- CSV headers may use stable internal field names chosen by the implementation, for example `order_number` or `raw_material_a`.
- The workbook structure is stable, so internal CSV headers can be mapped by fixed source columns.
- User-facing labels in the app and print output must use the Bulgarian field names/operators expect from the operational card, not internal CSV names.
- App-only fields that are not source Excel fields should start blank after import, including `Използван материал`, `Партида`, and tare weight.

Confirmed export location convention:

- The macro should create an export/extract folder in the same root directory as the `.xlsm` workbook.
- Each export should create a new CSV file in that folder.
- Use a simple folder name such as `extracts`.
- Use timestamped filenames so exports do not overwrite each other, for example `extrusion_orders_YYYYMMDD_HHMMSS.csv`.

Validation direction:

- The export may export selected rows, but the app import must validate whether each imported row is usable for the extrusion pilot.
- If a row has no extrusion flag or empty/missing extrusion data, the app should notify the shift manager with a message such as `no extrusion step` and skip that row without saving a card.
- This validation belongs to CSV import review so unusable rows do not enter planning or the terminal queue.
- If an imported order number already exists, the app should warn and allow the shift manager to overwrite/re-import.
- Overwrite/re-import should update only imported/front-card/order information.
- Overwrite/re-import must not overwrite existing roll entries, gross weights, timing data, or other back-page/workstation-entered production data.

Important caveat:

- The user suggested building a small macro into Excel.
- Clarification: "set in stone" means the workbook structure will not change. It does not prohibit adding read-only macros.
- It is acceptable to modify the actual shift-manager `.xlsm` file to add export automation, as long as the automation only reads/exports and does not edit or write existing workbook data.

Fallback options if CSV export becomes too risky or slow:

- Shift manager copies a full row from `Database` and pastes it into the app.
- Shift manager copies a narrower extrusion-relevant range and pastes it into the app.
- App reads the workbook directly from a shared location.
- App provides another import mechanism derived from the workbook.

Observed copy/paste facts:

- Excel row copy produces tab-separated text.
- A full row through `AY` can be mapped positionally to the database columns.
- Copy/paste should preserve raw values because many workbook cells are human-entered strings rather than clean typed data.

Recommended pilot import flow:

1. Shift manager opens an import/load screen in the app.
2. Shift manager imports the `.csv` generated from Excel.
3. App parses the CSV into one or more persistent app records with draft/imported status.
4. App shows imported orders as drafts in the app.
5. Shift manager opens/views a draft.
6. Shift manager verifies that the data looks correct.
7. Shift manager submits/releases the draft.
8. Released card appears in the terminal execution list.

This preview-before-submit step is confirmed as desirable because it prevents randomly bad transferred data from immediately appearing at the workstation.

Queue behavior is confirmed as simple machine-based sequencing: active cards are assigned to one of four machines, sorted by normalized numeric position within each machine, and shown without complex scheduling logic. The sequence only affects display order; operators can still open and run any active card when the shift manager permits it.

Copy/paste remains acceptable as a fallback, but CSV export is preferred because it is less prone to manual paste/selection errors.

Database-design direction:

- The app database should respect how the Excel data is currently structured.
- Imported order/card fields should remain differentiated rather than collapsed into one blob.
- Roll weights entered at the terminal must be saved in the app database under the related order number.
- The data model should separate imported order/card fields from roll-weight entries while linking them to the same order/card.
- Imported CSV rows should create persistent draft/imported order/card records before terminal release.
- On draft submission, the app must check whether the order has already been submitted/imported previously.
- If submitting/importing would duplicate an existing order number, the app should prompt/warn the shift manager.
- The shift manager may choose to overwrite/re-import the order data after warning.
- Re-import overwrite must preserve existing roll/timing/workstation data.
- Duplicate detection should use order number alone.
- The exact database columns should be defined during implementation from the confirmed conceptual schema above.

## Printing Constraint

The terminal UI may be app-native, but the printed paper output must match the Excel operational card.

Confirmed print requirements:

- Printing implementation is flexible. Browser print, generated HTML/CSS, PDF generation, or another method is acceptable if it is simple, reliable, and produces the required paper output.
- Print the extrusion front.
- Print the back page.
- Output is always exactly two pages: extrusion front page plus back page.
- Paper size is A4.
- The app should generate two pages. Duplex/front-back printing on one sheet can be handled by printer settings.
- Printing must be possible from the workstation/terminal itself.
- Printing/reprinting should be possible from completed cards so mistakes can be corrected and the card can be printed again.
- Only completed cards can be printed.
- Completion closes timing before print is allowed.
- Printing should be impossible until the card/order is finished.
- Preserve the Excel card layout one-to-one as much as possible.
- The back page should keep the same 120-roll grid even if fewer rolls were produced.
- Mild additions are acceptable:
  - start time
  - stop/finish time
  - tare weight
  - total gross weight
  - total net weight

The current Excel `Technology Cards` extrusion block and `Page Back` sheet are the visual source of truth for print layout. The final printed output should be effectively indistinguishable from the old paper operational card, except for the confirmed additions above. Place the additions on the page while preserving the familiar two-page/120-roll structure as much as possible. The exact placement of those additions is not decided.

Print-layout follow-up:

- Create/agree a printable card template before final print implementation.
- The template should show where the added fields go, especially on the back page.
- The added fields currently expected are start time, stop/finish time, tare weight, total gross weight, and total net weight.
- This layout decision can happen after the captured data fields are final.

## Deferred Functionality

Do not build this in the current implementation unless the user explicitly reopens it:

- Per-machine roll-change timer. Possible shape discussed: a simple timer or countdown related to when rolls are removed/changed, useful because one terminal services multiple extrusion machines. This is deferred until after the prototype is tested and the user confirms whether it is useful.

## Infrastructure Context

Confirmed infrastructure facts from the discussion:

- The app will have a dedicated server.
- The app will have its own Proxmox server and its own VM.
- The Excel workbook lives on the shift manager's PC.
- The shift manager's PC is on the same LAN as the app server and terminal.
- The app is expected to be accessed over LAN by both the shift manager and terminal.
- Remote access from outside the network should use Tailscale.
- The app should not be exposed directly to the public internet.
- Tailscale may be installed on the app VM for app/server access.
- Tailscale may also be installed on the Proxmox host for remote administration, including access to the Proxmox web UI on port `8006` through the Tailscale IP.

## Approved Technical Direction

Use a simple local web app stack:

| Layer | Choice |
| --- | --- |
| Backend | Python + FastAPI |
| Database | SQLite |
| Frontend | Simple server-rendered pages or light HTML/JS |
| Printing | HTML/CSS print views tuned to match the Excel operational card |
| Excel export | VBA macro writes CSV |
| Deployment | One Linux VM on the Proxmox server |
| Access | Browser over LAN |

Rationale:

- Keep moving parts minimal.
- Avoid a separate database server.
- Keep backup/restore straightforward.
- Keep the system easy to inspect and repair.
- SQLite is sufficient for one terminal and one shift-manager workflow.

Backup approach:

- Store the SQLite database on the app VM/server.
- Support timestamped backups through the documented SQLite-safe backup command.
- A 10-minute backup interval is acceptable because the database will be small and storage space is available.
- Backups should use SQLite-safe backup behavior rather than unsafe raw copying while writes may be active.
- Retention policy can be simple, for example frequent backups for recent days and fewer older backups.

## Operational Backup And Recovery

Current local startup command:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open the terminal at:

- `http://127.0.0.1:8000/terminal`

Open shift-manager admin at:

- `http://127.0.0.1:8000/admin`

Health check:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/health -UseBasicParsing -TimeoutSec 5
```

Shutdown and restart:

1. In the server terminal window, press `Ctrl+C`.
2. Wait until the server process exits.
3. Start it again with the startup command above.
4. Run the health check and reopen `/terminal`.

Runtime database location:

- default: `data/extrusion_terminal.sqlite3`
- override: set `EXTRUSION_DB_PATH` before starting the app

Backup location:

- default: `backups/`
- override: set `EXTRUSION_BACKUP_DIR`
- backup filenames: `extrusion_terminal_YYYYMMDD_HHMMSS_microseconds.sqlite3`

Create a SQLite-safe backup:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m app.backups backup
```

The backup command uses SQLite's backup API, creates the backup directory if needed, and keeps the newest `144` matching backup files by default. Milestone 8 does not install a scheduler; if recurring 10-minute backups are needed before pilot use, run this command from the deployment's approved scheduler. To change retention for a run:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m app.backups backup --keep 288
```

Restore procedure:

1. Stop the app with `Ctrl+C`.
2. Choose the backup file to restore from `backups/`.
3. Restore into the runtime database path:

```powershell
.\.test-runtime\codex-venv\Scripts\python.exe -m app.backups restore --backup backups\extrusion_terminal_YYYYMMDD_HHMMSS_microseconds.sqlite3 --target data\extrusion_terminal.sqlite3
```

4. Start the app again.
5. Run the health check.
6. Open `/admin` and `/terminal` and verify the expected orders are present.

Do not restore over `data/extrusion_terminal.sqlite3` while the app is running. Do not copy the database file with normal file-copy commands as the backup method while the app may be writing.

Troubleshooting:

- Failed imports: confirm the uploaded file is CSV, has headers including `order_number` and `extrusion_flag`, and shows extrusion data. Rows without an extrusion step are reported in the import result and skipped.
- Planning sequence looks wrong: release, reassignment, and resequencing should normalize each active machine queue to `1..N`; refresh `/admin/planning` and report the affected order if a gap or duplicate remains.
- Server restart: stop with `Ctrl+C`, start with the documented startup command, run `/health`, then refresh the terminal browser. Data should persist because it is stored in SQLite, not browser memory.

Conflict handling:

- Each order/card should have an `updated_at` timestamp or version number.
- When admin or terminal opens a card, the app should remember the loaded version.
- On save/action, if the card was changed elsewhere after it was loaded, the app should warn and require reload before continuing.
- Admin edits after release/running should be allowed.
- Terminal should show admin changes after refresh/reload. The terminal also checks for active queue and selected-card changes in the background; when safe it refreshes automatically, and while an operator is typing it shows an updates-available prompt instead.
- Do not build complex merge tooling for this prototype.
- The goal is to prevent silent overwrites when shift manager/admin and terminal are editing the same card.

## Implementation Guardrails

- Keep the app focused on extrusion until the user expands scope.
- Do not implement non-extrusion card workflows.
- Do not implement detailed machine tracking beyond the confirmed simple machine assignment, sequencing, and quick navigation.
- Do not implement named-user authentication for the pilot.
- Do not implement locked finished orders or reopen workflows.
- Do not require cancellation reasons.
- Cancelled cards should be reversible back to pending.
- Do not treat submit/release as the first persistence point. Imported draft records should already be saved in the app.
- Persist each roll/timing change immediately to reduce data loss if the terminal crashes.
- Do not change the workbook's data structure. The user stated that the structure is set in stone.
- Read-only export macros are acceptable in the actual shift-manager workbook.
- Excel automation must not edit or write existing workbook data.
- Do not use `Technology Cards` or `Page Back` as authoritative data sources; they are derived layouts.
- Use `Database` rows as the source for order/card data.
- Preserve workbook values without aggressive normalization.
- Prefer a structured CSV import over manual paste if it can be built without endangering the Excel source workbook or delaying the pilot.
- Use the approved simple stack unless there is a concrete blocker: Python/FastAPI, SQLite, simple HTML/JS, HTML/CSS print views.
- Implement SQLite-safe backups.
- Use simple optimistic conflict detection with `updated_at` or a version number.
- Handle operation flags case-insensitively.
- Do not assume every quantity is numeric.
- Date/shift columns on the printed back page are retained visually but are not used as app inputs.
- Do not assume terminal results must be synchronized back to Excel.
- Keep confirmed facts separate from open decisions in future edits.
- Treat this app as a bounded pilot/prototype, not as a foundation for future feature expansion.

## Inspection Notes

The workbook was inspected programmatically with `openpyxl`. The file was readable, but file hashing failed because another process had the workbook open. If future agents need a stronger workbook fingerprint, close Excel or copy the workbook to a temporary path before hashing.
