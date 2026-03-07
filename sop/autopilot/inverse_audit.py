from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import os
import subprocess
import sys
import time

from .command_utils import substitute_command_tokens
from .contracts import with_schema_version
from .schemas import InverseConfig


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_list_command(raw: str, source: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON command list in {source}: {exc}") from exc
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"command in {source} must be a non-empty JSON list")

    command: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, str):
            raise ValueError(f"command item at index {index} in {source} must be a string")
        if not item:
            raise ValueError(f"command item at index {index} in {source} must not be empty")
        command.append(item)
    return substitute_command_tokens(command)


def _default_command(prev_bundle_dir: Path, curr_bundle_dir: Path, audit_dir: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "sop.inverse_engine.cli",
        "diff",
        "--a",
        str(prev_bundle_dir),
        "--b",
        str(curr_bundle_dir),
        "--out",
        str(audit_dir),
    ]


def _resolve_command(
    inverse_cfg: InverseConfig,
    prev_bundle_dir: Path,
    curr_bundle_dir: Path,
    audit_dir: Path,
) -> tuple[str | list[str], str]:
    if inverse_cfg.cmd_file:
        cmd_path = Path(inverse_cfg.cmd_file)
        if not cmd_path.exists():
            raise ValueError(f"inverse cmd_file not found: {cmd_path}")
        try:
            raw = cmd_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ValueError(f"failed to read inverse cmd_file '{cmd_path}': {exc}") from exc
        return _parse_list_command(raw, f"inverse cmd_file:{cmd_path}"), "list"

    if inverse_cfg.cmd is not None:
        if isinstance(inverse_cfg.cmd, list):
            return substitute_command_tokens(list(inverse_cfg.cmd)), "list"
        cmd_text = inverse_cfg.cmd
        if cmd_text.lstrip().startswith("["):
            return _parse_list_command(cmd_text, "inverse cmd"), "list"
        return cmd_text, "string"

    return _default_command(prev_bundle_dir, curr_bundle_dir, audit_dir), "list"


def _write_exec_log(
    exec_path: Path,
    cmd: str | list[str] | None,
    cmd_mode: str,
    returncode: int | None,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "cmd": cmd,
        "cmd_mode": cmd_mode,
        "returncode": returncode,
        "start_time": started_at,
        "end_time": ended_at,
        "duration_ms": duration_ms,
    }
    if error_type:
        payload["error_type"] = error_type
    if error_message:
        payload["error_message"] = error_message
    exec_path.write_text(json.dumps(with_schema_version(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def run_inverse_diff(
    prev_bundle_dir: str | Path,
    curr_bundle_dir: str | Path,
    inverse_cfg: InverseConfig,
    audit_dir: str | Path,
) -> tuple[bool, dict[str, Any]]:
    prev_dir = Path(prev_bundle_dir)
    curr_dir = Path(curr_bundle_dir)
    audit_path = Path(audit_dir)
    audit_path.mkdir(parents=True, exist_ok=True)

    stdout_path = audit_path / "stdout.txt"
    stderr_path = audit_path / "stderr.txt"
    exec_path = audit_path / "exec.json"
    report_path = audit_path / "report.md"
    diff_path = audit_path / "diff.json"

    started = datetime.now(timezone.utc)
    started_iso = started.isoformat()
    started_perf = time.perf_counter()
    command: str | list[str] | None = None
    cmd_mode = "list"
    returncode: int | None = None
    stdout = ""
    stderr = ""
    error_type = ""
    error_message = ""
    warnings: list[str] = []

    try:
        command, cmd_mode = _resolve_command(
            inverse_cfg=inverse_cfg,
            prev_bundle_dir=prev_dir,
            curr_bundle_dir=curr_dir,
            audit_dir=audit_path,
        )
        env = os.environ.copy()
        env["AUTOPILOT_PREV_BUNDLE_DIR"] = str(prev_dir.resolve())
        env["AUTOPILOT_CURR_BUNDLE_DIR"] = str(curr_dir.resolve())
        env["AUTOPILOT_AUDIT_OUT_DIR"] = str(audit_path.resolve())
        result = subprocess.run(
            command,
            shell=cmd_mode == "string",
            cwd=str(curr_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=float(inverse_cfg.timeout_seconds),
        )
        returncode = result.returncode
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        if returncode != 0:
            error_type = "nonzero_exit"
            error_message = "inverse diff command returned non-zero exit code"
    except subprocess.TimeoutExpired as exc:
        error_type = "timeout"
        error_message = f"inverse diff command timed out after {inverse_cfg.timeout_seconds} seconds"
        if isinstance(exc.stdout, bytes):
            stdout = exc.stdout.decode("utf-8", errors="replace")
        elif isinstance(exc.stdout, str):
            stdout = exc.stdout
        if isinstance(exc.stderr, bytes):
            stderr = exc.stderr.decode("utf-8", errors="replace")
        elif isinstance(exc.stderr, str):
            stderr = exc.stderr
    except Exception as exc:  # pragma: no cover - defensive
        error_type = type(exc).__name__
        error_message = str(exc)

    ended_iso = _utc_now()
    duration_ms = int((time.perf_counter() - started_perf) * 1000)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    _write_exec_log(
        exec_path=exec_path,
        cmd=command,
        cmd_mode=cmd_mode,
        returncode=returncode,
        started_at=started_iso,
        ended_at=ended_iso,
        duration_ms=duration_ms,
        error_type=error_type or None,
        error_message=error_message or None,
    )

    if error_type:
        details = {
            "ok": False,
            "error_type": error_type,
            "error_message": error_message,
            "returncode": returncode,
            "audit_dir": str(audit_path),
            "report_path": str(report_path),
            "diff_path": str(diff_path),
            "exec_path": str(exec_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "cmd": command,
            "cmd_mode": cmd_mode,
        }
        return False, details

    if not diff_path.exists():
        warnings.append("inverse command succeeded but did not produce diff.json; created placeholder")
        diff_placeholder = {"ok": True, "warning": "placeholder diff generated by autopilot inverse audit"}
        diff_path.write_text(json.dumps(diff_placeholder, ensure_ascii=False, indent=2), encoding="utf-8")
    if not report_path.exists():
        warnings.append("inverse command succeeded but did not produce report.md; created placeholder")
        report_path.write_text(
            "# Inverse Diff Report\n\nPlaceholder report generated by autopilot inverse audit.\n",
            encoding="utf-8",
        )

    details = {
        "ok": True,
        "returncode": returncode,
        "audit_dir": str(audit_path),
        "report_path": str(report_path),
        "diff_path": str(diff_path),
        "exec_path": str(exec_path),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "cmd": command,
        "cmd_mode": cmd_mode,
        "warnings": warnings,
    }
    return True, details
