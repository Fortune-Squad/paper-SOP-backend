from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import sys

from .contracts import with_schema_version

class JsonlLedger:
    """Append-only JSONL ledger."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: dict[str, Any]) -> None:
        payload = with_schema_version(dict(event))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        return read_jsonl(self.path)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []

    entries: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                entries.append(with_schema_version(payload))
    return entries


def append_event(out_dir: str | Path, event_dict: dict[str, Any]) -> None:
    """
    Best-effort JSONL append for program_ledger.jsonl.

    Ledger failures must not break orchestration.
    """
    try:
        ledger_path = Path(out_dir) / "program_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        payload = with_schema_version(dict(event_dict))
        with ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - defensive logging path
        print(f"[autopilot] failed to append ledger event: {exc}", file=sys.stderr)
