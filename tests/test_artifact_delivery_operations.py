from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest


SYSTEMD_DIR = Path("deployment/systemd")
INSTALLER = Path("scripts/install_artifact_delivery.sh")
DEPLOY_SCRIPT = Path("scripts/deploy_production.sh")
RUNBOOK = Path("docs/production-artifact-delivery.md")
EXPECTED_UNITS = {
    "extrusion-terminal-backup.service",
    "extrusion-terminal-backup.timer",
    "extrusion-terminal-delivery.service",
    "extrusion-terminal-delivery.timer",
}


def read_unit(name: str) -> str:
    return (SYSTEMD_DIR / name).read_text(encoding="utf-8")


def prepare_installer_harness(tmp_path: Path) -> tuple[Path, dict[str, str], Path]:
    root = tmp_path / "root"
    base = root / "opt" / "extrusion-terminal"
    base.mkdir(parents=True)
    base.chmod(0o755)
    config_dir = root / "etc" / "extrusion-terminal"
    config_dir.mkdir(parents=True)
    webdav = config_dir / "hetzner-webdav.conf"
    webdav.write_text('user = "extrusion-backup:fake-password"\n', encoding="utf-8")
    discord = config_dir / "discord-webhook.conf"
    discord.write_text(
        'url = "https://discord.com/api/webhooks/123/fake-token?wait=true"\n',
        encoding="utf-8",
    )
    webdav.chmod(0o600)
    discord.chmod(0o600)
    (root / "etc" / "systemd" / "system").mkdir(parents=True)

    command_log = tmp_path / "system-commands.log"
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    systemd_analyze = fake_bin / "systemd-analyze"
    systemd_analyze.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'systemd-analyze %s\\n' \"$*\" >> \"$FAKE_SYSTEM_LOG\"\n"
        "[ \"${FAKE_VERIFY_FAILURE:-0}\" -eq 0 ]\n",
        encoding="utf-8",
    )
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        "#!/usr/bin/env bash\n"
        "printf 'systemctl %s\\n' \"$*\" >> \"$FAKE_SYSTEM_LOG\"\n"
        "if [ \"${1:-}\" = is-enabled ]; then "
        "if [ \"${FAKE_DISABLE_FAILURE:-0}\" -eq 1 ] "
        "|| [ -f \"${FAKE_SYSTEM_LOG}.enabled\" ]; then echo enabled; "
        "else echo disabled; fi; exit 0; fi\n"
        "if [ \"${1:-}\" = is-active ]; then "
        "if [ \"${FAKE_DISABLE_FAILURE:-0}\" -eq 1 ] "
        "|| [ -f \"${FAKE_SYSTEM_LOG}.enabled\" ]; then echo active; "
        "else echo inactive; fi; exit 0; fi\n"
        "if [ \"${FAKE_DISABLE_FAILURE:-0}\" -eq 1 ] "
        "&& [ \"${1:-}\" = disable ]; then exit 1; fi\n"
        "if [ \"${1:-}\" = disable ]; then "
        "rm -f \"${FAKE_SYSTEM_LOG}.enabled\"; fi\n"
        "if [ \"${1:-}\" = enable ]; then "
        "touch \"${FAKE_SYSTEM_LOG}.enabled\"; fi\n"
        "if [ \"${FAKE_DAEMON_RELOAD_FAILURE:-0}\" -eq 1 ] "
        "&& [ \"${1:-}\" = daemon-reload ]; then exit 1; fi\n",
        encoding="utf-8",
    )
    systemd_analyze.chmod(systemd_analyze.stat().st_mode | stat.S_IXUSR)
    systemctl.chmod(systemctl.stat().st_mode | stat.S_IXUSR)
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    environment["FAKE_SYSTEM_LOG"] = str(command_log)
    return root, environment, command_log


def run_installer(
    root: Path, environment: dict[str, str], *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "bash",
            str(INSTALLER.resolve()),
            "--test-root",
            str(root),
            *arguments,
        ],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_backup_timer_is_ten_minutes_and_persistent():
    timer = read_unit("extrusion-terminal-backup.timer")

    assert "OnCalendar=*:0/10" in timer
    assert "Persistent=true" in timer
    assert "AccuracySec=1s" in timer
    assert "Unit=extrusion-terminal-backup.service" in timer
    assert "WantedBy=timers.target" in timer


def test_delivery_timer_retries_once_per_minute():
    timer = read_unit("extrusion-terminal-delivery.timer")

    assert "OnBootSec=1min" in timer
    assert "OnUnitInactiveSec=1min" in timer
    assert "AccuracySec=10s" in timer
    assert "Unit=extrusion-terminal-delivery.service" in timer
    assert "WantedBy=timers.target" in timer


def test_services_are_one_shot_and_use_paths_outside_checkout():
    backup = read_unit("extrusion-terminal-backup.service")
    delivery = read_unit("extrusion-terminal-delivery.service")

    assert "Type=oneshot" in backup
    assert "Type=oneshot" in delivery
    assert "User=sk" in backup and "User=sk" in delivery
    assert "Group=sk" in backup and "Group=sk" in delivery
    assert "/opt/extrusion-terminal/artifact-delivery" in backup
    assert "/opt/extrusion-terminal/artifact-delivery" in delivery
    assert "flock --shared --nonblock" in backup
    assert "flock --shared --nonblock" in delivery
    assert "--conflict-exit-code 75" in backup
    assert "--conflict-exit-code 75" in delivery
    assert "SuccessExitStatus=75" in backup
    assert "SuccessExitStatus=75" in delivery
    assert "SuccessExitStatus=1" not in backup
    assert "SuccessExitStatus=1" not in delivery
    assert "TimeoutStartSec=5min" in backup
    assert "TimeoutStartSec=10min" in delivery
    assert "EnvironmentFile=" not in backup
    assert "EnvironmentFile=" not in delivery


def test_service_commands_and_runtime_environment_are_exact():
    backup = read_unit("extrusion-terminal-backup.service")
    delivery = read_unit("extrusion-terminal-delivery.service")

    assert "EXTRUSION_BACKUP_KEEP_COUNT=144" in backup
    assert "EXTRUSION_DB_PATH=/opt/extrusion-terminal/data/extrusion_terminal.sqlite3" in backup
    assert "EXTRUSION_WEBDAV_CURL_CONFIG=" not in backup
    assert (
        "/opt/extrusion-terminal/app/.venv/bin/python -m app.backup_job" in backup
    )
    assert (
        "EXTRUSION_WEBDAV_CURL_CONFIG=/etc/extrusion-terminal/hetzner-webdav.conf"
        in delivery
    )
    assert (
        "/opt/extrusion-terminal/app/.venv/bin/python -m "
        "app.artifact_delivery deliver" in delivery
    )


def test_installer_has_dry_run_before_any_mutation_and_strict_shell():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert installer.startswith("#!/usr/bin/env bash\nset -Eeuo pipefail\n")
    dry_run_exit = installer.index('if [ "$DRY_RUN" -eq 1 ]')
    first_directory_install = installer.index("install -d", dry_run_exit)
    first_systemctl = installer.index("systemctl daemon-reload", dry_run_exit)
    assert dry_run_exit < first_directory_install
    assert dry_run_exit < first_systemctl
    assert 'echo "Dry run complete. No files or services were changed."' in installer


def test_installer_preflights_secrets_without_reading_or_creating_them():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert 'PRODUCTION_CONFIG_DIR="/etc/extrusion-terminal"' in installer
    assert 'WEBDAV_CURL_CONFIG="$CONFIG_DIR/hetzner-webdav.conf"' in installer
    assert 'DISCORD_CURL_CONFIG="$CONFIG_DIR/discord-webhook.conf"' in installer
    assert "stat -c '%U'" in installer
    assert "stat -c '%G'" in installer
    assert "stat -c '%a'" in installer
    assert "group/world accessible" in installer
    assert "validate_curl_config" in installer
    assert "validate_discord_webhook_config" in installer
    assert "cat \"$WEBDAV_CURL_CONFIG\"" not in installer
    assert "cat \"$DISCORD_CURL_CONFIG\"" not in installer
    assert '> "$WEBDAV_CURL_CONFIG"' not in installer
    assert '> "$DISCORD_CURL_CONFIG"' not in installer


def test_installer_binds_privileged_unit_reads_to_the_exact_unreplaced_commit():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert "--accepted-revision is required for production" in installer
    assert "Accepted revision must be an exact lowercase 40-character commit ID" in installer
    assert "GIT_NO_REPLACE_OBJECTS=1" in installer
    assert "/usr/bin/git --no-replace-objects" in installer
    assert 'git_as_app_user -C "$REPO_DIR" show' in installer
    assert '"$SOURCE_REVISION:deployment/systemd/$unit_name"' in installer
    assert installer.count("validate_accepted_checkout") >= 3
    assert installer.index(
        '/usr/bin/flock --exclusive --timeout 600 "$MAINTENANCE_LOCK_FD"'
    ) < installer.rindex("validate_accepted_checkout")


def test_no_replace_git_view_exposes_a_replace_ref_worktree_as_dirty(tmp_path: Path):
    repository = tmp_path / "replace-ref-repository"
    repository.mkdir()

    def git(*arguments: str, protected: bool = False) -> str:
        environment = os.environ.copy()
        command = ["git"]
        if protected:
            environment["GIT_NO_REPLACE_OBJECTS"] = "1"
            command.append("--no-replace-objects")
        completed = subprocess.run(
            [*command, "-C", str(repository), *arguments],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    git("init", "--quiet")
    git("config", "user.name", "Task 25 test")
    git("config", "user.email", "task25@example.invalid")
    unit = repository / "unit.service"
    unit.write_text("accepted unit\n", encoding="utf-8")
    git("add", "unit.service")
    git("commit", "--quiet", "-m", "accepted")
    accepted_revision = git("rev-parse", "HEAD")

    unit.write_text("malicious replacement unit\n", encoding="utf-8")
    git("commit", "--quiet", "-am", "replacement")
    replacement_revision = git("rev-parse", "HEAD")
    git("replace", accepted_revision, replacement_revision)
    git("reset", "--quiet", "--hard", accepted_revision)

    assert git("rev-parse", "HEAD") == accepted_revision
    assert git("status", "--porcelain=v1") == ""
    assert git("show", f"{accepted_revision}:unit.service") == "malicious replacement unit"
    assert git("show", f"{accepted_revision}:unit.service", protected=True) == "accepted unit"
    protected_status = git("status", "--porcelain=v1", protected=True)
    assert protected_status
    assert "unit.service" in protected_status


def test_installer_creates_explicit_runtime_paths_and_nonsecret_lock():
    installer = INSTALLER.read_text(encoding="utf-8")

    assert 'PRODUCTION_BASE_DIR="/opt/extrusion-terminal"' in installer
    assert 'RUNTIME_DIR="$BASE_DIR/artifact-delivery"' in installer
    assert 'OUTBOX_DIR="$RUNTIME_DIR/outbox"' in installer
    assert 'STATE_DIR="$RUNTIME_DIR/state"' in installer
    assert 'MAINTENANCE_LOCK="$BASE_DIR/maintenance.lock"' in installer
    assert 'OPERATION_LOCK="$RUNTIME_DIR/operation.lock"' in installer
    assert 'install -d -o "$ANCHOR_OWNER" -g "$APP_GROUP" -m 0750 "$RUNTIME_DIR"' in installer
    assert 'install -d -o "$APP_OWNER" -g "$APP_GROUP" -m 0750 "$OUTBOX_DIR"' in installer
    assert 'install -o "$ANCHOR_OWNER" -g "$APP_GROUP" -m 0640 /dev/null "$OPERATION_LOCK"' in installer
    assert "Lock must have mode 640" in installer


def test_installer_allowlists_exactly_four_units_and_enables_only_timers():
    installer = INSTALLER.read_text(encoding="utf-8")
    unit_block = installer[
        installer.index("UNIT_NAMES=(") : installer.index(")", installer.index("UNIT_NAMES=("))
    ]
    found_units = set(re.findall(r"extrusion-terminal-(?:backup|delivery)\.(?:service|timer)", unit_block))
    timer_block = installer[
        installer.index("TIMER_NAMES=(") : installer.index(
            ")", installer.index("TIMER_NAMES=(")
        )
    ]
    found_timers = set(
        re.findall(r"extrusion-terminal-(?:backup|delivery)\.timer", timer_block)
    )

    assert found_units == EXPECTED_UNITS
    assert found_timers == {
        "extrusion-terminal-backup.timer",
        "extrusion-terminal-delivery.timer",
    }
    assert "systemctl daemon-reload" in installer
    assert 'systemctl enable --now "${TIMER_NAMES[@]}"' in installer


def test_deploy_serializes_installation_and_jobs_before_backup():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'MAINTENANCE_LOCK="/opt/extrusion-terminal/maintenance.lock"' in deploy
    assert 'OPERATION_LOCK="/opt/extrusion-terminal/artifact-delivery/operation.lock"' in deploy
    assert "/etc/systemd/system/extrusion-terminal-backup.service" in deploy
    assert "/etc/systemd/system/extrusion-terminal-delivery.service" in deploy
    assert 'validate_coordination_lock "$MAINTENANCE_LOCK" "Maintenance"' in deploy
    assert "Task 25 installation is incomplete" in deploy
    assert "mkdir -p /opt/extrusion-terminal/artifact-delivery" not in deploy
    assert 'exec {MAINTENANCE_LOCK_FD}<"$MAINTENANCE_LOCK"' in deploy
    maintenance_lock_command = (
        '/usr/bin/flock --exclusive --timeout "$MAINTENANCE_LOCK_WAIT_SECONDS" '
        '"$MAINTENANCE_LOCK_FD"'
    )
    assert maintenance_lock_command in deploy
    assert 'exec {OPERATION_LOCK_FD}<"$OPERATION_LOCK"' in deploy
    operation_lock_command = (
        '/usr/bin/flock --exclusive --timeout "$OPERATION_LOCK_WAIT_SECONDS" '
        '"$OPERATION_LOCK_FD"'
    )
    assert operation_lock_command in deploy
    state_decision = deploy.index("\ninspect_task25_installation\n")
    assert deploy.index(maintenance_lock_command) < state_decision
    assert deploy.index(operation_lock_command) < deploy.index(
        'log "SQLite-safe backup before code activation"'
    )


def test_failed_deploy_leaves_task25_timers_disabled():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert 'trap deployment_exit EXIT' in deploy
    assert 'systemctl_with_privilege disable --now "${TASK25_TIMER_NAMES[@]}"' in deploy
    assert "task25_timers_are_disabled" in deploy
    assert "task25_timers_are_enabled" in deploy
    assert "deployment failed; Task 25 timers remain disabled" in deploy
    assert "deployment failed and timer disablement could not be confirmed" in deploy
    assert 'systemctl_with_privilege enable --now "${PREVIOUSLY_ENABLED_TIMERS[@]}"' in deploy
    resume = deploy.index(
        'systemctl_with_privilege enable --now "${PREVIOUSLY_ENABLED_TIMERS[@]}"'
    )
    confirmation = deploy.index(
        'task25_timers_are_enabled "${PREVIOUSLY_ENABLED_TIMERS[@]}"'
    )
    clear_stopped = deploy.index("TASK25_TIMERS_STOPPED=0", resume)
    deployment_ok = deploy.index("DEPLOYMENT OK", resume)
    assert resume < confirmation < clear_stopped < deployment_ok


def test_deploy_disables_git_replacement_objects_for_revision_attestation():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")

    assert "GIT_NO_REPLACE_OBJECTS=1" in deploy
    assert "/usr/bin/git --no-replace-objects" in deploy
    assert "git_trusted status --porcelain=v1" in deploy
    assert "git_trusted fetch --prune" in deploy
    assert "git_trusted merge --ff-only" in deploy
    assert 'final_commit="$(git_trusted rev-parse HEAD)"' in deploy
    executable_lines = [
        line.strip()
        for line in deploy.splitlines()
        if re.search(r"(^|[\"$( ])git(?: |$)", line) and not line.lstrip().startswith("#")
    ]
    assert executable_lines == ["require_command git"]


def test_deploy_dry_run_reports_but_does_not_acquire_task25_lock():
    deploy = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    dry_run_block = deploy[
        deploy.index('if [ "$DRY_RUN" -eq 1 ]') : deploy.index(
            'log "preflight"', deploy.index('if [ "$DRY_RUN" -eq 1 ]')
        )
    ]

    assert "task25_coordination=" in deploy
    assert "maintenance_lock=" in deploy
    assert 'exec {MAINTENANCE_LOCK_FD}<"$MAINTENANCE_LOCK"' not in dry_run_block
    assert "/usr/bin/flock --exclusive" not in dry_run_block


def test_runbook_executes_only_a_root_staged_accepted_installer():
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "ACCEPTED_REVISION=REPLACE_WITH_EXACT_REVIEWED_COMMIT_ID" in runbook
    assert "GIT_NO_REPLACE_OBJECTS=1" in runbook
    assert "/usr/bin/git --no-replace-objects" in runbook
    assert "trusted_installer=\"$(/usr/bin/mktemp /run/" in runbook
    assert 'show "$revision:scripts/install_artifact_delivery.sh"' in runbook
    assert '/bin/chown root:root "$trusted_installer"' in runbook
    assert '/bin/chmod 0700 "$trusted_installer"' in runbook
    assert 'run_accepted_task25_installer --dry-run' in runbook
    assert 'run_accepted_task25_installer --enable' in runbook
    assert "sudo bash scripts/install_artifact_delivery.sh" not in runbook
    assert 'backup_dir = Path("/opt/extrusion-terminal/backups")' in runbook
    assert "DEFAULT_BACKUP_DIR" not in runbook
    assert "path.is_symlink() or not path.is_file()" in runbook


def test_actual_restore_holds_both_locks_before_quiescing_or_restoring():
    runbook = RUNBOOK.read_text(encoding="utf-8")
    actual_restore = runbook[runbook.index("For an actual restore") :]

    maintenance_open = actual_restore.index(
        "exec {MAINTENANCE_LOCK_FD}</opt/extrusion-terminal/maintenance.lock"
    )
    maintenance_lock = actual_restore.index(
        '/usr/bin/flock --exclusive --timeout 60 "$MAINTENANCE_LOCK_FD"'
    )
    operation_open = actual_restore.index(
        "exec {OPERATION_LOCK_FD}</opt/extrusion-terminal/artifact-delivery/operation.lock"
    )
    operation_lock = actual_restore.index(
        '/usr/bin/flock --exclusive --timeout 600 "$OPERATION_LOCK_FD"'
    )
    record_timer_state = actual_restore.index(
        "PREVIOUSLY_ENABLED_TASK25_TIMERS=()"
    )
    timer_disable = actual_restore.index("sudo systemctl disable --now")
    app_stop = actual_restore.index("sudo systemctl stop extrusion-terminal.service")
    restore = actual_restore.index("sudo -u sk .venv/bin/python -m app.backups restore")
    app_start = actual_restore.index("sudo systemctl start extrusion-terminal.service")
    operation_unlock = actual_restore.index(
        '/usr/bin/flock --unlock "$OPERATION_LOCK_FD"'
    )
    maintenance_unlock = actual_restore.index(
        '/usr/bin/flock --unlock "$MAINTENANCE_LOCK_FD"'
    )

    assert maintenance_open < maintenance_lock < operation_open < operation_lock
    assert operation_lock < record_timer_state < timer_disable
    assert timer_disable < app_stop < restore < app_start
    assert app_start < operation_unlock < maintenance_unlock


def test_installer_refuses_runtime_symlink_without_mutating_its_target(
    tmp_path: Path,
):
    root, environment, _log = prepare_installer_harness(tmp_path)
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir(mode=0o700)
    runtime = root / "opt" / "extrusion-terminal" / "artifact-delivery"
    runtime.symlink_to(sentinel, target_is_directory=True)

    result = run_installer(root, environment)

    assert result.returncode != 0
    assert "symbolic link" in result.stderr
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o700


def test_installer_keeps_timers_disabled_until_separate_enable_action(
    tmp_path: Path,
):
    root, environment, command_log = prepare_installer_harness(tmp_path)

    installed = run_installer(root, environment)

    assert installed.returncode == 0, installed.stderr
    systemd_dir = root / "etc" / "systemd" / "system"
    assert {path.name for path in systemd_dir.iterdir()} == EXPECTED_UNITS
    first_log = command_log.read_text(encoding="utf-8")
    assert "systemctl daemon-reload" in first_log
    assert "systemctl enable --now" not in first_log

    enabled = run_installer(root, environment, "--enable")

    assert enabled.returncode == 0, enabled.stderr
    final_log = command_log.read_text(encoding="utf-8")
    assert (
        "systemctl enable --now extrusion-terminal-backup.timer "
        "extrusion-terminal-delivery.timer"
    ) in final_log


def test_installer_dry_run_and_invalid_config_do_not_create_runtime(
    tmp_path: Path,
):
    root, environment, command_log = prepare_installer_harness(tmp_path)
    runtime = root / "opt" / "extrusion-terminal" / "artifact-delivery"

    dry_run = run_installer(root, environment, "--dry-run")

    assert dry_run.returncode == 0, dry_run.stderr
    assert not runtime.exists()
    assert not command_log.exists()

    discord = root / "etc" / "extrusion-terminal" / "discord-webhook.conf"
    discord.write_text('url = "https://example.com/not-discord"\n', encoding="utf-8")
    discord.chmod(0o600)

    invalid = run_installer(root, environment)

    assert invalid.returncode != 0
    assert "invalid webhook URL" in invalid.stderr
    assert not runtime.exists()
    assert not command_log.exists()


def test_installer_rerun_is_idempotent_and_still_does_not_enable_timers(
    tmp_path: Path,
):
    root, environment, command_log = prepare_installer_harness(tmp_path)

    first = run_installer(root, environment)
    second = run_installer(root, environment)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    systemd_dir = root / "etc" / "systemd" / "system"
    for unit_name in EXPECTED_UNITS:
        assert (systemd_dir / unit_name).read_bytes() == (
            SYSTEMD_DIR / unit_name
        ).read_bytes()
    assert "systemctl enable --now" not in command_log.read_text(encoding="utf-8")


def test_installer_does_not_claim_disabled_when_systemd_cannot_disable_timers(
    tmp_path: Path,
):
    root, environment, command_log = prepare_installer_harness(tmp_path)
    first = run_installer(root, environment)
    assert first.returncode == 0, first.stderr
    environment["FAKE_DISABLE_FAILURE"] = "1"

    failed = run_installer(root, environment)

    assert failed.returncode != 0
    assert "could not confirm task 25 timer is disabled" in failed.stderr.lower()
    assert "timers remain disabled" not in failed.stderr.lower()
    assert "systemctl disable --now" in command_log.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("failure_variable", "expected_log", "expects_disable"),
    [
        ("FAKE_VERIFY_FAILURE", "systemd-analyze verify", False),
        ("FAKE_DAEMON_RELOAD_FAILURE", "systemctl daemon-reload", True),
    ],
)
def test_installer_failure_preserves_previous_units_and_leaves_timers_disabled(
    tmp_path: Path,
    failure_variable: str,
    expected_log: str,
    expects_disable: bool,
):
    root, environment, command_log = prepare_installer_harness(tmp_path)
    systemd_dir = root / "etc" / "systemd" / "system"
    for unit_name in EXPECTED_UNITS:
        unit_path = systemd_dir / unit_name
        unit_path.write_text(
            f"previous {unit_name}\n", encoding="utf-8"
        )
        unit_path.chmod(0o644)
    environment[failure_variable] = "1"

    result = run_installer(root, environment)

    assert result.returncode != 0
    assert expected_log in command_log.read_text(encoding="utf-8"), result.stderr
    for unit_name in EXPECTED_UNITS:
        assert (systemd_dir / unit_name).read_text(encoding="utf-8") == (
            f"previous {unit_name}\n"
        )
    assert (
        "systemctl disable --now" in command_log.read_text(encoding="utf-8")
    ) is expects_disable
    preserved_stages = list(
        (root / "opt" / "extrusion-terminal").glob(
            ".artifact-delivery-install.*"
        )
    )
    if failure_variable == "FAKE_DAEMON_RELOAD_FAILURE":
        assert "rollback is incomplete" in result.stderr
        assert len(preserved_stages) == 1
        assert {path.name for path in (preserved_stages[0] / "previous").iterdir()} == EXPECTED_UNITS
    else:
        assert preserved_stages == []
