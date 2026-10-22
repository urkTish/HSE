"""A tiny in-process SMTP server for the mailer tests (no real mail server, no network)."""

from __future__ import annotations

import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Inbox:
    messages: list[tuple[str, list[str], bytes]] = field(default_factory=list)
    # RCPT TO replies by address (e.g. {"gone@contractor.sa": "550 5.1.1 no such user"})
    refuse: dict[str, str] = field(default_factory=dict)
    logins: list[str] = field(default_factory=list)


class _Handler(socketserver.StreamRequestHandler):
    inbox: Inbox

    def _say(self, line: str) -> None:
        self.wfile.write((line + "\r\n").encode())
        self.wfile.flush()

    def handle(self) -> None:
        self._say("220 fake.smtp ESMTP")
        sender, rcpts = "", []
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode(errors="replace").rstrip("\r\n")
            verb = line.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self.wfile.write(b"250-fake.smtp\r\n250-AUTH PLAIN LOGIN\r\n250 8BITMIME\r\n")
                self.wfile.flush()
            elif verb == "AUTH":
                self.inbox.logins.append(line)
                self._say("235 2.7.0 Authentication successful")
            elif verb == "MAIL":
                sender, rcpts = line.split(":", 1)[1].strip().strip("<>").split(">")[0], []
                self._say("250 OK")
            elif verb == "RCPT":
                addr = line.split(":", 1)[1].strip().strip("<>").split(">")[0]
                if addr in self.inbox.refuse:
                    self._say(self.inbox.refuse[addr])
                else:
                    rcpts.append(addr)
                    self._say("250 OK")
            elif verb == "DATA":
                self._say("354 End data with <CR><LF>.<CR><LF>")
                chunks: list[bytes] = []
                while True:
                    d = self.rfile.readline()
                    if d in (b".\r\n", b""):
                        break
                    chunks.append(d[1:] if d.startswith(b"..") else d)
                self.inbox.messages.append((sender, rcpts, b"".join(chunks)))
                self._say("250 OK queued")
            elif verb == "RSET":
                sender, rcpts = "", []
                self._say("250 OK")
            elif verb == "QUIT":
                self._say("221 Bye")
                return
            else:
                self._say("250 OK")


@contextmanager
def smtp_server() -> Iterator[tuple[int, Inbox]]:
    inbox = Inbox()
    handler = type("H", (_Handler,), {"inbox": inbox})
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield server.server_address[1], inbox
    finally:
        server.shutdown()
        server.server_close()
