from __future__ import absolute_import

import select
import socket
import ssl
import errno
from time import time, sleep
from socket import error as SocketError

from simpy._compat import PY2
from simpy.io.platform import blocking_io_errors
from simpy.io.base import (BaseIOEnvironment, BaseTCPSocket, BaseSSLSocket,
        socket_error)


class Environment(BaseIOEnvironment):
    def __init__(self, fds=None):
        BaseIOEnvironment.__init__(self, fds)

        # TODO Use an ordered set?
        self._rd, self._wd, self._xd = [], [], []

    def _iowait(self, timeout):
        # Windows quirk: select() does not take empty lists.
        if not (self._rd or self._wd or self._xd):
            if timeout is None:
                # Warning: This point represents a user error. No request to
                # read or write from a socket has been given and no timeout has
                # been given. The program will sleep forever.
                # It has been decided to not raise a warning or exception in
                # this case, because it is not feasible to detect this case in
                # the other backends. Let's see if we hit enough real world
                # cases to convince us otherwise.
                while True:
                    sleep(1)

            to = time() + timeout
            while True:
                duration = to - time()
                if duration <= 0:
                    break
                sleep(duration)
            return

        rd, wd, xd = select.select(self._rd, self._wd, self._xd, timeout)

        for fd in rd:
            self.fds[fd]._ready_read()
            self._rd.remove(fd)

        for fd in wd:
            self.fds[fd]._ready_write()
            self._wd.remove(fd)

        # TODO xd?


class TCPSocket(BaseTCPSocket):
    def _do_read(self):
        try:
            self._reader._value = self.sock.recv(self._reader.amount)
            if not self._reader._value:
                self._reader._ok = False
                self._reader._value = socket_error(errno.ECONNRESET)
            else:
                self._reader._ok = True
            self.env.schedule(self._reader)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._rd.append(self.sock.fileno())
                return

            self._reader.fail(e)
        self._reader = None

    def _do_write(self):
        try:
            self._writer._value = self.sock.send(self._writer.data)
            self._writer._ok = True
            self.env.schedule(self._writer)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._wd.append(self.sock.fileno())
                return

            self._writer.fail(e)
        self._writer = None

    def _do_accept(self):
        try:
            self._reader._value = type(self)(self.env, self.sock.accept()[0])
            if not self._reader._value:
                self._reader._ok = False
                self._reader._value = socket_error(errno.ECONNRESET)
            else:
                self._reader._ok = True
            self.env.schedule(self._reader)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._rd.append(self.fileno())
                return

            self._reader.fail(e)
        self._reader = None


class SSLSocket(BaseSSLSocket):
    def _do_read(self):
        try:
            self._reader._value = self.sock.recv(self._reader.amount)
            if not self._reader._value:
                self._reader._ok = False
                self._reader._value = socket_error(errno.ECONNRESET)
            else:
                self._reader._ok = True
            self.env.schedule(self._reader)
        except ssl.SSLError as e:
            if e.errno == ssl.SSL_ERROR_WANT_READ:
                self.env._rd.append(self.fileno())
                return

            self._reader.fail(e)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._rd.append(self.sock.fileno())
                return

            self._reader.fail(e)
        self._reader = None

    def _do_write(self):
        try:
            self._writer._value = self.sock.send(self._writer.data)
            self._writer._ok = True
            self.env.schedule(self._writer)
        except ssl.SSLError as e:
            if e.errno == ssl.SSL_ERROR_WANT_WRITE:
                self.env._wd.append(self.fileno())
                return

            self._writer.fail(e)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._wd.append(self.sock.fileno())
                return

            self._writer.fail(e)
        self._writer = None

    def _do_accept(self):
        try:
            sock = type(self)(self.env, self.sock.accept()[0])
            sock.handshake(False)
            self._reader._value = sock
            self._reader._ok = True
            self.env.schedule(self._reader)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                self.env._rd.append(self.sock.fileno())
                return

            self._reader.fail(e)
        self._reader = None

    def _ssl_handshake_read(self):
        self.env._rd.append(self.fileno())
        self._ssl_event = self.env.event()

    def _ssl_handshake_write(self):
        self.env._wd.append(self.fileno())
        self._ssl_event = self.env.event()

    def close(self):
        # FIXME Abort ssl_events of the handshake.
        # FIXME This repeats BaseTCPSocket.close(). The socket might be closed
        # before the handshake has completed. In this case there might be
        # deferred _reader or _writer events, which did not add the socket to
        # read or write queues.
        try:
            fileno = self.fileno()

            del self.env.fds[fileno]
            # TODO Remove events.
            if self._reader is not None:
                self._reader.fail(socket_error(errno.EBADF))
                self._reader = None
                try:
                    self.env._rd.remove(fileno)
                except ValueError:
                    pass
            if self._writer is not None:
                self._writer.fail(socket_error(errno.EBADF))
                self._writer = None
                try:
                    self.env._wd.remove(fileno)
                except ValueError:
                    pass
            self.sock.close()
        except socket.error as e:
            if e.errno == errno.EBADF:
                return
            raise e
