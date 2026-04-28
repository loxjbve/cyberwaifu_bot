from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.services.config_file_service import ConfigFileService


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_config_file_service_crud_and_listing(tmp_path):
    _write_json(tmp_path / "config" / "alpha.json", {"a": 1})
    _write_json(tmp_path / "prompts" / "beta.json", {"b": 2})

    service = ConfigFileService(str(tmp_path))

    listing = service.list_files()
    assert {item["name"] for item in listing["config"]} == {"alpha.json"}
    assert {item["name"] for item in listing["prompts"]} == {"beta.json"}

    read_payload = service.read_file("config/alpha.json")
    assert read_payload["content"] == {"a": 1}

    save_result = service.save_file("config/alpha.json", {"a": 9})
    assert save_result["success"] is True
    assert json.loads((tmp_path / "config" / "alpha.json").read_text(encoding="utf-8")) == {"a": 9}
    assert (tmp_path / "config" / "alpha.json.backup").exists()

    create_result = service.create_file("characters", "gamma", {"c": 3})
    assert create_result["path"] == "characters/gamma.json"
    assert (tmp_path / "characters" / "gamma.json").exists()

    delete_result = service.delete_file("characters/gamma.json")
    assert delete_result["success"] is True
    assert not (tmp_path / "characters" / "gamma.json").exists()


def test_config_file_service_rejects_invalid_paths(tmp_path):
    service = ConfigFileService(str(tmp_path))

    with pytest.raises(PermissionError):
        service.read_file("../secrets.json")

    with pytest.raises(PermissionError):
        service.save_file("unknown/test.json", {})

    with pytest.raises(ValueError):
        service.create_file("invalid", "name", {})
