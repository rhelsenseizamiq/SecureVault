"""
SFTP file browser widget — uses ttk.Treeview with paramiko SFTPClient.
All blocking SFTP operations run in daemon threads; results delivered via queue.
"""
import os
import queue
import stat
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from typing import Optional

try:
    import paramiko
except ImportError:
    paramiko = None


def _fmt_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _fmt_perms(mode: int) -> str:
    flags = "rwxrwxrwx"
    bits  = [0o400, 0o200, 0o100, 0o040, 0o020, 0o010, 0o004, 0o002, 0o001]
    d     = "d" if stat.S_ISDIR(mode) else "-"
    return d + "".join(f if mode & b else "-" for f, b in zip(flags, bits))


class SFTPBrowser(tk.Frame):
    """
    Embedded SFTP file browser.  Connect an SFTPClient with set_sftp().
    """

    BG     = "#12121f"
    HDR_BG = "#1a1a2e"
    FG     = "#d3d7cf"
    SEL    = "#1e3a5f"
    ACCENT = "#175ddc"

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=self.BG, **kwargs)
        self._sftp: Optional["paramiko.SFTPClient"] = None
        self._cwd  = "/"
        self._q:   queue.Queue = queue.Queue()
        self._build()
        self.after(200, self._poll_queue)

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        # Path bar
        nav = tk.Frame(self, bg=self.HDR_BG)
        nav.pack(fill=X)

        self._up_btn = ttk.Button(nav, text="↑ Up", command=self._go_up,
                                  bootstyle="secondary-outline", padding=(6, 2))
        self._up_btn.pack(side=LEFT, padx=(6, 2), pady=4)

        self._path_var = tk.StringVar(value="/")
        path_entry = tk.Entry(nav, textvariable=self._path_var,
                              bg="#1e1e2e", fg=self.FG, insertbackground=self.FG,
                              font=("Consolas", 10), bd=0, relief=FLAT,
                              highlightthickness=1, highlightbackground="#2e3245",
                              highlightcolor=self.ACCENT)
        path_entry.pack(side=LEFT, fill=X, expand=True, padx=4, pady=4, ipady=4)
        path_entry.bind("<Return>", lambda e: self._cd(self._path_var.get()))

        self._refresh_btn = ttk.Button(nav, text="⟳ Refresh", command=self._refresh,
                                       bootstyle="secondary-outline", padding=(6, 2))
        self._refresh_btn.pack(side=LEFT, padx=2, pady=4)

        # Action toolbar
        tb = tk.Frame(self, bg=self.HDR_BG)
        tb.pack(fill=X)
        for label, cmd, style in [
            ("⬇ Download", self._download, "primary-outline"),
            ("⬆ Upload",   self._upload,   "primary-outline"),
            ("📁 New Dir", self._mkdir,    "secondary-outline"),
            ("✏ Rename",   self._rename,   "secondary-outline"),
            ("🗑 Delete",  self._delete,   "danger-outline"),
        ]:
            ttk.Button(tb, text=label, command=cmd,
                       bootstyle=style, padding=(6, 2)).pack(side=LEFT, padx=2, pady=3)

        tk.Frame(self, bg="#2e3245", height=1).pack(fill=X)

        # Treeview
        cols = ("name", "size", "perms", "modified")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                  selectmode="browse")
        self._tree.heading("name",     text="Name",        anchor=W)
        self._tree.heading("size",     text="Size",        anchor=E)
        self._tree.heading("perms",    text="Permissions", anchor=W)
        self._tree.heading("modified", text="Modified",    anchor=W)
        self._tree.column("name",     width=260, stretch=True,  anchor=W)
        self._tree.column("size",     width=80,  stretch=False, anchor=E)
        self._tree.column("perms",    width=110, stretch=False, anchor=W)
        self._tree.column("modified", width=150, stretch=False, anchor=W)

        vsb = ttk.Scrollbar(self, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        hsb.pack(side=BOTTOM, fill=X)
        vsb.pack(side=RIGHT,  fill=Y)
        self._tree.pack(side=LEFT, fill=BOTH, expand=True)

        self._tree.bind("<Double-Button-1>", self._on_double_click)
        self._tree.bind("<Button-3>",        self._on_right_click)

        # Status bar
        self._status_var = tk.StringVar(value="Not connected")
        tk.Label(self, textvariable=self._status_var,
                 bg=self.HDR_BG, fg="#7d8fa6",
                 font=("Segoe UI", 8), anchor=W).pack(fill=X, padx=6)

    # ------------------------------------------------------------------ public

    def set_sftp(self, sftp: "paramiko.SFTPClient", start_path: str = "/") -> None:
        self._sftp = sftp
        self._cd(start_path)

    def detach(self) -> None:
        self._sftp = None
        self._status_var.set("Disconnected")

    # ------------------------------------------------------------------ navigation

    def _cd(self, path: str) -> None:
        if not self._sftp:
            return
        self._status_var.set(f"Loading {path} …")
        threading.Thread(target=self._list_dir, args=(path,), daemon=True).start()

    def _list_dir(self, path: str) -> None:
        try:
            entries = self._sftp.listdir_attr(path)
            self._q.put(("ls", path, entries))
        except Exception as e:
            self._q.put(("error", str(e), None))

    def _go_up(self) -> None:
        parent = os.path.dirname(self._cwd.rstrip("/")) or "/"
        self._cd(parent)

    def _refresh(self) -> None:
        self._cd(self._cwd)

    # ------------------------------------------------------------------ queue poll

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]
                if kind == "ls":
                    _, path, entries = msg
                    self._populate(path, entries)
                elif kind == "error":
                    _, err, _ = msg
                    messagebox.showerror("SFTP Error", err)
                    self._status_var.set("Error")
                elif kind == "done":
                    _, label = msg
                    self._status_var.set(label)
                    self._refresh()
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)

    # ------------------------------------------------------------------ populate

    def _populate(self, path: str, entries) -> None:
        self._cwd = path
        self._path_var.set(path)

        for item in self._tree.get_children():
            self._tree.delete(item)

        # Sort: dirs first, then files
        dirs  = sorted([e for e in entries if stat.S_ISDIR(e.st_mode)],
                       key=lambda e: e.filename.lower())
        files = sorted([e for e in entries if not stat.S_ISDIR(e.st_mode)],
                       key=lambda e: e.filename.lower())

        for e in dirs + files:
            is_dir = stat.S_ISDIR(e.st_mode)
            icon   = "📁" if is_dir else "📄"
            size   = "" if is_dir else _fmt_size(e.st_size or 0)
            perms  = _fmt_perms(e.st_mode) if e.st_mode else ""
            import datetime
            mtime  = (datetime.datetime.fromtimestamp(e.st_mtime).strftime("%Y-%m-%d %H:%M")
                      if e.st_mtime else "")
            self._tree.insert("", "end",
                              values=(f"{icon} {e.filename}", size, perms, mtime),
                              tags=("dir" if is_dir else "file",))

        self._tree.tag_configure("dir",  foreground="#729fcf")
        self._tree.tag_configure("file", foreground=self.FG)
        self._status_var.set(f"{path}  —  {len(entries)} items")

    # ------------------------------------------------------------------ actions

    def _on_double_click(self, _event) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        name = self._tree.item(sel[0], "values")[0].split(" ", 1)[-1]
        tags = self._tree.item(sel[0], "tags")
        if "dir" in tags:
            new_path = (self._cwd.rstrip("/") + "/" + name).replace("//", "/")
            self._cd(new_path)

    def _on_right_click(self, event) -> None:
        row = self._tree.identify_row(event.y)
        if row:
            self._tree.selection_set(row)

    def _selected_name(self) -> Optional[str]:
        sel = self._tree.selection()
        if not sel:
            return None
        return self._tree.item(sel[0], "values")[0].split(" ", 1)[-1]

    def _download(self) -> None:
        name = self._selected_name()
        if not name or not self._sftp:
            return
        remote = (self._cwd.rstrip("/") + "/" + name).replace("//", "/")
        local = filedialog.asksaveasfilename(initialfile=name, title="Save file as")
        if not local:
            return
        def _do():
            try:
                self._sftp.get(remote, local)
                self._q.put(("done", f"Downloaded {name}"))
            except Exception as e:
                self._q.put(("error", str(e), None))
        threading.Thread(target=_do, daemon=True).start()
        self._status_var.set(f"Downloading {name} …")

    def _upload(self) -> None:
        if not self._sftp:
            return
        local = filedialog.askopenfilename(title="Upload file")
        if not local:
            return
        name   = os.path.basename(local)
        remote = (self._cwd.rstrip("/") + "/" + name).replace("//", "/")
        def _do():
            try:
                self._sftp.put(local, remote)
                self._q.put(("done", f"Uploaded {name}"))
            except Exception as e:
                self._q.put(("error", str(e), None))
        threading.Thread(target=_do, daemon=True).start()
        self._status_var.set(f"Uploading {name} …")

    def _mkdir(self) -> None:
        if not self._sftp:
            return
        dlg = _InputDialog(self, "New Directory", "Directory name:")
        if dlg.result:
            remote = (self._cwd.rstrip("/") + "/" + dlg.result).replace("//", "/")
            try:
                self._sftp.mkdir(remote)
                self._refresh()
            except Exception as e:
                messagebox.showerror("SFTP Error", str(e))

    def _rename(self) -> None:
        name = self._selected_name()
        if not name or not self._sftp:
            return
        old = (self._cwd.rstrip("/") + "/" + name).replace("//", "/")
        dlg = _InputDialog(self, "Rename", "New name:", initial=name)
        if dlg.result:
            new = (self._cwd.rstrip("/") + "/" + dlg.result).replace("//", "/")
            try:
                self._sftp.rename(old, new)
                self._refresh()
            except Exception as e:
                messagebox.showerror("SFTP Error", str(e))

    def _delete(self) -> None:
        name = self._selected_name()
        if not name or not self._sftp:
            return
        if not messagebox.askyesno("Delete", f"Delete '{name}'?\nThis cannot be undone."):
            return
        remote = (self._cwd.rstrip("/") + "/" + name).replace("//", "/")
        tags   = self._tree.item(self._tree.selection()[0], "tags")
        def _do():
            try:
                if "dir" in tags:
                    self._sftp.rmdir(remote)
                else:
                    self._sftp.remove(remote)
                self._q.put(("done", f"Deleted {name}"))
            except Exception as e:
                self._q.put(("error", str(e), None))
        threading.Thread(target=_do, daemon=True).start()


# ---------------------------------------------------------------------------
# Simple inline input dialog
# ---------------------------------------------------------------------------

class _InputDialog(ttk.Toplevel):
    def __init__(self, parent, title: str, label: str, initial: str = ""):
        super().__init__(parent)
        self.title(title)
        self.result: Optional[str] = None
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        f = ttk.Frame(self, padding=16)
        f.pack(fill=BOTH, expand=YES)
        ttk.Label(f, text=label).pack(anchor=W, pady=(0, 6))

        self._var = ttk.StringVar(value=initial)
        entry = ttk.Entry(f, textvariable=self._var, width=36)
        entry.pack(fill=X, pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._ok())

        bf = ttk.Frame(f)
        bf.pack(fill=X)
        ttk.Button(bf, text="OK",     command=self._ok,     bootstyle="primary", width=10).pack(side=RIGHT, padx=(4, 0))
        ttk.Button(bf, text="Cancel", command=self.destroy, bootstyle="secondary", width=10).pack(side=RIGHT)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
        self.wait_window()

    def _ok(self) -> None:
        self.result = self._var.get().strip() or None
        self.destroy()
