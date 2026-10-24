#!/usr/bin/env python3
"""git MCP server — clean-room reimplementation of the recovered tool surface.

Tool names, parameters and descriptions are recovered verbatim from the
shipped `git_mcp_server` binary (RE_REPORT.md §3.3). Transport: MCP over stdio,
newline-delimited JSON-RPC 2.0, like the original.

Usage: python3 client/mcp_git_server.py        # speaks MCP on stdio
"""
import json
import os
import subprocess
import sys


def schema(props, required=()):
    return {
        "type": "object",
        "properties": props,
        "required": list(required),
        "additionalProperties": False,
    }


def s(desc):
    return {"type": "string", "description": desc}


def b(desc):
    return {"type": "boolean", "description": desc}


def i(desc):
    return {"type": "integer", "description": desc}


def sarr(desc):
    return {"type": "array", "items": {"type": "string"}, "description": desc}


REPO = s("Absolute path to the git repository root")

TOOLS = [
    ("git_init", "Initialize a git repository",
     schema({"repo_path": REPO, "initial_branch": s("Optional initial branch name (e.g. main)")}, ["repo_path"])),
    ("git_status", "Show repository status",
     schema({"repo_path": REPO}, ["repo_path"])),
    ("git_diff", "Show changes",
     schema({"repo_path": REPO, "path": s("Optional file path to diff"),
             "staged": b("If true show staged changes instead of unstaged")}, ["repo_path"])),
    ("git_log", "Show commit history",
     schema({"repo_path": REPO, "limit": i("Maximum number of commits to return (default 10)")}, ["repo_path"])),
    ("git_show", "Show a commit",
     schema({"repo_path": REPO, "commit": s("Commit hash or ref to show (default HEAD)")}, ["repo_path"])),
    ("git_add", "Stage files",
     schema({"repo_path": REPO, "paths": sarr("Files to stage")}, ["repo_path", "paths"])),
    ("git_commit", "Create a commit",
     schema({"repo_path": REPO, "message": s("Commit message"),
             "amend": b("If true amend the last commit")}, ["repo_path", "message"])),
    ("git_checkout", "Switch branches or restore files",
     schema({"repo_path": REPO, "target": s("Branch name or file path to checkout"),
             "create_branch": b("If true create a new branch")}, ["repo_path", "target"])),
    ("git_branch", "List, create or delete branches",
     schema({"repo_path": REPO, "name": s("Branch name (for create or delete)"),
             "delete": b("If true delete the branch")}, ["repo_path"])),
    ("git_stash", "Stash changes",
     schema({"repo_path": REPO, "action": s("Stash action: push pop list apply drop (default push)"),
             "message": s("Stash message (for push action)")}, ["repo_path"])),
    ("git_push", "Push to a remote",
     schema({"repo_path": REPO, "remote": s("Remote name (default origin)"),
             "branch": s("Branch to push")}, ["repo_path"])),
    ("git_pull", "Pull from a remote",
     schema({"repo_path": REPO, "remote": s("Remote name (default origin)"),
             "branch": s("Branch to pull")}, ["repo_path"])),
]

def _git(repo, *args):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, env=env)
    out = p.stdout.strip() or p.stderr.strip()
    return out if out else f"git {' '.join(args)}: exit {p.returncode}"


def _require_repo(args):
    repo = args["repo_path"]
    if not os.path.isabs(repo):
        raise ValueError("repo_path must be an absolute path")
    return repo


def call_tool(name, args):
    repo = _require_repo(args)
    if name == "git_init":
        cmd = ["init"]
        if args.get("initial_branch"):
            cmd += ["-b", args["initial_branch"]]
        return _git(repo, *cmd) if os.path.isdir(repo) else "repo_path does not exist"
    if name == "git_status":
        return _git(repo, "status", "--short") or "Working tree clean. No changes."
    if name == "git_diff":
        cmd = ["diff"]
        if args.get("staged"):
            cmd.append("--staged")
        if args.get("path"):
            cmd += ["--", args["path"]]
        return _git(repo, *cmd) or "No differences found."
    if name == "git_log":
        limit = args.get("limit", 10)
        return _git(repo, "log", f"-{limit}", "--oneline") or "No commits found."
    if name == "git_show":
        return _git(repo, "show", args.get("commit", "HEAD"))
    if name == "git_add":
        paths = args["paths"]
        out = _git(repo, "add", "--", *paths)
        return out if out.startswith("fatal") else f"Successfully staged {len(paths)} file(s)."
    if name == "git_commit":
        cmd = ["commit"]
        if args.get("amend"):
            cmd.append("--amend")
        cmd += ["-m", args["message"]]
        return _git(repo, *cmd)
    if name == "git_checkout":
        cmd = ["checkout"]
        if args.get("create_branch"):
            cmd.append("-b")
        cmd.append(args["target"])
        out = _git(repo, *cmd)
        return out if out.startswith("fatal") else f"Switched to '{args['target']}'."
    if name == "git_branch":
        cmd = ["branch"]
        if args.get("delete") and args.get("name"):
            cmd += ["-D", args["name"]]
        elif args.get("name"):
            cmd.append(args["name"])
        return _git(repo, *cmd)
    if name == "git_stash":
        action = args.get("action", "push")
        if action == "push":
            cmd = ["stash", "push"]
            if args.get("message"):
                cmd += ["-m", args["message"]]
            return _git(repo, *cmd)
        return _git(repo, "stash", action)
    if name == "git_push":
        cmd = ["push", args.get("remote", "origin")]
        if args.get("branch"):
            cmd.append(args["branch"])
        return _git(repo, *cmd)
    if name == "git_pull":
        cmd = ["pull", args.get("remote", "origin")]
        if args.get("branch"):
            cmd.append(args["branch"])
        return _git(repo, *cmd)
    raise ValueError(f"unknown tool: {name}")


def _result(text):
    return {"content": [{"type": "text", "text": text}]}


def handle(req):
    method = req.get("method", "")
    mid = req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "git-mcp-server", "version": "linux-reimpl"},
        }}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "tools": [{"name": n, "description": d, "inputSchema": sch}
                      for n, d, sch in TOOLS]}}
    if method == "tools/call":
        params = req.get("params", {})
        try:
            text = call_tool(params.get("name"), params.get("arguments", {}))
            return {"jsonrpc": "2.0", "id": mid, "result": _result(text)}
        except Exception as e:  # contract: tool errors report, never crash the server
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32000, "message": str(e)}}
    if mid is None:  # notification
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
