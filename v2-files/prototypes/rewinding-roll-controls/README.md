# Rewinding And Roll Controls Prototype

This is a standalone visual prototype derived from the current rendered
`/terminal/cards/1` screen on July 26, 2026. The reference includes the active
shift-management and pallet-field work that was present in the working tree at
capture time. It does not modify the production template, routes, or database.

Open `prototype.html` directly in a browser. The following interactions are
available without a server:

- record, change, or clear an informational rewinding-roll count;
- set a roll-change interval and view the countdown in the secondary control;
- open one roll at a time with its pencil icon;
- edit that roll's pallet, gross weight, and tare weight using the existing
  correction presentation;
- open the roll-specific delete confirmation; and
- review gross, core, and net values at a consistent one-decimal precision.

## Approved hierarchy represented here

1. Start, Pause, and End remain the primary order lifecycle controls.
2. Rewinding and Roll Change are compact secondary controls beside the
   `Ролки` heading.
3. Add remains the primary local action for the new-roll input.
4. Every existing roll has one pencil icon.
5. Save, Cancel, and Delete appear only after a particular roll is selected for
   editing.
6. The previous order-level overflow menu is absent from the prototype.
7. Start, Pause, and End use the same 150-pixel width so the longer End label
   retains visible padding.
8. The roll-entry fields use border-embedded labels `Ролка`, `Шпула`, and
   `Палет`; the surrounding mini-panel border is removed.
9. The roll table order is `№`, `Бруто`, `Шпула`, `Нето`, `Палет`, followed by
   the pencil action. All five information columns share equal widths; the
   pencil remains a compact action column.

## Source files

- `prototype.css` contains only the proposed visual additions and overrides.
- `prototype.js` contains the prototype-only interactions.
- `generate-prototype.mjs` renders the current terminal, applies the proposal,
  captures browser evidence, and regenerates the standalone HTML file.
- `verify-prototype.mjs` verifies the approved labels, table order, decimal
  precision, control sizing, content padding, alignment, interaction behavior,
  and 1366-pixel
  fit.
- `prototype.html` is the generated, self-contained review artifact.

The prototype uses temporary/example state only. It does not represent the
future persistence, database migration, status transition, concurrency, or
server-side validation implementation.

## Regeneration

Start the app against a guarded temporary database, then run:

```bash
BASE_URL=http://127.0.0.1:8014 \
  node v2-files/prototypes/rewinding-roll-controls/generate-prototype.mjs
```

With the standalone preview server running on port `8765`, verify it with:

```bash
PROTOTYPE_URL=http://127.0.0.1:8765/prototype.html \
  node v2-files/prototypes/rewinding-roll-controls/verify-prototype.mjs
```

Before implementation, regenerate this prototype against the post-blocker
terminal and reconcile any changes in the roll panel. Do not copy the generated
full-page HTML into the Jinja template; transfer the approved focused markup,
styles, and interactions from the source files instead.
