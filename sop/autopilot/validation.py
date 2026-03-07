from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .contracts import with_schema_version


def _normalize_check(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name", "")).strip()
    status = str(item.get("status", "")).strip().upper()
    if not name or not status:
        return None
    normalized = dict(item)
    normalized["name"] = name
    normalized["status"] = status
    return normalized


def _normalize_checks(
    checks: list[dict[str, Any]] | None,
    gate_result: str,
    status: str | None,
    error_message: str | None,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if checks:
        for item in checks:
            parsed = _normalize_check(item)
            if parsed is not None:
                normalized.append(parsed)

    if normalized:
        return normalized

    if gate_result == "PASS":
        return [{"name": "validation", "status": "PASS", "details": "validation passed"}]
    if gate_result == "PENDING":
        return [
            {
                "name": "validation",
                "status": "PENDING",
                "details": status or "pending",
            }
        ]
    return [
        {
            "name": "validation",
            "status": "FAIL",
            "details": error_message or "validation failed",
        }
    ]


def write_validation_report(
    path: str | Path,
    *,
    run_id: str,
    gate_result: str,
    checks: list[dict[str, Any]] | None = None,
    status: str | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    exec_log_path: str | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_gate = str(gate_result).strip().upper() or "FAIL"
    normalized_status = str(status).strip() if isinstance(status, str) else ""
    if normalized_gate == "PENDING" and not normalized_status:
        normalized_status = "PENDING"

    payload: dict[str, Any] = {
        "run_id": run_id,
        "gate_result": normalized_gate,
        "passed": normalized_gate == "PASS",
    }

    payload["checks"] = _normalize_checks(checks, normalized_gate, normalized_status or None, error_message)

    if normalized_gate == "PENDING":
        payload["passed"] = False
        payload["status"] = normalized_status

    if normalized_gate == "FAIL":
        payload["passed"] = False
        payload["error_type"] = error_type or "validation_failure"
        payload["error_message"] = error_message or "validation failed"
        if exec_log_path:
            payload["exec_log_path"] = exec_log_path
        if stdout_path:
            payload["stdout_path"] = stdout_path
        if stderr_path:
            payload["stderr_path"] = stderr_path

    if extras:
        for key, value in extras.items():
            if key in {"run_id", "gate_result", "passed", "checks"}:
                continue
            payload[key] = value

    payload = with_schema_version(payload)
    report_path = Path(path)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
