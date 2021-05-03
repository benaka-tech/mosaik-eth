from __future__ import absolute_import

import sys
import socket
import errno
from socket import error as SocketError

import pytest

from simpy._compat import PY2
from simpy.io import platform

if PY2:
    from simpy.io._compat import ConnectionError


# TODO Connect to the address of a normal socket (e.g. already connected).
# TODO Ports are not yet freed in virtual.
# TODO Close of all network connections.
# TODO Reconnect a client socket.

#def test_backlog(env, socket_type):
#    TODO This is strange. Although the socket only specifies a backlog of 10
#    more than 10 connection happen. There is no error on the remote side.
#    Don't know why yet.
#
#    service = network.socket_type(env)
#    service.bind(('127.0.0.1', 0))
#    service.listen(10)
#
#    socks = [network.connect(service.address) for i in range(100)]
#    for sock in socks:
#        print(sock)
#        yield sock.write(b'hello')


def test_timeout(env):
    time = env.now
    yield env.timeout(0.01)
    assert env.now - time >= 0.01


def test_connection(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            conn = yield service.accept()
            yield conn.write(b'hello')

    def client(env, address):
        conn = socket_type.connection(env, address)
        msg = yield conn.read(1024)
        env.exit(msg)

    env.process(server(env, service))
    result = yield env.process(client(env, service.address))
    assert result == b'hello'


def test_connection_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    yield sock.write(b'hello')
    data = yield service.read(1024)
    assert data == b'hello'

    yield service.write(b'hi there')
    service.close()
    data = yield sock.read(1024)
    assert data == b'hi there'


def test_close_with_pending_read_and_write(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    # FIXME Establish connection. Remove once connect returns an event.
    yield sock.write(b'init') & service.read(4)

    read_ev = sock.read(1024)
    service.close()

    try:
        yield read_ev
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno == errno.ECONNRESET

    data = b'spam' * 1000
    try:
        while True:
            yield sock.write(data)

        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


@pytest.mark.skipif(sys.platform == 'win32' or sys.version_info < (3,),
        reason='listen() fails on unbound sockets')
def test_connect_after_close(env, socket_type):
    server1 = socket_type.server(env, ('127.0.0.1', 0))
    server2 = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server1.address)
    service1 = yield server1.accept()
    sock.close()

    try:
        sock.connect(server2.address)
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)
    except ValueError as e:
        # SSL complains with a ValueError.
        assert e.args[0] == 'attempt to connect already-connected SSLSocket!'


def test_address_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()

    try:
        sock.address
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)


def test_read_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()

    read_ev = sock.read(10)
    try:
        yield read_ev
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)


def test_write_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()

    write_ev = sock.write(b'hi')
    try:
        yield write_ev
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)


def test_bind_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()

    try:
        sock.bind(('127.0.0.1', 0))
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)


def test_listen_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()

    try:
        sock.listen(5)
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno in (socket.EBADF, errno.ENOTSOCK)


def test_close_after_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    sock.close()
    sock.close()


def test_read_after_peer_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    service.close()

    # Read attempts do not fail immediately after the peer has closed his
    # connection endpoint.
    read_ev = sock.read(10)
    try:
        yield read_ev
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    # Following read attempts also not fail immediately.
    read_ev = sock.read(10)
    try:
        yield read_ev
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_write_after_peer_close(env, socket_type):
    """Because of network buffering write attempts on a socket which has just
    be remotely closed will succeed. All consequent write attempts will
    fail."""
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    yield sock.write(b'init')
    assert (yield service.read(4)) == b'init'
    service.close()

    try:
        # Implementation detail: async.TCPSocket and async.SSLSocket will fail
        # already after 2 write attempts. However, this is only the case for
        # inprocess connections. More write attempts will succeed on a
        # connection used by two processes. Virtual emulates the latter
        # behavior and needs more write attempts.
        data = b'spam' * 1024
        for i in range(3):
            sent = yield sock.write(data)
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    try:
        yield sock.write(b'hi')
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_close_after_peer_close(env, socket_type):
    """Concurrent close calls are legal."""
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server.address)
    service = yield server.accept()
    service.close()
    sock.close()


def test_multiple_connects(env, socket_type):
    """All but the initial connect call seem to be ignored."""
    server1 = socket_type.server(env, ('127.0.0.1', 0))
    server2 = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type(env)

    sock.connect(server1.address)
    sock.connect(server2.address)

    service1 = yield server1.accept()
    accept_ev = server2.accept()
    yield env.timeout(0.1)
    assert not accept_ev.triggered

    sock.write(b'hi')
    data = yield service1.read(2)
    assert data == b'hi'


def test_uninitialized_read(env, socket_type):
    sock = socket_type(env)
    try:
        yield sock.read(1024)
        pytest.fail('Expected an exception')
    except socket.error as e:
        assert e.errno == errno.ENOTCONN


def test_unconnected_write(env, socket_type):
    """Calling write() on an unconnected socket will result in an EPIPE
    error."""
    sock = socket_type(env)
    try:
        yield sock.write(b'hello')
        pytest.fail('Expected an exception')
    except ConnectionError:
        pass
    except socket.error as e:
        # ENOTCONN happens on windows.
        assert e.errno in (errno.EPIPE, errno.ENOTCONN)


def test_accept_without_bind(env, socket_type):
    service = socket_type(env)
    try:
        yield service.accept()
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno == platform.invalid_argument


def test_accept_without_listen(env, socket_type):
    service = socket_type(env)
    service.bind(('127.0.0.1', 0))
    try:
        yield service.accept()
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno == platform.invalid_argument


@pytest.mark.xfail()
def test_connect_on_accepting_socket_type(env, socket_type):
    # FIXME See test_listen_after_connect() for an explanation.
    service = socket_type.server(env, ('127.0.0.1', 0))
    try:
        service.connect(service.address)
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (errno.EINVAL, errno.WSAEINVAL)


@pytest.mark.xfail()
def test_read_on_accepting_socket_type(env, socket_type):
    # FIXME See test_listen_after_connect() for an explanation.
    service = socket_type.server(env, ('127.0.0.1', 0))
    try:
        service.read(10)
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (errno.EINVAL, errno.WSAEINVAL)


@pytest.mark.xfail()
def test_write_on_accepting_socket_type(env, socket_type):
    # FIXME See test_listen_after_connect() for an explanation.
    service = socket_type.server(env, ('127.0.0.1', 0))
    try:
        service.write(b'hello')
        pytest.fail('Expected a socket error')
    except ConnectionError:
        pass


@pytest.mark.skipif(sys.platform == 'win32',
        reason='listen() fails on unbound sockets')
def test_listen_without_bind(env, socket_type):
    service = socket_type(env)
    service.listen(5)
    assert service.address[0] == '0.0.0.0'


def test_bind_on_invalid_host(env, socket_type):
    service = socket_type(env)
    try:
        service.bind(('this_host_does_probably_not_exist', 0))
        pytest.fail('Expected a socket error')
    except socket.gaierror as e:
        # Windows quirk: Windows fails with errorcode 11004 in this case.
        assert e.errno in (socket.EAI_NONAME, 11004)


def test_multiple_binds(env, socket_type):
    """Multiple binds on the same address are allowed."""
    service_a = socket_type(env)
    service_a.bind(('127.0.0.1', 0))

    service_b = socket_type(env)
    service_b.bind(service_a.address)
    assert service_b.address == service_a.address


@pytest.mark.xfail(sys.platform == 'win32',
    reason='windows does not seem to raise an error')
def test_bind_on_used_port(env, socket_type):
    """Listen will claim the address and prevent additional binds."""
    service_a = socket_type.server(env, ('127.0.0.1', 0))

    service_b = socket_type(env)
    try:
        service_b.bind(service_a.address)
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno == errno.EADDRINUSE


def test_bind_on_reused_port(env, socket_type):
    """Ports can be reused immediately."""
    sock = socket_type.server(env, ('127.0.0.1', 0))
    address = sock.address
    sock.close()

    sock = socket_type(env)
    sock.bind(address)
    sock.listen(5)


def test_bind_after_connect(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, service.address)

    try:
        sock.bind(('127.0.0.1', 0))
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno == platform.invalid_argument


def test_listen_after_connect(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, service.address)
    # FIXME At least on linux, it is possible to call listen() on a socket on
    # which connect() has already been called. It is only invalid to call
    # listen() after the connection has been established. I should probably
    # remember the mode in which the socket has been set and fail immediately.
    # This would also obsolete the following accept() call.
    yield service.accept()

    try:
        sock.listen(5)
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (platform.invalid_argument, errno.EISCONN)


def test_unconnected_peer_address(env, socket_type):
    pass


def test_bind_reuse_after_close(env, socket_type):
    sock = socket_type.server(env, ('127.0.0.1', 0))
    sock.close()

    try:
        sock.bind(('127.0.0.1', 0))
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)


def test_connect_after_bind(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            conn = yield service.accept()
            yield conn.read(10)

    env.process(server(env, service))

    sock = socket_type(env)
    sock.bind(('127.0.0.1', 0))
    sock.connect(service.address)
    written = yield sock.write(b'hello')
    assert written == 5


def test_address(env, socket_type):
    sock = socket_type(env)
    assert sock.address == ('0.0.0.0', 0)

    sock.bind(('127.0.0.1', 0))
    assert sock.address[0] == '127.0.0.1'

    # A bad file descriptor error is raised on closed sockets.
    sock.close()
    try:
        sock.address
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)


def test_address_after_connect(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    assert sock.address[0] != '0.0.0.0'


def test_address_after_established_connection(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()

    assert sock.address[0] != '0.0.0.0'


def test_peer_address(env, socket_type):
    """``peer_address`` is only available if the socket is connected. Otherwise
    a ENOTCONN socket error is raised."""
    sock = socket_type(env)
    try:
        sock.peer_address
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno == errno.ENOTCONN

    service = socket_type.server(env, ('127.0.0.1', 0))

    sock.connect(service.address)
    assert sock.peer_address == service.address

    # A bad file descriptor error is raised on closed sockets.
    sock.close()
    try:
        sock.peer_address
        pytest.fail('Expected a socket error')
    except socket.error as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)


def test_all_address(env, socket_type):
    """The all address 0.0.0.0 allows to bind a port on all interfaces of a
    host."""
    service = socket_type.server(env, ('0.0.0.0', 0))

    sock = socket_type.connection(env, ('127.0.0.1', service.address[1]))
    assert service.address[0] == '0.0.0.0'
    assert sock.peer_address == ('127.0.0.1', service.address[1])


@pytest.mark.skipif(sys.platform == 'win32',
        reason='writes to unconnected sockets do not fail immediately on '
            'windows.')
def test_refused_connection_write(env, socket_type):
    """An attempt to write to a non-existing socket will result in a connection
    error."""
    sock = socket_type(env)
    try:
        sock.connect(('127.0.0.1', 999))
    except SocketError:
        pass

    try:
        yield sock.write(b'asdf')
        pytest.fail('Expected a socket error')
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    try:
        yield sock.write(b'asdf')
        pytest.fail('Expected a socket error')
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


@pytest.mark.skipif(sys.platform == 'win32',
        reason='writes to unconnected sockets do not fail immediately on '
            'windows.')
def test_refused_connection_read(env, socket_type):
    """An attempt to read from a non-existing socket will result in a
    connection error."""
    sock = socket_type(env)
    try:
        sock.connect(('127.0.0.1', 999))
    except SocketError:
        pass

    try:
        yield sock.read(1024)
        pytest.fail('Expected a socket error')
    except SocketError as e:
        pass

    try:
        yield sock.read(1024)
        pytest.fail('Expected a socket error')
    except SocketError as e:
        pass


@pytest.mark.timeout(5)
def test_no_route(env, socket_type):
    try:
        sock = socket_type.connection(env, ('a-host-that-does-not-exist', 80))
        pytest.fail('Expected a socket error')
    except socket.gaierror as e:
        # Windows quirk: Windows fails with errorcode 11004 in this case.
        assert e.errno in (socket.EAI_NONAME, 11004)

    yield env.exit()


def test_close_during_accept(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    accept_ev = server.accept()

    server.close()
    try:
        yield accept_ev
        assert False, 'Expected an exception'
    except socket.error as e:
        assert e.errno == errno.EBADF


def test_close_during_read(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    read_ev = sock.read(1024)
    sock.close()
    try:
        yield read_ev
        assert False, 'Expected a socket error.'
    except socket.error as e:
        assert e.errno == errno.EBADF


def test_peer_close_during_read_without_pending_data(env, socket_type):
    # Connect to the server and try to read two messages from the server. The
    # first one will be successfully transmitted. But the second attempt will
    # fail because the server closed the connection meanwhile.
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    service.write(b'hello')
    msg = yield sock.read(1024)
    assert msg == b'hello'
    service.close()
    try:
        yield sock.read(1024)
        assert False, 'Expected a socket error.'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    try:
        yield sock.read(1024)
        assert False, 'Expected a socket error.'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_peer_close_during_read_with_pending_data(env, socket_type):
    # Identical to test_close_during_read. Before the service socket is closed
    # the client sock sends some data. This causes an ECONNRESET error.
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    yield service.write(b'hello')
    msg = yield sock.read(1024)
    assert msg == b'hello'
    yield sock.write(b'spam')
    service.close()

    try:
        yield sock.read(1024)
        assert False, 'Expected a socket error.'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_close_during_write_without_pending_data(env, socket_type):
    # FIXME Why is EPIPE raised? Shouldn't this cause an ECONNRESET?
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    yield sock.write(b'hello')
    msg = yield service.read(1024)
    assert msg == b'hello'

    service.close()
    try:
        for i in range(2000):
            yield sock.write(b'spam')
        pytest.fail('Expected a socket error')
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


@pytest.mark.skipif(sys.platform == 'win32',
        reason='windows insanely buffers all outgoing data')
def test_buffer_overflow(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            yield service.accept()

    env.process(server(env, service))

    sock = socket_type.connection(env, service.address)
    # The maximum amount of send buffers are limited. That's why a large packet
    # can't be transmitted in one go.
    data = b'spam' * 1000000
    sent = yield sock.write(data)

    assert len(data) > sent


def test_concurrent_close(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    yield sock.write(b'hello')
    msg = yield service.read(1024)
    assert msg == b'hello'

    service.close()
    sock.close()

    yield env.timeout(0.01)


def test_concurrent_read(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            yield service.accept()

    env.process(server(env, service))

    conn = socket_type.connection(env, service.address)
    conn.read(1024)
    try:
        yield conn.read(1024)
        assert False, 'Expected an exception'
    except RuntimeError as e:
        assert e.args[0] == 'Already reading'


def test_concurrent_write(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            yield service.accept()

    env.process(server(env, service))

    conn = socket_type.connection(env, service.address)
    try:
        for i in range(1000):
            conn.write(b'spam' * 1000000)
        pytest.fail('Expected an error')
    except RuntimeError as e:
        assert e.args[0] == 'Already writing'


def test_close_during_write_with_pending_data(env, socket_type):
    """This test does only seem to work in in-process communications."""
    server = socket_type.server(env, ('127.0.0.1', 0))
    sock = socket_type.connection(env, server.address)
    service = yield server.accept()
    yield sock.write(b'hello')
    msg = yield service.read(1024)
    assert msg == b'hello'

    # This packet is transmitted into the buffer of the peer.
    yield sock.write(b'spam')
    # The peer closes the socket before it has read its data. This causes an
    # EPIPE error to be raised on the next write attempt.
    service.close()
    try:
        for i in range(2000):
            yield sock.write(b'spam')
        pytest.fail('Expected a socket error')
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

