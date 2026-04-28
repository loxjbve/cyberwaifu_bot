from __future__ import annotations

import importlib
import sys


def test_importing_runtime_modules_does_not_load_settings_or_mutate_sys_path(monkeypatch):
    import utils.config_utils as config_utils
    import utils.db_utils as db_utils
    import web.factory as web_factory

    original_sys_path = list(sys.path)

    def fail(*args, **kwargs):
        raise AssertionError("settings should not be loaded during module import")

    monkeypatch.setattr(config_utils, "load_settings", fail)
    monkeypatch.setattr(config_utils, "get_settings", fail)
    monkeypatch.setattr(config_utils, "get_config", fail)
    monkeypatch.setattr(config_utils, "get_default_api", fail)
    monkeypatch.setattr(config_utils, "get_default_char", fail)
    monkeypatch.setattr(config_utils, "get_default_preset", fail)
    monkeypatch.setattr(config_utils, "get_default_stream", fail)
    monkeypatch.setattr(config_utils, "get_default_frequency", fail)
    monkeypatch.setattr(config_utils, "get_default_balance", fail)

    importlib.reload(web_factory)
    importlib.reload(db_utils)

    assert sys.path == original_sys_path
