"""
Multi-Exec wizard — run a command on many SSH servers at once.

Flow (Back / Next):
  1. Choose servers (checklist + search)
  2. Choose credential (from the SecureVault vault)
  3. Write the command(s)
  4. Verify → Run  → results popup (per-server stdout/stderr/exit)

Commands run NON-interactively via zterm.ssh_client.run_command (paramiko
exec_command) on a small thread pool, so 100s of servers complete in parallel.
"""
import queue
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict

import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox

from zterm.ssh_client import run_command
from zterm.session_store import SSHSession


_BG   = "#0d0d1a"
_CARD = "#1a1a2e"
_TEXT = "#d3d7cf"
_TSEC = "#7d8fa6"
_ACC  = "#175ddc"
_MAX_WORKERS = 20


class MultiExecWizard(ttk.Toplevel):
    def __init__(self, parent, sessions: Dict[str, SSHSession],
                 get_credentials: Callable[[], dict]):
        super().__init__(parent)
        self._parent   = parent
        self._sessions = sessions
        self._get_creds = get_credentials

        self._selected: set = set()      # chosen session names
        self._step = 0
        self._timeout = 30
        self._use_pty = False

        # run state
        self._result_q: queue.Queue = queue.Queue()
        self._results: list = []
        self._total = 0
        self._executor = None

        self.title("Multi-Exec — run a command on many servers")
        self.configure(bg=_BG)
        self.geometry("760x560")
        self.minsize(640, 480)
        self.transient(parent)
        try:
            self.grab_set()
        except Exception:
            pass

        self._build()
        self._show_step(0)
        self._center()

    # ------------------------------------------------------------------ layout
    def _center(self):
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _build(self):
        # Step indicator
        self._crumb = tk.Label(self, bg=_BG, fg=_TSEC, font=("Segoe UI", 9),
                               anchor=W, padx=16, pady=8)
        self._crumb.pack(fill=X)

        self._body = tk.Frame(self, bg=_BG)
        self._body.pack(fill=BOTH, expand=True, padx=16)

        self._steps = [
            self._build_step_servers(),
            self._build_step_cred(),
            self._build_step_cmd(),
            self._build_step_verify(),
        ]

        # Nav bar
        nav = tk.Frame(self, bg=_BG, padx=16, pady=12)
        nav.pack(fill=X)
        self._cancel_btn = ttk.Button(nav, text="Cancel", command=self._on_close,
                                      bootstyle="secondary")
        self._cancel_btn.pack(side=LEFT)
        self._next_btn = ttk.Button(nav, text="Next  ▶", command=self._next,
                                    bootstyle="primary")
        self._next_btn.pack(side=RIGHT)
        self._back_btn = ttk.Button(nav, text="◀  Back", command=self._back,
                                    bootstyle="secondary-outline")
        self._back_btn.pack(side=RIGHT, padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- Step 1: servers --------------------------------------------------
    def _build_step_servers(self):
        f = tk.Frame(self._body, bg=_BG)
        tk.Label(f, text="1.  Choose the servers to run on", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 8))

        top = tk.Frame(f, bg=_BG)
        top.pack(fill=X)
        sw = tk.Frame(top, bg=_CARD)
        sw.pack(side=LEFT, fill=X, expand=True)
        tk.Label(sw, text="🔍", bg=_CARD, fg=_TSEC).pack(side=LEFT, padx=(6, 2))
        self._srv_search = tk.StringVar()
        self._srv_search.trace_add("write", lambda *_: self._fill_servers())
        tk.Entry(sw, textvariable=self._srv_search, bg=_CARD, fg=_TEXT,
                 insertbackground=_TEXT, relief=FLAT, bd=0, highlightthickness=0,
                 font=("Segoe UI", 10)).pack(side=LEFT, fill=X, expand=True,
                                             ipady=5, padx=(0, 6))
        ttk.Button(top, text="Select all", command=self._select_all_filtered,
                   bootstyle="secondary-outline", padding=(6, 2)).pack(side=LEFT, padx=(8, 2))
        ttk.Button(top, text="Clear", command=self._clear_selection,
                   bootstyle="secondary-outline", padding=(6, 2)).pack(side=LEFT)

        body = tk.Frame(f, bg=_BG)
        body.pack(fill=BOTH, expand=True, pady=(8, 4))
        self._srv_tree = ttk.Treeview(body, show="tree", selectmode="none")
        vsb = ttk.Scrollbar(body, orient="vertical", command=self._srv_tree.yview)
        self._srv_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        self._srv_tree.pack(side=LEFT, fill=BOTH, expand=True)
        self._srv_tree.bind("<Button-1>", self._toggle_server)

        self._srv_count = tk.Label(f, text="", bg=_BG, fg=_TSEC, font=("Segoe UI", 9))
        self._srv_count.pack(anchor=W)
        self._fill_servers()
        return f

    def _fill_servers(self):
        q = self._srv_search.get().strip().lower()
        self._srv_tree.delete(*self._srv_tree.get_children())
        for name in sorted(self._sessions):
            s = self._sessions[name]
            if q and q not in name.lower() and q not in s.host.lower():
                continue
            mark = "☑" if name in self._selected else "☐"
            self._srv_tree.insert("", "end", iid=name,
                                  text=f" {mark}  {name}   ({s.host}:{s.port})")
        self._update_srv_count()

    def _toggle_server(self, event):
        iid = self._srv_tree.identify_row(event.y)
        if not iid:
            return
        if iid in self._selected:
            self._selected.discard(iid)
        else:
            self._selected.add(iid)
        s = self._sessions[iid]
        mark = "☑" if iid in self._selected else "☐"
        self._srv_tree.item(iid, text=f" {mark}  {iid}   ({s.host}:{s.port})")
        self._update_srv_count()
        return "break"

    def _select_all_filtered(self):
        for iid in self._srv_tree.get_children():
            self._selected.add(iid)
        self._fill_servers()

    def _clear_selection(self):
        self._selected.clear()
        self._fill_servers()

    def _update_srv_count(self):
        self._srv_count.config(text=f"{len(self._selected)} server(s) selected")

    # ---- Step 2: credential ----------------------------------------------
    def _build_step_cred(self):
        f = tk.Frame(self._body, bg=_BG)
        tk.Label(f, text="2.  Choose the credential (password)", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 8))
        tk.Label(f, text="The selected vault credential's password is used to log in to every\n"
                         "chosen server. The username comes from each session (falls back to the\n"
                         "credential's username if a session has none).",
                 bg=_BG, fg=_TSEC, font=("Segoe UI", 9), justify=LEFT).pack(anchor=W, pady=(0, 14))

        row = tk.Frame(f, bg=_BG)
        row.pack(fill=X)
        tk.Label(row, text="Credential:", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 10)).pack(side=LEFT, padx=(0, 8))
        self._cred_var = tk.StringVar()
        self._cred_combo = ttk.Combobox(row, textvariable=self._cred_var,
                                        state="readonly", width=36)
        self._cred_combo.pack(side=LEFT)
        self._cred_combo.bind("<<ComboboxSelected>>", lambda e: self._update_cred_info())

        self._cred_info = tk.Label(f, text="", bg=_BG, fg=_TSEC,
                                   font=("Segoe UI", 9), justify=LEFT)
        self._cred_info.pack(anchor=W, pady=(12, 0))

        trow = tk.Frame(f, bg=_BG)
        trow.pack(fill=X, pady=(18, 0))
        tk.Label(trow, text="Per-server timeout (sec):", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 10)).pack(side=LEFT, padx=(0, 8))
        self._timeout_var = tk.IntVar(value=self._timeout)
        ttk.Spinbox(trow, from_=5, to=300, textvariable=self._timeout_var,
                    width=6).pack(side=LEFT)
        return f

    def _load_credentials(self):
        creds = self._get_creds() or {}
        names = sorted(creds.keys())
        self._cred_combo["values"] = names
        if names and not self._cred_var.get():
            # Default to the vault_ref most selected sessions use, else first.
            from collections import Counter
            refs = Counter(self._sessions[n].vault_ref for n in self._selected
                           if n in self._sessions)
            best = next((r for r, _ in refs.most_common() if r in creds), None)
            self._cred_var.set(best or names[0])
        self._update_cred_info()

    def _update_cred_info(self):
        creds = self._get_creds() or {}
        c = creds.get(self._cred_var.get())
        if c:
            self._cred_info.config(
                text=f"Login user (credential): {getattr(c, 'username', '') or '(none)'}\n"
                     f"Password: ••••••••  (from vault)")
        else:
            self._cred_info.config(text="No credential selected.")

    # ---- Step 3: command --------------------------------------------------
    def _build_step_cmd(self):
        f = tk.Frame(self._body, bg=_BG)
        tk.Label(f, text="3.  Command(s) to run", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 8))
        tk.Label(f, text="Runs non-interactively on every selected server. Put multiple "
                         "commands on separate lines.",
                 bg=_BG, fg=_TSEC, font=("Segoe UI", 9), justify=LEFT).pack(anchor=W, pady=(0, 10))
        self._cmd_text = tk.Text(f, height=10, bg=_CARD, fg=_TEXT,
                                 insertbackground=_TEXT, relief=FLAT,
                                 font=("Consolas", 11), wrap="word",
                                 highlightthickness=1, highlightbackground="#3a3f4b")
        self._cmd_text.pack(fill=BOTH, expand=True)
        self._cmd_text.insert("1.0", "hostname\nuptime")

        self._pty_var = tk.BooleanVar(value=False)
        opt = tk.Frame(f, bg=_BG)
        opt.pack(fill=X, pady=(8, 0))
        ttk.Checkbutton(opt, text="Request a PTY  (needed for sudo / interactive tools)",
                        variable=self._pty_var,
                        bootstyle="round-toggle").pack(side=LEFT)
        return f

    # ---- Step 4: verify ---------------------------------------------------
    def _build_step_verify(self):
        f = tk.Frame(self._body, bg=_BG)
        tk.Label(f, text="4.  Verify and run", bg=_BG, fg=_TEXT,
                 font=("Segoe UI", 13, "bold")).pack(anchor=W, pady=(0, 8))
        self._verify_text = tk.Text(f, bg=_CARD, fg=_TEXT, relief=FLAT,
                                    font=("Consolas", 10), wrap="word",
                                    highlightthickness=1, highlightbackground="#3a3f4b")
        self._verify_text.pack(fill=BOTH, expand=True)
        self._verify_text.configure(state="disabled")

        # Progress (hidden until Run)
        self._prog_frame = tk.Frame(f, bg=_BG)
        self._prog_lbl = tk.Label(self._prog_frame, text="", bg=_BG, fg=_TEXT,
                                  font=("Segoe UI", 10))
        self._prog_lbl.pack(anchor=W, pady=(8, 2))
        self._prog = ttk.Progressbar(self._prog_frame, mode="determinate")
        self._prog.pack(fill=X)
        return f

    def _refresh_verify(self):
        creds = self._get_creds() or {}
        c = creds.get(self._cred_var.get())
        cmd = self._cmd_text.get("1.0", "end-1c")
        names = sorted(self._selected)
        preview = "\n".join(f"  • {n}  ({self._sessions[n].host})"
                            for n in names[:40] if n in self._sessions)
        if len(names) > 40:
            preview += f"\n  … and {len(names) - 40} more"
        txt = (f"Servers   : {len(names)}\n{preview}\n\n"
               f"Credential: {self._cred_var.get()}  "
               f"(user: {getattr(c, 'username', '') or '(from session)'})\n"
               f"Timeout   : {self._timeout_var.get()} s / server\n"
               f"PTY       : {'yes (sudo-capable)' if self._pty_var.get() else 'no'}\n\n"
               f"Command(s):\n{cmd}\n")
        self._verify_text.configure(state="normal")
        self._verify_text.delete("1.0", "end")
        self._verify_text.insert("1.0", txt)
        self._verify_text.configure(state="disabled")

    # ------------------------------------------------------------------ nav
    def _show_step(self, i):
        for fr in self._steps:
            fr.pack_forget()
        self._step = i
        self._steps[i].pack(fill=BOTH, expand=True)
        self._crumb.config(
            text="   ›   ".join(
                (f"➤ {t}" if j == i else t)
                for j, t in enumerate(
                    ["Servers", "Credential", "Command", "Verify & Run"])))
        self._back_btn.configure(state=("disabled" if i == 0 else "normal"))
        self._next_btn.configure(text=("Run ▶" if i == len(self._steps) - 1 else "Next  ▶"),
                                 bootstyle=("success" if i == len(self._steps) - 1 else "primary"))
        if i == 1:
            self._load_credentials()
        elif i == 3:
            self._timeout = int(self._timeout_var.get())
            self._refresh_verify()

    def _back(self):
        if self._step > 0:
            self._show_step(self._step - 1)

    def _next(self):
        if self._step == 0:
            if not self._selected:
                messagebox.showwarning("Multi-Exec", "Select at least one server.",
                                       parent=self)
                return
        elif self._step == 1:
            if not self._cred_var.get():
                messagebox.showwarning("Multi-Exec", "Choose a credential.", parent=self)
                return
        elif self._step == 2:
            if not self._cmd_text.get("1.0", "end-1c").strip():
                messagebox.showwarning("Multi-Exec", "Enter a command to run.", parent=self)
                return
        elif self._step == 3:
            self._run()
            return
        self._show_step(self._step + 1)

    # ------------------------------------------------------------------ run
    def _run(self):
        sel = [self._sessions[n] for n in sorted(self._selected) if n in self._sessions]
        creds = self._get_creds() or {}
        cred = creds.get(self._cred_var.get())
        command = self._cmd_text.get("1.0", "end-1c")
        if not sel or not command.strip():
            return
        if not messagebox.askyesno(
                "Run Multi-Exec",
                f"Run the command on {len(sel)} server(s) now?", parent=self):
            return

        self._timeout = int(self._timeout_var.get())
        self._use_pty = bool(self._pty_var.get())   # snapshot for worker threads
        command = self._compose_command(command)    # add separators between commands
        self._results = []
        self._result_q = queue.Queue()
        self._total = len(sel)
        self._back_btn.configure(state="disabled")
        self._next_btn.configure(state="disabled")
        self._cancel_btn.configure(text="Close")
        self._prog_frame.pack(fill=X, pady=(8, 0))
        self._prog.configure(maximum=self._total, value=0)
        self._prog_lbl.config(text=f"Running on 0/{self._total} …")

        self._executor = ThreadPoolExecutor(
            max_workers=min(_MAX_WORKERS, max(1, len(sel))))
        for s in sel:
            self._executor.submit(self._worker, s, cred, command)
        self.after(120, self._poll_results)

    @staticmethod
    def _compose_command(command: str) -> str:
        """When several commands are entered, run them in ONE shell (so cd/env
        persist) but print a clear separator + the command before each, so the
        per-server output is easy to read."""
        lines = [ln for ln in command.splitlines() if ln.strip()]
        if len(lines) <= 1:
            return command
        sep = "-" * 60
        parts = []
        for ln in lines:
            label = ln.replace("'", "'\\''")     # safe single-quote escaping
            parts.append(
                f"echo ''; echo '{sep}'; echo '$ {label}'; echo '{sep}'; {ln}")
        return "\n".join(parts)

    def _worker(self, s: SSHSession, cred, command: str):
        creds = self._get_creds() or {}
        password = getattr(cred, "password", "") if cred else ""
        username = s.username or (getattr(cred, "username", "") if cred else "")
        jpw = ""
        if s.jump_host and s.jump_vault_ref:
            jc = creds.get(s.jump_vault_ref)
            jpw = getattr(jc, "password", "") if jc else ""
        res = run_command(
            host=s.host, port=s.port, username=username, password=password,
            key_path=(s.key_path if s.auth_type == "key" else ""),
            command=command,
            jump_host=s.jump_host, jump_port=s.jump_port, jump_user=s.jump_user,
            jump_password=jpw, jump_key_path=s.jump_key_path,
            exec_timeout=self._timeout, get_pty=self._use_pty,
        )
        res["name"] = s.name
        self._result_q.put(res)

    def _poll_results(self):
        if not self.winfo_exists():
            return
        try:
            while True:
                self._results.append(self._result_q.get_nowait())
        except queue.Empty:
            pass
        done = len(self._results)
        self._prog.configure(value=done)
        self._prog_lbl.config(text=f"Running on {done}/{self._total} …")
        if done >= self._total:
            self._prog_lbl.config(text=f"Done — {done}/{self._total} finished.")
            if self._executor:
                self._executor.shutdown(wait=False)
            _ResultsWindow(self._parent, list(self._results))
            self.destroy()
            return
        self.after(150, self._poll_results)

    def _on_close(self):
        if self._executor:
            self._executor.shutdown(wait=False)
        self.destroy()


class _ResultsWindow(ttk.Toplevel):
    """Per-server results: list on the left, full output on the right."""

    def __init__(self, parent, results: list):
        super().__init__(parent)
        self._results = {r["name"]: r for r in results}
        ok = sum(1 for r in results if r.get("ok"))
        fail = len(results) - ok

        self.title("Multi-Exec — results")
        self.configure(bg=_BG)
        self.geometry("900x600")
        self.transient(parent)

        hdr = tk.Frame(self, bg=_BG, padx=12, pady=8)
        hdr.pack(fill=X)
        tk.Label(hdr, text=f"✓ {ok} succeeded     ✗ {fail} failed     "
                           f"({len(results)} total)",
                 bg=_BG, fg=_TEXT, font=("Segoe UI", 11, "bold")).pack(side=LEFT)
        self._only_failed = tk.BooleanVar(value=False)
        ttk.Checkbutton(hdr, text="Show failed only", variable=self._only_failed,
                        bootstyle="round-toggle",
                        command=self._fill_list).pack(side=RIGHT)

        body = tk.Frame(self, bg=_BG)
        body.pack(fill=BOTH, expand=True, padx=8, pady=(0, 8))

        left = tk.Frame(body, bg=_BG, width=300)
        left.pack(side=LEFT, fill=Y)
        left.pack_propagate(False)
        self._tree = ttk.Treeview(left, columns=("exit",), show="tree headings",
                                  selectmode="browse")
        self._tree.heading("#0", text="Server")
        self._tree.heading("exit", text="Exit")
        self._tree.column("exit", width=50, anchor="center")
        lvsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=lvsb.set)
        lvsb.pack(side=RIGHT, fill=Y)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)
        self._tree.tag_configure("ok",   foreground="#73d216")
        self._tree.tag_configure("fail", foreground="#ef2929")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        right = tk.Frame(body, bg=_BG)
        right.pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 0))
        self._out = tk.Text(right, bg="#11111b", fg=_TEXT, relief=FLAT,
                            font=("Consolas", 10), wrap="word",
                            highlightthickness=0)
        ovsb = ttk.Scrollbar(right, orient="vertical", command=self._out.yview)
        self._out.configure(yscrollcommand=ovsb.set, state="disabled")
        ovsb.pack(side=RIGHT, fill=Y)
        self._out.pack(side=LEFT, fill=BOTH, expand=True)
        self._out.tag_configure("err", foreground="#ff8888")

        btns = tk.Frame(self, bg=_BG, padx=12)
        btns.pack(fill=X, pady=(0, 10))
        ttk.Button(btns, text="Copy all", command=self._copy_all,
                   bootstyle="secondary-outline").pack(side=LEFT)
        ttk.Button(btns, text="Close", command=self.destroy,
                   bootstyle="secondary").pack(side=RIGHT)

        self._fill_list()

    def _fill_list(self):
        self._tree.delete(*self._tree.get_children())
        for name in sorted(self._results):
            r = self._results[name]
            ok = r.get("ok")
            if self._only_failed.get() and ok:
                continue
            icon = "✓" if ok else "✗"
            exit_s = "" if r.get("exit_status") is None else str(r["exit_status"])
            self._tree.insert("", "end", iid=name, text=f"{icon}  {name}",
                              values=(exit_s,), tags=("ok" if ok else "fail",))
        kids = self._tree.get_children()
        if kids:
            self._tree.selection_set(kids[0])
            self._tree.see(kids[0])

    def _on_select(self, _e=None):
        sel = self._tree.selection()
        if not sel:
            return
        r = self._results.get(sel[0])
        if not r:
            return
        self._out.configure(state="normal")
        self._out.delete("1.0", "end")
        if r.get("error"):
            self._out.insert("end", f"[connection error] {r['error']}\n", "err")
        if r.get("stdout"):
            self._out.insert("end", r["stdout"])
        if r.get("stderr"):
            self._out.insert("end", "\n[stderr]\n", "err")
            self._out.insert("end", r["stderr"], "err")
        if not (r.get("error") or r.get("stdout") or r.get("stderr")):
            self._out.insert("end", "(no output)")
        self._out.configure(state="disabled")

    def _copy_all(self):
        parts = []
        for name in sorted(self._results):
            r = self._results[name]
            parts.append(f"===== {name} ({r['host']}) — "
                         f"{'OK' if r.get('ok') else 'FAIL'} "
                         f"exit={r.get('exit_status')} =====")
            if r.get("error"):
                parts.append(f"[error] {r['error']}")
            if r.get("stdout"):
                parts.append(r["stdout"].rstrip())
            if r.get("stderr"):
                parts.append("[stderr] " + r["stderr"].rstrip())
            parts.append("")
        try:
            self.clipboard_clear()
            self.clipboard_append("\n".join(parts))
        except Exception:
            pass
