from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import json
import os
import uuid

from .contracts import parse_iso8601_utc, with_schema_version
from .ledger import append_event


LOCK_FILENAME = ".autopilot.lock"
LOCK_STALE_AFTER = timedelta(hours=1)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OutDirLock(AbstractContextManager["OutDirLock"]):
    def __init__(self, out_dir: str | Path, command: str, enabled: bool = True) -> None:
        self.out_dir = Path(out_dir)
        self.command = command
        self.enabled = enabled
        self.lock_path = self.out_dir / LOCK_FILENAME
        self.owner_token = uuid.uuid4().hex
        self._acquired = False

    def __enter__(self) -> "OutDirLock":
        self.out_dir.mkdir(parents=True, exist_ok=True)
        if not self.enabled:
            return self
        self._acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.enabled or not self._acquired:
            return None
        try:
            if not self.lock_path.exists():
                return None
            payload = self._read_lock_payload()
            if payload.get("owner_token") == self.owner_token:
                released_payload = with_schema_version(dict(payload))
                released_payload["released"] = True
                released_payload["released_ts"] = _utc_now().isoformat()
                self.lock_path.write_text(
                    json.dumps(released_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        except Exception:
            pass
        return None

    def _acquire(self) -> None:
        now = _utc_now()
        payload = with_schema_version(
            {
                "pid": os.getpid(),
                "start_ts": now.isoformat(),
                "command": self.command,
                "owner_token": self.owner_token,
            }
        )

        if self.lock_path.exists():
            existing = self._read_lock_payload()
            if bool(existing.get("released")):
                self.lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                self._acquired = True
                return
            existing_ts = parse_iso8601_utc(str(existing.get("start_ts", "")))
            if existing_ts is None:
                try:
                    existing_ts = datetime.fromtimestamp(self.lock_path.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    existing_ts = now
            age = now - existing_ts
            if age > LOCK_STALE_AFTER:
                self.lock_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                append_event(
                    self.out_dir,
                    {
                        "ts": now.isoformat(),
                        "event": "LOCK_STALE_OVERRIDE",
                        "event_type": "LOCK_STALE_OVERRIDE",
                        "program_id": "unknown-program",
                        "candidate_id": "",
                        "execution_type": "",
                        "bundle_dir": str(self.out_dir),
                        "gate_result": "PENDING",
                        "status": "LOCK_STALE_OVERRIDE",
                        "details": {
                            "lock_path": str(self.lock_path),
                            "stale_age_seconds": int(age.total_seconds()),
                            "previous_lock": existing,
                            "command": self.command,
                        },
                    },
                )
                self._acquired = True
                return
            raise RuntimeError(
                f"out_dir lock exists and is active: {self.lock_path}. "
                "Use --no-lock to bypass if you are sure no concurrent run is active."
            )

        try:
            with self.lock_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        except FileExistsError:
            raise RuntimeError(
                f"out_dir lock exists: {self.lock_path}. "
                "Use --no-lock to bypass if you are sure no concurrent run is active."
            )
        self._acquired = True

    def _read_lock_payload(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return {}
