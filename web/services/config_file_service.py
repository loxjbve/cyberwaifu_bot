from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any


class ConfigFileService:
    CATEGORY_DIRS = {
        "characters": "characters",
        "config": "config",
        "prompts": "prompts",
        "agent_docs": "agent/docs",
    }
    PROTECTED_FILES = {
        "config/config.json",
        "config/config_local.json",
        "config/default_config.json",
    }
    PROTECTED_CONFIG_FILENAMES = {"config.json", "config_local.json", "default_config.json"}

    def __init__(self, project_root: str) -> None:
        self.project_root = project_root
        self.allowed_dirs = tuple(f"{directory}/" for directory in self.CATEGORY_DIRS.values())

    def list_files(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for category, rel_dir_path in self.CATEGORY_DIRS.items():
            files: list[dict[str, Any]] = []
            abs_dir_path = os.path.join(self.project_root, rel_dir_path)
            if os.path.exists(abs_dir_path):
                for filename in os.listdir(abs_dir_path):
                    if not filename.endswith(".json"):
                        continue
                    abs_file_path = os.path.join(abs_dir_path, filename)
                    rel_file_path = f"{rel_dir_path}/{filename}".replace("\\", "/")
                    if rel_file_path in self.PROTECTED_FILES:
                        continue
                    try:
                        with open(abs_file_path, "r", encoding="utf-8") as file:
                            json.load(file)
                        files.append(
                            {
                                "name": filename,
                                "path": rel_file_path,
                                "size": os.path.getsize(abs_file_path),
                                "modified": os.path.getmtime(abs_file_path),
                            }
                        )
                    except Exception as error:
                        files.append(
                            {
                                "name": filename,
                                "path": rel_file_path,
                                "error": str(error),
                            }
                        )
            result[category] = files
        return result

    def read_file(self, rel_path: str) -> dict[str, Any]:
        file_path = self._resolve_rel_path(rel_path)
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise FileNotFoundError("File not found")

        with open(file_path, "r", encoding="utf-8") as file:
            content = json.load(file)

        return {
            "content": content,
            "path": self._normalize_rel_path(rel_path),
            "name": os.path.basename(file_path),
        }

    def save_file(self, rel_path: str, content: Any) -> dict[str, Any]:
        file_path = self._resolve_rel_path(rel_path)
        json.dumps(content)
        if os.path.exists(file_path):
            shutil.copy2(file_path, f"{file_path}.backup")
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=2)
        return {"success": True, "message": "Saved"}

    def create_file(self, category: str, filename: str, content: Any) -> dict[str, Any]:
        if category not in self.CATEGORY_DIRS:
            raise ValueError("Invalid category")

        safe_filename = filename if filename.endswith(".json") else f"{filename}.json"
        safe_filename = re.sub(r"[\\/*?:\"<>|]", "", safe_filename)
        if not safe_filename:
            raise ValueError("Invalid filename")
        if category == "config" and safe_filename in self.PROTECTED_CONFIG_FILENAMES:
            raise PermissionError("Access denied")

        dir_path = os.path.join(self.project_root, self.CATEGORY_DIRS[category])
        os.makedirs(dir_path, exist_ok=True)

        file_path = os.path.join(dir_path, safe_filename)
        if not os.path.abspath(file_path).startswith(os.path.abspath(dir_path)):
            raise PermissionError("Invalid filename")
        if os.path.exists(file_path):
            raise FileExistsError("File already exists")

        json.dumps(content)
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=2)

        rel_path = f"{self.CATEGORY_DIRS[category]}/{safe_filename}".replace("\\", "/")
        return {"success": True, "message": "Created", "path": rel_path}

    def delete_file(self, rel_path: str) -> dict[str, Any]:
        file_path = self._resolve_rel_path(rel_path)
        if not os.path.exists(file_path):
            raise FileNotFoundError("File not found")

        backup_path = f"{file_path}.deleted.{int(time.time())}"
        shutil.move(file_path, backup_path)
        return {"success": True, "message": "Deleted", "backup": backup_path}

    def _normalize_rel_path(self, rel_path: str) -> str:
        normalized = os.path.normpath(rel_path).replace("\\", "/")
        if normalized.startswith(("../", "./", "/")):
            raise PermissionError("Invalid path")
        if not any(normalized.startswith(prefix) for prefix in self.allowed_dirs):
            raise PermissionError("Access denied")
        if normalized in self.PROTECTED_FILES:
            raise PermissionError("Access denied")
        return normalized

    def _resolve_rel_path(self, rel_path: str) -> str:
        normalized = self._normalize_rel_path(rel_path)
        file_path = os.path.join(self.project_root, normalized)
        if not os.path.abspath(file_path).startswith(os.path.abspath(self.project_root)):
            raise PermissionError("Access denied")
        return file_path
