#!/usr/bin/env bash
set -Eeuo pipefail

BUNDLE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_PREFIX="${EXTRUSION_INSTALL_ROOT:-}"
APT_GET="${EXTRUSION_INSTALL_APT_GET:-apt-get}"
ID="${EXTRUSION_INSTALL_ID:-id}"
INSTALL="${EXTRUSION_INSTALL_INSTALL:-install}"

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

validate_prefixed_path() {
    local requested_path="$1"
    local existing_path="$requested_path"
    local resolved_path

    [ -n "$ROOT_PREFIX" ] || return 0
    while [ ! -e "$existing_path" ] && [ ! -L "$existing_path" ]; do
        [ "$existing_path" != "$ROOT_PREFIX" ] || break
        existing_path="${existing_path%/*}"
        [ -n "$existing_path" ] || existing_path="/"
    done
    resolved_path="$(realpath -e -- "$existing_path")" || die "Could not resolve rooted path: $requested_path"
    case "$resolved_path" in
        "$ROOT_PREFIX"|"$ROOT_PREFIX"/*) ;;
        *) die "Rooted path escapes EXTRUSION_INSTALL_ROOT: $requested_path" ;;
    esac
}

if [ -z "$ROOT_PREFIX" ]; then
    [ "${EUID:-$(id -u)}" -eq 0 ] || die "Run this installer with sudo or as root"
else
    case "$ROOT_PREFIX" in
        //*) die "EXTRUSION_INSTALL_ROOT must not use multiple leading slashes" ;;
        /*) ;;
        *) die "EXTRUSION_INSTALL_ROOT must be an absolute test path" ;;
    esac
    case "/$ROOT_PREFIX/" in
        */./*|*/../*) die "EXTRUSION_INSTALL_ROOT must not contain dot path components" ;;
    esac
    [ -d "$ROOT_PREFIX" ] || die "EXTRUSION_INSTALL_ROOT must be an existing directory"
    ROOT_PREFIX="$(realpath -e -- "$ROOT_PREFIX")" || die "EXTRUSION_INSTALL_ROOT could not be resolved"
    [ "$ROOT_PREFIX" != "/" ] || die "EXTRUSION_INSTALL_ROOT must not resolve to /"
fi

for runtime_file in extrusion-kiosk-maintenance extrusion-kiosk-session maintenance.html gears.png; do
    [ -f "$BUNDLE_DIR/$runtime_file" ] && [ -r "$BUNDLE_DIR/$runtime_file" ] || die "Bundle runtime file is not a regular readable file: $runtime_file"
done
[ -f "$BUNDLE_DIR/extrusion-kiosk-maintenance" ] && [ -x "$BUNDLE_DIR/extrusion-kiosk-maintenance" ] || die "Bundle runtime script is not a regular executable file: extrusion-kiosk-maintenance"
[ -f "$BUNDLE_DIR/extrusion-kiosk-session" ] && [ -x "$BUNDLE_DIR/extrusion-kiosk-session" ] || die "Bundle runtime script is not a regular executable file: extrusion-kiosk-session"

for rooted_path in \
    "$ROOT_PREFIX/etc/extrusion-kiosk-url" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session" \
    "$ROOT_PREFIX/usr/share/xsessions/extrusion-kiosk.desktop" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-maintenance" \
    "$ROOT_PREFIX/usr/local/share/extrusion-kiosk" \
    "$ROOT_PREFIX/var/lib/extrusion-kiosk"; do
    validate_prefixed_path "$rooted_path"
done

[ -f "$ROOT_PREFIX/etc/extrusion-kiosk-url" ] && [ -r "$ROOT_PREFIX/etc/extrusion-kiosk-url" ] || die "Missing regular readable $ROOT_PREFIX/etc/extrusion-kiosk-url; run base kiosk provisioning first"
[ -f "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session" ] && [ -x "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session" ] || die "Missing regular executable $ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session; run base kiosk provisioning first"
[ -f "$ROOT_PREFIX/usr/share/xsessions/extrusion-kiosk.desktop" ] && [ -r "$ROOT_PREFIX/usr/share/xsessions/extrusion-kiosk.desktop" ] || die "Missing regular readable $ROOT_PREFIX/usr/share/xsessions/extrusion-kiosk.desktop; run base kiosk provisioning first"
"$ID" -u kiosk >/dev/null 2>&1 || die "The kiosk user must already exist; run base kiosk provisioning first"

"$APT_GET" update
"$APT_GET" install -y yad

"$INSTALL" -d -m 0755 "$ROOT_PREFIX/usr/local/share/extrusion-kiosk"
"$INSTALL" -d -m 0755 "$ROOT_PREFIX/var/lib/extrusion-kiosk"
"$INSTALL" -m 0755 "$BUNDLE_DIR/extrusion-kiosk-maintenance" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-maintenance"
"$INSTALL" -m 0755 "$BUNDLE_DIR/extrusion-kiosk-session" \
    "$ROOT_PREFIX/usr/local/bin/extrusion-kiosk-session"
"$INSTALL" -m 0644 "$BUNDLE_DIR/maintenance.html" \
    "$ROOT_PREFIX/usr/local/share/extrusion-kiosk/maintenance.html"
"$INSTALL" -m 0644 "$BUNDLE_DIR/gears.png" \
    "$ROOT_PREFIX/usr/local/share/extrusion-kiosk/gears.png"

cat <<'EOF'

Maintenance bundle installed. Reboot the workstation once to start the updated kiosk session:
  sudo reboot

After reconnecting, confirm the selected kiosk mode:
  sudo extrusion-kiosk-maintenance status

The independent base kiosk provisioner can replace the launcher. After any base
kiosk provisioning, rerun this installer and reboot the workstation.
EOF
