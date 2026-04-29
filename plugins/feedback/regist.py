from bot_core.plugin_system import PluginMeta
from plugins.feedback.commands import FeedbackCommand
from plugins._helpers import register_commands

plugin = PluginMeta(id="feedback", name="Feedback")


def register(registrar):
    register_commands(registrar, [FeedbackCommand])
