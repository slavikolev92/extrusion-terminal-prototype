# Design QA: Rewinding And Roll Controls Prototype

**Source visual truth**

- `artifacts/ui-checks/rewinding-ui-prototype/02-current-terminal-reference-1920x768.png`
- Focused roll pane: `artifacts/ui-checks/rewinding-ui-prototype/02b-current-roll-pane-reference.png`
- User-supplied field and table reference:
  `v2-files/prototypes/rewinding-roll-controls/example.JPG` (1174 × 765 pixels).

**Rendered implementation**

- `artifacts/ui-checks/rewinding-ui-prototype/03-prototype-default-1920x768.png`
- Focused roll pane: `artifacts/ui-checks/rewinding-ui-prototype/04-prototype-roll-pane-default.png`
- Standalone HTML: `artifacts/ui-checks/rewinding-ui-prototype/08-standalone-prototype-1920x768.png`
- Refined focused roll pane:
  `artifacts/ui-checks/rewinding-ui-prototype/12-refined-roll-pane-1920x768.png`
- Narrow-width check:
  `artifacts/ui-checks/rewinding-ui-prototype/13-refined-prototype-1366x768.png`

**Comparison setup**

- State: running card with three rolls, active shift, and pallet input.
- Primary viewport: 1920 × 768 CSS pixels at device scale factor 1.
- Responsive viewport: 1366 × 768 CSS pixels at device scale factor 1.
- Source and implementation captures use the same route content, browser,
  viewport, density, and temporary database fixture.
- The user-supplied image is an illustrative component reference rather than a
  full-screen source. Its field-label placement and evenly distributed table
  geometry were compared to the focused terminal pane; its placeholder values
  and omitted net column were not treated as required content.
- Full-view comparison confirmed that machine navigation, order header, primary
  actions, details, recipe, roll entry, and totals retain their source geometry.
- Refined focused side-by-side evidence:
  `artifacts/ui-checks/rewinding-ui-prototype/14-refined-fields-side-by-side.png`
  (1900 × 1009 pixels at device scale factor 1).

**Findings**

- No actionable P0, P1, or P2 fidelity differences remain.
- The three roll-entry captions sit across the top input borders as in the
  supplied reference. The fields remain individual controls and the unwanted
  border around their complete group is absent.
- The roll table reads `№`, gross, core, net, pallet, then edit. All five
  information columns have equal tracks; only the pencil remains a compact
  action column. The weight headers omit `кг` as requested.
- Gross, core/tare, and net table values consistently show one decimal place;
  roll and pallet numbers remain whole integers.
- Start, Pause, and End have matching 150-pixel widths. Playwright measured
  nonnegative, balanced internal space around all three contents; the previously
  clipped `Приключи` content now has at least 11 pixels on both sides.
- The new-roll, core, pallet, and Add controls share one bottom alignment; core
  and pallet inputs have matching widths. The 126-pixel Add button gives the
  icon/text group 15.7 pixels on both sides, and the measured vertical centers
  of the plus and label are identical.
- The `Ролка` and `Шпула` field captions were verified as identical Segoe UI,
  13-pixel, weight-600, 16-pixel-line-height text and were deliberately left
  unchanged.
- The roll number and its heading are centered within the same full-width track
  used by the other information columns.
- Fonts and typography continue to use the terminal's existing Segoe UI/Arial
  stack, sizes, weights, and hierarchy. The supplied image's larger type was not
  copied because the real terminal is denser and must remain readable at
  1366 × 768.
- Spacing and layout rhythm remain anchored to the existing 510-pixel roll
  panel. The roll panel and table have no horizontal overflow at either tested
  viewport.
- Colors and tokens reuse the existing terminal navy, neutral border, blue
  correction, red destructive, green timing, and amber attention semantics.
- Image and icon fidelity uses the existing project clock/switch assets plus a
  system pencil icon; the Kolev logo and machine icons are preserved from the
  rendered source.
- Copy is short, Bulgarian, and localized to the control it affects.

**Comparison history**

1. Initial prototype review found one P2 semantic-color issue: the rewinding
   dialog's Save button inherited the red finish/destructive style.
2. The Save and timer-start actions were changed to the terminal navy action
   color in `prototype.css` and `prototype.js`.
3. Post-fix evidence in
   `artifacts/ui-checks/rewinding-ui-prototype/04b-prototype-rewinding-dialog-1920x768.png`
   confirms the corrected action hierarchy.
4. The July 26 refinement identified P2 table-order, uneven sizing, inconsistent
   decimal precision, grouped-border, and field-label differences from the
   supplied example.
5. The fields, table grid, decimal formatting, and lifecycle button sizing were
   corrected in `prototype.css` and `prototype.js`.
6. Post-fix evidence is captured at 1920 × 768 and 1366 × 768 in files `12`,
   `13`, and the same-input side-by-side comparison `14` listed above.
7. User review found four P2 issues: the requested precision was one decimal,
   the roll number was too close to the left edge, `Приключи` was clipped inside
   an undersized equal-width control, and the Add content appeared misaligned.
8. Browser geometry confirmed the lifecycle button was 110 pixels wide while
   its End content required about 148 pixels, and the Add button was 100 pixels
   wide while its content required about 119 pixels. It also confirmed the Add
   icon/text centers and Roll/Core caption typography were already identical.
9. The lifecycle controls were widened to 150 pixels, Add to 126 pixels, the
   roll-number track was centered, and all displayed gross/core/net values were
   changed to one decimal. Revised evidence in files `12`–`14` passed the same
   browser checks at both viewports.
10. Final user review requested fully equal table distribution and removal of
    unit suffixes from the headers. The first five tracks now measure equally,
    and the labels are `№`, `Бруто`, `Шпула`, `Нето`, and `Палет`. Revised
    evidence in files `12`–`14` passed again at both viewports.

**Primary interactions tested**

- Open rewinding dialog, save a positive count, and update the button marker.
- Open roll-change dialog, start a countdown, and update the button state.
- Open a single roll with its pencil action.
- Preserve the approved table order while opening and closing per-roll editing.
- Open the selected roll's delete confirmation.
- Load and operate the generated standalone HTML without a server.
- Assert equal lifecycle-button widths, equal core/pallet input widths, aligned
  input/button bottoms, embedded field labels, five equal table information
  columns, one-decimal weights, balanced button-content padding, and no 1366-pixel
  clipping.
- Browser console and page errors checked during generation.

**Implementation checklist**

1. Obtain user approval of the prototype layout and wording.
2. Regenerate against the completed blocker branch/working tree.
3. Write the feature specification and implementation plan.
4. Implement backend state, migration, validation, conflict handling, and tests
   before connecting the approved production UI.

**Follow-up polish**

- None required before user review. Any requested visual change should be made
  in this prototype before the implementation plan is written.

final result: passed
