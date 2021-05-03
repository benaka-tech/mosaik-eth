import math

from simpy.io.codec import JSON

# TODO Custom converters.

basic_dataset = {
        'str': 'spam',
        'int': 42,
        'float': math.pi,
        'list': [1, 2, 3],
        'dict': {'a': 1, 'b': 2, 'c': 3},
}


def test_json_basic():
    codec = JSON()

    assert codec.decode(codec.encode(basic_dataset)) == basic_dataset


def test_json_custom():
    class MyType(object):
        def __init__(self, value):
            self.value = value

        @staticmethod
        def encode(obj):
            return obj.value

        @staticmethod
        def decode(data):
            return MyType(data)


    codec = JSON(types=((MyType, MyType.encode, MyType.decode),))

    obj1 = MyType('spam')
    obj2 = codec.decode(codec.encode(obj1))

    assert type(obj1) == type(obj2)
    assert obj1.value == obj2.value


def test_json_invalid_custom_decode():
    codec = JSON()
    assert codec.decode('{"__type__": [1, 2, 3]}') == {'__type__': [1, 2, 3]}
    assert codec.decode('{"__type__": [1]}') == {'__type__': [1]}

    try:
        codec.decode('{"__type__": [0, ""]}')
        assert False, 'Expected an exception'
    except ValueError as e:
        assert 'Failed to decode' in e.args[0]


def test_json_invalid_custom_encode():
    from datetime import datetime

    codec = JSON()

    try:
        codec.encode(datetime.now())
    except ValueError as e:
        assert 'Failed to encode' in e.args[0]
