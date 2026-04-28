import asyncio
import logging

from agent.llm_functions import generate_summary
from bot_core.data_repository.conv_model import Conversation
from utils.db_utils import dialog_summary_add

logger = logging.getLogger(__name__)


class SummaryService:
    """
    负责处理对话摘要的生成和管理。
    """

    _active_conversations: set[int] = set()

    def __init__(self, conversation: Conversation):
        self.conversation = conversation

    def check_and_generate_summaries_async(self) -> None:
        if not self.conversation.id:
            return

        logger.info("开始检查对话 %s 的摘要情况。", self.conversation.id)
        logger.info("该对话当前轮次为 %s 轮。", self.conversation.turns)
        if self.conversation.turns <= 60:
            logger.info("轮次不足 (<= 60)，跳过摘要检查。")
            return

        if self.conversation.id in self._active_conversations:
            logger.info("对话 %s 的摘要任务已在运行，跳过重复调度。", self.conversation.id)
            return

        area_count = (self.conversation.turns - 1) // 30
        summaries = self.conversation.summaries
        existing_areas = {
            summary.get("summary_area")
            for summary in summaries
            if summary.get("summary_area")
        }

        missing_areas: list[tuple[int, int, str]] = []
        for index in range(1, area_count + 1):
            start = (index - 1) * 30 + 1
            end = index * 30
            area_str = f"{start}-{end}"
            if area_str not in existing_areas:
                missing_areas.append((start, end, area_str))

        if not missing_areas:
            logger.info("对话 %s 的所有摘要区块均已存在。", self.conversation.id)
            return

        logger.info(
            "对话 %s 发现缺失摘要区块 %s，将启动后台任务依次补全。",
            self.conversation.id,
            [area[2] for area in missing_areas],
        )

        async def generate_all_summaries() -> None:
            try:
                for start, end, area_str in missing_areas:
                    result = await self._generate_summary(start, end)
                    if not result:
                        logger.warning("区块 %s 摘要生成失败，后续区块将不再尝试。", area_str)
                        break
            finally:
                self._active_conversations.discard(self.conversation.id)

        self._active_conversations.add(self.conversation.id)
        asyncio.create_task(generate_all_summaries())

    async def _generate_summary(self, start: int, end: int) -> bool:
        if not self.conversation.id:
            logger.error("无法生成摘要，因为没有会话 ID。")
            return False

        area_str = f"{start}-{end}"
        max_retry = 4
        for attempt in range(1, max_retry + 1):
            try:
                summary_text = await generate_summary(
                    self.conversation.id,
                    summary_type="zip",
                    start=start,
                    end=end,
                )

                if not summary_text or len(summary_text) < 200:
                    logger.warning(
                        "第 %s/%s 次尝试：区块 %s 生成的摘要过短(<200字符)，将重试。",
                        attempt,
                        max_retry,
                        area_str,
                    )
                    await asyncio.sleep(5)
                    continue

                result = dialog_summary_add(self.conversation.id, area_str, summary_text)
                if result:
                    logger.info("成功为区块 %s 添加摘要。", area_str)
                    return True

                logger.warning(
                    "第 %s/%s 次尝试：为区块 %s 添加摘要到数据库失败，将重试。",
                    attempt,
                    max_retry,
                    area_str,
                )
            except Exception as error:
                logger.error(
                    "第 %s/%s 次尝试为区块 %s 生成或添加摘要时出错: %s",
                    attempt,
                    max_retry,
                    area_str,
                    error,
                    exc_info=True,
                )

            if attempt < max_retry:
                await asyncio.sleep(5)

        logger.error("区块 %s 摘要生成失败，已达最大重试次数 %s。", area_str, max_retry)
        return False
