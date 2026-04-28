from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.tools_handler import parse_and_invoke_tool


def test_tool_handler_filters_schema_params(monkeypatch):
    async def fake_tool(command: str):
        return {
            "display": f"display:{command}",
            "llm_feedback": f"feedback:{command}",
        }

    monkeypatch.setattr(
        "agent.tools_handler.get_tool_spec",
        lambda name: SimpleNamespace(parameters={"command": {"type": "string"}})
        if name == "query_db"
        else None,
    )
    monkeypatch.setattr(
        "agent.tools_handler.tool_executor.get_callable",
        lambda name: fake_tool if name == "query_db" else None,
    )

    text, display_results, llm_feedback, had_tool_calls = asyncio.run(
        parse_and_invoke_tool(
            '{"tool_name":"query_db","parameters":{"command":"SELECT 1","ignored":"x"}}'
        )
    )

    assert text == ""
    assert had_tool_calls is True
    assert display_results == [
        {
            "tool_name": "query_db",
            "parameters": {"command": "SELECT 1", "ignored": "x"},
            "result": "display:SELECT 1",
        }
    ]
    assert llm_feedback == [
        {
            "tool_name": "query_db",
            "result": "feedback:SELECT 1",
        }
    ]


def test_tool_handler_handles_unknown_and_multiple_tools(monkeypatch):
    def sync_tool(value: int):
        return {"display": f"value:{value}", "llm_feedback": f"value:{value}"}

    monkeypatch.setattr(
        "agent.tools_handler.get_tool_spec",
        lambda name: SimpleNamespace(parameters={"value": {"type": "integer"}})
        if name == "known_tool"
        else None,
    )
    monkeypatch.setattr(
        "agent.tools_handler.tool_executor.get_callable",
        lambda name: sync_tool if name == "known_tool" else None,
    )

    text, display_results, llm_feedback, had_tool_calls = asyncio.run(
        parse_and_invoke_tool(
            '{"tool_calls":[{"tool_name":"known_tool","parameters":{"value":7}},{"tool_name":"missing_tool","parameters":{"value":9}}]}'
        )
    )

    assert text == ""
    assert had_tool_calls is True
    assert display_results[0]["result"] == "value:7"
    assert "未找到工具" in display_results[1]["result"]
    assert llm_feedback[0]["result"] == "value:7"
    assert "未找到工具" in llm_feedback[1]["result"]
