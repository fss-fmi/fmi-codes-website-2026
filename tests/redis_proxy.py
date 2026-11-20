"""A TCP proxy in front of a real Redis that a test switches between the outage kinds (#256).

- up:      bytes pass both ways.
- hang:    connections stay open and every byte is dropped, like a stalled master or a
           dead pod's IP during a Sentinel failover. New connections are accepted the same way.
- refuse:  the port is closed and every open connection is dropped, like a crashed Redis.
- cut():   drops every open connection now, whatever the mode, to kill Redis mid-request.
"""

import random
import socket
import threading
from urllib.parse import urlparse

# refuse() closes the port and up() binds the same one again. A port from the ephemeral
# range (32768 and up on Linux, 49152 on Windows) can be handed to an outgoing connection
# in between, and the rebind then fails with "Address already in use".
_PORTS_BELOW_EPHEMERAL = range(20000, 32768)
_BIND_ATTEMPTS = 50


class RedisProxy:
    def __init__(self, upstream_url: str):
        parsed = urlparse(upstream_url)
        self._upstream = (parsed.hostname or "localhost", parsed.port or 6379)
        self._db = parsed.path or "/0"
        self._lock = threading.Lock()
        self._sockets: set[socket.socket] = set()
        self._listener: socket.socket | None = None
        self.mode = "up"
        self.port = 0
        self._listen()

    @property
    def url(self) -> str:
        return f"redis://127.0.0.1:{self.port}{self._db}"

    def up(self) -> None:
        self.mode = "up"
        if self._listener is None:
            try:
                self._listen()
            except OSError as error:
                self.mode = "refuse"
                raise OSError(
                    error.errno, f"proxy could not listen on port {self.port} again: {error}"
                ) from error

    def hang(self) -> None:
        self.mode = "hang"

    def refuse(self) -> None:
        self.mode = "refuse"
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.close()
        self.cut()

    def cut(self) -> None:
        with self._lock:
            sockets, self._sockets = self._sockets, set()
        for sock in sockets:
            _close(sock)

    def close(self) -> None:
        self.refuse()

    def _listen(self) -> None:
        if self.port:
            listener = _bind(self.port)
        else:
            listener, self.port = _bind_below_ephemeral()
        listener.listen(64)
        self._listener = listener
        threading.Thread(target=self._accept, args=(listener,), daemon=True).start()

    def _accept(self, listener: socket.socket) -> None:
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            if self.mode == "refuse":
                _close(client)
                continue
            upstream = None
            if self.mode == "up":
                try:
                    upstream = socket.create_connection(self._upstream, timeout=5)
                    upstream.settimeout(None)
                except OSError:
                    _close(client)
                    continue
            with self._lock:
                self._sockets.add(client)
                if upstream is not None:
                    self._sockets.add(upstream)
            threading.Thread(target=self._pump, args=(client, upstream), daemon=True).start()
            if upstream is not None:
                threading.Thread(target=self._pump, args=(upstream, client), daemon=True).start()

    def _pump(self, source: socket.socket, target: socket.socket | None) -> None:
        try:
            while data := source.recv(65536):
                if self.mode == "up" and target is not None:
                    target.sendall(data)
        except OSError:
            pass
        finally:
            _close(source)
            if target is not None:
                _close(target)


def _bind(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", port))
    except OSError:
        listener.close()
        raise
    return listener


def _bind_below_ephemeral() -> tuple[socket.socket, int]:
    for port in random.sample(_PORTS_BELOW_EPHEMERAL, _BIND_ATTEMPTS):
        try:
            return _bind(port), port
        except OSError:
            continue
    raise OSError(f"no free port in {_PORTS_BELOW_EPHEMERAL} after {_BIND_ATTEMPTS} tries")


def _close(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()
