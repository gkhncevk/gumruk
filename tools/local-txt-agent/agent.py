"""
Core agent logic: talks to a local Ollama model and executes txt-file
operations (rename, edit, merge, split, organize, summarize) on a folder
the user points it at.

Design goal: the model NEVER touches files directly. It only proposes a
plan as strict JSON. The Flask app shows that plan to the user, and only
executes it after the user clicks "Apply" in the UI. This keeps a human
in the loop for anything destructive (renames, overwrites, merges).
"""

import json
import os
import re
import shutil

import requests

OLLAMA_BASE = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_BASE}/api/chat"
# Small, free, runs comfortably on an 8GB+ Apple Silicon Mac.
# If you have 16GB+ RAM, try "qwen2.5:7b-instruct" or "llama3.1:8b" for
# noticeably better instruction-following -- just `ollama pull` it first
# and change this value (or set the model in the UI).
DEFAULT_MODEL = "llama3.2:3b"

# Plain-text-ish file types this agent is allowed to see AND manage (rename,
# write, merge, split, move, delete). Keeping this an explicit allowlist
# (rather than "any file") means a model mistake can never reach outside the
# kinds of files you actually asked it to manage.
SUPPORTED_EXTENSIONS = (".txt", ".md", ".csv")

# Extra file types the agent may READ for context (e.g. to cross-check a
# project's docs against its actual code) but can never write, rename, move,
# or delete -- apply_actions()'s safe_new_path() only accepts SUPPORTED_EXTENSIONS,
# so even if a model mistakenly proposed an action on one of these, it would
# be rejected before touching disk. This is what lets the agent answer "does
# this README match what risk.py actually does" without expanding what it's
# allowed to modify.
#
# Deliberately kept read-only even though these are "just text" underneath:
# unlike .txt/.md/.csv (free prose / tabular data, where a bad edit at worst
# garbles a note or a row), these are syntactically fragile -- a small local
# model rewriting a .cs file or an appsettings.json can break a build or a
# running config in a way that's much harder to notice and undo. Source code
# and structured config stay read-only until there's a stronger case (e.g. a
# much better model, or per-file human review before every code write) for
# letting the agent touch them directly.
CONTEXT_ONLY_EXTENSIONS = (
    ".py",                                    # Python (ai-service)
    ".cs",                                    # C# (backend-dotnet)
    ".ts", ".tsx", ".js", ".jsx",              # TypeScript/JavaScript (frontend, frontend-nextjs)
    ".json", ".yaml", ".yml",                  # config (appsettings.json, package.json, docker-compose.yml, ...)
    ".html", ".css",                           # markup/styling
)

# Files above this size aren't worth showing a small local model in full --
# a 15,000-row data CSV would eat most of the context window and isn't
# something the model should be reasoning over qualitatively anyway. Skipped
# files are still listed by name (with their size) so the user knows they
# exist, just not previewed.
MAX_PREVIEW_FILE_SIZE = 200_000  # bytes

# Built with plain concatenation (not one big f-string) because the JSON examples below
# contain literal { } braces that must NOT be treated as format placeholders.
SYSTEM_PROMPT = (
    "You are a local file-organizing assistant. You help the user manage plain-text files "
    f"({', '.join(SUPPORTED_EXTENSIONS)}) in a folder on their own computer. You do NOT "
    "execute anything yourself -- you only PROPOSE a plan, and a human approves it before "
    "anything happens.\n\n"
    f"You may also be shown {', '.join(CONTEXT_ONLY_EXTENSIONS)} files from the same folder, "
    "marked as [READ-ONLY, for context] in the folder listing. These give you background (e.g. "
    "actual code/config a .md file is supposed to describe) but you can NEVER propose an action "
    "that writes, renames, moves, or deletes one of them -- only use them to inform what you say "
    "in \"reply\" or to inform an action on a SUPPORTED file (e.g. \"the README says the threshold "
    "is 0.15 but risk.py has 0.30\" is a reply, not a write to risk.py).\n\n"
) + """You will be given the current contents of a folder (filenames and a short preview of \
each file's text) and a user instruction in Turkish or English. Respond with STRICT JSON \
only, no prose outside the JSON, matching this shape:

{
  "reply": "<short natural-language explanation of what you're proposing, in the same language as the user>",
  "actions": [
    {"type": "rename", "from": "old_name.txt", "to": "new_name.txt"},
    {"type": "write", "path": "name.txt", "content": "new full file content"},
    {"type": "merge", "sources": ["a.txt", "b.txt"], "into": "merged.txt"},
    {"type": "split", "source": "big.txt", "parts": [{"name": "part1.txt", "content": "..."}, {"name": "part2.txt", "content": "..."}]},
    {"type": "move", "from": "name.txt", "to": "subfolder/name.txt"},
    {"type": "delete", "path": "name.txt"}
  ]
}

Rules:
- "actions" can be an empty list if the user is just asking a question or you need
  clarification -- in that case put your question/answer in "reply".
- Only propose actions you have enough information for. If the request is ambiguous,
  make the most reasonable choice given the file contents and explain the choice in "reply"
  rather than leaving actions empty for something clearly actionable.
- Never invent file contents you weren't shown -- if you need to see more of a file, say so
  in "reply" and propose no actions for that file yet.
- When the user asks you to replace, rename, or reword a specific word/phrase/label inside a
  file's content (e.g. "X yerine Y yaz", "replace X with Y"), the "content" you write back must
  be the file's FULL original text with ONLY that exact word/phrase changed everywhere it
  occurs -- do not touch, rephrase, or "improve" any other part of the text, and do not change
  a different word that merely looks related. Re-read the original content and the instruction
  carefully before writing the new content, since a wrong edit here directly overwrites the
  user's file.
- File names: when the user does NOT specify an exact filename, choose one that is lowercase,
  hyphen-separated, and based on actual content -- no generic names like "file1". Keep the same
  file extension as the original file you're renaming/basing this on (a .csv stays .csv, a .md
  stays .md) unless the user explicitly asks for a different file type.
- When the user DOES give you an exact filename or exact new name to use (e.g. "adını
  deneme.txt yap", "call it report.txt"), copy that name character-by-character exactly as they
  typed it -- do not "clean it up", hyphenate it, respell it, or otherwise change a single
  letter. If they forgot the extension, add the SAME extension as the file being renamed (not
  always .txt -- a .csv being renamed should get .csv). Getting a user-specified name slightly
  wrong (even one letter) is a real bug, not a style choice.
- .csv files are structured data, not free text: when writing new content for a .csv file,
  keep it valid CSV (comma-separated columns, the same number of columns on every row, keep the
  header row as-is unless asked to change it). Never turn a .csv file's content into paragraphs
  of prose.
- When the user asks you to summarize, explain, or extract information from a file's content
  (e.g. "özetini çıkar", "bu dosyada ne yazıyor", "summarize this") and does NOT ask you to save
  or write that summary anywhere, just answer directly in "reply" with an empty "actions" list --
  do not create a new file for it, and do not use "split" as a workaround for "make a new file
  with different content". Only propose a file action here if the user explicitly asks you to
  save/write the summary to a file, in which case use "write" (a single new file, with content
  that is actually shorter/condensed -- never just the original text copied unchanged, that is
  not a summary).
- Keep "reply" short -- a couple of sentences, not a report.
- Files marked [READ-ONLY, for context] (e.g. .py files) may be read and referenced in "reply",
  but NEVER appear as the "from"/"path"/"into"/"source" of an action -- if the user's instruction
  would require writing to one of them, explain in "reply" why you can't and propose no action
  for that file (you may still propose actions on other, editable files in the same request).
- If a file was listed as skipped for being too large, you were not shown its content -- don't
  guess what's inside it or propose an action based on assumed content; say in "reply" that you'd
  need it summarized in smaller pieces first.
- Output MUST be valid JSON and nothing else.

Example -- summarize without saving (note: no actions, and the reply is a real condensed
summary in your own words, not a copy of the original sentences):
User instruction: "bu dosyanın özetini çıkarır mısın"
File content shown to you: "Yarın saat 15:00'te pazarlama ekibiyle toplantı var. Gündem: Q3
kampanya bütçesi ve yeni reklam görselleri. Katılımcılar: Gökhan, Lara, Esra."
{"reply": "Yarın 15:00'te pazarlama ekibiyle Q3 bütçesi ve yeni reklamlar için toplantı var; katılımcılar Gökhan, Lara ve Esra.", "actions": []}
"""


def _ollama_chat(messages, model):
    resp = requests.post(
        OLLAMA_URL,
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def list_ollama_models():
    """Ask Ollama what models are already downloaded, so the UI can offer a
    dropdown instead of making the user remember/type an exact model name."""
    resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
    resp.raise_for_status()
    data = resp.json()
    return [m["name"] for m in data.get("models", [])]


def _extract_json(text):
    """Ollama with format=json should return clean JSON, but be defensive
    in case a model wraps it in ```json fences or adds stray text."""
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Model did not return JSON: {text[:200]}")
    return json.loads(match.group(0))


def list_folder_preview(folder, max_files=40, preview_chars=4000, max_file_size=MAX_PREVIEW_FILE_SIZE):
    """Build a compact description of the folder's files for the model.

    Returns (entries, skipped) where each entry has an "editable" flag
    (True for SUPPORTED_EXTENSIONS, False for CONTEXT_ONLY_EXTENSIONS) and
    "skipped" lists (path, size_bytes) for files that matched an allowed
    extension but were too large to preview in full."""
    entries = []
    skipped = []
    all_extensions = SUPPORTED_EXTENSIONS + CONTEXT_ONLY_EXTENSIONS
    if not os.path.isdir(folder):
        return entries, skipped
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            lname = name.lower()
            if not lname.endswith(all_extensions):
                continue
            rel = os.path.relpath(os.path.join(root, name), folder)
            full = os.path.join(root, name)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            if size > max_file_size:
                skipped.append((rel, size))
                continue
            try:
                with open(full, "r", errors="replace") as f:
                    content = f.read(preview_chars)
            except OSError:
                content = ""
            entries.append({
                "path": rel,
                "preview": content,
                "editable": lname.endswith(SUPPORTED_EXTENSIONS),
            })
            if len(entries) >= max_files:
                return entries, skipped
    return entries, skipped


def propose_plan(folder, user_message, history, model=None):
    model = model or DEFAULT_MODEL
    files, skipped = list_folder_preview(folder)

    lines = []
    for e in files:
        tag = "" if e["editable"] else " [READ-ONLY, for context]"
        lines.append(f"- {e['path']}{tag}: {e['preview']!r}")
    for rel, size in skipped:
        lines.append(f"- {rel}: [skipped, {size:,} bytes -- too large to preview in full]")

    folder_summary = "\n".join(lines) or (
        f"(folder is empty or has no {'/'.join(SUPPORTED_EXTENSIONS + CONTEXT_ONLY_EXTENSIONS)} files yet)"
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append(
        {
            "role": "user",
            "content": f"Folder contents:\n{folder_summary}\n\nUser instruction: {user_message}",
        }
    )

    raw = _ollama_chat(messages, model)
    plan = _extract_json(raw)
    plan.setdefault("reply", "")
    plan.setdefault("actions", [])
    return plan


def apply_actions(folder, actions):
    """Execute a list of approved actions against `folder`. Returns a list
    of {action, ok, detail} results. Paths are always resolved relative to
    `folder` and cannot escape it."""

    def safe_path(rel):
        target = os.path.normpath(os.path.join(folder, rel))
        if not target.startswith(os.path.normpath(folder)):
            raise ValueError(f"Path escapes target folder: {rel}")
        return target

    def safe_new_path(rel):
        """Like safe_path, but also refuses to create a file whose type
        isn't one this agent is meant to manage -- a guardrail so a model
        mistake can't result in writing/renaming into some other file type
        you never asked it to touch."""
        if not rel.lower().endswith(SUPPORTED_EXTENSIONS):
            raise ValueError(
                f"Desteklenmeyen dosya türü: {rel} (sadece {', '.join(SUPPORTED_EXTENSIONS)} destekleniyor)"
            )
        return safe_path(rel)

    results = []
    for action in actions:
        try:
            atype = action.get("type")
            if atype == "rename":
                src, dst = safe_path(action["from"]), safe_new_path(action["to"])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                results.append({"action": action, "ok": True, "detail": "renamed"})
            elif atype == "move":
                src, dst = safe_path(action["from"]), safe_new_path(action["to"])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                results.append({"action": action, "ok": True, "detail": "moved"})
            elif atype == "write":
                dst = safe_new_path(action["path"])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "w") as f:
                    f.write(action.get("content", ""))
                results.append({"action": action, "ok": True, "detail": "written"})
            elif atype == "merge":
                dst = safe_new_path(action["into"])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "w") as out:
                    for src_name in action["sources"]:
                        with open(safe_path(src_name), "r", errors="replace") as f:
                            out.write(f.read().rstrip() + "\n\n")
                results.append({"action": action, "ok": True, "detail": "merged"})
            elif atype == "split":
                for part in action["parts"]:
                    dst = safe_new_path(part["name"])
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "w") as f:
                        f.write(part.get("content", ""))
                results.append({"action": action, "ok": True, "detail": "split"})
            elif atype == "delete":
                os.remove(safe_path(action["path"]))
                results.append({"action": action, "ok": True, "detail": "deleted"})
            else:
                results.append({"action": action, "ok": False, "detail": f"unknown action type: {atype}"})
        except Exception as e:  # noqa: BLE001 - surface any failure to the UI
            results.append({"action": action, "ok": False, "detail": str(e)})
    return results