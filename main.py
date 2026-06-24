"""
ZM Password Manager - Main Entry Point
A modern, secure password manager with master password protection.

Author: Zamiq Mustafayev
Version: 2.0.0
"""
import os
import sys
from ui.theme import create_themed_root
from ui.login_window import LoginWindow
from ui.main_window import MainWindow


def main():
    """Main application entry point."""
    code = 0
    try:
        # Create themed root window (dark theme)
        root = create_themed_root()
        root.geometry("500x600")

        # Define login success callback
        def on_login_success(master_password: str, salt: bytes):
            MainWindow(root, master_password, salt)

        # Show login window
        LoginWindow(root, on_login_success)

        # Start application
        root.mainloop()

    except KeyboardInterrupt:
        print("\nApplication closed by user.")
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        code = 1

    # Force-terminate the instant the window closes. The Multi-Exec / credential
    # scans use ThreadPoolExecutor whose workers are NON-daemon, so
    # concurrent.futures' atexit hook would otherwise block process exit by
    # joining any worker still stuck on a slow/unreachable host — which made the
    # app "not close". All data is saved synchronously during use, so this is safe.
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


if __name__ == "__main__":
    main()
