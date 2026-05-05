from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from bot_core.data_repository.conv_model import Conversation, Group, GroupConfig, User
from bot_core.services.utils.prompt import HistoryAssembler
from utils.config_utils import get_settings

logger = logging.getLogger(__name__)


class SoulSkillError(RuntimeError):
    pass


@dataclass(frozen=True)
class SoulSkillBundle:
    character: str
    root: Path
    manifest_text: str
    skill_text: str
    available_documents: list[str]


class SoulSkillRepository:
    def __init__(self, souls_root: Optional[Path] = None) -> None:
        if souls_root is None:
            settings = get_settings(force_reload=False)
            souls_root = Path(settings.project_root) / "data" / "souls"
        self.souls_root = souls_root.resolve()

    def has_skill(self, character: str) -> bool:
        try:
            root = self._resolve_soul_root(character)
        except SoulSkillError:
            return False
        return (root / "SKILL.md").is_file()

    def load_bundle(self, character: str) -> SoulSkillBundle:
        root = self._resolve_soul_root(character)
        skill_text = self._read_required(root, "SKILL.md")
        manifest_text = self._read_required(root, "manifest.json")
        return SoulSkillBundle(
            character=character,
            root=root,
            manifest_text=manifest_text,
            skill_text=skill_text,
            available_documents=self._list_documents(root),
        )

    def read_documents(self, bundle: SoulSkillBundle, document_names: list[str]) -> dict[str, str]:
        documents: dict[str, str] = {}
        for document_name in document_names:
            if document_name in {"SKILL.md", "manifest.json"}:
                continue
            if document_name not in bundle.available_documents:
                logger.warning("Soul document %s is not available for %s", document_name, bundle.character)
                continue
            documents[document_name] = self._read_required(bundle.root, document_name)
        return documents

    def _resolve_soul_root(self, character: str) -> Path:
        if not character or any(separator in character for separator in ("/", "\\")):
            raise SoulSkillError(f"非法 soul 名称: {character!r}")

        root = (self.souls_root / character).resolve()
        try:
            root.relative_to(self.souls_root)
        except ValueError as error:
            raise SoulSkillError(f"Soul 路径越界: {character}") from error
        return root

    def _read_required(self, root: Path, relative_path: str) -> str:
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise SoulSkillError(f"Soul 文档路径越界: {relative_path}") from error

        if not path.is_file():
            raise SoulSkillError(f"缺少 Soul 文档: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _list_documents(root: Path) -> list[str]:
        return sorted(path.name for path in root.glob("*.md") if path.is_file())


class SoulAgentService:
    def __init__(
        self,
        *,
        llm_client: Any,
        user: User,
        input_text: str,
        conversation: Optional[Conversation] = None,
        group: Optional[Group] = None,
        group_config: Optional[GroupConfig] = None,
        repository: Optional[SoulSkillRepository] = None,
        history_assembler: Optional[HistoryAssembler] = None,
    ) -> None:
        self.llm_client = llm_client
        self.user = user
        self.input_text = input_text
        self.conversation = conversation
        self.group = group
        self.group_config = group_config
        self.repository = repository or SoulSkillRepository()
        self.history_assembler = history_assembler or HistoryAssembler()
        self.trace_messages: list[dict[str, Any]] = []

    async def build_response(self) -> str:
        character = self._resolve_character()
        bundle = self.repository.load_bundle(character)
        history = self._build_history_messages()

        planning_text = await self._run_llm(self._build_planning_messages(bundle, history))
        plan = self._parse_planning(planning_text, bundle.available_documents)
        documents = self.repository.read_documents(bundle, plan["documents"])

        synthesis_text = await self._run_llm(
            self._build_synthesis_messages(bundle, history, planning_text, documents)
        )
        return await self._run_llm(
            self._build_final_messages(bundle, history, planning_text, synthesis_text, documents)
        )

    def _resolve_character(self) -> str:
        if self.group_config and self.group_config.char:
            return self.group_config.char
        return self.user.character

    def _build_history_messages(self) -> list[dict[str, str]]:
        if self.group and self.conversation:
            return self.history_assembler.build_group_history(self.conversation.id).messages
        return self.history_assembler.build_private_history(self.conversation).messages

    async def _run_llm(self, messages: list[dict[str, Any]]) -> str:
        self.trace_messages.extend(messages)
        self.llm_client.set_messages(messages)
        chunks: list[str] = []
        async for chunk in self.llm_client.response(False):
            if chunk:
                chunks.append(chunk)
        return "".join(chunks)

    def _build_planning_messages(
        self,
        bundle: SoulSkillBundle,
        history: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是 Soul Skill Agent 的 planning 阶段。必须先依据 manifest.json 和 SKILL.md "
                    "判断任务类型、证据边界和需要补读的文档。只输出 JSON，不要输出解释。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "character": bundle.character,
                        "available_documents": bundle.available_documents,
                        "manifest_json": bundle.manifest_text,
                        "skill_md": bundle.skill_text,
                        "history": history,
                        "current_input": self.input_text,
                        "required_json_schema": {
                            "task_type": "string",
                            "documents": ["document.md"],
                            "evidence_boundary": "string",
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _build_synthesis_messages(
        self,
        bundle: SoulSkillBundle,
        history: list[dict[str, str]],
        planning_text: str,
        documents: dict[str, str],
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "你是 Soul Skill Agent 的 synthesis 阶段。根据 planning 与补读文档生成内部综合，"
                    "必须分清事实、推断、建议，并保留 SKILL.md 中的证据边界。不要生成最终聊天回复。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "character": bundle.character,
                        "planning": planning_text,
                        "manifest_json": bundle.manifest_text,
                        "skill_md": bundle.skill_text,
                        "documents": documents,
                        "history": history,
                        "current_input": self.input_text,
                    },
                    ensure_ascii=False,
                ),
            },
        ]

    def _build_final_messages(
        self,
        bundle: SoulSkillBundle,
        history: list[dict[str, str]],
        planning_text: str,
        synthesis_text: str,
        documents: dict[str, str],
    ) -> list[dict[str, Any]]:
        context = {
            "character": bundle.character,
            "chat_type": "group" if self.group else "private",
            "group_name": self.group.name if self.group else "",
            "planning": planning_text,
            "synthesis": synthesis_text,
            "loaded_documents": list(documents.keys()),
            "history": history,
            "current_input": self.input_text,
        }
        return [
            {
                "role": "system",
                "content": (
                    "你是 Soul Skill Agent 的 final 阶段。只输出最终可见回复，不暴露 planning/synthesis。"
                    "必须遵守 Soul Skill 的边界和证据纪律。输出必须兼容以下标签格式："
                    "<content>给用户看的回复</content><summary>一句话摘要</summary><comment>内部备注或暂无</comment>。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(context, ensure_ascii=False),
            },
        ]

    @staticmethod
    def _parse_planning(planning_text: str, available_documents: list[str]) -> dict[str, Any]:
        available = set(available_documents)
        parsed: dict[str, Any] = {}
        try:
            parsed = json.loads(planning_text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", planning_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    parsed = {}

        documents = parsed.get("documents") if isinstance(parsed, dict) else []
        if not isinstance(documents, list):
            documents = []

        safe_documents = [
            str(document)
            for document in documents
            if isinstance(document, str)
            and document in available
            and document not in {"SKILL.md", "manifest.json"}
        ]
        return {
            "task_type": parsed.get("task_type", "unknown") if isinstance(parsed, dict) else "unknown",
            "documents": safe_documents,
            "evidence_boundary": parsed.get("evidence_boundary", "") if isinstance(parsed, dict) else "",
        }
