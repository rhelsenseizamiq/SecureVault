"""
ZTerm SSH terminal panel — full-featured, embedded inside SecureVault.

Features
────────
  Sidebar
    • Treeview with group folders (click group header to expand/collapse)
    • Sessions shown under their group; ungrouped listed directly
    • Right-click menu: Connect · Duplicate Config · Edit · Change Color · Delete
    • Snippets panel with quick-send macros (collapsible)

  Tabs
    • Each SSH session opens as a notebook tab
    • Toolbar: Reconnect | Split → | Split ↓ | SFTP | Detach | Clone Tab | 💾 Log | ✕ Close
    • Split terminal: side-by-side or top/bottom — each pane = independent SSH connection
    • Detach: pops tab into a standalone Toplevel window
    • Clone Tab: opens a second tab for the same session (new connection)
    • Save Log: saves terminal text to a .txt file

  Other
    • Connection history (📊 History button) — last 500 sessions
    • SSH key management inside session dialog
    • Port forwarding + jump host support (configured per session)

Deletion fix
────────────
  Sessions are stored in a parallel list self._session_order so the
  Treeview iid maps directly to session name — no text parsing needed.
"""
import dataclasses
import logging
import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog
from typing import Callable, Dict, List, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from config import (DATA_DIR, ZTERM_RECONNECT_TRIES, ZTERM_RECONNECT_DELAYS)
from ui.zterm_session_dialog import ZTermSessionDialog
from zterm.history import ConnectionHistory
from zterm.session_store import SSHSession, ZTermSessionStore
from zterm.sftp_browser import SFTPBrowser
from zterm.snippets import Snippet, SnippetStore
from zterm.ssh_client import PARAMIKO_OK, SSHConnection
from zterm.terminal_widget import THEMES, TerminalWidget


# ── logging ──────────────────────────────────────────────────────────────────

def _make_log() -> logging.Logger:
    log_dir = Path(os.getenv("APPDATA", Path.home())) / "SecureVault"
    log_dir.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("zterm.panel")
    if not lg.handlers:
        fh = logging.FileHandler(log_dir / "zterm.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        lg.addHandler(fh)
        lg.setLevel(logging.DEBUG)
    return lg

log = _make_log()

_LABEL_COLORS = [
    ("Default", ""), ("Green", "#4e9a06"), ("Blue", "#3465a4"),
    ("Red", "#cc0000"), ("Yellow", "#c4a000"), ("Cyan", "#06989a"),
    ("Magenta", "#75507b"), ("Orange", "#e07000"),
]

# ── connect-via-jump-host helpers ─────────────────────────────────────────────
_JUMP_PREF_FILE = "zterm_jump.json"


def _jump_pref_load() -> str:
    """Last-used bastion session name (remembered across launches)."""
    import json
    try:
        p = DATA_DIR / _JUMP_PREF_FILE
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8")).get("session", "")
    except Exception:
        pass
    return ""


def _jump_pref_save(name: str) -> None:
    import json
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / _JUMP_PREF_FILE).write_text(
            json.dumps({"session": name}), encoding="utf-8")
    except Exception:
        pass


def _inject_jump(target: "SSHSession", *, host: str, port: int, user: str,
                 vault_ref: str = "", key_path: str = "") -> "SSHSession":
    """Return `target` routed through a jump host with the given login details."""
    if key_path:
        return dataclasses.replace(
            target, jump_host=host, jump_port=port, jump_user=user,
            jump_key_path=key_path, jump_vault_ref="")
    return dataclasses.replace(
        target, jump_host=host, jump_port=port, jump_user=user,
        jump_vault_ref=vault_ref, jump_key_path="")


def _jump_fields_for(bastion: "SSHSession", cred_name: str, get_creds):
    """Compute (user, vault_ref, key_path) for tunnelling through `bastion` using
    the chosen vault credential `cred_name` (falls back to the bastion's own)."""
    creds = get_creds() or {}
    cname = cred_name or bastion.vault_ref
    cred = creds.get(cname)
    user = (getattr(cred, "username", "") if cred else "") or bastion.username
    if not cname and bastion.auth_type == "key":      # key-only bastion
        return user, "", bastion.key_path
    return user, cname, ""


# ============================================================================
#  _Tooltip — tiny hover tooltip so icon-only buttons stay discoverable
# ============================================================================

class _Tooltip:
    def __init__(self, widget, text: str) -> None:
        self._widget = widget
        self._text   = text
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip or not self._text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._text,
                 bg="#2a2a40", fg="#e4e7ef",
                 font=("Segoe UI", 8), padx=6, pady=2,
                 relief="solid", borderwidth=1).pack()

    def _hide(self, _event=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ============================================================================
#  _RetryConnectDialog — shown when a connection fails (wrong username, etc.)
# ============================================================================

class _RetryConnectDialog(ttk.Toplevel):
    """
    On connect failure, ask whether to retry with a different username/password,
    and/or route the retry through a jump host (bastion).
    self.result = (username, password, jump_name) to retry, or None to give up.
    Password blank → keep the existing one. jump_name "" → no jump host.
    """
    def __init__(self, parent, host: str, port: int, username: str, error: str,
                 get_credentials: Optional[Callable[[], dict]] = None,
                 bastion_names: Optional[list] = None,
                 default_bastion: str = ""):
        super().__init__(parent)
        self.title("Connection Failed")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._creds = (get_credentials or (lambda: {}))()
        self._bastions = bastion_names or []

        f = ttk.Frame(self, padding=18)
        f.pack(fill=BOTH, expand=YES)

        ttk.Label(f, text="⚠  Could not connect",
                  font=("Segoe UI", 12, "bold"),
                  bootstyle="danger").pack(anchor=W)
        ttk.Label(f, text=f"{host}:{port}",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(2, 6))

        # error text (wrapped, truncated)
        msg = (error or "")[:200]
        ttk.Label(f, text=msg, font=("Segoe UI", 8),
                  bootstyle="secondary", wraplength=360,
                  justify=LEFT).pack(anchor=W, pady=(0, 10))

        ttk.Label(f, text="This server may use a different username. "
                          "Try again with:",
                  font=("Segoe UI", 9), wraplength=360,
                  justify=LEFT).pack(anchor=W, pady=(0, 8))

        ttk.Label(f, text="Username", font=("Segoe UI", 9),
                  bootstyle="secondary").pack(anchor=W)
        self._user = ttk.StringVar(value=username)
        ue = ttk.Entry(f, textvariable=self._user, width=34)
        ue.pack(fill=X, pady=(2, 8))

        # Password source: pick from the SecureVault store …
        ttk.Label(f, text="Password from vault", font=("Segoe UI", 9),
                  bootstyle="secondary").pack(anchor=W)
        self._vault = ttk.StringVar(value="(enter manually below)")
        vault_names = ["(enter manually below)"] + sorted(self._creds.keys())
        self._vault_cb = ttk.Combobox(f, textvariable=self._vault,
                                      values=vault_names, state="readonly", width=32)
        self._vault_cb.pack(fill=X, pady=(2, 8))
        self._vault_cb.bind("<<ComboboxSelected>>", self._on_vault_pick)

        # … or type one manually
        ttk.Label(f, text="Password (manual — blank keeps current)",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W)
        self._pass = ttk.StringVar()
        self._pass_entry = ttk.Entry(f, textvariable=self._pass, show="•", width=34)
        self._pass_entry.pack(fill=X, pady=(2, 12))

        # ── Optional: retry through a jump host (bastion) ──────────────────
        ttk.Separator(f).pack(fill=X, pady=(0, 8))
        self._use_jump = ttk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text="No direct route? Connect via jump host",
            variable=self._use_jump, bootstyle="info-round-toggle",
            command=self._on_jump_toggle).pack(anchor=W)
        self._jump_name = ttk.StringVar(value=default_bastion)
        self._jump_cb = ttk.Combobox(f, textvariable=self._jump_name,
                                     values=self._bastions, state="disabled", width=32)
        self._jump_cb.pack(fill=X, pady=(4, 14))

        bf = ttk.Frame(f)
        bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=self.destroy,
                   bootstyle="secondary", width=11).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(bf, text="Retry", command=self._retry,
                   bootstyle="primary", width=11).pack(side=RIGHT)

        ue.focus_set()
        ue.select_range(0, "end")
        ue.bind("<Return>", lambda e: self._retry())

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x,0)}+{max(y,0)}")
        self.wait_window()

    def _on_jump_toggle(self) -> None:
        self._jump_cb.configure(state="readonly" if self._use_jump.get() else "disabled")

    def _on_vault_pick(self, _event=None) -> None:
        """Picking a vault entry disables manual password entry."""
        chosen = self._vault.get()
        if chosen and not chosen.startswith("("):
            self._pass.set("")
            self._pass_entry.configure(state="disabled")
            # A vault credential is a user+pass pair — fill the username too
            # (still editable afterwards if the server uses a different login).
            cred = self._creds.get(chosen)
            cu = getattr(cred, "username", "") if cred else ""
            if cu:
                self._user.set(cu)
        else:
            self._pass_entry.configure(state="normal")

    def _retry(self) -> None:
        user = self._user.get().strip()
        if not user:
            return
        # Resolve password: vault selection wins, else manual entry, else blank
        chosen = self._vault.get()
        if chosen and not chosen.startswith("("):
            cred = self._creds.get(chosen)
            password = getattr(cred, "password", "") if cred else ""
        else:
            password = self._pass.get()
        jump_name = self._jump_name.get().strip() if self._use_jump.get() else ""
        self.result = (user, password, jump_name)
        self.destroy()


# ============================================================================
#  _TerminalPane — one SSH connection + terminal widget
# ============================================================================

class _TerminalPane(tk.Frame):
    BG = "#0a0a14"

    # Auto-close an SSH session after this many seconds with no input/output.
    IDLE_LIMIT_SEC  = 600     # 10 minutes
    IDLE_POLL_MS    = 30_000  # check every 30 s

    def __init__(self, parent, session: SSHSession, password: str,
                 status_cb: Optional[Callable[[str], None]] = None,
                 history: Optional[ConnectionHistory] = None,
                 get_credentials: Optional[Callable[[], dict]] = None,
                 get_sessions: Optional[Callable[[], dict]] = None, **kw):
        super().__init__(parent, bg=self.BG, **kw)
        self._session   = session
        self._password  = password
        self._status_cb = status_cb
        self._history   = history
        self._get_creds = get_credentials or (lambda: {})
        self._get_sessions = get_sessions or (lambda: {})
        self._hist_id:  Optional[str] = None
        self._ssh       = SSHConnection()
        self._idle_after = None          # pending idle-check after() id

        # Auto-reconnect state
        self._user_closing   = False     # True → close was intentional, don't reconnect
        self._was_connected  = False     # only auto-reconnect a session that connected once
        self._reconnect_n    = 0         # attempts used in the current drop

        self._term = TerminalWidget(self)
        self._term.pack(fill=BOTH, expand=True)

    def connect(self) -> None:
        threading.Thread(target=self._do_connect,
                         daemon=True, name="zterm-connect").start()

    def _resolve_jump_pass(self, s) -> str:
        """Look up the jump host's password from the vault credential it references."""
        if s.jump_host and s.jump_vault_ref:
            cred = (self._get_creds() or {}).get(s.jump_vault_ref)
            return getattr(cred, "password", "") if cred else ""
        return ""

    def _do_connect(self) -> None:
        s = self._session
        jump_pass = self._resolve_jump_pass(s)   # was never resolved before (bug)

        try:
            self._ssh.connect(
                host=s.host, port=s.port, username=s.username,
                password=self._password, key_path=s.key_path,
                jump_host=s.jump_host, jump_port=s.jump_port,
                jump_user=s.jump_user, jump_password=jump_pass,
                jump_key_path=s.jump_key_path,
                port_forwards=s.port_forwards,
            )
            if self._history:
                self._hist_id = self._history.log_start(
                    s.name, s.host, s.port, s.username)
            self.after(0, self._on_connected)
        except Exception as exc:
            msg = str(exc)
            log.error("Connect %s:%s — %s", s.host, s.port, msg)
            self.after(0, lambda m=msg: self._on_fail(m))

    def _on_connected(self) -> None:
        s = self._session
        self._was_connected = True
        self._user_closing  = False  # live again → future unexpected drops reconnect
        self._reconnect_n   = 0      # a fresh successful connect clears the drop counter
        lbl = f"✓  {s.username}@{s.host}:{s.port}"
        if s.jump_host:
            lbl += f"  (via {s.jump_host})"
        log.info(lbl)
        if self._status_cb:
            self._status_cb(lbl)
        self._term.connect_queue(self._ssh.queue, self._ssh.send, self._on_closed)
        self._term.set_resize_callback(self._ssh.resize)
        # KEY FIX: sync pyte screen + SSH PTY to actual widget size.
        # The <Configure>/resize event fires before SSH connects, so _resize_cb
        # was None then. Now that it's set, force a size sync immediately.
        self._term.after(100, self._term.sync_size)
        self._start_idle_monitor()

    def _on_fail(self, err: str) -> None:
        if self._status_cb:
            self._status_cb(f"✗  Failed — {err}")
        # Offer to retry with a different username / password, and/or route the
        # retry through a jump host (bastion) — e.g. when there's no direct path.
        all_sessions = self._get_sessions() or {}
        bastions = sorted(n for n, s in all_sessions.items()
                          if s.host != self._session.host)   # can't jump to self
        default_bastion = _jump_pref_load()
        if default_bastion not in bastions:
            default_bastion = ("ANSIBLE_Tower" if "ANSIBLE_Tower" in bastions
                               else (bastions[0] if bastions else ""))
        dlg = _RetryConnectDialog(
            self.winfo_toplevel(),
            host=self._session.host,
            port=self._session.port,
            username=self._session.username,
            error=err,
            get_credentials=self._get_creds,
            bastion_names=bastions,
            default_bastion=default_bastion,
        )
        if dlg.result:
            new_user, new_pass, jump_name = dlg.result
            self._session = dataclasses.replace(self._session, username=new_user)
            if new_pass:                       # blank = keep current password
                self._password = new_pass
            via = ""
            bastion = all_sessions.get(jump_name) if jump_name else None
            if bastion and bastion.host != self._session.host:
                juser, jref, jkey = _jump_fields_for(bastion, "", self._get_creds)
                self._session = _inject_jump(
                    self._session, host=bastion.host, port=bastion.port,
                    user=juser, vault_ref=jref, key_path=jkey)
                _jump_pref_save(jump_name)
                via = f" via {bastion.host}"
            self._ssh = SSHConnection()        # fresh connection object
            self._term.reset()
            if self._status_cb:
                self._status_cb(f"Reconnecting as {new_user}{via} …")
            self.connect()

    def _on_closed(self) -> None:
        if self._hist_id and self._history:
            self._history.log_end(self._hist_id)
            self._hist_id = None
        # Unexpected drop (not a user close, not idle close) → auto-reconnect.
        if (not self._user_closing and self._was_connected
                and self._reconnect_n < ZTERM_RECONNECT_TRIES
                and self.winfo_exists()):
            self._reconnect_n += 1
            delay = ZTERM_RECONNECT_DELAYS[
                min(self._reconnect_n - 1, len(ZTERM_RECONNECT_DELAYS) - 1)]
            try:
                self._term._text.insert(
                    "end",
                    f"\n\n— Connection lost, reconnecting "
                    f"({self._reconnect_n}/{ZTERM_RECONNECT_TRIES}) in {delay}s… —\n")
                self._term._text.see("end")
            except Exception:
                pass
            if self._status_cb:
                self._status_cb(
                    f"Reconnecting ({self._reconnect_n}/{ZTERM_RECONNECT_TRIES})…")
            self.after(delay * 1000, self._auto_reconnect)
            return
        if (not self._user_closing and self._was_connected
                and self._reconnect_n >= ZTERM_RECONNECT_TRIES):
            try:
                self._term._text.insert("end", "\n— Reconnect failed —\n")
                self._term._text.see("end")
            except Exception:
                pass
        if self._status_cb:
            self._status_cb("Disconnected")

    def _auto_reconnect(self) -> None:
        """Re-establish a dropped session (fresh shell, same target)."""
        if self._user_closing or not self.winfo_exists():
            return
        self._ssh = SSHConnection()      # fresh connection object
        self._term.reset()
        self.connect()

    def reconnect(self) -> None:
        self._reconnect_n = 0            # manual reconnect resets the drop counter
        # Mark closing so the OLD connection's close event doesn't ALSO trigger
        # an auto-reconnect; _on_connected clears it once we're live again.
        self._user_closing = True
        self._ssh.close()
        self._term.reset()
        self.connect()

    def adopt(self, ssh: SSHConnection, hist_id=None, state=None) -> None:
        """
        Take over an already-connected SSHConnection WITHOUT reconnecting.
        Used by Detach so the live shell (cwd, running processes) is preserved
        rather than re-authenticating into a fresh session. `state` (from the
        previous pane's terminal.export_state) restores the full scrollback and
        on-screen content so detach/attach never resets the display.
        """
        self._ssh = ssh
        self._hist_id = hist_id
        self._was_connected = True       # adopted conn is live → eligible for reconnect
        self._reconnect_n   = 0
        if state:
            try:
                self._term.import_state(state)
            except Exception:
                log.exception("import_state failed")
        s = self._session
        lbl = f"✓  {s.username}@{s.host}:{s.port}"
        if s.jump_host:
            lbl += f"  (via {s.jump_host})"
        if self._status_cb:
            self._status_cb(lbl)
        self._term.connect_queue(ssh.queue, ssh.send, self._on_closed)
        self._term.set_resize_callback(ssh.resize)
        self._term.after(100, self._term.sync_size)
        self._start_idle_monitor()

    # ── idle auto-close ─────────────────────────────────────────────────────
    def _start_idle_monitor(self) -> None:
        self._cancel_idle_monitor()
        self._idle_after = self.after(self.IDLE_POLL_MS, self._check_idle)

    def _cancel_idle_monitor(self) -> None:
        if self._idle_after is not None:
            try:
                self.after_cancel(self._idle_after)
            except Exception:
                pass
            self._idle_after = None

    def _check_idle(self) -> None:
        self._idle_after = None
        if not self.winfo_exists() or not self._ssh.is_active:
            return   # gone or already disconnected → stop polling
        if self._term.idle_seconds() >= self.IDLE_LIMIT_SEC:
            mins = self.IDLE_LIMIT_SEC // 60
            log.info("Idle timeout (%d min) — closing %s:%s",
                     mins, self._session.host, self._session.port)
            try:
                self._term._text.insert(
                    "end", f"\n\n— Session auto-closed after {mins} min idle —\n")
                self._term._text.see("end")
            except Exception:
                pass
            if self._status_cb:
                self._status_cb("Disconnected (idle timeout)")
            self.close()
            return
        self._start_idle_monitor()

    def release(self):
        """
        Hand off the live connection so this pane's close()/destroy won't
        terminate it. Returns (ssh, hist_id, state); the terminal stops
        consuming. `state` snapshots the display so the receiving pane can
        restore the full scrollback (detach/attach without reset).
        """
        self._cancel_idle_monitor()      # detached conn shouldn't be idle-killed
        self._user_closing = True        # handing off → the close() must not reconnect
        state = None
        try:
            state = self._term.export_state()
        except Exception:
            log.exception("export_state failed")
        ssh, hist_id = self._ssh, self._hist_id
        self._term.disconnect()          # stop draining the shared queue
        self._ssh = SSHConnection()      # dummy → close() becomes a no-op
        self._hist_id = None
        return ssh, hist_id, state

    def close(self) -> None:
        self._user_closing = True        # intentional close → no auto-reconnect
        self._cancel_idle_monitor()
        if self._hist_id and self._history:
            self._history.log_end(self._hist_id)
        self._ssh.close()

    def destroy(self) -> None:
        self._cancel_idle_monitor()
        super().destroy()

    def save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save Terminal Log",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=f"{self._session.name}_log.txt",
            parent=self.winfo_toplevel(),
        )
        if path:
            content = self._term._text.get("1.0", "end")
            Path(path).write_text(content, encoding="utf-8")
            messagebox.showinfo("Saved", f"Log saved to:\n{path}",
                                parent=self.winfo_toplevel())

    def open_sftp(self):
        return self._ssh.open_sftp()

    @property
    def is_active(self) -> bool:
        return self._ssh.is_active

    @property
    def terminal(self) -> TerminalWidget:
        return self._term


# ============================================================================
#  _SplitPaneWrapper — TerminalPane + close-button header (shown in split view)
# ============================================================================

class _SplitPaneWrapper(tk.Frame):
    """Wraps _TerminalPane with a mini header containing session label + ✕ button."""

    BG     = "#0a0a14"
    HDR_BG = "#131320"

    def __init__(self, parent, session: SSHSession, password: str,
                 status_cb: Optional[Callable[[str], None]],
                 history: Optional[ConnectionHistory],
                 on_close_pane: Callable[[], None],
                 get_credentials: Optional[Callable[[], dict]] = None,
                 get_sessions: Optional[Callable[[], dict]] = None,
                 adopt_ssh: Optional["SSHConnection"] = None,
                 adopt_state: Optional[dict] = None, **kw):
        super().__init__(parent, bg=self.BG, **kw)

        # Header (with ✕) is built but NOT packed until the pane is part of a
        # split. A single pane shows no header; splitting reveals it. This lets
        # us keep ONE persistent connection per pane — splitting never recreates
        # or drops an existing session.
        self._hdr = tk.Frame(self, bg=self.HDR_BG, height=22)
        self._hdr.pack_propagate(False)
        tk.Label(self._hdr,
                 text=f"  {session.username}@{session.host}:{session.port}",
                 bg=self.HDR_BG, fg="#7d8fa6",
                 font=("Segoe UI", 8)).pack(side=LEFT, pady=2)
        self._close_btn = tk.Button(
            self._hdr, text=" ✕ ", bg=self.HDR_BG, fg="#ef2929",
            activebackground="#550000", activeforeground="#fff",
            relief="flat", font=("Segoe UI", 8), cursor="hand2",
            command=on_close_pane)
        self._close_btn.pack(side=RIGHT, padx=3)

        self._pane = _TerminalPane(self, session, password, status_cb, history,
                                   get_credentials=get_credentials,
                                   get_sessions=get_sessions)
        self._pane.pack(fill=BOTH, expand=True)
        if adopt_ssh is not None:
            # take over a live connection (Detach) + restore its display
            self._pane.adopt(adopt_ssh, state=adopt_state)
        else:
            self._pane.connect()

    def release(self):
        return self._pane.release()

    def show_header(self) -> None:
        # Pack the header ABOVE the terminal (before=pane).
        self._hdr.pack(fill=X, before=self._pane)

    def hide_header(self) -> None:
        self._hdr.pack_forget()

    def reconnect(self)                -> None:     self._pane.reconnect()
    def close(self)                    -> None:     self._pane.close()
    def open_sftp(self):                            return self._pane.open_sftp()
    @property
    def is_active(self)                -> bool:     return self._pane.is_active
    @property
    def terminal(self) -> TerminalWidget:            return self._pane.terminal


# ============================================================================
#  _SessionTab — one notebook tab with split-able panes
# ============================================================================

class _SessionTab(tk.Frame):
    BG = "#0a0a14"

    def __init__(self, parent, session: SSHSession, password: str,
                 on_close: Callable[[], None],
                 open_tab_cb: Optional[Callable] = None,
                 history: Optional[ConnectionHistory] = None,
                 attach_cb: Optional[Callable] = None,   # set = detached mode
                 get_credentials: Optional[Callable[[], dict]] = None,
                 adopt_ssh: Optional["SSHConnection"] = None,  # detach: take over live conn
                 adopt_state: Optional[dict] = None,           # detach: restore display
                 panel: Optional["ZTermPanel"] = None,         # for broadcast fan-out
                 **kw):
        super().__init__(parent, bg=self.BG, **kw)
        self._session     = session
        self._password    = password
        self._on_close    = on_close
        self._open_tab_cb = open_tab_cb
        self._history     = history
        self._attach_cb   = attach_cb        # None → show Detach, else → show Attach
        self._get_creds   = get_credentials or (lambda: {})
        self._panel       = panel            # ZTermPanel (broadcast coordinator)
        self._panes: List[_SplitPaneWrapper] = []   # every pane (1 or more)
        self._sftp_open   = False

        self._build()
        # first pane (adopts a live conn + restores its display on detach)
        self._add_pane(adopt_ssh=adopt_ssh, adopt_state=adopt_state)

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        # ── Toolbar (icon-only with tooltips → never overflows) ──────────────
        tb = tk.Frame(self, bg="#070710")
        tb.pack(fill=X)

        def b(icon, cmd, tip, style="secondary-outline"):
            btn = ttk.Button(tb, text=icon, command=cmd,
                             bootstyle=style, padding=(5, 2), width=2)
            _Tooltip(btn, tip)
            return btn

        b("⟳",  self._reconnect, "Reconnect").pack(side=LEFT, padx=(4, 1), pady=3)
        b("⊞",  self._split_h,   "Split right (side-by-side)").pack(side=LEFT, padx=1, pady=3)
        b("⊟",  self._split_v,   "Split down (stacked)").pack(side=LEFT, padx=1, pady=3)
        b("📂", self._toggle_sftp, "SFTP file browser", "info-outline").pack(side=LEFT, padx=1, pady=3)
        b("⧉",  self._clone_tab, "Clone tab (new connection)").pack(side=LEFT, padx=1, pady=3)
        b("💾", self._save_log,  "Save terminal log").pack(side=LEFT, padx=1, pady=3)
        self._theme_btn = b("🎨", self._show_theme_menu, "Colour theme")
        self._theme_btn.pack(side=LEFT, padx=1, pady=3)

        if self._attach_cb:
            b("⤵", self._attach_cb, "Attach back to main window", "success-outline").pack(side=LEFT, padx=1, pady=3)
        else:
            b("⤴", self._detach, "Detach to separate window", "warning-outline").pack(side=LEFT, padx=1, pady=3)

        b("✕", self._close, "Close tab", "danger-outline").pack(side=RIGHT, padx=(1, 4), pady=3)

        # Status label expands to fill the gap and truncates instead of pushing
        # buttons off-screen at small widths.
        self._status_var = tk.StringVar(value="Connecting …")
        tk.Label(tb, textvariable=self._status_var,
                 bg="#070710", fg="#7d8fa6",
                 font=("Segoe UI", 8), anchor=W).pack(
                     side=LEFT, padx=8, fill=X, expand=True)

        # ── Content area: outer (vertical) = terminals | SFTP ───────────────
        self._outer = tk.PanedWindow(self, orient=VERTICAL,
                                     bg=self.BG, sashrelief=FLAT,
                                     sashwidth=5, sashpad=0)
        self._outer.pack(fill=BOTH, expand=True)

        # Inner (horizontal / vertical depending on split orientation)
        self._inner = tk.PanedWindow(self._outer, orient=HORIZONTAL,
                                     bg=self.BG, sashrelief=FLAT,
                                     sashwidth=5, sashpad=0)
        self._outer.add(self._inner, stretch="always", minsize=80)

        self._sftp_widget = SFTPBrowser(self._outer)

    # ------------------------------------------------------------------ panes

    def _add_pane(self, adopt_ssh: Optional["SSHConnection"] = None,
                  adopt_state: Optional[dict] = None) -> "_SplitPaneWrapper":
        """
        Add a pane. Every pane is a _SplitPaneWrapper with a hidden header;
        the header (with ✕) is only shown once 2+ panes exist. Connections are
        never recreated — splitting keeps every existing session alive.
        When adopt_ssh is given (Detach), the pane takes over that live
        connection instead of opening a new one, and adopt_state restores its
        scrollback/display.
        """
        wrapper = _SplitPaneWrapper(
            self._inner, self._session, self._password,
            status_cb=self._status_var.set,
            history=self._history,
            on_close_pane=lambda: None,   # real handler set just below
            get_credentials=self._get_creds,
            get_sessions=(lambda: self._panel._sessions if self._panel else {}),
            adopt_ssh=adopt_ssh,
            adopt_state=adopt_state,
        )
        # Bind the close button to remove THIS wrapper
        wrapper._close_btn.configure(
            command=lambda w=wrapper: self._remove_pane(w))
        self._inner.add(wrapper, stretch="always", minsize=80)
        self._panes.append(wrapper)
        self._update_headers()
        return wrapper

    def _remove_pane(self, wrapper: "_SplitPaneWrapper") -> None:
        """Close one pane. Closing the last pane closes the whole tab."""
        if len(self._panes) <= 1:
            self._close()
            return
        wrapper.close()
        try:
            self._inner.remove(wrapper)
            wrapper.destroy()
        except Exception:
            pass
        if wrapper in self._panes:
            self._panes.remove(wrapper)
        self._update_headers()

    def _update_headers(self) -> None:
        """Show per-pane ✕ headers only when there is more than one pane."""
        if len(self._panes) > 1:
            for p in self._panes:
                p.show_header()
        else:
            for p in self._panes:
                p.hide_header()

    # ------------------------------------------------------------------ active pane

    def _active_pane(self):
        """Return the focused pane wrapper (falls back to the first)."""
        w = self.focus_get()
        if w:
            for p in self._panes:
                if str(w).startswith(str(p)):
                    return p
        return self._panes[0] if self._panes else None

    def _active_terminal(self) -> Optional[TerminalWidget]:
        p = self._active_pane()
        return p.terminal if p else None

    # ------------------------------------------------------------------ toolbar actions

    def _reconnect(self) -> None:
        p = self._active_pane()
        if p:
            p.reconnect()

    def _split_h(self) -> None:
        self._inner.configure(orient=HORIZONTAL)
        self._add_pane()

    def _split_v(self) -> None:
        self._inner.configure(orient=VERTICAL)
        self._add_pane()

    def _toggle_sftp(self) -> None:
        if self._sftp_open:
            self._outer.remove(self._sftp_widget)
            self._sftp_widget.detach()
            self._sftp_open = False
            return
        src = self._active_pane()
        if not src or not src.is_active:
            messagebox.showwarning("Not Connected", "Connect to a server first.",
                                   parent=self.winfo_toplevel())
            return
        sftp = src.open_sftp()
        if not sftp:
            messagebox.showerror("SFTP Error", "Could not open SFTP channel.",
                                 parent=self.winfo_toplevel())
            return
        self._outer.add(self._sftp_widget, stretch="always", minsize=120)
        self._sftp_widget.set_sftp(sftp)
        self._sftp_open = True

    def _clone_tab(self) -> None:
        if self._open_tab_cb:
            self._open_tab_cb(self._session, self._password)

    def _detach(self) -> None:
        # Move the LIVE connection into the new window — do NOT reconnect.
        active = self._active_pane()
        if active is None:
            return
        ssh, _hist, state = active.release()   # hand off live SSH + its display

        top = tk.Toplevel(self.winfo_toplevel())
        top.title(f"ZTerm  —  {self._session.name}  "
                  f"({self._session.username}@{self._session.host})")
        top.geometry("960x640")
        top.configure(bg=self.BG)
        try:
            top.state("zoomed")
        except Exception:
            pass

        holder = {}

        # Attach: move the live connection back into a main-window tab (no reconnect)
        def _do_attach():
            d = holder.get("tab")
            ssh_back = None
            state_back = None
            if d is not None:
                a = d._active_pane()
                if a is not None:
                    ssh_back, _, state_back = a.release()
            top.destroy()
            if self._open_tab_cb:
                self._open_tab_cb(self._session, self._password,
                                  ssh_back, state_back)

        detached = _SessionTab(
            top,
            session     = self._session,
            password    = self._password,
            on_close    = top.destroy,
            open_tab_cb = self._open_tab_cb,
            history     = self._history,
            attach_cb   = _do_attach,
            get_credentials = self._get_creds,
            adopt_ssh   = ssh,             # take over the live connection
            adopt_state = state,           # restore its scrollback/display
        )
        holder["tab"] = detached
        detached.pack(fill=BOTH, expand=True)
        top.update_idletasks()
        top.protocol("WM_DELETE_WINDOW", top.destroy)

        # Remove the now-released pane from this tab (closes the tab if it was
        # the only pane). The released connection lives on in the new window.
        self._remove_pane(active)

    def _save_log(self) -> None:
        t = self._active_terminal()
        if t:
            path = filedialog.asksaveasfilename(
                title="Save Terminal Log",
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("All", "*.*")],
                initialfile=f"{self._session.name}_log.txt",
                parent=self.winfo_toplevel(),
            )
            if path:
                from pathlib import Path
                content = t._text.get("1.0", "end")
                Path(path).write_text(content, encoding="utf-8")

    def _show_theme_menu(self) -> None:
        m = tk.Menu(self, tearoff=0,
                    bg="#1e1e2e", fg="#d3d7cf",
                    activebackground="#175ddc", activeforeground="#fff",
                    relief="flat")
        for name in THEMES:
            m.add_command(
                label=f"  {name}",
                command=lambda n=name: self._apply_theme(n),
            )
        try:
            btn = self._theme_btn
            m.post(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
        except Exception:
            m.post(self.winfo_rootx() + 200, self.winfo_rooty() + 30)

    def _apply_theme(self, name: str) -> None:
        """Apply a colour theme to every terminal pane in this tab."""
        for p in self._panes:
            p.terminal.set_theme(name)

    def _close(self) -> None:
        for p in self._panes:
            p.close()
        self._on_close()

    def destroy(self) -> None:
        for p in self._panes:
            try: p.close()
            except Exception: pass
        super().destroy()


# ============================================================================
#  _HistoryWindow — connection history viewer
# ============================================================================

class _HistoryWindow(ttk.Toplevel):
    def __init__(self, parent, history: ConnectionHistory):
        super().__init__(parent)
        self.title("ZTerm — Connection History")
        self.geometry("760x420")
        self.transient(parent)

        f = ttk.Frame(self, padding=12)
        f.pack(fill=BOTH, expand=YES)
        ttk.Label(f, text="Connection History",
                  font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 8))

        cols = ("session", "host", "user", "started", "ended", "duration")
        tree = ttk.Treeview(f, columns=cols, show="headings", selectmode="browse")
        for col, width, label in [
            ("session",  140, "Session"),
            ("host",     150, "Host"),
            ("user",      90, "User"),
            ("started",  145, "Started"),
            ("ended",    145, "Ended"),
            ("duration",  80, "Duration"),
        ]:
            tree.heading(col, text=label, anchor=W)
            tree.column(col, width=width, anchor=W)

        vsb = ttk.Scrollbar(f, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        tree.pack(fill=BOTH, expand=True)

        for e in history.load():
            tree.insert("", "end", values=(
                e.session_name, f"{e.host}:{e.port}", e.username,
                e.started, e.ended, e.fmt_duration(),
            ))

        ttk.Button(f, text="Close", command=self.destroy,
                   bootstyle="secondary", width=10).pack(pady=(8, 0))


# ============================================================================
#  _SnippetEditor — add / edit snippet
# ============================================================================

class _SnippetEditor(ttk.Toplevel):
    def __init__(self, parent, on_save: Callable, snippet: Optional[Snippet] = None):
        super().__init__(parent)
        self.title("Edit Snippet" if snippet else "New Snippet")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        f = ttk.Frame(self, padding=16)
        f.pack(fill=BOTH, expand=YES)

        ttk.Label(f, text="Name:", font=("Segoe UI", 9)).pack(anchor=W)
        self._name = ttk.StringVar(value=snippet.name if snippet else "")
        ttk.Entry(f, textvariable=self._name, width=36).pack(fill=X, pady=(3, 8))

        ttk.Label(f, text="Command:", font=("Segoe UI", 9)).pack(anchor=W)
        self._cmd = ttk.StringVar(value=snippet.command if snippet else "")
        ttk.Entry(f, textvariable=self._cmd, width=36).pack(fill=X, pady=(3, 12))

        bf = ttk.Frame(f); bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=self.destroy,
                   bootstyle="secondary", width=9).pack(side=RIGHT, padx=(4, 0))
        ttk.Button(bf, text="Save", bootstyle="primary", width=9,
                   command=lambda: (on_save(Snippet(self._name.get().strip(),
                                                    self._cmd.get().strip())),
                                   self.destroy())).pack(side=RIGHT)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.wait_window()


# ============================================================================
#  _BastionChooser — pick a jump host for "Connect via jump host"
# ============================================================================

class _BastionChooser(ttk.Toplevel):
    """Modal: pick the jump host session AND which vault credential to log into it
    with. self.result = (bastion_name, cred_name) or None if cancelled."""

    def __init__(self, parent, target_name: str, bastions: list, default: str,
                 sessions: dict, creds: dict):
        super().__init__(parent)
        self.title("Connect via jump host")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result = None
        self._sessions = sessions
        self._cred_names = sorted(creds.keys())

        f = ttk.Frame(self, padding=18)
        f.pack(fill=BOTH, expand=YES)
        ttk.Label(f, text=f"Connect to “{target_name}” through a jump host:",
                  font=("Segoe UI", 10)).pack(anchor=W, pady=(0, 8))

        ttk.Label(f, text="Jump host (bastion)", font=("Segoe UI", 9),
                  bootstyle="secondary").pack(anchor=W)
        self._name = ttk.StringVar(value=default)
        cb = ttk.Combobox(f, textvariable=self._name, values=bastions,
                          state="readonly", width=36)
        cb.pack(fill=X, pady=(2, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._sync_cred_default())

        ttk.Label(f, text="Log into the jump host with credential", font=("Segoe UI", 9),
                  bootstyle="secondary").pack(anchor=W)
        self._cred = ttk.StringVar()
        self._cred_cb = ttk.Combobox(f, textvariable=self._cred,
                                     values=self._cred_names, state="readonly", width=36)
        self._cred_cb.pack(fill=X, pady=(2, 4))
        ttk.Label(f, text="Tip: this is the password for the JUMP host itself "
                          "(not the target server).",
                  font=("Segoe UI", 8), bootstyle="secondary",
                  wraplength=320, justify=LEFT).pack(anchor=W, pady=(0, 12))
        self._sync_cred_default()

        bf = ttk.Frame(f)
        bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=self.destroy,
                   bootstyle="secondary", width=11).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(bf, text="Connect", command=self._ok,
                   bootstyle="primary", width=11).pack(side=RIGHT)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.wait_window()

    def _sync_cred_default(self):
        """Default the credential to the chosen bastion's own vault_ref."""
        b = self._sessions.get(self._name.get())
        ref = getattr(b, "vault_ref", "") if b else ""
        if ref in self._cred_names:
            self._cred.set(ref)
        elif self._cred_names and not self._cred.get():
            self._cred.set(self._cred_names[0])

    def _ok(self):
        name = self._name.get().strip()
        if name:
            self.result = (name, self._cred.get().strip())
        self.destroy()


# ============================================================================
#  ZTermPanel — full sidebar + notebook
# ============================================================================

class ZTermPanel(tk.Frame):

    SBG    = "#0d0d1a"   # sidebar bg
    ACCENT = "#175ddc"
    TEXT   = "#d3d7cf"
    TSEC   = "#7d8fa6"
    IBORDER= "#2e3245"
    ITEM_BG= "#1a1a2e"   # search box / input bg

    def __init__(self, parent, get_credentials: Callable[[], dict],
                 update_credential_password: Optional[Callable[[str, str], bool]] = None,
                 **kw):
        super().__init__(parent, bg=self.SBG, **kw)
        self._get_creds = get_credentials
        self._update_cred_pw = update_credential_password
        self._store     = ZTermSessionStore(DATA_DIR)
        self._snip_store= SnippetStore(DATA_DIR)
        self._history   = ConnectionHistory(DATA_DIR)
        self._sessions: Dict[str, SSHSession] = self._store.load()
        self._snippets: List[Snippet]          = self._snip_store.load()
        self._build()
        self._refresh_tree()
        self._refresh_snippets()

    # ------------------------------------------------------------------ multi-exec
    def _open_multiexec(self) -> None:
        """Open the Multi-Exec wizard (select servers → credential → command →
        verify → run on all, results in a popup)."""
        from ui.zterm_multiexec import MultiExecWizard
        if not self._sessions:
            messagebox.showinfo("Multi-Exec", "No saved sessions to run on.",
                                parent=self.winfo_toplevel())
            return
        MultiExecWizard(self.winfo_toplevel(), self._sessions, self._get_creds)

    def _open_credtools(self) -> None:
        """Open the credential tools: test a credential across servers, and
        bulk-reassign which vault credential sessions use to connect."""
        from ui.zterm_credtools import CredToolsWindow
        if not self._sessions:
            messagebox.showinfo("Credential Tools", "No saved sessions.",
                                parent=self.winfo_toplevel())
            return
        CredToolsWindow(self.winfo_toplevel(), self._sessions, self._get_creds,
                        set_vault_ref=self._set_sessions_vault_ref,
                        rename_sessions=self._rename_sessions)

    def _set_sessions_vault_ref(self, names, new_ref: str) -> int:
        """Reassign the connection credential (vault_ref) of the given sessions.
        Persists + refreshes the tree. Returns how many were changed."""
        changed = 0
        for n in names:
            s = self._sessions.get(n)
            if s and s.vault_ref != new_ref:
                self._sessions[n] = dataclasses.replace(s, vault_ref=new_ref)
                changed += 1
        if changed:
            self._store.save(self._sessions)
            self._refresh_tree()
        return changed

    def _rename_sessions(self, renames: dict) -> int:
        """Rename sessions to discovered hostnames. The connect address (host) is
        NEVER changed — only the session name/key. Clashing names get the IP
        appended (then a numeric suffix) so names stay unique. Returns count."""
        changed = 0
        for old, desired in renames.items():
            s = self._sessions.get(old)
            desired = (desired or "").strip()
            if not s or not desired or desired == old:
                continue
            final = desired
            if final in self._sessions and final != old:
                final = f"{desired} ({s.host})"
            i = 2
            while final in self._sessions and final != old:
                final = f"{desired} ({s.host}) {i}"
                i += 1
            self._sessions.pop(old, None)
            self._sessions[final] = dataclasses.replace(s, name=final)
            changed += 1
        if changed:
            self._store.save(self._sessions)
            self._refresh_tree()
        return changed

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        # Horizontal paned window — the sidebar/terminal divider is draggable,
        # and the terminal area grows when the window is resized.
        self._hpaned = tk.PanedWindow(
            self, orient=HORIZONTAL, bg=self.IBORDER,
            sashwidth=5, sashrelief=FLAT, bd=0, opaqueresize=True,
        )
        self._hpaned.pack(fill=BOTH, expand=True)

        # ── left sidebar (resizable, min 170px, starts ~235px) ──────────
        left = tk.Frame(self._hpaned, bg=self.SBG)
        self._build_sidebar(left)
        self._hpaned.add(left, minsize=170, width=235, stretch="never")

        # ── right content area (grows with the window) ──────────────────
        right = tk.Frame(self._hpaned, bg="#0a0a14")
        self._build_notebook(right)
        self._hpaned.add(right, minsize=320, stretch="always")

    # ------------------------------------------------------------------ sidebar

    def _build_sidebar(self, parent) -> None:
        # ── Fixed top area: header + action buttons + Connect ────────────
        hdr = tk.Frame(parent, bg=self.SBG, padx=8, pady=6)
        hdr.pack(fill=X)
        tk.Label(hdr, text="SSH Sessions", bg=self.SBG, fg=self.TEXT,
                 font=("Segoe UI", 11, "bold"), anchor=W).pack(side=LEFT, fill=X, expand=True)
        hist_btn = ttk.Button(hdr, text="📊", command=self._show_history,
                              bootstyle="secondary-outline", padding=(3, 1))
        hist_btn.pack(side=RIGHT)
        _Tooltip(hist_btn, "Connection history")
        imp_btn = ttk.Button(hdr, text="⇩", command=self._import_mobaxterm,
                             bootstyle="secondary-outline", padding=(3, 1))
        imp_btn.pack(side=RIGHT, padx=(0, 4))
        _Tooltip(imp_btn, "Import sessions from MobaXterm")
        impf_btn = ttk.Button(hdr, text="⬇", command=self._import_sessions_file,
                              bootstyle="secondary-outline", padding=(3, 1))
        impf_btn.pack(side=RIGHT, padx=(0, 4))
        _Tooltip(impf_btn, "Import sessions from a .ztsessions file")
        exp_btn = ttk.Button(hdr, text="⬆", command=self._export_sessions_file,
                             bootstyle="secondary-outline", padding=(3, 1))
        exp_btn.pack(side=RIGHT, padx=(0, 4))
        _Tooltip(exp_btn, "Export all sessions to a .ztsessions file")

        br = tk.Frame(parent, bg=self.SBG, padx=6)
        br.pack(fill=X)
        for lbl, cmd, style in [
            ("+ New", self._add_session,    "primary-outline"),
            ("✏",     self._edit_session,   "secondary-outline"),
            ("🗑",     self._delete_session, "danger-outline"),
        ]:
            ttk.Button(br, text=lbl, command=cmd,
                       bootstyle=style, padding=(4, 2)).pack(
                           side=LEFT, padx=2, fill=X, expand=True)

        ttk.Button(parent, text="⚡  Connect",
                   command=self._connect_selected,
                   bootstyle="success", padding=(6, 6)).pack(fill=X, padx=6, pady=(4, 0))

        ttk.Button(parent, text="📡  Multi-Exec  (run on many)",
                   command=self._open_multiexec,
                   bootstyle="info-outline", padding=(6, 5)).pack(fill=X, padx=6, pady=(4, 0))

        ttk.Button(parent, text="🔑  Credentials  (test / reassign)",
                   command=self._open_credtools,
                   bootstyle="warning-outline", padding=(6, 5)).pack(fill=X, padx=6, pady=(4, 4))

        # ── Search box (filters tree by name / IP / hostname / user) ─────
        search_wrap = tk.Frame(parent, bg=self.ITEM_BG)
        search_wrap.pack(fill=X, padx=6, pady=(0, 4))
        tk.Label(search_wrap, text="🔍", bg=self.ITEM_BG, fg=self.TSEC,
                 font=("Segoe UI", 9)).pack(side=LEFT, padx=(6, 2))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_tree())
        search_entry = tk.Entry(
            search_wrap, textvariable=self._search_var,
            bg=self.ITEM_BG, fg=self.TEXT, insertbackground=self.TEXT,
            relief=FLAT, bd=0, highlightthickness=0, font=("Segoe UI", 9))
        search_entry.pack(side=LEFT, fill=X, expand=True, ipady=4, padx=(0, 2))
        # Esc clears the search
        search_entry.bind("<Escape>", lambda e: self._search_var.set(""))
        clear_btn = tk.Label(search_wrap, text="✕", bg=self.ITEM_BG, fg=self.TSEC,
                             font=("Segoe UI", 9), cursor="hand2")
        clear_btn.pack(side=RIGHT, padx=(0, 6))
        clear_btn.bind("<Button-1>", lambda e: self._search_var.set(""))

        self._search_count = tk.StringVar(value="")
        tk.Label(parent, textvariable=self._search_count, bg=self.SBG,
                 fg=self.TSEC, font=("Segoe UI", 8), anchor=W).pack(
                     fill=X, padx=10)

        tk.Frame(parent, bg=self.IBORDER, height=1).pack(fill=X, padx=6)

        # ── Resizable area: session tree ↑ / snippets ↓ (draggable) ─────
        vpaned = tk.PanedWindow(
            parent, orient=VERTICAL, bg=self.IBORDER,
            sashwidth=5, sashrelief=FLAT, bd=0, opaqueresize=True,
        )
        vpaned.pack(fill=BOTH, expand=True, padx=2, pady=2)

        # Session tree pane
        tree_pane = tk.Frame(vpaned, bg=self.SBG)
        self._tree = ttk.Treeview(tree_pane, show="tree", selectmode="browse")
        tvsb = ttk.Scrollbar(tree_pane, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=tvsb.set)
        tvsb.pack(side=RIGHT, fill=Y)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        self._tree.tag_configure("group",   font=("Segoe UI", 9, "bold"), foreground="#729fcf")
        self._tree.tag_configure("session", font=("Segoe UI", 9))
        self._tree.bind("<Double-Button-1>", self._on_tree_double)
        self._tree.bind("<Return>",          lambda e: self._connect_selected())
        self._tree.bind("<Button-3>",        self._on_right_click)
        vpaned.add(tree_pane, minsize=90, stretch="always")

        # Snippets pane
        snip_pane = tk.Frame(vpaned, bg=self.SBG)
        snip_hdr = tk.Frame(snip_pane, bg=self.SBG, padx=8, pady=3)
        snip_hdr.pack(fill=X)
        tk.Label(snip_hdr, text="Snippets", bg=self.SBG, fg=self.TEXT,
                 font=("Segoe UI", 9, "bold"), anchor=W).pack(side=LEFT)
        ttk.Button(snip_hdr, text="+", command=self._add_snippet,
                   bootstyle="secondary-outline", padding=(3, 1)).pack(side=RIGHT)

        snip_list_frame = tk.Frame(snip_pane, bg=self.SBG)
        snip_list_frame.pack(fill=BOTH, expand=True)
        self._snip_listbox = tk.Listbox(
            snip_list_frame, bg=self.SBG, fg=self.TEXT,
            selectbackground=self.ACCENT, selectforeground="#fff",
            font=("Segoe UI", 8), bd=0, relief=FLAT,
            highlightthickness=0, activestyle="none",
        )
        svsb = ttk.Scrollbar(snip_list_frame, orient="vertical",
                             command=self._snip_listbox.yview)
        self._snip_listbox.configure(yscrollcommand=svsb.set)
        svsb.pack(side=RIGHT, fill=Y)
        self._snip_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self._snip_listbox.bind("<Double-Button-1>", lambda e: self._send_snippet())
        self._snip_listbox.bind("<Button-3>",         self._on_snippet_right_click)
        vpaned.add(snip_pane, minsize=60, height=140, stretch="never")

    # ------------------------------------------------------------------ notebook

    def _build_notebook(self, parent) -> None:
        self._welcome = tk.Frame(parent, bg="#0a0a14")
        self._welcome.pack(fill=BOTH, expand=True)
        tk.Label(self._welcome, text="⚡", bg="#0a0a14", fg="#1a1a30",
                 font=("Segoe UI", 60)).pack(expand=True, pady=(60, 0))
        tk.Label(self._welcome, text="ZTerm SSH Client",
                 bg="#0a0a14", fg=self.TEXT,
                 font=("Segoe UI", 16, "bold")).pack()
        for hint in [
            "Double-click a session or press ⚡ Connect",
            "Right-click a session for duplicate, color, and more",
            "Split terminal with ⊞→ or ⊟↓ buttons in each tab",
        ]:
            tk.Label(self._welcome, text=hint, bg="#0a0a14", fg=self.TSEC,
                     font=("Segoe UI", 9)).pack(pady=1)

        self._notebook = ttk.Notebook(parent)
        self._notebook.pack(fill=BOTH, expand=True)
        self._notebook.pack_forget()

    # ------------------------------------------------------------------ tree refresh

    def _refresh_tree(self) -> None:
        self._tree.delete(*self._tree.get_children())

        # Search filter (matches name, host, or username — case-insensitive)
        query = ""
        if getattr(self, "_search_var", None) is not None:
            query = self._search_var.get().strip().lower()

        def matches(s: SSHSession) -> bool:
            if not query:
                return True
            return (query in s.name.lower()
                    or query in s.host.lower()
                    or query in (s.username or "").lower())

        # Group sessions (filtered)
        grouped: Dict[str, List[SSHSession]] = {}
        ungrouped: List[SSHSession] = []
        for s in sorted(self._sessions.values(), key=lambda x: x.name.lower()):
            if not matches(s):
                continue
            if s.group:
                grouped.setdefault(s.group, []).append(s)
            else:
                ungrouped.append(s)

        # When searching, expand groups so matches are visible; collapse otherwise.
        open_groups = bool(query)

        for group_name in sorted(grouped):
            gid = f"__group__{group_name}"
            self._tree.insert("", "end", iid=gid,
                              text=f"  📁 {group_name}",
                              tags=("group",), open=open_groups)
            for s in grouped[group_name]:
                self._insert_session(s, parent=gid)

        for s in ungrouped:
            self._insert_session(s, parent="")

        # Update the result count label, if present
        if getattr(self, "_search_count", None) is not None:
            shown = sum(len(v) for v in grouped.values()) + len(ungrouped)
            total = len(self._sessions)
            self._search_count.set(
                f"{shown} shown" if query else f"{total} sessions")

    def _insert_session(self, s: SSHSession, parent: str) -> None:
        icon  = "🖥"
        label = f"  {icon}  {s.name}  ({s.host}:{s.port})"
        fg    = s.color if s.color else self.TEXT
        self._tree.insert(parent, "end",
                          iid=s.name,           # iid IS the session name — safe lookup
                          text=label,
                          tags=("session",))
        if s.color:
            self._tree.tag_configure(f"col_{s.name}", foreground=s.color)
            self._tree.item(s.name, tags=("session", f"col_{s.name}"))

    # ------------------------------------------------------------------ selected session

    def _selected_session(self) -> Optional[SSHSession]:
        sel = self._tree.selection()
        if not sel:
            return None
        iid = sel[0]
        # Group nodes start with __group__
        if iid.startswith("__group__"):
            return None
        return self._sessions.get(iid)  # iid == session name — no parsing needed

    # ------------------------------------------------------------------ right-click

    def _on_tree_double(self, event) -> None:
        iid = self._tree.identify_row(event.y)
        if iid and not iid.startswith("__group__"):
            self._connect_selected()

    def _on_right_click(self, event: tk.Event) -> None:
        iid = self._tree.identify_row(event.y)
        if not iid or iid.startswith("__group__"):
            return
        self._tree.selection_set(iid)

        m = tk.Menu(self, tearoff=0, bg="#1e1e2e", fg=self.TEXT,
                    activebackground=self.ACCENT, activeforeground="#fff",
                    relief=FLAT, bd=1)
        m.add_command(label="⚡  Connect",         command=self._connect_selected)
        m.add_command(label="🛰  Connect via jump host …",
                      command=self._connect_via_jump)
        m.add_separator()
        m.add_command(label="⧉  Duplicate Config", command=self._duplicate_config)
        m.add_command(label="✏  Edit",              command=self._edit_session)
        m.add_separator()

        col_m = tk.Menu(m, tearoff=0, bg="#1e1e2e", fg=self.TEXT,
                        activebackground=self.ACCENT, activeforeground="#fff",
                        relief=FLAT)
        for lbl, hex_c in _LABEL_COLORS:
            col_m.add_command(label=f"  {lbl}",
                              command=lambda c=hex_c, n=iid: self._set_color(n, c))
        col_m.add_separator()
        col_m.add_command(label="  Custom …",
                          command=lambda n=iid: self._pick_color(n))
        m.add_cascade(label="🎨  Label Color",      menu=col_m)
        m.add_separator()
        m.add_command(label="🗑  Delete",             command=self._delete_session)
        m.post(event.x_root, event.y_root)

    # ------------------------------------------------------------------ CRUD

    def _add_session(self) -> None:
        def on_save(s: SSHSession) -> None:
            if s.name in self._sessions:
                messagebox.showerror("Duplicate",
                                     f"Session '{s.name}' already exists.",
                                     parent=self.winfo_toplevel())
                return
            self._sessions = self._store.add(s, self._sessions)
            self._refresh_tree()

        ZTermSessionDialog(
            self,
            credentials=self._get_creds(),
            on_save=on_save,
            existing_groups=self._store.groups(self._sessions),
        )

    def _edit_session(self) -> None:
        s = self._selected_session()
        if not s:
            messagebox.showinfo("ZTerm", "Select a session to edit.",
                                parent=self.winfo_toplevel())
            return

        def on_save(new_s: SSHSession) -> None:
            sessions = dict(self._sessions)
            if new_s.name != s.name:
                sessions.pop(s.name, None)
            sessions[new_s.name] = new_s
            self._store.save(sessions)
            self._sessions = sessions
            self._refresh_tree()

        ZTermSessionDialog(
            self, credentials=self._get_creds(),
            on_save=on_save, session=s,
            existing_groups=self._store.groups(self._sessions),
        )

    def _delete_session(self) -> None:
        s = self._selected_session()
        if not s:
            return
        if not messagebox.askyesno("Delete Session",
                                   f"Delete session '{s.name}'?\nThis cannot be undone.",
                                   parent=self.winfo_toplevel()):
            return
        self._sessions = self._store.delete(s.name, self._sessions)
        self._refresh_tree()

    def _duplicate_config(self) -> None:
        s = self._selected_session()
        if not s:
            return
        new_name = s.name + " (copy)"
        i = 1
        while new_name in self._sessions:
            i += 1
            new_name = f"{s.name} (copy {i})"
        dup = dataclasses.replace(s, name=new_name)
        self._sessions = self._store.add(dup, self._sessions)
        self._refresh_tree()

    # ------------------------------------------------------------------ colour

    def _set_color(self, name: str, color: str) -> None:
        s = dataclasses.replace(self._sessions[name], color=color)
        self._sessions[name] = s
        self._store.save(self._sessions)
        self._refresh_tree()

    def _pick_color(self, name: str) -> None:
        result = colorchooser.askcolor(
            color=self._sessions[name].color or "#d3d7cf",
            title=f"Pick colour for '{name}'",
            parent=self.winfo_toplevel(),
        )
        if result and result[1]:
            self._set_color(name, result[1])

    # ------------------------------------------------------------------ snippets

    def _refresh_snippets(self) -> None:
        self._snip_listbox.delete(0, "end")
        for sn in self._snippets:
            self._snip_listbox.insert("end", f"  ▷  {sn.name}")

    def _send_snippet(self) -> None:
        sel = self._snip_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._snippets):
            return
        cmd = self._snippets[idx].command + "\n"
        # Send to the active terminal pane in the focused tab
        tab = self._active_tab()
        if tab:
            p = tab._active_pane()
            if p:
                p.terminal._send(cmd)
            else:
                messagebox.showinfo("ZTerm",
                                    "No active terminal. Connect to a session first.",
                                    parent=self.winfo_toplevel())
        else:
            messagebox.showinfo("ZTerm",
                                "No tab is open. Connect to a session first.",
                                parent=self.winfo_toplevel())

    def _active_tab(self) -> Optional[_SessionTab]:
        try:
            sel = self._notebook.select()
            if sel:
                return self._notebook.nametowidget(sel)
        except Exception:
            pass
        return None

    def _add_snippet(self) -> None:
        def save(sn: Snippet) -> None:
            if sn.name and sn.command:
                self._snippets.append(sn)
                self._snip_store.save(self._snippets)
                self._refresh_snippets()
        _SnippetEditor(self, on_save=save)

    def _on_snippet_right_click(self, event: tk.Event) -> None:
        idx = self._snip_listbox.nearest(event.y)
        self._snip_listbox.selection_clear(0, "end")
        self._snip_listbox.selection_set(idx)

        m = tk.Menu(self, tearoff=0, bg="#1e1e2e", fg=self.TEXT,
                    activebackground=self.ACCENT, activeforeground="#fff", relief=FLAT)
        m.add_command(label="▷ Send to Terminal", command=self._send_snippet)
        m.add_separator()
        m.add_command(label="✏ Edit", command=lambda: self._edit_snippet(idx))
        m.add_command(label="🗑 Delete", command=lambda: self._delete_snippet(idx))
        m.post(event.x_root, event.y_root)

    def _edit_snippet(self, idx: int) -> None:
        if idx >= len(self._snippets):
            return
        old = self._snippets[idx]
        def save(sn: Snippet) -> None:
            if sn.name and sn.command:
                self._snippets[idx] = sn
                self._snip_store.save(self._snippets)
                self._refresh_snippets()
        _SnippetEditor(self, on_save=save, snippet=old)

    def _delete_snippet(self, idx: int) -> None:
        if idx < len(self._snippets):
            del self._snippets[idx]
            self._snip_store.save(self._snippets)
            self._refresh_snippets()

    # ------------------------------------------------------------------ history

    def _show_history(self) -> None:
        _HistoryWindow(self.winfo_toplevel(), self._history)

    # ------------------------------------------------------------------ import

    def _export_sessions_file(self) -> None:
        """Write all ZTerm sessions (+ snippets) to a portable .ztsessions JSON."""
        import json
        path = filedialog.asksaveasfilename(
            title="Export ZTerm sessions",
            defaultextension=".ztsessions",
            filetypes=[("ZTerm sessions", "*.ztsessions"), ("JSON", "*.json"),
                       ("All", "*.*")],
            initialfile="zterm_sessions.ztsessions",
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        try:
            data = {
                "version": 1,
                "sessions": {name: s.to_dict()
                             for name, s in self._sessions.items()},
                "snippets": [{"name": s.name, "command": s.command}
                             for s in self._snippets],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            messagebox.showinfo(
                "Export complete",
                f"Exported {len(self._sessions)} session(s) and "
                f"{len(self._snippets)} snippet(s) to:\n{path}",
                parent=self.winfo_toplevel(),
            )
        except Exception as e:
            messagebox.showerror("Export failed", str(e),
                                 parent=self.winfo_toplevel())

    def _import_sessions_file(self) -> None:
        """Merge sessions (+ snippets) from a .ztsessions file. Name clashes are
        skipped, never overwritten."""
        import json
        path = filedialog.askopenfilename(
            title="Import ZTerm sessions",
            filetypes=[("ZTerm sessions", "*.ztsessions"), ("JSON", "*.json"),
                       ("All", "*.*")],
            parent=self.winfo_toplevel(),
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("sessions", data)   # tolerate a bare {name: {...}} map
            added = skipped = 0
            for name, d in raw.items():
                if name in self._sessions:
                    skipped += 1
                    continue
                d = dict(d); d.setdefault("name", name)
                self._sessions[name] = SSHSession.from_dict(d)
                added += 1
            snip_added = 0
            have = {s.name for s in self._snippets}
            for sd in data.get("snippets", []):
                if sd.get("name") and sd["name"] not in have:
                    self._snippets.append(Snippet(sd["name"], sd.get("command", "")))
                    have.add(sd["name"]); snip_added += 1
            if added:
                self._store.save(self._sessions)
                self._refresh_tree()
            if snip_added:
                self._snip_store.save(self._snippets)
                self._refresh_snippets()
            messagebox.showinfo(
                "Import complete",
                f"Imported {added} session(s) ({skipped} duplicate(s) skipped) "
                f"and {snip_added} snippet(s).",
                parent=self.winfo_toplevel(),
            )
        except Exception as e:
            messagebox.showerror("Import failed", str(e),
                                 parent=self.winfo_toplevel())

    def _import_mobaxterm(self) -> None:
        from ui.zterm_import_dialog import ZTermImportDialog

        def on_import(new_sessions):
            added = skipped = 0
            for s in new_sessions:
                if s.name in self._sessions:
                    skipped += 1
                    continue
                self._sessions[s.name] = s
                added += 1
            if added:
                self._store.save(self._sessions)
                self._refresh_tree()
            messagebox.showinfo(
                "MobaXterm Import",
                f"Imported {added} session(s).\n"
                f"Skipped {skipped} duplicate(s) already in ZTerm.",
                parent=self.winfo_toplevel(),
            )

        ZTermImportDialog(self, get_credentials=self._get_creds, on_import=on_import)

    # ------------------------------------------------------------------ connect

    def _connect_selected(self) -> None:
        s = self._selected_session()
        if not s:
            messagebox.showinfo("ZTerm", "Select a session first.",
                                parent=self.winfo_toplevel())
            return
        self._open_tab(s)

    def _connect_via_jump(self) -> None:
        """Right-click → connect immediately through a chosen bastion (no need to
        wait for a direct-connect timeout)."""
        s = self._selected_session()
        if not s:
            messagebox.showinfo("ZTerm", "Select a session first.",
                                parent=self.winfo_toplevel())
            return
        bastions = sorted(n for n, b in self._sessions.items() if b.host != s.host)
        if not bastions:
            messagebox.showinfo("ZTerm", "No other session to use as a jump host.",
                                parent=self.winfo_toplevel())
            return
        default = _jump_pref_load()
        if default not in bastions:
            default = ("ANSIBLE_Tower" if "ANSIBLE_Tower" in bastions else bastions[0])
        chooser = _BastionChooser(self.winfo_toplevel(), s.name, bastions, default,
                                  self._sessions, self._get_creds() or {})
        if chooser.result:
            bname, cname = chooser.result
            _jump_pref_save(bname)
            self._open_tab(s, via_bastion=(bname, cname))

    def _open_tab(self, session: SSHSession, password: str = "",
                  adopt_ssh: Optional["SSHConnection"] = None,
                  adopt_state: Optional[dict] = None,
                  via_bastion: Optional[str] = None) -> None:
        if not PARAMIKO_OK:
            messagebox.showerror(
                "paramiko not installed",
                "Run:  pip install paramiko pyte\nThen restart SecureVault.",
                parent=self.winfo_toplevel(),
            )
            return

        log.info("Opening tab '%s' → %s@%s:%s  vault='%s'  jump='%s'%s",
                 session.name, session.username, session.host,
                 session.port, session.vault_ref, session.jump_host,
                 "  (adopting live conn)" if adopt_ssh else "")

        # Adopting a live connection (Attach back): no password resolution needed.
        if adopt_ssh is None and not password:
            if session.auth_type == "password":
                if session.vault_ref:
                    creds = self._get_creds()
                    cred  = creds.get(session.vault_ref)
                    if cred is None:
                        log.error("vault_ref '%s' not found", session.vault_ref)
                        messagebox.showerror(
                            "Vault entry not found",
                            f"Credential '{session.vault_ref}' not found in vault.\n\n"
                            f"Available: {', '.join(creds.keys()) or '(none)'}",
                            parent=self.winfo_toplevel(),
                        )
                        return
                    password = cred.password
                else:
                    password = simpledialog.askstring(
                        "Password",
                        f"Enter password for {session.username}@{session.host}:",
                        show="•", parent=self.winfo_toplevel(),
                    )
                    if password is None:
                        return

        # If the session has no username of its own, borrow it from the vault
        # credential so "use ansible_new" supplies BOTH the username and the
        # password (most imported plain-IP sessions have an empty username).
        eff_session = session
        if not session.username and session.vault_ref:
            cred = self._get_creds().get(session.vault_ref)
            cu = getattr(cred, "username", "") if cred else ""
            if cu:
                eff_session = dataclasses.replace(session, username=cu)

        # Right-click "Connect via jump host" → route through the chosen bastion
        # using the chosen credential. via_bastion = (bastion_name, cred_name).
        if via_bastion:
            bname, cname = via_bastion
            b = self._sessions.get(bname)
            if b and b.host != eff_session.host and not eff_session.jump_host:
                juser, jref, jkey = _jump_fields_for(b, cname, self._get_creds)
                eff_session = _inject_jump(
                    eff_session, host=b.host, port=b.port,
                    user=juser, vault_ref=jref, key_path=jkey)
                log.info("Routing %s via jump %s@%s (cred=%s)",
                         eff_session.host, juser, b.host, jref or "(key)")

        def on_close():
            try:
                self._notebook.forget(tab)
            except Exception:
                pass
            if not self._notebook.tabs():
                self._notebook.pack_forget()
                self._welcome.pack(fill=BOTH, expand=True)

        tab = _SessionTab(
            self._notebook,
            session=eff_session, password=password,
            on_close=on_close,
            open_tab_cb=self._open_tab,   # enables Clone Tab
            history=self._history,
            get_credentials=self._get_creds,
            adopt_ssh=adopt_ssh,         # Attach: take over live connection
            adopt_state=adopt_state,     # Attach: restore scrollback/display
            panel=self,
        )
        self._notebook.add(tab, text=f"  {session.name}  ")
        self._notebook.select(tab)

        self._welcome.pack_forget()
        self._notebook.pack(fill=BOTH, expand=True)
