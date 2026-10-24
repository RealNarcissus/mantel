# Architecture

The client is a GTK4 application with one job: drive an engine that already
knows how to be an agent. Everything else — approvals, history, tools,
schedules — is the client exposing a surface the engine already has.

## The two processes

```
 Python / GTK4                                   Go engine (`agy`)
 ─────────────                                   ─────────────────
 app/main.py       Adw.Application
 app/window.py     rail · top bar · stack · work panel · approvals
 app/engine.py     ──── spawn ─────────────────►  --print <prompt>
                        ├── stdin/args           --output-format stream-json
                        │                        --model, --mode, flags
                        └── NDJSON stdout ◄────  init | step_update | result
 app/session.py    modes, approval state, tool records, work items
```

One engine process per turn. The client asks for one turn, renders the stream
as it arrives, and when the turn ends it records usage, the conversation id
and any refusals.

`app/engine.py` is the only module that knows about processes. It parses
defensively — unknown event types are ignored rather than fatal — because the
stream format belongs to someone else and may drift.

## Data flow of one turn

1. **Composer** collects text, mode (chat/task/research), model, effort and
   approval mode; `app/session.py` turns those into engine flags.
2. **Window** appends the user message, opens an assistant bubble and starts
   the turn. If the engine could not resume this conversation last time, the
   recent turns are replayed inline first (`_history_prefix`).
3. **Engine** streams `step_update` events. Deltas go to the bubble; tool
   calls go to `session.record_tool`, which feeds the work panel.
4. **Result** closes the bubble with duration and token usage, and records
   `denied_actions`.
5. **Approvals**: each refusal becomes a card. Granting calls
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
| `engine.py` | Spawns the engine, parses NDJSON, emits turn signals |
| `session.py` | Modes, approval ladder state, tool records, work items |
| `permissions.py` | Reads/writes the engine's permission config and trusted folders |
| `approval.py` | Approval cards and the anchored stack |
| `changes.py` | `git status` / `git diff` reader |
| `schedules.py`, `scheduler.py` | Cron parser + store, and the in-app runner |
| `account.py` | OAuth sign-in, credential file, identity |
| `mcp.py`, `skills.py` | Connectors and skills, via the engine's stores |
| `remote.py` | The engine's remote-control daemon |
| `screenshot.py` | XDG portal capture with fallbacks |
| `store.py` | Conversations on disk |
| `theme.py` | Palette, generated stylesheet, icon loading |
| `fonts_env.py` | Points fontconfig at bundled fonts *before* Pango initialises |
| `home.py`, `cards.py`, `charts.py`, `markdown.py`, `hero_art.py` | Dashboard and content rendering |

## Decisions worth knowing

**The engine is the brain; the client is the body.** Anything the UI appears
to do — permissions, schedules applied to real prompts, skill installation —
terminates in the engine's own files and commands, so `agy mcp list` and the
Connectors page can never disagree.

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

**Demo mode is a first-class path.** `--demo` builds the window against a
throwaway store, a neutral identity and neutral paths. It exists so reviewers
(and the screenshot script) can see the application without an account or an
engine.
