# Architecture

The client is a GTK4 application with one job: drive an agent engine and put a
native Linux surface on it. Everything above the engine adapter — approvals,
history, tools, schedules — is engine-independent by design.

## The two processes

```
 Python / GTK4                          engine adapter (one module per engine)
 ─────────────                          ─────────────────────────────────────
 app/main.py       Adw.Application
 app/window.py     rail · top bar · stack · work panel · approvals
 app/engine.py     ──── facade ───────► engines/pi_rpc.py      (default target)
                        ├── spawn         pi --mode rpc   JSONL in / events out
                        │                 extension_ui_request / response
                        └── events   ─── engines/gemini_api.py   (REST, chat-only)
                                      engines/gemini_api.py     (public API)
 app/session.py    modes, approval state, tool records, work items
```

One engine process per conversation. The client asks for a turn, renders the
stream as it arrives, and records usage when the turn settles. Approvals are a
round trip inside that stream, not a post-hoc report.

`app/engines/` is the only place that knows about processes and protocols.
Adapters parse defensively — unknown event types are ignored rather than fatal,
because the stream format belongs to someone else and may drift.

Nothing above `app/engines/` imports an engine-specific module, names an
engine-specific path, or reads an engine-specific environment variable. `tests/test_engine_adapter.py` runs the
same expectations against every adapter — it is the definition of "an engine is
supported" — and `tests/fixtures/fake_pi.py` keeps that suite runnable with no
engine, credentials or network. See [plan/pi-engine.md](plan/pi-engine.md).

## Data flow of one turn

1. **Composer** collects text, mode (chat/task/research), model, effort and
   approval mode; `app/session.py` turns those into engine flags.
2. **Window** appends the user message, opens an assistant bubble and starts
   the turn. If the engine could not resume this conversation last time, the
   recent turns are replayed inline first (`_history_prefix`).
3. **Engine** streams deltas and tool events. Deltas go to the bubble; tool
   calls go to `session.record_tool`, which feeds the work panel.
4. **Settle** closes the bubble with duration and token usage.
5. **Approvals**: with the Pi adapter the engine asks *before* running a tool
   (`extension_ui_request`), the card answers it (`extension_ui_response`), and
   a deny means the tool never executes. When an engine can only report a
   reported afterwards, so granting calls
   `permissions.allow(...)`, which writes a real rule into the engine's
   `config.json`, then the request is replayed.
6. **Changes**: after every turn `changes.collect()` asks git what changed and
   the panel lists it.

## Modules

| Module | Responsibility |
|---|---|
| `main.py` | CLI flags, application lifecycle, offscreen smoke renders |
| `window.py` | Shell: rail, top bar, page stack, work panel, approvals, notifications |
| `sidebar.py`, `topbar.py` | The 304 px rail and the 100 px bar |
| `composer.py` | Prompt entry and the mode/model/effort/approval controls |
| `chat_view.py` | Transcript, assistant bubbles, `WorkPanel`, `ChangesPanel` |
| `engine.py` | Facade: selects an adapter, re-exports turn signals |
| `engines/` | One adapter per engine (Pi RPC, Gemini API); the only code that spawns processes |
| `session.py` | Modes, approval ladder state, tool records, work items |
| `permissions.py` | Reads/writes the engine's permission config and trusted folders |
| `approval.py` | Approval cards and the anchored stack |
| `changes.py` | `git status` / `git diff` reader |
| `schedules.py`, `scheduler.py` | Cron parser + store, and the in-app runner |
| `skills.py` | Skills the engine makes available |
| `screenshot.py` | XDG portal capture with fallbacks |
| `store.py` | Conversations on disk |
| `theme.py` | Palette, generated stylesheet, icon loading |
| `fonts_env.py` | Points fontconfig at bundled fonts *before* Pango initialises |
| `home.py`, `cards.py`, `charts.py`, `markdown.py`, `hero_art.py` | Dashboard and content rendering |

## Decisions worth knowing

**The engine is the brain; the client is the body.** Mantel does not own the
model, the tool loop or the provider credentials — and that is deliberate:
model access should follow *your* provider entitlement rather than which
desktop client you happen to run. Anything the UI appears to do — permissions,
schedules applied to real prompts, skill installation — terminates in the
engine's own stores, so the CLI and the UI can never disagree.

**Software rendering for verification.** Development happened on a machine
with no capturable compositor and no GPU. The UI is therefore verified by
rendering the real widget tree through a cairo `Gsk.Renderer` into a PNG
(`tests/harness.py`). That is not a mock: it is the same tree the compositor
would receive.

**Icons are baked, not drawn as text.** The glyph set is a private-use icon
font. GTK's text pipeline renders notdef boxes for those codepoints
non-deterministically across processes, so `tools/render_icons.py` bakes one
PNG per glyph and the client loads textures. When the glyphs are absent the
client falls back to stock symbolic icons — which is how a fresh clone looks.

**Optional assets, honest fallbacks.** Fonts and glyphs are third-party and
not redistributable, so `app/theme.py` and `app/fonts_env.py` treat them as
optional and degrade to system fonts and Adwaita icons. Nothing crashes, and
the layout is identical either way.

**The store is an index, not the only copy.** When the engine keeps sessions
(Pi does), the client reconciles a thread against the engine's own history on
open: a crash between the engine committing and the client saving cannot lose
a turn. The merge is content-aware — the stored transcript is matched as a
contiguous run inside the engine's history — and falls back to merging by
content when the two diverge.

**Demo mode is a first-class path.** `--demo` builds the window against a
throwaway store, a neutral identity and neutral paths. It exists so reviewers
(and the screenshot script) can see the application without an account or an
engine.
