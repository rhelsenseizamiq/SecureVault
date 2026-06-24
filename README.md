# 🔐 SecureVault — Password Manager + SSH Client

> A secure Windows desktop **password manager** with military-grade encryption, bundled with **ZTerm**, a full-featured embedded **SSH/SFTP client** for managing large server fleets.

**Current release: v3.0** — adds the ZTerm SSH client, multi-server tooling, and credential automation.

---

## ✨ Highlights in v3.0

- 🖥️ **ZTerm — embedded SSH client**: tabbed terminals, split panes, detach/re-attach (keeps the live shell + scrollback), SFTP browser, themes, snippets, connection history.
- 📡 **Multi-Exec**: run a command on many servers at once (wizard → pick servers → credential → command → results), with per-command separators, optional PTY for `sudo`, and an **Excel report** export.
- 🔑 **Credential tools**: test a credential across servers (see which pass/fail), bulk-**reassign** which vault credential a session uses, and auto-discover & apply server **hostnames** for IP-named sessions.
- 🛰️ **Connect via jump host (bastion)**: route a connection through another server — right-click → *Connect via jump host*, or offered automatically when a direct connect fails. Choose which credential logs into the jump host.
- 📥 **MobaXterm import** and **session export/import** (`.ztsessions`).
- 🎬 Animated login screen, dark title bar, window transparency, and many UX fixes.

---

## 🔒 Password Manager features

- **Military-grade encryption** — AES-256 (Fernet) with PBKDF2-HMAC-SHA256 key derivation (600,000 iterations).
- **Master password** — zero-knowledge; never stored, no recovery by design.
- **Password generator** + real-time **strength meter**.
- **Health check** — weak / duplicate password detection.
- **Notes, tags, favorites & recently-used** on credentials.
- **Auto-clear clipboard**, optional auto-lock, failed-login throttling.
- **Encrypted backup** export/import (`.svbackup`).

---

## 🚀 Quick start

### Run the pre-built app
1. Download `SecureVault.exe` from the [latest release](../../releases/latest).
2. Run it, create your master password, and start adding credentials.
3. For SSH: open **SSH Sessions** in the sidebar.

### Run from source
```bash
python -m pip install -r requirements.txt
python main.py
```

### Build the executable (Windows)
```bash
python -m PyInstaller SecureVault.spec --clean --noconfirm
# → dist/SecureVault.exe
```

**Requirements:** Windows 10/11, Python 3.10+. Dependencies: `cryptography`, `ttkbootstrap`, `paramiko`, `pyte`, `openpyxl` (see `requirements.txt`).

---

## 🔐 Security model

| Aspect | Detail |
|---|---|
| Encryption | AES-256 via Fernet |
| Key derivation | PBKDF2-HMAC-SHA256, 600k iterations, 32-byte salt |
| Master password | Hashed only (never stored in plaintext); no recovery |
| Data at rest | Credentials encrypted in `%APPDATA%/SecureVault/passwords.json.enc` |
| SSH | `paramiko` with jump-host tunneling; passwords pulled from the vault on demand |

All user data (master hash, encrypted credentials, SSH sessions, settings) is stored under
`%APPDATA%/SecureVault/` — **never** committed to this repository.

---

## 🗂️ Project layout

```
.
├── main.py              # entry point
├── config.py            # constants
├── crypto/              # Fernet encryption, PBKDF2, hashing
├── database/            # encrypted credential & master-password stores
├── models/              # Credential dataclass
├── ui/                  # all windows/dialogs (vault + ZTerm panel + tools)
├── utils/               # clipboard, session lock, strength, backup
├── zterm/               # SSH client engine (paramiko + pyte terminal)
└── tests/               # core/syntax tests
```

See [`CHANGELOG.md`](CHANGELOG.md) for the full version history, and
[`BUILD_INSTRUCTIONS.md`](BUILD_INSTRUCTIONS.md) for detailed build/packaging steps.

---

## 🤝 Contributing & License

Contributions welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md).
Licensed under the **MIT License** ([`LICENSE`](LICENSE)).

## ⚠️ Disclaimer

Provided "as is", without warranty. There is **no master-password recovery** by design — keep your master password safe and back up your vault.

**Author:** Zamiq Mustafayev · Built with ttkbootstrap, cryptography, paramiko, pyte & PyInstaller.
