# Workstation Kiosk Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Debian/Xfce workstation PC into a maintainable Chromium kiosk for the extrusion terminal prototype.

**Architecture:** Keep the normal Debian admin account for maintenance, create a separate non-sudo `kiosk` user, and configure LightDM to auto-login that user into a Chromium-only kiosk session. Store the terminal URL in `/etc/extrusion-kiosk-url` so the app server address can be changed after the PC moves to the business LAN.

**Tech Stack:** Debian 13, LightDM, X11, Chromium, Tailscale, OpenSSH.

---

## Confirmed Decisions

- Workstation OS: Debian, installed with Xfce and SSH server.
- Debian admin behavior: the install user `extrusion-terminal` has sudo access, but is not a root login shell. Use `sudo` for provisioning commands.
- Lock-down level: maintainable operator kiosk, not hardened appliance.
- Browser: Chromium.
- Maintenance access: existing Debian admin user over LAN SSH and Tailscale.
- Operator account: separate `kiosk` user with no sudo access.
- Kiosk URL: editable config file at `/etc/extrusion-kiosk-url`.
- Current tested kiosk URL: `http://192.168.1.83:8000/terminal`.
- Printing: out of scope for this workstation prototype.
- Known hardware risk: CMOS battery may be weak; do not block setup on it.
- Already verified by user: HDD boot and Ethernet work.
- Final prototype result: auto-login kiosk works after adding `xfwm4 --replace`, Chromium keyring suppression, and conservative Chromium GPU flags.

## Lessons From First Workstation Provisioning

- Use `sudo`; do not assume the install user is a root shell. `whoami` reports `extrusion-terminal`, while `sudo whoami` reports `root`.
- Set the real terminal URL before enabling auto-login. The first run used the local placeholder URL, which made the kiosk open the wrong target.
- Tailscale ping/status is not enough to prove maintenance access. Confirm `Test-NetConnection WORKSTATION_TAILSCALE_IP -Port 22` and `ssh extrusion-terminal@WORKSTATION_TAILSCALE_IP`.
- Tailscale ACLs must explicitly allow trusted admin machines to SSH to the workstation. The working ACL added host `extrusion-workstation = 100.94.38.101`, allowed `desktop-laptop` and `desktop-pc` to `extrusion-workstation` on `tcp:22`, and allowed `extrusion-workstation` to `extrusion-app` on `tcp:8000`.
- Chromium in the custom LightDM session showed a keyring prompt until launched with `--password-store=basic`.
- Chromium rendered as a vertical half-white/half-black screen until the kiosk launcher started `xfwm4 --replace` before Chromium and used `--disable-gpu` plus `--disable-gpu-compositing`.
- HP BIOS Power-On Options includes `Bypass F1 Prompt on Configuration Changes`; enabling it skipped the previous `163 - Time & Date Not Set` / `F1` boot-blocking screen during testing. The weak CMOS battery may still reset BIOS time after full power loss.
- Linux time, NTP, and RTC were corrected and verified on 2026-06-20. `timedatectl` showed Europe/Sofia time, synchronized system clock, active NTP, and `sudo hwclock --show` returned 2026-06-20 after `sudo hwclock --systohc`.

## Files Created On The Workstation

- `scripts/provision_workstation_kiosk.sh` - repo script that automates the workstation setup.
- `/etc/extrusion-kiosk-url` - one-line terminal URL.
- `/usr/local/bin/extrusion-kiosk-session` - launches Chromium kiosk and restarts it if it exits.
- `/usr/share/xsessions/extrusion-kiosk.desktop` - LightDM session entry.
- `/etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf` - auto-login configuration.
- `/etc/systemd/logind.conf.d/10-extrusion-kiosk.conf` - prevent idle suspend behavior.

## Preferred Automated Execution

Use the script for all repeatable setup. Keep only the approval and acceptance checks manual.

First pass, without auto-login:

```bash
sudo bash scripts/provision_workstation_kiosk.sh --terminal-url http://192.168.1.83:8000/terminal
```

Manual checkpoint:

```bash
tailscale ip
tailscale status
systemctl is-active ssh
ssh ADMIN_USER@WORKSTATION_IP
```

After Tailscale and SSH maintenance access work:

```bash
sudo bash scripts/provision_workstation_kiosk.sh --enable-autologin
sudo reboot
```

When the app VM IP changes:

```bash
sudo bash scripts/provision_workstation_kiosk.sh --terminal-url http://APP-VM-IP:8000/terminal
sudo reboot
```

To temporarily disable kiosk auto-login:

```bash
sudo bash scripts/provision_workstation_kiosk.sh --disable-autologin
sudo reboot
```

## Task 1: Capture Current Workstation Facts

**Files:**
- Modify: `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: On the workstation, capture OS/session/network facts**

Run:

```bash
cat /etc/os-release
echo "USER=$USER"
echo "XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP"
echo "DESKTOP_SESSION=$DESKTOP_SESSION"
echo "XDG_SESSION_TYPE=$XDG_SESSION_TYPE"
hostname
ip -brief addr
systemctl is-enabled ssh
systemctl is-active ssh
```

Expected:

```text
Debian 13/trixie or the installed Debian version is shown.
Xfce is shown as the current desktop/session.
Ethernet has an IPv4 address from DHCP.
ssh is enabled and active.
```

- [ ] **Step 2: Record the actual values**

Update `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` Phase 11 `Record` fields with:

```text
Workstation OS:
Desktop/session:
Network address during setup:
SSH status:
```

## Task 2: Install Workstation Packages

**Files:**
- Use: `scripts/provision_workstation_kiosk.sh`
- Workstation package database.

- [ ] **Step 1: Update apt metadata**

Run on the workstation through the provisioning script:

```bash
sudo bash scripts/provision_workstation_kiosk.sh --skip-tailscale-up
```

Expected:

```text
Chromium, curl, ca-certificates, xset utilities, unclutter, LightDM, OpenSSH server, Tailscale package config, kiosk user, kiosk launcher, kiosk session, and sleep-prevention config are installed or refreshed.
Auto-login is not enabled.
```

- [ ] **Step 2: Confirm commands exist**

Run:

```bash
command -v chromium
command -v xset
command -v unclutter
systemctl is-enabled lightdm
```

Expected:

```text
/usr/bin/chromium
/usr/bin/xset
/usr/bin/unclutter
enabled
```

If `lightdm` is not enabled, run:

```bash
sudo systemctl enable lightdm
```

## Task 3: Install And Connect Tailscale

**Files:**
- Use: `scripts/provision_workstation_kiosk.sh`
- Create on workstation: `/etc/apt/sources.list.d/tailscale.list`
- Create on workstation: `/usr/share/keyrings/tailscale-archive-keyring.gpg`

- [ ] **Step 1: Run the normal provisioning pass**

Run:

```bash
sudo bash scripts/provision_workstation_kiosk.sh
```

Expected:

```text
The script installs Tailscale and prints an authentication URL if the workstation is not already connected.
Open the URL from an admin machine, authenticate, and approve the workstation.
```

- [ ] **Step 2: Verify Tailscale**

Run:

```bash
tailscale ip
tailscale status
```

Expected:

```text
The workstation has a Tailscale IP and appears online in tailscale status.
```

## Task 4: Create The Kiosk User And Editable URL Config

**Files:**
- Create: `/etc/extrusion-kiosk-url`
- Create: `/home/kiosk/`

- [ ] **Step 1: Create the non-sudo kiosk user**

Run:

```bash
sudo adduser --disabled-password --gecos "Extrusion Kiosk" kiosk
```

Expected:

```text
User kiosk is created. It is not added to sudo.
```

- [ ] **Step 2: Create the terminal URL config**

Run:

```bash
printf '%s\n' 'http://127.0.0.1:8000/terminal' | sudo tee /etc/extrusion-kiosk-url >/dev/null
sudo chmod 0644 /etc/extrusion-kiosk-url
```

Expected:

```text
/etc/extrusion-kiosk-url exists and contains one URL.
```

When the business LAN app server IP is known, update it with:

```bash
printf '%s\n' 'http://APP-VM-IP:8000/terminal' | sudo tee /etc/extrusion-kiosk-url >/dev/null
```

## Task 5: Create The Chromium Kiosk Session

**Files:**
- Create: `/usr/local/bin/extrusion-kiosk-session`
- Create: `/usr/share/xsessions/extrusion-kiosk.desktop`

- [ ] **Step 1: Create the kiosk launcher script**

Run:

```bash
sudo tee /usr/local/bin/extrusion-kiosk-session >/dev/null <<'EOF'
#!/bin/sh
set -eu

URL_FILE="/etc/extrusion-kiosk-url"
DEFAULT_URL="http://127.0.0.1:8000/terminal"
PROFILE_DIR="$HOME/.config/extrusion-chromium"

xset s off || true
xset s noblank || true
xset -dpms || true
export XDG_CURRENT_DESKTOP=XFCE
export DESKTOP_SESSION=xfce
if command -v xfwm4 >/dev/null 2>&1; then
    xfwm4 --replace &
    sleep 1
fi
unclutter -idle 2 -root &

mkdir -p "$PROFILE_DIR"

while true; do
    if [ -r "$URL_FILE" ]; then
        KIOSK_URL="$(head -n 1 "$URL_FILE")"
    else
        KIOSK_URL="$DEFAULT_URL"
    fi

    chromium \
        --kiosk \
        --disable-gpu \
        --disable-gpu-compositing \
        --no-first-run \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-features=Translate \
        --password-store=basic \
        --user-data-dir="$PROFILE_DIR" \
        "$KIOSK_URL" || true

    sleep 2
done
EOF
sudo chmod 0755 /usr/local/bin/extrusion-kiosk-session
```

Expected:

```text
/usr/local/bin/extrusion-kiosk-session is executable.
```

- [ ] **Step 2: Create the LightDM session entry**

Run:

```bash
sudo tee /usr/share/xsessions/extrusion-kiosk.desktop >/dev/null <<'EOF'
[Desktop Entry]
Name=Extrusion Terminal Kiosk
Comment=Launch Chromium directly to the extrusion terminal app
Exec=/usr/local/bin/extrusion-kiosk-session
Type=Application
EOF
```

Expected:

```text
The login manager has an Extrusion Terminal Kiosk session option.
```

- [ ] **Step 3: Manual-test the kiosk script from the current desktop**

Run:

```bash
/usr/local/bin/extrusion-kiosk-session
```

Expected:

```text
Chromium opens full-screen to the URL from /etc/extrusion-kiosk-url.
Press Ctrl+C in the terminal used to start the test, or switch terminal/window and stop the process, before continuing.
```

## Task 6: Configure Auto-Login Into The Kiosk Session

**Files:**
- Create: `/etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf`

- [ ] **Step 1: Configure LightDM auto-login**

Run:

```bash
sudo mkdir -p /etc/lightdm/lightdm.conf.d
sudo tee /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf >/dev/null <<'EOF'
[Seat:*]
autologin-user=kiosk
autologin-user-timeout=0
user-session=extrusion-kiosk
EOF
```

Expected:

```text
LightDM will auto-login kiosk into the extrusion-kiosk session on next graphical start.
```

- [ ] **Step 2: Keep the existing admin user for maintenance**

Run:

```bash
getent passwd kiosk
groups kiosk
```

Expected:

```text
kiosk exists and is not in the sudo group.
```

Do not remove or weaken the existing admin user created during Debian installation.

## Task 7: Disable Sleep, Screen Blank, And Lock Interruptions

**Files:**
- Create: `/etc/systemd/logind.conf.d/10-extrusion-kiosk.conf`

- [ ] **Step 1: Disable system sleep targets**

Run:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Expected:

```text
The sleep and hibernate targets are masked.
```

- [ ] **Step 2: Configure logind to ignore idle suspend**

Run:

```bash
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/10-extrusion-kiosk.conf >/dev/null <<'EOF'
[Login]
IdleAction=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandlePowerKey=poweroff
EOF
sudo systemctl restart systemd-logind
```

Expected:

```text
The system does not suspend because of idle behavior. The power button still performs a normal poweroff.
```

The kiosk launcher also runs `xset s off`, `xset s noblank`, and `xset -dpms` inside the graphical session to prevent X11 screen blanking.

## Task 8: Reboot And Acceptance Test

**Files:**
- Modify: `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Reboot the workstation**

Run:

```bash
sudo reboot
```

Expected:

```text
After reboot, the workstation automatically opens Chromium full-screen to the terminal URL.
```

- [ ] **Step 2: Verify operator-facing behavior**

Check manually:

```text
No normal desktop panel or menu is visible.
Chromium address bar is not visible.
Closing Chromium causes it to reopen.
The terminal app can be used with keyboard and mouse.
The workstation does not sleep or lock during a reasonable idle check.
```

- [ ] **Step 3: Verify maintenance access**

From another machine on LAN or Tailscale, run:

```bash
ssh ADMIN_USER@WORKSTATION_IP
```

Expected:

```text
The admin user can log in over SSH. The kiosk user is not needed for maintenance.
```

- [ ] **Step 4: Record results**

Update `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md` Phase 11 `Record` fields:

```text
Browser: Chromium
Kiosk command/config: /usr/local/bin/extrusion-kiosk-session, /etc/extrusion-kiosk-url, LightDM extrusion-kiosk session
Tailscale machine name: extrusion-workstation-prototype
Reboot behavior:
Known limitations:
```

## Task 9: Recovery And URL Change Procedures

**Files:**
- Modify: `INFRASTRUCTURE_IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Document how to update the terminal URL**

Add this procedure to Phase 11 notes:

```bash
printf '%s\n' 'http://APP-VM-IP:8000/terminal' | sudo tee /etc/extrusion-kiosk-url >/dev/null
sudo reboot
```

Expected:

```text
After reboot, Chromium opens the new terminal URL.
```

- [ ] **Step 2: Document how to temporarily disable kiosk auto-login**

Add this procedure to Phase 11 notes:

```bash
sudo mv /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf.disabled
sudo reboot
```

Expected:

```text
After reboot, LightDM shows a normal login screen for maintenance.
```

- [ ] **Step 3: Document how to re-enable kiosk auto-login**

Add this procedure to Phase 11 notes:

```bash
sudo mv /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf.disabled /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf
sudo reboot
```

Expected:

```text
After reboot, the kiosk auto-login returns.
```

## Self-Review

- Spec coverage: Covers Debian/Xfce workstation, Chromium, kiosk user, editable URL, Tailscale, no workstation printing, sleep/lock prevention, reboot acceptance, and maintenance recovery.
- Placeholder scan: The symbolic values `APP-VM-IP`, `ADMIN_USER`, and `WORKSTATION_IP` appear only in operator-facing procedures where the exact production network values are not known yet. The setup itself starts with a local default URL and remains editable.
- Scope check: This plan does not configure printers, app server deployment, Proxmox, backups, or public internet exposure.
