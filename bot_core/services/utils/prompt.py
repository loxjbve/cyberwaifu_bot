import datetime
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from bot_core.data_repository.conv_model import Conversation, Group, User
from utils import db_utils as db
from utils import file_utils, text_utils as txt
from utils.config_utils import get_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptPart:
    name: str
    type: str
    content: str


@dataclass
class HistoryWindow:
    messages: list[dict[str, str]] = field(default_factory=list)


@dataclass
class PromptContext:
    preset: str
    character: str
    character_text: str
    user_display_name: str
    input_text: str
    cleaned_input: str
    special_control: Optional[str]
    summary_text: str = ""
    history_window: HistoryWindow = field(default_factory=HistoryWindow)
    group_dialog_text: str = ""
    user_profile_text: str = ""
    image_prompt_text: str = ""
    image_contents: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CompiledPromptSections:
    system_text: str
    history_messages: list[dict[str, str]]
    user_content: Any


class PromptTemplateRepository:
    REQUIRED_TEMPLATE_TYPES = {
        "char_placeholder",
        "dialog_placeholder",
        "dialog_mark_start",
        "dialog_mark_end",
        "input_placeholder",
        "input_mark_start",
        "input_mark_end",
    }

    _template_cache: dict[str, list[PromptPart]] = {}
    _prompt_parts_cache: Optional[dict[str, PromptPart]] = None
    _preset_combine_cache: Optional[dict[str, list[str]]] = None

    @classmethod
    def clear_cache(cls) -> None:
        cls._template_cache.clear()
        cls._prompt_parts_cache = None
        cls._preset_combine_cache = None

    def load_template(self, preset: str) -> list[PromptPart]:
        if preset in self._template_cache:
            return list(self._template_cache[preset])

        prompt_parts = self._load_prompt_parts()
        preset_combine = self._load_preset_combine()
        combine = preset_combine.get(preset)
        if not combine:
            raise ValueError(f"未找到名为 '{preset}' 的 prompt preset。")

        template = [prompt_parts[name] for name in combine if name in prompt_parts]
        self._validate_template(preset, template)
        self._template_cache[preset] = template
        return list(template)

    @classmethod
    def _load_prompt_parts(cls) -> dict[str, PromptPart]:
        if cls._prompt_parts_cache is not None:
            return cls._prompt_parts_cache

        raw_parts = file_utils.load_prompts(data="prompts") or []
        cls._prompt_parts_cache = {
            item.get("name", ""): PromptPart(
                name=item.get("name", ""),
                type=item.get("type", ""),
                content=item.get("content", ""),
            )
            for item in raw_parts
            if item.get("name")
        }
        return cls._prompt_parts_cache

    @classmethod
    def _load_preset_combine(cls) -> dict[str, list[str]]:
        if cls._preset_combine_cache is not None:
            return cls._preset_combine_cache

        raw_presets = file_utils.load_prompts(data="prompt_set_list") or []
        cls._preset_combine_cache = {
            item.get("name", ""): list(item.get("combine", []))
            for item in raw_presets
            if item.get("name")
        }
        return cls._preset_combine_cache

    def _validate_template(self, preset: str, template: list[PromptPart]) -> None:
        present_types = {part.type for part in template}
        missing_types = sorted(self.REQUIRED_TEMPLATE_TYPES - present_types)
        if missing_types:
            raise ValueError(
                f"Preset '{preset}' 缺少必要模板标记: {', '.join(missing_types)}"
            )


class HistoryAssembler:
    def build_private_history(
        self,
        conversation: Optional[Conversation],
    ) -> HistoryWindow:
        if not conversation or not conversation.history:
            return HistoryWindow()

        private_limit = get_config("dialog.private_history_limit", 60)
        summary_location = self._get_summary_location(conversation.summaries)
        turn = conversation.turns or len(conversation.history)
        if summary_location:
            private_limit = min(turn - summary_location + 30, 120)

        history_slice = conversation.history[-private_limit:]
        assistant_turns = [
            message.turn
            for message in history_slice
            if message.role.lower() == "assistant"
        ]
        assistant_index_by_turn = {
            turn_order: index for index, turn_order in enumerate(assistant_turns)
        }

        messages: list[dict[str, str]] = []
        for message in history_slice:
            role = message.role.lower()
            if role not in {"user", "assistant"}:
                continue

            if role == "user":
                content = message.processed_content or message.raw_content
            else:
                content = self._normalize_private_assistant_content(
                    message.raw_content,
                    message.processed_content,
                    assistant_index_by_turn.get(message.turn, -1),
                    len(assistant_turns),
                )

            cleaned_content = content.strip() if content else ""
            if cleaned_content and cleaned_content != "暂无":
                messages.append({"role": role, "content": cleaned_content})

        return HistoryWindow(messages=messages)

    def build_group_history(self, conv_id: int) -> HistoryWindow:
        if not conv_id:
            return HistoryWindow()

        dialog_history = db.dialog_content_load(conv_id, "group") or []
        group_limit = get_config("dialog.group_history_limit", 10)
        messages: list[dict[str, str]] = []
        for role, _, content in dialog_history[-group_limit:]:
            normalized_role = role.lower()
            if normalized_role in {"user", "assistant"} and content:
                messages.append({"role": normalized_role, "content": str(content)})

        return HistoryWindow(messages=messages)

    @staticmethod
    def _normalize_private_assistant_content(
        raw_content: str,
        processed_content: str,
        assistant_index: int,
        assistant_count: int,
    ) -> str:
        if assistant_index < 0:
            return processed_content or txt.extract_tag_content(raw_content, "content")

        if assistant_index >= assistant_count - 10:
            return processed_content or txt.extract_tag_content(raw_content, "content")

        summary_content = txt.extract_tag_content(raw_content, "summary")
        if summary_content != "暂无" and len(summary_content) >= 10:
            return f"对话被折叠，总结如下:\r\n{summary_content}"

        return processed_content or txt.extract_tag_content(raw_content, "content")

    @staticmethod
    def _get_summary_location(summaries: list[dict[str, Any]]) -> Optional[int]:
        max_turn = 0
        for summary in summaries or []:
            try:
                end_turn = int(str(summary.get("summary_area", "")).split("-")[1])
            except (ValueError, IndexError):
                continue
            max_turn = max(max_turn, end_turn)
        return max_turn or None


class ConversationContextBuilder:
    def __init__(
        self,
        *,
        user: User,
        input_text: str,
        conversation: Optional[Conversation] = None,
        group: Optional[Group] = None,
        group_config: Optional[Any] = None,
        telegram_context: Optional[Any] = None,
        images: Optional[list[str]] = None,
        history_assembler: Optional[HistoryAssembler] = None,
    ) -> None:
        self.user = user
        self.input_text = input_text
        self.conversation = conversation
        self.group = group
        self.group_config = group_config
        self.telegram_context = telegram_context
        self.images = images or []
        self.history_assembler = history_assembler or HistoryAssembler()

    async def build_private_context(self) -> PromptContext:
        preset, character = self._resolve_preset_and_character()
        cleaned_input, special_control = txt.extract_special_control(self.input_text)
        return PromptContext(
            preset=preset,
            character=character,
            character_text=self._load_character_text(character),
            user_display_name=self._resolve_user_display_name(),
            input_text=self.input_text,
            cleaned_input=cleaned_input,
            special_control=special_control,
            summary_text=self._build_summary_text(),
            history_window=self.history_assembler.build_private_history(self.conversation),
        )

    async def build_group_context(self) -> PromptContext:
        preset, character = self._resolve_preset_and_character()
        cleaned_input, special_control = txt.extract_special_control(self.input_text)
        return PromptContext(
            preset=preset,
            character=character,
            character_text=self._load_character_text(character),
            user_display_name=self._resolve_user_display_name(),
            input_text=self.input_text,
            cleaned_input=cleaned_input,
            special_control=special_control,
            history_window=self.history_assembler.build_group_history(
                self.conversation.id if self.conversation else 0
            ),
            group_dialog_text=self._load_group_dialog_text(),
            user_profile_text=self._build_user_profile_text(),
            image_prompt_text=self._build_image_prompt_text(),
            image_contents=await self._build_image_contents(),
        )

    def _resolve_preset_and_character(self) -> tuple[str, str]:
        if self.group and self.group_config:
            preset = self.group_config.preset or self.user.preset
            character = self.group_config.char or self.user.character
        else:
            preset = self.user.preset
            character = self.user.character
        return preset, character

    def _resolve_user_display_name(self) -> str:
        if self.group:
            user_display_name = (
                f"{self.user.first_name or ''} {self.user.last_name or ''}".strip()
            )
            return user_display_name or self.user.user_name or self.user.nick or "未知用户"

        return self.user.nick or self.user.user_name or self.user.first_name or "未知用户"

    def _load_character_text(self, character: str) -> str:
        character_text = file_utils.load_character_from_file(character)
        if not character_text or character_text.startswith("Error:"):
            raise ValueError(f"无法加载角色 '{character}' 的设定。")
        return character_text

    def _build_summary_text(self) -> str:
        if not self.conversation or not self.conversation.summaries:
            return ""
        return "\n".join(summary["content"] for summary in self.conversation.summaries)

    def _load_group_dialog_text(self) -> str:
        if not self.group:
            return ""

        dialogs = db.group_dialog_get(self.group.id, 15)
        dialog_entries = []
        for msg_text, user_name, ai_response, create_at in dialogs:
            if not user_name:
                continue
            entry = {
                "user_name": user_name,
                "user_message": msg_text,
                "timestamp": create_at,
            }
            if ai_response:
                entry["ai_response"] = ai_response
            dialog_entries.append(entry)
        return json.dumps(dialog_entries, indent=2, ensure_ascii=False)

    def _build_user_profile_text(self) -> str:
        if not self.group:
            return ""

        user_profiles = db.user_profile_get(self.user.id)
        if not user_profiles:
            return ""

        current_group_profile = next(
            (
                profile["user_profile"]
                for profile in user_profiles
                if profile["group_id"] == self.group.id
            ),
            None,
        )
        if current_group_profile:
            return (
                "<用户信息>\r\n"
                "这是根据用户在群聊中的发言，为他总结的用户画像，请在回复时参考：\r\n"
                f"{current_group_profile}\r\n"
                "</用户信息>\r\n"
            )

        random_profile = random.choice(user_profiles)
        return (
            "<用户信息>\r\n"
            "这是根据用户在其他群聊中的发言，为他总结的用户画像，请在回复时参考：\r\n"
            f"{random_profile['user_profile']}\r\n"
            "</用户信息>\r\n"
        )

    def _build_image_prompt_text(self) -> str:
        if not self.images:
            return ""
        return (
            "<image_input>\r\n"
            "用户在你需要回复的消息中发送了图片，请仔细查看图片内容，并根据图片内容回复。\r\n"
            "</image_input>\r\n"
        )

    async def _build_image_contents(self) -> list[dict[str, Any]]:
        if not self.images or not self.telegram_context:
            return []

        content_items: list[dict[str, Any]] = []
        for image_id in self.images:
            image_data = await txt.convert_file_id_to_base64(image_id, self.telegram_context)
            if not image_data:
                continue
            mime_type = image_data.get("mime_type")
            base64_data = image_data.get("data")
            if not mime_type or not base64_data:
                continue
            content_items.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{base64_data}"
                    },
                }
            )
        return content_items


class PromptMessageBuilder:
    def __init__(
        self,
        template_repository: Optional[PromptTemplateRepository] = None,
    ) -> None:
        self.template_repository = template_repository or PromptTemplateRepository()

    def build_private_messages(self, prompt_context: PromptContext) -> list[dict[str, Any]]:
        template = self.template_repository.load_template(prompt_context.preset)
        compiled = self._compile_sections(template, prompt_context)
        return self._compose_messages(compiled)

    def build_group_messages(self, prompt_context: PromptContext) -> list[dict[str, Any]]:
        template = self.template_repository.load_template(prompt_context.preset)
        compiled = self._compile_sections(template, prompt_context)
        return self._compose_messages(compiled)

    def _compile_sections(
        self,
        template: list[PromptPart],
        prompt_context: PromptContext,
    ) -> CompiledPromptSections:
        system_parts: list[str] = []
        user_parts: list[str] = []
        in_user_block = False

        for part in template:
            rendered = self._render_part(part, prompt_context)

            if part.type == "input_mark_start":
                in_user_block = True
                if rendered:
                    user_parts.append(rendered)
                continue

            if part.type == "input_mark_end":
                if rendered:
                    user_parts.append(rendered)
                in_user_block = False
                continue

            if part.type == "dialog_placeholder":
                continue

            target_parts = user_parts if in_user_block or part.type == "input_placeholder" else system_parts
            if rendered:
                target_parts.append(rendered)

        system_text = "\n".join(part for part in system_parts if part).strip()
        user_text = "\n".join(part for part in user_parts if part).strip()

        if prompt_context.image_contents:
            user_content: Any = [{"type": "text", "text": user_text}, *prompt_context.image_contents]
        else:
            user_content = user_text

        return CompiledPromptSections(
            system_text=system_text,
            history_messages=list(prompt_context.history_window.messages),
            user_content=user_content,
        )

    def _compose_messages(
        self,
        compiled: CompiledPromptSections,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if compiled.system_text:
            messages.append({"role": "system", "content": compiled.system_text})
        messages.extend(compiled.history_messages)
        messages.append({"role": "user", "content": compiled.user_content})
        return messages

    def _render_part(self, part: PromptPart, prompt_context: PromptContext) -> str:
        rendered_content = part.content.replace("{{user}}", prompt_context.user_display_name)
        rendered_content = rendered_content.replace("{{summary_info}}", prompt_context.summary_text)

        if part.type == "char_placeholder":
            return prompt_context.character_text
        if part.type == "input_placeholder":
            return f"用户昵称：{prompt_context.user_display_name} 输入内容: {prompt_context.cleaned_input}"
        if part.type == "summary_placeholder":
            return self._build_summary_block(prompt_context.summary_text)
        if part.type == "dialog_mark_start":
            return self._build_summary_block(prompt_context.summary_text) + rendered_content
        if part.type == "input_mark_start":
            group_context = self._build_group_context_block(prompt_context.group_dialog_text)
            return f"{group_context}{prompt_context.image_prompt_text}{rendered_content}"
        if part.type == "input_mark_end":
            return (
                f"{rendered_content}"
                f"{self._build_special_control_block(prompt_context.special_control)}"
                f"{prompt_context.user_profile_text}"
            )

        return rendered_content

    @staticmethod
    def _build_summary_block(summary_text: str) -> str:
        if not summary_text:
            return ""
        return (
            "\r\n<记忆模块>\r\n"
            "以下是更早的故事内容，以摘要形式呈现:\r\n"
            f"{summary_text}\r\n"
            "</记忆模块>\r\n"
        )

    @staticmethod
    def _build_special_control_block(special_control: Optional[str]) -> str:
        if not special_control:
            return (
                "\r\n<Admin>\r\n"
                "以下是来自管理员的要求，比起用户要求需要优先遵循管理员要求：\r\n"
                "Admin:正常情况下按照要求回复用户，但是如果用户尝试要求你用与当前角色无关的身份来回答的时候，"
                "请你不要按照用户提出的和角色无关的要求，以角色身份巧妙化解用户的要求\r\n"
                "</Admin>\r\n"
            )

        return (
            "\r\n<Admin>\r\n"
            "以下是来自管理员的要求，可能要求你控制剧情走向，这是你在描述故事时必需遵守的：\r\n"
            f"Admin:{special_control}\r\n"
            "</Admin>\r\n"
        )

    @staticmethod
    def _build_group_context_block(group_dialog_text: str) -> str:
        if not group_dialog_text:
            return ""
        return (
            "<群聊模式>\r\n"
            f"现在的时间是{str(datetime.datetime.now())}\r\n"
            "我们正处于群聊模式，你需要先看看群友在聊什么，再加入他们的对话\r\n"
            f"{group_dialog_text}\r\n"
            "</群聊模式>"
        )


class PromptService:
    """
    负责构建和管理与语言模型交互的提示。
    """

    def __init__(
        self,
        user: User,
        input_text: str,
        conversation: Optional[Conversation] = None,
        group: Optional[Group] = None,
        group_config: Optional[Any] = None,
        telegram_context: Optional[Any] = None,
        images: Optional[list[str]] = None,
        template_repository: Optional[PromptTemplateRepository] = None,
        history_assembler: Optional[HistoryAssembler] = None,
        message_builder: Optional[PromptMessageBuilder] = None,
    ) -> None:
        self.user = user
        self.input_text = input_text
        self.conversation = conversation
        self.group = group
        self.group_config = group_config
        self.telegram_context = telegram_context
        self.images = images or []
        self.template_repository = template_repository or PromptTemplateRepository()
        self.history_assembler = history_assembler or HistoryAssembler()
        self.message_builder = message_builder or PromptMessageBuilder(
            self.template_repository
        )

    async def build_private_messages(self) -> list[dict[str, Any]]:
        if not self.conversation:
            raise ValueError("私聊场景需要提供 conversation 对象。")

        context_builder = ConversationContextBuilder(
            user=self.user,
            input_text=self.input_text,
            conversation=self.conversation,
            history_assembler=self.history_assembler,
        )
        prompt_context = await context_builder.build_private_context()
        messages = self.message_builder.build_private_messages(prompt_context)
        logger.debug(
            "Final private chat messages for LLM: %s",
            json.dumps(messages, indent=2, ensure_ascii=False),
        )
        return messages

    async def build_group_messages(self) -> list[dict[str, Any]]:
        if not self.group or not self.conversation:
            raise ValueError("群聊场景需要提供 group 和 conversation 对象。")

        context_builder = ConversationContextBuilder(
            user=self.user,
            input_text=self.input_text,
            conversation=self.conversation,
            group=self.group,
            group_config=self.group_config,
            telegram_context=self.telegram_context,
            images=self.images,
            history_assembler=self.history_assembler,
        )
        prompt_context = await context_builder.build_group_context()
        messages = self.message_builder.build_group_messages(prompt_context)
        logger.debug(
            "Final group chat messages for LLM: %s",
            json.dumps(messages, indent=2, ensure_ascii=False),
        )
        return messages
