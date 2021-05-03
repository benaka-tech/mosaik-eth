from simpy.io.access import Hierarchy


class Item(object):
    @Hierarchy.Descriptor
    class hierarchy(Hierarchy.Accessor):
        @property
        def name(self):
            return self.obj.name

        @property
        def parent(self):
            return self.obj.parent

        def get_child(self, name):
            return self.obj.children[name]

    def __init__(self, name, children=(), parent=None):
        self._name = name
        self._parent = parent

        self.children = {}
        for child in children:
            child._parent = self
            self.children[child.name] = child

    @property
    def name(self):
        return self._name

    @property
    def parent(self):
        return self._parent



class Root(Item):
    def __init__(self, children):
        Item.__init__(self, None, children)

    def get_view(self, path):
        return '/'.join(path)


def test_hierarchy():
    root = Root([Item('a', [Item('b')])])

    path = ['a', 'b']
    b = root.hierarchy.lookup(path)

    assert b.hierarchy.path == path
    assert b.hierarchy.root == root

# TODO Objects with multiple accesses.
