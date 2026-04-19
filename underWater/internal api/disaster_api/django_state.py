import atexit
import logging
import os
from typing import Dict

from disaster_api import db
from disaster_api.auth_service import AuthService
from disaster_api.config import Settings, load_settings
from disaster_api.scheduler import PollingScheduler
from disaster_api.services.aggregator import DisasterAggregator

_state: Dict[str, object] = {}


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _should_start_scheduler(settings: Settings) -> bool:
    if not settings.enable_scheduler:
        return False
    if settings.server_debug and os.environ.get("RUN_MAIN") != "true":
        return False
    return True


def get_state() -> Dict[str, object]:
    if _state:
        return _state

    _configure_logging()
    current_settings = load_settings()

    db.init_db(current_settings.database_url)
    auth_service = AuthService(current_settings)
    aggregator = DisasterAggregator(current_settings)
    scheduler = PollingScheduler(current_settings.poll_interval_seconds, aggregator.run_cycle)

    _state.update(
        {
            "settings": current_settings,
            "auth_service": auth_service,
            "aggregator": aggregator,
            "scheduler": scheduler,
        }
    )

    if _should_start_scheduler(current_settings):
        scheduler.start(run_immediately=current_settings.run_sync_on_startup)
        atexit.register(scheduler.stop)
        logging.getLogger(__name__).info(
            "Background polling enabled: every %s seconds",
            current_settings.poll_interval_seconds,
        )
    else:
        logging.getLogger(__name__).info("Background polling disabled")

    return _state
