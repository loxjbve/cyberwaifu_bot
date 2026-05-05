from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from bot_core.data_repository.conv_model import Conversation, DialogMessage, User
from bot_core.services.conversation import Message
from bot_core.services.soul_agent import SoulAgentService, SoulSkillError, SoulSkillRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_user(**overrides) -> User:
    payload = {
        "uid": 1,
        "first_name": "Test",
        "last_name": "User",
        "user_name": "tester",
        "conversations": 0,
        "api": "default-api",
        "char": "test-soul",
        "preset": "Default_meeting",
        "stream": "no",
        "frequency": 0,
        "remain_frequency": 100,
        "balance": 1.5,
        "account_tier": 0,
        "chat_mode": "v2",
    }
    payload.update(overrides)
    return User.model_validate(payload)


def _make_conversation() -> Conversation:
    return Conversation.model_validate(
        {
            "conv_id": 1001,
            "user_id": 1,
            "character": "test-soul",
            "preset": "Default_meeting",
            "summaries": [],
            "turns": 1,
            "created_at": datetime(2026, 1, 1, 0, 0, 0),
            "updated_at": datetime(2026, 1, 1, 0, 0, 0),
            "history": [
                DialogMessage.model_validate(
                    {
                        "role": "user",
                        "turn": 1,
                        "raw_content": "你好",
                        "processed_content": "你好",
                        "created_at": datetime(2026, 1, 1, 0, 0, 0),
                    }
                )
            ],
        }
    )


def _copy_test_soul(tmp_path: Path) -> Path:
    soul_root = tmp_path / "souls" / "test-soul"
    soul_root.mkdir(parents=True)
    for source in (PROJECT_ROOT / "testdata").iterdir():
        if source.is_file():
            (soul_root / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path / "souls"


def test_soul_loader_reads_bundle_and_blocks_path_escape(tmp_path):
    souls_root = _copy_test_soul(tmp_path)
    repository = SoulSkillRepository(souls_root=souls_root)

    bundle = repository.load_bundle("test-soul")

    assert "SKILL.md" in bundle.available_documents
    assert "procedure.md" in bundle.available_documents
    assert "target_account_id" in bundle.manifest_text
    with pytest.raises(SoulSkillError):
        repository.load_bundle("../test-soul")


class FakeLLM:
    def __init__(self):
        self.messages = []
        self.calls = []
        self.outputs = [
            json.dumps(
                {
                    "task_type": "interaction",
                    "documents": ["interaction.md", "../secret.md"],
                    "evidence_boundary": "样本内",
                },
                ensure_ascii=False,
            ),
            "事实：已读 interaction。推断：需要温和回应。建议：保持边界。",
            "<content>这是 V2 回复</content><summary>V2 摘要</summary><comment>暂无</comment>",
        ]

    def set_messages(self, messages):
        self.messages = messages
        self.calls.append(messages)

    async def response(self, stream=False):
        output = self.outputs[len(self.calls) - 1]
        yield output


def test_soul_agent_runs_three_llm_stages_and_final_output(tmp_path):
    souls_root = _copy_test_soul(tmp_path)
    llm = FakeLLM()
    agent = SoulAgentService(
        llm_client=llm,
        user=_make_user(),
        input_text="应该怎么回复？",
        conversation=_make_conversation(),
        repository=SoulSkillRepository(souls_root=souls_root),
    )

    response = asyncio.run(agent.build_response())

    assert response.startswith("<content>这是 V2 回复")
    assert len(llm.calls) == 3
    assert "manifest_json" in llm.calls[0][1]["content"]
    assert "skill_md" in llm.calls[0][1]["content"]
    assert "interaction.md" in llm.calls[1][1]["content"]
    assert '"../secret.md":' not in llm.calls[1][1]["content"]
    assert Message(1, response, "output").text_processed == "这是 V2 回复"
