# Contributing

Mantel is a native GTK4 desktop for coding agents, with a productive day built
around it. The interesting parts are the **engine seam** and the **product
surfaces**; the design rationale is in [`docs/VISION.md`](docs/VISION.md) and the
engine plan in [`docs/plan/pi-engine.md`](docs/plan/pi-engine.md).

## Run it

```bash
git clone <repo> && cd mantel
python3 -m app.main --demo          # no engine needed
python3 -m app.main                 # needs `pi` on PATH, or GEMINI_API_KEY
```

Requirements: Linux with GTK4 and libadwaita, Python 3.10+, PyGObject, Pycairo,
and an engine (`pi`, or the Gemini API with `GEMINI_API_KEY`).

## The two gates

```bash
make lint           # ruff, pinned to the CI version
make test-offline   # 17 suites, no engine and no network
```

Both must pass. The suite is offline by design: engine behaviour goes through
protocol-faithful fakes (`tests/fixtures/`), so a contribution is verifiable
without credentials.

## Ground rules

- **Nothing above `app/engines/` may name an engine**, its files, its protocol
  or its environment variables. The UI talks to `EngineAdapter`; see
  `app/engines/__init__.py`.
- **Capabilities gate surfaces.** If an engine cannot back a page, the page does
  not exist for it — no dead links, no fake settings.
- **Behaviour is tested on disk, not in the transcript.** A denied write must
  leave no file; a completed task must count once.
- **Demo mode must not touch real data.** `--demo` redirects `XDG_DATA_HOME`.

## Plugins

The plugin contract, security model and a working example live in
[`docs/PLUGINS.md`](docs/PLUGINS.md) and [`plugins/day-summary`](plugins/day-summary).
A plugin is a folder with a `mantel.json` and a program; the host never executes
it on install.

## Commit style

Staged, explanatory commits: what changed, why, and what was verified. Prefer
several small commits over one large one.
