"""
Main Application Window — Bitwarden-inspired layout

Sidebar navigation + inline scrollable credential vault.
"""
import os
import time
import tkinter as tk
import webbrowser
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Dict
from models.credential import Credential
from database.credential_store import CredentialStore
from database.master_password_store import MasterPasswordStore
from ui.credential_dialog import CredentialDialog
from ui.password_generator import show_password_generator
from ui.settings_dialog import show_settings_dialog, SettingsManager
from utils.session_manager import SessionManager
from utils.clipboard_manager import ClipboardManager
from utils.validators import validate_password_strength
from utils.backup_manager import BackupManager


class MainWindow:
    # Bitwarden-inspired dark palette
    SIDEBAR_BG   = "#191c23"
    CONTENT_BG   = "#1e2230"
    ITEM_BG      = "#252836"
    ITEM_HOVER   = "#2d3248"
    NAV_ACTIVE   = "#1e3a5f"    # selected sidebar item
    ACCENT       = "#175ddc"
    TEXT         = "#e4e7ef"
    TEXT_SEC     = "#7d8fa6"
    BORDER       = "#2e3245"
    DANGER_COL   = "#dc3545"

    def __init__(self, root, master_password: str, salt: bytes):
        self.root = root
        self.master_password = master_password
        self.salt = salt
        self.credentials: Dict[str, Credential] = {}

        self.search_var    = None
        self.timer_label   = None
        self.count_label   = None
        self.canvas        = None
        self.canvas_win_id = None
        self.items_frame   = None
        self._nav_items    = []   # list of (frame, lbl, bar, extra_widgets)
        self._active_nav   = None  # currently highlighted nav frame
        self._view_mode    = "all"   # "all" | "favorites" | "recent"
        self._tag_filter   = None    # active tag filter (None = no tag filter)
        self.tag_bar       = None

        self.clipboard_manager = ClipboardManager(root)
        settings = SettingsManager.load_settings()
        self.session_manager = SessionManager(
            timeout_minutes=settings['auto_lock_minutes'],
            lock_callback=self._auto_lock
        )

        self._load_credentials()
        self._build_layout()
        # Auto-lock disabled — the inactivity monitor is intentionally not started.
        # (Manual "Lock Application" button still works.)
        self._bind_activity()
        self._tick_timer()
        # Closing the window force-terminates the process immediately, so a
        # background SSH scan worker (non-daemon ThreadPoolExecutor) can never
        # keep the app alive after the user clicks ✕.
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

    def _quit_app(self):
        os._exit(0)

    # ------------------------------------------------------------------ data
    def _load_credentials(self):
        try:
            self.credentials = CredentialStore.load_credentials(self.master_password, self.salt)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load credentials: {e}")
            self.credentials = {}

    def _save_credentials(self):
        try:
            CredentialStore.save_credentials(self.credentials, self.master_password, self.salt)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save credentials: {e}")

    # ------------------------------------------------------------------ layout
    def _build_layout(self):
        self.root.title("SecureVault")
        self.root.resizable(True, True)
        self.root.minsize(860, 550)
        self.root.configure(bg=self.SIDEBAR_BG)

        # Open maximized so everything is visible regardless of screen size
        try:
            self.root.state('zoomed')        # Windows
        except Exception:
            self.root.geometry("1200x750")   # fallback

        # Apply opacity after window is shown (after() ensures it takes effect)
        def _apply_opacity():
            settings = SettingsManager.load_settings()
            try:
                self.root.wm_attributes('-alpha', float(settings.get('opacity', 0.95)))
            except Exception:
                pass

        self.root.after(100, _apply_opacity)

        # Dark/matching title bar — longer delay so the window is fully composited
        self.root.after(200, self._apply_dark_titlebar)

        sidebar = tk.Frame(self.root, bg=self.SIDEBAR_BG, width=250)
        sidebar.pack(side=LEFT, fill=Y)
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        tk.Frame(self.root, bg=self.BORDER, width=1).pack(side=LEFT, fill=Y)

        # Content host — vault frame and ZTerm frame are swapped here
        self._content_host = tk.Frame(self.root, bg=self.CONTENT_BG)
        self._content_host.pack(side=LEFT, fill=BOTH, expand=True)

        self._vault_frame = tk.Frame(self._content_host, bg=self.CONTENT_BG)
        self._vault_frame.pack(fill=BOTH, expand=True)
        self._build_content(self._vault_frame)

        self._zterm_frame = tk.Frame(self._content_host, bg="#12121f")
        # Imported lazily so existing vault functionality is unaffected on import
        from ui.zterm_panel import ZTermPanel
        self._zterm_panel = ZTermPanel(
            self._zterm_frame,
            get_credentials=lambda: self.credentials,
            update_credential_password=self._zterm_update_credential_password,
        )
        self._zterm_panel.pack(fill=BOTH, expand=True)
        # Not packed yet — shown only when ZTERM nav item is selected

    def _apply_dark_titlebar(self):
        """Make the Windows title bar match the dark sidebar colour."""
        try:
            import ctypes
            # FindWindowW is more reliable than winfo_id() in PyInstaller builds
            hwnd = ctypes.windll.user32.FindWindowW(None, "SecureVault")
            if not hwnd:
                hwnd = self.root.winfo_id()

            # Dark mode — attribute 19 (Win10 <20H1) and 20 (Win10 20H1+ / Win11)
            for attr in (20, 19):
                try:
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, attr,
                        ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int)
                    )
                except Exception:
                    pass

            # Custom caption colour — Windows 11 only (attribute 35)
            # SIDEBAR_BG #191c23 → R=0x19 G=0x1c B=0x23 → COLORREF 0x00231c19
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 35,
                    ctypes.byref(ctypes.c_int(0x00231c19)), ctypes.sizeof(ctypes.c_int)
                )
            except Exception:
                pass
        except Exception:
            pass

    # ------------------------------------------------------------------ sidebar
    def _build_sidebar(self, parent):
        # Logo
        logo = tk.Frame(parent, bg=self.SIDEBAR_BG)
        logo.pack(fill=X, padx=15, pady=(18, 8))
        tk.Label(logo, text="SecureVault", bg=self.SIDEBAR_BG, fg=self.TEXT,
                 font=("Segoe UI", 13, "bold"), anchor=W).pack(fill=X)
        tk.Label(logo, text="Password Manager", bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 8), anchor=W).pack(fill=X)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X, padx=15, pady=10)

        # MY VAULT
        self._section_label(parent, "MY VAULT")
        activate_all = self._nav_btn(parent, "All Items", self._show_all, count=True)
        self._nav_btn(parent, "⭐ Favorites", self._show_favorites)
        self._nav_btn(parent, "🕘 Recent",    self._show_recent)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X, padx=12, pady=8)

        # TOOLS
        self._section_label(parent, "TOOLS")
        self._nav_btn(parent, "Password Generator", self._show_generator)
        self._nav_btn(parent, "Health Check",       self._check_health)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X, padx=12, pady=8)

        # ACCOUNT
        self._section_label(parent, "ACCOUNT")
        self._nav_btn(parent, "Settings",        self._show_settings)
        self._nav_btn(parent, "Change Password", self._change_master_password)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X, padx=12, pady=8)

        # BACKUP
        self._section_label(parent, "BACKUP")
        self._nav_btn(parent, "Export Backup", self._export_backup)
        self._nav_btn(parent, "Import Backup", self._import_backup)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X, padx=12, pady=8)

        # ZTERM
        self._section_label(parent, "ZTERM")
        self._nav_btn(parent, "SSH Sessions", self._show_zterm)

        # Set "All Items" as default active item without firing the command
        nav_tuple = self._nav_items[0]
        frame, lbl, bar, cnt_lbl = nav_tuple
        self._active_nav = nav_tuple
        bar.configure(bg=self.ACCENT)
        frame.configure(bg=self.NAV_ACTIVE)
        lbl.configure(bg=self.NAV_ACTIVE)
        if cnt_lbl:
            cnt_lbl.configure(bg=self.NAV_ACTIVE)

        # Push remaining to bottom
        tk.Frame(parent, bg=self.SIDEBAR_BG).pack(fill=BOTH, expand=True)

        # Bottom area
        bottom = tk.Frame(parent, bg=self.SIDEBAR_BG, padx=15, pady=15)
        bottom.pack(fill=X, side=BOTTOM)

        self.timer_label = tk.Label(bottom, text="", bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                                    font=("Segoe UI", 8))
        self.timer_label.pack(pady=(0, 8))

        # "Lock Application" button removed — locking is disabled.

        tk.Label(bottom, text="© Zamiq Mustafayev", bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 7)).pack(pady=(10, 0))

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 8), anchor=W).pack(fill=X, padx=20, pady=(4, 2))

    def _nav_btn(self, parent, text, command, count=False):
        frame = tk.Frame(parent, bg=self.SIDEBAR_BG, cursor="hand2")
        frame.pack(fill=X)

        # Left accent bar — always rendered; colour changes on active/inactive
        bar = tk.Frame(frame, bg=self.SIDEBAR_BG, width=4)
        bar.pack(side=LEFT, fill=Y)
        bar.pack_propagate(False)

        lbl = tk.Label(frame, text=text, bg=self.SIDEBAR_BG, fg=self.TEXT,
                       font=("Segoe UI", 9), anchor=W, padx=11, pady=7)
        lbl.pack(side=LEFT, fill=X, expand=True)

        cnt_lbl = None
        if count:
            cnt_lbl = tk.Label(frame, bg=self.SIDEBAR_BG, fg=self.TEXT_SEC,
                               text=str(len(self.credentials)),
                               font=("Segoe UI", 9), padx=10)
            cnt_lbl.pack(side=RIGHT)
            self.count_label = cnt_lbl

        nav_tuple = (frame, lbl, bar, cnt_lbl)
        self._nav_items.append(nav_tuple)
        all_bg_widgets = [frame, lbl] + ([cnt_lbl] if cnt_lbl else [])

        def _deactivate_all():
            for f, l, b, c in self._nav_items:
                b.configure(bg=self.SIDEBAR_BG)
                f.configure(bg=self.SIDEBAR_BG)
                l.configure(bg=self.SIDEBAR_BG)
                if c:
                    c.configure(bg=self.SIDEBAR_BG)

        def activate():
            _deactivate_all()
            self._active_nav = nav_tuple
            bar.configure(bg=self.ACCENT)
            for w in all_bg_widgets:
                w.configure(bg=self.NAV_ACTIVE)
            command()

        def enter(e):
            if self._active_nav is not nav_tuple:
                for w in all_bg_widgets:
                    w.configure(bg=self.ITEM_HOVER)

        def leave(e):
            if self._active_nav is not nav_tuple:
                for w in all_bg_widgets:
                    w.configure(bg=self.SIDEBAR_BG)

        for w in [frame, lbl] + ([cnt_lbl] if cnt_lbl else []):
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", lambda e, a=activate: a())

        return activate

    # ------------------------------------------------------------------ content
    def _build_content(self, parent):
        # Top bar
        topbar = tk.Frame(parent, bg=self.CONTENT_BG, pady=12, padx=15)
        topbar.pack(fill=X)

        # Search box
        search_wrap = tk.Frame(topbar, bg=self.ITEM_BG, padx=8)
        search_wrap.pack(side=LEFT, fill=X, expand=True, padx=(0, 12))

        tk.Label(search_wrap, text="🔍", bg=self.ITEM_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 10)).pack(side=LEFT)

        self.search_var = ttk.StringVar()
        self.search_var.trace('w', lambda *_: self._refresh())

        tk.Entry(search_wrap, textvariable=self.search_var,
                 bg=self.ITEM_BG, fg=self.TEXT, insertbackground=self.TEXT,
                 font=("Segoe UI", 11), bd=0, relief=FLAT,
                 highlightthickness=0).pack(side=LEFT, fill=X, expand=True, ipady=7, padx=(4, 0))

        ttk.Button(topbar, text="+ Add Item", command=self._add_credential,
                   bootstyle="primary").pack(side=RIGHT)

        tk.Frame(parent, bg=self.BORDER, height=1).pack(fill=X)

        # Tag filter chips (populated by _rebuild_tag_bar; hidden when no tags)
        self.tag_bar = tk.Frame(parent, bg=self.CONTENT_BG)

        # Scrollable vault list
        container = tk.Frame(parent, bg=self.CONTENT_BG)
        container.pack(fill=BOTH, expand=True)

        self.canvas = tk.Canvas(container, bg=self.CONTENT_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)

        self.items_frame = tk.Frame(self.canvas, bg=self.CONTENT_BG)
        self.items_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_win_id = self.canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_win_id, width=e.width)
        )

        vsb.pack(side=RIGHT, fill=Y)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.canvas.bind_all("<MouseWheel>", self._on_scroll)

        self._refresh()

    def _on_scroll(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------ vault list
    def _refresh(self):
        for w in self.items_frame.winfo_children():
            w.destroy()

        search = self.search_var.get().lower() if self.search_var else ""

        self._rebuild_tag_bar()

        if not self.credentials:
            self._empty_state("🔐", "Your vault is empty",
                              "Click \"+ Add Item\" to store your first credential")
            self._sync_count()
            return

        def match_search(k, v):
            if not search:
                return True
            return (search in k.lower()
                    or search in v.username.lower()
                    or (v.website_url and search in v.website_url.lower())
                    or (v.notes and search in v.notes.lower())
                    or any(search in t.lower() for t in v.tags))

        # Base item list, ordered by view mode.
        items = list(self.credentials.items())
        if self._view_mode == "favorites":
            items = [(k, v) for k, v in items if v.favorite]
        elif self._view_mode == "recent":
            items = [(k, v) for k, v in items if v.last_used]
            items.sort(key=lambda kv: kv[1].last_used, reverse=True)
            items = items[:10]
        else:  # all → favorites first, then alphabetical
            items.sort(key=lambda kv: (not kv[1].favorite, kv[0].lower()))

        filtered = [(k, v) for k, v in items
                    if match_search(k, v)
                    and (self._tag_filter is None or self._tag_filter in v.tags)]

        if not filtered:
            if self._view_mode == "favorites":
                self._empty_state("⭐", "No favorites yet",
                                  "Click the ☆ on an item to favorite it")
            elif self._view_mode == "recent":
                self._empty_state("🕘", "Nothing recent",
                                  "Copy or open an item and it shows up here")
            else:
                self._empty_state("🔍", "No results",
                                  f"Nothing matches \"{search or self._tag_filter}\"")
            self._sync_count()
            return

        for svc, cred in filtered:
            self._vault_card(svc, cred)

        self._sync_count()

    def _rebuild_tag_bar(self):
        """Render the clickable tag-filter chips above the item list."""
        if self.tag_bar is None:
            return
        for w in self.tag_bar.winfo_children():
            w.destroy()
        tags = sorted({t for c in self.credentials.values() for t in c.tags})
        if not tags:
            self.tag_bar.pack_forget()
            return
        self.tag_bar.pack(fill=X, padx=12, pady=(0, 4))
        tk.Label(self.tag_bar, text="Tags:", bg=self.CONTENT_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 8)).pack(side=LEFT, padx=(0, 4))
        if self._tag_filter is not None:
            self._chip(self.tag_bar, "✕ clear", None, active=False)
        for t in tags:
            self._chip(self.tag_bar, f"#{t}", t, active=(t == self._tag_filter))

    def _chip(self, parent, text, tag, active):
        bg = self.ACCENT if active else self.ITEM_BG
        lbl = tk.Label(parent, text=text, bg=bg, fg=self.TEXT,
                       font=("Segoe UI", 8), padx=6, pady=1, cursor="hand2")
        lbl.pack(side=LEFT, padx=2)
        lbl.bind("<Button-1>", lambda e, t=tag: self._set_tag_filter(t))
        return lbl

    def _set_tag_filter(self, tag):
        # Clicking the active tag (or "clear") removes the filter.
        self._tag_filter = None if (tag is None or tag == self._tag_filter) else tag
        self._refresh()

    def _empty_state(self, icon, title, subtitle):
        f = tk.Frame(self.items_frame, bg=self.CONTENT_BG)
        f.pack(pady=90)
        tk.Label(f, text=icon, bg=self.CONTENT_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 36)).pack()
        tk.Label(f, text=title, bg=self.CONTENT_BG, fg=self.TEXT,
                 font=("Segoe UI", 14, "bold")).pack(pady=(12, 4))
        tk.Label(f, text=subtitle, bg=self.CONTENT_BG, fg=self.TEXT_SEC,
                 font=("Segoe UI", 10)).pack()

    def _vault_card(self, service_name: str, cred: Credential):
        # Outer wrapper (provides padx/pady spacing between cards)
        wrapper = tk.Frame(self.items_frame, bg=self.CONTENT_BG)
        wrapper.pack(fill=X, padx=12, pady=2)

        card = tk.Frame(wrapper, bg=self.ITEM_BG, padx=0, pady=0)
        card.pack(fill=X)

        # Blue left accent bar
        tk.Frame(card, bg=self.ACCENT, width=4).pack(side=LEFT, fill=Y)

        inner = tk.Frame(card, bg=self.ITEM_BG, padx=12, pady=10)
        inner.pack(side=LEFT, fill=BOTH, expand=True)

        # Icon
        icon_lbl = tk.Label(inner, text="🔑", bg=self.ITEM_BG,
                            font=("Segoe UI", 13))
        icon_lbl.pack(side=LEFT, padx=(0, 10))

        # Text info
        info = tk.Frame(inner, bg=self.ITEM_BG)
        info.pack(side=LEFT, fill=X, expand=True)

        name_lbl = tk.Label(info, text=service_name, bg=self.ITEM_BG, fg=self.TEXT,
                            font=("Segoe UI", 11, "bold"), anchor=W)
        name_lbl.pack(fill=X)

        user_lbl = tk.Label(info, text=cred.username or "(no username)",
                           bg=self.ITEM_BG, fg=self.TEXT_SEC,
                           font=("Segoe UI", 9), anchor=W)
        user_lbl.pack(fill=X)

        url_lbl = None
        if cred.website_url:
            short_url = cred.website_url[:45] + ("…" if len(cred.website_url) > 45 else "")
            url_lbl = tk.Label(info, text=short_url, bg=self.ITEM_BG,
                              fg="#4a9eff", font=("Segoe UI", 8), anchor=W,
                              cursor="hand2")
            url_lbl.pack(fill=X)
            url_lbl.bind("<Button-1>", lambda e, u=cred.website_url: self._open_url(u))

        # Meta line: tags + notes indicator
        meta_lbl = None
        meta_bits = []
        if cred.tags:
            meta_bits.append("  ".join(f"#{t}" for t in cred.tags))
        if cred.notes:
            meta_bits.append("📝")
        if meta_bits:
            meta_lbl = tk.Label(info, text="   ".join(meta_bits), bg=self.ITEM_BG,
                               fg="#6fae6f", font=("Segoe UI", 8), anchor=W)
            meta_lbl.pack(fill=X)

        # Action buttons — text labels so they render correctly on all Windows versions
        btns = tk.Frame(inner, bg=self.ITEM_BG)
        btns.pack(side=RIGHT, padx=(8, 0))

        # Favorite star (toggles favorite, re-renders)
        star = tk.Label(btns, text="★" if cred.favorite else "☆", bg=self.ITEM_BG,
                        fg="#f0c000" if cred.favorite else self.TEXT_SEC,
                        font=("Segoe UI", 13), cursor="hand2")
        star.pack(side=LEFT, padx=(0, 6))
        star.bind("<Button-1>", lambda e, c=cred: self._toggle_favorite(c))

        if cred.website_url:
            self._small_btn(btns, "Open", lambda u=cred.website_url: self._open_url(u),
                            "info-outline")

        self._small_btn(btns, "Copy User",
                        lambda c=cred: (self._mark_used(c),
                                        self._copy_item(c.username, "Username")),
                        "secondary-outline")
        self._small_btn(btns, "Copy Pass",
                        lambda c=cred: (self._mark_used(c),
                                        self._copy_item(c.password, "Password")),
                        "secondary-outline")
        self._small_btn(btns, "Edit",
                        lambda s=service_name, c=cred: self._edit_credential(s, c),
                        "secondary-outline")
        self._small_btn(btns, "Delete",
                        lambda s=service_name, c=cred: self._delete_credential(s, c),
                        "danger-outline")

        # Hover effect
        bg_widgets = [card, inner, icon_lbl, info, name_lbl, user_lbl, btns, star]
        if url_lbl:
            bg_widgets.append(url_lbl)
        if meta_lbl:
            bg_widgets.append(meta_lbl)

        def enter(e, ws=bg_widgets):
            for w in ws:
                try:
                    w.configure(bg=self.ITEM_HOVER)
                except Exception:
                    pass

        def leave(e, ws=bg_widgets):
            for w in ws:
                try:
                    w.configure(bg=self.ITEM_BG)
                except Exception:
                    pass

        for w in [wrapper, card, inner, info, name_lbl, user_lbl, icon_lbl]:
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            # Double-click opens view dialog
            w.bind("<Double-Button-1>",
                   lambda e, s=service_name, c=cred: self._view_credential(s, c))

    def _small_btn(self, parent, text, command, style):
        btn = ttk.Button(parent, text=text, command=command,
                         bootstyle=style, padding=(6, 3))
        btn.pack(side=LEFT, padx=2)
        return btn

    def _sync_count(self):
        if self.count_label:
            self.count_label.configure(text=str(len(self.credentials)))

    # ------------------------------------------------------------------ CRUD
    def _add_credential(self):
        self.session_manager.record_activity()

        def on_save(credential, _):
            try:
                self.credentials = CredentialStore.add_credential(
                    credential, self.credentials, self.master_password, self.salt
                )
                self._refresh()
                messagebox.showinfo("Saved", f"'{credential.service_name}' added to your vault.")
            except ValueError as e:
                messagebox.showerror("Error", str(e))

        CredentialDialog(self.root, mode=CredentialDialog.MODE_ADD,
                         existing_services=set(self.credentials.keys()),
                         on_save=on_save, clipboard_manager=self.clipboard_manager)

    def _view_credential(self, service_name: str, cred: Credential):
        self.session_manager.record_activity()
        self._mark_used(cred)
        CredentialDialog(self.root, mode=CredentialDialog.MODE_VIEW,
                         credential=cred, clipboard_manager=self.clipboard_manager)

    def _zterm_update_credential_password(self, name: str, new_password: str) -> bool:
        """Update a vault credential's stored password (used by ZTerm's bulk
        password-change tool after it changes the password on the servers)."""
        cred = self.credentials.get(name)
        if not cred:
            return False
        cred.password = new_password
        self._persist()
        return True

    def _persist(self):
        """Save the in-memory credentials to the encrypted store."""
        try:
            CredentialStore.save_credentials(
                self.credentials, self.master_password, self.salt)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _mark_used(self, cred: Credential):
        """Stamp a credential as just-used (drives the Recent view)."""
        cred.last_used = time.time()
        self._persist()        # no _refresh → don't reshuffle cards mid-action

    def _toggle_favorite(self, cred: Credential):
        cred.favorite = not cred.favorite
        self._persist()
        self._refresh()

    def _edit_credential(self, service_name: str, cred: Credential):
        self.session_manager.record_activity()

        def on_save(new_cred, old_svc):
            try:
                self.credentials = CredentialStore.update_credential(
                    new_cred, old_svc, self.credentials, self.master_password, self.salt
                )
                self._refresh()
            except ValueError as e:
                messagebox.showerror("Error", str(e))

        CredentialDialog(self.root, mode=CredentialDialog.MODE_EDIT,
                         credential=cred,
                         existing_services=set(self.credentials.keys()),
                         on_save=on_save, clipboard_manager=self.clipboard_manager)

    def _delete_credential(self, service_name: str, cred: Credential):
        self.session_manager.record_activity()
        if not messagebox.askyesno("Delete Item",
                                   f"Delete '{service_name}'?\nThis cannot be undone."):
            return
        try:
            self.credentials = CredentialStore.delete_credential(
                service_name, self.credentials, self.master_password, self.salt
            )
            self._refresh()
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _copy_item(self, text: str, label: str):
        self.session_manager.record_activity()
        if self.clipboard_manager:
            settings = SettingsManager.load_settings()
            self.clipboard_manager.copy_with_autoclear(text, settings['clipboard_clear_seconds'])
        else:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _open_url(self, url: str):
        self.session_manager.record_activity()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        webbrowser.open(url)

    # ------------------------------------------------------------------ content switching

    def _set_window_opacity(self, opaque: bool) -> None:
        """Window -alpha is global; over the dark terminal it lets other
        windows ghost through and ruins readability. Force the window fully
        opaque while the terminal is visible; restore the user's opacity for
        the vault view."""
        try:
            if opaque:
                self.root.wm_attributes('-alpha', 1.0)
            else:
                settings = SettingsManager.load_settings()
                self.root.wm_attributes('-alpha', float(settings.get('opacity', 0.95)))
        except Exception:
            pass

    def _switch_to_vault(self) -> None:
        """Show the vault content area, hide ZTerm."""
        if hasattr(self, "_zterm_frame"):
            self._zterm_frame.pack_forget()
        if hasattr(self, "_vault_frame"):
            self._vault_frame.pack(fill=BOTH, expand=True)
        self._set_window_opacity(opaque=False)

    def _switch_to_zterm(self) -> None:
        """Show the ZTerm panel, hide vault content."""
        if hasattr(self, "_vault_frame"):
            self._vault_frame.pack_forget()
        if hasattr(self, "_zterm_frame"):
            self._zterm_frame.pack(fill=BOTH, expand=True)
        self._set_window_opacity(opaque=True)

    # ------------------------------------------------------------------ nav actions
    def _show_all(self):
        self._view_mode = "all"
        self._tag_filter = None
        self._switch_to_vault()
        if self.search_var:
            self.search_var.set("")     # triggers _refresh
        else:
            self._refresh()

    def _show_favorites(self):
        self._view_mode = "favorites"
        self._tag_filter = None
        self._switch_to_vault()
        self._refresh()

    def _show_recent(self):
        self._view_mode = "recent"
        self._tag_filter = None
        self._switch_to_vault()
        self._refresh()

    def _show_zterm(self) -> None:
        self._switch_to_zterm()

    def _show_generator(self):
        self.session_manager.record_activity()
        show_password_generator(self.root)

    def _show_settings(self):
        self.session_manager.record_activity()
        show_settings_dialog(self.root, self.session_manager)

    def _check_health(self):
        self.session_manager.record_activity()
        if not self.credentials:
            messagebox.showinfo("No Credentials", "No credentials to analyse.")
            return

        from utils.password_strength import estimate_password_strength

        weak, dup_map, pwd_seen = [], {}, {}
        for svc, cred in self.credentials.items():
            score, lbl, _ = estimate_password_strength(cred.password)
            if score < 3:
                weak.append((svc, lbl))
            p = cred.password
            if p in pwd_seen:
                dup_map.setdefault(p, [pwd_seen[p]]).append(svc)
            else:
                pwd_seen[p] = svc

        total = len(self.credentials)
        issues = len(weak) + len(dup_map)
        score = max(0, 100 - issues * 10)

        dlg = ttk.Toplevel(self.root)
        dlg.title("Password Health")
        dlg.geometry("540x460")
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() // 2) - 270
        y = (dlg.winfo_screenheight() // 2) - 230
        dlg.geometry(f"540x460+{x}+{y}")

        f = ttk.Frame(dlg, padding=20)
        f.pack(fill=BOTH, expand=YES)

        ttk.Label(f, text="Password Health", font=("Segoe UI", 15, "bold")).pack(anchor=W, pady=(0, 15))

        score_color = "#388e3c" if score >= 80 else "#f57c00" if score >= 50 else "#d32f2f"
        sf = ttk.Labelframe(f, text="Overall Score", padding=12)
        sf.pack(fill=X, pady=(0, 12))
        ttk.Label(sf, text=f"{score}%", font=("Segoe UI", 22, "bold"),
                 foreground=score_color).pack()
        ttk.Label(sf, text=f"{total} credentials analysed",
                 font=("Segoe UI", 9), bootstyle="secondary").pack()

        wf = ttk.Labelframe(f, text=f"Weak Passwords ({len(weak)})", padding=12)
        wf.pack(fill=BOTH, expand=YES, pady=(0, 8))
        if weak:
            import tkinter as tk2
            cv = tk2.Canvas(wf, height=100, highlightthickness=0)
            sb = ttk.Scrollbar(wf, orient="vertical", command=cv.yview)
            sf2 = ttk.Frame(cv)
            sf2.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
            cv.create_window((0, 0), window=sf2, anchor="nw")
            cv.configure(yscrollcommand=sb.set)
            for svc, lbl in weak:
                ttk.Label(sf2, text=f"• {svc}: {lbl}", font=("Segoe UI", 9)).pack(anchor=W, padx=4, pady=1)
            cv.pack(side=LEFT, fill=BOTH, expand=YES)
            sb.pack(side=RIGHT, fill=Y)
        else:
            ttk.Label(wf, text="✓ No weak passwords found!", foreground="#388e3c").pack()

        df = ttk.Labelframe(f, text=f"Duplicate Passwords ({len(dup_map)})", padding=12)
        df.pack(fill=BOTH, expand=YES, pady=(0, 10))
        if dup_map:
            for services in dup_map.values():
                ttk.Label(df, text=f"• Shared by: {', '.join(services)}",
                         font=("Segoe UI", 9)).pack(anchor=W, padx=4, pady=1)
        else:
            ttk.Label(df, text="✓ No duplicate passwords found!", foreground="#388e3c").pack()

        ttk.Button(f, text="Close", command=dlg.destroy,
                  bootstyle="secondary", width=12).pack(pady=(5, 0))

    def _export_backup(self):
        self.session_manager.record_activity()
        ok, msg = BackupManager.export_credentials(
            self.credentials, self.master_password, self.salt, parent_window=self.root
        )
        if ok:
            messagebox.showinfo("Export OK", msg)
        elif msg != "Export cancelled.":
            messagebox.showerror("Export Failed", msg)

    def _import_backup(self):
        self.session_manager.record_activity()
        if self.credentials:
            if not messagebox.askyesno("Import Backup",
                                        "Import credentials from a backup file?\n"
                                        "Duplicates will be handled interactively.",
                                        parent=self.root):
                return

        ok, imported, msg = BackupManager.import_credentials(
            self.master_password, self.salt, parent_window=self.root
        )
        if not ok:
            if msg != "Import cancelled.":
                messagebox.showerror("Import Failed", msg)
            return

        if imported:
            merged, merge_msg = BackupManager.merge_credentials(
                self.credentials, imported, parent_window=self.root
            )
            if merge_msg == "Import cancelled.":
                return
            self.credentials = merged
            self._save_credentials()
            self._refresh()
            messagebox.showinfo("Import OK", merge_msg)

    def _change_master_password(self):
        self.session_manager.record_activity()

        dlg = ttk.Toplevel(self.root)
        dlg.title("Change Master Password")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.update_idletasks()
        w, h = 420, 340
        x = (dlg.winfo_screenwidth() // 2) - (w // 2)
        y = (dlg.winfo_screenheight() // 2) - (h // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")

        f = ttk.Frame(dlg, padding=25)
        f.pack(fill=BOTH, expand=YES)
        ttk.Label(f, text="Change Master Password",
                 font=("Segoe UI", 14, "bold")).pack(anchor=W, pady=(0, 20))

        ttk.Label(f, text="Current Password", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 4))
        cur_var = ttk.StringVar()
        ttk.Entry(f, textvariable=cur_var, show="•", font=("Segoe UI", 11)).pack(fill=X, pady=(0, 12))

        ttk.Label(f, text="New Password", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 4))
        new_var = ttk.StringVar()
        ttk.Entry(f, textvariable=new_var, show="•", font=("Segoe UI", 11)).pack(fill=X, pady=(0, 12))

        ttk.Label(f, text="Confirm New Password", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 4))
        conf_var = ttk.StringVar()
        ttk.Entry(f, textvariable=conf_var, show="•", font=("Segoe UI", 11)).pack(fill=X, pady=(0, 20))

        def do_change():
            cur, new, conf = cur_var.get(), new_var.get(), conf_var.get()
            if cur != self.master_password:
                messagebox.showerror("Error", "Incorrect current password!")
                return
            if new != conf:
                messagebox.showerror("Error", "New passwords do not match!")
                return
            valid, err = validate_password_strength(new, is_master=True)
            if not valid:
                messagebox.showerror("Weak Password", err)
                return
            try:
                new_salt = MasterPasswordStore.change_master_password(cur, new)
                CredentialStore.save_credentials(self.credentials, new, new_salt)
                self.master_password = new
                self.salt = new_salt
                messagebox.showinfo("Success", "Master password changed!")
                dlg.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed: {e}")

        bf = ttk.Frame(f)
        bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=dlg.destroy,
                  bootstyle="secondary", width=12).pack(side=RIGHT, padx=(10, 0))
        ttk.Button(bf, text="Change", command=do_change,
                  bootstyle="success", width=12).pack(side=RIGHT)

    # ------------------------------------------------------------------ session
    def _bind_activity(self):
        self.root.bind('<Motion>', lambda e: self.session_manager.record_activity())
        self.root.bind('<Button>', lambda e: self.session_manager.record_activity())
        self.root.bind('<Key>',   lambda e: self.session_manager.record_activity())
        self.root.bind('<Control-n>', lambda e: self._add_credential())
        self.root.bind('<Control-g>', lambda e: self._show_generator())
        self.root.bind('<Control-comma>', lambda e: self._show_settings())

    def _tick_timer(self):
        if not self.session_manager._running:
            if self.timer_label:
                self.timer_label.config(text="🔓 Auto-lock disabled")
            return
        remaining = self.session_manager.get_time_until_lock()
        m, s = divmod(remaining, 60)
        if self.timer_label:
            self.timer_label.config(text=f"Auto-locks in {m}:{s:02d}")
        self.root.after(1000, self._tick_timer)

    def _lock(self):
        self._cleanup()
        self.root.destroy()
        from ui.theme import create_themed_root
        from ui.login_window import LoginWindow
        root = create_themed_root()
        root.geometry("500x600")

        def on_login(password, salt):
            MainWindow(root, password, salt)

        LoginWindow(root, on_login)
        root.mainloop()

    def _auto_lock(self):
        messagebox.showwarning("Auto-Lock", "Session locked due to inactivity.")
        self._lock()

    def _cleanup(self):
        self.session_manager.stop()
        self.clipboard_manager.cleanup()
        if self.canvas:
            try:
                self.canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass
