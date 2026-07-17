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
log_file=$LOG_FILE
EOF

if [ "$DRY_RUN" -eq 1 ]; then
    log "dry run"
    git status --short
    systemctl_read show "$SERVICE" -p ActiveState -p MainPID -p ExecMainStartTimestamp -p WorkingDirectory -p ExecStart || true
    echo "Dry run complete. No backup, Git update, dependency install, revision write, or restart was performed."
    exit 0
fi

log "preflight"
[ -f requirements.txt ] || die "requirements.txt not found in $APP_DIR"
[ -f app/main.py ] || die "app/main.py not found in $APP_DIR"
[ -f "$DB_PATH" ] || die "Production database not found: $DB_PATH"

current_branch="$(git branch --show-current)"
[ "$current_branch" = "$BRANCH" ] || die "Current branch is '$current_branch', expected '$BRANCH'."

dirty_status="$(git status --porcelain=v1 --untracked-files=normal)"
if [ -n "$dirty_status" ]; then
    printf '%s\n' "$dirty_status"
    die "Working tree is not clean. Refusing to deploy until local drift is reviewed."
fi

before_commit="$(git rev-parse HEAD)"
old_pid="$(systemctl show "$SERVICE" -p MainPID --value || true)"
old_started="$(systemctl show "$SERVICE" -p ExecMainStartTimestamp --value || true)"

echo "timestamp_before=$(date -Is)"
echo "commit_before=$before_commit"
echo "old_pid=${old_pid:-unknown}"
echo "old_started=${old_started:-unknown}"

log "fetch latest GitHub branch"
git fetch --prune "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH"
target_ref="$REMOTE/$BRANCH"
target_commit="$(git rev-parse "$target_ref^{commit}")"
echo "target_ref=$target_ref"
echo "target_commit=$target_commit"

log "SQLite-safe backup before code activation"
"$PYTHON" -m app.backups backup --source "$DB_PATH" --backup-dir "$BACKUP_DIR" --keep "$BACKUP_KEEP"

log "fast-forward checkout"
if [ "$before_commit" != "$target_commit" ]; then
    git merge --ff-only "$target_ref"
fi
after_commit="$(git rev-parse HEAD)"
[ "$after_commit" = "$target_commit" ] || die "Checkout is $after_commit, expected $target_commit."
echo "commit_after=$after_commit"

post_merge_status="$(git status --porcelain=v1 --untracked-files=normal)"
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
final_commit="$(git rev-parse HEAD)"
[ "$final_commit" = "$target_commit" ] || die "Final checkout is $final_commit, expected $target_commit."

cat <<EOF

DEPLOYMENT OK
deployed_commit=$target_commit
service=$SERVICE
pid=$new_pid
health_url=$HEALTH_URL
log_file=$LOG_FILE
timestamp_after=$(date -Is)
EOF
