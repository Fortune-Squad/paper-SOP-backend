from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from ..contracts import with_schema_version
from ..validation import write_validation_report


BRIDGE_NAME = "sop.autopilot.bridges.slot_b_manual_bundle"
DONE_MARKER_REL = "outputs/outputs_manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_env_path(name: str) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        raise RuntimeError(f"missing required environment variable: {name}")
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        raise RuntimeError(f"path in {name} does not exist: {path}")
    return path


def _read_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object in {path}")
    return payload


def _write_metadata(bundle_dir: Path, run_id: str) -> None:
    metadata_path = bundle_dir / "metadata.json"
    payload: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except Exception:
            payload = {}

    payload.setdefault("executor", "slot_b")
    payload.setdefault("mode", "manual_bundle")
    payload.setdefault("bridge", BRIDGE_NAME)
    payload.setdefault("run_id", run_id)
    metadata_path.write_text(
        json.dumps(with_schema_version(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_solver_log(bundle_dir: Path, message: str) -> Path:
    solver_log_path = bundle_dir / "solver_log.txt"
    solver_log_path.write_text(
        f"[{_utc_now()}] {message}\n",
        encoding="utf-8",
    )
    return solver_log_path


def _write_validation_pending(bundle_dir: Path, run_id: str, artifacts: dict[str, str]) -> None:
    validation_path = bundle_dir / "validation_report.json"
    write_validation_report(
        validation_path,
        run_id=run_id,
        gate_result="PENDING",
        status="WAITING_EXTERNAL_OUTPUTS",
        checks=[
            {
                "name": "slot_b_manual_bundle",
                "status": "PENDING",
                "details": "manual bundle created; waiting for external outputs marker",
            }
        ],
        extras={
            "done_marker": DONE_MARKER_REL,
            "artifacts": artifacts,
        },
    )


def _write_validation_fail(bundle_dir: Path, run_id: str, exc: Exception) -> None:
    validation_path = bundle_dir / "validation_report.json"
    write_validation_report(
        validation_path,
        run_id=run_id,
        gate_result="FAIL",
        checks=[
            {
                "name": "slot_b_manual_bundle",
                "status": "FAIL",
                "details": str(exc),
            }
        ],
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def _build_manual_bundle_job(program_spec: dict[str, Any], candidate_card: dict[str, Any]) -> dict[str, Any]:
    tool_raw = candidate_card.get("tool")
    if not isinstance(tool_raw, str) or not tool_raw.strip():
        tool_raw = program_spec.get("tool", "")
    tool = str(tool_raw).strip()

    instructions = (
        "Submit-only manual bundle mode.\n"
        "Run the external Slot-B workflow manually (no waiting in autopilot).\n"
        "After simulation, put outputs under outputs/ and create outputs/outputs_manifest.json.\n"
        "Manifest schema supports either string paths or objects with path/size/sha256.\n"
        "autopilot tick promotes PENDING->PASS only when files exist and optional size/hash checks pass."
    )

    return {
        "execution_type": "slot_b",
        "mode": "manual_bundle",
        "tool": tool,
        "inputs": [],
        "expected_outputs": [],
        "instructions": instructions,
    }


def _build_readme_text(bundle_dir: Path, manual_job_path: Path) -> str:
    return (
        "# Slot-B Manual Bundle Instructions\n\n"
        "This bundle was generated in submit-only mode.\n\n"
        "## What To Run\n\n"
        "1. Open `manual_bundle_job.json` for the requested context and instructions.\n"
        "2. Run your Slot-B external simulation workflow manually.\n\n"
        "## Where To Place Outputs\n\n"
        "1. Place outputs under `outputs/` inside this bundle directory.\n"
        "2. Create done marker file `outputs/outputs_manifest.json` (JSON).\n"
        "3. Run `py -m sop.autopilot.cli tick --out <autopilot_out_dir>`.\n"
        "4. Tick promotes to PASS only when all files listed in manifest exist.\n"
        "5. If a manifest entry includes `size` or `sha256`, tick verifies those too.\n\n"
        "Manifest schema:\n"
        "- `files`: either a list of relative path strings, or a list of objects\n"
        "- object form: `{ \"path\": \"relative\", \"size\": <int optional>, \"sha256\": \"<hex optional>\" }`\n"
        "- `note`: optional string\n\n"
        "Example manifest (simple):\n"
        "```json\n"
        "{\n"
        "  \"files\": [\"result.txt\", \"plots/summary.png\"],\n"
        "  \"note\": \"slot-b run complete\"\n"
        "}\n"
        "```\n\n"
        "Example manifest (with verification):\n"
        "```json\n"
        "{\n"
        "  \"files\": [\n"
        "    {\n"
        "      \"path\": \"result.txt\",\n"
        "      \"size\": 3,\n"
        "      \"sha256\": \"2689367b205c16ce32f8f4cce8a3f3d2c1f9f2472f5f45a39f7f5d0ef9f0a4f5\"\n"
        "    }\n"
        "  ],\n"
        "  \"note\": \"verified bundle\"\n"
        "}\n"
        "```\n\n"
        "Bundle directory:\n"
        f"- `{bundle_dir}`\n\n"
        "Job file:\n"
        f"- `{manual_job_path}`\n\n"
        "## Expected Files\n\n"
        "- Solver result exports generated by your external workflow\n"
        "- Any run notes or post-processing summaries\n"
        "- Keep `solver_log.txt` for traceability\n"
    )


def main() -> int:
    bundle_env = os.environ.get("AUTOPILOT_BUNDLE_DIR", "").strip()
    if bundle_env:
        bundle_path = Path(bundle_env)
        bundle_dir = bundle_path if bundle_path.is_absolute() else (Path.cwd() / bundle_path).resolve()
    else:
        bundle_dir = Path.cwd()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    run_id = "slot-b-manual-bundle-unknown"

    try:
        candidate_path = _require_env_path("AUTOPILOT_CANDIDATE_JSON")
        program_path = _require_env_path("AUTOPILOT_PROGRAM_JSON")
        candidate_card = _read_json_file(candidate_path)
        program_spec = _read_json_file(program_path)

        program_id = str(program_spec.get("program_id", "unknown"))
        candidate_id = str(candidate_card.get("id", "unknown"))
        run_id = f"{program_id}-{candidate_id}"

        artifacts_dir = bundle_dir / "artifacts" / "slot_b"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        outputs_dir = bundle_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)

        context_payload = {
            "program_spec": program_spec,
            "candidate_card": candidate_card,
        }

        context_path = artifacts_dir / "context.json"
        manual_job_path = artifacts_dir / "manual_bundle_job.json"
        readme_path = artifacts_dir / "README.md"

        context_path.write_text(
            json.dumps(context_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        manual_job_payload = _build_manual_bundle_job(program_spec, candidate_card)
        manual_job_path.write_text(
            json.dumps(manual_job_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        readme_path.write_text(
            _build_readme_text(bundle_dir=bundle_dir, manual_job_path=manual_job_path),
            encoding="utf-8",
        )

        _write_metadata(bundle_dir, run_id=run_id)
        solver_log_path = _write_solver_log(bundle_dir, "Slot-B manual bundle created (submit-only stub).")
        _write_validation_pending(
            bundle_dir=bundle_dir,
            run_id=run_id,
            artifacts={
                "context": str(context_path),
                "manual_bundle_job": str(manual_job_path),
                "readme": str(readme_path),
                "solver_log": str(solver_log_path),
                "outputs_dir": str(outputs_dir),
                "done_marker": DONE_MARKER_REL,
            },
        )
        return 0
    except Exception as exc:
        try:
            _write_metadata(bundle_dir, run_id=run_id)
            _write_solver_log(bundle_dir, f"Slot-B manual bundle failed: {exc}")
            _write_validation_fail(bundle_dir=bundle_dir, run_id=run_id, exc=exc)
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
