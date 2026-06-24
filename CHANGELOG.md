# SecureVault Changelog

## Version 3.0.0 — ZTerm & Fleet Tools (2026-06)

A major release that turns SecureVault into a password manager **and** an integrated SSH workstation.

### 🖥️ ZTerm — embedded SSH client (new)
- Tabbed terminals with a fast VT100/xterm-256color emulator (`pyte` + `paramiko`).
- **Split panes**, **detach/re-attach** tabs to separate windows *without dropping the live shell* — full scrollback and running programs are preserved.
- **SFTP browser** (upload/download/rename/delete), per-session **colors**, **themes**, **snippets**, and **connection history**.
- Mouse + right-click **copy/paste** (standard-terminal behavior), **font zoom** (Ctrl +/–/0), in-terminal **search** (Ctrl+F).
- **Auto-reconnect + TCP keepalive**; idle sessions auto-close after 10 minutes.
- Left-edge clipping and minimize/restore rendering bugs fixed.

### 📡 Multi-server tooling (new)
- **Multi-Exec wizard**: select servers → pick a vault credential → enter command(s) → verify → run in parallel; per-command separators, optional **PTY for sudo**, and a per-server results popup.
- **Excel report** export of scan/exec results (IP, hostname, result, credential) via `openpyxl`.

### 🔑 Credential tools (new)
- **Test a credential** across many servers (and which ones fail), testing several credentials in one pass.
- **Bulk reassign** which vault credential a session connects with (e.g. `ansible_new` → `ansible_new_new`).
- **Hostname discovery** — fetch each server's real hostname during a scan and rename IP-named sessions (connect IP preserved, duplicates de-duped).

### 🛰️ Jump host / bastion routing (new)
- **Connect via jump host**: right-click a session, or accept the offer in the "Connection Failed" dialog.
- Choose which **credential** authenticates to the jump host; clear jump-vs-target error reporting.

### 📥 Import / export
- **MobaXterm** `.ini` session import; ZTerm **session export/import** (`.ztsessions`).

### 🔒 Vault enhancements
- Credential **notes, tags, favorites, and recently-used**, with tag filtering and search.

### 🐛 Fixes
- App now terminates immediately on window close (no lingering process from background scan threads).
- Jump-host **password is now resolved from the vault** (previously unset).
- Numerous terminal rendering, copy/paste, and connection-stability fixes.

### ⚠️ Notes
- Backward compatible: existing `passwords.json.enc` and SSH session files load unchanged.
- New dependencies: `paramiko`, `pyte`, `openpyxl`.

---

## Version 2.1.0 - Enhanced Edition (2024)

### 🎉 New Features

#### 1. **Export/Import Backup System**
- **Export Backup**: Securely export all credentials to an encrypted backup file (.svbackup)
- **Import Backup**: Restore credentials from encrypted backup files
- **Smart Merge**: Automatically handles duplicate credentials during import with user choice
- **Encryption**: Backups are encrypted using your master password for maximum security
- Access via new buttons in main dashboard: 📤 Export Backup and 📥 Import Backup

#### 2. **Password Health Checker** 💊
- Analyze all stored passwords for security issues
- **Weak Password Detection**: Identifies passwords that don't meet security standards
- **Duplicate Detection**: Finds passwords used across multiple services
- **Health Score**: Visual overall security score (0-100%)
- **Detailed Reports**: Shows which services have weak or duplicate passwords
- Access via "Password Health" button in main dashboard

#### 3. **Enhanced User Experience**
- **Silent Copy Operations**: Removed popup notifications when copying passwords/usernames
- **Quick Password Copy**: Click on the password column (••••••••) to instantly copy password
- **Improved Help**: Added helpful tips in credential list window
- **Better Visual Feedback**: Enhanced tooltips and status messages

#### 4. **Simplified Theme Selection**
- Reduced from 16 themes to 3 carefully chosen themes:
  - **Light Theme** (flatly): Clean, modern light interface
  - **Dark Theme** (cyborg): Sleek dark interface for low-light environments
  - **Terminal Style** (vapor): Retro-futuristic terminal aesthetic
- Easier theme selection with descriptive names

### 🔧 Improvements

- **Better Credential List Navigation**:
  - Single-click on password column to copy password
  - Double-click anywhere to view full credential details
  - Right-click for full context menu

- **Enhanced Security**:
  - Backup files use same military-grade encryption as main storage
  - No data is ever stored unencrypted

- **Code Quality**:
  - Improved error handling
  - Better input validation
  - Enhanced code organization

### 🐛 Bug Fixes

- Fixed potential issues with theme switching
- Improved clipboard manager reliability
- Enhanced session management

### 📝 Usage Tips

**Export Backup**:
1. Click "📤 Export Backup" from main dashboard
2. Choose location to save .svbackup file
3. File is encrypted with your master password

**Import Backup**:
1. Click "📥 Import Backup" from main dashboard
2. Select .svbackup file
3. Choose how to handle duplicates (overwrite, skip, or cancel)

**Check Password Health**:
1. Click "💊 Password Health" from main dashboard
2. Review weak and duplicate passwords
3. Update weak passwords as recommended

**Quick Copy**:
- In credential list, simply click the "••••••••" in the password column
- No more annoying popup notifications!

### ⚠️ Breaking Changes

- None! All changes are backward compatible with v2.0.0
- Your existing credentials and master password remain unchanged

### 🔒 Security Notes

- Backup files (.svbackup) are as secure as your main password database
- Never share your backup files without changing the master password first
- Keep backups in a secure location (encrypted USB drive, secure cloud storage)

---

## Version 2.0.0 - Complete Rewrite

See README.md for full v2.0.0 changelog and migration notes from v1.0.

---

**For questions or issues, please visit**: https://github.com/zamiqm/SecureVault
