# Plugins

Mantel is a shell, and a shell should be shaped by the person using it. Plugins
are how: a folder with a manifest and a program, which adds commands to the
palette and — in later versions — panels, pages and triggers.

The design is deliberately conservative, because a plugin system is also a
remote-code-execution system with a friendly name.

## Three tiers

| Tier | What it is | Runs where | Status |
|---|---|---|---|
| **Skill** | markdown instructions the agent may follow, optionally with scripts | the engine's sandbox | engine-provided today |
| **Connector** | an MCP server exposing tools | its own process | engine-provided today |
| **Extension** | a program contributing commands (and eventually UI) | its own process, JSON-RPC to Mantel | **implemented** |

This page documents extensions, the tier this client hosts itself.

## The contract

An extension is a directory:

```
my-plugin/
  mantel.json     the manifest — data, never executed
  main.py         any program; Python 3 is just the reference
```

### `mantel.json`

```json
{
  "id": "com.example.hello",
  "name": "Hello",
  "version": "1.0.0",
  "apiVersion": 1,
  "description": "What it does, in one sentence.",
  "author": "you",
  "entry": ["python3", "main.py"],
  "permissions": {
    "fs": "none",
    "net": [],
    "memory": "none",
    "exec": false,
    "ui": []
  },
  "commands": [
    { "id": "hello", "title": "Say hello", "description": "Optional." }
  ]
}
```

Rules the host enforces:

- `id` is reverse-DNS (`com.example.hello`) and must be unique.
- `version` is free-form; `apiVersion` must equal `1`.
- `entry` is an **argv list** — there is no shell, so no quoting games.
- `permissions` may only use the keys below. Unknown keys are rejected rather
  than ignored.
- Every command needs an `id` and a `title`.

### Permissions

| Key | Values | Meaning |
|---|---|---|
| `fs` | `"none"` · `"workspace"` | file access |
| `net` | list of hosts | which hosts it may reach |
| `memory` | `"none"` · `"read"` · `"write"` | access to remembered facts |
| `exec` | `true` · `false` | may run commands |
| `ui` | list of slots | declarative contributions (not implemented yet) |

Permissions are *declarations*, not enforcement sandboxes: the host shows them
at install time and passes only the data a plugin asked for, but a determined
plugin runs with your user's privileges. Install plugins you trust, and read the
code — it is a folder.

### The protocol

One JSON request in on stdin, one JSON response out on stdout:

```json
{"id": "a1b2", "method": "command",
 "params": {"command": "hello", "date": "Friday 24 October"}}
```

```json
{"id": "a1b2", "ok": true, "result": {"message": "Hello."}}
```

Failure is `{"ok": false, "error": "…"}`. The host kills the process after
**8 seconds** (configurable per call), so a hung plugin is a failed command, not
a hung client. A plugin process is spawned per call: isolation is worth the
start-up cost at this scale.

### Context the host passes

For a command call the host adds, unless the plugin asked for nothing:

- `date` — the current day, as a string
- `tasks` — up to 20 open task titles
- `overdue` — how many are overdue

If `memory` is `read` or `write`, `memory` is a list of up to 10 remembered
facts. A plugin with `"fs": "none"` and `"net": []` receives nothing but this
context.

## Reference plugin

[`plugins/day-summary`](../plugins/day-summary) is a complete, dependency-free
example: it reads the context and returns one sentence about the day. About 60
lines including comments.

Install it from the Plugins page (**Install from folder…**) or copy it into the
plugins directory. Its command appears in `Ctrl+K` as *Summarise my day*.

## Installing and running

- **Install**: Plugins page → *Install from folder…* → pick the directory. The
  manifest is validated and a **capability sheet** is shown *before* anything is
  copied. Nothing executes on install.
- **Enable / disable**: the switch on the plugin's card. A disabled plugin does
  not appear in the palette and cannot be called.
- **Run**: from its card, or from the palette by name.
- **Uninstall**: deletes the plugin's folder. Your tasks, memories and
  conversations are untouched.

## Security model

| Measure | What it buys |
|---|---|
| Manifest is data | installing cannot execute code |
| Out-of-process, no shell | a crashing or hostile plugin cannot take the app down |
| Per-call timeout | a hang is an error, not a freeze |
| Capability sheet at install | you see the blast radius before it exists |
| Declared permissions → context | a plugin only receives data it asked for |
| Audit log (`.mantel/plugins/audit.jsonl`) | every install, run and failure is recorded |
| Safe mode (`MANTEL_SAFE_MODE=1`) | no plugin code runs at all |
| Path redaction in the UI | home directories do not leak into screenshots |

What is **not** here yet: a signed registry, automatic updates, resource limits
beyond a timeout, or enforcement of `net`/`fs` claims. Until then, treat a
plugin exactly like a shell script you found on the internet — because it is
one.

## Deliberate limits

- No UI contributions yet (`ui` is reserved): the declarative schema ships when
  there is a real use case for it, not before.
- No marketplace or index: install from a folder. Distribution design is in
  [VISION.md](VISION.md) §8.
- No upgrades: uninstall and reinstall.

## Writing one

1. Copy `plugins/day-summary` to a new folder.
2. Change `id`, `name` and `commands`.
3. Read one line from stdin, write one line to stdout.
4. Install it from the page and watch the audit log.

If you need something the protocol does not expose, that is a conversation to
have on the issue tracker rather than a reason to reach around it.
