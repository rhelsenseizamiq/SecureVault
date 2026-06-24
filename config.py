"""
Global configuration for SecureVault Password Manager

This file contains all the application-wide settings including security parameters,
file paths, and UI defaults. Modifying security settings (like PBKDF2 iterations)
may break compatibility with existing user data.
"""
import os
from pathlib import Path

# ============================================================================
# Application Information
# ============================================================================

APP_NAME = "SecureVault"
APP_VERSION = "2.1.0"
APP_AUTHOR = "Zamiq Mustafayev"

# ============================================================================
# Data Storage Paths
# ============================================================================

# Determine where to store user data based on the operating system
# Windows: %APPDATA%/SecureVault (e.g., C:/Users/YourName/AppData/Roaming/SecureVault)
# Linux/Mac: ~/.securevault (untested but should work)
if os.name == 'nt':  # Windows
    DATA_DIR = Path(os.getenv('APPDATA')) / APP_NAME
else:  # Linux/Mac
    DATA_DIR = Path.home() / f'.{APP_NAME.lower()}'

# Create the data directory if it doesn't exist yet
# This happens on first run or after the user deletes their data folder
DATA_DIR.mkdir(parents=True, exist_ok=True)

# User data files (all stored in DATA_DIR)
MASTER_PASSWORD_FILE = DATA_DIR / "master.dat"           # Hashed master password
CREDENTIALS_FILE = DATA_DIR / "passwords.json.enc"       # Encrypted credentials
SETTINGS_FILE = DATA_DIR / "settings.json"               # User preferences

# Legacy file paths from v1.0 (used only for migration detection)
LEGACY_KEY_FILE = "key.key"
LEGACY_STORE_FILE = "passwords.json.enc"

# ============================================================================
# Security & Cryptography Settings
# ============================================================================

# PBKDF2 configuration for key derivation and password hashing
# WARNING: Changing these values will break compatibility with existing user data!
PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation (600k iterations minimum)
PBKDF2_ALGORITHM = 'sha256'  # SHA-256 is secure and widely supported
SALT_LENGTH = 32             # 32 bytes = 256 bits (strong random salt)
KEY_LENGTH = 32              # 32 bytes = 256 bits (required for Fernet encryption)

# Session security defaults
DEFAULT_AUTO_LOCK_MINUTES = 10        # Lock app after 10 minutes of inactivity
DEFAULT_CLIPBOARD_CLEAR_SECONDS = 30  # Clear clipboard 30 seconds after copying
MAX_LOGIN_ATTEMPTS = 3                # Allow 3 failed login attempts
LOGIN_COOLDOWN_SECONDS = 30           # Then enforce 30-second cooldown

# Password strength requirements
MIN_PASSWORD_LENGTH = 8         # Minimum 8 characters for regular passwords
MIN_MASTER_PASSWORD_LENGTH = 12 # Minimum 12 characters for master password (stricter)

# ============================================================================
# ZTerm SSH client settings
# ============================================================================
ZTERM_KEEPALIVE_SEC   = 30            # TCP keepalive — stops idle disconnects
ZTERM_RECONNECT_TRIES = 3             # Auto-reconnect attempts on an unexpected drop
ZTERM_RECONNECT_DELAYS = (3, 6, 10)   # Backoff (seconds) between reconnect attempts

# ============================================================================
# User Interface Settings
# ============================================================================

# Default theme (see ttkbootstrap documentation for available themes)
# Available themes: flatly (modern), darkly (dark), cyborg (hacker - black/green)
DEFAULT_THEME = 'darkly'

# Window transparency (1.0 = fully opaque, 0.0 = fully transparent)
# Currently unused but available for future enhancements
WINDOW_ALPHA = 0.95
