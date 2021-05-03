from simpy.io.packet import Packet, Header


def test_packet(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    conn_a = Packet(socket_type.connection(env, server.address))
    conn_b = Packet((yield server.accept()))

    yield conn_a.write(b'hello, what is your name?')
    data = yield conn_b.read()
    assert data == b'hello, what is your name?'

    yield conn_b.write(b'bob')
    data = yield conn_a.read()
    yield conn_a.write(b'nice to meet you ' + data)

    data = yield conn_b.read()
    assert data == b'nice to meet you bob'


def test_packet_size_check(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    conn_a = Packet(socket_type.connection(env, server.address),
            max_packet_size=1)
    conn_b = Packet((yield server.accept()))
    try:
        yield conn_a.write(b'spam')
        assert False, 'Expected an exception'
    except ValueError as e:
        assert e.args[0] == 'Packet too large. Allowed 1 bytes but got 4 bytes'


def test_packet_chunks(env, socket_type):
    server = socket_type.server(env, ('127.0.0.1', 0))
    conn = socket_type.connection(env, server.address)

    def reader(env, server):
        conn = Packet((yield server.accept()))
        payloads = []
        try:
            while True:
                payloads.append((yield conn.read()))
        except:
            # Ignore connection errors.
            pass

        env.exit(payloads)

    reader_process = env.process(reader(env, server))

    send_payloads = [b'eggs', b'spam']
    for payload in send_payloads:
        packet = Header.pack(len(payload)) + payload
        for i in range(len(packet)):
            yield conn.write(packet[i:i+1])
    conn.close()

    recv_payloads = yield reader_process
    assert recv_payloads == send_payloads
