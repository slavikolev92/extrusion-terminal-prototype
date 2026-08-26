# Workstation Maintenance Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one root-level folder that can be copied to the Debian kiosk workstation and installed there to provide manual `notify`, `on`, `off`, and `status` maintenance-display controls without changing the FastAPI application.

**Architecture:** `workstation-maintenance/` is a flat, self-contained source and installation bundle. Its installer copies a maintenance-aware Chromium launcher, an SSH-operated controller, a local HTML page, and the selected gears image into fixed workstation system paths; runtime mode is selected by one marker file and remains entirely outside the application and database.

**Tech Stack:** Bash, Debian/Xfce/LightDM, Chromium, YAD/GTK, local HTML/CSS/PNG, pytest subprocess tests, repository-local Node Playwright.

## Global Constraints

- Work directly in the current checkout on `main`, as explicitly requested; do not create a branch or worktree.
- Preserve the dirty worktree and every unrelated user change. Agents work sequentially and may edit only files named in their assigned task.
- Do not stage or commit unless the user later gives explicit permission.
- Create every new source, page, test, verifier, image, and instruction file under the single root-level `workstation-maintenance/` folder.
- Do not modify any file under `app/`, any SQLite database/schema/migration, `scripts/deploy_production.sh`, or `scripts/provision_workstation_kiosk.sh`.
- Do not add timers, schedulers, daemons, deployment hooks, app-level maintenance state, automatic transitions, or LAN access blocking.
- Local implementation does not authorize copying to, installing on, rebooting, or otherwise changing the live workstation.
- Use `gpt-5.6-terra` with `high` reasoning for implementation agents, except the documentation-only task may use `gpt-5.6-terra` with `medium` reasoning.
- Use `gpt-5.6-sol` with `xhigh` reasoning for every task review, every fix re-review, and the final whole-change review. Never substitute Terra or a lower reasoning effort for a review.
- Review from the live working-tree files and task report because this execution intentionally has no branch or task commits. Store review briefs/packages only in the plan's ignored `.superpowers/sdd/` workspace.

---

## File Map

**Create — all new files stay together:**

- `workstation-maintenance/README.md` — exact copy, install, reboot, operating, recovery, and verification commands.
- `workstation-maintenance/install.sh` — idempotent root installer for an already-provisioned kiosk workstation.
- `workstation-maintenance/extrusion-kiosk-maintenance` — `notify`, `on`, `off`, and `status` controller.
- `workstation-maintenance/extrusion-kiosk-session` — maintenance-aware Chromium launcher installed over the existing launcher.
- `workstation-maintenance/maintenance.html` — network-independent Bulgarian maintenance page.
- `workstation-maintenance/gears.png` — byte-for-byte copy of `ui-prototypes/gears.png`.
- `workstation-maintenance/test_workstation_maintenance.py` — controller, launcher, installer, asset, and page tests.
- `workstation-maintenance/verify-ui.mjs` — fixed-path local Playwright verification and screenshot capture.

**Modify:**

- `pyproject.toml:1-3` — include `workstation-maintenance` in pytest discovery without removing `tests`.
- `docs/DEPLOYMENT.md:14-23` — link the optional manual workstation cover procedure while keeping deployment separate.
- `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md:745-891` — record the bundle, installed paths, reinstall rule, and live acceptance steps.

**Reference only:**

- `docs/superpowers/specs/2026-08-07-workstation-maintenance-display-design.md`
- `scripts/provision_workstation_kiosk.sh:146-196` — source of the currently proven launcher flags and Xfce behavior; do not edit it.
- `ui-prototypes/thumb_u.min.webp` — layout reference only.
- `ui-prototypes/gears.png` — accepted source artwork.

---

### Task 1: Controller and Test Harness

**Implementation model:** `gpt-5.6-terra`, reasoning effort `high`.

**Review model:** `gpt-5.6-sol`, reasoning effort `xhigh`.

**Files:**

- Create: `workstation-maintenance/extrusion-kiosk-maintenance`
- Create: `workstation-maintenance/test_workstation_maintenance.py`
- Modify: `pyproject.toml:1-3`

**Interfaces:**

- Consumes: installed page `/usr/local/share/extrusion-kiosk/maintenance.html`, image `/usr/local/share/extrusion-kiosk/gears.png`, and runtime session file `/run/user/KIOSK_UID/extrusion-kiosk-session.env`.
- Produces: command interface `extrusion-kiosk-maintenance notify MINUTES|on|off|status`; marker `/var/lib/extrusion-kiosk/maintenance-enabled`; output `mode=maintenance` or `mode=terminal`.

- [ ] **Step 1: Add bundle tests to normal pytest discovery**

Change the existing setting without removing the application tests:

```toml
[tool.pytest.ini_options]
addopts = "-p no:cacheprovider"
testpaths = ["tests", "workstation-maintenance"]
```

- [ ] **Step 2: Create the reusable subprocess test harness**

Create `workstation-maintenance/test_workstation_maintenance.py` with these exact constants and helpers:

```python
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest


BUNDLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BUNDLE_DIR.parent
CONTROLLER = BUNDLE_DIR / "extrusion-kiosk-maintenance"
LAUNCHER = BUNDLE_DIR / "extrusion-kiosk-session"
INSTALLER = BUNDLE_DIR / "install.sh"
PAGE = BUNDLE_DIR / "maintenance.html"
GEARS = BUNDLE_DIR / "gears.png"
VERIFIER = BUNDLE_DIR / "verify-ui.mjs"


def write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run_script(script: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
```

Add a `controller_environment(tmp_path)` fixture/helper that creates:

```text
<tmp>/share/maintenance.html
<tmp>/share/gears.png
<tmp>/state/
<tmp>/runtime/Xauthority
<tmp>/runtime/extrusion-kiosk-session.env
<tmp>/bin/runuser
<tmp>/bin/pkill
<tmp>/runuser.log
<tmp>/pkill.log
```

The session file content must be exactly:

```python
session_env.write_text(
    f"DISPLAY=:7\nXAUTHORITY={xauthority}\n",
    encoding="utf-8",
)
```

The fake commands log one argument per line:

```sh
#!/bin/sh
printf '%s\n' "$@" > "$EXTRUSION_TEST_RUNUSER_LOG"
```

```sh
#!/bin/sh
printf '%s\n' "$@" >> "$EXTRUSION_TEST_PKILL_LOG"
```

Set these environment overrides to the temporary paths:

```text
EXTRUSION_KIOSK_USER=kiosk
EXTRUSION_KIOSK_SHARE_DIR=<tmp>/share
EXTRUSION_KIOSK_STATE_DIR=<tmp>/state
EXTRUSION_KIOSK_SESSION_ENV_FILE=<tmp>/runtime/extrusion-kiosk-session.env
EXTRUSION_TEST_RUNUSER_LOG=<tmp>/runuser.log
EXTRUSION_TEST_PKILL_LOG=<tmp>/pkill.log
```

- [ ] **Step 3: Write the failing controller behavior tests**

Implement these tests with literal assertions rather than source-string-only checks:

```python
@pytest.mark.parametrize("minutes", ["", "0", "-1", "1.5", "abc", " 30"])
def test_notify_rejects_non_positive_or_non_integer_minutes(tmp_path, minutes):
    env, paths = controller_environment(tmp_path)
    args = ("notify",) if minutes == "" else ("notify", minutes)
    result = run_script(CONTROLLER, *args, env=env)
    assert result.returncode != 0
    assert not paths["runuser_log"].exists()
    assert not (paths["state"] / "maintenance-enabled").exists()
```

Add complete tests named:

```text
test_notify_uses_recorded_session_gears_one_ok_button_and_plural_copy
test_notify_uses_singular_bulgarian_minute_for_one
test_notify_propagates_dialog_failure_without_changing_mode
test_notify_rejects_missing_unknown_duplicate_blank_or_relative_session_values
test_on_validates_assets_before_creating_marker
test_on_creates_marker_and_targets_only_kiosk_chromium
test_on_is_idempotent
test_off_removes_marker_before_browser_restart_and_is_idempotent
test_status_reports_terminal_or_maintenance
test_unknown_command_prints_usage_and_fails
```

For `notify 30`, assert the fake `runuser` log contains these exact arguments:

```text
-u
kiosk
--
env
DISPLAY=:7
XAUTHORITY=<temporary absolute path>
yad
--title=Предстояща техническа поддръжка
--image=<temporary absolute path>/share/gears.png
--image-on-top
--text=След приблизително 30 минути терминалът ще бъде временно недостъпен поради техническа поддръжка. Моля, планирайте текущата работа.
--text-align=center
--button=OK:0
--buttons-layout=center
--center
--on-top
--no-escape
--fixed
--width=640
```

For `on` and `off`, assert the fake `pkill` log contains exactly:

```text
-TERM
-u
kiosk
-x
chromium
```

- [ ] **Step 4: Run the controller tests and verify the expected failure**

Run:

```bash
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'notify or test_on or test_off or status or unknown_command' -q
```

Expected: FAIL because `workstation-maintenance/extrusion-kiosk-maintenance` does not exist.

- [ ] **Step 5: Implement the controller**

Create a strict Bash script beginning with:

```bash
#!/usr/bin/env bash
set -Eeuo pipefail

KIOSK_USER="${EXTRUSION_KIOSK_USER:-kiosk}"
SHARE_DIR="${EXTRUSION_KIOSK_SHARE_DIR:-/usr/local/share/extrusion-kiosk}"
STATE_DIR="${EXTRUSION_KIOSK_STATE_DIR:-/var/lib/extrusion-kiosk}"
MARKER_FILE="${STATE_DIR}/maintenance-enabled"
PAGE_FILE="${SHARE_DIR}/maintenance.html"
IMAGE_FILE="${SHARE_DIR}/gears.png"

if [ -n "${EXTRUSION_KIOSK_SESSION_ENV_FILE:-}" ]; then
    SESSION_ENV_FILE="$EXTRUSION_KIOSK_SESSION_ENV_FILE"
else
    KIOSK_UID="$(id -u "$KIOSK_USER")"
    SESSION_ENV_FILE="/run/user/${KIOSK_UID}/extrusion-kiosk-session.env"
fi
```

Implement these functions:

```text
usage
die
validate_absolute_paths
read_session_env
stop_kiosk_browser
notify_operator
enable_maintenance
disable_maintenance
print_status
```

Required implementation rules:

- `validate_absolute_paths` accepts only absolute share/state/session paths and rejects `/` as `STATE_DIR`.
- `read_session_env` reads lines with `IFS='=' read -r key value`; it accepts exactly one `DISPLAY` and one `XAUTHORITY`, rejects unknown/duplicate/blank values, requires an absolute readable Xauthority path, and never calls `source`, `.`, `eval`, or a shell on file content.
- `notify_operator` accepts only a positive ASCII integer matching `^[1-9][0-9]*$`; it chooses `минута` only for `1`, otherwise `минути`.
- The YAD invocation matches the exact argument list asserted in Step 3 and remains blocking.
- `enable_maintenance` validates readable page and image before `install -d -m 0755 "$STATE_DIR"` and `install -m 0644 /dev/null "$MARKER_FILE"`.
- `disable_maintenance` runs `rm -f -- "$MARKER_FILE"` before browser termination.
- `stop_kiosk_browser` runs `pkill -TERM -u "$KIOSK_USER" -x` for each launcher-supported process name: `chromium`, `chromium-browser`, and `google-chrome`. Exit code `1` means that name has no process and is accepted, while higher codes propagate without attempting later names.
- `print_status` prints exactly `mode=maintenance` when the marker exists and `mode=terminal` otherwise.
- Dispatch accepts only `notify MINUTES`, `on`, `off`, and `status` with exact argument counts.

- [ ] **Step 6: Run the focused tests to green**

```bash
bash -n workstation-maintenance/extrusion-kiosk-maintenance
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'notify or test_on or test_off or status or unknown_command' -q
```

Expected: PASS with every created state file below pytest's temporary directory.

- [ ] **Step 7: Run the mandatory task review**

Create the task report and working-tree review package in this plan's ignored
SDD workspace. Dispatch a fresh reviewer with:

```text
model: gpt-5.6-sol
reasoning_effort: xhigh
```

The reviewer must verdict both specification compliance and code/test quality
for Task 1. Any fix is returned to the Terra implementer, retested, then
re-reviewed by a fresh Sol xhigh reviewer. Do not continue while Critical or
Important findings remain open.

---

### Task 2: Maintenance-Aware Kiosk Launcher

**Implementation model:** `gpt-5.6-terra`, reasoning effort `high`.

**Review model:** `gpt-5.6-sol`, reasoning effort `xhigh`.

**Files:**

- Create: `workstation-maintenance/extrusion-kiosk-session`
- Modify: `workstation-maintenance/test_workstation_maintenance.py`

**Interfaces:**

- Consumes: `/etc/extrusion-kiosk-url`, `/var/lib/extrusion-kiosk/maintenance-enabled`, installed `maintenance.html`, `DISPLAY`, and `XAUTHORITY`.
- Produces: runtime session file `extrusion-kiosk-session.env`, fixed cache directory `extrusion-chromium-http-cache`, and one Chromium launch URL per loop iteration.

- [ ] **Step 1: Add deterministic launcher command fakes**

Add `launcher_environment(tmp_path, maintenance_enabled=False)` to create fake
`chromium`, `xfwm4`, `unclutter`, and `xset` executables in a temporary `bin`.
The fake Chromium writes each argument to `EXTRUSION_TEST_CHROMIUM_LOG` and
exits `0`; the desktop fakes exit `0` without touching the real display.

Set:

```text
EXTRUSION_KIOSK_RUN_ONCE=1
EXTRUSION_KIOSK_URL_FILE=<tmp>/extrusion-kiosk-url
EXTRUSION_KIOSK_MAINTENANCE_MARKER=<tmp>/maintenance-enabled
EXTRUSION_KIOSK_MAINTENANCE_PAGE=<tmp>/maintenance.html
EXTRUSION_KIOSK_PROFILE_DIR=<tmp>/profile
EXTRUSION_KIOSK_RUNTIME_DIR=<tmp>/runtime
EXTRUSION_TEST_CHROMIUM_LOG=<tmp>/chromium.log
DISPLAY=:7
XAUTHORITY=<tmp>/Xauthority
```

- [ ] **Step 2: Write the failing launcher tests**

Add complete tests named:

```text
test_launcher_selects_configured_terminal_url_without_marker
test_launcher_selects_local_file_url_with_marker
test_launcher_clears_only_dedicated_http_cache
test_launcher_preserves_profile_and_neighboring_runtime_files
test_launcher_writes_only_display_and_xauthority_atomically_with_mode_0600
test_launcher_rejects_root_relative_or_parent_traversal_runtime_directory
test_launcher_preserves_existing_xfwm_gpu_keyring_and_kiosk_flags
```

The normal URL assertion is:

```python
assert "http://192.168.1.83:8000/terminal" in chromium_arguments
assert not any(argument.startswith("file://") for argument in chromium_arguments)
```

The maintenance URL assertion is:

```python
assert f"file://{paths['maintenance_page']}" in chromium_arguments
assert "http://192.168.1.83:8000/terminal" not in chromium_arguments
```

Before the cache test, create:

```text
<runtime>/extrusion-chromium-http-cache/stale-entry
<runtime>/must-survive
<profile>/must-survive
```

After one launch, assert only `stale-entry` disappeared and that Chromium
received `--disk-cache-dir=<runtime>/extrusion-chromium-http-cache`.

- [ ] **Step 3: Run launcher tests and verify the expected failure**

```bash
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k launcher -q
```

Expected: FAIL because `workstation-maintenance/extrusion-kiosk-session` does not exist.

- [ ] **Step 4: Implement the launcher from the proven current session**

Copy the established Xfce/Chromium behavior from
`scripts/provision_workstation_kiosk.sh:147-195` into a standalone POSIX shell
script. Preserve `xfwm4 --replace`, `unclutter`, DPMS disabling, the infinite
relaunch loop, and these flags:

```text
--kiosk
--disable-gpu
--disable-gpu-compositing
--no-first-run
--disable-infobars
--disable-session-crashed-bubble
--disable-features=Translate
--password-store=basic
--user-data-dir=<profile>
```

Define exact defaults:

```sh
URL_FILE="${EXTRUSION_KIOSK_URL_FILE:-/etc/extrusion-kiosk-url}"
DEFAULT_URL="http://127.0.0.1:8000/terminal"
MAINTENANCE_MARKER="${EXTRUSION_KIOSK_MAINTENANCE_MARKER:-/var/lib/extrusion-kiosk/maintenance-enabled}"
MAINTENANCE_PAGE="${EXTRUSION_KIOSK_MAINTENANCE_PAGE:-/usr/local/share/extrusion-kiosk/maintenance.html}"
PROFILE_DIR="${EXTRUSION_KIOSK_PROFILE_DIR:-$HOME/.config/extrusion-chromium}"
RUNTIME_DIR="${EXTRUSION_KIOSK_RUNTIME_DIR:-/run/user/$(id -u)}"
SESSION_ENV_FILE="${RUNTIME_DIR}/extrusion-kiosk-session.env"
CACHE_DIR="${RUNTIME_DIR}/extrusion-chromium-http-cache"
```

Reject `RUNTIME_DIR` unless it is absolute, not `/`, and contains no `.` or
`..` path component. Create the validated runtime directory, use `umask 077`,
write only these two lines to a sibling temporary file, `chmod 0600`, then
rename atomically over `SESSION_ENV_FILE`:

```text
DISPLAY=<value from ${DISPLAY:-}>
XAUTHORITY=<value from ${XAUTHORITY:-}>
```

Immediately before every browser launch, guard and reset only the cache child:

```sh
case "$CACHE_DIR" in
    "$RUNTIME_DIR/extrusion-chromium-http-cache") ;;
    *) exit 1 ;;
esac
rm -rf -- "$CACHE_DIR"
mkdir -m 0700 -- "$CACHE_DIR"
```

Select the marker-controlled URL and add:

```text
--disk-cache-dir=<fixed cache directory>
```

`EXTRUSION_KIOSK_RUN_ONCE=1` exits after the first Chromium process returns;
the normal unset value retains the infinite loop.

- [ ] **Step 5: Run launcher tests to green**

```bash
sh -n workstation-maintenance/extrusion-kiosk-session
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k launcher -q
```

Expected: PASS; the profile and neighboring runtime sentinel remain present.

- [ ] **Step 6: Run the mandatory task review**

Dispatch a fresh `gpt-5.6-sol` reviewer with `xhigh` reasoning. Require explicit
verdicts for URL selection, deletion safety, session-file safety, preservation
of the existing GPU/window-manager workaround, and test quality. Every fix
round is re-reviewed by Sol xhigh before Task 2 is complete.

---

### Task 3: Local Maintenance Page, Accepted Image, and Visual Check

**Implementation model:** `gpt-5.6-terra`, reasoning effort `high`.

**Review model:** `gpt-5.6-sol`, reasoning effort `xhigh`.

**Files:**

- Create: `workstation-maintenance/maintenance.html`
- Create: `workstation-maintenance/gears.png`
- Create: `workstation-maintenance/verify-ui.mjs`
- Modify: `workstation-maintenance/test_workstation_maintenance.py`

**Interfaces:**

- Consumes: accepted source artwork `ui-prototypes/gears.png` and layout reference `ui-prototypes/thumb_u.min.webp`.
- Produces: a `file://`-renderable maintenance page and screenshot `artifacts/ui-checks/workstation-maintenance/maintenance-screen.png`.

- [ ] **Step 1: Write failing page and asset tests**

Add complete tests named:

```text
test_maintenance_page_contains_exact_approved_bulgarian_copy
test_maintenance_page_has_no_controls_scripts_or_network_resources
test_maintenance_page_references_only_local_gears_png
test_bundle_gears_matches_selected_source_byte_for_byte
test_visual_verifier_has_valid_node_syntax
```

The exact text assertions are:

```python
source = PAGE.read_text(encoding="utf-8")
assert "Извършва се техническа поддръжка" in source
assert "Терминалът временно не е достъпен. Моля, изчакайте." in source
```

Lowercase the HTML and assert it contains none of:

```python
for forbidden in (
    "<button", "<a ", "<form", "<input", "<select", "<textarea",
    "<script", "http:", "https:", "@import",
):
    assert forbidden not in source.lower()
```

Assert the image copy:

```python
assert GEARS.read_bytes() == (REPO_ROOT / "ui-prototypes/gears.png").read_bytes()
```

- [ ] **Step 2: Run page tests and verify the expected failure**

```bash
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'maintenance_page or bundle_gears or visual_verifier' -q
```

Expected: FAIL because the three production files do not exist.

- [ ] **Step 3: Copy the accepted artwork unchanged**

```bash
cp ui-prototypes/gears.png workstation-maintenance/gears.png
```

Do not resize, optimize, recolor, regenerate, or replace it.

- [ ] **Step 4: Implement the static page**

Create one HTML5 document using `lang="bg"`, UTF-8, viewport metadata, system
fonts, and embedded CSS. Its body contains only:

```html
<main class="maintenance" aria-labelledby="maintenance-title">
  <img src="gears.png" alt="" width="512" height="512">
  <h1 id="maintenance-title">Извършва се техническа поддръжка</h1>
  <p>Терминалът временно не е достъпен. Моля, изчакайте.</p>
</main>
```

Make `html` and `body` fill the viewport; use a light-gray background; center
the group horizontally and vertically; constrain the image responsively; use
large dark heading and secondary text; add no interaction, animation, script,
remote resource, countdown, progress, time, reload, or completion estimate.

- [ ] **Step 5: Implement the fixed-path Playwright verifier**

Use `createRequire`, `fileURLToPath`, and `pathToFileURL`. Resolve the bundle
directory from `import.meta.url`, the repository as its parent, and these fixed
paths:

```js
const pagePath = path.join(bundleDir, "maintenance.html");
const artifactDir = path.join(
  repoRoot,
  "artifacts",
  "ui-checks",
  "workstation-maintenance",
);
const screenshotPath = path.join(artifactDir, "maintenance-screen.png");
```

Load repository-local `@playwright/test`, launch Chromium with a `1366x768`
viewport unless a more precise recorded kiosk resolution is found, abort every
`http:` and `https:` request, and load the local `file://` page. Assert both
text strings are visible, the image is complete with nonzero natural size, no
interactive element exists, and every loaded resource URL uses `file:`. Save a
full-page screenshot and close the browser in `finally`.

- [ ] **Step 6: Run page tests and visual verification to green**

```bash
node --check workstation-maintenance/verify-ui.mjs
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'maintenance_page or bundle_gears or visual_verifier' -q
./node_modules/.bin/playwright --version
node workstation-maintenance/verify-ui.mjs
```

Expected: PASS and a current screenshot at
`artifacts/ui-checks/workstation-maintenance/maintenance-screen.png`. Open the
image and inspect centering, legibility, transparency, and clipping.

- [ ] **Step 7: Run the mandatory task review**

Dispatch a fresh `gpt-5.6-sol` reviewer with `xhigh` reasoning. Give it the
page, verifier, tests, accepted image comparison, and screenshot path. Require
specification and quality verdicts. Use Sol xhigh for every re-review.

---

### Task 4: Copyable Installer and Operating Instructions

**Implementation model:** `gpt-5.6-terra`, reasoning effort `medium` for the README/documentation work and `high` for installer code/tests.

**Review model:** `gpt-5.6-sol`, reasoning effort `xhigh`.

**Files:**

- Create: `workstation-maintenance/install.sh`
- Create: `workstation-maintenance/README.md`
- Modify: `workstation-maintenance/test_workstation_maintenance.py`
- Modify: `docs/DEPLOYMENT.md:14-23`
- Modify: `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md:745-891`

**Interfaces:**

- Consumes: the four runtime siblings `extrusion-kiosk-maintenance`, `extrusion-kiosk-session`, `maintenance.html`, and `gears.png`.
- Produces: installed command/launcher/assets, an unchanged marker directory, and exact administrator commands for copying, installing, rebooting, warning, enabling, checking, and disabling maintenance.

- [ ] **Step 1: Add safe installer test hooks and failing tests**

The installer must use fixed production defaults but accept these path/command
overrides for subprocess tests:

```text
EXTRUSION_INSTALL_ROOT=<tmp>/root
EXTRUSION_INSTALL_APT_GET=<tmp>/bin/apt-get
EXTRUSION_INSTALL_ID=<tmp>/bin/id
```

`EXTRUSION_INSTALL_ROOT` prefixes only absolute installed/config paths during
tests. Production leaves it unset. Fake `apt-get` and `id` log calls and return
success; no test invokes sudo, the real package manager, or system paths.

Add complete tests named:

```text
test_installer_requires_root_before_any_mutation
test_installer_preflights_runtime_bundle_before_apt
test_installer_requires_existing_kiosk_user_url_and_session
test_installer_installs_yad_and_exact_files_with_expected_modes
test_installer_preserves_existing_maintenance_marker
test_installer_is_idempotent
test_installer_prints_reboot_and_post_reboot_status_commands_without_rebooting
test_complete_copyable_bundle_contains_every_documented_file
test_readme_contains_exact_scp_ssh_install_and_runtime_commands
```

For the successful install fixture, create under the temporary root:

```text
/etc/extrusion-kiosk-url
/usr/local/bin/extrusion-kiosk-session
/usr/share/xsessions/extrusion-kiosk.desktop
/var/lib/extrusion-kiosk/maintenance-enabled
```

After installation, assert the marker bytes are unchanged and assert modes
with `stat.S_IMODE(path.stat().st_mode)`:

```text
0755 /usr/local/bin/extrusion-kiosk-maintenance
0755 /usr/local/bin/extrusion-kiosk-session
0644 /usr/local/share/extrusion-kiosk/maintenance.html
0644 /usr/local/share/extrusion-kiosk/gears.png
0755 /var/lib/extrusion-kiosk
```

- [ ] **Step 2: Run installer tests and verify the expected failure**

```bash
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'installer or complete_copyable_bundle or readme' -q
```

Expected: FAIL because `install.sh` and `README.md` do not exist.

- [ ] **Step 3: Implement the idempotent installer**

Create `install.sh` with `#!/usr/bin/env bash` and `set -Eeuo pipefail`.
Resolve `BUNDLE_DIR` from `${BASH_SOURCE[0]}`. Before the first `apt-get` or
`install` command:

1. require effective UID `0` in production;
2. validate the optional test root as an absolute path other than `/`;
3. verify all four runtime siblings are readable and both scripts are executable;
4. verify `kiosk` exists using the selected `id` command;
5. verify the prefixed `/etc/extrusion-kiosk-url` is readable;
6. verify the prefixed existing launcher is executable;
7. verify the prefixed X session desktop file is readable.

Make the root/test boundary exact:

```bash
ROOT_PREFIX="${EXTRUSION_INSTALL_ROOT:-}"
if [ -z "$ROOT_PREFIX" ]; then
    [ "${EUID:-$(id -u)}" -eq 0 ] || die "Run this installer with sudo or as root"
else
    case "$ROOT_PREFIX" in
        /*) ;;
        *) die "EXTRUSION_INSTALL_ROOT must be an absolute test path" ;;
    esac
    [ "$ROOT_PREFIX" != "/" ] || die "EXTRUSION_INSTALL_ROOT must not be /"
fi
```

The override is the only supported non-root test mode. An unset override always
requires root, and production documentation never sets the override.

Use the selected package command exactly as:

```bash
"$APT_GET" update
"$APT_GET" install -y yad
```

Install with:

```bash
install -d -m 0755 "$ROOT_PREFIX/usr/local/share/extrusion-kiosk"
install -d -m 0755 "$ROOT_PREFIX/var/lib/extrusion-kiosk"
install -m 0755 "$BUNDLE_DIR/extrusion-kiosk-maintenance" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-maintenance"
install -m 0755 "$BUNDLE_DIR/extrusion-kiosk-session" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session"
install -m 0644 "$BUNDLE_DIR/maintenance.html" \
    "$ROOT_PREFIX/usr/local/share/extrusion-kiosk/maintenance.html"
install -m 0644 "$BUNDLE_DIR/gears.png" \
    "$ROOT_PREFIX/usr/local/share/extrusion-kiosk/gears.png"
```

Do not contain `reboot`, `shutdown`, `systemctl restart`, marker creation, or
marker removal as executable commands. Print, but do not run:

```text
sudo reboot
sudo extrusion-kiosk-maintenance status
```

Also print that base kiosk provisioning must be followed by rerunning this
installer because the independent base provisioner may replace the launcher.

- [ ] **Step 4: Write the bundle README as the authoritative runbook**

Include these exact local-to-workstation commands:

```bash
scp -r workstation-maintenance extrusion-terminal@100.94.38.101:~/
ssh -t extrusion-terminal@100.94.38.101 \
  'cd ~/workstation-maintenance && sudo bash install.sh'
ssh -t extrusion-terminal@100.94.38.101 'sudo reboot'
```

After reconnecting:

```bash
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance notify 30
sudo extrusion-kiosk-maintenance on
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance off
sudo extrusion-kiosk-maintenance status
```

Explain exactly:

- `notify` waits for `OK` but starts no timer;
- `on` and `off` are separate manual decisions and are idempotent;
- `on` covers the physical kiosk only and does not block LAN clients;
- `status` reports marker selection, not app health;
- `off` restarts Chromium with empty HTTP cache while preserving profile/local storage;
- reboot during maintenance returns to maintenance until `off`;
- if `off` exposes an app connection error, run `on` and fix the app separately;
- rerun `install.sh` and reboot after any future base kiosk provisioning;
- installation and maintenance commands never modify app/SQLite data.

Add troubleshooting for missing bundle files, YAD/package failure, absent kiosk
session, invalid runtime environment, dialog failure, already-stopped Chromium,
and app unavailability.

- [ ] **Step 5: Link the standalone runbook from existing operations docs**

In `docs/DEPLOYMENT.md`, add an optional workstation-cover paragraph linking
`../workstation-maintenance/README.md`. State that the production deploy script
does not activate or clear workstation maintenance.

In `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`, record:

- repository bundle `workstation-maintenance/`;
- the four installed runtime files/directories and runtime env/cache paths;
- complete-folder copy requirement;
- one required reboot after install/update;
- the base-provisioner-then-reinstall ordering;
- manual `notify/on/status/off` acceptance checks;
- design and implementation-plan links;
- keyboard shortcut restriction remains separate.

- [ ] **Step 6: Run installer and documentation tests to green**

```bash
bash -n workstation-maintenance/install.sh
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py \
  -k 'installer or complete_copyable_bundle or readme' -q
rg -n "copy only.*provision_workstation|automatically enables|blocks.*LAN" \
  workstation-maintenance/README.md docs/DEPLOYMENT.md \
  docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md
```

Expected: tests PASS. Any search result must be an explicit warning/denial, not
an obsolete instruction or false capability claim.

- [ ] **Step 7: Run the mandatory task review**

Dispatch a fresh `gpt-5.6-sol` reviewer with `xhigh` reasoning. Require it to
review installer mutation ordering, path safety, idempotence, marker
preservation, reboot non-automation, bundle copyability, and documentation
accuracy. Re-review every fix with Sol xhigh.

---

### Task 5: Whole-Bundle Verification and Final Sol Review

**Implementation/verification model:** `gpt-5.6-terra`, reasoning effort `high`.

**Final review model:** `gpt-5.6-sol`, reasoning effort `xhigh`.

**Files:**

- No additional source files expected.
- Generate ignored evidence only under `artifacts/ui-checks/workstation-maintenance/` and this plan's `.superpowers/sdd/` workspace.

**Interfaces:**

- Consumes: the complete root bundle and all four task reports/reviews.
- Produces: final test evidence, inspected screenshot, final Sol xhigh verdict, and a user handoff that does not modify the workstation.

- [ ] **Step 1: Run focused bundle verification from a fresh shell**

```bash
source .venv/bin/activate
python -m pytest workstation-maintenance/test_workstation_maintenance.py -q
bash -n workstation-maintenance/install.sh
bash -n workstation-maintenance/extrusion-kiosk-maintenance
sh -n workstation-maintenance/extrusion-kiosk-session
node --check workstation-maintenance/verify-ui.mjs
```

Expected: all PASS.

- [ ] **Step 2: Capture and inspect the required UI evidence**

```bash
./node_modules/.bin/playwright --version
node workstation-maintenance/verify-ui.mjs
```

Open `artifacts/ui-checks/workstation-maintenance/maintenance-screen.png` and
verify the gears render transparently, the Bulgarian copy is legible and
centered, nothing clips at the kiosk viewport, and no control is visible.

- [ ] **Step 3: Run repository regression and formatting checks**

```bash
source .venv/bin/activate
python -m pytest
git diff --check
rg -n "[[:blank:]]+$" workstation-maintenance \
  docs/superpowers/specs/2026-08-07-workstation-maintenance-display-design.md \
  docs/superpowers/plans/2026-08-07-workstation-maintenance-display.md
```

Expected: full tests PASS, no tracked-diff whitespace errors, and no trailing
whitespace matches in new untracked text files. If an unrelated dirty-baseline
failure occurs, record the exact command/output and determine whether it is
caused by named files in this plan; do not repair unrelated work.

- [ ] **Step 4: Perform the orchestrator's scope audit**

Verify from `git status`, `git diff`, and direct new-file inspection:

- every new implementation/support file is inside `workstation-maintenance/`;
- only `pyproject.toml`, `docs/DEPLOYMENT.md`, and
  `docs/INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` changed outside the existing
  design/plan files;
- no `app/`, database, migration, deploy script, or base provisioner changed;
- no timer, service, scheduler, automatic transition, or LAN block exists;
- no branch/worktree, stage, or commit was created;
- `notify` cannot change the marker;
- `on` validates assets before marker creation;
- `off` removes the marker before stopping Chromium;
- only supported kiosk-browser processes owned by `kiosk` are targeted;
- session data is parsed, never sourced;
- cache deletion cannot touch the profile, home, runtime root, or neighbor;
- installation does not reboot or alter the current marker;
- unrelated dirty-worktree files are untouched.

- [ ] **Step 5: Dispatch the mandatory whole-change review**

Create a review package containing the specification, plan, task reports,
review verdicts, current diff for the three modified tracked files, complete
contents of every new text file, binary hash comparison for `gears.png`, test
outputs, and screenshot path. Dispatch a fresh final reviewer with exactly:

```text
model: gpt-5.6-sol
reasoning_effort: xhigh
```

The final reviewer must assess end-to-end correctness, safety, copyability,
tests, UI evidence, operational instructions, and scope. If it reports
Critical or Important findings, dispatch one Terra-high fix agent for the full
finding set, rerun affected tests, then dispatch one fresh Sol-xhigh scoped
re-review. Do not substitute the orchestrator's own review for this gate.

- [ ] **Step 6: Report local completion without changing the workstation**

Report:

- root bundle path and contained files;
- exact focused/full test results;
- screenshot path;
- all task-review and final-review models/verdicts;
- confirmation that nothing was staged/committed and no branch/worktree exists;
- confirmation that the live workstation was not modified;
- the exact `scp`, SSH install, and reboot commands from the bundle README;
- the remaining accepted limitation that this covers only the kiosk display.

- [ ] **Step 7: Require separate approval before live installation**

Only after explicit user approval, copy `workstation-maintenance/` to
`extrusion-terminal@100.94.38.101`, verify the SSH host key rather than
bypassing it, run the installer, reboot, and perform the live acceptance
sequence. Local plan execution alone never authorizes those actions.

---

## Plan Self-Review

- **Specification coverage:** The plan covers the flat root bundle, complete-folder copying, independent installer, installed system paths, required reboot, manual workflow, dialog, page, marker persistence, safe X-session handoff, dedicated cache, accepted security boundary, failure behavior, and live approval gate.
- **Packaging consistency:** Every new source/support file is under `workstation-maintenance/`; the installer resolves siblings from its own directory and works after the folder is copied outside the repository.
- **Interface consistency:** Controller, launcher, installer, tests, README, and infrastructure docs use identical command names, marker/page/image/session/cache paths, Bulgarian strings, and mode output.
- **Review consistency:** Each task and every re-review explicitly requires `gpt-5.6-sol` with `xhigh`; implementation agents never serve as their own reviewers.
- **No-branch consistency:** Execution uses the current dirty checkout, sequential agents, ignored SDD artifacts, live working-tree review packages, and no staging/commits.
- **Scope consistency:** The app, database, deployment script, and base kiosk provisioner remain unchanged. Future base provisioning is handled by rerunning the independent bundle installer, not by coupling the two systems.
- **Placeholder scan:** The plan contains no `TODO`, `TBD`, omitted function/type definition, or unspecified model/reasoning setting. Test names, commands, file paths, modes, strings, and assertions are explicit.
