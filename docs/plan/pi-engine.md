# Plan: Pi as the first engine

**Status:** approved direction, not started
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

**M0 — adapter seam (½ day)**
Extract `EngineAdapter`, move the current bridge to `engines/legacy_agy.py`,
add the contract test. *Done when:* the app behaves identically and
`grep -r "agy" app/ --exclude-dir=engines` is empty.

**M1 — Pi, chat-only (2–3 days)**
Spawning `pi --mode rpc`, prompt/stream/settle, model list, effort, abort,
usage in the footer. *Done when:* a Task-mode turn streams to completion
against a real Pi install, and the transcript footer shows model and tokens.

**M2 — approvals (3–4 days)**
The extension above plus client rendering, timeout, and workspace rules.
*Done when:* the four acceptance criteria in §4 pass as tests, including the
"never executed" assertion.

**M3 — tool surface parity (2 days)**
Tool events drive the work panel; get_state drives the status pill; screenshots
and image generation keep working if the engine exposes them (else hidden
behind a capability flag). *Done when:* the work panel, changes panel and
status all behave as they do today.

**M4 — durability (4–6 days)**
Persistent Pi sessions: restore the transcript on start, resume after a kill,
steering while busy, compaction surfaced as a work item. *Done when:* kill -9
mid-turn, relaunch, and the conversation continues from the committed state —
demonstrated by a test that does exactly that.

**M5 — schedules become durable tasks (3–4 days)**
Evaluate Pi Durable's background tasks for scheduled prompts (including the
"app closed" question: a small daemon, or documented as app-open-only).
*Done when:* a schedule's run is visible as a task with its own transcript.

**M6 — Gemini engine, legacy deleted (4–5 days)**
`engines/gemini_sdk.py` on `google-genai`: streaming, function calling,
approvals through the same adapter contract, and Live API for voice as a
stretch. Delete the legacy adapter and the vendor OAuth module.
*Done when:* the contract test passes against Pi **and** Gemini, and no vendor
credential path remains in the repo.

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
