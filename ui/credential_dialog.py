"""
Credential add/edit/view dialog — scrollable, fits any screen size
"""
import tkinter as tk
import webbrowser
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from models.credential import Credential
from utils.validators import validate_service_name, validate_username
from utils.password_strength import estimate_password_strength, get_strength_color
from ui.password_generator import show_password_generator


class CredentialDialog:
    """Dialog for adding, editing, or viewing credentials."""

    MODE_ADD  = "add"
    MODE_EDIT = "edit"
    MODE_VIEW = "view"

    def __init__(self, parent, mode=MODE_ADD, credential=None, existing_services=None,
                 on_save=None, clipboard_manager=None):
        self.parent = parent
        self.mode = mode
        self.credential = credential
        self.existing_services = existing_services or set()
        self.on_save = on_save
        self.clipboard_manager = clipboard_manager
        self.show_password = False

        self.window = ttk.Toplevel(parent)
        self._set_title()
        self.window.resizable(True, True)
        self.window.transient(parent)
        self.window.grab_set()

        # Size: leave room so buttons are always visible
        w = 500
        # Use 85% of screen height, max 560
        screen_h = self.window.winfo_screenheight()
        h = min(560, int(screen_h * 0.85))

        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (w // 2)
        y = (self.window.winfo_screenheight() // 2) - (h // 2)
        self.window.geometry(f"{w}x{h}+{x}+{y}")
        self.window.minsize(460, 400)

        self._create_widgets()

    def _set_title(self):
        titles = {self.MODE_ADD: "Add New Item",
                  self.MODE_EDIT: "Edit Item",
                  self.MODE_VIEW: "View Item"}
        self.window.title(titles.get(self.mode, "Credential"))

    def _create_widgets(self):
        if self.mode == self.MODE_VIEW:
            self._create_view_widgets()
        else:
            self._create_edit_widgets()

    # ------------------------------------------------------------------ view
    def _create_view_widgets(self):
        outer = ttk.Frame(self.window)
        outer.pack(fill=BOTH, expand=YES)

        main_frame = ttk.Frame(outer, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        ttk.Label(main_frame, text=self.credential.service_name,
                 font=("Segoe UI", 16, "bold")).pack(anchor=W, pady=(0, 3))

        if self.credential.website_url:
            url_lbl = ttk.Label(main_frame, text=self.credential.website_url,
                               font=("Segoe UI", 9), bootstyle="info", cursor="hand2")
            url_lbl.pack(anchor=W, pady=(0, 12))
            url_lbl.bind("<Button-1>", lambda e: self._open_url(self.credential.website_url))
        else:
            ttk.Frame(main_frame, height=12).pack()

        ttk.Separator(main_frame).pack(fill=X, pady=(0, 15))

        # USERNAME
        ttk.Label(main_frame, text="USERNAME", font=("Segoe UI", 8),
                 bootstyle="secondary").pack(anchor=W)
        urow = ttk.Frame(main_frame)
        urow.pack(fill=X, pady=(3, 12))
        ttk.Label(urow, text=self.credential.username,
                 font=("Segoe UI", 11)).pack(side=LEFT)
        ttk.Button(urow, text="Copy", command=self._copy_username,
                  bootstyle="info-outline", width=8).pack(side=RIGHT)

        # PASSWORD
        ttk.Label(main_frame, text="PASSWORD", font=("Segoe UI", 8),
                 bootstyle="secondary").pack(anchor=W)
        prow = ttk.Frame(main_frame)
        prow.pack(fill=X, pady=(3, 12))

        self.password_display = ttk.Label(prow, text="••••••••", font=("Courier New", 11))
        self.password_display.pack(side=LEFT)

        bgrp = ttk.Frame(prow)
        bgrp.pack(side=RIGHT)
        self.show_btn = ttk.Button(bgrp, text="Show", command=self._toggle_password,
                                  bootstyle="secondary-outline", width=7)
        self.show_btn.pack(side=LEFT, padx=(0, 5))
        ttk.Button(bgrp, text="Copy", command=self._copy_password,
                  bootstyle="info-outline", width=7).pack(side=LEFT)

        # Strength
        score, label, _ = estimate_password_strength(self.credential.password)
        srow = ttk.Frame(main_frame)
        srow.pack(fill=X, pady=(0, 12))
        ttk.Label(srow, text="Strength:", font=("Segoe UI", 9)).pack(side=LEFT)
        ttk.Label(srow, text=label, font=("Segoe UI", 9, "bold"),
                 foreground=get_strength_color(score)).pack(side=LEFT, padx=(5, 0))

        # TAGS
        if self.credential.tags:
            ttk.Label(main_frame, text="TAGS", font=("Segoe UI", 8),
                     bootstyle="secondary").pack(anchor=W)
            ttk.Label(main_frame, text="  ".join(f"#{t}" for t in self.credential.tags),
                     font=("Segoe UI", 10), bootstyle="info").pack(anchor=W, pady=(3, 12))

        # NOTES
        if self.credential.notes:
            ttk.Label(main_frame, text="NOTES", font=("Segoe UI", 8),
                     bootstyle="secondary").pack(anchor=W)
            ttk.Label(main_frame, text=self.credential.notes, font=("Segoe UI", 10),
                     wraplength=440, justify=LEFT).pack(anchor=W, pady=(3, 12))

        # WEBSITE
        if self.credential.website_url:
            ttk.Label(main_frame, text="WEBSITE", font=("Segoe UI", 8),
                     bootstyle="secondary").pack(anchor=W)
            wrow = ttk.Frame(main_frame)
            wrow.pack(fill=X, pady=(3, 12))
            ttk.Label(wrow, text=self.credential.website_url,
                     font=("Segoe UI", 10)).pack(side=LEFT)
            ttk.Button(wrow, text="Open",
                      command=lambda: self._open_url(self.credential.website_url),
                      bootstyle="info-outline", width=8).pack(side=RIGHT)

        ttk.Button(main_frame, text="Close", command=self.window.destroy,
                  bootstyle="secondary", width=12).pack(pady=(10, 0))

    # ------------------------------------------------------------------ edit/add (scrollable)
    def _create_edit_widgets(self):
        # Scrollable canvas wrapper so nothing is ever cut off
        canvas = tk.Canvas(self.window, highlightthickness=0)
        vsb = ttk.Scrollbar(self.window, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)

        vsb.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        inner = ttk.Frame(canvas, padding=20)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(win_id, width=e.width)

        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self._build_edit_form(inner)

    def _build_edit_form(self, f):
        title_text = "Add New Item" if self.mode == self.MODE_ADD else "Edit Item"
        ttk.Label(f, text=title_text,
                 font=("Segoe UI", 15, "bold")).pack(anchor=W, pady=(0, 15))

        # Service Name
        ttk.Label(f, text="Service Name", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        self.service_var = ttk.StringVar(value=self.credential.service_name if self.credential else "")
        svc = ttk.Entry(f, textvariable=self.service_var, font=("Segoe UI", 11))
        svc.pack(fill=X, pady=(0, 12))
        if self.mode == self.MODE_ADD:
            svc.focus()

        # Website URL
        ttk.Label(f, text="Website URL  (optional)", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        self.url_var = ttk.StringVar(value=self.credential.website_url if self.credential else "")
        ttk.Entry(f, textvariable=self.url_var, font=("Segoe UI", 11)).pack(fill=X, pady=(0, 12))

        # Tags (comma-separated)
        ttk.Label(f, text="Tags  (comma-separated, optional)", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        tags_init = ", ".join(self.credential.tags) if self.credential else ""
        self.tags_var = ttk.StringVar(value=tags_init)
        ttk.Entry(f, textvariable=self.tags_var, font=("Segoe UI", 11)).pack(fill=X, pady=(0, 12))

        # Username
        ttk.Label(f, text="Username", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        self.username_var = ttk.StringVar(value=self.credential.username if self.credential else "")
        ttk.Entry(f, textvariable=self.username_var, font=("Segoe UI", 11)).pack(fill=X, pady=(0, 12))

        # Password
        ttk.Label(f, text="Password", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        prow = ttk.Frame(f)
        prow.pack(fill=X, pady=(0, 8))

        self.password_var = ttk.StringVar(value=self.credential.password if self.credential else "")
        self.password_entry = ttk.Entry(prow, textvariable=self.password_var,
                                        font=("Courier New", 11), show="•")
        self.password_entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, 8))
        self.password_var.trace('w', self._update_strength)

        self.show_btn = ttk.Button(prow, text="Show", command=self._toggle_password_entry,
                                  bootstyle="secondary-outline", width=7)
        self.show_btn.pack(side=LEFT)

        # Generate button
        ttk.Button(f, text="⚡ Generate Password", command=self._generate_password,
                  bootstyle="info-outline").pack(anchor=W, pady=(0, 8))

        # Strength row
        srow = ttk.Frame(f)
        srow.pack(fill=X, pady=(0, 3))
        ttk.Label(srow, text="Strength:", font=("Segoe UI", 9)).pack(side=LEFT)
        self.strength_label = ttk.Label(srow, text="", font=("Segoe UI", 9, "bold"))
        self.strength_label.pack(side=LEFT, padx=(5, 0))

        self.feedback_label = ttk.Label(f, text="", font=("Segoe UI", 8),
                                       bootstyle="secondary", wraplength=420)
        self.feedback_label.pack(fill=X, pady=(0, 15))

        self._update_strength()

        # Notes (multiline, optional)
        ttk.Label(f, text="Notes  (optional)", font=("Segoe UI", 9),
                 bootstyle="secondary").pack(anchor=W, pady=(0, 3))
        self.notes_text = tk.Text(f, height=4, font=("Segoe UI", 10), wrap="word",
                                  relief="flat", highlightthickness=1,
                                  highlightbackground="#3a3f4b")
        self.notes_text.pack(fill=X, pady=(0, 12))
        if self.credential and self.credential.notes:
            self.notes_text.insert("1.0", self.credential.notes)

        ttk.Separator(f).pack(fill=X, pady=(0, 12))

        # Save / Cancel — always visible at bottom of scroll area
        brow = ttk.Frame(f)
        brow.pack(fill=X)
        ttk.Button(brow, text="Cancel", command=self.window.destroy,
                  bootstyle="secondary", width=12).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(brow, text="Save", command=self._save,
                  bootstyle="success", width=12).pack(side=RIGHT)

    # ------------------------------------------------------------------ helpers
    def _toggle_password(self):
        self.show_password = not self.show_password
        if self.show_password:
            self.password_display.config(text=self.credential.password)
            self.show_btn.config(text="Hide")
        else:
            self.password_display.config(text="••••••••")
            self.show_btn.config(text="Show")

    def _toggle_password_entry(self):
        if self.password_entry.cget('show') == '•':
            self.password_entry.config(show='')
            self.show_btn.config(text="Hide")
        else:
            self.password_entry.config(show='•')
            self.show_btn.config(text="Show")

    def _update_strength(self, *args):
        score, label, feedback = estimate_password_strength(self.password_var.get())
        self.strength_label.config(text=label, foreground=get_strength_color(score))
        self.feedback_label.config(text=feedback)

    def _generate_password(self):
        def on_generated(password):
            self.password_var.set(password)
        show_password_generator(self.window, callback=on_generated)

    def _open_url(self, url: str):
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        webbrowser.open(url)

    def _copy_username(self):
        self._copy(self.credential.username)

    def _copy_password(self):
        self._copy(self.credential.password)

    def _copy(self, text: str):
        if self.clipboard_manager:
            from ui.settings_dialog import SettingsManager
            settings = SettingsManager.load_settings()
            self.clipboard_manager.copy_with_autoclear(text, settings['clipboard_clear_seconds'])
        else:
            self.window.clipboard_clear()
            self.window.clipboard_append(text)

    def _save(self):
        service  = self.service_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get()
        url      = self.url_var.get().strip()

        old_service    = self.credential.service_name if self.credential else None
        allow_existing = (self.mode == self.MODE_EDIT and service == old_service)

        valid, error = validate_service_name(service, self.existing_services, allow_existing)
        if not valid:
            messagebox.showerror("Invalid Service Name", error)
            return

        valid, error = validate_username(username)
        if not valid:
            messagebox.showerror("Invalid Username", error)
            return

        if not password:
            messagebox.showerror("Invalid Password", "Password cannot be empty")
            return

        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        notes = self.notes_text.get("1.0", "end-1c").strip()

        new_credential = Credential(
            service_name=service,
            username=username,
            password=password,
            website_url=url,
            notes=notes,
            tags=tags,
            # Preserve flags/usage when editing an existing item.
            favorite=self.credential.favorite if self.credential else False,
            last_used=self.credential.last_used if self.credential else 0.0,
        )

        if self.on_save:
            self.on_save(new_credential, old_service)

        self.window.destroy()
