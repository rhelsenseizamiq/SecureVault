"""
SSH session add/edit dialog — tabbed: Basic | Jump Host | Port Forwarding | SSH Keys.
Group field with dropdown of existing groups.
"""
import io
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Dict, List, Optional

import ttkbootstrap as ttk
from ttkbootstrap.constants import *

from zterm.session_store import PortForward, SSHSession


class ZTermSessionDialog(ttk.Toplevel):
    def __init__(self, parent,
                 credentials: dict,
                 on_save: Callable[[SSHSession], None],
                 session: Optional[SSHSession] = None,
                 existing_groups: Optional[List[str]] = None):
        super().__init__(parent)
        self.title("Edit SSH Session" if session else "New SSH Session")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._creds   = credentials
        self._on_save = on_save
        self._session = session
        self._groups  = existing_groups or []

        self._pf_rows: List[dict] = []   # port-forward UI rows

        self._build()
        if session:
            self._populate(session)

        self.update_idletasks()
        w, h = 520, 520
        x = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.wait_window()

    # ================================================================== build

    def _build(self) -> None:
        main = ttk.Frame(self, padding=12)
        main.pack(fill=BOTH, expand=YES)

        nb = ttk.Notebook(main)
        nb.pack(fill=BOTH, expand=YES, pady=(0, 10))

        self._build_basic(nb)
        self._build_jump(nb)
        self._build_pf(nb)
        self._build_keys(nb)

        bf = ttk.Frame(main)
        bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=self.destroy,
                   bootstyle="secondary", width=10).pack(side=RIGHT, padx=(6, 0))
        ttk.Button(bf, text="Save", command=self._save,
                   bootstyle="primary", width=10).pack(side=RIGHT)

    # ------------------------------------------------------------------ Tab 1: Basic

    def _build_basic(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Basic  ")

        def row(label, r):
            ttk.Label(f, text=label, bootstyle="secondary",
                      font=("Segoe UI", 9)).grid(row=r, column=0, sticky=W, pady=(4, 2))

        row("Session Name", 0)
        self._name_var = ttk.StringVar()
        ttk.Entry(f, textvariable=self._name_var).grid(
            row=1, column=0, columnspan=3, sticky=EW, pady=(0, 6))

        row("Group / Folder", 2)
        self._group_var = ttk.StringVar()
        group_cb = ttk.Combobox(f, textvariable=self._group_var,
                                values=["(no group)"] + self._groups, width=28)
        group_cb.grid(row=3, column=0, columnspan=3, sticky=EW, pady=(0, 6))
        ttk.Label(f, text="Type a new group name or pick existing",
                  font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=4, column=0, columnspan=3, sticky=W, pady=(0, 8))

        row("Host / IP", 5)
        self._host_var = ttk.StringVar()
        ttk.Entry(f, textvariable=self._host_var, width=28).grid(
            row=6, column=0, sticky=EW, padx=(0, 6))

        ttk.Label(f, text="Port", bootstyle="secondary",
                  font=("Segoe UI", 9)).grid(row=5, column=1, sticky=W)
        self._port_var = ttk.StringVar(value="22")
        ttk.Entry(f, textvariable=self._port_var, width=7).grid(
            row=6, column=1, sticky=W, pady=(0, 6))

        row("Username", 7)
        self._user_var = ttk.StringVar()
        ttk.Entry(f, textvariable=self._user_var).grid(
            row=8, column=0, columnspan=3, sticky=EW, pady=(0, 8))

        # Auth
        ttk.Label(f, text="Authentication", bootstyle="secondary",
                  font=("Segoe UI", 9)).grid(row=9, column=0, sticky=W)
        self._auth_var = ttk.StringVar(value="password")
        af = ttk.Frame(f)
        af.grid(row=10, column=0, columnspan=3, sticky=EW, pady=(2, 8))
        ttk.Radiobutton(af, text="Password",    variable=self._auth_var,
                        value="password", command=self._auth_changed).pack(side=LEFT, padx=(0, 14))
        ttk.Radiobutton(af, text="Private Key", variable=self._auth_var,
                        value="key",      command=self._auth_changed).pack(side=LEFT)

        # Password source
        self._pass_frame = ttk.LabelFrame(f, text="Password Source", padding=8)
        self._pass_frame.grid(row=11, column=0, columnspan=3, sticky=EW, pady=(0, 4))

        ttk.Label(self._pass_frame,
                  text="Pick a stored SecureVault credential (uses its password automatically):",
                  font=("Segoe UI", 8), bootstyle="secondary").pack(anchor=W)
        vault_names = sorted(self._creds.keys()) if self._creds else []
        self._vault_var = ttk.StringVar(value="(enter manually each time)")
        ttk.Combobox(self._pass_frame, textvariable=self._vault_var,
                     values=["(enter manually each time)"] + vault_names,
                     state="readonly").pack(fill=X, pady=(4, 0))

        # Key source
        self._key_frame = ttk.LabelFrame(f, text="Private Key File", padding=8)
        self._key_var = ttk.StringVar()
        kr = ttk.Frame(self._key_frame)
        kr.pack(fill=X)
        ttk.Entry(kr, textvariable=self._key_var).pack(side=LEFT, fill=X, expand=True)
        ttk.Button(kr, text="Browse", bootstyle="secondary-outline",
                   command=self._browse_key, padding=(5, 2)).pack(side=LEFT, padx=(5, 0))

        f.columnconfigure(0, weight=1)
        self._auth_changed()

    def _auth_changed(self) -> None:
        if self._auth_var.get() == "password":
            try: self._key_frame.grid_remove()
            except Exception: pass
            self._pass_frame.grid()
        else:
            self._pass_frame.grid_remove()
            self._key_frame.grid(row=11, column=0, columnspan=3, sticky=EW, pady=(0, 4))

    def _browse_key(self) -> None:
        p = filedialog.askopenfilename(title="Select private key file", parent=self)
        if p:
            self._key_var.set(p)

    # ------------------------------------------------------------------ Tab 2: Jump Host

    def _build_jump(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Jump Host  ")

        ttk.Label(f, text="Connect through a bastion / jump server before reaching the target.",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 10))

        def row(parent, label, var, width=30, show=""):
            ttk.Label(parent, text=label, font=("Segoe UI", 9),
                      bootstyle="secondary").pack(anchor=W, pady=(6, 2))
            e = ttk.Entry(parent, textvariable=var, width=width, show=show)
            e.pack(fill=X)

        self._jhost_var = ttk.StringVar()
        row(f, "Jump Host (leave empty to disable)", self._jhost_var)

        pr = ttk.Frame(f); pr.pack(fill=X, pady=(6, 0))
        ttk.Label(pr, text="Port", font=("Segoe UI", 9),
                  bootstyle="secondary").pack(side=LEFT)
        self._jport_var = ttk.StringVar(value="22")
        ttk.Entry(pr, textvariable=self._jport_var, width=7).pack(side=LEFT, padx=(4, 0))

        self._juser_var = ttk.StringVar()
        row(f, "Username on Jump Host", self._juser_var)

        ttk.Label(f, text="Password / Key on Jump Host",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(8, 2))
        vault_names = sorted(self._creds.keys()) if self._creds else []
        self._jvault_var = ttk.StringVar(value="(enter manually)")
        ttk.Combobox(f, textvariable=self._jvault_var,
                     values=["(enter manually)"] + vault_names,
                     state="readonly").pack(fill=X)

        self._jkey_var = ttk.StringVar()
        row(f, "OR: Private Key File for Jump Host", self._jkey_var)
        ttk.Button(f, text="Browse", bootstyle="secondary-outline",
                   command=lambda: self._jkey_var.set(
                       filedialog.askopenfilename(title="Jump host key", parent=self) or self._jkey_var.get()),
                   padding=(5, 2)).pack(anchor=W, pady=(3, 0))

    # ------------------------------------------------------------------ Tab 3: Port Forwarding

    def _build_pf(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  Port Forwarding  ")

        ttk.Label(f,
                  text="Local Port Forwarding: 127.0.0.1:local_port  →  remote_host:remote_port\n"
                       "Opens automatically when this session connects.",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 8))

        btn_row = ttk.Frame(f)
        btn_row.pack(fill=X, pady=(0, 6))
        ttk.Button(btn_row, text="+ Add Rule",
                   command=self._add_pf_row, bootstyle="primary-outline",
                   padding=(6, 3)).pack(side=LEFT)

        self._pf_frame = ttk.Frame(f)
        self._pf_frame.pack(fill=BOTH, expand=True)

        # Headers
        hdr = ttk.Frame(self._pf_frame)
        hdr.pack(fill=X)
        for text, w in [("Local Port", 10), ("Remote Host", 20), ("Remote Port", 10), ("Note", 14), ("", 4)]:
            ttk.Label(hdr, text=text, font=("Segoe UI", 8, "bold"),
                      bootstyle="secondary").pack(side=LEFT, padx=2)

    def _add_pf_row(self, pf: Optional[PortForward] = None) -> None:
        row_frame = ttk.Frame(self._pf_frame)
        row_frame.pack(fill=X, pady=2)

        lp = ttk.StringVar(value=str(pf.local_port)  if pf else "")
        rh = ttk.StringVar(value=pf.remote_host       if pf else "")
        rp = ttk.StringVar(value=str(pf.remote_port)  if pf else "")
        nt = ttk.StringVar(value=pf.description       if pf else "")

        ttk.Entry(row_frame, textvariable=lp, width=9).pack(side=LEFT, padx=2)
        ttk.Entry(row_frame, textvariable=rh, width=19).pack(side=LEFT, padx=2)
        ttk.Entry(row_frame, textvariable=rp, width=9).pack(side=LEFT, padx=2)
        ttk.Entry(row_frame, textvariable=nt, width=13).pack(side=LEFT, padx=2)

        row_data = {"frame": row_frame, "lp": lp, "rh": rh, "rp": rp, "nt": nt}
        self._pf_rows.append(row_data)

        def remove():
            self._pf_rows.remove(row_data)
            row_frame.destroy()

        ttk.Button(row_frame, text="✕", command=remove,
                   bootstyle="danger-outline", padding=(3, 1)).pack(side=LEFT, padx=2)

    # ------------------------------------------------------------------ Tab 4: SSH Keys

    def _build_keys(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb, padding=14)
        nb.add(f, text="  SSH Keys  ")

        ttk.Label(f, text="Generate a new SSH key pair (saved to your .ssh folder).",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(0, 10))

        ktype_row = ttk.Frame(f); ktype_row.pack(fill=X, pady=(0, 8))
        ttk.Label(ktype_row, text="Key type:", font=("Segoe UI", 9)).pack(side=LEFT)
        self._ktype_var = ttk.StringVar(value="ed25519")
        ttk.Radiobutton(ktype_row, text="Ed25519 (recommended)", variable=self._ktype_var,
                        value="ed25519").pack(side=LEFT, padx=(8, 0))
        ttk.Radiobutton(ktype_row, text="RSA 4096", variable=self._ktype_var,
                        value="rsa").pack(side=LEFT, padx=8)

        ttk.Label(f, text="Passphrase (optional):",
                  font=("Segoe UI", 9)).pack(anchor=W, pady=(0, 3))
        self._kpass_var = ttk.StringVar()
        ttk.Entry(f, textvariable=self._kpass_var, show="•").pack(fill=X, pady=(0, 8))

        ttk.Button(f, text="Generate Key Pair", command=self._generate_keys,
                   bootstyle="success", padding=(8, 5)).pack(anchor=W)

        ttk.Label(f, text="Public Key (copy to server's ~/.ssh/authorized_keys):",
                  font=("Segoe UI", 9), bootstyle="secondary").pack(anchor=W, pady=(12, 3))
        self._pub_text = tk.Text(f, height=4, font=("Consolas", 8),
                                  bg="#1e1e1e", fg="#8ae234",
                                  wrap="word", state="disabled")
        self._pub_text.pack(fill=X)

        ttk.Button(f, text="Copy Public Key", command=self._copy_pubkey,
                   bootstyle="info-outline", padding=(6, 3)).pack(anchor=W, pady=(6, 0))

        self._gen_pub = ""

    def _generate_keys(self) -> None:
        try:
            from zterm.ssh_client import SSHConnection
            priv, pub = SSHConnection.generate_key_pair(
                key_type=self._ktype_var.get(),
                passphrase=self._kpass_var.get(),
            )
            # Save private key
            ssh_dir = Path.home() / ".ssh"
            ssh_dir.mkdir(mode=0o700, exist_ok=True)
            ktype = self._ktype_var.get()
            fname = f"id_{ktype}_zterm"
            priv_path = ssh_dir / fname
            priv_path.write_text(priv)
            priv_path.chmod(0o600)
            pub_path = ssh_dir / (fname + ".pub")
            pub_path.write_text(pub + "\n")

            self._gen_pub = pub
            self._pub_text.config(state="normal")
            self._pub_text.delete("1.0", "end")
            self._pub_text.insert("1.0", pub)
            self._pub_text.config(state="disabled")

            # Auto-fill key path in Basic tab
            self._key_var.set(str(priv_path))
            self._auth_var.set("key")
            self._auth_changed()

            messagebox.showinfo("Key Generated",
                                f"Private key saved to:\n{priv_path}\n\n"
                                "Copy the public key to the server's ~/.ssh/authorized_keys",
                                parent=self)
        except Exception as e:
            messagebox.showerror("Key Generation Failed", str(e), parent=self)

    def _copy_pubkey(self) -> None:
        if self._gen_pub:
            self.clipboard_clear()
            self.clipboard_append(self._gen_pub)
            messagebox.showinfo("Copied", "Public key copied to clipboard.", parent=self)

    # ------------------------------------------------------------------ populate

    def _populate(self, s: SSHSession) -> None:
        self._name_var.set(s.name)
        self._host_var.set(s.host)
        self._port_var.set(str(s.port))
        self._user_var.set(s.username)
        self._auth_var.set(s.auth_type)
        self._group_var.set(s.group or "(no group)")
        if s.vault_ref:
            self._vault_var.set(s.vault_ref)
        self._key_var.set(s.key_path)
        # Jump
        self._jhost_var.set(s.jump_host)
        self._jport_var.set(str(s.jump_port))
        self._juser_var.set(s.jump_user)
        if s.jump_vault_ref:
            self._jvault_var.set(s.jump_vault_ref)
        self._jkey_var.set(s.jump_key_path)
        # Port forwards
        for pf in s.port_forwards:
            self._add_pf_row(pf)
        self._auth_changed()

    # ------------------------------------------------------------------ save

    def _save(self) -> None:
        name = self._name_var.get().strip()
        host = self._host_var.get().strip()
        user = self._user_var.get().strip()

        if not name or not host or not user:
            messagebox.showerror("Missing fields",
                                 "Session Name, Host and Username are required.",
                                 parent=self)
            return
        try:
            port = int(self._port_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid port", "Port must be a number.", parent=self)
            return

        group_val = self._group_var.get().strip()
        group = "" if group_val in ("(no group)", "") else group_val

        auth_type = self._auth_var.get()
        vault_ref = key_path = ""
        if auth_type == "password":
            v = self._vault_var.get()
            vault_ref = "" if v == "(enter manually each time)" else v
        else:
            key_path = self._key_var.get().strip()

        # Jump host
        jump_host = self._jhost_var.get().strip()
        try:
            jump_port = int(self._jport_var.get().strip() or "22")
        except ValueError:
            jump_port = 22
        jump_user  = self._juser_var.get().strip()
        jv = self._jvault_var.get()
        jump_vault = "" if jv == "(enter manually)" else jv
        jump_key   = self._jkey_var.get().strip()

        # Port forwards
        pf_list = []
        for row in self._pf_rows:
            try:
                lp = int(row["lp"].get())
                rh = row["rh"].get().strip()
                rp = int(row["rp"].get())
                if lp and rh and rp:
                    pf_list.append(PortForward(lp, rh, rp, row["nt"].get().strip()))
            except ValueError:
                pass

        session = SSHSession(
            name=name, host=host, port=port, username=user,
            auth_type=auth_type, vault_ref=vault_ref, key_path=key_path,
            group=group,
            jump_host=jump_host, jump_port=jump_port, jump_user=jump_user,
            jump_vault_ref=jump_vault, jump_key_path=jump_key,
            port_forwards=pf_list,
        )
        self._on_save(session)
        self.destroy()
