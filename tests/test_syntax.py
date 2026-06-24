"""
Syntax check for all Python modules (compiles without running)
"""
import py_compile
import sys
from pathlib import Path

print("=" * 80)
print("ZM Password Manager v2.0 - Syntax Check")
print("=" * 80)
print()

errors = []
success = []

# Get all Python files
python_files = [
    "config.py",
    "main.py",
    "crypto/encryption.py",
    "crypto/key_derivation.py",
    "crypto/password_hashing.py",
    "database/credential_store.py",
    "database/master_password_store.py",
    "database/migration.py",
    "models/credential.py",
    "ui/theme.py",
    "ui/login_window.py",
    "ui/main_window.py",
    "ui/credential_dialog.py",
    "ui/credential_list_window.py",
    "ui/password_generator.py",
    "ui/settings_dialog.py",
    "utils/password_strength.py",
    "utils/clipboard_manager.py",
    "utils/session_manager.py",
    "utils/validators.py",
]

print("Checking syntax of all Python files...")
print()

for filepath in python_files:
    try:
        py_compile.compile(filepath, doraise=True)
        success.append(filepath)
        print(f"  ✓ {filepath}")
    except py_compile.PyCompileError as e:
        errors.append((filepath, str(e)))
        print(f"  ❌ {filepath}")
        print(f"     Error: {e}")

print()
print("=" * 80)

if errors:
    print(f"❌ SYNTAX CHECK FAILED: {len(errors)} error(s)")
    print()
    for filepath, error in errors:
        print(f"  {filepath}:")
        print(f"    {error}")
    sys.exit(1)
else:
    print(f"✅ SYNTAX CHECK PASSED: All {len(success)} files compiled successfully!")
    print()
    print("Files checked:")
    for filepath in success:
        print(f"  • {filepath}")

print("=" * 80)
