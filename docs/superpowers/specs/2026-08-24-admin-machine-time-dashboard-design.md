# Admin Machine-Time Dashboard Design

## Purpose

Add a read-only admin dashboard that lets a shift manager review machine
execution in the resolved dashboard window, see pauses and periods without
production, and compare each order overlapping that window with earlier
comparable orders.

The accepted visual reference is
`ui-prototypes/admin-machine-time-dashboard.html`. Production implementation
must preserve that prototype's clean visual hierarchy and omit explanatory
training text, automatic verdicts, and status commentary.

## Scope

- Add one server-rendered admin page at `/admin/dashboard`.
- Make `/admin` redirect to `/admin/dashboard`.
- Use the approved admin navigation order: `Импорт` → `Планиране` →
  `Технологични карти` → `Табло` → `Настройки`. The older dashboard-first
  navigation direction is superseded; the logo follows the implemented admin
  navigation contract.
- Read existing `machines`, `cards`, `production_time_segments`, and
  `roll_entries` data only.
- Do not add a database migration, stored baseline, background service,
  polling API, WebSocket, or third-party dependency.
- Do not modify production records when the dashboard is opened or refreshed.

## Time Window And Presentation

- By default, the window is the rolling latest 24 hours ending when the request
  is rendered. A shift manager may select any completed `Europe/Sofia` calendar
  day, which runs from that local midnight to the next local midnight (and is
  therefore 23, 24, or 25 elapsed hours across daylight-saving transitions).
- Stored timestamps remain canonical UTC. All visible timestamps use
  `Europe/Sofia` civil time.
- The top timeline always shows all four fixed machines.
- Running segments overlapping the window are blue order intervals.
- A pause starts when a production segment ends with `end_reason = 'pause'`
  and ends at the next segment start, the card's finish time, or the request
  time while the card remains paused.
- The existing workflow may run another order while an earlier card remains
  paused on that machine. A running order takes visual precedence in the
  overlapping interval; orange pause time is shown only where no order is
  running.
- Every remaining uncovered interval is gray `Без производство` time.
- Intervals are clipped to the resolved window: either the rolling latest 24
  hours or the selected completed Sofia calendar day.
- The machine summary is `Активна <duration> (<percentage>%)`, where active
  time is the sum of clipped running segments and the percentage denominator
  is the resolved window's real elapsed duration.
- Rolling mode uses nine absolute three-hour ticks, including both boundaries.
  Calendar mode uses nine Sofia civil-time labels from `00:00` through `24:00`;
  their positions are proportional to the selected day's real elapsed 23, 24,
  or 25 hours rather than equally spaced by label count.
- Timeline order labels contain the order number without `#` or `№`, the
  order's current productivity in parentheses, and a one-line truncated
  customer name.
- Pause and inactive intervals show only their duration inside the bar.

## Timeline Interaction

- Hovering or focusing an order interval shows order number, customer,
  productivity, active duration for that displayed interval, start, and end.
- Hovering or focusing a pause or inactive interval shows its machine,
  duration, start, and end.
- Clicking a timeline interval does nothing and opens no dialog.
- Tooltips remain keyboard accessible and stay within the viewport.
- The Refresh button performs a normal page reload. No persistent
  `Обновено` label and no automatic refresh are added.

## Recent-Order Productivity Table

- The lower section is titled `Производителност по поръчки`.
- It contains one machine section for each of Machines 1 through 4.
- Each machine section lists each distinct order with a running segment that
  overlaps the resolved window. An order appears once even when it has multiple
  segments.
- Rows are ordered by the order's first overlapping segment within each
  machine.
- The displayed produced amount is the order's total recorded net kilograms,
  not only kilograms entered during the resolved window.
- The displayed active time is the order's complete recorded active time up
  to finish or request time, not only the clipped window portion.
- Productivity is total recorded net kilograms divided by complete recorded
  active hours. Produced kilograms and kilograms per hour are displayed as
  rounded whole numbers; durations are displayed as hours and minutes.
- Table headings retain the accepted two-line units: `Размер (мм)`,
  `Произведено (кг)`, and `Производителност (кг/ч)`.

## Historical Comparison

- A comparable order must be production-complete (`completed` or `archived`),
  use the same machine, have ended no later than the reviewed order's first
  start, and have exact normalized dimensions. Archiving does not remove
  otherwise valid production history.
- Dimension normalization parses the dedicated `size_thickness` field as
  numeric width and thickness separated by `/`. Decimal commas and decimal
  points are equivalent, and insignificant trailing zeroes do not change a
  match. Material and free-text product description are not matching inputs.
- The reviewed order is never included in its own baseline.
- Invalid or missing dimensions produce no baseline instead of an approximate
  match.
- With zero comparable orders, the gauge area is a clean, noninteractive
  blank line.
- With one comparable order, the gauge shows one historical point.
- With two or more comparable orders, the gauge shows their recorded minimum
  and maximum productivity.
- The current order's orange marker uses the same visual scale and may sit
  below, within, or above the blue historical range.
- Hovering or focusing a gauge shows the total number of comparable orders and
  at most the seven latest comparable orders with order number, dimensions,
  and productivity.
- Historical values are not silently removed as outliers. The dashboard is a
  transparent review tool, not an automatic judgment engine.

## Empty And Partial Data

- Machines with no activity still show a gray timeline filling the complete
  resolved window and an empty productivity table body.
- A recent order with no net kilograms or no positive active duration can
  still appear on the timeline, but its productivity and comparison gauge are
  left blank.
- Malformed dimensions leave the comparison gauge blank without preventing
  the rest of the dashboard from rendering.

## Verification

- All automated tests use a temporary SQLite database.
- Focused tests cover time-window clipping, pause/inactive classification,
  open segments, all four machines, exact dimension normalization, complete
  order productivity, zero/one/multiple comparisons, prior-only matching, and
  the seven-row tooltip cap.
- Window-mode tests prove rolling absolute three-hour ticks and the nine Sofia
  civil labels for ordinary, 23-hour, and 25-hour calendar days. They also
  prove that interval clipping, active-percentage denominator, overlapping-
  order membership, and the empty gray timeline all use the same resolved
  bounds and real elapsed duration.
- Route tests prove `/admin/dashboard` renders and `/admin` redirects there.
- Browser verification uses the local FastAPI app and repo-local Playwright,
  checks hover and keyboard tooltips, Refresh, customer truncation, all four
  machine groups, and absence of a useless horizontal scrollbar.
- Evidence is saved below `artifacts/ui-checks/admin-machine-time-dashboard/`.
- The full Python test suite and `git diff --check` run before completion is
  claimed.
