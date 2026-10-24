"""Skill tool registry: the recovered MCP tool surface exposed as Gemini
function declarations (PROTOCOL_SPEC.md §3.3 — 12 git + 15 obsidian tools).

Schemas and wordings are the recovered ones (RE_REPORT.md §3.3); execution
delegates to the clean-room MCP servers' `call_tool`.
"""
from tools.protocol_probes import mcp_git_server as git
from tools.protocol_probes import mcp_obsidian_server as obsidian

MODULES = (git, obsidian)


def _clean(schema):
    """Gemini's Schema proto rejects JSON-Schema-only keys like
    additionalProperties — strip them recursively."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items()
                if k != "additionalProperties"}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


def declarations():
    """Gemini functionDeclarations for every skill tool."""
    out = []
    for mod in MODULES:
        for name, description, schema in mod.TOOLS:
            out.append({"name": name, "description": description,
                        "parameters": _clean(schema)})
    return out


def execute(name, args):
    """Run one skill tool; returns its text result."""
    for mod in MODULES:
        for tool_name, _, _ in mod.TOOLS:
            if tool_name == name:
                return mod.call_tool(name, args or {})
    raise ValueError(f"unknown tool: {name}")
