# Security

Mantel runs an AI agent on your machine. That is the useful part and the risky
part, so the boundaries are documented rather than implied.

## Trust model

- **The engine runs with your privileges.** Pi (`pi --mode rpc`) is a coding
  agent: it reads and writes files and runs commands. Mantel does not sandbox
  it; it gates it.
- **Approvals are the gate.** Every mutating tool call asks before it runs, and
  a deny means the call never executes — asserted in tests on the filesystem,
  not on the transcript. Read-only calls pass without a prompt.
- **The client is the boundary for plugin code.** Extensions run out of process
  over JSON-RPC: the manifest is data (never executed on install), the
  capability sheet is shown before install, every call has a deadline, every
  action is audited, and `MANTEL_SAFE_MODE=1` runs no plugin code at all.
- **Local first.** Memory, tasks, calendar sources, knowledge indexes and plugin
  records live under `XDG_DATA_HOME`. The only network traffic is to the
  selected engine (or a calendar/notes source you explicitly configure).

## Known limits (deliberate, documented)

- Plugin `permissions` are **declarations**, shown at install time and used to
  decide what context is passed — they are not an OS sandbox. Install plugins
  you trust, and read them; a plugin is a shell script with a menu.
- Calendar reading is read-only (`.ics`); Mantel does not write to your calendar.
- Conversations and engine credentials belong to the engine's own store; Mantel
  never bundles or proxies a vendor login.

## Reporting a vulnerability

Open a private security advisory on the repository
(*Security → Report a vulnerability*) rather than a public issue. Please include
the affected file, a reproduction, and whether the issue lets a **plugin**
exceed its declared capabilities, a **prompt** cause an unapproved mutating
call, or **data** leave the machine.

There is no bug bounty. This is a spare-time project; the standard is honesty,
not speed.
