# Task 2 Report: Planning Context And Unsent Sorting

## What Was Implemented

- Extended `DRAFT_SORT_LABELS` with `size_thickness` and `ordered_gross_kg`.
- Added decimal gross-weight sorting with blank/invalid values kept last for descending sorts.
- Added planning delivery-date formatting for ISO and `dd/mm/YYYY` inputs.
- Added planning display-row preparation for delivery date, size, and gross weight.
- Applied prepared rows to both unsent cards and machine queues while preserving machine queue order.
- Added route coverage for size/gross sorting and for keeping machine queues in sequence order.
- Updated the compact planning render test to the accepted Task 2/Task 3 markup contract. Template/CSS changes were intentionally not made.

## Tests Run

- `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -k "planning_renders_compact or sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q`
  - Initial RED: `2 failed, 2 passed, 30 deselected`.
- `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -k "sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q`
  - GREEN: `3 passed, 31 deselected`.
- `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -q`
  - `33 passed, 1 failed`; the only failure is the intentionally updated compact-render assertion requiring the later Task 3 template/CSS redesign.
- `source .venv/bin/activate && python -m compileall -q app tests`
  - Passed.
- `git diff --check`
  - Passed.

## TDD Evidence

RED was observed before production changes with the focused command above. The expected failures were the new compact planning markup contract and unsupported size sorting. After implementing the specified context and sorting helpers, the focused GREEN command passed all three sorting/queue tests.

## Files Changed

- `app/main.py`
- `tests/test_admin_routes.py`

## Self-Review Findings Or Concerns

- No Task 3 template or CSS work was included.
- The compact render test remains red by design until the later template task supplies the accepted markup and formatted display values.
- Machine queue data is prepared for display but remains in the existing `fetch_machine_queues()` order; only unsent cards are sorted by draft headers.

## Fix Round 1/5

### Finding Fixed

`draft_decimal_sort_value` now treats non-finite Decimal values, including `NaN`, `Infinity`, and `-Infinity`, as missing gross values. They therefore remain in the missing-value group rather than reaching Decimal comparison during descending sorting.

### Focused TDD Evidence

- RED: `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -k "sorts_unreleased_cards_by_size_and_gross" -q`
  - Result: `1 failed, 33 deselected`; the route raised `decimal.InvalidOperation` while sorting the imported `ordered_gross_kg="NaN"` card.
- GREEN: `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -k "sorts_unreleased_cards_by_size_and_gross" -q`
  - Result: `1 passed, 33 deselected`.
- Focused sorting suite: `source .venv/bin/activate && python -m pytest tests/test_admin_routes.py -k "sorts_unreleased_cards or sort_does_not_reorder_machine_queues" -q`
  - Result: `3 passed, 31 deselected`.

### Fix Round Files

- `app/main.py`
- `tests/test_admin_routes.py`
