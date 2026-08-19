"""
Local-only web UI for the txt-file agent.

Run this on your own machine:
    pip install -r requirements.txt
    ollama serve                 # if it isn't already running
    ollama pull llama3.2:3b      # first time only
    python app.py
Then open http://localhost:5001 in your browser.

Nothing here talks to the internet except your own local Ollama server --
the model, the files, and the server all stay on your computer.
"""

import json
import os

from flask import Flask, jsonify, request, render_template

import agent

app = Flask(__name__)

# Conversation history, keyed by a browser-generated session id (so multiple
# tabs/folders don't mix histories). Persisted to a small JSON file next to
# this script so it survives page reloads AND server restarts (Flask's
# debug/auto-reload feature restarts the process on every file save, which
# would otherwise silently wipe an in-memory-only history).
SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sessions.json")


def load_sessions():
    try:
        with open(SESSIONS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sessions():
    try:
        with open(SESSIONS_FILE, "w") as f:
            json.dump(SESSIONS, f)
    except OSError:
        pass  # best-effort -- losing persistence shouldn't break the request


SESSIONS = load_sessions()


@app.route("/")
def index():
    return render_template("index.html", default_model=agent.DEFAULT_MODEL)


@app.route("/api/plan", methods=["POST"])
def api_plan():
    data = request.get_json(force=True)
    folder = os.path.expanduser(data.get("folder", "").strip())
    message = data.get("message", "").strip()
    session_id = data.get("session_id", "default")
    model = data.get("model") or agent.DEFAULT_MODEL

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": f"Folder not found: {folder or '(empty)'}"}), 400
    if not message:
        return jsonify({"error": "Empty message"}), 400

    history = SESSIONS.setdefault(session_id, [])

    try:
        plan = agent.propose_plan(folder, message, history, model=model)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500

    # For "write" actions on config files (.json/.yaml/.yml), attach a diff
    # against the file's actual current content so the approval UI can show
    # what would change line-by-line instead of just a wall of new content --
    # much easier to catch a bad edit in a diff than by eyeballing a full file.
    for action in plan.get("actions", []):
        if action.get("type") == "write" and str(action.get("path", "")).lower().endswith(agent.CONFIG_WRITABLE_EXTENSIONS):
            try:
                action["diff"] = agent.diff_for_write(folder, action["path"], action.get("content", ""))
            except ValueError:
                pass  # path escapes folder -- apply_actions will reject it anyway, no diff to show

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": plan.get("reply", "")})
    # keep history bounded
    SESSIONS[session_id] = history[-30:]
    save_sessions()

    return jsonify(plan)


@app.route("/api/history")
def api_history():
    session_id = request.args.get("session_id", "default")
    return jsonify({"history": SESSIONS.get(session_id, [])})


@app.route("/api/history/clear", methods=["POST"])
def api_history_clear():
    data = request.get_json(force=True)
    session_id = data.get("session_id", "default")
    SESSIONS.pop(session_id, None)
    save_sessions()
    return jsonify({"ok": True})


@app.route("/api/models")
def api_models():
    """Proxy Ollama's model list so the UI can show a dropdown of models
    you've actually downloaded, instead of a free-text field you can typo."""
    try:
        models = agent.list_ollama_models()
        return jsonify({"ok": True, "models": models})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/browse")
def api_browse():
    """List subfolders of a path so the UI can offer a simple point-and-click
    folder picker instead of making you type/paste a full path."""
    raw = request.args.get("path") or "~"
    path = os.path.abspath(os.path.expanduser(raw))

    if not os.path.isdir(path):
        return jsonify({"error": f"Klasör bulunamadı: {path}"}), 400

    try:
        dirs = sorted(
            name for name in os.listdir(path)
            if not name.startswith(".") and os.path.isdir(os.path.join(path, name))
        )
    except PermissionError:
        return jsonify({"error": f"Bu klasöre erişim izni yok: {path}"}), 403

    parent = os.path.dirname(path)
    if parent == path:  # reached filesystem root
        parent = None

    return jsonify({"path": path, "parent": parent, "dirs": dirs})


@app.route("/api/apply", methods=["POST"])
def api_apply():
    data = request.get_json(force=True)
    folder = os.path.expanduser(data.get("folder", "").strip())
    actions = data.get("actions", [])
    session_id = data.get("session_id", "default")

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": f"Folder not found: {folder or '(empty)'}"}), 400

    results = agent.apply_actions(folder, actions)

    # Record what was actually applied (vs. just proposed) so the model has
    # accurate context on the next message -- otherwise it only remembers
    # what it *suggested*, not what you actually approved or rejected.
    if results:
        summary = "; ".join(
            f"{r['action'].get('type')} {'OK' if r['ok'] else 'FAILED (' + r['detail'] + ')'}"
            for r in results
        )
        history = SESSIONS.setdefault(session_id, [])
        note = f"(uyguladığım işlemler: {summary})"
        # Fold this into the assistant's last turn rather than adding a new
        # entry. Chat models are trained on strict user/assistant alternation
        # -- two "user" turns back to back (your real next message right
        # after this status note) confuses smaller models about which one is
        # the actual instruction to act on. Appending to the existing
        # assistant turn keeps the alternation clean.
        if history and history[-1]["role"] == "assistant":
            history[-1]["content"] = (history[-1]["content"] + " " + note).strip()
        else:
            history.append({"role": "assistant", "content": note})
        SESSIONS[session_id] = history[-30:]
        save_sessions()

    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)