from bot_core.plugin_system import PluginMeta
from plugins.market_tools.commands import GroupCryptoCommand, PrivateCryptoCommand
from plugins.market_tools.tools import MarketToolRegistry
from plugins._helpers import register_commands, register_tool_registry

plugin = PluginMeta(id="market_tools", name="Market Tools")


def register(registrar):
    register_commands(registrar, [PrivateCryptoCommand, GroupCryptoCommand])
    register_tool_registry(registrar, MarketToolRegistry)
    registrar.register_prompt_section("market_tools", MarketToolRegistry.get_prompt_text)
