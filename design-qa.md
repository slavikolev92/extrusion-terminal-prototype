# Shift Management UI Redesign — Design QA

## Comparison target

- Source visual truth:
  - `/home/sk/projects/extrusion-terminal/source-files/new-design.JPG` — header direction only; source pixels `1077 × 735`, 120 DPI metadata.
  - `/home/sk/projects/extrusion-terminal/source-files/screen_start_shift.png` — start-selection direction; source pixels `1536 × 1024`.
  - `/home/sk/projects/extrusion-terminal/source-files/screen_start_shift_confirmation.png` — start-confirmation direction; source pixels `1672 × 941`.
  - `/home/sk/projects/extrusion-terminal/source-files/main_shift_button.png` — active management and history-preview direction; source pixels `1536 × 1024`.
- Browser-rendered implementation evidence:
  - `artifacts/ui-checks/shift-final-review-UarPfS/qa-terminal-header-1077x735.png` — `1077 × 735` CSS pixels.
  - `artifacts/ui-checks/shift-final-review-UarPfS/start-shift-selection.png` — `1536 × 1024` CSS pixels.
  - `artifacts/ui-checks/shift-final-review-UarPfS/qa-start-shift-confirmation-1672x941.png` — `1672 × 941` CSS pixels.
  - `artifacts/ui-checks/shift-final-review-UarPfS/active-shift-window.png` — `1536 × 1024` CSS pixels.
- Browser density: Playwright Chromium `deviceScaleFactor = 1`; implementation pixel dimensions equal their CSS viewport dimensions. No density downsampling was needed.
- States: inactive blocking gate, start selection, start confirmation before persistence, active header, active shift overview with three historical rows, full history, blocking handoff summary, and dismissible historical summary.

## Complete fixed-HEAD evidence

- The complete nine-screenshot browser set and manifest are under
  `artifacts/ui-checks/shift-final-review-UarPfS/`.
- The inspected states are terminal header without an active shift, start
  selection, start confirmation, active terminal header, active overview, full
  history, blocking ended-shift summary, dismissible historical summary, and
  admin shift-count configuration.
- `shift-management-ui-summary.json` records every required evidence path and
  the isolated database checks for this fixed HEAD.

## Findings

No actionable P0, P1, or P2 mismatch remains.

- Fonts and typography: the implementation uses the established terminal type stack, keeps Bulgarian labels legible at both required viewports, preserves hierarchy, and does not wrap or overflow any global header action. The source uses a lighter visual weight in places; the terminal's existing heavier operational type is an intentional product-system constraint.
- Spacing and layout rhythm: the header is truly centered against the viewport and its three actions have equal widths. At both required viewports the verifier also proves the logo and shift action stay within the header and viewport, the logo/center/shift regions do not overlap, and the shift action meets the computed right content edge. The start and confirmation dialogs, current-shift card, and history table are intentionally more compact than the exploratory sources, matching the approved written overrides.
- Colors and visual tokens: white surfaces, cool gray borders, blue primary actions, green active status, and gray inactive status are coherent with the source direction and the existing terminal tokens. The red irreversible end-shift action is an intentional semantic terminal convention.
- Image quality and asset fidelity: the existing Kolev logo is sharp at both comparison sizes. The supplied mockup icons were not recreated because the task explicitly forbids adding images, icons, or dependencies and confirms the existing logo asset is sufficient. No placeholder, custom SVG, CSS-art, or generated asset was introduced.
- Copy and content: the implemented text is Bulgarian throughout the tested shift flow. The written product copy overrides exploratory source wording where they differ. Stored timestamps remain UTC. Live previews and persisted shift timestamps are both displayed explicitly in `Europe/Sofia`, with Bulgarian month names and no visible seconds; summer and winter UTC offsets have Python coverage.
- Interaction and accessibility: blocking gate, start/end confirmation, and handoff states remain open on Escape and backdrop interaction and make the terminal inert where required; only their explicit actions advance or return. Overview, history, and historical-summary states close on Escape or backdrop and return focus to the shift header action. Tab and Shift+Tab wrapping is exercised in the blocking gate and active overview. Start confirmation persists nothing until `Потвърди`. `Виж всички`, `Преглед`, historical `Назад`, and handoff `Продължи` all reach their required states in the same modal flow.

## Browser and data checks

- Focused affected suite:
  `.venv/bin/python -m pytest tests/test_shift_routes.py tests/test_terminal_v8_render.py tests/test_shift_management_ui_script_safety.py tests/test_shift_management.py tests/test_roll_entry.py tests/test_admin_production_corrections.py -q`
  — `198 passed`.
- Full suite: `.venv/bin/python -m pytest -q` — `552 passed`.
- Static verification: `.venv/bin/python -m compileall app tests`,
  `node --check scripts/verify_shift_management_ui.mjs`, and
  `git diff --check` — all exited `0`.
- Primary viewport: `1536 × 1024`.
- Responsive verification viewport: `1366 × 768`.
- Additional source-native QA viewports: `1077 × 735` and `1672 × 941`.
- Primary interactions tested: configure shifts; import/release two cards; select and confirm a shift; compare the live Sofia minute immediately before confirmation with the saved Sofia start display; exercise blocking and dismissible Escape/backdrop behavior, focus return, and keyboard focus wrapping; start work; save tare; add and correct rolls; correct the active shift number; end a shift; continue through handoff; open full history; open and return from a historical summary; reject stale second-page work; confirm finish while polling is suspended.
- Browser errors: zero uncaught page errors and zero console errors.
- Database checks: `PRAGMA integrity_check = ok`; `PRAGMA foreign_key_check = 0 rows`.
- Screenshot contract: all nine required files exist and have nonzero sizes. The durable manifest is `artifacts/ui-checks/shift-final-review-UarPfS/shift-management-ui-summary.json`.

## Comparison history

1. Initial browser GREEN capture: `artifacts/ui-checks/shift-redesign-green-4C53WV/`. Inspection found no implementation P0/P1/P2 issue, but the header and confirmation sources used different native dimensions from the primary `1536 × 1024` capture.
2. Evidence-normalization iteration: added native-size implementation captures at `1077 × 735` and `1672 × 941`, reran the complete workflow, and produced `artifacts/ui-checks/shift-redesign-final-TtWCu8/`.
3. Final full and focused combined inspection: confirmed the remaining scale/icon/style differences are the binding compact-layout, existing-design-system, and no-new-assets overrides. No application visual fix or recapture loop was required.
4. Final-review fix verification: `artifacts/ui-checks/shift-final-review-UarPfS/` uses a `Europe/Sofia` Playwright context, proves the live-to-saved minute boundary, strengthened header containment/collision/right-edge geometry, and modal Escape/backdrop/focus behavior, then captures and inspects a fresh complete evidence set.

## Exact repeatable browser command

Run from the repository root. This uses isolated port `8011`, a fresh ignored SQLite database, and a cleanup trap; it does not touch or stop a process on port `8000`.

```bash
mkdir -p artifacts/ui-checks
UI_REDESIGN_DIR="$(mktemp -d "$PWD/artifacts/ui-checks/shift-redesign-XXXXXX")"
EXTRUSION_DATA_DIR="$UI_REDESIGN_DIR" \
EXTRUSION_DB_PATH="$UI_REDESIGN_DIR/shift-ui.sqlite3" \
  .venv/bin/python -c "from app.db import init_db; init_db()"
EXTRUSION_DATA_DIR="$UI_REDESIGN_DIR" \
EXTRUSION_DB_PATH="$UI_REDESIGN_DIR/shift-ui.sqlite3" \
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8011 \
  >"$UI_REDESIGN_DIR/server.log" 2>&1 &
UI_REDESIGN_SERVER_PID=$!
trap 'kill "$UI_REDESIGN_SERVER_PID" 2>/dev/null || true' EXIT
for attempt in $(seq 1 100); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null; then
    break
  fi
  sleep 0.1
done
curl -fsS http://127.0.0.1:8011/health >/dev/null
BASE_URL=http://127.0.0.1:8011 \
ARTIFACT_DIR="$UI_REDESIGN_DIR" \
  node scripts/verify_shift_management_ui.mjs
kill "$UI_REDESIGN_SERVER_PID"
wait "$UI_REDESIGN_SERVER_PID" || true
trap - EXIT
```

## Follow-up polish

No P3 follow-up is recommended for this bounded pilot slice.

final result: passed
