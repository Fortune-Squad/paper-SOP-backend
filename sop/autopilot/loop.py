from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import random
import time

from .adapters import FakeKernelAdapter, KernelAdapter, SubprocessKernelAdapter
from .command_utils import substitute_command_tokens
from .contracts import with_schema_version
from .inverse_audit import run_inverse_diff
from .ledger import JsonlLedger, append_event
from .schemas import CandidateCard, ExecutorConfig, ProgramSpec, RetryPolicy, RunRecord
from .validation import write_validation_report


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutopilotLoop:
    def __init__(
        self,
        spec: ProgramSpec,
        out_dir: str | Path,
        kernel_adapter: KernelAdapter | None = None,
        default_subprocess_timeout_seconds: int | None = None,
    ) -> None:
        self.spec = spec
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.ledger = JsonlLedger(self.out_dir / "program_ledger.jsonl")
        self.run_records_dir = self.out_dir / "run_records"
        self.run_records_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir = self.out_dir / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        default_adapter = FakeKernelAdapter()
        self.kernel = kernel_adapter or default_adapter
        self.default_subprocess_timeout_seconds = default_subprocess_timeout_seconds

    def run(self) -> list[RunRecord]:
        candidates = self.generate_candidates()
        planned = self.plan(candidates)
        run_records = self.dispatch_collect_and_score(planned)
        self.write_inbox(run_records)
        return run_records

    def generate_candidates(self) -> list[CandidateCard]:
        candidate_count = max(self.spec.max_candidates, 1)
        execution_types = self.spec.execution_types or ["slot_a"]
        cards: list[CandidateCard] = []
        for index in range(candidate_count):
            candidate_id = f"cand-{index + 1}"
            execution_type = execution_types[index] if index < len(execution_types) else "slot_a"
            constraints_hint = ", ".join(self.spec.constraints) if self.spec.constraints else "none"
            cards.append(
                CandidateCard(
                    id=candidate_id,
                    hypothesis=f"Candidate {index + 1} for goal: {self.spec.goal}",
                    plan=(
                        "Run minimal validation path via routed kernel; "
                        f"execution_type={execution_type}; constraints={constraints_hint}"
                    ),
                    required_artifacts=["metadata.json", "validation_report.json"],
                    eval_checks=["gate_result == PASS"],
                    priority=candidate_count - index,
                    execution_type=execution_type,
                )
            )

        self.ledger.append(
            {
                "ts": _utc_now(),
                "event": "generate",
                "program_id": self.spec.program_id,
                "count": len(cards),
                "candidate_ids": [card.id for card in cards],
                "execution_types": [card.execution_type for card in cards],
            }
        )
        return cards

    def plan(self, candidates: list[CandidateCard]) -> list[CandidateCard]:
        planned = sorted(candidates, key=lambda card: card.priority, reverse=True)
        self.ledger.append(
            {
                "ts": _utc_now(),
                "event": "plan",
                "program_id": self.spec.program_id,
                "order": [card.id for card in planned],
            }
        )
        return planned

    def dispatch_collect_and_score(self, planned: list[CandidateCard]) -> list[RunRecord]:
        run_records: list[RunRecord] = []
        for card in planned:
            dispatch_id = f"{self.spec.program_id}-{card.id}"
            record_path = self.run_records_dir / f"{card.id}.json"
            previous_record = self._read_validation_payload(record_path)
            previous_bundle_dir = self._normalize_previous_bundle_dir(previous_record)
            bundle_history = self._normalize_bundle_history(previous_record.get("bundle_history"))
            self.ledger.append(
                {
                    "ts": _utc_now(),
                    "event": "dispatch",
                    "program_id": self.spec.program_id,
                    "candidate_id": card.id,
                    "execution_type": card.execution_type,
                    "run_id": dispatch_id,
                }
            )

            executor_cfg = self.spec.executor_map.get(card.execution_type)
            adapter, route_error = self._resolve_adapter(card)
            retry_count = 0
            if route_error is not None:
                bundle_dir = self._write_routing_failure_bundle(
                    candidate_card=card,
                    error_type="executor_config_error",
                    error_message=route_error,
                )
            else:
                assert adapter is not None
                retry_policy = self.spec.retry_policy
                max_attempts = retry_policy.max_attempts if retry_policy else 0
                bundle_dir = None
                for attempt in range(max_attempts + 1):
                    try:
                        bundle_dir = adapter.submit(
                            program_spec=self.spec,
                            candidate_card=card,
                            out_dir=self.out_dir,
                        )
                        break
                    except Exception as exc:  # pragma: no cover - defensive
                        error_message = str(exc)
                        if (
                            retry_policy is not None
                            and attempt < max_attempts
                            and retry_policy.is_retryable(error_message)
                        ):
                            retry_count = attempt + 1
                            delay = retry_policy.delay_for_attempt(retry_count)
                            append_event(self.out_dir, {
                                "ts": _utc_now(),
                                "event_type": "retry_scheduled",
                                "program_id": self.spec.program_id,
                                "candidate_id": card.id,
                                "run_id": dispatch_id,
                                "attempt": retry_count,
                                "delay_seconds": delay,
                                "error": error_message,
                            })
                            time.sleep(delay)
                            continue
                        bundle_dir = self._write_routing_failure_bundle(
                            candidate_card=card,
                            error_type="adapter_exception",
                            error_message=error_message,
                        )
                        break
            run_id = self._read_run_id_from_bundle_dir(bundle_dir)

            gate_result = self._read_gate_result(bundle_dir / "validation_report.json")
            score = 1.0 if gate_result == "PASS" else 0.0
            next_action = self._read_next_action(bundle_dir / "validation_report.json", gate_result)
            updated_history = list(bundle_history)
            if previous_bundle_dir:
                if not updated_history or updated_history[-1] != previous_bundle_dir:
                    updated_history.append(previous_bundle_dir)

            record = RunRecord(
                run_id=run_id,
                program_id=self.spec.program_id,
                candidate_id=card.id,
                bundle_path=str(bundle_dir),
                gate_result=gate_result,
                score=score,
                execution_type=card.execution_type,
                next_action=next_action,
                bundle_history=updated_history,
                previous_bundle_dir=previous_bundle_dir,
                retry_count=retry_count,
                audit_status="SKIP",
            )

            with record_path.open("w", encoding="utf-8") as handle:
                json.dump(record.to_dict(), handle, ensure_ascii=False, indent=2)

            self._append_dispatch_submit_event(
                candidate_card=card,
                run_id=run_id,
                bundle_dir=bundle_dir,
                adapter=adapter,
                executor_cfg=executor_cfg,
                route_error=route_error,
                previous_bundle_dir=previous_bundle_dir,
                gate_result=gate_result,
            )
            record = self._run_inverse_audit_for_record(
                candidate_card=card,
                record=record,
                record_path=record_path,
            )
            run_records.append(record)

            self.ledger.append(
                {
                    "ts": _utc_now(),
                    "event": "collect",
                    "program_id": self.spec.program_id,
                    "candidate_id": card.id,
                    "run_id": run_id,
                    "bundle_path": str(bundle_dir),
                    "gate_result": gate_result,
                }
            )
            self.ledger.append(
                {
                    "ts": _utc_now(),
                    "event": "score",
                    "program_id": self.spec.program_id,
                    "candidate_id": card.id,
                    "run_id": run_id,
                    "score": score,
                }
            )

        return run_records

    def write_inbox(self, run_records: list[RunRecord]) -> Path:
        ranked = sorted(run_records, key=lambda record: record.score, reverse=True)
        top_k = ranked[: min(len(ranked), max(1, self.spec.max_candidates))]
        inbox_path = self._write_inbox_file(
            out_dir=self.out_dir,
            program_id=self.spec.program_id,
            goal=self.spec.goal,
            run_records=top_k,
        )
        self.ledger.append(
            {
                "ts": _utc_now(),
                "event": "inbox",
                "program_id": self.spec.program_id,
                "path": str(inbox_path),
                "count": len(top_k),
            }
        )
        return inbox_path

    @staticmethod
    def _read_gate_result(validation_report_path: Path) -> str:
        with validation_report_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        gate = payload.get("gate_result", "FAIL")
        return str(gate).upper()

    @staticmethod
    def _read_validation_payload(validation_report_path: Path) -> dict[str, Any]:
        if not validation_report_path.exists():
            return {}
        try:
            payload = json.loads(validation_report_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            return with_schema_version(payload)
        return {}

    @staticmethod
    def _read_next_action(validation_report_path: Path, gate_result: str) -> str | None:
        if gate_result != "PENDING":
            return None
        payload = AutopilotLoop._read_validation_payload(validation_report_path)
        status = str(payload.get("status", "")).upper()
        if status == "INVALID_OUTPUTS_MANIFEST":
            return (
                "Fix outputs_manifest.json: invalid JSON; "
                "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
            )
        if status == "MALFORMED_OUTPUTS_MANIFEST":
            return (
                "Fix outputs_manifest.json schema: include files list; "
                "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
            )
        if status == "MISSING_OUTPUT_FILES":
            missing_files = payload.get("missing_files")
            if isinstance(missing_files, list) and missing_files:
                missing_joined = ", ".join(str(item) for item in missing_files)
                return (
                    f"Add missing files under outputs/: {missing_joined}; "
                    "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                )
        if status in {"OUTPUT_FILE_SIZE_MISMATCH", "OUTPUT_FILE_HASH_MISMATCH"}:
            mismatches = payload.get("mismatches")
            if isinstance(mismatches, list) and mismatches:
                details = AutopilotLoop._format_mismatch_details(mismatches)
                return (
                    f"Resolve output mismatches: {details}; "
                    "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                )
            return (
                "Resolve output mismatches; "
                "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
            )
        done_marker = payload.get("done_marker")
        if isinstance(done_marker, str) and done_marker.strip():
            return f"Create done marker: {done_marker.strip()}"
        return "Create done marker: outputs/outputs_manifest.json"

    @staticmethod
    def _load_outputs_manifest(
        marker_path: Path,
    ) -> tuple[list[dict[str, Any]] | None, str | None, str | None]:
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return None, "INVALID_OUTPUTS_MANIFEST", f"outputs manifest JSON parse error: {exc}"
        except OSError as exc:
            return None, "INVALID_OUTPUTS_MANIFEST", f"failed to read outputs manifest: {exc}"

        if not isinstance(payload, dict):
            return None, "MALFORMED_OUTPUTS_MANIFEST", "outputs manifest must be a JSON object"

        files = payload.get("files")
        if not isinstance(files, list):
            return None, "MALFORMED_OUTPUTS_MANIFEST", "outputs manifest must contain 'files' as list"

        normalized_entries: list[dict[str, Any]] = []
        hex_chars = set("0123456789abcdef")
        for index, item in enumerate(files):
            entry: dict[str, Any]
            if isinstance(item, str):
                rel_value = item.strip()
                if not rel_value:
                    return None, "MALFORMED_OUTPUTS_MANIFEST", (
                        f"outputs manifest files[{index}] must be a non-empty string"
                    )
                entry = {"path": rel_value}
            elif isinstance(item, dict):
                raw_path = item.get("path")
                if not isinstance(raw_path, str) or not raw_path.strip():
                    return None, "MALFORMED_OUTPUTS_MANIFEST", (
                        f"outputs manifest files[{index}].path must be a non-empty string"
                    )
                entry = {"path": raw_path.strip()}

                if "size" in item:
                    size_value = item.get("size")
                    if (
                        not isinstance(size_value, int)
                        or isinstance(size_value, bool)
                        or size_value < 0
                    ):
                        return None, "MALFORMED_OUTPUTS_MANIFEST", (
                            f"outputs manifest files[{index}].size must be a non-negative integer"
                        )
                    entry["size"] = size_value

                if "sha256" in item:
                    hash_value = item.get("sha256")
                    if not isinstance(hash_value, str) or not hash_value.strip():
                        return None, "MALFORMED_OUTPUTS_MANIFEST", (
                            f"outputs manifest files[{index}].sha256 must be a non-empty hex string"
                        )
                    normalized_hash = hash_value.strip().lower()
                    if len(normalized_hash) != 64 or any(ch not in hex_chars for ch in normalized_hash):
                        return None, "MALFORMED_OUTPUTS_MANIFEST", (
                            f"outputs manifest files[{index}].sha256 must be 64 lowercase/uppercase hex chars"
                        )
                    entry["sha256"] = normalized_hash
            else:
                return None, "MALFORMED_OUTPUTS_MANIFEST", (
                    f"outputs manifest files[{index}] must be a string or object"
                )

            rel_path = Path(str(entry["path"]))
            if rel_path.is_absolute() or ".." in rel_path.parts:
                return None, "MALFORMED_OUTPUTS_MANIFEST", (
                    f"outputs manifest files[{index}] path must be relative under outputs/"
                )
            normalized_entries.append(entry)

        return normalized_entries, None, None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _format_mismatch_details(mismatches: list[dict[str, Any]]) -> str:
        snippets: list[str] = []
        for item in mismatches[:3]:
            path = str(item.get("path", "unknown"))
            check = str(item.get("kind", item.get("check", "value")))
            expected = item.get("expected")
            actual = item.get("actual")
            snippets.append(f"{path} ({check}: expected={expected}, actual={actual})")
        summary = "; ".join(snippets)
        if len(mismatches) > 3:
            return f"{summary}; and {len(mismatches) - 3} more"
        return summary

    @staticmethod
    def _normalize_state_text(value: str | None) -> str:
        if not value:
            return ""
        return str(value).strip().upper()

    @staticmethod
    def _normalize_next_action(value: str | None) -> str:
        if not value:
            return ""
        return str(value).strip()

    @staticmethod
    def _map_status_to_event_type(gate_result: str, status: str) -> str | None:
        normalized_gate = AutopilotLoop._normalize_state_text(gate_result)
        normalized_status = AutopilotLoop._normalize_state_text(status)
        if normalized_gate == "PASS":
            return "TICK_PROMOTE_PASS"
        if normalized_status == "INVALID_OUTPUTS_MANIFEST":
            return "TICK_MANIFEST_INVALID"
        if normalized_status == "MALFORMED_OUTPUTS_MANIFEST":
            return "TICK_MANIFEST_MALFORMED"
        if normalized_status == "WAITING_EXTERNAL_OUTPUTS":
            return "TICK_MANIFEST_INCOMPLETE"
        if normalized_status == "MISSING_OUTPUT_FILES":
            return "TICK_MANIFEST_INCOMPLETE"
        if normalized_status == "OUTPUT_FILE_SIZE_MISMATCH":
            return "TICK_OUTPUT_SIZE_MISMATCH"
        if normalized_status == "OUTPUT_FILE_HASH_MISMATCH":
            return "TICK_OUTPUT_HASH_MISMATCH"
        return None

    @staticmethod
    def _coerce_mismatches_for_event(mismatches: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in mismatches:
            kind = str(item.get("kind", item.get("check", ""))).strip().lower()
            if kind not in {"size", "sha256"}:
                kind = "size" if "size" in str(item.get("check", "")).lower() else "sha256"
            normalized.append(
                {
                    "path": str(item.get("path", "")),
                    "kind": kind,
                    "expected": item.get("expected"),
                    "actual": item.get("actual"),
                }
            )
        return normalized

    @staticmethod
    def _normalize_previous_bundle_dir(record_payload: dict[str, Any]) -> str | None:
        raw = record_payload.get("bundle_path")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return None

    @staticmethod
    def _normalize_bundle_history(raw: Any) -> list[str]:
        if not isinstance(raw, list):
            return []
        history: list[str] = []
        for item in raw:
            if isinstance(item, str):
                value = item.strip()
                if value:
                    history.append(value)
        return history

    @staticmethod
    def _new_run_id() -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y%m%d_%H%M%S_%f_") + f"{random.getrandbits(16):04x}"

    @classmethod
    def _read_run_id_from_bundle_dir(cls, bundle_dir: Path) -> str:
        metadata_payload = cls._read_validation_payload(bundle_dir / "metadata.json")
        metadata_run_id = metadata_payload.get("run_id")
        if isinstance(metadata_run_id, str) and metadata_run_id.strip():
            return metadata_run_id.strip()

        validation_payload = cls._read_validation_payload(bundle_dir / "validation_report.json")
        validation_run_id = validation_payload.get("run_id")
        if isinstance(validation_run_id, str) and validation_run_id.strip():
            return validation_run_id.strip()

        basename = bundle_dir.name
        if "-" in basename:
            inferred = basename.rsplit("-", 1)[-1].strip()
            if inferred:
                return inferred
        return cls._new_run_id()

    @staticmethod
    def _normalize_optional_str(value: Any) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized
        return None

    def _run_inverse_audit_for_record(
        self,
        candidate_card: CandidateCard,
        record: RunRecord,
        record_path: Path,
    ) -> RunRecord:
        if not self.spec.inverse.enabled:
            return record
        if not record.previous_bundle_dir:
            return record

        previous_bundle_dir = Path(record.previous_bundle_dir)
        current_bundle_dir = Path(record.bundle_path)
        audit_dir = current_bundle_dir / "audit"

        ok, details = run_inverse_diff(
            prev_bundle_dir=previous_bundle_dir,
            curr_bundle_dir=current_bundle_dir,
            inverse_cfg=self.spec.inverse,
            audit_dir=audit_dir,
        )
        record.audit_dir = str(audit_dir)
        record.audit_status = "OK" if ok else "FAIL"
        record.audit_report_path = self._normalize_optional_str(details.get("report_path"))
        record.audit_diff_path = self._normalize_optional_str(details.get("diff_path"))
        record.audit_exec_path = self._normalize_optional_str(details.get("exec_path"))

        with record_path.open("w", encoding="utf-8") as handle:
            json.dump(record.to_dict(), handle, ensure_ascii=False, indent=2)

        details_payload: dict[str, Any] = {
            "run_id": record.run_id,
            "previous_bundle_dir": record.previous_bundle_dir,
            "audit_dir": record.audit_dir,
            "report_path": record.audit_report_path,
            "diff_path": record.audit_diff_path,
            "exec_path": record.audit_exec_path,
            "returncode": details.get("returncode"),
        }
        if isinstance(details.get("warnings"), list):
            details_payload["warnings"] = details.get("warnings")
        if details.get("error_type"):
            details_payload["error_type"] = details.get("error_type")
        if details.get("error_message"):
            details_payload["error_message"] = details.get("error_message")

        event_type = "INVERSE_DIFF_OK" if ok else "INVERSE_DIFF_FAIL"
        event_payload = {
            "ts": _utc_now(),
            "event": event_type,
            "event_type": event_type,
            "program_id": record.program_id,
            "candidate_id": record.candidate_id,
            "execution_type": candidate_card.execution_type,
            "bundle_dir": record.bundle_path,
            "run_id": record.run_id,
            "gate_result": self._normalize_state_text(record.gate_result) or "FAIL",
            "status": record.audit_status or ("OK" if ok else "FAIL"),
            "details": details_payload,
        }
        append_event(self.out_dir, event_payload)
        return record

    def _append_dispatch_submit_event(
        self,
        candidate_card: CandidateCard,
        run_id: str,
        bundle_dir: Path,
        adapter: KernelAdapter | None,
        executor_cfg: ExecutorConfig | None,
        route_error: str | None,
        previous_bundle_dir: str | None,
        gate_result: str,
    ) -> None:
        kernel = "fake"
        cmd_mode = "string"
        cmd_file: str | None = None

        if executor_cfg is not None:
            kernel = executor_cfg.kernel
            if kernel == "subprocess":
                if executor_cfg.cmd_file:
                    cmd_mode = "list"
                    cmd_file = executor_cfg.cmd_file
                elif isinstance(executor_cfg.cmd, list):
                    cmd_mode = "list"
                elif isinstance(executor_cfg.cmd, str):
                    cmd_mode = "list" if executor_cfg.cmd.lstrip().startswith("[") else "string"

        if isinstance(adapter, SubprocessKernelAdapter):
            kernel = "subprocess"
            cmd_mode = adapter.cmd_mode
            if adapter.cmd_file:
                cmd_file = adapter.cmd_file
        elif isinstance(adapter, FakeKernelAdapter):
            kernel = "fake"
            cmd_mode = "string"
            cmd_file = None
        elif adapter is self.kernel and isinstance(self.kernel, SubprocessKernelAdapter):
            kernel = "subprocess"
            cmd_mode = self.kernel.cmd_mode
            if self.kernel.cmd_file:
                cmd_file = self.kernel.cmd_file

        details: dict[str, Any] = {
            "run_id": run_id,
            "kernel": kernel,
            "cmd_mode": cmd_mode,
        }
        if previous_bundle_dir:
            details["previous_bundle_dir"] = previous_bundle_dir
        if cmd_file:
            details["cmd_file"] = cmd_file
        if route_error:
            details["route_error"] = route_error

        status = "SUBMITTED" if route_error is None else "ROUTE_ERROR"
        normalized_gate = self._normalize_state_text(gate_result) or "PENDING"
        event_payload = {
            "ts": _utc_now(),
            "event": "DISPATCH_SUBMIT",
            "event_type": "DISPATCH_SUBMIT",
            "program_id": self.spec.program_id,
            "candidate_id": candidate_card.id,
            "execution_type": candidate_card.execution_type,
            "bundle_dir": str(bundle_dir),
            "run_id": run_id,
            "gate_result": normalized_gate,
            "status": status,
            "details": details,
        }
        append_event(self.out_dir, event_payload)

    @staticmethod
    def _display_relative_path(base_dir: Path, target: str) -> str:
        raw = Path(target)
        candidate = raw if raw.is_absolute() else (base_dir / raw)
        try:
            rel = candidate.resolve().relative_to(base_dir.resolve())
            return str(rel)
        except Exception:
            return str(raw)

    @staticmethod
    def _write_inbox_file(
        out_dir: str | Path,
        program_id: str,
        goal: str,
        run_records: list[RunRecord],
    ) -> Path:
        out_path = Path(out_dir)
        inbox_dir = out_path / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        inbox_path = inbox_dir / "topk.md"

        lines = [
            f"# Autopilot Inbox: {program_id}",
            "",
            f"Goal: {goal}",
            "",
            "## Top Candidates",
            "",
        ]
        for idx, record in enumerate(run_records, start=1):
            lines.extend(
                [
                    f"### {idx}. {record.candidate_id}",
                    f"- Run ID: `{record.run_id}`",
                    f"- Score: `{record.score:.2f}`",
                    f"- Execution Type: `{record.execution_type}`",
                    f"- Gate: `{record.gate_result}`",
                    f"- Bundle: `{record.bundle_path}`",
                ]
            )
            if record.gate_result == "PENDING" and record.next_action:
                lines.append(f"- Next Action: `{record.next_action}`")
            if record.audit_status:
                lines.append(f"- Audit: `{record.audit_status}`")
            if record.audit_report_path:
                report_display = AutopilotLoop._display_relative_path(out_path, record.audit_report_path)
                lines.append(f"- Audit Report: `{report_display}`")
            lines.append("")

        lines.extend(
            [
                "## Human Signoff",
                "",
                "- [ ] Approve top candidate",
                "- [ ] Request another run",
            ]
        )
        inbox_path.write_text("\n".join(lines), encoding="utf-8")
        return inbox_path

    @classmethod
    def tick(cls, out_dir: str | Path) -> dict[str, int]:
        out_path = Path(out_dir)
        run_records_dir = out_path / "run_records"
        run_records_dir.mkdir(parents=True, exist_ok=True)
        ledger = JsonlLedger(out_path / "program_ledger.jsonl")

        record_files = sorted(run_records_dir.glob("*.json"))
        promoted = 0
        pending = 0
        run_records: list[RunRecord] = []
        program_id = "unknown-program"
        goal = "unknown-goal"
        max_candidates = max(1, len(record_files))

        for record_path in record_files:
            raw = cls._read_validation_payload(record_path)
            if not raw:
                continue

            bundle_dir = cls._resolve_bundle_path(out_path, str(raw.get("bundle_path", "")))
            validation_path = bundle_dir / "validation_report.json"
            validation_payload = cls._read_validation_payload(validation_path)

            execution_type = str(raw.get("execution_type", "")).strip()
            if not execution_type:
                execution_type = cls._read_execution_type_from_bundle(bundle_dir)
            if not execution_type:
                execution_type = "slot_a"

            previous_gate = cls._normalize_state_text(
                str(raw.get("gate_result", validation_payload.get("gate_result", "FAIL")))
            ) or "FAIL"
            previous_status = cls._normalize_state_text(
                str(raw.get("status", validation_payload.get("status", "")))
            )
            previous_next_action = cls._normalize_next_action(
                raw.get("next_action") if isinstance(raw.get("next_action"), str) else None
            )

            current_gate = str(
                validation_payload.get("gate_result", raw.get("gate_result", "FAIL"))
            ).upper()
            if not current_gate:
                current_gate = "FAIL"
            current_status = cls._normalize_state_text(str(validation_payload.get("status", "")))
            done_marker = str(validation_payload.get("done_marker", "outputs/outputs_manifest.json"))
            if not done_marker.strip():
                done_marker = "outputs/outputs_manifest.json"
            done_marker = done_marker.strip()
            marker_path = (bundle_dir / done_marker).resolve()
            event_details: dict[str, Any] = {
                "done_marker": done_marker,
                "manifest_path": str(marker_path),
            }

            next_action: str | None = None
            manifest_error: str | None = None
            missing_files: list[str] = []
            mismatches: list[dict[str, Any]] = []
            if current_gate == "PENDING":
                run_id = str(raw.get("run_id", record_path.stem))
                if not marker_path.exists():
                    pending += 1
                    next_action = f"Create done marker: {done_marker}"
                    if not current_status:
                        current_status = "WAITING_EXTERNAL_OUTPUTS"
                    write_validation_report(
                        validation_path,
                        run_id=run_id,
                        gate_result="PENDING",
                        status=current_status,
                        checks=[
                            {
                                "name": "manifest_present",
                                "status": "PENDING",
                                "details": f"waiting for marker: {done_marker}",
                            }
                        ],
                        extras={"done_marker": done_marker},
                    )
                else:
                    manifest_entries, manifest_status, manifest_error = cls._load_outputs_manifest(marker_path)
                    if manifest_status is not None:
                        pending += 1
                        current_status = manifest_status
                        error_type = "JSONDecodeError" if manifest_status == "INVALID_OUTPUTS_MANIFEST" else "ValueError"
                        event_details["error_type"] = error_type
                        event_details["error_message"] = manifest_error or manifest_status
                        next_action = (
                            "Fix outputs_manifest.json: invalid JSON; "
                            "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                            if manifest_status == "INVALID_OUTPUTS_MANIFEST"
                            else "Fix outputs_manifest.json schema: include files list; "
                            "replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                        )
                        write_validation_report(
                            validation_path,
                            run_id=run_id,
                            gate_result="PENDING",
                            status=manifest_status,
                            checks=[
                                {
                                    "name": "manifest_present",
                                    "status": "PASS",
                                    "marker_path": str(marker_path),
                                },
                                {
                                    "name": "output_files_present",
                                    "status": "FAIL",
                                    "missing_files": [],
                                },
                                {
                                    "name": "output_files_verified",
                                    "status": "FAIL",
                                    "mismatches": [],
                                },
                            ],
                            error_type=error_type,
                            error_message=manifest_error or manifest_status,
                            extras={
                                "done_marker": done_marker,
                            },
                        )
                    else:
                        outputs_root = marker_path.parent
                        expected_entries = manifest_entries or []
                        expected_files = [str(entry.get("path", "")) for entry in expected_entries]
                        has_size_mismatch = False
                        has_hash_mismatch = False

                        for entry in expected_entries:
                            rel_file = str(entry.get("path", ""))
                            file_path = (outputs_root / rel_file).resolve()
                            if not file_path.exists() or not file_path.is_file():
                                missing_files.append(rel_file)
                                continue

                            if "size" in entry:
                                expected_size = int(entry["size"])
                                actual_size = file_path.stat().st_size
                                if actual_size != expected_size:
                                    has_size_mismatch = True
                                    mismatches.append(
                                        {
                                            "path": rel_file,
                                            "kind": "size",
                                            "check": "size",
                                            "expected": expected_size,
                                            "actual": actual_size,
                                        }
                                    )

                            if "sha256" in entry:
                                expected_hash = str(entry["sha256"]).lower()
                                actual_hash = cls._sha256_file(file_path).lower()
                                if actual_hash != expected_hash:
                                    has_hash_mismatch = True
                                    mismatches.append(
                                        {
                                            "path": rel_file,
                                            "kind": "sha256",
                                            "check": "sha256",
                                            "expected": expected_hash,
                                            "actual": actual_hash,
                                        }
                                    )

                        if missing_files or has_size_mismatch or has_hash_mismatch:
                            pending += 1
                            status = "MISSING_OUTPUT_FILES"
                            files_present_status = "FAIL"
                            if missing_files:
                                next_action = (
                                    "Add missing files under outputs/: "
                                    + ", ".join(missing_files)
                                    + "; replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                                )
                            elif has_size_mismatch:
                                status = "OUTPUT_FILE_SIZE_MISMATCH"
                                files_present_status = "PASS"
                                next_action = (
                                    "Resolve output size mismatches: "
                                    + cls._format_mismatch_details(mismatches)
                                    + "; replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                                )
                            else:
                                status = "OUTPUT_FILE_HASH_MISMATCH"
                                files_present_status = "PASS"
                                next_action = (
                                    "Resolve output hash mismatches: "
                                    + cls._format_mismatch_details(mismatches)
                                    + "; replace files under outputs/ and/or update outputs_manifest.json then rerun tick"
                                )

                            current_status = status
                            event_details["missing_files"] = missing_files
                            event_details["mismatches"] = cls._coerce_mismatches_for_event(mismatches)
                            write_validation_report(
                                validation_path,
                                run_id=run_id,
                                gate_result="PENDING",
                                status=status,
                                checks=[
                                    {
                                        "name": "manifest_present",
                                        "status": "PASS",
                                        "marker_path": str(marker_path),
                                    },
                                    {
                                        "name": "output_files_present",
                                        "status": files_present_status,
                                        "files": expected_files,
                                        "missing_files": missing_files,
                                    },
                                    {
                                        "name": "output_files_verified",
                                        "status": "FAIL",
                                        "mismatches": mismatches,
                                    },
                                ],
                                extras={
                                    "done_marker": done_marker,
                                    "missing_files": missing_files,
                                    "mismatches": mismatches,
                                },
                            )
                        else:
                            write_validation_report(
                                validation_path,
                                run_id=run_id,
                                gate_result="PASS",
                                checks=[
                                    {
                                        "name": "manifest_present",
                                        "status": "PASS",
                                        "marker_path": str(marker_path),
                                    },
                                    {
                                        "name": "output_files_present",
                                        "status": "PASS",
                                        "files": expected_files,
                                    },
                                    {
                                        "name": "output_files_verified",
                                        "status": "PASS",
                                        "mismatches": [],
                                    },
                                ],
                                extras={"completed_at": _utc_now()},
                            )
                            current_gate = "PASS"
                            current_status = ""
                            event_details["missing_files"] = []
                            event_details["mismatches"] = []
                            promoted += 1
            else:
                current_status = cls._normalize_state_text(str(validation_payload.get("status", "")))

            program_id = str(raw.get("program_id", program_id))
            bundle_program_spec = cls._read_bundle_program_spec(bundle_dir)
            if bundle_program_spec:
                goal = str(bundle_program_spec.get("goal", goal))
                try:
                    max_candidates = max(max_candidates, int(bundle_program_spec.get("max_candidates", max_candidates)))
                except (TypeError, ValueError):
                    pass

            score = 1.0 if current_gate == "PASS" else 0.0
            current_run_id = str(raw.get("run_id", "")).strip() or cls._read_run_id_from_bundle_dir(bundle_dir)
            current_history = cls._normalize_bundle_history(raw.get("bundle_history"))
            previous_bundle_dir = raw.get("previous_bundle_dir")
            if not isinstance(previous_bundle_dir, str) or not previous_bundle_dir.strip():
                previous_bundle_dir = None
            audit_dir = cls._normalize_optional_str(raw.get("audit_dir"))
            audit_status = cls._normalize_optional_str(raw.get("audit_status"))
            audit_report_path = cls._normalize_optional_str(raw.get("audit_report_path"))
            audit_diff_path = cls._normalize_optional_str(raw.get("audit_diff_path"))
            audit_exec_path = cls._normalize_optional_str(raw.get("audit_exec_path"))
            updated_record = RunRecord(
                run_id=current_run_id,
                program_id=program_id,
                candidate_id=str(raw.get("candidate_id", record_path.stem)),
                bundle_path=str(raw.get("bundle_path", str(bundle_dir))),
                gate_result=current_gate,
                score=score,
                execution_type=execution_type,
                next_action=next_action,
                bundle_history=current_history,
                previous_bundle_dir=previous_bundle_dir,
                audit_dir=audit_dir,
                audit_status=audit_status,
                audit_report_path=audit_report_path,
                audit_diff_path=audit_diff_path,
                audit_exec_path=audit_exec_path,
            )

            record_path.write_text(
                json.dumps(updated_record.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            run_records.append(updated_record)

            state_changed = (
                previous_gate != cls._normalize_state_text(current_gate)
                or previous_status != cls._normalize_state_text(current_status)
                or previous_next_action != cls._normalize_next_action(next_action)
            )
            tick_event_type = cls._map_status_to_event_type(current_gate, current_status)
            if state_changed and tick_event_type:
                event_details["run_id"] = updated_record.run_id
                if next_action:
                    event_details["next_action"] = next_action
                if manifest_error:
                    event_details["manifest_error"] = manifest_error
                event_payload = {
                    "ts": _utc_now(),
                    "event": tick_event_type,
                    "event_type": tick_event_type,
                    "program_id": updated_record.program_id,
                    "candidate_id": updated_record.candidate_id,
                    "execution_type": execution_type,
                    "bundle_dir": str(bundle_dir),
                    "run_id": updated_record.run_id,
                    "gate_result": cls._normalize_state_text(current_gate) or "FAIL",
                    "status": cls._normalize_state_text(current_status) or "COMPLETED",
                    "details": event_details,
                }
                append_event(out_path, event_payload)

        ranked = sorted(run_records, key=lambda record: record.score, reverse=True)
        top_k = ranked[: min(len(ranked), max(1, max_candidates))]
        inbox_path = cls._write_inbox_file(
            out_dir=out_path,
            program_id=program_id,
            goal=goal,
            run_records=top_k,
        )
        ledger.append(
            {
                "ts": _utc_now(),
                "event": "tick",
                "program_id": program_id,
                "path": str(inbox_path),
                "count": len(top_k),
                "promoted": promoted,
                "pending": pending,
            }
        )
        return {
            "records": len(run_records),
            "promoted": promoted,
            "pending": pending,
        }

    @staticmethod
    def _resolve_bundle_path(out_dir: Path, bundle_path: str) -> Path:
        raw_path = Path(bundle_path)
        if raw_path.is_absolute():
            return raw_path
        if raw_path.exists():
            return raw_path.resolve()
        candidate = (out_dir / raw_path).resolve()
        return candidate

    @staticmethod
    def _read_bundle_program_spec(bundle_dir: Path) -> dict[str, Any] | None:
        path = bundle_dir / "program_spec.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if isinstance(payload, dict):
            return payload
        return None

    @staticmethod
    def _read_execution_type_from_bundle(bundle_dir: Path) -> str:
        path = bundle_dir / "candidate_card.json"
        if not path.exists():
            return ""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        execution_type = payload.get("execution_type")
        if isinstance(execution_type, str):
            return execution_type.strip()
        return ""

    def _resolve_adapter(self, candidate_card: CandidateCard) -> tuple[KernelAdapter | None, str | None]:
        cfg = self.spec.executor_map.get(candidate_card.execution_type)
        if cfg is None:
            return self.kernel, None

        if cfg.kernel == "fake":
            return FakeKernelAdapter(), None

        if cfg.kernel == "subprocess":
            try:
                command = self._resolve_subprocess_command(cfg)
            except ValueError as exc:
                return None, str(exc)
            timeout_seconds = self._resolve_subprocess_timeout(cfg)
            return (
                SubprocessKernelAdapter(
                    command=command,
                    timeout_seconds=timeout_seconds,
                    cmd_file=cfg.cmd_file,
                ),
                None,
            )

        return None, f"unsupported kernel for execution_type '{candidate_card.execution_type}': {cfg.kernel}"

    def _resolve_subprocess_timeout(self, cfg: ExecutorConfig) -> float | None:
        if cfg.timeout_seconds is not None:
            return float(cfg.timeout_seconds)
        if self.default_subprocess_timeout_seconds is not None:
            return float(self.default_subprocess_timeout_seconds)
        if isinstance(self.kernel, SubprocessKernelAdapter):
            return self.kernel.timeout_seconds
        return None

    def _resolve_subprocess_command(self, cfg: ExecutorConfig) -> str | list[str]:
        if cfg.cmd_file:
            cmd_path = Path(cfg.cmd_file)
            if not cmd_path.exists():
                raise ValueError(f"cmd_file not found: {cmd_path}")
            try:
                raw = cmd_path.read_text(encoding="utf-8-sig")
            except OSError as exc:
                raise ValueError(f"failed to read cmd_file '{cmd_path}': {exc}") from exc
            return self._parse_json_command_list(raw, source=f"cmd_file:{cmd_path}")

        if cfg.cmd is None:
            raise ValueError("subprocess executor requires cmd or cmd_file")

        if isinstance(cfg.cmd, list):
            return substitute_command_tokens(list(cfg.cmd))

        cmd_text = cfg.cmd
        if cmd_text.lstrip().startswith("["):
            return self._parse_json_command_list(cmd_text, source="cmd")
        return cmd_text

    @staticmethod
    def _parse_json_command_list(raw: str, source: str) -> list[str]:
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

    def _write_routing_failure_bundle(
        self,
        candidate_card: CandidateCard,
        error_type: str,
        error_message: str,
    ) -> Path:
        run_id = self._new_run_id()
        bundle_dir = self.out_dir / "bundles" / f"{self.spec.program_id}-{candidate_card.id}-{run_id}"
        while bundle_dir.exists():
            run_id = self._new_run_id()
            bundle_dir = self.out_dir / "bundles" / f"{self.spec.program_id}-{candidate_card.id}-{run_id}"
        bundle_dir.mkdir(parents=True, exist_ok=False)

        metadata_path = bundle_dir / "metadata.json"
        validation_path = bundle_dir / "validation_report.json"

        metadata_payload: dict[str, Any] = {
            "run_id": run_id,
            "created_at": _utc_now(),
            "adapter": "executor_router",
            "program_id": self.spec.program_id,
            "candidate_id": candidate_card.id,
            "execution_type": candidate_card.execution_type,
        }
        metadata_path.write_text(
            json.dumps(with_schema_version(metadata_payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        write_validation_report(
            validation_path,
            run_id=run_id,
            gate_result="FAIL",
            checks=[
                {
                    "name": "executor_routing",
                    "status": "FAIL",
                    "details": error_message,
                }
            ],
            error_type=error_type,
            error_message=error_message,
            extras={
                "error": {
                    "error_type": error_type,
                    "error_message": error_message,
                    "execution_type": candidate_card.execution_type,
                }
            },
        )
        return bundle_dir
