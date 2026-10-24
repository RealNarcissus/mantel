#!/usr/bin/env python3
"""obsidian MCP server — clean-room reimplementation of the recovered tool surface.

Tool names are recovered verbatim from the shipped `obsidian_mcp_server`
binary (RE_REPORT.md §3.3); the wikilink/markdown-link regexes, .trash
semantics, default vault locations and result wordings come from the same
strings sweep. Field-level schemas for create/append/patch/manage_tags were
only partially recovered (hash-named Go shapes) — those take pragmatic
parameters. Transport: MCP over stdio, newline-delimited JSON-RPC 2.0.

Usage: python3 client/mcp_obsidian_server.py
"""
import json
import os
import re
import shutil
import sys

WIKILINK = re.compile(r"\[\[([^\]\|#]+)(?:[\|#][^\]]*)?\]\]")
MDLINK = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")
HEADING = r"(?m)^#+\s+%s\s*$"
DEFAULT_VAULT = os.path.expanduser("~/Documents/Obsidian Vault")
RULE_FILES = ("AGENTS.md", "CLAUDE.md")


def s(desc):
    return {"type": "string", "description": desc}


def b(desc):
    return {"type": "boolean", "description": desc}


def i(desc):
    return {"type": "integer", "description": desc}


def schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": False}


VAULT = s('Vault path (default: discovered active vault or "~/Documents/Obsidian Vault"; '
          "omit to scan all discovered vaults)")
NOTE_PATH = s("Note path relative to the vault root")

TOOLS = [
    ("obsidian_init_vault", "Initialize a vault",
     schema({"vault_path": VAULT}, ["vault_path"])),
    ("obsidian_list_notes", "List notes in the vault",
     schema({"vault_path": VAULT, "directory_path": s("Optional subdirectory")})),
    ("obsidian_read_note", "Read one note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH}, ["note_path"])),
    ("obsidian_create_note", "Create a note",
     schema({"vault_path": VAULT, "note_name": s("Note name (markdown)"),
             "directory_path": s("Optional directory"),
             "content": s("Initial content")}, ["note_name"])),
    ("obsidian_append_note", "Append content to a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH,
             "content": s("Content to append")}, ["note_path", "content"])),
    ("obsidian_patch_note", "Replace a heading section in a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH,
             "heading": s("Heading text to match"),
             "content": s("Replacement content")}, ["note_path", "heading", "content"])),
    ("obsidian_delete_note", "Delete a note (to .trash unless permanent)",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH,
             "permanent": b("If true delete without trashing")}, ["note_path"])),
    ("obsidian_move_note", "Move/rename a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH,
             "path": s("Destination path")}, ["note_path", "path"])),
    ("obsidian_create_directory", "Create a directory",
     schema({"vault_path": VAULT, "directory_path": s("Directory to create"),
             "subdirectory": s("Optional nested directory")}, ["directory_path"])),
    ("obsidian_search_notes", "Search note contents",
     schema({"vault_path": VAULT, "query": s("Search query"),
             "case_sensitive": b("Match case exactly"),
             "limit": i("Maximum results (default 50)")}, ["query"])),
    ("obsidian_list_tags", "List tags with note counts",
     schema({"vault_path": VAULT})),
    ("obsidian_manage_tags", "Add or remove a tag on a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH, "tag": s("Tag name"),
             "action": s("add or remove")}, ["note_path", "tag", "action"])),
    ("obsidian_get_backlinks", "Find notes linking to a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH}, ["note_path"])),
    ("obsidian_get_outgoing_links", "Find links from a note",
     schema({"vault_path": VAULT, "note_path": NOTE_PATH}, ["note_path"])),
    ("obsidian_get_rules", "Discover agent rule files (AGENTS.md / CLAUDE.md)",
     schema({"vault_path": VAULT})),
]


def discover_vaults(vault_path=None):
    if vault_path:
        return [vault_path]
    if os.environ.get("OBSIDIAN_VAULT_PATH"):
        return [os.environ["OBSIDIAN_VAULT_PATH"]]
    if os.path.isdir(DEFAULT_VAULT):
        return [DEFAULT_VAULT]
    return []


def vault_of(args):
    found = discover_vaults(args.get("vault_path"))
    if not found:
        raise ValueError('no vault found (set OBSIDIAN_VAULT_PATH or pass vault_path)')
    return found[0]


def note_file(vault, note_path):
    full = os.path.abspath(os.path.join(vault, note_path))
    if not full.startswith(os.path.abspath(vault) + os.sep):
        raise ValueError("note_path escapes the vault")
    return full


def md_files(vault):
    for root, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in (".trash", ".obsidian", ".git")]
        for f in sorted(files):
            if f.endswith(".md"):
                yield os.path.join(root, f)


def call_tool(name, args):
    vault = vault_of(args)
    if not os.path.isdir(vault):
        raise ValueError(f"vault does not exist: {vault}")

    if name == "obsidian_init_vault":
        os.makedirs(os.path.join(vault, ".trash"), exist_ok=True)
        return "This vault was initialized by the Gemini Agent."
    if name == "obsidian_list_notes":
        base = os.path.join(vault, args.get("directory_path", ""))
        rels = [os.path.relpath(p, vault) for p in md_files(base)]
        return "\n".join(rels) if rels else "No notes found."
    if name == "obsidian_read_note":
        path = note_file(vault, args["note_path"])
        if not os.path.isfile(path):
            raise ValueError(f"note not found: {args['note_path']}")
        return open(path, encoding="utf-8").read()
    if name == "obsidian_create_note":
        d = os.path.join(vault, args.get("directory_path", ""))
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, args["note_name"])
        if not path.endswith(".md"):
            path += ".md"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(args.get("content", ""))
        return f"Created and wrote note '{os.path.relpath(path, vault)}'"
    if name == "obsidian_append_note":
        path = note_file(vault, args["note_path"])
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(args["content"])
        return f"Successfully appended content to '{args['note_path']}'"
    if name == "obsidian_patch_note":
        path = note_file(vault, args["note_path"])
        text = open(path, encoding="utf-8").read()
        heading = args["heading"].lstrip("#").strip()
        pat = re.compile(HEADING % re.escape(heading))
        if not pat.search(text):
            raise ValueError(f"heading not found: {args['heading']}")
        # replace the content of the matched heading's section up to the next heading
        m = pat.search(text)
        nxt = re.search(r"(?m)^#+\s+", text[m.end():])
        end = m.end() + nxt.start() if nxt else len(text)
        text = text[:m.end()] + "\n" + args["content"] + "\n" + text[end:]
        open(path, "w", encoding="utf-8").write(text)
        return f"Patched section '{args['heading']}' in '{args['note_path']}'"
    if name == "obsidian_delete_note":
        path = note_file(vault, args["note_path"])
        if args.get("permanent"):
            os.remove(path)
            return f"Deleted '{args['note_path']}'"
        trash = os.path.join(vault, ".trash")
        os.makedirs(trash, exist_ok=True)
        shutil.move(path, os.path.join(trash, os.path.basename(path)))
        return f"Moved '{args['note_path']}' to vault .trash"
    if name == "obsidian_move_note":
        src = note_file(vault, args["note_path"])
        dst = note_file(vault, args["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        return f"Moved '{args['note_path']}' to '{args['path']}'"
    if name == "obsidian_create_directory":
        d = os.path.join(vault, args["directory_path"], args.get("subdirectory", ""))
        os.makedirs(d, exist_ok=True)
        return f"Created directory '{os.path.relpath(d, vault)}'"
    if name == "obsidian_search_notes":
        query = args["query"]
        limit = args.get("limit", 50)
        hits = []
        for p in md_files(vault):
            text = open(p, encoding="utf-8").read()
            hay = text if args.get("case_sensitive") else text.lower()
            needle = query if args.get("case_sensitive") else query.lower()
            if needle in hay:
                hits.append(os.path.relpath(p, vault))
            if len(hits) >= limit:
                break
        return "\n".join(hits) if hits else "No matching notes."
    if name == "obsidian_list_tags":
        notes_by_tag = {}
        for p in md_files(vault):
            text = open(p, encoding="utf-8").read()
            for tag in set(re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", text)):
                notes_by_tag.setdefault(tag, set()).add(os.path.relpath(p, vault))
        return "\n".join(f"- #{t} ({len(v)} note(s))"
                         for t, v in sorted(notes_by_tag.items())) or "No tags found."
    if name == "obsidian_manage_tags":
        path = note_file(vault, args["note_path"])
        text = open(path, encoding="utf-8").read()
        tag = args["tag"].lstrip("#")
        if args["action"] == "add":
            text = text.rstrip("\n") + f"\n- #{tag}\n"
        else:
            text = re.sub(rf"(?m)^-\s+#{re.escape(tag)}\s*\n", "", text)
        open(path, "w", encoding="utf-8").write(text)
        return f"Tag '{tag}' {args['action']}ed on '{args['note_path']}'"
    if name == "obsidian_get_backlinks":
        target = os.path.splitext(os.path.basename(args["note_path"]))[0]
        hits = []
        for p in md_files(vault):
            text = open(p, encoding="utf-8").read()
            if any(m.group(1).strip() == target for m in WIKILINK.finditer(text)) or \
               any(target in m.group(2) for m in MDLINK.finditer(text)):
                hits.append(os.path.relpath(p, vault))
        return "\n".join(hits) if hits else "No backlinks found."
    if name == "obsidian_get_outgoing_links":
        path = note_file(vault, args["note_path"])
        text = open(path, encoding="utf-8").read()
        links = [m.group(1).strip() for m in WIKILINK.finditer(text)]
        links += [m.group(2) for m in MDLINK.finditer(text)]
        header = f"Found {len(links)} outgoing link(s) in '{args['note_path']}':"
        return "\n".join([header] + links) if links else header
    if name == "obsidian_get_rules":
        lines = []
        for root, dirs, files in os.walk(vault):
            dirs[:] = [d for d in dirs if d not in (".trash", ".obsidian", ".git")]
            for f in files:
                if f in RULE_FILES:
                    lines.append(os.path.relpath(os.path.join(root, f), vault))
        out = ["### Rule Files in Vault"] + sorted(lines)
        if len(lines) > len(RULE_FILES):
            out.append("### Other Folder-Specific Rule Files in Vault")
        return "\n".join(out)
    raise ValueError(f"unknown tool: {name}")


def handle(req):
    method = req.get("method", "")
    mid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
            "serverInfo": {"name": "obsidian-mcp-server", "version": "linux-reimpl"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "tools": [{"name": n, "description": d, "inputSchema": sc}
                      for n, d, sc in TOOLS]}}
    if method == "tools/call":
        params = req.get("params", {})
        try:
            text = call_tool(params.get("name"), params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as e:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32000, "message": str(e)}}
    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        resp = handle(json.loads(line))
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
