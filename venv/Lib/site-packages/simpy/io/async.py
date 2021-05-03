import socket
import ssl
import errno
import asyncore
from time import sleep

from simpy.io.base import (BaseIOEnvironment, BaseTCPSocket, BaseSSLSocket,
        socket_error)
from simpy.io.platform import blocking_io_errors
from simpy.io._compat import PY2

if PY2:
    from simpy.io._compat import BlockingIOError


class Environment(BaseIOEnvironment):
    def _iowait(self, timeout):
        if self.fds:
            asyncore.loop(timeout, False, self.fds, 1)
        else:
            sleep(timeout)


class TCPSocket(BaseTCPSocket):
    def __init__(self, env, sock=None):
        BaseTCPSocket.__init__(self, env, sock)

        # Create handler and attach callbacks.
        # Note: asyncore.dispatcher will overwrite the fd entry in the fd map.
        self.handler = asyncore.dispatcher(self.sock, map=self.env.fds)
        self.handler.readable = self._readable
        self.handler.handle_read = self._do_read
        self.handler.handle_accept = self._do_accept
        self.handler.writable = self._writable
        self.handler.handle_write = self._do_write

    def _do_read(self):
        try:
            self._reader._value = self.sock.recv(self._reader.amount)
            if not self._reader._value:
                self._reader._ok = False
                self._reader._value = socket_error(errno.ECONNRESET)
            else:
                self._reader._ok = True
            self.env.schedule(self._reader)
        except BlockingIOError:
            return
        except socket.error as e:
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            self._reader.fail(e)
        self._reader = None

    def _do_write(self):
        try:
            self._writer._value = self.sock.send(self._writer.data)
            self._writer._ok = True
            self.env.schedule(self._writer)
        except BlockingIOError:
            return
        except socket.error as e:
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            self._writer.fail(e)
        self._writer = None

    def _do_accept(self):
        try:
            self._reader._value = type(self)(self.env, self.sock.accept()[0])
            self._reader._ok = True
            self.env.schedule(self._reader)
        except BlockingIOError:
            return
        except socket.error as e:
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            self._reader.fail(e)
        self._reader = None

    def _readable(self):
        return self._reader is not None

    def _writable(self):
        return self._writer is not None

    def bind(self, address):
        self.sock.bind(address)
        self.handler.handle_read = self._do_accept

    def close(self):
        try:
            fileno = self.fileno()

            del self.env.fds[fileno]

            # Fail events.
            if self._reader is not None:
                self._reader.fail(socket_error(errno.EBADF))
                self._reader = None
            if self._writer is not None:
                self._writer.fail(socket_error(errno.EBADF))
                self._writer = None
            self.sock.close()
        except socket.error as e:
            if e.errno == errno.EBADF:
                return
            raise e


class SSLSocket(BaseSSLSocket):
    def __init__(self, env, sock=None, **kwargs):
        BaseSSLSocket.__init__(self, env, sock, **kwargs)

        # FIXME This code duplication with TCPSocket is ugly. Maybe provide SSL
        # functionality as a mixin?

        # Create handler and attach callbacks.
        # Note: asyncore.dispatcher will overwrite the fd entry in the fd map.
        self.handler = asyncore.dispatcher(self.sock, map=self.env.fds)
        self.handler.readable = self._readable
        self.handler.handle_read = self._do_read
        self.handler.handle_accept = self._do_accept
        self.handler.writable = self._writable
        self.handler.handle_write = self._do_write

        self._handshake_read = None
        self._handshake_write = None

    # FIXME See above for code duplication.
    def bind(self, address):
        self.sock.bind(address)
        self.handler.handle_read = self._do_accept

    # FIXME See above for code duplication.
    def _readable(self):
        return self._reader is not None

    # FIXME See above for code duplication.
    def _writable(self):
        return self._writer is not None

    def _ssl_readable(self):
        return self._ssl_event is not None and self._handshake_read

    def _ssl_writable(self):
        return self._ssl_event is not None and self._handshake_write

    def _do_read(self):
        try:
            self._reader._value = self.sock.recv(self._reader.amount)
            if not self._reader._value:
                self._reader._ok = False
                self._reader._value = socket_error(errno.ECONNRESET)
            else:
                self._reader._ok = True
            self.env.schedule(self._reader)
        except (BlockingIOError, ssl.SSLWantReadError):
            return
        except socket.error as e:
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            self._reader.fail(e)
        self._reader = None

    def _do_write(self):
        try:
            self._writer._value = self.sock.send(self._writer.data)
            self._writer._ok = True
            self.env.schedule(self._writer)
        except (BlockingIOError, ssl.SSLWantWriteError):
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            return
        except socket.error as e:
            self._writer.fail(e)
        self._writer = None

    def _do_accept(self):
        try:
            sock = type(self)(self.env, self.sock.accept()[0])
            sock.handshake(False)
            self._reader._value = sock
            self._reader._ok = True
            self.env.schedule(self._reader)
        except BlockingIOError:
            return
        except socket.error as e:
            if e.errno in blocking_io_errors:
                # Python 2 branch.
                return
            self._reader.fail(e)
        self._reader = None

    def _ssl_handshake_read(self):
        self._ssl_event = self.env.event()
        self._handshake_read = True

    def _ssl_handshake_write(self):
        self._ssl_event = self.env.event()
        self._handshake_write = True

    def handshake(self, initiate=True):
        # FIXME Ugly hack.
        BaseSSLSocket.handshake(self, initiate)

        self.handler.readable = self._ssl_readable
        self.handler.writable = self._ssl_writable
        self.handler.handle_read = self._do_handshake
        self.handler.handle_write = self._do_handshake

    def _do_handshake(self):
        # FIXME Ugly hack.
        self._handshake_read = False
        self._handshake_write = False

        BaseSSLSocket._do_handshake(self)

        if self._ssl_event is None:
            self.handler.readable = self._readable
            self.handler.writable = self._writable
            self.handler.handle_read = self._do_read
            self.handler.handle_write = self._do_write

    def close(self):
        try:
            fileno = self.fileno()

            del self.env.fds[fileno]
            # FIXME Abort ssl_events of the handshake.

            # Fail events.
            if self._reader is not None:
                self._reader.fail(socket_error(errno.EBADF))
                self._reader = None
            if self._writer is not None:
                self._writer.fail(socket_error(errno.EBADF))
                self._writer = None
            self.sock.close()
        except socket.error as e:
            if e.errno == errno.EBADF:
                return
            raise e
