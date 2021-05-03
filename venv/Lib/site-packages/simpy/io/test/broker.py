import pytest

from simpy.io.network import RemoteException
from simpy.io.broker import RPC
from simpy.io.json import JSON

# TODO The protocol for node must be configurable, so that the http broker can
# be tested too.


class Node(object):
    @JSON.Descriptor
    class rpc(JSON.Accessor):
        @property
        def name(self):
            return self.obj.name

        @property
        def parent(self):
            return self.obj.parent

        def get_child(self, name):
            return self.obj.children[name]

    def __init__(self, name='', *children):
        self.name = name
        self.parent = None
        self.children = {}
        for child in children:
            child.parent = self
            self.children[child.name] = child


def test_broker(env, protocol):
    class Greeter(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc
        def greet(self, name):
            return 'Hi %s, I am a call' % name

        @rpc.passthru
        def forward(self, protocol, request, name):
            request.succeed('Hi %s, I am a passthru call' % name)

        @rpc
        def __call__(self, name):
            return 'Hi %s, I am a functor call' % name

        @rpc.process
        def process(self, name):
            result = yield env.event().succeed(name)
            # PY2: return statement with a value is not allowed inside a
            # generator.
            env.exit('Hi %s, I am a process call' % result)

    greeter = Greeter()

    # TODO Is it possible to provide the socket pair through a fixture? The
    # accept() call is problematic.
    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    server = JSON(sock_a, greeter.rpc)
    client = JSON(sock_b)

    result = yield client.remote.greet('Graham')
    assert result == 'Hi Graham, I am a call'

    result = yield client.remote.forward('John')
    assert result == 'Hi John, I am a passthru call'

    result = yield client.remote('Terry')
    assert result == 'Hi Terry, I am a functor call'

    result = yield client.remote.process('Eric')
    assert result == 'Hi Eric, I am a process call'


def test_expose_process(env, protocol):
    class Greeter(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc.process
        def delayed_greet(self):
            yield env.timeout(0.1)
            env.exit('hi there')

    greeter = Greeter()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    server = JSON(sock_a, greeter.rpc)
    client = JSON(sock_b)

    result = yield client.remote.delayed_greet()
    assert result == 'hi there'


def test_access_unexposed_method(env, protocol):
    class Greeter(Node):
        def greet(self):
            return 'hi there'

    greeter = Greeter()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    server = JSON(sock_a, greeter.rpc)
    client = JSON(sock_b)

    try:
        yield client.remote.greet()
        pytest.fail('Expected a remote exception')
    except RemoteException as e:
        assert str(e).endswith('RuntimeError: Failed to resolve path greet\n')


def test_access_nonexisting_method(env, protocol):
    node = Node()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    server = JSON(sock_a, node.rpc)
    client = JSON(sock_b)

    try:
        yield client.remote.greet()
        pytest.fail('Expected a remote exception')
    except RemoteException as e:
        assert str(e).endswith('RuntimeError: Failed to resolve path greet\n')


def test_callback(env, protocol):
    class Publisher(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc.call
        def set_callback(self, callback):
            self.callback = callback

    class Subscriber(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc.call
        def callback(self, value):
            self.value = value

    publisher = Publisher()
    subscriber = Subscriber()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_publisher = JSON(sock_a, publisher.rpc)
    peer_subscriber = JSON(sock_b, subscriber.rpc)

    yield peer_subscriber.remote.set_callback(subscriber.callback)

    yield publisher.callback('test')
    assert subscriber.value == 'test'


def test_hierarchy(env, protocol):
    class CustomNode(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc
        def get_name(self):
            return self.name

    root = CustomNode('a0',
            CustomNode('a1'),
            CustomNode('b1', CustomNode('a2')))

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_a = JSON(sock_a, root.rpc)
    peer_b = JSON(sock_b)

    assert (yield peer_b.remote.get_name()) == 'a0'
    assert (yield peer_b.remote.a1.get_name()) == 'a1'
    assert (yield peer_b.remote.b1.get_name()) == 'b1'
    assert (yield peer_b.remote.b1.a2.get_name()) == 'a2'


@pytest.mark.xfail
def test_router(env, protocol):
    news = rpc.router()

    @rpc
    @news.pattern(r'(\w+)/year_(\d+)')
    def view(topic, year, reader):
        return 'Dear %s, there are no news about %s for the year %s' % (
                reader, topic, year)

    server = rpc.broker(env, JSON, news, protocol.server(('127.0.0.1', 0)))
    client = rpc.broker(env, JSON)

    sock = protocol.connection(server.address)
    news_proxy = (yield client.connect(sock)).remote

    result = yield news_proxy.monty_python.year_1900('Jack')
    assert (result == 'Dear Jack, there are no news about monty_python '
            'for the year 1900')


@pytest.mark.xfail
def test_mismatch(env, protocol):
    news = rpc.router()

    @rpc
    @news.pattern(r'(\w+)/year_(\d+)')
    def view(topic, year, reader):
        return 'Dear %s, there are no news about %s for the year %s' % (
                reader, topic, year)

    server = rpc.broker(env, JSON, news, protocol.server(('127.0.0.1', 0)))
    client = rpc.broker(env, JSON)

    sock = protocol.connection(server.address)
    news_proxy = (yield client.connect(sock)).remote

    try:
        yield news_proxy.monty_python('Jack')
    except RemoteException as exc:
        assert exc.remote_traceback.endswith(
                'Failed to match the path monty_python\n')


def test_exception(env, protocol):
    class FailNode(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc
        def fail(self):
            raise RuntimeError('I failed')

    failnode = FailNode()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_a = JSON(sock_a, failnode.rpc)
    peer_b = JSON(sock_b)

    try:
        yield peer_b.remote.fail()
        assert False, 'Where is the exception?'
    except RemoteException as exc:
        assert exc.remote_traceback.endswith('I failed\n')


def test_result_encoding_exception(env, protocol):
    class FailNode(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc
        def fail(self):
            return object()

    failnode = FailNode()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_a = JSON(sock_a, failnode.rpc)
    peer_b = JSON(sock_b)

    try:
        yield peer_b.remote.fail()
        assert False, 'Where is the exception?'
    except RemoteException as exc:
        assert 'ValueError: Failed to encode' in exc.remote_traceback


def test_result_decoding_exception(env, protocol):
    class MyType(object):
        def __init__(self, value):
            self.value = value

        @staticmethod
        def encode(obj):
            return obj.value

        @staticmethod
        def decode(data):
            return MyType(data)

    class MyJSON(JSON):
        types = (MyType,)

    class FailNode(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        @rpc
        def fail(self):
            return MyType('eggs and spam')

    failnode = FailNode()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_a = MyJSON(sock_a, failnode.rpc)
    peer_b = JSON(sock_b)

    # FIXME Should I really need to defuse in this case?
    peer_b.message.reader.defused = True
    peer_b.message.writer.defused = True

    try:
        yield peer_b.remote.fail()
        assert False, 'Where is the exception?'
    except ValueError as exc:
        assert 'Failed to decode' in exc.args[0]


def test_invalid_hierarchy(env, protocol):
    class MyNode(Node):
        @JSON.Descriptor
        class rpc(Node.rpc):
            pass

        def __init__(self):
            Node.__init__(self)
            self.another_root = Node()

        @rpc
        def get_wrong_hierarchy(self):
            return self.another_root

    node = MyNode()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    peer_a = JSON(sock_a, node.rpc)
    peer_b = JSON(sock_b)

    try:
        yield peer_b.remote.get_wrong_hierarchy()
        assert False, 'Where is the exception?'
    except RemoteException as exc:
        assert 'Failed to encode' in exc.args[1]

# TODO Test exception if calling an object without __call__.
# TODO Test equality and hash function of proxy.
# TODO Test binding a function as root?
# TODO Test broker property of proxies.
# TODO Test connection shutdowns.
# TODO Test forwarding of proxies to a peer with no direct connection to the
# proxies host.
