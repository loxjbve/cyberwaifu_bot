from bot_core.plugin_system import PluginMeta
from plugins.sign.commands import SignCommand
from plugins._helpers import register_commands

plugin = PluginMeta(id="sign", name="Sign In")


def register(registrar):
    register_commands(registrar, [SignCommand])
