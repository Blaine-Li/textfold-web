"""The library agent: answers questions about the reader's library, or about one top-level topic, and proposes
changes to its folders and names.

The model never edits the library by itself. Its reply carries an answer and a list of actions; the page shows them,
the reader confirms, and apply() makes them through library.py. Deleting is not one of the actions: a deletion stays
an explicit action in the sidebar.
"""
import json
import re

from . import library, llm, models, store

MAX_ACTIONS = 12
MAX_PAPERS = 500
MAX_HISTORY = 6

SYSTEM = (
    "You are TextFold's library agent. You help a reader understand and organize their own research library: the "
    "papers they have collected, the folders they made, and the topics those folders represent. You answer from the "
    "library listing you are given, and say plainly when something is not in it. You answer with JSON only."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["new_folder", "move_papers", "rename_paper", "rename_folder"]},
                    "name": {"type": "string"},
                    "parent": {"type": "string"},
                    "folder": {"type": "string"},
                    "paper": {"type": "string"},
                    "papers": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["op"],
            },
        },
    },
    "required": ["answer", "actions"],
}


def _label(p):
    return str(p.get("name") or p.get("title") or p.get("id") or "").strip()


def _rows():
    return library.stamp(store.papers())


def _folders():
    d = library.load()
    return d["folders"], d["of"]


def _under(folders, fid):
    """The folder and every folder inside it, however deep."""
    out, more = {fid}, True
    while more:
        more = False
        for f in folders:
            if f.get("parent") in out and f["id"] not in out:
                out.add(f["id"])
                more = True
    return out


def _path(folders, fid, depth=0):
    by = {f["id"]: f for f in folders}
    names, seen = [], set()
    while fid in by and fid not in seen and depth < 40:
        seen.add(fid)
        names.append(by[fid]["name"])
        fid = by[fid].get("parent")
        depth += 1
    return " / ".join(reversed(names))


def context(scope="library", folder_id=None):
    """What the agent is shown: the folders as a tree, and the papers in scope, with their ids and places."""
    folders, of = _folders()
    papers = _rows()
    topic = None
    if scope == "topic":
        topic = next((f for f in folders if f["id"] == folder_id and not f.get("parent")), None)
        if topic is None:
            raise ValueError("no such top-level folder")
        inside = _under(folders, topic["id"])
        papers = [p for p in papers if of.get(p["id"]) in inside]
    elif scope != "library":
        raise ValueError("scope: library or topic")
    return {"scope": scope, "topic": topic, "folders": folders, "of": of, "papers": papers}


def _folder_lines(folders):
    kids = {}
    for f in folders:
        kids.setdefault(f.get("parent"), []).append(f)
    out = []

    def walk(parent, depth):
        for f in kids.get(parent, []):
            out.append(f"{'  ' * depth}- {f['id']}: {f['name']}")
            walk(f["id"], depth + 1)

    walk(None, 0)
    return out


def prompt(data, question, ui=None, history=()):
    """The model's instructions and the listing, in one text. Papers are capped so a large library still fits."""
    folders, papers = data["folders"], data["papers"][:MAX_PAPERS]
    lines = _folder_lines(folders)
    rows = []
    for p in papers:
        authors = ", ".join(str(a) for a in (p.get("authors") or [])[:3])
        place = _path(folders, data["of"].get(p["id"]), 0) if data["of"].get(p["id"]) else "not in a folder"
        rows.append(f"- [{p['id']}] {_label(p)[:180]}" + (f" — {authors[:120]}" if authors else "") + f" — {place}")
    topic = data["topic"]
    focus = ""
    if topic:
        focus = (f'\nThe reader is looking at the topic folder "{topic["name"]}" ({topic["id"]}). Its papers, including '
                 "those in folders inside it, are the ones listed here.\n")
    earlier = [t for t in history if isinstance(t, dict) and (t.get("q") or t.get("a"))][-MAX_HISTORY:]
    talk = ""
    if earlier:
        talk = "\nEarlier in this conversation:\n" + "\n\n".join(
            f"Q: {str(t.get('q') or '')[:1200]}\nA: {str(t.get('a') or '')[:1800]}" for t in earlier) + "\n"
    language = f"The reader's interface language is {ui}." if ui else ""
    return f"""You are helping a reader with their TextFold library.

The library's folders (a folder inside another is indented):
{chr(10).join(lines) or "(no folders yet)"}
{focus}
The papers in scope ({len(papers)} shown, at most {MAX_PAPERS}):
{chr(10).join(rows) or "(no papers yet)"}

How to answer:
- Answer in the language of the question. {language}
- Be concrete: name papers and folders the reader can recognize.
- The listing above is the only source about their library. Do not invent papers, ids, folders or counts.
- You may compare, summarize, suggest topics, find related work in the library, and help decide how to arrange it.
- Actions are proposals, not completed work. Never say you moved, renamed or created something; say what you propose
  and that it waits for confirmation.
- For a purely informational answer return "actions": [].
- Never propose deleting a paper or folder.

Actions you may propose (at most {MAX_ACTIONS}), using only ids from the listing:
  {{"op": "new_folder", "name": "...", "parent": "<existing folder id, omit for top level>", "papers": ["<paper id>"], "reason": "..."}}
  {{"op": "move_papers", "papers": ["<paper id>"], "folder": "<existing folder id, omit to move out>", "reason": "..."}}
  {{"op": "rename_paper", "paper": "<paper id>", "name": "...", "reason": "..."}}
  {{"op": "rename_folder", "folder": "<folder id>", "name": "...", "reason": "..."}}

Return JSON only, with this shape:
{{"answer": "Markdown answer for the reader", "actions": []}}
{talk}
The reader's question:
{question}
"""


def _clean_name(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:80]


def _paper_rows(pids, by):
    out, seen = [], set()
    for pid in pids if isinstance(pids, list) else []:
        pid = str(pid)
        if pid in by and pid not in seen:
            seen.add(pid)
            out.append({"id": pid, "title": _label(by[pid])})
    return out


def prepare_actions(raw, papers, folders, strict=False):
    """Validate and describe the actions a model proposed. Invalid ones are dropped, or ValueError when strict."""
    pby = {p["id"]: p for p in papers}
    fby = {f["id"]: f for f in folders}
    out = []
    for a in (raw if isinstance(raw, list) else [])[:MAX_ACTIONS]:
        if not isinstance(a, dict):
            if strict:
                raise ValueError("bad action")
            continue
        op, reason = a.get("op"), re.sub(r"\s+", " ", str(a.get("reason") or "")).strip()[:300]
        made = None
        if op == "new_folder":
            name = _clean_name(a.get("name"))
            parent = str(a.get("parent") or "")
            ps = _paper_rows(a.get("papers"), pby)
            if name and (not parent or parent in fby):
                made = {"op": op, "name": name, "papers": ps, "reason": reason,
                        **({"parent": {"id": parent, "name": _path(folders, parent)}} if parent else {})}
        elif op == "move_papers":
            fid = str(a.get("folder") or "")
            ps = _paper_rows(a.get("papers"), pby)
            if ps and (not fid or fid in fby):
                made = {"op": op, "papers": ps, "reason": reason,
                        **({"folder": {"id": fid, "name": _path(folders, fid)}} if fid else {})}
        elif op == "rename_paper":
            pid, name = str(a.get("paper") or ""), re.sub(r"\s+", " ", str(a.get("name") or "")).strip()[:200]
            if pid in pby and name:
                made = {"op": op, "name": name, "paper": {"id": pid, "title": _label(pby[pid])}, "reason": reason}
        elif op == "rename_folder":
            fid, name = str(a.get("folder") or a.get("id") or ""), _clean_name(a.get("name"))
            if fid in fby and name:
                made = {"op": op, "name": name, "folder": {"id": fid, "name": _path(folders, fid)}, "reason": reason}
        if made:
            out.append(made)
        elif strict:
            raise ValueError(f"bad {op or 'action'}")
    return out


def apply(actions):
    """Apply confirmed actions in order, all of them validated first. Returns the library after them."""
    if not isinstance(actions, list) or not actions:
        raise ValueError("no actions")
    if len(actions) > MAX_ACTIONS:
        raise ValueError("too many actions")
    papers, folders = _rows(), _folders()[0]
    ready = prepare_actions(actions, papers, folders, strict=True)
    if len(ready) != len(actions):
        raise ValueError("bad action")
    for a in ready:
        if a["op"] == "new_folder":
            body = {"op": "new", "name": a["name"], "papers": [p["id"] for p in a["papers"]]}
            if a.get("parent"):
                body["parent"] = a["parent"]["id"]
            library.change(body)
        elif a["op"] == "move_papers":
            library.change({"op": "move", "papers": [p["id"] for p in a["papers"]],
                            "folder": (a.get("folder") or {}).get("id") or None})
        elif a["op"] == "rename_paper":
            library.name(a["paper"]["id"], a["name"])
        elif a["op"] == "rename_folder":
            library.change({"op": "rename", "id": a["folder"]["id"], "name": a["name"]})
    return {"actions": ready, "folders": library.folders(),
            "papers": library.stamp(store.papers())}


def ask(scope, folder_id, question, ui=None, history=()):
    """Ask the model about the library or a topic. Returns {answer, actions, model, scope, folder}."""
    data = context(scope, folder_id)
    spec = models.ask_spec()
    text = prompt(data, question, ui, history)
    rec, _ = llm.call(text, SCHEMA, spec, store.library_root() / "agent-cache", timeout=300, system=SYSTEM)
    out = rec.get("out") if isinstance(rec, dict) else None
    if not isinstance(out, dict):
        raise RuntimeError("the model did not return an answer")
    answer = str(out.get("answer") or "").strip()[:12000]
    if not answer:
        raise RuntimeError("the model returned an empty answer")
    actions = prepare_actions(out.get("actions"), data["papers"], data["folders"])
    return {"answer": answer, "actions": actions, "model": spec.get("id", ""),
            "scope": scope, "folder": data["topic"]}
