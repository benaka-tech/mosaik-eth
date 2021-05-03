import os
import errno
import socket
import types

from simpy import core
from simpy.core import Environment, Infinity, BoundClass
from simpy.events import Event, Interrupt
from simpy.resources.store import Store
from simpy.io import platform
from simpy.io.network import BaseSocket, fail_func, socket_error
from simpy.io.base import Read, Write


class Environment(core.Environment):
    # FIXME Is it really required to subclass environment?

    def __init__(self, loopback_latency=lambda: 1):
        core.Environment.__init__(self)

        self.interfaces = [
                ('127.0.0.1', {'127.0.0.1': (self, loopback_latency)}),
        ]
        # FIXME self cannot be used to simulate a host. This would allow only
        # one host.

        self.ports = {}
        self._port_ofs = 0

    def _get_address(self, address):
        host, port = address
        if host != '0.0.0.0':
            for interface, routes in self.interfaces:
                if interface == host: break
            else:
                errcode = socket.EAI_NONAME
                raise socket.gaierror(errcode, os.strerror(errcode))

        # A port number of zero means auto-choose.
        if port == 0:
            # Search for a free port starting from the current port_ofs.
            for port in range(65535):
                port = 1 + (self._port_ofs + port) % (65535-1)
                if port not in self.ports:
                    break
            else:
                raise RuntimeError('No free port left')
            self._port_ofs = port
        elif port in self.ports:
            raise socket_error(errno.EADDRINUSE)

        return (host, port)

    def _register(self, sock):
        host, port = sock._address
        if port in self.ports:
            raise socket_error(errno.EADDRINUSE)

        self.ports[port] = sock

    def _unregister(self, sock):
        host, port = sock._address
        try:
            del self.ports[port]
        except KeyError:
            pass

    def _route(self, host):
        for interface, routes in self.interfaces:
            if host in routes: break
        else:
            errcode = socket.EAI_NONAME
            raise socket.gaierror(errcode, os.strerror(errcode))

        return interface, routes[host][0], routes[host][1]

    def _establish_connection(self, sock, address):
        host, port = address

        # Check if there's a route to the target address.
        interface, peer, latency = self._route(host)
        _, _, peer_latency = peer._route(interface)

        try:
            service = peer.ports[port]
        except KeyError:
            sock._incoming_error = errno.ECONNREFUSED
            sock._outgoing_error = errno.ECONNREFUSED
            return

        peer_sock = TCPSocket(self)

        sock_address = self._get_address((interface, 0))
        peer_address = peer._get_address((host, 0))

        sock._link(sock_address, peer_sock, address, latency)
        peer_sock._link(peer_address, sock, sock_address, peer_latency)

        self._register(sock)
        peer._register(peer_sock)

        # Enqueue the peer socket for acceptance.
        service.backlog.put(peer_sock)


class Frame(Event):
    def __init__(self, sock, data):
        Event.__init__(self, sock.env)
        self.sock = sock
        self.data = data


class TCPSocket(BaseSocket):
    def __init__(self, env, max_buffer_size=4096,
            max_segment_size=None):
        self.env = env
        self.max_buffer_size = max_buffer_size
        if max_segment_size:
            self.max_segment_size = max_segment_size
        else:
            self.max_segment_size = max_buffer_size

        self.incoming = None
        self.outgoing = None
        self.backlog = None

        self._address = ('0.0.0.0', 0)
        self._peer = None
        self._peer_address = None
        self._latency = None

        self._incoming_error = errno.ENOTCONN
        self._incoming_avail = None
        self._incoming_reader = None
        self._outgoing_error = errno.EPIPE
        self._outgoing_avail = None
        self._outgoing_writer = None

        self._frame_transmission = None
        self._reader = None
        self._writer = None

        self.read = types.MethodType(Read, self)
        self.write = types.MethodType(Write, self)

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

    def _link(self, address, peer, peer_address, latency):
        self._peer = peer
        self._address = address
        self._peer_address = peer_address
        self._latency = latency
        self._incoming_reader = self.env.process(self._read_incoming())
        self._outgoing_writer = self.env.process(self._write_outgoing())
        self._incoming_error = None
        self._outgoing_error = None
        self.incoming = b''
        self.outgoing = b''

    @property
    def address(self):
        if self._address is None:
            raise socket_error(errno.EBADF)
        return self._address

    @property
    def peer_address(self):
        if self._address is None:
            raise socket_error(errno.EBADF)
        if self._peer_address is None:
            raise socket_error(errno.ENOTCONN)

        return self._peer_address

    def bind(self, address):
        if self._address is None:
            raise socket_error(errno.EBADF)
        if self._incoming_error != errno.ENOTCONN:
            raise socket_error(platform.invalid_argument)
        self._address = self.env._get_address(address)

    def listen(self, backlog):
        if self._address is None:
            raise socket_error(errno.EBADF)
        if self._incoming_error != errno.ENOTCONN:
            raise socket_error(platform.invalid_argument)
        self.backlog = Store(self.env, capacity=backlog)
        self.env._register(self)

    def accept(self):
        if self.backlog is None:
            raise socket_error(platform.invalid_argument)
        return self.backlog.get()

    def connect(self, address):
        if self._address is None:
            raise socket_error(errno.EBADF)
        if self._peer is not None:
            # Already connected, do nothing.
            return
        if self.backlog is not None:
            raise socket_error(errno.EISCONN)
        self.env._establish_connection(self, address)

    def _try_read(self):
        if self._incoming_error is not None:
            self._reader.fail(socket_error(self._incoming_error))
            self._reader = None
            return

        if not self.incoming:
            return

        data = self.incoming[:self._reader.amount]
        self.incoming = self.incoming[self._reader.amount:]
        self._reader.succeed(data)
        self._reader = None

        if self._incoming_avail:
            self._incoming_avail.succeed()
            self._incoming_avail = None

    def _try_write(self):
        if self._outgoing_error is not None:
            self._writer.fail(socket_error(self._outgoing_error))
            self._writer = None
            return

        available = self.max_buffer_size - len(self.outgoing)
        if not available:
            return

        self.outgoing += self._writer.data[:available]
        self._writer.succeed(min(len(self._writer.data), available))
        self._writer = None

        if self._outgoing_avail:
            # Notify the reader process about the new data.
            self._outgoing_avail.succeed()
            self._outgoing_avail = None

    def _read_incoming(self):
        """Pushes remote data frames into :attr:`incoming`."""
        self._frame_transmission = Event(self.env)

        while True:
            if self._reader:
                self._try_read()

            if self._incoming_error is not None:
                break

            # Wait until there is room for incoming data.
            if len(self.incoming) >= self.max_buffer_size:
                self._incoming_avail = Event(self.env)
                yield self._incoming_avail
                continue

            frame = yield self._frame_transmission
            self._frame_transmission = Event(self.env)

            if frame is None:
                # A local close will end the frame transmission with None.
                continue

            if frame.data:
                read = min(self.max_buffer_size - len(self.incoming),
                        len(frame.data))
                self.incoming += frame.data[:read]
                # Simulate transmission of the frame acknowledgement.
                yield self.env.timeout(self._latency())
                frame.succeed(read)
            else:
                # An empty frame has been received, this means the remote side
                # has closed the connection.
                self._incoming_error = errno.ECONNRESET
                self.env._unregister(self)
                frame.succeed()

        self._frame_transmission = None

    def _write_outgoing(self):
        """Pulls data from :attr:`outgoing` and pushes it to the peer."""
        while True:
            if len(self.outgoing) == 0:
                if self._outgoing_error is None:
                    self._outgoing_avail = Event(self.env)
                    yield self._outgoing_avail

            data = self.outgoing[:self.max_segment_size]
            frame = Frame(self, data)
            yield self.env.timeout(self._latency())

            if self._peer._frame_transmission:
                # Inform peer of the frame and wait for the acknowledgement.
                self._peer._frame_transmission.succeed(frame)
                sent = yield frame
            else:
                # Peer has closed the connection
                sent = 0
                self._outgoing_error = errno.EPIPE

            if not frame.data:
                # The close frame has been sent.
                break

            self.outgoing = self.outgoing[sent:]

            if self._writer:
                self._try_write()

    def close(self):
        """Closes the socket, all further operations will raise ``EBADF``."""
        if self._address is None:
            return

        self._incoming_error = errno.EBADF
        self._outgoing_error = errno.EBADF
        if self._incoming_avail is not None:
            self._incoming_avail.succeed()
        if self._outgoing_avail is not None:
            self._outgoing_avail.succeed()
        if self._frame_transmission:
            # Wake the reader if it is currently waiting for a frame.
            if not self._frame_transmission.triggered:
                self._frame_transmission.succeed()
                self._frame_transmission = None

        if self.backlog is not None:
            for accepter in self.backlog.get_queue:
                if not accepter.triggered:
                    accepter.fail(socket_error(errno.EBADF))

        self.env._unregister(self)

        self._address = None
        self._peer_address = None
