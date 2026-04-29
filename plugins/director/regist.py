from bot_core.plugin_system import PluginMeta
from plugins.director.callbacks import DirectorCallback
from plugins.director.commands import DirectorCommand
from plugins._helpers import register_callbacks, register_commands

plugin = PluginMeta(id="director", name="Director Mode")


def register(registrar):
    register_commands(registrar, [DirectorCommand])
    register_callbacks(registrar, [DirectorCallback])
