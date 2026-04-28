import asyncio
import datetime
import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from telegram import Update
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes

import bot_core.services.utils.usage as usage
from bot_core.data_repository.conv_model import Conversation, Group, GroupConfig, User
from bot_core.data_repository.gateways import (
    ConversationGateway,
    DataAccessError,
    GroupGateway,
    UserGateway,
)
from bot_core.services.messages import MessageFactory, send_message
from bot_core.services.utils.error import BotError
from bot_core.services.utils.prompt import PromptService
from bot_core.services.utils.summary import SummaryService
from utils.LLM_utils import LLM
from utils import text_utils as txt
from utils.text_utils import contains_nsfw

logger = logging.getLogger(__name__)


class Message:
    def __init__(self, message_id: int, text: str, mark: str):
        self.id = message_id
        self.text_raw = text
        if mark == "input":
            self.text_processed = txt.extract_special_control(text)[0] or text
        elif mark == "output":
            self.text_processed = txt.extract_tag_content(text, "content")
            self.text_summary = txt.extract_tag_content(text, "summary")
            self.text_comment = txt.extract_tag_content(text, "comment")
        else:
            self.text_processed = text


class MessageParser:
    @staticmethod
    def extract_text(update: Update) -> str:
        if update.message:
            return update.message.text or update.message.caption or ""
        return ""

    @staticmethod
    def extract_input(update: Update) -> Optional[Message]:
        if not update.message:
            return None
        return Message(update.message.message_id, MessageParser.extract_text(update), "input")

    @staticmethod
    def extract_images(update: Update) -> list[str]:
        if not update.message:
            return []

        images: list[str] = []
        if update.message.photo:
            images.append(update.message.photo[-1].file_id)
        elif update.message.document and update.message.document.mime_type:
            if update.message.document.mime_type.startswith("image/"):
                images.append(update.message.document.file_id)
        return images


class ConversationResponder:
    def __init__(self, llm_client: Any, user: User):
        self.llm_client = llm_client
        self.user = user

    async def get_llm_response(self, messages: List[Dict[str, Any]]):
        self.llm_client.set_messages(messages)
        async for chunk in self.llm_client.response(self.user.stream):
            yield chunk

    async def stream_private_response(
        self,
        messages: List[Dict[str, Any]],
        placeholder,
    ) -> str:
        response_chunks: list[str] = []
        last_update_time = asyncio.get_event_loop().time()
        last_updated_content = "..."

        async for chunk in self.get_llm_response(messages):
            response_chunks.append(chunk)
            response = "".join(response_chunks)
            current_time = asyncio.get_event_loop().time()

            if (
                placeholder
                and current_time - last_update_time >= 4.0
                and response != last_updated_content
            ):
                display_text = response[:4000] + ("..." if len(response) > 4000 else "")
                try:
                    await placeholder.edit_text(display_text)
                except TelegramError as error:
                    if "Message is not modified" not in str(error):
                        logger.warning("Failed to update placeholder: %s", error)
                last_updated_content = response
                last_update_time = current_time

            await asyncio.sleep(0.01)

        return "".join(response_chunks)

    async def collect_response(self, messages: List[Dict[str, Any]]) -> str:
        response_chunks: list[str] = []
        async for chunk in self.get_llm_response(messages):
            response_chunks.append(chunk)
            await asyncio.sleep(0.01)
        return "".join(response_chunks)


class ConversationStore:
    def __init__(
        self,
        conversation_gateway: Optional[ConversationGateway] = None,
        group_gateway: Optional[GroupGateway] = None,
    ):
        self.conversation_gateway = conversation_gateway or ConversationGateway()
        self.group_gateway = group_gateway or GroupGateway()

    def create_private_conversation(self, user: User) -> Conversation:
        return self.conversation_gateway.create_private(user)

    def create_group_conversation(self, user: User, group: Group) -> int:
        return self.conversation_gateway.create_group_conversation(user, group)

    async def undo_last_private_turn(
        self,
        *,
        conversation: Conversation,
        user: User,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> Optional[str]:
        conv_id = conversation.id
        last_input_text = self.conversation_gateway.get_last_input_text(conv_id)
        msg_ids = [message_id for message_id in self.conversation_gateway.get_latest_message_ids(conv_id) if message_id is not None]

        if not msg_ids:
            return None

        try:
            await context.bot.delete_messages(user.id, msg_ids)
        except Exception as error:
            logger.warning("Bulk delete failed: %s", error)
            for message_id in msg_ids:
                try:
                    await context.bot.delete_message(user.id, message_id)
                except Exception as inner_error:
                    logger.warning("Delete message %s failed: %s", message_id, inner_error)

        deleted_count = 0
        for message_id in msg_ids[:2]:
            try:
                self.conversation_gateway.delete_message(conv_id, message_id)
                deleted_count += 1
            except DataAccessError as error:
                logger.warning("Delete dialog record failed: %s", error)

        if deleted_count:
            conversation.turns = max(0, conversation.turns - deleted_count)
            self.conversation_gateway.update_turns(conv_id, conversation.turns, "private")

        return last_input_text

    def save_private_turn(
        self,
        *,
        conversation: Conversation,
        user: User,
        input_message: Message,
        output_message: Message,
        messages: List[Dict[str, Any]],
    ) -> None:
        if output_message.text_raw.startswith("API调用失败"):
            logger.warning("Skipping persistence because API call failed")
            return

        current_turn = max(conversation.turns, self.conversation_gateway.get_turn_count(conversation.id))
        self.conversation_gateway.append_dialogs(
            conversation.id,
            [
                {
                    "role": "user",
                    "turn_order": current_turn + 1,
                    "raw_content": input_message.text_raw,
                    "processed_content": input_message.text_processed,
                    "message_id": input_message.id,
                },
                {
                    "role": "assistant",
                    "turn_order": current_turn + 2,
                    "raw_content": output_message.text_raw,
                    "processed_content": output_message.text_processed,
                    "message_id": output_message.id,
                },
            ],
            chat_type="private",
        )

        conversation.turns = current_turn + 2
        self.conversation_gateway.update_turns(conversation.id, conversation.turns, "private")

        updated_frequencies = usage.update_user_usage(
            user,
            messages,
            output_message.text_raw,
            "private_chat",
        )
        if updated_frequencies:
            user.remain_frequency, user.temporary_frequency = updated_frequencies

    def save_group_turn(
        self,
        *,
        group: Group,
        user: User,
        conv_id: int,
        input_message: Message,
        output_message: Message,
        trigger: Optional[str],
        messages: List[Dict[str, Any]],
    ) -> None:
        turn = self.conversation_gateway.get_turn_count(conv_id, "group")
        self.conversation_gateway.append_dialogs(
            conv_id,
            [
                {
                    "role": "user",
                    "turn_order": turn + 1,
                    "raw_content": input_message.text_raw,
                    "processed_content": input_message.text_processed,
                },
                {
                    "role": "assistant",
                    "turn_order": turn + 2,
                    "raw_content": output_message.text_raw,
                    "processed_content": output_message.text_processed,
                },
            ],
            chat_type="group",
        )
        self.group_gateway.update_group_conversation_turn(conv_id, turns_increase=2)
        self.group_gateway.update_group_stats(group.id, call_count_increase=1)

        group_context = SimpleNamespace(user=user, group=group)
        usage.update_user_usage(group_context, messages, output_message.text_raw, "group_chat")

        if trigger:
            self.group_gateway.update_dialog_response(
                group_id=group.id,
                message_id=input_message.id,
                trigger_type=trigger,
                raw_response=output_message.text_raw,
                processed_response=output_message.text_processed,
            )


class ConversationService:
    def __init__(
        self,
        llm_client: Any,
        user: User,
        context: ContextTypes.DEFAULT_TYPE,
        conversation: Optional[Conversation] = None,
        store: Optional[ConversationStore] = None,
    ):
        self.user = user
        self.context = context
        self.conversation = conversation
        self.responder = ConversationResponder(llm_client, user)
        self.store = store or ConversationStore()

    async def get_llm_response(self, messages: List[Dict[str, Any]]):
        async for chunk in self.responder.get_llm_response(messages):
            yield chunk

    async def undo_last_turn(self) -> Optional[str]:
        if not self.conversation:
            return None
        return await self.store.undo_last_private_turn(
            conversation=self.conversation,
            user=self.user,
            context=self.context,
        )

    def save_turn(self, input_message: Message, output_message: Message, messages: List[Dict[str, Any]]) -> None:
        if not self.conversation:
            raise BotError("Missing private conversation for save")
        self.store.save_private_turn(
            conversation=self.conversation,
            user=self.user,
            input_message=input_message,
            output_message=output_message,
            messages=messages,
        )

    def create_group_conversation(self, group: Group) -> int:
        return self.store.create_group_conversation(self.user, group)

    def save_group_turn(
        self,
        group: Group,
        conv_id: int,
        input_message: Message,
        output_message: Message,
        trigger: Optional[str],
        messages: List[Dict[str, Any]],
    ) -> None:
        self.store.save_group_turn(
            group=group,
            user=self.user,
            conv_id=conv_id,
            input_message=input_message,
            output_message=output_message,
            trigger=trigger,
            messages=messages,
        )


class GroupConv:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.chat or not update.message.from_user:
            raise BotError("GroupConv initialization failed due to missing message/chat/user")

        self.update = update
        self.context = context
        self.user_gateway = UserGateway()
        self.group_gateway = GroupGateway()
        self.conversation_gateway = ConversationGateway()

        self.group = self.group_gateway.get_group(update.message.chat.id)
        self.input = MessageParser.extract_input(update)
        if not self.input:
            raise BotError("GroupConv requires message input")

        self.output: Optional[Message] = None
        self.placeholder = None
        self.config = self.group_gateway.get_runtime_config(self.group.id)
        self.trigger: Optional[str] = None
        self.images = MessageParser.extract_images(update)

        self.user = self.user_gateway.get_or_create(
            user_id=update.message.from_user.id,
            first_name=update.message.from_user.first_name or "",
            last_name=update.message.from_user.last_name or "",
            user_name=update.message.from_user.username or "",
        )
        self.id = self.conversation_gateway.get_group_conversation_id(self.group.id, self.user.id)

        try:
            self.client = LLM(self.config.api, "group")
        except ValueError as error:
            if "API配置" in str(error):
                message = (
                    f"API配置错误\n\n当前配置的 API '{self.config.api}' 不存在。\n\n"
                    "请使用 /api 指令查看并切换到可用的 API 配置。"
                )
                asyncio.create_task(send_message(self.context, self.group.id, message))
                raise BotError(f"API配置 '{self.config.api}' 不存在") from error
            raise

        self.conv_service = ConversationService(self.client, self.user, self.context)
        if not self.id:
            self.id = self.conv_service.create_group_conversation(self.group)

    def set_trigger(self, trigger: Optional[str]) -> None:
        self.trigger = trigger

    async def response(self):
        try:
            if self.update.message:
                self.placeholder = await self.update.message.reply_text("思考中")
        except (BadRequest, TelegramError) as error:
            logger.warning("Failed to send placeholder: %s", error)
            return

        if self.trigger in ["random", "keyword", "@"]:
            self.id = None
        elif not self.id:
            self.id = self.conv_service.create_group_conversation(self.group)

        asyncio.create_task(self._response_to_user())

    async def _response_to_user(self):
        try:
            if not self.config.preset or not self.config.char:
                if self.placeholder:
                    await self.placeholder.edit_text("群组未配置机器人，无法回复。")
                return

            temp_conversation = Conversation.model_validate(
                {
                    "conv_id": self.id or 0,
                    "user_id": self.user.id,
                    "character": self.config.char or "",
                    "preset": self.config.preset or "",
                    "created_at": datetime.datetime.now(),
                    "updated_at": datetime.datetime.now(),
                    "turns": 0,
                    "summaries": [],
                }
            )

            prompt_service = PromptService(
                user=self.user,
                input_text=self.input.text_raw,
                conversation=temp_conversation,
                group=self.group,
                group_config=self.config,
            )
            messages = prompt_service.build_group_chat_prompts(images=self.images)
            conv_service = ConversationService(self.client, self.user, self.context, temp_conversation)

            if self.images:
                await self.client.embedd_image(self.images, self.context)

            response_text = await conv_service.responder.collect_response(messages)
            factory = MessageFactory(update=self.update, context=self.context)

            if self.placeholder:
                self.output = Message(self.placeholder.message_id, response_text, "output")
                await factory.edit(self.placeholder, self.output.text_processed)
            else:
                self.output = Message(0, response_text, "output")

            if self.id and self.output:
                self.conv_service.save_group_turn(
                    self.group,
                    self.id,
                    self.input,
                    self.output,
                    self.trigger,
                    messages,
                )
            elif self.trigger and self.output:
                self.group_gateway.update_dialog_response(
                    group_id=self.group.id,
                    message_id=self.input.id,
                    trigger_type=self.trigger,
                    raw_response=self.output.text_raw,
                    processed_response=self.output.text_processed,
                )
        except Exception as error:
            logger.error("Group response failed: %s", error, exc_info=True)
            if self.placeholder:
                factory = MessageFactory(update=self.update, context=self.context)
                await factory.edit(self.placeholder, f"出错了：{error}")


class PrivateConv:
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_user:
            raise BotError("PrivateConv requires an effective user")

        self.update = update
        self.context = context
        self.placeholder = None
        self.output: Optional[Message] = None
        self.input = MessageParser.extract_input(update)
        self.user_gateway = UserGateway()
        self.conversation_gateway = ConversationGateway()

        effective_user = update.effective_user
        self.user = self.user_gateway.get_or_create(
            user_id=effective_user.id,
            first_name=effective_user.first_name or "",
            last_name=effective_user.last_name or "",
            user_name=effective_user.username or "",
        )

        conversation = None
        if self.user.active_conversation_id:
            conversation = self.conversation_gateway.get_private(self.user.active_conversation_id)
        if not conversation:
            conversation = self.conversation_gateway.create_private(self.user)
            self.user.active_conversation_id = conversation.id
        self.conversation = conversation

        try:
            self.client = LLM(self.user.api, "private")
        except ValueError as error:
            if "API配置" in str(error):
                message = (
                    f"API配置错误\n\n当前配置的 API '{self.user.api}' 不存在。\n\n"
                    "请使用 /api 指令查看并切换到可用的 API 配置。"
                )
                asyncio.create_task(send_message(self.context, self.user.id, message))
                raise BotError(f"API配置 '{self.user.api}' 不存在") from error
            raise

        SummaryService(self.conversation).check_and_generate_summaries_async()
        self.conv_service = ConversationService(
            self.client,
            self.user,
            self.context,
            self.conversation,
        )

    async def response(self, save: bool = True):
        if self.update.message and self.update.message.text and self.update.message.text.startswith("/"):
            logger.warning("Command leaked into message handler: %s", self.update.message.text)
            return

        if self.user.remain_frequency <= 0 and self.user.temporary_frequency <= 0:
            await send_message(
                self.context,
                self.user.id,
                f"你的额度已用尽，\r\n当前额度：{self.user.remain_frequency}，临时额度：{self.user.temporary_frequency}\r\n若有疑问联系 @xi_cuicui",
            )
            return

        if self.update.message:
            self.placeholder = await self.update.message.reply_text("思考中")
        else:
            self.placeholder = await self.context.bot.send_message(chat_id=self.user.id, text="思考中")

        asyncio.create_task(self._response_to_user(save))

    async def regen(self):
        factory = MessageFactory(update=self.update, context=self.context)
        if self.user.remain_frequency <= 0 and self.user.temporary_frequency <= 0:
            await send_message(
                self.context,
                self.user.id,
                f"你的额度已用尽，\n当前额度：{self.user.remain_frequency}，临时额度：{self.user.temporary_frequency}\n若有疑问联系 @xi_cuicui",
            )
            return

        try:
            last_input_text = await self.conv_service.undo_last_turn()
            if last_input_text is None:
                await send_message(self.context, self.user.id, "重新生成失败，找不到上一条对话记录。")
                return

            self.placeholder = await self.context.bot.send_message(chat_id=self.user.id, text="重新生成中...")
            self.input = Message(0, last_input_text, "input")
            asyncio.create_task(self._response_to_user(save=True))
        except Exception as error:
            logger.error("Regenerate response failed: %s", error, exc_info=True)
            if self.placeholder:
                await factory.edit(self.placeholder, f"重新生成时出错了：{error}")
            else:
                await send_message(self.context, self.user.id, f"重新生成时出错了：{error}")

    async def undo(self):
        await self.conv_service.undo_last_turn()

    def set_callback_data(self, data: str):
        self.input = Message(0, data, "callback")

    async def _response_to_user(self, save: bool):
        factory = MessageFactory(update=self.update, context=self.context)

        try:
            if not self.input:
                logger.warning("No input message available for private response")
                return

            prompt_service = PromptService(
                user=self.user,
                conversation=self.conversation,
                input_text=self.input.text_raw,
            )
            messages = prompt_service.build_private_chat_prompts()
            final_response_text = await self.conv_service.responder.stream_private_response(
                messages,
                self.placeholder,
            )

            if self.placeholder:
                self.output = Message(self.placeholder.message_id, final_response_text, "output")
                await factory.edit(
                    placeholder=self.placeholder,
                    text=self.output.text_processed,
                    summary=getattr(self.output, "text_summary", None),
                    comment=getattr(self.output, "text_comment", None),
                )
            else:
                self.output = Message(0, final_response_text, "output")

            if contains_nsfw(self.output.text_raw) and self.user.preset == "Default_meeting":
                await send_message(
                    self.context,
                    self.user.id,
                    "检测到您正在使用默认配置，使用 `/preset` 切换 nsfw 配置可获得更好的内容质量",
                )

            if save and self.output:
                self.conv_service.save_turn(self.input, self.output, messages)
        except Exception as error:
            logger.error("Private response failed: %s", error, exc_info=True)
            if self.placeholder:
                await factory.edit(self.placeholder, f"出错了：{error}")
