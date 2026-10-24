# Port notes — what the reverse engineering actually yielded

Companion to `../RE_REPORT.md` (artifact analysis) and `../PROTOCOL_SPEC.md`
(recovered protocol). This records what mattered *for building the Linux
client*, including two findings that changed the approach.

## 1. The decisive finding: most of the product is already portable

The earlier analysis concluded "the macOS binary cannot run on Linux, so
reimplement at the seams." Re-checking the seams changed the picture:

- **`agy` ships as a native Linux x86-64 ELF.** The engine the desktop app
  drives is not macOS-specific. `file ~/.local/bin/agy` → ELF 64-bit LSB pie
  executable, x86-64, 215 MB.
- **It already speaks a GUI-shaped protocol.** `--output-format stream-json`
  emits NDJSON: `init` (conversation id, 58–60 tool names, permission mode),
  `step_update` (`text_delta` streaming, usage), `result` (status, response,
  duration, token counts). `--conversation <id>` resumes.
- **The visual identity is pure data**: the icon font, four text faces, ten
  Lottie animations and the app icon all extract cleanly from the bundle.

So the macOS-only part is the *shell*, and the shell is the thing worth
rebuilding natively. That inverted the effort estimate.

## 2. `GeminiSetup.exe` is not the Windows app

It is `UpdaterSetup.exe` (Google's Omaha updater stub, FileVersion
157.0.8089.0), which is why it is a 13 MB PE32 i386 with no application
payload. It does, however, leak the real app's identity:

```
appguid={533DD80C-942A-4464-B6A9-2E59428D784E}&appname=Gemini&needsadmin=false&ap=prod
```

An Omaha `update2/json` query against that GUID returned an empty body, so the
Windows package was not retrieved. Independently confirmed the macOS bundle
carries no Electron/asar/CEF/V8 payload at all (3,019 files scanned) — it is
genuinely native AppKit.

## 3. The icon font is a ligature + PUA font, and GTK cannot render it

`LuminousSymbols[FILL,opsz,wght].ttf` — 946 glyphs, 614 codepoints (548 in the
private use area), `rlig`/`rclt` ligature lookups, and a `FILL` axis for
filled variants. Three separate traps:

**(a) `getBestCmap()` mixes planes.** 71 of 577 glyph names resolve to
Supplementary Private Use Area-B codepoints (e.g. `gemini_spark` → U+FFF13).
Those render as notdef. Codepoints must be taken per-subtable and preferred
from the BMP PUA range.

**(b) GTK's text pipeline renders notdef for valid codepoints.** Verified with
outlines extracted straight from the font: `add` (U+E145) is 1 contour,
28 points, bbox (200,200)–(760,760) — a plus sign. Rendered through a
`Gtk.Label` it came out as a boxed `7`, through CSS, markup and `AttrFontDesc`
alike. FreeType (via ImageMagick, direct font file) drew the correct plus.

**(c) Even a direct PangoCairo render is non-deterministic across processes.**
The same `icon_texture("add", 24)` call returned a correct plus in one process
and a notdef box in another, depending on font resolution order — while
`Pango.Layout(fontmap.create_context())` and `PangoCairo.create_layout(cr)`
behaved differently inside a single process.

**Resolution:** stop rendering glyphs at runtime. `tools/render_icons.py`
renders all 577 glyphs × outlined/filled × light/dark (2,308 PNGs) once, in a
process with no GTK, and the app loads those. The output is inspectable
(`tests/probe_icons.py` renders the whole sheet), so correctness is verified
rather than assumed.

Also worth recording: the variable font was frozen to static
`Gemini Icons` / `Gemini Icons Filled` instances
(`tools/make_icon_fonts.py`). This did **not** fix the rendering, but it does
give filled icons as a family switch instead of a variation string, which is
more robust in GTK4 CSS.

## 4. Font registration must precede GTK

Fontconfig reads `FONTCONFIG_FILE` exactly once, on first use, and Pango
triggers that during GTK initialisation. Setting it in an `activate` handler
silently does nothing — `fc-match` finds the family, but Pango never uses it.
Hence `app/fonts_env.py`, a stdlib-only module imported before anything that
touches GTK.

## 5. Environment constraints worth knowing

- The development host has **no capturable compositor** (no `wlr-screencopy`,
  no portal screenshot) and **no GPU inside the sandbox**, so UI verification
  is done by rendering the real widget tree offscreen to PNG
  (`tests/harness.py`, `--smoke`). This proved good enough to catch every
  layout and icon defect above.
- The sandbox mounts `~/.cache` and `~/.gemini` read-only. The engine therefore
  cannot persist conversations during verification, and `--conversation`
  resume silently creates a *new* conversation with an empty response instead
  of failing loudly. On a normal desktop session this does not apply; the app
  keeps its own transcript regardless, and treats the engine id as an
  optimisation.
- `gtk4-layer-shell` must be `LD_PRELOAD`ed ahead of `libwayland`, and Mutter
  does not implement `wlr-layer-shell` at all. The overlay detects both and
  falls back to a centred undecorated window.

## 6. Measured, not assumed

| Claim | Evidence |
|---|---|
| Engine bridge streams | `tests/test_engine.py`: `[delta] 'BRIDGE-OK'`, status SUCCESS, 3.9 s, 18,859 tokens |
| Full UI + engine path | `--smoke-prompt`: answer rendered with `12.4s · 2,185 tok` footer |
| Model catalogue | `gemini-3.8-flash-{high,medium,low}`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium` |
| Icons correct | `docs/icons.png` — 4 groups, outlined + filled |
| Fonts load | `docs/app.png` — Google Sans Flex headings, Google Sans Text body |

---

# Part 2 — the shell design

The shell follows the "Hearth" concept dashboard by **@UiRahMan92**
(https://x.com/UiRahMan92). `docs/DESIGN.md` holds the measurements; this
section records the findings that changed how the port was built.

## 6. The reference is a different product, not a restyle of Gemini

"Hearth" is a personal-life dashboard concept, not the Gemini desktop app, so
nothing about it could be copied directly; only the design system could be
measured and rebuilt:

- the palette, the type system, the component geometry, the layout grid;
- the artwork, a painterly landscape keyed to the reference's palette —
  drawn here procedurally with Cairo (`app/hero_art.py`) from shaders
  recovered out of the original app, not copied.

## 7. Typography: the reference's mono is condensed, and not shippable

Measured from the reference frames:

| Text | ink w | ink h | chars | advance/char |
|---|---|---|---|---|
| `Calendar` | 72 | 11 | 8 | 8.75 |
| `Memory` | 53 | 13 | 6 | 8.75 |
| `Files` | 43 | 12 | 5 | 8.6 |
| `Build a better morning routine` | 212 | 12 | 30 | 7.07 |
| `Plan my vacation` | 136 | 12 | 17 | 8.0 |

Advance/height ≈ 0.72, which is *narrower* than any monospace available
here (all are 0.6 em). The reference face is a proprietary condensed mono
and cannot be shipped, so **JetBrains Mono** (SIL OFL) is bundled instead.

The consequence was measured, not assumed: JetBrains Mono at 15.5 px gives
`Calendar` an ink width of 71 against the reference's 72 — a 1 % difference,
i.e. the advance matches. Its ascenders are shorter (10 px against 11), so
the type sits slightly flatter in the line. Rendered side by side, the
difference is not perceptible.

`Google Sans Code` was rejected: its `i` dot is a rhombus, while the
reference's is square.

## 8. Four GTK4 traps, all found by measuring pixels

**(a) Stylesheet priority.** Installing the app stylesheet at
`STYLE_PROVIDER_PRIORITY_APPLICATION` loses to the theme-name provider
(`Adwaita-empty`) in this environment. Every `Gtk.Button` then renders with
no background, no border and white-on-white text. `USER` priority fixes it
globally. Found by a subagent's probe, not by eye.

**(b) `background:` is not enough.** Adwaita paints buttons with a
*background image*; `background: transparent` clears only the colour, so the
image survives and rows keep a grey plate. `background-image: none` is
required as well.

**(c) CSS has no compound selectors.** `label.md-h2` is invalid in GTK4 CSS,
so the heading rule silently lost to `.msg-ai label` on specificity and every
heading rendered at body size. The defaults were moved onto the container so
the heading rule wins.

**(d) Pango markup has no `class` attribute.** `<span class="md-code">` is
rejected outright, and the label comes out *empty* — the whole paragraph
vanishes rather than falling back. Inline code now takes its colour from the
active palette instead.

Also: `Gtk.KEY_Return` does not exist in GTK4 (it is `Gdk.KEY_Return`), so
Enter-to-send never fired; `Gtk.TextView` has no `width-chars` property;
`Gtk.Button` has no `set_xalign`; pycairo has no `Context.create_*_gradient`
(they are `cairo.LinearGradient` / `cairo.RadialGradient` classes); and
`Gtk.DrawingArea` uses `set_draw_func`, not a `draw` signal.

## 9. Offscreen rendering needs the window forced open

With no compositor the window takes the virtual screen's size, so the
reference geometry could not be compared. `set_size_request` on the window
plus a settle frame before the snapshot produces an exact 1744 × 1168
render — the same size as the reference frame.

The sidebar's reveal animation made the snapshot *intermittent*: sometimes
the slide was caught mid-flight and the rail was missing. The render path
now disables the transition (`--smoke` ⇒ `animate=False`); the app itself
still slides. Verified over five consecutive runs.

## 10. Measured geometry that the port reproduces

| | Reference | This client |
|---|---|---|
| Sidebar width | 304 | 304 |
| Content left margin | 340 | 340 |
| Content right edge | 1699 | 1707 |
| Nav row pitch | 48 | 48 |
| Nav text ink (`Calendar`) | x 55, w 72 | x 56, w 71 |
| Nav text baseline | y 312 | y 313 |
| Task row pitch | 32 | 32 |
| Top bar height | 100 | 100 |
| Hero card | y 105–376, h 271 | h 271 |

## 11. Icon rendering, again

The pre-render decision from Part 1 was not enough: rendering the *icon
font* at runtime produced notdef boxes for the private-use codepoints
through CSS, markup and `AttrFontDesc` alike, while a direct FreeType render
of the same codepoint was correct. The whole set is therefore baked —
4,616 PNGs (577 glyphs × outlined/filled × white/grey/navy) — and the desktop
icon is composited from the baked Gemini mark rather than rasterised at
build time, because a Pango re-render of that glyph came out as a solid
shape with the sparkle missing.

---

# Part 3 — making it an agent

## 12. The engine is drivable, and its refusals are the approval mechanism

The engine's non-interactive mode already does everything a client needs
except *pausing*. Captured from `agy --print … --output-format stream-json`:

```json
{"event":"init","init":{"model":…,"cwd":…,"tools":[58 names],"permission_mode":…}}
{"event":"step_update","step_update":{"step_type":"tool","tool_name":"write_file",
  "state":"ACTIVE","tool_info":{"parameters":{"Path":"…"}}}}
{"event":"step_update","step_update":{"step_type":"tool","step_name":…,
  "state":"DONE","tool_info":{"output":"1 lines, 6 bytes"}}}
{"event":"result","result":{"status":"SUCCESS","denied_actions":[{"action":"write_file","display_name":"WriteFile"}]}}
```

`denied_actions` is the crucial field: the engine tried, was refused, and
*says so* rather than failing silently. That turns refusals into a queue the
client can render as approval cards.

## 13. Permissions are a config file the client can own

The engine reads shared grants from
`~/.gemini/config/config.json`:

```json
{"userSettings": {"globalPermissionGrants": {
  "allow": ["read_file(*)", "write_file(/home/me/project)"],
  "deny": [], "ask": ["run_command(*)"]}}}
```

Rule syntax is `action(path)`; `*` matches anything. Measured behaviour:

| Config | `--print` write of a new file |
|---|---|
| no config at all | **refused** (`denied_actions`) |
| `allow: ["read_file(*)"]` | **refused** |
| `allow: […, "write_file(*)"]` | **succeeds** |
| `ask: ["write_file(*)"]` | **refused** |

So the client can implement the desktop app's trust model — connect a folder,
and the agent may work there — by writing `write_file(<folder>)`-style rules.
`ANTIGRAVITY_PERM_GRANTS` (an env var present in the binary) is **not** the
mechanism; it had no effect in any format tried.

Modes also matter: `--mode accept-edits` writes files but still refuses shell
commands; `--dangerously-skip-permissions` allows both.

## 14. Sign-in is a loopback OAuth exchange against Google's published client

The engine reads credentials from `~/.gemini/oauth_creds.json` and nothing
else — proven by pointing `HOME` at a throwaway directory containing only
that file: the engine authenticated and answered. It also falls back to a
keyring (`keyringAuth: loaded token`) when the file is absent.

That makes the file the integration point. The exchange follows Google's own
open-source Gemini CLI (`code_assist/oauth2.ts`):

- client: `681255809395-…apps.googleusercontent.com` with secret
  `<redacted-google-oauth-client-secret>` — an *installed application* client,
  which Google's own source notes is "obviously not treated as a secret"
- scopes: `cloud-platform`, `userinfo.email`, `userinfo.profile`
- redirect: `http://127.0.0.1:<ephemeral port>/oauth2callback`, `access_type=offline`,
  CSRF `state`, and the token response written back as the creds file

`tests/test_signin.py` drives the whole thing against a mock Google,
including rejecting a mismatched `state` and the file being written `0600`.

## 15. Approvals replay, they do not pause

There is no way to answer a permission question mid-turn: `--input-format
stream-json` is documented as "one NDJSON message per line" but this build
silently ignores messages whose `event` field it does not recognise (probed
with six candidate schemas), and the interactive TUI takes its answers from
stdin in raw mode rather than a documented protocol.

So the client grants the rule and replays the request. `tests/test_agent_flow.py`
proves the loop: refuse → card → grant → the file appears, and a
`--dangerously-skip-permissions` run needs no approval at all.

The honest limitation: an approved action costs a second turn.

## 16. The stream-json input protocol, cracked

Earlier I recorded that `--input-format stream-json` silently ignored every
message shape I tried. That was wrong in an interesting way: the messages were
not being ignored for being malformed — they were **unsupported events**, and
the engine warns to stderr:

```
warning: ignoring unsupported stream input message event "user_input"
```

Using that warning as an oracle (fast, no turn cost), and then reading the
error text of accepted-but-incomplete messages, gives the protocol:

```json
{"event": "user", "message": {"content": "Reply with exactly: STREAM-OK"}}
```

→ `init` (+ conversation id), streamed `step_update` `text_delta`s, then
`result`. Verified live.

Things this establishes:

* **Only one input event exists: `user`.** Sixteen other candidate names
  (`permission`, `cancel`, `interrupt`, `tool_result`, `set_model`, …) are all
  rejected. There is therefore **no way to answer a permission prompt
  mid-turn** — which is why approvals in this client grant a rule and replay
  the request rather than pausing it. That limitation is now a measured fact,
  not an assumption.
* The envelope is `message.content`, not `prompt` or `text`; the Go type
  behind it is `printmode.StreamInputUserMessage`, whose `PromptText()` method
  had hinted at the field before the error text confirmed it.
* A persistent process is possible: one NDJSON line per turn, context held by
  the process. This client still spawns per turn (simpler lifecycle, and the
  engine's own `--conversation` resume works when it can write its store) but
  the fast path is available.

## 17. Multi-turn context is now resilient

Measured: `--conversation <id>` resumes correctly when the engine can write
`~/.gemini` — a fresh turn asked "what number did I ask you to remember?"
answered `417`, with the same conversation id. When it *cannot* write (this
analysis sandbox mounts `~/.gemini` read-only) it silently starts a new
conversation and returns a different id.

So the client watches for that: if the id that comes back is not the one it
asked to resume, it marks the conversation `context_lost` and replays the
recent turns inline on the next request. `tests/test_context_fallback.py`
checks the replay is correctly built, bounded to eight turns, truncates huge
turns and skips blank ones.

## 18. Schedules run for real

`app/schedules.py` owns its own store (JSON in the XDG data dir) with a
five-field cron parser, and `app/scheduler.py` fires due schedules while the
app is open — one at a time, catching up a missed slot exactly once. Verified
end to end against the live engine: an overdue schedule ran, answered
`SCHEDULE-FIRED`, and the run was persisted with a timestamp so it was no
longer due. `tests/test_schedules.py` covers parsing, next-run maths,
descriptions, pause/resume, the history cap and a corrupt store.

## 19. The last three features were all engine surfaces already

Each of the remaining "missing" features turned out to be a capability the
engine already has, needing only a UI:

**Image generation.** Asking the engine to create a picture makes it call
`invoke_subagent` with `TypeName: "image-generator"`, which spawns an *Image
Generation Agent*; that agent writes a PNG. Verified: "a single ripe red apple
on a plain white background" produced a 1024 × 1024 photorealistic PNG
(≈1 MB). It needs a writable `~/.gemini/antigravity-cli`, so it fails cleanly
on a read-only home — the error text names the mount.

**Screen capture.** The compositor's portal exposes
`org.freedesktop.portal.Screenshot` and it works here: a real 729 KB PNG came
back. That is the portable route on Wayland and X11, so the client uses it
first and falls back to `grim` (wlr-screencopy) and ImageMagick's `import`.

**Remote control.** `agy remote-control start|status|stop` manages a systemd
*user* daemon and prints an instance name to pair with the phone. The status
output is parseable:

```
Daemon status: active (running)
Instance name: sefirah-lunar-plume
```

so the client shows it as a toggle with the instance name, and surfaces the
engine's own error when the daemon cannot start (usually a read-only home,
because it writes a token into the engine config).

The pattern is consistent with everything else in this port: the hard part
was never reimplementing these features, it was finding the surface.
