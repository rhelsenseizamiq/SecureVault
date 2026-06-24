"""
VT100/xterm-256color terminal widget for tkinter.

Scrollback design
─────────────────
  • _TrackingScreen subclasses pyte.Screen and overrides index() to capture
    each row as it scrolls off the top — only when cursor is at the bottom
    margin (actual scroll, not cursor move).

  • The tk.Text widget accumulates ALL output: scrollback lines are inserted
    once and never deleted; only the "active screen" (bottom n_rows lines)
    is re-rendered on each tick.

  • Auto-scroll only happens when the user is already at the bottom
    (yview()[1] >= 0.99). Scroll up → new output no longer forces the view
    back down.

Other notes
───────────
  • state='normal' always — fixes Windows background-colour tag rendering.
  • Copy/paste like a standard terminal: select text → auto-copied; right-click
    copies the selection or, if none, pastes the clipboard into the shell.
    Ctrl+Shift+C / Ctrl+Shift+V and middle-click paste also work. Shift+right-
    click opens the full menu. Clipboard reads fall back across formats so a
    password copied from the vault always pastes.
  • 60 fps render loop via after() with dirty flag; only renders when data
    arrives from SSH.
  • 256-colour + bold / italic / underline / reverse supported.
  • Cursor shown as reverse-video block.
"""
import tkinter as tk
import tkinter.font as tkfont
import queue
import time
from typing import Callable, Optional

try:
    import pyte
    PYTE_OK = True
except ImportError:
    PYTE_OK = False


# ── colour tables ────────────────────────────────────────────────────────────

_ANSI16: dict = {
    "black":          "#1e1e1e",
    "red":            "#cc0000",
    "green":          "#4e9a06",
    "brown":          "#c4a000",
    "yellow":         "#c4a000",
    "blue":           "#3465a4",
    "magenta":        "#75507b",
    "cyan":           "#06989a",
    "white":          "#d3d7cf",
    "bright_black":   "#555753",
    "bright_red":     "#ef2929",
    "bright_green":   "#8ae234",
    "bright_yellow":  "#fce94f",
    "bright_brown":   "#fce94f",
    "bright_blue":    "#729fcf",
    "bright_magenta": "#ad7fa8",
    "bright_cyan":    "#34e2e2",
    "bright_white":   "#eeeeec",
}

_FG_DEFAULT = "#d3d7cf"
_BG_DEFAULT = "#1e1e1e"


def _build_256() -> list:
    _16 = [
        "#000000", "#cc0000", "#4e9a06", "#c4a000",
        "#3465a4", "#75507b", "#06989a", "#d3d7cf",
        "#555753", "#ef2929", "#8ae234", "#fce94f",
        "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec",
    ]
    pal = list(_16)
    for i in range(216):
        b = i % 6;  g = (i // 6) % 6;  r = i // 36
        def _c(v): return 0 if v == 0 else 55 + v * 40
        pal.append(f"#{_c(r):02x}{_c(g):02x}{_c(b):02x}")
    for i in range(24):
        lv = 8 + i * 10
        pal.append(f"#{lv:02x}{lv:02x}{lv:02x}")
    return pal


_PALETTE_256 = _build_256()

# ── built-in colour themes ────────────────────────────────────────────────────

THEMES: dict = {
    "Dark (default)":  {"bg": "#1e1e1e", "fg": "#d3d7cf"},
    "Monokai":         {"bg": "#272822", "fg": "#f8f8f2"},
    "Solarized Dark":  {"bg": "#002b36", "fg": "#839496"},
    "Nord":            {"bg": "#2e3440", "fg": "#d8dee9"},
    "Dracula":         {"bg": "#282a36", "fg": "#f8f8f2"},
    "One Dark":        {"bg": "#282c34", "fg": "#abb2bf"},
    "Green on Black":  {"bg": "#000000", "fg": "#00ff00"},
    "Amber on Black":  {"bg": "#0a0800", "fg": "#ffb000"},
    "White on Black":  {"bg": "#000000", "fg": "#ffffff"},
    "Black on White":  {"bg": "#ffffff", "fg": "#1e1e1e"},
}


def _resolve_color(color: str, is_bg: bool,
                   theme_fg: str = _FG_DEFAULT,
                   theme_bg: str = _BG_DEFAULT) -> str:
    if color == "default":
        return theme_bg if is_bg else theme_fg
    if color in _ANSI16:
        return _ANSI16[color]
    try:
        idx = int(color)
        if 0 <= idx < 256:
            return _PALETTE_256[idx]
    except (ValueError, TypeError):
        pass
    return theme_bg if is_bg else theme_fg


# ── key map ───────────────────────────────────────────────────────────────────

_KEY_MAP: dict = {
    "Return":    "\r",   "KP_Enter": "\r",
    "BackSpace": "\x7f", "Tab":      "\t",
    "Escape":    "\x1b", "Delete":   "\x1b[3~",
    "Home":      "\x1b[H", "End":    "\x1b[F",
    "Prior":     "\x1b[5~", "Next":  "\x1b[6~",
    "Up":        "\x1b[A",  "Down":  "\x1b[B",
    "Right":     "\x1b[C",  "Left":  "\x1b[D",
    "Insert":    "\x1b[2~",
    "F1":  "\x1bOP",  "F2":  "\x1bOQ",  "F3":  "\x1bOR",  "F4":  "\x1bOS",
    "F5":  "\x1b[15~","F6":  "\x1b[17~","F7":  "\x1b[18~","F8":  "\x1b[19~",
    "F9":  "\x1b[20~","F10": "\x1b[21~","F11": "\x1b[23~","F12": "\x1b[24~",
}

_CTRL_MAP: dict = {c: chr(ord(c) - 96) for c in "abcdefghijklmnopqrstuvwxyz"}
_CTRL_MAP.update({"[": "\x1b", "\\": "\x1c", "]": "\x1d", "@": "\x00", "_": "\x1f"})


# ── pyte Screen subclass — captures scrolled-off rows ────────────────────────

if PYTE_OK:
    class _TrackingScreen(pyte.Screen):
        """
        pyte.Screen that records each row as it scrolls off the top into a
        `pending_scroll` list. The widget drains (and clears) that list on
        every render, so a burst of output never re-reads stale data and the
        capture cost is O(scrolled lines) total, not O(scrollback²).

        index() is pyte's line-feed hook; we only capture when the cursor sits
        on the bottom margin (a real scroll, not a plain cursor move).
        """

        def __init__(self, cols: int, rows: int) -> None:
            super().__init__(cols, rows)
            self.pending_scroll: list = []   # rows scrolled off since last drain

        def index(self) -> None:
            margins = self.margins
            bottom  = margins.bottom if margins else self.lines - 1
            top     = margins.top    if margins else 0
            if self.cursor.y == bottom:
                # Snapshot the departing row before pyte discards it.
                # buffer rows are sparse defaultdicts — materialise ALL columns
                # into a plain list so render never hits a missing-key.
                src = self.buffer[top]
                self.pending_scroll.append(
                    [src[x] for x in range(self.columns)])
            super().index()

        def resize(self, rows: int, columns: int) -> None:
            # Column changes invalidate buffered scroll lines — drop them.
            self.pending_scroll.clear()
            super().resize(rows, columns)
else:
    _TrackingScreen = None  # type: ignore


# ── terminal widget ───────────────────────────────────────────────────────────

class TerminalWidget(tk.Frame):
    """
    VT100-compatible SSH terminal widget with scrollback.
    Call connect_queue(queue, send_cb, close_cb) to wire an SSH connection.
    """

    _FONT_CANDIDATES = ["Consolas", "Lucida Console", "Courier New", "Courier"]
    FONT_SIZE = 11

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, bg=_BG_DEFAULT, **kwargs)

        self._pyte_ok    = PYTE_OK
        self._ssh_queue: Optional[queue.Queue]              = None
        self._send_cb:   Optional[Callable[[bytes], None]]  = None
        self._close_cb:  Optional[Callable[[], None]]       = None
        self._resize_cb: Optional[Callable[[int, int], None]] = None

        self._cols = 80
        self._rows = 24

        # Theme
        self._theme_fg = _FG_DEFAULT
        self._theme_bg = _BG_DEFAULT

        # pyte
        if PYTE_OK:
            self._screen = _TrackingScreen(self._cols, self._rows)
            self._stream = pyte.Stream(self._screen)
            self._blank_char = pyte.screens.Char(data=" ")
        else:
            self._screen = self._stream = None
            self._blank_char = None

        self._tag_cache: set = set()
        self._dirty = False

        # Scrollback / render state
        self._committed   = 0       # scrollback lines currently held in the widget
        self._prev_cy     = 0       # previous cursor row (to clear old cursor block)
        self._first_render = True   # force full active-region build on first paint
        self._is_at_bottom = True   # is the user scrolled to the bottom?

        # Activity tracking — last time data was sent or received. Used by the
        # owning pane to auto-close idle SSH sessions.
        self._last_activity = 0.0

        # Broadcast hook — when set and it returns True, input is fanned out to
        # all terminals by the panel instead of (only) this one's SSH.
        self._broadcast_hook: Optional[Callable[[str], bool]] = None

        self._build_widget()
        self._after_id = self.after(16, self._tick)

    # Max scrollback lines kept in the Text widget (older lines trimmed).
    MAX_SCROLLBACK = 5000

    # ── build ─────────────────────────────────────────────────────────────────

    def _build_widget(self) -> None:
        available = tkfont.families()
        family = next((f for f in self._FONT_CANDIDATES if f in available), "Courier")
        self._font      = tkfont.Font(family=family, size=self.FONT_SIZE)
        self._bold_font = tkfont.Font(family=family, size=self.FONT_SIZE, weight="bold")
        self._ital_font = tkfont.Font(family=family, size=self.FONT_SIZE, slant="italic")
        self._bi_font   = tkfont.Font(family=family, size=self.FONT_SIZE,
                                      weight="bold", slant="italic")
        self._char_w = self._font.measure("W")
        self._char_h = self._font.metrics("linespace")

        self._text = tk.Text(
            self, font=self._font,
            bg=self._theme_bg, fg=self._theme_fg,
            insertbackground="#ffffff", insertwidth=2,
            state="normal",          # NOT disabled — fixes Windows colour rendering
            wrap="none",
            cursor="xterm",
            relief="flat", bd=0, highlightthickness=0,
            takefocus=True,
            selectbackground="#3465a4",
            selectforeground=_FG_DEFAULT,
            exportselection=True,
        )

        # Find bar (Ctrl+F) — created hidden, packed at the top when shown.
        self._build_search_bar()

        self._vsb = tk.Scrollbar(self, orient="vertical")
        self._vsb.config(command=self._text.yview)
        self._text.configure(yscrollcommand=self._on_yscroll)

        self._vsb.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)

        # Cursor tag (reverse-video block)
        self._text.tag_configure("CURSOR",
                                 foreground=self._theme_bg,
                                 background=self._theme_fg)

        # Search highlight tags (raised above cell/sel tags so matches show).
        self._text.tag_configure("search",         background="#665c00", foreground="#ffffff")
        self._text.tag_configure("search_current", background="#d79921", foreground="#000000")
        self._text.bind("<Control-f>", self._show_search)
        self._text.bind("<Control-F>", self._show_search)

        # Selection highlight must sit ABOVE the per-cell colour tags, or the
        # cell backgrounds paint over it and the selection is invisible.
        self._text.tag_configure("sel",
                                 background="#3465a4",
                                 foreground="#ffffff")
        self._text.tag_raise("sel")

        # Key bindings
        self._text.bind("<Key>",          self._on_key)
        self._text.bind("<Control-Key>",  self._on_ctrl_key)
        self._text.bind("<Button-1>",     self._on_button1)
        self._text.bind("<ButtonRelease-1>", self._on_select_release)  # auto-copy
        self._text.bind("<Double-Button-1>", self._on_select_release)  # word select
        self._text.bind("<Triple-Button-1>", self._on_select_release)  # line select
        self._text.bind("<Control-Shift-KeyPress-C>", self._copy_selection)
        self._text.bind("<Control-Shift-KeyPress-V>", self._paste_to_ssh)
        self._text.bind("<Control-Shift-KeyPress-A>", self._select_all)
        # Middle-click pastes (classic X11/xterm behaviour)
        self._text.bind("<ButtonRelease-2>", self._paste_to_ssh)
        for seq in ("<<Paste>>", "<<Cut>>", "<<Clear>>"):
            self._text.bind(seq, lambda e: "break")

        # Right-click context menu (shown on Shift+Right-click, or as the
        # fallback gesture). Plain right-click does smart copy/paste below.
        self._menu = tk.Menu(self._text, tearoff=0)
        self._menu.add_command(label="Copy        (Ctrl+Shift+C)", command=self._copy_selection)
        self._menu.add_command(label="Paste       (Ctrl+Shift+V)", command=self._paste_to_ssh)
        self._menu.add_separator()
        self._menu.add_command(label="Select All  (Ctrl+Shift+A)", command=self._select_all)
        self._menu.add_command(label="Clear",      command=self.reset)
        self._menu.add_separator()
        self._menu.add_command(label="Zoom In  (Ctrl +)",  command=lambda: self._zoom(+1))
        self._menu.add_command(label="Zoom Out (Ctrl -)",  command=lambda: self._zoom(-1))
        self._menu.add_command(label="Reset Zoom (Ctrl 0)", command=self._reset_zoom)
        # Standard-terminal right-click: copy selection if any, else paste.
        self._text.bind("<Button-3>",        self._on_right_click)
        self._text.bind("<Shift-Button-3>",  self._show_context_menu)

        # Mouse-wheel: track scroll position
        self._text.bind("<MouseWheel>",    self._on_mousewheel)
        self._text.bind("<Button-4>",      self._on_mousewheel)   # Linux scroll up
        self._text.bind("<Button-5>",      self._on_mousewheel)   # Linux scroll down

        # Font zoom — Ctrl with +/-/0 or Ctrl+mouse-wheel
        self._text.bind("<Control-plus>",        lambda e: self._zoom(+1))
        self._text.bind("<Control-equal>",       lambda e: self._zoom(+1))
        self._text.bind("<Control-KP_Add>",      lambda e: self._zoom(+1))
        self._text.bind("<Control-minus>",       lambda e: self._zoom(-1))
        self._text.bind("<Control-KP_Subtract>", lambda e: self._zoom(-1))
        self._text.bind("<Control-0>",           self._reset_zoom)
        self._text.bind("<Control-MouseWheel>",  self._on_ctrl_wheel)
        self._text.bind("<Control-Button-4>",    lambda e: self._zoom(+1))
        self._text.bind("<Control-Button-5>",    lambda e: self._zoom(-1))

        self.bind("<Configure>", self._on_resize)

        if not self._pyte_ok:
            self._text.insert("1.0",
                              "pyte is not installed — terminal unavailable.\n"
                              "Run:  pip install pyte paramiko")

    # ── public API ────────────────────────────────────────────────────────────

    def connect_queue(self, ssh_queue: queue.Queue,
                      send_cb: Callable[[bytes], None],
                      close_cb: Callable[[], None]) -> None:
        self._ssh_queue = ssh_queue
        self._send_cb   = send_cb
        self._close_cb  = close_cb
        self._last_activity = time.time()   # fresh start → reset idle clock
        self._text.focus_set()

    def disconnect(self) -> None:
        self._ssh_queue = None
        self._send_cb   = None

    def idle_seconds(self) -> float:
        """Seconds since the last data sent or received (0 if never active)."""
        if not self._last_activity:
            return 0.0
        return time.time() - self._last_activity

    def set_resize_callback(self, cb: Callable[[int, int], None]) -> None:
        self._resize_cb = cb

    def set_broadcast_hook(self, cb: Optional[Callable[[str], bool]]) -> None:
        """Install a panel-level hook. While it returns True for given input,
        this terminal's keystrokes are broadcast to all terminals by the panel
        and NOT also sent locally (the panel includes this one in the fan-out)."""
        self._broadcast_hook = cb

    def sync_size(self) -> None:
        """
        Force-sync widget pixel size → pyte screen size → SSH PTY.
        Call this after SSH connects so the PTY matches the actual window.
        """
        self.update_idletasks()
        if not self.winfo_viewable():
            return                              # minimized/hidden → don't resize
        w = self._text.winfo_width()
        h = self._text.winfo_height()
        if w > 60 and h > 40 and self._char_w > 0 and self._char_h > 0:
            nc = max(10, (w - 4) // self._char_w)   # small margin → no left clip
            nr = max(5,  h // self._char_h)
            if nc != self._cols or nr != self._rows:
                self._cols, self._rows = nc, nr
                if self._pyte_ok and self._screen:
                    self._screen.resize(nr, nc)
                if self._resize_cb:
                    self._resize_cb(nc, nr)
                self._dirty = True

    def set_theme(self, name: str) -> None:
        """Switch colour theme; clears tag cache and forces full re-render."""
        t = THEMES.get(name, THEMES["Dark (default)"])
        self._theme_fg = t["fg"]
        self._theme_bg = t["bg"]
        self._tag_cache.clear()
        self.configure(bg=self._theme_bg)
        self._text.configure(bg=self._theme_bg, fg=self._theme_fg)
        self._text.tag_configure("CURSOR",
                                 foreground=self._theme_bg,
                                 background=self._theme_fg)
        # Full repaint needed — scrollback lines keep their (now stale) tags,
        # but those tags were just reconfigured, so colours update in place.
        # Force the active region to rebuild.
        self._first_render = True
        self._dirty = True

    def reset(self) -> None:
        if self._pyte_ok:
            self._screen = _TrackingScreen(self._cols, self._rows)
            self._stream = pyte.Stream(self._screen)
            self._tag_cache.clear()
            self._committed = 0
            self._prev_cy = 0
            self._first_render = True
            self._is_at_bottom = True
            self._text.delete("1.0", "end")
            self._dirty = True

    # ── detach / attach state transfer ──────────────────────────────────────────

    def export_state(self) -> Optional[dict]:
        """Snapshot everything needed to recreate this terminal's display in a
        new TerminalWidget (used by Detach/Attach so the scrollback and live
        screen survive the move — no reset, full history preserved)."""
        if not self._pyte_ok or self._screen is None:
            return None
        # Flush any rows that scrolled off but weren't committed to the Text yet.
        try:
            if self._screen.pending_scroll:
                self._full_render()
        except Exception:
            pass
        tagdefs = {}
        for t in self._text.tag_names():
            if t == "sel":
                continue
            try:
                tagdefs[t] = (
                    self._text.tag_cget(t, "foreground"),
                    self._text.tag_cget(t, "background"),
                    self._text.tag_cget(t, "underline"),
                )
            except tk.TclError:
                pass
        return {
            "screen":       self._screen,      # live pyte state — adopted as-is
            "stream":       self._stream,
            "prev_cy":      self._prev_cy,
            "is_at_bottom": self._is_at_bottom,
            "theme_fg":     self._theme_fg,
            "theme_bg":     self._theme_bg,
            "font_size":    int(self._font.cget("size")),
            "tagdefs":      tagdefs,
            "dump":         self._text.dump("1.0", "end-1c", text=True, tag=True),
        }

    def import_state(self, st: dict) -> None:
        """Restore a snapshot from export_state() into this fresh widget."""
        if not self._pyte_ok or not st:
            return

        # Theme + font first (so metrics are right before we size anything).
        self._theme_fg = st.get("theme_fg", self._theme_fg)
        self._theme_bg = st.get("theme_bg", self._theme_bg)
        self.configure(bg=self._theme_bg)
        self._text.configure(bg=self._theme_bg, fg=self._theme_fg)
        self._text.tag_configure("CURSOR",
                                 foreground=self._theme_bg,
                                 background=self._theme_fg)
        if st.get("font_size"):
            self._set_font_size(int(st["font_size"]))

        # Adopt the live pyte screen + stream so future output continues exactly
        # where it left off (cwd, running program, colours, cursor).
        self._screen = st["screen"]
        self._stream = st["stream"]
        self._cols   = self._screen.columns
        self._rows   = self._screen.lines

        # Recreate the scrollback colour tags (fg/bg/underline is enough; the
        # active region re-renders with full styling via _ensure_tag).
        self._tag_cache = set()
        for tname, cfg in st.get("tagdefs", {}).items():
            if tname in ("sel", "CURSOR"):
                continue
            fg, bg, under = cfg
            kw = {}
            if fg:    kw["foreground"] = fg
            if bg:    kw["background"] = bg
            if under: kw["underline"] = 1
            try:
                self._text.tag_configure(tname, **kw)
                self._text.tag_lower(tname, "sel")
            except tk.TclError:
                pass

        # Rebuild the text content (scrollback + screen) from the dump.
        self._text.delete("1.0", "end")
        open_tags: list = []
        for key, val, _idx in st.get("dump", []):
            if key == "text":
                self._text.insert("end", val,
                                  tuple(t for t in open_tags if t != "sel"))
            elif key == "tagon":
                open_tags.append(val)
            elif key == "tagoff" and val in open_tags:
                open_tags.remove(val)

        # Anchor the active region to the LAST n_rows lines, whatever the dump's
        # exact line count turned out to be.
        total = int(self._text.index("end-1c").split(".")[0])
        self._committed   = max(0, total - self._rows)
        self._prev_cy     = st.get("prev_cy", 0)
        self._is_at_bottom = st.get("is_at_bottom", True)
        self._first_render = True
        self._dirty        = True

    # ── 60 fps tick ───────────────────────────────────────────────────────────

    def _tick(self) -> None:
        # Capture the queue locally: _on_closed() nulls self._ssh_queue
        # mid-loop, which would otherwise crash the next get_nowait().
        q = self._ssh_queue
        if q is not None:
            try:
                while True:
                    kind, payload = q.get_nowait()
                    if kind == "data":
                        self._feed(payload)
                    elif kind == "close":
                        self._on_closed()
                        break
            except queue.Empty:
                pass

        if self._dirty:
            self._full_render()
            self._dirty = False

        self._after_id = self.after(16, self._tick)

    # ── data feed ─────────────────────────────────────────────────────────────

    def _feed(self, data: bytes) -> None:
        if not self._pyte_ok or self._stream is None:
            return
        self._last_activity = time.time()   # output from server = session in use
        try:
            self._stream.feed(data.decode("utf-8", errors="replace"))
        except Exception:
            pass
        self._dirty = True

    # ── rendering ─────────────────────────────────────────────────────────────

    def _full_render(self) -> None:
        """
        Incremental render — the key to a non-freezing terminal.

        Three cheap steps per frame instead of a full screen rebuild:
          1. Drain pending scrolled-off lines → ONE batched insert into the
             scrollback region, then trim the region to MAX_SCROLLBACK.
          2. Make sure the active region has exactly n_rows lines.
          3. Re-render ONLY the lines pyte marked dirty (+ the old & new cursor
             rows), each in a single text.insert() call.
        """
        if not self._pyte_ok or self._screen is None:
            return

        screen = self._screen
        text   = self._text
        n_rows = screen.lines
        n_cols = screen.columns
        cx, cy = screen.cursor.x, screen.cursor.y
        cy = min(cy, n_rows - 1)
        cx = min(cx, n_cols - 1)

        # Snapshot the at-bottom flag NOW. The text.insert calls below fire
        # _on_yscroll mid-render and would flip the flag to False before we
        # reach the see("end") check, breaking auto-scroll.
        follow_bottom = self._is_at_bottom

        # ── 1. Commit scrolled-off lines (single batched insert) ──────────
        pending = screen.pending_scroll
        if pending:
            screen.pending_scroll = []
            # A massive burst (e.g. `cat hugefile`) would all be trimmed away
            # anyway — keep only the last MAX_SCROLLBACK before rendering.
            if len(pending) > self.MAX_SCROLLBACK:
                pending = pending[-self.MAX_SCROLLBACK:]
            args: list = []
            for row in pending:
                args.extend(self._row_args(row, n_cols, None))
                args.append("\n"); args.append(())   # newline carries no tag
            # Insert the whole block right before the active region in one call
            text.insert(f"{self._committed + 1}.0", *args)
            self._committed += len(pending)

            # Trim oldest scrollback so the widget never grows without bound
            if self._committed > self.MAX_SCROLLBACK:
                excess = self._committed - self.MAX_SCROLLBACK
                text.delete("1.0", f"{excess + 1}.0")
                self._committed -= excess

        screen_start = self._committed + 1   # widget line of screen row 0

        # ── 2. Ensure the active region holds exactly n_rows lines ────────
        total_needed = self._committed + n_rows
        cur_lines = int(text.index("end-1c").split(".")[0])
        if cur_lines < total_needed:
            text.insert("end", "\n" * (total_needed - cur_lines))
        elif cur_lines > total_needed:
            text.delete(f"{total_needed}.end", "end")

        # ── 3. Redraw dirty lines only (+ old & new cursor rows) ──────────
        if self._first_render:
            dirty = set(range(n_rows))
            self._first_render = False
        else:
            dirty = set(screen.dirty)
            dirty.add(cy)
            dirty.add(self._prev_cy)
        screen.dirty.clear()

        for y in dirty:
            if y < 0 or y >= n_rows:
                continue
            line = screen_start + y
            cursor_col = cx if y == cy else None
            args = self._row_args(screen.buffer[y], n_cols, cursor_col)
            text.delete(f"{line}.0", f"{line}.end")
            if args:
                text.insert(f"{line}.0", *args)

        self._prev_cy = cy
        text.mark_set("insert", f"{screen_start + cy}.{cx}")

        # ── 4. Auto-scroll only when the user was at the bottom pre-render ──
        if follow_bottom:
            text.see("end")
            self._is_at_bottom = True   # see() fires _on_yscroll; keep coherent

        # Pin the horizontal view hard-left. pyte sizes each row to the widget
        # width, so we never want horizontal scroll — without this, a wide line
        # plus a far-right cursor scrolls the view right and clips the LEFT edge
        # (e.g. the first column of wide table output going invisible).
        text.xview_moveto(0.0)

    def _row_args(self, row, n_cols: int, cursor_col: Optional[int]) -> list:
        """
        Flatten a pyte row into alternating (text, taglist) args for a single
        Text.insert(index, t1, tags1, t2, tags2, …) call — far faster than one
        insert per span.
        """
        blank = self._blank_char

        def cell(i):
            # Works for live defaultdict rows AND materialised scrollback lists,
            # tolerating columns beyond the row's captured width.
            try:
                return row[i]
            except (KeyError, IndexError):
                return blank

        args: list = []
        x = 0
        while x < n_cols:
            is_cursor = (cursor_col is not None and x == cursor_col)
            char  = cell(x)
            start = x
            style = (char.fg, char.bg, char.bold,
                     char.italics, char.underscore, char.reverse)
            while x < n_cols and not (cursor_col is not None and x == cursor_col):
                c = cell(x)
                if (c.fg, c.bg, c.bold, c.italics,
                        c.underscore, c.reverse) != style:
                    break
                x += 1
            if x > start:
                span = "".join(cell(i).data if cell(i).data else " "
                               for i in range(start, x))
                args.append(span)
                args.append(self._ensure_tag(*style))
            if is_cursor and x < n_cols:
                c = cell(x)
                args.append(c.data or " ")
                args.append("CURSOR")
                x += 1
        return args

    def _ensure_tag(self, fg: str, bg: str, bold: bool,
                    italic: bool, under: bool, reverse: bool) -> str:
        tag = f"f{fg}_b{bg}_B{int(bold)}_i{int(italic)}_u{int(under)}_r{int(reverse)}"
        if tag in self._tag_cache:
            return tag

        kw: dict = {}
        if reverse:
            kw["foreground"] = _resolve_color(bg, True,  self._theme_fg, self._theme_bg)
            kw["background"] = _resolve_color(fg, False, self._theme_fg, self._theme_bg)
        else:
            kw["foreground"] = _resolve_color(fg, False, self._theme_fg, self._theme_bg)
            kw["background"] = _resolve_color(bg, True,  self._theme_fg, self._theme_bg)

        if bold and italic: kw["font"] = self._bi_font
        elif bold:          kw["font"] = self._bold_font
        elif italic:        kw["font"] = self._ital_font
        if under:           kw["underline"] = True

        self._text.tag_configure(tag, **kw)
        # Keep cell colour tags below the selection highlight so a selection
        # stays visible over coloured text.
        try:
            self._text.tag_lower(tag, "sel")
        except tk.TclError:
            pass
        self._tag_cache.add(tag)
        return tag

    # ── scroll tracking ───────────────────────────────────────────────────────

    # "At bottom" must mean the very last line is visible. A loose threshold
    # (e.g. 0.99) leaves you "stuck" at the bottom for a long buffer, snapping
    # back on every new line. 0.9999 ≈ exactly 1.0 but tolerant of rounding.
    _BOTTOM_EPS = 0.9999

    def _on_yscroll(self, first: str, last: str) -> None:
        """
        yscrollcommand callback — fires on EVERY view change (mouse wheel,
        scrollbar drag, programmatic scroll). Single source of truth for
        whether the user is parked at the bottom.
        """
        self._vsb.set(first, last)
        self._is_at_bottom = (float(last) >= self._BOTTOM_EPS)

    def _on_mousewheel(self, event: tk.Event) -> str:
        """Mouse-wheel scroll — scrolling triggers _on_yscroll, which updates
        the at-bottom flag, so nothing else to do here."""
        if event.num == 4:          # Linux scroll up
            self._text.yview_scroll(-3, "units")
        elif event.num == 5:        # Linux scroll down
            self._text.yview_scroll(3, "units")
        else:                       # Windows / macOS
            self._text.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    # ── font zoom ──────────────────────────────────────────────────────────────

    FONT_MIN, FONT_MAX = 7, 30

    def _on_ctrl_wheel(self, event: tk.Event) -> str:
        self._zoom(+1 if getattr(event, "delta", 0) > 0 else -1)
        return "break"

    def _reset_zoom(self, event=None) -> str:
        self._set_font_size(self.FONT_SIZE)
        return "break"

    def _zoom(self, delta: int) -> str:
        new = max(self.FONT_MIN, min(self.FONT_MAX,
                                     int(self._font.cget("size")) + delta))
        self._set_font_size(new)
        return "break"

    def _set_font_size(self, size: int) -> None:
        """Resize every terminal font (tags reference these Font objects, so
        they update in place), then re-sync the pyte/PTY geometry."""
        for f in (self._font, self._bold_font, self._ital_font, self._bi_font):
            f.configure(size=size)
        self._char_w = self._font.measure("W")
        self._char_h = self._font.metrics("linespace")
        self._first_render = True
        self._dirty = True
        self.after_idle(self.sync_size)

    # ── find bar (Ctrl+F) ───────────────────────────────────────────────────────

    def _build_search_bar(self) -> None:
        self._search_visible = False
        self._search_matches: list = []   # list of (start_index, end_index)
        self._search_idx = -1

        bar = tk.Frame(self, bg="#1e1e2e")
        self._search_bar = bar
        tk.Label(bar, text="Find:", bg="#1e1e2e", fg="#d3d7cf",
                 font=("Segoe UI", 9)).pack(side="left", padx=(8, 4), pady=3)
        self._search_var = tk.StringVar()
        ent = tk.Entry(bar, textvariable=self._search_var, width=28,
                       bg="#0d0d14", fg="#ffffff", insertbackground="#ffffff",
                       relief="flat")
        ent.pack(side="left", padx=2, pady=3)
        self._search_entry = ent
        self._search_count = tk.Label(bar, text="", bg="#1e1e2e", fg="#7d8fa6",
                                      font=("Segoe UI", 9))
        self._search_count.pack(side="left", padx=6)
        for txt, cmd in (("▲", lambda: self._search_step(-1)),
                         ("▼", lambda: self._search_step(+1)),
                         ("✕", self._hide_search)):
            tk.Button(bar, text=txt, command=cmd, bg="#1e1e2e", fg="#d3d7cf",
                      activebackground="#175ddc", activeforeground="#fff",
                      relief="flat", font=("Segoe UI", 9), cursor="hand2",
                      width=2).pack(side="left", padx=1)

        self._search_var.trace_add("write", lambda *_: self._run_search())
        ent.bind("<Return>",        lambda e: self._search_step(+1))
        ent.bind("<Shift-Return>",  lambda e: self._search_step(-1))
        ent.bind("<Escape>",        lambda e: self._hide_search())

    def _show_search(self, event=None) -> str:
        if not self._search_visible:
            self._search_bar.pack(side="top", fill="x", before=self._vsb)
            self._search_visible = True
        self._search_entry.focus_set()
        self._search_entry.select_range(0, "end")
        self._run_search()
        return "break"

    def _hide_search(self, event=None) -> str:
        if self._search_visible:
            self._search_bar.pack_forget()
            self._search_visible = False
        self._text.tag_remove("search", "1.0", "end")
        self._text.tag_remove("search_current", "1.0", "end")
        self._search_matches = []
        self._search_idx = -1
        self._text.focus_set()
        return "break"

    def _run_search(self) -> None:
        self._text.tag_remove("search", "1.0", "end")
        self._text.tag_remove("search_current", "1.0", "end")
        self._search_matches = []
        self._search_idx = -1
        term = self._search_var.get()
        if not term:
            self._search_count.config(text="")
            return
        idx = "1.0"
        while True:
            pos = self._text.search(term, idx, stopindex="end", nocase=1)
            if not pos:
                break
            end = f"{pos}+{len(term)}c"
            self._text.tag_add("search", pos, end)
            self._search_matches.append((pos, end))
            idx = end
        if self._search_matches:
            self._search_idx = 0
            self._highlight_current()
            self._search_count.config(text=f"1/{len(self._search_matches)}")
        else:
            self._search_count.config(text="0/0")

    def _search_step(self, direction: int) -> str:
        if not self._search_matches:
            self._run_search()
            return "break"
        self._search_idx = (self._search_idx + direction) % len(self._search_matches)
        self._highlight_current()
        self._search_count.config(
            text=f"{self._search_idx + 1}/{len(self._search_matches)}")
        return "break"

    def _highlight_current(self) -> None:
        self._text.tag_remove("search_current", "1.0", "end")
        if 0 <= self._search_idx < len(self._search_matches):
            start, end = self._search_matches[self._search_idx]
            self._text.tag_add("search_current", start, end)
            self._text.see(start)

    # ── keyboard ─────────────────────────────────────────────────────────────

    def _on_key(self, event: tk.Event) -> str:
        state  = event.state
        keysym = event.keysym
        char   = event.char

        if (state & 0x4) and (state & 0x1):
            return "break"   # Ctrl+Shift handled by explicit bindings
        if state & 0x4:
            return "break"   # Ctrl handled by _on_ctrl_key

        if keysym in _KEY_MAP:
            self._send(_KEY_MAP[keysym])
            return "break"

        if char and 32 <= ord(char[0]):
            self._send(char)
            # Typing = intent to see current output → snap to bottom
            self._is_at_bottom = True
            return "break"

        return "break"

    def _on_ctrl_key(self, event: tk.Event) -> str:
        if event.state & 0x1:
            return          # Ctrl+Shift: fall through to explicit bindings
        c = event.keysym.lower()
        if c in _CTRL_MAP:
            self._send(_CTRL_MAP[c])
            self._is_at_bottom = True
        return "break"

    # ── mouse copy / context menu ──────────────────────────────────────────────

    def _on_button1(self, event=None) -> None:
        """Left-click: focus the terminal but let Tk's default text selection
        (click-drag, double/triple click) run — so returning None, not 'break'."""
        self._text.focus_set()
        return None

    def _on_select_release(self, event=None) -> None:
        """MobaXterm-style auto-copy: as soon as a mouse selection is made,
        copy it to the clipboard. Returns None so the highlight stays visible."""
        try:
            if self._text.tag_ranges("sel"):
                sel = self._text.get("sel.first", "sel.last")
                if sel:
                    self._text.clipboard_clear()
                    self._text.clipboard_append(sel)
        except tk.TclError:
            pass
        return None

    def _on_right_click(self, event=None) -> str:
        """Standard-terminal right-click: if text is selected, copy it (and
        clear the highlight); otherwise paste the clipboard into the shell.
        This is what PuTTY / Windows Terminal do, and makes pasting a password
        a single right-click."""
        self._text.focus_set()
        if self._text.tag_ranges("sel"):
            self._copy_selection()
            try:
                self._text.tag_remove("sel", "1.0", "end")
            except tk.TclError:
                pass
        else:
            self._paste_to_ssh()
        return "break"

    def _show_context_menu(self, event=None) -> str:
        """Full context menu — bound to Shift+Right-click."""
        has_sel = bool(self._text.tag_ranges("sel"))
        try:
            self._menu.entryconfigure(0, state="normal" if has_sel else "disabled")
        except tk.TclError:
            pass
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()
        return "break"

    def _select_all(self, event=None) -> str:
        try:
            self._text.tag_add("sel", "1.0", "end-1c")
            sel = self._text.get("sel.first", "sel.last")
            if sel:
                self._text.clipboard_clear()
                self._text.clipboard_append(sel)
        except tk.TclError:
            pass
        return "break"

    def _copy_selection(self, event=None) -> str:
        try:
            sel = self._text.get("sel.first", "sel.last")
            self._text.clipboard_clear()
            self._text.clipboard_append(sel)
        except tk.TclError:
            pass
        return "break"

    def _read_clipboard(self) -> str:
        """Read clipboard text robustly. Tk's default clipboard_get() on Windows
        silently fails (TclError) when the text is offered only as UTF8_STRING/
        STRING, or briefly while another app holds the clipboard — which made
        pasting a copied password do nothing. Try several formats in turn."""
        for kwargs in ({}, {"type": "UTF8_STRING"}, {"type": "STRING"}):
            try:
                data = self._text.clipboard_get(**kwargs)
                if data:
                    return data
            except tk.TclError:
                continue
        try:                                   # last resort
            return self.selection_get(selection="CLIPBOARD")
        except tk.TclError:
            return ""

    def _paste_to_ssh(self, event=None) -> str:
        txt = self._read_clipboard()
        if txt:
            self._send(txt)
            self._is_at_bottom = True
        return "break"

    def _send(self, s: str) -> None:
        self._last_activity = time.time()       # user input = session in use
        # Broadcast mode: the panel fans this out to every terminal (including
        # this one), so don't also send locally.
        if self._broadcast_hook is not None and self._broadcast_hook(s):
            return
        if self._send_cb:
            self._send_cb(s.encode("utf-8"))

    def send_external(self, data: bytes) -> None:
        """Inject bytes straight to this terminal's SSH (used by broadcast and
        auto-run-on-connect). Bypasses the broadcast hook to avoid recursion."""
        if self._send_cb:
            self._last_activity = time.time()
            self._send_cb(data)

    # ── resize ────────────────────────────────────────────────────────────────

    def _on_resize(self, event: tk.Event) -> None:
        if self._char_w == 0 or self._char_h == 0:
            return
        # Ignore degenerate resize events. When the window is minimized/iconified
        # the frame collapses to a tiny size; resizing the pyte screen + PTY down
        # to a few rows then back corrupts the layout (huge blank gap + duplicated
        # prompt on restore). Only react to real, on-screen sizes.
        if not self.winfo_viewable():
            return
        if event.width < 80 or event.height < 50:
            return
        # Size from the Text widget, not the frame: event.width includes the
        # scrollbar, so columns were over-counted → rows wider than the visible
        # area → horizontal scroll clips the left edge. Subtract the scrollbar
        # width plus a small margin so the last column always fits.
        sb = self._vsb.winfo_width() if self._vsb.winfo_ismapped() else 16
        avail_w = max(self._char_w * 10, event.width - sb - 4)
        new_cols = max(10, avail_w        // self._char_w)
        new_rows = max(5,  event.height   // self._char_h)
        if new_cols != self._cols or new_rows != self._rows:
            self._cols, self._rows = new_cols, new_rows
            if self._pyte_ok and self._screen:
                self._screen.resize(new_rows, new_cols)
            if self._resize_cb:
                self._resize_cb(new_cols, new_rows)
            # Committed scrollback stays (wrap="none" keeps it intact);
            # rebuild the active region next paint.
            self._first_render = True
            self._dirty = True

    # ── events ────────────────────────────────────────────────────────────────

    def _on_closed(self) -> None:
        self._ssh_queue = None
        self._send_cb   = None
        self._text.insert("end", "\n\n— Connection closed —\n")
        self._text.see("end")
        if self._close_cb:
            self._close_cb()

    # ── cleanup ───────────────────────────────────────────────────────────────

    def destroy(self) -> None:
        try:
            self.after_cancel(self._after_id)
        except Exception:
            pass
        super().destroy()
