import logging
import threading
from typing import Callable


LOGGER = logging.getLogger(__name__)


class PollingScheduler:
    def __init__(self, interval_seconds: int, job: Callable[[], None]):
        self.interval_seconds = max(60, interval_seconds)
        self.job = job
        self._stop_event = threading.Event()
        self._thread = None
        self._run_immediately = True

    def start(self, run_immediately: bool = True) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._run_immediately = run_immediately
        self._thread = threading.Thread(target=self._loop, daemon=True, name="disaster-polling-scheduler")
        self._thread.start()
        LOGGER.info("Scheduler started. interval_seconds=%s", self.interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        LOGGER.info("Scheduler stopped")

    def _loop(self) -> None:
        if self._run_immediately:
            self._safe_run()

        while not self._stop_event.wait(self.interval_seconds):
            self._safe_run()

    def _safe_run(self) -> None:
        try:
            self.job()
        except Exception:  # noqa: BLE001
            LOGGER.exception("Scheduled sync job failed")
