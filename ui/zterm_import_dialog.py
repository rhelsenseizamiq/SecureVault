"""
Import-from-MobaXterm dialog.

Parses MobaXterm.ini, previews the SSH sessions it finds, lets the user pick a
grouping scheme and (optionally) map each MobaXterm credential tag to a stored
SecureVault entry, then hands the built SSHSession list back via on_import().
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, List, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from zterm.mobaxterm_import import MobaSession, find_mobaxterm_ini, parse_sessions
from zterm.session_store import SSHSession


class ZTermImportDialog(ttk.Toplevel):
    def __init__(self, parent,
                 get_credentials: Callable[[], dict],
                 on_import: Callable[[List[SSHSession]], None]):
        super().__init__(parent)
        self.title("Import Sessions from MobaXterm")
        self.transient(parent)
        self.grab_set()

        self._get_creds = get_credentials
        self._on_import = on_import
        self._sessions: List[MobaSession] = []

        self._build()

        # Auto-detect on open
        found = find_mobaxterm_ini()
        if found:
            self._load(found)

        self.update_idletasks()
        w, h = 720, 560
        x = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{max(x,0)}+{max(y,0)}")
        self.minsize(560, 420)
        self.wait_window()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        f = ttk.Frame(self, padding=12)
        f.pack(fill=BOTH, expand=YES)

        # ── File row ──────────────────────────────────────────────────
        file_row = ttk.Frame(f)
        file_row.pack(fill=X, pady=(0, 8))
        ttk.Label(file_row, text="MobaXterm.ini:",
                  font=("Segoe UI", 9)).pack(side=LEFT)
        self._path_var = ttk.StringVar(value="(not found — click Browse)")
        ttk.Entry(file_row, textvariable=self._path_var,
                  state="readonly").pack(side=LEFT, fill=X, expand=True, padx=6)
        ttk.Button(file_row, text="Browse…", command=self._browse,
                   bootstyle="secondary-outline", padding=(6, 2)).pack(side=LEFT)

        self._count_var = ttk.StringVar(value="No file loaded.")
        ttk.Label(f, textvariable=self._count_var, bootstyle="secondary",
                  font=("Segoe UI", 9)).pack(anchor=W, pady=(0, 6))

        # ── Preview table ─────────────────────────────────────────────
        table = ttk.Frame(f)
        table.pack(fill=BOTH, expand=YES)
        cols = ("name", "host", "port", "user")
        self._tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="none")
        for col, txt, w in [("name", "Session", 300), ("host", "Host", 180),
                            ("port", "Port", 60), ("user", "User", 120)]:
            self._tree.heading(col, text=txt, anchor=W)
            self._tree.column(col, width=w, anchor=W,
                             stretch=(col in ("name", "host")))
        vsb = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=RIGHT, fill=Y)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)

        # ── Options ───────────────────────────────────────────────────
        # Note: ttk.LabelFrame doesn't accept `padding=` on all Tk builds —
        # use an inner padded ttk.Frame instead.
        opt_box = ttk.LabelFrame(f, text="Import Options")
        opt_box.pack(fill=X, pady=(8, 8))
        opt = ttk.Frame(opt_box, padding=10)
        opt.pack(fill=X)

        ttk.Label(opt, text="Group sessions by:",
                  font=("Segoe UI", 9)).grid(row=0, column=0, sticky=W, pady=(0, 4))
        self._group_var = ttk.StringVar(value="tag")
        grp = ttk.Frame(opt)
        grp.grid(row=1, column=0, columnspan=3, sticky=W)
        for val, label in [
            ("tag",    "Credential tag (ansible, ansible_new…)"),
            ("single", "Single group 'MobaXterm'"),
            ("folder", "MobaXterm folders"),
            ("flat",   "No groups"),
        ]:
            ttk.Radiobutton(grp, text=label, value=val,
                            variable=self._group_var).pack(side=LEFT, padx=(0, 12))

        # Per-tag vault mapping (built after a file loads)
        self._map_frame = ttk.Frame(opt)
        self._map_frame.grid(row=2, column=0, columnspan=3, sticky=EW, pady=(8, 0))
        self._tag_vault_vars: dict = {}

        opt.columnconfigure(0, weight=1)

        # ── Buttons ───────────────────────────────────────────────────
        bf = ttk.Frame(f)
        bf.pack(fill=X)
        self._import_btn = ttk.Button(bf, text="Import", command=self._do_import,
                                      bootstyle="primary", width=12, state="disabled")
        self._import_btn.pack(side=RIGHT, padx=(6, 0))
        ttk.Button(bf, text="Cancel", command=self.destroy,
                   bootstyle="secondary", width=12).pack(side=RIGHT)

    # ------------------------------------------------------------------ load

    def _browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select MobaXterm.ini",
            filetypes=[("MobaXterm config", "*.ini"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        try:
            self._sessions = parse_sessions(path)
        except Exception as e:
            messagebox.showerror("Parse error", f"Could not read MobaXterm.ini:\n{e}",
                                 parent=self)
            return

        self._path_var.set(str(path))

        # Populate preview
        self._tree.delete(*self._tree.get_children())
        for s in self._sessions:
            self._tree.insert("", "end",
                              values=(s.name, s.host, s.port, s.username or "—"))

        n = len(self._sessions)
        self._count_var.set(f"{n} SSH session(s) found.")
        self._import_btn.configure(state="normal" if n else "disabled")

        self._build_tag_mapping()

    def _build_tag_mapping(self) -> None:
        """One vault-credential combobox per distinct non-empty credential tag."""
        for child in self._map_frame.winfo_children():
            child.destroy()
        self._tag_vault_vars.clear()

        tags = sorted({s.tag for s in self._sessions if s.tag})
        if not tags:
            return

        creds = self._get_creds() or {}
        vault_names = ["(none — enter on connect)"] + sorted(creds.keys())

        ttk.Label(self._map_frame,
                  text="Use a stored SecureVault password for each tag (optional):",
                  font=("Segoe UI", 8), bootstyle="secondary").grid(
                      row=0, column=0, columnspan=2, sticky=W, pady=(0, 4))
        for i, tag in enumerate(tags, start=1):
            ttk.Label(self._map_frame, text=f"   {tag}:",
                      font=("Segoe UI", 9)).grid(row=i, column=0, sticky=W, pady=1)
            var = ttk.StringVar(value="(none — enter on connect)")
            # Auto-select a vault entry whose name matches the tag, if present
            for vn in creds:
                if vn.lower() == tag.lower():
                    var.set(vn)
                    break
            ttk.Combobox(self._map_frame, textvariable=var, values=vault_names,
                         state="readonly", width=32).grid(
                             row=i, column=1, sticky=W, padx=(6, 0), pady=1)
            self._tag_vault_vars[tag] = var

    # ------------------------------------------------------------------ import

    def _do_import(self) -> None:
        mode = self._group_var.get()
        result: List[SSHSession] = []
        for s in self._sessions:
            if mode == "tag":
                group = s.tag
            elif mode == "single":
                group = "MobaXterm"
            elif mode == "folder":
                group = s.folder
            else:
                group = ""

            vault_ref = ""
            var = self._tag_vault_vars.get(s.tag)
            if var:
                v = var.get()
                if v and not v.startswith("("):
                    vault_ref = v

            result.append(SSHSession(
                name=s.name, host=s.host, port=s.port,
                username=s.username, auth_type="password",
                vault_ref=vault_ref, group=group,
            ))

        self._on_import(result)
        self.destroy()
