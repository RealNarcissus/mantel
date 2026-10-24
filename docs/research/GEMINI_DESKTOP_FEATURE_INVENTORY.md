# Google Gemini Desktop App — Feature Inventory (public-source research)

Research date: 2026-10-22. All sources are public URLs, cited inline.
Legend: **CONFIRMED** (official Google source or multiple independent sources) ·
**INFERRED** (logical consequence / third-party only) · **NOT FOUND** (no public evidence).

> Note on dates: Google shipped the native **macOS** app 2026‑04‑15 and the **Windows**
> app 2026‑09‑10/11. The Gemini *desktop* product in this scenario is macOS + Windows only
> (no official Linux build).

---

## 1. Account / sign-in

| # | Feature | Status | Evidence + UI note |
|---|---|---|---|
| 1.1 | Requires a Google Account | **CONFIRMED** | [Mac help](https://support.google.com/gemini/answer/17011627): "A personal Google Account you manage on your own, or a work or school account that your administrator has enabled Gemini." [Windows help](https://support.google.com/gemini/answer/18263854): same. UI: app prompts "Sign in with your Google Account if prompted" at first launch. |
| 1.2 | Sign-in happens on first launch | **CONFIRMED** | ZDNET hands-on: "As the Gemini app opens, you should be prompted to sign in with your Google account." [source](https://tech.yahoo.com/ai/gemini/articles/tried-gemini-app-mac-better-211828596.html) |
| 1.3 | One account across desktop/web/mobile; chats + memories sync | **CONFIRMED** | [gemini.google/desktop](https://gemini.google/desktop/) FAQ: "As long as you are signed into the same Google account, your chat history and memory will sync across all devices." |
| 1.4 | Account menu / profile in bottom-left corner of app | **CONFIRMED** | 9to5Google: new **Usage limits** page "can be quickly accessed from the account menu in the bottom-left corner" (previously opened `gemini.google.com/usage` in browser). [source](https://9to5google.com/2026/06/30/gemini-spark-mac-app/) |
| 1.5 | Work/school account **cannot** use agent mode (Tasks) or custom MCP apps | **CONFIRMED** | [Tasks doc](https://support.google.com/gemini/answer/17094507): "For now, this feature isn't available if you sign in with a work or school Google Account." [Custom apps doc](https://support.google.com/gemini/answer/17209137): same. |
| 1.6 | Sign-out entry point in desktop app | **NOT FOUND** | Only the *web* app's sign-out path is documented (profile picture/initial → Sign out). [source](https://support.google.com/gemini/answer/13278668) |
| 1.7 | **Multiple accounts / account switching** in the desktop app | **NOT FOUND** | No Google doc, blog post, or review mentions adding a second Google account or switching accounts in the native app. All public material implies a single signed-in account. |
| 1.8 | Signed-out state of the desktop app | **NOT FOUND** | No public description of what the app shows before sign-in. Docs only say "if prompted". |
| 1.9 | Browser-based OAuth vs in-app webview vs local callback server | **NOT PUBLISHED for the Gemini desktop app** | See §7 for the nearest public evidence. |

---

## 2. Core surfaces

| # | Feature | Status | Evidence + UI note |
|---|---|---|---|
| 2.1 | **Chat** | **CONFIRMED** | Sidebar with "New chat" + conversation history; model picker (Fast / Thinking / Pro). [ZDNET](https://tech.yahoo.com/ai/gemini/articles/tried-gemini-app-mac-better-211828596.html) |
| 2.2 | **Chat ⇄ Task mode toggle above the prompt box** | **CONFIRMED** (Oct 12–13, 2026) | "Chat" and "Task" buttons sit directly above the prompt box; replaced the old "Spark" sidebar tab. [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) · [AndroidPure](https://www.androidpure.com/gemini-spark-task-mode/) |
| 2.3 | **"Dive" mode** | **NOT FOUND** | No Google product/feature named "Dive" appears in any source. The real names are **Deep Research** and **Deep Think**. Do not implement "Dive". |
| 2.4 | **Deep Research** | **CONFIRMED** | Web: `Add Files → Deep Research`, optional Sources (Search default; Gmail/Drive if connected), `Edit plan` → `Start research` → `Open`; 5–10 min; report opens in Canvas panel with `Create → Audio Overview` and `Export to Docs`. [source](https://support.google.com/gemini/answer/15719111). Windows desktop release note: "dive into in-depth research on any topic" → present in the desktop workspace. [release notes](https://gemini.google/release-notes/) (2026.09.10) |
| 2.5 | **Deep Think** | **CONFIRMED** | "select 'Deep Think' in the prompt bar" + "Thinking" in the model dropdown; Ultra only; Gemini notifies when the response is ready (minutes). [release notes](https://gemini.google/release-notes/) (2025.12.04, 2026.02.12) |
| 2.6 | **Gems** (legacy custom assistants) | **CONFIRMED — being retired** | Gems move to the Settings panel 2026‑11‑17; removed for Workspace business/enterprise **no sooner than 2027‑03‑01**; education **no sooner than 2027‑06‑01**; personal accounts **November 2026**. Existing Gems are auto-migrated to **skills**. [transition doc](https://support.google.com/gemini/answer/18560919) · [Workspace blog](https://workspaceupdates.googleblog.com/2026/09/skills-gemini-app-workspace.html) |
| 2.7 | **Skills** (successor to Gems) | **CONFIRMED** | Sidebar → **Customize** → **Skills**. Create 3 ways: *Create with Gemini*, prefilled template, *Create manually*, or **Upload** a `SKILL.md` (+optional reference files, ≤100 MB). Skill names must be lowercase-hyphen. Max 100 active skills. Download skill = `.zip`. Invoke in chat with `/` (soon `@`) or `@`; Gemini auto-applies relevant skills. [source](https://support.google.com/gemini/answer/17094296) |
| 2.8 | **Skills do not work with**: Canvas, Deep Research, Create video, Create music, Guided learning | **CONFIRMED** | [source](https://support.google.com/gemini/answer/18560919) |
| 2.9 | **Extensions** (per-Gem Google-app extensions) | **NOT FOUND as a current surface** | The current surface is **Connectors** (Connected Apps). A third-party IT KB calls it "Settings → Extensions / Connected Apps" — low confidence. [KB](https://tcnj.teamdynamix.com/TDClient/1798/Portal/KB/Article/173156/Installing-and-Using-the-Google-Gemini-Desktop-App) |
| 2.10 | **Connectors / Connected Apps** | **CONFIRMED** | Sidebar → **Customize** → **Connectors**; each app card lists description, supported/unsupported actions, example prompts; `Add` / `More options Disconnect`. 40+ apps. [source](https://support.google.com/gemini/answer/13695044) · [release notes 2026.10.13](https://gemini.google/release-notes/) |
| 2.11 | **Third-party connectors** | **CONFIRMED** | Canva, Dropbox, Instacart, OpenTable, Zillow Rentals, Adobe, Box announced. [release notes 2026.10.13](https://gemini.google/release-notes/) · [MacRumors 2026‑07‑01](https://www.macrumors.com/2026/07/01/google-gemini-spark-comes-to-mac/) |
| 2.12 | **File / folder attachment** | **CONFIRMED** | `+` (Add files and tools) → local file from Mac, Google Drive, Google Photos, Gemini Notebook, Upload files. macOS Task mode additionally has **Add Mac folder** under *Connected folders*. [source](https://support.google.com/gemini/answer/17011627) · [source](https://support.google.com/gemini/answer/17208717) |
| 2.13 | **Image input** | **CONFIRMED** | "Analyze images: Upload images and ask Gemini questions about them." [source](https://support.google.com/gemini/answer/17011627) |
| 2.14 | **Voice — in-app dictation (Mic)** | **CONFIRMED** | Click **Mic** in the composer to dictate a prompt; click **Send** to submit. [source](https://support.google.com/gemini/answer/17011627) |
| 2.15 | **Voice — "Speak to Window" (macOS)** | **CONFIRMED** | Press-and-hold **fn**; release submits. Also: tap fn twice, or open Gemini → click *Speak to Window* → tap fn again. ESC or **Close** stops a session. Can dictate into the cursor of any app, refine highlighted text, summarise highlighted files, generate images into the workspace. Settings: **Gemini → Settings → Speak to Window → Use reasoning** toggle (on = agentic reasoning from screen context; off = plain dictation cleanup), plus **Tap to speak** vs **Hold while speaking** shortcut assignment. [Mac help](https://support.google.com/gemini/answer/17011627) · [release notes 2026.07.29](https://gemini.google/release-notes/) |
| 2.16 | **Voice-read responses + voice selection** | **CONFIRMED (third-party)** | 9to5Mac: settings allow "selecting from one of several voices for voice-read responses", plus "open new chats in mini chat or the main window" and "resetting mini chat based on a time duration". [source](https://9to5mac.com/2026/04/15/google-launches-gemini-mac-app-heres-what-it-offers/) |
| 2.17 | **Gemini Live (full-duplex) in the desktop app** | **NOT FOUND** | Release notes say Gemini Live integrated into chat for **Android and iOS** (2026.05.19). No desktop-app equivalent documented. |
| 2.18 | **Canvas** | **CONFIRMED** | Canvas panel in the chat; `Create` menu, `Export .txt/.md/Drive`, `Share Canvas`, `Export to Docs`, `Copy Contents`. [source](https://support.google.com/gemini/answer/15719111) · [source](https://support.google.com/gemini/answer/17094507) |
| 2.19 | **Image generation (Nano Banana)** | **CONFIRMED** | Desktop: Nano Banana image generation directly from the desktop workspace; dedicated *Creativity* workspace. Models: Nano Banana 2 Lite (Flash-Lite), Nano Banana 2 (Flash/Pro), Nano Banana Pro (Pro + paid plan, redo). [source](https://gemini.google/desktop/) · [source](https://support.google.com/gemini/answer/14286560) |
| 2.20 | **Image editing UI** | **INFERRED** | Nano Banana editing is confirmed for the web app (Library → image → **Chat** under the image → prompt; `More → Redo with Pro`; `Download full size`; `Export to Docs`). No desktop-specific image-editor surface is documented, but the desktop app exposes "Create image" from its Create menu. [source](https://support.google.com/gemini/answer/14286560) |
| 2.21 | **Video generation (Gemini Omni)** | **CONFIRMED** | "direct high-quality video creation with Gemini Omni"; also "Create video" in the desktop Create menu. [source](https://gemini.google/desktop/) · [release notes 2026.05.19](https://gemini.google/release-notes/) |
| 2.22 | **Music generation** | **CONFIRMED** | "Create music" appears in the desktop app's blue gradient Create menu (image / video / music / More tools). [source](https://gemini.google/desktop/) |
| 2.23 | **Scheduled / recurring prompts** | **CONFIRMED** | Two distinct systems: (a) **Scheduled actions in chat** — up to **10 active schedules**, `Scheduled` page in the sidebar (Active/Paused/Completed/Suggested), `More → Edit/Pause/Resume/Delete`, delivered as unread chat + notification; (b) **Schedules inside Tasks** — time- or event-triggered, up to **15 concurrent tasks**. [source](https://support.google.com/gemini/answer/16316416) · [source](https://support.google.com/gemini/answer/17094507) · [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) |
| 2.24 | **Personal Intelligence** | **CONFIRMED** | Opt-in; required for Tasks in Gemini. Connects Gmail, Photos, YouTube, Search. [source](https://support.google.com/gemini/answer/17094507) · [release notes 2026.01.20](https://gemini.google/release-notes/) |
| 2.25 | **Daily Brief / Student hub** | **CONFIRMED (web/mobile-first)** | Daily Brief = Personal-Intelligence digest; Student hub + study notebooks. No desktop-specific mention. [release notes](https://gemini.google/release-notes/) |

---

## 3. Agent capabilities (Task mode / "Spark")

| # | Feature | Status | Evidence + UI note |
|---|---|---|---|
| 3.1 | Agent mode exists, renamed over time | **CONFIRMED** | Announced as **Gemini Spark** at I/O 2026 (2026‑05‑19, 24/7 personal AI agent on cloud VMs); landed in the **macOS** app 2026‑06‑30 as a **Spark** sidebar tab; renamed to **Task mode** 2026‑10‑12/13 and moved to a Chat/Task toggle. [release notes](https://gemini.google/release-notes/) · [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) |
| 3.2 | **Local file system access (macOS only)** | **CONFIRMED** | "Gemini can only view files or directories that you specifically add to the Connected folders toolbar." Composer has a **Connected folders** row with `Add Mac folder` and per-item `Disconnect`. Gemini can analyse/edit/rename/re-organize files, and with permission "can view and edit most folders on your Mac, including downloads, files on your desktop, documents, and photos". [source](https://support.google.com/gemini/answer/17208717) |
| 3.3 | **Backup files before edits** | **CONFIRMED** | "When Gemini works with your computer files, it will create temporary backup files. You can choose to recover these backup files… Backup files are deleted when you start a new query or task, or after 24 hours." [source](https://support.google.com/gemini/answer/17208717) |
| 3.4 | **Local terminal / shell execution** | **NOT FOUND / NO** | No public evidence of a local terminal. Code execution happens on a **remote computer** in Google cloud ("Delete remote code execution data" in Task settings). [source](https://support.google.com/gemini/answer/17094507) |
| 3.5 | **MCP servers (custom)** | **CONFIRMED** | Add a custom app by MCP server URL in Connected Apps; supports **Dynamic Client Registration**, with an Advanced-features path for manual client id/secret. Custom apps are **English-only**, **18+, US-only, personal account**, require Keep Activity on, and are usable in **web + mobile** (and macOS app, where they are labelled **Connectors**). [source](https://support.google.com/gemini/answer/17209137) · [layer3labs](https://www.layer3labs.io/guides/how-to-use-gemini-spark) |
| 3.6 | **Bundled MCP servers (git / obsidian / messages / blender)** | **NOT FOUND** | No public mention of Google shipping bundled Git/Obsidian/Apple-Messages/Blender MCP servers. |
| 3.7 | **Computer use / screen control** | **CONFIRMED (partial)** | (a) *Share window* — macOS `⌘ + ⌘` or `+ → Share window → pick a window`; the app requests macOS **screen-recording/accessibility** permission on first use. Windows reviews say the Windows app can share **the entire desktop or a specific window**. (b) *Chrome auto browse* — drives the **local Chrome** on your desktop; Gemini asks for permission the first time and **confirms before every browsing task**. (c) *Remote browser* — cloud browser + remote computer; you can **Take over task** / **Go back to Gemini**. [source](https://support.google.com/gemini/answer/17011627) · [source](https://support.google.com/gemini/answer/17094507) · [ZDNET](https://tech.yahoo.com/ai/gemini/articles/tried-gemini-app-mac-better-211828596.html) |
| 3.8 | **Permission / approval model** | **CONFIRMED** | • Every task action is approved by the user: "approve every action with one tap" [desktop FAQ](https://gemini.google/desktop/). • MCP write actions require **manual confirmation**: "Currently, Gemini requires manual confirmation for any write actions" [custom apps](https://support.google.com/gemini/answer/17209137). • macOS Task settings toggle **"Alert when a backup fails"** — *on by default* — "Gemini asks for approval before continuing a task when it is unable to back up a file in a connected folder". • macOS Task settings toggle **"Keep this Mac awake to run tasks"**. • Destructive actions (permanent delete, share to 3rd parties) prompt for permission. [9to5Google](https://9to5google.com/2026/06/30/gemini-spark-mac-app/) · [source](https://support.google.com/gemini/answer/17208717) |
| 3.9 | **Work panel / progress UI** | **CONFIRMED** | Task thread → top **progress chip** opens the work panel: Completed step / Current step / Planned step, plus a **Files** section listing files Gemini read or updated. [source](https://support.google.com/gemini/answer/17094507) |
| 3.10 | **Remote control (phone → Mac)** | **CONFIRMED** | On the phone: Gemini → **Task** → **Add Computer** → select your Mac. Requires the Mac app running, the same Google account, same Wi-Fi **or** Bluetooth linked, and accepting terms of use in the macOS app. Capabilities: assign tasks, voice commands via the phone mic, typing, read past chats, quick actions (delete chat / start chat), media control (play/pause/skip). [source](https://support.google.com/gemini/answer/17208717) |
| 3.11 | **Google Antigravity integration (macOS)** | **CONFIRMED** | "click **Antigravity** at the top of the Gemini app on your Mac"; spin up a coding agent, **approve its plan**, agent builds and tests code in the background and **notifies you when ready**. English, personal + eligible work accounts (18+). [release notes 2026.10.13](https://gemini.google/release-notes/) |
| 3.12 | **File types the agent can generate** | **CONFIRMED** | .json .md .tex .txt / .pdf .docx / .csv .tsv .xlsx / .pptx / .py .js .ts .cpp .cc .c .h .java .go .rs .cs .php .rb .swift .kt .dart .sql .sv .sh / .html .jsx .tsx .angular / .png .jpg .jpeg .svg / .mp3 .mp4 / .tar .tar.gz .gz .zip. Plus native Google Docs/Sheets/Slides. [source](https://support.google.com/gemini/answer/17094507) |
| 3.13 | **Task mode on Windows** | **CONFIRMED ABSENT** | Google lists supported Task surfaces as mobile app, **Mac app**, gemini.google.com — **not** the Windows app. [layer3labs](https://www.layer3labs.io/guides/how-to-use-gemini-spark) (secondary; official docs likewise only mention the Mac app) |
| 3.14 | Task eligibility gates | **CONFIRMED** | 18+, personal Google Account, Google AI Pro or Ultra, Keep Activity ON, Personal Intelligence opt-in, outside EEA / UK / Switzerland / Nigeria. [source](https://support.google.com/gemini/answer/17094507) |

---

## 4. Native shell features (desktop-only)

| # | Feature | Status | Evidence + UI note |
|---|---|---|---|
| 4.1 | **Global hotkey → mini chat** | **CONFIRMED** | macOS **Option + Space** = mini chat overlay; **Option + Shift + Space** = full chat window. Windows **Alt + Space**. Both **customizable in Settings → Shortcuts**. [source](https://gemini.google/desktop/) · [source](https://support.google.com/gemini/answer/17011627) |
| 4.2 | **Menu bar / Dock (macOS)** | **CONFIRMED** | Gemini icon in the **menu bar** (top of screen) + **Dock** icon. Menu path: **Gemini → Settings → …** and **Gemini → Check for Updates**. [source](https://gemini.google/desktop/) · [source](https://support.google.com/gemini/answer/17011627) |
| 4.3 | **Taskbar / System tray (Windows)** | **CONFIRMED** | Launch from Taskbar; Gemini icon in the system tray. Installer "places shortcuts in your Start Menu and System Tray". [source](https://gemini.google/desktop/) · [KB](https://tcnj.teamdynamix.com/TDClient/1798/Portal/KB/Article/173156/Installing-and-Using-the-Google-Gemini-Desktop-App) (third-party) |
| 4.4 | **Window layout: mini chat overlay + full window** | **CONFIRMED** | Two surfaces: a small Spotlight-style mini chat and a full chat workspace. Mini chat can be configured to auto-reset after a time duration, and new chats can open in either mini chat or main window. [source](https://9to5mac.com/2026/04/15/google-launches-gemini-mac-app-heres-what-it-offers/) |
| 4.5 | **Sidebar structure** | **CONFIRMED** | Sidebar holds: **New chat**, conversation history (unified with Task threads since Oct 2026; filter by All / Ready / Needs attention / In progress), **Customize** (→ Connectors, Skills), **Scheduled** page, and the account menu bottom-left. [source](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) · [source](https://support.google.com/gemini/answer/13695044) |
| 4.6 | **Auto-updater** | **CONFIRMED** | macOS: `Gemini → Check for Updates` → **Install update**. Windows: bottom-right notification "Restart to update". [source](https://support.google.com/gemini/answer/17011627) · [source](https://support.google.com/gemini/answer/18263854) |
| 4.7 | **Notifications** | **CONFIRMED (limited)** | Confirmed: Windows update notification (bottom-right); Antigravity "notifying you the second it's ready". NOT confirmed: a desktop notification when a chat/task finishes. |
| 4.8 | **macOS Accessibility / Screen Recording permission prompts** | **INFERRED (third-party only)** | "Gemini requires Accessibility permissions so that global keyboard shortcuts and active window overlays can function properly." [KB](https://tcnj.teamdynamix.com/TDClient/1798/Portal/KB/Article/173156/Installing-and-Using-the-Google-Gemini-Desktop-App) |
| 4.9 | **Drag & drop files into the app** | **NOT FOUND** | Only picker-based "Add files and tools" / "Add Mac folder" are documented. |
| 4.10 | **`gemini://` URL scheme / deep links** | **NOT FOUND** | No public evidence the Gemini desktop app registers a `gemini://` URL scheme or handles deep links. (The `gemini://` hits on the web are the unrelated Gemini Gopher protocol, and a 2015-era `gemini-ios` issue.) |
| 4.11 | **"Open with" / file associations / Quick Look** | **NOT FOUND** | No evidence the app registers as a handler for documents. |
| 4.12 | **Native implementation** | **CONFIRMED** | macOS app is "**100% native Swift**", built with the Google Antigravity team, "100+ features in less than 100 days". [9to5Mac quoting Josh Woodward](https://9to5mac.com/2026/04/15/google-launches-gemini-mac-app-heres-what-it-offers/) |
| 4.13 | **System requirements** | **CONFIRMED** | macOS: Apple Silicon, macOS Sequoia 15.0+, 8 GB RAM, 200 MB disk. Windows: Windows 10+, x64 + ARM64, 8 GB RAM, 200 MB disk; installer `GeminiSetup.exe`. [source](https://support.google.com/gemini/answer/17011627) · [source](https://support.google.com/gemini/answer/18263854) |
| 4.14 | **Admin control** | **CONFIRMED** | The Gemini app (web + mobile + Chrome + **Gemini on Mac** + **Gemini for Windows**) is controlled by Generative AI settings in the Workspace Admin console; on by default for orgs with Gemini enabled; no end-user toggle. [source](https://support.google.com/a/answer/14571493) · [Mac blog](https://workspaceupdates.googleblog.com/2026/04/now-available-gemini-app-for-mac.html) · [Windows blog](https://workspaceupdates.googleblog.com/2026/09/the-gemini-desktop-app-is-now-available-for-Windows.html) |
| 4.15 | **Menus on macOS** | **CONFIRMED (partial)** | Documented macOS menu items: **Gemini → Settings**, **Gemini → Check for Updates**. `Settings` sub-pages seen: **Speak to Window**, **Tasks**, **Shortcuts**. No published full menu-bar inventory (no File/Edit/View/Window/Help breakdown). |

---

## 5. Desktop-specific vs web app

**Desktop-only (not in the web app):**
- Global hotkey mini chat / full chat (Option+Space, Option+Shift+Space, Alt+Space) — [desktop FAQ](https://gemini.google/desktop/)
- Share window (macOS `⌘+⌘`; Windows: whole desktop or a window) — [Mac help](https://support.google.com/gemini/answer/17011627)
- Speak to Window (hold `fn`, dictation into any app) — [Mac help](https://support.google.com/gemini/answer/17011627)
- **Connected folders** = local filesystem sandbox for the agent (macOS) — [source](https://support.google.com/gemini/answer/17208717)
- **Task mode on macOS** (Windows not supported) — [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/)
- **Remote control** — phone assigns tasks to the Mac — [source](https://support.google.com/gemini/answer/17208717)
- **Antigravity launch** — one-click coding agent — [release notes](https://gemini.google/release-notes/)
- Dedicated **Creativity** workspace with Create image / Create video / Create music / More tools — [desktop FAQ](https://gemini.google/desktop/)
- Native auto-updater, menu bar / system tray presence

**Shared with web + mobile + desktop:** Chat, Tasks/Task mode (web + mobile + Mac), Skills, Connectors (40+ apps), custom MCP apps, Deep Research, Canvas, models (Argon / Pro / Thinking / Fast), Nano Banana / Omni, Scheduled page, Personal Intelligence.
[release notes 2026.10.13](https://gemini.google/release-notes/) ("Customize is rolling out globally across web, mobile, and the Gemini desktop app on Windows and macOS")

**Windows desktop app is essentially "the web app in a shell"** at launch: Alt+Space, quick answers, drafting, summarising, brainstorming, coding help, image analysis, Workspace connections, Nano Banana, Deep Research. No Task mode, no Speak-to-Window in the official Windows doc. [Windows help](https://support.google.com/gemini/answer/18263854) · [Windows blog](https://workspaceupdates.googleblog.com/2026/09/the-gemini-desktop-app-is-now-available-for-Windows.html)

---

## 6. Verdict on your binary feature-flag checklist

| Flag / class | Public verdict | Basis |
|---|---|---|
| `enable_agent_mode` | **CONFIRMED** | Task mode (= former Gemini Spark) exists in the Mac app. [release notes 2026.06.30](https://gemini.google/release-notes/) |
| `enable_cowork_skills` | **NOT FOUND** | "Cowork" never appears in any public Google source. The nearest concepts are **Skills** and **Antigravity**. |
| `enable_client_side_skills` | **CONFIRMED (in spirit)** | Skills are created/stored client-side in the app: uploaded `SKILL.md` files, folders, .zip download, 100 MB limit, "upload files to create a skill" available only in the **Gemini app on Mac** and the web app. [source](https://support.google.com/gemini/answer/18560919) |
| `enable_mcp_tools` | **CONFIRMED** | MCP server tools are a first-class feature ("third-party services such as Model Context Protocol server tools"). [Privacy Hub](https://support.google.com/gemini/answer/13594961) |
| `enable_custom_mcp_apps` | **CONFIRMED** | "Add a custom app" = MCP server URL. [source](https://support.google.com/gemini/answer/17209137) |
| `enable_custom_mcps_on_gemini_chat` | **CONFIRMED** | "you can use the custom app in your chats for quick actions **or task threads**". [source](https://support.google.com/gemini/answer/13695044) |
| `enable_mcp_tool_ui_frame` | **INFERRED** | UI frame for MCP tool calls is implied by "supported and unsupported actions" lists + per-app details pages + "tool UI" behaviour, but no public screenshot/doc of a dedicated MCP tool UI frame. |
| `enable_git_bundled_mcp_tools` | **NOT FOUND** | No bundled Git MCP server documented. (GitHub *is* a supported source for Workspace in some tiers — "Connect to GitHub & upload code folders" — but that is a Google Workspace feature, not a bundled MCP server.) [admin table](https://support.google.com/a/answer/14571493) |
| `enable_obsidian_bundled_mcp_tools` | **NOT FOUND** | No mention of Obsidian anywhere in Google's public Gemini material. |
| `enable_messages_bundled_mcp_tools` | **NOT FOUND** | Apple Messages is only referenced as a *Connected App* that Gemini **cannot** use: "For now, Gemini can't use Connected Apps in Gemini in Google Messages." [source](https://support.google.com/gemini/answer/13695044) |
| `enable_blender_bundled_mcp_tools` | **NOT FOUND** | No mention of Blender in any Google Gemini source. |
| `enable_remote_control` | **CONFIRMED** | "Control the Gemini app on Mac remotely" — Task → Add Computer. [source](https://support.google.com/gemini/answer/17208717) |
| `enable_async_mode` | **INFERRED / CONFIRMED-in-effect** | Tasks run in the background ("24/7", background jobs, up to 15 concurrent). No public use of the word "async mode". |
| `enable_dynamo` | **NOT FOUND** | "Dynamo" never appears publicly in Gemini context. (Google's "Dynamo" is an unrelated KV database.) |
| `enable_remy_chat_convergence` | **NOT FOUND** | "Remy" never appears publicly in Gemini context. |
| `enable_remy_steering` | **NOT FOUND** | Same — no public trace. |
| `enable_remy_elicitation_*` | **NOT FOUND** | MCP **elicitation** is a standard MCP spec feature, and Google documents MCP server support generally, but "elicitation" is never named in Google's Gemini docs. |
| `disable_network_access_confirmation` | **INFERRED** | Google's documented model is the opposite default: manual confirmation for MCP **write** actions, per-task confirmation before Chrome auto-browsing, approval per agent action. A flag *disabling* network confirmation is plausible as an internal toggle but has no public counterpart. |
| `bundled_mcp_bypass_confirmation` | **NOT FOUND / contradicted** | Public docs explicitly say manual confirmation IS required for MCP write actions, and bundled MCP servers are not documented at all. |
| `SkillsManagerViewModelImpl` | **CONFIRMED** | Sidebar → Customize → **Skills** page with Create/Activate/Deactivate/Download/Delete per skill. [source](https://support.google.com/gemini/answer/17094296) |
| `CreateSkillViewModelImpl` | **CONFIRMED** | Three creation paths: *Create with Gemini*, prefilled template, *Create manually* (name / description / instructions). [source](https://support.google.com/gemini/answer/17094296) |
| `UploadSkillViewModelImpl` | **CONFIRMED** | *Create → Upload*: a `SKILL.md` file, or a folder/`.zip` containing `SKILL.md` in the main folder; name must equal folder name; supported types .txt .md .rst .rtf .tex .log .py .sh .json .yaml .csv .toml .xml .env .sql .html .css .svg Makefile Dockerfile .pdf .jpg .png. [source](https://support.google.com/gemini/answer/17094296) |
| `CustomMCPViewModel` | **CONFIRMED** | Custom-app management UI: Add custom app, Advanced features (DCR vs manual credentials), Disconnect, Remove app, unlink from Google Account "Linked apps". [source](https://support.google.com/gemini/answer/17209137) |
| `RemoteControlLauncher` | **CONFIRMED** | "Add Computer" flow on the remote device. [source](https://support.google.com/gemini/answer/17208717) |
| `EvalAgentModeLauncher` | **NOT FOUND** | No public trace; clearly an internal evaluation entry point. |
| `OmahaDirectInstaller` | **INFERRED** | Omaha is Google's long-standing updater service name; the Gemini apps have a built-in updater ("Check for Updates" / "Install update" / "Restart to update"). [source](https://support.google.com/gemini/answer/17011627) |
| `AppUpdaterServiceImpl` | **CONFIRMED** | Same as above (macOS `Gemini → Check for Updates`; Windows "Restart to update" toast). |
| `VoiceServiceImplementation` | **CONFIRMED** | Mic dictation + Speak to Window + "Use reasoning" setting + tap/hold shortcut types. [source](https://support.google.com/gemini/answer/17011627) |
| `CodeModeWebView` | **INFERRED / NOT CONFIRMED** | The closest confirmed thing is the **remote computer with code execution** used by Task mode, plus "code" as an output file type. No public evidence of a "Code mode" webview surface in the desktop app. Note: **Gemini Code Assist "Code mode"** exists as a separate Google Cloud feature — [docs](https://developers.google.com/gemini-code-assist/docs/agent-mode). |
| `ImageEditorUI` | **CONFIRMED (web)** / INFERRED (desktop) | Nano Banana image editing UI confirmed for Gemini Apps (Library → image → Chat under image → prompt; More → Redo with Pro). Desktop-specific editor not documented. [source](https://support.google.com/gemini/answer/14286560) |
| `MediaGenTemplates*` | **CONFIRMED** | Desktop Create menu = "Create image / Create video / Create music / More tools"; Gemini Omni supports "start from scratch, remix your camera roll, or try out a **premade template**". [source](https://gemini.google/desktop/) · [release notes 2026.05.19](https://gemini.google/release-notes/) |
| `GmailCard` | **INFERRED** | Gmail is a first-class connector (summarise threads, draft replies, declutter inbox, unsubscribe). A rich "Gmail card" UI is not documented. [source](https://support.google.com/gemini/answer/17094507) |
| `GmailDraftSyncCoordinator` | **NOT FOUND** | Google does document that Task mode can draft/send Gmail, but no "draft sync" behaviour is described. |
| `TaskListView` | **CONFIRMED** | The **task thread work panel** (Completed / Current / Planned steps + Files read/updated) and the **Scheduled** page grouped Active / Paused / Completed / Suggested. [source](https://support.google.com/gemini/answer/17094507) · [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) |
| `MessageTree` / `ChatMessageTree` | **CONFIRMED (web/app)** | Unified chat history where chats and Task threads are interleaved, filterable All / Ready / Needs attention / In progress; plus `Find & manage your recent chats`. [9to5Google](https://9to5google.com/2026/10/12/gemini-spark-task-redesign/) |
| `ConditionEvaluator` | **CONFIRMED (as a product concept)** | Schedules support **event conditions**: "When my flight is delayed (condition), notify me and propose an update to my itinerary (task)". Plus real-time topic tracking (blogs/news/social/finance/sports/shopping/weather/email) with alert-when-condition-met. [source](https://support.google.com/gemini/answer/17094296) · [MacRumors 2026‑07‑01](https://www.macrumors.com/2026/07/01/google-gemini-spark-comes-to-mac/) |
| `AreaScreenshotService` | **INFERRED** | "Share window" is confirmed; a *region/area* screenshot service is implied by "share your screen" + lasso-style selection but never documented. |
| `ScreenContextCoordinator` | **CONFIRMED (as a product concept)** | "Gemini infers whether you want to add text to the active window or take action"; "with screen context" reasoning mode for Speak to Window. [source](https://support.google.com/gemini/answer/17011627) · [release notes 2026.07.29](https://gemini.google/release-notes/) |
| `VirtualDisplayManager` | **NOT FOUND** | No public mention of a virtual display / headless display. (macOS 15's "virtual display" is plausible but unconfirmed.) |
| `PreservedChromeMonitor` | **INFERRED** | Chrome **auto browse** (drives the *local* Chrome, with per-task confirmation, plus "Stop" from the Gemini-in-Chrome side panel) is confirmed; a "preserved Chrome" monitor is not named publicly. [source](https://support.google.com/gemini/answer/17094507) |
| `LocalHotKeyHandler` | **CONFIRMED** | Global hotkeys (Option+Space / Option+Shift+Space / Alt+Space) with customisation in Settings. [source](https://gemini.google/desktop/) |
| `STCEscapeHotKey` | **INFERRED** | "To stop a Speak to Window session, tap the **ESC** key or click Close." → an ESC hotkey exists, but the "STC" prefix is unconfirmed. [source](https://support.google.com/gemini/answer/17011627) |
| `ScreenshotLasso*` | **NOT FOUND** | No public evidence of a lasso selection tool. |
| `BrowserViewModel` | **CONFIRMED** | Two browser surfaces: (1) local Chrome auto browse on desktop; (2) a **remote cloud browser** with `View live`, `Take over task`, `Go back to Gemini`. [source](https://support.google.com/gemini/answer/17094507) |
| `AI`/`Model` picker | **CONFIRMED** | Model dropdown: **Fast**, **Thinking**, **Pro**, plus **Deep Think** in the prompt bar; latest frontier model = **Gemini 4 Argon** (Pro/Ultra). Thinking level is changeable from the model menu at the top of a task thread. [release notes](https://gemini.google/release-notes/) · [source](https://support.google.com/gemini/answer/17094507) |

---

## 7. Sign-in flow — the most detail obtainable from public sources

**No public source documents the native Gemini desktop app's OAuth endpoints, client ID,
scopes, or callback mechanism.** Google's own docs only say "Sign in with your Google
Account if prompted." ([Mac](https://support.google.com/gemini/answer/17011627),
[Windows](https://support.google.com/gemini/answer/18263854))

Nearest public evidence, by decreasing directness:

1. **Google Antigravity** — the agentic IDE that the Gemini macOS app launches — uses a
   **loopback HTTP callback**. A user bug report shows the login request carrying
   `redirect_uri=http://localhost:[PORT]/oauth-callback` and the browser landing on
   `https://antigravity.google/auth-success?app=antigravity` instead of the callback.
   Forum volunteers note Antigravity and **Gemini CLI share the same OAuth system**.
   [thread](https://discuss.ai.google.dev/t/bug-macos-oauth-redirect-stuck-at-auth-success-page-localhost-redirect-not-working/131624)
2. **Gemini CLI (Google-official open-source client) — the most reproducible OAuth
   client publicly documented**, and the strongest precedent for a Linux client:
   - `client_id`: `<redacted-google-oauth-client-id>`
   - `client_secret`: `<redacted-google-oauth-client-secret>` (installed-app type; secret not
     treated as secret per Google's OAuth docs)
   - `scope`: `https://www.googleapis.com/auth/cloud-platform`,
     `https://www.googleapis.com/auth/userinfo.email`,
     `https://www.googleapis.com/auth/userinfo.profile`
   - Flow: local HTTP server captures the callback → token exchange → refresh token cached
     locally. Success/failure landing pages: `https://developers.google.com/gemini-code-assist/auth_success_gemini`
     / `auth_failure_gemini`.
   [source: packages/core/src/code_assist/oauth2.ts](https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/code_assist/oauth2.ts) ·
    [auth guide](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/authentication.mdx)
3. **The gemini.google.com web app** (which the desktop app mirrors) signs in through
   `accounts.google.com` in a browser session; sessions/cookies persist locally.
   An open-source Electron wrapper of gemini.google.com implements exactly that:
   OAuth handled in a separate `BrowserWindow` that loads `https://accounts.google.com`,
   `accounts.youtube.com` treated as OAuth domains, auth window auto-closes when
   navigation returns to `gemini.google.com`, and Gemini traffic goes to
   `https://gemini.google.com/u/0/_/BardChatUi/data/StreamGenerate` (plus `log` and
   `batchexecute` RPC endpoints).
   [constants.ts](https://raw.githubusercontent.com/bwendell/gemini-desktop/main/src/main/utils/constants.ts) ·
    [authWindow.ts](https://raw.githubusercontent.com/bwendell/gemini-desktop/main/src/main/windows/authWindow.ts) ·
    [repo](https://github.com/bwendell/gemini-desktop)
4. **Access control after sign-in** (documented, product-level): Tasks in Gemini and
   custom MCP apps require a **personal** Google Account, 18+, US (for custom apps),
   Keep Activity ON, Personal Intelligence opted in; work/school accounts are excluded.

---

## 8. Explicitly NOT confirmed / open questions

1. OAuth endpoints, client id, scopes, and callback style **for the native Gemini desktop app**.
2. Multi-account support / account switching in the desktop app.
3. The signed-out / pre-auth UI of the desktop app.
4. A `gemini://` URL scheme, deep links, "Open with" file associations, or Quick Look integration.
5. Drag-and-drop of files into the app window.
6. Bundled MCP servers for Git / Obsidian / Apple Messages / Blender.
7. Any public trace of "Cowork", "Dynamo", "Remy", "elicitation", "async mode", "Code mode webview", "virtual display", or "screenshot lasso" in Gemini.
8. A full macOS menu-bar inventory (only `Gemini → Settings` and `Gemini → Check for Updates` are documented).
9. Whether Task mode / Spark ever reaches the **Windows** app (Google currently lists it as unsupported).
10. Desktop-specific "Gmail card" / "draft sync" UI.
11. A native Linux build — none exists; the official apps are macOS (Apple Silicon, macOS 15+) and Windows (x64/ARM64) only.
12. Whether "Dive" was ever a Google Gemini feature name (it was not found anywhere; the real names are Deep Research / Deep Think).

## 9. Source index

- Gemini for desktop marketing page — https://gemini.google/desktop/ (also https://gemini.google/us/desktop/?hl=en)
- Gemini Apps release notes — https://gemini.google/release-notes/
- Use the Gemini app on Mac — https://support.google.com/gemini/answer/17011627
- Use the Gemini app for Windows — https://support.google.com/gemini/answer/18263854
- Assign tasks in the Gemini app on Mac — https://support.google.com/gemini/answer/17208717
- Manage your tasks & workflows in Gemini Apps — https://support.google.com/gemini/answer/17094507
- Create & manage skills for Gemini Apps — https://support.google.com/gemini/answer/17094296
- Connect & manage custom apps (MCP) — https://support.google.com/gemini/answer/17209137
- Use & manage Connected Apps in Gemini — https://support.google.com/gemini/answer/13695044
- Schedules in Gemini Apps — https://support.google.com/gemini/answer/16316416
- About the transition from Gems to skills — https://support.google.com/gemini/answer/18560919
- Use Deep Research in Gemini Apps — https://support.google.com/gemini/answer/15719111
- Generate & edit images with Gemini Apps — https://support.google.com/gemini/answer/14286560
- What you need to sign in to Gemini Apps — https://support.google.com/gemini/answer/13278668
- Gemini Apps Privacy Hub — https://support.google.com/gemini/answer/13594961
- Turn the Gemini App on or off (Admin) — https://support.google.com/a/answer/14571493
- Workspace blog: Mac launch — https://workspaceupdates.googleblog.com/2026/04/now-available-gemini-app-for-mac.html
- Workspace blog: Windows launch — https://workspaceupdates.googleblog.com/2026/09/the-gemini-desktop-app-is-now-available-for-Windows.html
- Workspace blog: skills + Gems transition — https://workspaceupdates.googleblog.com/2026/09/skills-gemini-app-workspace.html
- 9to5Google: Spark on macOS — https://9to5google.com/2026/06/30/gemini-spark-mac-app/
- 9to5Google: Spark→Task redesign — https://9to5google.com/2026/10/12/gemini-spark-task-redesign/
- 9to5Mac: Mac launch — https://9to5mac.com/2026/04/15/google-launches-gemini-mac-app-heres-what-it-offers/
- MacRumors: Spark on Mac — https://www.macrumors.com/2026/07/01/google-gemini-spark-comes-to-mac/
- ZDNET/Yahoo: Mac app hands-on — https://tech.yahoo.com/ai/gemini/articles/tried-gemini-app-mac-better-211828596.html
- AndroidPure: Task mode — https://www.androidpure.com/gemini-spark-task-mode/
- layer3labs: Spark→Task — https://www.layer3labs.io/guides/what-happened-to-gemini-spark ; how-to — https://www.layer3labs.io/guides/how-to-use-gemini-spark
- Gemini CLI oauth2.ts — https://raw.githubusercontent.com/google-gemini/gemini-cli/main/packages/core/src/code_assist/oauth2.ts
- Antigravity OAuth loopback bug — https://discuss.ai.google.dev/t/bug-macos-oauth-redirect-stuck-at-auth-success-page-localhost-redirect-not-working/131624
- bwendell/gemini-desktop (unofficial Electron wrapper; endpoint + auth-domain evidence) — https://github.com/bwendell/gemini-desktop
- Third-party IT KB (low confidence) — https://tcnj.teamdynamix.com/TDClient/1798/Portal/KB/Article/173156/Installing-and-Using-the-Google-Gemini-Desktop-App
