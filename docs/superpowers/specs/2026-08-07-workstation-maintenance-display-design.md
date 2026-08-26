# Workstation Maintenance Display Design

**Date:** 2026-08-07
**Status:** Approved through the user's packaging and execution direction

## Purpose

Provide a small, manually controlled workstation utility that warns the
operator about future maintenance, covers the physical Chromium kiosk with a
local maintenance page when maintenance actually begins, and restores the
terminal afterward.

This is not FastAPI functionality. It does not create application maintenance
state, change SQLite data, block the LAN application, or automate deployment.
It is workstation operational tooling whose canonical, reproducible source is
stored in this repository.

## Operator Workflow

The administrator connects to the workstation through SSH and runs:

```text
sudo extrusion-kiosk-maintenance notify 30
sudo extrusion-kiosk-maintenance on
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance off
```

- `notify MINUTES` opens one informational dialog over the physical kiosk. It
  contains the gears image, Bulgarian warning text, and one `OK` button.
- The notification is not a timer. It stores no schedule and never enables
  maintenance. The SSH command waits until the operator clicks `OK`; a
  successful return is the administrator's acknowledgment signal.
- `on` is run separately when the administrator decides maintenance begins. It
  switches the physical kiosk to the local maintenance page.
- `off` is run separately after the application update and verification. It
  returns the kiosk to the configured terminal URL with a fresh browser cache.
- `status` reports only whether the workstation marker currently selects
  `maintenance` or `terminal` mode.

There is no countdown, automatic transition, background timer, deployment
hook, production-state check, polling loop, or automatic completion.

## Repository Bundle

All source and support files for this functionality live together in one flat
folder at the repository root:

```text
workstation-maintenance/
├── README.md
├── install.sh
├── extrusion-kiosk-maintenance
├── extrusion-kiosk-session
├── maintenance.html
├── gears.png
├── test_workstation_maintenance.py
└── verify-ui.mjs
```

The folder is deliberately self-contained:

- `install.sh` installs or refreshes the workstation functionality;
- `extrusion-kiosk-maintenance` implements `notify`, `on`, `off`, and `status`;
- `extrusion-kiosk-session` is the maintenance-aware replacement for the
  existing Chromium kiosk launcher;
- `maintenance.html` and `gears.png` are the network-independent maintenance
  display;
- `test_workstation_maintenance.py` tests the scripts and bundle contract with
  temporary paths and fake process/graphical commands;
- `verify-ui.mjs` renders the local page using repository-local Playwright;
- `README.md` contains the exact copy, install, operating, recovery, and
  verification commands.

The image is copied byte-for-byte from the user-selected
`ui-prototypes/gears.png`. The visual hierarchy follows
`ui-prototypes/thumb_u.min.webp`; the screenshot itself is not embedded.

This bundle is operational source inside the repository, but it is outside the
FastAPI application. Nothing under `app/` imports or serves it.

## Copy and Installation Flow

The complete folder is copied to the existing workstation administrator's
home directory and is kept there so installation can be inspected or rerun:

```bash
scp -r workstation-maintenance extrusion-terminal@100.94.38.101:~/
ssh -t extrusion-terminal@100.94.38.101 \
  'cd ~/workstation-maintenance && sudo bash install.sh'
```

The installer resolves every input relative to its own directory, so it does
not depend on the repository or the caller's current directory after the
folder has been copied.

Before changing the workstation, `install.sh` verifies:

- it is running as root;
- every bundle file required at runtime exists and is readable;
- the dedicated `kiosk` user already exists;
- `/etc/extrusion-kiosk-url` exists and is readable;
- the existing kiosk launcher/session has already been provisioned.

It then installs YAD using Debian's package manager and installs:

```text
/usr/local/bin/extrusion-kiosk-maintenance
/usr/local/bin/extrusion-kiosk-session
/usr/local/share/extrusion-kiosk/maintenance.html
/usr/local/share/extrusion-kiosk/gears.png
/var/lib/extrusion-kiosk/
```

File modes are explicit: executables `0755`, page/image `0644`, installed
directories `0755`. The installer neither creates nor removes the
`maintenance-enabled` marker. Repeating installation is safe and preserves the
current terminal/maintenance selection.

The currently running kiosk launcher is an already-started shell process, so
the newly installed launcher takes effect after one deliberate workstation
reboot. The installer prints the exact reboot and post-reboot verification
commands; it does not reboot automatically.

The existing `scripts/provision_workstation_kiosk.sh` is not coupled to this
bundle. If base kiosk provisioning is ever rerun, the administrator must rerun
`workstation-maintenance/install.sh` afterward because the base provisioner
may restore its original launcher.

## Installed Runtime Architecture

The installed launcher remains responsible for starting and relaunching
Chromium. Before each start, it selects exactly one page:

- marker absent: the configured URL from `/etc/extrusion-kiosk-url`;
- marker present:
  `file:///usr/local/share/extrusion-kiosk/maintenance.html`.

The marker path is:

```text
/var/lib/extrusion-kiosk/maintenance-enabled
```

The marker persists across browser restarts and workstation reboots. A reboot
during maintenance therefore returns to the maintenance page until the
administrator deliberately runs `off`.

The launcher writes only its current `DISPLAY` and `XAUTHORITY` values to:

```text
/run/user/KIOSK_UID/extrusion-kiosk-session.env
```

It writes the file atomically with mode `0600`. The controller parses only
those two expected keys; it never sources, evaluates, or executes the file.
The controller uses the values to launch YAD as the non-sudo `kiosk` user from
an administrator's SSH session.

Chromium retains its normal profile and local storage. It uses a separate,
fixed cache directory:

```text
/run/user/KIOSK_UID/extrusion-chromium-http-cache
```

The launcher clears and recreates only that cache directory immediately before
every Chromium start. This gives `off` a clean application/asset load without
deleting the kiosk profile.

## Browser Switching

`on` validates that the installed page and image are readable, creates the
marker, and terminates only supported kiosk-browser processes owned by `kiosk`:
`chromium`, `chromium-browser`, and `google-chrome`. The existing launcher loop
reopens the selected browser on the local page.

`off` removes the marker before terminating the kiosk user's Chromium process.
The launcher then reopens the configured terminal URL.

Both commands are idempotent. Chromium already being stopped is not an error.
Neither command stops LightDM, Xfce, the launcher loop, the FastAPI service, or
any process owned by another user.

## Informational Dialog

The installer installs YAD from Debian. `notify` accepts one positive ASCII
integer. It uses `минута` for `1` and `минути` for every other accepted value.

For `notify 30`, the dialog text is:

```text
След приблизително 30 минути терминалът ще бъде временно недостъпен
поради техническа поддръжка. Моля, планирайте текущата работа.
```

The dialog uses `gears.png`, is centered and kept above Chromium, disables the
Escape-key close path, and exposes exactly one `OK` button. Clicking `OK`
returns success. Closing or failing to show the dialog returns nonzero and
does not change the marker or Chromium.

## Maintenance Page

At the kiosk viewport, the local page has:

- a full-viewport light-gray background;
- a centered vertical content group;
- the transparent gears image above the text;
- heading `Извършва се техническа поддръжка`;
- text `Терминалът временно не е достъпен. Моля, изчакайте.`;
- no buttons, links, forms, scripts, countdown, progress, scheduled time,
  reload action, or completion estimate;
- no remote fonts, stylesheets, images, requests, or other network dependency.

The page remains usable while the app VM or LAN is unavailable.

## Scope and Security Boundary

The maintenance display covers the physical kiosk only. It is not access
control. The application remains reachable from another LAN device whenever
the FastAPI server is running. A person who can escape kiosk mode can also
reach the configured terminal URL. This is accepted for the bounded pilot.

This slice must not modify:

- any file under `app/`;
- SQLite schema, migrations, values, or production records;
- `scripts/deploy_production.sh`;
- the application's `/admin` or `/terminal` behavior;
- production timing or operational-card state;
- keyboard-shortcut restrictions, which remain a separate workstation task.

## Failure Behavior

- Invalid `notify` input exits nonzero without opening a dialog.
- Missing YAD, image, session environment, `DISPLAY`, or `XAUTHORITY` produces a
  useful SSH error and changes no mode state.
- Unknown, duplicate, blank, relative, or unreadable session values are
  rejected rather than guessed or executed.
- `on` refuses to create the marker when the page or image is missing.
- If Chromium termination fails after `on`, the marker remains present so the
  next browser start still selects maintenance.
- `off` removes the marker even if Chromium is already stopped.
- If the app is unavailable after `off`, Chromium may display its normal
  connection error. The administrator can run `on` again and diagnose the app
  separately; there is no automatic rollback.
- A failed installation stops with a clear error. It does not reboot.

## Development and Review Policy

Implementation happens in the current checkout as the user requested. It does
not create a branch or worktree. The current dirty worktree and all unrelated
changes must be preserved. No file is staged or committed unless the user
later gives explicit permission.

Subagent-driven execution is sequential. GPT-5.6 Terra may implement bounded
tasks, but every task review, fix re-review, and final whole-change review must
use GPT-5.6 Sol with `xhigh` reasoning effort. No reviewer may inherit the
implementer's role or substitute a lower model.

Local implementation does not authorize copying files to the workstation,
installing packages there, rebooting it, running maintenance commands on it,
or changing any other external system. Those actions require separate user
approval after local tests and reviews pass.

## Verification

Automated tests use temporary paths and fake `runuser`, `pkill`, Chromium, and
desktop commands. They cover:

- bundle completeness and installer preflight ordering;
- shell syntax;
- notification argument and Bulgarian grammar handling;
- safe graphical-session parsing;
- dialog command construction and blocking result propagation;
- marker creation/removal, idempotence, status, and failure ordering;
- launcher URL selection;
- private atomic session-environment output;
- deletion of only the fixed HTTP-cache directory while preserving the
  Chromium profile and neighboring runtime files;
- the exact local page copy, no controls, and no network resources;
- installer paths, modes, YAD installation, marker preservation, and explicit
  reboot instruction.

Repository-local Playwright renders `workstation-maintenance/maintenance.html`
at the actual kiosk viewport and saves:

```text
artifacts/ui-checks/workstation-maintenance/maintenance-screen.png
```

After local checks and Sol xhigh reviews pass, a separately user-approved live
check verifies installation, reboot behavior, `notify 30`, acknowledgment,
`on`, Chromium relaunch, LAN reachability, `off`, fresh app loading,
local-storage preservation, and absence of application/database changes.
