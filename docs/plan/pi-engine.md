# Plan: Pi as the first engine

**Status:** M0–M4 complete; M5/M6 remaining
**Goal:** replace the legacy vendor engine with **Pi** (`pi --mode rpc`) as the
default engine, without changing the shell, and then adopt **Pi Durable** for
conversations and tasks.

Everything below is written against Pi 1.0 (Oct 2026). Pi Durable is explicitly
experimental, so its API is pinned and isolated behind one adapter.

---

## 1. Why Pi first

- **It removes the vendor dependency.** Pi is MIT, runs on your own provider
  auth, and has no account surface to get banned from.
- **Model access follows *your* credentials, not a client surface.** That is
  the whole reason this project exists: `pi-ai` is a unified multi-provider
  layer, so the newest model is available if your provider grants it — not if
  some desktop client's feature flag allows it.
- **It fills the gap that broke the old approval model.** Pi's non-interactive
  stream is bidirectional: extensions can ask the client a question mid-turn
  (`extension_ui_request`) and block until answered (`extension_ui_response`).
  Approvals become real gates instead of refusals that force a retry.
- **It has the durability this UI was designed for.** Pi Durable gives
  conversations and tool calls checkpoints, forking, steering and multi-client
  attach — the surfaces Mantel already draws (work panel, steering, schedules)
  map onto it directly.
- **The shape is already right.** `app/engine.py` spawns a subprocess and
  parses JSONL. Pi RPC is the same shape with a better protocol.

Non-goals for this plan: voice, image models, mobile/remote clients, Windows or
macOS builds.

## 2. Target architecture

```
app/
  engines/
    base.py        EngineAdapter protocol  (spawn, run_turn, stop, models, …)
    pi_rpc.py      pi --mode rpc          ← M1–M4
    gemini_sdk.py  google-genai           ← M6
    legacy_agy.py  the current bridge     ← deleted in M6
  engine.py        thin facade: picks an adapter, re-exports Turn/signals
```

Hard rules for the refactor:

1. **Nothing above `app/engines/` may import an engine-specific module**, name
   an engine-specific path, or read an engine-specific env var. The UI talks to
   `EngineAdapter` and nothing else.
2. `tests/test_engine_contract.py` runs the same assertions against every
   registered adapter (streaming deltas, tool events, usage, errors, abort).
   A new adapter is "done" when that suite passes.
3. The legacy adapter stays selectable via `MANTEL_ENGINE=legacy` until parity,
   then is deleted along with `app/account.py`'s vendor OAuth path.

## 3. Protocol mapping

| Mantel concept | Pi RPC |
|---|---|
| spawn a turn | `{"type":"prompt","message":…,"id":…}` → `data.disposition`; wait for `agent_settled` |
| streaming text | `message_update` → `assistantMessageEvent.text_delta` |
| tool started/finished | session events for tool calls (`bash_execution_update` carries output for bash) |
| work panel | the same tool events → `session.record_tool` |
| model list | `get_available_models`, `set_model`, `cycle_model` |
| reasoning effort | `set_thinking_level`, `get_available_thinking_levels` |
| stop button | `abort` |
| steering | `steer` / `follow_up` while busy |
| context reset | `compact` (manual, with instructions) |
| conversation resume | `switch_session`, `get_tree`, `get_entries`, `get_messages` |
| **approval card** | extension calls `ctx.ui.select` → `extension_ui_request` → our `ApprovalCard` → `extension_ui_response` |
| notification / status | `notify`, `setStatus` (fire-and-forget) |
| changes panel | unchanged — still `git` in the workspace |

Notes:
- **Framing must be strict JSONL.** Split on `\n` only; never use a line reader
  that also splits on `U+2028`/`U+2029` (Pi's docs call this out explicitly).
- **Subscribe before prompting.** A fast turn can settle before a lazy client
  installs its listeners.
- `bash` and `abort_bash` stay unused at first: tools must run inside Pi's own
  execution environment, not through a side channel the UI controls.

## 4. Approvals: the piece that has to be designed, not just wired

Pi ships **no built-in permission system** — by design, it runs with the user's
own privileges. So Mantel's approval ladder is now a security feature we own,
implemented as a Pi extension.

Design:

1. A small TypeScript extension (`engine/pi/approvals/`) registers a gate on
   tool calls. It computes a capability from the call — `read(path)`,
   `write(path)`, `exec(command)` — and asks the client.
2. It calls `ctx.ui.select` with the ladder as options:
   `Allow once`, `Allow for this session`, `Always allow in this folder`, `Deny`.
   The request carries the tool name, the path or command, and the workspace, so
   the client can render its existing card rather than a bare list.
3. The client answers with `extension_ui_response`. A cancelled/missing answer
   is a **deny**; a `timeout` is set so a dead client cannot wedge the agent.
4. The extension remembers decisions for the session and, for
   `Always allow in this folder`, writes a workspace-scoped rule the next tool
   call consults.

Acceptance criteria:
- A blocked `write_file`/`bash` **never executes** (assert on the filesystem,
  not on the transcript).
- Choosing "Always allow in this folder" auto-approves the same capability in
  that workspace, and does not leak to a sibling workspace.
- Killing the client mid-request denies rather than hangs.
- The extension is versioned and loaded from the repo, not installed globally.

## 5. Milestones

Each milestone ships green tests and no user-visible regression.

**M0 — adapter seam (done)**
`app/engines/base.py` holds the contract, `legacy_agy.py` holds the old bridge
unchanged, `app/engine.py` is a facade selecting by `MANTEL_ENGINE`, and
`tests/test_engine_adapter.py` is the contract suite. The three vendor-only
modules (account, remote, connectors) are marked as such.
*Known remaining references to the vendor outside `engines/` are exactly those
flagged vendor surfaces, not the bridge.*

**M1 — Pi, chat-only (done)**
`app/engines/pi_rpc.py` drives `pi --mode rpc`: prompt, streaming deltas,
thinking, tool lifecycle, usage normalised into the footer's shape, model list
via `get_available_models`, effort via `--thinking`, graceful abort, and a
refusal for engine dialogs so nothing can hang the UI before M2.
*Verified:* against a protocol-faithful fake (`tests/fixtures/fake_pi.py`) for
all nine contract checks, and against the real `pi` 1.4.0 for handshake and
session id; a real prompt currently stops at "No API key found for the selected
model", which is the expected blocker until a provider is connected.

**M2 — approvals (done)**
`pi-extensions/approvals.ts` gates `tool_call` and asks through `ctx.ui.select`;
the client renders the request as its own approval card and answers through
`extension_ui_response`. Grants are per-call, per-session and per-folder (the
last persisted under `~/.config/mantel/approvals.json`). Failure is closed: no
UI, no answer, a timeout, a read error or an unexpected value all deny. Escape
denies the visible card before it stops the turn.

*Acceptance, as tests:*
- the four-step ladder reaches the client, and "Allow once" lets the call run
- a deny means the tool never executes (asserted on the event stream, not the
  transcript)
- an unanswered dialog is declined by the adapter's own timer
- the shipped TypeScript gate loads in real `pi` (exit 0, `get_state` answered)
- the gate is fail-closed outside RPC mode (`ctx.hasUI` false → block)

**M3 — tool surface parity (done)**
- *Capability gating:* every rail surface declares the capability it needs and
  the window builds only what the engine backs — Connectors and Skills are gone
  for Pi, the account page is gone without an account, and Settings hides the
  vendor permission file and CLI approval-mode control (Pi says "approvals are
  enforced per call" instead). Vendor approval flags never reach an engine that
  cannot take them.
- *Steering:* Enter inside a running turn sends the text to the engine
  (`steer`) instead of stopping it, and the transcript shows it as a quiet
  `↳ steered:` note rather than a second user turn. Only offered when the
  engine advertises the capability; a settled turn refuses rather than
  silently dropping the message.
- *Parity:* tool events already drive the work panel and the changes panel is
  engine-independent; the status pill is derived from session state
  (needs-input / running / error / complete), so it reads the same on both
  engines. Compaction appears as a work item.

**M4 — durability (in progress)**
Persistent Pi sessions: restore the transcript on start, resume after a kill,
steering while busy, compaction surfaced as a work item. *Done so far:*
- **Session identity is durable.** The client's conversation id is what Pi
  resumes with (`--session-id`), and a test proves the same id is used by a
  fresh process after the previous one died.
- **The engine's store is a source of truth.** `Engine.history(id)` reads a
  session back through `get_messages`; the client uses it to reconcile a
  transcript that is shorter than the engine's (the engine committed, the
  client died before saving).
- **A crash mid-turn is recoverable.** Test: a turn is interrupted by process
  death, and the next turn in a new process still sees the committed history
  (`resumed:4`) — steering, the approval gate and usage all keep working
  afterwards.
- **Reconciliation is content-aware**, not index-based: the stored transcript
  is matched as a contiguous run inside the engine's history, with a
  content-merge fallback when the two diverge.

*Done since:*
- **An app-level `kill -9` harness.** The app is started mid-turn against the
  fake engine, killed with SIGKILL once the store records a pending turn, then
  restarted; the conversation is marked interrupted rather than left running or
  lost. This is the acceptance bar the plan set, as a test.
- **A resume affordance.** A turn in flight is recorded (`pending_prompt`); on
  load it becomes `interrupted`, and the transcript shows a card with
  *Continue* (asks the agent to pick the work back up) and *Dismiss*. The card
  is a real UI element, verified by rendering it.

*Found while writing that test:* a patch aimed at `load_demo` had also applied
to `submit()` (string replacement hit both), so every message wrote sample
tasks, installed the example plugin and attempted demo calendar/notes setup,
while the memory-capture block was shadowed. Removed, and the test now asserts
`submit()` contains no demo seeding.

**M5 — schedules become durable tasks (3–4 days)**
Evaluate Pi Durable's background tasks for scheduled prompts (including the
"app closed" question: a small daemon, or documented as app-open-only).
*Done when:* a schedule's run is visible as a task with its own transcript.

**M6 — Gemini engine, legacy deleted (in progress)**
- *Done:* `app/engines/gemini_api.py` speaks the public REST streaming API with
  no third-party dependency: model listing, SSE deltas, usage normalisation,
  HTTP error mapping and cancellation. It advertises `chat` but not `tools`, so
  the shell keeps the conversation and hides agent-only surfaces — the
  capability system doing exactly what it was built for. Verified against a
  local fake API, so no key or network is needed in CI.
- *Done since:* **function calling and approvals.** The adapter runs a bounded
  tool loop (8 model turns) over `read_file`, `write_file` and `run_command`.
  Reads are free; writes and commands ask through the same `dialog` protocol
  the Pi gate uses, so the client renders its existing approval card and a
  deny means the tool never executes (asserted on the filesystem, not the
  transcript). Paths outside the workspace are refused; command output and
  file reads are capped.
- *Remaining:* the contract suite (`tests/test_engine_adapter.py`) does not yet
  run against Gemini, and the legacy adapter plus its OAuth module are still
  in the tree. Those two are the milestone's acceptance bar.

Total: roughly 3–4 focused weeks to M6, with a publishable v0.2 at M2.

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pi Durable is experimental (API may change) | Pin the version; keep it behind `engines/pi_rpc.py`; the M1–M3 path uses the stable coding-agent RPC, not the durable package |
| Node 22.19+ is a new dependency | Treat `pi` like `agy` today: require it on `PATH`, document install; never bundle |
| Pi has no permission system | That is the feature, not the gap — but it means **we** are the security boundary. Deny-by-default, timeouts, workspace-scoped rules, and tests that assert refusal |
| Extension UI options are strings | Encode the ladder in the options for v0.2; richer cards come from a `notify` preamble or a later Pi UI extension |
| Provider auth differs per user | Document `pi` login + API-key paths; model picker reflects `get_available_models` rather than a hardcoded list |
| Long transcript restore is slow | Restore lazily: header + last N entries on open, full history on scroll back |

## 7. Definition of done for the public v0.2

- Pi is the default engine; the vendor engine is gone from the repo.
- The approval gate is proven to block execution, not just report it.
- A killed process resumes its conversation.
- The README's engine table has no "in progress" row for Pi.
- The screenshots are regenerated from demo mode and match the shipped UI.
