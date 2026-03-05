from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import sys

from .cli import main as cli_main
from .ledger import read_jsonl


def _validate_outputs(out_dir: Path) -> None:
    ledger_path = out_dir / "program_ledger.jsonl"
    inbox_path = out_dir / "inbox" / "topk.md"
    run_records_dir = out_dir / "run_records"

    if not ledger_path.exists():
        raise RuntimeError("Missing program_ledger.jsonl")
    if not inbox_path.exists():
        raise RuntimeError("Missing inbox/topk.md")
    if not run_records_dir.exists():
        raise RuntimeError("Missing run_records directory")

    entries = read_jsonl(ledger_path)
    if not entries:
        raise RuntimeError("Ledger is empty")

    run_files = sorted(run_records_dir.glob("*.json"))
    if not run_files:
        raise RuntimeError("No run record files generated")

    for file_path in run_files:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        if "bundle_path" not in payload:
            raise RuntimeError(f"Missing bundle_path in {file_path.name}")
        if "gate_result" not in payload:
            raise RuntimeError(f"Missing gate_result in {file_path.name}")

    content = inbox_path.read_text(encoding="utf-8")
    if "Human Signoff" not in content:
        raise RuntimeError("Inbox missing Human Signoff section")


def _read_ledger_entries(out_dir: Path) -> list[dict[str, object]]:
    return read_jsonl(out_dir / "program_ledger.jsonl")


def _count_ledger_event_type(out_dir: Path, event_type: str) -> int:
    entries = _read_ledger_entries(out_dir)
    count = 0
    for entry in entries:
        if str(entry.get("event_type", "")) == event_type:
            count += 1
    return count


def _validate_dispatch_submit_events(out_dir: Path, minimum_count: int) -> None:
    entries = _read_ledger_entries(out_dir)
    dispatch_events = [entry for entry in entries if str(entry.get("event_type", "")) == "DISPATCH_SUBMIT"]
    if len(dispatch_events) < minimum_count:
        raise RuntimeError(
            f"Expected at least {minimum_count} DISPATCH_SUBMIT events, found {len(dispatch_events)}"
        )

    required_keys = {
        "ts",
        "event_type",
        "program_id",
        "candidate_id",
        "execution_type",
        "bundle_dir",
        "gate_result",
        "status",
    }
    first = dispatch_events[0]
    missing = sorted(key for key in required_keys if key not in first)
    if missing:
        raise RuntimeError(f"DISPATCH_SUBMIT event missing required keys: {', '.join(missing)}")


def _validate_tick_event_present(out_dir: Path, event_type: str) -> None:
    if _count_ledger_event_type(out_dir, event_type) < 1:
        raise RuntimeError(f"Expected ledger event_type={event_type} in {out_dir}")


def _validate_versioned_bundle_history(out_dir: Path, program_id: str) -> None:
    bundles_dir = out_dir / "bundles"
    cand1_dirs = sorted(path for path in bundles_dir.glob(f"{program_id}-cand-1-*") if path.is_dir())
    if len(cand1_dirs) < 2:
        raise RuntimeError(
            f"Expected at least 2 versioned bundle dirs for cand-1, found {len(cand1_dirs)}"
        )
    if len({str(path) for path in cand1_dirs}) < 2:
        raise RuntimeError("Expected distinct bundle dirs for cand-1 across repeated runs")

    record_path = out_dir / "run_records" / "cand-1.json"
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    previous_bundle_dir = payload.get("previous_bundle_dir")
    bundle_history = payload.get("bundle_history")
    if not isinstance(previous_bundle_dir, str) or not previous_bundle_dir.strip():
        raise RuntimeError("cand-1 run_record missing previous_bundle_dir after repeat run")
    if not isinstance(bundle_history, list) or len(bundle_history) < 1:
        raise RuntimeError("cand-1 run_record bundle_history should contain at least one entry")
    if bundle_history[-1] != previous_bundle_dir:
        raise RuntimeError("cand-1 run_record bundle_history last entry should match previous_bundle_dir")

    entries = _read_ledger_entries(out_dir)
    cand1_dispatch = [
        entry
        for entry in entries
        if str(entry.get("event_type", "")) == "DISPATCH_SUBMIT"
        and str(entry.get("candidate_id", "")) == "cand-1"
    ]
    if len(cand1_dispatch) < 2:
        raise RuntimeError("Expected at least two DISPATCH_SUBMIT events for cand-1")

    run_ids: set[str] = set()
    has_previous_bundle_detail = False
    for entry in cand1_dispatch:
        run_id = str(entry.get("run_id", "")).strip()
        if not run_id:
            details = entry.get("details")
            if isinstance(details, dict):
                run_id = str(details.get("run_id", "")).strip()
        if run_id:
            run_ids.add(run_id)
        details = entry.get("details")
        if isinstance(details, dict):
            previous_detail = details.get("previous_bundle_dir")
            if isinstance(previous_detail, str) and previous_detail.strip():
                has_previous_bundle_detail = True

    if len(run_ids) < 2:
        raise RuntimeError("Expected DISPATCH_SUBMIT events for cand-1 to have different run_id values")
    if not has_previous_bundle_detail:
        raise RuntimeError("Expected DISPATCH_SUBMIT details to include previous_bundle_dir on repeat run")


def _validate_inverse_audit_rerun(out_dir: Path) -> None:
    record_path = out_dir / "run_records" / "cand-1.json"
    if not record_path.exists():
        raise RuntimeError("Inverse rerun smoke expected run_records/cand-1.json")
    payload = json.loads(record_path.read_text(encoding="utf-8"))

    if payload.get("audit_status") != "OK":
        raise RuntimeError("Inverse rerun smoke expected audit_status=OK on second run")
    audit_dir = payload.get("audit_dir")
    audit_report_path = payload.get("audit_report_path")
    audit_diff_path = payload.get("audit_diff_path")
    audit_exec_path = payload.get("audit_exec_path")
    for key, value in {
        "audit_dir": audit_dir,
        "audit_report_path": audit_report_path,
        "audit_diff_path": audit_diff_path,
        "audit_exec_path": audit_exec_path,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Inverse rerun smoke missing {key} in run_record")
    if not Path(str(audit_dir)).exists():
        raise RuntimeError("Inverse rerun smoke audit_dir does not exist")
    if not Path(str(audit_report_path)).exists():
        raise RuntimeError("Inverse rerun smoke missing audit report.md")
    if not Path(str(audit_diff_path)).exists():
        raise RuntimeError("Inverse rerun smoke missing audit diff.json")
    if not Path(str(audit_exec_path)).exists():
        raise RuntimeError("Inverse rerun smoke missing audit exec.json")

    _validate_tick_event_present(out_dir, "INVERSE_DIFF_OK")
    inbox_text = (out_dir / "inbox" / "topk.md").read_text(encoding="utf-8")
    if "Audit: `OK`" not in inbox_text:
        raise RuntimeError("Inverse rerun smoke inbox missing Audit OK line")
    if "Audit Report:" not in inbox_text or "report.md" not in inbox_text:
        raise RuntimeError("Inverse rerun smoke inbox missing audit report pointer")


def _validate_subprocess_logs(out_dir: Path) -> None:
    run_records_dir = out_dir / "run_records"
    for file_path in sorted(run_records_dir.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        bundle_dir = Path(payload["bundle_path"])
        logs_dir = bundle_dir / "logs"
        stdout_path = logs_dir / "stdout.txt"
        stderr_path = logs_dir / "stderr.txt"
        exec_path = logs_dir / "exec.json"

        if not stdout_path.exists():
            raise RuntimeError(f"Missing stdout log for {file_path.name}")
        if not stderr_path.exists():
            raise RuntimeError(f"Missing stderr log for {file_path.name}")
        if not exec_path.exists():
            raise RuntimeError(f"Missing exec log for {file_path.name}")

        exec_payload = json.loads(exec_path.read_text(encoding="utf-8"))
        if exec_payload.get("cmd_mode") != "list":
            raise RuntimeError(f"Expected cmd_mode=list for {file_path.name}")
        if "duration_ms" not in exec_payload:
            raise RuntimeError(f"Missing duration_ms in exec log for {file_path.name}")


def _build_subprocess_smoke_command() -> list[str]:
    code = (
        "import json,os,pathlib;"
        "bundle=pathlib.Path(os.environ['AUTOPILOT_BUNDLE_DIR']);"
        "meta={'adapter':'subprocess_smoke','ok':True};"
        "(bundle/'metadata.json').write_text(json.dumps(meta),encoding='utf-8');"
        "report={'gate_result':'PASS','passed':True,'checks':[{'name':'subprocess_smoke','status':'PASS'}]};"
        "(bundle/'validation_report.json').write_text(json.dumps(report),encoding='utf-8')"
    )
    return [sys.executable, "-c", code]


def _build_routing_subprocess_command() -> list[str]:
    code = (
        "import json,os,pathlib;"
        "bundle=pathlib.Path(os.environ['AUTOPILOT_BUNDLE_DIR']);"
        "meta={'adapter':'routing_subprocess_smoke','ok':True};"
        "(bundle/'metadata.json').write_text(json.dumps(meta),encoding='utf-8');"
        "report={'gate_result':'PASS','passed':True,'checks':[{'name':'routing_subprocess','status':'PASS'}]};"
        "(bundle/'validation_report.json').write_text(json.dumps(report),encoding='utf-8')"
    )
    return [sys.executable, "-c", code]


def _build_inverse_stub_command() -> list[str]:
    code = (
        "import json,os,pathlib;"
        "d=pathlib.Path(os.environ['AUTOPILOT_AUDIT_OUT_DIR']);"
        "d.mkdir(parents=True,exist_ok=True);"
        "(d/'diff.json').write_text(json.dumps({'ok':True}),encoding='utf-8');"
        "(d/'report.md').write_text('# audit ok\\n',encoding='utf-8')"
    )
    return [sys.executable, "-c", code]


def _validate_routing_outputs(out_dir: Path) -> None:
    run_records_dir = out_dir / "run_records"
    cand1_path = run_records_dir / "cand-1.json"
    cand2_path = run_records_dir / "cand-2.json"

    if not cand1_path.exists() or not cand2_path.exists():
        raise RuntimeError("Routing smoke expected cand-1.json and cand-2.json")

    cand1 = json.loads(cand1_path.read_text(encoding="utf-8"))
    cand2 = json.loads(cand2_path.read_text(encoding="utf-8"))
    if cand1.get("gate_result") != "PASS" or cand2.get("gate_result") != "PASS":
        raise RuntimeError("Routing smoke expected PASS for both candidates")

    bundle1 = Path(str(cand1["bundle_path"]))
    bundle2 = Path(str(cand2["bundle_path"]))
    validation1 = json.loads((bundle1 / "validation_report.json").read_text(encoding="utf-8"))
    validation2 = json.loads((bundle2 / "validation_report.json").read_text(encoding="utf-8"))

    checks1 = validation1.get("checks", [])
    checks2 = validation2.get("checks", [])
    check1_name = checks1[0].get("name") if checks1 else ""
    check2_name = checks2[0].get("name") if checks2 else ""

    if check1_name != "routing_subprocess":
        raise RuntimeError(f"cand-1 should be routed subprocess, got check={check1_name}")
    if check2_name != "fake_validation":
        raise RuntimeError(f"cand-2 should fall back to fake kernel, got check={check2_name}")

    if not (bundle1 / "logs" / "exec.json").exists():
        raise RuntimeError("cand-1 routed subprocess missing logs/exec.json")


def _validate_slot_ab_example_pending_outputs(out_dir: Path) -> tuple[Path, Path]:
    run_records_dir = out_dir / "run_records"
    cand1_path = run_records_dir / "cand-1.json"
    cand2_path = run_records_dir / "cand-2.json"
    if not cand1_path.exists() or not cand2_path.exists():
        raise RuntimeError("Slot-A+Slot-B smoke expected cand-1.json and cand-2.json")

    cand1 = json.loads(cand1_path.read_text(encoding="utf-8"))
    cand2 = json.loads(cand2_path.read_text(encoding="utf-8"))
    if cand1.get("gate_result") != "PASS":
        raise RuntimeError("Slot-A candidate should be PASS at submit time")
    if cand2.get("gate_result") != "PENDING":
        raise RuntimeError("Slot-B candidate should be PENDING at submit time")

    bundle1 = Path(str(cand1["bundle_path"]))
    bundle2 = Path(str(cand2["bundle_path"]))

    a2_path = bundle1 / "artifacts" / "slot_a" / "a2_prompt.md"
    a3_path = bundle1 / "artifacts" / "slot_a" / "a3_prompt.md"
    if not a2_path.exists() or not a3_path.exists():
        raise RuntimeError("Slot-A bundle missing a2_prompt.md or a3_prompt.md")

    manual_job_path = bundle2 / "artifacts" / "slot_b" / "manual_bundle_job.json"
    readme_path = bundle2 / "artifacts" / "slot_b" / "README.md"
    solver_log_path = bundle2 / "solver_log.txt"
    if not manual_job_path.exists() or not readme_path.exists():
        raise RuntimeError("Slot-B bundle missing manual_bundle_job.json or README.md")
    if not solver_log_path.exists():
        raise RuntimeError("Slot-B bundle missing solver_log.txt")

    validation1 = json.loads((bundle1 / "validation_report.json").read_text(encoding="utf-8"))
    validation2 = json.loads((bundle2 / "validation_report.json").read_text(encoding="utf-8"))
    if str(validation1.get("gate_result", "")).upper() != "PASS":
        raise RuntimeError("Slot-A bundle validation_report gate_result is not PASS")
    if str(validation2.get("gate_result", "")).upper() != "PENDING":
        raise RuntimeError("Slot-B bundle validation_report gate_result is not PENDING")
    done_marker = str(validation2.get("done_marker", "")).strip()
    if done_marker != "outputs/outputs_manifest.json":
        raise RuntimeError(f"Slot-B done_marker unexpected: {done_marker}")

    inbox_text = (out_dir / "inbox" / "topk.md").read_text(encoding="utf-8")
    if "Execution Type" not in inbox_text:
        raise RuntimeError("Inbox missing Execution Type at submit time")
    if "Next Action" not in inbox_text:
        raise RuntimeError("Inbox missing Next Action for pending candidate")

    return bundle1, bundle2


def _validate_slot_ab_after_tick(out_dir: Path, bundle1: Path, bundle2: Path) -> None:
    run_records_dir = out_dir / "run_records"
    cand1 = json.loads((run_records_dir / "cand-1.json").read_text(encoding="utf-8"))
    cand2 = json.loads((run_records_dir / "cand-2.json").read_text(encoding="utf-8"))
    if cand1.get("gate_result") != "PASS" or cand2.get("gate_result") != "PASS":
        raise RuntimeError("Slot-A+Slot-B smoke expected PASS for both candidates after tick")

    validation1 = json.loads((bundle1 / "validation_report.json").read_text(encoding="utf-8"))
    validation2 = json.loads((bundle2 / "validation_report.json").read_text(encoding="utf-8"))
    if str(validation1.get("gate_result", "")).upper() != "PASS":
        raise RuntimeError("Slot-A bundle validation_report gate_result should remain PASS after tick")
    if str(validation2.get("gate_result", "")).upper() != "PASS":
        raise RuntimeError("Slot-B bundle validation_report gate_result should be PASS after tick")

    checks2 = validation2.get("checks", [])
    if len(checks2) < 3:
        raise RuntimeError("Slot-B post-tick validation_report missing checks")
    if checks2[0].get("name") != "manifest_present" or checks2[0].get("status") != "PASS":
        raise RuntimeError("Slot-B post-tick manifest_present check should be PASS")
    if checks2[1].get("name") != "output_files_present" or checks2[1].get("status") != "PASS":
        raise RuntimeError("Slot-B post-tick output_files_present check should be PASS")
    if checks2[2].get("name") != "output_files_verified" or checks2[2].get("status") != "PASS":
        raise RuntimeError("Slot-B post-tick output_files_verified check should be PASS")
    files2 = checks2[1].get("files")
    if not isinstance(files2, list) or "result.txt" not in files2:
        raise RuntimeError("Slot-B post-tick output_files_present should list result.txt")
    mismatches2 = checks2[2].get("mismatches")
    if not isinstance(mismatches2, list) or mismatches2:
        raise RuntimeError("Slot-B post-tick output_files_verified should have empty mismatches")

    inbox_text = (out_dir / "inbox" / "topk.md").read_text(encoding="utf-8")
    if "Execution Type" not in inbox_text:
        raise RuntimeError("Inbox missing Execution Type after tick")
    if "slot_b" not in inbox_text:
        raise RuntimeError("Inbox missing slot_b record after tick")
    if "- Gate: `PASS`" not in inbox_text:
        raise RuntimeError("Inbox missing PASS gate line after tick")


def _validate_slot_ab_after_hash_mismatch_tick(out_dir: Path, bundle2: Path) -> None:
    run_records_dir = out_dir / "run_records"
    cand2 = json.loads((run_records_dir / "cand-2.json").read_text(encoding="utf-8"))
    if cand2.get("gate_result") != "PENDING":
        raise RuntimeError("Slot-B candidate should remain PENDING when manifest hash mismatches")
    next_action = str(cand2.get("next_action", ""))
    if "hash mismatches" not in next_action or "rerun tick" not in next_action:
        raise RuntimeError("Slot-B pending next_action should mention hash mismatches and rerun tick")

    validation2 = json.loads((bundle2 / "validation_report.json").read_text(encoding="utf-8"))
    if str(validation2.get("gate_result", "")).upper() != "PENDING":
        raise RuntimeError("Slot-B validation_report should remain PENDING when hash mismatches")
    if str(validation2.get("status", "")).upper() != "OUTPUT_FILE_HASH_MISMATCH":
        raise RuntimeError("Slot-B validation_report status should be OUTPUT_FILE_HASH_MISMATCH")
    checks2 = validation2.get("checks", [])
    if len(checks2) < 3:
        raise RuntimeError("Slot-B hash-mismatch validation_report missing checks")
    if checks2[0].get("name") != "manifest_present" or checks2[0].get("status") != "PASS":
        raise RuntimeError("Slot-B hash-mismatch check manifest_present should be PASS")
    if checks2[1].get("name") != "output_files_present" or checks2[1].get("status") != "PASS":
        raise RuntimeError("Slot-B hash-mismatch check output_files_present should be PASS")
    if checks2[2].get("name") != "output_files_verified" or checks2[2].get("status") != "FAIL":
        raise RuntimeError("Slot-B hash-mismatch check output_files_verified should be FAIL")
    mismatches = checks2[2].get("mismatches")
    if not isinstance(mismatches, list) or not mismatches:
        raise RuntimeError("Slot-B hash-mismatch check should include mismatches")
    first = mismatches[0]
    if first.get("path") != "result.txt":
        raise RuntimeError("Slot-B hash-mismatch mismatch path should be result.txt")
    if first.get("check") != "sha256":
        raise RuntimeError("Slot-B hash-mismatch should be on sha256")
    if str(first.get("expected", "")) == str(first.get("actual", "")):
        raise RuntimeError("Slot-B hash-mismatch expected/actual should differ")

    inbox_text = (out_dir / "inbox" / "topk.md").read_text(encoding="utf-8")
    if "Next Action" not in inbox_text or "hash mismatches" not in inbox_text:
        raise RuntimeError("Inbox should show pending next_action mentioning hash mismatches")


def main() -> int:
    smoke_root: Path | None = None
    try:
        smoke_base = Path(__file__).resolve().parent / ".smoke_tmp"
        smoke_base.mkdir(parents=True, exist_ok=True)
        session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        smoke_root = smoke_base / f"autopilot_smoke_{session_id}"
        smoke_root.mkdir(parents=True, exist_ok=True)
        spec_path = smoke_root / "program_spec.json"

        spec_payload = {
            "program_id": "smoke-program",
            "goal": "Verify minimal autopilot vertical slice",
            "constraints": ["windows-pathlib", "p0"],
            "max_candidates": 2,
        }
        spec_path.write_text(json.dumps(spec_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        fake_out_dir = smoke_root / "out_fake"
        rc = cli_main(
            [
                "run",
                "--spec",
                str(spec_path),
                "--out",
                str(fake_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Fake kernel CLI returned non-zero exit code: {rc}")
        _validate_outputs(fake_out_dir)

        subprocess_out_dir = smoke_root / "out_subprocess"
        subprocess_cmd = _build_subprocess_smoke_command()
        rc = cli_main(
            [
                "run",
                "--spec",
                str(spec_path),
                "--out",
                str(subprocess_out_dir),
                "--kernel",
                "subprocess",
                "--cmd",
                json.dumps(subprocess_cmd),
                "--timeout-seconds",
                "5",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Subprocess kernel CLI returned non-zero exit code: {rc}")
        _validate_outputs(subprocess_out_dir)
        _validate_subprocess_logs(subprocess_out_dir)

        routing_out_dir = smoke_root / "out_routing"
        routing_subprocess_cmd = _build_routing_subprocess_command()
        routing_spec_path = smoke_root / "program_spec_routing.json"
        routing_spec_payload = {
            "program_id": "smoke-routing",
            "goal": "Verify candidate-level executor_map routing",
            "constraints": ["routing", "executor_map"],
            "max_candidates": 2,
            "execution_types": ["slot_a", "pure_code"],
            "executor_map": {
                "slot_a": {
                    "kernel": "subprocess",
                    "cmd": routing_subprocess_cmd,
                    "timeout_seconds": 5,
                }
            },
        }
        routing_spec_path.write_text(
            json.dumps(routing_spec_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "run",
                "--spec",
                str(routing_spec_path),
                "--out",
                str(routing_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Routing kernel CLI returned non-zero exit code: {rc}")
        _validate_outputs(routing_out_dir)
        _validate_routing_outputs(routing_out_dir)

        repeat_out_dir = smoke_root / "out_repeat_history"
        repeat_spec_path = smoke_root / "program_spec_repeat.json"
        repeat_spec_payload = {
            "program_id": "smoke-repeat",
            "goal": "Verify append-only versioned bundles and per-candidate history",
            "constraints": ["append-only", "history"],
            "max_candidates": 1,
        }
        repeat_spec_path.write_text(
            json.dumps(repeat_spec_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "run",
                "--spec",
                str(repeat_spec_path),
                "--out",
                str(repeat_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Repeat history first run CLI returned non-zero exit code: {rc}")
        rc = cli_main(
            [
                "run",
                "--spec",
                str(repeat_spec_path),
                "--out",
                str(repeat_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Repeat history second run CLI returned non-zero exit code: {rc}")
        _validate_outputs(repeat_out_dir)
        _validate_versioned_bundle_history(repeat_out_dir, program_id="smoke-repeat")

        inverse_out_dir = smoke_root / "out_inverse_rerun"
        inverse_spec_path = smoke_root / "program_spec_inverse_rerun.json"
        inverse_spec_payload = {
            "program_id": "smoke-inverse",
            "goal": "Verify inverse diff audit on rerun",
            "constraints": ["inverse", "audit"],
            "max_candidates": 1,
            "inverse": {
                "enabled": True,
                "cmd": _build_inverse_stub_command(),
                "timeout_seconds": 10,
            },
        }
        inverse_spec_path.write_text(
            json.dumps(inverse_spec_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rc = cli_main(
            [
                "run",
                "--spec",
                str(inverse_spec_path),
                "--out",
                str(inverse_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Inverse rerun first run CLI returned non-zero exit code: {rc}")
        rc = cli_main(
            [
                "run",
                "--spec",
                str(inverse_spec_path),
                "--out",
                str(inverse_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Inverse rerun second run CLI returned non-zero exit code: {rc}")
        _validate_outputs(inverse_out_dir)
        _validate_inverse_audit_rerun(inverse_out_dir)

        slot_ab_out_dir = smoke_root / "out_slot_ab_hash_ok"
        rc = cli_main(
            [
                "run",
                "--spec",
                "sop/autopilot/examples/program_spec_slot_ab.json",
                "--out",
                str(slot_ab_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Slot-A+Slot-B example CLI returned non-zero exit code: {rc}")
        _validate_outputs(slot_ab_out_dir)
        slot_a_bundle, slot_b_bundle = _validate_slot_ab_example_pending_outputs(slot_ab_out_dir)
        _validate_dispatch_submit_events(slot_ab_out_dir, minimum_count=2)

        result_file_path = slot_b_bundle / "outputs" / "result.txt"
        result_content = b"ok\n"
        result_file_path.write_bytes(result_content)
        result_hash = hashlib.sha256(result_content).hexdigest()
        done_marker_path = slot_b_bundle / "outputs" / "outputs_manifest.json"
        done_marker_path.parent.mkdir(parents=True, exist_ok=True)
        done_marker_path.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "result.txt",
                            "size": len(result_content),
                            "sha256": result_hash,
                        }
                    ],
                    "note": "done",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        rc = cli_main(
            [
                "tick",
                "--out",
                str(slot_ab_out_dir),
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Slot-A+Slot-B tick CLI returned non-zero exit code: {rc}")
        _validate_slot_ab_after_tick(slot_ab_out_dir, slot_a_bundle, slot_b_bundle)
        _validate_tick_event_present(slot_ab_out_dir, "TICK_PROMOTE_PASS")

        slot_ab_hash_mismatch_out_dir = smoke_root / "out_slot_ab_hash_mismatch"
        rc = cli_main(
            [
                "run",
                "--spec",
                "sop/autopilot/examples/program_spec_slot_ab.json",
                "--out",
                str(slot_ab_hash_mismatch_out_dir),
                "--kernel",
                "fake",
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Slot-A+Slot-B hash mismatch CLI returned non-zero exit code: {rc}")
        _validate_outputs(slot_ab_hash_mismatch_out_dir)
        _, slot_b_mismatch_bundle = _validate_slot_ab_example_pending_outputs(slot_ab_hash_mismatch_out_dir)
        _validate_dispatch_submit_events(slot_ab_hash_mismatch_out_dir, minimum_count=2)

        mismatch_file_path = slot_b_mismatch_bundle / "outputs" / "result.txt"
        mismatch_content = b"ok\n"
        mismatch_file_path.write_bytes(mismatch_content)
        mismatch_manifest_path = slot_b_mismatch_bundle / "outputs" / "outputs_manifest.json"
        mismatch_manifest_path.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "result.txt",
                            "size": len(mismatch_content),
                            "sha256": "0" * 64,
                        }
                    ],
                    "note": "wrong hash",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        rc = cli_main(
            [
                "tick",
                "--out",
                str(slot_ab_hash_mismatch_out_dir),
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Slot-A+Slot-B hash mismatch tick CLI returned non-zero exit code: {rc}")
        _validate_slot_ab_after_hash_mismatch_tick(slot_ab_hash_mismatch_out_dir, slot_b_mismatch_bundle)
        _validate_tick_event_present(slot_ab_hash_mismatch_out_dir, "TICK_OUTPUT_HASH_MISMATCH")

        mismatch_event_count_before = _count_ledger_event_type(
            slot_ab_hash_mismatch_out_dir, "TICK_OUTPUT_HASH_MISMATCH"
        )
        rc = cli_main(
            [
                "tick",
                "--out",
                str(slot_ab_hash_mismatch_out_dir),
            ]
        )
        if rc != 0:
            raise RuntimeError(
                f"Slot-A+Slot-B hash mismatch second tick CLI returned non-zero exit code: {rc}"
            )
        mismatch_event_count_after = _count_ledger_event_type(
            slot_ab_hash_mismatch_out_dir, "TICK_OUTPUT_HASH_MISMATCH"
        )
        if mismatch_event_count_after != mismatch_event_count_before:
            raise RuntimeError(
                "Tick should not emit duplicate TICK_OUTPUT_HASH_MISMATCH without state change"
            )

        print(
            "SMOKE PASS: adapters, routing, append-only history, inverse audit, and Slot-B tick validation are runnable."
        )
        return 0
    except Exception as exc:
        print(f"SMOKE FAIL: {exc}")
        return 1
    finally:
        if smoke_root is not None and smoke_root.exists():
            shutil.rmtree(smoke_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
