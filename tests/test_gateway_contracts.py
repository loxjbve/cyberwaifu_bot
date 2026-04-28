from __future__ import annotations

import pytest

from bot_core.data_repository.gateways import ConversationGateway, DataAccessError, GroupGateway


def test_conversation_gateway_builds_model_from_repository_results(monkeypatch):
    gateway = ConversationGateway()

    monkeypatch.setattr(
        gateway.conversations,
        "conversation_private_detail_get",
        lambda conv_id: {
            "success": True,
            "data": (conv_id, 1, "char-a", "preset-a", "no", "2026-01-01", "2026-01-02", 2),
        },
    )
    monkeypatch.setattr(
        gateway.conversations,
        "dialog_content_with_timestamps_load",
        lambda conv_id, chat_type="private": {
            "success": True,
            "data": [("user", 1, "hello", "2026-01-01 00:00:00")],
        },
    )
    monkeypatch.setattr(
        gateway.conversations,
        "dialog_content_load",
        lambda conv_id, chat_type="private", raw=False: {
            "success": True,
            "data": [("user", 1, "hello")] if raw else [("user", 1, "hello")],
        },
    )
    monkeypatch.setattr(gateway, "get_summaries", lambda conv_id: [{"summary_area": "1-1", "content": "s"}])

    conversation = gateway.get_private(12345678)

    assert conversation is not None
    assert conversation.id == 12345678
    assert conversation.character == "char-a"
    assert len(conversation.history) == 1
    assert conversation.history[0].raw_content == "hello"


def test_group_gateway_raises_data_access_error_on_group_turn_update_failure(monkeypatch):
    gateway = GroupGateway()

    monkeypatch.setattr(
        gateway.conversations,
        "conversation_group_turns_increment",
        lambda conv_id, turns_increase=0: {"success": False, "error": "boom"},
    )

    with pytest.raises(DataAccessError):
        gateway.update_group_conversation_turn(42, 1)
