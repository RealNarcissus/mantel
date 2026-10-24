# Publishing checklist

Mantel is ready to publish as a public portfolio repository. This is the audited
short list: what is true, what to check, and exactly what to run.

## Audit result (24 Oct 2026)

| Check | Result |
|---|---|
| **No credentials** | Clean. No token, key, OAuth secret or `.env` is tracked; the vendor credential path was deleted in M6. |
| **No proprietary assets** | Clean. Only `assets/README.md` and `icon_glyphs.json` are tracked; fonts, glyph atlases and the app icon are gitignored. |
| **No personal data** | Clean. Screenshots use the neutral demo identity (`alex.rivera@example.com`, `/home/alex/projects`). Research probes no longer contain a developer's home path. |
| **No stale vendor code** | Clean. `legacy_agy`, vendor OAuth, remote daemon, connector store and permission file are gone, with their tests. |
| **Tests** | 17/17 offline suites from a fresh clone; renders under both engines. |
| **Lint** | `make lint` clean (ruff 0.17.2, pinned in CI). |
| **Links** | Every relative link in README and `docs/` resolves (the only unmatched ones are inside captured research pages, which link to their original hosts). |
| **History** | `main` only. The old `archive/pre-cleanup` branch holds pre-repositioning history and **must not be pushed**. |

Known caveat, documented rather than hidden: `docs/research/` contains captured
public documentation used for product research. It is not loaded by the app, it
is not shipped code, and deleting the folder changes nothing at runtime. See
[`docs/research/README.md`](research/README.md).

## The one decision left: the name

The working name is `mantel`. It appears in `README.md`, `docs/`, the window
title, `app/main.py` (`APP_ID`), the sidebar wordmark, `packaging/install.sh`
and the desktop entry. Renaming before publishing is a single commit; renaming
after is a redirection and a broken clone for anyone who starred it.

## Publish

```bash
# only main goes up
git branch -D archive/pre-cleanup

gh repo create mantel --public --source=. --remote=origin --push

gh repo edit --description \
  "A local-first desktop for AI agents on Linux — a productive day (tasks, memory, calendar) built around approvals you can see, work you can follow, and Pi or Gemini as engines." \
  --add-topic gtk4 --add-topic libadwaita --add-topic linux --add-topic python \
  --add-topic pygobject --add-topic ai-agents --add-topic agent-harness \
  --add-topic desktop-app --add-topic local-first
```

## Repository settings

- **About**: the description above, plus the README tagline.
- **Social preview**: `docs/screenshots/today.png` (1744×1168) crops well to
  1280×640.
- **Topics**: as above.
- **Discussions**: optional; issues are enough for a portfolio piece.
- **Releases**: tag `v0.2.0` once someone else has run it end to end with a
  connected engine.

## After publishing

- [ ] Open the repo in a private window: README renders, images load, tables and
      anchors work, no relative link 404s.
- [ ] Confirm the licence and the "unofficial / unaffiliated" notice are visible
      near the top.
- [ ] Add the one-line pitch to the CV, not the tech stack:
      *"A native Linux desktop for AI agents — approvals you can see, work you
      can follow."*

## Deliberately not done

Stated so the README is not read as a promise:

- **Voice** — arrives with the engine that supports it.
- **Embedding-based recall** — knowledge retrieval is lexical today, and says so.
- **Declarative plugin UI** — the `ui` permission is reserved, not implemented.
- **Schedules while the app is closed** — they fire on next start, by design.
