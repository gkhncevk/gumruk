"""Tests for list_folder_preview: what the agent actually gets to see before
proposing a plan. Most of the bugs fixed in this tool lived here (context
truncation, node_modules bloat, one project crowding out the rest, a
name-matched file missing its real content) -- this file is what stops them
from coming back silently.
"""

import agent


def test_writable_and_context_only_files_are_tagged_correctly(tmp_path):
    (tmp_path / "notes.txt").write_text("hello")
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "app.py").write_text("print(1)")

    entries, skipped = agent.list_folder_preview(str(tmp_path))
    by_path = {e["path"]: e for e in entries}

    assert by_path["notes.txt"]["editable"] is True
    assert by_path["config.json"]["editable"] is True  # config tier, writable
    assert by_path["app.py"]["editable"] is False  # source code, read-only
    assert skipped == []


def test_lock_files_and_own_session_file_are_excluded(tmp_path):
    (tmp_path / "package-lock.json").write_text('{"lockfileVersion": 3}')
    (tmp_path / ".sessions.json").write_text("[]")
    (tmp_path / "real.json").write_text("{}")

    entries, _ = agent.list_folder_preview(str(tmp_path))
    paths = {e["path"] for e in entries}

    assert "package-lock.json" not in paths
    assert ".sessions.json" not in paths
    assert "real.json" in paths


def test_dependency_directories_are_never_walked(tmp_path):
    deep = tmp_path / "node_modules" / "some-package"
    deep.mkdir(parents=True)
    (deep / "index.js").write_text("module.exports = {}")
    (tmp_path / "real.js").write_text("console.log(1)")

    entries, _ = agent.list_folder_preview(str(tmp_path))
    paths = {e["path"] for e in entries}

    assert not any("node_modules" in p for p in paths)
    assert "real.js" in paths


def test_large_files_are_skipped_not_previewed(tmp_path):
    small = tmp_path / "small.csv"
    small.write_text("a,b\n1,2\n")
    big = tmp_path / "big.csv"
    big.write_text("x" * 1000)

    entries, skipped = agent.list_folder_preview(str(tmp_path), max_file_size=500)

    assert any(e["path"] == "small.csv" for e in entries)
    assert not any(e["path"] == "big.csv" for e in entries)
    assert skipped == [("big.csv", 1000)]


def test_round_robin_gives_every_top_level_project_a_fair_share(tmp_path):
    # Regression test: os.walk's directory order isn't alphabetical or fair,
    # so a single project used to be able to eat the whole max_files budget
    # before any other project got a look-in.
    for project in ("alpha", "beta", "gamma"):
        d = tmp_path / project
        d.mkdir()
        for i in range(5):
            (d / f"file{i}.md").write_text(f"{project} file {i}")

    entries, _ = agent.list_folder_preview(str(tmp_path), max_files=6)
    tops = {e["path"].split("/", 1)[0] for e in entries}

    assert tops == {"alpha", "beta", "gamma"}, (
        "every top-level project should get at least one file in the "
        f"budget, got only: {tops}"
    )


def test_query_named_file_is_prioritized_and_gets_a_bigger_preview(tmp_path):
    project = tmp_path / "ai-service" / "app"
    project.mkdir(parents=True)
    # A long docstring pushes the real value past the default preview_chars,
    # mirroring the real risk.py bug this feature was built to fix.
    long_preamble = "x" * 2000
    (project / "risk.py").write_text(f'"""{long_preamble}"""\nCONFIDENCE_THRESHOLD = 0.30\n')
    (tmp_path / "ai-service" / "other.py").write_text("noise")

    entries, _ = agent.list_folder_preview(
        str(tmp_path), user_message="risk.py'deki CONFIDENCE_THRESHOLD nedir?", max_files=2
    )
    risk_entry = next(e for e in entries if e["path"].endswith("risk.py"))

    assert "CONFIDENCE_THRESHOLD = 0.30" in risk_entry["preview"]


def test_missing_folder_returns_empty_without_raising(tmp_path):
    entries, skipped = agent.list_folder_preview(str(tmp_path / "does-not-exist"))
    assert entries == []
    assert skipped == []
