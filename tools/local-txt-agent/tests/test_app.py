"""Tests for the Flask HTTP layer (app.py): the routes the UI actually
talks to (plan/apply/undo/history/browse). agent.py's own file-touching
logic is already covered by test_actions.py/test_folder_preview.py -- these
tests check that app.py wires HTTP requests to it correctly (status codes,
error shapes, session bookkeeping), with Ollama always mocked out via
agent._ollama_chat -- no network, no local model required.
"""

import json

import pytest

import agent
import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Redirect session persistence to a throwaway file BEFORE anything else
    # runs, so no test ever reads or overwrites the real
    # tools/local-txt-agent/.sessions.json (which holds your actual chat
    # history) -- and reset the in-memory stores so tests can't see state
    # left over from your real usage or from an earlier test.
    monkeypatch.setattr(app_module, "SESSIONS_FILE", str(tmp_path / "test_sessions.json"))
    app_module.SESSIONS.clear()
    app_module.UNDO_STORE.clear()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


# ---------- /api/plan ----------

def test_plan_rejects_missing_folder(client):
    res = client.post("/api/plan", json={"folder": "", "message": "hi"})
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_plan_rejects_empty_message(client, tmp_path):
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": ""})
    assert res.status_code == 400


def test_plan_success_records_conversation_history(client, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages, model: '{"reply": "merhaba", "actions": []}')
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "selam", "session_id": "s1"})

    assert res.status_code == 200
    data = res.get_json()
    assert data["reply"] == "merhaba"
    assert "_scan" in data  # the scan-stats caption the UI shows under the reply
    assert app_module.SESSIONS["s1"][-2] == {"role": "user", "content": "selam"}
    assert app_module.SESSIONS["s1"][-1] == {"role": "assistant", "content": "merhaba"}


def test_plan_surfaces_ollama_errors_as_500_with_friendly_message(client, tmp_path, monkeypatch):
    def raise_error(messages, model):
        raise RuntimeError("Ollama'ya bağlanılamadı. Terminalde 'ollama serve' çalışıyor mu kontrol et.")

    monkeypatch.setattr(agent, "_ollama_chat", raise_error)
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "selam"})

    assert res.status_code == 500
    assert "ollama serve" in res.get_json()["error"]


def test_plan_flags_ambiguous_replace_on_config_file_instead_of_hiding_it(client, tmp_path, monkeypatch):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages, model: json.dumps({
        "reply": "değiştiriyorum",
        "actions": [{"type": "replace", "path": "f.yml", "find": "1", "replace": "2"}],
    }))
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "degistir"})

    action = res.get_json()["actions"][0]
    assert action.get("diff_unavailable") is True
    assert "diff" not in action


# ---------- /api/apply + /api/undo ----------

def test_apply_then_undo_round_trips(client, tmp_path):
    (tmp_path / "notes.txt").write_text("original")

    apply_res = client.post("/api/apply", json={
        "folder": str(tmp_path),
        "actions": [{"type": "write", "path": "notes.txt", "content": "changed"}],
        "session_id": "s1",
    })
    assert apply_res.status_code == 200
    assert apply_res.get_json()["undoable"] is True
    assert (tmp_path / "notes.txt").read_text() == "changed"

    undo_res = client.post("/api/undo", json={"session_id": "s1"})
    assert undo_res.status_code == 200
    assert (tmp_path / "notes.txt").read_text() == "original"


def test_undo_without_a_prior_apply_returns_400(client):
    res = client.post("/api/undo", json={"session_id": "brand-new-session"})
    assert res.status_code == 400


def test_undo_is_single_use(client, tmp_path):
    (tmp_path / "notes.txt").write_text("v1")
    client.post("/api/apply", json={
        "folder": str(tmp_path),
        "actions": [{"type": "write", "path": "notes.txt", "content": "v2"}],
        "session_id": "s1",
    })

    first = client.post("/api/undo", json={"session_id": "s1"})
    assert first.status_code == 200
    second = client.post("/api/undo", json={"session_id": "s1"})
    assert second.status_code == 400  # nothing left to undo -- can't undo an undo


def test_apply_rejects_missing_folder(client):
    res = client.post("/api/apply", json={"folder": "", "actions": []})
    assert res.status_code == 400


# ---------- /api/history ----------

def test_history_clear_empties_the_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_ollama_chat", lambda messages, model: '{"reply": "ok", "actions": []}')
    client.post("/api/plan", json={"folder": str(tmp_path), "message": "hi", "session_id": "s1"})
    assert app_module.SESSIONS.get("s1")

    res = client.post("/api/history/clear", json={"session_id": "s1"})
    assert res.status_code == 200
    assert "s1" not in app_module.SESSIONS


# ---------- /api/browse ----------

def test_browse_rejects_missing_folder(client, tmp_path):
    res = client.get("/api/browse", query_string={"path": str(tmp_path / "nope")})
    assert res.status_code == 400


def test_browse_lists_subdirectories_only(client, tmp_path):
    (tmp_path / "sub1").mkdir()
    (tmp_path / "sub2").mkdir()
    (tmp_path / "file.txt").write_text("x")

    res = client.get("/api/browse", query_string={"path": str(tmp_path)})
    assert res.status_code == 200
    assert sorted(res.get_json()["dirs"]) == ["sub1", "sub2"]
