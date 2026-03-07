from __future__ import annotations

import logging
import signal
import time
from pathlib import Path
from typing import Any

from .hil_bridge import HILBridge
from .recovery import RecoveryManager

logger = logging.getLogger(__name__)


class AutopilotScheduler:
    """7x24 tick loop that wraps AutopilotLoop.tick().

    Handles crash recovery on startup, periodic tick execution,
    HIL ticket expiry, and graceful shutdown via SIGINT/SIGTERM.
    """

    def __init__(
        self,
        out_dir: str | Path,
        tick_interval_seconds: float = 30.0,
        max_consecutive_failures: int = 10,
        hil_inbox_dir: str | Path | None = None,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.tick_interval_seconds = tick_interval_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self.recovery = RecoveryManager(self.out_dir)
        self.hil = HILBridge(Path(hil_inbox_dir)) if hil_inbox_dir else None
        self._running = False
        self._tick_count = 0

    # ── main entry point ─────────────────────────────────────────────

    def run_forever(self) -> None:
        """Main entry point.  Blocks until SIGINT/SIGTERM or stop()."""
        self._running = True
        self._setup_signal_handlers()

        # Phase 1: Recovery on startup
        logger.info("AutopilotScheduler starting, out_dir=%s", self.out_dir)
        state = self.recovery.load_state()
        try:
            report = self.recovery.recover_on_startup()
            if report["recovered_orphans"]:
                logger.warning(
                    "Recovered %d orphaned runs", len(report["recovered_orphans"])
                )
        except Exception as exc:
            logger.error("Recovery failed (continuing): %s", exc)

        # Phase 2: Tick loop
        logger.info("Entering tick loop (interval=%.1fs)", self.tick_interval_seconds)
        while self._running:
            self._tick_count += 1
            tick_ok = self._do_one_tick(state)
            state = self.recovery.record_tick_result(state, tick_ok, {})

            if state.consecutive_failures >= self.max_consecutive_failures:
                logger.critical(
                    "Hit %d consecutive failures, pausing for 5 minutes",
                    state.consecutive_failures,
                )
                self._sleep(300)  # 5 min cooldown
            else:
                self._sleep(self.tick_interval_seconds)

        logger.info("AutopilotScheduler stopped after %d ticks", self._tick_count)

    # ── single tick ──────────────────────────────────────────────────

    def _do_one_tick(self, state: Any) -> bool:
        """Execute one tick cycle.  Returns True if successful."""
        try:
            # Import here to avoid circular import at module level
            from .loop import AutopilotLoop

            # Expire overdue HIL tickets
            if self.hil:
                expired = self.hil.expire_overdue()
                if expired:
                    logger.info("Expired %d HIL tickets", len(expired))

            # Main tick
            result = AutopilotLoop.tick(str(self.out_dir))
            logger.info("Tick #%d complete: %s", self._tick_count, result)
            return True
        except Exception as exc:
            logger.error("Tick #%d failed: %s", self._tick_count, exc, exc_info=True)
            return False

    # ── control ──────────────────────────────────────────────────────

    def stop(self) -> None:
        """Signal the scheduler to stop after current tick."""
        logger.info("Stop requested")
        self._running = False

    def _setup_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())

    def _sleep(self, seconds: float) -> None:
        """Interruptible sleep - checks _running flag every second."""
        remaining = seconds
        while remaining > 0 and self._running:
            time.sleep(min(1.0, remaining))
            remaining -= 1.0

    # ── properties ───────────────────────────────────────────────────

    @property
    def tick_count(self) -> int:
        return self._tick_count

    @property
    def is_running(self) -> bool:
        return self._running
