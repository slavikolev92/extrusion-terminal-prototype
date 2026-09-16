#!/usr/bin/env bash
set -Eeuo pipefail

INSTALLER_CALLER_PATH="${PATH:-/usr/sbin:/usr/bin:/sbin:/bin}"
PATH="/usr/sbin:/usr/bin:/sbin:/bin"
export PATH

PRODUCTION_BASE_DIR="/opt/extrusion-terminal"
PRODUCTION_APP_DIR="$PRODUCTION_BASE_DIR/app"
PRODUCTION_CONFIG_DIR="/etc/extrusion-terminal"
PRODUCTION_SYSTEMD_DIR="/etc/systemd/system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCRIPT_REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd -P)"
REPO_DIR="$SCRIPT_REPO_DIR"
UNIT_SOURCE_DIR="$REPO_DIR/deployment/systemd"
DRY_RUN=0
ENABLE_ONLY=0
TEST_ROOT=""
STAGE_DIR=""
UNIT_MUTATION_STARTED=0
TIMERS_FORCED_DISABLED=0
TRANSACTION_COMMITTED=0
SOURCE_REVISION=""
REQUESTED_APP_DIR=""
ACCEPTED_REVISION=""
APP_HOME=""

UNIT_NAMES=(
    extrusion-terminal-backup.service
    extrusion-terminal-backup.timer
    extrusion-terminal-delivery.service
    extrusion-terminal-delivery.timer
)
TIMER_NAMES=(
    extrusion-terminal-backup.timer
    extrusion-terminal-delivery.timer
)

usage() {
    cat <<'EOF'
Install the source-controlled Task 25 backup and delivery units, disabled by default.

Usage:
  bash scripts/install_artifact_delivery.sh --accepted-revision SHA [--dry-run]
  bash TRUSTED_INSTALLER --app-dir /opt/extrusion-terminal/app \
    --accepted-revision SHA [--enable]

Options:
  --dry-run  Perform read-only preflight and print intended non-secret paths.
  --enable   Enable both timers after the separately approved acceptance checks.
  --app-dir  Fixed production checkout (required by a root-staged installer).
  --accepted-revision  Exact reviewed 40-character Git commit ID.
  -h, --help Show this help.

Normal installation verifies and installs the four units but leaves both timers
disabled. --enable refuses changed or unverified installed units. This script
never creates, displays, or edits either protected curl config.
EOF
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

git_as_app_user() {
    if [ -z "$TEST_ROOT" ] && [ "$(id -u)" -eq 0 ]; then
        runuser -u "$APP_OWNER" -- /usr/bin/env -i \
            HOME="$APP_HOME" PATH=/usr/bin:/bin GIT_NO_REPLACE_OBJECTS=1 \
            /usr/bin/git --no-replace-objects \
            -c safe.directory="$REPO_DIR" "$@"
    else
        /usr/bin/env -i \
            HOME="$APP_HOME" PATH=/usr/bin:/bin GIT_NO_REPLACE_OBJECTS=1 \
            /usr/bin/git --no-replace-objects \
            -c safe.directory="$REPO_DIR" "$@"
    fi
}

validate_accepted_checkout() {
    local current_revision

    [ -n "$ACCEPTED_REVISION" ] \
        || die "--accepted-revision is required for production"
    [[ "$ACCEPTED_REVISION" =~ ^[0-9a-f]{40}$ ]] \
        || die "Accepted revision must be an exact lowercase 40-character commit ID"
    current_revision="$(git_as_app_user -C "$REPO_DIR" rev-parse 'HEAD^{commit}')"
    [ "$current_revision" = "$ACCEPTED_REVISION" ] \
        || die "Production checkout does not match the accepted revision"
    [ -z "$(git_as_app_user -C "$REPO_DIR" status --porcelain=v1 --untracked-files=normal)" ] \
        || die "Production app checkout must be clean before privileged installation"
    git_as_app_user -C "$REPO_DIR" cat-file -e "$ACCEPTED_REVISION^{commit}" \
        || die "Accepted revision is unavailable in the production checkout"
    SOURCE_REVISION="$ACCEPTED_REVISION"
}

path_is_symlink() {
    [ -L "$1" ]
}

validate_directory() {
    local path="$1"
    local owner="$2"
    local group="$3"
    local mode="$4"

    ! path_is_symlink "$path" || die "Directory must not be a symbolic link: $path"
    [ -d "$path" ] || die "Required directory does not exist: $path"
    [ "$(stat -c '%U' "$path")" = "$owner" ] || die "Directory has wrong owner: $path"
    [ "$(stat -c '%G' "$path")" = "$group" ] || die "Directory has wrong group: $path"
    [ "$(stat -c '%a' "$path")" = "$mode" ] || die "Directory has wrong mode (expected $mode): $path"
}

validate_optional_directory() {
    local path="$1"
    local owner="$2"
    local group="$3"
    local mode="$4"

    if path_is_symlink "$path"; then
        die "Directory must not be a symbolic link: $path"
    fi
    if [ -e "$path" ]; then
        validate_directory "$path" "$owner" "$group" "$mode"
    fi
}

validate_secret_config() {
    local path="$1"
    local owner
    local group
    local mode
    local permissions

    [ -f "$path" ] && [ ! -L "$path" ] || die "Protected curl config is not a regular file: $path"
    owner="$(stat -c '%U' "$path")"
    group="$(stat -c '%G' "$path")"
    mode="$(stat -c '%a' "$path")"
    [ "$owner" = "$APP_OWNER" ] || die "Protected curl config must be owned by $APP_OWNER: $path"
    [ "$group" = "$APP_GROUP" ] || die "Protected curl config group must be $APP_GROUP: $path"
    [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "Protected curl config mode is invalid: $path"
    permissions=$((8#$mode))
    [ $((permissions & 0077)) -eq 0 ] || die "Protected curl config is group/world accessible: $path"
    [ $((permissions & 0400)) -ne 0 ] || die "Protected curl config is not readable by $APP_OWNER: $path"
}

validate_optional_summary_config() {
    local path="$1"

    if path_is_symlink "$path"; then
        die "Backup summary config must not be a symbolic link: $path"
    fi
    if [ ! -e "$path" ]; then
        return
    fi
    [ -f "$path" ] || die "Backup summary config is not a regular file: $path"
    [ "$(stat -c '%U' "$path")" = "$ANCHOR_OWNER" ] \
        || die "Backup summary config has wrong owner: $path"
    [ "$(stat -c '%G' "$path")" = "$APP_GROUP" ] \
        || die "Backup summary config has wrong group: $path"
    [ "$(stat -c '%a' "$path")" = "640" ] \
        || die "Backup summary config must have mode 640: $path"
}

validate_lock() {
    local path="$1"

    [ -f "$path" ] && [ ! -L "$path" ] || die "Lock is not a regular file: $path"
    [ "$(stat -c '%U' "$path")" = "$ANCHOR_OWNER" ] || die "Lock has wrong owner: $path"
    [ "$(stat -c '%G' "$path")" = "$APP_GROUP" ] || die "Lock has wrong group: $path"
    [ "$(stat -c '%a' "$path")" = "640" ] || die "Lock must have mode 640: $path"
}

validate_unit_source() {
    local unit_name="$1"
    local source="$UNIT_SOURCE_DIR/$unit_name"

    [ -f "$source" ] && [ ! -L "$source" ] || die "Unit source is not a regular file: $source"
    if [ -z "$TEST_ROOT" ]; then
        git_as_app_user -C "$REPO_DIR" ls-files --error-unmatch -- \
            "deployment/systemd/$unit_name" >/dev/null \
            || die "Unit source is not tracked by Git: $source"
        git_as_app_user -C "$REPO_DIR" cat-file -e \
            "$SOURCE_REVISION:deployment/systemd/$unit_name" \
            || die "Unit source is absent from accepted revision: $source"
    fi
}

validate_installed_unit() {
    local unit_name="$1"
    local installed="$SYSTEMD_DIR/$unit_name"

    [ -f "$installed" ] && [ ! -L "$installed" ] || die "Installed unit is not a regular file: $installed"
    [ "$(stat -c '%U' "$installed")" = "$ANCHOR_OWNER" ] || die "Installed unit has wrong owner: $installed"
    [ "$(stat -c '%G' "$installed")" = "$ANCHOR_GROUP" ] || die "Installed unit has wrong group: $installed"
    [ "$(stat -c '%a' "$installed")" = "644" ] || die "Installed unit must have mode 644: $installed"
}

timer_is_confirmed_disabled() {
    local timer_name="$1"
    local enabled_state
    local active_state

    enabled_state="$(systemctl is-enabled "$timer_name" 2>/dev/null || true)"
    active_state="$(systemctl is-active "$timer_name" 2>/dev/null || true)"
    [ "$enabled_state" = "disabled" ] && [ "$active_state" = "inactive" ]
}

timer_is_confirmed_enabled() {
    local timer_name="$1"
    local enabled_state
    local active_state

    enabled_state="$(systemctl is-enabled "$timer_name" 2>/dev/null || true)"
    active_state="$(systemctl is-active "$timer_name" 2>/dev/null || true)"
    [ "$enabled_state" = "enabled" ] && [ "$active_state" = "active" ]
}

disable_installed_timers() {
    local timer_name
    local timer_path

    for timer_name in "${TIMER_NAMES[@]}"; do
        timer_path="$SYSTEMD_DIR/$timer_name"
        if [ -e "$timer_path" ] || [ -L "$timer_path" ]; then
            validate_installed_unit "$timer_name"
            systemctl disable --now "$timer_name" \
                || die "Could not confirm Task 25 timer is disabled: $timer_name"
            timer_is_confirmed_disabled "$timer_name" \
                || die "Could not confirm Task 25 timer is disabled: $timer_name"
        fi
    done
}

best_effort_disable_installed_timers() {
    local result=0
    local timer_name
    local timer_path

    for timer_name in "${TIMER_NAMES[@]}"; do
        timer_path="$SYSTEMD_DIR/$timer_name"
        if [ -e "$timer_path" ] || [ -L "$timer_path" ]; then
            if [ ! -f "$timer_path" ] || [ -L "$timer_path" ]; then
                result=1
                continue
            fi
            systemctl disable --now "$timer_name" >/dev/null 2>&1 || result=1
            timer_is_confirmed_disabled "$timer_name" || result=1
        fi
    done
    return "$result"
}

validate_configuration_contents() {
    local validation_code
    validation_code='from pathlib import Path
import sys
from app import backup_activity, backup_summary
from app.curl_transport import validate_curl_config
from app.pipeline_notifications import validate_discord_webhook_config
validate_curl_config(Path(sys.argv[1]), required_options=frozenset({"user"}), allowed_options=frozenset({"user"}))
validate_discord_webhook_config(Path(sys.argv[2]))
backup_summary.load_summary_times(Path(sys.argv[3]))'

    if [ -z "$TEST_ROOT" ] && [ "$(id -u)" -eq 0 ]; then
        (
            cd "$APP_DIR"
            runuser -u "$APP_OWNER" -- "$PYTHON" -B -c "$validation_code" \
                "$WEBDAV_CURL_CONFIG" "$DISCORD_CURL_CONFIG" "$SUMMARY_CONFIG"
        )
    else
        [ "$(id -un)" = "$APP_OWNER" ] \
            || die "Config validation must run as $APP_OWNER or root"
        (
            cd "$APP_DIR"
            "$PYTHON" -B -c "$validation_code" \
                "$WEBDAV_CURL_CONFIG" "$DISCORD_CURL_CONFIG" "$SUMMARY_CONFIG"
        )
    fi
}

stage_accepted_units() {
    local unit_name
    local staged_path

    STAGE_DIR="$(mktemp -d "$BASE_DIR/.artifact-delivery-install.XXXXXX")"
    install -d -o "$ANCHOR_OWNER" -g "$ANCHOR_GROUP" -m 0700 \
        "$STAGE_DIR/new" "$STAGE_DIR/previous"
    for unit_name in "${UNIT_NAMES[@]}"; do
        staged_path="$STAGE_DIR/new/$unit_name"
        if [ -z "$TEST_ROOT" ]; then
            git_as_app_user -C "$REPO_DIR" show \
                "$SOURCE_REVISION:deployment/systemd/$unit_name" > "$staged_path"
            chown "$ANCHOR_OWNER:$ANCHOR_GROUP" "$staged_path"
            chmod 0644 "$staged_path"
        else
            install -o "$ANCHOR_OWNER" -g "$ANCHOR_GROUP" -m 0644 \
                "$UNIT_SOURCE_DIR/$unit_name" "$staged_path"
        fi
    done
}

remove_stage() {
    if [ -n "$STAGE_DIR" ] && [ -d "$STAGE_DIR" ]; then
        case "$STAGE_DIR" in
            "$BASE_DIR"/.artifact-delivery-install.*) rm -rf -- "$STAGE_DIR" ;;
            *) printf 'ERROR: refusing unsafe temporary cleanup: %s\n' "$STAGE_DIR" >&2 ;;
        esac
    fi
}

rollback_on_exit() {
    local status=$?
    local disable_confirmed=1
    local rollback_confirmed=1
    local unit_name
    trap - EXIT
    set +e

    if [ "$status" -ne 0 ] && [ "$UNIT_MUTATION_STARTED" -eq 1 ] \
        && [ "$TRANSACTION_COMMITTED" -eq 0 ]; then
        for unit_name in "${UNIT_NAMES[@]}"; do
            if [ -f "$STAGE_DIR/previous/$unit_name" ]; then
                install -o "$ANCHOR_OWNER" -g "$ANCHOR_GROUP" -m 0644 \
                    "$STAGE_DIR/previous/$unit_name" "$SYSTEMD_DIR/$unit_name" \
                    || rollback_confirmed=0
                cmp --silent "$STAGE_DIR/previous/$unit_name" \
                    "$SYSTEMD_DIR/$unit_name" || rollback_confirmed=0
            else
                rm -f -- "$SYSTEMD_DIR/$unit_name" || rollback_confirmed=0
                if [ -e "$SYSTEMD_DIR/$unit_name" ] \
                    || [ -L "$SYSTEMD_DIR/$unit_name" ]; then
                    rollback_confirmed=0
                fi
            fi
        done
        systemctl daemon-reload >/dev/null 2>&1 || rollback_confirmed=0
        best_effort_disable_installed_timers || disable_confirmed=0
        if [ "$rollback_confirmed" -eq 0 ]; then
            printf 'ERROR: unit installation failed and rollback is incomplete; recovery files are preserved at %s.\n' "$STAGE_DIR" >&2
        elif [ "$disable_confirmed" -eq 0 ]; then
            printf 'ERROR: previous units were restored, but Task 25 timer disablement could not be confirmed.\n' >&2
        else
            printf 'ERROR: unit installation failed; previous units were restored and timers remain disabled.\n' >&2
        fi
    elif [ "$status" -ne 0 ] && [ "$TIMERS_FORCED_DISABLED" -eq 1 ]; then
        best_effort_disable_installed_timers || disable_confirmed=0
        if [ "$disable_confirmed" -eq 0 ]; then
            printf 'ERROR: could not confirm Task 25 timers are disabled.\n' >&2
        fi
    fi
    if [ "$rollback_confirmed" -eq 1 ]; then
        remove_stage
    fi
    exit "$status"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --enable)
            ENABLE_ONLY=1
            shift
            ;;
        --app-dir)
            [ "$#" -ge 2 ] || die "--app-dir requires a path"
            REQUESTED_APP_DIR="$2"
            shift 2
            ;;
        --accepted-revision)
            [ "$#" -ge 2 ] || die "--accepted-revision requires a commit ID"
            ACCEPTED_REVISION="$2"
            shift 2
            ;;
        --test-root)
            [ "$#" -ge 2 ] || die "--test-root requires a path"
            TEST_ROOT="$2"
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

if [ -n "$TEST_ROOT" ]; then
    [ "$(id -u)" -ne 0 ] || die "--test-root is forbidden for root"
    [ -d "$TEST_ROOT" ] && [ ! -L "$TEST_ROOT" ] || die "Test root is not a regular directory"
    TEST_ROOT="$(cd "$TEST_ROOT" && pwd -P)"
    PATH="$INSTALLER_CALLER_PATH"
    export PATH
    BASE_DIR="$TEST_ROOT$PRODUCTION_BASE_DIR"
    APP_DIR="$SCRIPT_REPO_DIR"
    REPO_DIR="$APP_DIR"
    CONFIG_DIR="$TEST_ROOT$PRODUCTION_CONFIG_DIR"
    SYSTEMD_DIR="$TEST_ROOT$PRODUCTION_SYSTEMD_DIR"
    APP_OWNER="$(id -un)"
    APP_GROUP="$(id -gn)"
    ANCHOR_OWNER="$APP_OWNER"
    ANCHOR_GROUP="$APP_GROUP"
else
    BASE_DIR="$PRODUCTION_BASE_DIR"
    APP_DIR="${REQUESTED_APP_DIR:-$PRODUCTION_APP_DIR}"
    [ "$APP_DIR" = "$PRODUCTION_APP_DIR" ] \
        || die "Production app directory must be $PRODUCTION_APP_DIR"
    REPO_DIR="$APP_DIR"
    CONFIG_DIR="$PRODUCTION_CONFIG_DIR"
    SYSTEMD_DIR="$PRODUCTION_SYSTEMD_DIR"
    APP_OWNER="sk"
    APP_GROUP="sk"
    ANCHOR_OWNER="root"
    ANCHOR_GROUP="root"
fi

UNIT_SOURCE_DIR="$REPO_DIR/deployment/systemd"

RUNTIME_DIR="$BASE_DIR/artifact-delivery"
OUTBOX_DIR="$RUNTIME_DIR/outbox"
STATE_DIR="$RUNTIME_DIR/state"
MAINTENANCE_LOCK="$BASE_DIR/maintenance.lock"
OPERATION_LOCK="$RUNTIME_DIR/operation.lock"
WEBDAV_CURL_CONFIG="$CONFIG_DIR/hetzner-webdav.conf"
DISCORD_CURL_CONFIG="$CONFIG_DIR/discord-webhook.conf"
SUMMARY_CONFIG="$CONFIG_DIR/backup-summary.conf"
PYTHON="$APP_DIR/.venv/bin/python"

require_command git
require_command getent
require_command id
require_command install
require_command stat
require_command systemctl
require_command systemd-analyze
require_command cmp
require_command mktemp
require_command chown
require_command chmod
if [ -z "$TEST_ROOT" ] && [ "$(id -u)" -eq 0 ]; then
    require_command runuser
fi
[ -x /usr/bin/flock ] || die "Required command not found: /usr/bin/flock"

[ -d "$APP_DIR" ] && [ ! -L "$APP_DIR" ] || die "Production app directory is invalid: $APP_DIR"
APP_DIR="$(cd "$APP_DIR" && pwd -P)"
if [ -z "$TEST_ROOT" ]; then
    id -u sk >/dev/null 2>&1 || die "Production user does not exist: sk"
    getent group sk >/dev/null 2>&1 || die "Production group does not exist: sk"
    APP_HOME="$(getent passwd "$APP_OWNER")"
    APP_HOME="${APP_HOME#*:*:*:*:*:}"
    APP_HOME="${APP_HOME%%:*}"
    [ -d "$APP_HOME" ] || die "Production user home is invalid: $APP_OWNER"
    validate_accepted_checkout
fi
[ -x "$PYTHON" ] || die "Production virtualenv Python is missing"
for module in artifact_outbox curl_transport pipeline_notifications artifact_delivery backup_activity backup_job backup_summary; do
    [ -f "$APP_DIR/app/$module.py" ] || die "Required Task 25 module is missing: app/$module.py"
done
validate_directory "$BASE_DIR" "$ANCHOR_OWNER" "$ANCHOR_GROUP" 755
validate_secret_config "$WEBDAV_CURL_CONFIG"
validate_secret_config "$DISCORD_CURL_CONFIG"
validate_optional_summary_config "$SUMMARY_CONFIG"
for unit_name in "${UNIT_NAMES[@]}"; do
    validate_unit_source "$unit_name"
done
validate_configuration_contents

validate_optional_directory "$RUNTIME_DIR" "$ANCHOR_OWNER" "$APP_GROUP" 750
validate_optional_directory "$OUTBOX_DIR" "$APP_OWNER" "$APP_GROUP" 750
validate_optional_directory "$STATE_DIR" "$APP_OWNER" "$APP_GROUP" 750
if [ -e "$MAINTENANCE_LOCK" ] || [ -L "$MAINTENANCE_LOCK" ]; then
    validate_lock "$MAINTENANCE_LOCK"
fi
if [ -e "$OPERATION_LOCK" ] || [ -L "$OPERATION_LOCK" ]; then
    validate_lock "$OPERATION_LOCK"
fi

printf 'mode=%s\n' "$([ "$ENABLE_ONLY" -eq 1 ] && echo enable || echo install-disabled)"
printf 'app_dir=%s\n' "$APP_DIR"
printf 'runtime_dir=%s\n' "$RUNTIME_DIR"
printf 'maintenance_lock=%s\n' "$MAINTENANCE_LOCK"
printf 'operation_lock=%s\n' "$OPERATION_LOCK"
printf 'webdav_config=%s\n' "$WEBDAV_CURL_CONFIG"
printf 'discord_config=%s\n' "$DISCORD_CURL_CONFIG"
printf 'summary_config=%s\n' "$SUMMARY_CONFIG"
printf 'units=%s\n' "${UNIT_NAMES[*]}"

if [ "$DRY_RUN" -eq 1 ]; then
    if [ "$ENABLE_ONLY" -eq 1 ]; then
        for unit_name in "${UNIT_NAMES[@]}"; do
            validate_installed_unit "$unit_name"
            cmp --silent "$UNIT_SOURCE_DIR/$unit_name" "$SYSTEMD_DIR/$unit_name" \
                || die "Installed unit differs from accepted source: $unit_name"
        done
    fi
    echo "Dry run complete. No files or services were changed."
    exit 0
fi

if [ -z "$TEST_ROOT" ]; then
    [ "$(id -u)" -eq 0 ] || die "Normal installation must run as root"
fi

if [ ! -e "$MAINTENANCE_LOCK" ]; then
    install -o "$ANCHOR_OWNER" -g "$APP_GROUP" -m 0640 /dev/null "$MAINTENANCE_LOCK"
fi
exec {MAINTENANCE_LOCK_FD}<"$MAINTENANCE_LOCK"
/usr/bin/flock --exclusive --timeout 600 "$MAINTENANCE_LOCK_FD" \
    || die "Timed out waiting for maintenance lock: $MAINTENANCE_LOCK"

if [ -z "$TEST_ROOT" ]; then
    validate_accepted_checkout
    for unit_name in "${UNIT_NAMES[@]}"; do
        validate_unit_source "$unit_name"
    done
fi

if [ ! -e "$RUNTIME_DIR" ]; then
    install -d -o "$ANCHOR_OWNER" -g "$APP_GROUP" -m 0750 "$RUNTIME_DIR"
fi
if [ ! -e "$OUTBOX_DIR" ]; then
    install -d -o "$APP_OWNER" -g "$APP_GROUP" -m 0750 "$OUTBOX_DIR"
fi
if [ ! -e "$STATE_DIR" ]; then
    install -d -o "$APP_OWNER" -g "$APP_GROUP" -m 0750 "$STATE_DIR"
fi
if [ ! -e "$OPERATION_LOCK" ]; then
    install -o "$ANCHOR_OWNER" -g "$APP_GROUP" -m 0640 /dev/null "$OPERATION_LOCK"
fi
validate_directory "$RUNTIME_DIR" "$ANCHOR_OWNER" "$APP_GROUP" 750
validate_directory "$OUTBOX_DIR" "$APP_OWNER" "$APP_GROUP" 750
validate_directory "$STATE_DIR" "$APP_OWNER" "$APP_GROUP" 750
validate_lock "$MAINTENANCE_LOCK"
validate_lock "$OPERATION_LOCK"

exec {OPERATION_LOCK_FD}<"$OPERATION_LOCK"
/usr/bin/flock --exclusive --timeout 600 "$OPERATION_LOCK_FD" \
    || die "Timed out waiting for operation lock: $OPERATION_LOCK"

trap rollback_on_exit EXIT
stage_accepted_units
systemd-analyze verify "${UNIT_NAMES[@]/#/$STAGE_DIR/new/}"

if [ "$ENABLE_ONLY" -eq 1 ]; then
    TIMERS_FORCED_DISABLED=1
    for unit_name in "${UNIT_NAMES[@]}"; do
        validate_installed_unit "$unit_name"
        cmp --silent "$STAGE_DIR/new/$unit_name" "$SYSTEMD_DIR/$unit_name" \
            || die "Installed unit differs from accepted source: $unit_name"
    done
    systemd-analyze verify "${UNIT_NAMES[@]/#/$SYSTEMD_DIR/}"
    systemctl daemon-reload
    systemctl enable --now "${TIMER_NAMES[@]}"
    for timer_name in "${TIMER_NAMES[@]}"; do
        timer_is_confirmed_enabled "$timer_name" \
            || die "Could not confirm Task 25 timer is enabled: $timer_name"
    done
    TRANSACTION_COMMITTED=1
    echo "Task 25 backup and delivery timers are enabled."
    exit 0
fi

TIMERS_FORCED_DISABLED=1
disable_installed_timers

for unit_name in "${UNIT_NAMES[@]}"; do
    if [ -e "$SYSTEMD_DIR/$unit_name" ] || [ -L "$SYSTEMD_DIR/$unit_name" ]; then
        validate_installed_unit "$unit_name"
        install -o "$ANCHOR_OWNER" -g "$ANCHOR_GROUP" -m 0600 \
            "$SYSTEMD_DIR/$unit_name" "$STAGE_DIR/previous/$unit_name"
    fi
done

UNIT_MUTATION_STARTED=1
for unit_name in "${UNIT_NAMES[@]}"; do
    install -o "$ANCHOR_OWNER" -g "$ANCHOR_GROUP" -m 0644 \
        "$STAGE_DIR/new/$unit_name" "$SYSTEMD_DIR/$unit_name"
done
systemd-analyze verify "${UNIT_NAMES[@]/#/$SYSTEMD_DIR/}"
systemctl daemon-reload
disable_installed_timers
TRANSACTION_COMMITTED=1

echo "Task 25 units are installed and verified; both timers remain disabled."
echo "Complete the disposable acceptance checks, then run this script with --enable."
