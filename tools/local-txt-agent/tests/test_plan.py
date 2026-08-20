"""Tests for the plan-proposal path: JSON extraction from a model's raw
output, and propose_plan's prompt construction. propose_plan itself always
calls Ollama, so these mock agent._ollama_chat rather than requiring a real
local model to be running -- these tests should pass with no Ollama, no
network, and no model downloaded.
"""

import pytest
import requests

import agent


# ---------- _ollama_chat: friendly error messages ----------
# requests' own exceptions read like a stack trace (ConnectionError's str()
# drags in urllib3's retry internals) -- these confirm the translation to one
# clear Turkish sentence actually happens, not just that *some* error occurs.

def test_ollama_chat_connection_error_message_mentions_ollama_serve(monkeypatch):
    def raise_connection_error(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(requests, "post", raise_connection_error)
    with pytest.raises(RuntimeError, match="ollama serve"):
        agent._ollama_chat([], "llama3.2:3b")


def test_ollama_chat_timeout_message_is_friendly(monkeypatch):
    def raise_timeout(*a, **k):
        raise requests.exceptions.Timeout("boom")

    monkeypatch.setattr(requests, "post", raise_timeout)
    with pytest.raises(RuntimeError, match="saniye içinde yanıt vermedi"):
        agent._ollama_chat([], "llama3.2:3b")


def test_ollama_chat_missing_model_message_suggests_pull(monkeypatch):
    class FakeResp:
        status_code = 404

    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="ollama pull llama3.2:3b"):
        agent._ollama_chat([], "llama3.2:3b")


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
    assert plan["reply"] == ""
    assert plan["actions"] == []


def test_propose_plan_reports_scan_stats(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("editable")
    (tmp_path / "server.py").write_text("read-only")
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages, model: "{}")

    plan = agent.propose_plan(str(tmp_path), "merhaba", [])

    assert plan["_scan"] == {"seen": 2, "editable": 1, "read_only": 1, "skipped": 0}


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
    assert '<file path="notes.txt">' in user_content
    assert '<file path="server.py" readonly="true">' in user_content
    # The actual point of this format: file content appears as real,
    # unescaped text (a real newline), not Python repr()'s '...\n...'.
    assert "\neditable\n" in user_content
    assert "\\n" not in user_content


def test_propose_plan_shows_yaml_content_with_real_indentation_not_escaped(tmp_path, monkeypatch):
    # Regression test for an observed bug: with the old repr()-based preview
    # format, a model asked to build a "replace" action's "find" text for
    # the plain "restart: unless-stopped" line kept inventing a "- " list-item
    # prefix that isn't actually there (docker-compose.yml has real "- " list
    # items nearby, e.g. under "ports:"/"volumes:", but "restart:" itself is
    # a plain key -- not a list item). The theory: an escaped single-line
    # blob makes every line look the same, so the model can't tell list items
    # from plain keys by their real formatting. This asserts the prompt now
    # preserves the file's exact original text -- byte for byte -- so that
    # theory can actually hold.
    yaml_content = (
        "services:\n"
        "  postgres:\n"
        "    ports:\n"
        '      - "5432:5432"\n'
        "    restart: unless-stopped\n"
    )
    (tmp_path / "docker-compose.yml").write_text(yaml_content)

    captured = {}

    def fake_chat(messages, model):
        captured["messages"] = messages
        return '{"reply": "ok", "actions": []}'

    monkeypatch.setattr(agent, "_ollama_chat", fake_chat)
    agent.propose_plan(str(tmp_path), "restart politikasini degistir", [])

    user_content = captured["messages"][-1]["content"]
    assert yaml_content in user_content  # exact original bytes, not repr()'d
    assert "    restart: unless-stopped" in user_content  # real indentation, no invented "- " prefix


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
