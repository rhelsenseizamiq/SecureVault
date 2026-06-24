"""Connection history — logs every SSH session with start/end times."""
import json
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class HistoryEntry:
    session_name: str
    host: str
    port: int
    username: str
    started: str          # ISO datetime string
    ended: str = ""       # filled on disconnect
    duration_s: int = 0   # seconds

    def fmt_duration(self) -> str:
        s = self.duration_s
        if s < 60:   return f"{s}s"
        if s < 3600: return f"{s//60}m {s%60}s"
        return f"{s//3600}h {(s%3600)//60}m"


MAX_HISTORY = 500


class ConnectionHistory:
    def __init__(self, data_dir: Path) -> None:
        self._file = data_dir / "zterm_history.json"
        self._active: dict = {}   # entry_id → (HistoryEntry, start_epoch)

    # ------------------------------------------------------------------ public

    def log_start(self, session_name: str, host: str,
                  port: int, username: str) -> str:
        entry_id = f"{session_name}_{time.monotonic_ns()}"
        now = datetime.now()
        entry = HistoryEntry(
            session_name=session_name,
            host=host, port=port, username=username,
            started=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._active[entry_id] = (entry, time.monotonic())
        return entry_id

    def log_end(self, entry_id: str) -> None:
        if entry_id not in self._active:
            return
        entry, t0 = self._active.pop(entry_id)
        entry.ended     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry.duration_s = int(time.monotonic() - t0)
        self._append(entry)

    def load(self) -> List[HistoryEntry]:
        if not self._file.exists():
            return []
        try:
            with open(self._file, encoding="utf-8") as f:
                return [HistoryEntry(**d) for d in json.load(f)]
        except Exception:
            return []

    # ------------------------------------------------------------------ internal

    def _append(self, entry: HistoryEntry) -> None:
        entries = self.load()
        entries.insert(0, entry)
        entries = entries[:MAX_HISTORY]
        self._file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump([asdict(e) for e in entries], f, indent=2)
