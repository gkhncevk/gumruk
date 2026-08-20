"""Tests for the plan-proposal path: JSON extraction from a model's raw
output, and propose_plan's prompt construction. propose_plan itself always
calls Ollama, so these mock agent._ollama_post (the shared low-level POST
that both the plain and tool-calling paths funnel through) rather than
requiring a real local model to be running -- these tests should pass with
no Ollama, no network, and no model downloaded.
"""

import pytest
import requests

import agent


def _fake_post(content):
    """An agent._ollama_post replacement for a model that answers
    immediately with `content` and never requests a tool call."""
    return lambda payload: {"content": content}


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
    monkeypatch.setattr(agent, "_ollama_post", _fake_post("{}"))
    plan = agent.propose_plan(str(tmp_path), "merhaba", [])
    assert plan["reply"] == ""
    assert plan["actions"] == []


def test_propose_plan_reports_scan_stats(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("editable")
    (tmp_path / "server.py").write_text("read-only")
    monkeypatch.setattr(agent, "_ollama_post", _fake_post("{}"))

    plan = agent.propose_plan(str(tmp_path), "merhaba", [])

    assert plan["_scan"] == {"seen": 2, "editable": 1, "read_only": 1, "skipped": 0}


def test_propose_plan_marks_context_only_files_as_read_only_in_the_prompt(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("editable")
    (tmp_path / "server.py").write_text("read-only")

    captured = {}

    def fake_post(payload):
        captured["messages"] = payload["messages"]
        return {"content": '{"reply": "ok", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
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

    def fake_post(payload):
        captured["messages"] = payload["messages"]
        return {"content": '{"reply": "ok", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    agent.propose_plan(str(tmp_path), "restart politikasini degistir", [])

    user_content = captured["messages"][-1]["content"]
    assert yaml_content in user_content  # exact original bytes, not repr()'d
    assert "    restart: unless-stopped" in user_content  # real indentation, no invented "- " prefix


def test_propose_plan_passes_conversation_history_through(tmp_path, monkeypatch):
    captured = {}

    def fake_post(payload):
        captured["messages"] = payload["messages"]
        return {"content": '{"reply": "ok", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    history = [{"role": "user", "content": "önceki mesaj"}, {"role": "assistant", "content": "önceki cevap"}]
    agent.propose_plan(str(tmp_path), "yeni mesaj", history)

    messages = captured["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1] == history[0]
    assert messages[2] == history[1]
    assert "yeni mesaj" in messages[-1]["content"]


# ---------- self-correction loop for "replace" actions ----------

def test_validate_replace_actions_returns_no_failures_for_a_clean_plan(tmp_path):
    (tmp_path / "f.yml").write_text("a: 1\n")
    failures = agent._validate_replace_actions(str(tmp_path), [
        {"type": "replace", "path": "f.yml", "find": "a: 1", "replace": "a: 2"}
    ])
    assert failures == []


def test_validate_replace_actions_catches_ambiguous_find(tmp_path):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")
    failures = agent._validate_replace_actions(str(tmp_path), [
        {"type": "replace", "path": "f.yml", "find": "1", "replace": "2"}
    ])
    assert len(failures) == 1
    assert "birden fazla" in failures[0][1]


def test_validate_replace_actions_ignores_non_replace_actions(tmp_path):
    failures = agent._validate_replace_actions(str(tmp_path), [
        {"type": "write", "path": "new.txt", "content": "hi"}
    ])
    assert failures == []


def test_propose_plan_retries_once_when_replace_is_ambiguous_then_succeeds(tmp_path, monkeypatch):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")

    responses = [
        # First attempt: ambiguous "find" (matches both lines).
        '{"reply": "degistiriyorum", "actions": [{"type": "replace", "path": "f.yml", "find": "1", "replace": "2"}]}',
        # Second attempt (after seeing the error): a corrected, unique find.
        '{"reply": "duzelttim", "actions": [{"type": "replace", "path": "f.yml", "find": "a: 1", "replace": "a: 2"}]}',
    ]
    calls = {"n": 0}

    def fake_post(payload):
        raw = responses[calls["n"]]
        calls["n"] += 1
        return {"content": raw}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "a'yi degistir", [])

    assert calls["n"] == 2  # one retry actually happened
    assert plan["_retries"] == 1
    assert plan["actions"][0]["find"] == "a: 1"  # the corrected version made it through


def test_propose_plan_gives_up_after_max_retries_and_still_returns_a_plan(tmp_path, monkeypatch):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")
    # Every attempt is ambiguous -- the model never fixes it.
    bad_response = '{"reply": "degistiriyorum", "actions": [{"type": "replace", "path": "f.yml", "find": "1", "replace": "2"}]}'
    calls = {"n": 0}

    def fake_post(payload):
        calls["n"] += 1
        return {"content": bad_response}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "a'yi degistir", [])

    # 1 initial attempt + MAX_REPLACE_RETRIES retries, no more, no infinite loop.
    assert calls["n"] == 1 + agent.MAX_REPLACE_RETRIES
    assert plan["_retries"] == agent.MAX_REPLACE_RETRIES
    assert plan["actions"]  # still returns whatever it last got, for the UI's ⚠️ warning to catch


def test_propose_plan_does_not_retry_when_there_are_no_replace_actions(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_post(payload):
        calls["n"] += 1
        return {"content": '{"reply": "ok", "actions": [{"type": "write", "path": "new.txt", "content": "hi"}]}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "yeni dosya olustur", [])

    assert calls["n"] == 1  # no wasted retry round trip
    assert plan["_retries"] == 0


# ---------- read_file tool ----------

def test_read_file_tool_returns_full_content(tmp_path):
    (tmp_path / "notes.txt").write_text("satır 1\nsatır 2\n")
    result = agent._read_file_tool(str(tmp_path), "notes.txt")
    assert result == "satır 1\nsatır 2\n"


def test_read_file_tool_rejects_path_escaping_folder(tmp_path):
    result = agent._read_file_tool(str(tmp_path), "../outside.txt")
    assert "Hata" in result
    assert "dışına" in result


def test_read_file_tool_rejects_unsupported_extension(tmp_path):
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    result = agent._read_file_tool(str(tmp_path), "image.png")
    assert "Hata" in result


def test_read_file_tool_reports_missing_file_without_raising(tmp_path):
    result = agent._read_file_tool(str(tmp_path), "does-not-exist.txt")
    assert "Hata" in result


def test_read_file_tool_truncates_very_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "READ_FILE_MAX_CHARS", 10)
    (tmp_path / "big.txt").write_text("x" * 100)
    result = agent._read_file_tool(str(tmp_path), "big.txt")
    assert result.startswith("x" * 10)
    assert "kırpıldı" in result


def test_run_tool_call_dispatches_to_read_file(tmp_path):
    (tmp_path / "notes.txt").write_text("merhaba")
    result = agent._run_tool_call(str(tmp_path), {"function": {"name": "read_file", "arguments": {"path": "notes.txt"}}})
    assert result == "merhaba"


def test_run_tool_call_reports_unknown_tool_without_raising(tmp_path):
    result = agent._run_tool_call(str(tmp_path), {"function": {"name": "delete_everything", "arguments": {}}})
    assert "Hata" in result
    assert "delete_everything" in result


# ---------- tool-calling loop in propose_plan ----------

def test_propose_plan_executes_a_read_file_tool_call_then_returns_final_content(tmp_path, monkeypatch):
    (tmp_path / "risk.py").write_text("CONFIDENCE_THRESHOLD = 0.30")
    calls = []

    def fake_post(payload):
        calls.append(payload)
        if len(calls) == 1:
            # First round: the model asks to read the file instead of
            # answering directly.
            return {
                "content": "",
                "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "risk.py"}}}],
            }
        # Second round: now it answers, having seen the tool result.
        return {"content": '{"reply": "0.30 imiş", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "risk.py'deki eşik değeri ne?", [])

    assert plan["reply"] == "0.30 imiş"
    assert len(calls) == 2
    # The first call offered the tool; the tool's actual result (the file's
    # real content) must have been fed back into the second call's messages.
    assert "tools" in calls[0]
    second_call_messages = calls[1]["messages"]
    assert any(m.get("role") == "tool" and "0.30" in m.get("content", "") for m in second_call_messages)


def test_propose_plan_falls_back_to_plain_answer_when_model_never_uses_tools(tmp_path, monkeypatch):
    # A model with no tool support (or one that just doesn't need it) --
    # confirms the tool-calling path doesn't force a second round trip when
    # none is needed.
    calls = {"n": 0}

    def fake_post(payload):
        calls["n"] += 1
        return {"content": '{"reply": "ok", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "merhaba", [])

    assert calls["n"] == 1
    assert plan["reply"] == "ok"


def test_propose_plan_stops_after_max_tool_rounds_and_forces_a_final_answer(tmp_path, monkeypatch):
    (tmp_path / "notes.txt").write_text("x")
    calls = {"n": 0}

    def fake_post(payload):
        calls["n"] += 1
        if "tools" in payload:
            # Keeps asking to read the same file forever -- should be cut
            # off rather than looping without end.
            return {
                "content": "",
                "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "notes.txt"}}}],
            }
        # The forced final call (no "tools" key, format="json") commits to an answer.
        return {"content": '{"reply": "sonunda", "actions": []}'}

    monkeypatch.setattr(agent, "_ollama_post", fake_post)
    plan = agent.propose_plan(str(tmp_path), "notes.txt ne diyor?", [])

    assert plan["reply"] == "sonunda"
    assert calls["n"] == agent.MAX_TOOL_ROUNDS + 1  # exhausted tool rounds + 1 forced plain call
    assert plan["_retries"] == 0
