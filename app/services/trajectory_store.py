"""
TrajectoryStore — append-only incident trajectory storage.

Core data asset of SignalPass.  Aggregates records from:
  - WP Engine (fail_wp, execute_wp exceptions, iterate_wp)
  - Gate runner (Gate FAIL)
  - Readiness Assessor (RA BLOCK)
  - Boundary checker (violations)
  - ErrorPatternCollector bridge (via callers: LLMTraceRecorder, SanityCheckAPI)
  - Slot-B memory bridge (via wp_engine call sites)

Storage: ``projects/{id}/trajectory/records.jsonl`` + ``index.json``
Design: append-only JSONL, no update/delete.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.trajectory_record import TrajectoryRecord

logger = logging.getLogger(__name__)


class TrajectoryStore:
    """Append-only trajectory record store backed by JSONL files."""

    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path)
        self.traj_dir = self.project_path / "trajectory"
        self.records_path = self.traj_dir / "records.jsonl"
        self.index_path = self.traj_dir / "index.json"

    # ── ensure dir exists ─────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self.traj_dir.mkdir(parents=True, exist_ok=True)

    # ── core write ────────────────────────────────────────────────

    def record(self, rec: TrajectoryRecord) -> str:
        """Append a TrajectoryRecord to the JSONL store.

        Returns the record_id.
        """
        self._ensure_dir()
        data = asdict(rec)
        with open(self.records_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        self._update_index(rec)
        logger.info("Trajectory recorded: id=%s summary=%.80s", rec.record_id, rec.problem_summary)
        return rec.record_id

    def record_fail_to_fix(
        self,
        problem: str,
        error_detail: str,
        root_cause: str,
        solution: str,
        outcome: str,
        *,
        error_category: str = "custom",
        slot: str = "core",
        stage: str = "",
        wp_id: str = "",
        project_id: str = "",
        source_system: str = "",
        source_actor: str = "system",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Convenience method for the common fail-to-fix pattern."""
        rec = TrajectoryRecord(
            problem_summary=problem,
            problem_detail=error_detail,
            root_cause=root_cause,
            error_category=error_category,
            slot=slot,
            stage=stage,
            wp_id=wp_id,
            project_id=project_id,
            solution_summary=solution,
            outcome=outcome,
            source_system=source_system,
            source_actor=source_actor,
            tags=tags or [],
        )
        return self.record(rec)

    # ── bridge: Slot-B memory ─────────────────────────────────────

    def ingest_from_slot_b_memory(self, entry: Dict[str, Any]) -> str:
        """Bridge a Slot-B memory entry dict into a TrajectoryRecord.

        Expected keys: tag, solver, wp_id, symptom, root_cause,
                       correction, prevention (optional).
        """
        tags = [entry.get("tag", "slot_b_error")]
        prevention = entry.get("prevention", "")
        if prevention:
            tags.append(f"prevention:{prevention}")

        rec = TrajectoryRecord(
            problem_summary=entry.get("symptom", ""),
            root_cause=entry.get("root_cause", ""),
            error_category="slot_b_error",
            slot="slot_b",
            solver=entry.get("solver", ""),
            wp_id=entry.get("wp_id", ""),
            solution_summary=entry.get("correction", ""),
            outcome="unresolved",
            source_system="slot_b_memory",
            source_actor="system",
            tags=tags,
        )
        return self.record(rec)

    # ── sync to MEMORY.md ─────────────────────────────────────────

    def sync_to_memory_md(self, memory_store: Any, max_entries: int = 20) -> int:
        """Sync recent resolved/workaround records into MEMORY.md.

        Returns the number of entries synced.
        """
        records = self._load_all()
        # Only sync resolved or workaround outcomes
        eligible = [
            r for r in records
            if r.get("outcome") in ("resolved", "workaround")
        ]
        # Most recent first, cap at max_entries
        eligible = eligible[-max_entries:]

        synced = 0
        for r in eligible:
            try:
                memory_store.add_error_pattern(
                    symptom=r.get("problem_summary", ""),
                    root_cause=r.get("root_cause", ""),
                    correction=r.get("solution_summary", ""),
                    source_actor=r.get("source_actor", "system"),
                    wp_id=r.get("wp_id", ""),
                )
                synced += 1
            except Exception as e:
                logger.warning("sync_to_memory_md skip: %s", e)
        return synced

    # ── query ─────────────────────────────────────────────────────

    def query(
        self,
        *,
        problem_type: Optional[str] = None,
        slot: Optional[str] = None,
        solver: Optional[str] = None,
        outcome_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Structured query over trajectory records."""
        records = self._load_all()
        results: List[Dict[str, Any]] = []
        for r in reversed(records):  # newest first
            if problem_type and r.get("error_category") != problem_type:
                continue
            if slot and r.get("slot") != slot:
                continue
            if solver and r.get("solver") != solver:
                continue
            if outcome_filter and r.get("outcome") != outcome_filter:
                continue
            results.append(r)
            if len(results) >= limit:
                break
        return results

    # ── export ────────────────────────────────────────────────────

    def export_for_delivery(self, sanitize: bool = True) -> List[Dict[str, Any]]:
        """Export records for external delivery; optionally sanitize."""
        records = self._load_all()
        if not sanitize:
            return records

        sanitized = []
        for r in records:
            clean = dict(r)
            # Remove internal detail fields
            for key in ("problem_detail", "solution_detail", "parameters"):
                clean.pop(key, None)
            # Redact project_id
            if "project_id" in clean:
                clean["project_id"] = "REDACTED"
            sanitized.append(clean)
        return sanitized

    def export_raw(self) -> List[Dict[str, Any]]:
        """Internal full-fidelity export."""
        return self._load_all()

    # ── stats ─────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregated statistics over trajectory records."""
        records = self._load_all()
        stats: Dict[str, Any] = {
            "total_records": len(records),
            "by_category": {},
            "by_slot": {},
            "by_outcome": {},
            "by_source_system": {},
        }
        for r in records:
            cat = r.get("error_category", "unknown")
            stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
            sl = r.get("slot", "unknown")
            stats["by_slot"][sl] = stats["by_slot"].get(sl, 0) + 1
            oc = r.get("outcome", "unknown")
            stats["by_outcome"][oc] = stats["by_outcome"].get(oc, 0) + 1
            ss = r.get("source_system", "unknown")
            stats["by_source_system"][ss] = stats["by_source_system"].get(ss, 0) + 1
        return stats

    # ── internal helpers ──────────────────────────────────────────

    def _load_all(self) -> List[Dict[str, Any]]:
        """Load all records from the JSONL file."""
        if not self.records_path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with open(self.records_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping malformed JSONL line in {self.records_path}")
        return records

    def _update_index(self, rec: TrajectoryRecord) -> None:
        """Maintain a lightweight index.json with counts and latest timestamp."""
        index: Dict[str, Any] = {}
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("TrajectoryStore index read failed, resetting: %s", e)
                index = {}

        index["total_records"] = index.get("total_records", 0) + 1
        index["last_updated"] = rec.timestamp
        cat = rec.error_category or "unknown"
        by_cat = index.setdefault("by_category", {})
        by_cat[cat] = by_cat.get(cat, 0) + 1

        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
