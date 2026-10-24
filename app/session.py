"""Agent sessions: chat vs task mode, approvals, and the work panel.

The engine is the same binary in both modes; what changes is how much
authority it is given and what the client does with the result.

Chat mode
    A plain exchange.  The engine still gets the workspace, and still reports
    the tools it used.

Task mode
    The agentic surface (the desktop app calls this Task mode).  The engine
    runs with its tools enabled and the client tracks a *work panel*: the
    steps it completed, the step it is on, what it plans next, and the files
    it read or wrote.

Approvals
    The engine refuses anything it is not explicitly granted and reports the
    refusal as ``denied_actions``.  The client turns that into an approval
    card, and the user can grant the action (once, or for the folder) and
    retry.  See :mod:`app.permissions`.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

MUTATING = frozenset({
    "write_file", "edit_file", "replace", "run_command", "bash", "delete_file",
    "create_file", "move_file", "run_shell_command",
})

from app import engine as engine_mod
from app import knowledge as knowledge_mod
from app import memory as memory_mod

# --- approval modes --------------------------------------------------------

@dataclass(frozen=True)
class ApprovalMode:
    key: str
    label: str
    description: str
    flags: tuple[str, ...] = ()


#: The modes the client offers, in increasing order of authority.
#:
#: The wording follows the desktop agents: Codex offers *Ask for approval* /
#: *Approve for me* / *Full access*, Claude offers *Manual* / *Accept edits* /
#: *Plan* / *Auto* / *Bypass*.  The engine here accepts three positions, so
#: the names are taken from the first pair and the escalation is explicit.
APPROVAL_MODES = (
    ApprovalMode(
        "ask", "Ask for approval",
        "Nothing runs until you approve it. The agent holds what it wants to do.",
    ),
    ApprovalMode(
        "edits", "Accept edits",
        "File edits are applied straight away; shell commands still wait for you.",
        ("--mode", "accept-edits"),
    ),
    ApprovalMode(
        "full", "Full access",
        "The agent may read, write and run commands without asking.",
        ("--dangerously-skip-permissions",),
    ),
)

MODE_BY_KEY = {m.key: m for m in APPROVAL_MODES}

#: The scope of a single approval, narrowest first — the same ladder Codex
#: and Claude use, so the user always chooses the smallest grant that unblocks
#: the task.
APPROVAL_SCOPES = (
    ("once", "Allow once"),
    ("session", "Allow for this session"),
    ("project", "Always allow in this folder"),
)


# --- status vocabulary -----------------------------------------------------

#: Codex's status words, reused so the meaning is familiar.
STATUS_IDLE = "idle"
STATUS_THINKING = "thinking"
STATUS_COMPLETE = "complete"
STATUS_NEEDS_INPUT = "needs_input"
STATUS_ERROR = "error"

STATUS_LABELS = {
    STATUS_IDLE: "Ready",
    STATUS_THINKING: "Thinking",
    STATUS_COMPLETE: "Complete",
    STATUS_NEEDS_INPUT: "Needs input",
    STATUS_ERROR: "Error",
}


# --- task vs chat ----------------------------------------------------------

MODE_CHAT = "chat"
MODE_TASK = "task"
MODE_RESEARCH = "research"

#: Instruction prefixed to a research turn.  The engine has `search_web` and
#: `read_url_content` in its tool palette, so research is a way of *using* it
#: rather than a separate pipeline.
RESEARCH_BRIEF = (
    "Research task. Work in this order:\n"
    "1. Break the question into the sub-questions that actually need answers.\n"
    "2. Use search_web and read_url_content to gather sources. Prefer primary "
    "sources and note the URL for every claim.\n"
    "3. If a source contradicts another, say so rather than picking one.\n"
    "4. Finish with a report under these headings: Summary (three sentences), "
    "Findings (grouped, each with its source), Open questions, Sources.\n"
    "Do not invent sources or statistics. If you cannot verify something, say "
    "so explicitly.\n\nThe question:\n"
)


@dataclass
class ToolActivity:
    """One tool call made during a turn."""

    name: str
    parameters: dict = field(default_factory=dict)
    output: str = ""
    error: str = ""
    state: str = "ACTIVE"
    started: float = field(default_factory=time.time)
    duration: float = 0.0

    @property
    def mutating(self) -> bool:
        return self.name in MUTATING

    @property
    def path(self) -> str:
        """The path this call touches, if any."""
        for key in ("Path", "path", "file_path", "FilePath", "NotebookPath"):
            value = self.parameters.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @property
    def command(self) -> str:
        for key in ("CommandLine", "command", "Command"):
            value = self.parameters.get(key)
            if isinstance(value, str) and value:
                return value
        return ""

    @property
    def summary(self) -> str:
        if self.path:
            return os.path.basename(self.path.rstrip("/")) or self.path
        if self.command:
            return self.command[:60]
        if self.output:
            return self.output[:60]
        return ""


@dataclass
class Approval:
    """An action the engine wanted to take but was not allowed to."""

    action: str
    display_name: str
    tool: ToolActivity | None = None

    @property
    def path(self) -> str:
        return self.tool.path if self.tool else ""

    @property
    def command(self) -> str:
        return self.tool.command if self.tool else ""

    @property
    def title(self) -> str:
        if self.path:
            return f"{self.display_name} {os.path.basename(self.path)}"
        if self.command:
            return f"Run {self.command[:48]}"
        return self.display_name

    @property
    def verb(self) -> str:
        """A sentence describing what the agent wants to do."""
        mapping = {
            "write_file": "write a file",
            "read_file": "read a file",
            "replace_file_content": "edit a file",
            "multi_replace_file_content": "edit a file",
            "sed_file": "edit a file",
            "list_dir": "list a folder",
            "run_command": "run a command",
        }
        return mapping.get(self.action, self.action.replace("_", " "))


@dataclass
class WorkItem:
    """A step in the work panel."""

    kind: str          # "done" | "current" | "planned" | "file"
    label: str
    detail: str = ""


class Session:
    """One agent session bound to a conversation."""

    def __init__(self, engine: engine_mod.Engine, conversation_id: str = "",
                 mode: str = MODE_CHAT, approval: str = "ask",
                 workspace: str = ""):
        self.engine = engine
        self.conversation_id = conversation_id
        self.mode = mode
        self.approval = approval
        self.workspace = workspace

        self.tools: list[ToolActivity] = []
        self.approvals: list[Approval] = []
        self.plan: list[str] = []
        self.started = time.time()

        self.running = False
        self.finished = False
        self.error = ""
        self._session_grants: set[str] = set()

    # -- configuration ------------------------------------------------------
    def flags(self) -> list[str]:
        """Extra engine flags for the current approval mode.

        Approval modes are a command-line concept of the legacy engine; an
        engine that asks before acting (Pi) needs no flags and would reject
        these. The capability decides, not the engine's name.
        """
        if not self.engine.supports(engine_mod.CLI_FLAGS):
            return []
        mode = MODE_BY_KEY.get(self.approval, APPROVAL_MODES[0])
        return list(mode.flags)

    def engine_mode(self) -> str:
        """The engine's own `--mode` value (chat vs task)."""
        return "auto" if self.mode != MODE_CHAT else ""

    #: Facts about the user are prepended to every turn, budgeted.
    use_memory = True

    #: Passages from the user's own notes, retrieved by the prompt.
    use_knowledge = True

    def brief(self, prompt: str) -> str:
        """The prompt the agent actually receives.

        Memory comes first: a short block of what the agent already knows, so
        the user does not have to re-explain themselves each session. It is
        budgeted (see `memory.PROFILE_BUDGET`) and scoped, never a data dump.
        """
        prefix = ""
        if self.use_memory:
            prefix = memory_mod.profile_block(scope=self.memory_scope())
        if self.use_knowledge and prompt.strip():
            try:
                prefix += knowledge_mod.context_block(prompt)
            except Exception:  # noqa: BLE001 - notes must never block a turn
                pass
        if self.mode == MODE_RESEARCH:
            return prefix + RESEARCH_BRIEF + prompt
        return prefix + prompt

    def memory_scope(self) -> str:
        """Which memory scope this turn is allowed to see."""
        return "all"

    # -- activity -----------------------------------------------------------
    def record_tool(self, name: str, parameters: dict, state: str,
                    output: str = "", error: str = "", duration: float = 0.0
                    ) -> ToolActivity:
        """Update (or create) the record for a tool call."""
        existing = None
        # the engine emits ACTIVE then DONE/ERROR for the same step, so the
        # record is updated rather than appended
        for tool in reversed(self.tools):
            if tool.name == name and tool.state == "ACTIVE":
                existing = tool
                break
        if existing is None:
            existing = ToolActivity(name=name, parameters=dict(parameters or {}))
            self.tools.append(existing)
        if parameters:
            existing.parameters.update(parameters)
        existing.state = state
        if output:
            existing.output = output
        if error:
            existing.error = error
        if duration:
            existing.duration = duration
        return existing

    def record_approvals(self, denied: list[dict]) -> list[Approval]:
        """Turn the engine's `denied_actions` into approval cards."""
        out: list[Approval] = []
        for entry in denied or []:
            action = str(entry.get("action", ""))
            display = str(entry.get("display_name", action))
            if not action:
                continue
            tool = None
            for candidate in reversed(self.tools):
                if candidate.name == action and candidate.state != "DONE":
                    tool = candidate
                    break
            if tool is None:
                for candidate in reversed(self.tools):
                    if candidate.name == action:
                        tool = candidate
                        break
            approval = Approval(action=action, display_name=display, tool=tool)
            out.append(approval)
        self.approvals = out
        return out

    # -- work panel ---------------------------------------------------------
    def work_items(self) -> list[WorkItem]:
        """Completed / current / planned steps and the files touched."""
        items: list[WorkItem] = []
        for tool in self.tools:
            if tool.state == "ACTIVE":
                items.append(WorkItem("current", tool.name, tool.summary))
            elif tool.state == "DONE":
                items.append(WorkItem("done", tool.name, tool.summary))
            elif tool.state == "ERROR":
                items.append(WorkItem("done", tool.name,
                                      tool.error or tool.summary))
        for step in self.plan:
            items.append(WorkItem("planned", step))
        seen: set[str] = set()
        for tool in self.tools:
            path = tool.path
            if path and path not in seen:
                seen.add(path)
                items.append(WorkItem("file", os.path.basename(path), path))
        return items

    def files_touched(self) -> list[str]:
        out: list[str] = []
        for tool in self.tools:
            path = tool.path
            if path and path not in out:
                out.append(path)
        return out

    # -- approval granting --------------------------------------------------
    def grant(self, approval: Approval, scope: str = "once") -> list[str]:
        """Grants are enforced by the engine's own gate now.

        The client can still remember a decision for this session; there is no
        vendor permission file to write, so persistent grants no longer exist.
        """
        if scope in ("session", "project"):
            grant = f"{approval.action}:{approval.path or '*'}"
            self._session_grants.add(grant)
            return [grant]
        return []

    def grantable(self, approval: Approval) -> bool:
        """Persistent grants are not offered: the engine owns the decision."""
        return False

    # -- status -------------------------------------------------------------
    def status(self) -> str:
        """The current state, in the vocabulary the desktop agents use."""
        if self.approvals:
            return STATUS_NEEDS_INPUT
        if self.running:
            return STATUS_THINKING
        if self.error:
            return STATUS_ERROR
        if self.finished:
            return STATUS_COMPLETE
        return STATUS_IDLE
