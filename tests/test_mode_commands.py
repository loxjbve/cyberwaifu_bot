from __future__ import annotations

import asyncio
from types import SimpleNamespace

from bot_core.command_handlers import mode as mode_module
from bot_core.command_handlers.mode import (
    GroupV1Command,
    GroupV2Command,
    PrivateV1Command,
    PrivateV2Command,
)
from bot_core.data_repository.conv_model import User


def _make_user(**overrides) -> User:
    payload = {
        "uid": 123,
        "first_name": "Test",
        "last_name": "User",
        "user_name": "tester",
        "conversations": 0,
        "api": "default-api",
        "char": "soul-a",
        "preset": "Default_meeting",
        "stream": "no",
        "frequency": 0,
        "remain_frequency": 100,
        "balance": 1.5,
        "account_tier": 0,
        "chat_mode": "v1",
    }
    payload.update(overrides)
    return User.model_validate(payload)


class ReplyMessage(SimpleNamespace):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def _private_update():
    message = ReplyMessage(
        from_user=SimpleNamespace(
            id=123,
            first_name="Test",
            last_name="User",
            username="tester",
        )
    )
    return SimpleNamespace(message=message)


def _group_update():
    message = ReplyMessage(
        chat=SimpleNamespace(id=-100, type="supergroup"),
        from_user=SimpleNamespace(
            id=123,
            first_name="Test",
            last_name="User",
            username="tester",
        ),
    )
    return SimpleNamespace(message=message)


class FakeUserGateway:
    def __init__(self):
        self.updated = []

    def get_or_create(self, **_kwargs):
        return _make_user()

    def update_chat_mode(self, user_id, chat_mode):
        self.updated.append((user_id, chat_mode))


class FakeGroupGateway:
    def __init__(self):
        self.updated = []

    def get_runtime_config(self, group_id):
        return SimpleNamespace(char="soul-a", preset="preset", api="api", chat_mode="v1")

    def update_chat_mode(self, group_id, chat_mode):
        self.updated.append((group_id, chat_mode))


class FakeSoulRepository:
    exists = True

    def has_skill(self, _character):
        return self.exists


def test_private_v2_switch_validates_soul_and_updates(monkeypatch):
    user_gateway = FakeUserGateway()
    monkeypatch.setattr(mode_module, "UserGateway", lambda: user_gateway)
    monkeypatch.setattr(mode_module, "SoulSkillRepository", lambda: FakeSoulRepository())
    update = _private_update()

    asyncio.run(PrivateV2Command().handle(update, SimpleNamespace()))

    assert user_gateway.updated == [(123, "v2")]
    assert update.message.replies == ["已切换到 V2 对话模式。"]


def test_private_v2_rejects_missing_soul(monkeypatch):
    user_gateway = FakeUserGateway()
    fake_repo = FakeSoulRepository()
    fake_repo.exists = False
    monkeypatch.setattr(mode_module, "UserGateway", lambda: user_gateway)
    monkeypatch.setattr(mode_module, "SoulSkillRepository", lambda: fake_repo)
    update = _private_update()

    asyncio.run(PrivateV2Command().handle(update, SimpleNamespace()))

    assert user_gateway.updated == []
    assert "缺少 data/souls/soul-a/SKILL.md" in update.message.replies[0]


def test_private_v1_updates_without_soul_validation(monkeypatch):
    user_gateway = FakeUserGateway()
    monkeypatch.setattr(mode_module, "UserGateway", lambda: user_gateway)
    update = _private_update()

    asyncio.run(PrivateV1Command().handle(update, SimpleNamespace()))

    assert user_gateway.updated == [(123, "v1")]


def test_group_mode_commands_update_group_and_require_admin_meta(monkeypatch):
    group_gateway = FakeGroupGateway()
    monkeypatch.setattr(mode_module, "GroupGateway", lambda: group_gateway)
    monkeypatch.setattr(mode_module, "SoulSkillRepository", lambda: FakeSoulRepository())
    update = _group_update()

    asyncio.run(GroupV2Command().handle(update, SimpleNamespace()))

    assert GroupV1Command.meta.group_admin_required is True
    assert GroupV2Command.meta.group_admin_required is True
    assert group_gateway.updated == [(-100, "v2")]
    assert update.message.replies == ["本群已切换到 V2 对话模式。"]
