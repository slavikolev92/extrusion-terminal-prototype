# Terminal Roll Input Focus Design

Date: 2026-07-22

## Goal

Reduce operator clicks during normal film-roll entry on `/terminal`.

When the selected card is actively running, the terminal should place the text cursor in the `Нова ролка, кг` input automatically after page load. This covers switching to a machine with a running card, starting a pending card, and returning after a successful roll entry.

## Confirmed Behavior

- Focus applies only when the selected card status is `running`.
- Focus does not apply when no card is selected.
- Focus does not apply for `pending`, `paused`, `completed`, `archived`, or `cancelled` cards.
- After clicking a machine whose selected/focus card is running, the loaded page focuses `Нова ролка, кг`.
- After successful `Старт`, the redirected running-card page focuses `Нова ролка, кг`.
- After successful new-roll entry, including pressing `Enter`, the redirected page focuses `Нова ролка, кг` again.
- After ordinary new-roll validation errors, the page focuses `Нова ролка, кг` so the operator can correct the value.
- Stale/conflict states take priority: when a reload-required alert is shown, focus must not move to the roll input.
- Roll correction mode takes priority: when roll correction mode is open, focus remains with the correction workflow and must not move to the new-roll input.

## Implementation Shape

Keep the behavior local to the server-rendered terminal UI.

- Mark the `Нова ролка, кг` input with a dedicated data attribute only when `selected_card.status == "running"`.
- Add a small JavaScript helper in `app/templates/terminal.html` that runs once on initial page load.
- The helper should find the marked input, check that it is enabled, and call `focus()`.
- The helper should skip focus when the terminal refresh/conflict alert exists.
- The helper should skip focus when roll correction mode starts open.

No route, database, production-rule, import, admin, or print behavior changes are required.

## Error Handling

Backend validation remains authoritative. This design only changes browser focus.

If a normal new-roll validation error renders under the input, the input remains the focus target because the selected card is still running and the operator should correct the same field.

If stale edit/conflict handling renders the reload-required alert, focus must not move to the input because the next valid action is reload.

## Testing

Automated render tests should verify:

- running cards render the new-roll focus marker;
- non-running cards do not render the marker;
- the focus script includes guards for conflict/reload alerts and roll correction mode;
- the existing new-roll form remains outside dirty-autosave behavior.

Browser verification should use a temporary SQLite database and Playwright to confirm:

- opening a running card places browser focus in `Нова ролка, кг`;
- entering a roll and pressing `Enter` returns with focus back in `Нова ролка, кг`;
- a stale/conflict page does not focus the roll input.

Save at least one relevant screenshot under `artifacts/ui-checks/`.

## Out Of Scope

- Changing when roll entry is allowed.
- Adding focus behavior to completed-card correction screens.
- Adding keyboard shortcuts.
- Changing machine-selection behavior.
- Changing backend route redirects.
- Changing dirty-autosave behavior for recipe or tare fields.
