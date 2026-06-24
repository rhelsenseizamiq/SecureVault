"""Macro / snippet library — quick-send commands to the active terminal."""
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List


@dataclass
class Snippet:
    name: str
    command: str


class SnippetStore:
    def __init__(self, data_dir: Path) -> None:
        self._file = data_dir / "zterm_snippets.json"

    def load(self) -> List[Snippet]:
        if not self._file.exists():
            return self._defaults()
        try:
            with open(self._file, encoding="utf-8") as f:
                return [Snippet(**d) for d in json.load(f)]
        except Exception:
            return self._defaults()

    def save(self, snippets: List[Snippet]) -> None:
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump([asdict(s) for s in snippets], f, indent=2)

    def _defaults(self) -> List[Snippet]:
        return [
            Snippet("Disk usage",      "df -h"),
            Snippet("Memory",          "free -h"),
            Snippet("Top processes",   "top"),
            Snippet("Who is logged in","w"),
            Snippet("List services",   "systemctl list-units --type=service --state=running"),
            Snippet("Tail syslog",     "tail -f /var/log/syslog"),
            Snippet("IP addresses",    "ip addr show"),
            Snippet("Open ports",      "ss -tlnp"),
        ]
