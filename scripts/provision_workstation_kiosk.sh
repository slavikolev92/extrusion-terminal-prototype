#!/usr/bin/env bash
set -Eeuo pipefail

DEFAULT_TERMINAL_URL="http://127.0.0.1:8000/terminal"
TERMINAL_URL=""
TAILSCALE_HOSTNAME="extrusion-workstation-prototype"
ENABLE_AUTOLOGIN=0
DISABLE_AUTOLOGIN=0
RUN_TAILSCALE_UP=1

usage() {
    cat <<'EOF'
Provision the Debian/Xfce workstation as an extrusion terminal kiosk.

Usage:
  sudo bash scripts/provision_workstation_kiosk.sh [options]

Options:
  --terminal-url URL        Set /etc/extrusion-kiosk-url. Defaults to
                            http://127.0.0.1:8000/terminal unless the file
                            already exists.
  --enable-autologin       Enable LightDM auto-login for the kiosk user.
                            Use only after SSH/Tailscale maintenance access
                            has been verified.
  --disable-autologin      Disable kiosk auto-login by moving the LightDM
                            config aside.
  --skip-tailscale-up      Install and start Tailscale, but do not run
                            tailscale up.
  --tailscale-hostname NAME Set the Tailscale hostname used by tailscale up.
                            Default: extrusion-workstation-prototype.
  -h, --help                Show this help.

Recommended first run:
  sudo bash scripts/provision_workstation_kiosk.sh --terminal-url http://APP-VM-IP:8000/terminal

After approving Tailscale and confirming SSH/Tailscale maintenance:
  sudo bash scripts/provision_workstation_kiosk.sh --enable-autologin
  sudo reboot
EOF
}

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --terminal-url)
            [ "$#" -ge 2 ] || die "--terminal-url requires a URL"
            TERMINAL_URL="$2"
            shift 2
            ;;
        --enable-autologin)
            ENABLE_AUTOLOGIN=1
            shift
            ;;
        --disable-autologin)
            DISABLE_AUTOLOGIN=1
            shift
            ;;
        --skip-tailscale-up)
            RUN_TAILSCALE_UP=0
            shift
            ;;
        --tailscale-hostname)
            [ "$#" -ge 2 ] || die "--tailscale-hostname requires a name"
            TAILSCALE_HOSTNAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

[ "$ENABLE_AUTOLOGIN" -eq 0 ] || [ "$DISABLE_AUTOLOGIN" -eq 0 ] || die "Use only one of --enable-autologin or --disable-autologin"
[ "${EUID:-$(id -u)}" -eq 0 ] || die "Run this script with sudo or as root"

if [ -z "$TERMINAL_URL" ]; then
    if [ -r /etc/extrusion-kiosk-url ]; then
        TERMINAL_URL="$(head -n 1 /etc/extrusion-kiosk-url)"
    else
        TERMINAL_URL="$DEFAULT_TERMINAL_URL"
    fi
fi

[ -r /etc/os-release ] || die "/etc/os-release not found"
# shellcheck disable=SC1091
. /etc/os-release
VERSION_CODENAME="${VERSION_CODENAME:-}"
[ -n "$VERSION_CODENAME" ] || die "Could not determine Debian codename from /etc/os-release"

if [ "${ID:-}" != "debian" ]; then
    log "This script is intended for Debian. Detected ID=${ID:-unknown}; continuing anyway."
fi

log "Installing Debian packages"
apt-get update
apt-get install -y chromium curl ca-certificates x11-xserver-utils unclutter lightdm openssh-server
systemctl enable --now ssh

log "Installing Tailscale from the official Debian repository"
install -d -m 0755 /usr/share/keyrings
curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.noarmor.gpg" \
    | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL "https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}.tailscale-keyring.list" \
    | tee /etc/apt/sources.list.d/tailscale.list >/dev/null
apt-get update
apt-get install -y tailscale
systemctl enable --now tailscaled

if [ "$RUN_TAILSCALE_UP" -eq 1 ]; then
    if tailscale status 2>&1 | grep -qi 'Logged out'; then
        log "Starting Tailscale login. Approve the URL this command prints."
        tailscale up --hostname "$TAILSCALE_HOSTNAME"
    elif tailscale status >/dev/null 2>&1; then
        log "Tailscale already appears to be connected"
    else
        log "Starting Tailscale login. Approve the URL this command prints."
        tailscale up --hostname "$TAILSCALE_HOSTNAME"
    fi
else
    log "Skipping tailscale up because --skip-tailscale-up was provided"
fi

log "Creating kiosk user if needed"
if id -u kiosk >/dev/null 2>&1; then
    log "User kiosk already exists"
else
    adduser --disabled-password --gecos "Extrusion Kiosk" kiosk
fi

log "Writing terminal URL config"
printf '%s\n' "$TERMINAL_URL" > /etc/extrusion-kiosk-url
chmod 0644 /etc/extrusion-kiosk-url

log "Writing Chromium kiosk launcher"
cat > /usr/local/bin/extrusion-kiosk-session <<'EOF'
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
    BROWSER="$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)"
    if [ -z "$BROWSER" ]; then
        sleep 10
        continue
    fi

    if [ -r "$URL_FILE" ]; then
        KIOSK_URL="$(head -n 1 "$URL_FILE")"
    else
        KIOSK_URL="$DEFAULT_URL"
    fi

    "$BROWSER" \
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
chmod 0755 /usr/local/bin/extrusion-kiosk-session

log "Writing LightDM kiosk session"
cat > /usr/share/xsessions/extrusion-kiosk.desktop <<'EOF'
[Desktop Entry]
Name=Extrusion Terminal Kiosk
Comment=Launch Chromium directly to the extrusion terminal app
Exec=/usr/local/bin/extrusion-kiosk-session
Type=Application
EOF
chmod 0644 /usr/share/xsessions/extrusion-kiosk.desktop

log "Disabling sleep and idle suspend"
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
install -d -m 0755 /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/10-extrusion-kiosk.conf <<'EOF'
[Login]
IdleAction=ignore
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandlePowerKey=poweroff
EOF
systemctl restart systemd-logind || true

log "Configuring LightDM auto-login state"
install -d -m 0755 /etc/lightdm/lightdm.conf.d
if [ "$DISABLE_AUTOLOGIN" -eq 1 ]; then
    if [ -f /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf ]; then
        mv /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf.disabled
    fi
    log "Kiosk auto-login disabled"
elif [ "$ENABLE_AUTOLOGIN" -eq 1 ]; then
    cat > /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf <<'EOF'
[Seat:*]
autologin-user=kiosk
autologin-user-timeout=0
user-session=extrusion-kiosk
EOF
    chmod 0644 /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf
    log "Kiosk auto-login enabled"
else
    log "Kiosk auto-login not enabled. Re-run with --enable-autologin after verifying maintenance access."
fi

log "Provisioning summary"
cat <<EOF
Terminal URL: $(cat /etc/extrusion-kiosk-url)
Kiosk launcher: /usr/local/bin/extrusion-kiosk-session
Kiosk session: /usr/share/xsessions/extrusion-kiosk.desktop
Auto-login config: /etc/lightdm/lightdm.conf.d/50-extrusion-kiosk.conf

Manual checks before enabling auto-login:
  tailscale ip
  tailscale status
  systemctl is-active ssh
  ssh ADMIN_USER@WORKSTATION_IP

Enable kiosk auto-login after maintenance access is confirmed:
  sudo bash scripts/provision_workstation_kiosk.sh --enable-autologin
  sudo reboot

Update the kiosk URL later:
  sudo bash scripts/provision_workstation_kiosk.sh --terminal-url http://APP-VM-IP:8000/terminal
EOF
