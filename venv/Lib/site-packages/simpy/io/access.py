import types
import functools


class Access(object):
    class Accessor(object):
        def __init__(self, name, obj):
            """An accessor provides information about ``obj``."""
            self.__accessname__ = name
            self.obj = obj

    class Descriptor(object):
        def __init__(self, accessor_type, name=None):
            self.accessor_type = accessor_type
            self.name = accessor_type.__name__ if name is None else name

            if not issubclass(self.accessor_type, Access.Accessor):
                raise RuntimeError('%s is not a subclass of %s' % (
                        self.accessor_type, Accessor.__name__))

        def __get__(self, obj, objtype=None):
            if obj is None:
                return self.accessor_type
            return self.accessor_type(self.name, obj)


class Hierarchy(Access):
    class Accessor(Access.Accessor):
        @property
        def name(self):
            raise NotImplementedError(self)

        @property
        def parent(self):
            raise NotImplementedError(self)

        @property
        def get_child(self):
            raise NotImplementedError(self)

        @property
        def path(self):
            path = []
            while True:
                parent = self.parent
                if parent is None:
                    return path
                path.insert(0, self.name)
                self = getattr(parent, self.__accessname__)

        @property
        def root(self):
            while True:
                parent = self.parent
                if parent is None:
                    return self.obj
                self = getattr(parent, self.__accessname__)

        def lookup(self, path):
            if not path:
                return self.obj

            accessor = getattr(self.get_child(path[0]), self.__accessname__)
            return accessor.lookup(path[1:])
