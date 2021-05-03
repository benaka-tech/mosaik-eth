import pytest

from simpy.io.network import RemoteException
from simpy.io.broker import RPC
from simpy.io.json import JSON


def test_custom_type(env, protocol):
    class MyType(object):
        def __init__(self, value):
            self.value = value

        @staticmethod
        def encode(obj):
            return obj.value

        @staticmethod
        def decode(data):
            return MyType(data)


    class MyConvertible(object):
        def __init__(self, value):
            self.value = value

        @staticmethod
        def encode(obj):
            return obj.value

        @staticmethod
        def decode(data):
            return MyConvertible(data)


    class MyJSON(JSON):
        types = (MyType,)
        converters = (MyConvertible,)

    class Greeter(object):
        @JSON.Descriptor
        class rpc(JSON.Accessor):
            @property
            def name(self):
                return self.obj.name

            @property
            def parent(self):
                return self.obj.parent

        @rpc
        def greet(self):
            return MyType('hi there'), MyConvertible('how are you?')

    greeter = Greeter()

    server_sock = protocol.server(('127.0.0.1', 0))
    sock_a = protocol.connection(server_sock.address)
    sock_b = yield server_sock.accept()

    server = MyJSON(sock_a, greeter.rpc)
    client = MyJSON(sock_b)

    my_type, my_convertible = yield client.remote.greet()
    assert type(my_type) == MyType
    assert my_type.value == 'hi there'
    assert type(my_convertible) == MyConvertible
    assert my_convertible.value == 'how are you?'
