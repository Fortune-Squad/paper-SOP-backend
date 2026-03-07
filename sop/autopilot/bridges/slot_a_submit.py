from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from ..contracts import with_schema_version
from ..validation import write_validation_report


BRIDGE_NAME = "sop.autopilot.bridges.slot_a_submit"


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


def _read_existing_run_id(bundle_dir: Path) -> str:
    metadata_path = bundle_dir / "metadata.json"
    if metadata_path.exists():
        try:
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                run_id = payload.get("run_id")
                if isinstance(run_id, str) and run_id.strip():
                    return run_id.strip()
        except Exception:
            pass
    name = bundle_dir.name
    if "-" in name:
        inferred = name.rsplit("-", 1)[-1].strip()
        if inferred:
            return inferred
    return "slot-a-submit-unknown"


def _resolve_optional_path(raw: str | None) -> Path | None:
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _resolve_slot_a_paths(program_spec: dict[str, Any]) -> tuple[Path | None, Path | None, list[str]]:
    diagnostics: list[str] = []
    paths_cfg = program_spec.get("paths", {})
    if not isinstance(paths_cfg, dict):
        paths_cfg = {}

    repo_root = _resolve_optional_path(paths_cfg.get("repo_root"))
    if repo_root is None:
        repo_root = _resolve_optional_path(os.environ.get("AUTOPILOT_REPO_ROOT"))

    backend_root = _resolve_optional_path(paths_cfg.get("slot_a_backend_root"))
    if backend_root is None:
        backend_root = _resolve_optional_path(os.environ.get("AUTOPILOT_SLOT_A_BACKEND_ROOT"))

    prompts_root = _resolve_optional_path(paths_cfg.get("slot_a_prompts_root"))
    if prompts_root is None:
        prompts_root = _resolve_optional_path(os.environ.get("AUTOPILOT_SLOT_A_PROMPTS_ROOT"))

    if backend_root is None and repo_root is not None:
        backend_root = repo_root / "paper-sop-automation" / "backend"
    if prompts_root is None and backend_root is not None:
        prompts_root = backend_root / "app" / "prompts"

    if backend_root is None or prompts_root is None:
        for parent in Path(__file__).resolve().parents:
            candidate_backend = parent / "paper-sop-automation" / "backend"
            candidate_prompts = candidate_backend / "app" / "prompts"
            if backend_root is None and candidate_backend.exists():
                backend_root = candidate_backend
            if prompts_root is None and candidate_prompts.exists():
                prompts_root = candidate_prompts
            if backend_root is not None and prompts_root is not None:
                break

    if backend_root is None or not backend_root.exists():
        diagnostics.append(f"slot_a backend root not found: {backend_root}")
    if prompts_root is None or not prompts_root.exists():
        diagnostics.append(f"slot_a prompts root not found: {prompts_root}")

    return backend_root, prompts_root, diagnostics


def _try_render_with_slot_a_runner(
    program_spec: dict[str, Any],
    backend_root: Path | None,
) -> tuple[str | None, str | None, str]:
    if backend_root is None or not backend_root.exists():
        return None, None, f"backend path not found: {backend_root}"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    try:
        from app.services.slot_a.slot_a_runner import SlotARunner  # type: ignore
    except Exception as exc:
        return None, None, f"SlotARunner import failed: {type(exc).__name__}: {exc}"

    evidence = {
        "data_profile": program_spec.get("data_profile", {}),
        "privacy_report": program_spec.get("privacy_report", {}),
        "cleaned_profile": program_spec.get("cleaned_profile", {}),
        "summary_stats": program_spec.get("summary_stats", {}),
    }
    domain_context = str(program_spec.get("domain_context", ""))
    north_star = str(program_spec.get("goal", ""))

    try:
        runner = SlotARunner(
            evidence=evidence,
            domain_context=domain_context,
            north_star=north_star,
        )
    except Exception as exc:
        return None, None, f"SlotARunner init failed: {type(exc).__name__}: {exc}"

    build_explore = getattr(runner, "build_explore_prompt", None)
    build_freeze = getattr(runner, "build_freeze_prompt", None)
    if not callable(build_explore) or not callable(build_freeze):
        return None, None, "SlotARunner prompt methods not available"

    try:
        a2_prompt = str(build_explore())
        a3_prompt = str(build_freeze(findings=[], stats_guard={"findings": []}))
    except Exception as exc:
        return None, None, f"SlotARunner render failed: {type(exc).__name__}: {exc}"
    return a2_prompt, a3_prompt, "slot_a_runner"


def _read_template(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def _compose_prompt(base_text: str, context_payload: dict[str, Any], source: str) -> str:
    context_json = json.dumps(context_payload, ensure_ascii=False, indent=2)
    return (
        f"{base_text.rstrip()}\n\n"
        "---\n"
        "## AUTOPILOT SUBMIT-ONLY CONTEXT\n\n"
        f"Source: {source}\n\n"
        "```json\n"
        f"{context_json}\n"
        "```\n"
    )


def _write_metadata(
    bundle_dir: Path,
    *,
    run_id: str,
    template_source: str,
    template_paths_used: list[str],
    backend_root_used: str,
) -> None:
    metadata_path = bundle_dir / "metadata.json"
    payload: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload = existing
        except Exception:
            payload = {}

    payload.setdefault("executor", "slot_a")
    payload.setdefault("mode", "submit_only")
    payload.setdefault("bridge", BRIDGE_NAME)
    payload.setdefault("run_id", run_id)
    payload["template_source"] = template_source
    payload["template_paths_used"] = template_paths_used
    payload["backend_root_used"] = backend_root_used
    # Backward-compatible aliases.
    payload["template_paths"] = template_paths_used
    payload["runner_path"] = []
    metadata_path.write_text(json.dumps(with_schema_version(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    bundle_env = os.environ.get("AUTOPILOT_BUNDLE_DIR", "").strip()
    if bundle_env:
        bundle_path = Path(bundle_env)
        bundle_dir = bundle_path if bundle_path.is_absolute() else (Path.cwd() / bundle_path).resolve()
    else:
        bundle_dir = Path.cwd()
    bundle_dir.mkdir(parents=True, exist_ok=True)

    run_id = _read_existing_run_id(bundle_dir)
    template_source = "template_files"
    template_paths_used: list[str] = []
    backend_root_used = ""

    try:
        candidate_path = _require_env_path("AUTOPILOT_CANDIDATE_JSON")
        program_path = _require_env_path("AUTOPILOT_PROGRAM_JSON")

        candidate_card = _read_json_file(candidate_path)
        program_spec = _read_json_file(program_path)
        run_id = _read_existing_run_id(bundle_dir)

        backend_root, prompts_root, path_diagnostics = _resolve_slot_a_paths(program_spec)
        backend_root_used = str(backend_root) if backend_root is not None else ""

        a2_template_path = (
            prompts_root / "gemini" / "slot_a_data_explore.md"
            if prompts_root is not None
            else Path("missing_slot_a_data_explore.md")
        )
        a3_template_path = (
            prompts_root / "chatgpt" / "slot_a_freeze.md"
            if prompts_root is not None
            else Path("missing_slot_a_freeze.md")
        )
        template_paths_used = [str(a2_template_path), str(a3_template_path)]

        artifacts_dir = bundle_dir / "artifacts" / "slot_a"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        context_payload = {
            "program_spec": program_spec,
            "candidate_card": candidate_card,
        }

        a2_prompt, a3_prompt, source = _try_render_with_slot_a_runner(program_spec, backend_root)
        diagnostics = list(path_diagnostics)
        if a2_prompt is None or a3_prompt is None:
            diagnostics.append(source)
            a2_base = _read_template(a2_template_path)
            a3_base = _read_template(a3_template_path)
            if a2_base is None or a3_base is None:
                raise RuntimeError(
                    "slot_a template-file fallback failed: missing templates; diagnostics: "
                    + "; ".join(diagnostics)
                )
            a2_prompt = _compose_prompt(a2_base, context_payload, "template_files")
            a3_prompt = _compose_prompt(a3_base, context_payload, "template_files")
            source = "template_files"
            template_source = "template_files"
        else:
            a2_prompt = _compose_prompt(a2_prompt, context_payload, "slot_a_runner")
            a3_prompt = _compose_prompt(a3_prompt, context_payload, "slot_a_runner")
            template_source = "slot_a_runner"

        a2_path = artifacts_dir / "a2_prompt.md"
        a3_path = artifacts_dir / "a3_prompt.md"
        context_path = artifacts_dir / "context.json"

        a2_path.write_text(a2_prompt, encoding="utf-8")
        a3_path.write_text(a3_prompt, encoding="utf-8")
        context_path.write_text(
            json.dumps(with_schema_version(context_payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        _write_metadata(
            bundle_dir=bundle_dir,
            run_id=run_id,
            template_source=template_source,
            template_paths_used=template_paths_used,
            backend_root_used=backend_root_used,
        )
        write_validation_report(
            bundle_dir / "validation_report.json",
            run_id=run_id,
            gate_result="PASS",
            checks=[
                {
                    "name": "slot_a_submit_only_bundle",
                    "status": "PASS",
                    "details": f"slot_a artifacts generated via {source}",
                }
            ],
            extras={
                "artifacts": {
                    "a2_prompt": str(a2_path),
                    "a3_prompt": str(a3_path),
                    "context": str(context_path),
                }
            },
        )
        return 0
    except Exception as exc:
        _write_metadata(
            bundle_dir=bundle_dir,
            run_id=run_id,
            template_source=template_source,
            template_paths_used=template_paths_used,
            backend_root_used=backend_root_used,
        )
        write_validation_report(
            bundle_dir / "validation_report.json",
            run_id=run_id,
            gate_result="FAIL",
            checks=[
                {
                    "name": "slot_a_submit_only_bundle",
                    "status": "FAIL",
                    "details": str(exc),
                }
            ],
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
