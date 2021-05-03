import os
import socket


class RemoteException(Exception):
    def __init__(self, origin, remote_traceback):
        Exception.__init__(self, origin, remote_traceback)
        self.origin = origin
        self.remote_traceback = remote_traceback

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return 'Origin %s\n%s' % (self.origin, self.remote_traceback)


class AbstractNetwork(object):
    def socket(self):
        raise NotImplementedError(self)

    def serve(self, address, backlog=5):
        socket = self.socket()
        socket.bind(address)
        socket.listen(backlog)
        return socket

    def connect(self, address):
        socket = self.socket()
        socket.connect(address)
        return socket


class BaseSocket(object):
    # TODO Maybe add a property to check the state of the socket?
    def bind(self, address):
        raise NotImplementedError(self)

    def listen(self, backlog):
        raise NotImplementedError(self)

    def accept(self):
        raise NotImplementedError(self)

    def connect(self, address):
        raise NotImplementedError(self)

    def read(self, amount):
        """Returns an event that will be triggered if *at least* one byte but
        *at most* ``amount`` of bytes are available for reading."""
        raise NotImplementedError(self)

    def write(self, data):
        raise NotImplementedError(self)

    def close(self):
        raise NotImplementedError(self)

    @property
    def address(self):
        raise NotImplementedError(self)

    @property
    def peer_address(self):
        raise NotImplementedError(self)


class Protocol(object):
    def __init__(self, env, *elements, **configs):
        self.env = env
        self.elements = elements
        self.configs = configs

    def __call__(self):
        parent = (self.env,)
        for element in reversed(self.elements):
            socket = element(*parent, **self.configs.get(element, {}))
            parent = (socket,)
        return socket

    def server(self, address, backlog=5):
        socket = self()
        socket.bind(address)
        socket.listen(backlog)
        return socket

    def connection(self, address):
        socket = self()
        socket.connect(address)
        return socket


def socket_error(errno):
    return socket.error(errno, os.strerror(errno))


def fail_func(exception_type, *exc_args, **exc_kwargs):
    def func(*args, **kwargs):
        raise exception_type(*exc_args, **exc_kwargs)
    return func
