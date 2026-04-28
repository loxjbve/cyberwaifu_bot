from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bot_core.data_repository.conv_model import Conversation, DialogMessage, Group, User
from bot_core.services.utils import prompt as prompt_module
from bot_core.services.utils.prompt import PromptService, PromptTemplateRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_user(**overrides) -> User:
    payload = {
        "uid": 1,
        "first_name": "Test",
        "last_name": "User",
        "user_name": "tester",
        "conversations": 0,
        "api": "default-api",
        "char": "test-char",
        "preset": "Default_meeting",
        "stream": "no",
        "frequency": 0,
        "remain_frequency": 100,
        "balance": 1.5,
        "account_tier": 0,
    }
    payload.update(overrides)
    return User.model_validate(payload)


def _make_dialog(role: str, turn: int, *, raw: str, processed: str) -> DialogMessage:
    return DialogMessage.model_validate(
        {
            "role": role,
            "turn": turn,
            "raw_content": raw,
            "processed_content": processed,
            "created_at": datetime(2026, 1, 1, 0, 0, 0),
        }
    )


def _make_private_conversation(history: list[DialogMessage]) -> Conversation:
    return Conversation.model_validate(
        {
            "conv_id": 1001,
            "user_id": 1,
            "character": "test-char",
            "preset": "Default_meeting",
            "summaries": [{"summary_area": "1-30", "content": "更早的剧情摘要"}],
            "turns": len(history),
            "created_at": datetime(2026, 1, 1, 0, 0, 0),
            "updated_at": datetime(2026, 1, 1, 0, 0, 0),
            "history": history,
        }
    )


def _load_repo_prompts(prompt_file=None, data="prompt_set_list"):
    prompt_path = PROJECT_ROOT / "prompts" / "prompts.json"
    return json.loads(prompt_path.read_text(encoding="utf-8")).get(data, [])


def test_private_messages_are_system_history_user_and_strip_thinking(monkeypatch):
    PromptTemplateRepository.clear_cache()
    monkeypatch.setattr(prompt_module.file_utils, "load_prompts", _load_repo_prompts)
    monkeypatch.setattr(
        prompt_module.file_utils,
        "load_character_from_file",
        lambda _name: '{"name":"test-char"}',
    )

    history = [
        _make_dialog(role="user", turn=1, raw="你好", processed="你好"),
        _make_dialog(
            role="assistant",
            turn=2,
            raw="<thinking>内部推理</thinking><content>回复一</content><summary>总结一</summary>",
            processed="回复一",
        ),
        _make_dialog(role="user", turn=3, raw="继续", processed="继续"),
        _make_dialog(
            role="assistant",
            turn=4,
            raw="<thinking>更多推理</thinking><content>回复二</content><summary>总结二</summary>",
            processed="回复二",
        ),
    ]
    conversation = _make_private_conversation(history)
    prompt_service = PromptService(
        user=_make_user(),
        conversation=conversation,
        input_text="现在继续这个剧情",
    )

    messages = asyncio.run(prompt_service.build_private_messages())

    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert [message["role"] for message in messages[1:-1]] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert "更早的剧情摘要" in messages[0]["content"]
    assert "用户昵称：" in messages[-1]["content"]
    assert all("<thinking>" not in message["content"] for message in messages[1:-1])


def test_group_messages_include_context_profile_and_image_payload(monkeypatch):
    PromptTemplateRepository.clear_cache()
    monkeypatch.setattr(prompt_module.file_utils, "load_prompts", _load_repo_prompts)
    monkeypatch.setattr(
        prompt_module.file_utils,
        "load_character_from_file",
        lambda _name: '{"name":"group-char"}',
    )
    monkeypatch.setattr(
        prompt_module.db,
        "dialog_content_load",
        lambda conv_id, chat_type="private", raw=False: [
            ("user", 1, "群友发言"),
            ("assistant", 2, "机器人回应"),
        ]
        if chat_type == "group" and conv_id == 2002
        else [],
    )
    monkeypatch.setattr(
        prompt_module.db,
        "group_dialog_get",
        lambda group_id, limit: [("刚刚在聊 BTC", "Alice", "涨疯了", "2026-01-01 00:00:00")]
        if group_id == 77 and limit == 15
        else [],
    )
    monkeypatch.setattr(
        prompt_module.db,
        "user_profile_get",
        lambda user_id: [{"group_id": 77, "user_profile": "偏好聊交易和盘口"}]
        if user_id == 1
        else None,
    )

    async def fake_convert_file_id_to_base64(_file_id: str, _context):
        return {"mime_type": "image/png", "data": "ZmFrZQ=="}

    monkeypatch.setattr(prompt_module.txt, "convert_file_id_to_base64", fake_convert_file_id_to_base64)

    conversation = Conversation.model_validate(
        {
            "conv_id": 2002,
            "user_id": 1,
            "character": "group-char",
            "preset": "Default_meeting",
            "summaries": [],
            "turns": 0,
            "created_at": datetime(2026, 1, 1, 0, 0, 0),
            "updated_at": datetime(2026, 1, 1, 0, 0, 0),
            "history": [],
        }
    )
    prompt_service = PromptService(
        user=_make_user(),
        conversation=conversation,
        group=Group(id=77, name="Test Group"),
        group_config=SimpleNamespace(preset="Default_meeting", char="group-char"),
        input_text="看看这张图",
        telegram_context=SimpleNamespace(bot=object()),
        images=["image-1"],
    )

    messages = asyncio.run(prompt_service.build_group_messages())

    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert [message["role"] for message in messages[1:-1]] == ["user", "assistant"]

    user_content = messages[-1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert any(item["type"] == "image_url" for item in user_content[1:])
    assert "<群聊模式>" in user_content[0]["text"]
    assert "<用户信息>" in user_content[0]["text"]
    assert "<image_input>" in user_content[0]["text"]


def test_prompt_template_repository_rejects_missing_required_markers(monkeypatch):
    PromptTemplateRepository.clear_cache()

    def fake_load_prompts(prompt_file=None, data="prompt_set_list"):
        if data == "prompt_set_list":
            return [{"name": "broken", "combine": ["char_info"]}]
        if data == "prompts":
            return [
                {
                    "name": "char_info",
                    "type": "char_placeholder",
                    "content": "{{char_info}}",
                }
            ]
        raise AssertionError(f"unexpected prompt data request: {data}")

    monkeypatch.setattr(prompt_module.file_utils, "load_prompts", fake_load_prompts)

    repository = PromptTemplateRepository()
    with pytest.raises(ValueError, match="缺少必要模板标记"):
        repository.load_template("broken")
