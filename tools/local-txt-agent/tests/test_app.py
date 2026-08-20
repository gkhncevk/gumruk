"""Tests for the Flask HTTP layer (app.py): the routes the UI actually
talks to (plan/apply/undo/history/browse). agent.py's own file-touching
logic is already covered by test_actions.py/test_folder_preview.py -- these
tests check that app.py wires HTTP requests to it correctly (status codes,
error shapes, session bookkeeping), with Ollama always mocked out via
agent._ollama_post (the shared low-level POST both the plain and
tool-calling paths funnel through) -- no network, no local model required.
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
    monkeypatch.setattr(agent, "_ollama_post", lambda payload: {"content": '{"reply": "merhaba", "actions": []}'})
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "selam", "session_id": "s1"})

    assert res.status_code == 200
    data = res.get_json()
    assert data["reply"] == "merhaba"
    assert "_scan" in data  # the scan-stats caption the UI shows under the reply
    assert app_module.SESSIONS["s1"][-2] == {"role": "user", "content": "selam"}
    assert app_module.SESSIONS["s1"][-1] == {"role": "assistant", "content": "merhaba"}


def test_plan_surfaces_ollama_errors_as_500_with_friendly_message(client, tmp_path, monkeypatch):
    def raise_error(payload):
        raise RuntimeError("Ollama'ya bağlanılamadı. Terminalde 'ollama serve' çalışıyor mu kontrol et.")

    monkeypatch.setattr(agent, "_ollama_post", raise_error)
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "selam"})

    assert res.status_code == 500
    assert "ollama serve" in res.get_json()["error"]


def test_plan_flags_ambiguous_replace_on_config_file_instead_of_hiding_it(client, tmp_path, monkeypatch):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")
    monkeypatch.setattr(agent, "_ollama_post", lambda payload: {"content": json.dumps({
        "reply": "değiştiriyorum",
        "actions": [{"type": "replace", "path": "f.yml", "find": "1", "replace": "2"}],
    })})
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "degistir"})

    action = res.get_json()["actions"][0]
    assert action.get("diff_unavailable") is True
    assert "diff" not in action


def test_plan_shows_a_diff_for_txt_writes_too_not_just_config(client, tmp_path, monkeypatch):
    # Diff previews used to be config-only (.json/.yaml/.yml); a .txt/.md/.csv
    # overwrite is no safer to eyeball as a raw content dump than a config
    # file is, so this should get the same treatment.
    (tmp_path / "notes.txt").write_text("eski içerik")
    monkeypatch.setattr(agent, "_ollama_post", lambda payload: {"content": json.dumps({
        "reply": "güncelliyorum",
        "actions": [{"type": "write", "path": "notes.txt", "content": "yeni içerik"}],
    })})
    res = client.post("/api/plan", json={"folder": str(tmp_path), "message": "güncelle"})

    action = res.get_json()["actions"][0]
    assert "diff" in action
    assert "-eski içerik" in action["diff"]
    assert "+yeni içerik" in action["diff"]


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


def test_undo_empties_after_its_one_entry_is_used(client, tmp_path):
    (tmp_path / "notes.txt").write_text("v1")
    client.post("/api/apply", json={
        "folder": str(tmp_path),
        "actions": [{"type": "write", "path": "notes.txt", "content": "v2"}],
        "session_id": "s1",
    })

    first = client.post("/api/undo", json={"session_id": "s1"})
    assert first.status_code == 200
    assert first.get_json()["more_available"] is False
    second = client.post("/api/undo", json={"session_id": "s1"})
    assert second.status_code == 400  # nothing left -- only one batch had been applied


def test_undo_chains_through_multiple_applies_in_reverse_order(client, tmp_path):
    # A proper LIFO stack: three applies, three undos, each one reversing
    # exactly the most recent remaining change -- walking all the way back
    # to the original content, not just the last edit.
    f = tmp_path / "notes.txt"
    f.write_text("v0")
    for content in ("v1", "v2", "v3"):
        res = client.post("/api/apply", json={
            "folder": str(tmp_path),
            "actions": [{"type": "write", "path": "notes.txt", "content": content}],
            "session_id": "s1",
        })
        assert res.get_json()["undoable"] is True

    assert f.read_text() == "v3"

    undo1 = client.post("/api/undo", json={"session_id": "s1"})
    assert undo1.get_json()["more_available"] is True
    assert f.read_text() == "v2"

    undo2 = client.post("/api/undo", json={"session_id": "s1"})
    assert undo2.get_json()["more_available"] is True
    assert f.read_text() == "v1"

    undo3 = client.post("/api/undo", json={"session_id": "s1"})
    assert undo3.get_json()["more_available"] is False
    assert f.read_text() == "v0"

    # Stack is now empty -- a fourth undo has nothing left to do.
    undo4 = client.post("/api/undo", json={"session_id": "s1"})
    assert undo4.status_code == 400


def test_undo_stack_is_bounded_by_max_undo_depth(client, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "MAX_UNDO_DEPTH", 2)
    f = tmp_path / "notes.txt"
    f.write_text("v0")
    for content in ("v1", "v2", "v3"):  # 3 applies, but the cap is 2
        client.post("/api/apply", json={
            "folder": str(tmp_path),
            "actions": [{"type": "write", "path": "notes.txt", "content": content}],
            "session_id": "s1",
        })

    # Only the 2 most recent batches are undoable -- the oldest (v0 -> v1)
    # fell off the bounded stack, so the earliest we can get back to is v1.
    client.post("/api/undo", json={"session_id": "s1"})
    client.post("/api/undo", json={"session_id": "s1"})
    assert f.read_text() == "v1"
    last_undo = client.post("/api/undo", json={"session_id": "s1"})
    assert last_undo.status_code == 400


def test_apply_rejects_missing_folder(client):
    res = client.post("/api/apply", json={"folder": "", "actions": []})
    assert res.status_code == 400


# ---------- /api/history ----------

def test_history_clear_empties_the_session(client, tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_ollama_post", lambda payload: {"content": '{"reply": "ok", "actions": []}'})
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
