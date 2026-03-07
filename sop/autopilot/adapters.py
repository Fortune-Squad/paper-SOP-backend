from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
import json
import logging
import os
import random
import subprocess
import time

from .command_utils import substitute_command_tokens
from .contracts import with_schema_version
from .schemas import CandidateCard, ProgramSpec
from .validation import write_validation_report


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    now = datetime.now(timezone.utc)
    # Sortable UTC run id: YYYYMMDD_HHMMSS_microsec_hex4
    return now.strftime("%Y%m%d_%H%M%S_%f_") + f"{random.getrandbits(16):04x}"


def _new_bundle_dir(
    out_dir: str | Path,
    program_spec: ProgramSpec,
    candidate_card: CandidateCard,
) -> tuple[str, Path]:
    out_path = Path(out_dir)
    bundles_root = out_path / "bundles"
    bundles_root.mkdir(parents=True, exist_ok=True)

    run_id = _new_run_id()
    bundle_dir = bundles_root / f"{program_spec.program_id}-{candidate_card.id}-{run_id}"
    while bundle_dir.exists():
        run_id = _new_run_id()
        bundle_dir = bundles_root / f"{program_spec.program_id}-{candidate_card.id}-{run_id}"
    return run_id, bundle_dir


def _ensure_schema_version_json(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    path.write_text(json.dumps(with_schema_version(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_existing_validation_report(path: Path, run_id: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    gate_result = str(payload.get("gate_result", "FAIL")).upper()
    checks = payload.get("checks")
    checks_list = checks if isinstance(checks, list) else None

    extras = dict(payload)
    for key in {
        "schema_version",
        "run_id",
        "gate_result",
        "passed",
        "checks",
        "status",
        "error_type",
        "error_message",
        "exec_log_path",
        "stdout_path",
        "stderr_path",
    }:
        extras.pop(key, None)

    write_validation_report(
        path,
        run_id=str(payload.get("run_id", run_id) or run_id),
        gate_result=gate_result,
        checks=checks_list,
        status=str(payload.get("status", "")) if "status" in payload else None,
        error_type=str(payload.get("error_type", "")) if "error_type" in payload else None,
        error_message=str(payload.get("error_message", "")) if "error_message" in payload else None,
        exec_log_path=str(payload.get("exec_log_path", "")) if "exec_log_path" in payload else None,
        stdout_path=str(payload.get("stdout_path", "")) if "stdout_path" in payload else None,
        stderr_path=str(payload.get("stderr_path", "")) if "stderr_path" in payload else None,
        extras=extras,
    )


class KernelAdapter(Protocol):
    def submit(
        self,
        program_spec: ProgramSpec,
        candidate_card: CandidateCard,
        out_dir: str | Path,
    ) -> Path:
        """
        Execute one candidate and return its bundle directory.
        """

    def cancel_project(self, project_id: str) -> bool:
        """Kill a running project. Returns True if cancelled, False if not found."""
        ...

    def list_active_projects(self) -> list[str]:
        """Return project_ids of all currently running projects."""
        ...

    def health_check(self) -> dict[str, Any]:
        """Return adapter health status. Minimum keys: ok (bool), adapter_type (str), timestamp (str)."""
        ...


class FakeKernelAdapter:
    """
    Fake adapter for Autopilot v1.0.

    Behavior:
    - Always writes metadata.json
    - Always writes validation_report.json with PASS
    """

    def __init__(self, bundles_root: str | Path | None = None) -> None:
        self.bundles_root = Path(bundles_root) if bundles_root else None
        self._active_projects: set[str] = set()

    def submit(
        self,
        program_spec: ProgramSpec,
        candidate_card: CandidateCard,
        out_dir: str | Path,
    ) -> Path:
        if self.bundles_root is not None:
            bundles_root = self.bundles_root
            bundles_root.mkdir(parents=True, exist_ok=True)
            run_id = _new_run_id()
            bundle_dir = bundles_root / f"{program_spec.program_id}-{candidate_card.id}-{run_id}"
            while bundle_dir.exists():
                run_id = _new_run_id()
                bundle_dir = bundles_root / f"{program_spec.program_id}-{candidate_card.id}-{run_id}"
        else:
            run_id, bundle_dir = _new_bundle_dir(out_dir, program_spec, candidate_card)
        bundle_dir.mkdir(parents=True, exist_ok=False)

        metadata = {
            "run_id": run_id,
            "created_at": _utc_now(),
            "adapter": "fake_kernel",
            "program_id": program_spec.program_id,
            "candidate_id": candidate_card.id,
        }
        validation_checks = [
            {
                "name": "fake_validation",
                "status": "PASS",
                "details": "FakeKernelAdapter default pass.",
            }
        ]

        with (bundle_dir / "metadata.json").open("w", encoding="utf-8") as handle:
            json.dump(with_schema_version(metadata), handle, ensure_ascii=False, indent=2)
        write_validation_report(
            bundle_dir / "validation_report.json",
            run_id=run_id,
            gate_result="PASS",
            checks=validation_checks,
        )

        self._active_projects.add(program_spec.program_id)
        return bundle_dir

    def cancel_project(self, project_id: str) -> bool:
        """Kill a running project. Returns True if cancelled, False if not found."""
        if project_id in self._active_projects:
            self._active_projects.discard(project_id)
            return True
        return False

    def list_active_projects(self) -> list[str]:
        """Return project_ids of all currently running projects."""
        return sorted(self._active_projects)

    def health_check(self) -> dict[str, Any]:
        """Return adapter health status."""
        return {
            "ok": True,
            "adapter_type": "fake",
            "timestamp": _utc_now(),
        }


class SubprocessKernelAdapter:
    """
    Subprocess-based adapter with contract enforcement.
    """

    def __init__(
        self,
        command: str | list[str],
        timeout_seconds: float | None = None,
        cmd_file: str | None = None,
    ) -> None:
        if isinstance(command, str):
            if not command or not command.strip():
                raise ValueError("command is required for SubprocessKernelAdapter")
            self.command: str | list[str] = command
            self.cmd_mode = "string"
        elif isinstance(command, list):
            if not command:
                raise ValueError("command list is required for SubprocessKernelAdapter")
            normalized: list[str] = []
            for index, item in enumerate(command):
                if not isinstance(item, str):
                    raise ValueError(f"command[{index}] must be a string")
                if not item:
                    raise ValueError(f"command[{index}] must not be empty")
                normalized.append(item)
            self.command = substitute_command_tokens(normalized)
            self.cmd_mode = "list"
        else:
            raise ValueError("command must be str or list[str]")
        self.timeout_seconds = timeout_seconds
        self.cmd_file = cmd_file

    def submit(
        self,
        program_spec: ProgramSpec,
        candidate_card: CandidateCard,
        out_dir: str | Path,
    ) -> Path:
        run_id, bundle_dir = _new_bundle_dir(out_dir, program_spec, candidate_card)
        bundle_dir.mkdir(parents=True, exist_ok=False)

        candidate_path = bundle_dir / "candidate_card.json"
        program_path = bundle_dir / "program_spec.json"
        metadata_path = bundle_dir / "metadata.json"
        validation_path = bundle_dir / "validation_report.json"
        logs_dir = bundle_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = logs_dir / "stdout.txt"
        stderr_path = logs_dir / "stderr.txt"
        exec_path = logs_dir / "exec.json"

        candidate_path.write_text(
            json.dumps(candidate_card.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        program_path.write_text(
            json.dumps(program_spec.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        started_at = datetime.now(timezone.utc)
        started_at_iso = started_at.isoformat()
        started_perf = time.perf_counter()
        command_failed = False
        return_code: int | None = None
        stdout = ""
        stderr = ""
        error_type = ""
        error_message = ""

        env = os.environ.copy()
        env["AUTOPILOT_BUNDLE_DIR"] = str(bundle_dir.resolve())
        env["AUTOPILOT_CANDIDATE_JSON"] = str(candidate_path.resolve())
        env["AUTOPILOT_PROGRAM_JSON"] = str(program_path.resolve())
        repo_root = Path(__file__).resolve().parents[2]
        current_pythonpath = env.get("PYTHONPATH", "")
        if current_pythonpath:
            env["PYTHONPATH"] = current_pythonpath + os.pathsep + str(repo_root)
        else:
            env["PYTHONPATH"] = str(repo_root)

        try:
            result = subprocess.run(
                self.command,
                shell=self.cmd_mode == "string",
                cwd=str(bundle_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            return_code = result.returncode
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            if result.returncode != 0:
                command_failed = True
                error_type = "nonzero_exit"
                error_message = "command returned non-zero exit code"
        except subprocess.TimeoutExpired as exc:
            command_failed = True
            error_type = "timeout"
            error_message = f"command timed out after {self.timeout_seconds} seconds"
            if isinstance(exc.stdout, bytes):
                stdout = exc.stdout.decode("utf-8", errors="replace")
            elif isinstance(exc.stdout, str):
                stdout = exc.stdout
            else:
                stdout = ""
            if isinstance(exc.stderr, bytes):
                stderr = exc.stderr.decode("utf-8", errors="replace")
            elif isinstance(exc.stderr, str):
                stderr = exc.stderr
            else:
                stderr = ""
        except Exception as exc:  # pragma: no cover - defensive
            command_failed = True
            error_type = "exception"
            error_message = f"subprocess launch failed: {exc}"

        ended_at = datetime.now(timezone.utc)
        ended_at_iso = ended_at.isoformat()
        duration_ms = int((time.perf_counter() - started_perf) * 1000)

        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")

        exec_payload = {
            "cmd": self.command,
            "cmd_mode": self.cmd_mode,
            "returncode": return_code,
            "start_time": started_at_iso,
            "end_time": ended_at_iso,
            "duration_ms": duration_ms,
        }
        exec_path.write_text(
            json.dumps(with_schema_version(exec_payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        command_succeeded = not command_failed

        if command_succeeded and not metadata_path.exists():
            metadata = {
                "run_id": run_id,
                "created_at": started_at_iso,
                "finished_at": ended_at_iso,
                "adapter": "subprocess_kernel",
                "program_id": program_spec.program_id,
                "candidate_id": candidate_card.id,
                "command": self.command,
                "return_code": return_code,
            }
            metadata_path.write_text(
                json.dumps(with_schema_version(metadata), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if metadata_path.exists():
            _ensure_schema_version_json(metadata_path)

        if not validation_path.exists():
            if not error_type:
                error_type = "missing_validation_report"
            if not error_message:
                error_message = "validation_report.json missing"
            command_failed = True
        elif command_succeeded:
            _normalize_existing_validation_report(validation_path, run_id=run_id)

        if command_failed:
            checks: list[dict[str, str]] = [
                {
                    "name": "subprocess_execution",
                    "status": "FAIL",
                    "details": error_message or "subprocess execution failed",
                }
            ]
            write_validation_report(
                validation_path,
                run_id=run_id,
                gate_result="FAIL",
                checks=checks,
                error_type=error_type or "subprocess_failure",
                error_message=error_message or "subprocess execution failed",
                exec_log_path=str(exec_path),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
                extras={
                    "error": {
                        "command": self.command,
                        "cmd_mode": self.cmd_mode,
                        "error_type": error_type or "subprocess_failure",
                        "error_message": error_message or "subprocess execution failed",
                        "returncode": return_code,
                        "exec_log_path": str(exec_path),
                        "stdout_path": str(stdout_path),
                        "stderr_path": str(stderr_path),
                    }
                },
            )

        return bundle_dir

    def _command_repr(self) -> str:
        """Return a safe string representation of the configured command."""
        if isinstance(self.command, list):
            return " ".join(self.command)
        return str(self.command)

    def cancel_project(self, project_id: str) -> bool:
        """Kill a running project. Returns False (placeholder, not yet wired)."""
        logging.getLogger(__name__).warning("cancel_project not yet wired to subprocess")
        return False

    def list_active_projects(self) -> list[str]:
        """Return project_ids of all currently running projects. Placeholder."""
        logging.getLogger(__name__).warning("list_active_projects not yet wired")
        return []

    def health_check(self) -> dict[str, Any]:
        """Return adapter health status."""
        return {
            "ok": True,
            "adapter_type": "subprocess",
            "timestamp": _utc_now(),
            "command": self._command_repr(),
        }
