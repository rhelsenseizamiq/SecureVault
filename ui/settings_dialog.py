"""
Settings dialog for application preferences
"""
import json
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from config import SETTINGS_FILE, DEFAULT_AUTO_LOCK_MINUTES, DEFAULT_CLIPBOARD_CLEAR_SECONDS
from utils.validators import validate_timeout


class SettingsManager:
    """Manages application settings persistence."""

    DEFAULT_SETTINGS = {
        'auto_lock_minutes': DEFAULT_AUTO_LOCK_MINUTES,
        'clipboard_clear_seconds': DEFAULT_CLIPBOARD_CLEAR_SECONDS,
        'opacity': 0.95
    }

    @staticmethod
    def load_settings() -> dict:
        """Load settings from file or return defaults."""
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, 'r') as f:
                    saved = json.load(f)
                    return {**SettingsManager.DEFAULT_SETTINGS, **saved}
        except Exception:
            pass
        return SettingsManager.DEFAULT_SETTINGS.copy()

    @staticmethod
    def save_settings(settings: dict) -> None:
        """Save settings to file."""
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")


class SettingsDialog:
    """Settings dialog with security and appearance options."""

    def __init__(self, parent, session_manager=None):
        self.parent = parent
        self.session_manager = session_manager
        self.settings = SettingsManager.load_settings()

        self.window = ttk.Toplevel(parent)
        self.window.title("Settings")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        w, h = 500, 380
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (w // 2)
        y = (self.window.winfo_screenheight() // 2) - (h // 2)
        self.window.geometry(f"{w}x{h}+{x}+{y}")

        self._create_widgets()

    def _create_widgets(self):
        main = ttk.Frame(self.window, padding=25)
        main.pack(fill=BOTH, expand=YES)

        ttk.Label(main, text="Settings", font=("Segoe UI", 15, "bold")).pack(anchor=W, pady=(0, 18))

        # ── Security ──────────────────────────────────────────────────
        sec = ttk.Labelframe(main, text="Security", padding=15)
        sec.pack(fill=X, pady=(0, 14))
        sec.columnconfigure(1, weight=1)

        ttk.Label(sec, text="Auto-lock timeout (minutes):").grid(
            row=0, column=0, sticky=W, pady=5)
        self.auto_lock_var = ttk.StringVar(value=str(self.settings['auto_lock_minutes']))
        ttk.Spinbox(sec, from_=1, to=120, textvariable=self.auto_lock_var,
                    width=8).grid(row=0, column=1, sticky=W, padx=(12, 0), pady=5)

        ttk.Label(sec, text="Clipboard auto-clear (seconds):").grid(
            row=1, column=0, sticky=W, pady=5)
        self.clipboard_var = ttk.StringVar(value=str(self.settings['clipboard_clear_seconds']))
        ttk.Spinbox(sec, from_=0, to=300, textvariable=self.clipboard_var,
                    width=8).grid(row=1, column=1, sticky=W, padx=(12, 0), pady=5)

        ttk.Label(sec, text="(0 = disabled)", font=("Segoe UI", 8),
                 bootstyle="secondary").grid(row=2, column=1, sticky=W, padx=(12, 0))

        # ── Appearance ────────────────────────────────────────────────
        app_frame = ttk.Labelframe(main, text="Appearance", padding=15)
        app_frame.pack(fill=X, pady=(0, 18))
        app_frame.columnconfigure(1, weight=1)

        ttk.Label(app_frame, text="Window transparency:").grid(
            row=0, column=0, sticky=W, pady=6)

        slider_row = ttk.Frame(app_frame)
        slider_row.grid(row=0, column=1, sticky=EW, padx=(12, 0), pady=6)

        current_opacity = float(self.settings.get('opacity', 1.0))
        self.opacity_var = ttk.DoubleVar(value=current_opacity)

        self.opacity_pct_label = ttk.Label(
            slider_row,
            text=f"{int(current_opacity * 100)}%",
            font=("Segoe UI", 9, "bold"),
            width=5
        )
        self.opacity_pct_label.pack(side=RIGHT)

        ttk.Scale(
            slider_row,
            from_=0.4,
            to=1.0,
            variable=self.opacity_var,
            orient=HORIZONTAL,
            bootstyle="info",
            command=self._on_opacity_change
        ).pack(side=LEFT, fill=X, expand=True, padx=(0, 6))

        ttk.Label(app_frame, text="Drag to adjust — preview updates live",
                 font=("Segoe UI", 8), bootstyle="secondary").grid(
            row=1, column=0, columnspan=2, sticky=W, padx=(0, 0))

        # ── Buttons ───────────────────────────────────────────────────
        bf = ttk.Frame(main)
        bf.pack(fill=X)
        ttk.Button(bf, text="Cancel", command=self._cancel,
                  bootstyle="secondary", width=12).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(bf, text="Save", command=self._save,
                  bootstyle="success", width=12).pack(side=RIGHT)

    def _on_opacity_change(self, value):
        """Preview opacity live while dragging."""
        v = float(value)
        self.opacity_pct_label.config(text=f"{int(v * 100)}%")
        try:
            self.parent.wm_attributes('-alpha', v)
        except Exception:
            pass

    def _cancel(self):
        """Restore original opacity then close."""
        try:
            self.parent.wm_attributes('-alpha', float(self.settings.get('opacity', 1.0)))
        except Exception:
            pass
        self.window.destroy()

    def _save(self):
        valid, timeout, error = validate_timeout(self.auto_lock_var.get(), 1, 120)
        if not valid:
            messagebox.showerror("Invalid Input", f"Auto-lock timeout: {error}")
            return

        try:
            clipboard_timeout = int(self.clipboard_var.get())
            if not (0 <= clipboard_timeout <= 300):
                raise ValueError()
        except ValueError:
            messagebox.showerror("Invalid Input", "Clipboard timeout must be 0–300 seconds")
            return

        opacity = round(float(self.opacity_var.get()), 2)

        self.settings['auto_lock_minutes'] = timeout
        self.settings['clipboard_clear_seconds'] = clipboard_timeout
        self.settings['opacity'] = opacity

        SettingsManager.save_settings(self.settings)

        if self.session_manager:
            self.session_manager.set_timeout(timeout)

        # Apply opacity permanently
        try:
            self.parent.wm_attributes('-alpha', opacity)
        except Exception:
            pass

        messagebox.showinfo("Saved", "Settings saved!")
        self.window.destroy()


def show_settings_dialog(parent, session_manager=None, on_theme_change=None):
    SettingsDialog(parent, session_manager)
