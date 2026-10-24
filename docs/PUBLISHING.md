# Publishing checklist

Mantel is prepared as a public portfolio repository. This is the short list of
what is true, what to check, and exactly what to run.

## Before you push

- [ ] **Decision: name.** The working name is `mantel`. Changing it touches
      `README.md`, `docs/`, the window title, `app/main.py` (`APP_ID`), the
      sidebar wordmark, `packaging/install.sh`, and the desktop entry. It is a
      single commit, but do it *before* publishing.
- [ ] **Decision: relative links.** `README.md` links relative paths only, so
      the repo renders the same on GitHub and locally.
- [ ] **No credentials.** Nothing under `~/.gemini`, no OAuth token, no
      `client/` secrets. `.gitignore` covers them; verify with
      `git log --all --name-only --format= | grep -iE 'credential|token|oauth'`.
- [ ] **No proprietary assets.** No Google fonts, glyph atlases, app icon or
      protocol dumps are tracked. `assets/README.md` explains how a user
      supplies their own.
- [ ] **No personal data in images.** Screenshots are rendered in demo mode
      (`tools/make_screenshots.py`), which uses a neutral identity, workspace
      and engine home.
- [ ] **Tests green.** `make test-offline` (no engine needed) and, optionally,
      the engine-backed ones with `agy` or a logged-in `pi`.

## Create the repository

```bash
gh repo create mantel --public --source=. --remote=origin --push

gh repo edit --description \
  "A native GTK4 desktop for AI agents on Linux — approvals, work panel, changes and durable conversations, with Pi and Gemini as engines." \
  --add-topic gtk4 --add-topic libadwaita --add-topic linux --add-topic python \
  --add-topic pygobject --add-topic ai-agents --add-topic agent-harness \
  --add-topic pi-agent --add-topic desktop-app
```

Only `main` should be pushed. There is a local `archive/pre-cleanup` branch from
before the repositioning; it contains the earlier history and **must not** be
published:

```bash
git branch -D archive/pre-cleanup
```

## Repository settings worth setting

- **About**: description above, plus the README tagline.
- **Social preview**: upload a screenshot (`docs/screenshots/home.png` is
  1744×1168; crop or letterbox to 1280×640).
- **Topics**: as above.
- **Discussions**: optional; issues are enough for a portfolio piece.
- **Releases**: tag `v0.1.0` only when the app runs end-to-end for a fresh user
  with a connected engine.

## After publishing

- [ ] Open the repo in a private window and check the README renders: images,
      tables, anchors, and that no relative link 404s.
- [ ] Confirm the licence and the "unofficial / unaffiliated" notice are
      visible near the top.
- [ ] Add the repo to your CV/portfolio with the one-line pitch, not the tech
      stack: *"A native Linux desktop for AI agents — approvals you can see,
      work you can follow."*

## What is deliberately not done yet

Stated here so the README is not read as a promise:

- Voice (Gemini Live) — arrives with the Gemini SDK engine.
- Durability across restarts — M4 in `docs/plan/pi-engine.md`.
- The productivity surfaces in `docs/VISION.md` (Today, capture, memory,
  plugins) — those are the product roadmap, not shipped features.
