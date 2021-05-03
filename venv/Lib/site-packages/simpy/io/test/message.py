from __future__ import absolute_import

import sys, errno
from socket import error as SocketError

from simpy._compat import PY2
from simpy.io import platform
from simpy.io.codec import JSON
from simpy.io.message import Message, RemoteException, MessageOverflowError


if PY2:
    from simpy.io._compat import ConnectionError, ConnectionResetError


# TODO Test requests with invalid ids.


def echo_server(env, service, name, **msg_kwargs):
    def handler(message):
        while True:
            request = yield message.recv()
            request.succeed(name + ': ' + request.content)

    while True:
        socket = yield service.accept()
        message = Message(env, socket, **msg_kwargs)
        env.process(handler(message))


def test_message(env, protocol):
    service = protocol.server(('127.0.0.1', 0))

    env.process(echo_server(env, service, 'server', codec=JSON()))
    client = Message(env, protocol.connection(service.address), JSON())

    result = yield client.send('hi')
    assert result == 'server: hi'
    result = yield client.send('bye')
    assert result == 'server: bye'


def test_fail_message(env, protocol):
    service = protocol.server(('127.0.0.1', 0))

    def failing_server(env, service):
        conn = yield service.accept()
        message = Message(env, conn, JSON())
        request = yield message.recv()
        try:
            raise RuntimeError('I am failing')
        except BaseException as e:
            if PY2:
                # Python < 3 does not support exception chaining. Attach
                # __traceback__ by hand.
                e.__traceback__ = sys.exc_info()[2]
            request.fail(e)

    env.process(failing_server(env, service))
    client = Message(env, protocol.connection(service.address), JSON())

    try:
        yield client.send('hi')
        assert False, 'Expected an exception'
    except RemoteException as e:
        assert 'raise RuntimeError(\'I am failing\')' in e.remote_traceback


def test_request_trigger_after_close(env, protocol):
    server = protocol.server(('127.0.0.1', 0))

    peer_a = Message(env, protocol.connection(server.address), JSON())
    peer_b = Message(env, (yield server.accept()), JSON())

    requests = []
    for i in range(2):
        peer_a.send('foo')
        requests.append((yield peer_b.recv()))

    peer_b.close()

    # Wait until the transmission processes are terminated.
    try:
        yield peer_b.send('foo')
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF

    # Now trigger both requests. Failures are ignored.
    requests[0].succeed()
    try:
        raise RuntimeError('I will be ignored')
    except RuntimeError as e:
        requests[1].fail(e)


def test_incoming_message_limit(env, protocol):
    server = protocol.server(('127.0.0.1', 0))

    limit = 5
    peer_a = Message(env, protocol.connection(server.address), JSON())
    peer_b = Message(env, (yield server.accept()), JSON(), limit)

    for i in range(limit):
        peer_a.send('foo')

    try:
        yield peer_a.send('spam')
    except ConnectionResetError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    assert peer_b.reader.value.errno == errno.EOVERFLOW


def test_incoming_message_limit(env, protocol):
    server = protocol.server(('127.0.0.1', 0))

    limit = 5
    peer_a = Message(env, protocol.connection(server.address), JSON(), limit)
    peer_b = Message(env, (yield server.accept()), JSON())

    for i in range(limit):
        peer_a.send('foo')

    try:
        peer_a.send('spam')
    except MessageOverflowError:
        pass


def test_concurrent_send(env, protocol):
    server = protocol.server(('127.0.0.1', 0))

    peer_a = Message(env, protocol.connection(server.address), JSON())
    peer_b = Message(env, (yield server.accept()), JSON())

    requests = [peer_a.send(msg) for msg in ('hi', 'sup?', 'bye')]

    for i in range(3):
        in_request = yield peer_b.recv()
        in_request.succeed('echo: ' + in_request.content)

    results = []
    for request in requests:
        results.append((yield request))

    assert results == ['echo: hi', 'echo: sup?', 'echo: bye']


def test_concurrent_send_reversed(env, protocol):
    """Responses may be received in any order."""
    server = protocol.server(('127.0.0.1', 0))

    peer_a = Message(env, protocol.connection(server.address), JSON())
    peer_b = Message(env, (yield server.accept()), JSON())

    requests = [peer_a.send(msg) for msg in ('hi', 'sup?', 'bye')]

    for i in range(3):
        in_request = yield peer_b.recv()
        in_request.succeed('echo: ' + in_request.content)

    results = []
    for request in reversed(requests):
        results.append((yield request))

    assert results == ['echo: bye', 'echo: sup?', 'echo: hi']


def test_concurrent_recv(env, protocol):
    """Concurrent calls to receive are not allowed."""
    server = protocol.server(('127.0.0.1', 0))

    peer_a = Message(env, protocol.connection(server.address), JSON())
    peer_b = Message(env, (yield server.accept()), JSON())

    peer_b.recv()
    try:
        peer_b.recv()
    except RuntimeError as e:
        assert e.args[0] == 'Concurrent receive attempt'


def test_server_close(env, protocol):
    """Any request send is going to be triggered with an error if the
    connection is closed."""
    # FIXME This test is fragile. The request failure depends on whichever IO
    # event is handled first. If the requests are small enough, all data will
    # be successfully written by virtual, causing the reader to fail first.
    # Real network backends fail earlier, presumably because each write call
    # takes some time and allows the close notification to be processed.

    server = protocol.server(('127.0.0.1', 0))
    client_msg = Message(env, protocol.connection(server.address), JSON())
    server_msg = Message(env, (yield server.accept()), JSON())

    requests = []
    for i in range(10):
        request = client_msg.send('hi' * 1024)
        request.defused = True
        requests.append(request)

    server_msg.close()

    for request in requests:
        try:
            yield request
            assert False, 'Expected an exception'
        except ConnectionError:
            pass
        except SocketError as e:
            assert PY2 and e.errno in platform.connection_errors


def test_close_process_termination_recv_send(env, protocol):
    """Reader and writer processes are not terminated immediately if the
    connection is closed. Only by attempting to read from or write to the
    connection the processes will be terminated."""
    server = protocol.server(('127.0.0.1', 0))
    client_msg = Message(env, protocol.connection(server.address), JSON())
    server_msg = Message(env, (yield server.accept()), JSON())

    cli_request = client_msg.send('hi')
    srv_request = yield server_msg.recv()
    srv_request.succeed('hi there')
    assert srv_request.content == 'hi'
    assert (yield cli_request) == 'hi there'

    client_msg.close()
    assert not client_msg.reader.triggered
    assert not client_msg.writer.triggered
    assert not server_msg.reader.triggered
    assert not server_msg.writer.triggered

    try:
        yield client_msg.recv()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF
        assert client_msg.reader.value.errno == errno.EBADF
        assert client_msg.writer.value.errno == errno.EBADF

    try:
        yield client_msg.send('hi')
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF

    try:
        yield server_msg.recv()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    assert server_msg.reader.value.errno in platform.connection_errors
    assert server_msg.writer.value.errno in platform.connection_errors

    try:
        yield server_msg.send('hi')
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_close_process_termination_send_recv(env, protocol):
    """Reader and writer processes are not terminated immediately if the
    connection is closed. Only by attempting to read from or write to the
    connection the processes will be terminated."""
    server = protocol.server(('127.0.0.1', 0))
    client_msg = Message(env, protocol.connection(server.address), JSON())
    server_msg = Message(env, (yield server.accept()), JSON())

    cli_request = client_msg.send('hi')
    srv_request = yield server_msg.recv()
    srv_request.succeed('hi there')
    assert srv_request.content == 'hi'
    assert (yield cli_request) == 'hi there'

    client_msg.close()
    assert not client_msg.reader.triggered
    assert not client_msg.writer.triggered
    assert not server_msg.reader.triggered
    assert not server_msg.writer.triggered

    try:
        yield server_msg.send('hi')
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    assert server_msg.writer.value.errno in platform.connection_errors
    assert server_msg.reader.value.errno in platform.connection_errors

    try:
        yield server_msg.recv()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    try:
        yield client_msg.send('hi')
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF
        assert client_msg.writer.value.errno == errno.EBADF
        assert client_msg.reader.value.errno == errno.EBADF

    try:
        yield client_msg.recv()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF


def test_client_close(env, protocol):
    """If responses cannot be delivered because the client has closed the
    connection."""
    server = protocol.server(('127.0.0.1', 0))
    client_msg = Message(env, protocol.connection(server.address), JSON())
    server_msg = Message(env, (yield server.accept()), JSON())

    requests = [client_msg.send('hi') for i in range(10)]

    srv_requests = []
    for i in range(len(requests)):
        srv_requests.append((yield server_msg.recv()))

    client_msg.close()

    for request in srv_requests:
        request.succeed('hello')

    for request in requests:
        try:
            yield request
            assert False, 'Expected an exception'
        except SocketError as e:
            assert e.errno == errno.EBADF


def test_unconnected_send(env, protocol):
    """Calling send() on an unconnected socket will fail."""
    peer = Message(env, protocol(), JSON())

    # Send does not fail immediately.
    ev = peer.send('foo')
    try:
        yield ev
    except SocketError as e:
        assert e.errno == errno.ENOTCONN


def test_unconnected_recv(env, protocol):
    """Calling recv() on an unconnected socket will fail."""
    peer = Message(env, protocol(), JSON())

    try:
        yield peer.recv()
    except SocketError as e:
        assert e.errno == errno.ENOTCONN
