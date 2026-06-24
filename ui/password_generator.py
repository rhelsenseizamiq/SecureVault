"""
Password generator dialog
"""
import secrets
import string
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from utils.password_strength import estimate_password_strength, get_strength_color


class PasswordGeneratorDialog:
    """Dialog for generating random passwords."""

    def __init__(self, parent, callback=None):
        """
        Initialize password generator dialog.

        Args:
            parent: Parent window
            callback: Optional callback function to receive generated password
        """
        self.parent = parent
        self.callback = callback
        self.generated_password = None

        # Create dialog
        self.window = ttk.Toplevel(parent)
        self.window.title("Password Generator")
        self.window.geometry("900x850")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        # Center window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.window.winfo_screenheight() // 2) - (450 // 2)
        self.window.geometry(f"900x850+{x}+{y}")

        self._create_widgets()
        self._generate_password()  # Generate initial password

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main frame
        main_frame = ttk.Frame(self.window, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)

        # Title
        ttk.Label(
            main_frame,
            text="Password Generator",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(0, 20))

        # Generated password display
        password_frame = ttk.Labelframe(main_frame, text="Generated Password", padding=10)
        password_frame.pack(fill=X, pady=(0, 20))

        self.password_var = ttk.StringVar()
        password_entry = ttk.Entry(
            password_frame,
            textvariable=self.password_var,
            font=("Courier New", 12),
            state="readonly"
        )
        password_entry.pack(fill=X, pady=(0, 10))

        # Strength meter
        strength_frame = ttk.Frame(password_frame)
        strength_frame.pack(fill=X)

        ttk.Label(strength_frame, text="Strength:").pack(side=LEFT)
        self.strength_label = ttk.Label(strength_frame, text="", font=("Segoe UI", 10, "bold"))
        self.strength_label.pack(side=LEFT, padx=(5, 0))

        # Options frame
        options_frame = ttk.Labelframe(main_frame, text="Options", padding=10)
        options_frame.pack(fill=BOTH, expand=YES, pady=(0, 20))

        # Length slider
        length_frame = ttk.Frame(options_frame)
        length_frame.pack(fill=X, pady=5)

        ttk.Label(length_frame, text="Length:").pack(side=LEFT)
        self.length_var = ttk.IntVar(value=16)
        self.length_label = ttk.Label(length_frame, text="16", width=3)
        self.length_label.pack(side=RIGHT)

        length_slider = ttk.Scale(
            length_frame,
            from_=8,
            to=64,
            variable=self.length_var,
            command=self._on_length_change,
            bootstyle="info"
        )
        length_slider.pack(side=LEFT, fill=X, expand=YES, padx=10)

        # Character type checkboxes
        self.uppercase_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Uppercase (A-Z)",
            variable=self.uppercase_var,
            command=self._generate_password,
            bootstyle="round-toggle"
        ).pack(anchor=W, pady=3)

        self.lowercase_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Lowercase (a-z)",
            variable=self.lowercase_var,
            command=self._generate_password,
            bootstyle="round-toggle"
        ).pack(anchor=W, pady=3)

        self.digits_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Digits (0-9)",
            variable=self.digits_var,
            command=self._generate_password,
            bootstyle="round-toggle"
        ).pack(anchor=W, pady=3)

        self.special_var = ttk.BooleanVar(value=True)
        ttk.Checkbutton(
            options_frame,
            text="Special Characters (!@#$%^&*)",
            variable=self.special_var,
            command=self._generate_password,
            bootstyle="round-toggle"
        ).pack(anchor=W, pady=3)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=X)

        ttk.Button(
            button_frame,
            text="Regenerate",
            command=self._generate_password,
            bootstyle="info",
            width=15
        ).pack(side=LEFT, padx=(0, 5))

        ttk.Button(
            button_frame,
            text="Copy",
            command=self._copy_password,
            bootstyle="secondary",
            width=15
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Use This Password",
            command=self._use_password,
            bootstyle="success",
            width=20
        ).pack(side=RIGHT)

    def _on_length_change(self, value):
        """Handle length slider change."""
        length = int(float(value))
        self.length_label.config(text=str(length))
        self._generate_password()

    def _generate_password(self):
        """Generate a new random password based on selected options."""
        # Build character set
        charset = ""
        if self.uppercase_var.get():
            charset += string.ascii_uppercase
        if self.lowercase_var.get():
            charset += string.ascii_lowercase
        if self.digits_var.get():
            charset += string.digits
        if self.special_var.get():
            charset += "!@#$%^&*()-_=+[]{}|;:,.<>?"

        if not charset:
            messagebox.showwarning("No Character Types", "Please select at least one character type.")
            self.uppercase_var.set(True)
            charset = string.ascii_uppercase

        # Generate password using secrets module (cryptographically secure)
        length = self.length_var.get()
        password = ''.join(secrets.choice(charset) for _ in range(length))

        self.generated_password = password
        self.password_var.set(password)

        # Update strength meter
        score, label, feedback = estimate_password_strength(password)
        self.strength_label.config(text=label, foreground=get_strength_color(score))

    def _copy_password(self):
        """Copy generated password to clipboard."""
        if self.generated_password:
            self.window.clipboard_clear()
            self.window.clipboard_append(self.generated_password)
            self.window.update()
            messagebox.showinfo("Copied", "Password copied to clipboard!")

    def _use_password(self):
        """Use the generated password (call callback and close)."""
        if self.callback and self.generated_password:
            self.callback(self.generated_password)
        self.window.destroy()


def show_password_generator(parent, callback=None):
    """
    Show password generator dialog.

    Args:
        parent: Parent window
        callback: Optional callback to receive generated password
    """
    PasswordGeneratorDialog(parent, callback)
