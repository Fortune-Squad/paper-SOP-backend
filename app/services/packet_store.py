"""
PacketStore — append-only HandoffPacket storage.

Mirrors the TrajectoryStore pattern:
  - ``projects/{id}/handoff/packets.jsonl``  (append-only data)
  - ``projects/{id}/handoff/index.json``     (lightweight counts)

Design: append-only JSONL, no update/delete.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.handoff_packet import HandoffPacket, ReasoningBlock, \
    DecisionBlock, ArtifactBlock, TaskBlock
from app.services.workplan import ConvergenceConfig

logger = logging.getLogger(__name__)


class PacketStore:
    """HandoffPacket storage — JSONL append + JSON index."""

    def __init__(self, project_path: str) -> None:
        self.project_path = Path(project_path)
        self.handoff_dir = self.project_path / "handoff"
        self.packets_path = self.handoff_dir / "packets.jsonl"
        self.index_path = self.handoff_dir / "index.json"

    # ── ensure dir ──────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self.handoff_dir.mkdir(parents=True, exist_ok=True)

    # ── core write ──────────────────────────────────────────────────

    def store(self, packet: HandoffPacket) -> str:
        """Append a HandoffPacket to the JSONL store.

        Returns the packet_id.
        """
        self._ensure_dir()
        data = asdict(packet)
        with open(self.packets_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
        self._update_index(packet)
        logger.info(
            "Packet stored: id=%s type=%s %s→%s",
            packet.packet_id, packet.packet_type,
            packet.from_model, packet.to_model,
        )
        return packet.packet_id

    # ── queries ─────────────────────────────────────────────────────

    def query_by_thread(self, thread_id: str) -> List[HandoffPacket]:
        """Return all packets belonging to a conversation thread."""
        records = self._load_all()
        return [
            self._dict_to_packet(r)
            for r in records
            if r.get("thread_id") == thread_id
        ]

    def query_by_phase(self, phase_id: str) -> List[HandoffPacket]:
        """Return all packets belonging to a specific phase."""
        records = self._load_all()
        return [
            self._dict_to_packet(r)
            for r in records
            if r.get("phase_id") == phase_id
        ]

    def get_latest(
        self,
        phase_id: str,
        packet_type: str,
    ) -> Optional[HandoffPacket]:
        """Return the most recent packet matching phase + type."""
        records = self._load_all()
        for r in reversed(records):
            if r.get("phase_id") == phase_id and r.get("packet_type") == packet_type:
                return self._dict_to_packet(r)
        return None

    def export_chain(self, thread_id: str) -> List[Dict[str, Any]]:
        """Export a full conversation chain as dicts, ordered by timestamp."""
        records = self._load_all()
        chain = [r for r in records if r.get("thread_id") == thread_id]
        chain.sort(key=lambda r: r.get("timestamp", ""))
        return chain

    # ── internal helpers ────────────────────────────────────────────

    def _load_all(self) -> List[Dict[str, Any]]:
        """Load all records from the JSONL file."""
        if not self.packets_path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with open(self.packets_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping malformed JSONL line in %s",
                        self.packets_path,
                    )
        return records

    def _update_index(self, packet: HandoffPacket) -> None:
        """Maintain a lightweight index.json with counts."""
        index: Dict[str, Any] = {}
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    index = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("PacketStore index read failed, resetting: %s", e)
                index = {}

        index["total_packets"] = index.get("total_packets", 0) + 1
        index["last_updated"] = packet.timestamp

        by_type = index.setdefault("by_type", {})
        pt = packet.packet_type or "unknown"
        by_type[pt] = by_type.get(pt, 0) + 1

        by_phase = index.setdefault("by_phase", {})
        ph = packet.phase_id or "unknown"
        by_phase[ph] = by_phase.get(ph, 0) + 1

        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _dict_to_packet(d: Dict[str, Any]) -> HandoffPacket:
        """Reconstruct a HandoffPacket from a plain dict."""
        reasoning_raw = d.get("reasoning")
        reasoning = ReasoningBlock(**reasoning_raw) if reasoning_raw else None

        decisions_raw = d.get("decisions")
        decisions = DecisionBlock(**decisions_raw) if decisions_raw else None

        artifacts_raw = d.get("artifacts")
        artifacts = ArtifactBlock(**artifacts_raw) if artifacts_raw else None

        task_raw = d.get("task")
        task = TaskBlock(**task_raw) if task_raw else None

        conv_raw = d.get("convergence")
        convergence = ConvergenceConfig(**conv_raw) if conv_raw else None

        return HandoffPacket(
            packet_id=d.get("packet_id", ""),
            schema_version=d.get("schema_version", "m2m-tp/0.2"),
            mode=d.get("mode", "quick"),
            from_model=d.get("from_model", ""),
            to_model=d.get("to_model", ""),
            phase_id=d.get("phase_id", ""),
            packet_type=d.get("packet_type", ""),
            timestamp=d.get("timestamp", ""),
            thread_id=d.get("thread_id", ""),
            parent_packet_id=d.get("parent_packet_id"),
            workplan_id=d.get("workplan_id", ""),
            stage_key=d.get("stage_key", ""),
            delivery_method=d.get("delivery_method", "DIRECT_API"),
            reasoning=reasoning,
            decisions=decisions,
            artifacts=artifacts,
            task=task,
            convergence=convergence,
        )
