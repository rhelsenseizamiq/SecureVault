"""
Clipboard manager with auto-clear functionality
"""
import threading
import tkinter as tk
from typing import Optional


class ClipboardManager:
    """Manages clipboard with auto-clear after timeout."""

    def __init__(self, root: tk.Tk):
        """
        Initialize clipboard manager.

        Args:
            root: Root tkinter window
        """
        self.root = root
        self._clear_timer: Optional[threading.Timer] = None
        self._last_copied_text: Optional[str] = None

    def copy_with_autoclear(self, text: str, timeout_seconds: int) -> None:
        """
        Copy text to clipboard and auto-clear after timeout.

        Args:
            text: Text to copy to clipboard
            timeout_seconds: Seconds until auto-clear (0 = no auto-clear)
        """
        # Cancel any existing timer
        if self._clear_timer and self._clear_timer.is_alive():
            self._clear_timer.cancel()

        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()  # Ensure clipboard is updated

        self._last_copied_text = text

        # Set up auto-clear if timeout > 0
        if timeout_seconds > 0:
            self._clear_timer = threading.Timer(
                timeout_seconds,
                self._clear_clipboard
            )
            self._clear_timer.daemon = True
            self._clear_timer.start()

    def _clear_clipboard(self) -> None:
        """
        Clear clipboard if it still contains our text.
        Uses root.after() to ensure thread safety with tkinter.
        """
        def safe_clear():
            try:
                # Get current clipboard content
                current_clipboard = self.root.clipboard_get()

                # Only clear if clipboard still contains what we copied
                if current_clipboard == self._last_copied_text:
                    self.root.clipboard_clear()
                    self.root.update()
                    self._last_copied_text = None

            except tk.TclError:
                # Clipboard is empty or inaccessible
                pass

        # Schedule the clear operation on the main thread
        self.root.after(0, safe_clear)

    def cancel_autoclear(self) -> None:
        """Cancel any pending auto-clear timer."""
        if self._clear_timer and self._clear_timer.is_alive():
            self._clear_timer.cancel()
            self._clear_timer = None

    def cleanup(self) -> None:
        """Clean up resources. Call this before destroying the window."""
        self.cancel_autoclear()
