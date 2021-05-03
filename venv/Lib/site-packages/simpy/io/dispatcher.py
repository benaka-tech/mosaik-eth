class Dispatcher(object):
    def dispatch(self, protocol, path, request, args, kwargs):
        raise NotImplementedError(self)

    def path(self, obj):
        raise NotImplementedError(self)


class HierarchyDispatcher(Dispatcher):
    def __init__(self, access, root_accessor):
        self.access = access
        self.root_accessor = root_accessor
        self.root = root_accessor.obj if root_accessor is not None else None

    def dispatch(self, protocol, path, request, args, kwargs):
        self.root_accessor.lookup_accessor(path)(protocol, request,
                args, kwargs)

    def path(self, obj):
        if obj is self.root:
            return []
        path = self.access.access(obj).path_accessor
        if self.access.access(path[0].parent).obj is not self.root:
            raise ValueError('%s does not belong to the hierarchy of %s' % (
                    obj, self.root))
        return [accessor.name for accessor in path]


class StaticDispatcher(Dispatcher):
    # TODO Implement by looking at django.
    # TODO Create a separate class to lookup the routes. This could be reused
    # for lookup objects in a normal hierarchy.
    def __init__(self, routes):
        """Resolves paths to objects by traversing a static set of routes. This
        router has the disadvantage of being static, meaning that you can't
        handle changing object hierarchies. However, this also has the benefit
        that no objects can be accidentily exposed."""
        self.routes = routes

    def dispatch(self, protocol, path, request, args, kwargs):
        raise NotImplementedError(self)

    def path(self, obj):
        raise NotImplementedError(self)
