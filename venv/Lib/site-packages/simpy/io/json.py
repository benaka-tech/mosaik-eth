from simpy.io import codec
from simpy.io.packet import Packet
from simpy.io.message import Message, RemoteException
from simpy.io.broker import RPC, Proxy


class JSON(RPC):
    types = ()
    converters = ()

    def __init__(self, socket, router=None):
        RPC.__init__(self, socket, router)

        self.codec = codec.JSON(
                self.types +
                    ((Proxy, self._encode_proxy, self._decode_proxy),),
                self.converters + ((self._encode_obj, self._decode_obj),))
        self.message = Message(self.env, self.socket, self.codec)
        self.remote = Proxy(self, '')

    def dispatch(self, call):
        return self.message.send(call)

    def handler(self):
        # TODO Decide if errors should be handled here, in dispatch() or in
        # callbacks to this process.
        try:
            while True:
                request = yield self.message.recv()
                path, args, kwargs = request.content

                try:
                    func, obj = self.router.dispatch(self, request, path)
                except Exception as e:
                    # FIXME Shouldn't the dispatcher handle these errors?
                    request.fail(e)
                    continue

                func(self, request, obj, args, kwargs)
        except Exception as e:
            # TODO Add proper handling of socket errors.
            pass

    def _encode_proxy(self, proxy):
        if proxy._rpc is not self:
            raise RuntimeError('Cannot serialize proxies of different '
                    'connections')

        return proxy._path

    def _decode_proxy(self, path):
        return self.router.lookup(path.split('/'))

    def _encode_obj(self, obj):
        return self.router.resolve(obj)

    def _decode_obj(self, path):
        try:
            proxy = self.proxies[path]
        except KeyError:
            proxy = Proxy(self, path)

        return proxy
