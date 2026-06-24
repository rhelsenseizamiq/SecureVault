"""
Login and Initial Setup Window

Handles user authentication and first-time setup for SecureVault.
Creates the master password on first run, or verifies it on subsequent logins.
"""
import time
import random
import string
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from database.master_password_store import MasterPasswordStore
from database.migration import LegacyMigration
from utils.password_strength import estimate_password_strength, get_strength_color
from utils.validators import validate_password_strength
from config import MAX_LOGIN_ATTEMPTS, LOGIN_COOLDOWN_SECONDS, MIN_MASTER_PASSWORD_LENGTH


class LoginWindow:
    """Login window with setup and migration support."""

    def __init__(self, root, on_success):
        """
        Initialize login window.

        Args:
            root: Root ttkbootstrap window
            on_success: Callback(master_password, salt) called on successful login
        """
        self.root = root
        self.on_success = on_success
        self.failed_attempts = 0
        self.cooldown_until = 0
        self.setup_mode = not MasterPasswordStore.exists()
        self.needs_migration = LegacyMigration.needs_migration()

        # If needs migration, force setup mode
        if self.needs_migration:
            self.setup_mode = True

        self._create_widgets()

    def _create_widgets(self):
        """Create login window widgets."""
        # Main container
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=BOTH, expand=YES)

        # Full-screen Matrix-style digital rain background, for fun :)
        self._build_animated_background(self.main_frame)
        canvas = self._canvas

        # Semi-transparent "glass" card drawn on the canvas. The stipple dither
        # lets the rain behind show through faintly, so rain is visible even
        # behind the card — positioned by _layout_card().
        self._card_id = canvas.create_rectangle(
            0, 0, 0, 0, fill="#0d0d12", outline="#22c55e", width=1,
            stipple="gray75", tags="card")
        self._title_id = canvas.create_text(
            0, 0, text="🔐 SecureVault", fill="#ffffff",
            font=("Segoe UI", 26, "bold"), tags="cardtext")
        self._subtitle_id = canvas.create_text(
            0, 0, text="Secure Password Storage", fill="#9aa0a6",
            font=("Segoe UI", 11), tags="cardtext")

        # Only the interactive controls sit in a solid block (kept tight so the
        # faint rain shows around them). Migration can clear just this host.
        self._form_host = ttk.Frame(canvas, bootstyle="dark")
        self._form_win = canvas.create_window(
            0, 0, window=self._form_host, anchor="n", tags="cardform")

        # Show migration notice if needed
        if self.needs_migration:
            self._show_migration_notice()
        elif self.setup_mode:
            self._show_setup_form()
        else:
            self._show_login_form()

        self._relayout()

    # ------------------------------------------------------------------ fun rain
    _ANIM_CELL = 16        # rain cell height (px)
    _ANIM_COL_W = 14       # rain column width (px)
    _ANIM_SHADES = ["#0a3d1a", "#0f5a26", "#15803d",
                    "#22c55e", "#4ade80", "#bbf7d0"]   # tail → bright head

    def _build_animated_background(self, parent):
        """A full-window Matrix-rain canvas. The login card floats on top."""
        try:
            bg = ttk.Style().lookup("TFrame", "background") or "#0d0d12"
        except Exception:
            bg = "#0d0d12"

        self._anim_chars = string.ascii_letters + string.digits + "$#@%&*+=/<>?!"
        self._anim_font  = ("Consolas", 11, "bold")
        self._anim_cols  = []      # per-column [head_row(float), speed(rows/frame)]
        self._anim_w     = 0
        self._anim_h     = 0
        self._anim_id    = None

        canvas = tk.Canvas(parent, bg=bg, highlightthickness=0, bd=0)
        canvas.pack(fill=BOTH, expand=YES)
        self._canvas = canvas
        canvas.bind("<Configure>", self._on_anim_configure)
        # Cancel the loop when the canvas goes away (login succeeds → frame
        # destroyed) so no stale after() callback fires into a dead widget.
        canvas.bind("<Destroy>", lambda e: self._stop_animation())
        self._animate()

    def _stop_animation(self):
        """Cancel the pending rain frame, if any."""
        if getattr(self, "_anim_id", None) is not None:
            try:
                self._canvas.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

    def _on_anim_configure(self, event):
        self._anim_w = event.width
        self._anim_h = event.height
        # Re-centre the login card whenever the window resizes
        self._layout_card()

        rows = max(1, event.height // self._ANIM_CELL)
        n = max(1, event.width // self._ANIM_COL_W)
        if len(self._anim_cols) == n:
            return
        self._anim_cols = [
            [random.randint(-rows, 0), random.uniform(0.5, 1.8)]
            for _ in range(n)
        ]

    def _relayout(self):
        """Re-position the card after the form is (re)built and sized."""
        if hasattr(self, "_canvas") and self._canvas.winfo_exists():
            self._canvas.after_idle(self._layout_card)

    def _layout_card(self):
        """Centre the glass card, title and form over the rain."""
        canvas = getattr(self, "_canvas", None)
        if canvas is None or not canvas.winfo_exists() or not hasattr(self, "_card_id"):
            return
        canvas.update_idletasks()
        w  = self._anim_w or canvas.winfo_width()
        h  = self._anim_h or canvas.winfo_height()
        cx, cy = w // 2, h // 2

        if getattr(self, "_login_mode", False):
            inner_w = 320
            card_w, card_h = inner_w + 96, 300
            top = cy - card_h // 2
            left, right = cx - inner_w // 2, cx + inner_w // 2
            canvas.coords(self._card_id, cx - card_w // 2, top,
                          cx + card_w // 2, top + card_h)
            canvas.coords(self._title_id,      cx,    top + 40)
            canvas.coords(self._subtitle_id,   cx,    top + 70)
            canvas.coords(self._lf_header,     cx,    top + 116)
            canvas.coords(self._lf_label,      left,  top + 150)
            canvas.coords(self._lf_entry_win,  left,  top + 180)
            canvas.coords(self._lf_show_win,   right, top + 180)
            canvas.coords(self._lf_login_win,  cx,    top + 222)
            canvas.coords(self._lf_attempts,   cx,    top + 270)
            return

        # Setup / migration: form lives in the (solid) form host
        fw = max(self._form_host.winfo_reqwidth(), 320)
        fh = self._form_host.winfo_reqheight()
        title_space = 104        # room above the form for title + subtitle
        pad_x, pad_bottom = 55, 34
        card_w = fw + pad_x * 2
        card_h = title_space + fh + pad_bottom
        top = cy - card_h // 2

        canvas.coords(self._card_id, cx - card_w // 2, top,
                      cx + card_w // 2, top + card_h)
        canvas.coords(self._title_id,    cx, top + 42)
        canvas.coords(self._subtitle_id, cx, top + 74)
        canvas.coords(self._form_win,    cx, top + title_space)

    def _animate(self):
        canvas = getattr(self, "_canvas", None)
        if canvas is None or not canvas.winfo_exists():
            return   # login frame destroyed → stop the loop cleanly

        cell  = self._ANIM_CELL
        rows  = max(1, (self._anim_h or canvas.winfo_height()) // cell)
        trail = len(self._ANIM_SHADES)

        canvas.delete("rain")
        for i, col in enumerate(self._anim_cols):
            head, speed = col
            x = i * self._ANIM_COL_W + self._ANIM_COL_W // 2
            for t in range(trail):
                yrow = int(head) - t
                if 0 <= yrow <= rows:
                    canvas.create_text(
                        x, yrow * cell + cell // 2,
                        text=random.choice(self._anim_chars),
                        fill=self._ANIM_SHADES[trail - 1 - t],
                        font=self._anim_font, tags="rain")
            col[0] = head + speed
            if int(head) - trail > rows:                 # fell off → respawn at top
                col[0] = random.randint(-rows, 0)
                col[1] = random.uniform(0.5, 1.8)

        # Keep the rain behind the login card
        canvas.tag_lower("rain")

        self._anim_id = canvas.after(75, self._animate)

    def _show_migration_notice(self):
        """Show migration notice and form."""
        # Clear existing form content
        for widget in self._form_host.winfo_children():
            widget.destroy()

        notice_frame = ttk.Labelframe(
            self._form_host,
            text="Migration Required",
            padding=20,
            bootstyle="warning"
        )
        notice_frame.pack(fill=BOTH, expand=YES, pady=(0, 20))

        ttk.Label(
            notice_frame,
            text="Legacy data detected!",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(0, 10))

        ttk.Label(
            notice_frame,
            text="This app now uses a master password system for enhanced security.\n"
                 "Your existing credentials will be migrated automatically.\n\n"
                 "Please create a new master password:",
            font=("Segoe UI", 10),
            justify=CENTER
        ).pack(pady=(0, 20))

        self._show_setup_form(is_migration=True)

    def _show_setup_form(self, is_migration=False):
        """Show initial setup form for creating master password."""
        form_frame = ttk.Frame(self._form_host)
        form_frame.pack(fill=X, pady=20)

        if not is_migration:
            ttk.Label(
                form_frame,
                text="Create Master Password",
                font=("Segoe UI", 14, "bold")
            ).pack(pady=(0, 20))

            ttk.Label(
                form_frame,
                text="This password will protect all your credentials.\n"
                     "⚠️ IMPORTANT: There is no way to recover a forgotten master password!",
                font=("Segoe UI", 9),
                bootstyle="warning",
                justify=CENTER
            ).pack(pady=(0, 15))

        # Master password
        ttk.Label(form_frame, text="Master Password:", font=("Segoe UI", 10)).pack(anchor=W, pady=(0, 5))

        password_frame = ttk.Frame(form_frame)
        password_frame.pack(fill=X, pady=(0, 10))

        self.setup_password_var = ttk.StringVar()
        self.setup_password_var.trace('w', self._update_setup_strength)

        self.setup_password_entry = ttk.Entry(
            password_frame,
            textvariable=self.setup_password_var,
            font=("Segoe UI", 11),
            show="•",
            width=30
        )
        self.setup_password_entry.pack(side=LEFT, fill=X, expand=YES, padx=(0, 5))
        self.setup_password_entry.focus()

        self.setup_show_btn = ttk.Button(
            password_frame,
            text="Show",
            command=self._toggle_setup_password,
            bootstyle="secondary-outline",
            width=8
        )
        self.setup_show_btn.pack(side=LEFT)

        # Strength meter
        strength_frame = ttk.Frame(form_frame)
        strength_frame.pack(fill=X, pady=(0, 10))

        ttk.Label(strength_frame, text="Strength:", font=("Segoe UI", 9)).pack(side=LEFT)
        self.setup_strength_label = ttk.Label(
            strength_frame,
            text="",
            font=("Segoe UI", 9, "bold")
        )
        self.setup_strength_label.pack(side=LEFT, padx=(5, 0))

        self.setup_feedback_label = ttk.Label(
            form_frame,
            text="",
            font=("Segoe UI", 8),
            bootstyle="secondary"
        )
        self.setup_feedback_label.pack(fill=X, pady=(0, 15))

        # Confirm password
        ttk.Label(form_frame, text="Confirm Master Password:", font=("Segoe UI", 10)).pack(anchor=W, pady=(0, 5))

        self.setup_confirm_var = ttk.StringVar()
        self.setup_confirm_entry = ttk.Entry(
            form_frame,
            textvariable=self.setup_confirm_var,
            font=("Segoe UI", 11),
            show="•",
            width=30
        )
        self.setup_confirm_entry.pack(fill=X, pady=(0, 20))

        # Create button
        ttk.Button(
            form_frame,
            text="Migrate & Create" if is_migration else "Create Master Password",
            command=lambda: self._create_master_password(is_migration),
            bootstyle="success",
            width=30
        ).pack()

        # Bind Enter key
        self.setup_password_entry.bind('<Return>', lambda e: self._create_master_password(is_migration))
        self.setup_confirm_entry.bind('<Return>', lambda e: self._create_master_password(is_migration))

    def _show_login_form(self):
        """Show login form — built directly on the rain canvas so the faint
        rain shows through everywhere except the actual input controls."""
        self._login_mode = True
        c = self._canvas
        c.itemconfigure("cardform", state="hidden")   # no opaque form block

        self.login_password_var = ttk.StringVar()

        self._lf_header = c.create_text(
            0, 0, text="Enter Master Password", fill="#ffffff",
            font=("Segoe UI", 15, "bold"), tags="login")
        self._lf_label = c.create_text(
            0, 0, text="Master Password:", fill="#cfd2d6",
            font=("Segoe UI", 10), anchor="w", tags="login")

        self.login_password_entry = ttk.Entry(
            c, textvariable=self.login_password_var,
            font=("Segoe UI", 11), show="•")
        self._lf_entry_win = c.create_window(
            0, 0, window=self.login_password_entry, anchor="w",
            width=238, height=30, tags="login")
        self.login_password_entry.focus()

        self.login_show_btn = ttk.Button(
            c, text="Show", command=self._toggle_login_password,
            bootstyle="secondary-outline")
        self._lf_show_win = c.create_window(
            0, 0, window=self.login_show_btn, anchor="e",
            width=74, height=30, tags="login")

        self.login_btn = ttk.Button(
            c, text="Login", command=self._verify_login, bootstyle="primary")
        self._lf_login_win = c.create_window(
            0, 0, window=self.login_btn, anchor="n",
            width=320, height=36, tags="login")

        self._lf_attempts = c.create_text(
            0, 0, text="", fill="#ff6b6b", font=("Segoe UI", 9), tags="login")

        self.login_password_entry.bind('<Return>', lambda e: self._verify_login())

    def _toggle_setup_password(self):
        """Toggle password visibility in setup mode."""
        if self.setup_password_entry.cget('show') == '•':
            self.setup_password_entry.config(show='')
            self.setup_show_btn.config(text="Hide")
        else:
            self.setup_password_entry.config(show='•')
            self.setup_show_btn.config(text="Show")

    def _toggle_login_password(self):
        """Toggle password visibility in login mode."""
        if self.login_password_entry.cget('show') == '•':
            self.login_password_entry.config(show='')
            self.login_show_btn.config(text="Hide")
        else:
            self.login_password_entry.config(show='•')
            self.login_show_btn.config(text="Show")

    def _update_setup_strength(self, *args):
        """Update password strength meter in setup mode."""
        password = self.setup_password_var.get()
        score, label, feedback = estimate_password_strength(password)

        self.setup_strength_label.config(
            text=label,
            foreground=get_strength_color(score)
        )
        self.setup_feedback_label.config(text=feedback)

    def _create_master_password(self, is_migration=False):
        """Create master password and complete setup."""
        password = self.setup_password_var.get()
        confirm = self.setup_confirm_var.get()

        # Validate passwords match
        if password != confirm:
            messagebox.showerror("Error", "Passwords do not match!")
            return

        # Validate password strength
        valid, error = validate_password_strength(password, is_master=True)
        if not valid:
            messagebox.showerror("Weak Password", error)
            return

        # Check minimum strength
        score, label, feedback = estimate_password_strength(password)
        if score < 2:  # Require at least "Fair"
            messagebox.showerror(
                "Weak Password",
                f"Password is too weak ({label}). Please create a stronger password.\n\n{feedback}"
            )
            return

        try:
            if is_migration:
                # Perform migration
                success, message = LegacyMigration.migrate_to_master_password(password)
                if not success:
                    messagebox.showerror("Migration Failed", message)
                    return

                messagebox.showinfo("Migration Successful", message)
                salt = MasterPasswordStore.get_salt()

            else:
                # Create new master password
                salt = MasterPasswordStore.create_master_password(password)

            # Success - call callback
            self._stop_animation()
            self.main_frame.destroy()
            self.on_success(password, salt)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to create master password: {e}")

    def _verify_login(self):
        """Verify login credentials."""
        # Check cooldown
        if time.time() < self.cooldown_until:
            remaining = int(self.cooldown_until - time.time())
            messagebox.showwarning(
                "Too Many Attempts",
                f"Please wait {remaining} seconds before trying again."
            )
            return

        password = self.login_password_var.get()

        if not password:
            messagebox.showerror("Error", "Please enter your master password")
            return

        try:
            # Verify password
            salt = MasterPasswordStore.verify_master_password(password)

            if salt is None:
                # Failed login
                self.failed_attempts += 1
                remaining_attempts = MAX_LOGIN_ATTEMPTS - self.failed_attempts

                if self.failed_attempts >= MAX_LOGIN_ATTEMPTS:
                    # Trigger cooldown
                    self.cooldown_until = time.time() + LOGIN_COOLDOWN_SECONDS
                    self.failed_attempts = 0
                    messagebox.showerror(
                        "Too Many Failed Attempts",
                        f"Too many failed login attempts.\n"
                        f"Please wait {LOGIN_COOLDOWN_SECONDS} seconds."
                    )
                    self.login_btn.config(state="disabled")
                    self.root.after(LOGIN_COOLDOWN_SECONDS * 1000, self._reset_cooldown)
                else:
                    self._canvas.itemconfigure(
                        self._lf_attempts,
                        text=f"Incorrect password. {remaining_attempts} attempts remaining."
                    )
                    messagebox.showerror("Login Failed", "Incorrect master password!")

                self.login_password_var.set("")
            else:
                # Successful login
                self._stop_animation()
                self.main_frame.destroy()
                self.on_success(password, salt)

        except Exception as e:
            messagebox.showerror("Error", f"Login failed: {e}")

    def _reset_cooldown(self):
        """Reset login button after cooldown."""
        self.login_btn.config(state="normal")
        self._canvas.itemconfigure(self._lf_attempts, text="")
