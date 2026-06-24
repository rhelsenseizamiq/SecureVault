"""
UI theme configuration using ttkbootstrap
"""
import ttkbootstrap as ttk
from config import DEFAULT_THEME


def create_themed_root(theme: str = DEFAULT_THEME) -> ttk.Window:
    """Create a themed root window using the darkly theme."""
    return ttk.Window(themename='darkly')


# Color constants for custom UI elements
STRENGTH_COLORS = {
    0: "#d32f2f",  # Very Weak - Red
    1: "#f57c00",  # Weak - Orange
    2: "#fbc02d",  # Fair - Yellow
    3: "#7cb342",  # Strong - Light Green
    4: "#388e3c"   # Very Strong - Dark Green
}
