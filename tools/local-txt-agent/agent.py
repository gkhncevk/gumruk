"""
Core agent logic: talks to a local Ollama model and executes txt-file
operations (rename, edit, merge, split, organize, summarize) on a folder
the user points it at.

Design goal: the model NEVER touches files directly. It only proposes a
plan as strict JSON. The Flask app shows that plan to the user, and only
executes it after the user clicks "Apply" in the UI. This keeps a human
in the loop for anything destructive (renames, overwrites, merges).
"""

import difflib
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

# Structured config files: also writable, but kept as a separate, smaller
# tier from SUPPORTED_EXTENSIONS on purpose. These are a deliberate first
# step into "the agent can write files that aren't free text" -- picked
# because a bad edit here (wrong port, wrong image tag) is typically
# noticeable and easy to revert, unlike a bad edit to actual source code
# (.py/.cs/.ts, still in CONTEXT_ONLY_EXTENSIONS below) which can silently
# break a build in ways that are much harder to spot. Every "write" action
# targeting one of these goes through diff_for_write() so you see exactly
# what changed before approving it, not just a wall of new content to eyeball.
CONFIG_WRITABLE_EXTENSIONS = (".json", ".yaml", ".yml")

# Every extension apply_actions() will accept as a write/rename/move target.
WRITABLE_EXTENSIONS = SUPPORTED_EXTENSIONS + CONFIG_WRITABLE_EXTENSIONS

# Extra file types the agent may READ for context (e.g. to cross-check a
# project's docs against its actual code) but can never write, rename, move,
# or delete -- apply_actions()'s safe_new_path() only accepts WRITABLE_EXTENSIONS,
# so even if a model mistakenly proposed an action on one of these, it would
# be rejected before touching disk. This is what lets the agent answer "does
# this README match what risk.py actually does" without expanding what it's
# allowed to modify.
#
# Deliberately kept read-only even though these are "just text" underneath:
# a small local model rewriting a .cs or .ts file can break a build in a way
# that's much harder to notice and undo than a bad config edit (which at
# least fails loudly and is caught by the diff preview). Source code stays
# read-only until there's a stronger case (e.g. a much better model, or the
# config-writing tier above proving out well) for letting the agent touch it
# directly.
CONTEXT_ONLY_EXTENSIONS = (
    ".py",                                    # Python (ai-service)
    ".cs",                                    # C# (backend-dotnet)
    ".ts", ".tsx", ".js", ".jsx",              # TypeScript/JavaScript (frontend, frontend-nextjs)
    ".html", ".css",                           # markup/styling
)

# Directories that are never worth walking into: dependency/build output
# folders. These aren't hidden (don't start with ".") so the old dot-only
# filter let os.walk descend into e.g. a Next.js project's node_modules --
# hundreds of packages' worth of .json/.js files, which alone can blow a
# small local model's context window (observed: a single node_modules
# pulled the folder summary past 22k tokens, truncating out the actual
# project files the user asked about). Keeping this as an explicit set
# (rather than trying to detect "is this a dependency folder") means it's
# easy to extend as new project types get added to the repo.
EXCLUDED_DIR_NAMES = {
    "node_modules", "bin", "obj", "dist", "build", "__pycache__",
    ".next", "venv", ".venv", ".embedding_cache",
}

# Auto-generated lock files: excluded by exact name regardless of extension
# or size. Even a short preview of one of these is pure noise for a model -
# they're dependency version pins, not something anyone (human or LLM)
# reads for meaning. Keeping this separate from EXCLUDED_DIR_NAMES because
# it's a filename check, not a directory-to-skip check.
EXCLUDED_FILE_NAMES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
    ".sessions.json",  # this agent's own chat-history file -- irrelevant as
    # cross-check context, and would otherwise show up whenever it's asked to
    # scan its own tools/local-txt-agent/ directory.
}

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
    f"({', '.join(SUPPORTED_EXTENSIONS)}) and structured config files "
    f"({', '.join(CONFIG_WRITABLE_EXTENSIONS)}) in a folder on their own computer. You do NOT "
    "execute anything yourself -- you only PROPOSE a plan, and a human approves it (after "
    "seeing exactly what would change) before anything happens.\n\n"
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
    {"type": "delete", "path": "name.txt"},
    {"type": "replace", "path": "name.txt", "find": "exact text copied from the file", "replace": "new text"}
  ]
}

Rules:
- "actions" can be an empty list if the user is just asking a question or you need
  clarification -- in that case put your question/answer in "reply". A question like
  "what files are in this folder" or "what does X say" is answered ENTIRELY in "reply"
  with "actions": [] -- never invent an action for it.
- The ONLY valid values for an action's "type" are: rename, write, replace, merge, split,
  move, delete (exactly as shown in the shape above). Never invent a different type (e.g.
  "list", "read", "summarize") -- those aren't real actions and will simply fail. If what
  the user wants isn't one of these seven operations, it belongs in "reply", not in "actions".
- Only propose actions you have enough information for. If the request is ambiguous,
  make the most reasonable choice given the file contents and explain the choice in "reply"
  rather than leaving actions empty for something clearly actionable.
- Never invent file contents you weren't shown -- if you need to see more of a file, say so
  in "reply" and propose no actions for that file yet.
- When the user asks you to change, rename, or reword a specific word/phrase/value/line
  inside an EXISTING file (e.g. "X yerine Y yaz", "portu 5432'den 5433'e degistir"), ALWAYS
  prefer "replace" over "write": set "find" to the exact text to change, copied
  character-for-character from the file content you were shown (same whitespace, same
  quoting, same casing), and "replace" to what it should become. "find" must match the
  file's content EXACTLY ONCE -- if the text you want to change appears more than once,
  include more of the surrounding line(s) in "find" until it's unique. Never include more
  than the minimum text needed to make the match unique and unambiguous -- do not paste in
  unrelated surrounding lines "just in case".
  "write" regenerates a file's ENTIRE content from what you remember of it, which risks
  silently altering parts you weren't asked to touch (comments, unrelated formatting) --
  this has been observed to happen in practice. Only use "write" when most/all of a file's
  content is genuinely changing, or the file doesn't exist yet. If you do use "write" on an
  existing file for a small change, the "content" you send back must be the file's FULL
  original text with ONLY the requested part changed -- everything else copied verbatim,
  not rephrased, reformatted, or "cleaned up".
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
- .json/.yaml/.yml files are structured config, not free text: when writing new content for one,
  change ONLY the specific key/value the user asked about and leave every other key, value,
  ordering, comment, and indentation exactly as it was in the original -- do not reformat,
  reindent, alphabetize keys, or "clean up" anything you weren't asked to touch. The result must
  be syntactically valid JSON (or YAML). If you're not fully sure the edit keeps the file valid,
  say so in "reply" and propose no action instead of guessing.
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


OLLAMA_TIMEOUT_SECONDS = 300  # local 7B/14B models on a loaded machine can take
# well over 120s for a large prompt - 120 was too tight and produced spurious
# "Read timed out" errors on real hardware under real load (Docker + dotnet +
# npm all running at once), not a sign anything was actually broken.


# Ollama serves every model with a 2048-token context window by default,
# regardless of how large a window the model itself actually supports -- this
# was the first cause of the empty-response bug: logs showed
# "limit=2050 prompt=22574", i.e. Ollama silently truncating the prompt down
# to its default window before the model ever saw most of it.
#
# Setting num_ctx explicitly fixed that, but exposed a second layer of the
# same problem: with num_ctx=8192, Ollama by default reserves roughly half of
# it for the model's own reply (since no num_predict was set), so anything
# over ~4100 prompt tokens still got truncated -- and worse, the truncation
# keeps only the first few tokens (observed: "keep=4"), which drops almost the
# entire system prompt (it's first in the message list) and leaves the model
# with no idea what JSON shape it's supposed to reply in. That's exactly what
# produced the garbage, schema-less JSON dump seen in practice (a raw
# file-path -> content mapping instead of {"reply": ..., "actions": [...]}).
#
# Fixing this for real means two things together: cap num_predict explicitly
# (so Ollama doesn't need to silently reserve half of num_ctx "just in case"),
# and raise num_ctx enough that even a conservative reservation leaves several
# thousand tokens of headroom over what list_folder_preview() below can
# actually produce.
OLLAMA_NUM_CTX = 16384
OLLAMA_NUM_PREDICT = 1024  # replies are meant to be short (see SYSTEM_PROMPT);
# this also stops a confused model from rambling for thousands of tokens (the
# garbage response above ran to 2563 output tokens and took ~170s for a
# question that should've been a one-line JSON reply).


def _ollama_chat(messages, model):
    # requests' default exceptions for "Ollama isn't running" and "the model
    # took too long" are technically accurate but read like a stack trace
    # (ConnectionError's str() includes the internal urllib3 retry machinery)
    # -- translating them into one clear Turkish sentence each is what turns
    # "the app broke" into "here's exactly what to do" for whoever's watching
    # the screen, not just whoever wrote the code.
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.2,
                    "num_ctx": OLLAMA_NUM_CTX,
                    "num_predict": OLLAMA_NUM_PREDICT,
                },
            },
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Ollama'ya bağlanılamadı. Terminalde 'ollama serve' çalışıyor mu kontrol et."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Model {OLLAMA_TIMEOUT_SECONDS} saniye içinde yanıt vermedi -- büyük bir klasör/model "
            "seçili olabilir, ya da bilgisayar başka bir işle meşgul. Daha küçük bir alt klasör "
            "seçmeyi ya da tekrar denemeyi dene."
        )
    if resp.status_code == 404:
        raise RuntimeError(
            f"'{model}' modeli bulunamadı. 'ollama pull {model}' ile indirmen gerekebilir."
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


# Lowered from the original 40 files / 4000 chars each once CONTEXT_ONLY_EXTENSIONS
# grew to 10 extensions across a multi-language repo. Even the first-round
# lowering (20 * 1500) still measured out at ~8.3K tokens on a real scan of the
# gumruk repo root -- fine against OLLAMA_NUM_CTX=16384, but it was that close
# to the smaller num_ctx we started with that a little more margin is worth
# having. Worst case is now 15 * 1200 = 18,000 chars (~4.5K tokens), leaving
# generous headroom under OLLAMA_NUM_CTX minus OLLAMA_NUM_PREDICT for the
# system prompt and conversation history on top.
MATCHED_FILE_PREVIEW_CHARS = 4000  # see the comment above the read() call below


def list_folder_preview(folder, user_message="", max_files=15, preview_chars=1200, max_file_size=MAX_PREVIEW_FILE_SIZE):
    """Build a compact description of the folder's files for the model.

    Returns (entries, skipped) where each entry has an "editable" flag
    (True for WRITABLE_EXTENSIONS, False for CONTEXT_ONLY_EXTENSIONS) and
    "skipped" lists (path, size_bytes) for files that matched an allowed
    extension but were too large to preview in full.

    `user_message` is used for a lightweight relevance boost: within each
    top-level project's file list, a file whose name is literally mentioned
    in the user's question (e.g. "risk.py'deki ... deger") is moved to the
    front, ahead of round-robin's plain alphabetical order. Without this, a
    deep file like ai-service/app/risk.py could sit past max_files even when
    the user explicitly asked about it by name -- fair-share-by-project alone
    doesn't know which specific file within a project actually matters for a
    given question."""
    entries = []
    skipped = []
    all_extensions = WRITABLE_EXTENSIONS + CONTEXT_ONLY_EXTENSIONS
    if not os.path.isdir(folder):
        return entries, skipped

    # os.walk visits subdirectories in whatever order the filesystem happens
    # to return them (not alphabetical, not "fair") -- on a multi-project repo
    # this meant a single top-level folder (observed: backend-dotnet, simply
    # because it came first) could consume the entire max_files budget before
    # any other project got a look-in, e.g. ai-service/ never appearing at
    # all. Grouping candidates by their top-level path component first and
    # then round-robining across groups guarantees every top-level folder
    # (and files sitting directly in `folder`) gets a fair share instead of
    # one subtree crowding out the rest.
    groups = {}  # top-level component -> sorted list of relative paths
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in EXCLUDED_DIR_NAMES]
        for name in files:
            if name in EXCLUDED_FILE_NAMES:
                continue
            lname = name.lower()
            if not lname.endswith(all_extensions):
                continue
            rel = os.path.relpath(os.path.join(root, name), folder)
            top = rel.split(os.sep, 1)[0] if os.sep in rel else ""
            groups.setdefault(top, []).append(rel)

    query = user_message.lower()
    matched_rels = set()
    for rels in groups.values():
        if query:
            for rel in rels:
                if os.path.basename(rel).lower() in query:
                    matched_rels.add(rel)
            rels.sort(key=lambda rel: (rel not in matched_rels, rel))
        else:
            rels.sort()
    group_keys = sorted(groups)
    cursors = {key: 0 for key in group_keys}

    while len(entries) < max_files:
        made_progress = False
        for key in group_keys:
            if len(entries) >= max_files:
                break
            rels = groups[key]
            if cursors[key] >= len(rels):
                continue
            rel = rels[cursors[key]]
            cursors[key] += 1
            made_progress = True

            full = os.path.join(folder, rel)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            if size > max_file_size:
                skipped.append((rel, size))
                continue
            # A file the user named explicitly gets a much bigger preview --
            # 1200 chars is enough for round-robin filler, but not for e.g. a
            # source file whose relevant constant sits after a long docstring
            # (observed: risk.py's CONFIDENCE_THRESHOLD starts at char 1705,
            # past the plain preview_chars cutoff, so the model could only
            # honestly say "I can't see the value" instead of answering).
            # There are normally only one or two name-matched files per
            # question, so this doesn't meaningfully change the overall
            # prompt budget.
            this_preview_chars = MATCHED_FILE_PREVIEW_CHARS if rel in matched_rels else preview_chars
            try:
                with open(full, "r", errors="replace") as f:
                    content = f.read(this_preview_chars)
            except OSError:
                content = ""
            lname = rel.lower()
            entries.append({
                "path": rel,
                "preview": content,
                "editable": lname.endswith(WRITABLE_EXTENSIONS),
            })
        if not made_progress:
            break

    return entries, skipped


def propose_plan(folder, user_message, history, model=None):
    model = model or DEFAULT_MODEL
    files, skipped = list_folder_preview(folder, user_message)

    lines = []
    for e in files:
        tag = "" if e["editable"] else " [READ-ONLY, for context]"
        lines.append(f"- {e['path']}{tag}: {e['preview']!r}")
    for rel, size in skipped:
        lines.append(f"- {rel}: [skipped, {size:,} bytes -- too large to preview in full]")

    folder_summary = "\n".join(lines) or (
        f"(folder is empty or has no {'/'.join(WRITABLE_EXTENSIONS + CONTEXT_ONLY_EXTENSIONS)} files yet)"
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
    # Scan stats for the UI's "what did it actually look at" caption -- makes
    # the folder-preview budgeting (round-robin fairness, size skipping) that
    # this tool relies on for safety visible to whoever's watching, instead
    # of an invisible implementation detail.
    plan["_scan"] = {
        "seen": len(files),
        "editable": sum(1 for e in files if e["editable"]),
        "read_only": sum(1 for e in files if not e["editable"]),
        "skipped": len(skipped),
    }
    return plan


def diff_for_write(folder, rel, new_content):
    """Unified diff between a file's current on-disk content and a proposed
    new "write" content -- so the UI can show exactly what a config-file edit
    would change instead of dumping the whole new file for the user to eyeball
    against memory. Read-only: never touches disk. Returns "" if the file
    doesn't exist yet (a genuinely new file, nothing to diff against) or if
    old and new content are identical."""
    target = os.path.normpath(os.path.join(folder, rel))
    if not target.startswith(os.path.normpath(folder)):
        raise ValueError(f"Path escapes target folder: {rel}")
    try:
        with open(target, "r", errors="replace") as f:
            old_content = f.read()
    except OSError:
        old_content = ""
    if old_content == (new_content or ""):
        return ""
    # keepends=True lines already carry their own trailing "\n", so join with
    # "" (not "\n") -- unified_diff's default lineterm="\n" only adds a
    # newline to the ---/+++/@@ header lines it generates itself, not to the
    # content lines it copies from old_lines/new_lines as-is.
    old_lines = old_content.splitlines(keepends=True)
    new_lines = (new_content or "").splitlines(keepends=True)
    diff_lines = difflib.unified_diff(old_lines, new_lines, fromfile=rel, tofile=rel)
    return "".join(diff_lines)


def compute_replace(content, find, replace):
    """Apply a find/replace to `content`, requiring `find` to match exactly
    once. Shared by apply_actions (to actually change the file) and
    diff_for_action (to preview the change) so the two can never disagree
    about what a "replace" action does.

    Requiring exactly one match (not "first match", not "all matches") is
    the whole point of this action type: it's what makes "replace" safe for
    a small local model to use on a file it can't fully re-verify -- if
    `find` isn't unique, silently picking one occurrence could edit the
    wrong spot, and silently replacing all occurrences could touch code the
    user never asked about. Either way this raises instead of guessing, and
    the model is expected to include more surrounding context in `find`
    until it's unique."""
    count = content.count(find)
    if count == 0:
        raise ValueError("'find' metni dosyada bulunamadı -- dosyanın gösterilen içeriğinden birebir kopyalanmalı")
    if count > 1:
        raise ValueError(
            f"'find' metni dosyada birden fazla yerde geçiyor ({count} kez) -- "
            "hangi yeri kastettiğin belirsiz, daha fazla çevresel bağlam içeren "
            "daha uzun/spesifik bir metin ver"
        )
    return content.replace(find, replace, 1)


def diff_for_action(folder, action):
    """Best-effort unified diff preview for a 'write' or 'replace' action
    targeting a config file, for the approval UI. Returns "" if the action
    isn't diffable (wrong type, path escapes the folder, or a 'replace'
    whose 'find' text isn't found/unique in the file right now) -- this is
    purely a preview and never raises; apply_actions is still the source of
    truth for whether an action actually succeeds when applied."""
    atype = action.get("type")
    rel = str(action.get("path", ""))
    target = os.path.normpath(os.path.join(folder, rel))
    if not target.startswith(os.path.normpath(folder)):
        return ""
    if atype == "write":
        return diff_for_write(folder, rel, action.get("content", ""))
    if atype == "replace":
        try:
            with open(target, "r", errors="replace") as f:
                old_content = f.read()
        except OSError:
            return ""
        try:
            new_content = compute_replace(old_content, action.get("find", ""), action.get("replace", ""))
        except ValueError:
            return ""
        return diff_for_write(folder, rel, new_content)
    return ""


def _touched_paths(action):
    """Every relative path an action could create, overwrite, or remove --
    used to snapshot pre-action state before a batch runs, so a later "Geri
    al" (undo) can restore exactly what was there. Merge deliberately omits
    its "sources" -- merge only reads them, never modifies them."""
    atype = action.get("type")
    if atype in ("rename", "move"):
        return [action.get("from"), action.get("to")]
    if atype in ("write", "replace", "delete"):
        return [action.get("path")]
    if atype == "merge":
        return [action.get("into")]
    if atype == "split":
        return [p.get("name") for p in action.get("parts", [])]
    return []


def _snapshot(folder, rel):
    """Capture whether `rel` currently exists and, if so, its full content --
    the unit of undo state. A path outside `folder` snapshots as "didn't
    exist"; the action touching it will fail its own safety check anyway, so
    there's nothing meaningful to restore."""
    full = os.path.normpath(os.path.join(folder, rel))
    if not full.startswith(os.path.normpath(folder)):
        return {"existed": False, "content": None}
    try:
        with open(full, "r", errors="replace") as f:
            return {"existed": True, "content": f.read()}
    except OSError:
        return {"existed": False, "content": None}


def restore_snapshot(folder, snapshot):
    """The other half of undo: put every path in `snapshot` back exactly how
    _snapshot() found it before the batch ran -- write back the captured
    content if it existed, delete it if it didn't. Mirrors apply_actions'
    {path, ok, detail} result shape."""
    results = []
    for rel, state in snapshot.items():
        full = os.path.normpath(os.path.join(folder, rel))
        if not full.startswith(os.path.normpath(folder)):
            results.append({"path": rel, "ok": False, "detail": "Path escapes target folder"})
            continue
        try:
            if state["existed"]:
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w") as f:
                    f.write(state["content"])
                results.append({"path": rel, "ok": True, "detail": "restored"})
            elif os.path.exists(full):
                os.remove(full)
                results.append({"path": rel, "ok": True, "detail": "removed (was newly created)"})
            else:
                results.append({"path": rel, "ok": True, "detail": "already absent"})
        except OSError as e:
            results.append({"path": rel, "ok": False, "detail": str(e)})
    return results


def apply_actions(folder, actions):
    """Execute a list of approved actions against `folder`. Returns
    (results, snapshot): `results` is a list of {action, ok, detail};
    `snapshot` is a {path: {existed, content}} dict capturing every touched
    path's state *before* this batch ran, ready to hand to restore_snapshot()
    for a one-level "Geri al" (undo). Paths are always resolved relative to
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
        if not rel.lower().endswith(WRITABLE_EXTENSIONS):
            raise ValueError(
                f"Desteklenmeyen dosya türü: {rel} (sadece {', '.join(WRITABLE_EXTENSIONS)} destekleniyor)"
            )
        return safe_path(rel)

    # Snapshot every path the whole batch could touch BEFORE executing
    # anything, so undo reverses back to how things were before the batch
    # started -- not just before the last action in it. First occurrence
    # wins per path (a path touched by two actions in the same batch should
    # still restore to its state before either of them ran).
    snapshot = {}
    for action in actions:
        for rel in _touched_paths(action):
            if rel and rel not in snapshot:
                snapshot[rel] = _snapshot(folder, rel)

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
            elif atype == "replace":
                dst = safe_new_path(action["path"])
                with open(dst, "r", errors="replace") as f:
                    current = f.read()
                new_content = compute_replace(current, action["find"], action["replace"])
                with open(dst, "w") as f:
                    f.write(new_content)
                results.append({"action": action, "ok": True, "detail": "replaced"})
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
    return results, snapshot