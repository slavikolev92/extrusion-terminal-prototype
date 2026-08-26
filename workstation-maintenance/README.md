# Workstation maintenance bundle

This is the authoritative runbook for showing the physical extrusion kiosk a
local maintenance page. Copy the complete `workstation-maintenance` folder; do
not copy an individual script. Installation and maintenance commands never
modify app or SQLite data.

## Install or update the bundle

Run these commands from a local administrator machine, with the repository
checkout as the current directory:

```bash
scp -r workstation-maintenance extrusion-terminal@100.94.38.101:~/
ssh -t extrusion-terminal@100.94.38.101 \
  'cd ~/workstation-maintenance && sudo bash install.sh'
ssh -t extrusion-terminal@100.94.38.101 'sudo reboot'
```

The installer requires the separately provisioned `kiosk` user, terminal URL,
launcher, and X session. It installs YAD and these runtime files:

- `/usr/local/bin/extrusion-kiosk-maintenance`
- `/usr/local/bin/extrusion-kiosk-session`
- `/usr/local/share/extrusion-kiosk/maintenance.html`
- `/usr/local/share/extrusion-kiosk/gears.png`
- `/var/lib/extrusion-kiosk/` (the installer preserves any existing
  `maintenance-enabled` marker)

Base kiosk provisioning is independent and can overwrite the launcher. Rerun
`sudo bash install.sh` from this copied folder, then reboot, after every future
base kiosk provisioning.

## Run a maintenance window

After reconnecting to the workstation, run the following in order when doing a
planned maintenance window:

```bash
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance notify 30
sudo extrusion-kiosk-maintenance on
sudo extrusion-kiosk-maintenance status
sudo extrusion-kiosk-maintenance off
sudo extrusion-kiosk-maintenance status
```

`notify 30` displays a warning and waits for the operator to select `OK`; it
starts no timer. `on` and `off` are separate manual decisions and are
idempotent. `on` changes the physical kiosk only; it does not block LAN clients.
`status` reports marker selection, not app health. `off` restarts Chromium with
an empty HTTP cache while preserving the browser profile and local storage. A
reboot during maintenance returns to maintenance until `off` is run.

If `off` exposes an app connection error, run `on` and fix the app separately.

## Troubleshooting

- **Missing bundle files:** copy the complete `workstation-maintenance` folder
  again and run the installer from inside it.
- **YAD or package failure:** correct the workstation package/network problem,
  then rerun `sudo bash install.sh` and reboot.
- **Absent kiosk session, user, or URL:** run the base kiosk provisioner first,
  then rerun this installer and reboot.
- **Invalid runtime environment:** confirm the kiosk X session is running and
  its runtime directory is available before using `notify`.
- **Dialog failure:** leave the terminal mode unchanged, resolve the kiosk
  session/display issue, and run `notify` again if the warning is still needed.
- **Already-stopped Chromium:** `on` and `off` still complete; the kiosk
  launcher will select the marker state when Chromium starts again.
- **App unavailable after `off`:** run `on` to return the physical kiosk to
  maintenance and repair the app independently.
