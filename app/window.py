"""Main window: navigation rail, top bar, page switching, agent wiring.

The shell is a navigation rail with the agent's primary surfaces, a history
list that marks what needs attention, and the account at the foot, rendered in
the design language measured for it (docs/DESIGN.md). The arrangement began as
a study of the Gemini desktop app; the design is @UiRahMan92's.
"""
from __future__ import annotations

import os
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from app import account as account_mod
from app import approval as approval_mod
from app import chat_view, composer, engine as engine_mod
from app import permissions
from app import palette as palette_mod
from app import session as session_mod
from app import sidebar as sidebar_mod
from app import theme, topbar as topbar_mod
from app.store import Store

#: The surfaces in the rail, in the order the desktop app uses.
#: (name, rail label, icon, capability the engine must provide)
PAGES = (
    ("today", "Today", "light_mode", engine_mod.CHAT),
    ("chat", "Chat", "chat", engine_mod.CHAT),
    ("tasks", "Tasks", "checklist", engine_mod.CHAT),
    ("create", "Create", "add_image_spark", engine_mod.IMAGES),
    ("schedule", "Schedule", "schedule", engine_mod.CHAT),
    ("memory", "Memory", "lightbulb", engine_mod.CHAT),
    ("plugins", "Plugins", "tune", engine_mod.CHAT),
    ("connectors", "Connectors", "extension", engine_mod.CONNECTORS),
    ("skills", "Skills", "notes_spark", engine_mod.SKILLS),
)

EFFORTS = ("low", "medium", "high", "xhigh", "max")


def pages_for(engine) -> list[tuple]:
    """The surfaces this engine can back, in rail order."""
    return [page for page in PAGES if engine.supports(page[3])]


class Window(Adw.ApplicationWindow):
    """The main window: rail, top bar, page stack and the agent's surfaces."""

    #: Stand-in identity for `--demo`, so screenshots and UI checks never show
    #: a real account.
    DEMO_NAME = "Alex Rivera"
    def __init__(self, application, engine: engine_mod.Engine, store: Store,
                 workspace: str = "", page: str = "home", scheme: str = "light",
                 size: tuple[int, int] = (1440, 940), animate: bool = True,
                 demo: bool = False):
        super().__init__(application=application)
        self.demo = demo
        self.engine = engine
        self.store = store
        self.workspace = workspace or os.path.expanduser("~")
        if demo:
            # neutral paths, and a throwaway engine home, so screenshots never
            # expose a real account, folder or permission file
            self.workspace = "/home/alex/projects"
            os.environ.setdefault("GEMINI_HOME_DIR", "/home/alex/.gemini")
            # demo data must never touch the real store, schedules or memory
            import tempfile as _tempfile  # noqa: PLC0415

            os.environ.setdefault(
                "XDG_DATA_HOME",
                _tempfile.mkdtemp(prefix="mantel-demo-data-"))
        self.conversation = None
        self.turn = None
        self.session = session_mod.Session(engine)
        self.approval = "ask"
        self.effort = "medium"
        self._page_name = page
        if demo:
            self._account = account_mod.Account(email=self.DEMO_MAIL,
                                                has_refresh_token=True)
        else:
            self._account = account_mod.load_account()

        # A surface exists only if the selected engine can back it. This is the
        # promise of the adapter seam: switching engines changes what the app
        # offers, not just who answers.
        self._pages_for_engine = pages_for(engine)

        self.set_default_size(*size)
        self.set_title("Mantel")

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.add_css_class("root")
        self.root = root

        self.sidebar = sidebar_mod.Sidebar(
            on_navigate=self._navigate,
            on_task=self._task,
            on_open=self.open_chat,
            on_collapse=self._toggle_sidebar,
            on_theme=self._set_theme,
            on_account=self._show_account,
            user_name=self._account.display_name,
            user_mail=self._account.email or "Not signed in",
            avatar_initials=self._account.initials,
            nav_items=[("explore", "Goals", "")] + [
                (icon, label, "") for _n, label, icon, _c in self._pages_for_engine],
        )
        self._sidebar_revealer = Gtk.Revealer()
        self._sidebar_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_RIGHT
            if animate else Gtk.RevealerTransitionType.NONE)
        self._sidebar_revealer.set_child(self.sidebar)
        self._sidebar_revealer.set_reveal_child(True)
        self._sidebar_revealer.set_vexpand(True)
        root.append(self._sidebar_revealer)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_hexpand(True)

        self.topbar = topbar_mod.TopBar(
            title="Overview",
            on_back=self._go_back,
            on_new=self.new_chat,
            on_filter=self._show_options,
        )
        content.append(self.topbar)

        self._pages = Gtk.Stack()
        self._pages.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._pages.set_hexpand(True)
        self._pages.set_vexpand(True)

        self.chat = chat_view.ChatView()
        self._pages.add_named(self.chat, "chat")

        self.home = self._build_home()
        if self.home is not None:
            self._pages.add_named(self._scrolled(self.home), "home")

        self._build_extra_pages()
        content.append(self._pages)

        # --- the work panel, the approvals and the composer ----------------
        self._work = chat_view.WorkPanel()
        self._work.set_visible(False)

        self._changes = chat_view.ChangesPanel(on_open=self._show_diff)
        self._changes.set_visible(False)

        self._approvals = approval_mod.ApprovalStack(self._on_approval)
        self._approvals.set_visible(False)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bottom.set_halign(Gtk.Align.CENTER)
        bottom.set_margin_start(36)
        bottom.set_margin_end(36)
        bottom.set_margin_bottom(24)

        self.composer = composer.Composer(
            on_submit=self.submit,
            on_stop=self.stop,
            on_steer=self.steer,
            on_pick_workspace=self.pick_workspace,
            on_pick_model=self._show_models,
            on_pick_approval=self._show_approvals,
            on_pick_effort=self._show_efforts,
            on_toggle_mode=self._set_mode,
        )
        self.composer.set_model(self._current_model_label())
        self.composer.set_workspace(self.workspace)
        self.composer.set_approval(self.approval)
        self.composer.set_effort(self.effort)
        self.composer.tools_btn.connect("clicked", lambda _b: self._show_add_menu())

        bottom.append(self._work)
        bottom.append(self._changes)
        bottom.append(self._approvals)
        bottom.append(self.composer)
        content.append(bottom)

        self._overlay = Gtk.Overlay()
        self._overlay.set_child(content)
        self._overlay.set_hexpand(True)
        self._overlay.set_vexpand(True)
        root.append(self._overlay)
        self.set_content(root)

        # --- command palette ----------------------------------------------
        self.palette = palette_mod.Palette(
            on_run=self._run_palette_action,
            on_close=self._close_palette,
            pages=[page[0] for page in self._pages_for_engine],
            extras_provider=self._plugin_palette_actions)
        self.palette.set_visible(True)
        self._overlay.add_overlay(self.palette)
        self._install_palette_shortcut()

        from app.reminders import ReminderRunner  # noqa: PLC0415
        from app.scheduler import Scheduler  # noqa: PLC0415

        self.reminders = ReminderRunner()
        self.reminders.connect("due", self._on_reminder)
        self.reminders.start()

        self.scheduler = Scheduler(engine)
        self.scheduler.connect("ran", self._on_schedule_ran)
        self.scheduler.connect("failed", self._on_schedule_failed)
        self.scheduler.start()

        self._install_actions()
        self._set_theme(scheme)
        self.conversation = self.store.new(cwd=self.workspace)
        self.chat.show_welcome(self._use_suggestion)
        self._go(page)
        self._refresh_sidebar()
        self._refresh_home()

    # -- pages --------------------------------------------------------------
    def _build_home(self):
        try:
            from app.home import HomePage  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - the dashboard is optional
            return None
        return HomePage(
            on_new_chat=self.new_chat,
            on_open_chat=self.open_chat,
            on_select_model=self._show_models,
        )

    def _build_extra_pages(self) -> None:
        """The pages the worker modules provide, if they are present."""
        # Connectors and Skills edit the *engine's* stores, so they only exist
        # for an engine that has them.
        self.connectors = None
        if self.engine.supports(engine_mod.CONNECTORS):
            try:
                from app.pages.connectors import ConnectorsPage  # noqa: PLC0415
                self.connectors = ConnectorsPage(
                    on_changed=self._refresh_sidebar)
                self._pages.add_named(
                    self._own_scroller(self.connectors), "connectors")
            except Exception:  # noqa: BLE001
                self.connectors = None
        self.skills = None
        if self.engine.supports(engine_mod.SKILLS):
            try:
                from app.pages.skills import SkillsPage  # noqa: PL151
                self.skills = SkillsPage(on_changed=self._refresh_sidebar)
                self._pages.add_named(self._own_scroller(self.skills), "skills")
            except Exception:  # noqa: BLE001
                self.skills = None
        try:
            from app.pages.today import TodayPage  # noqa: PLC0415
            self.today_page = TodayPage(
                on_toggle_task=lambda _id: self._refresh_today(),
                on_add_task=self._add_task_from_today,
                on_open_tasks=lambda: self._go("tasks"),
                on_open_chat=self.new_chat,
                on_focus_done=self._on_focus_done,
                on_open_settings=lambda: self._go("settings"),
                engine_name=self.engine.name,
                model_label=self._current_model_label())
            self._pages.add_named(self._own_scroller(self.today_page), "today")
        except Exception:  # noqa: BLE001
            self.today_page = None
        try:
            from app.pages.plugins import PluginsPage  # noqa: PLC0415
            self.plugins_page = PluginsPage(on_changed=self._refresh_plugins)
            self._pages.add_named(self._own_scroller(self.plugins_page),
                                  "plugins")
        except Exception:  # noqa: BLE001
            self.plugins_page = None
        try:
            from app.pages.memory import MemoryPage  # noqa: PLC0415
            self.memory = MemoryPage(
                on_changed=self._refresh_memory,
                on_add=lambda _text: self._refresh_memory())
            self._pages.add_named(self._own_scroller(self.memory), "memory")
        except Exception:  # noqa: BLE001
            self.memory = None
        try:
            from app.pages.create import CreatePage  # noqa: PLC0415
            self.create = CreatePage(on_generate=self._generate_image)
            self._pages.add_named(self._own_scroller(self.create), "create")
        except Exception:  # noqa: BLE001
            self.create = None
        try:
            from app.pages.tasks import TasksPage  # noqa: PLC0415
            self.tasks = TasksPage(on_changed=self._refresh_tasks)
            self._pages.add_named(self._own_scroller(self.tasks), "tasks")
        except Exception:  # noqa: BLE001
            self.tasks = None
        try:
            from app.pages.schedule import SchedulePage  # noqa: PLC0415
            self.schedule = SchedulePage(
                on_run_now=self._run_schedule,
                on_changed=self._refresh_schedules,
                workspace=self.workspace)
            self._pages.add_named(self._own_scroller(self.schedule), "schedule")
        except Exception:  # noqa: BLE001
            self.schedule = None
        try:
            from app.pages.settings import SettingsPage  # noqa: PLC0415
            self.settings = SettingsPage(
                on_theme=self._set_theme,
                on_approval=self.set_approval,
                on_effort=self.set_effort,
                on_workspace=self.pick_workspace,
                on_shortcuts=self._show_shortcuts,
                on_about=self._show_about,
                on_calendar=self._refresh_today,
                scheme="light",
                approval=self.approval,
                effort=self.effort,
                workspace=self.workspace,
                models=self.engine.models(),
                capabilities=self.engine.capabilities,
                engine_name=self.engine.name,
            )
            self._pages.add_named(self._own_scroller(self.settings), "settings")
        except Exception:  # noqa: BLE001
            self.settings = None
        self.account_page = None
        if self.engine.supports(engine_mod.ACCOUNT):
            try:
                from app.pages.account import AccountPage  # noqa: PLC0415
                self.account_page = AccountPage(
                    on_signed_in=self._on_signed_in,
                    on_signed_out=self._on_signed_out)
                self._pages.add_named(
                    self._own_scroller(self.account_page), "account")
            except Exception:  # noqa: BLE001
                self.account_page = None

    @staticmethod
    def _own_scroller(page: Gtk.Widget) -> Gtk.Widget:
        """Use the page's own scroller when it has one, to avoid nesting two."""
        child = page.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ScrolledWindow):
                return page
            child = child.get_next_sibling()
        return Window._scrolled(page)

    @staticmethod
    def _scrolled(page: Gtk.Widget) -> Gtk.ScrolledWindow:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(page)
        return scroll

    def _go(self, page: str) -> None:
        if page not in self._page_names():
            page = "home" if self.home is not None else "chat"
        self._page_name = page
        self._pages.set_visible_child_name(page)
        self.topbar.set_title(self._title_for(page))
        self.sidebar.set_active(self._sidebar_label(page))

    def _page_names(self) -> set[str]:
        """Every page actually present in the stack."""
        wanted = ({"chat", "home", "settings"}
                  | {name for name, _l, _i, _c in self._pages_for_engine}
                  | {"account"} if self.engine.supports(engine_mod.ACCOUNT)
                  else {"chat", "home", "settings"}
                  | {name for name, _l, _i, _c in self._pages_for_engine})
        return {name for name in wanted
                if self._pages.get_child_by_name(name) is not None}

    def _title_for(self, page: str) -> str:
        for name, label, _icon, _cap in self._pages_for_engine:
            if name == page:
                return label
        return {"home": "Overview", "account": "Account"}.get(page, "Overview")

    def _sidebar_label(self, page: str) -> str:
        if page == "home":
            return "Goals"
        for name, label, _icon, _cap in self._pages_for_engine:
            if name == page:
                return label
        return ""          # the account page has no rail entry

    def _navigate(self, label: str) -> None:
        if label == "Help Center":
            self._show_shortcuts()
            return
        mapping = {"Chat": "chat", "Tasks": "tasks", "Create": "create",
                   "Schedule": "schedule", "Connectors": "connectors",
                   "Skills": "skills", "Goals": "home",
                   "Setting": "settings"}
        self._go(mapping.get(label, "chat"))

    def _go_back(self) -> None:
        self._go("home" if self._page_name == "chat" else "chat")

    def _task(self, text: str) -> None:
        self._go("chat")
        self.composer.view.get_buffer().set_text(text)
        self.composer.view.set_opacity(1.0)
        self.composer.focus()

    def _toggle_sidebar(self) -> None:
        self._sidebar_revealer.set_reveal_child(
            not self._sidebar_revealer.get_reveal_child())

    # -- account ------------------------------------------------------------
    def _refresh_tasks(self) -> None:
        page = getattr(self, "tasks", None)
        if page is not None:
            page.refresh()
        self._refresh_today()

    def _refresh_plugins(self) -> None:
        page = getattr(self, "plugins_page", None)
        if page is not None:
            page.refresh()

    def _plugin_palette_actions(self) -> list:
        """Commands contributed by enabled plugins, for the palette."""
        from app import palette as palette_mod  # noqa: PLC0415
        from app import plugins as plugins_mod  # noqa: PLC0415

        actions = []
        for plugin, command in plugins_mod.commands():
            actions.append(palette_mod.Action(
                "plugin", command["title"],
                f"{plugin.manifest.name} · plugin",
                f"{plugin.manifest.id}|{command['id']}"))
        return actions

    def _run_plugin_command(self, payload: str) -> None:
        from app import plugins as plugins_mod  # noqa: PLC0415

        plugin_id, _, command_id = payload.partition("|")
        plugin = plugins_mod.find(plugin_id)
        if plugin is None:
            return
        ok, result = plugins_mod.run_command(plugin, command_id, {
            "date": __import__("time").strftime("%A %d %B"),
        })
        if not ok:
            self._notify(f"{plugin.manifest.name} failed", str(result)[:160])
            return
        message = result.get("message") if isinstance(result, dict) else result
        self._notify(plugin.manifest.name, str(message or "Done.")[:160])
        self._refresh_plugins()

    def _refresh_today(self) -> None:
        page = getattr(self, "today_page", None)
        if page is not None:
            page.refresh()

    def _add_task_from_today(self, text: str) -> None:
        from app import todos  # noqa: PLC0415

        if todos.add(text) is not None:
            self._refresh_tasks()
            self._refresh_sidebar()

    def _on_focus_done(self, *_args) -> None:
        """A focus session ended: say so once, without stealing focus."""
        self._notify("Focus session complete",
                     "Time for a break — or start another.")

    def _refresh_memory(self) -> None:
        page = getattr(self, "memory", None)
        if page is not None:
            page.refresh()
        self._refresh_today()

    def _refresh_settings(self) -> None:
        """Rebuild the Settings page after a change made on it."""
        page = getattr(self, "settings", None)
        if page is None:
            return
        from app.pages.settings import SettingsPage  # noqa: PLC0415

        wrapper = page.get_parent()
        holder = wrapper.get_parent() if wrapper is not None else None
        if holder is None:
            self._go("settings")
            return
        self.settings = SettingsPage(
            on_theme=self._set_theme,
            on_approval=self.set_approval,
            on_effort=self.set_effort,
            on_workspace=self.pick_workspace,
            on_shortcuts=self._show_shortcuts,
            on_about=self._show_about,
            on_calendar=self._refresh_today,
            scheme="light",
            approval=self.approval,
            effort=self.effort,
            workspace=self.workspace,
            models=self.engine.models(),
            capabilities=self.engine.capabilities,
            engine_name=self.engine.name,
        )
        holder.remove(wrapper)
        self._pages.add_named(self._own_scroller(self.settings), "settings")
        self._go("settings")


    # -- demo ---------------------------------------------------------------
    DEMO_NAME = "Alex Rivera"
    DEMO_MAIL = "alex.rivera@example.com"
    DEMO_INITIALS = "AR"

    DEMO_TRANSCRIPT = """Here is what I found in the workspace.

## Summary

The service has three entry points, and only one of them validates its input.
That is where I would start.

- `serve()` starts the HTTP listener and never checks the body
- `handle()` dispatches on the route table
- `validate()` is only called on the upload path

```python
def serve(port: int) -> None:
    app = make_app()
    app.run(host="127.0.0.1", port=port)
```

I also added a regression test for the missing check.
"""

    def load_demo(self) -> None:
        """Fill the window with sample content for screenshots and UI checks.

        Nothing here touches the engine or the disk: the point is to show the
        interface without signing in, so reviewers can see it too.
        """
        import tempfile as _tempfile  # noqa: PLC0415
        import time as _time  # noqa: PLC0415
        from pathlib import Path as _Path  # noqa: PLC0415

        from app import session as session_mod  # noqa: PLC0415
        from app.store import Conversation, Store  # noqa: PLC0415

        # demo data lives in a throwaway store: it must never mix with real
        # conversations, and repeated runs must not accumulate
        self.store = Store(root=_Path(_tempfile.mkdtemp(prefix="gemini-demo-")))
        shown_page = self._pages.get_visible_child_name()

        self.sidebar.set_account(self.DEMO_NAME, self.DEMO_MAIL,
                                 self.DEMO_INITIALS)
        self._account = account_mod.Account(
            email=self.DEMO_MAIL, has_refresh_token=True)

        now = _time.time()
        titles = [
            ("Audit the upload path", "Validated the upload handler and added a "
                                      "regression test."),
            ("Summarise this repo", "Walked the tree and mapped the entry "
                                    "points."),
            ("Draft release notes", "Turned the last two weeks of commits into "
                                    "customer-facing notes."),
            ("Compare model costs", "Charted token spend per model."),
        ]
        for index, (title, body) in enumerate(titles):
            conv = Conversation()
            conv.title = title
            conv.updated = now - index * 5400
            conv.add("user", title)
            conv.add("assistant", body)
            conv.engine_id = f"demo-{index}"
            self.store.save(conv)
        self._refresh_sidebar()

        self.chat.reset()
        self.chat.add_user("Find the input-validation gaps in this service.")
        message = self.chat.begin_assistant(model="Gemini 3.8 Flash (High)")
        message.set_text(self.DEMO_TRANSCRIPT)
        message.finish(duration=12.4, usage={"total_tokens": 2185})

        try:
            from pathlib import Path as _P  # noqa: PLC0415

            from app import plugins as plugins_mod  # noqa: PLC0415

            reference = (_P(__file__).resolve().parent.parent
                         / "plugins" / "day-summary")
            if reference.is_dir():
                plugins_mod.install(reference)
            page = getattr(self, "plugins_page", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            import datetime as _dt  # noqa: PLC0415

            from app import calendar as calendar_mod  # noqa: PLC0415

            today = _dt.date.today()
            def stamp(hour: int) -> str:
                return _dt.datetime.combine(
                    today, _dt.time(hour=hour)).strftime("%Y%m%dT%H%M%S")

            ics = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:design-review@demo
SUMMARY:Design review
DTSTART:{stamp(11)}
DTEND:{stamp(12)}
LOCATION:Room 2
END:VEVENT
BEGIN:VEVENT
UID:focus-hour@demo
SUMMARY:Focus hour
DTSTART:{stamp(15)}
DTEND:{stamp(16)}
END:VEVENT
BEGIN:VEVENT
UID:release@demo
SUMMARY:Release day
DTSTART;VALUE=DATE:{today.strftime('%Y%m%d')}
END:VEVENT
END:VCALENDAR
"""
            demo_ics = _Path(_tempfile.mkdtemp(prefix="mantel-demo-ics-")) / "day.ics"
            demo_ics.write_text(ics)
            calendar_mod.add_source(str(demo_ics))
            page = getattr(self, "today_page", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            from app import todos as todos_mod  # noqa: PLC0415

            for title in ("Pay the invoice today",
                          "Review the Pi adapter notes tomorrow",
                          "Draft the weekly note on Monday",
                          "Someday: read the durable harness docs"):
                todos_mod.add(title)
            done = todos_mod.add("Send the status update", due=0)
            if done is not None:
                todos_mod.complete(done.id)
            page = getattr(self, "tasks", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            from app import memory as memory_mod  # noqa: PLC0415

            for text, kind in (
                ("Prefers deep work before noon", "preference"),
                ("Works on Mantel, a native Linux client", "project"),
                ("Uses Neovim and a monospace everything", "preference"),
                ("Said they would review the PR by Friday", "commitment"),
            ):
                memory_mod.remember(text, kind=kind, source="you")
            page = getattr(self, "memory", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        self.session.record_tool("read_file", {"Path": "src/server.py"},
                                 "DONE", output="142 lines")
        self.session.record_tool("run_command", {"CommandLine": "pytest -q"},
                                 "DONE", output="42 passed")
        self._update_work()
        self._update_changes()

        self._refresh_tasks()
        self._refresh_memory()
        self._refresh_today()
        self.session.mode = session_mod.MODE_TASK
        if shown_page:
            self._go(shown_page)

    def _show_account(self) -> None:
        if self.account_page is not None:
            self._go("account")
            self.account_page.refresh()
        else:
            self._show_options()

    def _on_signed_in(self, acc) -> None:
        self._account = acc
        self.sidebar.set_account(acc.display_name, acc.email or "Not signed in",
                                 acc.initials)
        self._refresh_sidebar()

    def _on_signed_out(self) -> None:
        self._account = account_mod.load_account()

        # A surface exists only if the selected engine can back it. This is the
        # promise of the adapter seam: switching engines changes what the app
        # offers, not just who answers.
        self._pages_for_engine = pages_for(engine)
        self.sidebar.set_account("Mantel", "Not signed in", "?")
        self._refresh_sidebar()

    # -- theme --------------------------------------------------------------
    def _set_theme(self, key: str) -> None:
        sidebar = getattr(self, "sidebar", None)
        if sidebar is not None:
            sidebar.set_theme(key, notify=False)
        if key == "system":
            theme.set_scheme("dark" if self._system_is_dark() else "light")
        else:
            theme.set_scheme(key)
        if getattr(self, "composer", None) is not None:
            self.composer.queue_draw()
        if getattr(self, "home", None) is not None:
            self.home.queue_draw()

    @staticmethod
    def _system_is_dark() -> bool:
        try:
            import gi as _gi  # noqa: PLC0415

            _gi.require_version("Adw", "1")
            from gi.repository import Adw  # noqa: PLC0415

            return (Adw.StyleManager.get_default().get_color_scheme()
                    == Adw.ColorScheme.PREFER_DARK)
        except Exception:  # noqa: BLE001
            return False

    # -- models, effort, approval ------------------------------------------
    def _current_model_label(self) -> str:
        model = (self.conversation.model if self.conversation else "") or ""
        for mid, label in self.engine.models():
            if mid == model:
                return label
        models = self.engine.models()
        return models[0][1] if models else "model"

    def _show_models(self) -> None:
        self._menu(
            [(label, (lambda m=mid: self.set_model(m, label)))
             for mid, label in self.engine.models()],
            "Choose a model", self.composer.model_btn)

    def _show_efforts(self) -> None:
        self._menu(
            [(level.title(), (lambda e=level: self.set_effort(e)))
             for level in EFFORTS],
            "Reasoning effort", self.composer.effort_btn)

    def _show_approvals(self) -> None:
        self._menu(
            [(mode.label, (lambda k=mode.key: self.set_approval(k)))
             for mode in session_mod.APPROVAL_MODES],
            "What the agent may do without asking",
            self.composer.approval_btn)

    def _show_add_menu(self) -> None:
        """The composer's + menu: files, folders and customisation."""
        self._menu(
            [("Attach files…", self._attach_files),
             ("Take a screenshot", self._attach_screenshot),
             ("Add a folder…", self.pick_workspace),
             ("Connectors", lambda: self._go("connectors")),
             ("Skills", lambda: self._go("skills")),
             ("Schedules", lambda: self._go("schedule")),
             ("Remote control", lambda: self._go("settings"))],
            "Add files and tools", self.composer.tools_btn)

    def _generate_image(self, instruction: str) -> None:
        """Run a creation prompt in Task mode and show the result."""
        self._go("chat")
        self._refresh_tasks()
        self._refresh_memory()
        self._refresh_today()
        self.session.mode = session_mod.MODE_TASK
        if shown_page:
            self._go(shown_page)
        self.session.mode = session_mod.MODE_TASK
        buf = self.composer.view.get_buffer()
        buf.set_text(instruction)
        self.composer.view.set_opacity(1.0)
        self.composer.focus()

    def _attach_screenshot(self) -> None:
        """Capture the screen and attach it to the prompt."""
        from app import screenshot  # noqa: PLC0415

        def work():
            ok, result = screenshot.capture()
            GLib.idle_add(self._screenshot_done, ok, result)
            return False

        import threading  # noqa: PLC0415

        threading.Thread(target=work, daemon=True).start()

    def _screenshot_done(self, ok: bool, result: str) -> bool:
        if not ok:
            self._dialog("Screen capture", result)
            return False
        buf = self.composer.view.get_buffer()
        current = self.composer.text()
        mention = f"[attached screenshot: {result}]"
        buf.set_text((current + "\n" if current else "") + mention + "\n")
        self.composer.view.set_opacity(1.0)
        self.composer.focus()
        return False

    def _attach_files(self) -> None:
        """Pick files and mention them in the prompt, as the desktop app does."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Attach files")
        dialog.set_selection_mode(Gtk.SelectionMode.MULTIPLE)

        def done(dlg, result):
            try:
                files = dlg.open_multiple_finish(result)
            except GLib.Error:
                return
            if files is None:
                return
            names = []
            for index in range(files.get_n_items()):
                item = files.get_item(index)
                if item is not None:
                    path = item.get_path()
                    if path:
                        names.append(path)
            if not names:
                return
            buf = self.composer.view.get_buffer()
            current = self.composer.text()
            mention = "\n".join(f"[attached: {n}]" for n in names)
            buf.set_text((current + "\n" if current else "") + mention + "\n")
            self.composer.view.set_opacity(1.0)
            self.composer.focus()

        dialog.open_multiple(self, None, done)

    def _menu(self, items, title: str, anchor: Gtk.Widget) -> None:
        """A small popover menu anchored to one of the composer's controls."""
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("section-label")
        box.append(heading)
        for label, action in items:
            btn = Gtk.Button(label=label)
            btn.add_css_class("chip-grade")
            btn.connect("clicked", lambda _b, fn=action: (fn(), pop.popdown()))
            box.append(btn)
        pop.set_child(box)
        pop.set_parent(anchor)
        pop.popup()

    def set_model(self, model_id: str, label: str) -> None:
        if self.conversation:
            self.conversation.model = model_id
            self.store.save(self.conversation)
        self.composer.set_model(label)

    def set_effort(self, level: str) -> None:
        self.effort = level
        self.composer.set_effort(level)

    def set_approval(self, key: str) -> None:
        self.approval = key
        self.session.approval = key
        self.composer.set_approval(key)

    def _set_mode(self, mode: str) -> None:
        self.session.mode = mode
        if mode in (session_mod.MODE_TASK, session_mod.MODE_RESEARCH):
            self._go("tasks")
        else:
            self._go("chat")

    # -- workspace ----------------------------------------------------------
    def pick_workspace(self) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title("Choose a working folder")

        def done(dlg, result):
            try:
                folder = dlg.select_folder_finish(result)
            except GLib.Error:
                return
            if folder is None:
                return
            self.workspace = folder.get_path()
            self.composer.set_workspace(self.workspace)
            if self.conversation:
                self.conversation.cwd = self.workspace
                self.store.save(self.conversation)
            self._trust_workspace(self.workspace)

        dialog.select_folder(self, None, done)

    def _trust_workspace(self, folder: str) -> None:
        """Ask whether the agent may work in this folder, and record it."""
        if permissions.is_trusted(folder):
            return
        dialog = Adw.MessageDialog(
            transient_for=self, heading="Allow the agent to work in this folder?",
            body=("The agent will be able to read and change files under "
                  f"{folder}. You can change this later in Settings."))
        dialog.add_response("deny", "Not now")
        dialog.add_response("allow", "Allow")
        dialog.set_response_appearance("allow", Adw.ResponseAppearance.SUGGESTED)

        def on_response(dlg, response):
            if response != "allow":
                return
            permissions.trust_folder(folder)
            permissions.allow_folder(folder)

        dialog.connect("response", on_response)
        dialog.present()

    # -- sending ------------------------------------------------------------
    #: How many turns of history to resend when the engine cannot resume.
    HISTORY_TURNS = 8

    def _history_prefix(self, conv) -> str:
        """A compact transcript, for when the engine lost the conversation.

        The engine keeps the thread itself via ``--conversation``; when it
        cannot (a read-only home, a pruned store) the exchange would lose its
        context, so the recent turns are replayed inline instead.
        """
        turns = [m for m in conv.messages if m.role in ("user", "assistant")
                 and (m.text or "").strip()][-self.HISTORY_TURNS:]
        if not turns:
            return ""
        lines = ["Conversation so far, for context:"]
        for message in turns:
            speaker = "User" if message.role == "user" else "Assistant"
            body = " ".join(message.text.split())
            if len(body) > 600:
                body = body[:600] + "…"
            lines.append(f"{speaker}: {body}")
        lines.append("")
        lines.append("Now answer the next message, using the context above.")
        lines.append("")
        lines.append("")
        return "\n".join(lines)

    def submit(self, text: str) -> None:
        if self.turn is not None:
            return
        if self.conversation is None:
            self.conversation = self.store.new(cwd=self.workspace)
        conv = self.conversation
        conv.cwd = self.workspace
        # Build the fallback context *before* this message is in the history,
        # otherwise the prompt repeats the question it is about to ask.
        lost_context = not conv.engine_id or conv.context_lost
        history = self._history_prefix(conv) if lost_context else ""
        conv.add("user", text)
        self.store.save(conv)
        # Learn only what was stated plainly; the page shows exactly what was
        # kept, and the user can delete it.
        try:
            from pathlib import Path as _P  # noqa: PLC0415

            from app import plugins as plugins_mod  # noqa: PLC0415

            reference = (_P(__file__).resolve().parent.parent
                         / "plugins" / "day-summary")
            if reference.is_dir():
                plugins_mod.install(reference)
            page = getattr(self, "plugins_page", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            import datetime as _dt  # noqa: PLC0415

            from app import calendar as calendar_mod  # noqa: PLC0415

            today = _dt.date.today()
            def stamp(hour: int) -> str:
                return _dt.datetime.combine(
                    today, _dt.time(hour=hour)).strftime("%Y%m%dT%H%M%S")

            ics = f"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:design-review@demo
SUMMARY:Design review
DTSTART:{stamp(11)}
DTEND:{stamp(12)}
LOCATION:Room 2
END:VEVENT
BEGIN:VEVENT
UID:focus-hour@demo
SUMMARY:Focus hour
DTSTART:{stamp(15)}
DTEND:{stamp(16)}
END:VEVENT
BEGIN:VEVENT
UID:release@demo
SUMMARY:Release day
DTSTART;VALUE=DATE:{today.strftime('%Y%m%d')}
END:VEVENT
END:VCALENDAR
"""
            demo_ics = _Path(_tempfile.mkdtemp(prefix="mantel-demo-ics-")) / "day.ics"
            demo_ics.write_text(ics)
            calendar_mod.add_source(str(demo_ics))
            page = getattr(self, "today_page", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            from app import todos as todos_mod  # noqa: PLC0415

            for title in ("Pay the invoice today",
                          "Review the Pi adapter notes tomorrow",
                          "Draft the weekly note on Monday",
                          "Someday: read the durable harness docs"):
                todos_mod.add(title)
            done = todos_mod.add("Send the status update", due=0)
            if done is not None:
                todos_mod.complete(done.id)
            page = getattr(self, "tasks", None)
            if page is not None:
                page.refresh()
        except Exception:  # noqa: BLE001
            pass

        try:
            from app import memory as memory_mod  # noqa: PLC0415

            if memory_mod.capture(text):
                self._refresh_memory()
        except Exception:  # noqa: BLE001 - memory must never block a turn
            pass
        self.composer.clear()
        self.chat.add_user(text)

        self.session = session_mod.Session(
            self.engine, conversation_id=conv.engine_id,
            mode=self.composer.mode, approval=self.approval,
            workspace=self.workspace)
        self.session.running = True

        msg = self.chat.begin_assistant(model=self._current_model_label())
        self.composer.set_streaming(True)
        self.composer.set_steering(
            self.engine.supports(engine_mod.STEERING))

        prompt = history + text
        self._requested_engine_id = conv.engine_id
        self.turn = self.engine.run(
            prompt=self.session.brief(prompt),
            model=conv.model or "",
            conversation_id=conv.engine_id,
            cwd=self.workspace,
            effort=self.effort,
            extra_flags=tuple(self.session.flags()),
        )
        self.turn.connect("started", self._on_started)
        self.turn.connect("delta", lambda _t, d: msg.append_delta(d))
        self.turn.connect("thought", lambda _t, d: msg.append_thought(d))
        self.turn.connect("tool", self._on_tool)
        self.turn.connect("dialog", self._on_dialog)
        self.turn.connect("finished", lambda _t, r: self._on_finished(msg, r))
        self.turn.connect("failed", lambda _t, e: self._on_failed(msg, e))

    def steer(self, text: str) -> None:
        """Send an instruction into the running turn, when the engine can."""
        turn = self.turn
        if turn is None or not str(text).strip():
            return
        if not self.engine.supports(engine_mod.STEERING):
            return
        if turn.steer(text):
            self.chat.add_steer(text)
            if self.conversation is not None:
                self.conversation.add("user", f"[steer] {text}")
                self.store.save(self.conversation)

    def _on_dialog(self, _turn, request: dict) -> None:
        """The engine is blocked on a question. Show the card and answer it.

        With Pi this is the approval path: `tool_call` asks before the tool
        runs, so a deny means it never happened — no refusal to replay.
        """
        request_id = str((request or {}).get("id") or "")

        def answer(choice) -> None:
            turn = self.turn
            if turn is None or not request_id:
                return
            if choice is None:
                turn.answer_dialog(request_id, cancelled=True)
            elif (request or {}).get("method") == "confirm":
                turn.answer_dialog(request_id, confirmed=str(choice).lower()
                                   in ("allow", "yes", "true", "ok", "allow once"))
            else:
                turn.answer_dialog(request_id, value=str(choice))

        self._approvals.ask(request or {}, answer)

    def _on_started(self, _turn, engine_id: str) -> None:
        """Persist the engine's session id the moment it exists.

        Waiting until the turn finishes means a crash during the first turn
        loses the only pointer to the engine's session — and with it the
        ability to resume instead of replaying history by hand.
        """
        if self.conversation and engine_id:
            self.conversation.engine_id = engine_id
            self.store.save(self.conversation)

    def _on_tool(self, _turn, name: str, payload: str) -> None:
        """Record a tool call from the engine's stream."""
        import json as _json  # noqa: PLC0415

        try:
            data = _json.loads(payload)
        except (TypeError, ValueError):
            data = {"parameters": {}, "state": "ACTIVE"}
        self.session.record_tool(
            name,
            data.get("parameters") or {},
            data.get("state") or "ACTIVE",
            output=str(data.get("output") or ""),
            error=str(data.get("error") or ""),
            duration=float(data.get("duration") or 0),
        )
        self._update_work()

    def _update_work(self) -> None:
        items = self.session.work_items()
        self._work.set_items(items)
        self._work.set_visible(bool(items))
        self._update_changes()

    def _update_changes(self) -> None:
        """Show what actually changed on disk, per git."""
        from app import changes  # noqa: PLC0415

        try:
            files = changes.collect(self.workspace)
        except Exception:  # noqa: BLE001 - git is best-effort
            files = []
        self._changes.set_changes(files)

    def _show_diff(self, path: str) -> None:
        """Show one file's diff."""
        from app import changes  # noqa: PLC0415

        text = changes.diff(self.workspace, path) or "(no diff available)"
        dialog = Adw.MessageDialog(transient_for=self,
                                   heading=f"Changes in {path}")
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_monospace(True)
        view.get_buffer().set_text(text[:8000])
        view.add_css_class("composer")
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(view)
        scroll.set_size_request(760, 460)
        dialog.set_extra_child(scroll)
        dialog.add_response("close", "Close")
        dialog.present()

    def _on_finished(self, msg, result: dict) -> None:
        self._approvals.clear()
        self.composer.set_streaming(False)
        self.turn = None
        self.session.running = False
        self.session.finished = True
        status = (result or {}).get("status", "")
        error = (result or {}).get("error", "")
        text = (result or {}).get("text", "")

        denied = (result or {}).get("denied") or []
        approvals = self.session.record_approvals(denied)
        if approvals:
            self._approvals.show(approvals, self.session.grantable(approvals[0]))
            self.session.error = error

        if status and status != "SUCCESS":
            msg.fail(error or f"engine returned {status}")
            self.conversation.add("assistant", error or status,
                                  error=error or status)
        else:
            if text:
                msg.set_text(text)
            msg.finish(duration=(result or {}).get("duration", 0.0),
                       usage=(result or {}).get("usage", {}),
                       model=self._current_model_label())
            self.conversation.add("assistant", text,
                                  model=self._current_model_label())
        if self.conversation:
            returned = (result or {}).get("conversation_id") or ""
            requested = getattr(self, "_requested_engine_id", "")
            if returned:
                # the engine silently starts a new conversation when it cannot
                # resume; note it so the next turn replays the history
                self.conversation.context_lost = bool(
                    requested and returned != requested)
                self.conversation.engine_id = returned
        self.store.save(self.conversation)
        self._update_work()
        self._refresh_sidebar()
        self._refresh_today()
        gallery = getattr(self, "create", None)
        if gallery is not None:
            gallery.refresh()
        self._notify_done()

    def _deny_pending_question(self) -> bool:
        """Escape denies a visible question before it stops the turn."""
        stack = getattr(self, "_approvals", None)
        return bool(stack is not None and stack.deny_current())

    def _on_failed(self, msg, message: str) -> None:
        self._approvals.clear()
        self.composer.set_streaming(False)
        self.turn = None
        self.session.running = False
        self.session.error = message
        msg.fail(message)
        self.conversation.add("assistant", message, error=message)
        self.store.save(self.conversation)
        self._update_work()
        self._refresh_sidebar()

    def _notify_done(self) -> None:
        """Tell the desktop when a turn finishes, as the real apps do."""
        try:
            notification = Gio.Notification.new("Mantel")
            notification.set_body("Your turn is ready.")
            self.get_application().send_notification(None, notification)
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass

    def stop(self) -> None:
        """Escape / the stop button: deny a pending question first, else stop."""
        if self._deny_pending_question():
            return
        if self.turn is not None:
            self.turn.cancel()

    # -- reminders ----------------------------------------------------------
    def _on_reminder(self, _runner, task) -> None:
        """A task's time arrived. Notify, and show it on the page."""
        due = ""
        if getattr(task, "due", 0):
            import time as _time  # noqa: PLC0415

            due = _time.strftime("%H:%M", _time.localtime(task.due))
        body = task.title + (" · " + due if due else "")
        self._notify("Reminder", body)
        self._refresh_tasks()
        self._refresh_today()

    # -- schedules ----------------------------------------------------------
    def _run_schedule(self, schedule) -> None:
        """Run one schedule immediately."""
        self.scheduler.run(schedule)
        self._notify("Running schedule", schedule.title)

    def _refresh_schedules(self) -> None:
        page = getattr(self, "schedule", None)
        if page is not None:
            page.refresh()

    def _on_schedule_ran(self, _scheduler, schedule, run) -> None:
        self._notify(
            schedule.title,
            (run.text or "Finished.").replace("\n", " ")[:120])
        self._refresh_schedules()

    def _on_schedule_failed(self, _scheduler, schedule, message) -> None:
        self._notify(f"{schedule.title} failed", message[:120])
        self._refresh_schedules()

    def _notify(self, title: str, body: str) -> None:
        """Raise a desktop notification."""
        try:
            note = Gio.Notification.new(title)
            note.set_body(body)
            self.get_application().send_notification(None, note)
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass

    # -- approvals ----------------------------------------------------------
    def _on_approval(self, appr: session_mod.Approval, scope: str) -> None:
        if scope == "deny":
            self._approvals.clear()
            self.session.approvals = []
            self._update_work()
            return
        if not self.session.grantable(appr):
            self._approvals.clear()
            return
        self.session.grant(appr, scope)
        self._approvals.clear()
        self.session.approvals = []
        # the action was refused, so the turn has to run again with the grant
        if self.conversation is not None and self.conversation.messages:
            last = self.conversation.messages[-1]
            if last.role == "user":
                self._retry(last.text)

    def _retry(self, prompt: str) -> None:
        conv = self.conversation
        if conv is not None and conv.messages:
            conv.messages.pop()          # take the user turn back off the log
        self.submit(prompt)

    # -- the dashboard, fed with what the machine reports -------------------
    def _refresh_home(self) -> None:
        """Push real state into the dashboard."""
        if self.home is None:
            return
        from app import mcp as mcp_mod  # noqa: PLC0415
        from app import skills as skills_mod  # noqa: PLC0415

        models = []
        for mid, label in self.engine.models():
            models.append({
                "icon": "gemini_spark" if mid.startswith("gemini") else "memory",
                "name": label,
                "sub": "Gemini" if mid.startswith("gemini") else "Other",
                "grade": "A+",
            })
        if not models:
            models = [{"icon": "gemini_spark", "name": "No models",
                       "sub": "engine not found", "grade": "—"}]

        try:
            servers = mcp_mod.list_servers()
        except Exception:  # noqa: BLE001
            servers = []
        try:
            available = skills_mod.list_skills()
        except Exception:  # noqa: BLE001
            available = []

        chats = self.store.list()[:3]
        chat_cards = []
        for conv in chats:
            preview = ""
            for msg in conv.messages:
                if msg.role == "user":
                    preview = msg.text
                    break
            chat_cards.append({
                "id": conv.id,
                "title": conv.title,
                "body": preview or "No messages yet.",
                "status": session_mod.STATUS_LABELS.get(self._status_for(conv), ""),
                "date": time.strftime("%d %b", time.localtime(conv.updated)),
                "icon": "chat",
            })

        stats = [
            ("forum", str(len(self.store.list())), "Chats"),
            ("memory", str(len(models)), "Models"),
            ("extension", str(len(servers)), "Connectors"),
            ("notes_spark", str(len(available)), "Skills"),
        ]
        signature = (tuple(m["name"] for m in models), tuple(stats),
                     tuple(c["title"] for c in chat_cards))
        if signature == getattr(self, "_home_signature", None):
            return
        self._home_signature = signature
        self.home.set_live_data(models=models, stats=stats, chats=chat_cards)

    # -- history ------------------------------------------------------------
    def _refresh_sidebar(self) -> None:
        convs = self.store.list()
        self.sidebar.set_conversations(convs, self._status_for)
        tasks = getattr(self, "tasks", None)
        if tasks is not None:
            tasks.refresh()
        self._refresh_home()

    def _status_for(self, conv) -> str:
        if self.conversation is not None and conv.id == self.conversation.id:
            return self.session.status()
        return session_mod.STATUS_IDLE

    # -- conversations ------------------------------------------------------
    def new_chat(self) -> None:
        model = self.conversation.model if self.conversation else ""
        self.conversation = self.store.new(cwd=self.workspace, model=model)
        self.chat.reset()
        self.chat.show_welcome(self._use_suggestion)
        self.composer.clear()
        self.composer.set_model(self._current_model_label())
        self._go("chat")
        self.composer.focus()
        self._refresh_sidebar()

    def _use_suggestion(self, prompt: str) -> None:
        self.composer.view.get_buffer().set_text(prompt)
        self.composer.view.set_opacity(1.0)
        self.composer.focus()

    def open_chat(self, cid: str) -> None:
        conv = self.store.load(cid)
        if conv is None:
            return
        self.conversation = conv
        if conv.cwd:
            self.workspace = conv.cwd
            self.composer.set_workspace(conv.cwd)
        self.chat.reset()
        if not conv.messages:
            self.chat.show_welcome(self._use_suggestion)
        for msg in conv.messages:
            if msg.role == "user":
                self.chat.add_user(msg.text)
            elif msg.error:
                self.chat.add_error(msg.error)
            else:
                m = self.chat.add_assistant_text(msg.text, model=msg.model)
                if msg.thinking:
                    m.append_thought(msg.thinking)
        self.composer.set_model(self._current_model_label())
        self._go("chat")
        self._refresh_sidebar()
        self._restore_from_engine(conv)

    def _restore_from_engine(self, conv) -> None:
        """Fill in turns the engine has but our store does not.

        The store is written per message, so a crash between the engine
        committing and the client saving can leave a thread short. When the
        engine keeps its own session (Pi does), the transcript is reconciled
        against it — our JSON stays an index, not the only copy.
        """
        engine_id = getattr(conv, "engine_id", "")
        if not engine_id or not self.engine.supports(engine_mod.SESSIONS):
            return
        def work() -> None:
            history = self.engine.history(engine_id)
            if history:
                GLib.idle_add(self._apply_history, conv, history)

        threading.Thread(target=work, daemon=True,
                         name="mantel-history").start()

    @staticmethod
    def _missing_turns(stored: list[dict], history: list[dict]) -> list[dict]:
        """The turns the engine has that the store does not.

        The common case is a trailing gap (the engine committed, the client
        died before saving), so the stored transcript is matched as a
        contiguous run inside the engine's history and everything after it is
        appended. If the two disagree — a reset store, a thread started in
        another client — the fallback merges by content rather than guessing
        an index.
        """
        if not stored:
            return list(history)
        key = lambda entry: (entry.get("role"), entry.get("text"))  # noqa: E731
        wanted = [key(entry) for entry in stored]
        for offset in range(len(history) - len(wanted) + 1):
            if [key(entry) for entry in history[offset:offset + len(wanted)]] == wanted:
                return history[offset + len(wanted):]
        seen = set(wanted)
        extra = []
        for entry in history:
            if key(entry) in seen:
                continue
            seen.add(key(entry))
            extra.append(entry)
        return extra

    def _apply_history(self, conv, history: list[dict]) -> bool:
        """Append only the turns the transcript does not already show."""
        if self.conversation is None or self.conversation.id != conv.id:
            return False
        stored = [{"role": m.role, "text": m.text}
                  for m in conv.messages if m.text]
        missing = self._missing_turns(stored, history)
        if not missing:
            return False
        for entry in missing:
            role = entry.get("role")
            text = str(entry.get("text") or "")
            if not text:
                continue
            if role == "user":
                self.chat.add_user(text)
            else:
                self.chat.add_assistant_text(text)
            conv.add(role, text)
        self.store.save(conv)
        self._refresh_sidebar()
        return False

    def delete_chat(self, cid: str) -> None:
        self.store.delete(cid)
        if self.conversation and self.conversation.id == cid:
            self.new_chat()
        else:
            self._refresh_sidebar()

    # -- actions ------------------------------------------------------------
    def _install_palette_shortcut(self) -> None:
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)

        def bind(accel: str) -> None:
            trigger = Gtk.ShortcutTrigger.parse_string(accel)
            action = Gtk.CallbackAction.new(
                lambda *_args: (self.open_palette(), True)[1])
            controller.add_shortcut(Gtk.Shortcut.new(trigger, action))

        bind("<Control>k")
        bind("<Control>p")
        self.add_controller(controller)

    def open_palette(self, seed: str = "") -> None:
        self.palette.open(seed)

    def _close_palette(self) -> None:
        self.composer.focus()

    def _run_palette_action(self, action) -> None:
        """Turn a palette action into the real thing."""
        kind = getattr(action, "kind", "")
        payload = getattr(action, "payload", "")

        if kind == "navigate":
            self._go(payload)
            return
        if kind == "command":
            self._run_command(payload)
            return
        if kind == "ask":
            self.composer.view.get_buffer().set_text(
                f"[[ask]]{payload}")
            self._go("chat")
            self.composer.view.get_buffer().set_text(payload)
            self.composer.focus()
            return
        if kind == "task":
            from app import todos  # noqa: PLC0415

            task = todos.add(payload)
            if task is not None:
                self._notify("Task added", task.title)
                self._refresh_tasks()
                self._refresh_sidebar()
            return
        if kind == "remind":
            from app import todos  # noqa: PLC0415

            task = todos.add(payload, remind=True)
            if task is not None:
                self._notify("Reminder set", task.title)
                self._refresh_tasks()
            return
        if kind == "plugin":
            self._run_plugin_command(payload)
            return
        if kind == "note":
            from app import memory as memory_mod  # noqa: PLC0415

            fact = memory_mod.remember(payload, source="you")
            if fact is not None:
                self._notify("Remembered", fact.text)
                self._refresh_memory()
            return

    def _run_command(self, name: str) -> None:
        if name == "new-thread":
            self.new_chat()
        elif name == "start-focus":
            self._go("today")
            page = getattr(self, "today_page", None)
            if page is not None:
                page.focus.start()
        elif name == "toggle-theme":
            self._set_theme("dark" if theme.scheme().name == "light"
                            else "light")
        elif name == "review-day":
            from app import todos  # noqa: PLC0415

            open_tasks = todos.all_tasks(include_done=False)
            summary = ", ".join(task.title for task in open_tasks[:5])
            self.new_chat()
            self.composer.view.get_buffer().set_text(
                "Review my day. Open tasks: " + (summary or "none") +
                ". Ask me what to drop or defer, then propose a plan.")
            self.composer.focus()

    def _install_actions(self) -> None:
        def add(name, cb, accel=None):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", cb)
            self.add_action(action)
            if accel:
                self.get_application().set_accels_for_action(f"win.{name}", accel)

        add("new-chat", lambda *_: self.new_chat(), ["<Control>n"])
        add("pick-workspace", lambda *_: self.pick_workspace())
        add("engine-status", lambda *_: self._show_engine_status())
        add("shortcuts", lambda *_: self._show_shortcuts())
        add("about", lambda *_: self._show_about())
        add("connectors", lambda *_: self._go("connectors"))
        add("skills", lambda *_: self._go("skills"))
        add("schedule", lambda *_: self._go("schedule"))
        add("account", lambda *_: self._show_account())

    def _show_engine_status(self) -> None:
        binary = self.engine.binary or "not found"
        models = ", ".join(m for m, _ in self.engine.models())
        self._dialog("Engine status",
                     f"Engine binary:\n{binary}\n\nModels:\n{models}\n\n"
                     f"Working folder:\n{self.workspace}\n\n"
                     f"Approval mode: {self.composer.approval_label.get_text()}\n"
                     f"Effort: {self.effort}\n\n"
                     f"Signed in as: {self._account.email or 'nobody'}")

    def _show_shortcuts(self) -> None:
        self._dialog("Keyboard shortcuts",
                     "Enter — send\n"
                     "Shift+Enter — new line\n"
                     "Esc — stop generating\n"
                     "Ctrl+N — new chat\n"
                     "Ctrl+B — toggle sidebar")

    def _show_about(self) -> None:
        self._dialog(
            "About",
            "Mantel\n\n"
            "A native GTK4 desktop for AI agents on Linux: a design-led shell "
            "with approvals you can see, a work panel, a git-backed changed-files "
            "view, schedules and durable conversations. It grew out of a study "
            "of the Gemini desktop app, whose structure this shell follows.")

    def do_close_request(self) -> bool:
        """Stop the scheduler when the window closes."""
        scheduler = getattr(self, "scheduler", None)
        if scheduler is not None:
            scheduler.stop()
        reminders = getattr(self, "reminders", None)
        if reminders is not None:
            reminders.stop()
        today = getattr(self, "today_page", None)
        if today is not None:
            today.stop()
        return False

    def _show_options(self) -> None:
        self._dialog("Options",
                     "Everything about the agent lives under Customize:\n\n"
                     "Connectors — the MCP servers the agent can use\n"
                     "Skills — reusable instructions it can draw on\n"
                     "Schedule — recurring prompts\n\n"
                     "The account menu at the foot of the rail shows who is "
                     "signed in.")

    def _dialog(self, title: str, body: str) -> None:
        dlg = Adw.MessageDialog(transient_for=self, heading=title)
        lbl = Gtk.Label(label=body, xalign=0)
        lbl.set_wrap(True)
        lbl.set_selectable(True)
        lbl.set_margin_top(6)
        dlg.set_extra_child(lbl)
        dlg.add_response("close", "Close")
        dlg.present()
