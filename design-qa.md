# Shift Management UI Design QA

## Comparison target

- Main shift window source: `/home/sk/projects/extrusion-terminal/source-files/main_shift_button.png`
- Approved start confirmation: `artifacts/ui-checks/shift-complete-final-gFbueg/start-shift-confirmation.png`
- Main shift window implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/active-shift-window.png`
- Full-recipe implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/full-recipe-layout.png`
- End confirmation implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/end-shift-confirmation.png`
- Full history implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/full-shift-history.png`
- Ended-shift summary implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/ended-shift-summary.png`
- Historical summary implementation: `artifacts/ui-checks/shift-complete-final-gFbueg/historical-shift-summary.png`
- Full-view comparison evidence: the source and latest `active-shift-window.png`
  were opened together at equal size; the full-recipe screenshot was inspected
  separately because the source mock does not define the terminal card layout.

## Normalization

- Source and implementation screenshots are 1536 × 1024 pixels at a 1536 × 1024 CSS viewport and device scale factor 1.
- The source and main implementation were compared without scaling or cropping.
- The user-approved product changes supersede the mock where they differ: the current shift uses a dropdown instead of a large numbered badge, the green active label is omitted, and start/end timestamps display to the minute.

## Required fidelity surfaces

- Fonts and typography: all shift windows use the existing Segoe UI stack and one consistent hierarchy. Shell titles are 27px/800, section headings are 22px/750, table headings are uniformly 14px/700 in the same gray, and both confirmations use the same 29px title, 18px supporting copy, 17px question, and 18px actions.
- Spacing and layout rhythm: the main screen follows the source's header/current-shift/history/footer sequence. The main dialog is now capped at 1180px, the current-shift card at 120px high, and the start icon at 36px, preserving the correction dropdown, start timestamp, and end action in one compact row. The end confirmation and approved start confirmation both measure exactly 600 × 560 CSS pixels. History and summaries use bounded table regions rather than extending the dialog indefinitely.
- Colors and visual tokens: white surfaces, pale-blue information cards, blue primary actions, muted secondary text, gray table headings, light borders, and the dimmed/blurred backdrop are consistent across every shift state.
- Image quality and asset fidelity: all visible shift icons are the supplied SVG assets. No emoji, text glyph, inline SVG, CSS drawing, or placeholder replaces a supplied asset. The browser check confirmed each required icon loaded successfully.
- Copy and content: all visible shift copy is Bulgarian. Shift dates no longer include the `г.` year suffix. Summary columns remain `Производствена поръчка`, `Клиент`, `Вид изделие`, `Брой ролки`, and `Бруто, кг`; gross kilograms use one decimal place. The disallowed item counter remains absent.
- Responsiveness: the complete browser workflow passed at 1536 × 1024 and 1366 × 768. A seven-component recipe with fully populated details may overflow at either viewport; the details pane scrolls and the final component remains reachable. The isolated fixture also demonstrates the state where all seven rows fit together at 1536 × 1024.
- Accessibility and interaction: dialog labels follow the visible pane, blocking confirmations cannot be dismissed with Escape or backdrop clicks, dismissible windows restore focus, and the clean-URL overview now has an explicit close control. Dismissible overview/history/summary parameters are removed from the address after rendering, so closing and refreshing cannot reopen them. Supplied icons are decorative where their text label already exists, and pagination exposes an accessible navigation label and current-page state.

## Pagination and bounded history

- The overview renders at most the five newest completed shifts.
- `Виж всички` renders ten shifts per page.
- The page strip shows at most five page numbers with `Назад` and `Напред` controls.
- Out-of-range page requests clamp to the nearest valid page.
- Opening a summary from a later history page preserves that page for the Back action.

## Comparison history

### Pass 1 — blocked

- P1: the original implementation used visually unrelated generic title bars, inconsistent widths, mixed typography, and sparse current-shift presentation.
- P1: the end confirmation did not use the approved start-confirmation structure.
- P2: history was unbounded and the overview showed only three rows.

Fixes: rebuilt the remaining states around the approved shift visual system, used the supplied icon set, separated current shift and history, added bounded pagination, and normalized all table and summary treatments.

### Pass 2 — passed

- The main comparison shows the same header/current/history/footer composition as the source while preserving the approved dropdown and removal of the redundant active badge.
- The focused comparison shows the start and end confirmations in identical 600 × 560 frames with matching typography, colors, information-card treatment, spacing system, and actions.
- Full history, ended summary, and historical summary use the same shell header, close treatment, border radius, table typography, metadata cards, and button language.
- No actionable P0, P1, or P2 mismatch remains.

### Pass 3 — passed

- User-reported P1: dismissible History, Overview, and historical summaries
  persisted their query parameters, so refresh reopened the window in kiosk
  mode. The transient parameters are now removed after rendering and again on
  close; browser checks cover all three states and a refresh.
- P1 found by the full-data check: a seven-component recipe was clipped with
  no operator scrolling. The details pane now scrolls, and the browser check
  proves the seventh component is reachable at 1366 × 768.
- P2: the overview occupied almost the entire smaller viewport. The main frame,
  current-shift card, icon, dropdown, and end action were reduced while keeping
  the accepted hierarchy and supplied assets.
- P2: clean-URL opening had no visible close button. The button is now present
  for every dismissible state.
- The source and post-fix screenshot were compared at the same 1536 × 1024
  viewport. No actionable P0, P1, or P2 mismatch remains.

### Pass 4 — final adversarial correction gate passed

- Dismissing History or a historical summary now makes the next header Shift
  action open the current-shift overview, including when the prior pane was
  rendered by a server navigation.
- Start and end confirmations and the reload-required gate now have explicit
  Tab/Shift+Tab, Escape, and backdrop browser coverage. Dismissible focus return
  is checked after a stable animation frame.
- The complete fresh temporary-database workflow passed with zero console/page
  errors, `integrity_check=ok`, and zero foreign-key errors. Evidence is under
  `artifacts/ui-checks/shift-task01-title-green/`.
- The independent final review found one remaining title mismatch. The active
  overview now uses the specified `Управление на смяната` title both on the
  initial server render and every client-side reopen; the browser workflow
  asserts that behavior directly.

## Intentional P3 differences

- The main implementation is slightly narrower than the source mock so it remains comfortable at the terminal's smaller verified viewport.
- The longer Bulgarian end-confirmation title wraps to two lines while retaining the same font size and weight as the approved start confirmation.
- Screenshot fixture data contains three recent rows; the automated behavior test proves the approved five-row maximum.

## Browser evidence

- Complete workflow command: temporary SQLite database plus `scripts/verify_shift_management_ui.mjs` against the live FastAPI app; final artifacts are under `artifacts/ui-checks/shift-complete-final-gFbueg/`.
- Result: passed.
- Primary interactions tested: configure shift count; select, preview, confirm, and start a shift; correct active shift number; open/close management; prove clean-URL close availability; prove Overview, History, and historical summaries remain closed after refresh; end confirmation Back and Confirm; acknowledge handoff summary; open all history; inspect historical summary; reach all seven recipe components; preserve live corrected roll totals; stale-page blocking; keyboard focus wrapping; Escape/backdrop rules; and pagination presence.
- Console and page errors: zero.
- Database checks: `PRAGMA integrity_check = ok`; `PRAGMA foreign_key_check` returned zero rows.

final result: passed
