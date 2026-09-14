#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${EXTRUSION_DEPLOY_APP_DIR:-/opt/extrusion-terminal/app}"
SERVICE="${EXTRUSION_DEPLOY_SERVICE:-extrusion-terminal.service}"
REMOTE="${EXTRUSION_DEPLOY_REMOTE:-origin}"
BRANCH="${EXTRUSION_DEPLOY_BRANCH:-main}"
HOST="${EXTRUSION_DEPLOY_HOST:-0.0.0.0}"
PORT="${EXTRUSION_DEPLOY_PORT:-8000}"
HEALTH_URL="${EXTRUSION_DEPLOY_HEALTH_URL:-http://127.0.0.1:8000/health}"
DB_PATH="${EXTRUSION_DB_PATH:-/opt/extrusion-terminal/data/extrusion_terminal.sqlite3}"
BACKUP_DIR="${EXTRUSION_BACKUP_DIR:-/opt/extrusion-terminal/backups}"
BACKUP_KEEP="${EXTRUSION_BACKUP_KEEP_COUNT:-144}"
MAINTENANCE_BASE="/opt/extrusion-terminal"
MAINTENANCE_LOCK="/opt/extrusion-terminal/maintenance.lock"
OPERATION_LOCK="/opt/extrusion-terminal/artifact-delivery/operation.lock"
MAINTENANCE_LOCK_WAIT_SECONDS="600"
OPERATION_LOCK_WAIT_SECONDS="600"
TASK25_BACKUP_UNIT="/etc/systemd/system/extrusion-terminal-backup.service"
TASK25_DELIVERY_UNIT="/etc/systemd/system/extrusion-terminal-delivery.service"
TASK25_BACKUP_TIMER_UNIT="/etc/systemd/system/extrusion-terminal-backup.timer"
TASK25_DELIVERY_TIMER_UNIT="/etc/systemd/system/extrusion-terminal-delivery.timer"
TASK25_UNIT_PATHS=(
    "$TASK25_BACKUP_UNIT"
    "$TASK25_BACKUP_TIMER_UNIT"
    "$TASK25_DELIVERY_UNIT"
    "$TASK25_DELIVERY_TIMER_UNIT"
)
TASK25_TIMER_NAMES=(
    extrusion-terminal-backup.timer
    extrusion-terminal-delivery.timer
)
PREVIOUSLY_ENABLED_TIMERS=()
TASK25_TIMERS_STOPPED=0

DRY_RUN=0
SKIP_TESTS=0
REQUIRE_TESTS=0

usage() {
    cat <<'EOF'
Deploy the extrusion terminal app from the latest GitHub main branch.

Default production values:
  app dir:    /opt/extrusion-terminal/app
  service:    extrusion-terminal.service
  remote:     origin
  branch:     main
  health URL: http://127.0.0.1:8000/health
  database:   /opt/extrusion-terminal/data/extrusion_terminal.sqlite3
  backups:    /opt/extrusion-terminal/backups

Usage:
  bash scripts/deploy_production.sh [options]

Options:
  --app-dir PATH       Override the app checkout path.
  --service NAME       Override the systemd service name.
  --remote NAME        Override the Git remote. Default: origin.
  --branch NAME        Override the Git branch. Default: main.
  --host HOST          Expected uvicorn bind host. Default: 0.0.0.0.
  --port PORT          Expected uvicorn/listen port. Default: 8000.
  --health-url URL     Override the local health URL.
  --db-path PATH       Override the SQLite database path for backup.
  --backup-dir PATH    Override the backup directory.
  --backup-keep N      Number of newest backup files to retain. Default: 144.
  --skip-tests         Skip pytest even if it is installed.
  --require-tests      Fail if pytest is not installed.
  --dry-run            Print the resolved configuration and planned checks only.
  -h, --help           Show this help.

Normal production command:
  cd /opt/extrusion-terminal/app
  bash scripts/deploy_production.sh

This script intentionally refuses dirty local checkouts and divergent branches.
It uses fast-forward-only Git updates by default; it does not delete local work.
EOF
}

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

git_trusted() {
    /usr/bin/env \
        -u GIT_DIR \
        -u GIT_WORK_TREE \
        -u GIT_INDEX_FILE \
        -u GIT_OBJECT_DIRECTORY \
        -u GIT_ALTERNATE_OBJECT_DIRECTORIES \
        -u GIT_COMMON_DIR \
        -u GIT_NAMESPACE \
        -u GIT_REPLACE_REF_BASE \
        -u GIT_CONFIG_GLOBAL \
        -u GIT_CONFIG_SYSTEM \
        -u GIT_CONFIG_NOSYSTEM \
        -u GIT_CONFIG_COUNT \
        -u GIT_CONFIG_PARAMETERS \
        GIT_NO_REPLACE_OBJECTS=1 \
        /usr/bin/git --no-replace-objects \
        -c safe.directory="$APP_DIR" -C "$APP_DIR" "$@"
}

systemctl_with_privilege() {
    if [ "$(id -u)" -eq 0 ]; then
        systemctl "$@"
    else
        sudo systemctl "$@"
    fi
}

systemctl_read() {
    systemctl "$@" --no-pager
}

validate_protected_directory() {
    local path="$1"
    local owner="$2"
    local group="$3"
    local mode="$4"

    [ -d "$path" ] && [ ! -L "$path" ] \
        || die "Protected directory is missing or unsafe: $path"
    [ "$(stat -c '%U' "$path")" = "$owner" ] \
        || die "Protected directory has wrong owner: $path"
    [ "$(stat -c '%G' "$path")" = "$group" ] \
        || die "Protected directory has wrong group: $path"
    [ "$(stat -c '%a' "$path")" = "$mode" ] \
        || die "Protected directory has wrong mode: $path"
}

validate_coordination_lock() {
    local path="$1"
    local label="$2"

    [ -f "$path" ] && [ ! -L "$path" ] \
        || die "$label lock is missing or unsafe: $path"
    [ "$(stat -c '%U' "$path")" = "root" ] \
        || die "$label lock must be owned by root: $path"
    [ "$(stat -c '%G' "$path")" = "sk" ] \
        || die "$label lock must have group sk: $path"
    [ "$(stat -c '%a' "$path")" = "640" ] \
        || die "$label lock must have mode 640: $path"
}

inspect_task25_installation() {
    local installed_count=0
    local unit_path

    for unit_path in "${TASK25_UNIT_PATHS[@]}"; do
        if [ -e "$unit_path" ] || [ -L "$unit_path" ]; then
            [ -f "$unit_path" ] && [ ! -L "$unit_path" ] \
                || die "Task 25 installed unit is unsafe: $unit_path"
            [ "$(stat -c '%U' "$unit_path")" = "root" ] \
                || die "Task 25 installed unit must be owned by root: $unit_path"
            [ "$(stat -c '%G' "$unit_path")" = "root" ] \
                || die "Task 25 installed unit must have group root: $unit_path"
            [ "$(stat -c '%a' "$unit_path")" = "644" ] \
                || die "Task 25 installed unit must have mode 644: $unit_path"
            installed_count=$((installed_count + 1))
        fi
    done

    if [ "$installed_count" -eq 0 ]; then
        TASK25_COORDINATION="not-installed"
    elif [ "$installed_count" -eq "${#TASK25_UNIT_PATHS[@]}" ]; then
        validate_coordination_lock "$OPERATION_LOCK" "Task 25 operation"
        TASK25_COORDINATION="installed-lock-ready"
    else
        die "Task 25 installation is incomplete ($installed_count/${#TASK25_UNIT_PATHS[@]} units)"
    fi
}

task25_timers_are_disabled() {
    local timer_name
    local enabled_state
    local active_state

    for timer_name in "${TASK25_TIMER_NAMES[@]}"; do
        enabled_state="$(systemctl is-enabled "$timer_name" 2>/dev/null || true)"
        active_state="$(systemctl is-active "$timer_name" 2>/dev/null || true)"
        [ "$enabled_state" = "disabled" ] && [ "$active_state" = "inactive" ] \
            || return 1
    done
}

task25_timers_are_enabled() {
    local timer_name
    local enabled_state
    local active_state

    for timer_name in "$@"; do
        enabled_state="$(systemctl is-enabled "$timer_name" 2>/dev/null || true)"
        active_state="$(systemctl is-active "$timer_name" 2>/dev/null || true)"
        [ "$enabled_state" = "enabled" ] && [ "$active_state" = "active" ] \
            || return 1
    done
}

task25_units_match_checkout() {
    local unit_path
    local source_path

    for unit_path in "${TASK25_UNIT_PATHS[@]}"; do
        source_path="$APP_DIR/deployment/systemd/${unit_path##*/}"
        [ -f "$source_path" ] && [ ! -L "$source_path" ] || return 1
        cmp --silent "$source_path" "$unit_path" || return 1
    done
}

deployment_exit() {
    local status=$?
    trap - EXIT
    if [ "$status" -ne 0 ] && [ "$TASK25_TIMERS_STOPPED" -eq 1 ]; then
        set +e
        if systemctl_with_privilege disable --now "${TASK25_TIMER_NAMES[@]}" \
            >/dev/null 2>&1 && task25_timers_are_disabled; then
            printf '\nERROR: deployment failed; Task 25 timers remain disabled.\n' >&2
            printf 'Complete a successful deployment before re-enabling them.\n' >&2
        else
            printf '\nERROR: deployment failed and timer disablement could not be confirmed.\n' >&2
            printf 'Treat both Task 25 schedules as unsafe and intervene immediately.\n' >&2
        fi
    fi
    exit "$status"
}

json_field() {
    local field="$1"
    "$PYTHON" -c 'import json, sys
field = sys.argv[1]
data = json.load(sys.stdin)
value = data.get(field)
print("" if value is None else value)
' "$field"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --app-dir)
            [ "$#" -ge 2 ] || die "--app-dir requires a path"
            APP_DIR="$2"
            shift 2
            ;;
        --service)
            [ "$#" -ge 2 ] || die "--service requires a name"
            SERVICE="$2"
            shift 2
            ;;
        --remote)
            [ "$#" -ge 2 ] || die "--remote requires a name"
            REMOTE="$2"
            shift 2
            ;;
        --branch)
            [ "$#" -ge 2 ] || die "--branch requires a name"
            BRANCH="$2"
            shift 2
            ;;
        --host)
            [ "$#" -ge 2 ] || die "--host requires a value"
            HOST="$2"
            shift 2
            ;;
        --port)
            [ "$#" -ge 2 ] || die "--port requires a value"
            PORT="$2"
            shift 2
            ;;
        --health-url)
            [ "$#" -ge 2 ] || die "--health-url requires a URL"
            HEALTH_URL="$2"
            shift 2
            ;;
        --db-path)
            [ "$#" -ge 2 ] || die "--db-path requires a path"
            DB_PATH="$2"
            shift 2
            ;;
        --backup-dir)
            [ "$#" -ge 2 ] || die "--backup-dir requires a path"
            BACKUP_DIR="$2"
            shift 2
            ;;
        --backup-keep)
            [ "$#" -ge 2 ] || die "--backup-keep requires a number"
            BACKUP_KEEP="$2"
            shift 2
            ;;
        --skip-tests)
            SKIP_TESTS=1
            shift
            ;;
        --require-tests)
            REQUIRE_TESTS=1
            shift
            ;;
        --dry-run)
            DRY_RUN=1
            shift
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

require_command git
require_command curl
require_command systemctl
require_command ss
require_command stat
require_command cmp
require_command systemd-analyze
[ -x /usr/bin/flock ] || die "Required command not found: /usr/bin/flock"

[ -d "$APP_DIR" ] || die "App directory does not exist: $APP_DIR"
APP_DIR="$(cd "$APP_DIR" && pwd -P)"
cd "$APP_DIR"

PYTHON="$APP_DIR/.venv/bin/python"
[ -x "$PYTHON" ] || die "Project Python not found or not executable: $PYTHON"

DEPLOY_DIR="$APP_DIR/.deploy"
LOG_DIR="$DEPLOY_DIR/logs"
REVISION_FILE="$DEPLOY_DIR/current_revision"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/deploy_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG_FILE") 2>&1

TASK25_COORDINATION="not-inspected"
if [ -e "$TASK25_BACKUP_UNIT" ] || [ -e "$TASK25_DELIVERY_UNIT" ]; then
    TASK25_COORDINATION="installed-unverified"
fi

log "configuration"
cat <<EOF
app_dir=$APP_DIR
service=$SERVICE
remote=$REMOTE
branch=$BRANCH
host=$HOST
port=$PORT
health_url=$HEALTH_URL
db_path=$DB_PATH
backup_dir=$BACKUP_DIR
backup_keep=$BACKUP_KEEP
task25_coordination=$TASK25_COORDINATION
maintenance_lock=$MAINTENANCE_LOCK
operation_lock=$OPERATION_LOCK
log_file=$LOG_FILE
EOF

if [ "$DRY_RUN" -eq 1 ]; then
    log "dry run"
    git_trusted status --short
    systemctl_read show "$SERVICE" -p ActiveState -p MainPID -p ExecMainStartTimestamp -p WorkingDirectory -p ExecStart || true
    echo "Dry run complete. No backup, Git update, dependency install, revision write, or restart was performed."
    exit 0
fi

log "preflight"
[ -f requirements.txt ] || die "requirements.txt not found in $APP_DIR"
[ -f app/main.py ] || die "app/main.py not found in $APP_DIR"
[ -f "$DB_PATH" ] || die "Production database not found: $DB_PATH"
validate_protected_directory "$MAINTENANCE_BASE" root root 755
validate_coordination_lock "$MAINTENANCE_LOCK" "Maintenance"

log "acquire exclusive maintenance lock"
exec {MAINTENANCE_LOCK_FD}<"$MAINTENANCE_LOCK"
/usr/bin/flock --exclusive --timeout "$MAINTENANCE_LOCK_WAIT_SECONDS" "$MAINTENANCE_LOCK_FD" \
    || die "Timed out waiting for maintenance lock: $MAINTENANCE_LOCK"

inspect_task25_installation
echo "task25_coordination_locked=$TASK25_COORDINATION"

current_branch="$(git_trusted branch --show-current)"
[ "$current_branch" = "$BRANCH" ] || die "Current branch is '$current_branch', expected '$BRANCH'."

dirty_status="$(git_trusted status --porcelain=v1 --untracked-files=normal)"
if [ -n "$dirty_status" ]; then
    printf '%s\n' "$dirty_status"
    die "Working tree is not clean. Refusing to deploy until local drift is reviewed."
fi

before_commit="$(git_trusted rev-parse HEAD)"
old_pid="$(systemctl show "$SERVICE" -p MainPID --value || true)"
old_started="$(systemctl show "$SERVICE" -p ExecMainStartTimestamp --value || true)"

echo "timestamp_before=$(date -Is)"
echo "commit_before=$before_commit"
echo "old_pid=${old_pid:-unknown}"
echo "old_started=${old_started:-unknown}"

if [ "$TASK25_COORDINATION" = "installed-lock-ready" ]; then
    log "acquire exclusive Task 25 operation lock"
    exec {OPERATION_LOCK_FD}<"$OPERATION_LOCK"
    /usr/bin/flock --exclusive --timeout "$OPERATION_LOCK_WAIT_SECONDS" "$OPERATION_LOCK_FD" \
        || die "Timed out waiting for Task 25 operation lock: $OPERATION_LOCK"

    for timer_name in "${TASK25_TIMER_NAMES[@]}"; do
        if [ "$(systemctl is-enabled "$timer_name" 2>/dev/null || true)" = "enabled" ]; then
            PREVIOUSLY_ENABLED_TIMERS+=("$timer_name")
        fi
    done
    trap deployment_exit EXIT
    TASK25_TIMERS_STOPPED=1
    systemctl_with_privilege disable --now "${TASK25_TIMER_NAMES[@]}"
    task25_timers_are_disabled \
        || die "Could not confirm both Task 25 timers are disabled"
fi

log "fetch latest GitHub branch"
git_trusted fetch --prune "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH"
target_ref="$REMOTE/$BRANCH"
target_commit="$(git_trusted rev-parse "$target_ref^{commit}")"
echo "target_ref=$target_ref"
echo "target_commit=$target_commit"

log "SQLite-safe backup before code activation"
"$PYTHON" -m app.backups backup --source "$DB_PATH" --backup-dir "$BACKUP_DIR" --keep "$BACKUP_KEEP"

log "fast-forward checkout"
if [ "$before_commit" != "$target_commit" ]; then
    git_trusted merge --ff-only "$target_ref"
fi
after_commit="$(git_trusted rev-parse HEAD)"
[ "$after_commit" = "$target_commit" ] || die "Checkout is $after_commit, expected $target_commit."
echo "commit_after=$after_commit"

post_merge_status="$(git_trusted status --porcelain=v1 --untracked-files=normal)"
if [ -n "$post_merge_status" ]; then
    printf '%s\n' "$post_merge_status"
    die "Working tree became dirty after update. Refusing to restart production."
fi

log "install runtime dependencies"
"$PYTHON" -m pip install -r requirements.txt

log "syntax/import checks"
"$PYTHON" -m compileall -q app
"$PYTHON" - <<'PY'
import app.main
print("Imported app.main successfully")
PY

if [ "$SKIP_TESTS" -eq 1 ]; then
    log "tests skipped by option"
elif "$PYTHON" -m pytest --version >/dev/null 2>&1; then
    log "run pytest"
    "$PYTHON" -m pytest
elif [ "$REQUIRE_TESTS" -eq 1 ]; then
    die "pytest is not installed in this virtualenv and --require-tests was provided."
else
    log "pytest not installed; continuing after syntax/import checks"
fi

log "write deployed revision marker"
mkdir -p "$DEPLOY_DIR"
printf '%s\n' "$target_commit" > "$REVISION_FILE"

log "restart service"
systemctl_with_privilege restart "$SERVICE"

log "wait for active service"
new_pid=""
new_started=""
for _ in $(seq 1 30); do
    active_state="$(systemctl show "$SERVICE" -p ActiveState --value || true)"
    new_pid="$(systemctl show "$SERVICE" -p MainPID --value || true)"
    new_started="$(systemctl show "$SERVICE" -p ExecMainStartTimestamp --value || true)"
    if [ "$active_state" = "active" ] && [ -n "$new_pid" ] && [ "$new_pid" != "0" ]; then
        break
    fi
    sleep 1
done

[ "${active_state:-}" = "active" ] || die "$SERVICE did not become active."
[ -n "$new_pid" ] && [ "$new_pid" != "0" ] || die "$SERVICE has no running MainPID."
if [ -n "${old_pid:-}" ] && [ "$old_pid" != "0" ] && [ "$new_pid" = "$old_pid" ]; then
    die "$SERVICE MainPID did not change after restart."
fi

echo "new_pid=$new_pid"
echo "new_started=$new_started"
systemctl_read --full status "$SERVICE"

log "verify process identity"
process_cwd="$(readlink "/proc/$new_pid/cwd")"
process_cmd="$(tr '\0' ' ' < "/proc/$new_pid/cmdline" | sed 's/[[:space:]]*$//')"
expected_cmd="$PYTHON -m uvicorn app.main:app --host $HOST --port $PORT"

echo "process_cwd=$process_cwd"
echo "process_cmd=$process_cmd"
echo "expected_cmd=$expected_cmd"

[ "$process_cwd" = "$APP_DIR" ] || die "Process cwd is $process_cwd, expected $APP_DIR."
[ "$process_cmd" = "$expected_cmd" ] || die "Process command does not match expected uvicorn command."

log "verify port owner"
port_output=""
for _ in $(seq 1 30); do
    port_output="$(ss -ltnp "sport = :$PORT" || true)"
    if printf '%s\n' "$port_output" | grep -F "pid=$new_pid," >/dev/null; then
        break
    fi
    active_state="$(systemctl show "$SERVICE" -p ActiveState --value || true)"
    current_pid="$(systemctl show "$SERVICE" -p MainPID --value || true)"
    if [ "$active_state" != "active" ] || [ "$current_pid" != "$new_pid" ]; then
        systemctl_read --full status "$SERVICE" || true
        die "$SERVICE changed state before port $PORT was owned by PID $new_pid."
    fi
    sleep 1
done
printf '%s\n' "$port_output"
printf '%s\n' "$port_output" | grep -F "pid=$new_pid," >/dev/null \
    || die "Port $PORT was not owned by service PID $new_pid within 30 seconds."

log "verify health"
health_json=""
for _ in $(seq 1 30); do
    if health_json="$(curl --fail --silent --show-error "$HEALTH_URL")"; then
        break
    fi
    sleep 1
done
[ -n "$health_json" ] || die "Health endpoint did not respond: $HEALTH_URL"
printf '%s\n' "$health_json"

health_status="$(printf '%s\n' "$health_json" | json_field status)"
health_revision="$(printf '%s\n' "$health_json" | json_field app_revision)"
[ "$health_status" = "ok" ] || die "Health status is '$health_status', expected 'ok'."
[ "$health_revision" = "$target_commit" ] || die "Health revision is '$health_revision', expected '$target_commit'."

log "verify checkout remains exact target"
final_commit="$(git_trusted rev-parse HEAD)"
[ "$final_commit" = "$target_commit" ] || die "Final checkout is $final_commit, expected $target_commit."

if [ "$TASK25_COORDINATION" = "installed-lock-ready" ]; then
    task25_units_match_checkout \
        || die "Installed Task 25 units differ from the deployed checkout; run the guarded installer and re-verify before enablement"
    systemd-analyze verify "${TASK25_UNIT_PATHS[@]}"
fi

if [ "$TASK25_TIMERS_STOPPED" -eq 1 ]; then
    log "restore previously enabled Task 25 timers"
    if [ "${#PREVIOUSLY_ENABLED_TIMERS[@]}" -gt 0 ]; then
        systemctl_with_privilege enable --now "${PREVIOUSLY_ENABLED_TIMERS[@]}"
        task25_timers_are_enabled "${PREVIOUSLY_ENABLED_TIMERS[@]}" \
            || die "Could not confirm previously enabled Task 25 timers resumed"
    else
        echo "Task 25 timers were disabled before deployment and remain disabled."
    fi
    TASK25_TIMERS_STOPPED=0
fi

cat <<EOF

DEPLOYMENT OK
deployed_commit=$target_commit
service=$SERVICE
pid=$new_pid
health_url=$HEALTH_URL
log_file=$LOG_FILE
timestamp_after=$(date -Is)
EOF
