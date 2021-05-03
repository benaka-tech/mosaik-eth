from simpy.io.websocket import WebSocket, WebSocketHixie

# TODO Decommission of a http channel.
# TODO Decommission of a http channel with pending writes.
# TODO Server close.
# TODO Client close.

def test_websocket(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            conn = yield service.accept()
            websock = WebSocket(conn)
            yield websock.configure(False)
            data = yield websock.read()
            yield websock.write(b'echo ' + data)

    env.process(server(env, service))

    websock = WebSocket(socket_type.connection(env, service.address))
    yield websock.configure(True)

    yield websock.write(b'echo')
    response = yield websock.read()

    assert response == b'echo echo'


def test_websocket_hixie(env, socket_type):
    service = socket_type.server(env, ('127.0.0.1', 0))

    def server(env, service):
        while True:
            conn = yield service.accept()
            websock = WebSocketHixie(conn,
                    origin='http://%s:%d' % service.address,
                    location='ws://%s:%d' % service.address)
            yield websock.configure(False)
            data = yield websock.read()
            yield websock.write(b'echo ' + data)

    env.process(server(env, service))

    websock = WebSocketHixie(socket_type.connection(env, service.address),
            origin='http://%s:%d' % service.address,
            location='ws://%s:%d' % service.address)
    yield websock.configure(True)

    yield websock.write(b'echo')
    response = yield websock.read()

    assert response == b'echo echo'
