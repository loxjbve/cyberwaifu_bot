from __future__ import annotations

from typing import Optional

from db.runtime import initialize_database_runtime
from utils.config_utils import AppSettings, get_settings
from utils.logging_utils import bootstrap_logging


def bootstrap_application(settings: Optional[AppSettings] = None) -> AppSettings:
    active_settings = settings or get_settings(force_reload=False)
    bootstrap_logging()
    initialize_database_runtime(active_settings)
    return active_settings
