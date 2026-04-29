# Plugin System

Every runtime plugin lives in its own directory under `plugins/` and must expose
`regist.py`.

```python
from bot_core.plugin_system import PluginMeta

plugin = PluginMeta(id="example", name="Example")

def register(registrar):
    registrar.register_command(MyCommand)
```

Supported registrations:

- `register_command(CommandClass)`
- `register_callback(CallbackClass)`
- `register_message_interceptor(MessageInterceptorMeta(...), handler)`
- `register_lifecycle(startup=..., shutdown=...)`
- `register_agent_tool(AgentToolSpec(...))`
- `register_prompt_section(name, provider)`

Configuration can disable plugins or individual registrations:

```json
{
  "plugins": {
    "enabled": true,
    "items": {
      "trading": {
        "enabled": true,
        "commands": {
          "testliquidation": {"enabled": false}
        }
      }
    }
  }
}
```

Core built-ins such as account settings, character management, conversation
management, API/preset switching, and group management are registered by
`bot_core.builtins` and are not plugin directories.

Plugin implementations should live in their own plugin directory. Compatibility
modules under `bot_core.command_handlers` may re-export moved classes for old
imports, but runtime registration should import from the plugin package.
