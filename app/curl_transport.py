from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from .bounded_files import read_bounded_regular_file


CURL_PROCESS_TIMEOUT_SECONDS = 180
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_CONFIG_LINES = 200
_MAX_CONFIG_LINE_LENGTH = 8 * 1024


@dataclass(frozen=True)
class CurlResult:
    returncode: int
    stdout: str
    stderr: str


class CurlRunner(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        *,
        input_bytes: bytes | None = None,
    ) -> CurlResult: ...


def run_curl(
    command: Sequence[str],
    *,
    input_bytes: bytes | None = None,
) -> CurlResult:
    if isinstance(command, (str, bytes)):
        raise TypeError("curl command must be an argument sequence, not a shell string")
    completed = subprocess.run(
        list(command),
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=CURL_PROCESS_TIMEOUT_SECONDS,
    )
    return CurlResult(
        completed.returncode,
        completed.stdout.decode("utf-8", errors="replace"),
        completed.stderr.decode("utf-8", errors="replace"),
    )


def validate_curl_config(
    path: Path | str,
    *,
    required_options: frozenset[str],
    allowed_options: frozenset[str],
) -> Mapping[str, str]:
    if not required_options <= allowed_options:
        raise ValueError("Required curl config options must be allowlisted.")
    config_path = Path(path)
    try:
        raw = read_bounded_regular_file(
            config_path,
            max_bytes=_MAX_CONFIG_BYTES,
            label="Curl config",
        )
    except FileNotFoundError as error:
        raise ValueError(f"Unable to read curl config: {config_path}") from error
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Curl config is not UTF-8: {config_path}") from error

    parsed: dict[str, str] = {}
    lines = text.splitlines()
    if len(lines) > _MAX_CONFIG_LINES:
        raise ValueError(f"Curl config has too many lines: {config_path}")
    for line_number, raw_line in enumerate(lines, start=1):
        if len(raw_line) > _MAX_CONFIG_LINE_LENGTH:
            raise ValueError(
                f"Curl config line {line_number} is too long: {config_path}"
            )
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Malformed curl config directive on line {line_number}: {config_path}"
            )
        name, raw_value = line.split("=", 1)
        name = name.strip().removeprefix("--")
        if not name or name not in allowed_options:
            raise ValueError(
                f"Curl config option is not allowed on line {line_number}: {config_path}"
            )
        if name in parsed:
            raise ValueError(
                f"Duplicate curl config option on line {line_number}: {config_path}"
            )
        try:
            values = shlex.split(raw_value.strip(), comments=False, posix=True)
        except ValueError as error:
            raise ValueError(
                f"Malformed curl config value on line {line_number}: {config_path}"
            ) from error
        if len(values) != 1 or not values[0]:
            raise ValueError(
                f"Curl config option requires one value on line {line_number}: {config_path}"
            )
        parsed[name] = values[0]

    missing = required_options - parsed.keys()
    if missing:
        raise ValueError(f"Curl config is missing required options: {config_path}")
    return MappingProxyType(parsed)
