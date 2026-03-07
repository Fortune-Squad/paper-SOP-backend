from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import append_event, read_jsonl

logger = logging.getLogger(__name__)


# ── Atomic write helper ─────────────────────────────────────────────


def atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON atomically: tmpfile → fsync → os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".state_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ── ProgramState ─────────────────────────────────────────────────────


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProgramState:
    program_id: str = "unknown"
    status: str = "idle"
    created_at: str = ""
    updated_at: str = ""
    total_candidates: int = 0
    total_runs: int = 0
    active_runs: int = 0
    budget_consumed: float = 0.0
    decision_counts: dict[str, int] = field(default_factory=dict)
    last_successful_tick: str | None = None
    consecutive_failures: int = 0

    def __post_init__(self) -> None:
        now = _utc_now_iso()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_candidates": self.total_candidates,
            "total_runs": self.total_runs,
            "active_runs": self.active_runs,
            "budget_consumed": self.budget_consumed,
            "decision_counts": dict(self.decision_counts),
            "last_successful_tick": self.last_successful_tick,
            "consecutive_failures": self.consecutive_failures,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProgramState:
        return cls(
            program_id=str(data.get("program_id", "unknown")),
            status=str(data.get("status", "idle")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            total_candidates=int(data.get("total_candidates", 0)),
            total_runs=int(data.get("total_runs", 0)),
            active_runs=int(data.get("active_runs", 0)),
            budget_consumed=float(data.get("budget_consumed", 0.0)),
            decision_counts=dict(data.get("decision_counts", {})),
            last_successful_tick=data.get("last_successful_tick"),
            consecutive_failures=int(data.get("consecutive_failures", 0)),
        )


# ── RecoveryManager ──────────────────────────────────────────────────


# Event types that indicate a run has been acknowledged by the system
# (i.e. it got past DISPATCH_SUBMIT and was processed by a tick or audit).
_NON_RESOLUTION_EVENTS = frozenset({
    "DISPATCH_SUBMIT",
    "retry_scheduled",
    "orphan_detected",
})


class RecoveryManager:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.state_path = self.out_dir / "state.json"
        self.ledger_path = self.out_dir / "program_ledger.jsonl"

    # ── state persistence ────────────────────────────────────────────

    def load_state(self) -> ProgramState:
        """Read state.json if it exists, else return default ProgramState."""
        if not self.state_path.exists():
            return ProgramState()
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return ProgramState.from_dict(raw)
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Corrupted state.json, returning default: %s", exc)
        return ProgramState()

    def save_state(self, state: ProgramState) -> None:
        """Persist state atomically."""
        state.updated_at = _utc_now_iso()
        atomic_write_json(self.state_path, state.to_dict())

    # ── crash recovery ───────────────────────────────────────────────

    def recover_on_startup(self, adapter: Any = None) -> dict[str, Any]:
        """Call at process start.  Returns a recovery report."""
        report: dict[str, Any] = {
            "recovered_orphans": [],
            "ledger_entries_scanned": 0,
            "warnings": [],
        }

        # Step 1 – read ledger, find in-flight run_ids
        entries = read_jsonl(self.ledger_path)
        report["ledger_entries_scanned"] = len(entries)

        dispatched_run_ids: dict[str, dict[str, Any]] = {}
        resolved_run_ids: set[str] = set()

        for entry in entries:
            event_type = str(entry.get("event_type", ""))
            run_id = str(entry.get("run_id", "")).strip()
            if not run_id:
                details = entry.get("details")
                if isinstance(details, dict):
                    run_id = str(details.get("run_id", "")).strip()
            if not run_id:
                continue

            if event_type == "DISPATCH_SUBMIT":
                dispatched_run_ids[run_id] = entry
            elif event_type not in _NON_RESOLUTION_EVENTS:
                resolved_run_ids.add(run_id)

        in_flight = set(dispatched_run_ids) - resolved_run_ids

        # Step 2 – cross-reference with adapter if available
        adapter_active: set[str] | None = None
        if adapter is not None and hasattr(adapter, "list_active_projects"):
            try:
                active_list = adapter.list_active_projects()
                adapter_active = set(str(p) for p in active_list)
            except Exception as exc:
                report["warnings"].append(f"adapter.list_active_projects() failed: {exc}")

        orphaned_run_ids: list[str] = []
        for run_id in sorted(in_flight):
            if adapter_active is not None:
                # If the adapter reports this run as still active, skip it
                dispatch_entry = dispatched_run_ids[run_id]
                candidate_id = str(dispatch_entry.get("candidate_id", ""))
                program_id = str(dispatch_entry.get("program_id", ""))
                if run_id in adapter_active or program_id in adapter_active:
                    continue
            orphaned_run_ids.append(run_id)

        # Step 3 – log orphan events
        now = _utc_now_iso()
        for run_id in orphaned_run_ids:
            dispatch_entry = dispatched_run_ids[run_id]
            append_event(self.out_dir, {
                "ts": now,
                "event": "orphan_detected",
                "event_type": "orphan_detected",
                "program_id": str(dispatch_entry.get("program_id", "unknown")),
                "candidate_id": str(dispatch_entry.get("candidate_id", "")),
                "execution_type": str(dispatch_entry.get("execution_type", "")),
                "bundle_dir": str(dispatch_entry.get("bundle_dir", "")),
                "run_id": run_id,
                "gate_result": "PENDING",
                "status": "ORPHAN_DETECTED",
                "details": {
                    "original_dispatch_ts": str(dispatch_entry.get("ts", "")),
                    "recovery_ts": now,
                },
            })
            report["recovered_orphans"].append(run_id)

        # Step 4 – update state
        state = self.load_state()
        state.status = "running" if not orphaned_run_ids else "error"
        state.active_runs = max(0, state.active_runs - len(orphaned_run_ids))
        self.save_state(state)

        if orphaned_run_ids:
            logger.info(
                "Recovery detected %d orphaned runs: %s",
                len(orphaned_run_ids),
                orphaned_run_ids,
            )
        return report

    # ── tick bookkeeping ─────────────────────────────────────────────

    def record_tick_result(
        self,
        state: ProgramState,
        success: bool,
        tick_summary: dict,
    ) -> ProgramState:
        """Update state after each tick.  Returns updated state."""
        if success:
            state.last_successful_tick = _utc_now_iso()
            state.consecutive_failures = 0
        else:
            state.consecutive_failures += 1

        # Merge decision counts from tick_summary
        for key, count in tick_summary.get("decision_counts", {}).items():
            state.decision_counts[key] = state.decision_counts.get(key, 0) + count

        state.total_runs += int(tick_summary.get("runs", 0))
        state.active_runs = int(tick_summary.get("active_runs", state.active_runs))

        self.save_state(state)
        return state
