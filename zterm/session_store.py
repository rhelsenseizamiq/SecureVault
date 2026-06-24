"""
ZTerm SSH session persistence — plain JSON, no passwords stored.
Passwords come from SecureVault vault or are entered manually.
"""
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List


@dataclass
class PortForward:
    local_port:  int
    remote_host: str
    remote_port: int
    description: str = ""

    def to_dict(self):  return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            local_port  = int(d.get("local_port",  0)),
            remote_host = d.get("remote_host", ""),
            remote_port = int(d.get("remote_port", 0)),
            description = d.get("description", ""),
        )


@dataclass
class SSHSession:
    name:           str
    host:           str
    port:           int
    username:       str
    auth_type:      str        # "password" | "key"
    vault_ref:      str = ""   # SecureVault service_name for password lookup
    key_path:       str = ""   # path to private key file
    color:          str = ""   # sidebar label colour hex, e.g. "#4e9a06"
    group:          str = ""   # folder/group name shown in sidebar tree

    # Jump host (bastion)
    jump_host:       str = ""
    jump_port:       int = 22
    jump_user:       str = ""
    jump_vault_ref:  str = ""  # vault ref for jumphost password
    jump_key_path:   str = ""

    # Port forwarding rules
    port_forwards:   List[PortForward] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["port_forwards"] = [pf.to_dict() for pf in self.port_forwards]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SSHSession":
        pfs = [PortForward.from_dict(p) for p in d.get("port_forwards", [])]
        return cls(
            name          = d.get("name",          ""),
            host          = d.get("host",          ""),
            port          = int(d.get("port",       22)),
            username      = d.get("username",      ""),
            auth_type     = d.get("auth_type",     "password"),
            vault_ref     = d.get("vault_ref",     ""),
            key_path      = d.get("key_path",      ""),
            color         = d.get("color",         ""),
            group         = d.get("group",         ""),
            jump_host     = d.get("jump_host",     ""),
            jump_port     = int(d.get("jump_port",  22)),
            jump_user     = d.get("jump_user",     ""),
            jump_vault_ref= d.get("jump_vault_ref",""),
            jump_key_path = d.get("jump_key_path", ""),
            port_forwards = pfs,
        )


class ZTermSessionStore:
    def __init__(self, data_dir: Path) -> None:
        self._file = data_dir / "zterm_sessions.json"

    def load(self) -> Dict[str, SSHSession]:
        if not self._file.exists():
            return {}
        try:
            with open(self._file, encoding="utf-8") as f:
                data = json.load(f)
            return {k: SSHSession.from_dict(v) for k, v in data.items()}
        except Exception:
            return {}

    def save(self, sessions: Dict[str, SSHSession]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump({k: v.to_dict() for k, v in sessions.items()}, f, indent=2)

    def add(self, s: SSHSession, sessions: Dict[str, SSHSession]) -> Dict[str, SSHSession]:
        sessions = dict(sessions)
        sessions[s.name] = s
        self.save(sessions)
        return sessions

    def delete(self, name: str, sessions: Dict[str, SSHSession]) -> Dict[str, SSHSession]:
        sessions = dict(sessions)
        sessions.pop(name, None)
        self.save(sessions)
        return sessions

    def groups(self, sessions: Dict[str, SSHSession]) -> List[str]:
        """Return sorted unique group names (non-empty)."""
        return sorted({s.group for s in sessions.values() if s.group})
