# Infrastructure Implementation Plan

This plan tracks the physical server, Proxmox, app VM, backup, remote-access, and later workstation/kiosk setup for the extrusion terminal pilot.

Use this file while executing the setup. Record actual values, commands, decisions, and deviations directly in the notes sections so future hardware and infrastructure setups can reuse the lessons.

This infrastructure work is separate from `IMPLEMENTATION_PLAN.md`, which tracks application features.

## Confirmed Hardware

Detailed hardware notes are also recorded in `HARDWARE_SETUP.md`.

Server PC:

| Item | Value |
| --- | --- |
| Model | Dell OptiPlex 7080 Micro |
| CPU | Intel Core i3-10100, up to 4.30 GHz, 6 MB cache |
| RAM | 16 GB DDR4 SO-DIMM |
| Storage | 512 GB M.2 NVMe SSD |
| Ethernet | Present; wired LAN will be used |
| Wi-Fi | Present on label, but not planned for server connectivity |
| Serial number | FJ3K8F3 |

Terminal workstation:

| Item | Value |
| --- | --- |
| RAM | 4 GB |
| Input | Keyboard and mouse |
| Touchscreen | No |
| Display | Approximately 24 inches; exact resolution not confirmed |
| Network | Wired LAN only; no Wi-Fi requirement |
| Operating system | Linux only; no Windows OS |

Current hardware conclusion:

- The Dell OptiPlex 7080 Micro is sufficient for Proxmox plus one small Linux app VM for this pilot.
- The workstation specs are sufficient for browser kiosk usage unless later testing shows display scaling or browser performance issues.
- Because the server appears to have a single NVMe SSD, off-machine backup should be planned before pilot use.

## Scope

Current infrastructure goal:

- Build the app server now while app development continues.
- Defer final workstation/kiosk setup until the terminal UI is closer to pilot-ready.
- Use the current PC as a workstation simulator during app development.

Confirmed target architecture:

- Physical server runs Proxmox VE.
- One Linux VM runs the extrusion terminal FastAPI app.
- App uses SQLite on the VM.
- Shift manager opens `/admin` from the LAN.
- Workstation opens `/terminal` in kiosk mode later.
- Remote maintenance uses Tailscale.
- App is not exposed directly to the public internet.

Out of scope unless explicitly confirmed:

- public internet exposure
- public DNS/domain setup
- Docker/Kubernetes
- multi-node Proxmox cluster
- Proxmox high availability
- separate database server
- user/login system for the app

## Setup Log

Fill this in as work proceeds.

| Item | Value / Notes |
| --- | --- |
| Physical server model | |
| CPU | |
| RAM | |
| Storage devices | |
| Network port used | |
| Proxmox version | |
| Proxmox host name | |
| Proxmox management IP | |
| App VM name / ID | |
| App VM OS | |
| App VM IP | |
| App service port | `8000` unless changed |
| App install path | `/opt/extrusion-terminal/app` unless changed |
| SQLite DB path | `/opt/extrusion-terminal/data/extrusion_terminal.sqlite3` unless changed |
| Backup path | `/opt/extrusion-terminal/backups` unless changed |
| Tailscale machine name | |
| Backup schedule | |
| Restore test date | |
| Notes / deviations | |

## Phase 0 - Preflight Decisions

Status: pending

Goal: confirm the physical setup before installing anything.

Steps:

1. Confirm server hardware is ready:
   - CPU supports virtualization.
   - RAM is sufficient.
   - storage device is installed and can be erased for Proxmox.
   - wired network is available.

2. Confirm install media:
   - Proxmox VE ISO downloaded.
   - USB installer created.
   - keyboard/monitor available for installation.

3. Confirm network plan:
   - choose static IP or DHCP reservation for Proxmox host.
   - choose static IP or DHCP reservation for app VM.
   - decide hostnames.

Recommended names:

- Proxmox host: `extrusion-pve`
- App VM: `extrusion-app`

Record:

```text
Proxmox host IP:
App VM IP:
Gateway:
DNS:
LAN subnet:
```

Acceptance:

- Hardware, install media, and IP plan are confirmed.

Notes:

```text

```

## Phase 1 - Install Proxmox VE

Status: pending

Goal: install Proxmox bare-metal on the server.

Steps:

1. Boot server from Proxmox USB installer.
2. Install Proxmox to the selected storage device.
3. Set:
   - hostname
   - management IP
   - gateway
   - DNS
   - root password
   - admin email
4. Reboot after install.
5. From another PC, open the Proxmox web UI:

```text
https://PROXMOX-IP:8006
```

6. Log in as `root`.
7. Confirm storage and network bridge exist.

Acceptance:

- Proxmox web UI is reachable on LAN.
- Server survives reboot and returns to the same management IP.

Record:

```text
Proxmox URL:
Hostname:
Version:
Storage layout:
Network bridge:
```

Notes:

```text

```

## Phase 2 - Proxmox Baseline Configuration

Status: pending

Goal: make Proxmox ready for the app VM.

Steps:

1. Confirm package repositories are configured appropriately.
2. Run system updates from the Proxmox shell or web UI.
3. Reboot if kernel or core packages updated.
4. Confirm web UI still works after reboot.
5. Upload Debian or Ubuntu Server ISO to Proxmox storage.

Recommended VM OS:

- Debian 12 or current Ubuntu Server LTS.

Acceptance:

- Proxmox is updated.
- Linux server ISO is available in Proxmox.

Record:

```text
Linux ISO used:
Update date:
Any repository changes:
```

Notes:

```text

```

## Phase 3 - Create App VM

Status: pending

Goal: create a dedicated Linux VM for the app.

Recommended starting VM size:

- CPU: 2 vCPU
- RAM: 4 GB
- Disk: 40-80 GB
- Network: virtio on the LAN bridge

Steps:

1. Create VM in Proxmox.
2. Attach Debian/Ubuntu Server ISO.
3. Install OS.
4. Create admin user.
5. Configure static IP or DHCP reservation.
6. Enable OpenSSH server.
7. Reboot VM.
8. SSH into VM from LAN.

Acceptance:

- VM boots automatically after Proxmox restart if configured.
- VM is reachable over SSH.
- VM has stable LAN IP.

Record:

```text
VM ID:
VM name:
vCPU:
RAM:
Disk:
OS version:
VM IP:
Admin user:
SSH command:
```

Notes:

```text

```

## Phase 4 - Install App VM Dependencies

Status: pending

Goal: install runtime dependencies required by the FastAPI/SQLite app.

Steps:

1. Update package lists.
2. Install required packages:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git sqlite3 curl ca-certificates
```

3. Confirm versions:

```bash
python3 --version
sqlite3 --version
git --version
```

Acceptance:

- Python 3.11+ is available.
- `python3 -m venv` works.
- `sqlite3` and `git` are installed.

Record:

```text
Python version:
SQLite version:
Git version:
```

Notes:

```text

```

## Phase 5 - Deploy App Code

Status: pending

Goal: place the app code on the VM and create a virtual environment.

Recommended paths:

```text
/opt/extrusion-terminal/app
/opt/extrusion-terminal/data
/opt/extrusion-terminal/backups
```

Steps:

1. Create directories:

```bash
sudo mkdir -p /opt/extrusion-terminal/app
sudo mkdir -p /opt/extrusion-terminal/data
sudo mkdir -p /opt/extrusion-terminal/backups
sudo chown -R "$USER":"$USER" /opt/extrusion-terminal
```

2. Copy or clone the repository into:

```text
/opt/extrusion-terminal/app
```

3. Create app virtual environment:

```bash
cd /opt/extrusion-terminal/app
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

4. Run app once manually:

```bash
EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3 \
EXTRUSION_BACKUP_DIR=/opt/extrusion-terminal/backups \
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

5. From another machine, open:

```text
http://APP-VM-IP:8000/health
http://APP-VM-IP:8000/admin
http://APP-VM-IP:8000/terminal
```

6. Stop manual server with `Ctrl+C`.

Acceptance:

- App starts manually.
- `/health` returns OK.
- `/admin` and `/terminal` load from another LAN machine.
- SQLite database file appears in the configured data directory.

Record:

```text
App code source:
App branch/commit:
Manual health URL:
Database file created:
```

Notes:

```text

```

## Phase 6 - Create Systemd App Service

Status: pending

Goal: run the app automatically as a service.

Recommended service file:

```ini
[Unit]
Description=Extrusion Terminal App
After=network.target

[Service]
WorkingDirectory=/opt/extrusion-terminal/app
Environment=EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3
Environment=EXTRUSION_BACKUP_DIR=/opt/extrusion-terminal/backups
ExecStart=/opt/extrusion-terminal/app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Steps:

1. Create service:

```bash
sudo nano /etc/systemd/system/extrusion-terminal.service
```

2. Paste and adjust the service file.
3. Reload systemd:

```bash
sudo systemctl daemon-reload
```

4. Enable and start:

```bash
sudo systemctl enable --now extrusion-terminal.service
```

5. Check status:

```bash
sudo systemctl status extrusion-terminal.service
```

6. Check logs:

```bash
journalctl -u extrusion-terminal.service -n 100 --no-pager
```

7. Reboot VM and confirm app starts automatically:

```bash
sudo reboot
```

Acceptance:

- App starts at boot.
- App restarts if the process exits.
- `/health`, `/admin`, and `/terminal` work after VM reboot.

Record:

```text
Service file final contents:
Status check date:
Reboot test result:
```

Notes:

```text

```

## Phase 7 - Configure Backups

Status: pending

Goal: schedule SQLite-safe backups.

Existing app backup command:

```bash
cd /opt/extrusion-terminal/app
EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3 \
EXTRUSION_BACKUP_DIR=/opt/extrusion-terminal/backups \
.venv/bin/python -m app.backups backup
```

Recommended: systemd timer every 10 minutes.

Create service:

```bash
sudo nano /etc/systemd/system/extrusion-terminal-backup.service
```

Suggested content:

```ini
[Unit]
Description=Create SQLite-safe backup for Extrusion Terminal

[Service]
Type=oneshot
WorkingDirectory=/opt/extrusion-terminal/app
Environment=EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3
Environment=EXTRUSION_BACKUP_DIR=/opt/extrusion-terminal/backups
ExecStart=/opt/extrusion-terminal/app/.venv/bin/python -m app.backups backup
```

Create timer:

```bash
sudo nano /etc/systemd/system/extrusion-terminal-backup.timer
```

Suggested content:

```ini
[Unit]
Description=Run Extrusion Terminal backup every 10 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
Unit=extrusion-terminal-backup.service

[Install]
WantedBy=timers.target
```

Enable timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now extrusion-terminal-backup.timer
```

Check timer:

```bash
systemctl list-timers extrusion-terminal-backup.timer
```

Run manual backup:

```bash
sudo systemctl start extrusion-terminal-backup.service
ls -lh /opt/extrusion-terminal/backups
```

Acceptance:

- Manual backup creates a timestamped SQLite backup.
- Timer is active.
- Backup files appear after scheduled interval.

Record:

```text
Backup timer enabled:
First backup file:
Backup interval:
Retention behavior:
```

Notes:

```text

```

## Phase 8 - Restore Rehearsal

Status: pending

Goal: verify recovery before pilot use.

Steps:

1. Stop app:

```bash
sudo systemctl stop extrusion-terminal.service
```

2. Choose a backup file:

```bash
ls -lh /opt/extrusion-terminal/backups
```

3. Restore to a test target first:

```bash
cd /opt/extrusion-terminal/app
.venv/bin/python -m app.backups restore \
  --backup /opt/extrusion-terminal/backups/BACKUP_FILE.sqlite3 \
  --target /opt/extrusion-terminal/data/restore-test.sqlite3
```

4. If test restore succeeds, document the result.
5. Start app again:

```bash
sudo systemctl start extrusion-terminal.service
```

6. Confirm app works:

```text
http://APP-VM-IP:8000/health
```

Acceptance:

- Restore helper can restore a backup to a target file.
- App resumes normally after stop/start.

Do not restore over the production database while the app is running.

Record:

```text
Backup restored:
Restore target:
Restore result:
```

Notes:

```text

```

## Phase 9 - Install Tailscale

Status: pending

Goal: enable secure remote maintenance without public internet exposure.

Steps:

1. Install Tailscale on the app VM.
2. Authenticate:

```bash
sudo tailscale up
```

3. Verify:

```bash
tailscale ip
tailscale status
```

4. In the Tailscale admin console:
   - confirm the VM appears.
   - consider disabling key expiry for this trusted server if appropriate.

5. Test access from a remote trusted device:

```text
http://TAILSCALE-IP:8000/health
```

Acceptance:

- App VM is reachable over Tailscale.
- No router port forwarding is used.

Record:

```text
Tailscale IP:
Machine name:
Key expiry decision:
Remote health check result:
```

Notes:

```text

```

## Phase 10 - LAN Access Test With Shift Manager PC

Status: pending

Goal: confirm the shift manager can use admin pages over LAN.

Steps:

1. From shift-manager PC, open:

```text
http://APP-VM-IP:8000/admin
```

2. Test:
   - `/admin/import`
   - `/admin/planning`
   - `/terminal` as a read-only verification view

3. Import a small test CSV if appropriate.
4. Release a test card.
5. Confirm it appears in `/terminal`.

Acceptance:

- Shift manager PC can reach app reliably over LAN.
- Admin import and planning pages work from that PC.

Record:

```text
Shift manager PC tested:
Browser:
Import test result:
Release test result:
```

Notes:

```text

```

## Phase 11 - Workstation/Kiosk Setup Later

Status: deferred

Goal: create production workstation/kiosk after terminal UI is stable enough.

Confirmed direction:

- Use Linux kiosk mode, not Windows kiosk mode.
- Install Debian 13.x on the workstation.
- Use the Debian `amd64` netinst installer, currently `debian-13.5.0-amd64-netinst.iso`.
- Create the installer USB with Rufus in DD image mode.
- It is normal for Windows to stop showing the USB as a normal readable drive after Rufus writes the Debian installer in DD image mode.
- Start with a normal Debian installation, then apply workstation kiosk provisioning later.
- Kiosk provisioning should eventually create a kiosk user, configure auto-login, launch a browser in kiosk mode, and point to:

```text
http://APP-VM-IP:8000/terminal
```

Workstation settings to verify:

- no sleep during shifts
- no lock screen interruptions
- browser opens automatically after reboot
- no restore-tabs prompt
- no update prompts during production
- screen resolution and scaling fit terminal UI
- touchscreen or mouse behavior works
- keyboard behavior works for gross weight entry
- operator cannot easily reach admin page or desktop

Acceptance:

- On reboot, workstation opens directly to `/terminal`.
- Operator sees only the terminal workflow.
- Admin access is not exposed from the terminal UI.

Record:

```text
Workstation OS: Debian 13.x, using debian-13.5.0-amd64-netinst.iso for current install media
Install media: USB written with Rufus in DD image mode
Kiosk approach: Linux kiosk mode; normal Debian install first, provisioning script later
Browser:
Kiosk command/config:
Resolution:
Input devices:
Reboot behavior:
```

Notes:

```text
The Debian installer USB may appear unreadable or may not mount in Windows after being written in DD image mode. This is expected and does not mean the installer failed.
```

## Phase 12 - Final Pre-Pilot Infrastructure Rehearsal

Status: pending

Goal: verify infrastructure readiness before real pilot use.

Steps:

1. Reboot Proxmox host.
2. Confirm app VM starts.
3. Confirm app service starts.
4. Confirm `/health`, `/admin`, and `/terminal`.
5. Confirm backup timer still active.
6. Create a backup.
7. Run restore rehearsal to test target.
8. Confirm Tailscale access.
9. Confirm shift-manager PC can import and release.
10. Confirm workstation/kiosk opens `/terminal`.

Acceptance:

- Full restart and recovery path is understood.
- Backups exist and restore helper works.
- Shift manager and workstation can access their intended views.
- No public internet exposure is required.

Record:

```text
Rehearsal date:
Reboot result:
Backup result:
Restore result:
Shift-manager access:
Workstation access:
Known infrastructure limitations:
```

Notes:

```text

```

## Command Reference

App service:

```bash
sudo systemctl status extrusion-terminal.service
sudo systemctl restart extrusion-terminal.service
journalctl -u extrusion-terminal.service -n 100 --no-pager
```

Backup:

```bash
sudo systemctl start extrusion-terminal-backup.service
systemctl list-timers extrusion-terminal-backup.timer
ls -lh /opt/extrusion-terminal/backups
```

App health:

```text
http://APP-VM-IP:8000/health
```

Admin:

```text
http://APP-VM-IP:8000/admin
```

Terminal:

```text
http://APP-VM-IP:8000/terminal
```

## Open Questions

Record answers as they are decided.

```text
Will the app VM use Debian or Ubuntu Server?
Will Proxmox/app VM use static IPs or DHCP reservations?
Where should backups be copied outside the VM?
Will Tailscale be installed on Proxmox host, app VM, or both?
```
