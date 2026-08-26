# Task 19: Physical-Workstation Maintenance Display

Status: source implementation, automated verification, visual verification,
and review are complete as of August 8, 2026. The functionality has not yet
been installed or tested on the physical workstation.

## Outcome

The repository now contains one self-contained, copyable bundle:

```text
workstation-maintenance/
```

It provides workstation-only maintenance controls without modifying the
FastAPI application, SQLite schema/data, production lifecycle, deployment
script, or base kiosk provisioner.

The installed administrator interface is:

```text
sudo extrusion-kiosk-maintenance notify MINUTES
sudo extrusion-kiosk-maintenance on
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance off
```

- `notify MINUTES` shows the operator an informational Bulgarian dialog with
  the accepted gears image and one `OK` button. It waits for acknowledgment but
  creates no timer, schedule, or automatic maintenance transition.
- `on` manually restarts only the kiosk user's supported browser processes
  (`chromium`, `chromium-browser`, or `google-chrome`) and covers the physical
  kiosk with the local Bulgarian maintenance page.
- `status` reports whether the persistent workstation marker selects terminal
  or maintenance mode; it is not an application-health check.
- `off` manually removes the marker and restarts Chromium at the configured
  terminal URL with a fresh HTTP cache while preserving its profile and local
  storage.

The maintenance cover affects only the physical kiosk. It is not access
control and does not prevent another LAN client from reaching the application.

## Completed Source Work

The bundle contains:

- the controller and maintenance-aware Chromium launcher;
- the static Bulgarian maintenance page and accepted gears image;
- an idempotent installer for the already-provisioned Debian kiosk;
- controller, launcher, page, asset, and installer subprocess tests;
- a repository-local Playwright visual verifier; and
- the authoritative installation, operation, and troubleshooting runbook at
  `workstation-maintenance/README.md`.

Final local verification passed:

```text
68 workstation-maintenance tests
1,123 complete repository tests
Bash, POSIX shell, and Node syntax checks
Playwright 1.61.0 local-page verification at 1366x768
```

The accepted source and bundled `gears.png` files are byte-identical. The
verified screenshot is retained at:

```text
artifacts/ui-checks/workstation-maintenance/maintenance-screen.png
```

## Why Installation Is Separate

The source task is complete, but installation and live acceptance are kept as
a separate explicitly authorized workstation patch because they can disturb
the physical terminal:

- installation replaces the kiosk launcher and requires one reboot;
- `notify` deliberately covers the running terminal with a dialog until the
  operator clicks `OK`;
- `on` and `off` terminate and relaunch Chromium; and
- unsaved browser input could be lost during a browser restart.

The app service, database, production data, and LAN clients are not changed,
but the workstation test must still be scheduled while no operator is entering
data.

## Remaining Operational Gate

In the next user-authorized patch:

1. Choose a quiet workstation window and confirm no operator is entering data.
2. Read `workstation-maintenance/README.md` as the authoritative runbook.
3. Verify the workstation SSH host identity; do not bypass a host-key warning.
4. Copy the complete `workstation-maintenance/` folder to the workstation.
5. Run its installer and perform the one required reboot.
6. Confirm the initial mode is `mode=terminal`.
7. With someone watching the physical screen, verify `notify 30` and its `OK`
   acknowledgment without any mode change.
8. Run `on`, confirm the maintenance screen and `mode=maintenance`, and confirm
   another LAN client can still reach the application.
9. Run `off`, confirm the terminal returns and reports `mode=terminal`, and
   check that expected browser-local state remains available.

No agent is authorized to perform these live actions merely because this task
record exists. Copying, installation, reboot, and live maintenance commands
still require explicit user approval.

## Durable References

- Authoritative runbook: `workstation-maintenance/README.md`
- Approved design:
  `docs/superpowers/specs/2026-08-07-workstation-maintenance-display-design.md`
- Approved implementation plan:
  `docs/superpowers/plans/2026-08-07-workstation-maintenance-display.md`

After the live installation and acceptance sequence passes, update
`v2-files/PLAN.md` with the workstation result and move this record to
`v2-files/archive/` as completed operational evidence.
