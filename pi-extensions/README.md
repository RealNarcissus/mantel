# Pi extensions

Extensions run *inside* the Pi process with the user's own permissions, so this
directory is deliberately small: it holds the one extension the client ships,
and it is worth reading before you load anything else from elsewhere.

## `approvals.ts` — the approval gate

Pi has no built-in permission system by design. This extension supplies one, in
the shape the client already draws:

| Choice | Effect |
|---|---|
| Allow once | this call only |
| Allow for this session | this tool + target, until Pi exits |
| Always allow in this folder | this tool, in this working directory, persisted |
| Deny | the call is blocked — it never runs |

Read-only tools (`read`, `grep`, `find`, `ls`, `tool_search`) pass without
asking. Everything else asks.

It hooks `tool_call`, which runs **before** execution, and asks through
`ctx.ui.select`. Over the RPC protocol that becomes an `extension_ui_request`;
the client renders it as an approval card and answers with
`extension_ui_response`. That is why a deny here means the tool *did not run*,
rather than "ran, failed, was reported".

### Failure behaviour is closed

No attached UI, no answer, a timeout (5 minutes), an unreadable store or an
unexpected value all deny. A safety gate must never fall through to allow.

### Grants

Session grants live in memory for the life of the Pi process. Folder grants are
persisted to:

```
${XDG_CONFIG_HOME:-~/.config}/mantel/approvals.json
```

One entry per `{ folder, tool }`. Delete the file (or a key) to revoke.

### Loading

The client loads it automatically when running from a checkout:

```bash
pi --mode rpc --extension pi-extensions/approvals.ts
```

Override the path with `MANTEL_APPROVALS_EXT=/path/to/gate.ts`, or disable it
with `MANTEL_NO_APPROVALS_EXT=1` (Pi then runs with its own defaults — with no
permission prompts at all, so prefer not to).

### Reading it

About 150 lines. It is worth reading before trusting it with your shell: every
branch either returns `undefined` (run) or `{ block: true, reason }`.
