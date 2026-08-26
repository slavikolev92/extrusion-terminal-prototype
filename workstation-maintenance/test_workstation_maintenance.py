from __future__ import annotations

import os
import pwd
import shutil
import signal
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


def process_start_time(pid: int) -> int:
    stat_source = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    fields_after_command = stat_source[stat_source.rfind(")") + 2 :].split()
    return int(fields_after_command[19])


def write_browser_pid_record(
    path: Path,
    process: subprocess.Popen[bytes],
    browser: str,
    *,
    start_time: int | None = None,
) -> None:
    recorded_start = process_start_time(process.pid) if start_time is None else start_time
    path.write_text(
        f"PID={process.pid}\nSTART_TIME={recorded_start}\nBROWSER={browser}\n",
        encoding="utf-8",
    )


def controller_environment(tmp_path: Path) -> tuple[dict[str, str], dict[str, Path]]:
    share = tmp_path / "share"
    state = tmp_path / "state"
    runtime = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    share.mkdir()
    state.mkdir()
    runtime.mkdir()
    bin_dir.mkdir()

    page = share / "maintenance.html"
    gears = share / "gears.png"
    xauthority = runtime / "Xauthority"
    session_env = runtime / "extrusion-kiosk-session.env"
    browser_pid_file = runtime / "extrusion-kiosk-browser.pid"
    runuser_log = tmp_path / "runuser.log"
    pkill_log = tmp_path / "pkill.log"
    page.write_text("maintenance page", encoding="utf-8")
    gears.write_bytes(b"gears")
    xauthority.write_text("xauthority", encoding="utf-8")
    session_env.write_text(
        f"DISPLAY=:7\nXAUTHORITY={xauthority}\n",
        encoding="utf-8",
    )
    write_executable(
        bin_dir / "runuser",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$EXTRUSION_TEST_RUNUSER_LOG\"\n",
    )
    write_executable(
        bin_dir / "pkill",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$EXTRUSION_TEST_PKILL_LOG\"\n",
    )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "EXTRUSION_KIOSK_USER": "kiosk",
            "EXTRUSION_KIOSK_SHARE_DIR": str(share),
            "EXTRUSION_KIOSK_STATE_DIR": str(state),
            "EXTRUSION_KIOSK_SESSION_ENV_FILE": str(session_env),
            "EXTRUSION_KIOSK_BROWSER_PID_FILE": str(browser_pid_file),
            "EXTRUSION_TEST_RUNUSER_LOG": str(runuser_log),
            "EXTRUSION_TEST_PKILL_LOG": str(pkill_log),
        }
    )
    return env, {
        "share": share,
        "state": state,
        "runtime": runtime,
        "bin": bin_dir,
        "page": page,
        "gears": gears,
        "xauthority": xauthority,
        "session_env": session_env,
        "browser_pid_file": browser_pid_file,
        "runuser_log": runuser_log,
        "pkill_log": pkill_log,
    }


@pytest.mark.parametrize("minutes", ["", "0", "-1", "1.5", "abc", " 30"])
def test_notify_rejects_non_positive_or_non_integer_minutes(tmp_path, minutes):
    env, paths = controller_environment(tmp_path)
    args = ("notify",) if minutes == "" else ("notify", minutes)
    result = run_script(CONTROLLER, *args, env=env)
    assert result.returncode != 0
    assert not paths["runuser_log"].exists()
    assert not (paths["state"] / "maintenance-enabled").exists()


def test_notify_uses_recorded_session_gears_one_ok_button_and_plural_copy(tmp_path):
    env, paths = controller_environment(tmp_path)

    result = run_script(CONTROLLER, "notify", "30", env=env)

    assert result.returncode == 0
    assert paths["runuser_log"].read_text(encoding="utf-8").splitlines() == [
        "-u",
        "kiosk",
        "--",
        "env",
        "DISPLAY=:7",
        f"XAUTHORITY={paths['xauthority']}",
        "yad",
        "--title=Предстояща техническа поддръжка",
        f"--image={paths['share'] / 'gears.png'}",
        "--image-on-top",
        "--text=След приблизително 30 минути терминалът ще бъде временно недостъпен поради техническа поддръжка. Моля, планирайте текущата работа.",
        "--text-align=center",
        "--button=OK:0",
        "--buttons-layout=center",
        "--center",
        "--on-top",
        "--no-escape",
        "--fixed",
        "--width=640",
    ]
    assert not (paths["state"] / "maintenance-enabled").exists()


def test_notify_uses_singular_bulgarian_minute_for_one(tmp_path):
    env, paths = controller_environment(tmp_path)

    result = run_script(CONTROLLER, "notify", "1", env=env)

    assert result.returncode == 0
    assert "--text=След приблизително 1 минута терминалът ще бъде временно недостъпен поради техническа поддръжка. Моля, планирайте текущата работа." in paths[
        "runuser_log"
    ].read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("marker_contents", [None, b"preserve this marker\x00\n"])
@pytest.mark.parametrize("image_problem", ["missing", "unreadable"])
def test_notify_rejects_unusable_image_before_session_or_process_side_effects(
    tmp_path, marker_contents, image_problem
):
    env, paths = controller_environment(tmp_path)
    marker = paths["state"] / "maintenance-enabled"
    if marker_contents is not None:
        marker.write_bytes(marker_contents)
    if image_problem == "missing":
        paths["gears"].unlink()
    else:
        paths["gears"].chmod(0o000)
    paths["session_env"].write_text("unexpected=session value\n", encoding="utf-8")

    result = run_script(CONTROLLER, "notify", "30", env=env)

    assert result.returncode != 0
    assert "maintenance image" in result.stderr
    assert not paths["runuser_log"].exists()
    assert not paths["pkill_log"].exists()
    if marker_contents is None:
        assert not marker.exists()
    else:
        assert marker.read_bytes() == marker_contents


def test_notify_rejects_nonregular_image_before_session_or_process_side_effects(tmp_path):
    env, paths = controller_environment(tmp_path)
    paths["gears"].unlink()
    paths["gears"].mkdir()
    paths["session_env"].write_text("unexpected=session value\n", encoding="utf-8")

    result = run_script(CONTROLLER, "notify", "30", env=env)

    assert result.returncode != 0
    assert "maintenance image" in result.stderr
    assert not paths["runuser_log"].exists()
    assert not paths["pkill_log"].exists()
    assert not (paths["state"] / "maintenance-enabled").exists()


def test_notify_propagates_dialog_failure_without_changing_mode(tmp_path):
    env, paths = controller_environment(tmp_path)
    marker = paths["state"] / "maintenance-enabled"
    marker.write_text("", encoding="utf-8")
    write_executable(
        paths["bin"] / "runuser",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$EXTRUSION_TEST_RUNUSER_LOG\"\nexit 73\n",
    )

    result = run_script(CONTROLLER, "notify", "30", env=env)

    assert result.returncode == 73
    assert marker.exists()


@pytest.mark.parametrize(
    "session_contents",
    [
        "",
        "DISPLAY=:7\n",
        "XAUTHORITY=/tmp/Xauthority\n",
        "DISPLAY=:7\nXAUTHORITY=/tmp/Xauthority\nUNEXPECTED=value\n",
        "DISPLAY=:7\nDISPLAY=:8\nXAUTHORITY=/tmp/Xauthority\n",
        "DISPLAY=\nXAUTHORITY=/tmp/Xauthority\n",
        "DISPLAY=:7\nXAUTHORITY=relative/Xauthority\n",
    ],
)
def test_notify_rejects_missing_unknown_duplicate_blank_or_relative_session_values(
    tmp_path, session_contents
):
    env, paths = controller_environment(tmp_path)
    paths["session_env"].write_text(session_contents, encoding="utf-8")

    result = run_script(CONTROLLER, "notify", "30", env=env)

    assert result.returncode != 0
    assert not paths["runuser_log"].exists()
    assert not (paths["state"] / "maintenance-enabled").exists()


@pytest.mark.parametrize("asset", ["page", "gears"])
def test_on_validates_assets_before_creating_marker(tmp_path, asset):
    env, paths = controller_environment(tmp_path)
    paths[asset].unlink()

    result = run_script(CONTROLLER, "on", env=env)

    assert result.returncode != 0
    assert not (paths["state"] / "maintenance-enabled").exists()
    assert not paths["pkill_log"].exists()


@pytest.mark.parametrize("asset", ["page", "gears"])
def test_on_rejects_nonregular_maintenance_assets_before_creating_marker(tmp_path, asset):
    """Directories are readable but cannot be displayed as maintenance assets."""
    env, paths = controller_environment(tmp_path)
    paths[asset].unlink()
    paths[asset].mkdir()

    result = run_script(CONTROLLER, "on", env=env)

    assert result.returncode != 0
    assert "regular" in result.stderr
    assert not (paths["state"] / "maintenance-enabled").exists()
    assert not paths["pkill_log"].exists()


def test_on_creates_marker_when_launcher_has_no_active_browser(tmp_path):
    env, paths = controller_environment(tmp_path)

    result = run_script(CONTROLLER, "on", env=env)

    assert result.returncode == 0
    assert (paths["state"] / "maintenance-enabled").exists()
    assert not paths["pkill_log"].exists()


@pytest.mark.parametrize("browser_name", ["chromium", "chromium-browser", "google-chrome"])
@pytest.mark.parametrize("command", ["on", "off"])
def test_maintenance_mode_change_terminates_real_supported_browser_from_pid_record(
    tmp_path, command, browser_name
):
    env, paths = controller_environment(tmp_path)
    marker = paths["state"] / "maintenance-enabled"
    if command == "off":
        marker.write_text("", encoding="utf-8")
    browser = paths["bin"] / browser_name
    shutil.copy2("/bin/sleep", browser)
    process = subprocess.Popen([str(browser), "30"])
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        write_browser_pid_record(paths["browser_pid_file"], process, browser_name)

        result = run_script(CONTROLLER, command, env=env)

        assert result.returncode == 0, result.stderr
        try:
            returncode = process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pytest.fail(f"controller left the recorded {browser_name} process running")
        assert returncode == -signal.SIGTERM
        assert marker.exists() is (command == "on")
        assert not paths["pkill_log"].exists()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=1)


def test_stale_browser_pid_record_cannot_terminate_reused_unrelated_process(tmp_path):
    env, paths = controller_environment(tmp_path)
    process = subprocess.Popen(["/bin/sleep", "30"])
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        write_browser_pid_record(
            paths["browser_pid_file"],
            process,
            "chromium-browser",
            start_time=process_start_time(process.pid) + 1,
        )

        result = run_script(CONTROLLER, "on", env=env)

        assert result.returncode == 0, result.stderr
        assert process.poll() is None
        assert not paths["pkill_log"].exists()
    finally:
        process.terminate()
        process.wait(timeout=1)


def test_browser_pid_record_rejects_unrelated_process_identity(tmp_path):
    env, paths = controller_environment(tmp_path)
    process = subprocess.Popen(["/bin/sleep", "30"])
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        write_browser_pid_record(paths["browser_pid_file"], process, "chromium-browser")

        result = run_script(CONTROLLER, "on", env=env)

        assert result.returncode != 0
        assert "identity" in result.stderr
        assert process.poll() is None
        assert not paths["pkill_log"].exists()
    finally:
        process.terminate()
        process.wait(timeout=1)


def test_browser_pid_record_rejects_supported_argv_with_unrelated_executable(tmp_path):
    env, paths = controller_environment(tmp_path)
    process = subprocess.Popen(
        ["chromium-browser", "30"],
        executable="/bin/sleep",
    )
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        write_browser_pid_record(paths["browser_pid_file"], process, "chromium-browser")

        result = run_script(CONTROLLER, "on", env=env)

        assert result.returncode != 0
        assert "identity" in result.stderr
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=1)


def test_browser_pid_record_rejects_unrelated_argv_with_supported_executable(tmp_path):
    env, paths = controller_environment(tmp_path)
    browser = paths["bin"] / "chromium-browser"
    shutil.copy2("/bin/sleep", browser)
    process = subprocess.Popen(
        ["unrelated-process", "30"],
        executable=str(browser),
    )
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        write_browser_pid_record(paths["browser_pid_file"], process, "chromium-browser")

        result = run_script(CONTROLLER, "on", env=env)

        assert result.returncode != 0
        assert "identity" in result.stderr
        assert process.poll() is None
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=1)


@pytest.mark.parametrize("command", ["on", "off"])
def test_mode_change_propagates_real_browser_termination_error_after_marker_change(
    tmp_path, command
):
    env, paths = controller_environment(tmp_path)
    marker = paths["state"] / "maintenance-enabled"
    if command == "off":
        marker.write_text("", encoding="utf-8")
    browser = paths["bin"] / "chromium"
    shutil.copy2("/bin/sleep", browser)
    process = subprocess.Popen([str(browser), "30"])
    kill_log = tmp_path / "kill.log"
    write_executable(
        paths["bin"] / "kill-browser",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$EXTRUSION_TEST_KILL_LOG\"\nexit 23\n",
    )
    try:
        env["EXTRUSION_KIOSK_USER"] = pwd.getpwuid(os.getuid()).pw_name
        env["EXTRUSION_KIOSK_KILL"] = str(paths["bin"] / "kill-browser")
        env["EXTRUSION_TEST_KILL_LOG"] = str(kill_log)
        write_browser_pid_record(paths["browser_pid_file"], process, "chromium")

        result = run_script(CONTROLLER, command, env=env)

        assert result.returncode == 23
        assert marker.exists() is (command == "on")
        assert process.poll() is None
        assert kill_log.read_text(encoding="utf-8").splitlines() == [
            "-TERM",
            "--",
            str(process.pid),
        ]
    finally:
        process.terminate()
        process.wait(timeout=1)


def test_on_is_idempotent(tmp_path):
    env, paths = controller_environment(tmp_path)

    first = run_script(CONTROLLER, "on", env=env)
    second = run_script(CONTROLLER, "on", env=env)

    assert first.returncode == 0
    assert second.returncode == 0
    assert (paths["state"] / "maintenance-enabled").exists()
    assert not paths["pkill_log"].exists()


def test_on_accepts_an_absent_browser_process(tmp_path):
    env, paths = controller_environment(tmp_path)

    result = run_script(CONTROLLER, "on", env=env)

    assert result.returncode == 0
    assert (paths["state"] / "maintenance-enabled").exists()


def test_off_removes_marker_without_an_active_browser_and_is_idempotent(tmp_path):
    env, paths = controller_environment(tmp_path)
    marker = paths["state"] / "maintenance-enabled"
    marker.write_text("", encoding="utf-8")

    first = run_script(CONTROLLER, "off", env=env)
    second = run_script(CONTROLLER, "off", env=env)

    assert first.returncode == 0
    assert second.returncode == 0
    assert not marker.exists()
    assert not paths["pkill_log"].exists()


def test_status_reports_terminal_or_maintenance(tmp_path):
    env, paths = controller_environment(tmp_path)

    terminal = run_script(CONTROLLER, "status", env=env)
    (paths["state"] / "maintenance-enabled").write_text("", encoding="utf-8")
    maintenance = run_script(CONTROLLER, "status", env=env)

    assert terminal.returncode == 0
    assert terminal.stdout == "mode=terminal\n"
    assert maintenance.returncode == 0
    assert maintenance.stdout == "mode=maintenance\n"


def test_unknown_command_prints_usage_and_fails(tmp_path):
    env, _ = controller_environment(tmp_path)

    result = run_script(CONTROLLER, "unknown", env=env)

    assert result.returncode != 0
    assert "Usage:" in result.stderr


def launcher_environment(
    tmp_path: Path, maintenance_enabled: bool = False
) -> tuple[dict[str, str], dict[str, Path]]:
    """Create an isolated desktop command environment for the kiosk launcher."""
    bin_dir = tmp_path / "bin"
    runtime = tmp_path / "runtime"
    profile = tmp_path / "profile"
    url_file = tmp_path / "extrusion-kiosk-url"
    marker = tmp_path / "maintenance-enabled"
    maintenance_page = tmp_path / "maintenance.html"
    xauthority = tmp_path / "Xauthority"
    chromium_log = tmp_path / "chromium.log"
    desktop_log = tmp_path / "desktop.log"
    bin_dir.mkdir()
    runtime.mkdir()
    url_file.write_text("http://192.168.1.83:8000/terminal\n", encoding="utf-8")
    maintenance_page.write_text("maintenance page", encoding="utf-8")
    xauthority.write_text("xauthority", encoding="utf-8")
    if maintenance_enabled:
        marker.write_text("", encoding="utf-8")

    write_executable(
        bin_dir / "chromium",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$EXTRUSION_TEST_CHROMIUM_LOG\"\n",
    )
    for command in ("xfwm4", "unclutter", "xset"):
        write_executable(
            bin_dir / command,
            """#!/bin/sh
printf '%s|%s|XDG_CURRENT_DESKTOP=%s|DESKTOP_SESSION=%s\\n' "${0##*/}" "$*" "${XDG_CURRENT_DESKTOP:-}" "${DESKTOP_SESSION:-}" >> "$EXTRUSION_TEST_DESKTOP_LOG"
""",
        )

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
            "EXTRUSION_KIOSK_RUN_ONCE": "1",
            "EXTRUSION_KIOSK_URL_FILE": str(url_file),
            "EXTRUSION_KIOSK_MAINTENANCE_MARKER": str(marker),
            "EXTRUSION_KIOSK_MAINTENANCE_PAGE": str(maintenance_page),
            "EXTRUSION_KIOSK_PROFILE_DIR": str(profile),
            "EXTRUSION_KIOSK_RUNTIME_DIR": str(runtime),
            "EXTRUSION_TEST_CHROMIUM_LOG": str(chromium_log),
            "EXTRUSION_TEST_DESKTOP_LOG": str(desktop_log),
            "DISPLAY": ":7",
            "XAUTHORITY": str(xauthority),
        }
    )
    return env, {
        "bin": bin_dir,
        "runtime": runtime,
        "profile": profile,
        "url_file": url_file,
        "marker": marker,
        "maintenance_page": maintenance_page,
        "xauthority": xauthority,
        "chromium_log": chromium_log,
        "desktop_log": desktop_log,
    }


def chromium_arguments(paths: dict[str, Path]) -> list[str]:
    return paths["chromium_log"].read_text(encoding="utf-8").splitlines()


def test_launcher_selects_configured_terminal_url_without_marker(tmp_path):
    env, paths = launcher_environment(tmp_path)

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    arguments = chromium_arguments(paths)
    assert "http://192.168.1.83:8000/terminal" in arguments
    assert not any(argument.startswith("file://") for argument in arguments)


def test_launcher_selects_local_file_url_with_marker(tmp_path):
    env, paths = launcher_environment(tmp_path, maintenance_enabled=True)

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    arguments = chromium_arguments(paths)
    assert f"file://{paths['maintenance_page']}" in arguments
    assert "http://192.168.1.83:8000/terminal" not in arguments


def test_launcher_clears_only_dedicated_http_cache(tmp_path):
    env, paths = launcher_environment(tmp_path)
    cache = paths["runtime"] / "extrusion-chromium-http-cache"
    cache.mkdir()
    (cache / "stale-entry").write_text("stale", encoding="utf-8")
    (paths["runtime"] / "must-survive").write_text("runtime", encoding="utf-8")
    paths["profile"].mkdir()
    (paths["profile"] / "must-survive").write_text("profile", encoding="utf-8")

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    assert not (cache / "stale-entry").exists()
    assert (paths["runtime"] / "must-survive").exists()
    assert (paths["profile"] / "must-survive").exists()
    assert f"--disk-cache-dir={cache}" in chromium_arguments(paths)


def test_launcher_preserves_profile_and_neighboring_runtime_files(tmp_path):
    env, paths = launcher_environment(tmp_path)
    (paths["runtime"] / "neighbor").write_text("keep", encoding="utf-8")
    paths["profile"].mkdir()
    (paths["profile"] / "preferences").write_text("keep", encoding="utf-8")

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    assert (paths["runtime"] / "neighbor").read_text(encoding="utf-8") == "keep"
    assert (paths["profile"] / "preferences").read_text(encoding="utf-8") == "keep"


def test_launcher_writes_only_display_and_xauthority_atomically_with_mode_0600(tmp_path):
    env, paths = launcher_environment(tmp_path)
    session_env = paths["runtime"] / "extrusion-kiosk-session.env"
    session_env.write_text("stale=value\n", encoding="utf-8")
    session_env.chmod(0o644)

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    assert session_env.read_text(encoding="utf-8") == (
        f"DISPLAY=:7\nXAUTHORITY={paths['xauthority']}\n"
    )
    assert stat.S_IMODE(session_env.stat().st_mode) == 0o600


def test_launcher_records_active_browser_pid_start_time_and_selected_name(tmp_path):
    env, paths = launcher_environment(tmp_path)
    record_log = tmp_path / "browser-record.log"
    process_log = tmp_path / "browser-process.log"
    env["EXTRUSION_TEST_BROWSER_RECORD_LOG"] = str(record_log)
    env["EXTRUSION_TEST_BROWSER_PROCESS_LOG"] = str(process_log)
    write_executable(
        paths["bin"] / "chromium",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$$\" > \"$EXTRUSION_TEST_BROWSER_PROCESS_LOG\"\n"
        "record=\"$EXTRUSION_KIOSK_RUNTIME_DIR/extrusion-kiosk-browser.pid\"\n"
        "attempt=0\n"
        "while [ ! -f \"$record\" ] && [ \"$attempt\" -lt 100 ]; do\n"
        "  /bin/sleep 0.01\n"
        "  attempt=$((attempt + 1))\n"
        "done\n"
        "[ -f \"$record\" ] || exit 88\n"
        "cp \"$record\" \"$EXTRUSION_TEST_BROWSER_RECORD_LOG\"\n",
    )

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    record = dict(
        line.split("=", 1)
        for line in record_log.read_text(encoding="utf-8").splitlines()
    )
    assert set(record) == {"PID", "START_TIME", "BROWSER"}
    assert record["PID"] == process_log.read_text(encoding="utf-8").strip()
    assert record["BROWSER"] == "chromium"
    assert record["START_TIME"].isascii() and record["START_TIME"].isdigit()
    assert not (paths["runtime"] / "extrusion-kiosk-browser.pid").exists()


@pytest.mark.parametrize(
    ("runtime_dir", "should_launch"),
    [
        ("relative/runtime", False),
        ("/", False),
        ("//", False),
        ("///", False),
        ("/tmp/../unsafe", False),
        (None, True),
    ],
)
def test_launcher_rejects_root_relative_or_parent_traversal_runtime_directory(
    tmp_path, runtime_dir, should_launch
):
    env, paths = launcher_environment(tmp_path)
    safe_runtime = tmp_path / "safe-runtime"
    env["EXTRUSION_KIOSK_RUNTIME_DIR"] = runtime_dir or str(safe_runtime)

    result = run_script(LAUNCHER, env=env)

    if should_launch:
        assert result.returncode == 0
        assert safe_runtime.is_dir()
        assert paths["chromium_log"].exists()
    else:
        assert result.returncode != 0
        assert "Runtime directory" in result.stderr
        assert not paths["chromium_log"].exists()


def test_launcher_preserves_existing_xfwm_gpu_keyring_and_kiosk_flags(tmp_path):
    env, paths = launcher_environment(tmp_path)

    result = run_script(LAUNCHER, env=env)

    assert result.returncode == 0
    arguments = chromium_arguments(paths)
    assert "--kiosk" in arguments
    assert "--disable-gpu" in arguments
    assert "--disable-gpu-compositing" in arguments
    assert "--no-first-run" in arguments
    assert "--disable-infobars" in arguments
    assert "--disable-session-crashed-bubble" in arguments
    assert "--disable-features=Translate" in arguments
    assert "--password-store=basic" in arguments
    assert f"--user-data-dir={paths['profile']}" in arguments
    assert paths["desktop_log"].read_text(encoding="utf-8").splitlines() == [
        "xset|s off|XDG_CURRENT_DESKTOP=|DESKTOP_SESSION=",
        "xset|s noblank|XDG_CURRENT_DESKTOP=|DESKTOP_SESSION=",
        "xset|-dpms|XDG_CURRENT_DESKTOP=|DESKTOP_SESSION=",
        "xfwm4|--replace|XDG_CURRENT_DESKTOP=XFCE|DESKTOP_SESSION=xfce",
        "unclutter|-idle 2 -root|XDG_CURRENT_DESKTOP=XFCE|DESKTOP_SESSION=xfce",
    ]


def test_maintenance_page_contains_exact_approved_bulgarian_copy():
    source = PAGE.read_text(encoding="utf-8")

    assert "Извършва се техническа поддръжка" in source
    assert "Терминалът временно не е достъпен. Моля, изчакайте." in source


def test_maintenance_page_has_no_controls_scripts_or_network_resources():
    source = PAGE.read_text(encoding="utf-8")

    for forbidden in (
        "<button", "<a ", "<form", "<input", "<select", "<textarea",
        "<script", "http:", "https:", "@import",
    ):
        assert forbidden not in source.lower()


def test_maintenance_page_references_only_local_gears_png():
    source = PAGE.read_text(encoding="utf-8")

    assert '<img src="gears.png"' in source
    assert source.count(".png") == 1


def test_bundle_gears_matches_selected_source_byte_for_byte():
    assert GEARS.read_bytes() == (REPO_ROOT / "ui-prototypes/gears.png").read_bytes()


def test_visual_verifier_has_valid_node_syntax():
    result = subprocess.run(
        ["node", "--check", str(VERIFIER)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def installer_environment(tmp_path: Path) -> tuple[dict[str, str], dict[str, Path]]:
    """Create a temporary install root and harmless package/user command doubles."""
    root = tmp_path / "root"
    bin_dir = tmp_path / "bin"
    apt_log = tmp_path / "apt-get.log"
    id_log = tmp_path / "id.log"
    install_log = tmp_path / "install.log"
    root.mkdir()
    bin_dir.mkdir()
    write_executable(
        bin_dir / "apt-get",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$EXTRUSION_TEST_APT_LOG\"\n",
    )
    write_executable(
        bin_dir / "id",
        "#!/bin/sh\nprintf '%s\\n' \"$@\" >> \"$EXTRUSION_TEST_ID_LOG\"\nexit 0\n",
    )
    write_executable(
        bin_dir / "install",
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" >> \"$EXTRUSION_TEST_INSTALL_LOG\"\n"
        "exec /usr/bin/install \"$@\"\n",
    )
    env = os.environ.copy()
    env.update(
        {
            "EXTRUSION_INSTALL_ROOT": str(root),
            "EXTRUSION_INSTALL_APT_GET": str(bin_dir / "apt-get"),
            "EXTRUSION_INSTALL_ID": str(bin_dir / "id"),
            "EXTRUSION_INSTALL_INSTALL": str(bin_dir / "install"),
            "EXTRUSION_TEST_APT_LOG": str(apt_log),
            "EXTRUSION_TEST_ID_LOG": str(id_log),
            "EXTRUSION_TEST_INSTALL_LOG": str(install_log),
        }
    )
    return env, {
        "root": root,
        "bin": bin_dir,
        "apt_log": apt_log,
        "id_log": id_log,
        "install_log": install_log,
    }


def prepare_existing_kiosk_runtime(root: Path, marker_contents: bytes = b"marker\n") -> Path:
    """Provide the base-kiosk prerequisites that this bundle must preserve."""
    url_file = root / "etc/extrusion-kiosk-url"
    launcher = root / "usr/local/bin/extrusion-kiosk-session"
    session = root / "usr/share/xsessions/extrusion-kiosk.desktop"
    marker = root / "var/lib/extrusion-kiosk/maintenance-enabled"
    for path in (url_file, launcher, session, marker):
        path.parent.mkdir(parents=True, exist_ok=True)
    url_file.write_text("http://192.168.1.83:8000/terminal\n", encoding="utf-8")
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    session.write_text("[Desktop Entry]\n", encoding="utf-8")
    marker.write_bytes(marker_contents)
    return marker


def copied_bundle(tmp_path: Path) -> Path:
    """Copy the portable bundle so a preflight test can safely remove a sibling."""
    destination = tmp_path / "workstation-maintenance"
    shutil.copytree(BUNDLE_DIR, destination)
    return destination


def test_installer_requires_root_before_any_mutation(tmp_path):
    env = os.environ.copy()
    env.pop("EXTRUSION_INSTALL_ROOT", None)
    env["EXTRUSION_INSTALL_APT_GET"] = str(tmp_path / "apt-get")

    result = run_script(INSTALLER, env=env)

    assert result.returncode != 0
    assert "Run this installer with sudo or as root" in result.stderr
    assert not (tmp_path / "apt-get").exists()


@pytest.mark.parametrize("root_alias", ["//", "///", "/.", "/tmp/.."])
def test_installer_rejects_equivalent_root_test_prefix_before_any_mutation(tmp_path, root_alias):
    env, paths = installer_environment(tmp_path)
    env["EXTRUSION_INSTALL_ROOT"] = root_alias

    result = run_script(INSTALLER, env=env)

    assert result.returncode != 0
    assert "EXTRUSION_INSTALL_ROOT" in result.stderr
    assert not paths["id_log"].exists()
    assert not paths["apt_log"].exists()
    assert not (paths["root"] / "usr/local/share/extrusion-kiosk").exists()


def test_installer_rejects_symlinked_root_test_prefix_before_any_mutation(tmp_path):
    env, paths = installer_environment(tmp_path)
    root_alias = tmp_path / "root-alias"
    root_alias.symlink_to("/")
    env["EXTRUSION_INSTALL_ROOT"] = str(root_alias)

    result = run_script(INSTALLER, env=env)

    assert result.returncode != 0
    assert "EXTRUSION_INSTALL_ROOT" in result.stderr
    assert not paths["id_log"].exists()
    assert not paths["apt_log"].exists()
    assert not (paths["root"] / "usr/local/share/extrusion-kiosk").exists()


@pytest.mark.parametrize("escaped_parent", ["etc", "usr/local", "var/lib"])
def test_installer_rejects_nested_test_root_symlink_escape_before_any_mutation(
    tmp_path, escaped_parent
):
    env, paths = installer_environment(tmp_path)
    prepare_existing_kiosk_runtime(paths["root"])
    rooted_parent = paths["root"] / escaped_parent
    outside_parent = tmp_path / "outside" / escaped_parent
    outside_parent.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(rooted_parent, outside_parent)
    shutil.rmtree(rooted_parent)
    rooted_parent.symlink_to(outside_parent, target_is_directory=True)

    result = run_script(INSTALLER, env=env)

    assert result.returncode != 0
    assert "escapes EXTRUSION_INSTALL_ROOT" in result.stderr
    assert not paths["id_log"].exists()
    assert not paths["apt_log"].exists()
    assert not paths["install_log"].exists()
    assert not (paths["root"] / "usr/local/bin/extrusion-kiosk-maintenance").exists()
    assert not (outside_parent / "bin/extrusion-kiosk-maintenance").exists()


def test_installer_preflights_runtime_bundle_before_apt(tmp_path):
    bundle = copied_bundle(tmp_path)
    (bundle / "gears.png").unlink()
    env, paths = installer_environment(tmp_path)

    result = run_script(bundle / "install.sh", env=env)

    assert result.returncode != 0
    assert "gears.png" in result.stderr
    assert not paths["apt_log"].exists()
    assert not paths["id_log"].exists()
    assert not (paths["root"] / "usr/local/share/extrusion-kiosk").exists()


@pytest.mark.parametrize(
    ("path_class", "path_within_bundle"),
    [
        ("bundle controller", "extrusion-kiosk-maintenance"),
        ("bundle launcher", "extrusion-kiosk-session"),
        ("bundle page", "maintenance.html"),
        ("bundle image", "gears.png"),
        ("base URL", "etc/extrusion-kiosk-url"),
        ("base launcher", "usr/local/bin/extrusion-kiosk-session"),
        ("base X session", "usr/share/xsessions/extrusion-kiosk.desktop"),
    ],
)
def test_installer_rejects_required_directory_before_id_package_or_install_mutation(
    tmp_path, path_class, path_within_bundle
):
    bundle = copied_bundle(tmp_path)
    env, paths = installer_environment(tmp_path)
    prepare_existing_kiosk_runtime(paths["root"])
    installed_controller = paths["root"] / "usr/local/bin/extrusion-kiosk-maintenance"
    installed_controller.parent.mkdir(parents=True, exist_ok=True)
    installed_controller.write_bytes(b"existing installed controller\n")

    if path_class.startswith("bundle"):
        required_path = bundle / path_within_bundle
    else:
        required_path = paths["root"] / path_within_bundle
    required_path.unlink()
    required_path.mkdir()

    result = run_script(bundle / "install.sh", env=env)

    assert result.returncode != 0
    assert "regular" in result.stderr
    assert path_within_bundle.rsplit("/", 1)[-1] in result.stderr
    assert not paths["id_log"].exists()
    assert not paths["apt_log"].exists()
    assert installed_controller.read_bytes() == b"existing installed controller\n"


def test_installer_requires_existing_kiosk_user_url_and_session(tmp_path):
    env, paths = installer_environment(tmp_path)
    write_executable(paths["bin"] / "id", "#!/bin/sh\nexit 1\n")

    missing_user = run_script(INSTALLER, env=env)
    assert missing_user.returncode != 0
    assert not paths["apt_log"].exists()

    write_executable(paths["bin"] / "id", "#!/bin/sh\nexit 0\n")
    missing_url = run_script(INSTALLER, env=env)
    assert missing_url.returncode != 0
    assert "/etc/extrusion-kiosk-url" in missing_url.stderr

    url_file = paths["root"] / "etc/extrusion-kiosk-url"
    url_file.parent.mkdir(parents=True)
    url_file.write_text("http://192.168.1.83:8000/terminal\n", encoding="utf-8")
    missing_launcher = run_script(INSTALLER, env=env)
    assert missing_launcher.returncode != 0
    assert "extrusion-kiosk-session" in missing_launcher.stderr

    launcher = paths["root"] / "usr/local/bin/extrusion-kiosk-session"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    missing_session = run_script(INSTALLER, env=env)
    assert missing_session.returncode != 0
    assert "extrusion-kiosk.desktop" in missing_session.stderr
    assert not paths["apt_log"].exists()


def test_installer_installs_yad_and_exact_files_with_expected_modes(tmp_path):
    env, paths = installer_environment(tmp_path)
    prepare_existing_kiosk_runtime(paths["root"])

    result = run_script(INSTALLER, env=env)

    assert result.returncode == 0, result.stderr
    assert paths["apt_log"].read_text(encoding="utf-8").splitlines() == [
        "update",
        "install",
        "-y",
        "yad",
    ]
    assert paths["id_log"].read_text(encoding="utf-8").splitlines() == ["-u", "kiosk"]
    installed = {
        paths["root"] / "usr/local/bin/extrusion-kiosk-maintenance": 0o755,
        paths["root"] / "usr/local/bin/extrusion-kiosk-session": 0o755,
        paths["root"] / "usr/local/share/extrusion-kiosk/maintenance.html": 0o644,
        paths["root"] / "usr/local/share/extrusion-kiosk/gears.png": 0o644,
        paths["root"] / "var/lib/extrusion-kiosk": 0o755,
    }
    for path, mode in installed.items():
        assert path.exists()
        assert stat.S_IMODE(path.stat().st_mode) == mode
    assert (paths["root"] / "usr/local/bin/extrusion-kiosk-maintenance").read_bytes() == CONTROLLER.read_bytes()
    assert (paths["root"] / "usr/local/bin/extrusion-kiosk-session").read_bytes() == LAUNCHER.read_bytes()
    assert (paths["root"] / "usr/local/share/extrusion-kiosk/maintenance.html").read_bytes() == PAGE.read_bytes()
    assert (paths["root"] / "usr/local/share/extrusion-kiosk/gears.png").read_bytes() == GEARS.read_bytes()


def test_installer_preserves_existing_maintenance_marker(tmp_path):
    env, paths = installer_environment(tmp_path)
    marker = prepare_existing_kiosk_runtime(paths["root"], b"do not clear this marker\x00\n")

    result = run_script(INSTALLER, env=env)

    assert result.returncode == 0, result.stderr
    assert marker.read_bytes() == b"do not clear this marker\x00\n"


def test_installer_is_idempotent(tmp_path):
    env, paths = installer_environment(tmp_path)
    marker = prepare_existing_kiosk_runtime(paths["root"], b"keep\n")

    first = run_script(INSTALLER, env=env)
    second = run_script(INSTALLER, env=env)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert marker.read_bytes() == b"keep\n"
    assert paths["apt_log"].read_text(encoding="utf-8").splitlines() == [
        "update", "install", "-y", "yad", "update", "install", "-y", "yad"
    ]


def test_installer_prints_reboot_and_post_reboot_status_commands_without_rebooting(tmp_path):
    env, paths = installer_environment(tmp_path)
    prepare_existing_kiosk_runtime(paths["root"])
    reboot_log = tmp_path / "reboot.log"
    write_executable(
        paths["bin"] / "reboot",
        "#!/bin/sh\nprintf called > \"$EXTRUSION_TEST_REBOOT_LOG\"\n",
    )
    env["PATH"] = f"{paths['bin']}{os.pathsep}{env.get('PATH', '')}"
    env["EXTRUSION_TEST_REBOOT_LOG"] = str(reboot_log)

    result = run_script(INSTALLER, env=env)

    assert result.returncode == 0, result.stderr
    assert "sudo reboot" in result.stdout
    assert "sudo extrusion-kiosk-maintenance status" in result.stdout
    assert not reboot_log.exists()


def test_complete_copyable_bundle_contains_every_documented_file():
    expected = {
        "README.md",
        "install.sh",
        "extrusion-kiosk-maintenance",
        "extrusion-kiosk-session",
        "maintenance.html",
        "gears.png",
        "verify-ui.mjs",
        "test_workstation_maintenance.py",
    }

    assert expected <= {path.name for path in BUNDLE_DIR.iterdir()}


def test_readme_contains_exact_scp_ssh_install_and_runtime_commands():
    source = (BUNDLE_DIR / "README.md").read_text(encoding="utf-8")

    for command in (
        "scp -r workstation-maintenance extrusion-terminal@100.94.38.101:~/",
        "ssh -t extrusion-terminal@100.94.38.101 \\",
        "  'cd ~/workstation-maintenance && sudo bash install.sh'",
        "ssh -t extrusion-terminal@100.94.38.101 'sudo reboot'",
        "sudo extrusion-kiosk-maintenance status",
        "sudo extrusion-kiosk-maintenance notify 30",
        "sudo extrusion-kiosk-maintenance on",
        "sudo extrusion-kiosk-maintenance off",
    ):
        assert command in source
