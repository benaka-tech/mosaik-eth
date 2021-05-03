import sys
from time import time
from itertools import count
from heapq import heappush, heappop
import types
import socket
import ssl
import _ssl
import errno
from socket import error as SocketError

from simpy.core import (BaseEnvironment, BoundClass, Event, Process, Timeout,
        AllOf, AnyOf, NORMAL)
from simpy._compat import PY2
from simpy.io.network import BaseSocket, socket_error
from simpy.io.platform import blocking_io_errors, invalid_argument


class BaseIOEnvironment(BaseEnvironment):
    def __init__(self, fds=None):
        if fds is None:
            fds = {}

        self._queue = []
        """A list with all currently scheduled events."""
        self._eid = count()
        self._active_proc = None

        self.fds = fds

        BoundClass.bind_early(self)

    # FIXME Move this into the baseenvironment?
    @property
    def active_process(self):
        """Property that returns the currently active process."""
        return self._active_proc

    process = BoundClass(Process)
    timeout = BoundClass(Timeout)
    event = BoundClass(Event)
    all_of = BoundClass(AllOf)
    any_of = BoundClass(AnyOf)
    suspend = event
    start = process

    def exit(self, value=None):
        """Convenience function provided for Python versions prior to 3.3. Stop
        the current process, optionally providing a ``value``.

        .. note::

            From Python 3.3, you can use ``return value`` instead."""
        raise StopIteration(value)

    @property
    def now(self):
        return time()

    def schedule(self, event, priority=NORMAL, delay=0):
        heappush(self._queue, (time() + delay, priority, next(self._eid),
            event))

    def _iowait(self, timeout):
        raise NotImplementedError(self)

    def step(self):
        """Executes the next event. TODO Improve."""
        timeout = self._queue[0][0] - time() if self._queue else None

        if timeout is None or timeout > 0:
            self._iowait(timeout)

        event = heappop(self._queue)[3]

        for callback in event.callbacks:
            callback(event)

        # Mark event as processed.
        event.callbacks = None

        if not event.ok:
            if not hasattr(event, 'defused'):
                # The event has not been defused by a callback.
                raise event._value

    def close(self):
        for fileno, socket in list(self.fds.items()):
            try:
                socket.close()
            except OSError as e:
                if e.errno != errno.EBADF:
                    raise


class Read(Event):
    def __init__(self, sock, amount):
        if sock._reader:
            raise RuntimeError('Already reading')
        sock._reader = self

        Event.__init__(self, sock.env)
        self.sock = sock
        self.amount = amount

        sock._try_read()


class Accept(Event):
    def __init__(self, sock):
        if sock._reader:
            raise RuntimeError('Already accepting')
        sock._reader = self

        Event.__init__(self, sock.env)
        self.sock = sock
        # FIXME Accept should also use _try_read because _do_accept is
        # considered to be a socket implementation detail. However this fails
        # if accept is called on an unbound socket.
        sock._do_accept()


class Write(Event):
    def __init__(self, sock, data):
        if sock._writer:
            raise RuntimeError('Already writing')
        sock._writer = self

        Event.__init__(self, sock.env)
        self.sock = sock
        self.data = data

        sock._try_write()


class BaseTCPSocket(BaseSocket):
    def __init__(self, env, sock=None):
        self.env = env

        if sock is None:
            sock = socket.socket()
        self.sock = sock

        self.sock.setblocking(0)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.env.fds[self.fileno()] = self

        self._reader = None
        self._writer = None

        self._try_read = self._do_read
        self._try_write = self._do_write
        self._ready_read = self._do_read
        self._ready_write = self._do_write

        self.read = types.MethodType(Read, self)
        self.write = types.MethodType(Write, self)
        self.accept = types.MethodType(Accept, self)

    def _do_read(self):
        raise NotImplementedError(self)

    def _do_write(self):
        raise NotImplementedError(self)

    def _do_accept(self):
        raise NotImplementedError(self)

    @classmethod
    def server(cls, env, address, backlog=5):
        socket = cls(env)
        socket.bind(address)
        socket.listen(backlog)
        return socket

    @classmethod
    def connection(cls, env, address):
        socket = cls(env)
        socket.connect(address)
        return socket

    @property
    def address(self):
        try:
            return self.sock.getsockname()
        except SocketError as e:
            # Windows quirk: Return invalid address if the socket is not yet
            # connected as is done by linux.
            if sys.platform == 'win32':
                if e.errno == invalid_argument:
                    return ('0.0.0.0', 0)

            raise e

    @property
    def peer_address(self):
        return self.sock.getpeername()

    def fileno(self):
        fileno = self.sock.fileno()
        if fileno < 0:
            raise socket_error(errno.EBADF)
        return fileno

    def connect(self, address):
        # TODO Does the error happen on concurrent connect calls? If so, this
        # wrapping is not needed.
        try:
            self.sock.setblocking(1)
            self.sock.connect(address)
        except SocketError as e:
            # Windows quirk: Ignore blocking IO errors on connect.
            if e.errno in blocking_io_errors:
                return
            # Windows quirk: Ignore connects on already connected sockets as
            # linux does.
            if e.errno == errno.EISCONN:
                return

            raise e
        finally:
            self.sock.setblocking(0)

    def bind(self, address):
        self.sock.bind(address)
        self._try_read = self._do_accept
        self._ready_read = self._do_accept

    def listen(self, backlog):
        self.sock.listen(backlog)

    def close(self):
        # TODO Figure out if this behaviour is really usefull. Might require
        # the addition of methods that check for the sockets state.
        try:
            fileno = self.fileno()

            del self.env.fds[fileno]
            # TODO Remove events.
            if self._reader is not None:
                self._reader.fail(socket_error(errno.EBADF))
                self._reader = None
                self.env._rd.remove(fileno)
            if self._writer is not None:
                self._writer.fail(socket_error(errno.EBADF))
                self._writer = None
                self.env._wd.remove(fileno)
            self.sock.close()
        except SocketError as e:
            if e.errno == errno.EBADF:
                return
            raise e


class BaseSSLSocket(BaseTCPSocket):
    def __init__(self, env, sock=None, **kwargs):
        if sock is None:
            # Non-blocking sockets are not allowed to block for the handshake.
            kwargs['do_handshake_on_connect'] = None
            sock = ssl.wrap_socket(socket.socket(), **kwargs)

        BaseTCPSocket.__init__(self, env, sock)

        self._ssl_event = None

    def connect(self, address):
        try:
            self.sock.setblocking(1)
            self.sock.connect(address)
        except SocketError as e:
            if e.errno in blocking_io_errors:
                # Windows quirk: Ignore blocking IO errors on connect.
                pass
            elif e.errno == errno.EISCONN:
                # Windows quirk: Ignore connects on already connected sockets as
                # linux does.
                pass
            else:
                raise e
        finally:
            self.sock.setblocking(0)

        self.handshake()

    def handshake(self, initiate=True):
        self._try_read = self._defer_read
        self._try_write = self._defer_write
        self._ready_read = self._do_handshake
        self._ready_write = self._do_handshake

        self._ssl_event = self.env.event()
        self._do_handshake()

    def _defer_read(self):
        pass

    def _defer_write(self):
        pass

    def _ssl_handshake_read(self):
        raise NotImplementedError(self)

    def _ssl_handshake_write(self):
        raise NotImplementedError(self)

    def _do_handshake(self):
        """Performs the SSL handshake."""
        if self.sock._sslobj is None:
            # FIXME This wrapping is ugly as it is using SSL internal stuff. It
            # is really necessary?
            if PY2:
                self.sock._sslobj = _ssl.sslwrap(self.sock._sock, False,
                        self.sock.keyfile, self.sock.certfile,
                        self.sock.cert_reqs, self.sock.ssl_version,
                        self.sock.ca_certs)
            else:
                self.sock._sslobj = self.sock.context._wrap_socket(self.sock,
                        False, self.sock.server_hostname)

        if self._ssl_event is not None:
            self._ssl_event.succeed()
            self._ssl_event = None

        try:
            self.sock.do_handshake()
        except ssl.SSLError as err:
            if err.args[0] == ssl.SSL_ERROR_WANT_READ:
                self._ssl_handshake_read()
                return
            elif err.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                self._ssl_handshake_write()
                return
            else:
                raise
        except SocketError as e:
            pass

        # Handshake has completed. Resume normal operation.
        self._ready_read = self._do_read
        self._ready_write = self._do_write
        self._try_read = self._do_read
        self._try_write = self._do_write

        if self._reader is not None:
            self._try_read()
        if self._writer is not None:
            self._try_write()
