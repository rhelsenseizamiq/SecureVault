"""
Session manager with auto-lock on inactivity
"""
import threading
import time
from typing import Callable, Optional
from datetime import datetime, timedelta


class SessionManager:
    """Manages user session and auto-lock on inactivity."""

    def __init__(self, timeout_minutes: int, lock_callback: Callable[[], None]):
        """
        Initialize session manager.

        Args:
            timeout_minutes: Minutes of inactivity before auto-lock
            lock_callback: Function to call when session should lock
        """
        self.timeout_minutes = timeout_minutes
        self.lock_callback = lock_callback
        self._last_activity = datetime.now()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start monitoring for inactivity."""
        if self._running:
            return

        self._running = True
        self._last_activity = datetime.now()

        # Start background monitoring thread
        self._monitor_thread = threading.Thread(target=self._monitor_activity, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1)

    def record_activity(self) -> None:
        """Record user activity to reset the inactivity timer."""
        with self._lock:
            self._last_activity = datetime.now()

    def get_time_until_lock(self) -> int:
        """
        Get seconds remaining until auto-lock.

        Returns:
            Seconds until lock (0 if already expired)
        """
        with self._lock:
            elapsed = datetime.now() - self._last_activity
            timeout = timedelta(minutes=self.timeout_minutes)
            remaining = timeout - elapsed

            return max(0, int(remaining.total_seconds()))

    def _monitor_activity(self) -> None:
        """Background thread that monitors inactivity."""
        while self._running:
            time.sleep(5)  # Check every 5 seconds

            if not self._running:
                break

            # Check if timeout exceeded
            time_until_lock = self.get_time_until_lock()

            if time_until_lock == 0:
                # Timeout exceeded - trigger lock
                self._running = False
                self.lock_callback()
                break

    def set_timeout(self, timeout_minutes: int) -> None:
        """
        Update timeout setting.

        Args:
            timeout_minutes: New timeout in minutes
        """
        with self._lock:
            self.timeout_minutes = timeout_minutes
            self._last_activity = datetime.now()  # Reset timer

    def reset_timer(self) -> None:
        """Reset the inactivity timer to current time."""
        self.record_activity()
