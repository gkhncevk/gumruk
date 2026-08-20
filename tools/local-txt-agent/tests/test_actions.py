"""Tests for the parts of agent.py that actually touch disk: apply_actions,
compute_replace, the diff-preview helpers, and undo (restore_snapshot). This
is the security- and correctness-critical half of the agent -- a model only
ever PROPOSES a plan; these functions are what decide whether a proposal can
actually happen, and to what.
"""

import pytest

import agent


# ---------- compute_replace ----------

def test_compute_replace_requires_exactly_one_match():
    assert agent.compute_replace("a=1\nb=2\n", "a=1", "a=9") == "a=9\nb=2\n"


def test_compute_replace_rejects_no_match():
    with pytest.raises(ValueError, match="bulunamadı"):
        agent.compute_replace("a=1\n", "z=9", "z=0")


def test_compute_replace_rejects_ambiguous_match():
    with pytest.raises(ValueError, match="birden fazla"):
        agent.compute_replace("a=1\nb=1\n", "1", "2")


# ---------- apply_actions: extension + path safety ----------

def test_apply_actions_rejects_unwritable_extension(tmp_path):
    results, snapshot = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "Program.cs", "content": "class X {}"}
    ])
    assert results[0]["ok"] is False
    assert "Desteklenmeyen dosya türü" in results[0]["detail"]
    assert not (tmp_path / "Program.cs").exists()


def test_apply_actions_rejects_path_escaping_folder(tmp_path):
    outside = tmp_path.parent / "escaped.txt"
    results, _ = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "../escaped.txt", "content": "pwned"}
    ])
    assert results[0]["ok"] is False
    assert not outside.exists()


def test_apply_actions_unknown_type_fails_cleanly(tmp_path):
    results, _ = agent.apply_actions(str(tmp_path), [{"type": "teleport", "path": "x.txt"}])
    assert results[0]["ok"] is False
    assert "unknown action type" in results[0]["detail"]


# ---------- apply_actions: each action type does what it says ----------

def test_write_creates_a_new_file(tmp_path):
    results, _ = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "new.md", "content": "# hi"}
    ])
    assert results[0]["ok"] is True
    assert (tmp_path / "new.md").read_text() == "# hi"


def test_replace_only_touches_the_matched_text(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        'services:\n  postgres:\n    ports:\n      - "5432:5432"\n'
    )
    results, _ = agent.apply_actions(str(tmp_path), [
        {"type": "replace", "path": "docker-compose.yml", "find": '"5432:5432"', "replace": '"5433:5432"'}
    ])
    assert results[0]["ok"] is True
    content = (tmp_path / "docker-compose.yml").read_text()
    assert '"5433:5432"' in content
    assert content.count("postgres") == 1  # nothing else in the file was touched


def test_merge_concatenates_sources_without_modifying_them(tmp_path):
    (tmp_path / "a.txt").write_text("first")
    (tmp_path / "b.txt").write_text("second")
    results, _ = agent.apply_actions(str(tmp_path), [
        {"type": "merge", "sources": ["a.txt", "b.txt"], "into": "merged.txt"}
    ])
    assert results[0]["ok"] is True
    assert "first" in (tmp_path / "merged.txt").read_text()
    assert "second" in (tmp_path / "merged.txt").read_text()
    assert (tmp_path / "a.txt").read_text() == "first"  # source untouched
    assert (tmp_path / "b.txt").read_text() == "second"


def test_delete_removes_the_file(tmp_path):
    (tmp_path / "gone.txt").write_text("bye")
    results, _ = agent.apply_actions(str(tmp_path), [{"type": "delete", "path": "gone.txt"}])
    assert results[0]["ok"] is True
    assert not (tmp_path / "gone.txt").exists()


# ---------- diff_for_write / diff_for_action ----------

def test_diff_for_write_shows_only_the_changed_line(tmp_path):
    (tmp_path / "f.json").write_text('{\n  "a": 1\n}\n')
    diff = agent.diff_for_write(str(tmp_path), "f.json", '{\n  "a": 2\n}\n')
    assert '-  "a": 1' in diff
    assert '+  "a": 2' in diff


def test_diff_for_write_is_empty_when_content_is_unchanged(tmp_path):
    (tmp_path / "f.json").write_text('{"a": 1}')
    assert agent.diff_for_write(str(tmp_path), "f.json", '{"a": 1}') == ""


def test_diff_for_action_write_and_replace_agree_on_the_result(tmp_path):
    (tmp_path / "f.yml").write_text("port: 5432\n")
    write_diff = agent.diff_for_action(str(tmp_path), {
        "type": "write", "path": "f.yml", "content": "port: 5433\n"
    })
    replace_diff = agent.diff_for_action(str(tmp_path), {
        "type": "replace", "path": "f.yml", "find": "5432", "replace": "5433"
    })
    assert write_diff == replace_diff


def test_diff_for_action_returns_empty_for_ambiguous_replace(tmp_path):
    (tmp_path / "f.yml").write_text("a: 1\nb: 1\n")
    diff = agent.diff_for_action(str(tmp_path), {
        "type": "replace", "path": "f.yml", "find": "1", "replace": "2"
    })
    assert diff == ""  # preview never guesses; apply_actions will reject it too


# ---------- undo (snapshot + restore) ----------

def test_undo_restores_overwritten_file(tmp_path):
    (tmp_path / "notes.txt").write_text("original")
    _, snapshot = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "notes.txt", "content": "changed"}
    ])
    assert (tmp_path / "notes.txt").read_text() == "changed"

    agent.restore_snapshot(str(tmp_path), snapshot)
    assert (tmp_path / "notes.txt").read_text() == "original"


def test_undo_deletes_a_file_that_was_newly_created(tmp_path):
    _, snapshot = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "brand-new.txt", "content": "hi"}
    ])
    assert (tmp_path / "brand-new.txt").exists()

    agent.restore_snapshot(str(tmp_path), snapshot)
    assert not (tmp_path / "brand-new.txt").exists()


def test_undo_reverses_a_rename(tmp_path):
    (tmp_path / "a.txt").write_text("content")
    _, snapshot = agent.apply_actions(str(tmp_path), [{"type": "rename", "from": "a.txt", "to": "b.txt"}])
    assert (tmp_path / "b.txt").exists() and not (tmp_path / "a.txt").exists()

    agent.restore_snapshot(str(tmp_path), snapshot)
    assert (tmp_path / "a.txt").exists() and not (tmp_path / "b.txt").exists()
    assert (tmp_path / "a.txt").read_text() == "content"


def test_undo_restores_a_deleted_file(tmp_path):
    (tmp_path / "c.csv").write_text("x,y\n1,2\n")
    _, snapshot = agent.apply_actions(str(tmp_path), [{"type": "delete", "path": "c.csv"}])
    assert not (tmp_path / "c.csv").exists()

    agent.restore_snapshot(str(tmp_path), snapshot)
    assert (tmp_path / "c.csv").read_text() == "x,y\n1,2\n"


def test_undo_snapshot_captures_pre_batch_state_not_mid_batch_state(tmp_path):
    # Two actions in one batch both touch f.txt -- undo should restore to
    # how it was BEFORE the batch, not to some intermediate state.
    (tmp_path / "f.txt").write_text("v0")
    _, snapshot = agent.apply_actions(str(tmp_path), [
        {"type": "write", "path": "f.txt", "content": "v1"},
        {"type": "write", "path": "f.txt", "content": "v2"},
    ])
    assert (tmp_path / "f.txt").read_text() == "v2"

    agent.restore_snapshot(str(tmp_path), snapshot)
    assert (tmp_path / "f.txt").read_text() == "v0"
