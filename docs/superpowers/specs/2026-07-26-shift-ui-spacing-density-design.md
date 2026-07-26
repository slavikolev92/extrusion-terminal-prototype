# Shift UI Spacing And Density Design

## Goal

Polish the already approved shift-management screens and recover vertical space on the terminal without changing their behavior, typography, or touchscreen legibility.

## Approved adjustments

- Keep the start and end confirmation dialogs at the same 600 × 560 size and keep their existing typography.
- Redistribute confirmation-dialog spacing: add a modest gap between the details card and confirmation question, while removing equivalent unused space below the action row.
- Use the existing blue shift accent for the start-time icon in the active-shift overview and produced-amounts summary.
- Give the three produced-amounts metadata items equal width and equal internal spacing.
- At workstation-height viewports, slightly reduce the machine strip, selected-machine topbar, and Details-pane vertical spacing.
- Do not shrink fonts or recipe rows. Keep Details scrolling as a safety fallback for unusually long content.

## Verification

- Add focused render assertions for the approved CSS contracts.
- Verify the relevant shift flow and a fully populated recipe in the live app at 100% browser zoom.
- Capture fresh screenshots under `artifacts/ui-checks/`.
