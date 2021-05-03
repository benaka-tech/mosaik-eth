from weakref import WeakValueDictionary
import re
from types import MethodType

from simpy.core import Process
from simpy.io.access import Access, Hierarchy
from simpy.io.dispatcher import Dispatcher, HierarchyDispatcher


class Proxy(object):
    __slots__ = ('_rpc', '_path', '__weakref__')

    def __init__(self, rpc, path):
        self._rpc = rpc
        self._path = path
        self._rpc.proxies[path] = self

    def __call__(self, *args, **kwargs):
        return self._rpc.dispatch((self._path, args, kwargs))

    def __getattr__(self, name):
        # Don't allow to call any private or protected methods.
        if not name.startswith('_'):
            path = self._path + '/' + name if self._path else name
            if path in self._rpc.proxies:
                return self._rpc.proxies[path]

            return Proxy(self._rpc, path)


class RPC(object):
    def __init__(self, socket, router):
        self.socket = socket
        self.router = router

        self.env = socket.env
        self.proxies = WeakValueDictionary()
        self._handler = self.env.process(self.handler())

    def configure(self, initiate):
        """Establishes the connection (used for authentication, etc.)."""
        event = self.env.event()
        event.succeed(self)
        return event

    def dispatch(self, path, args, kwargs):
        raise NotImplementedError(self)

    def reply(self, request, ok, value):
        raise NotImplementedError(self)

    def handler(self):
        raise NotImplementedError(self)

    def close(self):
        self.socket.close()

    class Descriptor(Hierarchy.Descriptor):
        def __init__(self, accessor_type):
            Hierarchy.Descriptor.__init__(self, accessor_type)

            # Create the rpc dictionary for accessor type. Extend the base
            # classes rpc dictionary by default.
            if hasattr(self.accessor_type, 'rpc'):
                rpc = dict(self.accessor_type.rpc)
            else:
                rpc = {}
            setattr(self.accessor_type, 'rpc', rpc)

        def call(self, func):
            def wrapper(protocol, request, obj, args, kwargs):
                try:
                    request.succeed(func(obj, *args, **kwargs))
                except BaseException as e:
                    request.fail(e)

            self.expose(func, wrapper)
            return func

        def process(self, func):
            def wrapper(protocol, request, obj, args, kwargs):
                Process(protocol.env, func(obj, *args, **kwargs))\
                    .callbacks.append(request.trigger)

            self.expose(func, wrapper)
            return func

        def passthru(self, func):
            def wrapper(protocol, request, obj, args, kwargs):
                func(obj, protocol, request, *args, **kwargs)

            self.expose(func, wrapper)
            return func

        def expose(self, func, wrapper):
            self.accessor_type.rpc[func.__name__] = wrapper
            wrapper.target = func
            setattr(func, self.name,
                    Hierarchy.Descriptor(RPC.CallableAccessor, self.name))

        __call__ = call

    class Accessor(Hierarchy.Accessor):
        def dispatch(self, protocol, request, path):
            # TODO Handle errors.
            path = path.split('/')
            try:
                accessor = getattr(self.lookup(path[:-1]), self.__accessname__)
                func = accessor.rpc[path[-1] if path[-1] else '__call__']
            except BaseException as e:
                raise RuntimeError('Failed to resolve path %s' % (
                        '/'.join(path)))

            return func, accessor.obj

        def resolve(self, obj):
            # TODO Handle errors.

            # FIXME Is there a better way to figure out if descriptors of obj
            # work?
            if type(obj) is MethodType:
                descriptor = getattr(obj, self.__accessname__)
                accessor = descriptor.__get__(obj)
            else:
                accessor = getattr(obj, self.__accessname__)

            # Check for invalid root.
            if accessor.root is not self.obj:
                raise RuntimeError('%s belongs to a different hierarchy' % obj)

            return '/'.join(accessor.path)

    class CallableAccessor(Hierarchy.Accessor):
        @property
        def name(self):
            return self.obj.__name__

        @property
        def parent(self):
            return self.obj.__self__
