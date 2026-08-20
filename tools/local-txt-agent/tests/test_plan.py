"""Tests for the plan-proposal path: JSON extraction from a model's raw
output, and propose_plan's prompt construction. propose_plan itself always
calls Ollama, so these mock agent._ollama_chat rather than requiring a real
local model to be running -- these tests should pass with no Ollama, no
network, and no model downloaded.
"""

import pytest

import agent


# ---------- _extract_json ----------

def test_extract_json_parses_clean_json():
    plan = agent._extract_json('{"reply": "hi", "actions": []}')
    assert plan == {"reply": "hi", "actions": []}


def test_extract_json_tolerates_surrounding_prose_or_fences():
    raw = 'Sure, here you go:\n```json\n{"reply": "ok", "actions": []}\n```'
    plan = agent._extract_json(raw)
    assert plan == {"reply": "ok", "actions": []}


def test_extract_json_raises_on_non_json():
    with pytest.raises(ValueError, match="did not return JSON"):
        agent._extract_json("sorry, I can't help with that")


# ---------- propose_plan (Ollama mocked out) ----------

def test_propose_plan_fills_in_missing_reply_and_actions(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages, model: "{}")
    plan = agent.propose_plan(str(tmp_path), "merhaba", [])
    assert plan == {"reply": "", "actions": []}


def test_propose_plan_marks_context_only_files_as_read_only_in_the_prompt(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("editable")
    (tmp_path / "server.py").write_text("read-only")

    captured = {}

    def fake_chat(messages, model):
        captured["messages"] = messages
        return '{"reply": "ok", "actions": []}'

    monkeypatch.setattr(agent, "_ollama_chat", fake_chat)
    agent.propose_plan(str(tmp_path), "dosyaları listele", [])

    user_content = captured["messages"][-1]["content"]
    assert "notes.txt:" in user_content
    assert "server.py [READ-ONLY, for context]" in user_content


def test_propose_plan_passes_conversation_history_through(tmp_path, monkeypatch):
    captured = {}

    def fake_chat(messages, model):
        captured["messages"] = messages
        return '{"reply": "ok", "actions": []}'

    monkeypatch.setattr(agent, "_ollama_chat", fake_chat)
    history = [{"role": "user", "content": "önceki mesaj"}, {"role": "assistant", "content": "önceki cevap"}]
    agent.propose_plan(str(tmp_path), "yeni mesaj", history)

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == history[0]
    assert messages[2] == history[1]
    assert "yeni mesaj" in messages[-1]["content"]
