import logging

from bot_core.plugin_system import MessageInterceptorMeta, PluginMeta
from plugins.image_rating.commands import FuckCommand, KaoCommand
from plugins.image_rating.private_media import f_or_not
from plugins._helpers import register_commands

logger = logging.getLogger(__name__)

plugin = PluginMeta(id="image_rating", name="Image Rating")


async def private_media_interceptor(update, context) -> bool:
    if not update.message:
        return False
    if not (update.message.photo or update.message.sticker or update.message.animation):
        return False

    user_id = update.message.from_user.id if update.message.from_user else 0
    logger.info("Processing media message for user %s", user_id)
    await f_or_not(update, context)
    return True


def register(registrar):
    register_commands(registrar, [FuckCommand, KaoCommand])
    registrar.register_message_interceptor(
        MessageInterceptorMeta(
            name="private_media_rating",
            chat_type="private",
            priority=100,
        ),
        private_media_interceptor,
    )
