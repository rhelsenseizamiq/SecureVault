"""
SSH connection using paramiko.SSHClient — high-level, reliable API.
Supports: password auth, private key auth, jump host (bastion), port forwarding.

All blocking I/O runs on daemon threads. Results delivered via self.queue as
  ('data', bytes)  or  ('close', None).
The UI polls the queue with after().

Log file: %APPDATA%/SecureVault/zterm.log
"""
import logging
import os
import queue
import socket
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import paramiko
    PARAMIKO_OK = True
except ImportError:
    PARAMIKO_OK = False

try:
    from config import ZTERM_KEEPALIVE_SEC
except Exception:                       # standalone / import-order safety
    ZTERM_KEEPALIVE_SEC = 30


# ── logger ───────────────────────────────────────────────────────────────────

def _setup_log() -> logging.Logger:
    log_dir  = Path(os.getenv("APPDATA", Path.home())) / "SecureVault"
    log_dir.mkdir(parents=True, exist_ok=True)
    lg = logging.getLogger("zterm.ssh")
    if not lg.handlers:
        fh = logging.FileHandler(log_dir / "zterm.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        lg.addHandler(fh)
        lg.setLevel(logging.DEBUG)
    return lg

log = _setup_log()


# ── port-forward worker ───────────────────────────────────────────────────────

class _PortForwardThread(threading.Thread):
    """
    Listens on localhost:local_port and tunnels each connection to
    remote_host:remote_port via the given SSHClient transport.
    """
    def __init__(self, client: "paramiko.SSHClient",
                 local_port: int, remote_host: str, remote_port: int) -> None:
        super().__init__(daemon=True, name=f"pf-{local_port}")
        self._client      = client
        self._local_port  = local_port
        self._remote_host = remote_host
        self._remote_port = remote_port
        self._stop_evt    = threading.Event()

    def run(self) -> None:
        try:
            srv = socket.socket()
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", self._local_port))
            srv.listen(5)
            srv.settimeout(1.0)
            log.info("Port forward: 127.0.0.1:%d -> %s:%d",
                     self._local_port, self._remote_host, self._remote_port)
            while not self._stop_evt.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                threading.Thread(
                    target=self._handle, args=(conn,), daemon=True
                ).start()
        except Exception as e:
            log.error("Port forward bind failed: %s", e)

    def _handle(self, conn: socket.socket) -> None:
        try:
            transport = self._client.get_transport()
            if transport is None or not transport.is_active():
                conn.close()
                return
            channel = transport.open_channel(
                "direct-tcpip",
                (self._remote_host, self._remote_port),
                conn.getpeername(),
            )
            _bridge_sockets(conn, channel)
        except Exception as e:
            log.debug("Port forward handler: %s", e)
        finally:
            try: conn.close()
            except Exception: pass

    def stop(self) -> None:
        self._stop_evt.set()


def _bridge_sockets(sock: socket.socket, channel: "paramiko.Channel") -> None:
    """Bidirectionally copy between a raw socket and a paramiko channel."""
    import select
    channel.setblocking(False)
    sock.setblocking(False)
    while True:
        r, _, _ = select.select([sock, channel], [], [], 1.0)
        if not r:
            continue
        if sock in r:
            data = sock.recv(4096)
            if not data:
                break
            channel.sendall(data)
        if channel in r:
            try:
                data = channel.recv(4096)
            except Exception:
                break
            if not data:
                break
            sock.sendall(data)


# ── main SSH connection ───────────────────────────────────────────────────────

class SSHConnection:
    CONNECT_TIMEOUT = 15

    def __init__(self) -> None:
        self._client:    Optional["paramiko.SSHClient"] = None
        self._jump:      Optional["paramiko.SSHClient"] = None
        self._channel:   Optional["paramiko.Channel"]  = None
        self._thread:    Optional[threading.Thread]    = None
        self._pf_threads: List[_PortForwardThread]     = []
        self._running = False

        self.queue: queue.Queue = queue.Queue()

    # ------------------------------------------------------------------ connect

    def connect(self, host: str, port: int, username: str,
                password: str = "", key_path: str = "",
                cols: int = 80, rows: int = 24,
                jump_host: str = "", jump_port: int = 22,
                jump_user: str = "", jump_password: str = "",
                jump_key_path: str = "",
                port_forwards: list = ()) -> None:
        if not PARAMIKO_OK:
            raise RuntimeError("paramiko is not installed.\nRun: pip install paramiko")

        log.info("Connecting %s@%s:%s%s",
                 username, host, port,
                 f"  via {jump_host}:{jump_port}" if jump_host else "")

        sock = None

        # ── Jumphost ──────────────────────────────────────────────────────
        if jump_host:
            self._jump = paramiko.SSHClient()
            self._jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            jkw = dict(hostname=jump_host, port=jump_port, username=jump_user,
                       timeout=self.CONNECT_TIMEOUT,
                       look_for_keys=False, allow_agent=False)
            if jump_key_path:
                jkw["key_filename"] = jump_key_path
            elif jump_password:
                jkw["password"] = jump_password
            try:
                self._jump.connect(**jkw)
            except Exception as e:
                # Make it obvious the JUMP host (not the target) was the problem.
                raise RuntimeError(
                    f"Jump host {jump_user}@{jump_host}:{jump_port} — {e}") from e
            log.info("Jump host connected: %s@%s:%s", jump_user, jump_host, jump_port)

            transport = self._jump.get_transport()
            try:
                transport.set_keepalive(ZTERM_KEEPALIVE_SEC)
            except Exception:
                pass
            sock = transport.open_channel(
                "direct-tcpip", (host, port), ("127.0.0.1", 0)
            )

        # ── Target host ───────────────────────────────────────────────────
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kw = dict(
            hostname=host, port=port, username=username,
            timeout=self.CONNECT_TIMEOUT,
            banner_timeout=self.CONNECT_TIMEOUT,
            auth_timeout=self.CONNECT_TIMEOUT,
            look_for_keys=False, allow_agent=False,
        )
        if sock:
            kw["sock"] = sock          # route through jump channel
        if key_path:
            kw["key_filename"] = key_path
        elif password:
            kw["password"] = password

        client.connect(**kw)
        log.info("Authenticated: %s@%s:%s", username, host, port)

        # Keepalive stops the server dropping an idle session (and detects dead
        # links quickly so the UI can auto-reconnect).
        try:
            client.get_transport().set_keepalive(ZTERM_KEEPALIVE_SEC)
        except Exception:
            pass

        channel = client.invoke_shell(
            term="xterm-256color", width=cols, height=rows
        )
        channel.settimeout(0)

        self._client  = client
        self._channel = channel
        self._running = True

        # ── Start port forwards ───────────────────────────────────────────
        for pf in port_forwards:
            t = _PortForwardThread(client, pf.local_port,
                                   pf.remote_host, pf.remote_port)
            t.start()
            self._pf_threads.append(t)

        self._thread = threading.Thread(target=self._read_loop,
                                        daemon=True, name="zterm-reader")
        self._thread.start()
        log.info("Shell open — read loop started")

    # ------------------------------------------------------------------ I/O

    def send(self, data: bytes) -> None:
        if self._channel and not self._channel.closed:
            try:
                self._channel.sendall(data)
            except OSError as e:
                log.warning("send: %s", e)

    def resize(self, cols: int, rows: int) -> None:
        if self._channel and not self._channel.closed:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except OSError:
                pass

    def close(self) -> None:
        log.info("Closing connection")
        self._running = False
        for t in self._pf_threads:
            t.stop()
        self._pf_threads.clear()
        for obj in (self._channel, self._client, self._jump):
            if obj:
                try: obj.close()
                except Exception: pass

    def open_sftp(self) -> Optional["paramiko.SFTPClient"]:
        if self._client:
            try:
                return self._client.open_sftp()
            except Exception as e:
                log.error("SFTP open: %s", e)
        return None

    # ── SSH key utilities ─────────────────────────────────────────────────

    @staticmethod
    def generate_key_pair(key_type: str = "ed25519",
                          bits: int = 4096,
                          passphrase: str = "") -> Tuple[str, str]:
        """
        Generate an SSH key pair. Returns (private_key_pem, public_key_openssh).
        key_type: "ed25519" or "rsa"
        """
        import base64, io
        from cryptography.hazmat.primitives import serialization

        pw = passphrase.encode() if passphrase else None
        enc = (serialization.BestAvailableEncryption(pw)
               if pw else serialization.NoEncryption())

        if key_type == "ed25519":
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            priv_crypto = Ed25519PrivateKey.generate()
            key_name = "ssh-ed25519"
        else:
            from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
            from cryptography.hazmat.backends import default_backend
            priv_crypto = generate_private_key(65537, bits, default_backend())
            key_name = "ssh-rsa"

        # Private key in OpenSSH format
        priv_pem = priv_crypto.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.OpenSSH,
            enc,
        ).decode()

        # Public key in OpenSSH format
        pub_bytes = priv_crypto.public_key().public_bytes(
            serialization.Encoding.OpenSSH,
            serialization.PublicFormat.OpenSSH,
        ).decode()

        return priv_pem, f"{pub_bytes} zterm-generated"

    # ------------------------------------------------------------------ props

    @property
    def is_active(self) -> bool:
        return (self._channel is not None
                and not self._channel.closed
                and self._client is not None
                and self._client.get_transport() is not None
                and self._client.get_transport().is_active())

    # ------------------------------------------------------------------ reader

    def _read_loop(self) -> None:
        while self._running:
            try:
                if self._channel is None or self._channel.closed:
                    break
                if self._channel.recv_ready():
                    data = self._channel.recv(4096)
                    if not data:
                        break
                    self.queue.put(("data", data))
                else:
                    time.sleep(0.01)
            except Exception as e:
                log.error("Read loop: %s", e)
                break
        self.queue.put(("close", None))
        log.info("Read loop exited")


# ── one-off non-interactive command runner (used by Multi-Exec) ───────────────

def _connect_client(host, port, username, password, key_path,
                    jump_host, jump_port, jump_user, jump_password, jump_key_path,
                    connect_timeout):
    """Open a paramiko SSHClient (optionally through a jump host). Returns
    (client, jump_client). Raises on failure. Caller must close both."""
    jump = None
    sock = None
    if jump_host:
        jump = paramiko.SSHClient()
        jump.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        jkw = dict(hostname=jump_host, port=jump_port, username=jump_user,
                   timeout=connect_timeout, look_for_keys=False, allow_agent=False)
        if jump_key_path:
            jkw["key_filename"] = jump_key_path
        elif jump_password:
            jkw["password"] = jump_password
        jump.connect(**jkw)
        sock = jump.get_transport().open_channel(
            "direct-tcpip", (host, port), ("127.0.0.1", 0))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, port=port, username=username,
              timeout=connect_timeout, banner_timeout=connect_timeout,
              auth_timeout=connect_timeout, look_for_keys=False, allow_agent=False)
    if sock:
        kw["sock"] = sock
    if key_path:
        kw["key_filename"] = key_path
    elif password:
        kw["password"] = password
    client.connect(**kw)
    return client, jump


def _close_quiet(*objs):
    for c in objs:
        if c:
            try:
                c.close()
            except Exception:
                pass


def run_command(host: str, port: int, username: str,
                password: str = "", key_path: str = "", command: str = "",
                jump_host: str = "", jump_port: int = 22,
                jump_user: str = "", jump_password: str = "",
                jump_key_path: str = "",
                connect_timeout: int = 15, exec_timeout: int = 30,
                get_pty: bool = False) -> dict:
    """
    Open a throw-away SSH connection, run `command` non-interactively, and return
    a result dict: {host, ok, exit_status, stdout, stderr, error}. Never raises —
    failures are reported in the dict so a batch run can show per-server results.
    """
    result = {"host": host, "ok": False, "exit_status": None,
              "stdout": "", "stderr": "", "error": ""}
    if not PARAMIKO_OK:
        result["error"] = "paramiko not installed"
        return result

    jump = client = None
    try:
        client, jump = _connect_client(
            host, port, username, password, key_path,
            jump_host, jump_port, jump_user, jump_password, jump_key_path,
            connect_timeout)
        # get_pty=True allocates a pseudo-terminal so `sudo` (and other tools that
        # require a TTY) work. Note: with a PTY, stderr is folded into stdout.
        stdin, stdout, stderr = client.exec_command(
            command, timeout=exec_timeout, get_pty=get_pty)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        status = stdout.channel.recv_exit_status()
        result.update(ok=(status == 0), exit_status=status, stdout=out, stderr=err)
    except Exception as e:  # noqa: BLE001 — report every failure per host
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        _close_quiet(client, jump)
    return result


def test_auth(host: str, port: int, username: str,
              password: str = "", key_path: str = "",
              jump_host: str = "", jump_port: int = 22,
              jump_user: str = "", jump_password: str = "",
              jump_key_path: str = "", connect_timeout: int = 12) -> dict:
    """
    Just verify the credential can authenticate (connect, then disconnect).
    Returns {host, ok, error}. Never raises.
    """
    result = {"host": host, "ok": False, "error": ""}
    if not PARAMIKO_OK:
        result["error"] = "paramiko not installed"
        return result
    jump = client = None
    try:
        client, jump = _connect_client(
            host, port, username, password, key_path,
            jump_host, jump_port, jump_user, jump_password, jump_key_path,
            connect_timeout)
        result["ok"] = True
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
    finally:
        _close_quiet(client, jump)
    return result
