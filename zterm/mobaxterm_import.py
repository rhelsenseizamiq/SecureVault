"""
MobaXterm session importer — parses MobaXterm.ini and extracts SSH sessions.

MobaXterm stores sessions in an INI file under one or more [Bookmarks*] sections.
Each session is a line:

    SessionName=#109#0%HOST%PORT%USERNAME%%...

  - #109  → SSH session (the only type we import; #151/#105 are WSL/shell)
  - split the value on '%':  [1]=host  [2]=port  [3]=username (may be "[name]")

Folders: each [Bookmarks*] section may carry `SubRep=FolderName` (possibly nested
with '\'). When present it becomes the session's folder. Passwords are NOT stored
in the INI (MobaXterm keeps them encrypted in the Windows Registry), so imported
sessions have no password — the caller links a vault entry or prompts on connect.

This module is pure: it only reads and parses. It never writes anything.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

SSH_TYPE = "#109"   # MobaXterm session-type marker for SSH


@dataclass
class MobaSession:
    name:     str
    host:     str
    port:     int
    username: str    # bracket stripped, e.g. "ansible" ("" if none)
    tag:      str    # same as username here — the credential tag, for grouping
    folder:   str = ""   # MobaXterm SubRep folder, if any


# ---------------------------------------------------------------------------
# Locating MobaXterm.ini
# ---------------------------------------------------------------------------

def find_mobaxterm_ini() -> Optional[Path]:
    """Return the first existing MobaXterm.ini from common locations, else None."""
    candidates: List[Path] = []

    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "MobaXterm" / "MobaXterm.ini")

    home = Path.home()
    candidates += [
        home / "Documents" / "MobaXterm" / "MobaXterm.ini",
        home / "AppData" / "Roaming" / "MobaXterm" / "MobaXterm.ini",
    ]

    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    """Read the INI tolerantly — MobaXterm files are often latin-1 / cp1252."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, OSError):
            continue
    # Last resort: bytes → latin-1 (never raises)
    return path.read_bytes().decode("latin-1", errors="replace")


def _strip_tag(raw_user: str) -> str:
    """'[ansible]' -> 'ansible';  'root' -> 'root';  '' -> ''."""
    u = raw_user.strip()
    if len(u) >= 2 and u[0] == "[" and u[-1] == "]":
        return u[1:-1].strip()
    return u


def parse_sessions(ini_path: Path) -> List[MobaSession]:
    """
    Parse all SSH (#109) sessions from a MobaXterm.ini file.

    Returns a list of MobaSession (order preserved). Non-SSH entries, section
    headers, and metadata keys (SubRep/ImgNum) are skipped.
    """
    text = _read_text(ini_path)
    sessions: List[MobaSession] = []
    in_bookmarks = False
    current_folder = ""

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            continue

        # Section header
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1]
            in_bookmarks = section == "Bookmarks" or section.startswith("Bookmarks_")
            current_folder = ""   # reset; SubRep (if any) follows in this section
            continue

        if not in_bookmarks:
            continue

        # key=value (split on first '=' only — values contain '=' rarely but be safe)
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()

        # Folder marker for this section
        if key == "SubRep":
            current_folder = value.strip()
            continue
        if key == "ImgNum":
            continue

        # Session line — value like "#109#0%host%port%user%%..."
        if not value.startswith(SSH_TYPE):
            continue   # skip WSL (#151), shell (#105), etc.

        parts = value.split("%")
        if len(parts) < 4:
            continue

        host = parts[1].strip()
        if not host:
            continue
        try:
            port = int(parts[2].strip())
        except (ValueError, IndexError):
            port = 22
        username = _strip_tag(parts[3])

        sessions.append(MobaSession(
            name=key,
            host=host,
            port=port,
            username=username,
            tag=username,
            folder=current_folder,
        ))

    return sessions
