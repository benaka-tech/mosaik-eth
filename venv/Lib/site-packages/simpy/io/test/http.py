from __future__ import absolute_import

import errno
from socket import error as SocketError

import pytest

from simpy._compat import PY2
from simpy.io.http import Client, Service, HTTP

if not PY2:
    from http.client import HTTPException
else:
    from httplib import HTTPException
    from simpy.io._compat import ConnectionError
    from simpy.io import platform


@pytest.fixture()
def server(env, socket_type):
    return socket_type.server(env, ('127.0.0.1', 0))


@pytest.fixture()
def client(env, socket_type, server):
    return Client(socket_type.connection(env, server.address))


def test_request(env, socket_type, server, client):
    service = Service((yield server.accept()))

    # Dispatch request and await its transmission.
    cli_req = yield client.send('GET', '/')
    yield cli_req.write(b'dude')
    yield cli_req.write()

    # Wait until the next request is received and read all of its content.
    srv_req = yield service.recv()
    assert srv_req.uri == '/'
    srv_data = yield srv_req.read(all=True)

    # Send the response.
    srv_res = yield srv_req.respond(200)
    yield srv_res.write(b'hello ' + srv_data)
    yield srv_res.write()

    # Wait for the response and check its contents.
    cli_res = yield cli_req.response()
    cli_data = yield cli_res.read(all=True)
    assert cli_data == b'hello dude'


def test_concurrent_send(env, socket_type, server, client):
    service = Service((yield server.accept()))

    client.send('GET', '/')
    try:
        client.send('GET', '/')
        assert False, 'There should have been an error'
    except RuntimeError as e:
        assert e.args == ('Already sending',)


def test_concurrent_write(env, socket_type, server, client):
    service = Service((yield server.accept()))

    cli_req = yield client.send('GET', '/')
    cli_req.write(b'one')
    try:
        cli_req.write(b'two')
        assert False, 'There should have been an error'
    except RuntimeError as e:
        assert e.args == ('Concurrent write attempt',)


def test_concurrent_recv(env, socket_type, server, client):
    service = Service((yield server.accept()))

    service.recv()
    try:
        service.recv()
        assert False, 'There should have been an error'
    except RuntimeError as e:
        assert e.args == ('Already receiving',)


def test_concurrent_reads(env, socket_type, server, client):
    service = Service((yield server.accept()))

    cli_req = yield client.send('GET', '/')
    srv_req = yield service.recv()
    srv_req.read()
    try:
        srv_req.read()
        assert False, 'There should have been an error'
    except RuntimeError as e:
        assert e.args == ('Concurrent read attempt',)


def test_immediate_read_and_write(env, socket_type, server, client):
    service = Service((yield server.accept()))

    # Create a request but don't wait for headers to be sent.
    cli_req = client.send('GET', '/')
    # Directly writing to the request without waiting for the headers to be
    # sent is allowed for convenience.
    yield cli_req.write(b'foo')
    yield cli_req.write()

    # Create the incoming request but also don't wait for the headers to be
    # received.
    srv_req = service.recv()
    # Immediately reading from the request is allowed for convenience.
    data = yield srv_req.read(all=True)
    assert data == b'foo'


def test_out_of_order_response(env, socket_type, server, client):
    service = Service((yield server.accept()))

    yield client.get()
    yield client.get()

    srv_req1 = yield service.recv()
    yield srv_req1.read(all=True)
    srv_req2 = yield service.recv()
    yield srv_req2.read(all=True)

    try:
        srv_req2.respond(200)
        assert False, 'There should have been an error'
    except RuntimeError as e:
        assert e.args == ('Out of order response',)


def test_convenience_request(env, socket_type, server, client):
    service = Service((yield server.accept()))

    cli_req = yield client.get()
    srv_req = yield service.recv()
    assert srv_req.uri == ''
    yield srv_req.read(all=True)
    yield srv_req.respond(200, data=b'hello')

    cli_res = yield cli_req.response()
    data = yield cli_res.read(all=True)
    assert data == b'hello'

    # TODO Also test put.


def test_pipeline(env, socket_type, server, client):
    service = Service((yield server.accept()))

    # Client side pipelining: Dispatch 10 get requests and do not wait for the
    # responses.
    cli_req = []
    for i in range(10):
        req = yield client.get()
        cli_req.append(req)

    # Server side pipelining: Fetch all 10 incoming requests, read their
    # content but do not reply yet.
    srv_req = []
    for i in range(10):
        req = yield service.recv()
        assert req.method == 'GET'
        assert req.uri == ''
        yield req.read(all=True)
        srv_req.append(req)

    # Now respond all requests.
    for req in srv_req:
        yield req.respond(200, data=b'hello')

    # And finally read the responses.
    for req in cli_req:
        # Wait for the response headers.
        cli_res = yield req.response()
        # And read the response content.
        data = yield cli_res.data()
        assert data == b'hello'


def test_request_chunks(env, socket_type, server, client):
    service = Service((yield server.accept()))

    send_characters = list('abcdefghij')
    for i in range(3):
        cli_req = yield client.send('GET', '/')
        for character in send_characters:
            yield cli_req.write(character.encode('utf-8'))
        yield cli_req.write()

    for i in range(3):
        srv_req = yield service.recv()
        recv_characters = []
        for character in send_characters:
            recv_characters.append((yield srv_req.read()).decode('utf-8'))
        yield srv_req.read()
        yield srv_req
        assert send_characters == recv_characters


def test_response_chunks(env, socket_type, server, client):
    service = Service((yield server.accept()))

    for i in range(4):
        cli_req = yield client.get()

        srv_req = yield service.recv()
        yield srv_req.read(all=True)
        srv_res = srv_req.respond(200, phrase='OK')

        cli_res = yield cli_req.response()
        assert cli_res.code == '200' and cli_res.phrase == 'OK'

        send_characters = list('abcdefghij')
        recv_characters = []
        for character in send_characters:
            yield srv_res.write(character.encode('utf-8'))
            recv_characters.append((yield cli_res.read()).decode('utf-8'))
        yield srv_res.write()
        yield cli_res.read()
        yield cli_res

        assert send_characters == recv_characters


def test_service_close(env, socket_type, server, client):
    service = Service((yield server.accept()))

    cli_req = client.put()
    cli_req.defused = True

    srv_req = yield service.recv()
    srv_req.defused = True
    srv_res = srv_req.respond(200, phrase='OK')

    # Close the client.
    cli_res = yield cli_req.response()
    assert cli_res.code == '200'
    client.close()

    # The server won't notice that the client has closed the connection unless
    # it is waiting for data.
    try:
        yield srv_req.read()
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_http_broker(env, socket_type):
    class MyResource(object):
        @HTTP.Descriptor
        class http(HTTP.Accessor):
            parent = None

        @http
        @http.headers({'Content-Type': 'text/html'})
        def greet(self):
            return 'hi there'

    root = MyResource()

    server_sock = socket_type.server(env, ('127.0.0.1', 0))

    # FIXME Use a broker as client.
    client = Client(socket_type.connection(env, server_sock.address))

    sock = yield server_sock.accept()
    conn = HTTP(sock, root.http, client=False)

    cli_req = yield client.get('/greet')
    response = yield cli_req.response()
    assert response.headers['Content-Type'] == 'text/html'
    data = yield response.read(all=True)
    assert data == b'hi there'


def test_consequent_error_after_local_close(env, socket_type, server, client):
    service = Service((yield server.accept()))
    client.close()

    cli_req = client.get()
    try:
        yield cli_req
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF

    try:
        yield cli_req.response()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF

    # Consequent requests will fail with the same error.
    try:
        client.get()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno == errno.EBADF


def test_consequent_error_after_peer_close(env, socket_type, server, client):
    service = Service((yield server.accept()))
    cli_req = yield client.get()
    srv_req = yield service.recv()
    yield srv_req.respond(200, data=b'test')
    cli_res = yield cli_req.response()
    yield cli_res.data()

    cli_req = yield client.get()
    service.close()

    try:
        yield cli_req.response()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    # Consequent requests will fail with the same error.
    try:
        client.get()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_local_close_during_read_chunked_transfer(env, socket_type, server,
        client):
    service = Service((yield server.accept()))

    cli_req = client.get()
    srv_req = yield service.recv()

    # Send two chunks. The first chunk is read and the second is started to be
    # read. However, the client then immediately closes the socket causing the
    # read event to fail.
    srv_res = yield srv_req.respond(200)
    cli_res = yield cli_req.response()
    yield srv_res.write(b'foo')
    data = yield cli_res.read()
    assert data == b'foo'
    yield srv_res.write(b'spam')
    read_ev = cli_res.read()

    client.close()
    try:
        yield read_ev
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)

    # Further read attempts fail immediately.
    try:
        cli_res.read()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)


def test_local_close_during_write_chunked_transfer(env, socket_type, server,
        client):
    service = Service((yield server.accept()))

    cli_req = yield client.put()
    srv_req = yield service.recv()

    # Write two chunks. The first chunk is written and the second is started to
    # be written. However, the client then immediately closes the socket
    # causing the write event to fail.
    yield srv_req.respond(200)
    yield cli_req.write(b'foo')
    data = yield srv_req.read()
    assert data == b'foo'
    write_ev = cli_req.write(b'spam')

    client.close()
    try:
        yield write_ev
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)

    # Further write attempts fail immediately.
    try:
        cli_req.write()
        assert False, 'Expected an exception'
    except SocketError as e:
        assert e.errno in (errno.EBADF, errno.ENOTSOCK)


def test_remote_close_during_read_chunked_transfer(env, socket_type, server,
        client):
    service = Service((yield server.accept()))

    cli_req = yield client.get()
    srv_req = yield service.recv()

    # The service will write one chunk, which is read by the client. The client
    # then starts a second read attempt, while the service closes its socket.
    srv_res = yield srv_req.respond(200)
    cli_res = yield cli_req.response()
    yield srv_res.write(b'foo')
    data = yield cli_res.read()
    assert data == b'foo'
    read_ev = cli_res.read()

    service.close()
    try:
        yield read_ev
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    # Further read attempts fail immediately.
    try:
        cli_res.read()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_remote_close_during_write_chunked_transfer(env, socket_type, server,
        client):
    service = Service((yield server.accept()))

    cli_req = yield client.put()
    srv_req = yield service.recv()

    # The client will write one chunk, which is read by the service. The client
    # then starts further write attempts, while the service closes its socket.
    # The client will be notified of the remote close at some point.
    yield srv_req.respond(200)
    yield cli_req.write(b'foo')
    data = yield srv_req.read()
    assert data == b'foo'

    service.close()

    try:
        # See simpy/io/test/socket.py:test_write_after_peer_close for an
        # explanation.
        for i in range(3):
            yield cli_req.write(b'spam' * 1024)
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors

    # Further write attempts fail immediately.
    try:
        cli_req.write()
        assert False, 'Expected an exception'
    except ConnectionError:
        pass
    except SocketError as e:
        assert PY2 and e.errno in platform.connection_errors


def test_invalid_client_request(env, socket_type, server):
    client = socket_type.connection(env, server.address)
    service = Service((yield server.accept()))

    yield client.write(b'foo\r\n\r\n')

    try:
        yield service.recv()
        assert False, 'Expected an exception'
    except HTTPException as e:
        assert e.args[0] == 'Malformed header:\nfoo'


def test_invalid_client_request_encoding(env, socket_type, server):
    client = socket_type.connection(env, server.address)
    service = Service((yield server.accept()))

    yield client.write(b'f\xc3\xb6\xc3\xb6\r\n\r\n')

    try:
        yield service.recv()
        assert False, 'Expected an exception'
    except HTTPException as e:
        assert e.args[0].startswith('Malformed header:\nf')


def test_invalid_chunk_header(env, socket_type, server):
    client = socket_type.connection(env, server.address)
    service = Service((yield server.accept()))

    yield client.write(b'PUT / HTTP/1.1\r\n'
            b'Transfer-Encoding: chunked\r\n\r\nfoo\r\n')
    srv_req = yield service.recv()

    try:
        yield srv_req.read()
        assert False, 'Expected an exception'
    except HTTPException as e:
        assert e.args[0] == 'Malformed chunk header:\nfoo'


def test_max_header_size(env, socket_type, server):
    client = socket_type.connection(env, server.address)
    service = Service((yield server.accept()))

    yield client.write(b' ' * service.max_header_size)

    try:
        yield service.recv()
        assert False, 'Expected an exception'
    except HTTPException as e:
        assert e.args[0] == 'Header size limit exceeded'


def test_max_chunked_header_size(env, socket_type, server):
    client = socket_type.connection(env, server.address)
    service = Service((yield server.accept()))

    data = (b'PUT / HTTP/1.1\r\n' +
            b'Transfer-Encoding: chunked\r\n\r\n' +
            b' ' * service.max_header_size)
    while data:
        data = data[(yield client.write(data)):]

    srv_req = yield service.recv()

    try:
        yield srv_req.read()
        assert False, 'Expected an exception'
    except HTTPException as e:
        assert e.args[0] == 'Chunk header size limit exceeded'


def test_read_on_pending_response(env, socket_type, server, client):
    """The response may be requested at any time, even if the headers have not
    yet been sent. The same is true for read attempts."""
    service = Service((yield server.accept()))

    cli_req = client.get()
    cli_res = cli_req.response()
    read_ev = cli_res.read()

    srv_req = yield service.recv()
    yield srv_req.respond(200, data=b'foo')

    data = yield read_ev
    assert data == b'foo'


def test_write_on_pending_request(env, socket_type, server, client):
    """Data may be written to a request, even though the headers have not yet
    been sent."""
    service = Service((yield server.accept()))

    cli_req = client.put()
    write_ev = cli_req.write(b'foo')

    srv_req = yield service.recv()

    data = yield srv_req.read()
    assert data == b'foo'


def test_write_after_request_close(env, socket_type, server, client):
    service = Service((yield server.accept()))

    cli_req = yield client.put()
    yield cli_req.write(b'foo')
    yield cli_req.write()

    try:
        cli_req.write(b'spam')
        assert False, 'Expected an exception'
    except RuntimeError as e:
        assert e.args[0] == 'Message has already been sent'


def test_read_after_request_close(env, socket_type, server, client):
    """If all content of a message has been read, further read attempts will
    return an empty byte string."""
    service = Service((yield server.accept()))

    cli_req = yield client.put(data=b'spam')
    srv_req = yield service.recv()
    data = yield srv_req.read()
    assert data == b'spam'

    data = yield srv_req.read()
    assert data == b''
    data = yield srv_req.read()
    assert data == b''


@pytest.mark.skip()
def test_decommission_with_pending_data(env, socket_type, server, client):
    service = Service((yield server.accept()))
